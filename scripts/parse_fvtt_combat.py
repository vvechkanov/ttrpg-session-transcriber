#!/usr/bin/env python3
"""
Parse Foundry VTT encounter (combat) JSON logs and convert them to
timeline segments compatible with merge_whisperx.py.

Expected input: JSON (saved as .txt or .json) with structure:
    {
      "encounter_id": str,
      "scene_name": str,
      "started_at": ISO8601 UTC,
      "ended_at":   ISO8601 UTC,
      "rounds": [
        {
          "round_number": int,
          "started_at": ISO8601 UTC,
          "turns": [
            {
              "combatant_name": str,
              "started_at": ISO8601 UTC,
              "hp_start": int, "hp_max": int, "hp_end": int,
              "hp_changes":  [{"timestamp", "delta", "hp_before", "hp_after",
                               "source", "damage_type", "actor_name"}],
              "effect_events": [{"timestamp", "event_type",
                                  "effect_type", "effect_name", "slug",
                                  "actor_name", "new_value", "old_value"}],
            }
          ]
        }
      ]
    }

Recording start (info.txt) and all combat timestamps are UTC — alignment
is a direct subtraction, no timezone guessing needed.
"""

import json
from datetime import datetime
from pathlib import Path


# Major PF2e conditions worth surfacing in the narrative transcript.
# Custom "effects" (auras, spell-link buffs like Зеркальная эгида) are
# intentionally skipped — they toggle every turn and drown out the signal.
INTERESTING_CONDITIONS = {
    # Death / consciousness
    "dying", "unconscious", "dead", "wounded",
    # Movement / positioning
    "prone", "grabbed", "restrained", "immobilized", "fleeing", "slowed",
    # Perception
    "blinded", "deafened", "dazzled", "concealed", "hidden", "undetected",
    # Mental
    "frightened", "stunned", "paralyzed", "confused", "controlled",
    # Physical debuffs
    "fatigued", "enfeebled", "clumsy", "drained", "doomed",
    "sickened", "stupefied",
    # Combat tactical
    "off-guard", "flat-footed", "persistent-damage", "quickened",
}


# ── Helpers ───────────────────────────────────────────────────────────

def _parse_iso(s):
    """Parse ISO8601 string → timezone-aware UTC datetime, or None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_from_start(ts, rec_start):
    dt = _parse_iso(ts)
    if dt is None:
        return None
    return (dt - rec_start).total_seconds()


def _format_damage(change: dict) -> str:
    delta = change.get("delta") or 0
    before = change.get("hp_before")
    after = change.get("hp_after")
    hp_max = change.get("hp_max")
    source = (change.get("source") or "").strip()
    dtype = (change.get("damage_type") or "").strip()

    if delta < 0:
        head = f"−{-delta}"
    elif delta > 0:
        head = f"+{delta} (лечение)"
    else:
        head = "±0"

    tags = [t for t in (dtype, source) if t]
    tag_str = f" [{', '.join(tags)}]" if tags else ""

    hp_str = ""
    if before is not None and after is not None:
        if hp_max:
            hp_str = f" (HP {before}→{after}/{hp_max})"
        else:
            hp_str = f" (HP {before}→{after})"
    return f"{head}{tag_str}{hp_str}"


def _format_effect_event(ev: dict) -> str | None:
    """Return short text for a condition event, or None to skip."""
    if ev.get("effect_type") != "condition":
        return None
    slug = ev.get("slug") or ""
    if slug not in INTERESTING_CONDITIONS:
        return None

    etype = ev.get("event_type")
    name = (ev.get("effect_name") or slug).strip()

    if etype in ("applied", "changed"):
        return f"получает [{name}]"
    if etype == "removed" and slug in ("dying", "unconscious", "prone"):
        return f"снимает [{name}]"
    return None


# ── Main entry ────────────────────────────────────────────────────────

def parse_combat_file(path: Path) -> dict:
    """Load combat JSON (extension may be .txt or .json)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def combat_to_segments(
    combat: dict,
    recording_start_utc: datetime,
    *,
    label: str = "⚔️ Бой",
) -> list[dict]:
    """
    Flatten a combat encounter into a sorted list of segment dicts
    aligned to the audio recording timeline.

    Events that occur before recording start are dropped.
    """
    segs: list[dict] = []

    def add(start, text: str) -> None:
        if start is None or start < 0:
            return
        segs.append({
            "start": float(start),
            "end": float(start) + 0.1,
            "speaker": label,
            "text": text,
            "source": "combat",
        })

    # ── Combat start marker ──────────────────────────────────────────
    encounter_start = _parse_iso(combat.get("started_at"))
    scene = (combat.get("scene_name") or "").strip()
    if encounter_start is not None:
        header = "=== Бой начался"
        if scene and scene.lower() != "unknown scene":
            header += f" ({scene})"
        header += " ==="
        add((encounter_start - recording_start_utc).total_seconds(), header)

    # ── Rounds ────────────────────────────────────────────────────────
    for rnd in combat.get("rounds", []):
        rnum = rnd.get("round_number")
        # round 0 is the pre-init setup slot — skip its header
        if rnum and rnum > 0:
            add(
                _seconds_from_start(rnd.get("started_at"), recording_start_utc),
                f"=== Раунд {rnum} ===",
            )

        for turn in rnd.get("turns", []):
            name = turn.get("combatant_name", "?")
            hp_s = turn.get("hp_start")
            hp_m = turn.get("hp_max")
            hp_info = f" (HP {hp_s}/{hp_m})" if hp_s is not None and hp_m else ""
            add(
                _seconds_from_start(turn.get("started_at"), recording_start_utc),
                f"Ход: {name}{hp_info}",
            )

            for ch in turn.get("hp_changes", []):
                target = (ch.get("actor_name") or "?").strip()
                add(
                    _seconds_from_start(ch.get("timestamp"), recording_start_utc),
                    f"{name} → {target}: {_format_damage(ch)}",
                )

            for ev in turn.get("effect_events", []):
                body = _format_effect_event(ev)
                if not body:
                    continue
                target = (ev.get("actor_name") or "?").strip()
                add(
                    _seconds_from_start(ev.get("timestamp"), recording_start_utc),
                    f"{target} {body}",
                )

    # ── Combat end marker ────────────────────────────────────────────
    encounter_end = _parse_iso(combat.get("ended_at"))
    if encounter_end is not None:
        round_count = max(
            (r.get("round_number", 0) for r in combat.get("rounds", [])),
            default=0,
        )
        add(
            (encounter_end - recording_start_utc).total_seconds(),
            f"=== Бой окончен ({round_count} раундов) ===",
        )

    return segs


# ── CLI for standalone testing ────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: parse_fvtt_combat.py <combat.json|.txt> <info.txt>")
        sys.exit(1)

    # Reuse info.txt parser from chat module
    from parse_fvtt_chat import parse_info_start_time

    combat_path = Path(sys.argv[1])
    info_path = Path(sys.argv[2])
    combat = parse_combat_file(combat_path)
    rec_start = parse_info_start_time(info_path)

    segs = combat_to_segments(combat, rec_start)
    print(f"Parsed {combat_path.name} -> {len(segs)} combat events")
    for s in segs[:20]:
        t = s["start"]
        mm, ss = divmod(int(t), 60)
        hh, mm = divmod(mm, 60)
        print(f"  [{hh}:{mm:02d}:{ss:02d}] {s['text'][:100]}")
    if len(segs) > 20:
        print(f"  ... and {len(segs) - 20} more")
