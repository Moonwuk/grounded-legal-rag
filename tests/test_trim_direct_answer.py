"""A standalone yes/no lead does not make the actual answer disposable."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import without_blocked_sentence
from test_one_call_answers import one_call
from test_prose_answers import select

SOURCE = ('Порядок проверки закупок\n'
          'Проверяются поставщик и изготовитель. '
          'Заказы без заключения отдела закупок к исполнению не допускаются.')
FILES = {'Порядок проверки.txt': SOURCE}
CONDITION = 'Заказы без заключения отдела закупок к исполнению не допускаются.'
DIRECT = ('Проверяются поставщик и изготовитель, а заказы без заключения '
          'отдела закупок к исполнению не допускаются.')
BAD = 'Только главный бухгалтер проверяет изготовителя.'


class TrimDirectAnswerTests(unittest.TestCase):
    def test_checklist_after_bare_no_survives_as_source_when_prose_is_rejected(self):
        draft = ('Нет. Проверки только поставщика недостаточно: проверяются '
                 'поставщик и изготовитель. ' + CONDITION)
        result, model, _ = one_call(
            'Достаточно проверить поставщика или проверяется кто-то ещё?',
            [select('Проверяются поставщик', draft)] * 2, FILES)
        self.assertEqual(result['status'], 'answer')
        self.assertIn('поставщик и изготовитель', result['text'])
        self.assertTrue(result['quote_only'])
        self.assertLessEqual(len(model.calls), 2)

    def test_unsupported_first_substantive_assertion_is_not_approved(self):
        for lead in ('Да.', 'Нет.'):
            with self.subTest(lead=lead):
                draft = lead + ' ' + BAD + ' ' + CONDITION
                result, _, _ = one_call('Главный бухгалтер проверяет изготовителя?',
                                       [select('Проверяются поставщик', draft)] * 2, FILES)
                self.assertNotIn('Только главный бухгалтер', result['text'])
                self.assertTrue(result['quote_only'])
                self.assertFalse(result['text'].startswith(lead))

    def test_a_later_bad_aside_can_still_be_trimmed_after_the_real_answer(self):
        draft = 'Да. ' + DIRECT + ' ' + BAD
        result, model, _ = one_call('Нужны проверка поставщика и заключение отдела?',
                                   [select('Проверяются поставщик', draft)], FILES)
        self.assertTrue(result['text'].startswith('Да. ' + DIRECT), result['text'])
        self.assertNotIn(BAD, result['text'])
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 1)

    def test_first_explanation_can_be_replaced_by_its_exact_cited_source(self):
        clause = '2.2. Заявка согласуется с финансовым отделом.'
        direct = ('Заявку подаёт руководитель вашего отдела: её подаёт руководитель '
                  'отдела, которому нужен товар (п. 1.4).')
        files = {'Порядок закупок.txt':
                 'ПОРЯДОК ЗАКУПОК\n'
                 '1.4. Заявку на закупку подаёт руководитель отдела, которому нужен товар.\n'
                 + clause}
        draft = ('Нет. Финансовый отдел заявку согласует, но не инициирует закупку '
                 '(п. 2.2). ' + direct)

        def select_both(payload):
            return {'status': 'answer', 'answer': draft,
                    'source_ids': [f['id'] for f in payload['evidence']
                                   if f['text'].startswith(('1.4.', '2.2.'))]}

        result, model, _ = one_call(
            'Финансовый отдел должен подать заявку на закупку или руководитель нашего отдела?',
            [select_both], files)
        self.assertTrue(result['text'].startswith('Нет. ' + direct), result['text'])
        self.assertNotIn('не инициирует', result['text'])
        self.assertIn('«' + clause + '»', result['text'])
        self.assertEqual(result['status'], 'answer')
        self.assertFalse(result['quote_only'])
        self.assertEqual(len(model.calls), 1)

    def test_ordinary_first_sentence_keeps_existing_protection(self):
        selected = [Fragment('f', 'Порядок', 0, len(SOURCE), SOURCE, '')]
        retriever = SimpleNamespace(documents={})
        self.assertEqual(without_blocked_sentence(DIRECT + ' ' + BAD, selected, retriever), DIRECT)
        self.assertEqual(without_blocked_sentence(BAD + ' ' + DIRECT, selected, retriever),
                         BAD + ' ' + DIRECT)


if __name__ == '__main__':
    unittest.main()
