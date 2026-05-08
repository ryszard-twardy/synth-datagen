"""User-facing CLI for the pharma scenario.

Mounted under the root ``synth-datagen pharma`` namespace via
``add_typer`` in ``src/synth_datagen/cli.py``. Mirrors the saas_v3
sub-command pattern: ``synth-datagen pharma generate ...``.

## Lazy geopandas import

The pharma scenario depends on ``geopandas`` + ``shapely`` via the
``[pharma]`` optional extra. Module-level imports MUST stay free of
those (otherwise ``synth-datagen --help`` would crash for users who
installed the package without the extra). The actual ``import
geopandas`` / engine call is wrapped in a try/except inside the
``generate`` command body — when the extra is missing, the user
gets a friendly plain-text install hint and a non-zero exit code.

This file's top imports are deliberately limited to ``typer``,
``pathlib``, ``json``, ``datetime``, and the pharma config / vocab
modules. Engine / geo / validate imports happen inside ``generate``.

## Output artifacts (v0.3.0, four files in a flat output dir)

1. 8 CSVs (one per engine table).
2. ``metadata.json`` — full effective config + RNG state hash + geo
   lineage block + ``generated_at`` ISO-8601 timestamp.
3. ``geo_lineage.md`` — license attribution (ODbL for OSM, dl-de/by-2-0
   for BKG) + filenames + dataset shape.
4. ``benchmark_validation.md`` — written ONLY when
   ``--benchmark-validation`` is set; the validate.py
   ``render_markdown`` output.

Schema.sql, load_to_bigquery.sh, data_dictionary.md, and
expected_findings.md are deferred to v0.3.x per the Phase 6 plan.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import typer

from synth_datagen.pharma.config import PharmaConfig

app = typer.Typer(
    name="pharma",
    help=(
        "Generate German pharma field-sales synthetic datasets "
        "(acute-care + specialty-care). Requires the [pharma] extra: "
        "pip install 'synth-datagen[pharma]'"
    ),
    add_completion=False,
    no_args_is_help=True,
)


_INSTALL_HINT = (
    "Pharma scenario requires the [pharma] extra (geopandas + shapely).\n"
    "Install with:  pip install 'synth-datagen[pharma]'\n"
    'Or, if you\'re developing in this repo:  pip install -e ".[test,pharma]"'
)


def _check_pharma_extra_available() -> str | None:
    """Return ``None`` if geopandas + shapely are importable, else
    return a plain-text install hint.

    Lazy: the import attempts happen inside this function only, never
    at module load time.
    """
    try:
        import geopandas  # noqa: F401
        import shapely  # noqa: F401
    except ImportError:
        return _INSTALL_HINT
    return None


def _date_serializer(value: object) -> str:
    """JSON helper for date / Path objects in PharmaConfig dump."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unserializable {type(value).__name__}")


def _compute_rng_state_hash(seed: int, sub_mode: str) -> str:
    """Stable per-(seed, sub_mode) digest of the engine's first
    spawned-stream draws. Used as a reproducibility audit trail in
    ``metadata.json``.

    The digest is derived from the make_pharma_streams output,
    independent of the engine's table-generation logic — so it
    pins the seed-to-stream mapping but doesn't change when engine
    table logic evolves.
    """
    from synth_datagen.pharma.engine import make_pharma_streams

    streams = make_pharma_streams(seed)
    h = hashlib.sha256()
    h.update(sub_mode.encode("utf-8"))
    h.update(str(seed).encode("utf-8"))
    for label, rng in streams.items():
        h.update(label.encode("utf-8"))
        # Three integers per stream are enough to fingerprint the
        # spawn slot without consuming much state.
        h.update(rng.integers(0, 2**32 - 1, size=3).tobytes())
    return h.hexdigest()


def _write_csvs(tables: dict, output: Path) -> None:
    """Write each table as ``<name>.csv`` in ``output``."""
    for name, df in tables.items():
        df.to_csv(output / f"{name}.csv", index=False)


