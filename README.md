# Словодел

Открытый навык для редактуры русскоязычных текстов: постов, заголовков, рекламы, рассылок и сценариев. Помогает проверить смысл, ассоциации, звучание и ритм перед публикацией.

**Это самостоятельная редакторская методика.** Она вдохновлена вопросами фоносемантики и суггестивной лингвистики, но не является оригинальной программой «Словодел»/«Диатон», её копией или продуктом её авторов. Навык не обещает внушения или роста конверсии: оцените результат на своей аудитории.

## Установка публичного навыка v0.6.0

Публичная версия выпускается как **отдельная папка `skills/slovodel/`**, а не как сервер или бот. В ней находятся `SKILL.md`, `LICENSE`, `references/`, `assets/`, `scripts/`, `slovodel_core/` и пять схем в `schemas/`. Копировать весь репозиторий в папку навыков не нужно.

**Поддерживаемые пути:**
- **Codex CLI / IDE / desktop**: `~/.agents/skills/slovodel/SKILL.md` или `<проект>/.agents/skills/slovodel/SKILL.md`; вызов через `$slovodel` или `/skills`.
- **Claude Code**: `~/.claude/skills/slovodel/SKILL.md` или `<проект>/.claude/skills/slovodel/SKILL.md`; вызов `/slovodel`.

**Linux/macOS — установка в Codex:**

```bash
git clone --depth 1 --branch v0.6.0 https://github.com/rubigotrafikcash-gif/slovodel.git slovodel-release
mkdir -p "$HOME/.agents/skills"
cp -R slovodel-release/skills/slovodel "$HOME/.agents/skills/slovodel"
```

Для **Claude Code** вместо последней директории используй `$HOME/.claude/skills/slovodel`. Для Windows PowerShell, обновления, удаления, резервной копии, примеров CLI и проверки без Python см. **[полное руководство по установке](skills/slovodel/references/install.md)**.

После копирования каталог навыка автономен. С **Python 3.10+** доступны проверяемые офлайн-команды, без Python остаётся только качественная работа агента по инструкциям — **никаких выдуманных подсчётов**. Дополнительные словари необязательны и распространяются под собственной лицензией, не автоматически MIT.

**Статус проверки:** CI проверяет переносимость папки и реальные CLI в двух каталогах, похожих на расположения Codex/Claude. **Активация в аутентифицированных клиентах Codex/Claude не проверена**; не считать имитацию расположения самостоятельным E2E модели. Результат представлен как GitHub **pre-release**, пока независимые агентские испытания не подтверждены.

