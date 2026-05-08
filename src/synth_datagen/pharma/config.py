"""Pydantic configuration model for the pharma scenario.

The boundary between the CLI / YAML surface and the pharma engine.
Validation happens here; the engine receives a ``PharmaConfig``
instance and assumes paths exist, sub-mode is one of the documented
values, and numeric fields are within their declared ranges. The
engine does NOT re-validate.

Mirrors the saas_v3 ``StrictModel`` idiom (``extra='forbid'``) so a
typo in the YAML fails loudly at parse time rather than silently
going unread.

Default values come from the Phase 6 spec
(``prompts/pharma/05_implementation.md``) and are tuned to MediCorp,
the running portfolio example. They can be overridden per call.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# Documented set of primary ATC groups for specialty-care sub-mode.
# L01 oncology (default), L04 immunosuppressants, S01 ophthalmologicals,
# D dermatologicals. Acute-care covers a broader mix and ignores this
# field.
_VALID_PRIMARY_ATC: frozenset[str] = frozenset({"L01", "L04", "S01", "D"})


class PharmaConfig(BaseModel):
    """Configuration for a single pharma generation run."""

    model_config = ConfigDict(extra="forbid")

    # ------------------------------------------------------------------
    # Required inputs
    # ------------------------------------------------------------------

    sub_mode: Literal["acute-care", "specialty-care"] = Field(
        description="Pharma sub-mode. 'acute-care' targets hospitals "
        "(amenity=hospital, beds≥50). 'specialty-care' targets "
        "specialty clinics, MVZ, and specialist groups.",
    )

    hospitals_csv: Path = Field(
        description="Path to the OSM hospital snapshot CSV. Caller-"
        "supplied — synth-datagen does not bundle this. License: "
        "ODbL (caller's responsibility).",
    )

    bkg_bundeslaender: Path = Field(
        description="Path to the BKG VG250 Bundesländer GeoJSON "
        "(16 features in production). License: dl-de/by-2-0.",
    )

    bkg_landkreise: Path = Field(
        description="Path to the BKG VG250 Landkreise GeoJSON "
        "(~401 features in production, with parent AGS). License: "
        "dl-de/by-2-0.",
    )

    seed: int = Field(
        ge=0,
        description="User-facing seed for the run. RNG isolation is "
        "applied internally via the 'pharma' salt — see "
        "src/synth_datagen/rng.py.",
    )

    # ------------------------------------------------------------------
    # Defaults from the Phase 6 spec — overridable per run
    # ------------------------------------------------------------------

    company_name: str = Field(
        default="MediCorp",
        description="Synthetic manufacturer name. Appears in metadata "
        "and example outputs only — not embedded in any generated "
        "row.",
    )

    rep_count: int = Field(
        default=40,
        ge=10,
        le=200,
        description="Number of sales reps. Acute default 40 "
        "(~20 accounts/rep); specialty default ~60 "
        "(~30 accounts/rep).",
    )

    account_count: int = Field(
        default=850,
        ge=100,
        le=3000,
        description="Number of accounts to generate. Acute "
        "600–900 typical; specialty 1500–2500 typical.",
    )

    start_date: date = Field(
        default=date(2023, 1, 1),
        description="Order / visit history start.",
    )

    end_date: date = Field(
        default=date(2026, 6, 30),
        description="Order / visit history end. Must be > start_date.",
    )

    currency: str = Field(
        default="EUR",
        description="ISO-4217 currency code. EUR is the only tested "
        "value in v0.3.0 since the benchmarks are anchored to it.",
    )

    primary_atc: str | None = Field(
        default=None,
        description="Specialty-care: dominant ATC group "
        "(L01 oncology, L04 immunosuppressants, S01 ophthalmologicals, "
        "D dermatologicals). Acute-care: ignored.",
    )

    target_quota_attainment: float = Field(
        default=0.92,
        ge=0.5,
        le=1.5,
        description="Median rep quota-attainment ratio. Drives the "
        "synthetic revenue distribution shape.",
    )

    data_quality: Literal["clean", "medium", "messy"] = Field(
        default="medium",
        description="Quality-injection level. clean=zero defects; "
        "medium=published rates per spec §quality; messy=4× medium.",
    )

    benchmark_validation: bool = Field(
        default=False,
        description="If true, run the benchmark-validation pass after "
        "generation and emit benchmark_validation.md alongside the CSVs.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("hospitals_csv", "bkg_bundeslaender", "bkg_landkreise")
    @classmethod
    def _path_must_exist(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(f"Required input file not found: {value}")
        return value

    @model_validator(mode="after")
    def _end_date_after_start_date(self) -> "PharmaConfig":
        if self.end_date <= self.start_date:
            raise ValueError(
                f"end_date ({self.end_date}) must be strictly after "
                f"start_date ({self.start_date})."
            )
        return self

    @model_validator(mode="after")
    def _resolve_primary_atc(self) -> "PharmaConfig":
        if self.sub_mode == "specialty-care":
            # Default to L01 oncology when caller didn't pick.
            if self.primary_atc is None:
                # Bypass validation since we're inside model-after; set
                # via __dict__ to avoid recursive model_validate.
                object.__setattr__(self, "primary_atc", "L01")
            elif self.primary_atc not in _VALID_PRIMARY_ATC:
                raise ValueError(
                    f"primary_atc {self.primary_atc!r} not one of the "
                    f"documented values {sorted(_VALID_PRIMARY_ATC)}. "
                    "Add it to _VALID_PRIMARY_ATC in pharma/config.py "
                    "if it should be supported."
                )
        # Acute-care: no constraint. Field is ignored downstream.
        return self
