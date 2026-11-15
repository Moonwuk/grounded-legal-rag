"""Keep the strict exception guard; repair wording with source-owned operators."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Fragment
from psb_policy import SYSTEM, RESTRICTION_RETRY_GUIDANCE, lost_restrictions, restrictions_kept
from test_one_call_answers import answer, one_call


SOURCE = ('3.7. Ставка сбора 7 процентов применяется при реализации печатных изданий, '
          'за исключением рекламных каталогов.')
SELECTED = [Fragment('source', 'Правила сбора.txt', 0, len(SOURCE), SOURCE, '3.7.')]


class PassiveExclusionTests(unittest.TestCase):
    def test_unrecognised_passive_forms_keep_the_existing_exception_barrier(self):
        for text in (
                'Из перечня исключены рекламные каталоги.',
                'Рекламный каталог исключён из перечня.',
                'Рекламная продукция исключена из перечня.',
                'Рекламное издание исключено из перечня.',
                'Рекламные каталоги исключены из перечня.',
                'Нет, рекламные каталоги исключены из перечня.',
                'Льгота распространяется на издания, но не на любые: исключены рекламные каталоги.',
                'Ставка применяется при реализации изданий, но не каждого: из перечня исключены рекламные каталоги.'):
            with self.subTest(text=text):
                self.assertFalse(restrictions_kept(text, SELECTED))
                self.assertFalse(restrictions_kept(text, SELECTED, strict=True))
                self.assertIn('за исключением', lost_restrictions(text, SELECTED))

    def test_nonassertive_passives_do_not_satisfy_the_exception(self):
        for text in (
                'Рекламные каталоги не исключены.',
                'Рекламные каталоги не были исключены.',
                'Рекламные каталоги исключены не всегда.',
                'Рекламные каталоги исключены не все.',
                'Рекламные каталоги исключены — это не так.',
                'Рекламные каталоги были исключены.',
                'Рекламные каталоги будут исключены.',
                'Рекламные каталоги могут быть исключены.',
                'Следует исключить рекламные каталоги.',
                'Если рекламные каталоги исключены, ставка применяется.',
                'Если получено разрешение, то рекламные каталоги исключены.',
                'При условии согласования рекламные каталоги исключены.',
                'Рекламные каталоги исключены при согласовании с инспекцией.',
                'Рекламные каталоги исключены в случае согласования с инспекцией.',
                'Рекламные каталоги исключены, пока действует разрешение.',
                'В случае согласования с инспекцией: исключены рекламные каталоги.',
                'Рекламные каталоги исключены ли из перечня?',
                'Исключены ли рекламные каталоги',
                'Рекламные каталоги исключены?',
                'Нельзя утверждать: исключены рекламные каталоги.',
                'Не подтверждено: исключены рекламные каталоги.',
                'Не доказано, что рекламные каталоги исключены.',
                'Не следует утверждать: исключены рекламные каталоги.',
                'Неверно, что рекламные каталоги исключены.',
                'Ложно, что рекламные каталоги исключены.',
                'Неправильно считать, что рекламные каталоги исключены.',
                'Ошибочно считать, что рекламные каталоги исключены.',
                'Возможно, рекламные каталоги исключены.',
                'Предположим: исключены рекламные каталоги.',
                'Рекламные каталоги якобы исключены.',
                'Не исключено, что рекламные каталоги исключены.',
                'Сомнительно, что рекламные каталоги исключены.',
                'Надеемся, что рекламные каталоги исключены.',
                'Текст «исключены рекламные каталоги» требуется проверить.',
                'Фраза “исключены рекламные каталоги” требует проверки.',
                "Фраза 'исключены рекламные каталоги' требует проверки.",
                'Фраза ‘исключены рекламные каталоги’ требует проверки.',
                'Фраза „исключены рекламные каталоги“ требует проверки.',
                'Фраза `исключены рекламные каталоги` требует проверки.',
                'Проверь фразу "исключены рекламные каталоги".'):
            with self.subTest(text=text):
                self.assertFalse(restrictions_kept(text, SELECTED))
                self.assertIn('за исключением', lost_restrictions(text, SELECTED))

    def test_retry_requests_literal_source_operators_without_changing_the_first_request_or_guards(self):
        files = {'Правила сбора.txt': 'Правила сбора\n' + SOURCE}
        paraphrase = ('Нет. Ставка сбора 7 процентов применяется при реализации печатных изданий, '
                'но не любых: из перечня исключены рекламные каталоги (п. 3.7).')
        good = ('Нет. Ставка сбора 7 процентов применяется при реализации печатных изданий, '
                'за исключением рекламных каталогов (п. 3.7).')
        result, model, _ = one_call('Ставка сбора применяется к любому печатному изданию?',
                                   [answer('3.7.', paraphrase), answer('3.7.', good)], files)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[0][0], SYSTEM)
        self.assertNotIn('retry_restrictions', model.calls[0][1])
        self.assertIn(RESTRICTION_RETRY_GUIDANCE, model.calls[1][0])
        self.assertEqual(model.calls[1][1]['retry_restrictions'], ['за исключением'])
        self.assertEqual(result['status'], 'answer')
        self.assertFalse(result['quote_only'])
        self.assertTrue(result['text'].startswith(good), result['text'])
        bad_number = good.replace('7 процентов', '31 процент')
        result, model, _ = one_call('Ставка сбора применяется к любому печатному изданию?',
                                   [answer('3.7.', bad_number)] * 2, files)
        self.assertTrue(result['quote_only'])
        self.assertNotIn('31 процент', result['text'])
        self.assertEqual(len(model.calls), 2)


if __name__ == '__main__':
    unittest.main()
