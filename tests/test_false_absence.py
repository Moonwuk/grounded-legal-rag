"""Model text may not say that a document with an identifier is missing when
the base holds a document with that identifier.

Combined run, missing_information-0064 and 0070: "Ставка неустойки для
КТ-65/2026 … не определена: договора с таким обозначением в базе нет" while
documents of КТ-65/2026 are in the base — a fabricated fact, which zeroes the
judge's score for the question. Over 1 893 earlier answers the rule fires on
these two and on nothing else.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import answer_question, false_absence  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

FILES = {'fin.txt': 'СПРАВКА № КТ-4/2031\nДля объекта КТ-4/2031 лимит резерва составляет 52000 рублей.\n',
         'law.txt': 'Источник: Статья 330. Гражданский кодекс Российской Федерации\nСтатья 330. Неустойкой признается денежная сумма, определенная законом или договором.\n'}


class Known:
    doc_ids = {'a': {'кт-4/2031'}}


def generate(text):
    def answer(payload):
        fid = next(e['id'] for e in payload['evidence'] if 'Неустойкой' in e['text'])
        return {'status': 'answer', 'answer': text, 'source_ids': [fid], 'requested_facts': [], 'issue': ''}
    return answer


VERDICT = {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
           'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}


class FalseAbsenceTests(unittest.TestCase):
    def test_false_absence_is_not_published(self):
        claim = 'Ставка неустойки для КТ-4/2031 не определена: договора с таким обозначением в базе нет.'
        with corpus(FILES) as r:
            text, _ = answer_question('Какова ставка неустойки для КТ-4/2031?', r,
                                      ScriptedModel([generate(claim), VERDICT, generate(claim), VERDICT]))
        self.assertNotIn('в базе нет', text)

    def test_wordings(self):
        cases = [
            ('Ставку неустойки по КТ-4/2031 определить нельзя: договора с таким номером в ней нет.', True),
            ('Договор КТ-4/2031 в базе отсутствует.', True),
            ('Нет договора № КТ-4/2031.', True),
            ('Документа о неустойке по КТ-4/2031 в базе нет.', False),           # a document about a subject
            ('По договору КТ-4/2031 неустойка не установлена, документа о ней нет.', False),
            ('В договоре КТ-4/2031 условия о неустойке нет.', False),
            ('Договора КТ-9/2031 в базе нет.', False),                           # really absent
            ('Нет, лимит (справка КТ-4/2031 № 1) составляет 5 рублей.', False),  # yes/no answer, citation
            ('Базовое условие договора КТ-4/2031 применяется до даты; исключений нет.', False),
        ]
        for text, expected in cases:
            self.assertEqual(false_absence(text, Known()), expected, text)


if __name__ == '__main__':
    unittest.main()
