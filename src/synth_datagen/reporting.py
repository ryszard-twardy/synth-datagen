"""
Shared metadata writers for generated datasets.
"""

from __future__ import annotations

from rich.console import Console

from .config import GeneratorConfig
from .schema_builder import SchemaGraph


def write_data_dictionary(graph: SchemaGraph, config: GeneratorConfig, console: Console | None = None) -> None:
    lines = [
        "# Data Dictionary",
        "",
        f"**Scenario**: `{config.scenario.value}` | **Schema**: `{config.schema_type.value}` | **Seed**: `{config.seed}`",
        "",
    ]

    fk_map: dict[tuple[str, str], tuple[str, str]] = {}
    for relation in graph.relations:
        fk_map[(relation.source_table, relation.source_column)] = (
            relation.target_table,
            relation.target_column,
        )

    for table in graph.topological_order():
        lines.extend([
            f"## `{table.name}`",
            "",
            f"**Row count (default)**: {table.row_count:,}  | **PK**: `{table.pk_column}`",
            "",
            "| Column | Type | Nullable | Unique | Pattern | FK | Semantic |",
            "|--------|------|----------|--------|---------|----|----------|",
        ])
        for column in table.columns:
            fk_ref = fk_map.get((table.name, column.name))
            fk_text = f"`{fk_ref[0]}.{fk_ref[1]}`" if fk_ref else ""
            lines.append(
                f"| `{column.name}` | `{column.dtype.value}` | "
                f"{'yes' if column.nullable else 'no'} | "
                f"{'yes' if column.unique else 'no'} | "
                f"`{column.pattern or ''}` | {fk_text} | "
                f"`{column.semantic_type.value if column.semantic_type else ''}` |"
            )
        lines.append("")

    out_path = config.output_dir / "data_dictionary.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    if console:
        console.print(f"[green][OK][/green] Data dictionary -> {out_path}")


def write_erd(graph: SchemaGraph, config: GeneratorConfig, console: Console | None = None) -> None:
    lines = ["# Entity Relationship Diagram", "", "```mermaid", "erDiagram"]
    for table in graph.topological_order():
        lines.append(f"    {table.name} {{")
        for column in table.columns:
            pk_tag = " PK" if column.name == table.pk_column else (" FK" if column.name in table.fk_columns else "")
            lines.append(f"        {column.dtype.value} {column.name}{pk_tag}")
        lines.append("    }")
    for relation in graph.relations:
        lines.append(f'    {relation.target_table} ||--o{{ {relation.source_table} : "has"')
    lines.extend(["```", ""])
    out_path = config.output_dir / "erd.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    if console:
        console.print(f"[green][OK][/green] ERD (Mermaid) -> {out_path}")
