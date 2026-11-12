"""Weather-to-power conversion primitives and weather-risk payoffs.

Pure standard library. These are *reference* implementations of the four
conversion chains described in ``knowledge/气象与电力交易-2026-11.md``:
temperature -> load, wind speed -> wind power, irradiance -> PV output,
and rainfall/inflow -> hydro (kept as an index, not a physical model).

This is not a forecasting stack and not a trading system. Every parameter is
explicit, so the synthetic (grade-D) examples in the module can be recomputed
and the text cannot silently drift away from the code.
"""

from __future__ import annotations

import math

HEATING_BASE_C = 18.0
COOLING_BASE_C = 18.0
STANDARD_AIR_DENSITY = 1.225
REFERENCE_IRRADIANCE = 1000.0
REFERENCE_CELL_TEMP_C = 25.0


# --------------------------------------------------------------- 1. degree days

def degree_days(t_mean_c: list[float], base_c: float = HEATING_BASE_C, kind: str = "hdd") -> float:
    """Sum of daily heating or cooling degree days.

    HDD uses max(base - T, 0); CDD uses max(T - base, 0). A 18 C base matches
    the 65 F convention used by CME US degree-day contracts, but the base is a
    contract term, not a physical constant.
    """
    if kind not in ("hdd", "cdd"):
        raise ValueError("kind must be 'hdd' or 'cdd'")
    if not t_mean_c:
        return 0.0
    if kind == "hdd":
        return sum(max(base_c - t, 0.0) for t in t_mean_c)
    return sum(max(t - base_c, 0.0) for t in t_mean_c)


def degree_hours(t_hourly_c: list[float], base_c: float = COOLING_BASE_C, kind: str = "cdd") -> float:
    """Hourly degree hours; divide by 24 only when comparing with degree *days*."""
    return degree_days(t_hourly_c, base_c, kind)


def temperature_load_mw(base_load_mw: float, cdd: float, beta_mw_per_cdd: float,
                        humidity_term_mw: float = 0.0) -> float:
    """Linear temperature-sensitive load. beta is a fitted coefficient, not a constant.

    Keep base load, temperature-sensitive load and humidity/extra terms apart so
    a calibration error shows up in one place instead of being hidden in the base.
    """
    return base_load_mw + beta_mw_per_cdd * cdd + humidity_term_mw


# --------------------------------------------------------------------- 2. wind

def hub_height_wind(v_ref_ms: float, h_ref_m: float, h_hub_m: float,
                    alpha: float = 0.14) -> float:
    """Power-law vertical extrapolation of wind speed to hub height.

    alpha is site-specific (roughness, stability). Never feed a 10 m station
    wind directly into a 100 m turbine power curve.
    """
    if h_ref_m <= 0 or h_hub_m <= 0:
        raise ValueError("heights must be positive")
    return v_ref_ms * (h_hub_m / h_ref_m) ** alpha


def wind_power_mw(v_ms: float, rated_mw: float, cut_in_ms: float = 3.0,
                  rated_ms: float = 12.0, cut_out_ms: float = 25.0,
                  rho: float = STANDARD_AIR_DENSITY,
                  rho_ref: float = STANDARD_AIR_DENSITY) -> float:
    """Piecewise power curve with an air-density correction.

    Below cut-in and above cut-out output is zero; between cut-in and rated
    speed the cubic approximation is used; from rated to cut-out output is
    capped at nameplate. The density correction is applied to the sub-rated
    part only and never lifts output above rated_mw.
    """
    if not (0 <= cut_in_ms < rated_ms < cut_out_ms):
        raise ValueError("require 0 <= cut_in < rated < cut_out")
    if rated_mw <= 0 or rho <= 0 or rho_ref <= 0:
        raise ValueError("rated_mw and densities must be positive")
    if v_ms < cut_in_ms or v_ms > cut_out_ms:
        return 0.0
    if v_ms >= rated_ms:
        return rated_mw
    fraction = (v_ms ** 3 - cut_in_ms ** 3) / (rated_ms ** 3 - cut_in_ms ** 3)
    return min(rated_mw, rated_mw * fraction * (rho / rho_ref))


# ----------------------------------------------------------------------- 3. PV

