# UI QML Migration — Widgets → PySide6 + QtQuick/QML

**Status:** draft v0.1 (план, ещё не начат)
**Date:** 2026-04-20
**Owner:** architect (план) + python-dev (execution) + qa (приёмка)
**Supersedes:** `docs/architecture/ui-qt-migration.md` (Widgets-фаза)
**Related:**
- ADR-017 (UI toolkit — PySide6) — требует amendment: явно зафиксировать **QML** как основной стек (сейчас в тексте упор на QtWidgets).
- ADR-016 (Module UI Contract) — требует amendment: контракт шаблонов переписывается с «фабрика `QWidget`-ов» на «QML-компонент + QObject ViewModel».
- `docs/design/screen-3-session.md` — спека экрана (handoff-документ).
- `docs/design/mockups/figma-make/screen-3-session/v1/` — визуальный handoff (Figma Make v1 React/shadcn).

---

## 0. Почему вообще этот документ

Текущая ветка `claude/implement-ui-foundation-KviVz` содержит 9 шагов QML-прототипа (~6000 строк, `ui/qml/*`, `ui/engines/*`, `ui/models/*`), но:

1. Никакой воркер не дёргает `core/pipeline.py`, `core/discovery.py`, `sources/*`. Это визуальный мок на `time.sleep`.
2. ADR-017 в master-е аргументирует **QtWidgets** (`QFrame`, `QScrollArea`, `QPropertyAnimation(b"geometry")`, QSS). Ветка пошла мимо ADR.
3. В master-е параллельно живёт production-шелл `ui/shell/*` (Widgets, 4559 строк) — он собирается через `build.spec`, имеет реальный `RunController`, `install_wizard`, `SettingsDrawer`, `AddSourceDialog`.
4. `build.spec` **исключает** `QtQml`, `QtQuick`, `QtQuickControls2` — для QML-шелла spec надо переписывать.

Менеджерское решение (2026-04-20): **идём по QML (Вариант Б)**. QML становится основным стеком, Widgets-шелл снимается. Этот документ — детальный план.

---

## 1. Источник правды для UI — handoff, не импровизация

UI целиком собирается по **handoff-пакету** (Figma Make v1 + spec-документ), а не произвольно:

| Артефакт handoff | Роль | Где лежит |
|---|---|---|
| `docs/design/screen-3-session.md` | Поведенческая спека (12 разделов: блоки, состояния, drawer, ошибки) | репо, текст |
| `docs/design/mockups/figma-make/screen-3-session/v1/` | Визуальный эталон — React/shadcn экспорт из Figma Make | репо, HTML-прототип |
| `docs/design/mockups/figma-make/screen-3-session/v1/default_shadcn_theme.css` | Цветовые токены, радиусы, тени | репо, CSS |
| `docs/design/flowstep-prompts/screen-3-*.md` | Сценарные промпты под Flowstep-дизайн секций | репо, текст |

**Правила привязки:**

- Любой новый/правленный QML-компонент ссылается в шапке-комментарии на секцию `screen-3-session.md` (например, `// §6.3 Runtime-панель модуля`) **и** на имя React-компонента в Figma Make (`// Figma Make: FasterWhisperSettingsPanel.tsx`).
- Цветовые/типографические токены — **только из `default_shadcn_theme.css`**, перенесённые один-к-одному в `Theme.qml`. Ручной подбор «на глаз» — блокер ревью.
- Поведение (анимации, таймауты, что-показывать-когда) — только из `screen-3-session.md`. Никаких новых состояний/жестов без правки спеки.
- **Нет** handoff → **нет** UI. Если дизайн чего-то не покрывает (список Recent, онбординг-оверлей, Models screen) — это **не baseline MVP**; выносится в «Phase 12: post-MVP screens» или переоткрывает handoff.

**Трассировка экран → QML → core** (сокращённо, полный вариант — в §4):

