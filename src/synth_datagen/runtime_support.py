"""
Helpers for reporting missing runtime dependencies in CLI entrypoints.
"""

from __future__ import annotations

RUNTIME_DEPENDENCIES = frozenset(
    {
        "faker",
        "numpy",
        "pandas",
        "pyarrow",
        "pydantic",
        "rich",
        "typer",
        "yaml",
    }
)


def is_missing_runtime_dependency(exc: ModuleNotFoundError) -> bool:
    return getattr(exc, "name", None) in RUNTIME_DEPENDENCIES


def missing_dependency_message(module_name: str) -> str:
    return (
        f"Missing runtime dependency '{module_name}'.\n"
        "This repo requires Python 3.11+.\n"
        "From the repo root, install dependencies with a 3.11+ interpreter, for example:\n"
        '  py -3.11 -m pip install -e ".[test]"'
    )
