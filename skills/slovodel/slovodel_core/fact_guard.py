"""A8 deterministic *risk screening* of edits, not semantic equivalence.

Rules 2.0 (Core 0.8.0) separate two severities:

* ``blocker`` — a detected protected fact changed (amounts, numbers written in
  digits or words, codes, dates, weekdays/months, names, links, polarity or
  modality flips, guarantees, number-to-word bindings, protected phrases).
  Publication stays blocked until a human confirms the change.
* ``review`` — wording that often carries conditions or scope changed
  (если/только/после…, все/большинство…). A person must check it, but a
  paraphrase alone does not block the draft.

Reports never reveal the original values, names, URLs or text.
"""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from collections import Counter
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from . import __version__

VERSION = "a8-rules-2.0"
NUM = r"(?:\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,]\d+)?"
URL = re.compile(r"(?i)(?<!\w)(?:https?://|www\.)[^\s<>\"'«»]+")
EMAIL = re.compile(r"(?iu)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-zа-яё]{2,}")
MONEY = re.compile(
    rf"(?iu)(?<!\w)(?P<number>{NUM})\s*(?P<scale>тыс\.?|тысяч(?:а|и)?|млн\.?|миллион(?:а|ов)?)?\s*"
    r"(?P<currency>₽|руб(?:\.|ль|ля|лей)?|USD|EUR|\$|€)(?!\w)"
)
MONEY_PREFIX = re.compile(
    rf"(?iu)(?<!\w)(?P<currency>₽|USD|EUR|\$|€)\s*(?P<number>{NUM})(?!\w)"
)
DATE = re.compile(
    r"(?iu)(?<!\w)(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|"
    r"\d{1,2}\s+(?:январ[яь]|феврал[яь]|март[а]?|апрел[яь]|ма[яй]|"
    r"июн[яь]|июл[яь]|август[а]?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])"
    r"(?:\s+\d{4}\s*г(?:ода|\.)?)?)(?!\w)"
)
RANGE = re.compile(
    rf"(?iu)(?<!\w)(?:от\s+{NUM}\s+до\s+{NUM}|{NUM}\s*[-–—]\s*{NUM})"
    r"(?:\s*(?:час(?:а|ов)?|дн(?:я|ей|ь)|недел[ьи-я]*|месяц[а-я]*|"
    r"руб(?:лей|ля)?|₽|%))?(?!\w)"
)
QUANTITY = re.compile(
    rf"(?iu)(?<!\w){NUM}\s*(?:%|процент(?:а|ов)?|час(?:а|ов)?|"
    r"дн(?:я|ей|ь)|недел[ьи-я]*|месяц[а-я]*|лет|год(?:а|ов)?|"
    r"км|кг|шт\.?)(?:\s+(?:в|за)\s+(?:недел[ьи-я]*|месяц[а-я]*|"
    r"день|сутки|год))?(?!\w)"
)
# A token mixing letters and digits (promo codes, models, SKUs): OSEN10, 5G.
CODE = re.compile(r"(?u)(?<![\w-])(?=[\w-]*\d)(?=[\w-]*[^\W\d_])[\w]+(?:-[\w]+)*(?![\w-])")
NUMBER = re.compile(rf"(?<![\w]){NUM}(?!\w)")
DEADLINE = re.compile(
    r"(?iu)(?<!\w)(?:до|к|не позднее)\s+"
    r"(?:понедельник[а-яё]*|вторник[а-яё]*|сред[а-яё]*|четверг[а-яё]*|"
    r"пятниц[а-яё]*|суббот[а-яё]*|воскресен[а-яё]*|завтра|сегодня|"
    r"конца\s+(?:дня|недели|месяца))(?!\w)"
)
CALENDAR = re.compile(
    r"(?iu)(?<!\w)(?:понедельник(?:а|у|ом|е|и|ам|ов)?|вторник(?:а|у|ом|е|и|ам|ов)?|"
    r"сред(?:а|у|ы|е|ам)|четверг(?:а|у|ом|е|и|ам|ов)?|пятниц(?:а|у|ы|е|ей|ам)|"
    r"суббот(?:а|у|ы|е|ой|ам)|воскресень(?:е|я|ю|ем|ям)|"
    r"январ(?:ь|я|е|ю|ём|ем)|феврал(?:ь|я|е|ю|ём|ем)|март(?:а|е|у|ом)?|"
    r"апрел(?:ь|я|е|ю|ем)|ма(?:й|я|е|ю|ем)|июн(?:ь|я|е|ю|ем)|июл(?:ь|я|е|ю|ем)|"
    r"август(?:а|е|у|ом)?|сентябр(?:ь|я|е|ю|ём|ем)|октябр(?:ь|я|е|ю|ём|ем)|"
    r"ноябр(?:ь|я|е|ю|ём|ем)|декабр(?:ь|я|е|ю|ём|ем))(?!\w)"
)
ORG = re.compile(
    r"(?iu)(?<!\w)(?:ООО|АО|ПАО|НКО)\s*[«\"][^»\"\n]{1,100}[»\"]"
)
PERSON = re.compile(
    r"(?u)(?<!\w)[А-ЯЁ][а-яё]{1,30}\s+[А-ЯЁ][а-яё]{1,30}(?!\w)"
)
# Lexical conditions and scope words: a paraphrase is common, so REVIEW only.
CONDITION = re.compile(
    r"(?iu)(?<!\w)(?:не|ни|без|нельзя|запрещено|запрещается|"
    r"обязан(?:а|ы)?|долж(?:ен|на|ны)|может|могут|вправе|"
    r"необходимо|требуется|обязательн(?:о|а|ы|ый|ая|ое|ые)|обязателен|"
    r"только|лишь|исключительно|если|при\s+условии|"
    r"после|не\s+менее|не\s+более)(?!\w)"
)
QUANTIFIER = re.compile(
    r"(?iu)(?<!\w)(?:все|всех|всем|всеми|весь|вся|всё|каждый|каждая|каждое|"
    r"каждого|каждому|каждую|каждым|любой|любая|любое|любого|любому|любую|"
    r"никто|ничего|никого|большинство|большинства|большинству|многие|многих|"
    r"многим|некоторые|некоторых|несколько|обычно|иногда|часто|редко|"
    r"всегда|никогда|почти)(?!\w)"
)
GUARANTEE = re.compile(r"(?iu)(?<!\w)гарант[а-яё]*")
WORD = re.compile(r"(?u)[^\W\d_]+(?:[-'’][^\W\d_]+)*")

