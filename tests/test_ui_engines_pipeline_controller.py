"""Tests for ``ui.engines.pipeline_controller.PipelineController``.

Focuses on pieces that don't need a live QThread loop — summary
computation, state reset, cancellation flag. The full orchestration
(spawn worker → run → advance queue) is covered by the AsrWorker and
MergerWorker tests together with manual smoke via the boot harness.
"""

from __future__ import annotations

import json
from pathlib import Path

# Warm sources/__init__ before any deep imports (see test_core_asr).
from core.pipeline import run as _  # noqa: F401

from PySide6.QtGui import QGuiApplication

import sys

from domain.annotations import SpeechSegment
from ui.engines.pipeline_controller import PipelineController, _format_bytes
from ui.models import AppModel, SessionMeta, TrackListModel
from ui.models.session import TrackListModel as _TLM  # role aliases for clarity


def _write_flac_stub(path: Path) -> None:
    path.write_bytes(b"fLaC-stub")


def _write_speaker_map(session: Path, raw: dict) -> None:
    (session / "speaker_map.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _ensure_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("pc-test")
    app.setOrganizationName("pc-test")
    return app


def test_format_bytes_human_readable() -> None:
    assert _format_bytes(0) == "—"
    assert _format_bytes(-5) == "—"
    assert _format_bytes(512) == "512 B"
    assert _format_bytes(12 * 1024) == "12 KB"
    assert _format_bytes(int(1.5 * 1024 * 1024)) == "1.5 MB"


def test_compute_done_summary_reads_file_and_segments(tmp_path: Path) -> None:
    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    output = session / "merged.txt"
    output.write_text("Andrey: hello world\nBoris: greetings friend\n", encoding="utf-8")

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()

    # Pretend SessionMeta is pointing at our scratch session. Force
    # total_min via the openSession code path so the summary's hours-
    # and-minutes string has something to render.
    meta._total_min = 95  # 1 h 35 m
    meta._session_dir = session

    controller = PipelineController(app_model, tracks, meta)
    controller._collected_segments = {
        0: [
            SpeechSegment(start=0, end=1, speaker="Andrey", text="hello world", confidence=None),
        ],
        1: [
            SpeechSegment(start=2, end=3, speaker="Boris", text="greetings friend", confidence=None),
        ],
    }

    summary = controller._compute_done_summary(str(output))

    assert summary["fileSize"].endswith("B") or summary["fileSize"].endswith("KB")
    assert summary["wordCount"] == "6 слов"
    assert summary["cueCount"] == "2 реплик"
    assert summary["sessionLength"] == "1 ч 35 м"


def test_compute_done_summary_missing_file_gives_dashes(tmp_path: Path) -> None:
    _ensure_app()
    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    controller = PipelineController(app_model, tracks, meta)

    summary = controller._compute_done_summary(str(tmp_path / "nowhere.txt"))

    assert summary["fileSize"] == "—"
    assert summary["wordCount"] == "0 слов"


class _StubChunkingPrefs:
    """Minimal stand-in for AppPreferences.build_chunking_options()."""

    def __init__(self, enabled: bool, chunk_chars: int = 40_000, overlap_ratio: float = 0.2) -> None:
        from core.chunking import ChunkingOptions
        self._opts = ChunkingOptions(
            enabled=enabled,
            chunk_chars=chunk_chars,
            overlap_ratio=overlap_ratio,
        )

    def build_chunking_options(self):
        return self._opts

    def build_asr_options(self):  # unused by these tests
        from core.asr import AsrOptions
        return AsrOptions()


def test_maybe_chunk_output_invokes_chunker_when_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    _ensure_app()

    calls: list[dict] = []

    def _fake_chunk(merged_path, **kwargs):
        dest = tmp_path / "chunks"
        dest.mkdir(exist_ok=True)
        calls.append({"merged": merged_path, **kwargs})
        return dest

    monkeypatch.setattr(
        "ui.engines.pipeline_controller.chunk_text_file", _fake_chunk
    )

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    prefs = _StubChunkingPrefs(enabled=True, chunk_chars=30_000, overlap_ratio=0.15)
    controller = PipelineController(app_model, tracks, meta, preferences=prefs)

    merged = tmp_path / "merged.txt"
    merged.write_text("hello", encoding="utf-8")
    controller._maybe_chunk_output(str(merged))

    assert len(calls) == 1
    assert calls[0]["chunk_chars"] == 30_000
    assert calls[0]["overlap_ratio"] == 0.15
    assert controller.chunksDir.endswith("chunks")


def test_maybe_chunk_output_skips_when_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    _ensure_app()

    calls: list = []
    monkeypatch.setattr(
        "ui.engines.pipeline_controller.chunk_text_file",
        lambda *a, **kw: calls.append((a, kw)),
    )

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    prefs = _StubChunkingPrefs(enabled=False)
    controller = PipelineController(app_model, tracks, meta, preferences=prefs)

    controller._maybe_chunk_output(str(tmp_path / "merged.txt"))

    assert calls == []
    assert controller.chunksDir == ""


def test_maybe_chunk_output_swallows_chunker_failures(
    tmp_path: Path, monkeypatch
) -> None:
    _ensure_app()

    def _boom(*a, **kw):
        raise ValueError("merged file is empty")

    monkeypatch.setattr(
        "ui.engines.pipeline_controller.chunk_text_file", _boom
    )

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    prefs = _StubChunkingPrefs(enabled=True)
    controller = PipelineController(app_model, tracks, meta, preferences=prefs)

    # Must not raise — chunker failure is non-fatal (merged.txt is done).
    controller._maybe_chunk_output(str(tmp_path / "merged.txt"))
    assert controller.chunksDir == ""


# ─── feature #5 iteration 5b/2 — saveSpeakerMapEntry ────────────────────


def test_save_speaker_map_entry_writes_canonical_shape(tmp_path: Path) -> None:
    """Writing through the controller produces the new ``characters`` shape."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    meta.openSession(str(session))
    tracks.loadFromDir(str(session))
    controller = PipelineController(app_model, tracks, meta)

    controller.saveSpeakerMapEntry(0, "Alice", "PC", ["Aragorn", "Legolas"])

    data = json.loads((session / "speaker_map.json").read_text(encoding="utf-8"))
    assert "1-alice" in data
    entry = data["1-alice"]
    assert entry["player"] == "Alice"
    assert entry["characters"] == ["Aragorn", "Legolas"]
    assert entry["role"] == "PC"


def test_save_speaker_map_entry_preserves_extras(tmp_path: Path) -> None:
    """Unknown extra fields (notes / tags) survive a save."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")
    _write_speaker_map(session, {
        "1-alice": {
            "player": "Alice",
            "characters": ["Aragorn"],
            "role": "PC",
            "notes": "tends to mumble",
            "color": "#ff8800",
        },
    })

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    meta.openSession(str(session))
    tracks.loadFromDir(str(session))
    controller = PipelineController(app_model, tracks, meta)

    controller.saveSpeakerMapEntry(0, "Alice", "PC", ["Aragorn", "Legolas"])

    data = json.loads((session / "speaker_map.json").read_text(encoding="utf-8"))
    entry = data["1-alice"]
    assert entry["notes"] == "tends to mumble"
    assert entry["color"] == "#ff8800"
    assert entry["characters"] == ["Aragorn", "Legolas"]


