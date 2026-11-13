#!/usr/bin/env python3
"""Generate the synthetic first-year resource profile for the Yunnan wind pack.

The profile is monthly gross generation and a generation-weighted capture rate.
It is sized to the instance: 100 MW x 2,850 h = 285,000 MWh. All values are
grade D synthetic data and do not correspond to any real wind farm.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "resource_demo.csv"

TOTAL_MWH = 285_000.0
WEIGHTS_PCT = [9.5, 8.5, 10.5, 9.5, 8.0, 6.5, 6.0, 6.0, 6.5, 7.5, 9.5, 12.0]
CAPTURE_RATES = [0.95, 0.95, 0.94, 0.93, 0.92, 0.90, 0.88, 0.88, 0.89, 0.91, 0.94, 0.95]


def build_rows():
    if abs(sum(WEIGHTS_PCT) - 100.0) > 1e-9:
        raise ValueError("monthly weights must sum to 100%")
    rows = []
    for index, (weight, capture) in enumerate(zip(WEIGHTS_PCT, CAPTURE_RATES), start=1):
        rows.append(
            {
                "month": f"2028-{index:02d}",
                "generation_mwh": f"{TOTAL_MWH * weight / 100.0:.0f}",
                "capture_rate": f"{capture:.4f}",
            }
        )
    total = sum(float(row["generation_mwh"]) for row in rows)
    if abs(total - TOTAL_MWH) > 1e-9:
        raise ValueError(f"monthly generation sums to {total}, expected {TOTAL_MWH}")
    return rows


def main():
    rows = build_rows()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["month", "generation_mwh", "capture_rate"]
        )
        writer.writeheader()
        writer.writerows(rows)
    weighted = (
        sum(float(row["generation_mwh"]) * float(row["capture_rate"]) for row in rows)
        / TOTAL_MWH
    )
    print(f"wrote {OUT} ({len(rows)} rows, {TOTAL_MWH:,.0f} MWh, capture {weighted:.4f})")


if __name__ == "__main__":
    main()
