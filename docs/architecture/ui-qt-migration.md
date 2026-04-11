# UI Qt Migration — tkinter → PySide6

**Status:** working document (not an ADR)
**Owner:** architect (plan) + python-dev (execution)
**Related:** ADR-017 (UI toolkit — PySide6), ADR-016 (Module UI Contract),
`docs/design/screen-3-session.md`

---

## Purpose

Фазовый план миграции UI с tkinter на PySide6 без big-bang refactor.
Документ живёт и правится по ходу миграции: отметки «done», поправки
оценок, обнаруженные сюрпризы. Когда миграция завершена (Phase 10),
документ становится архивным read-only.

---

## Target folder layout

```
ui/
  shell/                         # главное окно, приложение, хост SettingsDrawer
    app.py                       # QApplication, main(), env switch
    main_window.py               # QMainWindow, breadcrumbs, tab bar
    settings_drawer.py           # QFrame overlay + scrim + animation + header/footer
    screens/
      session_screen.py          # Screen 3 — четыре вертикальных блока
      project_picker_screen.py   # (future; не в MVP Qt migration)

  templates/                     # reusable UI templates — ADR-016
    __init__.py                  # экспортирует шаблоны для core/ui_registry.py
    audio_source_template.py     # make_home_card / make_runtime_panel / make_settings_panel
    chat_source_template.py
    merger_template.py
    renderer_template.py

  widgets/                       # низкоуровневые Qt-примитивы
    help_tooltip.py              # [?] кнопка с QToolTip
    status_chip.py               # чип «готов» / «в работе» / «ошибка»
    progress_row.py              # строка прогресса трека (бар + label + ETA)

  gui.py                         # LEGACY tkinter — остаётся до Phase 9
  __init__.py

core/
  ui_contract.py                 # UIConfig + SettingsPanelProtocol (ADR-016)
  ui_registry.py                 # resolve_template() — единственный upward импорт в ui/
```

Всё ниже `ui/` — новое. Всё выше (`sources/`, `mergers/`, `renderers/`,
`domain/`, `core/pipeline.py`) — не трогается.

---

## Dependency chart

```
┌─────────────────────────────────┐
│ ui/shell/*                      │  PySide6, core/ui_registry,
│ (app, main_window, drawer,      │  ui/templates, core/pipeline
│  screens/*)                     │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ ui/templates/*                  │  PySide6, core/ui_contract,
│ (audio_source, chat_source,     │  ui/widgets
│  merger, renderer)              │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ ui/widgets/*                    │  PySide6 only
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ core/ui_registry.py             │  ui/templates/*  (⚠ controlled
│                                 │  upward import — см. ADR-016)
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ core/ui_contract.py             │  pure stdlib, dataclass + Protocol
└─────────────────────────────────┘
             ▲
             │ ONLY import from sources/ allowed
┌────────────┴────────────────────┐
│ sources/*, mergers/*,           │  NO PySide6, NO ui.*, NO tkinter
│ renderers/*, domain/*           │  ONLY core/ui_contract
└─────────────────────────────────┘
```

**Инварианты (повторно из ADR-016):**

- `sources/ ∪ mergers/ ∪ renderers/ ∪ domain/` → может импортить
  `core/ui_contract.py` и больше ничего UI-related.
- `ui/templates/` → `PySide6`, `core/ui_contract`, `ui/widgets/`.
- `ui/shell/` → `ui/templates/`, `core/ui_registry`, `PySide6`,
  `core/pipeline`.
- `core/ui_registry.py` → `ui/templates/*` (единственный разрешённый
  upward import в проекте; явно оформлен как исключение).

Любой другой upward import — блокер ревью.

---

## Phased plan

