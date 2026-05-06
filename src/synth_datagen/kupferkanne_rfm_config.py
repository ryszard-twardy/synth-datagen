"""
YAML configuration models for the Kupferkanne RFM generator.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import Field, field_validator, model_validator
import yaml

from .config import StrictModel

KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS = [
    "first_name",
    "last_name",
    "email",
    "phone",
    "state",
    "city",
    "address",
]


class KupferkanneCompanyConfig(StrictModel):
    name: str
    headquarters: str
    markets: list[str]
    business_model: str
    annual_revenue_eur: float = Field(gt=0)


class KupferkannePeriodConfig(StrictModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_range(self) -> "KupferkannePeriodConfig":
        if self.start_date > self.end_date:
            raise ValueError("period.start_date must be <= period.end_date")
        return self


class KupferkanneOutputConfig(StrictModel):
    default_dir: Path = Path("./output/")
    dimensions_dirname: str = "dimensions"
    monthly_dirname: str = "monthly"
    orders_prefix: str = "orders20"
    items_prefix: str = "items20"
    docs_filename: str = "kupferkanne_rfm_schema.md"
    effective_config_filename: str = "effective_config.yaml"
    manifest_filename: str = "manifest.json"
    dim_customers_filename: str = "dim_customers.csv"
    dim_products_filename: str = "dim_products.csv"
    dim_customers_extra_columns: list[str] = Field(
        default_factory=lambda: KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS.copy()
    )

    @field_validator("default_dir", mode="before")
    @classmethod
    def coerce_path(cls, value: object) -> Path:
        return Path(value)

    @field_validator("dim_customers_extra_columns", mode="before")
    @classmethod
    def coerce_dim_customer_columns(cls, value: object) -> list[str]:
        if value is None:
            return KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS.copy()
        if not isinstance(value, list):
            raise TypeError("output.dim_customers_extra_columns must be a list")
        return [str(item) for item in value]

    @model_validator(mode="after")
    def validate_dim_customer_columns(self) -> "KupferkanneOutputConfig":
        duplicates = sorted(
            {
                column
                for column in self.dim_customers_extra_columns
                if self.dim_customers_extra_columns.count(column) > 1
            }
        )
        if duplicates:
            raise ValueError(
                f"output.dim_customers_extra_columns contains duplicates: {duplicates}"
            )
        unknown = sorted(
            set(self.dim_customers_extra_columns)
            - set(KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS)
        )
        if unknown:
            raise ValueError(
                f"output.dim_customers_extra_columns contains unknown columns: {unknown}"
            )
        return self


class KupferkanneProductConfig(StrictModel):
    product_id: str
    product_name: str
    category: str
    retail_price: float = Field(gt=0)
    unit_cost: float = Field(gt=0)
    base_weight: float = Field(default=1.0, gt=0)
    tags: list[str] = Field(default_factory=list)


class KupferkanneCatalogConfig(StrictModel):
    category_order_shares: dict[str, float]
    products: list[KupferkanneProductConfig]

    @field_validator("category_order_shares", mode="before")
    @classmethod
    def coerce_category_shares(cls, value: object) -> dict[str, float]:
        if not isinstance(value, dict):
            raise TypeError("catalog.category_order_shares must be a mapping")
        return {str(key): float(val) for key, val in value.items()}

    @model_validator(mode="after")
    def validate_catalog(self) -> "KupferkanneCatalogConfig":
        if len(self.products) != 60:
            raise ValueError(
                f"catalog.products must contain exactly 60 products, found {len(self.products)}"
            )
        total_share = sum(self.category_order_shares.values())
        if abs(total_share - 1.0) > 1e-6:
            raise ValueError(
                f"catalog.category_order_shares must sum to 1.0, got {total_share:.6f}"
            )
        product_ids = [product.product_id for product in self.products]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("catalog.products must use unique product_id values")
        product_categories = {product.category for product in self.products}
        unknown_categories = sorted(
            set(self.category_order_shares) - product_categories
        )
        if unknown_categories:
            raise ValueError(
                f"catalog.category_order_shares contains unknown categories: {unknown_categories}"
            )
        return self


class KupferkanneAcquisitionPhaseConfig(StrictModel):
    start_month: str
    end_month: str
    monthly_new_customers: int = Field(gt=0)


class KupferkanneCustomersConfig(StrictModel):
    target_total_customers: int = Field(gt=0)
    prelaunch_seed_customers: int = Field(default=0, ge=0)
    acquisition_phases: list[KupferkanneAcquisitionPhaseConfig]

    @model_validator(mode="after")
    def validate_target(self) -> "KupferkanneCustomersConfig":
        if self.prelaunch_seed_customers >= self.target_total_customers:
            raise ValueError(
                "customers.prelaunch_seed_customers must be smaller than target_total_customers"
            )
        return self


class KupferkanneArchetypeConfig(StrictModel):
    name: str
    share: float = Field(gt=0, le=1)
    existing_order_weight: float = Field(default=1.0, ge=0)
    same_month_repeat_weight: float = Field(default=0.5, ge=0)
    max_orders_per_month: int = Field(default=3, ge=1)
    holiday_multiplier: float = Field(default=1.0, ge=0)
    q1_multiplier: float = Field(default=1.0, ge=0)
    summer_multiplier: float = Field(default=1.0, ge=0)
    active_months_after_signup: int | None = Field(default=None, ge=1)
    churn_after_months_min: int | None = Field(default=None, ge=1)
    churn_after_months_max: int | None = Field(default=None, ge=1)
    category_affinity: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_churn_window(self) -> "KupferkanneArchetypeConfig":
        if (
            self.churn_after_months_min is None
            and self.churn_after_months_max is not None
        ):
            raise ValueError(
                f"{self.name}: churn_after_months_min is required when churn_after_months_max is set"
            )
        if (
            self.churn_after_months_min is not None
            and self.churn_after_months_max is None
        ):
            raise ValueError(
                f"{self.name}: churn_after_months_max is required when churn_after_months_min is set"
            )
        if (
            self.churn_after_months_min is not None
            and self.churn_after_months_max is not None
            and self.churn_after_months_min > self.churn_after_months_max
        ):
            raise ValueError(
                f"{self.name}: churn_after_months_min must be <= churn_after_months_max"
            )
        return self


class KupferkanneCountryConfig(StrictModel):
    code: str
    share: float = Field(gt=0, le=1)


class KupferkanneSeasonalityConfig(StrictModel):
    monthly_order_baseline: dict[int, int]
    random_variance_pct: float = Field(default=0.10, ge=0, le=0.5)
    product_tag_multipliers: dict[str, dict[int, float]] = Field(default_factory=dict)

    @field_validator("monthly_order_baseline", mode="before")
    @classmethod
    def coerce_month_baselines(cls, value: object) -> dict[int, int]:
        if not isinstance(value, dict):
            raise TypeError("seasonality.monthly_order_baseline must be a mapping")
        return {int(key): int(val) for key, val in value.items()}

    @field_validator("product_tag_multipliers", mode="before")
    @classmethod
    def coerce_tag_months(cls, value: object) -> dict[str, dict[int, float]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("seasonality.product_tag_multipliers must be a mapping")
        normalized: dict[str, dict[int, float]] = {}
        for tag, months in value.items():
            if not isinstance(months, dict):
                raise TypeError(
                    f"seasonality.product_tag_multipliers.{tag} must be a mapping"
                )
            normalized[str(tag)] = {
                int(month): float(multiplier) for month, multiplier in months.items()
            }
        return normalized

    @model_validator(mode="after")
    def validate_months(self) -> "KupferkanneSeasonalityConfig":
        missing = [
            month for month in range(1, 13) if month not in self.monthly_order_baseline
        ]
        if missing:
            raise ValueError(
                f"seasonality.monthly_order_baseline is missing months: {missing}"
            )
        return self


class KupferkanneGrowthConfig(StrictModel):
    year_multipliers: dict[int, float]

    @field_validator("year_multipliers", mode="before")
    @classmethod
    def coerce_years(cls, value: object) -> dict[int, float]:
        if not isinstance(value, dict):
            raise TypeError("growth.year_multipliers must be a mapping")
        return {int(key): float(val) for key, val in value.items()}


class KupferkanneDiscountScenarioConfig(StrictModel):
    name: str
    share: float = Field(gt=0, le=1)
    discount_min: float = Field(ge=0, le=1)
    discount_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_range(self) -> "KupferkanneDiscountScenarioConfig":
        if self.discount_min > self.discount_max:
            raise ValueError(f"{self.name}: discount_min must be <= discount_max")
        return self


class KupferkanneDiscountsConfig(StrictModel):
    scenarios: list[KupferkanneDiscountScenarioConfig]
    seasonal_windows: list[dict[str, str]] = Field(default_factory=list)
    clearance_months: list[int] = Field(default_factory=lambda: [1, 7])
    loyalty_min_prior_orders: int = Field(default=5, ge=1)


class KupferkanneBasketAffinityRuleConfig(StrictModel):
    product_weights: dict[str, float] = Field(default_factory=dict)
    category_weights: dict[str, float] = Field(default_factory=dict)
    single_item_override_probability: float = Field(default=0.0, ge=0, le=1)
    max_distinct_cap: int | None = Field(default=None, ge=1)

    @field_validator("product_weights", "category_weights", mode="before")
    @classmethod
    def coerce_weights(cls, value: object) -> dict[str, float]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("affinity weights must be a mapping")
        return {str(key): float(val) for key, val in value.items()}


class KupferkanneBasketingConfig(StrictModel):
    max_distinct_products_per_order: int = Field(default=5, ge=1)
    initial_size_distribution: dict[int, float]
    affinity_rules: dict[str, KupferkanneBasketAffinityRuleConfig] = Field(
        default_factory=dict
    )

    @field_validator("initial_size_distribution", mode="before")
    @classmethod
    def coerce_size_distribution(cls, value: object) -> dict[int, float]:
        if not isinstance(value, dict):
            raise TypeError("basketing.initial_size_distribution must be a mapping")
        return {int(key): float(val) for key, val in value.items()}

    @model_validator(mode="after")
    def validate_distribution(self) -> "KupferkanneBasketingConfig":
        total = sum(self.initial_size_distribution.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"basketing.initial_size_distribution must sum to 1.0, got {total:.6f}"
            )
        invalid_counts = [
            count
            for count in self.initial_size_distribution
            if count < 1 or count > self.max_distinct_products_per_order
        ]
        if invalid_counts:
            raise ValueError(
                f"basketing.initial_size_distribution contains invalid counts: {sorted(invalid_counts)}"
            )
        return self


class KupferkanneDataQualityConfig(StrictModel):
    enabled: bool = True
    null_customer_id_rate: float = Field(default=0.0015, ge=0, le=1)
    null_order_date_rate: float = Field(default=0.0008, ge=0, le=1)
    malformed_date_rate: float = Field(default=0.0005, ge=0, le=1)
    future_date_rate: float = Field(default=0.0002, ge=0, le=1)
    negative_line_net_amount_rate: float = Field(default=0.0012, ge=0, le=1)
    zero_line_net_amount_rate: float = Field(default=0.0005, ge=0, le=1)
    cents_line_net_amount_rate: float = Field(default=0.0008, ge=0, le=1)
    whitespace_id_rate: float = Field(default=0.0015, ge=0, le=1)
    duplicate_row_rate: float = Field(default=0.0012, ge=0, le=1)
    null_line_net_amount_rate: float = Field(default=0.0008, ge=0, le=1)
    cents_window_start: date
    cents_window_end: date
    malformed_date_month: str
    future_date_anchor_years: list[int]
    duplicate_boundary_days: int = Field(default=2, ge=1)

    def target_dirty_rate(self) -> float:
        return (
            self.null_customer_id_rate
            + self.null_order_date_rate
            + self.malformed_date_rate
            + self.future_date_rate
            + self.negative_line_net_amount_rate
            + self.zero_line_net_amount_rate
            + self.cents_line_net_amount_rate
            + self.whitespace_id_rate
            + self.duplicate_row_rate
            + self.null_line_net_amount_rate
        )


class KupferkanneValidationTargetsConfig(StrictModel):
    target_total_orders: int = Field(gt=0)
    unique_orders_min: int = Field(gt=0)
    unique_orders_max: int = Field(gt=0)
    total_rows_min: int = Field(gt=0)
    total_rows_max: int = Field(gt=0)
    unique_customers_target: int = Field(gt=0)
    unique_customers_tolerance: int = Field(default=600, ge=0)
    avg_lines_per_order_min: float = Field(gt=0)
    avg_lines_per_order_max: float = Field(gt=0)
    single_item_share_target: float = Field(gt=0, le=1)
    single_item_share_tolerance: float = Field(default=0.04, ge=0, le=1)
    five_plus_max_share: float = Field(gt=0, le=1)
    dirty_rate_target: float = Field(gt=0, le=1)
    dirty_rate_tolerance: float = Field(default=0.0015, ge=0, le=1)
    corporate_order_share_max: float = Field(default=0.005, gt=0, le=1)

    @model_validator(mode="after")
    def validate_ranges(self) -> "KupferkanneValidationTargetsConfig":
        if self.unique_orders_min > self.unique_orders_max:
            raise ValueError(
                "validation_targets.unique_orders_min must be <= unique_orders_max"
            )
        if self.total_rows_min > self.total_rows_max:
            raise ValueError(
                "validation_targets.total_rows_min must be <= total_rows_max"
            )
        if self.avg_lines_per_order_min > self.avg_lines_per_order_max:
            raise ValueError(
                "validation_targets.avg_lines_per_order_min must be <= avg_lines_per_order_max"
            )
        if not (
            self.unique_orders_min <= self.target_total_orders <= self.unique_orders_max
        ):
            raise ValueError(
                "validation_targets.target_total_orders must sit inside unique_orders_min/max"
            )
        return self


class KupferkanneRfmConfig(StrictModel):
    company: KupferkanneCompanyConfig
    period: KupferkannePeriodConfig
    output: KupferkanneOutputConfig = Field(default_factory=KupferkanneOutputConfig)
    catalog: KupferkanneCatalogConfig
    customers: KupferkanneCustomersConfig
    archetypes: list[KupferkanneArchetypeConfig]
    basketing: KupferkanneBasketingConfig
    seasonality: KupferkanneSeasonalityConfig
    growth: KupferkanneGrowthConfig
    discounts: KupferkanneDiscountsConfig
    countries: list[KupferkanneCountryConfig]
    data_quality: KupferkanneDataQualityConfig
    validation_targets: KupferkanneValidationTargetsConfig

    @model_validator(mode="after")
    def validate_weights(self) -> "KupferkanneRfmConfig":
        archetype_share = sum(item.share for item in self.archetypes)
        if abs(archetype_share - 1.0) > 1e-6:
            raise ValueError(
                f"archetypes shares must sum to 1.0, got {archetype_share:.6f}"
            )
        country_share = sum(item.share for item in self.countries)
        if abs(country_share - 1.0) > 1e-6:
            raise ValueError(
                f"countries shares must sum to 1.0, got {country_share:.6f}"
            )
        discount_share = sum(item.share for item in self.discounts.scenarios)
        if abs(discount_share - 1.0) > 1e-6:
            raise ValueError(
                f"discount scenario shares must sum to 1.0, got {discount_share:.6f}"
            )
        category_names = {product.category for product in self.catalog.products}
        for archetype in self.archetypes:
            unknown = sorted(set(archetype.category_affinity) - category_names)
            if unknown:
                raise ValueError(
                    f"{archetype.name}: unknown category_affinity keys: {unknown}"
                )
        unknown_affinity_sources = sorted(
            set(self.basketing.affinity_rules) - category_names
        )
        if unknown_affinity_sources:
            raise ValueError(
                f"basketing.affinity_rules contains unknown source categories: {unknown_affinity_sources}"
            )
        unknown_affinity_targets = sorted(
            {
                category_name
                for rule in self.basketing.affinity_rules.values()
                for category_name in rule.category_weights
                if category_name not in category_names
            }
        )
        if unknown_affinity_targets:
            raise ValueError(
                f"basketing.affinity_rules contains unknown target categories: {unknown_affinity_targets}"
            )
        known_products = {product.product_id for product in self.catalog.products}
        unknown_product_ids = sorted(
            {
                product_id
                for rule in self.basketing.affinity_rules.values()
                for product_id in rule.product_weights
                if product_id not in known_products
            }
        )
        if unknown_product_ids:
            raise ValueError(
                f"basketing.affinity_rules contains unknown product_ids: {unknown_product_ids}"
            )
        return self

    def dump(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def load_kupferkanne_rfm_config(path: Path | str) -> KupferkanneRfmConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return KupferkanneRfmConfig.model_validate(data)


def write_effective_kupferkanne_config(
    config: KupferkanneRfmConfig, path: Path
) -> None:
    path.write_text(
        yaml.safe_dump(config.dump(), sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
