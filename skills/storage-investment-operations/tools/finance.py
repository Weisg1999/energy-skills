"""Investment metrics for storage projects. Standard library only."""

from __future__ import annotations


def npv(rate, cashflows):
    """Net present value; cashflows[0] is normally the negative capex."""
    if rate <= -1:
        raise ValueError("rate must be greater than -1")
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows, low=-0.9, high=1.0):
    """Internal rate of return by bisection.

    Returns None when the cash-flow pattern has no sign change in range.
    """
    if not any(cf < 0 for cf in cashflows) or not any(cf > 0 for cf in cashflows):
        return None
    f_low = npv(low, cashflows)
    f_high = npv(high, cashflows)
    while f_low * f_high > 0 and high < 1e6:
        high *= 2
        f_high = npv(high, cashflows)
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < 1e-6:
            return mid
        if f_low * f_mid <= 0:
            high = mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2


def payback(cashflows):
    """Simple payback in years, assuming annual cash flows after year 0."""
    cumulative = cashflows[0]
    if cumulative >= 0:
        return 0.0
    for year, cf in enumerate(cashflows[1:], start=1):
        previous = cumulative
        cumulative += cf
        if cumulative >= 0 and cf != 0:
            return year - 1 + (-previous) / cf
    return None


def discounted_payback(rate, cashflows):
    """Discounted payback in years."""
    cumulative = cashflows[0]
    if cumulative >= 0:
        return 0.0
    for year, cf in enumerate(cashflows[1:], start=1):
        discounted = cf / (1 + rate) ** year
        previous = cumulative
        cumulative += discounted
        if cumulative >= 0 and discounted != 0:
            return year - 1 + (-previous) / discounted
    return None


def lcos(
    capex,
    annual_opex,
    annual_charge_cost,
    annual_discharge_mwh,
    years,
    discount_rate,
    residual=0.0,
):
    """Levelized cost of storage per MWh discharged (AC side).

    The boundary is explicit: capex, opex, charging cost and residual value
    are included; taxes and financing are not. Report the boundary whenever
    you quote a number, because LCOS is not a single standardized metric.
    """
    if years <= 0 or annual_discharge_mwh <= 0:
        raise ValueError("years and annual_discharge_mwh must be positive")
    pv_cost = capex
    pv_energy = 0.0
    for year in range(1, years + 1):
        discount = (1 + discount_rate) ** year
        pv_cost += (annual_opex + annual_charge_cost) / discount
        pv_energy += annual_discharge_mwh / discount
    pv_cost -= residual / (1 + discount_rate) ** years
    return pv_cost / pv_energy


def annual_cashflow(
    revenue,
    opex,
    capex,
    years,
    tax_rate=0.25,
    depreciation_years=None,
):
    """Build a simple project cash-flow vector with straight-line depreciation."""
    depreciation_years = depreciation_years or years
    depreciation = capex / depreciation_years
    cashflows = [-capex]
    for year in range(1, years + 1):
        dep = depreciation if year <= depreciation_years else 0.0
        ebit = revenue - opex - dep
        tax = max(ebit, 0.0) * tax_rate
        net = ebit - tax
        cashflows.append(net + dep)
    return cashflows


def dscr(annual_cashflow, annual_debt_service):
    """Debt service coverage ratio."""
    if annual_debt_service <= 0:
        raise ValueError("annual_debt_service must be positive")
    return annual_cashflow / annual_debt_service
