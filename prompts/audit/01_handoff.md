# synth-datagen Audit & Refactor — Handoff Document
## v1.1 — Ready to start (English edition)

> **Project goal:** Audit and refactor the existing `synth-datagen` repo (Python CLI, private) to portfolio-grade quality. Four phases of work with a coding agent, totaling 14–20h wall time, spread over one week.
>
> **When to start:** Before Project 2 (SaaS Dashboard) — `synth-datagen` is the engine behind all upcoming portfolio projects (P2, P14, P13). Clean repo = clean data = clean dashboards.

---

## 1. PROJECT IDENTITY

**One-liner:** Take the existing private `synth-datagen` repo (Python CLI generating synthetic business data for retail/SaaS/fintech/logistics scenarios), perform a structured audit, refactor to clean code, add property-based tests, and publish as an open-source repo that stands as a portfolio piece in its own right.

**Why this project exists:**

`synth-datagen` is the engine behind every portfolio dashboard. Kupferkanne already uses it. Project 2 (Promptforge SaaS) and Project 14 (RFEDA) will use it. Project 13 (Payment Funnel) will use it. If the engine has bugs in statistical distributions or non-reproducible logic, every dashboard inherits potential problems. Plus: a published engine is a **standalone portfolio piece** — in interviews you can say "I built the tool that generates data for my projects," which is a story most juniors cannot tell.

**Position in portfolio timeline:**

You should run this audit **BEFORE Project 2**. Reason: Project 2 requires extending `synth-datagen` with new SaaS sub-modes (`plg-usage-based`, `vertical-account-based`) plus new fields (`acquisition_cost`, `mrr_delta`, `nps_score`). Extending a clean, tested repo is 3x faster than extending a messy one.

---

## 2. PREREQUISITES

### Technical requirements
- [ ] Python 3.11+ installed locally (3.12 preferred for stability)
- [ ] Git configured (user.name, user.email)
- [ ] Claude Code Pro or OpenAI Codex active
- [ ] Local clone of the private `synth-datagen` repo
- [ ] Pre-existing portfolio context available (Kupferkanne builds with known seed values for baseline diff)

