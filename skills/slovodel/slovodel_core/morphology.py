"""Optional Russian POS counts via a separately installed pymorphy3 dictionary.

No dictionary distributed here. No automatic network or pip calls.
POS ambiguity means *multiple distinct POS tags*; we do not claim contextual
disambiguation or conflate dictionary candidate scores with probabilities.
"""
from __future__ import annotations

from collections import Counter
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
import unicodedata

from . import METHOD_VERSION
from .metrics import cleaned, measurement, russian_token, unavailable, words

ANALYZER_VERSION = "2.0.6"
DICTIONARY_VERSION = "2.4.417150.4580142"
TAGS = (
    "NOUN", "ADJF", "ADJS", "COMP", "VERB", "INFN", "PRTF", "PRTS",
    "GRND", "NUMR", "ADVB", "NPRO", "PRED", "PREP", "CONJ", "PRCL",
    "INTJ",
)
TAGS_SET = frozenset(TAGS)
WARNINGS = ["NO_CONTEXT_DISAMBIGUATION", "POS_DICTIONARY_CC_BY_SA",
            "POS_IS_NOT_PSYCHOLOGICAL_INFERENCE"]


def load_backend() -> tuple[tuple[object, str] | None, str | None]:
    """Require exact documented runtime and dictionary versions, no fallback.

    Does not fetch anything. If the dependency is absent/incompatible, report
    unavailable. If it is present but broken, do not expose exception text.
    """
    try:
        analyzer_version = version("pymorphy3")
        dictionary_version = version("pymorphy3-dicts-ru")
    except PackageNotFoundError:
        return None, "MORPHOLOGY_DEPENDENCY_NOT_INSTALLED"
    if (analyzer_version != ANALYZER_VERSION or
            dictionary_version != DICTIONARY_VERSION):
        return None, "MORPHOLOGY_VERSION_UNSUPPORTED"
    try:
        lib = import_module("pymorphy3")
        dictionaries = import_module("pymorphy3_dicts_ru")
        morph = lib.MorphAnalyzer(path=dictionaries.get_path(), lang="ru")
    except (ImportError, OSError, ValueError, RuntimeError, KeyError):
        return None, "MORPHOLOGY_BACKEND_UNAVAILABLE"
    dataset_id = (f"pymorphy3:{analyzer_version}|"
                  f"pymorphy3-dicts-ru:{dictionary_version}")
    return (morph, dataset_id), None


def token_pos(word: str, analyzer: object) -> str:
    """One of POS, AMBIGUOUS, OOV, UNCLASSIFIED.

    Only known dictionary parses with a *unique* POS contribute to POS totals.
    Different grammatical cases of one POS do not count as POS ambiguity.
    """
    try:
        parses = analyzer.parse(word)
    except (AttributeError, OSError, RuntimeError, ValueError, KeyError):
        return "UNCLASSIFIED"
    if not parses:
        return "UNCLASSIFIED"
    known = [p for p in parses if bool(getattr(p, "is_known", False))]
    if not known:
        return "OOV"
    tags = {getattr(getattr(p, "tag", None), "POS", None) for p in known}
    if None in tags or not tags or any(tag not in TAGS_SET for tag in tags):
        return "UNCLASSIFIED"
    return next(iter(tags)) if len(tags) == 1 else "AMBIGUOUS"


def pos_measure(
    identifier: str, value: int | float, unit: str, n: int, dataset: str
) -> dict:
    item = measurement(identifier, value, unit, n, "a5.pymorphy3.unique_pos",
                       list(WARNINGS))
    item["dataset_id"] = dataset
    return item


def calculate_pos(decoded: str, backend: tuple[object, str]) -> list[dict]:
    """Return privacy-preserving aggregates, never surface source wordforms."""
    analyzer, dataset_id = backend
    text = unicodedata.normalize("NFC", decoded)
    tokens = [w for w in words(cleaned(text)) if russian_token(w)]
    total = len(tokens)
    groups = Counter(token_pos(w, analyzer) for w in tokens)
    resolved = sum(groups[tag] for tag in TAGS)
    output = []
    for tag in TAGS:
        output.append(pos_measure(
            "pos_" + tag.lower() + "_count", groups[tag], "tokens",
            total, dataset_id
        ))
        if total:
            output.append(pos_measure(
                "pos_" + tag.lower() + "_share",
                round(groups[tag] / total, 8), "ratio",
                total, dataset_id
            ))
        else:
            output.append(unavailable("pos_" + tag.lower() + "_share",
                                      "NO_RUSSIAN_TOKENS"))
    for key, label in (
        ("AMBIGUOUS", "pos_ambiguous_token_count"),
        ("OOV", "pos_oov_token_count"),
        ("UNCLASSIFIED", "pos_unclassified_token_count"),
    ):
        output.append(pos_measure(label, groups[key], "tokens", total,
                                  dataset_id))
    output.append(pos_measure("pos_resolved_token_count", resolved, "tokens",
                              total, dataset_id))
    if total:
        output.append(pos_measure("pos_coverage_ratio",
                                  round(resolved / total, 8), "ratio",
                                  total, dataset_id))
    else:
        output.append(unavailable("pos_coverage_ratio", "NO_RUSSIAN_TOKENS"))
    return output
