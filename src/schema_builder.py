"""
Schema builder: constructs the full table/column/relation graph for a scenario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import GeneratorConfig

from .config import Cardinality, ColumnConfig, DType, RelationConfig, TableConfig
from .id_utils import is_date_key_column, is_identifier_column


@dataclass
class SchemaGraph:
    tables: list[TableConfig] = field(default_factory=list)
    relations: list[RelationConfig] = field(default_factory=list)
    _index: dict[str, TableConfig] = field(default_factory=dict, repr=False)

    def add_table(self, table: TableConfig) -> None:
        self.tables.append(table)
        self._index[table.name] = table

    def get_table(self, name: str) -> TableConfig:
        return self._index[name]

    def has_table(self, name: str) -> bool:
        return name in self._index

    def topological_order(self) -> list[TableConfig]:
        in_degree: dict[str, int] = {t.name: 0 for t in self.tables}
        dependents: dict[str, list[str]] = {t.name: [] for t in self.tables}

        for rel in self.relations:
            if rel.cardinality == Cardinality.SELF:
                continue
            if rel.source_table != rel.target_table:
                in_degree[rel.source_table] += 1
                dependents[rel.target_table].append(rel.source_table)

        queue = [name for name, degree in in_degree.items() if degree == 0]
        ordered: list[str] = []
        while queue:
            node = queue.pop(0)
            ordered.append(node)
            for dependent in dependents.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        ordered.extend([name for name in in_degree if name not in ordered])
        return [self._index[name] for name in ordered]


class SchemaBuilder:
    def __init__(self, config: "GeneratorConfig") -> None:
        self.config = config

    def build(
        self,
        raw_tables: list[TableConfig],
        raw_relations: list[RelationConfig],
    ) -> SchemaGraph:
        graph = SchemaGraph()

        for table in raw_tables:
            graph.add_table(self._ensure_pk(self._apply_row_override(table)))

        expanded_relations: list[RelationConfig] = []
        for relation in raw_relations:
            if relation.cardinality == Cardinality.MANY_TO_MANY:
                junction, rel_a, rel_b = self._expand_nm(relation, graph)
                if not graph.has_table(junction.name):
                    graph.add_table(junction)
                expanded_relations.extend([rel_a, rel_b])
            else:
                expanded_relations.append(relation)
        graph.relations = expanded_relations

        for relation in expanded_relations:
            if relation.cardinality == Cardinality.SELF:
                continue
            table = graph.get_table(relation.source_table)
            if relation.source_column not in table.fk_columns:
                table.fk_columns.append(relation.source_column)
            if relation.source_column not in {col.name for col in table.columns}:
                table.columns.append(
                    ColumnConfig(
                        name=relation.source_column,
                        dtype=self._dtype_for_identifier(relation.source_column),
                        nullable=False,
                    )
                )

        return graph

    def _apply_row_override(self, table: TableConfig) -> TableConfig:
        if table.name in self.config.row_overrides:
            return table.model_copy(update={"row_count": self.config.row_overrides[table.name]})
        return table

    def _ensure_pk(self, table: TableConfig) -> TableConfig:
        if table.pk_column in {column.name for column in table.columns}:
            return table
        pk_col = ColumnConfig(
            name=table.pk_column,
            dtype=self._dtype_for_identifier(table.pk_column),
            nullable=False,
            unique=True,
        )
        return table.model_copy(update={"columns": [pk_col] + table.columns})

    @staticmethod
    def _dtype_for_identifier(column_name: str) -> DType:
        if is_date_key_column(column_name):
            return DType.INT
        if is_identifier_column(column_name):
            return DType.VARCHAR
        return DType.BIGINT

    def _expand_nm(
        self,
        relation: RelationConfig,
        graph: SchemaGraph,
    ) -> tuple[TableConfig, RelationConfig, RelationConfig]:
        junction_name = relation.junction_table or f"{relation.source_table}_{relation.target_table}_bridge"
        src_fk = f"{relation.source_table}_{relation.source_column}"
        tgt_fk = f"{relation.target_table}_{relation.target_column}"
        junction = TableConfig(
            name=junction_name,
            row_count=max(
                graph.get_table(relation.source_table).row_count,
                graph.get_table(relation.target_table).row_count,
            ),
            columns=[
                ColumnConfig(name=src_fk, dtype=DType.VARCHAR, nullable=False),
                ColumnConfig(name=tgt_fk, dtype=DType.VARCHAR, nullable=False),
            ],
            pk_column=src_fk,
            fk_columns=[src_fk, tgt_fk],
        )
        rel_a = RelationConfig(
            source_table=junction_name,
            source_column=src_fk,
            target_table=relation.source_table,
            target_column=relation.source_column,
            cardinality=Cardinality.ONE_TO_MANY,
        )
        rel_b = RelationConfig(
            source_table=junction_name,
            source_column=tgt_fk,
            target_table=relation.target_table,
            target_column=relation.target_column,
            cardinality=Cardinality.ONE_TO_MANY,
        )
        return junction, rel_a, rel_b
