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

### #2 ⚠️ Настройки модели ASR (CPU/GPU, RNNT/CTC, beam/VAD)

**Что хотим:** в UI покрутить где модель крутится (CPU vs GPU),
выбрать для GigaAM `rnnt` vs `e2e_rnnt`, для Whisper — beam/VAD/
язык/precision. Два слоя: глобальные defaults в SettingsScreen,
per-track override в TrackOverridePopover.

**Статус:** ⚠️ частично
- Core принимает всё: `PipelineParams` уже имеет `device`,
  `compute_type`, `beam_size`, `language`, `gigaam_variant`,
  `gigaam_precision`, `num_threads` ([core/pipeline.py:48](core/pipeline.py)).
- UI показывает часть: `TrackOverridePopover` раскрывается в
  "Расширенные параметры" с VAD/beam/language — **но layout-only**,
  значения хардкод, никуда не сохраняются
  ([ui/qml/popovers/TrackOverridePopover.qml:303](ui/qml/popovers/TrackOverridePopover.qml)).
- SettingsScreen глобальных контролов device/compute_type/variant
  не имеет вовсе ([ui/qml/screens/SettingsScreen.qml](ui/qml/screens/SettingsScreen.qml)).

**Что делать:** привязать QML-контролы к `PipelineParams`, добавить
секцию "ASR" в SettingsScreen + проброс per-track overrides через
`TrackListModel` в `PipelineController`.

---

### #3 ⚠️ Единая ось времени: всё выровнено лево-право

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

### #4 ❌ Несколько Craig-архивов в подпапках (Сессия 6)

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

### #7 ⚠️ Настройки чанкера (резать/overlap/параметры)

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
