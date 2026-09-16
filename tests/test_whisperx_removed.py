"""WhisperX is out of master, and a machine keeps it out.

Owner decision C2 (`TASKS.md`): the backend lives on in the owner's own
local branch, not here. A removal nobody guards comes back — a merge from
that branch, a registry entry copied from a stale example, a helpful
"restore the third backend" commit. Nothing in the tree would have
objected: the registry is a plain dict and the dispatch is a chain of
``if cls.__name__ == …``, so a returning backend looks exactly like a
normal addition.

Three separable checks, because the failure modes are separable:

* the module file is gone from disk,
* the speech registry does not name it,
* no live file in the tree names the module or its class.

Only the third catches a re-registration under a different module path,
and only the second catches a registry entry pointing at something else
entirely. Neither subsumes the other.

Cheap by construction: no audio, no models, no subprocess, no Qt.

What is deliberately *not* checked here is the word "whisperx" as such.
Three things in this tree carry it and are not the backend: the shipped
product name ``WhisperX-Transcriber`` (the Windows uninstall key is
registered under it — see ``launcher/uninstall_logic.py``), the deleted
legacy script ``merge_whisperx.py`` that several docstrings name as the
provenance of logic ported out of it, and the ``whisperx`` *PyPI package*
in the PyInstaller ``excludes`` lists, which is what keeps a system-wide
install from leaking into a frozen build. A guard on the bare word would
have to allowlist all three, and an allowlist that large stops being a
guard. The identifiers below are unambiguous instead.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: The module that was deleted. Only the module: the PowerShell script
#: that used to install the backend is still in the tree on purpose, and
#: nothing here checks for it (see the ``### Removed`` entry in
#: CHANGELOG.md and task C3 in TASKS.md).
WHISPERX_MODULE = PROJECT_ROOT / "sources" / "speech" / "whisperx.py"

#: Files that must turn up in any honest enumeration of this repository.
#: They are the canary for the scan below — see
#: ``test_the_scan_is_reading_a_real_tree``.
CANARY_FILES = ("sources/__init__.py", "core/pipeline.py", "README.md")

#: The backend's registry id, as it read in ``SPEECH_SOURCES``.
WHISPERX_BACKEND_ID = "whisperx"

#: Spellings that can only mean the removed backend. The class name and
#: both spellings of the module path — dotted for an import, sliced for a
#: document or a build spec.
#:
#: Assembled at runtime rather than written out, so that this file — which
#: necessarily contains all three — does not match itself when the scan
#: below reads the tree. Without that, the guard fails on its own text.
FORBIDDEN_SPELLINGS = (
    "WhisperX" + "Source",
    "sources.speech." + "whisperx",
    "sources/speech/" + "whisperx",
)

#: Documents that record the tree as it *was*. A changelog entry about the
#: removal has to name what it removed, and an ADR records the tree it was
#: decided against. Same list, and the same reasoning, as
#: ``tests/test_docs_architecture.py``.
HISTORICAL_PREFIXES = (
    "docs/adr/",
    "docs/architecture/",
    "docs/handoff/",
    "docs/plans/",
    "docs/specs/",
    "docs/design/",
)
HISTORICAL_DOCUMENTS = (
    "CHANGELOG.md",
    "docs/architecture-review-2026-06.md",
)

#: Binary and generated trees the scan has no business reading.
SKIPPED_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".exe")


def _tracked_files() -> list[str]:
    """Repository-relative paths git tracks and that exist on disk.

    git is asked first because it already knows what is generated and what
    is checked in. The walk is the fallback for a tree git cannot answer
    for — a checkout unpacked inside someone else's work tree, or git
    missing from the image entirely.
    """
    try:
        listed = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
            timeout=30,
        ).stdout.decode("utf-8")
        names = [n for n in listed.split("\0") if n]
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError):
        names = []

    if names:
        return [n for n in names if (PROJECT_ROOT / n).is_file()]
    return _walked_files()


def _walked_files() -> list[str]:
    """Fallback enumeration: walk the tree, prune the obvious."""
    pruned = {".git", "venv", ".venv", "__pycache__", "node_modules", "build", "dist"}
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in pruned]
        for filename in filenames:
            path = Path(dirpath) / filename
            found.append(path.relative_to(PROJECT_ROOT).as_posix())
    return found


def _live_files() -> list[str]:
    """Tracked files whose text is a claim about the tree as it is now."""
    return sorted(
        name
        for name in _tracked_files()
        if name not in HISTORICAL_DOCUMENTS
        and not name.startswith(HISTORICAL_PREFIXES)
        and not name.endswith(SKIPPED_SUFFIXES)
        # This file names all three spellings in order to look for them.
        and name != "tests/test_whisperx_removed.py"
    )


class TestTheModuleIsGone:
    def test_whisperx_module_file_does_not_exist(self):
        assert not WHISPERX_MODULE.exists(), (
            f"{WHISPERX_MODULE.relative_to(PROJECT_ROOT)} is back. Owner "
            "decision C2 keeps the backend in the owner's local branch only."
        )

    def test_whisperx_module_is_not_importable(self):
        with pytest.raises(ModuleNotFoundError):
            __import__("sources.speech.whisperx")


class TestTheRegistryDoesNotNameIt:
    def test_whisperx_is_not_a_registered_speech_source(self):
        from sources import SPEECH_SOURCES, list_speech_sources

        assert WHISPERX_BACKEND_ID not in SPEECH_SOURCES
        assert WHISPERX_BACKEND_ID not in list_speech_sources()

    def test_asking_for_whisperx_by_name_is_a_value_error(self):
        from sources import get_speech_source

        with pytest.raises(ValueError, match="Unknown speech source"):
            get_speech_source(WHISPERX_BACKEND_ID)

    def test_the_surviving_backends_are_the_two_the_owner_kept(self):
        """The count is the point of C2, so it is asserted, not implied.

        Written as a set rather than a length: a backend swapped for
        another would keep the count and change the product.
        """
        from sources import list_speech_sources

        assert set(list_speech_sources()) == {"faster-whisper", "gigaam"}


class TestTheDispatchHasNoDanglingBranch:
    def test_speech_kwargs_answers_for_every_registered_backend(self):
        """The invariant that outlives the removal.

        ``_speech_kwargs`` dispatches on ``cls.__name__`` and raises for
        anything it does not recognise. Deleting a backend and forgetting
        its branch is harmless; deleting a *branch* and forgetting the
        backend raises at run time, on a machine with the model already
        downloaded. This is the check that would have caught that.
        """
        from core.pipeline import PipelineParams, _speech_kwargs
        from sources import SPEECH_SOURCES

        params = PipelineParams()
        for name, cls in SPEECH_SOURCES.items():
            kwargs = _speech_kwargs(params, cls)
            assert isinstance(kwargs, dict), name
            assert "speaker_map" in kwargs, name


class TestNoLiveFileNamesTheBackend:
    def test_the_scan_is_reading_a_real_tree(self):
        """The scan below passes trivially over an empty file list.

        Measured, not supposed: forcing ``_live_files()`` to return ``[]``
        left the scan green and silent. Nothing else in the suite noticed,
        because "found no forbidden spellings" and "looked at nothing" are
        the same result.

        Enumeration failing outright is already handled — ``_tracked_files``
        falls back to a walk when git cannot answer. What this guards is the
        quieter way the list empties out: a filter predicate widened,
        ``SKIPPED_SUFFIXES`` gaining ``.py``, a short string landing in
        ``HISTORICAL_PREFIXES``. Each turns the scan into a no-op that
        reports success.

        Named files rather than a count, because a count drifts with the
        tree and teaches nobody what went missing.
        """
        files = _live_files()
        missing = [name for name in CANARY_FILES if name not in files]
        assert not missing, (
            f"_live_files() returned {len(files)} file(s), and {missing} "
            "not among them — the scan below is not looking at this "
            "repository, and its success means nothing."
        )

    def test_no_live_file_names_the_whisperx_module_or_class(self):
        """Catches the backend coming back under a different module path.

        Reported as one failure listing every hit, rather than the first
        one: a re-added backend touches the registry, the dispatch and the
        build spec together, and fixing them one test run at a time is
        three runs to learn what one run already knew.
        """
        hits: list[str] = []
        for name in _live_files():
            path = PROJECT_ROOT / name
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                # One report per line, not one per spelling: an import line
                # carries both the module path and the class name, and
                # listing it twice makes the failure look twice as large as
                # the work it asks for.
                if any(spelling in line for spelling in FORBIDDEN_SPELLINGS):
                    hits.append(f"{name}:{lineno}: {line.strip()}")

        assert not hits, (
            "the removed WhisperX backend is named by "
            f"{len(hits)} live line(s):\n" + "\n".join(hits)
        )
