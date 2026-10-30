"""Real Windows launcher regressions: runtime discovery and exit preservation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/slovodel'
POWERSHELL = shutil.which('pwsh') or shutil.which('powershell')


@unittest.skipUnless(os.name == 'nt' and POWERSHELL, 'Windows PowerShell entry point')
class PythonLauncher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'texts with spaces'
        self.home.mkdir()
        self.original = self.home / 'source.txt'
        self.revised = self.home / 'revision.txt'
        self.original.write_text('В 2024 году магазин открыт в Ижевске.', encoding='utf-8')
        self.revised.write_text('В 2025 году магазин открыт в Ижевске.', encoding='utf-8')

    def run_launcher(self, *args, env_extra=None, launcher=None):
        env = os.environ.copy()
        env.pop('SLOVODEL_PYTHON', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env.update(env_extra or {})
        return subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive',
                               '-File', str(launcher or SKILL/'scripts/check_workflow.ps1'),
                               *map(str, args)], cwd=self.home, env=env,
                              capture_output=True, timeout=35)

    def test_automatic_runtime_four_modes(self):
        for mode in ('create', 'audit', 'rewrite', 'compare'):
            with self.subTest(mode=mode):
                out = self.home / mode
                args = ['--input', self.original] if mode in ('create', 'audit') else [
                    '--before', self.original, '--after', self.original]
                p = self.run_launcher('--mode', mode, *args, '--output-dir', out)
                self.assertEqual(p.returncode, 0, p.stderr)
                e = json.loads((out/'execution.json').read_bytes())
                self.assertEqual(e['core_exit_code'], 0)
                self.assertEqual(e['verification'], 'passed')
                self.assertTrue(Path(e['python_executable']).is_file())
                self.assertGreaterEqual(tuple(map(int, e['python_version'].split('.'))), (3, 10))
                self.assertNotIn('WindowsApps', e['python_executable'])

    def test_fact_block_and_length_failure_exit_codes(self):
        p = self.run_launcher('-Python', sys.executable, '--mode', 'rewrite',
            '--before', self.original, '--after', self.revised, '--output-dir', self.home/'blocked')
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertEqual(json.loads((self.home/'blocked/core.json').read_bytes())['decision'], 'blocked')
        p = self.run_launcher('--mode', 'create', '--input', self.original,
            '--max-words', '1', '--output-dir', self.home/'too-long')
        self.assertEqual(p.returncode, 7, p.stderr)

    def test_explicit_invalid_python_does_not_silently_fallback(self):
        out = self.home/'not-run'
        p = self.run_launcher('-Python', self.home/'missing.exe', '--mode', 'audit',
                              '--input', self.original, '--output-dir', out)
        self.assertEqual(p.returncode, 8, p.stderr)
        self.assertFalse(out.exists())
        self.assertIn(b'REQUESTED_PYTHON_UNAVAILABLE', p.stderr)

    def test_environment_override_and_explicit_precedence(self):
        args = ['--mode', 'audit', '--input', self.original, '--output-dir', self.home/'env']
        p = self.run_launcher(*args, env_extra={'SLOVODEL_PYTHON': sys.executable})
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.run_launcher('-Python', sys.executable, '--mode', 'audit',
            '--input', self.original, '--output-dir', self.home/'explicit',
            env_extra={'SLOVODEL_PYTHON': str(self.home/'missing.exe')})
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_windowsapps_alias_is_not_executed(self):
        alias = self.home/'Microsoft/WindowsApps/python.exe'
        alias.parent.mkdir(parents=True)
        alias.write_bytes(b'This is not an executable; it must be skipped.')
        p = self.run_launcher('-Python', alias, '--mode', 'audit',
                              '--input', self.original, '--output-dir', self.home/'alias')
        self.assertEqual(p.returncode, 8, p.stderr)
        self.assertFalse((self.home/'alias').exists())

    def test_copied_skill_with_spaces_is_self_contained(self):
        copied = self.home/'plugin with spaces'/'skills'/'slovodel'
        shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        p = self.run_launcher('--mode', 'audit', '--input', self.original,
            '--output-dir', self.home/'copied-check', launcher=copied/'scripts/check_workflow.ps1')
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_invalid_core_input_code_is_preserved(self):
        p = self.run_launcher('--mode', 'audit', '--input', self.home/'missing.txt',
                              '--output-dir', self.home/'bad-input')
        self.assertEqual(p.returncode, 3, p.stderr)
        e = json.loads((self.home/'bad-input/execution.json').read_bytes())
        self.assertEqual(e['core_exit_code'], 3)
        self.assertEqual(e['verification'], 'not_run')

    def test_unrelated_executable_is_not_accepted_as_python(self):
        out = self.home/'not-python'
        p = self.run_launcher('-Python', POWERSHELL, '--mode', 'audit',
                              '--input', self.original, '--output-dir', out)
        self.assertEqual(p.returncode, 8, p.stderr)
        self.assertFalse(out.exists())

    def test_native_error_preference_does_not_change_core_exit(self):
        wrapper = self.home/'strict-caller.ps1'
        wrapper.write_text("$PSNativeCommandUseErrorActionPreference=$true\n"
            "& $env:SLOVODEL_TEST_LAUNCHER --mode rewrite --before $env:SLOVODEL_TEST_BEFORE "
            "--after $env:SLOVODEL_TEST_AFTER --output-dir $env:SLOVODEL_TEST_OUTPUT\n"
            "exit $LASTEXITCODE\n", encoding='utf-8')
        env = os.environ.copy()
        env.pop('SLOVODEL_PYTHON', None)
        env.update({'SLOVODEL_TEST_LAUNCHER':str(SKILL/'scripts/check_workflow.ps1'),
                    'SLOVODEL_TEST_BEFORE':str(self.original),
                    'SLOVODEL_TEST_AFTER':str(self.revised),
                    'SLOVODEL_TEST_OUTPUT':str(self.home/'native-error')})
        p = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(wrapper)],
                            env=env, capture_output=True, timeout=35)
        self.assertEqual(p.returncode, 5, p.stderr)


if __name__ == '__main__':
    unittest.main()
