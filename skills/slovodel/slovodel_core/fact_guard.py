"""A8 deterministic *risk screening* of edits, not semantic equivalence.

Rules 2.2 (Core 0.8.2) separate two severities:

* ``blocker`` — a detected protected fact changed (amounts, numbers written in
  digits or words, codes, dates, weekdays/months, names, links, polarity or
  modality flips, guarantees, number-to-word bindings, protected phrases).
  An editor must resolve the finding; the report itself never approves prose.
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
from .equivalence import date_key

VERSION = "a8-rules-2.3"
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
_MEASURE_UNIT = r"кв\.[ \t]*м\.?|м[²2]|см[²2]|м(?:етр(?:а|ов)?)?|см|мм|мл|л(?:итр(?:а|ов)?)?"
MEASURE = re.compile(rf"(?iu)(?<!\w)(?P<number>{NUM})\s*(?P<unit>{_MEASURE_UNIT})(?!\w)")
_MEASURE_LETTER = re.compile(r"[мл]", re.IGNORECASE)
# Extract a bounded two-line characteristic, not arbitrary preceding prose.
FIELD_MEASURE = re.compile(
    rf"(?imu)^[ \t]*(?:объ[её]м|площадь|высота|длина|ширина|толщина),[ \t]*"
    rf"(?P<unit>{_MEASURE_UNIT})[ \t]*\r?\n[ \t]*(?P<number>{NUM})[ \t]*(?=\r?$)"
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
    # Same line only: a UI label line and a button line are not a full name.
    r"(?u)(?<!\w)[А-ЯЁ][а-яё]{1,30}[ \t]+[А-ЯЁ][а-яё]{1,30}(?!\w)"
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

# Bounded commercial context; these are risk indicators, not semantic parsing.
_PRICE_BOUND = re.compile(
    r"(?iu)(?<!\w)(не\s+менее|не\s+более|начиная\s+с|от|до)[\s:—–-]*$"
)
_RATE = re.compile(
    r"(?iu)^\s*(?:в|за|/)\s*(час(?:а|ов)?|день|дня|дней|сутки|суток|"
    r"недел[а-яё]*|месяц[а-яё]*|год(?:а|ов)?)(?!\w)"
)
_PAYMENT_ROLE = re.compile(r"(?iu)(?<!\w)(предоплат[а-яё]*|аванс[а-яё]*|скидк[а-яё]*|залог[а-яё]*)(?!\w)")
_FREE = re.compile(r"(?iu)(?<!\w)бесплатн[а-яё]*(?!\w)")
_DATE_RELATION = re.compile(r"(?iu)(?<!\w)(не\s+позднее|не\s+раньше|после|до|с|к)[\s:—–-]*$")
_AUDIENCE = re.compile(r"(?iu)(?<!\w)(?:помогаем|поможем|работаем\s+с|для)\s+([^.!?;\n]{1,100})")

# These lexical cues trigger review, not a claim of semantic understanding.
TEMPORAL = re.compile(r"(?iu)(?<!\w)(?:на\s+момент\s+публикации|на\s+сегодняшний\s+день|"
                      r"в\s+настоящий\s+момент|в\s+этом\s+году|сейчас|сегодня|тогда)(?!\w)")
EPISTEMIC = re.compile(r"(?iu)(?<!\w)(?:предполож[а-яё]*|гипотез[а-яё]*|"
                       r"вероятно|возможно|по-видимому)(?!\w)")
ATTRIBUTION = re.compile(r"(?iu)(?<!\w)(?:по\s+данным\s+исследован[а-яё]*|"
                         r"по\s+мнению\s+автора|автор\s+(?:считает|полагает)|"
                         r"исследован[а-яё]*\s+(?:показал[а-яё]*|доказал[а-яё]*))(?!\w)")
_LATIN_TO_CYRILLIC = str.maketrans("ABCEHKMOPTXYaceopxy", "АВСЕНКМОРТХУасеорху")
_CYRILLIC_TO_LATIN = {v: chr(k) for k, v in _LATIN_TO_CYRILLIC.items()}


def _comparison_glyphs(text: str, peer: str) -> tuple[str, list[dict]]:
    """Normalize only mixed-script words with an unambiguous single-script result.

    Never touch URLs, emails, identifiers containing digits, or pure-script words.
    Offsets refer to the untouched input; hashes in CLI reports retain provenance.
    Ambiguous all-lookalike words remain untouched. Avito is an explicit alias,
    activated only by a mixed spelling and its canonical Cyrillic peer.
    """
    # No mixed token is possible without both scripts. Avoid a Python-level
    # walk over every word in large, entirely Cyrillic source documents.
    if not re.search(r"[A-Za-z]", text) or not re.search(r"[А-Яа-яЁё]", text):
        return text, []
    protected = [m.span() for regex in (URL, EMAIL) for m in regex.finditer(text)]
    protected.sort()
    cursor = 0
    changes = []
    pieces = []
    end = 0
    avito_peer = bool(re.search(r"(?iu)(?<!\w)авито(?!\w)", peer))
    for m in re.finditer(r"\w+", text):
        while cursor < len(protected) and protected[cursor][1] <= m.start():
            cursor += 1
        if cursor < len(protected) and protected[cursor][0] < m.end():
            continue
        token = m.group()
        if not token.isalpha() or not re.search(r"[A-Za-z]", token) or not re.search(r"[А-Яа-яЁё]", token):
            continue
        cyr = token.translate(_LATIN_TO_CYRILLIC)
        lat = token.translate(_CYRILLIC_TO_LATIN)
        options = [v for v in (cyr, lat) if re.fullmatch(r"[А-Яа-яЁё]+|[A-Za-z]+", v)]
        kind = "mixed_script_visual"
        if lat.casefold() == "avito" and avito_peer:
            replacement, kind = "Авито", "mixed_avito_alias"
        elif len(options) == 1:
            replacement = options[0]
        else:
            continue
        pieces.extend((text[end:m.start()], replacement))
        end = m.end()
        changes.append({"start": m.start(), "end": m.end(), "kind": kind})
    pieces.append(text[end:])
    return "".join(pieces), changes

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
    "commercial_term": BLOCKER,
    "initial_capital": REVIEW, "audience_context": REVIEW,
    "temporal_context": REVIEW, "epistemic_context": REVIEW, "attribution": REVIEW,
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


def _measure(match: re.Match) -> str:
    unit = _compact(match.group('unit'))
    unit = ('м²' if unit.startswith('кв.') or unit == 'м2' else
            'см²' if unit == 'см2' else
            'м' if unit.startswith('метр') else
            'л' if unit.startswith('литр') else unit)
    return _amount(match.group('number')) + ':' + unit


def _number_word(match: re.Match) -> str:
    return NUMBER_WORDS[match.group().casefold()]


def _ordinal(match: re.Match) -> str:
    for name, value in match.groupdict().items():
        if value:
            return "ord:" + name[1:]
    return "ord:?"


def _calendar(match: re.Match) -> str:
    return stem(match.group())


def _commercial_facts(text: str) -> Counter:
    """Bind a price qualifier, billing period or payment role to its value."""
    result: Counter = Counter()
    for regex, formatter in ((MONEY, _money), (MONEY_PREFIX, _money),
                             (QUANTITY, lambda m: _compact(m.group()))):
        for match in regex.finditer(text):
            prior = text[max(0, match.start() - 80):match.start()]
            prior = re.split(r"[.!?;\n]", prior)[-1]
            key = formatter(match)
            roles = list(_PAYMENT_ROLE.finditer(prior))
            if roles:
                raw = roles[-1].group().casefold()
                role = ("prepayment" if raw.startswith(("предоплат", "аванс"))
                        else "discount" if raw.startswith("скидк") else "deposit")
                result["role:" + key + ":" + role] += 1
            if regex is QUANTITY:
                continue
            bound = _PRICE_BOUND.search(prior)
            if bound:
                raw = _compact(bound.group(1))
                side = "min" if raw in ("от", "не менее", "начиная с") else "max"
                result["bound:" + key + ":" + side] += 1
            rate = _RATE.match(text[match.end():match.end() + 40])
            if rate:
                word = rate.group(1).casefold()
                period = ("month" if word.startswith("месяц") else
                          "week" if word.startswith("недел") else
                          "year" if word.startswith("год") else
                          "hour" if word.startswith("час") else "day")
                result["rate:" + key + ":" + period] += 1
    for match in DATE.finditer(text):
        prior = text[max(0, match.start() - 30):match.start()]
        relation = _DATE_RELATION.search(prior)
        if relation:
            raw = _compact(relation.group(1))
            raw = {"не позднее": "до", "к": "до"}.get(raw, raw)
            result["date:" + _compact(match.group()) + ":" + raw] += 1
    result["free_claim"] = len(_FREE.findall(text))
    return result


def _initial_capitals(text: str) -> Counter:
    """A changed capitalized start in shared context warrants review, not NER."""
    words = list(WORD.finditer(text))
    result: Counter = Counter()
    for index, match in enumerate(words):
        word = match.group()
        if not word[0].isupper() or not _sentence_initial(text, match.start()):
            continue
        following = words[index + 1:index + 4]
        if not following or re.search(r"[.!?;\n]", text[match.end():following[-1].end()]):
            continue
        context = " ".join(stem(w.group()) for w in following)
        result[context + "\x1f" + stem(word)] += 1
    return result


def _audience_context(text: str) -> Counter:
    stop = {"в", "с", "на", "по", "к", "о", "об", "и", "мы", "вы"}
    return Counter(" ".join(stem(w) for w in WORD.findall(m.group(1))
                            if w.casefold() not in stop)
                   for m in _AUDIENCE.finditer(text))


def _cardinal_quantities(text: str) -> str:
    """Normalize single-token cardinals before units for equivalence checking.

    Compound numbers, ordinals and implied units remain conservative. This
    helper is not used to rewrite the user's text or protected expressions.
    """
    masked = text
    for regex in (URL, EMAIL):
        masked, _ = _extract_spans(masked, regex)
    words = list(_WORD_RUN.finditer(masked))
    parts: list[str] = []
    end = 0
    for index, match in enumerate(words):
        value = NUMBER_WORDS.get(match.group().casefold())
        if value is None or Decimal(value) >= 1000:
            continue
        if index and words[index - 1].group().casefold() in NUMBER_WORDS:
            continue
        following = masked[match.end():match.end() + 40]
        if not QUANTITY.match(value + following):
            continue
        parts.extend((masked[end:match.start()], value))
        end = match.end()
    parts.append(masked[end:])
    return "".join(parts)


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


_WORD_RUN = re.compile(r"\w+")


def _extract_number_words(text: str) -> tuple[str, list[tuple[int, str]]]:
    """Same result as the NUMBER_WORD regex, found by dictionary lookup.

    A hundred-way alternation tried at every position cost over a second per
    MiB; matching whole words against NUMBER_WORDS is equivalent and fast.
    """
    pieces: list[str] = []
    found: list[tuple[int, str]] = []
    last = 0
    for m in _WORD_RUN.finditer(text):
        key = NUMBER_WORDS.get(m.group().casefold())
        if key is None:
            continue
        start, end = m.span()
        found.append((start, key))
        pieces.append(text[last:start])
        pieces.append(" " * (end - start))
        last = end
    if not found:
        return text, found
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
    # A colon starts a value («Кнопка: Войти»): a capital after it is not a name.
    return i < 0 or text[i] in ".!?…:"


def _proper_name_seeds(text: str) -> set[str]:
    seeds: set[str] = set()
    for m in WORD.finditer(text):
        word = m.group()
        latin = all(ch.isascii() for ch in word if ch.isalpha())
        marked_case = any(ch.isupper() for ch in word[1:])
        if latin or marked_case or (word[0].isupper() and not _sentence_initial(text, m.start())):
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
    for regex in (URL, EMAIL):
        masked, _ = _extract_spans(masked, regex)
    counts["commercial_term"] = _commercial_facts(masked)
    counts["initial_capital"] = _initial_capitals(masked)
    counts["audience_context"] = _audience_context(masked)
    for kind, pattern in (("temporal_context", TEMPORAL),
                          ("epistemic_context", EPISTEMIC), ("attribution", ATTRIBUTION)):
        counts[kind].update(_compact(m.group()) for m in pattern.finditer(masked))
    masked = text
    positions: list[tuple[int, str, str]] = []
    for name, regex, formatter, trim in (
        ("url", URL, None, True),
        ("email", EMAIL, None, False),
        ("money", MONEY, _money, False),
        ("money", MONEY_PREFIX, _money, False),
        ("date", DATE, lambda m: date_key(m.group()), False),
        ("deadline", DEADLINE, None, False),
        ("calendar", CALENDAR, _calendar, False),
        ("range", RANGE, None, False),
        ("quantity", FIELD_MEASURE, _measure, False),
        ("quantity", MEASURE, _measure, False),
        ("quantity", QUANTITY, None, False),
        ("code", CODE, None, False),
        ("number", NUMBER, None, False),
        ("number_word", ORDINAL, _ordinal, False),
        ("number_word", NUMBER_WORD, _number_word, False),
        ("organization", ORG, None, False),
        ("person", PERSON, lambda m: ' '.join(sorted(_compact(m.group()).split())), False),
    ):
        # Necessary conditions only: these fast paths cannot suppress a match.
        if regex is FIELD_MEASURE and "\n" not in masked:
            continue
        if regex is MEASURE and _MEASURE_LETTER.search(masked) is None:
            continue
        if regex is NUMBER_WORD:
            masked, found = _extract_number_words(masked)
        else:
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
    original_before, original_after = before, after
    before, before_changes = _comparison_glyphs(original_before, original_after)
    after, after_changes = _comparison_glyphs(original_after, original_before)
    from .equivalence import paired
    uncanonical = before, after
    before, after = paired(before, after, PERSON)
    equivalence_used = uncanonical != (before, after)
    seeds, base = _shared_context(before, after)
    left = inventory(before, terms, seeds, base)
    right = inventory(after, terms, seeds, base)
    # Explicit literal phrases remain exact, even when visual spelling is repaired.
    left["protected_term"] = Counter({t: protected_count(original_before, t) for t in terms})
    right["protected_term"] = Counter({t: protected_count(original_after, t) for t in terms})
    # URLs and contacts remain exact even if a person-like span abuts a link.
    for kind, regex in (('url', URL), ('email', EMAIL)):
        left[kind] = Counter(v for _,v in _extract_spans(original_before,regex,trim_url=kind=='url')[1])
        right[kind] = Counter(v for _,v in _extract_spans(original_after,regex,trim_url=kind=='url')[1])
    # Preserve historical finding categories, but suppress numeric differences
    # that disappear after a supported word-to-digit normalization. Context
    # bindings are compared too, so swapping two equivalent amounts still fails.
    equivalent_numeric: set[str] = set()
    if left["number_word"] != right["number_word"]:
        canonical_before = _cardinal_quantities(normalize(before))
        canonical_after = _cardinal_quantities(normalize(after))
        if canonical_before != normalize(before) or canonical_after != normalize(after):
            canonical_left = inventory(canonical_before, (), seeds, base)
            canonical_right = inventory(canonical_after, (), seeds, base)
            if all(canonical_left[kind] == canonical_right[kind] for kind in _NUMERIC_KINDS):
                equivalent_numeric = {kind for kind in (*_NUMERIC_KINDS, "binding", "commercial_term")
                                      if canonical_left[kind] == canonical_right[kind]}
    findings = []
    known_names = {stem(w) for w in WORD.findall(before) if w[0].isupper()}
    for kind in CATEGORIES:
        if kind in equivalent_numeric:
            continue
        old, new = left[kind], right[kind]
        if kind == "polarity":
            missing, added = _polarity_changed(old, new)
            before_count = after_count = missing
        elif kind == "modality":
            flipped = _flip((old["may"], old["must"]), (new["may"], new["must"]))
            missing = added = int(flipped)
            before_count, after_count = sum(old.values()), sum(new.values())
        elif kind in ("binding", "initial_capital"):
            missing, added = _binding_changed(old, new)
            before_count, after_count = sum(old.values()), sum(new.values())
        else:
            missing = sum((old - new).values())
            added = sum((new - old).values())
            before_count, after_count = sum(old.values()), sum(new.values())
        if missing or added:
            findings.append({
                "kind": kind,
                "severity": (REVIEW if kind == 'proper_name' and not missing
                             and set(new - old) <= known_names else SEVERITY[kind]),
                "before_count": before_count,
                "after_count": after_count,
                "removed_count": missing,
                "added_count": added,
            })
    unchanged = original_before == original_after
    blocking = any(item["severity"] == BLOCKER for item in findings)
    reviewing = any(item["severity"] == REVIEW for item in findings)
    decision = ("blocked" if blocking else
                "unchanged" if unchanged else "review_required")
    warnings = list(WARNINGS)
    if equivalence_used:
        warnings.append('BOUNDED_COMPARISON_EQUIVALENCE_REVIEW_ORIGINALS')
    if re.findall(r'(?<=[а-яё».)])\[\d{1,3}\]', original_before, re.I) != re.findall(r'(?<=[а-яё».)])\[\d{1,3}\]', original_after, re.I):
        warnings.append('ATTACHED_REFERENCE_MARKERS_CHANGED_REVIEW')
    if before_changes or after_changes:
        warnings.append("COMPARISON_GLYPHS_NORMALIZED_REVIEW_ORIGINALS")
    if any(left["temporal_context"].values()) or any(right["temporal_context"].values()):
        warnings.append("TEMPORAL_CONTEXT_REQUIRES_SOURCE_DATE_REVIEW")
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
        "comparison_normalization": {"before": before_changes, "after": after_changes},
        "warnings": warnings,
    }
