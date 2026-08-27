# Feature Requests / Product Check-in

Журнал фич-реквестов и наблюдений от владельца продукта. Менеджер (Claude)
подтверждает наличие функционала в коде, фиксирует пробелы, трекает статус.

**Что значат статусы:**
- ✅ **готово** — код есть, работает в пайплайне, покрыт тестами.
- ⚠️ **частично** — или core готов без UI, или UI нарисован без проводки,
  или реестр есть с одним-единственным наполнением.
- ❌ **нет** — с нуля.
- 🅿️ **запаркована** — осознанно отложено.
- 📋 **спроектировано** — решение принято и записано, кода ещё нет.
- 🔮 **future** — спроектировано, делаем позже.

**Статусы сторожит машина.** `tests/test_feature_statuses.py` держит три
проверки:

1. Значок в заголовке секции и значок в строке `**Статус:**` — один и тот
   же. Не «✅ сверху и ❌ снизу нельзя», а именно равенство: иначе достаточно
   переименовать заголовок, чтобы секция выпала из проверки.
2. Фича не может числиться несделанной, пока в дереве лежат все названные
   её артефакты. Артефакт — это путь **и** символ внутри него, причём
   закомментированные строки не считаются: реестр, из которого запись
   закомментировали, больше не доказывает ничего.
3. Каждая секция обязана нести строку `**Статус:**`, и значок должен стоять
   на той же строке. Иначе первые две молча её пропускают, и стереть статус
   (или перенести его на строку ниже — markdown это склеит) оказывается
   дешевле, чем поправить.

Это тот класс расхождений, который копится сам собой: секция росла сверху —
новый блок `> **Итерация N ✅**` приписывался к началу, — а исходная заявка
внизу оставалась в том виде, в каком её завели, и именно её читатель встречал
последней.

Машина не выбирает между ✅ и ⚠️: это продуктовое суждение, и оно остаётся за
человеком. Она говорит только «файл есть, а документ пишет, что его нет».
Когда ⚠️ верен по существу — модуль написан, но его никто не зовёт, — пометь
строку статуса словом `(частично)`, и проверка пропустит её. Это заявление, а
не глушилка: пометка означает, что статус сверили с кодом.

---

## Текущий бэклог (8 фич)

### #1 🅿️ Инсталлер — запаркован

Сейчас НЕ делаем и не трогаем. Разработка и тестирование идут из
исходников (`python -m ui.app_qml`).

**Состояние кода:** жив в `launcher/` + `build.spec` (PyInstaller,
Phase 9, коммит `0930ba3`). L1+L2 uninstall — коммит `bf4713d`.
Последние UI-правки в собранную сборку не попали (не пересобирали).

**Правило:** при работе над другими фичами не ломать `launcher/`,
но и не тратить время на `.exe`-сборку / смоук-тесты, пока явно
не разморозим.

**Статус:** 🅿️ запаркована — код в `launcher/` жив, сборка отстала

---

### #2 ✅ Настройки модели ASR — глобальные (итерация 1)

**Что хотим:** в SettingsScreen покрутить где модель крутится
(CPU vs GPU), GigaAM variant (rnnt/e2e_rnnt), precision (fp32/int8),
FW compute_type + beam_size, язык, количество CPU-потоков.
Настройки персистятся, применяются ко всем дорожкам.

**Статус:** ✅ готово — коммит `64a497c` (2026-04-21)
- `AsrOptions` dataclass в [core/asr.py](core/asr.py) — frozen, 7
  optional полей, готов к per-track merged_with() в итерации 2.
- `make_source(model_id, *, options=AsrOptions())` — все поля
  пробрасываются в backend-ы (FW получает beam_size и num_threads
  через расширенный `FasterWhisperSource.__init__`, GigaAM —
  variant/precision/num_threads).
- `AppPreferences` +7 Q_PROPERTY (asrDevice / asrComputeType /
  asrBeamSize / asrLanguage / gigaamVariant / gigaamPrecision /
  asrNumThreads) с QSettings-персистом. `defaultDevice` → `asrDevice`
  с одноразовой fallback-миграцией старого ключа.
- `AppPreferences.build_asr_options()` — единственный мост в core.
- `PipelineController` принимает preferences, пробрасывает options
  в make_source.
