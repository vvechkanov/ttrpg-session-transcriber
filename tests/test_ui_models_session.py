"""Tests for ``ui.models.session`` — Timeline screen view-models.

Focus of this file: iteration 3a of feature #3 — absolute-time
``startPct`` / ``endPct`` on ``SourceListModel`` rows. Covers:

* A session folder with real ``info.txt`` + ``Бой 1.txt`` produces
  non-zero, non-100 percentages for the combat row.
* A session folder without ``info.txt`` falls back to the legacy
  0..100% layout (no TimelineWindow can be built).
* ``SessionMeta.timelineWindow()`` is populated when the source
  list builds one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Warm the sources package before pulling Qt modules — matches the
# pattern from tests/test_ui_engines_pipeline_controller.py.
from core.pipeline import run as _  # noqa: F401

from PySide6.QtGui import QGuiApplication

from ui.models import SessionMeta, SourceListModel


def _ensure_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("session-model-test")
    app.setOrganizationName("session-model-test")
    return app


def _write_info(session: Path, start_iso: str) -> None:
    (session / "info.txt").write_text(
        f"Recording x\nStart time: {start_iso}\n",
        encoding="utf-8",
    )


def _write_combat(session: Path, name: str, started: str, ended: str) -> None:
    data = {
        "encounter_id": "x",
        "scene_name": "x",
        "started_at": started,
        "ended_at": ended,
        "initiative_order": [],
    }
    (session / name).write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )


def test_combat_row_percents_are_absolute_when_info_present(tmp_path: Path) -> None:
    """Combat whose times fall in the middle of the window renders mid-bar."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_info(session, "2026-04-09T17:21:29.274Z")
    _write_combat(
        session, "Бой 1.txt",
        "2026-04-09T19:25:33.183Z",
        "2026-04-09T20:45:45.523Z",
    )

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    # Exactly one row — the combat file.
    assert model.rowCount() == 1
    start_pct = model.data(model.index(0), SourceListModel.StartRole)
    end_pct = model.data(model.index(0), SourceListModel.EndRole)

    # Expected window: info_start .. info_start + 4h (default floor).
    # Combat starts at +2h4m4s = 124.07min / 240min = ~51.7%.
    # Combat ends at +3h24m16s = 204.27min / 240min = ~85.1%.
    assert 50.0 < start_pct < 53.0
    assert 84.0 < end_pct < 86.0

    # And SessionMeta got the window published back.
    window = meta.timelineWindow()
    assert window is not None
    assert window.t0.year == 2026


def test_no_info_no_sources_leaves_window_none(tmp_path: Path) -> None:
    """A folder without info.txt *and* without parseable combat/chat
    produces no window, so SessionMeta.timelineWindow stays ``None``."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    assert model.rowCount() == 0
    assert meta.timelineWindow() is None


def test_no_info_with_combat_still_builds_window(tmp_path: Path) -> None:
    """When info.txt is missing, a valid combat span anchors the window
    on its own. The lone combat row renders at 0..100% because its
    bounds *are* the window bounds — but the window is still real."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_combat(
        session, "Бой 1.txt",
        "2026-04-09T19:25:33.183Z",
        "2026-04-09T20:45:45.523Z",
    )

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    assert model.rowCount() == 1
    start_pct = model.data(model.index(0), SourceListModel.StartRole)
    end_pct = model.data(model.index(0), SourceListModel.EndRole)
    # Combat *is* the window — its bounds collapse to 0..100.
    assert start_pct == pytest.approx(0.0)
    assert end_pct == pytest.approx(100.0)
    assert meta.timelineWindow() is not None


def _write_flac_stub(path: Path) -> None:
    """Write a placeholder file at ``path`` — ffprobe is never called
    because TrackListModel.loadFromDir doesn't probe durations in 4a."""

    path.write_bytes(b"fLaC-stub")


