"""Canonical local medallion paths."""

from __future__ import annotations

import os
from pathlib import Path


DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"


def layer_paths(data_dir: str | Path | None = None) -> tuple[Path, Path, Path]:
    """Return canonical Bronze, Silver, and Gold paths for a data root."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    return root / "bronze", root / "silver", root / "gold"

