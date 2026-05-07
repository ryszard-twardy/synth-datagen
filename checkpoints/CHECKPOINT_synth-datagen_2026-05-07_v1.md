# CHECKPOINT — synth-datagen 2026-05-07 (post-hotfix, pre-Phase 4)

## L0 INDEX
- L1.CORE — current state, blocker resolution, next step
- L2.DECISIONS — append-only (this thread: 3 entries)
- L2.RULES — append-only (this thread: 2 entries)
- L2.SCHEMA — unchanged → stub
- L2.PIPELINE — unchanged → stub
- L2.GLOSSARY — unchanged → stub
- L2.FILES — append-only (this thread: 2 entries)

## L1 CORE

**Project:** synth-datagen (Python CLI, synthetic business datasets).
**Repo:** X:\Python\projects\synth-datagen, GitHub ryszard-twardy/synth-datagen (private).
**Phase status:** Phase 1 audit ✅ | Phase 2 refactor ✅ (v0.2.0-rc1) | Phase 3 tests ✅ (v0.2.0-rc2) | Phase 4 docs READY TO START.

**Current branch state:**
- main @ ec8b5e6 — CI green (run 25479480080, all 3 matrix legs)
- feat/docs @ a646817 — one commit ahead, cherry-picked Phase 4 prompt extraction
- hotfix/ci-coverage-gate — merged, can be deleted

**Tags:** v0.1.0-preaudit, v0.2.0-rc1, v0.2.0-rc2.

**Tests:** 251 fast + 48 slow = 299. Coverage 94%.

**Hotfix outcome (resolved this session):**
3 commits applied to bring CI green:
- 708318c: bumped pre-commit ruff hook v0.7.4 → v0.15.12 + added `--markdown-linebreak-ext=md`
- 5dff34c: pre-commit auto-fixes (whitespace + EOF on 7 markdown files)
- 84e0b13: ANSI escape strip helper in tests/conftest.py + 4 test asserts updated

Merged to main via `--no-ff` ec8b5e6, pushed direct (sandbox override approved).

## L1 OPEN
- [?] Whether `feat/docs` should be branched per Phase 4 sub-task or single branch — defer to fresh session
- [?] MkDocs Material vs simpler docs/ folder — Phase 4 prompt specifies MkDocs

## L2 DECISIONS (append-only)

| date | decision | why (≤15w) |
|---|---|---|
| 2026-05-07 | Bump pre-commit ruff to v0.15.12 (Option A) over pinning runtime to v0.7.4 | pre-commit mirrors runtime, not reverse; avoids stale ruff |
| 2026-05-07 | Add `--markdown-linebreak-ext=md` to trailing-whitespace hook | preserves intentional 2-space hard breaks in prompts/ |
| 2026-05-07 | ANSI strip helper in tests/conftest.py over disabling Rich via env vars | environment-agnostic; works on Windows local + Ubuntu CI |

## L2 RULES (append-only)

| rule | rationale |
|---|---|
| When pre-commit and runtime install same tool, pin both to identical version | prevents formatter-vs-formatter loops between CI steps |
| CLI test assertions must `strip_ansi(result.output)` before substring match | Rich renders ANSI in CI Ubuntu CliRunner but not Windows local |

## L2 FILES (append-only)

| path | role | added |
|---|---|---|
| tests/conftest.py | shared `strip_ansi()` helper for CLI tests | 2026-05-07 (84e0b13) |
| prompts/audit/phase4_docs.md | Phase 4 prompt for fresh Claude Code session | 2026-05-07 (a646817, on feat/docs only) |
| memory/ruff-pin-coupling.md | dual-ruff CI pitfall reference | 2026-05-07 |
| memory/cli-tests-ansi-on-ci.md | strip_ansi pattern reference | 2026-05-07 |
| MEMORY.md | index of memory/ artifacts | 2026-05-07 |

## L2 SCHEMA → stub (unchanged)
## L2 PIPELINE → stub (unchanged)
## L2 GLOSSARY → stub (unchanged)
