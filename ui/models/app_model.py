"""Top-level application state exposed to QML.

Holds the currently-visible screen and current session identifier.
Mirrors the prototype's top-level React state:

    { screen: 'timeline' | 'models' | 'settings' | 'empty', ... }

Per-session state (phase, tracks, sources, merger settings) lives on
``SessionModel`` (added in a later slice, not in this foundation step).
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal


SCREENS = ("empty", "timeline", "models", "settings")
PHASES  = ("idle", "asr", "merge", "done", "failed")


class AppModel(QObject):
    """Application-wide UI state.

    Exposed to QML as a context property named ``appModel``. QML binds
    to :pyattr:`screen` and calls :pymeth:`setScreen` from nav clicks.
    """

    screenChanged = Signal()
    currentSessionIdChanged = Signal()
    phaseChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # First-launch lands on Timeline to match the prototype's default.
        # The empty-state screen is reached through the Sessions nav item
        # when no session is open (handled inside TimelineScreen later).
        self._screen: str = "timeline"
        self._current_session_id: str = ""
        self._phase: str = "idle"

    # ── screen ────────────────────────────────────────────────────────
    @Property(str, notify=screenChanged)
    def screen(self) -> str:
        return self._screen

    @screen.setter  # type: ignore[no-redef]
    def screen(self, value: str) -> None:
        if value not in SCREENS:
            raise ValueError(f"unknown screen {value!r}; expected one of {SCREENS}")
        if self._screen == value:
            return
        self._screen = value
        self.screenChanged.emit()

    # ── currentSessionId ──────────────────────────────────────────────
    @Property(str, notify=currentSessionIdChanged)
    def currentSessionId(self) -> str:
        return self._current_session_id

    @currentSessionId.setter  # type: ignore[no-redef]
    def currentSessionId(self, value: str) -> None:
        if self._current_session_id == value:
            return
        self._current_session_id = value
        self.currentSessionIdChanged.emit()

    # ── phase ─────────────────────────────────────────────────────────
    @Property(str, notify=phaseChanged)
    def phase(self) -> str:
        return self._phase

    @phase.setter  # type: ignore[no-redef]
    def phase(self, value: str) -> None:
        if value not in PHASES:
            raise ValueError(f"unknown phase {value!r}; expected one of {PHASES}")
        if self._phase == value:
            return
        self._phase = value
        self.phaseChanged.emit()
