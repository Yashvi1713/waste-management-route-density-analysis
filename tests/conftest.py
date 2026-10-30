from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def truck_ids() -> set[str]:
    return {"T-001", "T-002"}


@pytest.fixture
def good_pickup() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pickup_id": "P00000001",
                "service_date": "2026-07-01",
                "route_id": "R-01",
                "truck_id": "T-001",
                "customer_id": "C-000001",
                "completed_at": "2026-07-01 08:00:00",
                "tons": "0.1",
                "status": "completed",
            }
        ]
    )


@pytest.fixture(scope="session")
def pipeline_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from generate_data import generate_dataset
    from run_pipeline import run_pipeline

    tmp_path = tmp_path_factory.mktemp("pipeline")
    generate_dataset(tmp_path / "data", days=30, seed=42)
    run_pipeline(tmp_path / "data")
    return tmp_path / "data"


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def manifest(root: Path) -> dict:
    return json.loads((root / "bronze" / "_manifest.json").read_text())

