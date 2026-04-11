# Module UI Template DI — implementation notes

**Статус:** **superseded by [ADR-016](../adr/ADR-016-module-ui-contract.md)** для канонического контракта.
Файл сохраняется как implementation notes: объясняет мотивацию,
обсуждает trade-off'ы, показывает примеры. За каноническими определениями
`UIConfig` / `SettingsPanelProtocol` / layer-rules — иди в ADR-016.
Open questions в §Open questions ниже считаются **снятыми** ADR-016;
оставлены здесь для истории.

**Дата исходных заметок:** 2026-04-11
**Уровень:** архитектурный слой, влияет на `sources/`, `mergers/`, `renderers/`, `ui/`

---

## Проблема

Каждый модуль в пайплайне (source / merger / renderer) должен показываться в
главном окне. Прямолинейный подход — «модуль сам поставляет свой виджет» — даёт
две проблемы:

1. **Дублирование UI-кода.** У нас, скорее всего, будет несколько audio-backend
   модулей (GigaAM-v3, Whisper/faster-whisper, sherpa-onnx для английского, GigaAM
   post-proc варианты, etc.). У всех audio-backend'ов UI почти идентичен: список
   дорожек, прогресс-бары, бейджи ролей, опционально — waveform. Если каждый
   модуль пишет свой виджет — получаем N почти одинаковых файлов.
2. **Нарушение слоёв.** Если модуль `sources/speech/gigaam.py` импортирует
   `tkinter`, он таскает UI-зависимость в доменный слой. При переходе на другой
   toolkit (PySide, Flet, web) придётся трогать каждый модуль.

---

## Решение

Ввести **отдельный слой UI-темплейтов** и связать его с модулями через
**конфигурационную DI-декларацию**.

### Новая структура

```
ui/
  shell/                       ← главное окно, навигация, роутинг
  templates/                   ← NEW: reusable UI templates
    audio_source_template.py   ← универсальный UI для ЛЮБОГО audio-backend
    chat_source_template.py    ← универсальный UI для ЛЮБОГО чат-парсера
    merger_template.py
    renderer_template.py
  widgets/                     ← низкоуровневые примитивы

sources/
  speech/
    gigaam.py                  ← объявляет ui_config.template = "audio_source"
    whisper.py                 ← объявляет ui_config.template = "audio_source"
  foundry_chat/
    parser.py                  ← объявляет ui_config.template = "chat_source"
```

### Контракт модуля

Каждый модуль-участник пайплайна экспортирует `ui_config`:

```python
from core.ui_contract import UIConfig

class GigaAMSource:
    ui_config = UIConfig(
        template="audio_source",
        params={
            "show_waveforms": True,
            "show_hotwords": True,
            "show_precision_selector": True,  # fp32/int8
            "show_language_hint": False,
        },
    )

class WhisperSource:
    ui_config = UIConfig(
        template="audio_source",      # тот же темплейт!
        params={
            "show_waveforms": True,
            "show_hotwords": False,
            "show_precision_selector": True,
            "show_language_hint": True,    # whisper умеет разные языки
            "show_beam_size": True,         # whisper-specific параметр
        },
    )
```

Модуль **не импортирует** tkinter, PySide, ничего GUI-specific. Он только
декларирует строковый идентификатор темплейта и словарь параметров для него.

### Контракт темплейта

Темплейт живёт в `ui/templates/` и экспортирует три фабрики виджетов — по
одной на каждое состояние модуля в UI:

```python
# ui/templates/audio_source_template.py

def make_home_card(parent, module, state, params) -> Widget:
    """Компактная карточка в блоке 1 (источники).

    Показывает иконку, имя, минимум инфы (список файлов), кнопку [Настроить].
    Состояния: idle / running (ярко) / dimmed / error / done (✓).
    """

def make_runtime_panel(parent, module, state, params) -> Widget:
    """Развёрнутая панель для блока 3 (обработка), появляется когда
    именно этот модуль сейчас работает.

    Для audio_source это: список треков, прогресс-бары, ETA, per-track статусы.
    """

def make_settings_panel(parent, module, state, params) -> Widget:
    """Контент для side drawer'а [Настроить].

    Чекбоксы/поля/таблицы из params. Валидация. Save/cancel кнопки НЕ
    здесь — их рисует хост (SettingsDrawer). Возвращаемый виджет должен
    реализовывать SettingsPanelProtocol (см. ниже).
    """
```

