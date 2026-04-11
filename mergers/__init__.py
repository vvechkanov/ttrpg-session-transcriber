"""Timeline → list[ScriptEvent]. Импортирует только domain."""

from mergers.base import Merger
from mergers.script_merger import ScriptMerger

MERGERS: dict[str, type[Merger]] = {"script": ScriptMerger}


def get_merger(name: str) -> Merger:
    if name not in MERGERS:
        raise KeyError(f"unknown merger {name!r}; known: {sorted(MERGERS)}")
    return MERGERS[name]()


def list_mergers() -> list[str]:
    return sorted(MERGERS)