_UNITS = {
    0: "ноль нуль нуля ноля нулю нолю",
    1: "один одна одно одни одного одной одному одну одним одном одними одних",
    2: "два две двух двум двумя",
    3: "три трёх трех трём трем тремя",
    4: "четыре четырёх четырех четырём четырем четырьмя",
    40: "сорок сорока",
    90: "девяносто девяноста",
    100: "сто ста",
    1.5: "полтора полторы полутора",
}
_SOFT = {
    5: "пят", 6: "шест", 7: "сем", 8: "восем", 9: "девят", 10: "десят",
    11: "одиннадцат", 12: "двенадцат", 13: "тринадцат", 14: "четырнадцат",
    15: "пятнадцат", 16: "шестнадцат", 17: "семнадцат", 18: "восемнадцат",
    19: "девятнадцат", 20: "двадцат", 30: "тридцат",
}
_TENS = {50: "пят", 60: "шест", 70: "сем", 80: "восем"}
_HUNDREDS = {
    200: "двести двухсот двумстам двумястами двухстах",
    300: "триста трёхсот трехсот тремстам тремястами трёхстах трехстах",
    400: "четыреста четырёхсот четырехсот четырёмстам четыремстам",
}
_HUNDRED_STEMS = {500: "пят", 600: "шест", 700: "сем", 800: "восем", 900: "девят"}
_BIG = {1000: "тысяч", 1000000: "миллион", 1000000000: "миллиард"}
_ORDINAL = {
    1: "перв", 2: "втор", 4: "четв[её]рт", 5: "пят", 6: "шест", 7: "седьм",
    8: "восьм", 9: "девят", 10: "десят",
}
_ADJ = "(?:ый|ой|ая|ое|ые|ого|ому|ым|ом|ую|ых|ыми)"


