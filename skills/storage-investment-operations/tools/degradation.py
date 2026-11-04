"""Degradation and augmentation screening. Standard library only."""

from __future__ import annotations


def equivalent_cycles(annual_discharge_mwh, energy_mwh, dod=1.0):
    """Full-equivalent cycles per year on the declared usable energy."""
    if energy_mwh <= 0 or not 0 < dod <= 1:
        raise ValueError("energy_mwh must be positive and dod in (0, 1]")
    return annual_discharge_mwh / (energy_mwh * dod)


def linear_soh(soh0, annual_fade, year):
    """Linear state-of-health path, floored at zero."""
    return max(soh0 - annual_fade * year, 0.0)


def years_to_threshold(soh0, annual_fade, threshold=0.8):
    """Years until SOH reaches the threshold, or None if it never does."""
    if annual_fade <= 0:
        return None
    years = (soh0 - threshold) / annual_fade
    return max(years, 0.0)


def augmentation_energy(energy_mwh, soh, target_soh=1.0):
    """Additional DC energy needed to restore usable energy at target SOH."""
    if soh <= 0:
        raise ValueError("soh must be positive")
    return energy_mwh * (target_soh / soh - 1.0)


def throughput_cost(annual_throughput_mwh, cost_per_kwh):
    """Annual degradation cost from AC throughput."""
    return annual_throughput_mwh * 1000 * cost_per_kwh
