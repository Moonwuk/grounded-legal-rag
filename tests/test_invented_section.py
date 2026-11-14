"""Model text may not cite a named section that the source document does not have.

Demo run final-9dd8e3c, question about the archive memo: the conclusion was
correct but cited «раздел о хранении и выдаче оригиналов»; the memo has no
sections. Two independent judges marked it as a fabricated fact, which zeroes
the question. Numbered sections were already checked as figures; a named one
was not.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import answer_question, invented_section  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

MEMO = ('ПРИКАЗ № ТР-3 от 04.02.2031\nО выдаче пропусков на склад\n'
        'Временный пропуск на склад выдаётся по заявке руководителя на срок не более 2 (двух) календарных дней.\n')
REGULATION = ('ПОЛОЖЕНИЕ О ЗАКУПКАХ\nРаздел 2. Порядок согласования закупок\n'
              '2.1. Закупка свыше 80 000 рублей согласуется с финансовым директором.\n'
              'Глава 4 «Ответственность сторон»\n4.1. За нарушение порядка согласования применяется взыскание.\n')
FILES = {'memo.txt': MEMO, 'reg.txt': REGULATION}


def generate(text, marker):
    def answer(payload):
        fid = next(e['id'] for e in payload['evidence'] if marker in e['text'])
        return {'status': 'answer', 'answer': text, 'source_ids': [fid], 'requested_facts': [], 'issue': ''}
    return answer


VERDICT = {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
           'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}


class InventedSectionTests(unittest.TestCase):
    def test_invented_section_is_not_published(self):
        claim = ('Нет. Временный пропуск выдаётся на срок не более 2 календарных дней '
                 '(приказ № ТР-3, раздел о выдаче и возврате пропусков).')
        with corpus(FILES) as r:
            text, _ = answer_question('Можно ли получить временный пропуск на склад на три дня?', r,
                                      ScriptedModel([generate(claim, 'Временный'), VERDICT] * 2))
        self.assertNotIn('раздел о выдаче', text)
        self.assertIn('не более 2 (двух) календарных дней', text)

    def test_wordings(self):
        with corpus(FILES) as r:
            memo = [f for f in r.fragments if f.document == 'memo.txt']
            reg = [f for f in r.fragments if f.document == 'reg.txt']
            cases = [
                ('См. раздел о выдаче пропусков.', memo, True),
                ('Это следует из главы о пропусках.', memo, True),
                ('Согласно подразделу «Пропуска» приказа.', memo, True),
                ('Это следует из раздела о порядке выдачи пропусков.', memo, True),
                ('В разделе «Выдача пропусков» срок — 2 дня.', memo, True),
                # The document has sections and chapters with these names.
                ('Согласно разделу о порядке согласования закупок, нужен финансовый директор.', reg, False),
                ('Ответственность установлена главой «Ответственность сторон».', reg, False),
                # A named chapter the regulation does not have.
                ('Это указано в главе «Порядок оплаты».', reg, True),
                # A heading of the document called a section is a real part.
                ('Нужен финансовый директор (положение о закупках, раздел «Порядок согласования закупок»).', reg, False),
                ('Срок — 2 дня (приказ № ТР-3, раздел «О выдаче пропусков на склад»).', memo, False),
                # No named section at all.
                ('Пропуск выдаётся не более чем на 2 дня.', memo, False),
                ('Главный бухгалтер о закупке не уведомляется.', reg, False),
                ('Раздел имущества о котором спрашивают не регулируется.', memo, False),
            ]
            for text, selected, expected in cases:
                self.assertEqual(invented_section(text, selected, r), expected, text)


if __name__ == '__main__':
    unittest.main()
