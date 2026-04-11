# Architecture

Этот документ фиксирует **целевую архитектуру** проекта `discord-session-transcriber` и план миграции к ней. Документ написан перед стартом Приоритета 2 и описывает состояние в которое проект придёт к концу этого приоритета. Каждый последующий приоритет (3-6) будет **расширять** эти слои, не трогая их границы.

---

## 1. Purpose & scope

**Для кого:** новые контрибьюторы и сам автор при возврате к проекту через несколько месяцев. Цель — за 10-15 минут чтения получить полную картину «как проект разделён на слои, что куда импортирует, и где живёт логика X».

**В документе есть:**
- Короткое описание текущего монолита и его проблем
- Целевое состояние (6 папок-слоёв, направление зависимостей, ответственности)
- Public contracts — точные сигнатуры dataclass-ов и ABC
- Pipeline flow от discovery до output файла
- План миграции (Приоритет 2 делает всё сразу, Приоритеты 3-6 расширяют)
- Зафиксированные архитектурные решения с причинами (ADR-стиль)
- Глоссарий Python-идиом для контрибьюторов из Kotlin/C++ мира

**Чего в документе НЕТ:**
- Deployment / packaging / PyInstaller детали — в `README.md` / `CONTRIBUTING.md`
- CI/CD pipeline — отдельная задача в Приоритете 3
- Model selection rationale (почему `large-v3`, чем хорош `bzikst/...-podlodka`) — в `README.md`
- Решение tkinter vs PySide6 — принимается в Приоритете 5
- API reference / docstrings — генерируются из кода

---

## 2. Current state (brief)

Сейчас проект — слабо структурированный монолит с двумя изолированными утилитами:

```
scripts/wisper_launcher.py    (1003 строки — монолит)
├── argparse CLI
├── tkinter GUI
├── subprocess вызов whisperx
├── pipeline orchestration (discover → transcribe → merge → chunk)
├── GPU pre-flight check
└── chat log integration coordination

scripts/merge_whisperx.py     (168 строк — engine-agnostic by design)
scripts/parse_fvtt_chat.py    (изолирован, чистые функции)
```

**Что работает:**
- `merge_whisperx.py` не привязан к WhisperX — читает только `start`/`end`/`text` per segment, speaker берёт из `speaker_map.json`. Любой backend с canonical JSON работает без изменений мерджера.
- `parse_fvtt_chat.py` — pure functions, без I/O в pipeline.

**Что плохо:**
- В `wisper_launcher.py` смешаны 5 разных ответственностей. Любое изменение GUI рискует сломать CLI и наоборот.
- Транскрипция жёстко прибита к `whisperx` CLI subprocess. Нельзя добавить альтернативный backend без `if/else` в оркестраторе.
- Мерджер умеет только объединять речевые сегменты одного говорящего по gap. Нет способа добавить chat / game log / emotion как равноправные элементы скрипта.
- Нет тестов — любой рефакторинг страшный.

---

## 3. Target state

К концу Приоритета 2 проект декомпозирован на **шесть папок**, каждая соответствует слою. Направления импортов строго однонаправленные.

```
┌────────────────────────────────────────────────────────────┐
│  ui/                                                        │
│  cli.py, gui.py                                             │
│  argparse, tkinter widgets, сбор params, progress display   │
└───────────────────────┬─────────────────────────────────────┘
                        │ imports
┌───────────────────────▼─────────────────────────────────────┐
│  core/                                                       │
│  pipeline.py, discovery.py, gpu_check.py, cache.py           │
│  orchestration: discover → extract → assemble timeline →     │
│  merge → render                                              │
└──┬─────────────────┬──────────────────┬────────────┬────────┘
   │ imports         │ imports          │ imports    │ imports
   ▼                 ▼                  ▼            ▼
┌──────────┐    ┌──────────┐      ┌──────────┐   ┌──────────┐
│ sources/ │    │ mergers/ │      │renderers/│   │ domain/  │
│          │    │          │      │          │   │          │
│ speech/  │    │script_   │      │plain_    │   │annotat-  │
│ game_log/│    │merger.py │      │text.py   │   │ions.py   │
│ base.py  │    │base.py   │      │base.py   │   │events.py │
│          │    │          │      │          │   │timeline. │
│          │    │          │      │          │   │py        │
│          │    │          │      │          │   │speaker_  │
│          │    │          │      │          │   │map.py    │
└────┬─────┘    └────┬─────┘      └────┬─────┘   └──────────┘
     │ imports       │ imports         │ imports      ▲
     └───────────────┴─────────────────┴──────────────┘
                                                   (pure, no deps)
```

