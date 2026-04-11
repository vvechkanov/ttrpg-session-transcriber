"""Merger ABC: Timeline → list[ScriptEvent]."""

from abc import ABC, abstractmethod

from domain.events import ScriptEvent
from domain.timeline import Timeline


class Merger(ABC):
    @abstractmethod
    def merge(self, timeline: Timeline) -> list[ScriptEvent]: ...
