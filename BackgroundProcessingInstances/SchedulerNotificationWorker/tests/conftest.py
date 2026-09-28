"""
Pytest configuration for the SchedulerNotificationWorker unit tests.

The worker's source lives at ../src and is not packaged (no __init__.py at
the package root), so we prepend it to sys.path here. That lets tests do
``import digest_builder`` (and friends) without needing the worker's
Docker container or a full shared.models install.

Runtime note: ``digest_builder.py`` only imports ``shared.models`` under
``TYPE_CHECKING`` so the tests do not need the shared package installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