### Knowledge requirements
- [ ] You know the structure of your `synth-datagen` (which scenarios, which CLI flags)
- [ ] You know the seed used for Kupferkanne data generation (needed for backward compatibility)
- [ ] You understand the Conventional Commits format (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`)

### Time setup
- [ ] You can reserve 2–3 days of focused work OR 1 week with 2–3h per day
- [ ] You have access to your local machine (audit requires running code; not doable from mobile)

---

## 3. CRITICAL DECISION: DO NOT INSTALL ALL SKILLS

Not every skill from the available libraries is needed. Install strategy:

| Library | Strategy | Reason |
|---------|----------|--------|
| **Superpowers (`obra/superpowers`)** | Install ALL (14 skills) | Coherent methodology — skills work together; cherry-picking breaks the workflow |
| **ECC (`affaan-m/everything-claude-code`)** | Install SELECTIVE (4 skills) | 50+ skills available, most irrelevant to this project |

### Concrete install commands

#### Step 1 — Superpowers (full install)

```bash
# In Claude Code (slash commands):
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

After installation, the following skills will be available automatically in any new Claude Code session:
- `brainstorming` — refines requirements before code
- `systematic-debugging` — 4-phase root cause process
- `test-driven-development` — red/green/refactor enforced
- `subagent-driven-development` — parallel iteration with code review
- `verification-before-completion` — concrete evidence required
- `writing-plans` — feature breakdown into 2–5 minute tasks
- `using-git-worktrees` — isolated workspace per feature
- `code-reviewer` agent — spec compliance + code quality review
- + 6 more (auto-load when relevant)

#### Step 2 — ECC (selective install — ONLY these 4)

```bash
# In Claude Code:
/plugin marketplace add affaan-m/everything-claude-code

# Instead of full ECC install, use selective skill mode:
# (Exact syntax depends on ECC version v2.0.0-rc.1)

# Option A: If ECC supports selective install via flags
/plugin install everything-claude-code@everything-claude-code --skills python-patterns,python-testing,search-first,agentshield

# Option B: If the above does not work, clone ECC manually and copy only the needed skills
git clone https://github.com/affaan-m/everything-claude-code /tmp/ecc
mkdir -p ~/.claude/skills/
cp -r /tmp/ecc/skills/python-patterns ~/.claude/skills/
cp -r /tmp/ecc/skills/python-testing ~/.claude/skills/
cp -r /tmp/ecc/skills/search-first ~/.claude/skills/
cp -r /tmp/ecc/skills/agentshield ~/.claude/skills/
```

⚠️ **Critical warning from ECC docs:** If you install ECC via `/plugin install`, do NOT also run `./install.sh --profile full`. That copies all skills to user directories and creates duplicates + duplicate runtime behavior. Choose ONE install method and stick to it.

#### Step 3 — Verify

```bash
# In Claude Code:
/plugin list
# Should show: superpowers, everything-claude-code

# Check which skills are actually active:
# (In a new session)
"List all available skills currently loaded in this session"
```

#### Step 4 — Optional: AgentShield baseline scan

```bash
# Before any audit, run a one-time baseline security scan:
cd X:\Python\projects\synth-datagen
npx ecc-agentshield scan --no-install
```

This gives you an immediate report on credentials in git history, dangerous functions, etc. If it finds P0 issues (e.g., a hardcoded API key in the private repo), fix them BEFORE Phase 1.

### Why these specific 4 ECC skills

| Skill | Used in | Why essential |
|-------|---------|---------------|
| `python-patterns` | Phase 2 (refactor) | Type hints, dataclass patterns, Pydantic v2 idioms |
| `python-testing` | Phase 3 (tests) | pytest fixtures, hypothesis property tests, coverage |
| `search-first` | Phase 1 (audit) | Forces research before any change — critical for audit |
| `agentshield` | Phase 1, 4 (security) | Scans credentials, injection risks, dangerous patterns |

### What you do NOT need from ECC (and why)

| Skill | Why skipped |
|-------|-------------|
| `react-patterns` | No React in this project |
| `typescript-patterns` | No TypeScript |
| `database-skills` | You generate CSV files, not manage a database |
| `api-design` | No REST API, CLI only |
| `deployment-skills` | Open-source repo, not a deployed production service |
| `mcp-skills` | You are not building an MCP server |
| `frontend-skills` | Backend only |
| `kubernetes-skills` | No k8s |

**Total context cost after selective install:** ~3500–5000 tokens overhead (Superpowers metadata 14 skills + ECC metadata 4 skills + active skill loading on demand). Acceptable for Claude Code Pro 200K window and Codex 128K window.

---

## 4. WORKFLOW STRUCTURE

### 4-phase map

```
PHASE 1 (1-2h)        PHASE 2 (4-6h)        PHASE 3 (4-6h)        PHASE 4 (2-3h)
┌────────────┐         ┌────────────┐         ┌────────────┐         ┌────────────┐
│   AUDIT    │  ──→    │  REFACTOR  │  ──→    │   TESTS &  │  ──→    │ DOCUMENT & │
│            │         │            │         │ VALIDATION │         │  PUBLISH   │
│ Read-only  │         │ Surgical   │         │ Property + │         │ README,    │
│ analysis   │         │ changes    │         │ integration│         │ docs site, │
│ + report   │         │ per audit  │         │ tests      │         │ release    │
└────────────┘         └────────────┘         └────────────┘         └────────────┘
   Day 1 AM            Day 1 PM + Day 2        Day 2-3              Day 3
```

### Time budget

| Phase | Agent work | Your review | Total wall |
|-------|-----------|-------------|------------|
| 0. Setup | 10 min | — | 10 min |
| 1. Audit | 1–2h | 30 min | 2–3h |
| 2. Refactor | 4–6h | 1h | 5–7h |
| 3. Tests | 4–6h | 30 min | 4–6h |
| 4. Docs | 2–3h | 30 min | 3–4h |
| **Total** | **11–17h** | **2.5–3h** | **14–20h** |

Realistically: 2–3 days focused, or 1 week at 2–3h/day.

---

## 5. EXECUTION RULES

### Rule 1: Each phase in a separate Claude Code session

Do not continue Phase 2 in the same session as Phase 1. Reason: agents lose context in long conversations (drift problem). Open a fresh chat for each phase. Save prompts as files in the repo (`prompts/01_audit.md`, `prompts/02_refactor.md`, etc.) — do not copy from chat history.

Each phase starts with:
```
"Read prompts/0X_<phase>.md and execute it."
```

### Rule 2: Phase 1 (audit) IS read-only

The agent does NOT modify code in Phase 1. If it starts editing files, interrupt and point it to the `## CONSTRAINTS` section of the prompt. Phase 1 output is ONE file: `audit_report.md`.

### Rule 3: Human checkpoint between phases

After each phase, stop for 30 minutes and read the output. Decide GO/NO-GO. If `audit_report.md` shows 50 P0 issues, do not blindly enter Phase 2 — rethink scope.

### Rule 4: Backward compatibility = HARD requirement

All existing scenarios (retail, saas, fintech, logistics) must produce IDENTICAL output for a given seed after refactor. Reason: Kupferkanne already uses data from `synth-datagen`. If refactor changes output for seed=42, your dashboards break.

The Phase 2 prompt contains an explicit baseline diff procedure:
1. Run scenario with seed=42, save `baseline_before/`
2. Make the change
3. Run with seed=42, save `baseline_after/`
4. `diff -r baseline_before/ baseline_after/`
5. If diff is non-empty: STOP, investigate

### Rule 5: TDD enforced via Superpowers

In Phase 2, you do NOT write "please write tests first" — Superpowers `test-driven-development` skill auto-activates. If the agent starts writing code without a test, interrupt and say "use test-driven-development skill" — that restores discipline.

### Rule 6: 3-strike rule

If the agent fails 3 attempts to fix the same problem, STOP. Architectural review needed. Either:
- Open a new session with `brainstorming` skill explicitly
- Or escalate to yourself and rethink the architecture

---

## 6. DEFINITION OF DONE

The workflow is complete when:

### Code quality
- [ ] `ruff check .` — zero warnings
- [ ] `ruff format --check .` — pass
- [ ] `mypy src/` — zero errors (on new code)
- [ ] `bandit -r src/` — zero high-severity findings

### Tests
- [ ] `pytest` — 100% pass rate
- [ ] Coverage >= 85% for `src/synth_datagen/`
- [ ] Property-based tests via Hypothesis for each scenario
- [ ] Benchmark validation tests for each scenario
- [ ] CI passes on GitHub Actions (Python 3.11, 3.12, 3.13)

### Backward compatibility
- [ ] Diff baseline_before vs baseline_after = empty (all scenarios, seed=42)
- [ ] Kupferkanne data regenerated with new `synth-datagen` is bit-for-bit identical to old

### Documentation
- [ ] README.md ≤ 300 lines, scannable, quickstart works copy-paste
- [ ] docs/ site builds via MkDocs Material
- [ ] CHANGELOG.md with v0.2.0 release notes
- [ ] CONTRIBUTING.md and SECURITY.md
- [ ] pyproject.toml with full PyPI metadata
- [ ] Every code example in README verified to work

### Reproducibility
- [ ] Same seed → identical output (test passes)
- [ ] Different seeds → different output (test passes)
- [ ] RNG stream isolation works (changing one config does not shift other streams)

### Repo hygiene
- [ ] Zero credentials in git history (agentshield clean)
- [ ] Conventional commits for all Phase 2 commits
- [ ] Tag v0.2.0 created
- [ ] Repo public (if you decide to publish)

---

## 7. RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agent skips Phase 1 audit and starts coding immediately | High | High | Explicit `## CONSTRAINTS — DO NOT MODIFY ANY CODE in this phase` in prompt. Intervene immediately. |
| Backward compatibility breaks after refactor | Medium | Critical | Baseline diff procedure mandatory after every change. Stop and investigate if diff is non-empty. |
| Audit finds 50+ P0 issues — overwhelming | Medium | Medium | After Phase 1 review: skip P3, focus on P0+P1. Defer some P2 to "Phase 5 future work" in README. |
| Skills install conflict (Superpowers + ECC duplicates) | Low | Medium | Explicit warning in install section: pick ONE install path, do not mix `/plugin install` with `./install.sh` |
| Agent loses context mid-phase | High (long sessions) | Low | Each phase in a separate session. Prompts as files in repo. |
| Phase 3 property tests are flaky | Medium | Low | Run pytest 5x in a row before declaring done. Hypothesis seeded explicitly via `@settings(database=None)`. |
| Time overrun — Phase 2 takes 2x longer than planned | Medium | Low | After 6h in Phase 2, stop and review scope. Defer remaining findings to Phase 5. |
| User intervention needed mid-Phase 2 (architectural decision) | High | Low | This is NOT a risk; it is a feature. Superpowers skills activate brainstorming when needed. Respond to agent questions promptly. |

---

## 8. POST-WORKFLOW: WHAT'S NEXT

After completing the workflow:

### Immediately
- Commit final state, tag v0.2.0
- Update LinkedIn featured section with link to repo
- Write a LinkedIn post: "I built the engine that powers my portfolio data" (one of the post #44 candidates from the LinkedIn calendar)

### Within a week
- Extend `synth-datagen` with SaaS scenario sub-modes (file 03 prompt)
- Start Project 2 (SaaS Dashboard) — using the now clean, tested engine

### Long-term
- PyPI publish (`twine upload dist/*`)
- Add new scenarios when needed (e-commerce funnel? marketing attribution?)
- Maintain repo: respond to issues, accept PRs, version bumps

---

## 9. COMMUNICATION PROTOCOL WITH THE AGENT

### When the agent asks for a decision
Respond immediately. Do not leave the agent hanging — long pauses risk session expiry and context loss.

### When the agent is stuck (3 failed attempts)
Say explicitly: "Stop. Use brainstorming skill to think about this differently before continuing." That activates the Superpowers escape hatch.

### When the agent claims "all tests pass"
Run `pytest` locally yourself. Do not trust the agent — `verification-before-completion` skill forces it to run the command and show output, but verification on your end is always valuable.

### When the agent scans a large repo (Phase 1)
Let it work — do not interrupt. Phase 1 may take 1–2h; that is normal. The output is a comprehensive report, not a quick scan.

---

## 10. CHECKLIST: AM I READY TO START?

Before opening the Phase 1 prompt, check:

- [ ] Superpowers installed (full)
- [ ] 4 selected ECC skills installed (selective)
- [ ] Local clone of `synth-datagen` from latest main
- [ ] Python 3.11+ with all tools available in PATH (3.12 preferred)
- [ ] You know the seed used for Kupferkanne (to validate backward compat in Phase 2)
- [ ] `prompts/` folder in repo with 4 files: `01_audit.md`, `02_refactor.md`, `03_tests.md`, `04_docs.md`
- [ ] 2–3 days of focused work reserved, or a 1-week plan at 2–3h per day
- [ ] Kupferkanne dashboard finished (so the `synth-datagen` audit does not block other work)
- [ ] GitHub access where the repo will eventually be public (if you plan to publish)

When all ✅, open a fresh Claude Code session and say:
```
"Read prompts/01_audit.md and execute it."
```

Phase 1 starts. Good luck.
