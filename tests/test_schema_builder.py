"""Direct unit tests for SchemaBuilder + SchemaGraph (P7 coverage hardening).

Pre-P7 coverage on ``src/synth_datagen/schema_builder.py`` was 74% — the
module is exercised indirectly by every scenario test, but several
branches (Cardinality.SELF, _expand_nm whole method, _ensure_pk inject
path, _dtype_for_identifier date-key vs identifier vs bigint) had no
direct coverage. These tests pin every public surface.
"""

from __future__ import annotations


from synth_datagen.config import (
    Cardinality,
    ColumnConfig,
    DataQuality,
    DataQualityConfig,
    Dialect,
    DType,
    GeneratorConfig,
    RelationConfig,
    Scenario,
    SchemaType,
    TableConfig,
)
from synth_datagen.schema_builder import SchemaBuilder, SchemaGraph


def _config(tmp_path, row_overrides: dict[str, int] | None = None) -> GeneratorConfig:
    return GeneratorConfig(
        scenario=Scenario.RETAIL,
        schema_type=SchemaType.STAR,
        dialect=Dialect.POSTGRES,
        seed=42,
        output_dir=tmp_path,
        chunk_size=500,
        row_overrides=row_overrides or {},
        data_quality=DataQualityConfig(level=DataQuality.NONE),
    )


def _table(
    name: str, pk: str = "id", row_count: int = 10, extra_cols: list | None = None
) -> TableConfig:
    cols = [ColumnConfig(name=pk, dtype=DType.VARCHAR, nullable=False, unique=True)]
    if extra_cols:
        cols.extend(extra_cols)
    return TableConfig(name=name, row_count=row_count, pk_column=pk, columns=cols)


class TestSchemaGraph:
    def test_add_and_get_table(self) -> None:
        graph = SchemaGraph()
        t = _table("orders")
        graph.add_table(t)
        assert graph.get_table("orders") is t
        assert graph.has_table("orders")

    def test_has_table_false_for_unknown(self) -> None:
        graph = SchemaGraph()
        assert not graph.has_table("nope")

    def test_topological_order_respects_dependencies(self) -> None:
        """orders depends on customers -> customers comes first."""
        graph = SchemaGraph()
        graph.add_table(_table("customers"))
        graph.add_table(_table("orders"))
        graph.relations = [
            RelationConfig(
                source_table="orders",
                source_column="customer_id",
                target_table="customers",
                target_column="id",
                cardinality=Cardinality.ONE_TO_MANY,
            )
        ]
        order = [t.name for t in graph.topological_order()]
        assert order.index("customers") < order.index("orders")

    def test_topological_order_skips_self_relations(self) -> None:
        """``Cardinality.SELF`` relations must not contribute to in-degree
        (line 39 — the ``continue`` branch)."""
        graph = SchemaGraph()
        graph.add_table(_table("employees"))
        graph.relations = [
            RelationConfig(
                source_table="employees",
                source_column="manager_id",
                target_table="employees",
                target_column="id",
                cardinality=Cardinality.SELF,
            )
        ]
        order = [t.name for t in graph.topological_order()]
        # Should not infinite loop or raise; employees lands in the output once.
        assert order == ["employees"]

    def test_topological_order_includes_disconnected_table(self) -> None:
        """Tables with no relations still appear in the output (line 54
        ordered.extend(...))."""
        graph = SchemaGraph()
        graph.add_table(_table("standalone"))
        order = [t.name for t in graph.topological_order()]
        assert "standalone" in order


