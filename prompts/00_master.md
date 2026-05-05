# synth-datagen — Master Workflow & Orchestration
## v1.1 — Single source of truth for the whole project (audit + SaaS extension + Pharma scenario) — English edition

> **Why this document exists:** Files 01–05 contain *execution instructions* (commands, REQs, contracts). This file is the *orchestration layer* — when to open which file, in which session, which commits, which human checkpoints. Open this FIRST in a new Claude thread. Attach files 01–05 alongside as a package.

> **State as of:** 2026-05-05. Workflow not yet started. P1 Kupferkanne in progress (Pages 2–6 + drillthrough for NovyPro publication).

---

## 0. HOW TO USE THIS DOCUMENT

### In a new Claude / Codex / Claude Code thread:
1. Attach all 6 files: `00_master.md` (this file) + `audit/01_handoff.md` + `audit/02_workflow.md` + `saas/03_extension.md` + `04_synth_datagen_pharma_integration_notes.md` + `pharma/05_implementation.md`
2. Say: *"Read 00 master workflow. This is the entry point. Tell me which phase I'm in based on Section 11 (State Tracker), and give me the next action."*
3. Claude reads master, checks state tracker (Section 11), proposes next action.

### Locally (offline):
- Keep all files in a `prompts/` folder inside the `synth-datagen` repo
- Sub-folders: `prompts/audit/` (01, 02), `prompts/saas/` (03), `prompts/pharma/` (04, 05)
- 00 master stays in `prompts/` as the entry point

---

## 1. PROJECT IDENTITY

**Repo:** `synth-datagen` (currently private, planned public after v0.2.0)

**Goal:** Take the existing private Python CLI repo with synthetic business datasets (retail, SaaS, fintech, logistics) to portfolio-grade open source. Then extend with two new scenarios (SaaS sub-modes, Pharma Field Sales) needed for Projects 2, 7, 13, 14.

**Wall time:** ~3–4 weeks at 2–3h/day. Full calendar span:
- Audit + refactor + tests + docs (Phases 1–4): ~1 week
- SaaS extension: ~3 days
- Pharma scenario: ~3–4 days
- Buffer and review: ~1 week

**Strategic reason:** synth-datagen is the engine behind every upcoming portfolio dashboard. Clean, tested, published repo = (a) every dashboard has trustworthy data, (b) the engine itself becomes a portfolio piece, (c) the story "I built the engine that powers my portfolio" is a senior-level talking point in interviews.

---

## 2. FILES IN THIS PROJECT

| # | File | Type | When to use | How to use |
|---|------|------|-------------|------------|
| **00** | `00_master.md` | **Master** | **Open first in a new thread** | Read |
| **01** | `audit/01_handoff.md` | Meta-handoff | Context and prerequisites before Phase 1 | Read |
| **02** | `audit/02_workflow.md` | 4-phase workflow | Phase 1–4: audit/refactor/tests/docs | Execute — paste fragments into Claude Code |
| **03** | `saas/03_extension.md` | Coding agent prompt | After Phase 4, extends repo with SaaS sub-modes | Execute — paste whole prompt into Claude Code |
| **04** | `04_synth_datagen_pharma_integration_notes.md` | Architecture | After SaaS extension, before file 05 | Read — do not paste into agent |
| **05** | `pharma/05_implementation.md` | Coding agent prompt | After reading 04 | Execute — paste whole prompt into Claude Code |

**Key distinction:** *Read* files give you context and decisions. *Execute* files are pasted into the agent as instructions. **Master (00) and Pharma integration notes (04) are NEVER pasted into the agent** — they are for you.

---

## 3. MASTER TIMELINE

