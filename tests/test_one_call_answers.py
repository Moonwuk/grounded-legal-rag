"""One model call per answer; the programmatic checks decide what is published.

Platform runs: every version with a verifier call (2-5 model calls per
question) scored 20-24 and ended on the 1100 s run deadline; the same runtime
with one call per question (archive 12) scored 34.2 in 507 s. Rows the deadline
did not reach were technical stubs. The batch now generates once per answer;
a text the checks reject keeps the provisions and gets one more generation,
deferred until every row has its first answer.
"""
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
import csv
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
import solution  # noqa: E402
from psb_policy import answer_structured  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

LEASE = {'Договор аренды К-4-2033 Опора.txt': 'Договор аренды № К-4/2033\n2.1. Арендная плата составляет 380 000 рублей в месяц.\n'
         '2.3. Пени за просрочку — 0,2% от суммы долга за каждый день.\n'
         '4.2. Арендатор не вправе сдавать помещение в субаренду без письменного согласия арендодателя.\n'}


def answer(clause, text):
    def model(payload):
        fid = next(e['id'] for e in payload['evidence'] if e['text'].startswith(clause))
        return {'status': 'answer', 'answer': text, 'source_ids': [fid], 'requested_facts': [], 'issue': ''}
    return model


def one_call(question, responses, files=LEASE):
    log = io.StringIO()
    with corpus(files) as r:
        model = ScriptedModel(responses)
        with redirect_stderr(log):
            result = answer_structured(question, r, model, verify=False)
    events = [json.loads(line) for line in log.getvalue().splitlines() if line.startswith('{"event": "policy_one_call"')]
    return result, model, events


class OneCallAnswerTests(unittest.TestCase):
    def test_checked_text_is_published_after_one_call(self):
        text = 'Арендная плата составляет 380 000 рублей в месяц (п. 2.1).'
        result, model, events = one_call('Какая арендная плата по К-4/2033?', [answer('2.1.', text)])
        self.assertEqual(len(model.calls), 1)
        self.assertNotIn('candidate', model.calls[0][1])
        self.assertEqual(result['status'], 'answer')
        self.assertTrue(result['text'].startswith(text), result['text'])
        self.assertEqual(events[-1]['prose'], 'published')

    def test_figure_absent_from_the_sources_gets_one_retry(self):
        bad = 'Арендная плата составляет 420 000 рублей в месяц (п. 2.1).'
        good = 'Арендная плата составляет 380 000 рублей в месяц (п. 2.1).'
        result, model, _ = one_call('Какая арендная плата по К-4/2033?', [answer('2.1.', bad), answer('2.1.', good)])
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1][1].get('retry_reason'), 'answer_numbers_not_in_sources')
        self.assertTrue(result['text'].startswith(good), result['text'])
        self.assertNotIn('420 000', result['text'])

    def test_twice_rejected_text_leaves_the_provisions(self):
        bad = 'Арендная плата составляет 420 000 рублей в месяц (п. 2.1).'
        result, model, _ = one_call('Какая арендная плата по К-4/2033?', [answer('2.1.', bad), answer('2.1.', bad)])
        self.assertEqual(len(model.calls), 2)
        self.assertNotIn('420 000', result['text'])
        self.assertIn('«2.1. Арендная плата составляет 380 000 рублей в месяц.»', result['text'])
        self.assertTrue(result['quote_only'])

    def test_lost_restriction_is_retried_with_its_wording(self):
        lost = 'Да, арендатор может сдавать помещение в субаренду (п. 4.2).'
        kept = 'Нет. Арендатор не вправе сдавать помещение в субаренду без письменного согласия арендодателя (п. 4.2).'
        result, model, _ = one_call('Можно ли сдать помещение по К-4/2033 в субаренду?', [answer('4.2.', lost), answer('4.2.', kept)])
        self.assertEqual(model.calls[1][1].get('retry_reason'), 'answer_lost_restrictions')
        self.assertTrue(result['text'].startswith(kept), result['text'])
        self.assertNotIn(lost, result['text'])

    def test_verify_true_keeps_the_verifier_call(self):
        text = 'Арендная плата составляет 380 000 рублей в месяц (п. 2.1).'
        verdict = {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
                   'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}
        with corpus(LEASE) as r:
            model = ScriptedModel([answer('2.1.', text), verdict])
            with redirect_stderr(io.StringIO()):
                result = answer_structured('Какая арендная плата по К-4/2033?', r, model)
        self.assertEqual(len(model.calls), 2)
        self.assertIn('candidate', model.calls[1][1])
        self.assertTrue(result['text'].startswith(text))


class OneCallBatchTests(unittest.TestCase):
    def run_batch(self, texts, verify=None):
        """texts: generation number per row -> answer text; one row per entry of the first list."""
        events = []

        class Client:
            def __init__(self, deadline, position=None):
                self.deadline, self.position, self.calls = deadline, position, 0

            def complete(self, system, payload):
                self.calls += 1
                events.append((self.position, 'verify' if 'candidate' in payload else 'generate'))
                f = next(f for f in payload['evidence'] if f['text'].startswith('9.1.'))
                return {'status': 'answer', 'answer': texts[min(self.calls, len(texts)) - 1],
                        'source_ids': [f['id']], 'requested_facts': []}

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (root / 'questions.csv').open('w', encoding='utf-8', newline='') as h:
                csv.writer(h).writerows([['id', 'question']] + [[f'00{i}', 'Можно ли передавать помещение?'] for i in range(3)])
            with zipfile.ZipFile(root / 'knowledge-base.zip', 'w') as z:
                z.writestr('terms.txt', '9.1. Помещение можно передавать только при письменном согласии владельца.')
            env = {'DATA_DIR': temp, 'MAX_WORKERS': '1', 'PSB_RUN_SECONDS': '1100'}
            if verify is not None:
                env['PSB_VERIFY'] = verify
            with patch.dict(os.environ, env, clear=True), patch.object(solution, 'ProxyClient', Client), \
                    patch.object(solution.Path, 'cwd', return_value=root), redirect_stderr(io.StringIO()):
                self.assertEqual(solution.main(), 0)
            with (root / 'submission.csv').open(encoding='utf-8', newline='') as h:
                rows = list(csv.DictReader(h))
        return events, rows

    def test_batch_default_is_one_call_per_answer(self):
        good = 'Помещение можно передавать только при письменном согласии владельца (п. 9.1).'
        events, rows = self.run_batch([good])
        self.assertEqual(events, [(0, 'generate'), (1, 'generate'), (2, 'generate')])
        self.assertTrue(all(row['answer'].startswith(good) for row in rows), rows)

    def test_retries_wait_until_every_row_has_its_first_answer(self):
        lost = 'Помещение можно передавать.'
        kept = 'Помещение можно передавать только при письменном согласии владельца (п. 9.1).'
        events, rows = self.run_batch([lost, kept])
        self.assertEqual([i for i, _ in events], [0, 1, 2, 0, 1, 2])
        self.assertTrue(all(stage == 'generate' for _, stage in events))
        self.assertTrue(all(row['answer'].startswith(kept) for row in rows), rows)

    def test_verifier_is_opt_in(self):
        good = 'Помещение можно передавать только при письменном согласии владельца (п. 9.1).'
        events, _ = self.run_batch([good], verify='1')
        self.assertIn((0, 'verify'), events)


if __name__ == '__main__':
    unittest.main()
