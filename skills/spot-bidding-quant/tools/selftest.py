"""Self-test: exercises the whole chain and asserts the claims made in SKILL.md.

CI entry point. Any assertion failure means the skill's stated guarantees are
no longer true, so the text must change together with the code.

Run:  python tools/selftest.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backtest as bt
import bid
import forecast as fc
import simulate
from dataio import load_rows, to_days


def build_models(days: list[list[float]]) -> dict:
    return {
        "seasonal_naive": lambda d, t: fc.seasonal_naive(d, t),
        "similar_day": lambda d, t: fc.similar_day(d, t),
        "ar2": lambda d, t: fc.ar_forecast(d, t),
    }


def section(title: str) -> None:
    print(f"\n== {title}")


def main() -> int:
    rows = load_rows()
    load_actual = to_days(rows, "load_actual_mw")
    load_forecast = to_days(rows, "load_forecast_mw")
    price = to_days(rows, "da_price")
    rt_price = to_days(rows, "rt_price")

    assert len(load_actual) == 60 and len(load_actual[0]) == 96, "unexpected data shape"

    section("load forecast")
    flat_fc = [v for day in load_forecast for v in day]
    flat_act = [v for day in load_actual for v in day]
    given_mape = fc.mape(flat_fc, flat_act)
    print(f"provided day-ahead load forecast MAPE = {given_mape:.3%}")
    assert given_mape < 0.04, "provided load forecast is worse than the documented ~1.5-3%"

    baseline = bt.rolling_predict(load_actual, lambda d, t: fc.seasonal_naive(d, t))
    base_summary = bt.summarize(*baseline)
    print(f"seasonal_naive  MAE={base_summary['mae']:.0f} MW  MAPE={base_summary['mape']:.2%}")

    similar = bt.rolling_predict(load_actual, lambda d, t: fc.similar_day(d, t))
    similar_summary = bt.summarize(*similar)
    print(f"similar_day     MAE={similar_summary['mae']:.0f} MW  MAPE={similar_summary['mape']:.2%}")

    corrected = bt.rolling_corrected(load_actual, lambda d, t: fc.similar_day(d, t))
    corrected_summary = bt.summarize(*corrected)
    print(f"similar+resid   MAE={corrected_summary['mae']:.0f} MW  MAPE={corrected_summary['mape']:.2%}")

    assert corrected_summary["mae"] < base_summary["mae"], "residual correction must beat seasonal naive"
    gain = bt.improvement(base_summary, corrected_summary)
    print(f"improvement over baseline = {gain:.1%} (MAE)")
    assert gain > 0.10, "documented MAE improvement is at least 10%"

    section("price forecast")
    price_base = bt.rolling_predict(price, lambda d, t: fc.seasonal_naive(d, t))
    price_corrected = bt.rolling_corrected(price, lambda d, t: fc.similar_day(d, t))
    pb, pc = bt.summarize(*price_base), bt.summarize(*price_corrected)
    print(f"seasonal_naive  MAE={pb['mae']:.1f} CNY/MWh  dir={pb['direction_accuracy']:.1%}  spike_recall={pb['spike_recall']:.1%}")
    print(f"similar+resid   MAE={pc['mae']:.1f} CNY/MWh  dir={pc['direction_accuracy']:.1%}  spike_recall={pc['spike_recall']:.1%}")
    assert pc["mae"] < pb["mae"], "corrected price forecast must beat seasonal naive"
    assert pc["direction_accuracy"] > 0.55, "direction accuracy must clear the coin-flip test"

    quantiles = fc.residual_quantiles(*price_corrected, quantiles=(0.1, 0.5, 0.9))
    print(f"residual quantiles q10/q50/q90 = {quantiles[0.1]:.1f} / {quantiles[0.5]:.1f} / {quantiles[0.9]:.1f}")
    assert quantiles[0.1] < quantiles[0.9], "price cone must widen in the right direction"

    section("bid construction")
    samples = [v for day in rt_price[-20:] for v in day]
    taker = bid.price_taker_optimum(280.0, samples, quantity=350.0)
    print(f"price-taker optimum: bid={taker['price']:.1f} at cost 280, expected profit={taker['profit']:.0f} CNY")
    assert abs(taker["price"] - 280.0) < 1e-6, "price taker must bid at marginal cost"
    assert taker["profit"] > 0, "profitable hours must show up in the expected value"

    pivotal = bid.pivotal_markup(cost=280.0, residual_intercept=1300.0, residual_slope=1.6)
    print(f"pivotal markup: bid={pivotal['price']:.1f}  qty={pivotal['quantity']:.0f} MW  pivotal={pivotal['pivotal']}")
    assert pivotal["price"] > 280.0 and pivotal["quantity"] < 1300.0 / 1.6

    skewed = sorted(samples)
    median = skewed[len(skewed) // 2]
    declared = bid.declared_quantity(samples, over_penalty=400.0, under_penalty=100.0)
    print(f"declared quantity under asymmetric penalty: {declared['quantity']:.0f} vs median {median:.0f} CNY/MWh")
    assert declared["quantity"] < median, "harsher over-declaration penalty must push the quantity down"

    curve = bid.bid_curve([180.0, 280.0, 420.0], [120.0, 120.0, 110.0])
    for row in curve:
        print(f"  bid {row['price']:>7.1f} CNY/MWh  qty={row['quantity']:.0f} MW  cum={row['cumulative']:.0f} MW")
    assert [r["price"] for r in curve] == sorted(r["price"] for r in curve), "curve must be monotone"
    assert curve[0]["price"] == 180.0, "default curve is a pure cost stack (markup = 0)"

    spread = bid.storage_arbitrage_threshold(0.88, 60.0)
    print(f"storage break-even spread at 88% efficiency, CNY 60/MWh cycle cost = {spread:.1f} CNY/MWh")
    assert spread > 0

    section("market simulation")
    participants = [
        simulate.Participant("coal-a", cost=270.0, capacity=600.0),
        simulate.Participant("coal-b", cost=300.0, capacity=500.0),
        simulate.Participant("gas-c", cost=420.0, capacity=300.0),
        simulate.Participant("wind-d", cost=0.0, capacity=400.0),
    ]
    for p in participants:
        p.segments = [(p.cost, p.capacity)]
    market = simulate.clear(participants, demand_mw=1300.0)
    print(f"clearing={market['clearing_price']:.1f}  served={market['served_mw']:.0f} MW  HHI={market['hhi']:.0f}")
    assert market["clearing_price"] == 300.0, "marginal unit sets the price"
    assert 0.0 <= market["hhi"] <= 10000.0

    sweep = simulate.bid_sweep(participants, 1300.0, "coal-b", [300.0, 350.0, 400.0, 450.0])
    for row in sweep:
        print(f"  bid={row['bid']:.0f}  clear={row['clearing_price']:.0f}  mw={row['dispatched_mw']:.0f}  profit={row['profit']:.0f}")
    pivotal_rows = [row for row in sweep if row["bid"] < 420.0]
    assert all(row["dispatched_mw"] > 0 and row["sets_price"] for row in pivotal_rows), "pivotal unit prices the margin"
    assert [row["profit"] for row in pivotal_rows] == sorted(row["profit"] for row in pivotal_rows), "profit rises with the bid while pivotal"
    assert sweep[-1]["dispatched_mw"] == 0 and sweep[-1]["clearing_price"] == 420.0, "above the next rival the unit is priced out"

    section("summary")
    print("all checks passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\nFAILED: {exc}")
        traceback.print_exc()
        sys.exit(1)
