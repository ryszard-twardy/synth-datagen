"""
YAML profile models for monthly retail sales generation.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path

from pydantic import Field, model_validator
import yaml

from .config import StrictModel


class MonthlyTrendMode(str, Enum):
    GROWTH = "growth"


class MonthlySalesPeriodProfile(StrictModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_range(self) -> "MonthlySalesPeriodProfile":
        if self.start_date > self.end_date:
            raise ValueError("period.start_date must be <= period.end_date")
        return self


class MonthlySalesVolumeProfile(StrictModel):
    max_orders_per_month: int = Field(gt=0)
    trend_mode: MonthlyTrendMode = MonthlyTrendMode.GROWTH
    start_ratio: float = Field(default=0.38, gt=0, le=1)
    seasonality_strength: float = Field(default=0.14, ge=0, le=1)
    volatility_strength: float = Field(default=0.08, ge=0, le=1)


class MonthlySalesNormalizedAuditProfile(StrictModel):
    null_required_rate: float = Field(default=0.0, ge=0, le=1)
    negative_numeric_rate: float = Field(default=0.0, ge=0, le=1)
    monetary_outlier_rate: float = Field(default=0.0, ge=0, le=1)


class MonthlySalesFlatAuditProfile(StrictModel):
    duplicate_orderid_rate: float = Field(default=0.0, ge=0, le=1)
    bad_orderdate_rate: float = Field(default=0.0, ge=0, le=1)
    mixed_ordervalue_format_rate: float = Field(default=0.0, ge=0, le=1)
    null_required_rate: float = Field(default=0.0, ge=0, le=1)
    negative_ordervalue_rate: float = Field(default=0.0, ge=0, le=1)


class MonthlySalesBadDataProfile(StrictModel):
    enabled: bool = False
    normalized: MonthlySalesNormalizedAuditProfile = Field(
        default_factory=MonthlySalesNormalizedAuditProfile
    )
    flat: MonthlySalesFlatAuditProfile = Field(
        default_factory=MonthlySalesFlatAuditProfile
    )

    def has_flat_defects(self) -> bool:
        return any(rate > 0 for rate in self.flat.model_dump().values())

    def has_normalized_defects(self) -> bool:
        return any(rate > 0 for rate in self.normalized.model_dump().values())


class MonthlySalesOutputProfile(StrictModel):
    layout: str = "both"
    include_flat: bool = True


class MonthlySalesProfile(StrictModel):
    period: MonthlySalesPeriodProfile
    volume: MonthlySalesVolumeProfile
    bad_data: MonthlySalesBadDataProfile = Field(
        default_factory=MonthlySalesBadDataProfile
    )
    output: MonthlySalesOutputProfile = Field(default_factory=MonthlySalesOutputProfile)


def load_monthly_sales_profile(path: Path | str) -> MonthlySalesProfile:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return MonthlySalesProfile.model_validate(data)
