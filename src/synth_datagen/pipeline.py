"""
Generation pipeline: generate canonical data, derive plausible dirty exports, then write outputs.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from faker import Faker
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from .config import GeneratorConfig, Scenario
from .exporters.csv_exporter import CsvExporter
from .exporters.parquet_exporter import ParquetExporter
from .exporters.sql_exporter import SqlExporter
from .exporters.sqlite_exporter import SqliteExporter
from .generators.base import BaseScenarioGenerator
from .reporting import write_data_dictionary, write_erd
from .schema_builder import SchemaBuilder
from .utils import apply_data_quality, seed_everything

console = Console()


def _get_generator(
    scenario: Scenario,
    config: GeneratorConfig,
    rng: np.random.Generator,
    faker: Faker,
) -> BaseScenarioGenerator:
    from .generators.fintech import FintechGenerator
    from .generators.logistics import LogisticsGenerator
    from .generators.retail import RetailGenerator
    from .generators.saas import SaasGenerator

    # Audit P1-9: explicit type[BaseScenarioGenerator] keeps mypy from
    # inferring the abstract base and complaining at the call site.
    mapping: dict[Scenario, type[BaseScenarioGenerator]] = {
        Scenario.RETAIL: RetailGenerator,
        Scenario.SAAS: SaasGenerator,
        Scenario.FINTECH: FintechGenerator,
        Scenario.LOGISTICS: LogisticsGenerator,
    }
    return mapping[scenario](config, rng, faker)


def run_pipeline(config: GeneratorConfig) -> None:
    t0 = time.perf_counter()
    console.rule("[bold cyan]synthetic-data[/bold cyan]", characters="-")
    console.print(f"Scenario : [green]{config.scenario.value}[/green]")
    console.print(f"Schema   : [green]{config.schema_type.value}[/green]")
    console.print(f"Dialect  : [green]{config.dialect.value}[/green]")
    console.print(f"Seed     : [green]{config.seed}[/green]")
    console.print(f"Output   : [green]{config.output_dir}[/green]")
    console.print(f"DQ level : [green]{config.data_quality.level.value}[/green]")
    console.rule(characters="-")

    _, rng, faker = seed_everything(config.seed)
    generator = _get_generator(config.scenario, config, rng, faker)
    raw_tables, raw_relations = generator.get_raw_schema()
    graph = SchemaBuilder(config).build(raw_tables, raw_relations)
    ordered_tables = graph.topological_order()
    console.print(f"Tables   : {[table.name for table in ordered_tables]}")
    console.rule(characters="-")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    csv_exporter = CsvExporter(config)
    sql_exporter = SqlExporter(config)
    parquet_exporter = ParquetExporter(config) if config.export_parquet else None
    sqlite_exporter = SqliteExporter(config) if config.export_sqlite else None

    canonical_chunks: dict[str, list[pd.DataFrame]] = {}
    fk_pools: dict[str, np.ndarray] = {}

    with Progress(
        SpinnerColumn(),
        "[bold]{task.description}",
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(
            "Generating canonical tables...", total=len(ordered_tables)
        )
        for table in ordered_tables:
            progress.update(
                task_id, description=f"Generating [cyan]{table.name}[/cyan]"
            )
            chunks = list(generator.generate_table(table, graph, fk_pools))
            canonical_chunks[table.name] = chunks
            full_df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            if table.pk_column in full_df.columns:
                fk_pools[f"{table.name}.{table.pk_column}"] = (
                    full_df[table.pk_column].dropna().to_numpy()
                )
            progress.advance(task_id)

    export_chunks: dict[str, list[pd.DataFrame]] = {}
    for table in ordered_tables:
        unique_state = {
            column.name: set(
                pd.concat(canonical_chunks[table.name], ignore_index=True)[column.name]
                .dropna()
                .tolist()
            )
            for column in table.columns
            if column.unique or column.name == table.pk_column
        }
        export_chunks[table.name] = [
            apply_data_quality(chunk, table, config.data_quality, rng, unique_state)
            for chunk in canonical_chunks[table.name]
        ]

    for table in ordered_tables:
        csv_exporter.export_table(table, iter(export_chunks[table.name]))
        if parquet_exporter:
            parquet_exporter.export_table(table, iter(export_chunks[table.name]))

    sql_path = sql_exporter.export(graph)
    console.print(f"[green][OK][/green] SQL DDL written -> {sql_path}")

    if sqlite_exporter:
        sqlite_data = [
            (table, iter(export_chunks[table.name])) for table in ordered_tables
        ]
        db_path = sqlite_exporter.export(graph, sqlite_data)
        console.print(f"[green][OK][/green] SQLite DB written -> {db_path}")

    write_data_dictionary(graph, config, console)
    write_erd(graph, config, console)

    elapsed = time.perf_counter() - t0
    total_rows = sum(
        sum(len(chunk) for chunk in chunks) for chunks in export_chunks.values()
    )
    console.rule(characters="-")
    console.print(
        f"[bold green]Done![/bold green] {total_rows:,} rows in {elapsed:.1f}s -> {config.output_dir}"
    )
