"""Optional reranker through the proxy's /rerank endpoint (RERANKER_MODEL).

The reranker reads lexical candidates below the hits and adds the most
relevant ones; it never removes a hit, and any failure keeps lexical search.
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
from psb_llm import ProviderError, RerankClient  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402

# Many weak lexical matches ("срок") push the answering provision below top_k.
DOCS = {f'n{i}.txt': f'Положение {i}. Срок хранения папки {i} составляет {i} дней.\n' for i in range(12)}
DOCS['target.txt'] = 'Статья 71. При неудовлетворительном результате испытания работодатель вправе расторгнуть трудовой договор; срок предупреждения — три дня.\n'
QUESTION = 'Какой срок предупреждения при увольнении из-за неудачного испытания?'


@contextmanager
def provider(mode='good'):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path, body))
            if mode == '500':
                self.send_response(500); self.end_headers(); return
            docs = body['documents']
            order = sorted(range(len(docs)), key=lambda i: -('испытани' in docs[i]))
            results = [dict(index=i, relevance_score=1.0) for i in order]
            if mode == 'bad_index':
                results[0]['index'] = len(docs) + 5
            raw = json.dumps(dict(results=results)).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    env = {'LLM_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1', 'LLM_API_KEY': 'test-placeholder',
           'RERANKER_MODEL': 'configured-reranker'}
    try:
        with patch.dict(os.environ, env):
            yield calls
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


class RerankTests(unittest.TestCase):
    def search(self, mode):
        with corpus(DOCS) as r:
            lexical = [f.document for f in r.search(QUESTION, top_k=2)]
            with provider(mode) as calls, open(os.devnull, 'w') as sink, patch.object(sys, 'stderr', sink):
                r.enable_rerank(RerankClient(time.monotonic() + 20))
                ranked = [f.document for f in r.search(QUESTION, top_k=2)]
            return lexical, ranked, calls

    def test_reranker_rescues_a_lower_candidate_and_keeps_hits(self):
        lexical, ranked, calls = self.search('good')
        self.assertIn('target.txt', ranked)
        self.assertEqual(ranked[:len(lexical)], lexical)
        self.assertEqual(calls[0][0], '/v1/rerank')
        self.assertEqual(calls[0][1]['model'], 'configured-reranker')

    def test_failures_keep_lexical_search(self):
        for mode in ('500', 'bad_index'):
            lexical, ranked, _ = self.search(mode)
            self.assertEqual(sorted(ranked), sorted(lexical), mode)

    def test_without_model_nothing_is_requested(self):
        with provider() as calls, patch.dict(os.environ, {'RERANKER_MODEL': ''}):
            with self.assertRaises(ProviderError):
                RerankClient(time.monotonic() + 5)
        self.assertEqual(calls, [])


class SolutionGateTests(unittest.TestCase):
    """A RERANKER_MODEL set by the platform alone does not enable the reranker."""

    def gate(self, flag):
        import solution
        with corpus(DOCS) as r, provider() as calls, patch.dict(os.environ, {'PSB_RERANK': flag}):
            code = solution.enable_optional_rerank(r, time.monotonic() + 20)
            r.search(QUESTION, top_k=2)
        return code, calls

    def test_model_without_flag_sends_nothing(self):
        for flag in ('', '0', 'yes'):
            code, calls = self.gate(flag)
            self.assertEqual(code, 'rerank_off', flag)
            self.assertEqual(calls, [], flag)

    def test_flag_enables_the_reranker(self):
        code, calls = self.gate('1')
        self.assertEqual(code, 'rerank_enabled')
        self.assertEqual(calls[0][0], '/v1/rerank')

    def test_flag_without_model_does_nothing(self):
        import solution
        with corpus(DOCS) as r, patch.dict(os.environ, {'PSB_RERANK': '1', 'RERANKER_MODEL': ''}):
            self.assertIsNone(solution.enable_optional_rerank(r, time.monotonic() + 5))


if __name__ == '__main__':
    unittest.main()
