"""Storage-side screening calculations and a day-ahead dispatch wrapper.

The analytic helpers reproduce the hand calculations used in the knowledge
drafts (AC-side energy, one-way efficiency, capacity payment, demand bill).
``station_day`` delegates the time-coupled schedule to ``dispatch.py``.

Conventions
-----------
* ``arbitrage_cycle`` / ``station_day``: power in MW, energy in MWh, prices in
  CNY/MWh, cost in CNY.
* ``capability``: power in kW, energy in kWh.
* One-way efficiency is ``sqrt(round-trip efficiency)``; usable DC energy is
  not AC discharge energy (they differ by one factor of eta).
"""

from __future__ import annotations

import math

import dispatch


def _eta(rte):
    rte = float(rte)
    if not 0 < rte <= 1:
        raise ValueError("rte must be in (0, 1]")
    return math.sqrt(rte)


def arbitrage_cycle(
    usable_dc_mwh,
    rte,
    charge_price,
    discharge_price,
    degradation_per_kwh=0.0,
):
    """One full cycle, AC-side revenue and cost.

    ``usable_dc_mwh`` is the energy available inside the SOC window, not the
    nameplate energy and not the AC discharge energy.
    """
    usable_dc_mwh = float(usable_dc_mwh)
    if usable_dc_mwh <= 0:
        raise ValueError("usable_dc_mwh must be positive")
    eta = _eta(rte)
    discharge_mwh = usable_dc_mwh * eta
    charge_mwh = usable_dc_mwh / eta
    revenue = discharge_mwh * float(discharge_price)
    charge_cost = charge_mwh * float(charge_price)
    gross = revenue - charge_cost
    throughput = charge_mwh + discharge_mwh
    degradation = throughput * 1000.0 * float(degradation_per_kwh)
    return {
        "usable_dc_mwh": usable_dc_mwh,
        "eta_one_way": eta,
        "discharge_mwh": discharge_mwh,
        "charge_mwh": charge_mwh,
        "revenue": revenue,
        "charge_cost": charge_cost,
        "gross": gross,
        "throughput_mwh": throughput,
        "degradation_cost": degradation,
        "net": gross - degradation,
    }


def station_day(
    prices_per_mwh,
    power_mw,
    energy_mwh,
    rte,
    *,
    sell_prices_per_mwh=None,
    soc_min=0.1,
    soc_max=0.9,
    soc_init=None,
    dt_h=1.0,
    pcc_import_mw=None,
    pcc_export_mw=None,
    degradation_per_kwh=0.0,
    reserve_up_mw=0.0,
    reserve_dn_mw=0.0,
    terminal="cycle",
    states=400,
):
    """Grid-side storage day-ahead schedule, returned in MW and MWh.

    ``sell_prices_per_mwh`` defaults to the buy series, which is the usual
    grid-side assumption when the station is paid the same TOU price for
    discharge; pass a discounted or market price when the settlement differs.
    """
    eta = _eta(rte)
    prices = [float(p) / 1000.0 for p in prices_per_mwh]
    if sell_prices_per_mwh is None:
        sell = list(prices)
    else:
        sell = [float(p) / 1000.0 for p in sell_prices_per_mwh]
    result = dispatch.dispatch_day(
        prices,
        [0.0] * len(prices),
        [0.0] * len(prices),
        sell_price=sell,
        capacity_kwh=float(energy_mwh) * 1000.0,
        power_charge_kw=float(power_mw) * 1000.0,
        power_discharge_kw=float(power_mw) * 1000.0,
        eta_charge=eta,
        eta_discharge=eta,
        soc_min=float(soc_min),
        soc_max=float(soc_max),
        soc_init=soc_init,
        dt_h=float(dt_h),
        pcc_import_kw=None if pcc_import_mw is None else float(pcc_import_mw) * 1000.0,
        pcc_export_kw=1e9 if pcc_export_mw is None else float(pcc_export_mw) * 1000.0,
        reserve_up_kw=float(reserve_up_mw) * 1000.0,
        reserve_dn_kw=float(reserve_dn_mw) * 1000.0,
        degradation_per_kwh=float(degradation_per_kwh),
        terminal=terminal,
        states=states,
    )
    if not result["feasible"]:
        return result
    schedule = result["schedule"]
    result["schedule"] = {
        "p_charge_mw": [v / 1000.0 for v in schedule["p_charge_kw"]],
        "p_discharge_mw": [v / 1000.0 for v in schedule["p_discharge_kw"]],
        "p_import_mw": [v / 1000.0 for v in schedule["p_import_kw"]],
        "p_export_mw": [v / 1000.0 for v in schedule["p_export_kw"]],
        "soc": schedule["soc"],
    }
    result["throughput_mwh"] = result["throughput_kwh"] / 1000.0
    result["peak_import_mw"] = result["peak_import_kw"] / 1000.0
    result["net_revenue"] = -result["cost"]
    return result


def curtailment_charge(
    ac_charge_mwh,
    rte,
    discharge_price,
    *,
    degradation_per_kwh=0.0,
    charge_cost_per_mwh=0.0,
    usable_dc_mwh=None,
    power_mw=None,
    hours=None,
):
    """Charge from otherwise-curtailed renewable energy.

    The AC charging energy is limited by ``power_mw * hours`` when both are
    supplied, and the stored DC energy must fit ``usable_dc_mwh``.
    """
    ac_charge_mwh = float(ac_charge_mwh)
    if power_mw is not None and hours is not None:
        ac_charge_mwh = min(ac_charge_mwh, float(power_mw) * float(hours))
    if ac_charge_mwh < 0:
        raise ValueError("ac_charge_mwh must be non-negative")
    eta = _eta(rte)
    stored_mwh = ac_charge_mwh * eta
    feasible = usable_dc_mwh is None or stored_mwh <= float(usable_dc_mwh) + 1e-9
    if not feasible:
        stored_mwh = float(usable_dc_mwh)
        ac_charge_mwh = stored_mwh / eta
    discharge_mwh = stored_mwh * eta
    revenue = discharge_mwh * float(discharge_price)
    charge_cost = ac_charge_mwh * float(charge_cost_per_mwh)
    throughput = ac_charge_mwh + discharge_mwh
    degradation = throughput * 1000.0 * float(degradation_per_kwh)
    return {
        "ac_charge_mwh": ac_charge_mwh,
        "stored_dc_mwh": stored_mwh,
        "discharge_mwh": discharge_mwh,
        "revenue": revenue,
        "charge_cost": charge_cost,
        "throughput_mwh": throughput,
        "degradation_cost": degradation,
        "net": revenue - charge_cost - degradation,
        "feasible_within_energy": feasible,
    }


def capability(
    pcs_kw,
    capacity_kwh,
    *,
    bms_kw=None,
    pcc_kw=None,
    derate=1.0,
    soh=1.0,
    soc_min=0.0,
    soc_max=1.0,
):
    """Available power, energy and duration for market qualification."""
    limits = [float(pcs_kw)]
    if bms_kw is not None:
        limits.append(float(bms_kw))
    if pcc_kw is not None:
        limits.append(float(pcc_kw))
    power = min(limits) * float(derate) * float(soh)
    energy = (float(soc_max) - float(soc_min)) * float(capacity_kwh) * float(soh)
    if power <= 0:
        raise ValueError("available power must be positive")
    return {
        "available_power_kw": power,
        "available_energy_kwh": energy,
        "duration_h": energy / power,
    }


def degradation_cost(throughput_mwh, price_per_kwh):
    """Linear throughput degradation cost."""
    return float(throughput_mwh) * 1000.0 * float(price_per_kwh)
