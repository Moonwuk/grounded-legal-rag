"""Preserve a sourced positive role without publishing its unsupported denial."""
from pathlib import Path
import re
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from test_one_call_answers import one_call


FIRST = ('Заявку на закупку подаёт руководитель подразделения, которому требуется оборудование '
         '(п. 1.5).')
POSITIVE = ('Финансовый отдел согласует заявку на закупку вместе с начальником склада (п. 3.6).')
DRAFT = FIRST + ' Финансовый отдел не инициирует закупку, а согласует заявку на закупку вместе с начальником склада (п. 3.6).'
SOURCE = '3.6. Заявка на закупку согласуется с финансовым отделом и начальником склада.'


def files(source=SOURCE):
    return {'Положение о закупках.txt': 'ПОЛОЖЕНИЕ О ЗАКУПКАХ\n'
            '1.5. Заявку на закупку подаёт руководитель подразделения, которому требуется оборудование.\n'
            + source + '\n'}


def generated(text, clauses=('1.5.', '3.6.')):
    def response(payload):
        ids = [f['id'] for f in payload['evidence'] if f['text'].startswith(clauses)]
        return {'status': 'answer', 'answer': text, 'source_ids': ids, 'requested_facts': [], 'issue': ''}
    return response


def run_role(text=DRAFT, source=SOURCE, clauses=('1.5.', '3.6.'), documents=None):
    return one_call('Кто инициирует закупку — финансовый отдел или руководитель подразделения?',
                    [generated(text, clauses), generated(text, clauses)], documents or files(source))


class PreservedPositiveRoleTests(unittest.TestCase):
    def test_positive_role_is_kept_without_the_unsupported_denial(self):
        result, model, events = run_role()
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(result['status'], 'answer')
        self.assertIn(FIRST + ' ' + POSITIVE, result['text'])
        self.assertNotIn('не инициирует', result['text'])
        self.assertNotIn('«3.6.', result['text'])
        self.assertIn('п. 1.5, 3.6.', result['text'])
        self.assertEqual(events[-1]['prose'], 'published')

    def test_single_approving_role_does_not_require_a_coactor(self):
        source = '3.6. Заявка на закупку согласуется с финансовым отделом.'
        result, _, _ = run_role(DRAFT.replace(' вместе с начальником склада', ''), source=source)
        self.assertIn('Финансовый отдел согласует заявку на закупку (п. 3.6).', result['text'])
        self.assertNotIn('не инициирует', result['text'])

    def test_invented_actor_action_or_object_does_not_survive(self):
        for positive in ('Юридический отдел согласует заявку на закупку вместе с начальником склада',
                         'Финансовый отдел утверждает заявку на закупку вместе с начальником склада',
                         'Финансовый отдел согласует главного бухгалтера',
                         'Руководитель подразделения согласует финансовый отдел',
                         'Финансовый отдел согласует продажу оборудования вместе с начальником склада'):
            # Split at the positive predicate, retaining its own subject.
            match = re.match(r'(.+?) (согласует|утверждает) (.+)', positive)
            draft = FIRST + f' {match[1]} не инициирует закупку, а {match[2]} {match[3]} (п. 3.6).'
            with self.subTest(positive=positive):
                result, _, _ = run_role(draft)
                self.assertNotIn(positive, result['text'])
                self.assertNotIn('не инициирует', result['text'])

    def test_source_conditions_prohibitions_and_split_facts_are_not_lost(self):
        for source in ('3.6. Заявка на закупку согласуется с финансовым отделом и начальником склада только при письменном разрешении директора.',
                       '3.6. Заявка на закупку не согласуется с финансовым отделом и начальником склада.',
                       '3.6. Заявка на закупку может согласовываться с финансовым отделом и начальником склада.',
                       '3.6. Заявка на закупку согласуется с финансовым отделом или начальником склада.',
                       '3.6. Заявка на закупку согласуется с финансовым отделом и начальником склада и директором.',
                       '3.6. Заявка на закупку согласуется с финансовым отделом. График согласуется с начальником склада.',
                       '3.6. Заявка на закупку согласуется с финансовым отделом.\n3.7. График согласуется с начальником склада.',
                       '3.6. Заявка на закупку согласуется с финансовым отделом и начальником склада, кроме срочных закупок.'):
            with self.subTest(source=source):
                result, _, _ = run_role(source=source, clauses=('1.5.', '3.6.', '3.7.'))
                self.assertNotIn(POSITIVE, result['text'])
                self.assertIn('«3.6.', result['text'])
        result, _, _ = run_role(DRAFT.replace(' вместе с начальником склада', ''))
        self.assertNotIn('Финансовый отдел согласует заявку на закупку (п. 3.6).', result['text'])

    def test_missing_or_ambiguous_selected_source_is_not_borrowed(self):
        result, _, _ = run_role(clauses=('1.5.',))
        self.assertNotIn(POSITIVE, result['text'])
        self.assertNotIn('3.6.', result['text'])
        documents = files()
        documents['Другой порядок закупок.txt'] = 'ДРУГОЙ ПОРЯДОК ЗАКУПОК\n' + SOURCE + '\n'
        result, _, _ = run_role(documents=documents)
        self.assertNotIn(POSITIVE, result['text'])

    def test_permissions_and_contrast_restrictions_are_not_promoted(self):
        for second in ('Финансовый отдел не обязан согласовывать заявку, а может согласовать её (п. 3.6).',
                       'Финансовый отдел согласует заявку, но не без письменного разрешения директора (п. 3.6).',
                       'Финансовый отдел согласует заявку, но не для срочной закупки (п. 3.6).'):
            result, _, _ = run_role(FIRST + ' ' + second)
            self.assertNotIn(POSITIVE, result['text'])
            self.assertNotIn('Финансовый отдел согласует заявку (п. 3.6).', result['text'])


if __name__ == '__main__':
    unittest.main()
