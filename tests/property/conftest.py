"""Auto-mark every property test as ``slow``.

Property tests regenerate full scenario datasets per Hypothesis example,
which costs 0.3-1.0s/example even at small scale. With max_examples=3 the
property suite still spends ~25-30s wall time, well over the per-test
threshold the rest of the suite stays under. Marking the whole package
``slow`` keeps a default ``pytest`` run inside the P6 <60s budget while
``pytest -m slow`` still exercises the full property coverage.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Apply ``pytest.mark.slow`` to every test discovered under
    ``tests/property/``."""
    slow_marker = pytest.mark.slow
    for item in items:
        # ``item.path`` lives inside tests/property/ — guard with a substring
        # rather than relying on conftest scoping so a future restructure
        # doesn't silently un-mark the suite.
        if "tests/property" in item.path.as_posix() or "tests\\property" in str(
            item.path
        ):
            item.add_marker(slow_marker)
