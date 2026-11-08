"""Bill construction: energy, pass-through charges, basic charge and power factor.

The line items follow the bill template in the knowledge module
``中国电价现行政策与查证-2026-11``. Every function is a pure calculator; the
caller supplies current provincial parameters.

Conventions
-----------
* Energy in kWh, power in kW or kVA, prices in CNY/kWh, CNY/kW/month or
  CNY/kVA/month, money in CNY.
* ``power_factor_adjustment`` uses a simplified two-slope schedule: 0.5% of the
  energy-side subtotal per 0.01 below 0.9, 0.15% per 0.01 above 0.9, with caps.
  Provinces use tiered schedules; replace the rates before quoting a result.
"""

from __future__ import annotations


def energy_charge(kwh, price):
    """Simple energy charge, CNY."""
    return float(kwh) * float(price)


def basic_charge_capacity(transformer_kva, price_per_kva_month):
    """Basic charge by transformer capacity."""
    transformer_kva = float(transformer_kva)
    if transformer_kva < 0:
        raise ValueError("transformer_kva must be non-negative")
    charge = transformer_kva * float(price_per_kva_month)
    return {
        "mode": "capacity",
        "billed_kw": transformer_kva,
        "over_kw": 0.0,
        "charge": charge,
    }


def basic_charge_demand(
    declared_kw,
    actual_max_kw,
    price_per_kw_month,
    threshold=1.05,
    overrun_multiplier=2.0,
    floor_kw=0.0,
):
    """Basic charge by contracted maximum demand.

    ``over = max(actual - threshold * declared, 0)`` and the charge is
    ``price * (declared + overrun_multiplier * over)``. ``floor_kw`` is the
    minimum declared demand allowed by the province (often 40% of transformer
    plus high-voltage motor capacity); pass 0 to disable it.
    """
    declared = max(float(declared_kw), float(floor_kw))
    if declared < 0:
        raise ValueError("declared_kw must be non-negative")
    actual = float(actual_max_kw)
    over = max(actual - float(threshold) * declared, 0.0)
    billed = declared + float(overrun_multiplier) * over
    return {
        "mode": "demand",
        "declared_kw": declared,
        "actual_max_kw": actual,
        "over_kw": over,
        "billed_kw": billed,
        "charge": billed * float(price_per_kw_month),
    }


def basic_charge_actual(actual_max_kw, price_per_kw_month):
    """Basic charge by actual maximum demand (no 105% penalty)."""
    actual = float(actual_max_kw)
    if actual < 0:
        raise ValueError("actual_max_kw must be non-negative")
    return {
        "mode": "actual",
        "actual_max_kw": actual,
        "billed_kw": actual,
        "over_kw": 0.0,
        "charge": actual * float(price_per_kw_month),
    }


def power_factor_adjustment(
    base_charge,
    pf,
    standard=0.9,
    penalty_per_step=0.005,
    reward_per_step=0.0015,
    max_penalty=0.15,
    max_reward=0.075,
):
    """Power-factor adjustment on the energy-side subtotal.

    ``pf`` is the monthly power factor; one step is 0.01. The result is the
    signed adjustment (positive means a surcharge) plus the multiplier.
    """
    pf = float(pf)
    if not 0.0 < pf <= 1.0:
        raise ValueError("pf must be in (0, 1]")
    base = float(base_charge)
    if pf < standard:
        steps = (standard - pf) / 0.01
        rate = min(steps * float(penalty_per_step), float(max_penalty))
    else:
        steps = (pf - standard) / 0.01
        rate = -min(steps * float(reward_per_step), float(max_reward))
    return {
        "pf": pf,
        "standard": float(standard),
        "rate": rate,
        "factor": 1.0 + rate,
        "adjustment": base * rate,
    }


def bill_breakdown(
    kwh_by_period,
    prices_by_period,
    transmission_price,
    system_price,
    fund_price,
    basic_fee,
    *,
    pf=None,
    pf_base=None,
    other_fees=0.0,
    pf_kwargs=None,
):
    """Assemble a monthly bill from energy, pass-through and basic charges.

    ``kwh_by_period`` and ``prices_by_period`` map tariff period to energy and
    price. ``pf_base`` overrides the base for the power-factor adjustment; by
    default it is the energy-side subtotal (energy, transmission, system and
    fund), which is the common convention.
    """
    energy = 0.0
    total_kwh = 0.0
    for name, kwh in kwh_by_period.items():
        if name not in prices_by_period:
            raise ValueError(f"missing price for period {name}")
        kwh = float(kwh)
        energy += kwh * float(prices_by_period[name])
        total_kwh += kwh
    if total_kwh <= 0:
        raise ValueError("total energy must be positive")
    transmission = total_kwh * float(transmission_price)
    system = total_kwh * float(system_price)
    fund = total_kwh * float(fund_price)
    subtotal = energy + transmission + system + fund + float(other_fees)
    adjustment = 0.0
    pf_detail = None
    if pf is not None:
        pf_detail = power_factor_adjustment(
            subtotal if pf_base is None else pf_base, pf, **(pf_kwargs or {})
        )
        adjustment = pf_detail["adjustment"]
    total = subtotal + float(basic_fee) + adjustment
    return {
        "total_kwh": total_kwh,
        "lines": {
            "energy": energy,
            "transmission": transmission,
            "system": system,
            "fund": fund,
            "other": float(other_fees),
            "subtotal": subtotal,
            "basic": float(basic_fee),
            "power_factor": adjustment,
        },
        "power_factor": pf_detail,
        "total": total,
        "average_price": total / total_kwh,
    }
