#!/usr/bin/env python3
"""Validate Agent Skills layout and smoke-test copied *standalone* skill.

Only stdlib required. Does NOT launch Codex/Claude models or modify HOME.
Makes temporary Codex- and Claude-style directories, then runs real Core CLI
from outside the repository with python -I.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "slovodel"
SCHEMA_NAMES = ("analysis", "compare", "fact-guard", "local-reference", "workflow", "zhuravlev-experimental")
REQUIRED = (
    "SKILL.md", "LICENSE", "scripts/workflow.py", "scripts/analyze.py",
    "scripts/compare.py", "scripts/validate.py", "scripts/build_reference.py",
    "slovodel_core/__init__.py", "slovodel_core/workflow.py",
    "slovodel_core/metrics.py", "slovodel_core/fact_guard.py",
    "slovodel_core/context.py", "slovodel_core/equivalence.py",
    "assets/voice-brief.md", "references/agent-workflow.md",
    "references/compliance.md", "references/morphology-licenses.md",
    "references/corpus-license-review.md",
    "references/methodology.md", "references/method-in-practice.md",
    "references/natural-russian.md", "references/semantic-review.md",
)
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def verify_package(source: Path) -> dict:
    if not source.is_dir() or source.name != "slovodel":
        raise AssertionError("PACKAGE_INVALID_ROOT")
    for required in REQUIRED:
        if not (source / required).is_file():
            raise AssertionError("PACKAGE_MISSING_RESOURCE:" + required)
    for file in source.rglob("*"):
        if file.is_symlink():
            raise AssertionError("PACKAGE_SYMLINK_DISALLOWED")
    front = (source / "SKILL.md").read_text(encoding="utf-8")
    if not front.startswith("---\n"):
        raise AssertionError("SKILL_METADATA_MISSING")
    parts = front.split("---\n", 2)
    if len(parts) != 3:
        raise AssertionError("SKILL_METADATA_INVALID")
    metadata = parts[1]
    name = re.search(r"(?m)^name:\s*(\S+)\s*$", metadata)
    description = re.search(r"(?m)^description:\s*(.+)$", metadata)
    license_field = re.search(r"(?m)^license:\s*(\S+)\s*$", metadata)
    if not name or name.group(1) != source.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name.group(1)):
        raise AssertionError("SKILL_NAME_INVALID")
    if not description:
        raise AssertionError("SKILL_DESCRIPTION_MISSING")
    # This skill uses YAML's valid double-quoted syntax, which JSON can read.
    desc = json.loads(description.group(1))
    if not isinstance(desc, str) or not (1 <= len(desc) <= 1024):
        raise AssertionError("SKILL_DESCRIPTION_INVALID")
    if not license_field or license_field.group(1) != "MIT":
        raise AssertionError("SKILL_LICENSE_INVALID")
    if "MIT License" not in (source / "LICENSE").read_text(encoding="utf-8"):
        raise AssertionError("SKILL_LICENSE_FILE_INVALID")
    all_md = list(source.rglob("*.md"))
    for md in all_md:
        relative_to_root = md.relative_to(source)
        content = md.read_text(encoding="utf-8")
        for destination in LINK.findall(content):
            if destination.startswith(("https://", "http://", "#", "mailto:")):
                continue
            # Ignore fragment identifiers in relative paths.
            target = (md.parent / destination.split("#", 1)[0]).resolve()
            if not target.is_relative_to(source.resolve()) or not target.is_file():
                raise AssertionError(
                    "SKILL_LOCAL_LINK_BROKEN:" + str(relative_to_root) + ":" + destination
                )
    for name in SCHEMA_NAMES:
        bundled = source / "schemas" / (name + ".schema.json")
        if not bundled.is_file():
            raise AssertionError("PACKAGE_MISSING_SCHEMA:" + name)
        if source.resolve() == SKILL.resolve():
            root_schema = ROOT / "schemas" / (name + ".schema.json")
            if bundled.read_bytes() != root_schema.read_bytes():
                raise AssertionError("PACKAGE_SCHEMA_DRIFT:" + name)
        schema = json.loads(bundled.read_text(encoding="utf-8"))
        if schema["$schema"] != "https://json-schema.org/draft/2020-12/schema":
            raise AssertionError("PACKAGE_BAD_SCHEMA:" + name)
    return {
        "name": "slovodel", "description_length": len(desc),
        "markdown_files": len(all_md), "schemas": len(SCHEMA_NAMES),
        "package_sha256": hashlib.sha256(front.encode("utf-8")).hexdigest(),
    }


def run_cli(skill: Path, outside: Path, mode: str, **paths: str) -> dict:
    cmd = [sys.executable, "-I", str(skill / "scripts" / "workflow.py"),
           "--mode", mode]
    for key, value in paths.items():
        cmd.extend(["--" + key.replace("_", "-"), value])
    result = subprocess.run(
        cmd, cwd=outside, capture_output=True, encoding="utf-8",
        check=False, timeout=30, env={**os.environ, "PYTHONPATH": ""},
    )
    wanted_exit = 5 if mode == "rewrite" else 0
    if result.returncode != wanted_exit:
        raise AssertionError("PORTABLE_CLI_FAIL:" + mode + ":exit=" + str(result.returncode)
                             + ":stderr=" + result.stderr[:150])
    data = json.loads(result.stdout)
    if data["mode"] != mode or data["execution"] != "local_core_executed":
        raise AssertionError("PORTABLE_CLI_MODE_MISMATCH:" + mode)
    if data["publication_ready"] is not False:
        raise AssertionError("PORTABLE_CLI_FALSE_APPROVAL:" + mode)
    if mode == "rewrite" and (data["decision"] != "blocked" or
                              data["fact_guard"]["decision"] != "blocked"):
        raise AssertionError("PORTABLE_CLI_GUARD_FAILED")
    if mode == "compare" and data["fact_guard"]["decision"] != "blocked":
        raise AssertionError("PORTABLE_COMPARE_GUARD_FAILED")
    if mode == "audit" and data["pre_analysis"]["mode"] != "audit":
        raise AssertionError("PORTABLE_AUDIT_FAILED")
    if mode == "create" and data["post_analysis"]["mode"] != "audit":
        raise AssertionError("PORTABLE_CREATE_FAILED")
    return {"mode": mode, "exit_code": result.returncode, "decision": data["decision"]}


def install_smoke(source: Path, prefix: Path, kind: str) -> dict:
    location = (prefix / ".agents/skills/slovodel" if kind == "codex"
                else prefix / ".claude/skills/slovodel")
    location.parent.mkdir(parents=True)
    shutil.copytree(source, location)
    check = verify_package(location)
    work = prefix / "outside-skill"
    work.mkdir()
    original = work / "original.txt"
    revised = work / "revised.txt"
    original.write_text("Оплата 50 000 ₽ и 20 часов в неделю.", encoding="utf-8")
    revised.write_text("Оплата 80 000 ₽ и 20 часов в неделю.", encoding="utf-8")
    r = [run_cli(location, work, "audit", input=str(original)),
         run_cli(location, work, "rewrite", before=str(original),
                 after=str(revised)),
         run_cli(location, work, "create", input=str(original)),
         run_cli(location, work, "compare", before=str(original),
                 after=str(revised))]
    # A text-only agent still gets all the prose files when Python is absent.
    if "При отсутствии Python" not in (location / "SKILL.md").read_text(encoding="utf-8"):
        raise AssertionError("TEXT_ONLY_FALLBACK_UNDOCUMENTED")
    return {"installation_layout": kind, "target_suffix": str(location.relative_to(prefix)),
            "metadata": check, "modes": r, "text_only_files_present": True,
            "agent_runtime_invoked": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Write evidence JSON (must not exist)")
    args = parser.parse_args()
    metadata = verify_package(SKILL)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        installations = [
            install_smoke(SKILL, base / "codex-home", "codex"),
            install_smoke(SKILL, base / "claude-home", "claude"),
        ]
    result = {
        "format": "slovodel.portable-install-smoke.v1",
        "source": "checked-out-repository-copy",
        "package": metadata,
        "python": sys.version.split()[0],
        "installations": installations,
        "actual_agent_model_execution": "NOT_RUN",
        "verification_scope": "directory-discovery-layout_and_isolated_python_cli_only",
        "result": "PASS",
    }
    payload = json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2)
    if args.output:
        dest = Path(args.output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("x", encoding="utf-8") as sink:
            sink.write(payload + "\n")
    print("INSTALL_SMOKE: PASS; Codex/Claude directory layout + isolated four-mode Python")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
