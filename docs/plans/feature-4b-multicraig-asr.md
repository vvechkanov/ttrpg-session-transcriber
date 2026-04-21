# План: Feature #4 iteration 4b — Multi-Craig ASR per segment

## 1. Цель и scope

- **В scope.** Прогонять ASR по **всем** `TrackSegment`-ам каждого ряда (не только `segments[0]`); смещать результирующие `SpeechSegment.start` / `.end` в единую «session-global» ось, отсчитываемую от `TimelineWindow.t0`; извлекать и отрисовывать waveform peaks для каждого сегмента отдельно.
- **В scope.** Аккумулировать конкатенированный `list[SpeechSegment]` на ряд так, чтобы MergerWorker потреблял его без знания о сегментах.
- **В scope.** Один прогресс-канал на ряд (weighted по длительности сегментов) и единая отмена по всем сегментам ряда.
- **Out of scope.** Брэкетирование тишины между сегментами, per-segment speaker override, переработка MergerWorker, запараллеливание ASR внутри ряда (последовательный цикл остаётся), Feature #7 (chunker).
- **Инвариант.** После 4b `TrackSegment.start_ts is None` ⇒ ряд не может корректно сместить сегмент к глобальному времени — такой сегмент обрабатывается с `time_offset_sec=0.0` и помечается (логом) как «unanchored»; merged.txt может иметь пересечения — документируем в разделе 7.

## 2. Контракт изменений в core

### 2.1. `core/asr.py` — расширение `transcribe_one_track`

Добавить keyword-only параметр с дефолтом:

```python
def transcribe_one_track(
    source: Source,
    audio_path: Path,
    *,
    speaker: str | None = None,
    on_progress: TrackProgress | None = None,
    should_cancel: CancelProbe | None = None,
    time_offset_sec: float = 0.0,
) -> list[SpeechSegment]:
```

**Семантика.** `transcribe_one_track` сам сдвигает `.start` / `.end` возвращаемых `SpeechSegment`-ов на `time_offset_sec` **после** вызова `source.transcribe_track`. Альтернативы:

- **(A) Caller-shift** — рабочий (`AsrWorker`) вызывает `shift_segments(segments, offset)` сразу после `transcribe_one_track`.
- **(B) Callee-shift** внутри `transcribe_one_track` (выбрано).

**Обоснование (B).** `transcribe_one_track` — единственная точка, где все три параметра (`source`, `audio_path`, `time_offset_sec`) встречаются одновременно, поэтому смещение там минимально изменяет контракт и не требует нового публичного хелпера. Кроме того, cancellation возвращает **частичный** список — он тоже должен быть смещён, и делать это в вызывающем коде означало бы дублировать обработку и в `done`, и в «cancel после partial» ветках `AsrWorker.run`. Единственный недостаток (callee-shift мутирует возвращаемые dataclass-ы) решается конструированием новых инстансов `SpeechSegment(start=s.start + off, end=s.end + off, ...)`, потому что `SpeechSegment` — обычный `@dataclass` (не frozen), но контракт «возвращаем новые объекты» держим ради будущего frozen-перехода.

**Защитный инвариант.** Если `time_offset_sec == 0.0`, возвращать исходный список без копирования (тесты 4a и legacy single-segment пути не меняют поведение).

### 2.2. Вычисление `time_offset_sec`

`time_offset_sec` рассчитывается в UI-слое перед вызовом воркера:

```
offset = (segment.start_ts - session_meta.timelineWindow().t0).total_seconds()
```

- `session_meta.timelineWindow()` уже публичен (`ui/models/session.py:180`).
- Если `timelineWindow() is None` или `segment.start_ts is None` — `offset = 0.0`.

Эту формулу инкапсулируем в новый Python-хелпер в `ui/models/session.py` (не Slot):

```python
def segment_offset_seconds(
    self, segment: TrackSegment
) -> float: ...
```

на `TrackListModel`, чтобы `PipelineController` не тянул `timelineWindow()` напрямую.

### 2.3. Новый Slot для передачи сегментов в pipeline

В `TrackListModel` добавить:

```python
@Slot(int, result=list)
def segmentsFor(self, row: int) -> list[dict]: ...
```

Возвращает `[{"audioPath": str, "offsetSec": float, "durationSec": float | None}, ...]`, упорядоченный как `entry.segments`. `PipelineController._advance` читает этот список (см. раздел 5).