[Список выпусков](https://github.com/rubigotrafikcash-gif/slovodel/releases) · [Установка Codex](https://learn.chatgpt.com/docs/build-skills) · [Установка Claude Code](https://code.claude.com/docs/en/skills).

## План развития публичной версии (15.10.2026)

Зафиксирована поэтапная разработка **публичного локального навыка**: измерительный Python Core, воспроизводимые метрики и проверка правок. **Состояние по Issue #10 (публичная упаковка v0.6.0):** Python Core дополнительно содержит исполняемую интеграцию четырёх редакторских режимов с измерениями A1–A7 и отдельным A8 fact guard. AI-агент сам пишет и оценивает текст; локальный Python только выполняет измерения и контроль. Он блокирует обнаруженные изменения, но **не доказывает смысловую эквивалентность** и не разрешает публикацию самостоятельно. Без `--morphology` и пакета остальные измерения работают как раньше. Общерусской нормативной базы по-прежнему нет; исторические и фонетические шкалы не реализованы. Приватный MCP/API, n8n, VPS и работа на домашнем сервере отложены.

- [Принятые решения и ограничения](docs/PROJECT_DECISIONS.md)
- [Техническая спецификация публичной версии](docs/PUBLIC_TECHNICAL_SPEC.md)
- [Последовательная дорожная карта и GitHub Issues](docs/ROADMAP.md)

**Процесс:** одновременно выполняется только одна задача. Текущий статус проверяйте в [GitHub Issues](https://github.com/rubigotrafikcash-gif/slovodel/issues); после закрытия текущей следующую начинают только по отдельной команде, без параллельной разработки.

## Что внутри

```text
skills/slovodel/SKILL.md
skills/slovodel/references/formats.md
skills/slovodel/references/compliance.md
skills/slovodel/references/examples.md
skills/slovodel/references/workflows.md
skills/slovodel/assets/voice-brief.md
skills/slovodel/references/methodology.md
skills/slovodel/references/cli-contract.md
skills/slovodel/references/metrics-contract.md
skills/slovodel/references/a2-contract.md
skills/slovodel/references/morphology-contract.md
skills/slovodel/references/fact-guard-contract.md
skills/slovodel/references/agent-workflow.md
skills/slovodel/references/install.md
skills/slovodel/LICENSE
skills/slovodel/schemas/{analysis,compare,local-reference,fact-guard,workflow}.schema.json
skills/slovodel/references/morphology-licenses.md
skills/slovodel/references/corpus-license-review.md
skills/slovodel/resources/corpora/README.md
skills/slovodel/scripts/{analyze,compare,build_reference,validate,workflow}.py
skills/slovodel/slovodel_core/
schemas/{analysis,compare,local-reference,fact-guard,workflow}.schema.json
tests/{test_cli,test_metrics,test_a2,test_morphology,test_fact_guard,test_workflow}.py
pyproject.toml
evals/cases.md
README.md
LICENSE
```

`SKILL.md` задаёт пять режимов: `audit` (диагностика без правки), `rewrite` (редактирование с контролем фактов), `create` (черновик по брифу), `compare` (сравнение двух версий), `historical_research` (источниковедческая справка). Справочники уточняют форматы, ограничения и примеры. `evals/cases.md` содержит **29 ручных сценариев**, но наличие сценариев **не означает успешного выполнения тестов**. В репозитории есть офлайн-скрипты и базовые **орфографические** измерители, а также необязательная морфология для подсчёта частей речи с явным учётом неоднозначности. Встроенных нормативных корпусов и исторических алгоритмов нет. Внешние запросы, серверы и ключи не требуются.

## Локальный Python Core (v0.6.0)

На машине с Python ≥3.10, **без установки сторонних пакетов**:

```bash
python skills/slovodel/scripts/analyze.py --input post.txt --mode audit --format json
python skills/slovodel/scripts/compare.py --before old.txt --after new.txt --format json
python -m unittest discover -s tests -v
```

Отчёт пишется в stdout; `--output result.json` создаёт новый файл, никогда не перезаписывает существующий. Скрипты не отправляют текст на сервер, выполняют локальные подсчёты букв, токенов, повторов, слогов по гласным, лексики и позиции композиционного сечения, **но не выполняют расчёты «Диатона»**. Сведения о методах и ограничениях: [метрики](skills/slovodel/references/metrics-contract.md). Подробнее: [контракт CLI и ограничения](skills/slovodel/references/cli-contract.md), [JSON schema анализа](schemas/analysis.schema.json), [JSON schema сравнения](schemas/compare.schema.json).

## A2 — локальные частоты, без внешнего корпуса

Корпусные таблицы **не встроены**. При желании можно создать профиль из собственных текстов: `python skills/slovodel/scripts/build_reference.py --help`. Для `analyze.py` и `compare.py` параметр `--reference profile.json` включает математические отклонения от **этого конкретного локального профиля**. Профиль не объявляется нормативным, а лицензия источника заявляется пользователем и не проверяется автоматически. Пример использования: [A2 contract](skills/slovodel/references/a2-contract.md), [сверка лицензий](skills/slovodel/references/corpus-license-review.md).

## A5 — необязательный POS-анализ русского текста

```bash
# Только при необходимости: сторонний движок MIT + отдельно лицензированный CC BY-SA словарь
python -m pip install pymorphy3==2.0.6 pymorphy3-dicts-ru==2.4.417150.4580142

python skills/slovodel/scripts/analyze.py --input post.txt --morphology
python skills/slovodel/scripts/compare.py --before old.txt --after new.txt --morphology
```

Без установки и флага POS остаётся `unavailable/null`, **при этом все другие вычисления доступны**. Известные словарю неоднозначные слова выводятся отдельной категорией, а не приписываются к произвольной части речи. [Контракт A5](skills/slovodel/references/morphology-contract.md), [лицензии источников](skills/slovodel/references/morphology-licenses.md).

## A8 — контроль фактов при правке

Перед тем как считать переписанный текст готовым, сравни исходник и вариант:

```bash
python skills/slovodel/scripts/validate.py --before original.txt --after edited.txt
python skills/slovodel/scripts/validate.py --before original.txt --after edited.txt --protected-file protected.txt
```

Команда вернёт JSON `blocked` (код выхода **5**) при изменении обнаруженных сумм, ссылок, дат, чисел, сроков, условий, имён и других защищённых элементов. `review_required` означает, что **автоматически не обнаружено** таких изменений, но экспертная проверка смысла всё равно необходима. Нет полного семантического анализа, автоматического допуска к публикации или разрешения правовых вопросов. [Подробный контракт A8](skills/slovodel/references/fact-guard-contract.md).

## Четыре исполняемых режима AI-навыка (Issue #8)

AI создаёт редакторские тексты; Python Core **не генерирует AI-контент**, а выполняет анализ, сравнение и контроль защищённых фактов. Вызовы локальны и **не разрешают автоматическую публикацию**:

```bash
python skills/slovodel/scripts/workflow.py --mode audit --input original.txt
python skills/slovodel/scripts/workflow.py --mode rewrite --before original.txt --after edited.txt
python skills/slovodel/scripts/workflow.py --mode create --input draft.txt
python skills/slovodel/scripts/workflow.py --mode compare --before a.txt --after b.txt
```

Для `rewrite` сделайте предварительный audit, затем AI-правку и только после неё запустите `workflow.py --mode rewrite`. При найденной опасной разнице вывод `blocked` (код **5**) запрещает считать текст готовым. Если расхождений не найдено, результат всё равно требует смысловой проверки. `create` анализирует уже подготовленный черновик, **не проверяет факты брифа**; `compare` возвращает только действительные сопоставимые метрики. При отсутствии доступного Python навык остаётся качественным редактором и не имитирует числовой анализ.

[Контракт взаимодействия агента и Core](skills/slovodel/references/agent-workflow.md) · [JSON Schema workflow](schemas/workflow.schema.json) · [E2E-тесты](tests/test_workflow.py).

## Использование

Откройте [SKILL.md](skills/slovodel/SKILL.md) и добавьте весь каталог `skills/slovodel` в каталог навыков вашего агента. Он должен сохранить `references/` и `assets/` рядом с `SKILL.md`.

- **Codex / ChatGPT:** включите каталог как навык через доступный в вашей версии интерфейс или положите его в поддерживаемый каталог навыков. В Codex явно вызовите `$slovodel`, в ChatGPT — `@slovodel`, если навык установлен. [Руководство OpenAI](https://developers.openai.com/codex/skills-and-plugins).
- **Claude Code:** скопируйте каталог в `.claude/skills/slovodel/` проекта или `~/.claude/skills/slovodel/` для себя; вызовите `/slovodel`. [Руководство Anthropic](https://code.claude.com/docs/en/skills).
- **Gemini CLI:** скопируйте каталог в `.agents/skills/slovodel/` проекта или `~/.gemini/skills/slovodel/`. Проверьте обнаружение командой `/skills list`; также поддерживается установка навыка из Git. [Руководство Gemini CLI](https://geminicli.com/docs/cli/skills/).

Пример запроса для `rewrite`: «Примени СловоДел к этому посту для кандидатов на роль ассистента. Сохрани факты, предложи один вариант и объясни ключевые правки». Для `audit`: «Проверь этот текст, но не переписывай». Для `compare`: «Сравни два варианта; не придумывай исторические баллы». 

**Режим без Python:** качественная редактура и диагностика возможны по инструкциям. **При наличии Python:** исполняемый `workflow.py` подтверждает локальный запуск Core и применяет A8 после AI-правки; измерительные CLI выдают воспроизводимые показатели и сопоставимые дельты; с явным `--reference` добавляется сравнение букв с **локальным ненормативным** профилем. Подтверждённых нормативных, морфологических и исторических показателей нет — `unavailable/null`, а не ноль. Показатели нельзя автоматически трактовать как силу воздействия или качество текста. Отсутствие расчёта — `unavailable`, а не ноль. Запуск локального Core требует поддерживающего агента и разрешённого окружения; GitHub не предоставляет постоянно работающую службу анализа.

## Проверки публичного навыка (Issue #9)

Модульные и E2E-тесты запускаются в GitHub Actions на Python 3.10/3.12: **160 тестов**, проверка схем JSON и запуск с/без необязательного русского словаря. На **пяти детерминированных модулях** (`metrics.py`, `a2.py`, `fact_guard.py`, `reports.py`, `workflow.py`) установлен CI-порог **≥90% покрытия строк**; фактически получено **97%** на контрольном прогоне. Это не точность редакторского анализа и не покрытие всей кодовой базы.

```bash
python -m unittest discover -s tests -v
python scripts/offline_smoke.py
# Дополнительные инструменты CI: jsonschema, coverage, опциональный pymorphy3.
```

[Протокол Issue #9](docs/ISSUE_9_VERIFICATION.md) · [22 синтетические пары проверок](tests/fixtures/issue9_cases.json) · [29 агентских сценариев](evals/cases.md) · [методика отдельного агентского тестирования](evals/agent-test-protocol.md).

**Важно:** 18 ответов GPT-6 зафиксированы в текущей беседе в виде [ручного журнала](evals/agent-runs/2026-10-15-gpt6-in-session.md), но это самооценка, **не** независимый запуск навыка, установленного в Codex/Claude/Gemini. Кросс-клиентский agent E2E остаётся `NOT_RUN` и не подтверждён успешным Python CI. Тестовые тексты искусственные; исходники клиентов в репозиторий не добавляются.

## Принципы

Факты и честность важнее благозвучия. Навык не анализирует чужое «подсознание», не выводит «частоту мозга» и не выдаёт недоказанный процент воздействия. Он не публикует материалы сам и не передаёт текст сторонним сервисам.

## Разработка и источники

Формат следует [открытой спецификации Agent Skills](https://agentskills.io/specification): имя `slovodel`, описание для обнаружения и основной `SKILL.md`, а подробности подгружаются из `references/`. Это согласуется с [OpenAI](https://developers.openai.com/api/docs/guides/tools-skills), [Anthropic](https://code.claude.com/docs/en/skills) и [Gemini CLI](https://geminicli.com/docs/cli/skills-best-practices/). Список исследований и границ применимости находится в [методологии](skills/slovodel/references/methodology.md).

Изменения приветствуются через issue или pull request: приложите исходный фрагмент без персональных данных, задачу, ожидаемую правку и источник для фактического утверждения. Проверяйте предложения на сценариях из [evals/cases.md](evals/cases.md).

Лицензия на **наши** тексты и инструкции — MIT. Права на оригинальную программу и цитируемые исследования принадлежат их правообладателям.
