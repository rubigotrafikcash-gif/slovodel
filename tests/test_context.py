import hashlib
import json
import unittest
from slovodel_core.workflow import build


def doc(text):
    return text.encode('utf-8'), text


def context(text):
    return doc(json.dumps([{'text': text, 'source': 'user brief'}], ensure_ascii=False))


class ContextReviewTests(unittest.TestCase):
    def run_edit(self, before, after, ctx, **kw):
        return build('rewrite', before_doc=doc(before), after_doc=doc(after),
                     context_doc=context(ctx), **kw)

    def test_added_date_is_review_with_raw_block_and_original_hash(self):
        before='Школа открылась.'
        report=self.run_edit(before,'Школа открылась 21 марта 2025 года.',
                             'Дата: 21 марта 2025 года.')
        self.assertEqual(report['decision'],'draft_requires_review')
        self.assertEqual(report['fact_guard']['decision'],'blocked')
        self.assertEqual(report['fact_guard']['source_sha256'],hashlib.sha256(before.encode()).hexdigest())
        self.assertEqual(report['context_review']['supported_addition_kinds'],['date'])
        self.assertFalse(report['publication_ready'])

    def test_wrong_date_is_not_supported(self):
        self.assertEqual(self.run_edit('Школа открылась.','Школа открылась 22 марта 2025 года.',
                                      '21 марта 2025 года')['decision'],'blocked')

    def test_context_cannot_excuse_replaced_amount(self):
        self.assertEqual(self.run_edit('Цена 100 рублей.','Цена 200 рублей.',
                                      'Цена 200 рублей.')['decision'],'blocked')

    def test_context_cannot_excuse_removed_negation(self):
        self.assertEqual(self.run_edit('Услуга не доступна.','Услуга доступна.',
                                      'Услуга доступна.')['decision'],'blocked')

    def test_context_cannot_excuse_literal_protected_term(self):
        self.assertEqual(self.run_edit('Модель Альфа.','Модель Бета.',
                                      'Модель Бета.',protected_terms=('альфа',))['decision'],'blocked')

    def test_supplied_names_are_review_not_publication(self):
        r=self.run_edit('Шкала надёжна.','Шкала ATAS надёжна.','Русскоязычная ATAS.')
        self.assertEqual(r['decision'],'draft_requires_review')
        self.assertEqual(r['context_review']['supported_addition_kinds'],['proper_name'])
        self.assertNotIn('ATAS',json.dumps(r['context_review']))

    def test_unprovided_name_remains_blocked(self):
        self.assertEqual(self.run_edit('Шкала надёжна.','Шкала ATAS надёжна.',
                                      'Другие сведения.')['decision'],'blocked')

    def test_no_names_joined_across_records(self):
        ctx=doc(json.dumps([{'text':'Иван','source':'brief'}, {'text':'Петров','source':'brief'}]))
        r=build('rewrite',before_doc=doc('Ведущий выступил.'),after_doc=doc('Иван Петров выступил.'),context_doc=ctx)
        self.assertEqual(r['decision'],'blocked')

    def test_context_rejected_for_audit_and_invalid_records(self):
        with self.assertRaises(ValueError): build('audit',input_doc=doc('Текст.'),context_doc=context('Дата.'))
        for bad in ('null','[]','{}','[{"text":"Дата"}]','[{"text":5,"source":"brief"}]'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                build('rewrite',before_doc=doc('Текст.'),after_doc=doc('Текст.'),context_doc=doc(bad))

    def test_compare_retains_comparison_only(self):
        r=build('compare',before_doc=doc('Школа открылась.'),after_doc=doc('Школа открылась 21 марта 2025 года.'),context_doc=context('21 марта 2025 года'))
        self.assertEqual(r['decision'],'comparison_only')

    def test_cli_context_schema_and_error(self):
        import subprocess,sys,tempfile
        from pathlib import Path
        try:
            import jsonschema
        except ImportError:
            jsonschema = None  # CI repeats the suite after installing this extra.
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name,text in [('before','Школа открылась.'),('after','Школа открылась 21 марта 2025 года.'),('context',context('21 марта 2025 года')[1])]:
                (p/name).write_text(text,encoding='utf-8')
            cmd=[sys.executable,str(root/'skills/slovodel/scripts/workflow.py'),'--mode','rewrite','--before',str(p/'before'),'--after',str(p/'after'),'--context-file',str(p/'context')]
            r=subprocess.run(cmd,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)
            if jsonschema is not None:
                jsonschema.validate(json.loads(r.stdout),json.loads((root/'schemas/workflow.schema.json').read_text(encoding='utf-8')))
            (p/'context').write_text('null',encoding='utf-8')
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,3)