- SettingsScreen — новая `SettingsGroup "ASR (распознавание речи)"`
  с 7 контролами перед "Мержер по умолчанию".

**Known limitation:** смена настроек при активной сессии не
инвалидирует `_sources` cache. Средство названо неверно, проверено
27.08: перезапуск прогона **не помогает** — `runAsr` кэш не трогает,
а `_sources.clear()` стоит только на ветке отмены и при закрытии
сессии. Помогает перезапуск приложения либо, случайно, отменённый
прогон. Тем же кэшем держится и speaker map (см. #5), то есть
ограничение шире, чем «настройки». Фиксится в итерации 2 вместе с
per-track invalidation.

**Тесты:** 310 passed, 5 skipped. Три новых теста на
AsrOptions-propagation + round-trip всех 7 preferences через
QSettings.

**Что НЕ сделано (осознанно, перенесено в future):** per-track
overrides — advanced-блок `TrackOverridePopover` остался
layout-only. См. future #9.

---

### #3 ✅ Единая ось времени — абсолютная, открыт дефект окна (3b)

> **Итерация 3a ✅** (2026-04-21) — абсолютные startPct/endPct для
> source rows. Новый модуль `core/timeline_window.py`:
> `TimelineWindow.pct_for(ts)`, `parse_info_start`, `parse_combat_file`,
> `chat_span`, `build_window`. `SessionMeta` хранит window,
> `SourceListModel.loadFromDir` считает процент через window и
> публикует row с реальными границами. Fallback на 0/100% если
> `info.txt` нет или окно меньше 10 мин.
>
> **Верификация на реальной Сессии 4:** info_start `17:21:29Z`, бой
> `19:25:33–20:45:45Z`, окно 240 мин (default 4h) → combat startPct
> **51.69%**, endPct **85.11%**. Тесты: 346 passed, 5 skipped, 36
> новых тестов.
>
> **Что НЕ сделано (на момент 3a):** `TimelineRuler.qml` всё
> ещё в относительных минутах — нужна отдельная итерация для
> абсолютных часов (20:00, 21:00...). Track lanes остаются
> full-width (при одном Craig это корректно; multi-Craig — #4).
> *Оба пункта закрыты позже — см. итерацию 3b ниже и #4.*

> **Найдено 2026-08-02 — окно оси строится по дефолту, а не по реальной длине.**
> `SourceListModel.loadFromDir` ([ui/models/session.py](ui/models/session.py))
> вызывает `build_window(...)`
> с `max_track_duration=None` («tracks probe asynchronously; 3a ignores them»).
> Окно считается один раз при открытии сессии, когда длительности ещё не
> известны, и берёт дефолтные 4 часа. Когда `PeaksWorker` приносит настоящие
> длительности через `SessionMeta.setTotalSeconds`, окно **не пересчитывается**.
>
> Проверено на Сессии-15 (реальная длина дорожек 4:45:12): бой рисуется на
> 73.40–91.49%, а по фактическому окну должен быть на **69.35–86.44%** —
> сдвиг ~4 п.п. для всех полос источников.
>
> На `merged.txt` **не влияет**: мержер выравнивает чат по `info.txt`
> независимо от UI-окна. Чисто визуальный дефект. Чинится пересчётом окна
> по сигналу `durationReady` — вместе с итерацией 3b.

**Уточнение владельца (21.04):** UI уже концептуально устроен как
таблица: слева гаттер 220 px (имена), справа общая ось времени.
Все элементы (чат, бой, Craig-сегменты, треки) — ряды на этой оси
с позициями `startPct..endPct`. Проблема не в слоях, а в том,
что оффсеты сейчас fake.

**Что хотим:** каждый источник и трек встаёт в правильный
горизонтальный диапазон по фактическому времени. Бой с 20:15 до
21:38 рисуется *в своём куске* оси, а не full-width. Чат
покрывает всё от первого до последнего сообщения. Треки Craig —
от своего `info.txt Start time` до `Start time + duration`. Ось
нормализована к `[min(all_starts), max(all_ends)]`.

**Статус:** ✅ ось абсолютная, бои парсятся; открыт один дефект окна

Пять пунктов, которыми прежний статус объяснял «каркас готов, парсинга нет»:
- `SourceLaneRow` умеет `startPct/endPct` с border + tick marks
  ([ui/qml/timeline/SourceLaneRow.qml](ui/qml/timeline/SourceLaneRow.qml)).
- `SourceListModel.loadFromDir` считает проценты через
  `TimelineWindow.pct_for`, а не константами: чат и бой получают
  реальные границы ([ui/models/session.py](ui/models/session.py)).
  `0.0/100.0` остались как fallback — когда окна нет, когда чат
  распарсился пустым и когда `parse_combat_file` вернул `None` на
  битом дампе. Последний случай при этом **никак не показывается**:
  комментарий в коде обещает, что полоса во всю ширину даст понять
  «что-то не так», но ни роли ошибки, ни бейджа, ни строки в логе нет,
  а ту же полную ширину даёт легитимная сессия без `info.txt` — то есть
  битый дамп визуально неотличим от исправного. Мерж при этом
  пропускает его молча в GUI и с `logger.exception` в CLI. Это пробел,
  а не индикация; заведён карточкой.
- `TimelineRuler` печатает абсолютные часы: режим `_wallClock`
  сажает тики на настоящие получасы и подписывает их как `20:00`
  ([ui/qml/timeline/TimelineRuler.qml](ui/qml/timeline/TimelineRuler.qml)).
  Режим включается, когда офсет чат-лога разрешён надёжно; если резолвер
  лишь угадал, `windowStartClockMinutes` отдаёт `-1`, и линейка
  возвращается к относительным минутам.
- Чат долетает до `SourceListModel`: `chat_timeline`
  ([core/timeline_window.py](core/timeline_window.py)) даёт и span ряда, и
  точки плотности, и офсет для часов линейки. Идёт он не через
  `FvttChatSource` — тот остался на пути `merged.txt`, — а через
  `parse_fvtt_log` и `resolve_tz_offset`, соседей по модулю; логику
  вычитания офсета `chat_timeline` намеренно повторяет, о чём сказано в
  его же докстринге.
- `Бой N.txt` парсится: `CombatDumpSource`
  ([sources/game_log/combat_dump.py](sources/game_log/combat_dump.py))
  для merged, `parse_combat_file` для UI. В пайплайн они приходят как
  `game_log=game_log_entries` ([core/pipeline.py](core/pipeline.py)),
  а не пустым списком.

**Осталось (итерация 3b):** дефект окна из блока выше — `build_window`
зовётся один раз с `max_track_duration=None` и не пересчитывается, когда
`durationReady` приносит настоящие длительности. Чисто визуальный сдвиг
полос; на `merged.txt` не влияет.

---

### #4 ✅ Несколько Craig-архивов — итерация 4b готова

> **Итерация 4b ✅** (2026-04-21) — per-segment ASR fanout + per-segment
> peaks + per-segment waveform. `transcribe_one_track(time_offset_sec)`
> сдвигает timestamps в session-global ось; `AsrWorker` принимает
> `tuple[SegmentJob, ...]` и крутит все сегменты строки серийно с
> duration-weighted прогрессом; `PeaksWorker` работает по плоскому
> списку `[(row, seg_idx, path)]` и отдаёт `peaksReady(row, seg_idx,
> peaks)`; `TrackListModel.setPeaks(row, seg_idx, peaks)` кладёт их в
> `peaks_by_segment` (primary зеркалится в row-level `peaks`); QML
> `TrackLaneRow` рисует `WaveformCanvas` на каждый сегмент через
> Repeater; row-progress остаётся единым оверлеем. План
> [docs/plans/feature-4b-multicraig-asr.md](docs/plans/feature-4b-multicraig-asr.md).
> Тесты: 375 passed, 3 skipped. 15 environmental errors (qtbot / bundled
> ffmpeg — не регрессии).

> **Итерация 4a ✅** (2026-04-21) — discovery multi-Craig + UI
> корректный. В `core/file_matchers.py` добавлены `CraigSegment`
> dataclass, `detect_craig_segments()`, `match_speaker()`.
> `detect_audio_files()` превращён в shim над `detect_craig_segments`
> — 0 breaking changes. `TrackListModel` группирует аудио по
> `match_speaker(stem)` — один row на спикера с
> `segments: tuple[TrackSegment, ...]`, сортируются по `start_ts`.
> Новая QML-role `SegmentsRole` возвращает `[{startPct, endPct}]`
> через `TimelineWindow.pct_for`. `TrackLaneRow.qml` — Repeater
> рисует N прямоугольников, secondary сегменты как placeholder
> (50% opacity, без waveform).
>
> **Верификация на Сессии 6** (`craig-1/` + `крэйг-2/`): 2 сегмента
> детектятся, `match_speaker` нормализует `1-sir_o_genri` /
> `2-sir_o_genri` → один ключ, 6 rows из 12 файлов. Sort:
> `craig-1` перед `крэйг-2` (casefold alphabetical).
>
> Тесты: 365 passed, 5 skipped (+19 новых тестов).
>
> **Что НЕ сделано (итерация 4b, future):** ASR в 4a бежит только
> по `segments[0].audio_path` (primary), остальные сегменты игнорятся.
> Peaks только для первого сегмента. 4b добавит
> `transcribe_one_track(time_offset_sec=0.0)` + fanout N workers per row
> + peaks per-segment.


**Что хотим:** папка сессии содержит `craig-1/` и `крэйг-2/` —
оба должны подхватиться как единый набор треков (с разделением
на сегменты по времени).

**Статус:** ✅ поддерживается — 4a discovery, 4b per-segment ASR и peaks

**Известное ограничение (найдено ревью Codex на PR #25, воспроизведено).**
Речь уезжает вперёд, когда чат или бой начались раньше записи Craig. У двух
осей разные нули: `TrackListModel.segment_offset_seconds`
([ui/models/session.py](ui/models/session.py)) считает офсет сегмента от
`TimelineWindow.t0`, а `ScriptMerger`
([mergers/script_merger.py](mergers/script_merger.py)) штампует те же события
от `recording_start` из `info.txt`. Разрыв между ними учитывается дважды.
Замер на сессии с записью через 107 минут после `t0`: речь из первой секунды
записи получает `start = 6420 с`, тогда как чат в тот же момент — `180 с`.
Не срабатывает, только когда запись и есть самый ранний якорь. Случай не
экзотический: кнопка Foundry «Export Chat Log» выгружает весь лог кампании,
поэтому чат почти всегда левее записи. Заведено карточкой.

Discovery спускается в подпапки `craig-*` / `крэйг-*`: `CraigSegment`,
`detect_craig_segments()` и `match_speaker()` в
[core/file_matchers.py](core/file_matchers.py). Треки одного игрока из
разных архивов сходятся в один ряд по нормализованному имени, сегменты
сортируются по `start_ts` и встают на общую ось через
`TimelineWindow.pct_for` (см. #3). ASR и peaks считаются по каждому
сегменту — итерация 4b.

---

### #5 ✅ Редактор speaker_map — итерация 5b готова

> **Итерация 5b ✅** (2026-04-25) — два коммита 5b/1 → 5b/2.
> Schema расширена с `character: str` до `characters: list[str]`
> (один игрок может иметь несколько PC, ГМ → пустой список),
> `_normalize_entry` принимает legacy shape без перезаписи диска
> и сохраняет unknown extras для будущих note/color/tags.
> UI: `SpeakerMapPopover.qml` (player + GM/PC pills + динамический
> список персонажей с add/remove), кликабельный role+cast лейбл в
> `TrackLaneRow` вместо character InlineEdit, collapsible
> `CastStrip.qml` сверху таймлайна с de-duped списком всех
> персонажей сессии. Inline-переименование игрока тоже пишет в
> JSON через `PipelineController.renamePlayer`.
> Коммиты: `338f171` (core+schema), `e771b43` (UI). 438 passed.

**Что хотим (исходный запрос):** UI где для каждого трека видно
player + character, один игрок может иметь несколько персонажей
(list-based), ГМ — без персонажа. Агрегированный "cast" сверху
сессии — список всех персонажей, удобно скормить в LLM-промпт.

**Что закрыто 5b:**
- Schema: `{"player": str, "characters": list[str], "role": str, ...extras}`.
- Read normalizes legacy `character: "X"` → `characters: ["X"]`,
  файл на диске НЕ переписывается тихо (upgrade при следующем save).
- `migrate_legacy_speaker_map` теперь вызывается из
  `TrackListModel.loadFromDir` — старые setup'ы с project-root
  файлом мигрируют на первом открытии.
- `SpeakerMapPopover.qml` на клик по role+cast лейблу. GM-режим
  скрывает список персонажей.
- `CastStrip.qml` — collapsed-by-default, chevron + count badge,
  Flow из accent-tinted pills с уникальными именами персонажей.
- Listener role (`"Слушатель"`) round-trip с `excluded=True`.
- `TrackOverridePopover` (модель ASR) и `SpeakerMapPopover`
  (player/character) — два независимых попапа на одной строке.

**Статус:** ✅ готово — итерация 5b закрыта

**Два известных ограничения (найдены ревью Codex на PR #25, воспроизведены).**

1. Правка не доезжает до второго Craig-архива. Ряд группирует сегменты по
   нормализованному имени (`match_speaker` срезает префикс `1-` / `2-`), а
   `PipelineController.saveSpeakerMapEntry` пишет в `speaker_map.json` один
   ключ — stem основного сегмента. Бэкенды же резолвят каждый сегмент по
   его полному stem, без нормализации. Проверено: после правки
   `resolve_speaker("1-alice")` даёт «Алиса (Одетт)», а
   `resolve_speaker("2-alice")` — сырое `2-alice`, и один игрок
   расщепляется в `merged.txt` надвое.
2. Правка после успешного прогона не применяется до перезапуска приложения.
   `PipelineController._get_or_make_source` захватывает карту только в
   момент создания источника, а `_sources` чистится лишь при отмене и при
   закрытии сессии — на успешном пути нет. JSON и модель обновляются сразу,
   вывод следующего прогона — нет.

Оба заведены карточками; здесь не чинятся.

**Future (5c, если потребуется):**
- Per-character notes/tags — schema это уже умеет (extras),
  UI пока нет.
- Copy-cast-to-clipboard кнопка в CastStrip для LLM-промпта.

---

### #6 📋 Выбор/настройка мержера + LLM-мержер

**Что хотим:** (а) селектор мержера в Settings, (б) новый **LLM-мержер**
на локальных моделях — исправляет ASR-ошибки, склеивает реплики,
вплетает fvtt-чат в правильные места.

**Статус:** 📋 анализ ML-specialist готов (2026-04-21), реализация
разбита на 3 этапа.

#### Технические решения (ML-specialist)

- **Задача LLM:** (A) ASR-коррекция имён PF2e / code-switching —
  *главная ценность*. (D) механическая склейка соседних реплик.
  (E) обогащение из fvtt-чата. **НЕ (B) атрибуция** (опасно),
  **НЕ (C) литературизация** (отдельная фича).
- **Модель:** `Qwen2.5 7B q4_K_M` как primary (4.7 GB, 6 GB VRAM,
  42 tok/s на RTX 3060). `Qwen2.5 14B` для mid-tier. Qwen лучше
  Llama/Mistral/Saiga по русскому + structured JSON output.
- **Движок:** **Ollama** (Windows native installer, OpenAI-compatible
  REST API, GPU offload автоматический, telemetry отключается через
  `OLLAMA_NOANALYSIS=1`). llama-cpp-python как fallback.
- **Окно:** 45 мин контента ≈ 10k токенов — вмещается в 16k context.
  Sliding: активная зона 5 мин, контекст ±20 мин до/после,
  шаг 5 мин. Для 3ч сессии — 36 вызовов × ~8 сек = **6 минут**.
- **Architecture:** `LLMMerger(Merger)` + `LLMBackendInstallable(Installable)`
  (как GigaAM). QThread worker. **ID-based addressing** (LLM
  редактирует только `text`, speaker readonly → защита от
  галлюцинаций атрибуции). Промпт EN, контент RU. Degradation
  fallback на `ScriptMerger` если Ollama недоступен.

#### План реализации — 3 этапа

**Этап 6.1 (сейчас, если беремся):** селектор мержера в
SettingsScreen. `LLMMerger` регистрируется в `MERGERS[]`, но
без реализации — деградирует до `script`. 1-2 дня работы.
**Разблокирует архитектуру без риска.**

**Этап 6.2 (после закрытия #4):** PoC — `scripts/llm_revise_poc.py`
(standalone CLI, вход merged.txt + speaker_map.json, выход
revised.txt). Qwen2.5 7B, окно 20 мин, только задача (A).
Тест на Сессии 4: "Пикаэль" → "Микаэль", "Анканта" → "Анканто".
1-2 дня.

**Этап 6.3 (если PoC даёт прирост качества):** полная интеграция
в pipeline — QThread worker, прогресс в UI, Installable-паттерн
для Ollama. 5-7 дней.

#### Рекомендация ML-specialist

**Отложить 6.2+6.3 до закрытия #4.** Причина: input в мержер
(canonical JSON speech segments) может измениться по формату при
стабилизации ASR-бэкендов в #4/4b. Лучше сначала зафиксировать
контракт, потом заходить в LLM-слой.

#### Риски (зафиксированы)

- **Галлюцинации смысла** — mitigation: явный запрет в промпте +
  verification по длине (>30% отклонение → revert к оригиналу).
- **Перепутанная атрибуция** — mitigation: speaker readonly.
- **Privacy** — localhost:11434, telemetry off, аудио машину
  не покидает.
- **Ollama daemon lifetime** — launcher управляет явно (subprocess
  terminate на закрытие).

---

### #7 ✅ Настройки чанкера (резать/overlap/параметры)

> **Реализовано ✅** (2026-04-21) — три коммита 7A → 7B → 7C.
> `ChunkingOptions` frozen dataclass в `core/chunking.py`; `PipelineParams`
> получает `chunking: ChunkingOptions | None`; новая стадия `"chunk"`
> в `PipelineStage` между `render` и `done`, post-step вызывает
> `chunk_text_file` и логирует при ошибке (не валит pipeline).
> `AppPreferences` +3 Q_PROPERTY (`chunkingEnabled` /
> `chunkingChunkChars` / `chunkingOverlapRatio`) с персистом под
> `chunking/*`, новый `build_chunking_options()` как зеркало
> `build_asr_options`. `SettingsScreen` получил группу «Чанки для
> LLM» (toggle + chunk_chars + overlap 0..50%). `PipelineController`
> синхронно вызывает чанкер после `_onMergeDone`, публикует
> `chunksDir` в Q_PROPERTY; `TimelineScreen` рисует второй `OutputChip`
> по `visible: chunksDir.length > 0`. План
> [docs/plans/feature-7-chunker.md](docs/plans/feature-7-chunker.md).

**Решения архитектора (2026-04-21):**
> - **Встраивание:** post-step в `pipeline.run()` перед финальным
>   `stage_cb("done")`. Новая стадия `"chunk"` (7 стадий вместо 6).
> - **Параметры (MVP, YAGNI):** `enabled` (default false),
>   `chunk_chars` (default 40_000), `overlap_ratio` (default 0.20).
>   Границы всегда параграфы, символы (не токены). Per-session
>   override отложен.
> - **UI:** только в SettingsScreen, новая SettingsGroup "Чанки
>   для LLM". Плюс опциональный OutputChip в DoneSummary.
> - **Контракт:** `ChunkingOptions` frozen dataclass рядом с
>   `AsrOptions` в `core/chunking.py`, новое поле
>   `chunking: ChunkingOptions | None = None` в `PipelineParams`.
> - **0 breaking** в `pipeline.run()` / CLI. Ломает тесты на
>   `PipelineStage` литерал — обновить.


**Что хотим:** после мержа в UI выбрать: резать на чанки или нет,
с каким overlap, какой размер чанка. Готовим на скармливание в
LLM для постобработки.

**Статус:** ✅ пайплайн зовёт, UI есть

- `core/chunking.py` + `scripts/chunk_text.py` на месте, и `pipeline.run()`
  вызывает `chunk_text_file` post-step'ом — стадия `"chunk"` между
  `render` и `done` ([core/pipeline.py](core/pipeline.py)). Стадия
  условная: чанкер работает, когда `chunking.enabled`, а по умолчанию
  выключен.
- Контролы есть: группа «Чанки для LLM» в
  [ui/qml/screens/SettingsScreen.qml](ui/qml/screens/SettingsScreen.qml)
  (toggle + chunk_chars + overlap), персист через `AppPreferences` под
  `chunking/*`.

Из двух развилок «Что делать» выбрана вторая — post-step, а не отдельный
рендерер; решение записано в блоке архитектора выше.

---

### #8 ✅ Combat-aware renderer

> **Реализовано ✅** — три коммита `fe0a7a6` → `03e337a` → `c69203a`.
> `CombatAwareRenderer` в [renderers/combat_aware.py](renderers/combat_aware.py)
> потребляет `Timeline.game_log`; реестр `RENDERERS` в
> [renderers/\_\_init\_\_.py](renderers/__init__.py) отдаёт его по ключу
> `"combat-aware"`, `MergerWorker` резолвит рендерер через реестр с
> fallback на `plain-text`. В `SettingsScreen` — «ФОРМАТ merged.txt»
> с пунктом «С разметкой боёв», персист через `AppPreferences`
> (`merger/renderer`). Вне боя вывод побайтово совпадает с `plain-text`.
> Тесты: [tests/test_renderers_combat_aware.py](tests/test_renderers_combat_aware.py),
> 28 проверок.

**Что хотим:** альтернатива `plain-text` рендереру — формат,
который особым образом маркирует бой в транскрипте. Внутри блока
боя: initiative order сверху, реплики помечены раундами/ходами,
в конце блока — результат.

Пример фрагмента:

```
━━━ БОЙ 1: Мост Гоблинов ━━━  [20:15 – 21:38]
Инициатива: Киран (28) → Дариус (24) → Бель (19) → Самум (15)
Раунд 1 · ход Кирана
  [20:15] Лиля (Киран): каст Fireball на центральную группу, DC 18
  ...
━━━ Конец боя: победа, XP +1200 ━━━
```

**Статус:** ✅ готово

Блокер «требует #3» снят вместе с #3: бои парсятся и приходят в
`Timeline` как `game_log`, а не пустым списком.

**Известное ограничение (найдено ревью Codex на PR #25, проверено по коду).**
Разметка боёв пропадает, когда `info.txt` лежит не в корне сессии, а внутри
`craig-1/` — то есть в раскладке, которую поддерживает #4. `CombatDumpSource`
без явного `info_file_path` ищет только `<сессия>/info.txt`, а `find_info_file`
([core/discovery.py](core/discovery.py)) смотрит туда же и отдаёт `None`. Дальше
пути расходятся только громкостью: CLI пишет `logger.exception`, а GUI
([ui/engines/merger_worker.py](ui/engines/merger_worker.py)) глотает
`FileNotFoundError` через `continue` вообще без записи в лог. В обоих случаях
`game_log` остаётся пустым, и выбранный «С разметкой боёв» рендерер честно
рисует транскрипт вовсе без боёв. Заведено отдельной карточкой — здесь не
чинится, потому что это дефект кода, а не статуса.

---

## 🔮 Future (делаем позже)

### #9 🔮 Per-track overrides настроек ASR (итерация 2 фичи #2)

**Что хотим:** advanced-блок `TrackOverridePopover` (сейчас layout-only
с захардкоженными "агрессивный" / beam `5` / "Русский" —
[ui/qml/popovers/TrackOverridePopover.qml](ui/qml/popovers/TrackOverridePopover.qml))
привязать к реальному per-row override. Один трек — свой device/
beam/variant, остальные берут глобальные из Settings.

**Скоуп:**
1. `AsrOptions.merged_with(override: AsrOptions) -> AsrOptions` —
   слияние `None` в override = взять из global.
2. `TrackListModel` — per-row `override_options: AsrOptions | None`.
   Сохранение/загрузка через session-local JSON (если нужно
   персистить между запусками).
3. `TrackOverridePopover` advanced-блок — bindings к row-override.
   UX: плейсхолдер "как у всех (cuda)" серым пока не override'нуто.
   Кнопка "сбросить к глобальному" очищает override.
4. `PipelineController._get_or_make_source` — для каждого трека
   считать `global.merged_with(row.override)`, ключ кэша сменить
   с `model_id` на `(model_id, options_hash)`. Побочно фиксит
   known limitation фичи #2 (смена глобальных настроек в активной
   сессии теперь инвалидирует источники корректно).

**Контракт готов:** `AsrOptions` уже frozen dataclass (коммит
`64a497c`) — для per-track достаточно добавить `merged_with` метод,
контракт `make_source` не меняется.

**Статус:** 🔮 future — поповер нарисован, проводки к per-row override нет

---
