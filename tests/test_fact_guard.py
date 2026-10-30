"""Issue #7 acceptance: deterministic A8 risk screening and safe CLI behavior."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/slovodel"
sys.path.insert(0, str(SKILL))

from slovodel_core.fact_guard import (  # noqa: E402
    CATEGORIES, check, inventory, validate_terms,
)

VALIDATE = SKILL / "scripts/validate.py"
SCHEMA = ROOT / "schemas/fact-guard.schema.json"


def kinds(before: str, after: str, terms=()):
    return {x["kind"] for x in check(before, after, terms)["findings"]}


class FactGuardTests(unittest.TestCase):
    def test_identical_is_not_publication_approval(self):
        result = check("Цена 80 000 ₽. Срок до пятницы.", 
                       "Цена 80 000 ₽. Срок до пятницы.")
        self.assertEqual(result["decision"], "unchanged")
        self.assertFalse(result["publish_ready"])
        self.assertEqual(result["semantic_equivalence"], "not_verified")
        self.assertFalse(result["changed"])
        self.assertEqual(result["findings"], [])

    def test_punctuation_change_requires_human_review(self):
        result = check("Привет, мир.", "Привет, мир!")
        self.assertEqual(result["decision"], "review_required")
        self.assertFalse(result["publish_ready"])
        self.assertEqual(result["findings"], [])

    def test_removed_money_is_blocked(self):
        result = check("Оплата 80 000 ₽ за месяц.", "Оплата обсуждается.")
        self.assertEqual(result["decision"], "blocked")
        self.assertIn("money", kinds("Оплата 80 000 ₽", "Оплата обсуждается"))
        self.assertEqual(next(x for x in result["findings"] if x["kind"]=="money")[
            "removed_count"], 1)

    def test_changed_money_with_same_count_is_blocked(self):
        self.assertIn("money", kinds("Оплата 50 000 ₽", "Оплата 80 000 ₽"))

    def test_added_unsupported_money_is_blocked(self):
        result = check("Оплата обсуждается.", "Оплата 80 000 ₽")
        self.assertIn("money", {x["kind"] for x in result["findings"]})
        self.assertEqual(next(x for x in result["findings"] if x["kind"]=="money")[
            "added_count"], 1)

    def test_equivalent_money_grouping_not_false_blocked(self):
        self.assertNotIn("money",
            kinds("Оплата 80000 ₽", "Оплата 80 000 ₽"))

    def test_money_scale_changes_are_caught(self):
        self.assertIn("money", kinds("Бюджет 80 тыс. ₽", "Бюджет 90 тыс. ₽"))

    def test_url_change_with_same_number_detected(self):
        self.assertIn("url", kinds(
            "https://example.org/a?x=1", "https://example.org/b?x=1"
        ))

    def test_url_not_leaking_query_numeric_parts(self):
        before=inventory("Пишите https://example.org/invite?id=734")
        self.assertEqual(sum(before["number"].values()), 0)
        self.assertEqual(sum(before["url"].values()), 1)

    def test_email_replacement_detected(self):
        self.assertIn("email", kinds(
            "Контакт: hello@example.org", "Контакт: sales@example.org"))

    def test_exact_date_and_deadline_changes_detected(self):
        self.assertIn("date", kinds("До 15.10.2026", "До 16.10.2026"))
        self.assertIn("date", kinds("Событие 15 октября 2026", 
                                     "Событие 16 октября 2026"))
        self.assertIn("deadline", kinds(
            "Отклики до пятницы", "Отклики до четверга"))

    def test_equivalent_full_date_formats(self):
        self.assertNotIn("date", kinds("15.10.2026", "2026-10-15"))
        self.assertIn("date", kinds("15.10.2026", "2026-10-16"))

    def test_range_upper_bound_detected(self):
        self.assertIn("range", kinds("От 5 до 7 дней", "От 5 до 9 дней"))
        self.assertIn("range", kinds("5–7 дней", "5–8 дней"))

    def test_duration_unit_change_caught(self):
        self.assertIn("quantity", kinds(
            "Занятость 20 часов в неделю", "Занятость 20 часов в месяц"))

    def test_percentage_change_detected(self):
        self.assertIn("quantity", kinds("Скидка 10%", "Скидка 15%"))

    def test_generic_number_detected(self):
        self.assertIn("number", kinds(
            "Нужно 12 кандидатов", "Нужно 15 кандидатов"))

    def test_removed_negation_detected(self):
        self.assertIn("condition", kinds(
            "Оплата не требуется", "Оплата требуется"))

    def test_added_negation_detected(self):
        self.assertIn("condition", kinds("Оплата требуется", "Оплата не требуется"))

    def test_modal_may_to_must_detected(self):
        self.assertIn("condition", kinds(
            "Пользователь может потребовать удаления.",
            "Пользователь должен потребовать удаления."))

    def test_mandatory_conditions_detected(self):
        self.assertIn("condition", kinds(
            "Доступ только после подтверждения.",
            "Доступ после подтверждения."))

    def test_organization_legal_name_detected(self):
        self.assertIn("organization", kinds(
            "ООО «Альфа»", "ООО «Бета»"))

    def test_full_person_name_detected(self):
        self.assertIn("person", kinds(
            "Иван Иванов оформил заявку.", "Пётр Сидоров оформил заявку."))

    def test_custom_important_clause_detected(self):
        terms=validate_terms(["Доставка только после оплаты"])
        before="Доставка только после оплаты. Укажите адрес."
        after="Доставка без предоплаты. Укажите адрес."
        self.assertIn("protected_term", kinds(before, after, terms))

    def test_term_can_be_unchanged_despite_punctuation(self):
        terms=validate_terms(["Оплата после выполнения"])
        self.assertNotIn("protected_term", kinds(
            "Оплата после выполнения.", "Оплата после выполнения!", terms))

    def test_missing_or_duplicate_terms_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PROTECTED_TERM"):
            validate_terms(["СРОК", "срок"])
        with self.assertRaisesRegex(ValueError, "TOO_MANY_PROTECTED_TERMS"):
            validate_terms([f"термин{i}" for i in range(101)])
        with self.assertRaisesRegex(ValueError, "INVALID_PROTECTED_TERMS"):
            validate_terms(["П" * 257])

    def test_privacy_never_includes_literal_values(self):
        confidential="Секретная 80 000 ₽. https://secret.example/q?key=8675309"
        result=check(confidential, "Изменён текст.")
        report=json.dumps(result,ensure_ascii=False)
        for value in ("Секретная", "80 000", "secret.example", "8675309"):
            self.assertNotIn(value, report)
        self.assertEqual(result["decision"], "blocked")

    def test_total_length_of_findings_is_category_bounded(self):
        before=" ".join("10 рублей" for _ in range(300))
        result=check(before,"Убрано.")
        self.assertLessEqual(len(result["findings"]),len(CATEGORIES))

    def test_disclaimer_for_same_negation_count_but_changed_scope(self):
        result=check("Не допускается возврат после оплаты.",
                     "Возврат не допускается до оплаты.")
        self.assertNotEqual(result["decision"], "unchanged")
        self.assertIn("NEGATION_SCOPE_NOT_VERIFIED",result["warnings"])
        self.assertFalse(result["publish_ready"])

    def test_nfc_visual_equivalence_requires_at_least_review(self):
        result=check("е\u0308лка", "ёлка")
        self.assertEqual(result["decision"], "review_required")

    def test_validated_terms_do_not_expose_value_as_key(self):
        result=check("Условие: только по договору.", "Условие: свободно.",
                     validate_terms(["только по договору"]))
        obj=result["findings"]
        self.assertIn("protected_term", {x["kind"] for x in obj})
        self.assertNotIn("по договору",json.dumps(result,ensure_ascii=False))


class FactGuardCliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)

    def file(self,name,text):
        p=self.home/name
        p.write_text(text,encoding="utf-8")
        return p

    def run_guard(self,before,after,*args):
        return subprocess.run(
            [sys.executable,str(VALIDATE),"--before",str(before),
             "--after",str(after),*map(str,args)],
            capture_output=True,text=True,encoding="utf-8",timeout=15,
            check=False,
        )

    def test_cli_block_returns_5_and_json(self):
        b=self.file("b.txt","Сумма 90 000 ₽")
        a=self.file("a.txt","Сумма 100 000 ₽")
        result=self.run_guard(b,a)
        self.assertEqual(result.returncode,5,result.stderr)
        report=json.loads(result.stdout)
        self.assertEqual(report["decision"],"blocked")
        self.assertEqual(report["source_sha256"],
                         hashlib.sha256(b.read_bytes()).hexdigest())
        self.assertEqual(report["revision_sha256"],
                         hashlib.sha256(a.read_bytes()).hexdigest())
        self.assertFalse(report["publish_ready"])
        self.assertEqual(b.read_text(encoding="utf-8"),"Сумма 90 000 ₽")

    def test_cli_identical_returns_zero(self):
        p=self.file("same.txt","Не разглашать данные.")
        result=self.run_guard(p,p)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["decision"],"unchanged")

    def test_cli_review_required_returns_zero_not_approval(self):
        b=self.file("b.txt","Услуга удобная.")
        a=self.file("a.txt","Услуга простая.")
        result=self.run_guard(b,a)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout)
        self.assertEqual(report["decision"],"review_required")
        self.assertFalse(report["publish_ready"])

    def test_cli_protected_file_blocks_dropped_phrase(self):
        b=self.file("b.txt","Соблюдайте согласование с редактором.")
        a=self.file("a.txt","Работайте свободно.")
        phrases=self.file("terms.txt","согласование с редактором\n")
        result=self.run_guard(b,a,"--protected-file",phrases)
        self.assertEqual(result.returncode,5,result.stderr)
        data=json.loads(result.stdout)
        self.assertEqual(data["protected_terms_count"],1)
        self.assertIn("protected_term",{r["kind"] for r in data["findings"]})

    def test_cli_bad_terms_rejected_without_printing_values(self):
        b=self.file("b.txt","А")
        a=self.file("a.txt","Б")
        terms=self.file("t.txt","SECRETWORD\nsecretword\n")
        result=self.run_guard(b,a,"--protected-file",terms)
        self.assertEqual(result.returncode,3,result.stderr)
        self.assertIn("DUPLICATE_PROTECTED_TERM",result.stderr)
        self.assertNotIn("SECRETWORD",result.stdout+result.stderr)

    def test_cli_exclusive_output_on_block(self):
        b=self.file("b.txt","Оплата 100 ₽")
        a=self.file("a.txt","Оплата 200 ₽")
        out=self.home/"guard.json"
        first=self.run_guard(b,a,"--output",out)
        self.assertEqual(first.returncode,5,first.stderr)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["decision"],
                         "blocked")
        snapshot=out.read_bytes()
        second=self.run_guard(b,a,"--output",out)
        self.assertEqual(second.returncode,4)
        self.assertEqual(out.read_bytes(),snapshot)

    def test_cli_bad_input_not_leaked(self):
        b=self.file("before.txt","secret")
        a=self.home/"missing.txt"
        result=self.run_guard(b,a)
        self.assertEqual(result.returncode,3)
        self.assertNotIn("secret",result.stdout+result.stderr)

    def test_full_schema_validation_when_installed(self):
        schema=json.loads(SCHEMA.read_text(encoding="utf-8"))
        b=self.file("b.txt","Оплата 100 ₽")
        a=self.file("a.txt","Оплата 200 ₽")
        result=self.run_guard(b,a)
        self.assertEqual(result.returncode,5)
        report=json.loads(result.stdout)
        self.assertEqual(set(report),set(schema["properties"]))
        self.assertTrue(set(schema["required"]) <= set(report))
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(report)
        report["decision"]="unchanged"
        with self.assertRaises(Exception):
            Draft202012Validator(schema).validate(report)


if __name__=="__main__":
    unittest.main()
