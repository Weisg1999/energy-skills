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
TRADING_DAY = "2026-11-19"
SCENARIO_OFFSETS = (-120.0, -60.0, 0.0, 70.0, 160.0)
TARGET_CYCLES = 1.6


def base_price(slot):
    hour = slot / 12.0
    if hour < 6:
        price = 285.0 + 18.0 * math.sin(2.0 * math.pi * slot / 288.0)
    elif hour < 8:
        price = 285.0 + 70.0 * (hour - 6.0)
    elif hour < 11:
        price = 425.0 + 15.0 * math.sin(2.0 * math.pi * slot / 61.0)
    elif hour < 16:
        price = 95.0 + 35.0 * math.sin(2.0 * math.pi * (slot - 132) / 120.0)
    elif hour < 17:
        price = 95.0 + 280.0 * (hour - 16.0)
    elif hour < 21:
        price = 615.0 + 35.0 * math.sin(2.0 * math.pi * (slot - 204) / 144.0)
    else:
        price = 615.0 - 95.0 * (hour - 21.0)
    return price + 12.0 * math.sin(2.0 * math.pi * slot / 37.0)


def scenario_price(slot, index):
    shape = 14.0 * math.sin(2.0 * math.pi * (slot + 11 * index) / 288.0)
    return base_price(slot) + SCENARIO_OFFSETS[index] + shape


def actual_da_price(slot):
    return base_price(slot) + 6.0 * math.sin(2.0 * math.pi * (slot + 5) / 97.0)


def actual_rt_price(slot):
    hour = slot / 12.0
    if 17.0 <= hour < 21.0:
        spread = 45.0
        if 204 <= slot <= 216:
            spread += 110.0
    elif 11.0 <= hour < 16.0:
        spread = -18.0
    elif hour < 6.0:
        spread = 8.0
    else:
        spread = 4.0
    noise = 22.0 * math.sin(2.0 * math.pi * (slot + 13) / 53.0) + 11.0 * math.cos(
        2.0 * math.pi * slot / 29.0
    )
    return actual_da_price(slot) + spread + noise


def slot_time(slot):
    minutes = slot * 5
    hour, minute = divmod(minutes, 60)
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

    da_prices = [clip(actual_da_price(slot)) for slot in range(n)]
    rt_prices = [clip(actual_rt_price(slot)) for slot in range(n)]
    schedule = run.solve_scenario(rt_prices, config, report)
    power = float(config["asset"]["power_mw"])
    actual_discharge = [
        min(power, value / 1000.0 * 0.97)
        for value in schedule["schedule"]["p_discharge_kw"]
    ]
    actual_charge = [
        min(power, value / 1000.0 * 1.03)
        for value in schedule["schedule"]["p_charge_kw"]
    ]
    # The raw DP arbitrages every small wiggle; a desk run respects a daily
    # cycle budget. Scaling toward the initial SOC keeps the trajectory feasible.
    through_put_mw = sum(actual_discharge) + sum(actual_charge)
    raw_throughput = through_put_mw * (report["mtu_min"] / 60.0)
    target_throughput = TARGET_CYCLES * 2.0 * float(config["asset"]["energy_mwh"])
    scale = target_throughput / raw_throughput
    actual_discharge = [value * scale for value in actual_discharge]
    actual_charge = [value * scale for value in actual_charge]

    t1_rows = [
        {
            "date": TRADING_DAY,
            "slot": slot,
            "da_price": f"{da_prices[slot]:.2f}",
            "rt_price": f"{rt_prices[slot]:.2f}",
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
            fieldnames=[
                "date",
                "slot",
                "da_price",
                "rt_price",
                "actual_discharge_mw",
                "actual_charge_mw",
            ],
        )
        writer.writeheader()
        writer.writerows(t1_rows)

    all_scenario_prices = [
        float(d1_rows[slot][field])
        for slot in range(n)
        for field in report["scenario_fields"]
    ]
    throughput_mwh = (sum(actual_discharge) + sum(actual_charge)) * (
        report["mtu_min"] / 60.0
    )
    print(f"trading day       {TRADING_DAY}")
    print(f"points            {n} x {report['mtu_min']:g} min")
    print(
        f"scenario prices   {min(all_scenario_prices):.1f} .. {max(all_scenario_prices):.1f} CNY/MWh"
    )
    print(f"actual DA / RT    {min(da_prices):.1f}-{max(da_prices):.1f} / {min(rt_prices):.1f}-{max(rt_prices):.1f}")
    print(
        f"actual schedule   discharge {sum(actual_discharge) * report['mtu_min'] / 60.0:.1f} MWh, "
        f"charge {sum(actual_charge) * report['mtu_min'] / 60.0:.1f} MWh"
    )
    print(
        f"equivalent cycles {throughput_mwh / (2.0 * float(config['asset']['energy_mwh'])):.2f}"
    )
    fuse = report["fuse"]
    start_slot = int(fuse["window_start_min"] // report["mtu_min"])
    end_slot = int(fuse["window_end_min"] // report["mtu_min"])
    window_rt = rt_prices[start_slot:end_slot]
    print(
        f"fuse window       {fuse['window_start']}-{fuse['window_end']} "
        f"RT mean {sum(window_rt) / len(window_rt):.1f} vs fuse {fuse['settlement_price']:.0f}"
    )


if __name__ == "__main__":
    main()
