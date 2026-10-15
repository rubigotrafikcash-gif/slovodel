"""Issue #6: optional POS analysis, dictionary provenance, ambiguity and fallback."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/slovodel"
sys.path.insert(0, str(SKILL))

from slovodel_core.morphology import (  # noqa: E402
    ANALYZER_VERSION, DICTIONARY_VERSION, TAGS, calculate_pos, load_backend,
    token_pos,
)
from slovodel_core.metrics import calculate  # noqa: E402

AUDIT = SKILL / "scripts/analyze.py"
COMPARE = SKILL / "scripts/compare.py"


def parse(pos, known=True):
    return SimpleNamespace(tag=SimpleNamespace(POS=pos), is_known=known)


class FakeMorph:
    def __init__(self, parsed=None):
        self.parsed = parsed or {}
        self.words = []

    def parse(self, word):
        self.words.append(word)
        return self.parsed.get(word, [parse("NOUN")])


def dataset():
    return ("pymorphy3:" + ANALYZER_VERSION +
            "|pymorphy3-dicts-ru:" + DICTIONARY_VERSION)


def measures(text, fake):
    return {m["id"]: m for m in calculate_pos(text, (fake, dataset()))}


class MorphologyTests(unittest.TestCase):
    def test_default_without_flag_is_unavailable(self):
        result = {m["id"]: m for m in calculate("Мама дома")}
        self.assertEqual(result["pos_distribution"]["status"], "unavailable")
        self.assertIsNone(result["pos_distribution"]["value"])
        self.assertNotIn("pos_noun_count", result)

    def test_unique_pos_with_multiple_cases_is_resolved(self):
        f=FakeMorph({"мама": [parse("NOUN"), parse("NOUN")]})
        result=measures("мама",f)
        self.assertEqual(result["pos_noun_count"]["value"],1)
        self.assertEqual(result["pos_ambiguous_token_count"]["value"],0)
        self.assertEqual(result["pos_coverage_ratio"]["value"],1.0)

    def test_ambiguity_different_pos_is_excluded_from_counts(self):
        f=FakeMorph({"стали":[parse("VERB"),parse("NOUN")]})
        result=measures("стали",f)
        self.assertEqual(result["pos_ambiguous_token_count"]["value"],1)
        self.assertEqual(result["pos_noun_count"]["value"],0)
        self.assertEqual(result["pos_verb_count"]["value"],0)
        self.assertEqual(result["pos_coverage_ratio"]["value"],0.0)
        self.assertIn("NO_CONTEXT_DISAMBIGUATION",
                      result["pos_ambiguous_token_count"]["warnings"])

    def test_oov_prediction_is_not_assumed_known(self):
        f=FakeMorph({"абракадабра":[parse("NOUN",known=False)]})
        result=measures("абракадабра",f)
        self.assertEqual(result["pos_oov_token_count"]["value"],1)
        self.assertEqual(result["pos_resolved_token_count"]["value"],0)

    def test_unclassified_if_unknown_tag(self):
        f=FakeMorph({"слово":[parse("FUTURE")]})
        result=measures("слово",f)
        self.assertEqual(result["pos_unclassified_token_count"]["value"],1)

    def test_no_parses_is_unclassified(self):
        f=FakeMorph({"слово":[]})
        # FakeMorph explicitly maps to [] (does not use fallback).
        result=measures("слово",f)
        self.assertEqual(result["pos_unclassified_token_count"]["value"],1)

    def test_no_english_or_url_or_email(self):
        f=FakeMorph()
        result=measures("мама hello https://пример.рф test@пример.рф",f)
        self.assertEqual(result["pos_noun_count"]["value"],1)
        self.assertEqual(f.words,["мама"])

    def test_total_accounting_and_shares(self):
        f=FakeMorph({
            "мама":[parse("NOUN")],
            "стали":[parse("NOUN"),parse("VERB")],
            "невидаль":[parse("NOUN",known=False)],
            "глагол":[parse("VERB")]
        })
        result=measures("мама стали невидаль глагол",f)
        self.assertEqual(result["pos_noun_count"]["value"],1)
        self.assertEqual(result["pos_verb_count"]["value"],1)
        self.assertEqual(result["pos_noun_share"]["value"],.25)
        self.assertEqual(result["pos_verb_share"]["value"],.25)
        self.assertEqual(result["pos_resolved_token_count"]["value"],2)
        self.assertEqual(result["pos_ambiguous_token_count"]["value"],1)
        self.assertEqual(result["pos_oov_token_count"]["value"],1)
        self.assertEqual(result["pos_coverage_ratio"]["value"],.5)
        self.assertEqual(sum(result["pos_"+p.lower()+"_count"]["value"]
                             for p in TAGS) + result["pos_ambiguous_token_count"]["value"]+
                         result["pos_oov_token_count"]["value"]+
                         result["pos_unclassified_token_count"]["value"],4)

    def test_empty_morphology_explicit_null_ratios(self):
        result=measures("",FakeMorph())
        self.assertEqual(result["pos_noun_count"]["value"],0)
        self.assertEqual(result["pos_noun_share"]["status"],"unavailable")
        self.assertIsNone(result["pos_noun_share"]["value"])
        self.assertEqual(result["pos_coverage_ratio"]["status"],"unavailable")
        self.assertIsNone(result["pos_coverage_ratio"]["value"])

    def test_methods_and_dataset_provenance(self):
        result=measures("мама",FakeMorph())
        item=result["pos_noun_count"]
        self.assertEqual(item["dataset_id"],dataset())
        self.assertEqual(item["method_id"],"slovodel.a5.pymorphy3.unique_pos")
        self.assertEqual(item["status"],"reproducible")
        self.assertTrue(item["method_version"])
        self.assertIn("POS_DICTIONARY_CC_BY_SA",item["warnings"])

    def test_only_aggregates_not_wordforms(self):
        private="секретноподобноеслово"
        f=FakeMorph({private:[parse("NOUN")]})
        result=measures(private,f)
        self.assertNotIn(private,json.dumps(result,ensure_ascii=False))

    def test_pinned_missing_dependency_gracefully_falls_back(self):
        from importlib.metadata import PackageNotFoundError
        with patch("slovodel_core.morphology.version",
                   side_effect=PackageNotFoundError):
            backend,reason=load_backend()
        self.assertIsNone(backend)
        self.assertEqual(reason,"MORPHOLOGY_DEPENDENCY_NOT_INSTALLED")

    def test_wrong_dictionary_version_refused(self):
        with patch("slovodel_core.morphology.version",
                   side_effect=lambda pkg: "2.0.6" if pkg=="pymorphy3" else "old"):
            backend,reason=load_backend()
        self.assertIsNone(backend)
        self.assertEqual(reason,"MORPHOLOGY_VERSION_UNSUPPORTED")

    def test_backend_initialization_failed_sanitized(self):
        with patch("slovodel_core.morphology.version",
                   side_effect=lambda pkg: ANALYZER_VERSION if pkg=="pymorphy3"
                   else DICTIONARY_VERSION):
            with patch("slovodel_core.morphology.import_module",
                       side_effect=ImportError("PRIVATE PATH /tmp/secret")):
                backend,reason=load_backend()
        self.assertIsNone(backend)
        self.assertEqual(reason,"MORPHOLOGY_BACKEND_UNAVAILABLE")
        self.assertNotIn("PRIVATE",reason)

    def test_cli_unflagged_no_pymorphy_integration(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"a.txt"
            src.write_text("Мама мыла раму",encoding="utf-8")
            result=subprocess.run([sys.executable,str(AUDIT),"--input",str(src)],
                                  capture_output=True,text=True,encoding="utf-8",
                                  timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            obj=json.loads(result.stdout)
            data={row["id"]:row for row in obj["measurements"]}
            self.assertEqual(data["pos_distribution"]["status"],"unavailable")
            self.assertNotIn("pos_noun_count",data)

    def test_cli_opt_in_graceful_if_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"a.txt"
            src.write_text("Мама мыла раму",encoding="utf-8")
            args=[sys.executable,str(AUDIT),"--input",str(src),"--morphology"]
            result=subprocess.run(args,capture_output=True,text=True,
                                  encoding="utf-8",timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            data={row["id"]:row for row in json.loads(result.stdout)["measurements"]}
            if "pos_distribution" in data:
                self.assertEqual(data["pos_distribution"]["status"],"unavailable")
                self.assertIn("MORPHOLOGY_",data["pos_distribution"]["warnings"][0])
            else:
                self.assertIn("pos_noun_count",data)
                self.assertEqual(data["pos_noun_count"]["status"],"reproducible")

    def test_full_cli_optional_integration_when_installed(self):
        backend,reason=load_backend()
        if backend is None:
            self.skipTest("Pinned optional pymorphy3 + dictionary not installed: "+str(reason))
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"text.txt"
            source.write_text("Мама мыла раму",encoding="utf-8")
            cmd=[sys.executable,str(AUDIT),"--input",str(source),"--morphology"]
            result=subprocess.run(cmd,capture_output=True,text=True,
                                  encoding="utf-8",timeout=25)
            self.assertEqual(result.returncode,0,result.stderr)
            data={r["id"]:r for r in json.loads(result.stdout)["measurements"]}
            self.assertIn("pos_noun_count",data)
            self.assertEqual(data["pos_noun_count"]["dataset_id"],dataset())
            self.assertGreaterEqual(data["pos_resolved_token_count"]["value"],1)
            cm=subprocess.run([sys.executable,str(COMPARE),"--before",str(source),
                               "--after",str(source),"--morphology"],
                              capture_output=True,text=True,encoding="utf-8",
                              timeout=25)
            self.assertEqual(cm.returncode,0,cm.stderr)
            comparisons=json.loads(cm.stdout)["comparisons"]
            self.assertIn("pos_noun_count",[r["id"] for r in comparisons])
            self.assertTrue(all(r["delta"]==0 for r in comparisons))

    def test_cli_morphology_report_preserves_input_and_no_source_text(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"private.txt"
            text="персональныйвымышленныйтекст" * 2
            source.write_text(text,encoding="utf-8")
            before=source.read_bytes()
            result=subprocess.run([sys.executable,str(AUDIT),"--input",str(source),
                                   "--morphology"],capture_output=True,text=True,
                                  encoding="utf-8",timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(source.read_bytes(),before)
            self.assertNotIn(text,result.stdout+result.stderr)

    def test_pos_ratios_unavailable_when_no_tokens_and_comparable_counts(self):
        f=FakeMorph()
        counts=measures("",f)
        self.assertEqual(counts["pos_resolved_token_count"]["value"],0)
        self.assertTrue(all(counts["pos_"+tag.lower()+"_count"]["value"]==0
                            for tag in TAGS))
        self.assertEqual(counts["pos_coverage_ratio"]["warnings"],
                         ["NO_RUSSIAN_TOKENS"])


if __name__=="__main__":
    unittest.main()
