"""Retry an incomplete document view without inventing what it contains."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from test_one_call_answers import one_call
from test_quarantined_absence import FILES, QUESTION, GOOD, PAYMENT, INSTRUCTION, answer


class QuarantineRetryTests(unittest.TestCase):
    def test_retry_explains_the_evidence_limit_and_keeps_the_direct_answer(self):
        bad = 'В служебной записке нет указаний об оплате через 64 дня. ' + GOOD
        result, model, _ = one_call(QUESTION, [answer(bad), answer(GOOD)], FILES)
        self.assertEqual(len(model.calls), 2)
        self.assertNotIn('retry_policy_feedback', model.calls[0][1])
        system, payload = model.calls[1]
        self.assertEqual(payload['retry_policy_feedback']['scope_barrier'], 'quarantined_content_absence')
        self.assertEqual(payload['retry_policy_draft'], bad)
        self.assertIn('не объясняй назначение исключённых указаний', system)
        self.assertIn('само по себе не делает ответ', system)
        self.assertNotIn(INSTRUCTION, str(payload))
        self.assertEqual(result['status'], 'answer')
        self.assertFalse(result['quote_only'])
        self.assertTrue(result['text'].startswith(GOOD))

    def test_diagnostic_does_not_authorize_an_unsupported_replacement(self):
        bad = 'В служебной записке нет указаний об оплате через 64 дня. ' + GOOD
        result, _, _ = one_call(QUESTION, [answer(bad), answer(GOOD.replace('18', '777'))], FILES)
        self.assertTrue(result['quote_only'])
        self.assertIn(PAYMENT, result['text'])
        self.assertNotIn('777', result['text'])
        self.assertNotIn(bad, result['text'])
        self.assertNotIn(INSTRUCTION, result['text'])


if __name__ == '__main__':
    unittest.main()
