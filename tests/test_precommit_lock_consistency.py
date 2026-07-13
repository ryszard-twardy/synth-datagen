"""Guard for the pre-commit-rev-vs-lock drift class.

Each tracked pre-commit hook rev must equal the tool version resolved in
uv.lock, which is the single source of tool-version truth. This drift
previously hit ruff (see memory/ruff-pin-coupling.md) and recurred for
mypy and bandit, realigned in #12. Without this guard, each recurrence is
caught only by manual audit.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).parents[1]
_PRECOMMIT_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"
_UV_LOCK = _REPO_ROOT / "uv.lock"

# Tracked pre-commit repo URL -> uv.lock package name. Scope is limited to
# tools with a uv.lock counterpart; pre-commit/pre-commit-hooks is
# intentionally excluded (no locked Python package to compare against).
_HOOK_TO_PACKAGE = {
    "https://github.com/PyCQA/bandit": "bandit",
    "https://github.com/astral-sh/ruff-pre-commit": "ruff",
    "https://github.com/pre-commit/mirrors-mypy": "mypy",
}

_CASES = sorted(_HOOK_TO_PACKAGE.items())


def _precommit_revs() -> dict[str, str]:
    with _PRECOMMIT_CONFIG.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    return {
        repo["repo"]: repo["rev"]
        for repo in config["repos"]
        if repo.get("rev") is not None
    }


def _locked_versions() -> dict[str, str]:
    with _UV_LOCK.open("rb") as fh:
        lock = tomllib.load(fh)
    return {package["name"]: package["version"] for package in lock["package"]}


def _strip_leading_v(rev: str) -> str:
    """Normalize a mirror tag (e.g. v2.1.0) to a bare version (2.1.0).

    mirrors-mypy and ruff-pre-commit tag with a leading ``v``; PyCQA/bandit
    does not. uv.lock stores bare versions, so strip a single leading ``v``.
    """
    return rev[1:] if rev.startswith("v") else rev


@pytest.mark.parametrize(
    ("repo_url", "package"),
    _CASES,
    ids=[package for _, package in _CASES],
)
def test_precommit_rev_matches_locked_version(repo_url: str, package: str) -> None:
    revs = _precommit_revs()
    locked = _locked_versions()

    assert repo_url in revs, (
        f"{repo_url} is expected in .pre-commit-config.yaml but was not "
        f"found; update the mapping in this test or the config"
    )
    assert package in locked, f"{package!r} is expected in uv.lock but was not found"

    hook_version = _strip_leading_v(revs[repo_url])
    locked_version = locked[package]

    assert hook_version == locked_version, (
        f"pre-commit rev for {package} is {revs[repo_url]!r} "
        f"(normalized {hook_version!r}) but uv.lock has {locked_version!r}; "
        f"align the .pre-commit-config.yaml rev to uv.lock"
    )
