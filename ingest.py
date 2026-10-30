"""Local Bronze-to-Silver ingestion with quarantine and reconciliation."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from config import DATA_DIR, layer_paths
from quality import classify_pickup_rejects, classify_route_day_rejects, deduplicate


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _read_daily(directory: Path) -> pd.DataFrame:
    files = sorted(directory.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No Bronze CSV files found in {directory}")
    return pd.concat([_read_csv(path) for path in files], ignore_index=True)


def _reject_rows(
    source: str,
    original: pd.DataFrame,
    reasons: pd.Series,
    loaded_at: pd.Timestamp,
) -> pd.DataFrame:
    rejected = original.loc[reasons.notna()]
    return pd.DataFrame(
        {
            "source": source,
            "rule": reasons.loc[rejected.index].astype(str).to_numpy(),
            "record": [
                json.dumps(record, sort_keys=True, separators=(",", ":"))
                for record in rejected.to_dict(orient="records")
            ],
            "loaded_at": loaded_at,
        }
    )


def _typed_pickups(frame: pd.DataFrame) -> pd.DataFrame:
    typed = frame.copy()
    typed["service_date"] = typed["service_date"].map(date.fromisoformat)
    typed["completed_at"] = typed["completed_at"].map(
        lambda value: datetime.fromisoformat(value) if value else None
    )
    typed["tons"] = pd.to_numeric(typed["tons"], errors="coerce")
    return typed


def _typed_route_days(frame: pd.DataFrame) -> pd.DataFrame:
    typed = frame.copy()
    typed["service_date"] = typed["service_date"].map(date.fromisoformat)
    for column in ["shift_hours", "km_driven", "labour_cost", "fuel_cost", "maint_cost"]:
        typed[column] = pd.to_numeric(typed[column], errors="coerce")
    return typed


def ingest_bronze(data_dir: str | Path = DATA_DIR) -> pd.DataFrame:
    """Ingest local Bronze into Silver and return the load audit."""
    bronze, silver, _ = layer_paths(data_dir)
    silver.mkdir(parents=True, exist_ok=True)
    loaded_at = pd.Timestamp(datetime.now(timezone.utc)).floor("s").tz_localize(None)

    dimensions = {
        "trucks": _read_csv(bronze / "trucks.csv"),
        "routes": _read_csv(bronze / "routes.csv"),
        "customers": _read_csv(bronze / "customers.csv"),
    }
    dimensions["trucks"]["model_year"] = pd.to_numeric(
        dimensions["trucks"]["model_year"], errors="coerce"
    ).astype("Int64")
    dimensions["routes"]["planned_stops"] = pd.to_numeric(
        dimensions["routes"]["planned_stops"], errors="coerce"
    ).astype("Int64")
    dimensions["customers"]["monthly_rate"] = pd.to_numeric(
        dimensions["customers"]["monthly_rate"], errors="coerce"
    )
    for source, frame in dimensions.items():
        frame.to_parquet(silver / f"{source}.parquet", index=False)

    truck_ids = set(dimensions["trucks"]["truck_id"])
    raw_pickups = _read_daily(bronze / "pickups")
    pickups, pickup_duplicates = deduplicate(raw_pickups, ["pickup_id"])
    pickup_reasons = classify_pickup_rejects(pickups, truck_ids)
    pickup_rejects = _reject_rows("pickups", pickups, pickup_reasons, loaded_at)
    valid_pickups = _typed_pickups(pickups.loc[pickup_reasons.isna()])
    valid_pickups.to_parquet(silver / "pickups.parquet", index=False)

    raw_route_days = _read_daily(bronze / "route_days")
    route_days, route_day_duplicates = deduplicate(
        raw_route_days, ["service_date", "route_id", "truck_id"]
    )
    route_day_reasons = classify_route_day_rejects(route_days, truck_ids)
    route_day_rejects = _reject_rows(
        "route_days", route_days, route_day_reasons, loaded_at
    )
    valid_route_days = _typed_route_days(route_days.loc[route_day_reasons.isna()])
    valid_route_days.to_parquet(silver / "route_days.parquet", index=False)

    rejects = pd.concat([pickup_rejects, route_day_rejects], ignore_index=True)
    rejects.to_parquet(silver / "rejects.parquet", index=False)
    audit_rows = [
        {
            "source": name,
            "raw_rows": len(frame),
            "duplicates_removed": 0,
            "rejected_rows": 0,
            "silver_rows": len(frame),
            "loaded_at": loaded_at,
        }
        for name, frame in dimensions.items()
    ]
    audit_rows.extend(
        [
            {
                "source": "pickups",
                "raw_rows": len(raw_pickups),
                "duplicates_removed": pickup_duplicates,
                "rejected_rows": int(pickup_reasons.notna().sum()),
                "silver_rows": len(valid_pickups),
                "loaded_at": loaded_at,
            },
            {
                "source": "route_days",
                "raw_rows": len(raw_route_days),
                "duplicates_removed": route_day_duplicates,
                "rejected_rows": int(route_day_reasons.notna().sum()),
                "silver_rows": len(valid_route_days),
                "loaded_at": loaded_at,
            },
        ]
    )
    audit = pd.DataFrame(audit_rows)
    audit.to_parquet(silver / "load_audit.parquet", index=False)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    audit = ingest_bronze(DATA_DIR)
    print(audit.to_string(index=False))
    reconciled = (
        audit.raw_rows
        == audit.silver_rows + audit.rejected_rows + audit.duplicates_removed
    )
    print(f"Reconciliation: {'PASS' if reconciled.all() else 'FAIL'}")


if __name__ == "__main__":
    main()
