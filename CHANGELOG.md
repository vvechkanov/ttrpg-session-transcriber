# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Open-source project hygiene: LICENSE (MIT), README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue and PR templates
- Decision log and detailed roadmap in `TASKS.md`

### Changed
- Project repositioned as "TTRPG Session Transcriber" — open-source desktop tool for processing Discord game session recordings

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
