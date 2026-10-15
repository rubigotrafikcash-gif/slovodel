"""Offline evidence bundle for the four public Slovodel editorial workflows.

This program does NOT generate, rewrite, approve, or publish prose. The AI
editor supplies draft files. Each step calls actual Core functions and records
only hashes, aggregate statistics and protected-fact categories.
"""
from __future__ import annotations

import hashlib
import re

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
    kw = {"reference": reference, "morphology": morphology,
          "morphology_reason": morphology_reason}
    report = {
        "workflow_schema_version": SCHEMA,
        "tool_version": __version__,
        "mode": mode,
        "execution": "local_core_executed",
        "ai_text_generation": "external_to_this_workflow",
        "publication_ready": False,
        "decision": "",
        "steps_executed": [],
        "pre_analysis": None,
        "post_analysis": None,
        "comparison": None,
        "fact_guard": None,
        "warnings": ["NO_AUTO_PUBLICATION", "NO_SEMANTIC_EQUIVALENCE_PROVEN"],
    }
    if mode == "audit":
        report["pre_analysis"] = audit(*input_doc, **kw)
        report["steps_executed"] = ["analyze_input"]
        report["decision"] = "audit_only"
    elif mode == "create":
        report["post_analysis"] = audit(*input_doc, **kw)
        report["steps_executed"] = ["analyze_agent_draft"]
        report["decision"] = "draft_requires_review"
        if PLACEHOLDER.search(input_doc[1]):
            report["warnings"].append("UNRESOLVED_PLACEHOLDER_DETECTED")
        report["warnings"].append("BRIEF_FACTS_NOT_AUTOMATICALLY_VERIFIED")
    elif mode == "rewrite":
        report["pre_analysis"] = audit(*before_doc, **kw)
        report["fact_guard"] = guard_report(before_doc, after_doc,
                                             protected_terms)
        report["post_analysis"] = audit(*after_doc, **kw)
        report["comparison"] = compare(
            *before_doc, *after_doc, **kw
        )
        report["steps_executed"] = [
            "analyze_original", "check_agent_edit_facts",
            "analyze_agent_revision", "compare_reproducible_metrics"
        ]
        report["decision"] = (
            "blocked" if report["fact_guard"]["decision"] == "blocked"
            else "draft_requires_review"
        )
        if report["decision"] == "blocked":
            report["warnings"].append("PUBLICATION_BLOCKED_BY_FACT_GUARD")
    else:
        report["pre_analysis"] = audit(*before_doc, **kw)
        report["post_analysis"] = audit(*after_doc, **kw)
        report["comparison"] = compare(*before_doc, *after_doc, **kw)
        report["fact_guard"] = guard_report(before_doc, after_doc,
                                             protected_terms)
        report["steps_executed"] = [
            "analyze_first", "analyze_second",
            "compare_reproducible_metrics", "screen_fact_differences"
        ]
        report["decision"] = "comparison_only"
        if report["fact_guard"]["decision"] == "blocked":
            report["warnings"].append("PROTECTED_FACTS_DIFFER")
    return report
