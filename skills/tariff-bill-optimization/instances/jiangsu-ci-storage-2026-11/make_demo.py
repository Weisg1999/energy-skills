#!/usr/bin/env python3
"""Generate the grade-D synthetic load for the Jiangsu C&I storage pack.

The series reuses ``tools/curves.py``: one representative day per month,
96 fifteen-minute points, scaled by the monthly factors. It corresponds to no
real customer, meter or bill.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parents[1]
sys.path.insert(0, str(SKILL_DIR / "tools"))

import curves  # noqa: E402


def main():
    data_dir = HERE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "load_demo.csv"
    loads = curves.monthly_loads(96)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["month", "slot", "load_kw"])
        for month in range(1, 13):
            for slot, value in enumerate(loads[month]):
                writer.writerow([month, slot, f"{value:.1f}"])
    print(f"wrote {path} ({12 * 96} rows)")


if __name__ == "__main__":
    main()
