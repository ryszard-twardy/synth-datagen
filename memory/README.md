# memory/

Project-specific technical knowledge: gotchas, architectural decisions,
and debugging notes that future contributors (or future me) need to
know but aren't documented elsewhere.

## What goes here

- Tooling pitfalls (e.g. version coupling between dev tools)
- Test environment quirks (e.g. CI vs local rendering differences)
- Build/deploy issues with non-obvious causes
- Architectural decisions that aren't visible from code alone

## What does NOT go here

- Workflow preferences (use private notes)
- Future project plans (use private docs)
- Personal context unrelated to the codebase

## Format

One file per topic, kebab-case filename, markdown. Each file:

- **Title** — clear problem statement
- **Symptom** — what you saw
- **Root cause** — why it happened
- **Fix** — what to do
- **References** — commits, issues, docs

## Index

| File | One-line summary |
|---|---|
| [`ruff-pin-coupling.md`](ruff-pin-coupling.md) | The pre-commit `ruff` rev must match the ruff installed via the `[test]` extra, or CI fights itself across pushes. |
| [`cli-tests-ansi-on-ci.md`](cli-tests-ansi-on-ci.md) | Typer `CliRunner` substring asserts on `--help` output need `strip_ansi()` because Rich emits ANSI on Ubuntu CI but not local Windows. |
| [`precommit-checkyaml-mkdocs.md`](precommit-checkyaml-mkdocs.md) | `mkdocs.yml` with `pymdownx` Python-name tags trips `pre-commit/check-yaml` (uses `yaml.safe_load`); `pytest` and `mkdocs build --strict` both pass while CI fails. |
| [`version-coupling.md`](version-coupling.md) | `pyproject.toml` `[project] version` and `src/synth_datagen/__init__.py.__version__` are two sources of truth — every release commit must bump both together. |
| [`pydantic-v2-validator-assignment.md`](pydantic-v2-validator-assignment.md) | Inside a Pydantic v2 `@model_validator(mode='after')`, use `object.__setattr__(self, ...)` for self-assignment — direct `self.field = value` re-enters validation. |
| [`spawn-slot-pattern.md`](spawn-slot-pattern.md) | RNG engines should derive `master.spawn(N)` count from `len(_STREAM_LABELS)` rather than hardcoded literals; pin the labels tuple in a regression test. |
| [`cross-platform-python-path.md`](cross-platform-python-path.md) | Subprocess shell-outs to Python MUST use `sys.executable`; hardcoded `.venv/Scripts/python.exe` is Windows-only and fails on Ubuntu CI. |

When adding a new entry, prepend a row to the table above and add a
brief note in the relevant CHANGELOG.md `[Unreleased]` block under
`Changed` if the entry encodes a new convention.
