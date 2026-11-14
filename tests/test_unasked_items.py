"""A lexical overlap heuristic must not delete grounded parts of an answer.

Open enumeration questions can ask for words not explicitly present in the
question. A final list item can also carry a condition applying to the whole
list. Re-generating a safe answer just to remove such an item loses requested
information or the condition. Actual unsupported numbers still require repair.
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

    def test_grounded_detail_does_not_trigger_deletion_retry(self):
        result, model, _ = one_call(QUESTION, [answer('3.4.', FULL), answer('3.4.', SHORT)], FILES)
        self.assertEqual(len(model.calls), 1)
        self.assertTrue(result['text'].startswith(FULL), result['text'])

    def test_text_still_naming_it_is_published_not_the_provision(self):
        result, model, _ = one_call(QUESTION, [answer('3.4.', FULL), answer('3.4.', FULL)], FILES)
        self.assertEqual(len(model.calls), 1)
        self.assertTrue(result['text'].startswith(FULL), result['text'])
        self.assertFalse(result['quote_only'])

    def test_open_enumeration_keeps_the_requested_other_items(self):
        files = {'Договор обслуживания М-19-2032.txt': 'Договор обслуживания № М-19/2032\n'
                 '7.8. Цена включает монтаж, доставку и упаковку.\n'}
        question = 'Кроме монтажа, что ещё входит в цену по договору М-19/2032?'
        full = 'Кроме монтажа, цена включает доставку и упаковку (п. 7.8).'
        incomplete = 'Цена включает монтаж (п. 7.8).'
        result, model, _ = one_call(question, [answer('7.8.', full), answer('7.8.', incomplete)], files)
        self.assertIn('доставку и упаковку', result['text'])
        self.assertEqual(len(model.calls), 1)

    def test_condition_after_last_list_item_is_preserved(self):
        files = {'Договор обслуживания М-19-2032.txt': 'Договор обслуживания № М-19/2032\n'
                 '7.8. Цена включает монтаж, доставку и упаковку при заказе от 900 000 рублей.\n'}
        question = 'Входит ли монтаж в цену по договору М-19/2032?'
        full = 'Монтаж включён в цену при заказе от 900 000 рублей (п. 7.8).'
        unconditional = 'Монтаж включён в цену (п. 7.8).'
        result, model, _ = one_call(question, [answer('7.8.', full), answer('7.8.', unconditional)], files)
        self.assertIn('при заказе от 900 000 рублей', result['text'])
        self.assertEqual(len(model.calls), 1)

    def test_unsupported_extra_number_still_requires_repair(self):
        unsupported = FULL.replace('7%', '8%')
        result, model, _ = one_call(QUESTION, [answer('3.4.', unsupported), answer('3.4.', FULL)], FILES)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1][1].get('retry_reason'), 'answer_numbers_not_in_sources')
        self.assertNotIn('8%', result['text'])
        self.assertIn('7%', result['text'])


if __name__ == '__main__':
    unittest.main()
