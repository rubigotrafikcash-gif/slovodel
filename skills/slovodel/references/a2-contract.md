# A2: локальный частотный эталон без утверждения нормативности

Версия Python Core 0.3.0. По умолчанию общерусская norm_letter_deviation **недоступна**, так как правомерный и репрезентативный корпус не утверждён.

## Формулы (для буквы i)

- p_i = n_i/N: доля буквы в анализируемом тексте по правилу A1.
- q_i = b_i/B: доля той же буквы в локальном пользовательском профиле, где B > 0.
- delta_pp = round(100 * (p_i - q_i), 8), единица = процентные пункты.
- ratio = round(p_i/q_i, 8) при q_i > 0, иначе unavailable/null, в том числе при p_i = 0.
- При N = 0 обе метрики unavailable/null, **не ноль**.
- Все 33 русские буквы (е и ё отдельно), 66 профильно-зависимых метрик. URL и email исключаются эвристически в точности как в базовом A1. Unicode NFC и casefold.

Значение reproducible относится только к **математике относительно указанного локального эталона**: каждая числовая метрика содержит метод и версию, n, единицу и dataset_id вида local-sha256:<64 hex>. Никаких «отклонений от нормы русского языка» по такому профилю не заявлять. Маркеры: LOCAL_REFERENCE_NOT_NORMATIVE, LICENSE_SELF_DECLARED_UNVERIFIED; при B меньше 10000 — SMALL_REFERENCE_CORPUS, N меньше 100 — SMALL_SAMPLE.

## Работа локально

Используется **только самостоятельно подготовленный/законно доступный текст** не более 1 МиБ. Метаданные лицензии декларируются самим пользователем и **не проверяются автоматически**.

~~~bash
python skills/slovodel/scripts/build_reference.py --input my_corpus.txt --source-label "My texts" --source-url "local://my-corpus" --genre "blog" --corpus-version "2026-10" --license-id "CC0-1.0" --rights-basis "I authored these texts" --output my_reference.json
python skills/slovodel/scripts/analyze.py --input post.txt --reference my_reference.json --output report.json
python skills/slovodel/scripts/compare.py --before old.txt --after new.txt --reference my_reference.json --output diff.json
~~~

Лицензия CC0 выше **пример для самостоятельно созданных материалов**, а не основание объявлять чужой текст своим.

Профиль: 33 целочисленных счётчика, total_letters > 0 равен их сумме, SHA-256 оригинального корпуса, жанр, версия, источник, заявленная лицензия и основание прав, method_version, preprocessing. Исходный текст **не сохраняется в JSON**. Проверяются строгая форма, отсутствие повторных ключей JSON, е/ё, неотрицательные целые, сумма, метод/версия. Статусы profile_kind=user_supplied_non_normative и license_status=self_declared_unverified принудительно заданы и не могут быть сменены на verified.

compare применяет **один и тот же** локальный профиль к обеим версиям и проверяет method_id, method_version, dataset_id. Для одинаковых текстов все доступные дельты равны 0; для q=0 ratio остаётся недоступной и в сравнение не входит. Без явного --reference локальных метрик нет, norm_letter_deviation остаётся unavailable/null всегда.

## Юридические и технические границы

Это буквенные, а не фонетические частоты; очень короткие тексты статистически нестабильны. Даже большая коллекция отдельного жанра не является представительной нормой языка. Заявленная пользователем лицензия не является подтверждённым разрешением распространения профиля. Никаких фоново скачиваемых корпусов и сетевых вызовов нет. SHA-256, жанр и частоты могут раскрывать информацию о чувствительном тексте; не выкладывать частные профили без проверки.

Подробности прав: [corpus-license-review.md](corpus-license-review.md). Паспорта: [resources/corpora/README.md](../resources/corpora/README.md).
