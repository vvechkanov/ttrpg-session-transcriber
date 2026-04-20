# Handoff: Session Transcriber — Desktop App UI

## Overview

This is a UI/UX design handoff for **Session Transcriber** — an offline desktop app that takes multi-track audio recordings from a D&D / TTRPG session (typically from Craig bot for Discord), runs per-track speech-to-text, and merges the results with Foundry VTT chat logs into a single readable transcript.

The core backend logic already exists in Python (repo: `vvechkanov/ttrpg-session-transcriber`). This handoff covers the **new desktop UI** that wraps that logic.

## About the Design Files

The file `Session Transcriber.html` in this bundle is a **design reference** — a React-based HTML prototype showing intended look, layout, interactions, and states. **It is not production code to ship.**

The task is to **recreate this design in the target desktop environment** — for this project, that is **PySide6 + QML** on top of the existing Python codebase. The HTML is there so you can open it in a browser and inspect every screen, interaction, and visual detail side-by-side with your implementation.

See `QML_MAPPING.md` for a React-component → QML-file cross-reference.

## Fidelity

**High-fidelity.** Colors, typography, spacing, and interactions are final. The implementation should reproduce the look pixel-closely, adapted to QML idioms. Details worth preserving:

- The warm "amber parchment" palette (not generic grey Material)
- Mono font for filenames, durations, technical values
- Sans for UI copy
- Subtle borders and soft shadows (no hard/flat outlines)
- Warning/error states use muted red/amber, never bright Material red

## Product context (so the UI makes sense)

- **Everything runs locally.** No cloud APIs. Models are downloaded once and cached on disk.
- **Source of audio:** Craig bot on Discord produces one FLAC per speaker. Users drop in a folder or a zip.
- **Chat log context:** Foundry VTT SQLite chat logs (`.db`) are imported to get `/r 1d20` rolls, session notes, combat state with timestamps. Merger stitches them into the transcript.
- **Custom parsers:** beyond Foundry, users may have custom log sources (combat trackers, bot logs, Markdown notes). Custom Python parser files (`*.py`) can be dropped in — the app auto-detects source type on import.
- **Players vs Characters:** each audio track maps to one real player (Andrey, Boris…) who plays one or more characters (Gandalf, Aragorn…). Both names appear in the final transcript. The GM is a special player; listeners/observers may have no audio at all.
- **Per-track model override:** the default ASR model is set globally, but a quiet player (e.g. Carol on a bad mic) can be reassigned to a more accurate model on her track only.
- **Session lifecycle:** idle → ASR (per-track, parallel) → merge → done. No rendering phase — merge emits the final `.txt` directly.

## Screens / Views

### 1. Empty State (`screen='empty'`)

First-run state, shown when no sessions exist yet and no models are installed.

- Centered column, max-width ~600px
- Large headline ("Сессий пока нет")
- Subtitle explaining Craig → transcript flow
- Primary CTA: "Создать первую сессию" (opens new-session flow)
- Below the CTA: compact **"Сначала установите модель"** banner — warns that ASR won't work until a model is downloaded, with a link to Models screen
- Three-step "how it works" illustration below (Craig → per-track ASR → merged transcript)

### 2. Timeline (`screen='timeline'`) — the main working view

This is where 90% of the user's time is spent. It has **four phases** driven by `phase` state: `idle | asr | merge | done`.

**Layout (all phases):**

```
┌─ Sidebar (collapsed recent sessions) ─┬─ Header (breadcrumb · session name · meta · CPU/GPU status) ──────────┐
│                                       │                                                                        │
│                                       ├─ Tabs (Обработка | Транскрипт | Журнал | Настройки сессии) ─────────┤
│                                       │                                                                        │
│                                       ├─ Phase bar (Распознавание ── Сборка) ──── Model picker ── Action btn │
│                                       │                                                                        │
│                                       ├─ Additional sources panel (Foundry VTT, custom parsers) w/ ruler ────┤
│                                       │                                                                        │
│                                       ├─ Audio tracks panel (one row per player) w/ waveform + ruler ────────┤
│                                       │                                                                        │
│                                       ├─ Merger chip (collapsible settings preview) ─────────────────────────┤
│                                       │                                                                        │
│                                       └─ Output file chip ────────────────────────────────────────────────────┤
└───────────────────────────────────────┴────────────────────────────────────────────────────────────────────────┘
```

**Phase: `idle`** — ready to run. Action button: "Запустить обработку". Tracks show dry waveforms. Craig segment markers (vertical lines where Craig split the recording) are visible. An "+ добавить источник" row lets users drop more chat-log files. An "+ добавить дорожку" row lets users manually add audio.

**Phase: `asr`** — per-track transcription running. Each audio row shows its own progress bar overlaid on the waveform (0–100%, tinted). Tracks with overridden models show the override badge. The phase-bar dot for "Распознавание" pulses. Overall progress/ETA shown in the action-button area (e.g. "68% · ~1 мин осталось"). Button becomes "Пауза · Отмена".