### Dependency rules (строго)

- `ui` → `core`
- `core` → `sources`, `mergers`, `renderers`, `domain`
- `sources` → `domain` only
- `mergers` → `domain` only
- `renderers` → `domain` only
- `domain` → ничего внутри проекта (pure)

### Запрещено

- `sources` импортирует `mergers` или `renderers`
- `mergers` импортирует `sources` или `renderers`
- `renderers` импортирует `sources` или `mergers`
- `domain` импортирует что угодно из проекта
- `core` знает про tkinter / PySide6 или любой GUI widget API
- Любой циклический импорт между слоями

В Python нет enforced module boundaries (в отличие от gradle modules в Kotlin) — эти правила держатся **дисциплиной + ревью + линтером** (ruff import-rules в Приоритете 3).

---

## 4. Layer responsibilities

| Слой | Делает | НЕ делает |
|---|---|---|
| `ui` | argparse parsing, tkinter widgets, сбор params в dict, запуск worker thread, отображение прогресса/ошибок | ASR, merge logic, file I/O транскриптов, subprocess вызовы |
| `core` | file discovery, GPU pre-flight, оркестрация pipeline, сборка `Timeline` (тип из `domain/`) в памяти, выбор конкретных Source/Merger/Renderer через registry, disk cache decorators | сама транскрипция, сам merge алгоритм, сам рендеринг текста, определение `Timeline` (он в `domain/`) |
| `sources` | извлечение аннотаций из входных данных (аудио, FVTT chat, будущие игровые логи), возврат `list[Annotation]` | pipeline orchestration, merge, форматирование вывода |
| `mergers` | комбинирование `Timeline` в плоскую упорядоченную `list[ScriptEvent]` — разрешение overlaps, проекция эмоций на речь, интерливинг chat/game event-ов | извлечение данных, форматирование вывода |
| `renderers` | форматирование `list[ScriptEvent]` в итоговый формат (plain text, markdown, html, obsidian) | решения что с чем объединять, обращение к sources / mergers |
| `domain` | pure dataclass-ы для аннотаций и событий, вспомогательные функции без I/O (speaker_map) | subprocess, ASR, GUI, file I/O |

---

## 5. Public contracts

Это единственные типы и интерфейсы через которые слои общаются. Всё остальное — внутренняя кухня слоя.

### 5.1 Raw annotation types (`domain/annotations.py`)

Эти типы возвращаются из `Source.extract(...)`. Каждый тип — layer specific: разные sources возвращают разные типы.

```python
@dataclass
class SpeechSegment:
    start: float
    end: float
    speaker: str | None
    text: str
    confidence: float | None = None

@dataclass
class EmotionTag:
    start: float
    end: float
    label: str
    confidence: float

@dataclass
class ChatMessage:
    at: float              # point event, start == end semantically
    channel: str           # "ic" | "ooc" (expandable)
    author: str
    text: str

@dataclass
class GameLogEntry:
    at: float
    actor: str
    action: str            # "roll" | "damage" | "spell" (expandable)
    detail: str

Annotation = SpeechSegment | EmotionTag | ChatMessage | GameLogEntry
```

### 5.2 Timeline (`domain/timeline.py`) — internal container

`Timeline` — in-memory структура которая собирается оркестратором из source outputs и передаётся мерджеру. Это **не публичный контракт**: нет schema_version, она не сериализуется публично, рендерерам не показывается.

Живёт в `domain/` (не в `core/`), потому что импортируется `mergers/base.py` в сигнатуре `merge(timeline: Timeline) -> list[ScriptEvent]`, а dependency rules запрещают `mergers → core`. См. ADR-12.

```python
@dataclass
class Timeline:
    """Слоённый контейнер аннотаций. Собирается core.pipeline,
    потребляется Merger. Не является сериализуемым форматом."""
    speech: list[SpeechSegment]
    emotions: list[EmotionTag]
    chat: list[ChatMessage]
    game_log: list[GameLogEntry]
```

### 5.3 Merger output — discriminated union (`domain/events.py`)

Merger выдаёт плоский, упорядоченный, **неперекрывающийся по разным типам** список `ScriptEvent`. Overlapping речь кодируется через `parallel_group`.

```python
@dataclass
class SpeechEvent:
    start: float
    end: float
    speaker: str
    text: str
    emotion: str | None = None           # проецируется из EmotionTag merger-ом
    parallel_group: int | None = None    # одинаковый id у overlapping SpeechEvent

@dataclass
class ChatEvent:
    at: float
    channel: Literal["ic", "ooc"]
    author: str
    text: str

@dataclass
class GameEvent:
    at: float
    actor: str
    action: Literal["roll", "damage", "spell"]
    detail: str

ScriptEvent = SpeechEvent | ChatEvent | GameEvent
```

