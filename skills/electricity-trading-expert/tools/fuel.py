"""Fuel-cost primitives for power bidding (pure standard library).

Reference implementations for the conversion chain described in
``knowledge/燃料与电力交易-2026-11.md``: long-term contract pricing,
blended fuel cost, fuel cost per MWh, gross/clean spreads, the coal-to-gas
switching carbon price, the dual-track price gap and inventory days.

These are *calibre* helpers, not a price forecast. Every parameter is explicit
so the synthetic (grade-D) examples in the module can be recomputed and the
text cannot silently drift away from the code.
"""

from __future__ import annotations

COAL_BASE_CNY_PER_TON = 675.0
COAL_PRICE_FLOOR = 570.0
COAL_PRICE_CAP = 770.0
COAL_RATE_KG_PER_MWH = 300.0
EF_COAL_TCO2_PER_MWH = 0.95
EF_GAS_TCO2_PER_MWH = 0.40


def long_term_coal_price(index_avg: float,
                         base: float = COAL_BASE_CNY_PER_TON,
                         floor: float = COAL_PRICE_FLOOR,
                         cap: float = COAL_PRICE_CAP) -> float:
    """China's 2026 thermal-coal long-term contract: base + 50% of the index deviation.

    The slope of 0.5 is the whole point: a 100 CNY/t spot move only moves the
    contract price by 50 CNY/t. floor/cap are the policy band, not a fit.
    """
    raw = base + (index_avg - base) / 2.0
    return min(cap, max(floor, raw))


def blended_coal_price(lt_price: float, spot_price: float, lt_share: float) -> float:
    """Effective delivered coal price when only part of the burn is covered by contracts."""
    if not 0.0 <= lt_share <= 1.0:
        raise ValueError("lt_share must be in [0, 1]")
    return lt_share * lt_price + (1.0 - lt_share) * spot_price


def coal_cost_per_mwh(price_cny_per_ton: float,
                      coal_rate_kg_per_mwh: float = COAL_RATE_KG_PER_MWH) -> float:
    """Fuel cost per MWh from a CNY/t coal price and a kg/MWh burn rate.

    Coal rate is plant-specific (unit age, load, coal quality); 300 g/kWh is
    only a convenient reference, not a national constant.
    """
    if price_cny_per_ton < 0 or coal_rate_kg_per_mwh <= 0:
        raise ValueError("price must be non-negative and coal rate positive")
    return price_cny_per_ton / 1000.0 * coal_rate_kg_per_mwh


def dark_spread(power_price: float, coal_cost_mwh: float,
                variable_om: float = 0.0) -> float:
    """Coal gross margin per MWh before carbon and fixed costs."""
    return power_price - coal_cost_mwh - variable_om


def spark_spread(power_price: float, gas_cost_mwh: float,
                 variable_om: float = 0.0) -> float:
    """Gas gross margin per MWh before carbon and fixed costs."""
    return power_price - gas_cost_mwh - variable_om


def clean_spread(gross_spread: float, carbon_price: float,
                 emission_factor: float) -> float:
    """Subtract the carbon cost; emission factor is tCO2/MWh, not tCO2/t fuel."""
    if emission_factor < 0:
        raise ValueError("emission factor must be non-negative")
    return gross_spread - carbon_price * emission_factor


def switch_carbon_price(coal_cost_mwh: float, gas_cost_mwh: float,
                        ef_coal: float = EF_COAL_TCO2_PER_MWH,
                        ef_gas: float = EF_GAS_TCO2_PER_MWH) -> float:
    """Carbon price at which coal and gas have equal short-run marginal cost.

    Above this price gas displaces coal in the merit order. Deliberately uses
    fuel cost only; add variable O&M to both sides if your convention needs it.
    """
    if ef_coal <= ef_gas:
        raise ValueError("coal emission factor must exceed gas")
    return (gas_cost_mwh - coal_cost_mwh) / (ef_coal - ef_gas)


def dual_track_gap(spot_price: float, index_avg: float,
                   base: float = COAL_BASE_CNY_PER_TON) -> float:
    """Spot price minus the long-term contract price, in CNY/t."""
    return spot_price - long_term_coal_price(index_avg, base)


def inventory_days(stock_ton: float, daily_burn_ton: float) -> float:
    """Days of cover; the thinnest buffer in a tight fuel market."""
    if daily_burn_ton <= 0:
        raise ValueError("daily burn must be positive")
    return stock_ton / daily_burn_ton
