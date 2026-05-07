"""Tests for the v0.2.1 saas_v3 benchmark validation pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from synth_datagen.saas_v3.config import (
    BenchmarkConfig,
    OutputMode,
    load_config,
)
from synth_datagen.saas_v3.engine import SaaSV3Engine
from synth_datagen.saas_v3.validate import (
    BenchmarkReport,
    compute_benchmarks,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


def test_benchmark_config_defaults() -> None:
    bc = BenchmarkConfig()
    assert bc.target_nrr_min == 1.05
    assert bc.target_nrr_max == 1.35
    assert bc.target_grr_min == 0.85
    assert bc.lifetime_churn_max == 0.40
    assert bc.trial_conversion_min == 0.15
    assert bc.trial_conversion_max == 0.40


@pytest.mark.slow
def test_compute_benchmarks_legacy_mode_returns_skipped(tmp_path) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.output.root_dir = tmp_path
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    report = compute_benchmarks(result.clean, cfg)
    assert isinstance(report, BenchmarkReport)
    assert report.skipped is True
    assert report.passed is True
    assert report.metrics == {}


@pytest.mark.slow
def test_compute_benchmarks_plg_mode_runs(tmp_path) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    cfg.output.root_dir = tmp_path
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    report = compute_benchmarks(result.clean, cfg)
    assert report.skipped is False
    # metrics keys may include NaNs on smoke data — verify the keys exist.
    assert "nrr" in report.metrics
    assert "grr" in report.metrics
    assert "lifetime_churn_rate" in report.metrics


@pytest.mark.slow
def test_compute_benchmarks_flags_lifetime_churn_above_threshold(tmp_path) -> None:
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    # Force a tight churn ceiling so smoke data fails it.
    cfg.benchmarks = BenchmarkConfig(lifetime_churn_max=0.001)
    cfg.output.root_dir = tmp_path
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    report = compute_benchmarks(result.clean, cfg)
    # Smoke data has churned accounts so the 0.001 threshold should fail.
    assert any(i.metric == "lifetime_churn_rate" for i in report.issues), (
        f"Expected churn issue, got metrics={report.metrics} issues={report.issues}"
    )
    assert report.passed is False
