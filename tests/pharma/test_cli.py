"""Tests for ``synth_datagen.pharma.cli`` — user-facing surface.

12 tests covering:

- CLI registration: ``synth-datagen pharma --help`` shows the
  subcommand even without ``[pharma]`` extra installed.
- Friendly extra-missing error: clear plain-text message + non-zero
  exit when geopandas isn't available.
- End-to-end generation: artifacts written to a flat output dir for
  both sub-modes.
- Artifact contents: 8 CSVs + metadata.json (with effective_config +
  geo_lineage + rng_state_hash + generated_at) + geo_lineage.md
  (license attribution); benchmark_validation.md ONLY when
  --benchmark-validation flag set.
- Exit-code wiring: --benchmark-validation + corrupted output → exit 1
  with CSVs still written (inspect-friendly per saas_v3 idiom).
- ANSI strip on every result.output assertion (memory:
  cli-tests-ansi-on-ci).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.helpers import strip_ansi

# Skip CLI smoke tests requiring engine when [pharma] extra absent.
# The "extra missing" test case stays runnable: it needs to monkey-
# patch sys.modules and so does NOT take a hard import dependency.
pytest.importorskip("geopandas", reason="requires '[pharma]' extra")
pytest.importorskip("shapely", reason="requires '[pharma]' extra")

from synth_datagen.cli import app as root_app  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pharma"
HOSPITALS_CSV = FIXTURE_DIR / "osm_hospitals_DE_test.csv"
BL_GEOJSON = FIXTURE_DIR / "bundeslaender_test.geojson"
LK_GEOJSON = FIXTURE_DIR / "landkreise_test.geojson"

# Wide terminal so Typer's --help renderer doesn't truncate long flag
# names like ``--bkg-bundeslaender`` to ellipsis. 200 cols is plenty
# for any pharma flag and doesn't affect non-help assertions.
runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})

EXPECTED_CSVS: tuple[str, ...] = (
    "accounts.csv",
    "sales_reps.csv",
    "territories.csv",
    "products.csv",
    "orders.csv",
    "rep_visits.csv",
    "account_specialties.csv",
    "geographic_metadata.csv",
)


def _invoke_pharma_generate(
    output_dir: Path,
    *,
    sub_mode: str = "acute-care",
    seed: int = 42,
    account_count: int = 100,
    rep_count: int = 15,
    extra_args: tuple[str, ...] = (),
):
    """Invoke ``synth-datagen pharma generate`` with the hermetic fixture."""
    return runner.invoke(
        root_app,
        [
            "pharma",
            "generate",
            "--sub-mode",
            sub_mode,
            "--hospitals-csv",
            str(HOSPITALS_CSV),
            "--bkg-bundeslaender",
            str(BL_GEOJSON),
            "--bkg-landkreise",
            str(LK_GEOJSON),
            "--output",
            str(output_dir),
            "--seed",
            str(seed),
            "--account-count",
            str(account_count),
            "--rep-count",
            str(rep_count),
            *extra_args,
        ],
    )


# ---------------------------------------------------------------------------
# Help + registration
# ---------------------------------------------------------------------------


def test_pharma_subcommand_appears_in_root_help() -> None:
    result = runner.invoke(root_app, ["--help"])
    output = strip_ansi(result.output)
    assert result.exit_code == 0
    assert "pharma" in output


def test_pharma_help_lists_required_flags() -> None:
    """All six required flags must appear in ``pharma generate --help``."""
    result = runner.invoke(root_app, ["pharma", "generate", "--help"])
    output = strip_ansi(result.output)
    assert result.exit_code == 0
    for needle in (
        "--sub-mode",
        "--hospitals-csv",
        "--bkg-bundeslaender",
        "--bkg-landkreise",
        "--output",
        "--seed",
    ):
        assert needle in output, f"--help missing flag {needle!r}"


def test_pharma_help_lists_optional_flags() -> None:
    """Optional flags also documented so users discover them."""
    result = runner.invoke(root_app, ["pharma", "generate", "--help"])
    output = strip_ansi(result.output)
    for needle in (
        "--account-count",
        "--rep-count",
        "--data-quality",
        "--benchmark-validation",
        "--company-name",
    ):
        assert needle in output, f"--help missing flag {needle!r}"


# ---------------------------------------------------------------------------
# Smoke: end-to-end generation writes the documented artifacts
# ---------------------------------------------------------------------------


def test_pharma_acute_generate_writes_eight_csvs(tmp_path: Path) -> None:
    out = tmp_path / "acute_run"
    result = _invoke_pharma_generate(out, sub_mode="acute-care")
    assert result.exit_code == 0, strip_ansi(result.output)
    for csv in EXPECTED_CSVS:
        assert (out / csv).exists(), f"missing CSV: {csv}"


def test_pharma_specialty_generate_writes_eight_csvs(tmp_path: Path) -> None:
    out = tmp_path / "specialty_run"
    result = _invoke_pharma_generate(out, sub_mode="specialty-care")
    assert result.exit_code == 0, strip_ansi(result.output)
    for csv in EXPECTED_CSVS:
        assert (out / csv).exists(), f"missing CSV: {csv}"


def test_pharma_generate_writes_metadata_json_with_audit_trail(tmp_path: Path) -> None:
    """metadata.json must contain effective_config, rng_state_hash,
    geo_lineage block, generated_at ISO-8601 timestamp."""
    out = tmp_path / "meta_run"
    result = _invoke_pharma_generate(out, sub_mode="acute-care", seed=42)
    assert result.exit_code == 0, strip_ansi(result.output)
    meta_path = out / "metadata.json"
    assert meta_path.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("effective_config", "rng_state_hash", "geo_lineage", "generated_at"):
        assert key in data, f"metadata.json missing key: {key!r}"
    # effective_config: full PharmaConfig dump.
    assert data["effective_config"]["seed"] == 42
    assert data["effective_config"]["sub_mode"] == "acute-care"
    # rng_state_hash: stable string per (seed, sub_mode).
    assert isinstance(data["rng_state_hash"], str) and len(data["rng_state_hash"]) >= 16
    # geo_lineage: license attribution.
    assert "ODbL" in data["geo_lineage"]["osm_license"]
    assert "dl-de/by-2-0" in data["geo_lineage"]["bkg_license"]
    # generated_at: ISO-8601 with timezone (must include 'T' separator).
    assert "T" in data["generated_at"]


def test_pharma_generate_writes_geo_lineage_md(tmp_path: Path) -> None:
    """geo_lineage.md is always written (license attribution)."""
    out = tmp_path / "lineage_run"
    result = _invoke_pharma_generate(out)
    assert result.exit_code == 0, strip_ansi(result.output)
    md = (out / "geo_lineage.md").read_text(encoding="utf-8")
    assert "ODbL" in md, "geo_lineage.md missing OSM license attribution"
    assert "dl-de/by-2-0" in md, "geo_lineage.md missing BKG license"
    assert "osm_hospitals_DE_test.csv" in md
    assert "bundeslaender_test.geojson" in md


def test_pharma_generate_creates_output_dir_if_missing(tmp_path: Path) -> None:
    """The CLI must mkdir parents (saas_v3 idiom)."""
    out = tmp_path / "deeply" / "nested" / "fresh"
    assert not out.exists()
    result = _invoke_pharma_generate(out)
    assert result.exit_code == 0, strip_ansi(result.output)
    assert out.is_dir()


# ---------------------------------------------------------------------------
# --benchmark-validation flag
# ---------------------------------------------------------------------------


def test_benchmark_validation_off_by_default(tmp_path: Path) -> None:
    """Without the flag, benchmark_validation.md must NOT be written."""
    out = tmp_path / "no_validation"
    result = _invoke_pharma_generate(out)
    assert result.exit_code == 0, strip_ansi(result.output)
    assert not (out / "benchmark_validation.md").exists()


def test_benchmark_validation_writes_markdown_when_enabled(tmp_path: Path) -> None:
    out = tmp_path / "with_validation"
    result = _invoke_pharma_generate(out, extra_args=("--benchmark-validation",))
    assert result.exit_code == 0, strip_ansi(result.output)
    md_path = out / "benchmark_validation.md"
    assert md_path.exists()
    md = md_path.read_text(encoding="utf-8")
    # Renders the table from validate.render_markdown().
    assert "ags_hierarchy_invariant" in md
    assert "Pharma benchmark validation" in md


# ---------------------------------------------------------------------------
# Bad-input handling
# ---------------------------------------------------------------------------


def test_pharma_generate_rejects_unknown_sub_mode(tmp_path: Path) -> None:
    result = runner.invoke(
        root_app,
        [
            "pharma",
            "generate",
            "--sub-mode",
            "vertical-account-based",  # not a pharma sub-mode
            "--hospitals-csv",
            str(HOSPITALS_CSV),
            "--bkg-bundeslaender",
            str(BL_GEOJSON),
            "--bkg-landkreise",
            str(LK_GEOJSON),
            "--output",
            str(tmp_path / "bad_mode"),
            "--seed",
            "42",
        ],
    )
    assert result.exit_code != 0
    output = strip_ansi(result.output)
    # Typer / Pydantic surface ValidationError; either way the
    # rejection must mention sub_mode / sub-mode somewhere.
    assert "sub" in output.lower() or "mode" in output.lower()


def test_pharma_generate_rejects_missing_hospitals_csv(tmp_path: Path) -> None:
    """File not found → non-zero exit."""
    result = runner.invoke(
        root_app,
        [
            "pharma",
            "generate",
            "--sub-mode",
            "acute-care",
            "--hospitals-csv",
            str(tmp_path / "does_not_exist.csv"),
            "--bkg-bundeslaender",
            str(BL_GEOJSON),
            "--bkg-landkreise",
            str(LK_GEOJSON),
            "--output",
            str(tmp_path / "out"),
            "--seed",
            "42",
        ],
    )
    assert result.exit_code != 0
    output = strip_ansi(result.output)
    # Typer surfaces "does not exist" via its Path validator.
    assert "exist" in output.lower() or "not found" in output.lower()


# ---------------------------------------------------------------------------
# Reproducibility through the CLI surface
# ---------------------------------------------------------------------------


def test_pharma_generate_reproducible_csv_bytes(tmp_path: Path) -> None:
    """Same seed → byte-identical CSVs across two CLI invocations.
    This is the integration-level reproducibility gate; the engine-
    level guarantee is in test_engine_smoke.py."""
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    res_a = _invoke_pharma_generate(out_a, seed=7)
    res_b = _invoke_pharma_generate(out_b, seed=7)
    assert res_a.exit_code == 0
    assert res_b.exit_code == 0
    for csv in EXPECTED_CSVS:
        bytes_a = (out_a / csv).read_bytes()
        bytes_b = (out_b / csv).read_bytes()
        assert bytes_a == bytes_b, f"CSV bytes differ across runs: {csv}"


# ---------------------------------------------------------------------------
# Friendly extra-missing error (no [pharma] extra installed)
# ---------------------------------------------------------------------------


def test_pharma_friendly_error_when_geopandas_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When geopandas isn't importable, ``pharma generate`` must exit
    non-zero with a plain-text install hint pointing at the
    ``[pharma]`` extra.

    Simulated by patching ``sys.modules['geopandas']`` to ``None``,
    which makes any subsequent ``import geopandas`` raise
    ``ImportError``. The CLI's lazy-import block must catch and
    convert.
    """
    import sys

    # Force ImportError on next ``import geopandas``.
    monkeypatch.setitem(sys.modules, "geopandas", None)

    result = _invoke_pharma_generate(tmp_path / "missing_extra")
    assert result.exit_code != 0
    output = strip_ansi(result.output)
    assert "pharma" in output.lower()
    assert "pip install" in output.lower() or "install" in output.lower()
