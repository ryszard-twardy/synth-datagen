# Version-string coupling – `pyproject.toml` and runtime `__version__`

`src/synth_datagen/__init__.py.__version__` is single-sourced from
package metadata (`importlib.metadata.version("synth-datagen")`). It
is no longer a hand-maintained literal and cannot drift from the
installed distribution on its own.

## Symptom (historical)

Before the fix, `synth_datagen.__version__` could report a different
string than `[project].version` in `pyproject.toml` after a release
commit. No test caught it because there was no parity assertion; the
drift only surfaced when someone read the wrong source of truth in a
bug report or a downstream notebook.

Concrete history of the drift:

- v0.2.0 – `pyproject.toml` bumped to `0.2.0`, `__init__.py` left at
  `0.2.0-dev`. Drift introduced.
- v0.2.1 – `pyproject.toml` bumped to `0.2.1`, `__init__.py` still
  `0.2.0-dev`. Drift persisted across a whole release cycle.
- v0.3.0-dev – both files moved together (caught at the start of
  Phase 6).
- v0.3.0 – both files landed at `0.3.0` in the release-bump commit.
- v0.3.2 – `pyproject.toml` bumped to `0.3.2`, `__init__.py` left at
  `0.3.1`. Third occurrence; flagged by Codex review on PR #15,
  tracked as issue #16.

## Root cause (historical)

The project chose `pyproject.toml` as the canonical version source
back in Phase 4 but never enforced parity with the runtime
`__version__`. Conventional Commits / release scripts touched only
`pyproject.toml`; the `__init__.py` literal was edited by hand and
got forgotten.

## Fix

Single-source the runtime version instead of hand-maintaining a
second literal: `__init__.py` now reads
`importlib.metadata.version("synth-datagen")`, falling back to the
non-version literal `"unknown"` if the package is not installed (so a
missing install fails loudly instead of reporting a stale version).
`tests/test_version_consistency.py` asserts `synth_datagen.__version__`
equals `[project].version` read live from `pyproject.toml` via
`tomllib`, so a future divergence fails the suite instead of shipping
silently.

Remaining manual version-value sites (not wired to metadata):

- `pyproject.toml` `[project].version` – canonical source; every
  release commit bumps this.
- `README.md` citation block – separate, unrelated literal, same
  defect class.

## References

- `pyproject.toml` `[project].version` (canonical source)
- `src/synth_datagen/__init__.py` `__version__` (derived via
  `importlib.metadata`)
- `tests/test_version_consistency.py` (parity guard)
- Phase 5 release commits – origin of the v0.2.0/v0.2.1 drift.
- Phase 6 commit `c09af3e` – `chore(release): bump version 0.3.0-dev -> 0.3.0`, the first release where both literals moved together.
- Issue #16 / PR #15 Codex review – origin of the v0.3.2 drift and the metadata single-source fix.
