# TTRPG Session Transcriber — Инженерный план работ

**Обновлено:** 2026-06-12 (внешнее архитектурное ревью).
**Основание:** [docs/architecture-review-2026-06.md](docs/architecture-review-2026-06.md) —
там полный разбор находок (нумерация `F-*`), рисков и обоснований.
**Продуктовый бэклог** (фичи #1–#9) живёт в [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md) —
этот файл его не дублирует, только ссылается.

> **Историческая справка.** Предыдущая версия TASKS.md описывала план
> «P2 six-layer refactor → P5 GUI» (март 2026). Этот план **выполнен и
> перевыполнен**: шесть слоёв внедрены, GUI мигрирован сразу на PySide6/QML
> (минуя tkinter-вариант), GigaAM-бэкенд реализован, тестовая инфраструктура
> построена (~440 тестов, CI-матрица). Старый текст доступен в git-истории
> (до коммита этого ревью).

---

## Решения владельца (2026-06-14)

Зафиксированы по итогам ревью. Меняют приоритеты ниже.

**North star:** довести до полноценно работающего продукта «у меня на компе»
для своей группы. Публичный v0.2.0 и инсталлер — следующим заходом, не сейчас.
Ничего не горит — берём паузу на гигиену и фундамент (Фазы 0–1), затем продукт.

| # | Решение |
|---|---|
| Аудитория | Для себя + группа сейчас; публичный релиз позже (A1=б) |
| Англ. локализация | Нужна **в будущем**, не сейчас → i18n отложен, но новые QML-строки сразу через `qsTr()` (B1) |
| Кол-во ASR-бэкендов | Трёх хватит; роста не планируем → единый реестр (F-C3) и дедуп install (F-C5) демотированы (B2) |
| WhisperX | **Удаляем из master** (остаётся в отдельной локальной ветке владельца) (C2) |
| Кэш ASR | **Реализуем** `DiskCachedSource` (C1) |
| LLM-мержер | Локально (Ollama), без облака (C4) |
| Инсталлер #1 | Заморожен до «работает у меня» → тесты launcher (F-D1) демотированы (D1) |
| Двойной UI-стек | Принят как есть (tkinter-бутстрап + QML-runtime) (D2) |
| Внешние PR / каналы | Не сейчас → plugin-инфраструктура остаётся отложенной (B3) |
| Процесс (делегировано ревью) | DoD включает доки; ruff — блокирующий гейт; владелец доков — автор каждого PR (E2/E3/E4) |

Открытый микровопрос: `scripts/install_whisperx_windows.ps1` (C3) — ревью
рекомендует удалить вместе с WhisperX (скрипт ставит именно его). Сделано как
задача 1.8 с пометкой; откати, если нужен fallback.

---

## Правила работы (сохраняются)

- Каждая подзадача = один логический коммит с working сборкой.
- Conventional commits, squash merge запрещён.
- Definition of Done включает документацию: фича не закрыта, пока
  README / CHANGELOG / ARCHITECTURE.md (если затронут) не обновлены.

---

## Фаза 0 — «Перестать врать»: синхронизация документации и квик-вины CI

**Цель:** ни один документ не даёт нерабочих инструкций. ≈1–2 дня, один PR.
**Риск:** нулевой.

### 0.1 Мёртвые ссылки на `wisper_launcher.py` (F-A1)
- [ ] `README.md:70,168` — заменить запуск на `python -m ui`, поправить дерево проекта
- [ ] `README.ru.md:70,168` — то же
- [ ] `CONTRIBUTING.md:30` — то же; убрать/поправить `pip install -e .[dev]` до выполнения 1.1
- [ ] `01_Как_пользоваться.md` — переписать workflow под текущий QML-UI и CLI
- [ ] `00_README.md` — переписать структуру проекта (6 слоёв, launcher, два exe)
- [ ] `scripts/00_README.md` — убрать описание удалённых скриптов, описать живые
      (capture_qml_screens, dump_qml_geometry, gen_baseline_newpipeline, gen_fixtures_noprint, chunk_text, download_gigaam)
- [ ] Пометить `scripts/install_whisperx_windows.ps1` как legacy (или удалить — решить)

### 0.2 CHANGELOG догнать реальность (F-A5)
- [ ] `## [Unreleased]` дополнить: QML UI, GigaAM-v3, multi-Craig (#4),
      speaker_map editor (#5), ASR settings (#2), чанкер (#7), timeline 3a

### 0.3 CI квик-вины (F-B2, F-B3, F-B4)
- [ ] `ci.yml`: явно определить судьбу маркера `gui` — включить в прогон
      осознанно (offscreen работает) и зафиксировать комментарием, либо исключить
- [ ] `ci.yml`: `actions/setup-python` с `cache: pip` в обоих jobs
- [ ] `launcher/build.spec`: убрать фантомные hiddenimports
      (`core.backend_installers`, `sources.speech.*`) или задокументировать, зачем они

### 0.4 Готово в рамках ревью (2026-06-12)
- [x] `TASKS.md` переписан под фактическое состояние (F-A2)
- [x] `02_Статус_и_заметки.md` актуализирован (F-A4)
- [x] `docs/architecture-review-2026-06.md` — полное ревью

---

## Фаза 1 — Фундамент: packaging, границы слоёв, реестры

**Цель:** убрать долг, который дорожает с каждым новым бэкендом/фичей. ≈1 неделя.

### 1.1 `pyproject.toml` (F-B1) — 🔴 приоритет
- [ ] `[project]`: name, version (единый источник — мигрировать из `launcher/version.py`), requires-python
- [ ] `[project.optional-dependencies]`: `dev` (pytest, pytest-qt, pytest-cov, ruff), `qt` (PySide6)
- [ ] CI ставит зависимости через `pip install -e .[dev,qt]` вместо хардкода
- [ ] `requirements-qt.txt` — оставить как тонкую ссылку или удалить
- [ ] Проверить, что `launcher/version.py` и build.spec-ы читают версию из одного места

### 1.2 Ruff + автоматический контроль границ слоёв (F-B5) — гейт блокирующий (E3)
- [ ] Конфиг ruff в `pyproject.toml` (стартово: E/F/I + `flake8-tidy-imports` banned-api для межслойных импортов)
- [ ] Альтернатива/дополнение: `import-linter` с контрактами из ARCHITECTURE.md §3
- [ ] Job `lint` в ci.yml — **блокирующий** (нарушение границ слоёв валит сборку)
- [ ] Прогнать, починить найденное (ожидается мелочь)

### 1.3 Починка нарушения dependency rule (F-C1)
- [ ] `core/merge_render.py`: `merge_and_render(timeline, *, merger="script", renderer="plain-text", merge_gap_sec=...) -> bytes` (+ опционально стадийный колбэк)
- [ ] `ui/engines/merger_worker.py` импортирует только core
- [ ] Тест: grep-защита (ruff из 1.2) + юнит на фасад

### 1.4 Реализовать `core/cache.py` (F-C2) — решено: вариант А (C1)
- [ ] ADR-019: кэш ASR-результатов
- [ ] `DiskCachedSource._load/_save` (json, ключ = hash(config) + mtimes аудио)
- [ ] Подключить в `pipeline.run` и `PipelineController`
- [ ] Тесты на инвалидацию (смена конфига; смена mtime; удаление `_cache/`)
- [ ] `DiskCachedMerger` НЕ реализовывать до LLM-мержера (#6 этап 6.3)

### 1.5 Удалить WhisperX из master (C2) — заменяет старую задачу «единый реестр»
> С удалением WhisperX остаётся 2 стабильных бэкенда без планов роста (B2),
> поэтому единый реестр (F-C3) и дедуп install-флоу (F-C5) **демотированы** в
> Фазу 3 / Отложено — текущий if/elif на 2 ветки приемлем.
- [ ] Удалить `sources/speech/whisperx.py` + регистрацию в `sources/__init__.py`
- [ ] Вычистить `make_source`/`_speech_kwargs`/`model_registry` от whisperx-веток
- [ ] Удалить связанные тесты и упоминания в ARCHITECTURE/README
- [ ] Tier-1 e2e baseline сейчас сгенерён faster-whisper — проверить, что не завязан на whisperx
- [ ] CHANGELOG `### Removed`: WhisperX backend (legacy subprocess wrapper)

### 1.6 Актуализация ARCHITECTURE.md (F-A3)
- [ ] Секция «UI-подслои»: ui/models, ui/engines (QThread-workers), ui/qml; потоки и сигналы
- [ ] Секция «Launcher vs Runtime»: два exe, tkinter-бутстрап ≈12 МБ, ленивый ML-стек в `%APPDATA%`
- [ ] Обновить pipeline flow (7 стадий, включая `chunk`) и список core-модулей
- [ ] ADR-018: выбор QML (vs Qt Widgets) — постфактум зафиксировать
- [ ] Перенести `Timeline`-диаграммы/контракты в соответствие коду (ничего менять не надо — только описать)

### 1.7 Тестовые пробелы (F-D2, F-D3)
> Тесты launcher (F-D1) демотированы в Отложено — инсталлер заморожен до
> «работает у меня» (D1). Вернуть в скоуп при разморозке #1.
- [ ] `tests/test_ui_cli.py`: argparse → PipelineParams маппинг, exit codes
- [ ] CONTRIBUTING: когда обязателен локальный tier-2 e2e прогон (перед релизом; при правках sources/mergers) (F-D3)

### 1.8 Удалить legacy `install_whisperx_windows.ps1` (C3)
> Ревью рекомендует удалить вместе с WhisperX (скрипт ставит именно его).
> Откати задачу, если нужен локальный fallback.
- [ ] Удалить `scripts/install_whisperx_windows.ps1`
- [ ] Убрать упоминания из `requirements-qt.txt` и `scripts/00_README.md`

---

## Фаза 2 — Продукт

Подробные описания — в `FEATURE_REQUESTS.md`. Рекомендованный порядок:

### 2.1 Фича #3, итерация 3b — абсолютная ось времени
- [ ] `CombatSource` (core): парсинг `Бой N.txt` → (started_at, ended_at, encounter, initiative) UTC
- [ ] `SourceListModel.loadFromDir`: реальные startPct/endPct для chat/combat рядов
- [ ] `TimelineRuler.qml`: абсолютные часы (18:00, 19:00…) вместо относительных минут
- [ ] `Timeline.game_log` начинает наполняться (контракт уже готов)
- **Разблокирует #8.**

### 2.2 Фича #6 — LLM-мержер (поэтапно, gate после PoC)
- [ ] **6.1** Селектор мержера в SettingsScreen; `LLMMerger` в `MERGERS` с деградацией до `script` (1–2 дня)
- [ ] **6.2** PoC `scripts/llm_revise_poc.py` (Qwen2.5 7B / Ollama, задача A — коррекция имён). Gate: качество на Сессии 4
- [ ] **6.3** Полная интеграция (QThread worker, Installable для Ollama) — **только после** green 6.2 и желательно после 3.1 (см. Фазу 3: PipelineController к этому моменту лучше разрезать)
- Блокер «ждём #4» снят — #4 закрыт 2026-04-21.

### 2.3 Фича #9 — per-track ASR overrides
- [ ] `AsrOptions.merged_with(override)`
- [ ] Per-row override в `TrackListModel` + bindings в `TrackOverridePopover` (сейчас layout-only)
- [ ] Ключ кэша источников: `(model_id, options_hash)` — заодно закрывает known-limitation фичи #2

### 2.4 Фича #8 — combat-aware renderer (после 2.1)
- [ ] `CombatAwareRenderer` в `renderers/`, потребляет `Timeline.game_log`
- [ ] Dropdown «Рендерер» в SettingsScreen

---

## Фаза 3 — Рефакторинг по случаю (фоном, не отдельным спринтом)

- [ ] **F-C4a** `PipelineController` (661 строка) → выделить `SpeakerMapManager`
      (строки 210–353) и `DoneSummaryBuilder` (544–607). Делать **перед 6.3**
- [ ] **F-C4b** `TrackListModel` (659 строк) → выделить session-loader
      (pure-функция поверх `core.file_matchers`) и payload-builder. Делать при
      следующей крупной правке session.py
- [ ] **F-C7** `core/fvtt_helpers.py` — убрать lazy-import (правило `core → sources` разрешено)
- [ ] **F-C8** `AppPreferences` — фабрика Q_PROPERTY (413 → ~250 строк)
- [ ] BaseWorker mixin для cancel-паттерна (asr/merger/peaks workers)

---

## Отложено осознанно (не делать без триггера)

| Что | Триггер |
|---|---|
| **F-C3** Единый реестр бэкендов | Появление 3-го бэкенда (сейчас планов нет, B2) |
| **F-C5** Generic InstallFlow (дедуп `_fw_*`/`_gigaam_*`) | Появление 3-го устанавливаемого бэкенда |
| **F-C6** Перенос `timeline_window.py` из core | Реальная боль / появление второго UI |
| **F-C9** QML i18n (массовый `qsTr()`, ~106 строк) | Подготовка к англ. аудитории (B1 — «в будущем»). До тех пор: новые строки сразу через `qsTr()`, старые не трогаем |
| **F-D1** Тесты launcher (bootstrap, install_logic) | Разморозка инсталлера #1 |
| Разморозка инсталлера (#1) | После «работает у меня на компе» (D1); перед ней — пересборка + smoke |
| `DiskCachedMerger` | Этап 6.3 (LLM-мержер) |
| Parakeet/Canary/Voxtral бэкенды | Не планируются (B2) |
| entry_points plugin discovery | Триггеры из ADR-11 (первый внешний PR / 6+ бэкендов) — не сейчас (B3) |
| Release automation, code signing, docs site, auto-update | После v0.2.0 (публичный релиз — следующим заходом) |

## Анти-задачи (решено НЕ делать — см. ревью §6)

- Новый big-bang рефакторинг; `src/` layout / PyPI (ADR-10);
  самописная plugin-система (ADR-11); переписывание launcher на Qt;
  новые ASR-бэкенды до закрытия F-C3.

---

## Открытые вопросы

Все вопросы ревью закрыты решениями владельца от 2026-06-14 (см. блок
«Решения владельца» вверху). Новые вопросы фиксировать здесь.

- _(пусто)_
