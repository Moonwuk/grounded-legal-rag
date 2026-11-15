"""HTTP adapter for the submission's answer policy."""
from contextlib import asynccontextmanager
import json
import os
import re
from pathlib import Path
import sys
from threading import BoundedSemaphore, Thread
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from web.history import History, identity, router as history_router

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).with_name("static")
sys.path.insert(0, str(ROOT / "prototype"))

from psb_corpus import load_corpus
from psb_llm import EmbeddingClient, ProviderError, ProxyClient, integer
from psb_policy import TECHNICAL, answer_structured, display_name
from psb_retrieval import Retriever

LABELS = {"user": "Пользователь", "assistant": "Ассистент"}
MAX_BODY = 256 * 1024
TOO_LONG = "Диалог слишком длинный. Начните новый."


@asynccontextmanager
async def lifespan(app):
    path = Path(os.getenv("KB_PATH") or ROOT / "organizer" / "knowledge-base.zip")
    skipped = []
    documents, fragments = load_corpus(path, skipped=skipped)
    if skipped:
        print("documents_skipped=%d reasons=%s" % (len(skipped), ",".join(sorted({c for _, c in skipped}))), file=sys.stderr)
    app.state.skipped = len(skipped)
    app.state.retriever = Retriever(documents, fragments)
    app.state.documents = {doc.sha256: doc for doc in documents}
    app.state.slots = BoundedSemaphore(integer("WEB_WORKERS", 2, 1, 8))
    app.state.dense = "off"
    history_path = os.getenv("CHAT_HISTORY_PATH", "")
    proxy_token = os.getenv("CHAT_PROXY_TOKEN", "")
    app.state.history = History(history_path, proxy_token) if history_path and proxy_token else None
    if os.getenv("EMB_MODEL", "").strip():
        # Dense candidates are indexed after start-up; until then search is BM25 only.
        app.state.dense = "indexing"
        Thread(target=index_dense, args=(app.state,), daemon=True).start()
    yield


def index_dense(state):
    try:
        client = EmbeddingClient(time.monotonic() + 10 * 365 * 86400)
        status = state.retriever.enable_dense(client, time.monotonic() + integer("PSB_DENSE_SECONDS", 600, 0, 3600))
    except ProviderError as error:
        status = "dense_disabled:" + str(error)
    state.dense = status
    print(status, file=sys.stderr)


app = FastAPI(title="Юридический ассистент", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(history_router)


@app.middleware("http")
async def private_chat_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/api/chat" or request.url.path.startswith("/api/chats"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


# UI-only signal for explicit, standalone forged system-role delimiters.
FORGED_ROLE = re.compile(r"(?im)^\s*(?:\[SYSTEM\]|<\|im_start\|>system|<\|system\|>)\s*\S")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=41)
    chat_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")


def describe(doc):
    title = display_name(doc.name)
    lower = title.lower()
    if "утратил силу" in lower:
        status = "утратил силу"
    elif "действующая" in lower:
        status = "действующая редакция"
    elif lower.startswith(("доп соглашение", "дополнительное соглашение")):
        status = "допсоглашение"
    else:
        status = ""
    category = doc.name.split("__", 1)[0] if "__" in doc.name else "документы"
    return dict(id=doc.sha256, title=title, category=category, status=status)


def to_question(messages):
    if messages[-1].role != "user":
        raise HTTPException(400, "Последнее сообщение должно быть от пользователя.")
    if any(not message.text.strip() or message.role != ("user" if i % 2 == 0 else "assistant")
           for i, message in enumerate(messages)):
        raise HTTPException(400, "Проверьте порядок сообщений и заполните вопрос.")
    if len(messages) == 1:
        return messages[0].text.strip()
    return "\n".join(f"{LABELS[m.role]}: {m.text.strip()}" for m in messages)


def model_client(deadline):
    try:
        return ProxyClient(deadline=deadline)
    except ProviderError as error:
        if str(error) == "missing_proxy_configuration":
            return None
        raise


