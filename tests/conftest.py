"""Shared pytest config: ensures scripts/ is on sys.path so tests can
``from parse_fvtt_chat import ...`` without an installed package.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
