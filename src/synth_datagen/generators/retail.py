"""
Retail / e-commerce scenario generator.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np
import pandas as pd
from faker import Faker

from ..config import GeneratorConfig, RelationConfig, TableConfig
from ..schema_builder import SchemaGraph
from .base import BaseScenarioGenerator
from .retail_builder import RetailDataBuilder, build_retail_schema


class RetailGenerator(BaseScenarioGenerator):
    def __init__(self, config: GeneratorConfig, rng: np.random.Generator, faker: Faker) -> None:
        super().__init__(config, rng, faker)
        self._cache: dict[str, pd.DataFrame] | None = None

    def get_raw_schema(self) -> tuple[list[TableConfig], list[RelationConfig]]:
        return build_retail_schema(self.config)

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
            builder = RetailDataBuilder(self.config, self.rng, self.faker)
            self._cache = builder.build_all_tables(graph)
