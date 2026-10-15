"""Deterministic, orthographic Russian text statistics (A1, A3, A4, A6, A7).

No corpus, pronunciation dictionary, morphological inference, or network I/O.
All calculations use a Unicode NFC copy. Text and token strings are never
returned; only aggregate measurements are exposed in the public JSON report.
"""
from __future__ import annotations

from collections import Counter
import re
import statistics
import unicodedata

from . import METHOD_VERSION

RU_ALPHABET = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
RU_LETTERS = frozenset(RU_ALPHABET)
VOWELS = frozenset("аеёиоуыэюя")
PHI = 0.61803398875
WINDOW = 5

# Remove URL and email data before lexical measurements. These are intentionally
# bounded heuristics, not full RFC parsers. No text fragments enter the output.
URL = re.compile(r"(?i)(?<!\w)(?:https?://|www\.)[^\s<>\"'()]+")
EMAIL = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[\w.-]+\.[\w-]+")
ABBREV = re.compile(
    r"(?i)(?<!\w)(?:т\.\s?д\.|т\.\s?п\.|г\.|ул\.|им\.|"
    r"см\.|напр\.|др\.|стр\.|рис\.|проф\.)"
)


def cleaned(text: str) -> str:
    """Mask excluded spans with spaces, preserving source-length positions."""
    text = URL.sub(lambda m: " " * len(m.group()), text)
    return EMAIL.sub(lambda m: " " * len(m.group()), text)


def is_mark(char: str) -> bool:
    return unicodedata.category(char).startswith("M")


def words(text: str) -> list[str]:
    """Letter tokens, marks attach to the preceding letter, hyphen joins words.

    ASCII hyphen connects two letter runs; U+2010/U+2011 also join. Em dash
    splits. Numbers, links/emails, emoji and underscore never become tokens.
    """
    result = []
    buf = []
    index = 0
    while index < len(text):
        ch = text[index]
        if ch.isalpha():
            buf.append(ch)
        elif buf and is_mark(ch):
            buf.append(ch)
        elif (ch in "-\u2010\u2011" and buf and
              index + 1 < len(text) and text[index + 1].isalpha()):
            buf.append("-")
        else:
            if buf:
                result.append("".join(buf).casefold())
                buf = []
        index += 1
    if buf:
        result.append("".join(buf).casefold())
    return result


def russian_token(word: str) -> bool:
    """Russian alphabet only, with marks attached and optional hyphens."""
    base = [ch for ch in word if not is_mark(ch) and ch != "-"]
    return bool(base) and all(ch in RU_LETTERS for ch in base)


def sentence_count(text: str) -> int:
    """Conservative punctuation heuristic, NOT syntactic parsing."""
    masked = ABBREV.sub(lambda m: m.group().replace(".", " "), text)
    # Decimal punctuation does not delimit a sentence.
    chars = list(masked)
    for i in range(1, len(chars) - 1):
        if (chars[i] == "." and chars[i - 1].isdigit()
                and chars[i + 1].isdigit()):
            chars[i] = " "
    parts = re.split(r"[.!?\u2026]+", "".join(chars))
    return sum(bool(words(part)) for part in parts)


def base_mark_clusters(text: str) -> int:
    """Approximation: combining marks extend preceding code point; NOT UAX29."""
    return sum(not is_mark(ch) for ch in text)


def measurement(
    identifier: str, value: int | float, unit: str, n: int,
    section: str, warnings: list[str] | None = None,
) -> dict:
    return {
        "id": identifier,
        "value": value,
        "unit": unit,
        "status": "reproducible",
        "method_id": "slovodel." + section,
        "method_version": METHOD_VERSION,
        "dataset_id": None,
        "n": n,
        "warnings": warnings or [],
    }


def unavailable(identifier: str, reason: str) -> dict:
    return {
        "id": identifier, "value": None, "unit": None,
        "status": "unavailable", "method_id": None,
        "method_version": None, "dataset_id": None, "n": None,
        "warnings": [reason],
    }


def letter_ngram_stats(ru_words: list[str], size: int) -> tuple[int, int]:
    """Per-word letter n-grams, never spanning word boundaries."""
    counts = Counter(
        word[i:i + size]
        for word in ru_words
        for i in range(max(0, len(word) - size + 1))
        if "-" not in word[i:i + size]
        and not any(is_mark(ch) for ch in word[i:i + size])
    )
    return (sum(freq > 1 for freq in counts.values()),
            sum(freq - 1 for freq in counts.values() if freq > 1))


def onset_windows(ru_words: list[str]) -> tuple[int, int]:
    onsets = [word[0] for word in ru_words]
    count = max(0, len(onsets) - WINDOW + 1)
    flagged = sum(
        len(set(onsets[i:i + WINDOW])) < WINDOW for i in range(count)
    )
    return count, flagged


