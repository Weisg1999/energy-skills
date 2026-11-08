"""Retail portfolio revenue, procurement cost and spot stress."""


def _validate(customers):
    if not customers:
        raise ValueError("customers must not be empty")
    for c in customers:
        if c["annual_kwh"] <= 0:
            raise ValueError("each customer must have positive annual_kwh")
        if c["retail_price"] < 0:
            raise ValueError("retail_price must be non-negative")


def portfolio_margin(customers, long_term_share, long_term_price, spot_price,
                     deviation_per_kwh=0.0, opex_per_kwh=0.0):
    """Annual margin of a customer portfolio under a two-part procurement mix."""
    _validate(customers)
    if not 0.0 <= long_term_share <= 1.0:
        raise ValueError("long_term_share must be in [0, 1]")
    energy = sum(c["annual_kwh"] for c in customers)
    revenue = sum(c["annual_kwh"] * c["retail_price"] for c in customers)
    procurement_price = long_term_share * long_term_price + (1.0 - long_term_share) * spot_price
    energy_cost = energy * procurement_price
    deviation_cost = energy * deviation_per_kwh
    opex = energy * opex_per_kwh
    net = revenue - energy_cost - deviation_cost - opex
    return {
        "energy_kwh": energy,
        "revenue": revenue,
        "procurement_price": procurement_price,
        "energy_cost": energy_cost,
        "deviation_cost": deviation_cost,
        "opex": opex,
        "gross_spread": revenue / energy - procurement_price,
        "net": net,
        "per_kwh": net / energy,
    }


def customer_contribution(customer, long_term_share, long_term_price, spot_price,
                          deviation_per_kwh=0.0, opex_per_kwh=0.0):
    """Annual contribution of a single customer, for keep/drop decisions."""
    result = portfolio_margin([customer], long_term_share, long_term_price, spot_price,
                              deviation_per_kwh, opex_per_kwh)
    return {"name": customer["name"], "annual_kwh": customer["annual_kwh"], "net": result["net"],
            "per_kwh": result["per_kwh"]}


def stress_spot(customers, multiplier, long_term_share, long_term_price, spot_price,
                deviation_per_kwh=0.0, opex_per_kwh=0.0):
    """Margin after scaling the spot price by multiplier."""
    return portfolio_margin(customers, long_term_share, long_term_price, spot_price * multiplier,
                            deviation_per_kwh, opex_per_kwh)


def break_even_spot_multiplier(customers, long_term_share, long_term_price, spot_price,
                               deviation_per_kwh=0.0, opex_per_kwh=0.0):
    """Spot multiplier at which portfolio net margin reaches zero."""
    base = portfolio_margin(customers, long_term_share, long_term_price, spot_price,
                            deviation_per_kwh, opex_per_kwh)
    spot_exposure = base["energy_kwh"] * (1.0 - long_term_share) * spot_price
    if spot_exposure <= 0:
        raise ValueError("no spot exposure; break-even is undefined")
    return 1.0 + base["net"] / spot_exposure
