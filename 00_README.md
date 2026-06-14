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
├── ui/                                 ← PySide6/QML GUI (точка входа `python -m ui`)
├── core/                               ← оркестрация пайплайна, discovery, пики
├── sources/ mergers/ renderers/        ← адаптеры входа, склейка, рендер merged.txt/chunks
├── prompts/
│   ├── 01_raw_to_transcript.md          ← промпт: сырьё → литературная стенограмма
│   └── 02_transcript_to_journal.md      ← промпт: стенограмма → журнал (глава книги)
├── venv/                                ← (создаётся инсталлятором)
└── tools/
    └── ffmpeg/                          ← (скачивается инсталлятором)
```

## Быстрый старт

### 1. Установка (один раз на новом компьютере)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate      # Linux/macOS
pip install -e .
```

ASR-бэкенд (faster-whisper / GigaAM и т.п.) приложение скачивает само в изолированный
каталог при первом запуске. Нужен **ffmpeg в `PATH`** (или положите его в `tools/ffmpeg/bin`).

### 2. Запуск

```bash
python -m ui
```

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
