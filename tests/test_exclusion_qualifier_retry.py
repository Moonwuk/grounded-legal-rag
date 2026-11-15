"""Source-owned exclusion definitions survive every bounded repair and verdict."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_llm import ProviderError
from psb_policy import (QUALIFIER_RETRY_GUIDANCE, RESIDUAL_RETRY_GUIDANCE, SYSTEM,
                        answer_structured)
from test_audit_fixes import corpus, verdict
from test_baseline import ScriptedModel
from test_one_call_answers import answer
from test_residual_reference_scope import RULE, SOURCE as RESIDUAL_SOURCE


PHRASE = 'металла медицинского и промышленного'
SOURCE = '5.1. Возврат разрешается (за исключением материалов: ' + PHRASE + ').'
BAD = 'Возврат разрешается, за исключением металла.'
GOOD = 'Возврат разрешается, за исключением ' + PHRASE + '.'
FILES = {'Порядок возврата.txt': 'Порядок возврата\n' + SOURCE}


def checked(payload):
    return {**verdict(payload), 'answer_supported': True}


def run(responses, *, verify=False, files=FILES):
    model = ScriptedModel(responses)
    with corpus(files) as retriever, redirect_stderr(io.StringIO()):
        result = answer_structured('Какие материалы можно вернуть?', retriever, model,
                                   verify=verify, repair_quotes=not verify)
    return result, model


class ExclusionQualifierRetryTests(unittest.TestCase):
    def test_qualifiers_between_two_distinct_heads_stay_attached_to_their_owner(self):
        source = ('5.1. Возврат разрешается (за исключением материалов: '
                  'металла медицинского и декоративного, пластика промышленного и пищевого).')
        files = {'Порядок возврата.txt': 'Порядок возврата\n' + source}
        good = 'Исключение — металл медицинский и промышленный пластик.'
        result, model = run([answer('5.1.', good)], files=files)
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 1)
        bad = 'Исключение — металл медицинский и промышленный.'
        result, model = run([answer('5.1.', bad)] * 3, files=files)
        self.assertTrue(result['quote_only'])
        self.assertEqual(len(model.calls), 3)

    def test_bare_category_is_repaired_without_changing_first_generation(self):
        for verify in (False, True):
            responses = ([answer('5.1.', BAD), checked, answer('5.1.', GOOD), checked] if verify
                         else [answer('5.1.', BAD), answer('5.1.', GOOD)])
            result, model = run(responses, verify=verify)
            self.assertFalse(result['quote_only'])
            self.assertTrue(result['text'].startswith(GOOD))
            generations = [(s, p) for s, p in model.calls if 'candidate' not in p]
            self.assertEqual(len(generations), 2)
            self.assertEqual(generations[0][0], SYSTEM)
            self.assertNotIn('retry_exclusion_qualifiers', generations[0][1])
            self.assertEqual(generations[1][1]['retry_reason'], 'answer_lost_restrictions')
            self.assertEqual(generations[1][1]['retry_exclusion_qualifiers'], [PHRASE])
            self.assertIn(QUALIFIER_RETRY_GUIDANCE, generations[1][0])
            if verify:
                first_verdict = next(p for _, p in model.calls if 'candidate' in p)
                self.assertNotIn('answer', first_verdict['candidate'])

    def test_positive_verifier_and_final_repair_cannot_publish_the_broadened_category(self):
        for verify in (False, True):
            responses = ([answer('5.1.', BAD), checked] * 2 if verify
                         else [answer('5.1.', BAD)] * 3)
            result, model = run(responses, verify=verify)
            self.assertTrue(result['quote_only'])
            self.assertIn(PHRASE, result['text'])
            self.assertFalse(result['text'].startswith(BAD))
            self.assertEqual(len(model.calls), 4 if verify else 3)
            if not verify:
                self.assertTrue(model.calls[-1][1]['final_text_repair'])
                self.assertEqual(model.calls[-1][1]['retry_exclusion_qualifiers'], [PHRASE])

    def test_quota_and_retry_failure_preserve_the_checked_quote_fallback(self):
        with patch('psb_policy.QUESTION_CALL_LIMIT', 2):
            result, model = run([answer('5.1.', BAD)] * 3)
        self.assertTrue(result['quote_only'])
        self.assertEqual(len(model.calls), 1)
        def fail(payload):
            raise ProviderError('http_503')
        result, model = run([answer('5.1.', BAD), fail])
        self.assertTrue(result['quote_only'])
        self.assertIn(PHRASE, result['text'])
        self.assertEqual(len(model.calls), 2)

    def test_current_selection_replaces_old_qualifier_feedback(self):
        new_phrase = 'песка озерного и речного'
        new_source = '5.2. Возврат разрешается (за исключением материалов: ' + new_phrase + ').'
        files = {'Порядок возврата.txt': 'Порядок возврата\n' + SOURCE + '\n' + new_source}
        new_bad = 'Возврат разрешается, за исключением песка.'
        new_good = 'Возврат разрешается, за исключением ' + new_phrase + '.'
        result, model = run([answer('5.1.', BAD), answer('5.2.', new_bad), answer('5.2.', new_good)],
                            files=files)
        self.assertFalse(result['quote_only'])
        self.assertEqual(model.calls[1][1]['retry_exclusion_qualifiers'], [PHRASE])
        self.assertEqual(model.calls[2][1]['retry_exclusion_qualifiers'], [new_phrase])

    def test_qualifiers_already_kept_remain_when_the_residual_condition_is_repaired(self):
        files = {'Порядок возврата.txt': 'Порядок возврата\n' + RESIDUAL_SOURCE + '\n'
                 + SOURCE.replace('5.1.', '6.')}
        def both(text):
            def generate(payload):
                return {'status': 'answer', 'answer': text,
                        'source_ids': [f['id'] for f in payload['evidence']
                                       if f['text'].startswith(('5.', '6.'))],
                        'requested_facts': [], 'issue': ''}
            return generate
        result, model = run([both(GOOD), both(RULE + ' ' + BAD), both(RULE + ' ' + GOOD)], files=files)
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 3)
        for system, payload in model.calls[1:]:
            self.assertEqual(payload['retry_exclusion_qualifiers'], [PHRASE])
            self.assertEqual(payload['retry_residual_conditions'], [RULE])
            self.assertIn(QUALIFIER_RETRY_GUIDANCE, system)
            self.assertTrue(system.endswith(RESIDUAL_RETRY_GUIDANCE))


if __name__ == '__main__':
    unittest.main()
