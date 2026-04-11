# TTRPG Session Transcriber — Tasks

Чек-лист задач для превращения проекта в полноценный open-source продукт. Архитектура — в `ARCHITECTURE.md`, обоснование ранних решений — в `~/.claude/plans/virtual-wondering-karp.md`.

**Имя проекта:** TTRPG Session Transcriber (`ttrpg-session-transcriber`)
**Лицензия:** MIT
**Текущая ветка:** master

---

## Порядок приоритетов (high-level)

1. **P2 — 6-layer big-bang refactor** (current focus). Миграция всего работающего кода на целевую архитектуру из `ARCHITECTURE.md`. Старый P2 про faster-whisper backend поглощён этим рефактором.
2. **P2.5 — Minimal test infra.** Pytest skeleton + e2e harness, необходимый для gate'а в P2.9. Полный code-quality (ruff, pre-commit, CI matrix) отложен в Deferred.
3. **P3 — GigaAM / sherpa-onnx backend.** Бывший P4. Уникальная фича, первый не-Whisper backend в новом `sources/speech/`.
4. **P4 — Emotions.** Новый слой. Research-first (model selection → source → merger projection → renderer).
5. **P5 — GUI polish.** Backend selector в installer, hotwords editor, решение tkinter vs PySide6.
6. **Deferred** — FVTT polish, pyannote диаризация, полный code quality, release automation.

---

## Приоритет 1 — Open-source hygiene (v0.1.0) — ДОСТИГНУТО ЧАСТИЧНО

Commit `104d550` добавил базовые файлы. Что сделано и что осталось:

### Done
- [x] `LICENSE` (MIT)
- [x] `CHANGELOG.md`
- [x] `SECURITY.md`
- [x] `CODE_OF_CONDUCT.md`
- [x] `CONTRIBUTING.md`
- [x] `.github/ISSUE_TEMPLATE/bug_report.md`
- [x] `.github/ISSUE_TEMPLATE/feature_request.md`
- [x] `.github/ISSUE_TEMPLATE/config.yml`
- [x] `.github/PULL_REQUEST_TEMPLATE.md`

### Открытые пункты (не блокируют P2, можно добить после)
- [ ] README rewrite по 4 USP (см. `project_open_source_positioning.md`):
  - Hero: «The only open-source tool that merges your Foundry VTT chat log into the per-speaker audio transcript timeline»
  - Comparison table vs TASMAS / Scribble / Kazkar / Archivist
  - Quick Start: Download .exe → drop Craig folder → done
  - FAQ (per-track vs diarization, GigaAM, local-only, GPU optional)
  - Русская версия в `docs/README.ru.md`
- [ ] Скриншот installer-а → `docs/screenshots/installer.png`
- [ ] GitHub description + topics (`ttrpg`, `dnd`, `pathfinder`, `transcription`, `whisper`, `discord`, `craig`, `foundry-vtt`, `russian`)
- [ ] Решить: переименовывать репозиторий в `ttrpg-session-transcriber` или оставить

---

## Приоритет 2 — Полный архитектурный рефакторинг на 6 слоёв

**Цель:** ввести целевую архитектуру из `ARCHITECTURE.md` (ui/core/sources/mergers/renderers/domain) в одном приоритете. Отменяет старый план поэтапной миграции (см. ADR-9). Заодно убирает зависимость от WhisperX CLI subprocess и добавляет faster-whisper как default backend.

### Prerequisites
- `ARCHITECTURE.md` актуален и прочитан (секции 3-6 обязательно).
- Решения зафиксированы:
  - **A**: `launcher/bootstrap.py` и `launcher/build.spec` обновляются жёстко в P2 (без shim). Риск поломки installer закрывается ручной проверкой сборки в 2.11.
  - **D**: `EmotionTag` определяется в `domain/annotations.py` в P2, но ни один source его не производит. `ScriptMerger` содержит пустую ветку проекции (вызывается с `emotions=[]`). Контракт закрыт к P4.
  - **Timeline location**: `Timeline` живёт в `domain/timeline.py` (не в `core/`), чтобы соблюсти dependency rule `mergers → domain only`. ARCHITECTURE.md §5.2 обновляется вместе с P2, добавляется ADR-12.
