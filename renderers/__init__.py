"""list[ScriptEvent] → bytes. Импортирует только domain."""

from renderers.base import Renderer
from renderers.plain_text import PlainTextRenderer

RENDERERS: dict[str, type[Renderer]] = {"plain-text": PlainTextRenderer}


def get_renderer(name: str) -> Renderer:
    if name not in RENDERERS:
        raise KeyError(f"unknown renderer {name!r}; known: {sorted(RENDERERS)}")
    return RENDERERS[name]()


def list_renderers() -> list[str]:
    return sorted(RENDERERS)
