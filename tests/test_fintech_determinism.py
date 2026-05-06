"""Explicit reproducibility tests for the fintech scenario (P2-7).

Mirrors the retail-only ``tests/test_determinism.py`` pattern so the four
classic scenarios all have the same dedicated reproducibility coverage at
the top level. The Hypothesis-fuzzed variant lives in
``tests/property/test_fintech_invariants.py`` — these tests use fixed seeds
and ``pd.testing.assert_frame_equal`` so a regression here points directly
at a specific failing column without going through the shrinker.
"""

from __future__ import annotations

import pandas as pd

from synth_datagen.config import (
    DataQuality,
    DataQualityConfig,
    Dialect,
    GeneratorConfig,
    Scenario,
    SchemaType,
)
from synth_datagen.generators.fintech import FintechGenerator
from synth_datagen.schema_builder import SchemaBuilder
from synth_datagen.utils import seed_everything


def _generate_fintech(
    seed: int, row_overrides: dict[str, int], tmp_path
) -> dict[str, pd.DataFrame]:
    config = GeneratorConfig(
        scenario=Scenario.FINTECH,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=seed,
        output_dir=tmp_path,
        chunk_size=500,
        row_overrides=row_overrides,
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    _, rng, faker = seed_everything(seed)
    gen = FintechGenerator(config, rng, faker)
    raw_t, raw_r = gen.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_t, raw_r)
    fk_pools: dict = {}
    result: dict = {}
    for table in graph.topological_order():
        chunks = list(gen.generate_table(table, graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        result[table.name] = df
        pk_key = f"{table.name}.{table.pk_column}"
        if table.pk_column in df.columns:
            fk_pools[pk_key] = df[table.pk_column].to_numpy()
    return result


_SMALL_OVERRIDES = {
    "customers": 100,
    "accounts": 150,
    "merchants": 50,
    "transactions": 400,
    "cards": 120,
    "loans": 80,
    "loan_payments": 200,
}


class TestFintechDeterminism:
    def test_same_seed_produces_identical_customers(self, tmp_path):
        a = _generate_fintech(42, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_fintech(42, _SMALL_OVERRIDES, tmp_path / "b")
        num_a = a["customers"].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b["customers"].select_dtypes(include=["number"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(num_a, num_b, check_dtype=False)

    def test_same_seed_produces_identical_transactions(self, tmp_path):
        a = _generate_fintech(42, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_fintech(42, _SMALL_OVERRIDES, tmp_path / "b")
        num_a = (
            a["transactions"].select_dtypes(include=["number"]).reset_index(drop=True)
        )
        num_b = (
            b["transactions"].select_dtypes(include=["number"]).reset_index(drop=True)
        )
        pd.testing.assert_frame_equal(num_a, num_b, check_dtype=False)

    def test_same_seed_produces_identical_cards(self, tmp_path):
        """Doubles as a guard for the P2 _advance_years_safe helper —
        the expiry_date column is byte-identical across reruns iff the
        date arithmetic is fully deterministic."""
        a = _generate_fintech(42, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_fintech(42, _SMALL_OVERRIDES, tmp_path / "b")
        # expiry_date is a date column -> compare as ISO strings to dodge
        # any silent dtype drift between datetime64[ns] and object.
        a_exp = a["cards"]["expiry_date"].astype(str).to_numpy()
        b_exp = b["cards"]["expiry_date"].astype(str).to_numpy()
        assert (a_exp == b_exp).all(), "card.expiry_date drifted across reruns"

    def test_different_seeds_differ(self, tmp_path):
        a = _generate_fintech(42, _SMALL_OVERRIDES, tmp_path / "s42")
        b = _generate_fintech(99, _SMALL_OVERRIDES, tmp_path / "s99")
        bal_a = a["accounts"]["balance"].to_numpy()
        bal_b = b["accounts"]["balance"].to_numpy()
        assert not (bal_a == bal_b).all(), (
            "different seeds produced identical balances — RNG isolation broken"
        )

    def test_same_seed_same_row_count(self, tmp_path):
        a = _generate_fintech(7, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_fintech(7, _SMALL_OVERRIDES, tmp_path / "b")
        for name in a:
            assert len(a[name]) == len(b[name]), (
                f"row count mismatch for {name}: {len(a[name])} vs {len(b[name])}"
            )
