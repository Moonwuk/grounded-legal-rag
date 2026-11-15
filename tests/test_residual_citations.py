"""Only source-confirmed neutral citations wrap a complete residual proposition."""
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'prototype'),
               str(Path(__file__).resolve().parent)]
from psb_corpus import Document, Fragment
from psb_policy import residual_conditions_kept, restrictions_kept
from test_residual_reference_scope import BAD, RULE, SOURCE


NAME = 'Учебный кодекс.txt'
HEADER = 'Источник: Статья 73. НК РФ\nСтатья 73. Ставки сбора\n'
DOC = Document(NAME, HEADER + SOURCE, '', ())
SELECTED = [Fragment('f', NAME, len(HEADER), len(DOC.text), SOURCE, '5.')]
DOCS = {NAME: DOC}
POSITIVE = (
    RULE[:-1] + ' (п. 5 ст. 73).',
    RULE[:-1] + ' (п. 5 ст. 73 НК РФ).',
    'По пункту 5 статьи 73 НК РФ ' + RULE.lower(),
    'Пункт 5 статьи 73 НК РФ устанавливает: «' + RULE[:-1] + '».',
)
APPLICABILITY = ('Пункт 5 статьи 73 НК РФ применяется к случаям, '
                 'не указанным в пунктах 3, 6 и 8 настоящей статьи.')


