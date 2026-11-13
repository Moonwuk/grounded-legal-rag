"""The source line names the edition a document states about itself.

Demo question 10 lost to the organizer starter with both independent judges:
the base holds two editions of the approval regulation, the golden answer and
the starter name «в редакции от 01.03.2025», our source line named only the
file. The label comes from the document header, not from the model.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import edition_label  # noqa: E402
from test_prose_answers import run  # noqa: E402

NEW = ('ПОЛОЖЕНИЕ О ЗАКУПКАХ ООО «ВЕКТОР»\nУтверждено приказом № 7-П от 20.01.2031\n'
       'Редакция от 05.02.2031. Действует с 05.02.2031. Редакция от 14.06.2029 утрачивает силу.\n'
       '2.2. Закупку инициирует руководитель подразделения-заказчика.\n')
OLD = ('РЕДАКЦИЯ УТРАТИЛА СИЛУ с 05.02.2031.\nПОЛОЖЕНИЕ О ЗАКУПКАХ ООО «ВЕКТОР»\nРедакция от 14.06.2029\n'
       '2.2. Закупку инициирует отдел снабжения.\n')
FILES = {'Положение о закупках 2031.txt': NEW, 'Положение о закупках 2029.txt': OLD}


class EditionLabelTests(unittest.TestCase):
    def test_labels_from_the_header(self):
        self.assertEqual(edition_label(NEW), 'ред. от 05.02.2031')
        self.assertEqual(edition_label(OLD), 'ред. от 14.06.2029, утратила силу с 05.02.2031')
        self.assertEqual(edition_label('ДОГОВОР № Д-1/2031\n1.1. Предмет договора.'), '')
        # A date deep in the body is not the document's edition.
        self.assertEqual(edition_label('Договор\n' + 'x\n' * 200 + 'Редакция от 01.01.2030'), '')

    def test_source_line_names_the_edition(self):
        def model(payload):
            f = next(f for f in payload['evidence'] if 'руководитель подразделения-заказчика' in f['text'])
            return {'status': 'answer', 'answer': 'Закупку инициирует руководитель подразделения-заказчика (п. 2.2).', 'source_ids': [f['id']]}

        def verdict(payload):
            return {'approved': True, 'complete': True, 'status': 'answer', 'answer_supported': True,
                    'claim_checks': [{'index': 0, 'supported': True, 'applicable': True}]}
        text, status, _, _ = run('Кто инициирует закупку по положению о закупках?', [model, verdict], FILES)
        self.assertEqual(status, 'answer')
        self.assertIn('Источник: Положение о закупках (ред. от 05.02.2031), п. 2.2.', text)


if __name__ == '__main__':
    unittest.main()