def _write_metadata_json(
    config: PharmaConfig,
    tables: dict,
    output: Path,
    *,
    rng_state_hash: str,
) -> None:
    """Audit-trail metadata: full effective_config + rng_state_hash +
    geo_lineage block + generated_at timestamp."""
    geographic = tables["geographic_metadata"].iloc[0]
    geo_lineage = geographic.get("geo_lineage", {})
    if not isinstance(geo_lineage, dict):
        # Defensive: pandas may auto-coerce on round-trip.
        geo_lineage = dict(geo_lineage) if geo_lineage else {}

    payload = {
        "effective_config": config.model_dump(mode="json"),
        "rng_state_hash": rng_state_hash,
        "geo_lineage": geo_lineage,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_accounts": int(geographic.get("total_accounts", 0)),
            "landkreise_with_accounts": int(
                geographic.get("landkreise_with_accounts", 0)
            ),
            "landkreis_coverage_pct": float(
                geographic.get("landkreis_coverage_pct", 0.0)
            ),
        },
    }
    (output / "metadata.json").write_text(
        json.dumps(payload, indent=2, default=_date_serializer),
        encoding="utf-8",
    )


def _write_geo_lineage_md(
    config: PharmaConfig,
    tables: dict,
    output: Path,
) -> None:
    """License-attribution + provenance markdown."""
    geographic = tables["geographic_metadata"].iloc[0]
    geo_lineage = geographic.get("geo_lineage", {})
    if not isinstance(geo_lineage, dict):
        geo_lineage = dict(geo_lineage) if geo_lineage else {}

    lines = [
        f"# Geographic data lineage — {config.sub_mode}",
        "",
        "## Source files (caller-supplied)",
        "",
        f"- **OSM hospitals snapshot:** `{geo_lineage.get('osm_snapshot_filename', '?')}`",
        f"- **BKG VG250 Bundesländer:** `{geo_lineage.get('bkg_bundeslaender_filename', '?')}`",
        f"- **BKG VG250 Landkreise:** `{geo_lineage.get('bkg_landkreise_filename', '?')}`",
        "",
        "## Licenses",
        "",
        f"- OSM data is **{geo_lineage.get('osm_license', 'ODbL')}**.",
        f"- BKG VG250 data is **{geo_lineage.get('bkg_license', 'dl-de/by-2-0')}**.",
        "",
        "Both licenses require attribution from the consumer when redistributing.",
        "synth-datagen does NOT bundle either source — the caller passes them in.",
        "",
        "## Dataset shape",
        "",
        f"- Bundesländer in source: {geo_lineage.get('bundesland_count', '?')}",
        f"- Landkreise in source: {geo_lineage.get('landkreis_count', '?')}",
        f"- Total accounts generated: {int(geographic.get('total_accounts', 0))}",
        f"- Landkreise with at least one account: "
        f"{int(geographic.get('landkreise_with_accounts', 0))}",
        f"- Landkreis coverage: {float(geographic.get('landkreis_coverage_pct', 0.0)):.2f}%",
        "",
    ]
    (output / "geo_lineage.md").write_text("\n".join(lines), encoding="utf-8")


@app.callback()
def _callback() -> None:
    """Pharma scenario commands."""


