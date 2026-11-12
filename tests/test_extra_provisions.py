"""A verified answer with a provision nobody asked about gets one attempt without it.

Demo answers judged against the organizer golden by models other than the
solution model: a true clause of the contract that the question did not ask
about (rent question answered with the utilities clause or the clause on
raising the rent) was marked as a fabricated fact, which zeroes the question.
The verifier now marks such a provision needed=false; the verified answer is
kept, and it is replaced only by another verified answer with text.

Also here: when the verifier rejects an inapplicable provision and the rest
is rejected too (combined run 9dd8e3c, multi_document-0022/0080/0086: the
applicable provision was never selected), one more generation is told so.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import unneeded  # noqa: E402
from test_prose_answers import run  # noqa: E402

SCENARIOS = [
    dict(files={'Договор хранения ХР-9-2032.txt': 'Договор хранения № ХР-9/2032\n4.1. Плата за хранение составляет 73 000 рублей в месяц.\n'
                '4.2. Плата вносится не позднее 12-го числа месяца.\n4.6. Страхование груза оплачивается Поклажедателем отдельно.\n'},
         question='Какая плата за хранение по договору ХР-9/2032?', asked='4.1.', extra='4.6.',
         long='Плата за хранение — 73 000 рублей в месяц (п. 4.1). Страхование груза оплачивается отдельно (п. 4.6).',
         short='Плата за хранение — 73 000 рублей в месяц (п. 4.1).'),
    dict(files={'Положение о командировках.txt': 'Положение о командировках\n2.3. Суточные составляют 1 450 рублей за каждый день командировки.\n'
                '2.7. Проезд в такси компенсируется по решению руководителя.\n'},
         question='Какой размер суточных в командировке?', asked='2.3.', extra='2.7.',
         long='Суточные — 1 450 рублей за каждый день командировки (п. 2.3). Проезд в такси компенсируется по решению руководителя (п. 2.7).',
         short='Суточные — 1 450 рублей за каждый день командировки (п. 2.3).'),
]


def generate(s, text, needles):
    def model(payload):
        ids = [next(f['id'] for f in payload['evidence'] if n in f['text']) for n in needles]
        return {'status': 'answer', 'answer': text, 'source_ids': ids}
    return model


def judge(not_needed=(), approved=True, text=True, needed_field=True):
    def model(payload):
        claims = payload['candidate']['claims']
        checks = [{'index': i, 'supported': True, 'applicable': True} for i in range(len(claims))]
        if needed_field:
            for c in checks:
                c['needed'] = c['index'] not in not_needed
        return {'approved': approved, 'complete': approved, 'status': 'answer', 'answer_supported': text and approved, 'claim_checks': checks}
    return model


class ExtraProvisionTests(unittest.TestCase):
    def test_unasked_provision_is_dropped_by_a_verified_retry(self):
        for s in SCENARIOS:
            with self.subTest(s['question']):
                long, short = generate(s, s['long'], (s['asked'], s['extra'])), generate(s, s['short'], (s['asked'],))
                text, status, model, _ = run(s['question'], [long, judge(not_needed=[1]), short, judge()], s['files'])
                self.assertEqual(status, 'answer')
                self.assertTrue(text.startswith(s['short']), text)
                self.assertNotIn(s['extra'], text)
                retry = model.calls[2][1]
                self.assertEqual(retry.get('retry_reason'), 'answer_extra_provisions')
                extra_id = next(f['id'] for f in retry['evidence'] if s['extra'] in f['text'])
                self.assertEqual(retry.get('retry_extra_source_ids'), [extra_id])

    def test_verified_answer_is_kept_when_the_retry_is_not_a_verified_text(self):
        for s in SCENARIOS:
            long, short = generate(s, s['long'], (s['asked'], s['extra'])), generate(s, s['short'], (s['asked'],))
            for name, second in (('rejected', judge(approved=False)), ('text unconfirmed', judge(text=False))):
                with self.subTest(s['question'] + ' / ' + name):
                    text, status, model, _ = run(s['question'], [long, judge(not_needed=[1]), short, second], s['files'])
                    self.assertEqual(status, 'answer')
                    self.assertTrue(text.startswith(s['long']), text)
                    self.assertEqual(len(model.calls), 4)

    def test_no_retry_without_an_explicit_mark_or_when_nothing_would_remain(self):
        for s in SCENARIOS:
            long = generate(s, s['long'], (s['asked'], s['extra']))
            for name, first in (('no field', judge(needed_field=False)), ('all needed', judge()), ('none needed', judge(not_needed=[0, 1]))):
                with self.subTest(s['question'] + ' / ' + name):
                    text, status, model, _ = run(s['question'], [long, first], s['files'])
                    self.assertEqual(status, 'answer')
                    self.assertTrue(text.startswith(s['long']))
                    self.assertEqual(len(model.calls), 2)

    def test_unneeded_reads_only_wellformed_checks(self):
        c = {'status': 'answer', 'claims': [{}, {}]}
        check = lambda *needed: {'claim_checks': [{'index': i, 'needed': n} for i, n in enumerate(needed)]}
        self.assertEqual(unneeded(c, check(True, False)), [1])
        self.assertEqual(unneeded(c, check(True, None)), [])
        self.assertEqual(unneeded(c, check(False, False)), [])
        self.assertEqual(unneeded(c, check(True)), [])
        self.assertEqual(unneeded(c, {'claim_checks': [{'index': 0, 'needed': True}, {'index': 7, 'needed': False}]}), [])
        self.assertEqual(unneeded(c, None), [])


class RegenerationAfterFailedReductionTests(unittest.TestCase):
    def test_applicable_provision_selected_on_the_told_retry(self):
        from test_contrast_and_restricted_answers import REVISIONS
        for s in REVISIONS:
            with self.subTest(s['question']):
                # First selection: only the inapplicable provision plus an unrelated one is impossible
                # here, so the rejection is scripted: inapplicable, then "incomplete".
                def wrong(payload):
                    ids = [next(f['id'] for f in payload['evidence'] if n in f['text']) for n in (s['own'], s['other'])]
                    return {'status': 'answer', 'answer': s['prose'], 'source_ids': ids}

                def inapplicable(payload):
                    n = len(payload['candidate']['claims'])
                    return {'approved': False, 'complete': False, 'status': 'answer', 'answer_supported': False,
                            'claim_checks': [{'index': i, 'supported': True, 'applicable': i != 1} for i in range(n)]}

                def incomplete(payload):
                    n = len(payload['candidate']['claims'])
                    return {'approved': False, 'complete': False, 'status': 'answer', 'answer_supported': False,
                            'claim_checks': [{'index': i, 'supported': True, 'applicable': True} for i in range(n)]}

                def right(payload):
                    f = next(f for f in payload['evidence'] if s['own'] in f['text'])
                    return {'status': 'answer', 'answer': '', 'source_ids': [f['id']]}

                ok = lambda payload: {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
                                      'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}
                text, status, model, events = run(s['question'], [wrong, inapplicable, incomplete, right, ok], s['files'])
                self.assertEqual(status, 'answer', text)
                self.assertIn(s['value'], text)
                self.assertEqual(model.calls[3][1].get('retry_reason'), 'inapplicable_provision')
                self.assertEqual([e['reduced'] for e in events], [False, True, False])


if __name__ == '__main__':
    unittest.main()
