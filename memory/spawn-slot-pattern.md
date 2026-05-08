# RNG spawn-slot pattern — derive count from `len(_STREAM_LABELS)`

When a scenario engine spawns child RNG streams via
`make_rng(seed, "scenario").spawn(N)`, derive `N` from
`len(_STREAM_LABELS)` rather than hardcoding the integer literal.

## Symptom

A scenario adds a new internal RNG stream (say, a new "compliance"
defect injector). The labels list is updated but the spawn count —
hardcoded as a literal `len(_ENGINE_RNG_LABELS) + 1` somewhere
else — is not. The new stream's RNG is silently the wrong slot, so
its bytes ride on top of an unrelated stream's state. No test fails
loudly; CSV bytes shift downstream from one specific table.

The saas_v3 engine has this fragility — it spawns
`len(_ENGINE_RNG_LABELS) + 1` streams to leave a slot for the
defects injector. The `+1` is a magic offset that doesn't auto-track
the labels, so adding a labelled stream without remembering the
invariant breaks byte-equality silently.

## Root cause

Spawn order and count are part of the byte-stable contract: the
N-th `.spawn()` returns a deterministic child seeded from the parent
sequence's state at draw N. If `N` and the labels list disagree, the
labels-to-streams mapping rotates, but no test compares the mapping
against an external source of truth. The bug surfaces only at
baseline-diff time.

## Fix

Pharma got this right (Phase 6). All streams — including the
quality / defect stream — are listed in a single tuple, and the
spawn count is derived from its length:

```python
# src/synth_datagen/pharma/engine.py
_STREAM_LABELS: tuple[str, ...] = (
    "accounts", "reps", "territories", "orders",
    "products", "engagement", "quality", "regional",
)

def make_pharma_streams(base_seed: int) -> dict[str, np.random.Generator]:
    master = make_rng(base_seed, "pharma")
    children = master.spawn(len(_STREAM_LABELS))   # auto-tracks the labels
    return dict(zip(_STREAM_LABELS, children))
```

Adding a new stream is one edit (append to the tuple) and the spawn
count auto-extends. Pin the tuple's exact contents in a regression
test so an accidental insertion in the middle is caught:

```python
def test_make_pharma_streams_returns_eight_named_streams() -> None:
    streams = make_pharma_streams(42)
    assert tuple(streams) == (
        "accounts", "reps", "territories", "orders",
        "products", "engagement", "quality", "regional",
    )
```

## How to apply to a new scenario

1. Define `_STREAM_LABELS: tuple[str, ...]` at module scope listing
   every concern, including defects/quality.
2. Use `master.spawn(len(_STREAM_LABELS))` — never a literal integer.
3. Add a regression test that pins the tuple's exact contents and order.
4. Document in the module docstring: **"Adding a new stream MUST
   append at the end."** Inserting in the middle shifts state for
   every downstream stream and breaks byte-equality for all prior
   seeds.

A v0.4.0+ candidate is to refactor saas_v3 to match this pattern.
The fix is a one-line change but bumps saas_v3 byte output once,
after which `scripts/baseline_diff.py` re-pins.

## References

- Live example: `src/synth_datagen/pharma/engine.py::_STREAM_LABELS`
- Regression test: `tests/pharma/test_engine.py::test_make_pharma_streams_returns_eight_named_streams`
- Anti-example: `src/synth_datagen/saas_v3/defects.py` (the `len(_ENGINE_RNG_LABELS) + 1` magic offset)
