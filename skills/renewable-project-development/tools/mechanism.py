"""Doc. 136 mechanism-price settlement and break-even helpers.

Prices are CNY/kWh unless a name says otherwise; quantities are MWh.
Provincial rules differ on the market-price reference, settlement period and
whether green-certificate revenue is inside or outside the mechanism. This
module implements the common "difference settlement on the covered quantity"
structure only.
"""

from __future__ import annotations


def cfd_settlement(
    mechanism_price: float,
    market_price: float,
    mechanism_quantity_mwh: float,
    total_generation_mwh: float,
    green_certificate_price: float = 0.0,
) -> dict:
    """Settle a mechanism-price contract for one period.

    The project sells all generation at the market price and receives (or pays)
    the difference between the mechanism price and the market price on the
    covered quantity. green_certificate_price is CNY per certificate, one
    certificate per MWh.
    """
    if total_generation_mwh <= 0.0:
        raise ValueError("total_generation_mwh must be positive")
    if not (0.0 <= mechanism_quantity_mwh <= total_generation_mwh):
        raise ValueError("mechanism quantity must be within total generation")

    market_revenue = market_price * total_generation_mwh * 1000.0
    transfer = (mechanism_price - market_price) * mechanism_quantity_mwh * 1000.0
    certificate_revenue = green_certificate_price * total_generation_mwh
    energy_revenue = market_revenue + transfer
    total_revenue = energy_revenue + certificate_revenue

    return {
        "coverage": mechanism_quantity_mwh / total_generation_mwh,
        "market_revenue": market_revenue,
        "transfer": transfer,
        "certificate_revenue": certificate_revenue,
        "energy_revenue": energy_revenue,
        "total_revenue": total_revenue,
        "effective_energy_price": energy_revenue / (total_generation_mwh * 1000.0),
        "all_in_price": total_revenue / (total_generation_mwh * 1000.0),
    }


def break_even_mechanism_price(
    lcoe: float,
    market_price: float,
    coverage: float,
    other_revenue_per_mwh: float = 0.0,
) -> float:
    """Mechanism price that makes the covered quantity cover the LCOE.

    lcoe, market_price and other_revenue_per_mwh are all in CNY/MWh; the
    returned mechanism price is also CNY/MWh. This is a pre-tax, levelised
    break-even, not an after-tax bid floor. other_revenue_per_mwh covers
    certificates or other per-MWh income.
    """
    if not (0.0 < coverage <= 1.0):
        raise ValueError("coverage must be in (0, 1]")
    return (lcoe - market_price * (1.0 - coverage) - other_revenue_per_mwh) / coverage


def capture_price(market_price: float, capture_rate: float) -> float:
    """Generation-weighted price actually captured by a variable resource."""
    return market_price * capture_rate
