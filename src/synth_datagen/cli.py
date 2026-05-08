"""Single ``synth-datagen`` CLI (audit P1-2).

Replaces the four parallel console scripts with one root command exposing
each scenario as a sub-command. Old console scripts remain in
``[project.scripts]`` as transitional aliases — they will be removed at
the next major version bump.

Sub-command map:
    synth-datagen retail            → classic generator, scenario=retail
    synth-datagen saas              → classic generator, scenario=saas
    synth-datagen fintech           → classic generator, scenario=fintech
    synth-datagen logistics         → classic generator, scenario=logistics
    synth-datagen scenarios         → list scenarios
    synth-datagen monthly-sales ... → mounts synth_datagen.monthly_sales_cli
    synth-datagen kupferkanne-rfm ... → mounts synth_datagen.kupferkanne_rfm_cli
    synth-datagen saas-v3 ...       → mounts synth_datagen.saas_v3.cli
    synth-datagen pharma ...        → mounts synth_datagen.pharma.cli
                                      (requires [pharma] extra)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .config import DataQuality, Scenario
from .kupferkanne_rfm_cli import app as kupfer_app
from .main import generate as _generate
from .main import list_scenarios as _list_scenarios
from .monthly_sales_cli import app as monthly_app
from .pharma.cli import app as pharma_app
from .saas_v3.cli import app as saas_v3_app

app = typer.Typer(
    name="synth-datagen",
    help="Generate synthetic relational datasets for SQL, Power BI, and analytics portfolios.",
    add_completion=False,
    no_args_is_help=True,
)


def _scenario_command(scenario: Scenario):
    """Build a thin Typer command that delegates to the classic generator
    pipeline with ``scenario`` hardcoded."""

    def command(
        rows: Optional[str] = typer.Option(
            None,
            "--rows",
            "-r",
            help='Row overrides per table, e.g. "fact_orders=200000,dim_customers=50000"',
        ),
        dialect: str = typer.Option(
            "postgres",
            "--dialect",
            "-d",
            help="SQL dialect: postgres | sqlite | mysql | sqlserver",
        ),
        output: Path = typer.Option(
            Path("./out"),
            "--output",
            "-o",
            help="Output directory for generated files.",
        ),
        seed: int = typer.Option(
            42,
            "--seed",
            help="Random seed for reproducibility.",
        ),
        discount_variation: bool = typer.Option(
            True,
            "--discount-variation/--no-discount-variation",
            help="Enable customer-segment-aware discount variation for retail workflows.",
        ),
        data_quality: DataQuality = typer.Option(
            DataQuality.NONE,
            "--data-quality",
            "--dq",
            help="Data quality issues to inject: none | light | medium | heavy",
        ),
        cols_min: int = typer.Option(
            8, "--cols-min", help="Minimum columns per auto-table."
        ),
        cols_max: int = typer.Option(
            25, "--cols-max", help="Maximum columns per auto-table."
        ),
        chunk_size: int = typer.Option(
            50_000,
            "--chunk-size",
            help="Rows per generation chunk (memory control).",
        ),
        export_sqlite: bool = typer.Option(False, "--export-sqlite/--no-sqlite"),
        export_parquet: bool = typer.Option(False, "--export-parquet/--no-parquet"),
        export_dml: bool = typer.Option(False, "--export-dml/--no-dml"),
    ) -> None:
        from .config import Dialect, SchemaType

        _generate(
            scenario=scenario,
            rows=rows,
            schema=SchemaType.STAR,
            dialect=Dialect(dialect),
            output=output,
            seed=seed,
            discount_variation=discount_variation,
            data_quality=data_quality,
            cols_min=cols_min,
            cols_max=cols_max,
            chunk_size=chunk_size,
            export_sqlite=export_sqlite,
            export_parquet=export_parquet,
            export_dml=export_dml,
        )

    command.__doc__ = f"Generate the {scenario.value} synthetic dataset."
    return command


for _scenario in Scenario:
    app.command(name=_scenario.value)(_scenario_command(_scenario))

app.command(name="scenarios")(_list_scenarios)
app.add_typer(monthly_app, name="monthly-sales")
app.add_typer(kupfer_app, name="kupferkanne-rfm")
app.add_typer(saas_v3_app, name="saas-v3")
app.add_typer(pharma_app, name="pharma")


if __name__ == "__main__":
    app()
