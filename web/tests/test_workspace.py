from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from web.app import app
from web.history import History
from web.queue import QueueManager
from web.workspace import turn_key


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = str(Path(directory) / "history.sqlite3")
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=self.path, CHAT_PROXY_TOKEN="fixture-token"))
        self.client = self.enterContext(TestClient(app))
        self.client.app.state.queue.close()
        self.headers = {"X-Chat-User": "alice", "X-Chat-Token": "fixture-token", "Content-Type": "application/json"}
        self.bob = {**self.headers, "X-Chat-User": "bob"}
        self.chat = self.client.post("/api/chats", headers=self.headers).json()["id"]
        self.turns = [
            {"question": "Первый вопрос", "answer": {"status": "answer", "text": "Первый ответ [1]", "sources": [{"quote": "Точное основание", "n": 1}]}},
            {"question": "Второй вопрос", "answer": {"status": "answer", "text": "Второй ответ", "sources": []}},
        ]
        self.history = self.client.app.state.history
        _, lease = self.history.begin("alice", self.chat)
        self.history.finish("alice", self.chat, lease, self.turns)
        self.prefix = "/api/workspace/chats/" + self.chat

    def call(self, method, path, data=None, headers=None):
        return self.client.request(method, path, headers=self.headers if headers is None else headers,
                                   **({"json": data} if data is not None else {}))

    def annotation(self, **changes):
        return dict(revision=0, turn_key=turn_key(self.turns[0]), saved=True, note="Моя заметка", **changes)

    def branch_data(self, include=False):
        return dict(id=str(uuid4()), index=1, turn_key=turn_key(self.turns[1]), include_answer=include, draft="Изменённый вопрос")

    def test_persistence_and_revision_conflicts_keep_transcript_unchanged(self):
        matter = {"contract": "Тестовый договор", "event_date": "2026-02-12", "situation": "Рабочие сведения"}
        self.assertEqual(self.call("PUT", self.prefix + "/matter", {"revision": 0, "matter": matter}).status_code, 200)
        self.assertEqual(self.call("PUT", self.prefix + "/matter", {"revision": 0, "matter": {}}).status_code, 409)
        draft = "/api/workspace/drafts/" + self.chat
        self.assertEqual(self.call("PUT", draft, {"revision": 0, "text": "Черновик"}).status_code, 200)
        self.assertEqual(self.call("PUT", draft, {"revision": 0, "text": "Чужая старая версия"}).status_code, 409)
        # Retrying the identical write after a lost response is safe.
        self.assertEqual(self.call("PUT", draft, {"revision": 0, "text": "Черновик"}).json()["revision"], 1)
        self.assertEqual(self.call("PUT", self.prefix + "/answers/0", self.annotation()).status_code, 200)
        self.assertEqual(self.call("PUT", self.prefix + "/answers/0", self.annotation()).status_code, 409)
        restored = History(self.path, "fixture-token")
        with restored.connect() as db:
            self.assertEqual(json.loads(restored.get(db, "alice", self.chat)["turns"]), self.turns)
        workspace = self.call("GET", self.prefix).json()
        self.assertEqual(workspace["matter"]["event_date"], matter["event_date"])
        self.assertEqual(workspace["draft"], "Черновик")
        self.assertEqual(workspace["answers"][0]["note"], "Моя заметка")
        self.assertEqual(self.call("GET", "/api/workspace/saved").json()[0]["answer"], self.turns[0]["answer"])

    def test_every_private_operation_checks_owner_and_cache(self):
        job = str(uuid4())
        self.call("POST", f"/api/chats/{self.chat}/jobs", {"id": job, "question": "В очереди"})
        operations = [
            ("GET", self.prefix, None),
            ("GET", "/api/workspace/drafts/" + self.chat, None),
            ("PUT", "/api/workspace/drafts/" + self.chat, {"revision": 0, "text": "Чужой"}),
            ("PUT", self.prefix + "/matter", {"revision": 0, "matter": {}}),
            ("PUT", self.prefix + "/answers/0", self.annotation()),
            ("POST", self.prefix + "/branch", self.branch_data()),
            ("PUT", self.prefix + "/read", {"turn_key": turn_key(self.turns[-1])}),
            ("PUT", self.prefix + "/queued/" + job, {"expected_question": "В очереди", "question": "Другой"}),
        ]
        for method, path, body in operations:
            with self.subTest(path=path, method=method):
                self.assertEqual(self.call(method, path, body, self.bob).status_code, 404)
                self.assertEqual(self.call(method, path, body, {}).status_code, 401)
        self.assertEqual(self.call("GET", "/api/workspace/saved", headers=self.bob).json(), [])
        self.assertEqual(self.call("GET", "/api/workspace/activity", headers=self.bob).json(), [])
        self.assertEqual(self.call("GET", self.prefix).headers["cache-control"], "private, no-store")
        self.call("PUT", "/api/workspace/drafts/new", {"revision": 0, "text": "Личный черновик"})
        self.assertEqual(self.call("GET", "/api/workspace/drafts/new", headers=self.bob).json()["text"], "")

    def test_validation_body_limits_and_csrf(self):
        draft = "/api/workspace/drafts/" + self.chat
        for body in [{"revision": 0, "text": "a" * 10001}, {"revision": -1, "text": "a"},
                     {"revision": 0, "text": "\u0000"},
                     {"revision": 0, "text": "a", "owner": "bob"}]:
            self.assertEqual(self.call("PUT", draft, body).status_code, 422)
        self.assertEqual(self.client.put(draft, headers=self.headers,
                         content=json.dumps({"revision": 0, "text": "\ud800"}, ensure_ascii=True)).status_code, 422)
        for matter in [{"event_date": "2026-02-31"}, {"contract": "a" * 301}, {"system_prompt": "hidden"}]:
            self.assertEqual(self.call("PUT", self.prefix + "/matter", {"revision": 0, "matter": matter}).status_code, 422)
        self.assertEqual(self.call("PUT", draft, {"revision": 0, "text": "x"}, {**self.headers, "Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.call("PUT", draft, {"revision": 0, "text": "x"}, {**self.headers, "Content-Type": "text/plain"}).status_code, 415)
        self.assertEqual(self.client.put(draft, headers=self.headers, content=b"x" * (128 * 1024 + 1)).status_code, 413)

    def test_branch_copies_only_the_selected_prefix_and_is_idempotent(self):
        self.call("PUT", self.prefix + "/matter", {"revision": 0, "matter": {"contract": "Личный контекст"}})
        body = self.branch_data()
        result = self.call("POST", self.prefix + "/branch", body)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.call("POST", self.prefix + "/branch", body).json(), result.json())
        self.assertEqual(len(self.call("GET", "/api/chats").json()), 2)
        child = result.json()["id"]
        self.assertEqual(self.call("GET", "/api/chats/" + child).json()["turns"], self.turns[:1])
        self.assertEqual(self.call("GET", "/api/chats/" + self.chat).json()["turns"], self.turns)
        workspace = self.call("GET", "/api/workspace/chats/" + child).json()
        self.assertEqual(workspace["draft"], body["draft"])
        self.assertEqual(workspace["parent"]["id"], self.chat)
        self.assertEqual(workspace["matter"]["contract"], "Личный контекст")
        with self.history.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_jobs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM request_budgets").fetchone()[0], 0)
        self.assertEqual(self.call("POST", self.prefix + "/branch", {**body, "draft": "Другой"}).status_code, 409)
        second = self.call("POST", self.prefix + "/branch", self.branch_data(True)).json()["id"]
        self.assertEqual(self.call("GET", "/api/chats/" + second).json()["turns"], self.turns)

    def test_workspace_is_not_in_generation_context_and_branch_has_no_future_turns(self):
        self.call("PUT", self.prefix + "/matter", {"revision": 0, "matter": {"situation": "PRIVATE_CARD_SENTINEL"}})
        self.call("PUT", self.prefix + "/answers/0", {**self.annotation(), "note": "PRIVATE_NOTE_SENTINEL"})
        child = self.call("POST", self.prefix + "/branch", self.branch_data()).json()["id"]
        self.call("POST", f"/api/chats/{child}/jobs", {"id": str(uuid4()), "question": "Исправленный вопрос"})
        calls = []
        def runner(question, latest, state, cancelled):
            calls.append((question, latest))
            return dict(status="answer", text="Ответ из заглушки", sources=[])
        manager = QueueManager(self.history, self.client.app.state, 1, runner)
        self.addCleanup(manager.close)
        manager.start()
        deadline = time.monotonic() + 4
        while not calls and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(len(calls), 1)
        self.assertIn("Первый вопрос", calls[0][0])
        for excluded in ["Второй вопрос", "Второй ответ", "PRIVATE_CARD_SENTINEL", "PRIVATE_NOTE_SENTINEL", "Изменённый вопрос"]:
            self.assertNotIn(excluded, calls[0][0])
        self.assertEqual(calls[0][1], "Исправленный вопрос")

    def test_stale_turn_and_chat_limits_do_not_create_a_branch(self):
        body = self.branch_data()
        self.assertEqual(self.call("POST", self.prefix + "/branch", {**body, "turn_key": "0" * 64}).status_code, 409)
        self.assertEqual(self.call("PUT", self.prefix + "/answers/0", {**self.annotation(), "turn_key": "0" * 64}).status_code, 409)
        with self.history.connect() as db:
            for index in range(99):
                db.execute("INSERT INTO chats(id,owner,title,updated) VALUES (?,'alice','fixture',1)", (str(uuid4()),))
        self.assertEqual(self.call("POST", self.prefix + "/branch", body).status_code, 429)

    def test_trash_restore_and_permanent_delete_clean_workspace(self):
        self.call("PUT", self.prefix + "/answers/0", self.annotation())
        body = self.branch_data()
        child = self.call("POST", self.prefix + "/branch", body).json()["id"]
        self.assertEqual(self.call("DELETE", "/api/chats/" + self.chat).status_code, 204)
        self.assertEqual(self.call("GET", self.prefix).status_code, 404)
        self.assertEqual(self.call("GET", "/api/workspace/saved").json(), [])
        self.assertEqual(self.call("POST", "/api/chats/" + self.chat + "/restore").status_code, 204)
        self.assertEqual(len(self.call("GET", "/api/workspace/saved").json()), 1)
        self.call("DELETE", "/api/chats/" + self.chat)
        self.assertEqual(self.call("DELETE", "/api/chats/" + self.chat + "/permanent").status_code, 204)
        self.assertIsNone(self.call("GET", "/api/workspace/chats/" + child).json()["parent"])
        with self.history.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM answer_annotations").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM chat_workspace WHERE chat_id=?", (self.chat,)).fetchone()[0], 0)

    def test_unread_only_tracks_completed_answers_and_requires_current_version(self):
        self.assertTrue(self.call("GET", "/api/workspace/activity").json()[0]["unread"])
        self.assertEqual(self.call("PUT", self.prefix + "/read", {"turn_key": turn_key(self.turns[0])}).status_code, 409)
        self.assertEqual(self.call("PUT", self.prefix + "/read", {"turn_key": turn_key(self.turns[1])}).status_code, 200)
        self.assertFalse(self.call("GET", "/api/workspace/activity").json()[0]["unread"])
        _, lease = self.history.begin("alice", self.chat)
        turns = self.turns + [{"question": "Ещё", "answer": {"status": "cancelled", "text": "Остановлено"}}]
        self.history.finish("alice", self.chat, lease, turns)
        self.assertFalse(self.call("GET", "/api/workspace/activity").json()[0]["unread"])
        self.assertEqual(self.call("PUT", self.prefix + "/answers/2", {**self.annotation(), "turn_key": turn_key(turns[-1])}).status_code, 409)

    def test_queue_edit_keeps_order_budget_and_rejects_claimed_job(self):
        first, second = str(uuid4()), str(uuid4())
        for job, question in [(first, "Первый в очереди"), (second, "Второй в очереди")]:
            self.call("POST", f"/api/chats/{self.chat}/jobs", {"id": job, "question": question})
        with self.history.connect() as db:
            before = [tuple(row) for row in db.execute("SELECT * FROM request_budgets")]
        body = {"expected_question": "Второй в очереди", "question": "Исправленный второй"}
        self.assertEqual(self.call("PUT", self.prefix + "/queued/" + second, body).status_code, 200)
        self.assertEqual(self.call("PUT", self.prefix + "/queued/" + second, body).status_code, 200)
        self.assertEqual(self.call("PUT", self.prefix + "/queued/" + second, {**body, "question": "Устаревшее изменение"}).status_code, 409)
        jobs = self.call("GET", f"/api/chats/{self.chat}/jobs").json()["jobs"]
        self.assertEqual([(item["id"], item["question"]) for item in jobs], [(first, "Первый в очереди"), (second, body["question"])])
        with self.history.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM request_budgets")], before)
            db.execute("UPDATE chat_jobs SET status='running' WHERE id=?", (second,))
        self.assertEqual(self.call("PUT", self.prefix + "/queued/" + second, {"expected_question": body["question"], "question": "Поздно"}).status_code, 409)

    def test_existing_database_migration_preserves_answers_and_is_repeatable(self):
        path = str(Path(self.path).with_name("old.sqlite3"))
        original = json.dumps(self.turns, ensure_ascii=False)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE chats(id TEXT PRIMARY KEY, owner TEXT, title TEXT, updated REAL, turns TEXT, busy_until REAL)")
            db.execute("INSERT INTO chats VALUES ('old','alice','Old',1,?,0)", (original,))
        History(path, "fixture-token")
        history = History(path, "fixture-token")
        with history.connect() as db:
            self.assertEqual(history.get(db, "alice", "old")["turns"], original)
            self.assertEqual(db.execute("SELECT count(*) FROM chat_workspace").fetchone()[0], 0)

    def test_searches_and_recents_are_private_and_survive_new_requests(self):
        searches = "/api/workspace/searches"
        recents = "/api/workspace/recent-documents"
        search = dict(id=str(uuid4()), title="Договоры", scope="picker", query="поставка",
                      kind="contracts", edition="current", selected=True)
        self.assertEqual(self.call("PUT", searches, dict(revision=0, items=[search])).status_code, 200)
        result = self.call("GET", searches).json()
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["items"][0]["query"], "поставка")
        self.assertTrue(result["items"][0]["selected"])
        self.assertEqual(self.call("GET", searches, headers=self.bob).json()["items"], [])
        self.assertEqual(self.call("GET", searches, headers={}).status_code, 401)
        self.assertEqual(self.call("PUT", searches, dict(revision=0, items=[])).status_code, 409)

        first, second = list(app.state.documents)[:2]
        for document_id in [first, second, first]:
            self.assertEqual(self.call("PUT", recents, dict(document_id=document_id)).status_code, 204)
        self.assertEqual([entry["document_id"] for entry in self.call("GET", recents).json()], [first, second])
        self.assertEqual(self.call("GET", recents, headers=self.bob).json(), [])
        self.assertEqual(self.call("DELETE", recents, headers=self.bob).status_code, 204)
        self.assertEqual(len(self.call("GET", recents).json()), 2)
        self.assertEqual(self.call("DELETE", recents).status_code, 204)
        self.assertEqual(self.call("GET", recents).json(), [])

    def test_checklist_links_branch_and_trash(self):
        path = self.prefix + "/checklist"
        task = dict(id=str(uuid4()), title="Сверить редакцию", done=True,
                    answer_key=turn_key(self.turns[0]), document_id=next(iter(app.state.documents)))
        self.assertEqual(self.call("PUT", path, dict(revision=0, items=[task])).status_code, 422)
        self.assertEqual(self.call("PUT", self.prefix + "/answers/0", self.annotation()).status_code, 200)
        self.assertEqual(self.call("PUT", path, dict(revision=0, items=[task])).status_code, 200)
        self.assertEqual(self.call("PUT", path, dict(revision=0, items=[])).status_code, 409)
        self.assertEqual(self.call("GET", path, headers=self.bob).status_code, 404)
        self.assertEqual(self.call("GET", path).json()["answers"][0]["key"], task["answer_key"])
        for copy in [False, True]:
            branch = self.branch_data()
            response = self.call("POST", self.prefix + "/branch", {**branch, "copy_checklist": copy})
            self.assertEqual(response.status_code, 201, response.text)
            items = self.call("GET", "/api/workspace/chats/" + branch["id"] + "/checklist").json()["items"]
            if copy:
                self.assertEqual(items[0]["document_id"], task["document_id"])
                self.assertFalse(items[0]["done"])
                self.assertIsNone(items[0]["answer_key"])
            else:
                self.assertEqual(items, [])
        chat = "/api/chats/" + self.chat
        self.assertEqual(self.call("DELETE", chat).status_code, 204)
        self.assertEqual(self.call("GET", path).status_code, 404)
        self.assertEqual(self.call("POST", chat + "/restore").status_code, 204)
        self.assertTrue(self.call("GET", path).json()["items"][0]["done"])
        self.assertEqual(self.call("DELETE", chat).status_code, 204)
        self.assertEqual(self.call("DELETE", chat + "/permanent").status_code, 204)
        with self.history.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM workspace_checklists WHERE chat_id=?", (self.chat,)).fetchone())
