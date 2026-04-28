"""
Abstract base class for all scenario generators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

import numpy as np
import pandas as pd
from faker import Faker

from ..config import GeneratorConfig, RelationConfig, TableConfig
from ..schema_builder import SchemaGraph


class BaseScenarioGenerator(ABC):
    """
    Every scenario generator must implement:
      - get_raw_schema() -> (tables, relations)   [pure definitions, no data]
      - generate_table(...)                        [chunked data production]
    """

    def __init__(self, config: GeneratorConfig, rng: np.random.Generator, faker: Faker) -> None:
        self.config = config
        self.rng = rng
        self.faker = faker

    @abstractmethod
    def get_raw_schema(self) -> tuple[list[TableConfig], list[RelationConfig]]:
        """Return un-wired table and relation definitions for this scenario."""
        ...

    @abstractmethod
    def generate_table(
        self,
        table: TableConfig,
        graph: SchemaGraph,
        fk_pools: dict[str, np.ndarray],
    ) -> Iterator[pd.DataFrame]:
        """
        Yield DataFrame chunks for `table`.

        Args:
            table:    TableConfig for the table being generated.
            graph:    Fully-built SchemaGraph (all tables + relations).
            fk_pools: Maps "table_name.column_name" -> numpy array of existing PK values.
                      Used to sample valid FK references.

        Yields:
            pd.DataFrame chunks of at most config.chunk_size rows each.
        """
        ...

    def _chunk_ranges(self, total: int) -> Iterator[tuple[int, int]]:
        """Yield (start, end) index pairs for chunked generation."""
        chunk = self.config.chunk_size
        start = 0
        while start < total:
            end = min(start + chunk, total)
            yield start, end
            start = end

    def _fk_pool_key(self, table_name: str, column_name: str) -> str:
        return f"{table_name}.{column_name}"

    def _yield_cached_table(self, df: pd.DataFrame) -> Iterator[pd.DataFrame]:
        if len(df) == 0:
            yield df.copy()
            return
        for start, end in self._chunk_ranges(len(df)):
            yield df.iloc[start:end].reset_index(drop=True)
