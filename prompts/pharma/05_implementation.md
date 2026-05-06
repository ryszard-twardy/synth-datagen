# Coding Agent Prompt: Extend synth-datagen with Production-Grade Pharma Field Sales Scenario

> **How to use this prompt:** This prompt is the implementation guide for adding the Pharma scenario to `synth-datagen` AFTER the audit/refactor (Phases 1–4 of `synth_datagen_audit_workflow.md`) is complete AND the SaaS scenario extension is implemented. Companion document: `synth_datagen_pharma_integration_notes.md` (architecture fit). Read both before pasting this prompt into Claude Code.

> **Prerequisites:** synth-datagen v0.2.0 tag exists, refactor is complete, SaaS PLG and Vertical sub-modes are live, OSM snapshot CSV is in the gis-territory-optimization repo, BKG VG250 GeoJSONs are downloaded.

---

```
## ROLE

You are a senior data engineer and synthetic data architect with deep expertise in:
- German pharmaceutical market structure (acute care vs specialty care, wholesale economics, AMNOG/GKV reimbursement)
- Geospatial data engineering (spatial joins, hierarchical admin codes, density modeling)
- Industry-realistic data generation calibrated to public benchmarks (DESTATIS, PHAGRO, vfa, IQVIA)
- Statistical distribution modeling (Beta, Pareto, log-normal, Gamma, Weibull)
- Reproducible RNG architecture with isolated stream seeding (XOR salt + spawn pattern)
- Python data engineering: pandas, numpy, geopandas, shapely, dataclasses, type hints, pytest

You are extending an existing CLI tool (`synth-datagen`) — NOT writing from scratch. The tool already supports retail, SaaS (with PLG and Vertical sub-modes), fintech, and logistics scenarios with configurable data quality injection and automatic documentation output. Your job is to add a Pharma Field Sales scenario that produces data realistic enough to back a portfolio dashboard (Project 7: GIS Territory Optimization for fictional company "MediCorp") AND is reusable for future pharma-market portfolio projects.

## CONTEXT

### The user
The user (Ryszard) is building a data analytics portfolio targeting EU data analyst / BI analyst roles. He has an existing `synth-datagen` Python CLI tool, recently refactored to a clean src layout with Pydantic v2 config, src/synth_datagen/scenarios/ Protocol-based scenario interface, isolated RNG streams, and benchmark-calibrated distributions. Existing scenarios:
- retail (used by Kupferkanne project — Project 1)
- saas with sub-modes plg-usage-based (used by Project 2 Promptforge) and vertical-account-based (used by Project 14 RFEDA)
- fintech, logistics

### The consumer project

**Project 7 — GIS Territory Sales Optimization (MediCorp mock company):**
- 7-page Power BI dashboard with: Territory Command Center, Bundesland Coverage Map, Landkreis Coverage Gaps, Rep Workload Balance, Channel Imbalance, Realignment Scenario, Account Drillthrough
- PostGIS spatial analysis at TWO administrative levels (16 Bundesländer + ~401 Landkreise)
- K-Means territory clustering with revenue weighting
- Coverage gap analysis at Landkreis level (revenue at risk by underserved district)
- Acute care vs specialty care channel comparison

The Pharma scenario must support BOTH sub-modes (acute-care + specialty-care) so the dashboard can compare channel imbalance — this is the unique narrative that distinguishes this dashboard from generic territory analyses.

### External data dependencies (NOT fetched by synth-datagen — passed as input parameters)

The Pharma scenario takes THREE external data inputs as Pydantic-validated file paths. It does NOT fetch from any API at runtime. This is a deliberate architectural constraint to keep synth-datagen a pure data generator.

1. **OSM hospital snapshot** (`--hospitals-csv`): A CSV committed to the consumer's repo (e.g., `data/osm_hospitals_germany_20260601.csv`). Required schema documented in `synth_datagen_pharma_integration_notes.md` Section 4.

2. **BKG Bundesländer GeoJSON** (`--bkg-bundeslaender`): The VG250 LAN file from gdz.bkg.bund.de (16 features).

3. **BKG Landkreise GeoJSON** (`--bkg-landkreise`): The VG250 KRS file from gdz.bkg.bund.de (~401 features, with parent AGS in attributes).

The user is responsible for fetching these once and committing them. synth-datagen reads them at generation time.

### Why this matters

The data must NOT have these synthetic-data fingerprints (lessons from prior portfolio attempts):
- Uniform geographic distribution (real German hospital density follows Pareto: München, Hamburg, Berlin metropolitan areas concentrate ~25% of accounts)
- Flat revenue distribution by Landkreis (real revenue concentrates in 20% of districts that hold 80% of high-bed-count hospitals)
- Identical acute and specialty distributions (they have very different geographic and economic dynamics)
- Round numbers in pricing (real PZN-based pricing is irregular due to AMNOG-Erstattungsbetrag negotiations)
- "Test Hospital 001" naming (real hospitals have distinctive German names: "Klinikum der Universität München", "Charité — Universitätsmedizin Berlin", "Asklepios Klinik Altona")

A senior healthcare data analyst should look at the data and say "this looks like real B2B German pharmaceutical sales data" — not "this is clearly synthetic."

## CRITICAL REQUIREMENTS (NON-NEGOTIABLE)

These are HARD requirements. If any fail, the dataset is unusable for the GIS Territory dashboard.

### REQ-1: Geographic Plausibility (Two-level Hierarchical)
The data MUST encode realistic German hospital density:
- Account density per Bundesland correlates with population (Spearman ρ > 0.7 against DESTATIS Bundesland population)
- Account density per Landkreis follows Pareto: top 20% of Landkreise contain 60–70% of accounts (matches DESTATIS hospital distribution data)
- Acute care accounts cluster in urban Landkreise (Kreisfreie Städte, Stadtkreise)
- Specialty care accounts cluster in/near major cities AND in medical hub Bundesländer (Bayern, NRW, Baden-Württemberg)
- ALL accounts must have valid `bundesland_ags` (2-digit) and `landkreis_ags` (5-digit), with `landkreis_ags[:2] == bundesland_ags` (hierarchy invariant)
- No Landkreis with 0 hospitals AND >500K population (data error if this happens)

**Sources:** DESTATIS Krankenhausstatistik (KHStatV), Federal Hospital Atlas 2024, BKG VG250 population data.

### REQ-2: Account Type Distribution Matches Reality
Account type breakdown must match published German hospital data:
- **Acute-care sub-mode:** ~91% Krankenhäuser (Hospital), ~9% other acute facilities. Out of hospitals: ~35% public ownership, ~33% private not-for-profit, ~32% private for-profit (DESTATIS 2023)
- **Specialty-care sub-mode:** Mix of: ~50% specialty clinics (Fachkliniken), ~30% medical care centers (MVZ), ~20% outpatient specialist groups
- **Bed count distribution (acute-care):** Log-normal, mean=145, sigma=0.85 — matches DESTATIS average (public hospitals avg 433 beds, private avg 132 beds; weighted average ~250 in hospital sector but skewed by long tail of small facilities)
- **University hospitals (Universitätskliniken):** Exactly 35 in Germany (DESTATIS), should be flagged with `account_archetype='University'` and command 8–12% of total revenue (despite being <2% of accounts)

**Sources:** DESTATIS Krankenhausstatistik 2023, Federal Hospital Atlas (Bundes-Klinik-Atlas) April 2025.

### REQ-3: Revenue Realism (Anchored to IQVIA/PHAGRO Benchmarks)
Generated revenue must be plausible relative to public benchmarks:
- **Total wholesale market:** PHAGRO 2024 = €42.5 billion. The synthetic MediCorp company is one of many manufacturers; revenue should be calibrated as a small market share (e.g., €80M–€150M annual revenue total across all accounts)
- **Hospital pharma channel:** IQVIA DKM 2022 = €6.3 billion (≈14% of total). Acute-care sub-mode revenue should split realistically into hospital channel
- **Specialty channel:** Higher-margin, higher per-account (specialty drugs are expensive)
- **Average revenue per account:**
  - Acute-care: log-normal mean=€95,000/year, sigma=1.15 (long tail — university hospitals can spend €1M+/year on a single product line)
  - Specialty-care: log-normal mean=€18,000/year, sigma=0.95
- **Margin %:** Generic products 4–8%, branded products 12–25%, specialty products 25–45%. Note: regulated wholesale margin is 2.8% on average (PHAGRO) — this is wholesale, not manufacturer. The synthetic data is from manufacturer perspective, so use the higher manufacturer margins.

**Sources:** PHAGRO Zahlen-Daten-Fakten 2024, IQVIA Marktbericht Classic 2022, vfa Arzneimittelmarkt in 10 Zahlen 2025.

### REQ-4: Sales Force Productivity (German Field Force Reality)
Rep productivity must match German pharma field force benchmarks:
- **Account-to-rep ratio:**
  - Acute-care: ~20 accounts per rep (40 reps, ~800 accounts)
  - Specialty-care: ~30 accounts per rep (60 reps, ~1,800 accounts) — slightly higher because visits are shorter
- **Visit frequency per account per year:**
  - Acute-care: 3–6 visits/year per account (Beta distribution α=2, β=3 over the range)
  - Specialty-care: 8–14 visits/year per account (Beta α=2.5, β=2.5)
- **Rep tenure:** Log-normal mean=4.2 years, sigma=0.9 (Pharmaceutical industry tenure is moderate; specialty pharma sees higher turnover)
- **Rep home location:** Concentrated in major Bundesländer (50% in BY+NW+BW, matching where 50% of pharma jobs are per Pharmalotse data)

**Sources:** Pharmalotse "Berufsbild Pharmareferent" (8 doctor visits + 1 pharmacy daily benchmark; rep numbers down from peak 22,000 to ~12,000 today), McKinsey "Death of a sales model — or not?" (territory benchmarks).

### REQ-5: Order Pattern Realism (Frequency × Amount Skew)
Order patterns must encode realistic procurement behavior:
- **Acute-care orders:**
  - Frequency: Log-normal mean=18 orders/account/year, sigma=0.7 (~monthly bulk orders)
  - Amount: Log-normal mean=€450/order line, sigma=1.4 (high variance — bulk vs replenishment)
  - Concentration: Top 20% of accounts (by revenue) account for 65–70% of orders (Pareto)
- **Specialty-care orders:**
  - Frequency: Log-normal mean=42 orders/account/year, sigma=0.6 (more frequent, smaller)
  - Amount: Log-normal mean=€180/order line, sigma=1.1
  - Concentration: Top 20% of accounts → 55–60% of orders
- **Seasonality:** Monthly volume index 0.85–1.15 with peak in October–December (typical pharma annual budget closeout) and trough in August (vacation period)
- **Day-of-week:** Mon–Thu peak, Friday lower (pharmacy ordering patterns)

**Sources:** PHAGRO Zahlen-Daten-Fakten (high-priced drug volume tripled in 10 years), industry tradition.

### REQ-6: Product Catalog (PZN + ATC Realism)
Products must follow German pharmaceutical regulatory structure:
- **PZN (Pharma-Zentralnummer):** 8-digit format (extended from 7-digit in 2013). Generated PZNs must be unique, valid checksum (last digit calculated per PZN algorithm)
- **ATC codes:** Standard WHO ATC classification, 7-character format (e.g., L01XC02 for Rituximab). Distribution by sub-mode:
  - Acute-care products: Cluster in J (anti-infectives), L (antineoplastic + immunomodulating), N (nervous system), B (blood + blood-forming)
  - Specialty-care products: One primary ATC group dominates per generation run (parametrizable: oncology L01, rheumatology L04, ophthalmology S01, etc.)
- **Hospital-only flag (`is_hospital_only`):** ~30% of acute-care products are Klinik-only Rx; 0% for specialty-care (which is mostly outpatient)
- **Innovation indicator:** ~5% of products flagged as launched in last 24 months (matches vfa data: 43 new active substances in 2024)
- **Patent status:** Mix of patent-protected, generic, biosimilar — calibrated to "patent-protected products account for 92% of value but a smaller share of volume" (vfa)

**Sources:** vfa Innovationsbilanz 2024 (43 new substances), vfa Biotech-Report 2025 (Onkologie 32%, Immunologie 28% market share), BfArM PZN registry.

### REQ-7: Reproducibility (Bit-for-Bit Identical Output for Same Seed)
Use the established RNG architecture from `synth_datagen_pharma_integration_notes.md` Section 3. Master salt is `0x5DDA50000` (reads as PHA in hex). Sub-streams via `.spawn()`:

```python
pharma_master = numpy.random.default_rng(seed=base_seed ^ 0x5DDA50000)
streams = pharma_master.spawn(8)
# Order: accounts, reps, territories, orders, products, engagement, quality, regional
```

CRITICAL: Adding a new stream requires extending the spawn count and APPENDING at the end. Inserting in the middle shifts state for downstream streams and breaks backward compatibility. This is enforced by `test_pharma_stream_count_stable`.

### REQ-8: Industry Benchmark Calibration (Source Citation Required)
Every distribution parameter must cite its source in the code. Document in `src/synth_datagen/benchmarks/pharma.py`:

```python
"""Pharma scenario benchmark constants.

All numerical parameters in this module MUST cite their source.
Re-validate annually against the latest reports.
"""

