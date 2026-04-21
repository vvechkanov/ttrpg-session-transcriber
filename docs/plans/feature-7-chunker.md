# План реализации Feature #7 — Chunker integration + UI settings

## 1. Цель и scope

- **In scope (MVP):** опциональный post-step в `core.pipeline.run()` после рендера, который режет `merged.txt` на перекрывающиеся чанки и кладёт их рядом в `chunks/`. Настройки (enabled / chunk_chars / overlap_ratio) живут в `AppPreferences` + SettingsScreen. `PipelineController` пробрасывает их через `PipelineParams`. На Done-фазе опциональный `OutputChip` показывает путь к `chunks/`.
- **In scope (контракт):** фrozen dataclass `ChunkingOptions` в `core/chunking.py`, поле `chunking: ChunkingOptions | None = None` в `PipelineParams`. Новая стадия `"chunk"` в `PipelineStage`.
- **Out of scope:** per-session override параметров чанкера (ставим в будущем рядом с per-track ASR override из #9); token-based splitting (только символы); progress-bar внутри стадии `"chunk"` (стадия единая, event-level gran); отдельный экран для просмотра чанков; автогенерация LLM-промптов из чанков.
- **Совместимость:** 0 breaking для Python API. CLI `scripts/chunk_text.py` не трогается. CLI-флаги `--chunk`, `--chunk_chars`, `--chunk_overlap` в `ui/cli.py` остаются как есть (независимый пост-вызов, прямой путь в `chunk_text_file`). Ломается только тест на литерал `PipelineStage` — обновить.
- **Invariant:** если `params.chunking is None` или `params.chunking.enabled is False`, стадия `"chunk"` не эмитится вообще (7 стадий только когда реально работаем).

## 2. Контракт `ChunkingOptions`

Разместить рядом с `chunk_text_file` в `core/chunking.py`:

```python
@dataclass(frozen=True)
class ChunkingOptions:
    """Post-render chunking knobs, forwarded from UI preferences."""
    enabled: bool = False
    chunk_chars: int = 40_000
    overlap_ratio: float = 0.20
```

Defaults совпадают с текущими defaults `chunk_text_file(chunk_chars=40_000, overlap_ratio=0.20)`. Клэмп `overlap_ratio` в `[0, 0.5]` остаётся внутри `chunk_text_file` (не дублируем в dataclass — пусть core сам защищает границу).

## 3. Этап 7A — core contract + pipeline stage

### 3.1 `core/chunking.py`

- Добавить `ChunkingOptions` (см. §2).
- `chunk_text_file(...)` **не меняется** по сигнатуре — остаётся с kwargs `chunk_chars`, `overlap_ratio`, `out_dir`. Нет смысла переделывать под options: это pure-функция, её и CLI (`scripts/chunk_text.py`), и новый pipeline-call могут звать одинаково. YAGNI.
- В pipeline мы распаковываем `ChunkingOptions` прямо в kwargs вызова — без тонких wrapper'ов.

### 3.2 `core/pipeline.py`

Изменения:

- Импорт: `from core.chunking import ChunkingOptions, chunk_text_file`.
- `PipelineStage` литерал расширяется:
  ```python
  PipelineStage = Literal["start", "speech", "chat", "merge", "render", "chunk", "done"]
  ```
  Порядок: `chunk` строго между `render` и `done`.
- `PipelineParams` получает новое поле:
  ```python
  chunking: ChunkingOptions | None = None
  ```
  В конце dataclass, с default `None` — существующие вызовы не ломаются.
- `run()` после записи `output_path.write_bytes(payload)` и до финального `stage_cb("done", ...)`:
  ```python
  if params.chunking is not None and params.chunking.enabled:
      stage_cb("chunk", f"{params.chunking.chunk_chars}ch/{params.chunking.overlap_ratio:.2f}")
      try:
          chunks_dir = chunk_text_file(
              output_path,
              chunk_chars=params.chunking.chunk_chars,
              overlap_ratio=params.chunking.overlap_ratio,
          )
          logger.info("Wrote chunks to %s", chunks_dir)
      except (FileNotFoundError, ValueError):
          logger.exception("Chunking post-step failed for %s", output_path)
          # Не валим весь pipeline — merged.txt уже записан.
  stage_cb("done", str(output_path))
  ```
  Сообщение `"done"` оставляем тем же (путь к `merged.txt`) — ломать формат нельзя, тест на него (`test_done_message_is_output_path`) жёсткий. Путь к `chunks/` в `done` не проносим.
- Output path convention: `chunks_dir` = `session_dir/chunks/` по умолчанию (поведение `chunk_text_file` уже такое, мы не передаём `out_dir`).

### 3.3 Тесты (core)

- `tests/test_pipeline_stage_callback.py` (строки 81-88): расширить ожидаемую последовательность? **Нет** — оставить как есть, потому что по умолчанию `params.chunking is None` и стадия `"chunk"` не эмитится. Тест зелёный без правки.
- Добавить новый тест в тот же файл (или отдельный):
  - `test_chunk_stage_emitted_when_enabled`: `PipelineParams(..., chunking=ChunkingOptions(enabled=True))`, мокнуть `chunk_text_file`, проверить что stages = `[start, speech, chat, merge, render, chunk, done]`.
  - `test_chunk_stage_skipped_when_disabled`: `enabled=False` → стадия `chunk` не в списке.
  - `test_chunk_failure_does_not_break_pipeline`: `chunk_text_file` бросает `ValueError` → `stage_cb("done", ...)` всё равно вызывается, `run()` не перепробрасывает.
- `tests/test_core_pipeline_kwargs.py::TestPipelineParamsDefaults`: добавить `test_default_chunking_is_none` (assert `p.chunking is None`).
- Новый `tests/test_core_chunking_options.py`: round-trip ChunkingOptions (frozen, defaults).

## 4. Этап 7B — preferences + QSettings

### 4.1 `ui/models/app_preferences.py`

Три новых Q_PROPERTY — по шаблону `asrDevice` / `asrBeamSize`:

| Python field | Q_PROPERTY | QSettings key | Default | Type exposed to QML |
|---|---|---|---|---|
| `_chunking_enabled` | `chunkingEnabled` | `chunking/enabled` | `False` | `bool` |
| `_chunking_chunk_chars` | `chunkingChunkChars` | `chunking/chunk_chars` | `"40000"` | `str` (TextInputField не round-trip'ит int) |
| `_chunking_overlap_ratio` | `chunkingOverlapRatio` | `chunking/overlap_ratio` | `"0.20"` | `str` (as above) |

Три новых Signal: `chunkingEnabledChanged`, `chunkingChunkCharsChanged`, `chunkingOverlapRatioChanged`.

Загрузка в `__init__` — по образцу `_asr_num_threads`. Для bool — через `_to_bool(self._settings.value("chunking/enabled", False))`.

Добавить `build_chunking_options()` method рядом с `build_asr_options()`:

```python
def build_chunking_options(self) -> ChunkingOptions:
    def _to_int(raw, fb): ...  # reuse pattern
    def _to_float(raw, fb):
        try: return float(raw)
        except ValueError: return fb
    return ChunkingOptions(
        enabled=self._chunking_enabled,
        chunk_chars=_to_int(self._chunking_chunk_chars, 40_000),
        overlap_ratio=_to_float(self._chunking_overlap_ratio, 0.20),
    )
```

Импорт: `from core.chunking import ChunkingOptions`.

Обновить docstring в начале файла: раздел "Keys grouped by section" — добавить `chunking/*` три ключа.

### 4.2 Тесты (prefs)

- `tests/ui_qml_smoke/test_app_preferences.py`: добавить строки для chunking-полей:
  - defaults: `chunkingEnabled is False`, `chunkingChunkChars == "40000"`, `chunkingOverlapRatio == "0.20"`.
  - mutate: `True`, `"60000"`, `"0.35"`.
  - создать второй `AppPreferences()` → значения сохранились.
  - `build_chunking_options()` возвращает правильно типизированный `ChunkingOptions`.

## 5. Этап 7C — QML Settings UI + DoneSummary chip

### 5.1 Новый SettingsGroup в `ui/qml/screens/SettingsScreen.qml`

Разместить **после** ASR-группы (строки 93-233), до "Мержер по умолчанию" (строка 236). Заголовок "Чанки для LLM", description "Резать `merged.txt` на перекрывающиеся куски для последующей обработки в LLM (summary, редактура). Границы — по параграфам.".

Структура:

1. Первая строка — `CheckRow` (есть в `ui/qml/controls/CheckRow.qml`): "Резать merged.txt на чанки после рендера", `checked: preferences.chunkingEnabled`, `onCheckedChanged: preferences.chunkingEnabled = checked`.
2. Вторая строка — `RowLayout` с двумя `SettingField`:
   - "РАЗМЕР ЧАНКА (символов)" → `TextInputField` mono, bound к `preferences.chunkingChunkChars`. Hint: "рекомендуется 30 000–60 000".
   - "OVERLAP" → `SelectField` с дискретными значениями `["0.00", "0.10", "0.20", "0.30", "0.40", "0.50"]`, labels: "Без перекрытия", "10%", "20% (рекомендуется)", "30%", "40%", "50% (максимум)". По шаблону `oocSelect`.
3. Обе строки параметров серые/disabled при `!preferences.chunkingEnabled` (через `enabled: preferences.chunkingEnabled` на SettingField). Это чистый аффорданс — `chunk_text_file` всё равно не вызовется.

Почему SelectField для overlap, а не TextInputField: свободный ввод float нестабилен (пользователь введёт "0,2" или "20%"), а дискретный шаг в 10% закрывает все разумные сценарии. YAGNI — не тащим SpinBox.

### 5.2 `ui/engines/pipeline_controller.py`

В `PipelineController` уже лежит `self._preferences`. Сейчас он только `build_asr_options()` для `make_source`. Но **`PipelineController` никогда не строит `PipelineParams` и не зовёт `core.pipeline.run()`** — он напрямую запускает `AsrWorker` + `MergerWorker`. То есть для UI-пути post-step нужно звать либо:

- **Вариант A (рекомендуется):** добавить `_spawn_chunker()` шаг после `_onMergeDone`, когда `self._preferences.build_chunking_options().enabled`. Логика:
  - После `self._app.phase = "done"` (или до — уточнить ниже) проверить опции.
  - Если enabled, импортировать `core.chunking.chunk_text_file`, вызвать **синхронно на main thread** (это IO-bound на десятки миллисекунд для среднего merged.txt; измеримо — но не стоит QThread-церемонии). Если возникнет жалоба на лаг, обернуть в `ChunkerWorker` по аналогии с `MergerWorker` (не сейчас, YAGNI).
  - Заполнить новое свойство `self._chunks_dir: str`, эмитнуть `chunksDirChanged`.
  - Добавить `Q_PROPERTY chunksDir` + `chunksDirChanged` signal.
- **Вариант B:** переписать UI-путь через `core.pipeline.run()` с `PipelineParams(..., chunking=preferences.build_chunking_options())`. Слишком большая рефакторинг-волна — `PipelineController` разбивает speech/merge на отдельные QThread'ы для per-row прогресса, а `run()` — монолит. Out of scope.

**Берём Вариант A.**

Правки в `pipeline_controller.py`:

- Import: `from core.chunking import chunk_text_file`.
- Добавить поле `self._chunks_dir: str = ""` рядом с `self._output_path`.
- Добавить `chunksDirChanged = Signal()` + `@Property(str, notify=chunksDirChanged) chunksDir`.
- В `_onMergeDone` после `self._app.setDoneSummary(...)` и до `self._app.phase = "done"`:
  ```python
  if self._preferences is not None:
      opts = self._preferences.build_chunking_options()
      if opts.enabled:
          try:
              dest = chunk_text_file(
                  Path(path),
                  chunk_chars=opts.chunk_chars,
                  overlap_ratio=opts.overlap_ratio,
              )
              self._chunks_dir = str(dest)
              self.chunksDirChanged.emit()
          except (FileNotFoundError, ValueError, OSError):
              logger.exception("Chunker post-step failed for %s", path)
  ```
- В `runAsr()` при ресете: `self._chunks_dir = ""` + emit.

### 5.3 OutputChip на Done-фазе

В `ui/qml/timeline/DoneSummary.qml` сейчас нет никакого списка артефактов — это просто заголовок. Сам `OutputChip.qml` рендерится где-то в `TimelineScreen.qml`. Нужно проверить и добавить второй `OutputChip` рядом с существующим:

- Условия: `visible: pipelineController.chunksDir.length > 0`, `done: true`, `fileName: "chunks/"`, `outputPath: pipelineController.chunksDir`, `sizeCaption: "N чанков"` (можно заполнить через `manifest.json` — но YAGNI для MVP; просто писать "чанки" или "готово").
- Альтернатива: вообще не трогать DoneSummary и добавить `OutputChip` только в `TimelineScreen.qml` рядом с существующим merged-чипом. **Так проще.**

Предпочитаемый подход: выяснить место в `TimelineScreen.qml` где инстанциируется `OutputChip` с `outputPath: pipelineController.outputPath`, и добавить второй `OutputChip` под ним с `outputPath: pipelineController.chunksDir`, `fileName: "chunks/"`, обёрнутый `visible:`.

### 5.4 Тесты (UI)

- `tests/test_ui_engines_pipeline_controller.py`: добавить тест, который монкипатчит `chunk_text_file` и `preferences.build_chunking_options()` → проверить что после `_onMergeDone` поле `chunksDir` заполнено. И второй — что при `enabled=False` `chunksDir` остаётся `""`.
- QML-тесты (`test_qml_timeline_phases.py` / `test_qml_shell_boot.py`) скорее всего не требуют правок — секции чанков необязательны, новый `OutputChip` `visible` по дефолту false.

## 6. Точки поломки тестов

Только эти файлы реально ломаются:

- `tests/test_pipeline_stage_callback.py` — **не ломается**, если default `chunking=None` (стадия `"chunk"` опциональна). Но я бы добавил в него 2-3 новых теста на путь `enabled=True`.
- `tests/ui_qml_smoke/test_app_preferences.py` — расширить defaults и mutate-блоки для трёх новых полей.
- `tests/test_core_pipeline_kwargs.py::TestPipelineParamsDefaults` — расширить одним новым assert.
- Новые файлы тестов: `tests/test_core_chunking_options.py` (dataclass frozen + defaults), при желании — отдельный `tests/test_pipeline_chunking_step.py` если не хотим раздувать `test_pipeline_stage_callback.py`.

**Не трогаем:** `tests/test_integration_full_pipeline.py`, `tests/test_e2e_tier2_semantic.py`, `tests/test_core_asr.py`, `scripts/chunk_text.py` и его тесты (если есть).

## 7. Ограничения / NOT done

- **Per-session override** параметров чанкера: отложен вместе с per-track ASR override в #9. Архитектурно тривиально добавить, когда появится SessionMeta-level settings popover.
- **Token-based splitting** (tiktoken / sentencepiece): нет — только символы. Добавить можно флагом `ChunkingOptions.unit: Literal["chars", "tokens"]`, но это не нужно для MVP.
- **Progress внутри стадии `"chunk"`**: нет — стадия монолитная, эмитится одна пара "старт"/переход. Чанкер обрабатывает даже 1 MB merged.txt за десятки миллисекунд.
- **ChunkerWorker на QThread**: нет — синхронный вызов на main thread в `_onMergeDone`. Измерить, если пользователь пожалуется.
- **Отображение содержимого чанков в UI**: нет. `OutputChip` только открывает папку `chunks/` через `Qt.openUrlExternally`.
- **`done` message в stage_cb**: оставляем путь к `merged.txt`, не к chunks — ломать тест не хочется, а путь к chunks и так доступен через `PipelineController.chunksDir`.
- **CLI `ui/cli.py` миграция на `PipelineParams.chunking`**: не делаем. Текущий `_run_chunk_post_step` работает, его вызов через `core.pipeline.run()` был бы минимальным плюсом за цену перепиливания `if args.chunk` ветки. Оставляем как есть.

## 8. Этапы коммитов

Три отдельных коммита (матчит разбиение этапов, каждый самодостаточный и не ломает master):

1. **commit 7A — `feat(core): ChunkingOptions + pipeline post-step`**
   - `core/chunking.py`: + dataclass `ChunkingOptions`.
   - `core/pipeline.py`: + `"chunk"` в литерале, + `chunking` field, + post-step в `run()`.
   - `tests/test_core_chunking_options.py`: новый.
   - `tests/test_pipeline_stage_callback.py`: +2-3 теста на enabled/disabled пути.
   - `tests/test_core_pipeline_kwargs.py`: + default assert.
   - После коммита: pipeline можно звать с `chunking=ChunkingOptions(enabled=True)` из любого Python-кода. UI ещё не вооружён.

2. **commit 7B — `feat(ui): chunking preferences + QSettings`**
   - `ui/models/app_preferences.py`: +3 Q_PROPERTY, +3 signals, +`build_chunking_options()`, обновлённый docstring.
   - `tests/ui_qml_smoke/test_app_preferences.py`: расширенный round-trip.
   - После коммита: preferences персистятся, но UI их не показывает и pipeline не использует.

3. **commit 7C — `feat(ui): chunker Settings UI + OutputChip wiring`**
   - `ui/qml/screens/SettingsScreen.qml`: +SettingsGroup "Чанки для LLM".
   - `ui/engines/pipeline_controller.py`: +`chunksDir` property, +вызов `chunk_text_file` в `_onMergeDone`.
   - `ui/qml/timeline/TimelineScreen.qml`: +второй `OutputChip` для chunks/.
   - `tests/test_ui_engines_pipeline_controller.py`: +тесты на post-step.

Альтернатива: слить 7B+7C в один коммит. Делать **не рекомендуется** — 7B даёт зелёный зал на QSettings отдельно, а 7C вносит QML-правки, которые валидируются другим набором smoke-тестов. Разделение упрощает code review.
