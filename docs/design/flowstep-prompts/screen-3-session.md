# Flowstep Prompt — Screen 3 (Session Detail)

Copy everything between the `---BEGIN---` and `---END---` markers below into
Flowstep as one prompt. Do not split it into parts unless Flowstep rejects
the length.

After Flowstep generates the first iteration, inspect and iterate with
short refinement messages like:

- "Make the processing block taller, the source cards shorter"
- "The [+ добавить источник] button should be a ghost button, not primary"
- "Remove the icons on the progress bars, keep only the percentage"

Do NOT restart the conversation in Flowstep — iterate within one session,
it holds context.

---BEGIN---

# Product

A Windows desktop app called **Session Transcriber**. It takes multi-track
audio recordings from the Craig Discord bot (one .flac per speaker) made
during a tabletop RPG session (Dungeons & Dragons, Pathfinder, Savage
Worlds), runs Russian speech recognition on each track, merges the results
with the Foundry Virtual Tabletop chat log, and outputs a single cleaned
transcript file the game master can read or feed to an LLM.

# User

A game master. Age 25 to 45. Technically literate, comfortable with files
and folders, but NOT a developer. Does not know what "RNNT", "VAD",
"beam size", "compute type", or "CTranslate2" mean — and should never see
those words in the UI. Processes recordings after the game, in the evening,
at a desk. Sessions are 3–5 hours long. Ran the same campaign with the
same 4–6 players every two weeks for months — the workflow is boringly
repetitive, so every extra click hurts.

# Mental model to convey visually

- **Project** = one tabletop campaign (e.g. "Storm King's Thunder"). Lives
  as a folder on disk.
- **Session** = one game night inside a project. Has its own inputs,
  caches, and output file.
- **Pipeline** = four vertical blocks that process a session, top to
  bottom:
  1. **Sources** — what data we have (audio files, chat log, etc.)
  2. **Merger** — which algorithm combines the parsed data on a timeline
  3. **Processing** — the engine, where work actually happens live
  4. **Output** — the final file

Blocks 1, 2, 4 are configuration areas. Block 3 is the live engine. User
clicks one big button in block 3 and watches.

# Design direction — MANDATORY

Theme: **Light**. Warm off-white canvas, white cards on top.

Mood in one phrase: **"a warm paper laboratory"**. Not gaming, not fantasy,
not corporate SaaS. Think of the atmosphere of a tabletop game master's
personal study after the game — hardcover notebooks, a good desk lamp,
amber-tinted paper, quiet focus. But the tool itself is modern and
precise, not skeuomorphic.

**Reference apps** (match their density, typography, calm):

- Obsidian light theme
- Craft.do
- Linear light theme
- Things 3 (macOS)

**Do NOT reference:**

- Discord
- Notion
- Figma
- Any fantasy RPG character sheet
- Any Material Design default

**Palette:** you pick the exact hex values, but respect these rules:

- Canvas background must be warm off-white (NOT pure white, NOT gray,
  NOT blue-tinted). Think "aged paper" but very subtle — maybe 3–5%
  warmth.
- Cards sit on canvas as slightly brighter / cleaner surfaces with soft
  subtle shadows.
- ONE accent color, warm, reminding of a desk lamp or candlelight —
  amber, honey, terracotta, burnt ochre. No reds, no blues, no greens as
  accent. Pick whichever shade reads "warm and grown-up" to you.
- Status chips: green for done, accent-color for in progress, red only
  for errors.
- Text: warm near-black primary, warm gray secondary. NO cold grays.

**Typography:**

- Sans-serif, modern, good Cyrillic support. Inter is a safe default.
  If you prefer something with more character (Geist, IBM Plex Sans,
  Söhne) go ahead, but NO serifs and NO display/fantasy fonts.
- Headings 18–22 px, body 14–15 px, caption 12 px.
- Monospace only for file paths and log lines.

**Shapes & density:**

