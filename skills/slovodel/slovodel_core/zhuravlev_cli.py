"""CLI for the experimental Zhuravlev arithmetic (no bundled tables, no network)."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .io import DataError, emit_json, read_text
from .zhuravlev import FormulaError, run


def execute(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slovodel-zhuravlev",
        description="EXPERIMENTAL arithmetic of a published word-estimate formula "
                    "on YOUR scores and frequencies. Not Diaton, not a copy score.",
    )
    parser.add_argument("--input", required=True,
                        help="UTF-8 JSON with exactly one of elements/scores/counts.")
    parser.add_argument("--output", help="Create a new JSON file (never overwrite).")
    opts = parser.parse_args(argv)
    try:
        _, text = read_text(opts.input)
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            raise FormulaError("INPUT_NOT_JSON") from None
        result = run(document)
        result["tool_version"] = __version__
        result["schema_version"] = "1.0.0"
        emit_json(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2),
                  opts.output)
        return 0
    except FormulaError as error:
        print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
        return 3
    except DataError as error:
        print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
        return 3 if str(error).startswith("INPUT_") else 4


def main() -> None:
    raise SystemExit(execute())
