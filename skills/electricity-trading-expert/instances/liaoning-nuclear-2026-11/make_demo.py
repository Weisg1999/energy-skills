#!/usr/bin/env python3
"""Generate grade-D synthetic data for the Liaoning nuclear mechanism-price pack.

The demo is deliberately shaped so that the pack exercises its own questions:

* the plant runs at constant base load, so the mechanism energy is exactly
  21h × 80% of output and the *market* energy is only ~30% of what a naive
  "all energy" view would suggest;
* the flat annual contract nearly matches the thin window-hour residual but
  leaves the 02:00–05:00 non-mechanism hours massively exposed — the monthly
  night contract only partially covers them;
* the real-time price in T+1 goes negative in hours 01:00–05:00 (window hour
  01:00–02:00 included), so the two settlement lines move in opposite
  directions: the mechanism CfD pays more while the un-hedged market residual
  loses money;
* the T+1 contract energy differs from the D-1 position (night up, evening
  down), so the contract buckets in the five-bucket bridge are not zero.

All prices stay inside the 2026 Liaoning clearing band
[−100, 1500] CNY/MWh (申报 −0.1–1.1、出清 −0.1–1.5 元/kWh，试运行参数).
Every number is deterministic — no randomness.

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
POINTS = 24
MTU_MIN = 60
DT_H = MTU_MIN / 60.0
PLAN_MW = 5700.0  # 基荷恒定（95% 负荷因子，D 级合成）
CLEAR_FLOOR = -100.0
CLEAR_CAP = 1500.0

# 5 个实时价情景（结算口径），情景 1 含深度负价（出清下限 −100 CNY/MWh）
SCENARIO_PRICES = {
    1: [40, -30, -100, -100, -100, -20, 60, 150, 230, 230, 230, 230,
        230, 230, 230, 230, 230, 280, 320, 320, 320, 250, 170, 130],
    2: [180, 180, 20, 20, 20, 150, 150, 220, 290, 290, 290, 290,
        290, 290, 290, 290, 290, 350, 420, 420, 420, 330, 240, 200],
    3: [260, 260, 80, 80, 80, 240, 240, 300, 360, 360, 360, 330,
        350, 350, 350, 380, 380, 460, 520, 520, 520, 440, 320, 280],
    4: [300, 300, 160, 160, 160, 280, 280, 360, 430, 430, 430, 430,
        430, 430, 430, 430, 430, 540, 640, 640, 640, 520, 380, 320],
    5: [340, 340, 220, 220, 220, 320, 320, 420, 500, 500, 500, 500,
        500, 500, 500, 500, 500, 660, 780, 780, 780, 620, 460, 380],
}

# T+1 实时结算价：01:00–05:00 负价（01:00 在机制窗口内、02:00–05:00 不在）
ACTUAL_RT_PRICE = [272, -15, -92, -85, -60, 10, 228, 312, 372, 348, 365, 342,
                   338, 361, 349, 392, 371, 480, 545, 560, 535, 452, 308, 291]

# 日前预出清价（仅信号，不用于结算；全部为正，与实时价形成对照）
PRECLEAR_D1 = [round(0.85 * price + 45.0 + 8.0 * math.sin(2.0 * math.pi * 3.0 * slot / POINTS), 6)
               for slot, price in enumerate(SCENARIO_PRICES[3])]
PRECLEAR_T1 = [265, 262, 118, 116, 113, 246, 243, 298, 350, 352, 349, 322,
              344, 341, 339, 371, 368, 438, 495, 498, 493, 421, 312, 276]

# D-7~D-1 滚动：市场电量预测（已扣机制电量）与调仓前持仓；目标比例 0.85 时逐日衔接
ROLLING_ROWS = [
    {"day_offset": -4, "forecast_market_energy_mwh": 40900.0, "position_before_mwh": 36000.0},
    {"day_offset": -3, "forecast_market_energy_mwh": 41180.0, "position_before_mwh": 34765.0},
    {"day_offset": -2, "forecast_market_energy_mwh": 40760.0, "position_before_mwh": 35003.0},
    {"day_offset": -1, "forecast_market_energy_mwh": 41240.0, "position_before_mwh": 34646.0},
    {"day_offset": 0, "forecast_market_energy_mwh": 41040.0, "position_before_mwh": 35054.0},
]


def slot_time(slot):
    hour = slot
    return f"{hour:02d}:00"


def actual_mw(slot):
    ripple = 2.5 * math.sin(2.0 * math.pi * 3.0 * slot / POINTS + 0.3)
    return round(PLAN_MW * 0.997 + ripple, 6)


def contract_factor(slot):
    """T+1 结算合约电量相对 D-1 持仓的调整：夜谷加仓 2%、晚峰减仓 3%。"""
    if slot in (2, 3, 4):
        return 1.02
    if slot in (18, 19, 20, 21):
        return 0.97
    return 1.0


def check_band(prices, name):
    for slot, price in enumerate(prices):
        if not CLEAR_FLOOR - 1e-9 <= price <= CLEAR_CAP + 1e-9:
            raise ValueError(f"{name}@slot{slot}={price} 超出出清区间 [−100, 1500] CNY/MWh")


def main():
    for name, prices in SCENARIO_PRICES.items():
        check_band(prices, f"price_s{name}")
    check_band(ACTUAL_RT_PRICE, "actual_rt_price")

    config = json.loads((HERE / "instance.json").read_text(encoding="utf-8"))
    book = hedge.book_position(config["book"], POINTS, MTU_MIN)
    position = book["position"]

    d1_rows = []
    for slot in range(POINTS):
        row = {
            "date": TRADING_DAY,
            "slot": slot,
            "start": slot_time(slot),
            "end": slot_time(slot + 1),
            "forecast_mw": f"{PLAN_MW:.6f}",
            "preclear_price": f"{PRECLEAR_D1[slot]:.6f}",
        }
        for name in sorted(SCENARIO_PRICES):
            row[f"price_s{name}"] = f"{SCENARIO_PRICES[name][slot]:.6f}"
        d1_rows.append(row)
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
                "actual_rt_price": f"{ACTUAL_RT_PRICE[slot]:.6f}",
                "preclear_price": f"{PRECLEAR_T1[slot]:.6f}",
            }
        )
    t1_path = HERE / "data" / "t1_demo.csv"
    with t1_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(t1_rows[0]))
        writer.writeheader()
        writer.writerows(t1_rows)

    rolling_path = HERE / "data" / "rolling_demo.csv"
    with rolling_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROLLING_ROWS[0]))
        writer.writeheader()
        writer.writerows(ROLLING_ROWS)

    # 口径 sanity：机制电量认定（21h × 80%）与市场电量
    excluded = [tuple(span) for span in config["asset"]["excluded_window_hours"]]
    window_slots = [slot for slot in range(POINTS)
                    if not any(slot >= a and slot + 1 <= b for a, b in excluded)]
    share = config["asset"]["mechanism_energy_share"]
    output_energy = PLAN_MW * POINTS * DT_H
    mechanism_energy = PLAN_MW * DT_H * share * len(window_slots)
    market_energy = output_energy - mechanism_energy
    actual_energy = sum(actual_mw(slot) for slot in range(POINTS)) * DT_H
    actual_contract = sum(float(row["actual_contract_mwh"]) for row in t1_rows)
    neg_s1 = [slot for slot, price in enumerate(SCENARIO_PRICES[1]) if price < 0]
    neg_t1 = [slot for slot, price in enumerate(ACTUAL_RT_PRICE) if price < 0]
    print(f"d1      {d1_path}  output={output_energy:,.1f} MWh  scenarios={len(SCENARIO_PRICES)}")
    print(f"t1      {t1_path}  actual={actual_energy:,.1f} MWh  contract={actual_contract:,.1f} MWh")
    print(f"rolling {rolling_path}  days={len(ROLLING_ROWS)} (target 0.85 chains exactly)")
    print(
        f"mechanism  window_hours={len(window_slots)} (02:00-05:00 excluded)  "
        f"mechanism={mechanism_energy:,.1f} MWh ({mechanism_energy / output_energy:.2%})  "
        f"market={market_energy:,.1f} MWh ({market_energy / output_energy:.2%})"
    )
    print(
        f"book  daily={book['energy_mwh']:,.1f} MWh  "
        f"hedge_ratio_on_market={book['energy_mwh'] / market_energy:.4f}  "
        f"negative_slots  s1={neg_s1}  t1={neg_t1}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