# DESTATIS Krankenhausstatistik 2023 (KHStatV)
# Source: https://www.destatis.de/DE/Themes/Society-Environment/Health/Hospitals/
TOTAL_HOSPITALS_DE = 1874
ACUTE_CARE_HOSPITALS_DE = 1585
PSYCHIATRIC_HOSPITALS_DE = 279
DAY_SURGERY_HOSPITALS_DE = 61
UNIVERSITY_HOSPITALS_DE = 35
TOTAL_HOSPITAL_BEDS_DE = 476_900

# Average bed counts by ownership type (DESTATIS)
AVG_BEDS_PUBLIC_HOSPITAL = 433
AVG_BEDS_PRIVATE_HOSPITAL = 132

# Ownership distribution (DESTATIS, Federal Hospital Atlas 2024)
PCT_HOSPITALS_PUBLIC = 0.35      # 552 / 1585
PCT_HOSPITALS_NONPROFIT = 0.33   # 525 / 1585 (approx)
PCT_HOSPITALS_FORPROFIT = 0.32   # 508 / 1585 (approx)

# PHAGRO 2024 wholesale market
# Source: PHAGRO Zahlen-Daten-Fakten 2024
TOTAL_WHOLESALE_REVENUE_DE_2024 = 42.5e9  # EUR
PCT_RX_OF_WHOLESALE = 0.85
WHOLESALE_MARGIN_AVG_PCT = 0.028  # 2.8%, regulated cap

