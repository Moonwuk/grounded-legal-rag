"""A partial answer names the part of the request that no provision covers.

Combined run, missing_information-0029 (and 0059 earlier): "Каковы лимит
резерва и ставка неустойки для КТ-30/2026?" was answered with the reserve
limit and "Уточните или предоставьте: номер договора или его текст" — the
model's generic code; the user was not told that the penalty rate is missing.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import answer_question, uncovered_parts  # noqa: E402
from psb_corpus import Fragment  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

FILES = {'fin.txt': 'СПРАВКА № КТ-7/2031\nДля объекта КТ-7/2031 лимит резерва составляет 41000 рублей; условие: решение комиссии.\n',
         'other.txt': 'ДОГОВОР № КТ-8/2031\nСрок поставки составляет 12 рабочих дней.\n'}


def partial(codes):
    def generate(payload):
        fid = next(e['id'] for e in payload['evidence'] if 'лимит резерва' in e['text'])
        return {'status': 'partial', 'answer': '', 'source_ids': [fid], 'requested_facts': codes, 'issue': ''}
    return generate


VERDICT = {'approved': True, 'complete': True, 'status': 'partial', 'answer_supported': True,
           'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}


class PartialGapTests(unittest.TestCase):
    def answer(self, question, codes):
        with corpus(FILES) as r:
            return answer_question(question, r, ScriptedModel([partial(codes), VERDICT, partial(codes), VERDICT]))

    def test_generic_codes_are_replaced_by_the_uncovered_subject(self):
        for codes in (['contract'], ['document'], ['contract', 'document']):
            text, status = self.answer('Каковы лимит резерва и ставка неустойки для КТ-7/2031?', codes)
            self.assertEqual(status, 'partial', codes)
            self.assertIn('«ставка неустойки»', text, codes)
            self.assertNotIn('номер договора', text, codes)
            self.assertIn('41000', text)

    def test_other_wording_and_subject(self):
        text, _ = self.answer('Какой лимит резерва КТ-7/2031, и в каком порядке возвращается аванс?', ['document'])
        self.assertIn('«порядке возвращается аванс»', text)
        self.assertNotIn('каком', text)

    def test_specific_codes_are_kept(self):
        # A date the user must give is not a missing document.
        text, _ = self.answer('Каковы лимит резерва и ставка неустойки для КТ-7/2031?', ['event_date'])
        self.assertIn('дата события', text)

    def test_parts(self):
        lim = Fragment('x', 'd', 0, 10, 'Для объекта КТ-7/2031 лимит резерва составляет 41000 рублей.', '')
        self.assertEqual(uncovered_parts('Каковы лимит резерва и ставка неустойки для КТ-7/2031?', [lim]), ['ставка неустойки'])
        self.assertEqual(uncovered_parts('Каков лимит резерва КТ-7/2031?', [lim]), [])
        # Nothing covered: not a partial gap, the request scope handles it.
        self.assertEqual(uncovered_parts('Какова ставка неустойки для КТ-7/2031?', [lim]), [])

    def test_lone_noun_before_and_shares_the_next_complement(self):
        # 24-question run on 06a3dda, N24: «Назовите дату и номер дополнительного
        # соглашения …» gave the gap «дату», published as «нет сведений: «дату»».
        rent = Fragment('x', 'd', 0, 10, '2.1. Арендная плата составляет 310 000 рублей в месяц.', '')
        bonus = Fragment('y', 'd', 0, 10, 'Премия по приказу Б-2/2033 составляет 15% оклада.', '')
        self.assertEqual(uncovered_parts('Назовите дату и номер соглашения к Б-11/2031, которым изменили арендную плату.', [rent]), [])
        self.assertEqual(uncovered_parts('Укажите основание и размер премии по приказу Б-2/2033.', [bonus]), [])
        # A lone noun at the end is an item of its own.
        lim = Fragment('z', 'd', 0, 10, 'Для объекта КТ-7/2031 лимит резерва составляет 41000 рублей.', '')
        self.assertEqual(uncovered_parts('Укажите лимит резерва КТ-7/2031 и срок.', [lim]), ['срок'])


    def test_insufficient_does_not_ask_for_a_named_contract_number(self):
        # Smoke 9dd8e3c, missing_information-0001: "Какова ставка неустойки для
        # КТ-2/2026?" got "Уточните или предоставьте: номер договора или его текст".
        def refuse(payload):
            return {'status': 'insufficient', 'answer': '', 'source_ids': [], 'requested_facts': ['contract'], 'issue': ''}
        verdict = {'approved': True, 'complete': True, 'status': 'insufficient', 'answer_supported': True, 'claim_checks': []}
        with corpus(FILES) as r:
            text, status = answer_question('Какова ставка неустойки для КТ-7/2031?', r, ScriptedModel([refuse, refuse, verdict]))
        self.assertEqual(status, 'insufficient')
        self.assertNotIn('номер договора', text)
        self.assertIn('обратитесь к юристу', text)
        # An unknown object still needs its contract.
        with corpus(FILES) as r:
            text, _ = answer_question('Какова ставка неустойки для КТ-55/2031?', r, ScriptedModel([refuse, refuse, verdict]))
        self.assertIn('номер договора', text)

if __name__ == '__main__':
    unittest.main()
