"""Issue #4 reference fixtures: orthographic, deterministic, no-model metrics."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/slovodel"
sys.path.insert(0, str(SKILL))
from slovodel_core.metrics import calculate, cleaned, russian_token, words  # noqa: E402

ANALYZE = SKILL / "scripts/analyze.py"
COMPARE = SKILL / "scripts/compare.py"


def metric(text: str, identifier: str) -> dict:
    return {m["id"]: m for m in calculate(text)}[identifier]


class MetricReferenceTests(unittest.TestCase):
    def test_unicode_nfc_yo_e_distinct(self):
        a = metric("Ёж е\u0308ж и ель", "letter_ё_count")
        b = metric("Ёж е\u0308ж и ель", "letter_е_count")
        self.assertEqual(a["value"], 2)
        self.assertEqual(b["value"], 1)
        self.assertEqual(a["n"], metric("Ёж е\u0308ж и ель",
                                       "russian_letter_count")["value"])

    def test_words_defis_mixed_and_emoji(self):
        text = "По-русски и по\u2011русски, HELLO тест42 😀 A_Я"
        t = words(cleaned(text))
        self.assertEqual(t, ["по-русски", "и", "по-русски",
                             "hello", "тест", "a", "я"])
        self.assertEqual(metric(text, "russian_token_count")["value"], 5)

    def test_url_email_excluded_from_tokens(self):
        text = "До https://пример.рф/путь и www.дом.рф; test@пример.рф"
        self.assertEqual(metric(text, "token_count")["value"], 2)
        self.assertEqual(metric(text, "russian_token_count")["value"], 2)

    def test_hyphenated_token_is_russian(self):
        self.assertTrue(russian_token("по-русски"))
        self.assertFalse(russian_token("hello-привет"))
        self.assertFalse(russian_token("hello"))

    def test_sentence_boundaries_and_abbreviations(self):
        text = "Мы были в г. Москве. Это т. д. пример! Всё?"
        self.assertEqual(metric(text, "sentence_count")["value"], 3)

    def test_sentence_ignores_decimal_point(self):
        text = "Цена 3.14. Далее пояснение."
        self.assertEqual(metric(text, "sentence_count")["value"], 2)

    def test_syllables_zero_vowel_word_and_latin(self):
        text = "В дом hello"
        self.assertEqual(metric(text, "russian_orthographic_syllable_total")["value"], 1)
        self.assertEqual(metric(text, "russian_zero_vowel_token_count")["value"], 1)
        self.assertEqual(metric(text, "russian_syllables_per_token_mean")["value"], .5)
        self.assertEqual(metric(text, "russian_syllables_per_token_median")["value"], .5)

    def test_ngrams_never_cross_token_boundary(self):
        text = "ма ма"
        self.assertEqual(metric(text, "letter_2gram_repeat_types")["value"], 1)
        self.assertEqual(metric(text, "letter_2gram_excess_occurrences")["value"], 1)
        self.assertEqual(metric(text, "letter_3gram_excess_occurrences")["value"], 0)

    def test_ngrams_repetition(self):
        text = "мама мама"
        self.assertEqual(metric(text, "letter_2gram_repeat_types")["value"], 2)
        self.assertEqual(metric(text, "letter_2gram_excess_occurrences")["value"], 4)
        self.assertEqual(metric(text, "letter_3gram_excess_occurrences")["value"], 2)

    def test_onset_windows_bounded(self):
        text = "мама мыла мяч мир мысль дом"
        self.assertEqual(metric(text, "onset_window_count")["value"], 2)
        self.assertEqual(metric(text, "onset_repetition_window_count")["value"], 2)

    def test_russian_wordform_statistics(self):
        text = "Мама мама МАМА"
        self.assertEqual(metric(text, "russian_token_count")["value"], 3)
        self.assertEqual(metric(text, "russian_wordform_type_count")["value"], 1)
        self.assertEqual(metric(text, "russian_repeated_wordform_excess")["value"], 2)
        self.assertEqual(metric(text, "russian_hapax_type_count")["value"], 0)
        self.assertEqual(metric(text, "russian_max_wordform_frequency")["value"], 3)
        self.assertEqual(metric(text, "russian_ttr")["value"], round(1 / 3, 8))

    def test_golden_position_one_based(self):
        text = "один два три четыре пять"
        self.assertEqual(metric(text, "golden_section_token_index")["value"], 3)
        self.assertIn("NO_PSYCHOLOGICAL_EFFECT_INFERRED",
                      metric(text, "golden_section_token_index")["warnings"])

    def test_empty_and_latin_only_inputs(self):
        for text in ("", "English only"):
            with self.subTest(text=text):
                self.assertEqual(metric(text, "russian_token_count")["value"], 0)
                for identifier in (
                    "russian_ttr", "russian_syllables_per_token_mean",
                    "golden_section_token_index" if not text else "russian_syllables_per_token_median",
                ):
                    self.assertEqual(metric(text, identifier)["status"], "unavailable")
                    self.assertIsNone(metric(text, identifier)["value"])
        self.assertEqual(metric("", "token_count")["value"], 0)

    def test_text_privacy_report_aggregate_only(self):
        secret = "секретныйпароль123 личныйадрес42"
        encoded = secret.encode("utf-8")
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "secret.txt"
            source.write_bytes(encoded)
            result = subprocess.run(
                [sys.executable, str(ANALYZE), "--input", str(source)],
                capture_output=True, text=True, encoding="utf-8", check=False,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("секретныйпароль", result.stdout + result.stderr)
            self.assertNotIn("личныйадрес", result.stdout + result.stderr)
            self.assertEqual(source.read_bytes(), encoded)
            self.assertTrue(all("value" in m
                                for m in json.loads(result.stdout)["measurements"]))

    def test_compare_identical_has_only_zero_deltas(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "text.txt"
            source.write_text("Тест! Тест. Ёлка, ель. 123",
                              encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(COMPARE), "--before", str(source),
                 "--after", str(source)],
                capture_output=True, text=True, encoding="utf-8",
                check=False, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["comparison_status"], "completed")
            self.assertTrue(data["comparisons"])
            self.assertTrue(all(p["delta"] == 0 for p in data["comparisons"]))

    def test_compare_ttr_incompatible_lengths(self):
        with tempfile.TemporaryDirectory() as d:
            before = Path(d) / "before.txt"
            after = Path(d) / "after.txt"
            before.write_text("мама мама", encoding="utf-8")
            after.write_text("мама мыла раму", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(COMPARE), "--before", str(before),
                 "--after", str(after)], capture_output=True, text=True,
                encoding="utf-8", check=False, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertIn("INCOMPARABLE_TTR_DIFFERENT_LENGTHS", data["warnings"])
            self.assertNotIn("russian_ttr", [c["id"] for c in data["comparisons"]])
            self.assertEqual(next(c for c in data["comparisons"]
                                  if c["id"] == "russian_token_count")["delta"], 1)

    def test_known_unavailable_scores_remain_null(self):
        for identifier in ("norm_letter_deviation", "pos_distribution",
                           "historical_suggestive_score"):
            m = metric("Текст", identifier)
            self.assertEqual(m["status"], "unavailable")
            self.assertIsNone(m["value"])

    def test_nfc_equivalent_text_same_measurements(self):
        first = {m["id"]: (m["status"], m["value"]) for m in calculate("е\u0308ж")}
        second = {m["id"]: (m["status"], m["value"]) for m in calculate("ёж")}
        self.assertEqual(first, second)

    def test_full_alphabet_has_33_independent_count_metrics(self):
        sample = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
        measures = {m["id"]: m for m in calculate(sample)}
        keys = [k for k in measures if k.startswith("letter_") and k.endswith("_count")]
        self.assertEqual(len(keys), 33)
        self.assertEqual(measures["russian_letter_count"]["value"], 33)
        self.assertTrue(all(measures[k]["value"] == 1 for k in keys))

    def test_one_letter_text_has_no_five_token_windows(self):
        self.assertEqual(metric("Я", "russian_token_count")["value"], 1)
        self.assertEqual(metric("Я", "russian_syllables_per_token_mean")["value"], 1.0)
        self.assertEqual(metric("Я", "onset_window_count")["value"], 0)
        self.assertEqual(metric("Я", "golden_section_token_index")["value"], 1)

    def test_unicode_cluster_is_explicitly_approximate(self):
        sample = "э\u0301 ☺\ufe0f"
        count = metric(sample, "base_mark_cluster_count")
        self.assertEqual(count["value"], 3)
        self.assertIn("NOT_UAX29_GRAPHEMES", count["warnings"])


if __name__ == "__main__":
    unittest.main()