def _number_words() -> dict[str, str]:
    forms: dict[str, str] = {}
    for value, text in _UNITS.items():
        for form in text.split():
            forms[form] = str(value)
    for value, stem in _SOFT.items():
        for end in ("ь", "и", "ью"):
            forms[stem + end] = str(value)
    forms["восьми"] = forms["восьмью"] = "8"
    for value, stem in _TENS.items():
        base = {"пят": "пять", "шест": "шесть", "сем": "семь", "восем": "восемь"}[stem]
        forms[base + "десят"] = str(value)
        forms[stem + "идесяти"] = str(value)
        forms[stem + "ьюдесятью"] = str(value)
    forms["восьмидесяти"] = "80"
    for value, text in _HUNDREDS.items():
        for form in text.split():
            forms[form] = str(value)
    for value, stem in _HUNDRED_STEMS.items():
        base = {"пят": "пять", "шест": "шесть", "сем": "семь",
                "восем": "восемь", "девят": "девять"}[stem]
        forms[base + "сот"] = str(value)
        forms[stem + "исот"] = str(value)
    forms["восьмисот"] = "800"
    for value, stem in _BIG.items():
        ends = ("а", "и", "", "у", "ей", "ам", "ами", "ах") if stem == "тысяч" else (
            "", "а", "ов", "у", "ом", "е", "ы", "ам", "ами", "ах")
        for end in ends:
            forms[stem + end] = str(value)
    return forms


NUMBER_WORDS = _number_words()
ORDINAL = re.compile(
    "(?iu)(?<!\\w)(?:" + "|".join(
        f"(?P<o{n}>{stem}{_ADJ})" for n, stem in _ORDINAL.items()
    ) + "|(?P<o3>трет(?:ий|ья|ье|ьи|ьего|ьему|ьим|ьем|ью|ьей|ьих|ьими)))(?!\\w)"
)
NUMBER_WORD = re.compile(
    "(?iu)(?<!\\w)(?:" + "|".join(
        re.escape(w) for w in sorted(NUMBER_WORDS, key=len, reverse=True)
    ) + ")(?!\\w)"
)

# Explicit polarity pairs (pole A, pole B) matched by token prefix.
POLARITY_PAIRS = (
    (("можно",), ("нельзя",)),
    (("бесплатн",), ("платн",)),
    (("разреш",), ("запрещ",)),
    (("всегда",), ("никогда",)),
    (("включ",), ("исключ",)),
    (("доступн",), ("недоступн",)),
    (("возможн",), ("невозможн",)),
    (("обязательн",), ("необязательн",)),
)
MAY = frozenset(("может", "могут", "можете", "можем", "вправе", "допускается",
                 "разрешается"))
MUST = frozenset(("должен", "должна", "должно", "должны", "обязан", "обязана",
                  "обязаны", "обязательно", "обязательна", "обязателен",
                  "обязательны", "необходимо", "требуется", "нужно"))
ANCHOR_STOP = frozenset((
    "для", "при", "около", "всего", "только", "лишь", "уже", "это", "все",
    "его", "её", "нас", "вас", "они", "она", "оно", "руб", "рублей", "рубля",
    "рубль", "тыс", "млн", "час", "часа", "часов", "дней", "дня", "день",
    "недель", "недели", "неделю", "месяц", "месяца", "месяцев", "лет", "года",
    "год", "раз", "раза", "штук", "процентов", "процента", "минут", "минуты",
    "или", "либо", "так", "как", "что", "чем", "где", "когда", "под", "над",
    "без", "через", "после", "перед", "около", "нам", "вам", "наш", "ваш",
))
ENDINGS = tuple(sorted((
    "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими", "ой", "ей",
    "ом", "ем", "ам", "ям", "ах", "ях", "ою", "ею", "ов", "ев", "ая", "яя",
    "ую", "юю", "ий", "ый", "ые", "ие", "ых", "их", "ым", "им", "ое", "ее",
    "а", "я", "у", "ю", "е", "ы", "и", "о", "ь", "й",
), key=len, reverse=True))
BLOCKER = "blocker"
REVIEW = "review"
SEVERITY = {
    "url": BLOCKER, "email": BLOCKER, "money": BLOCKER, "date": BLOCKER,
    "deadline": BLOCKER, "calendar": BLOCKER, "range": BLOCKER,
    "quantity": BLOCKER, "code": BLOCKER, "number": BLOCKER,
    "number_word": BLOCKER, "binding": BLOCKER, "organization": BLOCKER,
    "person": BLOCKER, "proper_name": BLOCKER, "polarity": BLOCKER,
    "modality": BLOCKER, "guarantee": BLOCKER, "protected_term": BLOCKER,
    "condition": REVIEW, "quantifier": REVIEW,
}
CATEGORIES = tuple(SEVERITY)
WARNINGS = [
    "HEURISTIC_ONLY_NO_SEMANTIC_EQUIVALENCE",
    "NEGATION_SCOPE_NOT_VERIFIED",
    "NAMES_AND_CONDITIONS_NOT_EXHAUSTIVE",
    "FACT_VALUES_REDACTED",
]
_NUMERIC_KINDS = ("money", "range", "quantity", "number", "number_word")
_BOUNDARY = re.compile(r"[.!?;,\n…]")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace(" ", " ").replace(
        " ", " "
    )


