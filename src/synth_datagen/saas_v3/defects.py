"""
Controlled dirty-data injection for SaaS synthetic engine v3.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
import hashlib

import numpy as np
import pandas as pd

from .config import SaaSV3Config
from .engine import EXPORTED_COLUMNS, GeneratedTables
from .ids import orphan_id


def _seed_from_label(seed: int, label: str) -> int:
    payload = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(payload[:8], "big", signed=False)


def _count_from_rate(total: int, rate: float) -> int:
    if total <= 0 or rate <= 0:
        return 0
    return min(total, max(1, int(round(total * rate))))


def _allocate_counts(total: int, capacities: list[int]) -> list[int]:
    if total <= 0 or not capacities:
        return [0] * len(capacities)
    total_capacity = sum(capacities)
    if total_capacity <= 0:
        return [0] * len(capacities)
    capped_total = min(total, total_capacity)
    weights = np.array(capacities, dtype=float) / float(total_capacity)
    raw = weights * capped_total
    counts = np.floor(raw).astype(int)
    counts = np.minimum(counts, np.array(capacities, dtype=int))
    remaining = int(capped_total - counts.sum())
    if remaining > 0:
        order = np.argsort(-(raw - counts))
        for idx in order.tolist():
            if remaining <= 0:
                break
            if counts[idx] >= capacities[idx]:
                continue
            counts[idx] += 1
            remaining -= 1
    return counts.tolist()


class DefectInjector:
    def __init__(self, config: SaaSV3Config, seed: int) -> None:
        self.config = config
        self.seed = seed

    def _rng(self, label: str) -> np.random.Generator:
        return np.random.default_rng(_seed_from_label(self.seed, f"defect:{label}"))

    def apply(self, clean: GeneratedTables) -> GeneratedTables:
        tables = {table_name: [batch.copy(deep=True) for batch in batches] for table_name, batches in clean.tables.items()}
        summary: dict[str, dict[str, object]] = {}

        self._inject_null_company_names(tables, summary)
        self._inject_case_duplicate_emails(tables, summary)
        self._inject_pre_signup_logins(tables, summary)
        self._inject_plan_typos(tables, summary)
        self._inject_negative_monthly_amounts(tables, summary)
        self._inject_reversed_subscription_dates(tables, summary)
        self._inject_orphan_events(tables, summary)
        self._inject_future_timestamps(tables, summary)
        self._inject_bad_date_formats(tables, summary)
        self._inject_mixed_invoice_amount_formats(tables, summary)
        self._inject_out_of_range_nps_scores(tables, summary)

        dirty = GeneratedTables(
            tables=tables,
            hidden_tables={name: frame.copy(deep=True) for name, frame in clean.hidden_tables.items()},
            metadata={
                "mode": "dirty",
                "seed": self.seed,
                "config_hash": self.config.config_hash(),
                "defect_summary": summary,
            },
        )
        dirty.metadata["row_counts"] = dirty.row_counts()
        return dirty

    def _inject_null_company_names(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.null_company_names
        accounts = tables["accounts"][0]
        count = _count_from_rate(len(accounts), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("null_company_names")
        if count:
            picks = rng.choice(len(accounts), size=count, replace=False)
            accounts.loc[picks, "company_name"] = np.nan
        summary["null_company_names"] = {"table": "accounts", "actual_count": count, "actual_rate": count / max(1, len(accounts))}

    def _random_case(self, email: str, rng: np.random.Generator) -> str:
        return "".join(ch.upper() if ch.isalpha() and rng.random() < 0.45 else ch.lower() if ch.isalpha() else ch for ch in email)

    def _inject_case_duplicate_emails(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.case_duplicate_emails
        users = tables["users"][0]
        count = _count_from_rate(len(users), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("case_duplicate_emails")
        actual = 0
        if count and len(users) > 1:
            target_idx = rng.choice(len(users), size=count, replace=False)
            source_idx = rng.choice(len(users), size=count, replace=True)
            for target, source in zip(target_idx.tolist(), source_idx.tolist(), strict=False):
                base = str(users.at[source, "email"])
                variant = self._random_case(base, rng)
                if variant == base:
                    variant = base.swapcase()
                users.at[target, "email"] = variant
                actual += 1
        summary["case_duplicate_emails"] = {"table": "users", "actual_count": actual, "actual_rate": actual / max(1, len(users))}

    def _inject_pre_signup_logins(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.pre_signup_logins
        users = tables["users"][0]
        accounts = tables["accounts"][0].set_index("account_id")
        eligible = users.index[users["last_login_at"].notna()].to_numpy()
        count = _count_from_rate(len(users), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("pre_signup_logins")
        actual = 0
        if count and len(eligible):
            picks = rng.choice(eligible, size=min(count, len(eligible)), replace=False)
            for idx in picks.tolist():
                signup = pd.Timestamp(accounts.loc[users.at[idx, "account_id"], "signup_date"]).date()
                offset_days = int(rng.integers(1, 31))
                login_date = signup - timedelta(days=offset_days)
                users.at[idx, "last_login_at"] = datetime.combine(login_date, time(hour=int(rng.integers(5, 21)), minute=int(rng.integers(0, 60))))
                actual += 1
        summary["pre_signup_logins"] = {"table": "users", "actual_count": actual, "actual_rate": actual / max(1, len(users))}

    def _plan_typo(self, plan_name: str) -> str:
        aliases = {
            "Professional": "Pro",
            "Enterprise": "Enterprize",
            "Starter": "Starter Plan",
        }
        return aliases.get(plan_name, f"{plan_name[: max(2, len(plan_name) - 2)]}r")

    def _inject_plan_typos(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.plan_name_typos
        subscriptions = tables["subscriptions"][0]
        count = _count_from_rate(len(subscriptions), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("plan_name_typos")
        actual = 0
        if count:
            picks = rng.choice(len(subscriptions), size=count, replace=False)
            for idx in picks.tolist():
                subscriptions.at[idx, "plan_name"] = self._plan_typo(str(subscriptions.at[idx, "plan_name"]))
                actual += 1
        summary["plan_name_typos"] = {"table": "subscriptions", "actual_count": actual, "actual_rate": actual / max(1, len(subscriptions))}

    def _inject_negative_monthly_amounts(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.negative_monthly_amounts
        subscriptions = tables["subscriptions"][0]
        count = _count_from_rate(len(subscriptions), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("negative_monthly_amounts")
        actual = 0
        if count:
            picks = rng.choice(len(subscriptions), size=count, replace=False)
            subscriptions.loc[picks, "monthly_amount"] = -subscriptions.loc[picks, "monthly_amount"].abs()
            actual = len(picks)
        summary["negative_monthly_amounts"] = {"table": "subscriptions", "actual_count": actual, "actual_rate": actual / max(1, len(subscriptions))}

    def _inject_reversed_subscription_dates(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.reversed_subscription_dates
        subscriptions = tables["subscriptions"][0]
        eligible = subscriptions.index.to_numpy()
        count = _count_from_rate(len(subscriptions), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("reversed_subscription_dates")
        actual = 0
        if count and len(eligible):
            picks = rng.choice(eligible, size=min(count, len(eligible)), replace=False)
            for idx in picks.tolist():
                start = pd.Timestamp(subscriptions.at[idx, "start_date"]).date()
                subscriptions.at[idx, "end_date"] = start - timedelta(days=int(rng.integers(1, 30)))
                actual += 1
        summary["reversed_subscription_dates"] = {"table": "subscriptions", "actual_count": actual, "actual_rate": actual / max(1, len(subscriptions))}

    def _inject_orphan_events(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.orphaned_product_events
        rng = self._rng("orphaned_product_events")
        total_rows = sum(len(batch) for batch in tables["product_events"])
        requested = _count_from_rate(total_rows, cfg.rate if cfg.enabled else 0.0)
        actual = 0
        for batch_index, batch in enumerate(tables["product_events"]):
            batch_count = min(len(batch), _count_from_rate(len(batch), cfg.rate if cfg.enabled else 0.0))
            if batch_count <= 0:
                continue
            picks = rng.choice(len(batch), size=batch_count, replace=False)
            for offset, idx in enumerate(picks.tolist(), start=1):
                batch.at[idx, "account_id"] = orphan_id("account_id", batch_index * 1_000_000 + offset)
                batch.at[idx, "user_id"] = orphan_id("user_id", batch_index * 1_000_000 + offset)
                actual += 1
        summary["orphaned_product_events"] = {"table": "product_events", "actual_count": actual, "actual_rate": actual / max(1, total_rows), "requested_count": requested}

    def _inject_future_timestamps(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.future_timestamps
        rate = cfg.rate if cfg.enabled else 0.0
        rng = self._rng("future_timestamps")
        future_base = self.config.history.as_of_date + timedelta(days=7)
        actual = 0
        if rate <= 0:
            summary["future_timestamps"] = {"tables": [], "actual_count": 0, "actual_rate": 0.0}
            return
        users = tables["users"][0]
        user_count = min(len(users), _count_from_rate(len(users), rate))
        if user_count:
            eligible = users.index[users["last_login_at"].notna()].to_numpy()
            if len(eligible):
                picks = rng.choice(eligible, size=min(user_count, len(eligible)), replace=False)
                for idx in picks.tolist():
                    users.at[idx, "last_login_at"] = datetime.combine(future_base + timedelta(days=int(rng.integers(0, 45))), time(hour=int(rng.integers(6, 23)), minute=int(rng.integers(0, 60))))
                    actual += 1
        invoices = tables["invoices"][0]
        inv_count = min(len(invoices), _count_from_rate(len(invoices), rate))
        if inv_count:
            picks = rng.choice(len(invoices), size=inv_count, replace=False)
            invoices.loc[picks, "invoice_date"] = [future_base + timedelta(days=int(rng.integers(0, 60))) for _ in range(inv_count)]
            actual += inv_count
        nps = tables["nps_responses"][0]
        nps_count = min(len(nps), _count_from_rate(len(nps), rate))
        if nps_count:
            picks = rng.choice(len(nps), size=nps_count, replace=False)
            nps.loc[picks, "survey_date"] = [future_base + timedelta(days=int(rng.integers(0, 90))) for _ in range(nps_count)]
            actual += nps_count
        event_total = 0
        for batch in tables["product_events"]:
            batch_count = min(len(batch), _count_from_rate(len(batch), rate))
            if batch_count <= 0:
                continue
            picks = rng.choice(len(batch), size=batch_count, replace=False)
            batch.loc[picks, "event_timestamp"] = [datetime.combine(future_base + timedelta(days=int(rng.integers(0, 90))), time(hour=int(rng.integers(0, 24)), minute=int(rng.integers(0, 60)), second=int(rng.integers(0, 60)))) for _ in range(batch_count)]
            actual += batch_count
            event_total += batch_count
        summary["future_timestamps"] = {"tables": ["users", "invoices", "nps_responses", "product_events"], "actual_count": actual, "event_rows": event_total}

    def _bad_date_value(self, column_name: str, rng: np.random.Generator) -> str:
        variants = {
            "last_login_at": ["2026-99-01T25:61:00", "not_a_date", "2026-13-40T12:00:00"],
            "event_timestamp": ["2026-99-01T25:61:00", "not_a_date", "2026-13-40T00:00:00"],
            "invoice_date": ["2026-13-40", "31/02/2026", "not_a_date"],
            "survey_date": ["2026-13-40", "31/02/2026", "not_a_date"],
        }
        choices = variants.get(column_name, ["not_a_date"])
        return str(rng.choice(choices))

    def _inject_bad_date_formats(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.bad_date_formats
        rate = cfg.rate if cfg.enabled else 0.0
        rng = self._rng("bad_date_formats")
        targets: list[tuple[pd.DataFrame, str]] = [
            (tables["users"][0], "last_login_at"),
            (tables["invoices"][0], "invoice_date"),
            (tables["nps_responses"][0], "survey_date"),
        ]
        targets.extend((batch, "event_timestamp") for batch in tables["product_events"])
        capacities = [len(frame) for frame, _ in targets]
        total_rows = sum(capacities)
        requested = _count_from_rate(total_rows, rate)
        allocations = _allocate_counts(requested, capacities)
        actual = 0
        touched_tables: set[str] = set()

        for (frame, column_name), count in zip(targets, allocations, strict=False):
            if count <= 0 or frame.empty:
                continue
            frame[column_name] = frame[column_name].astype(object)
            picks = rng.choice(len(frame), size=count, replace=False)
            for idx in picks.tolist():
                frame.at[idx, column_name] = self._bad_date_value(column_name, rng)
                actual += 1
            for table_name, columns in EXPORTED_COLUMNS.items():
                if column_name in columns:
                    touched_tables.add(table_name)
                    break

        summary["bad_date_formats"] = {
            "tables": sorted(touched_tables),
            "actual_count": actual,
            "actual_rate": actual / max(1, total_rows),
            "requested_count": requested,
        }

    def _format_amount_variant(self, amount: float, currency: str, rng: np.random.Generator) -> str:
        style = int(rng.integers(0, 4))
        if style == 0:
            return str(int(round(amount * 100)))
        if style == 1:
            return f"{currency} {amount:,.2f}"
        if style == 2:
            return f"€{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{amount:,.2f} {currency}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _inject_mixed_invoice_amount_formats(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.mixed_invoice_amount_formats
        invoices = tables["invoices"][0]
        count = _count_from_rate(len(invoices), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("mixed_invoice_amount_formats")
        actual = 0
        if count:
            invoices["amount_due"] = invoices["amount_due"].astype(object)
            invoices["amount_paid"] = invoices["amount_paid"].astype(object)
            picks = rng.choice(len(invoices), size=count, replace=False)
            for idx in picks.tolist():
                invoices.at[idx, "amount_due"] = self._format_amount_variant(float(invoices.at[idx, "amount_due"]), str(invoices.at[idx, "currency"]), rng)
                invoices.at[idx, "amount_paid"] = self._format_amount_variant(float(invoices.at[idx, "amount_paid"]), str(invoices.at[idx, "currency"]), rng)
                actual += 1
        summary["mixed_invoice_amount_formats"] = {"table": "invoices", "actual_count": actual, "actual_rate": actual / max(1, len(invoices))}

    def _inject_out_of_range_nps_scores(self, tables: dict[str, list[pd.DataFrame]], summary: dict[str, dict[str, object]]) -> None:
        cfg = self.config.defects.out_of_range_nps_scores
        nps = tables["nps_responses"][0]
        count = _count_from_rate(len(nps), cfg.rate if cfg.enabled else 0.0)
        rng = self._rng("out_of_range_nps_scores")
        actual = 0
        if count:
            picks = rng.choice(len(nps), size=count, replace=False)
            invalid_scores = np.array([-2, -1, 11, 12, 15])
            nps.loc[picks, "score"] = rng.choice(invalid_scores, size=count)
            actual = len(picks)
        summary["out_of_range_nps_scores"] = {"table": "nps_responses", "actual_count": actual, "actual_rate": actual / max(1, len(nps))}
