"""Application-owned refusal and missing-value wording.

Organizer demo, question 3 (a topic the base does not cover): the golden answer
says that the base has no documents on the topic, that the assistant does not
answer from memory, and whom to ask; our refusal said «недостаточно оснований …
предоставьте: документ с условиями» — a request the user cannot meet. Question
17 (warranty «указывается в гарантийном талоне»): the golden answer opens with
«конкретный срок в договоре не установлен»; ours opened with the bare quotation.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_prose_answers import run  # noqa: E402


def refuse(codes):
    return lambda payload: {'status': 'insufficient', 'answer': '', 'source_ids': [], 'requested_facts': codes, 'issue': ''}


VERDICT = lambda payload: {'approved': True, 'complete': True, 'status': 'insufficient', 'answer_supported': True, 'claim_checks': []}


class RefusalWordingTests(unittest.TestCase):
    def test_topic_outside_the_base(self):
        text, status, _, _ = run('Какой размер компенсации за неиспользованный отпуск?', [refuse(['document'])] * 2 + [VERDICT])
        self.assertEqual(status, 'insufficient')
        self.assertTrue(text.startswith('В базе знаний нет документов по вопросу «Какой размер компенсации'), text)
        self.assertIn('По памяти отвечать не буду', text)
        self.assertIn('обратитесь к юристу', text)
        self.assertNotIn('Уточните', text)
        # Golden refusal is about 35 words; the old one was over 60.
        self.assertLessEqual(len(text.split()), 45, text)

    def test_long_question_is_not_repeated(self):
        question = ('Какой размер компенсации за неиспользованный отпуск положен работнику, который увольняется '
                    'по собственному желанию после двух лет работы в компании?')
        text, _, _, _ = run(question, [refuse(['document'])] * 2 + [VERDICT])
        self.assertTrue(text.startswith('В базе знаний нет документов по этому вопросу, поэтому'), text)
        self.assertNotIn('собственному желанию', text)
        self.assertLessEqual(len(text.split()), 40, text)

    def test_a_specific_missing_fact_is_still_asked_for(self):
        text, _, _, _ = run('Какой срок оплаты по договору?', [refuse(['event_date'])] * 2 + [VERDICT])
        self.assertIn('Уточните или предоставьте: дата события.', text)
        self.assertIn('По памяти отвечать не буду', text)
        self.assertNotIn('обратитесь к юристу', text)

    def test_value_kept_in_another_document_opens_with_the_conclusion(self):
        files = {'Договор Л-3-2034.txt': 'Договор № Л-3/2034\n8.1. Срок поверки устанавливается изготовителем и указывается в паспорте прибора.\n'}
        def select(payload):
            f = next(f for f in payload['evidence'] if '8.1.' in f['text'])
            return {'status': 'partial', 'answer': '', 'source_ids': [f['id']], 'requested_facts': ['document']}
        verdict = lambda payload: {'approved': True, 'complete': True, 'status': 'partial', 'answer_supported': True,
                                   'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}
        text, _, _, _ = run('Какой срок поверки прибора по договору Л-3/2034?', [select, verdict] * 2, files)
        self.assertTrue(text.startswith('Конкретное значение в найденных документах не установлено'), text)
        self.assertIn('«указывается в паспорте прибора»', text)
        self.assertIn('«8.1. Срок поверки', text)


if __name__ == '__main__':
    unittest.main()
