"""A calculation written in the answer is checked number by number.

Combined run, LegalBench-RU (lb007, lb016, lb017 and others): questions that
need arithmetic (overtime pay under Article 152, tax under the simplified
system) ended in a generic refusal. Every figure of the model text had to be
in the sources or the question, so a computed result made the text
"ungrounded"; only the quoted rule was left and the verifier rejected it as
incomplete. A new figure is now allowed when it follows, by one or two
operations, from figures of the text that are in the sources or the question
(or already follow), and stands in a sentence with a written calculation.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import answer_question, prose_grounded  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

LAW = ('Источник: Статья 152. Трудовой кодекс Российской Федерации\nСтатья 152. Оплата сверхурочной работы\n'
       'Сверхурочная работа оплачивается за первые два часа работы не менее чем в полуторном размере, '
       'за последующие часы - не менее чем в двойном размере.\n')
QUESTION = 'Ставка 300 ₽/час, отработано 4 часа сверхурочно за день. Сколько составит оплата сверхурочных?'
BASIS = QUESTION + '\n' + LAW


class CalculationTests(unittest.TestCase):
    def test_shown_calculation_passes(self):
        for text in ('Оплата составит 2100 рублей: 300 × 1,5 × 2 = 900; 300 × 2 × 2 = 1200; 900 + 1200 = 2100.',
                     'Итого 2100 рублей: первые два часа — 300 × 1,5 × 2 = 900, остальные 2 часа — 300 × 2 × 2 = 1200.'):
            self.assertTrue(prose_grounded(text, BASIS), text)

    def test_unshown_wrong_or_unrelated_figures_fail(self):
        for text in ('Оплата составит 2100 рублей.',                                   # no calculation shown
                     'Оплата: 300 × 1,5 × 2 = 900; 300 × 2 × 2 = 1200; итого 2200.',  # wrong total
                     'Оплата: 300 × 1,5 × 2 = 950 рублей.',                             # wrong step
                     'Ставка 300 рублей, а с 2025 года — 600 рублей.',                  # double, no calculation
                     'Оплата 2100 рублей за 2026-07-01: 300 × 7 = 2100.'):              # 7 is not in the basis
            self.assertFalse(prose_grounded(text, BASIS), text)

    def test_percent_rate(self):
        basis = 'Доход 2 000 000 руб. Налоговая ставка устанавливается в размере 6 процентов.'
        self.assertTrue(prose_grounded('Налог 120 000 рублей: 2 000 000 × 6% = 120 000.', basis))
        self.assertFalse(prose_grounded('Налог 130 000 рублей: 2 000 000 × 6% = 130 000.', basis))

    def test_calculated_answer_is_published(self):
        text = 'Оплата составит 2100 рублей: 300 × 1,5 × 2 = 900; 300 × 2 × 2 = 1200; 900 + 1200 = 2100.'

        def generate(payload):
            fid = next(e['id'] for e in payload['evidence'] if 'полуторном' in e['text'])
            return {'status': 'answer', 'answer': text, 'source_ids': [fid], 'requested_facts': [], 'issue': ''}
        verdict = {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
                   'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}
        with corpus({'tk152.txt': LAW}) as r:
            published, status = answer_question(QUESTION, r, ScriptedModel([generate, verdict]))
        self.assertEqual(status, 'answer')
        self.assertTrue(published.startswith(text))


if __name__ == '__main__':
    unittest.main()


class CalculationBasisWithDottedNumbersTests(unittest.TestCase):
    """Diagnostic set on the organizer base (PSB_AB_20_vs_24, N21): every law of
    the base has «Дата выгрузки: 10.10.2026» in its header; that figure did not
    convert to a number, the error was caught and the check failed, so every
    calculation relying on a law was rejected and the answer became a refusal."""

    def test_dotted_figures_in_the_basis_do_not_break_the_check(self):
        from psb_policy import calculation_shown
        basis = ('Исходный штраф 45 000 рублей по пункту 3 статьи 87 учебного кодекса\n'
                 'Источник: Статья 87. Учебный кодекс\nURL: https://example.invalid/30400100/5e1d9a/\n'
                 'Дата выгрузки: 03.04.2031\nСм. также п. 1.2.3 приложения.\n'
                 '3. При наличии отягчающего обстоятельства размер штрафа увеличивается на 100 процентов.')
        self.assertTrue(calculation_shown('Штраф составит 90 000 рублей: 45 000 + 45 000 = 90 000.', basis))
        self.assertFalse(calculation_shown('Штраф составит 95 000 рублей: 45 000 + 45 000 = 95 000.', basis))
