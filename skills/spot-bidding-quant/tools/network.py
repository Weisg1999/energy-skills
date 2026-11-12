"""Two-node grid-constraint primitives for power bidding (pure standard library).

Reference implementations for the chain in ``knowledge/省间与跨区交易-2026-11.md``
§5.5-5.6: how a transmission limit splits one uniform price into locational
prices, and how the tradeable limit moves with outages, N-1 and reserve.

Division of labour: ``electricity-trading-expert/tools/market.py`` already owns
``congestion_surplus``, ``ftr_payout`` and LMP decomposition. This module does
NOT re-implement them; it only produces the clearing state, the location basis
and dynamic ATC. The ``congestion_rent`` field returned by ``two_node_clearing``
uses the same (p_sink - p_source) x flow calibre and is cross-checked in
``selftest.py`` against that module's documented example.

This is a deliberately small two-node model with single-segment supply at each
node. It is for teaching the calibre, not for simulating a real market.
"""

from __future__ import annotations


def two_node_clearing(c_a: float, cap_a: float, c_b: float, cap_b: float,
                      d_a: float, d_b: float, line_limit: float) -> dict:
    """Clear a cheap exporting node A and an expensive importing node B.

    A serves its own load first, then exports up to line_limit. If B still
    needs its own (expensive) unit, the line is congested and prices separate.
    Returns locational prices, flow, dispatch, congestion flag and the
    merchandising surplus (price difference times the constrained flow).
    """
    if c_a >= c_b:
        raise ValueError("node A must be the cheaper exporter")
    if min(cap_a, cap_b, d_a, d_b, line_limit) < 0:
        raise ValueError("capacities, demand and line limit must be non-negative")
    flow = min(line_limit, d_b, max(0.0, cap_a - d_a))
    g_a = d_a + flow
    g_b = d_b - flow
    if g_a > cap_a + 1e-9 or g_b > cap_b + 1e-9:
        raise ValueError("insufficient generation capacity at one node")
    congested = flow < d_b - 1e-9 and g_b > 0
    if congested:
        p_a, p_b = c_a, c_b
    else:
        p = c_a if g_b <= 1e-9 else c_b
        p_a = p_b = p
    return {
        "p_a": p_a,
        "p_b": p_b,
        "flow_mw": flow,
        "gen_a_mw": g_a,
        "gen_b_mw": g_b,
        "congested": congested,
        "congestion_rent": (p_b - p_a) * flow,
        "unbounded_price": c_a if (d_a + d_b) <= cap_a else c_b,
    }


def location_basis(p_node: float, p_hub: float) -> float:
    """Node price minus hub price; the quantity an FTR is meant to hedge."""
    return p_node - p_hub


def available_transfer_capability(nominal_mw: float,
                                  outage_derate: float = 0.0,
                                  n1_derate: float = 0.0,
                                  reserve_margin: float = 0.0) -> float:
    """Dynamic ATC after maintenance, N-1 and operating-reserve derates.

    The point is that the tradeable limit is not the nameplate rating: it moves
    with the outage schedule, security checks and the reserve kept for contingencies.
    """
    for name, x in (("outage_derate", outage_derate),
                    ("n1_derate", n1_derate),
                    ("reserve_margin", reserve_margin)):
        if not 0.0 <= x < 1.0:
            raise ValueError(f"{name} must be in [0, 1)")
    if nominal_mw <= 0:
        raise ValueError("nominal_mw must be positive")
    return nominal_mw * (1.0 - outage_derate) * (1.0 - n1_derate) * (1.0 - reserve_margin)