Существующий `audioPathFor(row)` оставляем как legacy shim для тестов и кода, который уже ему научен; внутри pipeline он больше не используется.

## 3. Этап 4b.1 — ASR fanout per segment

### 3.1. Решение: worker-owns-row

`AsrWorker` принимает список сегментов на ряд и крутит внутренний цикл. **Обоснование:**

- Один поток прогресса на ряд → не нужно агрегировать в `PipelineController` частичные pct от N под-воркеров.
- Одна точка отмены (QThread-level `requestInterruption`) применима ко всему ряду.
- `_collected_segments[row]` остаётся плоским списком, MergerWorker не меняется.

### 3.2. Новый конструктор `AsrWorker`

```python
def __init__(
    self,
    row: int,
    source: AsrSource,
    segments: tuple[_SegmentJob, ...],
) -> None: ...
```

где `_SegmentJob` — маленький frozen-dataclass (локальный для `ui/engines/asr_worker.py`):

```python
@dataclass(frozen=True)
class _SegmentJob:
    audio_path: Path
    offset_sec: float
    duration_sec: float  # 0.0 означает "неизвестна" — weight = 1/N fallback
```

Старое поле `self._audio_path` удаляется; тесты, конструирующие `AsrWorker(row, src, path)`, нужно поправить.

### 3.3. Новый `AsrWorker.run`

```python
total_weight = sum(max(j.duration_sec, 0.0) for j in self._segments)
if total_weight <= 0:
    # Fallback: равный вес на сегмент
    weights = [1.0 / len(self._segments)] * len(self._segments)
else:
    weights = [j.duration_sec / total_weight for j in self._segments]

completed_weight = 0.0
collected: list[SpeechSegment] = []

for i, job in enumerate(self._segments):
    if _should_cancel():
        break
    segment_weight = weights[i]

    def _on_seg_progress(pct: float, base=completed_weight, w=segment_weight) -> None:
        self.progress.emit(self._row, base + pct * w)

    try:
        segs = transcribe_one_track(
            self._source,
            job.audio_path,
            on_progress=_on_seg_progress,
            should_cancel=_should_cancel,
            time_offset_sec=job.offset_sec,
        )
    except Exception as exc:
        self.error.emit(self._row, str(exc))
        self.finished.emit()
        return

    collected.extend(segs)
    completed_weight += segment_weight

if not _should_cancel():
    self.done.emit(self._row, collected)
self.finished.emit()
```

**Что меняется vs. сегодня.**
- `progress` пересчитывается в global-row-scope (взвешенно). Делегаты в QML не меняются — они уже принимают 0..1.
- Частичные сегменты, полученные при cancel посреди второго сегмента, отбрасываются.
- `duration_sec` для весов берём из `TrackSegment.duration_sec`; если `None` — все сегменты с равным весом.

### 3.4. Fallback-вес, когда длительности ещё не пришли

`PeaksWorker.durationReady` в 4a эмитит **одну** максимальную длительность в `SessionMeta`, но per-segment длительность в `TrackSegment.duration_sec` оставлена `None`. Вариант решения, который держим в 4b:
- использовать `probe_duration(audio_path)` синхронно в `PipelineController._advance` **перед** запуском воркера (sub-second per file, 10 s timeout уже есть в `core/peaks.py:48-75`). Это один дополнительный вызов на сегмент в момент старта ASR — приемлемо, потому что ASR сам стартует медленно.
- (Альтернатива, отложена) расширить `PeaksWorker` чтобы эмитило per-segment duration в `TrackListModel`. Отложено: увеличивает радиус изменений без пропорциональной пользы в 4b.

## 4. Этап 4b.2 — Peaks per segment

### 4.1. Per-segment extraction

`TrackListModel.loadFromDir` меняет эмит `audioPathsChanged`: вместо `[(i, primary_path_str)]` эмитим `[(row, segment_idx, path_str)]` — либо новый сигнал `segmentPathsChanged`, либо универсальный.

**Выбор:** новый сигнал `segmentPathsChanged = Signal(list)` с payload `[(row, segment_idx, path_str)]`. `audioPathsChanged` оставляем для `appendTrack` (он по-прежнему кладёт один сегмент) — нулевой риск поломать single-audio drop.

`PeaksWorker` расширяется третьим индексом:
- конструктор принимает `Sequence[tuple[int, int, str]]` (`row, seg_idx, path`);
- `peaksReady = Signal(int, int, list)` — `(row, seg_idx, peaks)`;
- `durationReady = Signal(int, int, float)` — опционально.

