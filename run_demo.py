"""Quick end-to-end smoke test script - run from project root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

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

SMALL = {
    # retail
    "dim_customers": 500,
    "dim_products": 200,
    "dim_stores": 30,
    "dim_date": 1461,
    "dim_promotions": 50,
    "fact_orders": 2_000,
    "fact_order_items": 6_000,
    "fact_payments": 2_000,
    "bridge_order_promotions": 1_200,
    # saas
    "accounts": 300,
    "users": 1_500,
    "subscriptions": 600,
    "invoices": 2_000,
    "features": 30,
    "feature_usage": 5_000,
    "events": 10_000,
    # fintech
    "customers": 500,
    "transactions": 5_000,
    "cards": 600,
    "merchants": 150,
    "loans": 200,
    "loan_payments": 800,
    # logistics
    "warehouses": 20,
    "suppliers": 80,
    "products": 300,
    "inventory": 400,
    "carriers": 15,
    "shipments": 1_000,
    "shipment_items": 3_000,
}


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

    for scenario in Scenario:
        print(f"\n{'=' * 60}")
        print(f"  Scenario: {scenario.value}")
        print(f"{'=' * 60}")
        config = GeneratorConfig(
            scenario=scenario,
            schema_type=SchemaType.STAR,
            dialect=Dialect.POSTGRES,
            seed=42,
            output_dir=Path(f"./out/{scenario.value}"),
            chunk_size=1_000,
            row_overrides=SMALL,
            data_quality=DataQualityConfig(level=DataQuality.NONE),
            export_sqlite=True,
            export_parquet=True,
        )
        run_pipeline(config)

    print("\n[OK] All scenarios generated successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
