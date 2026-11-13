#!/usr/bin/env python3
"""Generate grade-D synthetic data for the Shandong thermal hedge pack.

The demo is deliberately shaped so that the pack exercises its own questions:

* the forecast output is above the contract position, so the book is under-hedged
  and there is a positive sell-surplus;
* the contract book is peak-heavy while the spot peak is higher than the
  monthly-peak contract price, so the hedge-value decomposition has a positive
  carry and a negative shape term;
* the T+1 contract energy is adjusted away from the D-1 position, so the
  contract-volume and contract-shape buckets in the bridge are not zero.

Run from this directory:

    python make_demo.py
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parents[1]
sys.path.insert(0, str(SKILL_DIR / "tools"))

import hedge  # noqa: E402

TRADING_DAY = "2026-11-18"
POINTS = 96
MTU_MIN = 15
DT_H = MTU_MIN / 60.0
EXPORT_FLOOR = -100.0


def slot_time(slot):
    minutes = int(slot * MTU_MIN)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def forecast_mw(slot):
    hour = slot * DT_H
    if hour < 8:
        base = 340.0
    elif hour < 12:
        base = 380.0
    elif hour < 17:
        base = 360.0
    elif hour < 22:
        base = 420.0
    else:
        base = 330.0
    ripple = 6.0 * math.sin(2.0 * math.pi * 2.0 * (slot + 0.5) / POINTS)
    ripple += 3.0 * math.sin(2.0 * math.pi * 4.0 * (slot + 0.5) / POINTS)
    return round(base + ripple, 6)


def base_price(slot):
    hour = slot * DT_H
    if hour < 7:
        return 320.0
    if hour < 8:
        return 340.0
    if hour < 11:
        return 400.0
    if hour < 14:
        return 260.0
    if hour < 17:
        return 360.0
    if hour < 21:
        return 520.0
    if hour < 22:
        return 430.0
    return 300.0


def scenario_offset(scenario, slot):
    hour = slot * DT_H
    if scenario == 1:
        offset = -45.0
    elif scenario == 2:
        offset = -15.0
    elif scenario == 3:
        offset = 0.0
    elif scenario == 4:
        offset = 35.0 + (60.0 if 17 <= hour < 22 else 0.0)
    else:
        offset = 0.0
        if hour < 8:
            offset -= 25.0
        if 11 <= hour < 15:
            offset -= 80.0
        if 17 <= hour < 22:
            offset += 70.0
    ripple = 4.0 * math.sin(2.0 * math.pi * 3.0 * (slot + 0.5) / POINTS + scenario * 0.7)
    return offset + ripple


def scenario_price(scenario, slot):
    return round(max(EXPORT_FLOOR, base_price(slot) + scenario_offset(scenario, slot)), 6)


def actual_mw(slot):
    ripple = 5.0 * math.sin(2.0 * math.pi * 3.0 * (slot + 0.5) / POINTS)
    return round(forecast_mw(slot) * 0.983 + ripple, 6)


def actual_price(slot):
    value = base_price(slot)
    value += 10.0 * math.sin(2.0 * math.pi * 2.0 * (slot + 0.5) / POINTS)
    value += 5.0 * math.sin(2.0 * math.pi * 5.0 * (slot + 0.5) / POINTS)
    return round(value, 6)


def contract_factor(slot):
    hour = slot * DT_H
    if hour < 8:
        return 0.992
    if hour < 17:
        return 1.004
    if hour < 22:
        return 1.018
    return 1.000


def main():
    config = json.loads((HERE / "instance.json").read_text(encoding="utf-8"))
    book = hedge.book_position(config["book"], POINTS, MTU_MIN)
    position = book["position"]

    d1_rows = []
    for slot in range(POINTS):
        d1_rows.append(
            {
                "date": TRADING_DAY,
                "slot": slot,
                "start": slot_time(slot),
                "end": slot_time(slot + 1),
                "forecast_mw": f"{forecast_mw(slot):.6f}",
                "price_s1": f"{scenario_price(1, slot):.6f}",
                "price_s2": f"{scenario_price(2, slot):.6f}",
                "price_s3": f"{scenario_price(3, slot):.6f}",
                "price_s4": f"{scenario_price(4, slot):.6f}",
                "price_s5": f"{scenario_price(5, slot):.6f}",
            }
        )
    d1_path = HERE / "data" / "d1_demo.csv"
    d1_path.parent.mkdir(parents=True, exist_ok=True)
    with d1_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(d1_rows[0]))
        writer.writeheader()
        writer.writerows(d1_rows)

    t1_rows = []
    for slot in range(POINTS):
        t1_rows.append(
            {
                "date": TRADING_DAY,
                "slot": slot,
                "actual_mw": f"{actual_mw(slot):.6f}",
                "actual_contract_mwh": f"{position[slot] * contract_factor(slot):.6f}",
                "actual_da_price": f"{actual_price(slot):.6f}",
            }
        )
    t1_path = HERE / "data" / "t1_demo.csv"
    with t1_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(t1_rows[0]))
        writer.writeheader()
        writer.writerows(t1_rows)

    rolling_rows = [
        {"day_offset": -4, "forecast_output_mwh": 8450.0, "position_before_mwh": 7000.0},
        {"day_offset": -3, "forecast_output_mwh": 8600.0, "position_before_mwh": 7182.5},
        {"day_offset": -2, "forecast_output_mwh": 8380.0, "position_before_mwh": 7310.0},
        {"day_offset": -1, "forecast_output_mwh": 8720.0, "position_before_mwh": 7123.0},
        {"day_offset": 0, "forecast_output_mwh": 8800.0, "position_before_mwh": 7412.0},
    ]
    rolling_path = HERE / "data" / "rolling_demo.csv"
    with rolling_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rolling_rows[0]))
        writer.writeheader()
        writer.writerows(rolling_rows)

    forecast_energy = sum(forecast_mw(slot) for slot in range(POINTS)) * DT_H
    actual_energy = sum(actual_mw(slot) for slot in range(POINTS)) * DT_H
    actual_contract = sum(float(row["actual_contract_mwh"]) for row in t1_rows)
    print(f"d1  {d1_path}  forecast={forecast_energy:,.3f} MWh")
    print(f"t1  {t1_path}  actual={actual_energy:,.3f} MWh  contract={actual_contract:,.3f} MWh")
    print(f"rolling  {rolling_path}  days={len(rolling_rows)}")
    print(
        f"book  daily={book['energy_mwh']:,.3f} MWh  "
        f"hedge_ratio={book['energy_mwh'] / forecast_energy:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
