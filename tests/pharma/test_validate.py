"""Tests for ``synth_datagen.pharma.validate``.

The validate module consumes the engine's 8-table output and runs a
fixed set of benchmark checks (REQ-1 / REQ-3 / REQ-4 / REQ-5 / REQ-7).
Returns a ``ValidationResult`` data structure; CLI in commit 12
serializes it to ``benchmark_validation.md``. Validate does NO file
I/O.

Scope (v0.3.0 — see commit-11 message for deferral rationale):

- REQ-1: AGS hierarchy invariant (always runs); population correlation
  (skipped under hermetic fixture, runs under real BKG data).
- REQ-3: revenue median ∈ sub-mode band.
- REQ-4: median visits/account/year ∈ sub-mode band.
- REQ-5: top-20 % revenue concentration ∈ loose Pareto envelope.
- REQ-7: orders FK integrity to accounts/reps/products.

REQ-2 (ownership distribution) and REQ-6 (product catalog spread) are
deferred to v0.3.x — those need production-scale data to assert
meaningfully.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Skip whole module if [pharma] extra missing.
pytest.importorskip("geopandas", reason="requires '[pharma]' extra")
pytest.importorskip("shapely", reason="requires '[pharma]' extra")

from synth_datagen.pharma import engine, validate  # noqa: E402
from synth_datagen.pharma.config import PharmaConfig  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pharma"
HOSPITALS_CSV = FIXTURE_DIR / "osm_hospitals_DE_test.csv"
BL_GEOJSON = FIXTURE_DIR / "bundeslaender_test.geojson"
LK_GEOJSON = FIXTURE_DIR / "landkreise_test.geojson"

# Smoke-scale config — same shape as test_engine_smoke.
SMOKE_ACCOUNT_COUNT = 200


def _make_config(sub_mode: str = "acute-care", *, seed: int = 42) -> PharmaConfig:
    return PharmaConfig(
        sub_mode=sub_mode,
        hospitals_csv=HOSPITALS_CSV,
        bkg_bundeslaender=BL_GEOJSON,
        bkg_landkreise=LK_GEOJSON,
        seed=seed,
        account_count=SMOKE_ACCOUNT_COUNT,
        rep_count=20,
        data_quality="clean",
    )


# ---------------------------------------------------------------------------
# ValidationResult / CheckResult shape
# ---------------------------------------------------------------------------


def test_check_status_literal() -> None:
    """The CheckStatus literal pins the four allowed states."""
    # Importable + iterable (typing.Literal is checked at type-check
    # time only; runtime exposure is via a tuple constant in validate).
    statuses = validate.ALLOWED_STATUSES
    assert set(statuses) == {"pass", "fail", "warn", "skip"}


def test_validation_result_is_frozen() -> None:
    """ValidationResult is a frozen dataclass — engine and CLI must
    not mutate the structure post-creation."""
    cfg = _make_config()
    out = engine.generate(cfg)
    result = validate.validate(cfg, out)
    with pytest.raises((AttributeError, TypeError)):
        result.checks = []  # type: ignore[misc]


def test_check_result_is_frozen() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    assert result.checks
    first = result.checks[0]
    with pytest.raises((AttributeError, TypeError)):
        first.status = "fail"  # type: ignore[misc]


def test_check_result_required_fields() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    for check in result.checks:
        assert isinstance(check.name, str) and check.name
        assert check.status in {"pass", "fail", "warn", "skip"}
        assert isinstance(check.message, str)
        # ``expected`` and ``actual`` are free-form (str / float / dict)
        # so the CLI can render them. Just confirm the attrs exist.
        _ = check.expected
        _ = check.actual


# ---------------------------------------------------------------------------
# Smoke: validate produces a non-empty checks list and a top-level
# pass/fail summary
# ---------------------------------------------------------------------------


def test_validate_runs_against_acute_engine_output() -> None:
    cfg = _make_config(sub_mode="acute-care")
    out = engine.generate(cfg)
    result = validate.validate(cfg, out)
    assert result.checks, "validate produced zero checks"
    # All-pass on smoke fixture (REQ-1 population correlation skipped).
    statuses = {c.status for c in result.checks}
    assert "fail" not in statuses, (
        f"acute smoke fixture failed validation: "
        f"{[c for c in result.checks if c.status == 'fail']}"
    )


def test_validate_runs_against_specialty_engine_output() -> None:
    cfg = _make_config(sub_mode="specialty-care")
    out = engine.generate(cfg)
    result = validate.validate(cfg, out)
    assert result.checks
    statuses = {c.status for c in result.checks}
    assert "fail" not in statuses, (
        f"specialty smoke fixture failed validation: "
        f"{[c for c in result.checks if c.status == 'fail']}"
    )


def test_validate_summary_property_pass_count() -> None:
    """ValidationResult.summary() returns counts per status — small
    helper so the CLI doesn't have to iterate twice."""
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    summary = result.summary()
    assert isinstance(summary, dict)
    assert set(summary.keys()) == {"pass", "fail", "warn", "skip"}
    assert sum(summary.values()) == len(result.checks)


