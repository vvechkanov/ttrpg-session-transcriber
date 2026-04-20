"""Background worker for blocking ``core.backend_installers`` calls.

``install_backend`` / ``uninstall_backend`` download hundreds of
megabytes and must not run on the UI thread — the docstring of
``core.backend_installers.install_backend`` even says so. This module
wraps them in the ``QObject + moveToThread(QThread)`` pattern the
handoff recommends (``docs/handoff/QML_MAPPING.md`` §Threading).

Typical use from :class:`ui.models.model_registry.ModelRegistry`::

    worker = InstallWorker(backend_id, "install")
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(self._on_install_progress)
    worker.done.connect(self._on_install_done)
    worker.done.connect(thread.quit)
    worker.error.connect(self._on_install_error)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()

The caller keeps a strong reference to ``thread`` and ``worker`` until
``QThread.finished`` fires, otherwise the GC may tear them down
mid-run.
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QObject, Signal, Slot

from core.backend_installers import (
    BackendId,
    install_backend,
    uninstall_backend,
)


Action = Literal["install", "uninstall"]


class InstallWorker(QObject):
    """One-shot installer/uninstaller. Emit once, terminate."""

    #: Percent 0..100 progress during install. Never emitted for uninstall.
    progress = Signal(int, str)

    #: Finished successfully — carries the target BackendId as plain string
    #: so QML can bind to it.
    done = Signal(str)

    #: Finished with an error — carries a human-readable message.
    error = Signal(str)

    def __init__(self, backend_id: BackendId, action: Action) -> None:
        super().__init__()
        self._backend_id = backend_id
        self._action: Action = action

    @Slot()
    def run(self) -> None:
        try:
            if self._action == "install":
                def on_progress(fraction: float, message: str) -> None:
                    # ``core.backend_installers`` invokes its callback
                    # as ``(fraction_0_to_1, human_readable_message)``
                    # (see ``sources.base.InstallProgress``). Throttling
                    # is our concern — the source may call often.
                    pct = max(0, min(100, int(fraction * 100)))
                    self.progress.emit(pct, message)

                install_backend(self._backend_id, progress=on_progress)
            else:
                uninstall_backend(self._backend_id)
            self.done.emit(self._backend_id.value)
        except Exception as exc:  # noqa: BLE001 — surface any failure to UI
            self.error.emit(str(exc))