def test_two_craig_segments_group_by_speaker(tmp_path: Path) -> None:
    """A session with craig-1/ + крэйг-2/ collapses into one row per
    unique speaker, not per file. Each row carries both segments."""

    _ensure_app()

    # Local import so the module-level test file above runs with just
    # SessionMeta/SourceListModel imports and this test pulls in the
    # track-side pieces only when exercised.
    from ui.models import TrackListModel
    from ui.models.session import TrackSegment  # re-exported via module

    session = tmp_path / "Session 6"
    session.mkdir()

    craig1 = session / "craig-1"
    craig1.mkdir()
    _write_flac_stub(craig1 / "1-sir_o_genri.flac")
    _write_flac_stub(craig1 / "2-v_vladimir.flac")
    _write_flac_stub(craig1 / "3-kozeff.flac")
    _write_flac_stub(craig1 / "4-vasia_nastasia.flac")
    _write_flac_stub(craig1 / "5-cybrea.flac")
    _write_flac_stub(craig1 / "6-orangeunicorn.flac")
    _write_info(craig1, "2026-04-09T17:00:00Z")

    craig2 = session / "крэйг-2"
    craig2.mkdir()
    _write_flac_stub(craig2 / "1-kozeff.flac")
    _write_flac_stub(craig2 / "2-sir_o_genri.flac")
    _write_flac_stub(craig2 / "3-orangeunicorn.flac")
    _write_flac_stub(craig2 / "4-v_vladimir.flac")
    _write_flac_stub(craig2 / "5-cybrea.flac")
    _write_flac_stub(craig2 / "6-vasia_nastasia.flac")
    _write_info(craig2, "2026-04-09T18:30:00Z")

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    # Six unique speakers — not twelve.
    assert tracks.rowCount() == 6

    # Every row has exactly two segments and the primary audio_path is
    # the one Craig recorded first (earlier start_ts).
    primary_stems = set()
    for row in range(tracks.rowCount()):
        segments_payload = tracks.data(
            tracks.index(row), TrackListModel.SegmentsRole
        )
        # No TimelineWindow attached → payload is the fallback 0..100%
        # *per segment* but we don't care about percentages here —
        # just check the underlying entry has 2 segments. Payload
        # length equals segment count regardless of window state.
        assert len(segments_payload) == 2, (
            f"row {row} should have 2 segments, got {len(segments_payload)}"
        )
        # NameRole was the audio stem until feature #5 iter 5b/2 — now
        # it picks up ``speaker_map.player`` if a map exists. Test the
        # actual primary audio path stem instead, which is grouping-
        # invariant.
        audio_path = tracks.audioPathFor(row)
        primary_stems.add(Path(audio_path).stem)

    # All six canonical speaker stems show up as the primary audio
    # file for some row.
    expected = {
        "1-sir_o_genri",
        "2-v_vladimir",
        "3-kozeff",
        "4-vasia_nastasia",
        "5-cybrea",
        "6-orangeunicorn",
    }
    assert primary_stems == expected


def test_single_craig_session_backward_compat(tmp_path: Path) -> None:
    """Flat layout (legacy pre-feature-#4 sessions) still produces one
    row per audio file with a single segment."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "flat"
    session.mkdir()
    _write_flac_stub(session / "1-andrey.flac")
    _write_flac_stub(session / "2-boris.flac")
    # Info.txt at the flat level still sets a start_ts for the lone
    # segment but doesn't change row count.
    _write_info(session, "2026-04-09T17:00:00Z")

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    assert tracks.rowCount() == 2
    for row in range(tracks.rowCount()):
        payload = tracks.data(
            tracks.index(row), TrackListModel.SegmentsRole
        )
        # Single segment per row — falls back to 0..100% because no
        # TimelineWindow is attached to this bare TrackListModel.
        assert len(payload) == 1


def test_late_joiner_has_single_segment(tmp_path: Path) -> None:
    """A speaker present in only one of the two Craig segments gets a
    row with exactly one TrackSegment — not two — so the UI doesn't
    draw a bogus placeholder rect for audio that doesn't exist."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "late-joiner"
    session.mkdir()

    craig1 = session / "craig-1"
    craig1.mkdir()
    _write_flac_stub(craig1 / "1-alice.flac")
    _write_info(craig1, "2026-04-09T17:00:00Z")

    # Bob shows up only in the second segment (arrived late).
    craig2 = session / "craig-2"
    craig2.mkdir()
    _write_flac_stub(craig2 / "1-alice.flac")
    _write_flac_stub(craig2 / "2-bob.flac")
    _write_info(craig2, "2026-04-09T18:00:00Z")

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    assert tracks.rowCount() == 2
    payloads_by_name = {
        tracks.data(tracks.index(r), TrackListModel.NameRole):
            tracks.data(tracks.index(r), TrackListModel.SegmentsRole)
        for r in range(tracks.rowCount())
    }
    # Alice appears in both segments → 2 entries.
    assert len(payloads_by_name["1-alice"]) == 2
    # Bob appears only in craig-2 → 1 entry.
    assert len(payloads_by_name["2-bob"]) == 1


