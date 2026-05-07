"""SaaS quickstart with medium data-quality injection.

Generates a SaaS dataset (accounts, users, subscriptions, invoices, events)
with intentional data-quality issues so you can practice ETL/cleaning.

Run from repo root:

    python examples/quickstart_saas.py

Equivalent CLI form:

    synth-datagen saas --seed 42 --output ./out/saas --data-quality medium \\
        --rows accounts=200,users=800,events=3000
"""

from pathlib import Path

from synth_datagen.config import (
    DataQuality,
    DataQualityConfig,
    Dialect,
    GeneratorConfig,
    Scenario,
    SchemaType,
)
from synth_datagen.pipeline import run_pipeline

config = GeneratorConfig(
    scenario=Scenario.SAAS,
    schema_type=SchemaType.STAR,
    dialect=Dialect.POSTGRES,
    seed=42,
    output_dir=Path("./out/saas"),
    row_overrides={
        "accounts": 200,
        "users": 800,
        "subscriptions": 400,
        "invoices": 1_000,
        "feature_usage": 2_000,
        "events": 3_000,
    },
    data_quality=DataQualityConfig(level=DataQuality.MEDIUM),
)
run_pipeline(config)
print(f"[OK] SaaS dataset (DQ=medium) written to {config.output_dir.resolve()}")
