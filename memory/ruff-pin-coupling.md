# ruff version coupling

The pre-commit `ruff` rev must match the `ruff` installed via the `[test]`
extra, or CI fights itself across pushes.

## Symptom

CI starts failing on the **format-check** step right after an unrelated
dependency bump or a `pip install -U` cycle, with errors like:

```
ruff format --check .
Would reformat: src/synth_datagen/<file>.py
1 file would be reformatted
```

…on a file you did not touch. Locally, `ruff format .` rewrites it.
You commit the rewrite. Next push, CI complains again about a different
line in the same file. Every commit one ruff rewrites, the other reverts.

## Root cause

The repo runs `ruff` twice on every push:

1. **`pre-commit run --all-files`** (CI's 3.12 matrix leg only) — uses
   the `ruff` version pinned by `rev:` in `.pre-commit-config.yaml`.
2. **`ruff format --check .`** (every matrix leg, separate CI step) —
   uses the `ruff` installed by `pip install -e ".[test]"`.

The `[test]` extra in `pyproject.toml` has **no upper bound** on `ruff`
(`"ruff>=0.5.0"`), so transitive solves can pick up newer ruffs that
change formatting style. The pre-commit hook's `rev:` is pinned
independently and drifts. When the two diverge, every commit one
formatter rewrites, the other reverts.

The specific style change that triggered this in our history was the
multi-line `assert (cond), "msg"` rewrite between ruff 0.7 and 0.15.

## Fix

When bumping `ruff` **anywhere** — `[test]` extras in `pyproject.toml`,
lockfile regeneration, or `pre-commit autoupdate` — bump it in **both**
places to the **same** version.

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.15.12   # MUST MATCH the ruff installed by [test] in pyproject.toml
  hooks:
    - id: ruff
      args: ["--fix"]
    - id: ruff-format
```

The comment block above the `astral-sh/ruff-pre-commit` entry in
`.pre-commit-config.yaml` carries this warning explicitly.

## References

- Hotfix that aligned the two pins: commit `708318c` —
  `build(pre-commit): bump ruff hook to v0.15.12 to match runtime`
- Comment block: `.pre-commit-config.yaml` lines 28–35
- Originally surfaced in the post-Phase-3 CI hotfix that produced
  `ec8b5e6` on `main`.
