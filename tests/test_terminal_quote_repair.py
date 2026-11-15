"""A final prose repair preserves checked evidence and all existing barriers."""
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
import io
import json
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
import psb_policy as policy
import solution
from psb_llm import ProviderError
from test_audit_fixes import corpus
from test_baseline import ScriptedModel
from test_unasked_items import FILES as PRICE_FILES, FULL, QUESTION as PRICE_QUESTION


FILES = {'Порядок.txt': 'Порядок учёта\n'
         '4.2. Период учёта составляет 12 месяцев с даты решения.\n'
         '4.3. Архив хранится в отделе кадров.'}
QUESTION = 'Каков период учёта?'
BAD = 'Период учёта составляет 99 месяцев с даты решения (п. 4.2).'
OTHER_BAD = 'Период учёта составляет 77 месяцев с даты решения (п. 4.2).'
GOOD = 'Период учёта составляет 12 месяцев с даты решения (п. 4.2).'


def generate(clause, text, *, status='answer', facts=(), issue=''):
    def response(payload):
        source = next(f for f in payload['evidence'] if f['text'].startswith(clause))
        return {'status': status, 'answer': text, 'source_ids': [source['id']],
                'requested_facts': list(facts), 'issue': issue}
    return response


def run_case(responses, *, files=FILES, question=QUESTION, repair=True, verify=False):
    model = ScriptedModel(responses)
    log = io.StringIO()
    with corpus(files) as retriever, redirect_stderr(log):
        result = policy.answer_structured(question, retriever, model, verify=verify,
                                          repair_quotes=repair)
    events = [json.loads(line) for line in log.getvalue().splitlines()
              if line.startswith('{"event": "policy_one_call"')]
    return result, model, events


