"""
Logistics / supply-chain scenario generator.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterator

import numpy as np
import pandas as pd
from faker import Faker

from ..config import ColumnConfig, DType, GeneratorConfig, RelationConfig, TableConfig
from ..id_utils import make_id_list
from ..schema_builder import SchemaGraph
from ..utils import COUNTRY_NAMES, COUNTRY_WEIGHTS, bounded_lognormal, datetime_range_samples, distribute_counts, weighted_choice
from .base import BaseScenarioGenerator

_SHIP_STATUS = ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "failed"]
_SHIP_W = [0.05, 0.08, 0.20, 0.10, 0.52, 0.05]
_TRANSPORT = ["road", "air", "sea", "rail", "courier"]
_TRANSPORT_W = [0.45, 0.22, 0.14, 0.09, 0.10]
_INCOTERMS = ["EXW", "FOB", "CIF", "DDP", "DAP"]
_SIM_START = datetime(2021, 1, 1)
_AS_OF = datetime(2025, 12, 31, 23, 59, 59)


class LogisticsGenerator(BaseScenarioGenerator):
    def __init__(self, config: GeneratorConfig, rng: np.random.Generator, faker: Faker) -> None:
        super().__init__(config, rng, faker)
        self._cache: dict[str, pd.DataFrame] | None = None

    def get_raw_schema(self) -> tuple[list[TableConfig], list[RelationConfig]]:
        ov = self.config.row_overrides
        tables = [
            TableConfig(
                name="warehouses",
                row_count=ov.get("warehouses", 100),
                pk_column="warehouse_id",
                columns=[
                    ColumnConfig(name="warehouse_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="name", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="city", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="capacity_m3", dtype=DType.FLOAT, nullable=True),
                    ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="suppliers",
                row_count=ov.get("suppliers", 500),
                pk_column="supplier_id",
                columns=[
                    ColumnConfig(name="supplier_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="name", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="lead_time_days", dtype=DType.INT, nullable=True),
                    ColumnConfig(name="rating", dtype=DType.FLOAT, nullable=True),
                    ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="products",
                row_count=ov.get("products", 3_000),
                pk_column="product_id",
                columns=[
                    ColumnConfig(name="product_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="sku", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="name", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="category", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="supplier_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="weight_kg", dtype=DType.FLOAT, nullable=True),
                    ColumnConfig(name="unit_cost", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(name="is_hazardous", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="inventory",
                row_count=ov.get("inventory", 10_000),
                pk_column="inv_id",
                columns=[
                    ColumnConfig(name="inv_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="warehouse_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="product_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="qty_on_hand", dtype=DType.INT, nullable=False),
                    ColumnConfig(name="qty_reserved", dtype=DType.INT, nullable=False),
                    ColumnConfig(name="last_updated", dtype=DType.TIMESTAMP, nullable=False),
                    ColumnConfig(name="reorder_point", dtype=DType.INT, nullable=True),
                ],
            ),
            TableConfig(
                name="carriers",
                row_count=ov.get("carriers", 50),
                pk_column="carrier_id",
                columns=[
                    ColumnConfig(name="carrier_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="name", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="transport", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="rating", dtype=DType.FLOAT, nullable=True),
                    ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="shipments",
                row_count=ov.get("shipments", 50_000),
                pk_column="shipment_id",
                columns=[
                    ColumnConfig(name="shipment_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="carrier_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="origin_wh", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="dest_country", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="transport_mode", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="incoterm", dtype=DType.VARCHAR, nullable=True),
                    ColumnConfig(name="shipped_at", dtype=DType.TIMESTAMP, nullable=False),
                    ColumnConfig(name="estimated_at", dtype=DType.TIMESTAMP, nullable=False),
                    ColumnConfig(name="delivered_at", dtype=DType.TIMESTAMP, nullable=True),
                    ColumnConfig(name="freight_cost", dtype=DType.DECIMAL, nullable=False),
                ],
            ),
            TableConfig(
                name="shipment_items",
                row_count=ov.get("shipment_items", 120_000),
                pk_column="si_id",
                columns=[
                    ColumnConfig(name="si_id", dtype=DType.VARCHAR, nullable=False, unique=True),
                    ColumnConfig(name="shipment_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="product_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="qty", dtype=DType.INT, nullable=False),
                    ColumnConfig(name="unit_cost", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(name="line_value", dtype=DType.DECIMAL, nullable=False),
                ],
            ),
        ]
        relations = [
            RelationConfig(source_table="products", source_column="supplier_id", target_table="suppliers", target_column="supplier_id"),
            RelationConfig(source_table="inventory", source_column="warehouse_id", target_table="warehouses", target_column="warehouse_id"),
            RelationConfig(source_table="inventory", source_column="product_id", target_table="products", target_column="product_id"),
            RelationConfig(source_table="shipments", source_column="carrier_id", target_table="carriers", target_column="carrier_id"),
            RelationConfig(source_table="shipments", source_column="origin_wh", target_table="warehouses", target_column="warehouse_id"),
            RelationConfig(source_table="shipment_items", source_column="shipment_id", target_table="shipments", target_column="shipment_id"),
            RelationConfig(source_table="shipment_items", source_column="product_id", target_table="products", target_column="product_id"),
        ]
        return tables, relations

    def generate_table(
        self,
        table: TableConfig,
        graph: SchemaGraph,
        fk_pools: dict[str, np.ndarray],
    ) -> Iterator[pd.DataFrame]:
        self._ensure_cache(graph)
        yield from self._yield_cached_table(self._cache[table.name])

    def _ensure_cache(self, graph: SchemaGraph) -> None:
        if self._cache is None:
            self._cache = self._build_all_tables(graph)

    def _build_all_tables(self, graph: SchemaGraph) -> dict[str, pd.DataFrame]:
        counts = {table.name: table.row_count for table in graph.tables}
        warehouses = self._build_warehouses(counts["warehouses"])
        suppliers = self._build_suppliers(counts["suppliers"])
        products = self._build_products(counts["products"], suppliers)
        inventory = self._build_inventory(counts["inventory"], warehouses, products)
        carriers = self._build_carriers(counts["carriers"])
        shipments, shipment_items = self._build_shipments_and_items(counts["shipments"], counts["shipment_items"], warehouses, products, carriers)
        return {
            "warehouses": warehouses,
            "suppliers": suppliers,
            "products": products,
            "inventory": inventory,
            "carriers": carriers,
            "shipments": shipments,
            "shipment_items": shipment_items,
        }

    def _build_warehouses(self, row_count: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "warehouse_id": make_id_list("warehouse_id", 1, row_count),
                "name": [f"WH-{self.faker.city()[:12]}" for _ in range(row_count)],
                "city": [self.faker.city() for _ in range(row_count)],
                "country": weighted_choice(COUNTRY_NAMES, COUNTRY_WEIGHTS, row_count, self.rng).tolist(),
                "capacity_m3": np.round(self.rng.uniform(800, 55_000, row_count), 1),
                "is_active": self.rng.random(row_count) > 0.05,
            }
        )

    def _build_suppliers(self, row_count: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "supplier_id": make_id_list("supplier_id", 1, row_count),
                "name": [self.faker.company() for _ in range(row_count)],
                "country": weighted_choice(COUNTRY_NAMES, COUNTRY_WEIGHTS, row_count, self.rng).tolist(),
                "lead_time_days": self.rng.integers(3, 61, size=row_count),
                "rating": np.round(self.rng.uniform(2.5, 5.0, row_count), 1),
                "is_active": self.rng.random(row_count) > 0.08,
            }
        )

    def _build_products(self, row_count: int, suppliers: pd.DataFrame) -> pd.DataFrame:
        categories = ["Electronics", "Chemicals", "Textiles", "Machinery", "Food", "Packaging", "Metals", "Plastics", "Pharmaceuticals", "Agricultural"]
        supplier_ids = suppliers["supplier_id"].to_numpy()
        unit_cost = np.round(bounded_lognormal(3.4, 0.9, 0.5, 4_000.0, row_count, self.rng), 2)
        return pd.DataFrame(
            {
                "product_id": make_id_list("product_id", 1, row_count),
                "sku": [f"LOG-{idx + 1:08d}" for idx in range(row_count)],
                "name": [f"{self.faker.color_name()} {str(self.rng.choice(categories))} Item" for _ in range(row_count)],
                "category": [str(self.rng.choice(categories)) for _ in range(row_count)],
                "supplier_id": [str(self.rng.choice(supplier_ids)) for _ in range(row_count)],
                "weight_kg": np.round(self.rng.uniform(0.5, 500.0, row_count), 2),
                "unit_cost": unit_cost,
                "is_hazardous": self.rng.random(row_count) < 0.08,
            }
        )

    def _build_inventory(self, row_count: int, warehouses: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
        warehouse_ids = warehouses["warehouse_id"].tolist()
        product_ids = products["product_id"].tolist()
        all_pairs = [(warehouse_id, product_id) for warehouse_id in warehouse_ids for product_id in product_ids]
        chosen_idx = self.rng.choice(len(all_pairs), size=row_count, replace=False)
        pairs = [all_pairs[int(idx)] for idx in chosen_idx]
        qty_on_hand = self.rng.integers(0, 10_001, size=row_count)
        qty_reserved = np.minimum(self.rng.integers(0, 700, size=row_count), qty_on_hand)
        return pd.DataFrame(
            {
                "inv_id": make_id_list("inv_id", 1, row_count),
                "warehouse_id": [pair[0] for pair in pairs],
                "product_id": [pair[1] for pair in pairs],
                "qty_on_hand": qty_on_hand,
                "qty_reserved": qty_reserved,
                "last_updated": pd.to_datetime(datetime_range_samples(_SIM_START, _AS_OF, row_count, self.rng)),
                "reorder_point": self.rng.integers(25, 1_001, size=row_count),
            }
        )

    def _build_carriers(self, row_count: int) -> pd.DataFrame:
        transport = weighted_choice(_TRANSPORT, _TRANSPORT_W, row_count, self.rng).tolist()
        return pd.DataFrame(
            {
                "carrier_id": make_id_list("carrier_id", 1, row_count),
                "name": [self.faker.company() for _ in range(row_count)],
                "transport": transport,
                "country": weighted_choice(COUNTRY_NAMES, COUNTRY_WEIGHTS, row_count, self.rng).tolist(),
                "rating": np.round(self.rng.uniform(2.8, 5.0, row_count), 1),
                "is_active": self.rng.random(row_count) > 0.08,
            }
        )

    def _build_shipments_and_items(
        self,
        shipment_count: int,
        item_count: int,
        warehouses: pd.DataFrame,
        products: pd.DataFrame,
        carriers: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        shipment_ids = make_id_list("shipment_id", 1, shipment_count)
        si_ids = make_id_list("si_id", 1, item_count)
        line_counts = distribute_counts(item_count, shipment_count, minimum=1, rng=self.rng)
        carrier_rows = carriers.set_index("carrier_id")
        warehouse_country = warehouses.set_index("warehouse_id")["country"].to_dict()
        product_cost = products.set_index("product_id")["unit_cost"].to_dict()
        product_weight = products.set_index("product_id")["weight_kg"].to_dict()
        product_ids = products["product_id"].to_numpy()
        shipment_records: list[dict[str, object]] = []
        item_records: list[dict[str, object]] = []
        item_pointer = 0
        carrier_ids = carriers["carrier_id"].to_numpy()
        warehouse_ids = warehouses["warehouse_id"].to_numpy()
        for idx, shipment_id in enumerate(shipment_ids):
            carrier_id = str(self.rng.choice(carrier_ids))
            carrier_transport = str(carrier_rows.loc[carrier_id, "transport"])
            origin_wh = str(self.rng.choice(warehouse_ids))
            origin_country = warehouse_country[origin_wh]
            dest_country = str(weighted_choice(COUNTRY_NAMES, COUNTRY_WEIGHTS, 1, self.rng)[0])
            shipped_at = datetime_range_samples(_SIM_START, _AS_OF - timedelta(days=1), 1, self.rng)[0]
            transit_days = {"air": int(self.rng.integers(1, 5)), "courier": int(self.rng.integers(1, 4)), "road": int(self.rng.integers(2, 12)), "rail": int(self.rng.integers(5, 18)), "sea": int(self.rng.integers(12, 45))}[carrier_transport]
            estimated_at = shipped_at + timedelta(days=transit_days)
            status = str(weighted_choice(_SHIP_STATUS, _SHIP_W, 1, self.rng)[0])
            delivered_at = None
            if status == "delivered":
                delivered_at = estimated_at + timedelta(days=int(self.rng.integers(0, 4)))
            elif status == "out_for_delivery":
                delivered_at = None
            total_weight = 0.0
            line_value_sum = 0.0
            line_count = int(line_counts[idx])
            chosen_products = self.rng.choice(product_ids, size=line_count, replace=line_count > len(product_ids))
            for _ in range(line_count):
                product_id = str(chosen_products[_])
                qty = int(self.rng.integers(1, 501))
                unit_cost = round(float(product_cost[product_id]), 2)
                line_value = round(qty * unit_cost, 2)
                total_weight += float(product_weight[product_id]) * qty
                line_value_sum += line_value
                item_records.append(
                    {
                        "si_id": si_ids[item_pointer],
                        "shipment_id": shipment_id,
                        "product_id": product_id,
                        "qty": qty,
                        "unit_cost": unit_cost,
                        "line_value": line_value,
                    }
                )
                item_pointer += 1
            distance_factor = 1.0 if dest_country == origin_country else 1.35
            mode_factor = {"road": 1.0, "air": 2.4, "sea": 0.7, "rail": 0.9, "courier": 1.6}[carrier_transport]
            freight_cost = round(max(20.0, 8.0 + total_weight * 0.12 * mode_factor * distance_factor + line_value_sum * 0.002), 2)
            shipment_records.append(
                {
                    "shipment_id": shipment_id,
                    "carrier_id": carrier_id,
                    "origin_wh": origin_wh,
                    "dest_country": dest_country,
                    "status": status,
                    "transport_mode": carrier_transport,
                    "incoterm": str(weighted_choice(_INCOTERMS, [0.18, 0.20, 0.18, 0.24, 0.20], 1, self.rng)[0]),
                    "shipped_at": shipped_at,
                    "estimated_at": estimated_at,
                    "delivered_at": delivered_at,
                    "freight_cost": freight_cost,
                }
            )
        return pd.DataFrame(shipment_records), pd.DataFrame(item_records)