def test_validate_overall_status_pass_when_no_failures() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    # On the smoke fixture every check is pass-or-skip; overall must
    # be pass.
    assert result.overall_status == "pass"


# ---------------------------------------------------------------------------
# REQ-1 — AGS hierarchy + population correlation
# ---------------------------------------------------------------------------


def test_check_ags_hierarchy_passes_on_clean_engine() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert "ags_hierarchy_invariant" in by_name
    assert by_name["ags_hierarchy_invariant"].status == "pass"


def test_check_ags_hierarchy_fails_on_corrupted_accounts() -> None:
    """If a downstream pipeline corrupts the AGS prefix, validate
    must catch it. Synthesize the corruption directly on the engine
    output so we don't need a separate failure-mode fixture."""
    cfg = _make_config()
    out = engine.generate(cfg)
    # Break one row's prefix.
    out["accounts"].loc[0, "landkreis_ags"] = "99999"
    out["accounts"].loc[0, "bundesland_ags"] = "01"
    result = validate.validate(cfg, out)
    by_name = {c.name: c for c in result.checks}
    assert by_name["ags_hierarchy_invariant"].status == "fail"


def test_check_population_correlation_skipped_on_fixture() -> None:
    """Spec REQ-1: ρ > 0.7 against DESTATIS BL population. The
    hermetic fixture has 3 BLs — Spearman on n=3 is statistically
    meaningless, so validate must mark the check ``skip`` (not
    fabricate a pass)."""
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert "bl_population_correlation" in by_name
    assert by_name["bl_population_correlation"].status == "skip"
    msg = by_name["bl_population_correlation"].message.lower()
    assert "fixture" in msg or "bundesländer" in msg or "real" in msg


# ---------------------------------------------------------------------------
# REQ-3 — revenue median in sub-mode band
# ---------------------------------------------------------------------------


def test_check_acute_revenue_median_passes_on_clean_engine() -> None:
    cfg = _make_config(sub_mode="acute-care")
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert "revenue_median_band" in by_name
    assert by_name["revenue_median_band"].status == "pass"


def test_check_specialty_revenue_median_passes_on_clean_engine() -> None:
    cfg = _make_config(sub_mode="specialty-care")
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert by_name["revenue_median_band"].status == "pass"


def test_check_revenue_median_fails_when_revenue_zeroed() -> None:
    """Engine output mutated to all-zero revenue — must fail the
    band check (median of zero is below any positive band floor)."""
    cfg = _make_config(sub_mode="acute-care")
    out = engine.generate(cfg)
    out["accounts"]["annual_revenue"] = 0.0
    result = validate.validate(cfg, out)
    by_name = {c.name: c for c in result.checks}
    assert by_name["revenue_median_band"].status == "fail"


# ---------------------------------------------------------------------------
# REQ-4 — visit frequency in sub-mode band
# ---------------------------------------------------------------------------


def test_check_acute_visit_freq_passes_on_clean_engine() -> None:
    cfg = _make_config(sub_mode="acute-care")
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert "visits_per_account_per_year" in by_name
    assert by_name["visits_per_account_per_year"].status == "pass"


def test_check_specialty_visit_freq_passes_on_clean_engine() -> None:
    cfg = _make_config(sub_mode="specialty-care")
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert by_name["visits_per_account_per_year"].status == "pass"


