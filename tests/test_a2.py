"""A2: local reference profiles, provenance, licensing metadata, edge cases."""
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

from slovodel_core.a2 import PROFILE_METHOD_VERSION  # noqa: E402
from slovodel_core.a2 import (  # noqa: E402
    ProfileError, compare_rate, count_letters, make_profile, parse_profile,
    calculate_reference,
)
from slovodel_core.metrics import RU_ALPHABET, calculate  # noqa: E402

BUILDER = SKILL / "scripts/build_reference.py"
AUDIT = SKILL / "scripts/analyze.py"
COMPARE = SKILL / "scripts/compare.py"


def metadata():
    return dict(
        source_label="Self-authored test text",
        source_url="local://synthetic-test",
        genre="synthetic",
        corpus_version="2026-10-test",
        license_id="CC0-1.0",
        rights_basis="Self-authored, explicitly self-declared; no external approval.",
    )


def fixture(text="мама мыла раму"):
    raw = text.encode("utf-8")
    return make_profile(raw, text, **metadata())


class A2UnitTests(unittest.TestCase):
    def test_default_normative_unavailable(self):
        metrics = {m["id"]: m for m in calculate("мама")}
        self.assertEqual(metrics["norm_letter_deviation"]["status"],
                         "unavailable")
        self.assertIsNone(metrics["norm_letter_deviation"]["value"])
        self.assertNotIn("local_ref_а_delta_pp", metrics)

    def test_exact_delta_and_ratio(self):
        self.assertEqual(compare_rate(1, 4, 1, 2), (-25.0, 0.5))
        self.assertEqual(compare_rate(2, 4, 1, 2), (0.0, 1.0))
        self.assertEqual(compare_rate(3, 4, 1, 2), (25.0, 1.5))

    def test_zero_baseline_ratio_unavailable_but_delta_valid(self):
        self.assertEqual(compare_rate(1, 4, 0, 4), (25.0, None))
        self.assertEqual(compare_rate(0, 4, 0, 4), (0.0, None))

    def test_zero_sample_and_bad_denominators(self):
        self.assertEqual(compare_rate(0, 0, 1, 2), (None, None))
        self.assertEqual(compare_rate(1, 4, 1, 0), (None, None))
        self.assertEqual(compare_rate(5, 4, 1, 2), (None, None))
        self.assertEqual(compare_rate(True, 4, 1, 2), (None, None))
        self.assertEqual(compare_rate(1, 4, -1, 2), (None, None))

    def test_profile_has_33_letters_and_provenance(self):
        p = fixture("Ёж е\u0308ж и ель")
        self.assertEqual(len(p["counts"]), 33)
        self.assertEqual(p["counts"]["ё"], 2)
        self.assertEqual(p["counts"]["е"], 1)
        self.assertEqual(sum(p["counts"].values()), p["total_letters"])
        self.assertEqual(p["method_version"], PROFILE_METHOD_VERSION)
        self.assertEqual(p["license_status"], "self_declared_unverified")
        self.assertEqual(p["profile_kind"], "user_supplied_non_normative")
        self.assertNotIn("Ёж", json.dumps(p, ensure_ascii=False))

    def test_url_and_email_exclusion_same_as_a1(self):
        counts = count_letters("мама https://пример.рф/путь hello@мир.рф ёж")
        self.assertEqual(counts["м"], 2)
        self.assertEqual(counts["ё"], 1)
        self.assertEqual(sum(counts.values()), len("мамаёж"))

    def test_normalization_equivalent_profiles_counts(self):
        self.assertEqual(
            count_letters("е\u0308лка"), count_letters("ёлка")
        )

    def test_fingerprints_and_metadata_are_repeatable(self):
        p=fixture()
        dumped=json.dumps(p,ensure_ascii=False)
        first,d1=parse_profile(dumped)
        second,d2=parse_profile(json.dumps(p,sort_keys=True,ensure_ascii=False))
        self.assertEqual(d1,d2)
        self.assertEqual(first,second)
        self.assertTrue(d1.startswith("local-sha256:"))
        self.assertEqual(len(d1),77)

    def test_reject_tampered_letter_sum(self):
        p=fixture()
        p["counts"]["а"]+=1
        with self.assertRaisesRegex(ProfileError, "PROFILE_INVALID_TOTAL"):
            parse_profile(json.dumps(p))

    def test_reject_duplicate_keys(self):
        p=json.dumps(fixture(),ensure_ascii=False)
        tampered=p[:-1]+',"total_letters": 999}'
        with self.assertRaisesRegex(ProfileError, "PROFILE_DUPLICATE_KEY"):
            parse_profile(tampered)

    def test_reject_outdated_method_version(self):
        p=fixture()
        p["method_version"]="0.0.0"
        with self.assertRaisesRegex(ProfileError, "PROFILE_VERSION_MISMATCH"):
            parse_profile(json.dumps(p))

    def test_reject_false_verified_license_status(self):
        p=fixture()
        p["license_status"]="verified"
        with self.assertRaisesRegex(ProfileError, "PROFILE_INVALID_METHOD"):
            parse_profile(json.dumps(p))

    def test_reject_negative_boolean_and_missing_letters(self):
        for bad in (-1,True):
            p=fixture()
            p["counts"]["а"]=bad
            with self.assertRaises(ProfileError):
                parse_profile(json.dumps(p))
        p=fixture()
        del p["counts"]["ё"]
        with self.assertRaisesRegex(ProfileError, "PROFILE_INVALID_ALPHABET"):
            parse_profile(json.dumps(p))

    def test_reject_invalid_or_missing_source_metadata(self):
        p=fixture()
        p["license_id"]=""
        with self.assertRaisesRegex(ProfileError, "PROFILE_MISSING_PROVENANCE"):
            parse_profile(json.dumps(p))
        p=fixture()
        p["source_sha256"]="A"*64
        with self.assertRaisesRegex(ProfileError, "PROFILE_INVALID_SOURCE_HASH"):
            parse_profile(json.dumps(p))

    def test_profile_rejects_nonrussian_input(self):
        with self.assertRaisesRegex(ProfileError,"PROFILE_NO_RUSSIAN_LETTERS"):
            make_profile(b"123", "123", **metadata())

    def test_user_reference_is_reproducible_not_normative(self):
        p=fixture("аааб")
        profile,digest=parse_profile(json.dumps(p))
        measures={m["id"]:m for m in calculate("аааабб", (profile,digest))}
        self.assertEqual(measures["local_ref_а_delta_pp"]["status"],
                         "reproducible")
        self.assertAlmostEqual(measures["local_ref_а_delta_pp"]["value"],
                               -8.33333333)
        self.assertAlmostEqual(measures["local_ref_а_ratio"]["value"],
                               .88888889)
        self.assertEqual(measures["local_ref_а_ratio"]["dataset_id"], digest)
        self.assertIn("LOCAL_REFERENCE_NOT_NORMATIVE",
                      measures["local_ref_а_delta_pp"]["warnings"])
        self.assertEqual(measures["norm_letter_deviation"]["status"],
                         "unavailable")

    def test_ratio_undefined_when_q_zero(self):
        p=fixture("аааа")
        profile,digest=parse_profile(json.dumps(p))
        measures={m["id"]:m for m in calculate("бб", (profile,digest))}
        self.assertEqual(measures["local_ref_б_delta_pp"]["value"],100.0)
        self.assertIsNone(measures["local_ref_б_ratio"]["value"])
        self.assertEqual(measures["local_ref_б_ratio"]["status"],"unavailable")
        self.assertIn("SMALL_REFERENCE_CORPUS",
                      measures["local_ref_б_delta_pp"]["warnings"])
        self.assertIn("SMALL_SAMPLE",
                      measures["local_ref_б_delta_pp"]["warnings"])

    def test_empty_sample_not_reported_as_zero_percent(self):
        p=fixture()
        profile,digest=parse_profile(json.dumps(p))
        rows=calculate_reference("123!!!",profile,digest)
        self.assertTrue(all(m["status"]=="unavailable" and m["value"] is None
                            for m in rows))

    def test_bad_dataset_id_is_rejected(self):
        p=fixture()
        with self.assertRaisesRegex(ProfileError,"PROFILE_INVALID_DATASET_ID"):
            calculate_reference("мама",p,"local-sha256:no")

    def test_profile_is_too_short_for_normative_label(self):
        p=fixture("мама")
        profile,digest=parse_profile(json.dumps(p))
        m=next(m for m in calculate("мама",(profile,digest))
               if m["id"]=="local_ref_м_delta_pp")
        self.assertIn("SMALL_REFERENCE_CORPUS",m["warnings"])

    def test_untrusted_profile_code_never_echoes_personal_content(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            bad=home/"bad.json"
            bad.write_text('{"secret":"PRIVATE_USER_INFORMATION"}',encoding="utf-8")
            sample=home/"text.txt"
            sample.write_text("текст",encoding="utf-8")
            p=subprocess.run([sys.executable,str(AUDIT),"--input",str(sample),
                              "--reference",str(bad)],capture_output=True,text=True,
                             encoding="utf-8",timeout=12)
            self.assertEqual(p.returncode,3)
            self.assertNotIn("PRIVATE_USER_INFORMATION",p.stderr+p.stdout)

    def test_cli_builder_analyze_compare(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            source=home/"source.txt"
            source.write_text("мама мыла раму",encoding="utf-8")
            profile=home/"profile.json"
            cmd=[sys.executable,str(BUILDER),"--input",str(source),
                 "--source-label","my test","--source-url","local://mytest",
                 "--genre","synthetic","--corpus-version","v1",
                 "--license-id","CC0-1.0","--rights-basis","self-authored",
                 "--output",str(profile)]
            build=subprocess.run(cmd,capture_output=True,text=True,
                                 encoding="utf-8",timeout=12)
            self.assertEqual(build.returncode,0,build.stderr)
            raw=source.read_bytes()
            self.assertEqual(json.loads(profile.read_text(encoding="utf-8"))[
                "source_sha256"],hashlib.sha256(raw).hexdigest())
            ana=subprocess.run([sys.executable,str(AUDIT),"--input",str(source),
                                "--reference",str(profile)],capture_output=True,
                               text=True,encoding="utf-8",timeout=12)
            self.assertEqual(ana.returncode,0,ana.stderr)
            audited=json.loads(ana.stdout)
            measured={m["id"]:m for m in audited["measurements"]}
            self.assertIn("local_ref_м_delta_pp",measured)
            self.assertEqual(measured["norm_letter_deviation"]["status"],
                             "unavailable")
            comp=subprocess.run([sys.executable,str(COMPARE),"--before",str(source),
                                 "--after",str(source),"--reference",str(profile)],
                                capture_output=True,text=True,encoding="utf-8",
                                timeout=12)
            self.assertEqual(comp.returncode,0,comp.stderr)
            compared=json.loads(comp.stdout)
            self.assertTrue(all(x["delta"]==0 for x in compared["comparisons"]))
            self.assertIn("LOCAL_REFERENCE_NOT_NORMATIVE",compared["warnings"])

    def test_profile_json_schema_full_validation(self):
        # stdlib invariants always run; full Draft 2020-12 checks when available.
        schema_path = ROOT / "schemas/local-reference.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        profile = fixture("мама мыла раму")
        self.assertEqual(set(profile), set(schema["required"]))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(profile["counts"]), set(schema["properties"]["counts"]["required"]))
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(profile)
        invalid = dict(profile, profile_kind="verified_normative")
        with self.assertRaises(Exception):
            validator.validate(invalid)

    def test_unknown_json_key_and_wrong_preprocessing_rejected(self):
        p=fixture()
        p["unauthorised_score"]=99
        with self.assertRaisesRegex(ProfileError, "PROFILE_INVALID_SHAPE"):
            parse_profile(json.dumps(p))
        p=fixture()
        p["preprocessing"]="change_yo_to_e"
        with self.assertRaisesRegex(ProfileError, "PROFILE_INVALID_METHOD"):
            parse_profile(json.dumps(p))

    def test_compare_rejects_mismatched_reference_version(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            source=home/"text.txt"
            source.write_text("текст",encoding="utf-8")
            profile=fixture()
            profile["method_version"]="old-method"
            reference=home/"profile.json"
            reference.write_text(json.dumps(profile),encoding="utf-8")
            result=subprocess.run(
                [sys.executable,str(COMPARE),"--before",str(source),
                 "--after",str(source),"--reference",str(reference)],
                capture_output=True,text=True,encoding="utf-8",timeout=12,
            )
            self.assertEqual(result.returncode,3)
            self.assertIn("PROFILE_VERSION_MISMATCH",result.stderr)
            self.assertEqual(result.stdout,"")

    def test_local_reference_requires_explicit_optin(self):
        p=fixture()
        profile,digest=parse_profile(json.dumps(p))
        normal={m["id"] for m in calculate("мама")}
        opted={m["id"] for m in calculate("мама", (profile,digest))}
        self.assertTrue("local_ref_а_delta_pp" not in normal)
        self.assertTrue("local_ref_а_delta_pp" in opted)
        self.assertEqual(len(opted-normal),66)


if __name__=="__main__":
    unittest.main()
