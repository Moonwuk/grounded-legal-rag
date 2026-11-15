"""Private web workspace. None of these fields are part of the RAG context."""
from datetime import date
from hashlib import sha256
import json
import time

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
    db.execute("""CREATE TABLE IF NOT EXISTS answer_annotations (
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        turn_index INTEGER NOT NULL, turn_key TEXT NOT NULL,
        saved INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL,
        PRIMARY KEY(chat_id, turn_index))""")


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


class BranchInput(Input):
    id: str = Field(pattern=UUID)
    index: int = Field(ge=0, le=19)
    turn_key: str = Field(pattern=HASH)
    include_answer: bool
    draft: str = Field(max_length=10000)


class ReadInput(Input):
    turn_key: str = Field(pattern=HASH)


class QueueEditInput(Input):
    expected_question: str = Field(min_length=1, max_length=10000)
    question: str = Field(min_length=1, max_length=10000)


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
        answers = []
        for index, turn in enumerate(turns):
            key = turn_key(turn)
            item = annotations.get(index)
            answers.append(item if item and item["turn_key"] == key else
                           dict(turn_index=index, turn_key=key, saved=False, note="", revision=0))
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


@router.get("/saved")
def saved_answers(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        rows = db.execute("""SELECT a.*,c.title,c.turns FROM answer_annotations a JOIN chats c ON c.id=a.chat_id
            WHERE c.owner=? AND (a.saved=1 OR a.note<>'')
            AND NOT EXISTS(SELECT 1 FROM chat_trash WHERE chat_id=c.id) ORDER BY c.updated DESC,a.turn_index""", (owner,))
        result = []
        for row in rows:
            turns = json.loads(row["turns"])
            index = row["turn_index"]
            if index >= len(turns) or turn_key(turns[index]) != row["turn_key"]:
                continue
            result.append(dict(chat_id=row["chat_id"], title=row["title"], turn_index=index,
                               saved=bool(row["saved"]), note=row["note"], **turns[index]))
        return result


def create_branch(chat_id, request, data):
    history, owner = identity(request)
    payload = json.dumps(data.model_dump(), sort_keys=True, ensure_ascii=False)
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
