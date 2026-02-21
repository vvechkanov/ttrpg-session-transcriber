# scripts/

Скрипты проекта **discord-session-transcriber**. Основная документация — в `../00_README.md`.

## Файлы

- **`install_whisperx_windows.ps1`** — инсталлятор: создаёт venv, ставит PyTorch + WhisperX, скачивает ffmpeg. Всё внутри проекта.
- **`run_whisperx_gui.bat`** — запуск GUI-лаунчера (вызывается из `../run.bat`).
- **`wisper_launcher.py`** — основной лаунчер: CLI + GUI (tkinter). Запускает WhisperX на аудиофайлах, вызывает merge и chunking.
- **`merge_whisperx.py`** — склейка JSON-транскриптов WhisperX в единый `merged.txt` по таймкодам.
- **`chunk_text.py`** — нарезка `merged.txt` на чанки с overlap для подачи в LLM.
