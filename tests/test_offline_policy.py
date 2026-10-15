"""Offline behavior + static inspection. No claim of OS-level sandbox."""
import ast
import json
from pathlib import Path
import socket
import sys
import unittest
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/slovodel"))

from slovodel_core.workflow import build


def blocked(*args, **kwargs):
    raise AssertionError("NETWORK_CALL_ATTEMPTED")


def doc(text):
    return text.encode("utf-8"), text


class OfflinePolicyTests(unittest.TestCase):
    def test_modes_run_with_socket_and_urlopen_disabled(self):
        with (patch.object(socket.socket, "connect", blocked),
              patch.object(socket.socket, "connect_ex", blocked),
              patch.object(socket, "getaddrinfo", blocked),
              patch.object(socket, "create_connection", blocked),
              patch.object(urllib.request, "urlopen", blocked)):
            for mode in ("audit","create","rewrite","compare"):
                kwargs = ({"input_doc":doc("Текст.")}
                          if mode in ("audit","create") else {
                              "before_doc":doc("Цена 10 ₽"),
                              "after_doc":doc("Цена 20 ₽"),
                          })
                with self.subTest(mode=mode):
                    report=build(mode,**kwargs)
                    self.assertEqual(report["execution"],"local_core_executed")
                    self.assertFalse(report["publication_ready"])
                    if mode=="rewrite":
                        self.assertEqual(report["decision"],"blocked")

    def test_no_direct_network_imports_in_core_or_cli(self):
        forbidden = {"requests","urllib","socket","aiohttp","http",
                     "ftplib","smtplib","httpx","grpc","websockets"}
        for folder in ("skills/slovodel/slovodel_core",
                       "skills/slovodel/scripts"):
            for file in (ROOT/folder).glob("*.py"):
                with self.subTest(file=file.name):
                    syntax=ast.parse(file.read_text(encoding="utf-8"))
                    for node in ast.walk(syntax):
                        if isinstance(node,ast.Import):
                            modules=[n.name for n in node.names]
                        elif isinstance(node,ast.ImportFrom):
                            modules=[node.module or ""]
                        else:
                            continue
                        self.assertFalse(forbidden & {
                            n.split(".")[0] for n in modules
                        })


if __name__=="__main__":
    unittest.main()
