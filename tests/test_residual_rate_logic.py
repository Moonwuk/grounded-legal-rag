"""Closed deductions retain the exact residual reference group and its owner."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Document, Fragment
from psb_policy import (_residual_logic_context, _residual_rate_logic,
                        answer_structured, residual_conditions_kept)
from test_audit_fixes import verdict
from test_baseline import ScriptedModel
from test_residual_citations import DOC, DOCS, HEADER, NAME, RULE, SELECTED, SOURCE


INSUFFICIENT = ('Нет, проверки неприменимости пункта 6 недостаточно '
                'для обоснования ставки 19% по пункту 5.')
CONDITIONAL = ('Если ни один из пунктов 3, 6 и 8 не применяется, '
               'ставка 19% по пункту 5 обоснована.')


class RuleRetriever:
    documents = DOCS

    def search(self, *args, **kwargs):
        return SELECTED

    def evidence(self, fragments):
        return [{'id': f.id, 'document': f.document, 'text': f.text} for f in fragments]


def generated(text):
    return {'status': 'answer', 'answer': text, 'source_ids': ['f'],
            'requested_facts': [], 'issue': ''}


class ResidualRateLogicTests(unittest.TestCase):
    def test_closed_subset_insufficiency_and_full_set_condition_keep_their_logic(self):
        for sentence in (
                INSUFFICIENT,
                INSUFFICIENT.replace('пункта 6', 'пунктов 3 и 6'),
                CONDITIONAL,
                CONDITIONAL.replace('3, 6 и 8', '8, 3 и 6'),
                CONDITIONAL.replace('19%', '19,0000 процента').replace('обоснована', 'применяется'),
                CONDITIONAL.replace('3, 6 и 8', '3, 6 и 8 настоящей статьи')):
            with self.subTest(sentence=sentence):
                self.assertTrue(residual_conditions_kept(RULE + ' ' + sentence, SELECTED, DOCS))
                self.assertFalse(residual_conditions_kept(sentence, SELECTED, DOCS))

    def test_partial_group_inversion_wrong_owner_or_extra_qualifier_never_authorize_a_rate(self):
        for sentence in (
                CONDITIONAL.replace('3, 6 и 8', '3 и 6'),
                CONDITIONAL.replace('3, 6 и 8', '3, 6, 8 и 8'),
                CONDITIONAL.replace('3, 6 и 8', '3, 6 и 9'),
                CONDITIONAL.replace('не применяется', 'применяется'),
                CONDITIONAL.replace('ни один', 'один'),
                CONDITIONAL.replace('пунктов', 'подпунктов'),
                CONDITIONAL.replace('по пункту 5', 'по пункту 6'),
                CONDITIONAL.replace('3, 6 и 8', '3, 6 и 8 статьи 74'),
                CONDITIONAL[:-1] + ' при наличии разрешения.',
                CONDITIONAL[:-1] + '?',
                'Неверно, что ' + CONDITIONAL,
                'Вопрос содержит: «' + CONDITIONAL + '»',
                INSUFFICIENT.replace('пункта 6', 'пункта 7'),
                INSUFFICIENT.replace('пункта 6', 'пунктов 3, 6 и 8'),
                INSUFFICIENT.replace('пункта 6', 'пунктов 6 и 6'),
                INSUFFICIENT.replace('пункта 6', 'подпункта 6'),
                INSUFFICIENT.replace('недостаточно', 'достаточно'),
                INSUFFICIENT.replace('недостаточно', 'не недостаточно'),
                INSUFFICIENT.replace('по пункту 5', 'по пункту 3'),
                INSUFFICIENT.replace('пункта 6', 'пункта 6 статьи 74'),
                'Для отдельной категории действует 19%.'):
            with self.subTest(sentence=sentence):
                self.assertFalse(residual_conditions_kept(RULE + ' ' + sentence, SELECTED, DOCS))

    def test_identifiers_are_strings_while_rates_are_numeric(self):
        rule = RULE.replace('19', '27.5').replace('3, 6 и 8', '1.10, 2.3 и 7')
        text = '12.2. ' + rule
        header = HEADER.replace('73', '91')
        doc = Document(NAME, header + text, '', ())
        selected = [Fragment('different', NAME, len(header), len(doc.text), text, '12.2.')]
        conditional = ('Если ни один из пунктов 7, 2.3 и 1.10 не применяется, '
                       'ставка 27,500% по пункту 12.2 обоснована.')
        self.assertTrue(residual_conditions_kept(rule + ' ' + conditional, selected, {NAME: doc}))
        self.assertFalse(residual_conditions_kept(rule + ' ' + conditional.replace('1.10', '1.1'),
                                                 selected, {NAME: doc}))
        context = _residual_logic_context(selected, {NAME: doc})
        self.assertFalse(_residual_rate_logic(conditional.replace('27,500', '27,6'), context))

    def test_short_forms_require_one_trusted_owner_and_the_point_reference_kind(self):
        self.assertFalse(residual_conditions_kept(RULE + ' ' + CONDITIONAL, SELECTED))
        for doc in (Document(NAME, DOC.text, '', ((0, len(HEADER)),)),
                    Document(NAME, DOC.text.replace(SOURCE, '7. ' + RULE), '', ()),
                    Document(NAME, DOC.text + '\nСтатья 74. Иное правило', '', ())):
            self.assertIsNone(_residual_logic_context(SELECTED, {NAME: doc}))
        other = Fragment('other', 'Другой документ.txt', 0, 12, 'Иные сведения', '')
        self.assertIsNone(_residual_logic_context(SELECTED + [other], DOCS))
        for source in (SOURCE.replace('пунктах', 'подпунктах'),
                       '5. При условии регистрации ' + RULE.lower(),
                       SOURCE[:-1] + ' при наличии разрешения.'):
            doc = Document(NAME, HEADER + source, '', ())
            fragment = Fragment('changed', NAME, len(HEADER), len(doc.text), source, '5.')
            self.assertIsNone(_residual_logic_context([fragment], {NAME: doc}))
        other_rule = RULE.replace('19', '27').replace('3, 6 и 8', '2, 7 и 9')
        text = HEADER + SOURCE + '\n6. ' + other_rule
        doc = Document(NAME, text, '', ())
        other = Fragment('other', NAME, len(HEADER + SOURCE + '\n'), len(text), '6. ' + other_rule, '6.')
        self.assertIsNone(_residual_logic_context(SELECTED + [other], {NAME: doc}))

    def test_both_modes_publish_the_complete_logic_without_an_extra_generation(self):
        text = INSUFFICIENT + ' ' + RULE + ' ' + CONDITIONAL
        for verify in (False, True):
            responses = [generated(text)]
            if verify:
                responses.append(lambda p: {**verdict(p), 'answer_supported': True})
            model = ScriptedModel(responses)
            with redirect_stderr(io.StringIO()):
                result = answer_structured('Достаточно ли проверить неприменимость пункта 6?',
                                           RuleRetriever(), model, verify=verify, repair_quotes=not verify)
            self.assertFalse(result['quote_only'])
            self.assertEqual(result['status'], 'answer')
            self.assertEqual(len(model.calls), 2 if verify else 1)

    def test_incomplete_condition_is_still_repaired_with_the_existing_bounded_retry(self):
        bad = RULE + ' ' + CONDITIONAL.replace('3, 6 и 8', '3 и 6')
        good = RULE + ' ' + CONDITIONAL
        model = ScriptedModel([generated(bad), generated(good)])
        with redirect_stderr(io.StringIO()):
            result = answer_structured('Когда применяется ставка?', RuleRetriever(), model,
                                       verify=False, repair_quotes=True)
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1][1]['retry_reason'], 'answer_lost_restrictions')


if __name__ == '__main__':
    unittest.main()
