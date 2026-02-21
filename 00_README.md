# discord-session-transcriber

Полностью автономный проект для пайплайна:

**Craig audio → JSON по спикерам → merged.txt → chunks → конспект сессии (LLM) → журнал сессии (LLM)**

Единственная внешняя зависимость — **Python 3.10–3.12 x64** в PATH. Всё остальное (venv, PyTorch, WhisperX, ffmpeg) устанавливается инсталлятором внутри этой папки.

## Структура проекта

```
discord-session-transcriber/
├── run.bat                              ← двойной клик — запуск GUI
├── 00_README.md                         ← этот файл
├── 01_Как_пользоваться.md               ← пошаговая инструкция
├── 02_Статус_и_заметки.md               ← текущий статус
├── scripts/
│   ├── install_whisperx_windows.ps1     ← инсталлятор (один раз)
│   ├── run_whisperx_gui.bat             ← запуск GUI (вызывается из run.bat)
│   ├── wisper_launcher.py               ← основной лаунчер (CLI + GUI)
│   ├── merge_whisperx.py                ← склейка JSON → merged.txt
│   └── chunk_text.py                    ← нарезка merged.txt → chunks
├── prompts/
│   ├── 01_raw_to_transcript.md          ← промпт: сырьё → литературная стенограмма
│   └── 02_transcript_to_journal.md      ← промпт: стенограмма → журнал (глава книги)
├── venv/                                ← (создаётся инсталлятором)
└── tools/
    └── ffmpeg/                          ← (скачивается инсталлятором)
```

## Быстрый старт

### 1. Установка (один раз на новом компьютере)

Двойной клик по **`install.bat`** в корне проекта. Всё.

Инсталлятор сам:
- создаёт `venv/` с PyTorch (GPU если есть NVIDIA, иначе CPU) и WhisperX;
- скачивает ffmpeg в `tools/ffmpeg/` (если его нет в системе).

Альтернативный запуск из PowerShell (с доп. флагами):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_whisperx_windows.ps1
```

Опциональные флаги: `-Torch cu121|cu124|cpu`, `-SkipFFmpeg`.

### 2. Запуск

Двойной клик по `run.bat` (или `scripts\run_whisperx_gui.bat`).

В GUI:
- выбрать папку сессии (где лежат `*.flac` и опционально `speaker_map.json`);
- настроить модель / compute / beam (по умолчанию: `large-v3`, `float16`, `10`);
- нажать «Запустить».

### 3. Результат

В папке сессии появятся:
- **`merged.txt`** — единый текст по спикерам, отсортированный по времени.
- **`chunks/`** — чанки с overlap и маркерами `=== CHUNK START/END ===`.
- **`chunks/000_context.txt`** — контекст (список спикеров, заметки).

### 4. Работа с LLM

1. Прогнать chunks через промпт `prompts/01_raw_to_transcript.md` → литературная стенограмма.
2. Стенограмму превратить в журнал через промпт `prompts/02_transcript_to_journal.md`.

## Промпты

- **`prompts/01_raw_to_transcript.md`** — сырьё → стенограмма/конспект
- **`prompts/02_transcript_to_journal.md`** — конспект → глава книги

## Заметки

- Финальный этап «конспект → журнал» — рабочий черновик, стиль может правиться.
- Diarization (разделение на спикеров средствами WhisperX) не используется — разделение идёт по отдельным аудиодорожкам Craig.
