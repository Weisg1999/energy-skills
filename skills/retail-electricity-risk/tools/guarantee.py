"""Performance-guarantee sizing and funding cost for retail sellers.

Two calibres are implemented: the current 2021 measure (1595) and the
2026 draft (annual sales x base rate x coefficient). The draft is not law.
"""


def current_guarantee(annual_wholesale_kwh, peak_two_month_kwh,
                      annual_rate=0.008, peak_rate=0.05):
    """max(12-month wholesale energy x 0.8 fen, 2-month peak energy x 5 fen)."""
    if annual_wholesale_kwh < 0 or peak_two_month_kwh < 0:
        raise ValueError("energy inputs must be non-negative")
    by_annual = annual_wholesale_kwh * annual_rate
    by_peak = peak_two_month_kwh * peak_rate
    return max(by_annual, by_peak)


def draft_guarantee(annual_sales_kwh, coefficient=1.0, base_rate=0.01, minimum=2_000_000.0):
    """Draft formula: max(minimum, annual sales x 1 fen/kWh x coefficient)."""
    if annual_sales_kwh < 0:
        raise ValueError("annual_sales_kwh must be non-negative")
    if not 1.0 <= coefficient <= 10.0:
        raise ValueError("coefficient must be in [1, 10]")
    return max(minimum, annual_sales_kwh * base_rate * coefficient)


def funding_cost(amount, annual_fee_rate):
    """Annual cost of a guarantee or cash deposit."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if annual_fee_rate < 0:
        raise ValueError("annual_fee_rate must be non-negative")
    return amount * annual_fee_rate


def collateral_gap(required, submitted):
    """Shortfall of submitted collateral against the required amount."""
    if required < 0 or submitted < 0:
        raise ValueError("amounts must be non-negative")
    gap = max(required - submitted, 0.0)
    return {"required": required, "submitted": submitted, "gap": gap,
            "status": "ok" if gap == 0 else "shortfall"}
