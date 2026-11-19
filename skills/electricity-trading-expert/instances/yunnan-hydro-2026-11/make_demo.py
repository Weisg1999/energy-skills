#!/usr/bin/env python3
"""Generate the synthetic inputs for the Yunnan cascade hydro pack.

Two files, all values grade D synthetic:

* ``data/profile_demo.csv`` — one hydro year, monthly: generation, the flat
  annual-average contract weight (1/12), the wet/dry seasonal contract
  weight, the monthly intra-provincial contract price and the green
  certificate share of generation.
* ``data/price_shapes_demo.csv`` — two Southern-regional 15-minute price
  shapes (wet / dry season), 96 slots per day, plus the within-day
  generation distribution (sums to 1 per season) used to weight the
  time-average price into a generation-weighted capture price.

Wet-season prices are deliberately pressed down by flood-season hydropower
(capture below time average); dry-season hydro follows the morning and
evening peaks (capture above time average). The arrays are static and the
script is deterministic.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE_OUT = HERE / "data" / "profile_demo.csv"
SHAPES_OUT = HERE / "data" / "price_shapes_demo.csv"

# ---------------------------------------------------------------------------
# 梯级水电年电量（D 级合成）：600 MW × 4,000 h = 2,400,000 MWh
# 汛期（6–10 月）约占 65%，枯期（11–5 月）约占 35%。
# ---------------------------------------------------------------------------
MONTHS = [f"2027-{m:02d}" for m in range(1, 13)]
SEASONS = ["dry", "dry", "dry", "dry", "dry", "wet", "wet", "wet", "wet", "wet", "dry", "dry"]
GENERATION_MWH = [
    108000,   # 1 月
    96000,    # 2 月
    100800,   # 3 月
    120000,   # 4 月
    151200,   # 5 月
    288000,   # 6 月
    372000,   # 7 月
    360000,   # 8 月
    312000,   # 9 月
    228000,   # 10 月
    144000,   # 11 月
    120000,   # 12 月
]
FLAT_WEIGHT = [round(1.0 / 12.0, 6)] * 12  # 年度平推分解（合计 0.999996）
SEASONAL_WEIGHT = [
    0.050,  # 1 月
    0.055,  # 2 月（枯期小月合同偏多 → 偏差）
    0.057,  # 3 月
    0.070,  # 4 月（春旱合同偏多 → 偏差）
    0.069,  # 5 月
    0.104,  # 6 月
    0.136,  # 7 月
    0.134,  # 8 月
    0.114,  # 9 月
    0.083,  # 10 月
    0.058,  # 11 月
    0.070,  # 12 月（年末合同偏多 → 偏差）
]
CONTRACT_PRICE = [
    0.380,  # 1 月（枯期高价）
    0.385,  # 2 月
    0.380,  # 3 月
    0.375,  # 4 月
    0.360,  # 5 月
    0.200,  # 6 月（汛期压价）
    0.185,  # 7 月
    0.180,  # 8 月
    0.190,  # 9 月
    0.210,  # 10 月
    0.360,  # 11 月
    0.370,  # 12 月
]
GREEN_RATIO = [0.25] * 5 + [0.35] * 5 + [0.25] * 2

# ---------------------------------------------------------------------------
# 南方区域 15 分钟价格形态（D 级合成，CNY/MWh）：24 小时模式 × 4 个 15 分钟槽。
# 汛期被大发水电压价（午间低谷），枯期紧平衡、早晚双峰。
# ---------------------------------------------------------------------------
WET_HOURLY_PRICE = (
    [140] * 6          # 00–06 夜间低谷
    + [150, 160]       # 06–08 晨间爬坡
    + [180, 170, 160]  # 08–11 午前
    + [115, 105, 110]  # 11–14 午间低谷（光伏 + 汛期大发）
    + [135, 140, 150]  # 14–17 午后
    + [200, 235, 245, 215]  # 17–21 弱晚峰
    + [200, 170, 150]  # 21–24 回落
)
WET_HOURLY_SHARE = (
    [4.9] * 6          # 汛期水电全天大发、略压午间与晚峰
    + [3.9, 4.0]
    + [4.4, 4.4, 4.3]
    + [4.4, 4.6, 4.4]
    + [4.4, 4.5, 4.4]
    + [3.8, 3.9, 4.0, 3.7]
    + [2.7, 2.5, 2.3]
)
DRY_HOURLY_PRICE = (
    [260] * 6          # 00–06 夜间低谷
    + [320, 380]       # 06–08 晨间爬坡
    + [470, 520, 540]  # 08–11 晨峰
    + [420, 400, 410]  # 11–14 午间
    + [430, 450, 470]  # 14–17 午后
    + [520, 560, 580, 550]  # 17–21 晚峰（外送通道紧张）
    + [470, 400, 320]  # 21–24 回落
)
DRY_HOURLY_SHARE = (
    [1.336, 1.336, 1.332, 1.332, 1.332, 1.332]  # 枯期夜间蓄水少发（份额取 0.004 的倍数，保证槽份额 6 位小数精确）
    + [4.0, 6.0]
    + [6.0, 6.0, 6.0]
    + [5.0, 5.0, 5.0]
    + [5.4, 5.3, 5.3]
    + [6.0, 6.0, 6.0, 6.0]
    + [3.0, 3.0, 3.0]
)


def _expand_hourly(values):
    """把 24 小时模式展开成 96 个 15 分钟槽（每槽 = 小时值 / 4 份额）。"""
    if len(values) != 24:
        raise ValueError(f"hourly pattern must have 24 rows, got {len(values)}")
    slots = []
    for hour, value in enumerate(values):
        for quarter in range(4):
            slots.append((hour * 4 + quarter, value))
    return slots


def main():
    if len(MONTHS) != 12 or len(set(MONTHS)) != 12:
        raise ValueError("months must be 12 unique YYYY-MM rows")
    if abs(sum(GENERATION_MWH) - 2400000) > 1e-9:
        raise ValueError(f"monthly generation must sum to 2,400,000 MWh, got {sum(GENERATION_MWH)}")
    if abs(sum(FLAT_WEIGHT) - 1.0) > 1e-3:
        raise ValueError(f"flat weights sum to {sum(FLAT_WEIGHT)}")
    if abs(sum(SEASONAL_WEIGHT) - 1.0) > 1e-9:
        raise ValueError(f"seasonal weights sum to {sum(SEASONAL_WEIGHT)}")
    if not (len(SEASONS) == len(GENERATION_MWH) == len(FLAT_WEIGHT) == len(SEASONAL_WEIGHT) == len(CONTRACT_PRICE) == len(GREEN_RATIO) == 12):
        raise ValueError("all monthly columns must have 12 rows")
    if abs(sum(WET_HOURLY_SHARE) - 100.0) > 1e-9:
        raise ValueError(f"wet hourly shares sum to {sum(WET_HOURLY_SHARE)}")
    if abs(sum(DRY_HOURLY_SHARE) - 100.0) > 1e-9:
        raise ValueError(f"dry hourly shares sum to {sum(DRY_HOURLY_SHARE)}")
    if len(WET_HOURLY_PRICE) != 24 or len(DRY_HOURLY_PRICE) != 24:
        raise ValueError("hourly price patterns must have 24 rows")

    rows = []
    for index in range(12):
        rows.append(
            {
                "month": MONTHS[index],
                "season": SEASONS[index],
                "generation_mwh": f"{GENERATION_MWH[index]:.0f}",
                "contract_weight": f"{FLAT_WEIGHT[index]:.6f}",
                "seasonal_weight": f"{SEASONAL_WEIGHT[index]:.6f}",
                "contract_price_cny_per_kwh": f"{CONTRACT_PRICE[index]:.4f}",
                "green_ratio": f"{GREEN_RATIO[index]:.4f}",
            }
        )
    PROFILE_OUT.parent.mkdir(parents=True, exist_ok=True)
    with PROFILE_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "month",
                "season",
                "generation_mwh",
                "contract_weight",
                "seasonal_weight",
                "contract_price_cny_per_kwh",
                "green_ratio",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    shape_rows = []
    for season, prices, shares in (
        ("wet", WET_HOURLY_PRICE, WET_HOURLY_SHARE),
        ("dry", DRY_HOURLY_PRICE, DRY_HOURLY_SHARE),
    ):
        for slot, price in _expand_hourly(prices):
            # 小时份额为百分数：/100 化为比例，再 /4 摊到 15 分钟槽（各季合计 1）。
            share = shares[slot // 4] / 100.0 / 4.0
            shape_rows.append(
                {
                    "season": season,
                    "slot": f"{slot}",
                    "price_cny_per_mwh": f"{price:.2f}",
                    "generation_share": f"{share:.6f}",
                }
            )
    with SHAPES_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["season", "slot", "price_cny_per_mwh", "generation_share"],
        )
        writer.writeheader()
        writer.writerows(shape_rows)

    wet_capture = sum(p * s for p, s in zip(WET_HOURLY_PRICE, WET_HOURLY_SHARE)) / 100.0
    dry_capture = sum(p * s for p, s in zip(DRY_HOURLY_PRICE, DRY_HOURLY_SHARE)) / 100.0
    wet_avg = sum(WET_HOURLY_PRICE) / 24.0
    dry_avg = sum(DRY_HOURLY_PRICE) / 24.0
    print(f"wrote {PROFILE_OUT} ({len(rows)} rows, {sum(GENERATION_MWH):,.0f} MWh)")
    print(f"wrote {SHAPES_OUT} ({len(shape_rows)} rows, 96 slots x wet/dry)")
    print(
        f"synthetic check: wet avg {wet_avg:.2f} vs capture {wet_capture:.2f} CNY/MWh "
        f"({wet_capture - wet_avg:+.2f}); dry avg {dry_avg:.2f} vs capture {dry_capture:.2f} "
        f"({dry_capture - dry_avg:+.2f})"
    )


if __name__ == "__main__":
    main()
