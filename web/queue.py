"""Durable per-dialogue FIFO, cancellation, and bounded background workers."""
import json
from threading import Event, Thread
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from web.history import identity
from web.generation import run_generation

router = APIRouter(prefix="/api/chats")
PENDING = ("queued", "running", "cancelling")
EXCLUDED_CONTEXT = {"technical_error", "cancelled"}


class JobInput(BaseModel):
    id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    question: str = Field(min_length=1, max_length=10000)


def json_only(request):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Ожидается JSON.")


def enqueue(request, chat_id, data):
    history, owner = identity(request)
    question = data.question.strip()
    if not question:
        raise HTTPException(422, "Введите вопрос.")
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        chat = history.get(db, owner, chat_id)
        existing = db.execute("SELECT * FROM chat_jobs WHERE id=?", (data.id,)).fetchone()
        if existing:
            if existing["chat_id"] != chat_id or existing["question"] != question:
                raise HTTPException(409, "Идентификатор вопроса уже использован.")
            return dict(id=existing["id"], status=existing["status"])
        jobs = db.execute("SELECT status FROM chat_jobs WHERE chat_id=?", (chat_id,)).fetchall()
        pending = sum(row["status"] in PENDING for row in jobs)
        if sum(row["status"] == "queued" for row in jobs) >= 5:
            raise HTTPException(429, "В очереди уже 5 вопросов. Дождитесь ответа или уберите лишний.")
        if len(jobs) >= 100:
            raise HTTPException(429, "Достигнут лимит запросов этого диалога. Начните новый.")
        turns = json.loads(chat["turns"])
        retry = bool(turns and turns[-1]["answer"]["status"] in EXCLUDED_CONTEXT and turns[-1]["question"] == question
                     and not any(row["status"] in ("running", "cancelling") for row in jobs))
        if len(turns) + pending - int(retry) >= 20:
            raise HTTPException(413, "Диалог слишком длинный. Начните новый.")
        if chat["busy_until"] > time.time() and not any(row["status"] in ("running", "cancelling") for row in jobs):
            raise HTTPException(409, "Дождитесь завершения текущего ответа.")
        db.execute("INSERT OR IGNORE INTO chat_queue(chat_id) VALUES (?)", (chat_id,))
        created = time.time()
        if retry:
            first_waiting = db.execute("SELECT MIN(created) FROM chat_jobs WHERE chat_id=? AND status='queued'", (chat_id,)).fetchone()[0]
            if first_waiting is not None:
                created = first_waiting - .001
        db.execute("INSERT INTO chat_jobs(id,chat_id,question,status,created) VALUES (?,?,?,'queued',?)",
                   (data.id, chat_id, question, created))
    return dict(id=data.id, status="queued")


@router.post("/{chat_id}/jobs", status_code=202)
async def submit(chat_id: str, request: Request):
    identity(request)
    json_only(request)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 64 * 1024:
            raise HTTPException(413, "Вопрос слишком длинный.")
    try:
        data = JobInput.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Проверьте вопрос и идентификатор запроса.") from None
    return await run_in_threadpool(enqueue, request, chat_id, data)


