"""Discarding an unsupported clause must not erase its selected source wording."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from test_one_call_answers import one_call


FILES = {'Порядок закупок.txt': 'ПОРЯДОК ЗАКУПОК\n'
         '1.4. Заявку на закупку подаёт руководитель отдела, которому нужен товар.\n'
         '2.2. Заявка согласуется с финансовым отделом.\n'
         '8.7. Заявки хранятся в архиве пять лет.\n'}
FIRST = 'Заявку на закупку подаёт руководитель вашего отдела, которому нужен товар (п. 1.4).'
SECOND = ' Финансовый отдел заявку согласует, но не инициирует закупку (п. 2.2).'


def generated(text, clauses=('1.4.', '2.2.')):
    def response(payload):
        ids = [f['id'] for f in payload['evidence'] if f['text'].startswith(clauses)]
        return {'status': 'answer', 'answer': text, 'source_ids': ids,
                'requested_facts': [], 'issue': ''}
    return response


class TrimmedSentenceEvidenceTests(unittest.TestCase):
    def test_rejected_negation_keeps_the_selected_positive_role(self):
        result, model, _ = one_call('Кто подаёт заявку — финансовый отдел или руководитель?',
                                   [generated(FIRST + SECOND)], FILES)
        self.assertEqual(len(model.calls), 1)
        self.assertTrue(result['text'].startswith(FIRST))
        self.assertNotIn('не инициирует', result['text'])
        self.assertIn('«2.2. Заявка согласуется с финансовым отделом.»', result['text'])
        self.assertIn('п. 1.4, 2.2.', result['text'])
        self.assertNotIn('8.7.', result['text'])

    def test_uncited_selected_provision_is_not_added(self):
        result, _, _ = one_call('Кто подаёт заявку?',
                                [generated(FIRST + SECOND, ('1.4.', '2.2.', '8.7.'))], FILES)
        self.assertNotIn('8.7.', result['text'])
        self.assertIn('«2.2.', result['text'])

    def test_unselected_clause_is_not_borrowed_from_retrieval(self):
        result, _, _ = one_call('Кто подаёт заявку?',
                                [generated(FIRST + SECOND, ('1.4.',))], FILES)
        self.assertNotIn('2.2.', result['text'])
        self.assertNotIn('не инициирует', result['text'])

    def test_already_explained_clause_is_not_quoted_twice(self):
        first = FIRST + ' Заявка согласуется с финансовым отделом (п. 2.2).'
        result, _, _ = one_call('Кто подаёт заявку?', [generated(first + SECOND)], FILES)
        self.assertNotIn('«2.2.', result['text'])
        self.assertNotIn('не инициирует', result['text'])
        self.assertIn('Заявка согласуется с финансовым отделом (п. 2.2).', result['text'])


if __name__ == '__main__':
    unittest.main()
