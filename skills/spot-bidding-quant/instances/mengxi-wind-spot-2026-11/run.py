#!/usr/bin/env python3
"""Run the Mengxi wind-farm spot instance pack.

What this pack adds on top of the Gansu wind pack:

* full-volume real-time settlement: actual output is paid at the real-time
  price, while the day-ahead pre-clear is only a scheduling reference;
* a paired wind/price scenario set (high wind comes with low or negative
  midday prices), so capture price and curtailment are not independent;
* a financial CfD on a share of actual generation, which changes the
  economics of curtailing at negative prices;
* a simplified declaration-deviation assessment outside a ±5% band;
* a six-bucket bridge from the day-ahead reference plan to the actual
  real-time settlement, with a zero identity gap.

All bundled numbers are synthetic grade D. They are not a market forecast,
a live trading signal or investment advice.
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
    """Validate the configuration and return a provenance/check report."""
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
    settlement = _rule_block(rules, "settlement", report)
    new_energy = _rule_block(rules, "new_energy", report)
    negative = _rule_block(rules, "negative_price", report)
    deviation = _rule_block(rules, "deviation_assessment", report)
    contract = _rule_block(rules, "contract", report)
    cost = _rule_block(rules, "cost", report)
    capacity = _rule_block(rules, "capacity_compensation", report)

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = int(_number(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1))
    if points != 96 or abs(mtu - 15.0) > 1e-9:
        raise ConfigError("Mengxi pack is 96 points per day at a 15-minute unit (real-time 5-min is aggregated)")
    floor = _number(_need(spot, "model_floor_cny_per_mwh", "rules.spot"), "rules.spot.model_floor_cny_per_mwh")
    cap = _number(_need(spot, "model_cap_cny_per_mwh", "rules.spot"), "rules.spot.model_cap_cny_per_mwh")
    if not (floor < 0 < cap):
        raise ConfigError("model bounds must straddle zero to allow negative prices")
    observed = _need(spot, "observed_2025", "rules.spot")
    observed_floor = _number(
        _need(observed, "floor_cny_per_mwh", "rules.spot.observed_2025"),
        "rules.spot.observed_2025.floor_cny_per_mwh",
    )
    observed_cap = _number(
        _need(observed, "cap_cny_per_mwh", "rules.spot.observed_2025"),
        "rules.spot.observed_2025.cap_cny_per_mwh",
    )
    if observed_floor < floor - 1e-9 or observed_cap > cap + 1e-9:
        raise ConfigError("model bounds must cover the observed 2025 range")
    early = _need(spot, "early_limit", "rules.spot")
    early_status = _text(early, "status", "rules.spot.early_limit")
    if "不得" not in early_status and "历史" not in early_status:
        raise ConfigError("early_limit.status must state that it is not the current limit")
    draft = _need(spot, "draft_2026", "rules.spot")
    draft_status = _text(draft, "status", "rules.spot.draft_2026")
    if "未生效" not in draft_status and "征求意见" not in draft_status:
        raise ConfigError("draft_2026.status must mark the draft as not effective")
    _text(spot, "current_limit_status", "rules.spot")
    _text(settlement, "basis", "rules.settlement")
    _text(settlement, "granularity", "rules.settlement")
    deviation_band = _number(
        _need(deviation, "band", "rules.deviation_assessment"),
        "rules.deviation_assessment.band",
        0.0,
        1.0,
    )
    deviation_penalty = _number(
        _need(deviation, "penalty_cny_per_mwh", "rules.deviation_assessment"),
        "rules.deviation_assessment.penalty_cny_per_mwh",
        0.0,
    )
    if _text(deviation, "basis", "rules.deviation_assessment") != "available_energy":
        raise ConfigError("deviation assessment must use available energy, before curtailment")

    incremental_after = _text(new_energy, "incremental_after", "rules.new_energy")
    if incremental_after != "2025-06-01":
        raise ConfigError("new_energy.incremental_after must be 2025-06-01")
    mechanism_text = _text(new_energy, "incremental_mechanism", "rules.new_energy")
    if "暂不纳入" not in mechanism_text:
        raise ConfigError("incremental projects must be marked as excluded from the mechanism price")
    stock_price = _number(
        _need(new_energy, "stock_mechanism_cny_per_mwh", "rules.new_energy"),
        "rules.new_energy.stock_mechanism_cny_per_mwh",
    )
    if abs(stock_price - 282.9) > 1e-9:
        raise ConfigError("stock mechanism price must be 282.9 CNY/MWh (0.2829 CNY/kWh)")
    signing_ratio = _number(
        _need(new_energy, "annual_signing_ratio", "rules.new_energy"),
        "rules.new_energy.annual_signing_ratio",
        0.0,
        1.0,
    )

    contract_price = _number(
        _need(contract, "contract_price_cny_per_mwh", "rules.contract"),
        "rules.contract.contract_price_cny_per_mwh",
        0.0,
    )
    contract_ratio = _number(
        _need(contract, "ratio_of_actual_generation", "rules.contract"),
        "rules.contract.ratio_of_actual_generation",
        0.0,
        1.0,
    )
    if abs(contract_ratio - signing_ratio) > 1e-9:
        raise ConfigError("contract ratio must match the annual signing ratio in this v1 pack")
    if not isinstance(contracts, list) or not contracts:
        raise ConfigError("contracts must contain at least one contract")
    first_contract = contracts[0]
    if _text(first_contract, "type", "contracts[0]") != "financial_cfd":
        raise ConfigError("contracts[0].type must be financial_cfd")
    if abs(
        _number(_need(first_contract, "price_cny_per_mwh", "contracts[0]"), "contracts[0].price_cny_per_mwh")
        - contract_price
    ) > 1e-9:
        raise ConfigError("contracts[0].price must match rules.contract")
    if abs(
        _number(
            _need(first_contract, "ratio_of_actual_generation", "contracts[0]"),
            "contracts[0].ratio_of_actual_generation",
        )
        - contract_ratio
    ) > 1e-9:
        raise ConfigError("contracts[0].ratio must match rules.contract")

    opex = _number(_need(cost, "opex_cny_per_mwh", "rules.cost"), "rules.cost.opex_cny_per_mwh", 0.0)
    fixed = _number(_need(cost, "fixed_cost_cny_per_day", "rules.cost"), "rules.cost.fixed_cost_cny_per_day", 0.0)
    if abs(opex - _number(_need(asset, "opex_cny_per_mwh", "asset"), "asset.opex_cny_per_mwh", 0.0)) > 1e-9:
        raise ConfigError("asset.opex must match rules.cost.opex")
    if abs(fixed - _number(_need(asset, "fixed_cost_cny_per_day", "asset"), "asset.fixed_cost_cny_per_day", 0.0)) > 1e-9:
        raise ConfigError("asset.fixed_cost must match rules.cost.fixed_cost")

    power = _number(_need(asset, "power_mw", "asset"), "asset.power_mw", 1.0)
    grid = _need(asset, "grid_connection", "asset")
    export_limit = _number(_need(grid, "export_limit_mw", "asset.grid_connection"), "asset.grid_connection.export_limit_mw", 0.0)
    import_limit = _number(_need(grid, "import_limit_mw", "asset.grid_connection"), "asset.grid_connection.import_limit_mw", 0.0)
    if export_limit > power + 1e-9:
        raise ConfigError("export limit cannot exceed asset power")
    if import_limit != 0.0:
        raise ConfigError("a wind farm in this pack cannot import from the grid")

    cvar_confidence = _number(
        _need(policy, "cvar_confidence", "policy"), "policy.cvar_confidence", 0.0, 1.0
    )
    strategies = _need(policy, "strategies", "policy")
    if not isinstance(strategies, dict) or len(strategies) < 2:
        raise ConfigError("policy.strategies must contain at least two strategies")
    for name, strategy in strategies.items():
        path = f"policy.strategies.{name}"
        _text(strategy, "label", path)
        q = _number(_need(strategy, "declared_quantity_quantile", path), f"{path}.declared_quantity_quantile", 0.0, 1.0)
        bid = _number(_need(strategy, "bid_price_cny_per_mwh", path), f"{path}.bid_price_cny_per_mwh", floor, cap)
        threshold = _number(
            _need(strategy, "curtail_threshold_cny_per_mwh", path),
            f"{path}.curtail_threshold_cny_per_mwh",
            floor,
            cap,
        )
        ratio = _number(_need(strategy, "curtail_ratio", path), f"{path}.curtail_ratio", 0.0, 1.0)
        if q < 0 or q > 1:
            raise ConfigError(f"{path}.declared_quantity_quantile must be 0-1")
        if bid < floor or bid > cap:
            raise ConfigError(f"{path}.bid_price is outside model bounds")
        if threshold < floor or threshold > cap:
            raise ConfigError(f"{path}.curtail_threshold is outside model bounds")
        if ratio < 0 or ratio > 1:
            raise ConfigError(f"{path}.curtail_ratio must be 0-1")

    d1 = _need(data_contract, "d1", "data_contract")
    t1 = _need(data_contract, "t1", "data_contract")
    wind_fields = _need(d1, "wind_fields", "data_contract.d1")
    price_fields = _need(d1, "price_fields", "data_contract.d1")
    weights = _need(d1, "scenario_weights", "data_contract.d1")
    if len(wind_fields) != 5 or len(price_fields) != 5 or len(weights) != 5:
        raise ConfigError("this pack expects exactly five wind and five price scenarios")
    if abs(sum(float(weight) for weight in weights) - 1.0) > 1e-9:
        raise ConfigError("scenario weights must sum to 1")
    for field in list(wind_fields) + list(price_fields) + ["forecast_mw", "da_price", "date", "slot", "start", "end"]:
        if field not in d1["required_fields"]:
            raise ConfigError(f"data_contract.d1.required_fields is missing {field}")
    for field in t1["required_fields"]:
        if field not in ("date", "slot", "actual_da_price", "actual_rt_price", "actual_available_mw", "actual_output_mw", "actual_curtail_mw"):
            raise ConfigError(f"data_contract.t1 has an unexpected field: {field}")
    if "actual_curtail_mw" not in t1["required_fields"]:
        raise ConfigError("data_contract.t1 must declare actual_curtail_mw")

    report["predicates"] = {
        "points_per_day": points,
        "mtu_min": mtu,
        "power": power,
        "export_limit": export_limit,
        "opex": opex,
        "fixed": fixed,
        "contract_price": contract_price,
        "contract_ratio": contract_ratio,
        "cvar_confidence": cvar_confidence,
        "scenario_weights": [float(weight) for weight in weights],
        "wind_fields": list(wind_fields),
        "price_fields": list(price_fields),
        "model_floor": floor,
        "model_cap": cap,
        "deviation_band": deviation_band,
        "deviation_penalty": deviation_penalty,
    }
    report["warnings"].extend(
        [
            "日前为预出清，本包只把它当调度参考，实际按实时全电量结算；若正式规则为日前+偏差两结算，请改用两结算对照口径",
            "实时 5 分钟出清在本包聚合为 96 点 15 分钟，不模拟 5 分钟内滚动决策",
            "蒙西限价有三套口径：早期 40-550/600（B）、2025 实绩 -48.66~1555.85（B）、2026 征求意见 -50~1500（C，未生效）；本包模型边界只覆盖实绩，不代表现行限价",
            "2025-06-01 后并网增量项目暂不纳入机制电价，无保底价；0.2829 元/kWh 只适用于存量项目",
            "CfD 280 元/MWh、60% 比例与捕获价参考均为 D 级假设，不是真实合同条款",
            "负价弃风会同时减少电量和按实际电量计价的 CfD 对冲，是否弃风要看边际损益，不能只看负价本身",
            "±5% 免考核带来自现货 101 问-B；30 元/MWh 的申报偏差考核为 D 级简化，正式考核公式待核",
        ]
    )
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
    d1_contract = config["data_contract"]["d1"]
    _check_shape(rows, d1_contract["required_fields"], report["predicates"]["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    n = report["predicates"]["points_per_day"]
    power = report["predicates"]["power"]
    bounds = (report["predicates"]["model_floor"], report["predicates"]["model_cap"])

    forecast = []
    for slot in range(n):
        value = _number(by_slot[slot]["forecast_mw"], f"{path.name}:forecast_mw@slot{slot}", 0.0)
        if value > power + 1e-6:
            raise ConfigError(f"{path.name}:forecast_mw@slot{slot}={value} exceeds asset.power_mw")
        forecast.append(value)

    wind = []
    for field in report["predicates"]["wind_fields"]:
        series = []
        for slot in range(n):
            value = _number(by_slot[slot][field], f"{path.name}:{field}@slot{slot}", 0.0)
            if value > power + 1e-6:
                raise ConfigError(f"{path.name}:{field}@slot{slot}={value} exceeds asset.power_mw")
            series.append(value)
        wind.append(series)

    prices = []
    for field in report["predicates"]["price_fields"]:
        series = []
        for slot in range(n):
            price = _number(by_slot[slot][field], f"{path.name}:{field}@slot{slot}")
            if not (bounds[0] - 0.01 <= price <= bounds[1] + 0.01):
                raise ConfigError(
                    f"{path.name}:{field}@slot{slot}={price} is outside the model bounds; "
                    "this is a model guard, not the formal market limit"
                )
            series.append(price)
        prices.append(series)

    da_price = []
    for slot in range(n):
        price = _number(by_slot[slot]["da_price"], f"{path.name}:da_price@slot{slot}")
        if not (bounds[0] - 0.01 <= price <= bounds[1] + 0.01):
            raise ConfigError(f"{path.name}:da_price@slot{slot}={price} is outside the model bounds")
        da_price.append(price)

    return {
        "date": rows[0]["date"],
        "slots": list(range(n)),
        "forecast": forecast,
        "wind": wind,
        "prices": prices,
        "da_price": da_price,
        "start": {slot: by_slot[slot]["start"] for slot in by_slot},
        "end": {slot: by_slot[slot]["end"] for slot in by_slot},
    }


def read_t1(path, config, report):
    rows = _read_rows(path)
    t1_contract = config["data_contract"]["t1"]
    _check_shape(rows, t1_contract["required_fields"], report["predicates"]["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    n = report["predicates"]["points_per_day"]
    power = report["predicates"]["power"]
    bounds = (report["predicates"]["model_floor"], report["predicates"]["model_cap"])
    da_price, rt_price, available, output, curtail = [], [], [], [], []
    for slot in range(n):
        row = by_slot[slot]
        da = _number(row["actual_da_price"], f"{path.name}:actual_da_price@slot{slot}")
        rt = _number(row["actual_rt_price"], f"{path.name}:actual_rt_price@slot{slot}")
        for label, price in (("actual_da_price", da), ("actual_rt_price", rt)):
            if not (bounds[0] - 0.01 <= price <= bounds[1] + 0.01):
                raise ConfigError(f"{path.name}:{label}@slot{slot}={price} is outside the model bounds")
        available_mw = _number(row["actual_available_mw"], f"{path.name}:actual_available_mw@slot{slot}", 0.0)
        output_mw = _number(row["actual_output_mw"], f"{path.name}:actual_output_mw@slot{slot}", 0.0)
        curtail_mw = _number(row["actual_curtail_mw"], f"{path.name}:actual_curtail_mw@slot{slot}", 0.0)
        for label, value in (("available", available_mw), ("output", output_mw), ("curtail", curtail_mw)):
            if value > power + 1e-6:
                raise ConfigError(f"{path.name}:{label}@slot{slot}={value} exceeds asset.power_mw")
        if abs(output_mw + curtail_mw - available_mw) > 1e-6:
            raise ConfigError(
                f"{path.name}:slot{slot} must satisfy output + curtail = available "
                f"({output_mw} + {curtail_mw} != {available_mw})"
            )
        da_price.append(da)
        rt_price.append(rt)
        available.append(available_mw)
        output.append(output_mw)
        curtail.append(curtail_mw)
    return {
        "date": rows[0]["date"],
        "da_price": da_price,
        "rt_price": rt_price,
        "available_mw": available,
        "output_mw": output,
        "curtail_mw": curtail,
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


def build_schedule(d1, strategy, report):
    """Declare a quantile of the wind scenarios, rounded down to 0.1 MW."""
    n = report["predicates"]["points_per_day"]
    q = float(strategy["declared_quantity_quantile"])
    cap = min(report["predicates"]["power"], report["predicates"]["export_limit"])
    scenarios = len(d1["wind"])
    declared = []
    for slot in range(n):
        value = quantile([d1["wind"][s][slot] for s in range(scenarios)], q)
        value = min(cap, max(0.0, value))
        value = math.floor(value * 10 + 1e-9) / 10.0
        declared.append(value)
    dt_h = report["predicates"]["mtu_min"] / 60.0
    forecast_energy = sum(d1["forecast"]) * dt_h
    declared_energy = sum(declared) * dt_h
    return {
        "declared": declared,
        "forecast_energy_mwh": forecast_energy,
        "declared_energy_mwh": declared_energy,
        "declared_to_forecast": declared_energy / forecast_energy if forecast_energy > 0 else None,
    }


def _scaled_market(d1, price_multiplier=1.0, wind_multiplier=1.0):
    """Return a shallow copy of the D-1 set with the requested stress applied."""
    if abs(price_multiplier - 1.0) < 1e-12 and abs(wind_multiplier - 1.0) < 1e-12:
        return d1
    return {
        **d1,
        "forecast": [value * wind_multiplier for value in d1["forecast"]],
        "wind": [
            [value * wind_multiplier for value in series]
            for series in d1["wind"]
        ],
        "prices": [
            [value * price_multiplier for value in series]
            for series in d1["prices"]
        ],
    }


def plan_reference(d1, schedule, config, report):
    """Day-ahead reference plan used only for the bridge and the plan row."""
    dt_h = report["predicates"]["mtu_min"] / 60.0
    declared = schedule["declared"]
    declared_energy = schedule["declared_energy_mwh"]
    if declared_energy <= 0:
        raise ConfigError("declared energy is zero; the reference plan is undefined")
    spot = sum(declared[t] * d1["da_price"][t] for t in range(len(declared))) * dt_h
    capture = spot / declared_energy
    cfd = report["predicates"]["contract_ratio"] * declared_energy * (
        report["predicates"]["contract_price"] - capture
    )
    opex = report["predicates"]["opex"] * declared_energy
    fixed = report["predicates"]["fixed"]
    return {
        "declared_energy_mwh": declared_energy,
        "spot_cny": spot,
        "capture_cny_per_mwh": capture,
        "cfd_cny": cfd,
        "opex_cny": opex,
        "fixed_cny": fixed,
        "deviation_penalty_cny": 0.0,
        "net_margin_cny": spot + cfd - opex - fixed,
    }


def evaluate_strategy(d1, strategy, config, report, price_multiplier=1.0, wind_multiplier=1.0, contract_ratio=None, curtail_threshold=None, curtail_ratio=None):
    """Evaluate one strategy over the five paired wind/price scenarios."""
    market = _scaled_market(d1, price_multiplier, wind_multiplier)
    schedule = build_schedule(market, strategy, report)
    plan = plan_reference(market, schedule, config, report)
    n = report["predicates"]["points_per_day"]
    dt_h = report["predicates"]["mtu_min"] / 60.0
    weights = report["predicates"]["scenario_weights"]
    ratio = report["predicates"]["contract_ratio"] if contract_ratio is None else float(contract_ratio)
    threshold = (
        float(strategy["curtail_threshold_cny_per_mwh"])
        if curtail_threshold is None
        else float(curtail_threshold)
    )
    curtail_ratio = (
        float(strategy["curtail_ratio"]) if curtail_ratio is None else float(curtail_ratio)
    )
    contract_price = report["predicates"]["contract_price"]
    opex = report["predicates"]["opex"]
    fixed = report["predicates"]["fixed"]
    band = report["predicates"]["deviation_band"]
    penalty_price = report["predicates"]["deviation_penalty"]
    declared_energy = schedule["declared_energy_mwh"]

    outcomes = []
    for index in range(len(market["wind"])):
        available_energy = 0.0
        curtail_energy = 0.0
        spot = 0.0
        for slot in range(n):
            available = market["wind"][index][slot]
            price = market["prices"][index][slot]
            if price < threshold:
                curtailed = available * curtail_ratio
            else:
                curtailed = 0.0
            actual = available - curtailed
            available_energy += available * dt_h
            curtail_energy += curtailed * dt_h
            spot += actual * price * dt_h
        energy = available_energy - curtail_energy
        if energy <= 0:
            raise ConfigError("scenario energy is zero; capture price is undefined")
        capture = spot / energy
        cfd = ratio * energy * (contract_price - capture)
        opex_cny = opex * energy
        deviation_ratio = (
            abs(available_energy - declared_energy) / declared_energy
            if declared_energy > 0
            else 0.0
        )
        deviation_penalty = max(0.0, deviation_ratio - band) * declared_energy * penalty_price
        net = spot + cfd - opex_cny - fixed - deviation_penalty
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "available_energy_mwh": available_energy,
                "curtail_energy_mwh": curtail_energy,
                "energy_mwh": energy,
                "capture_cny_per_mwh": capture,
                "spot_cny": spot,
                "cfd_cny": cfd,
                "opex_cny": opex_cny,
                "fixed_cny": fixed,
                "deviation_ratio": deviation_ratio,
                "deviation_penalty_cny": deviation_penalty,
                "net_margin_cny": net,
            }
        )

    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    alpha = 1.0 - report["predicates"]["cvar_confidence"]
    cvar = desk.weighted_cvar(
        [(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=alpha
    )
    expected_energy = sum(item["weight"] * item["energy_mwh"] for item in outcomes)
    expected_available = sum(item["weight"] * item["available_energy_mwh"] for item in outcomes)
    expected_curtail = sum(item["weight"] * item["curtail_energy_mwh"] for item in outcomes)
    expected_spot = sum(item["weight"] * item["spot_cny"] for item in outcomes)
    expected_cfd = sum(item["weight"] * item["cfd_cny"] for item in outcomes)
    expected_opex = sum(item["weight"] * item["opex_cny"] for item in outcomes)
    expected_penalty = sum(item["weight"] * item["deviation_penalty_cny"] for item in outcomes)
    return {
        "strategy": strategy,
        "schedule": schedule,
        "plan": plan,
        "outcomes": outcomes,
        "expected_net_margin_cny": expected,
        "cvar_cny": cvar,
        "cvar_confidence": report["predicates"]["cvar_confidence"],
        "expected_energy_mwh": expected_energy,
        "expected_available_energy_mwh": expected_available,
        "expected_curtail_energy_mwh": expected_curtail,
        "expected_capture_cny_per_mwh": expected_spot / expected_energy if expected_energy > 0 else None,
        "expected_spot_cny": expected_spot,
        "expected_cfd_cny": expected_cfd,
        "expected_opex_cny": expected_opex,
        "expected_fixed_cny": report["predicates"]["fixed"],
        "expected_deviation_penalty_cny": expected_penalty,
        "contract_ratio": ratio,
        "curtail_threshold_cny_per_mwh": threshold,
        "curtail_ratio": curtail_ratio,
    }


def settle_actual(t1, d1, schedule, strategy, config, report):
    """Settle the actual day at the real-time price, plus the CfD."""
    n = report["predicates"]["points_per_day"]
    dt_h = report["predicates"]["mtu_min"] / 60.0
    declared = schedule["declared"]
    output = t1["output_mw"]
    available = t1["available_mw"]
    curtail = t1["curtail_mw"]
    rt = t1["rt_price"]
    da = t1["da_price"]
    energy = sum(output) * dt_h
    if energy <= 0:
        raise ConfigError("actual output is zero; the capture price is undefined")
    spot = sum(output[t] * rt[t] for t in range(n)) * dt_h
    capture = spot / energy
    ratio = report["predicates"]["contract_ratio"]
    contract_price = report["predicates"]["contract_price"]
    cfd = ratio * energy * (contract_price - capture)
    opex = report["predicates"]["opex"] * energy
    fixed = report["predicates"]["fixed"]
    band = report["predicates"]["deviation_band"]
    penalty_price = report["predicates"]["deviation_penalty"]
    declared_energy = schedule["declared_energy_mwh"]
    available_energy = sum(available) * dt_h
    deviation_ratio = (
        abs(available_energy - declared_energy) / declared_energy
        if declared_energy > 0
        else 0.0
    )
    deviation_penalty = max(0.0, deviation_ratio - band) * declared_energy * penalty_price
    net = spot + cfd - opex - fixed - deviation_penalty

    two_spot = sum(
        declared[t] * da[t] + (output[t] - declared[t]) * rt[t] for t in range(n)
    ) * dt_h
    two_capture = two_spot / energy
    two_cfd = ratio * energy * (contract_price - two_capture)
    two_net = two_spot + two_cfd - opex - fixed - deviation_penalty

    curtail_energy = sum(curtail) * dt_h
    curtail_cost = sum(curtail[t] * rt[t] for t in range(n)) * dt_h
    return {
        "energy_mwh": energy,
        "available_energy_mwh": available_energy,
        "curtail_energy_mwh": curtail_energy,
        "curtail_cost_cny": curtail_cost,
        "spot_cny": spot,
        "capture_cny_per_mwh": capture,
        "cfd_cny": cfd,
        "opex_cny": opex,
        "fixed_cny": fixed,
        "deviation_ratio": deviation_ratio,
        "deviation_penalty_cny": deviation_penalty,
        "net_margin_cny": net,
        "two_settlement_spot_cny": two_spot,
        "two_settlement_capture_cny_per_mwh": two_capture,
        "two_settlement_cfd_cny": two_cfd,
        "two_settlement_net_margin_cny": two_net,
        "two_settlement_difference_cny": two_net - net,
        "declared_energy_mwh": declared_energy,
        "completion_ratio": energy / declared_energy if declared_energy > 0 else None,
        "declaration_accuracy": (
            1.0 - sum(abs(available[t] - declared[t]) for t in range(n)) * dt_h / available_energy
            if available_energy > 0
            else None
        ),
        "curtail_slots": sum(1 for value in curtail if value > 1e-9),
        "negative_rt_slots": sum(1 for value in rt if value < -1e-9),
    }


def build_bridge(plan, actual, t1, schedule, config, report):
    """Six buckets from the day-ahead reference plan to the actual net margin."""
    n = report["predicates"]["points_per_day"]
    dt_h = report["predicates"]["mtu_min"] / 60.0
    ratio = report["predicates"]["contract_ratio"]
    contract_price = report["predicates"]["contract_price"]
    opex = report["predicates"]["opex"]
    declared_energy = schedule["declared_energy_mwh"]
    actual_energy = actual["energy_mwh"]
    delta_energy = actual_energy - declared_energy
    da_average = plan["spot_cny"] / declared_energy if declared_energy > 0 else 0.0
    actual_capture = actual["capture_cny_per_mwh"]

    buckets = [
        {
            "item": "电量偏差（按日前价）",
            "category": "电量",
            "owner": "预测/执行",
            "amount": delta_energy * da_average,
        },
        {
            "item": "实时价格偏差（按实际电量）",
            "category": "价格",
            "owner": "市场",
            "amount": actual_energy * (actual_capture - da_average),
        },
        {
            "item": "CfD 电量效应",
            "category": "合约",
            "owner": "合约结算",
            "amount": ratio * delta_energy * (contract_price - da_average),
        },
        {
            "item": "CfD 价格效应",
            "category": "合约",
            "owner": "合约结算",
            "amount": ratio * actual_energy * (da_average - actual_capture),
        },
        {
            "item": "运营成本偏差",
            "category": "成本",
            "owner": "财务",
            "amount": -opex * delta_energy,
        },
        {
            "item": "申报偏差考核",
            "category": "考核",
            "owner": "调度/考核",
            "amount": -actual["deviation_penalty_cny"],
        },
    ]
    plan_profit = plan["net_margin_cny"]
    actual_profit = actual["net_margin_cny"]
    total = sum(item["amount"] for item in buckets)
    return {
        "plan_profit": plan_profit,
        "actual_profit": actual_profit,
        "delta": actual_profit - plan_profit,
        "identity_gap": actual_profit - plan_profit - total,
        "plan_spot": plan["spot_cny"],
        "actual_spot": actual["spot_cny"],
        "plan_cfd": plan["cfd_cny"],
        "actual_cfd": actual["cfd_cny"],
        "plan_energy_mwh": declared_energy,
        "actual_energy_mwh": actual_energy,
        "da_average_cny_per_mwh": da_average,
        "actual_capture_cny_per_mwh": actual_capture,
        "buckets": buckets,
    }


def build_bridge_detail(t1, schedule, config, report):
    n = report["predicates"]["points_per_day"]
    dt_h = report["predicates"]["mtu_min"] / 60.0
    declared = schedule["declared"]
    detail = []
    for slot in range(n):
        gap = t1["output_mw"][slot] - declared[slot]
        detail.append(
            {
                "slot": slot,
                "start": _slot_time(slot, report["predicates"]["mtu_min"]),
                "declared_mw": declared[slot],
                "available_mw": t1["available_mw"][slot],
                "output_mw": t1["output_mw"][slot],
                "curtail_mw": t1["curtail_mw"][slot],
                "rt_price_cny_per_mwh": t1["rt_price"][slot],
                "completion_ratio": (
                    t1["output_mw"][slot] / declared[slot] if declared[slot] > 1e-9 else None
                ),
                "quantity_effect_cny": gap * t1["rt_price"][slot] * dt_h,
            }
        )
    detail.sort(key=lambda item: abs(item["quantity_effect_cny"]), reverse=True)
    return detail[:5]


def _bisect_threshold(evaluate, low, high, target=0.0):
    low_value = evaluate(low)
    high_value = evaluate(high)
    if (low_value > target) == (high_value > target):
        return None
    for _ in range(80):
        middle = (low + high) / 2.0
        middle_value = evaluate(middle)
        if (middle_value > target) == (low_value > target):
            low = middle
            low_value = middle_value
        else:
            high = middle
            high_value = middle_value
    return (low + high) / 2.0


def build_sensitivity(d1, strategy, config, report, selected):
    cases = []

    def add_case(name, change, reference="选中策略", baseline=None, **kwargs):
        result = evaluate_strategy(d1, strategy, config, report, **kwargs)
        base = baseline if baseline is not None else selected["expected_net_margin_cny"]
        cases.append(
            {
                "case": name,
                "change": change,
                "reference": reference,
                "expected_net_margin_cny": result["expected_net_margin_cny"],
                "delta_vs_base_cny": result["expected_net_margin_cny"] - base,
                "cvar_cny": result["cvar_cny"],
                "expected_energy_mwh": result["expected_energy_mwh"],
                "expected_curtail_energy_mwh": result["expected_curtail_energy_mwh"],
                "capture_cny_per_mwh": result["expected_capture_cny_per_mwh"],
                "cfd_cny": result["expected_cfd_cny"],
                "deviation_penalty_cny": result["expected_deviation_penalty_cny"],
            }
        )

    for multiplier in config["policy"]["sensitivity"]["price_multipliers"]:
        add_case(
            f"实时价 ×{multiplier:.2f}",
            f"全部实时价格情景 ×{multiplier:.2f}",
            price_multiplier=multiplier,
        )
    for multiplier in config["policy"]["sensitivity"]["wind_multipliers"]:
        add_case(
            f"风功率 ×{multiplier:.2f}",
            f"全部风功率情景 ×{multiplier:.2f}，并重新申报",
            wind_multiplier=multiplier,
        )
    for ratio in config["policy"]["sensitivity"]["contract_ratios"]:
        add_case(
            f"合约比例 {ratio:.0%}",
            f"CfD 比例从 {selected['contract_ratio']:.0%} 调到 {ratio:.0%}",
            contract_ratio=ratio,
        )
    curtail_base = evaluate_strategy(d1, strategy, config, report, curtail_ratio=1.0)
    if selected["curtail_ratio"] < 1.0:
        add_case(
            "弃风策略基准",
            "弃风比例从 "
            f"{selected['curtail_ratio']:.0%} 调到 100%，阈值保持 "
            f"{selected['curtail_threshold_cny_per_mwh']:.0f} 元/MWh",
            curtail_ratio=1.0,
        )
    for threshold in config["policy"]["sensitivity"]["curtail_thresholds"]:
        add_case(
            f"弃风阈值 {threshold:.0f}",
            f"按 100% 弃风比例，阈值从 {selected['curtail_threshold_cny_per_mwh']:.0f} 调到 {threshold:.0f} 元/MWh",
            reference="100% 弃风基准",
            baseline=curtail_base["expected_net_margin_cny"],
            curtail_ratio=1.0,
            curtail_threshold=threshold,
        )
    combined = config["policy"]["sensitivity"]["combined"]
    add_case(
        "组合压力",
        "实时价 −15%、风功率 −10%、合约比例 30%、弃风阈值 −50、100% 弃风",
        price_multiplier=combined["price_multiplier"],
        wind_multiplier=combined["wind_multiplier"],
        contract_ratio=combined["contract_ratio"],
        curtail_threshold=combined["curtail_threshold_cny_per_mwh"],
        curtail_ratio=combined.get("curtail_ratio", 1.0),
    )
    return cases


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _money(value):
    return f"{value:,.2f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def _signed(value):
    return "—" if value is None else f"{value:+,.2f}"


def write_review(path, config, report, d1, selected, actual, bridge, bridge_detail, sensitivity, thresholds, fingerprint):
    strategy = selected["strategy"]
    lines = [
        "# 蒙西风电现货 · 复核表",
        "",
        f"> 实例 `{config['meta']['instance_id']}` · {config['meta']['province']} · "
        f"{config['meta']['entity_type']} · 交易日 {d1['date']} · 数据截止 {config['meta']['data_cutoff']} · 等级 {config['meta']['grade']}",
        "",
        "## 1. 结论",
        "",
        f"- 选中策略 **{strategy['label']}**：声明分位 P{strategy['declared_quantity_quantile'] * 100:.0f}，"
        f"弃风阈值 {selected['curtail_threshold_cny_per_mwh']:.0f} 元/MWh，"
        f"情景期望净收益 **{_money(selected['expected_net_margin_cny'])} 元**，CVaR {_money(selected['cvar_cny'])} 元。",
        f"- 情景期望捕获价 **{_money(selected['expected_capture_cny_per_mwh'])} 元/MWh**，"
        f"期望电量 {_money(selected['expected_energy_mwh'])} MWh，"
        f"期望弃风 {_money(selected['expected_curtail_energy_mwh'])} MWh。",
        f"- 日前参考计划净收益 {_money(selected['plan']['net_margin_cny'])} 元；"
        f"T+1 实际结算净收益 **{_money(actual['net_margin_cny'])} 元**，"
        f"较计划 {_signed(bridge['delta'])} 元。",
        f"- 实际捕获价 {_money(actual['capture_cny_per_mwh'])} 元/MWh，"
        f"日前参考价 {_money(bridge['da_average_cny_per_mwh'])} 元/MWh；"
        f"实际弃风 {_money(actual['curtail_energy_mwh'])} MWh，负价时段 {actual['negative_rt_slots']} 个。",
        f"- 申报偏差率 {_pct(actual['deviation_ratio'])}（免考核带 ±{report['predicates']['deviation_band']:.0%}），"
        f"偏差考核 **−{_money(actual['deviation_penalty_cny'])} 元**；"
        f"情景期望考核 −{_money(selected['expected_deviation_penalty_cny'])} 元。",
        "",
        "**一句话**：蒙西的日前只是预出清，真正进账的是实时价 × 实际电量；负价时弃不弃风，还要看按实际电量计价的 CfD 是否被一起弃掉。",
        "",
        "## 2. 四策略对比（五情景期望）",
        "",
        "| 策略 | 申报分位 | 弃风阈值（元/MWh） | 期望净收益（元） | 期望考核（元） | CVaR（元） | 期望电量（MWh） | 期望弃风（MWh） | 捕获价（元/MWh） |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["strategy_results"]:
        lines.append(
            f"| {item['strategy']['label']} | P{item['strategy']['declared_quantity_quantile'] * 100:.0f} | "
            f"{item['curtail_threshold_cny_per_mwh']:.0f} | {_money(item['expected_net_margin_cny'])} | "
            f"−{_money(item['expected_deviation_penalty_cny'])} | "
            f"{_money(item['cvar_cny'])} | {_money(item['expected_energy_mwh'])} | "
            f"{_money(item['expected_curtail_energy_mwh'])} | {_money(item['expected_capture_cny_per_mwh'])} |"
        )
    lines.extend(
        [
            "",
            "选择规则是情景期望净收益最大，不是单日现货收入最大；CVaR 与弃风电量同时列出，防止用高波动策略换期望值。申报分位越低越保守，但可用电量高于申报时同样触发偏差考核。",
            "",
            "## 3. 选中策略的情景明细",
            "",
            "| 情景 | 权重 | 可用电量（MWh） | 弃风（MWh） | 上网电量（MWh） | 捕获价（元/MWh） | 现货收入（元） | CfD（元） | 偏差率 | 偏差考核（元） | 净收益（元） |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for outcome in selected["outcomes"]:
        lines.append(
            f"| s{outcome['scenario']} | {outcome['weight']:.0%} | {_money(outcome['available_energy_mwh'])} | "
            f"{_money(outcome['curtail_energy_mwh'])} | {_money(outcome['energy_mwh'])} | "
            f"{_money(outcome['capture_cny_per_mwh'])} | {_money(outcome['spot_cny'])} | "
            f"{_money(outcome['cfd_cny'])} | {_pct(outcome['deviation_ratio'])} | "
            f"−{_money(outcome['deviation_penalty_cny'])} | {_money(outcome['net_margin_cny'])} |"
        )
    lines.extend(
        [
            "",
            "s1 是「大风 + 负价」情景，s5 是「小风 + 高价」情景；风功率与价格按同一编号配对，不能把两套情景独立抽样后随意拼配。",
            "",
            "## 4. T+1 实际结算与差异桥",
            "",
            "| 项目 | 值 |",
            "|---|---:|",
            f"| 实际上网电量 | {_money(actual['energy_mwh'])} MWh |",
            f"| 实际可用电量 | {_money(actual['available_energy_mwh'])} MWh |",
            f"| 弃风电量 | {_money(actual['curtail_energy_mwh'])} MWh |",
            f"| 实时捕获价 | {_money(actual['capture_cny_per_mwh'])} 元/MWh |",
            f"| 现货收入（实时全电量） | {_money(actual['spot_cny'])} 元 |",
            f"| CfD 结算 | {_money(actual['cfd_cny'])} 元 |",
            f"| 运维成本 | {_money(actual['opex_cny'])} 元 |",
            f"| 固定成本 | {_money(actual['fixed_cny'])} 元 |",
            f"| 申报偏差率（免考核带 ±{report['predicates']['deviation_band']:.0%}） | {_pct(actual['deviation_ratio'])} |",
            f"| 申报偏差考核 | −{_money(actual['deviation_penalty_cny'])} 元 |",
            f"| **实际净收益** | **{_money(actual['net_margin_cny'])} 元** |",
            f"| 日前参考计划净收益 | {_money(bridge['plan_profit'])} 元 |",
            f"| 计划 → 实际差异 | {_signed(bridge['delta'])} 元 |",
            f"| 两结算对照净收益 | {_money(actual['two_settlement_net_margin_cny'])} 元 |",
            f"| 两结算 − 实时全电量 | {_signed(actual['two_settlement_difference_cny'])} 元 |",
            "",
            "| 差异桥科目 | 类别 | 责任 | 金额（元） |",
            "|---|---|---|---:|",
        ]
    )
    for item in bridge["buckets"]:
        lines.append(f"| {item['item']} | {item['category']} | {item['owner']} | {_signed(item['amount'])} |")
    lines.append(f"| **合计** | | | **{_signed(bridge['delta'])}** |")
    lines.extend(
        [
            f"",
            f"差异桥残差 {bridge['identity_gap']:.2e} 元。两结算对照与实时全电量的差额约等于申报电量 ×（日前价 − 实时价）×（1 − 合约比例）；若省级正式规则采用另一种结算顺序，以正式规则为准。",
            "",
            "差异最大的时段：",
            "",
            "| 时段 | 申报（MW） | 可用（MW） | 上网（MW） | 弃风（MW） | 实时价 | 完成率 | 量差影响（元） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in bridge_detail:
        lines.append(
            f"| {item['start']} | {item['declared_mw']:.1f} | {item['available_mw']:.1f} | "
            f"{item['output_mw']:.1f} | {item['curtail_mw']:.1f} | {item['rt_price_cny_per_mwh']:.2f} | "
            f"{_pct(item['completion_ratio'])} | {_signed(item['quantity_effect_cny'])} |"
        )
    lines.extend(
        [
            "",
            "## 5. 敏感性",
            "",
            "| 情景 | 关键变化 | 对照基准 | 期望净收益（元） | 较基准（元） | 期望考核（元） | CVaR（元） | 捕获价（元/MWh） | CfD（元） |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case in sensitivity:
        lines.append(
            f"| {case['case']} | {case['change']} | {case['reference']} | {_money(case['expected_net_margin_cny'])} | "
            f"{_signed(case['delta_vs_base_cny'])} | −{_money(case['deviation_penalty_cny'])} | "
            f"{_money(case['cvar_cny'])} | {_money(case['capture_cny_per_mwh'])} | {_money(case['cfd_cny'])} |"
        )
    lines.extend(
        [
            "",
            "「弃风策略基准」一行先把弃风比例调到 100%；其后两行只改阈值，因此「较基准」只反映阈值变化。100% 弃风是压力测试，不是推荐策略。",
            "",
            "## 6. 临界值",
            "",
        ]
    )
    if thresholds.get("curtail_break_even_cny_per_mwh") is None:
        lines.append("- 弃风临界价：无法从当前捕获价推出（合约比例或价差为 0）。")
    else:
        lines.append(
            f"- 弃风临界价约 **{thresholds['curtail_break_even_cny_per_mwh']:.2f} 元/MWh**："
            "按实际捕获价与 CfD 比例估算，实时价低于该值时弃风才可能减少亏损；这是边际近似，不是调度指令。"
        )
    if thresholds.get("price_multiplier") is None:
        lines.append("- 实时价盈亏平衡：在 0–2 倍范围内未触及。")
    else:
        lines.append(f"- 实时价盈亏平衡：约 **{thresholds['price_multiplier']:.2f} 倍**（基准 1.00）。")
    if thresholds.get("contract_ratio") is None:
        lines.append("- 合约比例盈亏平衡：在 0–100% 范围内未触及。")
    else:
        lines.append(f"- 合约比例盈亏平衡：约 **{thresholds['contract_ratio'] * 100:.1f}%**（基准 {selected['contract_ratio'] * 100:.0f}%）。")
    lines.extend(
        [
            "",
            "## 7. 口径提醒",
            "",
            "- 蒙西是**全电量单轨制**：没有计划电量与市场电量双轨，中长期是差价合约而不是物理交割；不要套用其他省「中长期电量 + 现货偏差」的双轨账本。",
            "- **日前预出清不用于结算**：本包按实时全电量结算；若正式规则采用日前 + 偏差两结算，本包另列两结算对照，两者差额不能当作套利空间。",
            "- **限价三套口径**：早期 4-10 月 40-550、其他月 40-600（B）；2025 实绩 -48.66 至 1555.85（B）；2026 征求意见稿 -50 至 1500（C，未生效）。本包模型边界 -60 至 1600 只是覆盖实绩的演示区间，不是现行限价。",
            "- **增量无机制电价**：2025-06-01 后并网项目暂不纳入机制、无保底价；0.2829 元/kWh 只适用于存量项目，不能拿来做增量项目现金流。",
            "- **负价弃风不是免费选项**：弃风减少电量，也减少按实际电量计价的 CfD 对冲；是否弃风要按「避免的负价损失 − 失去的 CfD」比较。",
            "- **申报偏差考核是 D 级简化**：按弃风前可用电量与申报电量比较，超出 ±5% 的部分按 30 元/MWh 计；蒙西省级正式考核条款与免考核带待核，不能把本包数值当监管口径。",
            "- **5 分钟实时出清被聚合为 96 点**：本包不模拟 5 分钟内滚动决策、SOC/爬坡/断面约束，不能替代实时调度系统。",
            f"风格指纹 `{fingerprint}`；本复核表由 `run.py` 生成，计算期为 {d1['date']} 单日 96 点。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_instance(instance_path, d1_path, t1_path, out_dir=None):
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

    strategy_results = []
    for name, strategy in config["policy"]["strategies"].items():
        result = evaluate_strategy(d1, strategy, config, report)
        result["name"] = name
        strategy_results.append(result)
    report["strategy_results"] = strategy_results
    selected = max(strategy_results, key=lambda item: (item["expected_net_margin_cny"], item["cvar_cny"]))
    schedule = selected["schedule"]
    plan = selected["plan"]

    actual = None
    bridge = None
    bridge_detail = None
    sensitivity = []
    thresholds = {}
    if t1 is not None:
        actual = settle_actual(t1, d1, schedule, selected["strategy"], config, report)
        bridge = build_bridge(plan, actual, t1, schedule, config, report)
        bridge_detail = build_bridge_detail(t1, schedule, config, report)

    sensitivity = build_sensitivity(d1, selected["strategy"], config, report, selected)

    def price_net(multiplier):
        return evaluate_strategy(
            d1, selected["strategy"], config, report, price_multiplier=multiplier
        )["expected_net_margin_cny"]

    def ratio_net(ratio):
        return evaluate_strategy(
            d1, selected["strategy"], config, report, contract_ratio=ratio
        )["expected_net_margin_cny"]

    thresholds["price_multiplier"] = _bisect_threshold(price_net, 0.0, 2.0)
    thresholds["contract_ratio"] = _bisect_threshold(ratio_net, 0.0, 1.0)
    if actual is not None:
        thresholds["curtail_break_even_cny_per_mwh"] = -report["predicates"]["contract_ratio"] * (
            report["predicates"]["contract_price"] - actual["capture_cny_per_mwh"]
        )
    else:
        thresholds["curtail_break_even_cny_per_mwh"] = -report["predicates"]["contract_ratio"] * (
            report["predicates"]["contract_price"] - selected["expected_capture_cny_per_mwh"]
        )

    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = Path(out_dir) if out_dir is not None else HERE / "out" / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)

    bid_rows = []
    pred = report["predicates"]
    for slot in range(pred["points_per_day"]):
        expected_rt = sum(
            pred["scenario_weights"][index] * d1["prices"][index][slot]
            for index in range(len(d1["prices"]))
        )
        bid_rows.append(
            {
                "date": d1["date"],
                "slot": slot,
                "start": d1["start"][slot],
                "end": d1["end"][slot],
                "forecast_mw": d1["forecast"][slot],
                "declared_mw": schedule["declared"][slot],
                "bid_price_cny_per_mwh": selected["strategy"]["bid_price_cny_per_mwh"],
                "da_price_cny_per_mwh": d1["da_price"][slot],
                "expected_rt_price_cny_per_mwh": expected_rt,
                "curtail_threshold_cny_per_mwh": selected["curtail_threshold_cny_per_mwh"],
                "note": f"P{selected['strategy']['declared_quantity_quantile'] * 100:.0f}; DA pre-clear is reference only",
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
            "da_price_cny_per_mwh",
            "expected_rt_price_cny_per_mwh",
            "curtail_threshold_cny_per_mwh",
            "note",
        ],
    )

    strategy_rows = []
    for item in strategy_results:
        strategy_rows.append(
            {
                "strategy": item["name"],
                "label": item["strategy"]["label"],
                "quantile": item["strategy"]["declared_quantity_quantile"],
                "bid_price_cny_per_mwh": item["strategy"]["bid_price_cny_per_mwh"],
                "curtail_threshold_cny_per_mwh": item["curtail_threshold_cny_per_mwh"],
                "expected_net_margin_cny": item["expected_net_margin_cny"],
                "cvar_cny": item["cvar_cny"],
                "expected_energy_mwh": item["expected_energy_mwh"],
                "expected_curtail_energy_mwh": item["expected_curtail_energy_mwh"],
                "expected_capture_cny_per_mwh": item["expected_capture_cny_per_mwh"],
                "expected_spot_cny": item["expected_spot_cny"],
                "expected_cfd_cny": item["expected_cfd_cny"],
                "expected_opex_cny": item["expected_opex_cny"],
                "expected_fixed_cny": item["expected_fixed_cny"],
                "expected_deviation_penalty_cny": item["expected_deviation_penalty_cny"],
            }
        )
    _write_csv(
        out_dir / "strategies.csv",
        strategy_rows,
        [
            "strategy",
            "label",
            "quantile",
            "bid_price_cny_per_mwh",
            "curtail_threshold_cny_per_mwh",
            "expected_net_margin_cny",
            "cvar_cny",
            "expected_energy_mwh",
            "expected_curtail_energy_mwh",
            "expected_capture_cny_per_mwh",
            "expected_spot_cny",
            "expected_cfd_cny",
            "expected_opex_cny",
            "expected_fixed_cny",
            "expected_deviation_penalty_cny",
        ],
    )

    scenario_rows = []
    for outcome in selected["outcomes"]:
        scenario_rows.append(
            {
                "scenario": f"s{outcome['scenario']}",
                "weight": outcome["weight"],
                "available_energy_mwh": outcome["available_energy_mwh"],
                "curtail_energy_mwh": outcome["curtail_energy_mwh"],
                "energy_mwh": outcome["energy_mwh"],
                "capture_cny_per_mwh": outcome["capture_cny_per_mwh"],
                "spot_cny": outcome["spot_cny"],
                "cfd_cny": outcome["cfd_cny"],
                "opex_cny": outcome["opex_cny"],
                "fixed_cny": outcome["fixed_cny"],
                "deviation_ratio": outcome["deviation_ratio"],
                "deviation_penalty_cny": outcome["deviation_penalty_cny"],
                "net_margin_cny": outcome["net_margin_cny"],
            }
        )
    _write_csv(
        out_dir / "scenarios.csv",
        scenario_rows,
        [
            "scenario",
            "weight",
            "available_energy_mwh",
            "curtail_energy_mwh",
            "energy_mwh",
            "capture_cny_per_mwh",
            "spot_cny",
            "cfd_cny",
            "opex_cny",
            "fixed_cny",
            "deviation_ratio",
            "deviation_penalty_cny",
            "net_margin_cny",
        ],
    )

    if t1 is not None:
        n = pred["points_per_day"]
        dt_h = pred["mtu_min"] / 60.0
        total_energy = actual["energy_mwh"]
        settlement_rows = []
        for slot in range(n):
            slot_energy = t1["output_mw"][slot] * dt_h
            cfd_slot = actual["cfd_cny"] * slot_energy / total_energy if total_energy > 0 else 0.0
            settlement_rows.append(
                {
                    "date": t1["date"],
                    "slot": slot,
                    "start": d1["start"][slot],
                    "end": d1["end"][slot],
                    "da_price_cny_per_mwh": t1["da_price"][slot],
                    "rt_price_cny_per_mwh": t1["rt_price"][slot],
                    "actual_available_mw": t1["available_mw"][slot],
                    "actual_output_mw": t1["output_mw"][slot],
                    "actual_curtail_mw": t1["curtail_mw"][slot],
                    "spot_cny": slot_energy * t1["rt_price"][slot],
                    "cfd_cny": cfd_slot,
                }
            )
        _write_csv(
            out_dir / "settlement.csv",
            settlement_rows,
            [
                "date",
                "slot",
                "start",
                "end",
                "da_price_cny_per_mwh",
                "rt_price_cny_per_mwh",
                "actual_available_mw",
                "actual_output_mw",
                "actual_curtail_mw",
                "spot_cny",
                "cfd_cny",
            ],
        )
        bridge_out = {
            "plan_profit": bridge["plan_profit"],
            "actual_profit": bridge["actual_profit"],
            "delta": bridge["delta"],
            "identity_gap": bridge["identity_gap"],
            "plan_spot": bridge["plan_spot"],
            "actual_spot": bridge["actual_spot"],
            "plan_cfd": bridge["plan_cfd"],
            "actual_cfd": bridge["actual_cfd"],
            "plan_energy_mwh": bridge["plan_energy_mwh"],
            "actual_energy_mwh": bridge["actual_energy_mwh"],
            "da_average_cny_per_mwh": bridge["da_average_cny_per_mwh"],
            "actual_capture_cny_per_mwh": bridge["actual_capture_cny_per_mwh"],
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

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "selected_strategy": selected["name"],
        "selected": {
            "label": selected["strategy"]["label"],
            "declared_quantity_quantile": selected["strategy"]["declared_quantity_quantile"],
            "bid_price_cny_per_mwh": selected["strategy"]["bid_price_cny_per_mwh"],
            "curtail_threshold_cny_per_mwh": selected["curtail_threshold_cny_per_mwh"],
            "contract_ratio": selected["contract_ratio"],
            "expected_net_margin_cny": selected["expected_net_margin_cny"],
            "cvar_cny": selected["cvar_cny"],
            "expected_energy_mwh": selected["expected_energy_mwh"],
            "expected_curtail_energy_mwh": selected["expected_curtail_energy_mwh"],
            "expected_capture_cny_per_mwh": selected["expected_capture_cny_per_mwh"],
            "expected_spot_cny": selected["expected_spot_cny"],
            "expected_cfd_cny": selected["expected_cfd_cny"],
            "expected_deviation_penalty_cny": selected["expected_deviation_penalty_cny"],
            "plan_net_margin_cny": plan["net_margin_cny"],
            "scenarios": selected["outcomes"],
        },
        "strategies": [
            {
                "name": item["name"],
                "label": item["strategy"]["label"],
                "expected_net_margin_cny": item["expected_net_margin_cny"],
                "cvar_cny": item["cvar_cny"],
                "expected_curtail_energy_mwh": item["expected_curtail_energy_mwh"],
                "expected_deviation_penalty_cny": item["expected_deviation_penalty_cny"],
            }
            for item in strategy_results
        ],
        "actual": None
        if actual is None
        else {
            "energy_mwh": actual["energy_mwh"],
            "available_energy_mwh": actual["available_energy_mwh"],
            "curtail_energy_mwh": actual["curtail_energy_mwh"],
            "spot_cny": actual["spot_cny"],
            "capture_cny_per_mwh": actual["capture_cny_per_mwh"],
            "cfd_cny": actual["cfd_cny"],
            "opex_cny": actual["opex_cny"],
            "fixed_cny": actual["fixed_cny"],
            "deviation_ratio": actual["deviation_ratio"],
            "deviation_penalty_cny": actual["deviation_penalty_cny"],
            "net_margin_cny": actual["net_margin_cny"],
            "two_settlement_net_margin_cny": actual["two_settlement_net_margin_cny"],
            "two_settlement_difference_cny": actual["two_settlement_difference_cny"],
            "completion_ratio": actual["completion_ratio"],
            "declaration_accuracy": actual["declaration_accuracy"],
            "curtail_slots": actual["curtail_slots"],
            "negative_rt_slots": actual["negative_rt_slots"],
        },
        "bridge": None
        if bridge is None
        else {
            "plan_profit": bridge["plan_profit"],
            "actual_profit": bridge["actual_profit"],
            "delta": bridge["delta"],
            "identity_gap": bridge["identity_gap"],
        },
        "sensitivity": sensitivity,
        "thresholds": thresholds,
        "warnings": report["warnings"],
        "files": {
            "bid_sheet": "bid_sheet.csv",
            "strategies": "strategies.csv",
            "scenarios": "scenarios.csv",
            "settlement": "settlement.csv" if t1 is not None else None,
            "bridge": "bridge.json" if bridge is not None else None,
            "review": "review.md",
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(
        out_dir / "review.md",
        config,
        report,
        d1,
        selected,
        actual,
        bridge,
        bridge_detail or [],
        sensitivity,
        thresholds,
        fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "selected": selected,
        "actual": actual,
        "bridge": bridge,
        "bridge_detail": bridge_detail,
        "sensitivity": sensitivity,
        "thresholds": thresholds,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mengxi wind-farm spot instance runner")
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
    selected = summary["selected"]
    print(f"实例：{summary['instance_id']} / 交易日 {summary['trading_day']}")
    print(
        f"选中：{selected['label']}；期望净收益 {selected['expected_net_margin_cny']:,.2f} 元，"
        f"CVaR {selected['cvar_cny']:,.2f} 元"
    )
    print(
        f"期望电量 {selected['expected_energy_mwh']:,.1f} MWh，"
        f"弃风 {selected['expected_curtail_energy_mwh']:,.1f} MWh，"
        f"捕获价 {selected['expected_capture_cny_per_mwh']:,.2f} 元/MWh，"
        f"偏差考核 {selected['expected_deviation_penalty_cny']:,.2f} 元"
    )
    if result["actual"] is not None:
        actual = result["actual"]
        bridge = result["bridge"]
        print(
            f"实际：电量 {actual['energy_mwh']:,.1f} MWh，弃风 {actual['curtail_energy_mwh']:,.1f} MWh，"
            f"捕获价 {actual['capture_cny_per_mwh']:,.2f} 元/MWh，"
            f"净收益 {actual['net_margin_cny']:,.2f} 元"
        )
        print(
            f"差异桥：计划 {bridge['plan_profit']:,.2f} → 实际 {bridge['actual_profit']:,.2f}，"
            f"差异 {bridge['delta']:+,.2f} 元，残差 {bridge['identity_gap']:.2e}"
        )
        print(
            f"两结算对照：{actual['two_settlement_net_margin_cny']:,.2f} 元，"
            f"与实时全电量差 {actual['two_settlement_difference_cny']:+,.2f} 元"
        )
    print(f"弃风临界价：{result['thresholds']['curtail_break_even_cny_per_mwh']:.2f} 元/MWh")
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
