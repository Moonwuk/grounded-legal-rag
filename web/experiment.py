"""Bridge the competition engine to the web document and response contracts."""
from contextlib import redirect_stderr
import os
from pathlib import Path
import sys
import time

CORE = Path(__file__).resolve().parents[1] / "submissions" / "psb_experiment"
TECHNICAL = "Не удалось получить проверенный ответ. Повторите вопрос."


def normalized(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")


def original_span(document, cleaned, start, end, sanitize):
    """Translate cleaned offsets without losing the original text of a quotation."""
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(cleaned):
        raise ValueError("invalid_citation_range")
    chars, positions = [], []
    i = 0
    while i < len(document.text):
        char = document.text[i]
        positions.append(i)
        chars.append("\n" if char == "\r" else " " if char == "\u00a0" else char)
        i += 2 if document.text[i:i + 2] == "\r\n" else 1
    raw = "".join(chars)
    clean, _ = sanitize(raw)
    mapped, offset = [], 0
    for before, after in zip(raw.split("\n"), clean.split("\n")):
        mapped.extend(positions[offset:offset + len(before)] if before == after else [None] * len(after))
        offset += len(before)
        if offset < len(raw):
            mapped.append(positions[offset])
            offset += 1
    left = len(clean) - len(clean.lstrip())
    if clean.strip() != cleaned:
        raise ValueError("document_text_mismatch")
    selected = mapped[left + start:left + end]
    if len(selected) != end - start or any(pos is None for pos in selected):
        raise ValueError("citation_contains_removed_instruction")
    a, b = selected[0], selected[-1] + 1
    if normalized(document.text[a:b]) != cleaned[start:end]:
        raise ValueError("citation_text_mismatch")
    if any(a < stop and b > begin for begin, stop in document.quarantined):
        raise ValueError("citation_in_quarantine")
    return a, b


def run(question, documents):
    """Run only in the disposable generation process; no engine globals are shared."""
    started = time.monotonic()
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    # Batch diagnostics can contain drafts. The web never publishes those logs.
    with open(os.devnull, "w") as sink, redirect_stderr(sink):
        import config
        import kb as corpus
        import pipeline
        import runtime
        from index import Index
        from checks import unverified_refs

        config.MODE = "web"
        config.DEBUG = False
        pipeline.DEBUG = False
        original_loader = corpus.load_raw_docs
        corpus.load_raw_docs = lambda: [(d.name, normalized(d.text)) for d in documents]
        try:
            knowledge = corpus.build_kb()
        finally:
            corpus.load_raw_docs = original_loader
        if not knowledge.docs or not knowledge.chunks:
            return failure(started, "empty_corpus")
        index = Index(knowledge)
        if os.getenv("EMB_MODEL", "").strip():
            if config.PREBUILT_INDEX:
                index.load_prebuilt()
            if index.vecs is None:
                index.build_dense(cap=30)
        runtime.FLAGS.rerank_off = not bool(os.getenv("RERANKER_MODEL", "").strip())
        originals = {d.name: d for d in documents}
        ids = {d.idx: originals[d.path].sha256 for d in knowledge.docs}
        result = pipeline.answer(knowledge, index, question, ids=ids)
        if result.status == "error":
            return failure(started, "generation_failed")
        if any(w.get("code") in {"unverified_numbers", "clause_not_found"} for w in result.warnings):
            return failure(started, "answer_validation_failed")
        cited_docs = [d for d in knowledge.docs if any(c["doc_id"] == ids[d.idx] for c in result.citations)]
        if unverified_refs(knowledge, result.text, question, cited_docs):
            return failure(started, "reference_validation_failed")
        sources = []
        by_id = {ids[d.idx]: d for d in knowledge.docs}
        for cite in result.citations:
            if not cite.get("found"):
                return failure(started, "citation_not_found")
            doc = by_id[cite["doc_id"]]
            original = originals[doc.path]
            try:
                a, b = original_span(original, doc.text, cite["start"], cite["end"], corpus.sanitize)
            except (ValueError, KeyError):
                return failure(started, "citation_validation_failed")
            sources.append(dict(n=len(sources) + 1, document_id=original.sha256, title=doc.title,
                                status=doc.status, heading=cite.get("clause") or doc.label,
                                start=a, end=b, quote=original.text[a:b]))
        status = {"no_info": "insufficient", "premise_error": "answer"}.get(result.status, result.status)
        if status in {"answer", "partial"} and not sources:
            return failure(started, "answer_without_sources")
        if status not in {"answer", "partial", "insufficient", "clarify", "out_of_scope"}:
            return failure(started, "unknown_status")
        return dict(status=status, text=result.text, sources=sources, core="psb_experiment",
                    elapsed_seconds=round(time.monotonic() - started, 1))


def failure(started, code):
    return dict(status="technical_error", text=TECHNICAL, sources=[], error_code=code,
                core="psb_experiment", elapsed_seconds=round(time.monotonic() - started, 1))
