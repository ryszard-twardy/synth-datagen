"""
Shared pytest fixtures for the synthetic data generator test suite.
Uses small row counts for fast test execution.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the unpackaged top-level module run_demo (repo-root smoke script)
# importable for tests that exercise it directly.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Imports below the sys.path setup are intentional — required so tests can
# import the unpackaged top-level ``run_demo`` script. Ruff E402 is silenced
# at the line level rather than via a global ignore so other files still get
# the import-order check.
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from synth_datagen.config import (  # noqa: E402
    DataQuality,
    DataQualityConfig,
    Dialect,
    GeneratorConfig,
    Scenario,
    SchemaType,
)
from synth_datagen.generators.retail import RetailGenerator  # noqa: E402
from synth_datagen.schema_builder import SchemaBuilder, SchemaGraph  # noqa: E402
from synth_datagen.utils import seed_everything  # noqa: E402


@pytest.fixture(scope="session")
def retail_config(tmp_path_factory) -> GeneratorConfig:
    """Minimal retail config with small row counts for fast tests."""
    tmp = tmp_path_factory.mktemp("out")
    return GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp,
        chunk_size=500,
        row_overrides={
            "dim_customers": 200,
            "dim_products": 100,
            "dim_stores": 20,
            "dim_date": 365,
            "dim_promotions": 30,
            "fact_orders": 500,
            "fact_order_items": 1_000,
            "fact_payments": 500,
            "bridge_order_promotions": 300,
        },
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_sqlite=False,
        export_parquet=False,
    )


@pytest.fixture(scope="session")
def retail_graph(retail_config) -> SchemaGraph:
    """Build the retail schema graph."""
    _, rng, faker = seed_everything(retail_config.seed)
    gen = RetailGenerator(retail_config, rng, faker)
    raw_tables, raw_relations = gen.get_raw_schema()
    builder = SchemaBuilder(retail_config)
    return builder.build(raw_tables, raw_relations)


@pytest.fixture(scope="session")
def generated_dfs(retail_config, retail_graph) -> dict[str, "pd.DataFrame"]:
    """
    Generate all retail tables and return a dict: table_name -> DataFrame.
    Cached at session scope so tests share the same generated data.
    """
    import pandas as pd
    from synth_datagen.utils import seed_everything

    _, rng, faker = seed_everything(retail_config.seed)
    gen = RetailGenerator(retail_config, rng, faker)

    ordered = retail_graph.topological_order()
    fk_pools: dict[str, "np.ndarray"] = {}
    result: dict[str, pd.DataFrame] = {}

    import numpy as np

    for table in ordered:
        chunks = list(gen.generate_table(table, retail_graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        result[table.name] = df
        if table.pk_column in df.columns:
            pk_key = f"{table.name}.{table.pk_column}"
            fk_pools[pk_key] = df[table.pk_column].dropna().to_numpy()

    return result
