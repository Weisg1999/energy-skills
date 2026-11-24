"""Exact price attribution and pre-market scenario sensitivity (standard library only).

The point is to separate *what changed the price* from *what merely happened at
the same time*. A single-node SCED stack is cleared under a baseline state and
under an actual state; each factor is then switched on in every possible order
and its average marginal price effect is reported as an exact Shapley value.

Assumptions and limits are deliberate:

* one node, energy-only. The network factor is a reduced-form price wedge, not
  a DC-OPF result; congestion and loss physics stay in ``network.py`` and the
  knowledge module;
* demand and renewable output enter as a net load. A separate demand factor and
  renewable factor therefore both move the same residual load; the attribution
  says how much each *stated* change contributed, not which one is causally
  "responsible";
* outage is a derate of the unit's most expensive incremental capacity, fuel is
  a multiplier on cost-based offers, behaviour is a markup on selected offers,
  and policy is the price floor/cap;
* Shapley values are additive by construction and remove order dependence, but
  they are not causal proof. Correlated factors, forecast error and model error
  remain outside the arithmetic;
* all example data are synthetic grade D. Nothing here is a market forecast,
  settlement instruction or trading recommendation.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass, replace
from typing import Mapping

from clearing import Unit, clear_sced, demo_units


EPS = 1e-9
FACTOR_KINDS = (
    "demand",
    "renewable",
    "derate",
    "fuel",
    "network",
    "markup",
    "policy",
)


def _pairs(value: Mapping[str, float] | tuple[tuple[str, float], ...]) -> tuple[tuple[str, float], ...]:
    items = dict(value)
    return tuple(sorted((str(k), float(v)) for k, v in items.items()))


@dataclass(frozen=True)
class Factor:
    name: str
    kind: str
    value: object
    label: str = ""
    note: str = ""

    @property
    def display(self) -> str:
        return self.label or self.name

    def validate(self) -> None:
        if self.kind not in FACTOR_KINDS:
            raise ValueError(f"{self.name}: unknown factor kind {self.kind!r}")
        if not self.name:
            raise ValueError("factor name must not be empty")


@dataclass(frozen=True)
class MarketState:
    units: tuple[Unit, ...]
    demand_mw: float
    renewable_mw: float = 0.0
    derates: tuple[tuple[str, float], ...] = ()
    fuel_multipliers: tuple[tuple[str, float], ...] = ()
    markups: tuple[tuple[str, float], ...] = ()
    network_wedge: float = 0.0
    floor: float = -100.0
    cap: float = 1500.0

    def apply_factor(self, factor: Factor) -> "MarketState":
        factor.validate()
        if factor.kind == "demand":
            return replace(self, demand_mw=float(factor.value))
        if factor.kind == "renewable":
            return replace(self, renewable_mw=float(factor.value))
        if factor.kind == "derate":
            return replace(self, derates=_pairs(factor.value))
        if factor.kind == "fuel":
            return replace(self, fuel_multipliers=_pairs(factor.value))
        if factor.kind == "markup":
            return replace(self, markups=_pairs(factor.value))
        if factor.kind == "network":
            return replace(self, network_wedge=float(factor.value))
        floor, cap = factor.value
        return replace(self, floor=float(floor), cap=float(cap))

    def clearing_units(self) -> tuple[Unit, ...]:
        derates = dict(self.derates)
        fuel = dict(self.fuel_multipliers)
        markup = dict(self.markups)
        known = {unit.name for unit in self.units}
        for key in set(derates) | set(fuel) | set(markup):
            if key not in known:
                raise ValueError(f"unknown unit in factor: {key}")
        units = []
        for unit in self.units:
            adjusted = unit
            if unit.name in derates:
                adjusted = _derate_unit(adjusted, derates[unit.name])
            scale = fuel.get(unit.name, 1.0) * (1.0 + markup.get(unit.name, 0.0))
            if scale <= 0.0:
                raise ValueError(f"{unit.name}: price multiplier must be positive")
            if abs(scale - 1.0) > EPS:
                adjusted = _scale_unit(adjusted, scale)
            units.append(adjusted)
        return tuple(units)

    def clear(self) -> dict:
        if self.demand_mw < 0.0 or self.renewable_mw < 0.0:
            raise ValueError("demand and renewable output must be non-negative")
        if self.floor > self.cap:
            raise ValueError("floor must not exceed cap")
        units = self.clearing_units()
        net_demand = max(0.0, self.demand_mw - self.renewable_mw)
        energy_floor = self.floor - self.network_wedge
        energy_cap = self.cap - self.network_wedge
        if energy_floor > energy_cap:
            raise ValueError("policy band is too narrow for the network wedge")
        result = clear_sced(list(units), net_demand, floor=energy_floor, cap=energy_cap)
        price = min(max(result["price"] + self.network_wedge, self.floor), self.cap)
        return {
            "price": price,
            "energy_price_before_wedge": result["price"],
            "price_before_policy": result["price"] + self.network_wedge,
            "net_demand_mw": net_demand,
            "dispatch": result["dispatch"],
            "total_cost": result["total_cost"],
            "total_revenue": result["total_revenue"],
            "total_uplift": result["total_uplift"],
            "overgeneration_mw": result["overgeneration_mw"],
            "unserved_mw": result["unserved_mw"],
            "marginal_unit": result["marginal_unit"],
            "units": {unit.name: unit for unit in units},
        }


@dataclass(frozen=True)
class AttributionCase:
    baseline: MarketState
    factors: tuple[Factor, ...]

    def __post_init__(self) -> None:
        names = [factor.name for factor in self.factors]
        if len(names) != len(set(names)):
            raise ValueError("factor names must be unique")
        if len(self.factors) > 10:
            raise ValueError("exact Shapley is limited to 10 factors")
        for factor in self.factors:
            factor.validate()

    @property
    def actual(self) -> MarketState:
        return self.state_for(frozenset(factor.name for factor in self.factors))

    def state_for(self, selected: frozenset[str]) -> MarketState:
        state = self.baseline
        for factor in self.factors:
            if factor.name in selected:
                state = state.apply_factor(factor)
        return state

    def value(self, selected: frozenset[str], metric: str = "price") -> float:
        return float(self.state_for(selected).clear()[metric])

    def shapley(self, metric: str = "price") -> dict:
        names = [factor.name for factor in self.factors]
        n = len(names)
        subset_values = {}
        for size in range(n + 1):
            for combo in itertools.combinations(self.factors, size):
                key = frozenset(factor.name for factor in combo)
                subset_values[key] = self.value(key, metric)
        contributions = {}
        factorial = math.factorial
        for factor in self.factors:
            total = 0.0
            others = [item for item in self.factors if item.name != factor.name]
            for size in range(n):
                weight = factorial(size) * factorial(n - size - 1) / factorial(n)
                for combo in itertools.combinations(others, size):
                    key = frozenset(item.name for item in combo)
                    total += weight * (
                        subset_values[key | {factor.name}] - subset_values[key]
                    )
            contributions[factor.name] = total
        baseline = subset_values[frozenset()]
        actual = subset_values[frozenset(names)]
        return {
            "metric": metric,
            "baseline": baseline,
            "actual": actual,
            "delta": actual - baseline,
            "contributions": contributions,
            "sum": sum(contributions.values()),
        }

    def standalone(self, metric: str = "price") -> dict:
        baseline = self.value(frozenset(), metric)
        return {
            factor.name: self.value(frozenset([factor.name]), metric) - baseline
            for factor in self.factors
        }

    def sequential(self, order: tuple[str, ...], metric: str = "price") -> dict:
        expected = {factor.name for factor in self.factors}
        if set(order) != expected or len(order) != len(expected):
            raise ValueError("order must contain every factor exactly once")
        by_name = {factor.name: factor for factor in self.factors}
        state = self.baseline
        previous = state.clear()[metric]
        contributions = {}
        for name in order:
            state = state.apply_factor(by_name[name])
            current = state.clear()[metric]
            contributions[name] = current - previous
            previous = current
        return {
            "metric": metric,
            "order": tuple(order),
            "baseline": self.baseline.clear()[metric],
            "actual": state.clear()[metric],
            "delta": state.clear()[metric] - self.baseline.clear()[metric],
            "contributions": contributions,
        }

    def report(self, metric: str = "price") -> dict:
        return {
            "metric": metric,
            "baseline": self.baseline.clear(),
            "actual": self.actual.clear(),
            "shapley": self.shapley(metric),
            "standalone": self.standalone(metric),
            "factors": [
                {
                    "name": factor.name,
                    "label": factor.display,
                    "kind": factor.kind,
                    "value": factor.value,
                    "note": factor.note,
                }
                for factor in self.factors
            ],
        }


def _derate_unit(unit: Unit, derate_mw: float) -> Unit:
    """Remove capacity from the top of the unit's incremental stack."""
    available = unit.pmax - unit.pmin
    if derate_mw < 0.0:
        raise ValueError(f"{unit.name}: derate must be non-negative")
    if derate_mw >= available - EPS:
        raise ValueError(
            f"{unit.name}: derate {derate_mw} must be below pmax - pmin = {available}"
        )
    if derate_mw <= EPS:
        return unit
    keep = available - derate_mw
    segments = []
    remaining = keep
    for price, mw in unit.segments:
        take = min(mw, remaining)
        if take > EPS:
            segments.append((price, take))
            remaining -= take
        if remaining <= EPS:
            break
    return replace(unit, pmax=unit.pmin + keep, segments=tuple(segments))


