"""Guards the version-coupling drift documented in memory/version-coupling.md
(recurred at v0.2.0, v0.2.1, v0.3.2) – replaces the "no test catches it" gap.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import synth_datagen


def test_runtime_version_matches_packaged_version() -> None:
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as fh:
        pyproject = tomllib.load(fh)
    packaged_version = pyproject["project"]["version"]
    runtime_version = synth_datagen.__version__

    assert runtime_version == packaged_version, (
        f"packaged version (pyproject.toml [project].version) is "
        f"{packaged_version!r} but synth_datagen.__version__ is "
        f"{runtime_version!r}"
    )
