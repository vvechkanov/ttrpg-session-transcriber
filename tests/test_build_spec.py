"""Phase 10 — static invariants for build.spec.

We don't run PyInstaller in CI (too heavy), so this file only asserts
invariants that the spec **must** preserve:

    * File parses as Python.
    * onefile=False (LGPL replaceability requirement).
    * Heavy ML packages are in the excludes list.
    * The Qt excludes list mentions the big guilty modules
      (QtWebEngine, QtMultimedia, QtQml).
    * The spec points at ``ui/shell/app.py`` as the entry point.
    * Lazy template modules are listed under ``hiddenimports``.

If the spec drifts out of sync with the runtime (e.g. a new template is
added but not listed), this test catches it before the Phase 10 build
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


def test_spec_uses_ui_shell_app_entry():
    src = _spec_source()
    assert '"ui"' in src and '"shell"' in src and '"app.py"' in src


@pytest.mark.parametrize(
    "excluded",
    [
        "PySide6.QtWebEngineCore",
        "PySide6.QtMultimedia",
        "PySide6.QtQml",
        "PySide6.QtNetwork",
        "PySide6.QtSql",
    ],
)
def test_qt_excludes_present(excluded: str):
    assert excluded in _spec_source(), (
        f"{excluded} must be in _QT_EXCLUDES (Phase 10 bundle budget)"
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


@pytest.mark.parametrize(
    "hidden",
    [
        "ui.templates.audio_source_template",
        "ui.templates.chat_source_template",
        "ui.templates.merger_template",
        "ui.templates.renderer_template",
    ],
)
def test_lazy_templates_in_hidden_imports(hidden: str):
    src = _spec_source()
    assert hidden in src, (
        f"{hidden} must appear in hiddenimports — resolve_template is "
        f"dynamic and PyInstaller can't discover it otherwise."
    )


def test_lgpl_notice_shipped():
    notice = SPEC_PATH.parent / "licenses" / "LGPL-NOTICE.txt"
    assert notice.is_file(), "licenses/LGPL-NOTICE.txt missing (Phase 10)"
    text = notice.read_text(encoding="utf-8")
    assert "LGPL" in text
    assert "PySide6" in text or "Qt" in text
