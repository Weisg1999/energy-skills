#!/usr/bin/env python3
"""Generate the synthetic monthly profile for the Guangdong multi-user pack."""

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "profile_demo.csv"

MONTHS = [f"2027-{m:02d}" for m in range(1, 13)]
GENERATION = [42000.0, 42000.0, 42000.0, 36000.0, 28000.0, 24000.0,
              24000.0, 24000.0, 26000.0, 30000.0, 38000.0, 44000.0]
USER_A = [13000.0] * 12
USER_B = [10000.0, 9000.0, 9000.0, 8000.0, 7000.0, 5000.0,
          4000.0, 4000.0, 5000.0, 7000.0, 8000.0, 8000.0]
USER_C = [3000.0, 2000.0, 3000.0, 3000.0, 5000.0, 7000.0,
          9000.0, 9000.0, 7000.0, 5000.0, 3000.0, 4000.0]
FEED_IN_PRICE = [250.0] * 12


def main():
    assert sum(GENERATION) == 400000.0, sum(GENERATION)
    assert sum(USER_A) == 156000.0, sum(USER_A)
    assert sum(USER_B) == 84000.0, sum(USER_B)
    assert sum(USER_C) == 60000.0, sum(USER_C)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["month", "generation_mwh", "user_a_mwh", "user_b_mwh",
                         "user_c_mwh", "feed_in_price_cny_per_mwh"])
        for month, generation, a, b, c, price in zip(
                MONTHS, GENERATION, USER_A, USER_B, USER_C, FEED_IN_PRICE):
            writer.writerow([month, f"{generation:.1f}", f"{a:.1f}",
                             f"{b:.1f}", f"{c:.1f}", f"{price:.1f}"])
    print(f"写入 {OUT}：12 个月，发电量 {sum(GENERATION):,.0f} MWh，"
          f"用电量 {sum(USER_A) + sum(USER_B) + sum(USER_C):,.0f} MWh")


if __name__ == "__main__":
    main()
