# ADR-016: Module UI Contract

**Status:** Accepted
**Date:** 2026-04-11
**Related:** ADR-017 (UI toolkit — PySide6),
`docs/architecture/ui-qt-migration.md`,
`docs/design/screen-3-session.md`,
`docs/architecture/module-ui-template-di.md` (теперь — implementation notes,
канонический источник решения — этот ADR)

---

## Context

- Screen 3 (Session Detail) состоит из карточек source/merger/renderer
  модулей. На каждую карточку нужны минимум две UI-проекции: home-card
  (компактная в блоке 1/2/4) и runtime-panel (развёрнутая в блоке 3),
  плюс settings-panel в SettingsDrawer.
- Backend'ы ASR (GigaAM, faster-whisper, sherpa-onnx, …) имеют почти
  идентичные требования к UI: список треков, прогресс-бары, таблица
  спикеров. Прямолинейный подход «каждый модуль несёт свой виджет»
  даёт N почти одинаковых файлов и провоцирует drift.
- Прямой импорт GUI-тулкита (`tkinter` сейчас, `PySide6` после ADR-017)
  из `sources/speech/gigaam.py` ломает направление зависимостей
  (`sources/` → `ui/`), описанное в `ARCHITECTURE.md`.
- Нужно формализовать контракт так, чтобы:
  1. переход tk → Qt (ADR-017) не требовал менять ни один файл в
     `sources/`, `mergers/`, `renderers/`;
  2. добавление нового audio-backend'а стоило одну строчку
     `ui_config = UIConfig(...)`;
  3. шелл (SettingsDrawer, screens) оставался единственным местом,
     знающим про виджеты.

---

## Decision

Ввести **Module UI Contract** — декларативный DI для UI модулей
pipeline:

1. Каждый модуль (source/merger/renderer) несёт атрибут класса
   `ui_config: UIConfig | None`.
2. `UIConfig` — нейтральный dataclass (`template: str`, `params: dict`,
   `visible: bool`), живёт в **`core/ui_contract.py`**.
3. Три фабрики виджетов живут в **reusable templates** —
   `ui/templates/<name>_template.py`. Один шаблон обслуживает все
   backend'ы одного типа.
4. **Резолвер** в `core/ui_registry.py` переводит
   `ui_config.template` в модуль шаблона.
5. **`SettingsPanelProtocol`** — минимальный структурный интерфейс
   виджета, возвращаемого `make_settings_panel`. Живёт в
   `core/ui_contract.py` рядом с `UIConfig`.
6. Модули, которым UI не нужен (post-MVP preprocessing), указывают
   `ui_config = None` — они участвуют в pipeline, но не появляются
   на экране.

---

## Canonical types

Единственное каноническое место объявления —
`core/ui_contract.py`. Файл **не импортирует** ни `PySide6`, ни
`ui/*`, ни `sources/*`. Это чистый dataclass + Protocol.

