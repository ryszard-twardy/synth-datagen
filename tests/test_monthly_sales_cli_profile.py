from __future__ import annotations

import json

from typer.testing import CliRunner

from synth_datagen import monthly_sales_cli


runner = CliRunner()


def test_monthly_sales_cli_profile_generates_manifest(tmp_path) -> None:
    profile_path = tmp_path / "monthly_sales.audit.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "period:",
                "  start_date: 2025-01-01",
                "  end_date: 2025-02-28",
                "volume:",
                "  max_orders_per_month: 80",
                "  trend_mode: growth",
                "  start_ratio: 0.5",
                "  seasonality_strength: 0.1",
                "  volatility_strength: 0.02",
                "bad_data:",
                "  enabled: true",
                "  normalized:",
                "    null_required_rate: 0.02",
                "    negative_numeric_rate: 0.02",
                "    monetary_outlier_rate: 0.02",
                "  flat:",
                "    duplicate_orderid_rate: 0.02",
                "    bad_orderdate_rate: 0.02",
                "    mixed_ordervalue_format_rate: 0.02",
                "    null_required_rate: 0.02",
                "    negative_ordervalue_rate: 0.02",
                "output:",
                "  layout: both",
                "  include_flat: true",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "monthly_sales_profile"

    result = runner.invoke(
        monthly_sales_cli.app,
        [
            "generate",
            "--profile-config",
            str(profile_path),
            "--output",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile_config"].endswith("monthly_sales.audit.yaml")
    assert (
        manifest["defect_summary"]["normalized"]["null_required_fields"]["actual_count"]
        > 0
    )
    assert (
        manifest["defect_summary"]["flat"]["bad_orderdate_formats"]["actual_count"] > 0
    )


def test_monthly_sales_cli_profile_allows_discount_override(tmp_path) -> None:
    profile_path = tmp_path / "monthly_sales.profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "period:",
                "  start_date: 2025-01-01",
                "  end_date: 2025-01-31",
                "volume:",
                "  max_orders_per_month: 30",
                "output:",
                "  layout: combined",
                "  include_flat: false",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "monthly_sales_profile_override"

    result = runner.invoke(
        monthly_sales_cli.app,
        [
            "generate",
            "--profile-config",
            str(profile_path),
            "--output",
            str(output_dir),
            "--no-discount-variation",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["discount_variation"] is False
