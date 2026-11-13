"""Lexical baseline: BM25 with word-prefix features and source-context expansion.

No demo answers, question IDs, or expected answers are used by this module.
Prefix features are a baseline, not a Russian morphological analyser.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
from bisect import bisect_right, bisect_left
import heapq
import itertools
import math
import operator
import sys
import threading
import time
import re
from psb_corpus import Document, Fragment, check_deadline
from psb_llm import ProviderError

ORG_FORMS = {"ооо", "ао", "пао", "зао", "оао", "ип", "нко", "фгуп", "муп"}
STOP = set("и в во на по с со у к ко из за от до для не ли мы вы он она они это как какой какая какие что сколько нужно можно чем при а или его ее их нам нас наш этот того если будет было есть меня мне теперь".split())
DATE_DEFINITION = re.compile(
    r'\bдатой\s+([а-яё]+(?:\s+[а-яё]+){0,2}?)\s+(?:считается|является|признаётся|признается)\b', re.I)
UPPER_BOUND = re.compile(
    r'\b(?:(?:срок|период|продолжительность)\s+)?([а-яё]{5,})\s+не\s+'
    r'(?:может\s+превышать|превышает)\b', re.I)
CONDITIONAL_BOUND = re.compile(r'^\s*(?:\d+(?:\.\d+)*[.)]\s*)?(?:при|если|для|в\s+случае)\b', re.I)
TIME_UNIT = re.compile(r'\b(?:дн\w*|ден[ьья]|недел\w*|месяц\w*|год\w*|лет|час\w*|минут\w*)\b', re.I)


def date_term(text):
    return ' '.join(text.lower().replace('ё', 'е').split())


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


# --- Dates of validity and of the event (deterministic, unambiguous forms only) ---
MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
          "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
_DAY = (r"(?<![\d.\-])(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\s+(?:январ|феврал|март|апрел|ма|июн|июл|август|"
        r"сентябр|октябр|ноябр|декабр)[а-я]*\s+\d{4})")
# Article and point references in any case form: «статье 114», «ст. 41»,
# «пункту 4 статьи 114», «п. 3.1».
ARTICLE_REF = re.compile(r"(?<![а-яё])(?:стать[а-яё]*|ст\.)\s*(\d+(?:\.\d+)*)", re.I)
# «пункт 4», «п. 4», «часть 1», «ч. 1»: a part of a code article is numbered like a point.
POINT_REF = re.compile(r"(?<![а-яё])(?:пункт[а-яё]*|п\.|част[ьию][а-яё]*|ч\.)\s*(\d+(?:\.\d+)*)", re.I)
POINT_OF_ARTICLE = re.compile(r"(?<![а-яё])(?:пункт[а-яё]*|п\.|част[ьию][а-яё]*|ч\.)\s*(\d+(?:\.\d+)*)\s+(?:стать[а-яё]*|ст\.)\s*(\d+(?:\.\d+)*)", re.I)
# The opening line of a numbered point of a long article: its table of contents.
OUTLINE_POINT = re.compile(r"\s*\d{1,3}(?:\.\d{1,3})?\.\s")
CODE_REF = re.compile(r"\b(?:НК|ТК|ГК|ЖК|БК|УК|КоАП)\b|\b(?:налогов|трудов|гражданск|жилищн|бюджетн|уголовн)[а-яё]*\s+кодекс", re.I)
CODE_NAMES = {"нк": "налоговый", "тк": "трудовой", "гк": "гражданский", "жк": "жилищный", "бк": "бюджетный", "ук": "уголовный"}
VALID_FROM = re.compile(r"(?:начиная\s+с|^\s*действует\s+с|\.\s*действует\s+с)\s+" + _DAY + r"(?:\s*г\.?)?(?!\s*\(не)", re.I | re.M)
VALID_UNTIL = re.compile(r"\bдо\s+" + _DAY + r"(?:\s*г\.?)?\s*\(не\s+включая", re.I)
LOST_FORCE = re.compile(r"утратил[аио]?\s+силу\s+с\s+" + _DAY, re.I)


def parse_day(text):
    """A calendar date from ISO, dd.mm.yyyy or "1 августа 2024"; None if invalid."""
    import datetime
    text = text.casefold()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.date.fromisoformat(text)
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
        if m:
            return datetime.date(int(m[3]), int(m[2]), int(m[1]))
        m = re.fullmatch(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})", text)
        if m:
            month = next((n for stem, n in sorted(MONTHS.items(), key=lambda x: -len(x[0])) if m[2].startswith(stem)), None)
            return datetime.date(int(m[3]), month, int(m[1])) if month else None
    except ValueError:
        return None
    return None


def event_interval(question: str):
    """(first, last) day of the event named in the latest user turn that names one.

    Only an unambiguous date counts: exactly one full date, otherwise exactly one
    "в августе 2024". A document reference ("договор от 12.02.2024") and the
    current moment ("сейчас декабрь 2026") are not events."""
    import calendar, datetime
    for turn in reversed(user_turns(question)):
        days = {parse_day(m[1]) for m in re.finditer(_DAY, turn, re.I)
                if not re.search(r"\bот\s*$", turn[:m.start()])} - {None}
        if len(days) == 1:
            day = days.pop()
            return day, day
        if days:
            return None
        # Month and year of a full date ("от 12 февраля 2024") are not a separate event.
        turn = re.sub(_DAY, " ", turn, flags=re.I)
        months = {(int(m[2]), next(n for stem, n in sorted(MONTHS.items(), key=lambda x: -len(x[0])) if m[1].casefold().startswith(stem)))
                  for m in re.finditer(r"(?<!сейчас\s)\b(январ|феврал|март|апрел|ма[йея]|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-я]*\s+(\d{4})",
                                       turn, re.I)
                  if not re.search(r"сейчас\s*$", turn[:m.start()], re.I)}
        if len(months) == 1:
            year, month = months.pop()
            return datetime.date(year, month, 1), datetime.date(year, month, calendar.monthrange(year, month)[1])
        if months:
            return None
    return None


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
        # Contextual index text: a fragment cut from a long article keeps the
        # article title it belongs to ("Статья 164. Налоговые ставки").
        titles = {d.name: [(m.start(), m.group().strip()[:200]) for m in
                           re.finditer(r"(?m)^\s*Статья\s+\d+(?:\.\d+)*\.?[^\n]*", d.text)] for d in documents}
        self.context_titles = {}
        for index, f in enumerate(fragments):
            check_deadline(deadline)
            self.by_doc[f.document].append(f)
            title = next((t for start, t in reversed(titles.get(f.document, [])) if start <= f.start), "")
            if title and title in f.text:
                title = ""
            self.context_titles[f.id] = title
            c = Counter(tokens(f.document.replace("_", " ") + " " + title + " " + f.text))
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
        # Explicit definitions from the same document only. A date mentioned in
        # another contract must not supply the start event for this one.
        self.date_definitions = defaultdict(lambda: defaultdict(set))
        self.conditional_bounds = defaultdict(lambda: defaultdict(set))
        for d in documents:
            boundaries = self.paragraph_boundaries[d.name]
            for start, end in zip(boundaries, boundaries[1:]):
                check_deadline(deadline)
                if any(a < end and b > start for a, b in d.quarantined):
                    continue
                block = d.text[start:end]
                for m in DATE_DEFINITION.finditer(block):
                    self.date_definitions[d.name][date_term(m[1])].add((start, end))
                if CONDITIONAL_BOUND.search(block) and TIME_UNIT.search(block):
                    for m in UPPER_BOUND.finditer(block):
                        self.conditional_bounds[d.name][date_term(m[1])[:5]].add((start, end))
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
        # Document roles come from the text, so another naming scheme works the
        # same. A regulation names itself in a heading line ("РЕГЛАМЕНТ
        # СОГЛАСОВАНИЯ ДОГОВОРОВ ..."); its family is every edition with the same
        # title and every non-law document that cites that title.
        keys = {}
        for d in documents:
            if d.name in self.law_by_doc:
                continue
            for line in [line for line in d.text.splitlines() if line.strip()][:3]:
                words = re.findall(r"[а-яё]+", line.casefold().replace("ё", "е"))
                if words and words[0] == "регламент" and len(words) >= 2:
                    # The title ends before the organization form: "РЕГЛАМЕНТ ЗАКУПОК ООО ...".
                    title = list(itertools.takewhile(lambda w: w not in ORG_FORMS, words))[:3]
                    if len(title) >= 2:
                        keys[d.name] = tuple(w[:5] for w in title)
                        break
        self.regulations = set(keys)
        self.regulation_family = {}
        for name, key in keys.items():
            cited = re.compile(r"\b" + r"\w*\s+".join(map(re.escape, key)) + r"\w*", re.I)
            self.regulation_family[name] = {n for n, d in self.documents.items() if n not in self.law_by_doc
                                            and (keys.get(n) == key or cited.search(d.text.replace("ё", "е")))}
        self.parties = {d.name: {x.casefold().replace(" ", "-") for x in
                        re.findall(r"«([^»\n]{2,80})»", d.text[:1200])} for d in documents}

    # --- Optional dense candidates (EMB_MODEL through the organizer proxy) ---
    dense = None
    vectors = None

    def enable_dense(self, client, deadline: float) -> str:
        """Embed every fragment; on any failure keep lexical search only.

        Returns an application-owned status code for the run log."""
        texts = [(f.heading + "\n" + f.text if f.heading and f.heading not in f.text else f.text)[:2000]
                 for f in self.fragments]
        # The first chunk shows the provider's speed: if the whole corpus would
        # not fit the budget, stop now instead of spending the budget for nothing.
        vectors, chunk, started = [], 128, time.monotonic()
        try:
            for start in range(0, len(texts), chunk):
                vectors += client.embed(texts[start:start + chunk], deadline=deadline)
                elapsed = time.monotonic() - started
                if len(vectors) < len(texts) and started + elapsed / len(vectors) * len(texts) > deadline:
                    return "dense_disabled:embedding_too_slow"
        except ProviderError as error:
            return "dense_disabled:" + str(error)
        if len(vectors) != len(self.fragments):
            return "dense_disabled:invalid_embedding_response"
        # Searches in other threads read self.vectors: the lock and cache exist first.
        self._query_vectors, self._dense_lock, self._dense_failed = {}, threading.Lock(), False
        self.dense = client
        self.vectors = vectors
        return "dense_enabled"

    def validity(self, fragment):
        """(valid_from inclusive, valid_until exclusive) stated for this provision or
        in the header of its document; None where nothing unambiguous is stated.

        Laws are given in their current edition only; dates inside them are
        transitional provisions, not the validity of the provision."""
        start = end = None
        if fragment.document in self.law_by_doc:
            return start, end
        m = VALID_FROM.search(fragment.text)
        if m:
            start = parse_day(m[1])
        m = VALID_UNTIL.search(fragment.text)
        if m:
            end = parse_day(m[1])
        header = "\n".join([line for line in self.documents[fragment.document].text.splitlines() if line.strip()][:5])
        if start is None:
            m = VALID_FROM.search(header)
            start = parse_day(m[1]) if m else None
        if end is None:
            m = LOST_FORCE.search(header)
            end = parse_day(m[1]) if m else None
        return start, end

    def _dense_candidates(self, text: str, count: int) -> list[Fragment]:
        if self.vectors is None or self._dense_failed or count <= 0:
            return []
        with self._dense_lock:
            vector = self._query_vectors.get(text)
        if vector is None:
            try:
                vector = self.dense.embed([text])[0]
            except ProviderError:
                # A query-time failure is not a missing provision: lexical search continues.
                with self._dense_lock:
                    self._dense_failed = True
                print("dense_query_failed", file=sys.stderr)
                return []
            with self._dense_lock:
                if len(self._query_vectors) < 4096:
                    self._query_vectors[text] = vector
        best = heapq.nlargest(count, range(len(self.vectors)),
                              key=lambda i: sum(map(operator.mul, vector, self.vectors[i])))
        return [self.fragments[i] for i in best]

    # --- Optional reranker (RERANKER_MODEL through the organizer proxy) ---
    reranker = None

    def enable_rerank(self, client) -> str:
        self._rerank_lock, self._rerank_failed = threading.Lock(), False
        self.reranker = client
        return "rerank_enabled"

    def _rerank_candidates(self, text: str, pool: list[Fragment], count: int) -> list[Fragment]:
        """The reranker's best fragments of a candidate pool below the lexical hits."""
        if self.reranker is None or self._rerank_failed or not pool or count <= 0:
            return []
        documents = [((self.context_titles.get(f.id) or "") + "\n" + f.text)[:1500].strip() for f in pool]
        try:
            order = self.reranker.rank(text, documents)
        except ProviderError:
            with self._rerank_lock:
                self._rerank_failed = True
            print("rerank_failed", file=sys.stderr)
            return []
        return [pool[i] for i in order[:count]]

    def _scores(self, query):
        scores = defaultdict(float)
        for word, weight in query.items():
            check_deadline(self.deadline)
            for index, frequency in self.postings.get(word, ()):
                scores[index] += weight * self.idf[word] * frequency * 2.5 / (
                    frequency + 1.5 * (.25 + .75 * self.lengths[index] / self.avg))
        return scores

    def _article_fragments(self, current: str, articles: list[str], bound) -> list[Fragment]:
        """Heading and named points of each article the question names."""
        if not articles:
            return []
        codes = {CODE_NAMES[m.group(0).casefold()] for m in CODE_REF.finditer(current) if m.group(0).casefold() in CODE_NAMES}
        result = []
        for number in articles:
            heading = re.compile(r"\s*Статья\s+" + re.escape(number) + r"(?![\d.]\d)", re.I)
            docs = [d for d in self.law_by_doc if any(heading.match(f.text) for f in self.by_doc[d])]
            if codes:
                docs = [d for d in docs if self.law_by_doc[d].split()[0] in codes] or docs
            for d in sorted(docs)[:2]:
                result.extend(f for f in self.by_doc[d] if heading.match(f.text))
                for point, article, _ in bound:
                    if article == number:
                        mark = re.compile(re.escape(point) + r"[.)]\s")
                        # The point and its continuation paragraphs (a sanction
                        # «влечет наложение штрафа …» follows its part separately).
                        result.extend(f for f in self.by_doc[d]
                                      if mark.match(f.text) or mark.match(getattr(f, "heading", "") or ""))
        return result

    def search(self, question: str, top_k: int = 6, expanded: bool = False) -> list[Fragment]:
        turns = user_turns(question)
        current = turns[-1]
        query = Counter(tokens(current))
        for turn in turns[:-1]:
            for token in tokens(turn):
                query[token] += .35
        ids = set()
        parties = set()
        for turn in reversed(turns):
            if not ids:
                ids = identifiers(turn)
            if not parties:
                # Every party the latest turn naming any names, matched as whole
                # words: «Альфа-Трейд» is not found inside «Альфа-Трейдинг», and no
                # choice depends on set order (the hash seed).
                known = set().union(*self.parties.values())
                normalized = turn.casefold().replace(" ", "-")
                parties = {name for name in known if re.search(r"(?<![а-яa-z])" + re.escape(name) + r"(?![а-яa-z])", normalized)}
        # «пункт 4 статьи 114» is point 4 of article 114, not every «4.» of the
        # base; articles and points are read in any case form.
        bound = [(m.group(1), m.group(2), m.span()) for m in POINT_OF_ARTICLE.finditer(current)]
        bound_spans = [span for _, _, span in bound]
        articles = list(dict.fromkeys([n for _, n, _ in bound] + ARTICLE_REF.findall(current)))[:4]
        points = [m.group(1) for m in POINT_REF.finditer(current)
                  if not any(a <= m.start() < b for a, b in bound_spans)]
        clause_numbers = list(dict.fromkeys(points + articles))
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
            if parties & self.parties[f.document]:
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
        # Dense candidates find a provision worded differently from the question.
        # They are reserved places, so the lexical order of the hits is unchanged.
        for f in self._dense_candidates("\n".join(turns[-2:]), 4 if expanded else 2):
            if f.id not in existing:
                hits.append(f)
                existing.add(f.id)
        # The reranker reads the next lexical candidates and rescues the most
        # relevant ones; it never removes a hit.
        pool = [f for score, f in scored[:30] if score > 0 and f.id not in existing]
        for f in self._rerank_candidates("\n".join(turns[-2:]), pool, 4 if expanded else 2):
            if f.id not in existing:
                hits.append(f)
                existing.add(f.id)
        # A document named by its identifier («П-17/2024 … и ПТ-05/2023») has a
        # reserved place, so a comparison keeps every named contract.
        covered = set().union(*(self.doc_ids[f.document] for f in hits)) if hits else set()
        for named in sorted(ids - covered):
            best = next((f for score, f in scored if score > 0 and named in self.doc_ids[f.document]), None)
            if best is not None and best.id not in existing:
                hits.append(best)
                existing.add(best.id)
        # A named article has a reserved place: its heading and the named points,
        # however long and similarly worded another named article is.
        for f in self._article_fragments(current, articles, bound):
            if f.id not in existing:
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
            if name in self.regulations:
                connected.update(self.regulation_family[name])
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
                # A long law article also brings its table of contents: the short
                # opening line of each numbered point. A general rule («по ставке
                # 22 процента в случаях, не указанных в пунктах 1, 2 и 4») is not
                # outranked by dozens of fragments on the special cases.
                if hit.document in self.law_by_doc:
                    for f in [f for f in siblings if OUTLINE_POINT.match(f.text) and len(f.text) <= 400][:24]:
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
            if name in self.regulations:
                members |= self.regulation_family[name] & connected
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
            if name in self.regulations:
                required.update(self.regulation_family[name] & connected)
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
        pending = list(result)
        for f in pending:
            for parent in self.dependencies(f):
                if parent.id not in complete:
                    complete[parent.id] = parent
                    pending.append(parent)
                    if len(complete) > 512:
                        raise ValueError("evidence_size_limit")
        result = list(complete.values())
        # Never silently cut an exception or an amendment to satisfy a hard cap.
        if len(result) > 512 or sum(len(f.text) for f in result) > 100000:
            raise ValueError("evidence_size_limit")
        return result

    def date_dependencies(self, fragment, *, include_contained=False):
        """Exact definitions needed by an explicit 'с/от даты <event>' reference."""
        text = date_term(fragment.text)
        spans = set()
        for term, definitions in self.date_definitions[fragment.document].items():
            if re.search(r'\b(?:с|от)\s+даты\s+' + re.escape(term) + r'\b', text):
                spans.update(definitions)
        return self._dependency_fragments(fragment, spans, include_contained=include_contained)

    def bound_dependencies(self, fragment, *, include_contained=False):
        """Keep explicit conditional upper bounds for the same named duration.

        This narrow same-document construction does not infer arbitrary legal
        exceptions. The complete clauses still require applicability review.
        """
        if not TIME_UNIT.search(fragment.text):
            return []
        spans = set()
        for m in UPPER_BOUND.finditer(fragment.text):
            spans.update(self.conditional_bounds[fragment.document][date_term(m[1])[:5]])
        return self._dependency_fragments(fragment, spans, include_contained=include_contained)

    def publication_context(self, fragment):
        return (self.date_dependencies(fragment, include_contained=True)
                + self.bound_dependencies(fragment, include_contained=True))

    def _dependency_fragments(self, fragment, spans, *, include_contained=False):
        doc = self.documents[fragment.document]
        result = []
        for start, end in sorted(spans):
            if not include_contained and fragment.start <= start and fragment.end >= end:
                continue
            fid = hashlib.sha256(f"{doc.name}:{doc.sha256}:{start}:{end}".encode()).hexdigest()[:20]
            result.append(Fragment(fid, doc.name, start, end, doc.text[start:end], ""))
        return result

    def dependencies(self, fragment):
        """Source-owned introductions, date definitions and conditional bounds."""
        doc = self.documents[fragment.document]
        spans = {parent for (start, end), parent in self.list_parents[doc.name].items()
                 if start < fragment.end and end > fragment.start
                 and not (fragment.start <= parent[0] and fragment.end >= parent[1])}
        return (self._dependency_fragments(fragment, spans) + self.date_dependencies(fragment)
                + self.bound_dependencies(fragment))

    def complete_sources(self, sources, evidence):
        """Close a selected source set before semantic verification/publication."""
        by_id = {f.id: f for f in evidence}
        selected = {}
        visiting = set()
        def add(f):
            if f.id in selected or f.id in visiting:
                return
            visiting.add(f.id)
            if len(visiting) > 6:
                raise ValueError("structural_source_limit")
            for parent in self.dependencies(f):
                if parent.id not in by_id:
                    raise ValueError("missing_structural_source")
                add(by_id[parent.id])
            selected[f.id] = f
            visiting.remove(f.id)
            if len(selected) > 6:
                raise ValueError("structural_source_limit")
        for cite in sources:
            add(by_id[cite["fragment_id"]])
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
