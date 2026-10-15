"""End-to-end local workflows: actual Python Core execution, no invented AI calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills/slovodel/scripts/workflow.py"
SCHEMA = ROOT / "schemas/workflow.schema.json"


class WorkflowsE2ETests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def file(self, name, text):
        p = self.home / name
        p.write_text(text, encoding="utf-8")
        return p

    def run_mode(self, mode, *args):
        return subprocess.run(
            [sys.executable, str(RUNNER), "--mode", mode, *[str(x) for x in args]],
            capture_output=True, text=True, encoding="utf-8", timeout=20
        )

    def test_audit_only_one_analysis(self):
        original = self.file("original.txt", "Мама мыла раму.")
        result = self.run_mode("audit", "--input", original)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["decision"], "audit_only")
        self.assertEqual(data["steps_executed"], ["analyze_input"])
        self.assertIsNone(data["post_analysis"])
        self.assertIsNone(data["fact_guard"])
        self.assertIsNone(data["comparison"])
        self.assertEqual(data["pre_analysis"]["source_sha256"],
                         hashlib.sha256(original.read_bytes()).hexdigest())
        rows = {r["id"]: r for r in data["pre_analysis"]["measurements"]}
        self.assertEqual(rows["russian_token_count"]["value"], 3)
        self.assertEqual(rows["historical_suggestive_score"]["status"], "unavailable")
        self.assertFalse(data["publication_ready"])

    def test_create_analyses_external_draft_only(self):
        draft = self.file("draft.txt", "Сервис помогает составить список покупок.")
        result = self.run_mode("create", "--input", draft)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["decision"], "draft_requires_review")
        self.assertEqual(data["steps_executed"], ["analyze_agent_draft"])
        self.assertIsNone(data["pre_analysis"])
        self.assertIsNone(data["fact_guard"])
        self.assertEqual(data["post_analysis"]["source"]["size_bytes"],
                         len(draft.read_bytes()))
        self.assertIn("BRIEF_FACTS_NOT_AUTOMATICALLY_VERIFIED", data["warnings"])
        self.assertEqual(data["ai_text_generation"], "external_to_this_workflow")

    def test_create_placeholder_disclosed_without_copying(self):
        draft = self.file("draft.txt", "Цена [уточнить] ₽. Ссылка [URL].")
        result = self.run_mode("create", "--input", draft)
        self.assertEqual(result.returncode, 0)
        self.assertIn("UNRESOLVED_PLACEHOLDER_DETECTED",
                      json.loads(result.stdout)["warnings"])
        self.assertNotIn("[уточнить]", result.stdout)

    def test_rewrite_blocked_on_changed_salary(self):
        before = self.file("before.txt", "Оплата 50 000 ₽, 20 часов в неделю.")
        after = self.file("after.txt", "Оплата 80 000 ₽, 20 часов в неделю.")
        p = self.run_mode("rewrite", "--before", before, "--after", after)
        self.assertEqual(p.returncode, 5, p.stderr)
        report = json.loads(p.stdout)
        self.assertEqual(report["decision"], "blocked")
        self.assertEqual([x for x in report["fact_guard"]["findings"]
                          if x["kind"] == "money"][0]["removed_count"], 1)
        self.assertEqual(report["fact_guard"]["decision"], "blocked")
        self.assertFalse(report["publication_ready"])
        self.assertEqual(report["steps_executed"],
                         ["analyze_original", "check_agent_edit_facts",
                          "analyze_agent_revision",
                          "compare_reproducible_metrics"])
        self.assertIsNotNone(report["pre_analysis"])
        self.assertIsNotNone(report["post_analysis"])
        self.assertIsNotNone(report["comparison"])
        self.assertEqual(report["pre_analysis"]["source_sha256"],
                         hashlib.sha256(before.read_bytes()).hexdigest())
        self.assertNotIn("50 000", p.stdout)
        self.assertNotIn("80 000", p.stdout)

    def test_rewrite_without_detected_change_still_needs_review(self):
        a = self.file("before.txt", "Текст удобный.")
        b = self.file("after.txt", "Текст понятный.")
        p = self.run_mode("rewrite", "--before", a, "--after", b)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual(data["decision"], "draft_requires_review")
        self.assertEqual(data["fact_guard"]["decision"], "review_required")
        self.assertFalse(data["publication_ready"])

    def test_rewrite_custom_protected_phrase_blocks(self):
        a = self.file("before.txt", "Нужно письменное согласие редактора.")
        b = self.file("after.txt", "Нужно согласие редактора.")
        protected = self.file("terms.txt", "письменное согласие редактора\n")
        p = self.run_mode("rewrite", "--before", a, "--after", b,
                          "--protected-file", protected)
        self.assertEqual(p.returncode, 5)
        self.assertEqual(json.loads(p.stdout)["fact_guard"]["decision"], "blocked")

    def test_compare_actual_deltas_and_fact_risk(self):
        a = self.file("before.txt", "Срок 5 дней.")
        b = self.file("after.txt", "Срок 7 дней.")
        p = self.run_mode("compare", "--before", a, "--after", b)
        self.assertEqual(p.returncode, 0, p.stderr)
        obj = json.loads(p.stdout)
        self.assertEqual(obj["decision"], "comparison_only")
        self.assertEqual(obj["fact_guard"]["decision"], "blocked")
        self.assertIn("PROTECTED_FACTS_DIFFER", obj["warnings"])
        self.assertTrue(obj["comparison"]["comparisons"])
        self.assertFalse(obj["publication_ready"])
        self.assertIn("compare_reproducible_metrics", obj["steps_executed"])

    def test_compare_same_text_zero_deltas(self):
        a = self.file("before.txt", "Один текст.")
        p = self.run_mode("compare", "--before", a, "--after", a)
        self.assertEqual(p.returncode, 0, p.stderr)
        obj = json.loads(p.stdout)
        self.assertEqual(obj["fact_guard"]["decision"], "unchanged")
        self.assertTrue(all(row["delta"] == 0
                            for row in obj["comparison"]["comparisons"]))

    def test_no_fake_python_run_if_invalid_mode(self):
        p = self.run_mode("historical_research", "--input", "unused.txt")
        self.assertEqual(p.returncode, 2)
        self.assertIn("invalid choice", p.stderr)

    def test_no_third_party_package_default(self):
        a = self.file("sample.txt", "Мама мыла раму.")
        p = self.run_mode("audit", "--input", a)
        self.assertEqual(p.returncode, 0)
        ms = {x["id"]: x for x in json.loads(p.stdout)["pre_analysis"]["measurements"]}
        self.assertIsNone(ms["pos_distribution"]["value"])
        self.assertIsNone(ms["norm_letter_deviation"]["value"])

    def test_protected_terms_invalid_for_create_and_audit(self):
        a = self.file("sample.txt", "Текст.")
        terms = self.file("terms.txt", "термин")
        for mode in ("audit", "create"):
            p = self.run_mode(mode, "--input", a, "--protected-file", terms)
            self.assertEqual(p.returncode, 2, p.stderr)

    def test_missing_input_is_cli_error(self):
        self.assertEqual(self.run_mode("audit").returncode, 2)
        self.assertEqual(self.run_mode("rewrite", "--before", "notfound").returncode, 2)

    def test_existing_output_is_not_overwritten(self):
        a = self.file("sample.txt", "Текст.")
        out = self.file("output.json", "KEEP")
        p = self.run_mode("audit", "--input", a, "--output", out)
        self.assertEqual(p.returncode, 4)
        self.assertEqual(out.read_text(), "KEEP")

    def test_private_values_not_in_stdout(self):
        secret = "https://example.org/?private=9711137"
        a = self.file("before.txt", f"Ссылка {secret}")
        b = self.file("after.txt", "Ссылка изменилась")
        p = self.run_mode("rewrite", "--before", a, "--after", b)
        self.assertEqual(p.returncode, 5)
        self.assertNotIn(secret, p.stdout + p.stderr)

    def test_full_schema_for_each_mode(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        Draft202012Validator.check_schema(schema)
        v = Draft202012Validator(schema)
        a = self.file("a.txt", "Оплата 10 ₽.")
        b = self.file("b.txt", "Оплата 20 ₽.")
        for mode in ("audit", "create", "rewrite", "compare"):
            args = (["--input", a] if mode in ("audit", "create") else
                    ["--before", a, "--after", b])
            result = self.run_mode(mode, *args)
            self.assertIn(result.returncode, (0, 5))
            with self.subTest(mode=mode):
                bundle = json.loads(result.stdout)
                v.validate(bundle)
                for report_name, schema_name in (
                    ("pre_analysis", "analysis.schema.json"),
                    ("post_analysis", "analysis.schema.json"),
                    ("comparison", "compare.schema.json"),
                    ("fact_guard", "fact-guard.schema.json"),
                ):
                    nested = bundle[report_name]
                    if nested is None:
                        continue
                    nested_schema = json.loads(
                        (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
                    )
                    Draft202012Validator.check_schema(nested_schema)
                    Draft202012Validator(nested_schema).validate(nested)

    def test_file_is_unchanged_all_modes(self):
        a = self.file("a.txt", "Нельзя менять условия.")
        b = self.file("b.txt", "Можно менять условия.")
        ba, bb = a.read_bytes(), b.read_bytes()
        for mode in ("audit", "create", "rewrite", "compare"):
            args = (["--input", a] if mode in ("audit", "create") else
                    ["--before", a, "--after", b])
            self.assertIn(self.run_mode(mode, *args).returncode, (0, 5))
        self.assertEqual(a.read_bytes(), ba)
        self.assertEqual(b.read_bytes(), bb)


if __name__ == "__main__":
    unittest.main()
