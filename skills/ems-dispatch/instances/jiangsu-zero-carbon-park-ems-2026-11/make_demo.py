#!/usr/bin/env python3
"""Generate the bundled 96-point profile for the Jiangsu park pack.

The profile is a workday with a lunch dip, a 6 MWp PV bell and a three-segment
time-of-use tariff. All values are synthetic grade D.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

DT_H = 0.25
POINTS = 96


def load_kw(hour: float) -> float:
    if hour < 6:
        return 2600.0
    if hour < 8:
        return 2600.0 + (hour - 6.0) / 2.0 * 2200.0
    if hour < 11.5:
        return 4800.0
    if hour < 13:
        return 3400.0
    if hour < 17:
        return 5200.0
    if hour < 18:
        return 4800.0
    if hour < 21:
        return 5400.0
    if hour < 22:
        return 4200.0
    return 3000.0


def pv_kw(hour: float) -> float:
    if not 6.5 <= hour <= 18.0:
        return 0.0
    shape = max(0.0, 1.0 - ((hour - 12.25) / 5.75) ** 2) ** 1.1
    return 4900.0 * shape


def segment(hour: float) -> str:
    if 8 <= hour < 11.5 or 13 <= hour < 17 or 18 <= hour < 21:
        return "peak"
    if hour < 8 or hour >= 22:
        return "valley"
    return "flat"


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    price = {"peak": 0.95, "flat": 0.62, "valley": 0.28}
    rows = []
    for i in range(POINTS):
        hour = i * DT_H
        seg = segment(hour)
        rows.append(
            {
                "interval": i,
                "time": f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}",
                "load_kw": round(load_kw(hour), 1),
                "pv_kw": round(pv_kw(hour), 1),
                "buy_cny_per_kwh": price[seg],
                "segment": seg,
            }
        )
    path = DATA / "profile_demo.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["interval", "time", "load_kw", "pv_kw", "buy_cny_per_kwh", "segment"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {path}（{len(rows)} 点）")


if __name__ == "__main__":
    main()
