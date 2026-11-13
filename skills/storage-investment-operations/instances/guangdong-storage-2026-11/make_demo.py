#!/usr/bin/env python3
"""Generate grade-D synthetic scenario, frequency and availability data.

The shapes are deterministic, so the demo is reproducible. They correspond to
no real project, contract or market outcome.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

SCENARIOS = (
    ("s1", 80.0, 320.0, 0.20),
    ("s2", 120.0, 400.0, 0.25),
    ("s3", 160.0, 480.0, 0.30),
    ("s4", 200.0, 560.0, 0.15),
    ("s5", 240.0, 640.0, 0.10),
)

AVAILABILITY = (
    ("2026-01", 0.980),
    ("2026-02", 0.970),
    ("2026-03", 0.960),
    ("2026-04", 0.950),
    ("2026-05", 0.930),
    ("2026-06", 0.970),
    ("2026-07", 0.990),
    ("2026-08", 0.980),
    ("2026-09", 0.970),
    ("2026-10", 0.980),
    ("2026-11", 0.990),
    ("2026-12", 0.980),
)


def _frequency():
    rows = []
    for month in range(1, 13):
        mileage = 1500.0 + 120.0 * math.cos(2.0 * math.pi * (month - 1) / 12.0)
        k_factor = 1.40 + 0.10 * math.sin(2.0 * math.pi * (month - 1) / 12.0)
        rows.append((f"2026-{month:02d}", round(mileage, 1), round(k_factor, 3)))
    return rows


def _write(path, header, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    _write(
        DATA / "scenarios_demo.csv",
        ["scenario", "charge_price", "discharge_price", "weight"],
        SCENARIOS,
    )
    _write(
        DATA / "frequency_demo.csv",
        ["month", "mileage_mw_per_day", "k_factor"],
        _frequency(),
    )
    _write(
        DATA / "availability_demo.csv",
        ["month", "availability_ratio"],
        AVAILABILITY,
    )
    print(f"wrote {DATA / 'scenarios_demo.csv'}")
    print(f"wrote {DATA / 'frequency_demo.csv'}")
    print(f"wrote {DATA / 'availability_demo.csv'}")


if __name__ == "__main__":
    main()