- Создана отдельная ветка `feature/p2-six-layer-refactor`.

### Правила работы
- Каждая подзадача = один логический коммит с working сборкой.
- После каждого коммита текущие smoke-тесты (если есть) остаются зелёными.
- Ревью идёт по коммитам, не по общему diff'у.
- Squash merge запрещён — каждый коммит остаётся в истории.

---

### 2.1 Scaffolding шести папок
- [ ] `domain/__init__.py` (docstring про pure layer)
- [ ] `core/__init__.py`
- [ ] `sources/__init__.py`
- [ ] `sources/speech/__init__.py`
- [ ] `sources/game_log/__init__.py`
- [ ] `mergers/__init__.py`
- [ ] `renderers/__init__.py`
- [ ] `ui/__init__.py`
- [ ] Проверить: `python -c "import domain, core, sources, mergers, renderers, ui"` из корня работает
- [ ] Коммит: `refactor(p2): scaffold six-layer package structure`

### 2.2 Domain layer — pure dataclass-ы, speaker_map, Timeline

Никаких импортов внутри проекта. Только stdlib + typing.

- [ ] `domain/annotations.py`:
  - `SpeechSegment` (start, end, speaker: str|None, text, confidence: float|None = None)
  - `EmotionTag` (start, end, label, confidence) — определяется, не производится в P2
  - `ChatMessage` (at, channel: str, author, text)
  - `GameLogEntry` (at, actor, action: str, detail) — определяется, не производится в P2
  - `Annotation = SpeechSegment | EmotionTag | ChatMessage | GameLogEntry`
- [ ] `domain/events.py`:
  - `SpeechEvent` (start, end, speaker, text, emotion: str|None = None, parallel_group: int|None = None)
  - `ChatEvent` (at, channel: Literal["ic","ooc"], author, text)
  - `GameEvent` (at, actor, action: Literal["roll","damage","spell"], detail)
  - `ScriptEvent = SpeechEvent | ChatEvent | GameEvent`
- [ ] `domain/timeline.py`:
  - `@dataclass Timeline` с полями `speech, emotions, chat, game_log` (см. ARCHITECTURE.md §5.2 после обновления)
- [ ] `domain/speaker_map.py`:
  - `load_speaker_map(session_dir: Path) -> dict[str, str]` — port из `scripts/merge_whisperx.py:load_speaker_map` и `scripts/wisper_launcher.py:_find_speaker_map/_load_speaker_map`
  - `resolve_speaker(track_stem: str, speaker_map: dict[str, str]) -> str` — port из `merge_whisperx.speaker_label`
- [ ] Grep-проверить: в `domain/` нет импортов из `core/sources/mergers/renderers/ui/`
- [ ] Обновить `ARCHITECTURE.md` §5.2 (Timeline → domain) и добавить ADR-12
- [ ] Коммит: `feat(domain): add annotations, events, timeline, speaker_map pure layer`

### 2.3 Sources layer — base ABC, registry, speech/game_log реализации

Импортирует **только** `domain/`.

#### 2.3.1 Sources base + registry
- [ ] `sources/base.py`:
  - `class Source(ABC)` с `name: str` и `@abstractmethod extract(session_dir: Path) -> list[Annotation]`
- [ ] `sources/__init__.py`:
  - `SPEECH_SOURCES: dict[str, type[Source]]` (2 элемента в P2)
  - `GAME_LOG_SOURCES: dict[str, type[Source]]` (1 элемент)
  - Функции `get_speech_source(name)`, `list_speech_sources()`, `get_game_log_source(name)`
  - Без entry_points discovery (ADR-11)

#### 2.3.2 Speech sources
- [ ] `sources/speech/faster_whisper.py`:
  - `class FasterWhisperSource(Source)`, `name = "faster-whisper"`
  - `__init__(model="bzikst/faster-whisper-large-v3-ru-podlodka", device="cuda", compute_type="float16", language="ru", speaker_map: dict | None = None)`
  - `extract()`: находит аудио в `session_dir`, грузит `WhisperModel`, transcribe с `beam_size=5, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500)`, фильтр `no_speech_prob > 0.6`, возвращает `list[SpeechSegment]` для всех треков. `speaker` заполняется через `resolve_speaker(track_stem, speaker_map)`
  - Побочный эффект: пишет canonical JSON в `session_dir/transcripts/<track_stem>.json` (только `start/end/text/source_engine/schema_version` — ADR-8). Артефакт для дебага, merger читает in-memory
  - Helper `_write_canonical_json(segments, path, source_engine)`
