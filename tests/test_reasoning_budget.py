"""Reasoning effort and the token budget of the configured provider.

Matrix on the demo (deepseek-flash, MAX_TOKENS 1024/2048): truncated replies had
reasoning_tokens equal to max_tokens, mostly in verification; the retry that only
asked for a shorter JSON was truncated again and became a technical error.
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
from psb_llm import ProxyClient, ProviderError  # noqa: E402

VALUE = {'status': 'out_of_scope', 'claims': [], 'missing': [], 'clarification': ''}


def reply(finish, content, reasoning=None, budget=None):
    body = {'choices': [{'finish_reason': finish, 'message': {'content': content}}]}
    if reasoning is not None:
        body['usage'] = {'completion_tokens': budget, 'completion_tokens_details': {'reasoning_tokens': reasoning}}
    return json.dumps(body, ensure_ascii=False).encode()


@contextmanager
def provider(script):
    """script(call_index, body) -> (http_status, bytes)."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            calls.append(body)
            status, data = script(len(calls) - 1, body)
            self.send_response(status)
            self.send_header('Retry-After', '0')
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {'LLM_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1', 'LLM_API_KEY': 'test-placeholder',
           'LLM_MODEL': 'configured-test-model', 'MAX_TOKENS': '1000'}
    try:
        with patch.dict(os.environ, env):
            os.environ.pop('LLM_REASONING_EFFORT', None)
            yield calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ReasoningBudgetTests(unittest.TestCase):
    def setUp(self):
        ProxyClient.effort_rejected = False

    def tearDown(self):
        ProxyClient.effort_rejected = False

    def complete(self):
        with open(os.devnull, 'w') as sink, patch.object(sys, 'stderr', sink):
            return ProxyClient(time.monotonic() + 20).complete('Fixed policy', {})

    def test_reasoning_that_used_the_budget_is_retried_one_level_lower(self):
        def script(i, body):
            if i == 0:
                return 200, reply('length', '', reasoning=1000, budget=1000)
            return 200, reply('stop', json.dumps(VALUE))
        with provider(script) as calls:
            self.assertEqual(self.complete()['status'], 'out_of_scope')
        self.assertEqual([c.get('reasoning_effort') for c in calls], ['low', 'none'])
        self.assertEqual(calls[0]['max_tokens'], calls[1]['max_tokens'])

    def test_each_configured_level_steps_down(self):
        for configured, expected in (('max', 'low'), ('high', 'low'), ('low', 'none')):
            def script(i, body):
                return (200, reply('length', '', reasoning=990, budget=1000) if i == 0
                        else reply('stop', json.dumps(VALUE)))
            with provider(script) as calls, patch.dict(os.environ, {'LLM_REASONING_EFFORT': configured}):
                self.complete()
            self.assertEqual([c['reasoning_effort'] for c in calls], [configured, expected], configured)

    def test_without_usage_details_a_short_visible_text_means_hidden_reasoning(self):
        def script(i, body):
            return 200, (reply('length', '{"status":') if i == 0 else reply('stop', json.dumps(VALUE)))
        with provider(script) as calls:
            self.complete()
        self.assertEqual([c['reasoning_effort'] for c in calls], ['low', 'none'])

    def test_a_long_visible_answer_keeps_the_level(self):
        # The answer itself, not the reasoning, used the budget.
        def script(i, body):
            return 200, (reply('length', '{"text":"' + 'а' * 1200, reasoning=100, budget=1000) if i == 0
                         else reply('stop', json.dumps(VALUE)))
        with provider(script) as calls:
            self.complete()
        self.assertEqual([c['reasoning_effort'] for c in calls], ['low', 'low'])
        self.assertIn('Повтор после обрезки', calls[1]['messages'][0]['content'])

    def test_still_truncated_after_the_lower_level_is_a_technical_error(self):
        with provider(lambda i, body: (200, reply('length', '', reasoning=1000, budget=1000))) as calls:
            with self.assertRaises(ProviderError) as error:
                self.complete()
        self.assertEqual(str(error.exception), 'truncated_model_output')
        self.assertEqual(len(calls), 2)

    def test_default_sends_low_and_default_keyword_omits_the_parameter(self):
        with provider(lambda i, body: (200, reply('stop', json.dumps(VALUE)))) as calls:
            self.complete()
            with patch.dict(os.environ, {'LLM_REASONING_EFFORT': 'default'}):
                self.complete()
        self.assertEqual(calls[0]['reasoning_effort'], 'low')
        self.assertNotIn('reasoning_effort', calls[1])

    def test_unknown_level_is_a_configuration_error(self):
        with provider(lambda i, body: (200, reply('stop', json.dumps(VALUE)))) as calls:
            with patch.dict(os.environ, {'LLM_REASONING_EFFORT': 'medium'}), self.assertRaises(ProviderError):
                self.complete()
        self.assertEqual(calls, [])

    def test_provider_that_rejects_the_parameter_is_used_without_it_for_the_run(self):
        def script(i, body):
            return (400, b'{}') if 'reasoning_effort' in body else (200, reply('stop', json.dumps(VALUE)))
        with provider(script) as calls:
            self.assertEqual(self.complete()['status'], 'out_of_scope')
            self.complete()
        self.assertEqual(['reasoning_effort' in c for c in calls], [True, False, False])

    def test_other_bad_request_is_reported_not_hidden(self):
        with provider(lambda i, body: (400, b'{}')) as calls:
            with self.assertRaises(ProviderError) as error:
                self.complete()
        self.assertEqual(str(error.exception), 'http_400')
        self.assertEqual(['reasoning_effort' in c for c in calls], [True, False])
        # A bad request of another cause does not disable the parameter for the run.
        self.assertFalse(ProxyClient.effort_rejected)

    def test_truncation_does_not_reintroduce_a_rejected_parameter(self):
        ProxyClient.effort_rejected = True
        def script(i, body):
            return 200, (reply('length', '', reasoning=1000, budget=1000) if i == 0 else reply('stop', json.dumps(VALUE)))
        with provider(script) as calls:
            self.complete()
        self.assertEqual(['reasoning_effort' in c for c in calls], [False, False])


if __name__ == '__main__':
    unittest.main()
