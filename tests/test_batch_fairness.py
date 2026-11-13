"""A difficult early row must not spend the retry budget before later rows start,
and no row may lose a started call to a time share shorter than the call."""
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
import solution
from psb_llm import ProviderError
from psb_policy import TECHNICAL


class BatchFairnessTests(unittest.TestCase):
    def run_batch(self, mode, workers=1):
        events, windows = [], []

        class Client:
            def __init__(self, deadline, position=None):
                self.deadline, self.position, self.calls = deadline, position, 0

            def complete(self, system, payload):
                self.calls += 1
                events.append((self.position, 'verify' if 'candidate' in payload else 'generate'))
                windows.append(self.deadline - time.monotonic())
                if mode == 'failed_retry' and self.position == 0 and self.calls > 2:
                    raise ProviderError('http_503')
                if mode == 'slow' and self.deadline - time.monotonic() < 400:
                    # A call that needs 400 s of the 1100 s run, as ProxyClient
                    # would time out on a slow API.
                    raise ProviderError('run_deadline')
                rejected_row = 2 if mode == 'mixed' else 0
                if 'candidate' in payload:
                    ok = not (mode in {'rejected', 'mixed'} and self.position == rejected_row and self.calls == 2)
                    return {'approved': ok, 'complete': ok, 'status': payload['candidate']['status'],
                            'answer_supported': ok, 'claim_checks': [
                                {'index': i, 'supported': ok, 'applicable': True}
                                for i in range(len(payload['candidate']['claims']))]}
                f = next(f for f in payload['evidence'] if f['text'].startswith('9.1.'))
                partial = mode == 'failed_retry' and self.position == 0
                return {'status': 'partial' if partial else 'answer',
                        'answer': ('Помещение можно передавать только при письменном согласии владельца (п. 9.1).'
                                   if mode == 'restored' and self.calls > 2 else
                                   'Помещение можно передавать.' if mode in {'cosmetic', 'restored', 'mixed'} else ''),
                        'source_ids': [f['id']], 'requested_facts': ['document'] if partial else []}

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (root / 'questions.csv').open('w', encoding='utf-8', newline='') as h:
                csv.writer(h).writerows([['id', 'question']] + [
                    [f'00{i}', 'Можно ли передавать помещение?'] for i in range(3)])
            with zipfile.ZipFile(root / 'knowledge-base.zip', 'w') as z:
                z.writestr('terms.txt', '9.1. Помещение можно передавать только при письменном согласии владельца.')
            env = {'DATA_DIR': temp, 'MAX_WORKERS': str(workers), 'PSB_RUN_SECONDS': '1100'}
            with patch.dict(os.environ, env, clear=True), patch.object(solution, 'ProxyClient', Client), \
                    patch.object(solution.Path, 'cwd', return_value=root), redirect_stderr(io.StringIO()):
                self.assertEqual(solution.main(), 0)
            with (root / 'submission.csv').open(encoding='utf-8', newline='') as h:
                rows = list(csv.DictReader(h))
        return events, windows, rows

    def test_quote_only_answer_retries_its_text_after_all_first_attempts(self):
        # 24-question run on 06a3dda, N16-N18: a verified answer whose text was
        # dropped was published as bare quotations, without «Нет»/«120 часов»;
        # the one retry that restores the text never ran in batch.
        events, _, rows = self.run_batch('cosmetic')
        self.assertEqual([i for i, _ in events], [0, 0, 1, 1, 2, 2, 0, 0, 1, 1, 2, 2])
        self.assertTrue(all('письменном согласии' in row['answer'] for row in rows))

    def test_restored_text_is_published(self):
        _, _, rows = self.run_batch('restored')
        self.assertTrue(all(row['answer'].startswith('Помещение можно передавать только при письменном согласии')
                            for row in rows), rows)

    def test_unresolved_rows_retry_before_quote_only_answers(self):
        events, _, rows = self.run_batch('mixed')
        self.assertEqual([i for i, _ in events][:6], [0, 0, 1, 1, 2, 2])
        self.assertEqual([i for i, _ in events][6:8], [2, 2])
        self.assertTrue(all(row['answer'] != TECHNICAL for row in rows))

    def test_unverified_retry_runs_after_all_first_attempts(self):
        events, windows, rows = self.run_batch('rejected')
        self.assertEqual([i for i, _ in events], [0, 0, 1, 1, 2, 2, 0, 0])
        # Fairness is the order; a started call keeps the whole run window.
        self.assertGreater(min(windows), 1090)
        self.assertTrue(all(row['answer'] != TECHNICAL for row in rows))
        self.assertEqual([row['id'] for row in rows], ['000', '001', '002'])

    def test_slow_api_rows_are_not_cut_by_a_time_share(self):
        # Platform submission f750b281 (score 20.2, 996 s): each row got the
        # remaining time divided by the number of waves, and a call longer than
        # that share became a permanent technical error. Simulated with a 5 s
        # API, 40 rows, 120 s: 0 answers, against 21 before the time share.
        events, windows, rows = self.run_batch('slow')
        self.assertEqual(len(events), 6)
        self.assertTrue(all('письменном согласии' in row['answer'] for row in rows), rows)

    def test_partial_checkpoint_survives_failure_in_deferred_retry(self):
        events, _, rows = self.run_batch('failed_retry')
        self.assertEqual([i for i, _ in events], [0, 0, 1, 1, 2, 2, 0])
        self.assertIn('письменном согласии', rows[0]['answer'])
        self.assertNotEqual(rows[0]['answer'], TECHNICAL)

    def test_parallel_batch_preserves_all_rows(self):
        events, _, rows = self.run_batch('cosmetic', workers=2)
        self.assertEqual(len(events), 12)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all('письменном согласии' in row['answer'] for row in rows))


if __name__ == '__main__':
    unittest.main()
