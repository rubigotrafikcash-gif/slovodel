"""Offline evidence bundle for the four public Slovodel editorial workflows.

This program does NOT generate, rewrite, approve, or publish prose. The AI
editor supplies draft files. Each step calls actual Core functions and records
only hashes, aggregate statistics and protected-fact categories.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from . import __version__
from .fact_guard import check as check_facts
from .reports import audit, compare

SCHEMA = "1.0.0"
MODES = ("audit", "rewrite", "create", "compare")
# Detect explicitly unresolved placeholders; not a complete factual validator.
PLACEHOLDER = re.compile(r"\[[^\[\]\n]{1,120}\]")


def guard_report(
    original: tuple[bytes, str],
    revision: tuple[bytes, str],
    terms: tuple[str, ...],
) -> dict:
    """Match standalone validate.py fact-guard schema exactly."""
    report = check_facts(original[1], revision[1], terms)
    report["source_sha256"] = hashlib.sha256(original[0]).hexdigest()
    report["revision_sha256"] = hashlib.sha256(revision[0]).hexdigest()
    report["protected_terms_count"] = len(terms)
    return report


def build(
    mode: str, *, input_doc: tuple[bytes, str] | None = None,
    before_doc: tuple[bytes, str] | None = None,
    after_doc: tuple[bytes, str] | None = None,
    reference: tuple[dict, str] | None = None,
    morphology: tuple[object, str] | None = None,
    morphology_reason: str = "MORPHOLOGY_OPT_IN_REQUIRED",
    protected_terms: tuple[str, ...] = (),
) -> dict:
    if mode not in MODES:
        raise ValueError("WORKFLOW_INVALID_MODE")
    if mode in ("audit", "create"):
        if input_doc is None or before_doc is not None or after_doc is not None:
            raise ValueError("WORKFLOW_MISSING_OR_EXTRA_INPUT")
        if protected_terms:
            raise ValueError("WORKFLOW_TERMS_RESTRICTED_TO_TWO_TEXT_MODES")
    else:
        if input_doc is not None or before_doc is None or after_doc is None:
            raise ValueError("WORKFLOW_MISSING_OR_EXTRA_INPUT")
    empty: tuple[bytes, str] = (b"", "")
    single = input_doc or empty
    first = before_doc or empty
    second = after_doc or empty

    def run_audit(doc: tuple[bytes, str]) -> dict:
        return audit(doc[0], doc[1], reference=reference, morphology=morphology,
                     morphology_reason=morphology_reason)

    def run_compare(first: tuple[bytes, str], second: tuple[bytes, str]) -> dict:
        return compare(first[0], first[1], second[0], second[1],
                       reference=reference, morphology=morphology,
                       morphology_reason=morphology_reason)

    warnings: list[str] = ["NO_AUTO_PUBLICATION", "NO_SEMANTIC_EQUIVALENCE_PROVEN"]
    steps: list[str] = []
    report: dict[str, Any] = {
        "workflow_schema_version": SCHEMA,
        "tool_version": __version__,
        "mode": mode,
        "execution": "local_core_executed",
        "ai_text_generation": "external_to_this_workflow",
        "publication_ready": False,
        "decision": "",
        "steps_executed": steps,
        "pre_analysis": None,
        "post_analysis": None,
        "comparison": None,
        "fact_guard": None,
        "warnings": warnings,
    }
    if mode == "audit":
        report["pre_analysis"] = run_audit(single)
        steps.append("analyze_input")
        report["decision"] = "audit_only"
    elif mode == "create":
        report["post_analysis"] = run_audit(single)
        steps.append("analyze_agent_draft")
        report["decision"] = "draft_requires_review"
        if PLACEHOLDER.search(single[1]):
            warnings.append("UNRESOLVED_PLACEHOLDER_DETECTED")
        warnings.append("BRIEF_FACTS_NOT_AUTOMATICALLY_VERIFIED")
    elif mode == "rewrite":
        report["pre_analysis"] = run_audit(first)
        guard = guard_report(first, second, protected_terms)
        report["fact_guard"] = guard
        report["post_analysis"] = run_audit(second)
        report["comparison"] = run_compare(first, second)
        steps.extend([
            "analyze_original", "check_agent_edit_facts",
            "analyze_agent_revision", "compare_reproducible_metrics"
        ])
        report["decision"] = (
            "blocked" if guard["decision"] == "blocked"
            else "draft_requires_review"
        )
        if report["decision"] == "blocked":
            warnings.append("PUBLICATION_BLOCKED_BY_FACT_GUARD")
        if any(item["severity"] == "review"
               for item in guard["findings"]):
            warnings.append("FACT_GUARD_REVIEW_ITEMS")
    else:
        report["pre_analysis"] = run_audit(first)
        report["post_analysis"] = run_audit(second)
        report["comparison"] = run_compare(first, second)
        guard = guard_report(first, second, protected_terms)
        report["fact_guard"] = guard
        steps.extend([
            "analyze_first", "analyze_second",
            "compare_reproducible_metrics", "screen_fact_differences"
        ])
        report["decision"] = "comparison_only"
        if guard["decision"] == "blocked":
            warnings.append("PROTECTED_FACTS_DIFFER")
        if any(item["severity"] == "review"
               for item in guard["findings"]):
            warnings.append("FACT_GUARD_REVIEW_ITEMS")
    return report
