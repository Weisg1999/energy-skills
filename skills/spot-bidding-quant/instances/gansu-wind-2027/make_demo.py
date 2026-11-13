#!/usr/bin/env python3
"""Regenerate the synthetic D-1 / T+1 demo CSVs for the Gansu wind pack.

The demo is deterministic so the selftest and the review sheet stay
reproducible. It is grade D: not a wind forecast, not a market sample and not
investment advice.

    python make_demo.py
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent
TRADING_DAY = "2027-01-15"
WIND_MULTIPLIERS = (0.82, 0.92, 1.00, 1.08, 1.18)
PRICE_OFFSETS = (-95.0, -45.0, 0.0, 55.0, 125.0)


def base_wind(slot):
    hour = slot / 4.0
    if hour < 6:
        wind = 122.0 + 10.0 * math.sin(2.0 * math.pi * (slot + 4) / 96.0)
    elif hour < 10:
        wind = 108.0 - 3.5 * (hour - 6.0)
    elif hour < 15:
        wind = 62.0 + 6.0 * math.sin(2.0 * math.pi * (slot - 40) / 28.0)
    elif hour < 17:
        wind = 76.0 + 15.0 * (hour - 15.0)
    elif hour < 19:
        wind = 122.0 + 7.0 * math.sin(2.0 * math.pi * (slot - 68) / 8.0)
    else:
        wind = 128.0 + 6.0 * math.sin(2.0 * math.pi * (slot + 6) / 96.0)
    return wind


def scenario_wind(slot, index):
    shape = 0.04 * math.sin(2.0 * math.pi * (slot + 6 * index) / 96.0)
    return base_wind(slot) * (WIND_MULTIPLIERS[index] + shape)


def base_price(slot):
    hour = slot / 4.0
    if hour < 7:
        price = 235.0 + 22.0 * math.sin(2.0 * math.pi * (slot + 6) / 96.0)
    elif hour < 10:
        price = 320.0 + 28.0 * (hour - 7.0)
    elif hour < 16:
        price = 60.0 + 22.0 * math.sin(2.0 * math.pi * (slot - 40) / 24.0)
    elif hour < 19:
        price = 330.0 + 62.0 * (hour - 16.0)
    elif hour < 22:
        price = 555.0 - 18.0 * (hour - 19.0)
    else:
        price = 330.0 - 18.0 * (hour - 22.0)
    return price


def scenario_price(slot, index):
    shape = 10.0 * math.sin(2.0 * math.pi * (slot + 8 * index) / 96.0)
    return base_price(slot) + PRICE_OFFSETS[index] + shape


def actual_wind(slot):
    hour = slot / 4.0
    if 17.0 <= hour < 18.5:
        factor = 0.80
    elif hour < 6.0:
        factor = 1.03
    elif hour < 10.0:
        factor = 1.01
    elif hour < 15.0:
        factor = 0.98
    elif hour < 17.0:
        factor = 0.97
    else:
        factor = 1.02
    factor += 0.012 * math.sin(2.0 * math.pi * (slot + 7) / 23.0)
    return base_wind(slot) * factor


def rt_spread(slot):
    hour = slot / 4.0
    if 17.0 <= hour < 19.0:
        spread = 45.0
    elif 19.0 <= hour < 22.0:
        spread = 70.0
    elif 10.0 <= hour < 16.0:
        spread = -12.0
    else:
        spread = 6.0
    return spread + 9.0 * math.sin(2.0 * math.pi * (slot + 3) / 13.0)


def slot_time(slot):
    hour, minute = divmod(slot * 15, 60)
    return f"{hour:02d}:{minute:02d}"


def main():
    config = json.loads((HERE / "instance.json").read_text(encoding="utf-8"))
    report = run.validate_instance(config)
    bounds = report["bounds"]
    power = report["predicates"]["power"]
    n = report["points_per_day"]

    def clip_price(price):
        return min(bounds["clear_cap"], max(bounds["clear_floor"], price))

    def clip_wind(value):
        return min(power, max(0.0, value))

    data_dir = HERE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    d1_rows = []
    for slot in range(n):
        row = {
            "date": TRADING_DAY,
            "slot": slot,
            "start": slot_time(slot),
            "end": slot_time(slot + 1) if slot < n - 1 else "24:00",
            "forecast_mw": f"{clip_wind(base_wind(slot)):.3f}",
        }
        for index in range(len(WIND_MULTIPLIERS)):
            row[f"wind_s{index + 1}"] = f"{clip_wind(scenario_wind(slot, index)):.3f}"
            row[f"price_s{index + 1}"] = f"{clip_price(scenario_price(slot, index)):.2f}"
        d1_rows.append(row)

    actual = [clip_wind(actual_wind(slot)) for slot in range(n)]
    da_prices = [
        clip_price(scenario_price(slot, 2) + 5.0 * math.sin(2.0 * math.pi * slot / 31.0))
        for slot in range(n)
    ]
    rt_prices = [clip_price(da_prices[slot] + rt_spread(slot)) for slot in range(n)]
    t1_rows = [
        {
            "date": TRADING_DAY,
            "slot": slot,
            "actual_da_price": f"{da_prices[slot]:.2f}",
            "actual_rt_price": f"{rt_prices[slot]:.2f}",
            "actual_output_mw": f"{actual[slot]:.3f}",
        }
        for slot in range(n)
    ]

    d1_fields = ["date", "slot", "start", "end", "forecast_mw"] + list(report["wind_fields"]) + list(
        report["price_fields"]
    )
    with (data_dir / "d1_demo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=d1_fields)
        writer.writeheader()
        writer.writerows(d1_rows)
    with (data_dir / "t1_demo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "slot", "actual_da_price", "actual_rt_price", "actual_output_mw"],
        )
        writer.writeheader()
        writer.writerows(t1_rows)

    dt_h = report["mtu_min"] / 60.0
    forecast_energy = sum(float(row["forecast_mw"]) for row in d1_rows) * dt_h
    wind_energy = sum(actual) * dt_h
    price_min = min(float(row[field]) for row in d1_rows for field in report["price_fields"])
    price_max = max(float(row[field]) for row in d1_rows for field in report["price_fields"])
    print(f"trading day       {TRADING_DAY}")
    print(f"forecast energy   {forecast_energy:,.1f} MWh")
    print(f"actual energy     {wind_energy:,.1f} MWh")
    print(f"scenario prices   {price_min:.1f} .. {price_max:.1f} CNY/MWh")


if __name__ == "__main__":
    main()
