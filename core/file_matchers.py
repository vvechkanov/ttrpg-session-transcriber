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
gate: it takes a parser key string and a candidate path and returns
``True`` iff the extension matches what that parser can read. The
parser keys themselves live in the UI layer — we accept them as
plain strings so this module stays UI-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Extensions recognised as speech audio.
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


def _audio_files_in_flat_dir(dir_: Path) -> tuple[Path, ...]:
    """Return per-speaker audio files in ``dir_`` sorted by path.

    The filter logic that :func:`detect_audio_files` used to own:
    pick audio extensions, drop the Craig mix-down file (stem starts
    with ``craig``), leave the rest. Shared by both the flat-layout
    fallback and the per-segment discovery below.
    """
    matches: list[Path] = []
    for path in _iter_session_files(dir_):
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if path.stem.lower().startswith("craig"):
            continue
        matches.append(path)
    return tuple(matches)


#: Matches a Craig-segment subfolder name such as ``craig``,
#: ``craig-1``, ``craig_2``, ``craig 3`` or their Cyrillic
#: counterparts ``крэйг``, ``крэйг-2``. Case-insensitive via the
#: caller's ``casefold()``. The optional separator (``-``, ``_`` or
#: space) plus trailing digits are both optional so a lone ``craig``
#: folder still counts.
_CRAIG_SEGMENT_RE = re.compile(
    r"^(?:craig|крэйг)(?:[-_ ]?\d*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CraigSegment:
    """One Craig recording segment on disk.

    A session folder may contain multiple Craig segments when the
    recording was restarted mid-game (e.g. ``craig-1/`` and
    ``крэйг-2/`` side by side). Each segment carries its own
    ``info.txt`` with a ``Start time`` line, so consumers can map
    audio offsets back to wall-clock times.
    """

    dir: Path
    info_path: Path | None
    audio_files: tuple[Path, ...]


def _is_craig_segment_dir(candidate: Path) -> bool:
    """Return True if ``candidate`` looks like a Craig segment folder.

    Two ways a directory qualifies:
        * its name matches :data:`_CRAIG_SEGMENT_RE` (``craig-1``,
          ``крэйг 2`` etc.); OR
        * it contains an ``info.txt`` plus at least one audio file
          — covers manually-renamed dumps where someone stripped the
          ``craig-`` prefix.
    """
    if not candidate.is_dir():
        return False
    if candidate.name.startswith("."):
        return False
    if _CRAIG_SEGMENT_RE.match(candidate.name.casefold()):
        return True
    info = candidate / "info.txt"
    if info.is_file() and _audio_files_in_flat_dir(candidate):
        return True
    return False


def detect_craig_segments(session_dir: Path) -> tuple[CraigSegment, ...]:
    """Return ordered Craig segments discovered in ``session_dir``.

    Scans top-level subfolders for entries that either match the
    Craig naming convention (``craig``, ``craig-1``, ``крэйг-2`` —
    case-insensitive; see :data:`_CRAIG_SEGMENT_RE`) or carry an
    ``info.txt`` plus at least one audio file. The resulting segments
    are sorted by ``dir.name.casefold()`` so ``craig-1`` precedes
    ``крэйг-2`` alphabetically; if the caller needs chronological
    ordering by Craig's ``Start time`` that's the
    :mod:`core.timeline_window` layer's job, not this one's.

    When no Craig-style subfolder is found we fall back to treating
    ``session_dir`` itself as a single flat segment — this preserves
    the legacy "audio files live directly in the session folder"
    layout that every test fixture and real session before feature #4
    was built on.
    """
    segments: list[CraigSegment] = []
    if not session_dir.is_dir():
        return ()

    for entry in sorted(session_dir.iterdir(), key=lambda p: p.name.casefold()):
        if not _is_craig_segment_dir(entry):
            continue
        info = entry / "info.txt"
        segments.append(CraigSegment(
            dir=entry,
            info_path=info if info.is_file() else None,
            audio_files=_audio_files_in_flat_dir(entry),
        ))

    if segments:
        return tuple(segments)

    # Fallback: flat layout — the whole session_dir is one segment.
    flat_audio = _audio_files_in_flat_dir(session_dir)
    flat_info = session_dir / "info.txt"
    return (
        CraigSegment(
            dir=session_dir,
            info_path=flat_info if flat_info.is_file() else None,
            audio_files=flat_audio,
        ),
    )


#: Strips Craig's ``N-`` track-index prefix so the same speaker can be
#: grouped across multiple Craig segments. Craig assigns the leading
#: digit by join order within *one* recording, so the same player gets
#: different prefixes in different segments (``1-sir_o_genri`` vs
#: ``2-sir_o_genri``). Matching on the post-prefix part fixes that.
_SPEAKER_PREFIX_RE = re.compile(r"^\d+-")


def match_speaker(file_stem: str) -> str:
    """Normalise a file stem for per-speaker grouping across segments.

    ``"1-sir_o_genri"`` → ``"sir_o_genri"``;
    ``"2-sir_o_genri"`` → ``"sir_o_genri"`` (same speaker).

    A stem without the numeric prefix is returned lowercased as-is
    (``"Andrey"`` → ``"andrey"``), which keeps the key stable for
    both Craig-segment and flat-layout sessions.
    """
    return _SPEAKER_PREFIX_RE.sub("", file_stem).lower()


def detect_audio_files(session_dir: Path) -> tuple[Path, ...]:
    """Return every per-speaker audio file across all Craig segments.

    Thin compatibility shim over :func:`detect_craig_segments`: flat
    single-segment sessions behave exactly as before, multi-segment
    sessions get the union of audio files in a stable (path-sorted)
    order so call-sites that predate feature #4 keep working.

    A Craig recording folder contains one per-speaker ``.flac`` per
    Discord voice channel participant plus a single ``craig-*.flac``
    mix-down export we *don't* want to transcribe separately; the
    mix-down is filtered by :func:`_audio_files_in_flat_dir`.
    """
    all_files: list[Path] = []
    for seg in detect_craig_segments(session_dir):
        all_files.extend(seg.audio_files)
    return tuple(sorted(all_files))


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
#: stay in sync with the parser ids the UI picker dialogs emit.
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
    "CraigSegment",
    "accepted_extensions_for",
    "accepts_file_for",
    "detect_audio_files",
    "detect_combat_logs",
    "detect_craig_segments",
    "detect_fvtt_chat_logs",
    "match_speaker",
]
