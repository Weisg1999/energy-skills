"""Deterministic siting/sizing demo for grid-side storage.

A three-bus synthetic network with a transfer limit; compares no storage, two
storage sizes at the constrained bus, and the same storage at the wrong bus.
Reliability value uses a stated VoLL; economics use a stated CRF. Teaching only.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    name: str
    storage_mw: float
    storage_mwh: float
    bus: int
    congestion_benefit_m: float
    arbitrage_benefit_m: float


def eens_mwh(
    storage_mw: float,
    storage_mwh: float,
    bus: int,
    bus3_load_mw: float = 80.0,
    line23_limit_mw: float = 40.0,
    outage_h: float = 4.0,
) -> float:
    local_support = 0.0
    if bus == 3 and outage_h > 0:
        local_support = min(storage_mw, storage_mwh / outage_h)
    unserved_mw = max(0.0, bus3_load_mw - line23_limit_mw - local_support)
    return unserved_mw * outage_h


def reliability_value_m(eens_reduction_mwh: float, voll_cny_per_kwh: float = 30.0) -> float:
    return eens_reduction_mwh * 1000.0 * voll_cny_per_kwh / 1_000_000.0


def crf(rate: float = 0.08, years: int = 15) -> float:
    return rate / (1.0 - (1.0 + rate) ** (-years))


def annuity_factor(rate: float = 0.08, years: int = 15) -> float:
    return (1.0 - (1.0 + rate) ** (-years)) / rate


def storage_capex_m(storage_mwh: float, cny_per_wh: float = 0.60) -> float:
    return storage_mwh * 1_000_000.0 * cny_per_wh / 1_000_000.0


def evaluate(case: Case, base_eens_mwh: float) -> dict[str, float]:
    eens = eens_mwh(case.storage_mw, case.storage_mwh, case.bus)
    reliability = reliability_value_m(base_eens_mwh - eens)
    benefits = reliability + case.congestion_benefit_m + case.arbitrage_benefit_m
    capex = storage_capex_m(case.storage_mwh)
    annual_cost = capex * crf()
    npv = -capex + benefits * annuity_factor()
    return {
        "eens_mwh": eens,
        "reliability_value_m": reliability,
        "congestion_benefit_m": case.congestion_benefit_m,
        "arbitrage_benefit_m": case.arbitrage_benefit_m,
        "total_benefit_m": benefits,
        "capex_m": capex,
        "annual_cost_m": annual_cost,
        "npv_m": npv,
        "bcr": benefits * annuity_factor() / capex if capex > 0 else float("inf"),
    }


def demo() -> dict:
    base = eens_mwh(0.0, 0.0, bus=3)
    cases = (
        Case("no-storage", 0.0, 0.0, 3, 0.0, 0.0),
        Case("40MW-80MWh-bus3", 40.0, 80.0, 3, 1.0, 2.4),
        Case("80MW-160MWh-bus3", 80.0, 160.0, 3, 2.0, 4.8),
        Case("80MW-160MWh-bus2", 80.0, 160.0, 2, 0.25, 4.8),
    )
    rows = []
    for case in cases:
        row = {
            "name": case.name,
            "storage_mw": case.storage_mw,
            "storage_mwh": case.storage_mwh,
            "bus": case.bus,
        }
        row.update(evaluate(case, base))
        rows.append(row)
    return {
        "base": {
            "bus3_load_mw": 80.0,
            "line23_limit_mw": 40.0,
            "outage_h": 4.0,
            "base_eens_mwh": base,
            "voll_cny_per_kwh": 30.0,
            "capex_cny_per_wh": 0.60,
            "crf": crf(),
            "annuity_factor": annuity_factor(),
        },
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    result = demo()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("Storage siting/sizing demo (synthetic, D-level, 3-bus network)")
    print(f"  base EENS              {result['base']['base_eens_mwh']:.1f} MWh/y")
    for row in result["cases"]:
        print(
            f"  {row['name']:<22} EENS {row['eens_mwh']:6.1f} MWh  "
            f"NPV {row['npv_m']:7.2f} m  BCR {row['bcr']:.2f}"
        )


if __name__ == "__main__":
    main()