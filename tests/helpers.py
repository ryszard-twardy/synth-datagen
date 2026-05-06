from __future__ import annotations

from pathlib import Path

import numpy as np
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
from synth_datagen.generators.logistics import LogisticsGenerator
from synth_datagen.generators.retail import RetailGenerator
from synth_datagen.generators.saas import SaasGenerator
from synth_datagen.pipeline import run_pipeline
from synth_datagen.schema_builder import SchemaBuilder
from synth_datagen.utils import seed_everything


GENERATOR_BY_SCENARIO = {
    Scenario.RETAIL: RetailGenerator,
    Scenario.SAAS: SaasGenerator,
    Scenario.FINTECH: FintechGenerator,
    Scenario.LOGISTICS: LogisticsGenerator,
}


DEFAULT_SMALL_OVERRIDES: dict[Scenario, dict[str, int]] = {
    Scenario.RETAIL: {
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
    Scenario.SAAS: {
        "accounts": 60,
        "users": 180,
        "subscriptions": 80,
        "invoices": 240,
        "features": 18,
        "feature_usage": 500,
        "events": 900,
    },
    Scenario.FINTECH: {
        "customers": 80,
        "accounts": 120,
        "merchants": 30,
        "transactions": 600,
        "cards": 100,
        "loans": 50,
        "loan_payments": 180,
    },
    Scenario.LOGISTICS: {
        "warehouses": 12,
        "suppliers": 20,
        "products": 40,
        "inventory": 120,
        "carriers": 8,
        "shipments": 120,
        "shipment_items": 360,
    },
}


def generate_scenario_dfs(
    scenario: Scenario,
    tmp_path: Path,
    *,
    seed: int = 42,
    data_quality: DataQuality = DataQuality.NONE,
    row_overrides: dict[str, int] | None = None,
) -> tuple[dict[str, pd.DataFrame], object]:
    config = GeneratorConfig(
        scenario=scenario,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=seed,
        output_dir=tmp_path / scenario.value,
        chunk_size=500,
        row_overrides=row_overrides or DEFAULT_SMALL_OVERRIDES[scenario],
        data_quality=DataQualityConfig(level=data_quality),
        export_sqlite=False,
        export_parquet=False,
    )
    _, rng, faker = seed_everything(seed)
    generator = GENERATOR_BY_SCENARIO[scenario](config, rng, faker)
    raw_tables, raw_relations = generator.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_tables, raw_relations)

    fk_pools: dict[str, np.ndarray] = {}
    dfs: dict[str, pd.DataFrame] = {}
    for table in graph.topological_order():
        chunks = list(generator.generate_table(table, graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        dfs[table.name] = df
        if table.pk_column in df.columns:
            fk_pools[f"{table.name}.{table.pk_column}"] = (
                df[table.pk_column].dropna().to_numpy()
            )
    return dfs, graph


def generate_exported_csvs(
    scenario: Scenario,
    tmp_path: Path,
    *,
    seed: int = 42,
    data_quality: DataQuality = DataQuality.NONE,
    row_overrides: dict[str, int] | None = None,
) -> tuple[dict[str, pd.DataFrame], object]:
    config = GeneratorConfig(
        scenario=scenario,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=seed,
        output_dir=tmp_path / f"{scenario.value}_{data_quality.value}",
        chunk_size=500,
        row_overrides=row_overrides or DEFAULT_SMALL_OVERRIDES[scenario],
        data_quality=DataQualityConfig(level=data_quality),
        export_sqlite=False,
        export_parquet=False,
    )
    run_pipeline(config)
    _, rng, faker = seed_everything(seed)
    generator = GENERATOR_BY_SCENARIO[scenario](config, rng, faker)
    raw_tables, raw_relations = generator.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_tables, raw_relations)
    dfs = {
        table.name: pd.read_csv(config.output_dir / f"{table.name}.csv")
        for table in graph.topological_order()
    }
    return dfs, graph
