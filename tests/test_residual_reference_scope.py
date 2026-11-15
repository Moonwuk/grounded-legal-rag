"""A selected residual rule needs its entire negative reference group."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import (RESIDUAL_RETRY_GUIDANCE, SYSTEM, answer_structured,
                        residual_conditions_kept, residual_source_conditions, restrictions_kept)
from test_audit_fixes import corpus, verdict
from test_baseline import ScriptedModel
from test_one_call_answers import answer


RULE = ('Налогообложение производится по налоговой ставке 19 процентов '
        'в случаях, не указанных в пунктах 3, 6 и 8 настоящей статьи.')
SOURCE = '5. ' + RULE
SELECTED = [Fragment('f', 'Учебная статья 73.txt', 0, len(SOURCE), SOURCE, '5.')]
BAD = 'Если товар не поименован в пункте 6, применяется ставка 19 процентов.'
FILES = {'Учебная статья 73.txt': 'Статья 73. Ставки сбора\n' + SOURCE}


class ResidualReferenceScopeTests(unittest.TestCase):
    def test_complete_literal_rule_keeps_reference_kind_scope_and_every_identity(self):
        for text in (RULE, RULE.upper(), RULE.replace(', ', ' '), RULE.replace(' ', '  ')):
            with self.subTest(text=text):
                self.assertTrue(residual_conditions_kept(text, SELECTED))
                self.assertTrue(restrictions_kept(text, SELECTED))
        varied = SOURCE.replace('19', '27').replace('3, 6 и 8', '2.1, 7.2 и 9.3')
        source = Fragment('v', 'Порядок.txt', 0, len(varied), varied, '5.')
        self.assertTrue(residual_conditions_kept(varied.removeprefix('5. '), [source]))
        decimal = SOURCE.replace('19', '19,5')
        source = Fragment('decimal', 'Порядок.txt', 0, len(decimal), decimal, '5.')
        self.assertTrue(residual_conditions_kept(decimal.removeprefix('5. '), [source]))
        self.assertFalse(residual_conditions_kept(decimal.removeprefix('5. ').replace('19,5', '19 5'), [source]))

    def test_incomplete_inverted_or_merely_quoted_groups_are_not_a_complete_rule(self):
        for text in (
                BAD,
                BAD + ' В статье также есть пункты 3 и 8.',
                'Если применяются пункты 3, 6 и 8 статьи 73, ставка составляет 19 процентов.',
                RULE.replace('в пунктах', 'в подпунктах'),
                RULE.replace('настоящей статьи', 'статьи 74'),
                RULE.replace('3, 6 и 8', '3.1, 6 и 8'),
                'Ставка составляет 19 процентов. В пункте 6 указаны ставки 3 и 8 процентов.',
                'Неверно, что пункты 3, 6 и 8 не применяются. Поэтому ставка составляет 19 процентов.',
                'Вопрос содержит слова «если пункты 3, 6 и 8 не применяются». Ставка составляет 19 процентов.',
                'Неверно, что ' + RULE,
                'Предположим: ' + RULE,
                '«' + RULE + '»',
                RULE.replace('не указанных', 'указанных'),
                RULE + ' ' + BAD):
            with self.subTest(text=text):
                self.assertFalse(residual_conditions_kept(text, SELECTED))
                self.assertFalse(restrictions_kept(text, SELECTED))

    def test_category_exclusions_and_single_or_dashed_references_are_outside_this_guard(self):
        for text in (
                'Доходы организаций, не указанных в подпункте 1.2 настоящего пункта, учитываются отдельно.',
                'Правило применяется в случаях, не предусмотренных пунктом 4.1-1 настоящей статьи.',
                'Правило применяется в случае, не указанном в пункте 3 настоящей статьи.'):
            with self.subTest(text=text):
                source = Fragment('x', 'Порядок.txt', 0, len(text), text, '')
                self.assertEqual(residual_source_conditions([source]), [])

    def test_strict_selected_scope_requires_removing_an_unused_residual_source(self):
        other_text = 'Для основного перечня ставка составляет 11 процентов.'
        other = Fragment('other', 'Учебная статья 73.txt', 1, 2, other_text, '')
        self.assertFalse(restrictions_kept(other_text, [*SELECTED, other]))
        self.assertTrue(restrictions_kept(other_text, [other]))

    def test_bounded_retry_repeats_the_source_condition_and_preserves_all_other_guards(self):
        for verify in (False, True):
            with self.subTest(verify=verify):
                def checked(payload):
                    return {**verdict(payload), 'answer_supported': True}
                responses = ([answer('5.', BAD), checked, answer('5.', RULE), checked] if verify
                             else [answer('5.', BAD), answer('5.', RULE)])
                model = ScriptedModel(responses)
                with corpus(FILES) as retriever, redirect_stderr(io.StringIO()):
                    result = answer_structured('Какая ставка сбора?', retriever, model,
                                               verify=verify, repair_quotes=not verify)
                self.assertEqual(result['status'], 'answer')
                self.assertFalse(result['quote_only'])
                self.assertTrue(result['text'].startswith(RULE), result['text'])
                generations = [(system, p) for system, p in model.calls if 'candidate' not in p]
                self.assertEqual(len(generations), 2)
                self.assertEqual(generations[0][0], SYSTEM)
                self.assertNotIn('retry_residual_conditions', generations[0][1])
                self.assertEqual(generations[1][1]['retry_reason'], 'answer_lost_restrictions')
                self.assertEqual(generations[1][1]['retry_residual_conditions'], [RULE])
                self.assertIn(RESIDUAL_RETRY_GUIDANCE, generations[1][0])

    def test_changed_selection_replaces_the_residual_diagnostic(self):
        new_rule = RULE.replace('19', '27').replace('3, 6 и 8', '2, 7 и 9')
        files = {'Учебная статья 73.txt': 'Статья 73. Ставки сбора\n' + SOURCE + '\n6. ' + new_rule}
        bad_second = 'Если товар не поименован в пункте 7, применяется ставка 27 процентов.'
        model = ScriptedModel([answer('5.', BAD), answer('6.', bad_second), answer('6.', new_rule)])
        with corpus(files) as retriever, redirect_stderr(io.StringIO()):
            result = answer_structured('Какая ставка сбора?', retriever, model, verify=False, repair_quotes=True)
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(model.calls[1][1]['retry_residual_conditions'], [RULE])
        self.assertEqual(model.calls[2][1]['retry_residual_conditions'], [new_rule])
        self.assertFalse(result['quote_only'])

    def test_residual_rule_already_kept_is_preserved_while_repairing_another_restriction(self):
        exception = '6. Возврат разрешается, за исключением товаров, изготовленных по заказу.'
        files = {'Учебная статья 73.txt': 'Статья 73. Ставки сбора\n' + SOURCE + '\n' + exception}
        def select_both(text):
            def generate(payload):
                return {'status': 'answer', 'answer': text, 'requested_facts': [], 'issue': '',
                        'source_ids': [f['id'] for f in payload['evidence'] if f['text'].startswith(('5.', '6.'))]}
            return generate
        good = RULE + ' ' + exception.removeprefix('6. ')
        model = ScriptedModel([select_both(RULE + ' Возврат разрешается.'), select_both(good)])
        with corpus(files) as retriever, redirect_stderr(io.StringIO()):
            result = answer_structured('Какая ставка и разрешён ли возврат?', retriever, model, verify=False)
        self.assertEqual(model.calls[1][1]['retry_restrictions'], ['за исключением'])
        self.assertEqual(model.calls[1][1]['retry_residual_conditions'], [RULE])
        self.assertFalse(result['quote_only'])


if __name__ == '__main__':
    unittest.main()
