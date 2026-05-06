# Coding Agent Prompt: Extend synth-datagen with Production-Grade SaaS Scenario

> **How to use this prompt:** Paste the entire contents below into Claude Code, OpenAI Codex, or your coding agent of choice. The prompt is structured so the agent can work through it section by section without losing context. Each `## ROLE`, `## CONTEXT`, `## TASK` block is self-contained. Coding agent should first explore the existing `synth-datagen` codebase before writing any new code.

---

```
## ROLE

You are a senior data engineer and synthetic data architect with deep expertise in:
- B2B SaaS unit economics (MRR, ARR, NRR, GRR, CAC, LTV, churn modeling)
- Industry-realistic data generation calibrated to public benchmarks
- Statistical distribution modeling (Beta, Gamma, Pareto, log-normal, Weibull)
- Reproducible RNG architecture with isolated stream seeding
- Python data engineering: pandas, numpy, dataclasses, type hints, pytest

You are extending an existing CLI tool (`synth-datagen`) — NOT writing from scratch. The tool already supports retail, fintech, and logistics scenarios with configurable data quality injection and automatic documentation output. Your job is to add a SaaS scenario that produces data realistic enough to back two portfolio dashboards (Project 2: SaaS PLG Dashboard, Project 14: RFEDA Account Health Scorecard).

## CONTEXT

### The user
The user (Ryszard) is building a data analytics portfolio targeting EU SaaS/fintech roles. He has an existing `synth-datagen` Python CLI tool with:
- Scenarios for retail, SaaS (basic), fintech, logistics
- Configurable data quality injection (clean / medium / messy)
- Automatic documentation output (data dictionary, lineage)
- `--seed` flag with isolated RNG streams (e.g., `discount_rng = numpy.random.default_rng(seed=base_seed ^ 0xD15C0UNT)`)
- Beta distribution parametrization for segment-aware propensities
- `--discount-variation` CLI flag pattern as architectural reference

### The two consumer projects

**Project 2 — SaaS PLG Dashboard (Promptforge mock company):**
- 6-page Power BI dashboard with: Executive Summary, MRR Waterfall, Cohort Retention, Churn Drivers (BigQuery ML), Trial Funnel & CAC, Methodology
- Requires industry-plausible NRR > 110% scenarios driven by usage-based expansion
- Backed by BigQuery ML logistic regression for churn prediction

**Project 14 — RFEDA Account Health Scorecard (different SaaS company):**
- 400-line BigQuery CTE pipeline with 5-dimensional scoring (Recency, Feature breadth, Engagement depth, Dollar trajectory, Advocacy)
- Momentum layer comparing current 30-day window vs prior 30-day window
- 10-segment classification with revenue-at-risk and expansion-opportunity calculations

Both projects need DIFFERENT companies (different sub-vertical, naming, pricing model) but SAME scenario engine.

### Why this matters

A previous synthetic SaaS dataset (Analyst Builder CloudTask Pro) had four obvious synthetic-data fingerprints that would fail a hiring manager's plausibility check:
- 52% lifetime churn (real healthy SaaS: 5-15% annual)
- Flat churn-reason distribution (real distributions are Pareto-skewed)
- 500+ employee companies churning more than SMB (inverse of reality — enterprise is stickier)
- Uniform CAC across all plans (real CAC scales 5-20× with deal size)

The data you generate must NOT have these fingerprints. A senior SaaS analyst should look at the data and say "this looks like a real B2B SaaS company" — not "this is clearly synthetic."

## CRITICAL REQUIREMENTS (NON-NEGOTIABLE)

These are HARD requirements. If any of these fail, the dataset is unusable for the target dashboards.

### REQ-1: MRR Movement Coverage
The data MUST emit all 5 MRR movement types as discrete events with timestamps and revenue deltas:
- `new` — first paid subscription for an account
- `expansion` — same account, increased MRR (upgrade, seat add, usage tier increase)
- `contraction` — same account, decreased MRR (downgrade, seat reduction, NOT churn)
- `churn` — subscription cancellation (MRR → 0)
- `reactivation` — previously-churned account returns to paying status

Without ALL FIVE event types, the MRR waterfall cannot be built. Without expansion events, NRR collapses to GRR.

### REQ-2: NRR > 100% Achievable
At least one segment (typically Enterprise) MUST produce NRR in the 115-130% range. This requires:
- Expansion MRR > Contraction MRR + Churned MRR within that segment
- Realistic expansion timing (not all at month 1; spread over customer lifetime with peak at month 6-12)

### REQ-3: Plausible Churn Distribution
Monthly churn rates must follow inverse-pyramid pattern (smaller customers churn more):
- Free: 8-12% monthly (high churn, low CAC, expected)
- Pro/SMB: 3-5% monthly
- Team/Mid-market: 2-3% monthly
- Enterprise: 1-2% monthly

Lifetime churn over 36 months: ~25-35% total (NOT 52%).

### REQ-4: Realistic CAC by Segment
CAC must scale with deal size (not uniform):
- Free → Pro upgrade: €200-€500 (mostly self-serve)
- Pro: €400-€800
- Team/Mid-market: €1,500-€3,500
- Enterprise: €8,000-€20,000

These are calibrated against KeyBanc 2024 SaaS Benchmarks and Benchmarkit 2025.

### REQ-5: Pareto-Skewed Churn Reasons
Churn reasons must follow Pareto distribution (not flat). One or two reasons should account for 50%+ of churn:
- Primary reasons (top 2): "Budget cuts" and "Switched to competitor" — together 50-60% of churn
- Secondary reasons: "Feature gaps", "Poor support", "No longer needed" — 25-35% combined
- Long tail: "Company closed", "Acquisition", "Other" — remaining 10-15%

### REQ-6: 36+ Months of History
Cohort retention requires meaningful tenure data. Generate ≥36 months from the company's founding date to today. The first 3-6 months should have small denominators (the "noise period") and your code should flag this in the metadata so consumers know to exclude it from trend visualizations.

### REQ-7: Reproducibility
Use the existing `--seed` flag and isolated RNG stream pattern. Add a new SaaS-specific stream:
```python
saas_rng = numpy.random.default_rng(seed=base_seed ^ 0x5AA50000)
```
Within SaaS, further isolate streams for different concerns:
- `expansion_rng = saas_rng.spawn(1)[0]` for expansion event timing
- `churn_rng = saas_rng.spawn(2)[0]` for churn event timing
- `usage_rng = saas_rng.spawn(3)[0]` for usage event volume
- etc.

This ensures adding new logic doesn't shift RNG state for existing logic. Same seed → same data, every time.

### REQ-8: Industry Benchmark Calibration
Every distribution parameter must cite its source. Document in code comments:
```python
# Trial-to-paid conversion rate: 25% (KeyBanc 2024 median for B2B PLG SaaS)
# Source: https://www.keybanc.com/saas-survey-2024
TRIAL_CONVERSION_RATE = 0.25
```

Required benchmark sources:
- Benchmarkit 2025 SaaS Performance Metrics
- KeyBanc 2024 SaaS Survey
- OpenView 2024 SaaS Benchmarks
- Orb Billing 2025 Usage-Based Pricing Benchmarks
- ChartMogul 2024 SaaS Retention Report

## SCENARIO ARCHITECTURE

Build the SaaS scenario with TWO sub-modes (since Project 2 and Project 14 need different company profiles):

### Sub-mode A: `saas-plg-usage-based`
For Promptforge-style AI/ML productivity tools.
- Pricing: Free tier + 3 paid tiers + usage overage
- Primary expansion driver: token/API call/event volume increase
- Strong NRR (target: 120-130%)
- Trial-to-paid: 25-30%
- Industries: tech-forward (SaaS, AI startups, e-commerce, fintech)

### Sub-mode B: `saas-vertical-account-based`
For Project 14 (vertical SaaS where account health scoring matters).
- Pricing: 4 named tiers (Starter/Professional/Business/Enterprise) with annual contracts dominant
- Primary expansion driver: seat additions + module add-ons
- Moderate NRR (target: 105-115%)
- Trial-to-paid: 18-22% (longer sales cycle)
- Industries: vertical-specific (legal, restaurant, logistics, healthcare — pick one per generation)

## DATA SCHEMA

The scenario must output 9 tables in CSV format (or Parquet if specified):

### Table 1: `accounts` (4,000-5,000 rows)
- account_id (PK)
- company_name (realistic, no "Test Inc 001")
- signup_date
- plan_tier (Free, Pro, Team, Enterprise OR Starter, Professional, Business, Enterprise)
- country (weighted toward EU: DE, NL, FR, PL, ES, IT, UK, IE)
- employee_count (log-normal distribution, mean=120, sigma=1.2)
- industry (Pareto distribution: Tech 35%, E-commerce 18%, Finance 12%, Healthcare 10%, others)
- mrr (current)
- status (active, churned, paused)
- acquisition_channel (organic, paid_search, content, partner, outbound — Pareto)
- acquisition_cost (varies by channel and plan, log-normal within plan band)
- arr_band (computed: <1K, 1-10K, 10-100K, 100K+)

### Table 2: `users` (90,000-100,000 rows)
- user_id (PK), account_id (FK)
- role (admin, member, viewer)
- signup_date (constrained: >= account.signup_date)
- last_active_date (correlated with churn risk — recent for active, stale for at-risk)
- is_admin (boolean)
- avg_users_per_account: 4 (Free), 18 (Pro), 65 (Team), 280 (Enterprise) — log-normal around these means

### Table 3: `subscriptions` (8,000-10,000 rows)
- subscription_id (PK), account_id (FK)
- plan, mrr, start_date, end_date (NULL if active)
- billing_cycle (monthly OR annual — annual gets 17% discount, ~40% of customers prefer annual)
- status (active, churned, paused)
- One account can have MULTIPLE subscription rows over time (each upgrade/downgrade creates new row)

### Table 4: `subscription_events` (18,000-22,000 rows) ⚠️ CRITICAL TABLE
- event_id (PK), subscription_id (FK), account_id (FK, denormalized for ease)
- event_type ∈ {new, expansion, contraction, churn, reactivation}
- event_date
- mrr_delta (signed: positive for new/expansion/reactivation, negative for contraction/churn)
- previous_mrr, new_mrr
- reason (for churn: Pareto-distributed reasons; for expansion: 'seat_add', 'tier_upgrade', 'usage_overage', 'module_add')

This table is the source of truth for the MRR waterfall. It MUST sum correctly: SUM(mrr_delta) over time per account = current MRR.

### Table 5: `usage_events` (200,000-300,000 rows)
- event_id (PK), user_id (FK), account_id (FK)
- event_type (login, feature_use, api_call, integration_connect, etc.)
- event_date (datetime, hour-level granularity)
- token_count (NULL except for AI scenarios — log-normal when present)
- properties (JSON column with feature_name, duration_seconds, etc.)

Engagement patterns:
- Active customers: daily/weekly usage
- At-risk customers: declining frequency in last 30 days BEFORE churn
- Power users: 10× the median usage
- Weekly seasonality (Mon-Fri active, weekend drops)

### Table 6: `feature_usage` (50,000-60,000 rows)
- account_id, feature_name, first_used_date, last_used_date, total_uses
- 12-15 features total, with adoption funnel: 90% use core feature, 60% use second, declining to 15% for advanced features
- Higher feature breadth correlates with lower churn (this drives the BigQuery ML model insight)

### Table 7: `trials` (7,000-8,000 rows)
- trial_id (PK), account_id (FK)
- trial_start, trial_end, converted (bool), conversion_plan
- Trial duration: 14 days standard, 30 days for Enterprise
- Conversion timing within trial follows Beta(2, 5) distribution (most converters convert in first half)

### Table 8: `support_tickets` (12,000-15,000 rows)
- ticket_id (PK), account_id (FK)
- opened_date, resolved_date (NULL if open)
- severity (low/medium/high/critical — Pareto: 60% low, 25% medium, 12% high, 3% critical)
- resolution_time_hours (correlated with severity: critical median 2h, low median 24h)
- category (bug, question, feature_request, billing, other)

Tickets correlate with churn risk: customers with 3+ high/critical tickets in last 90 days have 5× higher churn probability.

### Table 9: `nps_responses` (8,000-10,000 rows)
- response_id (PK), account_id (FK)
- response_date, score (0-10), comment_category
- NPS distribution: 30% promoters (9-10), 50% passives (7-8), 20% detractors (0-6)
- Detractors have 3× higher churn probability in next 60 days

## STATISTICAL CORRELATIONS (REALISM REQUIREMENTS)

The data must encode these realistic correlations between tables. These are what create the "this looks real" effect:

### CHURN PREDICTORS (encode these into churn probability)
Churn probability per account per month should be a function of:
- `days_since_last_active` (linear positive correlation up to 30 days, then plateau)
- `feature_breadth_score` (negative correlation — more features = stickier)
- `support_ticket_severity_index` (positive correlation, especially high-severity)
- `nps_score` (negative correlation — detractors churn more)
- `plan_tier` (negative correlation with deal size)
- `account_age_months` (negative correlation — older accounts more stable)
- `acquisition_channel` (organic/partner > paid > outbound for retention)

### EXPANSION PREDICTORS
Expansion probability should be a function of:
- `current_usage / plan_limit_ratio` (when approaching limit, expansion likely)
- `feature_breadth` (broad users expand more)
- `team_growth_rate` (companies adding users → seat expansion)
- `nps_score` (promoters expand more)
- `time_in_current_plan` (peaks at 6-12 months)

### NOISE
Add realistic noise to all correlations (R² in 0.3-0.5 range, NOT 0.9). Real data is noisy. If your model can predict churn with 95% accuracy, the data is too clean.

## DATA QUALITY INJECTION (LEVERAGE EXISTING SYSTEM)

Apply the existing `--data-quality {clean|medium|messy}` flag pattern. For SaaS scenarios:

### Medium quality (default for portfolio):
- 0.5% of subscription_events have minor timestamp inconsistencies (events out of order by hours, not days)
- 0.3% of accounts have inconsistent country codes (e.g., 'DE', 'Germany', 'Deutschland' for same account history)
- 0.8% duplicate rows in usage_events (legitimate ETL boundary issue)
- 1.2% of MRR amounts have €/cents formatting inconsistency in raw export ('€129.00', '129', '12900' for cents)
- 0.5% of email/user_id null in usage_events (failed tracking)
- 0.2% of accounts have impossible event sequences (churn → activity → no reactivation event) — these test data quality validation

### Clean: zero issues. Messy: 3-5× the above rates.

## CLI INTERFACE

Extend the existing CLI with new flags:

```bash
synth-datagen saas \
    --sub-mode {plg-usage-based,vertical-account-based} \
    --company-name "Promptforge" \
    --industry-vertical "ai-productivity" \
    --start-date 2022-01-01 \
    --end-date 2026-04-30 \
    --account-count 4500 \
    --target-nrr 1.24 \
    --target-trial-conversion 0.27 \
    --currency EUR \
    --countries "DE,NL,FR,PL,ES,IT,UK,IE" \
    --data-quality medium \
    --seed 20260504 \
    --output-dir ./data/promptforge \
    --output-format csv \
    --include-bqml-features true \
    --benchmark-validation true