- [ ] `sources/speech/whisperx.py`:
  - `class WhisperXSource(Source)`, `name = "whisperx"`
  - Обёртка текущего subprocess вызова из `wisper_launcher.py:642-651`
  - После subprocess читает JSON, конвертирует в `list[SpeechSegment]`
  - Пишет тот же canonical JSON формат рядом

#### 2.3.3 Game log source
- [ ] `sources/game_log/fvtt_chat.py`:
  - `class FvttChatSource(Source)`, `name = "fvtt-chat"`
  - `__init__(chat_log_path: Path, info_file_path: Path|None = None, tz_offset: float|None = None)`
  - `extract(session_dir)`: port логики из `scripts/parse_fvtt_chat.py` (`parse_fvtt_log`, `parse_info_start_time`, `guess_tz_offset`, `chat_to_segments`), результат — `list[ChatMessage]`
  - Helper `_to_chat_message(entry: dict) -> ChatMessage` (channel ic/ooc)

- [ ] Регистрация в `sources/__init__.py`
- [ ] Grep-проверить: в `sources/` нет импортов из `core/mergers/renderers/ui/`
- [ ] Коммит: `feat(sources): add Source ABC, FasterWhisper/WhisperX/FvttChat implementations`

### 2.4 Mergers layer — base ABC + ScriptMerger

Импортирует **только** `domain/`.

- [ ] `mergers/base.py`:
  - `class Merger(ABC)`, `name: str`, `@abstractmethod merge(timeline: Timeline) -> list[ScriptEvent]`
- [ ] `mergers/script_merger.py`:
  - `class ScriptMerger(Merger)`, `name = "script"`
  - `__init__(merge_gap_sec: float = DEFAULT_MERGE_GAP_SEC, exclude_prefixes: tuple[str,...] = ())`
  - `merge(timeline)`:
    - Port `merge_adjacent()` из `merge_whisperx.py:81` для speech (на `SpeechSegment`, не dict)
    - → `list[SpeechEvent]` с `parallel_group=None` (overlap в P2 не решается)
    - Проекция `EmotionTag` на пересекающиеся `SpeechEvent` → поле `emotion` (в P2 ветка с пустым списком)
    - Интерливинг `ChatMessage` → `ChatEvent` между speech (port из `merge_whisperx.main`, строки ~110-168)
    - Интерливинг `GameLogEntry` → `GameEvent` (в P2 пустой список)
    - Сортировка по времени (speech use start, chat/game use at)
  - **Pure функция**: никаких обращений к диску, никакого чтения `speaker_map.json` (speaker уже разрезолвлен source-ом)
- [ ] `mergers/__init__.py`: `MERGERS = {"script": ScriptMerger}`, `get_merger(name)`, `list_mergers()`
- [ ] Placeholder smoke-test `tests/mergers/test_script_merger_smoke.py` (минимальный, без pytest framework — просто `if __name__ == "__main__"`)
- [ ] Grep-проверить: в `mergers/` нет импортов из `core/sources/renderers/ui/`
- [ ] Коммит: `feat(mergers): add Merger ABC and ScriptMerger`

### 2.5 Renderers layer — base ABC + PlainTextRenderer

Импортирует **только** `domain/`.

- [ ] `renderers/base.py`:
  - `class Renderer(ABC)`, `name: str`, `@abstractmethod render(events: list[ScriptEvent]) -> bytes`
- [ ] `renderers/plain_text.py`:
  - `class PlainTextRenderer(Renderer)`, `name = "plain-text"`
  - `render()`: `match event: case SpeechEvent: ... case ChatEvent: ... case GameEvent: ...`
  - Формат **байт-в-байт** эквивалентен текущему `merged.txt` (см. строки в `merge_whisperx.main`)
  - Helper `_format_time(sec: float) -> str` — port из `merge_whisperx.fmt_time`
  - Returns `result.encode("utf-8")`