```python
# core/ui_contract.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class UIConfig:
    """Декларативная UI-привязка модуля pipeline.

    Модуль (source/merger/renderer) объявляет это как атрибут класса::

        class GigaAMSource:
            ui_config = UIConfig(
                template="audio_source",
                params={"show_hotwords": True, "precision_options": ("fp32", "int8")},
            )

    Модуль НЕ импортирует PySide6 и НЕ импортирует из ``ui/``.
    """

    #: Идентификатор шаблона в ``ui/templates/``. Резолвится через
    #: ``core.ui_registry.resolve_template``. Примеры: ``"audio_source"``,
    #: ``"chat_source"``, ``"merger"``, ``"renderer"``.
    template: str

    #: Параметры для шаблона. Feature-флаги, опции, преднастроенные
    #: значения селекторов. Шаблон читает этот словарь и решает, какие
    #: поля показывать и с какими опциями.
    params: dict[str, Any] = field(default_factory=dict)

    #: Если ``False`` — модуль выполняется в pipeline, но не показывается
    #: на экране. Используется для фоновых post-processor'ов, debug-хуков,
    #: telemetry-коллекторов. По умолчанию ``True``.
    visible: bool = True


@runtime_checkable
class SettingsPanelProtocol(Protocol):
    """Контракт виджета, возвращаемого ``make_settings_panel``.

    Хост (SettingsDrawer) полагается только на эти члены. Виджет
    реализуется в ``ui/templates/<name>_template.py`` и может быть
    любым ``QWidget``-ом — важно только наличие ``changed`` Signal'а
    и трёх методов.
    """

    #: PySide6 ``Signal`` без аргументов. Шаблон эмитит его при каждом
    #: изменении любого поля формы (checkbox, text change, slider).
    #: Хост слушает для подсветки dirty-индикатора и активации кнопки
    #: ``[Сохранить]``.
    #:
    #: На уровне typing ``Signal`` не типизирован как атрибут Protocol
    #: корректно во всех версиях mypy; используем ``Any`` комментарий,
    #: runtime-проверка не требуется.
    changed: Any

    def validate(self) -> list[str]:
        """Вернуть список текстовых ошибок.

        Пустой список = форма валидна, можно вызывать ``apply_changes``.
        Непустой = хост показывает ошибки под формой и блокирует Save.
        Вызывается хостом при клике на ``[Сохранить]``, ДО
        ``apply_changes``.
        """

    def apply_changes(self) -> None:
        """Записать значения полей в модуль.

        Вызывается хостом после успешного ``validate()``. После возврата
        хост закрывает drawer и считает `has_unsaved_changes()` за False.
        Метод должен быть идемпотентен.
        """

    def has_unsaved_changes(self) -> bool:
        """Есть ли незафиксированные изменения.

        Используется хостом при закрытии drawer'а (Esc / scrim / [Отмена] /
        закрытие окна) — если True, показывается диалог «Сохранить
        изменения?».
        """
```

Шаблоны объявляют **три фабрики**:

```python
# ui/templates/audio_source_template.py — псевдокод контракта, не реализация
def make_home_card(parent, module, state, params): ...         # QWidget
def make_runtime_panel(parent, module, state, params): ...     # QWidget
def make_settings_panel(parent, module, state, params): ...    # SettingsPanelProtocol
```

Все три получают:

- `parent` — Qt-родитель (`QWidget`). Для `make_settings_panel` хост
  кладёт результат в `QScrollArea` боковой панели.
- `module` — ссылка на инстанс модуля pipeline. Шаблон читает и
  пишет его настройки через публичный API модуля (атрибуты,
  `apply_settings()` и т.п.).
- `state` — снэпшот runtime-состояния (`idle` / `running` / `dimmed` /
  `error` / `done`, прогресс, ETA). Передаётся хостом.
- `params` — словарь из `module.ui_config.params`.

---

## Resolver

```python
# core/ui_registry.py — canonical map template_id → module
from typing import Any

from core.ui_contract import UIConfig
from ui.templates import (
    audio_source_template,
    chat_source_template,
    merger_template,
    renderer_template,
)

_TEMPLATE_REGISTRY: dict[str, Any] = {
    "audio_source": audio_source_template,
    "chat_source":  chat_source_template,
    "merger":       merger_template,
    "renderer":     renderer_template,
}


def resolve_template(ui_config: UIConfig):
    try:
        return _TEMPLATE_REGISTRY[ui_config.template]
    except KeyError as e:
        raise KeyError(
            f"Unknown UI template: {ui_config.template!r}. "
            f"Registered: {sorted(_TEMPLATE_REGISTRY)}"
        ) from e
```

`core/ui_registry.py` — **единственное** место во всём проекте, где
`core/` импортирует из `ui/`. Это контролируемый «upward» импорт,
оправданный тем, что резолвер по определению должен знать о
существовании шаблонов. Все остальные «upward» импорты запрещены.

---

## Layer rules (invariants)

**Обязательные инварианты** (проверяются ревью и, как только будет
CI, статическим линтером):

1. `sources/`, `mergers/`, `renderers/`, `domain/` **НЕ импортируют**
   `PySide6.*`, не импортируют `ui.*`, не импортируют `tkinter.*`.
2. Эти слои могут импортировать **только** `core/ui_contract.py`
   (dataclass + Protocol) — и не более. Никакого `core/ui_registry.py`.