| Экран/блок (handoff §) | QML-файл | ViewModel | Core-вызов |
|---|---|---|---|
| Idle / empty (§3, §4 idle) | `ui/qml/screens/EmptyScreen.qml` | `AppModel` | `core.discovery.find_sessions` |
| Блок 1 Источники (§4) | `ui/qml/timeline/SourceLaneRow.qml` | `SourceListModel` | `core.file_matchers`, `sources.game_log.fvtt_chat.discover` |
| Блок 2 Мержер (§5) | `ui/qml/timeline/MergerChip.qml` | `AppModel.merger` | `mergers.MERGERS` |
| Блок 3 Running (§6.2–6.3) | `ui/qml/screens/TimelineScreen.qml` + `TrackLaneRow.qml` | `PipelineController` + `TrackListModel` | `core.pipeline.run(on_stage=...)` |
| Блок 3 Done (§6.4) | `ui/qml/timeline/DoneSummary.qml` | `AppModel.output` | — (читает output_path из `run` результата) |
| Блок 4 Вывод (§7) | `ui/qml/timeline/OutputChip.qml` | `AppModel.output` | `QDesktopServices.openUrl` на output_path |
| Settings Drawer (§9) | `ui/qml/drawers/*Drawer.qml` | `SettingsModel` | `QSettings` + `sources.*.DEFAULTS` |
| Errors (§10) | `ui/qml/controls/ErrorBanner.qml` | `AppModel.error` | ловится из `on_stage` + exception |

---

## 2. Как модульность архитектуры сойдётся с новым UI

Ключевой вопрос — **инварианты шестислойной архитектуры** (ADR-016) против QML. Сегодня `core/ui_contract.py` описывает «каждый модуль отдаёт три `QWidget`-фабрики» (`make_home_card`, `make_runtime_panel`, `make_settings_panel`). QML-шелл не может встраивать `QWidget`-ы напрямую в Quick-дерево без `QQuickWidget`-костылей. Инвариант нужно **переформулировать, не ослабляя**:

### 2.1. Переписанный контракт (amendment к ADR-016)

```python
# core/ui_contract.py (после amendment)

@dataclass(frozen=True)
class UIConfig:
    template: str              # имя шаблона в ui/templates/*
    params: dict[str, Any]     # module-specific, opaque для core

@dataclass(frozen=True)
class UITemplateQml:
    """Три QML-компонента + фабрика ViewModel-а."""
    home_card_qml: str         # "qrc:/templates/audio_source/HomeCard.qml"
    runtime_panel_qml: str     # "qrc:/templates/audio_source/RuntimePanel.qml"
    settings_panel_qml: str    # "qrc:/templates/audio_source/SettingsPanel.qml"

    def make_viewmodel(
        self,
        module: Source | Merger | Renderer,
        params: dict[str, Any],
    ) -> QObject: ...          # QObject c Q_PROPERTY-полями, даётся в контекст QML
```

### 2.2. Направление зависимостей (инвариант)

Диаграмма та же, только вместо QWidget-фабрик — QML-файлы + ViewModel-классы:

```
ui/shell/*.py  (QQmlApplicationEngine, loader)
    ↓ импортирует
ui/templates/*.py  (возвращают UITemplateQml + QObject VM)
    ↓ импортирует
core/ui_contract.py  (dataclass + Protocol)
    ↑ импортируют только
sources/*, mergers/*, renderers/*, domain/*  (НЕ знают QML вообще)

ui/qml/*.qml  —  рендерится из qrc/file URL, НЕ импортит Python
```

**Усиление инварианта (важно!):** `sources/`, `mergers/`, `renderers/`, `domain/` **не импортируют ни `PySide6.*`, ни строки с `qrc:/...`**. Им отдаётся только dataclass `UIConfig(template, params)` — полностью data-класс. Связка `template → UITemplateQml` живёт в `core/ui_registry.py` (единственный controlled upward импорт — как и сейчас).

### 2.3. Где QML, а где Python — правило раскладки

| Слой | Python | QML |
|---|---|---|
| `ui/shell/` | Да (QApplication, `QQmlApplicationEngine`, контекст-properties) | Главный `Main.qml` + `Sidebar.qml` |
| `ui/templates/` | Да (VM-классы `AudioSourceVM(QObject)` с `Q_PROPERTY`, сигналами) | `HomeCard.qml`, `RuntimePanel.qml`, `SettingsPanel.qml` каждого шаблона |
| `ui/engines/` | Да (QThread-воркеры, `PipelineController`) | — |
| `ui/models/` | Да (`QAbstractListModel` для треков, источников, recent sessions) | — |
| `ui/controls/` | Нет | Атомы (`PrimaryButton`, `Chip`, `SvgIcon`, `InlineEdit`) |
| `ui/timeline/` | Нет | Компоненты экрана Session (`TrackLaneRow`, `StitchOverlay`, `MergerChip`) |
| `ui/screens/` | Нет | Целые экраны (`EmptyScreen`, `TimelineScreen`, `ModelsScreen`, `SettingsScreen`) |
| `core/` | Да | **Никогда** |