# IQVIA Marktbericht Classic 2022
# Source: https://www.iqvia.com/-/media/iqvia/pdfs/germany/library/publications/
HOSPITAL_PHARMA_REVENUE_DE_2022 = 6.3e9   # IQVIA DKM
RETAIL_PHARMA_REVENUE_DE_2022 = 40.3e9    # IQVIA PharmaScope

# vfa Innovationsbilanz 2024
# Source: https://www.vfa.de/de/forschung-entwicklung/meilensteine-und-neueinfuehrungen
NEW_ACTIVE_SUBSTANCES_2024 = 43

# vfa Biotech-Report 2025 — biopharmaceuticals market shares
# Source: https://www.vfa.de/download/biotech-report-2025.pdf
BIOPHARMA_SHARE_ONCOLOGY = 0.32
BIOPHARMA_SHARE_IMMUNOLOGY = 0.28
BIOPHARMA_SHARE_HEMATOLOGY = 0.23
BIOPHARMA_SHARE_CNS = 0.19

# German pharma field force size
# Source: Grosch & Partners Pharmaaußendienst 2020 analysis
PHARMA_REPS_PEAK = 22_000        # historical peak
PHARMA_REPS_CURRENT = 12_000     # current estimate

# Daily visit benchmarks
# Source: Pharmalotse Berufsbild Pharmareferent
AVG_DOCTOR_VISITS_PER_DAY = 8
AVG_PHARMACY_VISITS_PER_DAY = 1
MAX_DOCTOR_VISITS_PER_DAY = 10
```

This module is the source of truth for all benchmark constants. Every distribution parameter elsewhere in the pharma scenario MUST import from here.

## SCENARIO ARCHITECTURE

Build the Pharma scenario with TWO sub-modes (mirroring the SaaS pattern). They share `_common.py` (account/geo skeleton) but diverge on order patterns, account types, product catalogs, and rep dynamics.

### Sub-mode A: `acute-care`
For Project 7 GIS Territory Optimization (acute-care channel). Focus on hospital procurement patterns.
- Account universe: hospitals (amenity=hospital) with bed_count ≥ 50
- Account count: 600–900
- Rep count: 35–45 (parametrizable, default 40)
- Average revenue per account: €60K–€180K/year
- Order frequency: monthly bulk
- Sales cycle: long (formulary committee, hospital pharmacy approval)
- Product mix: ATC J, L, N, B dominant
- Decision unit: hospital pharmacy committee

### Sub-mode B: `specialty-care`
For Project 7 specialty channel comparison.
- Account universe: clinics (amenity=clinic) + specialist groups + MVZ
- Account count: 1,500–2,500
- Rep count: 50–70 (parametrizable, default 60)
- Average revenue per account: €8K–€35K/year
- Order frequency: weekly/biweekly
- Sales cycle: short (specialist physician decision)
- Product mix: single primary ATC group (parametrizable: oncology, rheumatology, ophthalmology, dermatology)
- Decision unit: specialist physician

## DATA SCHEMA

The scenario must output 8 tables in CSV format (or Parquet if specified):

### Table 1: `accounts` (600–900 acute / 1,500–2,500 specialty)
- `account_id` (PK)
- `osm_id` (traceability to OSM source row)
- `name` (realistic German hospital/clinic names — NOT "Hospital 001")
- `account_type` ∈ {Hospital, SpecialtyClinic, MVZ, SpecialistGroup}
- `account_archetype` ∈ {University, Maximalversorger, Schwerpunktversorger, Grundversorger, Specialist, MVZ}
- `sub_mode` ∈ {acute-care, specialty-care}
- `bed_count` (NULL for clinics; log-normal-imputed for hospitals if OSM tag missing)
- `specialty_focus` (e.g., 'Onkologie', 'Kardiologie', 'Orthopädie')
- `street`, `city`, `plz` (from OSM, may be NULL — synth-datagen does NOT impute)
- `bundesland_ags` (2-digit, from spatial join — NEVER NULL)
- `landkreis_ags` (5-digit, from spatial join — NEVER NULL; first 2 chars MUST equal bundesland_ags)
- `latitude`, `longitude` (from OSM)
- `ownership_type` ∈ {public, nonprofit, forprofit}
- `annual_revenue` (synthetic, log-normal calibrated to REQ-3)
- `customer_since_date`
- `status` (active, inactive)
- `acquisition_channel` (cold-call, conference, referral, KOL — Pareto-distributed)

### Table 2: `sales_reps` (35–45 acute / 50–70 specialty)
- `rep_id` (PK)
- `name` (realistic German names)
- `sub_mode` (which org)
- `home_city`, `home_plz`
- `home_bundesland_ags`, `home_landkreis_ags`
- `latitude`, `longitude` (home location)
- `territory_id` (FK to territories)
- `hire_date` (log-normal tenure distribution)
- `tenure_years` (computed)

### Table 3: `territories` (12–18 per sub-mode)
- `territory_id` (PK)
- `territory_name` (e.g., "Süd-Bayern", "NRW-Mitte")
- `region` ∈ {Nord, Süd, Ost, West, Mitte}
- `sub_mode`
- `target_revenue` (annual quota)
- `geometry` (WKT or geojson — multipolygon spanning multiple Landkreise initially)

### Table 4: `products` (20–30 acute / 15–25 specialty)
- `product_id` (PK)
- `pzn` (8-digit unique, valid checksum)
- `product_name` (German naming convention: e.g., "Rituximab Sandoz 100 mg/10 ml")
- `atc_code` (7-char WHO ATC)
- `therapy_area` (mapped from ATC)
- `unit_price` (€, calibrated to REQ-3 margin bands)
- `margin_pct` (manufacturer margin, NOT wholesale)
- `is_hospital_only` (Klinik-only Rx flag)
- `launched_date` (5% within last 24 months for innovation indicator)
- `is_generic`, `is_biosimilar` (mutually exclusive booleans)

### Table 5: `orders` (30,000–50,000 per sub-mode, 18–36 months) ⚠️ CRITICAL TABLE
- `order_id` (PK)
- `account_id` (FK)
- `rep_id` (FK — the rep credited with the account at order time)
- `product_id` (FK)
- `order_date`
- `quantity` (integer, log-normal)
- `unit_price` (snapshot at order date)
- `amount` (= quantity × unit_price, with synthetic noise for AMNOG-Rabatt)
- `discount_pct` (negotiated, 0–25%, more common on bulk orders)
- `margin_pct` (snapshot)

This table is the source of truth for revenue analytics. SUM(amount) by account == account.annual_revenue * tenure_years (approximately, within ±10%).

### Table 6: `rep_visits` (5,000–15,000 per sub-mode)
- `visit_id` (PK)
- `account_id` (FK)
- `rep_id` (FK)
- `visit_date`
- `visit_duration_minutes` (mean=15 acute, mean=8 specialty)
- `outcome` ∈ {info, sample, demo, follow-up, no-access}
- `topics_discussed` (JSON array of product_ids)

This enables the dashboard to compute "calls per account per year" by sub-mode (REQ-4).

### Table 7: `account_specialties` (1,500–4,000 rows)
- `account_id` (FK)
- `specialty` (e.g., 'Onkologie', 'Kardiologie')
- `is_primary` (one per account is_primary=true)
- `bed_count` (sub-allocation of total beds, NULL for clinics)

Allows the dashboard to filter "show me oncology accounts in Bayern" or compute specialty-by-Bundesland heatmaps.

### Table 8: `geographic_metadata` (1 row, JSON-like)
- `osm_snapshot_date`
- `bkg_vintage_year`
- `bundesland_count` (= 16)
- `landkreis_count` (= ~401, exact from BKG file)
- `account_landkreis_coverage_pct` (% of Landkreise with at least 1 account)
- `seed`
- `total_accounts_acute`, `total_accounts_specialty`

This table is for metadata/lineage, not analytical use. It powers the "Data Quality" page of the dashboard.

## STATISTICAL CORRELATIONS (REALISM REQUIREMENTS)

The data must encode these correlations between tables. These create the "this looks real" effect:

### GEOGRAPHIC DENSITY CORRELATIONS
- Bundesland account count ~ population (Spearman ρ > 0.7)
- Landkreis account count ~ population × urban_factor (urban Landkreise overweighted by 1.5×)
- Rep home location ~ accounts within 60km radius (reps live near accounts)
- Distance from rep home to assigned account: log-normal mean=35 km, sigma=0.9 (reps cover wider area in rural Bundesländer)

### REVENUE PREDICTORS (per account)
Annual revenue per account is a function of:
- `bed_count` (positive correlation, R² ~ 0.45 for acute)
- `account_archetype` (University > Maximalversorger > Schwerpunktversorger > Grundversorger; absolute differences calibrated)
- `tenure_years` (negative noise — older customers may have lower MARGINAL revenue but higher TOTAL)
- `specialty_focus` count (more specialties = more revenue, plateaus at 4)
- `acquisition_channel` (conference + KOL accounts have higher revenue than cold-call)

### CHURN/INACTIVATION PREDICTORS (status='inactive')
- Distance to nearest rep > 90 km (positive correlation)
- Time since last visit > 365 days (positive correlation)
- Bed_count low + ownership=forprofit (some small private hospitals churn through M&A)
- Acute-care churn rate annual: ~4% (low — formulary lock-in)
- Specialty-care churn rate annual: ~9%

### NOISE
Add realistic noise (R² in 0.3–0.5 range, NOT 0.9). If a downstream BigQuery ML model predicts revenue with R² > 0.85 on this data, it's too clean.

## DATA QUALITY INJECTION

Apply the existing `--data-quality {clean|medium|messy}` flag pattern. Pharma-specific issues for `medium` mode:

- 0.4% of accounts: Hospital name spelling variants ("Klinikum Augsburg" vs "Klinikum der Stadt Augsburg")
- 0.6% of accounts: PLZ format inconsistency (4-digit vs 5-digit, leading zero stripped)
- 0.3% of accounts: Bundesland name vs ISO code mismatch ("Bayern" / "BY" / "Bavaria")
- 1.1% of orders: Negative quantities (returns — legitimate but easy to misfilter)
- 0.8% of orders: Order date misaligned with rep visit date by ±90 days (delayed CRM entry)
- 0.5% of orders: Account → rep assignment inconsistent with rep_visits (territory realignment legacy)
- 0.3% of products: Duplicate ATC code with old vs new PZN (PZN renumbering events)
- 1.0% of accounts: Coordinates rounded inconsistently (3 vs 6 decimals)

Clean: zero issues. Messy: 4× the above rates.

## CLI INTERFACE

Extend the existing CLI with the new pharma subcommand:

```bash
synth-datagen pharma \
    --sub-mode {acute-care,specialty-care} \
    --hospitals-csv ./data/osm_hospitals_germany_20260601.csv \
    --bkg-bundeslaender ./data/de_bundeslaender_VG250.geojson \
    --bkg-landkreise ./data/de_landkreise_VG250.geojson \
    --company-name "MediCorp" \
    --rep-count 40 \
    --account-count 850 \
    --start-date 2023-01-01 \
    --end-date 2026-06-30 \
    --currency EUR \
    --primary-atc L01 \
    --target-quota-attainment 0.92 \
    --data-quality medium \
    --seed 20260601 \
    --output-dir ./data/medicorp_acute \
    --output-format csv \
    --benchmark-validation true
