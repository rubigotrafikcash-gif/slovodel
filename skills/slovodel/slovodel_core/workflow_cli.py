"""Four editorial modes, real local calculations, no autonomous AI editor."""
from __future__ import annotations

import argparse
import json
import sys

from .a2 import ProfileError, parse_profile
from .fact_guard import validate_terms
from .io import DataError, emit_json, read_text
from .workflow import MODES, build


def execute(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slovodel-workflow",
        description="Run offline reports around externally authored text (no AI generation).",
    )
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--input", help="Source for audit; finished draft for create.")
    parser.add_argument("--before", help="Original version for rewrite/compare.")
    parser.add_argument("--after", help="Externally edited/second version.")
    parser.add_argument("--protected-file", help="Mandatory phrases, one per line.")
    parser.add_argument("--reference", help="User-supplied NON-normative A2 profile.")
    parser.add_argument("--morphology", action="store_true",
                        help="Use local installed pinned POS backend if available.")
    parser.add_argument("--output", help="Create new JSON file, no overwrite.")
    opts = parser.parse_args(argv)
    single = opts.mode in ("audit", "create")
    if (single and (not opts.input or opts.before or opts.after or
                    opts.protected_file)) or (
        not single and (opts.input or not opts.before or not opts.after)
    ):
        parser.error("invalid input files for selected mode")
    try:
        reference = None
        if opts.reference:
            _, raw_json = read_text(opts.reference)
            reference = parse_profile(raw_json)
        morphology, morphology_reason = None, "MORPHOLOGY_OPT_IN_REQUIRED"
        if opts.morphology:
            from .morphology import load_backend
            morphology, morphology_reason = load_backend()
        terms = ()
        if opts.protected_file:
            _, text = read_text(opts.protected_file)
            terms = validate_terms(text.splitlines())
        inp = read_text(opts.input) if single else None
        bef = read_text(opts.before) if not single else None
        aft = read_text(opts.after) if not single else None
        document = build(
            opts.mode, input_doc=inp, before_doc=bef, after_doc=aft,
            reference=reference, morphology=morphology,
            morphology_reason=morphology_reason, protected_terms=terms
        )
        payload = json.dumps(document, ensure_ascii=False,
                             sort_keys=True, indent=2)
        emit_json(payload, opts.output)
        return 5 if document["decision"] == "blocked" else 0
    except ProfileError as error:
        print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
        return 3
    except DataError as error:
        print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
        return 3 if str(error).startswith("INPUT_") else 4
    except ValueError:
        # Important: arbitrary exception data never escapes.
        print("SLOVODEL_ERROR: WORKFLOW_INPUT_INVALID", file=sys.stderr)
        return 3


def main() -> None:
    raise SystemExit(execute())
