from __future__ import annotations

import pandas as pd

from src.config import Scenario
from tests.helpers import generate_scenario_dfs


def test_fintech_accounts_follow_customer_lifecycle(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.FINTECH, tmp_path)
    merged = dfs["accounts"].merge(
        dfs["customers"][["customer_id", "created_at"]].rename(columns={"created_at": "customer_created_at"}),
        on="customer_id",
        how="left",
    )
    assert (pd.to_datetime(merged["opened_at"]) >= pd.to_datetime(merged["customer_created_at"])).all()
    closed_mask = merged["closed_at"].notna()
    assert (pd.to_datetime(merged.loc[closed_mask, "closed_at"]) >= pd.to_datetime(merged.loc[closed_mask, "opened_at"])).all()


def test_fintech_transactions_are_chronological_per_account(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.FINTECH, tmp_path)
    transactions = dfs["transactions"].merge(
        dfs["accounts"][["account_id", "opened_at", "closed_at"]],
        on="account_id",
        how="left",
    )
    created = pd.to_datetime(transactions["created_at"])
    opened = pd.to_datetime(transactions["opened_at"])
    assert (created >= opened).all()
    closed_mask = transactions["closed_at"].notna()
    assert (created[closed_mask] <= pd.to_datetime(transactions.loc[closed_mask, "closed_at"])).all()

    for _, group in transactions.sort_values(["account_id", "created_at", "transaction_id"]).groupby("account_id"):
        prev_balance = None
        for row in group.itertuples(index=False):
            if prev_balance is not None:
                assert round(prev_balance + float(row.amount), 2) == round(float(row.balance_after), 2)
            prev_balance = float(row.balance_after)


def test_fintech_merchants_and_loans_are_plausible(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.FINTECH, tmp_path)
    transactions = dfs["transactions"]
    assert transactions.loc[transactions["tx_type"].isin(["purchase", "refund"]), "merchant_id"].notna().all()
    assert transactions.loc[~transactions["tx_type"].isin(["purchase", "refund"]), "merchant_id"].isna().all()

    loans = dfs["loans"]
    assert (loans.loc[loans["status"] == "paid_off", "outstanding"] == 0).all()


def test_fintech_cards_follow_account_lifecycle(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.FINTECH, tmp_path)
    cards = dfs["cards"].merge(dfs["accounts"][["account_id", "opened_at", "is_active"]], on="account_id", how="left")
    assert (pd.to_datetime(cards["issue_date"]) >= pd.to_datetime(cards["opened_at"]).dt.normalize()).all()
    expired_active = (pd.to_datetime(cards["expiry_date"]) < pd.Timestamp("2025-12-31")) & cards["is_active_x"]
    assert not expired_active.any()

