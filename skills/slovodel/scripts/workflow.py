#!/usr/bin/env python3
"""Offline orchestration for agent-created text; no LLM calls are made here."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slovodel_core.workflow_cli import main  # noqa: E402

if __name__ == "__main__":
    main()
