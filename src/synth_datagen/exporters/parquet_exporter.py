"""
Parquet exporter: writes per-table .parquet files using PyArrow.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import GeneratorConfig, TableConfig


def _sanitise_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """Prepare a DataFrame for PyArrow serialisation.

    - Convert numpy datetime64 / Python datetime.date|datetime columns to
      pandas Timestamp so PyArrow can infer a proper Arrow type.
    - Convert any remaining object columns that contain date/datetime Python
      objects to strings (safe fallback) so Arrow doesn't choke.
    - Leave plain string / int / float / bool columns untouched.
    """
    chunk = chunk.copy()
    for col in chunk.columns:
        series = chunk[col]
        dtype = series.dtype

        # Already a proper datetime dtype — nothing to do
        if pd.api.types.is_datetime64_any_dtype(dtype):
            continue

        # Object columns may hold Python date/datetime/None or mixed types
        if dtype is object:
            # Sample a non-null value to decide how to handle the column
            sample = series.dropna().head(1)
            if len(sample) == 0:
                continue
            val = sample.iloc[0]

            if isinstance(val, (datetime.datetime, pd.Timestamp)):
                chunk[col] = pd.to_datetime(series, errors="coerce")
            elif isinstance(val, datetime.date):
                # Convert date objects to datetime (Arrow date32 via Timestamp)
                chunk[col] = pd.to_datetime(
                    series.apply(
                        lambda d: (
                            pd.Timestamp(d) if isinstance(d, datetime.date) else pd.NaT
                        )
                    ),
                    errors="coerce",
                )
            else:
                # Strings, mixed types — store as string for safety
                chunk[col] = series.astype(str).where(series.notna(), other=None)

    return chunk


class ParquetExporter:
    """Exports generated data to Parquet format (columnar, compressed)."""

    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self.output_dir = config.output_dir / "parquet"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_table(
        self,
        table: TableConfig,
        chunks: Iterator[pd.DataFrame],
    ) -> Path:
        """Stream chunks into a single Parquet file via PyArrow writer."""
        out_path = self.output_dir / f"{table.name}.parquet"
        writer: pq.ParquetWriter | None = None

        try:
            for chunk in chunks:
                chunk = _sanitise_chunk(chunk)
                arrow_table = pa.Table.from_pandas(chunk, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(
                        out_path,
                        arrow_table.schema,
                        compression="snappy",
                    )
                writer.write_table(arrow_table)
        finally:
            if writer:
                writer.close()

        return out_path
