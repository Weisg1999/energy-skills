"""Product carbon footprint (PCF) mechanics.

All quantities are kg CO2e unless stated otherwise. Standard library only.
The functions model accounting arithmetic, not a claim that a product is
certifiable or carbon neutral.
"""

from __future__ import annotations

STAGES = ("raw_material", "production", "transport", "use", "end_of_life")


def lifecycle_total(stage_kg):
    """Sum stage emissions; missing stages count as zero."""
    if any(value < 0 for value in stage_kg.values()):
        raise ValueError("stage emissions must be non-negative")
    unknown = set(stage_kg) - set(STAGES)
    if unknown:
        raise ValueError(f"unknown lifecycle stages: {sorted(unknown)}")
    return sum(stage_kg.values())


def intensity(total_kg, declared_units):
    """PCF per declared unit (kg CO2e per unit)."""
    if total_kg < 0:
        raise ValueError("total_kg must be non-negative")
    if declared_units <= 0:
        raise ValueError("declared_units must be positive")
    return total_kg / declared_units


def stage_shares(stage_kg):
    """Share of each stage in total emissions; shares sum to one."""
    total = lifecycle_total(stage_kg)
    if total <= 0:
        raise ValueError("total emissions must be positive")
    return {stage: value / total for stage, value in stage_kg.items()}


def allocate(total_kg, weights):
    """Allocate emissions across co-products by mass, energy or value weights."""
    if total_kg < 0:
        raise ValueError("total_kg must be non-negative")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(value < 0 for value in weights.values()):
        raise ValueError("weights must be non-negative")
    denominator = sum(weights.values())
    if denominator <= 0:
        raise ValueError("weights must sum to a positive value")
    return {key: total_kg * value / denominator for key, value in weights.items()}


def residual_after_reduction(total_kg, reduction_rate):
    """Emissions left after in-value-chain abatement, before any offsetting."""
    if total_kg < 0:
        raise ValueError("total_kg must be non-negative")
    if not 0 <= reduction_rate < 1:
        raise ValueError("reduction_rate must be in [0, 1)")
    return total_kg * (1 - reduction_rate)


def offset_cost(residual_kg, price_per_t):
    """Cost of offsetting residual emissions at a price per tonne."""
    if residual_kg < 0 or price_per_t < 0:
        raise ValueError("inputs must be non-negative")
    return residual_kg / 1000 * price_per_t
