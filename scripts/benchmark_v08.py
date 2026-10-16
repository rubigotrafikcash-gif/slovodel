#!/usr/bin/env python3
"""v0.8 primary-source benchmark that actually compares numbers.

1. Zhuravlev's published arithmetic (answer distribution, simple means, the
   weighted estimate of «лик», the ratio for «храп») is recomputed by the
   experimental kernel and compared with the printed values. A mismatch that
   neither rounding nor truncation explains FAILS the benchmark; the known
   «лик» truncation is reported, not hidden.
2. The v0.7 word cases are re-run through Core 0.8 to prove that no
   historical score is fabricated (historical_suggestive_score stays null).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "slovodel"))
from slovodel_core import __version__  # noqa: E402
from slovodel_core.reports import audit  # noqa: E402
from slovodel_core.zhuravlev import PUBLISHED_VECTORS, evaluate_vector  # noqa: E402


def benchmark() -> dict:
    formula_runs = []
    for vector in PUBLISHED_VECTORS:
        result = evaluate_vector(vector)
        if not (result["matches_published_rounding"]
                or result["matches_published_truncation"]):
            raise AssertionError("PUBLISHED_VECTOR_MISMATCH:" + vector["id"])
        if "expected_weights" in vector:
            if [round(w, 2) for w in result["weights"]] != vector["expected_weights"]:
                raise AssertionError("PUBLISHED_WEIGHTS_MISMATCH:" + vector["id"])
            if round(result["weighted_sum"], 2) != vector["expected_weighted_sum"]:
                raise AssertionError("PUBLISHED_SUM_MISMATCH:" + vector["id"])
            if round(result["weight_total"], 2) != vector["expected_weight_total"]:
                raise AssertionError("PUBLISHED_WEIGHT_TOTAL_MISMATCH:" + vector["id"])
        formula_runs.append(result)
    cases = json.loads((ROOT / "evals" / "primary-v07.json").read_text(encoding="utf-8"))
    word_runs = []
    for entry in cases["word_cases"]:
        text = entry["input"]
        metrics = {m["id"]: m for m in audit(text.encode("utf-8"), text)["measurements"]}
        hist = metrics["historical_suggestive_score"]
        if hist["status"] != "unavailable" or hist["value"] is not None:
            raise AssertionError("HISTORICAL_SCORE_FABRICATED")
        word_runs.append({"id": entry["id"], "published_scale_value": entry["published"],
                          "historical_score_value": None,
                          "comparability": "not_comparable_needs_user_score_table"})
    rounding = sum(r["matches_published_rounding"] for r in formula_runs)
    return {
        "benchmark_version": "v0.8.0",
        "engine_version": __version__,
        "formula_vectors": len(formula_runs),
        "formula_vectors_matching_rounding": rounding,
        "formula_vectors_matching_only_truncation": sum(
            r["matches_published_truncation"] and not r["matches_published_rounding"]
            for r in formula_runs),
        "formula_runs": formula_runs,
        "word_cases_without_fabricated_scores": len(word_runs),
        "word_runs": word_runs,
        "historical_program_executed": False,
        "source": "А. П. Журавлёв, «Звук и смысл» (1981/1991); сетевое издание автора "
                  "https://proza.ru/2023/06/04/53",
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Write fresh JSON to a new path")
    args = parser.parse_args()
    result = benchmark()
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    print(f"PRIMARY_BENCHMARK_V08: PASS {result['formula_vectors']} Zhuravlev vectors "
          f"({result['formula_vectors_matching_rounding']} by rounding, "
          f"{result['formula_vectors_matching_only_truncation']} only by truncation); "
          f"{result['word_cases_without_fabricated_scores']} word cases without fabricated scores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
