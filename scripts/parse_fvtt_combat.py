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


def _format_action(action: dict) -> str:
    """Compact one-line summary of a single in-turn action.

    Format: ``{action_name} | {action_type} | cost=N | roll=R (formula) |
    {degree} | damage=N type | DC=N | -> targets``. None / empty fields
    are omitted so noise stays low.
    """
    parts: list[str] = []
    name = (action.get("action_name") or action.get("title") or "").strip()
    if name:
        parts.append(name)
    action_type = action.get("action_type")
    if action_type:
        parts.append(str(action_type))
    cost = action.get("action_cost")
    if cost is not None:
        parts.append(f"cost={cost}")
    roll_result = action.get("roll_result")
    if roll_result is not None:
        formula = action.get("roll_formula")
        roll_str = f"roll={roll_result}"
        if formula:
            roll_str += f" ({formula})"
        parts.append(roll_str)
    degree = action.get("degree_of_success")
    if degree:
        parts.append(str(degree))
    damage = action.get("damage_dealt")
    if damage is not None:
        damage_type = (action.get("damage_type") or "").strip()
        parts.append(
            f"damage={damage}" + (f" {damage_type}" if damage_type else "")
        )
    healing = action.get("healing_done")
    if healing is not None:
        parts.append(f"healing={healing}")
    dc = action.get("dc") or {}
    dc_value = dc.get("value") if isinstance(dc, dict) else None
    if dc_value is not None:
        parts.append(f"DC={dc_value}")
    save_type = action.get("save_type")
    if save_type:
        parts.append(f"save={save_type}")
    targets = action.get("targets") or []
    target_names = [
        str(t.get("name") or "").strip()
        for t in targets
        if t.get("name")
    ]
    if target_names:
        parts.append(f"-> {', '.join(target_names)}")
    return " | ".join(parts)


def _format_movement(mv: dict) -> str:
    distance = mv.get("distance_ft")
    if distance is None:
        return ""
    return f"переместился на {distance} ft"


def _format_global_summary(stats: dict) -> str:
    """Encounter-wide totals: rounds, duration, XP, party level, difficulty."""
    parts: list[str] = []
    if (rounds := stats.get("total_rounds")) is not None:
        parts.append(f"rounds={rounds}")
    if (duration := stats.get("combat_duration_seconds")) is not None:
        parts.append(f"duration={int(duration)}s")
    if (xp := stats.get("total_xp")) is not None:
        parts.append(f"xp={xp}")
    if (party_level := stats.get("party_level")) is not None:
        parts.append(f"party_lvl={party_level}")
    if difficulty := stats.get("difficulty"):
        parts.append(f"difficulty={difficulty}")
    if (avg_gm := stats.get("avg_turn_duration_gm_seconds")) is not None:
        parts.append(f"avg_gm_turn={avg_gm:.0f}s")
    return " | ".join(parts)


def _format_actor_summary(stats: dict) -> str:
    """Per-actor stats: damage, healing, hit rate, downed, max single hit.

    Drops zero / None fields so the line stays compact.
    """
    parts: list[str] = []
    actor_type = stats.get("actor_type")
    level = stats.get("level")
    if actor_type or level is not None:
        type_part = str(actor_type) if actor_type else ""
        if level is not None:
            type_part = f"{type_part} lvl={level}".strip()
        parts.append(type_part)
    if (dmg := stats.get("damage_dealt")) is not None and dmg > 0:
        share = stats.get("damage_share_percent")
        share_str = f" ({share}%)" if share is not None else ""
        parts.append(f"DMG_dealt={dmg}{share_str}")
    if (taken := stats.get("damage_taken")) is not None and taken > 0:
        parts.append(f"DMG_taken={taken}")
    if (heal_done := stats.get("healing_done")) is not None and heal_done > 0:
        parts.append(f"healing_done={heal_done}")
    if (heal_recv := stats.get("healing_received")) is not None and heal_recv > 0:
        parts.append(f"healing_received={heal_recv}")
    if (hit_rate := stats.get("hit_rate_percent")) is not None:
        parts.append(f"hit_rate={hit_rate}%")
    if (downed := stats.get("times_downed")) is not None and downed > 0:
        parts.append(f"downed={downed}")
    if (revived := stats.get("revive_count")) is not None and revived > 0:
        parts.append(f"revived={revived}")
    max_hit = stats.get("max_single_hit") or {}
    max_hit_value = max_hit.get("value")
    if max_hit_value is not None and max_hit_value > 0:
        item = (max_hit.get("item_name") or "").strip()
        item_str = f" ({item})" if item else ""
        parts.append(f"max_hit={max_hit_value}{item_str}")
    one_shots = stats.get("one_shots") or []
    one_shot_names = [
        str(o.get("name") or "").strip()
        for o in one_shots
        if o.get("name")
    ]
    if one_shot_names:
        parts.append(f"one_shots=[{', '.join(one_shot_names)}]")
    return " | ".join(parts)


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

            # Actions don't carry their own timestamp — peg them to the
            # turn's started_at so they sort right after the turn header.
            turn_started_seconds = _seconds_from_start(
                turn.get("started_at"), recording_start_utc
            )
            for action in turn.get("actions", []) or []:
                detail = _format_action(action)
                if not detail:
                    continue
                add(turn_started_seconds, f"{name}: {detail}")

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

            for mv in turn.get("movements", []) or []:
                detail = _format_movement(mv)
                if not detail:
                    continue
                token_name = (mv.get("token_name") or "?").strip()
                add(
                    _seconds_from_start(mv.get("timestamp"), recording_start_utc),
                    f"{token_name} {detail}",
                )

    # ── Combat end marker ────────────────────────────────────────────
    encounter_end = _parse_iso(combat.get("ended_at"))
    if encounter_end is not None:
        round_count = max(
            (r.get("round_number", 0) for r in combat.get("rounds", [])),
            default=0,
        )
        encounter_end_seconds = (
            encounter_end - recording_start_utc
        ).total_seconds()
        add(encounter_end_seconds, f"=== Бой окончен ({round_count} раундов) ===")

        # ── Summary (encounter-wide + per-actor) ─────────────────────
        # Both blocks sit on the same timestamp as encounter_end with
        # stable insertion order — sorted() is stable, so they end up
        # right after the "=== Бой окончен ===" marker in merged.txt.
        summary = combat.get("summary") or {}
        global_stats = summary.get("global") or {}
        if global_stats:
            detail = _format_global_summary(global_stats)
            if detail:
                add(encounter_end_seconds, f"=== Итого боя: {detail} ===")
        per_actor = summary.get("per_actor") or {}
        for actor_id, stats in per_actor.items():
            actor_name = (stats.get("name") or actor_id).strip()
            detail = _format_actor_summary(stats)
            if detail:
                add(encounter_end_seconds, f"Итог {actor_name}: {detail}")

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
