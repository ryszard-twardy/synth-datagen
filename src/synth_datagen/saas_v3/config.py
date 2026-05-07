"""
YAML-driven configuration models for the SaaS synthetic engine v3.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from pathlib import Path
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import yaml


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutputMode(str, Enum):
    CLEAN = "clean"
    DIRTY = "dirty"
    BOTH = "both"


class OutputFormat(str, Enum):
    CSV = "csv"
    PARQUET = "parquet"
    BIGQUERY_SCHEMA = "bigquery_schema"


class RunConfig(StrictModel):
    name: str
    seed: int = Field(ge=0)
    schema_version: str = "saas_v3"
    # v0.2.1: 'legacy' = pre-extension behavior (byte-stable for existing configs).
    # 'plg-usage-based' = new sub-mode emitting subscription_events + benchmarks.
    # 'vertical-account-based' deferred to v0.3.0.
    mode: Literal["legacy", "plg-usage-based"] = "legacy"


class HistoryConfig(StrictModel):
    as_of_date: date
    lookback_years: float = Field(gt=0)

    @property
    def start_date(self) -> date:
        return self.as_of_date - timedelta(days=round(self.lookback_years * 365))


class RowTargets(StrictModel):
    accounts: int = Field(gt=0)
    users: int = Field(gt=0)
    subscriptions: int = Field(gt=0)
    product_events: int = Field(gt=0)
    invoices: int = Field(gt=0)
    support_tickets: int = Field(gt=0)
    nps_responses: int = Field(gt=0)

    def as_dict(self) -> dict[str, int]:
        return self.model_dump()


class PlanConfig(StrictModel):
    name: str
    monthly_price: float = Field(gt=0)
    probability: float = Field(gt=0)
    usage_multiplier: float = Field(default=1.0, gt=0)
    support_complexity: float = Field(default=1.0, gt=0)
    min_feature_depth: float = Field(default=0.5, gt=0)


class SizeSegmentConfig(StrictModel):
    name: str
    weight: float = Field(gt=0)
    user_count_min: int = Field(ge=1)
    user_count_max: int = Field(ge=1)
    event_multiplier: float = Field(default=1.0, gt=0)
    support_multiplier: float = Field(default=1.0, gt=0)
    plan_bias: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_range(self) -> "SizeSegmentConfig":
        if self.user_count_min > self.user_count_max:
            raise ValueError("user_count_min must be <= user_count_max")
        return self


class CountryConfig(StrictModel):
    name: str
    weight: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    timezone: str
    utc_offset_hours: int
    company_suffixes: list[str] = Field(default_factory=list)
    domain_tlds: list[str] = Field(default_factory=list)
    locale: str | None = None


class IndustryConfig(StrictModel):
    name: str
    weight: float = Field(gt=0)
    adoption_factor: float = Field(default=1.0, gt=0)
    support_factor: float = Field(default=1.0, gt=0)
    plan_bias: dict[str, float] = Field(default_factory=dict)
    nps_bias: float = 0.0


class AcquisitionChannelConfig(StrictModel):
    name: str
    weight: float = Field(gt=0)
    retention_adjustment: float = 0.0
    expansion_adjustment: float = 0.0
    nps_adjustment: float = 0.0


class RoleConfig(StrictModel):
    name: str
    weight: float = Field(gt=0)
    activity_multiplier: float = Field(default=1.0, gt=0)
    login_half_life_days: int = Field(default=21, ge=1)


class EventTypeConfig(StrictModel):
    name: str
    weight: float = Field(gt=0)
    feature_category: str
    platform_weights: dict[str, float]
    min_plan: str | None = None


class LifecycleConfig(StrictModel):
    new_account_months: int = Field(default=2, ge=1)
    minimum_tenure_days_before_churn: int = Field(default=90, ge=1)
    churn_base_probability: float = Field(default=0.16, ge=0, le=1)
    expansion_base_probability: float = Field(default=0.34, ge=0, le=1)
    contraction_base_probability: float = Field(default=0.12, ge=0, le=1)
    incident_burst_probability: float = Field(default=0.08, ge=0, le=1)
    seasonal_strength: float = Field(default=0.12, ge=0, le=1)


class BillingConfig(StrictModel):
    billing_period_weights: dict[str, float]
    paid_probability: float = Field(default=0.84, ge=0, le=1)
    partial_payment_probability: float = Field(default=0.07, ge=0, le=1)
    overdue_probability: float = Field(default=0.07, ge=0, le=1)
    void_probability: float = Field(default=0.02, ge=0, le=1)

    @model_validator(mode="after")
    def validate_probabilities(self) -> "BillingConfig":
        total = (
            self.paid_probability
            + self.partial_payment_probability
            + self.overdue_probability
            + self.void_probability
        )
        if total > 1.000001:
            raise ValueError("Billing status probabilities must sum to <= 1.0")
        return self


class DefectRateConfig(StrictModel):
    enabled: bool = True
    rate: float = Field(ge=0, le=1)


class DefectsConfig(StrictModel):
    null_company_names: DefectRateConfig
    case_duplicate_emails: DefectRateConfig
    pre_signup_logins: DefectRateConfig
    plan_name_typos: DefectRateConfig
    negative_monthly_amounts: DefectRateConfig
    reversed_subscription_dates: DefectRateConfig
    orphaned_product_events: DefectRateConfig
    future_timestamps: DefectRateConfig
    bad_date_formats: DefectRateConfig
    mixed_invoice_amount_formats: DefectRateConfig
    out_of_range_nps_scores: DefectRateConfig

    def active_rates(self) -> dict[str, float]:
        return {
            name: cfg["rate"]
            for name, cfg in self.model_dump().items()
            if cfg["enabled"]
        }


class OutputConfig(StrictModel):
    root_dir: Path
    formats: list[OutputFormat] = Field(default_factory=lambda: [OutputFormat.CSV])
    chunk_rows: int = Field(default=100_000, gt=0)
    write_effective_config: bool = True

    @field_validator("root_dir", mode="before")
    @classmethod
    def coerce_path(cls, value: Any) -> Path:
        return Path(value)


class ValidationConfig(StrictModel):
    row_count_tolerance: dict[str, float] = Field(default_factory=dict)
    defect_tolerance: float = Field(default=0.20, ge=0, le=1)
    local_hour_min: int = Field(default=6, ge=0, le=23)
    local_hour_max: int = Field(default=22, ge=0, le=23)

    @model_validator(mode="after")
    def validate_hour_range(self) -> "ValidationConfig":
        if self.local_hour_min > self.local_hour_max:
            raise ValueError("local_hour_min must be <= local_hour_max")
        return self


class BenchmarkConfig(StrictModel):
    """Industry benchmark target ranges (KeyBanc 2024 / Benchmarkit 2025).

    Used by validate.compute_benchmarks() when run.mode == 'plg-usage-based'.
    Skipped silently in legacy mode.
    """

    target_nrr_min: float = Field(default=1.05, gt=0)
    target_nrr_max: float = Field(default=1.35, gt=0)
    target_grr_min: float = Field(default=0.85, gt=0, le=1.0)
    lifetime_churn_max: float = Field(default=0.40, gt=0, le=1.0)
    trial_conversion_min: float = Field(default=0.15, ge=0, le=1.0)
    trial_conversion_max: float = Field(default=0.40, gt=0, le=1.0)


class SaaSV3Config(StrictModel):
    run: RunConfig
    history: HistoryConfig
    row_targets: RowTargets
    plans: list[PlanConfig]
    company_sizes: list[SizeSegmentConfig]
    countries: list[CountryConfig]
    industries: list[IndustryConfig]
    acquisition_channels: list[AcquisitionChannelConfig]
    role_mix: list[RoleConfig]
    event_taxonomy: list[EventTypeConfig]
    lifecycle: LifecycleConfig
    billing: BillingConfig
    benchmarks: BenchmarkConfig = Field(default_factory=BenchmarkConfig)
    defects: DefectsConfig
    output: OutputConfig
    validation: ValidationConfig = Field(default_factory=ValidationConfig)

    @model_validator(mode="after")
    def validate_lists(self) -> "SaaSV3Config":
        if len({plan.name for plan in self.plans}) != len(self.plans):
            raise ValueError("Plan names must be unique")
        if len({seg.name for seg in self.company_sizes}) != len(self.company_sizes):
            raise ValueError("Company size names must be unique")
        if len({country.name for country in self.countries}) != len(self.countries):
            raise ValueError("Country names must be unique")
        if len({industry.name for industry in self.industries}) != len(self.industries):
            raise ValueError("Industry names must be unique")
        if len({channel.name for channel in self.acquisition_channels}) != len(
            self.acquisition_channels
        ):
            raise ValueError("Acquisition channel names must be unique")
        if len({role.name for role in self.role_mix}) != len(self.role_mix):
            raise ValueError("Role names must be unique")
        if len({event.name for event in self.event_taxonomy}) != len(
            self.event_taxonomy
        ):
            raise ValueError("Event taxonomy names must be unique")
        plan_names = {plan.name for plan in self.plans}
        for segment in self.company_sizes:
            unknown = set(segment.plan_bias) - plan_names
            if unknown:
                raise ValueError(
                    f"Unknown plan names in company_sizes.plan_bias: {sorted(unknown)}"
                )
        for industry in self.industries:
            unknown = set(industry.plan_bias) - plan_names
            if unknown:
                raise ValueError(
                    f"Unknown plan names in industries.plan_bias: {sorted(unknown)}"
                )
        for event in self.event_taxonomy:
            if event.min_plan and event.min_plan not in plan_names:
                raise ValueError(f"Unknown event_taxonomy.min_plan '{event.min_plan}'")
        supported_periods = {"monthly", "quarterly", "annual"}
        if set(self.billing.billing_period_weights) - supported_periods:
            raise ValueError(
                "billing_period_weights only supports monthly, quarterly, and annual"
            )
        if self.row_targets.subscriptions < 1:
            raise ValueError("At least one subscription row is required")
        return self

    @property
    def history_start(self) -> date:
        return self.history.start_date

    @property
    def plan_names(self) -> list[str]:
        return [plan.name for plan in self.plans]

    @property
    def row_target_map(self) -> dict[str, int]:
        return self.row_targets.as_dict()

    def config_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode(
            "utf-8"
        )
        return hashlib.sha256(payload).hexdigest()[:16]


def load_config(path: Path | str) -> SaaSV3Config:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return SaaSV3Config.model_validate(data)


def dump_config(config: SaaSV3Config) -> str:
    return yaml.safe_dump(
        config.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=False,
    )
