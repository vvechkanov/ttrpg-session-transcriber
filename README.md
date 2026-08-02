# TTRPG Session Transcriber

**English** | [Русский](README.ru.md)

> The only open-source desktop tool that merges your **Foundry VTT chat log** into a **per-speaker Discord audio transcript** — locally, free, on your own hardware.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)
[![Status: pre-release](https://img.shields.io/badge/status-pre--release-orange.svg)](TASKS.md)

Process your **D&D / Pathfinder 2e** session recordings from Discord into clean, attributed transcripts ready for LLM-powered recap generation. Designed for the player who doesn't want to learn Docker, Python, or PowerShell — download one `.exe`, drop your Craig folder in, get a transcript.

> **Status:** v0.1.0 in active development. Pre-release builds are available in [Releases](../../releases). See [TASKS.md](TASKS.md) for the roadmap.

---

## Why this exists

If you've ever tried to transcribe your D&D session, you've hit one of these walls:

- **Cloud services** (Otter, Sonix, Kazkar, Archivist) — paid, your audio leaves your machine, no Foundry VTT integration
- **Generic Whisper wrappers** (Buzz, MacWhisper) — single-track only, can't tell which player cast Fireball
- **Open-source pipelines** (TASMAS, Scribble) — Docker-only, English-focused, command-line, not for non-technical players
- **Acoustic diarization** (WhisperX, pyannote) — struggles with overlapping voices, NPC impressions, and laughter

This project fixes all of that for the specific case of **a TTRPG group recording sessions through Craig on Discord**.

## What makes it different

### 🎲 Foundry VTT chat log alignment
Dice rolls, whispers, and OOC text from your Foundry VTT chat get woven into the audio transcript at the right moments in the session timeline. **No other open-source tool does this.**

### 🗣️ First-class Russian via GigaAM-v3
Sber's open Russian ASR model (MIT licensed) is shipped as a first-class backend with **contextual biasing** for PF2e names. Recognizes "Ачакек" and "Маэри" without hand-coaching the model.

### 📦 One-click `.exe` install for non-technical players
No Docker, no Python install, no PowerShell, no Hugging Face tokens. The single-EXE installer sets up Python, PyTorch, your chosen ASR backend, and ffmpeg automatically.

### 🎯 Perfect speaker attribution from Craig multi-track
Instead of fighting acoustic diarization on overlapping excited voices, we use Craig's per-speaker audio tracks. Every word is labeled correctly because every player is on their own audio stream. No pyannote, no Hugging Face EULA, no guessing.

### 🔄 Russian + English code-switching
Built for tables that say "каст Fireball на DC 15" without the model breaking. The default `bzikst/faster-whisper-large-v3-ru-podlodka` model handles both languages natively.

### 🔌 Pluggable ASR backends
Pick the engine that fits your sessions:

| Backend | Best for | License |
|---|---|---|
| `faster-whisper` (default) | Russian + English mixed sessions, all languages | MIT |
| `sherpa-onnx` + GigaAM-v3 | Pure Russian sessions, best Russian quality | MIT |
| `whisperx` (legacy) | Existing setups, backward compatibility | BSD-2 |

---

## Quick start

> **Pre-release:** the single-EXE installer is in active development. For now, use the developer setup below.

### Developer setup (works today)

```bash
git clone https://github.com/vvechkanov/ttrpg-session-transcriber.git
cd ttrpg-session-transcriber
python -m venv venv
venv\Scripts\activate                  # Windows
# source venv/bin/activate              # Linux/macOS
pip install -e .                        # add [dev] for the test suite
python -m ui
```

> **Requires ffmpeg on your `PATH`** (or drop the binaries into `tools/ffmpeg/bin`).
> The waveform/peaks tooling shells out to ffmpeg to decode audio.

In the GUI:

1. Pick your session folder (a folder of `.flac` tracks from Craig)
2. Optionally drop in a `speaker_map.json` to label tracks with player names
3. Optionally pick a Foundry VTT chat log to merge into the timeline
4. Click **Run**

Output appears in the same folder:

- `merged.txt` — full transcript with speaker labels and timestamps
- `chunks/` — text chunks ready for LLM post-processing

### Single-EXE install (coming in v0.1.0)

1. Download the latest `.exe` from [Releases](../../releases)
2. Run it. The installer downloads everything it needs.
3. Drop your Craig folder. Click **Transcribe**.

---

## How it works

```
Craig multi-track recording (.flac per player)
                +
Foundry VTT chat log export (optional)
                ↓
        ┌───────────────┐
        │  ASR backend  │ ← faster-whisper / sherpa-onnx / whisperx
        └───────────────┘
                ↓
   per-track JSON (canonical schema)
                ↓
        ┌───────────────┐
        │ merge timeline │ ← merge_whisperx.py
        └───────────────┘
                ↓
        merged.txt + chunks/
                ↓
        LLM post-processing (Claude / GPT / local)
                ↓
        Session recap, character notes, campaign log
```

---

## Comparison with alternatives

| | This project | TASMAS | Scribble | Kazkar.ai | Archivist | Buzz |
|---|---|---|---|---|---|---|
| **Local / free** | ✅ | ✅ | ✅ | ❌ cloud | ❌ cloud | ✅ |
| **Single .exe install** | ✅ | ❌ Docker | ❌ Docker | n/a | n/a | ✅ |
| **FVTT chat → audio merge** | ✅ | ❌ | ❌ | ❌ | ⚠️ entity sync only | ❌ |
| **Russian ASR (GigaAM)** | ✅ | ❌ | ❌ | ⚠️ generic | ❌ | ❌ |
| **Multi-track Craig input** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Pluggable ASR backends** | ✅ | ❌ | ⚠️ FW only | ❌ | ❌ | ❌ |
| **Pricing** | free | free | free | $$ | $6/mo | free |

---

## FAQ

**Why per-track Craig instead of acoustic diarization?**
Acoustic diarization (pyannote, WhisperX `--diarize`) struggles with TTRPG audio: overlapping excited voices, players doing NPC voices, dramatic shouting, and uncontrolled laughter. Craig records every player on a separate track, so attribution is perfect by construction — no model can confuse who said what when each speaker is on their own stream.

**Why GigaAM for Russian?**
GigaAM-v3 is Sber's open Russian ASR model under MIT license. On Russian audio it consistently outperforms Whisper. It also supports **contextual biasing** — you can hand it a list of NPC names and it will recognize them correctly instead of inventing creative variants. The hotwords file ships with PF2e names; you can swap in your own.

**Is my audio uploaded anywhere?**
No. Everything runs on your machine. No telemetry, no API calls, no cloud services. The project literally cannot see your audio — there is no server.

**Does it work without a GPU?**
Yes. All backends support CPU mode. With faster-whisper int8 quantization, a 3-hour session takes about 30-60 minutes on a modern CPU. With an NVIDIA GPU it takes 5-10 minutes.

**What about D&D 5e or other systems?**
The transcription pipeline is universal. We test it on Pathfinder 2e because that's what the maintainer plays. The hotwords file ships with PF2e names — you can replace `config/pathfinder_ru_hotwords.txt` with your own term list.

**Can I use this for non-TTRPG audio?**
Technically yes. Any multi-track Discord recording (podcasts, meetings, interviews) works. The Foundry VTT integration and PF2e hotwords obviously won't apply, but the core transcription pipeline is general-purpose.

**What's the difference vs Scribble / TASMAS?**
Scribble and TASMAS are both excellent open-source projects, but both require Docker, target English-speaking groups, and don't merge Foundry VTT chat into the audio timeline. We are built for the player who wants to double-click an `.exe`, not run `docker-compose up`.

---

## Project structure

```
ttrpg-session-transcriber/
├── launcher/                ← single-EXE installer (PyInstaller)
│   ├── bootstrap.py
│   ├── installer_ui.py
│   └── install_logic.py
├── ui/                     ← PySide6/QML GUI; entry point is `python -m ui`
│   ├── __main__.py         ← launches the QML application
│   ├── qml/                ← QML/JS UI assets
│   ├── engines/            ← background pipeline/ASR/merge workers
│   └── models/             ← Qt data models bound to the UI
├── core/                   ← pipeline orchestration, discovery, peaks
├── domain/                 ← pure dataclasses (segments, speaker maps)
├── sources/                ← ASR + FVTT input adapters
├── mergers/                ← per-track JSON → unified timeline
├── renderers/              ← timeline → merged.txt / chunks
├── prompts/                 ← LLM prompts for post-processing
├── config/                  ← hotwords, defaults
├── tests/                   ← pytest suite (in development)
└── docs/                    ← additional documentation
```

---

## Roadmap

See [TASKS.md](TASKS.md) for the detailed checklist. High level:

- **v0.1.0** (in progress) — faster-whisper backend, single-EXE installer with backend selection, FVTT chat alignment, MIT license, open-source project hygiene
- **v0.2.0** — GigaAM-v3 RNNT backend with contextual biasing, smoke tests on real Craig recordings, code quality skeleton
- **v0.3.0** — Polished GUI (PySide6 or improved tkinter), backend selection in installer
- **v1.0.0** — Cross-platform builds (Linux/macOS), full FVTT integration UX, production-ready

---

## Contributing

Pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgments

Built on top of excellent open-source work:

- **[Craig](https://craig.chat)** — multi-track Discord voice recorder by Yahweasel
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — primary ASR backend
- **[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** — ONNX runtime for GigaAM
- **[GigaAM](https://github.com/salute-developers/GigaAM)** — Sber's open Russian ASR model
- **[WhisperX](https://github.com/m-bain/whisperX)** — original transcription pipeline
- **[Foundry VTT](https://foundryvtt.com/)** — virtual tabletop integration
- **[Silero VAD](https://github.com/snakers4/silero-vad)** — voice activity detection
- **[bond005/whisper-podlodka-turbo](https://huggingface.co/bond005/whisper-podlodka-turbo)** — Russian Whisper fine-tune

Thanks to the TTRPG community for testing and feedback.
