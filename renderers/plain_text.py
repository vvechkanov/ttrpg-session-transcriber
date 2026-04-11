"""PlainTextRenderer — совместимый с legacy merged.txt формат."""

from core.ui_contract import UIConfig
from domain.events import ChatEvent, ScriptEvent, SpeechEvent

from renderers.base import Renderer


class PlainTextRenderer(Renderer):
    """Plain UTF-8 text, одна реплика = одна строка + пустая строка."""

    #: Module UI Contract binding (ADR-016). Resolves to
    #: ``ui/templates/renderer_template.py`` (Phase 8 stub) — renderer has
    #: no user-visible options in Phase 4, the template only shows the
    #: target file name + format hint.
    ui_config = UIConfig(
        template="renderer",
        params={"renderer_id": "plain-text", "filename": "merged.txt"},
    )

    def render(self, events: list[ScriptEvent]) -> bytes:
        lines: list[str] = []
        for event in events:
            if isinstance(event, SpeechEvent):
                lines.append(f"{event.speaker}: {event.text}\n\n")
            elif isinstance(event, ChatEvent):
                lines.append(f"[ЧАТ] {event.author}: {event.text}\n\n")
            else:  # GameEvent — not produced in P2, but handle defensively
                continue
        return "".join(lines).encode("utf-8")
