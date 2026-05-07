"""
Lifecycle-first SaaS synthetic data engine v3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import hashlib
import math

import numpy as np
import pandas as pd
from faker import Faker

from ..rng import make_rng
from .config import (
    CountryConfig,
    EventTypeConfig,
    OutputMode,
    SaaSV3Config,
    SizeSegmentConfig,
)
from .ids import IdFactory
from .vocab import DEFAULT_CANCELLATION_REASONS, build_company_name, build_domain


TABLE_ORDER = (
    "accounts",
    "users",
    "subscriptions",
    "product_events",
    "invoices",
    "support_tickets",
    "nps_responses",
)

EXPORTED_COLUMNS: dict[str, list[str]] = {
    "accounts": [
        "account_id",
        "company_name",
        "industry",
        "company_size",
        "country",
        "signup_date",
        "status",
        "acquisition_channel",
    ],
    "users": ["user_id", "account_id", "email", "role", "last_login_at", "is_active"],
    "subscriptions": [
        "subscription_id",
        "account_id",
        "plan_name",
        "billing_period",
        "start_date",
        "end_date",
        "monthly_amount",
        "status",
        "cancellation_reason",
    ],
    "product_events": [
        "event_id",
        "account_id",
        "user_id",
        "event_name",
        "event_timestamp",
        "feature_category",
        "platform",
    ],
    "invoices": [
        "invoice_id",
        "account_id",
        "invoice_date",
        "amount_due",
        "amount_paid",
        "currency",
        "status",
    ],
    "support_tickets": [
        "ticket_id",
        "account_id",
        "category",
        "priority",
        "status",
        "satisfaction_rating",
        "resolution_minutes",
    ],
    "nps_responses": ["response_id", "account_id", "score", "survey_date"],
}


@dataclass
class GeneratedTables:
    tables: dict[str, list[pd.DataFrame]]
    hidden_tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def iter_batches(self, table_name: str):
        return iter(self.tables[table_name])

    def materialize(self, table_name: str) -> pd.DataFrame:
        batches = self.tables[table_name]
        if not batches:
            return pd.DataFrame(columns=EXPORTED_COLUMNS[table_name])
        return pd.concat(batches, ignore_index=True)

    def row_counts(self) -> dict[str, int]:
        return {
            table_name: sum(len(batch) for batch in batches)
            for table_name, batches in self.tables.items()
        }


@dataclass
class GenerationResult:
    clean: GeneratedTables
    dirty: GeneratedTables | None = None


def _seed_from_label(seed: int, label: str) -> int:
    payload = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(payload[:8], "big", signed=False)


def _normalize(weights: np.ndarray) -> np.ndarray:
    values = np.asarray(weights, dtype=float)
    if values.sum() <= 0:
        return np.full(len(values), 1.0 / len(values))
    return values / values.sum()


def _allocate_total(
    total: int, weights: np.ndarray, minimums: np.ndarray | None = None
) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    minimums = (
        np.zeros(len(weights), dtype=int)
        if minimums is None
        else np.asarray(minimums, dtype=int)
    )
    if total < int(minimums.sum()):
        raise ValueError(
            "Requested total is smaller than the enforced minimum allocation"
        )
    remaining = int(total - minimums.sum())
    if remaining == 0:
        return minimums.copy()
    probs = _normalize(weights)
    raw = probs * remaining
    base = np.floor(raw).astype(int)
    leftover = remaining - int(base.sum())
    if leftover > 0:
        order = np.argsort(-(raw - base))
        base[order[:leftover]] += 1
    return minimums + base


def _logistic(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _month_starts(start_date: date, end_date: date) -> list[date]:
    starts = pd.date_range(
        pd.Timestamp(start_date).replace(day=1),
        pd.Timestamp(end_date).replace(day=1),
        freq="MS",
    )
    return [ts.date() for ts in starts]


def _month_end(value: date, as_of_date: date) -> date:
    month_end = (pd.Timestamp(value) + pd.offsets.MonthEnd(0)).date()
    return min(month_end, as_of_date)


def _sample_dates_between(
    start_date: date, end_date: date, size: int, rng: np.random.Generator
) -> list[date]:
    if start_date >= end_date:
        return [start_date] * size
    offsets = rng.integers(0, (end_date - start_date).days + 1, size=size)
    return [start_date + timedelta(days=int(offset)) for offset in offsets]


def _format_date_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.date


# Stable order — appending new labels is OK; reordering shifts bytes.
_RNG_LABELS: tuple[str, ...] = (
    "accounts",
    "lifecycle",
    "subscriptions",
    "account_month_state",
    "users",
    "invoices",
    "support_tickets",
    "nps",
    "product_events",
)


class SaaSV3Engine:
    def __init__(self, config: SaaSV3Config, seed_override: int | None = None) -> None:
        self.config = config.model_copy(deep=True)
        if seed_override is not None:
            self.config.run.seed = seed_override
        self.seed = self.config.run.seed
        self._parent_rng = make_rng(self.seed, "saas_v3")
        spawned = self._parent_rng.spawn(len(_RNG_LABELS))
        self._rng_streams: dict[str, np.random.Generator] = dict(
            zip(_RNG_LABELS, spawned)
        )
        self.faker = Faker()
        self.faker.seed_instance(self.seed)
        self.id_factory = IdFactory()
        self.as_of_date = self.config.history.as_of_date
        self.history_start = self.config.history_start
        self.plan_by_name = {plan.name: plan for plan in self.config.plans}
        self.plan_order = [plan.name for plan in self.config.plans]
        self.plan_rank = {
            plan.name: index for index, plan in enumerate(self.config.plans)
        }
        self.size_by_name = {
            segment.name: segment for segment in self.config.company_sizes
        }
        self.country_by_name = {
            country.name: country for country in self.config.countries
        }
        self.industry_by_name = {
            industry.name: industry for industry in self.config.industries
        }
        self.channel_by_name = {
            channel.name: channel for channel in self.config.acquisition_channels
        }
        self.role_by_name = {role.name: role for role in self.config.role_mix}

    def _rng(self, label: str) -> np.random.Generator:
        try:
            return self._rng_streams[label]
        except KeyError as exc:
            raise KeyError(
                f"Unknown saas_v3 RNG label '{label}'. Add it to _RNG_LABELS."
            ) from exc

    def _sample_configs(
        self,
        configs: list,
        size: int,
        rng: np.random.Generator,
        weight_attr: str = "weight",
    ) -> list:
        weights = np.array(
            [getattr(item, weight_attr) for item in configs], dtype=float
        )
        indices = rng.choice(len(configs), size=size, p=_normalize(weights))
        return [configs[int(index)] for index in indices]

    def generate(self, mode: OutputMode = OutputMode.BOTH) -> GenerationResult:
        profiles, billing_profile = self._build_account_profiles()
        lifecycle = self._build_lifecycle_scaffold(profiles, billing_profile)
        subscriptions = self._build_subscriptions(profiles, lifecycle)
        account_month_state = self._build_account_month_state(
            profiles, lifecycle, subscriptions
        )
        profiles = self._apply_latest_account_status(profiles, account_month_state)
        users, users_internal = self._build_users(profiles, account_month_state)
        activity_budget = self._build_activity_budget(
            account_month_state, users_internal
        )
        invoices, invoice_internal = self._build_invoices(
            profiles, subscriptions, account_month_state
        )
        support_tickets, support_internal = self._build_support_tickets(
            profiles, account_month_state
        )
        nps_responses, nps_internal = self._build_nps_responses(
            profiles, account_month_state
        )
        product_event_batches = self._build_product_events(
            activity_budget, users_internal
        )

        accounts = profiles[EXPORTED_COLUMNS["accounts"]].copy()
        clean = GeneratedTables(
            tables={
                "accounts": [accounts],
                "users": [users[EXPORTED_COLUMNS["users"]].copy()],
                "subscriptions": [
                    subscriptions[EXPORTED_COLUMNS["subscriptions"]].copy()
                ],
                "product_events": product_event_batches,
                "invoices": [invoices[EXPORTED_COLUMNS["invoices"]].copy()],
                "support_tickets": [
                    support_tickets[EXPORTED_COLUMNS["support_tickets"]].copy()
                ],
                "nps_responses": [
                    nps_responses[EXPORTED_COLUMNS["nps_responses"]].copy()
                ],
            },
            hidden_tables={
                "account_profile": profiles,
                "billing_profile": billing_profile,
                "lifecycle": lifecycle,
                "account_month_state": account_month_state,
                "users_internal": users_internal,
                "activity_budget": activity_budget,
                "invoice_internal": invoice_internal,
                "support_internal": support_internal,
                "nps_internal": nps_internal,
            },
            metadata={
                "mode": OutputMode.CLEAN.value,
                "seed": self.seed,
                "config_hash": self.config.config_hash(),
            },
        )
        clean.metadata["row_counts"] = clean.row_counts()
        if mode is OutputMode.CLEAN:
            return GenerationResult(clean=clean, dirty=None)
        from .defects import DefectInjector

        dirty = DefectInjector(self.config, self.seed).apply(clean)
        return GenerationResult(clean=clean, dirty=dirty)

    def _build_account_profiles(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        count = self.config.row_targets.accounts
        rng = self._rng("accounts")
        country_choices = self._sample_configs(self.config.countries, count, rng)
        industry_choices = self._sample_configs(self.config.industries, count, rng)
        size_choices = self._sample_configs(self.config.company_sizes, count, rng)
        channel_choices = self._sample_configs(
            self.config.acquisition_channels, count, rng
        )
        total_days = (self.as_of_date - self.history_start).days
        signup_offsets = np.floor(rng.beta(2.0, 1.5, size=count) * total_days).astype(
            int
        )
        signup_dates = [
            self.history_start + timedelta(days=int(offset))
            for offset in signup_offsets
        ]

        used_domains: set[str] = set()
        records: list[dict[str, object]] = []
        billing_records: list[dict[str, object]] = []
        for index in range(count):
            country: CountryConfig = country_choices[index]
            industry = industry_choices[index]
            segment: SizeSegmentConfig = size_choices[index]
            channel = channel_choices[index]
            signup_date = signup_dates[index]
            account_id = self.id_factory.next_id("account_id")
            company_name = build_company_name(
                industry.name, country.company_suffixes, rng
            )
            domain = build_domain(company_name, country.domain_tlds, used_domains, rng)
            base_health = float(np.clip(rng.normal(0.0, 0.55), -1.5, 1.5))
            expansion_score = float(
                np.clip(
                    base_health * 0.45
                    + channel.expansion_adjustment
                    + rng.normal(0.0, 0.45),
                    -1.8,
                    1.8,
                )
            )
            retention_score = float(
                np.clip(
                    base_health * 0.55
                    + channel.retention_adjustment
                    + rng.normal(0.0, 0.40),
                    -1.8,
                    1.8,
                )
            )
            payment_reliability = float(
                np.clip(
                    0.79 + 0.07 * retention_score + rng.normal(0.0, 0.06), 0.35, 0.99
                )
            )
            price_sensitivity = float(
                np.clip(
                    0.58
                    - 0.12 * (segment.name == "Enterprise")
                    + 0.08 * (segment.name == "SMB")
                    + rng.normal(0.0, 0.05),
                    0.05,
                    0.95,
                )
            )
            user_target = int(
                round(
                    rng.integers(segment.user_count_min, segment.user_count_max + 1)
                    * np.clip(
                        0.9
                        + 0.12 * industry.adoption_factor
                        + 0.10 * _logistic(base_health),
                        0.55,
                        1.7,
                    )
                )
            )
            records.append(
                {
                    "account_id": account_id,
                    "company_name": company_name,
                    "industry": industry.name,
                    "company_size": segment.name,
                    "country": country.name,
                    "signup_date": signup_date,
                    "status": "new",
                    "acquisition_channel": channel.name,
                    "domain": domain,
                    "timezone": country.timezone,
                    "utc_offset_hours": country.utc_offset_hours,
                    "currency": country.currency,
                    "industry_adoption_factor": industry.adoption_factor,
                    "industry_support_factor": industry.support_factor,
                    "industry_nps_bias": industry.nps_bias,
                    "base_health": base_health,
                    "expansion_score": expansion_score,
                    "retention_score": retention_score,
                    "payment_reliability": payment_reliability,
                    "price_sensitivity": price_sensitivity,
                    "base_user_target": max(1, user_target),
                }
            )
            billing_records.append(
                {
                    "account_id": account_id,
                    "preferred_billing_period": self._sample_billing_period(
                        segment.name, rng
                    ),
                    "currency": country.currency,
                    "dunning_risk": round(
                        float(
                            np.clip(
                                1.1 - payment_reliability + price_sensitivity / 3,
                                0.05,
                                1.5,
                            )
                        ),
                        4,
                    ),
                    "payment_reliability": payment_reliability,
                }
            )
        profiles = pd.DataFrame(records)
        profiles["signup_date"] = _format_date_series(profiles["signup_date"])
        billing_profile = pd.DataFrame(billing_records)
        return profiles, billing_profile

    def _build_lifecycle_scaffold(
        self, profiles: pd.DataFrame, billing_profile: pd.DataFrame
    ) -> pd.DataFrame:
        rng = self._rng("lifecycle")
        age_days = (
            pd.Timestamp(self.as_of_date) - pd.to_datetime(profiles["signup_date"])
        ).dt.days.clip(lower=30)
        account_count = len(profiles)
        target = self.config.row_targets.subscriptions
        churn_probs = (
            self.config.lifecycle.churn_base_probability
            * np.clip(
                1.05
                - profiles["retention_score"] * 0.12
                + profiles["price_sensitivity"] * 0.25,
                0.25,
                1.9,
            )
            * np.clip(age_days / 365, 0.35, 1.6)
        ).clip(0.02, 0.62)
        churned = rng.random(account_count) < churn_probs.to_numpy(dtype=float)
        churned = np.where(
            age_days < self.config.lifecycle.minimum_tenure_days_before_churn,
            False,
            churned,
        )
        if target >= account_count:
            extras = _allocate_total(
                target - account_count,
                weights=(
                    age_days.to_numpy(dtype=float)
                    * np.clip(
                        1.2
                        + profiles["expansion_score"].to_numpy(dtype=float)
                        + churn_probs.to_numpy(dtype=float),
                        0.15,
                        None,
                    )
                ),
            )
            subscription_counts = extras + 1
        else:
            subscription_counts = np.zeros(account_count, dtype=int)
            picks = rng.choice(
                account_count,
                size=target,
                replace=False,
                p=_normalize(age_days.to_numpy(dtype=float)),
            )
            subscription_counts[picks] = 1
        billing_lookup = billing_profile.set_index("account_id")
        records: list[dict[str, object]] = []
        for index, profile in enumerate(profiles.itertuples(index=False)):
            signup_date = pd.Timestamp(profile.signup_date).date()
            churn_date = None
            if churned[index]:
                earliest = signup_date + timedelta(
                    days=self.config.lifecycle.minimum_tenure_days_before_churn
                )
                latest = max(earliest, self.as_of_date - timedelta(days=15))
                span = max(0, (latest - earliest).days)
                churn_date = earliest + timedelta(
                    days=int(rng.integers(0, span + 1)) if span else 0
                )
            records.append(
                {
                    "account_id": profile.account_id,
                    "subscription_count": int(subscription_counts[index]),
                    "churned": bool(churned[index]),
                    "churn_probability": round(float(churn_probs.iloc[index]), 4),
                    "churn_date": churn_date,
                    "preferred_billing_period": str(
                        billing_lookup.loc[
                            profile.account_id, "preferred_billing_period"
                        ]
                    ),
                    "incident_factor": round(
                        float(
                            1.0
                            + rng.binomial(
                                1, self.config.lifecycle.incident_burst_probability
                            )
                            * rng.uniform(0.3, 1.1)
                        ),
                        4,
                    ),
                }
            )
        scaffold = pd.DataFrame(records)
        if not scaffold.empty:
            scaffold["churn_date"] = _format_date_series(scaffold["churn_date"])
        return scaffold

    def _sample_billing_period(self, size_name: str, rng: np.random.Generator) -> str:
        weights = dict(self.config.billing.billing_period_weights)
        if size_name == "Enterprise":
            weights["annual"] = weights.get("annual", 0.0) * 1.40
            weights["quarterly"] = weights.get("quarterly", 0.0) * 1.15
            weights["monthly"] = weights.get("monthly", 0.0) * 0.85
        elif size_name == "SMB":
            weights["monthly"] = weights.get("monthly", 0.0) * 1.25
            weights["annual"] = weights.get("annual", 0.0) * 0.75
        values = np.array(
            [weights.get(name, 0.0) for name in ("monthly", "quarterly", "annual")],
            dtype=float,
        )
        return str(rng.choice(["monthly", "quarterly", "annual"], p=_normalize(values)))

    def _sample_plan_for_account(
        self, profile: pd.Series, rng: np.random.Generator
    ) -> str:
        base = np.array([plan.probability for plan in self.config.plans], dtype=float)
        size_segment = self.size_by_name[str(profile["company_size"])]
        industry = self.industry_by_name[str(profile["industry"])]
        for index, plan in enumerate(self.config.plans):
            base[index] *= size_segment.plan_bias.get(plan.name, 1.0)
            base[index] *= industry.plan_bias.get(plan.name, 1.0)
        if str(profile["company_size"]) == "Enterprise":
            base[-1] *= 1.45
        return str(rng.choice(self.plan_order, p=_normalize(base)))

    def _next_plan_name(
        self, current_plan: str, profile: pd.Series, rng: np.random.Generator
    ) -> str:
        current_rank = self.plan_rank[current_plan]
        score = float(profile["expansion_score"]) + rng.normal(0.0, 0.35)
        if score > 0.30 and current_rank < len(self.plan_order) - 1:
            return self.plan_order[current_rank + 1]
        if score < -0.45 and current_rank > 0:
            return self.plan_order[current_rank - 1]
        if (
            current_rank < len(self.plan_order) - 1
            and rng.random() < self.config.lifecycle.expansion_base_probability * 0.2
        ):
            return self.plan_order[current_rank + 1]
        return current_plan

    def _build_subscriptions(
        self, profiles: pd.DataFrame, scaffold: pd.DataFrame
    ) -> pd.DataFrame:
        rng = self._rng("subscriptions")
        lifecycle_by_account = scaffold.set_index("account_id")
        rows: list[dict[str, object]] = []
        for profile in profiles.to_dict(orient="records"):
            meta = lifecycle_by_account.loc[profile["account_id"]]
            count = int(meta["subscription_count"])
            if count <= 0:
                continue
            signup_date = pd.Timestamp(profile["signup_date"]).date()
            active_end = (
                pd.Timestamp(meta["churn_date"]).date()
                if pd.notna(meta["churn_date"])
                else self.as_of_date
            )
            total_window_days = max(0, (active_end - signup_date).days)
            max_anchor_shift = max(0, min(21, total_window_days - max(0, count - 1)))
            start_anchor = signup_date + timedelta(
                days=int(rng.integers(0, max_anchor_shift + 1))
                if max_anchor_shift
                else 0
            )
            available_days = max(0, (active_end - start_anchor).days)
            transition_starts: list[date] = []
            if count > 1 and available_days >= count - 1:
                base_offsets = np.linspace(1, available_days, num=count, endpoint=True)[
                    1:
                ]
                offsets: list[int] = []
                previous = 0
                for value in base_offsets:
                    remaining = count - 1 - len(offsets)
                    min_offset = previous + 1
                    max_offset = max(min_offset, available_days - remaining + 1)
                    candidate = int(round(float(value) + int(rng.integers(-3, 4))))
                    offset = min(max(candidate, min_offset), max_offset)
                    previous = offset
                    offsets.append(offset)
                transition_starts = [
                    start_anchor + timedelta(days=int(offset)) for offset in offsets
                ]
            current_plan = self._sample_plan_for_account(pd.Series(profile), rng)
            current_billing = str(meta["preferred_billing_period"])
            period_starts = [start_anchor] + transition_starts
            for period_index, period_start in enumerate(period_starts):
                if period_index > 0:
                    current_plan = self._next_plan_name(
                        current_plan, pd.Series(profile), rng
                    )
                    if rng.random() < 0.25:
                        current_billing = self._sample_billing_period(
                            str(profile["company_size"]), rng
                        )
                next_start = (
                    period_starts[period_index + 1]
                    if period_index + 1 < len(period_starts)
                    else None
                )
                end_date = (
                    (next_start - timedelta(days=1))
                    if next_start
                    else (active_end if bool(meta["churned"]) else None)
                )
                status = "ended"
                cancellation_reason = "plan_change"
                if period_index == len(period_starts) - 1:
                    if bool(meta["churned"]):
                        status = "cancelled"
                        cancellation_reason = str(
                            rng.choice(DEFAULT_CANCELLATION_REASONS)
                        )
                    elif (
                        float(profile["payment_reliability"]) < 0.58
                        and rng.random() < 0.16
                    ):
                        status = "past_due"
                        cancellation_reason = None
                    else:
                        status = "active"
                        cancellation_reason = None
                rows.append(
                    {
                        "subscription_id": self.id_factory.next_id("subscription_id"),
                        "account_id": profile["account_id"],
                        "plan_name": current_plan,
                        "billing_period": current_billing,
                        "start_date": period_start,
                        "end_date": end_date,
                        "monthly_amount": round(
                            float(self.plan_by_name[current_plan].monthly_price), 2
                        ),
                        "status": status,
                        "cancellation_reason": cancellation_reason,
                    }
                )
        subscriptions = pd.DataFrame(rows)
        subscriptions["start_date"] = _format_date_series(subscriptions["start_date"])
        subscriptions["end_date"] = _format_date_series(subscriptions["end_date"])
        return subscriptions

    def _build_account_month_state(
        self,
        profiles: pd.DataFrame,
        scaffold: pd.DataFrame,
        subscriptions: pd.DataFrame,
    ) -> pd.DataFrame:
        rng = self._rng("account_month_state")
        scaffold_by_account = scaffold.set_index("account_id")
        grouped_subscriptions = {
            account_id: group.sort_values("start_date").reset_index(drop=True)
            for account_id, group in subscriptions.groupby("account_id", sort=False)
        }
        rows: list[dict[str, object]] = []
        for profile in profiles.to_dict(orient="records"):
            meta = scaffold_by_account.loc[profile["account_id"]]
            active_end = (
                pd.Timestamp(meta["churn_date"]).date()
                if pd.notna(meta["churn_date"])
                else self.as_of_date
            )
            months = _month_starts(
                pd.Timestamp(profile["signup_date"]).date(), active_end
            )
            sub_rows = grouped_subscriptions.get(profile["account_id"], pd.DataFrame())
            for month_start in months:
                month_end = _month_end(month_start, self.as_of_date)
                months_since_signup = max(
                    0,
                    (
                        pd.Timestamp(month_start) - pd.Timestamp(profile["signup_date"])
                    ).days
                    // 30,
                )
                active_sub = None
                if not sub_rows.empty:
                    active_candidates = sub_rows[
                        (pd.to_datetime(sub_rows["start_date"]).dt.date <= month_end)
                        & (
                            pd.to_datetime(sub_rows["end_date"]).dt.date.fillna(
                                self.as_of_date
                            )
                            >= month_start
                        )
                    ]
                    if not active_candidates.empty:
                        active_sub = active_candidates.iloc[-1]
                plan_name = (
                    active_sub["plan_name"]
                    if active_sub is not None
                    else self.plan_order[0]
                )
                plan = self.plan_by_name[str(plan_name)]
                plan_rank = self.plan_rank[str(plan_name)]
                ramp = min(1.0, (months_since_signup + 1) / 4.0)
                seasonal = 1.0 + self.config.lifecycle.seasonal_strength * math.sin(
                    (month_start.month - 1) * math.tau / 12.0
                )
                near_churn_penalty = 0.0
                if bool(meta["churned"]) and pd.notna(meta["churn_date"]):
                    days_to_churn = (
                        pd.Timestamp(meta["churn_date"]).date() - month_start
                    ).days
                    if days_to_churn <= 75:
                        near_churn_penalty = 0.22
                health = float(
                    np.clip(
                        0.48
                        + 0.12 * ramp
                        + 0.08 * _logistic(float(profile["base_health"]))
                        + 0.05 * float(profile["industry_adoption_factor"])
                        + 0.04 * float(profile["retention_score"])
                        + 0.03 * plan_rank
                        - near_churn_penalty
                        + rng.normal(0.0, 0.06),
                        0.05,
                        0.98,
                    )
                )
                recent_change = False
                if active_sub is not None:
                    recent_change = (
                        month_start - pd.Timestamp(active_sub["start_date"]).date()
                    ).days <= 45
                if (
                    bool(meta["churned"])
                    and pd.notna(meta["churn_date"])
                    and month_start
                    >= pd.Timestamp(meta["churn_date"]).replace(day=1).date()
                ):
                    lifecycle_state = "churned"
                elif months_since_signup < self.config.lifecycle.new_account_months:
                    lifecycle_state = "new"
                elif recent_change and float(profile["expansion_score"]) > 0.2:
                    lifecycle_state = "expanding"
                elif health < 0.34:
                    lifecycle_state = "at-risk"
                elif health < 0.52:
                    lifecycle_state = "stagnant"
                else:
                    lifecycle_state = "active"
                state_event_factor = {
                    "new": 0.60,
                    "active": 1.00,
                    "expanding": 1.18,
                    "stagnant": 0.74,
                    "at-risk": 0.52,
                    "churned": 0.16,
                }[lifecycle_state]
                state_ticket_factor = {
                    "new": 1.20,
                    "active": 0.85,
                    "expanding": 0.95,
                    "stagnant": 1.10,
                    "at-risk": 1.45,
                    "churned": 0.60,
                }[lifecycle_state]
                size_segment = self.size_by_name[str(profile["company_size"])]
                active_users_estimate = int(
                    max(
                        1,
                        round(
                            float(profile["base_user_target"])
                            * ramp
                            * max(0.25, health)
                            * state_event_factor
                        ),
                    )
                )
                event_weight = max(
                    0.01,
                    size_segment.event_multiplier
                    * float(profile["industry_adoption_factor"])
                    * plan.usage_multiplier
                    * seasonal
                    * max(0.22, health)
                    * state_event_factor,
                )
                ticket_pressure = max(
                    0.05,
                    size_segment.support_multiplier
                    * float(profile["industry_support_factor"])
                    * plan.support_complexity
                    * max(0.25, 1.2 - health)
                    * state_ticket_factor
                    * float(meta["incident_factor"]),
                )
                nps_signal = float(
                    np.clip(
                        0.24
                        + 0.46 * health
                        + 0.05 * float(profile["payment_reliability"])
                        + 0.03 * float(profile["industry_nps_bias"])
                        - 0.03 * ticket_pressure
                        + rng.normal(0.0, 0.05),
                        0.0,
                        1.0,
                    )
                )
                rows.append(
                    {
                        "account_id": profile["account_id"],
                        "month_start": month_start,
                        "month_end": month_end,
                        "lifecycle_state": lifecycle_state,
                        "plan_name": str(plan_name),
                        "billing_period": active_sub["billing_period"]
                        if active_sub is not None
                        else str(meta["preferred_billing_period"]),
                        "health_score": round(health, 4),
                        "active_users_estimate": active_users_estimate,
                        "event_weight": round(float(event_weight), 6),
                        "ticket_pressure": round(float(ticket_pressure), 6),
                        "nps_signal": round(float(nps_signal), 6),
                        "utc_offset_hours": int(profile["utc_offset_hours"]),
                        "company_size": profile["company_size"],
                        "industry": profile["industry"],
                    }
                )
        state = pd.DataFrame(rows)
        if not state.empty:
            state["month_start"] = _format_date_series(state["month_start"])
            state["month_end"] = _format_date_series(state["month_end"])
        return state

    def _apply_latest_account_status(
        self, profiles: pd.DataFrame, account_month_state: pd.DataFrame
    ) -> pd.DataFrame:
        latest = (
            account_month_state.sort_values(["account_id", "month_start"])
            .groupby("account_id", as_index=False)
            .tail(1)[["account_id", "lifecycle_state"]]
            .rename(columns={"lifecycle_state": "status"})
        )
        merged = profiles.drop(columns=["status"]).merge(
            latest, on="account_id", how="left"
        )
        merged["status"] = merged["status"].fillna("new")
        return merged

    def _sample_user_roles(
        self, count: int, account_profile: pd.Series, rng: np.random.Generator
    ) -> list[str]:
        roles = [role.name for role in self.config.role_mix]
        weights = np.array([role.weight for role in self.config.role_mix], dtype=float)
        if account_profile["company_size"] == "SMB":
            for index, role in enumerate(roles):
                if "admin" in role or "billing" in role:
                    weights[index] *= 1.20
        if account_profile["company_size"] == "Enterprise":
            for index, role in enumerate(roles):
                if "manager" in role or "integration" in role:
                    weights[index] *= 1.20
        picks = rng.choice(roles, size=count, p=_normalize(weights))
        role_list = [str(role) for role in picks]
        if count > 0 and "admin" in self.role_by_name:
            role_list[0] = "admin"
        return role_list

    def _build_users(
        self, profiles: pd.DataFrame, account_month_state: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        rng = self._rng("users")
        latest_status = profiles.set_index("account_id")["status"]
        status_factor = latest_status.map(
            {
                "new": 0.70,
                "active": 1.0,
                "expanding": 1.15,
                "stagnant": 0.75,
                "at-risk": 0.55,
                "churned": 0.25,
            }
        ).fillna(0.75)
        weights = profiles["base_user_target"].to_numpy(
            dtype=float
        ) * status_factor.to_numpy(dtype=float)
        minimums = (
            np.ones(len(profiles), dtype=int)
            if self.config.row_targets.users >= len(profiles)
            else np.zeros(len(profiles), dtype=int)
        )
        counts = _allocate_total(
            self.config.row_targets.users, weights=weights, minimums=minimums
        )
        users_rows: list[dict[str, object]] = []
        users_internal_rows: list[dict[str, object]] = []
        active_end_by_account = (
            account_month_state.groupby("account_id")["month_end"].max().to_dict()
        )
        for index, profile in enumerate(profiles.to_dict(orient="records")):
            account_id = profile["account_id"]
            user_count = int(counts[index])
            if user_count <= 0:
                continue
            roles = self._sample_user_roles(user_count, pd.Series(profile), rng)
            signup_date = pd.Timestamp(profile["signup_date"]).date()
            active_end = active_end_by_account.get(account_id, self.as_of_date)
            for user_index in range(user_count):
                role_name = roles[user_index]
                role = self.role_by_name[role_name]
                first = self.faker.first_name()
                last = self.faker.last_name()
                local = f"{first}.{last}.{user_index + 1}".lower().replace(" ", "")
                local = "".join(ch for ch in local if ch.isalnum() or ch == ".")
                email = f"{local}@{profile['domain']}"
                if user_index == 0:
                    create_date = signup_date
                else:
                    create_date = _sample_dates_between(
                        signup_date,
                        max(signup_date, min(active_end, self.as_of_date)),
                        1,
                        rng,
                    )[0]
                base_active_probability = {
                    "new": 0.86,
                    "active": 0.92,
                    "expanding": 0.95,
                    "stagnant": 0.72,
                    "at-risk": 0.58,
                    "churned": 0.16,
                }[str(profile["status"])]
                is_active = bool(
                    rng.random()
                    < np.clip(
                        base_active_probability
                        * (0.78 + role.activity_multiplier * 0.18),
                        0.05,
                        0.99,
                    )
                )
                last_login_at = None
                if is_active or rng.random() < 0.42:
                    anchor = min(self.as_of_date, active_end + timedelta(days=30))
                    lag_days = int(
                        rng.exponential(
                            max(
                                1.0,
                                role.login_half_life_days
                                / max(0.4, float(profile["base_health"]) + 1.2),
                            )
                        )
                    )
                    login_date = max(create_date, anchor - timedelta(days=lag_days))
                    last_login_at = min(
                        datetime.combine(
                            login_date,
                            time(
                                hour=int(rng.integers(6, 22)),
                                minute=int(rng.integers(0, 60)),
                                second=int(rng.integers(0, 60)),
                            ),
                        ),
                        datetime.combine(self.as_of_date, time(23, 59, 59)),
                    )
                user_id = self.id_factory.next_id("user_id")
                exported = {
                    "user_id": user_id,
                    "account_id": account_id,
                    "email": email,
                    "role": role_name,
                    "last_login_at": last_login_at,
                    "is_active": is_active,
                }
                users_rows.append(exported)
                users_internal_rows.append(
                    {
                        **exported,
                        "user_created_at": create_date,
                        "activity_multiplier": role.activity_multiplier,
                        "utc_offset_hours": profile["utc_offset_hours"],
                    }
                )
        users = pd.DataFrame(users_rows)
        users_internal = pd.DataFrame(users_internal_rows)
        return users, users_internal

    def _build_activity_budget(
        self, account_month_state: pd.DataFrame, users_internal: pd.DataFrame
    ) -> pd.DataFrame:
        state = account_month_state.copy()
        user_counts = users_internal.groupby("account_id")["user_id"].count()
        state["user_count"] = state["account_id"].map(user_counts).fillna(0).astype(int)
        state = state.loc[state["user_count"] > 0].copy()
        weights = state["event_weight"].to_numpy(dtype=float) * np.maximum(
            1.0, state["user_count"].to_numpy(dtype=float)
        )
        state["target_events"] = _allocate_total(
            self.config.row_targets.product_events, weights=weights
        )
        ranks = state["plan_name"].map(self.plan_rank).fillna(0).astype(int)
        norm_rank = ranks / max(1, len(self.plan_order) - 1)
        state["core_share"] = np.clip(0.58 - norm_rank * 0.10, 0.28, 0.70)
        state["advanced_share"] = np.clip(0.14 + norm_rank * 0.12, 0.08, 0.34)
        state["admin_share"] = np.clip(
            0.16 + (state["company_size"] == "Enterprise").astype(float) * 0.05,
            0.10,
            0.28,
        )
        remainder = 1.0 - (
            state["core_share"] + state["advanced_share"] + state["admin_share"]
        )
        state["integration_share"] = np.clip(remainder, 0.06, 0.38)
        total_shares = state[
            ["core_share", "advanced_share", "admin_share", "integration_share"]
        ].sum(axis=1)
        for column in [
            "core_share",
            "advanced_share",
            "admin_share",
            "integration_share",
        ]:
            state[column] = state[column] / total_shares
        return state

    def _build_invoices(
        self,
        profiles: pd.DataFrame,
        subscriptions: pd.DataFrame,
        account_month_state: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        rng = self._rng("invoices")
        currency_by_account = profiles.set_index("account_id")["currency"].to_dict()
        state_lookup = account_month_state.set_index(["account_id", "month_start"])
        rows: list[dict[str, object]] = []
        internal_rows: list[dict[str, object]] = []
        cadence_months = {"monthly": 1, "quarterly": 3, "annual": 12}
        for subscription in subscriptions.to_dict(orient="records"):
            start_date = pd.Timestamp(subscription["start_date"]).date()
            end_date = (
                pd.Timestamp(subscription["end_date"]).date()
                if pd.notna(subscription["end_date"])
                else self.as_of_date
            )
            cadence = cadence_months[str(subscription["billing_period"])]
            cursor = pd.Timestamp(start_date).replace(day=1).date()
            while cursor <= end_date:
                month_state = None
                try:
                    month_state = state_lookup.loc[(subscription["account_id"], cursor)]
                except KeyError:
                    pass
                payment_reliability = float(
                    profiles.loc[
                        profiles["account_id"] == subscription["account_id"],
                        "payment_reliability",
                    ].iloc[0]
                )
                amount_due = round(float(subscription["monthly_amount"]) * cadence, 2)
                draw = rng.random()
                paid_cutoff = payment_reliability * self.config.billing.paid_probability
                partial_cutoff = (
                    paid_cutoff + self.config.billing.partial_payment_probability
                )
                overdue_cutoff = (
                    partial_cutoff + self.config.billing.overdue_probability
                )
                if draw < paid_cutoff:
                    status = "paid"
                    amount_paid = amount_due
                elif draw < partial_cutoff:
                    status = "partially_paid"
                    amount_paid = round(amount_due * float(rng.uniform(0.35, 0.95)), 2)
                elif draw < overdue_cutoff:
                    status = "overdue"
                    amount_paid = round(amount_due * float(rng.uniform(0.0, 0.25)), 2)
                else:
                    status = "void"
                    amount_paid = 0.0
                invoice_id = self.id_factory.next_id("invoice_id")
                exported = {
                    "invoice_id": invoice_id,
                    "account_id": subscription["account_id"],
                    "invoice_date": max(start_date, cursor),
                    "amount_due": amount_due,
                    "amount_paid": amount_paid,
                    "currency": currency_by_account[subscription["account_id"]],
                    "status": status,
                }
                rows.append(exported)
                internal_rows.append(
                    {
                        **exported,
                        "subscription_id": subscription["subscription_id"],
                        "subscription_start_date": subscription["start_date"],
                        "subscription_end_date": subscription["end_date"],
                        "health_score": float(month_state["health_score"])
                        if month_state is not None
                        and not isinstance(month_state, pd.DataFrame)
                        else 0.64,
                    }
                )
                cursor = (pd.Timestamp(cursor) + pd.DateOffset(months=cadence)).date()
        invoices = pd.DataFrame(rows)
        internal = pd.DataFrame(internal_rows)
        target = self.config.row_targets.invoices
        if len(invoices) > target > 0:
            weights = (
                pd.to_datetime(invoices["invoice_date"])
                .astype("int64")
                .to_numpy(dtype=float)
            )
            keep = np.sort(
                rng.choice(
                    len(invoices), size=target, replace=False, p=_normalize(weights)
                )
            )
            invoices = invoices.iloc[keep].reset_index(drop=True)
            internal = internal.iloc[keep].reset_index(drop=True)
        if not invoices.empty:
            invoices["invoice_date"] = _format_date_series(invoices["invoice_date"])
            internal["invoice_date"] = _format_date_series(internal["invoice_date"])
            internal["subscription_start_date"] = _format_date_series(
                internal["subscription_start_date"]
            )
            internal["subscription_end_date"] = _format_date_series(
                internal["subscription_end_date"]
            )
        return invoices, internal

    def _sample_ticket_category(
        self, lifecycle_state: str, rng: np.random.Generator
    ) -> str:
        categories = np.array(
            [
                "onboarding",
                "billing",
                "bug",
                "integration",
                "permissions",
                "reporting",
                "feature_request",
            ],
            dtype=object,
        )
        weights = np.array([0.12, 0.15, 0.23, 0.14, 0.10, 0.14, 0.12], dtype=float)
        if lifecycle_state == "new":
            weights *= np.array([1.8, 0.9, 0.7, 1.0, 0.9, 1.1, 0.7])
        elif lifecycle_state in {"at-risk", "churned"}:
            weights *= np.array([0.6, 1.4, 1.35, 1.1, 1.0, 0.8, 0.7])
        return str(rng.choice(categories, p=_normalize(weights)))

    def _build_support_tickets(
        self, profiles: pd.DataFrame, account_month_state: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        rng = self._rng("support_tickets")
        counts = _allocate_total(
            self.config.row_targets.support_tickets,
            weights=account_month_state["ticket_pressure"].to_numpy(dtype=float),
        )
        rows: list[dict[str, object]] = []
        internal_rows: list[dict[str, object]] = []
        for record, ticket_count in zip(
            account_month_state.to_dict(orient="records"), counts.tolist(), strict=False
        ):
            for _ in range(int(ticket_count)):
                category = self._sample_ticket_category(
                    str(record["lifecycle_state"]), rng
                )
                priority_weights = {
                    "billing": np.array([0.18, 0.36, 0.32, 0.14]),
                    "bug": np.array([0.10, 0.30, 0.40, 0.20]),
                    "integration": np.array([0.12, 0.33, 0.36, 0.19]),
                }.get(category, np.array([0.28, 0.38, 0.24, 0.10]))
                priority = str(
                    rng.choice(
                        ["low", "medium", "high", "urgent"],
                        p=_normalize(priority_weights),
                    )
                )
                status = str(
                    rng.choice(
                        ["resolved", "closed", "pending", "open"],
                        p=[0.52, 0.20, 0.16, 0.12],
                    )
                )
                resolution_base = {
                    "low": 240,
                    "medium": 720,
                    "high": 1_440,
                    "urgent": 3_600,
                }[priority]
                resolution_minutes = int(
                    max(5, round(rng.lognormal(math.log(resolution_base), 0.55)))
                )
                satisfaction = None
                if status in {"resolved", "closed"}:
                    score = 4.2 - record["ticket_pressure"] * 0.7 + rng.normal(0.0, 0.8)
                    satisfaction = int(np.clip(round(score), 1, 5))
                opened_at = datetime.combine(
                    _sample_dates_between(
                        pd.Timestamp(record["month_start"]).date(),
                        pd.Timestamp(record["month_end"]).date(),
                        1,
                        rng,
                    )[0],
                    time(
                        hour=int(rng.integers(8, 19)), minute=int(rng.integers(0, 60))
                    ),
                )
                closed_at = opened_at + timedelta(minutes=resolution_minutes)
                ticket_id = self.id_factory.next_id("ticket_id")
                exported = {
                    "ticket_id": ticket_id,
                    "account_id": record["account_id"],
                    "category": category,
                    "priority": priority,
                    "status": status,
                    "satisfaction_rating": satisfaction,
                    "resolution_minutes": resolution_minutes,
                }
                rows.append(exported)
                internal_rows.append(
                    {
                        **exported,
                        "opened_at": opened_at,
                        "closed_at": closed_at,
                        "month_start": record["month_start"],
                    }
                )
        return pd.DataFrame(rows), pd.DataFrame(internal_rows)

    def _build_nps_responses(
        self, profiles: pd.DataFrame, account_month_state: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        rng = self._rng("nps")
        state_lookup = {
            (row.account_id, row.month_start): row
            for row in account_month_state.itertuples(index=False)
        }
        candidates: list[dict[str, object]] = []
        for profile in profiles.to_dict(orient="records"):
            signup = pd.Timestamp(profile["signup_date"]).date()
            first_survey = signup + timedelta(days=90)
            if first_survey > self.as_of_date:
                continue
            cursor = first_survey + timedelta(days=int(rng.integers(0, 35)))
            while cursor <= self.as_of_date:
                month_key = pd.Timestamp(cursor).replace(day=1).date()
                state = state_lookup.get((profile["account_id"], month_key))
                if state is not None and state.lifecycle_state != "churned":
                    candidates.append(
                        {
                            "account_id": profile["account_id"],
                            "survey_date": cursor,
                            "nps_signal": float(state.nps_signal),
                            "weight": max(0.05, float(state.nps_signal) + 0.20),
                        }
                    )
                cursor = cursor + timedelta(days=int(rng.integers(110, 181)))
        if not candidates:
            return pd.DataFrame(
                columns=EXPORTED_COLUMNS["nps_responses"]
            ), pd.DataFrame()
        candidate_df = pd.DataFrame(candidates)
        target = min(self.config.row_targets.nps_responses, len(candidate_df))
        indices = rng.choice(
            len(candidate_df),
            size=target,
            replace=False,
            p=_normalize(candidate_df["weight"].to_numpy(dtype=float)),
        )
        selected = candidate_df.iloc[np.sort(indices)].copy().reset_index(drop=True)
        selected["response_id"] = [
            self.id_factory.next_id("response_id") for _ in range(len(selected))
        ]
        selected["score"] = [
            int(np.clip(round(2.0 + 8.0 * float(signal) + rng.normal(0.0, 1.7)), 0, 10))
            for signal in selected["nps_signal"].tolist()
        ]
        selected["survey_date"] = _format_date_series(selected["survey_date"])
        return selected[EXPORTED_COLUMNS["nps_responses"]].copy(), selected

    def _sample_event_payload(
        self, plan_name: str, size: int, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        plan_rank = self.plan_rank[plan_name]
        eligible: list[EventTypeConfig] = []
        weights: list[float] = []
        for event in self.config.event_taxonomy:
            if (
                event.min_plan is not None
                and self.plan_rank[event.min_plan] > plan_rank
            ):
                continue
            eligible.append(event)
            weights.append(event.weight)
        picks = rng.choice(
            len(eligible), size=size, p=_normalize(np.array(weights, dtype=float))
        )
        event_names = np.empty(size, dtype=object)
        categories = np.empty(size, dtype=object)
        platforms = np.empty(size, dtype=object)
        for event_index in np.unique(picks):
            mask = picks == event_index
            event = eligible[int(event_index)]
            event_names[mask] = event.name
            categories[mask] = event.feature_category
            platform_names = list(event.platform_weights)
            platform_weights = np.array(
                list(event.platform_weights.values()), dtype=float
            )
            platforms[mask] = rng.choice(
                platform_names, size=int(mask.sum()), p=_normalize(platform_weights)
            )
        return event_names, categories, platforms

    def _sample_event_timestamps(
        self,
        start_date: date,
        end_date: date,
        utc_offset_hours: int,
        size: int,
        rng: np.random.Generator,
    ) -> pd.Series:
        days = pd.date_range(start=start_date, end=end_date, freq="D")
        day_weights = np.array(
            [1.15 if day.weekday() < 5 else 0.35 for day in days], dtype=float
        )
        selected_days = days[
            rng.choice(len(days), size=size, p=_normalize(day_weights))
        ]
        business_draw = rng.random(size)
        local_hours = np.where(
            business_draw < 0.78,
            rng.integers(7, 19, size=size),
            np.where(
                business_draw < 0.94,
                rng.integers(19, 23, size=size),
                rng.integers(0, 7, size=size),
            ),
        )
        minutes = rng.integers(0, 60, size=size)
        seconds = rng.integers(0, 60, size=size)
        local_ts = (
            pd.to_datetime(selected_days.date)
            + pd.to_timedelta(local_hours, unit="h")
            + pd.to_timedelta(minutes, unit="m")
            + pd.to_timedelta(seconds, unit="s")
        )
        return pd.Series(local_ts - pd.to_timedelta(utc_offset_hours, unit="h"))

    def _build_product_events(
        self, activity_budget: pd.DataFrame, users_internal: pd.DataFrame
    ) -> list[pd.DataFrame]:
        rng = self._rng("product_events")
        users_by_account = {
            account_id: group.sort_values("user_created_at").reset_index(drop=True)
            for account_id, group in users_internal.groupby("account_id", sort=False)
        }
        batches: list[pd.DataFrame] = []
        for _, month_rows in activity_budget.groupby("month_start", sort=True):
            month_frames: list[pd.DataFrame] = []
            for record in month_rows.to_dict(orient="records"):
                event_count = int(record["target_events"])
                if event_count <= 0:
                    continue
                users = users_by_account.get(record["account_id"])
                if users is None or users.empty:
                    continue
                month_end = pd.Timestamp(record["month_end"]).date()
                eligible_users = users.loc[
                    pd.to_datetime(users["user_created_at"]).dt.date <= month_end
                ].copy()
                if eligible_users.empty:
                    continue
                weights = eligible_users["activity_multiplier"].to_numpy(
                    dtype=float
                ) * np.where(eligible_users["is_active"], 1.25, 0.35)
                selected_users = eligible_users.iloc[
                    rng.choice(
                        len(eligible_users),
                        size=event_count,
                        replace=True,
                        p=_normalize(weights),
                    )
                ].reset_index(drop=True)
                event_names, categories, platforms = self._sample_event_payload(
                    str(record["plan_name"]), event_count, rng
                )
                timestamps = self._sample_event_timestamps(
                    pd.Timestamp(record["month_start"]).date(),
                    month_end,
                    int(record["utc_offset_hours"]),
                    event_count,
                    rng,
                )
                timestamps = pd.Series(
                    np.maximum(
                        timestamps.to_numpy(dtype="datetime64[ns]"),
                        pd.to_datetime(selected_users["user_created_at"]).to_numpy(
                            dtype="datetime64[ns]"
                        ),
                    )
                )
                month_frames.append(
                    pd.DataFrame(
                        {
                            "event_id": self.id_factory.next_ids(
                                "event_id", event_count
                            ),
                            "account_id": record["account_id"],
                            "user_id": selected_users["user_id"].to_numpy(),
                            "event_name": event_names,
                            "event_timestamp": timestamps.to_numpy(),
                            "feature_category": categories,
                            "platform": platforms,
                        }
                    )
                )
            if month_frames:
                batches.append(pd.concat(month_frames, ignore_index=True))
        return batches
