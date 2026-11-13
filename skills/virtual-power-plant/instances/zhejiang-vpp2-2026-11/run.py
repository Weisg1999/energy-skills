#!/usr/bin/env python3
"""Run the Zhejiang VPP 2.0 instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the VPP 2.0 rules, three aggregation units, policy,
  contracts and data contract.
* ``data/events_demo.csv`` is the monthly call list (10 synthetic calls).
* ``data/response_demo.csv`` is the per-event metered response.

The runner validates the aggregation-unit thresholds, settles positive and
negative response in CNY/MW, applies the shortfall assessment cap, computes
the monthly A+ to D rating and the fast-type capacity preparation fee.

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


class ConfigError(ValueError):
    """Raised when the instance or an input file fails validation."""


def _need(block, key, path):
    if not isinstance(block, dict) or key not in block:
        raise ConfigError(f"{path} is missing {key}")
    return block[key]


def _text(block, key, path):
    value = _need(block, key, path)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _number(value, path, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a number")
    if not math.isfinite(value):
        raise ConfigError(f"{path} must be finite")
    if low is not None and value < low - 1e-12:
        raise ConfigError(f"{path} must be >= {low}")
    if high is not None and value > high + 1e-12:
        raise ConfigError(f"{path} must be <= {high}")
    return float(value)


def _grade(block, path):
    grade = _text(block, "grade", path)
    if grade not in {"A", "B", "C", "D", "A/B", "B/C", "C/D", "B/C/D"}:
        raise ConfigError(f"{path}.grade {grade!r} is not a known grade")
    return grade


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report["provenance"].append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block


def _parse_hhmm(value, path):
    text = _text({"value": value}, "value", path)
    try:
        hour, minute = (int(part) for part in text.split(":"))
    except (ValueError, AttributeError):
        raise ConfigError(f"{path} must be HH:MM")
    if not (0 <= hour <= 23 and 0 <= minute < 60):
        raise ConfigError(f"{path} must be a valid time")
    return hour * 60 + minute


def _minutes_label(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _round_mw(value):
    return math.floor(value * 10 + 1e-9) / 10.0


def _capability(config):
    units = {}
    for unit in config["resources"]["units"]:
        units[unit["id"]] = {
            "id": unit["id"],
            "name": unit["name"],
            "unit_type": unit["unit_type"],
            "max_mw": 0.0,
            "positive_mw": 0.0,
            "negative_mw": 0.0,
            "items": [],
            "min_customer_age_months": None,
        }
    for item in config["resources"]["items"]:
        unit_id = item["unit"]
        if unit_id not in units:
            raise ConfigError(f"resource {item['id']} points to unknown unit {unit_id}")
        power = item["max_mw"] * item["availability"]
        positive = power * item["positive_ratio"]
        negative = power * item["negative_ratio"]
        record = units[unit_id]
        record["max_mw"] += item["max_mw"]
        record["positive_mw"] += positive
        record["negative_mw"] += negative
        record["items"].append(item["name"])
        if item.get("customer_age_months") is not None:
            age = float(item["customer_age_months"])
            current = record["min_customer_age_months"]
            record["min_customer_age_months"] = age if current is None else min(current, age)
    return units


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

    vpp2 = _rule_block(rules, "vpp2", report)
    baseline = _rule_block(rules, "baseline", report)
    _rule_block(rules, "spot", report)
    _rule_block(rules, "settlement", report)

    unit_types = _need(vpp2, "unit_types", "rules.vpp2")
    for key in ("generation", "storage", "load"):
        block = _need(unit_types, key, "rules.vpp2.unit_types")
        min_mw = _number(_need(block, "min_mw", f"unit_types.{key}"), f"unit_types.{key}.min_mw", 0.0)
        min_h = _number(
            _need(block, "min_duration_h", f"unit_types.{key}"), f"unit_types.{key}.min_duration_h", 0.0
        )
        if abs(min_mw - 5.0) > 1e-9 or abs(min_h - 1.0) > 1e-9:
            raise ConfigError("VPP 2.0 threshold must be >=5 MW and >=1 h for all three unit types")
    load_age = _number(
        _need(unit_types["load"], "customer_age_months_min", "unit_types.load"),
        "unit_types.load.customer_age_months_min",
        0.0,
    )
    if abs(load_age - 3.0) > 1e-9:
        raise ConfigError("load-type units require customer accounts older than 3 months")

    products = _need(vpp2, "response_products", "rules.vpp2")
    if products != ["调节型", "快速型", "局域型"]:
        raise ConfigError("VPP 2.0 products must be 调节型 / 快速型 / 局域型")

    rating = _need(vpp2, "rating", "rules.vpp2")
    ability_weight = _number(_need(rating, "ability_weight", "rating"), "rating.ability_weight", 0.0, 1.0)
    response_weight = _number(_need(rating, "response_weight", "rating"), "rating.response_weight", 0.0, 1.0)
    if abs(ability_weight - 0.3) > 1e-9 or abs(response_weight - 0.7) > 1e-9:
        raise ConfigError("monthly rating weights must be ability 0.3 / response 0.7")
    thresholds = _need(rating, "thresholds", "rating")
    for grade, expected in (("A+", 95.0), ("A", 90.0), ("B", 80.0), ("C", 70.0)):
        value = _number(_need(thresholds, grade, "rating.thresholds"), f"rating.thresholds.{grade}", 0.0, 100.0)
        if abs(value - expected) > 1e-9:
            raise ConfigError(f"rating threshold for {grade} must be {expected:g}")

    compensation = _need(vpp2, "compensation", "rules.vpp2")
    positive_tiers = _need(compensation, "positive_tiers_cny_per_mw", "compensation")
    negative_tiers = _need(compensation, "negative_tiers_cny_per_mw", "compensation")
    if positive_tiers != [800.0, 1000.0, 1200.0] or negative_tiers != [300.0, 350.0, 380.0]:
        raise ConfigError("VPP 2.0 tiers must be 800/1000/1200 and 300/350/380 CNY/MW")
    pos_cap = _number(_need(compensation, "positive_cap_cny_per_mw", "compensation"), "compensation.positive_cap", 0.0)
    neg_cap = _number(_need(compensation, "negative_cap_cny_per_mw", "compensation"), "compensation.negative_cap", 0.0)
    if abs(pos_cap - 1200.0) > 1e-9 or abs(neg_cap - 380.0) > 1e-9:
        raise ConfigError("VPP 2.0 compensation caps must be 1200 / 380 CNY/MW")

    min_rate = _number(
        _need(vpp2, "min_effective_response_rate", "rules.vpp2"),
        "rules.vpp2.min_effective_response_rate",
        0.0,
        1.0,
    )
    if abs(min_rate - 0.70) > 1e-9:
        raise ConfigError("VPP 2.0 effective response rate must be 70%")
    assessment_rules = _need(vpp2, "assessment", "rules.vpp2")
    cap_ratio = _number(
        _need(assessment_rules, "daily_cap_ratio", "assessment"), "assessment.daily_cap_ratio", 0.0
    )
    if abs(cap_ratio - 1.2) > 1e-9:
        raise ConfigError("daily assessment cap must be 1.2x compensation")
    fast_rules = _need(vpp2, "fast_type", "rules.vpp2")
    fast_threshold = int(
        _number(
            _need(fast_rules, "invalid_calls_zero_threshold", "fast_type"),
            "fast_type.invalid_calls_zero_threshold",
            1.0,
        )
    )
    if fast_threshold != 3:
        raise ConfigError("fast-type preparation fee is zeroed after 3 invalid calls in a month")

    baseline_count = int(_number(_need(baseline, "count", "rules.baseline"), "baseline.count", 1.0))
    deviation = _number(_need(baseline, "deviation", "rules.baseline"), "baseline.deviation", 0.0, 1.0)
    if baseline_count != 5 or abs(deviation - 0.25) > 1e-9:
        raise ConfigError("the bundled D-level baseline is 5 days with a +/-25% screen")

    units_block = _need(resources, "units", "resources")
    items = _need(resources, "items", "resources")
    if not isinstance(units_block, list) or len(units_block) != 3:
        raise ConfigError("resources.units must contain the three VPP 2.0 unit types")
    unit_ids = {unit["id"] for unit in units_block}
    if unit_ids != {"generation", "storage", "load"}:
        raise ConfigError("resources.units must be generation / storage / load")
    if not isinstance(items, list) or not items:
        raise ConfigError("resources.items must be a non-empty list")
    for index, item in enumerate(items):
        path = f"resources.items[{index}]"
        _text(item, "id", path)
        _text(item, "name", path)
        unit_id = _text(item, "unit", path)
        if unit_id not in unit_ids:
            raise ConfigError(f"{path}.unit {unit_id!r} is unknown")
        _number(_need(item, "max_mw", path), f"{path}.max_mw", 1e-9)
        _number(_need(item, "positive_ratio", path), f"{path}.positive_ratio", 0.0, 1.0)
        _number(_need(item, "negative_ratio", path), f"{path}.negative_ratio", 0.0, 1.0)
        _number(_need(item, "availability", path), f"{path}.availability", 0.0, 1.0)
        _grade(item, path)
        _text(item, "source", path)
        if unit_id == "load":
            age = _number(_need(item, "customer_age_months", path), f"{path}.customer_age_months", 0.0)
            if age <= load_age:
                raise ConfigError(f"{path} load customer must be older than {load_age:g} months")

    capabilities = _capability(config)
    for unit_id, record in capabilities.items():
        if record["positive_mw"] < 5.0 - 1e-9:
            raise ConfigError(f"{unit_id} positive capability {record['positive_mw']:.3f} MW is below 5 MW")

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    bid_ratio = _number(_need(policy, "bid_ratio", "policy"), "policy.bid_ratio", 0.0, 1.0)
    if not 0 < bid_ratio <= 1.0:
        raise ConfigError("policy.bid_ratio must be in (0, 1]")
    policy_assessment = _number(
        _need(policy, "assessment_ratio", "policy"), "policy.assessment_ratio", 0.0, 1.0
    )
    policy_fee = _number(
        _need(policy, "fast_prep_fee_cny_per_mw_month", "policy"),
        "policy.fast_prep_fee_cny_per_mw_month",
        0.0,
    )

    assessment_contract = _need(contracts, "assessment", "contracts")
    contract_ratio = _number(
        _need(assessment_contract, "ratio", "contracts.assessment"), "contracts.assessment.ratio", 0.0, 1.0
    )
    if abs(contract_ratio - policy_assessment) > 1e-9:
        raise ConfigError("contracts.assessment.ratio must equal policy.assessment_ratio")
    fee_contract = _need(contracts, "fast_prep_fee", "contracts")
    contract_fee = _number(
        _need(fee_contract, "cny_per_mw_month", "contracts.fast_prep_fee"),
        "contracts.fast_prep_fee.cny_per_mw_month",
        0.0,
    )
    if abs(contract_fee - policy_fee) > 1e-9:
        raise ConfigError("contracts.fast_prep_fee must equal policy.fast_prep_fee_cny_per_mw_month")
    opex = _need(contracts, "opex", "contracts")
    platform = _number(_need(opex, "platform_cny_per_month", "contracts.opex"), "contracts.opex.platform", 0.0)
    metering = _number(_need(opex, "metering_cny_per_event", "contracts.opex"), "contracts.opex.metering", 0.0)

    contract_events = _need(data_contract, "events", "data_contract")
    contract_response = _need(data_contract, "response", "data_contract")
    for key in (
        "event_id_field",
        "date_field",
        "unit_field",
        "product_field",
        "direction_field",
        "start_field",
        "end_field",
        "required_mw_field",
        "price_field",
    ):
        _text(contract_events, key, "data_contract.events")
    for key in ("event_id_field", "unit_field", "actual_mw_field"):
        _text(contract_response, key, "data_contract.response")

    report["checks"].append(
        {
            "units": {key: record["positive_mw"] for key, record in capabilities.items()},
            "bid_ratio": bid_ratio,
            "min_effective_response_rate": min_rate,
            "assessment_ratio": policy_assessment,
            "daily_cap_ratio": cap_ratio,
            "fast_invalid_threshold": fast_threshold,
            "fast_prep_fee_cny_per_mw_month": policy_fee,
            "platform_cny_per_month": platform,
            "metering_cny_per_event": metering,
            "baseline_days": baseline_count,
            "baseline_deviation": deviation,
        }
    )
    report["warnings"].append("浙江 VPP 2.0 基线算法未核到；本包不做基线认定，直接用计量响应量结算")
    report["warnings"].append("月度评级分数阈值与能力/响应分算法为 D 级假设，不是省负荷管理中心正式口径")
    report["warnings"].append("响应补偿按元/MW·次建模，原文计价时长与分档边界待核；不得与现货元/MWh 混用")
    report["predicates"] = {
        "bid_ratio": bid_ratio,
        "min_rate": min_rate,
        "assessment_ratio": policy_assessment,
        "cap_ratio": cap_ratio,
        "fast_invalid_threshold": fast_threshold,
        "fast_fee_per_mw": policy_fee,
        "platform": platform,
        "metering": metering,
        "ability_weight": ability_weight,
        "response_weight": response_weight,
        "thresholds": {key: float(value) for key, value in thresholds.items()},
        "positive_tiers": [float(value) for value in positive_tiers],
        "negative_tiers": [float(value) for value in negative_tiers],
    }
    report["capabilities"] = capabilities
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
    try:
        value = float(row[field])
    except (TypeError, ValueError):
        raise ConfigError(f"{path}:{line_no}.{field} must be a number")
    if not math.isfinite(value):
        raise ConfigError(f"{path}:{line_no}.{field} must be finite")
    return value


def load_events(path, config):
    contract = config["data_contract"]["events"]
    rows = _read_rows(path)
    if not rows:
        raise ConfigError("events file is empty")
    events = []
    seen = set()
    for line_no, row in enumerate(rows, start=2):
        event_id = (row.get(contract["event_id_field"]) or "").strip()
        if not event_id:
            raise ConfigError(f"events line {line_no} has an empty event_id")
        if event_id in seen:
            raise ConfigError(f"duplicate event_id {event_id}")
        seen.add(event_id)
        date = (row.get(contract["date_field"]) or "").strip()
        if len(date) != 10 or date[4] != "-" or date[7] != "-":
            raise ConfigError(f"events line {line_no} date must be YYYY-MM-DD")
        unit_id = (row.get(contract["unit_field"]) or "").strip()
        product = (row.get(contract["product_field"]) or "").strip()
        direction = (row.get(contract["direction_field"]) or "").strip()
        if direction not in {"positive", "negative"}:
            raise ConfigError(f"events line {line_no} direction must be positive/negative")
        start = _parse_hhmm(row.get(contract["start_field"]) or "", f"events:{line_no}.start")
        end = _parse_hhmm(row.get(contract["end_field"]) or "", f"events:{line_no}.end")
        if end <= start:
            raise ConfigError(f"events line {line_no} end must be after start")
        if abs((end - start) / 60.0 - 1.0) > 1e-9:
            raise ConfigError("the bundled D-level events are one-hour calls")
        events.append(
            {
                "event_id": event_id,
                "date": date,
                "month": date[:7],
                "unit_id": unit_id,
                "product": product,
                "direction": direction,
                "start": start,
                "end": end,
                "required_mw": _float_cell(row, contract["required_mw_field"], "events", line_no),
                "price": _float_cell(row, contract["price_field"], "events", line_no),
            }
        )
        compensation = config["rules"]["vpp2"]["compensation"]
        allowed = (
            compensation["positive_tiers_cny_per_mw"]
            if direction == "positive"
            else compensation["negative_tiers_cny_per_mw"]
        )
        if events[-1]["price"] not in [float(value) for value in allowed]:
            raise ConfigError(
                f"events line {line_no} price {events[-1]['price']:g} is not in the "
                f"{direction} tier {allowed}"
            )
    units = {event["unit_id"] for event in events}
    if units != {"generation", "storage", "load"}:
        raise ConfigError("events must cover all three aggregation units")
    if not any(event["direction"] == "positive" for event in events):
        raise ConfigError("events must include at least one positive call")
    if not any(event["direction"] == "negative" for event in events):
        raise ConfigError("events must include at least one negative call")
    if not any(event["product"] == "快速型" for event in events):
        raise ConfigError("events must include at least one fast-type call")
    months = {event["month"] for event in events}
    if len(months) != 1:
        raise ConfigError("the bundled monthly rating needs events from a single month")
    return events


def load_response(path, config, events):
    contract = config["data_contract"]["response"]
    rows = _read_rows(path)
    by_event = {}
    for line_no, row in enumerate(rows, start=2):
        event_id = (row.get(contract["event_id_field"]) or "").strip()
        unit_id = (row.get(contract["unit_field"]) or "").strip()
        actual = _float_cell(row, contract["actual_mw_field"], "response", line_no)
        if actual < 0:
            raise ConfigError(f"response line {line_no} actual_mw must be >= 0")
        if event_id in by_event:
            raise ConfigError(f"duplicate response for event {event_id}")
        by_event[event_id] = {"unit_id": unit_id, "actual_mw": actual}
    expected = {event["event_id"] for event in events}
    if set(by_event) != expected:
        raise ConfigError("response file must contain exactly one row per event")
    for event in events:
        if by_event[event["event_id"]]["unit_id"] != event["unit_id"]:
            raise ConfigError(f"response unit mismatch for event {event['event_id']}")
    return by_event


def settle(config, events, responses, report):
    predicate = report["predicates"]
    capabilities = report["capabilities"]
    settled = []
    for event in events:
        capability = capabilities[event["unit_id"]]
        direction_capability = capability[f"{event['direction']}_mw"] * predicate["bid_ratio"]
        direction_capability = _round_mw(max(0.0, direction_capability))
        cleared = min(direction_capability, event["required_mw"])
        actual = responses[event["event_id"]]["actual_mw"]
        rate = actual / cleared if cleared > 0 else 0.0
        valid = rate >= predicate["min_rate"] - 1e-12
        gross = min(actual, cleared * predicate["cap_ratio"]) * event["price"]
        if valid:
            assessment = 0.0
        else:
            shortfall = max(0.0, cleared - actual)
            assessment = shortfall * event["price"] * predicate["assessment_ratio"]
            assessment = min(assessment, predicate["cap_ratio"] * gross)
        settled.append(
            {
                **event,
                "declared_mw": direction_capability,
                "cleared_mw": cleared,
                "actual_mw": actual,
                "response_rate": rate,
                "valid": valid,
                "gross_cny": gross,
                "assessment_cny": assessment,
                "net_cny": gross - assessment,
            }
        )
    return settled


def monthly_rating(config, report, settled, events):
    predicate = report["predicates"]
    capabilities = report["capabilities"]
    ratings = []
    for unit_id in ("generation", "storage", "load"):
        capability = capabilities[unit_id]
        unit_events = [event for event in settled if event["unit_id"] == unit_id]
        declared = _round_mw(capability["positive_mw"] * predicate["bid_ratio"])
        ability_score = min(declared / 5.0, 1.0) * 100.0
        cleared = sum(event["cleared_mw"] for event in unit_events)
        actual = sum(event["actual_mw"] for event in unit_events)
        response_score = actual / cleared * 100.0 if cleared > 0 else 0.0
        total = predicate["ability_weight"] * ability_score + predicate["response_weight"] * response_score
        grade = "D"
        for candidate in ("A+", "A", "B", "C"):
            if total >= predicate["thresholds"][candidate] - 1e-12:
                grade = candidate
                break
        fast_events = [event for event in unit_events if event["product"] == "快速型"]
        fast_invalid = sum(1 for event in fast_events if not event["valid"])
        if not fast_events:
            prep_fee = 0.0
            prep_status = "不适用（当月无快速型调用）"
        elif fast_invalid >= predicate["fast_invalid_threshold"]:
            prep_fee = 0.0
            prep_status = f"归零（快速型无效调用 {fast_invalid} 次 ≥ {predicate['fast_invalid_threshold']} 次）"
        else:
            prep_fee = declared * predicate["fast_fee_per_mw"]
            prep_status = f"正常计付（快速型无效调用 {fast_invalid} 次 < {predicate['fast_invalid_threshold']} 次）"
        ratings.append(
            {
                "unit_id": unit_id,
                "name": capability["name"],
                "unit_type": capability["unit_type"],
                "declared_mw": declared,
                "ability_score": ability_score,
                "response_score": response_score,
                "total_score": total,
                "grade": grade,
                "events": len(unit_events),
                "valid_events": sum(1 for event in unit_events if event["valid"]),
                "fast_calls": len(fast_events),
                "fast_invalid": fast_invalid,
                "prep_fee_cny": prep_fee,
                "prep_fee_status": prep_status,
            }
        )
    return ratings


def summarize(config, report, settled, ratings):
    predicate = report["predicates"]
    gross = sum(event["gross_cny"] for event in settled)
    assessment = sum(event["assessment_cny"] for event in settled)
    response_net = gross - assessment
    prep_fee = sum(row["prep_fee_cny"] for row in ratings)
    opex = predicate["platform"] + predicate["metering"] * len(settled)
    net = response_net + prep_fee - opex
    return {
        "events": len(settled),
        "gross_cny": gross,
        "assessment_cny": assessment,
        "response_net_cny": response_net,
        "prep_fee_cny": prep_fee,
        "opex_cny": opex,
        "net_cny": net,
        "units_below_threshold": [
            unit_id
            for unit_id, record in report["capabilities"].items()
            if record["positive_mw"] < 5.0 - 1e-9
        ],
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
        if field in ("response_rate", "rate"):
            return f"{value:.4f}"
        if field.endswith("_score"):
            return f"{value:.2f}"
        return f"{value:.2f}"
    return value


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def write_review(path, config, report, settled, ratings, summary, fingerprint):
    predicate = report["predicates"]
    lines = [
        "# 浙江 VPP 2.0 实例 · 复核单",
        "",
        f"- 实例：`{config['meta']['instance_id']}`",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格指纹：`{fingerprint}`",
        "- 全部数据为 D 级合成，不对应任何真实聚合商、聚合单元或结算单。",
        "",
        "## 1. 结论摘要",
        "",
        f"- 三类聚合单元正调节能力：发电 {report['capabilities']['generation']['positive_mw']:.2f} MW、"
        f"储能 {report['capabilities']['storage']['positive_mw']:.2f} MW、"
        f"负荷 {report['capabilities']['load']['positive_mw']:.2f} MW，均达到 ≥5 MW/1 h 门槛。",
        f"- 当月调用 {summary['events']} 次，毛利 {_money(summary['gross_cny'])} 元，"
        f"考核 {_money(summary['assessment_cny'])} 元，响应净额 {_money(summary['response_net_cny'])} 元。",
        f"- 快速型能力准备费 {_money(summary['prep_fee_cny'])} 元；平台与计量运营成本 "
        f"{_money(summary['opex_cny'])} 元；当月净额 {_money(summary['net_cny'])} 元。",
        "- 月度评级："
        + "；".join(f"{row['name']} {row['grade']}（{row['total_score']:.2f} 分）" for row in ratings)
        + "。",
        "",
        "## 2. 三类聚合单元与门槛",
        "",
        "| 单元 | 资源 | 最大 MW | 正调节能力 MW | 负调节能力 MW | 申报正能力 MW | 门槛 | 结果 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for unit_id in ("generation", "storage", "load"):
        record = report["capabilities"][unit_id]
        declared = next(row["declared_mw"] for row in ratings if row["unit_id"] == unit_id)
        lines.append(
            f"| {record['name']} | {'、'.join(record['items'])} | {record['max_mw']:.1f} | "
            f"{record['positive_mw']:.2f} | {record['negative_mw']:.2f} | {declared:.2f} | ≥5 MW/1 h | 通过 |"
        )
    lines += [
        "",
        "门槛来自公告〔2026〕第7号：三类聚合单元均 ≥5 MW、持续 ≥1 h；负荷类还要求用户立户 >3 个月。"
        "资源参数为 D 级合成，不代表任何真实聚合单元。",
        "",
        "## 3. 月度调用与结算",
        "",
        "| 事件 | 日期 | 单元 | 产品 | 方向 | 时段 | 申报 MW | 中标 MW | 实际 MW | 响应率 | 有效 | 补偿（元） | 考核（元） | 净额（元） |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for event in settled:
        lines.append(
            f"| {event['event_id']} | {event['date']} | "
            f"{report['capabilities'][event['unit_id']]['name']} | {event['product']} | "
            f"{'正' if event['direction'] == 'positive' else '负'} | "
            f"{_minutes_label(event['start'])}-{_minutes_label(event['end'])} | "
            f"{event['declared_mw']:.2f} | {event['cleared_mw']:.2f} | {event['actual_mw']:.2f} | "
            f"{_pct(event['response_rate'])} | {'是' if event['valid'] else '否'} | "
            f"{_money(event['gross_cny'])} | {_money(event['assessment_cny'])} | {_money(event['net_cny'])} |"
        )
    lines += [
        "",
        f"补偿 = min(实际 MW, 1.2 × 中标 MW) × 元/MW；有效门槛 {_pct(predicate['min_rate'])}；"
        f"无效事件按实际差额 × 补偿价 × {predicate['assessment_ratio']:.2f} 计考核，"
        f"且不超过补偿的 {_pct(predicate['cap_ratio'])}。考核系数与计价时长均为 D 级假设。",
        "",
        "## 4. 月度评级",
        "",
        "| 单元 | 能力分 | 响应分 | 总分 | 评级 | 调用 / 有效 | 快速型 / 无效 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in ratings:
        lines.append(
            f"| {row['name']} | {row['ability_score']:.2f} | {row['response_score']:.2f} | "
            f"{row['total_score']:.2f} | {row['grade']} | {row['events']} / {row['valid_events']} | "
            f"{row['fast_calls']} / {row['fast_invalid']} |"
        )
    lines += [
        "",
        f"总分 = 能力分 × {predicate['ability_weight']:.1f} + 响应分 × {predicate['response_weight']:.1f}；"
        "能力分 = min(申报正能力 / 5 MW, 1) × 100；响应分 = Σ中标 MW × 响应率 / Σ中标 MW × 100。"
        "能力:响应 = 3:7 为公开口径，分数阈值与两项分数算法为 D 级假设。",
        "",
        "## 5. 快速型能力准备费",
        "",
        "| 单元 | 申报正能力 MW | 快速型调用 | 无效次数 | 准备费（元） | 状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in ratings:
        lines.append(
            f"| {row['name']} | {row['declared_mw']:.2f} | {row['fast_calls']} | {row['fast_invalid']} | "
            f"{_money(row['prep_fee_cny'])} | {row['prep_fee_status']} |"
        )
    lines += [
        "",
        f"准备费单价 {_money(predicate['fast_fee_per_mw'])} 元/MW·月（D 级假设）；"
        f"快速型月内无效调用 ≥{predicate['fast_invalid_threshold']} 次归零。",
        "",
        "## 6. 口径提醒",
        "",
        "- VPP 2.0 响应补偿是 **元/MW**，现货限价是 **元/MWh**；两者单位、市场与文件都不同，不能互相换算。",
        "- 三类聚合单元是发电类 / 储能类 / 负荷类；门槛统一 ≥5 MW/1 h，负荷类另要求立户 >3 个月。",
        "- 2025 年末 49 家 VPP、最大可调 160 万 kW、4,936 家资源是年报口径（C）；2026 年国庆前后 50 家、359.52 万 kW 是调用事件口径（C），都不是长期容量。",
        "- 快速型能力准备费、月度评级分数与考核系数是 D 级建模假设；正式口径以省负荷管理中心结算通知为准。",
        "- 本包不含现货、辅助服务、容量补偿与绿证；参与现货还需调度协议、自动化接入与涉网试验（B/C）。",
        "",
        "## 7. 使用与边界",
        "",
        "```bash",
        "python make_demo.py",
        "python run.py --demo",
        "python run.py --check-config",
        "python run.py --events 我的调用.csv --response 我的响应.csv --out out/my-case",
        "```",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        "- 本复核单是 D 级合成样板，不构成报价、签约或投资建议。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, events_path, response_path, out_dir):
    config = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    report = validate_instance(config)
    events = load_events(events_path, config)
    responses = load_response(response_path, config, events)
    settled = settle(config, events, responses, report)
    ratings = monthly_rating(config, report, settled, events)
    summary = summarize(config, report, settled, ratings)
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]

    out_dir.mkdir(parents=True, exist_ok=True)
    capability_rows = []
    for unit_id in ("generation", "storage", "load"):
        record = report["capabilities"][unit_id]
        declared = next(row["declared_mw"] for row in ratings if row["unit_id"] == unit_id)
        capability_rows.append(
            {
                "unit_id": unit_id,
                "unit_type": record["unit_type"],
                "name": record["name"],
                "resources": len(record["items"]),
                "max_mw": record["max_mw"],
                "positive_mw": record["positive_mw"],
                "negative_mw": record["negative_mw"],
                "declared_positive_mw": declared,
                "threshold_mw": 5.0,
                "pass": record["positive_mw"] >= 5.0 - 1e-9,
            }
        )
    _write_csv(
        out_dir / "unit_capability.csv",
        capability_rows,
        [
            "unit_id",
            "unit_type",
            "name",
            "resources",
            "max_mw",
            "positive_mw",
            "negative_mw",
            "declared_positive_mw",
            "threshold_mw",
            "pass",
        ],
    )
    _write_csv(
        out_dir / "events.csv",
        [
            {
                **event,
                "window": f"{_minutes_label(event['start'])}-{_minutes_label(event['end'])}",
                "price_cny_per_mw": event["price"],
            }
            for event in settled
        ],
        [
            "event_id",
            "date",
            "unit_id",
            "product",
            "direction",
            "window",
            "required_mw",
            "declared_mw",
            "cleared_mw",
            "actual_mw",
            "response_rate",
            "valid",
            "price_cny_per_mw",
            "gross_cny",
            "assessment_cny",
            "net_cny",
        ],
    )
    _write_csv(
        out_dir / "rating.csv",
        ratings,
        [
            "unit_id",
            "name",
            "unit_type",
            "declared_mw",
            "ability_score",
            "response_score",
            "total_score",
            "grade",
            "events",
            "valid_events",
            "fast_calls",
            "fast_invalid",
            "prep_fee_cny",
            "prep_fee_status",
        ],
    )

    summary_doc = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "unit_capabilities": capability_rows,
        "events": settled,
        "ratings": ratings,
        "summary": summary,
        "warnings": report["warnings"],
        "files": ["unit_capability.csv", "events.csv", "rating.csv", "summary.json", "review.md"],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary_doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(out_dir / "review.md", config, report, settled, ratings, summary, fingerprint)
    return {"summary": summary_doc, "out_dir": out_dir}


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Zhejiang VPP 2.0 instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--events", help="monthly call CSV")
    parser.add_argument("--response", help="per-event metered response CSV")
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
        for unit_id, record in report["capabilities"].items():
            print(
                f"  {record['name']:<12} 正调节 {record['positive_mw']:.2f} MW / "
                f"负调节 {record['negative_mw']:.2f} MW"
            )
        for warning in report["warnings"]:
            print(f"  warning: {warning}")
        return 0

    if args.demo:
        events_path = _resolve_data(config, "events")
        response_path = _resolve_data(config, "response")
        out_dir = HERE / "out" / "demo"
    else:
        if not args.events or not args.response:
            parser.error("--events and --response are required unless --demo or --check-config is used")
        events_path = Path(args.events)
        response_path = Path(args.response)
        out_dir = Path(args.out)

    try:
        result = run_instance(args.instance, events_path, response_path, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]["summary"]
    print(f"实例：{config['meta']['instance_id']} / 当月调用 {summary['events']} 次")
    print(
        "评级："
        + "；".join(
            f"{row['name']} {row['grade']}" for row in result["summary"]["ratings"]
        )
    )
    print(
        f"响应净额 {summary['response_net_cny']:,.0f} 元 / 准备费 {summary['prep_fee_cny']:,.0f} 元 / "
        f"净额 {summary['net_cny']:,.0f} 元"
    )
    print(f"输出目录：{out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
