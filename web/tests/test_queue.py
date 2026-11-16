import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from web.app import app
from web.queue import QueueManager


class QueueTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, CHAT_HISTORY_PATH=str(Path(tmp) / 'history.sqlite3'), CHAT_PROXY_TOKEN='fixture-token'))
        self.client = self.enterContext(TestClient(app))
        self.client.app.state.queue.close()
        self.headers = {'X-Chat-User': 'alice', 'X-Chat-Token': 'fixture-token', 'Content-Type': 'application/json'}
        self.chat = self.client.post('/api/chats', headers=self.headers).json()['id']
        self.release = Event()
        self.started = Event()
        self.calls = []
        self.manager = QueueManager(self.client.app.state.history, self.client.app.state, 2, self.runner)
        self.addCleanup(self.manager.close)

    def runner(self, question, latest, state, cancelled):
        self.calls.append((question, latest))
        self.started.set()
        while not self.release.wait(.01):
            if cancelled():
                return dict(status='cancelled', text='Остановлено', sources=[])
        return dict(status='answer', text='Ответ: ' + latest, sources=[])

    def submit(self, text, chat=None, job=None, headers=None):
        return self.client.post('/api/chats/' + (chat or self.chat) + '/jobs', headers=headers or self.headers,
                                json={'id': job or str(uuid4()), 'question': text})

    def state(self):
        return self.client.get(f'/api/chats/{self.chat}/jobs', headers=self.headers).json()

    def until(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail('Queue condition did not complete')

    def test_fifo_uses_previous_answers_and_idempotent_submission(self):
        first = str(uuid4())
        self.assertEqual(self.submit('Первый', job=first).status_code, 202)
        self.assertEqual(self.submit('Первый', job=first).status_code, 202)
        self.assertEqual(self.submit('Другой', job=first).status_code, 409)
        self.submit('Второй')
        self.manager.start()
        self.assertTrue(self.started.wait(3))
        self.assertEqual(len(self.calls), 1)
        self.release.set()
        self.until(lambda: len(self.state()['turns']) == 2)
        self.assertEqual([turn['question'] for turn in self.state()['turns']], ['Первый', 'Второй'])
        self.assertIn('Ассистент: Ответ: Первый', self.calls[1][0])
        self.assertEqual(self.calls[1][1], 'Второй')

    def test_rename_during_generation_survives_completion(self):
        self.submit('Исходный вопрос')
        self.manager.start()
        self.assertTrue(self.started.wait(3))
        response = self.client.put(f'/api/chats/{self.chat}/title', headers=self.headers, json={'title': 'Мои договоры'})
        self.assertEqual(response.status_code, 200)
        self.release.set()
        self.until(lambda: len(self.state()['turns']) == 1)
        self.assertEqual(self.state()['title'], 'Мои договоры')

    def test_reorder_waiting_questions_preserves_active_and_context(self):
        first = self.submit('Активный').json()['id']
        self.manager.start()
        self.assertTrue(self.started.wait(3))
        second = self.submit('Второй').json()['id']
        third = self.submit('Третий').json()['id']
        prefix = f'/api/chats/{self.chat}/jobs/'
        move = lambda id_, direction, headers=self.headers: self.client.post(prefix + id_ + '/move/' + direction, headers=headers)
        self.assertEqual(move(first, 'up').status_code, 409)
        self.assertEqual(move(third, 'up', {}).status_code, 401)
        self.assertEqual(move(third, 'up', {**self.headers, 'X-Chat-User': 'bob'}).status_code, 404)
        self.assertEqual(move(third, 'up', {**self.headers, 'Content-Type': 'text/plain'}).status_code, 415)
        self.assertEqual(move(third, 'sideways').status_code, 422)
        self.assertEqual(move(str(uuid4()), 'up').status_code, 404)
        self.assertEqual(move(third, 'up').status_code, 204)
        self.assertEqual([j['id'] for j in self.state()['jobs'] if j['status'] == 'queued'], [third, second])
        self.assertEqual(move(third, 'down').status_code, 204)
        self.assertEqual([j['id'] for j in self.state()['jobs'] if j['status'] == 'queued'], [second, third])
        self.assertEqual(move(second, 'up').status_code, 204)
        self.assertEqual(move(third, 'up').status_code, 204)
        self.release.set()
        self.until(lambda: len(self.state()['turns']) == 3)
        self.assertEqual([t['question'] for t in self.state()['turns']], ['Активный', 'Третий', 'Второй'])
        self.assertIn('Ассистент: Ответ: Третий', self.calls[2][0])

    def test_stop_pauses_queue_removes_waiting_and_excludes_cancelled_context(self):
        first = self.submit('Первый').json()['id']
        removed = self.submit('Убрать').json()['id']
        self.submit('После остановки')
        self.manager.start()
        self.assertTrue(self.started.wait(3))
        self.assertEqual(self.client.delete(f'/api/chats/{self.chat}/jobs/{removed}', headers=self.headers).status_code, 204)
        self.assertEqual(self.client.delete(f'/api/chats/{self.chat}/jobs/{first}', headers=self.headers).status_code, 204)
        self.until(lambda: self.state()['turns'] and self.state()['turns'][0]['answer']['status'] == 'cancelled')
        state = self.state()
        self.assertTrue(state['paused'])
        self.assertEqual([job['question'] for job in state['jobs']], ['После остановки'])
        self.assertEqual(len(self.calls), 1)
        self.release.set()
        self.client.post(f'/api/chats/{self.chat}/jobs/resume', headers=self.headers)
        self.until(lambda: len(self.state()['turns']) == 2)
        self.assertEqual(self.calls[-1][0], 'После остановки')

    def test_identity_limits_trash_and_legacy_cannot_bypass_queue(self):
        first = self.submit('Первый').json()['id']
        for headers in ({'X-Chat-User': 'bob', 'X-Chat-Token': 'fixture-token'}, {}):
            expected = 404 if headers else 401
            self.assertEqual(self.client.get(f'/api/chats/{self.chat}/jobs', headers=headers).status_code, expected)
            self.assertEqual(self.client.delete(f'/api/chats/{self.chat}/jobs/{first}', headers=headers).status_code, expected)
            self.assertEqual(self.submit('Чужой', headers={**headers, 'Content-Type': 'application/json'}).status_code, expected)
        for n in range(4):
            self.assertEqual(self.submit(str(n)).status_code, 202)
        self.assertEqual(self.submit('Шестой').status_code, 429)
        self.assertEqual(self.client.delete(f'/api/chats/{self.chat}', headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post('/api/chat', headers=self.headers, json={'chat_id': self.chat,
            'messages': [{'role': 'user', 'text': 'Обход'}]}).status_code, 409)
        self.assertEqual(self.client.post(f'/api/chats/{self.chat}/jobs/resume', headers={**self.headers, 'Content-Type': 'text/plain'}).status_code, 415)
        self.assertEqual(self.client.get(f'/api/chats/{self.chat}/jobs', headers=self.headers).headers['cache-control'], 'private, no-store')

    def test_expired_worker_pauses_surviving_queue_and_does_not_replay(self):
        self.submit('Прерванный')
        self.submit('Ждущий')
        job = self.manager.claim()
        with self.manager.history.connect() as db:
            db.execute('UPDATE chat_jobs SET lease_until=0 WHERE id=?', (job['id'],))
        self.assertIsNone(self.manager.claim())
        state = self.state()
        self.assertTrue(state['paused'])
        self.assertEqual(state['turns'][0]['answer']['status'], 'technical_error')
        self.assertEqual(state['jobs'][0]['question'], 'Ждущий')
        self.assertEqual(self.calls, [])

    def test_retry_is_inserted_before_dependents_and_replaces_failed_turn(self):
        self.submit('Первый')
        self.submit('Зависимый')
        job = self.manager.claim()
        with self.manager.history.connect() as db:
            self.manager.finish(db, job, dict(status='technical_error', text='Сбой', sources=[]))
        self.assertTrue(self.state()['paused'])
        self.submit('Первый')
        self.assertEqual([job['question'] for job in self.state()['jobs']], ['Первый', 'Зависимый'])
        self.release.set()
        self.client.post(f'/api/chats/{self.chat}/jobs/resume', headers=self.headers)
        self.manager.start()
        self.until(lambda: len(self.state()['turns']) == 2 and not self.state()['jobs'])
        self.assertEqual([turn['question'] for turn in self.state()['turns']], ['Первый', 'Зависимый'])
        self.assertIn('Ассистент: Ответ: Первый', self.calls[1][0])

    def test_retry_credit_cannot_exceed_the_turn_limit(self):
        turns = [{'question': str(n), 'answer': {'status': 'answer', 'text': 'a'}} for n in range(19)]
        turns.append({'question': 'Повтор', 'answer': {'status': 'technical_error', 'text': 'error'}})
        with self.manager.history.connect() as db:
            db.execute('UPDATE chats SET turns=? WHERE id=?', (json.dumps(turns), self.chat))
        self.assertEqual(self.submit('Повтор').status_code, 202)
        self.assertEqual(self.submit('Повтор').status_code, 413)
        self.assertEqual(self.submit('Новый').status_code, 413)

    def test_worker_failure_pauses_and_independent_chats_can_run(self):
        other = self.client.post('/api/chats', headers=self.headers).json()['id']
        self.submit('Первый')
        self.submit('Другой диалог', chat=other)
        self.manager.start()
        self.until(lambda: len(self.calls) == 2)
        self.release.set()
        self.until(lambda: len(self.state()['turns']) == 1)
        self.assertEqual({call[0] for call in self.calls}, {'Первый', 'Другой диалог'})


class ProcessCancellationTests(unittest.TestCase):
    def test_running_provider_process_can_be_cancelled(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from web.generation import run_generation
        connected, release, cancel = Event(), Event(), Event()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                connected.set()
                release.wait(8)
                try:
                    self.send_response(503); self.end_headers()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.dict(os.environ, LLM_BASE_URL=f'http://127.0.0.1:{server.server_port}',
                            LLM_API_KEY='fixture-key', LLM_MODEL='fixture-model'), TestClient(app) as client:
                result = []
                worker = Thread(target=lambda: result.append(run_generation('Арендная плата Северный Склад',
                    'Арендная плата Северный Склад', client.app.state, cancel.is_set)))
                worker.start()
                self.assertTrue(connected.wait(6), 'Provider was not called')
                started = time.monotonic()
                cancel.set()
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive())
                self.assertLess(time.monotonic() - started, 3)
                self.assertEqual(result[0]['status'], 'cancelled')
        finally:
            cancel.set(); release.set(); server.shutdown(); server.server_close()

    def test_isolated_worker_returns_verified_answer_and_exact_sources(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from web.generation import run_generation
        from test_app import LocalModel
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                payload = json.loads(request['messages'][1]['content'])
                result = LocalModel().complete(request['messages'][0]['content'], payload)
                raw = json.dumps({'choices': [{'message': {'content': json.dumps(result)}, 'finish_reason': 'stop'}]}).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with patch.dict(os.environ, LLM_BASE_URL=f'http://127.0.0.1:{server.server_port}',
                            LLM_API_KEY='fixture-key', LLM_MODEL='fixture-model', WEB_CORE='prototype'), TestClient(app) as client:
                result = run_generation('Арендная плата Северный Склад', 'Арендная плата Северный Склад', client.app.state, lambda: False)
                self.assertEqual(result['status'], 'answer')
                self.assertIn('450 000', result['text'])
                for source in result['sources']:
                    document = client.get('/api/documents/' + source['document_id']).json()
                    self.assertEqual(document['text'][source['start']:source['end']], source['quote'])
        finally:
            server.shutdown(); server.server_close()
