import unittest
from slovodel_core.fact_guard import check
from slovodel_core.equivalence import date_key, numbers, prepare


class EquivalentRecords(unittest.TestCase):
    def test_full_dates(self):
        for raw in ('21.02.2024','2024-02-21','21 февраля 2024 года'):
            self.assertNotEqual(check('Дата: '+raw,'Дата: 2024-02-21')['decision'],'blocked')
        for raw in ('22.02.2024','21.02.2025'):
            self.assertEqual(check('Дата: '+raw,'Дата: 2024-02-21')['decision'],'blocked')
        for raw in ('31.02.2024','15.10.26','15 марта','2024-13-01'):
            self.assertEqual(date_key(raw),raw)

    def test_compound_cardinal_values_and_mutations(self):
        for raw,value in [('тысячу пятьсот семьдесят два',1572),('две тысячи двадцать три',2023),('пять тысяч',5000),('двадцать один',21)]:
            self.assertEqual(numbers(raw),str(value))
            self.assertNotEqual(check(f'Собрали {value} документов.',f'Собрали {raw} документов.')['decision'],'blocked')
            self.assertEqual(check(f'Собрали {value+1} документов.',f'Собрали {raw} документов.')['decision'],'blocked')

    def test_invalid_combinations_are_not_summed(self):
        for raw in ('два три','десять один','сто двести','тысяча тысяча','ноль тысяч','двадцать третий участник'):
            self.assertEqual(numbers(raw),raw)

    def test_compound_years_preserve_period(self):
        a='Собрали 1572 решения с 2013 по 2023 гг.'
        b='Собрали тысячу пятьсот семьдесят два решения с две тысячи тринадцатого по две тысячи двадцать третий год.'
        self.assertNotEqual(check(a,b)['decision'],'blocked')
        self.assertEqual(check(a,b.replace('третий','второй'))['decision'],'blocked')
        self.assertNotEqual(check('За 2024 год.','За две тысячи двадцать четвёртый год.')['decision'],'blocked')

    def test_reversed_and_inflected_complete_names(self):
        for a,b in [('Ведущий: Иванов Олег.','Ведущий: Олег Иванов.'),('С физиком Феликсом Ауэрбахом.','С физиком Феликс Ауэрбах.')]:
            self.assertNotEqual(check(a,b)['decision'],'blocked')
            self.assertEqual(check(a,b.replace('Иванов','Петров').replace('Ауэрбах','Гольдберг'))['decision'],'blocked')

    def test_reference_markers_are_not_values_but_exact_terms_remain(self):
        self.assertEqual(check('Открыт завод[1].','Открыт завод.')['decision'],'blocked')
        self.assertEqual(check('Код [123].','Код [124].')['decision'],'blocked')
        self.assertEqual(check('Открыт завод[1].','Открыт завод.',('завод[1]',))['decision'],'blocked')

    def test_citation_review_requires_provenance_and_keeps_other_changes(self):
        import json
        from slovodel_core.workflow import build
        doc=lambda s:(s.encode('utf-8'),s)
        ctx=doc(json.dumps([{'text':'История завода.','source':'https://ru.wikipedia.org/wiki/Завод'}]))
        r=build('rewrite',before_doc=doc('Открыт завод[1] в 1908 году.'),after_doc=doc('Открыт завод в 1908 году.'),context_doc=ctx)
        self.assertEqual(r['decision'],'draft_requires_review')
        self.assertEqual(r['fact_guard']['decision'],'blocked')
        r=build('rewrite',before_doc=doc('Открыт завод[1] в 1908 году.'),after_doc=doc('Открыт завод в 1909 году.'),context_doc=ctx)
        self.assertEqual(r['decision'],'blocked')

    def test_shared_money_unit_does_not_allow_changed_amount(self):
        a='Взыскано 450 тыс. и 700 тыс. руб.'
        b='Взыскано 450 тыс. руб. и 700 тыс. руб.'
        self.assertNotEqual(check(a,b)['decision'],'blocked')
        self.assertEqual(check(a,b.replace('450','460'))['decision'],'blocked')

    def test_literal_urls_and_protected_spelling(self):
        self.assertEqual(prepare('https://example.org/завод[1]'),'https://example.org/завод[1]')
        self.assertEqual(check('https://example.org/завод[1]','https://example.org/завод')['decision'],'blocked')
        self.assertEqual(check('Собрали двадцать один документ.','Собрали 21 документ.',('двадцать один',))['decision'],'blocked')

    def test_list_count_requires_same_explicit_items(self):
        a='Анализ с позиций правового, экономического, социологического и психологического подходов.'
        b='Анализ четырёх подходов: правового, экономического, социологического и психологического.'
        self.assertNotEqual(check(a,b)['decision'],'blocked')
        self.assertEqual(check(a,b.replace('четырёх','пяти'))['decision'],'blocked')
        self.assertEqual(check(a,b.replace('психологического','медицинского'))['decision'],'blocked')

    def test_repeated_known_name_is_review_but_new_name_blocks(self):
        a='Ведёт Петров. Обсудим задачу.'
        self.assertNotEqual(check(a,'Ведёт Петров. Петров обсудит задачу.')['decision'],'blocked')
        self.assertEqual(check(a,'Ведёт Петров. Задачу обсудит Иванов.')['decision'],'blocked')
