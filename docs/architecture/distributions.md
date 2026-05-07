# Distributions

How `synth-datagen` chooses values isn't usually random in the uniform sense — most fields are sampled from realistic distributions tuned per scenario. This page documents the patterns that actually live in the v0.2.0 codebase.

## The patterns in v0.2.0

| Pattern | When | Where in code |
|---|---|---|
| Weighted choice | Categorical with a known mix (segment, plan tier, status, MCC) | Inline `rng.choice(values, p=weights)` calls in each generator |
| Uniform choice | Categorical with no informative mix (loan term, store category) | Inline `rng.choice(values)` calls |
| Normal | Bounded numeric where mean + std are known (e.g. fintech `credit_score`) | `np.random.Generator.normal(mean, std, size)` |
| Period-windowed timestamps | Activity timestamps clamped to the configured period | Inline `rng.integers(start_ts, end_ts)` plus per-scenario reweighting |
| Seasonality reweighting | Monthly-shard scenarios (`kupferkanne-rfm`, `monthly-sales`) | YAML-driven multipliers in `kupferkanne_rfm_config.py` and `monthly_sales_profile.py` |

## Weighted choice

Most categorical fields use `numpy.random.Generator.choice(values, p=weights)`. The weights are hardcoded from plausible business mixes — not measured against any specific corporate dataset. They are intentionally **plausible defaults**, not benchmarks.

For example, retail customer segments are drawn with hardcoded fractions in [`generators/retail_builder.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/generators/retail_builder.py); fintech merchant categories follow a similar inline pattern in [`generators/fintech.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/generators/fintech.py).

Want to override the mix? For now, fork the generator and edit. A v0.3.x design goal is to surface segment weights as YAML-driven config — the same pattern the `kupferkanne-rfm` sub-app already uses for its archetype mixes.

## Uniform choice

When there's no business reason to weight one option over another — loan term in months, store category, product category — the generator just calls `rng.choice(values)` with no `p=`. That gives uniform sampling across the option list. See [`generators/fintech.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/generators/fintech.py) for `term = int(self.rng.choice([12, 24, 36, 48, 60, 120, 180, 240, 360]))`.

## Normal

Numeric fields with a known mean and spread use `rng.normal(mean, std, size)`. The current consumer is `fintech.py::credit_score` — `np.round(self.rng.normal(690, 85, row_count))` produces a credit-score distribution centred on 690 with std 85, matching the well-known shape of US FICO scores. Values aren't truncated to the FICO bounds [300, 850] — about 0.4 % of rows fall outside that range, which is realistic noise for a synthetic ledger.

A more general rejection-sampling helper (truncated normal with strict bounds) is on the v0.3.x backlog — currently each generator handles bounds inline if it needs them.

## Period-windowed timestamps

Every fact table that carries a timestamp draws it from the configured generation period (`config.period.start_date`, `config.period.end_date`). The base draw is uniform-on-period via `rng.integers(start_ts, end_ts, size)`; some scenarios then reweight:

- **Retail orders** are biased toward weekends and end-of-month via the segment-aware logic in `retail_builder.py`.
- **Fintech transactions** are emitted in chronological order (post-sort) so account balances reconcile after a running-sum pass.
- **SaaS events** distribute across the period without specific weekday weighting in v0.2.0; promoting that pattern from `kupferkanne-rfm` to the unified scenarios is open work.

## Seasonality reweighting (sub-apps)

The `kupferkanne-rfm` and `monthly-sales` sub-apps drive seasonality from YAML rather than from hardcoded hooks. See `configs/kupferkanne_rfm_v3.yaml` for the `seasonality` block (per-month multipliers) and the `acquisition` block (per-phase customer acquisition rate). The same pattern is used by `monthly_sales_profile.py` for the monthly-sales sub-app.

Promoting this YAML pattern to the unified scenarios (so `synth-datagen retail` could accept a seasonality config) is a v0.3.x backlog item.

## Calibration disclaimer

These distributions are **plausible defaults**, not measured against any specific corporate dataset. They produce data that is *interesting* (statistically distinguishable from `rng.uniform`) and *realistic* (doesn't surprise an analyst), but they are not a benchmark.

A future v0.3.0 release will introduce a `pharma` scenario with explicitly-cited benchmark sources (DESTATIS, PHAGRO, IQVIA, vfa, Pharmalotse). Until then, treat the existing scenarios as "looks-real-enough for ETL practice" rather than "matches industry X."

## How distributions interact with `--data-quality`

The `--data-quality` levels do not change the underlying clean distribution — they corrupt the output of clean generation according to a separate set of probabilities. See [Architecture › Quality injection](quality-injection.md) for that layer.
