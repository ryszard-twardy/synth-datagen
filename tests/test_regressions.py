"""
Regression and smoke tests for recently fixed stability issues.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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
from synth_datagen.utils import apply_data_quality, seed_everything


def _generate_scenario_dfs(
    config: GeneratorConfig,
    generator_cls,
) -> tuple[dict[str, pd.DataFrame], object]:
    _, rng, faker = seed_everything(config.seed)
    gen = generator_cls(config, rng, faker)
    raw_tables, raw_relations = gen.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_tables, raw_relations)

    fk_pools: dict[str, np.ndarray] = {}
    dfs: dict[str, pd.DataFrame] = {}
    for table in graph.topological_order():
        chunks = list(gen.generate_table(table, graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        dfs[table.name] = df
        if table.pk_column in df.columns:
            fk_pools[f"{table.name}.{table.pk_column}"] = (
                df[table.pk_column].dropna().to_numpy()
            )
    return dfs, graph


def test_retail_dq_light_sqlite_export_succeeds(tmp_path) -> None:
    """Regression: DQ + SQLite export should not violate UNIQUE constraints."""
    config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path / "dq_sqlite",
        chunk_size=500,
        row_overrides={
            "dim_customers": 120,
            "dim_products": 80,
            "dim_stores": 20,
            "dim_date": 120,
            "dim_promotions": 20,
            "fact_orders": 180,
            "fact_order_items": 300,
            "fact_payments": 180,
            "bridge_order_promotions": 120,
        },
        data_quality=DataQualityConfig(level=DataQuality.LIGHT),
        export_sqlite=True,
    )

    run_pipeline(config)

    db_path = config.output_dir / "retail.db"
    assert db_path.exists(), "Expected SQLite database was not created"
    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute('SELECT COUNT(*) FROM "dim_customers"').fetchone()[0]
        assert count > 0
    finally:
        conn.close()


def test_outlier_injection_keeps_protected_numeric_columns() -> None:
    """Regression: outlier injection must not mutate protected PK/FK columns."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "account_id": [10, 11, 12, 13, 14],
            "amount": [10.0, 20.0, 30.0, 40.0, 50.0],
        }
    )
    rng = np.random.default_rng(42)
    dq = DataQualityConfig(level=DataQuality.NONE, outlier_rate=1.0)

    out = apply_data_quality(
        df.copy(),
        dq_config=dq,
        protected_cols=["id", "account_id"],
        rng=rng,
        pk_column="id",
    )

    assert out["id"].tolist() == df["id"].tolist()
    assert out["account_id"].tolist() == df["account_id"].tolist()
    assert not np.array_equal(out["amount"].to_numpy(), df["amount"].to_numpy())


@pytest.mark.parametrize(
    ("scenario", "generator_cls", "row_overrides"),
    [
        (
            Scenario.SAAS,
            SaasGenerator,
            {
                "accounts": 10,
                "users": 20,
                "subscriptions": 10,
                "invoices": 20,
                "features": 8,
                "feature_usage": 30,
                "events": 40,
            },
        ),
        (
            Scenario.FINTECH,
            FintechGenerator,
            {
                "customers": 10,
                "accounts": 12,
                "merchants": 6,
                "transactions": 24,
                "cards": 10,
                "loans": 8,
                "loan_payments": 16,
            },
        ),
        (
            Scenario.LOGISTICS,
            LogisticsGenerator,
            {
                "warehouses": 8,
                "suppliers": 10,
                "products": 20,
                "inventory": 30,
                "carriers": 5,
                "shipments": 20,
                "shipment_items": 40,
            },
        ),
    ],
)
def test_non_retail_scenario_smoke_fk_integrity(
    tmp_path: Path,
    scenario: Scenario,
    generator_cls,
    row_overrides: dict[str, int],
) -> None:
    """Smoke: small datasets generate and satisfy FK referential integrity."""
    config = GeneratorConfig(
        scenario=scenario,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path / scenario.value,
        chunk_size=500,
        row_overrides=row_overrides,
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_sqlite=False,
        export_parquet=False,
    )
    dfs, graph = _generate_scenario_dfs(config, generator_cls)

    for rel in graph.relations:
        src_vals = dfs[rel.source_table][rel.source_column].dropna()
        tgt_vals = set(dfs[rel.target_table][rel.target_column].dropna().tolist())
        assert src_vals.isin(tgt_vals).all(), (
            f"FK violation: {rel.source_table}.{rel.source_column} -> "
            f"{rel.target_table}.{rel.target_column}"
        )


def test_cli_generate_is_safe_under_cp1252(tmp_path: Path) -> None:
    """Regression: CLI should run without UnicodeEncodeError under cp1252."""
    out_dir = tmp_path / "cli_cp1252"
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-m",
        "synth_datagen.main",
        "generate",
        "--scenario",
        "retail",
        "--rows",
        (
            "dim_customers=10,dim_products=10,dim_stores=5,dim_date=10,"
            "dim_promotions=5,fact_orders=10,fact_order_items=20,"
            "fact_payments=10,bridge_order_promotions=10"
        ),
        "--output",
        str(out_dir),
        "--chunk-size",
        "500",
    ]
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env["PYTHONIOENCODING"] = "cp1252"

    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="cp1252",
    )

    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    assert "UnicodeEncodeError" not in proc.stdout
    assert "UnicodeEncodeError" not in proc.stderr