Все три фабрики получают:
- `parent` — Qt parent widget (`QWidget`). Для `make_settings_panel`
  хост кладёт результат в `QScrollArea` бокового drawer'а.
- `module` — ссылка на сам модуль (для чтения и записи его состояния)
- `state` — снэпшот runtime-состояния (для runtime_panel — прогресс, для
  home_card — «idle/running/dimmed», etc.)
- `params` — словарь из `module.ui_config.params`

### Резолвер

В `core/ui_registry.py`:

```python
_TEMPLATE_REGISTRY: dict[str, TemplateModule] = {
    "audio_source": audio_source_template,
    "chat_source":  chat_source_template,
    "merger":       merger_template,
    "renderer":     renderer_template,
}

def resolve_template(ui_config: UIConfig) -> TemplateModule:
    return _TEMPLATE_REGISTRY[ui_config.template]
```

Главное окно:

```python
for module in session.active_modules:
    tmpl = resolve_template(module.ui_config)
    card = tmpl.make_home_card(parent, module, state, module.ui_config.params)
    cards_frame.add(card)
```

### Хост: SettingsDrawer

`[Настроить]` на любой карточке → открывается **боковой drawer справа**
(не модальное окно). Drawer — это `QFrame` с `parent = main_window`, но
НЕ помещённый в layout: он живёт как оверлей поверх главного контента,
как Android navigation drawer / гамбургер-меню.

Параметры drawer'а (MVP):

- **Ширина:** 80% от текущей ширины главного окна, адаптивно на `resizeEvent`.
  Нижняя граница — 320 px для очень узких окон.
- **Поведение:** перекрывает правые 80% окна, **не сдвигает** основной
  контент. Основной контент остаётся на месте, drawer ложится сверху.
- **Backdrop:** полноэкранный полупрозрачный слой
  (`rgba(45,37,32,0.25)` — foreground @ 25% alpha) покрывает **всё окно
  целиком**, лежит **под** drawer'ом (как в Android navigation drawer).
  Визуально виден только на левых ~20%, потому что справа его закрывает
  сам drawer. Клик по любой видимой части backdrop'а → закрытие drawer'а.
- **Анимация:** `QPropertyAnimation` по `geometry`, 220 мс, `OutCubic`.
  Старт — за правым краем окна, финиш — прижат к правому краю.
- **Закрытие:** клик по backdrop, Esc, крестик в хедере, кнопки Отмена/Сохранить.
  При `has_unsaved_changes() == True` — подтверждение «Сохранить изменения?».
- **Одновременность:** в любой момент открыт **один** drawer на всё
  приложение. Открытие нового первым закрывает предыдущий (без
  подтверждения — по MVP-контракту).
- **Во время обработки:** `[Настроить]` задизейблены, drawer не открывается.
- **Реализация:** `ui/shell/settings_drawer.py::SettingsDrawer`. Public API —
  `open_with_panel(panel, *, title, subtitle)`, `close_drawer(*, force=False)`,
  сигналы `saved` / `cancelled`. `open_with_panel` enforces
  `isinstance(panel, SettingsPanelProtocol)` → `TypeError` если нарушено.

Структура drawer'а сверху вниз:

1. **Sticky header** (~72 px) — иконка модуля, заголовок («Настройки ·
   Аудио»), подзаголовок (backend + язык), крестик справа. Рисует хост.
2. **QScrollArea** — содержит `make_settings_panel(...)` от модуля. Модуль
   отвечает только за это.
3. **Sticky footer** (~64 px) — слева индикатор dirty, справа
   `[Отмена]` ghost + `[Сохранить]` primary. Рисует хост.

Так как drawer занимает 80% окна, он ощущается как «второй экран», не
как всплывашка. Типографика и отступы — такие же как на главном экране,
без экономии.

