#!/usr/bin/env python3
"""Generate the bundled 96-point profile for the Shandong storage-station pack.

The profile is a representative day with a four-segment spot price (valley,
midday PV dip, evening peak, flat), an AGC regulation setpoint and a handful of
frequency-deviation events. All values are synthetic grade D and correspond to
no real station, dispatch instruction or grid event.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

DT_H = 0.25
POINTS = 96

PRICE = {"valley": 200.0, "midday": 100.0, "peak": 900.0, "flat": 450.0}


def segment(hour: float) -> str:
    if hour < 7:
        return "valley"
    if 10 <= hour < 14:
        return "midday"
    if 18 <= hour < 22:
        return "peak"
    return "flat"


def agc_signal(i: int) -> float:
    base = 12.0 * math.sin(i * 0.22)
    if 56 <= i < 64:
        base += 60.0
    return round(base, 2)


def freq_deviation(i: int) -> float:
    events = {20: 0.06, 40: -0.10, 76: -0.50, 84: -0.15}
    return events.get(i, 0.0)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(POINTS):
        hour = i * DT_H
        seg = segment(hour)
        rows.append(
            {
                "interval": i,
                "time": f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}",
                "price_cny_per_mwh": PRICE[seg],
                "agc_signal_mw": agc_signal(i),
                "freq_deviation_hz": freq_deviation(i),
                "segment": seg,
            }
        )
    path = DATA / "profile_demo.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "interval",
                "time",
                "price_cny_per_mwh",
                "agc_signal_mw",
                "freq_deviation_hz",
                "segment",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {path}（{len(rows)} 点）")


if __name__ == "__main__":
    main()