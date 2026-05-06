from __future__ import annotations

import pandas as pd

from synth_datagen.config import DataQualityConfig, Dialect, GeneratorConfig, Scenario, SchemaType
from synth_datagen.generators.retail import RetailGenerator
from synth_datagen.schema_builder import SchemaBuilder
from synth_datagen.utils import seed_everything
from tests.helpers import generate_scenario_dfs


def _margin_by_segment(dfs: dict[str, pd.DataFrame]) -> pd.Series:
    items = (
        dfs["fact_order_items"]
        .merge(dfs["fact_orders"][["order_id", "customer_id"]], on="order_id", how="left")
        .merge(dfs["dim_customers"][["customer_id", "segment"]], on="customer_id", how="left")
        .merge(dfs["dim_products"][["product_id", "cost_price"]], on="product_id", how="left")
    )
    revenue = pd.to_numeric(items["line_total"], errors="coerce")
    cost = pd.to_numeric(items["qty"], errors="coerce") * pd.to_numeric(items["cost_price"], errors="coerce")
    summary = items.assign(revenue=revenue, cost=cost).groupby("segment", as_index=True)[["revenue", "cost"]].sum()
    return (summary["revenue"] - summary["cost"]) / summary["revenue"]


def test_retail_discount_variation_creates_segment_margin_ordering(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(
        Scenario.RETAIL,
        tmp_path,
        row_overrides={
            "dim_customers": 300,
            "dim_products": 120,
            "dim_stores": 20,
            "dim_date": 365,
            "dim_promotions": 30,
            "fact_orders": 1200,
            "fact_order_items": 3200,
            "fact_payments": 1200,
            "bridge_order_promotions": 400,
        },
    )
    margins = _margin_by_segment(dfs)
    assert margins["Premium"] > margins["B2C"] > margins["Budget"]
    assert margins["B2B"] > margins["B2C"]
    assert float(margins.max() - margins.min()) > 0.08


def test_retail_discount_variation_can_be_disabled(tmp_path) -> None:
    config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        discount_seed=42,
        discount_variation=False,
        output_dir=tmp_path / "retail_no_discount_variation",
        chunk_size=500,
        row_overrides={
            "dim_customers": 120,
            "dim_products": 60,
            "dim_stores": 12,
            "dim_date": 365,
            "dim_promotions": 20,
            "fact_orders": 240,
            "fact_order_items": 600,
            "fact_payments": 240,
            "bridge_order_promotions": 80,
        },
        data_quality=DataQualityConfig(),
    )
    _, rng, faker = seed_everything(config.seed)
    generator = RetailGenerator(config, rng, faker)
    raw_tables, raw_relations = generator.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_tables, raw_relations)
    fk_pools: dict[str, object] = {}
    items = None
    for table in graph.topological_order():
        chunks = list(generator.generate_table(table, graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        if table.name == "fact_order_items":
            items = df
        if table.pk_column in df.columns:
            fk_pools[f"{table.name}.{table.pk_column}"] = df[table.pk_column].dropna().to_numpy()
    assert items is not None
    assert items["discount_pct"].max() <= 0.25
