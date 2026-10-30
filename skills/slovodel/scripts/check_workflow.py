#!/usr/bin/env python3
"""Run Core and verify its evidence, capturing the actual Core exit code."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from slovodel_core.checked_workflow import main

if __name__=='__main__':main()
