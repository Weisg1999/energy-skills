#!/usr/bin/env python3
"""Generate the synthetic monthly market profile for the Liaoning VPP pack."""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
PEAK_PRICE = [560, 540, 500, 460, 440, 450, 520, 530, 490, 470, 510, 550]
FLAT_PRICE = [360, 350, 330, 300, 280, 300, 340, 350, 320, 310, 340, 360]
VALLEY_PRICE = [150, 140, 120, -50, -80, -30, 100, 110, 90, 80, 130, 160]
DR_HOURS = [18, 15, 10, 5, 4, 8, 14, 16, 8, 5, 10, 16]
FILL_HOURS = [40, 35, 30, 20, 20, 25, 35, 35, 30, 25, 30, 35]

FIELDS = [
    "month",
    "days",
    "peak_hours",
    "flat_hours",
    "valley_hours",
    "peak_price_cny_per_mwh",
    "flat_price_cny_per_mwh",
    "valley_price_cny_per_mwh",
    "dr_call_hours",
    "dr_price_cny_per_mwh",
    "valley_fill_hours",
    "valley_fill_price_cny_per_mwh",
    "freq_price_cny_per_kw_month",
]


def main() -> None:
    assert sum(DAYS) == 365, sum(DAYS)
    assert sum(DR_HOURS) == 129, sum(DR_HOURS)
    assert sum(FILL_HOURS) == 360, sum(FILL_HOURS)
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "market_demo.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for index in range(12):
            writer.writerow(
                {
                    "month": index + 1,
                    "days": DAYS[index],
                    "peak_hours": 4,
                    "flat_hours": 10,
                    "valley_hours": 10,
                    "peak_price_cny_per_mwh": PEAK_PRICE[index],
                    "flat_price_cny_per_mwh": FLAT_PRICE[index],
                    "valley_price_cny_per_mwh": VALLEY_PRICE[index],
                    "dr_call_hours": DR_HOURS[index],
                    "dr_price_cny_per_mwh": 4000,
                    "valley_fill_hours": FILL_HOURS[index],
                    "valley_fill_price_cny_per_mwh": 300,
                    "freq_price_cny_per_kw_month": 15,
                }
            )
    print(f"已写入 {path}（12 个月，DR 129 h，填谷 360 h）")


if __name__ == "__main__":
    main()
