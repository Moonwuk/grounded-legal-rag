"""A proposed value does not replace the missing document that defines it."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_policy import _asks_value
from test_one_call_answers import one_call, answer


SOURCE = ('7.2. Срок сервисного обслуживания определяется исполнителем '
          'и указывается в сервисном паспорте.')
FILES = {'Договор обслуживания С-6-2034.txt': 'Договор обслуживания № С-6/2034\n' + SOURCE}
EXPLANATION = ('Срок сервисного обслуживания определяется исполнителем '
               'и указывается в сервисном паспорте (п. 7.2).')


class ValueConfirmationTests(unittest.TestCase):
    def test_confirmation_needs_the_value_defining_document(self):
        for question in ('По договору С-6/2034 срок сервисного обслуживания ведь 19 месяцев?',
                         'Правда ли, что срок сервисного обслуживания составляет два года?',
                         'Срок сервисного обслуживания — 19 месяцев?',
                         'Срок сервисного обслуживания составляет 19 месяцев, верно?',
                         'Срок сервисного обслуживания составляет 19 месяцев, правильно?',
                         'Срок сервисного обслуживания составляет 19 месяцев, не так ли?',
                         'Срок сервисного обслуживания — 19 мес.?',
                         'Срок сервисного обслуживания — 2 г., верно?',
                         'Срок сервисного обслуживания ведь 19 месяцев',
                         'Подтверди, что срок сервисного обслуживания составляет два года'):
            with self.subTest(question=question):
                result, _, _ = one_call(question, [answer('7.2.', 'Нет. ' + EXPLANATION)] * 2, FILES)
                self.assertEqual(result['status'], 'partial', result['text'])
                self.assertFalse(result['text'].startswith('Нет.'))
                self.assertIn('сервисном паспорте', result['text'])
                self.assertIn('нужен этот документ', result['text'])

    def test_unqualified_yes_cannot_confirm_the_unknown_value(self):
        result, _, _ = one_call('Срок сервисного обслуживания ведь 19 месяцев?',
                               [answer('7.2.', 'Да. ' + EXPLANATION)] * 2, FILES)
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['text'].startswith('Да.'))

    def test_alternative_categorical_verdicts_do_not_establish_an_unknown_value(self):
        for verdict in ('Неверно.', 'Это не так.', 'Не так.', 'Неправильно.',
                        'Верно.', 'Это так.', 'Правильно.'):
            with self.subTest(verdict=verdict):
                result, _, _ = one_call('Срок сервисного обслуживания ведь 19 месяцев?',
                                       [answer('7.2.', verdict + ' ' + EXPLANATION)] * 2, FILES)
                self.assertEqual(result['status'], 'partial')
                self.assertFalse(result['text'].startswith(verdict))
                self.assertIn('сервисном паспорте', result['text'])
                self.assertIn('нужен этот документ', result['text'])

    def test_source_explanation_gets_an_application_owned_unknown_answer(self):
        result, _, _ = one_call('Срок сервисного обслуживания ведь 19 месяцев?',
                               [answer('7.2.', EXPLANATION)] * 2, FILES)
        self.assertTrue(result['quote_only'])
        self.assertTrue(result['text'].startswith('Конкретное значение в найденных документах не установлено:'))
        self.assertIn('«' + SOURCE + '»', result['text'])
        self.assertIn('Договор обслуживания С-6-2034', result['text'])
        self.assertIn('Чтобы назвать значение, нужен этот документ.', result['text'])

    def test_a_supplied_defining_document_restores_a_confirmable_value(self):
        files = {**FILES, 'Сервисный паспорт.txt':
                 'СЕРВИСНЫЙ ПАСПОРТ\n1.1. Срок сервисного обслуживания составляет 19 месяцев.'}
        good = 'Да. Срок сервисного обслуживания составляет 19 месяцев по сервисному паспорту (п. 1.1).'
        result, model, _ = one_call('Срок сервисного обслуживания ведь 19 месяцев?',
                                   [answer('1.1.', good)], files)
        self.assertEqual(result['status'], 'answer')
        self.assertTrue(result['text'].startswith(good))
        self.assertEqual(len(model.calls), 1)

    def test_fee_confirmation_is_not_specific_to_warranty_or_months(self):
        files = {'Порядок.txt': 'Порядок\n3.6. Размер комиссии устанавливается оператором и указывается в тарифном приложении.'}
        text = 'Размер комиссии устанавливается оператором и указывается в тарифном приложении (п. 3.6).'
        result, _, _ = one_call('Комиссия ведь 7 процентов?', [answer('3.6.', text)] * 2, files)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('тарифном приложении', result['text'])

    def test_scaled_money_confirmation_is_a_value_request(self):
        files = {'Порядок.txt': 'Порядок\n3.6. Сумма сбора устанавливается оператором и указывается в тарифном приложении.'}
        text = 'Сумма сбора устанавливается оператором и указывается в тарифном приложении (п. 3.6).'
        result, _, _ = one_call('Сумма сбора — 30 тыс. руб., верно?',
                               [answer('3.6.', 'Неверно. ' + text)] * 2, files)
        self.assertEqual(result['status'], 'partial')
        self.assertNotIn('Неверно.', result['text'])
        self.assertIn('тарифном приложении', result['text'])

    def test_short_price_label_keeps_its_value_dependency_across_case_endings(self):
        files = {'Порядок.txt': 'Порядок\n3.6. Цена устанавливается оператором и указывается в тарифном приложении.'}
        text = 'Цена устанавливается оператором и указывается в тарифном приложении (п. 3.6).'
        for question in ('Размер цены у оператора — 30 тыс. руб., верно?',
                         'Цену оператор установил в 30 тыс. руб., правильно?'):
            with self.subTest(question=question):
                result, _, _ = one_call(question, [answer('3.6.', 'Неверно. ' + text)] * 2, files)
                self.assertEqual(result['status'], 'partial')
                self.assertNotIn('Неверно.', result['text'])
                self.assertIn('тарифном приложении', result['text'])

    def test_an_incidental_value_is_not_a_value_request(self):
        for question in ('Гарантия заявлена на 19 месяцев. Кто определяет срок сервисного обслуживания?',
                         'Срок сервисного обслуживания составляет 19 месяцев.',
                         'Оборудование передано 13 месяцев назад. Где указан срок сервисного обслуживания?',
                         'Срок сервисного обслуживания — 19 месяцев, кто его устанавливает?',
                         'Можно ли из договора С-6/2034 сделать вывод, что срок сервисного обслуживания составляет 19 месяцев?',
                         'Договор С-6/2034 сам устанавливает срок сервисного обслуживания 19 месяцев?',
                         'В договоре прямо указан срок сервисного обслуживания 19 месяцев?'):
            with self.subTest(question=question):
                self.assertFalse(_asks_value(question))

    def test_evidential_denial_remains_a_direct_answer(self):
        text = ('Нет. Из договора нельзя сделать вывод, что срок сервисного обслуживания составляет 19 месяцев. '
                + EXPLANATION)
        result, model, _ = one_call('Можно ли из договора С-6/2034 сделать вывод, '
                                    'что срок сервисного обслуживания составляет 19 месяцев?',
                                    [answer('7.2.', text)], FILES)
        self.assertEqual(result['status'], 'answer')
        self.assertTrue(result['text'].startswith(text))
        self.assertEqual(len(model.calls), 1)

    def test_proposed_or_different_values_cannot_be_published_as_known(self):
        for assertion in ('Срок сервисного обслуживания составляет 19 месяцев.',
                          'Не 19 месяцев.', 'Указанные 19 месяцев не действуют.',
                          'Срок сервисного обслуживания составляет 37 месяцев.',
                          'Нет, подтвердить срок 19 месяцев без сервисного паспорта нельзя.'):
            with self.subTest(assertion=assertion):
                result, _, _ = one_call('Срок сервисного обслуживания ведь 19 месяцев?',
                                       [answer('7.2.', assertion + ' ' + EXPLANATION)] * 2, FILES)
                self.assertEqual(result['status'], 'partial')
                self.assertTrue(result['quote_only'])
                self.assertNotIn(assertion, result['text'])
                self.assertTrue(result['text'].startswith('Конкретное значение в найденных документах не установлено:'))
                self.assertIn('«' + SOURCE + '»', result['text'])
                self.assertIn('нужен этот документ', result['text'])

    def test_a_matching_number_in_another_contract_does_not_resolve_the_gap(self):
        files = {**{name: body.replace('Договор обслуживания', 'ДОГОВОР ОБСЛУЖИВАНИЯ')
                    for name, body in FILES.items()}, 'Договор обслуживания С-7-2034.txt':
                 'ДОГОВОР ОБСЛУЖИВАНИЯ № С-7/2034\n9.4. Срок сервисного обслуживания составляет 19 месяцев.'}
        assertion = 'Срок по договору С-6/2034 составляет 19 месяцев.'
        def response(payload):
            return {'status': 'answer', 'answer': assertion + ' ' + EXPLANATION,
                    'source_ids': [next(e['id'] for e in payload['evidence'] if e['text'].startswith(clause))
                                   for clause in ('7.2.', '9.4.')], 'requested_facts': [], 'issue': ''}
        result, _, _ = one_call('Срок сервисного обслуживания по договору С-6/2034 ведь 19 месяцев?',
                               [response] * 2, files)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(result['quote_only'])
        self.assertNotIn(assertion, result['text'])
        self.assertIn('«' + SOURCE + '»', result['text'])
        self.assertIn('Договор обслуживания № С-6/2034', result['text'])
        self.assertIn('Положение другого договора — Договор обслуживания № С-7/2034:', result['text'])
        self.assertLess(result['text'].index('Положение другого договора'), result['text'].index('«9.4.'))
        self.assertIn('нужен этот документ', result['text'])


if __name__ == '__main__':
    unittest.main()