def _compact(s: str) -> str:
    return " ".join(s.casefold().split())


_END_BY_LEN = tuple(
    (size, frozenset(e for e in ENDINGS if len(e) == size)) for size in (4, 3, 2, 1)
)


@lru_cache(maxsize=65536)
def stem(word: str) -> str:
    """Tiny suffix stripper for matching inflected forms; not a lemmatizer."""
    w = word.casefold().replace("ё", "е").replace("’", "'")
    for size, ends in _END_BY_LEN:
        if len(w) - size >= 3 and w[-size:] in ends:
            return w[:-size]
    return w


def _amount(s: str, scale: str = "") -> str:
    try:
        num = Decimal(s.replace(" ", "").replace(",", "."))
        if scale.startswith(("тыс", "тысяч")):
            num *= 1000
        elif scale.startswith(("млн", "миллион")):
            num *= 1000000
        return format(num.normalize(), "f")
    except InvalidOperation:
        return "INVALID_AMOUNT"


def _money(match: re.Match) -> str:
    raw = _compact(match.group("currency"))
    currency = "RUB" if raw.startswith(("руб", "₽")) else (
        "EUR" if raw in ("eur", "€") else "USD"
    )
    scale = _compact(match.groupdict().get("scale") or "")
    return currency + ":" + _amount(match.group("number"), scale)


def _number_word(match: re.Match) -> str:
    return NUMBER_WORDS[match.group().casefold()]


def _ordinal(match: re.Match) -> str:
    for name, value in match.groupdict().items():
        if value:
            return "ord:" + name[1:]
    return "ord:?"


def _calendar(match: re.Match) -> str:
    return stem(match.group())


def _extract_spans(text: str, pattern: re.Pattern, formatter=None,
                   trim_url: bool = False) -> tuple[str, list[tuple[int, str]]]:
    """Return text with matches blanked (same length) and (start, key) pairs.

    Linear: pieces are collected once instead of rebuilding the string per
    match, so a 1 MiB input stays fast.
    """
    pieces: list[str] = []
    found: list[tuple[int, str]] = []
    last = 0
    for m in pattern.finditer(text):
        span = m.group()
        end = m.end()
        if trim_url:
            span = span.rstrip(".,;:!?)»]")
            end = m.start() + len(span)
        if not span:
            continue
        key = formatter(m) if formatter else _compact(span)
        found.append((m.start(), key))
        pieces.append(text[last:m.start()])
        pieces.append(" " * (end - m.start()))
        last = end
    pieces.append(text[last:])
    return "".join(pieces), found


def validate_terms(lines: list[str] | None) -> tuple[str, ...]:
    if lines is None:
        return ()
    result: list[str] = []
    for line in lines:
        item = _compact(normalize(line))
        if not item:
            continue
        if ("\x00" in item or len(item) > 256 or
                any(c in item for c in "\r\n")):
            raise ValueError("INVALID_PROTECTED_TERMS")
        if item in result:
            raise ValueError("DUPLICATE_PROTECTED_TERM")
        result.append(item)
        if len(result) > 100:
            raise ValueError("TOO_MANY_PROTECTED_TERMS")
    return tuple(result)


def protected_count(text: str, term: str) -> int:
    return len(re.findall(r"(?<!\w)" + re.escape(term) + r"(?!\w)",
                          _compact(normalize(text))))


class _AnchorIndex:
    """Word and clause-boundary positions computed once per text (O(log n) lookups)."""

    def __init__(self, text: str):
        self.words = [(m.start(), m.group().casefold()) for m in WORD.finditer(text)]
        self.starts = [start for start, _ in self.words]
        self.bounds = [m.start() for m in _BOUNDARY.finditer(text)]

    def anchor(self, start: int) -> str | None:
        """Nearest preceding content word (≤3 words back) inside the same clause."""
        cut = bisect_left(self.bounds, start) - 1
        limit = self.bounds[cut] if cut >= 0 else -1
        index = bisect_left(self.starts, start) - 1
        for _ in range(3):
            if index < 0 or self.words[index][0] <= limit:
                return None
            low = self.words[index][1]
            if len(low) >= 3 and low not in ANCHOR_STOP:
                return stem(low)
            index -= 1
        return None


