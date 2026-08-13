from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.modules.ai_reasoning.domain.activity_window import ActivityWindowPolicy, project
from app.modules.ai_reasoning.domain.activity_window import ActivityWindowReader
from app.shared.exceptions import ValidationError

UTC = timezone.utc
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def row(kind, when, receipt=None, ident=None):
    return {"type": kind, "id": ident or uuid4(), "source_time": when, "receipt_time": receipt}


def test_window_boundaries_timezone_and_stable_tie_breaking():
    result = project(ActivityWindowPolicy(max_activities=10), [row("Z", BASE - timedelta(minutes=30), ident="b"), row("A", BASE + timedelta(minutes=60), ident="a"), row("A", BASE, ident="z"), row("A", BASE, ident="a")], BASE, BASE)
    assert [item["id"] for item in result["activities"]] == ["b", "a", "z", "a"]
    assert all(item["effective_timestamp"].endswith("+00:00") for item in result["activities"])
    assert "EQUAL_TIMESTAMP_TIE" in result["activities"][2]["uncertainty"]


def test_missing_invalid_future_skew_outside_and_limit_are_distinct():
    future = BASE + timedelta(minutes=10)
    result = project(ActivityWindowPolicy(max_activities=10), [row("A", None, BASE), row("B", future, BASE), row("C", BASE + timedelta(hours=2)), row("D", BASE), row("E", BASE + timedelta(minutes=1))], BASE, BASE, BASE)
    by_type = {item["type"]: item for item in result["activities"]}
    assert by_type["A"]["time_basis"] == "RECEIPT" and "SOURCE_TIME_MISSING" in by_type["A"]["uncertainty"]
    assert "FUTURE_TIME_SUSPECTED" in by_type["B"]["uncertainty"]
    assert by_type["C"]["position"] == "OUTSIDE" and "OUTSIDE_WINDOW" in by_type["C"]["uncertainty"]
    assert project(ActivityWindowPolicy(max_activities=1), [row("D", BASE), row("E", BASE + timedelta(minutes=1))], BASE, BASE)["omitted"] == 1


def test_missing_anchor_determinism_and_invalid_policy():
    assert project(ActivityWindowPolicy(), [row("A", BASE)], None, None)["warnings"] == ["ANCHOR_MISSING"]
    payload = [row("A", BASE, BASE, "a")]
    assert project(ActivityWindowPolicy(), payload, BASE, BASE, BASE) == project(ActivityWindowPolicy(), payload, BASE, BASE, BASE)
    with pytest.raises(ValidationError): ActivityWindowPolicy(before_minutes=0)


def test_skew_and_receipt_fallback_do_not_assert_source_chronology():
    result = project(ActivityWindowPolicy(), [row("A", BASE + timedelta(minutes=20), BASE)], BASE, BASE, BASE)
    item = result["activities"][0]
    assert item["time_basis"] == "RECEIPT"
    assert {"CLOCK_SKEW_SUSPECTED", "CONFLICTING_SENSOR_TIME", "FUTURE_TIME_SUSPECTED", "RECEIPT_TIME_FALLBACK"} <= set(item["uncertainty"])


def test_invalid_source_out_of_order_and_observation_warnings_are_deterministic():
    naive = datetime(2026, 1, 1, 12, 0)
    result = project(ActivityWindowPolicy(), [row("A", naive), row("B", BASE - timedelta(minutes=20), BASE)], BASE, BASE, BASE)
    by_type = {item["type"]: item for item in result["activities"]}
    assert by_type["A"]["time_basis"] == "NONE" and "SOURCE_TIME_INVALID" in by_type["A"]["uncertainty"]
    assert {"OUT_OF_ORDER_ARRIVAL", "CONFLICTING_SENSOR_TIME"} <= set(by_type["B"]["uncertainty"])
    assert "AFTER_ACTIVITY_NOT_OBSERVED" in result["warnings"]
