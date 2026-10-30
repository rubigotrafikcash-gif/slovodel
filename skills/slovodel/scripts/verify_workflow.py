#!/usr/bin/env python3
"""Check Core report hashes, execution invariants and optional full schemas."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slovodel_core.verification import main  # noqa: E402

if __name__ == '__main__':
    main()
