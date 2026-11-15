"""Private chat folders; deleting a folder never deletes its conversations."""
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from web.history import identity

router = APIRouter(prefix="/api")


class FolderInput(BaseModel):
    title: str = Field(min_length=1, max_length=60)


class MoveInput(BaseModel):
    folder_id: str | None = Field(max_length=36)


async def read_input(request, schema):
    identity(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(413, "Слишком большой запрос.")
    try:
        return schema.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Проверьте название папки или выбранную папку.") from None


def get_folder(db, owner, folder_id):
    row = db.execute("SELECT id, title FROM chat_folders WHERE id=? AND owner=?", (folder_id, owner)).fetchone()
    if row is None:
        raise HTTPException(404, "Папка не найдена. Обновите список.")
    return row


@router.get("/chat-folders")
def list_folders(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT id, title FROM chat_folders WHERE owner=? ORDER BY rowid", (owner,))]


def save_folder(request, title, folder_id=None):
    history, owner = identity(request)
    title = title.strip()
    if not title or any(ord(c) < 32 for c in title):
        raise HTTPException(422, "Укажите название папки без управляющих символов.")
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if folder_id:
            get_folder(db, owner, folder_id)
        rows = db.execute("SELECT id, title FROM chat_folders WHERE owner=?", (owner,)).fetchall()
        if any(row["id"] != folder_id and row["title"].casefold() == title.casefold() for row in rows):
            raise HTTPException(409, "Папка с таким названием уже есть.")
        if folder_id:
            db.execute("UPDATE chat_folders SET title=? WHERE id=? AND owner=?", (title, folder_id, owner))
        else:
            if len(rows) >= 30:
                raise HTTPException(429, "Достигнут лимит: 30 папок. Удалите ненужную.")
            folder_id = str(uuid4())
            db.execute("INSERT INTO chat_folders(id, owner, title) VALUES (?, ?, ?)", (folder_id, owner, title))
    return dict(id=folder_id, title=title)


@router.post("/chat-folders", status_code=201)
async def create_folder(request: Request):
    data = await read_input(request, FolderInput)
    return await run_in_threadpool(save_folder, request, data.title)


@router.put("/chat-folders/{folder_id}")
async def rename_folder(folder_id: str, request: Request):
    data = await read_input(request, FolderInput)
    return await run_in_threadpool(save_folder, request, data.title, folder_id)


@router.delete("/chat-folders/{folder_id}", status_code=204)
def delete_folder(folder_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        get_folder(db, owner, folder_id)
        # Foreign-key cascade removes membership only, never a chat or its turns.
        db.execute("DELETE FROM chat_folders WHERE id=? AND owner=?", (folder_id, owner))


def move_chat(request, chat_id, folder_id):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        history.get(db, owner, chat_id)
        if folder_id is not None:
            get_folder(db, owner, folder_id)
        db.execute("DELETE FROM chat_folder_items WHERE chat_id=?", (chat_id,))
        if folder_id is not None:
            db.execute("INSERT INTO chat_folder_items(chat_id, folder_id) VALUES (?, ?)", (chat_id, folder_id))
    return dict(id=chat_id, folder_id=folder_id)


@router.put("/chats/{chat_id}/folder")
async def set_chat_folder(chat_id: str, request: Request):
    data = await read_input(request, MoveInput)
    return await run_in_threadpool(move_chat, request, chat_id, data.folder_id)
