"""Question template library: server storage and the placeholder contract shared with the browser."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from web.app import app
from web.question_templates import BUILTIN, FIELDS, LIMIT, placeholders


class QuestionTemplateTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = str(Path(directory) / "history.sqlite3")
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=self.path, CHAT_PROXY_TOKEN="fixture-token"))
        self.client = self.enterContext(TestClient(app))
        self.client.app.state.queue.close()
        self.headers = {"X-Chat-User": "alice", "X-Chat-Token": "fixture-token", "Content-Type": "application/json"}
        self.bob = {**self.headers, "X-Chat-User": "bob"}

    def body(self, **changes):
        return {"id": str(uuid4()), "title": "Поставка: сроки", "description": "Мой вариант",
                "text": "Какие сроки поставки по договору {договор} на {дата}?\nУточнение: {уточнение}",
                "required": ["contract", "event_date"], **changes}

    def create(self, headers=None, **changes):
        return self.client.post("/api/question-templates", headers=headers or self.headers, json=self.body(**changes))

    def listing(self, headers=None):
        return self.client.get("/api/question-templates", headers=headers or self.headers).json()

    def test_builtin_templates_follow_the_same_contract(self):
        tokens = {field["token"] for field in FIELDS}
        self.assertEqual([item["title"] for item in BUILTIN],
                         ["Согласование договора", "Сроки и обязательства", "Редакция на дату", "Основания вывода"])
        for item in BUILTIN:
            with self.subTest(item=item["id"]):
                fields = placeholders(item["text"])
                self.assertTrue(set(item["required"]) <= set(fields))
                # An optional field is alone on its line, so dropping that line keeps the question intact.
                for line in item["text"].split("\n"):
                    used = placeholders(line)
                    if any(key not in item["required"] for key in used):
                        self.assertEqual(len(used), 1, line)
                self.assertIn("основани", item["text"].lower())
        listed = self.listing()
        self.assertEqual([item["id"] for item in listed["builtin"]], [item["id"] for item in BUILTIN])
        self.assertEqual(listed["builtin"][0]["fields"], ["contract", "counterparty", "amount", "event_date", "details"])
        self.assertEqual({field["token"] for field in listed["fields"]}, tokens)
        self.assertEqual(listed["own"], [])

    def test_create_find_update_copy_and_delete_with_revisions(self):
        created = self.create()
        self.assertEqual(created.status_code, 201)
        template = created.json()
        self.assertEqual((template["revision"], template["fields"], template["required"]),
                         (1, ["contract", "event_date", "details"], ["contract", "event_date"]))
        # A lost-response retry returns the same template; reusing the id for other text does not.
        retry = self.client.post("/api/question-templates", headers=self.headers, json=self.body(id=template["id"]))
        self.assertEqual(retry.json()["id"], template["id"])
        self.assertEqual(self.create(id=template["id"], title="Другой").status_code, 409)
        self.assertEqual(len(self.listing()["own"]), 1)
        path = "/api/question-templates/" + template["id"]
        changed = {key: value for key, value in self.body(title="Сроки поставки", required=["contract"]).items() if key != "id"}
        updated = self.client.put(path, headers=self.headers, json={**changed, "revision": 1})
        self.assertEqual((updated.status_code, updated.json()["revision"]), (200, 2))
        self.assertGreaterEqual(updated.json()["updated"], template["updated"])
        self.assertEqual(self.client.put(path, headers=self.headers, json={**changed, "revision": 1}).json()["revision"], 2)
        stale = {**changed, "title": "Старое изменение со второго устройства", "revision": 1}
        self.assertEqual(self.client.put(path, headers=self.headers, json=stale).status_code, 409)
        copy = self.create(title="Сроки поставки (копия)")
        self.assertEqual(copy.status_code, 201)
        self.assertEqual([item["title"] for item in self.listing()["own"]], ["Сроки поставки", "Сроки поставки (копия)"])
        self.assertEqual(self.client.delete(path + "?revision=1", headers=self.headers).status_code, 409)
        self.assertEqual(self.client.delete(path + "?revision=2", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.delete(path + "?revision=2", headers=self.headers).status_code, 404)
        self.assertEqual([item["title"] for item in self.listing()["own"]], ["Сроки поставки (копия)"])

    def test_placeholders_are_validated_not_guessed(self):
        for changes, message in [
            ({"text": "Какой срок по договору {номер}?"}, "Неизвестное поле {номер}"),
            ({"text": "Какой срок по договору {договор?"}, "Фигурные скобки"),
            ({"text": "Какой срок {}?"}, "Неизвестное поле {}"),
            ({"required": ["amount"]}, "Обязательным можно отметить"),
            ({"required": ["system_prompt"]}, "Обязательным можно отметить"),
            ({"title": "   "}, "Укажите название"),
        ]:
            with self.subTest(changes=changes):
                response = self.create(**changes)
                self.assertEqual(response.status_code, 422)
                self.assertIn(message, response.json()["detail"])
        for changes in [{"title": "a" * 81}, {"text": "a" * 4001}, {"description": "\u0000"}, {"owner": "bob"},
                        {"id": "not-a-uuid"}, {"required": "contract"}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.create(**changes).status_code, 422)
        self.assertEqual(self.create(text="  Вопрос без полей \r\nвторая строка  ", required=[]).json()["text"],
                         "Вопрос без полей \nвторая строка")
        with self.assertRaises(HTTPException):
            placeholders("{договор} и {контрагент} }")

    def test_owner_isolation_limits_csrf_and_no_generation(self):
        template = self.create().json()
        path = "/api/question-templates/" + template["id"]
        self.assertEqual(self.listing(self.bob)["own"], [])
        body = {key: value for key, value in self.body().items() if key != "id"}
        self.assertEqual(self.client.put(path, headers=self.bob, json={**body, "revision": 1}).status_code, 404)
        self.assertEqual(self.client.delete(path + "?revision=1", headers=self.bob).status_code, 404)
        self.assertEqual(self.create(headers=self.bob, id=template["id"]).status_code, 409)
        self.assertEqual(self.client.get("/api/question-templates", headers={"X-Chat-User": "alice"}).status_code, 401)
        self.assertEqual(self.create(headers={**self.headers, "Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/question-templates", headers={**self.headers, "Content-Type": "text/plain"},
                                          content=b"{}").status_code, 415)
        self.assertEqual(self.client.get("/api/question-templates", headers=self.headers).headers["cache-control"],
                         "private, no-store")
        for _ in range(LIMIT - 1):
            self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create().status_code, 429)
        self.assertEqual(self.create(headers=self.bob).status_code, 201)
        with self.client.app.state.history.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_jobs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM request_budgets").fetchone()[0], 0)


class TemplatesWithoutHistoryTests(unittest.TestCase):
    def test_builtin_templates_work_without_server_history(self):
        environment = {key: value for key, value in os.environ.items() if key not in {"CHAT_HISTORY_PATH", "CHAT_PROXY_TOKEN"}}
        with patch.dict(os.environ, environment, clear=True), TestClient(app) as client:
            listed = client.get("/api/question-templates")
            self.assertEqual(listed.status_code, 200)
            self.assertIsNone(listed.json()["own"])
            self.assertEqual(len(listed.json()["builtin"]), len(BUILTIN))
            created = client.post("/api/question-templates", json={"id": str(uuid4()), "title": "x", "text": "y"})
            self.assertEqual(created.status_code, 503)


if __name__ == "__main__":
    unittest.main()
