"""Explicit reproducibility tests for the logistics scenario (P2-7)."""

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
from synth_datagen.generators.logistics import LogisticsGenerator
from synth_datagen.schema_builder import SchemaBuilder
from synth_datagen.utils import seed_everything


def _generate_logistics(
    seed: int, row_overrides: dict[str, int], tmp_path
) -> dict[str, pd.DataFrame]:
    config = GeneratorConfig(
        scenario=Scenario.LOGISTICS,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=seed,
        output_dir=tmp_path,
        chunk_size=500,
        row_overrides=row_overrides,
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    _, rng, faker = seed_everything(seed)
    gen = LogisticsGenerator(config, rng, faker)
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
    "warehouses": 10,
    "suppliers": 30,
    "products": 80,
    "inventory": 150,
    "shipments": 120,
    "shipment_items": 300,
    "routes": 40,
}


class TestLogisticsDeterminism:
    def test_same_seed_produces_identical_warehouses(self, tmp_path):
        a = _generate_logistics(42, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_logistics(42, _SMALL_OVERRIDES, tmp_path / "b")
        num_a = a["warehouses"].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b["warehouses"].select_dtypes(include=["number"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(num_a, num_b, check_dtype=False)

    def test_same_seed_produces_identical_shipments(self, tmp_path):
        a = _generate_logistics(42, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_logistics(42, _SMALL_OVERRIDES, tmp_path / "b")
        num_a = a["shipments"].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b["shipments"].select_dtypes(include=["number"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(num_a, num_b, check_dtype=False)

    def test_same_seed_produces_identical_inventory(self, tmp_path):
        a = _generate_logistics(42, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_logistics(42, _SMALL_OVERRIDES, tmp_path / "b")
        num_a = a["inventory"].select_dtypes(include=["number"]).reset_index(drop=True)
        num_b = b["inventory"].select_dtypes(include=["number"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(num_a, num_b, check_dtype=False)

    def test_different_seeds_differ(self, tmp_path):
        a = _generate_logistics(42, _SMALL_OVERRIDES, tmp_path / "s42")
        b = _generate_logistics(99, _SMALL_OVERRIDES, tmp_path / "s99")
        cost_a = a["shipments"]["freight_cost"].to_numpy()
        cost_b = b["shipments"]["freight_cost"].to_numpy()
        assert not (cost_a == cost_b).all(), (
            "different seeds produced identical freight costs — RNG isolation broken"
        )

    def test_same_seed_same_row_count(self, tmp_path):
        a = _generate_logistics(7, _SMALL_OVERRIDES, tmp_path / "a")
        b = _generate_logistics(7, _SMALL_OVERRIDES, tmp_path / "b")
        for name in a:
            assert len(a[name]) == len(b[name]), (
                f"row count mismatch for {name}: {len(a[name])} vs {len(b[name])}"
            )
