# Cross-platform Python path — `sys.executable`, never `.venv/Scripts`

When a script or test shells out to a Python interpreter via
`subprocess.run([...])`, the first arg MUST be `sys.executable`,
NOT a hardcoded path like `.venv/Scripts/python.exe` (Windows-only)
or `.venv/bin/python` (POSIX-only). The venv layout differs across
platforms, so any hardcoded path is OS-locked.

## Symptom

CI Ubuntu fails `subprocess.run(...)` with:

```
FileNotFoundError: [Errno 2] No such file or directory:
'<repo>/.venv/Scripts/python.exe'
```

…while the same code passes locally on Windows. The bug is invisible
on a Windows-only developer machine — it only surfaces when CI (or
any non-Windows leg) actually invokes the subprocess path.

## Root cause

Two issues stack:

1. The Python venv layout is platform-specific: Windows uses
   `Scripts/`, POSIX uses `bin/`. A hardcoded literal can only
   target one.
2. Even on the "correct" platform, hardcoding `.venv/...` assumes
   a specific venv location. CI runners, Tox environments, system
   Python invocations, and uv-managed venvs all break the
   assumption.

`sys.executable` is the absolute path to the interpreter currently
running. It's already correct on every platform, every venv layout,
and every CI runner — no manual stitching needed.

## Fix

```python
# WRONG — Windows-only, repo-relative:
PYTHON = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")

# RIGHT — cross-platform:
import sys
PYTHON = sys.executable
```

Before committing any new subprocess shell-out, grep:

```bash
grep -rn "\.venv/Scripts" scripts/ tests/
grep -rn "\.venv/bin" scripts/ tests/
```

Both should return zero matches in code paths. Hits in
`README.md` / `CONTRIBUTING.md` for user-facing dev-setup instructions
are fine — those are documentation, not executed paths.

## The blind spot that lets this slip

A hardcoded venv path can sit in the codebase for a whole release
cycle if no CI test exercises the subprocess path on the wrong
platform. Phase 5 introduced the bug in `scripts/baseline_diff.py`
during a saas_v3 capture, but the Phase-5 CI only ran the `compare`
step (CSV-hash walking, no subprocess). Phase 6 added a new test
that actually invoked the script's subprocess path, and it failed
on all three Ubuntu matrix legs immediately — caught at the
final-CI-matrix-verification gate, not after release.

**Lesson:** if a new commit adds a CI-invoked test that shells out
to `python -m synth_datagen.cli ...` (or any Python child process),
double-check the subprocess command's first argument BEFORE pushing.
The grep takes 2 seconds and prevents a CI red light + force-push
round trip.

## References

- Python docs: <https://docs.python.org/3/library/sys.html#sys.executable>
- Live example after fix: `scripts/baseline_diff.py` (post-Phase-6 hotfix)
- Phase 6 commit: `fix(scripts): use sys.executable for cross-platform Python path`
