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


if __name__ == '__main__':
    unittest.main()
