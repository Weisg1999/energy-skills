#!/usr/bin/env python3
"""Regenerate the synthetic D-1 / T+1 demo CSVs for this instance.

The demo is deterministic so the selftest and the review sheet stay reproducible.
It is grade D: not a forecast, not a market sample and not investment advice.

    python make_demo.py
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
TRADING_DAY = "2026-11-18"
SCENARIO_OFFSETS = (-70.0, -30.0, 0.0, 50.0, 120.0)


def base_price(slot):
    hour = slot * 0.25
    if hour < 7:
        price = 300.0
    elif hour < 11:
        price = 380.0
    elif hour < 15:
        price = -60.0
    elif hour < 17:
        price = 320.0
    elif hour < 22:
        price = 720.0
    else:
        price = 350.0
    return price + 25.0 * math.sin(2.0 * math.pi * slot / 96.0)


def scenario_price(slot, index):
    shape = 12.0 * math.sin(2.0 * math.pi * (slot + 8 * index) / 96.0)
    return base_price(slot) + SCENARIO_OFFSETS[index] + shape


def actual_price(slot):
    noise = 35.0 * math.sin(2.0 * math.pi * (slot + 13) / 37.0) + 20.0 * math.cos(
        2.0 * math.pi * slot / 19.0
    )
    return base_price(slot) + noise


def slot_time(slot):
    hour, minute = divmod(slot * 15, 60)
    return f"{hour:02d}:{minute:02d}"


def main():
    config = json.loads((HERE / "instance.json").read_text(encoding="utf-8"))
    report = run.validate_instance(config)
    bounds = report["bounds"]
    n = report["points_per_day"]

    def clip(price):
        return min(bounds["clear_cap"], max(bounds["clear_floor"], price))

    data_dir = HERE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    d1_rows = []
    for slot in range(n):
        row = {
            "date": TRADING_DAY,
            "slot": slot,
            "start": slot_time(slot),
            "end": slot_time(slot + 1) if slot < n - 1 else "24:00",
        }
        for index in range(len(SCENARIO_OFFSETS)):
            row[f"price_s{index + 1}"] = f"{clip(scenario_price(slot, index)):.2f}"
        d1_rows.append(row)

    actual_prices = [clip(actual_price(slot)) for slot in range(n)]
    schedule = run.solve_scenario(actual_prices, config, report)
    power = float(config["asset"]["power_mw"])
    actual_discharge = [
        min(power, value / 1000.0 * 0.96)
        for value in schedule["schedule"]["p_discharge_kw"]
    ]
    actual_charge = [
        min(power, value / 1000.0 * 1.02)
        for value in schedule["schedule"]["p_charge_kw"]
    ]
    # The raw DP arbitrages every small wiggle; a desk run respects a daily
    # cycle budget. Scaling keeps the SOC trajectory inside the same window.
    target_cycles = 1.4
    raw_throughput = sum(actual_discharge) + sum(actual_charge)
    target_throughput = target_cycles * 2.0 * float(config["asset"]["energy_mwh"])
    scale = target_throughput / raw_throughput
    actual_discharge = [value * scale for value in actual_discharge]
    actual_charge = [value * scale for value in actual_charge]
    t1_rows = [
        {
            "date": TRADING_DAY,
            "slot": slot,
            "actual_price": f"{actual_prices[slot]:.2f}",
            "actual_discharge_mw": f"{actual_discharge[slot]:.3f}",
            "actual_charge_mw": f"{actual_charge[slot]:.3f}",
        }
        for slot in range(n)
    ]

    d1_fields = ["date", "slot", "start", "end"] + list(report["scenario_fields"])
    with (data_dir / "d1_demo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=d1_fields)
        writer.writeheader()
        writer.writerows(d1_rows)
    with (data_dir / "t1_demo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "slot", "actual_price", "actual_discharge_mw", "actual_charge_mw"],
        )
        writer.writeheader()
        writer.writerows(t1_rows)

    all_prices = [price for slot in range(n) for price in (float(d1_rows[slot][field]) for field in report["scenario_fields"])]
    throughput = sum(actual_discharge) + sum(actual_charge)
    print(f"trading day      {TRADING_DAY}")
    print(f"scenario prices  {min(all_prices):.1f} .. {max(all_prices):.1f} CNY/MWh")
    print(f"actual schedule  discharge {sum(actual_discharge):.1f} MWh, charge {sum(actual_charge):.1f} MWh")
    print(f"equivalent cycles {throughput / (2.0 * float(config['asset']['energy_mwh'])):.2f}")


if __name__ == "__main__":
    main()
