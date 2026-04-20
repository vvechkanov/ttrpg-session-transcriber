"""List model for ASR models shown on the Models screen.

Sources its rows from :mod:`core.backend_installers` (installable,
installed-ness, sizes) and enriches them with UI-editorial metadata
(vendor brand, subjective speed label, accuracy score) that lives in
the UI layer — these are presentation concerns, not install facts.

Install / uninstall / active-toggle run through :class:`InstallWorker`
on a :class:`QThread` per handoff § Threading; ``ModelRegistry`` owns
the worker lifetime so QML can stay oblivious to threading.

Persistence of the currently-active backend is in ``QSettings``
(``IniFormat`` → ``%APPDATA%/ttrpg-transcriber/settings.ini``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QSettings,
    QThread,
    Qt,
    Signal,
    Slot,
)

from core.backend_installers import (
    BACKENDS,
    BackendId,
    BackendInfo,
    installed_size_bytes,
    is_backend_installed,
    list_backends,
    models_root_path,
)
from ui.engines.install_worker import InstallWorker


_SETTINGS_KEY_ACTIVE = "models/active_backend"
_SETTINGS_DEFAULT_ACTIVE = BackendId.GIGAAM_RNNT_FP32


#: ModelRegistry enum → ``core.asr.make_source`` string id.
#:
#: ModelRegistry speaks install semantics (enum rows in a table),
#: whereas the ASR dispatcher in ``core.asr`` takes the lowercase
#: string ids that also live in ``TrackListModel.ModelIdRole``. This
#: dict is the one place that maps between the two vocabularies, so
#: :meth:`ModelRegistry.activeModelId` can tell the pipeline which
#: model to instantiate for tracks that have no per-row override.
_BACKEND_TO_ASR_ID: dict[BackendId, str] = {
    BackendId.GIGAAM_RNNT_FP32:           "gigaam",
    BackendId.FASTER_WHISPER_LARGE_V3_RU: "faster-whisper",
}


@dataclass(frozen=True)
class _Presentation:
    """UI-editorial metadata per backend.

    Vendor branding and subjective speed/accuracy labels live in the
    UI layer because they are presentation concerns. Core
    (``BackendInfo``) stays limited to install-time facts (size,
    description, default-selected).
    """

    vendor: str
    lang: str
    accuracy: int       # 0..100 — editorial ranking
    speed_label: str    # "очень быстро" / "быстро" / "средне" / "медленно"


_PRESENTATION: dict[BackendId, _Presentation] = {
    BackendId.GIGAAM_RNNT_FP32: _Presentation(
        vendor="Salute",
        lang="RU",
        accuracy=98,
        speed_label="быстро",
    ),
    BackendId.FASTER_WHISPER_LARGE_V3_RU: _Presentation(
        vendor="OpenAI + CTranslate2",
        lang="RU/EN/мульти.",
        accuracy=97,
        speed_label="медленно",
    ),
}


@dataclass
class ModelEntry:
    backend_id: BackendId
    name: str
    vendor: str
    size: str
    lang: str
    accuracy: int
    speed: str
    installed: bool
    active: bool


def _format_size(size_bytes: int) -> str:
    """Format bytes as "420 MB" or "3.1 GB" for the list view."""

    if size_bytes <= 0:
        return "—"
    mb = size_bytes / 1_000_000
    if mb < 1000:
        return f"{int(round(mb))} MB"
    gb = size_bytes / 1_000_000_000
    # One decimal under 10 GB, none above.
    return f"{gb:.1f} GB" if gb < 10 else f"{int(round(gb))} GB"


class ModelRegistry(QAbstractListModel):
    NameRole      = Qt.ItemDataRole.UserRole + 1
    VendorRole    = Qt.ItemDataRole.UserRole + 2
    SizeRole      = Qt.ItemDataRole.UserRole + 3
    LangRole      = Qt.ItemDataRole.UserRole + 4
    AccuracyRole  = Qt.ItemDataRole.UserRole + 5
    SpeedRole     = Qt.ItemDataRole.UserRole + 6
    InstalledRole = Qt.ItemDataRole.UserRole + 7
    ActiveRole    = Qt.ItemDataRole.UserRole + 8

    _ROLES: dict[int, bytes] = {
        NameRole:      b"name",
        VendorRole:    b"vendor",
        SizeRole:      b"size",
        LangRole:      b"lang",
        AccuracyRole:  b"accuracy",
        SpeedRole:     b"speed",
        InstalledRole: b"installed",
        ActiveRole:    b"active",
    }

    #: Emitted while an install is running — (row_index, pct_0_to_100, msg).
    installProgress = Signal(int, int, str)

    #: Emitted when an install or uninstall finishes successfully — row_index.
    installFinished = Signal(int)

    #: Emitted when an install or uninstall fails — (row_index, message).
    installFailed = Signal(int, str)

    #: Fires whenever the set of installed rows changes — install /
    #: uninstall finished, QSettings setActive applied. QML binds to
    #: installedCount / installedSizeLabel through this notify so the
    #: bottom-of-screen "Занято на диске" label re-evaluates after a
    #: worker completes (plain Slot-only would cache the first call).
    installedStateChanged = Signal()

    #: Fires when the user picks a new active backend (or the
    #: registry promotes one because the QSettings default was
    #: uninstalled). ``activeModelId`` bindings in QML and the
    #: pipeline refresh on this signal.
    activeModelIdChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._settings = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            "Session Transcriber",
            "Session Transcriber",
        )
        self._active_id = self._load_active_id()

        # Strong refs for the one-at-a-time install worker. QML never sees
        # these — the registry emits flattened installProgress / Finished
        # / Failed signals carrying the target row index.
        self._install_thread: QThread | None = None
        self._install_worker: InstallWorker | None = None
        self._install_row: int = -1

        self._rows: list[ModelEntry] = self._build_rows()

    # ── QAbstractListModel ────────────────────────────────────────────
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        match role:
            case ModelRegistry.NameRole:      return row.name
            case ModelRegistry.VendorRole:    return row.vendor
            case ModelRegistry.SizeRole:      return row.size
            case ModelRegistry.LangRole:      return row.lang
            case ModelRegistry.AccuracyRole:  return row.accuracy
            case ModelRegistry.SpeedRole:     return row.speed
            case ModelRegistry.InstalledRole: return row.installed
            case ModelRegistry.ActiveRole:    return row.active
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name) for role, name in self._ROLES.items()}

    # ── Slots exposed to QML ──────────────────────────────────────────
    @Slot(int, result="QVariant")
    def entryAt(self, row: int) -> dict[str, Any] | None:
        """Snapshot a row as a QVariantMap for the drawer."""

        if not (0 <= row < len(self._rows)):
            return None
        e = self._rows[row]
        return {
            "backend_id": e.backend_id.value,
            "name":       e.name,
            "vendor":     e.vendor,
            "size":       e.size,
            "lang":       e.lang,
            "accuracy":   e.accuracy,
            "speed":      e.speed,
            "installed":  e.installed,
            "active":     e.active,
        }

    @Slot(int)
    def setActive(self, row: int) -> None:
        """Mark the row as the active backend. Synchronous, cheap."""

        if not (0 <= row < len(self._rows)):
            return
        target = self._rows[row]
        if not target.installed or target.active:
            return
        self._active_id = target.backend_id
        self._settings.setValue(_SETTINGS_KEY_ACTIVE, target.backend_id.value)
        self._settings.sync()
        self._rebuild_and_reset()
        self.activeModelIdChanged.emit()

    @Property(str, notify=activeModelIdChanged)
    def activeModelId(self) -> str:
        """ASR model id for the currently-active backend.

        Returns the same lowercase identifiers that
        ``core.asr.make_source`` accepts — ``"gigaam"`` or
        ``"faster-whisper"`` for the two bundled backends. The
        pipeline reads this when a track has no explicit override so
        that the Models screen's "active" flag actually drives ASR.
        """

        return _BACKEND_TO_ASR_ID.get(self._active_id, "gigaam")

    @Slot(int)
    def install(self, row: int) -> None:
        """Kick off an install worker for ``row``. No-op if already running."""

        if self._install_thread is not None or not (0 <= row < len(self._rows)):
            return
        entry = self._rows[row]
        if entry.installed:
            return
        self._start_worker(row, entry.backend_id, "install")

    @Slot(int)
    def uninstall(self, row: int) -> None:
        """Kick off an uninstall worker for ``row``. No-op if already running."""

        if self._install_thread is not None or not (0 <= row < len(self._rows)):
            return
        entry = self._rows[row]
        if not entry.installed:
            return
        self._start_worker(row, entry.backend_id, "uninstall")

    @Slot()
    def refresh(self) -> None:
        """Re-read install state from core. Call after out-of-band changes."""

        self._rebuild_and_reset()

    @Slot(result=str)
    def modelsRoot(self) -> str:
        """Absolute path to the directory where backends are installed.

        Returns ``""`` if the directory does not exist yet (first run,
        no backend ever installed). QML uses this to open the folder
        in the OS file manager — a missing directory can't be opened.
        """

        root = models_root_path()
        return str(root) if root.exists() else ""

    @Property(int, notify=installedStateChanged)
    def installedCount(self) -> int:
        """Number of rows that are actually on disk."""

        return sum(1 for r in self._rows if r.installed)

    @Property(str, notify=installedStateChanged)
    def installedSizeLabel(self) -> str:
        """Human-readable total size across installed backends."""

        total = 0
        for info in list_backends():
            if is_backend_installed(info.id):
                total += installed_size_bytes(info.id)
        return _format_size(total)

    # ── Internal ──────────────────────────────────────────────────────
    def _build_rows(self) -> list[ModelEntry]:
        rows: list[ModelEntry] = []
        for info in list_backends():
            rows.append(self._row_from(info))

        # Only keep the active flag on a row that's actually installed.
        # Otherwise the table renders "активна" next to "Установить",
        # which reads as a contradiction. If the QSettings default
        # points at an uninstalled model, promote the first installed
        # row instead (still deterministic, since list_backends() is
        # a fixed order).
        active_rows = [r for r in rows if r.active and r.installed]
        if not active_rows:
            for r in rows:
                if r.installed:
                    rows = [
                        ModelEntry(**{**r.__dict__, "active": True})
                        if entry is r
                        else ModelEntry(**{**entry.__dict__, "active": False})
                        for entry in rows
                    ]
                    self._active_id = r.backend_id
                    break
            else:
                # No backend installed at all — clear active.
                rows = [
                    ModelEntry(**{**entry.__dict__, "active": False})
                    for entry in rows
                ]
        return rows

    def _row_from(self, info: BackendInfo) -> ModelEntry:
        pres = _PRESENTATION.get(info.id)
        installed = is_backend_installed(info.id)
        size_bytes = installed_size_bytes(info.id) if installed else info.approx_download_bytes
        return ModelEntry(
            backend_id=info.id,
            name=info.title,
            vendor=pres.vendor if pres else "—",
            size=_format_size(size_bytes),
            lang=pres.lang if pres else "—",
            accuracy=pres.accuracy if pres else 0,
            speed=pres.speed_label if pres else "—",
            installed=installed,
            active=(info.id == self._active_id),
        )

    def _rebuild_and_reset(self) -> None:
        prior_active = self._active_id
        self.beginResetModel()
        self._rows = self._build_rows()
        self.endResetModel()
        # Notify QML-bound Q_PROPERTY aggregates (installedCount,
        # installedSizeLabel) so the bottom-of-screen label refreshes
        # after an install/uninstall finishes.
        self.installedStateChanged.emit()
        # ``_build_rows`` can promote a different backend to active
        # when the QSettings default is uninstalled. Surface that
        # shift so bindings on ``activeModelId`` refresh.
        if self._active_id != prior_active:
            self.activeModelIdChanged.emit()

    def _load_active_id(self) -> BackendId:
        raw = self._settings.value(_SETTINGS_KEY_ACTIVE, _SETTINGS_DEFAULT_ACTIVE.value)
        try:
            return BackendId(str(raw))
        except ValueError:
            return _SETTINGS_DEFAULT_ACTIVE

    def _start_worker(self, row: int, backend_id: BackendId, action: str) -> None:
        thread = QThread()
        worker = InstallWorker(backend_id, action)  # type: ignore[arg-type]
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_worker_progress)
        worker.done.connect(self._on_worker_done)
        worker.error.connect(self._on_worker_error)
        worker.done.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._install_thread = thread
        self._install_worker = worker
        self._install_row = row

        thread.start()

    @Slot(int, str)
    def _on_worker_progress(self, pct: int, message: str) -> None:
        if self._install_row >= 0:
            self.installProgress.emit(self._install_row, pct, message)

    @Slot(str)
    def _on_worker_done(self, backend_id_value: str) -> None:
        finished_row = self._install_row
        self._rebuild_and_reset()
        if finished_row >= 0:
            self.installFinished.emit(finished_row)

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        failed_row = self._install_row
        if failed_row >= 0:
            self.installFailed.emit(failed_row, message)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._install_thread = None
        self._install_worker = None
        self._install_row = -1
