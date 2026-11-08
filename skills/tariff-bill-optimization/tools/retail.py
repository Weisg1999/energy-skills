"""Retail package comparison on a representative-day load.

Only the energy component is compared. Transmission, system-operation fees,
government funds and the basic charge are common to every package and must be
added separately; a package that looks cheap on energy can still lose on those
lines.

Conventions
-----------
* Load is a representative day per month, in kW; prices are CNY/kWh.
* ``monthly_loads`` maps month 1-12 to a 24-hour series; ``days`` defaults to
  the 2026 month lengths.
"""

from __future__ import annotations

import curves
import tariff

DAYS_2026 = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _month_items(monthly_loads, dt_h):
    items = sorted(monthly_loads.items()) if isinstance(monthly_loads, dict) else list(enumerate(monthly_loads, 1))
    for month, load in items:
        if abs(len(load) * dt_h - 24.0) > 1e-9:
            raise ValueError("each monthly load must span 24 hours")
    return items


def fixed_price_cost(monthly_loads, price, dt_h=1.0, days=None):
    """Annual energy cost under a flat energy price."""
    days = DAYS_2026 if days is None else days
    total = 0.0
    for month, load in _month_items(monthly_loads, dt_h):
        daily = sum(float(value) for value in load) * dt_h * float(price)
        total += daily * days[month - 1]
    return total


def tou_cost(monthly_loads, prices, periods=None, dt_h=1.0, days=None):
    """Annual energy cost under a time-of-use energy price."""
    days = DAYS_2026 if days is None else days
    total = 0.0
    for month, load in _month_items(monthly_loads, dt_h):
        total += tariff.tou_energy_cost(load, prices, periods, dt_h)["cost"] * days[month - 1]
    return total


def _market_curve(market_prices, month):
    if isinstance(market_prices, dict):
        return market_prices[month]
    return market_prices


def market_linked_cost(
    monthly_loads,
    market_prices,
    dt_h=1.0,
    pass_through=0.9,
    adder=0.0,
    floor=None,
    cap=None,
    days=None,
):
    """Annual energy cost under a market-linked package.

    The customer price in each interval is
    ``clamp(pass_through * market_price + adder, floor, cap)``. A lower
    pass-through shifts price risk to the retailer but usually comes with a
    higher adder.
    """
    days = DAYS_2026 if days is None else days
    total = 0.0
    for month, load in _month_items(monthly_loads, dt_h):
        prices = _market_curve(market_prices, month)
        if len(prices) != len(load):
            raise ValueError("market curve length must match load length")
        daily = 0.0
        for power, market in zip(load, prices):
            price = float(pass_through) * float(market) + float(adder)
            if floor is not None:
                price = max(price, float(floor))
            if cap is not None:
                price = min(price, float(cap))
            daily += float(power) * dt_h * price
        total += daily * days[month - 1]
    return total


def compare_packages(monthly_loads, packages, dt_h=1.0, days=None):
    """Rank packages by annual energy cost.

    Each package is a dict with ``name``, ``type`` (``fixed``, ``tou`` or
    ``market``) and the matching keyword arguments from the three cost
    functions above.
    """
    results = []
    day_counts = DAYS_2026 if days is None else days
    total_energy = sum(
        sum(float(value) for value in load) * dt_h * day_counts[month - 1]
        for month, load in _month_items(monthly_loads, dt_h)
    )
    for package in packages:
        kind = package["type"]
        if kind == "fixed":
            cost = fixed_price_cost(monthly_loads, package["price"], dt_h, days)
        elif kind == "tou":
            cost = tou_cost(
                monthly_loads, package["prices"], package.get("periods"), dt_h, days
            )
        elif kind == "market":
            cost = market_linked_cost(
                monthly_loads,
                package["market_prices"],
                dt_h,
                package.get("pass_through", 0.9),
                package.get("adder", 0.0),
                package.get("floor"),
                package.get("cap"),
                days,
            )
        else:
            raise ValueError(f"unknown package type: {kind}")
        results.append(
            {
                "name": package["name"],
                "type": kind,
                "cost": cost,
                "average_price": cost / total_energy if total_energy else 0.0,
            }
        )
    results.sort(key=lambda row: row["cost"])
    return results
