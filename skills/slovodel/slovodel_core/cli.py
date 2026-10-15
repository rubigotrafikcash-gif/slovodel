"""Command-line interface shared by analyze.py and compare.py."""
from __future__ import annotations

import argparse
import json
import sys

from .io import DataError, emit_json, read_text
from .reports import audit, compare


def execute(command: str, args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slovodel-" + command,
        description="Offline Slovodel orthographic metrics; no historical scores.",
    )
    if command == "analyze":
        parser.add_argument("--input", required=True)
        parser.add_argument("--mode", choices=["audit"], default="audit")
    elif command == "compare":
        parser.add_argument("--before", required=True)
        parser.add_argument("--after", required=True)
    else:
        raise ValueError("Unsupported command")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--output", help="Create a new JSON file (never overwrite).")
    namespace = parser.parse_args(args)
    try:
        if command == "analyze":
            raw, decoded = read_text(namespace.input)
            document = audit(raw, decoded)
        else:
            before_raw, before = read_text(namespace.before)
            after_raw, after = read_text(namespace.after)
            document = compare(before_raw, before, after_raw, after)
        serialized = json.dumps(
            document, ensure_ascii=False, sort_keys=True, indent=2
        )
        emit_json(serialized, namespace.output)
        return 0
    except DataError as error:
        print("SLOVODEL_ERROR: " + str(error), file=sys.stderr)
        return 3 if str(error).startswith("INPUT_") else 4


def main(command: str) -> None:
    raise SystemExit(execute(command))
