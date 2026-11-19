#!/usr/bin/env python3
"""Generate the synthetic Mengxi wind+PV+storage joint demo (D grade).

One trading day, 288 points (5-minute market time unit, matching the
Mengxi real-time 5-minute rolling clearing). Wind, PV and price scenarios
are paired by index: s1 is high renewable output / low midday price
(negative price window), s5 is low output / high price. The T+1 file adds
actual prices and actual wind/PV availability; the storage plan from the
D-1 file is executed as-is (grade-D assumption stated in the data contract).

The output is synthetic and must not be used as a market forecast.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATE = "2026-11-18"
N = 288
MTU = 5

# Hourly wind capacity factor: strong overnight/morning, midday dip.
WIND_CF = [
    0.52, 0.55, 0.58, 0.60, 0.62, 0.60,
    0.55, 0.50, 0.44, 0.38, 0.33, 0.30,
    0.30, 0.31, 0.33, 0.36, 0.40, 0.44,
    0.48, 0.52, 0.55, 0.57, 0.56, 0.54,
]
# Hourly PV capacity factor: bell between 07:00 and 18:00.
PV_CF = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.02, 0.15, 0.35, 0.60, 0.80, 0.90,
    0.92, 0.88, 0.78, 0.62, 0.42, 0.18,
    0.02, 0.0, 0.0, 0.0, 0.0, 0.0,
]
# Hourly day-ahead reference price anchors (CNY/MWh): night valley (charge),
# morning peak (discharge #1), midday deep negative valley (charge + discharge
# ban), pre-peak shoulder, evening peak (discharge #2).
BASE_DA = [
    210, 205, 202, 200, 204, 212,
    340, 350, 300, 190, 20, -25,
    -25, -25, -10, 60, 260, 380,
    470, 520, 500, 385, 320, 272, 210,
]
# Hourly real-time actual price anchors: deeper midday negative window.
BASE_RT = [
    205, 200, 197, 195, 199, 207,
    345, 355, 305, 185, -12, -30,
    -30, -30, -12, 55, 250, 390,
    480, 540, 505, 388, 325, 275, 205,
]

WIND_MULT = [1.18, 1.09, 1.00, 0.91, 0.82]
PV_MULT = [1.12, 1.06, 1.00, 0.94, 0.88]


def _anchor_curve(anchors, slot):
    """Linear interpolation between hourly anchors plus a small 5-min ripple."""
    hour = slot // 12
    frac = (slot % 12) / 12.0
    value = anchors[hour] * (1.0 - frac) + anchors[hour + 1] * frac
    return value + 8.0 * math.sin(2.0 * math.pi * slot / 37.0)


def _scenario_price(base, hour, index):
    if index == 0:
        return base - 30.0 if 10 <= hour < 15 else base * 0.85
    if index == 1:
        return base - 12.0 if 10 <= hour < 15 else base * 0.92
    if index == 2:
        return base
    if index == 3:
        return base * 1.10 + 10.0
    return base * 1.18 + 25.0


def _slot_noise(slot, phase):
    return 1.0 + 0.03 * math.sin(slot * 0.19 + phase)


def slot_time(slot):
    minutes = slot * MTU
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def main() -> int:
    config = json.loads((HERE / "instance.json").read_text(encoding="utf-8"))
    floor = float(config["rules"]["spot"]["model_floor_cny_per_mwh"])
    cap = float(config["rules"]["spot"]["model_cap_cny_per_mwh"])
    wind_cap = float(config["asset"]["wind"]["capacity_mw"])
    pv_cap = float(config["asset"]["pv"]["capacity_mw"])

    def clip(price):
        return min(cap, max(floor, price))

    DATA.mkdir(parents=True, exist_ok=True)
    d1_rows = []
    t1_rows = []
    for slot in range(N):
        hour = slot // 12
        row = {
            "date": DATE,
            "slot": slot,
            "start": slot_time(slot),
            "end": slot_time(slot + 1) if slot < N - 1 else "24:00",
        }
        base_wind = wind_cap * WIND_CF[hour] * _slot_noise(slot, 0.4)
        base_pv = pv_cap * PV_CF[hour] * _slot_noise(slot, 1.7)
        row["forecast_wind_mw"] = round(base_wind, 2)
        row["forecast_pv_mw"] = round(base_pv, 2)
        for index in range(5):
            row[f"wind_s{index + 1}"] = round(
                min(wind_cap, max(0.0, base_wind * WIND_MULT[index])), 2
            )
            row[f"pv_s{index + 1}"] = round(
                min(pv_cap, max(0.0, base_pv * PV_MULT[index])), 2
            )
        base_price = _anchor_curve(BASE_DA, slot)
        da_price = round(clip(base_price + 5.0 * math.sin(2.0 * math.pi * (slot + 7) / 91.0)), 2)
        row["da_price"] = da_price
        for index in range(5):
            row[f"price_s{index + 1}"] = round(clip(_scenario_price(base_price, hour, index)), 2)
        d1_rows.append(row)

        actual_da = round(clip(da_price + 4.0 * math.sin(2.0 * math.pi * (slot + 3) / 67.0)), 2)
        actual_rt = round(clip(_anchor_curve(BASE_RT, slot) + 3.0 * math.sin(2.0 * math.pi * (slot + 11) / 53.0)), 2)
        actual_wind = round(
            min(wind_cap, max(0.0, base_wind * 1.03 * _slot_noise(slot, 1.1))), 2
        )
        actual_pv = round(
            min(pv_cap, max(0.0, base_pv * 1.02 * _slot_noise(slot, 2.3))), 2
        )
        t1_rows.append(
            {
                "date": DATE,
                "slot": slot,
                "actual_da_price": actual_da,
                "actual_rt_price": actual_rt,
                "actual_wind_mw": actual_wind,
                "actual_pv_mw": actual_pv,
            }
        )

    assert len(d1_rows) == N and len(t1_rows) == N
    scenario_prices = [
        float(row[f"price_s{index + 1}"]) for row in d1_rows for index in range(5)
    ]
    s1_renewable = [row["wind_s1"] + row["pv_s1"] for row in d1_rows]
    negative_rt_slots = sum(1 for row in t1_rows if row["actual_rt_price"] < 0)
    assert min(scenario_prices) >= floor - 1e-6
    assert max(scenario_prices) <= cap + 1e-6
    assert negative_rt_slots >= 40, "T+1 must contain a real negative-price window"
    assert max(s1_renewable) > float(config["asset"]["grid_connection"]["export_limit_mw"]), (
        "s1 must exceed the shared export limit so curtailment absorption is real"
    )
    assert max(row["actual_rt_price"] for row in t1_rows) > 500.0

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

    wind_energy = sum(row["forecast_wind_mw"] for row in d1_rows) * MTU / 60.0
    pv_energy = sum(row["forecast_pv_mw"] for row in d1_rows) * MTU / 60.0
    s1_renewable_energy = sum(s1_renewable) * MTU / 60.0
    print(
        f"已写入 {DATA / 'd1_demo.csv'} 与 {DATA / 't1_demo.csv'}："
        f"{N} 点（{MTU} 分钟），预测风电 {wind_energy:,.0f} MWh + 光伏 {pv_energy:,.0f} MWh"
    )
    print(
        f"情景价区间 {min(scenario_prices):.1f} 至 {max(scenario_prices):.1f} 元/MWh；"
        f"s1 联合可用电量 {s1_renewable_energy:,.0f} MWh（超过出口限额的最大出力 "
        f"{max(s1_renewable):.1f} MW）；T+1 负价 {negative_rt_slots} 点"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
