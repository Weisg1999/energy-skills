#!/usr/bin/env python3
"""Generate grade-D synthetic D-1 and T+1 data for the Guangdong retail instance.

The data correspond to no real retailer, customer profile, contract or market
price. Shapes are deterministic, so the demo is reproducible.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATE = "2026-11-18"
POINTS = 96
MTU_MIN = 15
DAILY_ENERGY_MWH = 2880.0
SCENARIO_MULTIPLIERS = (0.85, 0.95, 1.0, 1.15, 1.45)

INDUSTRIAL = (
    (0, 0.46), (6, 0.52), (8, 0.78), (10, 0.92), (12, 0.82),
    (14, 0.88), (18, 0.90), (19, 1.00), (21, 0.80), (24, 0.48),
)
COMMERCIAL = (
    (0, 0.18), (7, 0.22), (9, 0.72), (12, 0.94), (14, 0.88),
    (18, 0.96), (21, 0.70), (23, 0.30), (24, 0.18),
)
DATA_CENTER = (
    (0, 0.95), (8, 1.00), (12, 1.02), (18, 1.04), (22, 1.00), (24, 0.96),
)
PRICE_ANCHORS = (
    (0, 280.0), (6, 260.0), (8, 380.0), (11, 300.0), (13, 230.0),
    (17, 420.0), (19, 850.0), (20, 700.0), (22, 380.0), (24, 300.0),
)


def _interp(anchors, hour):
    for index in range(len(anchors) - 1):
        x0, y0 = anchors[index]
        x1, y1 = anchors[index + 1]
        if x0 <= hour <= x1:
            return y0 + (y1 - y0) * (hour - x0) / (x1 - x0)
    return anchors[-1][1]


def _shape(anchors):
    raw = [_interp(anchors, (slot + 0.5) * 24.0 / POINTS) for slot in range(POINTS)]
    total = sum(raw)
    return [value / total for value in raw]


def _blended_load_shape():
    industrial = _shape(INDUSTRIAL)
    commercial = _shape(COMMERCIAL)
    data_center = _shape(DATA_CENTER)
    raw = [
        0.55 * industrial[slot] + 0.15 * commercial[slot] + 0.30 * data_center[slot]
        for slot in range(POINTS)
    ]
    total = sum(raw)
    return [value / total for value in raw]


def _price_curve():
    raw = [_interp(PRICE_ANCHORS, (slot + 0.5) * 24.0 / POINTS) for slot in range(POINTS)]
    mean = sum(raw) / len(raw)
    return [value * 360.0 / mean for value in raw]


def _actual_load(forecast):
    actual = []
    for slot, value in enumerate(forecast):
        factor = 1.012
        if 36 <= slot <= 45:
            factor = 1.060
        elif 72 <= slot <= 81:
            factor = 1.050
        actual.append(value * factor)
    return actual


def _actual_price(base):
    actual = []
    for slot, value in enumerate(base):
        ripple = 1.0 + 0.02 * math.sin(slot / 5.0)
        actual.append(value * 1.08 * ripple)
    return actual


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
    shape = _blended_load_shape()
    forecast = [value * DAILY_ENERGY_MWH / (MTU_MIN / 60.0) for value in shape]
    base = _price_curve()
    actual_load = _actual_load(forecast)
    actual_price = _actual_price(base)

    floor, cap = -50.0, 1800.0
    for name, curve in [("base", base)] + [
        (f"price_s{index + 1}", [value * multiplier for value in base])
        for index, multiplier in enumerate(SCENARIO_MULTIPLIERS)
    ]:
        low, high = min(curve), max(curve)
        if low < floor - 1e-9 or high > cap + 1e-9:
            raise AssertionError(f"{name} 越界：{low:.2f}–{high:.2f}")

    d1_rows = []
    for slot in range(POINTS):
        d1_rows.append(
            [
                DATE,
                slot,
                _slot_start(slot),
                _slot_end(slot),
                f"{forecast[slot]:.6f}",
                *[f"{base[slot] * multiplier:.2f}" for multiplier in SCENARIO_MULTIPLIERS],
            ]
        )
    d1_path = DATA / "d1_demo.csv"
    _write(
        d1_path,
        ["date", "slot", "start", "end", "forecast_load_mw", "price_s1", "price_s2", "price_s3", "price_s4", "price_s5"],
        d1_rows,
    )

    t1_rows = []
    for slot in range(POINTS):
        t1_rows.append(
            [
                DATE,
                slot,
                _slot_start(slot),
                _slot_end(slot),
                f"{actual_load[slot]:.6f}",
                f"{actual_price[slot]:.2f}",
            ]
        )
    t1_path = DATA / "t1_demo.csv"
    _write(t1_path, ["date", "slot", "start", "end", "actual_load_mw", "actual_price"], t1_rows)

    forecast_energy = sum(forecast) * MTU_MIN / 60.0
    actual_energy = sum(actual_load) * MTU_MIN / 60.0
    print(f"date={DATE} points={POINTS}")
    print(f"forecast energy={forecast_energy:,.1f} MWh actual energy={actual_energy:,.1f} MWh")
    print(f"reference average={sum(base) / len(base):.2f} CNY/MWh actual average={sum(actual_price) / len(actual_price):.2f}")
    print("scenario averages=" + ", ".join(f"{sum(base) / len(base) * multiplier:.2f}" for multiplier in SCENARIO_MULTIPLIERS))
    print(f"wrote {d1_path}")
    print(f"wrote {t1_path}")


if __name__ == "__main__":
    main()
