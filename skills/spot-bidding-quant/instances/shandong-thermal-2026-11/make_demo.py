#!/usr/bin/env python3
"""Generate grade-D synthetic D-1 and T+1 data for the Shandong thermal pack.

The data correspond to no real unit, contract or market price. Shapes are
deterministic, so the demo is reproducible.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

POWER_MW = 350.0
MIN_OUTPUT_MW = 122.5
HEAT_RATIO = 1.6
VARIABLE_COST = 260.0
MARKUP = 20.0
RESERVE_MW = 20.0
DATE = "2026-11-18"

BASE_ANCHORS = (
    (0, 220.0),
    (6, 235.0),
    (8, 300.0),
    (11, 330.0),
    (12, 190.0),
    (14, 185.0),
    (17, 300.0),
    (19, 560.0),
    (21, 400.0),
    (22, 280.0),
    (24, 225.0),
)

MULTIPLIERS = (0.75, 0.90, 1.00, 1.12, 1.30)


def _interp(anchors, hour):
    for (h0, v0), (h1, v1) in zip(anchors, anchors[1:]):
        if h0 <= hour <= h1:
            if h1 == h0:
                return v1
            return v0 + (v1 - v0) * (hour - h0) / (h1 - h0)
    return anchors[-1][1]


def _heat(slot):
    hour = slot / 4.0
    return 240.0 + 18.0 * math.cos(2.0 * math.pi * hour / 24.0)


def _heat_actual(slot):
    hour = slot / 4.0
    return _heat(slot) + 8.0 * math.sin(2.0 * math.pi * hour / 24.0 + 1.0)


def _actual_price(slot):
    hour = slot / 4.0
    base = _interp(BASE_ANCHORS, hour)
    return base * 1.03 + 18.0 * math.sin(2.0 * math.pi * hour / 24.0 + 0.4)


def _heat_min(heat):
    return min(POWER_MW, max(MIN_OUTPUT_MW, heat / HEAT_RATIO))


def _output(price, heat):
    energy_max = POWER_MW - RESERVE_MW
    return energy_max if price >= VARIABLE_COST + MARKUP else _heat_min(heat)


def _write(path, header, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    d1_rows = []
    t1_rows = []
    for slot in range(96):
        start_min = slot * 15
        end_min = start_min + 15
        start = f"{start_min // 60:02d}:{start_min % 60:02d}"
        end = f"{end_min // 60:02d}:{end_min % 60:02d}"
        hour = slot / 4.0
        base = _interp(BASE_ANCHORS, hour)
        heat = _heat(slot)
        prices = [base * factor for factor in MULTIPLIERS]
        d1_rows.append(
            [DATE, slot, start, end, f"{heat:.1f}"]
            + [f"{price:.1f}" for price in prices]
        )
        actual_price = _actual_price(slot)
        actual_heat = _heat_actual(slot)
        actual_output = _output(actual_price, actual_heat)
        t1_rows.append(
            [DATE, slot, f"{actual_price:.1f}", f"{actual_output:.1f}", f"{actual_heat:.1f}"]
        )

    _write(
        DATA / "d1_demo.csv",
        ["date", "slot", "start", "end", "heat_load_mw_th"]
        + [f"price_s{index}" for index in range(1, 6)],
        d1_rows,
    )
    _write(
        DATA / "t1_demo.csv",
        ["date", "slot", "actual_price", "actual_output_mw", "actual_heat_load_mw_th"],
        t1_rows,
    )
    print(f"wrote {DATA / 'd1_demo.csv'}")
    print(f"wrote {DATA / 't1_demo.csv'}")


if __name__ == "__main__":
    main()
