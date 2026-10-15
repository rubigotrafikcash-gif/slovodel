#!/usr/bin/env python3
"""Re-run public, short Zhuravlev word examples with actual Slovodel Core v0.7.

Whole Cherepanova examples in the input manifest are PRIOR v0.6 research
results, not reproduced copyrighted texts and NOT re-executed by this script.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "slovodel"))
from slovodel_core.reports import audit  # noqa: E402
from slovodel_core import __version__  # noqa: E402


def benchmark() -> dict:
    cases = json.loads((ROOT / "evals" / "primary-v07.json").read_text(encoding="utf-8"))
    word_results = []
    for entry in cases["word_cases"]:
        text = entry["input"]
        actual = audit(text.encode("utf-8"), text)
        metrics = {item["id"]: item for item in actual["measurements"]}
        hist = metrics["historical_suggestive_score"]
        if hist["status"] != "unavailable" or hist["value"] is not None:
            raise AssertionError("HISTORICAL_SCORE_FABRICATED")
        if metrics["russian_token_count"]["value"] != 1:
            raise AssertionError("REFERENCE_WORD_TOKENIZATION_FAILED")
        word_results.append({
            "id": entry["id"], "input": text, "published_scale": entry["scale"],
            "published_scale_value": entry["published"],
            "published_score_kind": entry["published_kind"],
            "source": entry["source"],
            "measured_core_version": __version__,
            "core_russian_letters": metrics["russian_letter_count"]["value"],
            "core_orthographic_vowels": metrics["russian_orthographic_syllable_total"]["value"],
            "core_a9_terminal_voiced_candidates": metrics["a9_final_voiced_letter_review_candidates"]["value"],
            "historical_score_status": hist["status"],
            "historical_score_value": hist["value"],
            "historical_value_difference": None,
            "comparability": "not_comparable"
        })
    # Older audit numbers are provenance data, not a fresh execution of the full
    # texts. Enforce this distinction in every machine-readable export.
    six = cases["text_cases"]
    if len(six) != 6 or any(item["v07_full_text_reexecution"] != "NOT_RUN_COPIED_SOURCE_TEXT_NOT_STORED" for item in six):
        raise AssertionError("SOURCE_TEXT_PROVENANCE_INVALID")
    return {
        "benchmark_version": "v0.7.0",
        "engine_version": __version__,
        "result": "PASS_WORD_REEXECUTION_NOT_COMPARABLE_TO_HISTORIC_SCORES",
        "z_word_scale_cases_executed": len(word_results),
        "ch_full_texts_executed_v07": 0,
        "ch_text_reference_records": len(six),
        "historical_program_executed": False,
        "historical_algorithm_similarity_percent": None,
        "word_runs": word_results,
        "ch_historical_v06_baseline_only": [
            {"id": x["id"], "title": x["title"],
             "published_mean_syllables": x["published_mean_syllables"],
             "previous_core_v06_orthographic_vowels_per_token":
                 x["previous_core_v06_orthographic_vowels_per_token"],
             "v07_full_text_reexecution": x["v07_full_text_reexecution"]}
            for x in six
        ],
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
    print("PRIMARY_BENCHMARK: PASS 10 word/scale examples; historical scores unavailable; 6 text baselines NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