Это **discriminated union** в смысле PEP 604 — mypy проверяет exhaustiveness в `match` statement. Для Kotlin разработчика это sealed hierarchy: добавление нового варианта требует обновить все `match` блоки, компилятор (mypy) подсвечивает пропущенные места.

### 5.4 Source ABC (`sources/base.py`)

```python
class Source(ABC):
    name: str

    @abstractmethod
    def extract(self, session_dir: Path) -> list[Annotation]: ...
```

### 5.4a DiskCached decorator (`core/cache.py`)

Generic disk cache decorator, применимый и к `Source`, и к `Merger`. Живёт в
`core/`, потому что используется обоими слоями и не принадлежит ни одному из
них (см. ADR-7).

```python
class DiskCachedSource(Source):
    """Decorator. Оборачивает Source, кэширует list[Annotation] в
    session_dir/_cache/sources/<source_name>.json. Формат кэша — внутренний
    (см. ADR-7)."""
    def __init__(self, wrapped: Source, cache_dir: Path): ...

class DiskCachedMerger(Merger):
    """Decorator. Оборачивает Merger, кэширует list[ScriptEvent] в
    session_dir/_cache/mergers/<merger_name>.json. Формат кэша — внутренний
    (см. ADR-7). Применяется только к дорогим мерджерам (LLM), ScriptMerger
    не оборачивается."""
    def __init__(self, wrapped: Merger, cache_dir: Path): ...
```

Оба декоратора реализуют тот же интерфейс что оборачиваемый объект
(`Source`/`Merger`), оркестратор в `core.pipeline` не отличает
кэширующуюся реализацию от прямой.

### 5.5 Merger ABC (`mergers/base.py`)

```python
class Merger(ABC):
    @abstractmethod
    def merge(self, timeline: Timeline) -> list[ScriptEvent]: ...
```

Конкретные реализации в Приоритете 2: `ScriptMerger` (детерминированный, без LLM). Будущие (не в P2): `LocalLLMMerger`, `ExternalLLMMerger`.

### 5.6 Renderer ABC (`renderers/base.py`)

```python
class Renderer(ABC):
    @abstractmethod
    def render(self, events: list[ScriptEvent]) -> bytes: ...
```

Конкретные реализации в Приоритете 2: `PlainTextRenderer` (совместимый с текущим `merged.txt`). Будущие: `MarkdownRenderer`, `ObsidianRenderer`, `HtmlRenderer`.

### 5.7 Canonical JSON (minimum) — выход speech sources

Speech source (`faster_whisper`, `whisperx`) пишет на диск JSON **только с required полями**:

- `start: float`
- `end: float`
- `text: str`
- `source_engine: str`
- `schema_version: int`

Optional поля (`confidence`, `no_speech_prob`, слова) добавляются additively когда появится реальный consumer. YAGNI (см. ADR-8).

---

## 6. Pipeline flow

```
User runs CLI/GUI
       │
       ▼
ui/ собирает params → core.pipeline.run(params)
       │
       ▼
┌──────────────────── core.pipeline ───────────────────────┐
│                                                           │
│  1. core.discovery → list[Path] аудио файлов             │
│  2. core.gpu_check → CUDA pre-flight                     │
│                                                           │
│  3. Для каждой session_dir:                              │
│                                                           │
│     sources/speech/faster_whisper.py                     │
│         wrapped by DiskCachedSource                      │
│         .extract(session_dir) → list[SpeechSegment]      │
│                                                           │
│     sources/game_log/fvtt_chat.py                        │
│         .extract(session_dir) → list[ChatMessage]        │
│                                                           │
│     (future) sources/emotion/*.py                        │
│         .extract(session_dir) → list[EmotionTag]         │
│                                                           │
│  4. Timeline assembly (in-memory, inside core):          │
│     timeline = Timeline(                                  │
│         speech=speech_segments,                          │
│         emotions=emotion_tags,                           │
│         chat=chat_messages,                              │
│         game_log=game_entries,                           │
│     )                                                     │
│                                                           │
│  5. merger = ScriptMerger()                              │
│     (для дорогих LLM мерджеров: wrapped by               │
│      DiskCachedMerger — см. ADR-7)                       │
│     events = merger.merge(timeline)                      │
│                                                           │
│  6. renderer = PlainTextRenderer()                       │
│     output_bytes = renderer.render(events)               │
│                                                           │
│  7. Запись output_bytes на диск                          │
│                                                           │
└──────────────────────────────────────────────────────────┘
       │
       ▼
ui/ отображает результат пользователю
```

