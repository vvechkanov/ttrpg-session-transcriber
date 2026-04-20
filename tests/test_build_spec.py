"""Static invariants for build.spec (Phase 9 — QML shell).

We don't run PyInstaller in CI (too heavy), so this file only asserts
invariants that the spec **must** preserve:

    * File parses as Python.
    * ``onefile=False`` (LGPL replaceability requirement).
    * Heavy ML packages are in the excludes list.
    * The Qt excludes list drops the big guilty modules
      (QtWebEngine, QtMultimedia, QtSql, QtNetwork, QtWidgets).
    * The QtQml / QtQuick / QtQuickControls2 stack is NOT excluded
      and IS listed in hiddenimports — the Basic style plugin lookup
      is a string call QtQuickControls2 loads at runtime so
      PyInstaller can't discover it otherwise.
    * The spec points at ``ui/app_qml.py`` as the entry point.
    * Lazy template modules are listed under ``hiddenimports``.
    * Bundled ffmpeg/ffprobe helpers reach ``tools/ffmpeg/bin``.
    * Handoff markdown ships under ``docs/handoff``.

If the spec drifts out of sync with the runtime (e.g. a new template
is added but not listed), this test catches it before the build
blows up in a user's hand.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SPEC_PATH = Path(__file__).resolve().parents[1] / "build.spec"


def _spec_source() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def test_spec_file_exists():
    assert SPEC_PATH.is_file(), f"build.spec not found at {SPEC_PATH}"


def test_spec_parses_as_python():
    ast.parse(_spec_source())


def test_spec_uses_ui_app_qml_entry():
    src = _spec_source()
    assert '"ui"' in src and '"app_qml.py"' in src, (
        "build.spec must point at ui/app_qml.py (QML shell), "
        "not ui/shell/app.py (Widgets shell, removed in Phase 10)."
    )


@pytest.mark.parametrize(
    "excluded",
    [
        "PySide6.QtWebEngineCore",
        "PySide6.QtMultimedia",
        "PySide6.QtNetwork",
        "PySide6.QtSql",
        "PySide6.QtWidgets",
    ],
)
def test_qt_excludes_present(excluded: str):
    assert excluded in _spec_source(), (
        f"{excluded} must be in _QT_EXCLUDES (Phase 9 bundle budget)"
    )


@pytest.mark.parametrize(
    "qt_module",
    [
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickTemplates2",
        "PySide6.QtSvg",
    ],
)
def test_qml_stack_not_excluded(qt_module: str):
    """Phase 9: the QML stack MUST NOT appear in the excludes list."""

    src = _spec_source()
    # Look for the exact occurrence inside _QT_EXCLUDES — a trailing
    # comma after the string is the signature of an excludes entry.
    needle = f'"{qt_module}",'
    # Find any excludes-list-style occurrence (inside _QT_EXCLUDES).
    # The string appears in hiddenimports as well, so just check that
    # it's NOT followed by a ``,`` inside a bracketed excludes region.
    # A simple substring check works because the hiddenimports list
    # ends with a closing bracket before _QT_EXCLUDES is defined.
    excludes_start = src.find("_QT_EXCLUDES")
    if excludes_start == -1:
        pytest.fail("_QT_EXCLUDES list not found in build.spec")
    excludes_end = src.find("]", excludes_start)
    excludes_block = src[excludes_start:excludes_end]
    assert needle not in excludes_block, (
        f"{qt_module} must NOT be in _QT_EXCLUDES — the QML shell "
        "needs it. Check Phase 9 migration notes."
    )


@pytest.mark.parametrize(
    "hidden",
    [
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickControls2",
        "PySide6.QtQuickTemplates2",
        "PySide6.QtSvg",
    ],
)
def test_qml_stack_in_hidden_imports(hidden: str):
    src = _spec_source()
    assert f'"{hidden}"' in src, (
        f"{hidden} must appear in hiddenimports so PyInstaller collects "
        "the DLL + style plugin."
    )


@pytest.mark.parametrize(
    "excluded",
    ["torch", "faster_whisper", "whisperx", "transformers", "pyannote", "tkinter"],
)
def test_heavy_ml_excludes_present(excluded: str):
    src = _spec_source()
    assert f'"{excluded}"' in src, (
        f"{excluded!r} must be excluded — installed via bootstrap runtime"
    )


def test_not_onefile_for_lgpl_compliance():
    src = _spec_source()
    assert "exclude_binaries=True" in src, (
        "build.spec must use exclude_binaries=True + COLLECT (folder mode) "
        "to keep Qt DLLs as separate files per LGPL replaceability."
    )
    assert "COLLECT(" in src, "COLLECT stage missing — onefile is forbidden"


def test_ui_templates_removed():
    """Phase 10: the template-factory layer is gone — spec must not mention it."""

    src = _spec_source()
    assert "ui.templates" not in src, (
        "ui.templates.* removed in Phase 10; hiddenimports must not cite them."
    )


@pytest.mark.parametrize(
    "hidden",
    [
        "sources.speech.gigaam",
        "sources.speech.faster_whisper",
        "sources.game_log.fvtt_chat",
        "mergers.script_merger",
        "renderers.plain_text",
    ],
)
def test_backend_plugins_in_hidden_imports(hidden: str):
    """Registry-resolved backends need explicit hiddenimports entries."""

    src = _spec_source()
    assert hidden in src, (
        f"{hidden} must appear in hiddenimports — SPEECH_SOURCES / "
        f"MERGERS / RENDERERS lookups are dynamic."
    )


def test_ffmpeg_bundled():
    src = _spec_source()
    assert "tools" in src and "ffmpeg" in src, (
        "Phase 5 peaks extraction shells out to the bundled ffmpeg — "
        "the spec must carry tools/ffmpeg/bin into the dist folder."
    )


def test_lgpl_notice_shipped():
    notice = SPEC_PATH.parent / "licenses" / "LGPL-NOTICE.txt"
    assert notice.is_file(), "licenses/LGPL-NOTICE.txt missing"
    text = notice.read_text(encoding="utf-8")
    assert "LGPL" in text
    assert "PySide6" in text or "Qt" in text