```
═══════════════════════════════════════════════════════════════════════════
PRE-FLIGHT (10 min)
  Install Superpowers + ECC selective
  Tag v0.1.0-preaudit (rollback point)
═══════════════════════════════════════════════════════════════════════════
                         ↓
═══════════════════════════════════════════════════════════════════════════
PHASE 1 — AUDIT (read-only, 1-2h agent + 30min review)
  [ Files: 01 (context) + 02 Phase 1 section (prompt) ]
  Output: audit_report.md
  Decision: GO/NO-GO for Phase 2
  COMMIT: 1 commit, push to main
═══════════════════════════════════════════════════════════════════════════
                         ↓
═══════════════════════════════════════════════════════════════════════════
PHASE 2 — REFACTOR (4-6h agent + 1h review)
  [ File: 02 Phase 2 section (prompt) ]
  Branch: feat/refactor-from-audit
  Multiple commits per finding (TDD enforced)
  Baseline diff retail/saas/fintech/logistics MUST be empty
  COMMITS: 5-15 commits
  TAG: v0.2.0-rc1 after merge to main
═══════════════════════════════════════════════════════════════════════════
                         ↓
═══════════════════════════════════════════════════════════════════════════
PHASE 3 — TESTS & VALIDATION (4-6h agent + 30min review)
  [ File: 02 Phase 3 section (prompt) ]
  Branch: feat/test-hardening
  Hypothesis property tests, benchmark validation, CI workflow
  Coverage >= 85%
  COMMITS: 5-10 commits
  TAG: v0.2.0-rc2 after merge to main
═══════════════════════════════════════════════════════════════════════════
                         ↓
═══════════════════════════════════════════════════════════════════════════
PHASE 4 — DOCS & PUBLICATION PREP (2-3h agent + 30min review)
  [ File: 02 Phase 4 section (prompt) ]
  Branch: feat/docs
  README, MkDocs site, CHANGELOG, CONTRIBUTING, SECURITY, pyproject metadata
  COMMITS: 5-8 commits
  TAG: v0.2.0 after merge to main  ← MILESTONE: repo ready for publication
  OPTIONAL: switch repo to public (GitHub UI)
  OPTIONAL: PyPI publish (twine upload)
═══════════════════════════════════════════════════════════════════════════
                         ↓
═══════════════════════════════════════════════════════════════════════════
SAAS EXTENSION (~3 days)
  [ File: 03 (whole prompt to agent) ]
  Branch: feat/saas-extension
  Step 1: Reconnaissance (read-only)
  Step 2: Architecture proposal — WAIT FOR USER APPROVAL
  Step 3a-3k: Implementation
  Step 4-5: Validation + handoff
  COMMITS: 8-12 commits
  TAG: v0.2.1 after merge to main
═══════════════════════════════════════════════════════════════════════════
                         ↓
═══════════════════════════════════════════════════════════════════════════
PHARMA SCENARIO (~3-4 days)
  [ Files: 04 (read it!) + 05 (whole prompt to agent) ]
  BEFORE opening agent: read 04 in full (architecture, integration)
  Branch: feat/pharma-scenario
  Step 1: Reconnaissance + read 04 references
  Step 2: Architecture proposal — WAIT FOR USER APPROVAL
  Step 3a-3k: Implementation
  Step 4-5: Validation + handoff
  COMMITS: 10-15 commits
  TAG: v0.3.0 after merge to main
═══════════════════════════════════════════════════════════════════════════
                         ↓
                    🟢 DONE
```

**Calendar plan:** assuming 2–3h/day focused work plus weekends for review:

| Week | What happens |
|------|--------------|
| Week 1 | Pre-flight + Phase 1 + Phase 2 (start) |
| Week 2 | Phase 2 (rest) + Phase 3 |
| Week 3 | Phase 4 + tag v0.2.0 + optional public release |
| Week 4 | SaaS extension + tag v0.2.1 |
| Week 5 | Pharma scenario + tag v0.3.0 |

---

## 4. STEP-BY-STEP EXECUTION

### Step 0 — Pre-flight (one-off)

```bash
# 1. Check synth-datagen repo state
cd X:\Python\projects\synth-datagen      # NOT in OneDrive!
git status                                # clean?
git log --oneline -5                      # where are you?

# 2. Tag baseline state (rollback point)
git tag v0.1.0-preaudit
git push origin v0.1.0-preaudit

# 3. Check Python
python --version                          # >= 3.11; prefer 3.12

# 4. Install skills
# In Claude Code:
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace

/plugin marketplace add affaan-m/everything-claude-code
# Selective install (4 skills):
git clone https://github.com/affaan-m/everything-claude-code /tmp/ecc
mkdir -p ~/.claude/skills/
cp -r /tmp/ecc/skills/python-patterns ~/.claude/skills/
cp -r /tmp/ecc/skills/python-testing ~/.claude/skills/
cp -r /tmp/ecc/skills/search-first ~/.claude/skills/
cp -r /tmp/ecc/skills/agentshield ~/.claude/skills/

# 5. Optional: baseline security scan
npx ecc-agentshield scan --no-install
# if P0 issues: fix BEFORE Phase 1

# 6. Create prompts/ folder
mkdir -p prompts/{audit,saas,pharma}
# Copy the 5 numbered files into the right subfolders
```

**Verification check:**
- [ ] `synth-datagen/` is outside OneDrive
- [ ] `git tag --list | grep preaudit` shows v0.1.0-preaudit
- [ ] `/plugin list` in Claude Code shows superpowers + everything-claude-code
- [ ] `python --version` returns 3.11.x or 3.12.x (3.13 acceptable but 3.12 preferred for stability)

---

### Step 1 — Phase 1: Audit (read-only)

**Before the session:** Read file **02** section "PHASE 1 — Audit". Cut out just the prompt (from `## ROLE` to the end of `## SUCCESS CRITERIA`) and save it as `prompts/audit/01_audit.md` in the repo.

**Session:**
```
1. Open a fresh Claude Code session in the synth-datagen repo directory
2. Say: "Read prompts/audit/01_audit.md and execute it."
3. Agent runs the audit (1-2h). DO NOT INTERRUPT. Output: audit_report.md
4. After completion: leave the session, open audit_report.md in your editor
```

