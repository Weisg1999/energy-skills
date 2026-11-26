"""Deterministic resource-adequacy/planning demo.

Enumerates thermal states for two synthetic portfolios against a three-block
load-duration curve, with wind/solar/storage capacity credits. Computes LOLE,
EENS and firm capacity. Teaching only; no real fleet data.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Thermal:
    name: str
    capacity_mw: float
    efor: float


@dataclass(frozen=True)
class Portfolio:
    name: str
    thermal: tuple[Thermal, ...]
    wind_mw: float
    wind_credit: float
    solar_mw: float
    solar_credit: float
    storage_mw: float
    storage_credit: float


LOAD_BLOCKS = (
    (1000.0, 100.0),
    (800.0, 3000.0),
    (500.0, 5660.0),
)
LOLE_TARGET_H = 2.4


def firm_capacity_mw(portfolio: Portfolio) -> float:
    return (
        sum(t.capacity_mw for t in portfolio.thermal)
        + portfolio.wind_mw * portfolio.wind_credit
        + portfolio.solar_mw * portfolio.solar_credit
        + portfolio.storage_mw * portfolio.storage_credit
    )


def adequacy(portfolio: Portfolio) -> dict[str, float]:
    firm_re = (
        portfolio.wind_mw * portfolio.wind_credit
        + portfolio.solar_mw * portfolio.solar_credit
        + portfolio.storage_mw * portfolio.storage_credit
    )
    lole = 0.0
    eens = 0.0
    states = []
    for flags in product((True, False), repeat=len(portfolio.thermal)):
        prob = 1.0
        available = firm_re
        for flag, unit in zip(flags, portfolio.thermal):
            prob *= (1.0 - unit.efor) if flag else unit.efor
            if flag:
                available += unit.capacity_mw
        state_lole = 0.0
        state_eens = 0.0
        for load, hours in LOAD_BLOCKS:
            unserved = max(0.0, load - available)
            if unserved > 0.0:
                state_lole += hours
                state_eens += unserved * hours
        lole += prob * state_lole
        eens += prob * state_eens
        states.append(
            {
                "available_mw": available,
                "probability": prob,
                "unserved_hours": state_lole,
                "unserved_mwh": state_eens,
            }
        )
    return {
        "firm_capacity_mw": firm_capacity_mw(portfolio),
        "lole_h_per_year": lole,
        "eens_mwh_per_year": eens,
        "meets_lole_target": lole <= LOLE_TARGET_H,
        "states": states,
    }


def demo() -> dict:
    coal = Thermal("coal", 600.0, 0.06)
    gas = Thermal("gas", 300.0, 0.04)
    port_a = Portfolio(
        "A-coal+1gas",
        (coal, gas),
        wind_mw=300.0,
        wind_credit=0.20,
        solar_mw=300.0,
        solar_credit=0.10,
        storage_mw=200.0,
        storage_credit=0.80,
    )
    port_b = Portfolio(
        "B-coal+3gas",
        (coal, gas, gas, gas),
        wind_mw=300.0,
        wind_credit=0.20,
        solar_mw=300.0,
        solar_credit=0.10,
        storage_mw=200.0,
        storage_credit=0.80,
    )
    return {
        "load_blocks": [{"load_mw": load, "hours": hours} for load, hours in LOAD_BLOCKS],
        "lole_target_h_per_year": LOLE_TARGET_H,
        "portfolios": {
            "A": adequacy(port_a),
            "B": adequacy(port_b),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    result = demo()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("Resource-adequacy demo (synthetic, D-level)")
    print(f"  peak load 1000 MW, blocks 100/3000/5660 h, LOLE target {LOLE_TARGET_H:.1f} h/y")
    for key in ("A", "B"):
        row = result["portfolios"][key]
        print(
            f"  portfolio {key}: firm {row['firm_capacity_mw']:.0f} MW, "
            f"LOLE {row['lole_h_per_year']:.3f} h/y, EENS {row['eens_mwh_per_year']:.2f} MWh/y"
        )


if __name__ == "__main__":
    main()