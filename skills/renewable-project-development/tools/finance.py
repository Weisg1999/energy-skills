"""After-tax project cash flow and debt metrics.

Standard library only. Simple straight-line depreciation and a single tax rate;
no loss carry-forward, tax holidays or accelerated depreciation.
"""

from __future__ import annotations


def project_cashflow(
    revenue: float,
    opex: float,
    capex: float,
    life_years: int,
    tax_rate: float = 0.25,
    depreciation_years: int | None = None,
    revenue_degradation: float = 0.0,
    opex_escalation: float = 0.0,
    residual_value: float = 0.0,
) -> list:
    """Annual after-tax cash flow, with capex at t=0."""
    if life_years <= 0:
        raise ValueError("life_years must be positive")
    dep_years = depreciation_years or life_years
    depreciation = capex / dep_years
    flows = [-capex]
    for year in range(1, life_years + 1):
        gross = revenue * (1.0 - revenue_degradation) ** (year - 1)
        cost = opex * (1.0 + opex_escalation) ** (year - 1)
        deductible = depreciation if year <= dep_years else 0.0
        taxable = max(gross - cost - deductible, 0.0)
        flows.append(gross - cost - taxable * tax_rate)
    flows[-1] += residual_value
    return flows


def npv(rate: float, flows: list) -> float:
    return sum(flow / (1.0 + rate) ** year for year, flow in enumerate(flows))


def irr(flows: list, low: float = -0.99, high: float = 1.0, iterations: int = 200) -> float:
    """IRR by bisection; requires a sign change between low and high."""
    if npv(low, flows) * npv(high, flows) > 0.0:
        raise ValueError("no sign change in the IRR bracket")
    for _ in range(iterations):
        mid = (low + high) / 2.0
        if npv(mid, flows) > 0.0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def payback(flows: list) -> float | None:
    """Simple payback in years from the first positive cumulative year."""
    cumulative = 0.0
    for year, flow in enumerate(flows):
        if year == 0:
            cumulative = flow
            continue
        if cumulative + flow >= 0.0:
            return year - 1 + (-cumulative) / flow
        cumulative += flow
    return None


def debt_payment(principal: float, annual_rate: float, years: int) -> float:
    """Level annual debt service (principal + interest)."""
    if years <= 0:
        raise ValueError("years must be positive")
    if annual_rate == 0.0:
        return principal / years
    return principal * annual_rate / (1.0 - (1.0 + annual_rate) ** -years)


def dscr(cfads: float, debt_service: float) -> float:
    """Debt service coverage ratio for one period."""
    if debt_service <= 0.0:
        raise ValueError("debt_service must be positive")
    return cfads / debt_service
