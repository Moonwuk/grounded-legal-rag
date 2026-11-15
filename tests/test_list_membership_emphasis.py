"""A pure copular list membership does not restrict how many actors may act."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import SYSTEM, EXCLUSIVE_RETRY_GUIDANCE, prose_scope_safe
from test_one_call_answers import answer, one_call


SOURCE = ('3.1. Чек-лист проверки: 1. Проверка банка партнёра. '
          '2. Проверка страны регистрации. 3. Проверка стоимости поставки.')
SELECTED = [Fragment('list', 'Порядок проверки.txt', 0, len(SOURCE), SOURCE, '3.1.')]


class ListMembershipEmphasisTests(unittest.TestCase):
    def test_pure_copula_keeps_source_backed_membership(self):
        for text in (
                'Банк партнёра — лишь один из них.',
                'Банк партнёра является лишь одним из них.',
                'Проверка страны регистрации — лишь одна из них.',
                'Проверка стоимости поставки является лишь одной из них.'):
            with self.subTest(text=text):
                self.assertTrue(prose_scope_safe(text, SELECTED))

    def test_count_restrictions_negation_questions_and_unknown_subjects_are_not_membership(self):
        for text in (
                'Лишь один из подписантов может подписать договор.',
                'Банк проверяет лишь одного из них.',
                'Банк партнёра не является лишь одним из них.',
                'Банк партнёра — не лишь один из них.',
                'Банк партнёра — лишь один из них?',
                'Если банк партнёра — лишь один из них.',
                'Если есть разрешение, банк партнёра — лишь один из них.',
                'Возможно, банк партнёра является лишь одним из них.',
                'Гарантия партнёра — лишь одна из них.',
                'Банк контрабанды — лишь один из них.',
                'Банк партнёра — лишь один из них, который может подписать договор.',
                'Банк партнёра — лишь один из них и имеет право на льготу.',
                'Банк партнёра — только один из них.',
                'Банк партнёра — лишь один из них. Договор подписывает только инспектор.'):
            with self.subTest(text=text):
                self.assertFalse(prose_scope_safe(text, SELECTED))

    def test_membership_requires_a_positive_explicit_list_not_an_incidental_mention(self):
        text = 'Банк партнёра — лишь один из них.'
        for source in (
                'Банк партнёра проверяется до заключения договора.',
                'Чек-лист проверки: 1. Проверка банка партнёра.',
                'Не проверяются: 1. Банк партнёра. 2. Страна регистрации.',
                'Чек-лист проверки: 1. Банк партнёра не проверяется. 2. Страна регистрации.',
                'Чек-лист проверки: 1. Проверка банка партнёра. 2. Уведомление банка партнёра.'):
            with self.subTest(source=source):
                selected = [Fragment('list', 'Порядок.txt', 0, len(source), source, '')]
                self.assertFalse(prose_scope_safe(text, selected))

    def test_source_subject_matching_does_not_confuse_counterparty_with_contraband(self):
        source = 'Чек-лист: 1. Проверка банка контрагента. 2. Проверка договора.'
        selected = [Fragment('list', 'Порядок.txt', 0, len(source), source, '')]
        self.assertTrue(prose_scope_safe('Банк контрагента — лишь один из них.', selected))
        self.assertFalse(prose_scope_safe('Банк контрабанды — лишь один из них.', selected))

    def test_complete_answer_keeps_the_membership_sentence_without_extra_generation(self):
        files = {'Порядок проверки.txt': 'Порядок проверки\n' + SOURCE}
        text = ('Чек-лист включает проверку банка партнёра, страны регистрации и стоимости поставки. '
                'Банк партнёра — лишь один из них.')
        result, model, _ = one_call('Что входит в чек-лист проверки?', [answer('3.1.', text)] * 2, files)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(result['status'], 'answer')
        self.assertFalse(result['quote_only'])
        self.assertTrue(result['text'].startswith(text), result['text'])

    def test_exclusive_retry_preserves_an_operator_the_first_answer_already_kept(self):
        source = ('5.1. До подписания договора с зарубежным поставщиком проверяются тарифные условия '
                  'и уполномоченные подписанты. Без подтверждения проверки подписание договора не допускается.')
        files = {'Порядок проверки.txt': 'Порядок проверки\n' + source}
        bad = ('Проверяются только тарифные условия и уполномоченные подписанты. '
               'Без подтверждения проверки подписание договора не допускается.')
        good = source.removeprefix('5.1. ')
        def retry(payload):
            self.assertEqual(payload['retry_policy_feedback']['scope_barrier'], 'exclusive_word')
            self.assertEqual(payload['retry_policy_feedback']['missing_restrictions'], [])
            self.assertEqual(payload['retry_preserve_restrictions'], ['не допускается'])
            return answer('5.1.', good)(payload)
        result, model, _ = one_call('Что проверяется до подписания договора?',
                                   [answer('5.1.', bad), retry], files)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[0][0], SYSTEM)
        self.assertNotIn('retry_preserve_restrictions', model.calls[0][1])
        self.assertIn(EXCLUSIVE_RETRY_GUIDANCE, model.calls[1][0])
        self.assertTrue(result['text'].startswith(good), result['text'])
        self.assertFalse(result['quote_only'])

    def test_other_retry_reasons_do_not_receive_exclusive_preservation_feedback(self):
        source = '5.1. Без подтверждения проверки подписание договора не допускается.'
        files = {'Порядок проверки.txt': 'Порядок проверки\n' + source}
        bad = 'Без подтверждения проверки подписание договора не допускается в течение 99 дней.'
        good = source.removeprefix('5.1. ')
        result, model, _ = one_call('Можно ли подписать договор без подтверждения проверки?',
                                   [answer('5.1.', bad), answer('5.1.', good)], files)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1][1]['retry_reason'], 'answer_numbers_not_in_sources')
        self.assertNotIn('retry_preserve_restrictions', model.calls[1][1])
        self.assertNotIn(EXCLUSIVE_RETRY_GUIDANCE, model.calls[1][0])
        self.assertNotIn('99', result['text'])


if __name__ == '__main__':
    unittest.main()
