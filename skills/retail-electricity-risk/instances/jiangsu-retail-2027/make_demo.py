#!/usr/bin/env python3
"""Generate grade-D synthetic D-1 and T+1 data for the Jiangsu 2027 retail demo.

The data are deterministic, contain no real customer or market information, and
only exist to exercise the pass-through + cap model in run.py.

    python make_demo.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATE = "2027-01-15"
POINTS = 96
MTU_MIN = 15

LOAD_ANCHORS = [
    62, 58, 55, 54, 56, 62, 72, 82, 90, 95, 98, 96,
    90, 92, 95, 98, 102, 108, 115, 112, 105, 95, 82, 70,
]
PRICE_ANCHORS = [
    300, 280, 270, 265, 270, 290, 330, 380, 420, 410, 380, 360,
    340, 330, 340, 370, 420, 480, 530, 510, 460, 400, 350, 320,
]
SCENARIO_OFFSETS = [-80.0, -40.0, 0.0, 40.0, 100.0]


def interp(anchors, slot):
    hour = slot * MTU_MIN / 60.0
    left = int(math.floor(hour)) % 24
    right = (left + 1) % 24
    fraction = hour - math.floor(hour)
    return anchors[left] * (1.0 - fraction) + anchors[right] * fraction


def load_curve():
    target_average = 720000.0 / 365.0 / 24.0
    raw = [interp(LOAD_ANCHORS, slot) for slot in range(POINTS)]
    scale = target_average / (sum(raw) / len(raw))
    return [
        raw[slot] * scale
        * (1.0 + 0.015 * math.sin(2.0 * math.pi * slot / POINTS * 7.0)
           + 0.008 * math.sin(2.0 * math.pi * slot / POINTS * 13.0))
        for slot in range(POINTS)
    ]


def price_curve(offset):
    return [
        max(0.0, interp(PRICE_ANCHORS, slot) + offset
            + 6.0 * math.sin(2.0 * math.pi * slot / POINTS * 5.0))
        for slot in range(POINTS)
    ]


def actual_load(forecast):
    rows = []
    for slot, value in enumerate(forecast):
        deviation = (
            0.010 * math.sin(2.0 * math.pi * slot / POINTS * 4.0)
            + 0.020 * math.sin(2.0 * math.pi * slot / POINTS * 9.0)
        )
        if 70 <= slot <= 74:
            deviation += 0.050
        if 20 <= slot <= 24:
            deviation -= 0.040
        rows.append(value * (1.0 + deviation))
    return rows


def actual_price(base):
    rows = []
    for slot, value in enumerate(base):
        price = value * (1.0 + 0.015 * math.sin(2.0 * math.pi * slot / POINTS * 6.0))
        if 68 <= slot <= 76:
            price += 40.0
        if 8 <= slot <= 16:
            price -= 15.0
        rows.append(max(0.0, price))
    return rows


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    forecast = load_curve()
    scenarios = {f"price_s{index}": price_curve(offset) for index, offset in enumerate(SCENARIO_OFFSETS, start=1)}
    actual = actual_load(forecast)
    actual_spot = actual_price(scenarios["price_s3"])

    d1_fields = ["date", "slot", "start", "end", "forecast_load_mw"] + list(scenarios)
    d1_rows = []
    for slot in range(POINTS):
        minutes = slot * MTU_MIN
        row = {
            "date": DATE,
            "slot": slot,
            "start": f"{minutes // 60:02d}:{minutes % 60:02d}",
            "end": f"{(minutes + MTU_MIN) // 60:02d}:{(minutes + MTU_MIN) % 60:02d}",
            "forecast_load_mw": f"{forecast[slot]:.6f}",
        }
        for field, curve in scenarios.items():
            row[field] = f"{curve[slot]:.2f}"
        d1_rows.append(row)

    t1_fields = [
        "date", "slot", "start", "end", "actual_load_mw", "actual_price",
        "actual_p1", "actual_p2", "actual_p3",
    ]
    t1_rows = []
    for slot in range(POINTS):
        minutes = slot * MTU_MIN
        t1_rows.append(
            {
                "date": DATE,
                "slot": slot,
                "start": f"{minutes // 60:02d}:{minutes % 60:02d}",
                "end": f"{(minutes + MTU_MIN) // 60:02d}:{(minutes + MTU_MIN) % 60:02d}",
                "actual_load_mw": f"{actual[slot]:.6f}",
                "actual_price": f"{actual_spot[slot]:.2f}",
                "actual_p1": "1.60",
                "actual_p2": "5.50",
                "actual_p3": "-0.12",
            }
        )

    write_csv(DATA / "d1_demo.csv", d1_fields, d1_rows)
    write_csv(DATA / "t1_demo.csv", t1_fields, t1_rows)

    energy = sum(forecast) * MTU_MIN / 60.0
    print(f"wrote {len(d1_rows)} x D-1 rows and {len(t1_rows)} x T+1 rows")
    print(f"forecast energy {energy:,.1f} MWh; average load {sum(forecast)/len(forecast):.2f} MW")
    print(f"scenario s3 load-weighted average {sum(p*q for p,q in zip(scenarios['price_s3'], forecast))/sum(forecast):.2f} CNY/MWh")
    print(f"actual energy {sum(actual)*MTU_MIN/60.0:,.1f} MWh")


if __name__ == "__main__":
    main()
