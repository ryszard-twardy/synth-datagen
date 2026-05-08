"""Pharma Field Sales scenario (acute-care + specialty-care sub-modes).

Phase 6 — v0.3.0. Generates synthetic German pharmaceutical sales data
calibrated against DESTATIS Krankenhausstatistik, PHAGRO wholesale
benchmarks, IQVIA DKM, vfa Innovationsbilanz/Biotech-Report, and
Pharmalotse field-force statistics.

Layout mirrors ``synth_datagen.saas_v3`` — flat module set, no
``scenarios/`` subtree. Public engine entry point will be exported here
once the engine module lands later in the Phase 6 commit sequence.

The pharma scenario depends on ``geopandas`` and ``shapely`` for spatial
joins against BKG VG250 administrative boundaries. Those are NOT core
dependencies — install via the ``[pharma]`` optional extra::

    pip install 'synth-datagen[pharma]'

The CLI entry point fails fast with a friendly message if the extra is
missing.
"""

from __future__ import annotations