def _scale_unit(unit: Unit, scale: float) -> Unit:
    return replace(
        unit,
        pmin_price=unit.pmin_price * scale,
        segments=tuple((price * scale, mw) for price, mw in unit.segments),
    )


def demo_case() -> AttributionCase:
    """Seven-factor synthetic case used by the module and selftest."""
    baseline = MarketState(
        units=tuple(demo_units()),
        demand_mw=520.0,
        renewable_mw=60.0,
        floor=-100.0,
        cap=1500.0,
    )
    factors = (
        Factor("load", "demand", 620.0, "负荷 +100 MW", "实际负荷高于基线"),
        Factor("renewable", "renewable", 0.0, "新能源 -60 MW", "风光出力低于基线"),
        Factor("outage", "derate", {"coal-a": 50.0}, "检修 coal-a -50 MW", "削去部分最贵增量段"),
        Factor(
            "fuel",
            "fuel",
            {"coal-a": 1.10, "coal-b": 1.10},
            "燃料 +10% (coal)",
            "仅煤电成本上移",
        ),
        Factor("network", "network", 15.0, "阻塞/网损 +15 元/MWh", "外生价格楔子"),
        Factor("behavior", "markup", {"gas-c": 0.05}, "报价加价 +5% (gas-c)", "仅气电报价上移"),
        Factor("policy", "policy", (-100.0, 600.0), "价格帽 600 元/MWh", "政策叠加项"),
    )
    return AttributionCase(baseline=baseline, factors=factors)