def test_save_speaker_map_entry_updates_model_in_place(tmp_path: Path) -> None:
    """The model row reflects the new values without a reload."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    meta.openSession(str(session))
    tracks.loadFromDir(str(session))
    controller = PipelineController(app_model, tracks, meta)

    controller.saveSpeakerMapEntry(0, "Alice", "PC", ["Aragorn"])

    name = tracks.data(tracks.index(0), _TLM.NameRole)
    role = tracks.data(tracks.index(0), _TLM.RoleRole)
    chars = tracks.data(tracks.index(0), _TLM.CharactersRole)
    assert name == "Alice"
    assert role == "Игрок"
    assert chars == ["Aragorn"]


def test_save_speaker_map_entry_filters_empty_characters(tmp_path: Path) -> None:
    """Empty / whitespace-only character names are dropped before write."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    meta.openSession(str(session))
    tracks.loadFromDir(str(session))
    controller = PipelineController(app_model, tracks, meta)

    controller.saveSpeakerMapEntry(
        0, "Alice", "PC", ["Aragorn", "", "  ", "Legolas"]
    )

    data = json.loads((session / "speaker_map.json").read_text(encoding="utf-8"))
    assert data["1-alice"]["characters"] == ["Aragorn", "Legolas"]


def test_save_speaker_map_entry_no_session_logs_and_skips(
    tmp_path: Path, caplog
) -> None:
    """Saving with no session attached is a no-op + warning, never a crash."""

    _ensure_app()

    app_model = AppModel()
    tracks = TrackListModel()
    controller = PipelineController(app_model, tracks, session_meta=None)

    controller.saveSpeakerMapEntry(0, "Alice", "PC", ["Aragorn"])
    assert not (tmp_path / "speaker_map.json").exists()


