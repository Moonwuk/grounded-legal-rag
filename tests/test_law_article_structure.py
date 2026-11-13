"""Long law articles: a named part with its sanction, and the article outline.

Check questions written from the organizer base on 13 November (one-call
version): «Какой штраф … установлен частью 1 статьи 13.11 КоАП РФ?» and «По
какой ставке НДС облагается реализация, если не применяются ставки 0 и 10
процентов?» were refused as «documents not found». «Часть 1 статьи» was not
read like «пункт 1 статьи»; the sanction of a part («влечет наложение штрафа …»)
is a separate paragraph that the reserved point did not bring; and the short
general-rate point of a long article lost to dozens of fragments on the
special cases. Synthetic articles with other numbers and wording.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_audit_fixes import corpus  # noqa: E402
import time  # noqa: E402
from psb_corpus import load_corpus  # noqa: E402
from psb_retrieval import Retriever  # noqa: E402
ROOT = Path(__file__).resolve().parents[1]

FILLER = ''.join(f'абзац {k}) поставки товаров группы {k}, перечисленных в перечне, утверждаемом правительством, '
                 f'облагаются по ставке 0 процентов при соблюдении условий подпункта {k}.\n' for k in range(1, 70))
TAX = ('Источник: Статья 71. УНК РФ Ставки сбора. Учебный налоговый кодекс Российской Федерации\n'
       'Статья 71. Ставки сбора\n'
       '1. Обложение производится по ставке сбора 0 процентов при реализации:\n' + FILLER +
       '2. Обложение производится по ставке сбора 9 процентов при реализации детских товаров.\n'
       + ''.join(f'абзац 9-{k}) детские товары группы {k} облагаются по ставке 9 процентов.\n' for k in range(1, 40)) +
       '3. Обложение производится по ставке сбора 19 процентов в случаях, не указанных в пунктах 1 и 2 настоящей статьи.\n'
       '4. При получении предоплаты сумма сбора определяется расчётным методом.\n')
KINDS = ['анкетных', 'медицинских', 'биометрических', 'платёжных', 'учебных', 'кадровых', 'семейных', 'архивных',
         'страховых', 'жилищных', 'налоговых', 'транспортных', 'пенсионных', 'судебных', 'почтовых', 'складских',
         'гостиничных', 'спортивных', 'музейных', 'театральных', 'клубных', 'дачных', 'лесных', 'речных']
AMOUNTS = ['десяти', 'двадцати', 'тридцати', 'сорока', 'пятидесяти', 'шестидесяти', 'семидесяти', 'восьмидесяти']
FINES = ('Источник: Статья 21.4. УКоАП РФ Нарушения в области учебных данных. Учебный кодекс\n'
         'Статья 21.4. Нарушения в области учебных данных\n'
         + ''.join(f'Часть изменена федеральным законом.\n{k}. Нарушение порядка обработки {kind} сведений -\n'
                   f'влечет наложение административного штрафа на граждан в размере от {AMOUNTS[k % 8]} тысяч рублей; '
                   f'на юридических лиц - от {AMOUNTS[(k + 3) % 8]} тысяч до {AMOUNTS[(k + 5) % 8]} тысяч рублей.\n'
                   f'Обработка {kind} сведений включает сбор, запись, хранение, уточнение и передачу таких сведений '
                   f'третьим лицам без уведомления оператора.\n' for k, kind in enumerate(KINDS, 1)))
FILES = {'законы__УНК_ст71.txt': TAX, 'законы__УКоАП_ст21.4.txt': FINES,
         'документы компании__Памятка.txt': 'Памятка по сбору и штрафам для сотрудников.\n'}


class LawArticleStructureTests(unittest.TestCase):
    def texts(self, question):
        with corpus(FILES) as r:
            return [f.text for f in r.search(question, top_k=6)]

    def test_named_part_brings_its_sanction(self):
        for question in ('Какой штраф для юридического лица установлен частью 1 статьи 21.4 УКоАП?',
                         'Какой штраф по ч. 1 ст. 21.4 для граждан?'):
            with self.subTest(question):
                texts = self.texts(question)
                self.assertTrue(any(t.startswith('1. Нарушение порядка обработки анкетных сведений') for t in texts))
                self.assertTrue(any('на юридических лиц - от пятидесяти тысяч до семидесяти тысяч' in t for t in texts), texts)

    def test_general_rule_of_a_long_article_is_in_the_outline(self):
        for question in ('По какой ставке сбора облагается реализация, если не применяются ставки 0 и 9 процентов?',
                         'По статье 71 общая ставка сбора — 18 процентов, верно?'):
            with self.subTest(question):
                texts = self.texts(question)
                self.assertTrue(any(t.startswith('3. Обложение производится по ставке сбора 19 процентов') for t in texts))



class AbbreviationTests(unittest.TestCase):
    """«утечка ПДн»: the law says «персональных данных», never «ПДн»."""

    LAW = ('Источник: Статья 8.2. УКоАП РФ Ответственность операторов. Учебный кодекс\n'
           'Статья 8.2. Ответственность операторов\n'
           + ''.join(f'{k}. Нарушение правил хранения архивных документов вида {k} влечет предупреждение.\n' for k in range(1, 30)) +
           '30. Неуведомление уполномоченного органа о неправомерной передаче персональных данных -\n'
           'влечет наложение штрафа на юридических лиц в размере от семисот тысяч до девятисот тысяч рублей.\n')

    def test_common_abbreviations_find_the_spelled_out_terms(self):
        with corpus({'законы__УКоАП_ст8.2.txt': self.LAW, 'документы компании__Памятка.txt': 'Памятка о хранении.\n'}) as r:
            for question in ('Какой штраф для компании, если не сообщили об утечке ПДн?',
                             'Какой штраф за неуведомление Роскомнадзора об утечке?'):
                with self.subTest(question):
                    texts = [f.text for f in r.search(question, top_k=6)]
                    self.assertTrue(any('от семисот тысяч до девятисот тысяч' in t for t in texts))


class OrganizerBaseReproductionTests(unittest.TestCase):
    """The reproduced misses on the organizer base itself (retrieval only)."""

    @classmethod
    def setUpClass(cls):
        documents, fragments = load_corpus(ROOT / 'organizer/knowledge-base.zip', time.monotonic() + 300)
        cls.retriever = Retriever(documents, fragments)

    def test_reproduced_questions_get_their_provisions(self):
        for question, needle in (
                ('Какой штраф для юридического лица установлен частью 1 статьи 13.11 КоАП РФ?',
                 'на юридических лиц - от ста пятидесяти тысяч до трехсот тысяч рублей'),
                ('По какой ставке НДС облагается реализация товаров, если не применяются ставки 0 и 10 процентов?',
                 'по налоговой ставке 22 процента в случаях, не указанных в пунктах 1, 2 и 4')):
            with self.subTest(question):
                texts = [f.text for f in self.retriever.search(question, top_k=6)]
                self.assertTrue(any(needle in t for t in texts))


if __name__ == '__main__':
    unittest.main()
