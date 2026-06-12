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

### 1.2 Ruff + автоматический контроль границ слоёв (F-B5)
- [ ] Конфиг ruff в `pyproject.toml` (стартово: E/F/I + `flake8-tidy-imports` banned-api для межслойных импортов)
- [ ] Альтернатива/дополнение: `import-linter` с контрактами из ARCHITECTURE.md §3
- [ ] Job `lint` в ci.yml
- [ ] Прогнать, починить найденное (ожидается мелочь)

### 1.3 Починка нарушения dependency rule (F-C1)
- [ ] `core/merge_render.py`: `merge_and_render(timeline, *, merger="script", renderer="plain-text", merge_gap_sec=...) -> bytes` (+ опционально стадийный колбэк)
- [ ] `ui/engines/merger_worker.py` импортирует только core
- [ ] Тест: grep-защита (ruff из 1.2) + юнит на фасад

### 1.4 Судьба `core/cache.py` (F-C2) — требуется решение, рекомендация: реализовать
- [ ] ADR-019: кэш ASR-результатов. Вариант А (рекомендуемый): реализовать
      `DiskCachedSource._load/_save` (json, ключ = hash(config) + mtimes аудио),
      подключить в `pipeline.run` и `PipelineController`. Вариант Б: удалить стаб,
      зафиксировать «кэшем являются canonical JSON в `transcripts/`» + реализовать их чтение
- [ ] Тесты на инвалидацию (смена конфига; смена mtime; удаление `_cache/`)
- [ ] `DiskCachedMerger` НЕ реализовывать до LLM-мержера (#6 этап 6.3)

### 1.5 Единый реестр ASR-бэкендов (F-C3)
- [ ] Дескриптор бэкенда (id, Source-класс, опции, installer-info) в одном модуле
      (`core/backends.py` или расширение `backend_installers.py`)
- [ ] `core/asr.py:make_source` — по реестру вместо if/elif (`asr.py:98-131`)
- [ ] `core/pipeline.py:_speech_kwargs` — производная от дескриптора (убрать ручную синхронизацию)
- [ ] `ui/models/model_registry.py` читает тот же реестр
- [ ] Критерий приёмки: добавление бэкенда = 1 новый файл source + 1 запись в реестре

### 1.6 Актуализация ARCHITECTURE.md (F-A3)
- [ ] Секция «UI-подслои»: ui/models, ui/engines (QThread-workers), ui/qml; потоки и сигналы
- [ ] Секция «Launcher vs Runtime»: два exe, tkinter-бутстрап ≈12 МБ, ленивый ML-стек в `%APPDATA%`
- [ ] Обновить pipeline flow (7 стадий, включая `chunk`) и список core-модулей
- [ ] ADR-018: выбор QML (vs Qt Widgets) — постфактум зафиксировать
- [ ] Перенести `Timeline`-диаграммы/контракты в соответствие коду (ничего менять не надо — только описать)

### 1.7 Тестовые пробелы (F-D1, F-D2)
- [ ] `tests/launcher/test_install_logic.py`: download_ffmpeg / download_runtime_zip с мокнутым urllib (happy path + сеть упала + битый zip)
- [ ] `tests/launcher/test_bootstrap.py`: sentinel-логика (нет / есть+версия совпала / stale)
- [ ] `tests/test_ui_cli.py`: argparse → PipelineParams маппинг, exit codes
- [ ] CONTRIBUTING: когда обязателен локальный tier-2 e2e прогон (перед релизом; при правках sources/mergers) (F-D3)

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
| **F-C5** Generic InstallFlow (дедуп `_fw_*`/`_gigaam_*`) | Добавление 3-го устанавливаемого бэкенда |
| **F-C6** Перенос `timeline_window.py` из core | Реальная боль / появление второго UI |
| **F-C9** QML i18n (`qsTr()`, ~106 строк) | Решение об англоязычной аудитории; иначе зафиксировать ru-only в README |
| Разморозка инсталлера (#1) | Явное решение владельца; перед ней — пересборка + smoke |
| `DiskCachedMerger` | Этап 6.3 (LLM-мержер) |
| Parakeet/Canary/Voxtral бэкенды | После F-C3 (единый реестр) |
| entry_points plugin discovery | Триггеры из ADR-11 (первый внешний PR / 6+ бэкендов) |
| Release automation, code signing, docs site, auto-update | После v0.2.0 |

## Анти-задачи (решено НЕ делать — см. ревью §6)

- Новый big-bang рефакторинг; `src/` layout / PyPI (ADR-10);
  самописная plugin-система (ADR-11); переписывание launcher на Qt;
  новые ASR-бэкенды до закрытия F-C3.

---

## Открытые вопросы (нужны решения владельца)

- [ ] F-C2: кэш ASR — реализовать DiskCachedSource (вариант А) или удалить стаб (вариант Б)? Рекомендация ревью: А
- [ ] F-C9: целимся ли в англоязычную аудиторию (определяет судьбу i18n)?
- [ ] `scripts/install_whisperx_windows.ps1` — удалить или оставить как legacy-fallback?
- [ ] Судьба WhisperX-бэкенда: он subprocess-legacy; поддерживать или объявить deprecated?
