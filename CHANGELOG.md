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
- Five settings that wrote to disk and were read by nobody are now visibly disabled and marked «СКОРО» rather than silently accepting input: the working folder (the session picker never asked for it), interface language (the project has no `QTranslator` at all), tooltips (no `ToolTip` exists in any screen), the completion sound (nothing in the project plays audio) and the Foundry OOC mode. OOC turned out not to be a wiring bug but an unbuilt feature — `ScriptMerger` takes no OOC parameter, no renderer looks at a message's channel, and the Foundry source stamps every message `"ic"` — so it joins the four rather than being fixed alongside the gap

### Fixed
- The «Расширенные параметры распознавания» disclosure in the per-track model popover could not be clicked anywhere, so the block behind it never opened. What that block holds is a mock-up rather than working settings — the VAD tags carry no handler at all, the punctuation checkbox is bound to nothing, and language and beam size already work globally from the Settings screen — so the fix restores a control that was visibly broken rather than settings that were out of reach; the block's own state is filed separately. Its `MouseArea` sat directly inside a `ColumnLayout`, and a layout sizes its children itself: the requested `width: parent.width` was replaced by an `implicitWidth` of zero, and the `y: -20` meant to lift the zone onto the caption was replaced by the layout's flow position, putting it below the caption instead. Measured on the real popover, the zone was `w=0 h=20` against a 352px header. The header row is now wrapped in a plain `Item` the layout sizes, with the click target anchored to it — the same shape as the disclosure that works in `ui/qml/timeline/CastStrip.qml`. The popover is 13px shorter as a result, and that is deliberate rather than overlooked: sized to nothing but 20 tall, the broken zone sat in the layout as an empty 20px row under the caption, and the wrapper keeps 20 of it back as the height of the click target the broken zone had asked for — leaving a 13px difference where the accident used to pad
- «Открыть папку моделей» on the Models screen stayed grey after a model was installed, until the app was restarted. `enabled` was bound to `ModelRegistry.modelsRoot`, a plain `Slot` — and a QML binding over a plain method is evaluated once at component creation and never again, so the button latched the "no folder yet" state of a fresh install. `modelsRoot` is now a `Property` notified by `installedStateChanged`, the signal `_on_worker_done` already emits; it was the last member of that group still a bare slot. Nothing in the app recovered from this short of a restart — `refresh()` does not help either, because it re-emits a signal the binding was never listening to
- Three of the four session tabs — «Транскрипт», «Журнал», «Настройки сессии» — offered a pointing-hand cursor and did nothing when clicked: the screens behind them do not exist yet and their `tabActivated` signal had no listener anywhere. They are now visibly disabled, and the active tab is bound to screen state instead of a hardcoded literal
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