class ResidualCitationTests(unittest.TestCase):
    def test_closed_applicability_preserves_the_same_source_owned_negative_group(self):
        self.assertTrue(residual_conditions_kept(APPLICABILITY, SELECTED, DOCS))
        self.assertTrue(restrictions_kept(APPLICABILITY, SELECTED, strict=True, documents=DOCS))
        self.assertFalse(residual_conditions_kept(APPLICABILITY, SELECTED))
        for before, after in (('указанных', 'предусмотренных'), ('указанных', 'перечисленных')):
            text = SOURCE.replace(before, after)
            doc = Document(NAME, HEADER + text, '', ())
            fragment = Fragment('different', NAME, len(HEADER), len(doc.text), text, '5.')
            answer = APPLICABILITY.replace('указанным', after[:-1] + 'м')
            self.assertTrue(residual_conditions_kept(answer, [fragment], {NAME: doc}))

    def test_applicability_cannot_invert_shorten_or_change_the_group_or_address(self):
        for text in (
                APPLICABILITY.replace('не указанным', 'указанным'),
                APPLICABILITY.replace('применяется', 'не применяется'),
                APPLICABILITY.replace('3, 6 и 8', '6'),
                APPLICABILITY.replace('3, 6 и 8', '3.1, 6 и 8'),
                APPLICABILITY.replace('пунктах', 'подпунктах'),
                APPLICABILITY.replace('настоящей статьи', 'статьи 74'),
                APPLICABILITY.replace('статьи 73', 'статьи 74'),
                APPLICABILITY.replace('Пункт 5', 'Пункт 7'),
                APPLICABILITY.replace('НК РФ', 'ГК РФ'),
                'Неверно, что ' + APPLICABILITY,
                'Если ' + APPLICABILITY,
                'Вопрос содержит: «' + APPLICABILITY + '»',
                APPLICABILITY[:-1] + '?',
                APPLICABILITY[:-1] + ' при наличии разрешения.',
                APPLICABILITY + ' ' + BAD,
                APPLICABILITY.replace('3, 6 и 8', '6') + ' Упомянуты также пункты 3 и 8.'):
            with self.subTest(text=text):
                self.assertFalse(residual_conditions_kept(text, SELECTED, DOCS))

    def test_applicability_does_not_drop_a_source_condition_after_the_group(self):
        text = SOURCE[:-1] + ' при наличии разрешения.'
        doc = Document(NAME, HEADER + text, '', ())
        fragment = Fragment('tail', NAME, len(HEADER), len(doc.text), text, '5.')
        self.assertFalse(residual_conditions_kept(APPLICABILITY, [fragment], {NAME: doc}))

    def test_applicability_requires_an_unqualified_simple_rate_source_prefix(self):
        for prefix in ('Если плательщик зарегистрирован, ', 'Для индивидуальных предпринимателей ',
                       'При условии регистрации ', 'По соглашению сторон '):
            text = '5. ' + prefix + RULE.lower()
            doc = Document(NAME, HEADER + text, '', ())
            fragment = Fragment('qualified', NAME, len(HEADER), len(doc.text), text, '5.')
            with self.subTest(prefix=prefix):
                self.assertFalse(residual_conditions_kept(APPLICABILITY, [fragment], {NAME: doc}))
                self.assertFalse(restrictions_kept(APPLICABILITY, [fragment], strict=True,
                                                  documents={NAME: doc}))
        for rate in ('1 процент', '27.5 процента', '18,5 процента'):
            text = SOURCE.replace('19 процентов', rate)
            doc = Document(NAME, HEADER + text, '', ())
            fragment = Fragment('rate', NAME, len(HEADER), len(doc.text), text, '5.')
            with self.subTest(rate=rate):
                self.assertTrue(residual_conditions_kept(APPLICABILITY, [fragment], {NAME: doc}))

    def test_three_closed_neutral_forms_keep_the_exact_source_rule(self):
        for text in POSITIVE:
            with self.subTest(text=text):
                self.assertTrue(residual_conditions_kept(text, SELECTED, DOCS))
                self.assertTrue(restrictions_kept(text, SELECTED, strict=True, documents=DOCS))
                self.assertFalse(residual_conditions_kept(text, SELECTED))

    def test_wrong_address_or_nonassertive_attribution_stays_blocked(self):
        for text in (
                *(s.replace('73', '74') for s in POSITIVE),
                *(s.replace('5', '7') for s in POSITIVE),
                *(s.replace('НК', 'ГК') for s in POSITIVE if 'НК' in s),
                'Вопрос содержит: ' + POSITIVE[-1],
                'Неверно, что ' + POSITIVE[-1],
                'Если ' + POSITIVE[-1],
                POSITIVE[-1][:-1] + '?',
                POSITIVE[-1].replace('устанавливает', 'не устанавливает'),
                POSITIVE[-1].replace('устанавливает', 'предположительно устанавливает'),
                POSITIVE[0] + ' ' + BAD,
                POSITIVE[2].replace('пунктах 3, 6 и 8', 'пункте 6'),
                POSITIVE[0].replace('настоящей статьи', 'статьи 74'),
                POSITIVE[0].replace('пунктах', 'подпунктах'),
                POSITIVE[0].replace('19 процентов', '19,5 процентов'),
                '«' + POSITIVE[2] + '»',
                POSITIVE[2][:-1] + ' при согласовании с инспекцией.'):
            with self.subTest(text=text):
                self.assertFalse(residual_conditions_kept(text, SELECTED, DOCS))

    def test_ambiguous_quarantined_or_unmatched_source_address_cannot_authorize_wrapper(self):
        changed = (
            Document(NAME, DOC.text + '\nСтатья 74. Другие правила', '', ()),
            Document(NAME, DOC.text, '', ((0, len(HEADER)),)),
            Document(NAME, DOC.text.replace('НК РФ', 'ГК РФ'), '', ()),
            Document(NAME, DOC.text.replace('Источник:', 'Описание:'), '', ()),
            Document(NAME, DOC.text.replace(SOURCE, '6. ' + RULE), '', ()),
        )
        for doc in changed:
            with self.subTest(doc=doc):
                self.assertFalse(residual_conditions_kept(POSITIVE[2], SELECTED, {NAME: doc}))
        self.assertFalse(residual_conditions_kept(POSITIVE[2], SELECTED, {}))

    def test_a_later_composite_provision_does_not_inherit_first_point_number(self):
        composite = '4. Для отдельной категории ставка составляет 11 процентов.\n' + SOURCE
        doc = Document(NAME, HEADER + composite, '', ())
        fragment = Fragment('composite', NAME, len(HEADER), len(doc.text), composite, '4.')
        self.assertFalse(residual_conditions_kept(POSITIVE[2].replace('пункту 5', 'пункту 4'),
                                                 [fragment], {NAME: doc}))

    def test_changed_article_point_code_and_reference_group_are_not_hardcoded(self):
        rule = RULE.replace('19', '27').replace('3, 6 и 8', '2.1, 7.2 и 9.3')
        text = '12. ' + rule
        header = 'Источник: Статья 91. ГК РФ\nСтатья 91. Платежи\n'
        doc = Document(NAME, header + text, '', ())
        fragment = Fragment('changed', NAME, len(header), len(doc.text), text, '12.')
        answer = 'Пункт 12 статьи 91 ГК РФ устанавливает: «' + rule[:-1] + '».'
        self.assertTrue(residual_conditions_kept(answer, [fragment], {NAME: doc}))


if __name__ == '__main__':
    unittest.main()