- Radius 8 px for buttons and chips, 12 px for cards, 16 px for modals.
- Generous but not wasteful padding. The screen should feel airy without
  being empty.
- Shadows are soft, warm-tinted, never hard.

**Iconography:** Lucide Icons only, outlined, 1.5 stroke width. Sizes
14 / 16 / 20 / 24 px. No emojis in the final UI (emojis appear in this
prompt only as placeholder indicators — replace with proper icons).

**Language:** All user-visible text in **Russian**. Keep technical jargon
behind small "[?]" help icons that expand into tooltips.

# Screen

**Name:** Session Detail — Pipeline View
**Path:** `Storm King's Thunder / Сессия 14 — Битва на мосту`
**Active tab:** `Обработка` (Processing)

## Layout

Top of screen:
- Breadcrumb line: `Storm King's Thunder / Сессия 14 — Битва на мосту`
- Horizontal tab bar with four tabs: `Обработка` (active, underlined with
  accent color), `Транскрипт`, `Журнал`, `Настройки сессии`

Main content area — four stacked blocks vertically, each is a rounded card
sitting on the canvas:

### Block 1 · Источники (Sources)

- Block header: left side `ИСТОЧНИКИ`, right side button
  `[+ добавить источник]` (ghost/secondary style, small plus icon)
- Body: horizontal row of 2 source cards + 1 empty "add" tile at the end

**Source card — Audio (Аудио)**, ~260 × 240 px:
- Top row: small audio waveform icon + title "Аудио"
- Subtitle: "GigaAM-v3 RNNT · русский" (small, secondary color)
- Middle: compact file list with small file icons:
  - `1-Andrey.flac`
  - `2-Boris.flac`
  - `3-Carol.flac`
  - `4-Dmitry.flac`
  - `5-Eve.flac`
  - `6-Frank.flac`
- Bottom row: status chip `готов` (green) on the left, button
  `[Настроить]` (ghost) on the right

**Source card — Foundry chat (Foundry VTT чат)**, same size:
- Icon: chat bubble
- Title: "Foundry VTT чат"
- Middle: one file name `chat-log-2026-04-10.db` + subtitle
  "1423 реплики · 12 участников"
- Bottom row: status chip `готов` (green) + `[Настроить]` ghost button

**Third tile — add-source slot**, same size but dashed border instead of
solid, no background fill:
- Centered large `+` icon
- Text: "Добавить источник"
- Subtext: "Аудио, чат, или другой парсер"

### Block 2 · Мержер (Merger)

Thin block, ~80 px tall. Single row:
- Left: merger icon + title "Мержер: timeline-v1" + small `[?]` help icon
- Subtitle: "Объединение событий по временным меткам"
- Right: button `[Настроить]` ghost

### Block 3 · Обработка (Processing) — THIS IS THE HERO BLOCK

Largest block on the screen, ~420 px tall. This is where the eye lands.

Header row:
- Left: `ОБРАБОТКА` title
- Right: large primary button `[▶ Запустить обработку]`
  (height 48 px, accent color, rounded 10 px, icon on the left)

Body (idle state for this mockup):
- Centered in the block, vertical stack:
  - Muted icon (~48 px, subtle amber)
  - One line of text: "Нажмите «Запустить», чтобы начать"
  - Secondary line: "Прогресс каждого источника появится здесь"

Footer row (inside the block, subtle, at the bottom):
- `☑ использовать кэши` checkbox with `[?]` help icon
- Right side: `[очистить кэш сессии]` ghost button, muted color

### Block 4 · Вывод (Output)

Medium block, ~120 px tall:
- Header: `ВЫВОД` on left, `[Настроить]` ghost on right
- Middle row:
  - Small document icon
  - Main text: "merged.txt"
  - Subtitle: "Формат: единый текст с таймкодами"
- Bottom row (placeholder for result, show as dimmed/empty in idle):
  - Dimmed text: "Файл появится после обработки"

