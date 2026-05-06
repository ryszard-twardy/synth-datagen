"""Regression test for the empty-feature-pool crash in saas.

Hypothesis property testing (P3) discovered that ``seed=103`` at small
scale (features=20) produces a feature dimension where no row has
``plan_min == 'free'``. ``_build_feature_usage`` then calls
``self.rng.choice(feature_by_rank[0])`` against an empty list, which
numpy raises as ``ValueError: a cannot be empty unless no samples are
taken``.

The fix wraps the feature-pool lookup with a fallback to the full
features list — graceful degradation that preserves behaviour for any
seed where the requested rank's pool was already non-empty (so the
backward-compat baseline at seed=42 stays byte-identical).

This test pins the discovered seed so a future refactor of either the
features dimension generator or the consumer can never silently
regress to the old crash path.
"""

from __future__ import annotations

import pytest

from tests.property._helpers import generate_scenario


@pytest.mark.parametrize("seed", [103])
def test_saas_completes_at_empty_feature_pool_seed(seed: int, tmp_path) -> None:
    """At ``seed=103`` the rank-0 feature pool is empty — must not crash."""
    out = generate_scenario("saas", seed, output_dir=tmp_path)
    # Sanity: feature_usage was populated despite the empty rank-0 pool.
    assert "feature_usage" in out
    assert len(out["feature_usage"]) > 0, "feature_usage came back empty"
    # Every feature_id in feature_usage must resolve to the features dim.
    feature_ids = set(out["features"]["feature_id"])
    used_features = set(out["feature_usage"]["feature_id"])
    assert used_features <= feature_ids, "orphan feature_id in feature_usage"
