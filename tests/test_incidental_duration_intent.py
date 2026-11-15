"""A duration in the question does not necessarily ask for an unknown value."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from test_one_call_answers import answer, one_call


SOURCE = ('7.2. Срок сервисного обслуживания определяется исполнителем '
          'и указывается в сервисном паспорте.')
FILES = {'Договор обслуживания С-6-2034.txt': 'Договор обслуживания № С-6/2034\n' + SOURCE}
EXPLANATION = ('Срок сервисного обслуживания определяется исполнителем '
               'и указывается в сервисном паспорте (п. 7.2).')


class IncidentalDurationIntentTests(unittest.TestCase):
    def assert_direct_answer(self, question, draft=EXPLANATION):
        # A second response makes an unwanted retry fail the assertion below,
        # rather than fail merely because the scripted response list ran out.
        result, model, events = one_call(question, [answer('7.2.', draft)] * 2, FILES)
        self.assertEqual(result['status'], 'answer', result['text'])
        self.assertFalse(result['quote_only'], result['text'])
        self.assertTrue(result['text'].startswith(draft), result['text'])
        self.assertTrue(result['sources'])
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(events[-1]['prose'], 'published')
        self.assertNotIn('Чтобы назвать конкретное значение', result['text'])
        self.assertNotIn('Предоставьте', result['text'])

    def test_elapsed_time_before_who_does_not_require_the_missing_value_document(self):
        for question in (
                'Оборудование передано 11 месяцев назад. Кто определяет срок сервисного обслуживания?',
                'После семи недель эксплуатации хочу узнать, кто определяет срок сервисного обслуживания.'):
            with self.subTest(question=question):
                self.assert_direct_answer(question)

    def test_elapsed_time_before_where_does_not_require_the_missing_value_document(self):
        for question in (
                'Оборудование передано 13 месяцев назад. Где указан срок сервисного обслуживания?',
                'Через пять недель после поставки хочу узнать, в каком документе указан срок сервисного обслуживания.'):
            with self.subTest(question=question):
                self.assert_direct_answer(question)

    def test_denial_of_evidential_support_is_a_direct_answer(self):
        question = ('Можно ли из договора С-6/2034 сделать вывод, '
                    'что срок сервисного обслуживания составляет 17 месяцев?')
        draft = ('Нет. Из договора нельзя сделать вывод, что срок сервисного обслуживания '
                 'составляет 17 месяцев. ' + EXPLANATION)
        self.assert_direct_answer(question, draft)

    def test_an_actual_open_value_request_still_requires_the_defining_document(self):
        result, _, _ = one_call('Какой срок сервисного обслуживания по договору С-6/2034?',
                               [answer('7.2.', EXPLANATION)] * 2, FILES)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['text'].startswith('Конкретное значение в найденных документах не установлено:'))
        self.assertIn('«' + SOURCE + '»', result['text'])
        self.assertIn('Договор обслуживания С-6-2034', result['text'])
        self.assertIn('Чтобы назвать значение, нужен этот документ.', result['text'])


if __name__ == '__main__':
    unittest.main()