def cell_temperature_c(t_ambient_c: float, ghi_wm2: float, noct_c: float = 45.0) -> float:
    """NOCT-style cell temperature estimate. GHI is W/m2 on the plane of array."""
    return t_ambient_c + (noct_c - 20.0) / 800.0 * max(ghi_wm2, 0.0)


def pv_dc_mw(ghi_wm2: float, p_dc_mw: float, t_cell_c: float,
             gamma_per_c: float = -0.0035,
             g_ref: float = REFERENCE_IRRADIANCE,
             t_ref: float = REFERENCE_CELL_TEMP_C) -> float:
    """DC output before inverter clipping, with a temperature derate.

    gamma_per_c is the module's power temperature coefficient (per C); the
    default -0.35%/C is a typical value, not a universal constant.
    """
    if ghi_wm2 <= 0 or p_dc_mw <= 0:
        return 0.0
    derate = 1.0 + gamma_per_c * (t_cell_c - t_ref)
    return max(0.0, p_dc_mw * (ghi_wm2 / g_ref) * derate)


# --------------------------------------------------------------- 4. ensembles

def quantile(values: list[float], q: float) -> float:
    """Linear-interpolation quantile (type-7). q in [0, 1]."""
    if not values:
        raise ValueError("empty ensemble")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    return ordered[low] + (pos - low) * (ordered[high] - ordered[low])


def optimal_bid_quantile(penalty_short: float, penalty_long: float) -> float:
    """Newsvendor quantile for asymmetric imbalance penalties.

    penalty_short is the cost of under-declaring (buy the shortfall at a high
    price); penalty_long is the cost of over-declaring (dump the surplus at a
    low price). The optimum is short / (short + long), not the mean.
    """
    if penalty_short <= 0 or penalty_long <= 0:
        raise ValueError("penalties must be positive")
    return penalty_short / (penalty_short + penalty_long)


def asymmetric_loss(bid_mw: float, scenarios_mw: list[float],
                    penalty_short: float, penalty_long: float) -> float:
    """Mean penalty over an ensemble, in the same units as the penalties."""
    if not scenarios_mw:
        raise ValueError("empty scenarios")
    total = 0.0
    for s in scenarios_mw:
        if s > bid_mw:
            total += (s - bid_mw) * penalty_short
        else:
            total += (bid_mw - s) * penalty_long
    return total / len(scenarios_mw)


def bid_from_ensemble(scenarios_mw: list[float], penalty_short: float,
                      penalty_long: float) -> float:
    """Optimal declared quantity under asymmetric penalties."""
    return quantile(scenarios_mw, optimal_bid_quantile(penalty_short, penalty_long))


# ------------------------------------------------------- 5. weather derivatives

def weather_future_payout(index_value: float, strike_index: float,
                          tick_value: float, quantity: float = 1.0,
                          cap: float | None = None) -> float:
    """Cash settlement of a linear degree-day futures position.

    tick_value is per index point per contract and is venue-specific: CME US
    degree-day contracts quote USD 20 per point, European HDD contracts EUR 20,
    and Pacific Rim CAT contracts JPY 2,500. Never assume a default.
    """
    raw = (index_value - strike_index) * tick_value * quantity
    if cap is not None:
        return min(raw, cap)
    return raw


def basis_gap(index_station: float, index_exposure: float) -> float:
    """Station index minus the hedger's real exposure index, in index points.

    A parametric hedge pays on the station index; a non-zero gap is the basis
    risk that no tick size or strike can remove.
    """
    return index_station - index_exposure


def inflow_index_mm(rainfall_mm: list[float], runoff_coefficient: float = 0.6,
                    lag_days: int = 1) -> list[float]:
    """A deliberately simple lagged runoff index, not a hydrological model.

    It exists to make the rainfall-to-inflow timing explicit: today's rain is
    not today's generation. Real hydro dispatch needs reservoir level, snow
    melt and upstream regulation.
    """
    if not 0.0 <= runoff_coefficient <= 1.0:
        raise ValueError("runoff coefficient must be in [0, 1]")
    if lag_days < 0:
        raise ValueError("lag must be non-negative")
    effective = [r * runoff_coefficient for r in rainfall_mm]
    return [0.0] * min(lag_days, len(effective)) + effective[:len(effective) - lag_days]
