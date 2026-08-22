# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Timezone anchor measured from the combat dump: `Бой*.txt` timestamps are UTC while the chat export is browser-local, so the offset between them can be measured instead of guessed. Independent of the machine running the merge
- Coverage warning when the Craig recording starts after the session did — names how much chat and which encounters have no audio behind them, on the session screen before the run rather than in the output after it
- `CONTRIBUTING.md` now says when the tier-2 end-to-end run is owed — before a release, and on changes to `sources/`, `mergers/`, `renderers/` or `core/pipeline.py`. CI has never run that suite and, by decision, will not: it needs a ~3.2 GB model bundle. `tests/test_tier2_e2e_gate.py` guards the mechanical half — that the suite still carries both markers and that CI's selection still excludes it
- ADR-021 records why screen invariants are checked by geometry rather than by pixel screenshots: the same four screens regenerated on Linux differ from the committed Windows captures in every file size, because the capture script registers Windows-only font paths

### Changed
- Project repositioned as "TTRPG Session Transcriber" — open-source desktop tool for processing Discord game session recordings
- The `craig-start` marker now resolves to the nearest quarter hour instead of the nearest hour, so zones like UTC+5:30 and UTC+5:45 survive it

### Fixed
- Three of the four session tabs — «Транскрипт», «Журнал», «Настройки сессии» — offered a pointing-hand cursor and did nothing when clicked: the screens behind them do not exist yet and their `tabActivated` signal had no listener anywhere. They are now visibly disabled, and the active tab is bound to screen state instead of a hardcoded literal
- The UI, the timeline strip and the merger resolved the chat log's UTC offset three different ways and could disagree by whole hours on the same files. They now share one resolver
- The system-timezone step asked for today's offset instead of the session's, sliding sessions recorded across a DST boundary by an hour
- Chat messages and combat events recorded before the recording started were dropped silently; they are now reported

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
