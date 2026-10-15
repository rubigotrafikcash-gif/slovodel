"""Issue #9 deterministic behavior, corpus mismatch, privacy and error regressions."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/slovodel"))

from slovodel_core import reports
from slovodel_core.a2 import (ProfileError, compare_rate, make_profile,
                              parse_profile, calculate_reference)
from slovodel_core.fact_guard import check, inventory, validate_terms
from slovodel_core.io import DataError, emit_json, read_text
from slovodel_core.metrics import (RU_ALPHABET, calculate, measurement,
                                   unavailable)
from slovodel_core.workflow import build, guard_report

FIXTURE = ROOT / "tests/fixtures/issue9_cases.json"


def doc(text):
    return text.encode("utf-8"), text


def reference():
    return make_profile(
        *doc("мама мама"), source_label="synthetic",
        source_url="local://self-authored", genre="test",
        corpus_version="v1", license_id="CC0-1.0",
        rights_basis="self authored synthetic data only",
    )


class FixtureRegressions(unittest.TestCase):
    def test_all_fact_guard_fixtures(self):
        config = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(config["cases"]), 15)
        self.assertEqual(len({x["id"] for x in config["cases"]}),
                         len(config["cases"]))
        for row in config["cases"]:
            with self.subTest(case=row["id"]):
                terms = validate_terms(row["terms"])
                guard = check(row["before"], row["after"], terms)
                self.assertEqual(guard["decision"], row["decision"])
                self.assertFalse(guard["publish_ready"])
                self.assertEqual(guard["semantic_equivalence"], "not_verified")
                if row["expected_kind"] is not None:
                    self.assertIn(row["expected_kind"],
                                  {x["kind"] for x in guard["findings"]})
                self.assertNotIn(row["before"], json.dumps(guard,
                                                          ensure_ascii=False))
                self.assertNotIn(row["after"], json.dumps(guard,
                                                         ensure_ascii=False))

    def test_each_fixture_in_workflow(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        for row in cases:
            with self.subTest(case=row["id"]):
                report = build("rewrite", before_doc=doc(row["before"]),
                               after_doc=doc(row["after"]),
                               protected_terms=validate_terms(row["terms"]))
                expected = ("blocked" if row["decision"] == "blocked"
                            else "draft_requires_review")
                self.assertEqual(report["decision"], expected)
                self.assertFalse(report["publication_ready"])
                self.assertTrue(report["comparison"]["comparisons"])
                self.assertNotIn("historical_suggestive_score",
                                 {x["id"] for x in report["comparison"]["comparisons"]})


class DeterministicKernelTests(unittest.TestCase):
    def test_no_reproducible_metric_has_null_numeric_value(self):
        texts = ("", "hello", "Ёж е\u0308ж", "мама-мама, 2 кота! 😀",
                 "https://site.example/page?x=3", "Хочу? Не хочу.")
        for text in texts:
            with self.subTest(text=text):
                rows = calculate(text)
                self.assertEqual(len({x["id"] for x in rows}), len(rows))
                for item in rows:
                    if item["status"] == "reproducible":
                        self.assertTrue(type(item["value"]) in (int,float))
                        self.assertGreaterEqual(item["n"], 0)
                    else:
                        self.assertIsNone(item["value"])
                indexed = {r["id"]:r for r in rows}
                self.assertIsNone(indexed["historical_suggestive_score"]["value"])
                self.assertIsNone(indexed["norm_letter_deviation"]["value"])

    def test_33_letter_counts_sum_to_total(self):
        for text in ("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                     "Ёж, ёж, ель", "hello", ""):
            with self.subTest(text=text):
                items = {x["id"]:x for x in calculate(text)}
                self.assertEqual(sum(items["letter_"+k+"_count"]["value"]
                                     for k in RU_ALPHABET),
                                 items["russian_letter_count"]["value"])

    def test_comparison_identical_has_zeros(self):
        for text in ("", "123", "Привет", "Всё хорошо, всё хорошо!", "Условие 20%."):
            with self.subTest(text=text):
                report=reports.compare(*doc(text), *doc(text))
                self.assertTrue(report["comparisons"])
                self.assertTrue(all(r["delta"] == 0 for r in report["comparisons"]))
                self.assertEqual(report["historical_compatibility"],"not_verified")

    def test_empty_metric_is_not_fake_zero(self):
        rows = {x["id"]:x for x in calculate("")}
        self.assertEqual(rows["token_count"]["value"], 0)
        self.assertEqual(rows["russian_ttr"]["status"], "unavailable")
        self.assertIsNone(rows["russian_ttr"]["value"])
        self.assertEqual(rows["pos_distribution"]["status"],"unavailable")

    def test_comparison_skips_different_methods_and_datasets(self):
        base=measurement("m1", 1.0, "ratio", 1, "a6.wordforms")
        other=copy.deepcopy(base)
        other["value"]=2.0
        other["method_version"]="incompatible"
        with patch("slovodel_core.reports.calculate",
                   side_effect=[[base],[other]]):
            r=reports.compare(*doc("текст"),*doc("иной"))
        self.assertEqual(r["comparison_status"],"unavailable")
        self.assertEqual(r["comparisons"],[])
        self.assertIn("METRIC_VERSION_MISMATCH:m1",r["warnings"])
        self.assertIn("NO_COMPARABLE_MEASUREMENTS",r["warnings"])
        other["method_version"]=base["method_version"]
        other["dataset_id"]="different-corpus"
        with patch("slovodel_core.reports.calculate",
                   side_effect=[[base],[other]]):
            r=reports.compare(*doc("текст"),*doc("иной"))
        self.assertEqual(r["comparisons"],[])
        self.assertIn("METRIC_VERSION_MISMATCH:m1",r["warnings"])

    def test_comparison_unavailable_not_replaced_with_numbers(self):
        none=unavailable("unavailable_hist", "HISTORICAL_METHOD_NOT_VERIFIED")
        with patch("slovodel_core.reports.calculate",
                   side_effect=[[none],[none]]):
            result=reports.compare(*doc(""), *doc(""))
        self.assertEqual(result["comparison_status"],"unavailable")
        self.assertEqual(result["comparisons"],[])
        self.assertIn("NO_COMPARABLE_MEASUREMENTS",result["warnings"])

    def test_ttr_length_dependent(self):
        r=reports.compare(*doc("мама мама"),*doc("мама мыла раму"))
        self.assertIn("INCOMPARABLE_TTR_DIFFERENT_LENGTHS",r["warnings"])
        self.assertNotIn("russian_ttr",{x["id"] for x in r["comparisons"]})

    def test_nfc_independent_of_bytes(self):
        a=reports.audit(*doc("ё"))
        b=reports.audit(*doc("е\u0308"))
        va={i["id"]:i["value"] for i in a["measurements"]}
        vb={i["id"]:i["value"] for i in b["measurements"]}
        self.assertEqual(va,vb)
        self.assertNotEqual(a["source_sha256"],b["source_sha256"])
        self.assertTrue(b["source"]["normalization_changed"])

    def test_reference_profile_roundtrip_and_opt_in(self):
        p=reference()
        parsed,digest=parse_profile(json.dumps(p,ensure_ascii=False))
        self.assertEqual(parsed,p)
        self.assertTrue(digest.startswith("local-sha256:"))
        self.assertNotIn("local_ref_м_delta_pp",{r["id"] for r in calculate("мама")})
        metrics={r["id"]:r for r in calculate("мама",reference=(parsed,digest))}
        self.assertIn("local_ref_м_delta_pp",metrics)
        self.assertEqual(metrics["norm_letter_deviation"]["status"],"unavailable")

    def test_mismatched_source_not_silent_validated(self):
        p=reference()
        p["method_version"]="future-unreviewed"
        with self.assertRaises(ProfileError):
            parse_profile(json.dumps(p))
        p=reference()
        p["counts"]["м"]=p["counts"]["м"]+1
        with self.assertRaises(ProfileError):
            parse_profile(json.dumps(p))

    def test_zero_baseline_unavailable_not_zero_ratio(self):
        self.assertEqual(compare_rate(0,0,1,10),(None,None))
        self.assertEqual(compare_rate(1,10,0,10),(10.0,None))

    def test_guard_metadata_complete_and_redacted(self):
        left=doc("Цена 50 000 ₽, контакт info@example.test.")
        right=doc("Цена 80 000 ₽, контакт support@example.test.")
        d=guard_report(left,right,())
        self.assertEqual(d["decision"],"blocked")
        self.assertEqual(d["source_sha256"],hashlib.sha256(left[0]).hexdigest())
        self.assertEqual(d["revision_sha256"],hashlib.sha256(right[0]).hexdigest())
        self.assertNotIn("info@example.test",json.dumps(d))
        self.assertFalse(d["publish_ready"])

    def test_workflow_invalid_mode_and_incorrect_arguments(self):
        with self.assertRaisesRegex(ValueError,"WORKFLOW_INVALID_MODE"):
            build("historical_research", input_doc=doc("текст"))
        for mode in ("audit","create"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError,"WORKFLOW_MISSING_OR_EXTRA_INPUT"):
                    build(mode, before_doc=doc("текст"))
                with self.assertRaisesRegex(ValueError,"WORKFLOW_TERMS_RESTRICTED"):
                    build(mode,input_doc=doc("текст"),protected_terms=("факт",))
        for mode in ("rewrite","compare"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError,"WORKFLOW_MISSING_OR_EXTRA_INPUT"):
                    build(mode,input_doc=doc("текст"))

    def test_workflow_requires_manual_review_even_without_diffs(self):
        same=doc("Один текст.")
        report=build("rewrite",before_doc=same,after_doc=same)
        self.assertEqual(report["decision"],"draft_requires_review")
        self.assertFalse(report["publication_ready"])
        self.assertEqual(report["fact_guard"]["decision"],"unchanged")

    def test_workflow_does_not_claim_it_created_draft(self):
        draft=build("create",input_doc=doc("Мама."))
        self.assertEqual(draft["ai_text_generation"],"external_to_this_workflow")
        self.assertEqual(draft["decision"],"draft_requires_review")

    def test_local_utf8_exclusive_output_and_read(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"input.txt"
            out=Path(td)/"report.json"
            data="ё, е\u0308".encode("utf-8")
            path.write_bytes(data)
            self.assertEqual(read_text(str(path)),(data,"ё, е\u0308"))
            emit_json('{"safe":true}',str(out))
            self.assertEqual(json.loads(out.read_text())["safe"],True)
            with self.assertRaises(DataError):
                emit_json('{"safe":false}',str(out))
            self.assertEqual(json.loads(out.read_text())["safe"],True)
            self.assertEqual(path.read_bytes(),data)

    def test_emit_to_stdout_is_not_user_text(self):
        with redirect_stdout(io.StringIO()) as sink:
            emit_json('{"status":"ok"}',None)
        self.assertEqual(sink.getvalue(),'{"status":"ok"}\n')

    def test_profile_metadata_no_raw_input(self):
        raw,txt=doc("Сверхсекретное слово мама")
        p=make_profile(raw,txt,source_label="synthetic",
                       source_url="local://self",genre="test",corpus_version="v1",
                       license_id="CC0-1.0",rights_basis="self authored")
        self.assertNotIn("Сверхсекретное",json.dumps(p,ensure_ascii=False))


if __name__=="__main__":
    unittest.main()
