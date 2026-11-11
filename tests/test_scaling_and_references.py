"""Regressions for two defects found on the evaluation workbench (no model calls).

1. Retrieval pulled the whole document family of every lexical hit, including
   hits about another contract; on a dense corpus the expanded search exceeded
   the evidence cap (177 of 500 synthetic questions).
2. A value delegated to a document that IS in the corpus was reported as a
   missing document when the title word had five letters ("талон"/"талоне").
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from psb_policy import value_dependencies
from test_audit_fixes import corpus

def family(number, term, extra):
    slug = number.replace('/', '-')
    return {f'Договор поставки {slug}.txt': f'Договор поставки № {number}\n4.1. Срок оплаты товара составляет {term} календарных дней после поставки.',
            f'Доп соглашение 1 к договору {slug}.txt': f'Дополнительное соглашение к договору № {number}\n1. Срок оплаты товара составляет {term + 15} календарных дней для поставок после изменения.',
            f'Акт сверки {slug}.txt': f'Акт сверки к договору № {number}\n{extra}'}

FILES = {**family('ВК-3/2031', 20, 'Сальдо расчётов на конец квартала равно нулю.'),
         **family('ГН-8/2032', 40, 'Стороны подтвердили отсутствие задолженности по таре.')}

class FamilyExpansionTests(unittest.TestCase):
    def documents(self, question, expanded):
        with corpus(FILES) as r:
            return {f.document for f in r.search(question, top_k=6, expanded=expanded)}

    def test_named_contract_brings_its_family_not_another_one(self):
        for number, other in (('ВК-3/2031', 'ГН-8-2032'), ('ГН-8/2032', 'ВК-3-2031')):
            own = number.replace('/', '-')
            for expanded in (False, True):
                with self.subTest(number=number, expanded=expanded):
                    found = self.documents(f'Какой срок оплаты товара по договору {number}?', expanded)
                    # Own amendment and the linked non-matching document are kept.
                    self.assertIn(f'Доп соглашение 1 к договору {own}.txt', found)
                    self.assertIn(f'Акт сверки {own}.txt', found)
                    # The other contract may be a lexical candidate, but its linked
                    # document is not pulled in. (In expanded mode of this six-file
                    # corpus every file is a lexical candidate by itself.)
                    if not expanded:
                        self.assertNotIn(f'Акт сверки {other}.txt', found)

    def test_question_without_identifier_still_expands_families(self):
        found = self.documents('Какой срок оплаты товара после поставки?', False)
        self.assertIn('Акт сверки ВК-3-2031.txt', found)
        self.assertIn('Акт сверки ГН-8-2032.txt', found)

class DelegatedValueTests(unittest.TestCase):
    CASES = [('6.1. Гарантийный срок на товар устанавливается производителем и указывается в гарантийном талоне.',
              'Гарантийный талон П-4-2032.txt', 'Гарантийный талон к договору № П-4/2032\n2.4. Гарантийный срок составляет 27 месяцев.',
              'Какой гарантийный срок на товар?'),
             ('3.2. Размер вознаграждения определяется заказчиком и указывается в акте приёмки.',
              'Акт приёмки Р-6-2033.txt', 'Акт приёмки к договору № Р-6/2033\n1. Размер вознаграждения составляет 90 000 рублей.',
              'Какой размер вознаграждения?')]

    def gaps(self, clause, files, question):
        with corpus({'Договор.txt': 'Договор\n' + clause, **files}) as r:
            selected = [f for f in r.search(question, top_k=6) if clause[:20] in f.text]
            self.assertTrue(selected)
            return value_dependencies(question, selected, r.documents)

    def test_present_document_is_not_requested(self):
        for clause, name, body, question in self.CASES:
            with self.subTest(name):
                self.assertEqual(self.gaps(clause, {name: body}, question), [])

    def test_absent_or_unrelated_document_is_still_requested(self):
        for clause, name, body, question in self.CASES:
            with self.subTest(name):
                self.assertTrue(self.gaps(clause, {}, question))
                self.assertTrue(self.gaps(clause, {'Протокол разногласий.txt': 'Протокол разногласий\n1. Разногласий нет.'}, question))

if __name__ == '__main__':
    unittest.main()
