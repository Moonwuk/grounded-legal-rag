"""Every additionally printed provision must appear in citations and source cards."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment
from psb_policy import render


def fragment(fid, document, text):
    return Fragment(fid, document, 0, len(text), text, '')


class PublishedContextCitationsTests(unittest.TestCase):
    def run_render(self, context, prose='Проверка занимает 7 рабочих дней (п. 8.2).', selected=None):
        main = fragment('main', 'Договор.txt', '8.2. Проверка занимает 7 рабочих дней с даты приёмки.')
        extra = fragment('unused', 'Договор.txt', '9.5. Размер штрафа составляет 100 рублей.')
        evidence = [main, extra]
        candidate = {'status': 'answer', 'claims': [{'text': main.text, 'sources': [
            {'fragment_id': x.id, 'quote': x.text} for x in (selected or [main])]}]}
        published = []
        text = render(candidate, evidence, prose=prose, context_sources=context,
                      published_sources=published)
        return text, published

    def test_printed_clause_in_same_document_is_referenced(self):
        f = fragment('ctx', 'Договор.txt', '7.4. Датой приёмки считается подписание акта.')
        text, sources = self.run_render([f])
        self.assertIn('Источник: Договор, п. 8.2, 7.4.', text)
        self.assertIn(f, sources)
        self.assertEqual(len([x for x in sources if x.id == f.id]), 1)

    def test_printed_context_keeps_its_own_document(self):
        f = fragment('ctx', 'Положение.txt', '12.3. Датой приёмки считается подписание акта.')
        text, sources = self.run_render([f])
        self.assertIn('Источники: Договор, п. 8.2; Положение, п. 12.3.', text)
        self.assertIn(f, sources)

    def test_unnumbered_printed_context_keeps_its_document(self):
        f = fragment('ctx', 'Памятка.txt', 'Приёмка подтверждается подписанным актом.')
        text, sources = self.run_render([f])
        self.assertIn('Источники: Договор, п. 8.2; Памятка.', text)
        self.assertIn(f, sources)

    def test_unprinted_context_is_not_added_to_references(self):
        f = fragment('ctx', 'Памятка.txt', '8.2. Проверка занимает 7 рабочих дней.')
        text, sources = self.run_render([f])
        self.assertNotIn('Памятка', text)
        self.assertNotIn(f, sources)

    def test_unrelated_selected_clause_is_not_added_to_source_line(self):
        main = fragment('main', 'Договор.txt', '8.2. Проверка занимает 7 рабочих дней с даты приёмки.')
        unused = fragment('unused', 'Договор.txt', '9.5. Размер штрафа составляет 100 рублей.')
        f = fragment('ctx', 'Договор.txt', '7.4. Датой приёмки считается подписание акта.')
        text, _ = self.run_render([f], selected=[main, unused])
        self.assertIn('Источник: Договор, п. 8.2, 7.4.', text)
        self.assertNotIn('9.5', text)


if __name__ == '__main__':
    unittest.main()
