"""Read-only corpus loader. Offsets refer to decoded source text, not file bytes."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import io
from xml.etree import ElementTree as ET
import hashlib
import re
import zipfile

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
        xml = archive.read(infos[0])
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("docx_entities_not_allowed")
    root = ET.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for p in root.iter(ns + "p"):
        parts = []
        for node in p.iter():
            if node.tag == ns + "t": parts.append(node.text or "")
            elif node.tag == ns + "tab": parts.append("\t")
            elif node.tag in {ns + "br", ns + "cr"}: parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def load_corpus(path: Path) -> tuple[list[Document], list[Fragment]]:
    documents = []
    fragments = []
    with zipfile.ZipFile(path) as archive:
        total = 0
        for info in sorted(archive.infolist(), key=lambda x: x.filename):
            name = info.filename
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name:
                raise ValueError("unsafe_archive_path")
            if info.is_dir() or name.startswith("__MACOSX/"):
                continue
            if p.suffix.lower() not in {".txt", ".md", ".docx"}:
                raise ValueError("unsupported_document_format")
            total += info.file_size
            if total > 64 * 1024 * 1024 or info.file_size > 8 * 1024 * 1024:
                raise ValueError("corpus_size_limit")
            raw = archive.read(info)
            text = read_docx(raw) if p.suffix.lower() == ".docx" else raw.decode("utf-8-sig")
            digest = hashlib.sha256(raw).hexdigest()
            banned = tuple((m.start(), m.end()) for m in re.finditer(r"[^\n]+", text)
                           if INSTRUCTION.search(m.group()))
            documents.append(Document(name, text, digest, banned))
            # Every source line remains addressable. Long paragraphs are split
            # with overlap; surrounding paragraphs are restored during retrieval.
            heading = ""
            for match in re.finditer(r"[^\n]+", text):
                line = match.group()
                if not line.strip() or any(a <= match.start() < b for a, b in banned):
                    continue
                if re.match(r"(?:Статья\s+\d|\d+(?:\.\d+)*\.\s)", line):
                    heading = line[:160]
                offset = 0
                while offset < len(line):
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
    if not documents or not fragments:
        raise ValueError("empty_corpus")
    if len({d.name for d in documents}) != len(documents):
        raise ValueError("duplicate_document")
    return documents, fragments
