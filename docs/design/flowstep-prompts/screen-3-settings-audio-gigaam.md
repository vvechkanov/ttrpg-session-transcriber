# Figma Make Prompt — Settings Drawer · Аудио (GigaAM-v3)

**Цель:** добавить в существующий Figma Make проект v1 (Session Detail)
контент боковой панели настроек для модуля "Аудио · GigaAM-v3".

**Как использовать:** открой в Figma Make тот же проект, что генерил
Screen 3 Session Detail (https://www.figma.com/make/mgU2WJkHx1b3PxIj97PH5F/…),
НЕ начинай новый чат. Вставь всё между `---BEGIN---` и `---END---` как
следующее сообщение — Make подхватит существующие токены (`theme.css`),
`SidePanel.tsx` и стиль карточек.

После первой итерации уточняй короткими репликами:
- "Secondary badge on a speaker row should be subtler"
- "Hotwords textarea needs more vertical space"
- "The new-speakers banner should use accent-tinted background, not red"

---BEGIN---

# Context (read this first)

This is a continuation of the same Session Transcriber project we already
built the Session Detail screen for. Keep using the exact same design
tokens from `src/styles/theme.css`:

- Canvas `--background: #FAF8F5` (warm off-white)
- Cards `--card: #FFFFFF`
- Text `--foreground: #2D2520`, muted `--muted-foreground: #6B625A`
- Accent `--primary/accent: #D4843B` (burnt ochre)
- Success `--success: #4A7C59`
- Destructive `--destructive: #C74242`
- Borders `--border: rgba(107, 98, 90, 0.15)`
- Radius `--radius: 0.625rem` (10 px)
- Font: same sans-serif as Session Detail screen
- Shadows: same warm soft shadows as Session Detail cards

Do NOT introduce new colors, new fonts, new radii, new shadows. Reuse
`Card`, `Button`, `Badge`, `Tooltip`, `Input`, `Textarea`, `Switch`,
`Slider`, `RadioGroup` from the existing `src/app/components/ui/` shadcn
set. Reuse `SidePanel.tsx` as the drawer host.

# What I need

Generate the **content** that goes inside the SidePanel drawer when the
user clicks `[Настроить]` on the "Аудио" source card in Block 1 of Session
Detail. This is the settings panel for the GigaAM-v3 audio source module.

The drawer host (SidePanel.tsx) already exists and handles:
- 80% width overlay, slides in from the right (animate-slide-in)
- Scrim on the left 20% (rgba(0,0,0,0.25)), click-to-close
- Sticky header with title + close button
- Sticky footer with [Отмена] / [Сохранить] buttons
- Esc to close, confirm on unsaved changes

You are generating ONLY the scrollable middle content of this drawer.
Do NOT redraw the drawer shell, the header, or the footer — those already
exist in SidePanel.tsx. Show them in the mockup for context, but the NEW
code you write is a component `AudioGigaamSettingsPanel.tsx` that renders
the form body.

# Drawer header (for context only — already exists)

- Icon: waveform (Lucide `AudioWaveform`)
- Title: **"Настройки · Аудио"**
- Subtitle (muted): **"GigaAM-v3 RNNT · русский"**
- Close button (Lucide `X`) on the right

# Drawer footer (for context only — already exists)

- Left: dirty indicator — small dot + text "Есть несохранённые изменения"
  in accent color, appears when any field changes
- Right: `[Отмена]` ghost button + `[Сохранить]` primary button

# The content (this is what I need)

All user-visible text in **Russian**. No emojis in final render — use
Lucide icons. Technical jargon (RNNT, VAD, compute type) hidden behind
small `[?]` help icons (`HelpTooltip` component from v1).

Layout: vertical stack of sections separated by thin dividers
(`border-border`). Generous 24 px gaps between sections. Section title
uses h3 style, uppercase tracking, muted color.

## Section 1 · New speakers banner (CONDITIONAL)

Visible only when new speakers are detected in the loaded CraigZip.

- Full-width card, accent-tinted background (`#D4843B` at ~8% opacity)
- Left: `UserPlus` icon in accent color
- Middle: bold line "Найдено 2 новых участника" + muted line "Назначьте
  им роли в таблице ниже, прежде чем запускать обработку"
- Right: small ghost link "перейти →" that scrolls to the speakers table

## Section 2 · Входные файлы (Input files)

- Section title: "ВХОДНЫЕ ФАЙЛЫ"
- Subtitle muted: "Файлы из CraigZip, распакованные автоматически"
- Read-only list of 6 rows, each row:
  - Small audio file icon (Lucide `FileAudio`)
  - Filename in monospace: `1-Andrey.flac`
  - Muted small text on the right: duration + size, e.g. `3:47:12 · 142 MB`
- Below the list: subtle ghost link "Заменить CraigZip →" aligned right
- Note: CraigZip upload itself happens on the main source card in Block 1,
  not here. This section is read-only view + re-upload shortcut.

## Section 3 · Участники и роли (Speakers & roles)

The most important section. This is where speaker_map editing lives.

- Section title: "УЧАСТНИКИ И РОЛИ"
- Subtitle muted: "Какая дорожка чей голос. Роль «Слушатель» исключает
  дорожку из обработки"
- Table with columns (fixed width):
  1. Файл (filename, monospace, muted)
  2. Игрок (text input, placeholder "имя игрока")
  3. Роль (segmented control / select: `GM` / `Игрок` / `Слушатель`)
  4. Персонаж (text input, placeholder "имя персонажа")
- 6 rows, one per track
- First 2 rows are pre-filled:
  - `1-Andrey.flac` · Andrey · GM · Гендальф
  - `2-Boris.flac` · Boris · Игрок · Арагорн
- Last 4 rows need filling (this is the "new speakers" state):
  - `3-Carol.flac` — row highlighted with accent-tinted left border (2 px)
    and a tiny accent dot next to the file name
  - `4-Dmitry.flac` — same highlight
  - `5-Eve.flac` — same highlight
  - `6-Frank.flac` — same highlight
- Empty-state placeholders in the player/character cells should be muted.
- Role segmented control default is "Игрок".
- Small ghost button below the table: `[+ добавить участника вручную]`
  for edge cases where a track is missing from CraigZip.

## Section 4 · Движок (Engine)

- Section title: "ДВИЖОК"
- Three rows:
  1. **Backend** (read-only): label "Backend" + value "GigaAM-v3 RNNT" in
     a locked-looking pill; next to it small `[?]` tooltip explaining that
     GigaAM is a Russian-optimized ASR engine
  2. **Язык** (read-only): label "Язык" + value "Русский" in the same
     locked-pill style
  3. **Точность вычислений** (compute precision) — label + segmented
     control with two options:
     - `fp32` (subtitle: "максимальное качество, медленнее")
     - `int8` (subtitle: "быстрее, немного менее точно")
     - `[?]` tooltip on the label: "Как числа хранятся в памяти модели.
       fp32 — эталон, int8 — оптимизация"

## Section 5 · Горячие слова (Hotwords)

- Section title: "ГОРЯЧИЕ СЛОВА"
- Subtitle: "Имена персонажей, локаций, заклинаний — по одному на строку.
  Помогает распознавать редкие слова"
- Large textarea (min 8 rows visible), monospace font
- Pre-filled example:
  ```
  Гендальф
  Арагорн
  Лютиэн
  Галадриэль
  Боромир
  Мория
  Палантир
  ```
- Small muted helper text below: "7 слов"

## Section 6 · Продвинутые (Advanced) — collapsed accordion

- Title row with chevron icon on the right: "ПРОДВИНУТЫЕ" + muted text
  "Тонкая настройка VAD и сегментации"
- Closed by default. When opened, reveals:
  - Label "Чувствительность речевой активности" + `[?]` tooltip
    ("VAD — определение, где речь, а где тишина. Выше значение = строже")
    + slider 0.30 — 0.70, value shown next to slider (default 0.50)
  - Label "Минимальная пауза (мс)" + tooltip + slider 100 — 2000 (default 500)
  - Label "Макс. длина сегмента (сек)" + slider 5 — 30 (default 15)
  - Warning strip at the bottom (muted background, `AlertTriangle` icon):
    "Меняйте только если знаете, что делаете. По умолчанию всё работает."

# States to generate (three artboards side by side)

1. **Default (clean, no new speakers)** — all 6 rows in speakers table are
   pre-filled, no banner, footer dirty indicator hidden, `[Сохранить]`
   button subtly disabled. Advanced accordion closed.

2. **New speakers detected** — the state described above: Section 1 banner
   visible with accent-tinted card, last 4 rows in speakers table
   highlighted, footer dirty indicator hidden (nothing changed YET, just
   flagged for user attention), `[Сохранить]` still disabled until user
   fills in the roles.

3. **Dirty (user typed into hotwords + changed a role)** — no banner,
   footer shows bright dirty indicator "Есть несохранённые изменения" in
   accent, `[Сохранить]` primary button active. One row in the speakers
   table has a subtle "edited" marker (small dot to the left of the
   filename).

# Do NOT

- Do not redesign SidePanel.tsx — only produce the inner content component
- Do not introduce new colors beyond the existing theme
- Do not use pure white (#FFFFFF) except for cards, which are already white
- Do not show CraigZip file upload dropzone here — CraigZip is dropped on
  the main source card, not inside settings
- Do not add save/cancel buttons inside the content — they live in the
  sticky footer of SidePanel
- Do not add tabs — this is a single scrollable form
- Do not add serif fonts, fantasy elements, or Material Design defaults

---END---

## Notes for the humans

- First iteration will probably put the sections in wrong order or use too
  much whitespace. Push back with "Compress Section 2 (files), give more
  room to Section 3 (speakers)".
- If the speakers table looks too much like an Excel grid, push back with
  "Speakers table should feel like a form, not a spreadsheet. No grid
  lines between cells, only row separators".
- If the banner in state 2 is too shouty, push back with "Banner should
  be informational, not alarming. Background at 6% accent opacity, no red".
- The prompt deliberately uses the SAME color tokens as v1 so Figma Make
  can continue without re-picking the palette. Do not let it regenerate
  theme.css.