`TrackListModel.setPeaks` становится `setPeaks(row, seg_idx, peaks)`.

### 4.2. Хранилище peaks в модели

`TrackEntry.peaks: list[float]` → `TrackEntry.peaks_by_segment: list[list[float]]`. Поле заводится `[[] for _ in segments]`. `PeaksRole` теперь отдаёт плоский список peaks для **первого** сегмента (назад-совместимо для случаев single-segment), а полный список прошит в `SegmentsRole`.

### 4.3. `SegmentsRole` payload

Расширяем существующий `_segments_payload` вместо добавления нового role: payload каждого сегмента становится

```python
{"startPct": ..., "endPct": ..., "peaks": [...]}
```

**Обоснование:** QML уже итерирует `root.segments` через `Repeater` (`TrackLaneRow.qml`); добавление поля в тот же объект не требует нового биндинга.

### 4.4. `TrackLaneRow.qml` changes

Заменить двойную конструкцию «WaveformCanvas фиксированный на весь трек + Repeater с placeholder-рект» на **один Repeater**, внутри которого — `WaveformCanvas`, позиционированный по `startPct` / `endPct`.

- удалить `WaveformCanvas` на primary;
- удалить `Rectangle` delegate секондарного placeholder;
- добавить `Repeater { model: root.segments; delegate: WaveformCanvas { x: ...; width: ...; peaks: modelData.peaks; ... } }`.
- property `peaks: var` на root-е становится необязательным (удаление в cleanup-коммите).

`progress` по-прежнему общерядный — «fill overlay» поверх всех сегментов остаётся аттаченным к `track` Item, чтобы «N% закрашено слева направо» совпадало со старым визуалом.

## 5. Этап 4b.3 — PipelineController wiring

### 5.1. `_advance` (`pipeline_controller.py`)

Замена блока `audio_path_str = self._tracks.audioPathFor(row) ...` на:

```python
seg_jobs_raw = self._tracks.segmentsFor(row)
if not seg_jobs_raw:
    self._tracks.setError(row, "Нет аудиофайлов для этого спикера")
    self._advance(); return

seg_jobs = tuple(
    _SegmentJob(
        audio_path=Path(j["audioPath"]),
        offset_sec=float(j["offsetSec"]),
        duration_sec=float(j.get("durationSec") or probe_duration(Path(j["audioPath"]))),
    )
    for j in seg_jobs_raw
)
```

Затем вместо `self._spawn(row, source, Path(audio_path_str))` вызываем `self._spawn(row, source, seg_jobs)`.

### 5.2. `_spawn`

Меняем сигнатуру `_spawn(self, row, source, seg_jobs)` — передаём tuple в `AsrWorker`.

### 5.3. Merged output

`_spawn_merger` уже собирает `list[SpeechSegment]` через `_collected_segments[row]`. Поскольку `transcribe_one_track` уже вернул global-scale времена, **никаких дополнительных сдвигов в `_spawn_merger` не требуется**. `MergerWorker` принимает сконкатенированный список, сортирует по `start`, склеивает — существующее поведение.

### 5.4. Что **не** трогаем

- `MergerWorker` и его API.
- `find_fvtt_chat_log` — работает от `session_dir`, сегментам индифферентен.
- `totalSeconds` в `SessionMeta` — в 4a он уже приходит через `PeaksWorker.durationReady` и представляет длину **самого длинного файла**, не объединённый span. После 4b желаемое: `totalSeconds` = `(t_end - t0).total_seconds()` из `TimelineWindow`. Отдельный TODO (см. раздел 7), но **не блокирует** 4b.

## 6. Изменения в тестах

### 6.1. Поломанные тесты

- `tests/test_core_asr.py::test_transcribe_one_track_forwards_args` — продолжит проходить без изменений (новый параметр keyword-only с дефолтом `0.0`).
- Любые тесты, конструирующие `AsrWorker(row, src, path)` напрямую — нужно обновить до нового конструктора с `tuple[_SegmentJob, ...]`.
- Тесты, проверяющие `TrackListModel.audioPathFor(row)` — остаются валидны (shim не удалён).
- Любой тест, мокающий `PeaksWorker(tracks=[(row, path)])` или проверяющий `peaksReady(row, peaks)` — сломается из-за расширения сигнатур.

### 6.2. Новые тесты

