"""Forecast-deviation exposure for retail portfolios.

The examples use a symmetric normal error and a two-sided tolerance band;
provincial rules differ, so the parameters are inputs, not defaults of law.
"""

import math
from statistics import NormalDist


def _normal_pdf(z):
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def excess_energy(actual_kwh, forecast_kwh, tolerance=0.05):
    """Energy outside the +/- tolerance band in a single period."""
    if forecast_kwh <= 0:
        raise ValueError("forecast_kwh must be positive")
    if not 0.0 <= tolerance < 1.0:
        raise ValueError("tolerance must be in [0, 1)")
    return max(abs(actual_kwh - forecast_kwh) - tolerance * forecast_kwh, 0.0)


def deviation_cost(actual_kwh, forecast_kwh, tolerance=0.05, penalty_per_kwh=0.15):
    """Assessment cost of one period's deviation."""
    if penalty_per_kwh < 0:
        raise ValueError("penalty_per_kwh must be non-negative")
    return excess_energy(actual_kwh, forecast_kwh, tolerance) * penalty_per_kwh


def expected_excess(forecast_kwh, sigma_pct, tolerance_pct):
    """Expected energy outside the band for a normal zero-mean error.

    E[|X| * 1{|X| > t}] = 2 * sigma * phi(t / sigma).
    """
    if forecast_kwh <= 0:
        raise ValueError("forecast_kwh must be positive")
    if sigma_pct <= 0:
        raise ValueError("sigma_pct must be positive")
    if not 0.0 <= tolerance_pct < 1.0:
        raise ValueError("tolerance_pct must be in [0, 1)")
    sigma = forecast_kwh * sigma_pct
    threshold = forecast_kwh * tolerance_pct
    return 2.0 * sigma * _normal_pdf(threshold / sigma)


def excess_quantile(forecast_kwh, sigma_pct, tolerance_pct, level=0.95):
    """Two-sided quantile of energy outside the band."""
    if not 0.0 < level < 1.0:
        raise ValueError("level must be in (0, 1)")
    if forecast_kwh <= 0:
        raise ValueError("forecast_kwh must be positive")
    sigma = forecast_kwh * sigma_pct
    threshold = forecast_kwh * tolerance_pct
    z = NormalDist().inv_cdf((1.0 + level) / 2.0)
    return max(z * sigma - threshold, 0.0)


def deviation_risk(forecast_kwh, sigma_pct, tolerance_pct, penalty_per_kwh=0.15, level=0.95):
    """Expected and quantile deviation cost for one period."""
    if penalty_per_kwh < 0:
        raise ValueError("penalty_per_kwh must be non-negative")
    expected = expected_excess(forecast_kwh, sigma_pct, tolerance_pct)
    quantile = excess_quantile(forecast_kwh, sigma_pct, tolerance_pct, level)
    return {
        "forecast_kwh": forecast_kwh,
        "expected_excess_kwh": expected,
        "expected_cost": expected * penalty_per_kwh,
        "quantile_level": level,
        "quantile_excess_kwh": quantile,
        "quantile_cost": quantile * penalty_per_kwh,
    }
