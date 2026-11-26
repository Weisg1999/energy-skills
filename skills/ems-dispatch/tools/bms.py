"""Deterministic BMS/EMS state-boundary demo for a synthetic 100 MW/200 MWh BESS.

Covers coulomb counting, OCV correction, SOH fade, SOP derating and passive
balancing time. All parameters are teaching assumptions, not a product datasheet.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

OCV_TABLE = (
    (0.0, 2.80),
    (10.0, 3.20),
    (20.0, 3.25),
    (30.0, 3.28),
    (40.0, 3.30),
    (50.0, 3.31),
    (60.0, 3.32),
    (70.0, 3.33),
    (80.0, 3.34),
    (90.0, 3.40),
    (100.0, 3.65),
)


@dataclass(frozen=True)
class BatterySpec:
    rated_mw: float
    energy_mwh: float
    capacity_ah: float
    cell_nominal_v: float = 3.2
    soc_min_pct: float = 10.0
    soc_max_pct: float = 90.0


def coulomb_soc(soc0_pct: float, current_a: float, hours: float, capacity_ah: float) -> float:
    if capacity_ah <= 0:
        raise ValueError("capacity must be positive")
    return soc0_pct - current_a * hours / capacity_ah * 100.0


def ocv_soc(voltage_v: float, table: tuple[tuple[float, float], ...] = OCV_TABLE) -> float:
    points = sorted(table, key=lambda p: p[1])
    if voltage_v <= points[0][1]:
        return points[0][0]
    if voltage_v >= points[-1][1]:
        return points[-1][0]
    for (soc_lo, v_lo), (soc_hi, v_hi) in zip(points, points[1:]):
        if v_lo <= voltage_v <= v_hi:
            return soc_lo + (voltage_v - v_lo) / (v_hi - v_lo) * (soc_hi - soc_lo)
    raise AssertionError("unreachable")


def soh_pct(
    cycles: float,
    years: float,
    cycle_fade_pct_per_1000: float = 1.5,
    calendar_fade_pct_per_year: float = 2.0,
) -> float:
    return 100.0 - cycle_fade_pct_per_1000 * cycles / 1000.0 - calendar_fade_pct_per_year * years


def remaining_capacity_ah(spec: BatterySpec, soh: float) -> float:
    return spec.capacity_ah * soh / 100.0


def sop_mw(
    spec: BatterySpec,
    soc_pct: float,
    temp_c: float,
    horizon_h: float,
    c_rate_max: float = 0.5,
    temp_derate_start_c: float = 35.0,
    temp_derate_per_c: float = 0.03,
) -> dict[str, float]:
    if horizon_h <= 0:
        raise ValueError("horizon must be positive")
    headroom_mwh = max(0.0, (soc_pct - spec.soc_min_pct) / 100.0 * spec.energy_mwh)
    energy_limit_mw = headroom_mwh / horizon_h
    power_limit_mw = min(spec.rated_mw, c_rate_max * spec.energy_mwh)
    temp_factor = max(0.0, 1.0 - temp_derate_per_c * max(0.0, temp_c - temp_derate_start_c))
    thermal_limit_mw = power_limit_mw * temp_factor
    return {
        "headroom_mwh": headroom_mwh,
        "energy_limit_mw": energy_limit_mw,
        "power_limit_mw": power_limit_mw,
        "temp_factor": temp_factor,
        "thermal_limit_mw": thermal_limit_mw,
        "sop_mw": min(energy_limit_mw, thermal_limit_mw),
    }


def balance_time_h(
    cell_voltages_v: tuple[float, ...],
    capacity_ah: float,
    balance_current_ma: float,
    cell_nominal_v: float = 3.2,
    mv_per_soc_pct: float = 0.25,
) -> dict[str, float]:
    if len(cell_voltages_v) < 2:
        raise ValueError("need at least two cells")
    delta_mv = (max(cell_voltages_v) - min(cell_voltages_v)) * 1000.0
    delta_soc_pct = delta_mv * mv_per_soc_pct
    excess_wh = delta_soc_pct / 100.0 * capacity_ah * cell_nominal_v
    power_w = balance_current_ma / 1000.0 * cell_nominal_v
    return {
        "delta_mv": delta_mv,
        "delta_soc_pct": delta_soc_pct,
        "excess_wh": excess_wh,
        "balance_power_w": power_w,
        "balance_time_h": excess_wh / power_w if power_w > 0 else float("inf"),
    }


def demo() -> dict:
    spec = BatterySpec(rated_mw=100.0, energy_mwh=200.0, capacity_ah=280.0)
    soc_coulomb = coulomb_soc(50.0, 100.0, 1.0, spec.capacity_ah)
    soc_ocv = ocv_soc(3.225)
    soh = soh_pct(cycles=600.0, years=2.0)
    capacity = remaining_capacity_ah(spec, soh)

    sop_healthy = sop_mw(spec, soc_pct=40.0, temp_c=25.0, horizon_h=0.5)
    sop_hot = sop_mw(spec, soc_pct=40.0, temp_c=45.0, horizon_h=0.5)
    sop_low = sop_mw(spec, soc_pct=15.0, temp_c=25.0, horizon_h=0.5)

    voltages = (
        3.330, 3.328, 3.326, 3.324, 3.322, 3.320, 3.318, 3.316,
        3.314, 3.312, 3.310, 3.308, 3.306, 3.304, 3.302, 3.290,
    )
    balance = balance_time_h(voltages, spec.capacity_ah, balance_current_ma=100.0)

    return {
        "spec": {
            "rated_mw": spec.rated_mw,
            "energy_mwh": spec.energy_mwh,
            "capacity_ah": spec.capacity_ah,
            "soc_min_pct": spec.soc_min_pct,
            "soc_max_pct": spec.soc_max_pct,
        },
        "soc": {
            "coulomb_pct": soc_coulomb,
            "ocv_pct": soc_ocv,
            "ocv_correction_pct": soc_ocv - soc_coulomb,
        },
        "soh": {
            "pct": soh,
            "remaining_capacity_ah": capacity,
            "cycle_fade_pct": 1.5 * 600.0 / 1000.0,
            "calendar_fade_pct": 2.0 * 2.0,
        },
        "energy": {
            "capacity_corrected_mwh": spec.energy_mwh * soh / 100.0,
            "usable_window_mwh": spec.energy_mwh * soh / 100.0 * (spec.soc_max_pct - spec.soc_min_pct) / 100.0,
            "discharge_from_50pct_mwh": spec.energy_mwh * soh / 100.0 * (50.0 - spec.soc_min_pct) / 100.0,
        },
        "sop": {
            "healthy_25c": sop_healthy,
            "hot_45c": sop_hot,
            "low_soc_15pct": sop_low,
        },
        "balance": balance,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    result = demo()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("BMS/EMS state-boundary demo (synthetic, D-level, 100 MW / 200 MWh)")
    print(f"  SOC coulomb / OCV      {result['soc']['coulomb_pct']:.3f}% / {result['soc']['ocv_pct']:.3f}%")
    print(f"  OCV correction         {result['soc']['ocv_correction_pct']:+.3f} pp")
    print(f"  SOH after 600 cycles / 2 y {result['soh']['pct']:.2f}%")
    print(f"  usable energy window   {result['energy']['usable_window_mwh']:.1f} MWh (from 50% SOC: {result['energy']['discharge_from_50pct_mwh']:.1f} MWh)")
    print(f"  SOP 25 C / 45 C        {result['sop']['healthy_25c']['sop_mw']:.1f} / {result['sop']['hot_45c']['sop_mw']:.1f} MW")
    print(f"  SOP at 15% SOC         {result['sop']['low_soc_15pct']['sop_mw']:.1f} MW")
    print(f"  passive balancing      {result['balance']['balance_time_h']:.1f} h")


if __name__ == "__main__":
    main()