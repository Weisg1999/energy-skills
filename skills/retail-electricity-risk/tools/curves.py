"""Synthetic load and price curves for the retail-electricity examples.

All data are grade-D synthetic and correspond to no real province or company.
"""

MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

MONTH_FACTORS = (0.93, 0.92, 0.96, 0.98, 1.00, 1.04, 1.08, 1.10, 1.02, 0.99, 0.95, 0.93)

SPOT_TOU_PRICES = {"valley": 0.30, "flat": 0.46, "peak": 0.70, "critical": 0.88}

_PERIODS = (
    ("valley", 0, 8),
    ("flat", 8, 10),
    ("peak", 10, 12),
    ("flat", 12, 18),
    ("peak", 18, 19),
    ("critical", 19, 20),
    ("peak", 20, 21),
    ("flat", 21, 23),
    ("valley", 23, 24),
)

_SHAPE_ANCHORS = {
    "industrial": (
        (0, 0.46), (6, 0.52), (8, 0.78), (10, 0.92), (12, 0.82),
        (14, 0.88), (18, 0.90), (19, 1.00), (21, 0.80), (24, 0.48),
    ),
    "commercial": (
        (0, 0.18), (7, 0.22), (9, 0.72), (12, 0.94), (14, 0.88),
        (18, 0.96), (21, 0.70), (23, 0.30), (24, 0.18),
    ),
    "ev": (
        (0, 0.55), (6, 0.35), (9, 0.42), (17, 0.55), (21, 0.92), (24, 0.62),
    ),
}


def tou_periods(n=96):
    """Return the period of each of n equal intervals over 24 hours."""
    if n <= 0:
        raise ValueError("n must be positive")
    step = 24.0 / n
    out = []
    for i in range(n):
        hour = i * step + step / 2.0
        for name, start, end in _PERIODS:
            if start <= hour < end:
                out.append(name)
                break
        else:
            raise ValueError(f"hour {hour} not covered")
    return out


def tou_prices(periods=None):
    periods = periods or tou_periods()
    return [SPOT_TOU_PRICES[p] for p in periods]


def base_spot_average():
    prices = tou_prices()
    return sum(prices) / len(prices)


def _interp(anchors, x):
    for i in range(len(anchors) - 1):
        x0, y0 = anchors[i]
        x1, y1 = anchors[i + 1]
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return anchors[-1][1]


def day_shape(kind, n=96):
    """Normalised 24-hour load shape; the values sum to 1."""
    if kind not in _SHAPE_ANCHORS:
        raise ValueError(f"unknown customer kind: {kind}")
    anchors = _SHAPE_ANCHORS[kind]
    step = 24.0 / n
    raw = [_interp(anchors, (i + 0.5) * step) for i in range(n)]
    total = sum(raw)
    return [v / total for v in raw]


def monthly_energy(annual_kwh, kind="industrial"):
    """Split annual energy into 12 months using seasonality and day counts."""
    if annual_kwh <= 0:
        raise ValueError("annual_kwh must be positive")
    weights = [MONTH_FACTORS[i] * MONTH_DAYS[i] for i in range(12)]
    total = sum(weights)
    return [annual_kwh * w / total for w in weights]


def spot_monthly(level=1.0):
    """Monthly average spot prices, normalised so the annual mean equals level."""
    if level <= 0:
        raise ValueError("level must be positive")
    raw = list(MONTH_FACTORS)
    mean = sum(raw) / 12.0
    return [level * v / mean for v in raw]


def customers():
    """A four-customer synthetic retail portfolio."""
    return [
        {"name": "industrial A", "annual_kwh": 30e6, "retail_price": 0.46, "kind": "industrial"},
        {"name": "commercial B", "annual_kwh": 20e6, "retail_price": 0.49, "kind": "commercial"},
        {"name": "EV fleet C", "annual_kwh": 10e6, "retail_price": 0.53, "kind": "ev"},
        {"name": "candidate D", "annual_kwh": 5e6, "retail_price": 0.43, "kind": "industrial"},
    ]
