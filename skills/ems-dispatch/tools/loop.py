"""Forecast -> bid -> dispatch -> settlement closed loop (screening model).

Stitches the three EMS tools into one decision chain:

1. ``newsvendor_bid`` turns a point forecast plus an error spread into a
   day-ahead bid. The optimal bid is NOT the P50 forecast: it is the
   newsvendor quantile ``Cu / (Cu + Co)`` set by the asymmetric realtime
   penalty (buy-back premium vs surplus discount).
2. ``closed_loop_day`` takes the bid curve as a delivery obligation, the
   realized renewable as available energy, and lets ``dispatch.dispatch_day``
   schedule storage to minimise the realtime deviation penalty. Grid import
   is the residual shortfall bought at the realtime buy price; grid export is
   the residual surplus sold at the realtime sell price.
3. Day-ahead revenue on the bid plus the realtime deviation settlement minus
   degradation is the producer's net. The loop closes because the settlement
   feeds back into the next day's forecast spread and penalty assumptions.

``deviation_settlement`` is the single-interval settlement with an optional
tolerance band (the domestic "免考" deadband); the day-level DP loop uses
linear realtime prices without a band. Pure standard library, deterministic,
no solver. All curves are synthetic unless the caller supplies measured data.
This is a screening tool, not a settlement engine or a bidding advisor.
"""

from __future__ import annotations

import math

import dispatch

# Acklam's inverse normal CDF coefficients (absolute error < 1.15e-9).
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


