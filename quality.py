"""Shared data-quality rules for Bronze operational records."""

from __future__ import annotations

import pandas as pd


def deduplicate(frame: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, int]:
    """Keep the last deterministic record for *keys* and return removal count."""
    duplicate_mask = frame.duplicated(keys, keep="last")
    return frame.loc[~duplicate_mask].copy(), int(duplicate_mask.sum())


def bad_status(frame: pd.DataFrame) -> pd.Series:
    return ~frame["status"].isin(["completed", "missed"])


def unknown_truck(frame: pd.DataFrame, truck_ids: set[str]) -> pd.Series:
    return ~frame["truck_id"].isin(truck_ids)


def tons_out_of_range(frame: pd.DataFrame) -> pd.Series:
    tons = pd.to_numeric(frame["tons"], errors="coerce")
    completed = frame["status"].eq("completed")
    return completed & (tons.isna() | tons.lt(0) | tons.gt(12))


def outside_shift(frame: pd.DataFrame) -> pd.Series:
    completed = frame["status"].eq("completed")
    values = frame["completed_at"].fillna("").astype(str)
    valid = values.str.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    clock = values.str.slice(11, 16)
    return completed & (~valid | clock.lt("05:00") | clock.gt("20:00"))


def nonpositive_measure(frame: pd.DataFrame) -> pd.Series:
    hours = pd.to_numeric(frame["shift_hours"], errors="coerce")
    km = pd.to_numeric(frame["km_driven"], errors="coerce")
    return hours.isna() | km.isna() | hours.le(0) | km.le(0)


def _first_failure(index: pd.Index, rules: list[tuple[str, pd.Series]]) -> pd.Series:
    result = pd.Series(pd.NA, index=index, dtype="string")
    for name, mask in rules:
        result.loc[result.isna() & mask.fillna(True)] = name
    return result


def classify_pickup_rejects(frame: pd.DataFrame, truck_ids: set[str]) -> pd.Series:
    """Return the first failed pickup rule in contract order."""
    return _first_failure(
        frame.index,
        [
            ("bad_status", bad_status(frame)),
            ("unknown_truck", unknown_truck(frame, truck_ids)),
            ("tons_out_of_range", tons_out_of_range(frame)),
            ("outside_shift", outside_shift(frame)),
        ],
    )


def classify_route_day_rejects(frame: pd.DataFrame, truck_ids: set[str]) -> pd.Series:
    """Return the first failed route-day rule in contract order."""
    return _first_failure(
        frame.index,
        [
            ("unknown_truck", unknown_truck(frame, truck_ids)),
            ("nonpositive_measure", nonpositive_measure(frame)),
        ],
    )

