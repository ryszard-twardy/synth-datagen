"""
CLI entry points for the SaaS synthetic engine v3.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..runtime_support import is_missing_runtime_dependency, missing_dependency_message

app = typer.Typer(
    name="synthetic-saas",
    help="Generate and validate ultra-realistic SaaS customer success datasets.",
    add_completion=False,
)


@app.callback()
def main() -> None:
    """SaaS synthetic engine v3 commands."""


@app.command("generate")
def generate(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, help="Path to YAML config."),
    mode: str = typer.Option("both", "--mode", help="Output mode: clean | dirty | both."),
    output: Path | None = typer.Option(None, "--output", help="Optional output override."),
    seed: int | None = typer.Option(None, "--seed", help="Optional seed override."),
) -> None:
    normalized_mode = _normalize_mode(mode)
    try:
        OutputMode, load_config, SaaSV3Engine, SaaSV3Exporter, validate_generated_dataset = _load_runtime()
    except ModuleNotFoundError as exc:
        if is_missing_runtime_dependency(exc):
            typer.echo(missing_dependency_message(exc.name), err=True)
            raise typer.Exit(code=1)
        raise

    cfg = load_config(config)
    engine = SaaSV3Engine(cfg, seed_override=seed)
    result = engine.generate(OutputMode(normalized_mode))
    clean_report = validate_generated_dataset(result.clean, engine.config, "clean")
    _echo_report(clean_report)
    if not clean_report.passed:
        raise typer.Exit(code=1)
    if result.dirty is not None:
        dirty_report = validate_generated_dataset(result.dirty, engine.config, "dirty")
        _echo_report(dirty_report)
        if not dirty_report.passed:
            raise typer.Exit(code=1)
    exporter = SaaSV3Exporter(engine.config)
    paths = exporter.export_result(result, output_override=output, config_source_path=config)
    for name, path in paths.items():
        typer.echo(f"{name}: {path}")


@app.command("validate")
def validate(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, help="Path to YAML config."),
    mode: str = typer.Option("clean", "--mode", help="Validation mode: clean | dirty."),
    run_root: Path | None = typer.Option(None, "--run-root", help="Generated run root. Defaults to config-derived path."),
) -> None:
    normalized_mode = _normalize_validate_mode(mode)
    try:
        load_config, SaaSV3Exporter, validate_exported_run = _load_validate_runtime()
    except ModuleNotFoundError as exc:
        if is_missing_runtime_dependency(exc):
            typer.echo(missing_dependency_message(exc.name), err=True)
            raise typer.Exit(code=1)
        raise

    cfg = load_config(config)
    exporter = SaaSV3Exporter(cfg)
    resolved_root = run_root or exporter.resolve_run_root()
    report = validate_exported_run(resolved_root, cfg, normalized_mode)
    _echo_report(report)
    if not report.passed:
        raise typer.Exit(code=1)


@app.command("smoke-test")
def smoke_test(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False, help="Path to YAML config."),
    output: Path | None = typer.Option(None, "--output", help="Optional output override."),
) -> None:
    try:
        OutputMode, load_config, SaaSV3Engine, SaaSV3Exporter, validate_generated_dataset = _load_runtime()
    except ModuleNotFoundError as exc:
        if is_missing_runtime_dependency(exc):
            typer.echo(missing_dependency_message(exc.name), err=True)
            raise typer.Exit(code=1)
        raise

    cfg = load_config(config)
    smoke_root = output or (cfg.output.root_dir / "smoke")
    engine = SaaSV3Engine(cfg)
    result = engine.generate(OutputMode.BOTH)
    clean_report = validate_generated_dataset(result.clean, engine.config, "clean")
    dirty_report = validate_generated_dataset(result.dirty, engine.config, "dirty") if result.dirty is not None else None
    _echo_report(clean_report)
    if dirty_report is not None:
        _echo_report(dirty_report)
    if not clean_report.passed or (dirty_report is not None and not dirty_report.passed):
        raise typer.Exit(code=1)
    exporter = SaaSV3Exporter(engine.config)
    paths = exporter.export_result(result, output_override=smoke_root, config_source_path=config)
    typer.echo(f"smoke_run_root: {paths['run_root']}")


def _load_runtime():
    from .config import OutputMode, load_config
    from .engine import SaaSV3Engine
    from .exporters import SaaSV3Exporter
    from .validate import validate_generated_dataset

    return OutputMode, load_config, SaaSV3Engine, SaaSV3Exporter, validate_generated_dataset


def _load_validate_runtime():
    from .config import load_config
    from .exporters import SaaSV3Exporter
    from .validate import validate_exported_run

    return load_config, SaaSV3Exporter, validate_exported_run


def _normalize_mode(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"clean", "dirty", "both"}:
        raise typer.BadParameter("Mode must be one of: clean, dirty, both.", param_hint="--mode")
    return normalized


def _normalize_validate_mode(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"clean", "dirty"}:
        raise typer.BadParameter("Mode must be one of: clean, dirty.", param_hint="--mode")
    return normalized


def _echo_report(report) -> None:
    status = "PASS" if report.passed else "FAIL"
    typer.echo(f"{report.mode}: {status}")
    for issue in report.issues:
        table_part = f"[{issue.table}] " if issue.table else ""
        typer.echo(f"  - {table_part}{issue.code}: {issue.message}")


if __name__ == "__main__":
    app()
