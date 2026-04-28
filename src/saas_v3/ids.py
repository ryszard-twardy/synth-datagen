"""
Deterministic production-style identifiers for SaaS v3.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class IdSpec:
    column_name: str
    prefix: str
    width: int = 10

    @property
    def pattern(self) -> str:
        return rf"^{self.prefix}_\d{{{self.width}}}$"

    def format(self, value: int) -> str:
        return f"{self.prefix}_{value:0{self.width}d}"


ID_SPECS: dict[str, IdSpec] = {
    "account_id": IdSpec("account_id", "acct"),
    "user_id": IdSpec("user_id", "usr"),
    "subscription_id": IdSpec("subscription_id", "sub"),
    "event_id": IdSpec("event_id", "evt"),
    "invoice_id": IdSpec("invoice_id", "inv"),
    "ticket_id": IdSpec("ticket_id", "tkt"),
    "response_id": IdSpec("response_id", "nps"),
}


class IdFactory:
    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)

    def next_id(self, column_name: str) -> str:
        spec = ID_SPECS[column_name]
        self._counters[column_name] += 1
        return spec.format(self._counters[column_name])

    def next_ids(self, column_name: str, size: int) -> list[str]:
        return [self.next_id(column_name) for _ in range(size)]


def pattern_for(column_name: str) -> str:
    return ID_SPECS[column_name].pattern


def is_valid_id(value: str, column_name: str) -> bool:
    return bool(re.fullmatch(pattern_for(column_name), str(value)))


def orphan_id(column_name: str, sequence: int) -> str:
    spec = ID_SPECS[column_name]
    return spec.format(9_000_000_000 + sequence)
