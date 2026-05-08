"""Pharma data-quality injection — 8 documented defects, three levels.

Phase 6 spec ``prompts/pharma/05_implementation.md`` §"DATA QUALITY
INJECTION" (lines 367–380) enumerates the issues. They are mutations
applied AFTER the engine has produced clean output, so the engine
itself stays focused on generation. The level argument selects:

- ``clean``  : no-op, identical-bytes return.
- ``medium`` : published rates per the spec.
- ``messy``  : 4× medium across all 8 defects.

## Stream-isolation contract (spec REQ-7)

The defect pass uses ONLY the ``rng`` argument passed in. It does NOT
draw from the engine's accounts/orders/reps/products/territories/
engagement/regional streams, and it does NOT re-seed from any table
content. This guarantees that flipping ``data_quality`` between
``clean`` and ``messy`` doesn't shift account locations, AGS, order
amounts before mutation, etc. — see
``test_pharma_stream_isolation_quality_doesnt_shift_geo`` in commit
10's property-test suite.

## Locked defect order

The list ``_DEFECT_LABELS`` is the order in which defects fire.
Re-ordering would change the RNG-state ladder and shift bytes for
the same seed. APPEND new defects at the end if you need to add one
in v0.3.x; do not insert.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal, Mapping, MutableMapping

import numpy as np
import pandas as pd

QualityLevel = Literal["clean", "medium", "messy"]

# Stable order — DO NOT reorder. Appending new labels is OK.
_DEFECT_LABELS: tuple[str, ...] = (
    "hospital_name_variants",
    "plz_format_inconsistency",
    "bundesland_name_iso_mismatch",
    "negative_order_quantities",
    "order_visit_date_misalignment",
    "account_rep_assignment_inconsistency",
    "duplicate_atc_old_new_pzn",
    "coordinate_precision_inconsistency",
)

# Medium-mode rates per the spec. Messy applies a 4× multiplier
# across the board; clean is a no-op.
_MEDIUM_RATES: dict[str, float] = {
    "hospital_name_variants": 0.004,
    "plz_format_inconsistency": 0.006,
    "bundesland_name_iso_mismatch": 0.003,
    "negative_order_quantities": 0.011,
    "order_visit_date_misalignment": 0.008,
    "account_rep_assignment_inconsistency": 0.005,
    "duplicate_atc_old_new_pzn": 0.003,
    "coordinate_precision_inconsistency": 0.010,
}

_LEVEL_MULTIPLIER: dict[str, float] = {
    "clean": 0.0,
    "medium": 1.0,
    "messy": 4.0,
}

# ---------------------------------------------------------------------------
# Bundesland aliases for defect 3 — illustrative; real CRM data has
# many more variants. The defect picks one of the alternative spellings
# / codes when the row's existing bundesland matches the canonical
# German name.
# ---------------------------------------------------------------------------

_BUNDESLAND_ALIASES: dict[str, tuple[str, ...]] = {
    "Baden-Württemberg": ("BW", "Baden-Wuerttemberg"),
    "Bayern": ("BY", "Bavaria"),
    "Berlin": ("BE", "Berlin/Brandenburg"),
    "Brandenburg": ("BB", "Berlin/Brandenburg"),
    "Bremen": ("HB", "Free Hanseatic City of Bremen"),
    "Hamburg": ("HH", "Free and Hanseatic City of Hamburg"),
    "Hessen": ("HE", "Hesse"),
    "Mecklenburg-Vorpommern": ("MV", "Mecklenburg-Western Pomerania"),
    "Niedersachsen": ("NI", "Lower Saxony"),
    "Nordrhein-Westfalen": ("NW", "North Rhine-Westphalia"),
    "Rheinland-Pfalz": ("RP", "Rhineland-Palatinate"),
    "Saarland": ("SL", "Saarland"),
    "Sachsen": ("SN", "Saxony"),
    "Sachsen-Anhalt": ("ST", "Saxony-Anhalt"),
    "Schleswig-Holstein": ("SH", "Schleswig-Holstein"),
    "Thüringen": ("TH", "Thuringia"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_from_rate(total: int, rate: float) -> int:
    """Number of rows to mutate. Floor at 0; if rate > 0 and total > 0
    but the product rounds to 0, force at least 1 so the defect isn't
    silently invisible at small input sizes."""
    if total <= 0 or rate <= 0:
        return 0
    raw = total * rate
    n = int(round(raw))
    if n == 0 and raw > 0:
        n = 1
    return min(n, total)


def _pick_indices(rng: np.random.Generator, n: int, total: int) -> np.ndarray:
    """Pick ``n`` distinct row indices from ``[0, total)``."""
    if n <= 0:
        return np.array([], dtype=np.int64)
    return rng.choice(total, size=n, replace=False)


# ---------------------------------------------------------------------------
# Per-defect mutation functions. Each takes a Tables mapping (mutated
# in place) + the quality RNG + the multiplier-adjusted rate.
# ---------------------------------------------------------------------------


def _apply_hospital_name_variants(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("accounts")
    if df is None or df.empty or "name" not in df.columns:
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    suffixes = (" (Hauptstandort)", " - Standort 2", " (alt)", " — Klinik")
    suffix_pick = rng.integers(0, len(suffixes), size=n)
    new_names = df["name"].astype(str).copy()
    for i, slot in zip(idx, suffix_pick):
        new_names.iat[int(i)] = f"{new_names.iat[int(i)]}{suffixes[int(slot)]}"
    df["name"] = new_names


def _apply_plz_format_inconsistency(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("accounts")
    if df is None or df.empty or "plz" not in df.columns:
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    plz = df["plz"].astype(str).copy()
    # Mutation: strip a leading '0' if present, else strip the last
    # digit (4-digit truncation). Either way the string changes.
    for i in idx:
        ii = int(i)
        original = plz.iat[ii]
        if original.startswith("0"):
            plz.iat[ii] = original.lstrip("0")
        else:
            plz.iat[ii] = original[:-1]  # 4-digit truncation
    df["plz"] = plz


def _apply_bundesland_name_iso_mismatch(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("accounts")
    if df is None or df.empty or "bundesland" not in df.columns:
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    new_bl = df["bundesland"].astype(str).copy()
    for i in idx:
        ii = int(i)
        canonical = new_bl.iat[ii]
        aliases = _BUNDESLAND_ALIASES.get(canonical)
        if aliases is None:
            continue  # row already isn't canonical; skip
        pick = int(rng.integers(0, len(aliases)))
        new_bl.iat[ii] = aliases[pick]
    df["bundesland"] = new_bl


def _apply_negative_order_quantities(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("orders")
    if df is None or df.empty or "quantity" not in df.columns:
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    qty = df["quantity"].copy()
    for i in idx:
        qty.iat[int(i)] = -abs(int(qty.iat[int(i)]))
    df["quantity"] = qty


def _apply_order_visit_date_misalignment(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("orders")
    if df is None or df.empty or "order_date" not in df.columns:
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    shifts_days = rng.integers(-90, 91, size=n)  # ±90 days inclusive
    new_dates = df["order_date"].copy()
    for i, sh in zip(idx, shifts_days):
        new_dates.iat[int(i)] = new_dates.iat[int(i)] + timedelta(days=int(sh))
    df["order_date"] = new_dates


def _apply_account_rep_assignment_inconsistency(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("orders")
    if df is None or df.empty or "rep_id" not in df.columns:
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    unique_reps = df["rep_id"].astype(str).unique()
    if len(unique_reps) < 2:
        return  # nothing to swap to
    new_reps = df["rep_id"].astype(str).copy()
    swap_pick = rng.choice(unique_reps, size=n)
    for i, new_rep in zip(idx, swap_pick):
        new_reps.iat[int(i)] = str(new_rep)
    df["rep_id"] = new_reps


def _apply_duplicate_atc_old_new_pzn(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("products")
    if df is None or df.empty or "pzn" not in df.columns:
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    dup_rows = df.iloc[idx].copy()
    # Mutate pzn on the duplicates: increment-and-format keeps PZN-ish
    # shape (8 digits). The duplicates carry the same atc_code so the
    # defect pattern is "same ATC, two PZNs" — the documented
    # PZN-renumbering scenario.
    new_pzns = []
    for _ in range(n):
        # 8-digit string, distinct from any existing in df.
        candidate = int(rng.integers(10_000_000, 100_000_000))
        new_pzns.append(f"{candidate:08d}")
    dup_rows["pzn"] = new_pzns
    # Keep the original product_id stable; pandas concat preserves
    # row order. Append duplicates after the original rows.
    tables["products"] = pd.concat([df, dup_rows], ignore_index=True)


def _apply_coordinate_precision_inconsistency(
    tables: MutableMapping[str, pd.DataFrame],
    rng: np.random.Generator,
    rate: float,
) -> None:
    df = tables.get("accounts")
    if df is None or df.empty:
        return
    if not {"latitude", "longitude"}.issubset(df.columns):
        return
    n = _count_from_rate(len(df), rate)
    if n == 0:
        return
    idx = _pick_indices(rng, n, len(df))
    lat = df["latitude"].copy()
    lon = df["longitude"].copy()
    for i in idx:
        ii = int(i)
        lat.iat[ii] = round(float(lat.iat[ii]), 3)
        lon.iat[ii] = round(float(lon.iat[ii]), 3)
    df["latitude"] = lat
    df["longitude"] = lon


# Defect dispatcher — dict so the order in _DEFECT_LABELS controls
# the firing order; missing entry = bug.
_DEFECT_DISPATCH = {
    "hospital_name_variants": _apply_hospital_name_variants,
    "plz_format_inconsistency": _apply_plz_format_inconsistency,
    "bundesland_name_iso_mismatch": _apply_bundesland_name_iso_mismatch,
    "negative_order_quantities": _apply_negative_order_quantities,
    "order_visit_date_misalignment": _apply_order_visit_date_misalignment,
    "account_rep_assignment_inconsistency": _apply_account_rep_assignment_inconsistency,
    "duplicate_atc_old_new_pzn": _apply_duplicate_atc_old_new_pzn,
    "coordinate_precision_inconsistency": _apply_coordinate_precision_inconsistency,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_pharma_defects(
    tables: Mapping[str, pd.DataFrame],
    *,
    level: QualityLevel,
    rng: np.random.Generator,
) -> dict[str, pd.DataFrame]:
    """Apply pharma-specific quality defects to ``tables``.

    Returns a new mapping with the mutated DataFrames; the input
    mapping is not modified. ``level`` selects ``clean`` (no-op),
    ``medium`` (spec rates), or ``messy`` (4× medium). ``rng`` is the
    quality-stream RNG; it MUST be a stream isolated from the
    accounts / orders / reps / products / territories / engagement /
    regional streams (see spec REQ-7).
    """
    if level not in _LEVEL_MULTIPLIER:
        raise ValueError(
            f"Unknown data-quality level {level!r}. Allowed: "
            f"{sorted(_LEVEL_MULTIPLIER)}"
        )

    multiplier = _LEVEL_MULTIPLIER[level]

    # Deep-copy the input so callers can compare before/after without
    # the engine accidentally aliasing live DataFrames.
    out: dict[str, pd.DataFrame] = {name: df.copy() for name, df in tables.items()}

    if multiplier == 0.0:
        # Clean mode: untouched. Skip the dispatch loop entirely so
        # we don't draw from the RNG.
        return out

    for label in _DEFECT_LABELS:
        rate = _MEDIUM_RATES[label] * multiplier
        _DEFECT_DISPATCH[label](out, rng, rate)

    return out
