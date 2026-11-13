#!/usr/bin/env python3
"""Generate grade-D synthetic data for the Shanghai user-side VPP pack.

Six history days x 96 points feed the baseline; the T+1 file is the event day.
All shapes are deterministic, so the demo is reproducible. The data correspond
to no real aggregator, customer, contract or metering point.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

DAYS = ("2026-08-08", "2026-08-09", "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13")
EVENT_DAY = "2026-08-14"
POINTS = 96
EVENT_START = 56  # 14:00
EVENT_END = 60    # 15:00

RESOURCES = (
    ("building_ac", "building_ac_mw"),
    ("ev", "ev_mw"),
    ("storage", "storage_mw"),
    ("data_center", "data_center_mw"),
    ("industrial", "industrial_mw"),
)

# Delivered response per resource during the event (MW), summing to about 70 MW
# against a cleared 80 MW. The shortfall is intentional: it exercises the 95%
# delivery threshold and the extra customer share in the bridge.
RESPONSE_MW = {
    "building_ac": 17.0,
    "ev": 17.5,
    "storage": 21.0,
    "data_center": 4.3,
    "industrial": 10.0,
}


def _bell(hour, center, width):
    return math.exp(-((hour - center) / width) ** 2)


def base_load(resource, hour):
    if resource == "building_ac":
        return 25.0 + 75.0 * _bell(hour, 14.5, 3.0)
    if resource == "ev":
        return 15.0 + 25.0 * _bell(hour, 8.0, 2.0) + 25.0 * _bell(hour, 19.0, 2.5)
    if resource == "storage":
        if hour < 6:
            return 10.0
        if 18 <= hour < 21:
            return -10.0
        return 0.0
    if resource == "data_center":
        return 45.0
    if resource == "industrial":
        return 70.0
    raise ValueError(resource)


def slot_hour(slot):
    return slot * 0.25


def history_value(resource, day_index, slot):
    hour = slot_hour(slot)
    wobble = 0.01 * math.sin((slot + day_index * 7) / 5.0) + 0.004 * day_index
    return base_load(resource, hour) * (1.0 + wobble)


def t1_value(resource, slot):
    hour = slot_hour(slot)
    value = base_load(resource, hour) * (1.0 + 0.005 * math.sin(slot / 4.0))
    if EVENT_START <= slot < EVENT_END:
        value -= RESPONSE_MW[resource]
    return value


def _write(path, header, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    header = ["date", "slot"] + [field for _, field in RESOURCES]
    rows = []
    for day_index, day in enumerate(DAYS):
        for slot in range(POINTS):
            rows.append(
                [day, slot]
                + [f"{history_value(resource, day_index, slot):.4f}" for resource, _ in RESOURCES]
            )
    _write(DATA / "history_demo.csv", header, rows)

    t1_rows = []
    for slot in range(POINTS):
        t1_rows.append(
            [EVENT_DAY, slot] + [f"{t1_value(resource, slot):.4f}" for resource, _ in RESOURCES]
        )
    _write(DATA / "t1_loads_demo.csv", header, t1_rows)

    _write(
        DATA / "event_demo.csv",
        ["scenario", "event_date", "event_start", "event_end", "required_mw", "incentive_price_cny_per_kwh"],
        [
            ("s1", EVENT_DAY, "14:00", "15:00", 70.0, 3.6),
            ("s2", EVENT_DAY, "14:00", "15:00", 80.0, 4.2),
            ("s3", EVENT_DAY, "14:00", "15:00", 90.0, 5.0),
        ],
    )
    _write(
        DATA / "t1_event_demo.csv",
        ["cleared_price_cny_per_kwh", "cleared_mw"],
        [(4.2, 80.0)],
    )
    print(f"wrote {DATA}")


if __name__ == "__main__":
    main()
