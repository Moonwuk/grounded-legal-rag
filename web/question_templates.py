"""Question templates. Filling a template only edits the visible draft; nothing is sent to the model."""
import json
import re
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from web.history import identity
from web.workspace import UUID, Input, conflict, read_input

router = APIRouter(prefix="/api/question-templates")
LIMIT = 50

# Application-owned placeholders. Keys match the matter card, so the browser can fill them
# from the card on an explicit user action. "details" has no card counterpart.
FIELDS = [
    dict(key="contract", token="договор", label="Договор", max_length=300, kind="text"),
    dict(key="counterparty", token="контрагент", label="Контрагент", max_length=300, kind="text"),
    dict(key="event_date", token="дата", label="Дата события", max_length=10, kind="date"),
    dict(key="amount", token="сумма", label="Сумма", max_length=100, kind="text"),
    dict(key="details", token="уточнение", label="Уточнение задачи", max_length=1000, kind="text"),
]
TOKENS = {field["token"]: field["key"] for field in FIELDS}
PLACEHOLDER = re.compile(r"\{([^{}\n]{0,40})\}")
KEYS = r"^(contract|counterparty|event_date|amount|details)$"

# Team-prepared starting points. They ask for grounds and gaps; none contains a legal conclusion.
# An optional field sits on its own line: the browser drops the line while that field is empty.
BUILTIN = [
    dict(id="builtin-approval", title="Согласование договора",
         description="Порядок одобрения сделки на дату события и сведения, которых не хватает.",
         text="Какой порядок согласования договора {договор} с {контрагент} на сумму {сумма} действовал на {дата}? "
              "Укажите основания из базы и сведения, которых не хватает для ответа.\nУточнение: {уточнение}",
         required=["contract", "counterparty", "event_date", "amount"]),
    dict(id="builtin-obligations", title="Сроки и обязательства",
         description="Обязанности сторон, сроки исполнения, условия и исключения по договору.",
         text="Какие обязательства сторон и сроки их исполнения установлены договором {договор}? "
              "Укажите условия, исключения и основания из базы.\nКонтрагент: {контрагент}\nУточнение: {уточнение}",
         required=["contract"]),
    dict(id="builtin-edition", title="Редакция на дату",
         description="Какая редакция договора и дополнительных соглашений применима к дате события.",
         text="Какая редакция договора {договор} и его дополнительных соглашений применялась на {дата}? "
              "Если нужной редакции нет в базе, сообщите об этом. Укажите основания из базы.\nУточнение: {уточнение}",
         required=["contract", "event_date"]),
    dict(id="builtin-grounds", title="Основания вывода",
         description="Какие положения базы подтверждают вывод и что нужно учесть.",
         text="Какие положения базы относятся к вопросу: {уточнение}? Приведите цитаты, условия и исключения; "
              "если оснований недостаточно, укажите, каких сведений не хватает.\nДоговор: {договор}",
         required=["details"]),
]


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS question_templates (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        text TEXT NOT NULL, required TEXT NOT NULL DEFAULT '[]',
        created REAL NOT NULL, updated REAL NOT NULL, revision INTEGER NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS question_templates_owner ON question_templates(owner)")


def placeholders(text):
    """Field keys in order of first use. Unknown fields and stray braces are rejected, not guessed."""
    keys = []
    for match in PLACEHOLDER.finditer(text):
        key = TOKENS.get(match.group(1))
        if key is None:
            raise HTTPException(422, "Неизвестное поле {%s}. Доступны: %s." % (
                match.group(1), ", ".join("{%s}" % token for token in TOKENS)))
        if key not in keys:
            keys.append(key)
    rest = PLACEHOLDER.sub("", text)
    if "{" in rest or "}" in rest:
        raise HTTPException(422, "Фигурные скобки используются только для полей: %s." % ", ".join(
            "{%s}" % token for token in TOKENS))
    return keys


class TemplateInput(Input):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    required: list[str] = Field(default_factory=list, max_length=len(FIELDS))


class TemplateCreate(TemplateInput):
    id: str = Field(pattern=UUID)


class TemplateUpdate(TemplateInput):
    revision: int = Field(ge=0)


def normalized(data):
    title, description = data.title.strip(), data.description.strip()
    text = data.text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not title:
        raise HTTPException(422, "Укажите название шаблона.")
    if not text:
        raise HTTPException(422, "Введите текст шаблона.")
    fields = placeholders(text)
    if any(not re.fullmatch(KEYS, key) or key not in fields for key in data.required):
        raise HTTPException(422, "Обязательным можно отметить только поле, которое есть в тексте шаблона.")
    return dict(title=title, description=description, text=text,
                required=[key for key in fields if key in data.required])


def serialize(row):
    return dict(id=row["id"], title=row["title"], description=row["description"], text=row["text"],
                required=json.loads(row["required"]), fields=placeholders(row["text"]),
                created=row["created"], updated=row["updated"], revision=row["revision"])


def same(row, values):
    return all(row[name] == values[name] for name in ("title", "description", "text")) and \
        json.loads(row["required"]) == values["required"]


@router.get("")
def list_templates(request: Request):
    builtin = [dict(item, fields=placeholders(item["text"])) for item in BUILTIN]
    if request.app.state.history is None:
        # Without server history the ready-made templates still work; own ones need a login.
        return dict(fields=FIELDS, builtin=builtin, own=None)
    history, owner = identity(request)
    with history.connect() as db:
        rows = db.execute("SELECT * FROM question_templates WHERE owner=?", (owner,)).fetchall()
    own = sorted((serialize(row) for row in rows), key=lambda item: (item["title"].casefold(), item["id"]))
    return dict(fields=FIELDS, builtin=builtin, own=own)


def create_template(request, data):
    history, owner = identity(request)
    values = normalized(data)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM question_templates WHERE id=?", (data.id,)).fetchone()
        if existing:
            # A retry after a lost response returns the stored template instead of a duplicate.
            if existing["owner"] == owner and same(existing, values):
                return serialize(existing)
            raise HTTPException(409, "Идентификатор шаблона уже использован. Сохраните шаблон ещё раз.")
        if db.execute("SELECT count(*) FROM question_templates WHERE owner=?", (owner,)).fetchone()[0] >= LIMIT:
            raise HTTPException(429, "Сохранено %d шаблонов. Удалите ненужный." % LIMIT)
        now = time.time()
        db.execute("INSERT INTO question_templates VALUES (?,?,?,?,?,?,?,?,1)",
                   (data.id, owner, values["title"], values["description"], values["text"],
                    json.dumps(values["required"]), now, now))
        return serialize(db.execute("SELECT * FROM question_templates WHERE id=?", (data.id,)).fetchone())


@router.post("", status_code=201)
async def create(request: Request):
    return await run_in_threadpool(create_template, request, await read_input(request, TemplateCreate))


def update_template(template_id, request, data):
    history, owner = identity(request)
    values = normalized(data)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM question_templates WHERE id=? AND owner=?", (template_id, owner)).fetchone()
        if row is None:
            raise HTTPException(404, "Шаблон не найден. Обновите список.")
        if row["revision"] != data.revision:
            if same(row, values):
                return serialize(row)
            conflict()
        db.execute("""UPDATE question_templates SET title=?,description=?,text=?,required=?,updated=?,revision=revision+1
            WHERE id=? AND owner=?""", (values["title"], values["description"], values["text"],
                                         json.dumps(values["required"]), time.time(), template_id, owner))
        return serialize(db.execute("SELECT * FROM question_templates WHERE id=?", (template_id,)).fetchone())


@router.put("/{template_id}")
async def update(template_id: str, request: Request):
    return await run_in_threadpool(update_template, template_id, request, await read_input(request, TemplateUpdate))


@router.delete("/{template_id}", status_code=204)
def delete(template_id: str, request: Request, revision: int = Query(ge=0)):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT revision FROM question_templates WHERE id=? AND owner=?", (template_id, owner)).fetchone()
        if row is None:
            raise HTTPException(404, "Шаблон не найден. Обновите список.")
        # Deleting a version edited on another device would silently discard that edit.
        if row["revision"] != revision:
            conflict()
        db.execute("DELETE FROM question_templates WHERE id=? AND owner=?", (template_id, owner))
