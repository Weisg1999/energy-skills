#!/usr/bin/env python3
"""Run the Shandong coal-CHP thermal instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the rule parameters, asset, policy profile and data
  contract. A trader edits it; no code change is needed for a new unit or a
  new style profile.
* ``data/d1_demo.csv`` is a 96-point, five-scenario D-1 price set plus the heat
  load forecast.
* ``data/t1_demo.csv`` is the T+1 actual price, metered output and heat load.

This pack deliberately does not reuse the storage DP kernel: a thermal unit is
not a battery. The schedule is a two-block price-taker: a must-run block set
by the heat constraint, plus an incremental block offered above variable cost.
Capacity compensation is a placeholder because the Shandong standard is not
publicly closed.

All bundled numbers are synthetic grade D. They are not a market forecast, a
live trading signal or investment advice.
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

import desk  # noqa: E402


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


def _rule_block(rules, name):
    block = _need(rules, name, "rules")
    for key in ("grade", "source"):
        _text(block, key, f"rules.{name}")
    return block


def validate_instance(config):
    """Validate the six blocks and return a provenance report."""
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot")
    _rule_block(rules, "settlement")
    capacity = _rule_block(rules, "capacity_compensation")
    _rule_block(rules, "thermal_participation")
    ancillary = _rule_block(rules, "ancillary")

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = int(_number(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1))
    expected_points = 24 * 60 / mtu
    if abs(expected_points - points) > 1e-9:
        raise ConfigError(
            f"rules.spot.points_per_day ({points}) does not match 24*60/{mtu:g}"
        )
    declare_floor = _number(
        _need(spot, "declare_floor_cny_per_mwh", "rules.spot"),
        "rules.spot.declare_floor_cny_per_mwh",
    )
    declare_cap = _number(
        _need(spot, "declare_cap_cny_per_mwh", "rules.spot"),
        "rules.spot.declare_cap_cny_per_mwh",
    )
    clear_floor = _number(
        _need(spot, "clear_floor_cny_per_mwh", "rules.spot"),
        "rules.spot.clear_floor_cny_per_mwh",
    )
    clear_cap = _number(
        _need(spot, "clear_cap_cny_per_mwh", "rules.spot"),
        "rules.spot.clear_cap_cny_per_mwh",
    )
    if not (clear_floor <= declare_floor < declare_cap <= clear_cap):
        raise ConfigError(
            "price bounds must satisfy clear_floor <= declare_floor < declare_cap <= clear_cap"
        )

    power = _number(_need(asset, "power_mw", "asset"), "asset.power_mw", 1e-9)
    min_output = _number(_need(asset, "min_output_mw", "asset"), "asset.min_output_mw", 0.0)
    if min_output > power + 1e-9:
        raise ConfigError("asset.min_output_mw must not exceed asset.power_mw")
    heat_load = _number(_need(asset, "heat_load_mw_th", "asset"), "asset.heat_load_mw_th", 0.0)
    heat_ratio = _number(
        _need(asset, "heat_to_power_ratio", "asset"), "asset.heat_to_power_ratio", 1e-9
    )
    _number(_need(asset, "ramp_mw_per_min", "asset"), "asset.ramp_mw_per_min", 1e-9)
    _number(
        _need(asset, "variable_cost_cny_per_mwh", "asset"),
        "asset.variable_cost_cny_per_mwh",
        0.0,
    )
    _number(asset.get("fixed_cost_cny_per_day", 0.0), "asset.fixed_cost_cny_per_day", 0.0)
    effective = _number(
        asset.get("effective_capacity_mw", power),
        "asset.effective_capacity_mw",
        0.0,
    )
    heat_min = max(min_output, heat_load / heat_ratio)
    if heat_min > power + 1e-9:
        raise ConfigError("heat load implies a minimum output above asset.power_mw")

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    qty_q = _number(
        _need(policy, "declared_quantity_quantile", "policy"),
        "policy.declared_quantity_quantile",
        0.0,
        1.0,
    )
    price_q = _number(
        _need(policy, "price_reference_quantile", "policy"),
        "policy.price_reference_quantile",
        0.0,
        1.0,
    )
    markup = _number(
        _need(policy, "energy_markup_cny_per_mwh", "policy"),
        "policy.energy_markup_cny_per_mwh",
        0.0,
    )
    reserve = _number(
        _need(policy, "regulation_reserve_mw", "policy"),
        "policy.regulation_reserve_mw",
        0.0,
    )
    if reserve + heat_min > power + 1e-9:
        raise ConfigError(
            "policy.regulation_reserve_mw plus the heat minimum exceeds asset.power_mw"
        )
    mileage = _number(
        _need(policy, "mileage_per_kw_day", "policy"), "policy.mileage_per_kw_day", 0.0
    )
    mileage_price = _number(
        _need(policy, "mileage_price_cny_per_kw_mile", "policy"),
        "policy.mileage_price_cny_per_kw_mile",
        0.0,
    )
    cap = _number(
        _need(ancillary, "mileage_price_cap_cny_per_kw_mile", "rules.ancillary"),
        "rules.ancillary.mileage_price_cap_cny_per_kw_mile",
        0.0,
    )
    if mileage_price > cap + 1e-12:
        raise ConfigError("policy mileage price exceeds the provincial cap")
    k_factor = _number(_need(policy, "k_factor", "policy"), "policy.k_factor", 0.0)
    coefficient_cap = _number(
        _need(ancillary, "coefficient_cap", "rules.ancillary"),
        "rules.ancillary.coefficient_cap",
        0.0,
    )
    if k_factor > coefficient_cap + 1e-12:
        raise ConfigError("policy.k_factor exceeds the provincial coefficient cap")

    def block(name, extra=""):
        item = {
            "block": f"rules.{name}",
            "grade": rules[name]["grade"],
            "source": rules[name]["source"],
        }
        if extra:
            item["status"] = extra
        return item

    provenance = [
        block("spot"),
        block("settlement"),
        block("capacity_compensation", capacity.get("status", "")),
        block("thermal_participation"),
        block("ancillary", ancillary.get("status", "")),
    ]
    if "negative_price" in rules:
        _rule_block(rules, "negative_price")
        provenance.append(block("negative_price"))

    warnings = []
    if capacity.get("price_cny_per_kw_year") is None or capacity.get("supply_demand_coefficient") is None:
        warnings.append(
            "容量补偿未计入：补偿电价标准或容量供需系数为空；山东具体数值待核实。"
        )
    if effective > power + 1e-9:
        warnings.append("有效容量大于额定功率，请确认容量认定口径。")
    if not config.get("contracts"):
        warnings.append("未配置中长期/CfD 合约；本切片按纯现货 + 调频 + 容量补偿占位结算。")
    warnings.append("调频 K 值与日里程为 D 级示例；机组侧 K 值按省级细则核定。")
    warnings.append("供热收益、燃料中长期与两个细则考核未纳入，不能把本表净边际当机组利润。")

    d1 = _need(data_contract, "d1", "data_contract")
    _text(d1, "file", "data_contract.d1")
    required = _need(d1, "required_fields", "data_contract.d1")
    if not isinstance(required, list) or len(required) == 0:
        raise ConfigError("data_contract.d1.required_fields must be a non-empty list")
    scenario_fields = _need(d1, "scenario_fields", "data_contract.d1")
    if not isinstance(scenario_fields, list) or len(scenario_fields) < 2:
        raise ConfigError("data_contract.d1.scenario_fields needs at least two scenarios")
    for field in scenario_fields:
        if field not in required:
            raise ConfigError(f"data_contract.d1.required_fields is missing {field}")
    weights = d1.get("scenario_weights", [1.0 / len(scenario_fields)] * len(scenario_fields))
    if len(weights) != len(scenario_fields):
        raise ConfigError("data_contract.d1.scenario_weights must match scenario_fields")
    parsed_weights = [_number(value, "data_contract.d1.scenario_weights", 0.0) for value in weights]
    if abs(sum(parsed_weights) - 1.0) > 1e-9:
        raise ConfigError("data_contract.d1.scenario_weights must sum to 1")
    t1 = _need(data_contract, "t1", "data_contract.t1")
    _text(t1, "file", "data_contract.t1")
    t1_required = _need(t1, "required_fields", "data_contract.t1")
    if not isinstance(t1_required, list) or len(t1_required) == 0:
        raise ConfigError("data_contract.t1.required_fields must be a non-empty list")

    return {
        "ok": True,
        "provenance": provenance,
        "warnings": warnings,
        "points_per_day": points,
        "mtu_min": mtu,
        "bounds": {
            "declare_floor": declare_floor,
            "declare_cap": declare_cap,
            "clear_floor": clear_floor,
            "clear_cap": clear_cap,
        },
        "scenario_weights": parsed_weights,
        "scenario_fields": list(scenario_fields),
        "heat_min_mw": heat_min,
    }


def _read_rows(path):
    if not path.exists():
        raise ConfigError(f"input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            if None in raw:
                raise ConfigError(f"{path.name}: row has more columns than the header")
            rows.append(
                {
                    (key.strip() if isinstance(key, str) else key): (
                        value.strip() if isinstance(value, str) else value
                    )
                    for key, value in raw.items()
                }
            )
    if not rows:
        raise ConfigError(f"{path.name} is empty")
    return rows


def _check_shape(rows, required, points, name):
    report = desk.validate_public_dataset(
        rows, required, points_per_day=points, date_field="date", slot_field="slot"
    )
    if not report["ok"]:
        raise ConfigError(
            f"{name} failed schema check: missing={report['missing_fields']} "
            f"duplicates={report['duplicates'][:3]} gaps={report['gaps'][:1]} "
            f"bad_slots={report['bad_slots'][:3]}"
        )
    return report


def _slot_time(slot, mtu_min):
    minutes = int(slot * mtu_min)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def read_d1(path, config, report):
    rows = _read_rows(path)
    d1 = config["data_contract"]["d1"]
    _check_shape(rows, d1["required_fields"], report["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    scenario_fields = report["scenario_fields"]
    prices = []
    for field in scenario_fields:
        series = []
        for slot in range(report["points_per_day"]):
            price = _number(by_slot[slot][field], f"{path.name}:{field}@slot{slot}")
            if not (
                report["bounds"]["clear_floor"] - 0.01
                <= price
                <= report["bounds"]["clear_cap"] + 0.01
            ):
                raise ConfigError(
                    f"{path.name}:{field}@slot{slot}={price} is outside the clearing band"
                )
            series.append(price)
        prices.append(series)
    heat = []
    for slot in range(report["points_per_day"]):
        value = _number(
            by_slot[slot]["heat_load_mw_th"], f"{path.name}:heat_load_mw_th@slot{slot}", 0.0
        )
        heat.append(value)
    return {
        "date": rows[0]["date"],
        "slots": list(range(report["points_per_day"])),
        "prices": prices,
        "heat_load": heat,
        "start": {slot: by_slot[slot]["start"] for slot in by_slot},
        "end": {slot: by_slot[slot]["end"] for slot in by_slot},
    }


def read_t1(path, config, report, power_mw):
    rows = _read_rows(path)
    t1 = config["data_contract"]["t1"]
    _check_shape(rows, t1["required_fields"], report["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    actual_price = []
    actual_output = []
    actual_heat = []
    for slot in range(report["points_per_day"]):
        row = by_slot[slot]
        price = _number(row["actual_price"], f"{path.name}:actual_price@slot{slot}")
        if not (
            report["bounds"]["clear_floor"] - 0.01
            <= price
            <= report["bounds"]["clear_cap"] + 0.01
        ):
            raise ConfigError(
                f"{path.name}:actual_price@slot{slot}={price} is outside the clearing band"
            )
        output = _number(row["actual_output_mw"], f"{path.name}:actual_output_mw@slot{slot}", 0.0)
        if output > power_mw + 1e-6:
            raise ConfigError(f"{path.name}:slot {slot} exceeds asset.power_mw")
        heat = _number(
            row["actual_heat_load_mw_th"],
            f"{path.name}:actual_heat_load_mw_th@slot{slot}",
            0.0,
        )
        actual_price.append(price)
        actual_output.append(output)
        actual_heat.append(heat)
    return {
        "date": rows[0]["date"],
        "price": actual_price,
        "output_mw": actual_output,
        "heat_load": actual_heat,
    }


def quantile(values, q):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile needs at least one value")
    if q <= 0:
        return ordered[0]
    if q >= 1:
        return ordered[-1]
    position = (len(ordered) - 1) * q
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def heat_min_mw(config, heat_load):
    asset = config["asset"]
    return min(
        float(asset["power_mw"]),
        max(float(asset["min_output_mw"]), float(heat_load) / float(asset["heat_to_power_ratio"])),
    )


def scenario_output(config, price, heat_min):
    asset = config["asset"]
    policy = config["policy"]
    energy_max = float(asset["power_mw"]) - float(policy["regulation_reserve_mw"])
    threshold = float(asset["variable_cost_cny_per_mwh"]) + float(
        policy["energy_markup_cny_per_mwh"]
    )
    output = energy_max if float(price) >= threshold else heat_min
    return max(heat_min, min(output, energy_max))


def build_bid(prices_by_scenario, heat_load, config, report):
    asset = config["asset"]
    policy = config["policy"]
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    weights = report["scenario_weights"]

    must_run = [heat_min_mw(config, value) for value in heat_load]
    schedules = []
    for series in prices_by_scenario:
        schedules.append(
            [
                scenario_output(config, series[t], must_run[t])
                for t in range(n)
            ]
        )

    reference = [
        quantile([prices_by_scenario[s][t] for s in range(len(prices_by_scenario))], policy["price_reference_quantile"])
        for t in range(n)
    ]
    incremental = [
        max(
            0.0,
            quantile(
                [schedules[s][t] - must_run[t] for s in range(len(schedules))],
                policy["declared_quantity_quantile"],
            ),
        )
        for t in range(n)
    ]

    offer = []
    offer_clip = []
    cost_offer = float(asset["variable_cost_cny_per_mwh"]) + float(
        policy["energy_markup_cny_per_mwh"]
    )
    for slot in range(n):
        raw = cost_offer
        offer.append(
            min(report["bounds"]["declare_cap"], max(report["bounds"]["declare_floor"], raw))
        )
        offer_clip.append(
            "floor"
            if raw < report["bounds"]["declare_floor"]
            else "cap"
            if raw > report["bounds"]["declare_cap"]
            else ""
        )

    rows = []
    for slot in range(n):
        probability = sum(
            weights[s]
            for s in range(len(weights))
            if prices_by_scenario[s][slot] >= offer[slot] - 1e-9
        )
        rows.append(
            {
                "date": None,
                "slot": slot,
                "side": "generation",
                "must_run_mw": must_run[slot],
                "quantity_mw": incremental[slot],
                "price_cny_per_mwh": offer[slot],
                "reference_price": reference[slot],
                "clear_probability": probability,
                "expected_mw": must_run[slot] + incremental[slot] * probability,
                "note": (
                    f"q={policy['declared_quantity_quantile']:.2f}; "
                    f"markup={offer[slot] - float(asset['variable_cost_cny_per_mwh']):.1f}"
                    + (f"; {offer_clip[slot]}-clipped" if offer_clip[slot] else "")
                ),
            }
        )

    plan = [
        must_run[t] + (incremental[t] if reference[t] >= offer[t] - 1e-9 else 0.0)
        for t in range(n)
    ]
    return {
        "schedules": schedules,
        "reference": reference,
        "must_run": must_run,
        "incremental": incremental,
        "offer": offer,
        "rows": rows,
        "plan_output": plan,
        "warnings": [],
        "throughput_mwh": sum(plan) * dt_h,
    }


def ancillary_daily(config):
    policy = config["policy"]
    return (
        float(policy["regulation_reserve_mw"])
        * 1000.0
        * float(policy["mileage_per_kw_day"])
        * float(policy["mileage_price_cny_per_kw_mile"])
        * float(policy["k_factor"])
    )


def daily_capacity(config):
    block = config["rules"]["capacity_compensation"]
    price = block.get("price_cny_per_kw_year")
    coefficient = block.get("supply_demand_coefficient")
    if price is None or coefficient is None:
        return None
    effective = float(config["asset"].get("effective_capacity_mw", config["asset"]["power_mw"]))
    return effective * 1000.0 * float(price) * float(coefficient) / 365.0


def evaluate_plan(bid, prices_by_scenario, config, report):
    asset = config["asset"]
    dt_h = report["mtu_min"] / 60.0
    weights = report["scenario_weights"]
    variable = float(asset["variable_cost_cny_per_mwh"])
    fixed = float(asset.get("fixed_cost_cny_per_day", 0.0))
    ancillary = ancillary_daily(config)
    capacity = daily_capacity(config)
    capacity_value = 0.0 if capacity is None else capacity
    n = report["points_per_day"]
    outcomes = []
    for index, prices in enumerate(prices_by_scenario):
        output = [
            bid["must_run"][t]
            + (bid["incremental"][t] if prices[t] >= bid["offer"][t] - 1e-9 else 0.0)
            for t in range(n)
        ]
        energy = sum(output[t] * (prices[t] - variable) * dt_h for t in range(n))
        net = energy + ancillary + capacity_value - fixed
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "mean_price": sum(prices) / n,
                "output_mwh": sum(output) * dt_h,
                "energy_margin_cny": energy,
                "ancillary_cny": ancillary,
                "capacity_cny": capacity_value,
                "fixed_cost_cny": fixed,
                "net_margin_cny": net,
            }
        )
    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    cvar = desk.weighted_cvar([(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=0.10)
    reference_energy = sum(
        bid["plan_output"][t] * (bid["reference"][t] - variable) * dt_h for t in range(n)
    )
    reference_net = reference_energy + ancillary + capacity_value - fixed
    return {
        "outcomes": outcomes,
        "expected_net_margin_cny": expected,
        "cvar_10_cny": cvar,
        "energy_margin_at_reference_cny": reference_energy,
        "ancillary_cny": ancillary,
        "capacity_compensation_cny": capacity,
        "fixed_cost_cny": fixed,
        "net_margin_at_reference_cny": reference_net,
        "expected_output_mwh": sum(
            (bid["must_run"][t] + bid["incremental"][t] * sum(
                weights[s]
                for s in range(len(weights))
                if prices_by_scenario[s][t] >= bid["offer"][t] - 1e-9
            ))
            for t in range(n)
        ) * dt_h,
    }


def build_bridge(bid, t1, config, report):
    dt_h = report["mtu_min"] / 60.0
    variable = float(config["asset"]["variable_cost_cny_per_mwh"])
    fixed = float(config["asset"].get("fixed_cost_cny_per_day", 0.0))
    ancillary = ancillary_daily(config)
    capacity = daily_capacity(config)
    capacity_value = 0.0 if capacity is None else capacity
    n = report["points_per_day"]

    plan_output = bid["plan_output"]
    plan_energy = sum(
        plan_output[t] * (bid["reference"][t] - variable) * dt_h for t in range(n)
    )
    plan_profit = plan_energy + ancillary + capacity_value - fixed
    actual_energy = sum(
        t1["output_mw"][t] * (t1["price"][t] - variable) * dt_h for t in range(n)
    )
    actual_profit = actual_energy + ancillary + capacity_value - fixed

    price_effect = sum(
        plan_output[t] * (t1["price"][t] - bid["reference"][t]) * dt_h for t in range(n)
    )
    quantity_effect = sum(
        (t1["output_mw"][t] - plan_output[t]) * (bid["reference"][t] - variable) * dt_h
        for t in range(n)
    )
    interaction = sum(
        (t1["output_mw"][t] - plan_output[t]) * (t1["price"][t] - bid["reference"][t]) * dt_h
        for t in range(n)
    )
    buckets = [
        {"item": "价差影响", "category": "price", "owner": "市场", "amount": price_effect},
        {"item": "量差影响", "category": "quantity", "owner": "执行/供热", "amount": quantity_effect},
        {"item": "价量交叉", "category": "interaction", "owner": "共同", "amount": interaction},
        {"item": "调频收入", "category": "ancillary", "owner": "运行", "amount": 0.0},
        {"item": "容量补偿", "category": "capacity", "owner": "规则", "amount": 0.0},
        {"item": "固定成本", "category": "fixed", "owner": "财务", "amount": 0.0},
    ]
    delta = actual_profit - plan_profit
    identity_gap = delta - sum(item["amount"] for item in buckets)
    return {
        "plan_profit": plan_profit,
        "actual_profit": actual_profit,
        "delta": delta,
        "identity_gap": identity_gap,
        "plan_energy": plan_energy,
        "actual_energy": actual_energy,
        "plan_ancillary": ancillary,
        "actual_ancillary": ancillary,
        "plan_capacity": capacity_value,
        "actual_capacity": capacity_value,
        "plan_fixed": fixed,
        "actual_fixed": fixed,
        "buckets": buckets,
    }


def build_bridge_detail(bid, t1, config, report):
    dt_h = report["mtu_min"] / 60.0
    variable = float(config["asset"]["variable_cost_cny_per_mwh"])
    detail = []
    for slot in range(report["points_per_day"]):
        delta_output = t1["output_mw"][slot] - bid["plan_output"][slot]
        detail.append(
            {
                "slot": slot,
                "start": _slot_time(slot, report["mtu_min"]),
                "plan_output_mw": bid["plan_output"][slot],
                "actual_output_mw": t1["output_mw"][slot],
                "plan_heat_mw_th": bid["must_run"][slot],
                "actual_heat_mw_th": t1["heat_load"][slot],
                "quantity_effect_cny": delta_output
                * (bid["reference"][slot] - variable)
                * dt_h,
            }
        )
    detail.sort(key=lambda item: abs(item["quantity_effect_cny"]), reverse=True)
    return detail[:5]


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(field, row.get(field)) for field in fields})


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _signed(value):
    return 0.0 if abs(value) < 0.5 else value


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, float):
        if field in ("quantity_mw", "expected_mw", "must_run_mw"):
            return f"{value:.3f}"
        if field in ("price_cny_per_mwh", "reference_price"):
            return f"{value:.2f}"
        if field == "clear_probability":
            return f"{value:.3f}"
        if field in ("amount", "quantity_effect_cny"):
            return f"{_signed(value):.2f}"
        return f"{value:.6f}"
    return value


def write_review(path, config, report, d1, bid, evaluation, bridge, bridge_detail, policy_fingerprint):
    policy = config["policy"]
    asset = config["asset"]
    dt_h = report["mtu_min"] / 60.0
    lines = [
        f"# 山东煤电/热电复核表：{config['meta']['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']} 分钟）",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格档：`{policy['profile_id']}` / 指纹 `{policy_fingerprint}`",
        f"- 机组：{asset['power_mw']:.0f} MW，最小出力 {asset['min_output_mw']:.0f} MW，"
        f"供热 {asset['heat_load_mw_th']:.0f} MW_th，热电比 {asset['heat_to_power_ratio']:.2f}",
        "",
        "## 1. 规则来源与未核实项",
        "",
        "| 规则块 | 级别 | 来源 | 状态 |",
        "|---|---|---|---|",
    ]
    for item in report["provenance"]:
        lines.append(
            f"| {item['block']} | {item['grade']} | {item['source']} | {item.get('status', '—')} |"
        )
    lines += [
        "",
        "## 2. 申报摘要",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 申报电量（参考价口径） | {bid['throughput_mwh']:.1f} MWh |",
        f"| 供热最小出力均值 | {sum(bid['must_run']) / len(bid['must_run']):.1f} MW |",
        f"| 调频备用 | {policy['regulation_reserve_mw']:.1f} MW |",
        f"| 调频日收入（D 级） | {_money(evaluation['ancillary_cny'])} CNY |",
        f"| 参考价口径电能量边际 | {_money(evaluation['energy_margin_at_reference_cny'])} CNY |",
        f"| 参考价口径净边际 | {_money(evaluation['net_margin_at_reference_cny'])} CNY |",
        f"| 情景期望净边际 | {_money(evaluation['expected_net_margin_cny'])} CNY |",
        f"| 情景 CVaR10 | {_money(evaluation['cvar_10_cny'])} CNY |",
        f"| 容量补偿 | {_money(evaluation['capacity_compensation_cny'])} CNY |",
        "",
        "## 3. 情景清算",
        "",
        "| 情景 | 权重 | 均价 | 上网电量 | 电能量边际 | 调频 | 净边际 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in evaluation["outcomes"]:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['mean_price']:.1f} | "
            f"{item['output_mwh']:.1f} | {item['energy_margin_cny']:,.0f} | "
            f"{item['ancillary_cny']:,.0f} | {item['net_margin_cny']:,.0f} |"
        )
    lines += [
        "",
        "> 读法：净边际只含现货电能量、调频与容量补偿占位，不含供热收益与燃料中长期；不能当机组利润。",
    ]
    if bridge is None:
        lines += ["", "## 4. T+1 差异桥", "", "未提供 T+1 实际数据，本次只出申报表。"]
    else:
        ordered = sorted(bridge["buckets"], key=lambda item: abs(item["amount"]), reverse=True)
        lines += [
            "",
            "## 4. T+1 差异桥",
            "",
            f"计划利润 {bridge['plan_profit']:,.0f} CNY，实际利润 {bridge['actual_profit']:,.0f} CNY，"
            f"差异 {bridge['delta']:,.0f} CNY，残差 {bridge['identity_gap']:.2e}。",
            "",
            "| 科目 | 类别 | 责任 | 金额（CNY） |",
            "|---|---|---|---:|",
        ]
        for item in ordered:
            lines.append(
                f"| {item['item']} | {item['category']} | {item['owner']} | {_signed(item['amount']):,.0f} |"
            )
        top = ordered[0] if ordered else None
        lines += [
            "",
            f"**最大差异科目**：{top['item'] if top else '—'}，{top['amount']:,.0f} CNY。"
            if top
            else "**最大差异科目**：—",
            "",
        ]
        if bridge_detail:
            lines += [
                "**量差最大的 5 个时段**（按参考价与变动成本折算）：",
                "",
                "| 时段 | 计划出力 | 实际出力 | 计划供热 | 实际供热 | 量影响（CNY） |",
                "|---|---:|---:|---:|---:|---:|",
            ]
            for item in bridge_detail:
                lines.append(
                    f"| {item['start']} | {item['plan_output_mw']:.1f} | {item['actual_output_mw']:.1f} | "
                    f"{item['plan_heat_mw_th']:.1f} | {item['actual_heat_mw_th']:.1f} | "
                    f"{_signed(item['quantity_effect_cny']):,.0f} |"
                )
    lines += [
        "",
        "## 5. 三个复核问题",
        "",
        "1. 最大差异科目归因到价、量、供热、执行、口径还是规则版本？证据包是否齐全？",
        "2. 供热最小出力是否按当日实际供热负荷重算？有没有用昨日最小出力代替？",
        "3. 容量补偿、运行成本补偿、两个细则考核是否仍未纳入？下一版要不要接入？",
        "",
        "## 6. 下一日动作（人工填写）",
        "",
        "- [ ] ",
        "- [ ] ",
        "- [ ] ",
        "",
        "## 7. 告警与边界",
        "",
    ]
    for warning in report["warnings"] + bid["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        f"- {config['meta']['disclaimer']}",
        "- 本表是价格接受者口径的盘面复核，不是市场出清仿真；实际出清、结算与考核以交易中心、调度机构正式结果为准。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, d1_path, t1_path, out_dir):
    """Validate, optimise, write the bid sheet, bridge and review."""
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{instance_path.name} is not valid JSON: {exc}") from exc
    report = validate_instance(config)
    d1_path = Path(d1_path)
    d1 = read_d1(d1_path, config, report)
    if t1_path is not None:
        t1 = read_t1(Path(t1_path), config, report, float(config["asset"]["power_mw"]))
        if t1["date"] != d1["date"]:
            raise ConfigError("D-1 and T+1 files must refer to the same trading day")
    else:
        t1 = None

    bid = build_bid(d1["prices"], d1["heat_load"], config, report)
    evaluation = evaluate_plan(bid, d1["prices"], config, report)
    bridge = None
    bridge_detail = None
    if t1 is not None:
        bridge = build_bridge(bid, t1, config, report)
        bridge_detail = build_bridge_detail(bid, t1, config, report)

    for row in bid["rows"]:
        row["date"] = d1["date"]
        row["start"] = d1["start"][row["slot"]]
        row["end"] = d1["end"][row["slot"]]

    policy_fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bid_fields = [
        "date",
        "slot",
        "start",
        "end",
        "side",
        "must_run_mw",
        "quantity_mw",
        "price_cny_per_mwh",
        "reference_price",
        "clear_probability",
        "expected_mw",
        "note",
    ]
    _write_csv(out_dir / "bid_sheet.csv", bid["rows"], bid_fields)

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": policy_fingerprint,
        "provenance": report["provenance"],
        "plan": {
            "output_mwh": bid["throughput_mwh"],
            "must_run_average_mw": sum(bid["must_run"]) / len(bid["must_run"]),
            "regulation_reserve_mw": config["policy"]["regulation_reserve_mw"],
            "expected_output_mwh": evaluation["expected_output_mwh"],
            "energy_margin_at_reference_cny": evaluation["energy_margin_at_reference_cny"],
            "ancillary_cny": evaluation["ancillary_cny"],
            "capacity_compensation_cny": evaluation["capacity_compensation_cny"],
            "fixed_cost_cny": evaluation["fixed_cost_cny"],
            "net_margin_at_reference_cny": evaluation["net_margin_at_reference_cny"],
            "expected_net_margin_cny": evaluation["expected_net_margin_cny"],
            "cvar_10_cny": evaluation["cvar_10_cny"],
            "scenarios": evaluation["outcomes"],
        },
        "warnings": report["warnings"] + bid["warnings"],
        "files": {
            "bid_sheet": "bid_sheet.csv",
            "review": "review.md",
            "bridge": "bridge.json" if bridge is not None else None,
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if bridge is not None:
        bridge_out = {
            "plan_profit": bridge["plan_profit"],
            "actual_profit": bridge["actual_profit"],
            "delta": bridge["delta"],
            "identity_gap": bridge["identity_gap"],
            "plan_energy": bridge["plan_energy"],
            "actual_energy": bridge["actual_energy"],
            "plan_ancillary": bridge["plan_ancillary"],
            "actual_ancillary": bridge["actual_ancillary"],
            "plan_capacity": bridge["plan_capacity"],
            "actual_capacity": bridge["actual_capacity"],
            "buckets": bridge["buckets"],
            "top_quantity_slots": bridge_detail,
        }
        (out_dir / "bridge.json").write_text(
            json.dumps(bridge_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _write_csv(
            out_dir / "bridge.csv",
            bridge_out["buckets"],
            ["item", "category", "owner", "amount"],
        )
    write_review(
        out_dir / "review.md",
        config,
        report,
        d1,
        bid,
        evaluation,
        bridge,
        bridge_detail,
        policy_fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "bid": bid,
        "evaluation": evaluation,
        "bridge": bridge,
        "bridge_detail": bridge_detail,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shandong coal-CHP thermal instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", help="D-1 96-point scenario CSV with heat load")
    parser.add_argument("--t1", help="T+1 actual CSV; omit to skip the bridge")
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
        d1_path = _resolve_data(config, "d1")
        t1_path = _resolve_data(config, "t1")
        out_dir = Path(args.out) if args.out != str(HERE / "out") else HERE / "out" / "demo"
    else:
        if not args.d1:
            print("必须提供 --d1，或使用 --demo", file=sys.stderr)
            return 1
        d1_path = Path(args.d1)
        t1_path = Path(args.t1) if args.t1 else None
        out_dir = Path(args.out)

    try:
        result = run_instance(args.instance, d1_path, t1_path, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    plan = summary["plan"]
    print(f"实例：{summary['instance_id']} / 交易日 {summary['trading_day']}")
    print(
        f"申报：上网电量 {plan['output_mwh']:.1f} MWh，"
        f"供热最小出力均值 {plan['must_run_average_mw']:.1f} MW，"
        f"调频备用 {plan['regulation_reserve_mw']:.1f} MW"
    )
    print(
        f"情景：期望净边际 {plan['expected_net_margin_cny']:,.0f} CNY，"
        f"CVaR10 {plan['cvar_10_cny']:,.0f} CNY"
    )
    if result["bridge"] is not None:
        print(
            f"差异桥：计划 {result['bridge']['plan_profit']:,.0f} → "
            f"实际 {result['bridge']['actual_profit']:,.0f}，"
            f"差异 {result['bridge']['delta']:,.0f} CNY，残差 {result['bridge']['identity_gap']:.2e}"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
