"""
Tests for exporters: CSV file creation, SQL DDL content, SQLite queryability.
"""

from __future__ import annotations

import sqlite3

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
from synth_datagen.exporters.sql_exporter import SqlExporter
from synth_datagen.exporters.sqlite_exporter import SqliteExporter
from synth_datagen.generators.retail import RetailGenerator
from synth_datagen.schema_builder import SchemaBuilder
from synth_datagen.utils import seed_everything

_SMALL_OVERRIDES = {
    "dim_customers": 50,
    "dim_products": 30,
    "dim_stores": 10,
    "dim_date": 365,
    "dim_promotions": 15,
    "fact_orders": 100,
    "fact_order_items": 200,
    "fact_payments": 100,
    "bridge_order_promotions": 60,
}


@pytest.fixture(scope="module")
def export_setup(tmp_path_factory):
    """Generate data and run all exporters; return (graph, dfs, output_dir)."""
    tmp = tmp_path_factory.mktemp("export_test")
    config = GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp,
        chunk_size=500,
        row_overrides=_SMALL_OVERRIDES,
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_sqlite=True,
    )
    _, rng, faker = seed_everything(42)
    gen = RetailGenerator(config, rng, faker)
    raw_tables, raw_relations = gen.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_tables, raw_relations)

    fk_pools: dict = {}
    dfs: dict[str, pd.DataFrame] = {}
    for table in graph.topological_order():
        chunks = list(gen.generate_table(table, graph, fk_pools))
        df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        dfs[table.name] = df
        if table.pk_column in df.columns:
            fk_pools[f"{table.name}.{table.pk_column}"] = df[table.pk_column].to_numpy()

    # CSV
    csv_exp = CsvExporter(config)
    for table in graph.topological_order():
        csv_exp.export_table(table, iter([dfs[table.name]]))

    # SQL DDL
    sql_exp = SqlExporter(config)
    sql_exp.export(graph)

    # SQLite
    sqlite_exp = SqliteExporter(config)
    sqlite_exp.export(
        graph,
        [(t, iter([dfs[t.name]])) for t in graph.topological_order()],
    )

    return graph, dfs, tmp


class TestCsvExporter:
    def test_csv_files_created(self, export_setup):
        graph, dfs, out_dir = export_setup
        for table in graph.topological_order():
            csv_path = out_dir / f"{table.name}.csv"
            assert csv_path.exists(), f"Missing CSV: {csv_path}"

    def test_csv_row_count(self, export_setup):
        graph, dfs, out_dir = export_setup
        for table in graph.topological_order():
            csv_path = out_dir / f"{table.name}.csv"
            df_read = pd.read_csv(csv_path)
            expected = len(dfs[table.name])
            assert len(df_read) == expected, (
                f"{table.name}: CSV has {len(df_read)} rows, expected {expected}"
            )

    def test_csv_has_pk_column(self, export_setup):
        graph, dfs, out_dir = export_setup
        for table in graph.topological_order():
            csv_path = out_dir / f"{table.name}.csv"
            header = pd.read_csv(csv_path, nrows=0).columns.tolist()
            assert table.pk_column in header, (
                f"{table.name}: PK '{table.pk_column}' missing from CSV"
            )


class TestSqlExporter:
    def test_schema_sql_created(self, export_setup):
        _, _, out_dir = export_setup
        sql_path = out_dir / "schema.sql"
        assert sql_path.exists(), "schema.sql not found"

    def test_schema_sql_contains_create_table(self, export_setup):
        graph, _, out_dir = export_setup
        content = (out_dir / "schema.sql").read_text()
        for table in graph.topological_order():
            assert "CREATE TABLE" in content
            assert table.name in content, f"schema.sql missing table {table.name}"

    def test_schema_sql_contains_primary_key(self, export_setup):
        _, _, out_dir = export_setup
        content = (out_dir / "schema.sql").read_text()
        assert "PRIMARY KEY" in content

    def test_schema_sql_contains_foreign_key(self, export_setup):
        _, _, out_dir = export_setup
        content = (out_dir / "schema.sql").read_text()
        assert "FOREIGN KEY" in content


class TestSqliteExporter:
    def test_sqlite_db_created(self, export_setup):
        _, _, out_dir = export_setup
        db_path = out_dir / "retail.db"
        assert db_path.exists(), "SQLite .db file not found"

    def test_sqlite_tables_exist(self, export_setup):
        graph, _, out_dir = export_setup
        db_path = out_dir / "retail.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cursor.fetchall()}
        conn.close()
        for table in graph.topological_order():
            assert table.name in existing, f"SQLite DB missing table {table.name}"

    def test_sqlite_row_counts_match(self, export_setup):
        graph, dfs, out_dir = export_setup
        db_path = out_dir / "retail.db"
        conn = sqlite3.connect(str(db_path))
        for table in graph.topological_order():
            count = conn.execute(f'SELECT COUNT(*) FROM "{table.name}"').fetchone()[0]
            expected = len(dfs[table.name])
            assert count == expected, (
                f"{table.name}: SQLite has {count} rows, expected {expected}"
            )
        conn.close()
