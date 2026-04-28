from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from src.saas_v3.cli import app


runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


def test_saas_v3_cli_smoke_test_writes_outputs(tmp_path) -> None:
    output_dir = tmp_path / "smoke_run"
    result = runner.invoke(app, ["smoke-test", "--config", str(SMOKE_CONFIG), "--output", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert (output_dir / "metadata" / "effective_config.yaml").exists()
    assert (output_dir / "metadata" / "manifest_clean.json").exists()
    assert (output_dir / "metadata" / "manifest_dirty.json").exists()
    assert (output_dir / "clean" / "csv" / "accounts.csv").exists()
    assert (output_dir / "dirty" / "csv" / "product_events.csv").exists()
