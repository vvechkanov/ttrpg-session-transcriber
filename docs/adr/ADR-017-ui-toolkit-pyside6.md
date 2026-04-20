# ADR-017: UI toolkit — PySide6

**Status:** Accepted
**Date:** 2026-04-11
**Supersedes:** implicit tkinter decision from Приоритет 1 (`ui/gui.py`)
**Related:** ADR-016 (Module UI Contract), `docs/design/screen-3-session.md`,
`docs/architecture/ui-qt-migration.md`

---

## Context

- `ui/gui.py` (tkinter) достиг визуального потолка: тёплая палитра Figma
  Make v1 (`#FAF8F5` / `#D4843B` / `#2D2520`, радиусы 10 px, мягкие
  тени) не воспроизводится в tk без ttk-хаков и платформенной грязи.
- Screen 3 требует **SettingsDrawer** — оверлей 80% ширины окна,
  выезжающий справа поверх основного контента, со scrim'ом и анимацией
  220 мс `OutCubic`. В tkinter нет нативных средств: ни
  absolute-позиционированного оверлея, ни анимации `geometry` по кривой,
  ни `QScrollArea` с sticky header/footer. Костыли на `place()` +
  `after()` не дают нужного качества.
- Screen 3 также требует runtime-панель с N прогресс-барами треков,
  сигналами о смене состояния из worker-потока — в tk это ручной
  `queue.Queue` + `after(100, poll)`. В Qt это `Signal`/`Slot`
  с thread-affinity из коробки.
- Проект open-source, планируется распространять как установочный
  exe. Лицензия тулкита должна позволять commercial redistributable.
- Единственный разработчик + единственный пользователь, поэтому
  «learning curve» стоит дешевле, чем «визуальный потолок на всю
  жизнь проекта».

---

## Alternatives considered

| Вариант | Вердикт | Причина отказа |
|---|---|---|
| **tkinter (оставить)** | ❌ | Визуальный потолок, нет нативного drawer, нет анимации, нет сигналов между потоками |
| **CustomTkinter** | ❌ | Косметический слой поверх tk — тот же потолок для drawer и анимации; новая зависимость без решения root-проблем |
| **Flet** | ❌ | Flutter runtime тянет ~100 MB, изоляция от Python-потоков хуже чем Qt, молодое community |
| **pywebview + React/HTML** | ❌ | Два стека (Python backend + JS frontend), webview2 runtime на Windows, тяжело дебажить, ломает «single-dev»-модель |
| **Tauri + Rust** | ❌ | Сменить язык фронта, Rust toolchain у пользователей и в CI, overkill для desktop ASR-утилиты |
| **PyQt6** | ❌ | GPL/commercial dual-licensing — для open-source проекта чище LGPL от Qt for Python |
| **PySide6** | ✅ | См. «Decision» |

---

## Decision

Использовать **PySide6** (Qt for Python, Qt 6.x, LGPL v3).

**Почему именно PySide6:**

- **LGPL v3** — можно линковать статически или динамически в
  commercial/redistributable продукт без передачи исходников
  приложения, при соблюдении условий LGPL (возможность замены Qt-части).
  Для open-source проекта это самый чистый путь. У PyQt6 — GPL или
  платная commercial лицензия; нам не подходит.
- **Qt Widgets** — зрелый виджет-сет, `QFrame`, `QScrollArea`,
  `QPropertyAnimation`, `QStackedWidget`, `QGraphicsEffect` (тени и
  прозрачности), стилизация через QSS-подмножество CSS.
- **Signals/Slots** — `Qt.QueuedConnection` даёт thread-safe доставку
  событий из worker-потоков в GUI без ручного `queue.Queue` + polling.
- **MVVM-friendly** — `QObject`-модели + property bindings позволяют
  держать шелл тонким и тестировать ViewModel отдельно.
- **PyInstaller support** — готовые hooks, проверенный путь упаковки
  в single-folder dist на Windows.
- **Екосистема** — pytest-qt для GUI-тестов, Qt Designer опционально,
  QSS для цветовых токенов theme.css.

---

## Consequences

### Положительные

- Можно воспроизвести Figma Make v1 палитру 1:1 через QSS-токены
  (`color: #2D2520; background: #FAF8F5; border-radius: 10px;`).
- `SettingsDrawer` реализуется прямым способом: `QFrame(parent=window)`
  без layout + `QPropertyAnimation(b"geometry")`.
- Runtime прогресс-панель: worker в `QThread`, `Signal(TrackProgress)`
  летит в `QProgressBar.setValue` через `Qt.QueuedConnection`.
- Нативный look-and-feel Windows (шрифты, фокус-рамки, right-click).
- LGPL совместима с планами распространять exe как open-source
  продукт.

### Отрицательные

- **Размер бандла:** PyInstaller-сборка с PySide6 добавляет ~80 MB к
  exe (Qt6Core, Qt6Gui, Qt6Widgets + QtNetwork для некоторых
  зависимостей). Минимизируется флагом `--exclude` для неиспользуемых
  Qt-модулей (`QtWebEngine`, `QtMultimedia`, `QtSql` и т.п.).
- **Learning curve:** Signals/Slots, event loop, `parent`-ownership,
  `QThread` vs `threading.Thread` — новая ментальная модель по
  сравнению с tkinter. Смягчаем тем, что код изолирован в
  `ui/shell/` и `ui/templates/`, остальной проект не затрагивается.
- **Coexistence window:** во время миграции в репе живут оба тулкита
  (`ui/gui.py` — tk, `ui/shell/*` — qt). Выбор точки входа — через
  переменную окружения `UI_TOOLKIT=tk|qt`. Дублирование временное,
  снимается в фазе 9 плана миграции.