**Где живёт Timeline:** только внутри одной итерации `pipeline.run`. Не сериализуется, не покидает process memory. Assembled в шаге 4, потребляется в шаге 5, после этого GC.

**Где применяется DiskCached декоратор:** оборачивает дорогие sources (speech — 10-30 мин wall clock) и дорогие мерджеры (LLM merger — 30-60 сек локально, $ + latency у API). Дешёвые компоненты (chat/game log sources, детерминированный `ScriptMerger`) не оборачиваются. Кэш живёт в `session_dir/_cache/sources/` и `session_dir/_cache/mergers/` соответственно. Рендереры не кэшируются — их вывод и так записывается пользователю в итоговый файл.

**Где happens merge:** в `ScriptMerger.merge()`, чистая функция от `Timeline` к `list[ScriptEvent]`. Merger проецирует EmotionTag на пересекающийся SpeechEvent (заполняя поле `emotion`), разрешает overlapping речь через `parallel_group`, интерливит ChatMessage и GameLogEntry между SpeechEvent-ами по времени `at`.

---

## 7. Migration plan

### Приоритет 2: полная перестройка (Variant A)

В одном приоритете вводятся все шесть слоёв: `ui/`, `core/`, `sources/`, `mergers/`, `renderers/`, `domain/`. Это **отменяет более ранний план постепенной миграции** (старый ADR «no big-bang» пересмотрен — см. ADR-9 ниже).

Обоснование перестройки в один приоритет:
- Контракты между слоями (Source, Merger, Renderer) настолько тонкие, что дробление по приоритетам создаёт временные shim-ы которые потом всё равно выкидывать.
- Без нового Merger нельзя добавить chat / emotion / game log как равноправные элементы — это блокирует Приоритеты 4-6.
- Тесты (Приоритет 3) пишутся уже по целевой структуре, не по промежуточной.

Что делает Приоритет 2 конкретно:
1. Создаёт папки `ui/`, `core/`, `sources/`, `mergers/`, `renderers/`, `domain/` с `__init__.py`.
2. Переносит `speaker_map.py` в `domain/`, создаёт `domain/annotations.py` и `domain/events.py`.
3. Оборачивает текущий subprocess вызов whisperx в `sources/speech/whisperx.py` как `Source`.
4. Добавляет `sources/speech/faster_whisper.py` (новый backend через Python API).
5. Оборачивает `parse_fvtt_chat.py` в `sources/game_log/fvtt_chat.py` как `Source`.
6. Переписывает `merge_whisperx.py` в `mergers/script_merger.py` реализующий новый `Merger` ABC и выдающий `list[ScriptEvent]`.
7. Создаёт `renderers/plain_text.py` который генерирует байтовый вывод эквивалентный текущему `merged.txt`.
8. Создаёт `core/pipeline.py`, `core/discovery.py`, `core/gpu_check.py`, `core/timeline.py`.
9. Переписывает CLI и GUI части `wisper_launcher.py` как `ui/cli.py` и `ui/gui.py`, они вызывают `core.pipeline.run(...)`.
10. Старый `scripts/wisper_launcher.py` удаляется. Старый `scripts/merge_whisperx.py` удаляется. `scripts/parse_fvtt_chat.py` удаляется.

Эквивалентность вывода с legacy проверяется end-to-end тестом: фиксированный аудио + chat log даёт байт-в-байт тот же `merged.txt` до и после.

### Приоритеты 3-6: только расширение существующих слоёв

| Приоритет | Слой | Действие |
|---|---|---|
| 3 | `tests/` | Pytest skeleton, fixtures, CI, ruff. Не меняет слои, добавляет инфраструктуру. |
| 4 | `sources/speech/` | Добавить `sherpa_onnx.py` (GigaAM-v3 RNNT). Новый файл в уже готовом слое. Контракт `Source` не меняется. |
| 5 | `ui/` | Миграция tkinter → PySide6 если выбрана. Остальные слои не трогаются. Возможно `renderers/markdown.py` / `renderers/obsidian.py`. |
| 6 | `mergers/`, `sources/emotion/` | Добавить `LocalLLMMerger` и/или emotion source. Всё additive. |

Если после P2 обнаружится что какой-то слой спроектирован неправильно — исправлять его придётся точечно, не полным рефакторингом. Это акцептабельный риск: контракты достаточно узкие (три ABC, четыре dataclass) чтобы проверить их на бумаге перед реализацией.

