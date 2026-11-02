"""Carbon-finance mechanics: pledge value, margin trigger, forward payoff.

Standard library only. These are risk tools, not trading recommendations.
"""

from __future__ import annotations


def pledge_value(quantity, price, haircut=0.6):
    """Loan collateral value for allowances pledged at a haircut."""
    if quantity < 0 or price < 0:
        raise ValueError("quantity and price must be non-negative")
    if not 0 < haircut <= 1:
        raise ValueError("haircut must be in (0, 1]")
    return quantity * price * haircut


def margin_call_price(loan, quantity, max_ltv=0.8):
    """Collateral price at which loan-to-value reaches the trigger."""
    if loan < 0 or quantity <= 0:
        raise ValueError("loan must be non-negative and quantity positive")
    if not 0 < max_ltv <= 1:
        raise ValueError("max_ltv must be in (0, 1]")
    return loan / (quantity * max_ltv)


def carbon_linked_loan_savings(principal, rate_step_down, years=1.0):
    """Interest saved when a carbon-linked loan steps the rate down.

    rate_step_down is an absolute rate (0.002 = 20 bp), not a percentage.
    """
    if principal < 0 or years < 0:
        raise ValueError("principal and years must be non-negative")
    if not 0 <= rate_step_down < 1:
        raise ValueError("rate_step_down must be in [0, 1)")
    return principal * rate_step_down * years


def forward_payoff(quantity, forward_price, spot_price, side="sell"):
    """Realised gain (positive) or loss (negative) versus the forward contract."""
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    if side not in ("sell", "buy"):
        raise ValueError("side must be 'sell' or 'buy'")
    sign = 1 if side == "sell" else -1
    return sign * quantity * (forward_price - spot_price)
