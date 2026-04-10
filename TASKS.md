# TTRPG Session Transcriber — Tasks

Чек-лист задач для превращения проекта в полноценный open-source продукт. Структура и обоснование — в `~/.claude/plans/virtual-wondering-karp.md`.

**Имя проекта:** TTRPG Session Transcriber (`ttrpg-session-transcriber`)
**Лицензия:** MIT (TBD — ждёт подтверждения)
**Текущая ветка:** master

---

## Приоритет 1 — Story / маркетинг (1-2 дня)

**Цель:** закрепить нишу до того как Scribble добавит наши преимущества.

### 1.1 Юридика и базовые файлы
- [ ] Создать `LICENSE` (MIT, copyright holder = vvechkanov)
- [ ] Создать `CHANGELOG.md` (Keep a Changelog формат, начать с unreleased секции)
- [ ] Создать `SECURITY.md` (placeholder с email для репортов)
- [ ] Создать `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1)

### 1.2 README rewrite
- [ ] Backup текущего README в `docs/legacy-readme.md`
- [ ] Hero-секция: «The only open-source tool that merges your Foundry VTT chat log into the per-speaker audio transcript timeline»
- [ ] Badge row: license, CI status (placeholder), Python versions, latest release
- [ ] Скриншот текущего installer-а (Windows) — положить в `docs/screenshots/installer.png`
- [ ] Секция «4 USP» с конкретикой по каждому
- [ ] Quick Start: «Download .exe → drop Craig folder → done» с GIF или скриншотами
- [ ] Comparison table vs TASMAS / Scribble / Kazkar / Archivist (честная)
- [ ] FAQ:
  - «Why per-track Craig instead of acoustic diarization?»
  - «Why GigaAM for Russian?»
  - «Is my audio uploaded anywhere?» (no — local only)
  - «Does it work without GPU?» (yes, slower)
  - «What about D&D 5e / other systems?» (yes — universal, PF2e is just our test bed)
- [ ] Roadmap секция со ссылкой на TASKS.md и план-файл
- [ ] Контакты / community (Discord/Telegram если есть)
- [ ] Acknowledgments: Craig, faster-whisper, sherpa-onnx, GigaAM, Foundry VTT
- [ ] Дублирующая README на русском в `docs/README.ru.md` или второй секцией

### 1.3 GitHub project hygiene
- [ ] Обновить description репозитория на GitHub
- [ ] Установить topics: `ttrpg`, `dnd`, `pathfinder`, `transcription`, `whisper`, `discord`, `craig`, `foundry-vtt`, `russian`
- [ ] Создать `CONTRIBUTING.md`:
  - Как клонировать и собрать локально
  - Как запустить тесты (placeholder, реально будет в Приоритете 3)
  - Code style (ruff)
  - Pull request process
- [ ] `.github/ISSUE_TEMPLATE/bug_report.md`
- [ ] `.github/ISSUE_TEMPLATE/feature_request.md`
- [ ] `.github/ISSUE_TEMPLATE/config.yml` (отключить blank issues)
- [ ] `.github/PULL_REQUEST_TEMPLATE.md`

### 1.4 Имя и переименование
- [ ] Решить — переименовываем GitHub репозиторий в `ttrpg-session-transcriber` или оставляем текущее имя
- [ ] Если переименовываем — обновить ссылки в скриптах, README, GitHub Actions
- [ ] Опечатка `wisper_launcher.py` → переименование в Приоритете 2 (вместе с backend рефакторингом)

### 1.5 Commit + PR
- [ ] Один большой PR «P1: open-source hygiene + README repositioning»
- [ ] Squash merge в master
- [ ] Тег `v0.1.0-rc1` (release candidate, ещё без backend изменений)

---

## Приоритет 2 — faster-whisper backend (1-2 дня)

**Цель:** убрать зависимость от WhisperX CLI subprocess. Ускорить транскрипцию 2-4×.

### 2.1 Создать структуру asr_backends
- [ ] `scripts/asr_backends/__init__.py` — registry с `BACKENDS`, `list_available_backends()`, `get_backend(name)`
- [ ] `scripts/asr_backends/base.py`:
  - `ASRBackend` ABC
  - `Segment` dataclass (start, end, text, speaker, confidence)
  - `TranscriptionResult` dataclass с canonical schema constants
  - `SCHEMA_VERSION = "1"`
  - Helper `write_canonical_json(result, path)`

### 2.2 FasterWhisperBackend
- [ ] `scripts/asr_backends/faster_whisper_backend.py`:
  - `is_available()`: try import faster_whisper
  - `name = "faster-whisper"`, `display_name`, `default_model = "bzikst/faster-whisper-large-v3-ru-podlodka"`
  - `supported_models = ["bzikst/faster-whisper-large-v3-ru-podlodka", "large-v3", "large-v3-turbo", "large-v2", "medium", "small", "base", "tiny"]`
  - `transcribe()`:
    - `WhisperModel(model_id, device, compute_type)`
    - `model.transcribe(audio, language="ru", beam_size=5, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500))`
    - Iterator → list, фильтр `no_speech_prob > 0.6`, `text.strip()`
    - `confidence = math.exp(s.avg_logprob)` если есть
    - Запись canonical JSON

### 2.3 WhisperXBackend (legacy wrapper)
- [ ] `scripts/asr_backends/whisperx_backend.py`:
  - `is_available()`: shutil.which("whisperx") or import whisperx
  - `transcribe()`: переносит код из `wisper_launcher.py:642-651` один в один
  - Запись canonical JSON (или просто rename полей если WhisperX сам их пишет)

### 2.4 Интеграция в launcher
- [ ] `scripts/wisper_launcher.py`:
  - Импорт registry из `asr_backends`
  - Заменить hardcoded `["whisperx", ...]` subprocess (line ~162, ~642-651) на `get_backend(...)`+`backend.transcribe(...)`
  - Выбор backend пока через config-файл `%LOCALAPPDATA%/.../asr_config.json` (default = "faster-whisper")
  - **GUI не трогаем** — combobox backend будет в Приоритете 5
- [ ] Переименовать `wisper_launcher.py` → `transcriber_launcher.py` (опечатка) — отдельным коммитом, обновить все ссылки

### 2.5 Smoke test (manual)
- [ ] Прогнать на 5-минутном Craig треке через FasterWhisperBackend
- [ ] Проверить что merge_whisperx.py парсит без ошибок
- [ ] A/B сравнение скорости и качества с текущим WhisperX
- [ ] Regression: WhisperXBackend wrapper выдаёт байт-в-байт идентичный merged.txt

### 2.6 Commit + PR
- [ ] PR «P2: faster-whisper backend + ASR abstraction»

---

## Приоритет 3 — Code quality skeleton (1 день)

**Цель:** инфраструктура для безопасных следующих изменений.

### 3.1 pyproject.toml
- [ ] `pyproject.toml` в корне:
  - `[project]` секция: name, version, description, authors, license, python_requires
  - `[project.dependencies]` — runtime deps (faster-whisper, soundfile, librosa)
  - `[project.optional-dependencies]`:
    - `dev` — pytest, pytest-cov, ruff, pre-commit
    - `gigaam` — sherpa-onnx
    - `diarize` — pyannote.audio
    - `whisperx` — git+https whisperx
  - `[project.scripts]` — entry points
  - `[build-system]` — setuptools
- [ ] Удалить (или оставить как legacy) разбросанные `requirements.txt` если они есть

### 3.2 Линтер
- [ ] `[tool.ruff]` секция в pyproject.toml:
  - line-length = 100
  - target-version = "py310"
  - select = ["E", "F", "W", "I", "B", "UP", "SIM"]
- [ ] Прогнать `ruff check --fix .` на существующем коде, зафиксировать отдельным коммитом «P3: ruff autofix»
- [ ] Проверить ничего не сломалось

### 3.3 Pre-commit
- [ ] `.pre-commit-config.yaml`:
  - ruff-pre-commit (lint + format)
  - pre-commit-hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-json, check-merge-conflict)
  - detect-secrets
- [ ] `pre-commit install` локально, проверить что хуки срабатывают

### 3.4 pytest skeleton
- [ ] `tests/__init__.py`
- [ ] `tests/conftest.py` — общие фикстуры (sample audio path, tmp output dir)
- [ ] `tests/fixtures/sample_5sec_ru.flac` — 5-секундный тестовый файл (взять из сессии или сгенерить через TTS)
- [ ] `tests/fixtures/sample_5sec_ru.expected.json` — ожидаемый canonical schema output
- [ ] `tests/test_canonical_schema.py`:
  - Валидация что canonical schema соответствует контракту
  - Tests для `write_canonical_json` helper
- [ ] `tests/asr_backends/test_faster_whisper.py`:
  - Smoke test transcribe() на sample
  - Проверка что output валидный canonical schema
- [ ] `tests/asr_backends/test_whisperx.py`:
  - Regression smoke test (skip if whisperx not installed)

### 3.5 GitHub Actions CI
- [ ] `.github/workflows/ci.yml`:
  - Triggers: pull_request, push to master
  - Matrix: ubuntu-latest + windows-latest, Python 3.10/3.11/3.12
  - Steps: checkout, setup-python, pip install -e .[dev], ruff check, pytest tests/
  - Artifacts: pytest report
- [ ] Branch protection rule на master:
  - Require status checks (CI matrix)
  - Require PR review (если будут контрибьюторы)
  - Dismiss stale reviews

### 3.6 Commit + PR
- [ ] PR «P3: pyproject.toml + ruff + pytest + CI»

---

## Приоритет 4 — GigaAM backend + smoke tests (2-3 дня)

**Цель:** уникальная фича — first-class GigaAM-v3 RNNT с biasing.

### 4.1 SherpaOnnxBackend
- [ ] `scripts/asr_backends/sherpa_onnx_backend.py`:
  - `is_available()`: try import sherpa_onnx
  - `name = "sherpa-onnx"`, `display_name = "sherpa-onnx + GigaAM-v3 (RU only)"`
  - `default_model = "gigaam-v3-rnnt"`
  - `supported_models = ["gigaam-v3-rnnt"]` (v1 — одна модель)
- [ ] Скачивание весов:
  - Helper `_download_gigaam_weights(cache_dir)` через `huggingface_hub.snapshot_download`
  - Repo: `Smirnov75/GigaAM-v3-sherpa-onnx`
  - Cache: `%LOCALAPPDATA%/TTRPG-Session-Transcriber/models/gigaam-v3-rnnt/`

### 4.2 Silero VAD pre-slicing
- [ ] Helper `_load_audio_16k_mono(audio_path)`:
  - Через soundfile/librosa
  - Resample 48k stereo → 16k mono float32
- [ ] Helper `_run_vad(samples, sr)`:
  - `sherpa_onnx.VoiceActivityDetector` с Silero VAD ONNX
  - Параметры: `min_silence_duration=0.5`, `max_speech_duration=20.0`
  - Returns list of (start_sec, end_sec, samples)
- [ ] Скачивание Silero VAD ONNX отдельным шагом (если ещё не в кэше)

### 4.3 Decode loop с hotwords
- [ ] В `transcribe()`:
  - Создать `OfflineRecognizer.from_transducer(...)` с hotwords_file и `decoding_method="modified_beam_search"`
  - For each VAD сегмент: create stream → accept_waveform → decode_stream → result.text.strip()
  - Empty results дроп
  - Запись canonical JSON

### 4.4 Hotwords config
- [ ] `config/pathfinder_ru_hotwords.txt`:
  - Формат `word:boost_score` (boost 1.5-3.0)
  - Имена NPC: Ачакек:3.0, Маэри:3.0, Летте:3.0, Ирваэль:2.5, Лизмагорт:2.5, ...
  - Сеттинг: Голарион:2.0
  - Игровые термины: паладин:2.0, спасбросок:2.0, инициатива:1.5
  - Источник: `skill/session-clean/SKILL.md` словарь ошибок + Transcription_Dictionary.md если доступен

### 4.5 Smoke tests (эмпирические)
- [ ] `scripts/smoke_test_backends.py`:
  - Standalone скрипт
  - Принимает path к Craig треку и opt path к hotwords
  - Прогоняет faster-whisper, sherpa-onnx (если установлен), whisperx (если установлен)
  - Печатает A/B таблицу: time, RAM peak, segment count, sample text
- [ ] Прогнать на реальной 5-минутной сессии Азланти
- [ ] Документировать результаты в `docs/backend-comparison.md`:
  - GigaAM hallucination rate на silent треке
  - faster-whisper `no_speech_prob` оптимальный threshold
  - GigaAM поведение на code-switching («каст Fireball на DC 15»)
  - Punctuation across VAD cuts для GigaAM
- [ ] Решение: оставлять SherpaOnnxBackend в v0.1.0 или отложить до v0.2.0 (по результатам)

### 4.6 Tests
- [ ] `tests/asr_backends/test_sherpa_onnx.py` (skip if not installed)

### 4.7 Commit + PR
- [ ] PR «P4: SherpaOnnxBackend + GigaAM-v3 + hotwords»

---

## Приоритет 5 — GUI и stack decision (3-5 дней)

**Цель:** UX для нетехнических игроков. Финальное решение по PySide6 vs tkinter.

### 5.0 Stack decision (BLOCKING)
- [ ] Принять решение: PySide6 vs tkinter
  - Если PySide6 → задачи 5.1-5.4
  - Если tkinter → задачи 5.5

### 5.1 PySide6 миграция (если выбран Qt)
- [ ] Добавить PySide6 в `[project.dependencies]`
- [ ] Migrate `scripts/transcriber_launcher.py` GUI часть (~700 строк) на Qt:
  - QMainWindow + QWidget layouts
  - QComboBox для backend/model
  - QPushButton, QLineEdit, QTextEdit для логов
  - QThread для фоновой обработки (вместо threading.Thread + queue)
  - Signals/slots вместо queue.Queue + after(100)
- [ ] Migrate `launcher/installer_ui.py` (~420 строк) на Qt
- [ ] Обновить PyInstaller spec:
  - Qt platform plugins (platforms/qwindows.dll)
  - Qt styles
  - imageformats

### 5.2 BackendSelectionDialog (на любом стеке)
- [ ] Новый класс `BackendSelectionDialog` в installer_ui:
  - Title «Select ASR backend and model»
  - Radio group: faster-whisper / sherpa-onnx / whisperx (legacy, hidden если не установлен)
  - QComboBox model, перезаполняется при смене backend
  - Карточка «What you get»: languages, download size, VRAM, biasing support
  - Warning label для GigaAM монолингвальности
  - Кнопка «Continue installation»

### 5.3 Hotwords editor
- [ ] Текстовое поле в GUI launcher для hotwords path
- [ ] File picker для выбора .txt файла
- [ ] Default: `%LOCALAPPDATA%/.../hotwords/pathfinder_ru.txt` если существует

### 5.4 LGPL документация (если PySide6)
- [ ] Добавить упоминание LGPL Qt в LICENSE/NOTICE
- [ ] CONTRIBUTING.md секция «How to swap Qt DLLs»

### 5.5 Tkinter путь (если остаёмся)
- [ ] Combobox backend перед combobox model в `transcriber_launcher.py:325`
- [ ] BackendSelectionDialog как tk.Toplevel с radio + label table
- [ ] Hotwords text field

### 5.6 Installer integration (на любом стеке)
- [ ] `launcher/installer_ui.py:STEPS` — заменить:
  ```python
  STEPS = [
      ("backend",  "Select ASR model"),       # NEW
      ("python",   "Prepare Python runtime"),
      ("pip",      "Install pip"),
      ("pytorch",  "Install PyTorch"),
      ("asr",      "Install ASR backend"),    # was "whisperx"
      ("model",    "Download model"),          # NEW
      ("ffmpeg",   "Download ffmpeg"),
  ]
  ```
- [ ] `launcher/install_logic.py`:
  - `install_asr_backend(python_exe, backend, gpu_mode, on_log, on_progress)` — выбирает packages по backend
  - `download_asr_model(python_exe, backend, model_id, data_dir, on_log, on_progress)` — pre-download через huggingface_hub
  - `STEP_WEIGHTS` пересчитать
- [ ] Запись `asr_config.json` после установки в `data_dir`
- [ ] GUI launcher читает `asr_config.json` при старте как defaults

### 5.7 End-to-end verification
- [ ] Чистая Windows VM → собрать .exe → запустить → BackendSelectionDialog → faster-whisper + podlodka → установка → транскрипция тестового файла → merged.txt
- [ ] Повторить для sherpa-onnx + gigaam-v3
- [ ] (Если PySide6) Linux VM cross-platform validation

### 5.8 Commit + PR
- [ ] PR «P5: backend selection in installer + GUI»
- [ ] Тег `v0.1.0-rc2`

---

## Приоритет 6 — FVTT polish + опц. диаризация (1-2 дня)

**Цель:** забить кол в землю на главном USP. FVTT chat alignment как hero feature.

### 6.1 FVTT alignment UX
- [ ] Явный шаг в GUI «Add Foundry VTT chat log (optional)» с file picker
- [ ] Validation: проверить формат файла, понять что timestamps корректные
- [ ] Error messaging если timestamps не align-ятся (например пользователь дал log от другой сессии)
- [ ] Документировать как экспортировать chat log из FVTT (скриншоты + steps)

### 6.2 parse_fvtt_chat.py polish
- [ ] Refactor для лучшего error reporting
- [ ] Tests `tests/test_parse_fvtt_chat.py`
- [ ] Edge cases: пустой chat log, timestamps до начала записи, timestamps после конца записи

### 6.3 README hero update
- [ ] Записать GIF demo демонстрирующий FVTT alignment
- [ ] Hero-section README обновить с этим GIF

### 6.4 Опциональная диаризация (pyannote)
- [ ] Чекбокс «Enable diarization» в GUI
- [ ] HF token из `%LOCALAPPDATA%/.../diarize_token.txt` или env `HF_TOKEN`
- [ ] Документировать процесс получения токена в FAQ
- [ ] Подчеркнуть в README: для Craig multi-track диаризация **не нужна** — multi-track даёт perfect attribution

### 6.5 Commit + PR
- [ ] PR «P6: FVTT polish + optional diarization»
- [ ] Тег `v0.1.0` (первый full release)

---

## Открытые вопросы (нужны решения от пользователя)

- [ ] Подтвердить лицензию: MIT или Apache-2.0?
- [ ] Подтвердить имя репо: переименовываем в `ttrpg-session-transcriber` или оставляем текущее?
- [ ] Имя автора / copyright holder для LICENSE
- [ ] Email для SECURITY.md
- [ ] Решение по стеку: PySide6 или tkinter (можно отложить до Приоритета 5)
- [ ] Где хранить hotwords-словарь PF2e: только в репо или ещё distribute через installer?
- [ ] Discord/Telegram канал для community — нужен или нет?

---

## Что НЕ в плане (deferred — после v0.1.0)

- Бенчмарк на полной Азланти-сессии (отдельный пост-релиз PR)
- Parakeet / Canary / Voxtral / Qwen3-ASR backend-ы
- Apple Silicon / Linux EXE сборки (только если PySide6)
- Code signing для Windows .exe
- Auto-update mechanism
- Docs site (mkdocs)
- GitHub Sponsors / Discussions
- Hotwords editor в GUI
- src/ layout рефакторинг
- mypy / type checking
- semantic-release / release-please
