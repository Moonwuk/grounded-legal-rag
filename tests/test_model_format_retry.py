"""A reply that is not a JSON object gets one bounded format retry.

Observed: gpt-oss:120b (1 of 54 calls on the demo) and deepseek-flash (1 of
about 1 300 questions) answered a JSON-only request with plain prose
(«Да. Подписанный оригинал договора передаётся…»). The client raised
invalid_model_response at once, and the question became a technical error.
"""
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_llm import ProxyClient, ProviderError  # noqa: E402
from test_reasoning_budget import VALUE, provider, reply  # noqa: E402

PROSE = 'Да. Оригинал передаётся в отдел за 5 рабочих дней (п. 4.1).'


class FormatRetryTests(unittest.TestCase):
    def complete(self):
        with open(os.devnull, 'w') as sink, patch.object(sys, 'stderr', sink):
            return ProxyClient(time.monotonic() + 20).complete('Fixed policy', {})

    def test_prose_reply_is_retried_once_with_a_format_reminder(self):
        for bad in (PROSE, '[1, 2]', '{"status": "answer"', '"answer"'):
            def script(i, body):
                return 200, reply('stop', bad if i == 0 else json.dumps(VALUE))
            with provider(script) as calls:
                self.assertEqual(self.complete(), VALUE, bad)
            self.assertEqual(len(calls), 2, bad)
            self.assertNotIn('JSON-объект', calls[0]['messages'][0]['content'])
            self.assertIn('JSON-объект', calls[1]['messages'][0]['content'])

    def test_second_invalid_reply_is_a_technical_error(self):
        with provider(lambda i, body: (200, reply('stop', PROSE))) as calls:
            with self.assertRaises(ProviderError) as error:
                self.complete()
        self.assertEqual(str(error.exception), 'invalid_model_response')
        self.assertEqual(len(calls), 2)

    def test_broken_envelope_is_not_retried(self):
        # Not the model's text: the provider envelope itself is malformed.
        with provider(lambda i, body: (200, b'{"choices": []}')) as calls:
            with self.assertRaises(ProviderError) as error:
                self.complete()
        self.assertEqual(str(error.exception), 'invalid_model_response')
        self.assertEqual(len(calls), 1)

    def test_duplicate_keys_still_rejected_after_retry(self):
        dup = '{"status": "answer", "status": "insufficient"}'
        with provider(lambda i, body: (200, reply('stop', dup))) as calls:
            with self.assertRaises(ProviderError):
                self.complete()
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
