#!/usr/bin/env python3
"""Generate the bundled D-level synthetic data for the Shandong cement pack."""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

PRODUCTION = (
    ("2025-01", 128000, "窑检修后复产"),
    ("2025-02", 122000, "春节错峰"),
    ("2025-03", 132000, ""),
    ("2025-04", 130000, ""),
    ("2025-05", 134000, "旺季"),
    ("2025-06", 129000, "错峰停窑 5 天"),
    ("2025-07", 126000, "高温限产"),
    ("2025-08", 131000, ""),
    ("2025-09", 128000, ""),
    ("2025-10", 130000, "旺季"),
    ("2025-11", 126000, "秋冬季错峰"),
    ("2025-12", 134000, "年末冲量"),
)

PRICES = (
    ("2026-01", 88.00, 80.50),
    ("2026-02", 89.20, 81.40),
    ("2026-03", 90.10, 82.00),
    ("2026-04", 87.50, 79.80),
    ("2026-05", 85.00, 78.60),
    ("2026-06", 83.40, 76.90),
    ("2026-07", 81.90, 75.80),
    ("2026-08", 80.60, 74.90),
    ("2026-09", 82.70, 77.20),
    ("2026-10", 90.40, 82.60),
    ("2026-11", 92.30, 84.10),
)


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    write_csv(
        DATA / "production_demo.csv",
        [
            {"month": month, "clinker_t": output, "note": note}
            for month, output, note in PRODUCTION
        ],
        ["month", "clinker_t", "note"],
    )
    write_csv(
        DATA / "verification_demo.csv",
        [
            {
                "compliance_year": 2025,
                "verified_emissions_tco2": 1430000,
                "verification_body": "合成核查机构（D 级）",
            }
        ],
        ["compliance_year", "verified_emissions_tco2", "verification_body"],
    )
    write_csv(
        DATA / "prices_demo.csv",
        [
            {"month": month, "cea_cny_per_t": cea, "ccer_cny_per_t": ccer}
            for month, cea, ccer in PRICES
        ],
        ["month", "cea_cny_per_t", "ccer_cny_per_t"],
    )
    print(f"wrote {DATA}")


if __name__ == "__main__":
    main()
