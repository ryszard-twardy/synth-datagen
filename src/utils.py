"""
Utility helpers: seeding, distributions, date helpers, and safe data-quality injection.
"""

from __future__ import annotations

import random
import string
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
import math
import uuid

import numpy as np
import pandas as pd
from faker import Faker

from .config import ColumnConfig, DataQualityConfig, SemanticType, TableConfig
from .id_utils import is_identifier_column, next_ids


def seed_everything(seed: int) -> tuple[random.Random, np.random.Generator, Faker]:
    rng_stdlib = random.Random(seed)
    rng_numpy = np.random.default_rng(seed)
    faker = Faker()
    Faker.seed(seed)
    return rng_stdlib, rng_numpy, faker


def bounded_lognormal(
    mu: float,
    sigma: float,
    lo: float,
    hi: float,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    return np.clip(rng.lognormal(mean=mu, sigma=sigma, size=size), lo, hi)


def weighted_choice(
    options: list,
    weights: list[float] | None,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if not options:
        return np.array([], dtype=object)
    if weights is None:
        return np.array(options, dtype=object)[rng.integers(0, len(options), size=size)]
    probs = np.array(weights, dtype=float)
    probs = probs / probs.sum()
    return np.array(options, dtype=object)[rng.choice(len(options), size=size, p=probs)]


def date_range_samples(
    start: date,
    end: date,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    delta_days = (end - start).days
    offsets = rng.integers(0, delta_days + 1, size=size)
    return np.array([start + timedelta(days=int(offset)) for offset in offsets], dtype=object)


def datetime_range_samples(
    start: datetime,
    end: datetime,
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    delta_seconds = int((end - start).total_seconds())
    offsets = rng.integers(0, delta_seconds + 1, size=size)
    return np.array([start + timedelta(seconds=int(offset)) for offset in offsets], dtype=object)


def sequential_ids(start: int, size: int) -> np.ndarray:
    return np.arange(start, start + size, dtype=np.int64)


def fk_sample(pk_pool: np.ndarray, size: int, rng: np.random.Generator) -> np.ndarray:
    if len(pk_pool) == 0:
        raise ValueError("Cannot sample from an empty FK pool")
    indices = rng.integers(0, len(pk_pool), size=size)
    return pk_pool[indices]


def chunk_iterator(total: int, chunk_size: int) -> Iterator[tuple[int, int]]:
    start = 0
    while start < total:
        end = min(start + chunk_size, total)
        yield start, end
        start = end


def distribute_counts(
    total: int,
    bins: int,
    minimum: int = 0,
    rng: np.random.Generator | None = None,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    if bins <= 0:
        raise ValueError("bins must be positive")
    if total < bins * minimum:
        raise ValueError("total is too small for requested minimum allocation")
    result = np.full(bins, minimum, dtype=np.int64)
    remaining = total - result.sum()
    if remaining == 0:
        return result
    if rng is None:
        rng = np.random.default_rng(42)
    if weights is None:
        weights = np.ones(bins, dtype=float)
    probs = np.array(weights, dtype=float)
    probs = probs / probs.sum()
    picks = rng.choice(bins, size=remaining, p=probs)
    for idx in picks:
        result[int(idx)] += 1
    return result


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(
        value.day,
        [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30,
         31, 31, 30, 31, 30, 31][month - 1],
    )
    return value.replace(year=year, month=month, day=day)


def month_starts_between(start: datetime, end: datetime, step_months: int) -> list[datetime]:
    values: list[datetime] = []
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while current <= end:
        values.append(current)
        current = add_months(current, step_months)
    return values


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, label))


def protected_columns_for_table(table: TableConfig) -> set[str]:
    protected = {table.pk_column, *table.fk_columns}
    for column in table.columns:
        if not column.nullable:
            protected.add(column.name)
        if column.semantic_type in {
            SemanticType.IDENTIFIER,
            SemanticType.DATE_KEY,
            SemanticType.STATUS,
            SemanticType.ENUM,
            SemanticType.SKU,
            SemanticType.REFERENCE,
            SemanticType.SESSION,
            SemanticType.IP_ADDRESS,
        }:
            protected.add(column.name)
        if column.name in {"full_date", "created_at", "shipped_at", "delivered_at", "paid_at",
                           "started_at", "ended_at", "issued_at", "due_at", "occurred_at",
                           "opened_at", "closed_at", "last_updated", "last_login",
                           "issue_date", "expiry_date", "dob", "valid_from", "valid_to",
                           "estimated_at", "disbursed_at"}:
            protected.add(column.name)
    return protected


def _is_string_like(series: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)


def inject_nulls(
    df: pd.DataFrame,
    null_rate: float,
    protected_cols: set[str],
    rng: np.random.Generator,
) -> pd.DataFrame:
    if null_rate == 0.0:
        return df
    for column in df.columns:
        if column in protected_cols:
            continue
        if df[column].dtype == bool or str(df[column].dtype) in {"bool", "boolean"}:
            continue
        mask = rng.random(size=len(df)) < null_rate
        if mask.any():
            df.loc[mask, column] = np.nan
    return df


def _next_numeric_values(existing_values: Iterable[object], count: int) -> list[int]:
    max_seen = 0
    for value in existing_values:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        if isinstance(value, (int, np.integer)):
            max_seen = max(max_seen, int(value))
    return list(range(max_seen + 1, max_seen + count + 1))


def _generate_unique_semantic_value(
    column: ColumnConfig,
    seed_value: object,
    sequence: int,
    existing_values: set[object],
) -> str:
    seed_text = "" if seed_value is None else str(seed_value)
    while True:
        if column.semantic_type == SemanticType.EMAIL:
            local, _, domain = seed_text.partition("@")
            local = local or "user"
            domain = domain or "example.com"
            candidate = f"{local}.dup{sequence}@{domain}"
        elif column.semantic_type == SemanticType.DOMAIN:
            candidate = f"dup-{sequence}.example.com"
        elif column.semantic_type == SemanticType.SKU:
            prefix = "".join(ch for ch in seed_text if ch.isalpha() or ch == "-") or "SKU-"
            candidate = f"{prefix}{sequence:08d}"
        elif column.semantic_type == SemanticType.REFERENCE:
            base = seed_text.split("-", 1)[0] if seed_text else "REF"
            candidate = f"{base}-{sequence:012X}"
        else:
            candidate = f"{seed_text}-dup-{sequence}"
        if candidate not in existing_values:
            return candidate
        sequence += 1


def inject_duplicates(
    df: pd.DataFrame,
    table: TableConfig,
    dupe_rate: float,
    rng: np.random.Generator,
    unique_state: dict[str, set[object]],
) -> pd.DataFrame:
    if dupe_rate == 0.0 or not table.allow_duplicate_injection or len(df) == 0:
        return df

    unique_columns = [col for col in table.columns if col.unique]
    if any(col.name != table.pk_column and col.name in table.fk_columns for col in unique_columns):
        return df

    n_dupes = max(1, int(len(df) * dupe_rate))
    picked_rows = df.iloc[rng.integers(0, len(df), size=n_dupes)].copy().reset_index(drop=True)

    pk_column = table.pk_column
    if is_identifier_column(pk_column):
        new_values = next_ids(pk_column, unique_state.setdefault(pk_column, set()), n_dupes)
    else:
        new_values = _next_numeric_values(unique_state.setdefault(pk_column, set()), n_dupes)
    picked_rows[pk_column] = new_values
    unique_state[pk_column].update(new_values)

    for column in unique_columns:
        if column.name == pk_column or column.name not in picked_rows.columns:
            continue
        if column.name in table.fk_columns:
            return df
        if not _is_string_like(picked_rows[column.name]):
            return df
        state = unique_state.setdefault(column.name, set())
        replacements: list[str] = []
        for index, value in enumerate(picked_rows[column.name].tolist(), start=1):
            replacement = _generate_unique_semantic_value(column, value, len(state) + index, state)
            state.add(replacement)
            replacements.append(replacement)
        picked_rows[column.name] = replacements

    return pd.concat([df, picked_rows], ignore_index=True)


def inject_outliers(
    df: pd.DataFrame,
    outlier_rate: float,
    rng: np.random.Generator,
    protected_cols: set[str],
) -> pd.DataFrame:
    if outlier_rate == 0.0:
        return df
    numeric_columns = [
        col for col in df.select_dtypes(include=[np.number]).columns if col not in protected_cols
    ]
    for column in numeric_columns:
        original_dtype = df[column].dtype
        is_integer = pd.api.types.is_integer_dtype(original_dtype)
        mask = rng.random(size=len(df)) < outlier_rate
        if not mask.any():
            continue
        factor = rng.uniform(10, 25, size=mask.sum())
        new_values = df.loc[mask, column].to_numpy(dtype=np.float64) * factor
        if is_integer:
            new_values = np.round(new_values).astype(original_dtype)
        df.loc[mask, column] = new_values
    return df


def inject_typos(
    df: pd.DataFrame,
    typo_rate: float,
    rng: np.random.Generator,
    protected_cols: set[str],
) -> pd.DataFrame:
    if typo_rate == 0.0:
        return df
    for column in df.columns:
        if column in protected_cols or not _is_string_like(df[column]):
            continue
        mask = rng.random(size=len(df)) < typo_rate
        for idx in np.where(mask)[0]:
            value = df.at[idx, column]
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            text = str(value)
            if len(text) < 4:
                continue
            position = int(rng.integers(1, len(text) - 1))
            replacement = str(rng.choice(list(string.ascii_lowercase)))
            df.at[idx, column] = text[:position] + replacement + text[position + 1:]
    return df


def apply_data_quality(
    df: pd.DataFrame,
    table: TableConfig | None = None,
    dq_config: DataQualityConfig | None = None,
    rng: np.random.Generator | None = None,
    unique_state: dict[str, set[object]] | None = None,
    *,
    protected_cols: list[str] | set[str] | None = None,
    pk_column: str | None = None,
    unique_cols: list[str] | None = None,
) -> pd.DataFrame:
    if dq_config is None or rng is None:
        raise ValueError("dq_config and rng are required")

    dirty = df.copy(deep=True)
    if table is not None:
        protected = protected_columns_for_table(table)
        state = unique_state or {}
        dirty = inject_nulls(dirty, dq_config.null_rate, protected, rng)
        dirty = inject_duplicates(dirty, table, dq_config.dupe_rate, rng, state)
        dirty = inject_outliers(dirty, dq_config.outlier_rate, rng, protected)
        dirty = inject_typos(dirty, dq_config.typo_rate, rng, protected)
        return dirty

    protected = set(protected_cols or [])
    dirty = inject_nulls(dirty, dq_config.null_rate, protected, rng)
    dirty = inject_outliers(dirty, dq_config.outlier_rate, rng, protected)
    dirty = inject_typos(dirty, dq_config.typo_rate, rng, protected)
    return dirty


COUNTRIES_WEIGHTED: list[tuple[str, str, float]] = [
    ("United States", "USD", 0.35),
    ("Germany", "EUR", 0.12),
    ("United Kingdom", "GBP", 0.10),
    ("France", "EUR", 0.08),
    ("Canada", "CAD", 0.07),
    ("Australia", "AUD", 0.06),
    ("Netherlands", "EUR", 0.04),
    ("Poland", "PLN", 0.04),
    ("Spain", "EUR", 0.04),
    ("Italy", "EUR", 0.04),
    ("Brazil", "BRL", 0.03),
    ("Japan", "JPY", 0.03),
]

COUNTRY_NAMES = [country for country, _, _ in COUNTRIES_WEIGHTED]
COUNTRY_CURRENCIES = {country: currency for country, currency, _ in COUNTRIES_WEIGHTED}
COUNTRY_WEIGHTS = [weight for _, _, weight in COUNTRIES_WEIGHTED]
