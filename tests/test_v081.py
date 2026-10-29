"""v0.8.1: synthetic fact-preservation regressions from the SMM audit."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/slovodel'))
from slovodel_core.fact_guard import check  # noqa: E402


class CommercialFactTests(unittest.TestCase):
    def assertBlocked(self, before, after, category='commercial_term'):
        for original, revision in ((before, after), (after, before)):
            with self.subTest(original=original, revision=revision):
                result = check(original, revision)
                self.assertEqual(result['decision'], 'blocked')
                self.assertIn(category, {item['kind'] for item in result['findings']})
                self.assertFalse(result['publish_ready'])

    def test_price_floor(self):
        self.assertBlocked('Стоимость от 15 000 ₽.', 'Стоимость 15 000 ₽.')

    def test_price_ceiling(self):
        self.assertBlocked('Цена до 15 000 ₽.', 'Цена 15 000 ₽.')

    def test_floor_to_ceiling(self):
        self.assertBlocked('Цена от 15 000 ₽.', 'Цена до 15 000 ₽.')

    def test_billing_period(self):
        self.assertBlocked('Стоимость — 15 000 ₽ в месяц.', 'Стоимость — 15 000 ₽ в неделю.')

    def test_billing_period_removed(self):
        self.assertBlocked('Пакет 900 ₽ за год.', 'Пакет 900 ₽.')

    def test_currency_prefix(self):
        self.assertBlocked('Цена от USD 50 в месяц.', 'Цена USD 50 в неделю.')

    def test_period_swap_keeps_amount_bag(self):
        self.assertBlocked('Пакет 100 ₽ в месяц; пакет 200 ₽ в год.',
                           'Пакет 100 ₽ в год; пакет 200 ₽ в месяц.')

    def test_payment_role(self):
        self.assertBlocked('Предоплата — 50%.', 'Скидка — 50%.')

    def test_role_removed(self):
        self.assertBlocked('Аванс — 500 ₽.', 'Цена — 500 ₽.')

    def test_free_service_added(self):
        self.assertBlocked('В пакет входит консультация.',
                           'В пакет входит бесплатная консультация.')

    def test_date_direction(self):
        self.assertBlocked('Запуск до 10 ноября.', 'Запуск после 10 ноября.')

    def test_brand_at_sentence_start(self):
        self.assertBlocked('ТаирПромо помогает бизнесу.',
                           'ТайрПромо помогает бизнесу.', 'proper_name')

    def test_initial_capital_requires_review(self):
        result = check('Самара — город проведения.', 'Казань — город проведения.')
        finding = next(item for item in result['findings'] if item['kind'] == 'initial_capital')
        self.assertEqual(finding['severity'], 'review')
        self.assertFalse(result['publish_ready'])

    def test_audience_context(self):
        result = check('Помогаем салонам красоты.', 'Помогаем медицинским клиникам.')
        finding = next(item for item in result['findings'] if item['kind'] == 'audience_context')
        self.assertEqual(finding['severity'], 'review')

    def test_no_values_in_report(self):
        result = check('Самара — город проведения. Аванс 8273 ₽.',
                       'Казань — город проведения. Скидка 8273 ₽.')
        encoded = json.dumps(result, ensure_ascii=False)
        for value in ('Самара', 'Казань', '8273', 'Аванс', 'Скидка'):
            self.assertNotIn(value, encoded)


class EquivalentEditTests(unittest.TestCase):
    def test_equivalent_pairs(self):
        pairs = [
            ('Подготовка занимает три дня.', 'Подготовка занимает 3 дня.'),
            ('Доставка за пять дней.', 'Доставка за 5 дней.'),
            ('Оплата через два месяца.', 'Оплата через 2 месяца.'),
            ('Цена — 15 тыс. рублей.', 'Цена — 15 000 ₽.'),
            ('Стоимость от 15 000 ₽.', 'Стоимость начиная с 15 000 ₽.'),
            ('Цена до 15 000 ₽.', 'Цена не более 15 000 ₽.'),
            ('Предоплата — 50%.', 'Аванс — 50%.'),
            ('Пакет 900 ₽ в месяц.', 'Пакет 900 ₽ за месяц.'),
            ('Доставка бесплатная.', 'Доставка бесплатно.'),
            ('Цена - 15 000 ₽.', 'Цена — 15 000 ₽.'),
            ('Помогаем разобраться в задаче.', 'Поможем разобраться с задачей.'),
        ]
        for before, after in pairs:
            for original, revision in ((before, after), (after, before)):
                with self.subTest(original=original, revision=revision):
                    result = check(original, revision)
                    self.assertNotEqual(result['decision'], 'blocked', result['findings'])
                    self.assertFalse(result['publish_ready'])

    def test_normalization_keeps_changed_amount(self):
        self.assertEqual(check('Подготовка занимает три дня.',
                               'Подготовка занимает 5 дней.')['decision'], 'blocked')

    def test_changed_word_quantities_without_anchor(self):
        self.assertEqual(check('Три дня.', 'Пять дней.')['decision'], 'blocked')

    def test_normalization_keeps_changed_unit(self):
        self.assertEqual(check('Подготовка занимает три дня.',
                               'Подготовка занимает 3 месяца.')['decision'], 'blocked')

    def test_normalization_keeps_swapped_bindings(self):
        self.assertEqual(check('Сайт три дня; магазин пять дней.',
                               'Сайт 5 дней; магазин 3 дня.')['decision'], 'blocked')

    def test_normalization_keeps_protected_phrase(self):
        result = check('Срок три дня.', 'Срок 3 дня.', ('три дня',))
        self.assertEqual(result['decision'], 'blocked')
        self.assertIn('protected_term', {item['kind'] for item in result['findings']})

    def test_compound_cardinals_are_not_partially_normalized(self):
        self.assertEqual(check('Срок двадцать три дня.', 'Срок 3 дня.')['decision'], 'blocked')

    def test_links_do_not_generate_commercial_findings(self):
        result = check('https://example.org/бесплатно', 'https://example.org/платно')
        self.assertNotIn('commercial_term', {item['kind'] for item in result['findings']})

    def test_capitalized_rephrasing_is_not_a_name_blocker(self):
        result = check('Соберём сайт за три дня.', 'Сделаем сайт за 3 дня.')
        self.assertNotEqual(result['decision'], 'blocked')


if __name__ == '__main__':
    unittest.main()
