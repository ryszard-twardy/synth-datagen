"""
Monthly retail sales dataset generation on top of the normalized retail engine schema.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from enum import Enum
import json
from math import ceil
from pathlib import Path
import re

import numpy as np
import pandas as pd
from pydantic import Field, field_validator, model_validator

from .config import (
    DataQuality,
    DataQualityConfig,
    Dialect,
    GeneratorConfig,
    Scenario,
    SchemaType,
    StrictModel,
)
from .exporters.csv_exporter import CsvExporter
from .exporters.parquet_exporter import ParquetExporter
from .exporters.sql_exporter import SqlExporter
from .exporters.sqlite_exporter import SqliteExporter
from .generators.retail_builder import RetailDataBuilder, build_retail_schema
from .monthly_sales_audit import apply_flat_audit_bad_data, apply_monthly_audit_bad_data
from .monthly_sales_profile import (
    MonthlySalesBadDataProfile,
    MonthlySalesProfile,
    MonthlyTrendMode,
)
from .reporting import write_data_dictionary, write_erd
from .schema_builder import SchemaBuilder, SchemaGraph
from .utils import apply_data_quality, distribute_counts, seed_everything
from .id_utils import next_start


DIMENSION_TABLE_NAMES = [
    "dim_customers",
    "dim_products",
    "dim_stores",
    "dim_date",
    "dim_promotions",
]
SALES_FILE_RE = re.compile(r"^sales_(\d{6})\.csv$")


class MonthlyLayout(str, Enum):
    MONTHLY = "monthly"
    COMBINED = "combined"
    BOTH = "both"
    SALES_FILES = "sales-files"


@dataclass(frozen=True)
class MonthBucket:
    label: str
    start_date: date
    end_date: date
    active_days: int
    days_in_month: int
    order_count: int = 0
    item_count: int = 0
    bridge_count: int = 0
    promo_count: int = 0


@dataclass(frozen=True)
class SalesFilesResumeState:
    dimension_tables: dict[str, pd.DataFrame]
    builder_dims: dict[str, pd.DataFrame]
    id_starts: dict[str, int]
    existing_month_labels: list[str]
    source_root: Path


class MonthlySalesConfig(StrictModel):
    start_date: date
    end_date: date
    orders_per_month: int
    avg_items_per_order: float = 2.5
    layout: MonthlyLayout = MonthlyLayout.MONTHLY
    include_flat: bool = True
    resume_from: Path | None = None
    output_dir: Path
    seed: int = 42
    discount_variation: bool = True
    data_quality: DataQuality = DataQuality.NONE
    export_parquet: bool = False
    export_sqlite: bool = False
    customers: int | None = None
    products: int | None = None
    stores: int | None = None
    promotions: int | None = None
    prorate_partial_months: bool = True
    profile_config: Path | None = None
    max_orders_per_month: int | None = None
    trend_mode: MonthlyTrendMode | None = None
    start_ratio: float = 1.0
    seasonality_strength: float = 0.0
    volatility_strength: float = 0.0
    audit_bad_data: MonthlySalesBadDataProfile = Field(
        default_factory=MonthlySalesBadDataProfile
    )

    @classmethod
    def from_inputs(
        cls,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        month: str | None = None,
        **kwargs: object,
    ) -> "MonthlySalesConfig":
        if month:
            if start_date or end_date:
                raise ValueError("Use either month or start_date/end_date, not both.")
            start_date, end_date = month_to_range(month)
        if start_date is None or end_date is None:
            raise ValueError(
                "start_date and end_date are required unless month is provided."
            )
        return cls(start_date=start_date, end_date=end_date, **kwargs)

    @classmethod
    def from_profile(
        cls,
        profile: MonthlySalesProfile,
        *,
        profile_path: Path,
        output_dir: Path,
        seed: int,
    ) -> "MonthlySalesConfig":
        try:
            layout = MonthlyLayout(profile.output.layout.strip().lower())
        except ValueError as exc:
            raise ValueError(
                "output.layout must be one of: monthly, combined, both, sales-files."
            ) from exc
        return cls(
            start_date=profile.period.start_date,
            end_date=profile.period.end_date,
            orders_per_month=profile.volume.max_orders_per_month,
            avg_items_per_order=2.5,
            layout=layout,
            include_flat=profile.output.include_flat,
            output_dir=output_dir,
            seed=seed,
            discount_variation=True,
            data_quality=DataQuality.NONE,
            profile_config=profile_path,
            max_orders_per_month=profile.volume.max_orders_per_month,
            trend_mode=profile.volume.trend_mode,
            start_ratio=profile.volume.start_ratio,
            seasonality_strength=profile.volume.seasonality_strength,
            volatility_strength=profile.volume.volatility_strength,
            audit_bad_data=profile.bad_data,
        )

    @field_validator("output_dir", "resume_from", "profile_config", mode="before")
    @classmethod
    def coerce_paths(cls, value: object) -> Path | None:
        if value is None:
            return None
        return Path(value)

    @model_validator(mode="after")
    def validate_config(self) -> "MonthlySalesConfig":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        if self.orders_per_month <= 0:
            raise ValueError("orders_per_month must be > 0")
        if self.avg_items_per_order < 1.0:
            raise ValueError("avg_items_per_order must be >= 1.0")
        if self.max_orders_per_month is not None and self.max_orders_per_month <= 0:
            raise ValueError("max_orders_per_month must be > 0")
        if self.trend_mode is not None and self.max_orders_per_month is None:
            raise ValueError("max_orders_per_month is required when trend_mode is set")
        if self.audit_bad_data.enabled and self.data_quality is not DataQuality.NONE:
            raise ValueError(
                "audit_bad_data cannot be combined with legacy data_quality modes"
            )
        if self.audit_bad_data.has_flat_defects() and not self.include_flat:
            raise ValueError(
                "include_flat must be enabled when flat-level audit defects are configured"
            )
        if self.layout is MonthlyLayout.SALES_FILES:
            if not self.include_flat:
                raise ValueError("sales-files layout requires include_flat=True")
            if self.export_parquet or self.export_sqlite:
                raise ValueError(
                    "sales-files layout does not support export_parquet or export_sqlite"
                )
            if self.audit_bad_data.has_normalized_defects():
                raise ValueError(
                    "sales-files layout supports only flat-level audit defects"
                )
        elif self.audit_bad_data.enabled and self.resume_from is not None:
            raise ValueError(
                "audit_bad_data is not supported together with resume_from outside sales-files layout"
            )
        if self.resume_from is not None:
            path = self.resume_from
            if self.layout is MonthlyLayout.SALES_FILES:
                if (
                    path.name != "combined"
                    and (path / "combined").exists()
                    and not _has_dimension_snapshot(path)
                ):
                    path = path / "combined"
                if not _has_dimension_snapshot(path):
                    raise ValueError(
                        "resume_from must contain dimension CSVs or a combined snapshot"
                    )
                return self
            if path.name != "combined" and (path / "combined").exists():
                path = path / "combined"
            required = [
                "dim_customers.csv",
                "dim_products.csv",
                "dim_stores.csv",
                "dim_date.csv",
                "dim_promotions.csv",
                "fact_orders.csv",
                "fact_order_items.csv",
                "fact_payments.csv",
                "bridge_order_promotions.csv",
            ]
            missing = [name for name in required if not (path / name).exists()]
            if missing:
                raise ValueError(
                    f"resume_from is missing retail combined tables: {missing}"
                )
        return self


def month_to_range(value: str) -> tuple[date, date]:
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        start = date(year, month, 1)
    except Exception as exc:  # pragma: no cover - defensive parse guard
        raise ValueError("month must be in YYYY-MM format") from exc
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def month_label_to_sales_filename(label: str) -> str:
    return f"sales_{label.replace('-', '')}.csv"


def compact_month_to_label(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}"


def _has_dimension_snapshot(path: Path) -> bool:
    return all((path / f"{name}.csv").exists() for name in DIMENSION_TABLE_NAMES)


def _sales_file_labels(path: Path) -> list[str]:
    labels: list[str] = []
    for file_path in path.glob("sales_*.csv"):
        match = SALES_FILE_RE.match(file_path.name)
        if match:
            labels.append(compact_month_to_label(match.group(1)))
    return sorted(set(labels))


def _month_label_end_date(label: str) -> date:
    start, end = month_to_range(label)
    return end


def _growth_order_targets(
    config: MonthlySalesConfig, buckets: list[MonthBucket]
) -> np.ndarray:
    if not buckets:
        return np.array([], dtype=np.int64)
    max_orders = config.max_orders_per_month or config.orders_per_month
    start_orders = max(1, int(round(max_orders * config.start_ratio)))
    if len(buckets) == 1:
        linear = np.array([max_orders], dtype=float)
    else:
        linear = np.linspace(start_orders, max_orders, num=len(buckets), dtype=float)
    month_offsets = np.arange(len(buckets), dtype=float)
    seasonality = 1.0 + (
        config.seasonality_strength * np.sin((2.0 * np.pi * month_offsets) / 12.0)
    )
    rng = np.random.default_rng(config.seed + 77)
    volatility = 1.0 + rng.normal(0.0, config.volatility_strength, size=len(buckets))
    targets = np.rint(linear * seasonality * volatility).astype(np.int64)
    targets = np.clip(targets, 1, max_orders)
    if len(targets) > 1 and targets[-1] <= targets[0]:
        targets[-1] = min(max_orders, max(targets[-1], targets[0] + 1))
    return targets


def month_buckets(config: MonthlySalesConfig) -> list[MonthBucket]:
    buckets: list[MonthBucket] = []
    cursor = date(config.start_date.year, config.start_date.month, 1)
    while cursor <= config.end_date:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        active_start = max(cursor, config.start_date)
        active_end = min(month_end, config.end_date)
        active_days = (active_end - active_start).days + 1
        days_in_month = month_end.day
        buckets.append(
            MonthBucket(
                label=f"{cursor.year:04d}-{cursor.month:02d}",
                start_date=active_start,
                end_date=active_end,
                active_days=active_days,
                days_in_month=days_in_month,
            )
        )
        cursor = next_month
    full_targets = (
        _growth_order_targets(config, buckets)
        if config.trend_mode is MonthlyTrendMode.GROWTH
        else np.full(len(buckets), config.orders_per_month, dtype=np.int64)
    )
    planned: list[MonthBucket] = []
    for idx, bucket in enumerate(buckets):
        order_count = int(full_targets[idx])
        if config.prorate_partial_months and bucket.active_days < bucket.days_in_month:
            order_count = max(
                1, int(round(order_count * bucket.active_days / bucket.days_in_month))
            )
        planned.append(
            MonthBucket(
                label=bucket.label,
                start_date=bucket.start_date,
                end_date=bucket.end_date,
                active_days=bucket.active_days,
                days_in_month=bucket.days_in_month,
                order_count=order_count,
            )
        )
    return planned


def derive_dimension_counts(
    config: MonthlySalesConfig, total_orders: int, total_items: int, month_count: int
) -> dict[str, int]:
    return {
        "dim_customers": config.customers
        or max(ceil(total_orders / 1.8), month_count * 250),
        "dim_products": config.products or max(250, min(5000, ceil(total_items / 40))),
        "dim_stores": config.stores or max(8, min(250, ceil(total_orders / 600))),
        "dim_promotions": config.promotions or max(12, min(300, month_count * 6)),
    }


def build_month_plan(config: MonthlySalesConfig) -> list[MonthBucket]:
    base = month_buckets(config)
    order_counts = np.array([bucket.order_count for bucket in base], dtype=np.int64)
    total_orders = int(order_counts.sum())
    total_items = max(
        total_orders, int(round(total_orders * config.avg_items_per_order))
    )
    total_bridge = int(round(total_orders * 0.35))
    dimension_counts = derive_dimension_counts(
        config, total_orders, total_items, len(base)
    )
    minimum_promos = 1 if dimension_counts["dim_promotions"] >= len(base) else 0
    extra_item_counts = distribute_counts(
        total_items - total_orders,
        len(base),
        minimum=0,
        rng=np.random.default_rng(config.seed + 101),
        weights=order_counts.astype(float),
    )
    item_counts = order_counts + extra_item_counts
    bridge_counts = distribute_counts(
        total_bridge,
        len(base),
        minimum=0,
        rng=np.random.default_rng(config.seed + 102),
        weights=order_counts.astype(float),
    )
    promo_counts = distribute_counts(
        dimension_counts["dim_promotions"],
        len(base),
        minimum=minimum_promos,
        rng=np.random.default_rng(config.seed + 103),
        weights=order_counts.astype(float),
    )
    planned: list[MonthBucket] = []
    for idx, bucket in enumerate(base):
        planned.append(
            MonthBucket(
                label=bucket.label,
                start_date=bucket.start_date,
                end_date=bucket.end_date,
                active_days=bucket.active_days,
                days_in_month=bucket.days_in_month,
                order_count=int(order_counts[idx]),
                item_count=int(item_counts[idx]),
                bridge_count=int(bridge_counts[idx]),
                promo_count=int(promo_counts[idx]),
            )
        )
    return planned


def load_sales_files_resume_state(path: Path | None) -> SalesFilesResumeState | None:
    if path is None:
        return None
    source_root = path
    combined_path = (
        path / "combined"
        if path.name != "combined" and (path / "combined").exists()
        else path
    )
    if (combined_path / "fact_orders.csv").exists() and _has_dimension_snapshot(
        combined_path
    ):
        dimension_root = combined_path
        dimension_tables = {
            name: pd.read_csv(dimension_root / f"{name}.csv")
            for name in DIMENSION_TABLE_NAMES
        }
        fact_orders = pd.read_csv(dimension_root / "fact_orders.csv")
        fact_order_items = pd.read_csv(dimension_root / "fact_order_items.csv")
        existing_month_labels = sorted(
            pd.to_datetime(fact_orders["created_at"], errors="coerce")
            .dt.strftime("%Y-%m")
            .dropna()
            .unique()
            .tolist()
        )
        order_ids = fact_orders["order_id"].dropna().astype(str).tolist()
        item_ids = fact_order_items["item_id"].dropna().astype(str).tolist()
        source_root = dimension_root
    else:
        dimension_root = path
        if not _has_dimension_snapshot(dimension_root):
            raise ValueError(
                "resume_from must contain dimension CSVs or a combined snapshot"
            )
        dimension_tables = {
            name: pd.read_csv(dimension_root / f"{name}.csv")
            for name in DIMENSION_TABLE_NAMES
        }
        existing_month_labels = _sales_file_labels(dimension_root)
        # Audit P1-9: drop redundant annotations — mypy flagged the names
        # as redefined when the if-branch above already bound them.
        order_ids = []
        item_ids = []
        for label in existing_month_labels:
            sales_path = dimension_root / month_label_to_sales_filename(label)
            sales_df = pd.read_csv(sales_path)
            order_ids.extend(sales_df["OrderID"].dropna().astype(str).tolist())
            item_ids.extend(sales_df["OrderItemID"].dropna().astype(str).tolist())
    id_starts = {
        "customer_id": next_start(
            "customer_id",
            dimension_tables["dim_customers"]["customer_id"]
            .dropna()
            .astype(str)
            .tolist(),
        ),
        "product_id": next_start(
            "product_id",
            dimension_tables["dim_products"]["product_id"]
            .dropna()
            .astype(str)
            .tolist(),
        ),
        "store_id": next_start(
            "store_id",
            dimension_tables["dim_stores"]["store_id"].dropna().astype(str).tolist(),
        ),
        "promo_id": next_start(
            "promo_id",
            dimension_tables["dim_promotions"]["promo_id"]
            .dropna()
            .astype(str)
            .tolist(),
        ),
        "order_id": next_start("order_id", order_ids) if order_ids else 1,
        "item_id": next_start("item_id", item_ids) if item_ids else 1,
        "payment_id": 1,
        "bridge_id": 1,
    }
    return SalesFilesResumeState(
        dimension_tables=dimension_tables,
        builder_dims={
            "dim_customers": dimension_tables["dim_customers"].copy(deep=True),
            "dim_products": dimension_tables["dim_products"].copy(deep=True),
            "dim_stores": dimension_tables["dim_stores"].copy(deep=True),
        },
        id_starts=id_starts,
        existing_month_labels=existing_month_labels,
        source_root=source_root,
    )


def validate_sales_files_resume_range(
    resume_state: SalesFilesResumeState, new_start_date: date
) -> None:
    if not resume_state.existing_month_labels:
        return
    latest_label = max(resume_state.existing_month_labels)
    latest_end = _month_label_end_date(latest_label)
    if new_start_date <= latest_end:
        raise ValueError(
            f"resume_from contains sales data through {latest_end.isoformat()}, "
            f"so start_date must be later than that."
        )


def generate_monthly_sales(config: MonthlySalesConfig) -> dict[str, Path]:
    _, rng, faker = seed_everything(config.seed)
    plan = build_month_plan(config)
    dimension_counts = derive_dimension_counts(
        config,
        total_orders=sum(bucket.order_count for bucket in plan),
        total_items=sum(bucket.item_count for bucket in plan),
        month_count=len(plan),
    )
    combined_path = config.output_dir / "combined"
    months_root = config.output_dir / "months"
    config.output_dir.mkdir(parents=True, exist_ok=True)

    sales_resume_state = (
        load_sales_files_resume_state(config.resume_from)
        if config.layout is MonthlyLayout.SALES_FILES
        else None
    )
    if sales_resume_state is not None:
        validate_sales_files_resume_range(sales_resume_state, config.start_date)

    resume_tables = (
        load_resume_tables(config.resume_from)
        if config.resume_from and sales_resume_state is None
        else None
    )
    if resume_tables is not None:
        validate_resume_range(resume_tables, config.start_date)

    if sales_resume_state is not None:
        id_starts = sales_resume_state.id_starts.copy()
        base_dims = {
            "dim_customers": sales_resume_state.builder_dims["dim_customers"].copy(
                deep=True
            ),
            "dim_products": sales_resume_state.builder_dims["dim_products"].copy(
                deep=True
            ),
            "dim_stores": sales_resume_state.builder_dims["dim_stores"].copy(deep=True),
        }
    else:
        id_starts = initial_id_starts(resume_tables)
        base_dims = (
            {
                "dim_customers": resume_tables["dim_customers"].copy(deep=True),
                "dim_products": resume_tables["dim_products"].copy(deep=True),
                "dim_stores": resume_tables["dim_stores"].copy(deep=True),
            }
            if resume_tables is not None
            else None
        )
    appended_tables: dict[str, list[pd.DataFrame]] = {
        "dim_date": [],
        "dim_promotions": [],
        "fact_orders": [],
        "fact_order_items": [],
        "fact_payments": [],
        "bridge_order_promotions": [],
    }

    for month_index, bucket in enumerate(plan):
        row_overrides = {
            "dim_customers": len(base_dims["dim_customers"])
            if base_dims is not None
            else dimension_counts["dim_customers"],
            "dim_products": len(base_dims["dim_products"])
            if base_dims is not None
            else dimension_counts["dim_products"],
            "dim_stores": len(base_dims["dim_stores"])
            if base_dims is not None
            else dimension_counts["dim_stores"],
            "dim_date": bucket.active_days,
            "dim_promotions": bucket.promo_count,
            "fact_orders": bucket.order_count,
            "fact_order_items": bucket.item_count,
            "fact_payments": bucket.order_count,
            "bridge_order_promotions": bucket.bridge_count,
        }
        generator_config = GeneratorConfig(
            scenario=Scenario.RETAIL,
            schema_type=SchemaType.STAR,
            dialect=Dialect.POSTGRES,
            seed=config.seed + month_index,
            discount_seed=config.seed,
            discount_variation=config.discount_variation,
            output_dir=combined_path,
            simulation_start=bucket.start_date,
            simulation_end=bucket.end_date,
            row_overrides=row_overrides,
            data_quality=DataQualityConfig(level=DataQuality.NONE),
        )
        raw_tables, raw_relations = build_retail_schema(generator_config)
        graph = SchemaBuilder(generator_config).build(raw_tables, raw_relations)
        builder = RetailDataBuilder(
            generator_config,
            rng,
            faker,
            date_start=bucket.start_date,
            date_end=bucket.end_date,
            id_starts=id_starts,
            existing_dims=base_dims,
        )
        tables = builder.build_all_tables(graph)
        base_dims = {
            "dim_customers": tables["dim_customers"].copy(deep=True),
            "dim_products": tables["dim_products"].copy(deep=True),
            "dim_stores": tables["dim_stores"].copy(deep=True),
        }
        for table_name in appended_tables:
            appended_tables[table_name].append(tables[table_name])
        id_starts = next_id_starts(id_starts, tables)

    combined_canonical = build_combined_canonical_tables(
        base_dims, appended_tables, resume_tables, config.end_date
    )
    graph = build_combined_graph(
        config, dimension_counts, plan, combined_path, combined_canonical
    )
    defect_summary: dict[str, object] = {}

    if config.audit_bad_data.enabled:
        exported_tables, normalized_summary = apply_monthly_audit_bad_data(
            combined_canonical,
            config.audit_bad_data,
            np.random.default_rng(config.seed + 500),
        )
        defect_summary["normalized"] = normalized_summary
        flat_for_manifest, flat_summary = apply_flat_audit_bad_data(
            build_flat_extract(exported_tables),
            config.audit_bad_data,
            np.random.default_rng(config.seed + 700),
        )
        defect_summary["flat"] = flat_summary
    elif resume_tables is None:
        exported_tables = apply_dq_to_tables(
            combined_canonical,
            graph,
            dq_config=monthly_dq_config(config.data_quality),
            rng=np.random.default_rng(config.seed + 500),
        )
        flat_for_manifest = (
            build_flat_extract(exported_tables) if config.include_flat else None
        )
    else:
        new_canonical = build_combined_canonical_tables(
            base_dims, appended_tables, None, config.end_date
        )
        new_exported = apply_dq_to_tables(
            new_canonical,
            graph,
            dq_config=monthly_dq_config(config.data_quality),
            rng=np.random.default_rng(config.seed + 500),
            tables_to_process=set(appended_tables.keys()),
        )
        exported_tables = merge_resume_and_new_tables(
            resume_tables, new_exported, config.end_date
        )
        flat_for_manifest = (
            build_flat_extract(exported_tables) if config.include_flat else None
        )

    outputs: dict[str, Path] = {}
    exported_dimension_tables = (
        sales_resume_state.dimension_tables
        if sales_resume_state is not None
        else {
            name: exported_tables[name].copy(deep=True)
            for name in DIMENSION_TABLE_NAMES
        }
    )
    sales_file_counts: dict[str, int] = {}
    if config.layout in {MonthlyLayout.COMBINED, MonthlyLayout.BOTH}:
        outputs["combined"] = write_combined_bundle(
            config, graph, exported_tables, combined_path, flat_df=flat_for_manifest
        )
    if config.layout in {MonthlyLayout.MONTHLY, MonthlyLayout.BOTH}:
        months_root.mkdir(parents=True, exist_ok=True)
        write_monthly_bundles(
            config,
            exported_tables,
            graph,
            months_root,
            audit_bad_data=config.audit_bad_data
            if config.audit_bad_data.enabled
            else None,
        )
        outputs["months"] = months_root
    if config.layout is MonthlyLayout.SALES_FILES:
        sales_file_counts = write_sales_files_bundle(
            config,
            exported_tables,
            config.output_dir,
            dimension_tables=exported_dimension_tables,
            audit_bad_data=config.audit_bad_data
            if config.audit_bad_data.enabled
            else None,
        )
        outputs["sales_files"] = config.output_dir

    write_manifest(
        config,
        plan,
        exported_tables,
        outputs,
        flat_for_manifest=flat_for_manifest,
        defect_summary=defect_summary,
        dimension_tables_for_manifest=exported_dimension_tables,
        sales_file_counts=sales_file_counts,
        dimension_source=sales_resume_state.source_root
        if sales_resume_state is not None
        else None,
    )
    return outputs


def monthly_dq_config(level: DataQuality) -> DataQualityConfig:
    return DataQualityConfig(level=level).model_copy(update={"dupe_rate": 0.0})


def initial_id_starts(resume_tables: dict[str, pd.DataFrame] | None) -> dict[str, int]:
    if resume_tables is None:
        return {
            "customer_id": 1,
            "product_id": 1,
            "store_id": 1,
            "promo_id": 1,
            "order_id": 1,
            "item_id": 1,
            "payment_id": 1,
            "bridge_id": 1,
        }
    return {
        "customer_id": next_start(
            "customer_id", resume_tables["dim_customers"]["customer_id"].tolist()
        ),
        "product_id": next_start(
            "product_id", resume_tables["dim_products"]["product_id"].tolist()
        ),
        "store_id": next_start(
            "store_id", resume_tables["dim_stores"]["store_id"].tolist()
        ),
        "promo_id": next_start(
            "promo_id", resume_tables["dim_promotions"]["promo_id"].tolist()
        ),
        "order_id": next_start(
            "order_id", resume_tables["fact_orders"]["order_id"].tolist()
        ),
        "item_id": next_start(
            "item_id", resume_tables["fact_order_items"]["item_id"].tolist()
        ),
        "payment_id": next_start(
            "payment_id", resume_tables["fact_payments"]["payment_id"].tolist()
        ),
        "bridge_id": next_start(
            "bridge_id", resume_tables["bridge_order_promotions"]["bridge_id"].tolist()
        ),
    }


def next_id_starts(
    current: dict[str, int], tables: dict[str, pd.DataFrame]
) -> dict[str, int]:
    next_values = current.copy()
    next_values["promo_id"] = current["promo_id"] + len(tables["dim_promotions"])
    next_values["order_id"] = current["order_id"] + len(tables["fact_orders"])
    next_values["item_id"] = current["item_id"] + len(tables["fact_order_items"])
    next_values["payment_id"] = current["payment_id"] + len(tables["fact_payments"])
    next_values["bridge_id"] = current["bridge_id"] + len(
        tables["bridge_order_promotions"]
    )
    if "dim_customers" in tables and current["customer_id"] == 1:
        next_values["customer_id"] = current["customer_id"] + len(
            tables["dim_customers"]
        )
    if "dim_products" in tables and current["product_id"] == 1:
        next_values["product_id"] = current["product_id"] + len(tables["dim_products"])
    if "dim_stores" in tables and current["store_id"] == 1:
        next_values["store_id"] = current["store_id"] + len(tables["dim_stores"])
    return next_values


def build_combined_canonical_tables(
    base_dims: dict[str, pd.DataFrame] | None,
    appended_tables: dict[str, list[pd.DataFrame]],
    resume_tables: dict[str, pd.DataFrame] | None,
    as_of_date: date,
) -> dict[str, pd.DataFrame]:
    if base_dims is None and resume_tables is None:
        raise ValueError("No base dimensions available for monthly sales generation")
    dim_products = (base_dims or resume_tables)["dim_products"].copy(deep=True)
    dim_stores = (base_dims or resume_tables)["dim_stores"].copy(deep=True)
    fact_orders = concat_frames(
        ([resume_tables["fact_orders"]] if resume_tables else [])
        + appended_tables["fact_orders"]
    )
    fact_order_items = concat_frames(
        ([resume_tables["fact_order_items"]] if resume_tables else [])
        + appended_tables["fact_order_items"]
    )
    fact_payments = concat_frames(
        ([resume_tables["fact_payments"]] if resume_tables else [])
        + appended_tables["fact_payments"]
    )
    bridge = concat_frames(
        ([resume_tables["bridge_order_promotions"]] if resume_tables else [])
        + appended_tables["bridge_order_promotions"]
    )
    dim_date = (
        concat_frames(
            ([resume_tables["dim_date"]] if resume_tables else [])
            + appended_tables["dim_date"]
        )
        .drop_duplicates(subset=["date_id"])
        .sort_values("date_id")
        .reset_index(drop=True)
    )
    dim_promotions = (
        concat_frames(
            ([resume_tables["dim_promotions"]] if resume_tables else [])
            + appended_tables["dim_promotions"]
        )
        .drop_duplicates(subset=["promo_id"])
        .reset_index(drop=True)
    )
    dim_customers = refresh_customer_metrics(
        (base_dims or resume_tables)["dim_customers"].copy(deep=True),
        fact_orders,
        as_of_date,
    )
    return {
        "dim_customers": dim_customers.reset_index(drop=True),
        "dim_products": dim_products.reset_index(drop=True),
        "dim_stores": dim_stores.reset_index(drop=True),
        "dim_date": dim_date,
        "dim_promotions": dim_promotions,
        "fact_orders": fact_orders.reset_index(drop=True),
        "fact_order_items": fact_order_items.reset_index(drop=True),
        "fact_payments": fact_payments.reset_index(drop=True),
        "bridge_order_promotions": bridge.reset_index(drop=True),
    }


def refresh_customer_metrics(
    dim_customers: pd.DataFrame, fact_orders: pd.DataFrame, as_of_date: date
) -> pd.DataFrame:
    dim_customers = dim_customers.copy(deep=True)
    customer_ltv = (
        fact_orders.loc[~fact_orders["status"].eq("cancelled")]
        .groupby("customer_id")["order_total"]
        .sum()
        .round(2)
    )
    customer_recent = (
        pd.to_datetime(fact_orders["created_at"], errors="coerce")
        .groupby(fact_orders["customer_id"])
        .max()
    )
    dim_customers["lifetime_value"] = (
        dim_customers["customer_id"].map(customer_ltv).fillna(0.0).round(2)
    )
    cutoff = pd.Timestamp(as_of_date) - timedelta(days=365)
    dim_customers["is_active"] = (
        dim_customers["customer_id"]
        .map(customer_recent)
        .fillna(pd.to_datetime(dim_customers["created_at"], errors="coerce"))
        .apply(lambda ts: pd.Timestamp(ts) >= cutoff)
    )
    return dim_customers


def build_combined_graph(
    config: MonthlySalesConfig,
    dimension_counts: dict[str, int],
    plan: list[MonthBucket],
    output_dir: Path,
    combined_tables: dict[str, pd.DataFrame],
) -> SchemaGraph:
    row_overrides = {
        "dim_customers": len(combined_tables["dim_customers"]),
        "dim_products": len(combined_tables["dim_products"]),
        "dim_stores": len(combined_tables["dim_stores"]),
        "dim_date": len(combined_tables["dim_date"]),
        "dim_promotions": len(combined_tables["dim_promotions"])
        or dimension_counts["dim_promotions"],
        "fact_orders": len(combined_tables["fact_orders"]),
        "fact_order_items": len(combined_tables["fact_order_items"]),
        "fact_payments": len(combined_tables["fact_payments"]),
        "bridge_order_promotions": len(combined_tables["bridge_order_promotions"]),
    }
    generator_config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=config.seed,
        discount_seed=config.seed,
        discount_variation=config.discount_variation,
        output_dir=output_dir,
        simulation_start=min(bucket.start_date for bucket in plan),
        simulation_end=max(bucket.end_date for bucket in plan),
        row_overrides=row_overrides,
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_parquet=config.export_parquet,
        export_sqlite=config.export_sqlite,
    )
    raw_tables, raw_relations = build_retail_schema(generator_config)
    return SchemaBuilder(generator_config).build(raw_tables, raw_relations)


def apply_dq_to_tables(
    tables: dict[str, pd.DataFrame],
    graph: SchemaGraph,
    *,
    dq_config: DataQualityConfig,
    rng: np.random.Generator,
    tables_to_process: set[str] | None = None,
) -> dict[str, pd.DataFrame]:
    table_lookup = {table.name: table for table in graph.tables}
    exported: dict[str, pd.DataFrame] = {}
    for table_name, df in tables.items():
        if tables_to_process is not None and table_name not in tables_to_process:
            exported[table_name] = df.copy(deep=True)
            continue
        table = table_lookup[table_name]
        unique_state = {
            column.name: set(df[column.name].dropna().tolist())
            for column in table.columns
            if column.unique or column.name == table.pk_column
        }
        exported[table_name] = apply_data_quality(
            df, table, dq_config, rng, unique_state
        )
    return exported


def merge_resume_and_new_tables(
    resume_tables: dict[str, pd.DataFrame],
    new_tables: dict[str, pd.DataFrame],
    as_of_date: date,
) -> dict[str, pd.DataFrame]:
    combined = {
        "dim_products": resume_tables["dim_products"].copy(deep=True),
        "dim_stores": resume_tables["dim_stores"].copy(deep=True),
        "dim_date": concat_frames([resume_tables["dim_date"], new_tables["dim_date"]])
        .drop_duplicates(subset=["date_id"])
        .sort_values("date_id")
        .reset_index(drop=True),
        "dim_promotions": concat_frames(
            [resume_tables["dim_promotions"], new_tables["dim_promotions"]]
        )
        .drop_duplicates(subset=["promo_id"])
        .reset_index(drop=True),
        "fact_orders": concat_frames(
            [resume_tables["fact_orders"], new_tables["fact_orders"]]
        ).reset_index(drop=True),
        "fact_order_items": concat_frames(
            [resume_tables["fact_order_items"], new_tables["fact_order_items"]]
        ).reset_index(drop=True),
        "fact_payments": concat_frames(
            [resume_tables["fact_payments"], new_tables["fact_payments"]]
        ).reset_index(drop=True),
        "bridge_order_promotions": concat_frames(
            [
                resume_tables["bridge_order_promotions"],
                new_tables["bridge_order_promotions"],
            ]
        ).reset_index(drop=True),
    }
    combined["dim_customers"] = refresh_customer_metrics(
        resume_tables["dim_customers"].copy(deep=True),
        combined["fact_orders"],
        as_of_date,
    )
    return combined


def load_resume_tables(path: Path | None) -> dict[str, pd.DataFrame] | None:
    if path is None:
        return None
    combined_path = (
        path / "combined"
        if path.name != "combined" and (path / "combined").exists()
        else path
    )
    table_names = [
        "dim_customers",
        "dim_products",
        "dim_stores",
        "dim_date",
        "dim_promotions",
        "fact_orders",
        "fact_order_items",
        "fact_payments",
        "bridge_order_promotions",
    ]
    return {name: pd.read_csv(combined_path / f"{name}.csv") for name in table_names}


def validate_resume_range(
    resume_tables: dict[str, pd.DataFrame], new_start_date: date
) -> None:
    existing_max = pd.to_datetime(
        resume_tables["fact_orders"]["created_at"], errors="coerce"
    ).max()
    if pd.isna(existing_max):
        return
    if new_start_date <= existing_max.date():
        raise ValueError(
            f"resume_from contains data through {existing_max.date().isoformat()}, "
            f"so start_date must be later than that."
        )


def write_combined_bundle(
    config: MonthlySalesConfig,
    graph: SchemaGraph,
    tables: dict[str, pd.DataFrame],
    output_dir: Path,
    *,
    flat_df: pd.DataFrame | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    generator_config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=config.seed,
        discount_seed=config.seed,
        discount_variation=config.discount_variation,
        output_dir=output_dir,
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_parquet=config.export_parquet,
        export_sqlite=config.export_sqlite,
    )
    csv_exporter = CsvExporter(generator_config)
    for table in graph.topological_order():
        csv_exporter.export_table(table, iter([tables[table.name]]))
    if config.include_flat:
        flat = flat_df if flat_df is not None else build_flat_extract(tables)
        flat.to_csv(output_dir / "monthly_sales_flat.csv", index=False)
    if config.export_parquet:
        parquet_exporter = ParquetExporter(generator_config)
        for table in graph.topological_order():
            parquet_exporter.export_table(table, iter([tables[table.name]]))
    sql_exporter = SqlExporter(generator_config)
    sql_exporter.export(graph)
    write_data_dictionary(graph, generator_config)
    write_erd(graph, generator_config)
    if config.export_sqlite:
        sqlite_exporter = SqliteExporter(generator_config)
        sqlite_exporter.export(
            graph,
            [
                (table, iter([tables[table.name]]))
                for table in graph.topological_order()
            ],
            db_name="retail",
        )
    return output_dir


def write_monthly_bundles(
    config: MonthlySalesConfig,
    tables: dict[str, pd.DataFrame],
    graph: SchemaGraph,
    months_root: Path,
    *,
    audit_bad_data: MonthlySalesBadDataProfile | None = None,
) -> None:
    order_dates = pd.to_datetime(tables["fact_orders"]["created_at"], errors="coerce")
    month_labels = order_dates.dt.strftime("%Y-%m").dropna().unique().tolist()
    for month_index, label in enumerate(sorted(month_labels)):
        month_tables = subset_month_tables(tables, label)
        output_dir = months_root / label
        generator_config = GeneratorConfig(
            scenario=Scenario.RETAIL,
            schema_type=SchemaType.STAR,
            dialect=Dialect.POSTGRES,
            seed=config.seed,
            discount_seed=config.seed,
            discount_variation=config.discount_variation,
            output_dir=output_dir,
            data_quality=DataQualityConfig(level=DataQuality.NONE),
        )
        csv_exporter = CsvExporter(generator_config)
        for table in graph.topological_order():
            csv_exporter.export_table(table, iter([month_tables[table.name]]))
        if config.include_flat:
            flat = build_flat_extract(month_tables)
            if audit_bad_data is not None and audit_bad_data.enabled:
                flat, _ = apply_flat_audit_bad_data(
                    flat,
                    audit_bad_data,
                    np.random.default_rng(config.seed + 800 + month_index),
                )
            flat.to_csv(output_dir / "monthly_sales_flat.csv", index=False)


def export_dimension_snapshot(
    dimension_tables: dict[str, pd.DataFrame], output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for table_name in DIMENSION_TABLE_NAMES:
        target = output_dir / f"{table_name}.csv"
        if target.exists():
            continue
        dimension_tables[table_name].to_csv(target, index=False)


def write_sales_files_bundle(
    config: MonthlySalesConfig,
    tables: dict[str, pd.DataFrame],
    output_dir: Path,
    *,
    dimension_tables: dict[str, pd.DataFrame],
    audit_bad_data: MonthlySalesBadDataProfile | None = None,
) -> dict[str, int]:
    export_dimension_snapshot(dimension_tables, output_dir)
    sales_file_counts: dict[str, int] = {}
    order_dates = pd.to_datetime(tables["fact_orders"]["created_at"], errors="coerce")
    month_labels = sorted(order_dates.dt.strftime("%Y-%m").dropna().unique().tolist())
    for month_index, label in enumerate(month_labels):
        month_tables = subset_month_tables(tables, label)
        flat = build_flat_extract(month_tables)
        if audit_bad_data is not None and audit_bad_data.enabled:
            flat, _ = apply_flat_audit_bad_data(
                flat,
                audit_bad_data,
                np.random.default_rng(config.seed + 900 + month_index),
            )
        filename = month_label_to_sales_filename(label)
        target = output_dir / filename
        if target.exists():
            raise ValueError(f"sales file already exists for {label}: {target}")
        flat.to_csv(target, index=False)
        sales_file_counts[filename] = int(len(flat))
    return sales_file_counts


def subset_month_tables(
    tables: dict[str, pd.DataFrame], month_label: str
) -> dict[str, pd.DataFrame]:
    orders = tables["fact_orders"].copy(deep=True)
    order_month = pd.to_datetime(orders["created_at"], errors="coerce").dt.strftime(
        "%Y-%m"
    )
    order_mask = order_month.eq(month_label)
    month_orders = orders.loc[order_mask].reset_index(drop=True)
    order_ids = set(month_orders["order_id"].tolist())
    month_items = (
        tables["fact_order_items"]
        .loc[tables["fact_order_items"]["order_id"].isin(order_ids)]
        .reset_index(drop=True)
    )
    month_payments = (
        tables["fact_payments"]
        .loc[tables["fact_payments"]["order_id"].isin(order_ids)]
        .reset_index(drop=True)
    )
    month_bridge = (
        tables["bridge_order_promotions"]
        .loc[tables["bridge_order_promotions"]["order_id"].isin(order_ids)]
        .reset_index(drop=True)
    )
    customer_ids = set(month_orders["customer_id"].tolist())
    store_ids = set(month_orders["store_id"].tolist())
    product_ids = set(month_items["product_id"].tolist())
    promo_ids = set(month_bridge["promo_id"].tolist())
    date_ids = set(month_orders["date_id"].tolist())
    return {
        "dim_customers": tables["dim_customers"]
        .loc[tables["dim_customers"]["customer_id"].isin(customer_ids)]
        .reset_index(drop=True),
        "dim_products": tables["dim_products"]
        .loc[tables["dim_products"]["product_id"].isin(product_ids)]
        .reset_index(drop=True),
        "dim_stores": tables["dim_stores"]
        .loc[tables["dim_stores"]["store_id"].isin(store_ids)]
        .reset_index(drop=True),
        "dim_date": tables["dim_date"]
        .loc[tables["dim_date"]["date_id"].isin(date_ids)]
        .reset_index(drop=True),
        "dim_promotions": tables["dim_promotions"]
        .loc[tables["dim_promotions"]["promo_id"].isin(promo_ids)]
        .reset_index(drop=True),
        "fact_orders": month_orders,
        "fact_order_items": month_items,
        "fact_payments": month_payments,
        "bridge_order_promotions": month_bridge,
    }


def build_flat_extract(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders = tables["fact_orders"][
        [
            "order_id",
            "customer_id",
            "created_at",
            "subtotal",
            "discount_amt",
            "shipping_amt",
            "order_total",
            "channel",
        ]
    ].copy()
    items = tables["fact_order_items"].copy()
    products = tables["dim_products"][["product_id", "subcategory"]].copy()
    merged = items.merge(orders, on="order_id", how="left").merge(
        products, on="product_id", how="left"
    )
    merged["share"] = np.where(
        merged["subtotal"] > 0, merged["line_total"] / merged["subtotal"], 0.0
    )
    merged["allocated_discount"] = merged["discount_amt"] * merged["share"]
    merged["allocated_shipping"] = merged["shipping_amt"] * merged["share"]
    merged["OrderValue"] = (
        merged["line_total"]
        - merged["allocated_discount"]
        + merged["allocated_shipping"]
    ).round(2)
    order_dates = pd.to_datetime(merged["created_at"], errors="coerce")
    merged["OrderDate"] = order_dates.apply(
        lambda ts: f"{ts.month}/{ts.day}/{ts.year}" if pd.notna(ts) else ""
    )
    order_targets = orders.set_index("order_id")["order_total"].to_dict()
    flat = pd.DataFrame(
        {
            "OrderID": merged["order_id"],
            "CustomerID": merged["customer_id"],
            "OrderDate": merged["OrderDate"],
            "ProductType": merged["subcategory"],
            "OrderValue": merged["OrderValue"],
            "OrderItemID": merged["item_id"],
            "ProductID": merged["product_id"],
            "Quantity": merged["qty"],
            "UnitPrice": merged["unit_price"],
            "Channel": merged["channel"],
        }
    )
    return reconcile_flat_order_values(flat, order_targets)


def reconcile_flat_order_values(
    flat: pd.DataFrame, order_targets: dict[str, float]
) -> pd.DataFrame:
    if flat.empty:
        return flat
    reconciled = flat.copy(deep=True)
    for order_id, target in order_targets.items():
        mask = reconciled["OrderID"].eq(order_id)
        rows = reconciled.loc[mask]
        difference = round(target - rows["OrderValue"].sum(), 2)
        if abs(difference) > 0 and not rows.empty:
            idx = rows.index[-1]
            reconciled.at[idx, "OrderValue"] = round(
                float(reconciled.at[idx, "OrderValue"]) + difference, 2
            )
    return reconciled


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        for frame in frames:
            if frame is not None:
                return frame.copy(deep=True)
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)


def write_manifest(
    config: MonthlySalesConfig,
    plan: list[MonthBucket],
    tables: dict[str, pd.DataFrame],
    outputs: dict[str, Path],
    *,
    flat_for_manifest: pd.DataFrame | None = None,
    defect_summary: dict[str, object] | None = None,
    dimension_tables_for_manifest: dict[str, pd.DataFrame] | None = None,
    sales_file_counts: dict[str, int] | None = None,
    dimension_source: Path | None = None,
) -> None:
    if config.layout is MonthlyLayout.SALES_FILES:
        dimension_tables = dimension_tables_for_manifest or {}
        row_counts = {name: int(len(df)) for name, df in dimension_tables.items()}
    else:
        row_counts = {name: int(len(df)) for name, df in tables.items()}
        if flat_for_manifest is not None:
            row_counts["monthly_sales_flat"] = int(len(flat_for_manifest))
    payload = {
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "orders_per_month": config.orders_per_month,
        "max_orders_per_month": config.max_orders_per_month,
        "avg_items_per_order": config.avg_items_per_order,
        "layout": config.layout.value,
        "include_flat": config.include_flat,
        "resume_from": str(config.resume_from) if config.resume_from else None,
        "profile_config": str(config.profile_config) if config.profile_config else None,
        "seed": config.seed,
        "discount_variation": config.discount_variation,
        "data_quality": config.data_quality.value,
        "trend_mode": config.trend_mode.value
        if config.trend_mode is not None
        else None,
        "start_ratio": config.start_ratio,
        "seasonality_strength": config.seasonality_strength,
        "volatility_strength": config.volatility_strength,
        "months": [asdict(bucket) for bucket in plan],
        "row_counts": row_counts,
        "sales_files": list((sales_file_counts or {}).keys()),
        "sales_file_row_counts": sales_file_counts or {},
        "dimension_source": str(dimension_source)
        if dimension_source is not None
        else None,
        "defect_summary": defect_summary or {},
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    (config.output_dir / "manifest.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
