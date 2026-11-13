"""«Дополнительное соглашение» is a document type, not «other requirements».

Run of the 24-question regression on 06a3dda, questions N24 and N14: the model
answered that the base holds no supplementary agreement to the lease (N24) or
that a deadline would need a separate document such as a supplementary
agreement, «которого в базе нет» (N14). The verifier confirmed both texts.
The barrier against unsupported «no other requirements» additions matched
«дополнительного соглашения … нет», rejected the text and only a generic
refusal or bare quotations were published.

Whether the base holds such an agreement is checked separately against the
corpus (false_absence); the barrier must still reject an added absence of
other requirements, payments or conditions.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import added_assertions_safe, false_absence, prose_scope_safe, scope_block_reason  # noqa: E402

RENT = [Fragment('r', 'Договор аренды Б-11-2031 Вектор.txt', 0, 120,
                 '2.1. Арендная плата составляет 310 000 (триста десять тысяч) рублей в месяц, включая НДС.', '')]
DEPOSIT = [Fragment('d', 'Договор аренды Б-11-2031 Вектор.txt', 0, 120,
                    '2.4. При подписании договора Арендатор вносит гарантийный взнос в размере двух месячных платежей.', '')]


class SupplementaryAgreementAbsenceTests(unittest.TestCase):
    def test_absent_agreement_is_not_an_added_requirement(self):
        for text in (
                'В базе нет дополнительного соглашения к договору аренды Б-11/2031, поэтому назвать его дату и номер '
                'по документам нельзя. Договором арендная плата установлена в размере 310 000 рублей в месяц (п. 2.1).',
                'Сведений о дополнительных соглашениях к договору Б-11/2031 в базе нет; по п. 2.1 плата — 310 000 рублей.',
                'Допсоглашение об изменении арендной платы в документах отсутствует; плата по договору — 310 000 рублей.'):
            with self.subTest(text):
                self.assertTrue(added_assertions_safe(text, RENT))
                self.assertTrue(prose_scope_safe(text, RENT))

    def test_document_needed_for_a_missing_term(self):
        text = ('Срок возврата гарантийного взноса договором Б-11/2031 не назван: п. 2.4 говорит о его внесении. '
                'Для ответа нужен документ, устанавливающий срок (например, дополнительное соглашение), которого в базе нет.')
        self.assertTrue(prose_scope_safe(text, DEPOSIT))

    def test_added_absence_of_other_terms_is_still_rejected(self):
        for text in ('Арендная плата составляет 310 000 рублей; дополнительных платежей нет.',
                     'Плата — 310 000 рублей, иных требований к арендатору договор не предусматривает.',
                     'Плата — 310 000 рублей; дополнительное согласование не требуется.',
                     'Других условий об оплате в договоре нет, плата — 310 000 рублей.'):
            with self.subTest(text):
                self.assertFalse(added_assertions_safe(text, RENT))


class Document:
    def __init__(self, text):
        self.text = text


class Base:
    """A contract with a supplementary agreement and one without."""
    doc_ids = {'contract-v': {'в-3/2032'}, 'supplement-v': {'в-3/2032'}, 'contract-k': {'к-9/2032'}}
    documents = {'contract-v': Document('ДОГОВОР ПОДРЯДА № В-3/2032\n1. Предмет договора'),
                 'supplement-v': Document('ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 2\nк договору подряда № В-3/2032'),
                 'contract-k': Document('ДОГОВОР ХРАНЕНИЯ № К-9/2032\n1. Предмет договора')}


class FalseSupplementAbsenceTests(unittest.TestCase):
    def test_denying_an_existing_agreement_is_caught(self):
        for text in ('В базе нет дополнительного соглашения к договору В-3/2032.',
                     'Дополнительного соглашения № 2 к договору подряда В-3/2032 в базе нет.',
                     'Допсоглашение к договору № В-3/2032 в документах отсутствует.'):
            with self.subTest(text):
                self.assertTrue(false_absence(text, Base()))

    def test_true_or_qualified_absence_is_left_to_the_verifier(self):
        for text in ('В базе нет дополнительного соглашения к договору К-9/2032, поэтому назвать его дату нельзя.',
                     'В базе нет допсоглашения к договору В-3/2032, которым изменена цена работ.',
                     'Дополнительного соглашения к договору В-3/2032 о продлении срока в базе нет.',
                     'По дополнительному соглашению к договору В-3/2032 срок изменён; иных изменений нет.'):
            with self.subTest(text):
                self.assertFalse(false_absence(text, Base()))



APPROVAL = [Fragment('a', 'Регламент закупок ред 2031.txt', 0, 120,
                     '3.4. Закупки на сумму свыше 800 000 рублей дополнительно согласуются с директором по безопасности.', '')]


class FinalRunGuardTests(unittest.TestCase):
    """Final 24-question run of 13 November: verified texts rejected by the barrier."""

    def test_named_supplementary_agreement_with_number(self):
        # «Дополнительного соглашения к договору аренды № …»: the numbered-document
        # reference was cut out and the orphaned «Дополнительного» read as «other».
        text = ('Дополнительного соглашения к договору аренды № Б-11/2031 об изменении арендной платы в базе нет. '
                'По договору плата составляет 310 000 рублей в месяц (п. 2.1).')
        self.assertTrue(added_assertions_safe(text, RENT))
        self.assertEqual(scope_block_reason(text, RENT, None), '')

    def test_source_wording_with_its_object_is_not_an_addition(self):
        for text in ('Нет. Директор по безопасности дополнительно согласует закупки свыше 800 000 рублей (п. 3.4), '
                     'поэтому закупка на 500 000 рублей его согласования не требует.',
                     'Нет: с директором по безопасности дополнительно согласуются закупки свыше 800 000 рублей, '
                     'а 500 000 рублей ниже порога, поэтому его согласование не нужно.'):
            with self.subTest(text):
                self.assertTrue(added_assertions_safe(text, APPROVAL))

    def test_other_absence_beside_source_wording_is_still_rejected(self):
        for text in ('Закупки свыше 800 000 рублей дополнительно согласуются, а дополнительно согласовывать что-либо ещё не нужно.',
                     'Дополнительно согласовывать ничего не требуется, если сумма до 800 000 рублей.',
                     'С директором по безопасности согласуются закупки свыше 800 000 рублей; иных согласований не требуется.'):
            with self.subTest(text):
                self.assertFalse(added_assertions_safe(text, APPROVAL))

    def test_exclusive_word_quoted_from_the_question(self):
        question = 'Закупка на 500 000 рублей. Нужен ли директор по безопасности только из-за суммы?'
        text = 'Нет, только из-за суммы директор по безопасности не нужен: порог — свыше 800 000 рублей (п. 3.4).'
        self.assertTrue(prose_scope_safe(text, APPROVAL, question=question))
        self.assertFalse(prose_scope_safe(text, APPROVAL))
        # The question's wording does not license another exclusive claim.
        self.assertFalse(prose_scope_safe('Согласовать нужно только с директором по безопасности (п. 3.4).',
                                          APPROVAL, question=question))


if __name__ == '__main__':
    unittest.main()
