from __future__ import annotations

import run_demo
from typer.testing import CliRunner

from synth_datagen import kupferkanne_rfm_cli
from synth_datagen import monthly_sales_cli
from synth_datagen.main import app as main_app


runner = CliRunner()


def _missing_faker() -> None:
    raise ModuleNotFoundError("No module named 'faker'", name="faker")


def test_main_generate_reports_missing_runtime_dependency(monkeypatch):
    monkeypatch.setattr("synth_datagen.main._load_pipeline", _missing_faker)

    result = runner.invoke(main_app, ["generate"])

    assert result.exit_code == 1
    assert "Missing runtime dependency 'faker'." in result.output
    assert "Python 3.11+" in result.output


def test_monthly_generate_help_does_not_load_runtime(monkeypatch):
    def fail_if_called():
        raise AssertionError("monthly runtime should not load for --help")

    monkeypatch.setattr(monthly_sales_cli, "_load_monthly_runtime", fail_if_called)

    result = runner.invoke(monthly_sales_cli.app, ["generate", "--help"])

    assert result.exit_code == 0
    assert "--profile-config" in result.output
    assert "--layout" in result.output
    assert "discount-vari" in result.output


def test_monthly_generate_rejects_invalid_layout_before_runtime_import(monkeypatch):
    def fail_if_called():
        raise AssertionError("monthly runtime should not load for invalid layout")

    monkeypatch.setattr(monthly_sales_cli, "_load_monthly_runtime", fail_if_called)

    result = runner.invoke(
        monthly_sales_cli.app,
        [
            "generate",
            "--month",
            "2025-01",
            "--orders-per-month",
            "10",
            "--layout",
            "invalid",
        ],
    )

    assert result.exit_code == 2
    assert "Layout must be one of:" in result.output
    assert "sales-files" in result.output


def test_monthly_generate_reports_missing_runtime_dependency(monkeypatch):
    monkeypatch.setattr(monthly_sales_cli, "_load_monthly_runtime", _missing_faker)

    result = runner.invoke(
        monthly_sales_cli.app,
        [
            "generate",
            "--month",
            "2025-01",
            "--orders-per-month",
            "10",
            "--layout",
            "monthly",
        ],
    )

    assert result.exit_code == 1
    assert "Missing runtime dependency 'faker'." in result.output


def test_monthly_generate_profile_rejects_conflicting_flags(monkeypatch, tmp_path):
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "period:\n  start_date: 2025-01-01\n  end_date: 2025-01-31\nvolume:\n  max_orders_per_month: 25\n",
        encoding="utf-8",
    )

    def fake_runtime():
        def fail_if_profile_loaded(_path):
            raise AssertionError("profile should not be loaded when CLI flags conflict")

        return object, object, object, fail_if_profile_loaded

    monkeypatch.setattr(monthly_sales_cli, "_load_monthly_runtime", fake_runtime)

    result = runner.invoke(
        monthly_sales_cli.app,
        ["generate", "--profile-config", str(profile_path), "--month", "2025-01"],
    )

    assert result.exit_code == 2
    assert "--profile-config" in result.output
    assert "--month" in result.output


def test_run_demo_reports_missing_runtime_dependency(monkeypatch, capsys):
    monkeypatch.setattr(run_demo, "_load_pipeline", _missing_faker)

    exit_code = run_demo.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Missing runtime dependency 'faker'." in captured.err


def test_kupferkanne_help_does_not_load_runtime(monkeypatch):
    def fail_if_called():
        raise AssertionError("kupferkanne runtime should not load for --help")

    monkeypatch.setattr(kupferkanne_rfm_cli, "_load_runtime", fail_if_called)

    result = runner.invoke(kupferkanne_rfm_cli.app, ["generate", "--help"])

    assert result.exit_code == 0
    assert "--config" in result.output
    assert "discount-varia" in result.output


def test_kupferkanne_reports_missing_runtime_dependency(monkeypatch):
    monkeypatch.setattr(kupferkanne_rfm_cli, "_load_runtime", _missing_faker)

    result = runner.invoke(
        kupferkanne_rfm_cli.app,
        ["generate", "--config", "configs/kupferkanne_rfm_v3.yaml"],
    )

    assert result.exit_code == 1
    assert "Missing runtime dependency 'faker'." in result.output
