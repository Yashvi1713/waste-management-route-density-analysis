from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from generate_data import generate_dataset


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_same_seed_same_output(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    generate_dataset(first, days=7, seed=42)
    generate_dataset(second, days=7, seed=42)
    assert _tree_bytes(first) == _tree_bytes(second)


def test_planted_error_rate(tmp_path: Path) -> None:
    root = tmp_path / "data"
    generate_dataset(root, days=10, seed=42)
    manifest = json.loads((root / "bronze" / "_manifest.json").read_text())
    planted = manifest["pickup_errors"]
    error_rows = sum(planted.values())
    raw_rows = sum(
        len(pd.read_csv(path, dtype=str))
        for path in (root / "bronze" / "pickups").glob("*.csv")
    )
    assert 0.02 <= error_rows / raw_rows <= 0.04


def test_clean_rows_reference_dimensions(tmp_path: Path) -> None:
    root = tmp_path / "data"
    generate_dataset(root, days=7, seed=42)
    bronze = root / "bronze"
    routes = set(pd.read_csv(bronze / "routes.csv", dtype=str).route_id)
    trucks = set(pd.read_csv(bronze / "trucks.csv", dtype=str).truck_id)
    customers = set(pd.read_csv(bronze / "customers.csv", dtype=str).customer_id)
    pickups = pd.concat(
        [pd.read_csv(path, dtype=str) for path in sorted((bronze / "pickups").glob("*.csv"))],
        ignore_index=True,
    )
    clean = pickups[
        pickups.status.isin(["completed", "missed"])
        & pickups.truck_id.isin(trucks)
        & pickups.route_id.isin(routes)
        & pickups.customer_id.isin(customers)
    ]
    assert not clean.empty
    assert set(clean.route_id) <= routes
    assert set(clean.truck_id) <= trucks
    assert set(clean.customer_id) <= customers

