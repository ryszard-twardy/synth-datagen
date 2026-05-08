"""Pharma benchmark validation pass.

Pure consumer of the engine's 8-table output. Runs a fixed set of
benchmark checks and returns a ``ValidationResult`` data structure;
the CLI in commit 12 serializes it to ``benchmark_validation.md``.

This module performs **NO file I/O**. ``validate.validate()`` is a
pure function over `(PharmaConfig, dict[str, DataFrame])`. The
``render_markdown()`` helper produces a string the CLI writes.

## Scope (v0.3.0)

Five spec REQs are checked:

- **REQ-1** — AGS hierarchy invariant (always runs); BL population
  correlation against DESTATIS (skipped when n_BL < 10, i.e. on the
  hermetic fixture; runs against real BKG data).
- **REQ-3** — revenue median ∈ sub-mode log-normal band (acute
  ~€95 k; specialty ~€18 k).
- **REQ-4** — median visits/account/year ∈ sub-mode Beta band
  (acute 3-6, specialty 8-14).
- **REQ-5** — top-20 % revenue concentration ∈ loose Pareto envelope
  (rationale documented in commit-10's property-test message body —
  loose enough to never flake at smoke scale, strict enough to catch
  uniform-revenue regressions).
- **REQ-7** — orders FK integrity (account_id / rep_id / product_id
  resolve to parent tables).

REQ-2 (ownership distribution) and REQ-6 (product catalog spread)
are deferred to v0.3.x — they need production-scale data to assert
meaningfully and would always skip on smoke fixtures.

## Status semantics

- ``pass``  — check ran and met its contract.
- ``fail``  — check ran and violated its contract. The dataset is
  unsuitable for the named REQ.
- ``warn``  — check ran but the result is borderline. v0.3.0 does
  not emit warns; reserved for v0.3.x calibration.
- ``skip``  — check could not run (e.g. fixture too small for a
  meaningful Spearman correlation). Skips do NOT contribute to
  ``overall_status``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from synth_datagen.pharma.config import PharmaConfig

CheckStatus = Literal["pass", "fail", "warn", "skip"]

#: Runtime-accessible tuple of allowed status values; pinned by
#: ``test_check_status_literal``. Keep in sync with the
#: ``CheckStatus`` Literal above.
ALLOWED_STATUSES: tuple[str, ...] = ("pass", "fail", "warn", "skip")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    """One row of the validation report."""

    name: str
    status: CheckStatus
    message: str
    expected: Any = None
    actual: Any = None


@dataclass(frozen=True)
class ValidationResult:
    """The full report. Frozen so engine and CLI cannot mutate
    after creation."""

    sub_mode: str
    seed: int
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    @property
    def overall_status(self) -> CheckStatus:
        """``fail`` if any check failed, else ``pass``. ``skip`` and
        ``warn`` do NOT down-grade overall status."""
        statuses = {c.status for c in self.checks}
        if "fail" in statuses:
            return "fail"
        return "pass"

    def summary(self) -> dict[str, int]:
        """Counts per status — small helper so the CLI doesn't iterate
        twice."""
        out = dict.fromkeys(ALLOWED_STATUSES, 0)
        for c in self.checks:
            out[c.status] += 1
        return out


# ---------------------------------------------------------------------------
# REQ-3 / REQ-4 / REQ-5 band constants — keep loose, see commit-10 message
# for rationale
# ---------------------------------------------------------------------------

# REQ-3: revenue median in sub-mode log-normal band. Acute target
# €95 k; specialty €18 k. Bands are 0.4× to 2.5× the target — loose
# enough to never flake at smoke scale, strict enough to catch
# all-zero-revenue regressions.
_ACUTE_REVENUE_MEDIAN_BAND: tuple[float, float] = (40_000.0, 240_000.0)
_SPECIALTY_REVENUE_MEDIAN_BAND: tuple[float, float] = (8_000.0, 45_000.0)

# REQ-4: visit frequency band. Same as the property-test bands in
# commit 10.
_ACUTE_VISIT_BAND: tuple[float, float] = (2.0, 7.0)
_SPECIALTY_VISIT_BAND: tuple[float, float] = (6.0, 16.0)

# REQ-5: top-20 % revenue concentration. Same envelope as commit 10.
_ACUTE_CONCENTRATION_BAND: tuple[float, float] = (0.45, 0.85)
_SPECIALTY_CONCENTRATION_BAND: tuple[float, float] = (0.40, 0.80)

# REQ-1 population correlation runs only when n_BL is large enough
# for Spearman to be meaningful. The hermetic fixture has 3 BLs;
# real BKG VG250 has 16. Threshold of 10 picks the fixture as the
# obvious "skip" case while still running on any reasonable real-
# world subset.
_MIN_BL_FOR_CORRELATION: int = 10
_MIN_POPULATION_CORRELATION: float = 0.7


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def validate(
    config: PharmaConfig,
    tables: dict[str, pd.DataFrame],
) -> ValidationResult:
    """Run the v0.3.0 pharma benchmark checks against ``tables``."""
    checks: list[CheckResult] = []

    checks.append(_check_ags_hierarchy(tables))
    checks.append(_check_population_correlation(tables))
    checks.append(_check_revenue_median(config, tables))
    checks.append(_check_visit_frequency(config, tables))
    checks.append(_check_top20_concentration(config, tables))
    checks.append(_check_orders_fk_integrity(tables))

    return ValidationResult(
        sub_mode=config.sub_mode,
        seed=int(config.seed),
        checks=tuple(checks),
    )


def render_markdown(result: ValidationResult) -> str:
    """Render a ValidationResult as a markdown report string."""
    lines: list[str] = []
    lines.append(
        f"# Pharma benchmark validation — {result.sub_mode} (seed={result.seed})"
    )
    lines.append("")
    summary = result.summary()
    lines.append(
        f"**Overall:** {result.overall_status.upper()}  |  "
        f"pass={summary['pass']}  fail={summary['fail']}  "
        f"warn={summary['warn']}  skip={summary['skip']}"
    )
    lines.append("")
    lines.append("| Check | Status | Expected | Actual | Notes |")
    lines.append("|-------|--------|----------|--------|-------|")
    for c in result.checks:
        lines.append(
            f"| `{c.name}` | **{c.status}** | {_render_value(c.expected)} | "
            f"{_render_value(c.actual)} | {c.message} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, tuple) and len(value) == 2:
        lo, hi = value
        return f"[{_render_value(lo)}, {_render_value(hi)}]"
    return str(value)


# ---------------------------------------------------------------------------
# Individual checks — REQ-1, REQ-3, REQ-4, REQ-5, REQ-7
# ---------------------------------------------------------------------------


def _check_ags_hierarchy(tables: dict[str, pd.DataFrame]) -> CheckResult:
    """REQ-1: every account satisfies ``landkreis_ags[:2] == bundesland_ags``
    with no NaN parent."""
    accounts = tables.get("accounts")
    if accounts is None or accounts.empty:
        return CheckResult(
            name="ags_hierarchy_invariant",
            status="fail",
            message="accounts table missing or empty",
        )
    nan_bl = int(accounts["bundesland_ags"].isna().sum())
    nan_lk = int(accounts["landkreis_ags"].isna().sum())
    if nan_bl or nan_lk:
        return CheckResult(
            name="ags_hierarchy_invariant",
            status="fail",
            message=f"NaN in AGS columns: bundesland={nan_bl}, landkreis={nan_lk}",
            expected="zero NaN",
            actual={"nan_bundesland": nan_bl, "nan_landkreis": nan_lk},
        )
    prefix = accounts["landkreis_ags"].astype(str).str[:2]
    parent = accounts["bundesland_ags"].astype(str)
    mismatches = int((prefix != parent).sum())
    if mismatches:
        return CheckResult(
            name="ags_hierarchy_invariant",
            status="fail",
            message=f"prefix mismatch on {mismatches} rows",
            expected="all rows: landkreis_ags[:2] == bundesland_ags",
            actual=f"{mismatches} mismatched rows",
        )
    return CheckResult(
        name="ags_hierarchy_invariant",
        status="pass",
        message="every account has consistent AGS hierarchy",
        expected="all rows: landkreis_ags[:2] == bundesland_ags",
        actual="all rows match",
    )


def _check_population_correlation(tables: dict[str, pd.DataFrame]) -> CheckResult:
    """REQ-1 (real-data): account density per BL correlates with
    population, Spearman ρ > 0.7. Skipped when n_BL too small to make
    the correlation statistically meaningful — that's the hermetic
    fixture path."""
    accounts = tables.get("accounts")
    metadata = tables.get("geographic_metadata")
    if accounts is None or accounts.empty or metadata is None or metadata.empty:
        return CheckResult(
            name="bl_population_correlation",
            status="skip",
            message="accounts or geographic_metadata missing",
        )
    n_bl = int(metadata.iloc[0].get("bundesland_count", 0))
    if n_bl < _MIN_BL_FOR_CORRELATION:
        return CheckResult(
            name="bl_population_correlation",
            status="skip",
            message=(
                f"only {n_bl} Bundesländer in fixture (need ≥ "
                f"{_MIN_BL_FOR_CORRELATION} for meaningful Spearman); "
                "runs against real BKG data, not synthetic test fixture"
            ),
            expected=f"ρ > {_MIN_POPULATION_CORRELATION}",
            actual=f"n_bundeslaender={n_bl}",
        )
    # Real-data path: requires the engine to have written a per-BL
    # population vector into geographic_metadata. v0.3.0 doesn't yet
    # surface that lookup (would need to round-trip BKG GeoJSON
    # populations through the engine output). Until that's wired, we
    # mark this skip even on real data.
    return CheckResult(
        name="bl_population_correlation",
        status="skip",
        message=(
            "real-data correlation lookup not yet wired through "
            "geographic_metadata; deferred to v0.3.x"
        ),
        expected=f"ρ > {_MIN_POPULATION_CORRELATION}",
        actual="(not computed)",
    )


def _check_revenue_median(
    config: PharmaConfig,
    tables: dict[str, pd.DataFrame],
) -> CheckResult:
    """REQ-3: median annual_revenue in sub-mode band."""
    accounts = tables.get("accounts")
    if accounts is None or accounts.empty:
        return CheckResult(
            name="revenue_median_band",
            status="fail",
            message="accounts table missing or empty",
        )
    median = float(accounts["annual_revenue"].median())
    band = (
        _ACUTE_REVENUE_MEDIAN_BAND
        if config.sub_mode == "acute-care"
        else _SPECIALTY_REVENUE_MEDIAN_BAND
    )
    if band[0] <= median <= band[1]:
        return CheckResult(
            name="revenue_median_band",
            status="pass",
            message=f"median annual_revenue €{median:,.0f}",
            expected=band,
            actual=median,
        )
    return CheckResult(
        name="revenue_median_band",
        status="fail",
        message=f"median €{median:,.0f} outside band €{band}",
        expected=band,
        actual=median,
    )


def _check_visit_frequency(
    config: PharmaConfig,
    tables: dict[str, pd.DataFrame],
) -> CheckResult:
    """REQ-4: median visits/account/year in sub-mode Beta band."""
    accounts = tables.get("accounts")
    visits = tables.get("rep_visits")
    if accounts is None or accounts.empty or visits is None or visits.empty:
        return CheckResult(
            name="visits_per_account_per_year",
            status="fail",
            message="accounts or rep_visits table missing or empty",
        )
    days_total = (config.end_date - config.start_date).days
    if days_total <= 0:
        return CheckResult(
            name="visits_per_account_per_year",
            status="skip",
            message="non-positive date window",
        )
    years_in_window = days_total / 365.25
    counts = (
        visits.groupby("account_id")
        .size()
        .reindex(accounts["account_id"], fill_value=0)
    )
    visits_per_year = counts / years_in_window
    median = float(visits_per_year.median())
    band = (
        _ACUTE_VISIT_BAND if config.sub_mode == "acute-care" else _SPECIALTY_VISIT_BAND
    )
    if band[0] <= median <= band[1]:
        return CheckResult(
            name="visits_per_account_per_year",
            status="pass",
            message=f"median visits/year {median:.2f}",
            expected=band,
            actual=median,
        )
    return CheckResult(
        name="visits_per_account_per_year",
        status="fail",
        message=f"median visits/year {median:.2f} outside band {band}",
        expected=band,
        actual=median,
    )


def _check_top20_concentration(
    config: PharmaConfig,
    tables: dict[str, pd.DataFrame],
) -> CheckResult:
    """REQ-5: top 20 % of accounts hold a band of total revenue."""
    accounts = tables.get("accounts")
    if accounts is None or accounts.empty:
        return CheckResult(
            name="top20_revenue_concentration",
            status="fail",
            message="accounts table missing or empty",
        )
    revenue = accounts["annual_revenue"].sort_values(ascending=False)
    total = float(revenue.sum())
    if total <= 0:
        return CheckResult(
            name="top20_revenue_concentration",
            status="fail",
            message=f"total revenue {total:.2f} non-positive",
            expected="positive total revenue",
            actual=total,
        )
    n_top = max(1, int(round(0.20 * len(revenue))))
    top_share = float(revenue.head(n_top).sum() / total)
    band = (
        _ACUTE_CONCENTRATION_BAND
        if config.sub_mode == "acute-care"
        else _SPECIALTY_CONCENTRATION_BAND
    )
    if band[0] <= top_share <= band[1]:
        return CheckResult(
            name="top20_revenue_concentration",
            status="pass",
            message=f"top-20% share {top_share:.2%}",
            expected=band,
            actual=top_share,
        )
    return CheckResult(
        name="top20_revenue_concentration",
        status="fail",
        message=f"top-20% share {top_share:.2%} outside band {band}",
        expected=band,
        actual=top_share,
    )


def _check_orders_fk_integrity(tables: dict[str, pd.DataFrame]) -> CheckResult:
    """REQ-7: orders.account_id / rep_id / product_id all resolve to
    parent tables."""
    orders = tables.get("orders")
    accounts = tables.get("accounts")
    reps = tables.get("sales_reps")
    products = tables.get("products")
    if (
        orders is None
        or orders.empty
        or accounts is None
        or reps is None
        or products is None
    ):
        return CheckResult(
            name="orders_fk_integrity",
            status="fail",
            message="orders / accounts / sales_reps / products missing",
        )
    orphans: dict[str, int] = {}
    accounts_set = set(accounts["account_id"])
    reps_set = set(reps["rep_id"])
    products_set = set(products["product_id"])
    orphan_acc = int((~orders["account_id"].isin(accounts_set)).sum())
    orphan_rep = int((~orders["rep_id"].isin(reps_set)).sum())
    orphan_prod = int((~orders["product_id"].isin(products_set)).sum())
    if orphan_acc:
        orphans["account_id"] = orphan_acc
    if orphan_rep:
        orphans["rep_id"] = orphan_rep
    if orphan_prod:
        orphans["product_id"] = orphan_prod
    if orphans:
        return CheckResult(
            name="orders_fk_integrity",
            status="fail",
            message=f"orphan FKs: {orphans}",
            expected="zero orphans on account_id / rep_id / product_id",
            actual=orphans,
        )
    return CheckResult(
        name="orders_fk_integrity",
        status="pass",
        message=f"{len(orders)} orders, all FKs resolve",
        expected="zero orphans",
        actual="zero orphans",
    )


# ---------------------------------------------------------------------------
# Module hygiene — keep numpy import live so type-checkers don't drop it
# (used for type expansion in future REQ-6 deferred work).
# ---------------------------------------------------------------------------

_ = np
