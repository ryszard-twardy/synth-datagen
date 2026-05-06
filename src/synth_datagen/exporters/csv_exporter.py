"""
Streaming CSV exporter.
Writes one CSV file per table, appending chunks to avoid loading all rows into memory.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

import pandas as pd

from ..config import GeneratorConfig, TableConfig


class CsvExporter:
    """
    Exports generated DataFrames to CSV files.

    Usage::

        exporter = CsvExporter(config)
        exporter.export_table(table, chunk_iter)
    """

    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self.output_dir = config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_table(
        self,
        table: TableConfig,
        chunks: Iterator[pd.DataFrame],
    ) -> Path:
        """
        Write all chunks for a table to a single CSV file.

        Args:
            table:  TableConfig for naming the file.
            chunks: Iterator of DataFrame chunks.

        Returns:
            Path to the written CSV file.
        """
        out_path = self.output_dir / f"{table.name}.csv"
        first = True

        with open(out_path, mode="w", newline="", encoding="utf-8-sig") as fh:
            for chunk in chunks:
                if first:
                    # Write header + first chunk
                    chunk.to_csv(fh, index=False, quoting=csv.QUOTE_NONNUMERIC)
                    first = False
                else:
                    # Append without repeating header
                    chunk.to_csv(fh, index=False, header=False, quoting=csv.QUOTE_NONNUMERIC)

        return out_path

    def export_all(
        self,
        tables_and_chunks: list[tuple[TableConfig, Iterator[pd.DataFrame]]],
    ) -> list[Path]:
        """Export multiple tables; returns list of written paths."""
        paths = []
        for table, chunks in tables_and_chunks:
            path = self.export_table(table, chunks)
            paths.append(path)
        return paths
