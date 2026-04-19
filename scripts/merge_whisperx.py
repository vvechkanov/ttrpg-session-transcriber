#!/usr/bin/env python3
import json, sys, argparse
from pathlib import Path

# Ensure sibling modules (parse_fvtt_chat) are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_EXCLUDE_PREFIXES = ("craig",)
DEFAULT_MERGE_GAP_SEC = 1.0

def load_speaker_map(session_dir: Path) -> dict:
    """
    Optional speaker map format (speaker_map.json):
      {
        "1-vivienen": {"player":"Настя","character":"Бэйль","role":"PC"},
        "2-v_vladimir": {"player":"Владимир","character":"ГМ","role":"GM"}
      }

    Search order:
      1. session_dir/speaker_map.json  (per-session override)
      2. <project_root>/speaker_map.json  (shared default)
    """
    candidates = [
        session_dir / "speaker_map.json",
        Path(__file__).resolve().parent.parent / "speaker_map.json",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}

def speaker_label(stem: str, speaker_map: dict) -> str:
    entry = speaker_map.get(stem) or speaker_map.get(f"{stem}.json") or {}
    if not isinstance(entry, dict):
        entry = {}
    player = (entry.get("player") or "").strip()
    character = (entry.get("character") or "").strip()
    if player and character:
        return f"{player} ({character})"
    if player:
        return player
    if character:
        return character
    return stem

def should_exclude(path: Path, exclude_prefixes: tuple[str, ...]) -> bool:
    stem = path.stem.lower()
    return any(stem == p or stem.startswith(p + "-") for p in exclude_prefixes)

def load_segments(path: Path, speaker_map: dict, exclude_prefixes: tuple[str, ...]):
    if should_exclude(path, exclude_prefixes):
        print(f"{path.name:35}  skipped (excluded)")
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    stem = path.stem
    speaker = speaker_label(stem, speaker_map)
    segs = data.get("segments", [])
    print(f"{path.name:35}  {len(segs):4} segments")
    out = []
    for seg in segs:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue
        out.append(
            {
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "speaker": speaker,
                "text": txt,
            }
        )
    return out

def merge_adjacent(all_segs: list[dict], *, gap_sec: float = DEFAULT_MERGE_GAP_SEC) -> list[dict]:
    """
    Glue consecutive segments of the same speaker if the gap is small.
    Greatly reduces "staircase" text for LLM consumption.
    Never merges segments from different sources (audio vs chat vs combat),
    and never merges combat events (each event is a discrete beat).
    """
    if not all_segs:
        return []
    merged = [all_segs[0].copy()]
    for seg in all_segs[1:]:
        prev = merged[-1]
        same_speaker = seg["speaker"] == prev["speaker"]
        same_source = seg.get("source") == prev.get("source")
        is_combat = seg.get("source") == "combat" or prev.get("source") == "combat"
        close_enough = (seg["start"] - prev["end"]) <= gap_sec
        if same_speaker and same_source and close_enough and not is_combat:
            prev["text"] = (prev["text"].rstrip() + " " + seg["text"].lstrip()).strip()
            prev["end"] = max(prev["end"], seg["end"])
        else:
            merged.append(seg.copy())
    return merged

def _resolve_info_file(info_file, session_dir: Path) -> Path:
    if info_file:
        return Path(info_file)
    auto_info = session_dir / "info.txt"
    if auto_info.exists():
        return auto_info
    sys.exit(">>> No info.txt found — cannot align external log timestamps")


def main(paths, *, chat_log=None, info_file=None, tz_offset=None, combat_logs=None):
    paths = [Path(p) for p in paths]
    session_dir = (paths[0].parent if paths else Path.cwd()).resolve()
    speaker_map = load_speaker_map(session_dir)

    all_segs = []
    for p in paths:
        all_segs.extend(load_segments(Path(p), speaker_map, DEFAULT_EXCLUDE_PREFIXES))

    # ── Integrate FVTT chat log ──────────────────────────────────────
    if chat_log:
        from parse_fvtt_chat import (
            parse_fvtt_log, parse_info_start_time,
            chat_to_segments, guess_tz_offset,
        )
        chat_log = Path(chat_log)
        entries = parse_fvtt_log(chat_log)
        print(f"{'[FVTT chat]':35}  {len(entries):4} entries from {chat_log.name}")

        rec_start = parse_info_start_time(_resolve_info_file(info_file, session_dir))

        if tz_offset is None:
            tz_offset = guess_tz_offset(entries, rec_start)
            print(f"  Auto-detected timezone: UTC{tz_offset:+.0f}")

        chat_segs = chat_to_segments(entries, rec_start, tz_offset)
        print(f"  {len(chat_segs)} chat segments within recording range")
        all_segs.extend(chat_segs)

    # ── Integrate FVTT combat (encounter) logs ───────────────────────
    if combat_logs:
        from parse_fvtt_chat import parse_info_start_time
        from parse_fvtt_combat import parse_combat_file, combat_to_segments

        rec_start = parse_info_start_time(_resolve_info_file(info_file, session_dir))
        for cpath in combat_logs:
            cpath = Path(cpath)
            try:
                combat = parse_combat_file(cpath)
            except Exception as e:
                print(f"{'[FVTT combat]':35}  !! skipped {cpath.name}: {e}")
                continue
            csegs = combat_to_segments(combat, rec_start)
            print(f"{'[FVTT combat]':35}  {len(csegs):4} events from {cpath.name}")
            all_segs.extend(csegs)

    if not all_segs:
        sys.exit(">>> No segments read – aborting")

    all_segs.sort(key=lambda s: s["start"])
    all_segs = merge_adjacent(all_segs, gap_sec=DEFAULT_MERGE_GAP_SEC)

    # write plain text for LLMs (no timecodes)
    txt_file = Path("merged.txt")
    chat_count = 0
    combat_count = 0
    with txt_file.open("w", encoding="utf-8") as out:
        for seg in all_segs:
            src = seg.get("source")
            if src == "chat":
                out.write(f"[ЧАТ] {seg['speaker']}: {seg['text']}\n\n")
                chat_count += 1
            elif src == "combat":
                out.write(f"[БОЙ] {seg['text']}\n\n")
                combat_count += 1
            else:
                out.write(f"{seg['speaker']}: {seg['text']}\n\n")

    print(f"\nDone. Wrote {len(all_segs)} cues "
          f"({chat_count} chat, {combat_count} combat) to:")
    print(" ", txt_file.resolve())

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Merge WhisperX JSONs + optional FVTT chat/combat logs")
    ap.add_argument("json_files", nargs="+", help="WhisperX JSON transcript files")
    ap.add_argument("--chat_log", default=None, help="Path to fvtt-log-*.txt chat log")
    ap.add_argument("--combat_log", action="append", default=None,
                    help="Path to FVTT encounter JSON (can be given multiple times)")
    ap.add_argument("--info_file", default=None, help="Path to info.txt (recording start time)")
    ap.add_argument("--tz_offset", type=float, default=None,
                    help="Chat log timezone UTC offset (e.g. 1 for UTC+1). Auto-detected if omitted.")
    args = ap.parse_args()
    main(
        args.json_files,
        chat_log=args.chat_log,
        info_file=args.info_file,
        tz_offset=args.tz_offset,
        combat_logs=args.combat_log,
    )
