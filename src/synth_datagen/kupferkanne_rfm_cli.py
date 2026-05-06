"""
CLI entry point for the Kupferkanne RFM generator.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .runtime_support import is_missing_runtime_dependency, missing_dependency_message

app = typer.Typer(
    name="synthetic-rfm-kupferkanne",
    help="Generate the Kupferkanne RFM star-schema export from a dedicated YAML config.",
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Kupferkanne RFM commands."""


@app.command("generate")
def generate(
    config: Path = typer.Option(
        ...,
        "--config",
        exists=True,
        dir_okay=False,
        help="Path to the Kupferkanne YAML config.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output directory override."
    ),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility."),
    discount_variation: bool = typer.Option(
        True,
        "--discount-variation/--no-discount-variation",
        help="Enable customer-segment-aware discount variation.",
    ),
) -> None:
    try:
        load_config, generate_dataset = _load_runtime()
    except ModuleNotFoundError as exc:
        if is_missing_runtime_dependency(exc):
            typer.echo(missing_dependency_message(exc.name), err=True)
            raise typer.Exit(code=1)
        raise

    resolved = load_config(config)
    target_output = output or resolved.output.default_dir
    outputs = generate_dataset(
        resolved, target_output, seed=seed, discount_variation=discount_variation
    )
    for name, path in outputs.items():
        typer.echo(f"{name}: {path}")
    manifest_path = outputs.get("manifest")
    if manifest_path is not None and manifest_path.exists():
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        typer.echo(
            "summary: "
            f"items={manifest['clean_metrics']['total_item_rows']}, "
            f"orders={manifest['clean_metrics']['unique_orders']}, "
            f"customers={manifest['clean_metrics']['unique_customers']}, "
            f"avg_items_per_order={manifest['clean_metrics']['avg_items_per_order']}, "
            f"dirty_rate={manifest['final_metrics']['dirty_rate']}"
        )


def _load_runtime():
    from .kupferkanne_rfm import generate_kupferkanne_rfm
    from .kupferkanne_rfm_config import load_kupferkanne_rfm_config

    return load_kupferkanne_rfm_config, generate_kupferkanne_rfm


if __name__ == "__main__":
    app()
