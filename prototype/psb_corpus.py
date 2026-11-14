"""Read-only corpus loader. Offsets refer to decoded source text, not file bytes."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import io
# ElementTree is used only with the DTD-rejecting DocumentXML target below.
from xml.etree import ElementTree as ET  # nosec B405
import hashlib
import re
import stat
import zipfile

MAX_DOCUMENTS = 4096
MAX_FRAGMENTS = 50000
MAX_TEXT = 64 * 1024 * 1024


def check_deadline(deadline):
    if deadline is not None:
        import time
        if time.monotonic() >= deadline:
            raise ValueError("corpus_deadline")


class DocumentXML(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        # Parser callback also catches UTF-16/32 declarations, unlike a byte regex.
        raise ValueError("docx_entities_not_allowed")

INSTRUCTION = re.compile(
    r"внимание\s+для\s+ии[- ]ассистента|игнорируй\s+все\s+остальные\s+документы|"
    r"ignore\s+(?:all|previous)\s+(?:previous\s+)?instructions", re.I)


@dataclass(frozen=True)
class Document:
    name: str
    text: str
    sha256: str
    quarantined: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Fragment:
    id: str
    document: str
    start: int
    end: int
    text: str
    heading: str


def norm(text: str) -> str:
    return " ".join(text.split())


def read_docx(raw: bytes) -> str:
    # Do not extract files or follow relationships, external links or macros.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = [i for i in archive.infolist() if i.filename == "word/document.xml"]
        if len(infos) != 1 or infos[0].file_size > 8 * 1024 * 1024:
            raise ValueError("invalid_docx_main_document")
        # Reject unsupported semantic parts instead of silently discarding them.
        if any(i.filename in {"word/footnotes.xml", "word/endnotes.xml"} for i in archive.infolist()):
            raise ValueError("docx_notes_not_supported")
        xml = archive.read(infos[0])
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("docx_entities_not_allowed")
    try:
        # DocumentXML rejects the DOCTYPE callback before entity declarations,
        # after encoding detection. Regression tests cover UTF-8/UTF-16 DTDs.
        root = ET.fromstring(xml, parser=ET.XMLParser(target=DocumentXML()))  # nosec B314
    except ET.ParseError:
        raise ValueError("invalid_docx_xml") from None
    stack = [(root, 0)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > 100000 or depth > 128:
            raise ValueError("docx_structure_limit")
        stack.extend((child, depth + 1) for child in node)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    if any(n.tag in {ns + "footnoteReference", ns + "endnoteReference", ns + "altChunk"} for n in root.iter()):
        raise ValueError("docx_semantic_part_not_supported")
    paragraphs = []
    for p in root.iter(ns + "p"):
        parts = []
        for node in p.iter():
            if node.tag == ns + "t": parts.append(node.text or "")
            elif node.tag == ns + "tab": parts.append("\t")
            elif node.tag in {ns + "br", ns + "cr"}: parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


# Problems of a single document. With a `skipped` list the document is left
# out with its reason and the rest of the base is read; archive-level limits and
# protections stay fatal.
DOCUMENT_ERRORS = {"unsupported_document_format", "empty_document", "document_not_utf8", "invalid_docx",
                   "invalid_docx_main_document", "docx_notes_not_supported", "docx_entities_not_allowed",
                   "invalid_docx_xml", "docx_structure_limit", "docx_semantic_part_not_supported"}


def read_document(suffix: str, raw: bytes) -> str:
    try:
        text = read_docx(raw) if suffix == ".docx" else raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("document_not_utf8") from None
    except zipfile.BadZipFile:
        raise ValueError("invalid_docx") from None
    if not text.strip():
        raise ValueError("empty_document")
    return text


def load_corpus(path: Path, deadline: float | None = None,
                skipped: list | None = None) -> tuple[list[Document], list[Fragment]]:
    documents = []
    fragments = []
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("archive_size_limit")
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > MAX_DOCUMENTS * 2:
            raise ValueError("archive_entry_limit")
        total = 0
        decoded_total = 0
        names = set()
        for info in sorted(archive.infolist(), key=lambda x: x.filename):
            check_deadline(deadline)
            name = info.filename
            p = PurePosixPath(name)
            if (p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name
                    or len(name) > 512 or any(ord(c) < 32 for c in name)):
                raise ValueError("unsafe_archive_path")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("archive_symlink")
            if info.is_dir() or name.startswith("__MACOSX/"):
                continue
            if p.suffix.lower() not in {".txt", ".md", ".docx"}:
                if skipped is None:
                    raise ValueError("unsupported_document_format")
                skipped.append((name, "unsupported_document_format"))
                continue
            if name in names or len(names) >= MAX_DOCUMENTS:
                raise ValueError("duplicate_document_or_count_limit")
            names.add(name)
            total += info.file_size
            if total > 64 * 1024 * 1024 or info.file_size > 8 * 1024 * 1024:
                raise ValueError("corpus_size_limit")
            raw = archive.read(info)
            try:
                text = read_document(p.suffix.lower(), raw)
            except ValueError as error:
                if skipped is None or str(error) not in DOCUMENT_ERRORS:
                    raise
                skipped.append((name, str(error)))
                continue
            decoded_total += len(text)
            if decoded_total > MAX_TEXT:
                raise ValueError("decoded_corpus_size_limit")
            digest = hashlib.sha256(raw).hexdigest()
            quarantined = []
            for m in re.finditer(r"[^\n]+", text):
                check_deadline(deadline)
                if INSTRUCTION.search(m.group()):
                    if len(quarantined) >= MAX_FRAGMENTS:
                        raise ValueError("quarantine_count_limit")
                    quarantined.append((m.start(), m.end()))
            banned = tuple(quarantined)
            banned_starts = {a for a, _ in banned}
            documents.append(Document(name, text, digest, banned))
            # Every source line remains addressable. Long paragraphs are split
            # with overlap; surrounding paragraphs are restored during retrieval.
            heading = ""
            for match in re.finditer(r"[^\n]+", text):
                check_deadline(deadline)
                line = match.group()
                if not line.strip() or match.start() in banned_starts:
                    continue
                if re.match(r"(?:Статья\s+\d|\d+(?:\.\d+)*\.\s)", line):
                    heading = line[:160]
                offset = 0
                while offset < len(line):
                    check_deadline(deadline)
                    if len(fragments) >= MAX_FRAGMENTS:
                        raise ValueError("fragment_count_limit")
                    start = match.start() + offset
                    end = min(match.end(), start + 2200)
                    if end < match.end():
                        boundary = text.rfind(" ", start + 1200, end)
                        if boundary > start:
                            end = boundary
                    fid = hashlib.sha256(f"{name}:{digest}:{start}:{end}".encode()).hexdigest()[:20]
                    fragments.append(Fragment(fid, name, start, end, text[start:end], heading))
                    if end == match.end():
                        break
                    offset = end - match.start() - 180
            lines = list(re.finditer(r"[^\n]+", text))
            for i, line in enumerate(lines):
                if not line.group().strip() or len(norm(line.group())) >= 12 or line.start() in banned_starts:
                    continue
                start = lines[max(0, i - 1)].start()
                end = lines[min(len(lines) - 1, i + 1)].end()
                if end - start > 2200 or any(a < end and b > start for a, b in banned):
                    continue
                if len(fragments) >= MAX_FRAGMENTS:
                    raise ValueError("fragment_count_limit")
                fid = hashlib.sha256(f"{name}:{digest}:{start}:{end}".encode()).hexdigest()[:20]
                if not any(f.id == fid for f in fragments[-3:]):
                    fragments.append(Fragment(fid, name, start, end, text[start:end], ""))
    if not documents or not fragments:
        raise ValueError("empty_corpus")
    if len({d.name for d in documents}) != len(documents):
        raise ValueError("duplicate_document")
    return documents, fragments
