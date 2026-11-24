"""A small, transparent SCED/SCUC clearing sandbox (standard library only).

The point is not to replace a production market-clearing engine. It is to make
the chain visible: bid segments -> feasible dispatch -> marginal price ->
make-whole uplift, and, across periods, commitment -> startup -> price.

Assumptions are deliberately limited and stated:

* one node, energy-only. Network limits, losses and reserve co-optimisation
  stay in ``network.py`` and in the knowledge module's references;
* a unit's minimum-output block has its own offer price; incremental segments
  are stacked above it;
* SCED is a deterministic merit-order walk over incremental segments;
* SCUC enumerates commitment states (small systems only), checks minimum
  up/down times and ramp between consecutive online periods, and clears each
  period with SCED;
* prices are as-bid marginal segment prices. With non-convex minimum output or
  block offers, a uniform price may not cover a unit's as-bid cost; the
  shortfall is reported as make-whole uplift rather than hidden.

All example data are synthetic grade D. Nothing here is a market forecast,
settlement instruction or trading recommendation.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass


EPS = 1e-9


@dataclass(frozen=True)
class Unit:
    """A thermal unit with a minimum-output block and incremental segments."""

    name: str
    pmin: float
    pmax: float
    pmin_price: float
    segments: tuple[tuple[float, float], ...]
    min_up: int = 1
    min_down: int = 1
    startup: float = 0.0
    no_load: float = 0.0
    initial_on: bool = False
    initial_hours: int = 0
    must_run: bool = False
    ramp_up: float | None = None
    ramp_down: float | None = None

    def validate(self) -> None:
        if self.pmin < 0.0 or self.pmax <= 0.0 or self.pmin > self.pmax + EPS:
            raise ValueError(f"{self.name}: require 0 <= pmin <= pmax")
        if self.min_up < 1 or self.min_down < 1:
            raise ValueError(f"{self.name}: min_up and min_down must be at least 1")
        if self.initial_hours < 0:
            raise ValueError(f"{self.name}: initial_hours must be non-negative")
        total = 0.0
        last_price = self.pmin_price
        for price, mw in self.segments:
            if mw <= 0.0:
                raise ValueError(f"{self.name}: segment MW must be positive")
            if price < last_price - EPS:
                raise ValueError(f"{self.name}: offer prices must be non-decreasing")
            last_price = price
            total += mw
        if abs(total - (self.pmax - self.pmin)) > 1e-6:
            raise ValueError(
                f"{self.name}: incremental segments sum to {total}, "
                f"expected pmax - pmin = {self.pmax - self.pmin}"
            )


def _validate_units(units: list[Unit]) -> None:
    if not units:
        raise ValueError("at least one unit is required")
    names = set()
    for unit in units:
        unit.validate()
        if unit.name in names:
            raise ValueError(f"duplicate unit name: {unit.name}")
        names.add(unit.name)


def _offer_rows(units: list[Unit]) -> list[dict]:
    rows = []
    for unit in units:
        rows.append(
            {
                "unit": unit.name,
                "price": unit.pmin_price,
                "mw": unit.pmin,
                "kind": "minimum output",
            }
        )
        for price, mw in unit.segments:
            rows.append({"unit": unit.name, "price": price, "mw": mw, "kind": "incremental"})
    rows.sort(key=lambda row: (row["price"], 0 if row["kind"] == "minimum output" else 1, row["unit"]))
    return rows


def clear_sced(
    units: list[Unit],
    demand_mw: float,
    floor: float = -100.0,
    cap: float = 1500.0,
) -> dict:
    """Clear one period by walking incremental offers above minimum output.

    All units passed in are treated as online. If total minimum output exceeds
    demand, the system over-generates and the price sits at the floor. If demand
    exceeds total capacity, the price sits at the cap and unserved load is
    reported. Neither case is silently "fixed".
    """
    _validate_units(units)
    if demand_mw < 0.0:
        raise ValueError("demand must be non-negative")
    if floor > cap:
        raise ValueError("floor must not exceed cap")

    total_pmin = sum(unit.pmin for unit in units)
    total_pmax = sum(unit.pmax for unit in units)
    dispatch = {unit.name: 0.0 for unit in units}
    cost_by_unit = {unit.name: 0.0 for unit in units}
    offers = _offer_rows(units)

    if demand_mw < total_pmin - EPS:
        for unit in units:
            dispatch[unit.name] = unit.pmin
            cost_by_unit[unit.name] = unit.pmin * unit.pmin_price
        price = floor
        overgeneration = total_pmin - demand_mw
        unserved = 0.0
        marginal_unit = "price floor"
        accepted = []
    elif demand_mw > total_pmax + EPS:
        for unit in units:
            dispatch[unit.name] = unit.pmax
            cost_by_unit[unit.name] = unit.pmin * unit.pmin_price + sum(
                price * mw for price, mw in unit.segments
            )
        price = cap
        overgeneration = 0.0
        unserved = demand_mw - total_pmax
        marginal_unit = "price cap"
        accepted = offers
    else:
        for unit in units:
            dispatch[unit.name] = unit.pmin
            cost_by_unit[unit.name] = unit.pmin * unit.pmin_price
        remaining = demand_mw - total_pmin
        accepted = []
        marginal_unit = "minimum-output boundary"
        marginal_price = max(unit.pmin_price for unit in units)
        for row in offers:
            if row["kind"] != "incremental":
                continue
            if remaining <= EPS:
                break
            unit = next(u for u in units if u.name == row["unit"])
            take = min(row["mw"], remaining)
            dispatch[unit.name] += take
            cost_by_unit[unit.name] += take * row["price"]
            accepted.append({**row, "taken": take})
            remaining -= take
            marginal_price = row["price"]
            marginal_unit = unit.name
        price = min(max(marginal_price, floor), cap)
        overgeneration = 0.0
        unserved = 0.0

    price = float(price)
    revenue_by_unit = {
        name: dispatch[name] * price for name in dispatch
    }
    uplift_by_unit = {
        name: max(0.0, cost_by_unit[name] - revenue_by_unit[name]) for name in dispatch
    }
    rent_by_unit = {
        name: max(0.0, revenue_by_unit[name] - cost_by_unit[name]) for name in dispatch
    }
    total_cost = sum(cost_by_unit.values())
    total_revenue = sum(revenue_by_unit.values())
    total_uplift = sum(uplift_by_unit.values())

    return {
        "price": price,
        "dispatch": dispatch,
        "cost_by_unit": cost_by_unit,
        "revenue_by_unit": revenue_by_unit,
        "uplift_by_unit": uplift_by_unit,
        "rent_by_unit": rent_by_unit,
        "total_cost": total_cost,
        "total_revenue": total_revenue,
        "total_uplift": total_uplift,
        "total_rent": sum(rent_by_unit.values()),
        "overgeneration_mw": overgeneration,
        "unserved_mw": unserved,
        "marginal_unit": marginal_unit,
        "accepted_segments": accepted,
        "offers": offers,
    }


def _valid_schedule(units: list[Unit], schedule: tuple[tuple[bool, ...], ...]) -> bool:
    """Check minimum up/down runs, including the pre-horizon initial state."""
    periods = len(schedule)
    for i, unit in enumerate(units):
        status = [unit.initial_on] + [schedule[t][i] for t in range(periods)]
        if unit.must_run and not all(status[1:]):
            return False
        run_state = status[0]
        run_length = 1
        runs: list[tuple[bool, int]] = []
        for value in status[1:]:
            if value == run_state:
                run_length += 1
            else:
                runs.append((run_state, run_length))
                run_state = value
                run_length = 1
        runs.append((run_state, run_length))
        if runs and runs[0][0] == unit.initial_on:
            runs[0] = (runs[0][0], runs[0][1] + unit.initial_hours)
        for is_on, length in runs:
            required = unit.min_up if is_on else unit.min_down
            if length < required:
                return False
    return True


def _ramp_ok(units: list[Unit], previous: dict, current: dict) -> bool:
    for unit in units:
        if unit.ramp_up is None and unit.ramp_down is None:
            continue
        p0 = previous.get(unit.name, 0.0)
        p1 = current.get(unit.name, 0.0)
        if p0 <= EPS and p1 <= EPS:
            continue
        # Startup/shutdown transitions are governed by the unit's start/shutdown
        # capability, not by the on-line ramp between two dispatched periods.
        if p0 <= EPS or p1 <= EPS:
            continue
        if unit.ramp_up is not None and p1 - p0 > unit.ramp_up + EPS:
            return False
        if unit.ramp_down is not None and p0 - p1 > unit.ramp_down + EPS:
            return False
    return True


def clear_scuc(
    units: list[Unit],
    demand_profile: list[float] | tuple[float, ...],
    floor: float = -100.0,
    cap: float = 1500.0,
    max_states: int = 1_000_000,
) -> dict:
    """Enumerate commitment states, then clear each period by SCED.

    This is exact for small teaching cases, not a production SCUC solver. It
    checks must-run, minimum up/down and ramp between consecutive online
    periods. Startup and no-load costs enter the objective; a unit whose
    as-bid energy and commitment cost exceeds its energy revenue receives a
    make-whole uplift.
    """
    _validate_units(units)
    if not demand_profile:
        raise ValueError("demand_profile must not be empty")
    if any(d < 0.0 for d in demand_profile):
        raise ValueError("demand must be non-negative")
    periods = len(demand_profile)
    n = len(units)
    if n * periods > 20 or (1 << (n * periods)) > max_states:
        raise ValueError("too many commitment states for exact enumeration")
    states = list(itertools.product((False, True), repeat=n))
    best = None
    best_key = None

    for schedule in itertools.product(states, repeat=periods):
        if not _valid_schedule(units, schedule):
            continue
        period_rows = []
        previous_dispatch = {unit.name: 0.0 for unit in units}
        energy_cost = 0.0
        startup_cost = 0.0
        no_load_cost = 0.0
        revenue = 0.0
        uplift = 0.0
        feasible = True

        for t, mask in enumerate(schedule):
            online = [unit for unit, on in zip(units, mask) if on]
            if not online:
                feasible = False
                break
            result = clear_sced(online, demand_profile[t], floor, cap)
            if result["unserved_mw"] > EPS:
                feasible = False
                break
            if not _ramp_ok(units, previous_dispatch, result["dispatch"]):
                feasible = False
                break

            started = {
                unit.name: (mask[i] and not (schedule[t - 1][i] if t > 0 else unit.initial_on))
                for i, unit in enumerate(units)
            }
            period_startup = sum(
                unit.startup for unit in online if started[unit.name]
            )
            period_no_load = sum(unit.no_load for unit in online)
            period_energy = result["total_cost"]
            period_revenue = result["total_revenue"]
            period_uplift = 0.0
            for unit in online:
                unit_cost = result["cost_by_unit"][unit.name] + unit.no_load
                if started[unit.name]:
                    unit_cost += unit.startup
                period_uplift += max(0.0, unit_cost - result["revenue_by_unit"][unit.name])

            energy_cost += period_energy
            startup_cost += period_startup
            no_load_cost += period_no_load
            revenue += period_revenue
            uplift += period_uplift
            period_rows.append(
                {
                    "period": t,
                    "demand_mw": demand_profile[t],
                    "price": result["price"],
                    "dispatch": result["dispatch"],
                    "commitment": {unit.name: bool(mask[i]) for i, unit in enumerate(units)},
                    "startup": {unit.name: bool(started[unit.name]) for unit in units},
                    "energy_cost": period_energy,
                    "startup_cost": period_startup,
                    "no_load_cost": period_no_load,
                    "revenue": period_revenue,
                    "uplift": period_uplift,
                    "marginal_unit": result["marginal_unit"],
                    "overgeneration_mw": result["overgeneration_mw"],
                    "unserved_mw": result["unserved_mw"],
                }
            )
            previous_dispatch = result["dispatch"]

        if not feasible:
            continue
        total_cost = energy_cost + startup_cost + no_load_cost
        key = (round(total_cost, 6), schedule)
        if best_key is None or key < best_key:
            best_key = key
            best = {
                "periods": period_rows,
                "summary": {
                    "total_cost": total_cost,
                    "energy_cost": energy_cost,
                    "startup_cost": startup_cost,
                    "no_load_cost": no_load_cost,
                    "revenue": revenue,
                    "uplift": uplift,
                    "rent": revenue - total_cost,
                    "prices": [row["price"] for row in period_rows],
                    "dispatch": [
                        {name: row["dispatch"][name] for name in row["dispatch"]}
                        for row in period_rows
                    ],
                    "commitment": [
                        {name: bool(on) for name, on in row["commitment"].items()}
                        for row in period_rows
                    ],
                },
            }

    if best is None:
        raise ValueError("no feasible commitment schedule")
    return best


def demo_units() -> list[Unit]:
    """Three-unit synthetic system used by the worked examples and selftest."""
    return [
        Unit(
            name="coal-a",
            pmin=100.0,
            pmax=300.0,
            pmin_price=180.0,
            segments=((240.0, 100.0), (320.0, 100.0)),
            min_up=2,
            min_down=2,
            initial_on=True,
            initial_hours=2,
            ramp_up=150.0,
            ramp_down=150.0,
        ),
        Unit(
            name="coal-b",
            pmin=80.0,
            pmax=260.0,
            pmin_price=260.0,
            segments=((340.0, 110.0), (480.0, 70.0)),
            min_up=2,
            min_down=2,
            startup=6000.0,
            initial_on=False,
            initial_hours=2,
            ramp_up=160.0,
            ramp_down=160.0,
        ),
        Unit(
            name="gas-c",
            pmin=20.0,
            pmax=120.0,
            pmin_price=520.0,
            segments=((650.0, 100.0),),
            min_up=1,
            min_down=1,
            startup=1000.0,
            initial_on=False,
            initial_hours=1,
            ramp_up=120.0,
            ramp_down=120.0,
        ),
    ]


def _fmt(value: float) -> str:
    return f"{value:,.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Small SCED/SCUC clearing sandbox")
    parser.add_argument("--demo", action="store_true", help="run the synthetic worked examples")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        return 0

    units = demo_units()
    sced = clear_sced(units, 430.0)
    scuc = clear_scuc(units, (260.0, 600.0, 520.0, 300.0))

    if args.json:
        print(json.dumps({"sced": sced, "scuc": scuc}, indent=2, ensure_ascii=True))
        return 0

    print("SCED demo, demand = 430 MW")
    print(f"price = {_fmt(sced['price'])} CNY/MWh, marginal = {sced['marginal_unit']}")
    for unit in units:
        print(
            f"  {unit.name:<8} dispatch={_fmt(sced['dispatch'][unit.name]):>10} MW  "
            f"cost={_fmt(sced['cost_by_unit'][unit.name]):>12}  "
            f"uplift={_fmt(sced['uplift_by_unit'][unit.name]):>10}"
        )
    print(
        f"  total cost={_fmt(sced['total_cost'])}  revenue={_fmt(sced['total_revenue'])}  "
        f"uplift={_fmt(sced['total_uplift'])}"
    )

    print("\nSCUC demo, demand = 260 / 600 / 520 / 300 MW")
    for row in scuc["periods"]:
        on = ",".join(name for name, value in row["commitment"].items() if value)
        dispatch = ", ".join(f"{name}={_fmt(mw)}" for name, mw in row["dispatch"].items())
        print(
            f"  t={row['period']} demand={_fmt(row['demand_mw']):>7}  price={_fmt(row['price']):>8}  "
            f"on=[{on}]  {dispatch}"
        )
    summary = scuc["summary"]
    print(
        f"  total cost={_fmt(summary['total_cost'])}  energy={_fmt(summary['energy_cost'])}  "
        f"startup={_fmt(summary['startup_cost'])}  revenue={_fmt(summary['revenue'])}  "
        f"uplift={_fmt(summary['uplift'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())