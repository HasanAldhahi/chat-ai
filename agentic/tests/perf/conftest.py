"""Shared fixtures for the Phase 5 / Task 5.3 perf suite.

All tests are auto-tagged ``@pytest.mark.perf`` so they only run when
explicitly requested with ``pytest -m perf``. They are advisory and
should not block PR merge — perf bounds depend on host load.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):  # noqa: D401
    perf = pytest.mark.perf
    for item in items:
        if "/tests/perf/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(perf)
