#!/usr/bin/env python3
import json, sys
from pathlib import Path
from itertools import count

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
    """
    if not all_segs:
        return []
    merged = [all_segs[0].copy()]
    for seg in all_segs[1:]:
        prev = merged[-1]
        same_speaker = seg["speaker"] == prev["speaker"]
        close_enough = (seg["start"] - prev["end"]) <= gap_sec
        if same_speaker and close_enough:
            prev["text"] = (prev["text"].rstrip() + " " + seg["text"].lstrip()).strip()
            prev["end"] = max(prev["end"], seg["end"])
        else:
            merged.append(seg.copy())
    return merged

def main(paths):
    paths = [Path(p) for p in paths]
    session_dir = (paths[0].parent if paths else Path.cwd()).resolve()
    speaker_map = load_speaker_map(session_dir)

    all_segs = []
    for p in paths:
        all_segs.extend(load_segments(Path(p), speaker_map, DEFAULT_EXCLUDE_PREFIXES))

    if not all_segs:
        sys.exit(">>> No segments read – aborting")

    all_segs.sort(key=lambda s: s["start"])
    all_segs = merge_adjacent(all_segs, gap_sec=DEFAULT_MERGE_GAP_SEC)

    # write plain text for LLMs (no timecodes)
    txt_file = Path("merged.txt")
    with txt_file.open("w", encoding="utf-8") as out:
        for seg in all_segs:
            out.write(f"{seg['speaker']}: {seg['text']}\n\n")

    print(f"\nDone. Wrote {len(all_segs)} cues to:")
    print(" ", txt_file.resolve())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: merge_whisperx.py transcript1.json …")
    main(sys.argv[1:])
