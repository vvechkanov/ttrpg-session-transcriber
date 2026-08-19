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

## 2. Состояние ДО перестройки (историческая справка)

> Раздел описывает то, что было **до** Приоритета 2, и оставлен ради ADR
> ниже: без него непонятно, от чего они отталкивались. Ничего из
> перечисленного здесь в дереве больше нет. Как устроен проект сегодня — §3,
> §4 и §6.

Тогда проект был слабо структурированным монолитом из трёх скриптов в
`scripts/`: запускалка на 1003 строки, движко-независимый мерджер и парсер
фаундривского чата. Имена файлов здесь намеренно не названы — документ
описывает то, что есть; за именами есть история git.

Запускалка совмещала пять ответственностей: argparse CLI, tkinter GUI,
subprocess-вызов whisperx, оркестрацию пайплайна и GPU pre-flight.

**Что в том состоянии было хорошо** (и что перестройка обязана была
сохранить):
- Мерджер не был привязан к WhisperX: читал только `start`/`end`/`text` на
  сегмент, говорящего брал из `speaker_map.json`. Любой backend с canonical
  JSON работал без его изменений.
- Парсер чата был набором чистых функций, без I/O в пайплайне.

**Что было плохо** (и ради чего затевался Приоритет 2):
- Пять ответственностей в одном файле: любое изменение GUI рисковало сломать
  CLI и наоборот.
- Транскрипция была прибита к `whisperx` через subprocess. Добавить второй
  backend можно было только через `if`/`else` в оркестраторе.
- Мерджер умел лишь склеивать речевые сегменты одного говорящего по паузе.
  Добавить chat, game log или эмоции как равноправные элементы было некуда.
- Тестов не было вовсе.

---

## 3. Target state

К концу Приоритета 2 проект декомпозирован на **шесть папок**, каждая соответствует слою. Направления импортов строго однонаправленные.

