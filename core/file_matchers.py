"""Pure file-matching helpers for the session folder.

Used by both the headless pipeline (``core/``) and the UI layer
(``ui/``). The rule is strict: **no content sniffing** — every
decision is made on the file name or its extension. We never
open a file just to guess its type.

All ``detect_*`` helpers:
    * return a tuple of :class:`Path` sorted alphabetically (by
      full path, so callers get a stable order across platforms);
    * operate on a single directory — no recursion into
      subfolders (sessions are flat layouts per the Craig export);
    * skip dotfiles (anything whose name starts with ``.``);
    * skip symlinks that resolve outside of ``session_dir`` as a
      minimal security sanity check.

The companion :func:`accepts_file_for` is the drop-validation
gate: it takes a parser key (one of the ``KEY_*`` constants in
``ui.shell.add_source_dialog``) and a candidate path and returns
``True`` iff the extension matches what that parser can read. The
parser keys themselves live in the UI layer — we accept them as
plain strings so this module stays UI-free.
"""

from __future__ import annotations

from pathlib import Path

#: Extensions recognised as speech audio. Kept identical to the
#: legacy ``ui.shell.app._AUDIO_EXTENSIONS`` set so swapping the
#: old helper for this one produces the same results.
AUDIO_EXTENSIONS: tuple[str, ...] = (
    ".flac",
    ".wav",
    ".mp3",
    ".ogg",
    ".m4a",
    ".opus",
)

#: Extensions accepted for the Foundry VTT chat parser. A plain
#: ``.txt`` log (what the FVTT "export chat" button produces) is
#: the only supported input — no JSON chat formats yet.
_FVTT_CHAT_EXTENSIONS: tuple[str, ...] = (".txt",)

#: Extensions accepted for combat / encounter dumps.
_COMBAT_EXTENSIONS: tuple[str, ...] = (".json", ".txt")


def _is_safe_regular_file(path: Path, session_dir: Path) -> bool:
    """Return True for a "normal" file inside ``session_dir``.

    Filters out:
        * anything that isn't a regular file (dirs, sockets, etc);
        * dotfiles (``.DS_Store``, ``.gitkeep`` and friends);
        * symlinks that, after ``resolve()``, point outside of
          ``session_dir``. A symlink pointing *inside* is fine.

    We resolve both sides before comparing so that the caller can
    pass in a ``session_dir`` with a relative or unresolved path
    and still get the expected answer.
    """
    if not path.is_file():
        return False
    if path.name.startswith("."):
        return False
    try:
        resolved = path.resolve()
        root = session_dir.resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(root)
    except ValueError:
        return False
    return True


def _iter_session_files(session_dir: Path) -> list[Path]:
    """Return a sorted list of safe regular files in ``session_dir``.

    Sorting happens once here so each ``detect_*`` helper inherits
    a consistent ordering (by the full path, case-sensitive —
    matches the behaviour of ``sorted(Path.iterdir())``).
    """
    if not session_dir.is_dir():
        return []
    candidates: list[Path] = []
    for entry in sorted(session_dir.iterdir()):
        if _is_safe_regular_file(entry, session_dir):
            candidates.append(entry)
    return candidates


def detect_audio_files(session_dir: Path) -> tuple[Path, ...]:
    """Return audio files in ``session_dir`` excluding Craig mix exports.

    A Craig recording folder contains one per-speaker ``.flac`` per
    Discord voice channel participant plus a single ``craig-*.flac``
    file which is the mixed-down export we *don't* want to transcribe
    separately. We skip any file whose stem starts with ``craig`` to
    keep per-speaker diarisation intact.
    """
    matches: list[Path] = []
    for path in _iter_session_files(session_dir):
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if path.stem.lower().startswith("craig"):
            continue
        matches.append(path)
    return tuple(matches)


