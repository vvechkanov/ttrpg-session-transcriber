"""Pytest configuration for discord-session-transcriber test suite.

Inserts the project root into sys.path so that `import core`, `import domain`,
`import sources`, etc. work when running pytest from the repo root without
installing the package.
"""

import sys
from pathlib import Path

# Project root = parent of tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
