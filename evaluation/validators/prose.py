"""Deterministic reading of a published prose answer against independent gold.

Bounded to the synthetic fact schema (payment/review/archive terms, reserve
limit, notification duty). The reader returns True only when every required
fact is asserted as the conclusion with the same value, unit and subject and
its condition and start event are mentioned; False only for a proven
contradiction; None (not evaluated) otherwise. Unrecognized wording is never
accepted and never declared false.

A value counts as *asserted* unless its context marks it as refuted
("а не 999") or conditional ("применяется при подписании акта до ...",
"если ...", "не распространяется"). Explanations of non-applicable rules are
therefore neither credited nor penalized.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

KEYWORDS = {
    'payment_term': r'срок\w*\s+оплат',
    'review_term': r'срок\w*\s+согласовани',
    'archive_term': r'срок\w*\s+хранени',
    'limit': r'лимит\w*\s+резерв',
    'duty': r'обязанност\w*\s+(?:по\s+)?уведомлени',
}
UNITS = {'payment_term': {'calendar_days', 'working_days'}, 'review_term': {'working_days'},
         'archive_term': {'working_days'}, 'limit': {'RUB'}, 'duty': {'boolean'}}
NO_CONDITION = 'без исключений'
# Subject matter of each predicate ("Оплата: ...", "Согласование: ...").
TOPICS = {'payment_term': r'оплат', 'review_term': r'согласовани', 'archive_term': r'хранени',
          'limit': r'резерв', 'duty': r'уведомлени'}

_NUMBER = re.compile(r'(?<![\w/.\-])(\d{1,3}(?:[   ]\d{3})+|\d+)(?![\w/\-]|[.,]\d)')
_UNIT = re.compile(r'\s*(?:(календарн\w*)\s+(?:дн\w*|день)|(рабоч\w*)\s+(?:дн\w*|день)|(руб\w*|₽))', re.I)
_ASSERTING_VERB = re.compile(r'(?:составля\w*|равн\w*|—|–|-)\s*$', re.I)
_REFUTED = re.compile(r'(?:\bа\s+не|\bне\s+(?:равн\w*|раве\w*|составля\w*)|\bвместо|\bне)\s*$', re.I)
_CONDITIONAL = re.compile(
    r'\bесли\b|\bпри\s+подписани|\bприменя\w*\s+(?:при|к|для|до|с)\b|\bдейству\w*\s+(?:при|до|с|для)\b'
    r'|\bне\s+(?:применя|распространя|действу)|\bначиная\s+с\b|\bдо\s+\d{4}-\d{2}-\d{2}'
    r'|\bранее\b|\bпрежн\w*|\bотносится\s+к\b|\bустановлен\w*\s+(?:при|для)\b'
    r'|\bне\s+наступ|(?<!\bот\s)\bс\s+\d{4}-\d{2}-\d{2}', re.I)
_CLAUSE = re.compile(r'[;:]|,\s+(?=(?:а|но|если|поскольку|так как|потому что|когда|который|которая|которое)\b)', re.I)
# A digit after a period continues the sentence: "п. 1", "ст. 5".
_SENTENCE = re.compile(r'(?<=[.!?])\s+(?=[«"(]?[А-ЯЁA-Z])')
_SUBJECT = re.compile(r'\b[А-ЯЁA-Z]{1,4}-\d{1,4}/\d{4}(?:-[А-ЯЁA-Z])?(?![\w/])')
_DUTY_FALSE = re.compile(r'\bне\s+возника\w*|\bне\s+возникнет|\bотсутству\w*\s+обязанност', re.I)
_DUTY_TRUE = re.compile(r'\bвозника\w*|\bвозникнет', re.I)
_STOP = {'при', 'для', 'без', 'или', 'это', 'его', 'она', 'они', 'что'}


@dataclass
class Mention:
    sentence: int
    position: int
    value: object
    unit: str | None
    status: str          # asserted | refuted | conditional
    predicate: str | None
    clause: str = ''     # the clause holding the value, citations in brackets removed


_ABBREVIATION = re.compile(r'(?:^|[\s(«"])(?:п|пп|ст|ч|гл|разд|см|абз|подп)\.$', re.I)
# A value named and then denied: "999 календарных дней не подтверждается".
_DENIED_AFTER = re.compile(r'^[^.;:!?]{0,20}?\b(?:не\s+подтвержда\w*|не\s+соответству\w*|неверн\w*|ошибочн\w*)', re.I)


def _sentences(text):
    """Split on sentence ends; "п.", "ст." and similar abbreviations never end one."""
    parts = [s for s in _SENTENCE.split(' '.join(text.split())) if s.strip()]
    merged = []
    for part in parts:
        if merged and _ABBREVIATION.search(merged[-1]):
            merged[-1] += ' ' + part
        else:
            merged.append(part)
    return merged


def _clauses(sentence):
    """(start, end, conditional) spans; a clause followed by "если ..." is conditional."""
    cuts = [0] + [m.end() for m in _CLAUSE.finditer(sentence)] + [len(sentence) + 1]
    spans = [(cuts[i], cuts[i + 1] - 1) for i in range(len(cuts) - 1)]
    result = []
    for i, (a, b) in enumerate(spans):
        text = sentence[a:b]
        following = sentence[spans[i + 1][0]:spans[i + 1][1]].lstrip() if i + 1 < len(spans) else ''
        result.append((a, b, bool(_CONDITIONAL.search(text) or re.match(r'если\b', following, re.I))))
    return result


def _predicate_at(sentence, position, unit, required):
    """Nearest preceding keyword, else a later one, else the only compatible required predicate."""
    found = []
    for predicate, pattern in KEYWORDS.items():
        for m in re.finditer(pattern, sentence, re.I):
            found.append((m.start(), predicate))
    before = [p for start, p in sorted(found) if start < position and unit in UNITS[p]]
    after = [p for start, p in sorted(found) if start >= position and unit in UNITS[p]]
    if before:
        return before[-1]
    if after:
        return after[0]
    compatible = {f['predicate'] for f in required if unit in UNITS[f['predicate']]}
    return compatible.pop() if len(compatible) == 1 else None


def mentions(prose, required):
    result = []
    for si, sentence in enumerate(_sentences(prose)):
        clauses = _clauses(sentence)
        def status(position):
            before = sentence[max(0, position - 16):position]
            if _REFUTED.search(before):
                return 'refuted'
            for a, b, conditional in clauses:
                if a <= position < b + 1:
                    return 'conditional' if conditional else 'asserted'
            return 'asserted'
        def clause_text(position):
            for a, b, _ in clauses:
                if a <= position < b + 1:
                    return re.sub(r'\([^()]*\)', ' ', sentence[a:b])
            return sentence
        for m in _NUMBER.finditer(sentence):
            u = _UNIT.match(sentence, m.end())
            unit = None
            if u:
                unit = 'calendar_days' if u.group(1) else 'working_days' if u.group(2) else 'RUB'
            state = status(m.start())
            if u and _DENIED_AFTER.search(sentence[u.end():]):
                state = 'refuted'
            # A bare number is a value only when asserted by a verb/dash or refuted.
            if unit is None and state != 'refuted' and not _ASSERTING_VERB.search(sentence[max(0, m.start() - 14):m.start()]):
                continue
            value = int(re.sub(r'\D', '', m.group(1)))
            predicate = _predicate_at(sentence, m.start(), unit, required) if unit else None
            if unit is None:
                # Unit-less refuted/asserted numbers attach to the nearest keyword.
                predicate = next((p for p in KEYWORDS if re.search(KEYWORDS[p], sentence[:m.start()], re.I)), None)
            result.append(Mention(si, m.start(), value, unit, state, predicate, clause_text(m.start())))
        for m in re.finditer(KEYWORDS['duty'], sentence, re.I):
            tail = sentence[m.end():]
            false, true = _DUTY_FALSE.search(tail), _DUTY_TRUE.search(tail)
            head = sentence[:m.start()]
            false = false or _DUTY_FALSE.search(head)
            if false or true:
                position = m.start()
                result.append(Mention(si, position, not bool(false), 'boolean', status(position), 'duty', clause_text(position)))
    return result


def _present(phrase, text):
    """Every content word of phrase occurs in text up to an inflectional ending.

    The compared prefix is fixed by the gold word (at most 5 letters, without
    its last letter), so a short unrelated word cannot shrink it.
    """
    words = [w for w in re.findall(r'[а-яёa-z]+', phrase.casefold().replace('ё', 'е')) if len(w) >= 3 and w not in _STOP]
    pool = re.findall(r'[а-яёa-z]+', text.casefold().replace('ё', 'е'))
    def match(w):
        k = min(5, len(w) - 1)
        return any(len(p) >= k and p[:k] == w[:k] for p in pool)
    return all(match(w) for w in words)


def _conclusion_in_condition(own, sentences, event_date):
    """The only value stated with "составляет/равен/—" inside a condition clause
    is the conclusion when the event date of the question is named in that or
    the next sentence ("…начиная с X составляет 60 дней. Акт от Y подпадает…").
    Two such values stay ambiguous."""
    if not event_date:
        return []
    picked = []
    for m in own:
        if m.status != 'conditional':
            continue
        sentence = sentences[m.sentence]
        head = sentence[max(0, m.position - 16):m.position]
        near = ' '.join(sentences[m.sentence:m.sentence + 2])
        if _ASSERTING_VERB.search(head) and event_date in near:
            picked.append(m)
    return picked if len({(m.value, m.unit) for m in picked}) == 1 else []


def evaluate_prose(prose, case):
    """Return (True|False|None, reasons). Reasons explain False or None."""
    expected = case['expected']
    if expected.get('issue') == 'conflict' or 'event_date' in expected.get('missing', []):
        return None, ['conditional_or_conflict_explanation_requires_manual_review']
    required = [r['fact'] for r in expected['required_claims']]
    if not required:
        return None, ['published_prose_semantics']
    found = mentions(prose, required)
    sentences = _sentences(prose)
    failures, unknown = [], []
    for f in required:
        own = [m for m in found if m.predicate == f['predicate']]
        # A value stated about another object ("касается объекта КТ-7/2026-Б")
        # is neither the conclusion nor a contradiction.
        aside = lambda m: bool(_SUBJECT.findall(m.clause)) and f['subject_id'] not in _SUBJECT.findall(m.clause)
        asserted = [m for m in own if m.status == 'asserted']
        # Only an aside next to a conclusion about the asked object; a lone
        # value about another object still fails as a wrong subject.
        if any(not aside(m) for m in asserted):
            asserted = [m for m in asserted if not aside(m)]
            own = [m for m in own if not aside(m)]
        if not asserted:
            asserted = _conclusion_in_condition(own, sentences, case.get('event_date'))
        if not asserted:
            unknown.append('prose_conclusion_not_identified')
            continue
        first = min(asserted, key=lambda m: (m.sentence, m.position))
        if first.value != f['value'] or (first.unit and first.unit != f['unit']):
            failures.append('prose_wrong_value_or_unit')
        if any(m.value != first.value or (m.unit and m.unit != first.unit) for m in asserted[1:]):
            failures.append('prose_contradictory_values')
        subjects = set(_SUBJECT.findall(first.clause))
        if subjects and f['subject_id'] not in subjects:
            failures.append('prose_wrong_subject')
        # Condition and start event belong to this fact: the conclusion sentence,
        # the next one, or a sentence naming the same subject matter.
        topic = TOPICS[f['predicate']]
        scope = ' '.join(s for i, s in enumerate(sentences)
                         if i in (first.sentence, first.sentence + 1) or re.search(topic, s, re.I))
        if f['condition'] != NO_CONDITION and not _present(f['condition'], scope):
            failures.append('prose_lost_condition')
        if not _present(f['start_event'], scope):
            failures.append('prose_lost_start_event')
    for bad in expected['forbidden_claims']:
        for m in found:
            if (m.status == 'asserted' and m.predicate == bad.get('predicate') and m.value == bad.get('value')
                    and (m.unit is None or 'unit' not in bad or m.unit == bad['unit'])):
                failures.append('prose_forbidden_value')
    if failures:
        return False, sorted(set(failures))
    if unknown:
        return None, ['published_prose_semantics'] + sorted(set(unknown))
    return True, []