def answer(question, state, latest_user_text=""):
    started = time.monotonic()
    if not state.slots.acquire(blocking=False):
        return dict(status="technical_error", text="Сервис занят. Повторите запрос через несколько секунд.",
                    sources=[], elapsed_seconds=0)
    try:
        client = model_client(deadline=started + 150)
        if client is None:
            return dict(
                status="technical_error",
                error_code="model_not_configured",
                text="Заполните LLM_BASE_URL, LLM_API_KEY и LLM_MODEL в файле .env и перезапустите веб-сервис.",
                sources=[],
                elapsed_seconds=round(time.monotonic() - started, 1),
            )
        result = answer_structured(question, state.retriever, client, top_k=integer("TOP_K", 6, 1, 40))
        sources = []
        for number, fragment in enumerate(result["sources"], 1):
            doc = state.retriever.documents[fragment.document]
            sources.append(dict(n=number, document_id=doc.sha256, title=display_name(doc.name),
                                status=describe(doc)["status"], heading=fragment.heading,
                                start=fragment.start, end=fragment.end, quote=fragment.text))
        response = dict(status=result["status"], text=result["text"], sources=sources,
                        elapsed_seconds=round(time.monotonic() - started, 1))
        if result["status"] in {"out_of_scope", "disallowed"} and FORGED_ROLE.search(latest_user_text):
            response["ui_state"] = "role_protection"
        return response
    except Exception as error:
        print("question_error: " + type(error).__name__, file=sys.stderr)
        return dict(status="technical_error", text=TECHNICAL, sources=[],
                    elapsed_seconds=round(time.monotonic() - started, 1))
    finally:
        state.slots.release()


@app.post("/api/chat")
async def chat(request: Request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            raise HTTPException(413, TOO_LONG)
        raw.extend(chunk)
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and isinstance(payload.get("messages"), list) and len(payload["messages"]) > 41:
            raise HTTPException(413, TOO_LONG)
        request_data = ChatRequest.model_validate(payload)
    except (ValidationError, ValueError, RecursionError):
        raise HTTPException(422, "Проверьте формат сообщений и длину вопроса.") from None
    if request_data.chat_id is not None:
        history, owner = identity(request)
        if len(request_data.messages) != 1 or request_data.messages[0].role != "user":
            raise HTTPException(400, "Для сохранённого диалога передайте только новый вопрос.")
        return await run_in_threadpool(answer_saved, history, owner, request_data.chat_id,
                                       request_data.messages[0], request.app.state)
    question = to_question(request_data.messages)
    if len(question) > 30000:
        raise HTTPException(413, TOO_LONG)
    return await run_in_threadpool(answer, question, request.app.state, request_data.messages[-1].text)


def answer_saved(history, owner, chat_id, message, state):
    turns, lease = history.begin(owner, chat_id, message.text)
    try:
        previous = []
        for turn in turns:
            if turn["answer"]["status"] != "technical_error":
                previous.extend([Message(role="user", text=turn["question"]),
                                 Message(role="assistant", text=turn["answer"]["text"])])
        question = to_question([*previous, message])
        if len(question) > 30000:
            raise HTTPException(413, TOO_LONG)
        result = answer(question, state, message.text)
        # A retry replaces the failed attempt, while technical errors never become model context.
        if turns and turns[-1]["answer"]["status"] == "technical_error" and turns[-1]["question"] == message.text:
            turns.pop()
        turns.append(dict(question=message.text, answer=result))
        history.finish(owner, chat_id, lease, turns)
        return result
    finally:
        history.finish(owner, chat_id, lease)


@app.get("/healthz")
def healthz(request: Request):
    retriever = request.app.state.retriever
    return dict(status="ok", documents=len(retriever.documents), fragments=len(retriever.fragments),
                dense=request.app.state.dense, skipped=request.app.state.skipped)


@app.get("/api/documents")
def documents(request: Request):
    return [describe(doc) for doc in request.app.state.documents.values()]


@app.get("/api/documents/{document_id}")
def document(document_id: str, request: Request):
    doc = request.app.state.documents.get(document_id)
    if doc is None:
        raise HTTPException(404, "Документ не найден.")
    return {**describe(doc), "text": doc.text}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