def _print_state(name: str, state: dict) -> None:
    dispatch = " ".join(
        f"{unit}={mw:.0f}" for unit, mw in sorted(state["dispatch"].items()) if mw > EPS
    )
    print(
        f"{name:<10} price={state['price']:.1f}  net={state['net_demand_mw']:.0f} MW  "
        f"cost={state['total_cost']:.0f}  uplift={state['total_uplift']:.0f}  "
        f"marginal={state['marginal_unit']}  {dispatch}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Exact price attribution on a synthetic bid stack")
    parser.add_argument("--metric", choices=("price", "total_cost"), default="price")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    case = demo_case()
    report = case.report(args.metric)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    _print_state("baseline", report["baseline"])
    _print_state("actual", report["actual"])
    print()

    shapley = report["shapley"]
    standalone = report["standalone"]
    print(f"Shapley attribution of {args.metric}: delta={shapley['delta']:+.2f}")
    for factor in case.factors:
        print(
            f"  {factor.display:<24} shapley={shapley['contributions'][factor.name]:+8.2f}  "
            f"standalone={standalone[factor.name]:+8.2f}"
        )
    print(
        f"  {'sum':<24} shapley={shapley['sum']:+8.2f}  "
        f"residual={shapley['sum'] - shapley['delta']:+.2e}"
    )

    order = tuple(factor.name for factor in case.factors)
    sequential = case.sequential(order)
    print()
    print("Sequential attribution in the order above (order-dependent, for comparison):")
    for factor in case.factors:
        print(f"  {factor.display:<24} {sequential['contributions'][factor.name]:+8.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())