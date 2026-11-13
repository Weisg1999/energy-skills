#!/usr/bin/env python3
"""Generate the synthetic Mengxi wind spot demo (D grade).

One trading day, 96 points. Wind and price scenarios are paired by index:
s1 is high wind / low price (including negative midday), s5 is low wind /
high price. The T+1 file adds a partial curtailment window at negative
midday prices so the settlement bridge has a real curtailment bucket.

The output is synthetic and must not be used as a market forecast.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATE = "2026-11-18"

# Hourly capacity factor of a windy day: strong overnight, dip at midday.
WIND_CF = [
    0.72, 0.76, 0.80, 0.82, 0.80, 0.76,
    0.70, 0.62, 0.55, 0.50, 0.46, 0.42,
    0.40, 0.42, 0.48, 0.55, 0.62, 0.68,
    0.72, 0.75, 0.78, 0.80, 0.78, 0.74,
]
# Day-ahead reference price, CNY/MWh. Midday is depressed by solar.
DA_PRICE = [
    150.0, 140.0, 130.0, 120.0, 115.0, 120.0,
    150.0, 190.0, 230.0, 220.0, 150.0, 90.0,
    60.0, 55.0, 70.0, 120.0, 210.0, 320.0,
    380.0, 400.0, 350.0, 270.0, 210.0, 180.0,
]
# Real-time actual price, CNY/MWh. Negative midday window.
RT_PRICE = [
    130.0, 120.0, 110.0, 100.0, 95.0, 100.0,
    130.0, 170.0, 210.0, 190.0, 60.0, -20.0,
    -35.0, -40.0, -10.0, 80.0, 220.0, 360.0,
    430.0, 450.0, 390.0, 290.0, 220.0, 180.0,
]

WIND_MULT = [1.18, 1.09, 1.00, 0.91, 0.82]


def _slot_noise(slot: int, phase: float) -> float:
    return 1.0 + 0.03 * math.sin(slot * 0.37 + phase)


def _scenario_price(base: float, hour: int, scenario: int) -> float:
    if scenario == 0:
        return base - 110.0 if 10 <= hour < 15 else base * 0.80
    if scenario == 1:
        return base - 70.0 if 10 <= hour < 15 else base * 0.90
    if scenario == 2:
        return base
    if scenario == 3:
        return base * 1.10 + 10.0
    return base * 1.20 + 20.0


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    d1_rows = []
    t1_rows = []
    for slot in range(96):
        hour = slot // 4
        minute = (slot % 4) * 15
        start = f"{hour:02d}:{minute:02d}"
        end_minute = minute + 15
        end_hour = hour + end_minute // 60
        end = f"{end_hour:02d}:{end_minute % 60:02d}"
        base_mw = 200.0 * WIND_CF[hour] * _slot_noise(slot, 0.4)
        forecast_mw = round(base_mw, 2)
        da_price = round(DA_PRICE[hour] + 4.0 * math.sin(slot * 0.21), 2)
        wind_values = [round(base_mw * multiplier, 2) for multiplier in WIND_MULT]
        price_values = [
            round(_scenario_price(da_price, hour, scenario), 2)
            for scenario in range(5)
        ]
        d1_rows.append(
            {
                "date": DATE,
                "slot": slot,
                "start": start,
                "end": end,
                "forecast_mw": forecast_mw,
                "wind_s1": wind_values[0],
                "wind_s2": wind_values[1],
                "wind_s3": wind_values[2],
                "wind_s4": wind_values[3],
                "wind_s5": wind_values[4],
                "price_s1": price_values[0],
                "price_s2": price_values[1],
                "price_s3": price_values[2],
                "price_s4": price_values[3],
                "price_s5": price_values[4],
                "da_price": da_price,
            }
        )

        actual_da = round(da_price + 5.0 * math.sin(slot * 0.17 + 0.8), 2)
        actual_rt = round(RT_PRICE[hour] + 3.0 * math.sin(slot * 0.29 + 0.3), 2)
        available = round(base_mw * 1.03 * _slot_noise(slot, 1.1), 2)
        if 11 <= hour < 15:
            curtail = round(available * 0.70, 2)
        else:
            curtail = 0.0
        output = round(available - curtail, 2)
        t1_rows.append(
            {
                "date": DATE,
                "slot": slot,
                "actual_da_price": actual_da,
                "actual_rt_price": actual_rt,
                "actual_available_mw": available,
                "actual_output_mw": output,
                "actual_curtail_mw": curtail,
            }
        )

    assert len(d1_rows) == 96 and len(t1_rows) == 96
    assert min(row["price_s1"] for row in d1_rows) >= -60.0
    assert min(row["actual_rt_price"] for row in t1_rows) < 0.0
    assert any(row["actual_curtail_mw"] > 0 for row in t1_rows)
    for row in t1_rows:
        assert abs(
            row["actual_output_mw"] + row["actual_curtail_mw"] - row["actual_available_mw"]
        ) < 1e-6

    d1_fields = list(d1_rows[0].keys())
    t1_fields = list(t1_rows[0].keys())
    with (DATA / "d1_demo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=d1_fields)
        writer.writeheader()
        writer.writerows(d1_rows)
    with (DATA / "t1_demo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=t1_fields)
        writer.writeheader()
        writer.writerows(t1_rows)

    forecast_energy = sum(row["forecast_mw"] for row in d1_rows) * 0.25
    actual_energy = sum(row["actual_output_mw"] for row in t1_rows) * 0.25
    curtail_energy = sum(row["actual_curtail_mw"] for row in t1_rows) * 0.25
    negative_slots = sum(1 for row in t1_rows if row["actual_rt_price"] < 0)
    print(
        f"已写入 {DATA / 'd1_demo.csv'} 与 {DATA / 't1_demo.csv'}："
        f"96 点，预测 {forecast_energy:,.0f} MWh，实际 {actual_energy:,.0f} MWh，"
        f"弃风 {curtail_energy:,.0f} MWh，负价 {negative_slots} 点"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
