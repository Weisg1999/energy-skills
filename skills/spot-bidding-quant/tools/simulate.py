"""A deliberately small competitive-bidding sandbox.

Clears a merit-order stack from submitted curves, reports concentration, and
sweeps a bidder's price to show the dispatch cliff. It is not a SCUC engine:
unit commitment, network limits, reserves and inter-temporal constraints need
a production dispatch model (PyPSA or equivalent).

Nothing here is a trading strategy. The sweep exists to show how much of a
unit's revenue comes from being infra-marginal rather than from clever pricing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Participant:
    name: str
    segments: list[tuple[float, float]] = field(default_factory=list)  # (price, mw)
    cost: float = 0.0
    capacity: float = 0.0


def clear(participants: list[Participant], demand_mw: float, floor: float = -100.0, cap: float = 1500.0) -> dict:
    """Pay-as-clear merit order: sort submitted segments, walk demand, price at margin."""
    offers = []
    for p in participants:
        for price, mw in p.segments:
            if mw <= 0:
                continue
            offers.append((min(max(price, floor), cap), mw, p.name))
    offers.sort(key=lambda row: (row[0], row[1]))

    remaining = demand_mw
    dispatched: dict[str, float] = {p.name: 0.0 for p in participants}
    clearing_price = floor
    for price, mw, name in offers:
        if remaining <= 0:
            break
        take = min(mw, remaining)
        dispatched[name] += take
        remaining -= take
        clearing_price = price

    return {
        "clearing_price": clearing_price,
        "served_mw": demand_mw - max(remaining, 0.0),
        "unserved_mw": max(remaining, 0.0),
        "dispatched": dispatched,
        "hhi": hhi(dispatched),
    }


def hhi(dispatched: dict[str, float]) -> float:
    total = sum(dispatched.values())
    if total <= 0:
        return 0.0
    return sum((v / total) ** 2 for v in dispatched.values()) * 10000.0


def bid_sweep(
    participants: list[Participant],
    demand_mw: float,
    own_name: str,
    prices: list[float],
    floor: float = -100.0,
    cap: float = 1500.0,
) -> list[dict]:
    """Hold rivals at their curves and sweep one bidder's single-segment bid.

    Reveals the step function a trader actually faces: below the marginal rival
    you are fully dispatched and the clearing price is set by someone else;
    above it you lose the volume entirely; only when you are pivotal does your
    own bid set the price.
    """
    own = next(p for p in participants if p.name == own_name)
    original = list(own.segments)
    rows = []
    try:
        for bid in prices:
            own.segments = [(bid, own.capacity)]
            result = clear(participants, demand_mw, floor, cap)
            mw = result["dispatched"][own_name]
            rows.append(
                {
                    "bid": round(bid, 2),
                    "clearing_price": result["clearing_price"],
                    "dispatched_mw": mw,
                    "profit": round(mw * (result["clearing_price"] - own.cost), 2),
                    "sets_price": abs(result["clearing_price"] - min(max(bid, floor), cap)) < 1e-9 and mw > 0,
                }
            )
    finally:
        own.segments = original
    return rows