## Spacing

- Outer page padding: 32 px
- Gap between blocks: 20 px
- Gap between source cards inside block 1: 16 px
- Inner block padding: 24 px
- Inner card padding: 20 px

## States to generate

Generate THREE variants of this screen as separate artboards in the same
Flowstep output:

1. **Idle** — as described above. This is the empty-but-ready state before
   the user presses Запустить.
2. **Running — audio in progress.** Same layout, but:
   - Source card "Аудио" has a bright accent-colored border and its
     status chip changes to "● в работе" (accent color)
   - Source card "Foundry VTT чат" and the merger block are **dimmed**
     (~50% opacity, non-interactive look)
   - Block 3 now shows a runtime panel:
     - Title: "🎙 Аудио · GigaAM-v3"
     - Thin divider line
     - Six rows, one per track, each row has: player name, role badge
       (GM / Игрок / Слушатель), progress bar, percentage, ETA
     - Example values:
       - `Andrey  ████████░░░░  67%  · 2 мин   GM · Гендальф`
       - `Boris   ██████████░░  ✓ из кэша      Игрок · Арагорн`
       - `Carol   ░░░░░░░░░░░░  в очереди       Игрок · Лютиэн`
       - `Dmitry  исключён (роль «слушатель»)`
       - `Eve     ░░░░░░░░░░░░  в очереди       Игрок · Галадриэль`
       - `Frank   ░░░░░░░░░░░░  в очереди       Игрок · Боромир`
     - Bottom summary line: "Текущий этап: VAD + ASR дорожки Andrey.
       Кэш: 1 из 5 дорожек."
   - The big button changes from `[▶ Запустить обработку]` to an overall
     progress indicator with an ETA: `◐ 42% · ~11 минут осталось`
   - Block 4 "Вывод" is dimmed
3. **Done** — all complete:
   - All source cards and the merger block have small `✓` status chips
     (green)
   - Block 3 shows a SUMMARY, not a runtime panel:
     - Big header: "✓ Готово за 14 минут 23 секунды"
     - Button on the right: `[▶ Перезапустить]`
     - Four summary lines with small icons:
       - `• Аудио · GigaAM-v3: 5 дорожек, 3ч 47м, 12 340 событий`
       - `• Foundry VTT чат: 1 423 события`
       - `• Мержер timeline-v1: 13 763 события в итоговом таймлайне`
       - `• Рендерер: merged.txt (84 KB)`
   - Block 4 now shows the real output:
     - File name "merged.txt" with size "84 KB" and "12 473 слова"
     - Two buttons: `[Открыть]` primary, `[Показать в папке]` ghost

## What to avoid

- Do not add a left sidebar or right rail on THIS screen — the four
  blocks use the full content width.
- Do not add fake data beyond what I specified. Do not invent extra
  settings, extra tabs, extra buttons. Keep exactly the buttons named
  above.
- Do not use pure white (#FFFFFF) for the page canvas — must be warm
  off-white.
- Do not use cold gray shadows. All shadows warm-tinted.
- Do not put emojis in the final render — replace with proper Lucide icons.
- Do not use serif fonts anywhere.
- Do not use fantasy decorative elements (swords, dice, dragons).

---END---

## Notes for the humans handling Flowstep

- Iterate in ONE Flowstep session. Don't start over.
- If the first pass goes too "corporate SaaS" — push back with:
  > "Less Linear, more Obsidian. Make the canvas warmer and add a subtle
  > grainy paper texture behind the blocks — 2% opacity max."
- If the accent color comes out too bright / orange / neon — push back:
  > "Desaturate the accent. Target: burnt ochre around #B8722B–#C48A3A,
  > not traffic-cone orange."
- If typography feels generic — push back:
  > "Try Geist Sans instead of Inter. Slightly tighter line-height."
- Collect all three state variants (idle / running / done) in one image
  so we can compare.