**Human checkpoint (30 min):**
- Read `audit_report.md`
- Record in state tracker (Section 11): count of P0/P1/P2/P3 issues
- Decision: GO (proceed to Phase 2) or NO-GO (if 50+ P0, rethink architecture)
- Mark in audit_report.md which findings you'll address in Phase 2 (you can skip some P3)

**Commits:**
```bash
git add audit_report.md
git commit -m "docs: add Phase 1 audit report"
git push origin main
```

**State tracker update** (Section 11): Phase 1 = ✅, current_phase = "Phase 2 ready"

---

### Step 2 — Phase 2: Refactor

**Before the session:** Cut the prompt from **02** section "PHASE 2 — Surgical Refactor", save as `prompts/audit/02_refactor.md`. PASTE at the start of the prompt (where the placeholder `[USER PASTES THE LIST OF FINDINGS TO ADDRESS HERE]` is) the specific findings from audit_report.md the agent should address.

**Session:**
```
git checkout -b feat/refactor-from-audit
# Fresh Claude Code session
# "Read prompts/audit/02_refactor.md and execute it."
```

**What happens (4-6h):**
- Agent picks the first finding
- Writes a plan in `tasks/plan_<finding_id>.md`
- TDD: failing test → implementation → passing test
- Baseline diff retail/saas/fintech/logistics with seed=42 → MUST be empty
- Commit using Conventional Commits format
- Next finding
- After each session: push to remote for backup

**Critical interventions:**
- If the agent starts writing code without a test: say "use test-driven-development skill"
- If baseline diff is non-empty: STOP, investigate (bug? intentional change? version bump?)
- If 3 failed attempts on the same problem: say "Stop. Use brainstorming skill before continuing."

**Sample commit messages:**
```bash
# After each fix:
git commit -m "refactor: extract RNG factory to src/synth_datagen/rng.py"
git commit -m "fix: correct Beta distribution alpha parameter in retail"
git commit -m "test: add reproducibility test for retail scenario"
git commit -m "chore: configure ruff and mypy in pyproject.toml"
git commit -m "refactor: migrate retail to src layout"

# Push after each session:
git push origin feat/refactor-from-audit
```

**Human checkpoint (1h, end of Phase 2):**
- All pre-commit hooks pass
- pytest 100% pass
- Baseline diff retail/saas/fintech/logistics with seed=42 = empty diff
- Coverage >= 80%
- Conventional commits format on every commit

**Merge:**
```bash
# PR (recommended, forces self-review):
gh pr create --title "Phase 2: Refactor from audit findings" --body "..."
gh pr merge --squash    # or --merge

# Or direct merge (if confident single-dev):
git checkout main
git merge --no-ff feat/refactor-from-audit
git push origin main

# Tag:
git tag v0.2.0-rc1
git push origin v0.2.0-rc1
```

**State tracker update**: Phase 2 = ✅, branch closed, current_phase = "Phase 3 ready"

---

### Step 3 — Phase 3: Tests & Validation

**Before the session:** Cut the prompt from **02** section "PHASE 3 — Tests & Validation", save as `prompts/audit/03_tests.md`.

**Session:**
```
git checkout main
git pull
git checkout -b feat/test-hardening
# Fresh Claude Code session
# "Read prompts/audit/03_tests.md and execute it."
```

**What happens (4-6h):**
- Coverage gap analysis
- Property-based tests via Hypothesis (5+ per scenario)
- Benchmark validation tests
- CLI integration tests
- Performance regression tests
- CI configuration (.github/workflows/ci.yml)

**Sample commits:**
```bash
git commit -m "test: add Hypothesis property tests for retail invariants"
git commit -m "test: add benchmark validation for SaaS NRR scenarios"
git commit -m "test: add CLI integration tests"
git commit -m "ci: add GitHub Actions workflow for Python 3.11/3.12/3.13"
```

**Human checkpoint (30 min):**
- pytest passes 5x in a row (no flaky tests)
- Coverage >= 85% for src/synth_datagen/
- CI workflow runs on a fresh PR
- Single `pytest` < 60s

**Merge + tag:**
```bash
git checkout main && git merge --no-ff feat/test-hardening && git push
git tag v0.2.0-rc2
git push origin v0.2.0-rc2
```

**State tracker update**: Phase 3 = ✅, current_phase = "Phase 4 ready"

---

### Step 4 — Phase 4: Docs & Publication Prep

**Before the session:** Cut the prompt from **02** section "PHASE 4 — Documentation", save as `prompts/audit/04_docs.md`.

**Session:**
```
git checkout main && git pull
git checkout -b feat/docs
# Fresh Claude Code session
# "Read prompts/audit/04_docs.md and execute it."
```

**What happens (2-3h):**
- README rewrite (≤ 300 lines, scannable, quickstart)
- MkDocs Material site setup
- CHANGELOG.md (Keep a Changelog format)
- CONTRIBUTING.md, SECURITY.md
- pyproject.toml metadata complete for PyPI

