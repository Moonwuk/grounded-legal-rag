"""Saved brief compositions. A brief references answer versions; it never copies, shortens or rewrites them."""
import json
import re
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from web.history import identity
from web.workspace import HASH, UUID, Input, conflict, read_input, turn_key

router = APIRouter(prefix="/api/workspace")
LIMIT = 20
EXCLUDED = {"technical_error", "cancelled"}
MATTER = r"^(contract|counterparty|event_date|amount|situation)$"


def initialize(db):
    # Owned through the dialogue: trash hides a brief with its dialogue, permanent deletion removes it.
    db.execute("""CREATE TABLE IF NOT EXISTS answer_briefs (
        id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        title TEXT NOT NULL, intro TEXT NOT NULL DEFAULT '', sections TEXT NOT NULL,
        matter_fields TEXT NOT NULL DEFAULT '[]', include_reviews INTEGER NOT NULL DEFAULT 0,
        created REAL NOT NULL, updated REAL NOT NULL, revision INTEGER NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS answer_briefs_chat ON answer_briefs(chat_id)")


class Section(Input):
    turn_index: int = Field(ge=0, le=19)
    turn_key: str = Field(pattern=HASH)
    comment: str = Field(default="", max_length=2000)


class BriefInput(Input):
    title: str = Field(min_length=1, max_length=120)
    intro: str = Field(default="", max_length=4000)
    sections: list[Section] = Field(min_length=1, max_length=20)
    matter_fields: list[str] = Field(default_factory=list, max_length=5)
    include_reviews: bool = False


class BriefCreate(BriefInput):
    id: str = Field(pattern=UUID)


class BriefUpdate(BriefInput):
    revision: int = Field(ge=0)


def available(turns, section):
    index = section["turn_index"]
    return (index < len(turns) and turn_key(turns[index]) == section["turn_key"]
            and turns[index]["answer"]["status"] not in EXCLUDED)


def normalized(data, turns):
    title = data.title.strip()
    if not title:
        raise HTTPException(422, "Укажите заголовок справки.")
    sections = [dict(turn_index=item.turn_index, turn_key=item.turn_key, comment=item.comment.strip())
                for item in data.sections]
    indexes = [item["turn_index"] for item in sections]
    if len(set(indexes)) != len(indexes):
        raise HTTPException(422, "Каждый ответ можно включить в справку только один раз.")
    if not all(available(turns, item) for item in sections):
        # The stored reference must name the exact answer version the user selected.
        raise HTTPException(409, "Ответ изменился или недоступен. Обновите состав справки.")
    if any(not re.fullmatch(MATTER, key) for key in data.matter_fields):
        raise HTTPException(422, "Выберите сведения карточки дела из списка.")
    return dict(title=title, intro=data.intro.strip(), sections=sections,
                matter_fields=list(dict.fromkeys(data.matter_fields)), include_reviews=data.include_reviews)


def serialize(row, turns):
    sections = [dict(item, available=available(turns, item)) for item in json.loads(row["sections"])]
    return dict(id=row["id"], title=row["title"], intro=row["intro"], sections=sections,
                matter_fields=json.loads(row["matter_fields"]), include_reviews=bool(row["include_reviews"]),
                created=row["created"], updated=row["updated"], revision=row["revision"])


def same(row, values):
    return (row["title"], row["intro"], json.loads(row["sections"]), json.loads(row["matter_fields"]),
            bool(row["include_reviews"])) == (values["title"], values["intro"], values["sections"],
                                              values["matter_fields"], values["include_reviews"])


def stored(values):
    return (values["title"], values["intro"], json.dumps(values["sections"], ensure_ascii=False),
            json.dumps(values["matter_fields"]), int(values["include_reviews"]))


@router.get("/chats/{chat_id}/briefs")
def list_briefs(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN")
        turns = json.loads(history.get(db, owner, chat_id)["turns"])
        rows = db.execute("SELECT * FROM answer_briefs WHERE chat_id=? ORDER BY updated DESC,id", (chat_id,))
        return [serialize(row, turns) for row in rows]


def create_brief(chat_id, request, data):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        turns = json.loads(history.get(db, owner, chat_id)["turns"])
        values = normalized(data, turns)
        existing = db.execute("SELECT * FROM answer_briefs WHERE id=?", (data.id,)).fetchone()
        if existing:
            if existing["chat_id"] == chat_id and same(existing, values):
                return serialize(existing, turns)
            raise HTTPException(409, "Идентификатор справки уже использован. Сохраните справку ещё раз.")
        if db.execute("SELECT count(*) FROM answer_briefs WHERE chat_id=?", (chat_id,)).fetchone()[0] >= LIMIT:
            raise HTTPException(429, "В диалоге сохранено %d справок. Удалите ненужную." % LIMIT)
        now = time.time()
        db.execute("INSERT INTO answer_briefs VALUES (?,?,?,?,?,?,?,?,?,1)",
                   (data.id, chat_id, *stored(values), now, now))
        return serialize(db.execute("SELECT * FROM answer_briefs WHERE id=?", (data.id,)).fetchone(), turns)


@router.post("/chats/{chat_id}/briefs", status_code=201)
async def create(chat_id: str, request: Request):
    return await run_in_threadpool(create_brief, chat_id, request, await read_input(request, BriefCreate))


def update_brief(chat_id, brief_id, request, data):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        turns = json.loads(history.get(db, owner, chat_id)["turns"])
        row = db.execute("SELECT * FROM answer_briefs WHERE id=? AND chat_id=?", (brief_id, chat_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Справка не найдена. Обновите список.")
        values = normalized(data, turns)
        if row["revision"] != data.revision:
            if same(row, values):
                return serialize(row, turns)
            conflict()
        db.execute("""UPDATE answer_briefs SET title=?,intro=?,sections=?,matter_fields=?,include_reviews=?,
            updated=?,revision=revision+1 WHERE id=? AND chat_id=?""", (*stored(values), time.time(), brief_id, chat_id))
        return serialize(db.execute("SELECT * FROM answer_briefs WHERE id=?", (brief_id,)).fetchone(), turns)


@router.put("/chats/{chat_id}/briefs/{brief_id}")
async def update(chat_id: str, brief_id: str, request: Request):
    return await run_in_threadpool(update_brief, chat_id, brief_id, request, await read_input(request, BriefUpdate))


@router.delete("/chats/{chat_id}/briefs/{brief_id}", status_code=204)
def delete(chat_id: str, brief_id: str, request: Request, revision: int = Query(ge=0)):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        history.get(db, owner, chat_id)
        row = db.execute("SELECT revision FROM answer_briefs WHERE id=? AND chat_id=?", (brief_id, chat_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Справка не найдена. Обновите список.")
        if row["revision"] != revision:
            conflict()
        db.execute("DELETE FROM answer_briefs WHERE id=? AND chat_id=?", (brief_id, chat_id))
