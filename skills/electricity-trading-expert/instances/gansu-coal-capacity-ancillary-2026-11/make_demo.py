#!/usr/bin/env python3
"""Generate the synthetic monthly market profile for the Gansu coal pack."""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

MONTHS = list(range(1, 13))
DAYS = [31, 28, 31, 25, 26, 30, 31, 31, 30, 31, 30, 31]
VALLEY_PRICE = [260, 250, 230, 210, 190, 180, 190, 200, 210, 230, 250, 270]
FLAT_PRICE = [150, 140, 120, 90, 70, 55, 60, 65, 80, 110, 140, 160]
PEAK_PRICE = [520, 500, 470, 440, 420, 430, 470, 480, 450, 460, 500, 540]
CONTRACT_MWH = [450000, 400000, 430000, 330000, 330000, 380000, 420000, 420000, 390000, 400000, 410000, 440000]

FIELDS = [
    "month",
    "days",
    "valley_hours",
    "flat_hours",
    "peak_hours",
    "valley_price_cny_per_mwh",
    "flat_price_cny_per_mwh",
    "peak_price_cny_per_mwh",
    "contract_mwh",
]


def main() -> None:
    assert sum(DAYS) == 355, sum(DAYS)
    assert sum(CONTRACT_MWH) == 4_800_000, sum(CONTRACT_MWH)
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "market_demo.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for i, month in enumerate(MONTHS):
            writer.writerow(
                {
                    "month": month,
                    "days": DAYS[i],
                    "valley_hours": 8,
                    "flat_hours": 8,
                    "peak_hours": 8,
                    "valley_price_cny_per_mwh": VALLEY_PRICE[i],
                    "flat_price_cny_per_mwh": FLAT_PRICE[i],
                    "peak_price_cny_per_mwh": PEAK_PRICE[i],
                    "contract_mwh": CONTRACT_MWH[i],
                }
            )
    print(f"已写入 {path}（12 个月，合同电量 4,800,000 MWh）")


if __name__ == "__main__":
    main()
