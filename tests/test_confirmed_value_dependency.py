"""A suggested quantity is still unknown when its defining document is absent."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import value_dependencies
from test_one_call_answers import one_call, answer

SOURCE = ('7.2. Срок сервисного обслуживания определяется изготовителем '
          'и указывается в сервисном паспорте.')
FILES = {'Договор С-9-2031.txt': 'Договор № С-9/2031\n' + SOURCE}
FRAGMENT = Fragment('f', 'Договор С-9-2031.txt', 0, len(SOURCE), SOURCE, '')
EXPLANATION = ('Срок сервисного обслуживания определяется изготовителем '
               'и указывается в сервисном паспорте (п. 7.2).')


class ConfirmedValueDependencyTests(unittest.TestCase):
    def test_numeric_and_spelled_out_proposals_need_the_value_document(self):
        for question in ('Срок сервисного обслуживания ведь 19 месяцев?',
                         'Правда, что срок сервисного обслуживания — 11 рабочих дней?',
                         'Сервисное обслуживание длится три года?'):
            with self.subTest(question=question):
                self.assertEqual(value_dependencies(question, [FRAGMENT], {}),
                                 ['указывается в сервисном паспорте'])

    def test_identifier_alone_is_not_a_proposed_quantity(self):
        self.assertEqual(value_dependencies('Расскажи об обслуживании по С-9/2031.', [FRAGMENT], {}), [])

    def test_who_and_where_questions_do_not_need_a_value(self):
        for question in ('Кто устанавливает срок сервисного обслуживания, даже если он 19 месяцев?',
                         'Где указан срок сервисного обслуживания 19 месяцев?',
                         'В каком документе указывается срок сервисного обслуживания 19 месяцев?',
                         'Подскажите, где указан срок сервисного обслуживания 19 месяцев?',
                         'По договору С-9/2031 кто устанавливает срок сервисного обслуживания, даже если он 19 месяцев?'):
            with self.subTest(question=question):
                self.assertEqual(value_dependencies(question, [FRAGMENT], {}), [])

    def test_confirmation_followed_by_location_still_needs_a_value(self):
        question = 'По договору С-9/2031 срок сервисного обслуживания 19 месяцев, и где это указано?'
        self.assertEqual(value_dependencies(question, [FRAGMENT], {}),
                         ['указывается в сервисном паспорте'])

    def test_service_price_does_not_require_the_missing_service_period(self):
        source = SOURCE + ' Стоимость сервисного обслуживания составляет 5 000 рублей.'
        files = {'Договор С-9-2031.txt': 'Договор № С-9/2031\n' + source}
        draft = 'Да. Стоимость сервисного обслуживания составляет 5 000 рублей (п. 7.2).'
        result, _, _ = one_call('Стоимость сервисного обслуживания составляет 5 000 рублей?',
                               [answer('7.2.', draft)], files)
        self.assertEqual(result['status'], 'answer')
        self.assertTrue(result['text'].startswith(draft), result['text'])

    def test_duration_does_not_activate_a_price_reference(self):
        source = ('7.2. Стоимость сервисного обслуживания определяется изготовителем '
                  'и указывается в сервисном паспорте.')
        fragment = Fragment('f', 'Договор С-9-2031.txt', 0, len(source), source, '')
        self.assertEqual(value_dependencies('Срок сервисного обслуживания 19 месяцев?',
                                            [fragment], {}), [])

    def test_reference_with_explicit_value_can_confirm_or_contradict(self):
        source = SOURCE + ' Для оборудования по настоящему договору он составляет 22 месяца.'
        files = {'Договор С-9-2031.txt': 'Договор № С-9/2031\n' + source}
        for proposed, draft in (
                (22, 'Да. Для оборудования по настоящему договору срок сервисного обслуживания составляет 22 месяца (п. 7.2).'),
                (19, 'Нет. Для оборудования по настоящему договору срок сервисного обслуживания составляет 22 месяца, а не 19 (п. 7.2).')):
            with self.subTest(proposed=proposed):
                result, _, _ = one_call(f'Срок сервисного обслуживания составляет {proposed} месяца?',
                                       [answer('7.2.', draft)], files)
                self.assertEqual(result['status'], 'answer')
                self.assertTrue(result['text'].startswith(draft), result['text'])

    def test_known_duration_in_another_selected_clause_resolves_the_dependency(self):
        known = '8.1. Срок сервисного обслуживания составляет 22 месяца.'
        fragment = Fragment('known', FRAGMENT.document, 0, len(known), known, '')
        for proposed in (19, 22):
            with self.subTest(proposed=proposed):
                self.assertEqual(value_dependencies(
                    f'Срок сервисного обслуживания составляет {proposed} месяца?',
                    [FRAGMENT, fragment], {}), [])
        # The existing open-question path is not expanded by this change.
        self.assertEqual(value_dependencies('Какой срок сервисного обслуживания?',
                                            [FRAGMENT, fragment], {}),
                         ['указывается в сервисном паспорте'])

    def test_other_duration_subject_or_document_cannot_resolve_the_dependency(self):
        for document, known in (
                (FRAGMENT.document, '8.1. Срок оплаты составляет 22 дня.'),
                (FRAGMENT.document, '8.1. Срок оплаты сервисного обслуживания составляет 22 дня.'),
                ('Договор М-2-2032.txt', '8.1. Срок сервисного обслуживания составляет 22 месяца.')):
            with self.subTest(document=document, known=known):
                fragment = Fragment('known', document, 0, len(known), known, '')
                self.assertEqual(value_dependencies('Срок сервисного обслуживания составляет 19 месяцев?',
                                                    [FRAGMENT, fragment], {}),
                                 ['указывается в сервисном паспорте'])

    def test_two_selected_clauses_can_confirm_or_contradict_a_known_duration(self):
        known = '8.1. Срок сервисного обслуживания составляет 22 месяца.'
        files = {FRAGMENT.document: 'Договор № С-9/2031\n' + SOURCE + '\n' + known}
        for proposed, start in ((22, 'Да. '), (19, 'Нет. ')):
            with self.subTest(proposed=proposed):
                draft = start + 'Срок сервисного обслуживания составляет 22 месяца (п. 8.1). ' + EXPLANATION

                def response(payload):
                    ids = [e['id'] for e in payload['evidence']
                           if e['text'].startswith(('7.2.', '8.1.'))]
                    self.assertEqual(len(ids), 2)
                    return {'status': 'answer', 'answer': draft, 'source_ids': ids,
                            'requested_facts': [], 'issue': ''}

                result, model, _ = one_call(f'Срок сервисного обслуживания составляет {proposed} месяца?',
                                            [response], files)
                self.assertEqual(result['status'], 'answer')
                self.assertTrue(result['text'].startswith(draft), result['text'])
                self.assertEqual(len(model.calls), 1)

    def test_unrelated_quantity_does_not_activate_the_dependency(self):
        self.assertEqual(value_dependencies('Срок оплаты ведь 19 дней?', [FRAGMENT], {}), [])

    def test_unknown_quantity_cannot_be_categorically_confirmed_or_denied(self):
        question = 'По договору С-9/2031 срок сервисного обслуживания ведь 19 месяцев?'
        for start in ('Нет. ', 'Да. '):
            with self.subTest(start=start):
                draft = start + EXPLANATION
                result, _, _ = one_call(question, [answer('7.2.', draft)] * 2, FILES)
                self.assertEqual(result['status'], 'partial')
                self.assertFalse(result['text'].startswith(start), result['text'])
                self.assertIn('Конкретное значение', result['text'])
                self.assertIn('Предоставьте', result['text'])
                self.assertIn('сервисном паспорте', result['text'])

    def test_scoped_document_absence_can_remain_a_prose_answer(self):
        draft = 'Нет, значение в договоре не указано. ' + EXPLANATION
        result, _, _ = one_call('Срок сервисного обслуживания ведь 19 месяцев?',
                               [answer('7.2.', draft)] * 2, FILES)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['text'].startswith(draft), result['text'])
        self.assertIn('Чтобы назвать конкретное значение', result['text'])

    def test_known_value_can_still_contradict_the_proposal(self):
        files = {'Договор С-9-2031.txt': 'Договор № С-9/2031\n7.2. Срок сервисного обслуживания составляет 22 месяца.'}
        draft = 'Нет. Срок сервисного обслуживания составляет 22 месяца, а не 19 (п. 7.2).'
        result, _, _ = one_call('По С-9/2031 срок сервисного обслуживания 19 месяцев?',
                               [answer('7.2.', draft)], files)
        self.assertEqual(result['status'], 'answer')
        self.assertTrue(result['text'].startswith(draft), result['text'])


if __name__ == '__main__':
    unittest.main()
