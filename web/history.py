"""Persistent chat history, isolated by the authenticated reverse-proxy identity."""
from contextlib import contextmanager
import json
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/chats")


class History:
    def __init__(self, path, token):
        self.path, self.token = path, token
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                updated REAL NOT NULL, turns TEXT NOT NULL DEFAULT '[]', busy_until REAL NOT NULL DEFAULT 0)""")
            db.execute("CREATE INDEX IF NOT EXISTS chats_owner ON chats(owner, updated)")
            db.execute("""CREATE TABLE IF NOT EXISTS document_tabs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
                document_ids TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)""")
            db.execute("CREATE INDEX IF NOT EXISTS document_tabs_owner ON document_tabs(owner)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, db, owner, chat_id):
        row = db.execute("SELECT * FROM chats WHERE id=? AND owner=?", (chat_id, owner)).fetchone()
        if row is None:
            raise HTTPException(404, "Диалог не найден.")
        return row

    def begin(self, owner, chat_id, question=""):
        with self.connect() as db:
            # Serialize the claim across threads/processes before reading the transcript.
            db.execute("BEGIN IMMEDIATE")
            row = self.get(db, owner, chat_id)
            if row["busy_until"] > time.time():
                raise HTTPException(409, "В этом диалоге ещё готовится ответ. Откройте его чуть позже.")
            turns = json.loads(row["turns"])
            retry = turns and turns[-1]["answer"]["status"] == "technical_error" and turns[-1]["question"] == question
            if len(turns) >= 20 and not retry:
                raise HTTPException(413, "Диалог слишком длинный. Начните новый.")
            lease = time.time() + 240
            db.execute("UPDATE chats SET busy_until=? WHERE id=? AND owner=?", (lease, chat_id, owner))
        return turns, lease

    def finish(self, owner, chat_id, lease, turns=None):
        with self.connect() as db:
            if turns is None:
                db.execute("UPDATE chats SET busy_until=0 WHERE id=? AND owner=? AND busy_until=?",
                           (chat_id, owner, lease))
            else:
                db.execute("""UPDATE chats SET turns=?, title=?, updated=?, busy_until=0
                              WHERE id=? AND owner=? AND busy_until=?""",
                           (json.dumps(turns, ensure_ascii=False), turns[0]["question"][:80], time.time(),
                            chat_id, owner, lease))


def identity(request):
    history = request.app.state.history
    if history is None:
        raise HTTPException(503, "История на сервере не настроена.")
    token = request.headers.get("x-chat-token", "")
    owner = request.headers.get("x-chat-user", "")
    if not secrets.compare_digest(token.encode(), history.token.encode()) or not re.fullmatch(r"[\w.@-]{1,128}", owner):
        raise HTTPException(401, "Для истории диалогов войдите через защищённый адрес сайта.")
    return history, owner


@router.get("")
def list_chats(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT id, title, updated FROM chats WHERE owner=? ORDER BY updated DESC, id", (owner,))]


@router.post("", status_code=201)
def create_chat(request: Request):
    history, owner = identity(request)
    # Requiring a non-simple content type prevents creation via cross-site HTML forms.
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")
    chat = dict(id=str(uuid4()), title="Новый диалог", updated=time.time())
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM chats WHERE owner=?", (owner,)).fetchone()[0] >= 100:
            raise HTTPException(429, "Сохранено 100 диалогов. Удалите ненужный, чтобы создать новый.")
        db.execute("INSERT INTO chats(id, owner, title, updated) VALUES (?, ?, ?, ?)",
                   (chat["id"], owner, chat["title"], chat["updated"]))
    return {**chat, "turns": []}


@router.get("/{chat_id}")
def get_chat(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        row = history.get(db, owner, chat_id)
        return dict(id=row["id"], title=row["title"], updated=row["updated"],
                    turns=json.loads(row["turns"]), busy=row["busy_until"] > time.time())


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = history.get(db, owner, chat_id)
        if row["busy_until"] > time.time():
            raise HTTPException(409, "Дождитесь завершения ответа перед удалением диалога.")
        db.execute("DELETE FROM chats WHERE id=? AND owner=?", (chat_id, owner))
