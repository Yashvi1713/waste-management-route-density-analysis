"""Streamlit dashboard for synthetic route economics and data quality."""

from __future__ import annotations

import os

import altair as alt
import pandas as pd
import streamlit as st

from analytics import load_dashboard_data
from kpis import filter_rows, fuel_kpis, route_kpis, summary_kpis


st.set_page_config(page_title="Route Density Lab", layout="wide")
st.title("Route Density Lab")
st.warning("Synthetic data")
backend = os.environ.get("ANALYTICS_BACKEND", "local").lower()
st.caption(f"Analytics backend: {backend}")


@st.cache_data(ttl=300)
def _load(mode: str) -> dict[str, pd.DataFrame]:
    return load_dashboard_data(mode)


data = _load(backend)
route_days = data["route_days"]

st.sidebar.header("Filters")
depot = st.sidebar.selectbox("Depot", ["All", *sorted(route_days.depot.unique())])
service_line = st.sidebar.selectbox(
    "Service line", ["All", *sorted(route_days.service_line.unique())]
)
fuel_type = st.sidebar.selectbox(
    "Fuel type", ["All", *sorted(route_days.fuel_type.unique())]
)
minimum_date = min(route_days.service_date)
maximum_date = max(route_days.service_date)
date_range = st.sidebar.date_input(
    "Date range", value=(minimum_date, maximum_date), min_value=minimum_date, max_value=maximum_date
)
start, end = date_range if len(date_range) == 2 else (minimum_date, maximum_date)
filters = {
    "depot": depot,
    "service_line": service_line,
    "fuel_type": fuel_type,
    "start": start,
    "end": end,
}
filtered = filter_rows(route_days, **filters)
summary = summary_kpis(filtered)
routes = route_kpis(filtered)
fleet = fuel_kpis(filtered)
flagged = routes.loc[routes.is_flagged]

overview, route_tab, fleet_tab, quality_tab = st.tabs(
    ["Overview", "Routes", "Fleet", "Data quality"]
)

with overview:
    columns = st.columns(6)
    columns[0].metric("Cost per stop", f"${summary['cost_per_stop']:,.2f}")
    columns[1].metric("Stops per hour", f"{summary['stops_per_hour']:,.1f}")
    columns[2].metric("Missed-pickup rate", f"{summary['missed_rate']:.2%}")
    columns[3].metric("Total pickups", f"{summary['total_pickups']:,}")
    columns[4].metric("Flagged routes", f"{len(flagged):,}")
    savings = float(flagged.annual_savings.sum())
    columns[5].metric("Annual savings", f"${savings:,.0f}")
    st.info(
        f"Bringing the {len(flagged)} flagged routes to their service-line median "
        f"saves about ${savings:,.0f} a year. This is an upper-bound estimate "
        "based on synthetic data."
    )
    pickup_status = pd.DataFrame(
        {
            "status": ["Completed", "Missed"],
            "pickups": [summary["completed_stops"], summary["missed_stops"]],
        }
    )
    pickup_donut = (
        alt.Chart(pickup_status)
        .mark_arc(innerRadius=70)
        .encode(
            theta=alt.Theta("pickups:Q", title="Pickup attempts"),
            color=alt.Color(
                "status:N",
                title="Status",
                scale=alt.Scale(
                    domain=["Completed", "Missed"],
                    range=["#2ca02c", "#d62728"],
                ),
            ),
            tooltip=["status:N", alt.Tooltip("pickups:Q", format=",")],
        )
        .properties(title="Pickup attempts by status")
    )
    st.altair_chart(pickup_donut, use_container_width=True)

with route_tab:
    st.subheader("Ten routes with the highest cost per stop")
    top = routes.nlargest(10, "cost_per_stop").copy()
    top["status"] = top.is_flagged.map({True: "Flagged", False: "Not flagged"})
    chart = (
        alt.Chart(top)
        .mark_bar()
        .encode(
            x=alt.X("cost_per_stop:Q", title="Cost per completed stop ($)"),
            y=alt.Y("route_id:N", sort="-x", title="Route"),
            color=alt.Color("status:N", scale=alt.Scale(domain=["Flagged", "Not flagged"], range=["#d62728", "#4c78a8"])),
            tooltip=["route_id", "service_line", "cost_per_stop", "median_cost_per_stop", "flag_reason"],
        )
    )
    st.altair_chart(chart, use_container_width=True)
    st.caption("Routes are compared only with the median cost per stop of their own service line.")
    st.dataframe(routes, use_container_width=True, hide_index=True)

with fleet_tab:
    st.subheader("CNG versus diesel")
    fleet_long = fleet.melt(
        id_vars="fuel_type",
        value_vars=["fuel_cost_per_km", "maint_cost_per_km", "vehicle_cost_per_km"],
        var_name="measure",
        value_name="cost_per_km",
    )
    fleet_chart = (
        alt.Chart(fleet_long)
        .mark_bar()
        .encode(
            x=alt.X("fuel_type:N", title="Fuel type"),
            y=alt.Y("cost_per_km:Q", title="Cost per kilometre ($)"),
            color="fuel_type:N",
            column=alt.Column("measure:N", title=None),
            tooltip=["fuel_type", "measure", "cost_per_km"],
        )
    )
    st.altair_chart(fleet_chart, use_container_width=True)
    st.dataframe(fleet, use_container_width=True, hide_index=True)

with quality_tab:
    audit = data["audit"].copy()
    audit["reconciles"] = (
        audit.raw_rows
        == audit.silver_rows + audit.rejected_rows + audit.duplicates_removed
    )
    st.metric("Sources reconciled", f"{int(audit.reconciles.sum())}/{len(audit)}")
    st.dataframe(audit, use_container_width=True, hide_index=True)
    st.subheader("Reject counts by rule")
    st.dataframe(data["reject_summary"], use_container_width=True, hide_index=True)
    st.subheader("Sample rejected records")
    st.dataframe(data["rejects"].head(20), use_container_width=True, hide_index=True)
    st.caption("All data and displayed numbers are synthetic.")
