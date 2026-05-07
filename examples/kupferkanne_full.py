"""Kupferkanne RFM scenario — monthly star-schema fact shards from YAML config.

Demonstrates the dedicated kupferkanne-rfm sub-command, which generates
per-month order/items CSVs plus shared dimension tables for RFM analysis.

Note: the default config covers Jan 2023 – Mar 2026 (39 months) and writes
~80 files. Expect ~5 minutes wall time. Trim the period in the YAML for
faster runs.

Run from repo root:

    python examples/kupferkanne_full.py

Equivalent CLI form:

    synth-datagen kupferkanne-rfm generate \\
        --config configs/kupferkanne_rfm_v3.yaml \\
        --output ./out/kupferkanne --seed 42
"""

from pathlib import Path

from synth_datagen.kupferkanne_rfm import generate_kupferkanne_rfm
from synth_datagen.kupferkanne_rfm_config import load_kupferkanne_rfm_config

CONFIG_PATH = Path("configs/kupferkanne_rfm_v3.yaml")
OUTPUT_DIR = Path("./out/kupferkanne")

config = load_kupferkanne_rfm_config(CONFIG_PATH)
generate_kupferkanne_rfm(config, OUTPUT_DIR, seed=42)
print(f"[OK] Kupferkanne RFM dataset written to {OUTPUT_DIR.resolve()}")
