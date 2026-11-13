#!/usr/bin/env python3
"""Run the Gansu wind-farm instance pack (2027 H1 mechanism window).

The engine is shared, the instance is local:

* ``instance.json`` holds the market rules, asset, style profile, the 136
  mechanism contract and the data contract. A trader edits it; no code change
  is needed for a new wind farm or a new style profile.
* ``data/d1_demo.csv`` is a 96-point, five-scenario D-1 wind and price set.
* ``data/t1_demo.csv`` is the T+1 actual day-ahead price, real-time price and
  metered output.

What this runner adds on top of the storage pack:

* a declared-quantity quantile across wind scenarios (the 钓鱼法 asymmetry),
* two-settlement energy revenue: day-ahead schedule at the DA price, deviation
  at the real-time price,
* 136 mechanism cash flow as a CfD on a share of actual generation, priced
  against the project capture price (a grade-D approximation of the settlement
  reference),
* a seven-line actual-vs-plan bridge so quantity, price, mechanism, assessment
  and cost effects stay separable.

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
REPO_ROOT = HERE.parents[3]
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


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    grade = _text(block, "grade", f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report["provenance"].append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block


def validate_instance(config):
    """Validate the six blocks and return a provenance and check report."""
    report = {"ok": True, "provenance": [], "checks": [], "warnings": []}
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    contracts = _need(config, "contracts", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot", report)
    _rule_block(rules, "settlement", report)
    mechanism = _rule_block(rules, "mechanism", report)
    fishing = _rule_block(rules, "fishing", report)
    capacity = _rule_block(rules, "capacity_compensation", report)

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = int(_number(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1))
    if points != 96 or abs(mtu - 15.0) > 1e-9:
        raise ConfigError("Gansu spot is 96 points per day at a 15-minute unit")
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
    expected_band = (40.0, 500.0, 40.0, 650.0)
    if any(abs(value - expected) > 1e-9 for value, expected in zip(
        (declare_floor, declare_cap, clear_floor, clear_cap), expected_band
    )):
        raise ConfigError(
            "V3.2 band must be declare 40-500 / clear 40-650 CNY/MWh; "
            "0-1000 is the pre-2026 band and must not be used here"
        )
    if not (clear_floor <= declare_floor < declare_cap <= clear_cap):
        raise ConfigError(
            "price bounds must satisfy clear_floor <= declare_floor < declare_cap <= clear_cap"
        )

    batches = _need(mechanism, "batches_cny_per_mwh", "rules.mechanism")
    expected_batches = {
        "existing_stock": 307.8,
        "batch_2026": 195.4,
        "wind_2027h1": 244.0,
        "solar_2027h1": 244.7,
    }
    for key, expected in expected_batches.items():
        value = _number(
            _need(batches, key, "rules.mechanism.batches_cny_per_mwh"),
            f"rules.mechanism.batches_cny_per_mwh.{key}",
        )
        if abs(value - expected) > 1e-9:
            raise ConfigError(
                f"rules.mechanism.batches_cny_per_mwh.{key} must be {expected:g} "
                "(0.3078 / 0.1954 / 0.2440 / 0.2447 CNY/kWh converted to CNY/MWh)"
            )

    if not isinstance(contracts, list) or len(contracts) != 1:
        raise ConfigError("contracts must hold exactly one 136 mechanism CfD")
    contract = contracts[0]
    _text(contract, "id", "contracts[0]")
    if contract.get("type") != "mechanism_cfd":
        raise ConfigError("contracts[0].type must be mechanism_cfd")
    contract_price = _number(
        _need(contract, "price_cny_per_mwh", "contracts[0]"),
        "contracts[0].price_cny_per_mwh",
        0.0,
    )
    if abs(contract_price - expected_batches["wind_2027h1"]) > 1e-9:
        raise ConfigError(
            "contracts[0].price_cny_per_mwh must equal the 2027H1 wind mechanism price 244.0"
        )
    ratio = _number(_need(contract, "ratio", "contracts[0]"), "contracts[0].ratio", 0.0, 1.0)
    if ratio <= 0.0:
        raise ConfigError("contracts[0].ratio must be positive")
    if contract.get("quantity_basis") != "actual_generation_ratio":
        raise ConfigError("contracts[0].quantity_basis must be actual_generation_ratio")
    if contract.get("reference_price_basis") != "project_capture_price":
        raise ConfigError("contracts[0].reference_price_basis must be project_capture_price")
    _text(contract, "grade", "contracts[0]")
    _text(contract, "source", "contracts[0]")

    threshold = _number(
        _need(fishing, "completion_threshold_ratio", "rules.fishing"),
        "rules.fishing.completion_threshold_ratio",
        0.0,
        1.0,
    )
    fishing_price = _number(
        _need(fishing, "assessment_cny_per_mwh", "rules.fishing"),
        "rules.fishing.assessment_cny_per_mwh",
        0.0,
    )
    if abs(threshold - 0.95) > 1e-9 or abs(fishing_price - 30.0) > 1e-9:
        raise ConfigError(
            "the bundled D-level 钓鱼法 is a 95% completion threshold at 30 CNY/MWh"
        )

    if capacity.get("applicable_to_wind") is not False:
        raise ConfigError(
            "wind farms do not receive the 330 CNY/kW-year reliable capacity payment"
        )
    _number(
        _need(capacity, "price_cny_per_kw_year", "rules.capacity_compensation"),
        "rules.capacity_compensation.price_cny_per_kw_year",
        0.0,
    )

    if asset.get("type") != "wind":
        raise ConfigError("asset.type must be wind for this pack")
    power = _number(_need(asset, "power_mw", "asset"), "asset.power_mw", 1e-9)
    opex = _number(_need(asset, "opex_cny_per_mwh", "asset"), "asset.opex_cny_per_mwh", 0.0)
    fixed = _number(asset.get("fixed_cost_cny_per_day", 0.0), "asset.fixed_cost_cny_per_day", 0.0)
    grid = _need(asset, "grid_connection", "asset")
    export_limit = _number(
        _need(grid, "export_limit_mw", "asset.grid_connection"),
        "asset.grid_connection.export_limit_mw",
        0.0,
    )
    _number(
        _need(grid, "import_limit_mw", "asset.grid_connection"),
        "asset.grid_connection.import_limit_mw",
        0.0,
    )
    if export_limit > power + 1e-9:
        raise ConfigError("asset.grid_connection.export_limit_mw must not exceed asset.power_mw")

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    bid_price = _number(
        _need(policy, "bid_price_cny_per_mwh", "policy"), "policy.bid_price_cny_per_mwh", 0.0
    )
    if abs(bid_price - declare_floor) > 1e-9:
        raise ConfigError(
            "policy.bid_price_cny_per_mwh must equal the declaration floor for this floor-bid profile"
        )
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
    confidence = _number(
        _need(policy, "cvar_confidence", "policy"), "policy.cvar_confidence", 0.0, 1.0
    )
    if not 0.0 < confidence < 1.0:
        raise ConfigError("policy.cvar_confidence must lie in (0, 1)")

    d1 = _need(data_contract, "d1", "data_contract")
    _text(d1, "file", "data_contract.d1")
    required = _need(d1, "required_fields", "data_contract.d1")
    if not isinstance(required, list) or len(required) == 0:
        raise ConfigError("data_contract.d1.required_fields must be a non-empty list")
    wind_fields = _need(d1, "wind_fields", "data_contract.d1")
    price_fields = _need(d1, "price_fields", "data_contract.d1")
    if not isinstance(wind_fields, list) or len(wind_fields) < 2:
        raise ConfigError("data_contract.d1.wind_fields needs at least two scenarios")
    if not isinstance(price_fields, list) or len(price_fields) != len(wind_fields):
        raise ConfigError("data_contract.d1.price_fields must match wind_fields in length")
    for field in list(wind_fields) + list(price_fields) + ["forecast_mw"]:
        if field not in required:
            raise ConfigError(f"data_contract.d1.required_fields is missing {field}")
    weights = d1.get("scenario_weights", [1.0 / len(wind_fields)] * len(wind_fields))
    if len(weights) != len(wind_fields):
        raise ConfigError("data_contract.d1.scenario_weights must match wind_fields")
    parsed_weights = [_number(value, "data_contract.d1.scenario_weights", 0.0) for value in weights]
    if abs(sum(parsed_weights) - 1.0) > 1e-9:
        raise ConfigError("data_contract.d1.scenario_weights must sum to 1")
    t1 = _need(data_contract, "t1", "data_contract")
    _text(t1, "file", "data_contract.t1")
    t1_required = _need(t1, "required_fields", "data_contract.t1")
    if not isinstance(t1_required, list) or len(t1_required) == 0:
        raise ConfigError("data_contract.t1.required_fields must be a non-empty list")

    report["checks"].append(
        {
            "points_per_day": points,
            "market_time_unit_min": mtu,
            "declare_band": [declare_floor, declare_cap],
            "clear_band": [clear_floor, clear_cap],
            "mechanism_price_cny_per_mwh": contract_price,
            "mechanism_ratio": ratio,
            "fishing_threshold": threshold,
            "fishing_price_cny_per_mwh": fishing_price,
            "bid_price_cny_per_mwh": bid_price,
            "wind_scenarios": len(wind_fields),
            "price_scenarios": len(price_fields),
        }
    )
    report["warnings"].append(
        "机制电量比例 30% 与「项目捕获价」参考口径均为 D 级假设；甘肃实际参考价与机制电量分配以结算账单和省级细则为准"
    )
    report["warnings"].append(
        "钓鱼法公开口径为分钟级完成率监测、回收未完成计划并增配；95% 门槛与 30 元/MWh 考核单价为 D 级简化，不得用于结算"
    )
    report["warnings"].append(
        "风电场不享受 330 元/kW·年可靠容量补偿（该政策限公用煤电与电网侧独立储能），本包容量收入为 0"
    )
    report["warnings"].append(
        "中长期 24 时段曲线、D+2 日滚动、省间外送与辅助服务未纳入；本包只做省内现货电能量 + 机制差价"
    )
    report["predicates"] = {
        "bid_price": bid_price,
        "declared_quantity_quantile": qty_q,
        "price_reference_quantile": price_q,
        "cvar_confidence": confidence,
        "mechanism_price": contract_price,
        "mechanism_ratio": ratio,
        "fishing_threshold": threshold,
        "fishing_price": fishing_price,
        "opex": opex,
        "fixed": fixed,
        "power": power,
        "export_limit": export_limit,
    }
    report["points_per_day"] = points
    report["mtu_min"] = mtu
    report["bounds"] = {
        "declare_floor": declare_floor,
        "declare_cap": declare_cap,
        "clear_floor": clear_floor,
        "clear_cap": clear_cap,
    }
    report["scenario_weights"] = parsed_weights
    report["wind_fields"] = list(wind_fields)
    report["price_fields"] = list(price_fields)
    return report


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
    n = report["points_per_day"]
    power = report["predicates"]["power"]

    forecast = []
    for slot in range(n):
        value = _number(by_slot[slot]["forecast_mw"], f"{path.name}:forecast_mw@slot{slot}", 0.0)
        if value > power + 1e-6:
            raise ConfigError(f"{path.name}:forecast_mw@slot{slot}={value} exceeds asset.power_mw")
        forecast.append(value)

    wind = []
    for field in report["wind_fields"]:
        series = []
        for slot in range(n):
            value = _number(by_slot[slot][field], f"{path.name}:{field}@slot{slot}", 0.0)
            if value > power + 1e-6:
                raise ConfigError(
                    f"{path.name}:{field}@slot{slot}={value} exceeds asset.power_mw"
                )
            series.append(value)
        wind.append(series)

    prices = []
    for field in report["price_fields"]:
        series = []
        for slot in range(n):
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

    return {
        "date": rows[0]["date"],
        "slots": list(range(n)),
        "forecast": forecast,
        "wind": wind,
        "prices": prices,
        "start": {slot: by_slot[slot]["start"] for slot in by_slot},
        "end": {slot: by_slot[slot]["end"] for slot in by_slot},
    }


def read_t1(path, config, report):
    rows = _read_rows(path)
    t1 = config["data_contract"]["t1"]
    _check_shape(rows, t1["required_fields"], report["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    n = report["points_per_day"]
    power = report["predicates"]["power"]
    da_price = []
    rt_price = []
    output = []
    for slot in range(n):
        row = by_slot[slot]
        da = _number(row["actual_da_price"], f"{path.name}:actual_da_price@slot{slot}")
        rt = _number(row["actual_rt_price"], f"{path.name}:actual_rt_price@slot{slot}")
        for label, price in (("actual_da_price", da), ("actual_rt_price", rt)):
            if not (
                report["bounds"]["clear_floor"] - 0.01
                <= price
                <= report["bounds"]["clear_cap"] + 0.01
            ):
                raise ConfigError(
                    f"{path.name}:{label}@slot{slot}={price} is outside the clearing band"
                )
        mw = _number(row["actual_output_mw"], f"{path.name}:actual_output_mw@slot{slot}", 0.0)
        if mw > power + 1e-6:
            raise ConfigError(f"{path.name}:actual_output_mw@slot{slot}={mw} exceeds asset.power_mw")
        da_price.append(da)
        rt_price.append(rt)
        output.append(mw)
    return {
        "date": rows[0]["date"],
        "da_price": da_price,
        "rt_price": rt_price,
        "output_mw": output,
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


def build_schedule(d1, config, report):
    """Declare a conservative quantile of the wind scenarios, rounded down to 0.1 MW."""
    n = report["points_per_day"]
    q = report["predicates"]["declared_quantity_quantile"]
    cap = min(report["predicates"]["power"], report["predicates"]["export_limit"])
    scenarios = len(d1["wind"])
    declared = []
    for slot in range(n):
        value = quantile([d1["wind"][s][slot] for s in range(scenarios)], q)
        value = min(cap, max(0.0, value))
        value = math.floor(value * 10 + 1e-9) / 10.0
        declared.append(value)
    dt_h = report["mtu_min"] / 60.0
    forecast_energy = sum(d1["forecast"]) * dt_h
    declared_energy = sum(declared) * dt_h
    if declared_energy > forecast_energy + 1e-6:
        report["warnings"].append(
            "申报电量高于中心预测：申报分位高于中位数或预测曲线本身偏低，请核对风功率情景"
        )
    return {
        "declared": declared,
        "forecast_energy_mwh": forecast_energy,
        "declared_energy_mwh": declared_energy,
        "declared_to_forecast": declared_energy / forecast_energy if forecast_energy > 0 else None,
    }


def evaluate_plan(d1, schedule, config, report):
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    weights = report["scenario_weights"]
    pred = report["predicates"]
    mech_price = pred["mechanism_price"]
    ratio = pred["mechanism_ratio"]
    opex = pred["opex"]
    fixed = pred["fixed"]
    energy = schedule["declared_energy_mwh"]
    declared = schedule["declared"]

    outcomes = []
    for index, prices in enumerate(d1["prices"]):
        spot = sum(declared[t] * prices[t] for t in range(n)) * dt_h
        mechanism = ratio * (mech_price * energy - spot)
        cost = opex * energy + fixed
        net = spot + mechanism - cost
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "mean_price_cny_per_mwh": sum(prices) / n,
                "spot_cny": spot,
                "mechanism_cny": mechanism,
                "opex_cny": opex * energy,
                "fixed_cny": fixed,
                "net_margin_cny": net,
            }
        )
    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    alpha = 1.0 - pred["cvar_confidence"]
    cvar = desk.weighted_cvar(
        [(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=alpha
    )
    reference = [
        quantile([d1["prices"][s][t] for s in range(len(d1["prices"]))], pred["price_reference_quantile"])
        for t in range(n)
    ]
    reference_spot = sum(declared[t] * reference[t] for t in range(n)) * dt_h
    reference_mechanism = ratio * (mech_price * energy - reference_spot)
    reference_cost = opex * energy + fixed
    reference_net = reference_spot + reference_mechanism - reference_cost
    return {
        "outcomes": outcomes,
        "expected_net_margin_cny": expected,
        "cvar_cny": cvar,
        "cvar_confidence": pred["cvar_confidence"],
        "reference_prices": reference,
        "reference_spot_cny": reference_spot,
        "reference_mechanism_cny": reference_mechanism,
        "reference_opex_cny": opex * energy,
        "reference_fixed_cny": fixed,
        "reference_net_margin_cny": reference_net,
        "reference_capture_cny_per_mwh": reference_spot / energy if energy > 0 else None,
        "reference_mechanism_energy_mwh": ratio * energy,
    }


def fishing_assessment(declared, output, config, report):
    """D-level 钓鱼法 screen: per-slot completion below the threshold is assessed."""
    dt_h = report["mtu_min"] / 60.0
    threshold = report["predicates"]["fishing_threshold"]
    price = report["predicates"]["fishing_price"]
    shortfall_mwh = 0.0
    slots_below = 0
    absolute_deviation_mwh = 0.0
    for t, plan in enumerate(declared):
        actual = output[t]
        if plan > 1e-9 and actual < threshold * plan - 1e-9:
            shortfall_mwh += (threshold * plan - actual) * dt_h
            slots_below += 1
        absolute_deviation_mwh += abs(actual - plan) * dt_h
    declared_energy = sum(declared) * dt_h
    actual_energy = sum(output) * dt_h
    return {
        "threshold_ratio": threshold,
        "price_cny_per_mwh": price,
        "shortfall_mwh": shortfall_mwh,
        "slots_below_threshold": slots_below,
        "assessment_cny": shortfall_mwh * price,
        "declared_energy_mwh": declared_energy,
        "actual_energy_mwh": actual_energy,
        "daily_completion_ratio": actual_energy / declared_energy if declared_energy > 0 else None,
        "declaration_accuracy": (
            1.0 - absolute_deviation_mwh / actual_energy if actual_energy > 0 else None
        ),
    }


def settle_actual(t1, schedule, config, report, fishing):
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    pred = report["predicates"]
    declared = schedule["declared"]
    output = t1["output_mw"]
    energy = sum(output) * dt_h
    if energy <= 0:
        raise ConfigError("actual output is zero; the capture price is undefined")
    spot = sum(
        declared[t] * t1["da_price"][t] + (output[t] - declared[t]) * t1["rt_price"][t]
        for t in range(n)
    ) * dt_h
    capture = spot / energy
    mechanism = pred["mechanism_ratio"] * (pred["mechanism_price"] * energy - spot)
    opex = pred["opex"] * energy
    fixed = pred["fixed"]
    net = spot + mechanism - fishing["assessment_cny"] - opex - fixed
    return {
        "spot_cny": spot,
        "capture_cny_per_mwh": capture,
        "mechanism_cny": mechanism,
        "mechanism_energy_mwh": pred["mechanism_ratio"] * energy,
        "assessment_cny": fishing["assessment_cny"],
        "opex_cny": opex,
        "fixed_cny": fixed,
        "net_margin_cny": net,
        "energy_mwh": energy,
        "da_energy_weighted_price_cny_per_mwh": sum(
            declared[t] * t1["da_price"][t] for t in range(n)
        )
        / sum(declared)
        if sum(declared) > 0
        else None,
        "rt_energy_weighted_price_cny_per_mwh": sum(
            output[t] * t1["rt_price"][t] for t in range(n)
        )
        / sum(output)
        if sum(output) > 0
        else None,
    }


def build_bridge(plan, actual, t1, schedule, config, report, fishing):
    """Seven buckets that sum to actual minus plan with a zero identity gap."""
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    pred = report["predicates"]
    declared = schedule["declared"]
    output = t1["output_mw"]
    reference = plan["reference_prices"]
    da = t1["da_price"]
    rt = t1["rt_price"]
    ratio = pred["mechanism_ratio"]
    mech_price = pred["mechanism_price"]
    opex = pred["opex"]
    delta_energy = actual["energy_mwh"] - schedule["declared_energy_mwh"]
    delta_spot = actual["spot_cny"] - plan["reference_spot_cny"]

    buckets = [
        {
            "item": "日前价格偏差",
            "category": "价格",
            "owner": "交易",
            "amount": sum(declared[t] * (da[t] - reference[t]) for t in range(n)) * dt_h,
        },
        {
            "item": "电能量量差",
            "category": "电量",
            "owner": "预测/执行",
            "amount": sum((output[t] - declared[t]) * da[t] for t in range(n)) * dt_h,
        },
        {
            "item": "偏差价差",
            "category": "价格",
            "owner": "市场",
            "amount": sum((output[t] - declared[t]) * (rt[t] - da[t]) for t in range(n)) * dt_h,
        },
        {
            "item": "机制电量量差",
            "category": "机制",
            "owner": "机制结算",
            "amount": ratio * mech_price * delta_energy,
        },
        {
            "item": "机制收入让渡",
            "category": "机制",
            "owner": "机制结算",
            "amount": -ratio * delta_spot,
        },
        {
            "item": "钓鱼法考核",
            "category": "考核",
            "owner": "调度/交易",
            "amount": -fishing["assessment_cny"],
        },
        {
            "item": "运营成本偏差",
            "category": "成本",
            "owner": "财务",
            "amount": -opex * delta_energy,
        },
    ]
    plan_profit = plan["reference_net_margin_cny"]
    actual_profit = actual["net_margin_cny"]
    total = sum(item["amount"] for item in buckets)
    return {
        "plan_profit": plan_profit,
        "actual_profit": actual_profit,
        "delta": actual_profit - plan_profit,
        "identity_gap": actual_profit - plan_profit - total,
        "plan_spot": plan["reference_spot_cny"],
        "actual_spot": actual["spot_cny"],
        "plan_mechanism": plan["reference_mechanism_cny"],
        "actual_mechanism": actual["mechanism_cny"],
        "plan_energy_mwh": schedule["declared_energy_mwh"],
        "actual_energy_mwh": actual["energy_mwh"],
        "buckets": buckets,
    }


def build_bridge_detail(t1, schedule, config, report):
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    declared = schedule["declared"]
    detail = []
    for slot in range(n):
        gap = t1["output_mw"][slot] - declared[slot]
        detail.append(
            {
                "slot": slot,
                "start": _slot_time(slot, report["mtu_min"]),
                "declared_mw": declared[slot],
                "actual_mw": t1["output_mw"][slot],
                "completion_ratio": (
                    t1["output_mw"][slot] / declared[slot] if declared[slot] > 1e-9 else None
                ),
                "quantity_effect_cny": gap * t1["da_price"][slot] * dt_h,
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


def _pct(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def _signed(value):
    return 0.0 if abs(value) < 0.5 else value


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, float):
        if field in ("forecast_mw", "declared_mw", "actual_mw"):
            return f"{value:.1f}"
        if field in ("bid_price_cny_per_mwh", "completion_threshold_mw"):
            return f"{value:.2f}"
        if field in ("completion_ratio",):
            return f"{value:.4f}"
        if field in ("amount", "quantity_effect_cny"):
            return f"{_signed(value):.2f}"
        return f"{value:.6f}"
    return value


def write_review(path, config, report, d1, schedule, plan, t1, actual, fishing, bridge, bridge_detail, fingerprint):
    pred = report["predicates"]
    asset = config["asset"]
    dt_h = report["mtu_min"] / 60.0
    lines = [
        f"# 甘肃风电复核表：{config['meta']['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']:g} 分钟）",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格档：`{config['policy']['profile_id']}` / 指纹 `{fingerprint}`",
        f"- 资产：{asset['power_mw']:.0f} MW 风电，出口限额 {asset['grid_connection']['export_limit_mw']:.0f} MW；"
        f"变动运维 {asset['opex_cny_per_mwh']:.0f} 元/MWh，固定成本 {asset['fixed_cost_cny_per_day']:,.0f} 元/日",
        f"- 机制：2027H1 风电机制电价 {pred['mechanism_price']:.1f} 元/MWh（0.2440 元/kWh），"
        f"机制电量比例 {_pct(pred['mechanism_ratio'])}（D 级假设），参考价 = 项目捕获价（D 级近似）",
        "",
        "## 1. 规则来源与未核实项",
        "",
        "| 规则块 | 级别 | 来源 |",
        "|---|---|---|",
    ]
    for item in report["provenance"]:
        lines.append(f"| {item['block']} | {item['grade']} | {item['source']} |")
    lines += [
        "",
        "## 2. 申报摘要",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 预测电量 | {schedule['forecast_energy_mwh']:.1f} MWh |",
        f"| 申报电量（q={pred['declared_quantity_quantile']:.2f}） | {schedule['declared_energy_mwh']:.1f} MWh |",
        f"| 申报 / 预测 | {_pct(schedule['declared_to_forecast'])} |",
        f"| 申报价 | {pred['bid_price']:.1f} 元/MWh（贴申报下限） |",
        f"| 参考价（q={pred['price_reference_quantile']:.2f}）捕获价 | "
        f"{_money(plan['reference_capture_cny_per_mwh'])} 元/MWh |",
        f"| 计划机制电量（{_pct(pred['mechanism_ratio'])} × 申报） | "
        f"{plan['reference_mechanism_energy_mwh']:.1f} MWh |",
        f"| 计划（参考价）现货收入 | {_money(plan['reference_spot_cny'])} CNY |",
        f"| 计划（参考价）机制差价 | {_money(plan['reference_mechanism_cny'])} CNY |",
        f"| 计划（参考价）运营成本 | {_money(plan['reference_opex_cny'] + plan['reference_fixed_cny'])} CNY |",
        f"| 计划（参考价）净收益 | {_money(plan['reference_net_margin_cny'])} CNY |",
        f"| 情景期望净收益 | {_money(plan['expected_net_margin_cny'])} CNY |",
        f"| CVaR（置信 {_pct(pred['cvar_confidence'])}） | {_money(plan['cvar_cny'])} CNY |",
        "",
        "## 3. 价格情景（96 点，逐点乘申报曲线）",
        "",
        "| 情景 | 权重 | 均价 | 现货收入 | 机制差价 | 运营成本 | 净收益 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in plan["outcomes"]:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['mean_price_cny_per_mwh']:.1f} | "
            f"{item['spot_cny']:,.0f} | {item['mechanism_cny']:,.0f} | "
            f"{item['opex_cny'] + item['fixed_cny']:,.0f} | {item['net_margin_cny']:,.0f} |"
        )
    lines += [
        "",
        f"> 读法：机制把 {_pct(pred['mechanism_ratio'])} 的现货收入换成 "
        f"{pred['mechanism_price']:.0f} 元/MWh 的机制收入。参考捕获价高于机制价时机制差价为负"
        "（项目向机制退还差价），低于机制价时为正（机制补差）；本演示为负，"
        "说明该风况下现货捕获价高于机制价。CVaR 为最差概率质量的平均，不是单日最大亏损。",
    ]
    if bridge is None:
        lines += ["", "## 4. T+1 实际", "", "未提供 T+1 实际数据，本次只出申报表。"]
    else:
        lines += [
            "",
            "## 4. T+1 实际结算",
            "",
            "| 项目 | 值 |",
            "|---|---:|",
            f"| 实际发电量 | {actual['energy_mwh']:.1f} MWh |",
            f"| 日完成率（实际 / 申报） | {_pct(fishing['daily_completion_ratio'])} |",
            f"| 申报准确率（1 − 平均绝对偏差率） | {_pct(fishing['declaration_accuracy'])} |",
            f"| 低于 {_pct(fishing['threshold_ratio'])} 门槛的时段 | {fishing['slots_below_threshold']} 个 |",
            f"| 钓鱼法考核电量缺口 | {fishing['shortfall_mwh']:.1f} MWh |",
            f"| 钓鱼法考核（D 级） | {_money(actual['assessment_cny'])} CNY |",
            f"| 日前电量加权价 | {_money(actual['da_energy_weighted_price_cny_per_mwh'])} 元/MWh |",
            f"| 实时价格指数（按实际出力加权，仅作参考） | "
            f"{_money(actual['rt_energy_weighted_price_cny_per_mwh'])} 元/MWh |",
            f"| 实际捕获价（现货收入 / 实际电量） | {_money(actual['capture_cny_per_mwh'])} 元/MWh |",
            f"| 现货收入（日前 + 实时偏差） | {_money(actual['spot_cny'])} CNY |",
            f"| 机制差价（{_pct(pred['mechanism_ratio'])} × 实际电量） | {_money(actual['mechanism_cny'])} CNY |",
            f"| 运营成本 | {_money(actual['opex_cny'] + actual['fixed_cny'])} CNY |",
            f"| 实际净收益 | {_money(actual['net_margin_cny'])} CNY |",
        ]
        lines += [
            "",
            "> 读法：日完成率超过 100% 不等于没有钓鱼法考核。考核按**时段**监测，"
            "个别时段低于门槛即进入考核；本演示的考核金额远小于高价时段少发电量的收入损失，"
            "真正的代价是「少发的恰是高价时段」，不是考核单价本身。",
        ]
        ordered = sorted(bridge["buckets"], key=lambda item: abs(item["amount"]), reverse=True)
        lines += [
            "",
            "## 5. T+1 差异桥",
            "",
            f"计划（参考价）净收益 {bridge['plan_profit']:,.0f} CNY，实际净收益 "
            f"{bridge['actual_profit']:,.0f} CNY，差异 {bridge['delta']:,.0f} CNY，"
            f"残差 {bridge['identity_gap']:.2e}。",
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
            f"**最大差异科目**：{top['item'] if top else '—'}，{top['amount']:,.0f} CNY。" if top else "**最大差异科目**：—",
            "",
        ]
        if bridge_detail:
            lines += [
                "**量偏差最大的 5 个时段**：",
                "",
                "| 时段 | 申报 | 实际 | 完成率 | 量影响（CNY） |",
                "|---|---:|---:|---:|---:|",
            ]
            for item in bridge_detail:
                lines.append(
                    f"| {item['start']} | {item['declared_mw']:.1f} | {item['actual_mw']:.1f} | "
                    f"{_pct(item['completion_ratio'])} | {_signed(item['quantity_effect_cny']):,.0f} |"
                )
    lines += [
        "",
        "## 6. 三个复核问题",
        "",
        "1. 最大差异科目归因到风况、日前价格、实时偏差、机制参考价还是考核口径？证据包是否齐全？",
        "2. 申报分位与钓鱼法门槛是否匹配？完成率低于门槛的时段是否集中在高价时段，是否需要单独调整该时段的申报？",
        "3. 机制参考价用项目捕获价是否与结算账单一致？若省级采用新能源加权均价，本表哪些科目需要重算？",
        "",
        "## 7. 下一日动作（人工填写）",
        "",
        "- [ ] ",
        "- [ ] ",
        "- [ ] ",
        "",
        "## 8. 告警与边界",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        f"- {config['meta']['disclaimer']}",
        "- 本表是国内现货价格接受者口径的盘面复核，不是交易中心结算单；实际出清、机制差价与考核以正式结果为准。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, d1_path, t1_path, out_dir):
    """Validate, build the bid sheet, settle T+1, and write the review."""
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{instance_path.name} is not valid JSON: {exc}") from exc
    report = validate_instance(config)
    d1 = read_d1(Path(d1_path), config, report)
    t1 = None
    if t1_path is not None:
        t1 = read_t1(Path(t1_path), config, report)
        if t1["date"] != d1["date"]:
            raise ConfigError("D-1 and T+1 files must refer to the same trading day")

    schedule = build_schedule(d1, config, report)
    plan = evaluate_plan(d1, schedule, config, report)
    actual = None
    fishing = None
    bridge = None
    bridge_detail = None
    if t1 is not None:
        fishing = fishing_assessment(schedule["declared"], t1["output_mw"], config, report)
        actual = settle_actual(t1, schedule, config, report, fishing)
        bridge = build_bridge(plan, actual, t1, schedule, config, report, fishing)
        bridge_detail = build_bridge_detail(t1, schedule, config, report)

    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bid_rows = []
    for slot in range(report["points_per_day"]):
        bid_rows.append(
            {
                "date": d1["date"],
                "slot": slot,
                "start": d1["start"][slot],
                "end": d1["end"][slot],
                "forecast_mw": d1["forecast"][slot],
                "declared_mw": schedule["declared"][slot],
                "bid_price_cny_per_mwh": report["predicates"]["bid_price"],
                "completion_threshold_mw": report["predicates"]["fishing_threshold"]
                * schedule["declared"][slot],
                "note": f"q={report['predicates']['declared_quantity_quantile']:.2f}; floor bid",
            }
        )
    _write_csv(
        out_dir / "bid_sheet.csv",
        bid_rows,
        [
            "date",
            "slot",
            "start",
            "end",
            "forecast_mw",
            "declared_mw",
            "bid_price_cny_per_mwh",
            "completion_threshold_mw",
            "note",
        ],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "plan": {
            "forecast_energy_mwh": schedule["forecast_energy_mwh"],
            "declared_energy_mwh": schedule["declared_energy_mwh"],
            "declared_to_forecast": schedule["declared_to_forecast"],
            "bid_price_cny_per_mwh": report["predicates"]["bid_price"],
            "mechanism_price_cny_per_mwh": report["predicates"]["mechanism_price"],
            "mechanism_ratio": report["predicates"]["mechanism_ratio"],
            "reference_capture_cny_per_mwh": plan["reference_capture_cny_per_mwh"],
            "reference_spot_cny": plan["reference_spot_cny"],
            "reference_mechanism_cny": plan["reference_mechanism_cny"],
            "reference_net_margin_cny": plan["reference_net_margin_cny"],
            "expected_net_margin_cny": plan["expected_net_margin_cny"],
            "cvar_cny": plan["cvar_cny"],
            "cvar_confidence": plan["cvar_confidence"],
            "scenarios": plan["outcomes"],
        },
        "actual": None
        if actual is None
        else {
            "energy_mwh": actual["energy_mwh"],
            "spot_cny": actual["spot_cny"],
            "capture_cny_per_mwh": actual["capture_cny_per_mwh"],
            "mechanism_cny": actual["mechanism_cny"],
            "mechanism_energy_mwh": actual["mechanism_energy_mwh"],
            "assessment_cny": actual["assessment_cny"],
            "opex_cny": actual["opex_cny"],
            "fixed_cny": actual["fixed_cny"],
            "net_margin_cny": actual["net_margin_cny"],
            "fishing": fishing,
        },
        "warnings": report["warnings"],
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
            "plan_spot": bridge["plan_spot"],
            "actual_spot": bridge["actual_spot"],
            "plan_mechanism": bridge["plan_mechanism"],
            "actual_mechanism": bridge["actual_mechanism"],
            "plan_energy_mwh": bridge["plan_energy_mwh"],
            "actual_energy_mwh": bridge["actual_energy_mwh"],
            "buckets": [
                {
                    "item": item["item"],
                    "category": item["category"],
                    "owner": item["owner"],
                    "amount": item["amount"],
                }
                for item in bridge["buckets"]
            ],
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
        schedule,
        plan,
        t1,
        actual,
        fishing,
        bridge,
        bridge_detail,
        fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "schedule": schedule,
        "plan": plan,
        "actual": actual,
        "fishing": fishing,
        "bridge": bridge,
        "bridge_detail": bridge_detail,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gansu wind-farm instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", help="D-1 96-point wind and price scenario CSV")
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
        f"申报：预测 {plan['forecast_energy_mwh']:.1f} MWh，申报 {plan['declared_energy_mwh']:.1f} MWh"
        f"（{plan['declared_to_forecast'] * 100:.1f}%），报价 {plan['bid_price_cny_per_mwh']:.0f} 元/MWh"
    )
    print(
        f"计划：参考捕获价 {plan['reference_capture_cny_per_mwh']:,.0f} 元/MWh，"
        f"净收益 {plan['reference_net_margin_cny']:,.0f} CNY；"
        f"情景期望 {plan['expected_net_margin_cny']:,.0f}，CVaR {plan['cvar_cny']:,.0f}"
    )
    if result["bridge"] is not None:
        fishing = result["fishing"]
        print(
            f"实际：完成率 {fishing['daily_completion_ratio'] * 100:.1f}%，"
            f"低于门槛 {fishing['slots_below_threshold']} 个时段，考核 {fishing['assessment_cny']:,.0f} CNY"
        )
        print(
            f"差异桥：计划 {result['bridge']['plan_profit']:,.0f} → 实际 "
            f"{result['bridge']['actual_profit']:,.0f}，差异 {result['bridge']['delta']:,.0f} CNY，"
            f"残差 {result['bridge']['identity_gap']:.2e}"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
