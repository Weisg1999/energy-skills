#!/usr/bin/env python3
"""Generate the synthetic monthly profile for the Gansu wind export pack.

Columns: actual generation, contract weight (sums to 1), Shandong landing spot
price and the green share of the contract. All values are grade D synthetic
data and do not correspond to any real wind farm or channel.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "profile_demo.csv"

GENERATION_MWH = [40800, 38400, 45600, 48000, 45600, 36000, 28800, 28800, 33600, 40800, 45600, 48000]
CONTRACT_WEIGHT = [
    0.080357,
    0.074405,
    0.086310,
    0.092262,
    0.086310,
    0.077381,
    0.089286,
    0.089286,
    0.065476,
    0.077381,
    0.089286,
    0.092260,
]
SPOT_PRICE = [0.30, 0.29, 0.26, 0.23, 0.21, 0.24, 0.28, 0.28, 0.25, 0.22, 0.27, 0.31]
GREEN_RATIO = [0.30] * 12


def main():
    if abs(sum(GENERATION_MWH) - 480000) > 1e-9:
        raise ValueError("monthly generation must sum to 480,000 MWh")
    if abs(sum(CONTRACT_WEIGHT) - 1.0) > 1e-6:
        raise ValueError(f"contract weights sum to {sum(CONTRACT_WEIGHT)}")
    if not (len(GENERATION_MWH) == len(CONTRACT_WEIGHT) == len(SPOT_PRICE) == len(GREEN_RATIO) == 12):
        raise ValueError("all columns must have 12 rows")

    rows = []
    for index in range(12):
        rows.append(
            {
                "month": f"2027-{index + 1:02d}",
                "generation_mwh": f"{GENERATION_MWH[index]:.0f}",
                "contract_weight": f"{CONTRACT_WEIGHT[index]:.6f}",
                "spot_price_cny_per_kwh": f"{SPOT_PRICE[index]:.4f}",
                "green_ratio": f"{GREEN_RATIO[index]:.4f}",
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "month",
                "generation_mwh",
                "contract_weight",
                "spot_price_cny_per_kwh",
                "green_ratio",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows, {sum(GENERATION_MWH):,.0f} MWh)")


if __name__ == "__main__":
    main()