```

The `--benchmark-validation true` flag should run a final pass that compares generated metrics against industry benchmarks and writes warnings to `metadata.json` if any metric is outside ±20% of expected range.

## OUTPUT ARTIFACTS

Generate in the output directory:

1. **Data files** (9 CSVs as defined above)
2. **`data_dictionary.md`** — every column documented with data type, source, distribution, expected range
3. **`metadata.json`** — generation parameters, seed used, RNG state hashes, benchmark validation results
4. **`benchmark_validation.md`** — table comparing generated metrics vs industry benchmarks (NRR, GRR, churn rates, CAC by segment, trial conversion, etc.)
5. **`expected_findings.md`** — pre-computed insights the data should produce (e.g., "Enterprise NRR should be 122-128%", "Power users churn 4× less than light users") — useful for testing dashboards
6. **`schema.sql`** — BigQuery CREATE TABLE statements with appropriate clustering keys
7. **`load_to_bigquery.sh`** — convenience script using `bq load` commands

## TASK BREAKDOWN

Work through this in the following order. Stop and ask the user for input if anything is unclear.

### Step 1: Reconnaissance (read-only)
- Locate the existing `synth-datagen` repository
- Read the existing scenario files to understand the architectural pattern (likely `scenarios/retail.py`, `scenarios/fintech.py`, etc.)
- Read the RNG isolation pattern in detail
- Read how data quality injection currently works
- Read the CLI argument parser to understand flag conventions
- Read existing data dictionary output format
- Document findings in a brief summary before proceeding

### Step 2: Architecture proposal
- Propose the file structure for the new SaaS scenario (e.g., `scenarios/saas/__init__.py`, `scenarios/saas/plg_usage_based.py`, `scenarios/saas/vertical_account_based.py`, `scenarios/saas/common.py`)
- Propose the new CLI flags and how they integrate with existing parser
- Propose the test plan
- WAIT for user approval before writing code

### Step 3: Implementation in dependency order
3a. Common types and constants (industry benchmarks, distribution parameters)
3b. RNG stream architecture for SaaS
3c. Account generation (foundation for everything else)
3d. Subscription and subscription_events generation (THE critical path)
3e. Users and usage_events generation
3f. Feature usage, trials, support tickets, NPS
3g. Data quality injection layer
3h. Benchmark validation pass
3i. Documentation generation
3j. CLI integration
3k. Tests (unit tests for distributions, integration test for end-to-end consistency)

### Step 4: Validation
- Run end-to-end with default parameters
- Verify benchmark validation passes
- Compute and report: total NRR, churn by segment, trial conversion, CAC by plan, MRR waterfall sums
- Generate visualizations: MRR over time, cohort retention heatmap, churn rate by segment
- Compare against expected_findings.md

### Step 5: Hand-off
- Write a usage example script
- Update the project's main README.md
- Generate a sample dataset for Promptforge (Project 2)
- Generate a sample dataset for the Project 14 vertical SaaS company (user will specify which one)

## TESTING REQUIREMENTS

For each generation run, validate:

```python
# Test: NRR achievable
assert 1.05 < computed_nrr < 1.35, f"NRR out of plausible range: {computed_nrr}"

