"""EXPERIMENTAL arithmetic of A. P. Zhuravlev's word-level phonosemantic estimate.

This module implements only the *published arithmetic* (simple mean, the mean
of a 1–5 answer distribution and the weighted mean with first-sound ×4,
stressed-sound ×2 and the relative-rarity factor p_max / p_i). It ships NO
sound-letter score table, NO frequency table and NO orthography-to-sound
converter: the user supplies already segmented elements with their own
scores and frequencies, with rights they hold. Results are ``experimental``:
they are not historical program output, not «Диатон», not a measure of
persuasion, and not a quality score for marketing copy.

Published check vectors (A. P. Zhuravlev, «Звук и смысл»; author's online
edition https://proza.ru/2023/06/04/53) are in ``PUBLISHED_VECTORS`` and are
asserted by tests and ``scripts/benchmark_v08.py``.
"""
from __future__ import annotations

from typing import Any

FIRST_WEIGHT = 4.0
STRESS_WEIGHT = 2.0
MAX_ELEMENTS = 64
STATUS = "experimental"
WARNINGS = [
    "EXPERIMENTAL_ARITHMETIC_ONLY",
    "USER_SUPPLIED_SCORES_AND_FREQUENCIES",
    "NO_SOUND_TABLE_BUNDLED",
    "NOT_DIATON_NOT_HISTORICAL_PROGRAM_OUTPUT",
    "NO_PSYCHOLOGICAL_EFFECT_INFERRED",
]


class FormulaError(ValueError):
    """Fixed error codes only; user values are never echoed."""


