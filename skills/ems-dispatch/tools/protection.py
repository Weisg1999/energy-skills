"""Deterministic protection-coordination demo for a synthetic 10 kV microgrid.

The case contrasts grid-connected and islanded fault currents, then checks
overcurrent pickup, sensitivity and upstream/downstream coordination. It is a
teaching reference, not a relay-setting program and carries no real grid data.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass

BASE_MVA = 100.0
BASE_KV = 10.0
BASE_CURRENT_KA = BASE_MVA / (math.sqrt(3.0) * BASE_KV)
ISLAND_LOAD_MW = 4.0
ISLAND_LOAD_PF = 0.95
ISLAND_PICKUP_FACTOR = 1.23


@dataclass(frozen=True)
class FaultCase:
    name: str
    z_source_pu: complex
    z_feeder_pu: complex


@dataclass(frozen=True)
class Relay:
    name: str
    pickup_ka: float
    tms: float
    curve: str = "SI"


def fault_current_ka(z_total_pu: complex) -> float:
    if abs(z_total_pu) < 1e-12:
        raise ValueError("zero total impedance")
    return BASE_CURRENT_KA / abs(z_total_pu)


def grid_fault(case: FaultCase) -> dict[str, float]:
    z_total = case.z_source_pu + case.z_feeder_pu
    i_pu = 1.0 / abs(z_total)
    return {
        "r_pu": z_total.real,
        "x_pu": z_total.imag,
        "z_abs_pu": abs(z_total),
        "i_pu": i_pu,
        "i_ka": i_pu * BASE_CURRENT_KA,
    }


def inverter_fault_current_ka(
    rated_mw: float, voltage_kv: float = BASE_KV, pf: float = 0.95, limit: float = 1.2
) -> float:
    rated_ka = rated_mw / (math.sqrt(3.0) * voltage_kv * pf)
    return limit * rated_ka


def relay_time_s(current_ka: float, relay: Relay) -> float:
    ratio = current_ka / relay.pickup_ka
    if ratio <= 1.0:
        return math.inf
    curves = {
        "SI": (0.14, 0.02),
        "VI": (13.5, 1.0),
        "EI": (80.0, 2.0),
    }
    if relay.curve not in curves:
        raise ValueError(f"unsupported curve {relay.curve}")
    k, alpha = curves[relay.curve]
    if relay.curve == "SI":
        return relay.tms * k / (ratio**alpha - 1.0)
    if relay.curve == "VI":
        return relay.tms * k / (ratio - 1.0)
    return relay.tms * k / (ratio**alpha - 1.0)


def sensitivity(fault_ka: float, pickup_ka: float) -> float:
    return fault_ka / pickup_ka


def coordination_margin_s(upstream: Relay, downstream: Relay, fault_ka: float) -> float:
    return relay_time_s(fault_ka, upstream) - relay_time_s(fault_ka, downstream)


def demo() -> dict:
    grid = FaultCase("grid-connected", complex(0.0, 0.4), complex(0.08, 0.12))
    far = FaultCase("grid-connected-far", complex(0.0, 0.4), complex(0.14, 0.22))
    near_grid = grid_fault(grid)
    far_grid = grid_fault(far)

    rated_mw = 10.0
    islanded_near = inverter_fault_current_ka(rated_mw, pf=ISLAND_LOAD_PF)
    islanded_far = 0.9 * islanded_near

    island_load_ka = ISLAND_LOAD_MW / (math.sqrt(3.0) * BASE_KV * ISLAND_LOAD_PF)
    island_pickup = round(ISLAND_PICKUP_FACTOR * island_load_ka, 2)

    r1_grid = Relay("microgrid-grid", pickup_ka=0.73, tms=0.10)
    r1_island = Relay("microgrid-island", pickup_ka=island_pickup, tms=0.10)
    r2 = Relay("upstream-grid", pickup_ka=1.00, tms=0.20)

    t_r1_near = relay_time_s(near_grid["i_ka"], r1_grid)
    t_r2_near = relay_time_s(near_grid["i_ka"], r2)
    t_r1_far = relay_time_s(far_grid["i_ka"], r1_grid)
    t_r2_far = relay_time_s(far_grid["i_ka"], r2)
    margin_near = t_r2_near - t_r1_near
    margin_far = t_r2_far - t_r1_far

    ground_pickup_a = 40.0
    ground_current_a = 400.0

    return {
        "base": {
            "mva": BASE_MVA,
            "kv": BASE_KV,
            "current_ka": BASE_CURRENT_KA,
        },
        "grid_near": near_grid,
        "grid_far": far_grid,
        "islanded": {
            "rated_mw": rated_mw,
            "rated_ka": rated_mw / (math.sqrt(3.0) * BASE_KV * ISLAND_LOAD_PF),
            "near_ka": islanded_near,
            "far_ka": islanded_far,
        },
        "island_load": {
            "load_mw": ISLAND_LOAD_MW,
            "load_pf": ISLAND_LOAD_PF,
            "current_ka": island_load_ka,
            "pickup_factor": ISLAND_PICKUP_FACTOR,
            "r1_pickup_ka": island_pickup,
        },
        "relays": {
            "r1_grid_pickup_ka": r1_grid.pickup_ka,
            "r1_island_pickup_ka": r1_island.pickup_ka,
            "r2_pickup_ka": r2.pickup_ka,
            "r1_tms": r1_grid.tms,
            "r2_tms": r2.tms,
        },
        "sensitivity": {
            "r1_grid_near": sensitivity(near_grid["i_ka"], r1_grid.pickup_ka),
            "r1_grid_far": sensitivity(far_grid["i_ka"], r1_grid.pickup_ka),
            "r1_island_near": sensitivity(islanded_near, r1_island.pickup_ka),
            "r1_island_far": sensitivity(islanded_far, r1_island.pickup_ka),
        },
        "times_s": {
            "r1_near": t_r1_near,
            "r2_near": t_r2_near,
            "r1_far": t_r1_far,
            "r2_far": t_r2_far,
        },
        "coordination": {
            "cti_target_s": 0.30,
            "margin_near_s": margin_near,
            "margin_far_s": margin_far,
            "min_margin_s": min(margin_near, margin_far),
            "pass": min(margin_near, margin_far) >= 0.30,
        },
        "grounding": {
            "ground_fault_a": ground_current_a,
            "zero_seq_pickup_a": ground_pickup_a,
            "sensitivity": ground_current_a / ground_pickup_a,
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
    print("Protection-coordination demo (synthetic, D-level, 10 kV / 100 MVA)")
    print(f"  grid fault near / far   {result['grid_near']['i_ka']:.3f} / {result['grid_far']['i_ka']:.3f} kA")
    print(f"  islanded near / far     {result['islanded']['near_ka']:.3f} / {result['islanded']['far_ka']:.3f} kA")
    print(f"  R1 pickup grid/island   {result['relays']['r1_grid_pickup_ka']:.2f} / {result['relays']['r1_island_pickup_ka']:.2f} kA")
    print(f"  island load {result['island_load']['load_mw']:.1f} MW -> {result['island_load']['current_ka']:.3f} kA, R1 pickup {result['island_load']['r1_pickup_ka']:.2f} kA")
    print(f"  R1 sensitivity far  grid/island {result['sensitivity']['r1_grid_far']:.2f} / {result['sensitivity']['r1_island_far']:.2f}")
    print(f"  R1 sensitivity near grid/island {result['sensitivity']['r1_grid_near']:.2f} / {result['sensitivity']['r1_island_near']:.2f}")
    print(f"  near-fault times        R1 {result['times_s']['r1_near']:.3f} s, R2 {result['times_s']['r2_near']:.3f} s")
    print(f"  far-fault times         R1 {result['times_s']['r1_far']:.3f} s, R2 {result['times_s']['r2_far']:.3f} s")
    print(f"  minimum CTI             {result['coordination']['min_margin_s']:.3f} s")
    print(f"  ground-fault sensitivity {result['grounding']['sensitivity']:.1f}")


if __name__ == "__main__":
    main()