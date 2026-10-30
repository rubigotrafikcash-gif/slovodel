"""Predicate-local modality regressions and shared evidence-verifier acceptance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT/'skills/slovodel'
sys.path.insert(0, str(SKILL))
from slovodel_core.fact_guard import check
from slovodel_core.verification import verify, VerificationError
from slovodel_core.workflow import build


class ModalityRegressions(unittest.TestCase):
    def test_historical_possibility_and_unrelated_instruction(self):
        before = 'Вторую смену могут открыть, если будет финансирование. Запись производится через сообщения сообщества.'
        after = 'Вторую смену могли открыть, если будет финансирование. Для записи нужно написать в сообщения сообщества.'
        result = check(before, after)
        self.assertNotEqual(result['decision'], 'blocked', result['findings'])
        self.assertNotIn('modality', {f['kind'] for f in result['findings']})

    def test_present_and_past_possibility_removal_block(self):
        for modal in ('могут', 'могли', 'могла бы'):
            with self.subTest(modal=modal):
                result = check(f'Команда {modal} открыть смену.', 'Команда открыли смену.')
                self.assertTrue(any(f['kind']=='modality' and f['severity']=='blocker'
                                    for f in result['findings']), result)

    def test_same_predicate_may_must_flips_and_reverse(self):
        pairs = [
            ('Клиент может отменить заказ.', 'Клиент должен отменить заказ.'),
            ('Пользователь мог потребовать удаления.', 'Пользователь обязан потребовать удаления.'),
        ]
        for a,b in pairs:
            for before,after in ((a,b),(b,a)):
                with self.subTest(before=before):
                    self.assertTrue(any(f['kind']=='modality' and f['severity']=='blocker'
                                        for f in check(before,after)['findings']))

    def test_equal_global_counts_do_not_hide_swapped_actions(self):
        result=check('Клиент может отменить заказ. Клиент должен оплатить заказ.',
                     'Клиент должен отменить заказ. Клиент может оплатить заказ.')
        self.assertIn('modality',{f['kind'] for f in result['findings']})

    def test_equal_global_counts_do_not_hide_swapped_objects(self):
        result=check('Можно открыть магазин. Нужно открыть склад.',
                     'Нужно открыть магазин. Можно открыть склад.')
        self.assertTrue(any(f['kind']=='modality' and f['severity']=='blocker'
                            for f in result['findings']))

    def test_historical_forms_and_clause_reordering(self):
        a='Команда может открыть смену. Для записи нужно написать сообщение.'
        b='Для записи нужно было написать сообщение. Команда могла открыть смену.'
        self.assertNotIn('modality',{f['kind'] for f in check(a,b)['findings']})

    def test_uncertain_nominal_paraphrase_is_review_not_approval(self):
        result=check('Команда могла открыть смену.', 'Рассматривалась возможность открытия смены.')
        finding=next(f for f in result['findings'] if f['kind']=='modality')
        self.assertEqual(finding['severity'],'review')
        self.assertFalse(result['publish_ready'])

    def test_unchanged_unknown_action_does_not_invent_finding(self):
        a='Доставка разрешается. Есть описание.'
        b='Доставка разрешается. Описание уточнено.'
        self.assertNotIn('modality',{f['kind'] for f in check(a,b)['findings']})

    def test_modal_words_in_links_do_not_create_claims(self):
        self.assertNotIn('modality',{f['kind'] for f in check(
            'См. https://example.org/могли/открыть.', 'См. https://example.org/открыли.')['findings']})

    def test_large_ambiguous_alignment_is_bounded_review(self):
        a='Команда могла открыть смену.'
        b=' '.join('Команда открыли смену.' for _ in range(100))
        f=next(f for f in check(a,b)['findings'] if f['kind']=='modality')
        self.assertEqual(f['severity'],'review')


class SharedVerifierTests(unittest.TestCase):
    def document(self, text):
        return text.encode('utf-8'),text

    def verify_report(self, report, docs, **kwargs):
        return verify(report, docs, core_exit_code=5 if report['decision']=='blocked' else 0,
                      schema_dir=SKILL/'schemas', **kwargs)

    def test_all_four_modes_and_matching_hashes(self):
        first=self.document('Оплата от 48 000 рублей в месяц.')
        second=self.document('Оплата до 48 000 рублей в месяц.')
        for mode in ('create','audit','rewrite','compare'):
            with self.subTest(mode=mode):
                single=mode in ('create','audit')
                r=build(mode, input_doc=first) if single else build(mode,before_doc=first,after_doc=second)
                docs={'input':first[0]} if single else {'before':first[0],'after':second[0]}
                v=self.verify_report(r,docs)
                self.assertEqual(v['structural_checks'],'passed')
                self.assertFalse(v['publication_ready'])
                self.assertEqual(v['semantic_review'],'not_performed_by_verifier')

    def test_mismatching_source_and_nested_hashes_rejected(self):
        doc=self.document('Текст для проверки.')
        r=build('audit',input_doc=doc)
        with self.assertRaisesRegex(VerificationError,'VERIFY_HASH_MISMATCH'):
            self.verify_report(r,{'input':b'changed'})
        for field in ('pre_analysis','comparison','fact_guard'):
            r=build('rewrite',before_doc=doc,after_doc=doc)
            if field=='pre_analysis':r[field]['source_sha256']='0'*64
            elif field=='comparison':r[field]['before']['sha256']='0'*64
            else:r[field]['source_sha256']='0'*64
            with self.subTest(field=field), self.assertRaisesRegex(VerificationError,'VERIFY_HASH_MISMATCH'):
                self.verify_report(r,{'before':doc[0],'after':doc[0]})

    def test_blocked_core_exit_is_verified_not_approved(self):
        a=self.document('Цена 100 рублей.');b=self.document('Цена 200 рублей.')
        r=build('rewrite',before_doc=a,after_doc=b)
        self.assertEqual(r['decision'],'blocked')
        v=self.verify_report(r,{'before':a[0],'after':b[0]})
        self.assertEqual(v['core_exit_code'],5)
        with self.assertRaisesRegex(VerificationError,'VERIFY_EXIT_CODE_MISMATCH'):
            verify(r,{'before':a[0],'after':b[0]},core_exit_code=0,schema_dir=SKILL/'schemas')

    def test_schema_missing_is_explicit_and_require_schema_fails(self):
        doc=self.document('Текст.');r=build('audit',input_doc=doc)
        with patch.dict(sys.modules,{'jsonschema':None}):
            v=self.verify_report(r,{'input':doc[0]})
            self.assertEqual(v['schema_validation'],'unavailable')
            with self.assertRaisesRegex(VerificationError,'VERIFY_SCHEMA_UNAVAILABLE'):
                self.verify_report(r,{'input':doc[0]},require_schema=True)

    def test_invented_publication_approval_rejected(self):
        doc=self.document('Текст.');r=build('audit',input_doc=doc)
        r['publication_ready']=True
        with self.assertRaises(VerificationError):self.verify_report(r,{'input':doc[0]})

    def test_context_requires_matching_context_file(self):
        doc=self.document('Текст.');ctx=self.document('[{"text":"Ижевск", "source":"бриф"}]')
        r=build('rewrite',before_doc=doc,after_doc=doc,context_doc=ctx)
        with self.assertRaisesRegex(VerificationError,'VERIFY_CONTEXT_REQUIRED'):
            self.verify_report(r,{'before':doc[0],'after':doc[0]})
        v=self.verify_report(r,{'before':doc[0],'after':doc[0],'context':ctx[0]})
        self.assertEqual(v['input_hashes']['context'],hashlib.sha256(ctx[0]).hexdigest())

    def test_cli_no_overwrite_and_sanitized_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'source.txt';report=p/'report.json';out=p/'verified.json'
            source.write_bytes(b'Text.');r=build('audit',input_doc=(b'Text.','Text.'))
            report.write_text(json.dumps(r),encoding='utf-8')
            cmd=[sys.executable,str(SKILL/'scripts/verify_workflow.py'),'--report',str(report),
                 '--input',str(source),'--core-exit-code','0','--output',str(out)]
            run=subprocess.run(cmd,capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr)
            run=subprocess.run(cmd,capture_output=True)
            self.assertEqual(run.returncode,6)
            self.assertNotIn(str(p).encode(),run.stderr)
            self.assertIn(b'OUTPUT_WRITE_FAILED',run.stderr)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.json';p.write_text('{"secret":"PRIVATE", "secret":1}',encoding='utf-8')
            run=subprocess.run([sys.executable,str(SKILL/'scripts/verify_workflow.py'),
                                '--report',str(p),'--core-exit-code','0'],capture_output=True)
            self.assertEqual(run.returncode,6)
            self.assertNotIn(b'PRIVATE',run.stderr)


if __name__=='__main__':unittest.main()
