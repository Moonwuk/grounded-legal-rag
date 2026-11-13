"""A missing cross-reference need not block a directly stated, verified answer."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
from psb_policy import answer_question
from test_baseline import ScriptedModel
from test_audit_fixes import corpus, verdict


class ReferenceScopeTests(unittest.TestCase):
    def run_case(self, *, scope='local', required=False, supported=True, direct=True, article=23):
        source = ('1. Обязанность представить доказательство получения разрешения либо наличия '
                  f'оснований статьи {article} настоящего Федерального закона возлагается на заявителя.')
        files = {'rule.txt': 'Источник: Статья 5. Федеральный закон от 03.04.2031 N 432-ФЗ\n'
                 'Статья 5. Разрешение\n' + source}
        question = ('На кого возложена обязанность доказать получение разрешения?' if direct else
                    f'Какие основания статьи {article} освобождают от получения разрешения?')

        def select(p):
            f = next(f for f in p['evidence'] if f['text'].startswith('1. Обязанность'))
            return {'status': 'answer', 'answer': 'Обязанность доказать получение разрешения возложена на заявителя.',
                    'source_ids': [f['id']], 'requested_facts': [], 'reference_scope': scope}

        def check(p):
            result = {**verdict(p), 'answer_supported': supported}
            if required is not None:
                result['references_required'] = required
            return result

        model = ScriptedModel([select, check, select, check])
        with corpus(files) as r:
            result = answer_question(question, r, model)
        return result, model

    def test_direct_answer_with_unrelated_reference_keeps_answer_status(self):
        for article in (23, 48):
            (text, status), model = self.run_case(article=article)
            self.assertEqual(status, 'answer')
            self.assertTrue(text.startswith('Обязанность доказать'), text)
            self.assertIn('не найдены тексты отсылочных статей', text)
            self.assertIn(str(article), text)
            self.assertNotIn('Предоставьте эти статьи', text)
            self.assertEqual(len(model.calls), 2)

    def test_dependency_is_not_waived_without_explicit_independent_verification(self):
        for required in (True, None, 'false', 0):
            with self.subTest(required=required):
                (text, status), model = self.run_case(required=required)
                self.assertNotEqual(status, 'answer')
                self.assertIn('Предоставьте эти статьи', text)
                self.assertEqual(model.calls[2][1]['retry_reason'], 'source_references_required')

    def test_default_scope_preserves_existing_conservative_behavior(self):
        for scope in ('required', '', 'unrecognized'):
            (text, status), _ = self.run_case(scope=scope)
            self.assertEqual(status, 'partial')
            self.assertIn('Предоставьте эти статьи', text)

    def test_unsupported_model_text_cannot_establish_local_answer(self):
        (text, status), _ = self.run_case(supported=False)
        self.assertNotEqual(status, 'answer')
        self.assertIn('Предоставьте эти статьи', text)

    def test_question_that_needs_missing_ground_stays_partial(self):
        (text, status), _ = self.run_case(required=True, direct=False, article=57)
        self.assertEqual(status, 'partial')
        self.assertIn('57', text)
        self.assertIn('Предоставьте эти статьи', text)


if __name__ == '__main__':
    unittest.main()
