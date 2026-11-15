"""Personal review marks: per login, per answer version, never a change of the core status."""
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app
from web.history import History
from web.workspace import turn_key


class AnswerReviewTests(unittest.TestCase):
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
            {"question": "Срок оплаты?", "answer": {"status": "answer", "text": "Десять дней [1]",
                                                     "sources": [{"n": 1, "quote": "в течение 10 дней"}]}},
            {"question": "Погода?", "answer": {"status": "out_of_scope", "text": "Вне тематики", "sources": []}},
            {"question": "Сбой", "answer": {"status": "technical_error", "text": "Ошибка", "sources": []}},
        ]
        self.write_turns(self.turns)
        self.history = self.client.app.state.history

    def write_turns(self, turns):
        history = self.client.app.state.history
        _, lease = history.begin("alice", self.chat)
        history.finish("alice", self.chat, lease, turns)

    def review(self, index, state, revision=0, headers=None, turns=None):
        turns = turns or self.turns
        return self.client.put(f"/api/workspace/chats/{self.chat}/answers/{index}/review",
                               headers=headers or self.headers,
                               json={"revision": revision, "turn_key": turn_key(turns[index]), "state": state})

    def workspace_review(self, index):
        return self.client.get("/api/workspace/chats/" + self.chat, headers=self.headers).json()["answers"][index]["review"]

    def test_set_change_reset_and_two_device_conflict(self):
        first = self.review(0, "sources_viewed")
        self.assertEqual(first.status_code, 200)
        self.assertEqual((first.json()["state"], first.json()["revision"]), ("sources_viewed", 1))
        self.assertIsInstance(first.json()["updated"], float)
        # A stale device cannot replace a newer different choice silently...
        self.assertEqual(self.review(0, "needs_check", revision=0).status_code, 409)
        # ...but repeating the same choice after a lost response is accepted unchanged.
        self.assertEqual(self.review(0, "sources_viewed", revision=0).json()["revision"], 1)
        self.assertEqual(self.review(0, "needs_check", revision=1).json()["revision"], 2)
        reset = self.review(0, "", revision=2).json()
        self.assertEqual((reset["state"], reset["revision"]), ("", 3))
        self.assertEqual(self.workspace_review(0)["state"], "")
        self.assertEqual(self.workspace_review(1), {"state": "", "updated": None, "revision": 0})

    def test_mark_is_bound_to_answer_version_and_never_changes_core_status(self):
        self.review(0, "sources_viewed")
        self.assertEqual(self.client.get("/api/chats/" + self.chat, headers=self.headers).json()["turns"], self.turns)
        replaced = [dict(self.turns[0], answer={**self.turns[0]["answer"], "text": "Другой ответ [1]"}), *self.turns[1:]]
        self.write_turns(replaced)
        # The replaced answer neither inherits the mark nor appears among reviewed materials.
        self.assertEqual(self.workspace_review(0)["state"], "")
        self.assertEqual(self.client.get("/api/workspace/saved", headers=self.headers).json(), [])
        self.assertEqual(self.review(0, "needs_check", turns=self.turns).status_code, 409)
        self.assertEqual(self.review(0, "needs_check", revision=0, turns=replaced).json()["revision"], 1)

    def test_unfinished_answers_and_answers_without_sources(self):
        self.assertEqual(self.review(2, "needs_check").status_code, 409)
        rejected = self.review(1, "sources_viewed")
        self.assertEqual(rejected.status_code, 422)
        self.assertIn("нет источников", rejected.json()["detail"])
        self.assertEqual(self.review(1, "needs_check").status_code, 200)
        self.assertEqual(self.review(9, "needs_check", turns=self.turns * 4).status_code, 404)
        for state in ["correct", "verified", "Источники просмотрены"]:
            self.assertEqual(self.review(0, state).status_code, 422)

    def test_saved_list_includes_review_only_answers_with_date(self):
        self.review(1, "needs_check")
        items = self.client.get("/api/workspace/saved", headers=self.headers).json()
        self.assertEqual([(item["turn_index"], item["saved"], item["note"]) for item in items], [(1, False, "")])
        self.assertEqual(items[0]["review"]["state"], "needs_check")
        self.assertEqual(items[0]["answer"], self.turns[1]["answer"])
        self.client.put(f"/api/workspace/chats/{self.chat}/answers/0", headers=self.headers,
                        json={"revision": 0, "turn_key": turn_key(self.turns[0]), "saved": True, "note": ""})
        items = self.client.get("/api/workspace/saved", headers=self.headers).json()
        self.assertEqual([(item["turn_index"], item["review"]["state"]) for item in items], [(0, ""), (1, "needs_check")])
        self.review(1, "", revision=1)
        self.assertEqual([item["turn_index"] for item in self.client.get("/api/workspace/saved", headers=self.headers).json()], [0])

    def test_owner_isolation_trash_and_permanent_delete(self):
        self.assertEqual(self.review(0, "needs_check", headers=self.bob).status_code, 404)
        self.assertEqual(self.review(0, "needs_check", headers={"Content-Type": "application/json"}).status_code, 401)
        self.assertEqual(self.client.put(f"/api/workspace/chats/{self.chat}/answers/0/review",
                                         headers={**self.headers, "Origin": "https://other.example"},
                                         json={"revision": 0, "turn_key": turn_key(self.turns[0]), "state": ""}).status_code, 403)
        self.review(0, "needs_check")
        self.assertEqual(self.client.get("/api/workspace/saved", headers=self.bob).json(), [])
        self.client.delete("/api/chats/" + self.chat, headers=self.headers)
        self.assertEqual(self.client.get("/api/workspace/saved", headers=self.headers).json(), [])
        self.assertEqual(self.review(0, "", revision=1).status_code, 404)
        self.client.post("/api/chats/" + self.chat + "/restore", headers=self.headers)
        self.assertEqual(self.workspace_review(0)["state"], "needs_check")
        self.client.delete("/api/chats/" + self.chat, headers=self.headers)
        self.client.delete("/api/chats/" + self.chat + "/permanent", headers=self.headers)
        with self.history.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM answer_reviews").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM chat_jobs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM request_budgets").fetchone()[0], 0)

    def test_existing_database_gains_review_table_without_rewriting_answers(self):
        path = str(Path(self.path).with_name("old.sqlite3"))
        original = json.dumps(self.turns, ensure_ascii=False)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE chats(id TEXT PRIMARY KEY, owner TEXT, title TEXT, updated REAL, turns TEXT, busy_until REAL)")
            db.execute("INSERT INTO chats VALUES ('old','alice','Old',1,?,0)", (original,))
        history = History(path, "fixture-token")
        with history.connect() as db:
            self.assertEqual(history.get(db, "alice", "old")["turns"], original)
            self.assertEqual(db.execute("SELECT count(*) FROM answer_reviews").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM answer_briefs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM question_templates").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
