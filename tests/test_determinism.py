"""
Tests for seed determinism: same seed → same data, different seed → different data.
"""

from __future__ import annotations

import pandas as pd

from src.config import DataQuality, DataQualityConfig, Dialect, GeneratorConfig, Scenario, SchemaType
from src.generators.retail import RetailGenerator
from src.schema_builder import SchemaBuilder
from src.utils import seed_everything


def _generate_retail(seed: int, row_overrides: dict, tmp_path) -> dict[str, pd.DataFrame]:
    """Helper: generate retail tables with given seed, return dict of DataFrames."""
    config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=seed,
        output_dir=tmp_path,
        chunk_size=500,
        row_overrides=row_overrides,
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    _, rng, faker = seed_everything(seed)
    gen     = RetailGenerator(config, rng, faker)
    raw_t, raw_r = gen.get_raw_schema()
    graph   = SchemaBuilder(config).build(raw_t, raw_r)

    fk_pools: dict = {}
    result:   dict = {}
    for table in graph.topological_order():
        chunks = list(gen.generate_table(table, graph, fk_pools))
        df     = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        result[table.name] = df
        pk_key = f"{table.name}.{table.pk_column}"
        if table.pk_column in df.columns:
            fk_pools[pk_key] = df[table.pk_column].to_numpy()
    return result


_SMALL_OVERRIDES = {
    "dim_customers": 100, "dim_products": 50, "dim_stores": 10,
    "dim_date": 365, "dim_promotions": 20, "fact_orders": 200,
    "fact_order_items": 400, "fact_payments": 200,
    "bridge_order_promotions": 100,
}


class TestDeterminism:

    def test_same_seed_produces_identical_customers(self, tmp_path):
        dfs_a = _generate_retail(42, _SMALL_OVERRIDES, tmp_path / "a")
        dfs_b = _generate_retail(42, _SMALL_OVERRIDES, tmp_path / "b")
        df_a  = dfs_a["dim_customers"].select_dtypes(exclude=["object"])
        df_b  = dfs_b["dim_customers"].select_dtypes(exclude=["object"])
        pd.testing.assert_frame_equal(df_a, df_b, check_dtype=False)

    def test_same_seed_produces_identical_orders(self, tmp_path):
        dfs_a = _generate_retail(42, _SMALL_OVERRIDES, tmp_path / "a")
        dfs_b = _generate_retail(42, _SMALL_OVERRIDES, tmp_path / "b")
        # Compare numeric columns only (datetimes may have type drift)
        num_a = dfs_a["fact_orders"].select_dtypes(include=["number"])
        num_b = dfs_b["fact_orders"].select_dtypes(include=["number"])
        pd.testing.assert_frame_equal(num_a, num_b, check_dtype=False)

    def test_different_seeds_differ(self, tmp_path):
        dfs_42 = _generate_retail(42, _SMALL_OVERRIDES, tmp_path / "s42")
        dfs_99 = _generate_retail(99, _SMALL_OVERRIDES, tmp_path / "s99")
        # Numeric subtotals must differ between seeds
        vals_42 = dfs_42["fact_orders"]["subtotal"].values
        vals_99 = dfs_99["fact_orders"]["subtotal"].values
        assert not (vals_42 == vals_99).all(), (
            "Different seeds produced identical data — seeding is broken"
        )

    def test_same_seed_same_row_count(self, tmp_path):
        dfs_a = _generate_retail(7, _SMALL_OVERRIDES, tmp_path / "a")
        dfs_b = _generate_retail(7, _SMALL_OVERRIDES, tmp_path / "b")
        for name in dfs_a:
            assert len(dfs_a[name]) == len(dfs_b[name]), (
                f"Row count mismatch for {name}: {len(dfs_a[name])} vs {len(dfs_b[name])}"
            )
