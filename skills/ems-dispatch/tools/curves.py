"""Deterministic synthetic curves for the EMS worked examples.

All profiles are code-generated, not measured data. They exist so that the
numbers quoted in SKILL.md and in the two knowledge drafts can be reproduced
by ``python tools/selftest.py``. Replace every curve with site data before any
project decision.
"""

from __future__ import annotations

import math


def _gauss(x, center, width):
    return math.exp(-0.5 * ((x - center) / width) ** 2)


def storage_day_prices(n=24):
    """24 hourly prices (CNY/MWh): valley 200, flat 450, peak 900."""
    if n != 24:
        raise ValueError("the storage example uses 24 hourly points")
    prices = []
    for k in range(n):
        if k < 8:
            prices.append(200.0)
        elif k < 18:
            prices.append(450.0)
        elif k < 22:
            prices.append(900.0)
        else:
            prices.append(450.0)
    return prices


def microgrid_day(n=96):
    """Microgrid example: dual-peak load, 500 kW PV, four-tier TOU tariff."""
    if n != 96:
        raise ValueError("the microgrid example uses 96 fifteen-minute points")
    dt = 24.0 / n
    load = []
    pv = []
    buy = []
    for k in range(n):
        h = (k + 0.5) * dt
        load.append(
            400.0
            + 480.0 * _gauss(h, 10.5, 1.5)
            + 480.0 * _gauss(h, 19.5, 1.6)
        )
        if 6.0 <= h <= 18.0:
            pv.append(500.0 * math.sin(math.pi * (h - 6.0) / 12.0) ** 1.3)
        else:
            pv.append(0.0)
        if h < 7.0:
            buy.append(0.30)
        elif h < 10.0:
            buy.append(0.65)
        elif h < 15.0:
            buy.append(1.05)
        elif h < 18.0:
            buy.append(0.65)
        elif h < 21.0:
            buy.append(1.05)
        elif h < 23.0:
            buy.append(1.25)
        else:
            buy.append(0.65)
    return {
        "dt_h": dt,
        "load_kw": load,
        "pv_kw": pv,
        "buy_price": buy,
        "sell_price": [0.0] * n,
    }


def user_day(n=96, peak_kw=12000.0, valley_kw=6000.0):
    """User-side load with a single evening peak and 350/700/1050 TOU."""
    if n != 96:
        raise ValueError("the user-side example uses 96 fifteen-minute points")
    dt = 24.0 / n
    load = []
    buy = []
    for k in range(n):
        h = (k + 0.5) * dt
        load.append(valley_kw + (peak_kw - valley_kw) * _gauss(h, 19.0, 2.0))
        if h < 8.0:
            buy.append(0.35)
        elif h < 10.0:
            buy.append(0.70)
        elif h < 15.0:
            buy.append(1.05)
        elif h < 18.0:
            buy.append(0.70)
        elif h < 21.0:
            buy.append(1.05)
        else:
            buy.append(0.70)
    return {
        "dt_h": dt,
        "load_kw": load,
        "pv_kw": [0.0] * n,
        "buy_price": buy,
        "sell_price": [0.0] * n,
    }
