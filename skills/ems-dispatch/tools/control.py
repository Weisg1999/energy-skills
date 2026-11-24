"""Deterministic AGC/AVC reference calculations for the synthetic example.

The module is intentionally small and dependency-free. It is not a dispatch
engine, a market tool or an assessment calculator.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass


EPS = 1e-9


@dataclass(frozen=True)
class AgcUnit:
    name: str
    reg_up_mw: float
    ramp_mw_min: float
    participation_factor: float = 1.0
    horizon_min: float = 5.0

    @property
    def capacity_mw(self) -> float:
        return min(self.reg_up_mw, self.ramp_mw_min * self.horizon_min)


@dataclass(frozen=True)
class AvcResource:
    name: str
    q_max_mvar: float
    priority: int = 1
    q_min_mvar: float = 0.0
    current_q_mvar: float = 0.0


def ace_mw(
    scheduled_export_mw: float,
    actual_export_mw: float,
    frequency_hz: float,
    bias_mw_per_hz: float,
    nominal_hz: float = 50.0,
) -> float:
    """Area control error with positive = the area is short of generation."""
    return (scheduled_export_mw - actual_export_mw) + bias_mw_per_hz * (
        nominal_hz - frequency_hz
    )


def agc_allocate(total_mw: float, units: list[AgcUnit]) -> dict:
    """Allocate by regulation range x participation factor, capped by ramp."""
    if total_mw < 0:
        raise ValueError("total_mw must be non-negative")
    allocations = {u.name: 0.0 for u in units}
    remaining = float(total_mw)

    for _ in range(len(units) + 1):
        active = [
            u
            for u in units
            if u.capacity_mw - allocations[u.name] > EPS
            and u.participation_factor > 0
        ]
        if not active or remaining <= EPS:
            break
        weights = {
            u.name: u.reg_up_mw * u.participation_factor for u in active
        }
        total_weight = sum(weights.values())
        if total_weight <= EPS:
            break
        moved = 0.0
        for u in active:
            room = u.capacity_mw - allocations[u.name]
            proposal = remaining * weights[u.name] / total_weight
            add = min(room, proposal)
            allocations[u.name] += add
            moved += add
        remaining -= moved
        if moved <= EPS:
            break

    rows = [
        {
            "name": u.name,
            "mw": allocations[u.name],
            "capacity_mw": u.capacity_mw,
            "weight": u.reg_up_mw * u.participation_factor,
        }
        for u in units
    ]
    allocated = sum(allocations.values())
    return {
        "requested_mw": total_mw,
        "allocations": rows,
        "allocated_mw": allocated,
        "unmet_mw": max(0.0, total_mw - allocated),
        "feasible": total_mw - allocated <= EPS,
    }


def agc_performance(
    target_mw: float,
    actual_mw: float,
    response_time_s: float,
    ramp_mw_min: float,
    required_ramp_mw_min: float,
    response_limit_s: float = 15.0,
    delivery_ratio: float = 0.95,
) -> dict:
    """Return separate response, ramp, accuracy and delivery indicators."""
    if target_mw <= 0:
        raise ValueError("target_mw must be positive")
    if required_ramp_mw_min <= 0:
        raise ValueError("required_ramp_mw_min must be positive")
    accuracy = 1.0 - abs(actual_mw - target_mw) / target_mw
    ramp_ratio = ramp_mw_min / required_ramp_mw_min
    return {
        "target_mw": target_mw,
        "actual_mw": actual_mw,
        "accuracy": accuracy,
        "ramp_ratio": ramp_ratio,
        "response_time_s": response_time_s,
        "response_ok": response_time_s <= response_limit_s,
        "delivery_ok": actual_mw >= delivery_ratio * target_mw,
    }


def avc_allocate(required_q_mvar: float, resources: list[AvcResource]) -> dict:
    """Allocate reactive power by priority, respecting each resource's range."""
    ordered = sorted(resources, key=lambda r: (r.priority, r.name))
    allocations = {r.name: 0.0 for r in resources}
    remaining = float(required_q_mvar)

    if remaining >= 0:
        for r in ordered:
            room = max(0.0, r.q_max_mvar - max(r.current_q_mvar, r.q_min_mvar))
            add = min(room, remaining)
            allocations[r.name] = add
            remaining -= add
            if remaining <= EPS:
                break
    else:
        for r in ordered:
            room = max(0.0, r.current_q_mvar - r.q_min_mvar)
            add = min(room, -remaining)
            allocations[r.name] = -add
            remaining += add
            if remaining >= -EPS:
                break

    rows = [
        {
            "name": r.name,
            "mvar": allocations[r.name],
            "q_min_mvar": r.q_min_mvar,
            "q_max_mvar": r.q_max_mvar,
            "priority": r.priority,
        }
        for r in resources
    ]
    allocated = sum(allocations.values())
    return {
        "requested_mvar": required_q_mvar,
        "allocations": rows,
        "allocated_mvar": allocated,
        "unmet_mvar": required_q_mvar - allocated,
        "feasible": abs(required_q_mvar - allocated) <= EPS,
    }