- [ ] `renderers/__init__.py`: `RENDERERS = {"plain-text": PlainTextRenderer}`
- [ ] Grep-проверить: в `renderers/` нет импортов из `core/sources/mergers/ui/`
- [ ] Коммит: `feat(renderers): add Renderer ABC and PlainTextRenderer`

### 2.6 Core layer — cache, discovery, gpu_check, pipeline

Импортирует `domain`, `sources`, `mergers`, `renderers`. **НЕ** импортирует `ui/`.

#### 2.6.1 Cache decorators (`core/cache.py`)
- [ ] `class DiskCachedSource(Source)`:
  - Wraps `Source`, cache в `session_dir/_cache/sources/<source.name>.json`
  - Инвалидация: hash(config + input file mtimes)
  - Формат кэша — internal, сериализация `list[Annotation]` в JSON
- [ ] `class DiskCachedMerger(Merger)`:
  - Wraps `Merger`, cache в `session_dir/_cache/mergers/<merger.name>.json`
  - В P2 **определяется, не применяется** (ScriptMerger дешёвый). Тесты отложены до P6
- [ ] Helpers `_compute_config_hash(obj) -> str`, `_compute_input_hash(paths) -> str`

#### 2.6.2 Discovery и GPU
- [ ] `core/discovery.py`:
  - `discover_session_dirs(root: Path) -> list[Path]` (port из `wisper_launcher._scan_audio_files` + обёртка)
  - `scan_audio_files(session_dir: Path, pattern="*.flac") -> list[Path]`
- [ ] `core/gpu_check.py`:
  - `detect_gpu() -> dict` (port из `_detect_gpu`)
  - `format_gpu_status(info) -> tuple[str, str]` (port из `_format_gpu_status`)
  - `quick_cuda_test() -> tuple[bool, str]` (port из `_quick_cuda_test`)

#### 2.6.3 Pipeline orchestrator (`core/pipeline.py`)
- [ ] `@dataclass PipelineParams`:
  - `session_dir: Path`
  - `speech_source_name: str = "faster-whisper"`
  - `speech_source_config: dict`
  - `fvtt_chat_log: Path | None = None`
  - `renderer_name: str = "plain-text"`
  - `use_cache: bool = True`
  - `output_path: Path | None = None`
- [ ] `def run(params: PipelineParams) -> Path`:
  1. `speaker_map = load_speaker_map(params.session_dir)`
  2. `source_cls = get_speech_source(params.speech_source_name)`; `source = source_cls(**params.speech_source_config, speaker_map=speaker_map)`
  3. If `use_cache`: `source = DiskCachedSource(source, cache_dir=...)`
  4. `speech_segments = source.extract(params.session_dir)`
  5. Если `fvtt_chat_log`: `chat_messages = FvttChatSource(...).extract(params.session_dir)`, иначе `[]`
  6. `timeline = Timeline(speech=speech_segments, emotions=[], chat=chat_messages, game_log=[])`
  7. `events = ScriptMerger().merge(timeline)`
  8. `output_bytes = PlainTextRenderer().render(events)`
  9. Запись в `params.output_path or session_dir / "merged.txt"`
  10. Return путь
- [ ] `def run_batch(root: Path, params_template: PipelineParams) -> list[Path]` — цикл из `wisper_launcher.main`
- [ ] Grep-проверить: в `core/` нет импортов `ui/` и нет tkinter/PySide6
- [ ] Коммит: `feat(core): add cache, discovery, gpu_check, pipeline orchestrator`

### 2.7 UI layer — CLI и GUI

Импортирует **только** `core/`.

- [ ] `ui/cli.py`:
  - `main() -> int` — port argparse из `wisper_launcher.main` (строки ~112-234)
  - Строит `PipelineParams`, вызывает `core.pipeline.run()` или `run_batch()`
  - Никакой orchestration логики — всё в core
