# Version-string coupling — `pyproject.toml` ↔ `__init__.py`

The package version lives in two places and they must be bumped in
the same commit: `[project] version` in `pyproject.toml` and
`__version__` in `src/synth_datagen/__init__.py`.

## Symptom

After a release commit, `synth_datagen.__version__` reports a
different string than `importlib.metadata.version("synth-datagen")`.
No test catches it because there is no parity assertion; the drift
only surfaces when someone reads the wrong source of truth in a bug
report or a downstream notebook.

Concrete history of the drift:

- v0.2.0 — `pyproject.toml` bumped to `0.2.0`, `__init__.py` left at
  `0.2.0-dev`. Drift introduced.
- v0.2.1 — `pyproject.toml` bumped to `0.2.1`, `__init__.py` still
  `0.2.0-dev`. Drift persisted across a whole release cycle.
- v0.3.0-dev — both files moved together (caught at the start of
  Phase 6).
- v0.3.0 — both files landed at `0.3.0` in the release-bump commit.

## Root cause

The project chose `pyproject.toml` as the canonical version source
back in Phase 4 but never enforced parity with the runtime
`__version__`. Conventional Commits / release scripts touched only
`pyproject.toml`; the `__init__.py` literal was edited by hand and
got forgotten.

## Fix

Every `chore(release)` commit MUST update both files in the same
diff. Review the diff before pushing the version bump and confirm
the two strings match.

```bash
# Sanity check before tagging:
grep -E '^version = "' pyproject.toml
grep -E '^__version__ = ' src/synth_datagen/__init__.py
```

A pre-commit hook that fails if the two strings disagree is a
candidate for v0.4.0+ (one-line shell or Python check). Until then,
manual review at version-bump time is the gate.

## References

- `pyproject.toml` `[project] version` (canonical source)
- `src/synth_datagen/__init__.py` `__version__` (runtime source)
- Phase 5 release commits — origin of the v0.2.0/v0.2.1 drift.
- Phase 6 commit `c09af3e` — `chore(release): bump version 0.3.0-dev -> 0.3.0`, the first release where both literals moved together.
