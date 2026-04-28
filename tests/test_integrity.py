"""
Tests for data integrity: PK uniqueness, FK referential integrity,
non-negative amounts, and date ordering.
"""

from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# PK uniqueness
# ---------------------------------------------------------------------------


class TestPrimaryKeys:
    """Every table's PK column must contain only unique, non-null values."""

    def test_pk_uniqueness_dim_customers(self, generated_dfs, retail_graph):
        self._assert_pk_unique("dim_customers", generated_dfs, retail_graph)

    def test_pk_uniqueness_dim_products(self, generated_dfs, retail_graph):
        self._assert_pk_unique("dim_products", generated_dfs, retail_graph)

    def test_pk_uniqueness_dim_stores(self, generated_dfs, retail_graph):
        self._assert_pk_unique("dim_stores", generated_dfs, retail_graph)

    def test_pk_uniqueness_dim_date(self, generated_dfs, retail_graph):
        self._assert_pk_unique("dim_date", generated_dfs, retail_graph)

    def test_pk_uniqueness_dim_promotions(self, generated_dfs, retail_graph):
        self._assert_pk_unique("dim_promotions", generated_dfs, retail_graph)

    def test_pk_uniqueness_fact_orders(self, generated_dfs, retail_graph):
        self._assert_pk_unique("fact_orders", generated_dfs, retail_graph)

    def test_pk_uniqueness_fact_order_items(self, generated_dfs, retail_graph):
        self._assert_pk_unique("fact_order_items", generated_dfs, retail_graph)

    def test_pk_uniqueness_fact_payments(self, generated_dfs, retail_graph):
        self._assert_pk_unique("fact_payments", generated_dfs, retail_graph)

    @staticmethod
    def _assert_pk_unique(table_name: str, dfs: dict, graph) -> None:
        table = graph.get_table(table_name)
        df    = dfs[table_name]
        pk    = table.pk_column
        assert pk in df.columns, f"PK column '{pk}' missing from {table_name}"
        assert df[pk].notna().all(),       f"{table_name}.{pk} has NULL values"
        assert df[pk].is_unique,           f"{table_name}.{pk} has duplicate values"


# ---------------------------------------------------------------------------
# FK referential integrity
# ---------------------------------------------------------------------------


class TestForeignKeys:
    """Every FK value must reference an existing PK in the parent table."""

    def test_fk_orders_customer(self, generated_dfs):
        self._assert_fk("fact_orders", "customer_id", "dim_customers", "customer_id", generated_dfs)

    def test_fk_orders_store(self, generated_dfs):
        self._assert_fk("fact_orders", "store_id", "dim_stores", "store_id", generated_dfs)

    def test_fk_order_items_order(self, generated_dfs):
        self._assert_fk("fact_order_items", "order_id", "fact_orders", "order_id", generated_dfs)

    def test_fk_order_items_product(self, generated_dfs):
        self._assert_fk("fact_order_items", "product_id", "dim_products", "product_id", generated_dfs)

    def test_fk_payments_order(self, generated_dfs):
        self._assert_fk("fact_payments", "order_id", "fact_orders", "order_id", generated_dfs)

    def test_fk_bridge_order(self, generated_dfs):
        self._assert_fk("bridge_order_promotions", "order_id", "fact_orders", "order_id", generated_dfs)

    def test_fk_bridge_promo(self, generated_dfs):
        self._assert_fk("bridge_order_promotions", "promo_id", "dim_promotions", "promo_id", generated_dfs)

    @staticmethod
    def _assert_fk(
        src_table: str, src_col: str,
        tgt_table: str, tgt_col: str,
        dfs: dict,
    ) -> None:
        src_df = dfs[src_table]
        tgt_df = dfs[tgt_table]

        assert src_col in src_df.columns, f"{src_table}.{src_col} missing"
        assert tgt_col in tgt_df.columns, f"{tgt_table}.{tgt_col} missing"

        valid_pks = set(tgt_df[tgt_col].dropna().tolist())
        fk_vals   = src_df[src_col].dropna()
        orphans   = fk_vals[~fk_vals.isin(valid_pks)]
        assert len(orphans) == 0, (
            f"Referential integrity violation: {src_table}.{src_col} → {tgt_table}.{tgt_col}: "
            f"{len(orphans)} orphaned value(s): {orphans.head(5).tolist()}"
        )


# ---------------------------------------------------------------------------
# Non-negative amounts
# ---------------------------------------------------------------------------


class TestAmountSanity:
    """Monetary and quantity columns must be non-negative."""

    def test_fact_order_items_positive_amounts(self, generated_dfs):
        df = generated_dfs["fact_order_items"]
        for col in ["qty", "unit_price", "line_total"]:
            neg = df[col] < 0
            assert not neg.any(), f"fact_order_items.{col} has {neg.sum()} negative values"

    def test_fact_orders_positive_totals(self, generated_dfs):
        df = generated_dfs["fact_orders"]
        for col in ["subtotal", "discount_amt", "shipping_amt", "order_total"]:
            neg = df[col] < 0
            assert not neg.any(), f"fact_orders.{col} has {neg.sum()} negative values"

    def test_dim_products_cost_less_than_price(self, generated_dfs):
        df = generated_dfs["dim_products"]
        bad = df["cost_price"] > df["list_price"]
        assert not bad.any(), f"dim_products: {bad.sum()} rows with cost > list_price"

    def test_fact_payments_positive_amount(self, generated_dfs):
        df = generated_dfs["fact_payments"]
        neg = df["amount"] < 0
        assert not neg.any(), f"fact_payments.amount has {neg.sum()} negative values"


# ---------------------------------------------------------------------------
# Date ordering
# ---------------------------------------------------------------------------


class TestDateOrdering:
    """Business date constraints: paid_at ≥ created_at, delivery ≥ shipped."""

    def test_promotions_valid_to_gte_valid_from(self, generated_dfs):
        df = generated_dfs["dim_promotions"]
        bad = pd.to_datetime(df["valid_to"]) < pd.to_datetime(df["valid_from"])
        assert not bad.any(), f"dim_promotions: {bad.sum()} rows with valid_to < valid_from"

    def test_orders_delivered_gte_shipped(self, generated_dfs):
        df = generated_dfs["fact_orders"].copy()
        mask = df["shipped_at"].notna() & df["delivered_at"].notna()
        if mask.sum() == 0:
            pytest.skip("No rows with both shipped_at and delivered_at")
        bad = pd.to_datetime(df.loc[mask, "delivered_at"]) < pd.to_datetime(df.loc[mask, "shipped_at"])
        assert not bad.any(), f"fact_orders: {bad.sum()} rows with delivered_at < shipped_at"
