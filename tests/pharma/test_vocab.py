"""Tests for ``synth_datagen.pharma.vocab``.

Vocab is leaf-level: pure-data tables (German cities, ATC codes,
hospital-name templates) plus three tiny generators
(``generate_pzn``, ``generate_hospital_name``, ``generate_atc_code``)
that the engine consumes downstream.

PZN8 (Pharma-Zentralnummer, 8-digit form, BfArM) is the German
prescription-drug identifier introduced in 2013. The 8th digit is a
check digit: ``c = sum(d_i * (i+1) for i in 0..6) mod 11``. If ``c
== 10`` the PZN is invalid and must be re-rolled.

The hospital-name generator must NEVER produce strings matching
"Hospital ###" or "Test ..." patterns — those would betray the
synthetic-data fingerprint the spec REQs forbid.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from synth_datagen.pharma import vocab


# ---------------------------------------------------------------------------
# PZN8 — checksum-validated 8-digit identifier
# ---------------------------------------------------------------------------


def test_pzn_is_eight_digits() -> None:
    rng = np.random.default_rng(42)
    pzn = vocab.generate_pzn(rng)
    assert isinstance(pzn, str)
    assert len(pzn) == 8
    assert pzn.isdigit()


def test_pzn_checksum_valid_official_algorithm() -> None:
    """Re-implement the published PZN8 algorithm and assert that every
    PZN we generate satisfies it. Catches transposed-weight bugs.

    Algorithm (BfArM): for the 7 leading digits d0..d6, compute
    ``c = sum(d_i * (i+1) for i in 0..6) mod 11``. The 8th digit
    of a valid PZN equals c. ``c == 10`` is unrepresentable → such
    PZNs are not assigned.
    """
    rng = np.random.default_rng(123)
    for _ in range(200):
        pzn = vocab.generate_pzn(rng)
        digits = [int(d) for d in pzn]
        leading = digits[:7]
        check = digits[7]
        expected = sum(d * (i + 1) for i, d in enumerate(leading)) % 11
        assert expected != 10, f"Invalid PZN {pzn!r} (check digit slot would be 10)"
        assert check == expected, (
            f"PZN {pzn!r}: expected check digit {expected}, got {check}"
        )


def test_pzn_uniqueness_at_scale() -> None:
    """1000 PZNs from one seed should be unique. With 8.18M valid
    8-digit PZNs (10^7 minus the ~10% rejected by checksum-10), the
    birthday-collision probability over 1000 draws is well under
    0.1 %. A duplicate here is a generator bug, not bad luck."""
    rng = np.random.default_rng(2026)
    pzns = [vocab.generate_pzn(rng) for _ in range(1000)]
    assert len(set(pzns)) == len(pzns)


def test_pzn_deterministic_under_seed() -> None:
    """Same seed → same sequence. Required for the engine's
    bit-stable output guarantee."""
    rng_a = np.random.default_rng(7)
    rng_b = np.random.default_rng(7)
    a = [vocab.generate_pzn(rng_a) for _ in range(50)]
    b = [vocab.generate_pzn(rng_b) for _ in range(50)]
    assert a == b


# ---------------------------------------------------------------------------
# Hospital names
# ---------------------------------------------------------------------------


def test_hospital_name_matches_german_template() -> None:
    """Names must follow one of a small set of German templates
    documented in the module. No 'Hospital 001' / 'Test Clinic' / any
    English-only output."""
    rng = np.random.default_rng(42)
    forbidden = re.compile(r"\b(Hospital|Test|Generic|Sample)\b")
    for _ in range(100):
        name = vocab.generate_hospital_name(rng)
        assert isinstance(name, str)
        assert name, "hospital name must be non-empty"
        assert not forbidden.search(name), (
            f"Hospital name {name!r} contains forbidden English token"
        )


def test_hospital_name_uses_one_of_documented_prefixes() -> None:
    """Spec REQ: names look like 'Klinikum Stadt', 'Universitätsklinikum
    Stadt', 'Krankenhaus Stadt', 'Klinik Saint Stadt', etc. Pin the
    set of opening words so the engine can't accidentally pick up
    English-leaking templates."""
    rng = np.random.default_rng(99)
    documented_prefixes = {
        "Klinikum",
        "Universitätsklinikum",
        "Krankenhaus",
        "Klinik",
        "St.",
        "Sankt",
        "Asklepios",
        "Helios",
    }
    for _ in range(200):
        name = vocab.generate_hospital_name(rng)
        first = name.split()[0]
        assert first in documented_prefixes, (
            f"Hospital name starts with unknown prefix: {first!r} (full: {name!r})"
        )


def test_hospital_name_university_template_when_flagged() -> None:
    """``generate_hospital_name(rng, is_university=True)`` must always
    produce a Universitätsklinikum name — for the ~35 university
    hospitals the engine flags as ``account_archetype='University'``."""
    rng = np.random.default_rng(0)
    for _ in range(20):
        name = vocab.generate_hospital_name(rng, is_university=True)
        assert name.startswith("Universitätsklinikum"), (
            f"University-flagged name must start with "
            f"'Universitätsklinikum', got {name!r}"
        )


def test_hospital_name_deterministic_under_seed() -> None:
    rng_a = np.random.default_rng(1)
    rng_b = np.random.default_rng(1)
    a = [vocab.generate_hospital_name(rng_a) for _ in range(20)]
    b = [vocab.generate_hospital_name(rng_b) for _ in range(20)]
    assert a == b


def test_hospital_name_uses_german_city_list() -> None:
    """At least one of the documented German cities must appear in
    the generated name (sanity check that the city table was loaded
    and used)."""
    rng = np.random.default_rng(11)
    sample = [vocab.generate_hospital_name(rng) for _ in range(30)]
    cities = vocab.GERMAN_CITIES
    matched = any(any(city in name for city in cities) for name in sample)
    assert matched, "no generated hospital name contained a German city"


# ---------------------------------------------------------------------------
# ATC codes
# ---------------------------------------------------------------------------


def test_atc_code_format_matches_who_pattern() -> None:
    """WHO ATC: ``[A-Z]\\d{2}[A-Z]{2}\\d{2}`` (level-5, 7 chars)."""
    rng = np.random.default_rng(42)
    pat = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
    for _ in range(100):
        code = vocab.generate_atc_code(rng)
        assert pat.match(code), f"ATC code {code!r} doesn't match WHO format"


def test_atc_code_within_documented_groups() -> None:
    """The pharma engine restricts to ATC anatomical groups
    documented in the spec: A (alimentary tract), B (blood),
    J (anti-infectives), L (antineoplastic + immunomodulating),
    N (nervous system), S (sensory), D (dermatologicals), R
    (respiratory)."""
    rng = np.random.default_rng(42)
    documented_anatomicals = set("ABJLNSDR")
    for _ in range(100):
        code = vocab.generate_atc_code(rng)
        assert code[0] in documented_anatomicals, (
            f"ATC code {code!r} starts with anatomical group {code[0]!r} "
            "outside the documented set"
        )


def test_atc_code_primary_group_filter() -> None:
    """When the engine picks a primary group for specialty-care
    (e.g. ``L01`` for oncology), passing ``primary='L01'`` must make
    every returned code start with that prefix."""
    rng = np.random.default_rng(42)
    for _ in range(50):
        code = vocab.generate_atc_code(rng, primary="L01")
        assert code.startswith("L01"), f"primary='L01' but got {code!r}"


def test_atc_code_unknown_primary_raises() -> None:
    """Typos in ``--primary-atc`` must surface here, not as a
    silently-mismatched primary."""
    rng = np.random.default_rng(42)
    with pytest.raises(ValueError, match="primary|atc"):
        vocab.generate_atc_code(rng, primary="ZZ99")


def test_atc_code_single_letter_primary_returns_in_group() -> None:
    """``primary='J'`` (just the anatomical group letter) returns any
    code in that group — used by acute-care to weight toward J / L /
    N / B without pinning a sub-group."""
    rng = np.random.default_rng(2026)
    for _ in range(50):
        code = vocab.generate_atc_code(rng, primary="J")
        assert code.startswith("J"), f"primary='J' but got {code!r}"


def test_atc_code_three_char_primary_with_no_matches_raises() -> None:
    """Edge case: ``primary='J99'`` — J is a valid group but no J99-
    prefixed code exists in the catalog. Must raise with a clear
    message naming the group, not silently fall back to a different
    sub-group."""
    rng = np.random.default_rng(42)
    with pytest.raises(ValueError, match="matches no codes"):
        vocab.generate_atc_code(rng, primary="J99")


def test_atc_code_deterministic_under_seed() -> None:
    rng_a = np.random.default_rng(5)
    rng_b = np.random.default_rng(5)
    a = [vocab.generate_atc_code(rng_a) for _ in range(30)]
    b = [vocab.generate_atc_code(rng_b) for _ in range(30)]
    assert a == b


# ---------------------------------------------------------------------------
# Module-level data hygiene
# ---------------------------------------------------------------------------


def test_german_cities_table_nonempty_and_strings() -> None:
    assert isinstance(vocab.GERMAN_CITIES, tuple)
    assert len(vocab.GERMAN_CITIES) >= 50
    assert all(isinstance(c, str) and c for c in vocab.GERMAN_CITIES)


def test_atc_catalog_keys_match_documented_groups() -> None:
    """The ATC catalog (used by ``generate_atc_code``) must enumerate
    only the 8 documented anatomical groups. Adding a new group
    should be a deliberate edit, not a slip."""
    documented = set("ABJLNSDR")
    assert set(vocab.ATC_CATALOG.keys()) <= documented


def test_atc_catalog_codes_are_valid_format() -> None:
    """Every code in the catalog must be a valid 7-char level-5 ATC."""
    pat = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
    flat = [code for codes in vocab.ATC_CATALOG.values() for code in codes]
    assert flat, "ATC catalog appears empty"
    for code in flat:
        assert pat.match(code), f"Catalog entry {code!r} has bad format"


def test_atc_catalog_codes_unique() -> None:
    flat = [code for codes in vocab.ATC_CATALOG.values() for code in codes]
    assert len(set(flat)) == len(flat), "duplicate ATC codes in catalog"
