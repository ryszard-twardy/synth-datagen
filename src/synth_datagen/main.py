"""
CLI entry point for synthetic-data.
Usage: synthetic-data generate [OPTIONS]
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .config import DataQuality, DataQualityConfig, Dialect, GeneratorConfig, Scenario, SchemaType
from .runtime_support import is_missing_runtime_dependency, missing_dependency_message

app = typer.Typer(
    name="synthetic-data",
    help="Generate synthetic relational datasets for SQL, Power BI, and analytics portfolios.",
    add_completion=False,
)
console = Console()


def _load_pipeline():
    from .pipeline import run_pipeline

    return run_pipeline


@app.command("generate")
def generate(
    scenario: Scenario = typer.Option(
        Scenario.RETAIL, "--scenario", "-s",
        help="Industry scenario: retail | saas | fintech | logistics",
    ),
    rows: Optional[str] = typer.Option(
        None, "--rows", "-r",
        help='Row overrides per table, e.g. "fact_orders=200000,dim_customers=50000"',
    ),
    schema: SchemaType = typer.Option(
        SchemaType.STAR, "--schema",
        help="Schema normalization. Only 'star' is currently supported.",
    ),
    dialect: Dialect = typer.Option(
        Dialect.POSTGRES, "--dialect", "-d",
        help="SQL dialect: postgres | sqlite | mysql | sqlserver",
    ),
    output: Path = typer.Option(
        Path("./out"), "--output", "-o",
        help="Output directory for generated files.",
    ),
    seed: int = typer.Option(
        42, "--seed",
        help="Random seed for reproducibility.",
    ),
    discount_variation: bool = typer.Option(
        True, "--discount-variation/--no-discount-variation",
        help="Enable customer-segment-aware discount variation for retail workflows.",
    ),
    data_quality: DataQuality = typer.Option(
        DataQuality.NONE, "--data-quality", "--dq",
        help="Data quality issues to inject: none | light | medium | heavy",
    ),
    cols_min: int = typer.Option(8,  "--cols-min", help="Minimum columns per auto-table."),
    cols_max: int = typer.Option(25, "--cols-max", help="Maximum columns per auto-table."),
    chunk_size: int = typer.Option(
        50_000, "--chunk-size",
        help="Rows per generation chunk (memory control).",
    ),
    export_sqlite: bool = typer.Option(
        False, "--export-sqlite/--no-sqlite",
        help="Also write a ready-to-query SQLite .db file.",
    ),
    export_parquet: bool = typer.Option(
        False, "--export-parquet/--no-parquet",
        help="Also write Parquet files (per table).",
    ),
    export_dml: bool = typer.Option(
        False, "--export-dml/--no-dml",
        help="Include INSERT statements in schema.sql (can be large).",
    ),
) -> None:
    """Generate synthetic relational datasets for a given scenario."""

    # Parse row overrides
    row_overrides: dict[str, int] = {}
    if rows:
        for part in rows.split(","):
            part = part.strip()
            if "=" in part:
                table_name, count = part.split("=", 1)
                row_overrides[table_name.strip()] = int(count.strip())

    dq_config = DataQualityConfig(level=data_quality)

    config = GeneratorConfig(
        scenario=scenario,
        schema_type=schema,
        dialect=dialect,
        seed=seed,
        discount_seed=seed,
        discount_variation=discount_variation,
        output_dir=output,
        chunk_size=chunk_size,
        row_overrides=row_overrides,
        cols_min=cols_min,
        cols_max=cols_max,
        data_quality=dq_config,
        export_sqlite=export_sqlite,
        export_parquet=export_parquet,
        export_dml=export_dml,
    )

    try:
        run_pipeline = _load_pipeline()
    except ModuleNotFoundError as exc:
        if is_missing_runtime_dependency(exc):
            typer.echo(missing_dependency_message(exc.name), err=True)
            raise typer.Exit(code=1)
        raise

    run_pipeline(config)


@app.command("scenarios")
def list_scenarios() -> None:
    """List all available scenarios."""
    console.print("[bold]Available scenarios:[/bold]")
    for s in Scenario:
        console.print(f"  * [cyan]{s.value}[/cyan]")


if __name__ == "__main__":
    app()
