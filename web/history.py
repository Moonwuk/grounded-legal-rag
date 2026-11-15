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
            db.execute("""CREATE TABLE IF NOT EXISTS chat_folders (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS chat_folders_owner ON chat_folders(owner)")
            db.execute("""CREATE TABLE IF NOT EXISTS chat_folder_items (
                chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
                folder_id TEXT NOT NULL REFERENCES chat_folders(id) ON DELETE CASCADE)""")
            db.execute("CREATE INDEX IF NOT EXISTS chat_folder_items_folder ON chat_folder_items(folder_id)")
            db.execute("""CREATE TABLE IF NOT EXISTS chat_trash (
                chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
                deleted REAL NOT NULL)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, db, owner, chat_id):
        row = db.execute("""SELECT * FROM chats WHERE id=? AND owner=?
                            AND NOT EXISTS (SELECT 1 FROM chat_trash WHERE chat_id=chats.id)""",
                         (chat_id, owner)).fetchone()
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
                db.execute("""UPDATE chats SET busy_until=0 WHERE id=? AND owner=? AND busy_until=?
                              AND NOT EXISTS (SELECT 1 FROM chat_trash WHERE chat_id=chats.id)""",
                           (chat_id, owner, lease))
            else:
                db.execute("""UPDATE chats SET turns=?, title=?, updated=?, busy_until=0
                              WHERE id=? AND owner=? AND busy_until=?
                              AND NOT EXISTS (SELECT 1 FROM chat_trash WHERE chat_id=chats.id)""",
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
def list_chats(request: Request, trash: bool = False):
    history, owner = identity(request)
    with history.connect() as db:
        return [dict(row) for row in db.execute(
            """SELECT c.id, c.title, c.updated, i.folder_id, t.deleted AS deleted_at FROM chats c
               LEFT JOIN chat_folder_items i ON i.chat_id=c.id
               LEFT JOIN chat_trash t ON t.chat_id=c.id
               WHERE c.owner=? AND (t.chat_id IS NOT NULL)=?
               ORDER BY COALESCE(t.deleted, c.updated) DESC, c.id""", (owner, trash))]


@router.post("", status_code=201)
def create_chat(request: Request, folder_id: str | None = None):
    history, owner = identity(request)
    # Requiring a non-simple content type prevents creation via cross-site HTML forms.
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")
    chat = dict(id=str(uuid4()), title="Новый диалог", updated=time.time())
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if folder_id is not None and not db.execute(
                "SELECT id FROM chat_folders WHERE id=? AND owner=?", (folder_id, owner)).fetchone():
            raise HTTPException(404, "Папка не найдена. Обновите список.")
        if active_count(db, owner) >= 100:
            raise HTTPException(429, "Сохранено 100 диалогов. Переместите ненужный в корзину, чтобы создать новый.")
        db.execute("INSERT INTO chats(id, owner, title, updated) VALUES (?, ?, ?, ?)",
                   (chat["id"], owner, chat["title"], chat["updated"]))
        if folder_id is not None:
            db.execute("INSERT INTO chat_folder_items(chat_id, folder_id) VALUES (?, ?)", (chat["id"], folder_id))
    return {**chat, "turns": [], "folder_id": folder_id}


@router.get("/{chat_id}")
def get_chat(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        row = history.get(db, owner, chat_id)
        membership = db.execute("SELECT folder_id FROM chat_folder_items WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(id=row["id"], title=row["title"], updated=row["updated"],
                    turns=json.loads(row["turns"]), busy=row["busy_until"] > time.time(),
                    folder_id=membership["folder_id"] if membership else None)


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = history.get(db, owner, chat_id)
        if row["busy_until"] > time.time():
            raise HTTPException(409, "Дождитесь завершения ответа перед удалением диалога.")
        if db.execute("""SELECT count(*) FROM chat_trash t JOIN chats c ON c.id=t.chat_id
                         WHERE c.owner=?""", (owner,)).fetchone()[0] >= 100:
            raise HTTPException(429, "В корзине 100 чатов. Удалите из неё ненужные навсегда, чтобы освободить место.")
        db.execute("INSERT INTO chat_trash(chat_id, deleted) VALUES (?, ?)", (chat_id, time.time()))


def active_count(db, owner):
    return db.execute("""SELECT count(*) FROM chats c WHERE c.owner=?
                         AND NOT EXISTS (SELECT 1 FROM chat_trash WHERE chat_id=c.id)""", (owner,)).fetchone()[0]


def trashed_chat(db, owner, chat_id):
    row = db.execute("SELECT * FROM chats WHERE id=? AND owner=?", (chat_id, owner)).fetchone()
    if row is None:
        raise HTTPException(404, "Диалог не найден.")
    if not db.execute("SELECT 1 FROM chat_trash WHERE chat_id=?", (chat_id,)).fetchone():
        raise HTTPException(409, "Сначала переместите диалог в корзину.")
    if row["busy_until"] > time.time():
        raise HTTPException(409, "Дождитесь завершения ответа.")


@router.post("/{chat_id}/restore", status_code=204)
def restore_chat(chat_id: str, request: Request):
    history, owner = identity(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        trashed_chat(db, owner, chat_id)
        if active_count(db, owner) >= 100:
            raise HTTPException(429, "Уже сохранено 100 диалогов. Освободите место перед восстановлением.")
        db.execute("DELETE FROM chat_trash WHERE chat_id=?", (chat_id,))


@router.delete("/{chat_id}/permanent", status_code=204)
def permanently_delete_chat(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        trashed_chat(db, owner, chat_id)
        db.execute("DELETE FROM chats WHERE id=? AND owner=?", (chat_id, owner))
