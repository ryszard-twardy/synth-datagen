"""
Phase 2 backward-compat baseline diff helper.

Usage:
    python scripts/baseline_diff.py capture <out_dir>
    python scripts/baseline_diff.py compare <baseline_dir> <candidate_dir>

Generates retail/saas/fintech/logistics with seed=42 (defaults). The diff
compares CSV bytes only — DDL/metadata files (schema.sql, *.md, *.json)
are ignored because they may legitimately reference paths or version
numbers that change during refactor.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")

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
                PYTHON, "-m", "src.main", "generate",
                "--scenario", scenario,
                "--seed", "42",
                "--output", str(target),
                "--rows", SCENARIO_ROWS[scenario],
            ],
            check=True,
            env=env,
        )


def _hash_csvs(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for csv in sorted(root.rglob("*.csv")):
        rel = csv.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha256(csv.read_bytes()).hexdigest()
    return hashes


def compare(baseline: Path, candidate: Path) -> int:
    failures: list[str] = []
    for scenario in SCENARIOS:
        b = _hash_csvs(baseline / scenario)
        c = _hash_csvs(candidate / scenario)
        if b.keys() != c.keys():
            missing_in_candidate = sorted(b.keys() - c.keys())
            extra_in_candidate = sorted(c.keys() - b.keys())
            failures.append(
                f"{scenario}: file set differs. missing={missing_in_candidate} extra={extra_in_candidate}"
            )
            continue
        for path, baseline_hash in b.items():
            if c[path] != baseline_hash:
                failures.append(f"{scenario}/{path}: hash mismatch")
    if failures:
        print("BASELINE DIFF FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK — all {len(SCENARIOS)} scenarios match (CSV bytes identical).")
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
