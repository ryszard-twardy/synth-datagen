# pre-commit `check-yaml` on `mkdocs.yml`

`mkdocs.yml` with `pymdownx` Python-name tags trips
`pre-commit-hooks::check-yaml` (which uses `yaml.safe_load`). `pytest`
and `mkdocs build --strict` both pass; only the pre-commit hook fails.
On this repo's CI, that's the **py3.12 leg only** (`ci.yml:36-38`), so
the failure looks Python-version-specific when it isn't.

## Symptom

CI fails on the `pre-commit (3.12 only)` step with:

```
hook id: check-yaml
could not determine a constructor for the tag
'tag:yaml.org,2002:python/name:pymdownx.superfences.fence_code_format'
  in "mkdocs.yml", line 88, column 19
```

py3.11 and py3.13 matrix legs stay green (they don't run pre-commit).
Locally, `pytest --no-cov -q` passes (251+) and
`mkdocs build --strict` succeeds (no warnings). Pushing seems safe;
CI disagrees.

## Root cause

`pre-commit/pre-commit-hooks::check-yaml` parses every YAML file with
`yaml.safe_load`. Safe loading refuses Python-specific tags like:

```yaml
- pymdownx.superfences:
    custom_fences:
      - name: mermaid
        class: mermaid
        format: !!python/name:pymdownx.superfences.fence_code_format
```

`pytest` doesn't load `mkdocs.yml` at all. `mkdocs build --strict`
uses MkDocs's own YAML loader which knows how to construct the tag.
Neither exercises the `safe_load` path the pre-commit hook does, so
local "all green" doesn't predict CI's pre-commit step.

The CI workflow runs `pre-commit run --all-files` only on the py3.12
matrix leg (an intentional optimisation in `.github/workflows/ci.yml`
lines 36-38: "Run pre-commit hooks once on the 3.12 leg to catch 'I
forgot to install pre-commit locally' PRs cheaply"). That makes the
failure look like a Python-version bug when it's actually a
loader-choice bug that any leg would hit if it ran the same hook.

## Fix

Add a single-file exclude on the `check-yaml` hook in
`.pre-commit-config.yaml`:

```yaml
- id: check-yaml
  exclude: ^mkdocs\.yml$
```

**Do not use `--unsafe`** — that flag enables arbitrary Python object
construction across **every** YAML file in the repo (configs/,
.github/workflows/, tests/), which is the exact attack surface
`bandit` and `check-yaml` exist to narrow. The single-file exclude
keeps the safe-load discipline everywhere except the one file that
legitimately needs the Python-name tag.

`mkdocs build --strict` already exercises `mkdocs.yml` against MkDocs's
own loader, so syntax errors in that file are still caught — just by
a different hook on a different lane.

## General lesson

When **adding any new YAML or TOML config** to the repo (`mkdocs.yml`,
new files under `.github/workflows/`, new YAML under `configs/`),
run `pre-commit run --all-files` locally before pushing. `pytest` and
the file's specific tool (`mkdocs build`, `actionlint`, ruff for TOML,
etc.) use their own loaders and won't catch a `safe_load` failure in
`check-yaml`.

Pure-content edits to existing config files don't need the extra step
— the hook already passed once.

## References

- Hotfix that added the exclude: commit `9841d35` —
  `fix(pre-commit): exclude mkdocs.yml from check-yaml hook`
- Failed CI run that surfaced it (private archive):
  `25490446923` (docs job, py3.12 leg)
- The Mermaid custom-fence config in `mkdocs.yml` at the line
  numbers that triggered the failure (lines 86–90 in v0.2.0).
