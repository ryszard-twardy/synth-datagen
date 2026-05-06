"""Direct unit + roundtrip tests for ParquetExporter (P7 coverage hardening).

Pre-P7 coverage on ``src/synth_datagen/exporters/parquet_exporter.py`` was
27% — the module was reachable only through a full scenario run with
``export_parquet=True``, which no existing test exercised. These tests
exercise the exporter in isolation across every dtype branch in
``_sanitise_chunk`` and assert a Parquet roundtrip preserves the data.
"""

from __future__ import annotations

import datetime
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
from synth_datagen.exporters.parquet_exporter import (
    ParquetExporter,
    _sanitise_chunk,
)


def _make_config(tmp_path: Path) -> GeneratorConfig:
    """Minimal config sufficient for ParquetExporter to initialise."""
    return GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path,
        chunk_size=500,
        row_overrides={},
        data_quality=DataQualityConfig(level=DataQuality.NONE),
        export_parquet=True,
    )


def _make_table(name: str = "t1", pk: str = "id") -> TableConfig:
    return TableConfig(
        name=name,
        row_count=10,
        pk_column=pk,
        columns=[
            ColumnConfig(name=pk, dtype=DType.VARCHAR, nullable=False, unique=True)
        ],
    )


class TestSanitiseChunk:
    """Branches in ``_sanitise_chunk`` (lines 27-60)."""

    def test_datetime64_dtype_passes_through_untouched(self) -> None:
        df = pd.DataFrame({"ts": pd.to_datetime(["2024-01-01", "2024-02-29"])})
        out = _sanitise_chunk(df)
        assert pd.api.types.is_datetime64_any_dtype(out["ts"])

    def test_object_with_python_datetime_is_converted(self) -> None:
        # Force an object-dtype column holding python datetimes (pandas 3.x
        # would otherwise promote a datetime list straight to datetime64[us]).
        df = pd.DataFrame(
            {
                "ts": pd.Series(
                    [datetime.datetime(2024, 1, 1), datetime.datetime(2025, 6, 30)],
                    dtype=object,
                )
            }
        )
        assert pd.api.types.is_object_dtype(df["ts"])  # precondition
        out = _sanitise_chunk(df)
        assert pd.api.types.is_datetime64_any_dtype(out["ts"])

    def test_object_with_python_date_is_converted_to_timestamp(self) -> None:
        df = pd.DataFrame(
            {"d": [datetime.date(2024, 1, 1), datetime.date(2025, 6, 30)]}
        )
        assert pd.api.types.is_object_dtype(df["d"])  # precondition
        out = _sanitise_chunk(df)
        assert pd.api.types.is_datetime64_any_dtype(out["d"])

    def test_object_with_strings_falls_back_to_string(self) -> None:
        df = pd.DataFrame({"s": ["alpha", "beta", "gamma"]})
        out = _sanitise_chunk(df)
        assert out["s"].tolist() == ["alpha", "beta", "gamma"]

    def test_object_all_null_column_left_alone(self) -> None:
        """Lines 40-41: empty sample after dropna -> early continue.

        The contract is "leave the column untouched", so assert dtype and
        values are unchanged — not just that the column survived (which
        would still pass if the function nuked and re-added it)."""
        df = pd.DataFrame({"x": [None, None, None]}, dtype=object)
        out = _sanitise_chunk(df)
        assert "x" in out.columns
        assert out["x"].dtype == df["x"].dtype  # still object
        assert out["x"].isna().all()
        assert len(out["x"]) == 3

    def test_input_df_not_mutated(self) -> None:
        """``_sanitise_chunk`` must not mutate the caller's DataFrame."""
        df = pd.DataFrame({"d": [datetime.date(2024, 1, 1)]})
        original_dtype = df["d"].dtype
        _ = _sanitise_chunk(df)
        assert df["d"].dtype == original_dtype


class TestParquetExporterIO:
    """End-to-end exporter contract (lines 67-69, 77-95)."""

    def test_init_creates_parquet_subdir(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        exporter = ParquetExporter(config)
        assert exporter.output_dir == tmp_path / "parquet"
        assert exporter.output_dir.exists() and exporter.output_dir.is_dir()

    def test_export_table_writes_parquet_file(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        exporter = ParquetExporter(config)
        table = _make_table("orders")
        df = pd.DataFrame(
            {
                "id": ["O-001", "O-002", "O-003"],
                "amount": [10.0, 20.5, 30.25],
                "qty": [1, 2, 3],
                "is_paid": [True, False, True],
            }
        )
        path = exporter.export_table(table, iter([df]))
        assert path.exists()
        assert path.suffix == ".parquet"

        # Roundtrip: read back gives the same data.
        df_read = pd.read_parquet(path)
        assert df_read["id"].tolist() == df["id"].tolist()
        assert df_read["qty"].tolist() == df["qty"].tolist()
        assert df_read["is_paid"].tolist() == df["is_paid"].tolist()

    def test_export_table_handles_multiple_chunks(self, tmp_path: Path) -> None:
        """Exercises the writer-keep-open path: first chunk creates the
        writer, second chunk re-uses it (line 84 ``if writer is None``)."""
        config = _make_config(tmp_path)
        exporter = ParquetExporter(config)
        table = _make_table("multi")
        chunk_a = pd.DataFrame({"id": ["A-1", "A-2"], "v": [1.0, 2.0]})
        chunk_b = pd.DataFrame({"id": ["B-1", "B-2"], "v": [3.0, 4.0]})
        path = exporter.export_table(table, iter([chunk_a, chunk_b]))

        df_read = pd.read_parquet(path)
        assert df_read["id"].tolist() == ["A-1", "A-2", "B-1", "B-2"]
        assert df_read["v"].tolist() == [1.0, 2.0, 3.0, 4.0]

    def test_export_table_with_empty_chunk_iterator_writes_no_file(
        self, tmp_path: Path
    ) -> None:
        """No chunks -> writer never opens -> finally branch closes nothing
        (line 92-93). Output file should not exist."""
        config = _make_config(tmp_path)
        exporter = ParquetExporter(config)
        table = _make_table("empty")
        path = exporter.export_table(table, iter([]))
        # Path is computed but file never created because writer never opened.
        assert not path.exists()

    def test_export_table_preserves_datetime_columns(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        exporter = ParquetExporter(config)
        table = _make_table("with_dates")
        df = pd.DataFrame(
            {
                "id": ["X-1", "X-2"],
                "issued_at": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2025, 6, 30),
                ],
                "issue_date": [
                    datetime.date(2024, 1, 1),
                    datetime.date(2025, 6, 30),
                ],
            }
        )
        path = exporter.export_table(table, iter([df]))
        df_read = pd.read_parquet(path)
        assert pd.api.types.is_datetime64_any_dtype(df_read["issued_at"])
        assert pd.api.types.is_datetime64_any_dtype(df_read["issue_date"])