- [ ] `ui/gui.py`:
  - `gui_main() -> int` — port tkinter из `wisper_launcher.gui_main` (строки ~301-1003)
  - Сохранение текущего поведения: dark theme, combobox model, прогресс, логи
  - Worker thread вызывает `core.pipeline.run()`, прогресс через queue
  - **НЕ добавляет** combobox backend (задача P5)
  - Default `speech_source_name = "faster-whisper"`
- [ ] Grep-проверить: в `ui/` нет импортов `sources/mergers/renderers`
- [ ] Коммит: `feat(ui): add cli and gui layers backed by core.pipeline`

### 2.8 Launcher/bootstrap update (жёстко, без shim)

- [ ] `launcher/bootstrap.py`:
  - Путь `DATA_DIR / "scripts" / "wisper_launcher.py"` → `DATA_DIR / "ui" / "gui.py"` (или новая entry-point функция)
  - `_extract_scripts()`: извлекать папки `ui/ core/ sources/ mergers/ renderers/ domain/ prompts/` вместо `scripts/`
- [ ] `launcher/build.spec`:
  - Заменить `(os.path.join(project_root, 'scripts', '*.py'), 'scripts')` на шесть tuple-ов по одному на папку
  - Hidden imports если PyInstaller не найдёт dynamic imports
- [ ] **Обязательно**: собрать .exe локально (или отложить в 2.11 smoke). Без проверки installer может сломаться молча
- [ ] Коммит: `build(launcher): update bootstrap and build.spec for six-layer layout`

### 2.9 E2E эквивалентность с legacy — GATE

**Критично: без green gate нельзя переходить к 2.10 (удаление legacy).**

- [ ] Fixture `tests/fixtures/e2e_p2/`:
  - Короткий Craig session (5-10 сек per track, 2-3 speaker)
  - `speaker_map.json`
  - FVTT chat log
  - `expected_merged.txt` — сгенерить **до** начала удаления legacy через текущий `scripts/wisper_launcher.py` (WhisperX), закоммитить
- [ ] `tests/e2e/test_p2_equivalence.py` (standalone):
  - Запускает `core.pipeline.run(PipelineParams(..., speech_source_name="whisperx", use_cache=False))`
  - Сравнивает байт-в-байт с `expected_merged.txt`
- [ ] Прогон с `speech_source_name="faster-whisper"`:
  - Байт-эквивалентность **не** требуется (другая модель)
  - Требуется: non-empty output, parseable формат, все speaker-ы присутствуют
- [ ] Зафиксировать результаты обоих прогонов в PR description
- [ ] Коммит: `test(e2e): add p2 equivalence harness against legacy merged.txt`

### 2.10 Удаление legacy кода

**Только после green 2.9.**

- [ ] Удалить `scripts/wisper_launcher.py`
- [ ] Удалить `scripts/merge_whisperx.py`
- [ ] Удалить `scripts/parse_fvtt_chat.py`
- [ ] **НЕ удалять** `scripts/chunk_text.py` (остаётся post-processing утилитой)
- [ ] Обновить упоминания в `README.md`, `CONTRIBUTING.md`
- [ ] `CHANGELOG.md` под `## [Unreleased]`:
  - `### Changed` — «Project restructured into six layers (ui, core, sources, mergers, renderers, domain). See ARCHITECTURE.md.»
  - `### Added` — «faster-whisper backend as default speech source (2-4× faster than WhisperX).»
  - `### Removed` — «scripts/wisper_launcher.py, merge_whisperx.py, parse_fvtt_chat.py (migrated to layered structure).»
- [ ] Коммит: `refactor(p2)!: remove legacy scripts, six-layer migration complete`

### 2.11 Manual smoke test на реальной сессии

- [ ] `ui/cli.py` на 5-минутной Craig сессии с FasterWhisperSource
- [ ] `ui/gui.py` на том же файле (GUI regression)
- [ ] С `--fvtt-chat-log` параметром: chat interleaved в output
- [ ] Batch на директории с 2-3 session_dir
- [ ] `_cache/sources/` создаётся, второй прогон значительно быстрее
- [ ] Удалить `_cache/`, повторить — пересчитывает
- [ ] **Сборка installer .exe** (если не сделано в 2.8) — запуск, BackendSelectionDialog пока legacy, транскрипция тестового файла

