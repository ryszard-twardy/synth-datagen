"""
Fintech / banking scenario generator.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterator

import numpy as np
import pandas as pd
from faker import Faker

from ..config import ColumnConfig, DType, GeneratorConfig, RelationConfig, TableConfig
from ..id_utils import make_id_list
from ..schema_builder import SchemaGraph
from ..utils import (
    COUNTRY_CURRENCIES,
    COUNTRY_NAMES,
    COUNTRY_WEIGHTS,
    add_months,
    bounded_lognormal,
    date_range_samples,
    datetime_range_samples,
    distribute_counts,
    weighted_choice,
)
from .base import BaseScenarioGenerator

_ACCOUNT_TYPES = ["checking", "savings", "money_market", "investment", "credit"]
_ACCOUNT_W = [0.42, 0.30, 0.08, 0.08, 0.12]
_TX_TYPES = ["purchase", "transfer", "withdrawal", "deposit", "refund", "fee"]
_TX_WEIGHTS = [0.44, 0.18, 0.10, 0.18, 0.05, 0.05]
_CARD_TYPES = ["debit", "credit", "prepaid"]
_CARD_W = [0.54, 0.38, 0.08]
_CARD_NETWORKS = ["Visa", "Mastercard", "Amex", "Discover"]
_CARD_NW = [0.46, 0.34, 0.15, 0.05]
_LOAN_TYPES = ["personal", "auto", "mortgage", "student", "business"]
_LOAN_W = [0.30, 0.18, 0.28, 0.14, 0.10]
_LOAN_STATUSES = ["active", "paid_off", "default", "deferred"]
_LOAN_SW = [0.66, 0.18, 0.08, 0.08]
_PAYMENT_STATUSES = ["completed", "pending", "failed", "reversed"]
_PAYMENT_SW = [0.84, 0.08, 0.05, 0.03]
_MERCHANT_CATS = [
    "retail",
    "food_beverage",
    "travel",
    "utilities",
    "healthcare",
    "entertainment",
    "online_services",
    "other",
]
_MERCHANT_W = [0.22, 0.20, 0.12, 0.10, 0.10, 0.10, 0.10, 0.06]
_SIM_START = datetime(2020, 1, 1)
_AS_OF = datetime(2025, 12, 31, 23, 59, 59)


def _advance_years_safe(d: date, years: int) -> date:
    """Return ``d`` plus ``years``, clamping Feb-29 to Feb-28 on non-leap targets.

    ``date.replace(year=...)`` raises ``ValueError`` when the source date is
    Feb 29 and the target year is not a leap year — the latent bug recorded
    under v0.2.0 "Fixed" in CHANGELOG.md (the fintech leap-day card-expiry
    crash) that crashed default-scale fintech generation. Real card issuers
    handle the same edge case by issuing the expiry on Feb 28 of the target
    year, which is the behaviour reproduced here.

    Any other date round-trips unchanged.
    """
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # Only triggered by Feb 29 -> non-leap target. Re-issue on Feb 28.
        return d.replace(year=d.year + years, day=28)


class FintechGenerator(BaseScenarioGenerator):
    def __init__(
        self, config: GeneratorConfig, rng: np.random.Generator, faker: Faker
    ) -> None:
        super().__init__(config, rng, faker)
        self._cache: dict[str, pd.DataFrame] | None = None

    def get_raw_schema(self) -> tuple[list[TableConfig], list[RelationConfig]]:
        ov = self.config.row_overrides
        tables = [
            TableConfig(
                name="customers",
                row_count=ov.get("customers", 10_000),
                pk_column="customer_id",
                columns=[
                    ColumnConfig(
                        name="customer_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(
                        name="first_name", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="last_name", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="email", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(name="phone", dtype=DType.VARCHAR, nullable=True),
                    ColumnConfig(name="dob", dtype=DType.DATE, nullable=True),
                    ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="city", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="credit_score", dtype=DType.INT, nullable=True),
                    ColumnConfig(
                        name="kyc_status", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(
                        name="created_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="accounts",
                row_count=ov.get("accounts", 15_000),
                pk_column="account_id",
                columns=[
                    ColumnConfig(
                        name="account_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(
                        name="customer_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(
                        name="account_type", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="currency", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="balance", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(
                        name="opened_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(
                        name="closed_at", dtype=DType.TIMESTAMP, nullable=True
                    ),
                    ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="merchants",
                row_count=ov.get("merchants", 2_000),
                pk_column="merchant_id",
                columns=[
                    ColumnConfig(
                        name="merchant_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(
                        name="merchant_name", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="category", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="country", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="city", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="is_online", dtype=DType.BOOLEAN, nullable=False),
                ],
            ),
            TableConfig(
                name="transactions",
                row_count=ov.get("transactions", 200_000),
                pk_column="transaction_id",
                columns=[
                    ColumnConfig(
                        name="transaction_id",
                        dtype=DType.VARCHAR,
                        nullable=False,
                        unique=True,
                    ),
                    ColumnConfig(
                        name="account_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(
                        name="merchant_id", dtype=DType.VARCHAR, nullable=True
                    ),
                    ColumnConfig(name="tx_type", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="amount", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(name="currency", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="balance_after", dtype=DType.DECIMAL, nullable=False
                    ),
                    ColumnConfig(name="description", dtype=DType.TEXT, nullable=True),
                    ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="created_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                ],
            ),
            TableConfig(
                name="cards",
                row_count=ov.get("cards", 12_000),
                pk_column="card_id",
                columns=[
                    ColumnConfig(
                        name="card_id", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(
                        name="account_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="card_type", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="network", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="last4", dtype=DType.VARCHAR, nullable=False, max_length=4
                    ),
                    ColumnConfig(name="issue_date", dtype=DType.DATE, nullable=False),
                    ColumnConfig(name="expiry_date", dtype=DType.DATE, nullable=False),
                    ColumnConfig(name="is_active", dtype=DType.BOOLEAN, nullable=False),
                    ColumnConfig(
                        name="spend_limit", dtype=DType.DECIMAL, nullable=True
                    ),
                ],
            ),
            TableConfig(
                name="loans",
                row_count=ov.get("loans", 3_000),
                pk_column="loan_id",
                columns=[
                    ColumnConfig(
                        name="loan_id", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(
                        name="customer_id", dtype=DType.VARCHAR, nullable=False
                    ),
                    ColumnConfig(name="loan_type", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="principal", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(
                        name="interest_rate", dtype=DType.DECIMAL, nullable=False
                    ),
                    ColumnConfig(name="term_months", dtype=DType.INT, nullable=False),
                    ColumnConfig(
                        name="monthly_payment", dtype=DType.DECIMAL, nullable=False
                    ),
                    ColumnConfig(
                        name="outstanding", dtype=DType.DECIMAL, nullable=False
                    ),
                    ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(
                        name="disbursed_at", dtype=DType.TIMESTAMP, nullable=False
                    ),
                    ColumnConfig(name="due_date", dtype=DType.DATE, nullable=False),
                    ColumnConfig(name="currency", dtype=DType.VARCHAR, nullable=False),
                ],
            ),
            TableConfig(
                name="loan_payments",
                row_count=ov.get("loan_payments", 30_000),
                pk_column="lp_id",
                columns=[
                    ColumnConfig(
                        name="lp_id", dtype=DType.VARCHAR, nullable=False, unique=True
                    ),
                    ColumnConfig(name="loan_id", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="amount", dtype=DType.DECIMAL, nullable=False),
                    ColumnConfig(name="paid_at", dtype=DType.TIMESTAMP, nullable=False),
                    ColumnConfig(name="status", dtype=DType.VARCHAR, nullable=False),
                    ColumnConfig(name="penalty", dtype=DType.DECIMAL, nullable=False),
                ],
            ),
        ]
        relations = [
            RelationConfig(
                source_table="accounts",
                source_column="customer_id",
                target_table="customers",
                target_column="customer_id",
            ),
            RelationConfig(
                source_table="transactions",
                source_column="account_id",
                target_table="accounts",
                target_column="account_id",
            ),
            RelationConfig(
                source_table="transactions",
                source_column="merchant_id",
                target_table="merchants",
                target_column="merchant_id",
            ),
            RelationConfig(
                source_table="cards",
                source_column="account_id",
                target_table="accounts",
                target_column="account_id",
            ),
            RelationConfig(
                source_table="loans",
                source_column="customer_id",
                target_table="customers",
                target_column="customer_id",
            ),
            RelationConfig(
                source_table="loan_payments",
                source_column="loan_id",
                target_table="loans",
                target_column="loan_id",
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
        customers = self._build_customers(counts["customers"])
        accounts = self._build_accounts(counts["accounts"], customers)
        merchants = self._build_merchants(counts["merchants"])
        transactions, account_balances = self._build_transactions(
            counts["transactions"], accounts, merchants
        )
        accounts["balance"] = (
            accounts["account_id"]
            .map(account_balances)
            .fillna(accounts["balance"])
            .round(2)
        )
        cards = self._build_cards(counts["cards"], accounts)
        loans = self._build_loans(counts["loans"], customers)
        loan_payments = self._build_loan_payments(counts["loan_payments"], loans)
        return {
            "customers": customers,
            "accounts": accounts,
            "merchants": merchants,
            "transactions": transactions,
            "cards": cards,
            "loans": loans,
            "loan_payments": loan_payments,
        }

    def _build_customers(self, row_count: int) -> pd.DataFrame:
        countries = weighted_choice(
            COUNTRY_NAMES, COUNTRY_WEIGHTS, row_count, self.rng
        ).tolist()
        created_at = pd.to_datetime(
            datetime_range_samples(
                _SIM_START, datetime(2025, 9, 30), row_count, self.rng
            )
        )
        first_names = [self.faker.first_name() for _ in range(row_count)]
        last_names = [self.faker.last_name() for _ in range(row_count)]
        return pd.DataFrame(
            {
                "customer_id": make_id_list("customer_id", 1, row_count),
                "first_name": first_names,
                "last_name": last_names,
                "email": [
                    f"{first_names[idx].lower()}.{last_names[idx].lower()}.{idx + 1:05d}@mail.com"
                    for idx in range(row_count)
                ],
                "phone": [
                    self.faker.phone_number() if self.rng.random() > 0.10 else None
                    for _ in range(row_count)
                ],
                "dob": date_range_samples(
                    date(1950, 1, 1), date(2003, 12, 31), row_count, self.rng
                ),
                "country": countries,
                "city": [self.faker.city() for _ in range(row_count)],
                "credit_score": np.round(self.rng.normal(690, 85, row_count))
                .clip(300, 850)
                .astype(int),
                "kyc_status": weighted_choice(
                    ["verified", "pending", "rejected", "not_started"],
                    [0.78, 0.12, 0.05, 0.05],
                    row_count,
                    self.rng,
                ).tolist(),
                "created_at": created_at,
                "is_active": self.rng.random(row_count) > 0.08,
            }
        )

    def _build_accounts(self, row_count: int, customers: pd.DataFrame) -> pd.DataFrame:
        counts = np.zeros(len(customers), dtype=int)
        if row_count >= len(customers):
            counts[:] = 1
            extra = row_count - len(customers)
            for idx in self.rng.integers(0, len(customers), size=extra):
                counts[int(idx)] += 1
        else:
            for idx in self.rng.choice(len(customers), size=row_count, replace=False):
                counts[int(idx)] += 1
        records: list[dict[str, object]] = []
        seq = 1
        for cust_idx, acct_count in enumerate(counts):
            if acct_count == 0:
                continue
            customer = customers.iloc[cust_idx]
            customer_created = pd.Timestamp(customer["created_at"]).to_pydatetime()
            for _ in range(int(acct_count)):
                account_type = str(
                    weighted_choice(_ACCOUNT_TYPES, _ACCOUNT_W, 1, self.rng)[0]
                )
                opened_at = datetime_range_samples(
                    customer_created, _AS_OF - timedelta(days=30), 1, self.rng
                )[0]
                is_active = bool(self.rng.random() > 0.14)
                closed_at = None
                if not is_active:
                    closed_at = datetime_range_samples(
                        opened_at + timedelta(days=30), _AS_OF, 1, self.rng
                    )[0]
                records.append(
                    {
                        "account_id": make_id_list("account_id", seq, 1)[0],
                        "customer_id": str(customer["customer_id"]),
                        "account_type": account_type,
                        "currency": COUNTRY_CURRENCIES.get(
                            str(customer["country"]), "USD"
                        ),
                        "balance": round(
                            float(
                                bounded_lognormal(
                                    6.0, 1.0, 100.0, 250_000.0, 1, self.rng
                                )[0]
                            ),
                            2,
                        ),
                        "opened_at": opened_at,
                        "closed_at": closed_at,
                        "is_active": is_active,
                    }
                )
                seq += 1
        return pd.DataFrame(records)

    def _build_merchants(self, row_count: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "merchant_id": make_id_list("merchant_id", 1, row_count),
                "merchant_name": [self.faker.company() for _ in range(row_count)],
                "category": weighted_choice(
                    _MERCHANT_CATS, _MERCHANT_W, row_count, self.rng
                ).tolist(),
                "country": weighted_choice(
                    COUNTRY_NAMES, COUNTRY_WEIGHTS, row_count, self.rng
                ).tolist(),
                "city": [self.faker.city() for _ in range(row_count)],
                "is_online": self.rng.random(row_count) > 0.42,
            }
        )

    def _build_transactions(
        self,
        row_count: int,
        accounts: pd.DataFrame,
        merchants: pd.DataFrame,
    ) -> tuple[pd.DataFrame, dict[str, float]]:
        weights = np.where(accounts["account_type"].eq("credit"), 1.5, 1.0)
        tx_counts = distribute_counts(
            row_count, len(accounts), minimum=0, rng=self.rng, weights=weights
        )
        merchant_ids = merchants["merchant_id"].to_numpy()
        records: list[dict[str, object]] = []
        balances: dict[str, float] = {}
        tx_seq = 1
        for idx, tx_count in enumerate(tx_counts):
            account = accounts.iloc[idx]
            start = pd.Timestamp(account["opened_at"]).to_pydatetime()
            end = (
                pd.Timestamp(account["closed_at"]).to_pydatetime()
                if pd.notna(account["closed_at"])
                else _AS_OF
            )
            if start >= end:
                end = start + timedelta(days=1)
            balance = float(account["balance"])
            timestamps = (
                sorted(
                    datetime_range_samples(start, end, int(tx_count), self.rng).tolist()
                )
                if tx_count
                else []
            )
            for ts in timestamps:
                tx_type = str(weighted_choice(_TX_TYPES, _TX_WEIGHTS, 1, self.rng)[0])
                raw_amount = round(
                    float(bounded_lognormal(3.3, 1.0, 1.0, 25_000.0, 1, self.rng)[0]), 2
                )
                if tx_type in {"purchase", "withdrawal", "fee"}:
                    amount = -raw_amount
                elif tx_type == "transfer":
                    amount = raw_amount if self.rng.random() < 0.45 else -raw_amount
                else:
                    amount = raw_amount
                merchant_id = None
                if tx_type in {"purchase", "refund"}:
                    merchant_id = str(self.rng.choice(merchant_ids))
                balance_floor = (
                    -50_000.0 if account["account_type"] == "credit" else -500.0
                )
                if balance + amount < balance_floor:
                    amount = round(balance_floor - balance, 2)
                balance = round(balance + amount, 2)
                records.append(
                    {
                        "transaction_id": make_id_list("transaction_id", tx_seq, 1)[0],
                        "account_id": str(account["account_id"]),
                        "merchant_id": merchant_id,
                        "tx_type": tx_type,
                        "amount": round(amount, 2),
                        "currency": str(account["currency"]),
                        "balance_after": round(balance, 2),
                        "description": self.faker.sentence(nb_words=5)
                        if self.rng.random() > 0.25
                        else None,
                        "status": str(
                            weighted_choice(
                                ["completed", "pending"], [0.92, 0.08], 1, self.rng
                            )[0]
                        ),
                        "created_at": ts,
                    }
                )
                tx_seq += 1
            balances[str(account["account_id"])] = round(balance, 2)
        transactions = (
            pd.DataFrame(records)
            .sort_values(["account_id", "created_at", "transaction_id"])
            .reset_index(drop=True)
        )
        return transactions, balances

    def _build_cards(self, row_count: int, accounts: pd.DataFrame) -> pd.DataFrame:
        counts = distribute_counts(
            row_count,
            len(accounts),
            minimum=0,
            rng=self.rng,
            weights=np.where(accounts["account_type"].eq("credit"), 1.6, 1.0),
        )
        records: list[dict[str, object]] = []
        seq = 1
        for idx, count in enumerate(counts):
            account = accounts.iloc[idx]
            issue_start = pd.Timestamp(account["opened_at"]).date()
            issue_end = min(
                (_AS_OF - timedelta(days=90)).date(),
                pd.Timestamp(account["closed_at"]).date()
                if pd.notna(account["closed_at"])
                else _AS_OF.date(),
            )
            if issue_start > issue_end:
                issue_end = issue_start
            issue_dates = date_range_samples(
                issue_start, issue_end, int(count), self.rng
            )
            for issue_date in issue_dates:
                expiry_date = _advance_years_safe(
                    issue_date, int(self.rng.integers(3, 6))
                )
                is_active = bool(
                    expiry_date >= _AS_OF.date()
                    and account["is_active"]
                    and self.rng.random() > 0.10
                )
                card_type = str(weighted_choice(_CARD_TYPES, _CARD_W, 1, self.rng)[0])
                records.append(
                    {
                        "card_id": make_id_list("card_id", seq, 1)[0],
                        "account_id": str(account["account_id"]),
                        "card_type": card_type,
                        "network": str(
                            weighted_choice(_CARD_NETWORKS, _CARD_NW, 1, self.rng)[0]
                        ),
                        "last4": f"{int(self.rng.integers(0, 10_000)):04d}",
                        "issue_date": issue_date,
                        "expiry_date": expiry_date,
                        "is_active": is_active,
                        "spend_limit": round(float(self.rng.uniform(500, 30_000)), 2)
                        if card_type == "credit"
                        else None,
                    }
                )
                seq += 1
        return pd.DataFrame(records)

    def _build_loans(self, row_count: int, customers: pd.DataFrame) -> pd.DataFrame:
        chosen_customers = self.rng.choice(
            len(customers), size=row_count, replace=row_count > len(customers)
        )
        records: list[dict[str, object]] = []
        for idx, cust_pos in enumerate(chosen_customers, start=1):
            customer = customers.iloc[int(cust_pos)]
            disbursed_at = datetime_range_samples(
                pd.Timestamp(customer["created_at"]).to_pydatetime(),
                _AS_OF - timedelta(days=30),
                1,
                self.rng,
            )[0]
            loan_type = str(weighted_choice(_LOAN_TYPES, _LOAN_W, 1, self.rng)[0])
            principal = round(
                float(bounded_lognormal(9.0, 1.0, 1_000.0, 900_000.0, 1, self.rng)[0]),
                2,
            )
            rate = round(float(self.rng.uniform(2.5, 24.0)), 2)
            term = int(self.rng.choice([12, 24, 36, 48, 60, 120, 180, 240, 360]))
            monthly_payment = round((principal / term) * (1 + rate / 1200), 2)
            status = str(weighted_choice(_LOAN_STATUSES, _LOAN_SW, 1, self.rng)[0])
            if status == "paid_off":
                outstanding = 0.0
            elif status == "default":
                outstanding = round(principal * float(self.rng.uniform(0.45, 1.0)), 2)
            elif status == "deferred":
                outstanding = round(principal * float(self.rng.uniform(0.65, 1.0)), 2)
            else:
                outstanding = round(principal * float(self.rng.uniform(0.10, 0.90)), 2)
            records.append(
                {
                    "loan_id": make_id_list("loan_id", idx, 1)[0],
                    "customer_id": str(customer["customer_id"]),
                    "loan_type": loan_type,
                    "principal": principal,
                    "interest_rate": rate,
                    "term_months": term,
                    "monthly_payment": monthly_payment,
                    "outstanding": outstanding,
                    "status": status,
                    "disbursed_at": disbursed_at,
                    "due_date": add_months(disbursed_at, term).date(),
                    "currency": COUNTRY_CURRENCIES.get(str(customer["country"]), "USD"),
                }
            )
        return pd.DataFrame(records)

    def _build_loan_payments(self, row_count: int, loans: pd.DataFrame) -> pd.DataFrame:
        candidates: list[dict[str, object]] = []
        for loan in loans.itertuples(index=False):
            total_installments = min(int(loan.term_months), 24)
            for installment in range(total_installments):
                due_dt = add_months(
                    pd.Timestamp(loan.disbursed_at).to_pydatetime(), installment + 1
                )
                if due_dt.date() > loan.due_date:
                    break
                status = str(
                    weighted_choice(_PAYMENT_STATUSES, _PAYMENT_SW, 1, self.rng)[0]
                )
                amount = round(
                    float(
                        self.rng.uniform(
                            max(1.0, loan.monthly_payment * 0.75), loan.monthly_payment
                        )
                    ),
                    2,
                )
                if status in {"failed", "reversed"}:
                    amount = round(
                        float(self.rng.uniform(0.0, loan.monthly_payment * 0.15)), 2
                    )
                paid_at = datetime_range_samples(
                    pd.Timestamp(loan.disbursed_at).to_pydatetime(), due_dt, 1, self.rng
                )[0]
                candidates.append(
                    {
                        "loan_id": str(loan.loan_id),
                        "amount": amount,
                        "paid_at": paid_at,
                        "status": status,
                        "penalty": round(float(self.rng.uniform(10, 200)), 2)
                        if paid_at > due_dt and self.rng.random() < 0.25
                        else 0.0,
                    }
                )
        if len(candidates) >= row_count:
            indices = self.rng.choice(len(candidates), size=row_count, replace=False)
            rows = [candidates[int(idx)] for idx in sorted(indices)]
        else:
            rows = list(candidates)
            while len(rows) < row_count and candidates:
                seed = dict(candidates[len(rows) % len(candidates)])
                seed["status"] = "pending"
                rows.append(seed)
        for idx, row in enumerate(rows, start=1):
            row["lp_id"] = make_id_list("lp_id", idx, 1)[0]
        return pd.DataFrame(rows)
