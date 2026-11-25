"""Deterministic SMIB transient-stability and inertia demo for the synthetic case.

The module is a teaching reference for equal-area critical clearing time, RK4
time-domain simulation, generation rejection and system RoCoF. It is not a
production dynamic-security program and carries no real grid data.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, replace


EPS = 1e-12


@dataclass(frozen=True)
class SmibCase:
    h: float = 5.0
    f0: float = 50.0
    pm_pre: float = 0.6
    pm_fault: float = 0.6
    pm_post: float = 0.6
    e_prime: float = 1.2
    u: float = 1.0
    x_pre: float = 0.4
    x_post: float = 0.8
    fault_power: float = 0.0
    t_clear: float = 0.45
    damping: float = 0.0
    horizon: float = 5.0
    step: float = 1e-3


def _omega_s(case: SmibCase) -> float:
    return 2.0 * math.pi * case.f0


def _inertia(case: SmibCase) -> float:
    return 2.0 * case.h / _omega_s(case)


def _pmax_pre(case: SmibCase) -> float:
    return case.e_prime * case.u / case.x_pre


def _pmax_post(case: SmibCase) -> float:
    return case.e_prime * case.u / case.x_post


def _angles(case: SmibCase) -> dict[str, float]:
    pmax_pre = _pmax_pre(case)
    pmax_post = _pmax_post(case)
    if not 0.0 <= case.pm_pre < pmax_pre:
        raise ValueError("pre-fault mechanical power outside the stable branch")
    if not 0.0 <= case.pm_post < pmax_post:
        raise ValueError("post-fault mechanical power outside the stable branch")
    delta0 = math.asin(case.pm_pre / pmax_pre)
    delta_sep = math.asin(case.pm_post / pmax_post)
    delta_max = math.pi - delta_sep
    return {
        "pmax_pre": pmax_pre,
        "pmax_post": pmax_post,
        "delta0_rad": delta0,
        "delta_sep_rad": delta_sep,
        "delta_max_rad": delta_max,
    }


def _area_balance(delta: float, case: SmibCase) -> float:
    angles = _angles(case)
    accel = (case.pm_fault - case.fault_power) * (delta - angles["delta0_rad"])
    decel = angles["pmax_post"] * (
        math.cos(delta) - math.cos(angles["delta_max_rad"])
    ) - case.pm_post * (angles["delta_max_rad"] - delta)
    return accel - decel


def equal_area(case: SmibCase) -> dict[str, float]:
    angles = _angles(case)
    delta0 = angles["delta0_rad"]
    delta_max = angles["delta_max_rad"]
    if case.pm_fault - case.fault_power <= EPS:
        raise ValueError("no accelerating area during the fault")
    low, high = delta0, delta_max
    for _ in range(200):
        mid = 0.5 * (low + high)
        if _area_balance(mid, case) > 0.0:
            high = mid
        else:
            low = mid
    delta_c = 0.5 * (low + high)
    m = _inertia(case)
    cct = math.sqrt(
        2.0 * m * (delta_c - delta0) / (case.pm_fault - case.fault_power)
    )
    accel = (case.pm_fault - case.fault_power) * (delta_c - delta0)
    decel = angles["pmax_post"] * (
        math.cos(delta_c) - math.cos(delta_max)
    ) - case.pm_post * (delta_max - delta_c)
    return {
        **angles,
        "inertia_s2": m,
        "delta_c_rad": delta_c,
        "delta_c_deg": math.degrees(delta_c),
        "delta0_deg": math.degrees(delta0),
        "delta_max_deg": math.degrees(delta_max),
        "accel_area_pu_rad": accel,
        "decel_area_pu_rad": decel,
        "margin_pu_rad": decel - accel,
        "cct_s": cct,
    }


def _derivative(state: tuple[float, float], case: SmibCase, phase: str) -> tuple[float, float]:
    delta, omega = state
    if phase == "pre":
        pm = case.pm_fault
        pe = case.fault_power
    else:
        pm = case.pm_post
        pe = _pmax_post(case) * math.sin(delta)
    d_delta = omega
    d_omega = (_omega_s(case) / (2.0 * case.h)) * (pm - pe) - case.damping * omega
    return d_delta, d_omega


def _rk4(
    state: tuple[float, float], case: SmibCase, phase: str, dt: float
) -> tuple[float, float]:
    k1 = _derivative(state, case, phase)
    s2 = (state[0] + 0.5 * dt * k1[0], state[1] + 0.5 * dt * k1[1])
    k2 = _derivative(s2, case, phase)
    s3 = (state[0] + 0.5 * dt * k2[0], state[1] + 0.5 * dt * k2[1])
    k3 = _derivative(s3, case, phase)
    s4 = (state[0] + dt * k3[0], state[1] + dt * k3[1])
    k4 = _derivative(s4, case, phase)
    return (
        state[0] + dt * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0]) / 6.0,
        state[1] + dt * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1]) / 6.0,
    )


def simulate(case: SmibCase) -> dict[str, float | bool]:
    angles = _angles(case)
    delta_max = angles["delta_max_rad"]
    delta, omega = angles["delta0_rad"], 0.0
    t = 0.0
    max_delta = delta
    max_omega = 0.0
    stable = True
    t_unstable = math.nan
    while t < case.horizon - EPS:
        phase = "pre" if t < case.t_clear - EPS else "post"
        dt = min(case.step, case.horizon - t)
        if phase == "pre" and t + dt > case.t_clear:
            dt = max(case.t_clear - t, EPS)
        delta, omega = _rk4((delta, omega), case, phase, dt)
        t += dt
        max_delta = max(max_delta, delta)
        max_omega = max(max_omega, abs(omega))
        if delta > delta_max and omega > 0.0:
            stable = False
            t_unstable = t
            break
    return {
        "stable": stable,
        "t_unstable_s": t_unstable,
        "delta_final_deg": math.degrees(delta),
        "delta_max_deg": math.degrees(max_delta),
        "omega_max_rad_s": max_omega,
        "t_end_s": t,
    }


def cct_by_simulation(case: SmibCase) -> float:
    high = min(case.horizon * 0.5, 2.0)
    while simulate(replace(case, t_clear=high))["stable"] and high < 3.0:
        high *= 1.5
    if simulate(replace(case, t_clear=high))["stable"]:
        return math.inf
    low = 0.0
    for _ in range(50):
        mid = 0.5 * (low + high)
        if simulate(replace(case, t_clear=mid))["stable"]:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def rocof(imbalance_mw: float, inertia_s: float, base_mva: float, f0: float = 50.0) -> float:
    if base_mva <= 0.0 or inertia_s <= 0.0:
        raise ValueError("base_mva and inertia_s must be positive")
    return -f0 * imbalance_mw / (2.0 * inertia_s * base_mva)


def inertia_sweep(
    imbalance_mw: float, base_mva: float, values: tuple[float, ...] = (2.0, 4.0, 6.0)
) -> list[dict[str, float]]:
    return [
        {"h_s": h, "rocof_hz_s": rocof(imbalance_mw, h, base_mva)}
        for h in values
    ]


def demo() -> dict:
    base = SmibCase()
    area = equal_area(base)
    early = simulate(replace(base, t_clear=0.30))
    late = simulate(replace(base, t_clear=0.45))
    sim_cct = cct_by_simulation(base)
    reject_case = replace(base, pm_fault=0.4, pm_post=0.4, t_clear=0.45)
    reject_area = equal_area(reject_case)
    reject_run = simulate(reject_case)
    return {
        "case": {
            "h_s": base.h,
            "f0_hz": base.f0,
            "pm_pre_pu": base.pm_pre,
            "pm_post_pu": base.pm_post,
            "x_pre_pu": base.x_pre,
            "x_post_pu": base.x_post,
            "fault_power_pu": base.fault_power,
        },
        "equal_area": area,
        "simulation": {
            "clear_030": early,
            "clear_045": late,
            "cct_s": sim_cct,
        },
        "generation_rejection": {
            "pm_fault_pu": reject_case.pm_fault,
            "pm_post_pu": reject_case.pm_post,
            "equal_area": reject_area,
            "run_045": reject_run,
        },
        "rocof": {
            "imbalance_mw": 1000.0,
            "base_mva": 100000.0,
            "reference_h_s": 4.0,
            "reference_hz_s": rocof(1000.0, 4.0, 100000.0),
            "sweep": inertia_sweep(1000.0, 100000.0),
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
    area = result["equal_area"]
    sim = result["simulation"]
    print("SMIB transient stability demo (synthetic, D-level)")
    print(f"  delta0        {area['delta0_deg']:.3f} deg")
    print(f"  delta_c       {area['delta_c_deg']:.3f} deg")
    print(f"  delta_max     {area['delta_max_deg']:.3f} deg")
    print(f"  equal-area CCT {area['cct_s']:.4f} s")
    print(f"  simulated CCT  {sim['cct_s']:.4f} s")
    print(f"  clear 0.30 s   {'stable' if sim['clear_030']['stable'] else 'unstable'}"
          f"  (max delta {sim['clear_030']['delta_max_deg']:.2f} deg)")
    print(f"  clear 0.45 s   {'stable' if sim['clear_045']['stable'] else 'unstable'}")
    rej = result["generation_rejection"]
    print(f"  rejection CCT  {rej['equal_area']['cct_s']:.4f} s")
    print(f"  rejection 0.45 s {'stable' if rej['run_045']['stable'] else 'unstable'}")
    rf = result["rocof"]
    print(f"  RoCoF          {rf['reference_hz_s']:.4f} Hz/s"
          f" for {rf['imbalance_mw']:.0f} MW on {rf['base_mva']:.0f} MVA, H={rf['reference_h_s']:.0f} s")
    for row in rf["sweep"]:
        print(f"    H={row['h_s']:.0f} s -> {row['rocof_hz_s']:.4f} Hz/s")


if __name__ == "__main__":
    main()