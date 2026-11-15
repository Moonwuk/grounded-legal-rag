"""A repeated thresholded ban preserves its own exception on every attempt."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_llm import ProviderError
from psb_policy import BOUND_EXCEPTION_RETRY_GUIDANCE, RESIDUAL_RETRY_GUIDANCE, SYSTEM, answer_structured
from test_audit_fixes import corpus, verdict
from test_baseline import ScriptedModel
from test_residual_reference_scope import RULE, SOURCE as RESIDUAL_SOURCE


EXCEPTION = 'за исключением предприятий, которые соответствуют критериям, установленным Советом директоров'
PREFIX = '1. Льгота не применяется к следующим категориям:'
ITEM = ('1.1. предприятиям, у которых доля экспортной выручки составляет не менее 35 процентов, '
        + EXCEPTION + ';')
FILES = {'Порядок льготы.txt': 'Порядок льготы\n' + PREFIX + '\n' + ITEM}
BAD = 'Льгота не применяется к предприятиям с долей экспортной выручки не менее 35 процентов.'
GOOD = BAD[:-1] + ', ' + EXCEPTION + '.'


def select(text):
    def generate(payload):
        return {'status': 'answer', 'answer': text,
                'source_ids': [f['id'] for f in payload['evidence'] if f['text'].startswith(('1.', '5.'))],
                'requested_facts': [], 'issue': ''}
    return generate


def checked(payload):
    return {**verdict(payload), 'answer_supported': True}


def run(responses, *, verify=False, files=FILES):
    model = ScriptedModel(responses)
    with corpus(files) as retriever, redirect_stderr(io.StringIO()):
        result = answer_structured('Когда применяется льгота?', retriever, model,
                                   verify=verify, repair_quotes=not verify)
    return result, model


class BoundExceptionRetryTests(unittest.TestCase):
    def test_the_existing_retry_preserves_the_selected_source_exception(self):
        for verify in (False, True):
            responses = ([select(BAD), checked, select(GOOD), checked] if verify
                         else [select(BAD), select(GOOD)])
            result, model = run(responses, verify=verify)
            self.assertFalse(result['quote_only'])
            generations = [(s, p) for s, p in model.calls if 'candidate' not in p]
            self.assertEqual(len(generations), 2)
            self.assertEqual(generations[0][0], SYSTEM)
            self.assertNotIn('retry_bound_exceptions', generations[0][1])
            self.assertEqual(generations[1][1]['retry_reason'], 'answer_lost_restrictions')
            self.assertEqual(generations[1][1]['retry_bound_exceptions'], [EXCEPTION])
            self.assertIn(BOUND_EXCEPTION_RETRY_GUIDANCE, generations[1][0])

    def test_a_positive_verifier_and_final_repair_do_not_override_the_exception_guard(self):
        for verify in (False, True):
            responses = [select(BAD), checked] * 2 if verify else [select(BAD)] * 3
            result, model = run(responses, verify=verify)
            self.assertTrue(result['quote_only'])
            self.assertIn(EXCEPTION, result['text'])
            self.assertFalse(result['text'].startswith(BAD))
            self.assertEqual(len(model.calls), 4 if verify else 3)
            if not verify:
                self.assertTrue(model.calls[-1][1]['final_text_repair'])

    def test_quota_and_api_failure_keep_the_full_source_exception(self):
        with patch('psb_policy.QUESTION_CALL_LIMIT', 2):
            result, model = run([select(BAD)] * 3)
        self.assertTrue(result['quote_only'])
        self.assertIn(EXCEPTION, result['text'])
        self.assertEqual(len(model.calls), 1)
        def fail(payload):
            raise ProviderError('http_503')
        result, model = run([select(BAD), fail])
        self.assertTrue(result['quote_only'])
        self.assertIn(EXCEPTION, result['text'])

    def test_a_standalone_unambiguous_exception_still_publishes_without_retry(self):
        good = BAD + ' Исключение — предприятия, соответствующие критериям Совета директоров.'
        result, model = run([select(good)])
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 1)

    def test_kept_exceptions_survive_repair_of_another_residual_condition(self):
        files = {'Порядок льготы.txt': FILES['Порядок льготы.txt'] + '\n' + RESIDUAL_SOURCE}
        result, model = run([select(GOOD), select(RULE + ' ' + BAD), select(RULE + ' ' + GOOD)], files=files)
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 3)
        for system, payload in model.calls[1:]:
            self.assertEqual(payload['retry_bound_exceptions'], [EXCEPTION])
            self.assertEqual(payload['retry_residual_conditions'], [RULE])
            self.assertTrue(system.endswith(RESIDUAL_RETRY_GUIDANCE))


if __name__ == '__main__':
    unittest.main()
