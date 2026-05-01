"""Tier-1 tests for scripts/parse_fvtt_combat.py — actions, movements,
summary block. Uses synthetic encounter dump (no disk JSON files)."""

from datetime import datetime, timezone


def _encounter_payload() -> dict:
    """Minimal encounter dump with all key fields populated."""
    return {
        "encounter_id": "enc-1",
        "scene_name": "Scene A",
        "started_at": "2026-04-18T16:30:00.000Z",  # 900s after Craig start
        "ended_at": "2026-04-18T16:35:00.000Z",  # 1200s
        "rounds": [
            # round 0 — служебный, header не выводится
            {"round_number": 0, "started_at": "2026-04-18T16:30:00.000Z",
             "turns": []},
            {
                "round_number": 1,
                "started_at": "2026-04-18T16:30:01.000Z",  # 901s
                "turns": [
                    {
                        "combatant_name": "Гельдала",
                        "actor_id": "A",
                        "started_at": "2026-04-18T16:30:01.000Z",
                        "ended_at": "2026-04-18T16:30:30.000Z",
                        "hp_start": 33,
                        "hp_max": 33,
                        "actions": [
                            {
                                "action_name": "Удар: Клыки",
                                "action_type": "strike",
                                "action_cost": 1,
                                "roll_result": 25,
                                "roll_formula": "1d20+12",
                                "degree_of_success": "success",
                                "damage_dealt": 13,
                                "damage_type": "piercing",
                                "dc": {"value": 19, "slug": "armor"},
                                "targets": [{"name": "Калигни"}],
                            },
                        ],
                        "hp_changes": [
                            {
                                "actor_name": "Калигни",
                                "timestamp": "2026-04-18T16:30:10.000Z",
                                "delta": -13,
                                "hp_before": 30,
                                "hp_after": 17,
                                "hp_max": 30,
                                "source": "Клыки",
                                "damage_type": "piercing",
                            },
                        ],
                        "effect_events": [
                            {
                                "event_type": "applied",
                                "effect_type": "condition",
                                "effect_name": "Ослеплён",
                                "slug": "blinded",
                                "actor_name": "Калигни",
                                "timestamp": "2026-04-18T16:30:15.000Z",
                            },
                        ],
                        "movements": [
                            {
                                "token_name": "Гельдала",
                                "timestamp": "2026-04-18T16:30:20.000Z",
                                "distance_ft": 25,
                            },
                        ],
                    },
                ],
            },
        ],
        "summary": {
            "global": {
                "total_rounds": 1,
                "combat_duration_seconds": 300.0,
                "total_xp": 80,
                "party_level": 3,
                "difficulty": "moderate",
            },
            "per_actor": {
                "A": {
                    "name": "Гельдала",
                    "actor_type": "pc",
                    "level": 3,
                    "damage_dealt": 13,
                    "damage_taken": 0,
                    "damage_share_percent": 100.0,
                    "hit_rate_percent": 100,
                    "max_single_hit": {"value": 13, "item_name": "Клыки"},
                    "one_shots": [],
                },
                "B": {
                    "name": "Калигни",
                    "actor_type": "npc",
                    "level": 2,
                    "damage_dealt": 0,
                    "damage_taken": 13,
                    "times_downed": 1,
                    "max_single_hit": {"value": 0, "item_name": None},
                    "one_shots": [],
                },
            },
        },
    }


def _rec_start() -> datetime:
    """Craig recording started at 16:15:00Z — 15 min before encounter."""
    return datetime(2026, 4, 18, 16, 15, 0, tzinfo=timezone.utc)


# ── Actions ───────────────────────────────────────────────────────────


