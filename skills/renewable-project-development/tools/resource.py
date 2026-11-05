"""Resource and yield helpers for wind and solar projects.

Standard library only. All outputs are gross or net energy at the meter,
before market settlement; currency is not involved here.
"""

from __future__ import annotations

from math import exp, gamma


def annual_energy_mwh(power_mw: float, full_load_hours: float) -> float:
    """Annual net generation from installed capacity and full-load hours."""
    return power_mw * full_load_hours


def capacity_factor(full_load_hours: float, hours_per_year: float = 8760.0) -> float:
    """Capacity factor implied by full-load hours."""
    return full_load_hours / hours_per_year


def p90_from_p50(p50: float, coefficient_of_variation: float, z: float = 1.2816) -> float:
    """Normal approximation of P90 from P50 and the coefficient of variation.

    z = 1.2816 is the one-sided 90% normal quantile. This is a screening
    approximation, not a substitute for a bankable yield assessment.
    """
    return p50 * (1.0 - z * coefficient_of_variation)


def pv_specific_yield(
    poa_kwh_m2: float,
    performance_ratio: float,
    bifacial_gain: float = 0.0,
) -> float:
    """Specific yield in kWh/kWp from plane-of-array irradiation."""
    return poa_kwh_m2 * performance_ratio * (1.0 + bifacial_gain)


def wind_capacity_factor(
    mean_speed_ms: float,
    shape_k: float,
    cut_in_ms: float,
    rated_ms: float,
    cut_out_ms: float,
    availability: float = 1.0,
    step_ms: float = 0.01,
) -> float:
    """Capacity factor from a Weibull wind distribution and a cubic power curve.

    The power curve is normalised: zero below cut-in and above cut-out, cubic
    between cut-in and rated, one between rated and cut-out. The Weibull scale
    parameter is derived from the mean speed. This is a screening model; a
    bankable assessment uses the turbine's measured power curve and site data.
    """
    if not (0.0 < mean_speed_ms and shape_k > 0.0):
        raise ValueError("mean_speed_ms and shape_k must be positive")
    if not (cut_in_ms < rated_ms < cut_out_ms):
        raise ValueError("power-curve speeds must satisfy cut_in < rated < cut_out")

    scale = mean_speed_ms / gamma(1.0 + 1.0 / shape_k)

    def pdf(v: float) -> float:
        return (shape_k / scale) * (v / scale) ** (shape_k - 1.0) * exp(-((v / scale) ** shape_k))

    def normalised_power(v: float) -> float:
        if v < cut_in_ms or v > cut_out_ms:
            return 0.0
        if v >= rated_ms:
            return 1.0
        return ((v - cut_in_ms) / (rated_ms - cut_in_ms)) ** 3

    total = 0.0
    v = step_ms
    while v <= cut_out_ms:
        total += normalised_power(v) * pdf(v) * step_ms
        v += step_ms
    return total * availability
