"""Compliance-position arithmetic for China's national ETS.

All quantities are tonnes of CO2-equivalent unless stated otherwise.
Standard library only.
"""

from __future__ import annotations


def free_allocation(activity_mwh, benchmark, correction=1.0):
    """Free allowance from a benchmark: activity x benchmark x correction."""
    if activity_mwh < 0:
        raise ValueError("activity_mwh must be non-negative")
    if benchmark <= 0:
        raise ValueError("benchmark must be positive")
    if correction <= 0:
        raise ValueError("correction must be positive")
    return activity_mwh * benchmark * correction


def ccer_limit(base, cap=0.05):
    """Maximum CCER that may be used against a compliance obligation.

    The national cap is a share of the surrender obligation, normally the
    verified emissions, not of the free allocation.
    """
    if base < 0:
        raise ValueError("base must be non-negative")
    if not 0 <= cap <= 1:
        raise ValueError("cap must be between 0 and 1")
    return base * cap


def compliance_position(allocation, verified_emissions, ccer_available=0.0, ccer_cap=0.05, cap_base=None):
    """Return the gap, CCER use, CEA purchase need and any surplus.

    CCER is used only up to the cap and never beyond the gap itself. The cap
    base defaults to verified emissions (the surrender obligation); pass an
    explicit cap_base only where a rule defines a different base.
    """
    if allocation < 0 or verified_emissions < 0 or ccer_available < 0:
        raise ValueError("inputs must be non-negative")
    gap = verified_emissions - allocation
    if gap <= 0:
        return {
            "gap": gap,
            "surplus": -gap,
            "ccer_used": 0.0,
            "ccer_unused": ccer_available,
            "cea_needed": 0.0,
        }
    base = verified_emissions if cap_base is None else cap_base
    limit = ccer_limit(base, ccer_cap)
    ccer_used = min(ccer_available, limit, gap)
    return {
        "gap": gap,
        "surplus": 0.0,
        "ccer_limit": limit,
        "ccer_used": ccer_used,
        "ccer_unused": ccer_available - ccer_used,
        "cea_needed": gap - ccer_used,
    }


def compliance_cost(position, cea_price, ccer_price=0.0):
    """Purchase cost of covering the position, excluding fees and penalties."""
    if cea_price < 0 or ccer_price < 0:
        raise ValueError("prices must be non-negative")
    return position["cea_needed"] * cea_price + position["ccer_used"] * ccer_price


def non_compliance_penalty(shortfall, market_average_price, multiple=5.0):
    """Penalty for an un-surrendered shortfall (Order 775: 5-10x market average)."""
    if shortfall < 0:
        raise ValueError("shortfall must be non-negative")
    if market_average_price < 0:
        raise ValueError("market_average_price must be non-negative")
    if not 5 <= multiple <= 10:
        raise ValueError("multiple must be within the statutory 5-10 range")
    return shortfall * market_average_price * multiple


def allocation_with_certification_bonus(base_allocation, bonus=0.005, cap=0.01):
    """Free-allocation uplift for a certified product footprint.

    Models the Shanghai 2026 draft rule: +0.5 percentage point for a certified
    product footprint, capped at +1 percentage point in total. Confirm the
    current local rule before using this outside that pilot.
    """
    if base_allocation < 0:
        raise ValueError("base_allocation must be non-negative")
    if bonus < 0 or cap < 0:
        raise ValueError("bonus and cap must be non-negative")
    applied = min(bonus, cap)
    return base_allocation * applied


def carryover_allowed(vintage_year):
    """Carry-over rule from the 2025/2026 allocation plan; confirm each year."""
    if vintage_year <= 2024:
        return False
    if vintage_year in (2025, 2026):
        return True
    raise ValueError("no carry-over rule configured for this vintage year")
