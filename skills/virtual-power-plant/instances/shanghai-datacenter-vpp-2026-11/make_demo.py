#!/usr/bin/env python3
"""Generate grade-D synthetic history, invitation and T+1 data for the
Shanghai independent-datacenter VPP pack.

The data correspond to no real datacenter, aggregator, contract or metered
load. Shapes are deterministic, so the demo is reproducible.

建模口径（全部 D 级合成）：
* IT 负载相对平坦、白天略高（在线任务不可断）；资源 ``dc_it_batch_mw`` 只计
  可迁移批处理部分，任务排程决定白天高、夜间低；
* 制冷负荷跟随午后热负荷爬坡，14-15 时到峰；
* UPS 备电电池基线为空载 0，事件时段前 0.5 h 放电（备电窗口约束），
  后 0.5 h 归零——演示"功率能力 ≠ 1 h 全程放电"；
* 附属园区空调为办公形态。7 月 8 日为批次任务外迁 + 园区低负载日，
  触发基线筛选的剔除演示（IT 批次 -50%、园区空调 -45%、制冷 -85% 保留）。
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
POINTS = 96
MTU_MIN = 15
HISTORY_DATES = (
    "2026-07-07",
    "2026-07-08",
    "2026-07-09",
    "2026-07-10",
    "2026-07-13",
)
ANOMALY_DATE = "2026-07-08"
# 批次任务外迁日：IT 批次减半、园区空调近半、制冷略降（不足以触发剔除）。
ANOMALY_FACTORS = {
    "dc_it_batch_mw": 0.50,
    "campus_hvac_mw": 0.45,
    "dc_cooling_mw": 0.85,
    "dc_ups_mw": 1.0,
}
EVENT_DATE = "2026-07-14"
EVENT_START = "14:00"
EVENT_END = "15:00"
EVENT_SLOTS = (56, 57, 58, 59)

# Piecewise-constant hourly anchors (hour, MW); the value applies to the hour.
SHAPES = {
    "dc_it_batch_mw": (
        (0, 3.0), (7, 6.0), (9, 11.0), (12, 11.5), (17, 10.0), (20, 7.5), (23, 4.5), (24, 3.5),
    ),
    "dc_cooling_mw": (
        (0, 5.0), (6, 4.6), (8, 6.0), (11, 8.5), (13, 9.8), (14, 10.2), (16, 9.6), (19, 7.5), (22, 6.0), (24, 5.2),
    ),
    "dc_ups_mw": (
        (0, 0.0), (24, 0.0),
    ),
    "campus_hvac_mw": (
        (0, 0.8), (8, 1.6), (10, 2.4), (12, 2.8), (14, 2.6), (17, 2.2), (19, 1.4), (22, 1.0), (24, 0.9),
    ),
}
# 事件窗口（14:00-15:00，slots 56-59）各资源的实际负荷（D 级合成）。
ACTUAL_EVENT_LOAD = {
    "dc_cooling_mw": 7.7,   # 冷冻水回调 + 蓄冷：削 2.5 MW
    "dc_it_batch_mw": 6.5,  # 批次迁移：削 5.0 MW
    "campus_hvac_mw": 1.9,  # 园区空调轮停：削 0.7 MW
}
# UPS 受 0.5 h 备电窗口约束：前 0.5 h 放电 4.0 MW，后 0.5 h 归零，
# 事件窗口平均削 2.0 MW（不是 4.0 MW——功率能力 ≠ 1 h 全程放电）。
UPS_EVENT_BY_SLOT = {56: -4.0, 57: -4.0, 58: 0.0, 59: 0.0}
SCENARIOS = (
    ("s1", "direct", 4.0, 3.8),
    ("s1", "self", 3.5, 3.4),
    ("s2", "direct", 5.5, 4.4),
    ("s2", "self", 4.7, 3.9),
    ("s3", "direct", 6.5, 5.0),
    ("s3", "self", 6.0, 4.6),
)
T1_EVENT = (
    ("direct", 4.4, 5.5),
    ("self", 3.9, 4.7),
)


def _value(anchors, hour):
    for index in range(len(anchors) - 1):
        h0, v0 = anchors[index]
        h1, v1 = anchors[index + 1]
        if h0 <= hour < h1:
            return v0
    return anchors[-1][1]


def _loads(hour, factors=None):
    factors = factors or {}
    return {
        field: _value(anchors, hour) * factors.get(field, 1.0)
        for field, anchors in SHAPES.items()
    }


def _slot_start(slot):
    minutes = slot * MTU_MIN
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _slot_end(slot):
    minutes = (slot + 1) * MTU_MIN
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _write(path, header, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    fields = list(SHAPES)
    header = ["date", "slot", "start", "end", *fields]

    history_rows = []
    for date in HISTORY_DATES:
        factors = ANOMALY_FACTORS if date == ANOMALY_DATE else None
        for slot in range(POINTS):
            loads = _loads((slot + 0.5) * 24.0 / POINTS, factors)
            history_rows.append(
                [
                    date,
                    slot,
                    _slot_start(slot),
                    _slot_end(slot),
                    *[f"{loads[field]:.6f}" for field in fields],
                ]
            )
    history_path = DATA / "history_demo.csv"
    _write(history_path, header, history_rows)

    t1_rows = []
    for slot in range(POINTS):
        loads = _loads((slot + 0.5) * 24.0 / POINTS)
        if slot in EVENT_SLOTS:
            loads.update(ACTUAL_EVENT_LOAD)
            loads["dc_ups_mw"] = UPS_EVENT_BY_SLOT[slot]
        t1_rows.append(
            [
                EVENT_DATE,
                slot,
                _slot_start(slot),
                _slot_end(slot),
                *[f"{loads[field]:.6f}" for field in fields],
            ]
        )
    t1_path = DATA / "t1_loads_demo.csv"
    _write(t1_path, header, t1_rows)

    event_rows = [
        [
            scenario,
            control_type,
            EVENT_DATE,
            EVENT_START,
            EVENT_END,
            f"{required_mw:.1f}",
            f"{marginal_price:.2f}",
        ]
        for scenario, control_type, required_mw, marginal_price in SCENARIOS
    ]
    event_path = DATA / "event_demo.csv"
    _write(
        event_path,
        [
            "scenario",
            "control_type",
            "event_date",
            "event_start",
            "event_end",
            "required_mw",
            "marginal_price_cny_per_kwh",
        ],
        event_rows,
    )

    t1_event_rows = [
        [control_type, EVENT_DATE, EVENT_START, EVENT_END, f"{price:.2f}", f"{awarded:.1f}"]
        for control_type, price, awarded in T1_EVENT
    ]
    t1_event_path = DATA / "t1_event_demo.csv"
    _write(
        t1_event_path,
        [
            "control_type",
            "event_date",
            "event_start",
            "event_end",
            "cleared_price_cny_per_kwh",
            "awarded_mw",
        ],
        t1_event_rows,
    )

    # 复核数字（与 README/pitfalls 对齐）
    baseline_window = {}
    for field in fields:
        baseline_window[field] = sum(
            _loads((slot + 0.5) * 24.0 / POINTS)[field] for slot in EVENT_SLOTS
        ) / len(EVENT_SLOTS)
    actual_window = {
        "dc_cooling_mw": ACTUAL_EVENT_LOAD["dc_cooling_mw"],
        "dc_it_batch_mw": ACTUAL_EVENT_LOAD["dc_it_batch_mw"],
        "campus_hvac_mw": ACTUAL_EVENT_LOAD["campus_hvac_mw"],
        "dc_ups_mw": sum(UPS_EVENT_BY_SLOT[s] for s in EVENT_SLOTS) / len(EVENT_SLOTS),
    }
    shed_direct = (baseline_window["dc_cooling_mw"] - actual_window["dc_cooling_mw"]) + (
        0.0 - actual_window["dc_ups_mw"]
    )
    shed_self = (baseline_window["dc_it_batch_mw"] - actual_window["dc_it_batch_mw"]) + (
        baseline_window["campus_hvac_mw"] - actual_window["campus_hvac_mw"]
    )
    ups_energy = -sum(UPS_EVENT_BY_SLOT[s] for s in (56, 57)) * MTU_MIN / 60.0
    print(f"event={EVENT_DATE} {EVENT_START}-{EVENT_END} slots={EVENT_SLOTS}")
    print(f"history days={len(HISTORY_DATES)} (anomaly day {ANOMALY_DATE}: it_batch x0.50, campus x0.45, cooling x0.85)")
    for field in fields:
        print(
            f"  {field}: baseline window avg={baseline_window[field]:.2f} MW, "
            f"actual window avg={actual_window[field]:.2f} MW"
        )
    print(f"direct shed={shed_direct:.2f} MW self shed={shed_self:.2f} MW")
    print(f"ups discharge energy in first 0.5 h={ups_energy:.2f} MWh (<= 4.50 x 0.5 h window)")
    print(f"wrote {history_path}")
    print(f"wrote {event_path}")
    print(f"wrote {t1_path}")
    print(f"wrote {t1_event_path}")


if __name__ == "__main__":
    main()
