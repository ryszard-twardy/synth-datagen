"""
Export utilities for SaaS synthetic engine v3.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import OutputFormat, SaaSV3Config, dump_config
from .engine import EXPORTED_COLUMNS, GeneratedTables, GenerationResult, TABLE_ORDER


DATE_COLUMNS = {"signup_date", "start_date", "end_date", "invoice_date", "survey_date"}
TIMESTAMP_COLUMNS = {"last_login_at", "event_timestamp"}


class SaaSV3Exporter:
    def __init__(self, config: SaaSV3Config) -> None:
        self.config = config

    def resolve_run_root(self, output_override: Path | None = None) -> Path:
        if output_override is not None:
            return Path(output_override)
        return (
            Path(self.config.output.root_dir)
            / f"{self.config.run.name}_seed{self.config.run.seed}_{self.config.history.as_of_date.isoformat()}"
        )

    def export_result(
        self,
        result: GenerationResult,
        *,
        output_override: Path | None = None,
        config_source_path: Path | None = None,
    ) -> dict[str, Path]:
        run_root = self.resolve_run_root(output_override)
        metadata_dir = run_root / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {"run_root": run_root}
        if self.config.output.write_effective_config:
            effective_config_path = metadata_dir / "effective_config.yaml"
            effective_config_path.write_text(dump_config(self.config), encoding="utf-8")
            paths["effective_config"] = effective_config_path
        if config_source_path is not None:
            paths["config_source"] = Path(config_source_path)

        paths.update(self._export_dataset(result.clean, "clean", run_root))
        if result.dirty is not None:
            paths.update(self._export_dataset(result.dirty, "dirty", run_root))
        return paths

    def _export_dataset(
        self, dataset: GeneratedTables, mode: str, run_root: Path
    ) -> dict[str, Path]:
        mode_root = run_root / mode
        csv_dir = mode_root / "csv"
        parquet_dir = mode_root / "parquet"
        schema_dir = run_root / "metadata" / "bigquery_schema" / mode
        manifest_path = run_root / "metadata" / f"manifest_{mode}.json"
        if OutputFormat.CSV in self.config.output.formats:
            csv_dir.mkdir(parents=True, exist_ok=True)
        if OutputFormat.PARQUET in self.config.output.formats:
            parquet_dir.mkdir(parents=True, exist_ok=True)
        if OutputFormat.BIGQUERY_SCHEMA in self.config.output.formats:
            schema_dir.mkdir(parents=True, exist_ok=True)

        for table_name in TABLE_ORDER:
            batches = dataset.tables[table_name]
            if OutputFormat.CSV in self.config.output.formats:
                csv_path = csv_dir / f"{table_name}.csv"
                self._write_csv_batches(csv_path, batches)
            if OutputFormat.PARQUET in self.config.output.formats:
                parquet_path = parquet_dir / f"{table_name}.parquet"
                self._write_parquet_batches(parquet_path, batches)
            if OutputFormat.BIGQUERY_SCHEMA in self.config.output.formats:
                schema_path = schema_dir / f"{table_name}.json"
                self._write_bigquery_schema(
                    schema_path,
                    table_name,
                    batches[0]
                    if batches
                    else pd.DataFrame(columns=EXPORTED_COLUMNS[table_name]),
                )

        manifest = {
            "mode": mode,
            "seed": self.config.run.seed,
            "schema_version": self.config.run.schema_version,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "config_hash": self.config.config_hash(),
            "row_counts": dataset.row_counts(),
            "target_row_counts": self.config.row_target_map,
            "defect_summary": dataset.metadata.get("defect_summary", {}),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )
        return {f"{mode}_root": mode_root, f"{mode}_manifest": manifest_path}

    def _write_csv_batches(self, path: Path, batches: list[pd.DataFrame]) -> None:
        first = True
        for batch in batches:
            batch.to_csv(path, index=False, mode="w" if first else "a", header=first)
            first = False
        if first:
            pd.DataFrame().to_csv(path, index=False)

    def _write_parquet_batches(self, path: Path, batches: list[pd.DataFrame]) -> None:
        writer: pq.ParquetWriter | None = None
        stringify_columns = self._columns_to_stringify_for_parquet(batches)
        try:
            for batch in batches:
                table = pa.Table.from_pandas(
                    self._prepare_batch_for_parquet(batch, stringify_columns),
                    preserve_index=False,
                )
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema)
                writer.write_table(table)
            if writer is None:
                empty = pa.Table.from_pandas(pd.DataFrame(), preserve_index=False)
                writer = pq.ParquetWriter(path, empty.schema)
        finally:
            if writer is not None:
                writer.close()

    def _columns_to_stringify_for_parquet(
        self, batches: list[pd.DataFrame]
    ) -> set[str]:
        observed_types: dict[str, set[type]] = {}
        for batch in batches:
            for column in batch.columns:
                non_null = batch[column].dropna()
                if non_null.empty:
                    continue
                observed_types.setdefault(column, set()).update(
                    type(value) for value in non_null.head(100).tolist()
                )
        return {
            column
            for column, types in observed_types.items()
            if len(types) > 1 or str in types
        }

    def _prepare_batch_for_parquet(
        self, batch: pd.DataFrame, stringify_columns: set[str]
    ) -> pd.DataFrame:
        prepared = batch.copy()
        for column in prepared.columns:
            if column not in stringify_columns and prepared[column].dtype != object:
                continue
            if column in stringify_columns:
                prepared[column] = prepared[column].map(
                    lambda value: None if pd.isna(value) else str(value)
                )
                continue
            non_null = prepared[column].dropna()
            types = {type(value) for value in non_null.head(100).tolist()}
            if len(types) > 1 or str in types:
                prepared[column] = prepared[column].map(
                    lambda value: None if pd.isna(value) else str(value)
                )
        return prepared

    def _write_bigquery_schema(
        self, path: Path, table_name: str, sample_df: pd.DataFrame
    ) -> None:
        fields = []
        for column in EXPORTED_COLUMNS[table_name]:
            series = (
                sample_df[column]
                if column in sample_df.columns
                else pd.Series(dtype=object)
            )
            fields.append(
                {
                    "name": column,
                    "type": self._bq_type_for_series(column, series),
                    "mode": "NULLABLE",
                }
            )
        path.write_text(json.dumps(fields, indent=2), encoding="utf-8")

    def _bq_type_for_series(self, column_name: str, series: pd.Series) -> str:
        if column_name in DATE_COLUMNS:
            return "DATE"
        if column_name in TIMESTAMP_COLUMNS:
            return "TIMESTAMP"
        if pd.api.types.is_bool_dtype(series):
            return "BOOL"
        if pd.api.types.is_integer_dtype(series):
            return "INT64"
        if pd.api.types.is_float_dtype(series):
            return "FLOAT64"
        return "STRING"
