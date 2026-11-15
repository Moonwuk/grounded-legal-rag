"""Private web workspace. None of these fields are part of the RAG context."""
from datetime import date
from hashlib import sha256
import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from web.history import active_count, identity

router = APIRouter(prefix="/api/workspace")
UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
HASH = r"^[0-9a-f]{64}$"


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS chat_workspace (
        chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
        matter TEXT NOT NULL DEFAULT '{}', matter_revision INTEGER NOT NULL DEFAULT 0,
        draft TEXT NOT NULL DEFAULT '', draft_revision INTEGER NOT NULL DEFAULT 0,
        read_key TEXT NOT NULL DEFAULT '',
        parent_id TEXT REFERENCES chats(id) ON DELETE SET NULL, parent_turn INTEGER,
        branch_request TEXT NOT NULL DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS new_dialogue_drafts (
        owner TEXT PRIMARY KEY, draft TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0)""")
    # The user's own review mark of one answer version; it never changes the core status.
    db.execute("""CREATE TABLE IF NOT EXISTS answer_reviews (
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        turn_index INTEGER NOT NULL, turn_key TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT '', updated REAL NOT NULL, revision INTEGER NOT NULL,
        PRIMARY KEY(chat_id, turn_index))""")
    db.execute("""CREATE TABLE IF NOT EXISTS answer_annotations (
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        turn_index INTEGER NOT NULL, turn_key TEXT NOT NULL,
        saved INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL,
        PRIMARY KEY(chat_id, turn_index))""")

    db.execute("""CREATE TABLE IF NOT EXISTS workspace_searches (
        owner TEXT PRIMARY KEY, items TEXT NOT NULL, revision INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS workspace_recent_documents (
        owner TEXT NOT NULL, document_id TEXT NOT NULL, title TEXT NOT NULL,
        opened REAL NOT NULL, PRIMARY KEY(owner, document_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS workspace_checklists (
        chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
        items TEXT NOT NULL, revision INTEGER NOT NULL)""")


def turn_key(turn):
    return sha256(json.dumps(turn, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def workspace_row(db, chat_id):
    db.execute("INSERT OR IGNORE INTO chat_workspace(chat_id) VALUES (?)", (chat_id,))
    return db.execute("SELECT * FROM chat_workspace WHERE chat_id=?", (chat_id,)).fetchone()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def printable(cls, value):
        if isinstance(value, str) and any((ord(c) < 32 and c not in "\n\r\t") or
                                         127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Unsupported control character")
        return value


class Matter(Input):
    contract: str = Field(default="", max_length=300)
    counterparty: str = Field(default="", max_length=300)
    event_date: str = Field(default="", max_length=10)
    amount: str = Field(default="", max_length=100)
    situation: str = Field(default="", max_length=3000)

    @field_validator("event_date")
    @classmethod
    def valid_date(cls, value):
        if value and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use an ISO date")
        return value


class MatterInput(Input):
    revision: int = Field(ge=0)
    matter: Matter


class DraftInput(Input):
    revision: int = Field(ge=0)
    text: str = Field(max_length=10000)


class AnnotationInput(Input):
    revision: int = Field(ge=0)
    turn_key: str = Field(pattern=HASH)
    saved: bool
    note: str = Field(max_length=4000)


class ReviewInput(Input):
    revision: int = Field(ge=0)
    turn_key: str = Field(pattern=HASH)
    # "" means "not reviewed by me"; there is deliberately no "answer is correct" state.
    state: str = Field(pattern=r"^(|sources_viewed|needs_check)$")


class BranchInput(Input):
    id: str = Field(pattern=UUID)
    index: int = Field(ge=0, le=19)
    turn_key: str = Field(pattern=HASH)
    include_answer: bool
    draft: str = Field(max_length=10000)
    copy_checklist: bool = False


class ReadInput(Input):
    turn_key: str = Field(pattern=HASH)


class QueueEditInput(Input):
    expected_question: str = Field(min_length=1, max_length=10000)
    question: str = Field(min_length=1, max_length=10000)


class SavedSearch(Input):
    id: str = Field(pattern=UUID)
    title: str = Field(min_length=1, max_length=80)
    scope: Literal["catalog", "picker"]
    query: str = Field(max_length=200)
    tab: str = Field(default="", max_length=40)
    kind: Literal["", "laws", "contracts", "addenda", "policies", "other"] = ""
    edition: Literal["", "current", "expired", "unspecified"] = ""
    selected: bool = False

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value):
        if not value.strip():
            raise ValueError("Empty title")
        return value.strip()


class SearchesInput(Input):
    revision: int = Field(ge=0)
    items: list[SavedSearch] = Field(max_length=30)


class RecentInput(Input):
    document_id: str = Field(pattern=HASH)


class ChecklistItem(Input):
    id: str = Field(pattern=UUID)
    title: str = Field(min_length=1, max_length=160)
    comment: str = Field(default="", max_length=500)
    done: bool = False
    document_id: str | None = Field(default=None, pattern=HASH)
    answer_key: str | None = Field(default=None, pattern=HASH)

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value):
        if not value.strip():
            raise ValueError("Empty title")
        return value.strip()


class ChecklistInput(Input):
    revision: int = Field(ge=0)
    items: list[ChecklistItem] = Field(max_length=40)


async def read_input(request, model):
    identity(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 128 * 1024:
            raise HTTPException(413, "Слишком большой запрос.")
    try:
        return model.model_validate_json(body)
    except (ValidationError, ValueError):
        raise HTTPException(422, "Проверьте заполненные поля и длину текста.") from None


def conflict():
    raise HTTPException(409, "Данные изменены на другом устройстве. Обновите их перед сохранением.")


def listed(row):
    return dict(items=json.loads(row["items"]), revision=row["revision"]) if row else dict(items=[], revision=0)


def serialize_items(items):
    if len({item.id for item in items}) != len(items):
        raise HTTPException(422, "Идентификаторы записей должны быть уникальны.")
    return [item.model_dump() for item in items]


@router.get("/searches")
def get_searches(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        return listed(db.execute("SELECT items,revision FROM workspace_searches WHERE owner=?", (owner,)).fetchone())


def save_searches(request, data):
    history, owner = identity(request)
    items = serialize_items(data.items)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = listed(db.execute("SELECT items,revision FROM workspace_searches WHERE owner=?", (owner,)).fetchone())
        if current["revision"] != data.revision:
            conflict()
        revision = data.revision + 1
        db.execute("""INSERT INTO workspace_searches VALUES (?,?,?)
            ON CONFLICT(owner) DO UPDATE SET items=excluded.items,revision=excluded.revision""",
                   (owner, json.dumps(items, ensure_ascii=False), revision))
    return dict(items=items, revision=revision)


@router.put("/searches")
async def update_searches(request: Request):
    return await run_in_threadpool(save_searches, request, await read_input(request, SearchesInput))


@router.get("/recent-documents")
def get_recent_documents(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        return [dict(row, available=row["document_id"] in request.app.state.documents) for row in db.execute(
            """SELECT document_id,title,opened FROM workspace_recent_documents WHERE owner=?
               ORDER BY opened DESC,document_id LIMIT 20""", (owner,))]


def remember_recent_document(request, data):
    history, owner = identity(request)
    document = request.app.state.documents.get(data.document_id)
    if document is None:
        raise HTTPException(404, "Документ недоступен.")
    from psb_policy import display_name
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""INSERT INTO workspace_recent_documents VALUES (?,?,?,?)
            ON CONFLICT(owner,document_id) DO UPDATE SET opened=excluded.opened,title=excluded.title""",
                   (owner, data.document_id, display_name(document.name), time.time()))
        db.execute("""DELETE FROM workspace_recent_documents WHERE owner=? AND document_id IN (
            SELECT document_id FROM workspace_recent_documents WHERE owner=?
            ORDER BY opened DESC,document_id LIMIT -1 OFFSET 20)""", (owner, owner))


@router.put("/recent-documents", status_code=204)
async def update_recent_document(request: Request):
    await run_in_threadpool(remember_recent_document, request, await read_input(request, RecentInput))


@router.delete("/recent-documents", status_code=204)
def clear_recent_documents(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("DELETE FROM workspace_recent_documents WHERE owner=?", (owner,))


def load_checklist(db, chat_id):
    return listed(db.execute("SELECT items,revision FROM workspace_checklists WHERE chat_id=?", (chat_id,)).fetchone())


@router.get("/chats/{chat_id}/checklist")
def get_checklist(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN")
        chat = history.get(db, owner, chat_id)
        record = load_checklist(db, chat_id)
        turns = json.loads(chat["turns"])
        options = []
        for row in db.execute("SELECT turn_index,turn_key FROM answer_annotations WHERE chat_id=? AND saved=1", (chat_id,)):
            index, key = row["turn_index"], row["turn_key"]
            if index < len(turns) and key == turn_key(turns[index]):
                options.append(dict(key=key, index=index, title=turns[index]["question"][:160]))
        return dict(**record, answers=options)


def save_checklist(chat_id, request, data):
    history, owner = identity(request)
    items = serialize_items(data.items)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        chat = history.get(db, owner, chat_id)
        record = load_checklist(db, chat_id)
        if record["revision"] != data.revision:
            conflict()
        previous = {item["id"]: item for item in record["items"]}
        turns = json.loads(chat["turns"])
        saved_keys = {row["turn_key"] for row in db.execute(
            "SELECT turn_index,turn_key FROM answer_annotations WHERE chat_id=? AND saved=1", (chat_id,))
            if row["turn_index"] < len(turns) and row["turn_key"] == turn_key(turns[row["turn_index"]])}
        for item in items:
            old = previous.get(item["id"], {})
            answer, document = item["answer_key"], item["document_id"]
            invalid_answer = answer and answer != old.get("answer_key") and answer not in saved_keys
            invalid_document = document and document != old.get("document_id") and document not in request.app.state.documents
            if invalid_answer or invalid_document:
                raise HTTPException(422, "Выберите доступный документ или сохранённый ответ этого диалога.")
        revision = data.revision + 1
        db.execute("""INSERT INTO workspace_checklists VALUES (?,?,?)
            ON CONFLICT(chat_id) DO UPDATE SET items=excluded.items,revision=excluded.revision""",
                   (chat_id, json.dumps(items, ensure_ascii=False), revision))
    return dict(items=items, revision=revision)


@router.put("/chats/{chat_id}/checklist")
async def update_checklist(chat_id: str, request: Request):
    return await run_in_threadpool(save_checklist, chat_id, request, await read_input(request, ChecklistInput))


@router.get("/chats/{chat_id}")
def get_workspace(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        chat = history.get(db, owner, chat_id)
        row = workspace_row(db, chat_id)
        turns = json.loads(chat["turns"])
        annotations = {item["turn_index"]: dict(item) for item in db.execute(
            "SELECT turn_index,turn_key,saved,note,revision FROM answer_annotations WHERE chat_id=?", (chat_id,))}
        reviews = current_reviews(db, chat_id, turns)
        answers = []
        for index, turn in enumerate(turns):
            key = turn_key(turn)
            item = annotations.get(index)
            answer = (item if item and item["turn_key"] == key else
                      dict(turn_index=index, turn_key=key, saved=False, note="", revision=0))
            answers.append({**answer, "review": reviews.get(index, NO_REVIEW)})
        parent = db.execute("""SELECT c.id,c.title FROM chats c WHERE c.id=? AND c.owner=?
            AND NOT EXISTS(SELECT 1 FROM chat_trash WHERE chat_id=c.id)""", (row["parent_id"], owner)).fetchone()
        return dict(matter=json.loads(row["matter"]), matter_revision=row["matter_revision"],
                    draft=row["draft"], draft_revision=row["draft_revision"], answers=answers,
                    last_question=turns[-1]["question"] if turns else "",
                    last_answer=turns[-1]["answer"]["text"] if turns else "",
                    parent=dict(parent) if parent else None)


@router.get("/drafts/{chat_id}")
def get_draft(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        if chat_id == "new":
            row = db.execute("SELECT draft,revision FROM new_dialogue_drafts WHERE owner=?", (owner,)).fetchone()
            return dict(text=row["draft"], revision=row["revision"]) if row else dict(text="", revision=0)
        history.get(db, owner, chat_id)
        row = db.execute("SELECT draft,draft_revision FROM chat_workspace WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(text=row["draft"], revision=row["draft_revision"]) if row else dict(text="", revision=0)


def save_draft(chat_id, request, data):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if chat_id == "new":
            db.execute("INSERT OR IGNORE INTO new_dialogue_drafts(owner) VALUES (?)", (owner,))
            row = db.execute("SELECT * FROM new_dialogue_drafts WHERE owner=?", (owner,)).fetchone()
            if row["revision"] != data.revision:
                if row["draft"] == data.text:
                    return dict(text=row["draft"], revision=row["revision"])
                conflict()
            db.execute("UPDATE new_dialogue_drafts SET draft=?,revision=revision+1 WHERE owner=?", (data.text, owner))
        else:
            history.get(db, owner, chat_id)
            row = workspace_row(db, chat_id)
            if row["draft_revision"] != data.revision:
                if row["draft"] == data.text:
                    return dict(text=row["draft"], revision=row["draft_revision"])
                conflict()
            db.execute("UPDATE chat_workspace SET draft=?,draft_revision=draft_revision+1 WHERE chat_id=?", (data.text, chat_id))
        return dict(text=data.text, revision=data.revision + 1)


@router.put("/drafts/{chat_id}")
async def update_draft(chat_id: str, request: Request):
    data = await read_input(request, DraftInput)
    return await run_in_threadpool(save_draft, chat_id, request, data)


def save_matter(chat_id, request, data):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        history.get(db, owner, chat_id)
        row = workspace_row(db, chat_id)
        if row["matter_revision"] != data.revision:
            conflict()
        value = data.matter.model_dump()
        db.execute("UPDATE chat_workspace SET matter=?,matter_revision=matter_revision+1 WHERE chat_id=?",
                   (json.dumps(value, ensure_ascii=False), chat_id))
        return dict(matter=value, matter_revision=data.revision + 1)


@router.put("/chats/{chat_id}/matter")
async def update_matter(chat_id: str, request: Request):
    return await run_in_threadpool(save_matter, chat_id, request, await read_input(request, MatterInput))


def save_annotation(chat_id, index, request, data):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        chat = history.get(db, owner, chat_id)
        turns = json.loads(chat["turns"])
        if index < 0 or index >= len(turns):
            raise HTTPException(404, "Ответ не найден.")
        turn = turns[index]
        if turn_key(turn) != data.turn_key:
            conflict()
        if turn["answer"]["status"] in {"technical_error", "cancelled"}:
            raise HTTPException(409, "Дождитесь готового ответа.")
        old = db.execute("SELECT * FROM answer_annotations WHERE chat_id=? AND turn_index=?", (chat_id, index)).fetchone()
        revision = old["revision"] if old and old["turn_key"] == data.turn_key else 0
        if revision != data.revision:
            conflict()
        db.execute("INSERT OR REPLACE INTO answer_annotations VALUES (?,?,?,?,?,?)",
                   (chat_id, index, data.turn_key, data.saved, data.note, revision + 1))
        return dict(turn_index=index, turn_key=data.turn_key, saved=data.saved, note=data.note, revision=revision + 1)


@router.put("/chats/{chat_id}/answers/{index}")
async def update_annotation(chat_id: str, index: int, request: Request):
    return await run_in_threadpool(save_annotation, chat_id, index, request, await read_input(request, AnnotationInput))


NO_REVIEW = dict(state="", updated=None, revision=0)


def current_reviews(db, chat_id, turns):
    """Review marks of the answer versions still present; a replaced answer has no mark."""
    result = {}
    for row in db.execute("SELECT turn_index,turn_key,state,updated,revision FROM answer_reviews WHERE chat_id=?", (chat_id,)):
        index = row["turn_index"]
        if index < len(turns) and turn_key(turns[index]) == row["turn_key"]:
            result[index] = dict(state=row["state"], updated=row["updated"], revision=row["revision"])
    return result


def save_review(chat_id, index, request, data):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        turns = json.loads(history.get(db, owner, chat_id)["turns"])
        if index < 0 or index >= len(turns):
            raise HTTPException(404, "Ответ не найден.")
        turn = turns[index]
        if turn_key(turn) != data.turn_key:
            conflict()
        if turn["answer"]["status"] in {"technical_error", "cancelled"}:
            raise HTTPException(409, "Дождитесь готового ответа.")
        if data.state == "sources_viewed" and not turn["answer"].get("sources"):
            raise HTTPException(422, "У этого ответа нет источников. Выберите другую отметку.")
        old = db.execute("SELECT * FROM answer_reviews WHERE chat_id=? AND turn_index=?", (chat_id, index)).fetchone()
        current = old if old and old["turn_key"] == data.turn_key else None
        revision = current["revision"] if current else 0
        if revision != data.revision:
            # Repeating the same choice after a lost response is safe; a different stale choice is not.
            if current and current["state"] == data.state:
                return dict(turn_index=index, turn_key=data.turn_key, state=current["state"],
                            updated=current["updated"], revision=revision)
            conflict()
        now = time.time()
        db.execute("INSERT OR REPLACE INTO answer_reviews VALUES (?,?,?,?,?,?)",
                   (chat_id, index, data.turn_key, data.state, now, revision + 1))
        return dict(turn_index=index, turn_key=data.turn_key, state=data.state, updated=now, revision=revision + 1)


@router.put("/chats/{chat_id}/answers/{index}/review")
async def update_review(chat_id: str, index: int, request: Request):
    return await run_in_threadpool(save_review, chat_id, index, request, await read_input(request, ReviewInput))


@router.get("/saved")
def saved_answers(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        chats = db.execute("""SELECT c.id,c.title,c.turns FROM chats c WHERE c.owner=?
            AND NOT EXISTS(SELECT 1 FROM chat_trash WHERE chat_id=c.id)
            AND (EXISTS(SELECT 1 FROM answer_annotations a WHERE a.chat_id=c.id AND (a.saved=1 OR a.note<>''))
                 OR EXISTS(SELECT 1 FROM answer_reviews r WHERE r.chat_id=c.id AND r.state<>''))
            ORDER BY c.updated DESC,c.id""", (owner,)).fetchall()
        result = []
        for chat in chats:
            turns = json.loads(chat["turns"])
            annotations = {row["turn_index"]: row for row in db.execute(
                "SELECT turn_index,turn_key,saved,note FROM answer_annotations WHERE chat_id=?", (chat["id"],))}
            reviews = current_reviews(db, chat["id"], turns)
            for index, turn in enumerate(turns):
                annotation = annotations.get(index)
                if annotation is not None and annotation["turn_key"] != turn_key(turn):
                    annotation = None
                saved, note = bool(annotation and annotation["saved"]), annotation["note"] if annotation else ""
                review = reviews.get(index, NO_REVIEW)
                if saved or note or review["state"]:
                    result.append(dict(chat_id=chat["id"], title=chat["title"], turn_index=index,
                                       saved=saved, note=note, review=review, **turn))
        return result


def create_branch(chat_id, request, data):
    history, owner = identity(request)
    payload = json.dumps(data.model_dump(exclude={"copy_checklist"} if not data.copy_checklist else None), sort_keys=True, ensure_ascii=False)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        parent = history.get(db, owner, chat_id)
        existing = db.execute("SELECT * FROM chats WHERE id=?", (data.id,)).fetchone()
        if existing:
            record = db.execute("SELECT * FROM chat_workspace WHERE chat_id=?", (data.id,)).fetchone()
            if existing["owner"] != owner or not record or record["parent_id"] != chat_id or record["branch_request"] != payload:
                conflict()
            history.get(db, owner, data.id)
            return dict(id=data.id)
        turns = json.loads(parent["turns"])
        if data.index >= len(turns):
            raise HTTPException(404, "Вопрос не найден.")
        if turn_key(turns[data.index]) != data.turn_key:
            conflict()
        prefix = turns[:data.index + int(data.include_answer)]
        if len(prefix) >= 20:
            raise HTTPException(413, "В этой ветке уже 20 вопросов. Начните новый диалог.")
        if active_count(db, owner) >= 100:
            raise HTTPException(429, "Сохранено 100 диалогов. Освободите место для ветки.")
        title = ("Ветка · " + parent["title"])[:80]
        db.execute("INSERT INTO chats(id,owner,title,updated,turns,title_manual) VALUES (?,?,?,?,?,1)",
                   (data.id, owner, title, time.time(), json.dumps(prefix, ensure_ascii=False)))
        matter = db.execute("SELECT matter FROM chat_workspace WHERE chat_id=?", (chat_id,)).fetchone()
        db.execute("""INSERT INTO chat_workspace(chat_id,matter,draft,draft_revision,parent_id,parent_turn,branch_request)
            VALUES (?,?,?,1,?,?,?)""", (data.id, matter["matter"] if matter else "{}", data.draft, chat_id, data.index, payload))
        if data.copy_checklist:
            items = [{**item, "done": False, "answer_key": None} for item in load_checklist(db, chat_id)["items"]]
            if items:
                db.execute("INSERT INTO workspace_checklists VALUES (?,?,1)",
                           (data.id, json.dumps(items, ensure_ascii=False)))
        folder = db.execute("SELECT folder_id FROM chat_folder_items WHERE chat_id=?", (chat_id,)).fetchone()
        if folder:
            db.execute("INSERT INTO chat_folder_items VALUES (?,?)", (data.id, folder["folder_id"]))
        return dict(id=data.id)


@router.post("/chats/{chat_id}/branch", status_code=201)
async def branch(chat_id: str, request: Request):
    return await run_in_threadpool(create_branch, chat_id, request, await read_input(request, BranchInput))


@router.get("/activity")
def activity(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        result = []
        for row in db.execute("""SELECT c.id,c.turns,w.read_key FROM chats c LEFT JOIN chat_workspace w ON w.chat_id=c.id
            WHERE c.owner=? AND NOT EXISTS(SELECT 1 FROM chat_trash WHERE chat_id=c.id)""", (owner,)):
            turns = json.loads(row["turns"])
            ready = turns and turns[-1]["answer"]["status"] not in {"technical_error", "cancelled"}
            result.append(dict(id=row["id"], unread=bool(ready and turn_key(turns[-1]) != row["read_key"])))
        return result


def mark_read(chat_id, request, data):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        turns = json.loads(history.get(db, owner, chat_id)["turns"])
        if not turns or turn_key(turns[-1]) != data.turn_key:
            conflict()
        workspace_row(db, chat_id)
        db.execute("UPDATE chat_workspace SET read_key=? WHERE chat_id=?", (data.turn_key, chat_id))
    return dict(read=True)


@router.put("/chats/{chat_id}/read")
async def read_answer(chat_id: str, request: Request):
    return await run_in_threadpool(mark_read, chat_id, request, await read_input(request, ReadInput))


def edit_queued(chat_id, job_id, request, data):
    history, owner = identity(request)
    question = data.question.strip()
    if not question:
        raise HTTPException(422, "Введите вопрос.")
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        history.get(db, owner, chat_id)
        row = db.execute("SELECT * FROM chat_jobs WHERE id=? AND chat_id=?", (job_id, chat_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Вопрос не найден.")
        if row["status"] != "queued":
            raise HTTPException(409, "Вопрос уже обрабатывается. Можно изменить только ожидающий вопрос.")
        if row["question"] != data.expected_question:
            if row["question"] == question:
                return dict(id=job_id, question=question)
            conflict()
        db.execute("UPDATE chat_jobs SET question=? WHERE id=?", (question, job_id))
    return dict(id=job_id, question=question)


@router.put("/chats/{chat_id}/queued/{job_id}")
async def update_queued(chat_id: str, job_id: str, request: Request):
    return await run_in_threadpool(edit_queued, chat_id, job_id, request, await read_input(request, QueueEditInput))
