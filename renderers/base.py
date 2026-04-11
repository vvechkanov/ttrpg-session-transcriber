"""Renderer ABC: list[ScriptEvent] → bytes."""

from abc import ABC, abstractmethod

from domain.events import ScriptEvent


class Renderer(ABC):
    @abstractmethod
    def render(self, events: list[ScriptEvent]) -> bytes: ...
