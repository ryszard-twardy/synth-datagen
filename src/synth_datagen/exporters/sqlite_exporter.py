"""
SQLite exporter: creates a ready-to-query .db file from generated data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pandas as pd

from ..config import Dialect, GeneratorConfig, TableConfig
from ..exporters.sql_exporter import SqlExporter, _TYPE_MAP
from ..schema_builder import SchemaGraph


class SqliteExporter:
    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self.output_dir = config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        sqlite_config = config.model_copy(update={"dialect": Dialect.SQLITE})
        self._ddl_gen = SqlExporter(sqlite_config)

    def export(
        self,
        graph: SchemaGraph,
        tables_and_chunks: list[tuple[TableConfig, Iterator[pd.DataFrame]]],
        db_name: str | None = None,
    ) -> Path:
        name = db_name or self.config.scenario.value
        db_path = self.output_dir / f"{name}.db"
        if db_path.exists():
            db_path.unlink()

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        try:
            self._apply_ddl(conn, graph)
            self._insert_all(conn, tables_and_chunks)
            self._create_indexes(conn, graph)
            conn.commit()
        finally:
            conn.close()
        return db_path

    def _apply_ddl(self, conn: sqlite3.Connection, graph: SchemaGraph) -> None:
        for table in graph.topological_order():
            conn.execute(self._create_table_sqlite(table))

    def _create_table_sqlite(self, table: TableConfig) -> str:
        type_map = _TYPE_MAP[Dialect.SQLITE]
        column_defs: list[str] = []
        for column in table.columns:
            sql_type = type_map[column.dtype.value]
            nullable = "" if column.nullable else " NOT NULL"
            if column.name == table.pk_column:
                column_defs.append(f'"{column.name}" {sql_type} PRIMARY KEY')
            else:
                unique = " UNIQUE" if column.unique else ""
                column_defs.append(f'"{column.name}" {sql_type}{nullable}{unique}')
        return (
            f'CREATE TABLE IF NOT EXISTS "{table.name}" (\n    '
            + ",\n    ".join(column_defs)
            + "\n);\n"
        )

    def _insert_all(
        self,
        conn: sqlite3.Connection,
        tables_and_chunks: list[tuple[TableConfig, Iterator[pd.DataFrame]]],
    ) -> None:
        for table, chunks in tables_and_chunks:
            for chunk in chunks:
                clean = chunk.copy()
                for column in clean.select_dtypes(include=["object", "string"]).columns:
                    clean[column] = (
                        clean[column].astype(str).where(clean[column].notna(), None)
                    )
                clean.to_sql(
                    table.name,
                    conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=10_000,
                )

    def _create_indexes(self, conn: sqlite3.Connection, graph: SchemaGraph) -> None:
        for relation in graph.relations:
            idx_name = f"idx_{relation.source_table}_{relation.source_column}"
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{idx_name}" '
                f'ON "{relation.source_table}" ("{relation.source_column}");'
            )
