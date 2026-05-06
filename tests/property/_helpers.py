"""Shared helpers for Hypothesis property tests across the four classic
scenarios (retail / saas / fintech / logistics).

Each scenario's generator is exercised through the same in-process call path
the existing test_determinism.py and test_*_realism.py modules use, but
parametrised by scenario name so a property test can fuzz seeds across all
four with a single helper.

Row overrides are deliberately small (60-300 rows per table) so a
``max_examples=5`` Hypothesis run completes in single-digit seconds — the
slow-test trim in P6 will tighten further if needed.

Intentionally NOT decorated with ``@pytest.fixture`` — Hypothesis
``@given``-decorated tests cannot accept function-scoped fixtures cleanly,
so callers invoke ``generate_scenario()`` directly each example.
"""

from __future__ import annotations

from typing import Any

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
from synth_datagen.schema_builder import SchemaBuilder
from synth_datagen.utils import seed_everything

# Per-scenario small overrides. Tuned so the generator finishes inside ~1s
# at default DQ level for any seed sampled by Hypothesis. Numbers chosen to
# preserve foreign-key plausibility (e.g. fintech needs accounts >= customers
# to keep account/customer cardinality realistic).
_OVERRIDES: dict[str, dict[str, int]] = {
    "retail": {
        "dim_customers": 100,
        "dim_products": 50,
        "dim_stores": 10,
        "dim_date": 365,
        "dim_promotions": 20,
        "fact_orders": 200,
        "fact_order_items": 400,
        "fact_payments": 200,
        "bridge_order_promotions": 100,
    },
    "saas": {
        "accounts": 100,
        "users": 300,
        "subscriptions": 120,
        "invoices": 300,
        "features": 20,
        "feature_usage": 400,
        "events": 600,
    },
    "fintech": {
        "customers": 100,
        "accounts": 150,
        "merchants": 50,
        "transactions": 400,
        "cards": 120,
        "loans": 80,
        "loan_payments": 200,
    },
    "logistics": {
        "warehouses": 10,
        "suppliers": 30,
        "products": 80,
        "inventory": 150,
        "shipments": 120,
        "shipment_items": 300,
        "routes": 40,
    },
}

_GENERATORS: dict[str, tuple[Any, Scenario]] = {
    "retail": (RetailGenerator, Scenario.RETAIL),
    "saas": (SaasGenerator, Scenario.SAAS),
    "fintech": (FintechGenerator, Scenario.FINTECH),
    "logistics": (LogisticsGenerator, Scenario.LOGISTICS),
}


def generate_scenario(
    scenario: str, seed: int, *, output_dir: Any
) -> dict[str, pd.DataFrame]:
    """Generate the named scenario at small scale with the given seed.

    Returns a dict mapping table name to DataFrame, populated in
    topological order (so foreign-key columns reference rows that exist).
    """
    if scenario not in _GENERATORS:
        raise ValueError(f"unknown scenario: {scenario!r}")
    generator_cls, scenario_enum = _GENERATORS[scenario]
    config = GeneratorConfig(
        scenario=scenario_enum,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=seed,
        output_dir=output_dir,
        chunk_size=500,
        row_overrides=_OVERRIDES[scenario],
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_sqlite=False,
        export_parquet=False,
    )
    _, rng, faker = seed_everything(seed)
    gen = generator_cls(config, rng, faker)
    raw_t, raw_r = gen.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_t, raw_r)

    fk_pools: dict[str, Any] = {}
    result: dict[str, pd.DataFrame] = {}
    for table in graph.topological_order():
        chunks = list(gen.generate_table(table, graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        result[table.name] = df
        pk_key = f"{table.name}.{table.pk_column}"
        if table.pk_column in df.columns:
            fk_pools[pk_key] = df[table.pk_column].to_numpy()
    return result
