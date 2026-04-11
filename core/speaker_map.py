"""Re-export of domain.speaker_map helpers for UI consumers.

Exists so ``ui/`` can load a speaker map without reaching into ``domain/``
directly, honoring the dependency rule ``ui → core → ...``.
"""

from domain.speaker_map import load_speaker_map  # noqa: F401