def _sentence_initial(text: str, start: int) -> bool:
    i = start - 1
    while i >= 0 and (text[i].isspace() or text[i] in "«\"'(-–—•*▪●✓✔→>[]"
                      or unicodedata.category(text[i]) == "So"):
        if text[i] == "\n":
            return True
        i -= 1
    return i < 0 or text[i] in ".!?…"


def _proper_name_seeds(text: str) -> set[str]:
    seeds: set[str] = set()
    for m in WORD.finditer(text):
        word = m.group()
        latin = all(ch.isascii() for ch in word if ch.isalpha())
        if latin or (word[0].isupper() and not _sentence_initial(text, m.start())):
            seeds.add(stem(word))
    return seeds


def _polarity(tokens: list[str], base: set[str]) -> tuple[Counter, Counter]:
    """(positive, negated) counts per stem; fused «не-» only when its base exists."""
    pos: Counter = Counter()
    neg: Counter = Counter()
    for index, token in enumerate(tokens):
        if token in ("не", "ни"):
            continue
        negated = index > 0 and tokens[index - 1] in ("не", "ни")
        if token.startswith("не") and len(token) > 4 and stem(token[2:]) in base:
            neg[stem(token[2:])] += 1
            continue
        (neg if negated else pos)[stem(token)] += 1
    return pos, neg


def _pole_counts(tokens: list[str]) -> list[tuple[int, int]]:
    unique = Counter(tokens)
    result = []
    for poles_a, poles_b in POLARITY_PAIRS:
        a = b = 0
        for token, freq in unique.items():
            if token.startswith(poles_b):
                b += freq
            elif token.startswith(poles_a):
                a += freq
        result.append((a, b))
    return result


def _tokens(text: str) -> list[str]:
    return [w.casefold().replace("ё", "е") for w in WORD.findall(text)]


def inventory(text: str, terms: tuple[str, ...] = (),
              name_seeds: set[str] | None = None,
              base_stems: set[str] | None = None) -> dict[str, Counter]:
    """Multiset of category keys; values are never written to output."""
    text = normalize(text)
    counts: dict[str, Counter] = {kind: Counter() for kind in CATEGORIES}
    for term in terms:
        counts["protected_term"][term] = protected_count(text, term)
    masked = text
    positions: list[tuple[int, str, str]] = []
    for name, regex, formatter, trim in (
        ("url", URL, None, True),
        ("email", EMAIL, None, False),
        ("money", MONEY, _money, False),
        ("money", MONEY_PREFIX, _money, False),
        ("date", DATE, None, False),
        ("deadline", DEADLINE, None, False),
        ("calendar", CALENDAR, _calendar, False),
        ("range", RANGE, None, False),
        ("quantity", QUANTITY, None, False),
        ("code", CODE, None, False),
        ("number", NUMBER, None, False),
        ("number_word", ORDINAL, _ordinal, False),
        ("number_word", NUMBER_WORD, _number_word, False),
        ("organization", ORG, None, False),
        ("person", PERSON, None, False),
    ):
        masked, found = _extract_spans(masked, regex, formatter, trim)
        counts[name].update(key for _, key in found)
        positions.extend((start, name, key) for start, key in found)
    anchors = _AnchorIndex(text)
    for start, name, key in positions:
        if name in _NUMERIC_KINDS:
            anchor = anchors.anchor(start)
            if anchor is not None:
                counts["binding"][anchor + "\x1f" + name + "\x1f" + key] += 1
    tokens = _tokens(masked)
    seeds = name_seeds if name_seeds is not None else _proper_name_seeds(masked)
    for token in tokens:
        if stem(token) in seeds:
            counts["proper_name"][stem(token)] += 1
    base = base_stems if base_stems is not None else {
        stem(t) for t in tokens if not t.startswith("не")}
    pos, neg = _polarity(tokens, base)
    for key, value in pos.items():
        counts["polarity"]["+" + key] += value
    for key, value in neg.items():
        counts["polarity"]["-" + key] += value
    for index, (a, b) in enumerate(_pole_counts(tokens)):
        counts["polarity"]["pair" + str(index) + "a"] += a
        counts["polarity"]["pair" + str(index) + "b"] += b
    counts["modality"]["may"] = sum(t in MAY for t in tokens)
    counts["modality"]["must"] = sum(t in MUST for t in tokens)
    counts["guarantee"]["g"] = len(GUARANTEE.findall(masked))
    counts["condition"].update(_compact(m.group()) for m in CONDITION.finditer(masked))
    counts["quantifier"].update(
        _compact(m.group()).replace("ё", "е") for m in QUANTIFIER.finditer(masked))
    return counts


