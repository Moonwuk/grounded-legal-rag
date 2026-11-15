"""A complete residual norm does not license an extra categorical rate claim."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import answer_structured, residual_conditions_kept, restrictions_kept
from test_audit_fixes import corpus, verdict
from test_baseline import ScriptedModel
from test_one_call_answers import answer
from test_residual_citations import APPLICABILITY, DOCS, POSITIVE, SELECTED
from test_residual_reference_scope import FILES, RULE, SOURCE


class ResidualRateAssertionTests(unittest.TestCase):
    def test_complete_norm_does_not_cover_a_separate_categorical_application(self):
        for assertion in (
                'Для рекламных каталогов действует 19%.',
                'Для архивных материалов ставка 11% не применяется; действует 19%.',
                'Не 11%, а 19% применяется к учебным пособиям.',
                'Ставка составляет 19,0 процента.',
                'Ставка составляет 19.0000%.',
                'Ставка составляет 19.00000%.',
                'Ставка составляет +19%.',
                'Для архивных материалов предусмотрена 19-процентная ставка.',
                'Ставка составляет девятнадцать процентов.',
                'Ставка составляет девятнадцать %.',
                'Для каталогов действует ставка. 19 процентов.',
                'Ставка 19 процентов применяется, если остальные условия выполнены.',
                'Применяется ставка 11%, а не 19%, но для каталогов действует 19%.'):
            for text in (assertion + ' ' + RULE, RULE + ' ' + assertion):
                with self.subTest(text=text):
                    self.assertFalse(residual_conditions_kept(text, SELECTED, DOCS))
                    self.assertFalse(restrictions_kept(text, SELECTED, documents=DOCS))

    def test_full_norm_bare_initial_answer_and_explicit_rate_contrast_remain(self):
        for text in (
                RULE,
                '19 процентов. ' + RULE,
                '19,0%. ' + RULE,
                'Девятнадцать процентов. ' + RULE,
                'Девятнадцать %. ' + RULE,
                '19 процентов (п. 5 ст. 73 НК РФ). ' + RULE,
                RULE + ' Для названной реализации предусмотрено 11%, а не 19%.',
                RULE + ' Для названной реализации предусмотрено 11%, а не 19% (п. 5 ст. 73).',
                RULE + ' Для названной реализации предусмотрено 11%, а не девятнадцать процентов.',
                APPLICABILITY + ' Для названной реализации предусмотрено 11%, а не 19%.',
                *POSITIVE):
            with self.subTest(text=text):
                self.assertTrue(residual_conditions_kept(text, SELECTED, DOCS))

    def test_short_answer_must_be_initial_and_contrast_cannot_hide_a_predicate(self):
        for text in (
                RULE + ' 19 процентов.',
                RULE + ' Для каталога 11%, а не 19% действует в обычном случае.',
                RULE + ' Для каталога 11%, а не 19% (п. 5 ст. 74).',
                RULE + ' Для каталога 11%, а не 19% (хотя эта ставка применяется).'):
            with self.subTest(text=text):
                self.assertFalse(residual_conditions_kept(text, SELECTED, DOCS))

    def test_rate_is_source_owned_with_variable_decimal_and_word_forms(self):
        for rate, other in (('27', 'двадцать семь'), ('18,5', '18.5000'), ('7', 'семь')):
            rule = RULE.replace('19', rate)
            source = SOURCE.replace('19', rate)
            selected = [Fragment('varied', 'Порядок.txt', 0, len(source), source, '5.')]
            self.assertFalse(residual_conditions_kept(
                rule + ' Для отдельной категории применяется ' + other + ' процентов.', selected))
            self.assertTrue(residual_conditions_kept(rate + ' процентов. ' + rule, selected))
            if ',' not in rate:
                self.assertFalse(residual_conditions_kept(
                    rule + ' Для отдельной категории применяется ' + other + '%.', selected))
        self.assertTrue(residual_conditions_kept(RULE + ' Для иной категории предусмотрено 11%.', SELECTED))

    def test_same_bounded_retry_repairs_the_claim_in_batch_and_verified_modes(self):
        bad = 'Для печатных каталогов действует 19 процентов. ' + RULE
        for verify in (False, True):
            def checked(payload):
                return {**verdict(payload), 'answer_supported': True}
            responses = ([answer('5.', bad), checked, answer('5.', RULE), checked] if verify
                         else [answer('5.', bad), answer('5.', RULE)])
            model = ScriptedModel(responses)
            with corpus(FILES) as retriever, redirect_stderr(io.StringIO()):
                result = answer_structured('Какая ставка сбора?', retriever, model,
                                           verify=verify, repair_quotes=not verify)
            self.assertEqual(result['status'], 'answer')
            self.assertFalse(result['quote_only'])
            self.assertTrue(result['text'].startswith(RULE))
            generations = [p for _, p in model.calls if 'candidate' not in p]
            self.assertEqual(len(generations), 2)
            self.assertEqual(generations[1]['retry_reason'], 'answer_lost_restrictions')
            self.assertEqual(generations[1]['retry_residual_conditions'], [RULE])

    def test_repeated_categorical_claim_never_replaces_quote_fallback(self):
        bad = 'Для печатных каталогов действует 19 процентов. ' + RULE
        model = ScriptedModel([answer('5.', bad)] * 3)
        with corpus(FILES) as retriever, redirect_stderr(io.StringIO()):
            result = answer_structured('Какая ставка сбора?', retriever, model,
                                       verify=False, repair_quotes=True)
        self.assertTrue(result['quote_only'])
        self.assertNotIn('Для печатных каталогов', result['text'])
        self.assertEqual(len(model.calls), 3)


if __name__ == '__main__':
    unittest.main()
