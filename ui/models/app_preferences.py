"""Global user preferences backed by ``QSettings(IniFormat)``.

Persisted to ``%APPDATA%/Session Transcriber/Session Transcriber.ini``
on Windows (and the OS-appropriate path elsewhere). Exposed to QML as
the ``preferences`` context property; forms in ``SettingsScreen.qml``
bind directly to these Q_PROPERTY fields and changes save on
``sync()`` which the setters invoke eagerly — no Cancel/Save round-trip,
the handoff screen has no such buttons.

Keys grouped by section:

* ``paths/working_folder``   — base dir for session folders + cache
* ``merger/max_gap``         — free-form seconds (string so the
                               TextField doesn't round-trip via float)
* ``merger/ooc_mode``        — "skip" | "italic" | "include"
* ``interface/language``     — "ru" | "en"
* ``interface/show_tooltips`` — bool
* ``interface/sound_on_done`` — bool
* ``devices/default``        — "cuda" | "cpu" | "mps" (hidden in MVP,
                               used when PipelineController spawns ASR
                               workers in Phase 6)
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, Signal


def _default_working_folder() -> str:
    home = Path.home()
    return str(home / "Sessions")


class AppPreferences(QObject):
    """QObject wrapper with Q_PROPERTY per preference + QSettings persistence.

    Every setter calls ``QSettings.sync()`` so an unexpected crash
    never loses a just-toggled checkbox. QSettings caches writes,
    ``sync()`` flushes — cheap for small INI files.
    """

    workingFolderChanged = Signal()
    mergerMaxGapChanged = Signal()
    mergerOocModeChanged = Signal()
    interfaceLanguageChanged = Signal()
    showTooltipsChanged = Signal()
    soundOnDoneChanged = Signal()
    defaultDeviceChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            "Session Transcriber",
            "Session Transcriber",
        )
        # Load with typed defaults — QSettings.value returns ``str`` on
        # round-trip from INI, so we cast bools explicitly.
        self._working_folder: str = str(
            self._settings.value("paths/working_folder", _default_working_folder())
        )
        self._merger_max_gap: str = str(
            self._settings.value("merger/max_gap", "1.0")
        )
        self._merger_ooc_mode: str = str(
            self._settings.value("merger/ooc_mode", "skip")
        )
        self._interface_language: str = str(
            self._settings.value("interface/language", "ru")
        )
        self._show_tooltips: bool = _to_bool(
            self._settings.value("interface/show_tooltips", True)
        )
        self._sound_on_done: bool = _to_bool(
            self._settings.value("interface/sound_on_done", True)
        )
        self._default_device: str = str(
            self._settings.value("devices/default", "cuda")
        )

    # ── workingFolder ────────────────────────────────────────────────
    @Property(str, notify=workingFolderChanged)
    def workingFolder(self) -> str:
        return self._working_folder

    @workingFolder.setter  # type: ignore[no-redef]
    def workingFolder(self, value: str) -> None:
        if value == self._working_folder:
            return
        self._working_folder = value
        self._settings.setValue("paths/working_folder", value)
        self._settings.sync()
        self.workingFolderChanged.emit()

    # ── mergerMaxGap ─────────────────────────────────────────────────
    @Property(str, notify=mergerMaxGapChanged)
    def mergerMaxGap(self) -> str:
        return self._merger_max_gap

    @mergerMaxGap.setter  # type: ignore[no-redef]
    def mergerMaxGap(self, value: str) -> None:
        if value == self._merger_max_gap:
            return
        self._merger_max_gap = value
        self._settings.setValue("merger/max_gap", value)
        self._settings.sync()
        self.mergerMaxGapChanged.emit()

    # ── mergerOocMode ────────────────────────────────────────────────
    @Property(str, notify=mergerOocModeChanged)
    def mergerOocMode(self) -> str:
        return self._merger_ooc_mode

    @mergerOocMode.setter  # type: ignore[no-redef]
    def mergerOocMode(self, value: str) -> None:
        if value == self._merger_ooc_mode:
            return
        self._merger_ooc_mode = value
        self._settings.setValue("merger/ooc_mode", value)
        self._settings.sync()
        self.mergerOocModeChanged.emit()

    # ── interfaceLanguage ────────────────────────────────────────────
    @Property(str, notify=interfaceLanguageChanged)
    def interfaceLanguage(self) -> str:
        return self._interface_language

    @interfaceLanguage.setter  # type: ignore[no-redef]
    def interfaceLanguage(self, value: str) -> None:
        if value == self._interface_language:
            return
        self._interface_language = value
        self._settings.setValue("interface/language", value)
        self._settings.sync()
        self.interfaceLanguageChanged.emit()

    # ── showTooltips ─────────────────────────────────────────────────
    @Property(bool, notify=showTooltipsChanged)
    def showTooltips(self) -> bool:
        return self._show_tooltips

    @showTooltips.setter  # type: ignore[no-redef]
    def showTooltips(self, value: bool) -> None:
        if value == self._show_tooltips:
            return
        self._show_tooltips = value
        self._settings.setValue("interface/show_tooltips", value)
        self._settings.sync()
        self.showTooltipsChanged.emit()

    # ── soundOnDone ──────────────────────────────────────────────────
    @Property(bool, notify=soundOnDoneChanged)
    def soundOnDone(self) -> bool:
        return self._sound_on_done

    @soundOnDone.setter  # type: ignore[no-redef]
    def soundOnDone(self, value: bool) -> None:
        if value == self._sound_on_done:
            return
        self._sound_on_done = value
        self._settings.setValue("interface/sound_on_done", value)
        self._settings.sync()
        self.soundOnDoneChanged.emit()

    # ── defaultDevice ────────────────────────────────────────────────
    @Property(str, notify=defaultDeviceChanged)
    def defaultDevice(self) -> str:
        return self._default_device

    @defaultDevice.setter  # type: ignore[no-redef]
    def defaultDevice(self, value: str) -> None:
        if value == self._default_device:
            return
        self._default_device = value
        self._settings.setValue("devices/default", value)
        self._settings.sync()
        self.defaultDeviceChanged.emit()


def _to_bool(raw: object) -> bool:
    """Coerce a QSettings-returned value to bool.

    QSettings round-trips booleans through INI as the strings "true" /
    "false". First-boot (before the key is written) returns the Python
    default we pass in, which may already be a bool — handle both.
    """

    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "1", "yes", "on"}
