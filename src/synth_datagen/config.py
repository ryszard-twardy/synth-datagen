"""
Configuration models for the synthetic data generator.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .id_utils import id_length_for, id_pattern_for, is_date_key_column, is_identifier_column


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scenario(str, Enum):
    RETAIL = "retail"
    SAAS = "saas"
    FINTECH = "fintech"
    LOGISTICS = "logistics"


class SchemaType(str, Enum):
    STAR = "star"


class Dialect(str, Enum):
    POSTGRES = "postgres"
    SQLITE = "sqlite"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"


class DataQuality(str, Enum):
    NONE = "none"
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class Cardinality(str, Enum):
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:M"
    SELF = "self"


class DType(str, Enum):
    INT = "int"
    BIGINT = "bigint"
    FLOAT = "float"
    DECIMAL = "decimal"
    VARCHAR = "varchar"
    TEXT = "text"
    DATE = "date"
    TIMESTAMP = "timestamp"
    BOOLEAN = "boolean"
    UUID = "uuid"


class SemanticType(str, Enum):
    IDENTIFIER = "identifier"
    DATE_KEY = "date_key"
    EMAIL = "email"
    DOMAIN = "domain"
    SKU = "sku"
    REFERENCE = "reference"
    STATUS = "status"
    ENUM = "enum"
    SESSION = "session"
    IP_ADDRESS = "ip_address"


class ColumnConfig(StrictModel):
    name: str
    dtype: DType
    nullable: bool = False
    unique: bool = False
    faker_provider: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    pattern: str | None = None
    max_length: int | None = None
    semantic_type: SemanticType | None = None

    @model_validator(mode="after")
    def enrich_identifier_metadata(self) -> "ColumnConfig":
        if is_identifier_column(self.name):
            self.pattern = self.pattern or id_pattern_for(self.name)
            self.max_length = self.max_length or id_length_for(self.name)
            self.semantic_type = self.semantic_type or SemanticType.IDENTIFIER
            if self.dtype != DType.VARCHAR:
                self.dtype = DType.VARCHAR
        elif is_date_key_column(self.name):
            self.pattern = self.pattern or id_pattern_for(self.name)
            self.max_length = self.max_length or id_length_for(self.name)
            self.semantic_type = self.semantic_type or SemanticType.DATE_KEY
            if self.dtype != DType.INT:
                self.dtype = DType.INT
        elif self.name == "email":
            self.semantic_type = self.semantic_type or SemanticType.EMAIL
            self.max_length = self.max_length or 255
        elif self.name == "domain":
            self.semantic_type = self.semantic_type or SemanticType.DOMAIN
            self.max_length = self.max_length or 255
        elif self.name == "sku":
            self.semantic_type = self.semantic_type or SemanticType.SKU
            self.max_length = self.max_length or 32
        elif self.name in {"gateway_ref"} or self.name.endswith("_ref"):
            self.semantic_type = self.semantic_type or SemanticType.REFERENCE
            self.max_length = self.max_length or 64
        elif "status" in self.name:
            self.semantic_type = self.semantic_type or SemanticType.STATUS
            self.max_length = self.max_length or 32
        elif self.name in {
            "currency", "country", "channel", "role", "network", "account_type",
            "loan_type", "tx_type", "transport", "transport_mode", "incoterm",
            "discount_type", "store_type", "segment", "plan", "plan_min",
            "billing_cycle", "category", "subcategory", "event_type", "method",
            "kyc_status",
        }:
            self.semantic_type = self.semantic_type or SemanticType.ENUM
            if self.dtype == DType.VARCHAR and self.max_length is None:
                self.max_length = 64
        elif self.name == "session_id":
            self.semantic_type = self.semantic_type or SemanticType.SESSION
            self.max_length = self.max_length or 36
        elif self.name == "ip_address":
            self.semantic_type = self.semantic_type or SemanticType.IP_ADDRESS
            self.max_length = self.max_length or 45
        return self


class RelationConfig(StrictModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    cardinality: Cardinality = Cardinality.ONE_TO_MANY
    junction_table: str | None = None


class TableConfig(StrictModel):
    name: str
    row_count: int = Field(gt=0)
    columns: list[ColumnConfig]
    pk_column: str = "id"
    fk_columns: list[str] = Field(default_factory=list)
    scenario_tag: str | None = None
    allow_duplicate_injection: bool = True


_QUALITY_PRESETS: dict[DataQuality, dict[str, float]] = {
    DataQuality.NONE: {"null_rate": 0.0, "dupe_rate": 0.0, "outlier_rate": 0.0, "typo_rate": 0.0},
    DataQuality.LIGHT: {"null_rate": 0.02, "dupe_rate": 0.005, "outlier_rate": 0.01, "typo_rate": 0.01},
    DataQuality.MEDIUM: {"null_rate": 0.05, "dupe_rate": 0.015, "outlier_rate": 0.03, "typo_rate": 0.03},
    DataQuality.HEAVY: {"null_rate": 0.12, "dupe_rate": 0.04, "outlier_rate": 0.07, "typo_rate": 0.06},
}


class DataQualityConfig(StrictModel):
    level: DataQuality = DataQuality.NONE
    null_rate: float = 0.0
    dupe_rate: float = 0.0
    outlier_rate: float = 0.0
    typo_rate: float = 0.0

    @model_validator(mode="after")
    def apply_preset(self) -> "DataQualityConfig":
        preset = _QUALITY_PRESETS[self.level]
        for key, val in preset.items():
            if getattr(self, key) == 0.0:
                setattr(self, key, val)
        return self


_DEFAULT_ROW_COUNTS: dict[Scenario, dict[str, int]] = {
    Scenario.RETAIL: {
        "dim_customers": 20_000,
        "dim_products": 5_000,
        "dim_stores": 200,
        "dim_date": 1_461,
        "dim_promotions": 150,
        "fact_orders": 80_000,
        "fact_order_items": 200_000,
        "fact_payments": 80_000,
        "bridge_order_promotions": 30_000,
    },
    Scenario.SAAS: {
        "accounts": 5_000,
        "users": 25_000,
        "subscriptions": 6_000,
        "invoices": 20_000,
        "features": 50,
        "feature_usage": 150_000,
        "events": 500_000,
    },
    Scenario.FINTECH: {
        "customers": 10_000,
        "accounts": 15_000,
        "merchants": 2_000,
        "transactions": 200_000,
        "cards": 12_000,
        "loans": 3_000,
        "loan_payments": 30_000,
    },
    Scenario.LOGISTICS: {
        "warehouses": 100,
        "suppliers": 500,
        "products": 3_000,
        "inventory": 10_000,
        "carriers": 50,
        "shipments": 50_000,
        "shipment_items": 120_000,
    },
}


class GeneratorConfig(StrictModel):
    scenario: Scenario = Scenario.RETAIL
    schema_type: SchemaType = SchemaType.STAR
    dialect: Dialect = Dialect.POSTGRES
    seed: int = 42
    discount_seed: int | None = None
    discount_variation: bool = True
    output_dir: Path = Path("./out")
    simulation_start: date | None = None
    simulation_end: date | None = None
    chunk_size: int = Field(default=50_000, gt=0)
    row_overrides: dict[str, int] = Field(default_factory=dict)
    cols_min: int = Field(default=8, ge=1)
    cols_max: int = Field(default=25, ge=1)
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    export_sqlite: bool = False
    export_parquet: bool = False
    export_dml: bool = False

    @field_validator("output_dir", mode="before")
    @classmethod
    def coerce_path(cls, value: Any) -> Path:
        return Path(value)

    @model_validator(mode="after")
    def validate_supported_options(self) -> "GeneratorConfig":
        if self.cols_min > self.cols_max:
            raise ValueError(f"cols_min ({self.cols_min}) must be <= cols_max ({self.cols_max})")
        if self.simulation_start and self.simulation_end and self.simulation_start > self.simulation_end:
            raise ValueError("simulation_start must be <= simulation_end")
        defaults = _DEFAULT_ROW_COUNTS[self.scenario]
        resolved = {name: self.row_overrides.get(name, default) for name, default in defaults.items()}
        if self.scenario is Scenario.RETAIL:
            if resolved["fact_payments"] != resolved["fact_orders"]:
                raise ValueError("Retail requires fact_payments to equal fact_orders.")
            if resolved["fact_order_items"] < resolved["fact_orders"]:
                raise ValueError("Retail requires fact_order_items to be >= fact_orders.")
        if self.scenario is Scenario.LOGISTICS:
            if resolved["inventory"] > resolved["warehouses"] * resolved["products"]:
                raise ValueError("Logistics inventory cannot exceed warehouses * products.")
        return self
