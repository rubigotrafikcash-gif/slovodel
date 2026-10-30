"""Exercise the documented direct fallback in Windows PowerShell, without PS1."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT/'skills/slovodel'
SHELL = shutil.which('powershell')


@unittest.skipUnless(os.name == 'nt' and SHELL, 'Windows direct fallback')
class DirectPythonFallback(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.before = self.home/'before.txt'
        self.after = self.home/'after.txt'
        self.before.write_text('В 2024 году открыт магазин в Ижевске.', encoding='utf-8')
        self.after.write_text('В 2025 году открыт магазин в Ижевске.', encoding='utf-8')
        self.block = re.search(r'```powershell\n(.*?)\n```',
            (SKILL/'references/python-fallback.md').read_text(encoding='utf-8'), re.S).group(1)

    def run_fallback(self, mode, folder, changed=False, invalid=False, force_default=False):
        env = os.environ.copy()
        env.pop('SLOVODEL_PYTHON', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env.update({'SLOVODEL_TEST_ENTRY':str(SKILL/'scripts/check_workflow.py'),
                    'SLOVODEL_TEST_BEFORE':str(self.before),
                    'SLOVODEL_TEST_AFTER':str(self.after if changed else self.before),
                    'SLOVODEL_TEST_OUTPUT':str(self.home/folder),
                    'SLOVODEL_TEST_MODE':mode})
        if invalid:
            env['SLOVODEL_PYTHON'] = str(self.home/'not-installed.exe')
        elif not force_default and not (Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe').is_file():
            # Generic GitHub runners have Python but no OpenAI runtime bundle.
            env['SLOVODEL_PYTHON'] = sys.executable
        args = ('--input $env:SLOVODEL_TEST_BEFORE' if mode in ('create', 'audit') else
                '--before $env:SLOVODEL_TEST_BEFORE --after $env:SLOVODEL_TEST_AFTER')
        command = "$ErrorActionPreference='Stop'\n" + self.block + '\n' + (
            '& $runtimePython -B $env:SLOVODEL_TEST_ENTRY --mode $env:SLOVODEL_TEST_MODE '
            + args + ' --output-dir $env:SLOVODEL_TEST_OUTPUT\nexit $LASTEXITCODE\n')
        return subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-Command', command],
                              env=env, capture_output=True, timeout=30)

    def test_all_modes_without_loading_ps1(self):
        for mode in ('create', 'rewrite', 'audit', 'compare'):
            with self.subTest(mode=mode):
                p = self.run_fallback(mode, mode)
                self.assertEqual(p.returncode, 0, p.stderr)
                e = json.loads((self.home/mode/'execution.json').read_bytes())
                self.assertEqual(e['verification'], 'passed')
                self.assertEqual(e['core_exit_code'], 0)
                self.assertNotIn('WindowsApps', e['python_executable'])

    def test_default_runtime_without_any_override(self):
        if not (Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe').is_file():
            self.skipTest('Host does not have the optional OpenAI runtime bundle')
        p = self.run_fallback('audit', 'automatic', force_default=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_factual_block_exit_is_not_hidden(self):
        p = self.run_fallback('rewrite', 'blocked', changed=True)
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertEqual(json.loads((self.home/'blocked/core.json').read_bytes())['decision'], 'blocked')

    def test_missing_explicit_interpreter_cannot_produce_core_report(self):
        p = self.run_fallback('audit', 'invalid', invalid=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.home/'invalid').exists())


if __name__ == '__main__':
    unittest.main()