**Phase: `merge`** — ASR done, merger stitching. Audio rows go static/muted. A **stitch overlay** appears across all lanes — vertical markers showing where Craig gaps are being bridged with chat-log events. The merger chip expands slightly to show live gap-fill count. Action button: "Сборка…".

**Phase: `done`** — finished. Audio rows become playable (click a waveform to preview). The output file chip shows size, duration, segment count, and has "Открыть", "Экспорт", "Показать в папке" actions. A subtle green check appears on the phase bar. User can tweak merger settings and re-run just the merge (cheap), or re-run ASR on one track (expensive, requires invalidation).

### 3. Models (`screen='models'`) — model manager

Table of ASR models:

| Column | Content |
|---|---|
| Model name | `GigaAM-v3 RNNT (int8)` with vendor subtitle (`Salute`, `OpenAI + CTranslate2`, `Alpha Cephei`) |
| Size | `420 MB`, `3.1 GB`… |
| Language | `RU`, `RU/EN`, `RU/EN/мульти…` |
| Accuracy | Horizontal bar + `98%` label (green ≥95, amber otherwise) |
| Speed | Dot + label (`быстро`, `средне`, `медленно`, `очень быстро`) |
| Action | `Сделать активной` / `Установить` / `Удалить` |

- Active model row has a tinted background and an "активна" badge
- Row click → opens **Model details drawer** on the right (see below)
- Bottom: disk-usage bar ("Занято на диске: 4.3 GB из 3 моделей") + "Открыть папку моделей" button
- Top: "+ Добавить модель" primary button (opens dialog to paste HuggingFace URL or local path)

### 4. Settings (`screen='settings'`) — app-level settings

Tabbed or single-page form with sections:

- **Устройство по умолчанию** — CPU / CUDA / MPS (disabled if not available). Default for new sessions; per-session override also available.
- **Языки по умолчанию** — comma-separated list
- **Папки по умолчанию** — где хранить сессии, модели, экспорт
- **Merger defaults** — max gap, role detection on/off, include dice rolls, include OOC, timestamp precision
- **Парсеры** — list of installed custom parsers (Python files dropped in), with test buttons
- **Горячие клавиши**
- **О программе**

### 5. Session settings tab (inside Timeline screen)

This is the 4th tab inside a session (`Настройки сессии`), distinct from app-level settings. Two panels:

**Panel A: Игроки и дорожки**
- Table: Player name · Characters · ASR model override · audio file path
- Inline-editable names
- Click "gAM"/"Whs⚠" badge → opens per-track model override popover
- Listeners (no audio) shown dimmed

**Panel B: Сборка таймлайна** (merger override for this session)
- Inherits global defaults, shows "override for this session" hint in the header
- Values that differ from the global default are highlighted (amber underline)
- Settings: max gap seconds, role detection, dice roll inclusion, OOC handling, timestamp format
- "Сбросить к глобальным" button

### 6. Model details drawer (overlays Models screen)

Right-side drawer, 460px wide, slides in from right.

- **Header:** model icon, name, vendor · size · language, close button
- **Stat chips:** accuracy %, speed, size
- **Параметры запуска** card:
  - Device (CPU/CUDA/MPS segmented)
  - Precision (int8 / fp16 / fp32)
  - CPU threads
  - VAD (выкл / мягкий / агрессивный)
  - Beam size slider
  - Checkboxes: auto-punctuation, name capitalization, session-level result cache
- **Action stack:**
  - "Сделать активной" / "Установить · 1.5 GB" (context-dependent)
  - "Открыть папку модели" (ghost)
  - "Удалить с диска" (red ghost, installed only)

Dismiss: click backdrop or close button.

### 7. Per-track model override popover (overlays Timeline)

Small anchored popover appearing next to the track's model badge.

- **Header:** player avatar + "Модель для {PlayerName}" + close
- **Radio list of available models:** default option at top ("Как у всех") + each installed model with short notes
- **Collapsible "Расширенные параметры распознавания":**
  - VAD segmented (with a Carol-specific hint if the track is marked quiet: "рекомендуем агрессивный")
  - Beam size, language, initial prompt (plain mono textbox with example fantasy-names list)
  - Punctuation checkbox
- **Footer:** "Сбросить к дефолтам" (ghost) · "Готово" (primary)

Dismiss: click elsewhere, close button, or "Готово".

## Interactions & Behavior

### Global

- Sidebar click → switch screen. Active item has amber accent + left-bar accent
- Phase persisted in `localStorage` so refresh doesn't lose state (prototype convenience — in production this lives in app state)
- All monospace text uses a dedicated mono font stack

### Timeline

- Hover on waveform lane → faint cursor line tracks mouse; click plays from position (done phase only)
- Hover on Craig segment marker → tooltip with exact timestamp
- Hover on "+ добавить источник" or "+ добавить дорожку" → row brightens
- Drag file onto timeline → opens Add-source dialog with auto-detected parser
- Running phase: action button turns into Pause/Cancel combo
- Transition idle→asr: phase-bar dot begins pulsing (1.2s cycle)
- Transition asr→merge: stitch markers appear with staggered fade-in across lanes
- Transition merge→done: phase-bar gets green check, output chip gets "Открыть" button