def calculate(decoded: str, reference: tuple[dict, str] | None = None,
              morphology: tuple[object, str] | None = None,
              morphology_reason: str = "MORPHOLOGY_OPT_IN_REQUIRED") -> list[dict]:
    """Ordered list of aggregate, provenance-tagged metrics."""
    text = unicodedata.normalize("NFC", decoded)
    safe = cleaned(text)
    tokens = words(safe)
    ru_words = [token for token in tokens if russian_token(token)]
    ru_letters = [ch for ch in safe.casefold() if ch in RU_LETTERS]
    letter_counts = Counter(ru_letters)
    ru_freqs = Counter(ru_words)
    syllables = [sum(ch in VOWELS for ch in word) for word in ru_words]
    n_ru = len(ru_words)
    n_letters = len(ru_letters)
    metrics = []

    def add(identifier: str, value: int | float, unit: str,
            n: int, section: str, warnings: list[str] | None = None) -> None:
        metrics.append(measurement(identifier, value, unit, n, section, warnings))

    # A1: deliberately count all-letter tokens and Russian-only tokens separately.
    add("token_count", len(tokens), "tokens", len(tokens), "a1.tokens")
    add("russian_token_count", n_ru, "tokens", n_ru, "a1.russian_tokens")
    add("sentence_count", sentence_count(safe), "sentences",
        len(tokens), "a1.sentence_heuristic", ["HEURISTIC_ABBREVIATIONS"])
    add("unicode_codepoint_count", len(text), "codepoints", len(text), "a1.codepoints")
    add("base_mark_cluster_count", base_mark_clusters(text), "clusters",
        len(text), "a1.base_mark_clusters", ["NOT_UAX29_GRAPHEMES"])
    add("russian_letter_count", n_letters, "letters", n_letters, "a1.letters")
    for ch in RU_ALPHABET:
        add("letter_" + ch + "_count", letter_counts[ch], "letters",
            n_letters, "a1.letters")
    # A3: repeated textual letter sequences; never call them phonemes.
    for size in (2, 3):
        types, excess = letter_ngram_stats(ru_words, size)
        add("letter_" + str(size) + "gram_repeat_types",
            types, "types", n_ru, "a3.letter_ngrams")
        add("letter_" + str(size) + "gram_excess_occurrences",
            excess, "occurrences", n_ru, "a3.letter_ngrams")
    window_count, flagged = onset_windows(ru_words)
    add("onset_window_count", window_count, "windows", n_ru,
        "a3.onset_5_tokens", ["ORTHOGRAPHIC_NOT_PHONETIC"])
    add("onset_repetition_window_count", flagged, "windows", window_count,
        "a3.onset_5_tokens", ["ORTHOGRAPHIC_NOT_PHONETIC"])

    # A4: letter-vowel heuristic, not phonetic prosody/syllabification.
    add("russian_orthographic_syllable_total", sum(syllables), "syllables",
        n_ru, "a4.orthographic_vowel_count")
    add("russian_zero_vowel_token_count", sum(n == 0 for n in syllables),
        "tokens", n_ru, "a4.orthographic_vowel_count")
    if n_ru:
        add("russian_syllables_per_token_mean",
            round(sum(syllables) / n_ru, 8), "syllables/token",
            n_ru, "a4.orthographic_vowel_count")
        add("russian_syllables_per_token_median",
            statistics.median(syllables), "syllables/token",
            n_ru, "a4.orthographic_vowel_count")
    else:
        metrics.extend([
            unavailable("russian_syllables_per_token_mean", "NO_RUSSIAN_TOKENS"),
            unavailable("russian_syllables_per_token_median", "NO_RUSSIAN_TOKENS"),
        ])

    # A6: word-form aggregates only; no token dictionary to leak user text.
    types = len(ru_freqs)
    add("russian_wordform_type_count", types, "types", n_ru, "a6.wordforms")
    add("russian_hapax_type_count",
        sum(freq == 1 for freq in ru_freqs.values()), "types", n_ru,
        "a6.wordforms")
    add("russian_repeated_wordform_type_count",
        sum(freq > 1 for freq in ru_freqs.values()), "types", n_ru,
        "a6.wordforms")
    add("russian_repeated_wordform_excess",
        n_ru - types, "tokens", n_ru, "a6.wordforms")
    add("russian_max_wordform_frequency",
        max(ru_freqs.values(), default=0), "occurrences", n_ru,
        "a6.wordforms")
    if n_ru:
        add("russian_ttr", round(types / n_ru, 8), "ratio", n_ru,
            "a6.wordforms", ["TTR_LENGTH_SENSITIVE"])
    else:
        metrics.append(unavailable("russian_ttr", "NO_RUSSIAN_TOKENS"))

    # A7: 1-based position in the all-language token stream.
    if tokens:
        add("golden_section_token_index",
            min(len(tokens), max(1, round(PHI * len(tokens)))),
            "token_index_1_based", len(tokens), "a7.geometric_fraction",
            ["NO_PSYCHOLOGICAL_EFFECT_INFERRED"])
    else:
        metrics.append(unavailable("golden_section_token_index", "NO_TOKENS"))
    if reference is not None:
        from .a2 import calculate_reference
        metrics.extend(calculate_reference(decoded, reference[0], reference[1]))
    if morphology is not None:
        from .morphology import calculate_pos
        metrics.extend(calculate_pos(decoded, morphology))
    else:
        metrics.append(unavailable("pos_distribution", morphology_reason))
    metrics.extend([
        unavailable("norm_letter_deviation", "NORMATIVE_CORPUS_NOT_AVAILABLE"),
        unavailable("historical_suggestive_score",
                    "HISTORICAL_METHOD_NOT_VERIFIED"),
    ])
    return metrics
