"""Private, persisted collections of existing corpus documents."""
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from web.history import identity

router = APIRouter(prefix="/api/document-tabs")


class TabInput(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    document_ids: list[str] = Field(max_length=500)
    revision: int = Field(default=0, ge=0)


def serialize(row):
    return dict(id=row["id"], title=row["title"],
                document_ids=json.loads(row["document_ids"]), revision=row["revision"])


@router.get("")
def list_tabs(request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        return [serialize(row) for row in db.execute(
            "SELECT * FROM document_tabs WHERE owner=? ORDER BY rowid", (owner,))]


async def read_input(request):
    identity(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 64 * 1024:
            raise HTTPException(413, "Слишком большой список документов.")
    try:
        tab = TabInput.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Укажите название до 60 символов и список документов.") from None
    tab.title = tab.title.strip()
    if not tab.title or any(ord(c) < 32 for c in tab.title):
        raise HTTPException(422, "Укажите название вкладки без управляющих символов.")
    tab.document_ids = list(dict.fromkeys(tab.document_ids))
    if any(doc_id not in request.app.state.documents for doc_id in tab.document_ids):
        raise HTTPException(422, "В списке есть документ, которого больше нет в базе. Обновите страницу.")
    return tab


def save_tab(request, tab, tab_id=None):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if tab_id:
            row = db.execute("SELECT revision FROM document_tabs WHERE id=? AND owner=?", (tab_id, owner)).fetchone()
            if row is None:
                raise HTTPException(404, "Вкладка не найдена.")
            if row["revision"] != tab.revision:
                raise HTTPException(409, "Вкладка изменена на другом устройстве. Закройте окно и обновите вкладки.")
            revision = tab.revision + 1
            db.execute("UPDATE document_tabs SET title=?, document_ids=?, revision=? WHERE id=? AND owner=?",
                       (tab.title, json.dumps(tab.document_ids), revision, tab_id, owner))
        else:
            if db.execute("SELECT count(*) FROM document_tabs WHERE owner=?", (owner,)).fetchone()[0] >= 30:
                raise HTTPException(429, "Достигнут лимит: 30 своих вкладок. Удалите ненужную.")
            tab_id, revision = str(uuid4()), 1
            db.execute("INSERT INTO document_tabs(id, owner, title, document_ids) VALUES (?, ?, ?, ?)",
                       (tab_id, owner, tab.title, json.dumps(tab.document_ids)))
    return dict(id=tab_id, title=tab.title, document_ids=tab.document_ids, revision=revision)


@router.post("", status_code=201)
async def create_tab(request: Request):
    tab = await read_input(request)
    return await run_in_threadpool(save_tab, request, tab)


@router.put("/{tab_id}")
async def update_tab(tab_id: str, request: Request):
    tab = await read_input(request)
    return await run_in_threadpool(save_tab, request, tab, tab_id)


@router.delete("/{tab_id}", status_code=204)
def delete_tab(tab_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        result = db.execute("DELETE FROM document_tabs WHERE id=? AND owner=?", (tab_id, owner))
        if not result.rowcount:
            raise HTTPException(404, "Вкладка не найдена.")
