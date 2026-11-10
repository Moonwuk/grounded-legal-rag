"""Lexical baseline: BM25 with word-prefix features and source-context expansion.

No demo answers, question IDs, or expected answers are used by this module.
Prefix features are a baseline, not a Russian morphological analyser.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import math
import re
from psb_corpus import Document, Fragment, check_deadline

STOP = set("и в во на по с со у к ко из за от до для не ли мы вы он она они это как какой какая какие что сколько нужно можно чем при а или его ее их нам нас наш этот того если будет было есть меня мне теперь".split())


def tokens(text: str) -> list[str]:
    result = []
    for word in re.findall(r"[а-яёa-z0-9]+", text.lower().replace("ё", "е")):
        if word in STOP or len(word) < 2:
            continue
        result.append(word)
        if len(word) >= 6:
            result.append("~" + word[:5])
            result.append("^" + word[:4])
    return result


def user_turns(question: str) -> list[str]:
    # Textual role labels are data, never API roles or trusted instructions.
    parts = re.split(r"(?im)^\s*(Пользователь|Ассистент)\s*:\s*", question)
    if len(parts) < 3:
        return [question]
    return [parts[i + 1] for i in range(1, len(parts) - 1, 2)
            if parts[i].lower() == "пользователь"] or [question]


def identifiers(text: str) -> set[str]:
    return {re.sub(r"\s+", "", x).lower() for x in
            re.findall(r"\b(?:ПТ|П|А)\s*[-–]\s*\d{2}\s*/\s*\d{4}\b", text, re.I)}


class Retriever:
    def __init__(self, documents: list[Document], fragments: list[Fragment], deadline=None):
        self.deadline = deadline
        self.documents = {d.name: d for d in documents}
        self.fragments = fragments
        self.by_doc = defaultdict(list)
        self.counts = []
        self.postings = defaultdict(list)
        df = Counter()
        features = 0
        for index, f in enumerate(fragments):
            check_deadline(deadline)
            self.by_doc[f.document].append(f)
            c = Counter(tokens(f.document.replace("_", " ") + " " + f.text))
            features += len(c)
            if features > 2000000:
                raise ValueError("index_feature_limit")
            self.counts.append(c)
            df.update(c.keys())
            for word, frequency in c.items():
                self.postings[word].append((index, frequency))
        self.lengths = [sum(c.values()) for c in self.counts]
        self.avg = sum(map(lambda c: sum(c.values()), self.counts)) / len(self.counts)
        self.idf = {w: math.log(1 + (len(fragments) - n + .5) / (n + .5)) for w, n in df.items()}
        self.doc_ids = {d.name: identifiers(d.text[:700]) for d in documents}

    def _scores(self, query):
        scores = defaultdict(float)
        for word, weight in query.items():
            check_deadline(self.deadline)
            for index, frequency in self.postings.get(word, ()):
                scores[index] += weight * self.idf[word] * frequency * 2.5 / (
                    frequency + 1.5 * (.25 + .75 * self.lengths[index] / self.avg))
        return scores

    def search(self, question: str, top_k: int = 6, expanded: bool = False) -> list[Fragment]:
        turns = user_turns(question)
        current = turns[-1]
        query = Counter(tokens(current))
        for turn in turns[:-1]:
            for token in tokens(turn):
                query[token] += .35
        ids = set()
        party = None
        for turn in reversed(turns):
            if not ids:
                ids = identifiers(turn)
            if party is None:
                matches = re.findall(r"альфа[- ]трейдинг\b|альфа[- ]трейд\b|северн\w*\s+склад\w*", turn, re.I)
                if matches:
                    party = matches[-1].lower().replace(" ", "-")
        scored = []
        clauses = re.split(r"\s+и\s+(?=(?:како|кто|где|сколь|до\s|нужно|можно))", current, flags=re.I)
        if len(clauses) > 16:
            raise ValueError("question_complexity_limit")
        # IDs are strong entity features, but not useful when discovering a
        # separate document answering another part of the same question.
        lexical_queries = [Counter(t for t in tokens(re.sub(
            r"\b(?:ПТ|П|А)\s*[-–]\s*\d{2}\s*/\s*\d{4}\b", "", clause, flags=re.I))
            if not t.isdigit()) for clause in clauses]
        lexical_scores = [[] for _ in lexical_queries]
        primary = self._scores(query)
        secondary = [self._scores(q) for q in lexical_queries]
        for index, f in enumerate(self.fragments):
            score = primary.get(index, 0.)
            for j, scores in enumerate(secondary):
                lexical_score = scores.get(index, 0.)
                lexical_scores[j].append((lexical_score, f))
            if ids & self.doc_ids[f.document]:
                score += 9
            name = f.document.lower()
            if party:
                if party == "альфа-трейд" and re.search(r"альфа-трейд(?:\.|\s|$)", name):
                    score += 7
                elif party == "альфа-трейдинг" and "альфа-трейдинг" in name:
                    score += 7
                elif party.startswith("северн") and "северный склад" in name:
                    score += 7
            scored.append((score, f))
        scored.sort(key=lambda x: (-x[0], x[1].document, x[1].start))
        hits = [f for score, f in scored if score > 0][:top_k * (2 if expanded else 1)]
        # Exact entity matches must not crowd out a second subject such as
        # archive handling. Reserve candidates from the unboosted lexical rank.
        existing = {f.id for f in hits}
        for ranking in lexical_scores:
            ranking.sort(key=lambda x: (-x[0], x[1].document, x[1].start))
            for score, f in ranking[:4 if expanded else 2]:
                if score > 0 and f.id not in existing:
                    hits.append(f)
                    existing.add(f.id)
        selected = {f.id: f for f in hits}
        selected_docs = {f.document for f in hits}
        # Relations are derived from the corpus text. Keep dates and original
        # clauses together with changes. The LLM still must assess applicability.
        connected = set(selected_docs)
        for name in selected_docs:
            if self.doc_ids[name]:
                connected.update(n for n, docids in self.doc_ids.items() if docids & self.doc_ids[name])
            if "регламент согласования" in name.lower():
                connected.update(n for n, d in self.documents.items()
                                 if not n.startswith("законы__") and "регламент" in d.text.lower())
        for name in connected:
            if len(self.documents[name].text) <= 7500:
                selected.update((f.id, f) for f in self.by_doc[name])
        for hit in hits:
            siblings = self.by_doc[hit.document]
            if len(self.documents[hit.document].text) > 7500:
                i = siblings.index(hit)
                for f in siblings[max(0, i - 2):i + 3]:
                    selected[f.id] = f
                # Preserve editorial and article-level context as well as hit text.
                for f in siblings[:7]:
                    selected[f.id] = f
        # If the context does not fit, drop whole documents, never sever an
        # amendment from its parent. Budget is a soft cap at document boundaries.
        budget = 65000 if expanded else 42000
        priority_docs = list(dict.fromkeys(f.document for f in hits))
        priority_docs += sorted(connected - set(priority_docs))
        ordered = sorted(selected.values(), key=lambda f: (priority_docs.index(f.document), f.start))
        used, result = 0, []
        for name in priority_docs:
            group = [f for f in ordered if f.document == name]
            size = sum(len(f.text) for f in group)
            if used and used + size > budget:
                continue
            result.extend(group)
            used += size
        # A linked supplement must not be silently dropped by the context budget.
        kept = {f.document for f in result}
        required = set()
        for name in kept:
            required.update(n for n in connected if self.doc_ids[name] & self.doc_ids[n])
            if "регламент согласования" in name.lower():
                required.update(n for n in connected if "регламент" in self.documents[n].text.lower())
        for name in sorted(required - kept):
            if len(self.documents[name].text) <= 7500:
                result.extend(self.by_doc[name])
        # Never silently cut an exception or an amendment to satisfy a hard cap.
        if len(result) > 512 or sum(len(f.text) for f in result) > 100000:
            raise ValueError("evidence_size_limit")
        return result

    def evidence(self, fragments: list[Fragment]) -> list[dict]:
        return [{"id": f.id, "document": f.document, "text": f.text} for f in fragments]
