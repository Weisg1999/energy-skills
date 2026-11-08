"""Declared-demand optimisation and comparison of the three basic-charge modes.

The closed form follows from the bill formula
``charge = price * (D + m * max(A - k * D, 0))`` with ``k`` the 105% threshold
and ``m`` the overrun multiplier. For ``D >= A / k`` the charge grows with D;
below ``A / k`` it falls as D rises. The optimum is therefore
``D* = max(floor, A / k)``, capped by the transformer capacity.
"""

from __future__ import annotations

import bill


def optimal_declared(
    actual_max_kw,
    price_per_kw_month,
    floor_kw=0.0,
    cap_kw=None,
    threshold=1.05,
    overrun_multiplier=2.0,
):
    """Cost-minimising declared demand for one month."""
    actual = float(actual_max_kw)
    target = max(float(floor_kw), actual / float(threshold))
    if cap_kw is not None:
        target = min(target, float(cap_kw))
    if target < 0:
        raise ValueError("declared demand must be non-negative")
    row = bill.basic_charge_demand(
        target,
        actual,
        price_per_kw_month,
        threshold=threshold,
        overrun_multiplier=overrun_multiplier,
        floor_kw=0.0,
    )
    row["optimal"] = True
    return row


def annual_contract_demand(
    monthly_max_kw,
    price_per_kw_month,
    floor_kw=0.0,
    cap_kw=None,
    threshold=1.05,
    overrun_multiplier=2.0,
):
    """Optimise the declared demand month by month.

    ``monthly_max_kw`` may be a list or a dict keyed 1-12; order is preserved
    for lists and sorted by month for dicts.
    """
    items = list(monthly_max_kw.items()) if isinstance(monthly_max_kw, dict) else list(enumerate(monthly_max_kw, 1))
    detail = []
    total = 0.0
    for month, actual in items:
        row = optimal_declared(
            actual,
            price_per_kw_month,
            floor_kw=floor_kw,
            cap_kw=cap_kw,
            threshold=threshold,
            overrun_multiplier=overrun_multiplier,
        )
        row["month"] = month
        detail.append(row)
        total += row["charge"]
    return {"months": len(detail), "total": total, "detail": detail}


def compare_modes(
    monthly_max_kw,
    *,
    demand_price,
    capacity_price,
    transformer_kva,
    floor_ratio=0.4,
    cap_kw=None,
    threshold=1.05,
    overrun_multiplier=2.0,
):
    """Compare capacity, contracted-demand and actual-demand billing.

    ``floor_ratio`` is applied to the transformer capacity only; provinces that
    include high-voltage motors in the 40% floor need a larger base.
    """
    actual = list(monthly_max_kw.values()) if isinstance(monthly_max_kw, dict) else list(monthly_max_kw)
    months = len(actual)
    capacity = bill.basic_charge_capacity(transformer_kva, capacity_price)["charge"] * months
    contract = annual_contract_demand(
        monthly_max_kw,
        demand_price,
        floor_kw=float(floor_ratio) * float(transformer_kva),
        cap_kw=transformer_kva if cap_kw is None else cap_kw,
        threshold=threshold,
        overrun_multiplier=overrun_multiplier,
    )
    actual_mode = sum(
        bill.basic_charge_actual(value, demand_price)["charge"] for value in actual
    )
    rows = {
        "capacity": {"total": capacity, "average_month": capacity / months},
        "contract": {"total": contract["total"], "average_month": contract["total"] / months, "detail": contract},
        "actual": {"total": actual_mode, "average_month": actual_mode / months},
    }
    best = min(rows, key=lambda name: rows[name]["total"])
    return {"months": months, "rows": rows, "best": best, "saving_vs_worst": rows[max(rows, key=lambda n: rows[n]["total"])]["total"] - rows[best]["total"]}
