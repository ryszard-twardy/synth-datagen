from __future__ import annotations


import pandas as pd
import pytest

from synth_datagen.config import DataQuality, DType, Scenario
from tests.helpers import generate_exported_csvs


@pytest.mark.parametrize("scenario", [Scenario.RETAIL, Scenario.SAAS, Scenario.FINTECH, Scenario.LOGISTICS])
@pytest.mark.parametrize("dq_level", [DataQuality.LIGHT, DataQuality.HEAVY])
def test_dq_preserves_structured_fields(tmp_path, scenario: Scenario, dq_level: DataQuality) -> None:
    dfs, graph = generate_exported_csvs(scenario, tmp_path, data_quality=dq_level)

    for table in graph.topological_order():
        df = dfs[table.name]
        for column in table.columns:
            if column.pattern and column.name in df.columns:
                assert df[column.name].dropna().astype(str).str.fullmatch(column.pattern).all()
            if column.dtype in {DType.DATE, DType.TIMESTAMP} and column.name in df.columns:
                non_null = df[column.name].dropna()
                parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
                assert parsed.notna().all(), f"{table.name}.{column.name} contains unparseable values"

        if "email" in df.columns:
            assert df["email"].dropna().astype(str).str.contains(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", regex=True).all()
        if "domain" in df.columns:
            assert df["domain"].dropna().astype(str).str.contains(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", regex=True).all()
        if "sku" in df.columns:
            assert not df["sku"].dropna().astype(str).str.contains("_dup", regex=False).any()
        if "gateway_ref" in df.columns:
            assert df["gateway_ref"].dropna().astype(str).str.fullmatch(r"GW-[0-9A-F]{12}").all()

    for relation in graph.relations:
        src_vals = dfs[relation.source_table][relation.source_column].dropna().astype(str)
        tgt_vals = set(dfs[relation.target_table][relation.target_column].dropna().astype(str).tolist())
        assert src_vals.isin(tgt_vals).all()
