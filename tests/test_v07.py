"""v0.7 regression on source words and conservative copywriting diagnostics."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"skills"/"slovodel"))
from slovodel_core import __version__
from slovodel_core.metrics import calculate
from slovodel_core.reports import audit

def m(text, key):
    return {v["id"]:v for v in calculate(text)}[key]

class CopywriterV07(unittest.TestCase):
    def test_version(self):
        # v0.7 features remain; the package version is kept in sync across files.
        import re
        pyproject=(ROOT/"pyproject.toml").read_text(encoding="utf-8")
        skill=(ROOT/"skills"/"slovodel"/"SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f'version = "{__version__}"', pyproject)
        self.assertRegex(skill, r'version: "' + re.escape(__version__) + '"')
        self.assertGreaterEqual(tuple(map(int,__version__.split("."))),(0,7,0))

    def test_a4_alternative_denominator(self):
        self.assertEqual(m("В доме","russian_syllables_per_token_mean")["value"],1.0)
        self.assertEqual(m("В доме","a4_vowels_per_nonzero_word_mean")["value"],2.0)
        self.assertEqual(m("В доме","a4_words_with_vowels_count")["value"],1)

    def test_three_vowels_and_empty(self):
        self.assertEqual(m("достопримечательность дом","a4_words_3plus_vowels_count")["value"],1)
        self.assertIsNone(m("","a4_vowels_per_nonzero_word_mean")["value"])
        self.assertIsNone(m("в к","a4_vowels_per_nonzero_word_mean")["value"])

    def test_a7_position_in_sentence(self):
        s="Первое. Второе третье! Четвёртое пятое шестое."
        self.assertEqual(m(s,"golden_section_token_index")["value"],4)
        self.assertEqual(m(s,"a7_golden_section_sentence_ordinal")["value"],3)
        self.assertEqual(m(s,"a7_golden_section_sentence_length_tokens")["value"],3)

    def test_sentence_warning(self):
        t=" ".join(["слово"]*26)+"."
        self.assertEqual(m(t,"a7_sentences_over_25_tokens")["value"],1)
        self.assertIn("EDITORIAL_THRESHOLD_NOT_QUALITY_SCORE",m(t,"a7_sentences_over_25_tokens")["warnings"])

    def test_sound_is_only_review_candidate(self):
        self.assertEqual(m("любовь дуб город","a9_final_voiced_letter_review_candidates")["value"],3)
        self.assertEqual(m("лик храп","a9_final_voiced_letter_review_candidates")["value"],0)
        self.assertIn("NOT_A_PHONETIC_TRANSCRIPTION",m("любовь","a9_final_voiced_letter_review_candidates")["warnings"])

    def test_historical_values_unavailable(self):
        manifest=json.loads((ROOT/"evals/primary-v07.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["word_cases"]),10)
        self.assertEqual(len(manifest["text_cases"]),6)
        for record in manifest["word_cases"]:
            with self.subTest(word=record["input"],scale=record["scale"]):
                sample=record["input"]
                result=audit(sample.encode("utf-8"),sample)
                vals={x["id"]:x for x in result["measurements"]}
                self.assertEqual(vals["russian_token_count"]["value"],1)
                self.assertIsNone(vals["historical_suggestive_score"]["value"])
        self.assertTrue(all(x["v07_full_text_reexecution"].startswith("NOT_RUN_") for x in manifest["text_cases"]))

    def test_actual_word_benchmark(self):
        with tempfile.TemporaryDirectory() as td:
            destination=Path(td)/"result.json"
            run=subprocess.run([sys.executable,str(ROOT/"scripts/benchmark_v07.py"),"--output",str(destination)],
                               capture_output=True,text=True,encoding="utf-8",timeout=30,cwd=td)
            self.assertEqual(run.returncode,0,run.stderr[:250])
            data=json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(data["z_word_scale_cases_executed"],10)
            self.assertEqual(data["ch_short_excerpts_executed_v07"],2)
            self.assertEqual(data["zh_before_after_pair_executions"],2)
            self.assertTrue(all(x["core_token_count_delta"] == 0 and x["core_vowels_per_word_delta"] == 0 and x["historical_phonosemantic_delta"] is None for x in data["zh_before_after_results"]))
            self.assertTrue(all(x["historical_full_text_score_comparability"] == "NOT_COMPARABLE_EXCERPT_ONLY" for x in data["ch_short_excerpt_runs"]))
            self.assertEqual(data["ch_full_texts_executed_v07"],0)
            self.assertIsNone(data["historical_algorithm_similarity_percent"])

    def test_correct_user_language(self):
        skill=(ROOT/"skills/slovodel/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("для создания и улучшения текстов на русском языке",skill)
        self.assertNotIn("AI-копирайтер для русского языка",skill)

if __name__=="__main__":
    unittest.main()
