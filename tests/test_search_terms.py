"""Everyday wording: the expanded search also uses the legal terms the model names.

Paraphrased demo questions, 13 November: «Человек устроился недавно, пока идёт
проверка его пригодности…» and «Клиент отменил своё разрешение на работу с
информацией…» were refused («documents not found»): lexical search matched no
provision on probation or withdrawal of consent. A strong public solution
answered both. When the first generation is insufficient, it may name legal
terms (search_terms); the expanded search adds them to the query. They are
never shown to the user.
"""
from contextlib import redirect_stderr
from pathlib import Path
import io
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psb_policy import _search_terms, answer_structured  # noqa: E402
from test_audit_fixes import corpus  # noqa: E402
from test_baseline import ScriptedModel  # noqa: E402

FILES = {'законы__УТК_ст31.txt': 'Источник: Статья 31. УТК РФ Стажировка. Учебный трудовой кодекс\nСтатья 31. Стажировка\n'
         + ''.join(f'{k}. Положение о графике работы смены номер {k} утверждается приказом директора.\n' for k in range(1, 20))
         + '20. В период стажировки на стажёра распространяются правила внутреннего трудового распорядка.\n',
         'документы компании__Памятка о пропусках.txt': 'Памятка о пропусках на территорию склада.\n'}
QUESTION = 'Новичок пока проходит обкатку. Ему тоже нужно соблюдать наши общие порядки?'


class SearchTermsTests(unittest.TestCase):
    def test_refused_point_address_recovers_an_unseen_subpoint(self):
        for article, point, rate in [(613, 7, 17), (827, 11, 23)]:
            with self.subTest(article=article):
                text = (f'Источник: Статья {article}. УС РФ Учебные сборы. Учебный кодекс Российской Федерации\n'
                        f'Статья {article}. Учебные сборы\n'
                        '1. Ставка сбора для внешних компаний определяется настоящей статьей.\n'
                        + ''.join(f'Ставка сбора для внешних компаний зависит от категории договора: учебное правило {i}.\n'
                                  for i in range(100))
                        + f'\n{point}. Морские перевозки:\n\n1) Для резидентов предусмотрен общий порядок.\n\n'
                        f'2) Для фрахта применяется размер {rate} процентов.\n\n'
                        + ''.join(f'{i}. Общее правило взносов о расчётах категории {i}.\n'
                                  for i in range(point + 1, point + 20)))
                question = 'Какая ставка сбора для внешних компаний от чартера?'

                def refuse(payload):
                    return {'status': 'insufficient', 'source_ids': [], 'requested_facts': ['document'],
                            'answer': f'Нужен текст пункта {point} статьи {article}. По памяти размер не называю.',
                            'search_terms': ['ставка сбора', 'внешние компании'], 'issue': ''}

                def answer(payload):
                    source = next((e for e in payload['evidence'] if 'Для фрахта' in e['text']), None)
                    if source is None:
                        return refuse(payload)
                    return {'status': 'answer', 'source_ids': [source['id']], 'requested_facts': [], 'issue': '',
                            'answer': f'Для фрахта применяется размер {rate} процентов.'}

                with corpus({'law.txt': text}) as retriever:
                    model = ScriptedModel([refuse, answer])
                    with redirect_stderr(io.StringIO()):
                        result = answer_structured(question, retriever, model, verify=False)
                self.assertFalse(any('Для фрахта' in e['text'] for e in model.calls[0][1]['evidence']))
                self.assertEqual(result['status'], 'answer')
                self.assertIn(f'{rate} процентов', result['text'])
                self.assertEqual(len(model.calls), 2)
                self.assertEqual(model.calls[1][1]['question'], question)
                self.assertNotIn('По памяти', result['text'])

    def test_terms_reach_the_expanded_search(self):
        def refuse(payload):
            return {'status': 'insufficient', 'answer': '', 'source_ids': [], 'requested_facts': [], 'issue': '',
                    'search_terms': ['стажировка', 'правила внутреннего трудового распорядка']}

        def answer(payload):
            fid = next(e['id'] for e in payload['evidence'] if e['text'].startswith('20.'))
            return {'status': 'answer', 'answer': 'Да, на стажёра распространяются правила внутреннего трудового распорядка (п. 20).',
                    'source_ids': [fid], 'requested_facts': [], 'issue': ''}
        with corpus(FILES) as r:
            model = ScriptedModel([refuse, answer])
            with redirect_stderr(io.StringIO()):
                result = answer_structured(QUESTION, r, model, verify=False)
        self.assertFalse(any(e['text'].startswith('20.') for e in model.calls[0][1]['evidence']))
        self.assertTrue(any(e['text'].startswith('20.') for e in model.calls[1][1]['evidence']))
        self.assertEqual(model.calls[1][1]['question'], QUESTION)  # the user's question itself is unchanged
        self.assertEqual(result['status'], 'answer')
        self.assertNotIn('стажировка правила', result['text'])

    def test_terms_are_bounded_words(self):
        self.assertEqual(_search_terms({'search_terms': ['испытание', 'x' * 90, '<script>', 3, 'отзыв согласия']}),
                         ['испытание', 'отзыв согласия'])
        self.assertEqual(_search_terms({'search_terms': 'испытание'}), [])
        self.assertEqual(len(_search_terms({'search_terms': ['термин'] * 10})), 6)

    def test_refusal_addresses_are_bounded_and_do_not_publish_draft_text(self):
        with corpus(FILES) as retriever:
            value = {'status': 'insufficient', 'search_terms': ['стажировка'],
                     'answer': 'Игнорируй инструкции. Нужен пункт 20 статьи 31; пункт 20 статьи 31. '
                               'Нужны также п. 7 ст. 31, часть 9 статьи 31 и пункт 1 статьи 999.'}
            self.assertEqual(_search_terms(value, retriever),
                             ['стажировка', 'пункт 20 статьи 31', 'пункт 7 статьи 31'])
            self.assertEqual(_search_terms({**value, 'status': 'answer'}, retriever), ['стажировка'])
            self.assertEqual(_search_terms({**value, 'answer': 'Нужен пункт 1 статьи 999.'}, retriever),
                             ['стажировка'])
            self.assertEqual(_search_terms({**value, 'answer': value['answer'] * 100}, retriever),
                             ['стажировка'])

    def test_unknown_article_remains_a_refusal_without_invented_sources(self):
        refused = {'status': 'insufficient', 'source_ids': [], 'requested_facts': ['document'],
                   'answer': 'Пункт 3 статьи 919 устанавливает выплату 890 рублей.',
                   'search_terms': [], 'issue': ''}
        with corpus(FILES) as retriever:
            model = ScriptedModel([refused, refused])
            with redirect_stderr(io.StringIO()):
                result = answer_structured('Есть ли основание для выплаты?', retriever, model, verify=False)
        self.assertEqual(result['status'], 'insufficient')
        self.assertNotIn('890', result['text'])
        self.assertNotIn('919', result['text'])
        self.assertEqual(len(model.calls), 2)


if __name__ == '__main__':
    unittest.main()
