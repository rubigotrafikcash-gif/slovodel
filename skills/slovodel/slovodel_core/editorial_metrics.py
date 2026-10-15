"""v0.7 independent editorial diagnostics for texts written in Russian.

These are deterministic token/orthographic measurements, NOT measurements of
persuasion, emotional influence, phonetic valence, or historical Diaton scores.
The final-devoicing counter flags SPELLING patterns for a human/agent review;
it does not transcribe sound or resolve pronunciation exceptions.
"""
from __future__ import annotations

import re
from .metrics import (ABBREV, PHI, VOWELS, cleaned, measurement,
                      russian_token, unavailable, words)

FINAL_VOICED = re.compile(r"[бвгджз]ь?$")


def _sentence_lengths(text: str) -> list[int]:
    """Follow existing A1 sentence heuristic; return nonempty token lengths."""
    text = ABBREV.sub(lambda m: m.group().replace(".", " "), text)
    chars = list(text)
    for index in range(1, len(chars) - 1):
        if chars[index] == "." and chars[index - 1].isdigit() and chars[index + 1].isdigit():
            chars[index] = " "
    return [len(part_tokens) for segment in re.split(r"[.!?\u2026]+", "".join(chars))
            if (part_tokens := words(segment))]


def extra_metrics(decoded: str) -> list[dict]:
    """Compute editor-friendly, source-free aggregates without touching v0.6 metrics."""
    safe = cleaned(decoded)
    tokens = words(safe)
    ru = [token for token in tokens if russian_token(token)]
    n = len(ru)
    lengths = _sentence_lengths(safe)
    result = []

    def add(identifier: str, value: int | float, unit: str,
            sample: int, section: str, warnings: list[str] | None = None) -> None:
        result.append(measurement(identifier, value, unit, sample, section, warnings))

    pronounced_candidates = sum(bool(FINAL_VOICED.search(token)) for token in ru)
    add("a9_final_voiced_letter_review_candidates", pronounced_candidates, "tokens",
        n, "a9.spelling_final_voiced", [
            "SPELLING_HEURISTIC_NOT_IPA", "NOT_A_PHONETIC_TRANSCRIPTION",
            "EXCEPTIONS_AND_CONTEXT_NOT_RESOLVED",
        ])
    multisyllabic = sum(sum(ch in VOWELS for ch in token) >= 3 for token in ru)
    add("a4_words_3plus_vowels_count", multisyllabic, "tokens", n,
        "a4.vowels_3plus", ["ORTHOGRAPHIC_NOT_PHONETIC"])
    with_vowels = [sum(ch in VOWELS for ch in token) for token in ru
                   if any(ch in VOWELS for ch in token)]
    add("a4_words_with_vowels_count", len(with_vowels), "tokens", n,
        "a4.nonzero_vowel_tokens")
    if with_vowels:
        add("a4_vowels_per_nonzero_word_mean",
            round(sum(with_vowels) / len(with_vowels), 8), "vowels/token",
            len(with_vowels), "a4.nonzero_vowel_mean",
            ["DIFFERENT_DENOMINATOR_FROM_A4", "NOT_HISTORICAL_CHEREPANOVA"])
    else:
        result.append(unavailable("a4_vowels_per_nonzero_word_mean",
                                  "NO_TOKENS_WITH_VOWELS"))
    add("a7_sentence_count_by_segmentation", len(lengths), "sentences", len(tokens),
        "a7.sentence_windows", ["PUNCTUATION_HEURISTIC_NOT_SEMANTIC"])
    add("a7_max_sentence_length_tokens", max(lengths, default=0), "tokens",
        len(lengths), "a7.sentence_windows", ["PUNCTUATION_HEURISTIC_NOT_SEMANTIC"])
    add("a7_sentences_over_25_tokens", sum(v > 25 for v in lengths),
        "sentences", len(lengths), "a7.sentence_windows",
        ["EDITORIAL_THRESHOLD_NOT_QUALITY_SCORE"])
    if tokens and lengths:
        index = min(len(tokens), max(1, round(PHI * len(tokens))))
        accum = 0
        for ordinal, size in enumerate(lengths, 1):
            accum += size
            if accum >= index:
                add("a7_golden_section_sentence_ordinal", ordinal, "sentence_index_1_based",
                    len(tokens), "a7.sentence_position",
                    ["ORTHOGRAPHIC_POSITION_NOT_AUTHOR_INTENTION",
                     "NO_PSYCHOLOGICAL_EFFECT_INFERRED"])
                add("a7_golden_section_sentence_length_tokens", size, "tokens",
                    len(tokens), "a7.sentence_position",
                    ["PUNCTUATION_HEURISTIC_NOT_SEMANTIC"])
                break
    else:
        result.extend([
            unavailable("a7_golden_section_sentence_ordinal", "NO_TOKENS"),
            unavailable("a7_golden_section_sentence_length_tokens", "NO_TOKENS"),
        ])
    return result
