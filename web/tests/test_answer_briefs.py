"""Brief compositions reference exact answer versions and never call the model."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from web.app import app
from web.answer_briefs import LIMIT
from web.workspace import turn_key


class AnswerBriefTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=str(Path(directory) / "history.sqlite3"),
                                     CHAT_PROXY_TOKEN="fixture-token"))
        self.client = self.enterContext(TestClient(app))
        self.client.app.state.queue.close()
        self.history = self.client.app.state.history
        self.headers = {"X-Chat-User": "alice", "X-Chat-Token": "fixture-token", "Content-Type": "application/json"}
        self.bob = {**self.headers, "X-Chat-User": "bob"}
        self.chat = self.client.post("/api/chats", headers=self.headers).json()["id"]
        self.turns = [
            {"question": "Срок оплаты?", "answer": {"status": "answer", "text": "Десять дней [1]",
                                                     "sources": [{"n": 1, "title": "Договор А", "quote": "в течение 10 дней"}]}},
            {"question": "Неустойка?", "answer": {"status": "partial", "text": "Подтверждена часть [1]",
                                                   "sources": [{"n": 1, "title": "Договор Б", "quote": "0,1 % в день"}]}},
            {"question": "Сбой", "answer": {"status": "technical_error", "text": "Ошибка", "sources": []}},
            {"question": "Дата события?", "answer": {"status": "clarify", "text": "Уточните дату события.", "sources": []}},
        ]
        self.write_turns(self.turns)
        self.prefix = f"/api/workspace/chats/{self.chat}/briefs"

    def write_turns(self, turns):
        _, lease = self.history.begin("alice", self.chat)
        self.history.finish("alice", self.chat, lease, turns)

    def section(self, index, comment="", turns=None):
        return {"turn_index": index, "turn_key": turn_key((turns or self.turns)[index]), "comment": comment}

    def body(self, **changes):
        return {"id": str(uuid4()), "title": "Справка по оплате", "intro": "Для руководителя",
                "sections": [self.section(1, "Проверить расчёт"), self.section(0)],
                "matter_fields": ["contract", "event_date"], "include_reviews": True, **changes}

    def create(self, headers=None, **changes):
        return self.client.post(self.prefix, headers=headers or self.headers, json=self.body(**changes))

    def listing(self, headers=None):
        return self.client.get(self.prefix, headers=headers or self.headers)

    def test_saved_composition_keeps_selected_order_and_user_fields(self):
        created = self.create()
        self.assertEqual(created.status_code, 201)
        brief = created.json()
        self.assertEqual([(item["turn_index"], item["comment"], item["available"]) for item in brief["sections"]],
                         [(1, "Проверить расчёт", True), (0, "", True)])
        self.assertEqual((brief["intro"], brief["matter_fields"], brief["include_reviews"], brief["revision"]),
                         ("Для руководителя", ["contract", "event_date"], True, 1))
        self.assertEqual(self.listing().json(), [brief])
        # The brief stores references only; the dialogue and its answers stay unchanged.
        self.assertEqual(self.client.get("/api/chats/" + self.chat, headers=self.headers).json()["turns"], self.turns)
        with self.history.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_jobs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM request_budgets").fetchone()[0], 0)

    def test_revisions_retries_and_delete(self):
        brief = self.create().json()
        path = self.prefix + "/" + brief["id"]
        retry = self.client.post(self.prefix, headers=self.headers, json=self.body(id=brief["id"]))
        self.assertEqual(retry.json()["id"], brief["id"])
        self.assertEqual(self.create(id=brief["id"], title="Другая").status_code, 409)
        reordered = {key: value for key, value in self.body(sections=[self.section(0), self.section(3)]).items() if key != "id"}
        updated = self.client.put(path, headers=self.headers, json={**reordered, "revision": 1})
        self.assertEqual([item["turn_index"] for item in updated.json()["sections"]], [0, 3])
        self.assertEqual(self.client.put(path, headers=self.headers, json={**reordered, "revision": 1}).json()["revision"], 2)
        stale = {**reordered, "title": "Старая версия с другого устройства", "revision": 1}
        self.assertEqual(self.client.put(path, headers=self.headers, json=stale).status_code, 409)
        self.assertEqual(self.client.delete(path + "?revision=1", headers=self.headers).status_code, 409)
        self.assertEqual(self.client.delete(path + "?revision=2", headers=self.headers).status_code, 204)
        self.assertEqual(self.listing().json(), [])

    def test_only_exact_finished_answer_versions_can_be_referenced(self):
        for sections, status in [
            ([self.section(2)], 409),  # technical error
            ([{**self.section(0), "turn_key": "0" * 64}], 409),
            ([{**self.section(0), "turn_index": 4}], 409),
            ([self.section(0), self.section(0)], 422),
            ([], 422),
        ]:
            with self.subTest(sections=sections):
                self.assertEqual(self.create(sections=sections).status_code, status)
        for changes in [{"matter_fields": ["system_prompt"]}, {"title": " "}, {"title": "a" * 121},
                        {"intro": "a" * 4001}, {"sections": [self.section(0, "a" * 2001)]}, {"owner": "bob"}]:
            with self.subTest(changes=list(changes)):
                self.assertEqual(self.create(**changes).status_code, 422)

    def test_changed_answer_is_marked_unavailable_instead_of_substituted(self):
        brief = self.create().json()
        replaced = [self.turns[0], dict(self.turns[1], answer={**self.turns[1]["answer"], "text": "Новый текст [1]"}),
                    *self.turns[2:]]
        self.write_turns(replaced)
        sections = self.listing().json()[0]["sections"]
        self.assertEqual([(item["turn_index"], item["available"]) for item in sections], [(1, False), (0, True)])
        body = {key: value for key, value in self.body().items() if key != "id"}
        self.assertEqual(self.client.put(self.prefix + "/" + brief["id"], headers=self.headers,
                                         json={**body, "revision": 1}).status_code, 409)
        fixed = {**body, "sections": [self.section(0)], "revision": 1}
        self.assertEqual(self.client.put(self.prefix + "/" + brief["id"], headers=self.headers, json=fixed).status_code, 200)

    def test_owner_isolation_trash_cascade_and_limits(self):
        brief = self.create().json()
        path = self.prefix + "/" + brief["id"]
        self.assertEqual(self.listing(self.bob).status_code, 404)
        self.assertEqual(self.create(headers=self.bob).status_code, 404)
        body = {key: value for key, value in self.body().items() if key != "id"}
        self.assertEqual(self.client.put(path, headers=self.bob, json={**body, "revision": 1}).status_code, 404)
        self.assertEqual(self.client.delete(path + "?revision=1", headers=self.bob).status_code, 404)
        self.assertEqual(self.listing({"X-Chat-User": "alice"}).status_code, 401)
        self.assertEqual(self.create(headers={**self.headers, "Origin": "https://other.example"}).status_code, 403)
        other = self.client.post("/api/chats", headers=self.headers).json()["id"]
        self.assertEqual(self.client.put(f"/api/workspace/chats/{other}/briefs/{brief['id']}", headers=self.headers,
                                         json={**body, "revision": 1}).status_code, 404)
        self.client.delete("/api/chats/" + self.chat, headers=self.headers)
        self.assertEqual(self.listing().status_code, 404)
        self.client.post(f"/api/chats/{self.chat}/restore", headers=self.headers)
        self.assertEqual(len(self.listing().json()), 1)
        for _ in range(LIMIT - 1):
            self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create().status_code, 429)
        self.client.delete("/api/chats/" + self.chat, headers=self.headers)
        self.client.delete(f"/api/chats/{self.chat}/permanent", headers=self.headers)
        with self.history.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM answer_briefs").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
