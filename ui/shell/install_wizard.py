"""In-process backend install wizard for the PySide6 shell.

When the runtime ``session-transcriber.exe`` detects that a requested
ASR backend is not installed (e.g. the user switched from GigaAM to
faster-whisper in the settings drawer after the initial install, or
manually deleted the backend directory), it shows
:class:`InstallWizardDialog`. The dialog runs
:func:`core.backend_installers.install_backend` on a background
:class:`QThread` and streams progress into a progress bar + status
label. On success it returns ``QDialog.Accepted``.

This is the PySide6 port of the tkinter ``_show_install_modal`` flow
in :mod:`ui.gui_legacy`. No network code lives here — that stays in
``sources/speech/_bundle_download.py``; the wizard is just a thin
UI wrapper that respects Epic A tracked-install invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

# Epic A shim — resolved lazily inside the worker thread so the import
# cycle that ``sources/__init__.py`` still has does not fire at
# module-import time. See
# ``tests/test_e2e_tier2_semantic.py`` for the same defensive pattern.
from core.backend_installers import BackendId, BACKENDS


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ProgressEvent:
    fraction: float  # 0.0 – 1.0; negative means "error"
    message: str


class _InstallWorker(QObject):
    """QObject running on a secondary thread; calls ``install_backend``.

    We deliberately do not subclass ``QThread`` — that lets Qt manage
    thread affinity via ``moveToThread``, which is the recommended
    pattern for PySide6 workers (``Qt for Python`` docs §Threading).
    """

    progress = Signal(float, str)  # fraction 0-1, status message
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, backend_id: BackendId) -> None:
        super().__init__()
        self._backend_id = backend_id

    def run(self) -> None:
        """Thread entry point — blocks until install_backend returns."""
        try:
            from core.backend_installers import install_backend

            def _progress_cb(fraction: float, message: str) -> None:
                self.progress.emit(fraction, message)

            install_backend(self._backend_id, progress=_progress_cb)
        except Exception as exc:  # noqa: BLE001 — surface to user
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit()


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class InstallWizardDialog(QDialog):
    """Modal progress dialog for a single backend install.

    Usage::

        dlg = InstallWizardDialog(BackendId.FASTER_WHISPER_LARGE_V3_RU, parent=self)
        if dlg.exec() == QDialog.Accepted:
            # backend is now installed; proceed
            ...

    The dialog disables its close button while the install is active
    (Epic A installs are atomic — cancelling mid-way is explicitly
    not supported by ``_bundle_download.install_bundle``).
    """

    def __init__(
        self,
        backend_id: BackendId,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend_id = backend_id
        self._info = BACKENDS[backend_id]
        self._done = False
        self._error: str | None = None

        self.setWindowTitle("Установка модели")
        self.setModal(True)
        # Block close button while installing (Epic A atomic install).
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.resize(520, 220)

        self._build_ui()
        self._start_worker()

    # ── UI ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel(self._info.title)
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        size_mb = self._info.approx_download_bytes // 1_000_000
        subtitle = QLabel(
            f"Загрузка ~{size_mb} MB. Пожалуйста, не закрывайте окно."
        )
        subtitle.setStyleSheet("color: #6c7086; font-size: 10px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self._status_label = QLabel("Подготовка...")
        self._status_label.setWordWrap(True)
        self._status_label.setMinimumHeight(36)
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)  # per-mille for smoother UI
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        # Button box — Cancel is disabled while running; OK/Close
        # appears after completion or failure.
        self._buttons = QDialogButtonBox()
        self._close_btn = self._buttons.addButton(
            "Закрыть", QDialogButtonBox.AcceptRole
        )
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self._on_close_clicked)
        layout.addWidget(self._buttons)

    # ── Worker wiring ────────────────────────────────────────────────

    def _start_worker(self) -> None:
        self._thread = QThread(self)
        self._worker = _InstallWorker(self._backend_id)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.failed.connect(self._on_failed)

        # Start the blocking call as soon as the thread is running.
        self._thread.started.connect(self._worker.run)
        # Clean up when the thread finishes (either success or error).
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    # ── Slots ────────────────────────────────────────────────────────

    def _on_progress(self, fraction: float, message: str) -> None:
        if fraction >= 0:
            self._progress_bar.setValue(int(fraction * 1000))
        self._status_label.setText(message)

    def _on_finished_ok(self) -> None:
        self._done = True
        self._progress_bar.setValue(1000)
        self._status_label.setText("Установка завершена.")
        self._close_btn.setEnabled(True)
        # Auto-accept so the caller continues without an extra click.
        self.accept()

    def _on_failed(self, error: str) -> None:
        self._error = error
        self._status_label.setText(f"Ошибка: {error}")
        self._close_btn.setText("Закрыть")
        self._close_btn.setEnabled(True)
        # Re-enable window close so the user is not stuck.
        self.setWindowFlag(Qt.WindowCloseButtonHint, True)
        self.show()  # re-apply flag

    def _on_close_clicked(self) -> None:
        if self._error:
            self.reject()
        else:
            self.accept()

    # Block keyboard Esc while running (matches ``WindowCloseButtonHint`` off).
    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key_Escape and not (self._done or self._error):
            event.ignore()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------

def ensure_backend_installed(
    backend_id: BackendId,
    parent: QWidget | None = None,
) -> bool:
    """Install the backend if needed; return True iff it is now installed.

    Blocks the caller with a modal dialog while the install is
    running. Uses :func:`core.backend_installers.is_backend_installed`
    for the up-front check and :class:`InstallWizardDialog` for the
    install itself.
    """
    from core.backend_installers import is_backend_installed

    if is_backend_installed(backend_id):
        return True

    dlg = InstallWizardDialog(backend_id, parent=parent)
    accepted = dlg.exec() == QDialog.Accepted
    if not accepted:
        return False
    return is_backend_installed(backend_id)
