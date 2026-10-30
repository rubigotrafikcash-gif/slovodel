"""v0.8.0 (Issue #24): regressions found by the independent v0.7 audit.

Synthetic, self-written sentences only; names, prices and brands are fictitious
examples, not user texts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "slovodel"
sys.path.insert(0, str(SKILL))

from slovodel_core.fact_guard import CATEGORIES, SEVERITY, check  # noqa: E402
from slovodel_core.metrics import calculate  # noqa: E402
from slovodel_core.reports import audit  # noqa: E402
from slovodel_core.workflow import build  # noqa: E402
from slovodel_core.zhuravlev import (  # noqa: E402
    PUBLISHED_VECTORS, FormulaError, distribution_mean, evaluate_vector, run,
    simple_mean, weighted_score,
)


def value(text: str, key: str):
    return {m["id"]: m for m in calculate(text)}[key]["value"]


# (name, before, after, category that must be reported)
REAL_CHANGES = [
    ("number in words", "Доставка за три дня.", "Доставка за пять дней.", "number_word"),
    ("amount in words", "Стоимость — пять тысяч рублей.", "Стоимость — семь тысяч рублей.", "money"),
    ("swapped prices", "Сайт 100 000 ₽, лендинг 30 000 ₽.", "Сайт 30 000 ₽, лендинг 100 000 ₽.", "binding"),
    ("swapped terms", "Лендинг за 3 дня, сайт за 10 дней.", "Лендинг за 10 дней, сайт за 3 дня.", "binding"),
    ("fused negation", "Возврат возможен в течение 14 дней.", "Возврат невозможен в течение 14 дней.", "polarity"),
    ("fused negation 2", "Услуга доступна жителям Ижевска.", "Услуга недоступна жителям Ижевска.", "polarity"),
    ("antonym can/cannot", "Отменить заказ можно.", "Отменить заказ нельзя.", "polarity"),
    ("free/paid", "Консультация бесплатная.", "Консультация платная.", "polarity"),
    ("separate negation", "Предоплата не требуется.", "Предоплата требуется.", "polarity"),
    ("guarantee added", "Помогаем увеличить продажи.", "Гарантируем рост продаж.", "guarantee"),
    ("surname", "Ведёт курс Петрова.", "Ведёт курс Иванова.", "proper_name"),
    ("latin brand", "Продаём на Wildberries.", "Продаём на Ozon.", "proper_name"),
    ("city", "Работаем в Ижевске.", "Работаем в Казани.", "proper_name"),
    ("phone", "Звоните +7 (912) 123-45-67.", "Звоните +7 (912) 123-45-76.", "number"),
    ("time", "Работаем с 10:00 до 19:00.", "Работаем с 9:00 до 19:00.", "number"),
    ("weekday", "Приём заявок в пятницу.", "Приём заявок в субботу.", "calendar"),
    ("month", "Старт курса в октябре.", "Старт курса в ноябре.", "calendar"),
    ("ordinal in words", "Первое занятие бесплатно.", "Второе занятие бесплатно.", "number_word"),
    ("promo code", "Промокод OSEN10 даёт скидку.", "Промокод OSEN20 даёт скидку.", "code"),
    ("url", "Подробнее: https://example.org/a", "Подробнее: https://example.org/b", "url"),
    ("may to must", "Клиент может отменить заказ.", "Клиент должен отменить заказ.", "modality"),
]
REVIEW_CHANGES = [
    ("most to all", "Большинство клиентов возвращается.", "Все клиенты возвращаются.", "quantifier"),
    ("obligation weakened", "Запись обязательна.", "Приходите по записи.", "condition"),
    ("restriction added", "Принимаем заявки.", "Принимаем заявки только после проверки.", "condition"),
]
PARAPHRASES = [
    ("Скидка, если оплатите сразу.", "Скидка при оплате сразу."),
    ("Мы работаем в Ижевске с 2015 года.", "С 2015 года работаем в Ижевске."),
    ("Цена 30000 рублей.", "Цена — 30 000 ₽."),
    ("Не забудьте взять паспорт.", "Возьмите паспорт."),
    ("Записывайтесь к Анне.", "Анна ждёт вас. Записывайтесь."),
    ("Только по записи.", "Лишь по записи."),
    ("Друзья, мы запускаем новую услугу! Теперь мы делаем не только сайты, но и рекламу "
     "в Яндекс Директ. Если у вас уже есть сайт, мы можем подключить рекламу за 3 дня. "
     "Стоимость настройки — 15 000 ₽. Пишите в личку, обсудим.",
     "Новая услуга: реклама в Яндекс Директ. Уже есть сайт? Подключим рекламу за 3 дня. "
     "Настройка — 15 000 ₽. Напишите в личные сообщения — обсудим вашу задачу."),
    ("Курс длится 6 недель. Занятия проходят по вторникам и четвергам в 19:00. Стоимость "
     "24 900 рублей, можно оплатить в рассрочку на 3 месяца.",
     "6 недель, занятия по вторникам и четвергам в 19:00. Стоимость — 24 900 ₽, можно "
     "оплатить в рассрочку на 3 месяца."),
    ("Елена Балтина — личный стилист. Помогает собрать гардероб под ваш образ жизни.",
     "Личный стилист Елена Балтина поможет собрать гардероб под ваш образ жизни."),
    ("Доставка по городу бесплатная при заказе от 3000 ₽.",
     "При заказе от 3000 ₽ доставим по городу бесплатно."),
    ("Пишите нам в Telegram: @tairpromo. Отвечаем в течение часа.",
     "Отвечаем в течение часа — пишите в Telegram: @tairpromo."),
    ("Сайт за 7 дней, лендинг за 3 дня.", "За 7 дней — сайт, за 3 дня — лендинг."),
    ("Возврат возможен в течение 14 дней с момента покупки.",
     "В течение 14 дней с момента покупки возврат возможен."),
    ("Мы не берём предоплату и не навязываем допуслуги.",
     "Не берём предоплату и не навязываем дополнительные услуги."),
    ("Первая консультация бесплатно. Дальше — по прайсу.",
     "Первая консультация — бесплатно, следующие — по прайсу."),
    ("Каждый участник получит сертификат.", "Сертификат получит каждый участник."),
    ("Заказать можно на Wildberries и Ozon.",
     "Товар есть на Wildberries и Ozon — заказывайте, где удобнее."),
    ("Цена от 30 000 до 50 000 ₽ в зависимости от объёма.",
     "В зависимости от объёма — от 30 000 до 50 000 ₽."),
]


class FactGuardRules2(unittest.TestCase):
    def test_every_category_has_a_severity(self):
        self.assertEqual(set(CATEGORIES), set(SEVERITY))
        self.assertEqual({SEVERITY[k] for k in ("condition", "quantifier")}, {"review"})

    def test_real_changes_are_blocked_with_their_category(self):
        for name, before, after, kind in REAL_CHANGES:
            with self.subTest(case=name):
                result = check(before, after)
                self.assertEqual(result["decision"], "blocked")
                self.assertIn(kind, {f["kind"] for f in result["findings"]})
                self.assertFalse(result["publish_ready"])

    def test_scope_changes_are_flagged_for_review(self):
        for name, before, after, kind in REVIEW_CHANGES:
            with self.subTest(case=name):
                result = check(before, after)
                self.assertEqual(result["decision"], "review_required")
                finding = next(f for f in result["findings"] if f["kind"] == kind)
                self.assertEqual(finding["severity"], "review")
                self.assertIn("CONDITION_OR_SCOPE_WORDING_CHANGED_REVIEW",
                              result["warnings"])

    def test_paraphrases_are_not_blocked(self):
        for before, after in PARAPHRASES:
            with self.subTest(before=before[:40]):
                self.assertNotEqual(check(before, after)["decision"], "blocked")

    def test_interface_labels_and_lines_are_not_names(self):
        # Found by the independent agent run (scenario 8): UI copy was blocked.
        for before, after in (
            ("Заголовок\nВойдите в аккаунт", "Войдите в аккаунт\nВойти"),
            ("Текст: Вы не вошли. Кнопка: Войти",
             "Текст: Войдите в аккаунт. Кнопка: Продолжить"),
        ):
            with self.subTest(after=after):
                self.assertNotEqual(check(before, after)["decision"], "blocked")

    def test_values_and_names_never_leak(self):
        result = check("Сайт 100 000 ₽, ведёт Петрова, код OSEN10.",
                       "Сайт 30 000 ₽, ведёт Иванова, код OSEN20.")
        dump = json.dumps(result, ensure_ascii=False)
        for secret in ("100 000", "30 000", "Петров", "Иванов", "OSEN", "сайт"):
            self.assertNotIn(secret, dump)

    def test_workflow_marks_review_items(self):
        doc = lambda t: (t.encode("utf-8"), t)  # noqa: E731
        report = build("rewrite", before_doc=doc("Скидка, если оплатите сразу."),
                       after_doc=doc("Скидка при оплате сразу."))
        self.assertEqual(report["decision"], "draft_requires_review")
        self.assertIn("FACT_GUARD_REVIEW_ITEMS", report["warnings"])

    def test_one_mebibyte_is_linear_time(self):
        text = ("Цена 30 000 ₽ за 7 дней в Ижевске, если оплатите. " * 25000)[:1_000_000]
        started = time.perf_counter()
        check(text, text + " ")
        # Old quadratic rules took 29–152 s here; generous bound for slow CI.
        self.assertLess(time.perf_counter() - started, 60)

    def test_number_dense_mebibyte_meets_five_second_target(self):
        # Worst input found in v0.8 verification: almost every token is a
        # number. Measured 6.3 s before the number-word lookup, ~3 s after.
        # CI bound is 2x the 5 s target so slow shared runners do not flake;
        # the local measurement is recorded in docs/ISSUE_24_VERIFICATION.md.
        unit = "".join(f"{n} {w} " for n, w in zip(
            range(1000, 1008), ("дней", "₽", "%", "часов") * 2)) + "три. "
        text = (unit * (1_048_000 // len(unit.encode("utf-8"))))[:1_000_000]
        started = time.perf_counter()
        result = check(text, text + " Гарантия.")
        self.assertLess(time.perf_counter() - started, 10)
        self.assertEqual(result["decision"], "blocked")

    def test_number_word_lookup_matches_regex(self):
        from slovodel_core import fact_guard as fg
        forms = list(fg.NUMBER_WORDS)
        extra = ["три3", "3три", "три_", "_три", "три-пять", "ТРИ", "Три", "ТРЁХ",
                 "стоп", "сороко", "пол", "(три)", "«пять»", "три\u00ad"]
        for word in forms + extra:
            for variant in (word, word.upper(), word.capitalize()):
                text = f"цена {variant}, всего {variant}."
                pieces, found, last = [], [], 0
                for m in fg.NUMBER_WORD.finditer(text):
                    found.append((m.start(), fg.NUMBER_WORDS[m.group().casefold()]))
                    pieces += [text[last:m.start()], " " * (m.end() - m.start())]
                    last = m.end()
                pieces.append(text[last:])
                self.assertEqual(fg._extract_number_words(text),
                                 ("".join(pieces), found), variant)


class Metrics080(unittest.TestCase):
    def test_line_breaks_split_list_posts(self):
        post = ("Что вы получите\nГотовый сайт под ключ\nТексты от копирайтера\n"
                "Подключение заявок в Telegram\nПоддержку 30 дней")
        self.assertEqual(value(post, "sentence_count"), 5)
        self.assertEqual(value(post, "a7_max_sentence_length_tokens"), 4)

    def test_wrapped_prose_stays_one_sentence(self):
        self.assertEqual(value("Мы делаем сайты\nи рекламу для бизнеса.", "sentence_count"), 1)

    def test_abbreviation_can_end_sentence(self):
        self.assertEqual(value("Пишем посты, статьи и др. Звоните нам.", "sentence_count"), 2)
        self.assertEqual(value("Посты, статьи и т. д. Пишите.", "sentence_count"), 2)
        self.assertEqual(value("См. рис. Три.", "sentence_count"), 1)
        self.assertEqual(value("Живём на ул. Ленина.", "sentence_count"), 1)

    def test_a9_skips_prepositions(self):
        self.assertEqual(value("В доме из бумаги под окном без двери.",
                               "a9_final_voiced_letter_review_candidates"), 0)
        self.assertEqual(value("Дуб. Сад. Глаз.", "a9_final_voiced_letter_review_candidates"), 3)

    def test_invisible_characters_do_not_split_words(self):
        for joiner in ("­", "​", "⁠"):
            with self.subTest(joiner=hex(ord(joiner))):
                text = "про" + joiner + "движение сайтов"
                self.assertEqual(value(text, "russian_token_count"), 2)
                self.assertEqual(value(text, "invisible_format_char_count"), 1)

    def test_homoglyphs_are_read_as_russian_and_reported(self):
        text = "Мы делаем сaйты и рекламу. Пишите нам сегoдня."
        self.assertEqual(value(text, "russian_token_count"), 8)
        self.assertEqual(value(text, "homoglyph_folded_token_count"), 2)
        self.assertEqual(value(text, "mixed_script_token_count"), 2)
        report = audit(text.encode("utf-8"), text)
        self.assertIn("MIXED_SCRIPT_TOKENS_PRESENT", report["warnings"])

    def test_non_lookalike_mixed_tokens_are_not_folded(self):
        text = "Купите Fитнес"
        self.assertEqual(value(text, "mixed_script_token_count"), 1)
        self.assertEqual(value(text, "homoglyph_folded_token_count"), 0)

    def test_apostrophe_joins_names(self):
        self.assertEqual(value("Д'Артаньян пришёл.", "russian_token_count"), 2)

    def test_method_version_is_bumped_not_silent(self):
        versions = {m["method_version"] for m in calculate("Текст.") if m["method_version"]}
        self.assertIn("0.8.0", versions)


class Utf8Output(unittest.TestCase):
    def test_stdout_is_utf8_even_on_latin_code_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.txt"
            path.write_text("Привет, мир.", encoding="utf-8")
            for encoding in ("cp1252", "cp437", "ascii"):
                with self.subTest(encoding=encoding):
                    env = dict(os.environ, PYTHONIOENCODING=encoding)
                    result = subprocess.run(
                        [sys.executable, str(SKILL / "scripts" / "analyze.py"),
                         "--input", str(path)],
                        capture_output=True, env=env, timeout=60, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(result.stdout.decode("utf-8"))
                    self.assertEqual(report["mode"], "audit")


class ZhuravlevExperimental(unittest.TestCase):
    def test_published_vectors(self):
        results = {v["id"]: evaluate_vector(v) for v in PUBLISHED_VECTORS}
        for result in results.values():
            self.assertTrue(result["matches_published_rounding"]
                            or result["matches_published_truncation"], result["id"])
        lik = results["zh-lik-weighted"]
        self.assertEqual([round(w, 2) for w in lik["weights"]], [7.04, 4.0, 1.0])
        self.assertAlmostEqual(lik["weighted_sum"], 24.776, places=6)
        self.assertAlmostEqual(lik["computed"], 2.057807, places=5)
        self.assertFalse(lik["matches_published_rounding"])  # documented discrepancy

    def test_arithmetic(self):
        self.assertEqual(distribution_mean({1: 9, 2: 34, 3: 5, 4: 2, 5: 0}), 2.0)
        self.assertAlmostEqual(simple_mean([4.1, 2.9, 1.5, 3.5]), 3.0)
        single = weighted_score([{"score": 3.0, "frequency": 1.0, "first": True,
                                  "stressed": True}])
        self.assertEqual(single["value"], 3.0)
        self.assertEqual(single["weights"], [8.0])
        self.assertEqual(single["status"], "experimental")

    def test_rejections(self):
        bad = [
            [],
            [{"score": 6, "frequency": 1}],
            [{"score": 3, "frequency": 0}],
            [{"score": 3, "frequency": 1, "first": True},
             {"score": 3, "frequency": 1, "first": True}],
            [{"score": 3, "frequency": 1, "word": "секрет"}],
            [{"score": True, "frequency": 1}],
        ]
        for elements in bad:
            with self.subTest(elements=str(elements)[:40]):
                with self.assertRaises(FormulaError):
                    weighted_score(elements)
        with self.assertRaises(FormulaError):
            run({"scores": [3], "counts": {"1": 1}})

    def test_cli_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "elements.json"
            path.write_text(json.dumps({"counts": {"1": 9, "2": 34, "3": 5, "4": 2}}),
                            encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SKILL / "scripts" / "zhuravlev.py"), "--input", str(path)],
                capture_output=True, timeout=60, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual(report["value"], 2.0)
            self.assertIn("NOT_DIATON_NOT_HISTORICAL_PROGRAM_OUTPUT", report["warnings"])
            try:
                from jsonschema import Draft202012Validator
            except ImportError:
                return
            schema = json.loads((ROOT / "schemas" / "zhuravlev-experimental.schema.json")
                                .read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(report)

    def test_run_entry_points(self):
        lik = run({"elements": PUBLISHED_VECTORS[3]["input"]["elements"]})
        self.assertEqual(lik["method_id"], "zhuravlev.weighted_mean")
        self.assertEqual(run({"scores": [1.9, 2.0, 3.4]})["method_id"], "zhuravlev.simple_mean")
        dist = run({"counts": {"1": 9, "2": 34, "3": 5, "4": 2}, "scale": "сильный — слабый"})
        self.assertEqual(dist["value"], 2.0)
        for bad in ([], {"scores": "3"}, {"counts": []}, {"counts": {"x": 1}},
                    {"counts": {"9": 1}}, {"counts": {"1": -1}}, {"counts": {"1": 0}},
                    {"scores": []}, {"scores": ["3"]}, {"scores": [float("nan")]},
                    {"elements": "x"}, {"elements": [1]},
                    {"elements": [{"score": 3, "frequency": 1, "first": "yes"}]},
                    {"elements": [{"score": 3, "frequency": 1}] * 65}, {"other": 1}):
            with self.subTest(bad=str(bad)[:40]):
                with self.assertRaises(FormulaError):
                    run(bad)

    def test_main_audit_still_has_no_historical_score(self):
        ids = {m["id"]: m for m in calculate("храп")}
        self.assertIsNone(ids["historical_suggestive_score"]["value"])


if __name__ == "__main__":
    unittest.main()