### Контракт SettingsPanelProtocol

Виджет, возвращаемый `make_settings_panel`, должен реализовывать:

```python
from typing import Protocol
from PySide6.QtCore import Signal

class SettingsPanelProtocol(Protocol):
    changed: Signal  # emit при любом изменении поля (для dirty-индикатора)

    def validate(self) -> list[str]:
        """Список текстовых ошибок; пусто = можно сохранять."""

    def apply_changes(self) -> None:
        """Записать значения полей в модуль. Вызывает хост при Save."""

    def has_unsaved_changes(self) -> bool:
        """Флаг для индикации dirty и подтверждения при закрытии."""
```

Хост слушает `changed`, подсвечивает индикатор, блокирует `[Сохранить]`
пока `validate()` не вернёт пустой список.

---

## Следствия

### Плюсы

1. **Нулевое дублирование.** Добавление нового audio-backend'а = 1 строчка
   `ui_config` + опционально пара новых параметров.
2. **Чистые слои.** `sources/`, `mergers/`, `renderers/` не импортируют
   GUI-библиотеки. При миграции с tkinter на что-то современное (PySide,
   Flet) меняется только `ui/templates/*` и `ui/shell/*`. Контракт
   модулей не трогается.
3. **Тестируемость.** Темплейты тестируются с фиктивными модулями.
   Модули тестируются без UI вообще.
4. **Легко добавить дополнительный view.** Например, `make_log_excerpt(...)`
   для вкладки `Журнал`. Добавляется в контракт темплейта один раз,
   используется всеми модулями соответствующего типа.

### Минусы / риски

1. **Дополнительная абстракция.** Новичку в проекте придётся понять: где
   UI модуля? → в ui_config указан темплейт → темплейт в `ui/templates/`.
   Смягчаем хорошей документацией (это доку этот файл и есть).
2. **Ригидность темплейта.** Если какой-то будущий модуль захочет
   показывать что-то принципиально другое, он вынужден либо впихивать в
   существующий темплейт новые `params`, либо создавать новый темплейт.
   Политика: **создавать новый темплейт имеет смысл только когда различия
   существенные.** Для вариаций — расширять params.
3. **Зависимость core → ui_config dataclass.** Чтобы `sources/` могли
   импортировать `UIConfig`, он должен жить в нейтральном месте. Варианты:
   `core/ui_contract.py` (работает, core — нейтральный слой) или
   `domain/ui_contract.py` (чище, но domain должен остаться безGUI —
   `UIConfig` это просто dataclass, GUI-лексики в нём нет). Склоняюсь к
   `core/ui_contract.py`.

---

## План внедрения

1. **ADR-016** — формализовать контракт, получить sign-off архитектора
2. **`core/ui_contract.py`** — объявить `UIConfig` dataclass
3. **`ui/templates/audio_source_template.py`** — первый темплейт, под
   GigaAM
4. **`sources/speech/gigaam.py`** — добавить `ui_config`
5. **`core/ui_registry.py`** — резолвер
6. **`ui/shell/session_screen.py`** — переписать Screen 3 с новым контрактом
7. **Тесты:** `tests/ui/test_templates.py`, `tests/core/test_ui_registry.py`
8. **Пример**: добавить заглушку `sources/speech/whisper_stub.py` с
   `ui_config.template = "audio_source"` но другими params — убедиться
   что один темплейт обслуживает оба
9. **Обновить ARCHITECTURE.md** — добавить раздел про UI templates layer

---

## Open questions для архитектора

1. `UIConfig` жить в `core/` или в `domain/`?
2. Тесты темплейтов — как гонять GUI-код в CI? Варианты: (а) mock tkinter,
   (б) отдельный marker, (в) отложить до post-MVP.
3. Hot-reload темплейтов в dev-режиме — полезно или YAGNI?
4. Что делать с модулями, которые **не хотят** иметь UI вообще (например,
   background preprocessing в post-MVP)? Вариант: `ui_config = None` →
   модуль не появляется на экране, но работает по pipeline.
