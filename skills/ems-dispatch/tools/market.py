"""Market-side revenue and bill calculations used in the EMS worked examples.

These are screening formulas, not settlement engines. Province-level rules
(denominator duration, availability threshold, demand-charge basis, mileage
price and K-factor) must replace the defaults before publication.
"""

from __future__ import annotations


def capacity_payment(
    power_mw,
    price_per_kw_year,
    duration_h,
    denominator_h,
    *,
    availability=1.0,
    cap_ratio=1.0,
):
    """Capacity payment with duration scaling and availability.

    The ratio is ``min(duration_h / denominator_h, cap_ratio)``; 114号文 caps
    the ratio at 1x, while the provincial denominator (4/6/8/10 h) still has to
    be checked against the current local document.
    """
    if float(power_mw) < 0:
        raise ValueError("power_mw must be non-negative")
    if float(denominator_h) <= 0:
        raise ValueError("denominator_h must be positive")
    ratio = min(float(duration_h) / float(denominator_h), float(cap_ratio))
    annual = (
        float(price_per_kw_year)
        * float(power_mw)
        * 1000.0
        * ratio
        * float(availability)
    )
    return {
        "ratio": ratio,
        "annual": annual,
        "daily": annual / 365.0,
        "monthly": annual / 12.0,
    }


def frequency_regulation(
    capacity_mw,
    capacity_price_per_mw_h,
    hours,
    mileage_mw,
    mileage_price_per_mw,
    k_factor=1.0,
    *,
    performance_factor=1.0,
):
    """Frequency-regulation capacity plus mileage revenue for one day."""
    if float(capacity_mw) < 0 or float(mileage_mw) < 0:
        raise ValueError("capacities must be non-negative")
    capacity_revenue = (
        float(capacity_price_per_mw_h)
        * float(capacity_mw)
        * float(hours)
    )
    mileage_revenue = (
        float(mileage_price_per_mw)
        * float(mileage_mw)
        * float(k_factor)
        * float(performance_factor)
    )
    return {
        "capacity_revenue": capacity_revenue,
        "mileage_revenue": mileage_revenue,
        "total": capacity_revenue + mileage_revenue,
    }


def demand_bill(setpoint_kw, peak_kw, price_per_kw_month, *, overrun_multiplier=2.0):
    """Two-part basic tariff with the common 105% demand overrun rule.

    Bill = price * (setpoint + multiplier * max(0, peak - 1.05*setpoint)).
    A peak below the setpoint is billed at the setpoint; export never offsets
    demand. Confirm the local basis (15-min average import, contract demand or
    transformer capacity) before using the result.
    """
    setpoint_kw = float(setpoint_kw)
    peak_kw = float(peak_kw)
    if setpoint_kw < 0:
        raise ValueError("setpoint_kw must be non-negative")
    threshold = 1.05 * setpoint_kw
    over_kw = max(0.0, peak_kw - threshold)
    billed_kw = setpoint_kw + float(overrun_multiplier) * over_kw
    return {
        "setpoint_kw": setpoint_kw,
        "peak_kw": peak_kw,
        "over_kw": over_kw,
        "billed_kw": billed_kw,
        "monthly": billed_kw * float(price_per_kw_month),
    }


def demand_saving(setpoint_kw, peak_before_kw, peak_after_kw, price_per_kw_month):
    """Monthly saving from shaving the peak, holding the setpoint fixed."""
    before = demand_bill(setpoint_kw, peak_before_kw, price_per_kw_month)
    after = demand_bill(setpoint_kw, peak_after_kw, price_per_kw_month)
    return {
        "before": before,
        "after": after,
        "monthly": before["monthly"] - after["monthly"],
        "daily": (before["monthly"] - after["monthly"]) / 30.0,
    }