def test_segments_role_uses_timeline_window_when_attached(
    tmp_path: Path,
) -> None:
    """With SessionMeta attached and a TimelineWindow built from the
    source side, SegmentsRole resolves each segment's start_ts to a
    non-zero startPct."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()

    craig1 = session / "craig-1"
    craig1.mkdir()
    _write_flac_stub(craig1 / "1-alice.flac")
    _write_info(craig1, "2026-04-09T17:00:00Z")

    craig2 = session / "craig-2"
    craig2.mkdir()
    _write_flac_stub(craig2 / "1-alice.flac")
    _write_info(craig2, "2026-04-09T19:00:00Z")

    # Top-level info.txt anchors the TimelineWindow at 17:00; a combat
    # at 20:30 extends t_end and gives the window a real span.
    _write_info(session, "2026-04-09T17:00:00Z")
    _write_combat(
        session, "Бой 1.txt",
        "2026-04-09T20:30:00Z",
        "2026-04-09T20:45:00Z",
    )

    meta = SessionMeta()
    sources = SourceListModel()
    sources.setSessionMeta(meta)
    sources.loadFromDir(str(session))
    # Sanity: window was built.
    assert meta.timelineWindow() is not None

    tracks = TrackListModel()
    tracks.setSessionMeta(meta)
    tracks.loadFromDir(str(session))

    # Alice is the only speaker — one row, two segments.
    assert tracks.rowCount() == 1
    payload = tracks.data(tracks.index(0), TrackListModel.SegmentsRole)
    assert len(payload) == 2
    # Primary segment starts at t0 → 0%. Secondary at t0+2h on a 4h
    # default window → ~50%.
    assert payload[0]["startPct"] == pytest.approx(0.0, abs=0.1)
    assert 40.0 < payload[1]["startPct"] < 60.0


def test_malformed_combat_still_gets_a_row_fullwidth(tmp_path: Path) -> None:
    """A broken combat JSON still renders as a full-width row so the
    user isn't left wondering why their file disappeared."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_info(session, "2026-04-09T17:21:29.274Z")
    (session / "Бой 1.txt").write_text("{broken json", encoding="utf-8")

    meta = SessionMeta()
    model = SourceListModel()
    model.setSessionMeta(meta)
    model.loadFromDir(str(session))

    assert model.rowCount() == 1
    start_pct = model.data(model.index(0), SourceListModel.StartRole)
    end_pct = model.data(model.index(0), SourceListModel.EndRole)
    # Window exists (info.txt present) but combat parse failed →
    # full-width fallback for that single row.
    assert start_pct == 0.0
    assert end_pct == 100.0


# ─── feature #4 iteration 4b — per-segment peaks ────────────────────────


def test_set_peaks_per_segment_populates_segments_role(tmp_path: Path) -> None:
    """setPeaks(row, seg_idx, peaks) fills peaks_by_segment and the
    SegmentsRole payload exposes the matching list in order."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()

    craig1 = session / "craig-1"
    craig1.mkdir()
    _write_flac_stub(craig1 / "1-alice.flac")
    _write_info(craig1, "2026-04-09T17:00:00Z")

    craig2 = session / "craig-2"
    craig2.mkdir()
    _write_flac_stub(craig2 / "1-alice.flac")
    _write_info(craig2, "2026-04-09T18:00:00Z")

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    # One row (Alice), two segments.
    assert tracks.rowCount() == 1
    tracks.setPeaks(0, 0, [0.1, 0.2, 0.3])
    tracks.setPeaks(0, 1, [0.5, 0.6])

    payload = tracks.data(tracks.index(0), TrackListModel.SegmentsRole)
    assert len(payload) == 2
    assert payload[0]["peaks"] == [0.1, 0.2, 0.3]
    assert payload[1]["peaks"] == [0.5, 0.6]


def test_set_peaks_primary_mirrors_to_row_peaks(tmp_path: Path) -> None:
    """Writing seg_idx=0 also updates the row-level ``peaks`` list so
    legacy PeaksRole readers still see the primary waveform."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "flat"
    session.mkdir()
    _write_flac_stub(session / "1-andrey.flac")

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    tracks.setPeaks(0, 0, [0.9, 0.8])
    # PeaksRole exposes the row-level list — same content.
    assert tracks.data(tracks.index(0), TrackListModel.PeaksRole) == [0.9, 0.8]


