#!/usr/bin/env python3
"""Generate the D-grade synthetic monthly market file for the Shenzhen V2G pack."""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

FIELDS = [
    "month",
    "days",
    "peak_hours",
    "flat_hours",
    "valley_hours",
    "peak_price_cny_per_mwh",
    "flat_price_cny_per_mwh",
    "valley_price_cny_per_mwh",
    "v2g_discharge_price_cny_per_mwh",
    "dr_call_hours",
    "dr_price_cny_per_mwh",
    "reserve_price_cny_per_kw_month",
]

ROWS = [
    [1, 31, 4, 10, 10, 1150, 650, 340, 900, 2, 2600, 8],
    [2, 28, 4, 10, 10, 1100, 640, 330, 880, 2, 2600, 8],
    [3, 31, 4, 10, 10, 1050, 600, 300, 850, 2, 2400, 7],
    [4, 30, 4, 10, 10, 1050, 600, 300, 850, 2, 2400, 7],
    [5, 31, 4, 10, 10, 1100, 620, 310, 880, 8, 2500, 8],
    [6, 30, 5, 9, 10, 1250, 720, 380, 1000, 16, 2600, 9],
    [7, 31, 5, 9, 10, 1300, 750, 400, 1050, 28, 2700, 9],
    [8, 31, 5, 9, 10, 1300, 750, 400, 1050, 28, 2700, 9],
    [9, 30, 4, 10, 10, 1200, 700, 370, 980, 16, 2600, 9],
    [10, 31, 4, 10, 10, 1050, 600, 300, 850, 8, 2400, 7],
    [11, 30, 4, 10, 10, 1050, 600, 300, 850, 2, 2400, 7],
    [12, 31, 4, 10, 10, 1150, 650, 340, 900, 2, 2600, 8],
]


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "market_demo.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(ROWS)

    assert len(ROWS) == 12
    assert sum(row[1] for row in ROWS) == 365
    assert all(row[2] + row[3] + row[4] == 24 for row in ROWS)
    assert all(row[8] < row[5] for row in ROWS)
    assert all(row[8] > row[7] for row in ROWS)
    assert sum(row[9] for row in ROWS) == 116
    assert all(7 <= row[11] <= 9 for row in ROWS)

    print(f"写出 {path}（12 个月，365 天，DR 调用 {sum(row[9] for row in ROWS)} 小时）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
