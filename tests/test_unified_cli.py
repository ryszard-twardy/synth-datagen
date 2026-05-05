"""Tests for the unified ``synth-datagen`` CLI introduced in audit P1-2.

The four legacy console scripts (synthetic-data, synthetic-monthly-sales,
synthetic-saas, synthetic-rfm-kupferkanne) remain as transitional aliases;
the new top-level command exposes one sub-command per scenario.
"""

from __future__ import annotations

from pathlib import Path
import tomllib

from typer.testing import CliRunner

from synth_datagen.cli import app

REPO_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_unified_cli_console_script_is_declared() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    assert scripts["synth-datagen"] == "synth_datagen.cli:app"


def test_unified_cli_help_lists_every_subcommand() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for sub in [
        "retail", "saas", "fintech", "logistics",
        "scenarios", "monthly-sales", "kupferkanne-rfm", "saas-v3",
    ]:
        assert sub in result.output, f"Missing sub-command: {sub}"


def test_unified_cli_scenario_help_runs() -> None:
    """Each scenario sub-command must at least show its own --help."""
    for scenario in ("retail", "saas", "fintech", "logistics"):
        result = runner.invoke(app, [scenario, "--help"])
        assert result.exit_code == 0, f"{scenario} help failed: {result.output}"
        assert "--seed" in result.output
        assert "--output" in result.output


def test_license_file_present_and_declared() -> None:
    """Audit P0-1: repo must ship a LICENSE file and pyproject must declare
    the matching license — otherwise default copyright blocks any reuse."""
    license_path = REPO_ROOT / "LICENSE"
    assert license_path.exists(), "LICENSE file is missing"
    text = license_path.read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Permission is hereby granted" in text

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["license"] == {"text": "MIT"}
    assert "License :: OSI Approved :: MIT License" in pyproject["project"]["classifiers"]


def test_legacy_aliases_still_declared() -> None:
    """Old entry-point names must remain so existing scripts keep working."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    assert scripts["synthetic-data"] == "synth_datagen.main:app"
    assert scripts["synthetic-monthly-sales"] == "synth_datagen.monthly_sales_cli:app"
    assert scripts["synthetic-saas"] == "synth_datagen.saas_v3.cli:app"
    assert scripts["synthetic-rfm-kupferkanne"] == "synth_datagen.kupferkanne_rfm_cli:app"
