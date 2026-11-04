"""Revenue stacking for storage investment screening.

All functions use AC-side prices in CNY/MWh, power in MW and energy in MWh.
They are screening tools, not settlement engines: provincial rules, metering
points and contract terms must replace the defaults before any decision.
"""

from __future__ import annotations

import math


def _ac_energies(power_mw, duration_h, usable_ratio, rte):
    if power_mw <= 0 or duration_h <= 0:
        raise ValueError("power_mw and duration_h must be positive")
    if not 0 < rte <= 1:
        raise ValueError("rte must be in (0, 1]")
    if not 0 < usable_ratio <= 1:
        raise ValueError("usable_ratio must be in (0, 1]")
    usable_dc_mwh = power_mw * duration_h * usable_ratio
    one_way = math.sqrt(rte)
    return usable_dc_mwh, usable_dc_mwh * one_way, usable_dc_mwh / one_way


def arbitrage(
    power_mw,
    duration_h,
    rte,
    cycles_per_day,
    days,
    charge_price,
    discharge_price,
    usable_ratio=1.0,
    availability=1.0,
    degradation_cost_per_kwh=0.0,
):
    """Energy arbitrage with AC-side charging and discharging.

    usable_ratio applies to DC energy; one-way efficiency is sqrt(rte).
    ``days`` already carries availability when the caller uses operating days.
    """
    usable_dc, discharge_mwh, charge_mwh = _ac_energies(
        power_mw, duration_h, usable_ratio, rte
    )
    gross_per_cycle = discharge_mwh * discharge_price - charge_mwh * charge_price
    cycles = cycles_per_day * days * availability
    annual_gross = gross_per_cycle * cycles
    annual_throughput = (discharge_mwh + charge_mwh) * cycles
    annual_degradation_cost = annual_throughput * 1000 * degradation_cost_per_kwh
    return {
        "usable_dc_mwh": usable_dc,
        "discharge_mwh_per_cycle": discharge_mwh,
        "charge_mwh_per_cycle": charge_mwh,
        "gross_per_cycle": gross_per_cycle,
        "annual_gross": annual_gross,
        "annual_throughput_mwh": annual_throughput,
        "annual_degradation_cost": annual_degradation_cost,
        "annual_net": annual_gross - annual_degradation_cost,
    }


def capacity_payment(
    power_mw,
    price_per_kw_year,
    duration_h,
    peak_duration_h,
    availability=1.0,
):
    """Capacity payment under the 2026 national framework.

    Ratio = min(full-power duration / longest net-load peak duration, 1).
    The provincial price and denominator must be taken from the current
    provincial document; the defaults here are only an example.
    """
    if peak_duration_h <= 0:
        raise ValueError("peak_duration_h must be positive")
    ratio = min(duration_h / peak_duration_h, 1.0)
    annual = power_mw * 1000 * price_per_kw_year * ratio * availability
    return {"ratio": ratio, "annual": annual}


def demand_bill(setpoint_kw, actual_kw, price_per_kw_month):
    """Two-part basic tariff under contract maximum demand.

    Basic bill = price * (setpoint + 2 * over), where
    over = max(actual - 1.05 * setpoint, 0).
    """
    over_kw = max(actual_kw - 1.05 * setpoint_kw, 0.0)
    return {
        "over_kw": over_kw,
        "monthly": price_per_kw_month * (setpoint_kw + 2 * over_kw),
    }


def demand_savings(
    setpoint_kw,
    actual_before_kw,
    actual_after_kw,
    price_per_kw_month,
    months=12,
):
    """Savings from shaving the monthly maximum demand."""
    before = demand_bill(setpoint_kw, actual_before_kw, price_per_kw_month)
    after = demand_bill(setpoint_kw, actual_after_kw, price_per_kw_month)
    monthly = before["monthly"] - after["monthly"]
    return {
        "before": before,
        "after": after,
        "monthly": monthly,
        "annual": monthly * months,
    }


def frequency_regulation(
    capacity_mw,
    capacity_price_per_mw_h,
    mileage_mw_per_day,
    mileage_price_per_mw,
    k_factor,
    days,
    availability=1.0,
):
    """Frequency-regulation capacity plus mileage payment, before energy cost.

    The result is gross revenue. It is not additive to arbitrage without
    deducting reserved power/energy and the opportunity cost.
    """
    daily = capacity_mw * capacity_price_per_mw_h * 24
    daily += mileage_mw_per_day * mileage_price_per_mw * k_factor
    annual = daily * days * availability
    return {"daily": daily, "annual": annual}


def stack(items, haircut=0.0):
    """Sum revenue items and apply a single haircut for overlap/availability."""
    if not 0 <= haircut < 1:
        raise ValueError("haircut must be in [0, 1)")
    gross = sum(items.values())
    return {"gross": gross, "haircut": haircut, "net": gross * (1 - haircut)}
