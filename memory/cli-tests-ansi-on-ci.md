# CLI tests — ANSI escapes on CI

Typer `CliRunner.invoke(...)` substring asserts on `--help` output
need `strip_ansi()` because Rich emits ANSI escapes on Ubuntu CI but
not on local Windows.

## Symptom

Tests in `tests/test_cli_startup.py` and `tests/test_unified_cli.py`
that assert against the `--help` output:

```python
result = runner.invoke(app, ["generate", "--help"])
assert "--profile-config" in result.output   # ← passes locally, FAILS on CI
```

…pass on local Windows. On Ubuntu CI they fail with the literal flag
appearing nowhere in `result.output`. Inspecting `repr(result.output)`
on CI shows the flag is rendered with embedded SGR escapes:

```
'\x1b[1;36m-\x1b[0m\x1b[1;36m-profile\x1b[0m\x1b[1;36m-config\x1b[0m'
```

The colour-reset boundaries split the literal substring `--profile-config`
across multiple ANSI segments, so plain `in` matching never finds it.

## Root cause

Typer 0.16+ pipes Rich's `force_terminal` decision through to its
renderer. `CliRunner` is non-TTY but Rich on Ubuntu still writes
colours regardless. Local Windows `CliRunner` produces clean text,
which masks the bug locally — the test passes for one developer and
fails on a different OS.

## Fix

Wrap any `result.output` assertion against auto-generated `--help`
text with the `strip_ansi()` helper:

```python
from tests.helpers import strip_ansi

result = runner.invoke(app, ["generate", "--help"])
output = strip_ansi(result.output)
assert "--profile-config" in output
```

`strip_ansi()` is a no-op on plain text, so applying it unconditionally
is safe. It lives in `tests/helpers.py` and re-exports the regex from
the standalone fixture.

**When NOT needed:** assertions against `result.exit_code`, against
non-Rich-rendered output (e.g. `"Layout must be one of:"` printed via
plain `typer.echo`), or against custom error messages emitted before
the Rich rendering pipeline. Only auto-generated `--help` text passes
through Rich.

## References

- Helper: `tests/helpers.py::strip_ansi`
- Hotfix that introduced the helper + fixed the four broken assertions:
  commit `84e0b13` — `fix(tests): strip ANSI escapes before CLI output
  assertions`
- Originally surfaced in the post-Phase-3 CI hotfix that produced
  `ec8b5e6` on `main`.
