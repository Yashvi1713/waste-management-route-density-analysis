"""Run deterministic Athena reconciliation, grain, and non-empty checks."""

from __future__ import annotations

import os
import time

import boto3


REGION = os.environ.get("AWS_REGION", "eu-west-1")
SILVER = os.environ.get("AWS_SILVER_DATABASE", "route_lab_silver")
GOLD = os.environ.get("AWS_GOLD_DATABASE", "route_lab_gold")
WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "route-lab")
athena = boto3.client("athena", region_name=REGION)


def scalar(query: str, database: str) -> int:
    query_id = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=WORKGROUP,
    )["QueryExecutionId"]
    while True:
        execution = athena.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(2)
    if state != "SUCCEEDED":
        raise RuntimeError(execution["Status"].get("StateChangeReason", state))
    rows = athena.get_query_results(QueryExecutionId=query_id)["ResultSet"]["Rows"]
    return int(rows[1]["Data"][0]["VarCharValue"])


CHECKS = [
    (
        "Silver reconciliation failures",
        "SELECT count(*) FROM load_audit WHERE raw_rows <> silver_rows + rejected_rows + duplicates_removed",
        SILVER,
        lambda value: value == 0,
    ),
    (
        "Duplicate fact_pickup keys",
        "SELECT count(*) FROM (SELECT pickup_id FROM fact_pickup GROUP BY pickup_id HAVING count(*) > 1)",
        GOLD,
        lambda value: value == 0,
    ),
    (
        "Duplicate fact_route_day grains",
        "SELECT count(*) FROM (SELECT service_date, route_id, truck_id FROM fact_route_day GROUP BY service_date, route_id, truck_id HAVING count(*) > 1)",
        GOLD,
        lambda value: value == 0,
    ),
    (
        "mart_route_day row count",
        "SELECT count(*) FROM mart_route_day",
        GOLD,
        lambda value: value > 0,
    ),
]


def main() -> int:
    failures = 0
    for name, query, database, predicate in CHECKS:
        try:
            value = scalar(query, database)
            passed = predicate(value)
        except Exception as error:  # present one deterministic result per check
            value, passed = str(error), False
        print(f"{'PASS' if passed else 'FAIL'} {name}: {value}")
        failures += not passed
    print(f"AWS QA: {'PASS' if failures == 0 else 'FAIL'} ({len(CHECKS) - failures}/{len(CHECKS)})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

