"""Pre-tax levelised cost of electricity for renewable projects.

Standard library only. The result is a screening metric: it excludes financing
structure, tax shields and provincial settlement rules. Use the after-tax cash
flow in finance.py for the investment decision.
"""

from __future__ import annotations


def lcoe(
    capex: float,
    opex_annual: float,
    annual_generation_mwh: float,
    life_years: int,
    discount_rate: float,
    degradation: float = 0.0,
    curtailment: float = 0.0,
    opex_escalation: float = 0.0,
    residual_value: float = 0.0,
) -> dict:
    """Levelised cost in CNY/MWh on a pre-tax basis.

    capex is a lump sum at t=0, opex starts in year 1, generation degrades
    geometrically, and residual_value is discounted at the end of life.
    """
    if life_years <= 0:
        raise ValueError("life_years must be positive")
    if not (0.0 <= curtailment < 1.0):
        raise ValueError("curtailment must be in [0, 1)")
    if not (0.0 <= degradation < 1.0):
        raise ValueError("degradation must be in [0, 1)")

    net_generation = annual_generation_mwh * (1.0 - curtailment)
    discounted_cost = capex
    discounted_energy = 0.0
    for year in range(1, life_years + 1):
        discount = (1.0 + discount_rate) ** year
        discounted_cost += opex_annual * (1.0 + opex_escalation) ** (year - 1) / discount
        discounted_energy += net_generation * (1.0 - degradation) ** (year - 1) / discount
    discounted_cost -= residual_value / (1.0 + discount_rate) ** life_years

    opex_pv = 0.0
    for year in range(1, life_years + 1):
        opex_pv += opex_annual * (1.0 + opex_escalation) ** (year - 1) / (1.0 + discount_rate) ** year
    capex_share = (capex - residual_value / (1.0 + discount_rate) ** life_years) / discounted_cost
    opex_share = opex_pv / discounted_cost

    return {
        "lcoe": discounted_cost / discounted_energy,
        "discounted_cost": discounted_cost,
        "discounted_energy_mwh": discounted_energy,
        "net_annual_generation_mwh": net_generation,
        "capex_share": capex_share,
        "opex_share": opex_share,
    }