def droop_response(
    reserve_mw: float,
    droop_pct: float,
    delta_f_hz: float,
    deadband_hz: float = 0.03,
    nominal_hz: float = 50.0,
) -> float:
    """Primary-frequency response for a symmetric droop and deadband."""
    if reserve_mw < 0 or droop_pct <= 0 or deadband_hz < 0:
        raise ValueError("invalid droop parameters")
    effective = max(0.0, abs(delta_f_hz) - deadband_hz)
    full_delta = droop_pct / 100.0 * nominal_hz
    return min(reserve_mw, reserve_mw * effective / full_delta)


def demo() -> dict:
    ace = ace_mw(100.0, 80.0, 49.95, 400.0)
    units = [
        AgcUnit("coal-A", 40.0, 6.0, 0.6, 5.0),
        AgcUnit("storage-B", 20.0, 10.0, 0.4, 5.0),
    ]
    agc = agc_allocate(ace, units)
    perf_a = agc_performance(30.0, 28.5, 12.0, 5.7, 6.0)
    perf_b = agc_performance(10.0, 10.2, 3.0, 10.0, 10.0)
    avc = avc_allocate(
        60.0,
        [
            AvcResource("pv", 30.0, priority=1),
            AvcResource("svg", 40.0, priority=2),
            AvcResource("storage", 20.0, priority=3),
        ],
    )
    return {
        "ace": {
            "scheduled_export_mw": 100.0,
            "actual_export_mw": 80.0,
            "frequency_hz": 49.95,
            "bias_mw_per_hz": 400.0,
            "ace_mw": ace,
        },
        "agc": agc,
        "performance": {"coal-A": perf_a, "storage-B": perf_b},
        "avc": avc,
        "droop": {
            "reserve_mw": 20.0,
            "droop_pct": 2.0,
            "delta_f_hz": -0.10,
            "deadband_hz": 0.03,
            "response_mw": droop_response(20.0, 2.0, -0.10, 0.03),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()
    data = demo()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"ACE = {data['ace']['ace_mw']:.2f} MW")
    for row in data["agc"]["allocations"]:
        print(
            f"AGC {row['name']:<10} {row['mw']:.2f} MW "
            f"(capacity {row['capacity_mw']:.2f}, weight {row['weight']:.2f})"
        )
    print(f"AGC unmet = {data['agc']['unmet_mw']:.2f} MW")
    for name, row in data["performance"].items():
        print(
            f"{name:<10} accuracy={row['accuracy']:.3f} "
            f"ramp_ratio={row['ramp_ratio']:.3f} "
            f"response_ok={row['response_ok']} delivery_ok={row['delivery_ok']}"
        )
    for row in data["avc"]["allocations"]:
        print(f"AVC {row['name']:<10} {row['mvar']:.2f} Mvar")
    print(f"AVC unmet = {data['avc']['unmet_mvar']:.2f} Mvar")
    print(f"Primary-frequency response = {data['droop']['response_mw']:.2f} MW")


if __name__ == "__main__":
    main()