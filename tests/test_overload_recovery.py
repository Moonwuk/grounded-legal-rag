"""An overloaded proxy must not turn rows into zero-scoring technical stubs.

Archive 24 on the platform: 20.354 at 00:22, right after the daily limit reset,
in 542 of 1100 s; locally the same archive beats archive 12 (34.2) on every set.
A locally simulated row whose calls all failed (429, 5xx, timeouts) kept «Не удалось проверить
ответ из-за технической ошибки» for good, although half of the time was left;
the client gave up after three attempts with 1 and 2 s pauses. Other teams
report score variation, but without platform outputs or logs it does not prove
that identical answers were scored differently or that server load caused it.

Now a failed row is started again after the other rows, at most twice, and a
429 pauses every worker (shared cooldown).
"""
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
import csv
import io
import os
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
import solution  # noqa: E402
from psb_llm import ProviderError, ProxyClient  # noqa: E402
from psb_policy import TECHNICAL  # noqa: E402

GOOD = 'Помещение можно передавать только при письменном согласии владельца (п. 9.1).'


def run_batch(fail_first, rows=4):
    """fail_first: number of first calls (over all rows) that raise as an overloaded proxy."""
    state = {'calls': 0}

    class Client:
        def __init__(self, deadline, position=None):
            self.deadline, self.position = deadline, position

        def complete(self, system, payload):
            state['calls'] += 1
            if state['calls'] <= fail_first:
                raise ProviderError('proxy_unavailable')
            f = next(f for f in payload['evidence'] if f['text'].startswith('9.1.'))
            return {'status': 'answer', 'answer': GOOD, 'source_ids': [f['id']], 'requested_facts': []}

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        with (root / 'questions.csv').open('w', encoding='utf-8', newline='') as h:
            csv.writer(h).writerows([['id', 'question']] + [[f'0{i}', 'Можно ли передавать помещение?'] for i in range(rows)])
        with zipfile.ZipFile(root / 'knowledge-base.zip', 'w') as z:
            z.writestr('terms.txt', '9.1. Помещение можно передавать только при письменном согласии владельца.')
        env = {'DATA_DIR': temp, 'MAX_WORKERS': '1', 'PSB_RUN_SECONDS': '1100'}
        with patch.dict(os.environ, env, clear=True), patch.object(solution, 'ProxyClient', Client), \
                patch.object(solution.Path, 'cwd', return_value=root), redirect_stderr(io.StringIO()):
            solution.main()
        with (root / 'submission.csv').open(encoding='utf-8', newline='') as h:
            return [r['answer'] for r in csv.DictReader(h)], state['calls']


class OverloadRecoveryTests(unittest.TestCase):
    def test_failed_rows_are_answered_later(self):
        # The first two rows fail completely; the proxy then recovers.
        answers, calls = run_batch(fail_first=2)
        self.assertTrue(all(a.startswith(GOOD) for a in answers), answers)
        self.assertNotIn(TECHNICAL, answers)
        self.assertEqual(calls, 2 + 4)

    def test_repeated_failure_is_bounded(self):
        # A proxy that never answers: each row is tried three times, then the
        # technical message stays (it does not claim the base lacks the answer).
        answers, calls = run_batch(fail_first=10 ** 6, rows=3)
        self.assertEqual(answers, [TECHNICAL] * 3)
        self.assertEqual(calls, 3 * 3)


class SharedCooldownTests(unittest.TestCase):
    def tearDown(self):
        ProxyClient.cooldown_until = 0.0

    def test_a_429_pauses_other_workers(self):
        ProxyClient.cooldown_until = time.monotonic() + 7
        with patch.dict(os.environ, {'LLM_BASE_URL': 'https://proxy.invalid', 'LLM_API_KEY': 'k', 'LLM_MODEL': 'm'}), \
                patch('psb_llm.time.sleep', side_effect=lambda s: (_ for _ in ()).throw(RuntimeError(s))):
            client = ProxyClient(time.monotonic() + 60)
            with self.assertRaises(RuntimeError) as slept:
                client.complete('policy', {})
        self.assertGreater(slept.exception.args[0], 6)


if __name__ == '__main__':
    unittest.main()
