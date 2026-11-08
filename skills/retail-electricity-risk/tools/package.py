"""Retail package build-up and quoting.

All amounts are CNY; prices are CNY/kWh unless stated otherwise.
"""


def _non_negative(name, value):
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def fixed_price(wholesale_price, deviation_per_kwh=0.0, opex_per_kwh=0.0, margin_per_kwh=0.0):
    """Build a fixed retail price from cost components."""
    _non_negative("wholesale_price", wholesale_price)
    _non_negative("deviation_per_kwh", deviation_per_kwh)
    _non_negative("opex_per_kwh", opex_per_kwh)
    return wholesale_price + deviation_per_kwh + opex_per_kwh + margin_per_kwh


def market_linked_price(spot_price, pass_through=1.0, adder=0.0, floor=None, cap=None):
    """Price a market-linked package: pass_through * spot + adder, clamped."""
    _non_negative("spot_price", spot_price)
    _non_negative("pass_through", pass_through)
    price = pass_through * spot_price + adder
    if floor is not None:
        price = max(price, floor)
    if cap is not None:
        price = min(price, cap)
    return price


def margin(price, wholesale_price, deviation_per_kwh=0.0, opex_per_kwh=0.0):
    """Per-kWh contribution after energy, deviation and operating costs."""
    _non_negative("deviation_per_kwh", deviation_per_kwh)
    _non_negative("opex_per_kwh", opex_per_kwh)
    return price - wholesale_price - deviation_per_kwh - opex_per_kwh


def annual_result(price, annual_kwh, wholesale_price, deviation_per_kwh=0.0, opex_per_kwh=0.0):
    """Annual revenue, cost and margin for one package."""
    if annual_kwh <= 0:
        raise ValueError("annual_kwh must be positive")
    per_kwh = margin(price, wholesale_price, deviation_per_kwh, opex_per_kwh)
    return {
        "annual_kwh": annual_kwh,
        "revenue": price * annual_kwh,
        "energy_cost": wholesale_price * annual_kwh,
        "deviation_cost": deviation_per_kwh * annual_kwh,
        "opex": opex_per_kwh * annual_kwh,
        "net": per_kwh * annual_kwh,
        "per_kwh": per_kwh,
    }


def break_even_spot(retail_price, long_term_price, long_term_share, deviation_per_kwh=0.0, opex_per_kwh=0.0):
    """Spot price at which a fixed-price retail contract breaks even."""
    if not 0.0 <= long_term_share <= 1.0:
        raise ValueError("long_term_share must be in [0, 1]")
    spot_share = 1.0 - long_term_share
    if spot_share == 0.0:
        raise ValueError("no spot exposure; break-even is undefined")
    return (retail_price - deviation_per_kwh - opex_per_kwh - long_term_share * long_term_price) / spot_share