---

## 8. Design decisions & rationale

ADR-стиль: каждое решение + контекст + последствия. Эти решения зафиксированы и не пересматриваются без явной причины.

### ADR-1: Three-stage pipeline (Sources → Merger → Renderer)

**Decision:** Разделение извлечения, комбинирования и форматирования на три независимых стадии со strategy pattern на каждой. Источники возвращают raw annotations, merger комбинирует Timeline в плоский `list[ScriptEvent]`, renderer превращает в файл.

**Context:** Текущий `wisper_launcher.py` смешивает все три ответственности. Добавить новый формат вывода (markdown), новый источник (эмоции) или новую стратегию merge (LLM) нельзя без трогания соседей.

**Consequences:**
- (+) Независимая эволюция слоёв: новый ASR backend не трогает рендереры; новый формат вывода не трогает sources.
- (+) Каждая стадия тестируется изолированно с синтетическими fixture-ами.
- (+) LLM merger в будущем подключается как ещё одна реализация `Merger` ABC, остальной код не меняется.
- (−) Больше файлов и папок чем сейчас. Приемлемо: каждый файл простой.

### ADR-2: Discriminated union для ScriptEvent вместо monolithic dataclass

**Decision:** `ScriptEvent = SpeechEvent | ChatEvent | GameEvent` — три независимых dataclass, не один с `kind: Literal[...]` и `attributes: dict`.

**Context:** Monolithic вариант (`ScriptEvent` с полем `kind` и общим `attributes: dict`) ведёт к stringly-typed bag: рендерер проверяет `if event.kind == "chat": event.attributes["author"]` без помощи типизатора. В Python 3.10+ sum type + `match` statement дают exhaustive checking через mypy.

**Consequences:**
- (+) Добавление нового типа события: новый dataclass + обновить `match` в рендерерах. Mypy показывает где забыл.
- (+) Нет defensive parsing в рендерерах — поля типизированы на уровне каждого варианта.
- (+) Для Kotlin разработчика читается как sealed hierarchy, для C++ — как `std::variant`.
- (−) Нельзя сделать полиморфный список полей (но он и не нужен — по factу у типов совершенно разные атрибуты).

### ADR-3: Emotion как поле SpeechEvent, не отдельный event type

**Decision:** На merger output уровне эмоция живёт как поле `SpeechEvent.emotion: str | None`, не как отдельный `EmotionEvent` в sequence. На raw уровне (`sources/`) `EmotionTag` остаётся отдельным типом в Timeline. Merger проецирует EmotionTag на соответствующий SpeechEvent по временному пересечению.

**Context:** Эмоция без речи бессмысленна для текстовых рендереров. Показывать «[00:04-00:06] emotion: angry» без текста — шум, не информация. Альтернатива — держать EmotionEvent в sequence — заставляет каждый рендерер решать что с ним делать.

**Consequences:**
- (+) Renderer просто печатает `event.emotion` рядом с репликой, один if.
- (+) Merger может **разбить** SpeechEvent на два если эмоция меняется в середине фразы — и оба получат соответствующее значение `emotion`.
- (+) EmotionTag на raw уровне сохраняется как есть — если появится не-текстовый рендерер (waveform UI), он читает Timeline (через custom merger) и видит эмоции отдельно.
- (−) Merger чуть сложнее — проекция вместо passthrough. Приемлемо: это один из главных смыслов существования merger-а.

### ADR-4: parallel_group для overlapping speech

**Decision:** Overlapping речь (два спикера одновременно) представляется как два соседних `SpeechEvent` с одинаковым `parallel_group: int`. Merger решает порядок и присваивает id. Renderer применяет **единственное правило**: если `event.parallel_group == prev.parallel_group`, добавить маркер одновременности в вывод.

**Context:** Физически overlapping unresolvable в линейную последовательность без information loss. Flat контракт (`list[ScriptEvent]`) требует какого-то решения. Альтернатива — `ParallelSpeech` dataclass с `list[SpeechEvent]` внутри — добавляет вложенность и усложняет рендереры сразу.

**Consequences:**
- (+) Renderer остаётся «dumb»: одно правило, никакой рекурсии по вложенности.
- (+) LLM merger может превратить parallel_group в narrative rewrite («Alice замахивается, Bob перебивает»), не трогая контракт.
- (+) Simple merger (P2) ставит id только когда intervals реально пересекаются, остальные события имеют `parallel_group = None`.
- (−) Структурная группировка потребует миграции если понадобится. Migration path: добавить `ParallelSpeech` дополнительным вариантом union — existing рендереры продолжают работать с `SpeechEvent`, новые используют вариант.

