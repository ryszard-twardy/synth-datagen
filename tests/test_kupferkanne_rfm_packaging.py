from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

# P6 slow-test trim: the suite below runs the full saas_v3 / kupferkanne_rfm
# pipeline at production scale. Keep them out of default pytest by tagging
pytestmark = pytest.mark.slow


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_kupferkanne_v3_console_script_is_declared() -> None:
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    scripts = pyproject["project"]["scripts"]
    assert (
        scripts["synthetic-rfm-kupferkanne"] == "synth_datagen.kupferkanne_rfm_cli:app"
    )
