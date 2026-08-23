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
- `docs/process.md` §5 now looks for Codex's approval where it actually arrives. When Codex has findings it creates a review object; when it has none it creates no review at all and posts a plain PR comment carrying `**Reviewed commit:** <sha>`. §5 knew only the first channel and, for the second, told the agent to wait for a 👍 reaction — which the cloud runner cannot read through any available tool. Approved PRs therefore sat in «На ревью» overnight. The reaction rule is gone rather than kept "for later", both observable channels are named in terms the reader can call, and the comment's sha is documented as a 10-character prefix so it is matched by prefix rather than by an equality that can never hold. `tests/test_process_review_signals.py` guards it. The same section gains a way out of the wait it used to have no exit from: 20 minutes of silence, then one `@codex review`, then 20 more. That call is bounded to one per HEAD commit rather than one per run — a card outlives the night, so a per-run bound would let each night spend another 40 minutes on the same silent PR — and it carries the sha (`@codex review (HEAD: <sha>)`), because a PR comment has no commit attached and a bare invocation cannot be told apart from last night's
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
