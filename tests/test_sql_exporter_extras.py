"""Extra coverage for SqlExporter (P7 coverage hardening).

Existing ``tests/test_exporters.py::TestSqlExporter`` covers the basic DDL
path — these tests add the previously-uncovered branches: dialect-specific
DROP TABLE / VARCHAR length, the DML INSERT path, and the value-encoder
``_sql_val`` (NULL / NaN / bool / numeric / quoted string).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from synth_datagen.config import (
    ColumnConfig,
    DataQuality,
    DataQualityConfig,
    Dialect,
    DType,
    GeneratorConfig,
    Scenario,
    SchemaType,
    TableConfig,
)
from synth_datagen.exporters.sql_exporter import SqlExporter, _sql_val
from synth_datagen.schema_builder import SchemaBuilder, SchemaGraph


def _config(
    tmp_path: Path, dialect: Dialect, *, export_dml: bool = False
) -> GeneratorConfig:
    return GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=dialect,
        seed=42,
        output_dir=tmp_path,
        chunk_size=500,
        row_overrides={},
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_dml=export_dml,
    )


def _simple_graph(
    tmp_path: Path, dialect: Dialect
) -> tuple[SqlExporter, SchemaGraph, TableConfig]:
    config = _config(tmp_path, dialect)
    exporter = SqlExporter(config)
    table = TableConfig(
        name="customers",
        row_count=2,
        pk_column="id",
        columns=[
            ColumnConfig(name="id", dtype=DType.VARCHAR, nullable=False, unique=True),
            ColumnConfig(name="name", dtype=DType.VARCHAR, nullable=False),
        ],
    )
    graph = SchemaBuilder(config).build([table], [])
    return exporter, graph, table


class TestDropTableDialect:
    """Line 117 — Postgres CASCADE vs other dialects."""

    def test_postgres_drop_uses_cascade(self, tmp_path: Path) -> None:
        exporter, graph, _ = _simple_graph(tmp_path, Dialect.POSTGRES)
        ddl = exporter.generate_ddl(graph)
        assert 'DROP TABLE IF EXISTS "customers" CASCADE' in ddl

    def test_sqlite_drop_omits_cascade(self, tmp_path: Path) -> None:
        exporter, graph, _ = _simple_graph(tmp_path, Dialect.SQLITE)
        ddl = exporter.generate_ddl(graph)
        assert 'DROP TABLE IF EXISTS "customers";' in ddl
        assert "CASCADE" not in ddl


class TestVarcharDialect:
    """Lines 121-126 — VARCHAR has a length on POSTGRES/MYSQL/SQLSERVER but
    not SQLITE (line 122-123 ``if SQLITE -> base``)."""

    def test_sqlite_varchar_no_length(self, tmp_path: Path) -> None:
        exporter, graph, _ = _simple_graph(tmp_path, Dialect.SQLITE)
        ddl = exporter.generate_ddl(graph)
        # SQLite maps VARCHAR -> TEXT and skips the (n) suffix.
        assert "TEXT" in ddl
        # No length suffix appears anywhere on the customers columns.
        for line in ddl.splitlines():
            if "name" in line and "TEXT" in line:
                assert "(" not in line.split("TEXT")[1].split(",")[0]

    def test_postgres_varchar_uses_default_length(self, tmp_path: Path) -> None:
        exporter, graph, _ = _simple_graph(tmp_path, Dialect.POSTGRES)
        ddl = exporter.generate_ddl(graph)
        # The exporter falls back to 255 when max_length is unset on the column.
        assert "VARCHAR(255)" in ddl

    def test_postgres_varchar_respects_max_length(self, tmp_path: Path) -> None:
        config = _config(tmp_path, Dialect.POSTGRES)
        exporter = SqlExporter(config)
        table = TableConfig(
            name="t",
            row_count=1,
            pk_column="id",
            columns=[
                ColumnConfig(
                    name="id", dtype=DType.VARCHAR, nullable=False, unique=True
                ),
                ColumnConfig(
                    name="code", dtype=DType.VARCHAR, nullable=False, max_length=8
                ),
            ],
        )
        graph = SchemaBuilder(config).build([table], [])
        ddl = exporter.generate_ddl(graph)
        assert "VARCHAR(8)" in ddl


class TestDmlExport:
    """Lines 105-108, 154-167 — DML INSERT path through ``export``."""

    def test_export_with_dml_writes_insert_statements(self, tmp_path: Path) -> None:
        config = _config(tmp_path, Dialect.POSTGRES, export_dml=True)
        exporter = SqlExporter(config)
        table = TableConfig(
            name="t",
            row_count=2,
            pk_column="id",
            columns=[
                ColumnConfig(
                    name="id", dtype=DType.VARCHAR, nullable=False, unique=True
                ),
                ColumnConfig(name="qty", dtype=DType.INT, nullable=False),
            ],
        )
        graph = SchemaBuilder(config).build([table], [])
        df = pd.DataFrame({"id": ["A", "B"], "qty": [1, 2]})
        path = exporter.export(graph, [(table, iter([df]))])
        content = path.read_text(encoding="utf-8")
        assert 'INSERT INTO "t" ("id", "qty") VALUES' in content
        assert "DML" in content

    def test_export_without_dml_omits_inserts(self, tmp_path: Path) -> None:
        config = _config(tmp_path, Dialect.POSTGRES, export_dml=False)
        exporter = SqlExporter(config)
        table = TableConfig(
            name="t",
            row_count=2,
            pk_column="id",
            columns=[
                ColumnConfig(
                    name="id", dtype=DType.VARCHAR, nullable=False, unique=True
                ),
            ],
        )
        graph = SchemaBuilder(config).build([table], [])
        df = pd.DataFrame({"id": ["A", "B"]})
        path = exporter.export(graph, [(table, iter([df]))])
        content = path.read_text(encoding="utf-8")
        assert "INSERT INTO" not in content

    def test_inserts_chunk_at_batch_boundary(self, tmp_path: Path) -> None:
        """Lines 158-166 — ``range(0, len(rows), batch)`` generates multiple
        INSERT statements when the DataFrame exceeds ``batch`` rows."""
        config = _config(tmp_path, Dialect.POSTGRES, export_dml=True)
        exporter = SqlExporter(config)
        table = TableConfig(
            name="t",
            row_count=600,
            pk_column="id",
            columns=[
                ColumnConfig(
                    name="id", dtype=DType.VARCHAR, nullable=False, unique=True
                ),
            ],
        )
        graph = SchemaBuilder(config).build([table], [])
        df = pd.DataFrame({"id": [f"A-{i:04d}" for i in range(600)]})
        path = exporter.export(graph, [(table, iter([df]))])
        content = path.read_text(encoding="utf-8")
        # Default batch=500 -> 600 rows produce two INSERT statements.
        assert content.count('INSERT INTO "t"') == 2


class TestSqlValEncoder:
    """Lines 170-178 — every branch of ``_sql_val``."""

    def test_none_becomes_null(self) -> None:
        assert _sql_val(None) == "NULL"

    def test_nan_becomes_null(self) -> None:
        assert _sql_val(float("nan")) == "NULL"

    def test_true_becomes_TRUE(self) -> None:
        # Order-sensitive: ``isinstance(True, int)`` is True in Python, so
        # the source must check ``bool`` *before* ``int`` for this to
        # return "TRUE" instead of "1". This test (and ``test_false_*``)
        # pin that ordering invariant — if a refactor swaps the branches,
        # this fails first and names the regression.
        assert _sql_val(True) == "TRUE"

    def test_false_becomes_FALSE(self) -> None:
        assert _sql_val(False) == "FALSE"

    def test_int_passes_through_as_string(self) -> None:
        assert _sql_val(42) == "42"

    def test_float_passes_through_as_string(self) -> None:
        assert _sql_val(3.14) == "3.14"

    def test_plain_string_quoted(self) -> None:
        assert _sql_val("alpha") == "'alpha'"

    def test_string_with_apostrophe_doubled(self) -> None:
        """SQL standard: escape ' as ''."""
        assert _sql_val("O'Brien") == "'O''Brien'"