**Инвариант покрытия тестами:** ViewModel-ы (Python, `QObject` subclass) тестируются pytest-qt **без** запуска QML-движка — через прямые вызовы сигналов/свойств. Сам QML покрывается smoke-тестом «экран грузится без warnings + визуальный regression через QtQuick `grabToImage`».

### 2.4. Один источник токенов дизайн-системы

Сейчас токены живут в трёх местах: `ui/shell/theme.py`, `ui/qml/Theme.qml`, `docs/design/mockups/.../default_shadcn_theme.css`. **Канонический источник — `default_shadcn_theme.css`** (пришёл из Figma). Генерация: скрипт `scripts/gen_theme.py` читает CSS, эмитит `ui/qml/Theme.qml` (QtObject-singleton) при каждом изменении. После сноса Widgets-шелла `ui/shell/theme.py` удаляется.

### 2.5. Что это даёт архитектуре

- Слои `sources/mergers/renderers/domain` остаются **UI-agnostic**. Можно завтра сделать CLI, TUI, web-фронт — `core.pipeline.run` не меняется.
- Шаблоны в `ui/templates/*` — единственная точка, где «знают» про QML. Любой новый source (хоть OBS, хоть Vmix) реализует `ui_config: UIConfig(...)` + один шаблон — шелл автоматически показывает карточку + runtime-panel.
- QML — декларативный, тема и поведение переносятся из Figma Make близко 1:1, и **не надо** тащить React-рантайм или WebView.

---

## 3. Снос старого — deletion list

После успешной приёмки Phase 9 (см. §4) из репа удаляются:

### 3.1. Widgets-шелл (весь)

```
ui/shell/app.py                          1165 строк
ui/shell/main_window.py                  — если есть
ui/shell/settings_drawer.py               551
ui/shell/install_wizard.py                242
ui/shell/run_controller.py                184
ui/shell/add_source_dialog.py             213
ui/shell/_demo_stub_panel.py               84
ui/shell/theme.py                          76
ui/shell/screens/session_screen.py        899
ui/shell/screens/empty_state_screen.py    540
ui/shell/screens/models_screen.py         412
ui/shell/screens/onboarding_overlay.py    172
ui/shell/screens/__init__.py               21
ui/shell/__init__.py                        0
ui/shell/__pycache__/                    (gitignored)
```
**Итого:** ~4559 строк + вся папка `ui/shell/`.

### 3.2. Tkinter legacy

```
ui/gui_legacy.py                         (legacy tk шелл)
```
**Триггер удаления:** после Phase 5 (feature-parity баззик с tk выключается — tk его не видит).

### 3.3. Widgets-шаблоны (переписываются)

```
ui/templates/audio_source_template.py    — переписать на UITemplateQml
ui/templates/chat_source_template.py     — переписать
ui/templates/merger_template.py          — переписать
ui/templates/renderer_template.py        — переписать
ui/widgets/*                             — полностью удалить (QWidget-атомы)
```

### 3.4. Устаревшая документация

```
docs/architecture/ui-qt-migration.md     → переименовать в .archived.md
                                            (фазовый план для Widgets)
```

ADR-017 **не удаляется** — он получает amendment (§5.1 ниже). ADR-016 аналогично.

### 3.5. Тесты Widgets (если есть pytest-qt на shell)

```
tests/ui/test_shell_*.py                 — удалить все, что импортят ui.shell.*
tests/ui/test_settings_drawer.py         — переписать под QML
tests/ui/test_run_controller.py          — переписать под ui/engines/pipeline_controller.py
```

### 3.6. build.spec — не удаление, а полная переработка

`build.spec` сейчас **исключает** `QtQml`, `QtQuick`, `QtQuickControls2`, `QtQuickWidgets`, `QtSvg` — это ломает QML. Переписывается в Phase 8.

### 3.7. Прототип на ветке — что мёрджится, что пересматривается

Ветка `claude/implement-ui-foundation-KviVz` содержит 9 шагов QML-прототипа. После старта этого плана:

- `ui/qml/Theme.qml`, `ui/qml/controls/*`, `ui/qml/screens/*`, `ui/qml/timeline/*` — мёрджатся **как базовый визуальный слой** (Phase 1 — темизация, Phase 2–4 — экраны).
- `ui/engines/asr_worker.py`, `ui/engines/merger_worker.py`, `ui/engines/pipeline_controller.py` — **не мёрджатся as-is**, переписываются в Phase 5 чтобы реально дёргать `core.pipeline.run`.
- `ui/models/session_mock.py` — удаляется. Заменяется на реальный `ui/models/session_model.py` с данными из `core.discovery`.
- `ui/models/app_model.py`, `ui/models/model_registry.py` — ревьюится, оставляется частично.

---

## 4. Phased plan

| Phase | Работа | Оценка | Blocker |
|---|---|---|---|
| **0 — Решение** | Amendment к ADR-017 (PySide6 + **QML** как выбор), amendment к ADR-016 (`UITemplateQml` вместо `make_*_widget`). Открыть PR с обоими amendment-ами перед стартом кода. | 0.5 д | — |
| **1 — Фундамент** | Слить тематический слой с ветки: `Theme.qml`, `controls/*`, `Main.qml`, `Sidebar.qml`. Скрипт `scripts/gen_theme.py` генерит `Theme.qml` из `default_shadcn_theme.css`. `QQmlApplicationEngine` поднимает пустой `Main.qml` через `ui/shell/app.py` (переписан, ~80 строк). | 1 д | Phase 0 |
| **2 — Экраны idle** | `EmptyScreen.qml` (пустое состояние по §4 idle), `TimelineScreen.qml` idle, `SettingsScreen.qml` shell. Всё от `AppModel`-stub, без реальных данных. | 1 д | Phase 1 |
| **3 — Контракт v2** | Переписать `core/ui_contract.py` на `UITemplateQml`. Обновить `core/ui_registry.py` на lazy-resolve QML-путей. Templates `audio_source/chat_source/merger/renderer` пока — stub (возвращают реальный QML, но VM пустой). Unit-тесты на registry. | 1 д | Phase 0 amendment ADR-016 |
| **4 — Реальная discovery** | `SourceListModel` (QAbstractListModel) наполняется из `core.discovery.find_sessions` + `core.file_matchers`. Drop-folder → список файлов → карточки. TrackListModel из `.ogg` имён. | 1.5 д | Phase 2, Phase 3 |
| **5 — Wire pipeline** | `ui/engines/pipeline_controller.py` — переписан: вызывает `core.pipeline.run(session_dir, params, on_stage=self._emit_stage)` в `QThread`. `on_stage` маршалится через `Qt.QueuedConnection` в `AppModel.stageChanged`. Cancel = `thread.requestInterruption()` + проверка в стадиях. | 2 д | Phase 3, Phase 4 |
| **6 — Running/Done** | `TimelineScreen` состояния running/done по §6.2–6.4: TrackLaneRow с прогрессом, StitchOverlay (стичи мержера), DoneSummary со счётчиками, OutputChip с кнопкой «Открыть файл». Реальные значения от `PipelineController`. | 1.5 д | Phase 5 |
| **7 — Settings drawer** | `SettingsDrawer.qml` по §9. Переписать на QML анимацию (`Behavior on x` + OutCubic), scrim, sticky header/footer, dirty-state confirmation. Persist через `QSettings`. `SettingsModel(QObject)` экспозит свойства. | 1.5 д | Phase 6 |
| **8 — PyInstaller** | Переписать `build.spec`: убрать `PySide6.QtQml`, `PySide6.QtQuick`, `PySide6.QtQuickControls2`, `PySide6.QtQuickTemplates2`, `PySide6.QtSvg` из `_QT_EXCLUDES`. Добавить QML-файлы в `datas`. Добавить hidden imports для `PySide6.QtQuickControls2` style plugins. Сборка на чистой Windows-VM. Smoke: запуск exe → видит папку Craig → прогоняет одну реальную сессию. | 2 д | Phase 7 |
| **9 — Снос Widgets** | Удалить всё из §3.1 + §3.2 + §3.3. Удалить тесты §3.5 и написать новые pytest-qt на VM-уровень. Удалить `ui/gui_legacy.py`. Архивировать `docs/architecture/ui-qt-migration.md`. Одним PR-ом. | 1 д | Phase 8 зелёный билд |
| **10 — Тесты** | pytest-qt на `PipelineController` (мок-core), `SourceListModel`, `SettingsModel`. QML smoke test: `QQmlApplicationEngine` грузит каждый экран без warnings. CI: вызывается `build.spec` в матрице. | 2 д | Phase 9 |