| Phase | Работа | Оценка | Blocker от architect |
|---|---|---|---|
| **0** | Infrastructure: ветка, добавить `PySide6` в `requirements.txt` / `pyproject.toml`, скелет папок `ui/shell/`, `ui/templates/`, `ui/widgets/`, hello-world `app.py` с пустым `QMainWindow`, env-switch `UI_TOOLKIT=tk|qt`, smoke test запуска | ~0.5 дня | Нет — можно параллелить с ADR работой |
| **1** | `core/ui_contract.py` + `core/ui_registry.py` по ADR-016. Файлы минимальные: `UIConfig`, `SettingsPanelProtocol`, `resolve_template`, `_TEMPLATE_REGISTRY` с placeholder-импортами для ещё не существующих шаблонов (lazy import, чтобы резолвер падал только когда шаблон реально нужен) | ~0.5 дня | **ADR-016 accepted** |
| **2** | `ui/shell/settings_drawer.py` — `QFrame` overlay, scrim, `QPropertyAnimation(b"geometry")` 220 мс OutCubic, sticky header (~72 px) + `QScrollArea` + sticky footer (~64 px) с кнопками Отмена/Сохранить, dirty indicator, Esc close, scrim click close, `has_unsaved_changes` confirmation. Без контента — тестовая форма-заглушка | ~1 день | ADR-017 accepted, Phase 0, Phase 1 |
| **3** | `ui/shell/screens/session_screen.py` — четыре блока, только idle state. Фиктивные карточки без реальных модулей. QSS темы из `theme.css`. Навигация (breadcrumb + tab bar) тоже пока фиктивная | ~1 день | Phase 2 |
| **4** | `ui/templates/audio_source_template.py` — первый реальный шаблон. Реализует `make_home_card` + `make_settings_panel` (runtime_panel пока stub). Содержит секции из Figma Make v1 prompt: входные файлы, участники и роли, движок, hotwords, advanced accordion. Работает с fake-модулем в dev mode | ~1 день | Phase 3 |
| **5** | Wire реальный модуль: добавить `ui_config = UIConfig(template="audio_source", params={...})` в `sources/speech/gigaam.py`. Проверить `resolve_template(GigaAMSource.ui_config)` → возвращает модуль шаблона. Home-card рендерится из реального инстанса. Settings panel читает/пишет speaker_map и hotwords GigaAM | ~0.5 дня | Phase 4 |
| **6** | `make_runtime_panel` для `audio_source_template` + `QThread` воркер + `Signal(TrackProgress)`, `Qt.QueuedConnection`. Прогресс GigaAM реально капает в UI. Состояния idle/running/done/error у блока 3 | ~1.5 дня | Phase 5 |
| **7** | Running + Done состояния Session Detail целиком. Карточки блока 1 переключаются в dimmed/highlighted в зависимости от running модуля. Done-сводка как описано в §6.4 screen-3-session.md | ~1 день | Phase 6 |
| **8** | Stubs шаблонов: `chat_source_template`, `merger_template`, `renderer_template`. Home-card + пустой settings panel. Runtime panel — только метки «в работе / готово». Цель — чтобы весь пайплайн визуально отображался, даже без полноценных UI для non-audio модулей | ~1 день | Phase 7 |
| **9** | Feature parity с текущим `ui/gui.py`: запуск pipeline, выбор project/session, speaker_map editing, hotwords, смена backend, обработка ошибок. User acceptance → retire `ui/gui.py` (удалить после sign-off) | ~1 день + тестирование | Phase 8 |
| **10** | PyInstaller `build.spec`: `--exclude-module` для ненужных Qt-модулей (QtWebEngine, QtMultimedia, QtSql, QtDBus и т.п.), сборка single-folder dist, smoke test на чистом Windows, проверка LGPL notice в дистрибутиве | ~0.5 дня | Phase 9 |

**Итого:** ~10 рабочих дней (чистое время, без учёта ожидания ревью,
переключений на другие задачи, сюрпризов).

---

## Parallel tracks

- **Architect (этот агент):** ADR-016 и ADR-017 — blocker для Phase 1 и
  Phase 2, но **НЕ для Phase 0** (инфраструктура, зависимости, скелет).
  Python-dev может начинать Phase 0 параллельно с написанием ADR.
