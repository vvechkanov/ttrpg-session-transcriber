# scripts/

Скрипты проекта **discord-session-transcriber**. Основная документация — в `../00_README.md`.

Точка входа приложения теперь — `python -m ui` (GUI и headless-CLI). Лаунчер
`wisper_launcher.py` и `merge_whisperx.py` удалены; их функции переехали в
слои `core/`, `mergers/`, `renderers/` и `ui/`.

## Файлы

- **`install_whisperx_windows.ps1`** — legacy-инсталлятор PyTorch/WhisperX (исторический; новый поток — `pip install -e .` + рантайм-установка бэкенда).
- **`chunk_text.py`** — нарезка `merged.txt` на чанки с overlap для подачи в LLM.
- **`download_gigaam.py`** — загрузка модели GigaAM.
- **`capture_qml_screens.py`, `dump_qml_geometry.py`** — отладочные утилиты для QML-UI.
- **`gen_*.py`, `generate_e2e_fixtures.py`** — генерация тестовых фикстур.
- **`precommit_gate.py`** — хук Claude Code `PreToolUse`. Читает payload со stdin, и если в команде есть слово `commit`, материализует индекс через `git checkout-index -a --prefix=<tmp>/` и гоняет по снимку `ruff check --select F821` и быстрый набор pytest. Красное — отказ в коммите. Проверяет индекс, а не рабочее дерево: коммит записывает индекс.
- **`test_edit_reminder.py`** — хук Claude Code `PostToolUse` на `Write|Edit`. На файл в `tests/` отдаёт три вопроса, отличающие тест, который поймает регрессию, от теста, который только выглядит так; на остальных файлах молчит.

Оба хука включаются через `.claude/settings.json`, а `.claude/` — в `.gitignore`. На свежем клоне и в облачной сессии они не работают; блокирующая проверка там живёт в CI (см. `docs/process.md` §7.1).
