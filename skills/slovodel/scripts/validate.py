#!/usr/bin/env python3
"""Validate protected facts between an original and edited UTF-8 text."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slovodel_core.cli import main  # noqa: E402

if __name__ == "__main__":
    main("validate")
