"""
CLI entry point for monthly retail sales generation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from click.core import ParameterSource

from .config import DataQuality
from .runtime_support import is_missing_runtime_dependency, missing_dependency_message

app = typer.Typer(
    name="synthetic-monthly-sales",
    help="Generate monthly retail sales datasets with normalized PK/FK tables and an optional flat extract.",
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Monthly retail sales generation commands."""


@app.command("generate")
def generate(
    ctx: typer.Context,
    profile_config: Path | None = typer.Option(None, "--profile-config", help="YAML profile for monthly-sales generation."),
    start_date: str | None = typer.Option(None, "--start-date", help="Start date in YYYY-MM-DD format."),
    end_date: str | None = typer.Option(None, "--end-date", help="End date in YYYY-MM-DD format."),
    month: str | None = typer.Option(None, "--month", help="Convenience monthly range in YYYY-MM format."),
    orders_per_month: int | None = typer.Option(None, "--orders-per-month", help="Target orders per month."),
    avg_items_per_order: float = typer.Option(2.5, "--avg-items-per-order", help="Average line items per order."),
    layout: str = typer.Option("monthly", "--layout", help="Output layout: monthly | combined | both."),
    include_flat: bool = typer.Option(True, "--include-flat/--no-flat", help="Also export a flat monthly sales extract."),
    resume_from: Path | None = typer.Option(None, "--resume-from", help="Prior combined snapshot to append from."),
    output: Path = typer.Option(Path("./out/monthly_sales"), "--output", "-o", help="Output directory."),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility."),
    discount_variation: bool = typer.Option(
        True,
        "--discount-variation/--no-discount-variation",
        help="Enable customer-segment-aware discount variation.",
    ),
    data_quality: DataQuality = typer.Option(DataQuality.NONE, "--data-quality", "--dq", help="Dirty-but-plausible data quality mode."),
    export_parquet: bool = typer.Option(False, "--export-parquet/--no-parquet", help="Also export combined parquet files."),
    export_sqlite: bool = typer.Option(False, "--export-sqlite/--no-sqlite", help="Also export a combined SQLite database."),
    customers: int | None = typer.Option(None, "--customers", help="Optional total customer dimension size."),
    products: int | None = typer.Option(None, "--products", help="Optional total product dimension size."),
    stores: int | None = typer.Option(None, "--stores", help="Optional total store dimension size."),
    promotions: int | None = typer.Option(None, "--promotions", help="Optional total promotion dimension size."),
    prorate_partial_months: bool = typer.Option(True, "--prorate-partial-months/--no-prorate-partial-months", help="Scale first/last partial months by active-day share."),
) -> None:
    normalized_layout = _normalize_layout(layout)

    try:
        MonthlyLayout, MonthlySalesConfig, generate_monthly_sales, load_monthly_sales_profile = _load_monthly_runtime()
    except ModuleNotFoundError as exc:
        if is_missing_runtime_dependency(exc):
            typer.echo(missing_dependency_message(exc.name), err=True)
            raise typer.Exit(code=1)
        raise

    if profile_config is not None:
        _reject_profile_conflicts(
            ctx,
            [
                "start_date",
                "end_date",
                "month",
                "orders_per_month",
                "avg_items_per_order",
                "layout",
                "include_flat",
                "resume_from",
                "data_quality",
                "export_parquet",
                "export_sqlite",
                "customers",
                "products",
                "stores",
                "promotions",
                "prorate_partial_months",
            ],
        )
        profile = load_monthly_sales_profile(profile_config)
        config = MonthlySalesConfig.from_profile(
            profile,
            profile_path=profile_config,
            output_dir=output,
            seed=seed,
        )
        config = config.model_copy(update={"discount_variation": discount_variation})
    else:
        if orders_per_month is None:
            raise typer.BadParameter("--orders-per-month is required unless --profile-config is used.", param_hint="--orders-per-month")
        config = MonthlySalesConfig.from_inputs(
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            month=month,
            orders_per_month=orders_per_month,
            avg_items_per_order=avg_items_per_order,
            layout=MonthlyLayout(normalized_layout),
            include_flat=include_flat,
            resume_from=resume_from,
            output_dir=output,
            seed=seed,
            discount_variation=discount_variation,
            data_quality=data_quality,
            export_parquet=export_parquet,
            export_sqlite=export_sqlite,
            customers=customers,
            products=products,
            stores=stores,
            promotions=promotions,
            prorate_partial_months=prorate_partial_months,
        )
    outputs = generate_monthly_sales(config)
    for name, path in outputs.items():
        typer.echo(f"{name}: {path}")


def _load_monthly_runtime():
    from .monthly_sales import MonthlyLayout, MonthlySalesConfig, generate_monthly_sales
    from .monthly_sales_profile import load_monthly_sales_profile

    return MonthlyLayout, MonthlySalesConfig, generate_monthly_sales, load_monthly_sales_profile


def _reject_profile_conflicts(ctx: typer.Context, parameter_names: list[str]) -> None:
    conflicts: list[str] = []
    for name in parameter_names:
        source = ctx.get_parameter_source(name)
        if source not in {None, ParameterSource.DEFAULT}:
            conflicts.append(f"--{name.replace('_', '-')}")
    if conflicts:
        joined = ", ".join(conflicts)
        raise typer.BadParameter(
            f"When --profile-config is used, only --output and --seed may be overridden. Remove: {joined}",
            param_hint="--profile-config",
        )


def _normalize_layout(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"monthly", "combined", "both", "sales-files"}:
        raise typer.BadParameter("Layout must be one of: monthly, combined, both, sales-files.", param_hint="--layout")
    return normalized


def _parse_date(value: str | None):
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:  # pragma: no cover - CLI parsing guard
        raise typer.BadParameter("Dates must use YYYY-MM-DD format.") from exc


if __name__ == "__main__":
    app()
