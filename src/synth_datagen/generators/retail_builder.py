"""
Shared retail schema and data-building logic.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import re

import numpy as np
import pandas as pd
from faker import Faker

from ..config import ColumnConfig, DType, GeneratorConfig, RelationConfig, TableConfig
from ..discounts import build_discount_rng, sample_discount, sample_discount_propensity
from ..id_utils import date_to_key, make_id_list
from ..schema_builder import SchemaGraph
from ..utils import (
    COUNTRY_NAMES,
    COUNTRY_WEIGHTS,
    bounded_lognormal,
    date_range_samples,
    distribute_counts,
    weighted_choice,
)

_CATEGORIES = {
    "Electronics": ["Smartphones", "Laptops", "Tablets", "Headphones", "Cameras"],
    "Clothing": ["Menswear", "Womenswear", "Kids", "Accessories", "Shoes"],
    "Home": ["Furniture", "Kitchenware", "Bedding", "Decor", "Storage"],
    "Sports": ["Fitness", "Outdoor", "Team Sports", "Cycling", "Water Sports"],
    "Books": ["Fiction", "Non-Fiction", "Science", "Technology", "Children"],
    "Beauty": ["Skincare", "Makeup", "Haircare", "Fragrances", "Tools"],
    "Food": ["Snacks", "Beverages", "Organic", "International", "Supplements"],
}
_CATEGORY_W = [0.20, 0.18, 0.15, 0.13, 0.10, 0.12, 0.12]

_SEGMENTS = ["B2C", "B2B", "Premium", "Budget"]
_SEGMENT_W = [0.56, 0.12, 0.20, 0.12]

_CHANNELS = ["web", "mobile_app", "marketplace", "store", "phone"]
_CHANNEL_W = [0.40, 0.28, 0.18, 0.10, 0.04]

_ORDER_STATUSES = ["pending", "confirmed", "shipped", "delivered", "cancelled", "refunded"]
_ORDER_STATUS_W = [0.04, 0.06, 0.10, 0.70, 0.06, 0.04]

_STORE_TYPES = ["flagship", "outlet", "express", "online_hub"]
_STORE_TYPE_W = [0.24, 0.18, 0.22, 0.36]

_PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "bank_transfer", "buy_now_pay_later"]
_PAYMENT_W = [0.42, 0.23, 0.18, 0.10, 0.07]

_PROMO_TYPES = ["percentage", "fixed_amount", "free_shipping", "bogo"]
_PROMO_W = [0.52, 0.22, 0.16, 0.10]

_DEFAULT_SIM_START = datetime(2022, 1, 1)
_DEFAULT_SIM_END = datetime(2025, 12, 31, 23, 59, 59)
_ENABLED_MARGIN_MIN = 0.55
_ENABLED_MARGIN_RANGE = 0.18
_SEGMENT_ORDER_WEIGHT_SHAPES = {"B2C": 1.6, "B2B": 7.0, "Premium": 8.0, "Budget": 0.4}
_SEGMENT_ORDER_WEIGHT_MULTIPLIERS = {"B2C": 1.0, "B2B": 1.6, "Premium": 2.0, "Budget": 0.35}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", ".", value.lower()).strip(".")
    return cleaned or "customer"


def _discount_tier_for_segment(segment: str) -> str:
    normalized = str(segment).strip()
    if normalized in {"Premium", "B2B"}:
        return "high"
    if normalized == "Budget":
        return "low"
    return "mid"


def resolve_retail_bounds(
    config: GeneratorConfig,
    *,
    date_start: date | None = None,
    date_end: date | None = None,
) -> tuple[datetime, datetime]:
    start_date = date_start or config.simulation_start or _DEFAULT_SIM_START.date()
    end_date = date_end or config.simulation_end or _DEFAULT_SIM_END.date()
    return (
        datetime.combine(start_date, time.min),
        datetime.combine(end_date, time.max).replace(microsecond=0),
    )


def default_retail_dim_date_count(config: GeneratorConfig) -> int:
    start_dt, end_dt = resolve_retail_bounds(config)
    return (end_dt.date() - start_dt.date()).days + 1


def build_retail_schema(config: GeneratorConfig) -> tuple[list[TableConfig], list[RelationConfig]]:
    ov = config.row_overrides
    dim_date_count = ov.get("dim_date", default_retail_dim_date_count(config))
    tables = [
        TableConfig(
            name="dim_customers",
            row_count=ov.get("dim_customers", 20_000),
            pk_column="customer_id",
            columns=[
                ColumnConfig(name="customer_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="first_name", dtype=DType.VARCHAR, nullable=False, max_length=80),
                ColumnConfig(name="last_name", dtype=DType.VARCHAR, nullable=False, max_length=80),
                ColumnConfig(name="email", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="phone", dtype=DType.VARCHAR, nullable=True, max_length=40),
                ColumnConfig(name="city", dtype=DType.VARCHAR, nullable=False, max_length=80),
                ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="segment", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="created_at", dtype=DType.TIMESTAMP, nullable=False),
                ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                ColumnConfig(name="lifetime_value", dtype=DType.DECIMAL, nullable=True),
            ],
        ),
        TableConfig(
            name="dim_products",
            row_count=ov.get("dim_products", 5_000),
            pk_column="product_id",
            columns=[
                ColumnConfig(name="product_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="sku", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="name", dtype=DType.VARCHAR, nullable=False, max_length=160),
                ColumnConfig(name="category", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="subcategory", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="brand", dtype=DType.VARCHAR, nullable=True, max_length=120),
                ColumnConfig(name="cost_price", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="list_price", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="currency", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="weight_kg", dtype=DType.FLOAT, nullable=True),
                ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
            ],
        ),
        TableConfig(
            name="dim_stores",
            row_count=ov.get("dim_stores", 200),
            pk_column="store_id",
            columns=[
                ColumnConfig(name="store_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="store_name", dtype=DType.VARCHAR, nullable=False, max_length=160),
                ColumnConfig(name="store_type", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="city", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="region", dtype=DType.VARCHAR, nullable=False, max_length=80),
                ColumnConfig(name="opened_date", dtype=DType.DATE, nullable=False),
                ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
            ],
        ),
        TableConfig(
            name="dim_date",
            row_count=dim_date_count,
            pk_column="date_id",
            allow_duplicate_injection=False,
            columns=[
                ColumnConfig(name="date_id", dtype=DType.INT, nullable=False, unique=True),
                ColumnConfig(name="full_date", dtype=DType.DATE, nullable=False),
                ColumnConfig(name="year", dtype=DType.INT, nullable=False),
                ColumnConfig(name="quarter", dtype=DType.INT, nullable=False),
                ColumnConfig(name="month", dtype=DType.INT, nullable=False),
                ColumnConfig(name="month_name", dtype=DType.VARCHAR, nullable=False, max_length=20),
                ColumnConfig(name="week", dtype=DType.INT, nullable=False),
                ColumnConfig(name="day_of_week", dtype=DType.INT, nullable=False),
                ColumnConfig(name="day_name", dtype=DType.VARCHAR, nullable=False, max_length=20),
                ColumnConfig(name="is_weekend", dtype=DType.BOOLEAN, nullable=False),
                ColumnConfig(name="is_holiday", dtype=DType.BOOLEAN, nullable=False),
            ],
        ),
        TableConfig(
            name="dim_promotions",
            row_count=ov.get("dim_promotions", 150),
            pk_column="promo_id",
            columns=[
                ColumnConfig(name="promo_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="promo_name", dtype=DType.VARCHAR, nullable=False, max_length=120),
                ColumnConfig(name="discount_type", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="discount_value", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="valid_from", dtype=DType.DATE, nullable=False),
                ColumnConfig(name="valid_to", dtype=DType.DATE, nullable=False),
                ColumnConfig(name="min_order_value", dtype=DType.DECIMAL, nullable=True),
                ColumnConfig(name="is_stackable", dtype=DType.BOOLEAN, nullable=False),
            ],
        ),
        TableConfig(
            name="fact_orders",
            row_count=ov.get("fact_orders", 80_000),
            pk_column="order_id",
            columns=[
                ColumnConfig(name="order_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="customer_id", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="store_id", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="date_id", dtype=DType.INT, nullable=False),
                ColumnConfig(name="channel", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="currency", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="subtotal", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="discount_amt", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="shipping_amt", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="order_total", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="created_at", dtype=DType.TIMESTAMP, nullable=False),
                ColumnConfig(name="shipped_at", dtype=DType.TIMESTAMP, nullable=True),
                ColumnConfig(name="delivered_at", dtype=DType.TIMESTAMP, nullable=True),
            ],
        ),
        TableConfig(
            name="fact_order_items",
            row_count=ov.get("fact_order_items", 200_000),
            pk_column="item_id",
            columns=[
                ColumnConfig(name="item_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="order_id", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="product_id", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="qty", dtype=DType.INT, nullable=False),
                ColumnConfig(name="unit_price", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="discount_pct", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="line_total", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="return_flag", dtype=DType.BOOLEAN, nullable=False),
            ],
        ),
        TableConfig(
            name="fact_payments",
            row_count=ov.get("fact_payments", 80_000),
            pk_column="payment_id",
            allow_duplicate_injection=False,
            columns=[
                ColumnConfig(name="payment_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="order_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="method", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="paid_at", dtype=DType.TIMESTAMP, nullable=True),
                ColumnConfig(name="amount", dtype=DType.DECIMAL, nullable=False),
                ColumnConfig(name="currency", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="gateway_ref", dtype=DType.VARCHAR, nullable=True),
            ],
        ),
        TableConfig(
            name="bridge_order_promotions",
            row_count=ov.get("bridge_order_promotions", 30_000),
            pk_column="bridge_id",
            columns=[
                ColumnConfig(name="bridge_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                ColumnConfig(name="order_id", dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name="promo_id", dtype=DType.VARCHAR, nullable=False),
            ],
        ),
    ]
    relations = [
        RelationConfig(source_table="fact_orders", source_column="customer_id", target_table="dim_customers", target_column="customer_id"),
        RelationConfig(source_table="fact_orders", source_column="store_id", target_table="dim_stores", target_column="store_id"),
        RelationConfig(source_table="fact_orders", source_column="date_id", target_table="dim_date", target_column="date_id"),
        RelationConfig(source_table="fact_order_items", source_column="order_id", target_table="fact_orders", target_column="order_id"),
        RelationConfig(source_table="fact_order_items", source_column="product_id", target_table="dim_products", target_column="product_id"),
        RelationConfig(source_table="fact_payments", source_column="order_id", target_table="fact_orders", target_column="order_id"),
        RelationConfig(source_table="bridge_order_promotions", source_column="order_id", target_table="fact_orders", target_column="order_id"),
        RelationConfig(source_table="bridge_order_promotions", source_column="promo_id", target_table="dim_promotions", target_column="promo_id"),
    ]
    return tables, relations


class RetailDataBuilder:
    def __init__(
        self,
        config: GeneratorConfig,
        rng: np.random.Generator,
        faker: Faker,
        *,
        date_start: date | None = None,
        date_end: date | None = None,
        id_starts: dict[str, int] | None = None,
        existing_dims: dict[str, pd.DataFrame] | None = None,
    ) -> None:
        self.config = config
        self.rng = rng
        self.faker = faker
        self.discount_seed = config.discount_seed if config.discount_seed is not None else config.seed
        self.discount_rng = build_discount_rng(self.discount_seed) if config.discount_variation else None
        self.range_start, self.range_end = resolve_retail_bounds(config, date_start=date_start, date_end=date_end)
        self.id_starts = {key: int(value) for key, value in (id_starts or {}).items()}
        self.existing_dims = {key: value.copy(deep=True) for key, value in (existing_dims or {}).items()}

    def build_all_tables(self, graph: SchemaGraph) -> dict[str, pd.DataFrame]:
        counts = {table.name: table.row_count for table in graph.tables}
        dim_date = self._build_dim_date(counts["dim_date"])

        if "dim_customers" in self.existing_dims:
            dim_customers = self.existing_dims["dim_customers"].copy(deep=True).reset_index(drop=True)
        else:
            dim_customers = self._build_dim_customers(counts["dim_customers"], dim_date)
        customer_weights = self._customer_propensity_weights(dim_customers)
        customer_discount_propensities = self._customer_discount_propensities(dim_customers)

        if "dim_products" in self.existing_dims:
            dim_products = self.existing_dims["dim_products"].copy(deep=True).reset_index(drop=True)
        else:
            dim_products = self._build_dim_products(counts["dim_products"])

        if "dim_stores" in self.existing_dims:
            dim_stores = self.existing_dims["dim_stores"].copy(deep=True).reset_index(drop=True)
        else:
            dim_stores = self._build_dim_stores(counts["dim_stores"], dim_date)

        dim_promotions, promo_lookup_by_date = self._build_dim_promotions(counts["dim_promotions"], dim_date)
        fact_orders, fact_order_items, fact_payments, bridge = self._build_orders_and_related(
            counts["fact_orders"],
            counts["fact_order_items"],
            counts["bridge_order_promotions"],
            dim_customers,
            dim_products,
            dim_stores,
            dim_date,
            customer_weights,
            customer_discount_propensities,
            promo_lookup_by_date,
        )
        dim_customers = self._apply_customer_metrics(dim_customers, fact_orders)
        return {
            "dim_customers": dim_customers,
            "dim_products": dim_products,
            "dim_stores": dim_stores,
            "dim_date": dim_date,
            "dim_promotions": dim_promotions,
            "fact_orders": fact_orders,
            "fact_order_items": fact_order_items,
            "fact_payments": fact_payments,
            "bridge_order_promotions": bridge,
        }

    def _id_start(self, column_name: str) -> int:
        return self.id_starts.get(column_name, 1)

    def _build_dim_date(self, row_count: int) -> pd.DataFrame:
        if self.config.simulation_start is not None or self.config.simulation_end is not None:
            expected_days = (self.range_end.date() - self.range_start.date()).days + 1
            if row_count != expected_days:
                row_count = expected_days
            dates = pd.date_range(start=self.range_start.date(), end=self.range_end.date(), freq="D")
        else:
            dates = pd.date_range(start=self.range_start.date(), periods=row_count, freq="D")
        return pd.DataFrame(
            {
                "date_id": [date_to_key(ts.date()) for ts in dates],
                "full_date": dates.date,
                "year": dates.year,
                "quarter": dates.quarter,
                "month": dates.month,
                "month_name": dates.strftime("%B"),
                "week": dates.isocalendar().week.astype(int),
                "day_of_week": dates.dayofweek,
                "day_name": dates.strftime("%A"),
                "is_weekend": dates.dayofweek >= 5,
                "is_holiday": False,
            }
        )

    def _build_dim_customers(self, row_count: int, dim_date: pd.DataFrame) -> pd.DataFrame:
        max_customer_dt = pd.Timestamp(dim_date["full_date"].max()).to_pydatetime().replace(hour=23, minute=59, second=59)
        countries = weighted_choice(COUNTRY_NAMES, COUNTRY_WEIGHTS, row_count, self.rng).tolist()
        segments = weighted_choice(_SEGMENTS, _SEGMENT_W, row_count, self.rng).tolist()
        first_names = [self.faker.first_name() for _ in range(row_count)]
        last_names = [self.faker.last_name() for _ in range(row_count)]
        domains = weighted_choice(
            ["gmail.com", "outlook.com", "yahoo.com", "proton.me", "icloud.com"],
            [0.36, 0.24, 0.18, 0.10, 0.12],
            row_count,
            self.rng,
        ).tolist()
        max_days = max((max_customer_dt - datetime(2021, 1, 1)).days, 1)
        created_offsets = self.rng.integers(0, max_days + 1, size=row_count)
        created_at = pd.to_datetime(
            [datetime(2021, 1, 1) + timedelta(days=int(offset), seconds=int(self.rng.integers(0, 24 * 60 * 60))) for offset in created_offsets]
        )
        start_id = self._id_start("customer_id")
        return pd.DataFrame(
            {
                "customer_id": make_id_list("customer_id", start_id, row_count),
                "first_name": first_names,
                "last_name": last_names,
                "email": [
                    f"{_slug(first_names[idx])}.{_slug(last_names[idx])}.{start_id + idx:05d}@{domains[idx]}"
                    for idx in range(row_count)
                ],
                "phone": [self.faker.phone_number() if self.rng.random() > 0.09 else None for _ in range(row_count)],
                "city": [self.faker.city() for _ in range(row_count)],
                "country": countries,
                "segment": segments,
                "created_at": created_at,
                "is_active": True,
                "lifetime_value": np.zeros(row_count),
            }
        )

    def _customer_propensity_weights(self, dim_customers: pd.DataFrame) -> np.ndarray:
        segments = dim_customers["segment"].fillna("B2C").astype(str).tolist()
        weights = np.array(
            [
                float(
                    self.rng.gamma(shape=_SEGMENT_ORDER_WEIGHT_SHAPES.get(segment, 2.0), scale=1.0)
                    * _SEGMENT_ORDER_WEIGHT_MULTIPLIERS.get(segment, 1.0)
                )
                for segment in segments
            ],
            dtype=float,
        )
        if "lifetime_value" in dim_customers.columns:
            ltv = pd.to_numeric(dim_customers["lifetime_value"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
            weights *= 1.0 + np.clip(ltv / 2500.0, 0.0, 1.5)
        weights = np.where(weights > 0.0, weights, 0.1)
        return weights / weights.sum()

    def _build_dim_products(self, row_count: int) -> pd.DataFrame:
        categories = weighted_choice(list(_CATEGORIES.keys()), _CATEGORY_W, row_count, self.rng).tolist()
        subcategories = [str(self.rng.choice(_CATEGORIES[category])) for category in categories]
        cost_price = np.round(bounded_lognormal(3.25, 0.75, 2.0, 750.0, row_count, self.rng), 2)
        if self.config.discount_variation:
            margin_pct = _ENABLED_MARGIN_MIN + (self.rng.beta(2.4, 2.4, row_count) * _ENABLED_MARGIN_RANGE)
            list_price = np.round(cost_price / np.clip(1 - margin_pct, 0.08, None), 2)
        else:
            list_price = np.round(cost_price * (1 + self.rng.uniform(0.18, 1.10, row_count)), 2)
        start_id = self._id_start("product_id")
        return pd.DataFrame(
            {
                "product_id": make_id_list("product_id", start_id, row_count),
                "sku": [f"SKU-{start_id + idx:08d}" for idx in range(row_count)],
                "name": [f"{self.faker.color_name()} {subcategory}" for subcategory in subcategories],
                "category": categories,
                "subcategory": subcategories,
                "brand": [self.faker.company().split()[0] if self.rng.random() > 0.14 else None for _ in range(row_count)],
                "cost_price": cost_price,
                "list_price": list_price,
                "currency": ["USD"] * row_count,
                "weight_kg": np.round(self.rng.uniform(0.1, 25.0, row_count), 3),
                "is_active": self.rng.random(row_count) > 0.04,
            }
        )

    def _customer_discount_propensities(self, dim_customers: pd.DataFrame) -> dict[str, float]:
        if not self.config.discount_variation or self.discount_rng is None:
            return {}
        segment_lookup = (
            dim_customers.assign(customer_id=dim_customers["customer_id"].astype(str))
            .set_index("customer_id")["segment"]
            .astype(str)
            .to_dict()
        )
        lookup: dict[str, float] = {}
        for customer_id in sorted(segment_lookup):
            segment = segment_lookup[customer_id]
            lookup[customer_id] = sample_discount_propensity(_discount_tier_for_segment(segment), self.discount_rng)
        return lookup

    def _build_dim_stores(self, row_count: int, dim_date: pd.DataFrame) -> pd.DataFrame:
        cities = [self.faker.city() for _ in range(row_count)]
        store_types = weighted_choice(_STORE_TYPES, _STORE_TYPE_W, row_count, self.rng).tolist()
        max_open_date = pd.Timestamp(dim_date["full_date"].max()).date()
        start_id = self._id_start("store_id")
        return pd.DataFrame(
            {
                "store_id": make_id_list("store_id", start_id, row_count),
                "store_name": [f"{cities[idx]} {store_types[idx].replace('_', ' ').title()}" for idx in range(row_count)],
                "store_type": store_types,
                "city": cities,
                "country": weighted_choice(COUNTRY_NAMES, COUNTRY_WEIGHTS, row_count, self.rng).tolist(),
                "region": [f"Region-{int(self.rng.integers(1, 9))}" for _ in range(row_count)],
                "opened_date": date_range_samples(date(2012, 1, 1), max_open_date, row_count, self.rng),
                "is_active": self.rng.random(row_count) > 0.08,
            }
        )

    def _build_dim_promotions(
        self,
        row_count: int,
        dim_date: pd.DataFrame,
    ) -> tuple[pd.DataFrame, dict[int, list[dict[str, object]]]]:
        if row_count <= 0:
            empty = pd.DataFrame(
                columns=[
                    "promo_id", "promo_name", "discount_type", "discount_value",
                    "valid_from", "valid_to", "min_order_value", "is_stackable",
                ]
            )
            return empty, {}
        promo_types = weighted_choice(_PROMO_TYPES, _PROMO_W, row_count, self.rng).tolist()
        valid_from = date_range_samples(dim_date["full_date"].min(), dim_date["full_date"].max(), row_count, self.rng)
        valid_to = []
        discount_values: list[float] = []
        for promo_type, vf in zip(promo_types, valid_from):
            valid_to.append(min(vf + timedelta(days=int(self.rng.integers(10, 91))), dim_date["full_date"].max()))
            if promo_type == "percentage":
                discount_values.append(round(float(self.rng.uniform(5, 25)), 2))
            elif promo_type == "fixed_amount":
                discount_values.append(round(float(self.rng.uniform(5, 40)), 2))
            elif promo_type == "free_shipping":
                discount_values.append(0.0)
            else:
                discount_values.append(round(float(self.rng.uniform(5, 15)), 2))
        start_id = self._id_start("promo_id")
        df = pd.DataFrame(
            {
                "promo_id": make_id_list("promo_id", start_id, row_count),
                "promo_name": [f"{str(self.rng.choice(['SAVE', 'FLASH', 'VIP', 'LOYALTY', 'WEEKEND']))}-{start_id + idx:04d}" for idx in range(row_count)],
                "discount_type": promo_types,
                "discount_value": discount_values,
                "valid_from": valid_from,
                "valid_to": np.array(valid_to, dtype=object),
                "min_order_value": np.where(self.rng.random(row_count) > 0.45, np.round(self.rng.uniform(20, 180, row_count), 2), None),
                "is_stackable": self.rng.random(row_count) < 0.24,
            }
        )
        lookup: dict[int, list[dict[str, object]]] = defaultdict(list)
        for row in df.itertuples(index=False):
            current = row.valid_from
            while current <= row.valid_to:
                lookup[date_to_key(current)].append(row._asdict())
                current += timedelta(days=1)
        return df, lookup

    def _build_orders_and_related(
        self,
        order_count: int,
        item_count: int,
        bridge_target: int,
        dim_customers: pd.DataFrame,
        dim_products: pd.DataFrame,
        dim_stores: pd.DataFrame,
        dim_date: pd.DataFrame,
        customer_weights: np.ndarray,
        customer_discount_propensities: dict[str, float],
        promo_lookup_by_date: dict[int, list[dict[str, object]]],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        order_ids = make_id_list("order_id", self._id_start("order_id"), order_count)
        item_ids = make_id_list("item_id", self._id_start("item_id"), item_count)
        payment_ids = make_id_list("payment_id", self._id_start("payment_id"), order_count)
        customer_idx = self.rng.choice(len(dim_customers), size=order_count, p=customer_weights)
        store_idx = self.rng.integers(0, len(dim_stores), size=order_count)
        statuses = weighted_choice(_ORDER_STATUSES, _ORDER_STATUS_W, order_count, self.rng).tolist()
        channels = weighted_choice(_CHANNELS, _CHANNEL_W, order_count, self.rng).tolist()
        line_counts = distribute_counts(item_count, order_count, minimum=1, rng=self.rng)

        product_ids = dim_products["product_id"].astype(str).to_numpy()
        product_prices = dim_products.set_index("product_id")["list_price"].to_dict()
        product_weights = np.clip(dim_products["list_price"].to_numpy(dtype=float), 5.0, 300.0)
        product_weights = (1 / product_weights) ** 0.3
        product_weights = product_weights / product_weights.sum()
        product_weight_lookup = dim_products.set_index("product_id")["weight_kg"].to_dict()

        date_frame = dim_date.copy()
        date_frame["full_date"] = pd.to_datetime(date_frame["full_date"])
        date_frame["weight"] = self._date_weights(date_frame)

        order_records: list[dict[str, object]] = []
        item_records: list[dict[str, object]] = []
        payment_records: list[dict[str, object]] = []
        bridge_pairs: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        item_pointer = 0
        max_dim_dt = pd.Timestamp(dim_date["full_date"].max()).to_pydatetime().replace(hour=23, minute=59, second=59)

        for order_pos, order_id in enumerate(order_ids):
            customer = dim_customers.iloc[int(customer_idx[order_pos])]
            store = dim_stores.iloc[int(store_idx[order_pos])]
            customer_created = pd.Timestamp(customer["created_at"]).to_pydatetime()
            store_opened = pd.Timestamp(store["opened_date"]).date()
            lower_bound = max(
                customer_created,
                datetime.combine(store_opened, time.min),
                self.range_start,
            )
            if lower_bound > max_dim_dt:
                lower_bound = max_dim_dt
            created_at = self._sample_order_datetime(lower_bound, date_frame)
            date_id = date_to_key(created_at.date())
            line_count = int(line_counts[order_pos])
            chosen_products = self.rng.choice(
                product_ids,
                size=line_count,
                replace=line_count > len(product_ids),
                p=product_weights,
            )
            qtys = self.rng.choice([1, 2, 3, 4, 5], size=line_count, p=[0.44, 0.27, 0.16, 0.08, 0.05])
            if self.config.discount_variation and self.discount_rng is not None:
                customer_propensity = customer_discount_propensities.get(str(customer["customer_id"]), 0.22)
                discounts = np.array(
                    [round(sample_discount(customer_propensity, self.discount_rng), 4) for _ in range(line_count)],
                    dtype=float,
                )
            else:
                discounts = np.round(self.rng.beta(1.2, 8.0, size=line_count) * 0.25, 4)

            subtotal = 0.0
            total_weight = 0.0
            for line_idx in range(line_count):
                product_id = str(chosen_products[line_idx])
                unit_price = round(float(product_prices[product_id]), 2)
                line_total = round(float(qtys[line_idx]) * unit_price * (1 - float(discounts[line_idx])), 2)
                subtotal += line_total
                total_weight += float(product_weight_lookup[product_id]) * int(qtys[line_idx])
                item_records.append(
                    {
                        "item_id": item_ids[item_pointer],
                        "order_id": order_id,
                        "product_id": product_id,
                        "qty": int(qtys[line_idx]),
                        "unit_price": unit_price,
                        "discount_pct": round(float(discounts[line_idx]), 4),
                        "line_total": line_total,
                        "return_flag": False,
                    }
                )
                item_pointer += 1
            subtotal = round(subtotal, 2)

            selected_promos = self._select_promotions(date_id, subtotal, promo_lookup_by_date)
            discount_amt = 0.0
            free_shipping = False
            for promo in selected_promos:
                pair = (order_id, str(promo["promo_id"]))
                if pair not in seen_pairs and len(bridge_pairs) < bridge_target:
                    seen_pairs.add(pair)
                    bridge_pairs.append(pair)
                if promo["discount_type"] == "percentage":
                    discount_amt += subtotal * float(promo["discount_value"]) / 100
                elif promo["discount_type"] == "fixed_amount":
                    discount_amt += float(promo["discount_value"])
                elif promo["discount_type"] == "free_shipping":
                    free_shipping = True
                else:
                    discount_amt += subtotal * 0.10
            discount_amt = round(min(discount_amt, subtotal * 0.4), 2)
            shipping_amt = self._shipping_amount(statuses[order_pos], subtotal, total_weight, free_shipping)
            order_total = round(max(subtotal - discount_amt + shipping_amt, 0.0), 2)
            shipped_at, delivered_at = self._order_timestamps(statuses[order_pos], created_at)
            payment_status, paid_at, amount, gateway_ref = self._payment_details(
                statuses[order_pos],
                created_at,
                order_total,
                order_pos,
                self._id_start("payment_id"),
            )

            order_records.append(
                {
                    "order_id": order_id,
                    "customer_id": str(customer["customer_id"]),
                    "store_id": str(store["store_id"]),
                    "date_id": date_id,
                    "channel": channels[order_pos],
                    "status": statuses[order_pos],
                    "currency": "USD",
                    "subtotal": subtotal,
                    "discount_amt": discount_amt,
                    "shipping_amt": shipping_amt,
                    "order_total": order_total,
                    "created_at": created_at,
                    "shipped_at": shipped_at,
                    "delivered_at": delivered_at,
                }
            )
            payment_records.append(
                {
                    "payment_id": payment_ids[order_pos],
                    "order_id": order_id,
                    "method": str(weighted_choice(_PAYMENT_METHODS, _PAYMENT_W, 1, self.rng)[0]),
                    "paid_at": paid_at,
                    "amount": amount,
                    "currency": "USD",
                    "status": payment_status,
                    "gateway_ref": gateway_ref,
                }
            )

        fact_orders = pd.DataFrame(order_records)
        fact_order_items = pd.DataFrame(item_records)
        status_lookup = fact_orders.set_index("order_id")["status"].to_dict()
        for row_idx, row in fact_order_items.iterrows():
            if status_lookup[row["order_id"]] == "refunded":
                fact_order_items.at[row_idx, "return_flag"] = self.rng.random() < 0.55
            elif status_lookup[row["order_id"]] == "delivered":
                fact_order_items.at[row_idx, "return_flag"] = self.rng.random() < 0.04

        while len(bridge_pairs) < bridge_target and not fact_orders.empty:
            sampled_order = fact_orders.iloc[int(self.rng.integers(0, len(fact_orders)))]
            promo_options = promo_lookup_by_date.get(int(sampled_order["date_id"]), [])
            if not promo_options:
                break
            promo_id = str(promo_options[int(self.rng.integers(0, len(promo_options)))]["promo_id"])
            pair = (str(sampled_order["order_id"]), promo_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            bridge_pairs.append(pair)

        return (
            fact_orders,
            fact_order_items,
            pd.DataFrame(payment_records),
            pd.DataFrame(
                {
                    "bridge_id": make_id_list("bridge_id", self._id_start("bridge_id"), len(bridge_pairs)),
                    "order_id": [pair[0] for pair in bridge_pairs],
                    "promo_id": [pair[1] for pair in bridge_pairs],
                }
            ),
        )

    def _date_weights(self, date_frame: pd.DataFrame) -> np.ndarray:
        weights = np.ones(len(date_frame), dtype=float)
        weights *= np.where(date_frame["day_of_week"].to_numpy(dtype=int) >= 5, 1.18, 1.0)
        day_numbers = date_frame["full_date"].dt.day.to_numpy(dtype=int)
        weights *= np.where(np.isin(day_numbers, [1, 2, 3, 14, 15, 16, 30, 31]), 1.12, 1.0)
        weights *= np.where((day_numbers >= 25) & (day_numbers <= 28), 1.05, 1.0)
        return weights / weights.sum()

    def _sample_order_datetime(self, lower_bound: datetime, date_frame: pd.DataFrame) -> datetime:
        eligible = date_frame.loc[date_frame["full_date"] >= pd.Timestamp(lower_bound.date())].copy()
        if eligible.empty:
            return lower_bound
        weights = eligible["weight"].to_numpy(dtype=float)
        weights = weights / weights.sum()
        picked = eligible.iloc[int(self.rng.choice(len(eligible), p=weights))]
        chosen_date = pd.Timestamp(picked["full_date"]).date()
        day_start = datetime.combine(chosen_date, time.min)
        start = max(lower_bound, day_start)
        day_end = datetime.combine(chosen_date, time.max).replace(microsecond=0)
        if start >= day_end:
            return start
        delta_seconds = int((day_end - start).total_seconds())
        return start + timedelta(seconds=int(self.rng.integers(0, delta_seconds + 1)))

    def _apply_customer_metrics(self, dim_customers: pd.DataFrame, fact_orders: pd.DataFrame) -> pd.DataFrame:
        dim_customers = dim_customers.copy(deep=True)
        base_ltv = pd.to_numeric(dim_customers.get("lifetime_value", 0.0), errors="coerce").fillna(0.0)
        customer_ltv = (
            fact_orders.loc[~fact_orders["status"].eq("cancelled")]
            .groupby("customer_id")["order_total"]
            .sum()
            .round(2)
        )
        customer_recent = fact_orders.groupby("customer_id")["created_at"].max()
        dim_customers["lifetime_value"] = (
            base_ltv + dim_customers["customer_id"].map(customer_ltv).fillna(0.0)
        ).round(2)
        cutoff = pd.Timestamp(self.range_end - timedelta(days=365))
        existing_active = pd.Series(dim_customers.get("is_active", False), index=dim_customers.index).astype(bool)
        new_activity = dim_customers["customer_id"].map(customer_recent).apply(
            lambda ts: pd.Timestamp(ts) >= cutoff if pd.notna(ts) else None
        )
        dim_customers["is_active"] = new_activity.where(new_activity.notna(), existing_active).astype(bool)
        return dim_customers

    def _select_promotions(
        self,
        date_id: int,
        subtotal: float,
        promo_lookup_by_date: dict[int, list[dict[str, object]]],
    ) -> list[dict[str, object]]:
        valid_promos = [
            promo for promo in promo_lookup_by_date.get(date_id, [])
            if promo["min_order_value"] is None or subtotal >= float(promo["min_order_value"])
        ]
        if not valid_promos or self.rng.random() >= 0.24:
            return []
        selected = [valid_promos[int(self.rng.integers(0, len(valid_promos)))]]
        stackables = [promo for promo in valid_promos if promo["promo_id"] != selected[0]["promo_id"] and promo["is_stackable"]]
        if stackables and self.rng.random() < 0.08:
            selected.append(stackables[int(self.rng.integers(0, len(stackables)))])
        return selected

    def _shipping_amount(self, status: str, subtotal: float, total_weight: float, free_shipping: bool) -> float:
        if status in {"pending", "confirmed", "cancelled"}:
            return 0.0
        if free_shipping or subtotal >= 75:
            return 0.0
        return round(4.5 + min(total_weight, 25.0) * 0.35, 2)

    def _order_timestamps(self, status: str, created_at: datetime) -> tuple[datetime | None, datetime | None]:
        shipped_at: datetime | None = None
        delivered_at: datetime | None = None
        if status in {"shipped", "delivered", "refunded"}:
            shipped_at = created_at + timedelta(hours=int(self.rng.integers(6, 72)))
        if status in {"delivered", "refunded"} and shipped_at is not None:
            delivered_at = shipped_at + timedelta(hours=int(self.rng.integers(12, 216)))
        return shipped_at, delivered_at

    def _payment_details(
        self,
        order_status: str,
        created_at: datetime,
        order_total: float,
        sequence: int,
        payment_start: int,
    ) -> tuple[str, datetime | None, float, str | None]:
        if order_status == "cancelled":
            payment_status = "failed" if self.rng.random() < 0.82 else "refunded"
        elif order_status == "pending":
            payment_status = "pending" if self.rng.random() < 0.72 else "failed"
        elif order_status == "confirmed":
            payment_status = "completed" if self.rng.random() < 0.84 else "pending"
        elif order_status == "refunded":
            payment_status = "refunded"
        else:
            payment_status = "completed"
        ref_value = payment_start + sequence
        if payment_status in {"completed", "refunded"}:
            return (
                payment_status,
                created_at + timedelta(minutes=int(self.rng.integers(5, 60 * 48))),
                round(order_total, 2),
                f"GW-{ref_value:012X}",
            )
        if payment_status == "pending":
            return payment_status, None, round(order_total, 2), f"GW-{ref_value:012X}"
        return payment_status, None, 0.0, None
