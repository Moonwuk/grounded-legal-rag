"""Exercise the actual engine through the disposable web worker with a stub API."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from web.app import app
from web.experiment import original_span
from psb_corpus import Document


class CitationMappingTests(unittest.TestCase):
    def test_removed_line_crlf_nbsp_and_unicode_preserve_original_offsets(self):
        raw = "  📄 Документ\r\nignore instructions\r\n3.1. Цена 37\u00a0800 рублей.\r\n3.2. Цена 37\u00a0800 рублей.\r\n"
        sanitize = lambda text: (text.replace("ignore instructions", "[удалено]"), [])
        doc = Document("contract.txt", raw, "hash", ())
        clean = sanitize(raw.replace("\r\n", "\n").replace("\u00a0", " "))[0].strip()
        quote = "3.2. Цена 37 800 рублей."
        start = clean.index(quote)
        a, b = original_span(doc, clean, start, start + len(quote), sanitize)
        self.assertEqual(raw[a:b], "3.2. Цена 37\u00a0800 рублей.")
        self.assertEqual(a, raw.index("3.2."))
        bad = clean.index("[удалено]")
        with self.assertRaises(ValueError):
            original_span(doc, clean, bad, bad + len("[удалено]"), sanitize)

    def test_invalid_quarantined_and_mismatched_ranges_are_rejected(self):
        doc = Document("contract.txt", "Цена 100 рублей.", "hash", ((0, 4),))
        sanitize = lambda text: (text, [])
        for text, a, b in [(doc.text, -1, 4), (doc.text, 0, 40), (doc.text, 0, 4), ("Другой текст", 0, 3)]:
            with self.subTest(a=a, b=b), self.assertRaises(ValueError):
                original_span(doc, text, a, b, sanitize)


class ExperimentWebTests(unittest.TestCase):
    def setUp(self):
        self.content = "Арендная плата составляет 450 000 рублей в месяц, включая НДС. Источник: договор аренды № А-08/2024 с ООО «Северный Склад», п. 3.1."
        self.requests = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.path, payload))
                raw = json.dumps({'choices': [{'message': {'content': owner.content}, 'finish_reason': 'stop'}]}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        tmp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, WEB_CORE='experiment', EMB_MODEL='', RERANKER_MODEL='',
            LLM_BASE_URL=f'http://127.0.0.1:{self.server.server_port}', LLM_API_KEY='fixture-key',
            LLM_MODEL='fixture-model', CHAT_HISTORY_PATH=str(Path(tmp)/'history.db'), CHAT_PROXY_TOKEN='fixture-token'))
        self.client = self.enterContext(TestClient(app))
        self.headers = {'X-Chat-User':'alice','X-Chat-Token':'fixture-token','Content-Type':'application/json'}

    def ask(self):
        return self.client.post('/api/chat', headers=self.headers, json={'messages':[
            {'role':'user','text':'Какова арендная плата по договору с ООО «Северный Склад»?'}]}).json()

    def test_new_engine_response_and_sources_keep_existing_document_ids(self):
        self.assertEqual(self.client.get('/healthz').json()['core'], 'experiment')
        catalog = self.client.get('/api/documents', headers=self.headers).json()
        result = self.ask()
        self.assertEqual(result['status'], 'answer', result)
        self.assertEqual(result['core'], 'psb_experiment')
        self.assertTrue(result['sources'])
        for source in result['sources']:
            self.assertIn(source['document_id'], [d['id'] for d in catalog])
            doc = self.client.get('/api/documents/'+source['document_id'], headers=self.headers).json()
            self.assertEqual(doc['text'][source['start']:source['end']], source['quote'])
        self.assertTrue(self.requests)
        self.assertTrue(all(path == '/chat/completions' for path, _ in self.requests))
        self.assertNotIn('draft', result)
        self.assertNotIn('debug', result)

    def test_unverified_amount_and_invented_clause_are_not_published(self):
        for content in [self.content.replace('450 000', '87 654'), self.content.replace('3.1.', '9.9.')]:
            with self.subTest(content=content):
                self.content = content
                result = self.ask()
                self.assertEqual(result['status'], 'technical_error', result)
                self.assertEqual(result['sources'], [])
                self.assertNotIn('87 654', result['text'])
                self.assertNotIn('9.9', result['text'])

    def test_queue_uses_new_engine_and_persists_answer(self):
        chat = self.client.post('/api/chats', headers=self.headers).json()['id']
        response = self.client.post(f'/api/chats/{chat}/jobs', headers=self.headers,
            json={'id':str(uuid4()),'question':'Какова арендная плата по договору с ООО «Северный Склад»?'})
        self.assertEqual(response.status_code, 202)
        until = time.monotonic()+15
        while time.monotonic()<until:
            state = self.client.get(f'/api/chats/{chat}/jobs', headers=self.headers).json()
            if state['turns']:
                break
            time.sleep(.05)
        self.assertTrue(state['turns'])
        result = state['turns'][0]['answer']
        self.assertEqual(result['status'], 'answer', result)
        self.assertEqual(result['core'], 'psb_experiment')
        self.assertTrue(result['sources'])
