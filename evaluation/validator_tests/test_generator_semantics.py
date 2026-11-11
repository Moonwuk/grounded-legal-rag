"""Layouts may change structure, never the legal meaning the gold relies on.

Smoke f39195a contradiction-0000: the letter layout appended "электронная
копия используется для ознакомления; условия не изменяет" to every letter,
including the "conflicting" contract. The model correctly treated that copy
as non-operative, while the gold still expected an unresolved conflict.
"""
import re
import unittest
from evaluation.generate_corpus import FAMILIES,render_document,wording,fact

# Statements about the force of the document or of its conditions. Gold treats
# every rendered document as operative, so boilerplate must not say otherwise.
FORCE=re.compile(
    r'для\s+ознакомлени|не\s+име\w*\s+(?:юридическ\w+\s+)?сил|недействительн|утратил\w*\s+сил'
    r'|(?:услови\w*|положени\w*|документ\w*|редакци\w*|копи\w*)[^.\n]{0,60}?\bне\s+(?:изменя|применя|действу|порожда)'
    r'|\bне\s+(?:изменя|отменя)\w*\s+(?:услови|положени|срок)',re.I)

def boilerplate(family,facts):
    spec=dict(title='CONTRACT № ЗТ-9/2033 / 0007 (conflict)',group=4,subject='ЗТ-9/2033',family=family,facts=facts,serial=7)
    text=render_document(spec)
    for f in facts:
        clause=wording(f)
        assert clause in text,(family,clause)
        text=text.replace(clause,'')
    return text

class LayoutSemanticsTests(unittest.TestCase):
    def test_marker_detects_known_non_operative_wording(self):
        for bad in ['Примечание [1]: электронная копия используется для ознакомления; условия не изменяет.',
                    'Настоящая редакция не применяется к расчётам.','Документ не имеет юридической силы.',
                    'Письмо не изменяет условий договора.']:
            self.assertTrue(FORCE.search(bad),bad)
        for fine in ['Порядок регистрации материалов не определяет срок оплаты.',
                     'Указанное исключение не распространяется на иных контрагентов.',
                     'Примечание [1]: нумерация приложений приведена по реестру отправки.']:
            self.assertFalse(FORCE.search(fine),fine)

    def test_no_layout_declares_its_conditions_non_operative(self):
        variants=[[fact('ЗТ-9/2033','payment_term',61,'calendar_days',valid_from='2033-03-01')],
                  [fact('ЗТ-9/2033','limit',73500,'RUB','решение комиссии','утверждение бюджета'),
                   fact('ЗТ-9/2033','duty',True,'boolean','при смене банка','проверка реквизитов')]]
        for family in FAMILIES:
            for facts in variants:
                with self.subTest(family=family,facts=len(facts)):
                    self.assertIsNone(FORCE.search(boilerplate(family,facts)))

class CorpusIdentityTests(unittest.TestCase):
    def test_corpus_id_follows_rendered_text(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import evaluation.generate_corpus as g
        with tempfile.TemporaryDirectory() as tmp:
            a=g.generate(Path(tmp)/'a','t',40,30,20330301)['corpus_id']
            b=g.generate(Path(tmp)/'b','t',40,30,20330301)['corpus_id']
            original=g.render_document
            with patch.object(g,'render_document',lambda spec:original(spec)+'\nСлужебная отметка.'):
                c=g.generate(Path(tmp)/'c','t',40,30,20330301)['corpus_id']
        self.assertEqual(a,b);self.assertNotEqual(a,c)

if __name__=='__main__':unittest.main()
