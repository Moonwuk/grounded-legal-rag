import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from web.app import app


class DocumentTabsTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=str(Path(tmp) / "history.sqlite3"),
                                     CHAT_PROXY_TOKEN="fixture-token"))
        self.client = self.enterContext(TestClient(app))
        self.headers = {"X-Chat-User": "alice", "X-Chat-Token": "fixture-token"}
        self.ids = [doc["id"] for doc in self.client.get("/api/documents", headers=self.headers).json()]

    def create(self, **changes):
        payload = dict(title="Сделка", document_ids=self.ids[:2])
        return self.client.post("/api/document-tabs", headers=self.headers, json={**payload, **changes})

    def test_collection_persists_across_sessions_and_delete_preserves_corpus(self):
        response = self.create(title="  Сделка  ", document_ids=self.ids[:2] * 2)
        self.assertEqual(response.status_code, 201)
        tab = response.json()
        self.assertEqual(tab["title"], "Сделка")
        self.assertEqual(tab["document_ids"], self.ids[:2])
        with TestClient(app) as second:
            self.assertEqual(second.get("/api/document-tabs", headers=self.headers).json(), [tab])
        updated = self.client.put("/api/document-tabs/" + tab["id"], headers=self.headers,
                                  json={**tab, "title": "Пустая", "document_ids": []})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["document_ids"], [])
        stale = self.client.put("/api/document-tabs/" + tab["id"], headers=self.headers, json=tab)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client.delete("/api/document-tabs/" + tab["id"], headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get("/api/document-tabs", headers=self.headers).json(), [])
        self.assertEqual([doc["id"] for doc in self.client.get("/api/documents", headers=self.headers).json()], self.ids)

    def test_identity_isolation_and_private_cache(self):
        tab = self.create().json()
        for headers in ({}, {**self.headers, "X-Chat-Token": "wrong"}):
            self.assertEqual(self.client.get("/api/document-tabs", headers=headers).status_code, 401)
            self.assertEqual(self.client.post("/api/document-tabs", headers=headers, json=tab).status_code, 401)
            self.assertEqual(self.client.put("/api/document-tabs/" + tab["id"], headers=headers, json=tab).status_code, 401)
            self.assertEqual(self.client.delete("/api/document-tabs/" + tab["id"], headers=headers).status_code, 401)
        bob = {**self.headers, "X-Chat-User": "bob"}
        self.assertEqual(self.client.get("/api/document-tabs", headers=bob).json(), [])
        self.assertEqual(self.client.put("/api/document-tabs/" + tab["id"], headers=bob, json=tab).status_code, 404)
        self.assertEqual(self.client.delete("/api/document-tabs/" + tab["id"], headers=bob).status_code, 404)
        response = self.client.get("/api/document-tabs", headers=self.headers)
        self.assertEqual(response.headers["cache-control"], "private, no-store")

    def test_validation_limits_and_cross_site_forms(self):
        for changes in ({"title": " "}, {"title": "x" * 61}, {"title": "x\nx"},
                        {"document_ids": ["unknown"]}, {"document_ids": self.ids[:1] * 501}):
            self.assertEqual(self.create(**changes).status_code, 422)
        self.assertEqual(self.client.post("/api/document-tabs", headers=self.headers,
                                         data={"title": "form"}).status_code, 415)
        self.assertEqual(self.client.post("/api/document-tabs", headers={**self.headers, "Content-Type": "application/json"},
                                         content="x" * 65537).status_code, 413)
        for i in range(30):
            self.assertEqual(self.create(title=str(i)).status_code, 201)
        self.assertEqual(self.create().status_code, 429)
