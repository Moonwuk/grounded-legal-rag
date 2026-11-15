"""A bounded repair remembers alternating omissions only while sources support them."""
from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_policy import answer_structured, restrictions_kept
from test_audit_fixes import corpus
from test_baseline import ScriptedModel


OLD = ('5.2. Возврат разрешается при наличии квитанции, '
       'за исключением товаров, изготовленных по заказу.')
NEW = ('5.3. Возврат товара со скрытым браком разрешается при условии уведомления продавца, '
       'за исключением товара, повреждённого покупателем.')
SIMPLE = '5.4. Возврат разрешается при условии уведомления продавца.'
FILES = {'Порядок возврата.txt': 'Порядок возврата\n' + '\n'.join((OLD, NEW, SIMPLE))}
QUESTION = 'Когда разрешается возврат?'


def select(clause, text):
    def generate(payload):
        source = next(f for f in payload['evidence'] if f['text'].startswith(clause))
        return {'status': 'answer', 'answer': text, 'source_ids': [source['id']],
                'requested_facts': [], 'issue': ''}
    return generate


def run(responses):
    model = ScriptedModel(responses)
    with corpus(FILES) as retriever, redirect_stderr(io.StringIO()):
        result = answer_structured(QUESTION, retriever, model, verify=False, repair_quotes=True)
    return result, model


class RetryRestrictionMemoryTests(unittest.TestCase):
    def test_alternating_omissions_are_both_reminded_in_the_existing_third_attempt(self):
        first = 'Возврат разрешается при наличии квитанции.'
        second = 'Возврат разрешается, за исключением товаров, изготовленных по заказу.'
        final = OLD.removeprefix('5.2. ')
        def repair(payload):
            self.assertEqual(set(payload['retry_restrictions']), {'при наличии', 'за исключением'})
            return select('5.2.', final)(payload)
        result, model = run([select('5.2.', first), select('5.2.', second), repair])
        self.assertEqual(len(model.calls), 3)
        self.assertNotIn('retry_restrictions', model.calls[0][1])
        self.assertEqual(model.calls[1][1]['retry_restrictions'], ['за исключением'])
        self.assertTrue(model.calls[2][1]['final_text_repair'])
        self.assertFalse(result['quote_only'], result['text'])
        self.assertTrue(result['text'].startswith(final), result['text'])

    def test_a_restriction_absent_from_the_current_selected_source_is_forgotten(self):
        final = SIMPLE.removeprefix('5.4. ')
        def repair(payload):
            self.assertEqual(payload['retry_restrictions'], ['при условии'])
            return select('5.4.', final)(payload)
        result, model = run([
            select('5.2.', 'Возврат разрешается при наличии квитанции.'),
            select('5.4.', 'Возврат разрешается.'), repair])
        self.assertEqual(len(model.calls), 3)
        self.assertFalse(result['quote_only'])
        self.assertTrue(result['text'].startswith(final))
        self.assertNotIn('за исключением', model.calls[2][1]['retry_restrictions'])

    def test_remembered_class_uses_the_current_source_wording(self):
        def repair(payload):
            self.assertEqual(set(payload['retry_restrictions']), {'при условии', 'за исключением'})
            self.assertNotIn('при наличии', payload['retry_restrictions'])
            return select('5.3.', NEW.removeprefix('5.3. '))(payload)
        result, model = run([
            select('5.2.', 'Возврат разрешается, за исключением товаров, изготовленных по заказу.'),
            select('5.3.', 'Возврат товара со скрытым браком разрешается при условии уведомления продавца.'),
            repair])
        self.assertEqual(model.calls[1][1]['retry_restrictions'], ['при наличии'])
        self.assertEqual(len(model.calls), 3)
        self.assertFalse(result['quote_only'])

    def test_reminders_cannot_approve_an_omission_or_add_another_call(self):
        first = 'Возврат разрешается при наличии квитанции.'
        second = 'Возврат разрешается, за исключением товаров, изготовленных по заказу.'
        result, model = run([select('5.2.', first), select('5.2.', second), select('5.2.', first)])
        self.assertEqual(len(model.calls), 3)
        self.assertTrue(result['quote_only'])
        self.assertIn('«' + OLD + '»', result['text'])
        with corpus(FILES) as retriever:
            sources = [f for f in retriever.search(QUESTION) if f.text.startswith('5.2.')]
            self.assertFalse(restrictions_kept(first, sources, question=QUESTION))
            self.assertFalse(restrictions_kept(second, sources, question=QUESTION))

    def test_remembered_restrictions_do_not_cross_question_boundaries(self):
        run([select('5.2.', 'Возврат разрешается при наличии квитанции.'),
             select('5.2.', 'Возврат разрешается, за исключением товаров, изготовленных по заказу.'),
             select('5.2.', OLD.removeprefix('5.2. '))])
        result, model = run([select('5.4.', 'Возврат разрешается.'),
                             select('5.4.', SIMPLE.removeprefix('5.4. '))])
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(model.calls[1][1]['retry_restrictions'], ['при условии'])
        self.assertFalse(result['quote_only'])


if __name__ == '__main__':
    unittest.main()
