"""Tests for the v0.2.1 subscription_events table (plg-usage-based mode)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from synth_datagen.saas_v3.config import OutputMode, load_config
from synth_datagen.saas_v3.engine import SaaSV3Engine

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


pytestmark = pytest.mark.slow  # full pipeline tests


def _plg_config(tmp_path):
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    cfg.output.root_dir = tmp_path
    return cfg


def _legacy_config(tmp_path):
    cfg = load_config(SMOKE_CONFIG)
    cfg.output.root_dir = tmp_path
    return cfg


def test_legacy_mode_omits_subscription_events(tmp_path) -> None:
    cfg = _legacy_config(tmp_path)
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    assert "subscription_events" not in result.clean.tables


def test_plg_mode_emits_all_five_movement_types(tmp_path) -> None:
    result = SaaSV3Engine(_plg_config(tmp_path)).generate(OutputMode.CLEAN)
    events = result.clean.materialize("subscription_events")
    assert {"new", "expansion", "contraction", "churn", "reactivation"}.issubset(
        set(events["event_type"].unique())
    )


def test_plg_mode_event_types_have_signed_deltas(tmp_path) -> None:
    result = SaaSV3Engine(_plg_config(tmp_path)).generate(OutputMode.CLEAN)
    events = result.clean.materialize("subscription_events")
    assert (events.loc[events.event_type == "new", "mrr_delta"] > 0).all()
    assert (events.loc[events.event_type == "expansion", "mrr_delta"] > 0).all()
    assert (events.loc[events.event_type == "contraction", "mrr_delta"] < 0).all()
    assert (events.loc[events.event_type == "churn", "mrr_delta"] < 0).all()
    assert (events.loc[events.event_type == "reactivation", "mrr_delta"] > 0).all()


def test_plg_mode_mrr_delta_sum_matches_account_mrr(tmp_path) -> None:
    result = SaaSV3Engine(_plg_config(tmp_path)).generate(OutputMode.CLEAN)
    accounts = result.clean.hidden_tables["accounts_with_mrr"].set_index("account_id")["mrr"]
    events = result.clean.materialize("subscription_events")
    delta_sum = events.groupby("account_id")["mrr_delta"].sum()
    sample_size = min(50, len(accounts))
    sampled = accounts.sample(sample_size, random_state=0)
    for acct, mrr in sampled.items():
        observed = float(delta_sum.get(acct, 0.0))
        assert abs(observed - float(mrr)) < 0.01, (
            f"account={acct} delta_sum={observed} mrr={mrr}"
        )


def test_plg_mode_reproducible(tmp_path) -> None:
    a = SaaSV3Engine(_plg_config(tmp_path / "a")).generate(OutputMode.CLEAN).clean.materialize("subscription_events")
    b = SaaSV3Engine(_plg_config(tmp_path / "b")).generate(OutputMode.CLEAN).clean.materialize("subscription_events")
    pd.testing.assert_frame_equal(a, b)


def test_plg_mode_event_id_format(tmp_path) -> None:
    from synth_datagen.saas_v3.ids import pattern_for
    result = SaaSV3Engine(_plg_config(tmp_path)).generate(OutputMode.CLEAN)
    events = result.clean.materialize("subscription_events")
    assert events["event_id"].astype(str).str.fullmatch(pattern_for("subscription_event_id")).all()
