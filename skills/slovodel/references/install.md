# Установка публичного «СловоДела» — v0.7.0

**Одна папка `slovodel/` — полный автономный пакет навыка**: `SKILL.md`, `LICENSE`, `references/`, `assets/`, `scripts/`, `slovodel_core/`, `schemas/`. Python не нужен для качественной редактуры: AI-агент читает инструкции и оформляет текст. Для проверяемых числовых расчётов требуется **Python 3.10+** в среде агента и разрешение на локальный запуск скриптов.

Официальные пути загрузки Agent Skills (проверены для документации):
- [Codex / ChatGPT — Build skills](https://learn.chatgpt.com/docs/build-skills): для пользователя `~/.agents/skills/slovodel/`, для проекта `<repo>/.agents/skills/slovodel/`; выбор навыка через `/skills` или `$slovodel`. Самостоятельный навык поддерживается Codex CLI/IDE/ChatGPT desktop; **не обещайте установку отдельной папки как полноценного ChatGPT mobile-плагина**.
- [Claude Code — Skills](https://code.claude.com/docs/en/skills): пользовательская директория `~/.claude/skills/slovodel/`, проектная `<repo>/.claude/skills/slovodel/`; явный вызов `/slovodel`. Не путать Claude Code с Claude web/синхронизацией аккаунта.

## Чистая установка из GitHub

Сначала скачай **конкретную опубликованную версию** в отдельную временную директорию. Для Linux/macOS (с установленным Git):

```bash
git clone --depth 1 --branch v0.7.0 https://github.com/rubigotrafikcash-gif/slovodel.git slovodel-release

# Установить в Codex (один раз, если такого каталога ещё нет):
mkdir -p "$HOME/.agents/skills"
cp -R slovodel-release/skills/slovodel "$HOME/.agents/skills/slovodel"

# ИЛИ установить в Claude Code:
mkdir -p "$HOME/.claude/skills"
cp -R slovodel-release/skills/slovodel "$HOME/.claude/skills/slovodel"
```

**Выбирай нужный агент; не обязательно устанавливать в оба.** Если каталог уже существует, **не накладывай новую папку поверх старой**: сначала сделай резервную копию старой версии и только потом обновляй. Перед первым использованием изучи `SKILL.md`, `LICENSE`, состав файлов и права стороннего словаря.

Для Windows PowerShell:

```powershell
git clone --depth 1 --branch v0.7.0 https://github.com/rubigotrafikcash-gif/slovodel.git slovodel-release

# Codex:
New-Item -ItemType Directory -Force "$HOME/.agents/skills" | Out-Null
Copy-Item -Recurse -LiteralPath "slovodel-release/skills/slovodel" -Destination "$HOME/.agents/skills/slovodel"

# ИЛИ Claude Code:
New-Item -ItemType Directory -Force "$HOME/.claude/skills" | Out-Null
Copy-Item -Recurse -LiteralPath "slovodel-release/skills/slovodel" -Destination "$HOME/.claude/skills/slovodel"
```

В PowerShell не выполняй `Copy-Item` поверх уже существующей папки без предварительного резервного копирования. Если нет Git, скачай **Source code (ZIP)** для конкретного GitHub Release, распакуй и скопируй только каталог `skills/slovodel` внутрь соответствующей директории агента, сохранив структуру. В графическом файловом менеджере путь и структура аналогичны.

**Удаление:** отключи/заверши работу агента и удали *только* установленную папку `~/.agents/skills/slovodel` или `~/.claude/skills/slovodel`, убедившись, что это именно пакет «СловоДел». Другие каталоги навыков не трогай. Встроенных сервисов/фоновых процессов и собственной БД нет.

## Проверка после установки

При наличии локального Python и если установленный навык находится в Codex:

```bash
python "$HOME/.agents/skills/slovodel/scripts/workflow.py" --help
python "$HOME/.agents/skills/slovodel/scripts/analyze.py" --help
```

Для Claude Code замени путь на `$HOME/.claude/skills/slovodel`. В PowerShell используй `python "$HOME/.agents/skills/slovodel/scripts/workflow.py" --help` или `py -3` с доступным Python 3.10+.

После запуска AI-агента проверь, что навык `slovodel` обнаружен, и отдельно проведи задания `audit`, `rewrite`, `create`, `compare` из [плана реальных агентских испытаний](https://github.com/rubigotrafikcash-gif/slovodel/blob/main/evals/cases.md). **Успешная проверка структуры файлов или CLI не равна проверке активации навыка реальным агентом.** Для Codex/Claude обязательно записывай фактическую версию клиента и сохранённый ответ; если агент не запускался — `NOT_RUN`.

## Без Python и без сети

**Наличие Python необязательно** для текстовой редакторской работы: даже без выполнения `scripts/*.py` агент использует `SKILL.md`, `references/` и `assets/`; разрешены только **качественные** выводы, без выдуманных баллов или заявления «Core запускался». Отсутствие локального Python в конкретной среде — не основание запускать внешние модели или передавать текст другому сервису.

Сами `scripts/*.py` используют **стандартную библиотеку Python**, без собственного API/сервера и без проектных сетевых вызовов. Среда исполнения по умолчанию **не имеет сетевой изоляции на уровне ОС**, поэтому не обещайте sandbox. Скачать GitHub-репозиторий или установить необязательные зависимости может потребоваться через интернет *до* использования офлайн-сценария.

## Опциональные возможности и лицензии

| Возможность | Дополнительные условия |
|---|---|
| Базовый анализ A1/A3/A4/A6/A7, A8 fact-guard, четыре режима | Python 3.10+, без дополнительных Python-пакетов; все схемы JSON внутри `schemas/` |
| Строгая внешняя валидация JSON Schema | Необязательный `jsonschema==4.25.1` (для пользователя не обязателен) |
| Русские части речи A5 | **Только при явном `--morphology`**: `pymorphy3==2.0.6` (MIT) + `pymorphy3-dicts-ru==2.4.417150.4580142` (код MIT; **данные словаря CC BY-SA 3.0**) |
| A2 сравнение буквенных частот | `--reference` с предоставленным пользователем собственным профилем, объявленным **ненормативным**, права на источник пользователь проверяет самостоятельно |
| Историческая «сила внушения», «Диатон», общерусская нормативная база | **Не реализованы, значения unavailable/null** |

Лицензия **собственного кода MIT**, см. `LICENSE` в самом пакете. Необязательные словари **не копируются в GitHub и не становятся MIT от того, что Python-обвязка MIT**. См. [лицензии морфологии](morphology-licenses.md) и [сведения о корпусах](corpus-license-review.md). Статистика и логирование не являются проверкой достоверности рекламы или юридической пригодности.

## Что действительно проверено в CI

GitHub Actions ставит **копию одной папки** `skills/slovodel` в два временных дерева с путями Codex и Claude Code, убирает возможность использовать остальные файлы репозитория как импортируемые модули, запускает четыре режима Python из третьего каталога с `python -I`, проверяет JSON и `blocked` на разнице сумм, сводит версии внешних и встроенных схем. Проверка выполняется без реальных учётных данных. Это **подтверждённая проверка переносимости каталога и исполняемого слоя**, но **НЕ** запуск самих моделей Codex/Claude и не тест реального выбора навыка из меню, которые могут требовать установленный клиент и авторизацию.

Выпуск `v0.7.0` содержит проверенный публичный пакет; следи за [GitHub Release](https://github.com/rubigotrafikcash-gif/slovodel/releases). Не копируй в публичный репозиторий пользовательские исходники/скриншоты/токены.