```

The `--benchmark-validation true` flag runs a final pass that compares generated metrics against benchmarks in `benchmarks/pharma.py` and writes warnings to `metadata.json` if any metric is outside ±20% of expected range.

For specialty-care sub-mode, `--primary-atc` selects the dominant therapy area (defaults: L01 oncology). Required values: L01 (oncology), L04 (immunosuppressants), S01 (ophthalmologicals), D (dermatologicals).

## OUTPUT ARTIFACTS

Generate in the output directory (8 files, +1 vs SaaS):

1. **Data files** (8 CSVs as defined above)
2. **`data_dictionary.md`** — every column documented with type, source, distribution, expected range
3. **`metadata.json`** — generation parameters, seed used, RNG state hashes, benchmark validation results, geo lineage block
4. **`benchmark_validation.md`** — table comparing generated metrics vs DESTATIS/PHAGRO/IQVIA/vfa benchmarks
5. **`expected_findings.md`** — pre-computed insights ("Bayern should show 22–26% of acute-care total revenue", "Top 5 University hospitals account for ~10% of revenue")
6. **`schema.sql`** — BigQuery CREATE TABLE statements with appropriate clustering keys (cluster on `bundesland_ags` for boundary-aligned queries)
7. **`load_to_bigquery.sh`** — convenience script using `bq load` commands
8. **`geo_lineage.md`** — OSM snapshot date, BKG vintage, AGS schema version, license attribution (ODbL for OSM, dl-de/by-2-0 for BKG). Required for portfolio honesty.

## TASK BREAKDOWN

Work through this in the following order. Stop and ask the user for input if anything is unclear.

### Step 1: Reconnaissance (read-only)
- Read the existing post-refactor `synth_datagen` repo structure
- Read existing scenario files for architectural pattern (specifically `scenarios/saas/_common.py`, `scenarios/saas/plg_usage_based.py`)
- Read the RNG isolation pattern in `src/synth_datagen/rng.py`
- Read how shared modules (`distributions.py`, `quality.py`) are imported
- Read the existing CLI argument parser (`cli.py`) to understand Typer command/option conventions
- Read existing benchmark constants files in `src/synth_datagen/benchmarks/`
- Read the SaaS scenario tests in `tests/scenarios/test_saas_*.py` for testing pattern reference
- Document findings in a brief summary before proceeding

### Step 2: Architecture proposal
- Propose the file structure for the new pharma scenario:
  - `src/synth_datagen/scenarios/pharma/__init__.py`
  - `src/synth_datagen/scenarios/pharma/_common.py`
  - `src/synth_datagen/scenarios/pharma/acute_care.py`
  - `src/synth_datagen/scenarios/pharma/specialty_care.py`
  - `src/synth_datagen/geo.py` (NEW shared module)
  - `src/synth_datagen/benchmarks/pharma.py` (NEW)
- Propose the new CLI flags and how they integrate with existing parser
- Propose the test plan (per `synth_datagen_pharma_integration_notes.md` Section 7)
- WAIT for user approval before writing code

### Step 3: Implementation in dependency order

3a. **`benchmarks/pharma.py`** — All industry benchmark constants with citations (must be done first; everything else imports from here)

3b. **`geo.py`** — Shared geo helpers
- `load_bundeslaender(geojson_path) -> GeoDataFrame`
- `load_landkreise(geojson_path) -> GeoDataFrame`
- `load_osm_hospitals(csv_path) -> DataFrame`
- `spatial_join_to_landkreis(points_gdf, landkreise_gdf) -> Series[str]` (returns AGS for each point)
- `validate_ags_hierarchy(landkreise_df, bundeslaender_df) -> None` (raises if invariant fails)

3c. **RNG factory in `rng.py`** — Add `PHARMA_MASTER_SALT = 0x5DDA50000` and `make_pharma_rng_streams()`

3d. **`scenarios/pharma/_common.py`** — Shared logic
- Account generation skeleton (sample from OSM, spatial join, impute bed_count)
- Realistic German name generator (German hospital naming patterns: "{Klinikum/Krankenhaus/Klinik} {City}", "{Saint} {City}", "{University} Klinikum")
- AGS hierarchy validation
- Data quality injection layer (pharma-specific patterns)

3e. **`scenarios/pharma/acute_care.py`** — Sub-mode A implementation

3f. **`scenarios/pharma/specialty_care.py`** — Sub-mode B implementation

3g. **`scenarios/pharma/__init__.py`** — Scenario protocol export

3h. **CLI integration in `cli.py`** — Add `pharma` subcommand with all flags

3i. **`docs.py` extensions** — Auto-doc generation for pharma schema (8 tables)

3j. **`benchmark_validation` logic** — Compare generated metrics to benchmarks, write warnings

3k. **Tests** — One test file per sub-mode, plus shared geo tests, plus reproducibility test

### Step 4: Validation
- Run end-to-end with default parameters for acute-care sub-mode
- Run end-to-end with default parameters for specialty-care sub-mode
- Verify benchmark validation passes
- Compute and report: revenue distribution by Bundesland, account density correlation with population, top-20% revenue concentration, churn rates by sub-mode
- Compare against `expected_findings.md`

### Step 5: Hand-off
- Write `examples/pharma_medicorp.py` — usage example for Project 7 GIS Territory dashboard
- Update the project's main README.md (add Pharma to scenarios list)
- Update CHANGELOG.md (this is the v0.3.0 release)
- Generate baseline outputs for both sub-modes with seed=20260601 and 20260602
- Verify backward compatibility: regenerate retail (Kupferkanne seed) and saas (Promptforge seed) — diff against pre-pharma baseline must be EMPTY

## TESTING REQUIREMENTS

For each generation run, validate:

```python
# Test: Geographic plausibility (REQ-1)
def test_pharma_acute_geographic_plausibility():
    out = pharma.generate(sub_mode="acute-care", seed=42, account_count=850, ...)
    accounts = out["accounts"]
    # All AGS resolved
    assert accounts["bundesland_ags"].notna().all()
    assert accounts["landkreis_ags"].notna().all()
    # Hierarchy invariant
    assert (accounts["landkreis_ags"].str[:2] == accounts["bundesland_ags"]).all()
    # Pareto-like distribution at Landkreis level
    counts_per_lk = accounts["landkreis_ags"].value_counts()
    top_20pct = counts_per_lk.head(int(len(counts_per_lk) * 0.2)).sum()
    assert top_20pct / len(accounts) > 0.55, f"Top 20% concentration too low: {top_20pct/len(accounts)}"

