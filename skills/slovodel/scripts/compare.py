#!/usr/bin/env python3
"""Compare source fingerprints; no linguistic delta metrics are implemented."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slovodel_core.cli import main  # noqa: E402

if __name__ == "__main__":
    main("compare")
