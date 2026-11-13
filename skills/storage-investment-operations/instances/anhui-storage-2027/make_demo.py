#!/usr/bin/env python3
"""Generate grade-D synthetic scenario and assessment data for the Anhui pack.

The data correspond to no real project, contract or market price. Shapes are
deterministic, so the demo is reproducible.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

SCENARIOS = (
    ("s1", 180.0, 520.0, 0.20),
    ("s2", 220.0, 560.0, 0.25),
    ("s3", 260.0, 600.0, 0.25),
    ("s4", 300.0, 640.0, 0.20),
    ("s5", 340.0, 680.0, 0.10),
)

AVAILABILITY = (
    ("2027-01", 0.995),
    ("2027-02", 0.990),
    ("2027-03", 0.985),
    ("2027-04", 0.970),
    ("2027-05", 0.940),
    ("2027-06", 0.990),
    ("2027-07", 1.000),
    ("2027-08", 0.985),
    ("2027-09", 0.985),
    ("2027-10", 0.990),
    ("2027-11", 0.995),
    ("2027-12", 0.985),
)


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
        DATA / "assessment_demo.csv",
        ["month", "availability_ratio"],
        AVAILABILITY,
    )
    print(f"wrote {DATA / 'scenarios_demo.csv'}")
    print(f"wrote {DATA / 'assessment_demo.csv'}")


if __name__ == "__main__":
    main()
