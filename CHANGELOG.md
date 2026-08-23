# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Timezone anchor measured from the combat dump: `Бой*.txt` timestamps are UTC while the chat export is browser-local, so the offset between them can be measured instead of guessed. Independent of the machine running the merge
- Coverage warning when the Craig recording starts after the session did — names how much chat and which encounters have no audio behind them, on the session screen before the run rather than in the output after it
- `CONTRIBUTING.md` now says when the tier-2 end-to-end run is owed — before a release, and on changes to `sources/`, `mergers/`, `renderers/`, `core/` or `domain/` — everything the run reads. CI has never run that suite and, by decision, will not: it needs a ~3.2 GB model bundle (ADR-022). `tests/test_tier2_e2e_gate.py` guards the mechanical half — that the suite still carries both markers, and that no pytest invocation in `ci.yml` collects it
- ADR-021 records why screen invariants are checked by geometry rather than by pixel screenshots: the same four screens regenerated on Linux differ from the committed Windows captures in every file size, because the capture script registers Windows-only font paths. It also records what `scripts/dump_qml_geometry.py` actually flags today — zero width or height — as against the two further checks its own docstring claims and does not implement

### Changed
- Project repositioned as "TTRPG Session Transcriber" — open-source desktop tool for processing Discord game session recordings
- The `craig-start` marker now resolves to the nearest quarter hour instead of the nearest hour, so zones like UTC+5:30 and UTC+5:45 survive it
- Five settings that wrote to disk and were read by nobody are now visibly disabled and marked «СКОРО» rather than silently accepting input: the working folder (the session picker never asked for it), interface language (the project has no `QTranslator` at all), tooltips (no `ToolTip` exists in any screen), the completion sound (nothing in the project plays audio) and the Foundry OOC mode. OOC turned out not to be a wiring bug but an unbuilt feature — `ScriptMerger` takes no OOC parameter, no renderer looks at a message's channel, and the Foundry source stamps every message `"ic"` — so it joins the four rather than being fixed alongside the gap

### Fixed
- «Макс. gap между репликами» in Settings never reached the merger. The GUI built its merge worker without a gap at all, so `ScriptMerger` glued replicas by the worker's own default whatever the field said — the value saved, redisplayed on restart, and changed nothing about merged.txt. It is now passed through, with the previous default kept for an unset or unparseable field so a fresh install merges byte-for-byte as before. One case does move: anyone who typed a number into the dead field back when it did nothing will see their merged.txt change on the next run — the setting they made is finally being honoured
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
