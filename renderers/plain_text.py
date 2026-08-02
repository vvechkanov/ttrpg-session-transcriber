"""PlainTextRenderer — совместимый с legacy merged.txt формат."""

from domain.events import ChatEvent, GameEvent, ScriptEvent, SpeechEvent

from renderers.base import Renderer


class PlainTextRenderer(Renderer):
    """Plain UTF-8 text, одна реплика = одна строка + пустая строка."""

    def render(self, events: list[ScriptEvent]) -> bytes:
        lines: list[str] = []
        for event in events:
            if isinstance(event, SpeechEvent):
                lines.append(f"{event.speaker}: {event.text}\n\n")
            elif isinstance(event, ChatEvent):
                lines.append(f"[ЧАТ] {event.author}: {event.text}\n\n")
            elif isinstance(event, GameEvent):
                lines.append(_render_game_event(event))
        return "".join(lines).encode("utf-8")


def _render_game_event(event: GameEvent) -> str:
    """Отформатировать GameEvent в одну строку для merged.txt.

    Вокабуляр действий определён в ``CombatDumpSource``. Неизвестные
    действия рендерятся обобщённым форматом ``[ИГРА] action — actor — detail``.
    """
    if event.action == "encounter_start":
        suffix = f" — {event.detail}" if event.detail else ""
        return f"[БОЙ НАЧАЛСЯ]{suffix}\n\n"
    if event.action == "encounter_end":
        return "[БОЙ ОКОНЧЕН]\n\n"
    if event.action == "initiative":
        return f"[ИНИЦИАТИВА] {event.actor}: {event.detail}\n\n"
    if event.action == "round_start":
        return f"[РАУНД {event.detail}]\n\n"
    if event.action == "turn_start":
        suffix = f" ({event.detail})" if event.detail else ""
        return f"[ХОД] {event.actor}{suffix}\n\n"
    if event.action == "action":
        return f"[ДЕЙСТВИЕ] {event.actor}: {event.detail}\n\n"
    if event.action == "hp_change":
        actor_part = f"{event.actor}: " if event.actor else ""
        return f"[HP] {actor_part}{event.detail}\n\n"
    if event.action == "effect_applied":
        return f"[ЭФФЕКТ +] {event.actor}: {event.detail}\n\n"
    if event.action == "effect_removed":
        return f"[ЭФФЕКТ −] {event.actor}: {event.detail}\n\n"
    if event.action == "effect_changed":
        return f"[ЭФФЕКТ ~] {event.actor}: {event.detail}\n\n"
    if event.action == "movement":
        return f"[ПЕРЕМЕЩЕНИЕ] {event.actor}: {event.detail}\n\n"
    if event.action == "encounter_summary_global":
        return f"[ИТОГО БОЯ] {event.detail}\n\n"
    if event.action == "encounter_summary_actor":
        return f"[ИТОГ {event.actor}] {event.detail}\n\n"
    parts = [event.action]
    if event.actor:
        parts.append(event.actor)
    if event.detail:
        parts.append(event.detail)
    return f"[ИГРА] {' — '.join(parts)}\n\n"
