"""CCER project economics: reductions, cash flows, NPV, IRR and break-even price.

Standard library only. All cash amounts are in the same currency as the price input.
"""

from __future__ import annotations


def emission_reductions(baseline, project, leakage=0.0):
    """ER = baseline - project - leakage, in tCO2e per year."""
    if baseline < 0 or project < 0 or leakage < 0:
        raise ValueError("emission inputs must be non-negative")
    return baseline - project - leakage


def annuity_factor(rate, years):
    """Present value of one unit per year for `years` at `rate`."""
    if years <= 0:
        raise ValueError("years must be positive")
    if rate == 0:
        return float(years)
    if rate <= -1:
        raise ValueError("rate must be greater than -1")
    return (1 - (1 + rate) ** -years) / rate


def project_cashflows(annual_reductions, price, capex, opex, years, escalation=0.0):
    """Cash flows: capex at t=0, then (reductions x price - opex) each year."""
    if annual_reductions < 0 or price < 0 or capex < 0 or opex < 0:
        raise ValueError("inputs must be non-negative")
    if years <= 0:
        raise ValueError("years must be positive")
    flows = [-capex]
    for t in range(years):
        revenue = annual_reductions * price * (1 + escalation) ** t
        flows.append(revenue - opex)
    return flows


def npv(cashflows, discount_rate):
    """Net present value with the first cash flow at t=0."""
    if discount_rate <= -1:
        raise ValueError("discount_rate must be greater than -1")
    return sum(cf / (1 + discount_rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows, low=-0.99, high=10.0, tol=1e-9):
    """Internal rate of return by bisection; None if no sign change."""
    if not cashflows:
        raise ValueError("cashflows must not be empty")

    def value(rate):
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))

    f_low, f_high = value(low), value(high)
    if f_low * f_high > 0:
        return None
    for _ in range(300):
        mid = (low + high) / 2
        f_mid = value(mid)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid < 0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


def break_even_price(annual_reductions, capex, opex, years, discount_rate=0.08):
    """Constant certificate price at which project NPV equals zero."""
    if annual_reductions <= 0:
        raise ValueError("annual_reductions must be positive")
    return (opex + capex / annuity_factor(discount_rate, years)) / annual_reductions


def sensitivity(annual_reductions, price, capex, opex, years, discount_rate=0.08):
    """NPV under +/-10% price, volume and capex, plus +25% opex."""
    cases = {
        "base": (annual_reductions, price, capex, opex),
        "price -10%": (annual_reductions, price * 0.9, capex, opex),
        "price +10%": (annual_reductions, price * 1.1, capex, opex),
        "volume -10%": (annual_reductions * 0.9, price, capex, opex),
        "capex +10%": (annual_reductions, price, capex * 1.1, opex),
        "opex +25%": (annual_reductions, price, capex, opex * 1.25),
    }
    out = {}
    for name, (er, p, cap, op) in cases.items():
        flows = project_cashflows(er, p, cap, op, years)
        out[name] = npv(flows, discount_rate)
    return out
