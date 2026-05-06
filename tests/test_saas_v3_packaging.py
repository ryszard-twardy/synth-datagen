from __future__ import annotations

from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_saas_v3_console_script_is_declared() -> None:
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    scripts = pyproject["project"]["scripts"]
    assert scripts["synthetic-saas"] == "synth_datagen.saas_v3.cli:app"
