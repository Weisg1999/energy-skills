#!/usr/bin/env python3
"""Generate the synthetic monthly profile for the Sichuan runoff-hydro pack.

Columns: season tag (丰/平/枯), actual generation, contract weight (sums to 1,
split across seasons by the 2025 regular direct-purchase ratio 45.23/16.73/38.04
within-season by resource shape) and the synthetic spot price. All values are
grade D synthetic data and do not correspond to any real station or trade.

Price shape follows the Sichuan seasonality documented in the provincial
knowledge module: high output and low prices in the 丰水期 (Jun-Oct), low
output and high prices in the 枯水期 (Jan-Apr, Dec).
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "profile_demo.csv"

YEAR = 2027
PLANNED_MWH = 1_440_000.0  # 300 MW x 4,800 h, grade D synthetic

# Monthly share of annual generation (径流式：丰水期 6–10 月来水集中，C 口径的 D 级形态)
GENERATION_SHARE = {
    1: 0.045, 2: 0.040, 3: 0.050, 4: 0.070, 5: 0.085,
    6: 0.115, 7: 0.140, 8: 0.145, 9: 0.120, 10: 0.095,
    11: 0.055, 12: 0.040,
}

# 2025 常规直购丰/平/枯电量比（B 级事实，四川省级知识模块 §5）作为合同分解锚
SEASON_SPLIT = {"丰": 0.4523, "平": 0.1673, "枯": 0.3804}
SEASON_MONTHS = {"丰": [6, 7, 8, 9, 10], "平": [5, 11], "枯": [1, 2, 3, 4, 12]}

# Synthetic monthly spot price (D 级)：丰低枯高，
# 锚点为丰水期实时均价约 129 元/MWh、枯水期约 314 元/MWh（C 口径），枯水期个别月份高于枯季合同价
SPOT_PRICE = {
    1: 0.38, 2: 0.33, 3: 0.31, 4: 0.28, 5: 0.20,
    6: 0.14, 7: 0.12, 8: 0.12, 9: 0.13, 10: 0.15,
    11: 0.24, 12: 0.39,
}


def season_of(month: int) -> str:
    for season, months in SEASON_MONTHS.items():
        if month in months:
            return season
    raise ValueError(f"month {month} not covered by season map")


def main():
    if abs(sum(GENERATION_SHARE.values()) - 1.0) > 1e-9:
        raise ValueError("monthly generation shares must sum to 1")
    if abs(sum(SEASON_SPLIT.values()) - 1.0) > 1e-9:
        raise ValueError("season split must sum to 1")

    # 合同权重：季内按本站出力形态分摊，季间按常规直购分期比例
    season_gen_share = {s: sum(GENERATION_SHARE[m] for m in months) for s, months in SEASON_MONTHS.items()}
    contract_weight = {}
    for season, months in SEASON_MONTHS.items():
        for month in months:
            contract_weight[month] = round(
                GENERATION_SHARE[month] / season_gen_share[season] * SEASON_SPLIT[season], 6
            )
    if abs(sum(contract_weight.values()) - 1.0) > 1e-5:
        raise ValueError(f"contract weights sum to {sum(contract_weight.values())}")
    for season, months in SEASON_MONTHS.items():
        season_weight = sum(contract_weight[m] for m in months)
        if abs(season_weight - SEASON_SPLIT[season]) > 1e-4:
            raise ValueError(f"{season} contract weight {season_weight} != {SEASON_SPLIT[season]}")

    rows = []
    for month in range(1, 13):
        rows.append(
            {
                "month": f"{YEAR}-{month:02d}",
                "season": season_of(month),
                "generation_mwh": f"{PLANNED_MWH * GENERATION_SHARE[month]:.0f}",
                "contract_weight": f"{contract_weight[month]:.6f}",
                "spot_price_cny_per_kwh": f"{SPOT_PRICE[month]:.4f}",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "month",
                "season",
                "generation_mwh",
                "contract_weight",
                "spot_price_cny_per_kwh",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows, {PLANNED_MWH:,.0f} MWh)")
    print("season generation share:", {s: f"{v:.2%}" for s, v in season_gen_share.items()})
    print("season contract weight:", {s: f"{sum(contract_weight[m] for m in ms):.4f}" for s, ms in SEASON_MONTHS.items()})


if __name__ == "__main__":
    main()
