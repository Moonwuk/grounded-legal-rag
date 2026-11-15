"""Mixed failures share a finite request budget and the workers' cooldown.

The provider and clock are local fixtures. No live API or credentials are used.
"""
from contextlib import redirect_stderr
import io
from itertools import permutations
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototype"))
from psb_llm import ProviderError, ProxyClient  # noqa: E402

VALUE = {"status": "out_of_scope", "source_ids": [], "answer": ""}


class Clock:
    def __init__(self):
        self.now = 100.0
        self.pauses = []
        self.on_sleep = None

    def sleep(self, seconds):
        self.pauses.append(seconds)
        self.now += seconds
        if self.on_sleep:
            self.on_sleep(seconds)


class Reply(io.BytesIO):
    def __init__(self, kind):
        payload = {
            "choices": [{
                "finish_reason": "length" if kind == "length" else "stop",
                "message": {"content": {
                    "ok": json.dumps(VALUE),
                    "length": '{"status":',
                    "bad_json": "A reply outside the JSON contract.",
                }[kind]},
            }],
        }
        super().__init__(json.dumps(payload).encode())


class MixedProxyRetryTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.clock = Clock()
        ProxyClient.cooldown_until = 0.0
        ProxyClient.effort_rejected = False

    def tearDown(self):
        ProxyClient.cooldown_until = 0.0
        ProxyClient.effort_rejected = False

    def complete(self, script, seconds=60, other_cooldown=0):
        script = iter(script)

        def opened(request, timeout):
            body = json.loads(request.data)
            self.calls.append((self.clock.now, body))
            if len(self.calls) == 1 and other_cooldown:
                # Another worker received Retry-After while this call was in flight.
                ProxyClient.cooldown_until = self.clock.now + other_cooldown
            event = next(script)
            if isinstance(event, int):
                raise HTTPError("https://proxy.invalid", event, "fixture", {"Retry-After": "0"}, None)
            return Reply(event)

        env = {"LLM_BASE_URL": "https://proxy.invalid", "LLM_API_KEY": "test-placeholder",
               "LLM_MODEL": "configured-test-model", "MAX_TOKENS": "1024"}
        with patch.dict(os.environ, env, clear=True), \
                patch("psb_llm.time.monotonic", side_effect=lambda: self.clock.now), \
                patch("psb_llm.time.sleep", side_effect=self.clock.sleep), \
                redirect_stderr(io.StringIO()):
            client = ProxyClient(self.clock.now + seconds)
            client.opener.open = opened
            value = client.complete("Fixed policy", {})
            self.assertEqual(client.calls, 1)
            return value

    def test_truncated_third_response_uses_the_fourth_request(self):
        self.assertEqual(self.complete([503, 503, "length", "ok"]), VALUE)
        self.assertEqual([b["max_tokens"] for _, b in self.calls], [2048, 2048, 2048, 4096])
        self.assertEqual(self.clock.pauses, [2, 5])

    def test_malformed_third_response_uses_the_fourth_request(self):
        self.assertEqual(self.complete([503, 503, "bad_json", "ok"]), VALUE)
        self.assertEqual(len(self.calls), 4)
        self.assertIn("JSON-объект", self.calls[-1][1]["messages"][0]["content"])

    def test_unsupported_effort_on_third_request_can_recover(self):
        for code in (400, 422):
            with self.subTest(code=code):
                self.setUp()
                self.assertEqual(self.complete([503, 503, code, "ok"]), VALUE)
                self.assertIn("reasoning_effort", self.calls[-2][1])
                self.assertNotIn("reasoning_effort", self.calls[-1][1])
                self.assertTrue(ProxyClient.effort_rejected)

    def test_mixed_repairs_recover_in_every_order(self):
        for failures in permutations((503, "length", "bad_json")):
            with self.subTest(failures=failures):
                self.setUp()
                self.assertEqual(self.complete([*failures, "ok"]), VALUE)
                self.assertEqual(len(self.calls), 4)

    def test_each_repair_remains_bounded(self):
        for event, error in (("length", "truncated_model_output"),
                             ("bad_json", "invalid_model_response"), (400, "http_400")):
            with self.subTest(event=event):
                self.setUp()
                with self.assertRaisesRegex(ProviderError, "^" + error + "$"):
                    self.complete([event, event, "ok"])
                self.assertEqual(len(self.calls), 2)
                self.assertFalse(ProxyClient.effort_rejected)

    def test_last_failure_does_not_create_a_fifth_request(self):
        for event, error in (("length", "truncated_model_output"),
                             ("bad_json", "invalid_model_response"),
                             (422, "http_422"), (503, "proxy_unavailable")):
            with self.subTest(event=event):
                self.setUp()
                with self.assertRaisesRegex(ProviderError, "^" + error + "$"):
                    self.complete([503, 503, 503, event, "ok"])
                self.assertEqual(len(self.calls), 4)
                self.assertEqual(self.clock.pauses, [2, 5, 10])

    def test_retry_observes_a_longer_cooldown_from_another_worker(self):
        self.assertEqual(self.complete([503, "ok"], other_cooldown=30), VALUE)
        self.assertEqual([when for when, _ in self.calls], [100, 130])

    def test_cooldown_extension_during_wait_is_observed(self):
        def extend(seconds):
            if seconds == 28:
                ProxyClient.cooldown_until = self.clock.now + 5
        self.clock.on_sleep = extend
        self.assertEqual(self.complete([503, "ok"], other_cooldown=30), VALUE)
        self.assertEqual([when for when, _ in self.calls], [100, 135])

    def test_shared_cooldown_cannot_cross_the_run_deadline(self):
        with self.assertRaisesRegex(ProviderError, "^run_deadline$"):
            self.complete([503, "ok"], seconds=10, other_cooldown=30)
        self.assertEqual(len(self.calls), 1)

    def test_backoff_cannot_cross_the_run_deadline(self):
        with self.assertRaisesRegex(ProviderError, "^run_deadline$"):
            self.complete([503, 503, "length", "ok"], seconds=8)
        self.assertEqual(len(self.calls), 2)


if __name__ == "__main__":
    unittest.main()
