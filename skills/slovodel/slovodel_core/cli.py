"""Offline CLI: audit / compare / build an opt-in non-normative local profile."""
from __future__ import annotations

import argparse
import json
import sys

from .a2 import ProfileError, make_profile, parse_profile
from .io import DataError, emit_json, read_text
from .reports import audit, compare


def execute(command: str, args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slovodel-" + command,
        description="Offline Russian orthographic metrics; no official normative corpus.",
    )
    if command == "analyze":
        parser.add_argument("--input", required=True)
        parser.add_argument("--mode", choices=["audit"], default="audit")
        parser.add_argument("--reference", help="Local profile JSON (not normative).")
        parser.add_argument("--morphology", action="store_true",
                            help="Optional local pymorphy3 POS; no network.")
    elif command == "compare":
        parser.add_argument("--before", required=True)
        parser.add_argument("--after", required=True)
        parser.add_argument("--reference", help="Local profile JSON (not normative).")
        parser.add_argument("--morphology", action="store_true",
                            help="Optional local pymorphy3 POS; no network.")
    elif command == "validate":
        parser.add_argument("--before", required=True)
        parser.add_argument("--after", required=True)
        parser.add_argument("--protected-file",
                            help="UTF-8 lines of essential phrases (max 100).")
    elif command == "build-reference":
        parser.add_argument("--input", required=True)
        for arg in (
            "source-label", "source-url", "genre", "corpus-version",
            "license-id", "rights-basis",
        ):
            parser.add_argument("--" + arg, required=True)
    else:
        raise ValueError("Unsupported command")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--output", help="Create a new JSON file (never overwrite).")
    namespace = parser.parse_args(args)
    try:
        if command == "validate":
            import hashlib
            from .fact_guard import check, validate_terms
            before_raw, before = read_text(namespace.before)
            after_raw, after = read_text(namespace.after)
            terms = ()
            if namespace.protected_file is not None:
                _, term_text = read_text(namespace.protected_file)
                terms = validate_terms(term_text.splitlines())
            document = check(before, after, terms)
            document["source_sha256"] = hashlib.sha256(before_raw).hexdigest()
            document["revision_sha256"] = hashlib.sha256(after_raw).hexdigest()
            document["protected_terms_count"] = len(terms)
        elif command == "build-reference":
            raw, decoded = read_text(namespace.input)
            document = make_profile(
                raw, decoded,
                source_label=namespace.source_label,
                source_url=namespace.source_url,
                genre=namespace.genre,
                corpus_version=namespace.corpus_version,
                license_id=namespace.license_id,
                rights_basis=namespace.rights_basis,
            )
        else:
            morphology, morphology_reason = None, "MORPHOLOGY_OPT_IN_REQUIRED"
            if namespace.morphology:
                from .morphology import load_backend
                morphology, morphology_reason = load_backend()
            reference = None
            if namespace.reference is not None:
                _, local_json = read_text(namespace.reference)
                reference = parse_profile(local_json)
            if command == "analyze":
                raw, decoded = read_text(namespace.input)
                document = audit(raw, decoded, reference=reference,
                                 morphology=morphology,
                                 morphology_reason=morphology_reason)
            else:
                before_raw, before = read_text(namespace.before)
                after_raw, after = read_text(namespace.after)
                document = compare(
                    before_raw, before, after_raw, after, reference=reference,
                    morphology=morphology, morphology_reason=morphology_reason
                )
        serialized = json.dumps(
            document, ensure_ascii=False, sort_keys=True, indent=2
        )
        emit_json(serialized, namespace.output)
        return 5 if command == "validate" and document["decision"] == "blocked" else 0
    except ProfileError as error:
        # ProfileError inherits ValueError and must be caught first (A2).
        print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
        return 3
    except ValueError as error:
        # validate_terms uses fixed codes only; never echo arbitrary user text.
        if command == "validate":
            print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
            return 3
        raise
    except DataError as error:
        print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
        return 3 if str(error).startswith("INPUT_") else 4


def main(command: str) -> None:
    raise SystemExit(execute(command))
