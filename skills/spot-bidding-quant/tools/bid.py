"""Bid construction: the price-taker theorem, pivotal markup, quantity choice.

The single most important result in this file: under pay-as-clear clearing with
no capacity constraint, a price taker maximises expected profit by bidding at
marginal cost. Markup only pays when the unit is pivotal, and persistent
economic withholding is a regulatory red line, not a strategy.
"""

from __future__ import annotations

import math


def cvar(pnl: list[float], alpha: float = 0.05) -> float:
    """Expected shortfall: mean of the worst `alpha` share of outcomes."""
    if not pnl:
        return 0.0
    ordered = sorted(pnl)
    k = max(1, int(math.ceil(alpha * len(ordered))))
    return sum(ordered[:k]) / k


def expected_profit(cost: float, price: float, samples: list[float], quantity: float = 1.0) -> float:
    """Price-taker PnL under pay-as-clear: dispatched in full when pi >= bid.

    PnL = quantity x (pi - cost) for samples with pi >= bid, otherwise zero.
    """
    hits = [s for s in samples if s >= price]
    if not hits:
        return 0.0
    return quantity * sum(s - cost for s in hits) / len(samples)


def price_taker_optimum(cost: float, samples: list[float], quantity: float = 1.0) -> dict:
    """Verify the theorem instead of assuming a markup.

    Bidding below cost admits samples priced under cost (negative profit),
    bidding above cost forfeits profitable samples. The optimum is exactly the
    marginal cost, so any "optimisation" that reports a markup of zero for a
    non-pivotal unit is correct, not broken.
    """
    if not samples:
        return {"price": cost, "profit": 0.0}
    best_price, best_profit = cost, expected_profit(cost, cost, samples, quantity)
    for price in sorted(set(round(s, 2) for s in samples)):
        profit = expected_profit(cost, price, samples, quantity)
        if profit > best_profit + 1e-9:
            best_price, best_profit = price, profit
    return {"price": round(best_price, 2), "profit": best_profit}


def pivotal_markup(
    cost: float,
    residual_intercept: float,
    residual_slope: float,
    cap: float = 1500.0,
) -> dict:
    """Optimal bid when your unit is pivotal, using residual demand R(p)=a-b*p.

    Profit = (p - c)(a - b*p), so p* = (a/b + c)/2, clamped to [cost, cap].
    `residual_intercept` and `residual_slope` must be estimated from observed
    residual demand, not assumed. Voluntarily withholding capacity to move the
    price is economic withholding and is monitored as market power abuse.
    """
    if residual_slope <= 0:
        raise ValueError("residual slope must be positive")
    price = 0.5 * (residual_intercept / residual_slope + cost)
    price = min(max(price, cost), cap)
    quantity = max(0.0, residual_intercept - residual_slope * price)
    return {
        "price": round(price, 2),
        "quantity": round(quantity, 2),
        "profit": round((price - cost) * quantity, 2),
        "pivotal": quantity > 0 and price > cost,
    }


def declared_quantity(
    samples: list[float],
    over_penalty: float,
    under_penalty: float,
    step: float = 1.0,
) -> dict:
    """Quantity choice under imbalance penalties (renewables, limited energy).

    Minimise over_penalty x E[(q - actual)+] + under_penalty x E[(actual - q)+].
    With a symmetric penalty the optimum is the median; a harsher over-declaration
    penalty pushes the declared quantity below the mean, which is the whole point
    of bidding conservatively when the fine is asymmetric.
    """
    if not samples:
        return {"quantity": 0.0, "expected_cost": 0.0}
    lo, hi = min(samples), max(samples)
    best_q, best_cost = lo, float("inf")
    q = lo
    while q <= hi + 1e-9:
        cost = sum(
            over_penalty * max(0.0, q - a) + under_penalty * max(0.0, a - q) for a in samples
        ) / len(samples)
        if cost < best_cost:
            best_q, best_cost = q, cost
        q += step
    return {"quantity": round(best_q, 2), "expected_cost": round(best_cost, 2)}


def bid_curve(
    segment_costs: list[float],
    segment_quantities: list[float],
    markup: float = 0.0,
) -> list[dict]:
    """Build a monotone quantity-price curve from a cost stack.

    `markup` is an explicit assumption, not an output: leave it at zero for a
    price taker and justify any non-zero value with residual demand.
    """
    curve = []
    cumulative = 0.0
    for cost, quantity in zip(segment_costs, segment_quantities):
        price = cost * (1.0 + markup)
        cumulative += quantity
        curve.append(
            {
                "price": round(price, 2),
                "quantity": quantity,
                "cumulative": round(cumulative, 2),
                "cost": cost,
            }
        )
    prices = [row["price"] for row in curve]
    if prices != sorted(prices):
        raise ValueError("bid curve is not monotone: check segment costs")
    return curve


def contract_adjustment(
    spot_pnl: list[float],
    contract_quantity: float,
    contract_price: float,
    spot_prices: list[float],
) -> list[float]:
    """Overlay a medium/long-term contract on a spot PnL series.

    Cash flow = spot PnL + contract_quantity x (contract_price - spot_price).
    The contract does not change dispatch; it converts spot exposure into a
    fixed-price settlement, so it moves variance more than the mean.
    """
    return [pnl + contract_quantity * (contract_price - price) for pnl, price in zip(spot_pnl, spot_prices)]


def storage_arbitrage_threshold(round_trip_efficiency: float, cycle_cost: float) -> float:
    """Minimum peak-valley spread for storage arbitrage to break even.

    spread_min = cycle_cost / round_trip_efficiency, in CNY/MWh.
    """
    return cycle_cost / max(1e-6, round_trip_efficiency)
