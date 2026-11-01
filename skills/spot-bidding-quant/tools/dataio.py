"""CSV loading helpers shared by the reference tools."""

from __future__ import annotations

import csv
from pathlib import Path

SLOTS = 96
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "sample" / "synthetic_spot_60d.csv"


def load_rows(path: Path | str = DEFAULT_PATH) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_days(rows: list[dict[str, str]], column: str) -> list[list[float]]:
    """Group one column into a list of days, each a list of SLOTS floats."""
    days: list[list[float]] = []
    current: list[float] = []
    current_date = None
    for row in rows:
        if current_date is not None and row["date"] != current_date:
            days.append(current)
            current = []
        current_date = row["date"]
        current.append(float(row[column]))
    if current:
        days.append(current)
    return days


def dates(rows: list[dict[str, str]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        if not seen or seen[-1] != row["date"]:
            seen.append(row["date"])
    return seen
