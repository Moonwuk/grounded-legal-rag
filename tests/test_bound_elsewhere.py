"""A conditional upper bound for another situation is not printed under the answer.

Same-time runs of 13 November, question «предельный срок испытания для главного
бухгалтера»: every answer ended with the appended source sentence «При заключении
трудового договора на срок от двух до шести месяцев испытание не может
превышать двух недель» — an exception for short contracts the question does not
describe. The judge counts an unasked detail as invented. The bound is still
printed when the question describes its situation, and still kept for
verification (complete_sources).
"""
from pathlib import Path
import sys
import unittest
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'), str(Path(__file__).resolve().parent)]
from test_prose_answers import confirm, run, select  # noqa: E402

LAW = {'законы__УчК_ст41_действующая.txt':
       'Учебный кодекс\n\nСтатья 41. Стажировка\n\n'
       'Срок стажировки не может превышать двух месяцев, а для старших инженеров и их заместителей — '
       'четырёх месяцев, если иное не установлено законом.\n\n'
       'При заключении ученического договора на срок до одного года стажировка не может превышать десяти дней.\n'}
BOUND = 'При заключении ученического договора на срок до одного года стажировка не может превышать десяти дней.'
DRAFT = 'Для старшего инженера срок стажировки не может превышать четырёх месяцев (ст. 41).'


class BoundElsewhereTests(unittest.TestCase):
    def test_bound_for_another_situation_is_not_printed(self):
        for question in ('Какой предельный срок стажировки для старшего инженера?',
                         'Сколько максимум может длиться стажировка старшего инженера?'):
            with self.subTest(question):
                text, status, _, _ = run(question, [select('Срок стажировки', DRAFT), confirm()], LAW)
                self.assertEqual(status, 'answer')
                self.assertTrue(text.startswith(DRAFT), text)
                self.assertNotIn('десяти дней', text)

    def test_bound_is_printed_when_the_question_describes_its_situation(self):
        question = 'Какой предельный срок стажировки старшего инженера, если ученический договор заключён на полгода?'
        text, _, _, _ = run(question, [select('Срок стажировки', DRAFT), confirm()], LAW)
        self.assertIn(BOUND, text)

    def test_bound_restated_by_the_text_is_not_repeated(self):
        # N15 of the same run: the text repeated the bound word for word and the
        # quotation followed it again (its final period defeated the comparison).
        question = 'Ученический договор заключён на полгода. Можно ли стажировку старшего инженера на месяц?'
        draft = ('Нет. При заключении ученического договора на срок до одного года стажировка не может превышать '
                 'десяти дней, поэтому месяц установить нельзя (ст. 41).')
        text, _, _, _ = run(question, [select('При заключении', draft), confirm()], LAW)
        self.assertEqual(text.count('не может превышать десяти дней'), 1, text)


if __name__ == '__main__':
    unittest.main()