### 2.12 PR и merge
- [ ] Открыть PR `P2: six-layer refactor + faster-whisper backend`:
  - Ссылка на `ARCHITECTURE.md` и ADR-9
  - Результаты 2.9 (e2e эквивалентность)
  - Результаты 2.11 (manual smoke)
  - Список удалённых файлов
- [ ] Self-review каждого коммита 2.1 → 2.10
- [ ] Merge с сохранением коммитов (**без** squash)
- [ ] Tag `v0.2.0-rc1`

---

## Приоритет 2.5 — Minimal test infra

**Цель:** pytest skeleton + fixture для e2e gate в P2.9. Полный code quality (ruff, pre-commit, CI matrix) — в Deferred.

### 2.5.1 pyproject.toml (минимальный)
- [ ] `pyproject.toml` в корне:
  - `[project]` — name, version, description, authors, license, python_requires
  - `[project.optional-dependencies.dev]` — pytest, pytest-cov
  - `[build-system]` — setuptools

### 2.5.2 pytest skeleton
- [ ] `tests/__init__.py`
- [ ] `tests/conftest.py` — общие фикстуры (sample audio path, tmp output dir)
- [ ] `tests/fixtures/e2e_p2/` (используется в P2.9)
- [ ] `tests/domain/test_speaker_map.py` — unit-тесты pure функций
- [ ] `tests/mergers/test_script_merger.py` — in-memory Timeline → ScriptEvent list
- [ ] `tests/renderers/test_plain_text.py` — snapshot test формата

### 2.5.3 Коммит
- [ ] PR `P2.5: minimal pytest infra`

---

## Приоритет 3 — GigaAM / sherpa-onnx backend

**Цель:** уникальная фича — first-class GigaAM-v3 RNNT с hotwords biasing. Первый не-Whisper backend в `sources/speech/`.

### 3.1 SherpaOnnxSource
- [ ] `sources/speech/sherpa_onnx.py`:
  - `class SherpaOnnxSource(Source)`, `name = "sherpa-onnx"`
  - `__init__(model="gigaam-v3-rnnt", hotwords_path: Path|None = None, speaker_map: dict|None = None)`
  - Регистрация в `sources/__init__.py`: `SPEECH_SOURCES["sherpa-onnx"] = SherpaOnnxSource`

### 3.2 Скачивание весов
- [ ] Helper `_download_gigaam_weights(cache_dir)` через `huggingface_hub.snapshot_download`
- [ ] Repo: `Smirnov75/GigaAM-v3-sherpa-onnx`
- [ ] Cache: `%LOCALAPPDATA%/TTRPG-Session-Transcriber/models/gigaam-v3-rnnt/`

### 3.3 Silero VAD pre-slicing
- [ ] `_load_audio_16k_mono(audio_path)` — resample 48k stereo → 16k mono float32
- [ ] `_run_vad(samples, sr)` — `sherpa_onnx.VoiceActivityDetector` с Silero VAD ONNX, `min_silence_duration=0.5`, `max_speech_duration=20.0`
- [ ] Скачивание Silero VAD ONNX отдельным шагом

### 3.4 Decode loop с hotwords
- [ ] `OfflineRecognizer.from_transducer(...)` с `hotwords_file` и `decoding_method="modified_beam_search"`
- [ ] For each VAD сегмент: create stream → accept_waveform → decode_stream → result.text.strip()
- [ ] Empty results дроп, collect в `list[SpeechSegment]`

### 3.5 Hotwords config
- [ ] `config/pathfinder_ru_hotwords.txt`:
  - Формат `word:boost_score` (boost 1.5-3.0)
  - Имена NPC: Ачакек:3.0, Маэри:3.0, Летте:3.0, Ирваэль:2.5, Лизмагорт:2.5, ...
  - Сеттинг: Голарион:2.0
  - Термины: паладин:2.0, спасбросок:2.0, инициатива:1.5
  - Источник: `skill/session-clean/SKILL.md` + `Transcription_Dictionary.md` если доступен