### ADR-5: LLM merger разбивает SpeechEvent для inline вставок, не зашивает маркеры в text

**Decision:** Когда (будущий) LLM merger хочет вставить GameEvent внутрь реплики, он **разбивает** `SpeechEvent` на два соседних и ставит `GameEvent` между ними. Он **не** вставляет маркеры вида `[[roll:18]]` в поле `text`.

**Context:** Если маркеры зашиваются в text, рендерер вынужден парсить строки — это ломает типизированный flat контракт и перекладывает знание о домене на каждый рендерер.

**Consequences:**
- (+) Рендерер работает только с типами, никакой string parsing.
- (+) Юнит-тесты merger-а проверяют что `text` не содержит структурированных маркеров (regex guard в тесте).
- (+) Script merger (P2) не умеет разбивать — он ставит GameEvent соседним элементом после речи, это деградирует качественно но не ломает контракт.
- (−) LLM merger чуть сложнее: надо решить по какой границе разбивать. Это его legitimate работа.

### ADR-6: Timeline — внутренний in-memory контейнер, не публичный контракт

**Decision:** `Timeline` живёт в `core/timeline.py`, собирается in-memory из source outputs, передаётся merger-у. Не имеет `schema_version`, не сериализуется публично, не доступна рендерерам. Единственные публичные контракты — `list[Annotation]` на выходе source и `list[ScriptEvent]` на выходе merger.

**Context:** Ранее обсуждалось сделать Timeline публичным контрактом (для будущего interactive UI где виджеты показывают слои отдельно). Но `ScriptEvent` содержит достаточно данных (start, end, speaker, text, emotion, parallel_group) для interactive use case.

**Consequences:**
- (+) Упрощение публичной поверхности API: два контракта вместо трёх.
- (+) Timeline может свободно эволюционировать — добавление нового слоя (например `dice: list[DiceRoll]`) не требует обновления schema_version или миграции.
- (+) Interactive рендерер (если появится) работает через `ScriptEvent` + свой custom merger который сохраняет структуру.
- (−) Если захочется кэшировать Timeline между запусками мерджера (для итерации merger стратегий) — придётся ввести internal format. Это делает `DiskCachedSource` на уровне sources (источники дорогие, Timeline сборка дешёвая).

### ADR-7: DiskCached decorator — performance optimization для Source и Merger, не публичный контракт

**Decision:** DiskCached — это **два параллельных decorator-а** над существующими ABC: `DiskCachedSource(Source)` и `DiskCachedMerger(Merger)`. Оба живут в `core/cache.py`, кэшируют output в `session_dir/_cache/{sources|mergers}/<name>.json`. Формат кэша **внутренний**, может меняться между версиями. Инвалидация через hash конфига + hash входных данных. Не документируется как пользовательский формат. Рендереры сознательно исключены — их результат и так материализуется на диске как итоговый файл.

**Context:**
- Транскрипция whisper занимает 10-30 минут wall clock на сессию. Итерация merger стратегий без кэша требует перегона ASR каждый раз — неприемлемо.
- LLM merger (локальная Qwen 7B ~30-60 сек на сессию, API — $ + latency) имеет тот же характер дорогостоящей детерминированной функции. Итерация рендереров или post-processing поверх merger output-а без кэша перегоняет LLM каждый раз — та же проблема что с ASR, тот же паттерн решения.
- Альтернатива «сделать один generic `DiskCached[T]` декоратор поверх абстрактного `Callable[input, output]`» отвергнута: Source и Merger имеют разные input типы (`Path` vs `Timeline`), разные ключи кэша, разные стратегии инвалидации. Два узких decorator-а проще и честнее чем generic который всё равно внутри разветвляется.

**Consequences:**
- (+) Первый запуск медленный, последующие быстрые — и для ASR, и для LLM merger.
- (+) Decorator pattern — применяется selectively к дорогим компонентам. `ScriptMerger` (P2, детерминированный, миллисекунды) не оборачивается, `LocalLLMMerger` (P6+) оборачивается.
- (+) Пользователь может удалить `_cache/` целиком или подпапку (`_cache/mergers/`) — следующий запуск пересчитает именно её.
- (+) Расширение концепции не ломает существующие контракты: `DiskCachedSource` сохраняет текущую семантику, `DiskCachedMerger` добавляется additively.
- (−) Нужна стратегия инвалидации для мерджера: hash от `Timeline` + hash конфига мерджера. Timeline hash нетривиален (нужна каноническая сериализация dataclass-ов). Детали — при реализации `LocalLLMMerger` (не в P2, P2 сам по себе в кэше не нуждается).
- (−) Риск расхождения: если кэшированный merger output собран из устаревшего Timeline (например после пересчёта speech source), нужно инвалидировать. Митигация: Timeline hash включается в ключ кэша мерджера.