**Итого:** ~14–15 рабочих дней.

---

## 5. Критерии приёмки (definition of done на бету)

1. Запуск `python -m ui` на чистой машине с установленным `PySide6`, `PyYAML`, `click` → открывается QML-шелл, виден Empty state.
2. Drag'n'drop папки Craig с `.ogg`-файлами → отображается список треков (real discovery).
3. Кнопка «Запустить» → реально вызывается `core.pipeline.run` → в UI капает прогресс стадий (`speech/chat/merge/render`) в реальном времени.
4. По окончанию — Done summary + клик на OutputChip открывает `merged.txt` в системном редакторе.
5. Settings drawer сохраняет hotwords, engine, compute_type → `QSettings` → виден при перезапуске.
6. `pyinstaller build.spec --noconfirm --clean` собирает `dist/session-transcriber/session-transcriber.exe` на Windows-VM; exe запускается без `python` в системе.
7. `pytest` зелёный; в `tests/ui/` нет ни одного импорта `ui.shell.*` или `ui.gui_legacy`.
8. В репе **нет** файлов из §3.1–§3.5.
9. ADR-017 и ADR-016 имеют `## Amendment (2026-0?-??)` с объяснением перехода на QML и ссылкой на этот документ.

---

## 6. Риски

1. **QML + PyInstaller на Windows.** QtQuickControls2 требует runtime-style plugin (Basic/Fusion) — PyInstaller его не всегда цепляет. Митигация: явный `hiddenimports` в Phase 8 + smoke-тест на чистой VM.
2. **LGPL для QtQuick.** Та же схема, что и для Widgets (dynamic DLL рядом с exe). Не использовать `--onefile`. Проверка в Phase 8.
3. **`QSettings` на Windows.** По умолчанию пишет в реестр — для exe без прав это ок, но ключи размазываются. Митигация: форсить `QSettings.IniFormat` + путь `%APPDATA%\ttrpg-transcriber\settings.ini`.
4. **QAbstractListModel boilerplate.** Больше кода на ListModel, чем в React с map-ом. Митигация: один base-класс `DictListModel` в `ui/models/_base.py`, от него наследуем.
5. **Тесты QML.** pytest-qt неплохо покрывает QObject, но настоящий QML покрывается только smoke-ом. Визуальные regression-ы ловим ручным прогоном по чек-листу `docs/design/screen-3-session.md` (checklist рождается в Phase 10).
6. **Откат.** До Phase 9 Widgets-шелл ещё в репе — можно крутить через другую entry-point (`python -m ui.shell`). После Phase 9 отката нет — перед сносом снимаем тэг `v0.9-widgets-frozen` как last-known-good.

---

## 7. Open questions

- **MVVM между шаблонами.** Как именно шаблон audio_source отдаёт `SettingsPanel.qml` контекстный объект? Вариант: шаблон возвращает `(qml_path, QObject)`, шелл кладёт объект в `engine.rootContext().setContextProperty(name, obj)` перед загрузкой компонента. Детали — в amendment-е ADR-016.
- **Несколько сессий одновременно.** MVP: одна сессия за раз. Параллельность — post-MVP (нужна очередь в PipelineController).
- **Project picker (Screen 2).** Handoff его пока не описывает подробно — MVP держит Empty state + Recent. Полноценный Project picker — post-MVP, отдельный handoff-пакет.
- **Real-time transcript preview.** §6.3 handoff-а — вне scope MVP (см. §8 handoff-а).

---

## 8. Progress log

- [ ] Phase 0 — ADR amendments
- [ ] Phase 1 — Theme/Main/Sidebar foundation
- [ ] Phase 2 — Idle screens
- [ ] Phase 3 — Contract v2 (`UITemplateQml`)
- [ ] Phase 4 — Real discovery → models
- [ ] Phase 5 — Wire `core.pipeline.run`
- [ ] Phase 6 — Running/Done states
- [ ] Phase 7 — Settings drawer
- [ ] Phase 8 — PyInstaller + build.spec rewrite
- [ ] Phase 9 — Снос Widgets + tk_legacy
- [ ] Phase 10 — Tests + CI