### 3.6 Smoke tests (эмпирические)
- [ ] `scripts/smoke_test_backends.py`:
  - Standalone, принимает path к Craig треку + opt hotwords
  - Прогоняет все зарегистрированные speech sources
  - A/B таблица: time, RAM peak, segment count, sample text
- [ ] Прогнать на реальной 5-минутной сессии Азланти
- [ ] `docs/backend-comparison.md`:
  - GigaAM hallucination rate на silent треке
  - faster-whisper `no_speech_prob` оптимальный threshold
  - GigaAM на code-switching («каст Fireball на DC 15»)
  - Punctuation across VAD cuts
- [ ] Решение: оставлять SherpaOnnxSource в v0.2.0 или отложить

### 3.7 Tests
- [ ] `tests/sources/test_sherpa_onnx.py` (skip if not installed)

### 3.8 PR
- [ ] PR `P3: SherpaOnnxSource + GigaAM-v3 + hotwords`

---

## Приоритет 4 — Emotions

**Цель:** добавить извлечение эмоций как equal-class аннотацию. Merger уже умеет проецировать `EmotionTag` на `SpeechEvent.emotion` (сделано в P2 как пустая ветка) — в P4 только добавляется source и конкретная модель.

### 4.0 Research (BLOCKING, до кодинга)
- [ ] Запросить у `ml-specialist` обзор моделей:
  - CrisperWhisper (emotion + transcription в одном)
  - Wav2Vec2-based emotion classifiers (superb/wav2vec2-base-superb-er и аналоги)
  - Audio-specific: opensmile features + classifier
  - Мультимодальные (audio + text) — дороже
- [ ] Критерии выбора:
  - Работа на русском (или language-agnostic acoustic features)
  - Inference time (должно быть < ASR)
  - Набор эмоций (минимум: neutral/angry/happy/sad/surprised/fear)
  - Лицензия (совместимая с MIT)
  - CPU/GPU модели
- [ ] Решение по модели + зафиксировать в `docs/emotion-model-rationale.md`
- [ ] Решение по формату `EmotionTag.label` (canonical set or free text)

### 4.1 EmotionSource implementation
- [ ] `sources/emotion/__init__.py`
- [ ] `sources/emotion/<chosen_model>.py`:
  - `class <Name>EmotionSource(Source)`, реализует `extract() -> list[EmotionTag]`
  - Chunking стратегия: скользящее окно или per VAD-сегмент
  - Confidence threshold
- [ ] Регистрация: новый registry `EMOTION_SOURCES` в `sources/__init__.py`
- [ ] `core/pipeline.py`: добавить `emotion_source_name: str | None = None` в `PipelineParams`, если задан — extract и положить в `Timeline.emotions`

### 4.2 Merger projection (уже есть branch из P2)
- [ ] Убедиться что `ScriptMerger` корректно проецирует EmotionTag на пересекающиеся SpeechEvent
- [ ] Edge case: эмоция меняется в середине фразы — разбивать SpeechEvent на два (ADR-3)
- [ ] Unit-тесты на проекцию с синтетическими fixture-ами

### 4.3 Renderer update
- [ ] `renderers/plain_text.py`: если `event.emotion is not None` — выводить рядом с репликой (формат: `[00:04-00:06] Alice [angry]: текст`)
- [ ] Snapshot test обновить

### 4.4 Smoke test
- [ ] Прогнать на реальной сессии Азланти
- [ ] Субъективная оценка: насколько эмоции совпадают с ожидаемыми в эмоциональных моментах

### 4.5 PR
- [ ] PR `P4: emotion source + merger projection + renderer update`

---

## Приоритет 5 — GUI polish

**Цель:** UX для нетехнических игроков. Backend selector, hotwords editor, финальное решение tkinter vs PySide6.

### 5.0 Stack decision (BLOCKING)
- [ ] Принять решение: PySide6 vs tkinter
  - Если PySide6 → задачи 5.1-5.4
  - Если tkinter → задачи 5.5

### 5.1 PySide6 миграция (если выбран Qt)
- [ ] Добавить PySide6 в `[project.dependencies]`
- [ ] Migrate `ui/gui.py` (~700 строк) на Qt:
  - QMainWindow + QWidget layouts
  - QComboBox для backend/model
  - QPushButton, QLineEdit, QTextEdit
  - QThread для фоновой обработки (вместо threading.Thread + queue)
  - Signals/slots вместо queue + `after(100)`
