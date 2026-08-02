
# Context

Same Session Transcriber project. Same theme tokens. Same `SidePanel.tsx`
drawer host. Same typography. I already have a version of this panel for
the **GigaAM-v3** backend (see the previous message). Now I need a
**second version** of the same settings panel for a **different audio
backend: faster-whisper**. The layout and sectioning should be almost
identical so that the shared template pattern is visible, BUT the engine
configuration section is different because Whisper has different knobs.

This demonstrates that one `audio_source_template` with different
`params` produces both panels — no duplicated UI code.

# What stays the same (do not redraw from scratch, reuse)

- Canvas, cards, accent, text colors — same theme tokens as before
- Header: same `AudioWaveform` icon, close button, sticky layout
- Footer: same dirty indicator + Отмена / Сохранить buttons
- **Section 1** New speakers banner — same component
- **Section 2** Входные файлы — identical, same 6 .flac rows from CraigZip
- **Section 3** Участники и роли — identical speakers table
- **Section 5** Горячие слова — REPLACED by "Стартовая подсказка" (see below)
- **Section 6** Продвинутые — same VAD sliders, PLUS two extra Whisper-
  specific fields

# What changes — the Engine section

## Header subtitle (replaces "GigaAM-v3 RNNT · русский")

- **"faster-whisper · large-v3 · многоязычная"**

## Section 4 · Движок (replaces the GigaAM engine section entirely)

- Section title: "ДВИЖОК"
- Rows:
  1. **Backend** (read-only): value "faster-whisper (CTranslate2)" in
     locked-pill + `[?]` tooltip "Оптимизированная реализация OpenAI
     Whisper на движке CTranslate2. В 4× быстрее оригинала."
  2. **Размер модели** (model size) — segmented control with 5 options:
     `tiny` / `base` / `small` / `medium` / `large-v3` (default selected:
     `large-v3`). Below the selector, muted helper text that changes
     with selection. For `large-v3`: "3 GB VRAM, лучшее качество,
     медленнее". For `tiny`: "75 MB, быстро, только общая суть".
  3. **Язык** (language) — dropdown select. Options: "Автоопределение",
     "Русский", "English", "Deutsch", "Français", "Español", "Italiano",
     "Polski", "Українська". Default: "Русский". `[?]` tooltip: "Если
     выбрать один язык — модель работает точнее и быстрее. Автоопределение
     — если в записи несколько языков."
  4. **Точность вычислений** (compute precision) — segmented control with
     THREE options (not two like GigaAM):
     - `float16` ("баланс качества и скорости, рекомендуется для GPU")
     - `int8_float16` ("меньше памяти, небольшая потеря качества")
     - `int8` ("минимум памяти, CPU-friendly")
     - Default selected: `float16`
     - `[?]` tooltip: "Как числа хранятся в памяти модели. float16 —
       хороший баланс. int8 — если не хватает памяти."
  5. **Beam size** — label + slider 1–10 (default 5) + value shown next
     to slider + `[?]` tooltip: "Сколько альтернативных расшифровок
     модель рассматривает параллельно. Больше = точнее, но медленнее."

Visual note: the engine section is noticeably longer than GigaAM's (5 rows
vs 3). This is expected — the layout should accommodate it without feeling
cramped.

## Section 5 · Стартовая подсказка (replaces Горячие слова)

Whisper doesn't support hotwords biasing the same way GigaAM does.
Instead, it has `initial_prompt` — a seed string that biases the
transcript style. Label it accordingly:

- Section title: "СТАРТОВАЯ ПОДСКАЗКА"
- Subtitle: "Фраза в начале, которая настраивает модель на стиль записи.
  Например, имена персонажей или типичные термины сессии."
- `[?]` tooltip on the title: "Whisper использует эту подсказку как
  «затравку» контекста. В отличие от горячих слов, это не гарантия
  распознавания конкретных слов, а намёк на стиль."
- Single textarea, ~4 rows tall (smaller than GigaAM hotwords), regular
  sans-serif (not monospace — it's a sentence, not a list)
- Pre-filled example:
  ```
  Партия приключенцев в Средиземье. Персонажи: Гендальф (маг),
  Арагорн (следопыт), Лютиэн (жрица), Галадриэль (бард),
  Боромир (воин). Бросок d20, спасбросок, инициатива.
  ```
- Muted character counter below: "178 / 1000 символов"

## Section 6 · Продвинутые (accordion)

Same as GigaAM + two extra Whisper-specific fields at the end:

- Чувствительность речевой активности (VAD) — slider 0.30–0.70
- Минимальная пауза (мс) — slider 100–2000
- Макс. длина сегмента (сек) — slider 5–30
- **NEW:** `no_speech_threshold` — slider 0.3–0.9 (default 0.6) +
  `[?]` "Порог уверенности Whisper в том, что в сегменте нет речи.
  Выше — строже."
- **NEW:** `temperature` (fallback) — slider 0.0–1.0 (default 0.0) +
  `[?]` "Случайность декодирования. 0 = детерминистично. Увеличивайте
  только если Whisper зациклился на повторе слов."
- Same warning strip at the bottom.

# States to generate (three artboards side by side)

1. **Default** — speakers table pre-filled, no banner, footer clean,
   engine section shows defaults (large-v3, Русский, float16, beam 5),
   advanced accordion closed.

2. **New speakers detected + non-default engine** — banner visible,
   last 4 speaker rows highlighted. Engine section shows USER-CHANGED
   values: `small` model selected, language "Автоопределение",
   `int8_float16` precision, beam 3. Footer dirty indicator active.

3. **Advanced accordion open** — default engine values, no banner, but
   Section 6 is expanded showing all 5 sliders. Footer dirty inactive.

# Do NOT

- Do not change the layout of sections 1, 2, 3 — they're identical to
  GigaAM version
- Do not introduce a separate "model download" UI — assume models are
  already downloaded, that's a different screen
- Do not show GPU/CPU switcher — it's auto-detected, not user-facing
- Do not show beam + temperature as advanced only — beam is a primary
  engine param in Whisper, temperature is advanced
- Do not use pure white backgrounds other than cards