### ADR-8: Canonical JSON minimum — только required поля

**Decision:** JSON на выходе speech source содержит только `start`, `end`, `text`, `source_engine`, `schema_version`. Optional поля (`confidence`, `no_speech_prob`, `words`) не включаются пока их реально никто не читает.

**Context:** Соблазн заложить «на будущее» metadata поля для QA / тюнинга / аналитики. Но ни один текущий consumer их не читает. YAGNI.

**Consequences:**
- (+) Canonical JSON остаётся читаемым человеком.
- (+) Меньше расхождений между backend-ами (нечего нормализовывать).
- (+) При появлении consumer — добавить поля additively, bump `schema_version`. Миграция тривиальна.
- (−) Если в P4 сравнение backend-ов по confidence понадобится — придётся добавлять поле тогда. Это нормальный flow.

### ADR-9: Big-bang refactor в Приоритете 2 (отмена предыдущего запрета)

**Decision:** Все шесть слоёв вводятся в одном приоритете (P2), а не поэтапно. Это прямо отменяет ранее зафиксированный принцип «один слой за приоритет».

**Context:** Прошлая версия ADR запрещала big-bang refactor из страха перед длинными ревью и регрессиями. Но при ближайшем рассмотрении контракты между слоями настолько тонкие (три ABC + четыре dataclass), что временные shim-ы между поэтапными версиями стоят дороже чем одна согласованная перестройка. Кроме того, новый Merger нужен чтобы разблокировать chat/emotion/game log как равноправные элементы — без него P4-P6 упираются.

**Consequences:**
- (+) Нет временных компромиссных структур которые потом выкидывать.
- (+) Тесты P3 пишутся сразу по целевой архитектуре.
- (+) Контракты проверены на бумаге в этом документе до начала кодинга — риск переделки снижен.
- (−) PR Приоритета 2 большой. Митигация: разбивается на последовательность логических коммитов (domain → sources → mergers → renderers → core → ui → удаление legacy) с working сборкой на каждом шаге. End-to-end тест эквивалентности с legacy фиксирует что поведение не сломано.
- (−) Если в P2 обнаружится ошибка проектирования — откат более болезненный. Митигация: отдельная ветка, merge только когда e2e эквивалентность подтверждена.

### ADR-10: Один слой за папку, folder-based модули вместо `src/` layout

**Decision:** `sources/`, `mergers/`, `renderers/`, `domain/`, `core/`, `ui/` — каждая папка соответствует слою, публично импортируемые сущности выставлены в `__init__.py`. Никакого `src/discord_session_transcriber/` layout.

**Context:** Современный Python style рекомендует `src/` layout для распространяемых пакетов. Это правильно для библиотек на PyPI. Наш проект — приложение с точкой входа, в master-плане PyPI не запланирован.

**Consequences:**
- (+) Контрибьюторам из Kotlin/Java привычно: папка = package.
- (+) Не нужно обновлять PyInstaller spec и installer пути.
- (+) Dependency rules проверяются ревьюером + ruff, не build system.
- (−) Если решим публиковать на PyPI — потребуется отдельный refactor. Acceptable.

### ADR-11: Plugin extensibility — hardcoded registry now, pip entry_points позже, самописный plugin system отвергнут

**Decision:** Discovery и регистрация Source/Merger реализаций происходит через hardcoded Python registry в `sources/__init__.py` и `mergers/__init__.py` в P2. В будущем (при появлении триггера) добавляется поддержка pip entry_points additively: registry сначала читает hardcoded mapping, затем сканит `importlib.metadata.entry_points(group="dst.sources")` и `group="dst.mergers"`. Самописный plugin system с манифестами, self-installer, централизованным каталогом и downloader-ом моделей отвергнут.

**Context:** Предложение сделать каждый backend отдельным GitHub репо с self-installer-ом рассмотрено и отклонено. Индустриальные precedent-ы (Stable Diffusion WebUI, ComfyUI, Jupyter kernels, VSCode extensions) либо опираются на native package manager языка, либо требуют dedicated marketplace infrastructure. Для solo-разработчика с 3 планируемыми backends (faster-whisper, sherpa-onnx, whisperx legacy) и нетехнической целевой аудиторией стоимость самописного plugin system (примерно 8-10 ADR + 5-7 новых core модулей + отдельный репо для каталога) не окупается. Pip + entry_points покрывают 95% use cases (code discovery, dependency management, версионирование, install/uninstall/upgrade) бесплатно. Веса моделей — отдельный lifecycle и решаются на уровне backend-а (HuggingFace Hub, sherpa-onnx downloader, кэш в `%LOCALAPPDATA%/models/`), не через plugin installer.

