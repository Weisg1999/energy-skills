#!/usr/bin/env python3
"""Generate grade-D synthetic history, invitation and T+1 data for the Jiangsu pack.

The data correspond to no real aggregator, customer, baseline, contract or
market price. Shapes are deterministic, so the demo is reproducible.
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
    "2026-07-14",
)
LOW_ENERGY_DATE = "2026-07-10"
LOW_ENERGY_FACTOR = 0.20
EVENT_DATE = "2026-07-15"
EVENT_START = "19:00"
EVENT_END = "19:30"
EVENT_SLOTS = (76, 77)

# Piecewise-constant hourly anchors (hour, MW); the value applies to the hour.
SHAPES = {
    "industrial_direct_mw": (
        (0, 18.0), (6, 22.0), (8, 28.0), (17, 30.0), (22, 20.0), (24, 20.0),
    ),
    "storage_direct_mw": (
        (0, 0.0), (2, 5.0), (5, 0.0), (24, 0.0),
    ),
    "hvac_direct_mw": (
        (0, 1.2), (6, 3.0), (17, 4.0), (22, 1.5), (24, 1.5),
    ),
    "industrial_self_mw": (
        (0, 16.0), (6, 24.0), (17, 26.0), (22, 18.0), (24, 18.0),
    ),
}
BASELINE_EVENT_LOAD = {
    "industrial_direct_mw": 30.0,
    "storage_direct_mw": 0.0,
    "hvac_direct_mw": 4.0,
    "industrial_self_mw": 26.0,
}
ACTUAL_EVENT_LOAD = {
    "industrial_direct_mw": 17.46,
    "storage_direct_mw": -9.50,
    "hvac_direct_mw": 1.84,
    "industrial_self_mw": 15.20,
}
SCENARIOS = (
    ("s1", "direct", 20.0, 13.0),
    ("s1", "self", 6.0, 8.8),
    ("s2", "direct", 26.0, 13.8),
    ("s2", "self", 9.0, 9.6),
    ("s3", "direct", 32.0, 14.8),
    ("s3", "self", 12.0, 10.2),
)
T1_EVENT = (
    ("direct", 13.8, 26.0),
    ("self", 9.6, 8.6),
)


def _value(anchors, hour):
    for index in range(len(anchors) - 1):
        h0, v0 = anchors[index]
        h1, v1 = anchors[index + 1]
        if h0 <= hour < h1:
            return v0
    return anchors[-1][1]


def _loads(hour, factor=1.0):
    return {field: _value(anchors, hour) * factor for field, anchors in SHAPES.items()}


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
        factor = LOW_ENERGY_FACTOR if date == LOW_ENERGY_DATE else 1.0
        for slot in range(POINTS):
            loads = _loads((slot + 0.5) * 24.0 / POINTS, factor)
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

    normal_energy = sum(_loads((slot + 0.5) * 24.0 / POINTS)["industrial_direct_mw"] for slot in range(POINTS)) * MTU_MIN / 60.0
    low_energy = normal_energy * LOW_ENERGY_FACTOR
    direct_shed = sum(
        BASELINE_EVENT_LOAD[field] - ACTUAL_EVENT_LOAD[field]
        for field in ("industrial_direct_mw", "storage_direct_mw", "hvac_direct_mw")
    )
    self_shed = BASELINE_EVENT_LOAD["industrial_self_mw"] - ACTUAL_EVENT_LOAD["industrial_self_mw"]
    print(f"event={EVENT_DATE} {EVENT_START}-{EVENT_END} slots={EVENT_SLOTS}")
    print(f"history days={len(HISTORY_DATES)} normal energy={normal_energy:,.1f} MWh low day={low_energy:,.1f} MWh")
    print(f"actual direct shed={direct_shed:.2f} MW self shed={self_shed:.2f} MW")
    print(f"wrote {history_path}")
    print(f"wrote {event_path}")
    print(f"wrote {t1_path}")
    print(f"wrote {t1_event_path}")


if __name__ == "__main__":
    main()
