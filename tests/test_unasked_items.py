"""An element of a listing that the question does not ask about gets one retry.

Same-time runs of 13 November, demo 16 and its paraphrases: «Доставка и упаковка
включены в цену?» was answered «цена включает НДС по ставке 20%, стоимость
упаковки и доставки» in 2 of 4 runs even with the prompt rule of archive 22. VAT
is in the clause but was not asked, and the judge analogue zeroed the answer.
The batch now retries once naming the extra element; a text that still names it
is published rather than the bare provisions (the fact is true).
"""
from pathlib import Path
import sys
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'), str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment  # noqa: E402
from psb_policy import unasked_items  # noqa: E402
from test_one_call_answers import answer, one_call  # noqa: E402

CLAUSE = '3.4. Стоимость работ включает налог по ставке 7%, вывоз мусора и уборку территории.'
FILES = {'Договор подряда Р-5-2031.txt': 'Договор подряда № Р-5/2031\n' + CLAUSE + '\n'}
SRC = [Fragment('a', 'd', 0, 1, CLAUSE, '')]
FULL = 'Да, вывоз мусора и уборка входят в стоимость: она включает налог по ставке 7%, вывоз мусора и уборку территории (п. 3.4).'
SHORT = 'Да, вывоз мусора и уборка территории входят в стоимость работ и отдельно не оплачиваются (п. 3.4).'
QUESTION = 'Входят ли вывоз мусора и уборка в стоимость работ по договору Р-5/2031?'


class UnaskedItemTests(unittest.TestCase):
    def test_detection(self):
        self.assertEqual(unasked_items(FULL, SRC, QUESTION), ['налог по ставке 7%'])
        self.assertEqual(unasked_items(SHORT, SRC, QUESTION), [])
        # Synonyms only: which elements were asked is unknown, nothing is claimed.
        self.assertEqual(unasked_items(FULL, SRC, 'Включены ли утилизация отходов и клининг в цену по Р-5/2031?'), [])
        # A single-element listing («…в месяц, включая НДС») is the value itself.
        rent = [Fragment('b', 'd', 0, 1, '2.1. Плата составляет 90 000 рублей в месяц, включая НДС.', '')]
        self.assertEqual(unasked_items('Плата — 90 000 рублей в месяц, включая НДС (п. 2.1).', rent, 'Какая плата?'), [])

    def test_retry_drops_the_element(self):
        result, model, _ = one_call(QUESTION, [answer('3.4.', FULL), answer('3.4.', SHORT)], FILES)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1][1].get('retry_reason'), 'answer_extra_items')
        self.assertEqual(model.calls[1][1].get('retry_extra_items'), ['налог по ставке 7%'])
        self.assertTrue(result['text'].startswith(SHORT), result['text'])

    def test_text_still_naming_it_is_published_not_the_provision(self):
        result, model, _ = one_call(QUESTION, [answer('3.4.', FULL), answer('3.4.', FULL)], FILES)
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(result['text'].startswith(FULL), result['text'])
        self.assertFalse(result['quote_only'])


if __name__ == '__main__':
    unittest.main()