class TestActions:
    def test_action_segment_emitted_per_action(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        action_segs = [s for s in segs if "Удар: Клыки" in s["text"]]
        assert len(action_segs) == 1

    def test_action_text_includes_full_detail(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        text = next(s["text"] for s in segs if "Удар: Клыки" in s["text"])
        # combatant name as actor prefix
        assert text.startswith("Гельдала: ")
        for token in (
            "Удар: Клыки",
            "strike",
            "cost=1",
            "roll=25",
            "1d20+12",
            "success",
            "damage=13 piercing",
            "DC=19",
            "-> Калигни",
        ):
            assert token in text, f"missing: {token}"

    def test_action_pegged_to_turn_started_at(self):
        """Actions don't carry their own timestamp; should sit at turn start."""
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        action_seg = next(s for s in segs if "Удар: Клыки" in s["text"])
        # turn started at 16:30:01Z, rec_start 16:15:00Z → 901s
        assert action_seg["start"] == 901.0


# ── Movements ─────────────────────────────────────────────────────────


class TestMovements:
    def test_movement_emitted_with_distance(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        moves = [s for s in segs if "переместился" in s["text"]]
        assert len(moves) == 1
        assert "Гельдала" in moves[0]["text"]
        assert "25 ft" in moves[0]["text"]
        # 16:30:20Z - 16:15:00Z = 920s
        assert moves[0]["start"] == 920.0


# ── Summary block ─────────────────────────────────────────────────────


class TestSummary:
    def test_global_summary_emitted(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        global_segs = [s for s in segs if "Итого боя" in s["text"]]
        assert len(global_segs) == 1
        text = global_segs[0]["text"]
        for token in ("rounds=1", "duration=300s", "xp=80",
                      "party_lvl=3", "difficulty=moderate"):
            assert token in text, f"missing: {token}"

    def test_per_actor_summary_emitted(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        per_actor = [s for s in segs if s["text"].startswith("Итог ")]
        assert len(per_actor) == 2
        names = {s["text"].split(":")[0] for s in per_actor}
        assert names == {"Итог Гельдала", "Итог Калигни"}

    def test_actor_summary_includes_key_stats(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        text = next(
            s["text"] for s in segs
            if s["text"].startswith("Итог Гельдала")
        )
        for token in ("pc lvl=3", "DMG_dealt=13", "hit_rate=100%",
                      "max_hit=13", "Клыки"):
            assert token in text, f"missing: {token}"

    def test_actor_summary_omits_zero_fields(self):
        """Zero / None stats shouldn't clutter the line."""
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        text = next(
            s["text"] for s in segs
            if s["text"].startswith("Итог Гельдала")
        )
        # Гельдала has damage_taken=0 → must NOT appear.
        assert "DMG_taken" not in text
        assert "healing_done" not in text  # also 0 / not set


# ── Existing whitelist regression (don't break it) ────────────────────


class TestEffectWhitelist:
    def test_blinded_condition_emitted(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        effect_segs = [s for s in segs if "получает [Ослеплён]" in s["text"]]
        assert len(effect_segs) == 1

    def test_unwhitelisted_effect_dropped(self):
        from parse_fvtt_combat import combat_to_segments
        # Add an "effect" type (not "condition") → must be filtered out.
        payload = _encounter_payload()
        payload["rounds"][1]["turns"][0]["effect_events"].append({
            "event_type": "applied",
            "effect_type": "effect",
            "effect_name": "Зеркальная эгида",
            "slug": "mirrored-aegis",
            "actor_name": "Гельдала",
            "timestamp": "2026-04-18T16:30:16.000Z",
        })
        segs = combat_to_segments(payload, _rec_start())
        assert not any("Зеркальная эгида" in s["text"] for s in segs)


# ── Order: summary lines come AFTER encounter end ─────────────────────


class TestSummaryOrder:
    def test_summary_emitted_after_encounter_end(self):
        from parse_fvtt_combat import combat_to_segments
        segs = combat_to_segments(_encounter_payload(), _rec_start())
        end_idx = next(
            i for i, s in enumerate(segs) if "Бой окончен" in s["text"]
        )
        global_idx = next(
            i for i, s in enumerate(segs) if "Итого боя" in s["text"]
        )
        actor_idx = min(
            i for i, s in enumerate(segs) if s["text"].startswith("Итог ")
        )
        assert end_idx < global_idx < actor_idx
