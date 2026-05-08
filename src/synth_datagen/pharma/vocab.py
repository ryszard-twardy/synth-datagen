"""German-pharma vocabulary helpers — leaf module consumed by the
pharma engine.

Three areas, each with module-level data + a small generator:

1. **PZN8** — Pharma-Zentralnummer, 8-digit form (BfArM, 2013).
   ``generate_pzn(rng)`` yields a checksum-valid string.
2. **Hospital names** — German naming conventions (Klinikum X /
   Universitätsklinikum Y / Asklepios Klinik Z / …).
   ``generate_hospital_name(rng, is_university=...)``.
3. **ATC codes** — WHO Anatomical Therapeutic Chemical level-5 codes,
   restricted to anatomical groups documented in the pharma spec
   (A, B, J, L, N, S, D, R). ``generate_atc_code(rng, primary=...)``.

All generators consume an ``np.random.Generator`` argument so the
caller controls the stream — the engine wires this up so each table
draws from its own ``.spawn()``-isolated stream and adding a new
generator can't shift other tables' bytes.

The German city table and the ATC code catalog are public-domain
information (WHO ATC, Wikipedia city list); no copyright notice
needed but the choice of subset is project-curated.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# German city table — public-domain Wikipedia top-cities list, manually
# curated to ~75 entries spanning all 16 Bundesländer for reasonable
# geographic spread. Used both as the trailing token in hospital names
# ("Klinikum {city}") and as a source of place-of-Saint suffixes.
# ---------------------------------------------------------------------------

GERMAN_CITIES: tuple[str, ...] = (
    "Berlin",
    "Hamburg",
    "München",
    "Köln",
    "Frankfurt",
    "Stuttgart",
    "Düsseldorf",
    "Leipzig",
    "Dortmund",
    "Essen",
    "Bremen",
    "Dresden",
    "Hannover",
    "Nürnberg",
    "Duisburg",
    "Bochum",
    "Wuppertal",
    "Bielefeld",
    "Bonn",
    "Münster",
    "Karlsruhe",
    "Mannheim",
    "Augsburg",
    "Wiesbaden",
    "Mönchengladbach",
    "Gelsenkirchen",
    "Braunschweig",
    "Chemnitz",
    "Kiel",
    "Aachen",
    "Halle",
    "Magdeburg",
    "Freiburg",
    "Krefeld",
    "Lübeck",
    "Mainz",
    "Erfurt",
    "Oberhausen",
    "Rostock",
    "Kassel",
    "Hagen",
    "Saarbrücken",
    "Hamm",
    "Mülheim",
    "Potsdam",
    "Ludwigshafen",
    "Oldenburg",
    "Leverkusen",
    "Osnabrück",
    "Heidelberg",
    "Solingen",
    "Darmstadt",
    "Herne",
    "Regensburg",
    "Neuss",
    "Paderborn",
    "Würzburg",
    "Ingolstadt",
    "Heilbronn",
    "Ulm",
    "Göttingen",
    "Wolfsburg",
    "Pforzheim",
    "Offenbach",
    "Bottrop",
    "Reutlingen",
    "Bremerhaven",
    "Koblenz",
    "Recklinghausen",
    "Bergisch Gladbach",
    "Erlangen",
    "Trier",
    "Jena",
    "Salzgitter",
    "Siegen",
    "Cottbus",
    "Hildesheim",
)


# ---------------------------------------------------------------------------
# Hospital-name templates. The engine asks for a name; vocab picks one
# of these patterns at random (uniformly for now; the engine can weight
# later if needed). University-flagged calls always go through the
# Universitätsklinikum pattern so the engine can pin the ~35
# Universitätskliniken regardless of the random draw.
# ---------------------------------------------------------------------------

_HOSPITAL_TEMPLATES: tuple[str, ...] = (
    "Klinikum {city}",
    "Krankenhaus {city}",
    "Klinik {city}",
    "St. Marien Klinikum {city}",
    "St. Josef Krankenhaus {city}",
    "Sankt Anna Klinik {city}",
    "Asklepios Klinik {city}",
    "Helios Klinikum {city}",
)

_UNIVERSITY_TEMPLATE = "Universitätsklinikum {city}"


def generate_hospital_name(
    rng: np.random.Generator, *, is_university: bool = False
) -> str:
    """Return a realistic German hospital name."""
    city = str(rng.choice(GERMAN_CITIES))
    if is_university:
        return _UNIVERSITY_TEMPLATE.format(city=city)
    template = str(rng.choice(_HOSPITAL_TEMPLATES))
    return template.format(city=city)


# ---------------------------------------------------------------------------
# PZN8 (Pharma-Zentralnummer, 8-digit form)
# ---------------------------------------------------------------------------
#
# Algorithm (BfArM): for the 7 leading digits d0..d6, the check digit
# c = sum(d_i * (i+1) for i in 0..6) mod 11. If c == 10 the PZN is
# unrepresentable and not assigned — we re-roll the leading digits in
# that case.
#
# Search space: 10^7 = 10,000,000 leading-digit combinations,
# minus ~10% rejected (c == 10) ≈ 8.18M valid PZNs. Plenty of room
# for the synthetic catalog (20-30 PZNs per run).


def _pzn_check_digit(leading_digits: list[int]) -> int:
    """Return ``c`` per BfArM, or 10 if the PZN would be invalid."""
    return sum(d * (i + 1) for i, d in enumerate(leading_digits)) % 11


def generate_pzn(rng: np.random.Generator) -> str:
    """Return a checksum-valid 8-digit PZN string.

    Re-rolls when the random leading-digits combo would require check
    digit 10 (which is unrepresentable, so the PZN would not be
    assigned by BfArM). Worst-case loop iterations are bounded by the
    ~10% reject rate — uncommon to need more than 2 tries.
    """
    while True:
        leading = [int(d) for d in rng.integers(0, 10, size=7)]
        check = _pzn_check_digit(leading)
        if check != 10:
            return "".join(str(d) for d in leading) + str(check)


# ---------------------------------------------------------------------------
# ATC catalog — WHO Anatomical Therapeutic Chemical level-5 codes.
# Curated subset spanning the 8 documented anatomical groups in the
# Phase 6 spec. WHO ATC is public-domain information; the choice of
# 5–6 codes per group is project-curated to give the engine a
# realistic-looking pharma-line spread without bloating the module.
# ---------------------------------------------------------------------------

ATC_CATALOG: dict[str, tuple[str, ...]] = {
    # A — alimentary tract & metabolism
    "A": (
        "A02BC01",  # omeprazole
        "A02BC02",  # pantoprazole
        "A10BA02",  # metformin
        "A10BJ02",  # liraglutide
        "A11CC04",  # cholecalciferol
    ),
    # B — blood & blood-forming organs
    "B": (
        "B01AC06",  # acetylsalicylic acid (low-dose)
        "B01AF02",  # apixaban
        "B01AF01",  # rivaroxaban
        "B03BA01",  # cyanocobalamin
        "B05BA10",  # parenteral nutrition
    ),
    # J — anti-infectives for systemic use (acute-care heavy)
    "J": (
        "J01CA04",  # amoxicillin
        "J01DC02",  # cefuroxime
        "J01DD04",  # ceftriaxone
        "J01XA01",  # vancomycin
        "J05AB14",  # valganciclovir
        "J07BB02",  # influenza vaccine
    ),
    # L — antineoplastic + immunomodulating (specialty-care heavy)
    "L": (
        "L01XC02",  # rituximab
        "L01XC07",  # bevacizumab
        "L01XE26",  # cabozantinib
        "L01FF02",  # pembrolizumab
        "L04AB01",  # etanercept
        "L04AB02",  # infliximab
    ),
    # N — nervous system
    "N": (
        "N02BE01",  # paracetamol
        "N02AA01",  # morphine
        "N03AX12",  # gabapentin
        "N06AB04",  # citalopram
        "N06AB10",  # escitalopram
    ),
    # S — sensory organs (S01 ophthalmology = specialty-care primary)
    "S": (
        "S01EE04",  # travoprost
        "S01EE03",  # bimatoprost
        "S01LA04",  # ranibizumab
        "S01LA05",  # aflibercept
    ),
    # D — dermatologicals
    "D": (
        "D05AX02",  # calcipotriol
        "D07AC01",  # betamethasone
        "D11AH01",  # tacrolimus topical
        "D11AH05",  # crisaborole
    ),
    # R — respiratory
    "R": (
        "R03AC02",  # salbutamol
        "R03AC13",  # formoterol
        "R03DC03",  # montelukast
        "R03BB04",  # tiotropium
    ),
}


def generate_atc_code(rng: np.random.Generator, *, primary: str | None = None) -> str:
    """Return a single WHO ATC level-5 code.

    When ``primary`` is given, return a code that starts with that
    prefix. ``primary`` must be either a full anatomical group letter
    (e.g. ``'L'``) or a 3-character sub-group (e.g. ``'L01'``); other
    forms raise ``ValueError`` so a typo in ``--primary-atc`` surfaces
    here, not as silently-mismatched output.
    """
    if primary is None:
        # Uniform draw across the 8 anatomical groups.
        group = str(rng.choice(list(ATC_CATALOG.keys())))
        return str(rng.choice(ATC_CATALOG[group]))

    if len(primary) == 1 and primary in ATC_CATALOG:
        candidates = ATC_CATALOG[primary]
        return str(rng.choice(candidates))
    if len(primary) == 3 and primary[0] in ATC_CATALOG:
        candidates = tuple(c for c in ATC_CATALOG[primary[0]] if c.startswith(primary))
        if not candidates:
            raise ValueError(
                f"primary={primary!r} matches no codes in ATC_CATALOG. "
                f"Available {primary[0]}-group codes: {ATC_CATALOG[primary[0]]}"
            )
        return str(rng.choice(candidates))
    raise ValueError(
        f"primary={primary!r} is not a recognised ATC anatomical group "
        f"or 3-character sub-group prefix. Allowed groups: "
        f"{sorted(ATC_CATALOG.keys())}."
    )
