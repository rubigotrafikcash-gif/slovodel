"""Observed fresh-text failure classes, with synthetic non-copyright fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/slovodel'
sys.path.insert(0,str(SKILL))
from slovodel_core.fact_guard import check
from slovodel_core.workflow import build
from slovodel_core.checked_workflow import word_count,main as checked_main
from slovodel_core.verification import VerificationError


class FormattingRegressions(unittest.TestCase):
    def test_ranges_and_rate_abbreviations(self):
        for left,right in [('Участники 12—17 лет.','Участники 12–17 лет.'),
                           ('Сон менее 6 ч/сут.','Сон менее 6 часов в сутки.')]:
            with self.subTest(left=left):
                self.assertNotEqual(check(left,right)['decision'],'blocked')

    def test_values_units_and_rate_boundaries_still_block(self):
        for right in ('Сон менее 8 часов в сутки.','Сон менее 6 часов в неделю.',
                      'Сон более 6 часов в сутки.'):
            r=check('Сон менее 6 ч/сут.',right)
            self.assertEqual(r['decision'],'blocked')
        self.assertEqual(check('Возраст 12—17 лет.','Возраст 12–19 лет.')['decision'],'blocked')

    def test_literal_and_identifiers_not_normalized(self):
        a='Сон 6 ч/сут. Код X12-17. https://example.org/12-17'
        b='Сон 6 часов в сутки. Код X12-17. https://example.org/12-17'
        self.assertNotEqual(check(a,b)['decision'],'blocked')
        self.assertEqual(check(a,b,('6 ч/сут',))['decision'],'blocked')
        self.assertEqual(check(a,b.replace('X12-17','X12-19'))['decision'],'blocked')
        self.assertEqual(check(a,b.replace('/12-17','/12-19'))['decision'],'blocked')

    def test_section_labels_not_names_but_substantive_headings_protected(self):
        self.assertNotEqual(check('МАТЕРИАЛЫ И МЕТОДЫ\nВ группе 37 участников.\nРЕЗУЛЬТАТЫ\nСон оценён.',
                                  'В группе 37 участников. Сон оценён.')['decision'],'blocked')
        for source in ('РЕЗУЛЬТАТЫ 37\nСон оценён.','ПРИБОР МЕДИК\nСон оценён.'):
            self.assertEqual(check(source,'Сон оценён.')['decision'],'blocked')

    def test_citation_provenance_cannot_excuse_changed_value(self):
        def run(a,b):
            ctx=json.dumps([{'text':'Источник — энциклопедическая статья.',
                             'source':'https://ru.wikipedia.org/wiki/Test'}]).encode()
            return build('rewrite',before_doc=(a.encode(),a),after_doc=(b.encode(),b),
                         context_doc=(ctx,ctx.decode()))
        self.assertEqual(run('Длина 730 м[2].','Длина 730 м.')['decision'],'draft_requires_review')
        self.assertEqual(run('Длина 730 м[2].','Длина 731 м.')['decision'],'blocked')


class CheckedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.original=self.file('before.txt','Стоимость 120 рублей.')
        self.after=self.file('after.txt','Стоимость 180 рублей.')
    def file(self,name,text):
        p=self.home/name;p.write_text(text,encoding='utf-8');return p
    def run_check(self,mode,*args,out='check'):
        argv=['check_workflow.py','--mode',mode,'--output-dir',str(self.home/out),*map(str,args)]
        stdout,stderr=StringIO(),StringIO()
        with patch.object(sys,'argv',argv),redirect_stdout(stdout),redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as stopped:checked_main()
        return SimpleNamespace(returncode=stopped.exception.code,stdout=stdout.getvalue(),stderr=stderr.getvalue())
    def load(self,name,out='check'):return json.loads((self.home/out/name).read_text(encoding='utf-8'))

    def test_real_block_exit_hashes_and_no_overwrite(self):
        before=self.original.read_bytes()
        r=self.run_check('rewrite','--before',self.original,'--after',self.after)
        self.assertEqual(r.returncode,5,r.stderr)
        self.assertEqual(self.load('execution.json')['core_exit_code'],5)
        self.assertEqual(self.load('execution.json')['runner_exit_code'],5)
        self.assertEqual(self.load('verification.json')['input_hashes']['before'],hashlib.sha256(before).hexdigest())
        self.assertFalse(self.load('core.json')['publication_ready'])
        old=(self.home/'check/core.json').read_bytes()
        self.assertEqual(self.run_check('rewrite','--before',self.original,'--after',self.after).returncode,4)
        self.assertEqual(old,(self.home/'check/core.json').read_bytes())
        self.assertEqual(before,self.original.read_bytes())

    def test_word_limits_fail_then_new_final_draft_passes(self):
        draft=self.file('draft.txt','Модель с металлическим корпусом.')
        r=self.run_check('create','--input',draft,'--min-words',5,'--max-words',8)
        self.assertEqual(r.returncode,7,r.stderr)
        self.assertEqual(self.load('execution.json')['core_exit_code'],0)
        self.assertEqual(self.load('execution.json')['word_limits']['status'],'failed')
        final=self.file('final.txt','Эта модель с металлическим корпусом.')
        r=self.run_check('create','--input',final,'--min-words',5,'--max-words',8,out='final')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.load('execution.json','final')['word_limits']['count'],5)

    def test_audit_compare_answer_limits(self):
        answer=self.file('answer.txt','Первый вариант точнее второго.')
        for mode,args in [('audit',['--input',self.original]),('compare',['--before',self.original,'--after',self.after])]:
            r=self.run_check(mode,*args,'--answer',answer,'--max-words',6,out=mode)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(self.load('execution.json',mode)['word_limits']['count'],4)

    def test_missing_input_records_failure_not_fake_verification(self):
        r=self.run_check('audit','--input',self.home/'missing.txt')
        self.assertEqual(r.returncode,3)
        meta=self.load('execution.json')
        self.assertEqual(meta['core_exit_code'],3)
        self.assertEqual(meta['verification'],'not_run')
        self.assertFalse((self.home/'check/verification.json').exists())

    def test_answer_required_for_audit_limits_and_invalid_bounds(self):
        self.assertEqual(self.run_check('audit','--input',self.original,'--max-words',5).returncode,2)
        self.assertEqual(self.run_check('create','--input',self.after,'--min-words',8,'--max-words',5).returncode,2)
        self.assertEqual(word_count('Объём — 2 л.\n- Без подсветки.'),5)

    def test_verifier_failure_cannot_be_success(self):
        with patch('slovodel_core.checked_workflow.verify',side_effect=VerificationError('VERIFY_HASH_MISMATCH')):
            r=self.run_check('audit','--input',self.original)
        self.assertEqual(r.returncode,6)
        self.assertEqual(self.load('execution.json')['core_exit_code'],0)
        self.assertEqual(self.load('execution.json')['verification'],'not_run')
        self.assertFalse((self.home/'check/verification.json').exists())

    def test_packaged_entrypoint_runs_from_another_directory(self):
        r=subprocess.run([sys.executable,str(SKILL/'scripts/check_workflow.py'),'--mode','audit',
                          '--input',str(self.original),'--output-dir',str(self.home/'entry')],
                         cwd=self.home,capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.load('execution.json','entry')['verification'],'passed')

if __name__=='__main__':unittest.main()
