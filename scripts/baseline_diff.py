"""
Phase 2 backward-compat baseline diff helper.

Usage:
    python scripts/baseline_diff.py capture <out_dir>
    python scripts/baseline_diff.py compare <baseline_dir> <candidate_dir>

Generates retail/saas/fintech/logistics with seed=42 (defaults), plus the
saas_v3 smoke run (v0.2.1+). The diff compares CSV bytes only — DDL/metadata
files (schema.sql, *.md, *.json) are ignored because they may legitimately
reference paths or version numbers that change during refactor.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Use sys.executable so subprocess invocations work cross-platform.
# The previous hardcoded ``.venv/Scripts/python.exe`` was Windows-only and
# crashed on CI Ubuntu (FileNotFoundError) — caught by the Phase-6 final
# CI matrix verification on c09af3e.
PYTHON = sys.executable

# Small row overrides per scenario to keep baseline diff fast and avoid
# latent default-scale bugs that are out of scope for Phase 2 (e.g. fintech
# leap-day card expiry crash). The audit confirmed empty diffs at "shrunken
# row counts" — these mirror that approach.
SCENARIO_ROWS: dict[str, str] = {
    "retail": (
        "dim_customers=100,dim_products=50,dim_stores=10,dim_date=365,"
        "dim_promotions=20,fact_orders=200,fact_order_items=400,"
        "fact_payments=200,bridge_order_promotions=100"
    ),
    "saas": (
        "accounts=100,users=300,subscriptions=120,invoices=300,features=20,"
        "feature_usage=400,events=600"
    ),
    "fintech": (
        "customers=100,accounts=150,merchants=50,transactions=400,cards=120,"
        "loans=80,loan_payments=200"
    ),
    "logistics": (
        "warehouses=10,suppliers=30,products=80,inventory=150,shipments=120,"
        "shipment_items=300,routes=40"
    ),
}
SCENARIOS = tuple(SCENARIO_ROWS)

# Phase 5 (v0.2.1) addition: pin the saas_v3 sub-app smoke run alongside
# the four legacy scenarios. saas_v3 uses YAML configs instead of --rows
# overrides, so the capture path differs. The smoke config runs in
# legacy mode (run.mode default "legacy"), so this baseline is byte-stable
# starting from v0.2.1 onward.
SAAS_V3_CAPTURE = {
    "label": "saas_v3",
    "config": "configs/saas_v3.smoke.yaml",
    "extra_args": [
        "--mode",
        "clean",  # Smoke run, deterministic CSVs only.
        # No --seed override; the YAML's seed: 42 is what gets pinned.
    ],
}

# Phase 6 (v0.3.0) addition: pin both pharma sub-modes against the
# hermetic test fixtures. Pharma writes 8 CSVs + metadata.json +
# geo_lineage.md to a flat output dir; ``compare`` already walks
# ``*.csv`` only so the non-deterministic ``metadata.json`` (carries
# a ``generated_at`` ISO-8601 timestamp) is implicitly excluded.
# Account count is small (100) so each capture finishes in well under
# a second.
_PHARMA_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "pharma"
PHARMA_CAPTURES: tuple[dict[str, str], ...] = (
    {
        "label": "pharma-acute",
        "sub_mode": "acute-care",
    },
    {
        "label": "pharma-specialty",
        "sub_mode": "specialty-care",
    },
)
PHARMA_LABELS: tuple[str, ...] = tuple(c["label"] for c in PHARMA_CAPTURES)


def capture_saas_v3(out_root: Path) -> None:
    """Capture the saas_v3 smoke run into ``out_root / "saas_v3"``.

    The sub-app produces a versioned run-root inside ``--output``. We
    flatten it under ``out_root / "saas_v3"`` so the existing _hash_csvs
    walker picks it up identically to the legacy scenarios.
    """
    target = out_root / SAAS_V3_CAPTURE["label"]
    print(f"[capture] saas_v3 -> {target}")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # The sub-app writes to --output/{name}_seed{seed}_{as_of}/...
    # We pass --output target directly; the sub-app creates the versioned
    # subdir inside it.
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            PYTHON,
            "-m",
            "synth_datagen.cli",
            "saas-v3",
            "generate",
            "--config",
            SAAS_V3_CAPTURE["config"],
            "--output",
            str(target),
            *SAAS_V3_CAPTURE["extra_args"],
        ],
        check=True,
        env=env,
    )


def capture_pharma(out_root: Path) -> None:
    """Capture both pharma sub-modes against the hermetic fixtures.

    Each sub-mode writes its 8 CSVs + metadata.json + geo_lineage.md
    to ``out_root / pharma-acute/`` and ``out_root / pharma-specialty/``
    respectively. ``compare`` walks ``*.csv`` only, so ``metadata.json``
    (with its non-deterministic ``generated_at``) is excluded from the
    byte-equality check.
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for cap in PHARMA_CAPTURES:
        target = out_root / cap["label"]
        print(f"[capture] {cap['label']} -> {target}")
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                PYTHON,
                "-m",
                "synth_datagen.cli",
                "pharma",
                "generate",
                "--sub-mode",
                cap["sub_mode"],
                "--hospitals-csv",
                str(_PHARMA_FIXTURE_DIR / "osm_hospitals_DE_test.csv"),
                "--bkg-bundeslaender",
                str(_PHARMA_FIXTURE_DIR / "bundeslaender_test.geojson"),
                "--bkg-landkreise",
                str(_PHARMA_FIXTURE_DIR / "landkreise_test.geojson"),
                "--seed",
                "42",
                "--account-count",
                "100",
                "--rep-count",
                "15",
                "--data-quality",
                "clean",
                "--output",
                str(target),
            ],
            check=True,
            env=env,
        )


