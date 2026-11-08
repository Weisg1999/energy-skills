"""Synthetic load, tariff and market-price curves for the worked examples.

All series are deterministic and synthetic (grade D). They illustrate model
behaviour and are not a forecast for any real customer or province.
"""

from __future__ import annotations

# Four-period table used by the examples: valley, flat, peak and critical.
# Every hour of the day is assigned exactly once; ``tariff.validate_periods``
# enforces that.
PERIODS = [
    ("valley", 0, 8),
    ("flat", 8, 10),
    ("peak", 10, 12),
    ("flat", 12, 18),
    ("peak", 18, 19),
    ("critical", 19, 20),
    ("peak", 20, 21),
    ("flat", 21, 23),
    ("valley", 23, 24),
]

TOU_PRICES = {"valley": 0.30, "flat": 0.62, "peak": 1.05, "critical": 1.26}

# Piecewise-linear industrial load, in kW. The evening maximum sits inside the
# critical period; the night base keeps the valley period busy.
_LOAD_ANCHORS = [
    (0, 480),
    (6, 480),
    (7, 700),
    (8, 900),
    (10, 1120),
    (12, 1050),
    (13, 820),
    (14, 980),
    (17, 1000),
    (18, 900),
    (19, 1150),
    (20, 1100),
    (21, 900),
    (22, 700),
    (23, 520),
    (24, 480),
]

# Monthly scaling of the representative day, January to December.
MONTH_FACTORS = (0.82, 0.80, 0.90, 0.94, 0.98, 1.04, 1.10, 1.14, 1.02, 0.96, 0.88, 0.84)

# 2026 is not a leap year.
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Synthetic day-ahead energy price, CNY/kWh, with a morning plateau and an
# evening spike. Monthly variation is left to the scenario multipliers.
_MARKET_ANCHORS = [
    (0, 0.26),
    (6, 0.28),
    (8, 0.46),
    (10, 0.64),
    (12, 0.55),
    (14, 0.42),
    (17, 0.50),
    (19, 0.86),
    (20, 0.72),
    (21, 0.58),
    (22, 0.38),
    (24, 0.28),
]


def _interp(anchors, hour):
    for (h0, v0), (h1, v1) in zip(anchors, anchors[1:]):
        if h0 <= hour <= h1:
            if h1 == h0:
                return float(v1)
            return v0 + (v1 - v0) * (hour - h0) / (h1 - h0)
    return float(anchors[-1][1])


def tou_periods():
    """Return the period table as ``(name, start_hour, end_hour)`` tuples."""
    return list(PERIODS)


def tou_prices():
    """Return a copy of the synthetic four-period tariff, CNY/kWh."""
    return dict(TOU_PRICES)


def industrial_day(n=96, scale=1.0):
    """Synthetic industrial load, ``n`` intervals of ``24 / n`` hours."""
    dt = 24.0 / n
    return [_interp(_LOAD_ANCHORS, i * dt) * float(scale) for i in range(n)]


def monthly_loads(n=96):
    """Representative-day load for each month, keyed 1-12."""
    base = industrial_day(n)
    return {month: [value * factor for value in base] for month, factor in enumerate(MONTH_FACTORS, 1)}


def market_day(n=96, scale=1.0):
    """Synthetic day-ahead price curve, CNY/kWh."""
    dt = 24.0 / n
    return [_interp(_MARKET_ANCHORS, i * dt) * float(scale) for i in range(n)]