def test_set_peaks_secondary_does_not_touch_primary(tmp_path: Path) -> None:
    """Non-primary peaks land on the segment, leave the row mirror alone."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()

    craig1 = session / "craig-1"
    craig1.mkdir()
    _write_flac_stub(craig1 / "1-alice.flac")
    _write_info(craig1, "2026-04-09T17:00:00Z")

    craig2 = session / "craig-2"
    craig2.mkdir()
    _write_flac_stub(craig2 / "1-alice.flac")
    _write_info(craig2, "2026-04-09T18:00:00Z")

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    # Start with empty peaks everywhere, then drop secondary-only.
    tracks.setPeaks(0, 1, [0.42])
    # Row-level primary mirror is still empty.
    assert tracks.data(tracks.index(0), TrackListModel.PeaksRole) == []
    payload = tracks.data(tracks.index(0), TrackListModel.SegmentsRole)
    assert payload[0]["peaks"] == []
    assert payload[1]["peaks"] == [0.42]


# ─── feature #5 iteration 5b/2 — speaker_map editor ──────────────────────


def _write_speaker_map(session: Path, raw: dict) -> None:
    (session / "speaker_map.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_load_from_dir_populates_characters_and_role(tmp_path: Path) -> None:
    """speaker_map.json drives each row's player / characters / role."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-test_gm.flac")
    _write_flac_stub(session / "2-test_player.flac")
    _write_speaker_map(session, {
        "1-test_gm": {"player": "Alice", "characters": [], "role": "GM"},
        "2-test_player": {
            "player": "Bob",
            "characters": ["Aragorn", "Legolas"],
            "role": "PC",
        },
    })

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    assert tracks.rowCount() == 2

    by_path = {}
    for row in range(tracks.rowCount()):
        stem = Path(tracks.audioPathFor(row)).stem
        by_path[stem] = {
            "name": tracks.data(tracks.index(row), TrackListModel.NameRole),
            "role": tracks.data(tracks.index(row), TrackListModel.RoleRole),
            "characters": tracks.data(tracks.index(row), TrackListModel.CharactersRole),
            "display": tracks.data(tracks.index(row), TrackListModel.CharacterDisplayRole),
        }

    assert by_path["1-test_gm"]["name"] == "Alice"
    assert by_path["1-test_gm"]["role"] == "GM"
    assert by_path["1-test_gm"]["characters"] == []

    assert by_path["2-test_player"]["name"] == "Bob"
    assert by_path["2-test_player"]["role"] == "Игрок"
    assert by_path["2-test_player"]["characters"] == ["Aragorn", "Legolas"]
    assert by_path["2-test_player"]["display"] == "Aragorn / Legolas"


def test_legacy_character_field_normalises_to_list(tmp_path: Path) -> None:
    """The old ``character: "..."`` shape on disk loads as a one-element list."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")
    _write_speaker_map(session, {
        "1-alice": {"player": "Alice", "character": "Aragorn", "role": "PC"},
    })

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    assert tracks.rowCount() == 1
    chars = tracks.data(tracks.index(0), TrackListModel.CharactersRole)
    assert chars == ["Aragorn"]


def test_aggregated_characters_dedups_and_sorts(tmp_path: Path) -> None:
    """``aggregatedCharacters`` returns a sorted, de-duped union."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")
    _write_flac_stub(session / "2-bob.flac")
    _write_flac_stub(session / "3-carol.flac")
    _write_speaker_map(session, {
        "1-alice": {"player": "Alice", "characters": ["Bran", "Aragorn"], "role": "PC"},
        "2-bob": {"player": "Bob", "characters": ["Aragorn"], "role": "PC"},
        "3-carol": {"player": "Carol", "characters": [], "role": "GM"},
    })

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    # Aragorn appears in two rows but only once in the aggregate;
    # sorted alphabetically.
    assert tracks.aggregatedCharacters == ["Aragorn", "Bran"]


