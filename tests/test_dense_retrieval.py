"""Optional dense candidates through the proxy's /embeddings endpoint.

The stub embeds by concept, not by words: a question worded differently from
the provision shares no rare token with it, so lexical search alone ranks it
below other provisions.
"""
import json
import os
import sys
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_llm import EmbeddingClient, ProviderError  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402

CONCEPTS = [('увол', 'расторж', 'прекращ'), ('аренд', 'помещ'), ('постав', 'товар'), ('отпуск',), ('налог', 'ндс')]
DOCS = {
    'a.txt': 'Статья 71. Результат испытания\nПри неудовлетворительном результате испытания работодатель имеет право до истечения срока расторгнуть трудовой договор, предупредив работника не позднее чем за три дня.\n',
    'b.txt': 'ДОГОВОР АРЕНДЫ № А-1/2031\n3.1. Плата за помещение составляет 100 000 рублей в месяц.\n',
    'c.txt': 'ДОГОВОР ПОСТАВКИ № П-2/2031\n4.1. Срок поставки товара составляет 10 рабочих дней.\n',
    'd.txt': 'Статья 115. Продолжительность отпуска\nЕжегодный основной оплачиваемый отпуск составляет 28 календарных дней. Сотрудник может обратиться к работодателю.\n',
}
QUESTION = 'Можно ли уволить новичка, который не справился в первые месяцы?'


def vector(text):
    low = text.casefold()
    v = [float(sum(low.count(w) for w in words)) for words in CONCEPTS] + [0.05] * 11
    return v


@contextmanager
def provider(mode='good'):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body)
            if mode == '500' or (mode == 'query_fails' and len(calls) > 1):
                self.send_response(500); self.end_headers(); return
            data = [dict(index=i, embedding=vector(t)) for i, t in enumerate(body['input'])]
            if mode == 'short':
                data = data[:-1]
            if mode == 'nan':
                data[0]['embedding'][0] = 'NaN'
            raw = json.dumps(dict(data=data)).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    env = {'LLM_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1', 'LLM_API_KEY': 'test-placeholder',
           'EMB_MODEL': 'configured-embedding-model'}
    try:
        with patch.dict(os.environ, env):
            yield calls
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


class DenseRetrievalTests(unittest.TestCase):
    def search(self, mode=None, question=QUESTION):
        with corpus(DOCS) as r:
            lexical = [f.document for f in r.search(question, top_k=1)]
            if mode is None:
                return lexical, None, []
            with provider(mode) as calls, open(os.devnull, 'w') as sink, patch.object(sys, 'stderr', sink):
                status = r.enable_dense(EmbeddingClient(time.monotonic() + 20), time.monotonic() + 20)
                hybrid = [f.document for f in r.search(question, top_k=1)]
            return lexical, (status, hybrid), calls

    def test_dense_candidate_finds_a_differently_worded_provision(self):
        lexical, (status, hybrid), calls = self.search('good')
        self.assertEqual(status, 'dense_enabled')
        self.assertNotIn('a.txt', lexical)
        self.assertIn('a.txt', hybrid)
        # Lexical hits keep their place; dense ones are appended.
        self.assertEqual(hybrid[:len(lexical)], lexical)
        self.assertEqual(calls[0]['model'], 'configured-embedding-model')

    def test_index_failures_keep_lexical_search_unchanged(self):
        for mode, code in (('500', 'dense_disabled:embedding_http_500'), ('short', 'dense_disabled:invalid_embedding_response'),
                           ('nan', 'dense_disabled:invalid_embedding_response')):
            lexical, (status, hybrid), _ = self.search(mode)
            self.assertEqual(status, code, mode)
            self.assertEqual(hybrid, lexical, mode)

    def test_query_failure_falls_back_to_lexical(self):
        lexical, (status, hybrid), _ = self.search('query_fails')
        self.assertEqual(status, 'dense_enabled')
        self.assertEqual(hybrid, lexical)

    def test_without_embedding_model_nothing_is_requested(self):
        with provider() as calls, patch.dict(os.environ, {'EMB_MODEL': ''}):
            with self.assertRaises(ProviderError) as error:
                EmbeddingClient(time.monotonic() + 5)
        self.assertEqual(str(error.exception), 'embedding_not_configured')
        self.assertEqual(calls, [])

    def test_index_deadline_disables_dense(self):
        with corpus(DOCS) as r, provider() as calls:
            status = r.enable_dense(EmbeddingClient(time.monotonic() + 20), time.monotonic() - 1)
        self.assertEqual(status, 'dense_disabled:embedding_deadline')
        self.assertEqual(calls, [])
        self.assertIsNone(r.vectors)


    def test_slow_provider_is_dropped_after_the_first_chunk(self):
        # Local CPU bge-m3 took 291 s for 1113 fragments: a slow provider must not
        # consume the whole indexing budget before lexical search takes over.
        import psb_llm
        many = {f'x{i}.txt': f'Положение {i}. ' + 'Текст о поставке товара. ' * 3 for i in range(1000)}
        original = psb_llm.EmbeddingClient.embed
        def slow(self, texts, deadline=None):
            time.sleep(0.6)
            return original(self, texts, deadline)
        with corpus(many) as r, provider() as calls, patch.object(psb_llm.EmbeddingClient, 'embed', slow):
            status = r.enable_dense(EmbeddingClient(time.monotonic() + 20), time.monotonic() + 2.5)
        self.assertEqual(status, 'dense_disabled:embedding_too_slow')
        self.assertIsNone(r.vectors)
        self.assertLessEqual(sum(len(c['input']) for c in calls), 128)

if __name__ == '__main__':
    unittest.main()
