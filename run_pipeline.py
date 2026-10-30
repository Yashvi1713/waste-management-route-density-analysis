"""Run local Bronze-to-Silver-to-Gold processing."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from config import DATA_DIR, layer_paths
from ingest import ingest_bronze
from kpis import fuel_kpis, route_kpis


SQL_FILES = ["01_dims.sql", "02_facts.sql", "03_marts.sql"]


def run_pipeline(data_dir: str | Path = DATA_DIR) -> None:
    """Build typed Silver and dimensional Gold Parquet datasets."""
    _, silver, gold = layer_paths(data_dir)
    gold.mkdir(parents=True, exist_ok=True)
    audit = ingest_bronze(data_dir)
    if not (
        audit.raw_rows
        == audit.silver_rows + audit.rejected_rows + audit.duplicates_removed
    ).all():
        raise RuntimeError("Silver reconciliation failed")

    connection = duckdb.connect()
    values = {"silver": str(silver.resolve()), "gold": str(gold.resolve())}
    for filename in SQL_FILES:
        sql = (Path(__file__).parent / "sql" / filename).read_text().format(**values)
        connection.execute(sql)

    excluded = connection.execute(
        f"""
        WITH pickup_days AS (
            SELECT DISTINCT service_date, route_id, truck_id
            FROM read_parquet('{gold / 'fact_pickup.parquet'}')
        ), trusted_cost AS (
            SELECT service_date, route_id, truck_id
            FROM read_parquet('{gold / 'fact_route_day.parquet'}')
        )
        SELECT count(*) FROM pickup_days p
        LEFT JOIN trusted_cost f USING (service_date, route_id, truck_id)
        WHERE f.route_id IS NULL
        """
    ).fetchone()[0]
    print(f"Excluded route days without trusted cost: {excluded}")

    mart = connection.execute(
        f"SELECT * FROM read_parquet('{gold / 'mart_route_day.parquet'}')"
    ).fetchdf()
    route_kpis(mart).to_parquet(gold / "mart_route_kpis.parquet", index=False)
    fuel_kpis(mart).to_parquet(gold / "mart_fuel_kpis.parquet", index=False)
    connection.close()
    print(f"Pipeline complete: {silver} -> {gold}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    run_pipeline(DATA_DIR)


if __name__ == "__main__":
    main()