### Models

- Row hover: background lightens
- Row click: drawer slides in (200–240ms, ease-out)
- Drawer backdrop: 28% ink overlay; clicking closes

### Popovers

- Single global click handler closes any open popover unless click is inside it
- ESC also closes (to add in implementation)

### Animations (all 180–240ms, ease-out)

- `dropIn` — menus/dropdowns (translateY -12→0 + opacity)
- `slideDown` — inline panels (translateY -8→0 + opacity)
- `slideInR` — drawers (translateX +20→0 + opacity) — **removed in prototype due to screenshot-tool issue; can be re-added in QML with `Behavior on x`**
- `spin` — loading spinners
- `caret` — blinking text cursor in edit mode

## State Management

The prototype has this top-level state:

```js
{
  screen: 'timeline' | 'models' | 'settings' | 'empty',
  phase:  'idle' | 'asr' | 'merge' | 'done',
  // + local component state for popovers, drawers, inline edits
}
```

In production (Python/Qt):

- `AppModel` — current screen, current session ID
- `SessionModel` — per-session: phase, tracks, sources, merger settings, output path
- `TrackModel` — per-audio-track: player, characters, model override, ASR progress, waveform data
- `ModelRegistry` — installed models, active default, download queue
- `MergerEngine` — signals `progress(float)`, `gapFilled(ts, source)`, `done(path)`
- `AsrEngine` per track — runs in QThread; emits `progress(pct)`, `done(segments)`, `error(msg)`

All engines must be threaded — ASR/merge are CPU-heavy and will freeze the UI if run on the main thread.

## Design Tokens

### Colors (warm parchment palette)

```
bg           #FAF8F5   (app background)
card         #FFFFFF   (elevated surfaces, drawer, popover)
cardAlt      #F4F0E8   (muted surface, search, footer)

ink          #2D2520   (primary text)
ink2         #4A3F36   (secondary)
ink3         #6B625A   (tertiary, labels)
ink4         #9A9088   (muted, uppercase micro-labels)

border       rgba(107,98,90,0.18)   (card borders)
borderSoft   rgba(107,98,90,0.10)   (row separators)

accent       #C97B3E   (primary action — amber)
accentDeep   #9A5A28   (hover, active)
accentSoft   rgba(201,123,62,0.35)  (soft border on active states)
accentWash   rgba(201,123,62,0.08)  (row tint for active items)

green        #6B8E4E   (success, installed, good accuracy)
red          #B45454   (destructive)
amber        #C89A3E   (warnings, quiet-player flags)
```

### Player hues (for avatars + waveforms)

Each player gets a stable warm hue — 6 hand-picked values rotated per track. The base color is used for the round avatar and tinted `@ 45% alpha` for the waveform bars.

### Typography

- Sans: system-ui fallback stack tuned for Cyrillic readability (not Inter, not Roboto)
- Mono: JetBrains-style or Fira Code — used for filenames, timestamps, sizes, technical values
- Scale: 10/11/11.5/12/12.5/13/14/16/22 px (no values outside this set in the prototype)
- Weights: 400, 500, 600, 700

### Spacing

- Base unit: 4px
- Standard paddings: 4, 6, 8, 10, 12, 14, 16, 20, 24, 32px
- Gaps: 4, 6, 8, 10, 12, 14, 16
- Container max-widths: 600 (empty state), 1100–1200 (models table), fluid (timeline)

### Radii

- Small chips: 5–7px
- Cards: 9–12px
- Pill buttons: 999px
- Avatars: 999px

### Shadows

- Popovers: `0 20px 60px rgba(45,37,32,0.18), 0 4px 12px rgba(45,37,32,0.08)`
- Drawer: `-16px 0 40px rgba(45,37,32,0.14)`
- No drop shadows on regular cards — borders only

## Assets

No external image assets are used. All icons are **inline SVG** drawn with stroke-width 1.5 on a 16–20px box (the `I.*` icon set in the prototype). Re-implement in QML with `Shape` primitives or a small SVG file per icon.

Player avatars are **initials on tinted circles** — no uploaded images.

Waveforms are **generated client-side** from mock data in the prototype. In production they come from the audio-decoder pass before ASR (peak data cached per-track).

## Files

- `Session Transcriber.html` — full prototype, all screens in one file (React inline via Babel)
- `QML_MAPPING.md` — React → QML structure cross-reference
- `screenshots/` — (optional, not included by default) per-screen PNG references

## How to explore

1. Open `Session Transcriber.html` in a browser
2. A tiny "Phase & Screen" panel appears top-right (demo switcher). Use it to cycle through:
   - Empty state
   - Timeline · idle
   - Timeline · asr (with live-looking progress)
   - Timeline · merge (stitch overlay)
   - Timeline · done (playable)
   - Models
   - Settings (session settings tab)
3. Click around — per-track badges open the override popover, model rows open the drawer, add-source/add-track open their dialogs.