# ─── reviewer follow-up: renamePlayer routes through speaker_map.json ───


def test_rename_player_persists_to_speaker_map(tmp_path: Path) -> None:
    """Inline player rename writes to speaker_map.json so it survives reload."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")
    _write_speaker_map(session, {
        "1-alice": {
            "player": "Alice",
            "characters": ["Aragorn", "Legolas"],
            "role": "PC",
            "notes": "keep me",
        },
    })

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    meta.openSession(str(session))
    tracks.loadFromDir(str(session))
    controller = PipelineController(app_model, tracks, meta)

    controller.renamePlayer(0, "Alice The Bold")

    data = json.loads((session / "speaker_map.json").read_text(encoding="utf-8"))
    entry = data["1-alice"]
    assert entry["player"] == "Alice The Bold"
    # Characters / role / extras are preserved verbatim.
    assert entry["characters"] == ["Aragorn", "Legolas"]
    assert entry["role"] == "PC"
    assert entry["notes"] == "keep me"

    # Model row reflects the new name in-place.
    name = tracks.data(tracks.index(0), _TLM.NameRole)
    assert name == "Alice The Bold"


def test_rename_player_preserves_listener_role(tmp_path: Path) -> None:
    """Renaming a Слушатель row keeps the listener role on disk."""

    _ensure_app()

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-listener.flac")
    _write_speaker_map(session, {
        "1-listener": {"player": "Lurker", "characters": [], "role": "Слушатель"},
    })

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    meta.openSession(str(session))
    tracks.loadFromDir(str(session))
    controller = PipelineController(app_model, tracks, meta)

    # Sanity: load-side mapped to listener + excluded.
    assert tracks.data(tracks.index(0), _TLM.RoleRole) == "Слушатель"
    assert tracks.data(tracks.index(0), _TLM.ExcludedRole) is True

    controller.renamePlayer(0, "Quiet One")

    data = json.loads((session / "speaker_map.json").read_text(encoding="utf-8"))
    entry = data["1-listener"]
    assert entry["player"] == "Quiet One"
    assert entry["role"] == "Слушатель"


def test_rename_player_out_of_range_no_op(
    tmp_path: Path, monkeypatch
) -> None:
    """An out-of-range row index neither crashes nor writes anything."""

    _ensure_app()

    # Sandbox the legacy-migration project root so loadFromDir can't
    # silently copy the repo's real speaker_map.json into our scratch
    # session and break the "no file" assertion below.
    from core import speaker_map as core_speaker_map
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    monkeypatch.setattr(core_speaker_map, "_project_root", lambda: fake_root)

    session = tmp_path / "sess"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")

    app_model = AppModel()
    tracks = TrackListModel()
    meta = SessionMeta()
    meta.openSession(str(session))
    tracks.loadFromDir(str(session))
    controller = PipelineController(app_model, tracks, meta)

    # Capture the speaker_map state (if any) before the rename — the
    # test asserts that an out-of-range rename does not mutate it.
    before = (
        (session / "speaker_map.json").read_text(encoding="utf-8")
        if (session / "speaker_map.json").exists() else None
    )
    controller.renamePlayer(99, "Nobody")
    after = (
        (session / "speaker_map.json").read_text(encoding="utf-8")
        if (session / "speaker_map.json").exists() else None
    )
    assert before == after


def test_speaker_map_reaches_make_source(tmp_path: Path, monkeypatch) -> None:
    """The GUI path must hand the speaker map to the ASR backend.

    Every backend resolves ``SpeechSegment.speaker`` from the audio
    stem inside ``transcribe_track``. Built without a map, a source
    labels every line "1-v_vladimir" and nothing downstream can
    recover the player — which is what merged.txt looked like before
    this wiring landed. The CLI path (``core.pipeline``) always passed
    it; the Qt shell did not.
    """

    _ensure_app()

    session = tmp_path / "session"
    session.mkdir()
    _write_flac_stub(session / "1-vova.flac")
    _write_speaker_map(session, {
        "1-vova": {"player": "Вова", "characters": [], "role": "GM"},
    })

    captured: dict[str, object] = {}

    def _fake_make_source(model_id, *, options=None, speaker_map=None):
        captured["model_id"] = model_id
        captured["speaker_map"] = speaker_map
        return object()

    monkeypatch.setattr(
        "ui.engines.pipeline_controller.make_source", _fake_make_source
    )

    meta = SessionMeta()
    tracks = TrackListModel()
    controller = PipelineController(AppModel(), tracks, meta)
    meta.openSession(session.as_uri())

    controller._get_or_make_source("gigaam")

    assert captured["speaker_map"], (
        "make_source was called without a speaker map — merged.txt would "
        "carry raw audio stems instead of player names"
    )
    assert captured["speaker_map"].get("1-vova") == "Вова", captured["speaker_map"]


def test_speaker_map_absent_session_is_not_fatal(monkeypatch) -> None:
    """No open session → empty map, not a crash.

    ``make_source`` treats an empty mapping as "no mapping" and falls
    back to the stem, which is the pre-existing behaviour.
    """

    _ensure_app()

    captured: dict[str, object] = {}

    def _fake_make_source(model_id, *, options=None, speaker_map=None):
        captured["speaker_map"] = speaker_map
        return object()

    monkeypatch.setattr(
        "ui.engines.pipeline_controller.make_source", _fake_make_source
    )

    controller = PipelineController(AppModel(), TrackListModel(), SessionMeta())
    controller._get_or_make_source("gigaam")

    assert captured["speaker_map"] == {}


class _RegistryStub:
    """Minimal stand-in for ModelRegistry's pre-flight surface."""

    def __init__(self, any_installed: bool) -> None:
        self.anyInstalled = any_installed
        self.activeModelId = "gigaam"


