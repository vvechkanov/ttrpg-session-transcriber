# TTRPG Session Transcriber

[English](README.md) | **Русский**

> Единственный open-source десктопный инструмент, который вплетает **чат-лог Foundry VTT** в **по-говорящий транскрипт аудио из Discord** — локально, бесплатно, на вашем железе.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)
[![Status: pre-release](https://img.shields.io/badge/status-pre--release-orange.svg)](TASKS.md)

Превращает записи **D&D / Pathfinder 2e** сессий из Discord в чистые транскрипты с атрибуцией по говорящим — готовые к LLM-постобработке для генерации отчётов. Сделано для игрока, который не хочет учить Docker, Python или PowerShell — скачал один `.exe`, кинул туда папку с Craig, получил транскрипт.

> **Статус:** v0.1.0 в активной разработке. Pre-release сборки доступны в [Releases](../../releases). Дорожная карта в [TASKS.md](TASKS.md).

---

## Зачем это нужно

Если вы когда-то пробовали транскрибировать сессию D&D, вы упирались в одну из этих стен:

- **Облачные сервисы** (Otter, Sonix, Kazkar, Archivist) — платные, ваше аудио уходит из дома, нет интеграции с Foundry VTT
- **Универсальные обёртки над Whisper** (Buzz, MacWhisper) — однотрековые, не понимают кто из игроков кастует Fireball
- **Open-source пайплайны** (TASMAS, Scribble) — только Docker, заточены под английский, командная строка, не для нетехнических игроков
- **Акустическая диаризация** (WhisperX, pyannote) — ломается на пересекающихся голосах, NPC-озвучках и смехе

Этот проект решает всё это для конкретного случая: **TTRPG-группа пишет сессии через Craig в Discord**.

## Чем мы отличаемся

### 🎲 Синхронизация с чат-логом Foundry VTT
Броски кубов, шёпоты и OOC-сообщения из чата Foundry VTT вплетаются в аудио-транскрипт в нужные моменты на таймлайне сессии. **Никто из open-source конкурентов этого не делает.**

### 🗣️ Первоклассный русский через GigaAM-v3
Открытая русская ASR-модель Сбера (под MIT) поставляется как first-class бэкенд с **контекстным байасингом** под имена PF2e. Узнаёт «Ачакек» и «Маэри» без ручного дообучения.

### 📦 Установка одним `.exe` для нетехнических игроков
Никакого Docker, никакой установки Python, никакого PowerShell, никаких токенов Hugging Face. Single-EXE инсталлятор сам ставит Python, PyTorch, выбранный ASR-бэкенд и ffmpeg.

### 🎯 Идеальная атрибуция говорящих за счёт мультитрека Craig
Вместо того чтобы драться с акустической диаризацией на пересекающихся возбуждённых голосах, мы используем то, что Craig пишет каждого игрока на отдельный трек. Каждое слово помечено корректно по построению — потому что каждый игрок на своём аудиопотоке. Никакого pyannote, никакой EULA Hugging Face, никаких догадок.

### 🔄 Code-switching русский ↔ английский
Сделано для столов, где говорят «каст Fireball на DC 15» — модель не ломается. Дефолтная модель `bzikst/faster-whisper-large-v3-ru-podlodka` нативно тянет оба языка.

### 🔌 Подключаемые ASR-бэкенды
Выбирайте движок под свои сессии:

| Бэкенд | Лучше всего для | Лицензия |
|---|---|---|
| `faster-whisper` (по умолчанию) | Смешанные русско-английские сессии, любые языки | MIT |
| `sherpa-onnx` + GigaAM-v3 | Чисто русские сессии, лучшее качество для русского | MIT |
| `whisperx` (legacy) | Существующие сетапы, обратная совместимость | BSD-2 |

---

## Быстрый старт

> **Pre-release:** single-EXE инсталлятор в активной разработке. Пока используйте dev-сетап ниже.

### Сетап для разработчика (работает уже сейчас)

```bash
git clone https://github.com/vvechkanov/ttrpg-session-transcriber.git
cd ttrpg-session-transcriber
python -m venv venv
venv\Scripts\activate                  # Windows
# source venv/bin/activate              # Linux/macOS
pip install -e .
python scripts/wisper_launcher.py
```

В GUI:

1. Выберите папку сессии (папка с `.flac` треками от Craig)
2. Опционально киньте `speaker_map.json` чтобы пометить треки именами игроков
3. Опционально выберите чат-лог Foundry VTT для вплетения в таймлайн
4. Нажмите **Run**

Результат появится в той же папке:

- `merged.txt` — полный транскрипт с метками говорящих и таймстемпами
- `chunks/` — текстовые чанки готовые для LLM-постобработки

### Установка одним `.exe` (в v0.1.0)

1. Скачайте свежий `.exe` со страницы [Releases](../../releases)
2. Запустите. Инсталлятор сам скачает всё нужное.
3. Киньте папку Craig. Нажмите **Transcribe**.

---

## Как это работает

```
Мультитрек Craig (.flac на каждого игрока)
                +
Чат-лог Foundry VTT (опционально)
                ↓
        ┌───────────────┐
        │  ASR backend  │ ← faster-whisper / sherpa-onnx / whisperx
        └───────────────┘
                ↓
   per-track JSON (канонический schema)
                ↓
        ┌───────────────┐
        │ merge timeline │ ← merge_whisperx.py
        └───────────────┘
                ↓
        merged.txt + chunks/
                ↓
        LLM-постобработка (Claude / GPT / локальная)
                ↓
        Отчёт по сессии, заметки персонажей, журнал кампании
```

---

## Сравнение с альтернативами

| | This project | TASMAS | Scribble | Kazkar.ai | Archivist | Buzz |
|---|---|---|---|---|---|---|
| **Локально / бесплатно** | ✅ | ✅ | ✅ | ❌ облако | ❌ облако | ✅ |
| **Установка одним .exe** | ✅ | ❌ Docker | ❌ Docker | n/a | n/a | ✅ |
| **FVTT chat → audio merge** | ✅ | ❌ | ❌ | ❌ | ⚠️ только entity sync | ❌ |
| **Русская ASR (GigaAM)** | ✅ | ❌ | ❌ | ⚠️ generic | ❌ | ❌ |
| **Мультитрек Craig на вход** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Подключаемые ASR-бэкенды** | ✅ | ❌ | ⚠️ только FW | ❌ | ❌ | ❌ |
| **Цена** | бесплатно | бесплатно | бесплатно | $$ | $6/мес | бесплатно |

---

## FAQ

**Почему мультитрек Craig вместо акустической диаризации?**
Акустическая диаризация (pyannote, WhisperX `--diarize`) ломается на TTRPG-аудио: пересекающиеся возбуждённые голоса, игроки делают NPC-голоса, драматические крики, неконтролируемый смех. Craig пишет каждого игрока на отдельный трек, поэтому атрибуция идеальна по построению — никакая модель не может перепутать кто что сказал, когда каждый говорящий на своём потоке.

**Почему GigaAM для русского?**
GigaAM-v3 — открытая русская ASR-модель Сбера под MIT. На русском аудио стабильно обгоняет Whisper. Также поддерживает **контекстный байасинг** — можно дать ей список имён NPC, и она будет узнавать их корректно вместо того чтобы изобретать креативные варианты. Файл с hotwords содержит имена PF2e — можно подставить свой.

**Моё аудио куда-то загружается?**
Нет. Всё работает на вашей машине. Никакой телеметрии, никаких API-вызовов, никаких облачных сервисов. Проект буквально не может видеть ваше аудио — нет никакого сервера.

**Работает ли без GPU?**
Да. Все бэкенды поддерживают CPU-режим. С faster-whisper int8-квантизацией 3-часовая сессия занимает примерно 30-60 минут на современном CPU. С NVIDIA GPU — 5-10 минут.

**Что насчёт D&D 5e или других систем?**
Сам пайплайн транскрипции универсален. Мы тестируем на Pathfinder 2e потому что мейнтейнер играет в неё. В файле hotwords лежат имена PF2e — можно заменить `config/pathfinder_ru_hotwords.txt` своим списком терминов.

**Можно ли использовать для не-TTRPG аудио?**
Технически да. Любая мультитрековая запись из Discord (подкасты, митинги, интервью) подойдёт. Интеграция с Foundry VTT и hotwords PF2e тут не пригодятся, но сам пайплайн транскрипции — общего назначения.

**В чём отличие от Scribble / TASMAS?**
Scribble и TASMAS — отличные open-source проекты, но оба требуют Docker, заточены под англоязычные группы и не вплетают чат Foundry VTT в аудио-таймлайн. Мы сделаны для игрока, который хочет дабл-кликнуть `.exe`, а не запускать `docker-compose up`.

---

## Структура проекта

```
ttrpg-session-transcriber/
├── launcher/                ← single-EXE инсталлятор (PyInstaller)
│   ├── bootstrap.py
│   ├── installer_ui.py
│   └── install_logic.py
├── scripts/
│   ├── asr_backends/        ← подключаемые ASR-бэкенды (в разработке)
│   ├── wisper_launcher.py   ← GUI-лаунчер пайплайна
│   ├── merge_whisperx.py    ← per-track JSON → единый merged.txt
│   ├── parse_fvtt_chat.py   ← чат-лог Foundry VTT → сегменты
│   └── chunk_text.py        ← merged.txt → чанки для LLM
├── prompts/                 ← LLM-промпты для постобработки
├── config/                  ← hotwords, дефолты
├── tests/                   ← pytest suite (в разработке)
└── docs/                    ← дополнительная документация
```

---

## Дорожная карта

Подробный чек-лист в [TASKS.md](TASKS.md). Верхнеуровнево:

- **v0.1.0** (в работе) — бэкенд faster-whisper, single-EXE инсталлятор с выбором бэкенда, синхронизация чата FVTT, MIT-лицензия, гигиена open-source проекта
- **v0.2.0** — бэкенд GigaAM-v3 RNNT с контекстным байасингом, smoke-тесты на реальных Craig-записях, скелет для качества кода
- **v0.3.0** — Полированный GUI (PySide6 или улучшенный tkinter), выбор бэкенда в инсталляторе
- **v1.0.0** — Кросс-платформенные сборки (Linux/macOS), полная UX-интеграция FVTT, production-ready

---

## Контрибьютинг

Pull request-ы приветствуются. Сетап разработки и гайдлайны в [CONTRIBUTING.md](CONTRIBUTING.md).

Проект следует [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).

---

## Лицензия

MIT — см. [LICENSE](LICENSE).

---

## Благодарности

Построено поверх отличных open-source работ:

- **[Craig](https://craig.chat)** — мультитрековый Discord voice recorder от Yahweasel
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — основной ASR-бэкенд
- **[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** — ONNX runtime для GigaAM
- **[GigaAM](https://github.com/salute-developers/GigaAM)** — открытая русская ASR-модель от Сбера
- **[WhisperX](https://github.com/m-bain/whisperX)** — оригинальный пайплайн транскрипции
- **[Foundry VTT](https://foundryvtt.com/)** — интеграция с виртуальным тейблтопом
- **[Silero VAD](https://github.com/snakers4/silero-vad)** — voice activity detection
- **[bond005/whisper-podlodka-turbo](https://huggingface.co/bond005/whisper-podlodka-turbo)** — русский файн-тюн Whisper

Спасибо TTRPG-сообществу за тестирование и фидбэк.
