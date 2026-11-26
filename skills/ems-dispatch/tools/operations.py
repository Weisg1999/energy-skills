"""Deterministic operations demo: day-ahead merit order, reserve, AGC and a contingency.

A three-unit synthetic system (coal, gas, storage) is dispatched for a
day-ahead net load, re-dispatched for a real-time deviation, then checked for
reserve, AGC allocation and a gas outage. Normal reserve counts thermal
headroom only; ramp values are MW per dispatch interval, not MW/h. Teaching
only; no market data.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

RESERVE_REQUIREMENT_MW = 80.0


@dataclass(frozen=True)
class Unit:
    name: str
    pmin: float
    pmax: float
    cost: float
    ramp: float


def merit_dispatch(net_load_mw: float, units: tuple[Unit, ...]) -> dict[str, float]:
    if net_load_mw < sum(u.pmin for u in units):
        raise ValueError("net load below minimum generation")
    if net_load_mw > sum(u.pmax for u in units):
        raise ValueError("net load above maximum generation")
    dispatch = {u.name: u.pmin for u in units}
    remaining = net_load_mw - sum(dispatch.values())
    for unit in sorted(units, key=lambda u: (u.cost, u.name)):
        room = unit.pmax - dispatch[unit.name]
        take = min(room, remaining)
        dispatch[unit.name] += take
        remaining -= take
        if remaining <= 1e-9:
            break
    if remaining > 1e-6:
        raise AssertionError("merit order failed to clear")
    return dispatch


def reserve_mw(units: tuple[Unit, ...], dispatch: dict[str, float]) -> float:
    """Thermal online headroom only; storage is excluded from normal reserve."""
    return sum(u.pmax - dispatch[u.name] for u in units)


def total_cost(units: tuple[Unit, ...], dispatch: dict[str, float]) -> float:
    return sum(u.cost * dispatch[u.name] for u in units)


def ramp_ok(units: tuple[Unit, ...], before: dict[str, float], after: dict[str, float]) -> bool:
    return all(abs(after[u.name] - before[u.name]) <= u.ramp + 1e-9 for u in units)


def agc_allocate(
    request_mw: float,
    units: tuple[Unit, ...],
    dispatch: dict[str, float],
    weights: dict[str, float],
) -> dict[str, float]:
    remaining = max(0.0, request_mw)
    allocation = {u.name: 0.0 for u in units}
    active = [u for u in units if weights.get(u.name, 0.0) > 0.0]
    while remaining > 1e-9 and active:
        weight_sum = sum(weights[u.name] for u in active)
        moved = 0.0
        for unit in list(active):
            headroom = unit.pmax - dispatch[unit.name] - allocation[unit.name]
            want = remaining * weights[unit.name] / weight_sum
            take = min(headroom, unit.ramp, want)
            allocation[unit.name] += take
            moved += take
            if headroom <= 1e-9 or unit.ramp <= 1e-9:
                active.remove(unit)
        if moved <= 1e-9:
            break
        remaining -= moved
    allocation["unmet_mw"] = max(0.0, remaining)
    return allocation


def demo() -> dict:
    coal = Unit("coal", pmin=150.0, pmax=300.0, cost=300.0, ramp=60.0)
    gas = Unit("gas", pmin=50.0, pmax=200.0, cost=450.0, ramp=100.0)
    units = (coal, gas)

    day_load = 300.0
    rt_load = 360.0
    day = merit_dispatch(day_load, units)
    rt = merit_dispatch(rt_load, units)

    agc = agc_allocate(20.0, units, rt, {"coal": 0.6, "gas": 0.4})

    contingency = {"coal": 300.0, "gas": 0.0, "storage": 60.0}
    storage_initial_mwh = 100.0
    storage_min_mwh = 20.0
    storage_energy_used = min(contingency["storage"], storage_initial_mwh - storage_min_mwh)
    storage_remaining_mwh = storage_initial_mwh - storage_energy_used
    storage_remaining_power_mw = 100.0 - contingency["storage"]
    reserve_duration_h = (
        storage_remaining_mwh / storage_remaining_power_mw
        if storage_remaining_power_mw > 0
        else float("inf")
    )
    contingency_reserve = (coal.pmax - contingency["coal"]) + storage_remaining_power_mw

    return {
        "ramp_unit": "MW per dispatch interval",
        "units": {
            "coal": {"pmin": coal.pmin, "pmax": coal.pmax, "cost": coal.cost, "ramp": coal.ramp},
            "gas": {"pmin": gas.pmin, "pmax": gas.pmax, "cost": gas.cost, "ramp": gas.ramp},
            "storage": {"pmax": 100.0, "energy_mwh": 200.0, "soc_pct": 50.0, "min_soc_pct": 10.0},
        },
        "day_ahead": {
            "net_load_mw": day_load,
            "dispatch": day,
            "cost_cny": total_cost(units, day),
            "reserve_mw": reserve_mw(units, day),
            "reserve_scope": "thermal-only",
        },
        "real_time": {
            "net_load_mw": rt_load,
            "dispatch": rt,
            "cost_cny": total_cost(units, rt),
            "reserve_mw": reserve_mw(units, rt),
            "reserve_scope": "thermal-only",
            "ramp_ok": ramp_ok(units, day, rt),
            "imbalance_cost_cny": total_cost(units, rt) - total_cost(units, day),
        },
        "agc": {
            "request_mw": 20.0,
            "allocation": agc,
            "final_gas_mw": rt["gas"] + agc["gas"],
        },
        "contingency": {
            "case": "gas outage, net load 360 MW",
            "dispatch": contingency,
            "served_mw": sum(contingency.values()),
            "reserve_mw": contingency_reserve,
            "reserve_scope": "post-contingency thermal+storage",
            "reserve_requirement_mw": RESERVE_REQUIREMENT_MW,
            "reserve_shortfall_mw": max(0.0, RESERVE_REQUIREMENT_MW - contingency_reserve),
            "storage_energy_used_mwh": storage_energy_used,
            "storage_remaining_mwh": storage_remaining_mwh,
            "storage_remaining_power_mw": storage_remaining_power_mw,
            "reserve_duration_h_at_remaining_power": reserve_duration_h,
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
    d = result["day_ahead"]
    r = result["real_time"]
    print("Operations demo (synthetic, D-level)")
    print(f"  day-ahead {d['net_load_mw']:.0f} MW  coal/gas {d['dispatch']['coal']:.0f}/{d['dispatch']['gas']:.0f} MW  cost {d['cost_cny']:.0f} CNY  thermal reserve {d['reserve_mw']:.0f} MW")
    print(f"  real-time {r['net_load_mw']:.0f} MW  coal/gas {r['dispatch']['coal']:.0f}/{r['dispatch']['gas']:.0f} MW  cost {r['cost_cny']:.0f} CNY  thermal reserve {r['reserve_mw']:.0f} MW")
    print(f"  AGC 20 MW -> coal {result['agc']['allocation']['coal']:.0f} / gas {result['agc']['allocation']['gas']:.0f} MW")
    print(f"  gas outage upward capability {result['contingency']['reserve_mw']:.0f} MW, shortfall {result['contingency']['reserve_shortfall_mw']:.0f} MW")


if __name__ == "__main__":
    main()