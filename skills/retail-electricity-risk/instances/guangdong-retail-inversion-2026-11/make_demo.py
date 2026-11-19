#!/usr/bin/env python3
"""Generate grade-D synthetic monthly replay data for the Guangdong retail-inversion instance.

Window: 2025-12 (签约基准月) .. 2026-11 (数据截止月)，12 个月。
Contents: 三个客户群的月度预测/实际电量（季节性取自引擎层 curves.MONTH_FACTORS），
以及月度现货均价路径：已实现路径（含上行尖峰形态）+ 四条事前情景（下行/中性/上行/尖峰上行）。

All data are grade-D synthetic and correspond to no real retailer, customer,
contract or market outcome. Spot levels are only calibrated in magnitude to the
Guangdong 2026 observed day-ahead range 425-696 CNY/MWh (grade B); the monthly
path itself is fictional. Shapes are deterministic, so the demo is reproducible.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import curves  # noqa: E402  引擎层季节性因子（D 级合成形状，非省级事实）

DATA = HERE / "data"
FLOOR, CAP = -50.0, 1800.0

# 复盘窗口：2025-12（签约基准月）至 2026-11（数据截止 2026-11-12 前）。
MONTHS = [
    "2025-12",
    "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
    "2026-07", "2026-08", "2026-09", "2026-10", "2026-11",
]

ANNUAL_ENERGY_MWH = 1_200_000.0
SEGMENTS = (
    ("industrial", "大工业（连续生产）", 0.45, 0.5),
    ("commercial", "一般工商业", 0.35, 1.0),
    ("retail", "中小零售用户", 0.20, 0.8),
)
# amplitude：客户群月度曲线相对组合平均的峰谷幅度（0=平坦，1=完全跟随季节因子）。

# 实际/预测偏差系数（D 级）：上半年小幅波动、2 月春节回落、
# 7-9 月高温季负荷超预测（尖峰月 +3.0% ~ +4.2%，超过 3% 免考带 → 偏差考核与现货补货同时发生）。
ACTUAL_FACTORS = {
    "2025-12": 1.004,
    "2026-01": 1.012,
    "2026-02": 0.965,
    "2026-03": 0.990,
    "2026-04": 1.015,
    "2026-05": 1.020,
    "2026-06": 1.018,
    "2026-07": 1.030,
    "2026-08": 1.042,
    "2026-09": 1.035,
    "2026-10": 1.008,
    "2026-11": 0.995,
}

# 已实现现货月均价路径（D 级合成，量级参考广东 2026 年 1-9 月日前 425-696 厘/kWh，B）：
# 上半年温和、4 月起抬升（呼应 2026-04-11 实时 0.978 元/kWh 尖峰，C）、8-9 月尖峰。
SPOT_BASE = {
    "2025-12": 388.0,
    "2026-01": 402.0,
    "2026-02": 375.0,
    "2026-03": 392.0,
    "2026-04": 455.0,
    "2026-05": 470.0,
    "2026-06": 505.0,
    "2026-07": 545.0,
    "2026-08": 640.0,
    "2026-09": 600.0,
    "2026-10": 520.0,
    "2026-11": 490.0,
}

# 四条事前情景（D 级）：s1 是当年压力测试只测的下行方向（案例 7 的核心错误），
# s2 是签约期中性假设，s3/s4 是未测的上行方向（s4 含限价区间内的尖峰形态）。
SPOT_S1_FACTOR = 0.78
SPOT_S2_PATH = {
    "2025-12": 398.0, "2026-01": 400.0, "2026-02": 396.0, "2026-03": 399.0,
    "2026-04": 402.0, "2026-05": 404.0, "2026-06": 406.0, "2026-07": 408.0,
    "2026-08": 410.0, "2026-09": 407.0, "2026-10": 403.0, "2026-11": 400.0,
}
SPOT_S3_FACTOR = 1.22
SPOT_S4_FACTORS = {
    "2025-12": 1.05, "2026-01": 1.05, "2026-02": 1.00, "2026-03": 1.10,
    "2026-04": 1.30, "2026-05": 1.45, "2026-06": 1.70, "2026-07": 1.90,
    "2026-08": 2.10, "2026-09": 2.00, "2026-10": 1.70, "2026-11": 1.50,
}


def _rolled_month_factors():
    """Map each window month to the engine seasonality factor (Dec..Nov order)."""
    factors = {}
    for month in MONTHS:
        year, m = int(month[:4]), int(month[5:7])
        index = m - 1
        factors[month] = curves.MONTH_FACTORS[index] * curves.MONTH_DAYS[index]
    return factors


def _segment_monthly_energy(key, share, amplitude, month_weight):
    """Monthly forecast energy per segment: seasonality blended with the segment amplitude."""
    raw = []
    for month in MONTHS:
        factor = month_weight[month]
        total_weight = sum(month_weight.values())
        base = share * ANNUAL_ENERGY_MWH * factor / total_weight
        tilted = share * ANNUAL_ENERGY_MWH / len(MONTHS)
        value = amplitude * base + (1.0 - amplitude) * tilted
        raw.append((month, value))
    # 归一化：保证该客户群 12 个月合计恰好等于 年电量×份额。
    total = sum(value for _, value in raw)
    target = share * ANNUAL_ENERGY_MWH
    return {month: value * target / total for month, value in raw}


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    month_weight = _rolled_month_factors()
    forecast = {}
    actual = {}
    for key, _name, share, amplitude in SEGMENTS:
        forecast[key] = _segment_monthly_energy(key, share, amplitude, month_weight)
        actual[key] = {m: forecast[key][m] * ACTUAL_FACTORS[m] for m in MONTHS}

    spot_s1 = {m: SPOT_BASE[m] * SPOT_S1_FACTOR for m in MONTHS}
    spot_s3 = {m: SPOT_BASE[m] * SPOT_S3_FACTOR for m in MONTHS}
    spot_s4 = {m: SPOT_BASE[m] * SPOT_S4_FACTORS[m] for m in MONTHS}

    scenarios = {
        "spot_base_cny_per_mwh": SPOT_BASE,
        "spot_s1_cny_per_mwh": spot_s1,
        "spot_s2_cny_per_mwh": SPOT_S2_PATH,
        "spot_s3_cny_per_mwh": spot_s3,
        "spot_s4_cny_per_mwh": spot_s4,
    }
    for name, path in scenarios.items():
        low, high = min(path.values()), max(path.values())
        if low < FLOOR - 1e-9 or high > CAP + 1e-9:
            raise AssertionError(f"{name} 越界：{low:.2f}–{high:.2f}（{FLOOR}–{CAP}）")

    header = ["month"]
    for key, _name, _share, _amp in SEGMENTS:
        header += [f"{key}_forecast_mwh", f"{key}_actual_mwh"]
    header += list(scenarios.keys())

    rows = []
    for month in MONTHS:
        row = [month]
        for key, _name, _share, _amp in SEGMENTS:
            row += [f"{forecast[key][month]:.3f}", f"{actual[key][month]:.3f}"]
        row += [f"{path[month]:.2f}" for path in scenarios.values()]
        rows.append(row)

    path_out = DATA / "monthly_demo.csv"
    with path_out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)

    total_forecast = sum(sum(values.values()) for values in forecast.values())
    total_actual = sum(sum(values.values()) for values in actual.values())
    print(f"window={'2025-12 .. 2026-11'} months={len(MONTHS)}")
    print(f"forecast energy={total_forecast:,.1f} MWh actual energy={total_actual:,.1f} MWh")
    for key, name, share, _amp in SEGMENTS:
        seg_f = sum(forecast[key].values())
        seg_a = sum(actual[key].values())
        print(f"  {name}: share={share:.0%} forecast={seg_f:,.1f} actual={seg_a:,.1f} MWh")
    for name, path in scenarios.items():
        avg = sum(path.values()) / len(path)
        print(f"  {name}: avg={avg:,.2f} min={min(path.values()):,.2f} max={max(path.values()):,.2f} CNY/MWh")
    out_of_band = [
        m for m in MONTHS
        if abs(ACTUAL_FACTORS[m] - 1.0) > 0.03 + 1e-12
    ]
    print(f"months beyond 3% tolerance band: {', '.join(out_of_band) if out_of_band else 'none'}")
    print(f"wrote {path_out}")


if __name__ == "__main__":
    main()
