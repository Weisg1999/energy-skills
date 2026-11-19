#!/usr/bin/env python3
"""Regenerate the synthetic D-1 / T+1 demo CSVs for this instance.

The demo is deterministic so the selftest and the review sheet stay reproducible.
It is grade D: not a forecast, not a market sample and not investment advice.

The price shape follows the Zhejiang module description only qualitatively:
"midday PV surplus, evening scarcity" (§4.3) with the evening peak roughly
aligned to the 16:00-23:00 TOU peak of document 112 (§6.2). Every number is
synthetic; the module gives no Zhejiang spot time-of-day average to calibrate
against, so the levels are invented and clipped to the -200..1,200 CNY/MWh band.

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
SCENARIO_OFFSETS = (-160.0, -80.0, 0.0, 80.0, 160.0)
TARGET_CYCLES = 1.1


def base_price(slot):
    """Midday PV trough + evening peak 16:00-23:00, night valley (D-level shape)."""
    hour = slot / 12.0
    if hour < 6:
        price = 170.0 + 10.0 * math.sin(2.0 * math.pi * slot / 288.0)
    elif hour < 9:
        price = 170.0 + 30.0 * (hour - 6.0)
    elif hour < 11:
        price = 250.0
    elif hour < 12:
        price = 250.0 - 180.0 * (hour - 11.0)
    elif hour < 15:
        price = 70.0 + 12.0 * math.sin(2.0 * math.pi * (slot - 132) / 73.0)
    elif hour < 16:
        price = 70.0 + 280.0 * (hour - 15.0)
    elif hour < 17:
        price = 350.0 + 250.0 * (hour - 16.0)
    elif hour < 21:
        price = 780.0 + 30.0 * math.sin(2.0 * math.pi * (slot - 204) / 144.0)
    elif hour < 23:
        price = 780.0 - 140.0 * (hour - 21.0)
    else:
        price = 500.0 - 280.0 * (hour - 23.0)
    return price + 10.0 * math.sin(2.0 * math.pi * slot / 37.0)


def scenario_price(slot, index):
    shape = 14.0 * math.sin(2.0 * math.pi * (slot + 11 * index) / 288.0)
    return base_price(slot) + SCENARIO_OFFSETS[index] + shape


def actual_da_price(slot):
    return base_price(slot) + 6.0 * math.sin(2.0 * math.pi * (slot + 5) / 97.0)


def actual_rt_price(slot):
    hour = slot / 12.0
    if 11.0 <= hour < 15.0:
        # Midday PV surplus deepens the trough; around noon it crosses zero.
        spread = -85.0
        if 144 <= slot <= 156:
            spread -= 40.0
    elif 17.0 <= hour < 21.0:
        spread = 45.0
        if 228 <= slot <= 234:
            spread += 110.0
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
    # cycle budget (112号后「一充一放」为主). Scaling toward the initial SOC
    # keeps the trajectory feasible.
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
    negative_rt = sum(1 for price in rt_prices if price < 0.0)
    negative_scenarios = sum(1 for price in all_scenario_prices if price < 0.0)
    print(f"trading day       {TRADING_DAY}")
    print(f"points            {n} x {report['mtu_min']:g} min")
    print(
        f"scenario prices   {min(all_scenario_prices):.1f} .. {max(all_scenario_prices):.1f} CNY/MWh"
    )
    print(f"actual DA / RT    {min(da_prices):.1f}-{max(da_prices):.1f} / {min(rt_prices):.1f}-{max(rt_prices):.1f}")
    print(f"negative prices   {negative_scenarios} scenario points, {negative_rt} actual RT points")
    print(
        f"actual schedule   discharge {sum(actual_discharge) * report['mtu_min'] / 60.0:.1f} MWh, "
        f"charge {sum(actual_charge) * report['mtu_min'] / 60.0:.1f} MWh"
    )
    print(
        f"equivalent cycles {throughput_mwh / (2.0 * float(config['asset']['energy_mwh'])):.2f}"
    )
    stress = report["stress"]
    start_slot = int(stress["window_start_min"] // report["mtu_min"])
    end_slot = int(stress["window_end_min"] // report["mtu_min"])
    window_rt = rt_prices[start_slot:end_slot]
    print(
        f"midday window     {stress['window_start']}-{stress['window_end']} "
        f"RT mean {sum(window_rt) / len(window_rt):.1f} vs stress {stress['settlement_price']:.0f}"
    )


if __name__ == "__main__":
    main()