class TestSchemaBuilderBuild:
    def test_build_passes_through_simple_one_to_many(self, tmp_path) -> None:
        builder = SchemaBuilder(_config(tmp_path))
        graph = builder.build(
            raw_tables=[_table("customers"), _table("orders", pk="order_id")],
            raw_relations=[
                RelationConfig(
                    source_table="orders",
                    source_column="customer_id",
                    target_table="customers",
                    target_column="id",
                    cardinality=Cardinality.ONE_TO_MANY,
                )
            ],
        )
        # The FK column was injected onto the source table.
        orders = graph.get_table("orders")
        assert "customer_id" in {col.name for col in orders.columns}
        assert "customer_id" in orders.fk_columns

    def test_build_does_not_re_add_existing_fk_column(self, tmp_path) -> None:
        """If the FK column already exists on the source table, line 89
        (``not in {col.name for col ...}``) keeps the column list unchanged."""
        existing_fk = ColumnConfig(
            name="customer_id", dtype=DType.VARCHAR, nullable=False
        )
        builder = SchemaBuilder(_config(tmp_path))
        graph = builder.build(
            raw_tables=[
                _table("customers"),
                _table("orders", pk="order_id", extra_cols=[existing_fk]),
            ],
            raw_relations=[
                RelationConfig(
                    source_table="orders",
                    source_column="customer_id",
                    target_table="customers",
                    target_column="id",
                    cardinality=Cardinality.ONE_TO_MANY,
                )
            ],
        )
        orders = graph.get_table("orders")
        # customer_id must appear exactly once (not duplicated by the inject branch).
        names = [col.name for col in orders.columns]
        assert names.count("customer_id") == 1

    def test_build_skips_self_relations_for_fk_injection(self, tmp_path) -> None:
        """``Cardinality.SELF`` relations skip the FK-inject path (line 84)."""
        builder = SchemaBuilder(_config(tmp_path))
        graph = builder.build(
            raw_tables=[_table("employees")],
            raw_relations=[
                RelationConfig(
                    source_table="employees",
                    source_column="manager_id",
                    target_table="employees",
                    target_column="id",
                    cardinality=Cardinality.SELF,
                )
            ],
        )
        employees = graph.get_table("employees")
        # SELF relation does not auto-inject the column; it is the caller's job.
        assert "manager_id" not in {col.name for col in employees.columns}

    def test_apply_row_override(self, tmp_path) -> None:
        builder = SchemaBuilder(_config(tmp_path, row_overrides={"orders": 5}))
        graph = builder.build(
            raw_tables=[_table("orders", row_count=10_000)],
            raw_relations=[],
        )
        assert graph.get_table("orders").row_count == 5

    def test_row_override_does_not_affect_other_tables(self, tmp_path) -> None:
        builder = SchemaBuilder(_config(tmp_path, row_overrides={"orders": 5}))
        graph = builder.build(
            raw_tables=[_table("orders", row_count=999), _table("items", row_count=42)],
            raw_relations=[],
        )
        assert graph.get_table("items").row_count == 42

    def test_ensure_pk_injects_missing_pk_column(self, tmp_path) -> None:
        """Lines 110-116: when pk_column is not in columns, prepend it."""
        builder = SchemaBuilder(_config(tmp_path))
        # Build a table where pk_column "customer_id" is NOT in columns.
        bad_table = TableConfig(
            name="customers",
            row_count=10,
            pk_column="customer_id",
            columns=[ColumnConfig(name="name", dtype=DType.VARCHAR, nullable=False)],
        )
        graph = builder.build(raw_tables=[bad_table], raw_relations=[])
        result = graph.get_table("customers")
        col_names = [col.name for col in result.columns]
        # PK injected at the front; original column preserved.
        assert col_names[0] == "customer_id"
        assert "name" in col_names

    def test_ensure_pk_leaves_existing_pk_alone(self, tmp_path) -> None:
        builder = SchemaBuilder(_config(tmp_path))
        good_table = _table("orders", pk="order_id")
        graph = builder.build(raw_tables=[good_table], raw_relations=[])
        result = graph.get_table("orders")
        col_names = [col.name for col in result.columns]
        assert col_names.count("order_id") == 1


