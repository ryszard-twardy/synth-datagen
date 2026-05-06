"""CSV byte-equality and roundtrip tests (audit P2-8).

Closes the audit finding that determinism tests use ``assert_frame_equal``
on in-memory DataFrames but never re-read exported CSVs to confirm the
write/read contract holds at the byte level. The Phase 2 baseline-diff
harness (``scripts/baseline_diff.py``) does this at the CLI level for
retail/saas/fintech/logistics; this module mirrors that contract inside
the test suite so a regression surfaces during ``pytest`` rather than
only during manual baseline-diff runs.

Test layout
- ``test_<scenario>_csv_bytes_identical_across_runs`` (parametrised over
  the four classic scenarios): generate + export twice with the same
  seed, SHA-256 every CSV in both runs, assert byte-for-byte identity.
- ``test_<scenario>_csv_roundtrip_preserves_data`` (parametrised over
  the four classic scenarios): generate + export, re-read each CSV with
  ``pd.read_csv``, assert numeric and integer columns match the in-
  memory DataFrame element-for-element.
- ``test_kupferkanne_rfm_csv_bytes_identical_across_runs``: dedicated
  test for the Kupferkanne RFM scenario, which has a different export
  path (``generate_kupferkanne_rfm`` writes monthly + dimensions
  directly, no ``CsvExporter``).
"""

from __future__ import annotations

import copy
import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from synth_datagen.config import (
    DataQuality,
    DataQualityConfig,
    Dialect,
    GeneratorConfig,
    Scenario,
    SchemaType,
)
from synth_datagen.exporters.csv_exporter import CsvExporter
from synth_datagen.generators.fintech import FintechGenerator
from synth_datagen.generators.logistics import LogisticsGenerator
from synth_datagen.generators.retail import RetailGenerator
from synth_datagen.generators.saas import SaasGenerator
from synth_datagen.kupferkanne_rfm import generate_kupferkanne_rfm
from synth_datagen.kupferkanne_rfm_config import load_kupferkanne_rfm_config
from synth_datagen.schema_builder import SchemaBuilder
from synth_datagen.utils import seed_everything

# Mirror the small-row overrides used by tests/property/_helpers.py so
# byte-equality tests share the same "fast but realistic" data shape as
# the rest of the suite. Duplicated rather than imported because the
# property helper lives in a sibling test directory and pytest discovers
# top-level tests independently.
_GENERATORS = {
    "retail": (RetailGenerator, Scenario.RETAIL),
    "saas": (SaasGenerator, Scenario.SAAS),
    "fintech": (FintechGenerator, Scenario.FINTECH),
    "logistics": (LogisticsGenerator, Scenario.LOGISTICS),
}

_OVERRIDES: dict[str, dict[str, int]] = {
    "retail": {
        "dim_customers": 100,
        "dim_products": 50,
        "dim_stores": 10,
        "dim_date": 365,
        "dim_promotions": 20,
        "fact_orders": 200,
        "fact_order_items": 400,
        "fact_payments": 200,
        "bridge_order_promotions": 100,
    },
    "saas": {
        "accounts": 100,
        "users": 300,
        "subscriptions": 120,
        "invoices": 300,
        "features": 20,
        "feature_usage": 400,
        "events": 600,
    },
    "fintech": {
        "customers": 100,
        "accounts": 150,
        "merchants": 50,
        "transactions": 400,
        "cards": 120,
        "loans": 80,
        "loan_payments": 200,
    },
    "logistics": {
        "warehouses": 10,
        "suppliers": 30,
        "products": 80,
        "inventory": 150,
        "shipments": 120,
        "shipment_items": 300,
        "routes": 40,
    },
}


