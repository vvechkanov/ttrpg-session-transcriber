"""CombatDumpSource — encounter dump из FVTT (PF2e) в ``GameLogEntry``-и.

Источник данных — ``Бой*.json`` / ``combat*.json`` / ``encounter*.json``,
которые экспортируются модулем `pf2e-combat-chronicle` в Foundry VTT.
Все timestamp-ы в файле — UTC (без эвристик taimezone, как в FvttChat).

Стратегия — "максимум информации": вытаскиваем всё, что несёт смысл для
последующего пересказа боя. Фильтруем только явный шум:

* ``position_start`` / ``position_end`` — сырые координаты, бесполезны
  без карты;
* ``effects_start`` / ``effects_end`` — снимки эффектов, на каждом ходу
  одно и то же; реальные изменения уже приходят через ``effect_events``;
* ``chat_messages[]`` внутри turn-а — хранит только id+timestamp без
  текста; сами сообщения уже разбираются ``FvttChatSource``.

Вокабуляр ``GameLogEntry.action``:

    encounter_start            — старт встречи (``detail`` = scene_name)
    initiative                 — entry на боевого участника при старте
                                 (``actor`` = name, ``detail`` = init/level/type)
    round_start                — начало раунда инициативы
    turn_start                 — ход персонажа (``detail`` = HP X/Y [+temp])
    action                     — индивидуальное действие в ход
                                 (удар/заклинание/навык/...)
    hp_change                  — изменение HP с timestamp-ом
    effect_applied             — состояние/эффект применён
    effect_removed             — снят
    effect_changed             — изменился (значение)
    movement                   — перемещение токена
    encounter_end              — конец встречи
    encounter_summary_global   — общая статистика (rounds, duration, XP)
    encounter_summary_actor    — per-actor статистика (DMG, hit_rate, etc.)

События с ``at < 0`` (бой раньше старта Craig segment-а) тихо
отбрасываются — это согласуется с поведением ``FvttChatSource``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from domain.annotations import GameLogEntry
from sources.base import Source
from sources.game_log.fvtt_chat import parse_info_start_time


class CombatDumpSource(Source):
    """Game log source — encounter dump (Бой*.json)."""

    name = "combat-dump"

    def __init__(
        self,
        combat_log_path: Path,
        info_file_path: Path | None = None,
    ) -> None:
        self.combat_log_path = combat_log_path
        self.info_file_path = info_file_path

    def extract(self, session_dir: Path) -> list[GameLogEntry]:
        """Прочитать combat dump и вернуть ``list[GameLogEntry]``.

        ``at`` для каждой записи — секунды от старта Craig recording-а
        (как в ``FvttChatSource``). Записи с ``at < 0`` отбрасываются.
        """
        info_path = self.info_file_path
        if info_path is None:
            candidate = session_dir / "info.txt"
            if not candidate.exists():
                raise FileNotFoundError(
                    f"info.txt не найден в {session_dir}; "
                    "передайте info_file_path явно для выравнивания combat timestamps"
                )
            info_path = candidate

        rec_start = parse_info_start_time(info_path)

        with open(self.combat_log_path, encoding="utf-8") as f:
            data = json.load(f)

        entries: list[GameLogEntry] = []

        encounter_started_at = data.get("started_at")
        if encounter_started_at:
            entries.append(
                _entry(
                    encounter_started_at,
                    rec_start,
                    actor="",
                    action="encounter_start",
                    detail=str(data.get("scene_name") or ""),
                )
            )

            # Инициатива — выводим на тот же момент, что и encounter_start.
            for combatant in data.get("initiative_order", []) or []:
                entries.append(
                    _entry(
                        encounter_started_at,
                        rec_start,
                        actor=str(combatant.get("name") or ""),
                        action="initiative",
                        detail=_format_initiative(combatant),
                    )
                )

        for round_data in data.get("rounds", []) or []:
            round_number = round_data.get("round_number")
            round_started_at = round_data.get("started_at")
            # round 0 — служебный раунд до инициативы (всегда пустой turns,
            # timestamp совпадает с encounter.started_at). Не дублируем.
            if round_started_at and round_number not in (None, 0):
                entries.append(
                    _entry(
                        round_started_at,
                        rec_start,
                        actor="",
                        action="round_start",
                        detail=str(round_number),
                    )
                )

            for turn_data in round_data.get("turns", []) or []:
                _emit_turn_entries(turn_data, rec_start, entries)

        encounter_ended_at = data.get("ended_at")
        if encounter_ended_at:
            entries.append(
                _entry(
                    encounter_ended_at,
                    rec_start,
                    actor="",
                    action="encounter_end",
                    detail="",
                )
            )

            # Summary прицепляем к ended_at с микросдвигом в epsilon-секунду,
            # чтобы он гарантированно отсортировался ПОСЛЕ encounter_end и
            # перед любыми последующими событиями (стабильная сортировка
            # сохранит исходный порядок entries в одной точке времени).
            summary = data.get("summary") or {}
            global_stats = summary.get("global") or {}
            if global_stats:
                entries.append(
                    _entry(
                        encounter_ended_at,
                        rec_start,
                        actor="",
                        action="encounter_summary_global",
                        detail=_format_global_summary(global_stats),
                    )
                )

            per_actor = summary.get("per_actor") or {}
            for actor_id, stats in per_actor.items():
                name = stats.get("name") or actor_id
                entries.append(
                    _entry(
                        encounter_ended_at,
                        rec_start,
                        actor=str(name),
                        action="encounter_summary_actor",
                        detail=_format_actor_summary(stats),
                    )
                )

        return [e for e in entries if e.at >= 0]


def _emit_turn_entries(
    turn: dict, rec_start: datetime, entries: list[GameLogEntry]
) -> None:
    """Развернуть один turn в набор GameLogEntry-и: ход, действия, HP, эффекты, перемещения."""
    turn_started_at = turn.get("started_at")
    combatant_name = turn.get("combatant_name") or ""

    if turn_started_at and combatant_name:
        entries.append(
            _entry(
                turn_started_at,
                rec_start,
                actor=combatant_name,
                action="turn_start",
                detail=_format_turn_hp(turn),
            )
        )

    # Действия в ход — у самих action-ов нет timestamp-а, привязываем к
    # turn_started_at. Порядок внутри одного момента сохранится через
    # стабильную сортировку в мерджере.
    if turn_started_at:
        for action in turn.get("actions", []) or []:
            entries.append(
                _entry(
                    turn_started_at,
                    rec_start,
                    actor=combatant_name,
                    action="action",
                    detail=_format_action(action),
                )
            )

    for hp_change in turn.get("hp_changes", []) or []:
        ts = hp_change.get("timestamp")
        if not ts:
            continue
        entries.append(
            _entry(
                ts,
                rec_start,
                actor=str(hp_change.get("actor_name") or ""),
                action="hp_change",
                detail=_format_hp_change(hp_change),
            )
        )

    for ev in turn.get("effect_events", []) or []:
        ts = ev.get("timestamp")
        if not ts:
            continue
        event_type = ev.get("event_type") or "changed"
        action_name = f"effect_{event_type}"
        entries.append(
            _entry(
                ts,
                rec_start,
                actor=str(ev.get("actor_name") or ""),
                action=action_name,
                detail=_format_effect_event(ev),
            )
        )

    for mv in turn.get("movements", []) or []:
        ts = mv.get("timestamp")
        if not ts:
            continue
        entries.append(
            _entry(
                ts,
                rec_start,
                actor=str(mv.get("token_name") or ""),
                action="movement",
                detail=_format_movement(mv),
            )
        )


# ── Форматтеры detail-строк ────────────────────────────────────────────


def _format_initiative(combatant: dict) -> str:
    parts = []
    init = combatant.get("initiative_total")
    if init is not None:
        parts.append(f"init={init}")
    level = combatant.get("actor_level")
    if level is not None:
        parts.append(f"lvl={level}")
    actor_type = combatant.get("actor_type")
    if actor_type:
        parts.append(str(actor_type))
    return ", ".join(parts)


def _format_turn_hp(turn: dict) -> str:
    hp_start = turn.get("hp_start")
    hp_max = turn.get("hp_max")
    temp = turn.get("temp_hp_start") or 0
    if hp_start is None or hp_max is None:
        return ""
    detail = f"HP {hp_start}/{hp_max}"
    if temp:
        detail += f" (+{temp} temp)"
    return detail


def _format_action(action: dict) -> str:
    parts: list[str] = []
    name = action.get("action_name") or action.get("title") or ""
    if name:
        parts.append(str(name))
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
        damage_type = action.get("damage_type") or ""
        parts.append(f"damage={damage}{(' ' + damage_type) if damage_type else ''}")
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
    target_names = [str(t.get("name") or "") for t in targets if t.get("name")]
    if target_names:
        parts.append(f"-> {', '.join(target_names)}")
    return " | ".join(parts)


def _format_hp_change(hp_change: dict) -> str:
    delta = hp_change.get("delta")
    parts: list[str] = []
    if delta is not None:
        sign = "+" if delta >= 0 else ""
        parts.append(f"{sign}{delta} HP")
    source = hp_change.get("source")
    if source:
        parts.append(f"from {source}")
    damage_type = hp_change.get("damage_type")
    if damage_type:
        parts.append(f"({damage_type})")
    return " ".join(parts)


def _format_effect_event(ev: dict) -> str:
    parts: list[str] = []
    name = ev.get("effect_name") or ""
    if name:
        parts.append(str(name))
    eff_type = ev.get("effect_type")
    if eff_type:
        parts.append(f"[{eff_type}]")
    if ev.get("event_type") == "changed":
        old_v = ev.get("old_value")
        new_v = ev.get("new_value")
        if old_v is not None or new_v is not None:
            parts.append(f"{old_v} -> {new_v}")
    return " ".join(parts)


def _format_movement(mv: dict) -> str:
    distance = mv.get("distance_ft")
    if distance is None:
        return ""
    return f"{distance} ft"


def _format_global_summary(stats: dict) -> str:
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
    """Per-actor сводка: формат компактный, машинно-парсимый, отбрасываем
    None / 0-значения когда они малозначимы."""
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
        item = max_hit.get("item_name") or ""
        item_str = f" ({item})" if item else ""
        parts.append(f"max_hit={max_hit_value}{item_str}")
    one_shots = stats.get("one_shots") or []
    if one_shots:
        names = [str(o.get("name") or "") for o in one_shots if o.get("name")]
        if names:
            parts.append(f"one_shots=[{', '.join(names)}]")
    return " | ".join(parts)


# ── Конструктор GameLogEntry ──────────────────────────────────────────


def _entry(
    timestamp_iso: str,
    rec_start: datetime,
    *,
    actor: str,
    action: str,
    detail: str,
) -> GameLogEntry:
    """Сконвертировать ISO8601 UTC timestamp в ``GameLogEntry`` относительно rec_start."""
    raw = timestamp_iso.replace("Z", "+00:00")
    moment = datetime.fromisoformat(raw)
    at = (moment - rec_start).total_seconds()
    return GameLogEntry(at=at, actor=actor, action=action, detail=detail)
