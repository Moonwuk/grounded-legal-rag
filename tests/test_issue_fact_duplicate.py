"""Remove only an explicitly selected issue duplicated into the fact-code enum."""
from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from psb_policy import FOLLOWUPS, ISSUES, expand_selection, render, validate_candidate
from test_prose_answers import run, confirm


def selection(issue='historical_version', facts=None, status='insufficient'):
    return {'status': status, 'answer': 'Непроверенный произвольный ответ 987654.',
            'source_ids': [], 'requested_facts': [issue] if facts is None else facts,
            'issue': issue}


class IssueFactDuplicateTests(unittest.TestCase):
    def test_same_explicit_issue_duplicate_is_removed(self):
        original = selection()
        before = copy.deepcopy(original)
        candidate = expand_selection(original, [])
        self.assertEqual(original, before)
        self.assertEqual(candidate['requested_facts'], [])
        self.assertEqual(candidate['issue'], 'historical_version')
        self.assertTrue(validate_candidate(candidate, []))
        text = render(candidate, [], question='Можно ли установить прежнее значение по текущей редакции?')
        self.assertTrue(text.startswith(ISSUES['historical_version']))
        self.assertNotIn(original['answer'], text)
        self.assertNotIn('987654', text)

    def test_valid_fact_codes_remain_in_their_original_order(self):
        candidate = expand_selection(selection(facts=[
            'event_date', 'historical_version', 'document', 'historical_version']), [])
        self.assertEqual(candidate['requested_facts'], ['event_date', 'document'])
        self.assertTrue(validate_candidate(candidate, []))

    def test_empty_fact_list_with_valid_issue_is_already_sufficient(self):
        candidate = expand_selection(selection(facts=[]), [])
        self.assertEqual(candidate['requested_facts'], [])
        self.assertTrue(validate_candidate(candidate, []))

    def test_missing_unknown_or_mismatched_issue_does_not_repair_a_fact_code(self):
        cases = [selection(issue='', facts=['historical_version']),
                 selection(issue='invented', facts=['invented']),
                 selection(issue='invalid_date', facts=['historical_version']),
                 selection(issue='document', facts=['document']),
                 selection(issue='historical_version', facts=['invalid_date'])]
        for original in cases:
            with self.subTest(original=original):
                candidate = expand_selection(original, [])
                self.assertEqual(candidate['requested_facts'], original['requested_facts'])
                self.assertFalse(validate_candidate(candidate, []))

    def test_other_invalid_facts_are_preserved_and_rejected(self):
        for invalid in ('invented', 123, None, {'code': 'document'}, ['document']):
            with self.subTest(invalid=invalid):
                candidate = expand_selection(selection(facts=['historical_version', invalid]), [])
                self.assertEqual(candidate['requested_facts'], [invalid])
                self.assertFalse(validate_candidate(candidate, []))

    def test_invalid_types_and_oversized_fact_lists_are_not_laundered(self):
        for facts in ('historical_version', None, {'historical_version': True},
                      ['historical_version'] * (len(FOLLOWUPS) + 1)):
            with self.subTest(facts=facts):
                original = selection()
                original['requested_facts'] = facts
                candidate = expand_selection(original, [])
                self.assertEqual(candidate['requested_facts'], facts)
                self.assertFalse(validate_candidate(candidate, []))
        for issue in (None, ['historical_version'], {'issue': 'historical_version'}):
            with self.subTest(issue=issue):
                candidate = expand_selection(selection(issue=issue, facts=['historical_version']), [])
                self.assertFalse(validate_candidate(candidate, []))

    def test_status_and_conflict_evidence_requirements_remain_in_force(self):
        for original in (selection(status='answer'), selection(status='partial'),
                         selection(issue='conflicting_documents')):
            with self.subTest(original=original):
                candidate = expand_selection(original, [])
                self.assertEqual(candidate['requested_facts'], [])
                self.assertFalse(validate_candidate(candidate, []))

    def test_direct_claim_format_is_not_repaired(self):
        candidate = expand_selection(selection(), [])
        candidate['requested_facts'] = ['historical_version']
        self.assertEqual(expand_selection(candidate, []), candidate)
        self.assertFalse(validate_candidate(candidate, []))

    def test_standard_flow_publishes_only_the_typed_historical_refusal(self):
        def missing(payload):
            return selection()
        text, status, model, _ = run(
            'Можно ли установить прежнее значение по текущей редакции?',
            [missing, missing, confirm()])
        self.assertEqual(status, 'insufficient')
        self.assertTrue(text.startswith(ISSUES['historical_version']))
        self.assertNotIn('987654', text)
        self.assertEqual(model.calls[-1][1]['candidate']['requested_facts'], [])
        self.assertEqual(model.calls[-1][1]['candidate']['issue'], 'historical_version')


if __name__ == '__main__':
    unittest.main()
