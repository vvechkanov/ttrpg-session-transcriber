"""Integration test: ``AppPreferences`` persists through ``QSettings``.

Uses a scratch organization so we don't stomp the user's real INI,
writes a few keys, constructs a second instance, asserts the values
survived. Run as::

    QT_QPA_PLATFORM=offscreen python tests/ui_qml_smoke/test_app_preferences.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ui.models.app_preferences import AppPreferences, _to_bool  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        sys.stderr.write(f"FAIL: {msg}\n")
        raise SystemExit(1)


def main() -> int:
    # Scratch org/app so we don't touch real user settings. Point
    # QSettings at a temp dir to keep the test hermetic.
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation),
    )

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("Session Transcriber")
    app.setOrganizationName("Session Transcriber")

    # Clear any previous run's leftovers.
    QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "Session Transcriber",
        "Session Transcriber",
    ).clear()

    # _to_bool sanity
    _assert(_to_bool(True) is True, "bool True")
    _assert(_to_bool("true") is True, "str 'true'")
    _assert(_to_bool("false") is False, "str 'false'")
    _assert(_to_bool(0) is False, "int 0")
    _assert(_to_bool("1") is True, "str '1'")

    prefs = AppPreferences()

    # Defaults — Sessions folder in the home dir + all bool-ish true.
    _assert("Sessions" in prefs.workingFolder, f"default folder: {prefs.workingFolder!r}")
    _assert(prefs.mergerMaxGap == "1.0", f"default gap: {prefs.mergerMaxGap!r}")
    _assert(prefs.mergerOocMode == "skip", f"default ooc: {prefs.mergerOocMode!r}")
    _assert(prefs.interfaceLanguage == "ru", f"default lang: {prefs.interfaceLanguage!r}")
    _assert(prefs.showTooltips is True, "default tooltips")
    _assert(prefs.soundOnDone is True, "default sound")
    _assert(prefs.asrDevice == "cuda", f"default device: {prefs.asrDevice!r}")
    _assert(prefs.asrComputeType == "float16", f"default compute: {prefs.asrComputeType!r}")
    _assert(prefs.asrBeamSize == "5", f"default beam: {prefs.asrBeamSize!r}")
    _assert(prefs.asrLanguage == "ru", f"default asr lang: {prefs.asrLanguage!r}")
    _assert(prefs.gigaamVariant == "rnnt", f"default variant: {prefs.gigaamVariant!r}")
    _assert(prefs.gigaamPrecision == "fp32", f"default precision: {prefs.gigaamPrecision!r}")
    _assert(prefs.asrNumThreads == "4", f"default threads: {prefs.asrNumThreads!r}")
    _assert(prefs.chunkingEnabled is False, "default chunking enabled")
    _assert(prefs.chunkingChunkChars == "40000", f"default chunk_chars: {prefs.chunkingChunkChars!r}")
    _assert(prefs.chunkingOverlapRatio == "0.20", f"default overlap: {prefs.chunkingOverlapRatio!r}")

    # Mutate every field.
    prefs.workingFolder = "D:/TTRPG/Sessions"
    prefs.mergerMaxGap = "2.5"
    prefs.mergerOocMode = "italic"
    prefs.interfaceLanguage = "en"
    prefs.showTooltips = False
    prefs.soundOnDone = False
    prefs.asrDevice = "cpu"
    prefs.asrComputeType = "int8"
    prefs.asrBeamSize = "8"
    prefs.asrLanguage = "en"
    prefs.gigaamVariant = "e2e_rnnt"
    prefs.gigaamPrecision = "int8"
    prefs.asrNumThreads = "2"
    prefs.chunkingEnabled = True
    prefs.chunkingChunkChars = "60000"
    prefs.chunkingOverlapRatio = "0.35"

    # A second instance should pick up the persisted values.
    prefs2 = AppPreferences()
    _assert(prefs2.workingFolder == "D:/TTRPG/Sessions", f"round-trip folder: {prefs2.workingFolder!r}")
    _assert(prefs2.mergerMaxGap == "2.5", f"round-trip gap: {prefs2.mergerMaxGap!r}")
    _assert(prefs2.mergerOocMode == "italic", f"round-trip ooc: {prefs2.mergerOocMode!r}")
    _assert(prefs2.interfaceLanguage == "en", f"round-trip lang: {prefs2.interfaceLanguage!r}")
    _assert(prefs2.showTooltips is False, "round-trip tooltips")
    _assert(prefs2.soundOnDone is False, "round-trip sound")
    _assert(prefs2.asrDevice == "cpu", f"round-trip device: {prefs2.asrDevice!r}")
    _assert(prefs2.asrComputeType == "int8", f"round-trip compute: {prefs2.asrComputeType!r}")
    _assert(prefs2.asrBeamSize == "8", f"round-trip beam: {prefs2.asrBeamSize!r}")
    _assert(prefs2.asrLanguage == "en", f"round-trip asr lang: {prefs2.asrLanguage!r}")
    _assert(prefs2.gigaamVariant == "e2e_rnnt", f"round-trip variant: {prefs2.gigaamVariant!r}")
    _assert(prefs2.gigaamPrecision == "int8", f"round-trip precision: {prefs2.gigaamPrecision!r}")
    _assert(prefs2.asrNumThreads == "2", f"round-trip threads: {prefs2.asrNumThreads!r}")
    _assert(prefs2.chunkingEnabled is True, "round-trip chunking enabled")
    _assert(prefs2.chunkingChunkChars == "60000", f"round-trip chunk_chars: {prefs2.chunkingChunkChars!r}")
    _assert(prefs2.chunkingOverlapRatio == "0.35", f"round-trip overlap: {prefs2.chunkingOverlapRatio!r}")

    # build_asr_options snapshot — strings coerced to ints, others pass through.
    opts = prefs2.build_asr_options()
    _assert(opts.device == "cpu", f"opts.device: {opts.device!r}")
    _assert(opts.compute_type == "int8", f"opts.compute_type: {opts.compute_type!r}")
    _assert(opts.beam_size == 8, f"opts.beam_size: {opts.beam_size!r}")
    _assert(opts.language == "en", f"opts.language: {opts.language!r}")
    _assert(opts.gigaam_variant == "e2e_rnnt", f"opts.gigaam_variant: {opts.gigaam_variant!r}")
    _assert(opts.gigaam_precision == "int8", f"opts.gigaam_precision: {opts.gigaam_precision!r}")
    _assert(opts.num_threads == 2, f"opts.num_threads: {opts.num_threads!r}")

    # build_chunking_options — string-to-int/float coercion plus enabled bool.
    copts = prefs2.build_chunking_options()
    _assert(copts.enabled is True, f"copts.enabled: {copts.enabled!r}")
    _assert(copts.chunk_chars == 60_000, f"copts.chunk_chars: {copts.chunk_chars!r}")
    _assert(abs(copts.overlap_ratio - 0.35) < 1e-9, f"copts.overlap_ratio: {copts.overlap_ratio!r}")

    print("OK: AppPreferences round-trips through QSettings(IniFormat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