# ---------------------------------------------------------------------------
# REQ-5 — top-20 % revenue concentration (loose band)
# ---------------------------------------------------------------------------


def test_check_revenue_concentration_passes_on_clean_engine() -> None:
    cfg = _make_config(sub_mode="acute-care")
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert "top20_revenue_concentration" in by_name
    assert by_name["top20_revenue_concentration"].status == "pass"


def test_check_revenue_concentration_fails_on_uniform_revenue() -> None:
    """Set every account to the same revenue → top-20 % share collapses
    to ~0.20, well below the loose band floor (0.45)."""
    cfg = _make_config(sub_mode="acute-care")
    out = engine.generate(cfg)
    out["accounts"]["annual_revenue"] = 1000.0
    result = validate.validate(cfg, out)
    by_name = {c.name: c for c in result.checks}
    assert by_name["top20_revenue_concentration"].status == "fail"


# ---------------------------------------------------------------------------
# REQ-7 — orders FK integrity
# ---------------------------------------------------------------------------


def test_check_orders_fk_integrity_passes_on_clean_engine() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    by_name = {c.name: c for c in result.checks}
    assert "orders_fk_integrity" in by_name
    assert by_name["orders_fk_integrity"].status == "pass"


def test_check_orders_fk_integrity_fails_on_orphan() -> None:
    """Inject an orphan account_id into orders — validate must catch
    it. Production engine never produces orphans (FK sampling-with-
    replacement is bounded by the parent-id list), but a downstream
    pipeline mutation could."""
    cfg = _make_config()
    out = engine.generate(cfg)
    out["orders"].loc[0, "account_id"] = "acc_pharma_999999"  # not in accounts
    result = validate.validate(cfg, out)
    by_name = {c.name: c for c in result.checks}
    assert by_name["orders_fk_integrity"].status == "fail"


# ---------------------------------------------------------------------------
# Pure-function discipline
# ---------------------------------------------------------------------------


def test_validate_does_not_write_files(tmp_path: Path, monkeypatch) -> None:
    """validate.validate() must perform NO file I/O. Catch any
    accidental open() / Path.write_text in the implementation by
    redirecting cwd to a temp dir and asserting it remains empty."""
    monkeypatch.chdir(tmp_path)
    cfg = _make_config()
    validate.validate(cfg, engine.generate(cfg))
    leftovers = list(tmp_path.iterdir())
    assert leftovers == [], f"validate.validate() wrote files to cwd: {leftovers}"


def test_validate_does_not_mutate_input_tables() -> None:
    cfg = _make_config()
    out = engine.generate(cfg)
    pre_acc = out["accounts"].to_csv(index=False)
    pre_ord = out["orders"].to_csv(index=False)
    validate.validate(cfg, out)
    assert out["accounts"].to_csv(index=False) == pre_acc
    assert out["orders"].to_csv(index=False) == pre_ord


def test_validate_deterministic_per_seed() -> None:
    """Same seed + same config → identical ValidationResult content."""
    cfg = _make_config(seed=42)
    out_a = engine.generate(cfg)
    out_b = engine.generate(cfg)
    res_a = validate.validate(cfg, out_a)
    res_b = validate.validate(cfg, out_b)
    a_pairs = [(c.name, c.status) for c in res_a.checks]
    b_pairs = [(c.name, c.status) for c in res_b.checks]
    assert a_pairs == b_pairs


# ---------------------------------------------------------------------------
# Markdown-rendering helper (CLI uses this in commit 12)
# ---------------------------------------------------------------------------


def test_render_markdown_returns_string() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    md = validate.render_markdown(result)
    assert isinstance(md, str)
    assert md.strip(), "rendered markdown is empty"


def test_render_markdown_contains_each_check_name() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    md = validate.render_markdown(result)
    for check in result.checks:
        assert check.name in md, f"check name {check.name!r} missing from markdown"


def test_render_markdown_indicates_overall_status() -> None:
    cfg = _make_config()
    result = validate.validate(cfg, engine.generate(cfg))
    md = validate.render_markdown(result).lower()
    assert "pass" in md or "fail" in md
