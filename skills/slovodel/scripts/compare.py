#!/usr/bin/env python3
"""Compare compatible numeric measurements without historic/semantic scores."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slovodel_core.cli import main  # noqa: E402

if __name__ == "__main__":
    main("compare")