- [ ] Migrate `launcher/installer_ui.py` (~420 строк) на Qt
- [ ] PyInstaller spec: Qt platform plugins, styles, imageformats

### 5.2 BackendSelectionDialog
- [ ] Новый класс `BackendSelectionDialog` в installer_ui:
  - Title «Select ASR backend and model»
  - Radio group: faster-whisper / sherpa-onnx / whisperx (legacy, hidden если не установлен)
  - QComboBox model, перезаполняется при смене backend (читает `list_speech_sources()` + `supported_models`)
  - Карточка «What you get»: languages, download size, VRAM, biasing support, emotion support
  - Warning label для GigaAM монолингвальности
  - Кнопка «Continue installation»

### 5.3 Hotwords editor
- [ ] Текстовое поле в GUI launcher для hotwords path
- [ ] File picker для выбора .txt
- [ ] Default: `%LOCALAPPDATA%/.../hotwords/pathfinder_ru.txt`

### 5.4 LGPL документация (если PySide6)
- [ ] Упоминание LGPL Qt в LICENSE/NOTICE
- [ ] CONTRIBUTING.md секция «How to swap Qt DLLs»

### 5.5 Tkinter путь (если остаёмся)
- [ ] Combobox backend перед combobox model в `ui/gui.py`
- [ ] BackendSelectionDialog как tk.Toplevel с radio + label table
- [ ] Hotwords text field

### 5.6 Installer integration
- [ ] `launcher/installer_ui.py:STEPS`:
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
  - `install_asr_backend(python_exe, backend, gpu_mode, on_log, on_progress)`
  - `download_asr_model(python_exe, backend, model_id, data_dir, on_log, on_progress)`
  - `STEP_WEIGHTS` пересчитать
- [ ] Запись `asr_config.json` после установки в `data_dir`
- [ ] GUI launcher читает `asr_config.json` при старте как defaults

### 5.7 End-to-end verification
- [ ] Чистая Windows VM → .exe → BackendSelectionDialog → faster-whisper + podlodka → установка → транскрипция → merged.txt
- [ ] Повторить для sherpa-onnx + gigaam-v3
- [ ] (Если PySide6) Linux VM cross-platform validation

### 5.8 PR
- [ ] PR `P5: backend selection in installer + GUI polish`
- [ ] Tag `v0.2.0-rc2`

---

## Открытые вопросы (нужны решения)

- [ ] Подтвердить имя репо: переименовываем в `ttrpg-session-transcriber` или оставляем?
- [ ] Стек GUI: PySide6 или tkinter (решение в P5.0)
- [ ] Где хранить hotwords-словарь PF2e: только в репо или distribute через installer?
- [ ] Discord/Telegram канал для community — нужен?
- [ ] Модель эмоций (решение в P4.0)

---

## Deferred (после v0.2.0)

- **Code quality infrastructure**: ruff, pre-commit, detect-secrets, GitHub Actions CI matrix (ubuntu + windows × py 3.10/3.11/3.12), branch protection rules. Текущий P2.5 закрывает только pytest skeleton — остальное отложено чтобы не тормозить рефакторинг.
- **FVTT polish**: GIF demo, явный шаг «Add Foundry VTT chat log» в GUI, validation timestamps, error messaging, edge case tests для `parse_fvtt_chat`.
- **Опциональная диаризация**: pyannote чекбокс в GUI, HF token handling, документация процесса получения токена.
- **Бенчмарк** на полной Азланти-сессии
- **Parakeet / Canary / Voxtral / Qwen3-ASR** backend-ы
- **Apple Silicon / Linux EXE** сборки (только если PySide6)
- **Code signing** для Windows .exe
- **Auto-update** mechanism
- **Docs site** (mkdocs)
- **GitHub Sponsors / Discussions**
- **Hotwords editor** в GUI (расширение 5.3)
- **src/ layout** рефакторинг (если пойдём на PyPI)
- **mypy / type checking**
- **semantic-release / release-please**
