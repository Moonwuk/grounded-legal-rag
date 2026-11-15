"""Exercise completion and unknown-value policy through the real CSV batch."""
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

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
import solution
from test_money_calculation_completion import BASIS, DRAFT, QUESTION
from test_value_confirmation import FILES as VALUE_FILES, EXPLANATION, SOURCE


MONEY_FILES = {'Договор М-8-2036.txt': 'Договор № М-8/2036\n' + BASIS}


def select(clauses, text):
    def response(payload):
        return {'status': 'answer', 'answer': text,
                'source_ids': [next(e['id'] for e in payload['evidence']
                                    if e['text'].startswith(clause)) for clause in clauses],
                'requested_facts': [], 'issue': ''}
    return response


def run_csv_batch(cases, files):
    """Use main(), actual ZIP parsing, retrieval, policy and atomic CSV output."""
    calls, log = [], io.StringIO()

    class Client:
        def __init__(self, deadline, position=None):
            self.deadline, self.position, self.calls = deadline, position, 0

        def complete(self, system, payload):
            calls.append((self.position, system, payload))
            responses = cases[self.position][1]
            response = responses[min(self.calls, len(responses) - 1)]
            self.calls += 1
            return response(payload)

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        with (root / 'questions.csv').open('w', encoding='utf-8', newline='') as handle:
            csv.writer(handle).writerows([['id', 'question']] +
                                        [[str(i), question] for i, (question, _) in enumerate(cases)])
        with zipfile.ZipFile(root / 'knowledge-base.zip', 'w') as archive:
            for name, text in files.items():
                archive.writestr(name, text)
        with patch.dict(os.environ, {'DATA_DIR': temp, 'MAX_WORKERS': '1', 'PSB_RUN_SECONDS': '60'}, clear=True), \
                patch.object(solution, 'ProxyClient', Client), \
                patch.object(solution.Path, 'cwd', return_value=root), redirect_stderr(log):
            code = solution.main()
        with (root / 'submission.csv').open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
    events = [json.loads(line) for line in log.getvalue().splitlines()
              if line.startswith('{"event": "policy_one_call"')]
    return code, rows, calls, events