# Test: Account type distribution (REQ-2)
def test_pharma_acute_account_type_distribution():
    out = pharma.generate(sub_mode="acute-care", seed=42, account_count=850, ...)
    type_counts = out["accounts"]["account_archetype"].value_counts(normalize=True)
    # University hospitals should be ~2-4% of accounts
    assert 0.015 < type_counts.get("University", 0) < 0.05

# Test: Revenue realism (REQ-3)
def test_pharma_acute_revenue_realism():
    out = pharma.generate(sub_mode="acute-care", seed=42, account_count=850, ...)
    accounts = out["accounts"]
    median_revenue = accounts["annual_revenue"].median()
    assert 30_000 < median_revenue < 120_000  # acute-care band
    # Top 5 university hospitals concentrate revenue
    uni_revenue = accounts.loc[accounts["account_archetype"] == "University", "annual_revenue"].sum()
    total_revenue = accounts["annual_revenue"].sum()
    uni_pct = uni_revenue / total_revenue
    assert 0.05 < uni_pct < 0.18, f"University hospital revenue concentration off: {uni_pct}"

# Test: Sales force productivity (REQ-4)
def test_pharma_specialty_visit_frequency():
    out = pharma.generate(sub_mode="specialty-care", seed=42, ...)
    visits_per_account_per_year = (
        out["rep_visits"].groupby("account_id").size()
        / years_in_dataset(out)
    )
    median_visits = visits_per_account_per_year.median()
    assert 7 < median_visits < 16

