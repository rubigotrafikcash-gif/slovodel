# Словодел

Открытый навык для редактуры русскоязычных текстов: постов, заголовков, рекламы, рассылок и сценариев. Помогает проверить смысл, ассоциации, звучание и ритм перед публикацией.

**Это самостоятельная редакторская методика.** Она вдохновлена вопросами фоносемантики и суггестивной лингвистики, но не является оригинальной программой «Словодел»/«Диатон», её копией или продуктом её авторов. Навык не обещает внушения или роста конверсии: оцените результат на своей аудитории.

## План развития публичной версии (15.10.2026)

Зафиксирована поэтапная разработка **публичного локального навыка**: измерительный Python Core, воспроизводимые метрики и проверка правок. **Состояние по Issue #4:** локальный Python Core v0.2.0 рассчитывает **ограниченный набор проверяемых орфографических метрик A1/A3/A4/A6/A7**. Нормативные частоты, морфология, звуковые и исторические шкалы ещё не реализованы и корректно возвращают `unavailable`, без выдуманных баллов. Приватный MCP/API, n8n, VPS и работа на домашнем сервере отложены.

- [Принятые решения и ограничения](docs/PROJECT_DECISIONS.md)
- [Техническая спецификация публичной версии](docs/PUBLIC_TECHNICAL_SPEC.md)
- [Последовательная дорожная карта и GitHub Issues](docs/ROADMAP.md)

**Процесс:** одновременно выполняется только одна задача. Первой в очереди назначена [Issue #2](https://github.com/rubigotrafikcash-gif/slovodel/issues/2). Актуальный статус её выполнения проверяйте в GitHub Issues: после закрытия задачи следующая становится доступной **только последовательно**, без параллельной разработки.

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
skills/slovodel/scripts/{analyze,compare}.py
skills/slovodel/slovodel_core/
schemas/{analysis,compare}.schema.json
tests/{test_cli,test_metrics}.py
pyproject.toml
evals/cases.md
README.md
LICENSE
```

`SKILL.md` задаёт пять режимов: `audit` (диагностика без правки), `rewrite` (редактирование с контролем фактов), `create` (черновик по брифу), `compare` (сравнение двух версий), `historical_research` (источниковедческая справка). Справочники уточняют форматы, ограничения и примеры. `evals/cases.md` содержит **25 ручных сценариев**, но наличие сценариев **не означает успешного выполнения тестов**. В репозитории есть офлайн-скрипты и реализованные базовые **орфографические** измерители; нормативные корпуса, морфология и исторические алгоритмы не входят в текущую версию. Внешние запросы, серверы и ключи не требуются.

## Локальный Python Core (Issue #4, v0.2.0)

На машине с Python ≥3.10, **без установки сторонних пакетов**:

```bash
python skills/slovodel/scripts/analyze.py --input post.txt --mode audit --format json
python skills/slovodel/scripts/compare.py --before old.txt --after new.txt --format json
python -m unittest discover -s tests -v
```

Отчёт пишется в stdout; `--output result.json` создаёт новый файл, никогда не перезаписывает существующий. Скрипты не отправляют текст на сервер, выполняют локальные подсчёты букв, токенов, повторов, слогов по гласным, лексики и позиции композиционного сечения, **но не выполняют расчёты «Диатона»**. Сведения о методах и ограничениях: [метрики](skills/slovodel/references/metrics-contract.md). Подробнее: [контракт CLI и ограничения](skills/slovodel/references/cli-contract.md), [JSON schema анализа](schemas/analysis.schema.json), [JSON schema сравнения](schemas/compare.schema.json).

## Использование

Откройте [SKILL.md](skills/slovodel/SKILL.md) и добавьте весь каталог `skills/slovodel` в каталог навыков вашего агента. Он должен сохранить `references/` и `assets/` рядом с `SKILL.md`.

- **Codex / ChatGPT:** включите каталог как навык через доступный в вашей версии интерфейс или положите его в поддерживаемый каталог навыков. В Codex явно вызовите `$slovodel`, в ChatGPT — `@slovodel`, если навык установлен. [Руководство OpenAI](https://developers.openai.com/codex/skills-and-plugins).
- **Claude Code:** скопируйте каталог в `.claude/skills/slovodel/` проекта или `~/.claude/skills/slovodel/` для себя; вызовите `/slovodel`. [Руководство Anthropic](https://code.claude.com/docs/en/skills).
- **Gemini CLI:** скопируйте каталог в `.agents/skills/slovodel/` проекта или `~/.gemini/skills/slovodel/`. Проверьте обнаружение командой `/skills list`; также поддерживается установка навыка из Git. [Руководство Gemini CLI](https://geminicli.com/docs/cli/skills/).

Пример запроса для `rewrite`: «Примени СловоДел к этому посту для кандидатов на роль ассистента. Сохрани факты, предложи один вариант и объясни ключевые правки». Для `audit`: «Проверь этот текст, но не переписывай». Для `compare`: «Сравни два варианта; не придумывай исторические баллы». 

**Режим без Python:** качественная редактура и диагностика возможны по инструкциям. **При наличии Python:** два CLI выдают измеренные орфографические показатели и сопоставимые дельты; нормативные, морфологические и исторические показатели возвращают `unavailable`, а не ноль. Показатели нельзя автоматически трактовать как силу воздействия или качество текста. Отсутствие расчёта — `unavailable`, а не ноль. Запуск локального Core требует поддерживающего агента и разрешённого окружения; GitHub не предоставляет постоянно работающую службу анализа.

## Принципы

Факты и честность важнее благозвучия. Навык не анализирует чужое «подсознание», не выводит «частоту мозга» и не выдаёт недоказанный процент воздействия. Он не публикует материалы сам и не передаёт текст сторонним сервисам.

## Разработка и источники

Формат следует [открытой спецификации Agent Skills](https://agentskills.io/specification): имя `slovodel`, описание для обнаружения и основной `SKILL.md`, а подробности подгружаются из `references/`. Это согласуется с [OpenAI](https://developers.openai.com/api/docs/guides/tools-skills), [Anthropic](https://code.claude.com/docs/en/skills) и [Gemini CLI](https://geminicli.com/docs/cli/skills-best-practices/). Список исследований и границ применимости находится в [методологии](skills/slovodel/references/methodology.md).

Изменения приветствуются через issue или pull request: приложите исходный фрагмент без персональных данных, задачу, ожидаемую правку и источник для фактического утверждения. Проверяйте предложения на сценариях из [evals/cases.md](evals/cases.md).

Лицензия на **наши** тексты и инструкции — MIT. Права на оригинальную программу и цитируемые исследования принадлежат их правообладателям.
