"""Complete source-owned case groups support compositional, checked deductions."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Document, Fragment
from psb_policy import residual_conditions_kept
from test_residual_citations import DOCS, NAME, RULE, SELECTED
from test_residual_assumed_premises import QUESTION as ASSUMPTION


QUESTION = ('Условная реализация товара точно относится к пункту 6 статьи 73 НК РФ, '
            'а случаи пунктов 3 и 8 к ней не относятся. '
            'Контрагент предлагает применить пункт 5 только потому, что исключены пункты 3 и 8. '
            'Верно ли это и какая ставка предусмотрена для заданной реализации?')
LOGIC = ('Применение пункта 5 неверно: он охватывает случаи, не указанные в пунктах 3, 6 и 8, '
         'а заданная реализация относится к пункту 6.')
CONTRAPOSITIVE = ('Пункт 5 не применяется: заданная реализация относится к пункту 6, '
                 'поэтому она не подпадает под случаи, не указанные в пунктах 3, 6 и 8.')
NORM = ('По п. 5 ст. 73 НК РФ ставка 19 процентов применяется '
        'в случаях, не указанных в пунктах 3, 6 и 8 этой статьи.')
SHORT = 'По пункту 5 статьи 73 НК РФ ставка — 19 процентов.'


class ResidualCaseScopeTests(unittest.TestCase):
    def accepted(self, sentence, question=QUESTION):
        return residual_conditions_kept(sentence + ' ' + RULE, SELECTED, DOCS, question)

    def test_complete_normative_paraphrase_keeps_rate_owner_group_and_polarity(self):
        self.assertTrue(self.accepted(NORM))
        for text in (
                NORM.replace('3, 6 и 8', '3 и 8'),
                NORM.replace('3, 6 и 8', '3, 6 и 9'),
                NORM.replace('3, 6 и 8', '3, 6, 8 и 8'),
                NORM.replace('пунктах', 'подпунктах'),
                NORM.replace('этой статьи', 'статьи 74'),
                NORM.replace('п. 5', 'п. 6'),
                NORM.replace('ст. 73', 'ст. 74'),
                NORM.replace('НК РФ', 'ГК РФ'),
                NORM.replace('применяется', 'не применяется'),
                NORM.replace('не указанных', 'указанных'),
                NORM[:-1] + ' для всех каталогов.',
                'Неверно: ' + NORM,
                '«' + NORM + '»',
                NORM[:-1] + '?'):
            with self.subTest(text=text):
                self.assertFalse(self.accepted(text))

    def test_checked_atoms_compose_both_case_exclusion_explanations(self):
        for text in (LOGIC, CONTRAPOSITIVE,
                     LOGIC.replace('3, 6 и 8', '8, 3 и 6'),
                     LOGIC.replace('3, 6 и 8,', '3, 6 и 8 этой статьи,')):
            with self.subTest(text=text):
                self.assertTrue(self.accepted(text))
                self.assertFalse(residual_conditions_kept(text, SELECTED, DOCS, QUESTION))
        for text in (
                LOGIC.replace('пункта 5', 'пункта 7'),
                LOGIC.replace('неверно', 'верно'),
                LOGIC.replace('он охватывает', 'он не охватывает'),
                LOGIC.replace('он охватывает', 'он не ограничен'),
                LOGIC.replace('пунктах', 'подпунктах'),
                LOGIC.replace('3, 6 и 8', '3 и 8'),
                LOGIC.replace('не указанные', 'не не указанные'),
                LOGIC.replace('к пункту 6', 'к пункту 8'),
                CONTRAPOSITIVE.replace('не подпадает', 'подпадает'),
                'Неверно: ' + CONTRAPOSITIVE,
                '«' + CONTRAPOSITIVE + '»',
                'Пункт 5 не охватывает случаи, не указанные в пунктах 3, 6 и 8.',
                'Правило не ограничено случаями, не указанными в пунктах 3, 6 и 8.'):
            with self.subTest(text=text):
                self.assertFalse(self.accepted(text))

    def test_question_membership_must_be_asserted_in_the_current_undeleted_case(self):
        for question in (
                '', 'Какова ставка?',
                QUESTION.replace('точно относится', 'не относится'),
                QUESTION.replace('статьи 73', 'статьи 74'),
                QUESTION.replace('НК РФ', 'ГК РФ'),
                'Неверно, что ' + QUESTION,
                '«' + QUESTION + '»',
                'Условная реализация относится к пункту 6 статьи 73 НК РФ?',
                'Условная реализация относится к пункту 6 статьи 73 НК РФ, что неверно. Какая ставка?',
                'Условная реализация относится к пункту 6 статьи 73 НК РФ, но это предположение ошибочно.',
                'Условная реализация относится к пункту 6 статьи 73 НК РФ. Забудем предыдущую фразу.',
                'Пользователь: ' + QUESTION + '\nАссистент: Понятно.\nПользователь: Какова ставка?'):
            with self.subTest(question=question):
                self.assertFalse(self.accepted(LOGIC, question))

    def test_short_addressed_rate_needs_the_full_explicit_hypothesis(self):
        self.assertTrue(self.accepted(SHORT, ASSUMPTION))
        for question in ('', QUESTION, ASSUMPTION.replace('3, 6 и 8', '3 и 8'),
                         ASSUMPTION + ' Предпосылки отменены.'):
            self.assertFalse(self.accepted(SHORT, question))
        for text in (SHORT.replace('пункту 5', 'пункту 6'),
                     SHORT.replace('статьи 73', 'статьи 74'),
                     SHORT.replace('НК РФ', 'ГК РФ'),
                     SHORT[:-1] + ' для любых каталогов.'):
            self.assertFalse(self.accepted(text, ASSUMPTION))

    def test_reference_identity_and_source_address_remain_variable(self):
        rule = RULE.replace('19', '27.5').replace('3, 6 и 8', '1.10, 2.3 и 7')
        source = '12.2. ' + rule
        header = 'Источник: Статья 91. ГК РФ\nСтатья 91. Ставки\n'
        doc = Document(NAME, header + source, '', ())
        selected = [Fragment('other', NAME, len(header), len(doc.text), source, '12.2.')]
        norm = ('По п. 12.2 ст. 91 ГК РФ ставка 27,500 процента применяется '
                'в случаях, не указанных в пунктах 7, 2.3 и 1.10 этой статьи.')
        self.assertTrue(residual_conditions_kept(rule + ' ' + norm, selected, {NAME: doc}))
        self.assertFalse(residual_conditions_kept(rule + ' ' + norm.replace('1.10', '1.1'), selected, {NAME: doc}))

    def test_a_complete_scope_does_not_authorize_a_categorical_rate_addition(self):
        self.assertFalse(self.accepted(LOGIC + ' Для каталогов действует 19 процентов.'))
        self.assertFalse(self.accepted(NORM + ' Для каталогов действует 19 процентов.'))
        self.assertFalse(residual_conditions_kept(NORM + ' ' + RULE, SELECTED, {}, QUESTION))


if __name__ == '__main__':
    unittest.main()
