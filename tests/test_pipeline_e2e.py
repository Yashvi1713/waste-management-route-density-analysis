from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from qa.run_qa import run_qa


def test_rows_reconcile(pipeline_dir: Path) -> None:
    audit = pd.read_parquet(pipeline_dir / "silver" / "load_audit.parquet")
    assert (
        audit.raw_rows
        == audit.silver_rows + audit.rejected_rows + audit.duplicates_removed
    ).all()


def test_marts_built(pipeline_dir: Path) -> None:
    required = [
        "dim_truck", "dim_route", "dim_customer", "dim_date",
        "fact_pickup", "fact_route_day", "mart_route_day",
        "mart_rejects_summary", "mart_route_kpis", "mart_fuel_kpis",
    ]
    connection = duckdb.connect()
    for name in required:
        path = pipeline_dir / "gold" / f"{name}.parquet"
        assert path.exists(), name
        assert connection.execute(
            f"SELECT count(*) FROM read_parquet('{path}')"
        ).fetchone()[0] > 0
    connection.close()


def test_contract_passes(pipeline_dir: Path, tmp_path: Path) -> None:
    report = tmp_path / "qa_report.md"
    assert run_qa(pipeline_dir, report_path=report)
    assert "FAIL" not in report.read_text()


def test_planted_routes_flagged(pipeline_dir: Path) -> None:
    routes = pd.read_parquet(pipeline_dir / "gold" / "mart_route_kpis.parquet")
    flagged = set(routes.loc[routes.is_flagged, "route_id"])
    assert {"R-04", "R-17", "R-29"} <= flagged

