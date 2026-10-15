#!/usr/bin/env python3
"""Synthetic offline smoke test; deny ordinary Python socket entry points.

Not an OS network sandbox: CI also statically scans application imports.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
import json
import socket
import sys
import tempfile
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/slovodel"))
from slovodel_core.workflow import build
from slovodel_core.fact_guard import check


def document(text: str) -> tuple[bytes, str]:
    return text.encode("utf-8"), text


def blocked(*args, **kwargs):
    raise AssertionError("NETWORK_CALL_ATTEMPTED")


def main() -> None:
    original = document("Срок 5 дней, оплата 50 000 ₽.")
    revised = document("Срок 7 дней, оплата 80 000 ₽.")
    with contextlib.ExitStack() as patches:
        patches.enter_context(patch.object(socket.socket, "connect", blocked))
        patches.enter_context(patch.object(socket.socket, "connect_ex", blocked))
        patches.enter_context(patch.object(socket, "create_connection", blocked))
        patches.enter_context(patch.object(socket, "getaddrinfo", blocked))
        patches.enter_context(patch.object(urllib.request, "urlopen", blocked))
        for mode in ("audit", "rewrite", "create", "compare"):
            options = ({"input_doc": original} if mode in ("audit", "create") else
                       {"before_doc": original, "after_doc": revised})
            data = build(mode, **options)
            assert data["execution"] == "local_core_executed"
            assert data["publication_ready"] is False
            assert data["ai_text_generation"] == "external_to_this_workflow"
            assert "historical_suggestive_score" not in json.dumps(
                data.get("comparison") or {}
            )
            if mode == "rewrite":
                assert data["decision"] == "blocked"
                assert data["fact_guard"]["publish_ready"] is False
            if mode == "compare":
                assert data["fact_guard"]["decision"] == "blocked"
            if mode == "audit":
                assert data["comparison"] is None
            if mode == "create":
                assert data["pre_analysis"] is None
        assert check(original[1], revised[1])["decision"] == "blocked"
    print("OFFLINE_SMOKE: 4 modes + guard PASS (network entry points denied)")


if __name__ == "__main__":
    main()
