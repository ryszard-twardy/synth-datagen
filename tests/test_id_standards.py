from __future__ import annotations


import pytest

from src.config import DataQuality, Scenario
from tests.helpers import generate_exported_csvs


@pytest.mark.parametrize("scenario", [Scenario.RETAIL, Scenario.SAAS, Scenario.FINTECH, Scenario.LOGISTICS])
@pytest.mark.parametrize("dq_level", [DataQuality.NONE, DataQuality.LIGHT])
def test_id_formats_and_fk_integrity(tmp_path, scenario: Scenario, dq_level: DataQuality) -> None:
    dfs, graph = generate_exported_csvs(scenario, tmp_path, data_quality=dq_level)

    for table in graph.topological_order():
        df = dfs[table.name]
        pk = table.pk_column
        assert df[pk].notna().all(), f"{table.name}.{pk} contains null PK values"
        assert df[pk].astype(str).is_unique, f"{table.name}.{pk} contains duplicate PK values"
        pk_cfg = next(column for column in table.columns if column.name == pk)
        if pk_cfg.pattern:
            assert df[pk].astype(str).str.fullmatch(pk_cfg.pattern).all(), f"{table.name}.{pk} violates ID format"

        for column in table.columns:
            if not column.pattern or column.name not in df.columns:
                continue
            series = df[column.name].dropna().astype(str)
            assert series.str.fullmatch(column.pattern).all(), f"{table.name}.{column.name} violates pattern {column.pattern}"

    for relation in graph.relations:
        src_vals = dfs[relation.source_table][relation.source_column].dropna().astype(str)
        tgt_vals = set(dfs[relation.target_table][relation.target_column].dropna().astype(str).tolist())
        assert src_vals.isin(tgt_vals).all(), f"Broken FK: {relation.source_table}.{relation.source_column}"

