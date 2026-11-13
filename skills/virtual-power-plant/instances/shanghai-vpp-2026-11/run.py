#!/usr/bin/env python3
"""Run the Shanghai user-side VPP instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the 1+5 rule context, resource portfolio, policy
  profile, contracts and data contract.
* ``data/history_demo.csv`` is the baseline sample (6 days x 96 points).
* ``data/event_demo.csv`` is the invitation (3 scenarios).
* ``data/t1_loads_demo.csv`` and ``data/t1_event_demo.csv`` are the T+1
  metered loads and the actual clearing outcome.

The baseline and capability kernels come from ``virtual-power-plant/tools``
(``cbl``, ``aggregation``). This runner adds the Shanghai resource portfolio,
event settlement, response validation and the T+1 bridge.

All bundled numbers are synthetic grade D. They are not a market forecast, a
live bidding signal or investment advice.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parents[1]
sys.path.insert(0, str(SKILL_DIR / "tools"))

import aggregation  # noqa: E402
import cbl  # noqa: E402

POINTS = 96
DT_H = 0.25
TRUE_TEXT = {"1", "true", "yes", "y", "是"}


class ConfigError(ValueError):
    """Raised when the instance or an input file fails validation."""


def _need(mapping, key, path):
    if not isinstance(mapping, dict) or key not in mapping:
        raise ConfigError(f"{path}.{key} is required")
    return mapping[key]


def _number(value, path, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{path} must be a number")
    if not math.isfinite(number):
        raise ConfigError(f"{path} must be finite")
    if minimum is not None and number < minimum - 1e-12:
        raise ConfigError(f"{path} must be >= {minimum}")
    if maximum is not None and number > maximum + 1e-12:
        raise ConfigError(f"{path} must be <= {maximum}")
    return number


def _text(mapping, key, path):
    value = _need(mapping, key, path)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _grade(mapping, path):
    value = _text(mapping, "grade", path)
    parts = [part.strip() for part in value.replace("，", "/").split("/") if part.strip()]
    if not parts or any(part not in {"A", "B", "C", "D"} for part in parts):
        raise ConfigError(f"{path}.grade must combine A/B/C/D, got {value!r}")
    return value


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report["provenance"].append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block


def _parse_hhmm(value, path):
    text = _text({"value": value}, "value", path)
    try:
        hour, minute = text.split(":")
        hour, minute = int(hour), int(minute)
    except (ValueError, AttributeError):
        raise ConfigError(f"{path} must be HH:MM")
    if not (0 <= hour <= 23 and 0 <= minute < 60):
        raise ConfigError(f"{path} must be a valid time")
    return hour * 60 + minute


def _slot_label(slot):
    minutes = slot * 15
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _round_mw(value):
    return math.floor(value * 10 + 1e-9) / 10.0


def validate_instance(config):
    """Validate the six blocks and return a provenance and check report."""
    report = {"ok": True, "provenance": [], "checks": [], "warnings": []}
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    resources = _need(config, "resources", "instance")
    policy = _need(config, "policy", "instance")
    contracts = _need(config, "contracts", "instance")
    data_contract = _need(config, "data_contract", "instance")

    plan = _rule_block(rules, "vpp_plan", report)
    baseline = _rule_block(rules, "baseline", report)
    event = _rule_block(rules, "event", report)
    settlement = _rule_block(rules, "settlement", report)

    targets = _need(plan, "targets_10k_kw", "rules.vpp_plan")
    for year, expected in (("2025", 110.0), ("2026", 160.0), ("2027", 220.0)):
        value = _number(_need(targets, year, "rules.vpp_plan.targets_10k_kw"), f"targets.{year}", 1.0)
        if abs(value - expected) > 1e-9:
            raise ConfigError(f"407号 target for {year} must be {expected:g} 万kW")
    call = _number(
        _need(plan, "call_2025_08_10k_kw", "rules.vpp_plan"), "rules.vpp_plan.call_2025_08_10k_kw", 0.0
    )
    if abs(call - 116.27) > 1e-9:
        raise ConfigError("407号/公开口径: 2025-08 call must be 116.27 万kW")
    if plan.get("aggregation_threshold") is not None:
        raise ConfigError("407号 sets no unified MW aggregation threshold; keep the field null")
    resource_targets = _need(plan, "resource_targets_2027_10k_kw", "rules.vpp_plan")
    adjustable_sum = 0.0
    access_sum = 0.0
    for category in resource_targets:
        block = _need(resource_targets, category, "rules.vpp_plan.resource_targets_2027_10k_kw")
        access_sum += _number(_need(block, "access", f"targets.{category}"), f"targets.{category}.access", 0.0)
        adjustable_sum += _number(
            _need(block, "adjustable", f"targets.{category}"), f"targets.{category}.adjustable", 0.0
        )
    if abs(access_sum - 840.0) > 1e-6 or abs(adjustable_sum - 220.0) > 1e-6:
        raise ConfigError("2027 resource targets must sum to 840 access / 220 adjustable 万kW")

    items = _need(resources, "items", "resources")
    if not isinstance(items, list) or len(items) != 5:
        raise ConfigError("resources.items must contain the five 1+5 resource categories")
    ids = set()
    load_fields = {}
    for index, item in enumerate(items):
        path = f"resources.items[{index}]"
        resource_id = _text(item, "id", path)
        if resource_id in ids:
            raise ConfigError(f"duplicate resource id: {resource_id}")
        ids.add(resource_id)
        if resource_id not in resource_targets:
            raise ConfigError(f"{path}.id {resource_id!r} is not in the 1+5 target table")
        _text(item, "name", path)
        _text(item, "category", path)
        _number(_need(item, "max_mw", path), f"{path}.max_mw", 1e-9)
        _number(_need(item, "adjustable_ratio", path), f"{path}.adjustable_ratio", 0.0, 1.0)
        _number(_need(item, "availability", path), f"{path}.availability", 0.0, 1.0)
        _number(_need(item, "usable_ratio", path), f"{path}.usable_ratio", 0.0, 1.0)
        _number(_need(item, "customer_share", path), f"{path}.customer_share", 0.0, 1.0)
        _grade(item, path)
        _text(item, "source", path)
        field = _text(item, "load_field", path)
        load_fields[resource_id] = field
    if ids != set(resource_targets):
        raise ConfigError("resources.items must cover exactly the 1+5 categories")
    if len(set(load_fields.values())) != len(load_fields):
        raise ConfigError("load_field values must be unique")

    _text(baseline, "method", "rules.baseline")
    count = int(_number(_need(baseline, "count", "rules.baseline"), "rules.baseline.count", 1))
    deviation = _number(_need(baseline, "deviation", "rules.baseline"), "rules.baseline.deviation", 0.0, 1.0)
    adjustment = _number(_need(baseline, "adjustment", "rules.baseline"), "rules.baseline.adjustment", 0.0)
    if count != 5 or abs(deviation - 0.25) > 1e-9:
        raise ConfigError("the bundled D-level baseline is 5 days with a +/-25% screen")

    duration = _number(_need(event, "duration_h", "rules.event"), "rules.event.duration_h", 1e-9)
    start = _parse_hhmm(_need(event, "window", "rules.event").split("-")[0], "rules.event.window.start")
    end = _parse_hhmm(_need(event, "window", "rules.event").split("-")[-1], "rules.event.window.end")
    if end <= start:
        raise ConfigError("rules.event.window end must be after start")
    if abs((end - start) / 60.0 - duration) > 1e-9:
        raise ConfigError("rules.event.duration_h must equal the window length")
    min_rate = _number(_need(event, "min_response_rate", "rules.event"), "rules.event.min_response_rate", 0.0, 1.0)
    cap_ratio = _number(
        _need(event, "overshoot_cap_ratio", "rules.event"), "rules.event.overshoot_cap_ratio", 1.0
    )

    bid_price = _number(
        _need(settlement, "assumed_bid_price_cny_per_kwh", "rules.settlement"),
        "rules.settlement.assumed_bid_price_cny_per_kwh",
        1e-9,
    )
    scenario_prices = _need(settlement, "price_scenarios_cny_per_kwh", "rules.settlement")
    if not isinstance(scenario_prices, list) or len(scenario_prices) != 3:
        raise ConfigError("rules.settlement.price_scenarios_cny_per_kwh must hold three prices")
    prices = [
        _number(value, "rules.settlement.price_scenarios", 1e-9) for value in scenario_prices
    ]
    if sorted(prices) != [3.6, 4.2, 5.0] or abs(bid_price - 4.2) > 1e-9:
        raise ConfigError("the bundled D-level price set is 3.6 / 4.2 / 5.0 with a 4.2 bid")

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    bid_ratio = _number(_need(policy, "bid_ratio", "policy"), "policy.bid_ratio", 0.0, 1.0)
    policy_price = _number(
        _need(policy, "bid_price_cny_per_kwh", "policy"), "policy.bid_price_cny_per_kwh", 1e-9
    )
    if abs(policy_price - bid_price) > 1e-9:
        raise ConfigError("policy.bid_price_cny_per_kwh must equal rules.settlement.assumed_bid_price")
    delivery = _number(
        _need(policy, "planned_delivery_ratio", "policy"), "policy.planned_delivery_ratio", 0.0, 1.0
    )
    coincidence = _number(_need(policy, "coincidence", "policy"), "policy.coincidence", 0.0, 1.0)
    confidence = _number(
        _need(policy, "scenario_cvar_confidence", "policy"), "policy.scenario_cvar_confidence", 0.0, 1.0
    )
    if not 0 < confidence < 1:
        raise ConfigError("policy.scenario_cvar_confidence must be in (0, 1)")

    shortfall = _need(contracts, "shortfall", "contracts")
    _number(_need(shortfall, "delivery_threshold", "contracts.shortfall"), "contracts.shortfall.delivery_threshold", 0.0, 1.0)
    _number(_need(shortfall, "extra_customer_share", "contracts.shortfall"), "contracts.shortfall.extra_customer_share", 0.0, 1.0)
    opex = _need(contracts, "opex", "contracts")
    _number(_need(opex, "variable_cny_per_mwh", "contracts.opex"), "contracts.opex.variable_cny_per_mwh", 0.0)
    _number(_need(opex, "fixed_cny_per_event", "contracts.opex"), "contracts.opex.fixed_cny_per_event", 0.0)

    for key, name in (("history", "history"), ("event", "event"), ("t1_loads", "t1_loads"), ("t1_event", "t1_event")):
        block = _need(data_contract, key, "data_contract")
        _text(block, "file", f"data_contract.{key}")
    weights = _need(data_contract["event"], "scenario_weights", "data_contract.event")
    if not isinstance(weights, list) or len(weights) != 3:
        raise ConfigError("data_contract.event.scenario_weights must hold three weights")
    if abs(sum(_number(value, "scenario_weights", 0.0) for value in weights) - 1.0) > 1e-6:
        raise ConfigError("scenario weights must sum to 1")

    report["checks"].append(
        {
            "targets_10k_kw": targets,
            "call_2025_08_10k_kw": call,
            "baseline_days": count,
            "baseline_deviation": deviation,
            "baseline_adjustment": adjustment,
            "event_duration_h": duration,
            "event_window": f"{_slot_label(start // 15)}-{_slot_label(end // 15)}",
            "min_response_rate": min_rate,
            "overshoot_cap_ratio": cap_ratio,
            "bid_ratio": bid_ratio,
            "bid_price_cny_per_kwh": bid_price,
            "planned_delivery_ratio": delivery,
            "coincidence": coincidence,
            "cvar_confidence": confidence,
            "resources": len(items),
        }
    )
    report["warnings"].append("基线算法为 D 级建模假设，上海 VPP 基线口径待省级细则")
    report["warnings"].append("响应有效性门槛与超额封顶为 D 级假设，不得用于结算")
    report["warnings"].append("响应激励 4.2 元/kWh 为 D 级演示价，上海补偿标准待核实")
    report["predicates"] = {
        "start_slot": start // 15,
        "end_slot": end // 15,
        "min_response_rate": min_rate,
        "cap_ratio": cap_ratio,
        "delivery_threshold": _number(shortfall["delivery_threshold"], "contracts.shortfall.delivery_threshold"),
        "extra_customer_share": _number(shortfall["extra_customer_share"], "contracts.shortfall.extra_customer_share"),
        "variable_opex": _number(opex["variable_cny_per_mwh"], "contracts.opex.variable_cny_per_mwh"),
        "fixed_opex": _number(opex["fixed_cny_per_event"], "contracts.opex.fixed_cny_per_event"),
        "scenario_weights": [float(value) for value in weights],
    }
    return report


def _read_rows(path):
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}")


def _float_cell(row, field, path, line_no):
    if field not in row:
        raise ConfigError(f"{path} line {line_no} is missing {field}")
    return _number(row[field], f"{path}:{line_no}.{field}")


def load_history(path, config, report):
    contract = config["data_contract"]["history"]
    rows = _read_rows(path)
    if not rows:
        raise ConfigError("history is empty")
    fields = contract["load_fields"]
    by_day = {}
    for line_no, row in enumerate(rows, start=2):
        day = (row.get(contract["date_field"]) or "").strip()
        if not day:
            raise ConfigError(f"history line {line_no} has an empty date")
        slot = int(_float_cell(row, contract["slot_field"], "history", line_no))
        if not 0 <= slot < POINTS:
            raise ConfigError(f"history line {line_no} slot out of range")
        day_data = by_day.setdefault(day, {resource: [None] * POINTS for resource in fields})
        for resource in fields:
            day_data[resource][slot] = _float_cell(row, fields[resource], "history", line_no)
    for day, values in by_day.items():
        for resource, curve in values.items():
            if any(value is None for value in curve):
                raise ConfigError(f"history {day} / {resource} has missing points")
    if len(by_day) < config["rules"]["baseline"]["count"]:
        raise ConfigError("history must cover at least the baseline sample days")
    report["history_days"] = sorted(by_day)
    return by_day


def load_event(path, config):
    contract = config["data_contract"]["event"]
    rows = _read_rows(path)
    if len(rows) != len(contract["scenario_weights"]):
        raise ConfigError("event scenario count does not match scenario_weights")
    scenarios = []
    for line_no, row in enumerate(rows, start=2):
        name = (row.get(contract["scenario_field"]) or "").strip()
        if not name:
            raise ConfigError(f"event line {line_no} has an empty scenario")
        scenarios.append(
            {
                "scenario": name,
                "event_date": (row.get(contract["event_date_field"]) or "").strip(),
                "start": (row.get(contract["start_field"]) or "").strip(),
                "end": (row.get(contract["end_field"]) or "").strip(),
                "required_mw": _float_cell(row, contract["required_mw_field"], "event", line_no),
                "incentive_price": _float_cell(
                    row, contract["incentive_price_field"], "event", line_no
                ),
            }
        )
    dates = {item["event_date"] for item in scenarios}
    windows = {(item["start"], item["end"]) for item in scenarios}
    if len(dates) != 1 or len(windows) != 1:
        raise ConfigError("all event scenarios must share one date and window")
    return scenarios


def load_t1_loads(path, config):
    contract = config["data_contract"]["t1_loads"]
    rows = _read_rows(path)
    fields = contract["load_fields"]
    days = {}
    for line_no, row in enumerate(rows, start=2):
        day = (row.get(contract["date_field"]) or "").strip()
        slot = int(_float_cell(row, contract["slot_field"], "t1_loads", line_no))
        if not 0 <= slot < POINTS:
            raise ConfigError(f"t1_loads line {line_no} slot out of range")
        day_data = days.setdefault(day, {resource: [None] * POINTS for resource in fields})
        for resource in fields:
            day_data[resource][slot] = _float_cell(row, fields[resource], "t1_loads", line_no)
    if len(days) != 1:
        raise ConfigError("t1_loads must contain exactly one event day")
    day, values = next(iter(days.items()))
    for resource, curve in values.items():
        if any(value is None for value in curve):
            raise ConfigError(f"t1_loads {day} / {resource} has missing points")
    return day, values


def load_t1_event(path, config):
    contract = config["data_contract"]["t1_event"]
    rows = _read_rows(path)
    if len(rows) != 1:
        raise ConfigError("t1_event must contain exactly one row")
    row = rows[0]
    return {
        "cleared_price": _float_cell(row, contract["cleared_price_field"], "t1_event", 2),
        "cleared_mw": _float_cell(row, contract["cleared_mw_field"], "t1_event", 2),
    }


def compute_baselines(config, history, event_date, report):
    baseline_rules = config["rules"]["baseline"]
    count = int(baseline_rules["count"])
    days = sorted((day for day in history if day < event_date), reverse=True)[:count]
    if len(days) < count:
        raise ConfigError("not enough history days before the event date")
    fields = config["data_contract"]["history"]["load_fields"]
    baselines = {}
    diagnostics = {}
    for resource, field in fields.items():
        samples = []
        for day in days:
            curve = history[day][resource]
            samples.append({"energy_mwh": sum(curve) * DT_H, "curve_mw": list(curve)})
        result = cbl.customer_baseline(
            samples,
            count=count,
            deviation=baseline_rules["deviation"],
            adjustment=baseline_rules["adjustment"],
        )
        baselines[resource] = result["baseline_mw"]
        diagnostics[resource] = {
            "candidates": result["candidates"],
            "kept": result["kept"],
            "dropped": result["dropped"],
            "mean_energy_mwh": result["mean_energy_mwh"],
        }
    total = [sum(baselines[resource][slot] for resource in fields) for slot in range(POINTS)]
    report["baseline_days_used"] = days
    report["baseline_diagnostics"] = diagnostics
    return baselines, total


def build_bid(config, report):
    items = config["resources"]["items"]
    policy = config["policy"]
    duration = config["rules"]["event"]["duration_h"]
    portfolio = []
    total_available = 0.0
    total_theoretical = 0.0
    weighted_share = 0.0
    for item in items:
        capability = aggregation.resource_capability(
            item["max_mw"],
            item["adjustable_ratio"],
            duration,
            item["usable_ratio"],
        )
        available = capability["power_mw"] * item["availability"]
        total_theoretical += capability["power_mw"]
        total_available += available
        weighted_share += available * item["customer_share"]
        portfolio.append(
            {
                "resource": item["id"],
                "name": item["name"],
                "category": item["category"],
                "max_mw": item["max_mw"],
                "adjustable_ratio": item["adjustable_ratio"],
                "availability": item["availability"],
                "available_mw": available,
                "customer_share": item["customer_share"],
            }
        )
    coincidence = policy["coincidence"]
    declared = total_available * coincidence
    bid_mw = _round_mw(declared * policy["bid_ratio"])
    for row in portfolio:
        row["bid_mw"] = bid_mw * row["available_mw"] / total_available
        row["share_of_bid"] = row["available_mw"] / total_available
    avg_share = weighted_share / total_available
    eligible_mw = aggregation.aggregate(
        [(row["resource"], {"power_mw": row["available_mw"], "energy_mwh": 0.0}) for row in portfolio],
        coincidence=1.0,
        availability=1.0,
    )
    return {
        "theoretical_power_mw": total_theoretical,
        "available_power_mw": total_available,
        "declared_power_mw": declared,
        "bid_mw": bid_mw,
        "coincidence": coincidence,
        "bid_ratio": policy["bid_ratio"],
        "avg_customer_share": avg_share,
        "resources": portfolio,
        "eligible_check_mw": eligible_mw["theoretical_power_mw"],
        "target_2027_10k_kw": config["rules"]["vpp_plan"]["targets_10k_kw"]["2027"],
    }


def _weighted_cvar(pairs, confidence):
    tail = 1.0 - confidence
    remaining = tail
    accumulated = 0.0
    for weight, value in sorted(pairs, key=lambda pair: pair[1]):
        take = min(weight, remaining)
        accumulated += take * value
        remaining -= take
        if remaining <= 1e-12:
            break
    used = tail - remaining
    if used <= 1e-12:
        return None
    return accumulated / used


def assess_scenarios(config, event, bid, report):
    weights = config["data_contract"]["event"]["scenario_weights"]
    duration = config["rules"]["event"]["duration_h"]
    delivery = config["policy"]["planned_delivery_ratio"]
    bid_price = config["policy"]["bid_price_cny_per_kwh"]
    predicate = report["predicates"]
    share = bid["avg_customer_share"]
    rows = []
    for item, weight in zip(event, weights):
        cleared = min(bid["bid_mw"], item["required_mw"]) if bid_price <= item["incentive_price"] + 1e-9 else 0.0
        delivered = cleared * duration * delivery
        revenue = delivered * 1000.0 * item["incentive_price"]
        customer = revenue * share
        opex = predicate["variable_opex"] * delivered + (predicate["fixed_opex"] if cleared > 0 else 0.0)
        margin = revenue - customer - opex
        rows.append(
            {
                "scenario": item["scenario"],
                "weight": float(weight),
                "required_mw": item["required_mw"],
                "incentive_price": item["incentive_price"],
                "cleared_mw": cleared,
                "delivered_mwh": delivered,
                "revenue_cny": revenue,
                "customer_share_cny": customer,
                "opex_cny": opex,
                "margin_cny": margin,
            }
        )
    expected = sum(row["weight"] * row["margin_cny"] for row in rows)
    cvar = _weighted_cvar([(row["weight"], row["margin_cny"]) for row in rows], config["policy"]["scenario_cvar_confidence"])
    reference = next((row for row in rows if abs(row["incentive_price"] - bid_price) < 1e-9), rows[len(rows) // 2])
    return {"rows": rows, "expected_margin_cny": expected, "cvar_cny": cvar, "reference": reference}


def assess_actual(config, event, bid, baselines, t1_day, t1_loads, t1_event, report):
    predicate = report["predicates"]
    start = predicate["start_slot"]
    end = predicate["end_slot"]
    duration = config["rules"]["event"]["duration_h"]
    fields = config["data_contract"]["t1_loads"]["load_fields"]
    per_resource = []
    total_mwh = 0.0
    for resource in fields:
        response_mwh = 0.0
        for slot in range(start, end):
            response_mwh += max(0.0, baselines[resource][slot] - t1_loads[resource][slot]) * DT_H
        total_mwh += response_mwh
        per_resource.append(
            {
                "resource": resource,
                "response_mwh": response_mwh,
                "baseline_avg_mw": sum(baselines[resource][start:end]) / (end - start),
                "actual_avg_mw": sum(t1_loads[resource][start:end]) / (end - start),
            }
        )
    cleared_mwh = t1_event["cleared_mw"] * duration
    plan_mwh = cleared_mwh * config["policy"]["planned_delivery_ratio"]
    rate = total_mwh / plan_mwh if plan_mwh > 0 else 0.0
    valid = rate >= predicate["min_response_rate"]
    cap_mwh = cleared_mwh * predicate["cap_ratio"]
    paid_mwh = min(total_mwh, cap_mwh) if valid else 0.0
    price = t1_event["cleared_price"]
    revenue = paid_mwh * 1000.0 * price
    share = bid["avg_customer_share"]
    shortfall = rate < predicate["delivery_threshold"]
    share_actual = min(share + predicate["extra_customer_share"], 0.95) if shortfall else share
    customer = revenue * share_actual
    opex = predicate["variable_opex"] * total_mwh + predicate["fixed_opex"]
    margin = revenue - customer - opex
    return {
        "event_day": t1_day,
        "window": f"{_slot_label(start)}-{_slot_label(end)}",
        "per_resource": per_resource,
        "actual_mwh": total_mwh,
        "plan_mwh": plan_mwh,
        "cleared_mwh": cleared_mwh,
        "cap_mwh": cap_mwh,
        "response_rate": rate,
        "valid": valid,
        "shortfall": shortfall,
        "paid_mwh": paid_mwh,
        "price_cny_per_kwh": price,
        "revenue_cny": revenue,
        "customer_share": share_actual,
        "customer_share_cny": customer,
        "opex_cny": opex,
        "margin_cny": margin,
    }


def _bridge_items(config, actual):
    base_share = actual["base_share"]
    price = actual["price_cny_per_kwh"]
    plan_mwh = actual["plan_mwh"]
    actual_mwh = actual["actual_mwh"]
    cap_mwh = actual["cap_mwh"]
    paid = actual["paid_mwh"]
    predicate = actual["predicate"]

    revenue_plan = plan_mwh * 1000.0 * price
    opex_plan = predicate["variable_opex"] * plan_mwh + predicate["fixed_opex"]
    margin_plan = revenue_plan * (1 - base_share) - opex_plan
    margin_actual = actual["margin_cny"]

    items = [
        {
            "item": "响应量偏差",
            "amount_cny": (actual_mwh - plan_mwh) * 1000.0 * price * (1 - base_share),
            "note": "(实际响应 − 计划响应) × 价格 × (1 − 客户分成)",
        },
        {
            "item": "超额封顶",
            "amount_cny": -max(0.0, actual_mwh - cap_mwh) * 1000.0 * price * (1 - base_share),
            "note": "实际响应超过 1.2 倍中标量的部分不计费",
        },
        {
            "item": "有效性扣减",
            "amount_cny": 0.0 if actual["valid"] else -min(actual_mwh, cap_mwh) * 1000.0 * price * (1 - base_share),
            "note": "响应率低于门槛时整场不计费（D 级假设）",
        },
        {
            "item": "客户分成变化",
            "amount_cny": -paid * 1000.0 * price * (actual["customer_share"] - base_share),
            "note": "未达 95% 执行率时额外让利 5 个百分点",
        },
        {
            "item": "运营成本偏差",
            "amount_cny": -(
                predicate["variable_opex"] * (actual_mwh - plan_mwh)
            ),
            "note": "变动运营成本随实际响应量变化；固定成本不变",
        },
    ]
    total = margin_actual - margin_plan
    residual = total - sum(item["amount_cny"] for item in items)
    return {
        "plan_margin_cny": margin_plan,
        "actual_margin_cny": margin_actual,
        "delta_cny": total,
        "items": items,
        "residual_cny": residual,
    }


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(field, row.get(field)) for field in fields})


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if field in ("response_rate", "customer_share", "share_of_bid", "utilization"):
            return f"{value:.4f}"
        return f"{value:.2f}"
    return value


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _wan(value):
    return "—" if value is None else f"{value / 10000.0:,.1f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def write_review(path, config, report, bid, scenarios, actual, bridge, fingerprint):
    plan = config["rules"]["vpp_plan"]
    lines = [
        "# 上海用户侧虚拟电厂实例 · 复核单",
        "",
        f"- 实例：`{config['meta']['instance_id']}`",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格指纹：`{fingerprint}`",
        "- 全部数据为 D 级合成，不对应任何真实聚合商、用户或结算单。",
        "",
        "## 1. 结论摘要",
        "",
        f"- 组合理论可调 {bid['theoretical_power_mw']:.1f} MW，计入可用率 {bid['available_power_mw']:.1f} MW，"
        f"同时率 {_pct(bid['coincidence'])} 后申报能力 {bid['declared_power_mw']:.1f} MW，"
        f"按 {_pct(bid['bid_ratio'])} 申报 {bid['bid_mw']:.1f} MW。",
        f"- 占 407 号 2027 年全市可调目标 {plan['targets_10k_kw']['2027']:g} 万 kW 的 "
        f"{_pct(bid['bid_mw'] / (plan['targets_10k_kw']['2027'] * 10.0))}。",
        f"- 参考情景（{scenarios['reference']['incentive_price']:.1f} 元/kWh）中标 "
        f"{scenarios['reference']['cleared_mw']:.1f} MW，计划响应 "
        f"{scenarios['reference']['delivered_mwh']:.1f} MWh，聚合商边际 {_wan(scenarios['reference']['margin_cny'])} 万元。",
        f"- 情景期望边际 {_wan(scenarios['expected_margin_cny'])} 万元；CVaR（置信 "
        f"{_pct(config['policy']['scenario_cvar_confidence'])}，最差 "
        f"{_pct(1 - config['policy']['scenario_cvar_confidence'])} 概率质量均值）{_wan(scenarios['cvar_cny'])} 万元。",
        "- CVaR 为 0 表示最差概率质量落在未中标情景（本演示把未中标记为边际 0），不是「没有风险」；"
        "尾部风险体现为丢掉高价情景的收入，而不是现金亏损。",
        f"- T+1：实际响应 {actual['actual_mwh']:.1f} MWh / 计划 {actual['plan_mwh']:.1f} MWh，"
        f"响应率 {_pct(actual['response_rate'])}，{'认定有效' if actual['valid'] else '认定无效'}；"
        f"结算电量 {actual['paid_mwh']:.1f} MWh。",
        f"- T+1 差异桥：计划边际 {_wan(bridge['plan_margin_cny'])} 万元 → 实际 "
        f"{_wan(bridge['actual_margin_cny'])} 万元，差异 {_wan(bridge['delta_cny'])} 万元，"
        f"残差 {bridge['residual_cny']:.6f} 元。",
        "",
        "## 2. 组合与能力（1+5）",
        "",
        "| 资源 | 类别 | 额定 MW | 可调比例 | 可用率 | 可用 MW | 申报 MW | 客户分成 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in bid["resources"]:
        lines.append(
            f"| {row['name']} | {row['category']} | {row['max_mw']:.1f} | {_pct(row['adjustable_ratio'])} | "
            f"{_pct(row['availability'])} | {row['available_mw']:.2f} | {row['bid_mw']:.2f} | "
            f"{_pct(row['customer_share'])} |"
        )
    category_by_id = {item["id"]: item["category"] for item in config["resources"]["items"]}
    lines += [
        "",
        f"407 号 2027 年五类资源目标（接入 / 可调，万 kW）："
        + "；".join(
            f"{category_by_id.get(category, category)} {value['access']:g}/{value['adjustable']:g}"
            for category, value in plan["resource_targets_2027_10k_kw"].items()
        )
        + "。本组合是合成样板，不对应任何真实运营商的目标分解。",
        "",
        "## 3. 基线",
        "",
        f"- 方法：{config['rules']['baseline']['method']}；候选 {config['rules']['baseline']['count']} 日，"
        f"剔除日电量偏离 ±{_pct(config['rules']['baseline']['deviation'])} 的异常日。",
        "- 该方法是 D 级建模假设；上海 VPP 基线算法未在本库核到，不能当作正式结算口径。",
        "",
        "## 4. 情景申报与结算",
        "",
        "| 情景 | 权重 | 邀约需求 MW | 激励价 元/kWh | 中标 MW | 计划响应 MWh | 收入（万元） | 聚合商边际（万元） |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in scenarios["rows"]:
        lines.append(
            f"| {row['scenario']} | {row['weight']:.2f} | {row['required_mw']:.1f} | {row['incentive_price']:.1f} | "
            f"{row['cleared_mw']:.1f} | {row['delivered_mwh']:.1f} | {_wan(row['revenue_cny'])} | "
            f"{_wan(row['margin_cny'])} |"
        )
    lines += [
        "",
        f"报价 {config['policy']['bid_price_cny_per_kwh']:.1f} 元/kWh，高于报价的情景不中标；"
        "中标量 = min(申报能力, 邀约需求)；计划响应已乘计划执行率 "
        f"{_pct(config['policy']['planned_delivery_ratio'])}。",
        "",
        "## 5. T+1 响应认定",
        "",
        "| 资源 | 基线均值 MW | 实际均值 MW | 响应电量 MWh |",
        "| --- | --- | --- | --- |",
    ]
    for row in actual["per_resource"]:
        lines.append(
            f"| {row['resource']} | {row['baseline_avg_mw']:.2f} | {row['actual_avg_mw']:.2f} | "
            f"{row['response_mwh']:.2f} |"
        )
    lines += [
        "",
        f"- 响应率 {_pct(actual['response_rate'])}，门槛 {_pct(config['rules']['event']['min_response_rate'])}"
        f"（D 级假设），{'有效' if actual['valid'] else '无效'}。",
        f"- 超额封顶 {_pct(config['rules']['event']['overshoot_cap_ratio'])}：结算电量 "
        f"{actual['paid_mwh']:.1f} MWh；未达 95% 执行率时客户分成由 "
        f"{_pct(actual['base_share'])} 提高到 {_pct(actual['customer_share'])}。",
        "",
        "## 6. T+1 差异桥",
        "",
        "| 科目 | 金额（万元） | 口径 |",
        "| --- | --- | --- |",
    ]
    for item in bridge["items"]:
        lines.append(f"| {item['item']} | {_wan(item['amount_cny'])} | {item['note']} |")
    lines += [
        f"| **合计** | **{_wan(bridge['delta_cny'])}** | 计划边际 → 实际边际 |",
        "",
        f"残差 {bridge['residual_cny']:.6f} 元；不为零说明科目拆分有误。",
        "",
        "## 7. 口径提醒",
        "",
        f"- 407 号是 VPP **建设方案**，不是现货文件；上海现货自 2025-10-29 起连续结算试运行，转正待核。",
        f"- 110/160/220 万 kW 是可调能力**目标**；2025-08 的 116.27 万 kW 是**实测调用事件**，两者不能互换。",
        f"- 2026-07 的 164.77 万 kW 与 49 家运营商、203.24 万 kW 申报可调均为 C 级行业口径，待省级原文。",
        "- 407 号未设统一 MW 聚合门槛；本包不套用外省 5 MW / 1 MW 门槛。",
        "",
        "## 8. 使用与边界",
        "",
        "```bash",
        "python make_demo.py",
        "python run.py --demo",
        "python run.py --check-config",
        "python run.py --history 我的历史.csv --event 我的邀约.csv --t1-loads 我的T1.csv --t1-event 我的出清.csv --out out/my-case",
        "```",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        "- v1 不含中长期、现货、辅助服务、容量补偿与绿证；响应补偿标准与结算细则待上海原文。",
        "- 本复核单是 D 级合成样板，不构成报价、签约或投资建议。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, history_path, event_path, t1_loads_path, t1_event_path, out_dir):
    config = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    report = validate_instance(config)
    history = load_history(history_path, config, report)
    event = load_event(event_path, config)
    t1_day, t1_loads = load_t1_loads(t1_loads_path, config)
    t1_event = load_t1_event(t1_event_path, config)

    event_date = event[0]["event_date"]
    if t1_day != event_date:
        raise ConfigError(f"T+1 day {t1_day} does not match event date {event_date}")
    expected_start = report["checks"][0]["event_window"]
    if (event[0]["start"], event[0]["end"]) != tuple(expected_start.split("-")):
        raise ConfigError("event file window does not match rules.event.window")

    baselines, total_baseline = compute_baselines(config, history, event_date, report)
    bid = build_bid(config, report)
    scenarios = assess_scenarios(config, event, bid, report)
    actual = assess_actual(config, event, bid, baselines, t1_day, t1_loads, t1_event, report)
    actual["predicate"] = report["predicates"]
    actual["base_share"] = bid["avg_customer_share"]
    bridge = _bridge_items(config, actual)
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]

    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_rows = []
    for slot in range(POINTS):
        row = {
            "slot": slot,
            "time": _slot_label(slot),
            "total_baseline_mw": total_baseline[slot],
        }
        for resource, curve in baselines.items():
            row[f"{resource}_baseline_mw"] = curve[slot]
        baseline_rows.append(row)
    _write_csv(
        out_dir / "baseline.csv",
        baseline_rows,
        ["slot", "time", "total_baseline_mw"] + [f"{resource}_baseline_mw" for resource in baselines],
    )
    _write_csv(
        out_dir / "bid.csv",
        bid["resources"],
        ["resource", "name", "category", "max_mw", "adjustable_ratio", "availability", "available_mw", "bid_mw", "share_of_bid", "customer_share"],
    )
    _write_csv(
        out_dir / "scenarios.csv",
        scenarios["rows"],
        ["scenario", "weight", "required_mw", "incentive_price", "cleared_mw", "delivered_mwh", "revenue_cny", "customer_share_cny", "opex_cny", "margin_cny"],
    )
    _write_csv(
        out_dir / "t1_bridge.csv",
        bridge["items"],
        ["item", "amount_cny", "note"],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "portfolio": {
            "theoretical_power_mw": bid["theoretical_power_mw"],
            "available_power_mw": bid["available_power_mw"],
            "declared_power_mw": bid["declared_power_mw"],
            "bid_mw": bid["bid_mw"],
            "avg_customer_share": bid["avg_customer_share"],
            "resources": bid["resources"],
            "share_of_2027_target": bid["bid_mw"] / (bid["target_2027_10k_kw"] * 10.0),
        },
        "baseline": {
            "days_used": report["baseline_days_used"],
            "diagnostics": report["baseline_diagnostics"],
        },
        "event": {
            "date": event_date,
            "window": expected_start,
            "scenarios": scenarios["rows"],
            "expected_margin_cny": scenarios["expected_margin_cny"],
            "cvar_cny": scenarios["cvar_cny"],
            "cvar_confidence": config["policy"]["scenario_cvar_confidence"],
        },
        "actual": actual,
        "bridge": bridge,
        "warnings": report["warnings"],
        "files": ["baseline.csv", "bid.csv", "scenarios.csv", "t1_bridge.csv", "review.md"],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(out_dir / "review.md", config, report, bid, scenarios, actual, bridge, fingerprint)
    return {"summary": summary, "out_dir": out_dir}


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shanghai user-side VPP instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--history", help="baseline history CSV")
    parser.add_argument("--event", help="event scenario CSV")
    parser.add_argument("--t1-loads", help="T+1 metered loads CSV")
    parser.add_argument("--t1-event", help="T+1 clearing CSV")
    parser.add_argument("--out", default=str(HERE / "out"))
    parser.add_argument("--demo", action="store_true", help="use the bundled synthetic demo data")
    parser.add_argument("--check-config", action="store_true", help="validate and print provenance")
    args = parser.parse_args(argv)

    try:
        config = json.loads(Path(args.instance).read_text(encoding="utf-8"))
        report = validate_instance(config)
    except (OSError, json.JSONDecodeError, ConfigError) as exc:
        print(f"配置校验失败：{exc}", file=sys.stderr)
        return 1

    if args.check_config:
        print(f"配置校验通过：{config['meta']['instance_id']}")
        for item in report["provenance"]:
            print(f"  {item['block']:<32} {item['grade']:<5} {item['source']}")
        for warning in report["warnings"]:
            print(f"  warning: {warning}")
        return 0

    if args.demo:
        history_path = _resolve_data(config, "history")
        event_path = _resolve_data(config, "event")
        t1_loads_path = _resolve_data(config, "t1_loads")
        t1_event_path = _resolve_data(config, "t1_event")
        out_dir = Path(args.out) if args.out != str(HERE / "out") else HERE / "out" / "demo"
    else:
        if not (args.history and args.event and args.t1_loads and args.t1_event):
            print("必须同时提供 --history/--event/--t1-loads/--t1-event，或使用 --demo", file=sys.stderr)
            return 1
        history_path = Path(args.history)
        event_path = Path(args.event)
        t1_loads_path = Path(args.t1_loads)
        t1_event_path = Path(args.t1_event)
        out_dir = Path(args.out)

    try:
        result = run_instance(
            args.instance, history_path, event_path, t1_loads_path, t1_event_path, out_dir
        )
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    portfolio = summary["portfolio"]
    actual = summary["actual"]
    bridge = summary["bridge"]
    print(f"实例：{summary['instance_id']} / 事件 {summary['event']['date']} {summary['event']['window']}")
    print(
        f"组合：可调 {portfolio['theoretical_power_mw']:.1f} MW，申报 {portfolio['bid_mw']:.1f} MW，"
        f"占 2027 目标 {portfolio['share_of_2027_target']:.2%}"
    )
    print(
        f"情景：期望边际 {_wan(summary['event']['expected_margin_cny'])} 万元，"
        f"CVaR {_wan(summary['event']['cvar_cny'])} 万元"
    )
    print(
        f"T+1：响应率 {actual['response_rate']:.2%}，{'有效' if actual['valid'] else '无效'}，"
        f"结算 {actual['paid_mwh']:.1f} MWh，桥残差 {bridge['residual_cny']:.2e} 元"
    )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
