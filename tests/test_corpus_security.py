"""DOCX parser regressions without network access or a model API."""
from pathlib import Path
import io
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))
from psb_corpus import read_docx


NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ENCODINGS = (
    ("utf-8", "UTF-8"),
    ("utf-16", "UTF-16"),
    ("utf-16-le", "UTF-16LE"),
    ("utf-16-be", "UTF-16BE"),
)


def document_xml(text, declaration=""):
    return (declaration + f'<w:document xmlns:w="{NAMESPACE}"><w:body>'
            f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
            "</w:body></w:document>")


def docx_xml(xml):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return result.getvalue()


class DocxSecurityTests(unittest.TestCase):
    def test_valid_text_and_predefined_entities_in_supported_encodings(self):
        for encoding, declaration in ENCODINGS:
            with self.subTest(encoding=encoding):
                xml = (f'<?xml version="1.0" encoding="{declaration}"?>'
                       + document_xml("Оплата &amp; срок: &#51;0 дней."))
                self.assertEqual(read_docx(docx_xml(xml.encode(encoding))),
                                 "Оплата & срок: 30 дней.")

    def test_all_dtds_rejected_after_decoding(self):
        declarations = (
            '<!DOCTYPE w:document>',
            '<!DOCTYPE w:document [<!ENTITY probe "SHOULD_NOT_EXPAND">]>',
            '<!DOCTYPE w:document [<!ENTITY probe SYSTEM "file:///nonexistent-docx-probe">]>',
            '<!DOCTYPE w:document SYSTEM "https://example.invalid/docx-probe.dtd">',
        )
        for encoding, encoding_declaration in ENCODINGS:
            for dtd in declarations:
                with self.subTest(encoding=encoding, dtd=dtd):
                    xml = (f'<?xml version="1.0" encoding="{encoding_declaration}"?>'
                           + document_xml("&probe;", dtd))
                    with self.assertRaisesRegex(ValueError, "docx_entities_not_allowed"):
                        read_docx(docx_xml(xml.encode(encoding)))

    def test_utf32_dtds_fail_closed(self):
        for encoding, declaration in (
            ("utf-32", "UTF-32"),
            ("utf-32-le", "UTF-32LE"),
            ("utf-32-be", "UTF-32BE"),
        ):
            with self.subTest(encoding=encoding):
                xml = (f'<?xml version="1.0" encoding="{declaration}"?>'
                       + document_xml("&probe;", '<!DOCTYPE w:document ['
                                      '<!ENTITY probe "SHOULD_NOT_EXPAND">]>'))
                with self.assertRaisesRegex(
                    ValueError, "invalid_docx_xml|docx_entities_not_allowed"
                ):
                    read_docx(docx_xml(xml.encode(encoding)))

    def test_malformed_xml_is_a_controlled_error(self):
        with self.assertRaisesRegex(ValueError, "invalid_docx_xml"):
            read_docx(docx_xml(b"<document>"))


if __name__ == "__main__":
    unittest.main()
