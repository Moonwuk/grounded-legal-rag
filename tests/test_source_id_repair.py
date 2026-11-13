"""A fragment id with a one-character slip is restored, anything else still fails.

24-question run after the fixes of 13 November, question N04 (penalty under
one contract and the 10% cap of another): both generations returned a
source_ids entry that was not in the evidence, e.g. «e925b2eed76a75ae3268b»
for «925b2eed76a75ae3268b» — one extra character. expand_selection rejected
the whole candidate before verification, twice, and the row ended as a
generic refusal; the same question is answered correctly in other runs.

An id is restored only when exactly one evidence id is one insertion,
deletion or substitution away. The candidate is then verified as usual.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import expand_selection  # noqa: E402
from test_prose_answers import run  # noqa: E402

EVIDENCE = [Fragment('4c1d9a7e02b55f3e8a61', 'Договор.txt', 0, 50, '5.2. Пени — 0,07% за каждый день.', ''),
            Fragment('b80e6f2c9d1a43aa07e5', 'Договор.txt', 50, 100, '5.3. Предел пеней — 8% суммы.', '')]


def pick(ids):
    return expand_selection({'status': 'answer', 'answer': '', 'source_ids': ids, 'requested_facts': []}, EVIDENCE)


class SourceIdRepairTests(unittest.TestCase):
    def test_one_character_slips_are_restored(self):
        for slip in ('e4c1d9a7e02b55f3e8a61', '4c1d9a7e02b55f3e8a6', '4c1d9a7e02b55f3e8a6f', '4c1d9a7e02b5f3e8a61'):
            with self.subTest(slip):
                value = pick([slip, 'b80e6f2c9d1a43aa07e5'])
                self.assertEqual([c['sources'][0]['fragment_id'] for c in value['claims']],
                                 ['4c1d9a7e02b55f3e8a61', 'b80e6f2c9d1a43aa07e5'])
                self.assertEqual(value['claims'][0]['text'], EVIDENCE[0].text)

    def test_other_ids_still_fail(self):
        for ids in (['ff1d9a7e02b55f3e8a61'],                          # two characters off
                    ['0000000000000000000a'],                          # unrelated
                    ['e4c1d9a7e02b55f3e8a61', '4c1d9a7e02b55f3e8a61'],  # repair would duplicate
                    [7]):
            with self.subTest(ids):
                self.assertEqual(pick(ids), {})

    def test_ambiguous_slip_fails(self):
        near = [Fragment('aaaaaaaaaaaaaaaaaaab', 'd', 0, 1, 'x', ''), Fragment('aaaaaaaaaaaaaaaaaaac', 'd', 1, 2, 'y', '')]
        value = expand_selection({'status': 'answer', 'answer': '', 'source_ids': ['aaaaaaaaaaaaaaaaaaad']}, near)
        self.assertEqual(value, {})

    def test_restored_answer_is_verified_and_published(self):
        files = {'Договор поставки Л-6-2032.txt': 'Договор поставки № Л-6/2032\n5.2. Пени составляют 0,07% от суммы долга за каждый день.\n'}
        text = 'Пени — 0,07% от суммы долга за каждый день (п. 5.2).'

        def generate(payload):
            fid = next(e['id'] for e in payload['evidence'] if e['text'].startswith('5.2.'))
            return {'status': 'answer', 'answer': text, 'source_ids': ['e' + fid], 'requested_facts': [], 'issue': ''}

        def confirm(payload):
            return {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
                    'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}
        answer, status, model, _ = run('Какие пени по Л-6/2032?', [generate, confirm], files)
        self.assertEqual(status, 'answer')
        self.assertTrue(answer.startswith(text), answer)
        self.assertEqual(len(model.calls), 2)


if __name__ == '__main__':
    unittest.main()
