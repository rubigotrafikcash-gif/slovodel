"""Reproducible report skeleton. Metrics arrive in later GitHub issues."""
from __future__ import annotations

import hashlib
import unicodedata

from . import METHOD_VERSION, SCHEMA_VERSION, __version__


def source_info(raw: bytes, decoded: str) -> dict:
    normalized = unicodedata.normalize("NFC", decoded)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "normalization": "NFC",
        "normalization_changed": normalized != decoded,
        "offset_map_status": "not_implemented",
    }


def unavailable(identifier: str, reason: str) -> dict:
    return {
        "id": identifier,
        "value": None,
        "unit": None,
        "status": "unavailable",
        "method_id": None,
        "method_version": None,
        "dataset_id": None,
        "n": None,
        "warnings": [reason],
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
        "source_policy": {
            "network_access": False,
            "raw_text_in_report": False,
            "storage": "memory_only_unless_output_selected",
        },
        "measurements": [
            unavailable("token_count", "NOT_IMPLEMENTED_ISSUE_3"),
            unavailable("historical_suggestive_score", "HISTORICAL_METHOD_NOT_VERIFIED"),
        ],
        "historical_compatibility": "not_verified",
        "warnings": (["EMPTY_INPUT"] if not decoded else []) +
            ["NO_LINGUISTIC_METRICS_IMPLEMENTED"],
        "errors": [],
    }


def compare(
    before_raw: bytes, before: str, after_raw: bytes, after: str
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "mode": "compare",
        "language": "ru",
        "language_detection": "not_performed",
        "source_policy": {
            "network_access": False,
            "raw_text_in_report": False,
            "storage": "memory_only_unless_output_selected",
        },
        "before": source_info(before_raw, before),
        "after": source_info(after_raw, after),
        "measurement_method_version": METHOD_VERSION,
        "comparison_status": "unavailable",
        "comparisons": [],
        "historical_compatibility": "not_verified",
        "warnings": ["NO_COMPARABLE_MEASUREMENTS_IMPLEMENTED"],
        "errors": [],
    }
