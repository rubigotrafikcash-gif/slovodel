"""Issue #3: subprocess acceptance tests of the offline report scaffold."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ANALYZE = ROOT / "skills/slovodel/scripts/analyze.py"
COMPARE = ROOT / "skills/slovodel/scripts/compare.py"
SCHEMAS = ROOT / "schemas"


class OfflineCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tmp = Path(self.directory.name)

    def file(self, name: str, data: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path

    def call(self, script: Path, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(script), *map(str, arguments)],
            text=True, encoding="utf-8", capture_output=True, check=False,
            timeout=15,
        )

    def test_audit_contract_raw_bytes_unchanged(self):
        raw = "е\u0308, ё. Пример".encode("utf-8")
        path = self.file("input.txt", raw)
        result = self.call(ANALYZE, "--input", path, "--mode", "audit")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(report["source"]["sha256"], report["source_sha256"])
        self.assertEqual(report["source"]["size_bytes"], len(raw))
        self.assertTrue(report["source"]["normalization_changed"])
        self.assertEqual(path.read_bytes(), raw)
        self.assertNotIn("Пример", result.stdout)
        self.assertEqual(report["historical_compatibility"], "not_verified")
        self.assertFalse(report["source_policy"]["network_access"])
        self.assertTrue(all(
            m["status"] == "unavailable" and m["value"] is None
            for m in report["measurements"]
        ))

    def test_same_input_deterministic(self):
        path = self.file("input.txt", "Мама мыла раму".encode())
        first = self.call(ANALYZE, "--input", path)
        second = self.call(ANALYZE, "--input", path)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)

    def test_compare_no_invented_deltas(self):
        path = self.file("input.txt", "Привет".encode())
        result = self.call(COMPARE, "--before", path, "--after", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["before"]["sha256"], report["after"]["sha256"])
        self.assertEqual(report["comparison_status"], "unavailable")
        self.assertEqual(report["comparisons"], [])
        self.assertEqual(report["mode"], "compare")

    def test_bad_encoding_does_not_echo_data(self):
        path = self.file("secrets.txt", b"PRIVATESECRET\xff")
        result = self.call(ANALYZE, "--input", path)
        self.assertEqual(result.returncode, 3)
        self.assertIn("INPUT_NOT_UTF8", result.stderr)
        self.assertNotIn("PRIVATESECRET", result.stderr + result.stdout)

    def test_missing_file(self):
        result = self.call(ANALYZE, "--input", self.tmp / "missing.txt")
        self.assertEqual(result.returncode, 3)
        self.assertIn("INPUT_READ_FAILED", result.stderr)

    def test_oversized_file(self):
        path = self.file("large.txt", b"z" * (1_048_576 + 1))
        result = self.call(ANALYZE, "--input", path)
        self.assertEqual(result.returncode, 3)
        self.assertIn("INPUT_TOO_LARGE", result.stderr)
        self.assertNotIn("z" * 10, result.stderr)

    def test_symlink_rejected(self):
        path = self.file("original.txt", b"Hello")
        link = self.tmp / "alias.txt"
        try:
            link.symlink_to(path)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not allow symlinks")
        result = self.call(ANALYZE, "--input", link)
        self.assertEqual(result.returncode, 3)
        self.assertIn("INPUT_SYMLINK", result.stderr)

    def test_fifo_input_rejected_without_blocking(self):
        import os
        fifo = self.tmp / "pipe"
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO unsupported on this OS")
        os.mkfifo(fifo)
        result = self.call(ANALYZE, "--input", fifo)
        self.assertEqual(result.returncode, 3)
        self.assertIn("INPUT_NOT_REGULAR_FILE", result.stderr)

    def test_output_symlink_never_overwrites_target(self):
        source = self.file("input.txt", b"DATA")
        target = self.file("target.json", b"PROTECTED")
        link = self.tmp / "out.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not allow symlinks")
        result = self.call(ANALYZE, "--input", source, "--output", link)
        self.assertEqual(result.returncode, 4)
        self.assertEqual(target.read_bytes(), b"PROTECTED")

    def test_empty_file_warning(self):
        path = self.file("empty.txt", b"")
        result = self.call(ANALYZE, "--input", path)
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertIn("EMPTY_INPUT", report["warnings"])

    def test_output_exclusive_and_private(self):
        path = self.file("input.txt", b"abc")
        output = self.tmp / "result.json"
        first = self.call(ANALYZE, "--input", path, "--output", output)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, "")
        self.assertEqual(json.loads(output.read_text())["mode"], "audit")
        before = output.read_bytes()
        second = self.call(ANALYZE, "--input", path, "--output", output)
        self.assertEqual(second.returncode, 4)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(path.read_bytes(), b"abc")
        if sys.platform != "win32":
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_input_output_same_path_rejected(self):
        path = self.file("input.txt", b"KEEP")
        result = self.call(ANALYZE, "--input", path, "--output", path)
        self.assertEqual(result.returncode, 4)
        self.assertEqual(path.read_bytes(), b"KEEP")

    def test_bad_cli_mode(self):
        path = self.file("input.txt", b"abc")
        result = self.call(ANALYZE, "--input", path, "--mode", "rewrite")
        self.assertEqual(result.returncode, 2)

    def test_utf8_bom_kept_in_hash(self):
        raw = b"\xef\xbb\xbf" + "Текст".encode()
        path = self.file("bom.txt", raw)
        result = self.call(ANALYZE, "--input", path)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["source"]["size_bytes"], len(raw))

    def test_schema_file_is_valid_json(self):
        for path in SCHEMAS.glob("*.json"):
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"],
                                 "https://json-schema.org/draft/2020-12/schema")
                self.assertFalse(schema["additionalProperties"])

    def test_output_shapes_against_schema(self):
        # This stdlib-level invariant runs even without third-party jsonschema.
        # When jsonschema is present, additionally enforce the full draft 2020-12.
        first = self.file("first.txt", "Текст".encode())
        outputs = [
            ("analysis.schema.json",
             json.loads(self.call(ANALYZE, "--input", first).stdout)),
            ("compare.schema.json",
             json.loads(self.call(COMPARE, "--before", first,
                                  "--after", first).stdout)),
        ]
        for schema_name, document in outputs:
            with self.subTest(schema=schema_name):
                schema = json.loads((SCHEMAS / schema_name).read_text())
                self.assertTrue(set(schema["required"]) <= set(document))
                self.assertEqual(set(document), set(schema["properties"]))
                try:
                    from jsonschema import Draft202012Validator
                except ImportError:
                    continue
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(document)


if __name__ == "__main__":
    unittest.main()