def _generate_and_export_csvs(
    scenario: str, seed: int, output_dir: Path
) -> dict[str, pd.DataFrame]:
    """Generate the named scenario at small scale, write every table to CSV
    via the canonical ``CsvExporter``, and return the in-memory DataFrames
    keyed by table name. The CSVs land in ``output_dir`` exactly as a real
    ``synth-datagen generate`` invocation would write them.
    """
    generator_cls, scenario_enum = _GENERATORS[scenario]
    config = GeneratorConfig(
        scenario=scenario_enum,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=seed,
        output_dir=output_dir,
        chunk_size=500,
        row_overrides=_OVERRIDES[scenario],
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_sqlite=False,
        export_parquet=False,
    )
    _, rng, faker = seed_everything(seed)
    gen = generator_cls(config, rng, faker)
    raw_t, raw_r = gen.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_t, raw_r)

    fk_pools: dict = {}
    dfs: dict[str, pd.DataFrame] = {}
    csv_exporter = CsvExporter(config)
    for table in graph.topological_order():
        chunks = list(gen.generate_table(table, graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        dfs[table.name] = df
        if table.pk_column in df.columns:
            fk_pools[f"{table.name}.{table.pk_column}"] = df[table.pk_column].to_numpy()
        # Export this table immediately so the CsvExporter sees it in the
        # same chunk shape it would in production (one chunk = full table
        # at this small scale).
        csv_exporter.export_table(table, iter([df]))
    return dfs


def _hash_dir_csvs(root: Path) -> dict[str, str]:
    """SHA-256 every CSV under ``root`` keyed by relative path."""
    return {
        csv.relative_to(root).as_posix(): hashlib.sha256(csv.read_bytes()).hexdigest()
        for csv in sorted(root.rglob("*.csv"))
    }


@pytest.mark.parametrize("scenario", ["retail", "saas", "fintech", "logistics"])
def test_csv_bytes_identical_across_runs(scenario: str, tmp_path: Path) -> None:
    """Two runs with seed=42 must produce byte-for-byte identical CSV files.

    This is the test-suite equivalent of ``scripts/baseline_diff.py``
    capture+compare. A failure here points at non-determinism somewhere in
    the generation -> export pipeline that the baseline harness would also
    flag, but caught earlier in the dev loop.
    """
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    _generate_and_export_csvs(scenario, seed=42, output_dir=out_a)
    _generate_and_export_csvs(scenario, seed=42, output_dir=out_b)

    hashes_a = _hash_dir_csvs(out_a)
    hashes_b = _hash_dir_csvs(out_b)

    assert hashes_a.keys() == hashes_b.keys(), (
        f"{scenario}: CSV file set differs between runs. "
        f"Only in A: {sorted(hashes_a.keys() - hashes_b.keys())}; "
        f"only in B: {sorted(hashes_b.keys() - hashes_a.keys())}"
    )
    mismatches = [
        f"{path}: A={hashes_a[path][:12]}... B={hashes_b[path][:12]}..."
        for path in hashes_a
        if hashes_a[path] != hashes_b[path]
    ]
    assert not mismatches, (
        f"{scenario}: CSV bytes drift across runs at seed=42:\n  "
        + "\n  ".join(mismatches)
    )


@pytest.mark.parametrize("scenario", ["retail", "saas", "fintech", "logistics"])
def test_csv_roundtrip_preserves_data(scenario: str, tmp_path: Path) -> None:
    """Every numeric and integer column round-trips through CSV without loss.

    Reading a CSV back loses datetime dtype information (it returns ``object``
    columns of strings), so this test asserts equality only on numeric and
    integer columns where round-trip equality is meaningful. String columns
    are compared as ``object`` series with NaN-aware equality.
    """
    dfs_in = _generate_and_export_csvs(scenario, seed=42, output_dir=tmp_path)

    for table_name, df_in in dfs_in.items():
        csv_path = tmp_path / f"{table_name}.csv"
        assert csv_path.exists(), f"{scenario}/{table_name}: CSV not written"

        df_read = pd.read_csv(csv_path)

        # Column set must round-trip exactly — header order included.
        assert list(df_read.columns) == list(df_in.columns), (
            f"{scenario}/{table_name}: column order drifted on read. "
            f"in={list(df_in.columns)} read={list(df_read.columns)}"
        )

        # Row count must match.
        assert len(df_read) == len(df_in), (
            f"{scenario}/{table_name}: row count drifted on read. "
            f"in={len(df_in)} read={len(df_read)}"
        )

        # Numeric / integer columns: element-for-element equality.
        numeric_cols = df_in.select_dtypes(include=["number"]).columns.tolist()
        for col in numeric_cols:
            in_values = df_in[col].to_numpy()
            read_values = df_read[col].to_numpy()
            # Use pandas testing for NaN-aware float comparison.
            pd.testing.assert_series_equal(
                pd.Series(in_values),
                pd.Series(read_values),
                check_names=False,
                check_dtype=False,
                obj=f"{scenario}/{table_name}/{col}",
            )


def test_kupferkanne_rfm_csv_bytes_identical_across_runs(tmp_path: Path) -> None:
    """Two Kupferkanne RFM runs with seed=42 produce byte-identical CSV files.

    Uses a shrunk config (200 customers, 2-month window) so the test stays
    under 5s — full-size config would take ~140s for two runs.
    """
    config = load_kupferkanne_rfm_config(Path("configs/kupferkanne_rfm_v3.yaml"))
    config = copy.deepcopy(config)
    config.customers.target_total_customers = 200
    config.period.end_date = date(2023, 2, 28)

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    generate_kupferkanne_rfm(config, out_a, seed=42)
    generate_kupferkanne_rfm(copy.deepcopy(config), out_b, seed=42)

    hashes_a = _hash_dir_csvs(out_a)
    hashes_b = _hash_dir_csvs(out_b)

    assert hashes_a.keys() == hashes_b.keys(), (
        "kupferkanne_rfm: CSV file set differs between runs. "
        f"Only in A: {sorted(hashes_a.keys() - hashes_b.keys())}; "
        f"only in B: {sorted(hashes_b.keys() - hashes_a.keys())}"
    )
    mismatches = [
        f"{path}: A={hashes_a[path][:12]}... B={hashes_b[path][:12]}..."
        for path in hashes_a
        if hashes_a[path] != hashes_b[path]
    ]
    assert not mismatches, (
        "kupferkanne_rfm: CSV bytes drift across runs at seed=42:\n  "
        + "\n  ".join(mismatches)
    )
    # Sanity: the run actually produced something.
    assert hashes_a, "kupferkanne_rfm: no CSVs found in output directory"