def _shared_context(before: str, after: str) -> tuple[set[str], set[str]]:
    seeds = set()
    base = set()
    for text in (before, after):
        masked = text
        for regex in (URL, EMAIL):
            masked, _ = _extract_spans(masked, regex)
        seeds |= _proper_name_seeds(normalize(masked))
        base |= {stem(t) for t in _tokens(normalize(masked)) if not t.startswith("не")}
    return seeds, base


def _flip(old: tuple[int, int], new: tuple[int, int]) -> bool:
    return (new[0] < old[0] and new[1] > old[1]) or (
        new[0] > old[0] and new[1] < old[1])


def _polarity_changed(old: Counter, new: Counter) -> tuple[int, int]:
    """Count stems whose negation changed while the word stayed, plus pair flips."""
    changed = 0
    stems = {k[1:] for k in list(old) + list(new) if k[0] in "+-"}
    for key in stems:
        o_pos, o_neg = old["+" + key], old["-" + key]
        n_pos, n_neg = new["+" + key], new["-" + key]
        if (o_pos + o_neg) and (n_pos + n_neg) and o_neg != n_neg:
            changed += 1
    for index in range(len(POLARITY_PAIRS)):
        o = (old["pair" + str(index) + "a"], old["pair" + str(index) + "b"])
        n = (new["pair" + str(index) + "a"], new["pair" + str(index) + "b"])
        if _flip(o, n):
            changed += 1
    return changed, changed


def _binding_changed(old: Counter, new: Counter) -> tuple[int, int]:
    """Anchors present in both texts whose attached values differ (swaps)."""
    def by_anchor(c: Counter) -> dict[str, Counter]:
        out: dict[str, Counter] = {}
        for key, value in c.items():
            anchor, _, rest = key.partition("\x1f")
            out.setdefault(anchor, Counter())[rest] += value
        return out
    left, right = by_anchor(old), by_anchor(new)
    removed = added = 0
    for anchor in set(left) & set(right):
        if left[anchor] != right[anchor]:
            removed += sum((left[anchor] - right[anchor]).values())
            added += sum((right[anchor] - left[anchor]).values())
    return removed, added


def check(before: str, after: str, terms: tuple[str, ...] = ()) -> dict:
    seeds, base = _shared_context(before, after)
    left = inventory(before, terms, seeds, base)
    right = inventory(after, terms, seeds, base)
    findings = []
    for kind in CATEGORIES:
        old, new = left[kind], right[kind]
        if kind == "polarity":
            missing, added = _polarity_changed(old, new)
            before_count = after_count = missing
        elif kind == "modality":
            flipped = _flip((old["may"], old["must"]), (new["may"], new["must"]))
            missing = added = int(flipped)
            before_count, after_count = sum(old.values()), sum(new.values())
        elif kind == "binding":
            missing, added = _binding_changed(old, new)
            before_count, after_count = sum(old.values()), sum(new.values())
        else:
            missing = sum((old - new).values())
            added = sum((new - old).values())
            before_count, after_count = sum(old.values()), sum(new.values())
        if missing or added:
            findings.append({
                "kind": kind,
                "severity": SEVERITY[kind],
                "before_count": before_count,
                "after_count": after_count,
                "removed_count": missing,
                "added_count": added,
            })
    unchanged = before == after
    blocking = any(item["severity"] == BLOCKER for item in findings)
    reviewing = any(item["severity"] == REVIEW for item in findings)
    decision = ("blocked" if blocking else
                "unchanged" if unchanged else "review_required")
    warnings = list(WARNINGS)
    if blocking:
        warnings.append("BLOCKING_FACT_DIFFERENCES_REQUIRE_APPROVAL")
    if reviewing:
        warnings.append("CONDITION_OR_SCOPE_WORDING_CHANGED_REVIEW")
    if not unchanged and not blocking:
        warnings.append("CHANGED_TEXT_REQUIRES_SEMANTIC_REVIEW")
    return {
        "guard_version": VERSION,
        "tool_version": __version__,
        "decision": decision,
        "publish_ready": False,
        "semantic_equivalence": "not_verified",
        "changed": not unchanged,
        "findings": findings,
        "warnings": warnings,
    }