def test_update_speaker_map_row_emits_aggregate_change(tmp_path: Path) -> None:
    """Updating a row triggers ``aggregatedCharactersChanged`` for the strip."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")
    _write_speaker_map(session, {
        "1-alice": {"player": "Alice", "characters": ["Aragorn"], "role": "PC"},
    })

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    fired = []
    tracks.aggregatedCharactersChanged.connect(lambda: fired.append(True))

    tracks.updateSpeakerMapRow(0, "Alice", "PC", ["Aragorn", "Legolas"])

    assert fired, "aggregatedCharactersChanged was not emitted"
    assert tracks.aggregatedCharacters == ["Aragorn", "Legolas"]
    chars = tracks.data(tracks.index(0), TrackListModel.CharactersRole)
    assert chars == ["Aragorn", "Legolas"]


# ─── Reviewer follow-up to 5b/2 ─────────────────────────────────────────


def test_load_from_dir_migrates_legacy_project_root_map(
    tmp_path: Path, monkeypatch
) -> None:
    """Project-root speaker_map.json gets copied into the session dir on
    first load, then drives the row data — read-side fallback alone
    isn't enough because re-saves would orphan the user's edits.
    """

    _ensure_app()

    from ui.models import TrackListModel
    from core import speaker_map as core_speaker_map

    # Pretend the project root is a sandbox so we don't rely on the
    # real repo-level speaker_map.json (which exists with unrelated
    # entries and would otherwise leak into the test).
    fake_root = tmp_path / "fake_project_root"
    fake_root.mkdir()
    monkeypatch.setattr(core_speaker_map, "_project_root", lambda: fake_root)

    legacy_map = {
        "1-alice": {"player": "Alice", "character": "Aragorn", "role": "PC"},
    }
    (fake_root / "speaker_map.json").write_text(
        json.dumps(legacy_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")
    # No session-local speaker_map.json on disk yet.
    assert not (session / "speaker_map.json").exists()

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    # Migration copied the file into the session folder.
    session_map = session / "speaker_map.json"
    assert session_map.exists(), (
        "loadFromDir should migrate the legacy project-root speaker_map.json"
    )
    # And it normalised on save (legacy `character` → `characters` list).
    on_disk = json.loads(session_map.read_text(encoding="utf-8"))
    # The migration is a copy, not a re-normalise — the reader still
    # normalises in memory. Ensure the row reflects the normalised form.
    assert "1-alice" in on_disk
    assert tracks.rowCount() == 1
    chars = tracks.data(tracks.index(0), TrackListModel.CharactersRole)
    assert chars == ["Aragorn"]
    name = tracks.data(tracks.index(0), TrackListModel.NameRole)
    assert name == "Alice"


def test_load_from_dir_listener_role_round_trips(tmp_path: Path) -> None:
    """A speaker_map entry with role="Слушатель" loads as excluded."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-quiet.flac")
    _write_speaker_map(session, {
        "1-quiet": {"player": "Quiet", "characters": [], "role": "Слушатель"},
    })

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    assert tracks.rowCount() == 1
    role = tracks.data(tracks.index(0), TrackListModel.RoleRole)
    excluded = tracks.data(tracks.index(0), TrackListModel.ExcludedRole)
    assert role == "Слушатель"
    assert excluded is True


def test_has_speaker_map_role_distinguishes_fresh_vs_saved(tmp_path: Path) -> None:
    """``HasSpeakerMapRole`` is True only for rows hydrated from disk."""

    _ensure_app()

    from ui.models import TrackListModel

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-known.flac")
    _write_flac_stub(session / "2-fresh.flac")
    _write_speaker_map(session, {
        "1-known": {"player": "Known", "characters": ["Hero"], "role": "PC"},
        # 2-fresh deliberately omitted.
    })

    tracks = TrackListModel()
    tracks.loadFromDir(str(session))

    by_stem = {}
    for row in range(tracks.rowCount()):
        stem = Path(tracks.audioPathFor(row)).stem
        by_stem[stem] = tracks.data(
            tracks.index(row), TrackListModel.HasSpeakerMapRole
        )

    assert by_stem["1-known"] is True
    assert by_stem["2-fresh"] is False

    # And after a save through updateSpeakerMapRow, the flag flips.
    fresh_row = next(
        r for r in range(tracks.rowCount())
        if Path(tracks.audioPathFor(r)).stem == "2-fresh"
    )
    tracks.updateSpeakerMapRow(fresh_row, "FreshPlayer", "PC", ["Char"])
    assert tracks.data(
        tracks.index(fresh_row), TrackListModel.HasSpeakerMapRole
    ) is True
