"""Element checks of a published free-text answer (section 14 corpora).

A case lists the elements its answer must contain and the statements it must
not make, taken from the documents and the organizer reference. The check is
deterministic and deliberately narrow: it proves the presence of key values,
clause numbers, polarity and phrases, not the full legal reasoning. Anything
it cannot decide is reported as not_evaluated, never as pass.

Element kinds:
  value     {"value": 450000 or null (any), "unit": "RUB"|"working_days"|"calendar_days"|"months"}
  clause    {"any": ["3.1"]}                 clause/article number cited in the text
  phrase    {"any": ["круглосуточ", ...]}    one alternative must occur (lowercase stem/regex)
  polarity  {"value": "да"|"нет"}            the answer opens with this word
Forbidden kinds: value (asserted, not refuted), phrase, polarity.
"""
from __future__ import annotations
import re
from evaluation.validators.prose import _REFUTED

STATUS_TEXTS = (
    ('technical_error', 'Не удалось проверить ответ из-за технической ошибки'),
    ('unverified', 'Не удалось получить достаточно проверенных оснований'),
    ('insufficient', 'В найденных документах недостаточно оснований'),
    ('out_of_scope', 'Я отвечаю на юридические вопросы по предоставленной базе'),
    ('disallowed', 'Я не могу помогать совершать противоправные действия'),
    ('clarify', 'Уточните'),
)
_SCALE = {'тыс': 10**3, 'млн': 10**6, 'миллион': 10**6, 'млрд': 10**9, 'миллиард': 10**9}
_NUMBER = re.compile(r'(?<![\w/.\-])(\d{1,3}(?:[   ]\d{3})+|\d+(?:[.,]\d+)?)(?![\w/\-]|[.,]\d)'
                     r'(?:\s*(тыс|млн|миллион\w*|млрд|миллиард\w*)\.?)?')
_UNIT = re.compile(r'\s*(?:\([^)]{0,60}\)\s*)?(?:(рабоч\w*)\s+(?:дн\w*|день)|(календарн\w*)\s+(?:дн\w*|день)'
                   r'|(месяц\w*|мес\.)|(руб\w*|₽))', re.I)


# "документов об увеличении до 500 000 рублей в базе нет": the value is named as absent, not asserted.
_ABSENT = re.compile(r'^[^.;!?]{0,80}?\b(?:нет|отсутству\w*|не\s+(?:найден\w*|представлен\w*|предусмотрен\w*|установлен\w*))', re.I)


def _refuted(text, start, end):
    return bool(_REFUTED.search(text[max(0, start - 16):start]) or _ABSENT.search(text[end:]))


def norm(text):
    return ' '.join(text.casefold().replace('ё', 'е').split())


def status_of(answer):
    """The solution's status as published; fixed application texts identify refusals."""
    text = answer.strip()
    for status, prefix in STATUS_TEXTS:
        if text.startswith(prefix):
            return status
    return 'answer' if text else 'empty'


# Small cardinal numbers in words, any case: "трёх рабочих дней", "пять рабочих дней".
_WORDS = [(r'одн\w*|один', 1), (r'дв(?:а|е|ух|ум|умя)', 2), (r'тр(?:и|[её]х|[её]м|емя)', 3), (r'четыр\w*', 4),
          (r'пят(?:ь|и|ью)', 5), (r'шест(?:ь|и|ью)', 6), (r'сем(?:ь|и|ью)', 7), (r'вос[ье]м(?:ь|и|ью)', 8),
          (r'девят(?:ь|и|ью)', 9), (r'десят(?:ь|и|ью)', 10)]
_WORD_NUMBER = re.compile(r'(?<![\w-])(' + '|'.join(w for w, _ in _WORDS) + r')(?![\w-])', re.I)


def _word_value(word):
    return next(v for w, v in _WORDS if re.fullmatch(w, word, re.I))


def values(text):
    """(value, unit, refuted) for every number (digits or a small number word) followed by a known unit."""
    found = []
    for m in _WORD_NUMBER.finditer(text):
        unit_match = _UNIT.match(text, m.end())
        if unit_match:
            unit = ('working_days', 'calendar_days', 'months', 'RUB')[[g is not None for g in unit_match.groups()].index(True)]
            found.append((_word_value(m.group(1)), unit, _refuted(text, m.start(), unit_match.end())))
    for m in _NUMBER.finditer(text):
        unit_match = _UNIT.match(text, m.end())
        if not unit_match:
            continue
        unit = ('working_days', 'calendar_days', 'months', 'RUB')[[g is not None for g in unit_match.groups()].index(True)]
        raw = re.sub(r'[   ]', '', m.group(1)).replace(',', '.')
        number = float(raw)
        if m.group(2):
            number *= next(v for k, v in _SCALE.items() if m.group(2).startswith(k))
        refuted = _refuted(text, m.start(), unit_match.end())
        found.append((int(number) if number.is_integer() else number, unit, refuted))
    return found


def opening(text):
    m = re.match(r'\s*[«"]?(да|нет)\b', norm(text))
    return m.group(1) if m else None


def has(element, text, found):
    kind = element['kind']
    if kind == 'value':
        # value null: any asserted value in this unit (e.g. an amount the base does not contain).
        return any((element['value'] is None or v == element['value']) and u == element['unit'] and not r for v, u, r in found)
    if kind == 'clause':
        return any(re.search(r'(?<![\d.])' + re.escape(c) + r'(?![\d]|\.\d)', text) for c in element['any'])
    if kind == 'phrase':
        return any(re.search(p, norm(text)) for p in element['any'])
    if kind == 'polarity':
        return opening(text) == element['value']
    raise ValueError('unknown element kind: ' + kind)


def check(case, answer):
    """Return dict(outcome=pass|fail|not_evaluated|system_error, status, failures, not_evaluated)."""
    status = status_of(answer)
    if status == 'technical_error':
        return dict(outcome='system_error', status=status, failures=['system_error'], not_evaluated=[])
    failures, unknown = [], []
    if status not in case['allowed_statuses']:
        answerable = 'answer' in case['allowed_statuses']
        failures.append('false_refusal' if answerable and status != 'answer' else 'wrong_status')
    found = values(answer)
    if status == 'answer':
        for element in case.get('required', []):
            if not has(element, answer, found):
                if element['kind'] == 'polarity' and opening(answer) is None:
                    unknown.append('polarity_not_stated')
                else:
                    failures.append('missing:' + element.get('id', element['kind']))
    for element in case.get('forbidden', []):
        if has(element, answer, found):
            failures.append('forbidden:' + element.get('id', element['kind']))
    outcome = 'fail' if failures else 'not_evaluated' if unknown else 'pass'
    return dict(outcome=outcome, status=status, failures=sorted(set(failures)), not_evaluated=sorted(set(unknown)))
