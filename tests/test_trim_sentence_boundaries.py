"""Deleting an assertion must not leave its address/title prefix behind."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import _trim_sentences, scope_block_reason, without_blocked_sentence


FIRST = 'Прежний адрес доставки указан в договоре: г. Бережск, ул. Речная, д. 7.'
ADDRESS = 'Новый адрес — г. Озёрск, ул. Каменная, д. 12'
LAST = 'Прежний адрес указан в основном договоре поставки.'


class TrimSentenceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.retriever = SimpleNamespace(documents={})
        self.selected = [Fragment('a', 'Договор', 0, 1, FIRST, ''),
                         Fragment('b', 'Изменение', 0, 1, ADDRESS + '.', '')]

    def test_whole_address_assertion_is_removed_without_a_dangling_street(self):
        bad = ADDRESS + ' — применяется только по вторникам.'
        draft = FIRST + ' ' + bad + ' ' + LAST
        self.assertTrue(scope_block_reason(draft, self.selected, self.retriever))
        result = without_blocked_sentence(draft, self.selected, self.retriever)
        self.assertEqual(result, FIRST + ' ' + LAST)
        self.assertNotIn('Озёрск', result)
        self.assertFalse(scope_block_reason(result, self.selected, self.retriever))

    def test_end_of_year_does_not_consume_the_following_explanation(self):
        bad = ADDRESS + ' — применяется только после 1 апреля 2032 г.'
        self.assertEqual(without_blocked_sentence(FIRST + ' ' + bad + ' ' + LAST,
                                                 self.selected, self.retriever), FIRST + ' ' + LAST)

    def test_initials_titles_and_article_labels_stay_inside_the_assertion(self):
        for prefix in ('Директор А. Б. Берегов', 'Доклад проф. А. Б. Берегова',
                       'Правило ст. Учебного кодекса', 'Отделение пос. Озёрный'):
            with self.subTest(prefix=prefix):
                draft = FIRST + ' ' + prefix + ' действует только по понедельникам.'
                self.assertEqual(without_blocked_sentence(draft, self.selected, self.retriever), FIRST)

    def test_false_first_assertion_cannot_be_rescued_by_deleting_its_tail(self):
        draft = 'Правило ст. Учебного кодекса действует только по понедельникам. ' + FIRST
        result = without_blocked_sentence(draft, self.selected, self.retriever)
        self.assertEqual(result, draft)
        self.assertTrue(scope_block_reason(result, self.selected, self.retriever))

    def test_completed_numbers_citations_and_measurements_keep_real_boundaries(self):
        for first in (FIRST, 'Применяется пункт 4.2. Отчёт проверяется.',
                      'Адрес указан в договоре (п. 4.2). Отчёт проверяется.',
                      'Плата составляет 800 руб. Отчёт проверяется.',
                      'Срок составляет 8 мес. Отчёт проверяется.',
                      'Хранятся акты, счета и т. д. Отчёт проверяется.'):
            with self.subTest(first=first):
                self.assertGreaterEqual(len(_trim_sentences(first + ' Только директор вправе менять срок.')), 2)
                self.assertEqual(_trim_sentences(first + ' Только директор вправе менять срок.')[-1],
                                 'Только директор вправе менять срок.')

    def test_many_address_abbreviations_keep_one_assertion(self):
        first = 'Адреса: ' + ', '.join(f'г. Бережск, ул. Речная, д. {n}' for n in range(1, 70)) + '.'
        self.assertEqual(_trim_sentences(first + ' Следующее предложение.'),
                         [first, 'Следующее предложение.'])


if __name__ == '__main__':
    unittest.main()
