"""Rejected numeral experiments must not reappear through retry diagnostics."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from test_one_call_answers import answer, one_call


class RetryGuardPreservationTests(unittest.TestCase):
    def test_incidental_first_day_does_not_authorize_one_day_payment(self):
        files = {'Договор.txt': 'Договор\n4.2. Срок оплаты составляет 20 дней.'}
        bad = 'Срок оплаты составляет 1 день (п. 4.2).'
        result, model, _ = one_call('Сегодня день — первый в отпуске. Какой срок оплаты?',
                                   [answer('4.2.', bad)] * 2, files)
        self.assertTrue(result['quote_only'])
        self.assertNotIn('составляет 1 день', result['text'])
        self.assertIn('20 дней', result['text'])
        self.assertEqual(len(model.calls), 2)

    def test_incidental_first_hour_does_not_authorize_one_ruble(self):
        files = {'Договор.txt': 'Договор\n4.2. Размер пени устанавливается отдельным соглашением.'}
        bad = 'Размер пени составляет 1 рубль (п. 4.2).'
        result, _, _ = one_call('Час — первый в новой смене. Каков размер пени?',
                               [answer('4.2.', bad)] * 2, files)
        self.assertNotIn('составляет 1 рубль', result['text'])

    def test_last_two_hours_do_not_support_first_two_hours(self):
        files = {'Порядок.txt': 'Порядок\n4.2. Последним двум часам дежурства соответствует повышенная оплата.'}
        bad = 'Первым двум часам дежурства соответствует повышенная оплата (п. 4.2).'
        result, _, _ = one_call('Как оплачивается начало дежурства?',
                               [answer('4.2.', bad)] * 2, files)
        self.assertFalse(result['text'].startswith(bad), result['text'])
        self.assertIn('Последним двум', result['text'])

    def test_supported_predicate_keeps_the_original_one_call_path(self):
        files = {'Порядок.txt': 'Порядок\n4.2. День начала учёта является первым в новом периоде и оплачивается с надбавкой.'}
        good = 'День — первый в новом периоде и оплачивается с надбавкой (п. 4.2).'
        result, model, _ = one_call('Как учитывается и оплачивается день начала учёта?',
                                   [answer('4.2.', good)], files)
        self.assertTrue(result['text'].startswith(good), result['text'])
        self.assertEqual(len(model.calls), 1)


if __name__ == '__main__':
    unittest.main()
