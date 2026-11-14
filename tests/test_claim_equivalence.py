"""Bounded paraphrases must preserve the relation, not just familiar words.

The two official answers are acceptance fixtures, not a quality benchmark.
All generalisation/negative cases use unrelated synthetic clauses. No model API.
"""
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
import csv
import io
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'prototype'), str(ROOT / 'tests')]
import solution
from psb_corpus import Fragment, load_corpus
from psb_policy import added_assertions_safe, answer_structured, scope_block_reason
from psb_retrieval import Retriever
from test_baseline import ScriptedModel


def source(text, name='Договор оборудования.txt', fid='s'):
    return Fragment(fid, name, 0, len(text), text, '')


class ClaimEquivalenceTests(unittest.TestCase):
    def test_inclusion_aspect_and_anaphoric_expenses(self):
        for items in ('упаковки и доставки', 'монтажа и страхования', 'погрузки и перевозки'):
            f = source(f'7.3. Цена оборудования указывается в спецификации и включает стоимость {items}.')
            for absence in ('Отдельная оплата этих расходов условиями пункта 7.3 не предусмотрена.',
                            'Отдельно их оплачивать не нужно.',
                            'Отдельная оплата этих расходов не требуется.'):
                for aspect in ('', 'уже '):
                    text = f'Цена оборудования, указанная в спецификации, {aspect}включает стоимость {items}. {absence}'
                    with self.subTest(text=text):
                        self.assertTrue(added_assertions_safe(text, [f]))

    def test_setting_predicate_preserves_actor_and_record(self):
        for subject, actor, instrument, record in (
            ('Срок службы', 'изготовитель', 'изготовителем', 'формуляре'),
            ('Период обслуживания', 'поставщик', 'поставщиком', 'паспорте'),
            ('Интервал поверки', 'производитель', 'производителем', 'сертификате'),
        ):
            for original, paraphrase in (('устанавливается', 'определяет'), ('определяется', 'устанавливает')):
                f = source(f'8.4. {subject} {original} {instrument} и указывается в {record}.')
                text = f'{subject} {paraphrase} {actor}, и он указывается в {record}.'
                with self.subTest(text=text):
                    self.assertTrue(added_assertions_safe(text, [f]))

    def test_setting_does_not_change_actor_object_record_or_polarity(self):
        f = source('8.4. Срок службы устанавливается изготовителем и указывается в формуляре.')
        for text in (
            'Срок службы определяет покупатель, и он указывается в формуляре.',
            'Стоимость ремонта определяет изготовитель, и она указывается в формуляре.',
            'Срок службы определяет изготовитель, и он указывается в накладной.',
            'Срок службы не определяет изготовитель, и он указывается в формуляре.',
            'Срок службы определяет изготовитель, и он не указывается в формуляре.',
        ):
            with self.subTest(text=text):
                self.assertFalse(added_assertions_safe(text, [f]))

    def test_actor_from_another_clause_cannot_set_the_parameter(self):
        f = source('8.4. Срок службы устанавливается изготовителем и указывается в формуляре поставщика.')
        wrong = 'Срок службы определяет поставщик, и он указывается в формуляре изготовителя.'
        self.assertFalse(added_assertions_safe(wrong, [f]))

    def test_optional_or_negative_setting_cannot_become_unconditional(self):
        text = 'Срок службы определяет изготовитель, и он указывается в формуляре.'
        for provision in (
            'Срок службы не устанавливается изготовителем и указывается в формуляре.',
            'Срок службы может устанавливаться изготовителем и указывается в формуляре.',
        ):
            with self.subTest(provision=provision):
                self.assertFalse(added_assertions_safe(text, [source(provision)]))

    def test_setting_equivalence_preserves_conditions(self):
        prefix = 'Срок службы устанавливается изготовителем и указывается в формуляре'
        condition = ', если оборудование обслуживается поставщиком'
        f = source(prefix + condition + '.')
        paraphrase = 'Срок службы определяет изготовитель, и он указывается в формуляре'
        self.assertTrue(added_assertions_safe(paraphrase + condition + '.', [f]))
        self.assertFalse(added_assertions_safe(paraphrase + '.', [f]))
        self.assertFalse(added_assertions_safe(paraphrase + condition.replace('если', 'если не') + '.', [f]))

    def test_aspect_does_not_erase_inclusion_conditions_or_modality(self):
        text = 'Цена, указанная в спецификации, уже включает стоимость погрузки.'
        for provision in (
            'Цена указывается в спецификации и не включает стоимость погрузки.',
            'Цена указывается в спецификации и может включать стоимость погрузки.',
            'Цена указывается в спецификации и будет включать стоимость погрузки.',
            'Цена указывается в спецификации и включает стоимость погрузки при наличии пропуска.',
        ):
            with self.subTest(provision=provision):
                self.assertFalse(added_assertions_safe(text, [source(provision)]))

    def test_payment_inference_cannot_add_an_expense_or_remove_a_charge(self):
        f = source('7.3. Цена оборудования указывается в спецификации и включает стоимость погрузки и перевозки.')
        for text in (
            'Цена оборудования, указанная в спецификации, уже включает стоимость ремонта. Отдельно его оплачивать не нужно.',
            'Цена оборудования включает стоимость погрузки и перевозки. Отдельная оплата ремонта не предусмотрена.',
            'Цена оборудования включает стоимость погрузки и перевозки. Никаких других платежей не требуется.',
            'Цена оборудования не включает стоимость погрузки и перевозки. Отдельная оплата этих расходов не требуется.',
            'Нет, цена оборудования, указанная в спецификации, включает стоимость погрузки и перевозки, поэтому отдельно их оплачивают.',
        ):
            with self.subTest(text=text):
                self.assertFalse(added_assertions_safe(text, [f]))

    def test_payment_inference_requires_unconditional_positive_inclusion(self):
        text = 'Цена включает стоимость погрузки. Отдельно её оплачивать не нужно.'
        for provision in (
            'Цена не включает стоимость погрузки.',
            'Цена может включать стоимость погрузки.',
            'Цена будет включать стоимость погрузки.',
            'Цена включает стоимость погрузки только при наличии пропуска.',
            'Цена включает стоимость погрузки, если оформлен пропуск.',
        ):
            with self.subTest(provision=provision):
                self.assertFalse(added_assertions_safe(text, [source(provision)]))

    def test_anaphora_cannot_jump_over_a_different_expense(self):
        f = source('Цена включает стоимость погрузки и перевозки.')
        text = ('Цена включает стоимость погрузки и перевозки. Обсуждались расходы на ремонт. '
                'Отдельная оплата этих расходов не требуется.')
        self.assertFalse(added_assertions_safe(text, [f]))

    def test_record_names_do_not_leak_between_documents(self):
        a = source('Цена оборудования указывается в спецификации и включает стоимость погрузки.',
                   'Договор Северный.txt', 'a')
        b = source('Цена ремонта указывается в смете.', 'Договор Южный.txt', 'b')
        text = 'По договору Южный цена оборудования, указанная в спецификации, уже включает стоимость погрузки.'
        self.assertFalse(added_assertions_safe(text, [a, b]))


class OfficialGuardReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs, fragments = load_corpus(ROOT / 'organizer/knowledge-base.zip')
        cls.retriever = Retriever(docs, fragments)
        def rows(name, field):
            with (ROOT / 'organizer' / name).open(encoding='utf-8-sig') as h:
                return {r['id']: r[field] for r in csv.DictReader(h)}
        cls.questions = rows('demo_questions.csv', 'question')
        cls.gold = rows('demo_output.csv', 'answer')
        # Remove exactly the source label, retaining the substantive sentence AFTER it in Q17.
        cls.texts = {
            '16': cls.gold['16'].replace(' Источник: договор № П-17/2024, п. 2.1.', ''),
            '17': cls.gold['17'].replace(' Источник: договор № ПТ-05/2023, п. 6.1.', ''),
        }
        cls.contracts = {'16': ('П-17-2024', '2.1.'), '17': ('ПТ-05-2023', '6.1.')}

    def response(self, qid, text=None):
        contract, clause = self.contracts[qid]
        def choose(payload):
            f = next(e for e in payload['evidence'] if contract in e['document'] and e['text'].startswith(clause))
            return {'status': 'answer' if qid == '16' else 'partial',
                    'answer': text or self.texts[qid], 'source_ids': [f['id']],
                    'requested_facts': [] if qid == '16' else ['warranty_document'], 'issue': ''}
        return choose

    def test_official_text_passes_guard_with_correct_sources(self):
        for qid, text in self.texts.items():
            with self.subTest(qid=qid):
                evidence = self.retriever.search(self.questions[qid])
                response = self.response(qid)({'evidence': self.retriever.evidence(evidence)})
                selected = [f for f in evidence if f.id in response['source_ids']]
                self.assertEqual(scope_block_reason(text, selected, self.retriever, self.questions[qid]), '')

    def test_official_text_survives_real_one_call_policy(self):
        for qid, text in self.texts.items():
            model = ScriptedModel([self.response(qid)] * 5)
            with self.subTest(qid=qid), redirect_stderr(io.StringIO()):
                result = answer_structured(self.questions[qid], self.retriever, model, verify=False)
                self.assertTrue(result['text'].startswith(text), result['text'])
                self.assertFalse(result['quote_only'])
                for f in result['sources']:
                    self.assertEqual(f.text, self.retriever.documents[f.document].text[f.start:f.end])

    def test_real_batch_preserves_both_complete_answers(self):
        owner = self
        ids = ['16', '17']
        class FixtureClient:
            def __init__(self, deadline, position=None):
                self.position = position
            def complete(self, system, payload):
                return owner.response(ids[self.position])(payload)
        with patch.object(solution, 'ProxyClient', FixtureClient), redirect_stderr(io.StringIO()):
            checkpoints = list(solution.run_questions(
                [(qid, self.questions[qid]) for qid in ids], self.retriever, time.monotonic() + 30, 2, 6))
        latest = {index: text for index, text, _ in checkpoints}
        self.assertEqual(set(latest), {0, 1})
        for index, qid in enumerate(ids):
            self.assertTrue(latest[index].startswith(self.texts[qid]), latest[index])

    def test_invented_term_does_not_pass_full_policy(self):
        bad = 'Гарантийный срок составляет 93 месяца и указывается в гарантийном талоне.'
        model = ScriptedModel([self.response('17', bad)] * 5)
        with redirect_stderr(io.StringIO()):
            result = answer_structured(self.questions['17'], self.retriever, model, verify=False)
        self.assertNotIn('93 месяца', result['text'])


if __name__ == '__main__':
    unittest.main()
