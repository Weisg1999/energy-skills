#!/usr/bin/env python3
"""Generate the bundled D-level synthetic data for the Zhejiang VPP 2.0 pack."""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

EVENTS = (
    ("e01", "2026-09-05", "generation", "调节型", "positive", "10:00", "11:00", 6.0, 1000.0),
    ("e02", "2026-09-12", "generation", "局域型", "positive", "15:00", "16:00", 5.0, 800.0),
    ("e03", "2026-09-20", "generation", "调节型", "negative", "02:00", "03:00", 1.0, 300.0),
    ("e04", "2026-09-06", "storage", "快速型", "positive", "19:00", "20:00", 5.0, 1200.0),
    ("e05", "2026-09-15", "storage", "快速型", "positive", "19:00", "20:00", 5.0, 1200.0),
    ("e06", "2026-09-22", "storage", "调节型", "negative", "13:00", "14:00", 1.0, 380.0),
    ("e07", "2026-09-07", "load", "快速型", "positive", "18:00", "19:00", 5.0, 1200.0),
    ("e08", "2026-09-14", "load", "快速型", "positive", "18:00", "19:00", 5.0, 1200.0),
    ("e09", "2026-09-21", "load", "快速型", "positive", "18:00", "19:00", 5.0, 1200.0),
    ("e10", "2026-09-28", "load", "调节型", "positive", "10:00", "11:00", 5.0, 1000.0),
)

RESPONSE = {
    "e01": 5.52,
    "e02": 3.75,
    "e03": 0.60,
    "e04": 4.80,
    "e05": 4.40,
    "e06": 0.90,
    "e07": 2.75,
    "e08": 3.00,
    "e09": 3.25,
    "e10": 4.50,
}


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    write_csv(
        DATA / "events_demo.csv",
        [
            {
                "event_id": row[0],
                "date": row[1],
                "unit_id": row[2],
                "product": row[3],
                "direction": row[4],
                "start": row[5],
                "end": row[6],
                "required_mw": row[7],
                "price_cny_per_mw": row[8],
            }
            for row in EVENTS
        ],
        [
            "event_id",
            "date",
            "unit_id",
            "product",
            "direction",
            "start",
            "end",
            "required_mw",
            "price_cny_per_mw",
        ],
    )
    write_csv(
        DATA / "response_demo.csv",
        [
            {
                "event_id": event_id,
                "unit_id": next(row[2] for row in EVENTS if row[0] == event_id),
                "actual_mw": actual,
            }
            for event_id, actual in RESPONSE.items()
        ],
        ["event_id", "unit_id", "actual_mw"],
    )
    print(f"wrote {DATA}")


if __name__ == "__main__":
    main()