@app.command("generate")
def generate(
    sub_mode: str = typer.Option(
        ...,
        "--sub-mode",
        help="Pharma sub-mode: acute-care | specialty-care.",
    ),
    hospitals_csv: Path = typer.Option(
        ...,
        "--hospitals-csv",
        exists=True,
        dir_okay=False,
        help="Caller-supplied OSM hospital snapshot CSV (ODbL).",
    ),
    bkg_bundeslaender: Path = typer.Option(
        ...,
        "--bkg-bundeslaender",
        exists=True,
        dir_okay=False,
        help="Caller-supplied BKG VG250 Bundesländer GeoJSON (dl-de/by-2-0).",
    ),
    bkg_landkreise: Path = typer.Option(
        ...,
        "--bkg-landkreise",
        exists=True,
        dir_okay=False,
        help="Caller-supplied BKG VG250 Landkreise GeoJSON (dl-de/by-2-0).",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        help="Output directory for the four artifacts (created if missing).",
    ),
    seed: int = typer.Option(
        ...,
        "--seed",
        help="Reproducibility seed for the pharma RNG salt.",
    ),
    company_name: str = typer.Option(
        "MediCorp",
        "--company-name",
        help="Synthetic manufacturer name used in metadata only.",
    ),
    rep_count: int = typer.Option(
        40,
        "--rep-count",
        help="Number of sales reps (10-200).",
    ),
    account_count: int = typer.Option(
        850,
        "--account-count",
        help="Number of accounts (100-3000).",
    ),
    primary_atc: str | None = typer.Option(
        None,
        "--primary-atc",
        help=(
            "Specialty-care: dominant ATC group (L01 oncology, "
            "L04 immunosuppressants, S01 ophthalmologicals, D dermatologicals). "
            "Acute-care: ignored."
        ),
    ),
    target_quota_attainment: float = typer.Option(
        0.92,
        "--target-quota-attainment",
        help="Median rep quota-attainment ratio (0.5-1.5).",
    ),
    data_quality: str = typer.Option(
        "medium",
        "--data-quality",
        help="Data quality level: clean | medium | messy.",
    ),
    benchmark_validation: bool = typer.Option(
        False,
        "--benchmark-validation/--no-benchmark-validation",
        help=(
            "Run the v0.3.0 benchmark-validation pass and write "
            "benchmark_validation.md. Exit non-zero on validation failure "
            "(CSVs still written for inspection)."
        ),
    ),
) -> None:
    """Generate a pharma synthetic dataset.

    Outputs into ``--output`` (created if missing): 8 CSVs +
    metadata.json + geo_lineage.md, plus benchmark_validation.md when
    --benchmark-validation is set.
    """
    # Lazy import — fail with friendly install hint if the [pharma]
    # extra isn't available.
    extra_error = _check_pharma_extra_available()
    if extra_error is not None:
        typer.echo(extra_error, err=True)
        raise typer.Exit(code=1)

    try:
        cfg = PharmaConfig(
            sub_mode=sub_mode,  # type: ignore[arg-type]
            hospitals_csv=hospitals_csv,
            bkg_bundeslaender=bkg_bundeslaender,
            bkg_landkreise=bkg_landkreise,
            seed=seed,
            company_name=company_name,
            rep_count=rep_count,
            account_count=account_count,
            primary_atc=primary_atc,
            target_quota_attainment=target_quota_attainment,
            data_quality=data_quality,  # type: ignore[arg-type]
            benchmark_validation=benchmark_validation,
        )
    except Exception as exc:
        # Pydantic raises ValidationError for unknown sub-mode / bad
        # bounds / etc. Surface a clean plain-text rejection rather
        # than a Python traceback so users (and tests) see the cause
        # immediately.
        typer.echo(f"Invalid pharma config: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    # Engine / validate imports happen here — engine.generate touches
    # geopandas via geo.py, so this must come AFTER the extra check.
    from synth_datagen.pharma import engine, validate

    output.mkdir(parents=True, exist_ok=True)

    tables = engine.generate(cfg)
    rng_state_hash = _compute_rng_state_hash(cfg.seed, cfg.sub_mode)

    _write_csvs(tables, output)
    _write_metadata_json(cfg, tables, output, rng_state_hash=rng_state_hash)
    _write_geo_lineage_md(cfg, tables, output)

    exit_code = 0
    if benchmark_validation:
        result = validate.validate(cfg, tables)
        (output / "benchmark_validation.md").write_text(
            validate.render_markdown(result), encoding="utf-8"
        )
        if result.overall_status == "fail":
            # CSVs still on disk for inspection; non-zero exit gates
            # CI workflows. Mirrors saas_v3 idiom.
            exit_code = 1

    if exit_code != 0:
        raise typer.Exit(code=exit_code)
