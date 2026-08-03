# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The pipeline was rewritten from the ground up: the WhisperX-era launcher script is
gone, replaced by a six-layer codebase (`domain / sources / mergers / renderers /
core / ui`) behind a PySide6/QML desktop UI. Measured on a real 4h45m six-track
session, the new pipeline runs in 18m34s against two to three hours, adds 722 words
of recovered speech, and produces zero silence hallucinations against 39.

### Added
- PySide6/QML desktop UI (`python -m ui`): session timeline, waveforms, per-stage
  pipeline progress, models screen, settings
- GigaAM-v3 speech backend via sherpa-onnx, with its own VAD and bundle installer
  (ADR-013)
- Global ASR settings — device, compute type, beam size, language, GigaAM variant
  and precision, CPU threads — persisted across runs (feature #2)
- Multiple Craig archives per session: per-segment ASR fan-out, per-segment peaks
  and waveforms on a shared axis (feature #4)
- speaker_map editor: player → multiple characters, GM and listener roles, session
  cast strip (feature #5)
- Combat log source — `pf2e-combat-chronicle` encounter dumps parsed into typed
  game-log events on the timeline
- Absolute time window for the session: chat and combat lanes are positioned by
  real timestamps rather than full width (feature #3, iteration 3a)
- Chunking of the merged transcript for LLM post-processing, with configurable
  chunk size and overlap (feature #7)
- Per-track transcript reuse: a repeat run over the same session reloads the
  canonical JSON instead of re-running ASR (under a second per track, warm)
- First-run install prompt that provisions the selected backend
- CLI with GUI parity (`python -m ui <args>`)
- Bootstrap installer and PyInstaller build for both executables (frozen — see
  FEATURE_REQUESTS #1)
- `pyproject.toml`, CI matrix (ubuntu/windows × py3.11/3.12), three-tier e2e test
  strategy, ~490 tests
- Open-source project hygiene: LICENSE (MIT), README, CONTRIBUTING, CODE_OF_CONDUCT,
  SECURITY, issue and PR templates
- `VISION.md` — product specification: principles, layers and slots, the ladder of
  releases and how each step is measured

### Changed
- Project repositioned as "TTRPG Session Transcriber" — open-source desktop tool for
  processing Discord game session recordings
- Same-speaker merge gap raised from 1.0s to 2.0s: the old value was tuned for
  Whisper chunking and left VAD-sliced monologues shattered
- GigaAM no longer enables beam search by default — `modified_beam_search` hung
  indefinitely on real speech

### Fixed
- `speaker_map.json` never reached the ASR sources from the Qt shell, so `merged.txt`
  carried audio file stems instead of player names
- Waveform peaks are decoded in parallel; lanes shimmer while pending
- Live track counter and listener exclusion in the session view

### Removed
- `scripts/wisper_launcher.py` and `scripts/merge_whisperx.py` — the monolith and its
  merger, superseded by the layered pipeline

## [0.0.1] - 2026-03

### Added
- Initial single-EXE launcher with installer UI
- GitHub Actions release workflow
- Foundry VTT chat log integration via `parse_fvtt_chat.py`
- WhisperX-based transcription pipeline
- Per-track Craig multi-speaker support via `merge_whisperx.py`
- LLM post-processing via `session-clean` and `session-book` skills

[Unreleased]: https://github.com/vvechkanov/ttrpg-session-transcriber/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/vvechkanov/ttrpg-session-transcriber/releases/tag/v0.0.1
