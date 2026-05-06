from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from synth_datagen.kupferkanne_rfm import build_month_plans
from synth_datagen.kupferkanne_rfm_config import (
    KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS,
    load_kupferkanne_rfm_config,
)


def test_kupferkanne_v3_config_loads_full_catalog_and_sections() -> None:
    config = load_kupferkanne_rfm_config(Path("configs/kupferkanne_rfm_v3.yaml"))

    assert config.company.name == "Kupferkanne"
    assert len(config.catalog.products) == 60
    assert len(config.archetypes) == 8
    assert config.output.orders_prefix == "orders20"
    assert config.output.items_prefix == "items20"
    assert config.output.dimensions_dirname == "dimensions"
    assert config.output.monthly_dirname == "monthly"
    assert str(config.output.default_dir).replace("\\", "/") == "output"
    assert config.output.dim_customers_filename == "dim_customers.csv"
    assert config.output.dim_products_filename == "dim_products.csv"
    assert (
        config.output.dim_customers_extra_columns
        == KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS
    )
    assert abs(sum(item.share for item in config.countries) - 1.0) < 1e-9
    country_lookup = {item.code: item.share for item in config.countries}
    assert country_lookup["DE"] > country_lookup["AT"] > country_lookup["CH"]
    assert country_lookup["DE"] > 0.5
    assert country_lookup["AT"] >= 0.12
    assert config.data_quality.target_dirty_rate() > 0.008


def test_kupferkanne_v3_month_plans_cover_39_months_and_target_orders() -> None:
    config = load_kupferkanne_rfm_config(Path("configs/kupferkanne_rfm_v3.yaml"))
    plans = build_month_plans(config, np.random.default_rng(42))

    assert len(plans) == 39
    assert plans[0].label == "2023-01"
    assert plans[-1].label == "2026-03"
    assert (
        sum(plan.order_target for plan in plans)
        == config.validation_targets.target_total_orders
    )


def test_kupferkanne_v3_config_allows_subset_and_empty_customer_extra_columns(
    tmp_path,
) -> None:
    base = yaml.safe_load(
        Path("configs/kupferkanne_rfm_v3.yaml").read_text(encoding="utf-8")
    )
    subset_config = tmp_path / "kupferkanne_subset.yaml"
    base["output"]["dim_customers_extra_columns"] = ["first_name", "email", "city"]
    subset_config.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")

    loaded_subset = load_kupferkanne_rfm_config(subset_config)
    assert loaded_subset.output.dim_customers_extra_columns == [
        "first_name",
        "email",
        "city",
    ]

    empty_config = tmp_path / "kupferkanne_empty.yaml"
    base["output"]["dim_customers_extra_columns"] = []
    empty_config.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")

    loaded_empty = load_kupferkanne_rfm_config(empty_config)
    assert loaded_empty.output.dim_customers_extra_columns == []


def test_kupferkanne_v3_config_rejects_invalid_customer_extra_columns(tmp_path) -> None:
    base = yaml.safe_load(
        Path("configs/kupferkanne_rfm_v3.yaml").read_text(encoding="utf-8")
    )
    invalid_config = tmp_path / "kupferkanne_invalid.yaml"
    base["output"]["dim_customers_extra_columns"] = [
        "first_name",
        "email",
        "email",
        "postcode",
    ]
    invalid_config.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError):
        load_kupferkanne_rfm_config(invalid_config)
