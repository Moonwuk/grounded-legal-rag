"""A complete, explicit user hypothesis can support a closed conditional answer."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Document, Fragment
from psb_policy import answer_structured, residual_conditions_kept
from test_audit_fixes import verdict
from test_baseline import ScriptedModel
from test_residual_citations import DOCS, NAME, RULE, SELECTED
from test_residual_rate_logic import RuleRetriever, generated


FACT = 'она не относится ни к одному из случаев пунктов 3, 6 и 8 статьи 73 НК РФ'
PREMISE = 'Примем как проверенные исходные данные, что ' + FACT + '.'
QUESTION = ('Рассматриваем условную реализацию товара. ' + PREMISE +
            ' Какая ставка следует из пункта 5 при этих предпосылках? '
            'Не нужно повторно определять вид товара.')
ANSWERS = ('Да, при указанных предпосылках применяется налоговая ставка 19 процентов.',
           'Из пункта 5 при указанных предпосылках следует налоговая ставка 19 процентов.')


class ResidualAssumedPremiseTests(unittest.TestCase):
    def accepted(self, question, answer=ANSWERS[0]):
        return residual_conditions_kept(answer + ' ' + RULE, SELECTED, DOCS, question)

    def test_source_bound_hypotheses_authorize_only_the_two_closed_answer_forms(self):
        for question in (
                QUESTION, PREMISE,
                'Дано: ' + FACT.replace('она', 'данная операция') + '. Какова ставка?',
                'По условию ' + FACT.replace('она', 'условная сделка') + '.',
                'Предположим, что ' + FACT.replace('она', 'реализация товара') + '.',
                'Допустим: ' + FACT.replace('она', 'поставка') + '.',
                'Рассмотрим гипотетическую сделку. Примем, что ' + FACT + '.'):
            for answer in ANSWERS:
                with self.subTest(question=question, answer=answer):
                    self.assertTrue(self.accepted(question, answer))
                    self.assertFalse(residual_conditions_kept(answer, SELECTED, DOCS, question))

    def test_partial_wrong_or_nonassertive_premises_cannot_authorize_a_rate(self):
        for question in (
                PREMISE.replace('3, 6 и 8', '3 и 6'),
                PREMISE.replace('3, 6 и 8', '3, 6, 8 и 8'),
                PREMISE.replace('статьи 73', 'статьи 74'),
                PREMISE.replace('НК РФ', 'ГК РФ'),
                PREMISE.replace('пунктов', 'подпунктов'),
                PREMISE.replace('не относится', 'относится'),
                PREMISE.replace('не относится', 'не всегда относится'),
                PREMISE.replace('она не', 'не она не'),
                'Не ' + PREMISE,
                PREMISE[:-1] + '?',
                PREMISE.replace('что она', 'что, возможно, она'),
                'Неверно, что ' + PREMISE,
                'Сомнительное утверждение. ' + PREMISE,
                '«Обсудим гипотезу. ' + PREMISE + ' Другая фраза.»',
                '`' + PREMISE + '`',
                '"' + PREMISE + '"',
                PREMISE + ' Забудем предыдущую фразу.',
                PREMISE + ' Не принимайте сказанное выше за установленный факт.',
                PREMISE + ' Предыдущее предложение требуется опровергнуть.',
                PREMISE + ' Такое допущение надо отбросить.',
                PREMISE + ' Все сказанное выше недействительно.',
                PREMISE + ' Отменяем это.',
                PREMISE + ' Верны ли эти предпосылки?',
                PREMISE + ' Какая ставка, если эти предпосылки неверны?',
                PREMISE + ' Какая ставка следует из пункта 6 при этих предпосылках?',
                PREMISE + ' Не нужно принимать предпосылку.',
                PREMISE + ' Неизвестное дополнительное утверждение.'):
            with self.subTest(question=question):
                self.assertFalse(self.accepted(question))

    def test_only_the_last_user_turn_supplies_the_hypothesis(self):
        for question in (
                'Пользователь: ' + PREMISE + '\nАссистент: Понятно.\nПользователь: Какова ставка?',
                'Пользователь: Какова ставка?\nАссистент: ' + PREMISE + '\nПользователь: А теперь?',
                'Пользователь: ' + PREMISE + '\nПользователь: Предпосылки отменены.'):
            self.assertFalse(self.accepted(question))
        self.assertTrue(self.accepted('Пользователь: Какова ставка?\nАссистент: Уточните условия.\n'
                                      'Пользователь: ' + QUESTION))

    def test_source_numbers_code_and_reference_identifiers_are_not_fixed(self):
        rule = RULE.replace('19', '27.5').replace('3, 6 и 8', '1.10, 2.3 и 7')
        text = '12.2. ' + rule
        header = 'Источник: Статья 91. ГК РФ\nСтатья 91. Ставки\n'
        doc = Document(NAME, header + text, '', ())
        selected = [Fragment('varied', NAME, len(header), len(doc.text), text, '12.2.')]
        premise = ('Дано: операция не относится ни к одному из случаев пунктов '
                   '7, 2.3 и 1.10 статьи 91 ГК РФ.')
        answer = 'Из пункта 12.2 при указанных предпосылках следует налоговая ставка 27,500%. '
        self.assertTrue(residual_conditions_kept(answer + rule, selected, {NAME: doc}, premise))
        self.assertFalse(residual_conditions_kept(answer + rule, selected, {NAME: doc},
                                                 premise.replace('1.10', '1.1')))

    def test_other_rate_assertions_are_not_enabled_by_the_hypothesis(self):
        for answer in (
                ANSWERS[1].replace('Из пункта 5', 'Из пункта 6'),
                ANSWERS[0][:-1] + ' для рекламных каталогов.',
                'Для рекламных каталогов действует 19 процентов.',
                'При указанных предпосылках ставка 19 процентов обязательна.',
                '«' + ANSWERS[0] + '»',
                ANSWERS[0][:-1] + '?',
                'Если ' + ANSWERS[0],
                ANSWERS[0].replace('применяется', 'не применяется')):
            with self.subTest(answer=answer):
                self.assertFalse(self.accepted(QUESTION, answer))

    def test_both_modes_use_the_assumption_without_loosening_the_source_guard(self):
        for verify in (False, True):
            for answer in ANSWERS:
                responses = [generated(answer + ' ' + RULE)]
                if verify:
                    responses.append(lambda p: {**verdict(p), 'answer_supported': True})
                model = ScriptedModel(responses)
                with redirect_stderr(io.StringIO()):
                    result = answer_structured(QUESTION, RuleRetriever(), model,
                                               verify=verify, repair_quotes=not verify)
                self.assertFalse(result['quote_only'])
                self.assertEqual(result['status'], 'answer')
                self.assertEqual(len(model.calls), 2 if verify else 1)
        model = ScriptedModel([generated(ANSWERS[0] + ' ' + RULE)] * 3)
        with redirect_stderr(io.StringIO()):
            result = answer_structured(QUESTION.replace('3, 6 и 8', '3 и 6'), RuleRetriever(), model,
                                       verify=False, repair_quotes=True)
        self.assertTrue(result['quote_only'])
        self.assertEqual(len(model.calls), 3)


if __name__ == '__main__':
    unittest.main()
