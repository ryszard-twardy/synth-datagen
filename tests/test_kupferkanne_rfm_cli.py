from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
import yaml

from synth_datagen import kupferkanne_rfm_cli

import pytest

# P6 slow-test trim: the suite below runs the full saas_v3 / kupferkanne_rfm
# pipeline at production scale. Keep them out of default pytest by tagging
pytestmark = pytest.mark.slow


runner = CliRunner()


def test_kupferkanne_v3_cli_generates_dataset_from_config(tmp_path) -> None:
    base = yaml.safe_load(
        Path("configs/kupferkanne_rfm_v3.yaml").read_text(encoding="utf-8")
    )
    base["period"]["end_date"] = "2023-03-31"
    base["customers"]["target_total_customers"] = 2500
    base["validation_targets"]["target_total_orders"] = 9000
    base["validation_targets"]["unique_orders_min"] = 8000
    base["validation_targets"]["unique_orders_max"] = 10000
    base["validation_targets"]["total_rows_min"] = 12000
    base["validation_targets"]["total_rows_max"] = 18000
    base["validation_targets"]["unique_customers_target"] = 2500
    config_path = tmp_path / "kupferkanne_small_v3.yaml"
    config_path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    output_dir = tmp_path / "kupferkanne_cli_v3"

    result = runner.invoke(
        kupferkanne_rfm_cli.app,
        [
            "generate",
            "--config",
            str(config_path),
            "--output",
            str(output_dir),
            "--seed",
            "42",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "summary:" in result.output
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["period"]["start_date"] == "2023-01-01"
    assert manifest["period"]["end_date"] == "2023-03-31"
    assert (output_dir / "dimensions" / "dim_customers.csv").exists()
    assert (output_dir / "dimensions" / "dim_products.csv").exists()
    assert (output_dir / "monthly" / "orders202301.csv").exists()
    assert (output_dir / "monthly" / "items202301.csv").exists()
