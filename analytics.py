"""Dashboard data adapter for local DuckDB and AWS Athena Gold data."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import boto3
import duckdb
import pandas as pd

from config import DATA_DIR, layer_paths


def _local_data(data_dir: str | Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    _, silver, gold = layer_paths(data_dir)
    connection = duckdb.connect()
    frames = {
        "route_days": connection.execute(
            f"SELECT * FROM read_parquet('{gold / 'mart_route_day.parquet'}')"
        ).fetchdf(),
        "audit": connection.execute(
            f"SELECT * FROM read_parquet('{silver / 'load_audit.parquet'}')"
        ).fetchdf(),
        "rejects": connection.execute(
            f"SELECT * FROM read_parquet('{silver / 'rejects.parquet'}')"
        ).fetchdf(),
        "reject_summary": connection.execute(
            f"SELECT * FROM read_parquet('{gold / 'mart_rejects_summary.parquet'}')"
        ).fetchdf(),
    }
    connection.close()
    frames["route_days"]["service_date"] = pd.to_datetime(
        frames["route_days"]["service_date"]
    ).dt.date
    return frames


def _athena_query(sql: str, database: str) -> pd.DataFrame:
    """Execute a compact Athena query and return its CSV result."""
    region = os.environ.get("AWS_REGION", "eu-west-1")
    workgroup = os.environ.get("ATHENA_WORKGROUP", "route-lab")
    athena = boto3.client("athena", region_name=region)
    query_id = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )["QueryExecutionId"]
    while True:
        execution = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(1)
    if state != "SUCCEEDED":
        reason = execution["Status"].get("StateChangeReason", "unknown failure")
        raise RuntimeError(f"Athena query {state}: {reason}")
    location = execution["ResultConfiguration"]["OutputLocation"]
    bucket, key = location.removeprefix("s3://").split("/", 1)
    body = boto3.client("s3", region_name=region).get_object(Bucket=bucket, Key=key)["Body"].read()
    return pd.read_csv(io.BytesIO(body))


def _athena_data() -> dict[str, pd.DataFrame]:
    silver_db = os.environ.get("AWS_SILVER_DATABASE", "route_lab_silver")
    gold_db = os.environ.get("AWS_GOLD_DATABASE", "route_lab_gold")
    route_days = _athena_query(
        """SELECT CAST(service_date AS DATE) AS service_date, route_id, truck_id,
                  depot, service_line, fuel_type, completed_stops, missed_stops,
                  tons, shift_hours, km_driven, labour_cost, fuel_cost,
                  maint_cost, total_cost FROM mart_route_day""",
        gold_db,
    )
    # Athena CSV returns dates as strings. Convert explicitly before filters/KPIs.
    route_days["service_date"] = pd.to_datetime(route_days["service_date"]).dt.date
    return {
        "route_days": route_days,
        "audit": _athena_query("SELECT * FROM load_audit", silver_db),
        "rejects": _athena_query("SELECT * FROM rejects LIMIT 200", silver_db),
        "reject_summary": _athena_query("SELECT * FROM mart_rejects_summary", gold_db),
    }


def load_dashboard_data(
    backend: str | None = None, data_dir: str | Path = DATA_DIR
) -> dict[str, pd.DataFrame]:
    """Load compact dashboard datasets from local Parquet or Athena."""
    mode = (backend or os.environ.get("ANALYTICS_BACKEND", "local")).lower()
    if mode == "local":
        return _local_data(data_dir)
    if mode == "athena":
        return _athena_data()
    raise ValueError("ANALYTICS_BACKEND must be 'local' or 'athena'")