def capture(out_root: Path) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for scenario in SCENARIOS:
        target = out_root / scenario
        print(f"[capture] {scenario} -> {target}")
        subprocess.run(
            [
                PYTHON,
                "-m",
                "synth_datagen.main",
                "generate",
                "--scenario",
                scenario,
                "--seed",
                "42",
                "--output",
                str(target),
                "--rows",
                SCENARIO_ROWS[scenario],
            ],
            check=True,
            env=env,
        )
    capture_saas_v3(out_root)
    capture_pharma(out_root)


def _hash_csvs(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for csv in sorted(root.rglob("*.csv")):
        rel = csv.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha256(csv.read_bytes()).hexdigest()
    return hashes


def compare(baseline: Path, candidate: Path) -> int:
    failures: list[str] = []
    targets = list(SCENARIOS) + [SAAS_V3_CAPTURE["label"]] + list(PHARMA_LABELS)
    skipped: list[str] = []
    for label in targets:
        baseline_target = baseline / label
        candidate_target = candidate / label
        if not baseline_target.exists():
            # Pharma labels were added in v0.3.0; saas_v3 in v0.2.1.
            # A pre-v0.3.0 baseline won't have pharma; pre-v0.2.1 won't
            # have saas_v3. Skip rather than fail — the same skip path
            # the saas_v3 v0.2.1 add-on used.
            era = (
                "pre-v0.3.0"
                if label in PHARMA_LABELS
                else "pre-v0.2.1"
                if label == SAAS_V3_CAPTURE["label"]
                else "older"
            )
            print(
                f"  [skip] {label}: baseline does not contain this target ({era} baseline)"
            )
            skipped.append(label)
            continue
        if not candidate_target.exists():
            failures.append(f"{label}: missing from candidate")
            continue
        b = _hash_csvs(baseline_target)
        c = _hash_csvs(candidate_target)
        if b.keys() != c.keys():
            missing_in_candidate = sorted(b.keys() - c.keys())
            extra_in_candidate = sorted(c.keys() - b.keys())
            failures.append(
                f"{label}: file set differs. missing={missing_in_candidate} extra={extra_in_candidate}"
            )
            continue
        for path, baseline_hash in b.items():
            if c[path] != baseline_hash:
                failures.append(f"{label}/{path}: hash mismatch")
    if failures:
        print("BASELINE DIFF FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    matched = len(targets) - len(skipped)
    if skipped:
        print(
            f"OK — {matched} scenarios match (CSV bytes identical), {len(skipped)} skipped ({', '.join(skipped)})."
        )
    else:
        print(f"OK — all {len(targets)} scenarios match (CSV bytes identical).")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "capture":
        capture(Path(argv[2]))
        return 0
    if cmd == "compare":
        return compare(Path(argv[2]), Path(argv[3]))
    print(f"Unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
