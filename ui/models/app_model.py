"""Top-level application state exposed to QML.

Holds the currently-visible screen and current session identifier.
Mirrors the prototype's top-level React state:

    { screen: 'timeline' | 'models' | 'settings' | 'empty', ... }

Per-session state (phase, tracks, sources, merger settings) lives on
``SessionModel`` (added in a later slice, not in this foundation step).
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot


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
    mergeProgressChanged = Signal()
    mergeStitchesChanged = Signal()
    doneSummaryChanged = Signal()
    errorMessageChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # First-launch lands on the empty state — there is no real
        # session open yet. Once the user drops a folder and
        # SessionMeta.openSession runs, Main.qml flips this to
        # "timeline" (see the DropArea handler).
        self._screen: str = "empty"
        self._current_session_id: str = ""
        self._phase: str = "idle"
        self._merge_progress: float = 0.0
        # Stitch positions in timeline %. Live-populated while the
        # MergerWorker runs; QML renders one line per entry.
        self._merge_stitches: list[float] = []

        # Done-phase summary numbers. Populated when the pipeline
        # finishes; QML reads them for the DoneSummary banner and the
        # TranscriptPreview stats row.
        self._done_summary: dict[str, str | int] = {}

        # Set by :class:`ui.engines.pipeline_controller.PipelineController`
        # when the merger worker errors out — QML renders a FailedBanner
        # off this string. Cleared on the next ``runAsr`` and on done.
        self._error_message: str = ""

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

    # ── mergeProgress (0..1) ──────────────────────────────────────────
    @Property(float, notify=mergeProgressChanged)
    def mergeProgress(self) -> float:
        return self._merge_progress

    @mergeProgress.setter  # type: ignore[no-redef]
    def mergeProgress(self, value: float) -> None:
        clamped = 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)
        if self._merge_progress == clamped:
            return
        self._merge_progress = clamped
        self.mergeProgressChanged.emit()

    # ── mergeStitches (list of timeline-% positions) ──────────────────
    @Property("QVariantList", notify=mergeStitchesChanged)
    def mergeStitches(self) -> list[float]:
        return list(self._merge_stitches)

    def addStitch(self, position_pct: float) -> None:
        """Append a stitch marker. Not a ``Slot`` — this is Python-only."""

        self._merge_stitches.append(float(position_pct))
        self.mergeStitchesChanged.emit()

    def clearMergeState(self) -> None:
        """Reset merge progress and stitches (called on re-run / cancel)."""

        changed = False
        if self._merge_progress != 0.0:
            self._merge_progress = 0.0
            self.mergeProgressChanged.emit()
            changed = True
        if self._merge_stitches:
            self._merge_stitches = []
            self.mergeStitchesChanged.emit()
            changed = True
        if self._done_summary:
            self._done_summary = {}
            self.doneSummaryChanged.emit()
            changed = True
        return changed

    # ── doneSummary ───────────────────────────────────────────────────
    @Property("QVariantMap", notify=doneSummaryChanged)
    def doneSummary(self) -> dict[str, str | int]:
        """QVariantMap snapshot of final-pipeline stats.

        Keys QML reads:
          durationLabel   — "14 минут 23 секунды" (elapsed)
          statsLine       — secondary mono line for DoneSummary
          fileSize        — "84 KB"
          wordCount       — "12 473 слова"
          cueCount        — "847 реплик"
          sessionLength   — "3 ч 47 м"
        """

        return dict(self._done_summary)

    def setDoneSummary(self, data: dict[str, str | int]) -> None:
        """Assign the summary map. Called from PipelineController on success."""

        if data == self._done_summary:
            return
        self._done_summary = dict(data)
        self.doneSummaryChanged.emit()

    # ── errorMessage (surfaces a merge/pipeline failure to QML) ──────
    @Property(str, notify=errorMessageChanged)
    def errorMessage(self) -> str:
        return self._error_message

    @Slot(str)
    def setErrorMessage(self, message: str) -> None:
        """Set/clear the failure message. Empty string hides the banner.

        Exposed as a ``Slot`` so QML (the FailedBanner's "Скрыть"
        handler) can clear the string directly without a controller
        indirection. Python callers use the same entry point.
        """

        if self._error_message == message:
            return
        self._error_message = message
        self.errorMessageChanged.emit()