@router.get("/{chat_id}/jobs")
def snapshot(chat_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN")
        chat = history.get(db, owner, chat_id)
        jobs = [dict(row) for row in db.execute(
            "SELECT id, question, status FROM chat_jobs WHERE chat_id=? AND status IN ('queued','running','cancelling') ORDER BY created,rowid", (chat_id,))]
        control = db.execute("SELECT paused FROM chat_queue WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(jobs=jobs, paused=bool(control and control[0]), turns=json.loads(chat["turns"]),
                    busy=chat["busy_until"] > time.time(), title=chat["title"])


@router.delete("/{chat_id}/jobs/{job_id}", status_code=204)
def cancel(chat_id: str, job_id: str, request: Request):
    history, owner = identity(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        history.get(db, owner, chat_id)
        job = db.execute("SELECT status FROM chat_jobs WHERE id=? AND chat_id=?", (job_id, chat_id)).fetchone()
        if not job:
            raise HTTPException(404, "Вопрос не найден.")
        if job[0] == "queued":
            db.execute("UPDATE chat_jobs SET status='cancelled' WHERE id=?", (job_id,))
        elif job[0] in ("running", "cancelling"):
            db.execute("UPDATE chat_jobs SET status='cancelling' WHERE id=?", (job_id,))
            db.execute("UPDATE chat_queue SET paused=1 WHERE chat_id=?", (chat_id,))


@router.post("/{chat_id}/jobs/resume", status_code=204)
def resume(chat_id: str, request: Request):
    history, owner = identity(request)
    json_only(request)
    with history.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        history.get(db, owner, chat_id)
        if db.execute("SELECT 1 FROM chat_jobs WHERE chat_id=? AND status='cancelling'", (chat_id,)).fetchone():
            raise HTTPException(409, "Дождитесь остановки текущего ответа.")
        db.execute("UPDATE chat_queue SET paused=0 WHERE chat_id=?", (chat_id,))


class QueueManager:
    def __init__(self, history, state, workers=2, runner=run_generation):
        self.history, self.state, self.runner = history, state, runner
        self.stopped = Event()
        self.worker_id = str(uuid4())
        self.threads = [Thread(target=self.loop, daemon=True) for _ in range(workers)]

    def start(self):
        for thread in self.threads:
            thread.start()

    def close(self):
        self.stopped.set()
        for thread in self.threads:
            if thread.ident is not None:
                thread.join(timeout=5)

    def finish(self, db, job, result):
        row = db.execute("SELECT * FROM chats WHERE id=? AND busy_until=?", (job["chat_id"], job["chat_lease"])).fetchone()
        if row is None:
            db.execute("UPDATE chat_jobs SET status='failed' WHERE id=?", (job["id"],))
            return
        turns = json.loads(row["turns"])
        if turns and turns[-1]["answer"]["status"] in EXCLUDED_CONTEXT and turns[-1]["question"] == job["question"]:
            turns.pop()
        turns.append(dict(question=job["question"], answer=result))
        status = "cancelled" if result["status"] == "cancelled" else "failed" if result["status"] == "technical_error" else "done"
        db.execute("UPDATE chats SET turns=?,title=?,updated=?,busy_until=0 WHERE id=?",
                   (json.dumps(turns, ensure_ascii=False), turns[0]["question"][:80], time.time(), job["chat_id"]))
        db.execute("UPDATE chat_jobs SET status=?,lease_until=0 WHERE id=?", (status, job["id"]))
        if status != "done":
            db.execute("UPDATE chat_queue SET paused=1 WHERE chat_id=?", (job["chat_id"],))

    def claim(self):
        with self.history.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Expired workers are never replayed: an interrupted provider request may have completed.
            for expired in db.execute("SELECT * FROM chat_jobs WHERE status IN ('running','cancelling') AND lease_until<?", (time.time(),)).fetchall():
                self.finish(db, expired, dict(status="technical_error", text="Обработка прервалась. Повторите вопрос или продолжите очередь.", sources=[]))
            row = db.execute("""SELECT j.* FROM chat_jobs j JOIN chats c ON c.id=j.chat_id
                JOIN chat_queue q ON q.chat_id=c.id WHERE j.status='queued' AND q.paused=0
                AND c.busy_until<=? AND NOT EXISTS (SELECT 1 FROM chat_trash WHERE chat_id=c.id)
                AND NOT EXISTS (SELECT 1 FROM chat_jobs other WHERE other.chat_id=c.id AND other.status IN ('running','cancelling'))
                ORDER BY j.created,j.rowid LIMIT 1""", (time.time(),)).fetchone()
            if row is None:
                return None
            job = dict(row)
            job["chat_lease"] = time.time() + 240
            db.execute("UPDATE chat_jobs SET status='running',worker=?,lease_until=?,chat_lease=? WHERE id=?",
                       (self.worker_id, time.time() + 15, job["chat_lease"], job["id"]))
            db.execute("UPDATE chats SET busy_until=? WHERE id=?", (job["chat_lease"], job["chat_id"]))
            return job

    def run(self, job):
        last_heartbeat = 0

        def cancelled():
            nonlocal last_heartbeat
            if self.stopped.is_set():
                return True
            with self.history.connect() as db:
                row = db.execute("SELECT status,worker FROM chat_jobs WHERE id=?", (job["id"],)).fetchone()
                if row is None or row[0] != "running" or row[1] != self.worker_id:
                    return True
                if time.monotonic() - last_heartbeat > 1:
                    db.execute("UPDATE chat_jobs SET lease_until=? WHERE id=? AND worker=? AND status='running'",
                               (time.time() + 15, job["id"], self.worker_id))
                    last_heartbeat = time.monotonic()
            return False

        try:
            from web.app import Message, to_question
            with self.history.connect() as db:
                turns = json.loads(db.execute("SELECT turns FROM chats WHERE id=?", (job["chat_id"],)).fetchone()[0])
            previous = []
            for turn in turns:
                if turn["answer"]["status"] not in EXCLUDED_CONTEXT:
                    previous.extend([Message(role="user", text=turn["question"]), Message(role="assistant", text=turn["answer"]["text"])])
            question = to_question([*previous, Message(role="user", text=job["question"])])
            if len(question) > 30000:
                result = dict(status="technical_error", text="Диалог слишком длинный. Начните новый.", sources=[])
            else:
                result = self.runner(question, job["question"], self.state, cancelled)
        except Exception as error:
            print("queue_error: " + type(error).__name__)
            result = dict(status="technical_error", text="Не удалось получить ответ. Повторите вопрос.", sources=[])
        with self.history.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM chat_jobs WHERE id=?", (job["id"],)).fetchone()
            if current and current["worker"] == self.worker_id and current["status"] in ("running", "cancelling"):
                if current["status"] == "cancelling" or self.stopped.is_set():
                    result = dict(status="cancelled", text="Ответ остановлен.", sources=[])
                self.finish(db, job, result)

    def loop(self):
        while not self.stopped.is_set():
            if self.state.slots.acquire(blocking=False):
                try:
                    job = self.claim()
                    if job:
                        self.run(job)
                        continue
                except Exception as error:
                    print("queue_worker_error: " + type(error).__name__)
                finally:
                    self.state.slots.release()
            self.stopped.wait(.25)
