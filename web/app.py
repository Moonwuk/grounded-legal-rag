"""HTTP adapter for the submission's answer policy."""
from contextlib import asynccontextmanager
import json
import os
import re
from pathlib import Path
import sys
from threading import BoundedSemaphore
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).with_name("static")
sys.path.insert(0, str(ROOT / "prototype"))

from psb_corpus import load_corpus
from psb_llm import ProviderError, ProxyClient, integer
from psb_policy import TECHNICAL, answer_structured, display_name
from psb_retrieval import Retriever

LABELS = {"user": "Пользователь", "assistant": "Ассистент"}
MAX_BODY = 256 * 1024
TOO_LONG = "Диалог слишком длинный. Начните новый."


@asynccontextmanager
async def lifespan(app):
    path = Path(os.getenv("KB_PATH") or ROOT / "organizer" / "knowledge-base.zip")
    documents, fragments = load_corpus(path)
    app.state.retriever = Retriever(documents, fragments)
    app.state.documents = {doc.sha256: doc for doc in documents}
    app.state.slots = BoundedSemaphore(integer("WEB_WORKERS", 2, 1, 8))
    yield


app = FastAPI(title="Юридический ассистент", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
# UI-only signal for explicit, standalone forged system-role delimiters.
FORGED_ROLE = re.compile(r"(?im)^\s*(?:\[SYSTEM\]|<\|im_start\|>system|<\|system\|>)\s*\S")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=41)


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
    question = to_question(request_data.messages)
    if len(question) > 30000:
        raise HTTPException(413, TOO_LONG)
    return await run_in_threadpool(answer, question, request.app.state, request_data.messages[-1].text)


@app.get("/healthz")
def healthz(request: Request):
    retriever = request.app.state.retriever
    return dict(status="ok", documents=len(retriever.documents), fragments=len(retriever.fragments))


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