class TerminalQuoteRepairTests(unittest.TestCase):
    def test_default_remains_two_attempts_and_initial_requests_are_unchanged(self):
        responses = [generate('4.2.', BAD), generate('4.2.', OTHER_BAD)]
        with corpus(FILES) as retriever, redirect_stderr(io.StringIO()):
            default_model = ScriptedModel(responses)
            baseline = policy.answer_structured(QUESTION, retriever, default_model, verify=False)
        result, model, _ = run_case(responses + [generate('4.2.', GOOD)])
        self.assertEqual(len(default_model.calls), 2)
        self.assertTrue(baseline['quote_only'])
        self.assertEqual(model.calls[:2], default_model.calls)
        self.assertEqual(len(model.calls), 3)
        self.assertFalse(result['quote_only'])
        self.assertTrue(result['text'].startswith(GOOD), result['text'])

    def test_latest_numeric_failure_replaces_the_first_diagnostic(self):
        _, model, _ = run_case([generate('4.2.', BAD), generate('4.2.', OTHER_BAD),
                                generate('4.2.', GOOD)])
        second, third = [payload for _, payload in model.calls[1:]]
        self.assertEqual(second['retry_numeric_feedback']['unmatched_numbers'], ['99'])
        self.assertEqual(third['retry_numeric_feedback']['unmatched_numbers'], ['77'])
        self.assertEqual(third['retry_rejected_answer'], OTHER_BAD)
        self.assertTrue(third['final_text_repair'])
        self.assertNotIn('final_text_repair', second)
        self.assertTrue(all('candidate' not in payload for _, payload in model.calls))

    def test_new_ordinal_failure_is_diagnosed_without_authorizing_the_number(self):
        files = {'Порядок.txt': 'Порядок дежурств\n'
                 '4.2. Первые два часа дежурства оплачиваются с надбавкой.'}
        second = 'Надбавка полагается первым двум часам дежурства (п. 4.2).'
        good = 'Надбавка полагается за начальные 2 часа дежурства (п. 4.2).'
        result, model, _ = run_case([
            generate('4.2.', 'Надбавка полагается за 99 часов дежурства (п. 4.2).'),
            generate('4.2.', second), generate('4.2.', good)], files=files,
            question='За какое время дежурства полагается надбавка?')
        self.assertEqual(model.calls[2][1]['retry_numeric_feedback']['unmatched_numbers'], ['1'])
        self.assertEqual(model.calls[2][1]['retry_rejected_answer'], second)
        self.assertFalse(policy.prose_grounded(second, next(iter(files.values()))))
        self.assertTrue(result['text'].startswith(good), result['text'])

    def test_reason_changes_from_numeric_to_current_exclusive_claim(self):
        files = {'Порядок.txt': 'Порядок заявок\n3.4. Заявку согласует руководитель отдела.'}
        exclusive = 'Только руководитель отдела вправе согласовывать заявку (п. 3.4).'
        good = 'Заявку согласует руководитель отдела (п. 3.4).'
        result, model, _ = run_case([
            generate('3.4.', 'Заявку согласует руководитель отдела за 99 дней (п. 3.4).'),
            generate('3.4.', exclusive), generate('3.4.', good)],
            files=files, question='Кто согласует заявку?')
        payload = model.calls[2][1]
        self.assertEqual(payload['retry_reason'], 'answer_not_supported')
        self.assertEqual(payload['retry_policy_draft'], exclusive)
        self.assertEqual(payload['retry_policy_feedback']['scope_barrier'], 'exclusive_word')
        self.assertNotIn('retry_numeric_feedback', payload)
        self.assertNotIn('retry_rejected_answer', payload)
        self.assertTrue(result['text'].startswith(good), result['text'])

    def test_reason_changes_from_scope_to_current_numeric_claim(self):
        result, model, _ = run_case([
            generate('4.2.', 'Только директор устанавливает период учёта (п. 4.2).'),
            generate('4.2.', OTHER_BAD), generate('4.2.', GOOD)])
        payload = model.calls[2][1]
        self.assertEqual(payload['retry_reason'], 'answer_numbers_not_in_sources')
        self.assertEqual(payload['retry_numeric_feedback']['unmatched_numbers'], ['77'])
        self.assertEqual(payload['retry_rejected_answer'], OTHER_BAD)
        self.assertEqual(payload['retry_policy_draft'], OTHER_BAD)
        self.assertTrue(result['text'].startswith(GOOD), result['text'])

    def test_missing_restriction_gets_one_final_attempt_but_is_never_waived(self):
        files = {'Правила.txt': 'Правила доступа\n'
                 '4.2. Работник не вправе передавать пропуск другому лицу.'}
        bad = 'Работник вправе передавать пропуск другому лицу (п. 4.2).'
        good = 'Работник не вправе передавать пропуск другому лицу (п. 4.2).'
        for last, published in ((good, True), (bad, False)):
            with self.subTest(last=last):
                result, model, _ = run_case([generate('4.2.', bad)] * 2 + [generate('4.2.', last)],
                    files=files, question='Можно передать пропуск другому лицу?')
                self.assertEqual(len(model.calls), 3)
                self.assertEqual(model.calls[2][1]['retry_reason'], 'answer_lost_restrictions')
                self.assertIn('не вправе', model.calls[2][1]['retry_restrictions'])
                self.assertEqual(result['quote_only'], not published)
                self.assertNotIn(bad, result['text'])

    def test_first_or_second_valid_answer_is_not_regenerated(self):
        for responses in ([generate('4.2.', GOOD)],
                          [generate('4.2.', BAD), generate('4.2.', GOOD)]):
            with self.subTest(calls=len(responses)):
                result, model, _ = run_case(responses)
                self.assertEqual(len(model.calls), len(responses))
                self.assertFalse(result['quote_only'])
                self.assertTrue(result['text'].startswith(GOOD))

    def test_valid_first_fallback_prevents_a_third_attempt(self):
        responses = [generate('3.4.', FULL),
                     generate('3.4.', 'Вывоз мусора стоит 99 рублей (п. 3.4).')]
        result, model, _ = run_case(responses, files=PRICE_FILES, question=PRICE_QUESTION)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1][1]['retry_reason'], 'answer_extra_items')
        self.assertFalse(result['quote_only'])
        self.assertTrue(result['text'].startswith(FULL), result['text'])

    def test_partial_or_typed_issue_never_gets_a_terminal_attempt(self):
        for options in ({'status': 'partial', 'facts': ('document',)},
                        {'status': 'partial', 'issue': 'historical_version'},
                        {'status': 'partial', 'issue': 'ambiguous_entity'}):
            with self.subTest(options=options):
                result, model, _ = run_case([generate('4.2.', BAD, **options)] * 2)
                self.assertEqual(len(model.calls), 2)
                self.assertEqual(result['status'], 'partial')
                self.assertTrue(result['quote_only'])

    def test_missing_value_document_is_not_a_wording_failure(self):
        files = {'Договор.txt': 'Договор поставки\n'
                 '6.1. Гарантийный срок на товар устанавливается производителем '
                 'и указывается в гарантийном талоне.'}
        result, model, _ = run_case([
            generate('6.1.', 'Гарантийный срок составляет 99 месяцев (п. 6.1).')] * 2,
            files=files, question='Какой гарантийный срок на товар?')
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(result['status'], 'partial')
        self.assertNotIn('99 месяцев', result['text'])
        self.assertIn('гарантийн', result['text'].lower())

    def test_missing_cross_reference_is_not_repaired_as_prose(self):
        files = {'Правило.txt': 'Источник: Статья 5. Федеральный закон от 03.04.2031 N 432-ФЗ\n'
                 'Статья 5. Разрешение\n1. Обязанность представить доказательство получения '
                 'разрешения либо наличия оснований статьи 23 настоящего Федерального закона '
                 'возлагается на заявителя.'}
        result, model, _ = run_case([
            generate('1. Обязанность', 'Доказательство нужно представить за 99 дней.')] * 2,
            files=files, question='Как подтвердить наличие оснований статьи 23?')
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('не найдены тексты отсылочных статей', result['text'])

    def test_absent_prose_or_sources_does_not_start_a_terminal_attempt(self):
        for second in (generate('4.2.', ''),
                       {'status': 'answer', 'answer': GOOD, 'source_ids': [], 'requested_facts': []}):
            with self.subTest(second=second):
                result, model, _ = run_case([generate('4.2.', BAD), second])
                self.assertEqual(len(model.calls), 2)
                self.assertTrue(result['quote_only'])

    def test_equal_or_worse_terminal_result_preserves_exact_baseline(self):
        first_two = [generate('4.2.', BAD), generate('4.2.', OTHER_BAD)]
        baseline, _, _ = run_case(first_two, repair=False)
        terminal_results = [
            generate('4.2.', BAD),
            generate('4.3.', 'Архив хранится 99 месяцев в отделе кадров (п. 4.3).'),
            generate('4.2.', GOOD, status='partial', facts=('document',)),
            {'status': 'insufficient', 'answer': '', 'source_ids': []},
        ]
        for third in terminal_results:
            with self.subTest(third=third):
                result, model, _ = run_case(first_two + [third])
                self.assertEqual(len(model.calls), 3)
                self.assertEqual(result, baseline)
                self.assertNotIn('99 месяцев', result['text'])

    def test_provider_failure_keeps_exact_pre_terminal_result(self):
        responses = [generate('4.2.', BAD), generate('4.3.', 'Архив хранится 99 месяцев.')]
        baseline, _, _ = run_case(responses, repair=False)
        self.assertIn('Архив хранится', baseline['text'])
        for code in ('http_503', 'run_deadline', 'model_invalid_json'):
            with self.subTest(code=code):
                result, model, _ = run_case(responses + [ProviderError(code)])
                self.assertEqual(len(model.calls), 3)
                self.assertEqual(result, baseline)

    def test_invalid_terminal_schema_keeps_exact_pre_terminal_result(self):
        responses = [generate('4.2.', BAD), generate('4.2.', OTHER_BAD)]
        baseline, _, _ = run_case(responses, repair=False)
        invalid = [None, [], {}, {'status': 'answer', 'source_ids': ['unavailable'], 'answer': GOOD},
                   {'status': 'answer', 'source_ids': 12, 'answer': GOOD}]
        for third in invalid:
            with self.subTest(third=third):
                result, model, _ = run_case(responses + [third])
                self.assertEqual(len(model.calls), 3)
                self.assertEqual(result, baseline)

    def test_terminal_repair_does_not_authorize_incidental_one_day(self):
        files = {'Порядок.txt': 'Порядок дежурств\n'
                 '4.2. Первые два часа дежурства оплачиваются с надбавкой.'}
        bad = 'Надбавка полагается за один день дежурства (п. 4.2).'
        result, model, _ = run_case([generate('4.2.', bad)] * 3, files=files,
            question='Сегодня день — первый. За какое время дежурства полагается надбавка?')
        self.assertEqual(len(model.calls), 3)
        self.assertTrue(result['quote_only'])
        self.assertNotIn(bad, result['text'])

    def test_terminal_repair_does_not_turn_last_two_hours_into_first_two(self):
        files = {'Порядок.txt': 'Порядок дежурств\n'
                 '4.2. Последним двум часам дежурства соответствует повышенная оплата.'}
        bad = 'Первым двум часам дежурства соответствует повышенная оплата (п. 4.2).'
        result, model, _ = run_case([generate('4.2.', bad)] * 3, files=files,
                                   question='Как оплачивается начало дежурства?')
        self.assertEqual(len(model.calls), 3)
        self.assertTrue(result['quote_only'])
        self.assertNotIn(bad, result['text'])
        self.assertIn('Последним двум часам', result['text'])

    def test_inapplicable_second_selection_does_not_trigger_terminal_repair(self):
        files = {**FILES, 'Новый порядок.txt': 'Новый порядок учёта\nДействует с 01.03.2036.\n'
                 '5.2. Период учёта составляет 18 месяцев с даты решения.'}
        newer = 'Период учёта составляет 18 месяцев с даты решения (п. 5.2).'
        result, model, events = run_case([generate('4.2.', BAD), generate('5.2.', newer)],
            files=files, question='Решение принято 15 марта 2033 года. Каков период учёта?')
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(events[-1]['edition_mismatch'])
        self.assertTrue(result['quote_only'])
        self.assertNotIn('18 месяцев', result['text'])

    def test_inapplicable_terminal_selection_cannot_replace_current_quotes(self):
        files = {**FILES, 'Новый порядок.txt': 'Новый порядок учёта\nДействует с 01.03.2036.\n'
                 '5.2. Период учёта составляет 18 месяцев с даты решения.'}
        question = 'Решение принято 15 марта 2033 года. Каков период учёта?'
        first_two = [generate('4.2.', BAD), generate('4.2.', OTHER_BAD)]
        baseline, _, _ = run_case(first_two, files=files, question=question, repair=False)
        result, model, events = run_case(first_two + [generate('5.2.',
            'Период учёта составляет 18 месяцев с даты решения (п. 5.2).')],
            files=files, question=question)
        self.assertEqual(len(model.calls), 3)
        self.assertTrue(events[-1]['edition_mismatch'])
        self.assertEqual(result, baseline)

    def test_terminal_repair_does_not_authorize_a_derived_end_date(self):
        bad = ('Период учёта — 12 месяцев с 15 марта 2033 года '
               'до 15 марта 2034 года (п. 4.2).')
        result, model, _ = run_case([generate('4.2.', bad)] * 3,
            question='Решение принято 15 марта 2033 года. Каков период учёта?')
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(model.calls[2][1]['retry_numeric_feedback']['unmatched_dates'], ['15.03.2034'])
        self.assertTrue(result['quote_only'])
        self.assertNotIn('2034', result['text'])

    def test_verifier_mode_never_adds_a_terminal_generation(self):
        verdict = {'approved': True, 'complete': True, 'status': 'answer',
                   'answer_supported': True,
                   'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}
        result, model, _ = run_case([generate('4.2.', BAD), verdict,
                                    generate('4.2.', OTHER_BAD), verdict], verify=True)
        self.assertEqual(len(model.calls), 4)
        self.assertEqual(sum('candidate' not in payload for _, payload in model.calls), 2)
        self.assertTrue(result['quote_only'])
        self.assertTrue(all('final_text_repair' not in payload for _, payload in model.calls))

    def test_checkpoint_yields_exact_baseline_before_terminal_generation(self):
        responses = [generate('4.2.', BAD), generate('4.3.', 'Архив хранится 99 месяцев.')]
        baseline, _, _ = run_case(responses, repair=False)
        with corpus(FILES) as retriever, redirect_stderr(io.StringIO()):
            model = ScriptedModel(responses + [generate('4.2.', GOOD)])
            steps = policy.answer_steps(QUESTION, retriever, model, verify=False, repair_quotes=True)
            first = next(steps)
            self.assertEqual(len(model.calls), 1)
            self.assertTrue(first['quote_only'])
            second = next(steps)
            self.assertEqual(len(model.calls), 2)
            self.assertEqual(second, baseline)
            steps.close()
        self.assertEqual(len(model.calls), 2)


class TerminalRepairBatchTests(unittest.TestCase):
    def run_batch(self, *, stop_before_third=False):
        events, payloads = [], []
        clock = [0.0]

        class Client:
            def __init__(self, deadline, position=None):
                self.position, self.calls = position, 0

            def complete(self, system, payload):
                self.calls += 1
                events.append((self.position, self.calls))
                payloads.append(payload)
                text = [BAD, OTHER_BAD, GOOD][self.calls - 1]
                if stop_before_third and self.position == 2 and self.calls == 2:
                    clock[0] = 100.0
                return generate('4.2.', text)(payload)

        with corpus(FILES) as retriever, patch.object(solution, 'ProxyClient', Client), \
                patch.object(time, 'monotonic', side_effect=lambda: clock[0]), redirect_stderr(io.StringIO()):
            checkpoints = list(solution.run_questions([(f'00{i}', QUESTION) for i in range(3)],
                retriever, deadline=100.0, workers=1, top_k=6, verify=False))
        latest = {index: (text, status) for index, text, status in checkpoints}
        return events, payloads, latest

    def test_batch_runs_all_second_attempts_before_any_third(self):
        events, payloads, rows = self.run_batch()
        self.assertEqual(events, [(i, attempt) for attempt in (1, 2, 3) for i in range(3)])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(text.startswith(GOOD) and status == 'answer' for text, status in rows.values()))
        self.assertEqual([p.get('final_text_repair', False) for p in payloads], [False] * 6 + [True] * 3)

    def test_global_deadline_keeps_second_round_checkpoints_without_third_calls(self):
        events, _, rows = self.run_batch(stop_before_third=True)
        self.assertEqual(events, [(i, attempt) for attempt in (1, 2) for i in range(3)])
        self.assertEqual(len(rows), 3)
        baseline, _, _ = run_case([generate('4.2.', BAD), generate('4.2.', OTHER_BAD)], repair=False)
        self.assertTrue(all(text == baseline['text'] and status == baseline['status']
                            for text, status in rows.values()))


if __name__ == '__main__':
    unittest.main()
