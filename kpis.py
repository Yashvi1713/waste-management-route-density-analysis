"""Single source of truth for filtered, sum-over-sum KPI calculations."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


FILTER_COLUMNS = ("depot", "service_line", "fuel_type")


def filter_rows(
    frame: pd.DataFrame,
    depot: str | None = None,
    service_line: str | None = None,
    fuel_type: str | None = None,
    start: date | str | None = None,
    end: date | str | None = None,
) -> pd.DataFrame:
    """Apply optional dashboard filters while preserving date semantics."""
    result = frame.copy()
    for column, value in zip(FILTER_COLUMNS, (depot, service_line, fuel_type)):
        if value and value != "All":
            result = result.loc[result[column].eq(value)]
    dates = pd.to_datetime(result["service_date"]).dt.date
    if start is not None:
        start_date = pd.Timestamp(start).date()
        result = result.loc[dates >= start_date]
        dates = dates.loc[result.index]
    if end is not None:
        end_date = pd.Timestamp(end).date()
        result = result.loc[dates <= end_date]
    return result


def _divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def summary_kpis(frame: pd.DataFrame, **filters) -> dict[str, float]:
    """Calculate overall additive totals and their sum-over-sum ratios."""
    rows = filter_rows(frame, **filters) if filters else frame
    completed = int(rows["completed_stops"].sum())
    missed = int(rows["missed_stops"].sum())
    tons = float(rows["tons"].sum())
    hours = float(rows["shift_hours"].sum())
    total_cost = float(rows["total_cost"].sum())
    return {
        "completed_stops": completed,
        "missed_stops": missed,
        "total_pickups": completed + missed,
        "tons": tons,
        "shift_hours": hours,
        "total_cost": total_cost,
        "stops_per_hour": _divide(completed, hours),
        "tons_per_hour": _divide(tons, hours),
        "missed_rate": _divide(missed, completed + missed),
        "cost_per_stop": _divide(total_cost, completed),
    }


def fuel_kpis(frame: pd.DataFrame, **filters) -> pd.DataFrame:
    """Calculate sum-over-sum vehicle KPIs grouped by fuel type."""
    rows = filter_rows(frame, **filters) if filters else frame
    grouped = (
        rows.groupby("fuel_type", as_index=False)[["fuel_cost", "maint_cost", "km_driven"]]
        .sum()
        .sort_values("fuel_type")
        .reset_index(drop=True)
    )
    grouped["fuel_cost_per_km"] = grouped.apply(
        lambda row: _divide(row.fuel_cost, row.km_driven), axis=1
    )
    grouped["maint_cost_per_km"] = grouped.apply(
        lambda row: _divide(row.maint_cost, row.km_driven), axis=1
    )
    grouped["vehicle_cost_per_km"] = grouped.apply(
        lambda row: _divide(row.fuel_cost + row.maint_cost, row.km_driven), axis=1
    )
    return grouped


def _percent_rank(series: pd.Series) -> pd.Series:
    if len(series) <= 1:
        return pd.Series(0.0, index=series.index)
    return (series.rank(method="min") - 1) / (len(series) - 1)


def route_kpis(frame: pd.DataFrame, **filters) -> pd.DataFrame:
    """Calculate route metrics, service-line medians, savings, and flags."""
    rows = filter_rows(frame, **filters) if filters else frame
    dimensions = (
        rows.sort_values("service_date")
        .groupby("route_id", as_index=False)[["depot", "service_line"]]
        .first()
    )
    totals = rows.groupby("route_id", as_index=False).agg(
        completed_stops=("completed_stops", "sum"),
        missed_stops=("missed_stops", "sum"),
        tons=("tons", "sum"),
        shift_hours=("shift_hours", "sum"),
        total_cost=("total_cost", "sum"),
    )
    result = dimensions.merge(totals, on="route_id", validate="one_to_one")
    result["service_days_in_data"] = int(rows["service_date"].nunique())
    result["stops_per_hour"] = result.apply(
        lambda row: _divide(row.completed_stops, row.shift_hours), axis=1
    )
    result["tons_per_hour"] = result.apply(
        lambda row: _divide(row.tons, row.shift_hours), axis=1
    )
    result["missed_rate"] = result.apply(
        lambda row: _divide(row.missed_stops, row.completed_stops + row.missed_stops), axis=1
    )
    result["cost_per_stop"] = result.apply(
        lambda row: _divide(row.total_cost, row.completed_stops), axis=1
    )
    result["median_cost_per_stop"] = result.groupby("service_line")[
        "cost_per_stop"
    ].transform("median")
    excess = (result["cost_per_stop"] - result["median_cost_per_stop"]).clip(lower=0)
    result["annual_savings"] = (
        excess * result["completed_stops"] * 260 / result["service_days_in_data"]
    )
    density_rank = result.groupby("service_line")["stops_per_hour"].transform(_percent_rank)
    cost_rank = result.groupby("service_line")["cost_per_stop"].transform(_percent_rank)
    result["low_density"] = density_rank.le(0.10)
    result["high_cost"] = cost_rank.ge(0.90)
    result["is_flagged"] = result["low_density"] | result["high_cost"]
    result["flag_reason"] = np.select(
        [
            result["low_density"] & result["high_cost"],
            result["low_density"],
            result["high_cost"],
        ],
        ["low_density+high_cost", "low_density", "high_cost"],
        default="",
    )
    return result.sort_values("route_id").reset_index(drop=True)

