"""Tests for :mod:`core.recent_sessions` and :mod:`core.onboarding_state`.

Pure stdlib coverage — no Qt, no UI imports. ``config_dir`` is
monkeypatched to point at ``tmp_path`` so tests never touch the real
per-user config directory on the host.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import onboarding_state, recent_sessions
from core.recent_sessions import (
    MAX_RECENT,
    RecentSession,
    add_recent,
    clear_recent,
    load_recent,
)


@pytest.fixture
def cfg_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect both modules' ``config_dir`` to ``tmp_path/config``.

    Both modules are patched to the same lambda so their files end up
    side-by-side, just like in production.
    """
    target = tmp_path / "config"
    target.mkdir()
    monkeypatch.setattr(recent_sessions, "config_dir", lambda: target)
    # onboarding_state imports ``config_dir`` by name; patching the
    # attribute on that module is what actually takes effect there.
    monkeypatch.setattr(onboarding_state, "config_dir", lambda: target)
    return target


def _make_session(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name
    d.mkdir()
    return d


# ── load_recent / add_recent ───────────────────────────────────────────


class TestLoadRecent:
    def test_missing_file_returns_empty(self, cfg_dir: Path):
        assert load_recent() == ()

    def test_corrupt_json_returns_empty(self, cfg_dir: Path):
        (cfg_dir / "recent_sessions.json").write_text(
            "not-json-at-all{", encoding="utf-8"
        )
        assert load_recent() == ()

    def test_skips_missing_paths(self, cfg_dir: Path, tmp_path: Path):
        alive = _make_session(tmp_path, "alive-session")
        dead = tmp_path / "gone"  # never created

        payload = {
            "sessions": [
                {"path": str(alive), "opened_at": 100.0},
                {"path": str(dead), "opened_at": 200.0},
            ]
        }
        (cfg_dir / "recent_sessions.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        got = load_recent()
        assert len(got) == 1
        assert got[0].path == alive

    def test_wrong_top_level_shape_returns_empty(self, cfg_dir: Path):
        (cfg_dir / "recent_sessions.json").write_text(
            json.dumps(["just", "a", "list"]), encoding="utf-8"
        )
        assert load_recent() == ()


class TestAddRecent:
    def test_creates_file_on_first_call(
        self, cfg_dir: Path, tmp_path: Path
    ):
        target = cfg_dir / "recent_sessions.json"
        assert not target.exists()

        session = _make_session(tmp_path, "session-1")
        result = add_recent(session)

        assert target.exists()
        assert len(result) == 1
        assert result[0].path == session.resolve()

    def test_dedupes_same_path(self, cfg_dir: Path, tmp_path: Path):
        session = _make_session(tmp_path, "session-1")
        add_recent(session)
        second = add_recent(session)

        assert len(second) == 1
        assert second[0].path == session.resolve()

    def test_caps_at_max_recent(self, cfg_dir: Path, tmp_path: Path):
        # Add MAX_RECENT + 2 distinct sessions; oldest two should fall off.
        created = [
            _make_session(tmp_path, f"session-{i}")
            for i in range(MAX_RECENT + 2)
        ]
        for s in created:
            add_recent(s)

        result = load_recent()
        assert len(result) == MAX_RECENT
        # Newest first: last two created are at the top, oldest two are gone.
        top_paths = [r.path for r in result]
        assert top_paths[0] == created[-1].resolve()
        assert top_paths[1] == created[-2].resolve()
        dropped = [created[0].resolve(), created[1].resolve()]
        for p in dropped:
            assert p not in top_paths

    def test_newest_is_first(self, cfg_dir: Path, tmp_path: Path):
        a = _make_session(tmp_path, "a")
        b = _make_session(tmp_path, "b")
        add_recent(a)
        result = add_recent(b)
        assert [r.path for r in result] == [b.resolve(), a.resolve()]


class TestClearRecent:
    def test_wipes_file(self, cfg_dir: Path, tmp_path: Path):
        session = _make_session(tmp_path, "session-1")
        add_recent(session)
        path = cfg_dir / "recent_sessions.json"
        assert path.exists()

        clear_recent()

        assert not path.exists()
        assert load_recent() == ()

    def test_clear_on_missing_file_is_noop(self, cfg_dir: Path):
        # No file yet; should not raise.
        clear_recent()
        assert load_recent() == ()


# ── RecentSession dataclass ────────────────────────────────────────────


class TestRecentSessionDataclass:
    def test_is_frozen(self, tmp_path: Path):
        s = RecentSession(path=tmp_path, opened_at=123.0)
        with pytest.raises(Exception):  # FrozenInstanceError
            s.path = tmp_path / "other"  # type: ignore[misc]


# ── onboarding_state ───────────────────────────────────────────────────


class TestOnboardingState:
    def test_first_run_on_missing_file(self, cfg_dir: Path):
        assert onboarding_state.is_first_run() is True

    def test_mark_onboarded_flips_flag(self, cfg_dir: Path):
        assert onboarding_state.is_first_run() is True
        onboarding_state.mark_onboarded()
        assert onboarding_state.is_first_run() is False

    def test_corrupt_flag_file_counts_as_first_run(self, cfg_dir: Path):
        (cfg_dir / "onboarding_state.json").write_text(
            "{{not-json", encoding="utf-8"
        )
        assert onboarding_state.is_first_run() is True

    def test_clear_recent_does_not_reset_flag(self, cfg_dir: Path):
        onboarding_state.mark_onboarded()
        clear_recent()
        assert onboarding_state.is_first_run() is False
