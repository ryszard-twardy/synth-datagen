# Security policy

## Supported versions

`synth-datagen` follows [Semantic Versioning](https://semver.org/). Only
the latest published minor version receives security fixes.

| Version | Supported |
|---|---|
| 0.3.x | ✅ |
| 0.2.x | ✅ — security fixes through 2026-06-07 (30-day grace after 0.3.0 release) |
| < 0.2 | ❌ (pre-audit; not on PyPI) |

0.3.0 shipped 2026-05-08. The 0.2.x line continues to receive
security patches until 2026-06-07, then drops out of support. When
the next minor version (0.4.0) ships, 0.3.x will move to the same
30-day grace window.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Email the maintainer directly: <r.twardy@proton.me>. Use the
subject line `synth-datagen security: <short title>` so the report is
not filed in the wrong inbox.

Please include:

- A description of the vulnerability and its impact.
- The version (`pip show synth-datagen` or commit SHA) you observed it on.
- A minimal reproduction — the `--seed`, CLI command, or Python snippet
  that triggers the issue.
- Any suggested fix or mitigation, if you have one.

Encrypted reports are welcome; request a PGP key in your initial mail
and one will be returned out of band.

## Disclosure timeline

| Day | Action |
|---|---|
| 0   | You report. |
| ≤ 2 | Maintainer acknowledges receipt. |
| ≤ 7 | Maintainer confirms reproducibility and assigns severity. |
| ≤ 30 | Fix released (patch version) for supported branches. |
| +0–14 | Coordinated public disclosure: GitHub Security Advisory + CHANGELOG entry crediting the reporter (unless you ask to remain anonymous). |

If a fix is going to take longer than 30 days, you'll get a status
update before the deadline with a revised target.

## Scope

In scope:

- Code-injection bugs in generated SQL DDL or DML output (the SQL
  exporter quotes values via `_sql_val` and treats table/column names
  as a closed config schema; bypasses are bugs).
- Path-traversal or arbitrary-write bugs in the exporters.
- YAML deserialisation issues in any of the YAML-driven sub-apps
  (Kupferkanne RFM, SaaS v3, monthly-sales, pharma) — we use
  `yaml.safe_load` everywhere; reports of unsafe loads are bugs.
- Pickle / arbitrary-code-execution surfaces — there should be none;
  if you find one, that's a bug.
- Denial-of-service via pathological config values that bypass Pydantic
  validation.

Out of scope:

- The intentional `--data-quality {light,medium,heavy}` injection — it
  is supposed to produce malformed values; that is the whole point.
- Supply-chain issues in upstream dependencies — report those to the
  upstream project (e.g. `pandas`, `numpy`, `pyarrow`) and we'll bump
  the pin once a fixed version ships.
- Performance issues that aren't security-relevant — open a normal
  issue.

Thank you for helping keep `synth-datagen` users safe.