3. `ui/templates/*` импортируют `PySide6.*`, `core/ui_contract.py`,
   `ui/widgets/*` — и ничего из `sources/` (шаблоны работают через
   duck-typed `module` аргумент).
4. `ui/shell/*` импортирует `ui/templates/*`, `core/ui_registry.py`,
   `PySide6.*`, `core/pipeline.py`.
5. `core/ui_registry.py` импортирует `ui/templates/*` (единственное
   исключение из правила направления зависимостей).

Любое нарушение — блокер при ревью. Формулировка из `ARCHITECTURE.md`:
«направление зависимостей строго однонаправленное: `ui → core →
sources/mergers/renderers/domain`». ADR-016 уточняет это правило для
нового UI-слоя.

---

## SettingsDrawer lifecycle

Хост-drawer живёт в `ui/shell/settings_drawer.py` (см. §9 в
`docs/design/screen-3-session.md`). Взаимодействие с
`SettingsPanelProtocol`:

1. Пользователь кликает `[Настроить]` на карточке.
2. Шелл вызывает `template.make_settings_panel(drawer_scroll_area,
   module, state, params)` — получает виджет `panel`.
3. Шелл кладёт `panel` в `QScrollArea`, подключается к `panel.changed`
   и при каждом сигнале перерисовывает dirty-индикатор в footer'е.
4. Клик на `[Сохранить]` → шелл вызывает `panel.validate()`.
   - Если список ошибок пуст → `panel.apply_changes()` → drawer
     закрывается анимацией.
   - Если непуст → шелл показывает ошибки под формой, кнопка
     остаётся доступной, drawer не закрывается.
5. Клик на `[Отмена]` / Esc / scrim / крестик / закрытие окна →
   шелл проверяет `panel.has_unsaved_changes()`:
   - False → закрыть без вопроса.
   - True → модальное подтверждение «Сохранить изменения?»
     (Да / Нет / Отмена).
6. Во время processing'а (`pipeline.is_running`) все кнопки
   `[Настроить]` задизейблены, drawer не открыть.

---

## Open questions — resolved

### Q1. Где живёт `UIConfig` — `core/ui_contract.py` или `domain/ui_contract.py`?

**Решение:** `core/ui_contract.py`.

**Обоснование:** `domain/` в текущей архитектуре
(`ARCHITECTURE.md`, §3) — чистые value-object'ы предметной области
(`SpeechSegment`, `SpeakerMap`, etc.), без инфраструктурных
абстракций. `UIConfig` — это инфраструктурный контракт между слоями,
пусть и представленный через dataclass. Место таких контрактов —
`core/`. Кроме того, `core/pipeline.py` уже импортируется из
`sources/base.py` через `Source` ABC, значит путь `sources/ →
core/*` уже легитимен.

### Q2. Тесты виджетов в CI — pytest-qt с offscreen, маркер, или отложить?

**Решение:** **pytest-qt с `QT_QPA_PLATFORM=offscreen`**, под
маркером `@pytest.mark.gui`, по умолчанию **отключено** в CI до
Phase 9 плана миграции.

**Обоснование:** на этапе Phase 2-8 у нас ещё нет стабильного набора
шаблонов — тесты протухают быстрее, чем пишутся. После Phase 9
(retire `ui/gui.py`) подключаем pytest-qt с offscreen платформой, а
маркер `gui` позволяет локально прогонять GUI-тесты выборочно. До
Phase 9 все гарантии контракта покрываются unit-тестами на
`core/ui_registry.py` + structural `isinstance(..., SettingsPanelProtocol)`
проверками (благо Protocol помечен `@runtime_checkable`).

Что покрываем тестами до Phase 9:

- `core/ui_contract.py` — dataclass round-trip, `visible` default.
- `core/ui_registry.py` — resolve известных template, KeyError на
  неизвестных, явный список зарегистрированных template id.
- В `sources/speech/gigaam.py` — smoke-тест: `GigaAMSource.ui_config`
  существует, `template == "audio_source"`, `params` — dict.

### Q3. Hot-reload шаблонов в dev-режиме?

**Решение:** **YAGNI**. Не делаем.

