"""One unreadable document no longer rejects the whole knowledge base.

Before: an empty file, a file of another format, text that is not UTF-8 or a
DOCX with footnotes made load_corpus raise, solution.py wrote a technical
answer for every question, and the platform judge would score zero. Now a
caller that passes `skipped` gets the document left out explicitly, with a
reason code, and the rest of the base is read. Archive-level protections
(unsafe paths, links, size and count limits, duplicates) stay fatal, and
without `skipped` the old behaviour is unchanged.
"""
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
from psb_corpus import load_corpus  # noqa: E402

GOOD = 'Договор № ТР-4/2032\n3.1. Плата за хранение составляет 61 000 рублей в месяц.\n'


def docx(body, notes=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   f'<w:body><w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body></w:document>')
        if notes:
            z.writestr('word/footnotes.xml', '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
    return buf.getvalue()


def archive(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)


BAD = {
    'пустой.txt': b'   \n',
    'скан.pdf': b'%PDF-1.4 binary',
    'кодировка.txt': 'Срок 30 дней'.encode('cp1251'),
    'сноски.docx': docx('Положение со сноской', notes=True),
    'битый.docx': b'not a zip',
}
CODES = {'пустой.txt': 'empty_document', 'скан.pdf': 'unsupported_document_format',
         'кодировка.txt': 'document_not_utf8', 'сноски.docx': 'docx_notes_not_supported', 'битый.docx': 'invalid_docx'}


class DocumentSkippingTests(unittest.TestCase):
    def test_bad_documents_are_skipped_with_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'kb.zip'
            archive(path, {'договор.txt': GOOD.encode(), **BAD})
            skipped = []
            docs, frags = load_corpus(path, skipped=skipped)
            self.assertEqual([d.name for d in docs], ['договор.txt'])
            self.assertTrue(any('61 000' in f.text for f in frags))
            self.assertEqual(dict(skipped), CODES)

    def test_without_skipped_the_first_bad_document_still_raises(self):
        for name, data in BAD.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'kb.zip'
                archive(path, {'договор.txt': GOOD.encode(), name: data})
                with self.assertRaises(ValueError):
                    load_corpus(path)

    def test_archive_level_protections_stay_fatal(self):
        for files in ({'../выход.txt': GOOD.encode()}, {'C:\\окно.txt': GOOD.encode()}):
            with self.subTest(list(files)), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'kb.zip'
                archive(path, {'договор.txt': GOOD.encode(), **files})
                with self.assertRaises(ValueError):
                    load_corpus(path, skipped=[])

    def test_all_documents_bad_is_still_an_empty_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'kb.zip'
            archive(path, BAD)
            with self.assertRaisesRegex(ValueError, 'empty_corpus'):
                load_corpus(path, skipped=[])

    def test_solution_answers_with_a_bad_document_in_the_base(self):
        # A stub model at an unreachable address: the run must get past loading
        # (technical answers are expected), not stop with exit code 2.
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            data.mkdir()
            archive(data / 'knowledge-base.zip', {'договор.txt': GOOD.encode(), **BAD})
            (data / 'questions.csv').write_text('id,question\n01,Какая плата за хранение по договору ТР-4/2032?\n', encoding='utf-8')
            env = {**os.environ, 'DATA_DIR': str(data), 'LLM_BASE_URL': 'http://127.0.0.1:9/v1',
                   'LLM_API_KEY': 'test-placeholder', 'LLM_MODEL': 'stub', 'PSB_RUN_SECONDS': '20'}
            env.pop('EMB_MODEL', None)
            run = subprocess.run([sys.executable, str(ROOT / 'prototype' / 'solution.py')], cwd=tmp, env=env,
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-500:])
            self.assertIn('documents_skipped=5', run.stderr)
            rows = list(csv.DictReader(open(Path(tmp) / 'submission.csv', encoding='utf-8')))
            self.assertEqual([r['id'] for r in rows], ['01'])


if __name__ == '__main__':
    unittest.main()
