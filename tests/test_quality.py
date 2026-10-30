from __future__ import annotations

import pandas as pd

from quality import classify_pickup_rejects, classify_route_day_rejects, deduplicate


def test_duplicates_removed(good_pickup: pd.DataFrame) -> None:
    rows = pd.concat([good_pickup, good_pickup], ignore_index=True)
    kept, removed = deduplicate(rows, ["pickup_id"])
    assert len(kept) == 1
    assert removed == 1


def test_tons_rule(good_pickup: pd.DataFrame, truck_ids: set[str]) -> None:
    bad = good_pickup.copy()
    bad.loc[0, "tons"] = "15.5"
    assert classify_pickup_rejects(bad, truck_ids).iloc[0] == "tons_out_of_range"


def test_unknown_truck_rule(good_pickup: pd.DataFrame, truck_ids: set[str]) -> None:
    bad = good_pickup.copy()
    bad.loc[0, "truck_id"] = "T-999"
    assert classify_pickup_rejects(bad, truck_ids).iloc[0] == "unknown_truck"


def test_outside_shift_rule(good_pickup: pd.DataFrame, truck_ids: set[str]) -> None:
    bad = good_pickup.copy()
    bad.loc[0, "completed_at"] = "2026-07-01 03:15:00"
    assert classify_pickup_rejects(bad, truck_ids).iloc[0] == "outside_shift"


def test_bad_status_rule(good_pickup: pd.DataFrame, truck_ids: set[str]) -> None:
    bad = good_pickup.copy()
    bad.loc[0, "status"] = "COMPLETE"
    assert classify_pickup_rejects(bad, truck_ids).iloc[0] == "bad_status"


def test_route_day_rule(truck_ids: set[str]) -> None:
    rows = pd.DataFrame(
        [{"truck_id": "T-001", "shift_hours": "10", "km_driven": "-1"}]
    )
    assert classify_route_day_rejects(rows, truck_ids).iloc[0] == "nonpositive_measure"


def test_first_failed_rule_wins(good_pickup: pd.DataFrame, truck_ids: set[str]) -> None:
    bad = good_pickup.copy()
    bad.loc[0, ["status", "truck_id", "tons"]] = ["unknown", "T-999", "15.5"]
    assert classify_pickup_rejects(bad, truck_ids).iloc[0] == "bad_status"