def _number(value: Any, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormulaError(code)
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise FormulaError(code)
    return result


def simple_mean(scores: list[float]) -> float:
    """Arithmetic mean of element scores (book's first, unweighted attempt)."""
    if not scores:
        raise FormulaError("NO_ELEMENTS")
    values = [_number(s, "SCORE_NOT_A_NUMBER") for s in scores]
    for value in values:
        if not 1.0 <= value <= 5.0:
            raise FormulaError("SCORE_OUT_OF_RANGE")
    return sum(values) / len(values)


def distribution_mean(counts: dict[int, int]) -> float:
    """Mean scale answer from counts of answers 1..5 (e.g. 9×1, 34×2, ...)."""
    total = 0
    weighted = 0
    for answer, count in counts.items():
        if answer not in (1, 2, 3, 4, 5):
            raise FormulaError("ANSWER_OUT_OF_RANGE")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise FormulaError("COUNT_INVALID")
        total += count
        weighted += answer * count
    if total == 0:
        raise FormulaError("NO_ANSWERS")
    return weighted / total


def weighted_score(elements: list[dict]) -> dict:
    """F = Σ f_i·w_i / Σ w_i, w_i = (p_max/p_i) · 4[first] · 2[stressed].

    Each element: {"score": 1..5, "frequency": > 0, "first": bool,
    "stressed": bool}. Exactly one element may be first. Zero or missing
    frequency is rejected (the book's rule for p_i = 0 is not published).
    """
    if not isinstance(elements, list) or not elements:
        raise FormulaError("NO_ELEMENTS")
    if len(elements) > MAX_ELEMENTS:
        raise FormulaError("TOO_MANY_ELEMENTS")
    parsed = []
    for item in elements:
        if not isinstance(item, dict):
            raise FormulaError("ELEMENT_NOT_OBJECT")
        extra = set(item) - {"score", "frequency", "first", "stressed"}
        if extra:
            raise FormulaError("ELEMENT_UNKNOWN_FIELD")
        score = _number(item.get("score"), "SCORE_NOT_A_NUMBER")
        if not 1.0 <= score <= 5.0:
            raise FormulaError("SCORE_OUT_OF_RANGE")
        frequency = _number(item.get("frequency"), "FREQUENCY_NOT_A_NUMBER")
        if frequency <= 0:
            raise FormulaError("FREQUENCY_NOT_POSITIVE")
        first = item.get("first", False)
        stressed = item.get("stressed", False)
        if not isinstance(first, bool) or not isinstance(stressed, bool):
            raise FormulaError("FLAG_NOT_BOOLEAN")
        parsed.append((score, frequency, first, stressed))
    if sum(first for _, _, first, _ in parsed) > 1:
        raise FormulaError("MORE_THAN_ONE_FIRST_ELEMENT")
    p_max = max(frequency for _, frequency, _, _ in parsed)
    weights = [
        (p_max / frequency) * (FIRST_WEIGHT if first else 1.0)
        * (STRESS_WEIGHT if stressed else 1.0)
        for _, frequency, first, stressed in parsed
    ]
    weighted_sum = sum(score * w for (score, _, _, _), w in zip(parsed, weights, strict=True))
    total_weight = sum(weights)
    return {
        "status": STATUS,
        "value": round(weighted_sum / total_weight, 6),
        "weighted_sum": round(weighted_sum, 6),
        "weight_total": round(total_weight, 6),
        "weights": [round(w, 6) for w in weights],
        "n_elements": len(parsed),
        "warnings": list(WARNINGS),
    }


# Published arithmetic from the book, kept as short facts (no tables).
# "computed" is what this module returns; "published" is the printed number.
PUBLISHED_VECTORS = [
    {
        "id": "zh-dist-d-strong-weak",
        "what": "Средняя оценка звука Д по шкале «сильный — слабый»",
        "kind": "distribution_mean",
        "input": {"counts": {1: 9, 2: 34, 3: 5, 4: 2, 5: 0}},
        "published": 2.0,
        "decimals": 1,
    },
    {
        "id": "zh-lik-simple",
        "what": "«лик», простое среднее, «красивый — отталкивающий»",
        "kind": "simple_mean",
        "input": {"scores": [1.9, 2.0, 3.4]},
        "published": 2.4,
        "decimals": 1,
    },
    {
        "id": "zh-khrap-simple",
        "what": "«храп», простое среднее, «хороший — плохой»",
        "kind": "simple_mean",
        "input": {"scores": [4.1, 2.9, 1.5, 3.5]},
        "published": 3.0,
        "decimals": 1,
    },
    {
        "id": "zh-lik-weighted",
        "what": "«лик», взвешенная оценка: Л′ первый (×4, частотный множитель 1,76), "
                "И ударный (×2, множитель 2), К самый частый (1)",
        "kind": "weighted_score",
        # Frequencies chosen so that p_max/p_i equals the book's multipliers.
        "input": {"elements": [
            {"score": 1.9, "frequency": 1 / 1.76, "first": True, "stressed": False},
            {"score": 2.0, "frequency": 0.5, "first": False, "stressed": True},
            {"score": 3.4, "frequency": 1.0, "first": False, "stressed": False},
        ]},
        "expected_weights": [7.04, 4.0, 1.0],
        "expected_weighted_sum": 24.78,
        "expected_weight_total": 12.04,
        "published": 2.0,
        "decimals": 1,
        "known_discrepancy": "Arithmetic gives 2.058 (2.1 when rounded); the printed "
                             "value 2.0 suggests truncation. Recorded, not hidden.",
    },
    {
        "id": "zh-khrap-weighted-ratio",
        "what": "«храп», взвешенная оценка: отношение опубликованных сумм 110,92 / 29,22",
        "kind": "ratio",
        "input": {"weighted_sum": 110.92, "weight_total": 29.22},
        "published": 3.8,
        "decimals": 1,
    },
]


def evaluate_vector(vector: dict) -> dict:
    """Run one published vector through this module and compare."""
    kind = vector["kind"]
    if kind == "distribution_mean":
        computed = distribution_mean(vector["input"]["counts"])
        detail: dict = {}
    elif kind == "simple_mean":
        computed = simple_mean(vector["input"]["scores"])
        detail = {}
    elif kind == "ratio":
        computed = vector["input"]["weighted_sum"] / vector["input"]["weight_total"]
        detail = {}
    else:
        detail = weighted_score(vector["input"]["elements"])
        computed = detail["value"]
    rounded = round(computed, vector["decimals"])
    truncated = int(computed * 10 ** vector["decimals"]) / 10 ** vector["decimals"]
    matches_rounded = abs(rounded - vector["published"]) < 1e-9
    matches_truncated = abs(truncated - vector["published"]) < 1e-9
    return {
        "id": vector["id"],
        "computed": round(computed, 6),
        "published": vector["published"],
        "matches_published_rounding": matches_rounded,
        "matches_published_truncation": matches_truncated,
        "weights": detail.get("weights"),
        "weighted_sum": detail.get("weighted_sum"),
        "weight_total": detail.get("weight_total"),
        "known_discrepancy": vector.get("known_discrepancy"),
    }


def run(document: Any) -> dict:
    """CLI entry: exactly one of elements / scores / counts."""
    if not isinstance(document, dict):
        raise FormulaError("INPUT_NOT_OBJECT")
    keys = {"elements", "scores", "counts"} & set(document)
    if len(keys) != 1 or set(document) - {"elements", "scores", "counts", "scale"}:
        raise FormulaError("INPUT_NEEDS_EXACTLY_ONE_OF_ELEMENTS_SCORES_COUNTS")
    if "elements" in document:
        result = weighted_score(document["elements"])
        method = "zhuravlev.weighted_mean"
    elif "scores" in document:
        if not isinstance(document["scores"], list):
            raise FormulaError("SCORES_NOT_LIST")
        result = {"status": STATUS, "value": round(simple_mean(document["scores"]), 6),
                  "n_elements": len(document["scores"]), "warnings": list(WARNINGS)}
        method = "zhuravlev.simple_mean"
    else:
        raw = document["counts"]
        if not isinstance(raw, dict):
            raise FormulaError("COUNTS_NOT_OBJECT")
        try:
            counts = {int(k): v for k, v in raw.items()}
        except (TypeError, ValueError):
            raise FormulaError("ANSWER_OUT_OF_RANGE") from None
        result = {"status": STATUS, "value": round(distribution_mean(counts), 6),
                  "n_elements": sum(counts.values()), "warnings": list(WARNINGS)}
        method = "zhuravlev.distribution_mean"
    result["method_id"] = method
    return result