def norm_ppf(p):
    """Inverse standard normal CDF (Acklam rational approximation)."""
    p = float(p)
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    if p <= _P_HIGH:
        q = p - 0.5
        r = q * q
        return (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / (
            ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
        (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
    )


def newsvendor_bid(p50_mw, sigma_mw, da_price, rt_buy, rt_sell):
    """Optimal day-ahead bid from a Gaussian forecast and asymmetric penalties.

    Underage cost ``Cu = da - rt_sell`` (margin lost when bidding too low and
    selling surplus cheaply realtime); overage cost ``Co = rt_buy - da``
    (buy-back premium when bidding too high). The critical fractile is
    ``Cu / (Cu + Co)``; the bid is the corresponding forecast quantile. Prices
    in CNY/MWh, power in MW. The bid is clamped to be non-negative.
    """
    p50_mw = float(p50_mw)
    sigma_mw = float(sigma_mw)
    da = float(da_price)
    rt_b = float(rt_buy)
    rt_s = float(rt_sell)
    if sigma_mw < 0:
        raise ValueError("sigma_mw must be non-negative")
    cu = da - rt_s
    co = rt_b - da
    if cu + co <= 0:
        quantile = 0.5
    else:
        quantile = cu / (cu + co)
    quantile = min(max(quantile, 1e-6), 1.0 - 1e-6)
    z = norm_ppf(quantile)
    bid = max(0.0, p50_mw + z * sigma_mw)
    return {
        "underage_cost": cu,
        "overage_cost": co,
        "quantile": quantile,
        "z": z,
        "bid_mw": bid,
    }


def deviation_settlement(
    bid_mw,
    realized_mw,
    da_price,
    rt_buy,
    rt_sell,
    *,
    dt_h=1.0,
    tolerance_ratio=0.0,
):
    """Single-interval day-ahead plus realtime deviation settlement.

    Day-ahead pays the bid at ``da_price``. The deviation ``realized - bid``
    inside the tolerance band ``tolerance_ratio * bid`` is settled at the
    day-ahead price (no penalty, the domestic "免考" deadband). Shortfall
    beyond the band is bought back at ``rt_buy``; surplus beyond the band is
    sold at ``rt_sell``. Prices in CNY/MWh, power in MW, result in CNY.
    """
    bid = float(bid_mw)
    realized = float(realized_mw)
    da = float(da_price)
    rt_b = float(rt_buy)
    rt_s = float(rt_sell)
    dt_h = float(dt_h)
    if bid < 0 or dt_h <= 0:
        raise ValueError("bid must be non-negative and dt_h positive")
    band = float(tolerance_ratio) * bid
    dev = realized - bid
    da_revenue = bid * da * dt_h
    rt_cost = 0.0
    rt_revenue = 0.0
    penalized = 0.0
    if dev < -band:
        penalized = -dev - band
        rt_cost = penalized * rt_b * dt_h
    elif dev > band:
        penalized = dev - band
        rt_revenue = penalized * rt_s * dt_h
    return {
        "deviation_mw": dev,
        "band_mw": band,
        "penalized_mw": penalized,
        "da_revenue": da_revenue,
        "rt_cost": rt_cost,
        "rt_revenue": rt_revenue,
        "net": da_revenue - rt_cost + rt_revenue,
    }


def closed_loop_day(
    p50_mw,
    sigma_mw,
    da_price_per_mwh,
    rt_buy_per_mwh,
    rt_sell_per_mwh,
    *,
    realized_error_mw=None,
    power_mw,
    energy_mwh,
    rte,
    soc_min=0.1,
    soc_max=0.9,
    soc_init=None,
    degradation_per_kwh=0.0,
    dt_h=1.0,
    states=200,
):
    """Forecast -> bid -> storage dispatch -> settlement for one horizon.

    The bid curve is the delivery obligation (``load`` to the dispatch kernel),
    the realized renewable is available energy (``pv``), and storage is
    scheduled by ``dispatch.dispatch_day`` to minimise the realtime deviation
    penalty. Residual grid import is shortfall bought at ``rt_buy``; residual
    export is surplus sold at ``rt_sell``. Day-ahead revenue on the bid plus
    realtime settlement minus degradation is the producer net.

    ``realized_error_mw`` defaults to a deterministic synthetic pattern; pass
    measured errors for a real replay. Power in MW, energy in MWh, prices in
    CNY/MWh, money in CNY. Screening model, not a settlement engine.
    """
    p50 = [float(v) for v in p50_mw]
    sigma = [float(v) for v in sigma_mw]
    da = [float(v) for v in da_price_per_mwh]
    rt_b = [float(v) for v in rt_buy_per_mwh]
    rt_s = [float(v) for v in rt_sell_per_mwh]
    n = len(p50)
    if not (len(sigma) == len(da) == len(rt_b) == len(rt_s) == n):
        raise ValueError("all input curves must have the same length")
    if n == 0:
        raise ValueError("curves must not be empty")
    if realized_error_mw is None:
        error = [sigma[t] * math.sin(t * 0.7) * 1.2 for t in range(n)]
    else:
        error = [float(v) for v in realized_error_mw]
        if len(error) != n:
            raise ValueError("realized_error_mw must match curve length")

    bids = []
    for t in range(n):
        bids.append(newsvendor_bid(p50[t], sigma[t], da[t], rt_b[t], rt_s[t])["bid_mw"])
    realized = [p50[t] + error[t] for t in range(n)]

    eta = math.sqrt(float(rte))
    result = dispatch.dispatch_day(
        [rt_b[t] / 1000.0 for t in range(n)],
        [bids[t] * 1000.0 for t in range(n)],
        [realized[t] * 1000.0 for t in range(n)],
        sell_price=[rt_s[t] / 1000.0 for t in range(n)],
        capacity_kwh=float(energy_mwh) * 1000.0,
        power_charge_kw=float(power_mw) * 1000.0,
        power_discharge_kw=float(power_mw) * 1000.0,
        eta_charge=eta,
        eta_discharge=eta,
        soc_min=float(soc_min),
        soc_max=float(soc_max),
        soc_init=soc_init,
        dt_h=float(dt_h),
        pcc_import_kw=None,
        pcc_export_kw=1e9,
        degradation_per_kwh=float(degradation_per_kwh),
        terminal="cycle",
        states=states,
    )
    if not result["feasible"]:
        return result

    schedule = result["schedule"]
    da_revenue = sum(bids[t] * da[t] * float(dt_h) for t in range(n))
    rt_cost = result["buy_cost"]
    rt_revenue = result["sell_revenue"]
    degradation = result["degradation_cost"]
    return {
        "feasible": True,
        "bid_mw": bids,
        "realized_mw": realized,
        "deviation_mw": [realized[t] - bids[t] for t in range(n)],
        "residual_import_mw": [v / 1000.0 for v in schedule["p_import_kw"]],
        "residual_export_mw": [v / 1000.0 for v in schedule["p_export_kw"]],
        "da_revenue": da_revenue,
        "rt_cost": rt_cost,
        "rt_revenue": rt_revenue,
        "degradation_cost": degradation,
        "net": da_revenue - rt_cost + rt_revenue - degradation,
        "throughput_mwh": result["throughput_kwh"] / 1000.0,
        "raw_shortfall_mwh": sum(max(0.0, bids[t] - realized[t]) * float(dt_h) for t in range(n)),
        "residual_shortfall_mwh": result["imported_kwh"] / 1000.0,
    }