"""Regression guards for the pharma additions in scripts/baseline_diff.py.

Two unit tests:

1. ``test_baseline_diff_includes_pharma_targets`` — import-level
   sanity that the pharma labels show up in the script's targets
   list. Catches a refactor that drops or renames the pharma block.

2. ``test_baseline_diff_pharma_capture_writes_csvs`` — invokes
   ``capture_pharma`` end-to-end against ``tmp_path`` and confirms
   the 8 CSV files land under both sub-modes' subdirs. Catches a
   path-resolution or sub-app-invocation regression.

The actual byte-equality gate is the manual ``compare`` ceremony in
commit 14; these tests just ensure the script's structure stays
intact across refactors.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Skip whole module if [pharma] extra missing — the capture path
# shells out to the pharma sub-app, which needs geopandas.
pytest.importorskip("geopandas", reason="requires '[pharma]' extra")
pytest.importorskip("shapely", reason="requires '[pharma]' extra")

# scripts/baseline_diff.py isn't a package; load it as an arbitrary
# module so we can introspect its module-level constants.
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "baseline_diff.py"


def _load_baseline_diff_module():
    """Load scripts/baseline_diff.py as a module under the synthetic
    name ``_baseline_diff_under_test``."""
    spec = importlib.util.spec_from_file_location(
        "_baseline_diff_under_test", SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_baseline_diff_includes_pharma_targets() -> None:
    """``PHARMA_LABELS`` must contain both sub-modes; ``compare()``
    targets list must end with these labels (after legacy + saas_v3)."""
    module = _load_baseline_diff_module()
    assert module.PHARMA_LABELS == ("pharma-acute", "pharma-specialty"), (
        f"PHARMA_LABELS shape changed: {module.PHARMA_LABELS!r}"
    )
    # The two sub-mode entries also appear in PHARMA_CAPTURES with
    # matching label/sub_mode pairs.
    by_label = {c["label"]: c["sub_mode"] for c in module.PHARMA_CAPTURES}
    assert by_label == {
        "pharma-acute": "acute-care",
        "pharma-specialty": "specialty-care",
    }


def test_baseline_diff_pharma_capture_writes_csvs(tmp_path: Path) -> None:
    """Invoking capture_pharma against tmp_path must produce 8 CSVs
    under each sub-mode's subdirectory.

    This shells out to the pharma sub-app via subprocess.run — same
    code path the production capture uses. Slow-ish (~3-5 s for two
    sub-mode runs at account_count=100) but still well inside the
    fast-lane budget.
    """
    module = _load_baseline_diff_module()
    module.capture_pharma(tmp_path)

    expected_csvs = {
        "accounts.csv",
        "sales_reps.csv",
        "territories.csv",
        "products.csv",
        "orders.csv",
        "rep_visits.csv",
        "account_specialties.csv",
        "geographic_metadata.csv",
    }
    for label in module.PHARMA_LABELS:
        sub_dir = tmp_path / label
        assert sub_dir.is_dir(), f"capture_pharma did not create {sub_dir}"
        actual_csvs = {p.name for p in sub_dir.glob("*.csv")}
        missing = expected_csvs - actual_csvs
        assert not missing, f"{label}: missing CSVs {missing}"
