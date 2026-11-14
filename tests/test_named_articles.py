"""A question that names an article (and a point of it) gets that article.

Diagnostic set on the organizer base (archive PSB_AB_20_vs_24, N20/N21):
«по статье 114 НК РФ» — the dative was not read as an article number;
«по пункту 4 статьи 114 НК РФ … из пункта 2 статьи 112» — «пункт 2» boosted
every fragment starting with «2.» in every document, the long and similarly
worded article 112 took all places and article 114 was never retrieved, so
the fine could not be calculated. A named article now has a reserved place,
and a point bound to an article is looked up in that article only.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_audit_fixes import corpus  # noqa: E402

A40 = ('Источник: Статья 40. УК-Т РФ Обстоятельства, смягчающие и отягчающие взыскание. Учебный кодекс Российской Федерации\n'
       'Статья 40. Обстоятельства, смягчающие и отягчающие взыскание\n'
       '1. Обстоятельствами, смягчающими взыскание, признаются:\n'
       '1) совершение нарушения впервые; смягчающее обстоятельство уменьшает взыскание.\n'
       '2) совершение нарушения под влиянием угрозы; смягчающее обстоятельство учитывается.\n'
       + ''.join(f'{k}) иное смягчающее обстоятельство № {k}, при котором штраф за нарушение может быть уменьшен; смягчающих обстоятельств может быть несколько.\n' for k in range(3, 12)) +
       '2. Обстоятельством, отягчающим взыскание, признается повторное нарушение; отягчающее обстоятельство увеличивает взыскание.\n'
       '3. Смягчающие и отягчающие обстоятельства устанавливаются органом и учитываются при применении взыскания.\n'
       '4. Обстоятельства, смягчающие или отягчающие взыскание, учитываются при наложении взыскания.\n')
A41 = ('Источник: Статья 41. УК-Т РФ Учебные взыскания. Учебный кодекс Российской Федерации\n'
       'Статья 41. Учебные взыскания\n'
       '1. Учебное взыскание является мерой ответственности.\n'
       '2. Взыскания применяются в виде штрафов.\n'
       '3. При наличии хотя бы одного смягчающего обстоятельства размер штрафа подлежит уменьшению не меньше чем в два раза.\n'
       '4. При наличии обстоятельства, предусмотренного пунктом 2 статьи 40, размер штрафа увеличивается на 100 процентов.\n')
FILES = {'законы__УКТ_ст40.txt': A40, 'законы__УКТ_ст41.txt': A41,
         'документы компании__Положение о штрафах.txt': '2. Штраф уплачивается в течение 10 дней.\n4. Повторное нарушение влечёт выговор.\n'}


class NamedArticleTests(unittest.TestCase):
    def texts(self, question, expanded=False):
        with corpus(FILES) as r:
            return [(f.document, f.text) for f in r.search(question, top_k=6, expanded=expanded)]

    def test_named_article_in_every_case_form(self):
        for question in ('По статье 41 Учебного кодекса исходный штраф 50 000 рублей, есть одно смягчающее обстоятельство. Каков штраф?',
                         'Что говорит статья 41 УК-Т РФ о смягчающих обстоятельствах?',
                         'Согласно ст. 41 Учебного кодекса как учитывается смягчающее обстоятельство?',
                         'Как статьей 41 Учебного кодекса учитывается смягчающее обстоятельство?'):
            with self.subTest(question):
                hits = self.texts(question)
                self.assertTrue(any(d.endswith('ст41.txt') for d, _ in hits), hits)

    def test_point_bound_to_its_article(self):
        question = ('По пункту 4 статьи 41 Учебного кодекса исходный штраф 30 000 рублей, установлено отягчающее '
                    'обстоятельство из пункта 2 статьи 40. Смягчающих нет. Каков штраф?')
        for expanded in (False, True):
            hits = self.texts(question, expanded)
            self.assertTrue(any(t.startswith('4. При наличии обстоятельства, предусмотренного') for _, t in hits), hits)
            self.assertTrue(any(t.startswith('2. Обстоятельством, отягчающим') for _, t in hits), hits)
            # The bound point does not pull same-numbered points of other documents.
            self.assertFalse(any(t.startswith('4. Повторное нарушение') for _, t in hits), hits)

    def test_contract_clause_numbers_still_work(self):
        hits = self.texts('В какой срок уплачивается штраф по п. 2 Положения о штрафах?')
        self.assertTrue(any(t.startswith('2. Штраф уплачивается') for _, t in hits), hits)


class OrganizerBaseArticleTests(unittest.TestCase):
    """The same on the organizer base, in wordings and numbers other than N20/N21."""

    @classmethod
    def setUpClass(cls):
        from psb_corpus import load_corpus
        from psb_retrieval import Retriever
        docs, frags = load_corpus(Path(__file__).resolve().parents[1] / 'organizer' / 'knowledge-base.zip')
        cls.r = Retriever(docs, frags)

    def docs(self, question, expanded=False):
        return {f.document.split('__')[-1] for f in self.r.search(question, top_k=6, expanded=expanded)}

    def test_named_tax_articles_are_retrieved(self):
        for question in ('По статье 114 НК РФ исходный штраф 90 000 рублей. Есть одно смягчающее обстоятельство и нет отягчающих. В каких пределах штраф?',
                         'Исходный штраф 40 000 рублей по пункту 4 статьи 114 НК РФ, установлено обстоятельство из пункта 2 статьи 112 НК РФ. Каков штраф?'):
            for expanded in (False, True):
                with self.subTest(question=question, expanded=expanded):
                    found = self.docs(question, expanded)
                    self.assertIn('НК_ст114_действующая.txt', found)
                    if 'статьи 112' in question:
                        self.assertIn('НК_ст112_действующая.txt', found)


if __name__ == '__main__':
    unittest.main()
