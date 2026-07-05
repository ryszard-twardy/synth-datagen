"""
Dedicated Kupferkanne RFM generator for the current line-item export contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
import json
from pathlib import Path
import unicodedata

from faker import Faker
import numpy as np
import pandas as pd

from .discounts import build_discount_rng, sample_discount, sample_discount_propensity
from .rng import make_rng
from .kupferkanne_rfm_config import (
    KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS,
    KupferkanneArchetypeConfig,
    KupferkanneRfmConfig,
    write_effective_kupferkanne_config,
)


ORDERS_COLUMNS = [
    "OrderID",
    "CustomerID",
    "OrderDate",
    "OrderDiscountPct",
    "BasketItemCount",
]
ITEMS_COLUMNS = [
    "OrderID",
    "LineNumber",
    "ProductID",
    "Quantity",
    "UnitPrice",
    "LineNetAmount",
]

DIM_CUSTOMERS_EXPORT_LABELS = {
    "CustomerID": "CustomerID",
    "signup_date": "SignupDate",
    "customer_archetype": "CustomerArchetype",
    "first_name": "FirstName",
    "last_name": "LastName",
    "email": "Email",
    "phone": "Phone",
    "Country": "Country",
    "state": "State",
    "city": "City",
    "address": "Address",
}
DIM_CUSTOMERS_EXPORT_COLUMNS = [
    "CustomerID",
    "SignupDate",
    "CustomerArchetype",
    "FirstName",
    "LastName",
    "Email",
    "Phone",
    "Country",
    "State",
    "City",
    "Address",
]
DIM_PRODUCTS_EXPORT_COLUMNS = [
    "ProductID",
    "ProductName",
    "ProductCategory",
    "Brand",
    "RetailPrice",
    "UnitCost",
    "MarginPct",
]

INTERNAL_LINE_COLUMNS = [
    "OrderLineNumber",
    "OrderID",
    "CustomerID",
    "OrderDate",
    "Country",
    "ProductID",
    "ProductCategory",
    "ProductName",
    "Quantity",
    "UnitPrice",
    "UnitCost",
    "LineDiscountPct",
    "LineNetAmount",
    "OrderDiscountPct",
    "BasketItemCount",
]
_KUPFER_ENABLED_MARGIN_FLOOR = 0.645


@dataclass(frozen=True)
class KupferMonthPlan:
    label: str
    month_start: date
    month_end: date
    active_days: int
    days_in_month: int
    order_target: int
    new_customer_target: int


@dataclass
class CustomerState:
    customer_id: str
    signup_date: date
    country: str
    archetype: str
    discount_propensity: float | None = None
    churn_end_label: str | None = None
    order_count: int = 0
    last_order_date: date | None = None
    monthly_order_counts: dict[str, int] = field(default_factory=dict)


def _month_sequence(start_date: date, end_date: date) -> list[tuple[date, date]]:
    months: list[tuple[date, date]] = []
    cursor = date(start_date.year, start_date.month, 1)
    while cursor <= end_date:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        months.append((cursor, month_end))
        cursor = next_month
    return months


def _month_label(value: date) -> str:
    return value.strftime("%Y-%m")


def _month_filename(prefix: str, value: date) -> str:
    return f"{prefix}{value.strftime('%y%m')}.csv"


def _month_diff(start_date: date, end_date: date) -> int:
    return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)


def _allocate_counts(total: int, weights: list[float]) -> list[int]:
    if total <= 0:
        return [0] * len(weights)
    weight_array = np.array(weights, dtype=float)
    if weight_array.sum() <= 0:
        raise ValueError("weights must sum to a positive value")
    normalized = weight_array / weight_array.sum()
    raw = normalized * total
    counts = np.floor(raw).astype(int)
    remainder = int(total - counts.sum())
    if remainder > 0:
        order = np.argsort(-(raw - counts))
        for idx in order[:remainder]:
            counts[idx] += 1
    return counts.tolist()


def _random_date_in_range(
    rng: np.random.Generator, start_date: date, end_date: date
) -> date:
    if end_date <= start_date:
        return start_date
    offset = int(rng.integers(0, (end_date - start_date).days + 1))
    return start_date + timedelta(days=offset)


def _choose_weighted(
    rng: np.random.Generator, options: list[str], weights: list[float]
) -> str:
    probs = np.array(weights, dtype=float)
    if probs.sum() <= 0:
        probs = np.ones(len(options), dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(np.array(options, dtype=object), p=probs))


def _format_customer_id(value: int) -> str:
    return f"CUST-{value:05d}"


def _format_order_id(year: int, value: int) -> str:
    return f"ORD-{year}-{value:06d}"


def _product_brand(product_id: str) -> str:
    if product_id in {
        "PROD-004",
        "PROD-005",
        "PROD-013",
        "PROD-016",
        "PROD-036",
        "PROD-041",
    }:
        return "Kupferkanne Eigenmarke"
    if product_id in {
        "PROD-001",
        "PROD-002",
        "PROD-003",
        "PROD-006",
        "PROD-007",
        "PROD-012",
        "PROD-020",
        "PROD-021",
        "PROD-025",
        "PROD-027",
        "PROD-028",
        "PROD-029",
    }:
        return "Terroir Select"
    if product_id in {
        "PROD-044",
        "PROD-045",
        "PROD-046",
        "PROD-047",
        "PROD-048",
        "PROD-049",
        "PROD-050",
        "PROD-051",
        "PROD-052",
        "PROD-053",
    }:
        return "Partner Brands"
    if product_id in {
        "PROD-009",
        "PROD-010",
        "PROD-018",
        "PROD-019",
        "PROD-030",
        "PROD-031",
        "PROD-042",
        "PROD-043",
        "PROD-054",
        "PROD-055",
        "PROD-056",
        "PROD-057",
        "PROD-058",
        "PROD-059",
        "PROD-060",
    }:
        return "Kupferkanne Geschenke"
    return "Artisan Direct"


COUNTRY_LOCALES: dict[str, str] = {
    "DE": "de_DE",
    "AT": "de_AT",
    "CH": "de_CH",
    "PL": "pl_PL",
    "NL": "nl_NL",
    "BE": "fr_BE",
    "UK": "en_GB",
    "SE": "sv_SE",
    "DK": "da_DK",
}

COUNTRY_REGIONS: dict[str, list[tuple[str, list[str]]]] = {
    "DE": [
        ("Bavaria", ["Munich", "Nuremberg", "Augsburg"]),
        ("Berlin", ["Berlin"]),
        ("North Rhine-Westphalia", ["Cologne", "Dusseldorf", "Dortmund"]),
    ],
    "AT": [
        ("Vienna", ["Vienna"]),
        ("Upper Austria", ["Linz", "Wels"]),
        ("Salzburg", ["Salzburg"]),
    ],
    "CH": [
        ("Zurich", ["Zurich", "Winterthur"]),
        ("Bern", ["Bern", "Biel/Bienne"]),
        ("Vaud", ["Lausanne", "Montreux"]),
    ],
    "PL": [
        ("Masovian", ["Warsaw", "Radom"]),
        ("Lesser Poland", ["Krakow", "Tarnow"]),
        ("Lower Silesian", ["Wroclaw", "Legnica"]),
    ],
    "NL": [
        ("North Holland", ["Amsterdam", "Haarlem"]),
        ("South Holland", ["Rotterdam", "The Hague"]),
        ("North Brabant", ["Eindhoven", "Breda"]),
    ],
    "BE": [
        ("Flanders", ["Antwerp", "Ghent"]),
        ("Brussels-Capital", ["Brussels"]),
        ("Wallonia", ["Liege", "Namur"]),
    ],
    "UK": [
        ("England", ["London", "Manchester", "Bristol"]),
        ("Scotland", ["Edinburgh", "Glasgow"]),
        ("Wales", ["Cardiff", "Swansea"]),
    ],
    "SE": [
        ("Stockholm County", ["Stockholm", "Sodertalje"]),
        ("Vastra Gotaland", ["Gothenburg", "Borås"]),
        ("Skane", ["Malmo", "Lund"]),
    ],
    "DK": [
        ("Capital Region", ["Copenhagen", "Hillerod"]),
        ("Central Denmark", ["Aarhus", "Randers"]),
        ("Southern Denmark", ["Odense", "Kolding"]),
    ],
}


def _slug_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(
        character.lower() if character.isalnum() else "." for character in ascii_only
    )
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    return cleaned.strip(".") or "customer"


def _discount_tier_for_archetype(archetype_name: str) -> str:
    if archetype_name in {"Coffee Regulars", "Premium Enthusiasts", "Power Buyers"}:
        return "high"
    if archetype_name in {"Gift Buyers", "One-Time Buyers", "New Arrivals"}:
        return "low"
    return "mid"


def _build_country_fakers(rng: np.random.Generator) -> dict[str, Faker]:
    fakers: dict[str, Faker] = {}
    for country_code, locale in COUNTRY_LOCALES.items():
        faker = Faker(locale)
        faker.seed_instance(int(rng.integers(0, 1_000_000_000)))
        fakers[country_code] = faker
    return fakers


def _build_customer_contact_profile(
    customer_id: str,
    country_code: str,
    rng: np.random.Generator,
    faker_by_country: dict[str, Faker],
) -> dict[str, str]:
    faker = faker_by_country[country_code]
    first_name = faker.first_name()
    last_name = faker.last_name()
    state_name, cities = COUNTRY_REGIONS[country_code][
        int(rng.integers(0, len(COUNTRY_REGIONS[country_code])))
    ]
    city = str(rng.choice(np.array(cities, dtype=object)))
    street_name = faker.street_name().replace("\n", " ").strip()
    building_number = faker.building_number().replace("\n", " ").strip()
    address = f"{street_name} {building_number}, {city}"
    customer_number = customer_id.split("-")[-1]
    email = f"{_slug_text(first_name)}.{_slug_text(last_name)}.{customer_number}@{country_code.lower()}.kupferkanne.test"
    phone = faker.phone_number().replace("\n", " ").strip()
    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "state": state_name,
        "city": city,
        "address": address,
    }


def build_month_plans(
    config: KupferkanneRfmConfig, rng: np.random.Generator
) -> list[KupferMonthPlan]:
    months = _month_sequence(config.period.start_date, config.period.end_date)
    raw_targets: list[float] = []
    month_metadata: list[tuple[date, date, int, int]] = []
    for month_start, month_end in months:
        active_start = max(month_start, config.period.start_date)
        active_end = min(month_end, config.period.end_date)
        active_days = (active_end - active_start).days + 1
        days_in_month = month_end.day
        baseline = float(config.seasonality.monthly_order_baseline[month_start.month])
        year_multiplier = float(config.growth.year_multipliers[month_start.year])
        variance = float(
            rng.uniform(
                1.0 - config.seasonality.random_variance_pct,
                1.0 + config.seasonality.random_variance_pct,
            )
        )
        partial_ratio = active_days / days_in_month
        raw_targets.append(baseline * year_multiplier * variance * partial_ratio)
        month_metadata.append((active_start, active_end, active_days, days_in_month))

    scaled_orders = _allocate_counts(
        config.validation_targets.target_total_orders, raw_targets
    )

    phase_weights: dict[str, float] = {}
    for phase in config.customers.acquisition_phases:
        phase_month_start = pd.Period(phase.start_month, freq="M")
        phase_month_end = pd.Period(phase.end_month, freq="M")
        current = phase_month_start
        while current <= phase_month_end:
            phase_weights[str(current)] = float(phase.monthly_new_customers)
            current += 1
    acquisition_weights = [
        phase_weights.get(pd.Period(month_start, freq="M").strftime("%Y-%m"), 0.0)
        for month_start, _ in months
    ]
    scaled_new = _allocate_counts(
        config.customers.target_total_customers
        - config.customers.prelaunch_seed_customers,
        acquisition_weights,
    )
    if scaled_new:
        scaled_new[0] += config.customers.prelaunch_seed_customers

    plans: list[KupferMonthPlan] = []
    for idx, (month_start, _) in enumerate(months):
        active_start, active_end, active_days, days_in_month = month_metadata[idx]
        new_customer_target = min(scaled_new[idx], scaled_orders[idx])
        plans.append(
            KupferMonthPlan(
                label=_month_label(month_start),
                month_start=active_start,
                month_end=active_end,
                active_days=active_days,
                days_in_month=days_in_month,
                order_target=int(scaled_orders[idx]),
                new_customer_target=int(new_customer_target),
            )
        )
    return plans


def build_product_dimension(
    config: KupferkanneRfmConfig, *, discount_variation: bool = True
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for product in config.catalog.products:
        retail_price = float(product.retail_price)
        unit_cost = round(product.unit_cost, 2)
        if discount_variation:
            floor_price = unit_cost / (1.0 - _KUPFER_ENABLED_MARGIN_FLOOR)
            retail_price = max(retail_price, floor_price)
        retail_price = round(retail_price, 2)
        rows.append(
            {
                "ProductID": product.product_id,
                "ProductName": product.product_name,
                "ProductCategory": product.category,
                "Brand": _product_brand(product.product_id),
                "RetailPrice": retail_price,
                "UnitCost": unit_cost,
                "MarginPct": round((retail_price - unit_cost) / retail_price, 4),
                "base_weight": float(product.base_weight),
                "tags": list(product.tags),
            }
        )
    return pd.DataFrame(rows)


def build_customer_population(
    config: KupferkanneRfmConfig,
    plans: list[KupferMonthPlan],
    rng: np.random.Generator,
    discount_rng: np.random.Generator | None = None,
) -> tuple[
    pd.DataFrame,
    dict[str, CustomerState],
    dict[str, list[str]],
    dict[str, KupferkanneArchetypeConfig],
]:
    archetype_lookup = {item.name: item for item in config.archetypes}
    archetype_names = [item.name for item in config.archetypes]
    archetype_counts = _allocate_counts(
        config.customers.target_total_customers,
        [item.share for item in config.archetypes],
    )
    remaining_archetypes = dict(zip(archetype_names, archetype_counts, strict=False))
    country_codes = [item.code for item in config.countries]
    country_weights = [item.share for item in config.countries]

    customer_rows: list[dict[str, object]] = []
    states: dict[str, CustomerState] = {}
    customers_by_month: dict[str, list[str]] = {}
    customer_index = 1
    faker_by_country = _build_country_fakers(rng)

    for month_index, plan in enumerate(plans):
        month_customer_ids: list[str] = []
        for new_customer_index in range(plan.new_customer_target):
            customer_id = _format_customer_id(customer_index)
            customer_index += 1

            available_names = [
                name for name in archetype_names if remaining_archetypes[name] > 0
            ]
            available_weights = [remaining_archetypes[name] for name in available_names]
            archetype_name = _choose_weighted(rng, available_names, available_weights)
            remaining_archetypes[archetype_name] -= 1

            if (
                month_index == 0
                and new_customer_index < config.customers.prelaunch_seed_customers
            ):
                signup_end = min(plan.month_end, plan.month_start + timedelta(days=6))
                signup_date = _random_date_in_range(rng, plan.month_start, signup_end)
            else:
                signup_date = _random_date_in_range(
                    rng, plan.month_start, plan.month_end
                )

            country_code = _choose_weighted(rng, country_codes, country_weights)
            contact_profile = _build_customer_contact_profile(
                customer_id, country_code, rng, faker_by_country
            )
            archetype = archetype_lookup[archetype_name]
            discount_propensity = (
                sample_discount_propensity(
                    _discount_tier_for_archetype(archetype_name), discount_rng
                )
                if discount_rng is not None
                else None
            )
            churn_end_label: str | None = None
            if (
                archetype.churn_after_months_min is not None
                and archetype.churn_after_months_max is not None
            ):
                churn_months = int(
                    rng.integers(
                        archetype.churn_after_months_min,
                        archetype.churn_after_months_max + 1,
                    )
                )
                churn_month_index = min(len(plans) - 1, month_index + churn_months)
                churn_end_label = plans[churn_month_index].label

            customer_rows.append(
                {
                    "CustomerID": customer_id,
                    "signup_date": signup_date.isoformat(),
                    "Country": country_code,
                    "customer_archetype": archetype_name,
                    "churn_end_month": churn_end_label,
                    **contact_profile,
                }
            )
            states[customer_id] = CustomerState(
                customer_id=customer_id,
                signup_date=signup_date,
                country=country_code,
                archetype=archetype_name,
                discount_propensity=discount_propensity,
                churn_end_label=churn_end_label,
            )
            month_customer_ids.append(customer_id)
        customers_by_month[plan.label] = month_customer_ids

    dim_customers = pd.DataFrame(customer_rows)
    return dim_customers, states, customers_by_month, archetype_lookup


def _product_tag_multiplier(
    config: KupferkanneRfmConfig, tags: list[str], month_number: int
) -> float:
    multiplier = 1.0
    for tag in tags:
        multiplier *= float(
            config.seasonality.product_tag_multipliers.get(tag, {}).get(
                month_number, 1.0
            )
        )
    return multiplier


def _customer_month_weight(
    state: CustomerState,
    archetype: KupferkanneArchetypeConfig,
    month_plan: KupferMonthPlan,
) -> float:
    if state.order_count <= 0:
        return 0.0
    if archetype.active_months_after_signup is not None:
        if (
            _month_diff(state.signup_date, month_plan.month_start)
            >= archetype.active_months_after_signup
        ):
            return 0.0
    if state.churn_end_label is not None and month_plan.label > state.churn_end_label:
        return 0.0

    existing_monthly_orders = state.monthly_order_counts.get(month_plan.label, 0)
    if existing_monthly_orders >= archetype.max_orders_per_month:
        return 0.0

    weight = float(archetype.existing_order_weight)
    if existing_monthly_orders > 0:
        weight *= float(archetype.same_month_repeat_weight)
    if month_plan.month_start.month in {11, 12}:
        weight *= float(archetype.holiday_multiplier)
    if month_plan.month_start.month in {1, 2, 3}:
        weight *= float(archetype.q1_multiplier)
    if month_plan.month_start.month in {6, 7, 8}:
        weight *= float(archetype.summer_multiplier)
    if state.last_order_date is not None:
        gap_days = (month_plan.month_start - state.last_order_date).days
        if gap_days < 10 and archetype.name != "Power Buyers":
            weight *= 0.25
        elif 21 <= gap_days <= 60:
            weight *= 1.20
        elif gap_days > 180 and archetype.name in {
            "Coffee Regulars",
            "Occasional Explorers",
            "Premium Enthusiasts",
        }:
            weight *= 0.70
    if archetype.name == "Gift Buyers" and month_plan.month_start.month not in {
        2,
        11,
        12,
    }:
        weight *= 0.12
    if archetype.name == "New Arrivals":
        months_since_signup = _month_diff(state.signup_date, month_plan.month_start)
        weight *= 1.20 if months_since_signup <= 1 else 0.20
    return max(weight, 0.0)


def _prepare_product_probability_cache(
    config: KupferkanneRfmConfig,
    products_df: pd.DataFrame,
    archetype_lookup: dict[str, KupferkanneArchetypeConfig],
) -> dict[tuple[str, int], np.ndarray]:
    cache: dict[tuple[str, int], np.ndarray] = {}
    for archetype_name, archetype in archetype_lookup.items():
        for month_number in range(1, 13):
            weights = []
            for _, row in products_df.iterrows():
                category_weight = float(
                    config.catalog.category_order_shares.get(
                        str(row["ProductCategory"]), 0.0
                    )
                )
                affinity = float(
                    archetype.category_affinity.get(str(row["ProductCategory"]), 1.0)
                )
                tag_multiplier = _product_tag_multiplier(
                    config, list(row["tags"]), month_number
                )
                weight = (
                    float(row["base_weight"])
                    * category_weight
                    * affinity
                    * tag_multiplier
                )
                if row["ProductID"] == "PROD-057":
                    weight *= 0.18
                weights.append(weight)
            probabilities = np.array(weights, dtype=float)
            cache[(archetype_name, month_number)] = probabilities / probabilities.sum()
    return cache


def _pick_anchor_product(
    products_df: pd.DataFrame,
    state: CustomerState,
    order_date: date,
    rng: np.random.Generator,
    probability_cache: dict[tuple[str, int], np.ndarray],
) -> pd.Series:
    probabilities = probability_cache[(state.archetype, order_date.month)]
    product_index = int(rng.choice(np.arange(len(products_df)), p=probabilities))
    return products_df.iloc[product_index]


def _pick_initial_basket_size(
    config: KupferkanneRfmConfig, rng: np.random.Generator
) -> int:
    counts = np.array(sorted(config.basketing.initial_size_distribution), dtype=int)
    probabilities = np.array(
        [config.basketing.initial_size_distribution[int(count)] for count in counts],
        dtype=float,
    )
    probabilities = probabilities / probabilities.sum()
    return int(rng.choice(counts, p=probabilities))


def _resolve_basket_size(
    config: KupferkanneRfmConfig,
    state: CustomerState,
    anchor_product: pd.Series,
    desired_size: int,
    rng: np.random.Generator,
) -> int:
    category = str(anchor_product["ProductCategory"])
    tags = set(anchor_product["tags"])
    retail_price = float(anchor_product["RetailPrice"])
    size = int(desired_size)
    rule = config.basketing.affinity_rules.get(category)

    if rule is not None and rule.max_distinct_cap is not None:
        size = min(size, int(rule.max_distinct_cap))
    if (
        rule is not None
        and rule.single_item_override_probability > 0
        and float(rng.random()) < rule.single_item_override_probability
    ):
        size = 1
    if category == "Kitchen Accessories" and size > 2 and float(rng.random()) < 0.75:
        size = 2
    if retail_price >= 80 and size > 2 and float(rng.random()) < 0.70:
        size = 2
    if (
        state.archetype in {"One-Time Buyers", "Gift Buyers", "New Arrivals"}
        and size > 2
    ):
        size = 2
    if state.archetype == "Occasional Explorers" and size > 3:
        size = 3
    if state.archetype == "Coffee Regulars" and size > 3 and float(rng.random()) < 0.60:
        size = 3
    if state.archetype == "Churned Loyals" and size > 3 and float(rng.random()) < 0.50:
        size = 3
    if "corporate" in tags:
        size = 1
    return max(1, min(size, config.basketing.max_distinct_products_per_order))


def _pick_companion_products(
    config: KupferkanneRfmConfig,
    products_df: pd.DataFrame,
    state: CustomerState,
    order_date: date,
    rng: np.random.Generator,
    probability_cache: dict[tuple[str, int], np.ndarray],
    *,
    anchor_product: pd.Series,
    basket_size: int,
) -> list[pd.Series]:
    if basket_size <= 1:
        return [anchor_product]

    base_probabilities = probability_cache[(state.archetype, order_date.month)].copy()
    categories = products_df["ProductCategory"].astype(str).to_numpy()
    product_ids = products_df["ProductID"].astype(str).to_numpy()
    selected_indices = [int(anchor_product.name)]
    rule = config.basketing.affinity_rules.get(str(anchor_product["ProductCategory"]))
    product_weights = rule.product_weights if rule is not None else {}
    category_weights = rule.category_weights if rule is not None else {}

    while len(selected_indices) < basket_size:
        candidate_probabilities = base_probabilities.copy()
        for idx, (product_id, category_name) in enumerate(
            zip(product_ids, categories, strict=False)
        ):
            if idx in selected_indices:
                candidate_probabilities[idx] = 0.0
                continue
            candidate_probabilities[idx] *= float(
                category_weights.get(str(category_name), 1.0)
            )
            candidate_probabilities[idx] *= float(
                product_weights.get(str(product_id), 1.0)
            )
        probability_sum = float(candidate_probabilities.sum())
        if probability_sum <= 0:
            break
        candidate_probabilities = candidate_probabilities / probability_sum
        selected_indices.append(
            int(rng.choice(np.arange(len(products_df)), p=candidate_probabilities))
        )

    return [products_df.iloc[index] for index in selected_indices]


def _pick_quantity(product_row: pd.Series, rng: np.random.Generator) -> int:
    category = str(product_row["ProductCategory"])
    product_id = str(product_row["ProductID"])
    if category in {"Specialty Coffee", "Premium Teas"}:
        return int(rng.choice(np.array([1, 2, 3]), p=np.array([0.60, 0.30, 0.10])))
    if category == "Artisan Spices & Oils":
        return int(rng.choice(np.array([1, 2]), p=np.array([0.75, 0.25])))
    if category == "Specialty Pantry":
        return int(
            rng.choice(np.array([1, 2, 3, 4]), p=np.array([0.50, 0.30, 0.15, 0.05]))
        )
    if category == "Kitchen Accessories":
        return int(rng.choice(np.array([1, 2]), p=np.array([0.95, 0.05])))
    if category == "Curated Gift Boxes":
        if product_id == "PROD-057":
            return int(rng.choice(np.array([1, 2, 3]), p=np.array([0.90, 0.08, 0.02])))
        return 1
    return 1


def _window_match(order_date: date, start_text: str, end_text: str) -> bool:
    start_month, start_day = [int(part) for part in start_text.split("-")]
    end_month, end_day = [int(part) for part in end_text.split("-")]
    current = (order_date.month, order_date.day)
    return (start_month, start_day) <= current <= (end_month, end_day)


def _pick_discount(
    config: KupferkanneRfmConfig,
    state: CustomerState,
    anchor_product: pd.Series,
    order_date: date,
    rng: np.random.Generator,
) -> float:
    scenarios = {item.name: item for item in config.discounts.scenarios}
    candidate_names = ["No discount"]
    candidate_weights = [scenarios["No discount"].share]
    if state.order_count == 0 and "Welcome offer" in scenarios:
        candidate_names.append("Welcome offer")
        candidate_weights.append(scenarios["Welcome offer"].share * 4.5)
    if any(
        _window_match(order_date, window["start"], window["end"])
        for window in config.discounts.seasonal_windows
    ):
        candidate_names.append("Seasonal promo")
        candidate_weights.append(scenarios["Seasonal promo"].share * 4.0)
    if (
        state.order_count >= config.discounts.loyalty_min_prior_orders
        and state.archetype in {"Coffee Regulars", "Power Buyers"}
    ):
        candidate_names.append("Loyalty discount")
        candidate_weights.append(scenarios["Loyalty discount"].share * 3.5)
    if order_date.month in set(config.discounts.clearance_months):
        candidate_names.append("Clearance")
        candidate_weights.append(scenarios["Clearance"].share * 3.0)
    if str(anchor_product["ProductID"]) == "PROD-057":
        candidate_names.append("Corporate bulk")
        candidate_weights.append(scenarios["Corporate bulk"].share * 8.0)

    chosen = _choose_weighted(rng, candidate_names, candidate_weights)
    scenario = scenarios[chosen]
    if scenario.discount_max <= 0:
        return 0.0
    return round(float(rng.uniform(scenario.discount_min, scenario.discount_max)), 4)


def _line_discount_values(
    config: KupferkanneRfmConfig,
    state: CustomerState,
    anchor_product: pd.Series,
    order_date: date,
    rng: np.random.Generator,
    discount_rng: np.random.Generator | None,
    *,
    line_count: int,
    discount_variation: bool,
) -> list[float]:
    if (
        discount_variation
        and discount_rng is not None
        and state.discount_propensity is not None
    ):
        return [
            round(sample_discount(state.discount_propensity, discount_rng), 4)
            for _ in range(line_count)
        ]
    legacy_discount = _pick_discount(config, state, anchor_product, order_date, rng)
    return [legacy_discount] * line_count


def _append_order_rows(
    config: KupferkanneRfmConfig,
    state: CustomerState,
    order_date: date,
    month_label: str,
    rng: np.random.Generator,
    products_df: pd.DataFrame,
    probability_cache: dict[tuple[str, int], np.ndarray],
    year_order_counters: dict[int, int],
    fact_orders_rows: list[dict[str, object]],
    clean_line_rows: list[dict[str, object]],
    discount_rng: np.random.Generator | None,
    *,
    discount_variation: bool,
) -> None:
    desired_size = _pick_initial_basket_size(config, rng)
    anchor_product = _pick_anchor_product(
        products_df, state, order_date, rng, probability_cache
    )
    basket_size = _resolve_basket_size(config, state, anchor_product, desired_size, rng)
    basket_products = _pick_companion_products(
        config,
        products_df,
        state,
        order_date,
        rng,
        probability_cache,
        anchor_product=anchor_product,
        basket_size=basket_size,
    )
    line_discounts = _line_discount_values(
        config,
        state,
        anchor_product,
        order_date,
        rng,
        discount_rng,
        line_count=len(basket_products),
        discount_variation=discount_variation,
    )

    year_order_counters.setdefault(order_date.year, 0)
    year_order_counters[order_date.year] += 1
    order_id = _format_order_id(order_date.year, year_order_counters[order_date.year])
    line_rows: list[dict[str, object]] = []
    line_gross_total = 0.0
    line_discount_value_total = 0.0

    for line_number, (product_row, line_discount) in enumerate(
        zip(basket_products, line_discounts, strict=False), start=1
    ):
        quantity = _pick_quantity(product_row, rng)
        unit_price = round(float(product_row["RetailPrice"]), 2)
        unit_cost = round(float(product_row["UnitCost"]), 2)
        gross_line_amount = quantity * unit_price
        line_net_amount = round(gross_line_amount * (1.0 - line_discount), 2)
        line_gross_total += gross_line_amount
        line_discount_value_total += gross_line_amount * line_discount
        line_rows.append(
            {
                "OrderLineNumber": line_number,
                "OrderID": order_id,
                "CustomerID": state.customer_id,
                "OrderDate": order_date.isoformat(),
                "Country": state.country,
                "ProductID": str(product_row["ProductID"]),
                "ProductCategory": str(product_row["ProductCategory"]),
                "ProductName": str(product_row["ProductName"]),
                "Quantity": int(quantity),
                "UnitPrice": unit_price,
                "UnitCost": unit_cost,
                "LineDiscountPct": round(line_discount, 4),
                "LineNetAmount": line_net_amount,
                "OrderDiscountPct": 0.0,
                "BasketItemCount": len(basket_products),
            }
        )
    order_discount = (
        round(line_discount_value_total / line_gross_total, 4)
        if line_gross_total > 0
        else 0.0
    )
    fact_orders_rows.append(
        {
            "OrderID": order_id,
            "CustomerID": state.customer_id,
            "OrderDate": order_date.isoformat(),
            "Country": state.country,
            "OrderDiscountPct": order_discount,
            "BasketItemCount": len(basket_products),
        }
    )
    for row in line_rows:
        row["OrderDiscountPct"] = order_discount
        clean_line_rows.append(row)

    state.order_count += 1
    state.last_order_date = order_date
    state.monthly_order_counts[month_label] = (
        state.monthly_order_counts.get(month_label, 0) + 1
    )


def build_clean_kupferkanne_frames(
    config: KupferkanneRfmConfig,
    *,
    seed: int = 42,
    discount_variation: bool = True,
) -> dict[str, object]:
    # Audit P1-11: route through the rng factory. salt=0 ('master') keeps
    # the byte stream identical to the legacy default_rng(seed). A future
    # version-bump can promote this to a dedicated salt for stronger
    # isolation between clean-frame generation and dirty-data injection.
    rng = make_rng(seed, "master")
    discount_rng = build_discount_rng(seed) if discount_variation else None
    month_plans = build_month_plans(config, rng)
    dim_products = build_product_dimension(
        config, discount_variation=discount_variation
    )
    dim_customers, customer_states, customers_by_month, archetype_lookup = (
        build_customer_population(
            config,
            month_plans,
            rng,
            discount_rng,
        )
    )
    product_probability_cache = _prepare_product_probability_cache(
        config, dim_products, archetype_lookup
    )

    fact_orders_rows: list[dict[str, object]] = []
    clean_line_rows: list[dict[str, object]] = []
    year_order_counters: dict[int, int] = {}
    _baseline_values = list(config.seasonality.monthly_order_baseline.values())
    _baseline_mean = sum(_baseline_values) / len(_baseline_values)

    for plan in month_plans:
        month_customers = customers_by_month[plan.label]
        for customer_id in month_customers:
            state = customer_states[customer_id]
            order_date = _random_date_in_range(
                rng, max(plan.month_start, state.signup_date), plan.month_end
            )
            _append_order_rows(
                config,
                state,
                order_date,
                plan.label,
                rng,
                dim_products,
                product_probability_cache,
                year_order_counters,
                fact_orders_rows,
                clean_line_rows,
                discount_rng,
                discount_variation=discount_variation,
            )

        slot_customer_ids: list[str] = []
        slot_weights: list[float] = []
        n_eligible_unique = 0
        for customer_id, state in customer_states.items():
            if state.signup_date > plan.month_end:
                continue
            archetype = archetype_lookup[state.archetype]
            weight = _customer_month_weight(state, archetype, plan)
            if weight <= 0:
                continue
            n_eligible_unique += 1
            existing_monthly_orders = state.monthly_order_counts.get(plan.label, 0)
            available_slots = max(
                0, archetype.max_orders_per_month - existing_monthly_orders
            )
            for slot_index in range(available_slots):
                slot_customer_ids.append(customer_id)
                slot_weights.append(
                    weight * (archetype.same_month_repeat_weight**slot_index)
                )

        seasonal_mult = (
            config.seasonality.monthly_order_baseline[plan.month_start.month]
            / _baseline_mean
        )
        # Issue #7: scale the repeat budget by the partial-period day-ratio, the
        # same active_days / days_in_month factor build_month_plans applies to the
        # order target. Computed as a single division so full months, where
        # active_days == days_in_month, yield exactly 1.0 and leave their repeat
        # budgets byte-identical; only the final partial month shrinks.
        partial_ratio = plan.active_days / plan.days_in_month
        repeat_budget = round(
            n_eligible_unique
            * config.customers.target_per_capita_repeat_rate
            * seasonal_mult
            * partial_ratio
        )
        if repeat_budget > 0 and slot_customer_ids:
            slot_array = np.array(slot_customer_ids, dtype=object)
            slot_weight_array = np.array(slot_weights, dtype=float)
            slot_weight_array = slot_weight_array / slot_weight_array.sum()
            take = min(repeat_budget, len(slot_array))
            sampled_customer_ids = rng.choice(
                slot_array, size=take, replace=False, p=slot_weight_array
            )
            for customer_id in sampled_customer_ids.tolist():
                state = customer_states[str(customer_id)]
                order_date = _random_date_in_range(
                    rng, plan.month_start, plan.month_end
                )
                _append_order_rows(
                    config,
                    state,
                    order_date,
                    plan.label,
                    rng,
                    dim_products,
                    product_probability_cache,
                    year_order_counters,
                    fact_orders_rows,
                    clean_line_rows,
                    discount_rng,
                    discount_variation=discount_variation,
                )

    fact_orders = pd.DataFrame(fact_orders_rows)
    clean_lines = pd.DataFrame(clean_line_rows)
    return {
        "month_plans": month_plans,
        "dim_customers": dim_customers[
            [
                "CustomerID",
                "signup_date",
                "Country",
                "customer_archetype",
                "churn_end_month",
                *KUPFERKANNE_DIM_CUSTOMERS_EXTRA_COLUMNS,
            ]
        ].copy(),
        "dim_products": dim_products.copy(),
        "fact_orders": fact_orders.copy(),
        "clean_lines": clean_lines[INTERNAL_LINE_COLUMNS].copy(),
    }


def _orders_filename(config: KupferkanneRfmConfig, value: date) -> str:
    return _month_filename(config.output.orders_prefix, value)


def _items_filename(config: KupferkanneRfmConfig, value: date) -> str:
    return _month_filename(config.output.items_prefix, value)


def _dim_customers_export_columns(config: KupferkanneRfmConfig) -> list[str]:
    selected = set(config.output.dim_customers_extra_columns)
    ordered_internal = [
        "CustomerID",
        "signup_date",
        "customer_archetype",
        *[
            column
            for column in ["first_name", "last_name", "email", "phone"]
            if column in selected
        ],
        "Country",
        *[column for column in ["state", "city", "address"] if column in selected],
    ]
    return [DIM_CUSTOMERS_EXPORT_LABELS[column] for column in ordered_internal]


def _build_dim_customers_export(
    config: KupferkanneRfmConfig, dim_customers: pd.DataFrame
) -> pd.DataFrame:
    return dim_customers.rename(columns=DIM_CUSTOMERS_EXPORT_LABELS)[
        _dim_customers_export_columns(config)
    ].copy()


def _build_dim_products_export(dim_products: pd.DataFrame) -> pd.DataFrame:
    return dim_products[DIM_PRODUCTS_EXPORT_COLUMNS].copy()


def _build_orders_export(fact_orders: pd.DataFrame) -> pd.DataFrame:
    return fact_orders[ORDERS_COLUMNS].copy()


def _build_items_export(clean_lines: pd.DataFrame) -> pd.DataFrame:
    return clean_lines.rename(columns={"OrderLineNumber": "LineNumber"})[
        ["OrderDate", *ITEMS_COLUMNS]
    ].copy()


def _split_monthly_orders_files(
    config: KupferkanneRfmConfig,
    fact_orders: pd.DataFrame,
    month_plans: list[KupferMonthPlan],
) -> dict[str, pd.DataFrame]:
    order_dates = pd.to_datetime(fact_orders["OrderDate"], errors="coerce")
    grouped: dict[str, pd.DataFrame] = {}
    for plan in month_plans:
        filename = _orders_filename(config, plan.month_start)
        mask = order_dates.dt.strftime("%Y-%m").eq(plan.label)
        grouped[filename] = (
            fact_orders.loc[mask, ORDERS_COLUMNS].reset_index(drop=True).copy()
        )
    return grouped


def _split_monthly_items_files(
    config: KupferkanneRfmConfig,
    clean_items: pd.DataFrame,
    month_plans: list[KupferMonthPlan],
) -> dict[str, pd.DataFrame]:
    order_dates = pd.to_datetime(clean_items["OrderDate"], errors="coerce")
    grouped: dict[str, pd.DataFrame] = {}
    for plan in month_plans:
        filename = _items_filename(config, plan.month_start)
        mask = order_dates.dt.strftime("%Y-%m").eq(plan.label)
        grouped[filename] = clean_items.loc[mask].reset_index(drop=True).copy()
    return grouped


def _issue_count(total_rows: int, rate: float) -> int:
    if total_rows <= 0 or rate <= 0:
        return 0
    return max(1, int(round(total_rows * rate)))


def _prepare_dirty_orders_files(
    files: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    prepared: dict[str, pd.DataFrame] = {}
    object_columns = {"OrderID", "CustomerID", "OrderDate"}
    for name, df in files.items():
        copy = df.reset_index(drop=True).copy()
        for column in object_columns:
            copy[column] = copy[column].astype(object)
        prepared[name] = copy
    return prepared


def _prepare_dirty_items_files(
    files: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    prepared: dict[str, pd.DataFrame] = {}
    object_columns = {"OrderID", "ProductID", "LineNetAmount"}
    for name, df in files.items():
        copy = df.reset_index(drop=True).copy()
        for column in object_columns:
            if column in copy.columns:
                copy[column] = copy[column].astype(object)
        prepared[name] = copy
    return prepared


def _build_location_frame(
    files: dict[str, pd.DataFrame], *, date_column: str | None
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for file_name, df in files.items():
        if df.empty:
            continue
        event_dates = (
            pd.to_datetime(df[date_column], errors="coerce")
            if date_column is not None
            else pd.Series(pd.NaT, index=df.index)
        )
        frames.append(
            pd.DataFrame(
                {
                    "file_name": file_name,
                    "row_index": np.arange(len(df), dtype=int),
                    "event_date": event_dates,
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["file_name", "row_index", "event_date"])
    return pd.concat(frames, ignore_index=True)


def _pick_location_indices(
    location_frame: pd.DataFrame,
    rng: np.random.Generator,
    used_mask: np.ndarray,
    *,
    count: int,
    mask: np.ndarray,
) -> np.ndarray:
    if count <= 0 or location_frame.empty:
        return np.array([], dtype=int)
    candidate_indices = np.flatnonzero(mask & ~used_mask)
    if candidate_indices.size == 0:
        return np.array([], dtype=int)
    take = min(count, candidate_indices.size)
    picks = np.array(rng.choice(candidate_indices, size=take, replace=False), dtype=int)
    used_mask[picks] = True
    return picks


def inject_kupferkanne_dirty_data(
    config: KupferkanneRfmConfig,
    clean_orders: pd.DataFrame,
    clean_items: pd.DataFrame,
    month_plans: list[KupferMonthPlan],
    *,
    seed: int,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, object]]:
    orders_files = _split_monthly_orders_files(config, clean_orders, month_plans)
    items_files = _split_monthly_items_files(config, clean_items, month_plans)
    # Audit P1-11: route through the rng factory (salt=0). See note above.
    rng = make_rng(seed, "master")
    summary: dict[str, object] = {}

    clean_order_total = int(sum(len(df) for df in orders_files.values()))
    clean_item_total = int(sum(len(df) for df in items_files.values()))
    clean_fact_total = clean_order_total + clean_item_total
    duplicate_target = (
        _issue_count(clean_fact_total, config.data_quality.duplicate_row_rate)
        if config.data_quality.enabled
        else 0
    )
    duplicate_added = 0
    ordered_filenames = [
        _items_filename(config, plan.month_start) for plan in month_plans
    ]
    for file_name in ordered_filenames:
        if duplicate_added >= duplicate_target:
            break
        source_df = items_files[file_name]
        if source_df.empty:
            continue
        source_dates = pd.to_datetime(source_df["OrderDate"], errors="coerce")
        if source_dates.notna().sum() == 0:
            continue
        max_date = source_dates.max()
        candidates = source_df.loc[
            source_dates
            >= (
                max_date
                - timedelta(days=config.data_quality.duplicate_boundary_days - 1)
            )
        ]
        if candidates.empty:
            continue
        take = min(len(candidates), duplicate_target - duplicate_added)
        picks = rng.choice(np.arange(len(candidates)), size=take, replace=False)
        items_files[file_name] = pd.concat(
            [items_files[file_name], candidates.iloc[picks].copy(deep=True)],
            ignore_index=True,
        )
        duplicate_added += int(take)
    summary["duplicate_rows"] = {
        "actual_count": duplicate_added,
        "target_count": duplicate_target,
    }

    if not config.data_quality.enabled:
        return orders_files, items_files, summary

    orders_files = _prepare_dirty_orders_files(orders_files)
    items_files = _prepare_dirty_items_files(items_files)
    order_locations = _build_location_frame(orders_files, date_column="OrderDate")
    item_locations = _build_location_frame(items_files, date_column="OrderDate")
    total_rows = int(
        sum(len(df) for df in orders_files.values())
        + sum(len(df) for df in items_files.values())
    )
    used_order_mask = np.zeros(len(order_locations), dtype=bool)
    used_item_mask = np.zeros(len(item_locations), dtype=bool)
    all_order_mask = np.ones(len(order_locations), dtype=bool)
    all_item_mask = np.ones(len(item_locations), dtype=bool)

    counts = {
        "null_customer_id": _issue_count(
            total_rows, config.data_quality.null_customer_id_rate
        ),
        "null_order_date": _issue_count(
            total_rows, config.data_quality.null_order_date_rate
        ),
        "malformed_date": _issue_count(
            total_rows, config.data_quality.malformed_date_rate
        ),
        "future_date": _issue_count(total_rows, config.data_quality.future_date_rate),
        "negative_line_net_amount": _issue_count(
            total_rows, config.data_quality.negative_line_net_amount_rate
        ),
        "zero_line_net_amount": _issue_count(
            total_rows, config.data_quality.zero_line_net_amount_rate
        ),
        "cents_line_net_amount": _issue_count(
            total_rows, config.data_quality.cents_line_net_amount_rate
        ),
        "whitespace_ids": _issue_count(
            total_rows, config.data_quality.whitespace_id_rate
        ),
        "null_line_net_amount": _issue_count(
            total_rows, config.data_quality.null_line_net_amount_rate
        ),
    }

    picks = _pick_location_indices(
        order_locations,
        rng,
        used_order_mask,
        count=counts["null_customer_id"],
        mask=all_order_mask,
    )
    for location_index in picks.tolist():
        file_name = str(order_locations.at[location_index, "file_name"])
        row_index = int(order_locations.at[location_index, "row_index"])
        orders_files[file_name].at[row_index, "CustomerID"] = ""
    summary["null_customer_id"] = {
        "actual_count": int(len(picks)),
        "target_count": counts["null_customer_id"],
    }

    picks = _pick_location_indices(
        order_locations,
        rng,
        used_order_mask,
        count=counts["null_order_date"],
        mask=all_order_mask,
    )
    for location_index in picks.tolist():
        file_name = str(order_locations.at[location_index, "file_name"])
        row_index = int(order_locations.at[location_index, "row_index"])
        orders_files[file_name].at[row_index, "OrderDate"] = ""
    summary["null_order_date"] = {
        "actual_count": int(len(picks)),
        "target_count": counts["null_order_date"],
    }

    malformed_file = f"{config.output.orders_prefix}{config.data_quality.malformed_date_month[2:].replace('-', '')}.csv"
    malformed_variants = ["14/02/2024", "2024.02.15", "15. Feb 2024"]
    malformed_mask = order_locations["file_name"].eq(malformed_file).to_numpy()
    picks = _pick_location_indices(
        order_locations,
        rng,
        used_order_mask,
        count=counts["malformed_date"],
        mask=malformed_mask,
    )
    for idx, location_index in enumerate(picks.tolist()):
        file_name = str(order_locations.at[location_index, "file_name"])
        row_index = int(order_locations.at[location_index, "row_index"])
        orders_files[file_name].at[row_index, "OrderDate"] = malformed_variants[
            idx % len(malformed_variants)
        ]
    summary["malformed_date"] = {
        "actual_count": int(len(picks)),
        "target_count": counts["malformed_date"],
    }

    january_files = {
        f"{config.output.orders_prefix}{year % 100:02d}01.csv"
        for year in config.data_quality.future_date_anchor_years
    }
    january_mask = order_locations["file_name"].isin(january_files).to_numpy()
    january_date_mask = (
        january_mask
        & order_locations["event_date"].notna().to_numpy()
        & order_locations["event_date"].dt.day.eq(1).to_numpy()
    )
    picks = _pick_location_indices(
        order_locations,
        rng,
        used_order_mask,
        count=counts["future_date"],
        mask=january_date_mask,
    )
    for location_index in picks.tolist():
        file_name = str(order_locations.at[location_index, "file_name"])
        row_index = int(order_locations.at[location_index, "row_index"])
        orders_files[file_name].at[row_index, "OrderDate"] = "2027-01-01"
    summary["future_date"] = {
        "actual_count": int(len(picks)),
        "target_count": counts["future_date"],
    }

    jan_files = {
        f"{config.output.items_prefix}{year % 100:02d}01.csv"
        for year in range(
            config.period.start_date.year, config.period.end_date.year + 1
        )
    }
    jul_files = {
        f"{config.output.items_prefix}{year % 100:02d}07.csv"
        for year in range(
            config.period.start_date.year, config.period.end_date.year + 1
        )
    }
    jan_count = int(round(counts["negative_line_net_amount"] * 0.40))
    jul_count = int(round(counts["negative_line_net_amount"] * 0.20))
    other_count = max(0, counts["negative_line_net_amount"] - jan_count - jul_count)
    jan_mask = item_locations["file_name"].isin(jan_files).to_numpy()
    jul_mask = item_locations["file_name"].isin(jul_files).to_numpy()
    other_mask = ~(jan_mask | jul_mask)
    negative_picks = np.concatenate(
        [
            _pick_location_indices(
                item_locations, rng, used_item_mask, count=jan_count, mask=jan_mask
            ),
            _pick_location_indices(
                item_locations, rng, used_item_mask, count=jul_count, mask=jul_mask
            ),
            _pick_location_indices(
                item_locations, rng, used_item_mask, count=other_count, mask=other_mask
            ),
        ]
    )
    for location_index in negative_picks.tolist():
        file_name = str(item_locations.at[location_index, "file_name"])
        row_index = int(item_locations.at[location_index, "row_index"])
        value = abs(
            float(
                pd.to_numeric(
                    pd.Series([items_files[file_name].at[row_index, "LineNetAmount"]]),
                    errors="coerce",
                )
                .fillna(1.0)
                .iloc[0]
            )
        )
        items_files[file_name].at[row_index, "LineNetAmount"] = round(-value, 2)
    summary["negative_line_net_amount"] = {
        "actual_count": int(len(negative_picks)),
        "target_count": counts["negative_line_net_amount"],
    }

    q1_files = {
        f"{config.output.items_prefix}{year % 100:02d}{month:02d}.csv"
        for year in range(
            config.period.start_date.year, config.period.end_date.year + 1
        )
        for month in (1, 2, 3)
    }
    q1_count = int(round(counts["zero_line_net_amount"] * 0.60))
    q1_mask = item_locations["file_name"].isin(q1_files).to_numpy()
    zero_picks = np.concatenate(
        [
            _pick_location_indices(
                item_locations, rng, used_item_mask, count=q1_count, mask=q1_mask
            ),
            _pick_location_indices(
                item_locations,
                rng,
                used_item_mask,
                count=max(0, counts["zero_line_net_amount"] - q1_count),
                mask=~q1_mask,
            ),
        ]
    )
    for location_index in zero_picks.tolist():
        file_name = str(item_locations.at[location_index, "file_name"])
        row_index = int(item_locations.at[location_index, "row_index"])
        items_files[file_name].at[row_index, "LineNetAmount"] = 0.0
    summary["zero_line_net_amount"] = {
        "actual_count": int(len(zero_picks)),
        "target_count": counts["zero_line_net_amount"],
    }

    cents_dates = item_locations["event_date"]
    cents_mask = (
        item_locations["file_name"]
        .eq(_items_filename(config, config.data_quality.cents_window_start))
        .to_numpy()
        & cents_dates.notna().to_numpy()
        & cents_dates.ge(
            pd.Timestamp(config.data_quality.cents_window_start)
        ).to_numpy()
        & cents_dates.le(pd.Timestamp(config.data_quality.cents_window_end)).to_numpy()
    )
    picks = _pick_location_indices(
        item_locations,
        rng,
        used_item_mask,
        count=counts["cents_line_net_amount"],
        mask=cents_mask,
    )
    for location_index in picks.tolist():
        file_name = str(item_locations.at[location_index, "file_name"])
        row_index = int(item_locations.at[location_index, "row_index"])
        value = abs(
            float(
                pd.to_numeric(
                    pd.Series([items_files[file_name].at[row_index, "LineNetAmount"]]),
                    errors="coerce",
                )
                .fillna(1.0)
                .iloc[0]
            )
        )
        items_files[file_name].at[row_index, "LineNetAmount"] = int(round(value * 100))
    summary["cents_line_net_amount"] = {
        "actual_count": int(len(picks)),
        "target_count": counts["cents_line_net_amount"],
    }

    whitespace_order_target = int(round(counts["whitespace_ids"] * 0.5))
    whitespace_item_target = max(0, counts["whitespace_ids"] - whitespace_order_target)
    order_picks = _pick_location_indices(
        order_locations,
        rng,
        used_order_mask,
        count=whitespace_order_target,
        mask=all_order_mask,
    )
    item_picks = _pick_location_indices(
        item_locations,
        rng,
        used_item_mask,
        count=whitespace_item_target,
        mask=all_item_mask,
    )
    for location_index in order_picks.tolist():
        file_name = str(order_locations.at[location_index, "file_name"])
        row_index = int(order_locations.at[location_index, "row_index"])
        orders_files[file_name].at[row_index, "CustomerID"] = (
            f" {orders_files[file_name].at[row_index, 'CustomerID']} "
        )
    for location_index in item_picks.tolist():
        file_name = str(item_locations.at[location_index, "file_name"])
        row_index = int(item_locations.at[location_index, "row_index"])
        if int(rng.integers(0, 2)) == 0:
            items_files[file_name].at[row_index, "OrderID"] = (
                f" {items_files[file_name].at[row_index, 'OrderID']} "
            )
        else:
            items_files[file_name].at[row_index, "ProductID"] = (
                f" {items_files[file_name].at[row_index, 'ProductID']} "
            )
    summary["whitespace_ids"] = {
        "actual_count": int(len(order_picks) + len(item_picks)),
        "target_count": counts["whitespace_ids"],
    }

    picks = _pick_location_indices(
        item_locations,
        rng,
        used_item_mask,
        count=counts["null_line_net_amount"],
        mask=all_item_mask,
    )
    for location_index in picks.tolist():
        file_name = str(item_locations.at[location_index, "file_name"])
        row_index = int(item_locations.at[location_index, "row_index"])
        items_files[file_name].at[row_index, "LineNetAmount"] = ""
    summary["null_line_net_amount"] = {
        "actual_count": int(len(picks)),
        "target_count": counts["null_line_net_amount"],
    }
    return orders_files, items_files, summary


def build_kupferkanne_manifest(
    config: KupferkanneRfmConfig,
    month_plans: list[KupferMonthPlan],
    dim_customers: pd.DataFrame,
    dim_products: pd.DataFrame,
    fact_orders: pd.DataFrame,
    clean_lines: pd.DataFrame,
    final_orders_files: dict[str, pd.DataFrame],
    final_items_files: dict[str, pd.DataFrame],
    issue_summary: dict[str, object],
    order_row_counts: dict[str, int],
    item_row_counts: dict[str, int],
) -> dict[str, object]:
    total_rows = int(sum(order_row_counts.values()) + sum(item_row_counts.values()))
    dirty_issue_rows = int(sum(item["actual_count"] for item in issue_summary.values()))
    dirty_rate = dirty_issue_rows / total_rows if total_rows else 0.0
    clean_unique_orders = int(fact_orders["OrderID"].nunique())
    clean_unique_customers = int(dim_customers["CustomerID"].nunique())
    avg_items_per_order = (
        len(clean_lines) / clean_unique_orders if clean_unique_orders else 0.0
    )
    basket_counts = clean_lines.groupby("OrderID")["OrderLineNumber"].nunique()
    single_item_share = (
        float((basket_counts == 1).mean()) if not basket_counts.empty else 0.0
    )
    five_plus_share = (
        float((basket_counts >= 5).mean()) if not basket_counts.empty else 0.0
    )
    december_counts = [
        count
        for name, count in item_row_counts.items()
        if name.endswith("11.csv") or name.endswith("12.csv")
    ]
    average_month = (
        sum(item_row_counts.values()) / len(item_row_counts) if item_row_counts else 0.0
    )
    corporate_order_share = (
        float(
            clean_lines.loc[
                clean_lines["ProductID"].eq("PROD-057"), "OrderID"
            ].nunique()
            / clean_unique_orders
        )
        if clean_unique_orders
        else 0.0
    )
    clean_formula = clean_lines.assign(
        expected=(
            pd.to_numeric(clean_lines["Quantity"], errors="coerce")
            * pd.to_numeric(clean_lines["UnitPrice"], errors="coerce")
            * (1 - pd.to_numeric(clean_lines["LineDiscountPct"], errors="coerce"))
        ).round(2)
    )
    advent_ids = {"PROD-009", "PROD-018", "PROD-043"}
    advent_months_ok = not clean_lines.loc[
        clean_lines["ProductID"].isin(advent_ids), "OrderDate"
    ].pipe(
        lambda s: (
            pd.to_datetime(s, errors="coerce").dt.month.isin([11, 12]).eq(False).any()
        )
    )

    checks = {
        "orders_file_count_is_39": len(order_row_counts) == 39,
        "items_file_count_is_39": len(item_row_counts) == 39,
        "dimensions_count_is_2": True,
        "total_item_rows_in_target_range": config.validation_targets.total_rows_min
        <= len(clean_lines)
        <= config.validation_targets.total_rows_max,
        "unique_orders_in_target_range": config.validation_targets.unique_orders_min
        <= clean_unique_orders
        <= config.validation_targets.unique_orders_max,
        "unique_customers_near_target": abs(
            clean_unique_customers - config.validation_targets.unique_customers_target
        )
        <= config.validation_targets.unique_customers_tolerance,
        "avg_items_per_order_in_range": config.validation_targets.avg_lines_per_order_min
        <= avg_items_per_order
        <= config.validation_targets.avg_lines_per_order_max,
        "single_item_share_near_target": abs(
            single_item_share - config.validation_targets.single_item_share_target
        )
        <= config.validation_targets.single_item_share_tolerance,
        "five_plus_share_below_max": five_plus_share
        < config.validation_targets.five_plus_max_share,
        "orders_have_one_row_per_order": fact_orders["OrderID"].is_unique,
        "items_allow_repeated_order_ids": bool((basket_counts > 1).any()),
        "no_order_total_column": all(
            "OrderValue" not in df.columns and "OrderTotal" not in df.columns
            for df in final_orders_files.values()
        )
        and all(
            "OrderValue" not in df.columns and "OrderTotal" not in df.columns
            for df in final_items_files.values()
        ),
        "line_formula_valid_for_clean_rows": np.allclose(
            clean_formula["LineNetAmount"], clean_formula["expected"], atol=0.01
        ),
        "basket_item_count_valid_for_clean_rows": fact_orders.set_index("OrderID")[
            "BasketItemCount"
        ]
        .eq(basket_counts)
        .all(),
        "dirty_rate_near_target": abs(
            dirty_rate - config.validation_targets.dirty_rate_target
        )
        <= config.validation_targets.dirty_rate_tolerance,
        "holiday_peak_visible": (
            float(np.mean(december_counts)) if december_counts else 0.0
        )
        > average_month * 1.75,
        "all_product_ids_known": set(clean_lines["ProductID"]).issubset(
            set(dim_products["ProductID"])
        ),
        "corporate_box_rare_enough": corporate_order_share
        < config.validation_targets.corporate_order_share_max,
        "advent_products_nov_dec_only": advent_months_ok,
    }

    return {
        "company": config.company.model_dump(mode="json"),
        "period": {
            "start_date": config.period.start_date.isoformat(),
            "end_date": config.period.end_date.isoformat(),
        },
        "schema_version": "4-table-star",
        "output": {
            "orders_prefix": config.output.orders_prefix,
            "items_prefix": config.output.items_prefix,
            "dim_customers_filename": config.output.dim_customers_filename,
            "dim_products_filename": config.output.dim_products_filename,
            "dim_customers_columns": _dim_customers_export_columns(config),
        },
        "files": {
            "orders": sorted(order_row_counts),
            "items": sorted(item_row_counts),
            "dimensions": [
                config.output.dim_customers_filename,
                config.output.dim_products_filename,
            ],
        },
        "row_counts": {
            "orders": order_row_counts,
            "items": item_row_counts,
        },
        "clean_metrics": {
            "total_order_rows": int(len(fact_orders)),
            "total_item_rows": int(len(clean_lines)),
            "unique_orders": clean_unique_orders,
            "unique_customers": clean_unique_customers,
            "avg_items_per_order": round(avg_items_per_order, 4),
            "single_item_share": round(single_item_share, 4),
            "five_plus_item_share": round(five_plus_share, 4),
            "corporate_order_share": round(corporate_order_share, 5),
        },
        "final_metrics": {
            "total_fact_rows": total_rows,
            "dirty_rate": round(dirty_rate, 6),
            "duplicate_rows": int(issue_summary["duplicate_rows"]["actual_count"]),
        },
        "customer_summary": {
            "country_distribution": dim_customers["Country"]
            .value_counts(normalize=True)
            .round(4)
            .to_dict(),
            "archetype_distribution": dim_customers["customer_archetype"]
            .value_counts(normalize=True)
            .round(4)
            .to_dict(),
        },
        "month_plans": [asdict(plan) for plan in month_plans],
        "quality_issues": issue_summary,
        "validation_checks": checks,
    }


def write_kupferkanne_schema_doc(config: KupferkanneRfmConfig, path: Path) -> None:
    content = "\n".join(
        [
            "# Kupferkanne Star Schema",
            "",
            "## Entity Relationship Diagram",
            "",
            "dim_customers --< fact_orders --< fact_order_items >-- dim_products",
            "",
            "## Tables",
            "",
            "### dim_customers (dimension, static)",
            "- CustomerID (PK)",
            "- SignupDate",
            "- CustomerArchetype",
            "- Country",
            "- Optional enrichment columns from config: FirstName, LastName, Email, Phone, State, City, Address",
            "",
            "### dim_products (dimension, static)",
            "- ProductID (PK)",
            "- ProductName",
            "- ProductCategory",
            "- Brand",
            "- RetailPrice",
            "- UnitCost",
            "- MarginPct",
            "",
            "### fact_orders (fact, monthly shards: orders20YYMM)",
            "- OrderID (PK)",
            "- CustomerID (FK -> dim_customers)",
            "- OrderDate",
            "- OrderDiscountPct",
            "- BasketItemCount",
            "",
            "### fact_order_items (fact, monthly shards: items20YYMM)",
            "- OrderID (FK -> fact_orders)",
            "- LineNumber (1-based within each OrderID; clean PK component with OrderID)",
            "- ProductID (FK -> dim_products)",
            "- Quantity",
            "- UnitPrice",
            "- LineNetAmount",
            "",
            "## Notes",
            "- OrderValue is intentionally absent from fact_orders; derive it as SUM(LineNetAmount) GROUP BY OrderID.",
            "- Dimension tables are always clean; quality issues exist only in fact tables.",
            "- OrderDiscountPct is the basket-weighted average of internal line discounts.",
            "- Clean fact_order_items rows are uniquely identified by (OrderID, LineNumber).",
            f"- dim_customers export columns: {', '.join(_dim_customers_export_columns(config))}",
        ]
    )
    path.write_text(content, encoding="utf-8")


def generate_kupferkanne_rfm(
    config: KupferkanneRfmConfig,
    output_dir: Path,
    *,
    seed: int = 42,
    discount_variation: bool = True,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dimensions_dir = output_dir / config.output.dimensions_dirname
    monthly_dir = output_dir / config.output.monthly_dirname
    dimensions_dir.mkdir(parents=True, exist_ok=True)
    monthly_dir.mkdir(parents=True, exist_ok=True)
    clean = build_clean_kupferkanne_frames(
        config, seed=seed, discount_variation=discount_variation
    )
    month_plans: list[KupferMonthPlan] = clean["month_plans"]
    dim_customers: pd.DataFrame = clean["dim_customers"]
    dim_products: pd.DataFrame = clean["dim_products"]
    fact_orders: pd.DataFrame = clean["fact_orders"]
    clean_lines: pd.DataFrame = clean["clean_lines"]

    dim_customers_export = _build_dim_customers_export(config, dim_customers)
    dim_products_export = _build_dim_products_export(dim_products)
    clean_orders_export = _build_orders_export(fact_orders)
    clean_items_export = _build_items_export(clean_lines)

    dim_customers_export.to_csv(
        dimensions_dir / config.output.dim_customers_filename, index=False
    )
    dim_products_export.to_csv(
        dimensions_dir / config.output.dim_products_filename, index=False
    )

    final_orders_files, final_items_files, issue_summary = (
        inject_kupferkanne_dirty_data(
            config,
            clean_orders_export,
            clean_items_export,
            month_plans,
            seed=seed + 501,
        )
    )

    order_row_counts: dict[str, int] = {}
    item_row_counts: dict[str, int] = {}
    for month_start, _ in _month_sequence(
        config.period.start_date, config.period.end_date
    ):
        orders_filename = _orders_filename(config, month_start)
        items_filename = _items_filename(config, month_start)
        final_orders_files[orders_filename][ORDERS_COLUMNS].to_csv(
            monthly_dir / orders_filename, index=False
        )
        final_items_files[items_filename][ITEMS_COLUMNS].to_csv(
            monthly_dir / items_filename, index=False
        )
        order_row_counts[orders_filename] = int(
            len(final_orders_files[orders_filename])
        )
        item_row_counts[items_filename] = int(len(final_items_files[items_filename]))

    write_effective_kupferkanne_config(
        config, output_dir / config.output.effective_config_filename
    )
    write_kupferkanne_schema_doc(config, output_dir / config.output.docs_filename)
    manifest = build_kupferkanne_manifest(
        config,
        month_plans,
        dim_customers,
        dim_products,
        fact_orders,
        clean_lines,
        final_orders_files,
        final_items_files,
        issue_summary,
        order_row_counts,
        item_row_counts,
    )
    (output_dir / config.output.manifest_filename).write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    return {
        "output": output_dir,
        "dimensions": dimensions_dir,
        "monthly": monthly_dir,
        "manifest": output_dir / config.output.manifest_filename,
        "dim_customers": dimensions_dir / config.output.dim_customers_filename,
        "dim_products": dimensions_dir / config.output.dim_products_filename,
    }
