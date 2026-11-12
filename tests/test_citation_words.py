"""A reference to the basis is not an added assertion.

Demo run 436ae8f, question 12 (probation and labour rules): the model text
ended with «(статья 70 ТК РФ)»; the barrier against unsupported additions
read «актов, содержащих …» as a statement about the contents of a document and
required every word of the sentence, «статья» included, to be in the source.
The same text with «(ст. 70 ТК РФ)» passed. The text was rejected twice and
only the quotation was published.
"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from psb_corpus import Fragment  # noqa: E402
from psb_policy import added_assertions_safe  # noqa: E402

SOURCE = [Fragment('f', 'law.txt', 0, 200, 'В период стажировки на работника распространяются требования локальных актов, '
                   'содержащих правила внутреннего распорядка.', '')]
BODY = 'Да. В период стажировки на работника распространяются требования локальных актов, содержащих правила внутреннего распорядка'


class CitationWordsTests(unittest.TestCase):
    def test_reference_wordings_are_equivalent(self):
        for reference in ('(ст. 44 Учебного кодекса)', '(статья 44 ТК РФ)', '(статьи 44 Учебного кодекса РФ)',
                          '(пункт 4.2 положения)', '(п. 4.2)', '(подпункт 3 пункта 2 статьи 44 ГК РФ)', '(часть 2 статьи 44 КоАП РФ)'):
            with self.subTest(reference):
                self.assertTrue(added_assertions_safe(f'{BODY} {reference}.', SOURCE))

    def test_unsupported_record_claims_are_still_rejected(self):
        for text in ('Акт содержит подпись директора (статья 44 ТК РФ).',
                     'В период стажировки на работника распространяются требования локальных актов, содержащих премиальные выплаты (статья 44).',
                     'Протокол фиксирует отказ работника (пункт 4.2).'):
            with self.subTest(text):
                self.assertFalse(added_assertions_safe(text, SOURCE))


if __name__ == '__main__':
    unittest.main()
