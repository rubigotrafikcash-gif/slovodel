"""Versioned, aggregate-only audit and compatible comparison reports."""
from __future__ import annotations

import hashlib
import unicodedata

from . import METHOD_VERSION, SCHEMA_VERSION, __version__
from .metrics import calculate


def source_info(raw: bytes, decoded: str) -> dict:
    normalized = unicodedata.normalize("NFC", decoded)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "normalization": "NFC",
        "normalization_changed": normalized != decoded,
        "offset_map_status": "not_implemented",
    }


def source_policy() -> dict:
    return {
        "network_access": False,
        "raw_text_in_report": False,
        "storage": "memory_only_unless_output_selected",
    }


def audit(raw: bytes, decoded: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "mode": "audit",
        "language": "ru",
        "language_detection": "not_performed",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source": source_info(raw, decoded),
        "source_policy": source_policy(),
        "measurements": calculate(decoded),
        "historical_compatibility": "not_verified",
        "warnings": (["EMPTY_INPUT"] if not decoded else []) +
            ["ORTHOGRAPHIC_NOT_PHONETIC",
             "URL_EMAIL_EXCLUSION_HEURISTIC",
             "NO_NORMATIVE_CORPUS"],
        "errors": [],
    }


def compare(
    before_raw: bytes, before: str, after_raw: bytes, after: str
) -> dict:
    before_items = {item["id"]: item for item in calculate(before)}
    after_items = {item["id"]: item for item in calculate(after)}
    pairs = []
    warnings = ["ORTHOGRAPHIC_NOT_PHONETIC",
                "URL_EMAIL_EXCLUSION_HEURISTIC",
                "NO_NORMATIVE_CORPUS"]
    for identifier, first in before_items.items():
        second = after_items[identifier]
        # Only measurements with matching method and dataset are comparable.
        if (first["status"] != "reproducible"
                or second["status"] != "reproducible"):
            continue
        if (first["method_id"], first["method_version"], first["dataset_id"]) != (
                second["method_id"], second["method_version"],
                second["dataset_id"]):
            warnings.append("METRIC_VERSION_MISMATCH:" + identifier)
            continue
        if identifier == "russian_ttr" and first["n"] != second["n"]:
            warnings.append("INCOMPARABLE_TTR_DIFFERENT_LENGTHS")
            continue
        change = second["value"] - first["value"]
        if isinstance(change, float):
            change = round(change, 8)
            if change == 0:
                change = 0.0
        pairs.append({
            "id": identifier,
            "before": first["value"],
            "after": second["value"],
            "delta": change,
            "unit": first["unit"],
            "method_id": first["method_id"],
            "method_version": first["method_version"],
            "dataset_id": first["dataset_id"],
            "n_before": first["n"],
            "n_after": second["n"],
            "warnings": list(dict.fromkeys(
                first["warnings"] + second["warnings"]
                + (["DIFFERENT_SAMPLE_SIZES"] if first["n"] != second["n"] else [])
            )),
        })
    if before_raw == after_raw:
        assert all(item["delta"] == 0 for item in pairs)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "mode": "compare",
        "language": "ru",
        "language_detection": "not_performed",
        "source_policy": source_policy(),
        "before": source_info(before_raw, before),
        "after": source_info(after_raw, after),
        "measurement_method_version": METHOD_VERSION,
        "comparison_status": "completed" if pairs else "unavailable",
        "comparisons": pairs,
        "historical_compatibility": "not_verified",
        "warnings": warnings if pairs else warnings + ["NO_COMPARABLE_MEASUREMENTS"],
        "errors": [],
    }
