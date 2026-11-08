"""Time-of-use period handling and load shifting.

Conventions
-----------
* Load is in kW, prices in CNY/kWh, energy in kWh and cost in CNY.
* A period table is a list of ``(name, start_hour, end_hour)`` tuples that must
  cover every hour of the day exactly once. Names may repeat (for example two
  ``peak`` windows); ``validate_periods`` only rejects gaps and overlaps.
* ``dt_h`` must divide the day into equal intervals; interval ``i`` is assigned
  to the integer hour it starts in, so a 15-minute interval at 19.25 maps to
  hour 19.
"""

from __future__ import annotations

import curves


def validate_periods(periods=None):
    """Return the hour-to-period map, raising on gaps or overlaps."""
    periods = curves.tou_periods() if periods is None else list(periods)
    hours = [None] * 24
    for name, start, end in periods:
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= 24):
            raise ValueError(f"invalid period window: {(name, start, end)}")
        for hour in range(start, end):
            if hours[hour] is not None:
                raise ValueError(f"hour {hour} assigned to both {hours[hour]} and {name}")
            hours[hour] = name
    missing = [hour for hour, name in enumerate(hours) if name is None]
    if missing:
        raise ValueError(f"hours not covered: {missing}")
    return hours


def period_hours(periods=None):
    """Total hours assigned to each period name."""
    periods = curves.tou_periods() if periods is None else list(periods)
    result = {}
    for name, start, end in periods:
        result[name] = result.get(name, 0) + (end - start)
    return result


def tou_energy_cost(load_kw, prices, periods=None, dt_h=1.0):
    """Energy and cost by period for one day.

    ``prices`` maps period name to CNY/kWh. Returns total energy, total cost,
    average price and a per-period breakdown.
    """
    hours = validate_periods(periods)
    if abs(len(load_kw) * dt_h - 24.0) > 1e-9:
        raise ValueError("len(load_kw) * dt_h must equal 24 hours")
    by_period = {}
    total_cost = 0.0
    for i, power in enumerate(load_kw):
        hour = int(i * dt_h + 1e-9)
        name = hours[hour]
        if name not in prices:
            raise ValueError(f"missing price for period {name}")
        kwh = float(power) * dt_h
        cost = kwh * float(prices[name])
        total_cost += cost
        row = by_period.setdefault(name, {"kwh": 0.0, "cost": 0.0})
        row["kwh"] += kwh
        row["cost"] += cost
    energy = sum(row["kwh"] for row in by_period.values())
    return {
        "energy_kwh": energy,
        "cost": total_cost,
        "average_price": total_cost / energy if energy else 0.0,
        "by_period": by_period,
    }


def shift_energy(
    load_kw,
    prices,
    source_period,
    target_period,
    energy_kwh,
    periods=None,
    dt_h=1.0,
    max_power_kw=None,
):
    """Move energy from the most expensive source intervals to the cheapest targets.

    This is the textbook transportation problem with independent interval
    capacities, so filling the cheapest target intervals first is optimal for
    the requested block. A move only happens when the source price is strictly
    above the target price. ``max_power_kw`` caps the load after the move and
    defaults to the current peak.
    """
    hours = validate_periods(periods)
    if abs(len(load_kw) * dt_h - 24.0) > 1e-9:
        raise ValueError("len(load_kw) * dt_h must equal 24 hours")
    max_power = max(load_kw) if max_power_kw is None else float(max_power_kw)
    if max_power < max(load_kw):
        raise ValueError("max_power_kw must not be below the current peak")

    source_idx = [i for i in range(len(load_kw)) if hours[int(i * dt_h + 1e-9)] == source_period]
    target_idx = [i for i in range(len(load_kw)) if hours[int(i * dt_h + 1e-9)] == target_period]
    if not source_idx or not target_idx:
        raise ValueError("source and target periods must both appear in the table")

    targets = []
    for i in target_idx:
        room = (max_power - float(load_kw[i])) * dt_h
        if room > 1e-9:
            targets.append([float(prices[target_period]), i, room, 0.0])
    targets.sort()

    before = tou_energy_cost(load_kw, prices, periods, dt_h)
    new_load = [float(value) for value in load_kw]
    remaining = float(energy_kwh)
    moved = 0.0
    source_detail = []
    for i in sorted(source_idx, key=lambda j: prices[source_period], reverse=True):
        if remaining <= 1e-9:
            break
        source_price = float(prices[source_period])
        available = new_load[i] * dt_h
        taken = 0.0
        for target in targets:
            if remaining <= 1e-9 or available <= 1e-9:
                break
            target_price, j, room, used = target
            if target_price >= source_price:
                continue
            take = min(remaining, available, room - used)
            if take <= 1e-9:
                continue
            target[3] = used + take
            new_load[j] += take / dt_h
            new_load[i] -= take / dt_h
            available -= take
            remaining -= take
            moved += take
            taken += take
        if taken > 0:
            source_detail.append({"interval": i, "kwh": taken, "price": source_price})

    after = tou_energy_cost(new_load, prices, periods, dt_h)
    target_detail = []
    for price, j, room, used in targets:
        if used > 0:
            target_detail.append({"interval": j, "kwh": used, "price": price})
    return {
        "moved_kwh": moved,
        "new_load_kw": new_load,
        "cost_before": before["cost"],
        "cost_after": after["cost"],
        "saving": before["cost"] - after["cost"],
        "source": source_detail,
        "target": target_detail,
    }