class TestSchemaBuilderDtypeForIdentifier:
    """Lines 120-124 — three branches of ``_dtype_for_identifier``."""

    def test_date_key_column_maps_to_int(self) -> None:
        # date_id is the canonical date-key column name.
        assert SchemaBuilder._dtype_for_identifier("date_id") == DType.INT

    def test_identifier_column_maps_to_varchar(self) -> None:
        # *_id columns are identifiers per id_utils
        assert SchemaBuilder._dtype_for_identifier("customer_id") == DType.VARCHAR

    def test_other_column_maps_to_bigint(self) -> None:
        assert SchemaBuilder._dtype_for_identifier("counter") == DType.BIGINT


class TestSchemaBuilderManyToManyExpansion:
    """Lines 75-78, 131-164 — the M2M relation -> junction table expansion."""

    def test_m2m_creates_junction_table(self, tmp_path) -> None:
        builder = SchemaBuilder(_config(tmp_path))
        graph = builder.build(
            raw_tables=[
                _table("orders", pk="order_id", row_count=100),
                _table("promotions", pk="promo_id", row_count=20),
            ],
            raw_relations=[
                RelationConfig(
                    source_table="orders",
                    source_column="order_id",
                    target_table="promotions",
                    target_column="promo_id",
                    cardinality=Cardinality.MANY_TO_MANY,
                )
            ],
        )
        # Default junction name is "<src>_<tgt>_bridge"
        assert graph.has_table("orders_promotions_bridge")
        junction = graph.get_table("orders_promotions_bridge")
        col_names = {col.name for col in junction.columns}
        assert {"orders_order_id", "promotions_promo_id"} <= col_names

    def test_m2m_junction_inherits_max_row_count(self, tmp_path) -> None:
        """Junction row_count = max(source.row_count, target.row_count)."""
        builder = SchemaBuilder(_config(tmp_path))
        graph = builder.build(
            raw_tables=[
                _table("a", pk="a_id", row_count=200),
                _table("b", pk="b_id", row_count=50),
            ],
            raw_relations=[
                RelationConfig(
                    source_table="a",
                    source_column="a_id",
                    target_table="b",
                    target_column="b_id",
                    cardinality=Cardinality.MANY_TO_MANY,
                )
            ],
        )
        assert graph.get_table("a_b_bridge").row_count == 200

    def test_m2m_with_explicit_junction_name(self, tmp_path) -> None:
        builder = SchemaBuilder(_config(tmp_path))
        graph = builder.build(
            raw_tables=[
                _table("orders", pk="order_id", row_count=100),
                _table("promos", pk="promo_id", row_count=20),
            ],
            raw_relations=[
                RelationConfig(
                    source_table="orders",
                    source_column="order_id",
                    target_table="promos",
                    target_column="promo_id",
                    cardinality=Cardinality.MANY_TO_MANY,
                    junction_table="custom_bridge",
                )
            ],
        )
        assert graph.has_table("custom_bridge")
        assert not graph.has_table("orders_promos_bridge")

    def test_m2m_does_not_re_add_existing_junction(self, tmp_path) -> None:
        """If a table named like the junction already exists in raw_tables,
        line 76-77 (``if not graph.has_table(junction.name)``) keeps it."""
        existing_junction = _table("orders_promos_bridge", pk="bridge_id")
        builder = SchemaBuilder(_config(tmp_path))
        graph = builder.build(
            raw_tables=[
                _table("orders", pk="order_id", row_count=100),
                _table("promos", pk="promo_id", row_count=20),
                existing_junction,
            ],
            raw_relations=[
                RelationConfig(
                    source_table="orders",
                    source_column="order_id",
                    target_table="promos",
                    target_column="promo_id",
                    cardinality=Cardinality.MANY_TO_MANY,
                )
            ],
        )
        # The original PK is preserved (would be replaced if junction was re-added).
        assert graph.get_table("orders_promos_bridge").pk_column == "bridge_id"