- **Python-dev:** Phase 0 → ждёт ADR accepted → Phase 1 → Phase 2 → ...
- **QA:** тестовая матрица и pytest-qt setup — готовятся в Phase 8,
  активируются в Phase 9.
- **ML-specialist:** не затронут миграцией; `sources/speech/gigaam.py`
  получает один новый атрибут в Phase 5, остальной код не меняется.

---

## Rollback strategy

`ui/gui.py` остаётся в репе **до конца Phase 9** и user sign-off.
Переключение — через переменную окружения:

```bash
# Legacy tkinter (default до Phase 9)
set UI_TOOLKIT=tk
python -m session_transcriber

# Новый Qt
set UI_TOOLKIT=qt
python -m session_transcriber
```

Точка входа в `ui/shell/app.py` (или сохранённом `__main__.py`)
читает переменную и роутит на нужный UI:

```python
# псевдокод — реализация в python-dev
toolkit = os.environ.get("UI_TOOLKIT", "tk").lower()
if toolkit == "qt":
    from ui.shell.app import main_qt
    main_qt()
else:
    from ui.gui import main_tk
    main_tk()
```

Если Qt-ветка падает в продакшене у пользователя — он просто
переключает переменную и возвращается на tk. Это страховка на
период миграции.

**Удаление `ui/gui.py`** — отдельный коммит в Phase 9, после того
как Qt-ветка прошла две полные реальные сессии пользователя без
регрессий.

---

## Out of scope for MVP Qt migration

Те же исключения, что и у Screen 3 спеки (§8 screen-3-session.md):

- Pause / cancel кнопок во время processing.
- Drawer для второго мержера (только один мержер в MVP).
- Real-time transcript preview в блоке 3.
- Встроенный редактор транскрипта.
- Multi-session parallelism.
- Project picker screen (Screen 2 / Screen 1) — остаются на tk до
  отдельного решения post-MVP. Session Screen — единственный Qt-экран
  в MVP.
- Hot-reload шаблонов в dev — YAGNI, см. ADR-016 Q3.
- Полноценные pytest-qt тесты — активируются в Phase 9, не раньше
  (ADR-016 Q2).

---

## Known risks

1. **Project picker на tk, Session screen на qt.** Переход между ними
   в одном процессе — открытый вопрос. Варианты: (a) весь процесс
   перезапускается при смене экрана (ugly но простое); (b) project
   picker мигрируется на qt тоже (расширяет scope); (c) session
   screen запускается в отдельном subprocess (сложно). MVP-решение:
   оставляем project picker на tk, session screen запускается
   отдельной командой / кнопкой, которая закрывает tk-окно и
   открывает qt-окно. Решаем детально в Phase 9.
2. **QSS покрытие.** Некоторые токены из `theme.css` (radius 10 px,
   тени на карточках) потребуют `QGraphicsDropShadowEffect` вместо
   CSS box-shadow. Проверяется в Phase 2-3.
3. **PyInstaller bundle size.** Ожидаем ~80 MB прироста. Если
   получим >120 MB — ревизим exclude list в Phase 10. Если меньше —
   не трогаем.
4. **LGPL compliance.** Проверить, что PyInstaller кладёт Qt DLL-и
   отдельными файлами (dynamic linking) — это обеспечивает
   replaceability требуемую LGPL. Не использовать
   `--onefile` — он упаковывает DLL внутрь exe и усложняет соблюдение
   лицензии.

---

## Progress log

(Заполняется по ходу выполнения.)

- [ ] Phase 0 — infrastructure
- [ ] Phase 1 — `core/ui_contract.py` + `core/ui_registry.py`
- [ ] Phase 2 — `settings_drawer.py`
- [ ] Phase 3 — `session_screen.py` idle
- [ ] Phase 4 — `audio_source_template.py`
- [ ] Phase 5 — wire GigaAMSource.ui_config
- [ ] Phase 6 — runtime panel + QThread + signals
- [ ] Phase 7 — running/done states
- [ ] Phase 8 — chat/merger/renderer template stubs
- [ ] Phase 9 — feature parity + retire gui.py
- [ ] Phase 10 — PyInstaller build
