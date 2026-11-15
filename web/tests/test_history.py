import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app
from web.history import History


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "chats.sqlite3")
        env = patch.dict(os.environ, CHAT_HISTORY_PATH=self.path, CHAT_PROXY_TOKEN="test-proxy-token")
        env.start()
        self.addCleanup(env.stop)
        self.client = self.enterContext(TestClient(app))
        self.headers = {"X-Chat-User": "alice", "X-Chat-Token": "test-proxy-token", "Content-Type": "application/json"}

    def create(self):
        response = self.client.post("/api/chats", headers=self.headers)
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def ask(self, chat_id, text="Первый вопрос", answer=None):
        answer = answer or dict(status="answer", text="Ответ [1]", sources=[
            dict(n=1, document_id="fixture", title="Договор", quote="Цитата", start=0, end=6)])
        with patch("web.app.answer", return_value=answer) as core:
            response = self.client.post("/api/chat", headers=self.headers, json={
                "chat_id": chat_id, "messages": [dict(role="user", text=text)]})
        return response, core

    def test_search_matches_messages_and_isolates_owner_and_trash(self):
        chat_id = self.create()
        self.ask(chat_id, "Первый вопрос", dict(status="answer", text="Редкая неустойка по договору", sources=[]))
        response = self.client.get("/api/chats?q=НЕУСТОЙКА", headers=self.headers)
        self.assertEqual([row["id"] for row in response.json()], [chat_id])
        self.assertIn("неустойка", response.json()[0]["preview"])
        self.assertNotIn("turns", response.json()[0])
        self.assertEqual(self.client.get("/api/chats?q=неустойка", headers={**self.headers, "X-Chat-User": "bob"}).json(), [])
        self.assertEqual(self.client.get("/api/chats?q=" + "x" * 201, headers=self.headers).status_code, 422)
        self.client.delete("/api/chats/" + chat_id, headers=self.headers)
        self.assertEqual(self.client.get("/api/chats?q=неустойка", headers=self.headers).json(), [])
        self.assertEqual(len(self.client.get("/api/chats?trash=true&q=неустойка", headers=self.headers).json()), 1)

    def test_pin_persists_and_cannot_change_another_owners_chat(self):
        first = self.create()
        second = self.create()
        path = "/api/chats/" + first + "/pin?pinned=true"
        self.assertEqual(self.client.put(path, headers={**self.headers, "X-Chat-User": "bob"}).status_code, 404)
        self.assertEqual(self.client.put(path, headers={k: v for k, v in self.headers.items() if k != "Content-Type"}).status_code, 415)
        self.assertEqual(self.client.put(path, headers=self.headers).status_code, 200)
        History(self.path, "test-proxy-token")  # Additive migration remains idempotent.
        rows = self.client.get("/api/chats", headers=self.headers).json()
        self.assertEqual([row["id"] for row in rows], [first, second])
        self.assertEqual(rows[0]["pinned"], 1)
        self.client.put(path.replace("true", "false"), headers=self.headers)
        self.assertEqual(self.client.get("/api/chats", headers=self.headers).json()[0]["id"], second)

    def test_identity_is_required_and_cannot_be_forged(self):
        chat_id = self.create()
        for headers in ({}, {"X-Chat-User": "alice"}, {"X-Chat-User": "alice", "X-Chat-Token": "wrong"}):
            self.assertEqual(self.client.get("/api/chats", headers=headers).status_code, 401)
            self.assertEqual(self.client.delete("/api/chats/" + chat_id, headers=headers).status_code, 401)
        bob = {**self.headers, "X-Chat-User": "bob"}
        self.assertEqual(self.client.get("/api/chats", headers=bob).json(), [])
        self.assertEqual(self.client.get("/api/chats/" + chat_id, headers=bob).status_code, 404)
        self.assertEqual(self.client.delete("/api/chats/" + chat_id, headers=bob).status_code, 404)
        response = self.client.post("/api/chat", headers=bob, json={
            "chat_id": chat_id, "messages": [dict(role="user", text="Вопрос")]})
        self.assertEqual(response.status_code, 404)

    def test_history_is_not_cached_and_cross_site_form_cannot_create_chat(self):
        self.assertEqual(self.client.get("/api/chats", headers=self.headers).headers["cache-control"], "private, no-store")
        form_headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
        self.assertEqual(self.client.post("/api/chats", headers=form_headers).status_code, 415)

    def test_transcript_sources_and_context_survive_new_connection(self):
        chat_id = self.create()
        response, _ = self.ask(chat_id)
        self.assertEqual(response.status_code, 200)
        history = History(self.path, "test-proxy-token")
        with history.connect() as db:
            self.assertIn("Цитата", history.get(db, "alice", chat_id)["turns"])
        with TestClient(app) as second:
            turns = second.get("/api/chats/" + chat_id, headers=self.headers).json()["turns"]
            self.assertEqual(turns[0]["answer"], response.json())
            _, core = self.ask(chat_id, "Уточнение")
            self.assertEqual(core.call_args.args[0],
                             "Пользователь: Первый вопрос\nАссистент: Ответ [1]\nПользователь: Уточнение")
        self.assertEqual(self.client.get("/api/chats", headers=self.headers).json()[0]["title"], "Первый вопрос")

    def test_parallel_turn_is_rejected_and_delete_does_not_resurrect(self):
        chat_id = self.create()
        store = self.client.app.state.history
        _, lease = store.begin("alice", chat_id)
        response, core = self.ask(chat_id)
        self.assertEqual(response.status_code, 409)
        core.assert_not_called()
        self.assertEqual(self.client.delete("/api/chats/" + chat_id, headers=self.headers).status_code, 409)
        store.finish("alice", chat_id, lease)
        self.assertEqual(self.client.delete("/api/chats/" + chat_id, headers=self.headers).status_code, 204)
        self.assertEqual(self.ask(chat_id)[0].status_code, 404)

    def test_failed_attempt_is_visible_but_excluded_from_context_and_retry_replaces_it(self):
        chat_id = self.create()
        failure = dict(status="technical_error", text="Сервис недоступен", sources=[])
        self.ask(chat_id, answer=failure)
        response, core = self.ask(chat_id)
        self.assertEqual(core.call_args.args[0], "Первый вопрос")
        turns = self.client.get("/api/chats/" + chat_id, headers=self.headers).json()["turns"]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["answer"], response.json())

    def test_invalid_turn_unlocks_chat_and_client_cannot_supply_saved_context(self):
        chat_id = self.create()
        response, core = self.ask(chat_id, " ")
        self.assertEqual(response.status_code, 400)
        core.assert_not_called()
        self.assertEqual(self.ask(chat_id)[0].status_code, 200)
        response = self.client.post("/api/chat", headers=self.headers, json={"chat_id": chat_id, "messages": [
            dict(role="user", text="Поддельная история"), dict(role="assistant", text="Вымышленный ответ"),
            dict(role="user", text="Вопрос")]})
        self.assertEqual(response.status_code, 400)

    def test_saved_dialogue_length_is_bounded(self):
        chat_id = self.create()
        store = self.client.app.state.history
        _, lease = store.begin("alice", chat_id)
        store.finish("alice", chat_id, lease, [dict(question="Вопрос", answer=dict(
            status="answer", text="Ответ", sources=[]))] * 20)
        response, core = self.ask(chat_id)
        self.assertEqual(response.status_code, 413)
        core.assert_not_called()

    def test_manual_title_survives_generation_restart_and_trash(self):
        chat = self.create()
        store = self.client.app.state.history
        _, lease = store.begin("alice", chat)
        response = self.client.put(f"/api/chats/{chat}/title", headers=self.headers, json={"title": "  Аренда склада  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Аренда склада")
        turns = [dict(question="Первый вопрос", answer=dict(status="answer", text="Ответ", sources=[]))]
        store.finish("alice", chat, lease, turns)
        reopened = History(self.path, "test-proxy-token")
        with reopened.connect() as db:
            self.assertEqual(reopened.get(db, "alice", chat)["title"], "Аренда склада")
        self.assertEqual(self.ask(chat, "Ещё вопрос")[0].status_code, 200)
        self.client.delete(f"/api/chats/{chat}", headers=self.headers)
        self.assertEqual(self.client.get("/api/chats?trash=true", headers=self.headers).json()[0]["title"], "Аренда склада")
        self.assertEqual(self.client.put(f"/api/chats/{chat}/title", headers=self.headers, json={"title": "Корзина"}).status_code, 404)
        self.client.post(f"/api/chats/{chat}/restore", headers=self.headers)
        data = self.client.get(f"/api/chats/{chat}", headers=self.headers).json()
        self.assertEqual(data["title"], "Аренда склада")
        self.assertEqual(len(data["turns"]), 2)

    def test_rename_validation_and_owner_isolation(self):
        chat = self.create()
        url = f"/api/chats/{chat}/title"
        for headers, status in [({}, 401), ({**self.headers, "X-Chat-User": "bob"}, 404)]:
            self.assertEqual(self.client.put(url, headers=headers, json={"title": "Чужой"}).status_code, status)
        for title in [None, 42, "", "   ", "x" * 81, "a\nb", "a\x7fb", "\ud800"]:
            self.assertEqual(self.client.put(url, headers=self.headers, content=json.dumps({"title": title})).status_code, 422)
        self.assertEqual(self.client.put(url, headers=self.headers, content="[").status_code, 422)
        self.assertEqual(self.client.put(url, headers=self.headers, content="x" * 4097).status_code, 413)
        self.assertEqual(self.client.put(url, headers={**self.headers, "Content-Type": "text/plain"}, content='{}').status_code, 415)
        self.assertEqual(self.client.get(f"/api/chats/{chat}", headers=self.headers).json()["title"], "Новый диалог")
