from __future__ import annotations

import pandas as pd

from synth_datagen.config import Scenario
from tests.helpers import DEFAULT_SMALL_OVERRIDES, generate_scenario_dfs


def test_saas_account_mrr_matches_active_subscriptions(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.SAAS, tmp_path)
    active = dfs["subscriptions"].loc[
        dfs["subscriptions"]["status"].isin(
            ["active", "past_due", "trialing", "paused"]
        )
    ]
    expected = active.groupby("account_id")["mrr"].sum().round(2)
    actual = dfs["accounts"].copy()
    actual["expected_mrr"] = actual["account_id"].map(expected).fillna(0.0).round(2)
    assert (actual["mrr"].round(2) == actual["expected_mrr"]).all()


def test_saas_users_and_activity_follow_entity_lifecycle(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.SAAS, tmp_path)
    users = dfs["users"].merge(
        dfs["accounts"][["account_id", "domain", "created_at"]],
        on="account_id",
        how="left",
        suffixes=("", "_account"),
    )
    assert (
        pd.to_datetime(users["created_at"])
        >= pd.to_datetime(users["created_at_account"])
    ).all()
    assert users.apply(
        lambda row: str(row["email"]).endswith(f"@{row['domain']}"), axis=1
    ).all()

    events = dfs["events"].merge(
        users[["user_id", "created_at"]], on="user_id", how="left"
    )
    assert (
        pd.to_datetime(events["occurred_at"]) >= pd.to_datetime(events["created_at"])
    ).all()

    usage = dfs["feature_usage"].merge(
        users[["user_id", "created_at"]], on="user_id", how="left"
    )
    assert (
        pd.to_datetime(usage["used_at"]) >= pd.to_datetime(usage["created_at"])
    ).all()


def test_saas_invoices_stay_within_subscription_window(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.SAAS, tmp_path)
    merged = dfs["invoices"].merge(
        dfs["subscriptions"][["sub_id", "started_at", "ended_at"]],
        on="sub_id",
        how="left",
    )
    issued = pd.to_datetime(merged["issued_at"])
    started = pd.to_datetime(merged["started_at"])
    ended = pd.to_datetime(merged["ended_at"]).fillna(pd.Timestamp.max.normalize())
    assert (issued >= started).all()
    assert (issued <= ended).all()


def test_saas_feature_usage_respects_plan_minimum(tmp_path) -> None:
    dfs, _ = generate_scenario_dfs(Scenario.SAAS, tmp_path)
    plan_rank = {
        "free": 0,
        "starter": 1,
        "growth": 2,
        "professional": 3,
        "enterprise": 4,
    }
    usage = (
        dfs["feature_usage"]
        .merge(dfs["users"][["user_id", "account_id"]], on="user_id", how="left")
        .merge(dfs["features"][["feature_id", "plan_min"]], on="feature_id", how="left")
    )
    subscriptions = dfs["subscriptions"].copy()
    subscriptions["started_at"] = pd.to_datetime(subscriptions["started_at"])
    subscriptions["ended_at"] = pd.to_datetime(subscriptions["ended_at"]).fillna(
        pd.Timestamp.max.normalize()
    )
    plan_by_row = []
    for row in usage.itertuples(index=False):
        used_at = pd.Timestamp(row.used_at)
        active = subscriptions[
            (subscriptions["account_id"] == row.account_id)
            & (subscriptions["started_at"] <= used_at)
            & (subscriptions["ended_at"] >= used_at)
        ]
        if active.empty:
            plan_by_row.append("free")
        else:
            latest = active.sort_values("started_at").iloc[-1]
            plan_by_row.append(str(latest["plan"]))
    assert (
        pd.Series(plan_by_row).map(plan_rank).ge(usage["plan_min"].map(plan_rank)).all()
    )


def test_saas_features_honor_requested_row_count(tmp_path) -> None:
    overrides = dict(DEFAULT_SMALL_OVERRIDES[Scenario.SAAS])
    overrides["features"] = 40
    dfs, _ = generate_scenario_dfs(Scenario.SAAS, tmp_path, row_overrides=overrides)
    assert len(dfs["features"]) == 40
