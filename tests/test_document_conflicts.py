"""A conflict between documents is named, with each side quoted (scripted stubs).

Diagnosis (evaluation/reports/diag-conflict-2e9af79-*): every provision was
supported, yet the candidate could only call the gap "missing document", since
the policy had no code for a conflict; the verifier rejected it and the user
got a generic refusal.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from psb_policy import ISSUES, FOLLOWUPS, UNVERIFIED
from test_prose_answers import run, confirm

CONFLICTS = [
    dict(files={'Договор поставки М-2-2033.txt': 'Договор поставки № М-2/2033\n4.1. Оплата производится в течение 30 календарных дней после поставки.',
                'Письмо поставщика о сроке оплаты М-2-2033.txt': 'Письмо по договору № М-2/2033\nСрок оплаты товара составляет 60 календарных дней после поставки.'},
         question='Какой срок оплаты по договору М-2/2033?', sides=('4.1. Оплата', 'Срок оплаты товара')),
    dict(files={'Положение о премировании ред 2031.txt': 'Положение о премировании\n2.3. Премия выплачивается не позднее 10 числа месяца.',
                'Приказ о премировании 2031.txt': 'Приказ о премировании\n1. Премия выплачивается не позднее 25 числа месяца.'},
         question='До какого числа выплачивается премия?', sides=('2.3. Премия', '1. Премия')),
]

def conflict(s, status='partial', issue='conflicting_documents', sides=None, facts=('priority_rule',), answer=''):
    def model(payload):
        ids = [next(f['id'] for f in payload['evidence'] if n in f['text']) for n in (sides or s['sides'])]
        return {'status': status, 'answer': answer, 'source_ids': ids, 'requested_facts': list(facts), 'issue': issue}
    return model

class DocumentConflictTests(unittest.TestCase):
    def test_conflict_is_named_with_each_side_verbatim(self):
        for s in CONFLICTS:
            with self.subTest(s['question']):
                text, status, model, events = run(s['question'], [conflict(s), confirm()], s['files'])
                self.assertEqual(status, 'partial', text)
                lines = text.split('\n')
                self.assertEqual(lines[0], ISSUES['conflicting_documents'])
                for body in s['files'].values():
                    self.assertIn(body.split('\n')[1] + '»', text)
                self.assertIn(FOLLOWUPS['priority_rule'], text)
                self.assertNotIn('Приведённые документы подтверждают только указанную часть', text)
                self.assertEqual(model.calls[-1][1]['candidate']['issue'], 'conflicting_documents')

    def test_checked_model_text_precedes_the_application_statement(self):
        s = CONFLICTS[0]
        prose = 'В договоре срок оплаты 30 календарных дней (п. 4.1), а в письме поставщика — 60 календарных дней.'
        text, status, _, events = run(s['question'], [conflict(s, answer=prose), confirm()], s['files'])
        self.assertEqual(status, 'partial')
        self.assertTrue(text.startswith(prose + '\n' + ISSUES['conflicting_documents']), text)
        self.assertIn('«4.1. Оплата производится', text)
        self.assertEqual(events[-1]['prose'], 'published')

    def test_clarify_with_conflict_states_it_once(self):
        s = CONFLICTS[1]
        text, status, _, _ = run(s['question'], [conflict(s, status='clarify'), confirm()], s['files'])
        self.assertEqual(status, 'clarify')
        self.assertEqual(text.count(ISSUES['conflicting_documents']), 1)
        self.assertEqual(text.count(FOLLOWUPS['priority_rule']), 1)

    def test_malformed_conflict_is_not_published(self):
        s = CONFLICTS[0]
        one_side = (s['sides'][0],)
        same_document = dict(s, files={'Договор поставки М-2-2033.txt': 'Договор № М-2/2033\n4.1. Оплата в течение 30 дней.\n4.2. Оплата в течение 60 дней.'}, sides=('4.1.', '4.2.'))
        for case, first in [(s, conflict(s, sides=one_side)), (s, conflict(s, status='answer', facts=())), (same_document, conflict(same_document))]:
            with self.subTest(first=first):
                text, status, model, _ = run(case['question'], [first, first, confirm()], case['files'])
                self.assertEqual((text, status), (UNVERIFIED, 'unverified'))
                self.assertTrue(all('candidate' not in p for _, p in model.calls))

    def test_verifier_rejection_of_the_conflict_is_respected(self):
        s = CONFLICTS[1]
        reject = lambda p: {'approved': False, 'complete': False, 'status': p['candidate']['status'], 'answer_supported': False,
                            'claim_checks': [{'index': i, 'supported': True, 'applicable': True} for i in range(len(p['candidate']['claims']))]}
        text, status, _, _ = run(s['question'], [conflict(s), reject, conflict(s), reject], s['files'])
        self.assertEqual((text, status), (UNVERIFIED, 'unverified'))

if __name__ == '__main__':
    unittest.main()