def detect_fvtt_chat_logs(session_dir: Path) -> tuple[Path, ...]:
    """Return files matching the FVTT chat export pattern.

    Foundry VTT's "export chat" button produces ``fvtt-log-<date>.txt``
    by convention. We accept any ``fvtt-log*.txt`` so both the
    date-stamped export and the plain ``fvtt-log.txt`` work.
    """
    matches: list[Path] = []
    for path in _iter_session_files(session_dir):
        if path.suffix.lower() not in _FVTT_CHAT_EXTENSIONS:
            continue
        if not path.name.lower().startswith("fvtt-log"):
            continue
        matches.append(path)
    return tuple(matches)


def detect_combat_logs(session_dir: Path) -> tuple[Path, ...]:
    """Return combat / encounter dump files in ``session_dir``.

    Matches three naming conventions we've seen in real sessions:
        * ``Бой*.{json,txt}`` — Russian-named exports from Foundry
          VTT "encounter" automation macros;
        * ``combat*.json`` — English equivalents;
        * ``encounter*.json`` — alternative English prefix.

    Case-insensitive on both the prefix and the extension.
    """
    matches: list[Path] = []
    for path in _iter_session_files(session_dir):
        ext = path.suffix.lower()
        if ext not in _COMBAT_EXTENSIONS:
            continue
        name_lower = path.name.lower()
        stem_lower = path.stem.lower()
        # Russian "Бой" prefix — casefold handles unicode case pairing.
        is_ru_combat = stem_lower.casefold().startswith("бой")
        is_en_combat = stem_lower.startswith("combat") and ext == ".json"
        is_encounter = stem_lower.startswith("encounter") and ext == ".json"
        # Russian "Бой" files may be .json or .txt per _COMBAT_EXTENSIONS.
        if is_ru_combat and ext in _COMBAT_EXTENSIONS:
            matches.append(path)
            continue
        if is_en_combat or is_encounter:
            matches.append(path)
            continue
        # name_lower kept for potential future prefixes; currently unused.
        _ = name_lower
    return tuple(matches)


#: Parser keys are duplicated here as module-level strings so
#: ``core/file_matchers`` doesn't import from ``ui/``. They must
#: stay in sync with ``ui.shell.add_source_dialog.KEY_*``. The test
#: suite pins this invariant.
_KEY_GIGAAM = "gigaam"
_KEY_FASTER_WHISPER = "faster-whisper"
_KEY_FVTT_CHAT = "fvtt-chat"

#: Map parser-key → accepted extensions. Unknown keys fall through
#: and :func:`accepts_file_for` returns ``False`` for them.
_ACCEPTED_EXTENSIONS_BY_KEY: dict[str, tuple[str, ...]] = {
    _KEY_GIGAAM: AUDIO_EXTENSIONS,
    _KEY_FASTER_WHISPER: AUDIO_EXTENSIONS,
    _KEY_FVTT_CHAT: _FVTT_CHAT_EXTENSIONS,
}


def accepted_extensions_for(parser_key: str) -> tuple[str, ...]:
    """Return the extensions ``parser_key`` knows how to read.

    Empty tuple for unknown keys — callers use this length check to
    render "unknown parser" hints without crashing.
    """
    return _ACCEPTED_EXTENSIONS_BY_KEY.get(parser_key, ())


def accepts_file_for(parser_key: str, path: Path) -> bool:
    """Return True iff ``path`` has an extension ``parser_key`` accepts.

    No I/O — purely the suffix check. Unknown parser keys return
    ``False`` (never raise) so drop handlers can treat the mismatch
    as a validation error, not a bug.
    """
    accepted = accepted_extensions_for(parser_key)
    if not accepted:
        return False
    return path.suffix.lower() in accepted


__all__ = [
    "AUDIO_EXTENSIONS",
    "accepted_extensions_for",
    "accepts_file_for",
    "detect_audio_files",
    "detect_combat_logs",
    "detect_fvtt_chat_logs",
]
