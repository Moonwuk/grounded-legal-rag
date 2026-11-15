import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app


class ChatTrashTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=str(Path(tmp) / "history.sqlite3"),
                                     CHAT_PROXY_TOKEN="fixture-token"))
        self.client = self.enterContext(TestClient(app))
        self.headers = {"X-Chat-User": "alice", "X-Chat-Token": "fixture-token", "Content-Type": "application/json"}

    def create(self, folder=None):
        response = self.client.post("/api/chats", headers=self.headers, params={"folder_id": folder} if folder else {})
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def trash(self, chat):
        self.assertEqual(self.client.delete(f"/api/chats/{chat}", headers=self.headers).status_code, 204)

    def restore(self, chat):
        return self.client.post(f"/api/chats/{chat}/restore", headers=self.headers)

    def test_round_trip_keeps_transcript_sources_and_folder_across_sessions(self):
        folder = self.client.post("/api/chat-folders", headers=self.headers, json={"title": "Дела"}).json()["id"]
        chat = self.create(folder)
        answer = {"status": "answer", "text": "Ответ [1]", "sources": [{"document_id": "source", "quote": "Цитата"}]}
        store = self.client.app.state.history
        turns, lease = store.begin("alice", chat)
        store.finish("alice", chat, lease, [{"question": "Вопрос", "answer": answer}])
        original = self.client.get(f"/api/chats/{chat}", headers=self.headers).json()
        self.trash(chat)
        self.assertEqual(self.client.get("/api/chats", headers=self.headers).json(), [])
        with TestClient(app) as second:
            trash = second.get("/api/chats?trash=true", headers=self.headers)
            self.assertEqual(trash.headers["cache-control"], "private, no-store")
            self.assertEqual(trash.json()[0]["id"], chat)
            self.assertGreater(trash.json()[0]["deleted_at"], 0)
        self.assertEqual(self.client.get(f"/api/chats/{chat}", headers=self.headers).status_code, 404)
        with patch("web.app.answer") as model:
            response = self.client.post("/api/chat", headers=self.headers, json={
                "chat_id": chat, "messages": [{"role": "user", "text": "Продолжить"}]})
            self.assertEqual(response.status_code, 404)
            model.assert_not_called()
        self.assertEqual(self.client.put(f"/api/chats/{chat}/folder", headers=self.headers,
                                        json={"folder_id": None}).status_code, 404)
        self.assertEqual(self.restore(chat).status_code, 204)
        self.assertEqual(self.client.get(f"/api/chats/{chat}", headers=self.headers).json(), original)
        self.assertEqual(self.client.get("/api/chats?trash=true", headers=self.headers).json(), [])

    def test_restore_after_folder_deletion_and_permanent_delete_requires_trash(self):
        folder = self.client.post("/api/chat-folders", headers=self.headers, json={"title": "Дела"}).json()["id"]
        chat = self.create(folder)
        self.assertEqual(self.client.delete(f"/api/chats/{chat}/permanent", headers=self.headers).status_code, 409)
        self.trash(chat)
        self.client.delete(f"/api/chat-folders/{folder}", headers=self.headers)
        self.assertEqual(self.restore(chat).status_code, 204)
        self.assertIsNone(self.client.get(f"/api/chats/{chat}", headers=self.headers).json()["folder_id"])
        self.trash(chat)
        self.assertEqual(self.client.delete(f"/api/chats/{chat}/permanent", headers=self.headers).status_code, 204)
        self.assertEqual(self.restore(chat).status_code, 404)
        with self.client.app.state.history.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_trash").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM chats").fetchone()[0], 0)

    def test_owner_auth_and_non_json_restore(self):
        chat = self.create()
        self.trash(chat)
        bob = {**self.headers, "X-Chat-User": "bob"}
        self.assertEqual(self.client.get("/api/chats?trash=true", headers=bob).json(), [])
        for headers, status in [(bob, 404), ({}, 401), ({**self.headers, "X-Chat-Token": "wrong"}, 401)]:
            self.assertEqual(self.client.post(f"/api/chats/{chat}/restore", headers=headers).status_code, status)
            self.assertEqual(self.client.delete(f"/api/chats/{chat}/permanent", headers=headers).status_code, status)
        self.assertEqual(self.client.post(f"/api/chats/{chat}/restore", headers={**self.headers, "Content-Type": "text/plain"}).status_code, 415)

    def test_active_and_trash_limits_do_not_silently_evict_chats(self):
        chat = self.create()
        self.trash(chat)
        store = self.client.app.state.history
        with store.connect() as db:
            db.executemany("INSERT INTO chats(id,owner,title,updated) VALUES (?, 'alice', 'fixture', 0)",
                           [(f"active-{i}",) for i in range(100)])
        self.assertEqual(self.restore(chat).status_code, 429)
        self.assertEqual(self.client.post("/api/chats", headers=self.headers).status_code, 429)
        self.trash("active-0")
        self.assertEqual(self.restore(chat).status_code, 204)
        with store.connect() as db:
            db.executemany("INSERT INTO chat_trash(chat_id,deleted) VALUES (?, 1)", [(f"active-{i}",) for i in range(1, 100)])
        self.assertEqual(self.client.delete(f"/api/chats/{chat}", headers=self.headers).status_code, 429)
        self.assertEqual(len(self.client.get("/api/chats?trash=true", headers=self.headers).json()), 100)
        self.assertEqual(self.client.get(f"/api/chats/{chat}", headers=self.headers).status_code, 200)

    def test_busy_and_late_completion_cannot_change_trashed_transcript(self):
        chat = self.create()
        store = self.client.app.state.history
        _, lease = store.begin("alice", chat)
        self.assertEqual(self.client.delete(f"/api/chats/{chat}", headers=self.headers).status_code, 409)
        expired = time.time() - 1
        with store.connect() as db:
            db.execute("UPDATE chats SET busy_until=? WHERE id=?", (expired, chat))
        self.trash(chat)
        store.finish("alice", chat, expired, [{"question": "Late", "answer": {"text": "Late"}}])
        self.assertEqual(self.restore(chat).status_code, 204)
        self.assertEqual(self.client.get(f"/api/chats/{chat}", headers=self.headers).json()["turns"], [])
