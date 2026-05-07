"""Hypothesis invariants for saas_v3 plg-usage-based mode."""
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from synth_datagen.saas_v3.config import OutputMode, load_config
from synth_datagen.saas_v3.engine import SaaSV3Engine

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


@pytest.mark.slow
@settings(max_examples=8, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_subscription_events_mrr_delta_balances(tmp_path_factory, seed: int) -> None:
    """For any seed, SUM(subscription_events.mrr_delta) per account_id
    must equal the account's final MRR (within 0.01 EUR tolerance).

    This is the source-of-truth invariant for the MRR waterfall — if it
    fails, the dashboard built on subscription_events will mis-report.
    """
    cfg = load_config(SMOKE_CONFIG)
    cfg.run.mode = "plg-usage-based"
    cfg.run.seed = seed
    cfg.output.root_dir = tmp_path_factory.mktemp(f"seed_{seed}")
    result = SaaSV3Engine(cfg).generate(OutputMode.CLEAN)
    events = result.clean.materialize("subscription_events")
    account_mrr = (
        result.clean.hidden_tables["accounts_with_mrr"]
        .set_index("account_id")["mrr"]
    )
    delta_sum = events.groupby("account_id")["mrr_delta"].sum()
    for acct, mrr in account_mrr.items():
        observed = float(delta_sum.get(acct, 0.0))
        assert abs(observed - float(mrr)) < 0.01, (
            f"seed={seed} account={acct} delta_sum={observed} mrr={mrr}"
        )
