"""Generate deterministic synthetic Bronze waste-collection extracts."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import DATA_DIR, layer_paths


DEPOTS = ["Vaughan", "Brampton", "Mississauga"]
PROBLEM_ROUTES = {"R-04", "R-17", "R-29"}
START_DATE = date(2026, 7, 1)


def _routes(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for n in range(1, 41):
        route_id = f"R-{n:02d}"
        commercial = n >= 31
        if route_id in PROBLEM_ROUTES:
            planned = int(rng.integers(600, 641))
        elif commercial:
            planned = int(rng.integers(90, 131))
        else:
            planned = int(rng.integers(650, 951))
        rows.append(
            {
                "route_id": route_id,
                "depot": DEPOTS[(n - 1) % 3],
                "service_line": "commercial" if commercial else "residential",
                "planned_stops": planned,
            }
        )
    return pd.DataFrame(rows)


def _trucks(rng: np.random.Generator, routes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    route_by_number = routes.set_index(routes.route_id.str[-2:].astype(int))
    for n in range(1, 49):
        if n <= 40:
            route = route_by_number.loc[n]
            depot = route.depot
            body = "front_load" if route.service_line == "commercial" else "side_load"
        else:
            depot = DEPOTS[(n - 41) % 3]
            body = "side_load"
        rows.append(
            {
                "truck_id": f"T-{n:03d}",
                "depot": depot,
                "fuel_type": "CNG" if rng.random() < 0.4 else "diesel",
                "model_year": int(rng.integers(2014, 2025)),
                "body_type": body,
            }
        )
    return pd.DataFrame(rows)


def _customers(rng: np.random.Generator, routes: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    next_id = 1
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    for route in routes.itertuples(index=False):
        for weekday in weekdays:
            size = int(route.planned_stops)
            ids = [f"C-{n:06d}" for n in range(next_id, next_id + size)]
            next_id += size
            if route.service_line == "residential":
                segments = np.full(size, "residential", dtype=object)
                rates = rng.uniform(32, 45, size)
            else:
                industrial = rng.random(size) < 0.2
                segments = np.where(industrial, "industrial", "small_business")
                rates = np.where(
                    industrial,
                    rng.uniform(600, 1500, size),
                    rng.uniform(180, 420, size),
                )
            frames.append(
                pd.DataFrame(
                    {
                        "customer_id": ids,
                        "route_id": route.route_id,
                        "segment": segments,
                        "service_day": weekday,
                        "monthly_rate": np.round(rates, 2),
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


def _service_dates(days: int) -> list[date]:
    return [
        START_DATE + timedelta(days=offset)
        for offset in range(days)
        if (START_DATE + timedelta(days=offset)).weekday() < 5
    ]


def _choose_truck(
    rng: np.random.Generator,
    route_number: int,
    depot: str,
    trucks: pd.DataFrame,
) -> pd.Series:
    if rng.random() >= 0.04:
        return trucks.iloc[route_number - 1]
    spares = trucks[(trucks.index >= 40) & (trucks.depot == depot)]
    return spares.iloc[int(rng.integers(0, len(spares)))]


def _plant_pickup_errors(
    rng: np.random.Generator,
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Plant disjoint single-rule errors, then append exact duplicates."""
    n = len(frame)
    order = rng.permutation(n)
    shares = {
        "tons_out_of_range": 0.008,
        "unknown_truck": 0.005,
        "outside_shift": 0.0045,
        "bad_status": 0.0025,
    }
    counts = {name: int(round(n * share)) for name, share in shares.items()}
    cursor = 0
    for rule, count in counts.items():
        idx = order[cursor : cursor + count]
        cursor += count
        if rule == "tons_out_of_range":
            frame.loc[idx, "status"] = "completed"
            values = np.resize(np.array(["", "-0.4", "15.5"], dtype=object), count)
            frame.loc[idx, "tons"] = values
        elif rule == "unknown_truck":
            frame.loc[idx, "truck_id"] = "T-999"
        elif rule == "outside_shift":
            frame.loc[idx, "status"] = "completed"
            frame.loc[idx, "completed_at"] = [
                f"{value} {'03' if i % 2 == 0 else '22'}:{i % 60:02d}:00"
                for i, value in enumerate(frame.loc[idx, "service_date"])
            ]
        else:
            values = np.resize(np.array(["COMPLETE", "unknown", ""], dtype=object), count)
            frame.loc[idx, "status"] = values

    duplicate_count = int(round(n * 0.01))
    duplicate_pool = order[cursor:]
    duplicate_idx = duplicate_pool[:duplicate_count]
    duplicates = frame.loc[duplicate_idx].copy()
    output = pd.concat([frame, duplicates], ignore_index=True)
    counts["duplicates"] = duplicate_count
    return output, counts


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def generate_dataset(data_dir: str | Path = DATA_DIR, days: int = 90, seed: int = 42) -> dict:
    """Generate Bronze files beneath *data_dir* and return their manifest."""
    rng = np.random.default_rng(seed)
    bronze, _, _ = layer_paths(data_dir)
    bronze.mkdir(parents=True, exist_ok=True)
    (bronze / "pickups").mkdir(exist_ok=True)
    (bronze / "route_days").mkdir(exist_ok=True)

    routes = _routes(rng)
    trucks = _trucks(rng, routes)
    customers = _customers(rng, routes)
    _write_csv(trucks, bronze / "trucks.csv")
    _write_csv(routes, bronze / "routes.csv")
    _write_csv(customers, bronze / "customers.csv")

    customer_groups = {
        key: group.reset_index(drop=True)
        for key, group in customers.groupby(["route_id", "service_day"], sort=False)
    }
    manifest = {
        "seed": seed,
        "start_date": START_DATE.isoformat(),
        "calendar_days": days,
        "service_days": len(_service_dates(days)),
        "pickup_errors": {
            "tons_out_of_range": 0,
            "unknown_truck": 0,
            "outside_shift": 0,
            "bad_status": 0,
            "duplicates": 0,
        },
        "route_day_errors": {"nonpositive_measure": 0},
        "files": {},
    }
    pickup_number = 1

    for service_date in _service_dates(days):
        pickup_frames: list[pd.DataFrame] = []
        route_day_rows = []
        weekday = service_date.strftime("%A")
        for route_number, route in enumerate(routes.itertuples(index=False), start=1):
            truck = _choose_truck(rng, route_number, route.depot, trucks)
            selected = customer_groups[(route.route_id, weekday)]
            stops = len(selected)
            if route.route_id in PROBLEM_ROUTES:
                base_sph = float(rng.normal(58, 1.5))
                base_km = float(rng.normal(110, 15) * 1.6)
                missed_base = 0.025
            elif route.service_line == "residential":
                base_sph = float(np.clip(rng.normal(95, 7), 80, 115))
                base_km = float(rng.normal(110, 15))
                missed_base = 0.008
            else:
                base_sph = float(np.clip(rng.normal(14, 1.5), 12, 18))
                base_km = float(rng.normal(160, 20))
                missed_base = 0.006
            stops_per_hour = base_sph * float(np.clip(rng.normal(1, 0.04), 0.92, 1.08))
            interval = 3600 / stops_per_hour
            start_seconds = 5 * 3600 + 45 * 60 + float(rng.uniform(0, 20 * 60))
            completed_seconds = start_seconds + 15 * 60 + np.arange(stops) * interval
            missed_probability = missed_base + 0.0015 * (2026 - int(truck.model_year))
            missed = rng.random(stops) < missed_probability
            if route.service_line == "residential":
                tons = rng.gamma(4, 0.0055, stops)
            else:
                tons = np.clip(rng.gamma(3, 0.15, stops), 0.01, 11.9)
            timestamps = np.datetime64(service_date.isoformat(), "s") + completed_seconds.astype(
                "timedelta64[s]"
            )
            completed_at = np.char.replace(
                np.datetime_as_string(timestamps, unit="s"), "T", " "
            ).astype(object)
            completed_at[missed] = ""
            tons_text = np.char.mod("%.4f", tons).astype(object)
            tons_text[missed] = ""
            pickup_ids = [f"P{n:08d}" for n in range(pickup_number, pickup_number + stops)]
            pickup_number += stops
            pickup_frames.append(
                pd.DataFrame(
                    {
                        "pickup_id": pickup_ids,
                        "service_date": service_date.isoformat(),
                        "route_id": route.route_id,
                        "truck_id": truck.truck_id,
                        "customer_id": selected.customer_id.to_numpy(),
                        "completed_at": completed_at,
                        "tons": tons_text,
                        "status": np.where(missed, "missed", "completed"),
                    }
                )
            )

            shift_hours = (15 * 60 + stops * interval) / 3600 + 0.75
            km = max(1.0, base_km * float(rng.uniform(0.9, 1.1)))
            regular = min(shift_hours, 10)
            overtime = max(shift_hours - 10, 0)
            labour = 38.5 * (regular + 1.5 * overtime)
            fuel_rate = 0.58 if truck.fuel_type == "CNG" else 0.92
            maint_rate = 0.61 if truck.fuel_type == "CNG" else 0.55
            fuel = km * fuel_rate * float(rng.uniform(0.95, 1.05))
            maint = km * maint_rate * (1 + 0.04 * (2026 - int(truck.model_year)))
            if rng.random() < 0.003:
                km = -km
                manifest["route_day_errors"]["nonpositive_measure"] += 1
            route_day_rows.append(
                {
                    "service_date": service_date.isoformat(),
                    "route_id": route.route_id,
                    "truck_id": truck.truck_id,
                    "shift_hours": round(shift_hours, 4),
                    "km_driven": round(km, 4),
                    "labour_cost": round(labour, 2),
                    "fuel_cost": round(fuel, 2),
                    "maint_cost": round(maint, 2),
                }
            )

        daily_pickups, counts = _plant_pickup_errors(
            rng, pd.concat(pickup_frames, ignore_index=True)
        )
        for name, count in counts.items():
            manifest["pickup_errors"][name] += count
        pickup_path = bronze / "pickups" / f"{service_date.isoformat()}.csv"
        route_day_path = bronze / "route_days" / f"{service_date.isoformat()}.csv"
        _write_csv(daily_pickups, pickup_path)
        _write_csv(pd.DataFrame(route_day_rows), route_day_path)
        manifest["files"][str(pickup_path.relative_to(bronze))] = len(daily_pickups)
        manifest["files"][str(route_day_path.relative_to(bronze))] = len(route_day_rows)

    manifest["files"]["trucks.csv"] = len(trucks)
    manifest["files"]["routes.csv"] = len(routes)
    manifest["files"]["customers.csv"] = len(customers)
    (bronze / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90, help="calendar days")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    manifest = generate_dataset(DATA_DIR, days=args.days, seed=args.seed)
    errors = sum(manifest["pickup_errors"].values())
    pickup_rows = sum(
        count for name, count in manifest["files"].items() if name.startswith("pickups/")
    )
    print(f"Generated {manifest['service_days']} service days in {DATA_DIR / 'bronze'}")
    print(f"Planted pickup error rate: {errors / pickup_rows:.2%}")


if __name__ == "__main__":
    main()