**Commits:**
```bash
git commit -m "docs: rewrite README with quickstart and architecture"
git commit -m "docs: add MkDocs Material site"
git commit -m "docs: add CHANGELOG.md for v0.2.0"
git commit -m "docs: add CONTRIBUTING.md and SECURITY.md"
git commit -m "chore: update pyproject.toml metadata for PyPI publication"
```

**Human checkpoint (30 min):**
- README answers "what is this and why care" within the first 30 seconds of reading
- `mkdocs build --strict` succeeds
- Every code example in README/docs verified to work
- Fresh clone + `pip install -e ".[test]"` + `pytest` works

**Merge + final tag:**
```bash
git checkout main && git merge --no-ff feat/docs && git push
git tag v0.2.0
git push origin v0.2.0
```

🎉 **MILESTONE: synth-datagen v0.2.0 ready for public release.**

**Optional — switch repo to public:**
- GitHub UI → Settings → "Change repository visibility" → Public
- Update LinkedIn featured section with link to repo
- Write LinkedIn post: "I built the engine that powers my portfolio data" (post #44 from calendar)

**Optional — PyPI publish:**
```bash
pip install build twine
python -m build
twine upload dist/*
```

**State tracker update**: Phase 4 = ✅, v0.2.0 tagged, current_phase = "SaaS extension ready"

---

### Step 5 — SaaS Extension

**Before the session:** Open file **03** in your editor. The whole file is the prompt to copy.

**Session:**
```
git checkout main && git pull
git checkout -b feat/saas-extension
# Fresh Claude Code session
# Paste the whole prompt from saas/03_extension.md
```

**What happens (~3 days, 8-12 sessions of 1-2h):**
- Step 1: Reconnaissance (agent reads repo)
- Step 2: Architecture proposal — **WAIT FOR YOUR APPROVAL** before agent starts coding
- Step 3a-3k: Implementation (TDD enforced)
- Step 4: Validation (run end-to-end with default params)
- Step 5: Handoff (examples script, README update, sample dataset)

**After Step 2 — your decision:**
The agent proposes a file structure (`scenarios/saas/__init__.py`, `_common.py`, `plg_usage_based.py`, `vertical_account_based.py`). Before approving:
- Does it match the post-refactor architecture from Phase 2?
- Is RNG salt 0x5AA50000 registered in `rng.py`?
- Are CLI flags consistent with the rest of the scenarios?

If yes: "Approved, proceed with Step 3."

**Commits:**
```bash
git commit -m "feat(saas): add benchmark constants module with KeyBanc 2024 sources"
git commit -m "feat(saas): add RNG salt 0x5AA50000 and stream factory"
git commit -m "feat(saas): implement plg-usage-based sub-mode account generation"
git commit -m "feat(saas): implement subscription_events 5 movement types"
git commit -m "feat(saas): implement vertical-account-based sub-mode"
git commit -m "test(saas): add benchmark validation tests for NRR/CAC/churn"
git commit -m "feat(saas): integrate sub-modes into CLI"
git commit -m "docs(saas): update README with SaaS scenario examples"
```

**Human checkpoint (1h, end of SaaS extension):**
- Promptforge (`--sub-mode plg-usage-based --company-name "Promptforge" --seed 20260504`) generates a full dataset
- NRR Enterprise in the 1.15-1.30 range
- Inverse pyramid churn (Free > Pro > Team > Enterprise)
- All 5 MRR movement types present
- Backward compat: retail/fintech/logistics with prior seeds → identical output

**Merge + tag:**
```bash
git checkout main && git merge --no-ff feat/saas-extension && git push
git tag v0.2.1
git push origin v0.2.1
```

**State tracker update**: SaaS extension = ✅, v0.2.1 tagged, current_phase = "Pharma ready"

---

### Step 6 — Pharma Scenario (TWO files: read 04, execute 05)

**Before the session (CRITICAL):**

1. **Read file 04 in full** (`04_synth_datagen_pharma_integration_notes.md`). It is the architectural companion document. DO NOT paste into agent.
2. Verify prerequisites from 04 Section 13:
   - [ ] Repo at tag v0.2.1 (post SaaS)
   - [ ] OSM hospital snapshot CSV in P7 GIS repo (`gis-territory-optimization/data/osm_hospitals_germany_<DATE>.csv`)
   - [ ] BKG VG250 GeoJSONs (Bundesländer + Landkreise) in P7 GIS repo
   - [ ] Pre-flight: spatial join validation (16 Bundesländer, ~401 Landkreise, AGS hierarchy intact)

**If OSM/BKG data is not yet downloaded:**
Before starting Pharma, do this once (in P7 GIS repo, NOT in synth-datagen):
```bash
cd /path/to/gis-territory-optimization
mkdir -p data scripts

# Manual download BKG VG250 ZIP from gdz.bkg.bund.de
# Extract bundeslaender.geojson + landkreise.geojson into data/

# Write scripts/fetch_osm_hospitals.py (Overpass API, single-shot)
python scripts/fetch_osm_hospitals.py \
    --output data/osm_hospitals_germany_$(date +%Y%m%d).csv

# Validate:
python -c "
import pandas as pd
df = pd.read_csv('data/osm_hospitals_germany_*.csv')
print(f'Rows: {len(df)}')             # >= 3000
print(f'NULL coords: {df[df.latitude.isna()].shape[0]}')  # = 0
"

git add data/osm_hospitals_germany_*.csv data/de_*VG250.geojson
git commit -m "chore: add OSM hospital snapshot and BKG VG250 boundaries"
git push
```

**Pharma session:**
```
cd X:\Python\projects\synth-datagen
git checkout main && git pull
git checkout -b feat/pharma-scenario
# Fresh Claude Code session
# Paste the whole prompt from pharma/05_implementation.md
```

**What happens (~3-4 days, 10-15 sessions of 1-2h):**
- Step 1: Reconnaissance (reads repo + reads 04 as reference)
- Step 2: Architecture proposal — **WAIT FOR YOUR APPROVAL**
- Step 3a-3k: Implementation
  - 3a: `benchmarks/pharma.py` (DESTATIS, PHAGRO, IQVIA, vfa constants)
  - 3b: `geo.py` shared module (haversine, AGS hierarchy)
  - 3c: RNG factory updates (salt 0x5DDA50000)
  - 3d: `pharma/_common.py`
  - 3e: `pharma/acute_care.py`
  - 3f: `pharma/specialty_care.py`
  - 3g: `pharma/__init__.py`
  - 3h: CLI integration
  - 3i: docs.py extensions
  - 3j: benchmark_validation logic
  - 3k: tests
- Step 4: Validation (both sub-modes)
- Step 5: Handoff + examples/pharma_medicorp.py

**Commits:**
```bash
git commit -m "feat(pharma): add benchmark constants module with DESTATIS/PHAGRO/IQVIA sources"
git commit -m "feat(pharma): add geo.py shared module for AGS hierarchy and SRID transforms"
git commit -m "feat(pharma): register RNG salt 0x5DDA50000 in rng factory"
git commit -m "feat(pharma): implement _common.py with German hospital name generator"
git commit -m "feat(pharma): implement acute-care sub-mode"
git commit -m "feat(pharma): implement specialty-care sub-mode"
git commit -m "feat(pharma): integrate pharma subcommand in CLI"
git commit -m "test(pharma): add geo plausibility and AGS hierarchy tests"
git commit -m "test(pharma): add population correlation and reproducibility tests"
git commit -m "docs(pharma): add geo_lineage.md auto-doc generation"
git commit -m "docs(pharma): add examples/pharma_medicorp.py for P7 GIS project"
```

**Human checkpoint (1h, end of Pharma):**
- MediCorp acute (`--sub-mode acute-care --seed 20260601`) generates a full dataset
- MediCorp specialty (`--sub-mode specialty-care --seed 20260602`) generates a full dataset
- Bundesland → Landkreis hierarchy invariant: 100% of accounts have valid `bundesland_ags + landkreis_ags`, parent FK matches
- Population correlation > 0.7
- Top 20% Landkreise concentrate 60-70% of accounts (Pareto)
- Backward compat: retail/saas-plg/saas-vertical/fintech/logistics with prior seeds → identical output

**Merge + final tag:**
```bash
git checkout main && git merge --no-ff feat/pharma-scenario && git push
git tag v0.3.0
git push origin v0.3.0
```

🎉 **MILESTONE: synth-datagen v0.3.0 — full engine behind 5 portfolio projects.**

**State tracker update**: Pharma = ✅, v0.3.0 tagged, current_phase = "DONE"

---

## 5. COMMITS — FULL STRATEGY

### Format: Conventional Commits

| Prefix | When to use | Example |
|--------|-------------|---------|
| `feat:` | New functionality (new scenario, new sub-mode, new CLI flag) | `feat(pharma): add specialty-care sub-mode` |
| `fix:` | Bug fix (e.g., wrong distribution param) | `fix(retail): correct Beta alpha parameter` |
| `refactor:` | Structural change without behavior change | `refactor: extract RNG factory to rng.py` |
| `test:` | Adding/modifying tests | `test(saas): add Hypothesis property tests` |
| `docs:` | Documentation only | `docs: rewrite README with quickstart` |
| `chore:` | Tooling, deps, config | `chore: configure ruff in pyproject.toml` |
| `ci:` | GitHub Actions, CI config | `ci: add Python 3.13 to test matrix` |

**Scope in parentheses** (optional but recommended): `feat(saas):`, `feat(pharma):`, `test(retail):`, etc. Helps `git log --grep`.

### Branches

| Branch | Purpose | Lifetime |
|--------|---------|----------|
| `main` | Stable, every commit passes CI | Permanent |
| `feat/refactor-from-audit` | Phase 2 | ~1 week |
| `feat/test-hardening` | Phase 3 | ~3 days |
| `feat/docs` | Phase 4 | ~2 days |
| `feat/saas-extension` | SaaS scenario | ~3 days |
| `feat/pharma-scenario` | Pharma scenario | ~4 days |

**Each branch has one purpose.** Do not mix refactor + tests in one branch.

### Tags (Semantic Versioning)

| Tag | Meaning | When |
|-----|---------|------|
| `v0.1.0-preaudit` | As-is state, baseline | BEFORE Phase 1 |
| `v0.2.0-rc1` | After Phase 2 (refactor done) | Release candidate |
| `v0.2.0-rc2` | After Phase 3 (tests done) | Release candidate |
| `v0.2.0` | After Phase 4 (docs done) | **Public release** |
| `v0.2.1` | After SaaS extension | Minor version (new scenarios) |
| `v0.3.0` | After Pharma scenario | Minor version (new scenario + new shared module geo.py) |

### Push frequency

- **After every Claude Code session:** `git push origin <current-branch>` — backup
- **At the end of a phase/extension:** merge to main, tag, push tag
- **Evening after work:** always push (even WIP) — sessions can disappear

### Repo public — when?

**Recommendation: after Phase 4 (tag v0.2.0).** At that point the repo has:
- Clean code (refactor done)
- Solid tests (Hypothesis + benchmarks + CI)
- Documentation (README + MkDocs site)
- Professional pyproject.toml

SaaS extension and Pharma scenario land on the public repo as later versions (v0.2.1, v0.3.0).

---

## 6. HUMAN DECISION POINTS — WHERE YOU MUST DECIDE

Phases 1–4 contain decisions the agent will not make on its own. Full list:

| After | Decision | Consequences |
|-------|----------|--------------|
| Phase 1 audit | Which findings do you address in Phase 2? | P0 + P1 = mandatory; P2 selective; P3 you can skip |
| Phase 1 audit | GO/NO-GO for Phase 2? | If 50+ P0 → spend another day on architecture |
| Phase 2 (mid-flight) | Backward compat break — bug or intentional? | Bug → fix; intentional → version bump (v0.2.0 → v1.0.0) |
| Phase 2 (mid-flight) | 3 failed attempts on the same finding? | Stop session, brainstorming skill, may need architecture rethink |
| Phase 4 | Repo public? When? | Recommendation: yes, after v0.2.0. Can defer to v0.3.0 if you want a quiet phase. |
| Phase 4 | PyPI publish? | Optional. Do it if a recruiter is supposed to `pip install synth-datagen` and try it. |
| SaaS Step 2 | Approve agent's architecture proposal? | Verify it matches Phase 2 outcome and RNG conventions |
| SaaS Step 4 | Backward compat passed for retail/fintech/logistics? | Empty diff = OK, otherwise STOP |
| Pharma Step 2 | Approve architecture proposal? | Verify alignment with 04 integration notes |
| Pharma Step 4 | Backward compat passed for retail/saas-*/fintech/logistics? | Empty diff = OK |

---

## 7. ESCAPE HATCHES — WHEN THINGS BREAK

### Backward compat break (non-empty baseline diff)

```bash
# Stop. Don't commit.
# Investigate:
git diff baseline_before/ baseline_after/ | head -50

# Is it a bug (RNG state shift)?
# Is it intentional behavior change (changing distribution param to correct value)?

# If bug:
# - Find the change that caused it (likely insertion in RNG stream order)
# - Fix
# - Re-run baseline diff

# If intentional:
# - Document in CHANGELOG.md as breaking change
# - Major version bump (v0.2.x → v1.0.0)
# - User-facing migration guide
```

### Agent stuck (3 failed attempts)

```
In chat:
"Stop. Use the brainstorming skill from Superpowers. 
Don't write any more code. Tell me three different architectural approaches 
to this problem and your reasoning for each."

# Pick one approach, then "OK, proceed with approach #2."
```

### Claude Code session vanished / interrupted

```bash
# Don't worry — code is committed.
git status                  # clean or WIP?
git log --oneline -5        # recent changes

# If WIP mid-session:
# Unfortunately, context is lost. Restart phase from the nearest commit point.
# Master doc + state tracker help restoring context.
```

### Audit finds P0 in git history (e.g., exposed API key)

```bash
# This is a BLOCKER for public release.
# Options:
# 1. git rebase -i + remove the bad commit (complex, breaks history for collaborators)
# 2. BFG Repo-Cleaner: https://rtyley.github.io/bfg-repo-cleaner/
# 3. git filter-repo
# 4. Simplest: rotate the leaked credential (it's already public if anyone cloned)
#    + commit removal + force push + document in SECURITY.md

# After fix: re-run agentshield to confirm clean history
```

### Phase 4 docs build fails (`mkdocs build --strict`)

```bash
# Most common causes:
# - broken markdown links → fix the links
# - missing pages in mkdocs.yml → add to nav
# - code examples don't run → run each code block, fix it

# Strict mode is your friend — it stops broken docs from being published
```

---

## 8. PARALLEL WORK — HOW THIS FITS WITH THE REST OF THE PORTFOLIO

This project runs in parallel with:
- **P1 Kupferkanne** (Power BI dashboard pages 2–6 + drillthrough for publication)
- **us-equity-benchmark** (Python + Hetzner VPS, Phase 0 done)
- Hetzner VPS Freqtrade Dry Run (background)

**Recommendation: priority on P1 Kupferkanne.**

| Week | P1 (Kupferkanne) | synth-datagen | us-equity-benchmark |
|------|------------------|---------------|--------------------|
| 1 | 80% (Page 2-6 publish) | 20% (Phase 1 audit, review time) | 0% |
| 2 | 30% (refinement, screenshots, README) | 70% (Phase 2 refactor) | 0% |
| 3 | 0% (P1 done) | 100% (Phase 3-4 + tag v0.2.0) | 0% |
| 4 | 0% | 60% (SaaS extension) | 40% (Phase 1 if time allows) |
| 5 | 0% | 60% (Pharma scenario) | 40% |

**Rule: if P1 and synth-datagen ever conflict in any week, P1 wins.** P1 = portfolio ready for job applications. synth-datagen = engine behind it. Without P1 there is not even an entry point to interviews.

---

## 9. ENVIRONMENT & TOOLING

### Local environment

```bash
# Repo location:
X:\Python\projects\synth-datagen\    # NOT in OneDrive!
                                      # OneDrive breaks venv path resolution

# Python:
python --version                      # 3.12 preferred (uv-managed venv)

# IDE:
VS Code with Claude Code extension   # Subscription, not API
                                      # affaan-m everything-claude-code skill pack

# Git:
git --version                         # 2.40+
gh --version                          # GitHub CLI for PRs

# Coding agent:
Claude Code (preferred)               # has Superpowers + ECC selective
# OR Codex (alternative)              # similar skills via affaan-m/everything-claude-code
```

### Cloud environment

- **GitHub:** ryszard-twardy/synth-datagen (currently private; planned public after v0.2.0)
- **Hetzner CX22:** runs Freqtrade Dry Run, does NOT interfere with synth-datagen local work
- **PyPI:** optional after v0.2.0

### Skills active (Phase 2-4)

- **Superpowers** (full install, 14 skills): brainstorming, systematic-debugging, test-driven-development, subagent-driven-development, verification-before-completion, writing-plans, using-git-worktrees, code-reviewer agent, ...
- **ECC selective** (4 skills): python-patterns, python-testing, search-first, agentshield

---

## 10. DEFINITION OF DONE — WHOLE PROJECT

The workflow is complete when ALL of the below are ✅:

### synth-datagen v0.2.0 (post Phase 4)
- [ ] `git tag --list` shows v0.1.0-preaudit, v0.2.0
- [ ] `pytest` 100% pass
- [ ] Coverage >= 85% for `src/synth_datagen/`
- [ ] CI passes on Python 3.11/3.12/3.13
- [ ] `mkdocs build --strict` succeeds
- [ ] README ≤ 300 lines, scannable
- [ ] CHANGELOG.md with v0.1.0-preaudit + v0.2.0 release notes
- [ ] CONTRIBUTING.md, SECURITY.md, LICENSE in repo
- [ ] pyproject.toml has full PyPI metadata
- [ ] Baseline diff retail/saas/fintech/logistics with seed=42 → empty
- [ ] Repo public on GitHub (or conscious decision to delay)

### synth-datagen v0.2.1 (post SaaS extension)
- [ ] `git tag --list` shows v0.2.1
- [ ] SaaS PLG sub-mode produces full dataset (NRR 1.15-1.30, inverse pyramid churn, 5 movement types)
- [ ] SaaS Vertical sub-mode produces full dataset (different dynamics, annual contracts)
- [ ] Backward compat retail/fintech/logistics → empty diff
- [ ] CHANGELOG entry for v0.2.1
- [ ] Examples: `examples/saas_promptforge.py`, `examples/saas_vertical_demo.py`

### synth-datagen v0.3.0 (post Pharma scenario)
- [ ] `git tag --list` shows v0.3.0
- [ ] Pharma acute-care sub-mode produces full dataset (German hospitals, AGS hierarchy)
- [ ] Pharma specialty-care sub-mode produces full dataset
- [ ] `geo.py` shared module registered
- [ ] `benchmarks/pharma.py` with citations to DESTATIS/PHAGRO/IQVIA/vfa
- [ ] Backward compat retail/saas-*/fintech/logistics → empty diff
- [ ] CHANGELOG entry for v0.3.0
- [ ] `examples/pharma_medicorp.py` for P7 GIS project
- [ ] LinkedIn post: "I built the engine that powers my portfolio data"

---

## 11. STATE TRACKER — UPDATE AS YOU GO

> **Critical for continuation in a new thread.** Fill these fields after every session. In a new thread Claude reads this first to know "where you are".

```yaml
# UPDATE THIS BLOCK AFTER EACH SESSION
project_state:
  last_updated: "YYYY-MM-DD HH:MM"
  current_phase: "pre-flight"  # pre-flight | phase-1 | phase-2 | phase-3 | phase-4 | saas-extension | pharma-scenario | done
  current_branch: "main"
  current_commit_hash: ""
  repo_local_path: "X:\\Python\\projects\\synth-datagen"
  
tags_created:
  v0_1_0_preaudit: ""          # YYYY-MM-DD when tagged
  v0_2_0_rc1: ""
  v0_2_0_rc2: ""
  v0_2_0: ""                    # ← public release date
  v0_2_1: ""                    # ← post SaaS extension
  v0_3_0: ""                    # ← post Pharma scenario

audit_findings:
  total_p0: 0
  total_p1: 0
  total_p2: 0
  total_p3: 0
  addressed_in_phase2: []       # list of finding IDs

decisions_made:
  - "(template) On YYYY-MM-DD: chose Option B for OSM fetch (snapshot in P7 repo, not internal to synth-datagen)"
  - "(template) On YYYY-MM-DD: chose Pharma sub-mode (b) two-modes (acute-care + specialty-care)"
  - "(template) On YYYY-MM-DD: chose research benchmark sources from DESTATIS, PHAGRO, IQVIA, vfa, Pharmalotse"
  
known_blockers: []              # what's stopping progress
last_action: ""                 # last thing you did
next_action: ""                 # next planned action

repo_state:
  is_public: false              # change to true post v0.2.0
  is_on_pypi: false             # change to true if you publish
```

---

## 12. CONTINUATION PROMPT — TO PASTE IN A NEW THREAD

When you start a new Claude thread (e.g., after a few days off), paste:

```
I'm continuing the synth-datagen audit + extensions project. I'm attaching 6 files:
- 00_master.md (THIS — entry point)
- audit/01_handoff.md
- audit/02_workflow.md
- saas/03_extension.md
- pharma/04_integration_notes.md
- pharma/05_implementation.md

Read 00 master workflow. Section 11 has the state tracker — 
check current_phase, decisions_made, and next_action. 

Tell me:
1. Which phase I'm in
2. What the next concrete step is  
3. Which prerequisites I need to verify before executing the next action
4. Any blocking decisions I have to make

Don't execute anything beyond orientation.
```

Claude will read the master, verify state, propose next action, and wait for your go-ahead.

---

## 13. WHAT IF…

| Question | Answer |
|----------|--------|
| …I don't finish the project in 5 weeks? | OK, extend. Master doc holds state. There's no deadline. |
| …I want to skip Phase 3 tests? | NO. Property tests are what separates "code that works" from "code you'd publish". |
| …I want to do Pharma before SaaS? | NO. The SaaS extension establishes the sub-mode pattern that Pharma copies. |
| …I want to do P7 GIS before Pharma scenario? | NO. P7 dashboard consumes data from the Pharma scenario. Without Pharma scenario, P7 has ad-hoc synthetic data you'd write twice. |
| …repo stays private forever? | OK, but you lose the portfolio narrative. v0.2.0 can stay private; SaaS extension and Pharma can too. But the "I built the engine" story works best with a public repo. |
| …skill conflicts between Superpowers + ECC? | See Section 7 escape hatches. Pick ONE install method, don't mix `/plugin install` with `./install.sh`. |
| …Phase 1 audit finds 100+ findings? | Realistic. Address P0 + P1 (critical). P2 selectively. P3 defer to "Phase 5 future work" in README. |
| …I don't have time for daily work? | OK, weekends. Master doc holds state, Claude Code sessions are atomic (each phase in a separate session = you can have weeks between phases). |

---

## 14. WHAT'S NEXT POST v0.3.0

After completing the Pharma scenario, you have a fully-functional synth-datagen v0.3.0 with 5 scenarios and 2 sub-modes (SaaS + Pharma). Next steps in the portfolio:

```
[v0.3.0 DONE]
   ↓
P2 SaaS Dashboard (Promptforge, ~10-14 days) — uses synth-datagen saas plg-usage-based
   ↓
Maven Supply Chain / Candy warm-up (PostGIS practice, 4-5 days)
   ↓
P7 GIS Territory Dashboard (~16 days) — uses synth-datagen pharma + Project7_GIS_Territory_Handoff_v1.1.md
   ↓
P14 RFEDA Account Health Scorecard (~16 days) — uses synth-datagen saas vertical-account-based
   ↓
P13 Payment Funnel (~14 days) — uses synth-datagen fintech
   ↓
🟢 PORTFOLIO COMPLETE (5 dashboards + open-source engine)
   ↓
Job applications begin in earnest
```

---

## 15. CLOSING NOTE

This project is not a sprint. The audit/refactor takes time because you do it once well, not five times badly. SaaS and Pharma extensions take time because they give you the "I built the engine that powers my portfolio" narrative — a story most juniors cannot tell.

Stay focused. No shortcuts. After every phase, update the State Tracker (Section 11). Commit often, push after every session.

Good luck.

---

**Author:** Ryszard Twardy  
**Master document version:** v1.1 (English edition, repo path corrected to X:\Python\projects)  
**Created:** 2026-05-05  
**Last updated:** 2026-05-05  
**Status:** Ready for execution post Kupferkanne completion
