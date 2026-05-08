"""Pharma scenario benchmark constants — single source of truth.

Every numeric parameter used by the pharma engine MUST be derived from a
constant defined here. Each constant carries an inline comment naming
the public source. Re-validate annually against the latest DESTATIS,
PHAGRO, IQVIA, vfa, and Pharmalotse releases — this is a curated subset,
not an exhaustive copy.

Style: module-level UPPER_SNAKE constants only. Scalars (int/float/str)
only — no lists, no dicts, no dataclasses. Anything richer goes into a
dedicated module (e.g. ``pharma.vocab`` for ATC code tables).

Tests in ``tests/pharma/test_benchmarks.py`` enforce internal
relationships (subtypes summing to totals, share fractions in [0, 1],
ordering constraints) so a typo surfaces here, not three commits later
in a downstream realism check.

Spec reference: prompts/pharma/05_implementation.md REQ-8.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# DESTATIS Krankenhausstatistik 2023 (KHStatV)
# Source: https://www.destatis.de/DE/Themes/Society-Environment/Health/Hospitals/
# ---------------------------------------------------------------------------

#: Total hospitals in Germany (DESTATIS 2023). Sum of acute-care +
#: psychiatric + day-surgery hospitals.
TOTAL_HOSPITALS_DE: int = 1874

#: Acute-care (somatic) hospitals only — exclude psychiatric and
#: day-surgery facilities.
ACUTE_CARE_HOSPITALS_DE: int = 1585

#: Psychiatric hospitals (Psychiatrische Krankenhäuser).
PSYCHIATRIC_HOSPITALS_DE: int = 279

#: Day-surgery hospitals (Tageskliniken).
DAY_SURGERY_HOSPITALS_DE: int = 61

#: University hospitals (Universitätskliniken). DESTATIS publishes
#: exactly 35 — these are flagged in the engine as
#: ``account_archetype='University'`` and command 8–12 % of total
#: revenue despite being <2 % of accounts.
UNIVERSITY_HOSPITALS_DE: int = 35

#: Total acute-care hospital beds (DESTATIS 2023).
TOTAL_HOSPITAL_BEDS_DE: int = 476_900

#: Average bed count, public hospitals (DESTATIS 2023). Public hospitals
#: are noticeably larger than private ones — driver of the bimodal
#: bed-count distribution the engine reproduces.
AVG_BEDS_PUBLIC_HOSPITAL: int = 433

#: Average bed count, private hospitals (DESTATIS 2023, weighted
#: across non-profit and for-profit ownership).
AVG_BEDS_PRIVATE_HOSPITAL: int = 132

#: Hospitals owned by the public sector (Bundesländer / Kommunen /
#: Bund). DESTATIS 2023, Federal Hospital Atlas 2024.
PCT_HOSPITALS_PUBLIC: float = 0.35  # 552 / 1585 acute-care hospitals

#: Non-profit hospital ownership share (church/charity foundations).
PCT_HOSPITALS_NONPROFIT: float = 0.33  # 525 / 1585 (rounded)

#: For-profit hospital ownership share (private companies).
PCT_HOSPITALS_FORPROFIT: float = 0.32  # 508 / 1585 (rounded)


# ---------------------------------------------------------------------------
# PHAGRO Zahlen-Daten-Fakten 2024 — wholesale-market reality
# Source: https://www.phagro.de/zahlen-daten-fakten/
# ---------------------------------------------------------------------------

#: Total pharmaceutical wholesale revenue in Germany, 2024 (PHAGRO).
#: The synthetic MediCorp dataset represents one manufacturer of many —
#: per-account revenue calibration aims for €80M–€150M total, well
#: under 0.5 % of this number.
TOTAL_WHOLESALE_REVENUE_DE_2024: float = 42.5e9  # EUR

#: Share of wholesale that is prescription-only (Rx) drugs (PHAGRO).
PCT_RX_OF_WHOLESALE: float = 0.85

#: Regulated wholesale margin cap, 2.8 % on average (PHAGRO). This is
#: the *wholesale* margin, NOT the manufacturer margin the engine uses
#: for ``products.margin_pct`` — wholesale margins are systematically
#: tighter than manufacturer margins and the dataset is from the
#: manufacturer perspective.
WHOLESALE_MARGIN_AVG_PCT: float = 0.028


# ---------------------------------------------------------------------------
# IQVIA Marktbericht Classic 2022
# Source: https://www.iqvia.com/-/media/iqvia/pdfs/germany/library/publications/
# ---------------------------------------------------------------------------

#: Hospital pharma channel revenue, Germany 2022 (IQVIA DKM).
HOSPITAL_PHARMA_REVENUE_DE_2022: float = 6.3e9  # EUR

#: Retail pharma channel revenue, Germany 2022 (IQVIA PharmaScope).
RETAIL_PHARMA_REVENUE_DE_2022: float = 40.3e9  # EUR


# ---------------------------------------------------------------------------
# vfa Innovationsbilanz 2024 + Biotech-Report 2025
# Sources:
#   https://www.vfa.de/de/forschung-entwicklung/meilensteine-und-neueinfuehrungen
#   https://www.vfa.de/download/biotech-report-2025.pdf
# ---------------------------------------------------------------------------

#: New active substances launched in Germany, 2024 (vfa). Used to
#: calibrate the ~5 % "innovation" flag on the products catalog
#: (products launched in the last 24 months).
NEW_ACTIVE_SUBSTANCES_2024: int = 43

#: Biopharmaceutical market share, oncology (vfa Biotech-Report 2025).
#: Specialty-care sub-mode picks oncology by default for the dominant
#: ATC group (L01).
BIOPHARMA_SHARE_ONCOLOGY: float = 0.32

#: Biopharmaceutical market share, immunology (vfa).
BIOPHARMA_SHARE_IMMUNOLOGY: float = 0.28

#: Biopharmaceutical market share, hematology (vfa).
BIOPHARMA_SHARE_HEMATOLOGY: float = 0.23

#: Biopharmaceutical market share, central nervous system (vfa).
BIOPHARMA_SHARE_CNS: float = 0.19


# ---------------------------------------------------------------------------
# German pharma field-force size
# Source: Grosch & Partners "Pharmaaußendienst 2020" analysis
# ---------------------------------------------------------------------------

#: Historical peak pharma field-force headcount in Germany. The
#: contraction from ~22k to ~12k over the 2010s is a real industry
#: dynamic (consolidation, KOL targeting) and shows up in the rep
#: tenure distribution the engine reproduces.
PHARMA_REPS_PEAK: int = 22_000

#: Current pharma field-force headcount, Germany.
PHARMA_REPS_CURRENT: int = 12_000


# ---------------------------------------------------------------------------
# Pharmalotse "Berufsbild Pharmareferent" — daily visit benchmarks
# Source: https://www.pharmalotse.de/berufsbild-pharmareferent/
# ---------------------------------------------------------------------------

#: Average doctor visits per rep per working day (Pharmalotse).
AVG_DOCTOR_VISITS_PER_DAY: int = 8

#: Average pharmacy visits per rep per working day (Pharmalotse).
AVG_PHARMACY_VISITS_PER_DAY: int = 1

#: Practical maximum doctor visits per rep per day before quality
#: degrades (Pharmalotse).
MAX_DOCTOR_VISITS_PER_DAY: int = 10
