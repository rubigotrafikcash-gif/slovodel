"""Replay runs diagnostics in the right mode and rejects corrupt inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.evidence = self.home/'evidence'
        for kind in ('cases', 'outputs'):
            (self.evidence/'eval'/kind).mkdir(parents=True)
        for case_id, mode in (('T01', 'audit'), ('T02', 'spoken')):
            fragment = 'Срок — три дня.'
            digest = hashlib.sha256(fragment.encode()).hexdigest()
            (self.evidence/'eval/cases'/f'{case_id}.json').write_text(json.dumps(dict(
                case_id=case_id, mode=mode, fragment=fragment, input_sha256=digest)),encoding='utf-8')
            for branch in ('A','B'):
                (self.evidence/'eval/outputs'/f'{case_id}_{branch}.json').write_text(json.dumps(dict(
                    case_id=case_id, branch=branch, input_sha256=digest,
                    final_response='Замечаний нет.' if mode=='audit' else 'Срок — 3 дня.')),encoding='utf-8')

    def run_replay(self):
        return subprocess.run([sys.executable,str(ROOT/'scripts/replay_audit.py'),
            '--evidence',str(self.evidence),'--output',str(self.home/'result')],capture_output=True)

    def test_actual_cli_modes_hashes_and_logs(self):
        run = self.run_replay()
        self.assertEqual(run.returncode,0,run.stderr)
        manifest=json.loads((self.home/'result/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['records'],4)
        for rec in manifest['runs']:
            self.assertIsNone(rec['platform_model'])
            self.assertEqual(rec['editorial_fact_verdict'],'not_assessed_by_replay')
            report=json.loads((self.home/'result'/rec['case']/'stdout.json').read_text(encoding='utf-8'))
            if rec['task_mode']=='audit':
                self.assertIsNone(report['fact_guard'])
                self.assertEqual(rec['decision'],'audit_only')
            else:
                self.assertEqual(rec['mode'],'rewrite')
                self.assertEqual(report['fact_guard']['revision_sha256'],rec['response_sha256'])
        self.assertNotEqual(self.run_replay().returncode,0)  # never overwrite evidence

    def test_tampered_input_fails_before_writing_results(self):
        path=self.evidence/'eval/cases/T02.json'
        card=json.loads(path.read_text(encoding='utf-8'))
        card['fragment']='Срок — пять дней.'
        path.write_text(json.dumps(card),encoding='utf-8')
        run=self.run_replay()
        self.assertNotEqual(run.returncode,0)
        self.assertIn(b'Input hash mismatch',run.stderr)
        self.assertFalse((self.home/'result').exists())

    def test_path_like_case_id_is_rejected(self):
        path=self.evidence/'eval/outputs/T01_A.json'
        rec=json.loads(path.read_text(encoding='utf-8'))
        rec['case_id']='../T01'
        path.write_text(json.dumps(rec),encoding='utf-8')
        self.assertNotEqual(self.run_replay().returncode,0)
        self.assertFalse((self.home/'result').exists())


if __name__ == '__main__':
    unittest.main()
