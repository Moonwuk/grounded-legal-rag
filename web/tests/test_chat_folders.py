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


class ChatFolderTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.path = str(Path(tmp) / "history.sqlite3")
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=self.path, CHAT_PROXY_TOKEN="fixture-token"))
        self.client = self.enterContext(TestClient(app))
        self.headers = {"X-Chat-User": "alice", "X-Chat-Token": "fixture-token", "Content-Type": "application/json"}

    def folder(self, title="Договоры"):
        response = self.client.post("/api/chat-folders", headers=self.headers, json={"title": title})
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def chat(self, folder_id=None):
        response = self.client.post("/api/chats", headers=self.headers,
                                    params={"folder_id": folder_id} if folder_id else {})
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def move(self, chat, folder, headers=None):
        return self.client.put(f"/api/chats/{chat}/folder", headers=headers or self.headers, json={"folder_id": folder})

    def test_persistence_move_rename_and_folder_delete_preserve_messages(self):
        folder = self.folder()
        chat = self.chat(folder)
        store = self.client.app.state.history
        _, lease = store.begin("alice", chat)
        turns = [{"question": "Вопрос", "answer": {"status": "answer", "text": "Ответ", "sources": []}}]
        store.finish("alice", chat, lease, turns)
        with TestClient(app) as second:
            response = second.get("/api/chats", headers=self.headers)
            self.assertEqual(response.json()[0]["folder_id"], folder)
            self.assertEqual(second.get(f"/api/chats/{chat}", headers=self.headers).json()["turns"], turns)
        self.assertEqual(self.client.put(f"/api/chat-folders/{folder}", headers=self.headers,
                                        json={"title": "Сделки"}).status_code, 200)
        self.assertEqual(self.client.get("/api/chat-folders", headers=self.headers).json()[0]["title"], "Сделки")
        self.assertEqual(self.move(chat, None).status_code, 200)
        self.assertIsNone(self.client.get("/api/chats", headers=self.headers).json()[0]["folder_id"])
        self.assertEqual(self.move(chat, folder).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/chat-folders/{folder}", headers=self.headers).status_code, 204)
        result = self.client.get(f"/api/chats/{chat}", headers=self.headers).json()
        self.assertIsNone(result["folder_id"])
        self.assertEqual(result["turns"], turns)

    def test_ownership_for_every_operation_and_cache(self):
        folder, chat = self.folder(), self.chat()
        bob = {**self.headers, "X-Chat-User": "bob"}
        for headers in ({}, {**self.headers, "X-Chat-Token": "wrong"}):
            self.assertEqual(self.client.get("/api/chat-folders", headers=headers).status_code, 401)
            self.assertEqual(self.client.post("/api/chat-folders", headers=headers, json={"title": "x"}).status_code, 401)
            self.assertEqual(self.client.put(f"/api/chat-folders/{folder}", headers=headers, json={"title": "x"}).status_code, 401)
            self.assertEqual(self.client.delete(f"/api/chat-folders/{folder}", headers=headers).status_code, 401)
            self.assertEqual(self.move(chat, folder, headers={**headers, "irrelevant": "test"}).status_code, 401)
        self.assertEqual(self.client.get("/api/chat-folders", headers=bob).json(), [])
        self.assertEqual(self.client.put(f"/api/chat-folders/{folder}", headers=bob, json={"title": "x"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/chat-folders/{folder}", headers=bob).status_code, 404)
        self.assertEqual(self.client.post("/api/chats", params={"folder_id": folder}, headers=bob).status_code, 404)
        self.assertEqual(self.move(chat, folder, bob).status_code, 404)
        bob_folder = self.client.post("/api/chat-folders", headers=bob, json={"title": "Bob"}).json()["id"]
        self.assertEqual(self.move(chat, bob_folder).status_code, 404)
        self.assertEqual(self.client.get("/api/chat-folders", headers=self.headers).headers["cache-control"], "private, no-store")

    def test_limits_validation_and_deleted_destination(self):
        for title in ["", "  ", "a" * 61, "a\nb"]:
            self.assertEqual(self.client.post("/api/chat-folders", headers=self.headers, json={"title": title}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat-folders", headers={**self.headers, "Content-Type": "text/plain"},
                                         content='{"title":"form"}').status_code, 415)
        self.assertEqual(self.client.post("/api/chat-folders", headers=self.headers, content="x" * 4097).status_code, 413)
        folder, chat = self.folder("Дела"), self.chat()
        self.assertEqual(self.client.post("/api/chat-folders", headers=self.headers, json={"title": " дела "}).status_code, 409)
        self.client.delete(f"/api/chat-folders/{folder}", headers=self.headers)
        self.assertEqual(self.move(chat, folder).status_code, 404)
        self.assertEqual(self.client.post("/api/chats", params={"folder_id": folder}, headers=self.headers).status_code, 404)
        self.assertEqual(len(self.client.get("/api/chats", headers=self.headers).json()), 1)
        for i in range(30):
            self.folder(str(i))
        self.assertEqual(self.client.post("/api/chat-folders", headers=self.headers, json={"title": "31"}).status_code, 429)

    def test_moving_while_answer_finishes_and_chat_delete_cleanup(self):
        folder, chat = self.folder(), self.chat()
        store = self.client.app.state.history
        _, lease = store.begin("alice", chat)
        self.assertEqual(self.move(chat, folder).status_code, 200)
        store.finish("alice", chat, lease, [{"question": "q", "answer": {"status": "answer", "text": "a"}}])
        self.assertEqual(self.client.get(f"/api/chats/{chat}", headers=self.headers).json()["folder_id"], folder)
        self.assertEqual(self.client.delete(f"/api/chats/{chat}", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.delete(f"/api/chats/{chat}/permanent", headers=self.headers).status_code, 204)
        with store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chat_folder_items").fetchone()[0], 0)

    def test_old_database_is_upgraded_without_altering_chats(self):
        legacy = str(Path(self.path).with_name("legacy.sqlite3"))
        turns = json.dumps([{"question": "legacy", "answer": {"text": "saved"}}])
        with sqlite3.connect(legacy) as db:
            db.execute("CREATE TABLE chats(id TEXT PRIMARY KEY, owner TEXT, title TEXT, updated REAL, turns TEXT, busy_until REAL)")
            db.execute("INSERT INTO chats VALUES ('old', 'alice', 'Old', 1, ?, 0)", (turns,))
        history = History(legacy, "fixture-token")
        History(legacy, "fixture-token")  # Startup migration is repeatable.
        with history.connect() as db:
            self.assertEqual(history.get(db, "alice", "old")["turns"], turns)
            self.assertEqual(db.execute("SELECT count(*) FROM chat_folder_items").fetchone()[0], 0)
