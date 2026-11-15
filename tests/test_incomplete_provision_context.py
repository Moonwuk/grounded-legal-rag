"""A partial view of a provision cannot support a complete legal conclusion."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_llm import ProviderError
from psb_policy import answer_structured


FIRST = '1. Ставка сбора составляет 7 процентов.'
CONDITION = 'Указанная ставка применяется при наличии разрешения.'
PROSE = 'Ставка сбора составляет 7 процентов.'
COMPLETE_PROSE = 'Ставка сбора составляет 7 процентов при наличии разрешения.'
WARNING = 'Полнота основания не подтверждена:'


class ContextRetriever:
    documents = {}

    def __init__(self, *, resolved=False, initially_complete=False, ordinary_gaps=False):
        self.resolved = resolved
        self.initially_complete = initially_complete
        self.ordinary_gaps = ordinary_gaps
        self.searches = []
        self.first = Fragment('first', 'Правила.txt', 0, len(FIRST), FIRST, '1.')
        self.condition = Fragment('condition', 'Правила.txt', len(FIRST) + 1,
                                  len(FIRST) + 1 + len(CONDITION), CONDITION, '1.')

    def search(self, question, *, top_k, expanded):
        self.searches.append(expanded)
        return ([self.first, self.condition] if self.initially_complete or (expanded and self.resolved)
                else [self.first])

    def evidence(self, fragments):
        return [{'id': f.id, 'document': f.document, 'text': f.text,
                 'start': f.start, 'end': f.end} for f in fragments]

    def context_gaps(self, selected, evidence):
        if self.first in selected and self.condition not in evidence:
            return [{'document': 'Правила.txt', 'articles': [],
                     'provisions': ['пункт 1 статьи 71'], 'reason': 'incomplete_context'}]
        return []

    def reference_gaps(self, selected):
        return [{'document': 'Правила.txt', 'articles': ['9', '10']}] if self.ordinary_gaps else []


class ContextModel:
    def __init__(self, *, fail_retry=False, reject_retry=False):
        self.fail_retry = fail_retry
        self.reject_retry = reject_retry
        self.calls = []

    def complete(self, system, payload):
        self.calls.append((system, payload))
        if 'candidate' in payload:
            accepted = not (self.reject_retry and payload['expanded_search'])
            return {'approved': accepted, 'complete': True, 'answer_supported': True,
                    'status': payload['candidate']['status'], 'references_required': False,
                    'claim_checks': [{'index': i, 'supported': accepted, 'applicable': True}
                                     for i, _ in enumerate(payload['candidate']['claims'])]}
        if self.fail_retry and payload['expanded_search']:
            raise ProviderError('http_503')
        full = any(f['id'] == 'condition' for f in payload['evidence'])
        return {'status': 'answer', 'answer': COMPLETE_PROSE if full else PROSE,
                'source_ids': [f['id'] for f in payload['evidence']], 'requested_facts': [],
                'issue': '', 'reference_scope': 'local'}


class OversizedContextRetriever(ContextRetriever):
    def __init__(self):
        super().__init__()
        text = FIRST + ' ' + 'Описание категории плательщиков. ' * 160
        other = 'Порядок регистрации плательщиков. ' * 160
        self.first = Fragment('first', 'Правила.txt', 0, len(text), text, '1.')
        self.extra = Fragment('extra', 'Порядок.txt', 0, len(other), other, '2.')

    def search(self, question, *, top_k, expanded):
        self.searches.append(expanded)
        return [self.first, self.extra]


def run_case(retriever, model, *, verify):
    output = io.StringIO()
    with redirect_stderr(output):
        result = answer_structured('Какова ставка сбора?', retriever, model,
                                   verify=verify, repair_quotes=not verify)
    events = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
    return result, events


class IncompleteProvisionContextTests(unittest.TestCase):
    def assert_partial(self, result):
        self.assertEqual(result['status'], 'partial', result['text'])
        self.assertTrue(result['quote_only'])
        self.assertIn(WARNING, result['text'])
        self.assertIn('«' + FIRST + '»', result['text'])
        self.assertFalse(result['text'].startswith(PROSE))
        self.assertNotIn('В предоставленной базе не найдены', result['text'])
        self.assertNotIn('Предоставьте', result['text'])

    def test_expanded_search_can_complete_context_and_restore_a_direct_answer(self):
        for verify in (False, True):
            with self.subTest(verify=verify):
                retriever, model = ContextRetriever(resolved=True), ContextModel()
                result, _ = run_case(retriever, model, verify=verify)
                self.assertEqual(retriever.searches, [False, True])
                self.assertEqual(len(model.calls), 4 if verify else 2)
                self.assertEqual(result['status'], 'answer', result['text'])
                self.assertTrue(result['text'].startswith(COMPLETE_PROSE), result['text'])
                self.assertNotIn(WARNING, result['text'])
                retry = next(p for _, p in model.calls if p['expanded_search'] and 'candidate' not in p)
                self.assertEqual(retry['retry_reason'], 'incomplete_source_context')

    def test_unresolved_context_stays_partial_despite_local_scope_and_positive_verifier(self):
        for verify in (False, True):
            with self.subTest(verify=verify):
                retriever, model = ContextRetriever(), ContextModel()
                result, events = run_case(retriever, model, verify=verify)
                self.assert_partial(result)
                self.assertEqual(retriever.searches, [False, True])
                self.assertEqual(len(model.calls), 4 if verify else 2)
                for _, payload in model.calls:
                    if 'candidate' in payload:
                        self.assertEqual(payload['candidate']['status'], 'partial')
                        self.assertNotIn('answer', payload['candidate'])
                        self.assertNotEqual(payload['candidate'].get('reference_scope'), 'local')
                if verify:
                    self.assertTrue(all(e['source_gap_count'] == 1 for e in events))
                    self.assertTrue(all(e['reference_scope'] == 'required' for e in events))

    def test_expanded_api_failure_preserves_the_safe_partial_checkpoint(self):
        for verify in (False, True):
            with self.subTest(verify=verify):
                retriever, model = ContextRetriever(), ContextModel(fail_retry=True)
                result, _ = run_case(retriever, model, verify=verify)
                self.assert_partial(result)
                self.assertEqual(retriever.searches, [False, True])
                self.assertEqual(len(model.calls), 3 if verify else 2)

    def test_second_verifier_rejection_does_not_replace_verified_partial(self):
        retriever, model = ContextRetriever(resolved=True), ContextModel(reject_retry=True)
        result, _ = run_case(retriever, model, verify=True)
        self.assert_partial(result)
        self.assertEqual(len(model.calls), 4)

    def test_call_quota_does_not_discard_verified_partial(self):
        retriever, model = ContextRetriever(), ContextModel()
        with patch('psb_policy.QUESTION_CALL_LIMIT', 2):
            result, _ = run_case(retriever, model, verify=True)
        self.assert_partial(result)
        self.assertEqual(retriever.searches, [False])
        self.assertEqual(len(model.calls), 2)

    def test_complete_first_context_keeps_existing_one_attempt_behavior(self):
        for verify in (False, True):
            with self.subTest(verify=verify):
                retriever, model = ContextRetriever(initially_complete=True), ContextModel()
                result, _ = run_case(retriever, model, verify=verify)
                self.assertEqual(result['status'], 'answer', result['text'])
                self.assertEqual(retriever.searches, [False])
                self.assertEqual(len(model.calls), 2 if verify else 1)

    def test_missing_articles_remain_distinct_and_are_counted_with_context_gaps(self):
        retriever, model = ContextRetriever(ordinary_gaps=True), ContextModel()
        result, events = run_case(retriever, model, verify=True)
        self.assertEqual(result['status'], 'partial')
        self.assertIn(WARNING, result['text'])
        self.assertIn('не найдены тексты отсылочных статей 9, 10', result['text'])
        self.assertIn('Предоставьте эти статьи.', result['text'])
        self.assertTrue(all(e['source_gap_count'] == 3 for e in events))

    def test_oversized_partial_quotes_keep_a_bounded_warning_and_the_expanded_attempt(self):
        for verify in (False, True):
            for fail_retry in (False, True):
                with self.subTest(verify=verify, fail_retry=fail_retry):
                    retriever = OversizedContextRetriever()
                    model = ContextModel(fail_retry=fail_retry)
                    result, _ = run_case(retriever, model, verify=verify)
                    self.assertEqual(result['status'], 'partial', result['text'])
                    self.assertTrue(result['quote_only'])
                    self.assertLessEqual(len(result['text']), 10000)
                    self.assertIn(WARNING, result['text'])
                    self.assertNotIn(PROSE, result['text'])
                    self.assertNotIn('Описание категории', result['text'])
                    self.assertNotIn('Порядок регистрации', result['text'])
                    self.assertIn('[1] Правила.', result['text'])
                    self.assertIn('[2] Порядок.', result['text'])
                    self.assertEqual(result['sources'], [retriever.first, retriever.extra])
                    self.assertEqual(retriever.searches, [False, True])
                    expected_calls = (3 if fail_retry else 4) if verify else 2
                    self.assertEqual(len(model.calls), expected_calls)

    def test_size_fallback_does_not_relax_the_regular_answer_length_limit(self):
        retriever = OversizedContextRetriever()
        retriever.context_gaps = lambda selected, evidence: []
        model = ContextModel()
        # A plain quote-only response without a context-gap diagnosis keeps the
        # original size barrier; it cannot borrow the special partial summary.
        original_complete = model.complete
        def quotes_only(system, payload):
            answer = original_complete(system, payload)
            if 'candidate' not in payload:
                answer['answer'] = ''
            return answer
        model.complete = quotes_only
        result, _ = run_case(retriever, model, verify=False)
        self.assertEqual(result['status'], 'technical_error')
        self.assertNotIn(WARNING, result['text'])
        self.assertEqual(retriever.searches, [False])


if __name__ == '__main__':
    unittest.main()