# Test: Inverse pyramid churn
churn_by_plan = compute_monthly_churn_by_plan(events)
assert churn_by_plan['Free'] > churn_by_plan['Pro']
assert churn_by_plan['Pro'] > churn_by_plan['Team']
assert churn_by_plan['Team'] > churn_by_plan['Enterprise']

# Test: All 5 movement types present
movement_types = events['event_type'].unique()
assert set(['new', 'expansion', 'contraction', 'churn', 'reactivation']).issubset(set(movement_types))

# Test: MRR waterfall sums correctly per account
for account_id in accounts.sample(100):
    delta_sum = events[events.account_id == account_id]['mrr_delta'].sum()
    current_mrr = accounts.loc[accounts.account_id == account_id, 'mrr'].iloc[0]
    assert abs(delta_sum - current_mrr) < 0.01

# Test: Reproducibility
data_run_1 = generate(seed=42)
data_run_2 = generate(seed=42)
assert data_run_1.equals(data_run_2)

# Test: Stream isolation (changing one feature doesn't affect others)
data_baseline = generate(seed=42, target_nrr=1.20)
data_high_nrr = generate(seed=42, target_nrr=1.30)
# Account names and signup dates should be IDENTICAL — only MRR-related fields differ
assert data_baseline['accounts'][['account_id', 'company_name', 'signup_date']].equals(
    data_high_nrr['accounts'][['account_id', 'company_name', 'signup_date']]
)
```

## DELIVERABLES

When complete, provide:
1. Summary of changes made (files added, files modified, lines of code)
2. Output of running with default seed: full benchmark validation report
3. Sample of 100 rows from each table
4. Confirmation that all 5 critical requirements (REQ-1 through REQ-8) are met with evidence
5. A one-paragraph explanation of any deviations from this prompt and why

## CONSTRAINTS

- Do NOT introduce new dependencies beyond what `synth-datagen` already uses (likely numpy, pandas, faker, click/argparse)
- Do NOT break existing scenarios — all retail/fintech/logistics tests must still pass
- Do NOT generate data faster by skipping correlation logic — realism is the entire point
- Do NOT use simple uniform distributions where Pareto/log-normal/Beta would be more realistic
- Do NOT hardcode "Promptforge" or any company name into the scenario logic — make it parametrizable
- Do follow the existing code style and conventions of the repository
- Do write tests as you go (not all at the end)
- Do commit incrementally with descriptive messages

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
- The user can run `synth-datagen saas --sub-mode plg-usage-based --company-name "Promptforge" --seed 20260504` and get a complete, internally-consistent dataset
- The output passes all benchmark validation checks
- The MRR waterfall in Power BI shows realistic 5-movement decomposition
- A senior SaaS analyst examining the data says "this looks like real B2B SaaS data" — not "this is clearly synthetic"
- The same seed produces identical output across runs
- Existing scenarios (retail, fintech, logistics) continue to work unchanged
```

