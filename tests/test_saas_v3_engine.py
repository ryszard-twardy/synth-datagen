from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.saas_v3.config import OutputMode, load_config
from src.saas_v3.engine import SaaSV3Engine
from src.saas_v3.ids import pattern_for
from src.saas_v3.validate import validate_generated_dataset


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = REPO_ROOT / "configs" / "saas_v3.smoke.yaml"


def _smoke_config(tmp_path):
    config = load_config(SMOKE_CONFIG)
    config.output.root_dir = tmp_path / "saas_v3"
    return config


@pytest.fixture()
def smoke_result(tmp_path):
    config = _smoke_config(tmp_path)
    engine = SaaSV3Engine(config)
    return config, engine.generate(OutputMode.BOTH)


def test_saas_v3_deterministic_core_tables(tmp_path) -> None:
    config_a = _smoke_config(tmp_path / "a")
    config_b = _smoke_config(tmp_path / "b")
    result_a = SaaSV3Engine(config_a).generate(OutputMode.BOTH)
    result_b = SaaSV3Engine(config_b).generate(OutputMode.BOTH)

    for table_name in ["accounts", "users", "subscriptions", "invoices", "support_tickets", "nps_responses"]:
        left = result_a.clean.materialize(table_name)
        right = result_b.clean.materialize(table_name)
        pd.testing.assert_frame_equal(left, right)

    pd.testing.assert_frame_equal(result_a.clean.materialize("product_events"), result_b.clean.materialize("product_events"))


def test_saas_v3_clean_validation_and_id_formats(smoke_result) -> None:
    config, result = smoke_result
    report = validate_generated_dataset(result.clean, config, "clean")
    assert report.passed, report.issues

    accounts = result.clean.materialize("accounts")
    users = result.clean.materialize("users")
    subscriptions = result.clean.materialize("subscriptions")
    events = result.clean.materialize("product_events")
    invoices = result.clean.materialize("invoices")
    tickets = result.clean.materialize("support_tickets")
    nps = result.clean.materialize("nps_responses")

    assert accounts["account_id"].astype(str).str.fullmatch(pattern_for("account_id")).all()
    assert users["user_id"].astype(str).str.fullmatch(pattern_for("user_id")).all()
    assert subscriptions["subscription_id"].astype(str).str.fullmatch(pattern_for("subscription_id")).all()
    assert events["event_id"].astype(str).str.fullmatch(pattern_for("event_id")).all()
    assert invoices["invoice_id"].astype(str).str.fullmatch(pattern_for("invoice_id")).all()
    assert tickets["ticket_id"].astype(str).str.fullmatch(pattern_for("ticket_id")).all()
    assert nps["response_id"].astype(str).str.fullmatch(pattern_for("response_id")).all()


def test_saas_v3_dirty_validation_and_required_defects(smoke_result) -> None:
    config, result = smoke_result
    assert result.dirty is not None
    report = validate_generated_dataset(result.dirty, config, "dirty")
    assert report.passed, report.issues

    counts = report.metrics["defect_counts"]
    required = {
        "null_company_names",
        "case_duplicate_emails",
        "pre_signup_logins",
        "plan_name_typos",
        "negative_monthly_amounts",
        "reversed_subscription_dates",
        "orphaned_product_events",
        "future_timestamps",
        "bad_date_formats",
        "mixed_invoice_amount_formats",
        "out_of_range_nps_scores",
    }
    assert required == set(counts)
    assert all(counts[name] > 0 for name in required)
