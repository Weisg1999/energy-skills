#!/usr/bin/env python3
"""Generate the synthetic negative-price-day profile for the Shandong replay pack.

Two files:

* ``data/price_profile_demo.csv`` — one replay day, 24 hourly slots: PV
  available output (D-grade synthetic duck curve peaking at the 200 MW
  capacity) and three noon-price scenarios. S1 (base) is the deep-valley
  negative-price day used for the loss replay, with the 11:00-14:00 deep
  valley touching the -80 CNY/MWh declaration floor; S2 is a mild negative
  day; S3 is a no-negative day.
* ``data/declaration_curves_demo.csv`` — the two D-1 declaration curves:
  strategy A declares full available output (the wrong baseline), strategy B
  declares 10% of available output in the forecast negative window
  (slots 11-14). Both curves stay fixed across the three scenarios; only
  realized clearing prices change.

All values are grade D synthetic data and do not correspond to any real
plant, day or clearing result.
"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "data"

CAPACITY_MW = 200.0
CURTAIL_RATIO = 0.9  # mirrors instance.json strategy_b.curtail_ratio
DECLARATION_WINDOW = [11, 12, 13, 14]  # forecast negative slots, mirrors trigger 0

AVAILABLE_MW = [0, 0, 0, 0, 0, 0, 10, 45, 95, 145, 180, 195, 200, 200, 195, 175, 135, 85, 35, 5, 0, 0, 0, 0]

PRICE_S1_DEEP_VALLEY = [330, 320, 310, 305, 310, 320, 340, 355, 380, 300, 120, -60, -80, -80, -30, 180, 320, 480, 650, 520, 420, 360, 330, 315]
PRICE_S2_MILD = [330, 320, 310, 305, 310, 320, 340, 355, 380, 300, 120, -10, -30, -30, -5, 180, 320, 480, 650, 520, 420, 360, 330, 315]
PRICE_S3_NO_NEGATIVE = [330, 320, 310, 305, 310, 320, 340, 355, 380, 300, 120, 60, 40, 40, 80, 180, 320, 480, 650, 520, 420, 360, 330, 315]

PRICE_FIELDS = [
    "price_s1_deep_valley",
    "price_s2_mild",
    "price_s3_no_negative",
]


def start_end(slot: int) -> tuple[str, str]:
    return f"{slot:02d}:00", f"{(slot + 1) % 24:02d}:00"


def validate() -> None:
    n = len(AVAILABLE_MW)
    if not (len(PRICE_S1_DEEP_VALLEY) == len(PRICE_S2_MILD) == len(PRICE_S3_NO_NEGATIVE) == n == 24):
        raise ValueError("all columns must have 24 hourly slots")
    if max(AVAILABLE_MW) > CAPACITY_MW:
        raise ValueError("available output must not exceed installed capacity")
    if max(AVAILABLE_MW) < CAPACITY_MW:
        raise ValueError("duck curve must reach the 200 MW capacity at noon (满发 clipping)")
    total = sum(AVAILABLE_MW)
    if total != 1700:
        raise ValueError(f"daily available energy must be 1,700 MWh, got {total}")
    for slot in DECLARATION_WINDOW:
        for prices, label in ((PRICE_S1_DEEP_VALLEY, "S1"), (PRICE_S2_MILD, "S2")):
            if prices[slot] >= 0:
                raise ValueError(f"{label} slot {slot} must be negative")
        if PRICE_S3_NO_NEGATIVE[slot] <= 0:
            raise ValueError(f"S3 slot {slot} must be positive (no negative day)")
    if PRICE_S1_DEEP_VALLEY[12] != -80 or PRICE_S1_DEEP_VALLEY[13] != -80:
        raise ValueError("S1 noon must touch the -80 CNY/MWh declaration floor")
    if PRICE_S1_DEEP_VALLEY[11] != -60:
        raise ValueError("S1 slot 11 must stay at the -60 deep-valley sample")
    for prices in (PRICE_S1_DEEP_VALLEY, PRICE_S2_MILD, PRICE_S3_NO_NEGATIVE):
        if min(prices) < -100 or max(prices) > 1500:
            raise ValueError("prices must stay within the Shandong clearing limits [-100, 1500] CNY/MWh")


def declaration_curves() -> tuple[list[float], list[float]]:
    declare_a = [float(x) for x in AVAILABLE_MW]
    declare_b = [float(x) for x in AVAILABLE_MW]
    for slot in DECLARATION_WINDOW:
        declare_b[slot] = AVAILABLE_MW[slot] * (1.0 - CURTAIL_RATIO)
    return declare_a, declare_b


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    validate()
    declare_a, declare_b = declaration_curves()

    price_rows = []
    declaration_rows = []
    for slot in range(24):
        start, end = start_end(slot)
        price_rows.append(
            {
                "slot": slot,
                "start": start,
                "end": end,
                "pv_available_mw": f"{AVAILABLE_MW[slot]:.1f}",
                "price_s1_deep_valley": f"{PRICE_S1_DEEP_VALLEY[slot]:.1f}",
                "price_s2_mild": f"{PRICE_S2_MILD[slot]:.1f}",
                "price_s3_no_negative": f"{PRICE_S3_NO_NEGATIVE[slot]:.1f}",
            }
        )
        declaration_rows.append(
            {
                "slot": slot,
                "start": start,
                "end": end,
                "declare_a_full_mw": f"{declare_a[slot]:.1f}",
                "declare_b_curtail_mw": f"{declare_b[slot]:.1f}",
            }
        )

    write_csv(
        OUT_DIR / "price_profile_demo.csv",
        ["slot", "start", "end", "pv_available_mw"] + PRICE_FIELDS,
        price_rows,
    )
    write_csv(
        OUT_DIR / "declaration_curves_demo.csv",
        ["slot", "start", "end", "declare_a_full_mw", "declare_b_curtail_mw"],
        declaration_rows,
    )

    daily = sum(AVAILABLE_MW)
    window_energy = sum(AVAILABLE_MW[s] for s in DECLARATION_WINDOW)
    print(f"wrote {OUT_DIR / 'price_profile_demo.csv'} (24 slots, 3 scenarios)")
    print(f"wrote {OUT_DIR / 'declaration_curves_demo.csv'} (A full / B {CURTAIL_RATIO:.0%} curtail in slots {DECLARATION_WINDOW})")
    print(f"available energy {daily:,.0f} MWh, declaration-window energy {window_energy:,.0f} MWh")


if __name__ == "__main__":
    main()
