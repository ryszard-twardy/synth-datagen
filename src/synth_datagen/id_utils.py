"""
Identifier helpers for production-style business keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Iterable

import numpy as np


ID_WIDTH = 8
DATE_KEY_PATTERN = r"^\d{8}$"


@dataclass(frozen=True)
class IdSpec:
    column_name: str
    prefix: str
    width: int = ID_WIDTH

    @property
    def pattern(self) -> str:
        return rf"^{self.prefix}\d{{{self.width}}}$"

    @property
    def max_length(self) -> int:
        return len(self.prefix) + self.width

    def format(self, value: int) -> str:
        return f"{self.prefix}{value:0{self.width}d}"


_ID_SPECS: dict[str, IdSpec] = {
    "customer_id": IdSpec("customer_id", "CU"),
    "order_id": IdSpec("order_id", "OR"),
    "product_id": IdSpec("product_id", "PR"),
    "store_id": IdSpec("store_id", "ST"),
    "promo_id": IdSpec("promo_id", "PM"),
    "item_id": IdSpec("item_id", "IT"),
    "payment_id": IdSpec("payment_id", "PY"),
    "bridge_id": IdSpec("bridge_id", "BR"),
    "account_id": IdSpec("account_id", "AC"),
    "user_id": IdSpec("user_id", "US"),
    "sub_id": IdSpec("sub_id", "SB"),
    "invoice_id": IdSpec("invoice_id", "IV"),
    "feature_id": IdSpec("feature_id", "FT"),
    "usage_id": IdSpec("usage_id", "UG"),
    "event_id": IdSpec("event_id", "EV"),
    "transaction_id": IdSpec("transaction_id", "TX"),
    "merchant_id": IdSpec("merchant_id", "MR"),
    "card_id": IdSpec("card_id", "CD"),
    "loan_id": IdSpec("loan_id", "LN"),
    "lp_id": IdSpec("lp_id", "LP"),
    "warehouse_id": IdSpec("warehouse_id", "WH"),
    "supplier_id": IdSpec("supplier_id", "SP"),
    "inv_id": IdSpec("inv_id", "IN"),
    "carrier_id": IdSpec("carrier_id", "CR"),
    "shipment_id": IdSpec("shipment_id", "SH"),
    "si_id": IdSpec("si_id", "SI"),
}


def is_date_key_column(column_name: str) -> bool:
    return column_name == "date_id"


def get_id_spec(column_name: str) -> IdSpec | None:
    return _ID_SPECS.get(column_name)


def is_identifier_column(column_name: str) -> bool:
    return column_name in _ID_SPECS


def id_pattern_for(column_name: str) -> str | None:
    spec = get_id_spec(column_name)
    if spec:
        return spec.pattern
    if is_date_key_column(column_name):
        return DATE_KEY_PATTERN
    return None


def id_length_for(column_name: str) -> int | None:
    spec = get_id_spec(column_name)
    if spec:
        return spec.max_length
    if is_date_key_column(column_name):
        return 8
    return None


def make_ids(column_name: str, start: int, size: int) -> np.ndarray:
    spec = get_id_spec(column_name)
    if spec is None:
        raise KeyError(f"No ID spec registered for column '{column_name}'")
    return np.array([spec.format(start + idx) for idx in range(size)], dtype=object)


def make_id_list(column_name: str, start: int, size: int) -> list[str]:
    return make_ids(column_name, start, size).tolist()


def numeric_suffix(value: str, column_name: str) -> int:
    spec = get_id_spec(column_name)
    if spec is None:
        raise KeyError(f"No ID spec registered for column '{column_name}'")
    if not isinstance(value, str) or not re.fullmatch(spec.pattern, value):
        raise ValueError(f"Value '{value}' does not match ID format for {column_name}")
    return int(value[len(spec.prefix):])


def next_ids(column_name: str, existing_values: Iterable[object], count: int) -> list[str]:
    if count <= 0:
        return []
    spec = get_id_spec(column_name)
    if spec is None:
        raise KeyError(f"No ID spec registered for column '{column_name}'")
    max_seen = 0
    for value in existing_values:
        if value is None:
            continue
        if isinstance(value, str) and re.fullmatch(spec.pattern, value):
            max_seen = max(max_seen, int(value[len(spec.prefix):]))
    return [spec.format(max_seen + idx + 1) for idx in range(count)]


def max_numeric_suffix(column_name: str, existing_values: Iterable[object]) -> int:
    spec = get_id_spec(column_name)
    if spec is None:
        raise KeyError(f"No ID spec registered for column '{column_name}'")
    max_seen = 0
    for value in existing_values:
        if value is None:
            continue
        if isinstance(value, str) and re.fullmatch(spec.pattern, value):
            max_seen = max(max_seen, int(value[len(spec.prefix):]))
    return max_seen


def next_start(column_name: str, existing_values: Iterable[object]) -> int:
    return max_numeric_suffix(column_name, existing_values) + 1


def date_to_key(value: date) -> int:
    return int(value.strftime("%Y%m%d"))
