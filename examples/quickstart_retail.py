"""Retail quickstart — small e-commerce dataset, clean data, all exporters.

Run from repo root:

    python examples/quickstart_retail.py

Equivalent CLI form:

    synth-datagen retail --seed 42 --output ./out/retail \\
        --rows fact_orders=500,fact_order_items=1500,fact_payments=500 \\
        --export-parquet
"""

import sys
from pathlib import Path

from synth_datagen.config import (
    DataQuality,
    DataQualityConfig,
    Dialect,
    GeneratorConfig,
    Scenario,
    SchemaType,
)
from synth_datagen.runtime_support import (
    is_missing_runtime_dependency,
    missing_dependency_message,
)


def _load_pipeline():
    from synth_datagen.pipeline import run_pipeline

    return run_pipeline


def main() -> int:
    try:
        run_pipeline = _load_pipeline()
    except ModuleNotFoundError as exc:
        if is_missing_runtime_dependency(exc):
            print(missing_dependency_message(exc.name), file=sys.stderr)
            return 1
        raise

    config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=Path("./out/retail"),
        row_overrides={
            "fact_orders": 500,
            "fact_order_items": 1_500,
            "fact_payments": 500,  # must equal fact_orders (1:1)
        },
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_parquet=True,
    )
    run_pipeline(config)
    print(f"[OK] Retail dataset written to {config.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
