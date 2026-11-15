"""Regression checks for the public web trust boundary and generation budgets."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from fastapi import HTTPException
from web.app import app


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=str(Path(tmp) / 'history.sqlite3'),
                                     CHAT_PROXY_TOKEN='fixture-token', WEB_REQUESTS_PER_MINUTE='2', WEB_REQUESTS_PER_DAY='3'))
        self.client = self.enterContext(TestClient(app))
        self.client.app.state.queue.close()
        self.headers = {'X-Chat-User': 'alice', 'X-Chat-Token': 'fixture-token'}

    def chat(self):
        response = self.client.post('/api/chats', headers=self.headers, json={})
        self.assertEqual(response.status_code, 201)
        return response.json()['id']

    def submit(self, chat, id_=None):
        return self.client.post(f'/api/chats/{chat}/jobs', headers=self.headers, json={'id': id_ or str(uuid4()), 'question': 'Вопрос'})

    def test_every_api_requires_proxy_identity_when_history_enabled(self):
        for path, method in [('/api/documents', 'get'), ('/api/documents/unknown', 'get'), ('/api/chat', 'post'), ('/api/chats', 'get')]:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, headers={'X-Chat-User': 'alice'})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers['cache-control'], 'private, no-store')
        self.assertEqual(self.client.get('/api/documents', headers=self.headers).status_code, 200)

    def test_browser_origins_and_fetch_metadata_fail_closed(self):
        chat = self.chat()
        for origin in ['https://evil.example', 'null', 'http://testserver.evil.example', 'http://testserver/path', 'http://[']:
            response = self.client.delete(f'/api/chats/{chat}', headers={**self.headers, 'Origin': origin})
            self.assertEqual(response.status_code, 403, origin)
        self.assertEqual(self.client.delete(f'/api/chats/{chat}', headers={**self.headers, 'Sec-Fetch-Site': 'cross-site'}).status_code, 403)
        self.assertEqual(self.client.get(f'/api/chats/{chat}', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/chats/{chat}', headers={**self.headers, 'Origin': 'http://testserver'}).status_code, 204)

    def test_security_headers_on_pages_api_and_errors(self):
        for path in ['/', '/static/app.js', '/api/documents', '/missing']:
            response = self.client.get(path, headers=self.headers)
            self.assertIn("script-src 'self'", response.headers['content-security-policy'])
            self.assertIn("frame-ancestors 'none'", response.headers['content-security-policy'])
            self.assertEqual(response.headers['x-frame-options'], 'DENY')
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')

    def test_budgets_shared_across_dialogues_legacy_api_and_restart(self):
        first, second = self.chat(), self.chat()
        job = str(uuid4())
        self.assertEqual(self.submit(first, job).status_code, 202)
        self.assertEqual(self.submit(first, job).status_code, 202)  # Lost-response retry is free.
        self.assertEqual(self.submit(second).status_code, 202)
        limited = self.submit(first)
        self.assertEqual(limited.status_code, 429)
        self.assertGreater(int(limited.headers['retry-after']), 0)
        with patch('web.app.answer') as model:
            self.assertEqual(self.client.post('/api/chat', headers=self.headers,
                json={'messages': [{'role': 'user', 'text': 'Обход очереди'}]}).status_code, 429)
            model.assert_not_called()
        # Counters are durable and do not disappear with deleted chats.
        store = self.client.app.state.history
        from web.history import History
        reopened = History(store.path, 'fixture-token')
        with self.assertRaises(HTTPException) as rejected:
            reopened.reserve_generation('alice')
        self.assertEqual(rejected.exception.status_code, 429)
        # Another login has a separate budget.
        reopened.reserve_generation('bob')
        with patch.dict(os.environ, WEB_REQUESTS_PER_MINUTE='20'):
            self.assertEqual(self.submit(second).status_code, 202)
            self.assertEqual(self.submit(second).status_code, 429)  # Daily cap, not minute cap.
