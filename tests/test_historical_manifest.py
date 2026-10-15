"""Issue #11: research-only historical matrix integrity, NO historical scoring."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/research/historical-scale-matrix.json"
RESEARCH = ROOT / "docs/research/ISSUE_11_SOURCE_AUDIT.md"


class HistoricalAuditIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(MATRIX.read_text(encoding="utf-8"))
        cls.rows = cls.record["rows"]

    def test_25_word_scales_and_20_distinct_text_slots(self):
        words = [x for x in self.rows if x["object"] == "single_word_sound_letter_semantic_differential"]
        texts = [x for x in self.rows if x["object"] == "whole_text_diaton_20_scale"]
        funcs = [x for x in self.rows if x["object"] == "historical_function_group"]
        self.assertEqual([x["id"] for x in words], [f"ZH-W{i:02d}" for i in range(1, 26)])
        self.assertEqual([x["id"] for x in texts], [f"CH-T{i:02d}" for i in range(1, 21)])
        self.assertEqual([x["id"] for x in funcs], [f"H-F{i:02d}" for i in range(1, 12)])
        self.assertEqual(len(self.rows), 56)
        self.assertEqual(len({x["id"] for x in self.rows}), 56)
        self.assertTrue(all(x["name"] is None and x["formula"] is None for x in texts))
        self.assertTrue(all(x["source_id"] == "zhuravlev_1991" and x["name"] for x in words))

    def test_every_historical_score_remains_null_and_unavailable(self):
        self.assertEqual(self.record["default_runtime_status"], "unavailable")
        self.assertEqual(self.record["independent_original_diaton_equivalence"], "not_verified")
        for item in self.rows:
            with self.subTest(item=item["id"]):
                self.assertEqual(item["runtime_status"], "unavailable")
                self.assertIsNone(item["runtime_value"])
                self.assertNotEqual(item["research_status"], "reproducible")
                self.assertEqual(item["license_status"], "redistribution_permission_not_verified")
                self.assertTrue(item["decision"])

    def test_references_and_formula_data_fields(self):
        sources = self.record["sources"]
        for item in self.rows:
            with self.subTest(item=item["id"]):
                self.assertIn(item["source_id"], sources)
                self.assertTrue(sources[item["source_id"]]["url"].startswith("https://"))
                self.assertTrue(item["input_data"])
                self.assertIn("data_verified", item)
                self.assertIn("formula", item)
        weight = next(x for x in self.rows if x["id"] == "H-F01")
        self.assertIn("p_max/p_i", weight["formula"])
        text = next(x for x in self.rows if x["id"] == "H-F04")
        self.assertIsNone(text["formula"])

    def test_printed_sample_arithmetic_is_explicitly_rechecked(self):
        # Published intermediate sums for "lik". This does not recreate a scale
        # and deliberately uses no third-party copyrighted score matrix.
        val = 24.78 / 12.04
        self.assertAlmostEqual(val, 2.05814, places=5)
        self.assertEqual(round(val, 1), 2.1)
        self.assertEqual(round(110.92 / 29.22, 1), 3.8)
        self.assertEqual(46 * 25, 1150)
        self.assertNotEqual(346 * 25, 1150)

    def test_research_says_no_go_without_open_licensed_data(self):
        report = RESEARCH.read_text(encoding="utf-8")
        for term in ("NO_GO_NUMERICAL_RELEASE", "25 шкал слова",
                     "20 шкал текста", "ЧЕРЕПАНОВА"):
            # equivalent case-insensitive reference for historical name
            with self.subTest(term=term):
                self.assertIn(term.casefold(), report.casefold())
        self.assertIn("runtime_status", report)
        self.assertIn("нулевой частоты", report)


if __name__ == "__main__":
    unittest.main()