def test_run_without_a_model_explains_itself(tmp_path: Path) -> None:
    """No model installed → one sentence, not six stack traces.

    Every track used to fail separately with a developer-facing
    RuntimeError ("GigaAM-v3 model is not installed. Run installer or
    GigaAMSource().install(params)"), which is what a first-time user
    saw after dropping their first folder.
    """

    _ensure_app()

    session = tmp_path / "session"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")
    _write_flac_stub(session / "2-bob.flac")

    app_model = AppModel()
    meta = SessionMeta()
    tracks = TrackListModel()
    controller = PipelineController(
        app_model, tracks, meta, _RegistryStub(any_installed=False)
    )
    meta.openSession(session.as_uri())

    controller.runAsr()

    message = app_model.errorMessage
    assert message, "a missing model must surface a message"
    assert "Модели" in message, message
    assert "RuntimeError" not in message and "install(" not in message, (
        f"developer-facing text leaked to the user: {message}"
    )
    assert app_model.phase != "asr", "must not start ASR without a model"


def test_guard_passes_when_a_model_is_installed(tmp_path: Path) -> None:
    """The guard must not block the normal path.

    Stops at the guard rather than letting ``runAsr`` spawn a worker —
    starting real ASR here would go looking for model weights.
    """

    _ensure_app()

    session = tmp_path / "session"
    session.mkdir()
    _write_flac_stub(session / "1-alice.flac")

    app_model = AppModel()
    meta = SessionMeta()
    tracks = TrackListModel()
    controller = PipelineController(
        app_model, tracks, meta, _RegistryStub(any_installed=True)
    )
    meta.openSession(session.as_uri())

    # Every track excluded, and the merge spawn stubbed out: the guard
    # is then the only thing that could refuse, and it must not.
    # Letting a real merge thread start would leave a live QThread
    # behind and hang the test session.
    for row in range(tracks.rowCount()):
        tracks.updateSpeakerMapRow(row, "Alice", "Слушатель", [])
    spawned: list[bool] = []
    controller._spawn_merger = lambda: spawned.append(True)  # type: ignore[method-assign]

    controller.runAsr()

    assert app_model.errorMessage == "", app_model.errorMessage
    assert spawned == [True], "the guard swallowed a run it should have allowed"
