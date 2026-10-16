#!/usr/bin/env python3
"""EXPERIMENTAL: Zhuravlev word-estimate arithmetic on user-supplied scores."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slovodel_core.zhuravlev_cli import main  # noqa: E402

if __name__ == "__main__":
    main()