- **LGPL обязательства:** в дистрибутиве должен лежать текст LGPL и
  уведомление, что Qt можно заменить. Упаковка требует либо dynamic
  linking (по умолчанию у PySide6), либо выложенных object-файлов.
  Для нас это автоматически так как PyInstaller кладёт Qt-DLL-и
  отдельными файлами в dist.

### Нейтральные

- PySide6 и tkinter мирно сосуществуют в одном процессе при наличии
  одного event-loop'а за раз. Параллельный запуск двух GUI в одном
  процессе не поддерживается, но нам и не нужен — выбор делает
  `UI_TOOLKIT` на старте.

---

## Implementation

См. `docs/architecture/ui-qt-migration.md` — фазовый план миграции
(Phase 0 … Phase 10, ~10 рабочих дней суммарно).

Критическая зависимость: контракт модуля и шелл-протоколы определены
в **ADR-016**, который должен быть accepted до старта Phase 1
(`core/ui_contract.py`).

---

## Notes

- Решение **не** обязывает добавлять PySide6 в runtime-зависимости
  CLI-режима. `scripts/*` и `core/pipeline.py` продолжают работать без
  PySide6 установленного.
- Все GUI-зависимости кончаются в `ui/`. Слои `sources/`, `mergers/`,
  `renderers/`, `domain/`, `core/pipeline.py` не импортируют
  `PySide6.*` — это инвариант, обеспечиваемый ADR-016.

---

## Amendment (2026-04-20) — QML как основной шелл, Widgets снимается

**Status:** Accepted
**Trigger:** дизайн-handoff `_ _.zip` (извлечён в `docs/handoff/`) +
`docs/architecture/ui-qml-migration.md` (фазовый план).

### Context

Исходное решение «PySide6» было сформулировано в терминах **Qt
Widgets** (`QFrame`, `QScrollArea`, `QPropertyAnimation(b"geometry")`,
QSS). По нему построен `ui/shell/*` (~4559 строк, production на
2026-04-19).

Дизайн-handoff, пришедший 2026-04-20, предписывает **декларативный
QtQuick/QML-шелл**: `ApplicationWindow` + `StackLayout` + `ListView` +
`Behavior on x/opacity` + `Drawer` + `Popup`, Theme как `pragma
Singleton QtObject`. `QML_MAPPING.md` в handoff-е даёт готовую раскладку
(`ui/qml/screens/`, `ui/qml/timeline/`, `ui/qml/controls/`), готовый
`Theme.qml` и рекомендации по `QAbstractListModel` + `QThread + Worker`.

Qt Widgets-шелл этому handoff-у не отвечает: amber-parchment палитра,
waveform canvas с per-track прогрессом, stitch overlay с стаггер
анимациями, drawer справа с бэкдропом — всё это в Widgets потребует
много QSS-костылей и custom paintEvent-ов. QML собирает это
декларативно.

### Decision

**PySide6 остаётся** (LGPL, thread-safe signals, PyInstaller, Qt for
Python). Меняется **подсет**: с `QtWidgets` на
`QtQuick + QtQuickControls2 (стиль Basic) + QtQuickTemplates2 +
QtQml + QtSvg`. Qt 6.5+.

- Шелл — `QQmlApplicationEngine` + `Main.qml`, а не
  `QApplication + QMainWindow`.
- Экраны — QML-файлы в `ui/qml/screens/*`, не `QWidget`-подклассы в
  `ui/shell/screens/*`.
- Темизация — `Theme.qml` singleton, не `QSS` строка в `theme.py`.
- Persistence — `QSettings(IniFormat)` →
  `%APPDATA%\ttrpg-transcriber\settings.ini`.
- Воркеры — `QThread + worker.moveToThread(thread)` (паттерн handoff-а)
  вместо `QThread` subclass.

### Consequences

- **Плюс:** handoff воспроизводится декларативно и близко к 1:1,
  без custom paintEvent. Anim-ы (drawer slide, stitch fade-in,
  phase-bar pulse) — встроенный `Behavior { NumberAnimation }`.
- **Плюс:** меньше Python-кода в шелле (`ui/shell/app.py` сжимается с
  1165 строк до ~80 строк loader-а).
- **Плюс:** модели данных (`ui/models/*`) тестируются pytest-qt без
  запуска QML-движка — чистый QObject-интерфейс.
- **Минус (bundle):** QtQuick + QtQuickControls2 добавляют ~30 MB к
  PyInstaller-сборке поверх Widgets-базы. Ожидаемый total — ~110 MB
  (был ~80 MB). Порог 120 MB из исходного ADR всё ещё держится.
- **Минус (PyInstaller):** QtQuickControls2 Basic style plugin не
  подхватывается автоматически — нужен явный `hiddenimports` в
  `build.spec`. Риск mitigated smoke-тестом на чистой Windows-VM в
  Phase 9.
- **Нейтральное (LGPL):** та же схема, что и для Widgets — dynamic
  DLL рядом с exe, `onefile=False`, LGPL-notice в `licenses/`. Не
  меняется.

### Переходный план

См. `docs/architecture/ui-qml-migration.md`, фазы 0–11. Widgets-шелл
удаляется в Phase 10 одним PR-ом вместе с `ui/gui_legacy.py`,
`ui/templates/*`, тестами `tests/ui/test_*.py` под Widgets и старой
дизайн-документацией (`docs/design/flowstep-prompts/`,
`docs/design/mockups/figma-make/`, `docs/design/screen-3-session.md`).
Перед этим снимается тэг `v0.9-widgets-frozen` — last-known-good
Widgets-сборка для отката.

Документ `docs/architecture/ui-qt-migration.md` (завершённый фазовый
план Widgets-миграции) архивируется в `.archived.md` — он полезен как
история, но больше не руководство.