---

## How this prompt is structured (for reference)

This prompt deliberately uses these prompt engineering patterns:

**Role assignment with specific expertise** — not "you are a data engineer" but "senior data engineer with deep expertise in [5 specific areas]." Coding agents perform measurably better when their domain is precisely scoped.

**Context before requirements** — the agent learns about the existing codebase, the user, and the consumer projects before seeing what to build. This prevents premature solutions.

**Numbered, non-negotiable requirements (REQ-1 through REQ-8)** — each requirement is testable and explicitly labeled as critical. Coding agents respect explicit constraints over implicit preferences.

**Statistical specificity over hand-waving** — every distribution is named (Beta, Pareto, log-normal) with parameters or behavior described. "Make it realistic" produces toy data; "log-normal with mean=120, sigma=1.2" produces real data.

**Anti-pattern documentation** — listing what the CloudTask Pro data did wrong gives the agent concrete failure modes to avoid, not just abstract goals to hit.

**Industry benchmark calibration with sources** — every parameter cites Benchmarkit/KeyBanc/Orb. This forces the agent to ground decisions in reality rather than fabrication.

**Explicit task breakdown** — Step 1 is read-only reconnaissance, Step 2 is architecture proposal that REQUIRES user approval before code is written. This prevents the "agent immediately starts coding" failure mode.

**Test-driven validation** — actual `assert` statements as part of the prompt mean the agent will write code that passes those assertions, not code that "looks correct."

**Reproducibility as first-class requirement** — the seed/RNG isolation pattern is described in code, not prose. Agents replicate code patterns more reliably than prose descriptions.

**Success criteria as hiring-manager test** — "a senior SaaS analyst should say it looks real" is the ultimate quality bar, beyond any specific metric.

## Recommended usage with Claude Code

1. Open Claude Code in your `synth-datagen` repo directory
2. Paste the prompt above
3. Let Claude Code execute Step 1 (reconnaissance)
4. Review the summary, correct any misunderstandings
5. Approve Step 2 (architecture) before any code is written
6. Let Steps 3-5 proceed with periodic check-ins

If the agent skips reconnaissance or starts coding before architecture approval, interrupt and reference the "## TASK BREAKDOWN" section explicitly.
