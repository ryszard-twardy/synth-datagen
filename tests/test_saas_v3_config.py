from __future__ import annotations

from pathlib import Path

from synth_datagen.saas_v3.config import load_config


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "saas_v3.default.yaml"
AUDIT_CONFIG = REPO_ROOT / "configs" / "saas_v3.audit_093.yaml"


def test_saas_v3_default_config_uses_requested_business_defaults() -> None:
    config = load_config(DEFAULT_CONFIG)

    assert config.row_targets.accounts == 1500
    assert config.history.lookback_years == 2.5
    assert [plan.name for plan in config.plans] == [
        "Starter",
        "Professional",
        "Enterprise",
    ]
    assert [plan.monthly_price for plan in config.plans] == [49.0, 149.0, 399.0]
    assert config.output.root_dir.as_posix().endswith("out/saas_v3")
    assert config.defects.bad_date_formats.rate == 0.003


def test_saas_v3_audit_config_uses_093_percent_per_check() -> None:
    config = load_config(AUDIT_CONFIG)

    assert config.output.formats == ["csv"]
    assert config.row_targets.accounts == 300
    assert config.row_targets.users == 2000
    assert config.row_targets.subscriptions == 1000
    assert config.row_targets.product_events == 100000
    assert config.row_targets.invoices == 4000
    assert config.row_targets.support_tickets == 1500
    assert config.row_targets.nps_responses == 500
    assert all(rate == 0.0093 for rate in config.defects.active_rates().values())
