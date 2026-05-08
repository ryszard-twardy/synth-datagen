"""Tests for ``synth_datagen.pharma.config.PharmaConfig``.

The config is the boundary between the CLI/YAML surface and the
engine. Pydantic catches malformed inputs here so the engine can
assume a clean, validated PharmaConfig instance and not re-validate
internally.

Sub-mode tests cover both ``acute-care`` and ``specialty-care``;
date / count / quota bounds are sub-mode-agnostic; the
``primary_atc`` validator is sub-mode-aware (required for specialty,
ignored / defaulted for acute).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from synth_datagen.pharma.config import PharmaConfig

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pharma"
HOSPITALS_CSV = FIXTURE_DIR / "osm_hospitals_DE_test.csv"
BL_GEOJSON = FIXTURE_DIR / "bundeslaender_test.geojson"
LK_GEOJSON = FIXTURE_DIR / "landkreise_test.geojson"


# Helper so tests don't have to spell every required field every time.
def _minimal_kwargs(**overrides) -> dict:
    base = dict(
        sub_mode="acute-care",
        hospitals_csv=HOSPITALS_CSV,
        bkg_bundeslaender=BL_GEOJSON,
        bkg_landkreise=LK_GEOJSON,
        seed=42,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_minimal_acute_config_validates() -> None:
    cfg = PharmaConfig(**_minimal_kwargs())
    assert cfg.sub_mode == "acute-care"
    assert cfg.seed == 42
    # Defaults come from the spec (Phase 6 plan).
    assert cfg.company_name == "MediCorp"
    assert cfg.account_count == 850
    assert cfg.rep_count == 40
    assert cfg.data_quality == "medium"
    assert cfg.benchmark_validation is False


def test_minimal_specialty_config_validates() -> None:
    cfg = PharmaConfig(**_minimal_kwargs(sub_mode="specialty-care"))
    assert cfg.sub_mode == "specialty-care"
    # Default primary_atc kicks in for specialty.
    assert cfg.primary_atc == "L01"


def test_config_paths_resolve_to_path_objects() -> None:
    cfg = PharmaConfig(**_minimal_kwargs())
    assert isinstance(cfg.hospitals_csv, Path)
    assert isinstance(cfg.bkg_bundeslaender, Path)
    assert isinstance(cfg.bkg_landkreise, Path)


# ---------------------------------------------------------------------------
# File-existence validation
# ---------------------------------------------------------------------------


def test_config_rejects_missing_hospitals_csv(tmp_path: Path) -> None:
    bogus = tmp_path / "does_not_exist.csv"
    with pytest.raises(ValidationError, match="not found|does not exist"):
        PharmaConfig(**_minimal_kwargs(hospitals_csv=bogus))


def test_config_rejects_missing_bkg_bundeslaender(tmp_path: Path) -> None:
    bogus = tmp_path / "missing_bl.geojson"
    with pytest.raises(ValidationError, match="not found|does not exist"):
        PharmaConfig(**_minimal_kwargs(bkg_bundeslaender=bogus))


def test_config_rejects_missing_bkg_landkreise(tmp_path: Path) -> None:
    bogus = tmp_path / "missing_lk.geojson"
    with pytest.raises(ValidationError, match="not found|does not exist"):
        PharmaConfig(**_minimal_kwargs(bkg_landkreise=bogus))


# ---------------------------------------------------------------------------
# Sub-mode validation
# ---------------------------------------------------------------------------


def test_config_rejects_unknown_sub_mode() -> None:
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(sub_mode="vertical-account-based"))


def test_config_accepts_both_documented_sub_modes() -> None:
    for mode in ("acute-care", "specialty-care"):
        cfg = PharmaConfig(**_minimal_kwargs(sub_mode=mode))
        assert cfg.sub_mode == mode


# ---------------------------------------------------------------------------
# Numeric bounds
# ---------------------------------------------------------------------------


def test_account_count_lower_bound() -> None:
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(account_count=99))


def test_account_count_upper_bound() -> None:
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(account_count=3001))


def test_rep_count_lower_bound() -> None:
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(rep_count=9))


def test_rep_count_upper_bound() -> None:
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(rep_count=201))


def test_target_quota_attainment_bounds() -> None:
    # Below the floor.
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(target_quota_attainment=0.4))
    # Above the ceiling.
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(target_quota_attainment=1.6))


def test_seed_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(seed=-1))


# ---------------------------------------------------------------------------
# Date validation
# ---------------------------------------------------------------------------


def test_end_date_must_be_after_start_date() -> None:
    with pytest.raises(ValidationError, match="end_date|start|date"):
        PharmaConfig(
            **_minimal_kwargs(
                start_date=date(2026, 1, 1),
                end_date=date(2025, 12, 31),
            )
        )


def test_default_date_window_is_valid() -> None:
    cfg = PharmaConfig(**_minimal_kwargs())
    assert cfg.start_date < cfg.end_date


# ---------------------------------------------------------------------------
# Sub-mode × primary_atc cross-validation
# ---------------------------------------------------------------------------


def test_specialty_primary_atc_default_oncology() -> None:
    cfg = PharmaConfig(**_minimal_kwargs(sub_mode="specialty-care"))
    assert cfg.primary_atc == "L01"


def test_specialty_accepts_documented_atc_values() -> None:
    for atc in ("L01", "L04", "S01", "D"):
        cfg = PharmaConfig(
            **_minimal_kwargs(sub_mode="specialty-care", primary_atc=atc)
        )
        assert cfg.primary_atc == atc


def test_specialty_rejects_unknown_atc() -> None:
    with pytest.raises(ValidationError, match="primary_atc|atc"):
        PharmaConfig(**_minimal_kwargs(sub_mode="specialty-care", primary_atc="ZZ99"))


def test_acute_does_not_require_primary_atc() -> None:
    """Acute-care sub-mode covers ATC J/L/N/B in distribution; no
    single primary group. The field is allowed to be None for acute."""
    cfg = PharmaConfig(**_minimal_kwargs(sub_mode="acute-care"))
    # Either None or an explicit default — the contract is just
    # "doesn't crash and isn't required from the caller".
    assert cfg.primary_atc is None or isinstance(cfg.primary_atc, str)


# ---------------------------------------------------------------------------
# data_quality validation
# ---------------------------------------------------------------------------


def test_data_quality_accepts_documented_values() -> None:
    for q in ("clean", "medium", "messy"):
        cfg = PharmaConfig(**_minimal_kwargs(data_quality=q))
        assert cfg.data_quality == q


def test_data_quality_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        PharmaConfig(**_minimal_kwargs(data_quality="extra-spicy"))


# ---------------------------------------------------------------------------
# Strict-model contract
# ---------------------------------------------------------------------------


def test_config_rejects_unknown_extra_field() -> None:
    """``extra='forbid'`` mirrors the saas_v3 idiom — typos in the YAML
    fail loudly rather than silently going unread."""
    with pytest.raises(ValidationError, match="extra|forbidden|unexpected"):
        PharmaConfig(**_minimal_kwargs(thiss_iss_a_typoo="oops"))


def test_config_currency_default() -> None:
    cfg = PharmaConfig(**_minimal_kwargs())
    assert cfg.currency == "EUR"


def test_company_name_override() -> None:
    cfg = PharmaConfig(**_minimal_kwargs(company_name="Acme Pharma"))
    assert cfg.company_name == "Acme Pharma"
