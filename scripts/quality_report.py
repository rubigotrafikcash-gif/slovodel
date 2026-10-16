#!/usr/bin/env python3
"""Run tests and store a privacy-conservative machine-readable test result.

Only test IDs, counts and status are emitted; no fixture bodies or traceback
contents are included in the artifact.
"""
from __future__ import annotations

import argparse
import json
import platform
import unittest
from pathlib import Path


class LoggedResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test.id())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    ns = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).resolve().parents[1] / "tests")
    )
    result = LoggedResult()
    suite.run(result)
    failed = sorted(x.id() for x, _ in result.failures)
    errored = sorted(x.id() for x, _ in result.errors)
    skipped = sorted(x.id() for x, _ in result.skipped)
    payload = {
        "format": "slovodel.test-results.v1",
        "python_version": platform.python_version(),
        "tests_run": result.testsRun,
        "passed_count": len(result.passed),
        "failure_count": len(failed),
        "error_count": len(errored),
        "skipped_count": len(skipped),
        "passed_ids": sorted(result.passed),
        "failed_ids": failed,
        "error_ids": errored,
        "skipped_ids": skipped,
        "result": "PASS" if result.wasSuccessful() else "FAIL",
        "source_content": "synthetic_fixtures_only",
    }
    path = Path(ns.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    print("UNITTEST_JSON:", payload["result"], result.testsRun,
          "passed", payload["passed_count"],
          "failed", len(failed) + len(errored),
          "skipped", len(skipped))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
