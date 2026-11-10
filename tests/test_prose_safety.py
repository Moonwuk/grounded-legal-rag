"""Regression checks for the submitted prose patch, using approving stubs."""
from pathlib import Path
import io
import sys
from contextlib import redirect_stderr
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from psb_corpus import load_corpus
from psb_retrieval import Retriever
from psb_policy import answer_question, prose_grounded
from test_baseline import ScriptedModel
from test_prose_answers import run, select, confirm


class ProseSafetyTests(unittest.TestCase):
    def test_reference_numbers_do_not_replace_missing_basis_notice(self):
        docs, fragments = load_corpus(ROOT / 'organizer/knowledge-base.zip')
        prose = ('Доказательство согласия или наличия оснований статей 6, 10 и 11 '
                 'должен предоставить оператор.')
        # Select the obligation paragraph, which does not trigger source_only.
        # Thus this regression exercises the prose renderer's mandatory notice.
        model = ScriptedModel([select('3. Обязанность', prose), confirm()])
        with redirect_stderr(io.StringIO()):
            text, status = answer_question('Человек отозвал согласие. Удалить всё?', Retriever(docs, fragments), model)
        self.assertEqual(status, 'partial')
        self.assertTrue(text.startswith(prose))
        self.assertIn('В предоставленной базе не найдены тексты отсылочных статей 6, 10, 11', text)

    def test_word_numerals_are_checked_as_quantities(self):
        basis = 'Срок оплаты — 37 дней. Испытание — 6 месяцев.'
        for wrong in ('девяноста', 'девяносто', 'сто двадцать', 'тридцать пять', 'ноль'):
            with self.subTest(wrong=wrong):
                self.assertFalse(prose_grounded('Срок оплаты — ' + wrong + ' дней.', basis))
        self.assertTrue(prose_grounded('Срок оплаты — тридцать семь дней.', basis))
        self.assertTrue(prose_grounded('Испытание — шести месяцев.', basis))
        self.assertTrue(prose_grounded('Лимит — тридцать семь тысяч двести рублей.', 'Лимит — 37 200 рублей.'))
        false_text = 'Оплата производится в течение девяноста календарных дней.'
        text, status, _, _ = run('Каков срок оплаты?',
            [select('3.1.', false_text), confirm(), select('3.1.', false_text), confirm()])
        self.assertEqual(status, 'answer')
        self.assertNotIn(false_text, text)
        self.assertIn('37', text)

    def test_huge_number_in_user_facts_preserves_verified_source_fallback(self):
        prose = 'Оплата производится в течение 37 календарных дней.'
        text, status, _, _ = run('Срок оплаты? ' + '9' * 5000,
            [select('3.1.', prose), confirm(), select('3.1.', prose), confirm()])
        self.assertEqual(status, 'answer')
        self.assertIn('«3.1. Оплата производится в течение 37', text)

    def test_huge_scaled_number_is_rejected_without_raising(self):
        self.assertFalse(prose_grounded('Сумма ' + '9' * 310 + ' млн рублей.', 'Сумма — 37 рублей.'))

    def test_scaled_amount_does_not_use_binary_floating_point(self):
        self.assertTrue(prose_grounded('Лимит 123456789012345678.901 млн рублей.',
                                      'Лимит 123456789012345678901000 рублей.'))

    def test_negative_permissions_use_source_wording_even_if_verifier_approves(self):
        for provision, false_text in (
            ('4.2. Арендатор не вправе сдавать помещение без письменного согласия.',
             'Да. Арендатор вправе сдавать помещение без письменного согласия.'),
            ('4.2. Передача оборудования запрещена.', 'Передача оборудования разрешена.'),
        ):
            with self.subTest(provision=provision):
                text, status, _, _ = run('Можно сдавать помещение или передавать оборудование без согласия?', [select('4.2.', false_text), confirm()],
                                         {'Договор.txt': provision})
                self.assertEqual(status, 'answer')
                self.assertNotIn(false_text, text)
                self.assertIn('«' + provision + '»', text)

    def test_conditional_permission_cannot_lose_its_condition(self):
        source = '2.1. Только при наличии письменного согласия допускается вывоз оборудования.'
        false_text = 'Вывоз оборудования допускается без ограничений.'
        text, status, _, _ = run('Можно вывезти оборудование?', [select('2.1.', false_text), confirm()],
                                 {'Положение.txt': source})
        self.assertEqual(status, 'answer')
        self.assertNotIn(false_text, text)
        self.assertIn(source, text)

    def test_no_source_free_legal_text_can_escape_as_a_refusal(self):
        prose = 'В базе нет договора. Обработку персональных данных можно продолжать без согласия.'
        def absent(payload):
            return {'status': 'insufficient', 'answer': prose, 'source_ids': [], 'requested_facts': ['document']}
        text, status, _, _ = run('Нужен договор?', [absent, absent, confirm()])
        self.assertEqual(status, 'insufficient')
        self.assertNotIn('можно продолжать без согласия', text)
        self.assertIn('недостаточно оснований', text)


if __name__ == '__main__':
    unittest.main()
