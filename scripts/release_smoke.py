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
    "slovodel_core/context.py",
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
    wanted_exit = 5 if mo…8173 tokens truncated… метрики оригинала нужны для плана редактуры; иначе достаточно одного `--mode rewrite`, а отдельный `validate.py` не запускается (A8 уже внутри). Нельзя утверждать, что вызов автоматически направляет AI.

## JSON-вывод

Формат [workflow.schema.json](../schemas/workflow.schema.json) — верхнеуровневый пакет `mode`, `execution`, `ai_text_generation`, `publication_ready=false`, `decision`, `steps_executed`, `pre_analysis`, `post_analysis`, `comparison`, `fact_guard`, `warnings`. Вложенные отчёты принадлежат ранее внедрённым `analysis.schema.json`, `compare.schema.json`, `fact-guard.schema.json`; последовательно проверяй **все четыре** при доступном JSON Schema-валидаторе. Объём метрик может быть большим, поэтому пересказывай только непосредственно значимые для конкретного текста.

`fact_guard` не копирует суммы, имена, ссылки: лишь категории и счётчики. Измеренные метрики содержат агрегаты, версии и предупреждения. Не вставляй в ответ внутренние системные хеши или приватные данные без необходимости.

## Fallback без Python

Когда среда не может запускать скрипты/не получила разрешения:
- Не утверждай, что Core запускался, не придумывай `reproducible`-числа и не изображай JSON-отчёт.
- Выполни вручную **только качественный** `audit`/редактуру/`create`/сопоставление. Для `rewrite` самостоятельно перечисли сохранённые цифры, URL и условия **только как редакторскую сверку**, отметь, что автоматическая A8-проверка не проведена; при юридически значимом/критическом тексте не выдавай неподтверждённую редакцию за безопасную.
- `compare` без исполняемой среды: сравни тон, смысл и исходные факты, но **не вычисляй воображаемые проценты влияния или технические показатели**.
- Если пользователь просил именно вычислительный отчёт, честно укажи, что выполнение недоступно.

## Что НЕ реализовано

Нет автономного AI-генератора, AI-API, подключённого приватного MCP, Notion/Telegram, автоматической публикации, полноценного семантического доказательства сохранения фактов. **E2E-тесты Issue #8 проверяют фактическое исполнение локального Core и структурные статусы**, а не объективное качество созданного AI текста или реальный запуск чужого агента без доступа к его окружению.

## Контекстные добавления в 0.8.2

Для rewrite/compare доступен `--context-file context.json`. Формат и границы —
в [смысловой сверке](semantic-review.md). Составляй записи из исходного брифа
и метаданных до оценки результата, с указателем на источник. Не включай в
подтверждения собственные догадки. `fact_guard` сохраняет исходную диагностику;
`context_review` отдельно объясняет поддержанные добавления и остаточные блокировки.
Даже при снятии workflow-блокировки обязательна редакторская проверка.