class QualityCompletionIntegrationTests(unittest.TestCase):
    def test_money_completion_reaches_the_final_csv_with_its_conditions(self):
        code, rows, calls, _ = run_csv_batch(
            [(QUESTION, [select(['3.1.', '8.4.'], DRAFT)])], MONEY_FILES)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertTrue(rows[0]['answer'].startswith(DRAFT), rows)
        self.assertIn('Расчёт: 6 200 000 × 50% = 3 100 000 рублей.', rows[0]['answer'])
        self.assertIn('неустойки и убытки', rows[0]['answer'])
        self.assertIn('Источник:', rows[0]['answer'])

    def test_completed_money_does_not_bypass_a_dropped_source_restriction(self):
        files = {'Договор.txt': 'Договор\n' + BASIS.rstrip('.') + ', за исключением случаев умысла.'}
        _, rows, calls, events = run_csv_batch(
            [(QUESTION, [select(['3.1.', '8.4.'], DRAFT)])], files)
        self.assertGreaterEqual(len(calls), 2)
        self.assertFalse(rows[0]['answer'].startswith(DRAFT))
        self.assertNotIn('Расчёт:', rows[0]['answer'])
        self.assertIn('за исключением случаев умысла', rows[0]['answer'])
        self.assertTrue(all(e['prose'] != 'published' for e in events))

    def test_the_price_of_another_subject_is_not_completed_as_the_requested_fee(self):
        files = {'Тариф.txt': 'Тариф\n1.1. Цена услуг составляет 60 000 рублей.\n'
                             '1.2. Сбор составляет 15% от цены оборудования.'}
        text = 'Сбор составляет 15% от 60 000 рублей (п. 1.1, 1.2).'
        _, rows, calls, events = run_csv_batch(
            [('Какова сумма сбора в рублях?', [select(['1.1.', '1.2.'], text)])], files)
        self.assertNotIn('Расчёт:', rows[0]['answer'])
        self.assertNotIn('9 000', rows[0]['answer'])
        self.assertFalse(rows[0]['answer'].startswith(text))
        self.assertTrue(all(e['scope_guard'] == 'money_base_mismatch' for e in events))
        self.assertEqual(calls[1][2]['retry_policy_feedback']['scope_barrier'], 'money_base_mismatch')
        self.assertIn('не подставляй чужую сумму', calls[1][1])
        self.assertIn('Цена услуг составляет 60 000 рублей', rows[0]['answer'])
        self.assertIn('Сбор составляет 15% от цены оборудования', rows[0]['answer'])

    def test_missing_value_feedback_and_the_second_answer_name_the_actual_document(self):
        known = 'Конкретный срок не установлен в договоре. ' + EXPLANATION
        cases = [('Срок сервисного обслуживания ведь 19 месяцев?',
                  [select(['7.2.'], 'Нет. ' + EXPLANATION), select(['7.2.'], known)]),
                 (QUESTION, [select(['3.1.', '8.4.'], DRAFT)])]
        code, rows, calls, events = run_csv_batch(cases, {**VALUE_FILES, **MONEY_FILES})
        self.assertEqual(code, 0)
        self.assertEqual([position for position, _, _ in calls], [0, 1, 0])
        self.assertEqual(calls[-1][2].get('retry_reason'), 'missing_value_document')
        self.assertEqual(calls[-1][2].get('retry_value_documents'), ['указывается в сервисном паспорте'])
        self.assertIn('нельзя подтвердить', calls[-1][1])
        self.assertTrue(rows[0]['answer'].startswith('Конкретное значение в найденных документах не установлено:'))
        self.assertIn('«' + SOURCE + '»', rows[0]['answer'])
        self.assertIn('Договор обслуживания С-6-2034', rows[0]['answer'])
        self.assertIn('Чтобы назвать значение, нужен этот документ.', rows[0]['answer'])
        self.assertEqual(events[-1]['candidate_status'], 'partial')
        self.assertNotIn('final_text_repair', calls[-1][2])

    def test_unknown_value_gets_no_terminal_third_generation(self):
        _, rows, calls, events = run_csv_batch(
            [('Срок сервисного обслуживания составляет 19 месяцев, верно?',
              [select(['7.2.'], 'Неверно. ' + EXPLANATION)])], VALUE_FILES)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all('final_text_repair' not in payload for _, _, payload in calls))
        self.assertTrue(all(e['candidate_status'] == 'partial' for e in events))
        self.assertNotIn('Неверно.', rows[0]['answer'])
        self.assertIn('сервисном паспорте', rows[0]['answer'])
        self.assertIn('нужен этот документ', rows[0]['answer'])

    def test_an_invented_number_still_gets_the_missing_value_dependency(self):
        bad = 'Срок сервисного обслуживания составляет 37 месяцев. ' + EXPLANATION
        _, rows, calls, _ = run_csv_batch(
            [('Срок сервисного обслуживания ведь 19 месяцев?',
              [select(['7.2.'], bad), select(['7.2.'], EXPLANATION)])], VALUE_FILES)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][2].get('retry_reason'), 'missing_value_document')
        self.assertEqual(calls[1][2].get('retry_value_documents'), ['указывается в сервисном паспорте'])
        self.assertNotIn('37 месяцев', rows[0]['answer'])
        self.assertIn('«' + SOURCE + '»', rows[0]['answer'])

    def test_evidence_denial_and_incidental_duration_remain_single_call_answers(self):
        denial = ('Нет. Из договора нельзя сделать вывод, что срок сервисного обслуживания '
                  'составляет 17 месяцев. ' + EXPLANATION)
        cases = [('Оборудование передано 11 месяцев назад. Кто определяет срок сервисного обслуживания?',
                  [select(['7.2.'], EXPLANATION)]),
                 ('Можно ли из договора С-6/2034 сделать вывод, что срок сервисного обслуживания составляет 17 месяцев?',
                  [select(['7.2.'], denial)])]
        _, rows, calls, events = run_csv_batch(cases, VALUE_FILES)
        self.assertEqual([position for position, _, _ in calls], [0, 1])
        self.assertTrue(rows[0]['answer'].startswith(EXPLANATION))
        self.assertTrue(rows[1]['answer'].startswith(denial))
        self.assertTrue(all(e['candidate_status'] == 'answer' for e in events))
        self.assertTrue(all('нужен этот документ' not in row['answer'] for row in rows))


if __name__ == '__main__':
    unittest.main()
