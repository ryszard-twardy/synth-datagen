# Distributions

How `synth-datagen` chooses values isn't usually random in the uniform sense — most fields are sampled from realistic distributions tuned per scenario. This page documents the patterns used and why.

## The four patterns

| Pattern | When | Example |
|---|---|---|
| Weighted choice | Categorical with known mix | Customer segment (`new` 40 %, `casual` 35 %, `loyal` 20 %, `vip` 5 %) |
| Truncated normal | Bounded numeric with a target mean | Order line count (mean 3, min 1, max 12) |
| Power-law / Pareto | Long-tail counts | Account event volume, customer lifetime value |
| Calendar-aware | Seasonality, weekend dips, end-of-month spikes | Order date, payment date, login activity |

Implementations live next to each scenario generator — for example, retail discount-variation logic is in [`generators/retail_builder.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/generators/retail_builder.py) and SaaS event volume is in [`generators/saas.py`](https://github.com/ryszard-twardy/synth-datagen/blob/main/src/synth_datagen/generators/saas.py).

## Weighted choice

Most categorical fields use `numpy.random.Generator.choice(values, p=weights)`. The weights are hardcoded from plausible business mixes — not measured against any specific corporate dataset. They are intentionally **plausible defaults**, not benchmarks.

```python
segments = ["new", "casual", "loyal", "vip"]
weights = [0.40, 0.35, 0.20, 0.05]
customer_segments = rng.choice(segments, size=n, p=weights)
```

Want to override the mix? For now, fork the generator and edit. A v0.3.x design goal is to surface segment weights as YAML-driven config.

## Truncated normal

For bounded numeric fields (e.g. line items per order), the generator draws from a normal distribution and rejects values outside the bound until it has `n` valid samples:

```python
def truncated_normal(rng, mean, std, min_v, max_v, size):
    out = np.empty(size, dtype=int)
    n_filled = 0
    while n_filled < size:
        draw = rng.normal(mean, std, size=size * 2).round().astype(int)
        ok = draw[(draw >= min_v) & (draw <= max_v)]
        take = min(len(ok), size - n_filled)
        out[n_filled : n_filled + take] = ok[:take]
        n_filled += take
    return out
```

This avoids the bias you'd get from clipping (which piles density at the bounds). The exact helper used internally is in [`generators/_distributions.py`](https://github.com/ryszard-twardy/synth-datagen/tree/main/src/synth_datagen/generators).

## Power-law / Pareto

Counts that span orders of magnitude — total events per account, total order value per customer — are sampled from a Pareto. A small number of accounts dominate event volume; most accounts are quiet. This matches reality and stress-tests cardinality-sensitive aggregations.

```python
shape = 1.5  # tail-heaviness; lower = heavier tail
events_per_account = rng.pareto(a=shape, size=n_accounts) * scale
```

## Calendar-aware

Activity timestamps aren't uniform across the calendar:

- **Order dates** are biased toward weekends and end-of-month for retail; toward business hours weekdays for fintech.
- **SaaS login events** dip on weekends, spike on Mondays.
- **Promotion validity windows** cluster around realistic retail seasons (Black Friday, summer sales, January post-holiday).

Implementation: a base uniform draw is reweighted by a per-day multiplier table that lives next to each scenario.

## Calibration disclaimer

These distributions are **plausible defaults**, not measured against any specific corporate dataset. They produce data that's *interesting* (i.e. statistically distinguishable from `rng.uniform`) and *realistic* (i.e. doesn't surprise an analyst), but they aren't a benchmark.

A future v0.3.0 release will introduce a `pharma` scenario with explicitly-cited benchmark sources (DESTATIS, PHAGRO, IQVIA, vfa, Pharmalotse). Until then, treat the existing scenarios as "looks-real-enough for ETL practice" rather than "matches industry X."

## How distributions interact with `--data-quality`

The four `--data-quality` levels do not change the underlying clean distribution — they corrupt the output of clean generation according to a separate set of probabilities. See [Architecture › Quality injection](quality-injection.md) for that layer.