def test_retail_payments_align_with_orders(tmp_path: Path) -> None:
    config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path / "retail_realism",
        chunk_size=500,
        row_overrides={
            "dim_customers": 80,
            "dim_products": 80,
            "dim_stores": 20,
            "dim_date": 365,
            "dim_promotions": 20,
            "fact_orders": 300,
            "fact_order_items": 500,
            "fact_payments": 300,
            "bridge_order_promotions": 120,
        },
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    dfs, _ = _generate_scenario_dfs(config, RetailGenerator)
    orders = dfs["fact_orders"][["order_id", "created_at", "order_total", "currency"]]
    payments = dfs["fact_payments"]
    merged = payments.merge(
        orders, on="order_id", how="left", suffixes=("_pay", "_order")
    )
    paid_mask = merged["paid_at"].notna()
    if paid_mask.any():
        assert (
            pd.to_datetime(merged.loc[paid_mask, "paid_at"])
            >= pd.to_datetime(merged.loc[paid_mask, "created_at"])
        ).all()
    completed_mask = merged["status"].isin(["completed", "refunded", "pending"])
    assert np.allclose(
        merged.loc[completed_mask, "amount"].to_numpy(dtype=float),
        merged.loc[completed_mask, "order_total"].to_numpy(dtype=float),
        atol=0.01,
    )
    assert (merged["currency_pay"] == merged["currency_order"]).all()


def test_saas_invoice_account_matches_subscription(tmp_path: Path) -> None:
    config = GeneratorConfig(
        scenario=Scenario.SAAS,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path / "saas_realism",
        chunk_size=500,
        row_overrides={
            "accounts": 120,
            "users": 300,
            "subscriptions": 160,
            "invoices": 600,
            "features": 20,
            "feature_usage": 800,
            "events": 1200,
        },
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    dfs, _ = _generate_scenario_dfs(config, SaasGenerator)
    merged = dfs["invoices"].merge(
        dfs["subscriptions"][["sub_id", "account_id"]].rename(
            columns={"account_id": "sub_account_id"}
        ),
        on="sub_id",
        how="left",
    )
    assert (merged["account_id"] == merged["sub_account_id"]).all()


def test_fintech_loan_payments_within_monthly_payment(tmp_path: Path) -> None:
    config = GeneratorConfig(
        scenario=Scenario.FINTECH,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path / "fintech_realism",
        chunk_size=500,
        row_overrides={
            "customers": 120,
            "accounts": 180,
            "merchants": 60,
            "transactions": 1200,
            "cards": 120,
            "loans": 100,
            "loan_payments": 600,
        },
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    dfs, _ = _generate_scenario_dfs(config, FintechGenerator)
    merged = dfs["loan_payments"].merge(
        dfs["loans"][["loan_id", "monthly_payment", "disbursed_at", "due_date"]],
        on="loan_id",
        how="left",
    )
    assert (merged["amount"] <= merged["monthly_payment"] + 1e-9).all()
    due_dt = pd.to_datetime(merged["due_date"])
    paid_dt = pd.to_datetime(merged["paid_at"])
    disbursed_dt = pd.to_datetime(merged["disbursed_at"])
    assert ((paid_dt >= disbursed_dt) & (paid_dt <= due_dt)).all()


def test_logistics_shipment_transport_matches_carrier(tmp_path: Path) -> None:
    config = GeneratorConfig(
        scenario=Scenario.LOGISTICS,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path / "logistics_realism",
        chunk_size=500,
        row_overrides={
            "warehouses": 40,
            "suppliers": 80,
            "products": 200,
            "inventory": 400,
            "carriers": 30,
            "shipments": 600,
            "shipment_items": 1200,
        },
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    dfs, _ = _generate_scenario_dfs(config, LogisticsGenerator)
    merged = dfs["shipments"].merge(
        dfs["carriers"][["carrier_id", "transport"]], on="carrier_id", how="left"
    )
    match_rate = (merged["transport_mode"] == merged["transport"]).mean()
    assert match_rate >= 0.90


def test_retail_dim_date_respects_row_override(tmp_path: Path) -> None:
    """Regression: dim_date generator should honor row_overrides."""
    config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path / "retail_dim_date_override",
        chunk_size=500,
        row_overrides={"dim_date": 10},
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )
    _, rng, faker = seed_everything(config.seed)
    gen = RetailGenerator(config, rng, faker)
    raw_tables, raw_relations = gen.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_tables, raw_relations)
    table = graph.get_table("dim_date")
    chunks = list(gen.generate_table(table, graph, fk_pools={}))
    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    assert len(df) == 10


def test_distribute_counts_requires_rng() -> None:
    """Audit P2-4: distribute_counts used to silently fall back to
    np.random.default_rng(42) when called with rng=None — a reproducibility
    foot-gun. Now it raises so callers cannot accidentally bypass the seed.
    """
    from synth_datagen.utils import distribute_counts

    with pytest.raises(TypeError, match="rng is required"):
        distribute_counts(total=10, bins=3, rng=None)


def test_schema_type_only_exposes_star() -> None:
    """SchemaType must only expose 'star'. Audit P2-9: 3nf and mixed are dead values
    rejected at runtime by the GeneratorConfig validator — a foot-gun, since users
    discover non-support only at construction time. Removing them makes the type
    system the single source of truth.
    """
    assert set(SchemaType.__members__) == {"STAR"}
    assert [m.value for m in SchemaType] == ["star"]