- `tests/test_core_asr.py::test_transcribe_one_track_applies_time_offset` — вызвать с `time_offset_sec=10.0` и _FakeSource, возвращающим segment `start=0.0, end=1.0`; убедиться что возврат содержит `start=10.0, end=11.0`.
- `tests/test_core_asr.py::test_transcribe_one_track_zero_offset_is_identity` — `time_offset_sec=0.0` не создаёт копию (проверяем `segs[0] is fake_returned_segment`).
- `tests/test_asr_worker_multi_segment.py::test_two_segments_concatenated_with_offsets` — поднять `AsrWorker` с двумя `_SegmentJob`, `_FakeSource` возвращает 1 сегмент на файл; проверить `done` emitted с 2 сегментами, второй имеет `start` равный `offset_sec[1]`.
- `tests/test_asr_worker_multi_segment.py::test_cancel_mid_second_segment` — `_FakeSource` поддерживает `should_cancel`, возвращает partial; установить `cancelled=True` при вызове `on_progress` во втором сегменте; проверить что `done` не emitted, `finished` emitted ровно один раз.
- `tests/test_asr_worker_multi_segment.py::test_progress_is_duration_weighted` — два сегмента, длительности 2.0 и 6.0; убедиться что в момент, когда первый сегмент завершён, `progress.emit` получил значение ≈ 0.25 (2/(2+6)).
- `tests/test_session_models.py::test_segments_role_includes_peaks` — проверить что `SegmentsRole` payload содержит `peaks`, равный содержимому `TrackEntry.peaks_by_segment[i]`.

## 7. Ограничения / NOT done

- **Пропуски между сегментами.** Если Craig-1 закончился в `t0+1h` и Craig-2 начался в `t0+1h05m`, в результирующем `list[SpeechSegment]` будет 5-минутная «дыра» без аннотаций. Никакой интерполяции/silence-bridging — документируем и оставляем на отдельную итерацию.
- **Пересечения сегментов.** Теоретически возможно. Поведение после 4b: оба сегмента транскрибируются независимо, `MergerWorker` получает пересекающиеся cue; merged.txt может иметь дубли. Не чиним — предупреждаем в docstring `TrackListModel.loadFromDir`.
- **Per-segment speaker override.** Не поддержано: `match_speaker` даёт один ключ на все сегменты ряда; `AsrWorker` не принимает `speaker` в `_SegmentJob`. Out of scope.
- **`SessionMeta.totalSeconds` как span.** Сегодня это `max(track_duration)`. После 4b желаемое — span из `TimelineWindow`, но это feature #3 follow-up.
- **Peaks cache invalidation.** Никаких изменений в `core/peaks.py`: `<audio>.peaks.bin` по-прежнему per-file, per-segment просто означает N кэшей рядом с N аудиофайлами.

## 8. Этапы коммитов

Рекомендуемый split — **три коммита**, в следующем порядке (каждый проходит тесты самостоятельно):

1. **commit 4b/1 — core + contract.**
   - `core/asr.py`: добавить `time_offset_sec`; реализовать pure-callee shift; unit-тесты.
   - `ui/models/session.py`: добавить `segment_offset_seconds` и `segmentsFor` Slot.
   - `ui/engines/asr_worker.py`: переписать под `tuple[_SegmentJob, ...]`.
   - `ui/engines/pipeline_controller.py`: переключить `_advance` / `_spawn` на `segmentsFor`.
   - Тесты: `tests/test_core_asr.py` расширение + новый `tests/test_asr_worker_multi_segment.py`.

2. **commit 4b/2 — peaks per segment.**
   - `ui/engines/peaks_worker.py`: сигнатуры + новый сигнал.
   - `ui/models/session.py`: `TrackEntry.peaks_by_segment`, `setPeaks(row, seg_idx, peaks)`, обновить `_segments_payload` чтобы включал `peaks`.
   - `ui/app_qml.py`: перевесить коннекты на новые сигналы.
   - Тесты на роль `SegmentsRole`.

3. **commit 4b/3 — QML-рендер per-segment waveform.**
   - `ui/qml/timeline/TrackLaneRow.qml`: Repeater → WaveformCanvas per segment; выбросить 50%-placeholder; progress-overlay по-прежнему на весь `track` Item.
   - Скриншот-тест или runtime smoke-check (вручную).

Альтернативный «единый» split не рекомендуется: коммит 4b/1 имеет самостоятельную ценность (ASR-корректность) даже без визуальных изменений — merged.txt начинает содержать правильные timestamps немедленно.
