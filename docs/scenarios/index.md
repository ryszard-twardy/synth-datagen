# Scenarios overview

`synth-datagen` ships with four built-in scenarios. Each is a star schema with realistic dim/fact/bridge structure; each accepts the same CLI surface (`--seed`, `--output`, `--rows`, `--data-quality`, exporter toggles).

| Scenario | Tables | Models |
|---|---|---|
| [Retail](retail.md) | 9 | E-commerce orders with customer segments, promotions, payments |
| [SaaS](saas.md) | 7 | B2B SaaS subscriptions, usage events, invoices |
| [Fintech](fintech.md) | 7 | Payment ledger with cards, merchants, loans |
| [Logistics](logistics.md) | 7 | Shipping with warehouses, carriers, inventory |

Plus three sub-apps mounted under the same root command:

```bash
synth-datagen monthly-sales generate ...      # period-windowed retail
synth-datagen kupferkanne-rfm generate ...    # monthly fact shards from YAML
synth-datagen saas-v3 generate ...            # audit-grade dirty CSV pipeline
```

The sub-apps are the same engine wired up to YAML configs (in [`configs/`](https://github.com/ryszard-twardy/synth-datagen/tree/main/configs)) for use cases that don't fit the single-flag CLI.

## Choosing a scenario

| If you need… | Pick |
|---|---|
| RFM analysis examples, customer-segment dashboards | [Retail](retail.md) or `kupferkanne-rfm` |
| Funnel / churn analysis, product analytics | [SaaS](saas.md) |
| Reconciliation, fraud signals, ledger validation | [Fintech](fintech.md) |
| Supply-chain / freight cost analysis | [Logistics](logistics.md) |
| Audit-grade dirty CSVs (per-check defect rates) | `saas-v3` |
| Monthly fact-table sharding (one CSV per month) | `kupferkanne-rfm` or `monthly-sales` |

## What every scenario gives you

- A **clean star schema** — at least one fact table, multiple dim tables, sometimes a bridge table.
- **Stable PK formats** — `CU00000001`, `OR00000001`, etc. — and `YYYYMMDD` integer date keys.
- **Cross-table coherence** — FK pools sampled from real PK pools; totals reconcile.
- **Per-scenario invariants** — covered by Hypothesis property tests in CI.
- **Deterministic output** — same `--seed` → same bytes.

For the architectural reasoning behind these guarantees, jump to [Architecture › RNG isolation](../architecture/rng-isolation.md) and [Architecture › Distributions](../architecture/distributions.md).
