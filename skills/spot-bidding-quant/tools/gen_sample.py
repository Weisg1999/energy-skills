"""Generate the synthetic day-ahead dataset used by the reference tools.

All data are synthetic: a convex supply stack, a weather-driven load profile and
a solar/wind profile. Nothing here is real market data and no figure in the
generated file may be quoted as a market observation.

Run:  python tools/gen_sample.py
"""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

SLOTS = 96
DAYS = 60
START = date(2026, 9, 1)
SEED = 20261101
OUT = Path(__file__).resolve().parent.parent / "data" / "sample" / "synthetic_spot_60d.csv"


def load_shape(hour: float) -> float:
    morning = math.exp(-0.5 * ((hour - 10.0) / 2.2) ** 2)
    evening = math.exp(-0.5 * ((hour - 19.5) / 2.0) ** 2)
    midday = 0.55 * math.exp(-0.5 * ((hour - 14.0) / 2.5) ** 2)
    return 0.72 + 0.30 * morning + 0.55 * evening + 0.18 * midday


def solar_shape(hour: float) -> float:
    if hour < 6.0 or hour > 18.5:
        return 0.0
    return max(0.0, math.sin(math.pi * (hour - 6.0) / 12.5)) ** 1.5


def price_curve(net_load: float, capacity: float = 45000.0) -> float:
    x = net_load / capacity
    price = 250.0 + 1200.0 * max(x, 0.0) ** 2.5
    if x < 0.45:
        price -= 2500.0 * (0.45 - x) ** 1.2
    return price


def main() -> None:
    rng = random.Random(SEED)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = 27.0
    wind_level = 3200.0
    rows = []

    for d in range(DAYS):
        day = START + timedelta(days=d)
        is_weekend = day.weekday() >= 5
        weekday_factor = 0.93 if is_weekend else 1.0
        temp += rng.gauss(0.0, 0.9)
        temp = min(34.0, max(12.0, 0.985 * temp + 0.015 * 24.0))
        wind_level = max(600.0, 0.85 * wind_level + 0.15 * rng.gauss(3200.0, 900.0))
        cloud = min(1.0, max(0.25, rng.gauss(0.72, 0.16)))

        for slot in range(SLOTS):
            hour = slot / 4.0
            temp_slot = temp + 4.0 * math.sin(math.pi * (hour - 8.0) / 12.0)
            cooling = 0.012 * max(0.0, temp_slot - 26.0)
            load = 33000.0 * load_shape(hour) * weekday_factor * (1.0 + cooling)

            solar = 9000.0 * solar_shape(hour) * cloud * (0.85 + 0.15 * math.sin(math.pi * d / 30.0))
            wind = wind_level * (0.75 + 0.35 * math.sin(math.pi * (hour + 3.0) / 10.0) ** 2)
            renewable = solar + wind

            net_load = load - renewable
            raw_price = price_curve(net_load)
            if net_load / 45000.0 > 0.82 and rng.random() < 0.02:
                raw_price += rng.uniform(300.0, 650.0)
            da_price = max(-100.0, min(1500.0, raw_price + rng.gauss(0.0, 28.0)))
            rt_price = max(-100.0, min(2000.0, da_price + rng.gauss(0.0, 45.0)))

            load_forecast = load * (1.0 + rng.gauss(0.0, 0.015))
            wind_forecast = max(0.0, wind * (1.0 + rng.gauss(0.0, 0.07)))
            solar_forecast = max(0.0, solar * (1.0 + rng.gauss(0.0, 0.09)))

            rows.append(
                {
                    "date": day.isoformat(),
                    "slot": slot,
                    "hour": round(hour, 2),
                    "load_forecast_mw": round(load_forecast, 1),
                    "load_actual_mw": round(load, 1),
                    "wind_forecast_mw": round(wind_forecast, 1),
                    "wind_actual_mw": round(wind, 1),
                    "solar_forecast_mw": round(solar_forecast, 1),
                    "solar_actual_mw": round(solar, 1),
                    "da_price": round(da_price, 1),
                    "rt_price": round(rt_price, 1),
                }
            )

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows ({DAYS} days x {SLOTS} slots) to {OUT}")


if __name__ == "__main__":
    main()
