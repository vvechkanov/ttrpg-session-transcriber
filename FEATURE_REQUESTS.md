# Feature Requests / Product Check-in

Журнал фич-реквестов и наблюдений от владельца продукта. Менеджер (Claude)
подтверждает наличие функционала в коде, фиксирует пробелы, трекает статус.

**Что значат статусы:**
- ✅ **готово** — код есть, работает в пайплайне, покрыт тестами.
- ⚠️ **частично** — или core готов без UI, или UI нарисован без проводки,
  или реестр есть с одним-единственным наполнением.
- ❌ **нет** — с нуля.
- 🅿️ **запаркована** — осознанно отложено.
- 🔮 **future** — спроектировано, делаем позже.

---

## Текущий бэклог (7 фич)

### #1 🅿️ Инсталлер — запаркован

Сейчас НЕ делаем и не трогаем. Разработка и тестирование идут из
исходников (`python -m ui.app_qml`).

**Состояние кода:** жив в `launcher/` + `build.spec` (PyInstaller,
Phase 9, коммит `0930ba3`). L1+L2 uninstall — коммит `bf4713d`.
Последние UI-правки в собранную сборку не попали (не пересобирали).

**Правило:** при работе над другими фичами не ломать `launcher/`,
но и не тратить время на `.exe`-сборку / смоук-тесты, пока явно
не разморозим.

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
инвалидирует `_sources` cache — пользователь должен перезапустить
run. Фиксится в итерации 2 вместе с per-track invalidation.

**Тесты:** 310 passed, 5 skipped. Три новых теста на
AsrOptions-propagation + round-trip всех 7 preferences через
QSettings.

**Что НЕ сделано (осознанно, перенесено в future):** per-track
overrides — advanced-блок `TrackOverridePopover` остался
layout-only. См. future #9.

---