**Triggers для перехода на entry_points:**
- Первый не-авторский PR с новым backend, ИЛИ
- Backend pool вырастает до 6+, ИЛИ
- Пользовательский запрос на «только-один-backend» установку (bundle size).

**Consequences:**
- (+) P2 пишется без plugin infrastructure overhead — 15 строк registry.
- (+) Переход на entry_points позже additive, не ломает существующие backends.
- (+) Веса моделей остаются под контролем backend-авторов через стандартные механизмы (HuggingFace cache), без дублирования infrastructure.
- (+) Solo разработчик не тащит поддержку каталога, версионирования плагинов, security/signing, update mechanism.
- (−) Если 3-я сторона захочет добавить backend до триггера — ей придётся сделать PR в main репо вместо независимой публикации. Acceptable: это нормальный open-source workflow на раннем этапе проекта.
- (−) Если решим добавить marketplace UI с иконками и рейтингами — это всё равно будет отдельный трек поверх entry_points, не замена текущего подхода. Acceptable.

### ADR-12: `Timeline` живёт в `domain/`, а не в `core/`

**Decision:** `Timeline` dataclass переносится из `core/timeline.py` в `domain/timeline.py`. Ранние версии этого документа (§5.2, §4) размещали его в `core/`.

**Context:** Dependency rules секции 3 запрещают `mergers → core`. Но `Merger.merge()` имеет сигнатуру `merge(timeline: Timeline) -> list[ScriptEvent]` — значит `mergers/base.py` обязан импортировать `Timeline`. Если Timeline в `core/`, то `mergers` вынужден импортировать из `core` — нарушение. Обнаружено при декомпозиции P2 перед началом реализации.

**Consequences:**
- (+) Dependency rules строго выполняются: `mergers → domain only`, `core → domain + sources + mergers + renderers`.
- (+) Timeline остаётся pure dataclass без поведения — его естественное место в `domain/`, не в `core/`.
- (+) `core` продолжает содержать orchestration (`pipeline.py`), discovery, GPU check, cache — всё что требует знать о sources/mergers/renderers.
- (−) Ранняя текстовая версия документа упоминала `core/timeline.py` — обновлена в §5.2 и §4 (диаграмма). Эта ADR фиксирует изменение для истории.
- (−) Философски Timeline «internal container для core.pipeline» — это orchestration-layer concept. Но dependency rules важнее философии: если тип пересекает границы, он идёт в тот слой который видят обе стороны. В данном случае `domain` — единственный такой слой (его видят все).

---

## 9. Glossary (для контрибьюторов из Kotlin/C++)

| Python | Kotlin / C++ аналог | Смысл |
|---|---|---|
| `ABC` + `@abstractmethod` | `interface` / pure virtual class | контракт без реализации, наследник обязан переопределить |
| `@dataclass` | `data class` / struct | value object, автогенерация `__init__`, `__eq__`, `__repr__` |
| `A \| B \| C` (PEP 604 union) | sealed hierarchy / `std::variant` | discriminated union; `match` statement + mypy дают exhaustiveness |
| `Literal["a", "b"]` | enum class / scoped enum | строго ограниченный набор строковых значений |
| `match event: case SpeechEvent(...):` | `when (event) is Speech ->` | pattern matching по типу, exhaustive если union закрыт |
| `Path` (`pathlib`) | `java.nio.Path` / `std::filesystem::path` | типизированный путь к файлу/папке |
| `@classmethod` | companion object method / static method | метод класса без instance |
| module (`.py` файл) | package + file | единица импорта |
| package (папка с `__init__.py`) | gradle module / namespace | группа модулей с публичным API |
| registry `dict` (имя → класс) | DI container (упрощённый) | factory по строковому имени |
| `str \| None` | `String?` / `std::optional<std::string>` | nullable type (Python 3.10+) |
| decorator pattern (`DiskCachedSource(wrapped)`) | class decorator / wrapper | class который оборачивает другой, реализуя тот же интерфейс |
| `raise ValueError(...)` | `throw IllegalArgumentException` | исключение в типе данных |
| f-string `f"hello {name}"` | string template `"hello $name"` | интерполяция |
| `if __name__ == "__main__":` | `fun main()` / `int main()` | точка входа модуля |
