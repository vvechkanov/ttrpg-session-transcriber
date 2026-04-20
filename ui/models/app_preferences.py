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
* ``asr/device``             — "cuda" | "cpu"
* ``asr/compute_type``       — faster-whisper compute type
* ``asr/beam_size``          — faster-whisper beam size (string)
* ``asr/language``           — "ru" | "en" | "auto"
* ``asr/gigaam_variant``     — "rnnt" | "e2e_rnnt"
* ``asr/gigaam_precision``   — "fp32" | "int8"
* ``asr/num_threads``        — CPU threads (string)
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, Signal

from core.asr import AsrOptions


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
    asrDeviceChanged = Signal()
    asrComputeTypeChanged = Signal()
    asrBeamSizeChanged = Signal()
    asrLanguageChanged = Signal()
    gigaamVariantChanged = Signal()
    gigaamPrecisionChanged = Signal()
    asrNumThreadsChanged = Signal()

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
        # One-shot migration: fall back to the old ``devices/default``
        # key if ``asr/device`` has never been written. The legacy key
        # is left untouched; first write of ``asrDevice`` seats the new
        # key, after which reads skip the fallback naturally.
        self._asr_device: str = str(
            self._settings.value(
                "asr/device",
                self._settings.value("devices/default", "cuda"),
            )
        )
        self._asr_compute_type: str = str(
            self._settings.value("asr/compute_type", "float16")
        )
        self._asr_beam_size: str = str(
            self._settings.value("asr/beam_size", "5")
        )
        self._asr_language: str = str(
            self._settings.value("asr/language", "ru")
        )
        self._gigaam_variant: str = str(
            self._settings.value("asr/gigaam_variant", "rnnt")
        )
        self._gigaam_precision: str = str(
            self._settings.value("asr/gigaam_precision", "fp32")
        )
        self._asr_num_threads: str = str(
            self._settings.value("asr/num_threads", "4")
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

    # ── asrDevice ────────────────────────────────────────────────────
    @Property(str, notify=asrDeviceChanged)
    def asrDevice(self) -> str:
        return self._asr_device

    @asrDevice.setter  # type: ignore[no-redef]
    def asrDevice(self, value: str) -> None:
        if value == self._asr_device:
            return
        self._asr_device = value
        self._settings.setValue("asr/device", value)
        self._settings.sync()
        self.asrDeviceChanged.emit()

    # ── asrComputeType ───────────────────────────────────────────────
    @Property(str, notify=asrComputeTypeChanged)
    def asrComputeType(self) -> str:
        return self._asr_compute_type

    @asrComputeType.setter  # type: ignore[no-redef]
    def asrComputeType(self, value: str) -> None:
        if value == self._asr_compute_type:
            return
        self._asr_compute_type = value
        self._settings.setValue("asr/compute_type", value)
        self._settings.sync()
        self.asrComputeTypeChanged.emit()

    # ── asrBeamSize ──────────────────────────────────────────────────
    @Property(str, notify=asrBeamSizeChanged)
    def asrBeamSize(self) -> str:
        return self._asr_beam_size

    @asrBeamSize.setter  # type: ignore[no-redef]
    def asrBeamSize(self, value: str) -> None:
        if value == self._asr_beam_size:
            return
        self._asr_beam_size = value
        self._settings.setValue("asr/beam_size", value)
        self._settings.sync()
        self.asrBeamSizeChanged.emit()

    # ── asrLanguage ──────────────────────────────────────────────────
    @Property(str, notify=asrLanguageChanged)
    def asrLanguage(self) -> str:
        return self._asr_language

    @asrLanguage.setter  # type: ignore[no-redef]
    def asrLanguage(self, value: str) -> None:
        if value == self._asr_language:
            return
        self._asr_language = value
        self._settings.setValue("asr/language", value)
        self._settings.sync()
        self.asrLanguageChanged.emit()

    # ── gigaamVariant ────────────────────────────────────────────────
    @Property(str, notify=gigaamVariantChanged)
    def gigaamVariant(self) -> str:
        return self._gigaam_variant

    @gigaamVariant.setter  # type: ignore[no-redef]
    def gigaamVariant(self, value: str) -> None:
        if value == self._gigaam_variant:
            return
        self._gigaam_variant = value
        self._settings.setValue("asr/gigaam_variant", value)
        self._settings.sync()
        self.gigaamVariantChanged.emit()

    # ── gigaamPrecision ──────────────────────────────────────────────
    @Property(str, notify=gigaamPrecisionChanged)
    def gigaamPrecision(self) -> str:
        return self._gigaam_precision

    @gigaamPrecision.setter  # type: ignore[no-redef]
    def gigaamPrecision(self, value: str) -> None:
        if value == self._gigaam_precision:
            return
        self._gigaam_precision = value
        self._settings.setValue("asr/gigaam_precision", value)
        self._settings.sync()
        self.gigaamPrecisionChanged.emit()

    # ── asrNumThreads ────────────────────────────────────────────────
    @Property(str, notify=asrNumThreadsChanged)
    def asrNumThreads(self) -> str:
        return self._asr_num_threads

    @asrNumThreads.setter  # type: ignore[no-redef]
    def asrNumThreads(self, value: str) -> None:
        if value == self._asr_num_threads:
            return
        self._asr_num_threads = value
        self._settings.setValue("asr/num_threads", value)
        self._settings.sync()
        self.asrNumThreadsChanged.emit()

    # ── options builder ──────────────────────────────────────────────
    def build_asr_options(self) -> AsrOptions:
        """Snapshot current preferences into an :class:`AsrOptions`."""

        def _to_int(raw: str, fallback: int) -> int:
            try:
                return int(raw)
            except ValueError:
                return fallback

        return AsrOptions(
            device=self._asr_device,
            compute_type=self._asr_compute_type,
            beam_size=_to_int(self._asr_beam_size, 5),
            language=self._asr_language,
            gigaam_variant=self._gigaam_variant,
            gigaam_precision=self._gigaam_precision,
            num_threads=_to_int(self._asr_num_threads, 4),
        )


def _to_bool(raw: object) -> bool:
    """Coerce a QSettings-returned value to bool.

    QSettings round-trips booleans through INI as the strings "true" /
    "false". First-boot (before the key is written) returns the Python
    default we pass in, which may already be a bool — handle both.
    """

    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "1", "yes", "on"}
