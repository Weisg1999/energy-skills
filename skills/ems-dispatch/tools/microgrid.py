"""Microgrid-side dispatch wrapper and island feasibility checks.

Units: kW, kWh, CNY/kWh. The wrapper adds the microgrid-specific defaults
(no export, PCC import limit, PV curtailment) on top of ``dispatch.py``.
"""

from __future__ import annotations

import dispatch


def microgrid_day(
    load_kw,
    pv_kw,
    buy_price,
    *,
    sell_price=None,
    capacity_kwh,
    power_charge_kw,
    power_discharge_kw,
    eta_charge=0.95,
    eta_discharge=0.95,
    soc_min=0.2,
    soc_max=0.95,
    soc_init=None,
    dt_h=0.25,
    pcc_import_kw=None,
    pcc_export_kw=0.0,
    reserve_up_kw=0.0,
    reserve_dn_kw=0.0,
    reserve_hours=1.0,
    degradation_per_kwh=0.0,
    terminal="cycle",
    states=200,
):
    """One-day microgrid schedule with PV curtailment and PCC limits."""
    return dispatch.dispatch_day(
        buy_price,
        load_kw,
        pv_kw,
        sell_price=sell_price,
        capacity_kwh=capacity_kwh,
        power_charge_kw=power_charge_kw,
        power_discharge_kw=power_discharge_kw,
        eta_charge=eta_charge,
        eta_discharge=eta_discharge,
        soc_min=soc_min,
        soc_max=soc_max,
        soc_init=soc_init,
        dt_h=dt_h,
        pcc_import_kw=pcc_import_kw,
        pcc_export_kw=pcc_export_kw,
        reserve_up_kw=reserve_up_kw,
        reserve_dn_kw=reserve_dn_kw,
        reserve_hours=reserve_hours,
        degradation_per_kwh=degradation_per_kwh,
        terminal=terminal,
        states=states,
    )


def baseline_day(
    load_kw,
    pv_kw,
    buy_price,
    *,
    sell_price=None,
    dt_h=0.25,
    pcc_import_kw=None,
    pcc_export_kw=0.0,
):
    """Counterfactual without storage, with the same PCC and curtailment rules."""
    return dispatch.baseline_day(
        buy_price,
        load_kw,
        pv_kw,
        sell_price=sell_price,
        dt_h=dt_h,
        pcc_import_kw=pcc_import_kw,
        pcc_export_kw=pcc_export_kw,
    )


def net_load(load_kw, pv_kw):
    """Load minus PV, interval by interval."""
    return [float(load) - float(pv) for load, pv in zip(load_kw, pv_kw)]


def island_energy_need(load_kw, dt_h=0.25):
    """Energy required by a given island load profile."""
    return sum(float(p) for p in load_kw) * float(dt_h)


def island_feasible(available_kwh, need_kwh, *, reserve_ratio=0.0):
    """Check available energy against island load plus a reserve margin."""
    available_kwh = float(available_kwh)
    need_kwh = float(need_kwh)
    required = need_kwh * (1.0 + float(reserve_ratio))
    return {
        "available_kwh": available_kwh,
        "need_kwh": need_kwh,
        "required_kwh": required,
        "margin_kwh": available_kwh - required,
        "feasible": available_kwh >= required,
    }


def island_window(load_kw, start_index, end_index, dt_h=0.25, reserve_ratio=0.0):
    """Energy need for a half-open island window ``[start, end)``."""
    if start_index < 0 or end_index > len(load_kw) or start_index >= end_index:
        raise ValueError("invalid island window")
    need = island_energy_need(load_kw[start_index:end_index], dt_h)
    return {
        "need_kwh": need,
        "required_kwh": need * (1.0 + float(reserve_ratio)),
        "intervals": end_index - start_index,
    }