### #3 ✅ Единая ось времени — итерация 3a готова

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
> **Что НЕ сделано (итерация 3b, future):** `TimelineRuler.qml` всё
> ещё в относительных минутах — нужна отдельная итерация для
> абсолютных часов (20:00, 21:00...). Track lanes остаются
> full-width (при одном Craig это корректно; multi-Craig — #4).

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

**Статус:** ⚠️ каркас готов, парсинг таймстемпов нет
- `SourceLaneRow` уже умеет `startPct/endPct` с border + tick
  marks ([ui/qml/timeline/SourceLaneRow.qml](ui/qml/timeline/SourceLaneRow.qml)).
- `SourceListModel.loadFromDir` находит чат+бой и создаёт ряды,
  **но** `startPct=0, endPct=100` захардкожены
  ([ui/models/session.py:640](ui/models/session.py)) — комментарий
  прямо: "precise timeline offsets require timestamp parsing that's
  out of scope until Phase 7".
- `TimelineRuler` получает `totalMinutes` из `SessionMeta` — сейчас
  это max длительности трека, не реальный диапазон сессии.
- `FvttChatSource` уже парсит chat с привязкой к `info.txt` (для
  merged.txt), но результат не долетает до `SourceListModel`.
- `Бой N.txt` вообще не парсится ни для UI, ни для merged
  (`Timeline(game_log=[])` в [core/pipeline.py:123](core/pipeline.py)).

**Что делать:**
1. `CombatSource` (core) — читает `Бой N.txt`, возвращает
   `(started_at, ended_at, encounter_name, initiative)` в UTC.
2. `SessionMeta` расширить: `absoluteStart`, `absoluteEnd`, метод
   `pctForTime(dt_utc) -> float`.
3. `SourceListModel.loadFromDir` вызывает chat/combat parser'ы и
   считает startPct/endPct через SessionMeta.
4. `TrackListModel` rows получают `startPct/endPct` из
   `info.txt Start time` + ffprobe duration.
5. `TimelineRuler` показывает реальные часы (18:00, 19:00, ...)
   вместо относительных минут.

---

### #4 📋 Несколько Craig-архивов в подпапках (Сессия 6)

> **Статус:** план архитектора готов (итерации 4a + 4b), ожидает коммита
> #3 3a. 4a = discovery multi-Craig + UI корректный + ASR single-worker
> без offset (таймкоды неточные, но полные). 4b = `time_offset_sec`
> + fanout N workers per row. **0 breaking changes** в public API —
> через shims и default kwargs. Match per-speaker по
> `re.sub(r'^\d+-', '', stem)`.


**Что хотим:** папка сессии содержит `craig-1/` и `крэйг-2/` —
оба должны подхватиться как единый набор треков (с разделением
на сегменты по времени).

**Статус:** ❌ не поддерживается
- `_iter_session_files` в [core/file_matchers.py:76](core/file_matchers.py)
  прямо документирует "no recursion into subfolders". Откроешь
  Сессию 6 — получишь 0 аудио-файлов.

**Что делать:** расширить discovery до одного уровня подпапок с
префиксом `craig-*` / `крэйг-*`, стыковать треки одного игрока
через Discord-канал (`sir.o.genri#0`), два Craig по `info.txt`
Start time превращаются в два сегмента на общей оси (см. #3).

---

### #5 ⚠️ Редактор speaker_map (игрок/персонаж на трек)

**Что хотим:** UI где для каждого трека видно player + character,
один игрок может иметь несколько персонажей (list-based), ГМ —
без персонажа. Агрегированный "cast" сверху сессии — список всех
персонажей, удобно скормить в LLM-промпт.

**Статус:** ⚠️ core готов, UI нет
- `speaker_map.json` формат есть и используется (`Сессия 4 — копия`
  содержит готовый файл).
- `core/speaker_map.py` умеет `load_speaker_map_raw` /
  `save_speaker_map_raw` / `migrate_legacy_speaker_map` — полный
  CRUD.
- В QML **нет** экрана/попапа редактирования. `TrackOverridePopover`
  — только про модель, не про спикера.

**Что делать:** `SpeakerMapPopover.qml` на клик по имени трека в
`TrackLaneRow`, проброс через `PipelineController` в
`save_speaker_map_raw`. Поддержать несколько персонажей на игрока
(list).

---

### #6 ⚠️ Выбор/настройка мержера

**Что хотим:** выбрать один из нескольких мержеров, настроить
текущий. Добавить альтернативные стратегии склейки
(script/screenplay/minutes).

**Статус:** ⚠️ инфраструктура есть, выбора нет
- Реестр `MERGERS[params.merger]()` работает ([core/pipeline.py:20](core/pipeline.py)),
  но в `mergers/` только `"script"`.
- SettingsScreen даёт `mergerMaxGap` + `mergerOocMode`, но **не**
  выбор типа мержера.

**Что делать:** добавить селект типа мержера в SettingsScreen,
при появлении второго мержера — экран с per-merger параметрами.

---

### #7 📋 Настройки чанкера (резать/overlap/параметры)

> **Статус:** план архитектора готов (задачи 7A→7B→7C). Ждёт
> очереди после #4. Решения:
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

**Статус:** ⚠️ core есть, пайплайн не зовёт, UI нет
- `core/chunking.py` + `scripts/chunk_text.py` существуют,
  но `pipeline.run()` не вызывает чанкер — только рендерит merged.
- Ни в одном QML-экране нет контролов чанкера.

**Что делать:** либо сделать чанкер отдельным Renderer-ом
(`"chunks"` в `RENDERERS` с параметрами), либо post-step после
render. UI — `ChunkerSettingsGroup` в SettingsScreen или секция
на Done-фазе TimelineScreen.

---

## 🔮 Future (делаем позже)

### #9 🔮 Per-track overrides настроек ASR (итерация 2 фичи #2)

**Что хотим:** advanced-блок `TrackOverridePopover` (сейчас layout-only
с захардкоженными "агрессивный" / beam `5` / "Русский" —
[ui/qml/popovers/TrackOverridePopover.qml:303](ui/qml/popovers/TrackOverridePopover.qml))
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

---

### #8 🔮 Combat-aware renderer

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

**Статус:** ❌ не реализовано
- `RENDERERS` реестр есть ([core/pipeline.py:21](core/pipeline.py)),
  но только `plain-text`.
- **Блокер:** требует #3 (combat-aware Timeline с `game_log`,
  а не пустым списком).

**Что делать:** новый `CombatAwareRenderer` в `renderers/`,
потребляет `Timeline.game_log` (combat events), маркирует в
выводе. В SettingsScreen → dropdown "Рендерер": `plain-text` /
`screenplay` / `combat-aware`.

---
