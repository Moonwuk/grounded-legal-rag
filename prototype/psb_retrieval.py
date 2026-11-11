"""Lexical baseline: BM25 with word-prefix features and source-context expansion.

No demo answers, question IDs, or expected answers are used by this module.
Prefix features are a baseline, not a Russian morphological analyser.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
from bisect import bisect_right, bisect_left
import math
import re
from psb_corpus import Document, Fragment, check_deadline

STOP = set("и в во на по с со у к ко из за от до для не ли мы вы он она они это как какой какая какие что сколько нужно можно чем при а или его ее их нам нас наш этот того если будет было есть меня мне теперь".split())


def tokens(text: str) -> list[str]:
    result = []
    for word in re.findall(r"[а-яёa-z0-9]+", text.lower().replace("ё", "е")):
        if word in STOP or (len(word) < 2 and not word.isdigit()):
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
            re.findall(r"\b[A-Za-zА-Яа-яЁё]{1,8}\s*[-–]\s*\d{1,8}\s*/\s*\d{4}\b", text, re.I)}


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
        self.paragraph_boundaries = {}
        for d in documents:
            boundaries = [0]
            previous_blank = False
            for line in re.finditer(r"[^\n]*(?:\n|$)", d.text):
                value = line.group()
                if not value:
                    continue
                structural = re.match(r"\s*(?:Статья\s+\d|\d+(?:\.\d+)*[.)]\s)", value, re.I)
                if value.strip() and (previous_blank or structural) and line.start() > boundaries[-1]:
                    boundaries.append(line.start())
                previous_blank = not value.strip()
            if boundaries[-1] != len(d.text):
                boundaries.append(len(d.text))
            # Quarantine is a hard context boundary. Restoring a paragraph
            # must never reintroduce a removed instruction line.
            self.paragraph_boundaries[d.name] = sorted(set(boundaries) |
                {offset for span in d.quarantined for offset in span})
        # Explicit flat lists only: a colon introduces items terminated by
        # semicolons and a final period. No semantic relations are guessed.
        self.list_parents = {}
        for d in documents:
            parent, style = None, None
            boundaries = self.paragraph_boundaries[d.name]
            links = {}
            for start, end in zip(boundaries, boundaries[1:]):
                check_deadline(deadline)
                value = d.text[start:end].strip()
                if any(a < end and b > start for a, b in d.quarantined):
                    parent, style = None, None
                    continue
                if not value:
                    continue
                if value.endswith(":"):
                    parent, style = (start, end), None
                    continue
                marker = re.match(r"(?:([-•])\s+|(\d+[.)])\s+|([а-яa-z][)])\s+)", value)
                current_style = ("bullet" if marker.group(1) else
                                 "number" + marker.group(2)[-1] if marker.group(2) else "letter") if marker else "plain"
                item = bool(marker) or value[0].islower()
                if (parent is not None and item and value.endswith((";", "."))
                        and (style is None or style == current_style)):
                    links[(start, end)] = parent
                    style = current_style
                    if value.endswith("."):
                        parent, style = None, None
                else:
                    parent, style = None, None
            self.list_parents[d.name] = links
        self.article_catalog = defaultdict(set)
        self.law_by_doc = {}
        for d in documents:
            header = d.text.split("\n", 1)[0]
            code = re.search(r"\b([а-яё]+)\s+кодекс\b", header, re.I)
            law = re.search(r"(?:N|№)\s*(\d+)\s*[-–]\s*ФЗ\b", header, re.I)
            identity = code.group(1).casefold() + " кодекс" if code else (law.group(1) + "-фз" if law else None)
            if identity:
                self.law_by_doc[d.name] = identity
                articles = re.findall(r"(?:^|Источник:.*?)(?:Статья)\s+(\d+(?:\.\d+)?)", d.text, re.I | re.M)
                self.article_catalog[identity].update(articles)
        self.parties = {d.name: {x.casefold().replace(" ", "-") for x in
                        re.findall(r"«([^»\n]{2,80})»", d.text[:1200])} for d in documents}

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
                known = set().union(*self.parties.values())
                normalized = turn.casefold().replace(" ", "-")
                matches = [name for name in known if re.search(r"(?<![а-яa-z])" + re.escape(name) + r"(?![а-яa-z])", normalized)]
                if matches:
                    party = max(matches, key=lambda name: normalized.rfind(name))
        clause_numbers = re.findall(r"(?:пункт(?:а|е)?|п\.|статья|статьи)\s*(\d+(?:\.\d+)*)", current, re.I)
        scored = []
        clauses = re.split(r"\s+и\s+(?=(?:како|кто|где|сколь|до\s|нужно|можно))", current, flags=re.I)
        if len(clauses) > 16:
            raise ValueError("question_complexity_limit")
        # IDs are strong entity features, but not useful when discovering a
        # separate document answering another part of the same question.
        lexical_queries = [Counter(t for t in tokens(re.sub(
            r"\b[A-Za-zА-Яа-яЁё]{1,8}\s*[-–]\s*\d{1,8}\s*/\s*\d{4}\b", "", clause, flags=re.I))
            ) for clause in clauses]
        lexical_scores = [[] for _ in lexical_queries]
        primary = self._scores(query)
        secondary = [self._scores(q) for q in lexical_queries]
        for index, f in enumerate(self.fragments):
            score = primary.get(index, 0.)
            if any(re.match(r"(?:Статья\s+)?" + re.escape(n) + r"(?:[.\s)]|$)", f.text, re.I) for n in clause_numbers):
                score += 25
            for j, scores in enumerate(secondary):
                lexical_score = scores.get(index, 0.)
                lexical_scores[j].append((lexical_score, f))
            if ids & self.doc_ids[f.document]:
                score += 9
            name = f.document.lower()
            if party and party in self.parties[f.document]:
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
            # When the question names an identifier, only documents of that
            # identifier bring their linked documents. A lexical hit about another
            # contract stays a candidate itself but must not pull in its whole family.
            if self.doc_ids[name] and (not ids or ids & self.doc_ids[name]):
                connected.update(n for n, docids in self.doc_ids.items() if docids & self.doc_ids[name])
            if "регламент согласования" in name.lower():
                connected.update(n for n, d in self.documents.items()
                                 if not n.startswith("законы__") and "регламент" in d.text.lower())
        for name in connected:
            if len(self.documents[name].text) <= 7500 or name not in selected_docs:
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
        def unit(name):
            """A document with every document it must not be separated from."""
            members = {name} | {n for n in connected if self.doc_ids[name] & self.doc_ids[n]}
            if "регламент согласования" in name.lower():
                members |= {n for n in connected if "регламент" in self.documents[n].text.lower()}
            return members
        # The budget counts a document together with its linked documents, so a
        # family is kept whole or skipped whole; linked documents can no longer
        # be added afterwards past the budget.
        used, result, taken = 0, [], set()
        for name in priority_docs:
            if name in taken:
                continue
            members = unit(name) - taken
            group = [f for f in ordered if f.document in members]
            group += [f for n in sorted(members) if n not in {g.document for g in group} for f in self.by_doc[n]]
            size = sum(len(f.text) for f in group)
            if used and used + size > budget:
                continue
            result.extend(group)
            taken |= members
            used += size
        # Present kept documents in the original priority order.
        result.sort(key=lambda f: (priority_docs.index(f.document) if f.document in priority_docs else len(priority_docs), f.start))
        # A linked supplement must not be silently dropped by the context budget.
        kept = {f.document for f in result}
        required = set()
        for name in kept:
            required.update(n for n in connected if self.doc_ids[name] & self.doc_ids[n])
            if "регламент согласования" in name.lower():
                required.update(n for n in connected if "регламент" in self.documents[n].text.lower())
        for name in sorted(required):
            existing_ids = {f.id for f in result}
            result.extend(f for f in self.by_doc[name] if f.id not in existing_ids)
        # Index windows are navigation aids, not publication units. Restore the
        # complete source blocks (blank/structural boundaries) before the model may select them.
        complete = {}
        for f in result:
            doc = self.documents[f.document]
            boundaries = self.paragraph_boundaries[doc.name]
            start = boundaries[max(0, bisect_right(boundaries, f.start) - 1)]
            end = boundaries[min(len(boundaries) - 1, bisect_left(boundaries, f.end))]
            if any(a < end and b > start for a, b in doc.quarantined):
                raise ValueError("unsafe_source_context")
            fid = hashlib.sha256(f"{doc.name}:{doc.sha256}:{start}:{end}".encode()).hexdigest()[:20]
            complete[fid] = Fragment(fid, doc.name, start, end, doc.text[start:end], f.heading)
        result = list(complete.values())
        # Restore dependency sources even when a narrow search window omitted
        # the introduction. They keep independent exact source coordinates.
        for f in list(result):
            for parent in self.dependencies(f):
                complete[parent.id] = parent
        result = list(complete.values())
        # Never silently cut an exception or an amendment to satisfy a hard cap.
        if len(result) > 512 or sum(len(f.text) for f in result) > 100000:
            raise ValueError("evidence_size_limit")
        return result

    def dependencies(self, fragment):
        """Return source-owned introductions required by a selected list item."""
        doc = self.documents[fragment.document]
        spans = {parent for (start, end), parent in self.list_parents[doc.name].items()
                 if start < fragment.end and end > fragment.start
                 and not (fragment.start <= parent[0] and fragment.end >= parent[1])}
        result = []
        for start, end in sorted(spans):
            fid = hashlib.sha256(f"{doc.name}:{doc.sha256}:{start}:{end}".encode()).hexdigest()[:20]
            result.append(Fragment(fid, doc.name, start, end, doc.text[start:end], ""))
        return result

    def complete_sources(self, sources, evidence):
        """Close a selected source set before semantic verification/publication."""
        by_id = {f.id: f for f in evidence}
        selected = {}
        for cite in sources:
            f = by_id[cite["fragment_id"]]
            for parent in self.dependencies(f):
                if parent.id not in by_id:
                    raise ValueError("missing_structural_source")
                selected[parent.id] = parent
            selected[f.id] = f
        return [{"fragment_id":f.id, "quote":f.text} for f in selected.values()]

    def evidence(self, fragments: list[Fragment]) -> list[dict]:
        return [{"id": f.id, "document": f.document, "text": f.text} for f in fragments]

    def reference_gaps(self, fragments):
        """Resolve explicit same-law article references against source headings.

        Unsupported reference forms are not guessed. This catalog does not
        establish legal applicability or absence outside the supplied corpus.
        """
        missing = defaultdict(set)
        for f in fragments:
            law = self.law_by_doc.get(f.document)
            if not law:
                continue
            for match in re.finditer(r"настоящего\s+(?:Федерального\s+закона|Кодекса)", f.text, re.I):
                prefix = f.text[max(0, match.start() - 400):match.start()]
                parts = re.findall(r"[а-яё]+|\d+(?:\.\d+)*|[^\w\s]", prefix, re.I)
                tail = []
                for token in reversed(parts):
                    if (re.fullmatch(r"\d+(?:\.\d+)*|[,–-]", token)
                            or re.fullmatch(r"пункт[а-яё]*|част[а-яё]*|стать[яеию]|и", token, re.I)):
                        tail.append(token)
                    else:
                        break
                chain = " ".join(reversed(tail))
                refs = set(re.findall(r"стать[яеию]\s+(\d+(?:\.\d+)?)", chain, re.I))
                missing[f.document].update(refs - self.article_catalog[law])
        return [{"document":name, "articles":sorted(articles, key=lambda x:tuple(map(int,x.split('.'))))}
                for name, articles in sorted(missing.items()) if articles]