```
┌────────────────────────────────────────────────────────────┐
│  ui/                                                        │
│  cli.py, app_qml.py, models, engines, qml      — см. §4.1   │
│  argparse, QML-шелл, сбор params, progress display          │
└───────────────────────┬─────────────────────────────────────┘
                        │ imports
┌───────────────────────▼─────────────────────────────────────┐
│  core/                                                       │
│  pipeline.py, discovery.py, gpu_check.py, asr.py, …          │
│  orchestration: discover → extract → assemble timeline →     │
│  merge → render                                              │
└──┬─────────────────┬──────────────────┬────────────┬────────┘
   │ imports         │ imports          │ imports    │ imports
   ▼                 ▼                  ▼            ▼
┌──────────┐    ┌──────────┐      ┌──────────┐   ┌──────────┐
│ sources/ │    │ mergers/ │      │renderers/│   │ domain/  │
│          │    │          │      │          │   │          │
│ speech   │    │script_   │      │plain_    │   │annotat-  │
│ game_log │    │merger.py │      │text.py   │   │ions.py   │
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

> **Правило `ui` → `core` сейчас нарушено, и это не описка в списке.**
> `ui/engines/merger_worker.py` импортирует `mergers`, `renderers` и
> `domain` напрямую, минуя `core`, и дополнительно тянет `sources.game_log`
> ленивыми импортами внутри `_parse_chat()` и `_parse_combat_dumps()` —
> такие рёбра легко не заметить глазами. `ui/engines/asr_worker.py` и
> `ui/engines/pipeline_controller.py` импортируют `domain.annotations`.
> Список составлен чтением импортов и может быть неполон, пока его не
> проверяет машина. Причина в §4.1: GUI не зовёт `core.pipeline.run`, а
> воспроизводит его шаги у себя, и вместе с шагами утащил зависимости.
> Машина этого не ловит: `import-linter` числится в `docs/process.md`, §7.1,
> как работа впереди, а не как действующий гейт, и конфигурации для него в
> дереве нет.
> Записано здесь, чтобы расхождение было видно, а не считалось соблюдённым.

---

## 4. Layer responsibilities

| Слой | Делает | НЕ делает |
|---|---|---|
| `ui` | argparse parsing, QML-шелл, сбор params, запуск воркеров на отдельных потоках, отображение прогресса/ошибок | ASR, subprocess вызовы. **Оговорка:** `MergerWorker` из `ui/engines` сам зовёт мерджер, рендерер и пишет итоговый файл — см. §4.1 |
| `core` | file discovery, GPU pre-flight, оркестрация pipeline, сборка `Timeline` (тип из `domain/`) в памяти, выбор конкретных Source/Merger/Renderer через registry, disk cache decorators | сама транскрипция, сам merge алгоритм, сам рендеринг текста, определение `Timeline` (он в `domain/`) |
| `sources` | извлечение аннотаций из входных данных (аудио, FVTT chat, будущие игровые логи), возврат `list[Annotation]` | pipeline orchestration, merge, форматирование вывода |
| `mergers` | комбинирование `Timeline` в плоскую упорядоченную `list[ScriptEvent]` — разрешение overlaps, проекция эмоций на речь, интерливинг chat/game event-ов | извлечение данных, форматирование вывода |
| `renderers` | форматирование `list[ScriptEvent]` в итоговый формат (plain text, markdown, html, obsidian) | решения что с чем объединять, обращение к sources / mergers |
| `domain` | pure dataclass-ы для аннотаций и событий, вспомогательные функции без I/O (speaker_map) | subprocess, ASR, GUI, file I/O |

### 4.1 Внутри `ui/`: три подслоя

У `sources/` деление тоже есть (`sources/speech/`, `sources/game_log/`), но там это просто вид
источника. В `ui/` подслои отличаются ролью и потоком, в котором живут, поэтому
им нужен отдельный разбор. Таблица выше говорит, чего слой не делает; здесь —
как он устроен внутри.

| Подслой | Что там | Правило |
|---|---|---|
| `ui/models` | `QObject` и `QAbstractListModel`, которые QML видит как свойства и модели: `AppModel`, `AppPreferences`, `ModelRegistry`, `SessionMeta`, `TrackListModel`, `SourceListModel` | Держат состояние и отдают его в QML. Долгую работу не делают — она уходит в `ui/engines` |
| `ui/engines` | воркеры на отдельных потоках: `AsrWorker`, `MergerWorker`, `PeaksWorker`, `InstallWorker` — и оркестратор `PipelineController` | Воркеры считают и про QML не знают ничего. Сигналы — их канал **наружу**, а не единственный способ с ними говорить: работу они получают аргументами конструктора, а тех, у кого есть `cancel()`, останавливают прямым вызовом извне (три разных варианта отмены разобраны ниже). `PipelineController` — исключение и в другом: он отдаётся в QML контекст-проперти, объявляет `Property` ради биндингов и держит ссылки на модели из `ui/models`, вызывая их методы напрямую |
| `ui/qml` | сам шелл: `ui/qml/Main.qml`, `ui/qml/Theme.qml`, плюс `ui/qml/screens/`, `ui/qml/controls/`, `ui/qml/timeline/`, `ui/qml/drawers/`, `ui/qml/popovers/` | Разметка и анимация. Никакой доменной логики |

**Зависимость между `ui/models` и `ui/engines` — в обе стороны, и это стоит
знать до того, как двигать импорты.** `PipelineController` из `engines` держит
ссылки на модели и зовёт их методы; в обратную сторону `ModelRegistry` из
`models` сам создаёт `InstallWorker` из `engines` и поднимает ему поток.
Цикла на уровне модулей нет только потому, что одна из сторон импортирует тип
отложенно. Считать эту границу однонаправленной нельзя.

**Потоки.** Воркеры устроены по идиоме Qt `QObject + moveToThread(QThread)`, а не
наследованием от `QThread`. Каждый воркер — `QObject` с `Slot`-ом, который зовут
из своего потока, и набором `Signal`-ов наружу.

Отмена устроена в трёх вариантах, и смотреть надо не только на то, что воркер
умеет, но и на то, что ему реально присылают.

`AsrWorker` умеет оба канала — внешний `QThread.requestInterruption()` и
собственный слот `cancel()` — и оба ему приходят: `PipelineController.cancel()`
дёргает `requestInterruption()` на ASR-потоке и вызывает `worker.cancel()`.

Гранулярность при этом **внутри дорожки, а не между ними**, и это стоит знать
прежде, чем рассчитывать на «дорожка либо расшифрована, либо нет». Обе
проверки свёрнуты в замыкание `_should_cancel`, которое уходит аргументом в
`core.asr.transcribe_one_track` и опрашивается в тесном цикле самого источника
— у GigaAM на каждом окне VAD, у faster-whisper между декодированными
сегментами. Поэтому отмена останавливает расшифровку посреди файла, а источник
возвращает то, что успел. Наружу это не течёт: `AsrWorker` в таком случае
просто не испускает `done`, и частичный результат никуда не идёт.

`MergerWorker` умеет оба, но подключён один. `PipelineController.cancel()`
трогает только `self._thread` — это поток ASR; `self._merge_thread`
`requestInterruption()` не получает никогда, до мерж-воркера доходит лишь
прямой вызов `cancel()`. Рассчитывать на прерывание потока во время мержа
нельзя, пока эта проводка не появится.

У `PeaksWorker` канал один — слот `cancel()` со своим флагом; им пользуется
`ui/app_qml.py`, когда выбранная папка сменилась и старый расчёт уже не нужен.
У `InstallWorker` отмены нет ни в каком виде — а он единственный, кто качает и
распаковывает файлы; прервать установку бэкенда сейчас нечем.

**Сигналы.** Имена — не описание, а то, что реально объявлено в коде:

| Воркер | Сигналы |
|---|---|
| `ui/engines/asr_worker.py::AsrWorker` | `progress(int, float)`, `done(int, list)`, `error(int, str)`, `finished()` |
| `ui/engines/merger_worker.py::MergerWorker` | `progress(float)`, `gapFilled(float, str)`, `done(str)`, `error(str)`, `finished()` |
| `ui/engines/peaks_worker.py::PeaksWorker` | `peaksReady(int, int, list)`, `durationReady(float)`, `segmentDurationReady(int, int, float)`, `allDone()` |
| `ui/engines/install_worker.py::InstallWorker` | `progress(int, str)`, `done(str)`, `error(str)` |

Как гасится поток — у каждого воркера по-своему, и это стоит смотреть, а не
предполагать. `AsrWorker` и `MergerWorker` испускают `finished()` на **каждой**
ветке выхода, включая ошибку и отмену; поток-владелец подписан на него своим
`quit`. У `PeaksWorker` ту же роль играет `allDone`. У `InstallWorker` сигнала
`finished` нет вовсе — `ModelRegistry` вешает `quit` сразу на `done` и `error`.

**Точки входа — и они ведут в разные места.** `python -m ui` попадает в
`ui/__main__.py`, оттуда в `ui.main()` (`ui/__init__.py`), который смотрит на
`sys.argv`: без аргументов — GUI (`ui/app_qml.py`, `QQmlApplicationEngine` +
`ui/qml/Main.qml`), с аргументами — CLI (`ui/cli.py`).

Дальше пути расходятся, и это стоит знать прежде, чем считать фичу доехавшей:

- **CLI** зовёт `core.pipeline.run` целиком — но не со всеми стадиями из §6.
  `ui/cli.py` не кладёт `ChunkingOptions` в `PipelineParams`, поэтому стадия
  `"chunk"` внутри `run` не выполняется никогда; при `--chunk` чанкинг идёт
  отдельным пост-шагом (`_run_chunk_post_step`) уже после возврата из `run`.
  Подробнее — в §6.
- **GUI не зовёт `core.pipeline.run` вообще.** `PipelineController` держит
  собственную очередь дорожек и гоняет по одной `AsrWorker` на `QThread`
  (через `core.asr.transcribe_one_track`), а когда очередь опустеет —
  запускает `MergerWorker` на втором потоке. Стадия рендера схлопнута внутрь
  merge-воркера, чанкинг контроллер делает синхронно у себя.

Отсюда практическое следствие: фича, добавленная в `core.pipeline.run`, видна
в CLI и **не видна в GUI**, пока её не провели через `PipelineController` или
`MergerWorker`. Дважды за неделю «сделано» оказывалось мёртвым кодом ровно
по этой причине.

### 4.2 Launcher и runtime — два разных исполняемых файла

Собираются двумя разными спеками, и это не одно приложение в двух видах:

| | Спека | Точка входа | Что это |
|---|---|---|---|
| Launcher | `launcher/build.spec` | `launcher/bootstrap.py` | Bootstrap-инсталлер. Исключает `PySide6` целиком — UI живёт в другом exe |
| Runtime | `build.spec` в корне | `ui/app_qml.py` | Само приложение: шесть слоёв и QML-шелл |

Runtime собирается **папочным** дистрибутивом, а не одним файлом: это условие
LGPL — пользователь должен иметь возможность подменить Qt-библиотеки.

Тяжёлый ML-стек не входит **ни в один** из них и не значится в зависимостях
`pyproject.toml`. `core/backend_installers.py` доставляет во время работы
ровно два бандла: GigaAM-v3 RNNT поверх sherpa-onnx и faster-whisper
large-v3-ru. Поэтому bootstrap остаётся маленьким, а пользователь скачивает
веса только того бэкенда, который выбрал.

`torch` не ставит ни один из них, и `core/backend_installers.py` тоже: он
знает только про бандлы GigaAM/sherpa и faster-whisper. Источник
`sources/speech/whisperx.py`, которому torch нужен, остаётся в дереве, и
поставить его есть чем — `scripts/install_whisperx_windows.ps1` тянет колёса
torch (CPU или CUDA) и сам WhisperX в venv проекта. Это путь разработчика, а
не часть продукта: ни один exe его не запускает и в бандлы он не входит. По
решению из `TASKS.md` (C2) WhisperX вообще подлежит удалению из master.

Здесь же — всё, что осталось в проекте от tkinter: окно установщика
(`launcher/installer_ui.py`), окно удаления (`launcher/uninstaller_ui.py`) и
аварийный диалог ошибки в `launcher/bootstrap.py`. В слое `ui/` его нет, и
корневая спека исключает его из бандла явно — но выкидывать tkinter из проекта
целиком нельзя, пока эти три места живы.

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

    #: Момент старта записи — единственное, что связывает относительные
    #: ``at`` аннотаций с настоящим временем. Aware-datetime в зоне самой
    #: сессии, не в UTC: иначе каждый рендерер обязан был бы выяснять зону
    #: сам, а взять её неоткуда, кроме как разобрав чат.
    recording_start: datetime | None = None
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
    wall_clock: datetime | None = None   # см. ниже

@dataclass
class ChatEvent:
    at: float
    channel: Literal["ic", "ooc"]
    author: str
    text: str
    wall_clock: datetime | None = None

@dataclass
class GameEvent:
    at: float
    actor: str
    action: str                          # открытое множество, не Literal:
                                         # roll, damage, spell, encounter_start,
                                         # encounter_end, round_start, turn_start
    detail: str
    wall_clock: datetime | None = None

ScriptEvent = SpeechEvent | ChatEvent | GameEvent
```

