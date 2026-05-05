"""
Validation helpers for SaaS synthetic engine v3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import SaaSV3Config
from .engine import EXPORTED_COLUMNS, GeneratedTables, TABLE_ORDER


@dataclass
class ValidationIssue:
    code: str
    table: str | None
    message: str


@dataclass
class ValidationReport:
    mode: str
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    metrics: dict[str, object] = field(default_factory=dict)


def validate_generated_dataset(dataset: GeneratedTables, config: SaaSV3Config, mode: str) -> ValidationReport:
    issues: list[ValidationIssue] = []
    metrics: dict[str, object] = {"row_counts": dataset.row_counts()}

    _validate_schema(dataset, issues)
    _validate_row_counts(dataset, config, issues)
    if mode == "clean":
        _validate_clean_integrity(dataset, config, issues, metrics)
    else:
        _validate_dirty_defects(dataset, config, issues, metrics)

    return ValidationReport(mode=mode, passed=not issues, issues=issues, metrics=metrics)


def validate_exported_run(run_root: Path, config: SaaSV3Config, mode: str) -> ValidationReport:
    dataset_root = run_root / mode / "csv"
    tables = {table_name: [pd.read_csv(dataset_root / f"{table_name}.csv")] for table_name in TABLE_ORDER}
    dataset = GeneratedTables(tables=tables, metadata={})
    return validate_generated_dataset(dataset, config, mode)


def _validate_schema(dataset: GeneratedTables, issues: list[ValidationIssue]) -> None:
    for table_name in TABLE_ORDER:
        columns = list(dataset.materialize(table_name).columns)
        if columns != EXPORTED_COLUMNS[table_name]:
            issues.append(ValidationIssue("schema_columns", table_name, f"Expected columns {EXPORTED_COLUMNS[table_name]} but found {columns}"))


def _validate_row_counts(dataset: GeneratedTables, config: SaaSV3Config, issues: list[ValidationIssue]) -> None:
    actual = dataset.row_counts()
    for table_name, target in config.row_target_map.items():
        tolerance = config.validation.row_count_tolerance.get(table_name, 0.0)
        observed = actual.get(table_name, 0)
        if abs(observed - target) > max(1, int(round(target * tolerance))):
            issues.append(ValidationIssue("row_count", table_name, f"Observed {observed} rows vs target {target} with tolerance {tolerance}"))


def _validate_clean_integrity(dataset: GeneratedTables, config: SaaSV3Config, issues: list[ValidationIssue], metrics: dict[str, object]) -> None:
    accounts = dataset.materialize("accounts")
    users = dataset.materialize("users")
    subscriptions = dataset.materialize("subscriptions")
    events = dataset.materialize("product_events")
    invoices = dataset.materialize("invoices")
    nps = dataset.materialize("nps_responses")

    _assert_unique(accounts, "account_id", "accounts", issues)
    _assert_unique(users, "user_id", "users", issues)
    _assert_unique(subscriptions, "subscription_id", "subscriptions", issues)
    _assert_unique(events, "event_id", "product_events", issues)
    _assert_unique(invoices, "invoice_id", "invoices", issues)
    _assert_unique(dataset.materialize("support_tickets"), "ticket_id", "support_tickets", issues)
    _assert_unique(nps, "response_id", "nps_responses", issues)

    account_ids = set(accounts["account_id"].astype(str))
    user_ids = set(users["user_id"].astype(str))
    if not users["account_id"].astype(str).isin(account_ids).all():
        issues.append(ValidationIssue("fk_users_accounts", "users", "users.account_id contains unknown account_id values"))
    if not subscriptions["account_id"].astype(str).isin(account_ids).all():
        issues.append(ValidationIssue("fk_subscriptions_accounts", "subscriptions", "subscriptions.account_id contains unknown account_id values"))
    if not invoices["account_id"].astype(str).isin(account_ids).all():
        issues.append(ValidationIssue("fk_invoices_accounts", "invoices", "invoices.account_id contains unknown account_id values"))
    if not dataset.materialize("support_tickets")["account_id"].astype(str).isin(account_ids).all():
        issues.append(ValidationIssue("fk_tickets_accounts", "support_tickets", "support_tickets.account_id contains unknown account_id values"))
    if not nps["account_id"].astype(str).isin(account_ids).all():
        issues.append(ValidationIssue("fk_nps_accounts", "nps_responses", "nps_responses.account_id contains unknown account_id values"))
    if not events["account_id"].astype(str).isin(account_ids).all():
        issues.append(ValidationIssue("fk_events_accounts", "product_events", "product_events.account_id contains unknown account_id values"))
    if not events["user_id"].astype(str).isin(user_ids).all():
        issues.append(ValidationIssue("fk_events_users", "product_events", "product_events.user_id contains unknown user_id values"))

    account_signup = accounts.set_index("account_id")["signup_date"]
    users_last_login = pd.to_datetime(users["last_login_at"], errors="coerce")
    users_signup = pd.to_datetime(users["account_id"].map(account_signup), errors="coerce")
    if (users_last_login.dropna() < users_signup.loc[users_last_login.dropna().index]).any():
        issues.append(ValidationIssue("chronology_user_login", "users", "Found last_login_at values earlier than account signup_date"))
    if (pd.to_datetime(subscriptions["end_date"], errors="coerce").dropna() < pd.to_datetime(subscriptions["start_date"], errors="coerce").loc[pd.to_datetime(subscriptions["end_date"], errors="coerce").dropna().index]).any():
        issues.append(ValidationIssue("chronology_subscriptions", "subscriptions", "Found subscriptions with end_date earlier than start_date"))
    event_signup = pd.to_datetime(events["account_id"].map(account_signup), errors="coerce")
    event_time = pd.to_datetime(events["event_timestamp"], errors="coerce")
    if (event_time < event_signup).any():
        issues.append(ValidationIssue("chronology_events_signup", "product_events", "Found events earlier than account signup_date"))
    if (pd.to_datetime(nps["survey_date"], errors="coerce") < pd.to_datetime(nps["account_id"].map(account_signup), errors="coerce")).any():
        issues.append(ValidationIssue("chronology_nps", "nps_responses", "Found NPS responses earlier than signup_date"))
    if (pd.to_datetime(invoices["invoice_date"], errors="coerce") < pd.to_datetime(invoices["account_id"].map(account_signup), errors="coerce")).any():
        issues.append(ValidationIssue("chronology_invoices", "invoices", "Found invoices earlier than signup_date"))

    if dataset.hidden_tables:
        invoice_internal = dataset.hidden_tables.get("invoice_internal")
        if invoice_internal is not None and not invoice_internal.empty:
            invoice_dt = pd.to_datetime(invoice_internal["invoice_date"], errors="coerce")
            sub_start = pd.to_datetime(invoice_internal["subscription_start_date"], errors="coerce")
            sub_end = pd.to_datetime(invoice_internal["subscription_end_date"], errors="coerce").fillna(pd.Timestamp.max.normalize())
            if ((invoice_dt < sub_start) | (invoice_dt > sub_end)).any():
                issues.append(ValidationIssue("invoice_subscription_alignment", "invoices", "Some invoices fall outside their subscription windows"))
        profiles = dataset.hidden_tables.get("account_profile")
        if profiles is not None and not profiles.empty and not events.empty:
            offsets = profiles.set_index("account_id")["utc_offset_hours"].to_dict()
            sample = events.head(min(10_000, len(events))).copy()
            sample["local_hour"] = (pd.to_datetime(sample["event_timestamp"], errors="coerce") + pd.to_timedelta(sample["account_id"].map(offsets).fillna(0), unit="h")).dt.hour
            share = sample["local_hour"].between(config.validation.local_hour_min, config.validation.local_hour_max).mean()
            metrics["event_local_hour_share"] = float(share)
            if share < 0.60:
                issues.append(ValidationIssue("event_local_hours", "product_events", f"Only {share:.2%} of sampled events land in expected local-hour windows"))


def _validate_dirty_defects(dataset: GeneratedTables, config: SaaSV3Config, issues: list[ValidationIssue], metrics: dict[str, object]) -> None:
    accounts = dataset.materialize("accounts")
    users = dataset.materialize("users")
    subscriptions = dataset.materialize("subscriptions")
    events = dataset.materialize("product_events")
    invoices = dataset.materialize("invoices")
    nps = dataset.materialize("nps_responses")

    account_signup = pd.to_datetime(accounts.set_index("account_id")["signup_date"], errors="coerce")
    invalid_user_dates = _count_invalid_datetimes(users["last_login_at"])
    invalid_event_dates = _count_invalid_datetimes(events["event_timestamp"])
    invalid_invoice_dates = _count_invalid_datetimes(invoices["invoice_date"])
    invalid_nps_dates = _count_invalid_datetimes(nps["survey_date"])
    defect_counts = {
        "null_company_names": int(accounts["company_name"].isna().sum()),
        "case_duplicate_emails": int(users["email"].astype(str).str.lower().duplicated(keep=False).sum()),
        "pre_signup_logins": int((pd.to_datetime(users["last_login_at"], errors="coerce") < pd.to_datetime(users["account_id"].map(account_signup), errors="coerce")).sum()),
        "plan_name_typos": int((~subscriptions["plan_name"].isin(config.plan_names)).sum()),
        "negative_monthly_amounts": int((pd.to_numeric(subscriptions["monthly_amount"], errors="coerce") < 0).sum()),
        "reversed_subscription_dates": int((pd.to_datetime(subscriptions["end_date"], errors="coerce") < pd.to_datetime(subscriptions["start_date"], errors="coerce")).sum()),
        "orphaned_product_events": int(((~events["account_id"].astype(str).isin(accounts["account_id"].astype(str))) | (~events["user_id"].astype(str).isin(users["user_id"].astype(str)))).sum()),
        "future_timestamps": int(
            (pd.to_datetime(users["last_login_at"], errors="coerce") > pd.Timestamp(config.history.as_of_date)).sum()
            + (pd.to_datetime(events["event_timestamp"], errors="coerce") > pd.Timestamp(config.history.as_of_date)).sum()
            + (pd.to_datetime(invoices["invoice_date"], errors="coerce") > pd.Timestamp(config.history.as_of_date)).sum()
            + (pd.to_datetime(nps["survey_date"], errors="coerce") > pd.Timestamp(config.history.as_of_date)).sum()
        ),
        "bad_date_formats": int(invalid_user_dates + invalid_event_dates + invalid_invoice_dates + invalid_nps_dates),
        "mixed_invoice_amount_formats": int(
            _count_mixed_amount_strings(invoices["amount_due"])
            + _count_mixed_amount_strings(invoices["amount_paid"])
        ),
        "out_of_range_nps_scores": int(((pd.to_numeric(nps["score"], errors="coerce") < 0) | (pd.to_numeric(nps["score"], errors="coerce") > 10)).sum()),
    }
    metrics["defect_counts"] = defect_counts

    _assert_defect_present("null_company_names", defect_counts["null_company_names"], len(accounts), config.defects.null_company_names.rate, config, issues)
    _assert_defect_present("case_duplicate_emails", defect_counts["case_duplicate_emails"], len(users), config.defects.case_duplicate_emails.rate, config, issues)
    _assert_defect_present("pre_signup_logins", defect_counts["pre_signup_logins"], len(users), config.defects.pre_signup_logins.rate, config, issues)
    _assert_defect_present("plan_name_typos", defect_counts["plan_name_typos"], len(subscriptions), config.defects.plan_name_typos.rate, config, issues)
    _assert_defect_present("negative_monthly_amounts", defect_counts["negative_monthly_amounts"], len(subscriptions), config.defects.negative_monthly_amounts.rate, config, issues)
    _assert_defect_present("reversed_subscription_dates", defect_counts["reversed_subscription_dates"], len(subscriptions), config.defects.reversed_subscription_dates.rate, config, issues)
    _assert_defect_present("orphaned_product_events", defect_counts["orphaned_product_events"], len(events), config.defects.orphaned_product_events.rate, config, issues)
    combined_temporal_total = max(1, len(users) + len(events) + len(invoices) + len(nps))
    _assert_defect_present("future_timestamps", defect_counts["future_timestamps"], combined_temporal_total, config.defects.future_timestamps.rate, config, issues)
    _assert_defect_present("bad_date_formats", defect_counts["bad_date_formats"], combined_temporal_total, config.defects.bad_date_formats.rate, config, issues)
    _assert_defect_present("mixed_invoice_amount_formats", defect_counts["mixed_invoice_amount_formats"], max(1, len(invoices) * 2), config.defects.mixed_invoice_amount_formats.rate, config, issues)
    _assert_defect_present("out_of_range_nps_scores", defect_counts["out_of_range_nps_scores"], len(nps), config.defects.out_of_range_nps_scores.rate, config, issues)


def _assert_unique(df: pd.DataFrame, column: str, table_name: str, issues: list[ValidationIssue]) -> None:
    if df[column].isna().any():
        issues.append(ValidationIssue("null_pk", table_name, f"{column} contains null values"))
    if not df[column].is_unique:
        issues.append(ValidationIssue("duplicate_pk", table_name, f"{column} contains duplicate values"))


def _count_invalid_datetimes(series: pd.Series) -> int:
    non_null = series.notna()
    if not non_null.any():
        return 0
    parsed = pd.to_datetime(series[non_null], errors="coerce")
    return int(parsed.isna().sum())


def _count_mixed_amount_strings(series: pd.Series) -> int:
    count = 0
    for value in series.dropna().astype(str).tolist():
        if "," in value or any(ch.isalpha() for ch in value):
            count += 1
    return count


def _assert_defect_present(name: str, count: int, total: int, rate: float, config: SaaSV3Config, issues: list[ValidationIssue]) -> None:
    if rate <= 0:
        return
    expected = max(1, int(round(total * rate)))
    tolerance = max(1, int(round(expected * config.validation.defect_tolerance)))
    if count < max(1, expected - tolerance):
        issues.append(ValidationIssue("defect_rate_low", None, f"{name} produced {count} rows; expected about {expected}"))
