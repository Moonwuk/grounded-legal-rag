import os
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
