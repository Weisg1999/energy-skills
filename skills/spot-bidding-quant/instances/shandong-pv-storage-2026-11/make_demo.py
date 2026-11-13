#!/usr/bin/env python3
"""Generate the synthetic D-1 and T+1 CSV files for the PV+storage pack.

All numbers are grade-D synthetic. The five price scenarios are paired with
five PV scenarios of opposite quality: the cloudy scenario has high prices, the
sunny scenario has low or negative midday prices. This correlation is the point
of the pack; independent price and PV sampling would overstate the joint
entity's revenue.

Run from this directory:

    python make_demo.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATE = "2026-11-18"
POINTS = 96
MTU_MIN = 15

PRICE_ANCHORS = [
    (0.0, 330.0),
    (5.0, 310.0),
    (6.5, 330.0),
    (8.0, 390.0),
    (9.5, 260.0),
    (10.5, 80.0),
    (12.0, -20.0),
    (14.0, 10.0),
    (15.5, 220.0),
    (17.0, 520.0),
    (18.5, 660.0),
    (20.0, 620.0),
    (21.5, 430.0),
    (24.0, 330.0),
]

MIDDAY_OFFSET = [140.0, 70.0, 0.0, -50.0, -80.0]
EVENING_OFFSET = [110.0, 55.0, 0.0, -55.0, -110.0]
MORNING_OFFSET = [20.0, 10.0, 0.0, -10.0, -20.0]
PV_FACTOR = [0.72, 0.86, 1.00, 1.12, 1.22]
WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]
PV_CAPACITY = 200.0
EXPORT_LIMIT = 100.0
STORAGE_POWER = 100.0
STORAGE_ENERGY = 200.0
SOC_MIN = 0.05
SOC_MAX = 0.95
SOC_INIT = 0.10
RTE = 0.88


def interpolate(anchors, hour):
    for index in range(len(anchors) - 1):
        h0, v0 = anchors[index]
        h1, v1 = anchors[index + 1]
        if h0 <= hour <= h1:
            fraction = (hour - h0) / (h1 - h0)
            return v0 + (v1 - v0) * fraction
    return anchors[-1][1]


def price_base(slot):
    hour = slot * 0.25 + 0.125
    return interpolate(PRICE_ANCHORS, hour)


def scenario_offset(scenario, hour):
    if 9.5 <= hour < 15.5:
        return MIDDAY_OFFSET[scenario]
    if 16.5 <= hour < 21.5:
        return EVENING_OFFSET[scenario]
    if 6.0 <= hour < 9.0:
        return MORNING_OFFSET[scenario]
    return 0.0


def pv_base(slot):
    hour = slot * 0.25 + 0.125
    if hour < 7.0 or hour > 17.2:
        return 0.0
    x = (hour - 12.1) / 3.6
    return max(0.0, 150.0 * (1.0 - x * x))


def clip(value, low, high):
    return low if value < low else high if value > high else value


def build_d1():
    rows = []
    for slot in range(POINTS):
        hour = slot * 0.25
        end_hour = hour + 0.25
        row = {
            "date": DATE,
            "slot": slot,
            "start": f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}",
            "end": f"{int(end_hour):02d}:{int(round((end_hour % 1) * 60)):02d}",
        }
        for scenario in range(5):
            price = clip(
                price_base(slot) + scenario_offset(scenario, hour + 0.125),
                -100.0,
                1500.0,
            )
            pv = min(PV_CAPACITY, pv_base(slot) * PV_FACTOR[scenario])
            row[f"pv_s{scenario + 1}"] = round(pv, 3)
            row[f"price_s{scenario + 1}"] = round(price, 3)
        rows.append(row)
    return rows


def build_t1():
    """A plausible actual day: slightly more PV, a midday cloud dip, lower evening peak."""
    rows = []
    eta = math.sqrt(RTE)
    energy = SOC_INIT * STORAGE_ENERGY
    low = SOC_MIN * STORAGE_ENERGY
    high = SOC_MAX * STORAGE_ENERGY
    for slot in range(POINTS):
        hour = slot * 0.25
        end_hour = hour + 0.25
        midpoint = hour + 0.125
        price = clip(price_base(slot) + 25.0, -100.0, 1500.0)
        if 17.0 <= midpoint < 21.0:
            price = clip(price - 35.0, -100.0, 1500.0)
        elif 6.0 <= midpoint < 9.0:
            price = clip(price + 5.0, -100.0, 1500.0)
        pv = min(PV_CAPACITY, pv_base(slot) * 1.04)
        if 11.75 <= midpoint < 12.5:
            pv = min(PV_CAPACITY, pv * 0.82)
        charge = 0.0
        discharge = 0.0
        if price < 30.0 and pv > 20.0:
            charge = min(STORAGE_POWER, 0.60 * pv, max(0.0, (high - energy) / (eta * 0.25)))
            energy += charge * eta * 0.25
        elif price > 450.0 and 17.0 <= midpoint < 20.5:
            discharge = min(STORAGE_POWER, 85.0, max(0.0, (energy - low) * eta / 0.25))
            energy -= discharge / eta * 0.25
        gross = pv - charge + discharge
        export = min(EXPORT_LIMIT, max(0.0, gross))
        curtail = max(0.0, gross - export)
        rows.append(
            {
                "date": DATE,
                "slot": slot,
                "start": f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}",
                "end": f"{int(end_hour):02d}:{int(round((end_hour % 1) * 60)):02d}",
                "actual_price": round(price, 3),
                "actual_pv_mw": round(pv, 3),
                "actual_charge_mw": round(charge, 3),
                "actual_discharge_mw": round(discharge, 3),
                "actual_export_mw": round(export, 3),
                "actual_curtail_mw": round(curtail, 3),
            }
        )
    return rows


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    d1 = build_d1()
    t1 = build_t1()
    write_csv(
        DATA / "d1_demo.csv",
        d1,
        ["date", "slot", "start", "end"]
        + [f"pv_s{index}" for index in range(1, 6)]
        + [f"price_s{index}" for index in range(1, 6)],
    )
    write_csv(
        DATA / "t1_demo.csv",
        t1,
        [
            "date",
            "slot",
            "start",
            "end",
            "actual_price",
            "actual_pv_mw",
            "actual_charge_mw",
            "actual_discharge_mw",
            "actual_export_mw",
            "actual_curtail_mw",
        ],
    )
    print(f"wrote {DATA / 'd1_demo.csv'} and {DATA / 't1_demo.csv'}")


if __name__ == "__main__":
    main()
