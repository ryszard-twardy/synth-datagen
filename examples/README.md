# Examples

Runnable end-to-end scripts, one per scenario. Each has been verified to
execute on a fresh checkout against the development install
(`uv pip install -e ".[test]"`).

| Script | Scenario | Runtime | Output |
|---|---|---|---|
| `quickstart_retail.py` | retail | ~6 s | 21 files in `./out/retail/` (CSV + Parquet + DDL + dictionary + ERD) |
| `quickstart_saas.py` | saas with `data-quality=medium` | ~2 s | 10 files in `./out/saas/` |
| `kupferkanne_full.py` | kupferkanne-rfm (full 39-month period) | ~5 min | 83 files in `./out/kupferkanne/` |

Run any of them from the repo root:

```bash
python examples/quickstart_retail.py
python examples/quickstart_saas.py
python examples/kupferkanne_full.py
```

Each script header documents the equivalent `synth-datagen` CLI invocation
so you can switch to the shell form once you understand the Python API.

## How they were sized

Retail and SaaS use small `row_overrides` (a few hundred rows per fact
table) so the quickstart finishes in seconds. The Kupferkanne example
uses the **default** config from `configs/kupferkanne_rfm_v3.yaml` to
exercise the full monthly-shard pipeline; trim the `period` block in
that YAML for a faster run.

## Adding a new example

1. Match the import / call style of `quickstart_saas.py` (the simplest).
2. Verify it runs end-to-end and writes files before committing.
3. Update the table above and link from the README "Examples" section.
4. Keep it ≤ ~60 lines so readers can scan the whole script at once.
