"""A8 deterministic *risk screening* of edits, not semantic equivalence.

Changes to detected protected tokens BLOCK publication pending human review.
Text changes with no detected tokens still REQUIRE human editorial review.
Reports intentionally reveal no original amounts, URLs, names, or text.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from . import __version__

VERSION = "a8-rules-1.0"
NUM = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d+)?"
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
NUMBER = re.compile(rf"(?<![\w]){NUM}(?!\w)")
DEADLINE = re.compile(
    r"(?iu)(?<!\w)(?:до|к|не позднее)\s+"
    r"(?:понедельник[а-яё]*|вторник[а-яё]*|сред[а-яё]*|четверг[а-яё]*|"
    r"пятниц[а-яё]*|суббот[а-яё]*|воскресен[а-яё]*|завтра|сегодня|"
    r"конца\s+(?:дня|недели|месяца))(?!\w)"
)
ORG = re.compile(
    r"(?iu)(?<!\w)(?:ООО|АО|ПАО|НКО)\s*[«\"][^»\"\n]{1,100}[»\"]"
)
PERSON = re.compile(
    r"(?u)(?<!\w)[А-ЯЁ][а-яё]{1,30}\s+[А-ЯЁ][а-яё]{1,30}(?!\w)"
)
# This is a shallow lexical check. Scope and synonym substitution are not solved.
CONDITION = re.compile(
    r"(?iu)(?<!\w)(?:не|ни|без|нельзя|запрещено|запрещается|"
    r"обязан(?:а|ы)?|долж(?:ен|на|ны)|может|могут|вправе|"
    r"необходимо|требуется|обязательно|только|если|при\s+условии|"
    r"после|не\s+менее|не\s+более)(?!\w)"
)

CATEGORIES = ("url", "email", "money", "date", "deadline",
              "range", "quantity", "number", "organization", "person",
              "condition", "protected_term")
WARNINGS = [
    "HEURISTIC_ONLY_NO_SEMANTIC_EQUIVALENCE",
    "NEGATION_SCOPE_NOT_VERIFIED",
    "NAMES_AND_CONDITIONS_NOT_EXHAUSTIVE",
    "FACT_VALUES_REDACTED",
]


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\u00a0", " ").replace(
        "\u202f", " "
    )


def _compact(s: str) -> str:
    return " ".join(s.casefold().split())


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


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + (" " * (end - start)) + text[end:]


def _extract_spans(text: str, pattern: re.Pattern,
                   formatter=None, trim_url: bool = False
                   ) -> tuple[str, Counter]:
    found = Counter()
    matches = list(pattern.finditer(text))
    for m in reversed(matches):
        span = m.group()
        end = m.end()
        if trim_url:
            span = span.rstrip(".,;:!?)»]")
            end = m.start() + len(span)
        if not span:
            continue
        key = formatter(m) if formatter else _compact(span)
        found[key] += 1
        text = _blank(text, m.start(), end)
    return text, found


def validate_terms(lines: list[str] | None) -> tuple[str, ...]:
    if lines is None:
        return ()
    result = []
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


def inventory(text: str, terms: tuple[str, ...] = ()) -> dict[str, Counter]:
    """Multiset of category values, never written to output."""
    text = normalize(text)
    counts = {kind: Counter() for kind in CATEGORIES}
    for term in terms:
        # Store an index, not raw phrase, even in ephemeral dictionary keys.
        counts["protected_term"][term] = protected_count(text, term)
    for name, regex, formatter, trim in (
        ("url", URL, None, True),
        ("email", EMAIL, None, False),
        ("money", MONEY, _money, False),
        ("money", MONEY_PREFIX, _money, False),
        ("date", DATE, None, False),
        ("deadline", DEADLINE, None, False),
        ("range", RANGE, None, False),
        ("quantity", QUANTITY, None, False),
        ("number", NUMBER, None, False),
        ("organization", ORG, None, False),
        ("person", PERSON, None, False),
    ):
        text, discovered = _extract_spans(text, regex, formatter, trim)
        counts[name].update(discovered)
    # Lexical conditions are independent of the numeric masking above.
    full = normalize(text)  # masked text prevents false signals inside URLs etc.
    counts["condition"].update(_compact(m.group()) for m in CONDITION.finditer(full))
    return counts


def check(before: str, after: str, terms: tuple[str, ...] = ()) -> dict:
    left, right = inventory(before, terms), inventory(after, terms)
    findings = []
    for kind in CATEGORIES:
        old, new = left[kind], right[kind]
        missing = sum((old - new).values())
        added = sum((new - old).values())
        if missing or added:
            findings.append({
                "kind": kind,
                "severity": "blocker",
                "before_count": sum(old.values()),
                "after_count": sum(new.values()),
                "removed_count": missing,
                "added_count": added,
            })
    unchanged = before == after
    decision = ("blocked" if findings else
                "unchanged" if unchanged else "review_required")
    return {
        "guard_version": VERSION,
        "tool_version": __version__,
        "decision": decision,
        "publish_ready": False,
        "semantic_equivalence": "not_verified",
        "changed": not unchanged,
        "findings": findings,
        "warnings": WARNINGS + (
            ["BLOCKING_FACT_DIFFERENCES_REQUIRE_APPROVAL"] if findings else
            ["CHANGED_TEXT_REQUIRES_SEMANTIC_REVIEW"] if not unchanged else []
        ),
    }
