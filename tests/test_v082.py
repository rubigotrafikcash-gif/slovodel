"""Synthetic regression controls inspired by the private 106-case audit.

These are not original source excerpts or a new model A/B benchmark.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/slovodel'))
from slovodel_core.fact_guard import check, _comparison_glyphs


class ComparisonNormalizationTests(unittest.TestCase):
    def test_harmless_mixed_repairs_both_directions(self):
        pairs = [
            ('Мы pассмaтривaем заявки без oпытa.', 'Мы рассматриваем заявки без опыта.'),
            ('Пoмoгaем через Аvitо.', 'Помогаем через Авито.'),
            ('В центре «Pocпeчaть» площадь 42,5 кв.м.', 'В центре «Роспечать» площадь 42,5 м².'),
            ('В здании "CОМИЗ", пeрвая линия.', 'В здании «СОМИЗ», на первой линии.'),
        ]
        for a, b in pairs:
            for before, after in ((a,b),(b,a)):
                with self.subTest(before=before):
                    r = check(before, after)
                    self.assertNotEqual(r['decision'], 'blocked', r['findings'])
                    self.assertFalse(r['publish_ready'])
                    self.assertEqual(r['semantic_equivalence'], 'not_verified')
                    self.assertIn('COMPARISON_GLYPHS_NORMALIZED_REVIEW_ORIGINALS', r['warnings'])

    def test_offsets_refer_to_original_and_do_not_expose_values(self):
        before = '😀 Мы pассмaтривaем заявки.'
        r = check(before, '😀 Мы рассматриваем заявки.')
        item = r['comparison_normalization']['before'][0]
        self.assertEqual(before[item['start']:item['end']], 'pассмaтривaем')
        self.assertEqual(set(item), {'start','end','kind'})

    def test_pure_names_ambiguous_and_codes_stay_untouched(self):
        for text in ('PAY РАУ', 'CОC', 'Модель АB12', 'ООО ABC'):
            self.assertEqual(_comparison_glyphs(text, '')[0], text)

    def test_protected_urls_emails_and_terms_still_block(self):
        pairs = [
            ('https://example.org/Аvitо', 'https://example.org/Авито'),
            ('pассмaтривaем@example.org', 'рассматриваем@example.org'),
            ('Код АB12', 'Код AB12'),
        ]
        for a,b in pairs:
            self.assertEqual(check(a,b)['decision'], 'blocked')
        self.assertEqual(check('Бренд Аvitо', 'Бренд Авито', ('аvitо',))['decision'], 'blocked')

    def test_changed_name_and_quantity_still_block(self):
        for a,b in [
            ('В здании «CОМИЗ».', 'В здании «СОМИС».'),
            ('Пoмoгaем через Аvitо.', 'Помогаем через Ozon.'),
            ('Плoщадь 42,5 кв.м.', 'Площадь 43,5 м².'),
            ('Высота 4 м.', 'Высота 4 см.'),
            ('Площадь 42 м².', 'Площадь 42 м.'),
            ('Бренд PAY.', 'Бренд РАУ.'),
        ]:
            with self.subTest(a=a,b=b):
                self.assertEqual(check(a,b)['decision'], 'blocked')

    def test_unit_forms_and_bindings(self):
        for a,b in [('Площадь 42 кв. м;', 'Площадь 42 м²;'),
                    ('Высота 4 метра.', 'Высота 4 м.'),
                    ('Объём 2 литра.', 'Объём 2 л.')]:
            self.assertNotEqual(check(a,b)['decision'], 'blocked')
        r=check('Офис 42 м²; склад 80 м².', 'Офис 80 м²; склад 42 м².')
        self.assertIn('binding', {f['kind'] for f in r['findings']})

    def test_unchanged_mixed_text_remains_unchanged(self):
        self.assertEqual(check('Пoмoгaем через Аvitо.', 'Пoмoгaем через Аvitо.')['decision'], 'unchanged')

    def test_two_line_product_characteristics(self):
        for a,b in [('Объем, мл\n    450\n\nКоличество предметов\n    2', 'Объём: 450 мл. Количество предметов: 2.'),
                    ('Объем, л\n    1.8', 'Объём 1.8 л.'),
                    ('Площадь, кв. м\n  45,5', 'Площадь 45,5 м².')]:
            for before,after in ((a,b),(b,a)):
                self.assertNotEqual(check(before,after)['decision'],'blocked')

    def test_table_measurement_mutations_stay_blocked(self):
        for after in ('Объём 450 л.', 'Объём 460 мл.'):
            self.assertEqual(check('Объем, мл\n  450',after)['decision'],'blocked')


class SemanticCueTests(unittest.TestCase):
    def test_review_cues(self):
        for before,after,kind in [
            ('Тогда открыли парк.', 'Сейчас открыли парк.', 'temporal_context'),
            ('Вероятно, покупатели ждут скидок.', 'Покупатели ждут скидок.', 'epistemic_context'),
            ('Покупатели выбирают доставку.', 'По данным исследования, покупатели выбирают доставку.', 'attribution'),
            ('Автор считает: покупатели выбирают доставку.', 'Покупатели выбирают доставку.', 'attribution'),
        ]:
            r=check(before,after)
            self.assertIn(kind, {f['kind'] for f in r['findings']})
            self.assertTrue(all(f['severity']=='review' for f in r['findings'] if f['kind']==kind))

    def test_same_relative_time_still_needs_context_review(self):
        r=check('Сейчас учатся 500 детей.', 'Сейчас в школе учатся 500 детей.')
        self.assertIn('TEMPORAL_CONTEXT_REQUIRES_SOURCE_DATE_REVIEW', r['warnings'])
        self.assertEqual(r['semantic_equivalence'], 'not_verified')

    def test_urls_do_not_generate_semantic_cues(self):
        r=check('https://example.org/сейчас', 'https://example.org/тогда')
        self.assertNotIn('temporal_context', {f['kind'] for f in r['findings']})

    def test_required_identifier_is_explicit(self):
        r=check('Русскоязычная версия QRS: порог 0,7.', 'Порог 0,7.', ('русскоязычная версия', 'qrs'))
        self.assertEqual(r['decision'], 'blocked')
        self.assertIn('protected_term', {f['kind'] for f in r['findings']})


if __name__ == '__main__':
    unittest.main()
