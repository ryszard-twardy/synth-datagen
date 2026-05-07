# Logistics

A 7-table model of a multi-warehouse, multi-carrier shipping operation. Inventory levels drive shipment composition; freight costs are internally consistent with carrier rate cards and shipment weight/volume.

## Tables

| Table | Kind | Default rows (no `--rows` override) | Notes |
|---|---|---|---|
| `warehouses` | dim | 100 | Location, type (DC / cross-dock / 3PL) |
| `suppliers` | dim | 500 | Country, lead time, OTD score |
| `products` | dim | 3,000 | SKU, weight, volume, hazmat flag |
| `inventory` | fact | 10,000 | (warehouse_id, product_id) on-hand snapshots |
| `carriers` | dim | 50 | Mode (truck / air / sea / parcel), lanes, rate card hash |
| `shipments` | fact | 50,000 | Origin warehouse, destination, carrier, freight cost |
| `shipment_items` | fact | 120,000 | (shipment_id, product_id, quantity) — averages ~2.4× `shipments` |

The defaults above match `src/synth_datagen/generators/logistics.py` at v0.2.0.

## Sample command

```bash
synth-datagen logistics \
    --seed 42 \
    --output ./out/logistics \
    --rows shipments=300,shipment_items=900 \
    --export-parquet
```

## Schema highlights

- **`shipments.freight_cost`** derives from `weight × distance × carrier_rate × surcharges`, where `surcharges` are realistic (fuel, residential, hazmat). Distinct from a uniform-random freight cost — useful when you want to demonstrate cost-allocation logic that survives sanity checks.
- **`shipment_items` quantities** never exceed the `inventory` row for the (warehouse, product) pair at the shipment's `created_at`. (Verified by the inventory-coverage Hypothesis property in CI.)
- **`inventory`** is a snapshot, not a ledger — but the snapshot is consistent with the shipment fact: `on_hand_qty` reflects post-shipment levels for the simulated period.
- **Carriers** carry a `rate_card_hash` so you can group shipments that priced under the same rate revision.

## Realistic operational quirks

When `--data-quality` ≥ `medium`:

- Some shipments lack a `delivered_at` (missing scan event).
- Some `shipment_items.quantity` overshoot inventory by small amounts (oversells corrected at fulfilment).
- Carrier rate cards drift mid-period — you'll see the same lane priced differently before/after a hash change.
- A few shipments have `actual_delivered_at` before `scheduled_delivered_at` — yes, that does happen with timezone bugs in real systems.

## Python API equivalent

```python
from pathlib import Path

from synth_datagen.config import (
    DataQuality, DataQualityConfig, Dialect,
    GeneratorConfig, Scenario, SchemaType,
)
from synth_datagen.pipeline import run_pipeline

config = GeneratorConfig(
    scenario=Scenario.LOGISTICS,
    schema_type=SchemaType.STAR,
    dialect=Dialect.POSTGRES,
    seed=42,
    output_dir=Path("./out/logistics"),
    row_overrides={"shipments": 300, "shipment_items": 900},
    export_parquet=True,
)
run_pipeline(config)
```

## Determinism

Like every other scenario, `--seed` fully determines output. The byte-equality test lives at `tests/test_logistics_realism.py::test_logistics_csv_byte_equality`.