**Обоснование:** у проекта один разработчик + один пользователь.
Перезапуск dev-приложения после изменения шаблона — 2 секунды. Hot
reload на Qt требует либо `importlib.reload` плюс аккуратное
пересоздание всех виджетов (что само по себе может ломаться на
parent ownership), либо watchdog на файловую систему. Сложность
непропорциональна выгоде. Если когда-нибудь появится второй
разработчик и станет мешать — вернёмся.

### Q4. Модули без UI — `ui_config = None`

**Решение:** формально поддерживаем. Семантика:

- `ui_config is None` означает «модуль участвует в pipeline, но не
  имеет UI-проекции». Шелл такие модули не рендерит, `SettingsDrawer`
  для них недоступен, в блоке 3 они выполняются молча — пользователь
  видит их только в `Журнал`.
- Использование: post-MVP preprocessing-хуки (нормализация громкости,
  удаление тишины перед ASR), telemetry collector'ы, health-check'и.
- Оркестратор (`core/pipeline.py`) обрабатывает модули с `ui_config
  is None` так же, как и видимые — разницы в pipeline API нет.
- Для MVP ни один реальный модуль не использует этот режим, но
  поле оставляем в контракте, чтобы не менять сигнатуру
  `UIConfig` в post-MVP.

Флаг `visible: bool = True` у **видимого** UIConfig нужен отдельно
от `None` — для кейса «модуль хочет иметь настройки в drawer'е, но
не показывать карточку на главном экране». Пример: глобальный
model-manager, настраиваемый из меню, не являющийся pipeline-шагом.
В MVP тоже не используется, но семантика зарезервирована.

---

## Migration impact on existing modules

`sources/speech/gigaam.py` — единственное изменение:

```python
# в теле класса GigaAMSource, рядом с имеющимися атрибутами
from core.ui_contract import UIConfig  # импорт в верху файла

class GigaAMSource(Source):
    ui_config = UIConfig(
        template="audio_source",
        params={
            "show_hotwords": True,
            "precision_options": ("fp32", "int8"),
            "show_language_hint": False,
            "engine_label": "GigaAM-v3 RNNT",
            "engine_subtitle": "русский",
        },
    )
    # ...остальной код не меняется
```

Никаких импортов `PySide6`, никаких виджет-классов в модуле. Весь
визуал — в `ui/templates/audio_source_template.py`, читающем
`params`.

Второй backend (`sources/speech/whisper.py`, если/когда появится)
использует **тот же** `template="audio_source"` с другими `params`
— см. `docs/design/flowstep-prompts/screen-3-settings-audio-whisper.md`
как доказательство, что один шаблон с разными params даёт визуально
разные, но консистентные панели.

---

## Consequences

### Положительные

- Zero UI duplication между backend'ами одного типа.
- `sources/` / `mergers/` / `renderers/` чистые от GUI-импортов →
  миграция tkinter → PySide6 (ADR-017) не трогает эти слои вообще.
- Тестируемость: модуль тестируется без UI, шаблон тестируется с
  fake-модулем.
- Контракт `SettingsPanelProtocol` унифицирует поведение drawer'а
  для всех модулей.

### Отрицательные

- Лишний уровень косвенности при навигации по коду: «где UI
  GigaAM?» → `ui_config.template = "audio_source"` →
  `ui/templates/audio_source_template.py`. Смягчается документацией
  (этот ADR) и тем, что все шаблоны лежат в одной папке.
- Шаблоны ригидны: если будущий модуль захочет принципиально
  другой UI, он либо расширяет `params` существующего шаблона, либо
  создаёт новый шаблон. Политика — **новый шаблон только при
  существенных различиях; вариации делаются через params**.
- Валидация `params` сейчас runtime-only — шаблон падает при
  отсутствии ожидаемого ключа. В MVP это приемлемо; при росте
  числа шаблонов подумаем о TypedDict/pydantic.

### Нейтральные

- `core/ui_registry.py` — единственный контролируемый «upward»
  импорт (`core → ui`). Явно документирован как исключение.
- Документ `docs/architecture/module-ui-template-di.md`
  переводится в статус «tech notes / implementation details» —
  канонический источник решений теперь этот ADR. Старые open
  questions в том файле считаются снятыми этим ADR.
