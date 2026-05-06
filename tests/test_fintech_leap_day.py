"""Regression tests for the Feb-29 leap-day card-expiry crash in fintech.

Reproduces audit_report.md L503-506 — `date(2024, 2, 29).replace(year=2025)`
raises ``ValueError: day is out of range for month`` because 2025 is not a
leap year. Default-scale fintech generation hits this with high probability
because card issue dates land on Feb 29 in any 4+ year window crossing
2020 or 2024 (the leap years inside the scenario's 2020-2025 simulation
range).

The fix introduces ``_advance_years_safe`` — a tiny helper that mirrors how
real card issuers handle this case: an issue date of Feb 29 in a non-leap
target year falls back to Feb 28. All other dates are unaffected.

These tests cover both the helper directly and the integration path so a
regression at either layer is caught immediately.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from synth_datagen.generators.fintech import _advance_years_safe


class TestAdvanceYearsSafe:
    """Unit tests for the date-arithmetic helper."""

    def test_normal_date_unchanged(self) -> None:
        """Non-Feb-29 dates round-trip through any positive offset."""
        assert _advance_years_safe(date(2024, 6, 15), 3) == date(2027, 6, 15)

    def test_feb29_to_leap_year_preserves_day(self) -> None:
        """Feb 29 -> another leap year keeps the 29th."""
        assert _advance_years_safe(date(2024, 2, 29), 4) == date(2028, 2, 29)

    def test_feb29_to_non_leap_year_falls_back_to_feb28(self) -> None:
        """The bug's canonical case: 2024-02-29 -> 2025 must yield Feb 28."""
        assert _advance_years_safe(date(2024, 2, 29), 1) == date(2025, 2, 28)

    def test_feb29_2024_to_2027_non_leap(self) -> None:
        """3-year offset (within the scenario's [3,5] expiry range) on a
        non-leap target — exercises the same branch the cards generator hits."""
        assert _advance_years_safe(date(2024, 2, 29), 3) == date(2027, 2, 28)

    def test_feb29_2020_to_2025_non_leap(self) -> None:
        """Older leap-year issue date — covers the 2020-02-29 + 5 path that
        any generator with default scale will sample at least once."""
        assert _advance_years_safe(date(2020, 2, 29), 5) == date(2025, 2, 28)


@pytest.mark.parametrize(
    "issue_year,offset,expected",
    [
        # Inside fintech's scenario window, all combinations of (leap issue
        # year, offset in [3,5]) the generator can sample. Anchors confirm
        # the helper is consistent across the full sample space, not just
        # the single value the crash trace happened to land on.
        (2020, 3, date(2023, 2, 28)),
        (2020, 4, date(2024, 2, 29)),
        (2020, 5, date(2025, 2, 28)),
        (2024, 3, date(2027, 2, 28)),
        (2024, 4, date(2028, 2, 29)),
        (2024, 5, date(2029, 2, 28)),
    ],
)
def test_feb29_full_offset_grid(issue_year: int, offset: int, expected: date) -> None:
    """Parametrised grid across every (leap-issue, offset) combo the cards
    generator can produce in the 2020-2025 simulation window."""
    assert _advance_years_safe(date(issue_year, 2, 29), offset) == expected


def test_fintech_completes_at_card_heavy_scale_with_seed_42(tmp_path: Path) -> None:
    """End-to-end repro of audit_report.md L503-506.

    Default-scale fintech generation (cards=12_000) with seed=42 used to
    crash on the first Feb-29 issue date the RNG produced. This test runs a
    config that keeps cards at default (so Feb-29 issue dates are
    near-certain) but trims everything else so the test stays under ~10s.

    Asserts the run completes (returncode 0) and the cards.csv was written
    with realistic row count.
    """
    repo_root = Path(__file__).resolve().parent.parent
    rows = (
        "customers=300,accounts=500,merchants=50,transactions=500,"
        "cards=12000,loans=40,loan_payments=80"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "synth_datagen.main",
            "generate",
            "--scenario",
            "fintech",
            "--seed",
            "42",
            "--output",
            str(tmp_path),
            "--rows",
            rows,
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={
            **__import__("os").environ,
            "PYTHONIOENCODING": "utf-8",
        },
    )
    assert result.returncode == 0, (
        "fintech generation crashed at card-heavy scale "
        f"(seed=42): {result.stderr[-1000:]}"
    )
    cards_csv = tmp_path / "cards.csv"
    assert cards_csv.exists(), "cards.csv was not produced"
    # Sanity: file should have header + 12_000 data rows, give or take.
    line_count = len(cards_csv.read_text(encoding="utf-8").splitlines())
    assert line_count > 10_000, f"cards.csv too small: {line_count} lines"
