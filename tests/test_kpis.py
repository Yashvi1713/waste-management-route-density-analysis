from __future__ import annotations

import pandas as pd
import pytest

from kpis import fuel_kpis, route_kpis, summary_kpis


@pytest.fixture
def worked_example() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "service_date": pd.to_datetime(["2026-07-01", "2026-07-02"]).date,
            "route_id": ["R-01", "R-01"],
            "truck_id": ["T-001", "T-001"],
            "depot": ["Vaughan", "Vaughan"],
            "service_line": ["residential", "residential"],
            "fuel_type": ["CNG", "CNG"],
            "completed_stops": [3, 5],
            "missed_stops": [1, 0],
            "tons": [1.5, 2.5],
            "shift_hours": [2.0, 3.0],
            "km_driven": [10.0, 20.0],
            "labour_cost": [60.0, 90.0],
            "fuel_cost": [6.0, 12.0],
            "maint_cost": [4.0, 8.0],
            "total_cost": [70.0, 110.0],
        }
    )


def test_worked_example(worked_example: pd.DataFrame) -> None:
    summary = summary_kpis(worked_example)
    fuel = fuel_kpis(worked_example).iloc[0]
    assert summary["completed_stops"] == 8
    assert summary["missed_stops"] == 1
    assert summary["missed_rate"] == pytest.approx(0.1111, abs=0.00005)
    assert summary["stops_per_hour"] == pytest.approx(1.6)
    assert summary["tons_per_hour"] == pytest.approx(0.8)
    assert summary["total_cost"] == pytest.approx(180)
    assert summary["cost_per_stop"] == pytest.approx(22.5)
    assert fuel["fuel_cost_per_km"] == pytest.approx(0.6)
    assert fuel["maint_cost_per_km"] == pytest.approx(0.4)
    assert fuel["vehicle_cost_per_km"] == pytest.approx(1.0)


def test_ratios_are_sum_over_sum(worked_example: pd.DataFrame) -> None:
    actual = summary_kpis(worked_example)["cost_per_stop"]
    assert actual == pytest.approx(22.5)
    assert actual != pytest.approx(22.6667, abs=0.00005)


def test_total_pickups_is_completed_plus_missed(worked_example: pd.DataFrame) -> None:
    summary = summary_kpis(worked_example)
    assert summary["total_pickups"] == 9
    assert summary["total_pickups"] == summary["completed_stops"] + summary["missed_stops"]


def test_route_median_never_crosses_service_lines() -> None:
    rows = pd.DataFrame(
        {
            "service_date": pd.to_datetime(["2026-07-01"] * 4).date,
            "route_id": ["R-01", "R-02", "R-31", "R-32"],
            "truck_id": ["T-001", "T-002", "T-031", "T-032"],
            "depot": ["Vaughan"] * 4,
            "service_line": ["residential", "residential", "commercial", "commercial"],
            "fuel_type": ["CNG"] * 4,
            "completed_stops": [10] * 4,
            "missed_stops": [0] * 4,
            "tons": [1.0] * 4,
            "shift_hours": [1.0] * 4,
            "km_driven": [10.0] * 4,
            "labour_cost": [0.0] * 4,
            "fuel_cost": [0.0] * 4,
            "maint_cost": [0.0] * 4,
            "total_cost": [10.0, 30.0, 100.0, 300.0],
        }
    )
    result = route_kpis(rows).set_index("route_id")
    assert result.loc["R-01", "median_cost_per_stop"] == pytest.approx(2.0)
    assert result.loc["R-31", "median_cost_per_stop"] == pytest.approx(20.0)

