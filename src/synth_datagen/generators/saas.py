"""
SaaS scenario generator.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterator

import numpy as np
import pandas as pd
from faker import Faker

from ..config import ColumnConfig, DType, GeneratorConfig, RelationConfig, TableConfig
from ..id_utils import make_id_list
from ..schema_builder import SchemaGraph
from ..utils import (
    add_months,
    bounded_lognormal,
    datetime_range_samples,
    stable_uuid,
    weighted_choice,
)
from .base import BaseScenarioGenerator

_PLANS = ["free", "starter", "growth", "professional", "enterprise"]
_PLAN_W = [0.24, 0.28, 0.24, 0.16, 0.08]
_PLAN_PRICE = {
    "free": 0.0,
    "starter": 29.0,
    "growth": 79.0,
    "professional": 199.0,
    "enterprise": 499.0,
}
_PLAN_RANK = {plan: idx for idx, plan in enumerate(_PLANS)}

_SUB_STATUSES = ["active", "cancelled", "past_due", "trialing", "paused"]
_SUB_STATUS_W = [0.66, 0.10, 0.09, 0.09, 0.06]

_EVENT_TYPES = [
    "login",
    "page_view",
    "feature_click",
    "export",
    "invite_sent",
    "api_call",
    "settings_change",
    "logout",
]
_EVENT_W = [0.22, 0.34, 0.16, 0.05, 0.04, 0.12, 0.04, 0.03]

_INV_STATUSES = ["paid", "pending", "overdue", "voided"]
_INV_STATUS_W = [0.78, 0.10, 0.09, 0.03]

_SIM_START = datetime(2021, 1, 1)
_AS_OF = datetime(2025, 12, 31, 23, 59, 59)


class SaasGenerator(BaseScenarioGenerator):
    def __init__(
        self, config: GeneratorConfig, rng: np.random.Generator, faker: Faker
    ) -> None:
        super().__init__(config, rng, faker)
        self._cache: dict[str, pd.DataFrame] | None = None

    def get_raw_schema(self) -> tuple[list[TableConfig], list[RelationConfig]]:
        ov = self.config.row_overrides
        tables = [
            TableConfig(
                name="accounts",
                row_count=ov.get("accounts", 5_000),
                pk_column="account_id",
                columns=[
                    ColumnConfig(
                        name="account_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(
                        name="company_name",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        max_length=160,
                    ),
                    ColumnConfig(
                        name="domain", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(
                        name="industry",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        max_length=80,
                    ),
                    ColumnConfig(name="employee_count", dtype=DType.INT, nullable=True),
                    ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="created_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(name="mrr", dtype=DType.DECIMAL, nullable=True),
                ],
            ),
            TableConfig(
                name="users",
                row_count=ov.get("users", 25_000),
                pk_column="user_id",
                columns=[
                    ColumnConfig(
                        name="user_id", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(
                        name="account_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(
                        name="email", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(name="role", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="created_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(
                        name="last_login", dtype=DType.TIMESTAMP, nullable=True
                    ),
                    ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="subscriptions",
                row_count=ov.get("subscriptions", 6_000),
                pk_column="sub_id",
                columns=[
                    ColumnConfig(
                        name="sub_id", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(
                        name="account_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="plan", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="mrr", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(
                        name="started_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(name="ended_at", dtype=DType.TIMESTAMP, nullable=True),
                    ColumnConfig(
                        name="billing_cycle", dtype=DType.VARCHAR, nullable=False
                    ),
                ],
            ),
            TableConfig(
                name="invoices",
                row_count=ov.get("invoices", 20_000),
                pk_column="invoice_id",
                columns=[
                    ColumnConfig(
                        name="invoice_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(
                        name="account_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="sub_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="amount", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(name="currency", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="issued_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(name="due_at", dtype=DType.TIMESTAMP, nullable=False),
                    ColumnConfig(name="paid_at", dtype=DType.TIMESTAMP, nullable=True),
                ],
            ),
            TableConfig(
                name="features",
                row_count=ov.get("features", 50),
                pk_column="feature_id",
                allow_duplicate_injection=False,
                columns=[
                    ColumnConfig(
                        name="feature_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(
                        name="name", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(name="category", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="plan_min", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="is_beta", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="feature_usage",
                row_count=ov.get("feature_usage", 150_000),
                pk_column="usage_id",
                columns=[
                    ColumnConfig(
                        name="usage_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(name="user_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="feature_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="used_at", dtype=DType.TIMESTAMP, nullable=False),
                    ColumnConfig(name="duration_s", dtype=DType.INT, nullable=True),
                ],
            ),
            TableConfig(
                name="events",
                row_count=ov.get("events", 500_000),
                pk_column="event_id",
                columns=[
                    ColumnConfig(
                        name="event_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(name="user_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="event_type", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(
                        name="occurred_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(name="session_id", dtype=DType.VARCHAR, nullable=True),
                    ColumnConfig(name="ip_address", dtype=DType.VARCHAR, nullable=True),
                ],
            ),
        ]
        relations = [
            RelationConfig(
                source_table="users",
                source_column="account_id",
                target_table="accounts",
                target_column="account_id",
            ),
            RelationConfig(
                source_table="subscriptions",
                source_column="account_id",
                target_table="accounts",
                target_column="account_id",
            ),
            RelationConfig(
                source_table="invoices",
                source_column="account_id",
                target_table="accounts",
                target_column="account_id",
            ),
            RelationConfig(
                source_table="invoices",
                source_column="sub_id",
                target_table="subscriptions",
                target_column="sub_id",
            ),
            RelationConfig(
                source_table="feature_usage",
                source_column="user_id",
                target_table="users",
                target_column="user_id",
            ),
            RelationConfig(
                source_table="feature_usage",
                source_column="feature_id",
                target_table="features",
                target_column="feature_id",
            ),
            RelationConfig(
                source_table="events",
                source_column="user_id",
                target_table="users",
                target_column="user_id",
            ),
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
        accounts = self._build_accounts(counts["accounts"])
        subscriptions = self._build_subscriptions(counts["subscriptions"], accounts)
        account_mrr = (
            subscriptions.loc[
                subscriptions["status"].isin(
                    ["active", "past_due", "trialing", "paused"]
                )
            ]
            .groupby("account_id")["mrr"]
            .sum()
        )
        accounts["mrr"] = accounts["account_id"].map(account_mrr).fillna(0.0).round(2)
        users = self._build_users(counts["users"], accounts)
        features = self._build_features(counts["features"])
        invoices = self._build_invoices(counts["invoices"], subscriptions)
        feature_usage = self._build_feature_usage(
            counts["feature_usage"], users, features, subscriptions
        )
        events = self._build_events(counts["events"], users)
        return {
            "accounts": accounts,
            "users": users,
            "subscriptions": subscriptions,
            "invoices": invoices,
            "features": features,
            "feature_usage": feature_usage,
            "events": events,
        }

    def _build_accounts(self, row_count: int) -> pd.DataFrame:
        industries = [
            "SaaS",
            "Fintech",
            "Healthcare",
            "Retail",
            "Media",
            "Education",
            "Logistics",
            "Manufacturing",
        ]
        company_names = [self.faker.company() for _ in range(row_count)]
        return pd.DataFrame(
            {
                "account_id": make_id_list("account_id", 1, row_count),
                "company_name": company_names,
                "domain": [
                    f"{self.faker.domain_word()}-{idx + 1}.io"
                    for idx in range(row_count)
                ],
                "industry": [
                    str(self.rng.choice(industries)) for _ in range(row_count)
                ],
                "employee_count": np.round(
                    bounded_lognormal(3.8, 1.1, 5, 5_000, row_count, self.rng)
                ).astype(int),
                "country": weighted_choice(
                    [
                        "United States",
                        "United Kingdom",
                        "Germany",
                        "Canada",
                        "Australia",
                        "Netherlands",
                    ],
                    [0.40, 0.14, 0.16, 0.10, 0.10, 0.10],
                    row_count,
                    self.rng,
                ).tolist(),
                "created_at": pd.to_datetime(
                    datetime_range_samples(
                        _SIM_START, datetime(2025, 9, 30), row_count, self.rng
                    )
                ),
                "mrr": np.zeros(row_count),
            }
        )

    def _build_subscriptions(
        self, row_count: int, accounts: pd.DataFrame
    ) -> pd.DataFrame:
        account_ids = accounts["account_id"].tolist()
        counts = np.zeros(len(accounts), dtype=int)
        if row_count >= len(accounts):
            counts[:] = 1
            extra = row_count - len(accounts)
            if extra > 0:
                extra_picks = self.rng.integers(0, len(accounts), size=extra)
                for idx in extra_picks:
                    counts[int(idx)] += 1
        else:
            chosen = self.rng.choice(len(accounts), size=row_count, replace=False)
            counts[chosen] = 1

        records: list[dict[str, object]] = []
        seq = 1
        for idx, sub_count in enumerate(counts):
            if sub_count == 0:
                continue
            account = accounts.iloc[idx]
            timeline_start = pd.Timestamp(
                account["created_at"]
            ).to_pydatetime() + timedelta(days=int(self.rng.integers(0, 45)))
            for sub_idx in range(int(sub_count)):
                remaining_window_end = _AS_OF - timedelta(days=60)
                if timeline_start > remaining_window_end:
                    timeline_start = remaining_window_end
                plan = str(weighted_choice(_PLANS, _PLAN_W, 1, self.rng)[0])
                billing_cycle = str(
                    weighted_choice(["monthly", "annual"], [0.72, 0.28], 1, self.rng)[0]
                )
                seats_factor = max(1.0, float(account["employee_count"]) / 80.0)
                mrr = round(
                    _PLAN_PRICE[plan]
                    * (1.0 if plan == "free" else min(seats_factor, 20.0)),
                    2,
                )
                if sub_idx < sub_count - 1:
                    duration_months = int(self.rng.integers(6, 20))
                    ended_at = min(
                        add_months(timeline_start, duration_months),
                        _AS_OF - timedelta(days=30),
                    )
                    status = "cancelled"
                else:
                    status = str(
                        weighted_choice(_SUB_STATUSES, _SUB_STATUS_W, 1, self.rng)[0]
                    )
                    ended_at = None
                    if status == "cancelled":
                        ended_at = min(
                            add_months(timeline_start, int(self.rng.integers(2, 18))),
                            _AS_OF,
                        )
                records.append(
                    {
                        "sub_id": make_id_list("sub_id", seq, 1)[0],
                        "account_id": account_ids[idx],
                        "plan": plan,
                        "status": status,
                        "mrr": mrr,
                        "started_at": timeline_start,
                        "ended_at": ended_at,
                        "billing_cycle": billing_cycle,
                    }
                )
                seq += 1
                timeline_start = (ended_at or _AS_OF) + timedelta(
                    days=int(self.rng.integers(3, 45))
                )
        return pd.DataFrame(records)

    def _build_users(self, row_count: int, accounts: pd.DataFrame) -> pd.DataFrame:
        weights = np.sqrt(accounts["employee_count"].to_numpy(dtype=float))
        weights = weights / weights.sum()
        account_idx = self.rng.choice(len(accounts), size=row_count, p=weights)
        roles = ["owner", "admin", "member", "viewer", "billing"]
        role_w = [0.05, 0.15, 0.52, 0.18, 0.10]
        records: list[dict[str, object]] = []
        for idx in range(row_count):
            account = accounts.iloc[int(account_idx[idx])]
            created_at = datetime_range_samples(
                pd.Timestamp(account["created_at"]).to_pydatetime(), _AS_OF, 1, self.rng
            )[0]
            is_active = bool(self.rng.random() > 0.12)
            last_login = None
            if is_active or self.rng.random() > 0.25:
                last_login = datetime_range_samples(created_at, _AS_OF, 1, self.rng)[0]
            local = f"{self.faker.first_name().lower()}.{self.faker.last_name().lower()}.{idx + 1:05d}"
            records.append(
                {
                    "user_id": make_id_list("user_id", idx + 1, 1)[0],
                    "account_id": str(account["account_id"]),
                    "email": f"{local}@{account['domain']}",
                    "role": str(weighted_choice(roles, role_w, 1, self.rng)[0]),
                    "created_at": created_at,
                    "last_login": last_login,
                    "is_active": is_active,
                }
            )
        return pd.DataFrame(records)

    def _build_features(self, row_count: int) -> pd.DataFrame:
        base_names = [
            "Dashboard",
            "Reports",
            "API Access",
            "Export CSV",
            "Webhooks",
            "SSO",
            "Custom Roles",
            "Audit Log",
            "2FA",
            "White Label",
            "Data Import",
            "Integrations",
            "Custom Domain",
            "Priority Support",
            "SLA Guarantee",
            "Analytics",
            "Collaboration",
            "Version History",
            "Backups",
            "Advanced Search",
            "Bulk Actions",
            "Team Management",
            "Custom Alerts",
            "Mobile App",
            "CLI Tool",
            "SDK Access",
            "Sandbox Environment",
            "Usage Reports",
            "Billing Portal",
            "Multi Currency",
        ]
        while len(base_names) < row_count:
            base_names.append(f"Generated Feature {len(base_names) + 1:03d}")
        categories = ["Core", "Analytics", "Security", "Integration", "Admin"]
        return pd.DataFrame(
            {
                "feature_id": make_id_list("feature_id", 1, row_count),
                "name": base_names[:row_count],
                "category": [
                    str(self.rng.choice(categories)) for _ in range(row_count)
                ],
                "plan_min": weighted_choice(
                    _PLANS, [0.20, 0.24, 0.24, 0.20, 0.12], row_count, self.rng
                ).tolist(),
                "is_beta": self.rng.random(row_count) < 0.12,
            }
        )

    def _build_invoices(
        self, row_count: int, subscriptions: pd.DataFrame
    ) -> pd.DataFrame:
        candidates: list[dict[str, object]] = []
        for sub in subscriptions.itertuples(index=False):
            started_at = pd.Timestamp(sub.started_at).to_pydatetime()
            ended_at = (
                pd.Timestamp(sub.ended_at).to_pydatetime()
                if pd.notna(sub.ended_at)
                else _AS_OF
            )
            step_months = 12 if sub.billing_cycle == "annual" else 1
            amount = round(float(sub.mrr) * step_months, 2)
            issued_at = started_at
            while issued_at <= ended_at:
                due_at = issued_at + timedelta(days=30)
                if due_at < _AS_OF - timedelta(days=45):
                    status = str(
                        weighted_choice(_INV_STATUSES, _INV_STATUS_W, 1, self.rng)[0]
                    )
                else:
                    status = str(
                        weighted_choice(
                            ["paid", "pending", "overdue"],
                            [0.72, 0.22, 0.06],
                            1,
                            self.rng,
                        )[0]
                    )
                paid_at = None
                if status == "paid":
                    paid_at = datetime_range_samples(
                        issued_at, min(due_at, _AS_OF), 1, self.rng
                    )[0]
                candidates.append(
                    {
                        "account_id": str(sub.account_id),
                        "sub_id": str(sub.sub_id),
                        "amount": amount,
                        "currency": "USD",
                        "status": status,
                        "issued_at": issued_at,
                        "due_at": due_at,
                        "paid_at": paid_at,
                    }
                )
                issued_at = add_months(issued_at, step_months)
        if len(candidates) >= row_count:
            indices = self.rng.choice(len(candidates), size=row_count, replace=False)
            rows = [candidates[int(idx)] for idx in sorted(indices)]
        else:
            rows = list(candidates)
            while len(rows) < row_count and candidates:
                seed = dict(candidates[len(rows) % len(candidates)])
                seed["issued_at"] = min(
                    pd.Timestamp(seed["issued_at"]).to_pydatetime() + timedelta(days=7),
                    _AS_OF,
                )
                seed["due_at"] = min(
                    pd.Timestamp(seed["due_at"]).to_pydatetime() + timedelta(days=7),
                    _AS_OF + timedelta(days=30),
                )
                seed["status"] = "pending"
                seed["paid_at"] = None
                rows.append(seed)
        for idx, row in enumerate(rows, start=1):
            row["invoice_id"] = make_id_list("invoice_id", idx, 1)[0]
        return pd.DataFrame(rows)

    def _active_plan_intervals(
        self, subscriptions: pd.DataFrame
    ) -> dict[str, list[tuple[datetime, datetime, str]]]:
        intervals: dict[str, list[tuple[datetime, datetime, str]]] = defaultdict(list)
        for sub in subscriptions.itertuples(index=False):
            start = pd.Timestamp(sub.started_at).to_pydatetime()
            end = (
                pd.Timestamp(sub.ended_at).to_pydatetime()
                if pd.notna(sub.ended_at)
                else _AS_OF
            )
            intervals[str(sub.account_id)].append((start, end, str(sub.plan)))
        return intervals

    def _build_feature_usage(
        self,
        row_count: int,
        users: pd.DataFrame,
        features: pd.DataFrame,
        subscriptions: pd.DataFrame,
    ) -> pd.DataFrame:
        intervals = self._active_plan_intervals(subscriptions)
        feature_by_rank = {
            rank: features.loc[
                features["plan_min"].map(_PLAN_RANK) <= rank, "feature_id"
            ].tolist()
            for rank in range(len(_PLANS))
        }
        # Small ``features`` row counts plus the weighted plan_min sampler can
        # leave low ranks (typically rank-0 'free') with no eligible features.
        # The downstream ``self.rng.choice(...)`` would then crash with
        # ``ValueError: a cannot be empty``. Hypothesis surfaced this at
        # seed=103 (see tests/test_saas_empty_feature_pool.py); the fallback
        # below preserves existing seed=42 behaviour because the ``or`` only
        # fires when the rank bucket was empty.
        all_features = features["feature_id"].tolist()
        for rank in feature_by_rank:
            if not feature_by_rank[rank]:
                feature_by_rank[rank] = all_features
        user_weights = np.where(users["is_active"], 2.0, 1.0)
        user_weights = user_weights / user_weights.sum()
        sampled_users = self.rng.choice(len(users), size=row_count, p=user_weights)
        records: list[dict[str, object]] = []
        for idx, user_pos in enumerate(sampled_users, start=1):
            user = users.iloc[int(user_pos)]
            user_created = pd.Timestamp(user["created_at"]).to_pydatetime()
            account_intervals = [
                interval
                for interval in intervals.get(str(user["account_id"]), [])
                if interval[1] >= user_created
            ]
            if account_intervals:
                interval = account_intervals[
                    int(self.rng.integers(0, len(account_intervals)))
                ]
                start_at = max(interval[0], user_created)
                end_at = max(interval[1], start_at)
                used_at = datetime_range_samples(start_at, end_at, 1, self.rng)[0]
                feature_pool = feature_by_rank[_PLAN_RANK[interval[2]]]
            else:
                used_at = datetime_range_samples(user_created, _AS_OF, 1, self.rng)[0]
                feature_pool = feature_by_rank[_PLAN_RANK["free"]]
            records.append(
                {
                    "usage_id": make_id_list("usage_id", idx, 1)[0],
                    "user_id": str(user["user_id"]),
                    "feature_id": str(self.rng.choice(feature_pool)),
                    "used_at": used_at,
                    "duration_s": int(self.rng.integers(5, 3_601))
                    if self.rng.random() > 0.08
                    else None,
                }
            )
        return pd.DataFrame(records)

    def _build_events(self, row_count: int, users: pd.DataFrame) -> pd.DataFrame:
        user_weights = np.where(users["is_active"], 2.0, 1.0)
        user_weights = user_weights / user_weights.sum()
        sampled_users = self.rng.choice(len(users), size=row_count, p=user_weights)
        records: list[dict[str, object]] = []
        for idx, user_pos in enumerate(sampled_users, start=1):
            user = users.iloc[int(user_pos)]
            occurred_at = datetime_range_samples(
                pd.Timestamp(user["created_at"]).to_pydatetime(), _AS_OF, 1, self.rng
            )[0]
            records.append(
                {
                    "event_id": make_id_list("event_id", idx, 1)[0],
                    "user_id": str(user["user_id"]),
                    "event_type": str(
                        weighted_choice(_EVENT_TYPES, _EVENT_W, 1, self.rng)[0]
                    ),
                    "occurred_at": occurred_at,
                    "session_id": stable_uuid(
                        f"session-{user['user_id']}-{occurred_at.isoformat()}"
                    )
                    if self.rng.random() > 0.05
                    else None,
                    "ip_address": self.faker.ipv4()
                    if self.rng.random() > 0.03
                    else None,
                }
            )
        return pd.DataFrame(records)
