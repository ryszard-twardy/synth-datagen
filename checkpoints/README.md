# checkpoints/

Session-end snapshots capturing project state, decisions, and resolved
blockers. One file per significant session.

## Naming

`CHECKPOINT_synth-datagen_YYYY-MM-DD_vN.md`

- Date: session end date
- Version: increments per same-day session (v1, v2…)

## Structure

Per userPreferences tiered 3-layer schema:
- L0 INDEX (table of contents)
- L1 CORE (current state, blockers, next step) + L1 OPEN ([?] uncertainties)
- L2 DECISIONS / RULES / SCHEMA / PIPELINE / GLOSSARY / FILES (append-only,
  stub if unchanged)

Total ≤2,500 words. Verbatim identifiers (SHAs, run IDs, paths).
`why:` ≤15w on each decision.

## Lifecycle

- Append-only: never edit a past checkpoint. Newer state goes in a new file.
- Living L2 artifacts (DECISIONS.md, RULES.md, etc.) at repo root may be
  updated; checkpoints reference them, not duplicate.