`wall_clock` — то, как абсолютное время доезжает до рендерера. `Renderer.render`
получает только `list[ScriptEvent]` и `Timeline.recording_start` не видит, поэтому
мерджер раскладывает его по событиям заранее. Без этого поля рендерер, желающий
напечатать «19:11», взять этот час неоткуда.

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

> **Статус на сегодня: заготовка, а не работающий кэш.** В `core/cache.py`
> объявлен только `DiskCachedSource`, его `_load`/`_save` поднимают
> `NotImplementedError`, а `core/pipeline.py` этот модуль не импортирует
> вовсе. `DiskCachedMerger` не написан. Ниже — целевой контракт, по которому
> интерфейс зарезервирован; читать его как описание работающего кода нельзя.

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
ui/cli.py собирает params → core.pipeline.run(session_dir, params)
       │
       ▼
┌──────────────────── core.pipeline.run ───────────────────┐
│                                                           │
│  "start"   check_gpu_or_warn(params.device)              │
│                                                           │
│  "speech"  SPEECH_SOURCES[params.speech_backend]         │
│               .extract(session_dir) → list[SpeechSegment]│
│                                                           │
│  "chat"    find_fvtt_chat_log → FvttChatSource           │
│               .extract(session_dir) → list[ChatMessage]  │
│            (или "no chat log" — стадия всё равно есть)   │
│                                                           │
│  "combat"  каждый найденный боевой дамп →                │
│            CombatDumpSource.extract(session_dir)         │
│               → list[GameLogEntry]                       │
│                                                           │
│            Timeline(speech=…, chat=…, game_log=…,        │
│                     emotions=…, recording_start=…)       │
│            — собирается здесь, своей стадии не имеет     │
│                                                           │
│  "merge"   MERGERS[params.merger]().merge(timeline)      │
│               → list[ScriptEvent]                        │
│                                                           │
│  "render"  get_renderer(params.renderer).render(events)  │
│            → bytes → запись на диск                      │
│                                                           │
│  "chunk"   только если params.chunking включён           │
│                                                           │
│  "done"    путь итогового файла                          │
│                                                           │
└──────────────────────────────────────────────────────────┘
       │
       ▼
