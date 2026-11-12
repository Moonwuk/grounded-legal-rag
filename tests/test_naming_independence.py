"""Document roles come from the text, not from the organizer file-name scheme.

Before: a regulation family was linked only when the file name contained
"регламент согласования", and laws were excluded by the "законы__" prefix.
With other names the editions of a regulation were no longer kept together.
"""
from pathlib import Path
import sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_audit_fixes import corpus

OLD = ('РЕДАКЦИЯ УТРАТИЛА СИЛУ с 01.04.2031.\nРЕГЛАМЕНТ ЗАКУПОК ООО «ТЕСТ-ЛАЙН»\n'
       '1. Договор на сумму свыше 7 000 000 рублей согласует финансовый директор.\n')
NEW = ('РЕГЛАМЕНТ ЗАКУПОК ООО «ТЕСТ-ЛАЙН»\nУтверждён приказом № 3-П от 15.03.2031\n'
       '1. Договор на сумму свыше 9 000 000 рублей согласует генеральный директор.\n')
LETTER = 'ООО «ТЕСТ-ЛАЙН»\nСлужба закупок\nНапоминаем, что регламент закупок обязателен для всех подразделений.\n'
LAW = ('Источник: Статья 41. Трудовой кодекс Российской Федерации\nСтатья 41. Коллективный договор\n'
       'Локальный регламент работодателя не может ухудшать положение работника.\n')
OTHER = 'ДОГОВОР ПОСТАВКИ № Р-9/2031\nСрок поставки составляет 12 рабочих дней.\n'


def files(names):
    return dict(zip(names, (OLD, NEW, LETTER, LAW, OTHER)))


class NamingIndependenceTests(unittest.TestCase):
    def documents(self, names, question):
        with corpus(files(names)) as r:
            return r, {f.document for f in r.search(question)}

    def test_regulation_editions_stay_together_with_opaque_names(self):
        names = ['doc_04.txt', 'doc_01.md', 'doc_03.txt', 'doc_02.txt', 'doc_05.txt']
        r, docs = self.documents(names, 'Кто согласует договор на сумму 8 000 000 рублей по регламенту закупок?')
        self.assertEqual(r.regulations, {'doc_04.txt', 'doc_01.md'})
        self.assertLessEqual({'doc_04.txt', 'doc_01.md', 'doc_03.txt'}, docs)
        # A law that mentions a regulation is not a member of the company family.
        self.assertNotIn('doc_02.txt', r.regulations)
        self.assertIn('doc_02.txt', r.law_by_doc)

    def test_same_roles_as_organizer_style_names(self):
        organizer = ['документы компании__Регламент закупок ред 2030 (утратил силу).txt',
                     'документы компании__Регламент закупок ред 2031.md',
                     'документы компании__Письмо службы закупок.txt',
                     'законы__ТК_ст41_действующая.txt', 'документы компании__Договор поставки Р-9-2031.txt']
        opaque = ['a.txt', 'b.md', 'c.txt', 'd.txt', 'e.txt']
        question = 'Кто согласует договор на сумму 8 000 000 рублей по регламенту закупок?'
        first, docs_first = self.documents(organizer, question)
        second, docs_second = self.documents(opaque, question)
        rename = dict(zip(organizer, opaque))
        # File-name words may change the rank; the roles and the family may not.
        self.assertEqual({rename[n] for n in first.regulations}, second.regulations)
        self.assertEqual({rename[n] for n in first.law_by_doc}, set(second.law_by_doc))
        self.assertLessEqual({'a.txt', 'b.md', 'c.txt'}, {rename[n] for n in docs_first})
        self.assertLessEqual({'a.txt', 'b.md', 'c.txt'}, docs_second)

if __name__ == '__main__':
    unittest.main()
