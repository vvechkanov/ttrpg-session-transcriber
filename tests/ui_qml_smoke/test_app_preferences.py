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
    _assert(prefs.defaultDevice == "cuda", f"default device: {prefs.defaultDevice!r}")

    # Mutate every field.
    prefs.workingFolder = "D:/TTRPG/Sessions"
    prefs.mergerMaxGap = "2.5"
    prefs.mergerOocMode = "italic"
    prefs.interfaceLanguage = "en"
    prefs.showTooltips = False
    prefs.soundOnDone = False
    prefs.defaultDevice = "cpu"

    # A second instance should pick up the persisted values.
    prefs2 = AppPreferences()
    _assert(prefs2.workingFolder == "D:/TTRPG/Sessions", f"round-trip folder: {prefs2.workingFolder!r}")
    _assert(prefs2.mergerMaxGap == "2.5", f"round-trip gap: {prefs2.mergerMaxGap!r}")
    _assert(prefs2.mergerOocMode == "italic", f"round-trip ooc: {prefs2.mergerOocMode!r}")
    _assert(prefs2.interfaceLanguage == "en", f"round-trip lang: {prefs2.interfaceLanguage!r}")
    _assert(prefs2.showTooltips is False, "round-trip tooltips")
    _assert(prefs2.soundOnDone is False, "round-trip sound")
    _assert(prefs2.defaultDevice == "cpu", f"round-trip device: {prefs2.defaultDevice!r}")

    print("OK: AppPreferences round-trips through QSettings(IniFormat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