# Test: Reproducibility (REQ-7)
def test_pharma_reproducibility():
    out1 = pharma.generate(sub_mode="acute-care", seed=42, ...)
    out2 = pharma.generate(sub_mode="acute-care", seed=42, ...)
    for table_name in out1.keys():
        assert out1[table_name].equals(out2[table_name])

# Test: Stream isolation (REQ-7)
def test_pharma_stream_isolation():
    """Changing data_quality must not shift account locations or AGS."""
    base = pharma.generate(sub_mode="acute-care", seed=42, data_quality="clean", ...)
    msy  = pharma.generate(sub_mode="acute-care", seed=42, data_quality="messy", ...)
    invariant_cols = ["account_id", "latitude", "longitude", "bundesland_ags", "landkreis_ags"]
    assert base["accounts"][invariant_cols].equals(msy["accounts"][invariant_cols])

# Test: Stream count stable (regression guard)
def test_pharma_stream_count_stable():
    streams = make_pharma_rng_streams(base_seed=42)
    assert list(streams.keys()) == [
        "accounts", "reps", "territories", "orders",
        "products", "engagement", "quality", "regional",
    ]

# Test: Population correlation (REQ-1)
def test_pharma_bundesland_population_correlation():
    out = pharma.generate(sub_mode="acute-care", seed=42, account_count=850, ...)
    accounts_per_bl = out["accounts"]["bundesland_ags"].value_counts()
    bl_population = out["bundeslaender"].set_index("ags_2digit")["population"]
    correlation = accounts_per_bl.corr(bl_population, method="spearman")
    assert correlation > 0.7, f"Population correlation too weak: {correlation}"

