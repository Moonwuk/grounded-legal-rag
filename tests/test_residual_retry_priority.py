"""Specific source-copy requirements remain last in a bounded repair prompt."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_policy import (FINAL_REPAIR_GUIDANCE, POLICY_RETRY_GUIDANCE,
                        RESIDUAL_RETRY_GUIDANCE, SYSTEM, answer_structured,
                        residual_conditions_kept)
from test_audit_fixes import corpus
from test_baseline import ScriptedModel
from test_one_call_answers import answer, one_call
from test_residual_reference_scope import FILES, RULE, SELECTED


PARAPHRASE = ('Нет. Пункт 5 применяется только к случаям, '
              'не указанным в пунктах 3, 6 и 8.')


class ResidualRetryPriorityTests(unittest.TestCase):
    def test_source_copy_instruction_follows_policy_and_final_repair_once(self):
        for final in (RULE, PARAPHRASE):
            with self.subTest(final=final):
                model = ScriptedModel([answer('5.', PARAPHRASE), answer('5.', PARAPHRASE),
                                       answer('5.', final)])
                with corpus(FILES) as retriever, redirect_stderr(io.StringIO()):
                    result = answer_structured('Применяется ли пункт 5 к случаю из пункта 6?',
                                               retriever, model, verify=False, repair_quotes=True)
                self.assertEqual(len(model.calls), 3)
                self.assertEqual(model.calls[0][0], SYSTEM)
                self.assertNotIn('retry_residual_conditions', model.calls[0][1])
                for system, payload in model.calls[1:]:
                    self.assertEqual(payload['retry_reason'], 'answer_lost_restrictions')
                    self.assertEqual(payload['retry_residual_conditions'], [RULE])
                    self.assertEqual(payload['retry_policy_feedback']['scope_barrier'], 'exclusive_word')
                    self.assertIn(POLICY_RETRY_GUIDANCE, system)
                    self.assertTrue(system.endswith(RESIDUAL_RETRY_GUIDANCE))
                    self.assertEqual(system.count(RESIDUAL_RETRY_GUIDANCE), 1)
                self.assertIn(FINAL_REPAIR_GUIDANCE, model.calls[2][0])
                self.assertTrue(model.calls[2][1]['final_text_repair'])
                self.assertEqual(result['quote_only'], final == PARAPHRASE)
                self.assertFalse(residual_conditions_kept(PARAPHRASE, SELECTED))

    def test_nonresidual_repair_and_first_generation_keep_their_prompt_contract(self):
        text = '5. Проверяются тарифные условия и полномочия подписантов.'
        bad = 'Проверяются только тарифные условия и полномочия подписантов.'
        files = {'Порядок проверки.txt': 'Порядок проверки\n' + text}
        result, model, _ = one_call('Что проверяется?',
                                   [answer('5.', bad), answer('5.', text[3:])], files)
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[0][0], SYSTEM)
        self.assertIn(POLICY_RETRY_GUIDANCE, model.calls[1][0])
        for system, payload in model.calls:
            self.assertNotIn(RESIDUAL_RETRY_GUIDANCE, system)
            self.assertNotIn('retry_residual_conditions', payload)


if __name__ == '__main__':
    unittest.main()
