"""Tier 1 — CombatDumpSource parse tests.

Использует синтетический мини-encounter dump (написан в коде, не читается
с диска), чтобы тесты не зависели от реальных Бой*.json. Проверяем:
* основной вокабуляр действий (encounter_start/end, initiative, round/turn,
  action, hp_change, effect_*, movement);
* парсинг summary (global + per_actor);
* фильтрацию событий до старта Craig (at < 0);
* отсутствие info.txt — корректный FileNotFoundError.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _encounter_payload() -> dict:
    """Минимальный encounter dump со всеми ключевыми полями."""
    return {
        "encounter_id": "enc-1",
        "scene_name": "Scene A",
        "started_at": "2026-04-18T16:30:00.000Z",  # 900s после Craig start
        "ended_at": "2026-04-18T16:35:00.000Z",  # 1200s
        "initiative_order": [
            {
                "name": "Гельдала",
                "actor_id": "A",
                "actor_level": 3,
                "actor_type": "pc",
                "initiative_total": 25,
            },
            {
                "name": "Калигни",
                "actor_id": "B",
                "actor_level": 2,
                "actor_type": "npc",
                "initiative_total": 20,
            },
        ],
        "rounds": [
            # round 0 — служебный, не должен породить round_start
            {"round_number": 0, "started_at": "2026-04-18T16:30:00.000Z", "turns": []},
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
                        "temp_hp_start": 5,
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
                                "timestamp": "2026-04-18T16:30:10.000Z",  # 910s
                                "delta": -13,
                                "source": "Клыки",
                                "damage_type": "piercing",
                            },
                        ],
                        "effect_events": [
                            {
                                "event_type": "applied",
                                "effect_name": "Ослеплён",
                                "effect_type": "condition",
                                "actor_name": "Калигни",
                                "timestamp": "2026-04-18T16:30:15.000Z",  # 915s
                            },
                        ],
                        "movements": [
                            {
                                "token_name": "Гельдала",
                                "timestamp": "2026-04-18T16:30:20.000Z",  # 920s
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


@pytest.fixture
def combat_session(tmp_path: Path) -> Path:
    """Session dir с info.txt (Craig start = 16:15:16Z) + Бой 1.txt."""
    info = tmp_path / "info.txt"
    info.write_text("Start time: 2026-04-18T16:15:00.000Z\n", encoding="utf-8")
    combat = tmp_path / "Бой 1.json"
    combat.write_text(
        json.dumps(_encounter_payload(), ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


class TestCombatDumpSourceCore:
    def test_extracts_encounter_start(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        starts = [e for e in entries if e.action == "encounter_start"]
        assert len(starts) == 1
        # 16:30:00Z - 16:15:00Z = 900s
        assert starts[0].at == 900.0
        assert starts[0].detail == "Scene A"

    def test_extracts_initiative_per_combatant(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        inits = [e for e in entries if e.action == "initiative"]
        assert {e.actor for e in inits} == {"Гельдала", "Калигни"}
        # detail содержит init/lvl/type
        geldala = next(e for e in inits if e.actor == "Гельдала")
        assert "init=25" in geldala.detail
        assert "lvl=3" in geldala.detail
        assert "pc" in geldala.detail

    def test_round_zero_is_skipped(self, combat_session: Path):
        """Служебный round 0 не должен породить round_start."""
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        rounds = [e for e in entries if e.action == "round_start"]
        assert [e.detail for e in rounds] == ["1"]

    def test_extracts_turn_with_hp_detail(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        turns = [e for e in entries if e.action == "turn_start"]
        assert len(turns) == 1
        assert turns[0].actor == "Гельдала"
        assert "HP 33/33" in turns[0].detail
        assert "+5 temp" in turns[0].detail

    def test_extracts_action_with_full_detail(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        actions = [e for e in entries if e.action == "action"]
        assert len(actions) == 1
        d = actions[0].detail
        assert "Удар: Клыки" in d
        assert "strike" in d
        assert "roll=25" in d
        assert "(1d20+12)" in d
        assert "success" in d
        assert "damage=13 piercing" in d
        assert "DC=19" in d
        assert "-> Калигни" in d

    def test_extracts_hp_change_with_own_timestamp(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        hp_events = [e for e in entries if e.action == "hp_change"]
        assert len(hp_events) == 1
        # 16:30:10Z - 16:15:00Z = 910s
        assert hp_events[0].at == 910.0
        assert hp_events[0].actor == "Калигни"
        assert "-13 HP" in hp_events[0].detail
        assert "Клыки" in hp_events[0].detail
        assert "piercing" in hp_events[0].detail

    def test_extracts_effect_events(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        effects = [e for e in entries if e.action == "effect_applied"]
        assert len(effects) == 1
        assert effects[0].actor == "Калигни"
        assert "Ослеплён" in effects[0].detail

    def test_extracts_movement(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        moves = [e for e in entries if e.action == "movement"]
        assert len(moves) == 1
        assert moves[0].actor == "Гельдала"
        assert "25 ft" in moves[0].detail

    def test_extracts_encounter_end_and_summaries(self, combat_session: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        ends = [e for e in entries if e.action == "encounter_end"]
        assert len(ends) == 1
        global_summary = [e for e in entries if e.action == "encounter_summary_global"]
        assert len(global_summary) == 1
        assert "rounds=1" in global_summary[0].detail
        assert "xp=80" in global_summary[0].detail
        assert "difficulty=moderate" in global_summary[0].detail
        actor_summaries = [
            e for e in entries if e.action == "encounter_summary_actor"
        ]
        assert {e.actor for e in actor_summaries} == {"Гельдала", "Калигни"}

    def test_summaries_render_after_encounter_end_in_sorted_order(
        self, combat_session: Path
    ):
        """Summary entries имеют тот же at, что и encounter_end, но идут после.

        Гарантия достигается стабильной сортировкой в мерджере + порядком
        emit-а в extract: encounter_end → summary_global → summary_actor.
        """
        from sources.game_log.combat_dump import CombatDumpSource
        src = CombatDumpSource(combat_log_path=combat_session / "Бой 1.json")
        entries = src.extract(combat_session)
        end_idx = next(i for i, e in enumerate(entries) if e.action == "encounter_end")
        global_idx = next(
            i for i, e in enumerate(entries)
            if e.action == "encounter_summary_global"
        )
        actor_idx = min(
            i for i, e in enumerate(entries)
            if e.action == "encounter_summary_actor"
        )
        assert end_idx < global_idx < actor_idx

    def test_filters_events_before_recording(self, tmp_path: Path):
        """Если бой стартанул до Craig segment-а — все события отбрасываются."""
        from sources.game_log.combat_dump import CombatDumpSource
        # Craig start ПОЗЖЕ encounter_start.
        info = tmp_path / "info.txt"
        info.write_text("Start time: 2026-04-18T20:00:00.000Z\n", encoding="utf-8")
        combat = tmp_path / "Бой 1.json"
        combat.write_text(
            json.dumps(_encounter_payload(), ensure_ascii=False), encoding="utf-8"
        )
        src = CombatDumpSource(combat_log_path=combat)
        assert src.extract(tmp_path) == []

    def test_missing_info_file_raises(self, tmp_path: Path):
        from sources.game_log.combat_dump import CombatDumpSource
        combat = tmp_path / "Бой 1.json"
        combat.write_text(
            json.dumps(_encounter_payload(), ensure_ascii=False), encoding="utf-8"
        )
        src = CombatDumpSource(combat_log_path=combat)
        empty_dir = tmp_path / "no_info"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            src.extract(empty_dir)