# Test: Backward compatibility (no shift in retail/saas)
def test_pre_pharma_baselines_unchanged():
    # Run retail with Kupferkanne seed
    retail_out = retail.generate(seed=KUPFERKANNE_SEED, ...)
    # Compare to baseline_pre_pharma/retail/
    assert retail_out.equals(load_baseline("baseline_pre_pharma/retail"))

# Integration test: CLI end-to-end
def test_cli_pharma_acute_e2e(tmp_path):
    result = subprocess.run([
        "synth-datagen", "pharma",
        "--sub-mode", "acute-care",
        "--hospitals-csv", str(test_fixtures / "osm_hospitals_DE_test.csv"),
        "--bkg-bundeslaender", str(test_fixtures / "bundeslaender_test.geojson"),
        "--bkg-landkreise", str(test_fixtures / "landkreise_test.geojson"),
        "--seed", "42", "--account-count", "300",
        "--output-dir", str(tmp_path),
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert (tmp_path / "accounts.csv").exists()
    assert (tmp_path / "geo_lineage.md").exists()
    assert (tmp_path / "metadata.json").exists()
```

## DELIVERABLES

When complete, provide:
1. Summary of changes made (files added, files modified, lines of code)
2. Output of running with default seed for both sub-modes: full benchmark validation report
3. Sample of 100 rows from each table (both sub-modes)
4. Confirmation that all 8 critical requirements (REQ-1 through REQ-8) are met with evidence
5. A one-paragraph explanation of any deviations from this prompt and why
6. Updated CHANGELOG.md entry for v0.3.0
7. Confirmation that retail and saas scenarios still produce IDENTICAL output to pre-pharma baselines (empty diff)

## CONSTRAINTS

- Do NOT introduce new heavyweight dependencies. Pharma scenario can use: numpy, pandas, geopandas, shapely (already required by SaaS for some helpers; if not, justify the addition). NO requests, NO API clients, NO HTTP libraries.
- Do NOT break existing scenarios — all retail/saas/fintech/logistics tests must still pass. Backward compatibility is HARD requirement (Phase 2 baseline diff procedure applies).
- Do NOT generate data faster by skipping correlation logic — realism is the entire point.
- Do NOT use uniform distributions where Pareto/log-normal/Beta would be more realistic.
- Do NOT hardcode "MediCorp" or any company name into the scenario logic — make it parametrizable via `--company-name`.
- Do NOT fetch any external data at runtime — all geographic data is supplied as input parameters.
- Do follow the existing code style and conventions of the repository (ruff + mypy strict on new code).
- Do write tests as you go (TDD per Superpowers `test-driven-development` skill).
- Do commit incrementally with conventional commit messages: `feat:`, `test:`, `docs:`, `refactor:`.
- Do verify backward compatibility BEFORE committing the new scenario: run baseline diff procedure on retail and saas with their respective seeds.

## SESSION CLOSURE — code-reviewer pass

Before declaring this session done, activate the `code-reviewer` agent skill 
from Superpowers and run a final review:

1. Diff against main: `git diff main..HEAD --stat -w` and inspect semantic changes
2. Check spec compliance: every [ADDRESS] finding from the audit / every required 
   deliverable from this prompt has a matching commit
3. Check architectural compliance: 
   - RNG factory used correctly (no direct np.random.default_rng calls in 
     scenario code)
   - Backward compat baseline diff is empty for all prior scenarios
   - Conventional Commits format on every commit
   - No co-authored-by trailer
4. Report issues found, OR confirm: "Code review pass clean."

Only after this pass: declare session complete and request user merge.

## SUCCESS CRITERIA

This task is complete when:
- The user can run `synth-datagen pharma --sub-mode acute-care --hospitals-csv ... --bkg-bundeslaender ... --bkg-landkreise ... --company-name "MediCorp" --seed 20260601 --output-dir ./data/medicorp_acute` and get a complete, internally-consistent dataset.
- The same is true for `--sub-mode specialty-care`.
- The output passes all benchmark validation checks (REQ-1 through REQ-8).
- The generated data, when loaded into PostGIS, makes the Project 7 GIS Territory dashboard credible — a senior healthcare data analyst examining the data says "this looks like real B2B German pharmaceutical sales data."
- Same seed produces identical output across runs (bit-for-bit reproducibility).
- Existing scenarios (retail, saas-plg, saas-vertical, fintech, logistics) continue to work unchanged.
- CHANGELOG entry for v0.3.0 documents the new scenario, new shared module `geo.py`, new external file inputs.
- All 5 critical tests pass: reproducibility, stream isolation, stream count stable, population correlation, backward compatibility.
```

---

## Recommended usage with Claude Code

1. Open Claude Code in your `synth-datagen` repo directory (post-refactor, post-SaaS-extension)
2. Confirm prerequisites:
   - `git tag` shows v0.2.0 exists
   - `pytest` passes 100% on existing scenarios
   - SaaS scenario produces both PLG and Vertical sub-mode outputs
   - OSM hospital snapshot + BKG VG250 GeoJSONs exist in the gis-territory-optimization repo
3. Save this prompt to `prompts/05_pharma_implementation.md`
4. Open a fresh Claude Code session and say: `"Read prompts/05_pharma_implementation.md and execute it."`
5. Let the agent execute Step 1 (reconnaissance) and review its summary
6. Approve Step 2 (architecture proposal) before any code is written
7. Let Steps 3–5 proceed with periodic check-ins; intervene at each commit

If the agent skips reconnaissance or starts coding before architecture approval, interrupt and reference the `## TASK BREAKDOWN` section explicitly. The Superpowers `brainstorming` skill should activate when ambiguity arises (e.g., "How should I handle the case where OSM PLZ is NULL but spatial join resolves to a Landkreis?" — that's a design decision the user should make, not the agent).