ui/ отображает результат пользователю
```

**Стадии — это контракт.** `core/pipeline.py::PipelineStage` перечисляет их
исчерпывающе. Это API `core` для прогресса (`on_stage: StageCallback`) —
и сейчас его **никто не использует**: `ui/cli.py` зовёт `run` и `run_batch`
без колбэка, так что все стадии уходят в `_noop_stage`, а у GUI свои каналы
(`core.asr.transcribe_one_track(on_progress=…)` для дорожек и `InstallProgress`
из `sources/base.py` для установки бэкендов). То есть контракт есть,
потребителя у него нет:

```python
PipelineStage = Literal[
    "start", "speech", "chat", "combat", "merge", "render", "chunk", "done"
]
```

Восемь имён. `"chat"` и `"combat"` испускаются даже когда соответствующего
файла нет — с сообщением `"no chat log"` / `"no combat dump"`, чтобы UI мог
показать пропуск, а не тишину. `"chunk"` — единственная условная: только при
включённом чанкинге. Прогресс намеренно постадийный, без процента внутри
стадии.

Стадию `"chunk"` при этом не проходит **никто**: `ui/cli.py` не кладёт
`ChunkingOptions` в `PipelineParams`, а чанкает пост-шагом после `run`, GUI
делает то же самое у себя в `PipelineController`. То есть ветка внутри
`core.pipeline.run` есть, а вызывающих у неё нет — правка чанкинга там не
доедет ни до CLI, ни до GUI.

**Этот путь — не тот, которым идёт GUI.** См. §4.1: QML-шелл не вызывает
`core.pipeline.run` и воспроизводит часть этих шагов сам.

**Где живёт Timeline:** внутри одной итерации того, кто его собрал. Не сериализуется, не покидает process memory. На пути CLI это `pipeline.run` — сборка между стадиями `"combat"` и `"merge"`, потребление мерджером, дальше GC. На пути GUI свой экземпляр строит `MergerWorker.run()` (§4.1), поэтому работа, связанная с Timeline, должна доезжать до обоих мест.

**Где применялся бы DiskCached декоратор** (напоминание из §5.4a: это заготовка, `core/pipeline.py` её не импортирует)**:** оборачивает дорогие sources (speech — 10-30 мин wall clock) и дорогие мерджеры (LLM merger — 30-60 сек локально, $ + latency у API). Дешёвые компоненты (chat/game log sources, детерминированный `ScriptMerger`) не оборачиваются. Кэш живёт в `session_dir/_cache/sources/` и `session_dir/_cache/mergers/` соответственно. Рендереры не кэшируются — их вывод и так записывается пользователю в итоговый файл.

**Где happens merge:** в `ScriptMerger.merge()`, чистая функция от `Timeline` к `list[ScriptEvent]`. Merger проецирует EmotionTag на пересекающийся SpeechEvent (заполняя поле `emotion`), разрешает overlapping речь через `parallel_group`, интерливит ChatMessage и GameLogEntry между SpeechEvent-ами по времени `at`.

---

## 7. Migration plan

### Приоритет 2: полная перестройка (Variant A)

В одном приоритете вводятся все шесть слоёв: `ui/`, `core/`, `sources/`, `mergers/`, `renderers/`, `domain/`. Это **отменяет более ранний план постепенной миграции** (старый ADR «no big-bang» пересмотрен — см. ADR-9 ниже).

Обоснование перестройки в один приоритет:
- Контракты между слоями (Source, Merger, Renderer) настолько тонкие, что дробление по приоритетам создаёт временные shim-ы которые потом всё равно выкидывать.
- Без нового Merger нельзя добавить chat / emotion / game log как равноправные элементы — это блокирует Приоритеты 4-6.
- Тесты (Приоритет 3) пишутся уже по целевой структуре, не по промежуточной.

**Статус: выполнено.** Раздел оставлен как запись о том, откуда взялась текущая
структура — при чтении старых коммитов это единственное место, где написано,
что чем заменено. Всё, что ниже, уже в master.

Что сделал Приоритет 2:
1. Завёл шесть слоёв: `ui/`, `core/`, `sources/`, `mergers/`, `renderers/`, `domain/`.
2. Перенёс работу со speaker map в `domain/speaker_map.py`, завёл `domain/annotations.py` и `domain/events.py`.
3. Обернул вызов whisperx в `sources/speech/whisperx.py` как `Source`.
4. Добавил `sources/speech/faster_whisper.py` — backend через Python API.
5. Обернул разбор фаундривского чат-лога в `sources/game_log/fvtt_chat.py` как `Source`.
6. Заменил старый merge-скрипт на `mergers/script_merger.py` — реализует `Merger` ABC и выдаёт `list[ScriptEvent]`.
7. Завёл `renderers/plain_text.py`, сохраняющий прежний формат plain-text. Именно формат: эквивалентность байт-в-байт не проверялась — см. абзац под этим списком.
8. Завёл `core/pipeline.py`, `core/discovery.py`, `core/gpu_check.py`; `Timeline` при этом уехал в `domain/` (ADR-12).
9. Разделил CLI и GUI: `ui/cli.py` и отдельный tkinter-шелл. QML пришёл позже, в Приоритете 5 — не смешивать эти две миграции. `core.pipeline.run` зовёт только CLI; как устроен путь GUI сегодня — §4.1.
10. Три legacy-скрипта из `scripts/` — запускалка, мерджер и парсер чата — удалены. Их имена намеренно не перечислены: документ описывает то, что есть, а не то, чего нет; в истории git они на месте.

План предполагал сверку с legacy байт-в-байт, но она **не была проведена**: снимок вывода до перестройки в репозиторий не попал. Вместо неё в `tests/fixtures/e2e_p2/` лежит baseline, снятый с уже нового пайплайна, а тест сверяет с ним пересечение по токенам с порогом 90%. То есть это защита от регрессий нового пайплайна, а не доказательство эквивалентности старому.

### Приоритеты 3-6: только расширение существующих слоёв

| Приоритет | Слой | Действие | Статус |
|---|---|---|---|
| 3 | `tests/` | Pytest skeleton, fixtures, CI, ruff. Не меняет слои, добавляет инфраструктуру. | сделано |
| 4 | `sources/speech/` | Добавить backend GigaAM-v3 RNNT. Новый файл в уже готовом слое, контракт `Source` не меняется. | сделано как `sources/speech/gigaam.py` (GigaAM-v3 поверх sherpa-onnx), а не отдельным файлом с именем движка |
| 5 | `ui/` | Миграция tkinter → PySide6. | сделано, вылилось в QML — см. `docs/adr/ADR-017-ui-toolkit-pyside6.md`, поправка от 2026-04-20 |
| 6 | `mergers/`, `sources/emotion/` (planned) | `LocalLLMMerger` и/или emotion source. Всё additive. | не начато |

Если после P2 обнаружится что какой-то слой спроектирован неправильно — исправлять его придётся точечно, не полным рефакторингом. Это акцептабельный риск: контракты достаточно узкие (три ABC, четыре dataclass) чтобы проверить их на бумаге перед реализацией.

---

## 8. Design decisions & rationale

ADR-стиль: каждое решение + контекст + последствия. Эти решения зафиксированы и не пересматриваются без явной причины.

### ADR-1: Three-stage pipeline (Sources → Merger → Renderer)

**Decision:** Разделение извлечения, комбинирования и форматирования на три независимых стадии со strategy pattern на каждой. Источники возвращают raw annotations, merger комбинирует Timeline в плоский `list[ScriptEvent]`, renderer превращает в файл.

**Context:** Тогдашняя запускалка из `scripts/` (§2) смешивала все три ответственности. Добавить новый формат вывода (markdown), новый источник (эмоции) или новую стратегию merge (LLM) нельзя без трогания соседей.

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

**Decision:** `Timeline` живёт в `domain/timeline.py` (эта ADR писалась, когда он лежал в `core/` — переезд зафиксирован в ADR-12 ниже), собирается in-memory из source outputs, передаётся merger-у. Не имеет `schema_version`, не сериализуется публично, не доступна рендерерам. Единственные публичные контракты — `list[Annotation]` на выходе source и `list[ScriptEvent]` на выходе merger.

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

**Decision:** `Timeline` dataclass переносится из `core/` в `domain/timeline.py`. Ранние версии этого документа (§5.2, §4) размещали его в `core/`.

**Context:** Dependency rules секции 3 запрещают `mergers → core`. Но `Merger.merge()` имеет сигнатуру `merge(timeline: Timeline) -> list[ScriptEvent]` — значит `mergers/base.py` обязан импортировать `Timeline`. Если Timeline в `core/`, то `mergers` вынужден импортировать из `core` — нарушение. Обнаружено при декомпозиции P2 перед началом реализации.

**Consequences:**
- (+) Dependency rules строго выполняются: `mergers → domain only`, `core → domain + sources + mergers + renderers`.
- (+) Timeline остаётся pure dataclass без поведения — его естественное место в `domain/`, не в `core/`.
- (+) `core` продолжает содержать orchestration (`core/pipeline.py`), discovery, GPU check, cache — всё что требует знать о sources/mergers/renderers.
- (−) Ранняя текстовая версия документа помещала Timeline в `core/` — обновлена в §5.2 и §4 (диаграмма). Эта ADR фиксирует изменение для истории.
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
