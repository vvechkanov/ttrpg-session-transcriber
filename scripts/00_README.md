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
