#!/usr/bin/env python3
"""Run the Shanghai independent-datacenter VPP instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the rule parameters (407 号「1+5」事实为 A 级，
  邀约/结算参数为 D 级演示假设), the datacenter asset, the resource
  portfolio (制冷 / UPS / 可迁移批处理 / 附属园区空调), the policy profile,
  contracts and data contract.
* ``data/history_demo.csv`` is the baseline sample (5 workdays x 96 points,
  其中 1 日为批次任务外迁日，触发基线剔除).
* ``data/event_demo.csv`` is the invitation (3 scenarios x 2 control types).
* ``data/t1_loads_demo.csv`` and ``data/t1_event_demo.csv`` are the T+1
  metered loads and the actual clearing outcome.

All bundled numbers are synthetic grade D. They are not a market forecast, a
live bidding signal, a settlement basis or investment advice. 规则事实只取自
knowledge/上海电力市场-2026-11.md 与 knowledge/虚拟电厂聚合调度与商业模式-2026-11.md
中带级别标注的内容；模块没有的上海规则值一律 null + 待核实。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parents[1]
sys.path.insert(0, str(SKILL_DIR / "tools"))

import cbl  # noqa: E402

CONTROL_TYPES = ("direct", "self")
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


def _optional_number(mapping, key, path, minimum=None, maximum=None):
    """字段允许显式 null（待核实）；给出值时按数值校验。"""
    if key not in mapping:
        raise ConfigError(f"{path}.{key} is required (use null when 待核实)")
    value = mapping[key]
    if value is None:
        return None
    return _number(value, path, minimum, maximum)


def _integer(value, path, minimum=None):
    number = _number(value, path, minimum)
    if abs(number - round(number)) > 1e-9:
        raise ConfigError(f"{path} must be an integer")
    return int(round(number))


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
    report["provenance"].append(
        {"block": f"rules.{name}", "grade": grade, "source": source}
    )
    return block


def _parse_hhmm(value, path):
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ConfigError(f"{path} must be HH:MM, got {text!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        raise ConfigError(f"{path} must be HH:MM, got {text!r}")
    if not (0 <= hour <= 24 and 0 <= minute < 60):
        raise ConfigError(f"{path} is outside 00:00-24:00: {text!r}")
    minutes = hour * 60 + minute
    if minutes > 24 * 60:
        raise ConfigError(f"{path} is outside 00:00-24:00: {text!r}")
    return minutes


def _parse_window(value, path):
    text = str(value).strip()
    for separator in ("-", "–", "~"):
        if separator in text:
            start_text, end_text = text.split(separator, 1)
            return _parse_hhmm(start_text, f"{path}.start"), _parse_hhmm(end_text, f"{path}.end")
    raise ConfigError(f"{path} must be HH:MM-HH:MM, got {text!r}")


def _slot_label(slot, mtu_min):
    minutes = slot * mtu_min
    return f"{minutes // 60:02d}:{minutes % 60:02d}", (
        f"{(minutes + mtu_min) // 60:02d}:{(minutes + mtu_min) % 60:02d}"
    )


def validate_instance(config):
    """Validate the config blocks and return a normalised report."""
    report = {"provenance": [], "warnings": []}
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "market", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    _grade(meta, "meta")
    _text(meta, "disclaimer", "meta")
    if "D 级合成样板" not in meta["disclaimer"]:
        report["warnings"].append("meta.disclaimer 未写明 D 级合成样板声明")
    units = _need(meta, "units", "meta")
    for key, expected in (("power", "MW"), ("energy", "MWh"), ("price", "CNY/kWh")):
        value = _text(units, key, "meta.units")
        if value != expected:
            raise ConfigError(f"meta.units.{key} must be {expected}, got {value!r}")

    rules = _need(config, "rules", "instance")
    plan = _rule_block(rules, "vpp_plan", report)
    dr = _rule_block(rules, "demand_response", report)
    baseline_rule = _rule_block(rules, "baseline", report)
    spot = _rule_block(rules, "spot", report)
    settlement = _rule_block(rules, "settlement", report)
    if bool(spot.get("included", False)):
        raise ConfigError("rules.spot.included=true is not implemented in v1")
    _text(settlement, "incentive_formula", "rules.settlement")

    # ---- rules.vpp_plan：407 号事实（A 级为主，事件口径 B/C、行业口径 C）----
    for key in ("document", "issued", "system_1plus5", "participation"):
        _text(plan, key, "rules.vpp_plan")
    targets = _need(plan, "targets_10k_kw", "rules.vpp_plan")
    for key in ("2025", "2026", "2027"):
        _number(_need(targets, key, "rules.vpp_plan.targets_10k_kw"), f"rules.vpp_plan.targets_10k_kw.{key}", 0.0)
    dc_target = _need(plan, "data_center_target_2027_10k_kw", "rules.vpp_plan")
    for key in ("access", "adjustable"):
        _number(_need(dc_target, key, "rules.vpp_plan.data_center_target_2027_10k_kw"),
                f"rules.vpp_plan.data_center_target_2027_10k_kw.{key}", 0.0)
    call_2025 = _number(
        _optional_number(plan, "call_2025_08_10k_kw", "rules.vpp_plan", 0.0),
        "rules.vpp_plan.call_2025_08_10k_kw",
    )
    operators = _need(plan, "operators_2025_08", "rules.vpp_plan")
    _integer(_need(operators, "count", "rules.vpp_plan.operators_2025_08"),
             "rules.vpp_plan.operators_2025_08.count", 0)
    _number(_need(operators, "declared_10k_kw", "rules.vpp_plan.operators_2025_08"),
            "rules.vpp_plan.operators_2025_08.declared_10k_kw", 0.0)
    _integer(_need(operators, "tests", "rules.vpp_plan.operators_2025_08"),
             "rules.vpp_plan.operators_2025_08.tests", 0)
    _optional_number(plan, "aggregation_threshold", "rules.vpp_plan", 0.0)
    if plan.get("aggregation_threshold") is not None:
        report["warnings"].append("rules.vpp_plan.aggregation_threshold 非 null：407 号口径为未设统一 MW 聚合门槛，请核对来源")
    for key in ("call_2025_08_status", "call_2026_07_status", "data_center_target_status", "management_center_status"):
        if "待核" in str(plan.get(key, "")):
            report["warnings"].append(f"rules.vpp_plan.{key} 含待核实项，结算前须以省级原文确认")

    # ---- rules.demand_response：邀约与调用参数（D 级演示假设 + 待核实）----
    _text(dr, "notice", "rules.demand_response")
    duration_h = _number(
        _need(dr, "duration_h", "rules.demand_response"),
        "rules.demand_response.duration_h",
        1e-9,
    )
    window = _parse_window(_text(dr, "window", "rules.demand_response"), "rules.demand_response.window")
    dispatchable = _parse_window(
        _text(dr, "dispatchable_window", "rules.demand_response"),
        "rules.demand_response.dispatchable_window",
    )
    min_rate = _number(
        _need(dr, "min_response_rate", "rules.demand_response"),
        "rules.demand_response.min_response_rate",
        1e-9,
        1.0,
    )
    overshoot = _number(
        _need(dr, "overshoot_cap_ratio", "rules.demand_response"),
        "rules.demand_response.overshoot_cap_ratio",
        1.0,
        3.0,
    )
    bid_cap = _optional_number(dr, "bid_cap_cny_per_kwh", "rules.demand_response", 1e-9)
    _text(dr, "no_double_participation", "rules.demand_response")
    test_min_ratio = _number(
        _need(dr, "test_min_scale_ratio", "rules.demand_response"),
        "rules.demand_response.test_min_scale_ratio",
        1e-9,
        1.0,
    )
    if bid_cap is None:
        report["warnings"].append(
            "上海需求响应补偿单价与报价上限未核实（bid_cap=null）：报价无上限校验，只按 D 级演示价处理"
        )
    for key in ("single_response_deadline_status", "min_response_rate_status", "overshoot_cap_status", "test_min_scale_status"):
        if "待核实" in str(dr.get(key, "")):
            report["warnings"].append(f"rules.demand_response.{key}：待核实项未估算成事实")
        elif "D 级" in str(dr.get(key, "")):
            report["warnings"].append(f"rules.demand_response.{key} 为 D 级演示假设")
    if "待核" in str(dr.get("duration_status", "")) and "D 级" in str(dr.get("duration_status", "")):
        report["warnings"].append("event 时长为 D 级假设；结算前须核对邀约中的单次事件时长")

    # ---- rules.baseline：通用 CBL（模块 §7.2），上海口径待核 ----
    method = _text(baseline_rule, "method", "rules.baseline")
    count = _integer(_need(baseline_rule, "count", "rules.baseline"), "rules.baseline.count", 3)
    deviation = _number(
        _need(baseline_rule, "deviation", "rules.baseline"), "rules.baseline.deviation", 1e-9, 1.0
    )
    adjustment = _number(
        _need(baseline_rule, "adjustment", "rules.baseline"), "rules.baseline.adjustment", 1e-9
    )
    sample_min = _integer(
        _need(baseline_rule, "sample_min", "rules.baseline"), "rules.baseline.sample_min", 1
    )
    if 24 * 60 % sample_min:
        raise ConfigError("rules.baseline.sample_min must divide 24*60")
    points = 24 * 60 // sample_min
    _text(baseline_rule, "aggregation", "rules.baseline")
    if "待核" in str(baseline_rule.get("status", "")):
        report["warnings"].append(
            "上海 VPP 基线算法未核实：本包按通用 CBL 口径（5 同类日、±25% 剔除、修正系数）演示"
        )

    # ---- rules.asset：数据中心资产（D 级）----
    asset = _need(config, "asset", "instance")
    asset_grade = _grade(asset, "asset")
    asset_source = _text(asset, "source", "asset")
    report["provenance"].append({"block": "asset", "grade": asset_grade, "source": asset_source})
    _text(asset, "aggregation_structure", "asset")
    it_rated = _number(_need(asset, "it_load_rated_mw", "asset"), "asset.it_load_rated_mw", 1e-9)
    pue_design = _number(_need(asset, "pue_design", "asset"), "asset.pue_design", 1.0)
    if pue_design <= 1.0:
        raise ConfigError("asset.pue_design must be above 1.0")
    cooling_rated = _number(_need(asset, "cooling_rated_mw", "asset"), "asset.cooling_rated_mw", 0.0)
    ups_rated = _number(_need(asset, "ups_rated_mw", "asset"), "asset.ups_rated_mw", 0.0)
    campus_rated = _number(_need(asset, "campus_rated_mw", "asset"), "asset.campus_rated_mw", 0.0)
    implied_cooling = it_rated * (pue_design - 1.0)
    if implied_cooling > 0 and not 0.4 * implied_cooling <= cooling_rated <= 1.5 * implied_cooling:
        report["warnings"].append(
            f"制冷额定 {cooling_rated:.1f} MW 与 IT×(PUE−1)={implied_cooling:.1f} MW 偏离较大："
            "PUE 与制冷/IT 负荷耦合，核对是否含园区空调等其他非 IT 负荷"
        )

    # ---- resources：数据中心 + 附属可调资源 ----
    resources_block = _need(config, "resources", "instance")
    items = _need(resources_block, "items", "resources")
    if not isinstance(items, list) or not items:
        raise ConfigError("resources.items must be a non-empty list")
    resources = []
    seen_ids, seen_names, seen_fields = set(), set(), set()
    for index, item in enumerate(items):
        path = f"resources.items[{index}]"
        resource_id = _text(item, "id", path)
        name = _text(item, "name", path)
        control_type = _text(item, "control_type", path)
        if control_type not in CONTROL_TYPES:
            raise ConfigError(f"{path}.control_type must be direct or self")
        max_mw = _number(_need(item, "max_mw", path), f"{path}.max_mw", 1e-9)
        adjustable = _number(
            _need(item, "adjustable_ratio", path), f"{path}.adjustable_ratio", 1e-9, 1.0
        )
        availability = _number(
            _need(item, "availability", path), f"{path}.availability", 1e-9, 1.0
        )
        duration_h = _number(_need(item, "duration_h", path), f"{path}.duration_h", 1e-9)
        share = _number(
            _need(item, "customer_share", path), f"{path}.customer_share", 0.0, 1.0
        )
        if share >= 1.0:
            raise ConfigError(f"{path}.customer_share must be below 1.0")
        allow_negative = bool(_need(item, "allow_negative_load", path))
        commitment = bool(_need(item, "other_market_commitment", path))
        load_field = _text(item, "load_field", path)
        _grade(item, path)
        _text(item, "source", path)
        if resource_id in seen_ids:
            raise ConfigError(f"duplicate resource id: {resource_id}")
        if name in seen_names:
            raise ConfigError(f"duplicate resource name: {name}")
        if load_field in seen_fields:
            raise ConfigError(f"duplicate load_field: {load_field}")
        seen_ids.add(resource_id)
        seen_names.add(name)
        seen_fields.add(load_field)
        capability = max_mw * adjustable * availability
        resources.append(
            {
                "id": resource_id,
                "name": name,
                "control_type": control_type,
                "max_mw": max_mw,
                "adjustable_ratio": adjustable,
                "availability": availability,
                "duration_h": duration_h,
                "customer_share": share,
                "allow_negative_load": allow_negative,
                "other_market_commitment": commitment,
                "enabled": not commitment,
                "load_field": load_field,
                "capability_mw": capability,
                "energy_limit_mwh": max_mw * adjustable * duration_h,
            }
        )
        if commitment:
            report["warnings"].append(
                f"资源 {name} 标记 other_market_commitment=true，已从可调能力中排除"
            )

    capability = {control_type: 0.0 for control_type in CONTROL_TYPES}
    share_weighted = {control_type: 0.0 for control_type in CONTROL_TYPES}
    for resource in resources:
        if not resource["enabled"]:
            continue
        control_type = resource["control_type"]
        capability[control_type] += resource["capability_mw"]
        share_weighted[control_type] += resource["capability_mw"] * resource["customer_share"]
    share_by_type = {
        control_type: (
            share_weighted[control_type] / capability[control_type]
            if capability[control_type] > 0
            else 0.0
        )
        for control_type in CONTROL_TYPES
    }
    for control_type in CONTROL_TYPES:
        if capability[control_type] <= 0:
            raise ConfigError(f"no enabled {control_type} resource with positive capability")

    policy = _need(config, "policy", "instance")
    profile_id = _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    bid_ratio = _need(policy, "bid_ratio", "policy")
    bid_price = _need(policy, "bid_price_cny_per_kwh", "policy")
    declared = {}
    for control_type in CONTROL_TYPES:
        ratio = _number(
            _need(bid_ratio, control_type, "policy.bid_ratio"),
            f"policy.bid_ratio.{control_type}",
            1e-9,
            1.0,
        )
        price = _number(
            _need(bid_price, control_type, "policy.bid_price_cny_per_kwh"),
            f"policy.bid_price_cny_per_kwh.{control_type}",
            0.0,
        )
        if bid_cap is not None and price > bid_cap + 1e-9:
            raise ConfigError(
                f"policy.bid_price_cny_per_kwh.{control_type} ({price}) exceeds the "
                f"rule cap ({bid_cap})"
            )
        if bid_cap is None and price > 0:
            report["warnings"].append(
                f"{control_type} 报价 {price:.2f} 元/kWh 为 D 级演示价：上海官方单价未核实，"
                "不构成报价依据"
            )
        bid_ratio[control_type] = ratio
        bid_price[control_type] = price
    rounding = _number(
        _need(policy, "declaration_rounding_mw", "policy"),
        "policy.declaration_rounding_mw",
        1e-9,
    )
    planned_delivery = _number(
        _need(policy, "planned_delivery_ratio", "policy"),
        "policy.planned_delivery_ratio",
        1e-9,
        1.0,
    )
    cvar_confidence = _number(
        _need(policy, "scenario_cvar_confidence", "policy"),
        "policy.scenario_cvar_confidence",
        1e-9,
        1.0,
    )
    for control_type in CONTROL_TYPES:
        raw = capability[control_type] * bid_ratio[control_type]
        rounded = math.floor(raw / rounding + 1e-9) * rounding
        declared[control_type] = round(rounded, 10)
        if declared[control_type] > capability[control_type] + 1e-9:
            raise ConfigError(
                f"declared {control_type} quantity exceeds capability: "
                f"{declared[control_type]} > {capability[control_type]}"
            )

    contracts = _need(config, "contracts", "instance")
    shortfall = _need(contracts, "shortfall", "contracts")
    threshold = _number(
        _need(shortfall, "delivery_threshold", "contracts.shortfall"),
        "contracts.shortfall.delivery_threshold",
        1e-9,
        1.0,
    )
    extra_share = _number(
        _need(shortfall, "extra_customer_share", "contracts.shortfall"),
        "contracts.shortfall.extra_customer_share",
        0.0,
        1.0,
    )
    if threshold + extra_share > 1.0 + 1e-9:
        raise ConfigError("contracts.shortfall extra share pushes customer share above 1.0")
    opex = _need(contracts, "opex", "contracts")
    variable_opex = _number(
        _need(opex, "variable_cny_per_mwh", "contracts.opex"),
        "contracts.opex.variable_cny_per_mwh",
        0.0,
    )
    fixed_opex = _number(
        _need(opex, "fixed_cny_per_event", "contracts.opex"),
        "contracts.opex.fixed_cny_per_event",
        0.0,
    )
    contracts_grade = _grade(contracts, "contracts")
    contracts_source = _text(contracts, "source", "contracts")
    report["provenance"].append(
        {"block": "contracts", "grade": contracts_grade, "source": contracts_source}
    )
    if planned_delivery < threshold:
        report["warnings"].append(
            "计划执行率低于未达标补偿门槛：计划净收益本身已隐含客户补偿风险"
        )

    qualification = _need(config, "qualification", "instance")
    test_scale = _number(
        _need(qualification, "test_scale_mw", "qualification"),
        "qualification.test_scale_mw",
        1e-9,
    )
    declared_at_test = _number(
        _need(qualification, "declared_at_test_mw", "qualification"),
        "qualification.declared_at_test_mw",
        1e-9,
    )
    test_ratio = test_scale / declared_at_test
    if test_ratio < test_min_ratio - 1e-9:
        raise ConfigError(
            f"qualification.test_scale_mw ({test_scale}) is below "
            f"{test_min_ratio:.0%} of declared_at_test_mw ({declared_at_test})"
        )
    test_window_declared = _parse_window(
        _text(qualification, "test_window", "qualification"),
        "qualification.test_window",
    )
    result = _text(qualification, "result", "qualification")
    if result.lower() != "pass":
        report["warnings"].append(f"qualification.result is {result!r}, not pass")
    _text(qualification, "test_items", "qualification")
    report["provenance"].append(
        {
            "block": "qualification",
            "grade": _grade(qualification, "qualification"),
            "source": _text(qualification, "source", "qualification"),
        }
    )
    report["qualification"] = {
        "test_scale_mw": test_scale,
        "declared_at_test_mw": declared_at_test,
        "scale_ratio": test_ratio,
        "min_scale_ratio": test_min_ratio,
        "window": test_window_declared,
        "result": result,
    }
    if "D 级" in str(dr.get("test_min_scale_status", "")):
        report["warnings"].append(
            "专项实测规模比例 20% 为 D 级演示假设（借用江苏口径演示）；上海实测认定比例未核实"
        )

    data_contract = _need(config, "data_contract", "instance")
    history_contract = _need(data_contract, "history", "data_contract")
    event_contract = _need(data_contract, "event", "data_contract")
    t1_loads_contract = _need(data_contract, "t1_loads", "data_contract")
    t1_event_contract = _need(data_contract, "t1_event", "data_contract")
    for name, block in (
        ("history", history_contract),
        ("event", event_contract),
        ("t1_loads", t1_loads_contract),
        ("t1_event", t1_event_contract),
    ):
        _text(block, "file", f"data_contract.{name}")
        _grade(block, f"data_contract.{name}")
    for name in ("history", "t1_loads"):
        block = data_contract[name]
        load_fields = _need(block, "load_fields", f"data_contract.{name}")
        _text(block, "date_field", f"data_contract.{name}")
        _text(block, "slot_field", f"data_contract.{name}")
        for resource in resources:
            if resource["id"] not in load_fields:
                if resource["enabled"]:
                    raise ConfigError(
                        f"data_contract.{name}.load_fields is missing resource {resource['id']}"
                    )
                report["warnings"].append(
                    f"data_contract.{name}.load_fields is missing disabled resource {resource['id']}"
                )
                continue
            field = _text(load_fields, resource["id"], f"data_contract.{name}.load_fields")
            if field != resource["load_field"]:
                raise ConfigError(
                    f"data_contract.{name}.load_fields.{resource['id']} ({field}) "
                    f"does not match resources[].load_field ({resource['load_field']})"
                )
    weights = _need(event_contract, "scenario_weights", "data_contract.event")
    if not isinstance(weights, list) or len(weights) < 2:
        raise ConfigError("data_contract.event.scenario_weights must list at least two scenarios")
    weights = [_number(value, "data_contract.event.scenario_weights", 0.0, 1.0) for value in weights]
    if abs(sum(weights) - 1.0) > 1e-9:
        raise ConfigError("data_contract.event.scenario_weights must sum to 1")
    _text(event_contract, "scenario_field", "data_contract.event")
    _text(event_contract, "event_date_field", "data_contract.event")
    _text(event_contract, "start_field", "data_contract.event")
    _text(event_contract, "end_field", "data_contract.event")
    _text(event_contract, "required_mw_field", "data_contract.event")
    _text(event_contract, "marginal_price_field", "data_contract.event")
    _text(t1_event_contract, "control_type_field", "data_contract.t1_event")
    _text(t1_event_contract, "cleared_price_field", "data_contract.t1_event")
    _text(t1_event_contract, "awarded_mw_field", "data_contract.t1_event")
    report["provenance"].append(
        {
            "block": "data_contract",
            "grade": "/".join(sorted({block["grade"] for block in (history_contract, event_contract, t1_loads_contract, t1_event_contract)})),
            "source": "本包输入契约；演示数据为 make_demo.py 生成的 D 级合成数据",
        }
    )

    if "待核" in str(settlement.get("unit_price_status", "")) and settlement.get("unit_price_cny_per_kwh") is None:
        report["warnings"].append(
            "上海需求响应补偿单价未核实（settlement.unit_price=null）：严禁把外省单价或模块算例价套给上海"
        )
    if "待核实" in str(settlement.get("funding", "")):
        report["warnings"].append("需求响应资金渠道未核实")
    report["warnings"].append("本包为 D 级合成样板，不对应任何真实数据中心、聚合商、合同或计量数据")

    resource_grade = "/".join(sorted({_grade(item, f"resources.items[{i}]") for i, item in enumerate(items)}))
    report["provenance"].append(
        {
            "block": "resources",
            "grade": resource_grade,
            "source": "资源参数为示例占位；实际按数据中心 IT 台账、UPS/制冷配置与历史响应率填写",
        }
    )
    report.update(
        {
            "mtu_min": sample_min,
            "points_per_day": points,
            "resources": resources,
            "asset": {
                "aggregation_structure": asset["aggregation_structure"],
                "it_load_rated_mw": it_rated,
                "pue_design": pue_design,
                "cooling_rated_mw": cooling_rated,
                "ups_rated_mw": ups_rated,
                "campus_rated_mw": campus_rated,
            },
            "capability_by_type": capability,
            "share_by_type": share_by_type,
            "declared_by_type": declared,
            "bid_ratio": {key: float(value) for key, value in bid_ratio.items()},
            "bid_price": {key: float(value) for key, value in bid_price.items()},
            "caps": bid_cap,
            "overshoot": overshoot,
            "event_duration_h": duration_h,
            "min_response_rate": min_rate,
            "window": window,
            "dispatchable_window": dispatchable,
            "baseline": {
                "method": method,
                "count": count,
                "deviation": deviation,
                "adjustment": adjustment,
            },
            "test": {"min_scale_ratio": test_min_ratio},
            "policy": policy,
            "contracts": {
                "threshold": threshold,
                "extra_share": extra_share,
                "variable_opex": variable_opex,
                "fixed_opex": fixed_opex,
            },
            "declaration_rounding_mw": rounding,
            "planned_delivery_ratio": planned_delivery,
            "cvar_confidence": cvar_confidence,
            "data_contract": data_contract,
            "profile_id": profile_id,
        }
    )
    return report


def _read_rows(path):
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ConfigError(f"{path.name} has no header")
        return list(reader)


def _cell(row, field, path, line_no):
    if field not in row:
        raise ConfigError(f"{path.name} line {line_no}: missing column {field!r}")
    value = row[field]
    if value is None or not str(value).strip():
        raise ConfigError(f"{path.name} line {line_no}: empty value in {field!r}")
    return str(value).strip()


def _float_cell(row, field, path, line_no):
    value = _cell(row, field, path, line_no)
    try:
        number = float(value)
    except ValueError:
        raise ConfigError(f"{path.name} line {line_no}: {field!r} is not a number")
    if not math.isfinite(number):
        raise ConfigError(f"{path.name} line {line_no}: {field!r} is not finite")
    return number


def _group_loads(rows, contract, resources, points, path, required_slots=None):
    date_field = contract["date_field"]
    slot_field = contract["slot_field"]
    load_fields = contract["load_fields"]
    resource_by_id = {resource["id"]: resource for resource in resources}
    by_date = {}
    seen = set()
    for line_no, row in enumerate(rows, start=2):
        date = _cell(row, date_field, path, line_no)
        try:
            slot = int(_cell(row, slot_field, path, line_no))
        except ValueError:
            raise ConfigError(f"{path.name} line {line_no}: slot is not an integer")
        if not 0 <= slot < points:
            raise ConfigError(f"{path.name} line {line_no}: slot {slot} outside 0-{points - 1}")
        key = (date, slot)
        if key in seen:
            raise ConfigError(f"{path.name}: duplicate point {date} slot {slot}")
        seen.add(key)
        loads = {}
        for resource_id, field in load_fields.items():
            resource = resource_by_id.get(resource_id)
            if resource is None:
                raise ConfigError(f"{path.name}: load_fields references unknown resource {resource_id}")
            value = _float_cell(row, field, path, line_no)
            if value < -1e-9 and not resource["allow_negative_load"]:
                raise ConfigError(
                    f"{path.name} line {line_no}: {resource['name']} load cannot be negative"
                )
            loads[resource_id] = value
        by_date.setdefault(date, {})[slot] = loads
    if not by_date:
        raise ConfigError(f"{path.name} has no data rows")
    slots = list(range(points)) if required_slots is None else list(required_slots)
    for date, curve in by_date.items():
        missing = [slot for slot in slots if slot not in curve]
        if missing:
            raise ConfigError(
                f"{path.name}: {date} is missing slots {missing[:6]}"
                + ("..." if len(missing) > 6 else "")
            )
    return by_date


def load_history(path, report):
    contract = report["data_contract"]["history"]
    rows = _read_rows(path)
    by_date = _group_loads(rows, contract, report["resources"], report["points_per_day"], Path(path))
    if len(by_date) < 3:
        raise ConfigError("history must contain at least 3 sample days")
    return by_date


def load_event(path, report):
    contract = report["data_contract"]["event"]
    rows = _read_rows(path)
    scenario_field = contract["scenario_field"]
    control_field = "control_type"
    scenarios = {}
    event_meta = None
    for line_no, row in enumerate(rows, start=2):
        scenario = _cell(row, scenario_field, Path(path), line_no)
        control_type = _cell(row, control_field, Path(path), line_no)
        if control_type not in CONTROL_TYPES:
            raise ConfigError(f"{Path(path).name} line {line_no}: unknown control_type {control_type!r}")
        event_date = _cell(row, contract["event_date_field"], Path(path), line_no)
        start_text = _cell(row, contract["start_field"], Path(path), line_no)
        end_text = _cell(row, contract["end_field"], Path(path), line_no)
        start_min = _parse_hhmm(start_text, f"{Path(path).name} line {line_no} event_start")
        end_min = _parse_hhmm(end_text, f"{Path(path).name} line {line_no} event_end")
        if event_meta is None:
            event_meta = (event_date, start_text, end_text, start_min, end_min)
        elif event_meta[:3] != (event_date, start_text, end_text):
            raise ConfigError("event scenarios must share one event date and window")
        required_mw = _float_cell(row, contract["required_mw_field"], Path(path), line_no)
        price = _float_cell(row, contract["marginal_price_field"], Path(path), line_no)
        if required_mw < -1e-9:
            raise ConfigError(f"{Path(path).name} line {line_no}: required_mw must be non-negative")
        if price < -1e-9:
            raise ConfigError(f"{Path(path).name} line {line_no}: marginal price must be non-negative")
        overlap = str(row.get("overlap_other_dr", "")).strip().lower()
        if overlap in TRUE_TEXT:
            raise ConfigError(
                f"{Path(path).name} line {line_no}: resource already participates in an "
                "overlapping demand-response event; same-period double participation is not allowed"
            )
        slot_map = scenarios.setdefault(scenario, {})
        if control_type in slot_map:
            raise ConfigError(f"{Path(path).name}: duplicate scenario/control_type {scenario}/{control_type}")
        slot_map[control_type] = {
            "required_mw": required_mw,
            "marginal_price": price,
            "overlap_other_dr": overlap,
        }
    if not scenarios:
        raise ConfigError(f"{Path(path).name} has no data rows")
    weights = report["data_contract"]["event"]["scenario_weights"]
    if len(weights) != len(scenarios):
        raise ConfigError(
            f"{Path(path).name}: {len(scenarios)} scenarios but {len(weights)} weights"
        )
    event_date, start_text, end_text, start_min, end_min = event_meta
    try:
        dt.date.fromisoformat(event_date)
    except ValueError:
        raise ConfigError(f"event date is not ISO: {event_date!r}")
    duration_min = end_min - start_min
    if duration_min <= 0:
        raise ConfigError("event window must have positive duration")
    expected_min = report["event_duration_h"] * 60
    if abs(duration_min - expected_min) > 1e-9:
        raise ConfigError(
            f"event window is {duration_min} min but rules.demand_response.duration_h "
            f"implies {expected_min:g} min"
        )
    mtu = report["mtu_min"]
    if start_min % mtu or end_min % mtu:
        raise ConfigError("event window must align to the baseline sample interval")
    start_slot = start_min // mtu
    end_slot = end_min // mtu
    if end_slot > report["points_per_day"]:
        raise ConfigError("event window runs past the end of the day")
    window_start, window_end = report["window"]
    if start_min < window_start or end_min > window_end:
        report["warnings"].append(
            "事件窗口超出 rules.demand_response.window 的 D 级演示窗口；实际以邀约通知为准"
        )
    scenario_list = []
    for index, (name, types) in enumerate(scenarios.items()):
        missing = [control_type for control_type in CONTROL_TYPES if control_type not in types]
        if missing:
            raise ConfigError(f"scenario {name} is missing control types {missing}")
        scenario_list.append(
            {
                "name": name,
                "weight": float(weights[index]),
                "types": types,
            }
        )
    return {
        "date": event_date,
        "start": start_text,
        "end": end_text,
        "start_min": start_min,
        "end_min": end_min,
        "start_slot": start_slot,
        "end_slot": end_slot,
        "scenarios": scenario_list,
    }


def load_t1_loads(path, report, event):
    contract = report["data_contract"]["t1_loads"]
    rows = _read_rows(path)
    required_slots = range(event["start_slot"], event["end_slot"])
    by_date = _group_loads(
        rows,
        contract,
        report["resources"],
        report["points_per_day"],
        Path(path),
        required_slots=required_slots,
    )
    if event["date"] not in by_date:
        raise ConfigError(f"{Path(path).name} has no rows for event date {event['date']}")
    return by_date[event["date"]]


def load_t1_event(path, report, event, declared):
    contract = report["data_contract"]["t1_event"]
    rows = _read_rows(path)
    path_obj = Path(path)
    outcomes = {}
    for line_no, row in enumerate(rows, start=2):
        control_type = _cell(row, contract["control_type_field"], path_obj, line_no)
        if control_type not in CONTROL_TYPES:
            raise ConfigError(f"{path_obj.name} line {line_no}: unknown control_type {control_type!r}")
        if control_type in outcomes:
            raise ConfigError(f"{path_obj.name}: duplicate control_type {control_type}")
        event_date = _cell(row, "event_date", path_obj, line_no)
        start_text = _cell(row, "event_start", path_obj, line_no)
        end_text = _cell(row, "event_end", path_obj, line_no)
        if (event_date, start_text, end_text) != (event["date"], event["start"], event["end"]):
            raise ConfigError(
                f"{path_obj.name} line {line_no}: T+1 event does not match the invitation window"
            )
        price = _float_cell(row, contract["cleared_price_field"], path_obj, line_no)
        awarded = _float_cell(row, contract["awarded_mw_field"], path_obj, line_no)
        cap = report["caps"]
        if price < -1e-9:
            raise ConfigError(f"{path_obj.name} line {line_no}: cleared price must be non-negative")
        if cap is not None and price > cap + 1e-9:
            raise ConfigError(
                f"{path_obj.name} line {line_no}: cleared price {price} exceeds the rule cap {cap}"
            )
        if awarded < -1e-9 or awarded > declared[control_type] + 1e-9:
            raise ConfigError(
                f"{path_obj.name} line {line_no}: awarded {awarded} exceeds declared "
                f"{declared[control_type]}"
            )
        outcomes[control_type] = {"price": price, "awarded_mw": awarded}
    missing = [control_type for control_type in CONTROL_TYPES if control_type not in outcomes]
    if missing:
        raise ConfigError(f"{path_obj.name}: missing control types {missing}")
    return outcomes


def compute_baselines(history, event_date, report):
    """按「最近 N 个同类日」选样，再走通用 CBL（5 日、±25% 剔除、修正系数）。

    同类日 = 与事件日同为工作日或同为休息日（模块 §7.2「最近 5 个同类日」口径，
    D 级建模：上海正式同类日定义未核实）。
    """
    event_day = dt.date.fromisoformat(event_date)
    count = report["baseline"]["count"]
    dates = sorted(history, reverse=True)
    dates = [date for date in dates if date != event_date]
    same_type = [
        date
        for date in dates
        if (dt.date.fromisoformat(date).weekday() >= 5) == (event_day.weekday() >= 5)
    ]
    if len(same_type) < count:
        report["warnings"].append(
            f"history has {len(same_type)} same-type sample days, fewer than the configured {count}; "
            "baseline uses all available same-type days"
        )
    selected = same_type[:count]
    mtu_h = report["mtu_min"] / 60.0
    baselines = {}
    for resource in report["resources"]:
        if not resource["enabled"]:
            continue
        days = []
        for date in selected:
            curve = [history[date][slot][resource["id"]] for slot in range(report["points_per_day"])]
            days.append(
                {
                    "energy_mwh": sum(curve) * mtu_h,
                    "curve_mw": curve,
                }
            )
        baseline = cbl.customer_baseline(
            days,
            count=len(days),
            deviation=report["baseline"]["deviation"],
            adjustment=report["baseline"]["adjustment"],
        )
        baselines[resource["id"]] = baseline
    if baselines:
        dropped = {baseline["dropped"] for baseline in baselines.values()}
        if any(dropped):
            report["warnings"].append(
                "baseline screen dropped abnormal day(s): "
                + ", ".join(
                    f"{resource['name']} {baselines[resource['id']]['dropped']}"
                    for resource in report["resources"]
                    if resource["enabled"] and baselines[resource["id"]]["dropped"]
                )
            )
    return baselines, len(selected)


def build_bid(report):
    rows = []
    for control_type in CONTROL_TYPES:
        rows.append(
            {
                "control_type": control_type,
                "capability_mw": report["capability_by_type"][control_type],
                "bid_ratio": report["bid_ratio"][control_type],
                "declared_mw": report["declared_by_type"][control_type],
                "bid_price_cny_per_kwh": report["bid_price"][control_type],
                "bid_cap_cny_per_kwh": report["caps"],
                "headroom_mw": report["capability_by_type"][control_type]
                - report["declared_by_type"][control_type],
                "customer_share": report["share_by_type"][control_type],
            }
        )
    resource_rows = [
        {
            "id": resource["id"],
            "name": resource["name"],
            "control_type": resource["control_type"],
            "max_mw": resource["max_mw"],
            "adjustable_ratio": resource["adjustable_ratio"],
            "availability": resource["availability"],
            "duration_h": resource["duration_h"],
            "capability_mw": resource["capability_mw"],
            "energy_limit_mwh": resource["energy_limit_mwh"],
            "customer_share": resource["customer_share"],
            "enabled": resource["enabled"],
        }
        for resource in report["resources"]
    ]
    return {"by_type": rows, "resources": resource_rows}


def _weighted_cvar(values, confidence):
    tail = 1.0 - confidence
    if tail <= 0:
        return min(item["net_cny"] for item in values)
    remaining = tail
    total = 0.0
    for item in sorted(values, key=lambda entry: entry["net_cny"]):
        take = min(item["weight"], remaining)
        total += take * item["net_cny"]
        remaining -= take
        if remaining <= 1e-12:
            break
    return total / tail


def assess_scenarios(event, report):
    duration = report["event_duration_h"]
    variable_opex = report["contracts"]["variable_opex"]
    fixed_opex = report["contracts"]["fixed_opex"]
    outcomes = []
    for scenario in event["scenarios"]:
        rows = []
        total_gross = total_share = total_variable = 0.0
        for control_type in CONTROL_TYPES:
            quote = scenario["types"][control_type]
            required = quote["required_mw"]
            marginal = quote["marginal_price"]
            bid_price = report["bid_price"][control_type]
            clears = bid_price <= marginal + 1e-9
            awarded = min(report["declared_by_type"][control_type], required) if clears else 0.0
            gross = marginal * awarded * 1000.0 * duration
            share = report["share_by_type"][control_type]
            share_cost = gross * share
            variable = awarded * duration * variable_opex
            net = gross - share_cost - variable
            total_gross += gross
            total_share += share_cost
            total_variable += variable
            rows.append(
                {
                    "scenario": scenario["name"],
                    "weight": scenario["weight"],
                    "control_type": control_type,
                    "required_mw": required,
                    "marginal_price": marginal,
                    "bid_price": bid_price,
                    "clears": clears,
                    "awarded_mw": awarded,
                    "gross_cny": gross,
                    "customer_share_cny": share_cost,
                    "variable_opex_cny": variable,
                    "fixed_opex_cny": 0.0,
                    "net_cny": net,
                }
            )
        total_net = total_gross - total_share - total_variable - fixed_opex
        rows.append(
            {
                "scenario": scenario["name"],
                "weight": scenario["weight"],
                "control_type": "total",
                "required_mw": None,
                "marginal_price": None,
                "bid_price": None,
                "clears": None,
                "awarded_mw": sum(row["awarded_mw"] for row in rows),
                "gross_cny": total_gross,
                "customer_share_cny": total_share,
                "variable_opex_cny": total_variable,
                "fixed_opex_cny": fixed_opex,
                "net_cny": total_net,
            }
        )
        outcomes.append(rows)
    expected_gross = {
        control_type: sum(
            scenario["weight"] * row["gross_cny"]
            for scenario, rows in zip(event["scenarios"], outcomes)
            for row in rows
            if row["control_type"] == control_type
        )
        for control_type in CONTROL_TYPES
    }
    expected_award = {
        control_type: sum(
            scenario["weight"] * row["awarded_mw"]
            for scenario, rows in zip(event["scenarios"], outcomes)
            for row in rows
            if row["control_type"] == control_type
        )
        for control_type in CONTROL_TYPES
    }
    totals = [rows[-1] for rows in outcomes]
    expected_net = sum(item["weight"] * item["net_cny"] for item in totals)
    return {
        "rows": [row for rows in outcomes for row in rows],
        "totals": totals,
        "expected_gross": expected_gross,
        "expected_award": expected_award,
        "expected_net": expected_net,
        "cvar": _weighted_cvar(totals, report["cvar_confidence"]),
    }


def build_plan(scenario_result, report):
    duration = report["event_duration_h"]
    ratio = report["planned_delivery_ratio"]
    by_type = {}
    for control_type in CONTROL_TYPES:
        gross = scenario_result["expected_gross"][control_type] * ratio
        award = scenario_result["expected_award"][control_type]
        delivered = award * ratio
        price = gross / (delivered * 1000.0 * duration) if delivered > 1e-12 else 0.0
        share = report["share_by_type"][control_type]
        variable = delivered * duration * report["contracts"]["variable_opex"]
        by_type[control_type] = {
            "price": price,
            "awarded_mw": award,
            "delivered_mw": delivered,
            "gross_cny": gross,
            "customer_share_cny": gross * share,
            "variable_opex_cny": variable,
            "share": share,
        }
    gross_total = sum(item["gross_cny"] for item in by_type.values())
    share_total = sum(item["customer_share_cny"] for item in by_type.values())
    variable_total = sum(item["variable_opex_cny"] for item in by_type.values())
    net = gross_total - share_total - variable_total - report["contracts"]["fixed_opex"]
    return {
        "by_type": by_type,
        "gross_cny": gross_total,
        "customer_share_cny": share_total,
        "variable_opex_cny": variable_total,
        "fixed_opex_cny": report["contracts"]["fixed_opex"],
        "net_cny": net,
    }


def assess_actual(event, report, baselines, t1_loads, t1_event):
    duration = report["event_duration_h"]
    variable_opex = report["contracts"]["variable_opex"]
    fixed_opex = report["contracts"]["fixed_opex"]
    resources_by_type = {
        control_type: [
            resource
            for resource in report["resources"]
            if resource["enabled"] and resource["control_type"] == control_type
        ]
        for control_type in CONTROL_TYPES
    }
    slots = list(range(event["start_slot"], event["end_slot"]))
    detail = []
    by_type = {}
    for control_type in CONTROL_TYPES:
        outcome = t1_event[control_type]
        price = outcome["price"]
        awarded = outcome["awarded_mw"]
        shed_by_resource = {}
        for resource in resources_by_type[control_type]:
            baseline_curve = baselines[resource["id"]]["baseline_mw"]
            baseline_avg = sum(baseline_curve[slot] for slot in slots) / len(slots)
            actual_avg = sum(t1_loads[slot][resource["id"]] for slot in slots) / len(slots)
            shed_avg = max(0.0, baseline_avg - actual_avg)
            shed_energy = shed_avg * duration
            energy_limit = resource["energy_limit_mwh"]
            shed_by_resource[resource["id"]] = {
                "baseline_mw": baseline_avg,
                "actual_mw": actual_avg,
                "shed_mw": shed_avg,
                "shed_energy_mwh": shed_energy,
                "energy_limit_mwh": energy_limit,
                "energy_ok": shed_energy <= energy_limit + 1e-9,
            }
        total_shed = sum(item["shed_mw"] for item in shed_by_resource.values())
        response_rate = total_shed / awarded if awarded > 1e-12 else None
        valid = response_rate is not None and response_rate >= report["min_response_rate"] - 1e-12
        cap_shed = awarded * report["overshoot"]
        paid_shed = min(total_shed, cap_shed) if valid else 0.0
        delivery_ratio = total_shed / awarded if awarded > 1e-12 else None
        share = report["share_by_type"][control_type]
        if delivery_ratio is not None and delivery_ratio < report["contracts"]["threshold"] - 1e-12:
            share += report["contracts"]["extra_share"]
        gross = price * paid_shed * 1000.0 * duration
        variable = paid_shed * duration * variable_opex
        by_type[control_type] = {
            "price": price,
            "awarded_mw": awarded,
            "shed_mw": total_shed,
            "response_rate": response_rate,
            "valid": valid,
            "paid_shed_mw": paid_shed,
            "capped": total_shed > cap_shed + 1e-9,
            "delivery_ratio": delivery_ratio,
            "share": share,
            "gross_cny": gross,
            "customer_share_cny": gross * share,
            "variable_opex_cny": variable,
        }
        paid_ratio = paid_shed / total_shed if total_shed > 1e-12 else 0.0
        for resource in resources_by_type[control_type]:
            record = shed_by_resource[resource["id"]]
            detail.append(
                {
                    "control_type": control_type,
                    "resource_id": resource["id"],
                    "resource_name": resource["name"],
                    "baseline_mw": record["baseline_mw"],
                    "actual_mw": record["actual_mw"],
                    "shed_mw": record["shed_mw"],
                    "shed_energy_mwh": record["shed_energy_mwh"],
                    "energy_limit_mwh": record["energy_limit_mwh"],
                    "energy_ok": record["energy_ok"],
                    "paid_shed_mw": record["shed_mw"] * paid_ratio,
                    "paid_energy_mwh": record["shed_mw"] * paid_ratio * duration,
                    "cleared_price": price,
                    "gross_cny": price * record["shed_mw"] * paid_ratio * 1000.0 * duration,
                }
            )
    gross_total = sum(item["gross_cny"] for item in by_type.values())
    share_total = sum(item["customer_share_cny"] for item in by_type.values())
    variable_total = sum(item["variable_opex_cny"] for item in by_type.values())
    net = gross_total - share_total - variable_total - fixed_opex
    if not all(item["valid"] for item in by_type.values()):
        report["warnings"].append(
            "至少一个控制类型的响应率低于有效门槛；本包按 0 计量并保留原始响应量"
        )
    return {
        "by_type": by_type,
        "detail": detail,
        "gross_cny": gross_total,
        "customer_share_cny": share_total,
        "variable_opex_cny": variable_total,
        "fixed_opex_cny": fixed_opex,
        "net_cny": net,
    }


def build_bridge(plan, actual, report):
    duration = report["event_duration_h"]
    buckets = []
    for control_type in CONTROL_TYPES:
        plan_type = plan["by_type"][control_type]
        actual_type = actual["by_type"][control_type]
        keep = 1.0 - plan_type["share"]
        gross_price = actual_type["price"] * plan_type["delivered_mw"] * 1000.0 * duration
        gross_award = (
            actual_type["price"]
            * actual_type["awarded_mw"]
            * report["planned_delivery_ratio"]
            * 1000.0
            * duration
        )
        gross_execution = actual_type["price"] * actual_type["shed_mw"] * 1000.0 * duration
        gross_capped = actual_type["price"] * actual_type["paid_shed_mw"] * 1000.0 * duration
        buckets.extend(
            [
                {
                    "item": "出清价差",
                    "category": "价格",
                    "owner": "市场",
                    "control_type": control_type,
                    "amount": (gross_price - plan_type["gross_cny"]) * keep,
                },
                {
                    "item": "中标量差",
                    "category": "数量",
                    "owner": "申报",
                    "control_type": control_type,
                    "amount": (gross_award - gross_price) * keep,
                },
                {
                    "item": "执行率差",
                    "category": "执行",
                    "owner": "资源",
                    "control_type": control_type,
                    "amount": (gross_execution - gross_award) * keep,
                },
                {
                    "item": "超额封顶或无效扣减",
                    "category": "规则",
                    "owner": "规则",
                    "control_type": control_type,
                    "amount": (gross_capped - gross_execution) * keep,
                },
                {
                    "item": "客户分成与未达标补偿",
                    "category": "合同",
                    "owner": "客户",
                    "control_type": control_type,
                    "amount": -(actual_type["share"] - plan_type["share"]) * gross_capped,
                },
            ]
        )
    opex_delta = (
        actual["variable_opex_cny"]
        + actual["fixed_opex_cny"]
        - plan["variable_opex_cny"]
        - plan["fixed_opex_cny"]
    )
    buckets.append(
        {
            "item": "运营成本",
            "category": "成本",
            "owner": "聚合商",
            "control_type": "total",
            "amount": -opex_delta,
        }
    )
    total_delta = actual["net_cny"] - plan["net_cny"]
    bucket_sum = sum(item["amount"] for item in buckets)
    return {
        "plan_net_cny": plan["net_cny"],
        "actual_net_cny": actual["net_cny"],
        "delta_cny": total_delta,
        "identity_gap": total_delta - bucket_sum,
        "buckets": buckets,
    }


def _write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _money(value):
    return f"{value:,.0f}"


def _signed(value):
    return f"{value:+,.0f}"


def _compliance(event, report, bid, actual, baselines):
    items = []
    cap = report["caps"]
    for control_type in CONTROL_TYPES:
        price = report["bid_price"][control_type]
        if cap is None:
            items.append(
                {
                    "item": f"{control_type} 报价上限校验",
                    "status": "warn",
                    "detail": "上海官方单价与上限未核实，报价按 D 级演示价处理，不构成报价依据",
                }
            )
        else:
            items.append(
                {
                    "item": f"{control_type} 报价不超上限",
                    "status": "pass" if price <= cap + 1e-9 else "fail",
                    "detail": f"{price:.2f} ≤ {cap:.2f} 元/kWh",
                }
            )
        declared = report["declared_by_type"][control_type]
        capability = report["capability_by_type"][control_type]
        items.append(
            {
                "item": f"{control_type} 申报不超可调能力",
                "status": "pass" if declared <= capability + 1e-9 else "fail",
                "detail": f"{declared:.2f} ≤ {capability:.2f} MW",
            }
        )
    qualification = report["qualification"]
    items.append(
        {
            "item": "专项实测规模 ≥ 申报值 20%（D 级演示假设）",
            "status": "pass" if qualification["scale_ratio"] >= qualification["min_scale_ratio"] - 1e-9 else "fail",
            "detail": f"{qualification['test_scale_mw']:.2f} / {qualification['declared_at_test_mw']:.2f} = {qualification['scale_ratio']:.1%}",
        }
    )
    window_start, window_end = report["dispatchable_window"]
    if event["start_min"] >= window_start and event["end_min"] <= window_end:
        status = "pass"
    else:
        status = "warn"
    items.append(
        {
            "item": "事件落在数据中心 D 级可调窗口",
            "status": status,
            "detail": f"{event['start']}-{event['end']} ∈ 可调窗口（D 级演示）",
        }
    )
    excluded = [resource["name"] for resource in report["resources"] if not resource["enabled"]]
    items.append(
        {
            "item": "同一时段不重复参与 DR",
            "status": "pass" if not excluded else "warn",
            "detail": "无重复参与标记" if not excluded else f"已排除：{', '.join(excluded)}",
        }
    )
    if actual is not None:
        duration = report["event_duration_h"]
        for control_type in CONTROL_TYPES:
            item = actual["by_type"][control_type]
            if item["response_rate"] is None:
                items.append(
                    {
                        "item": f"{control_type} 响应有效性",
                        "status": "warn",
                        "detail": "未中标，不做响应认定",
                    }
                )
            else:
                items.append(
                    {
                        "item": f"{control_type} 响应率 ≥ {report['min_response_rate']:.0%}（D 级演示门槛）",
                        "status": "pass" if item["valid"] else "fail",
                        "detail": f"{item['response_rate']:.1%}",
                    }
                )
            over_limit = [
                record["resource_name"]
                for record in actual["detail"]
                if record["control_type"] == control_type and not record["energy_ok"]
            ]
            items.append(
                {
                    "item": f"{control_type} 响应电量不超资源持续时间约束",
                    "status": "fail" if over_limit else "pass",
                    "detail": (
                        f"超约束：{', '.join(over_limit)}"
                        if over_limit
                        else f"按 {duration:.2f} h 事件时长与各资源 duration_h 复核"
                    ),
                }
            )
    items.append(
        {
            "item": "制冷可调与 PUE 耦合提示",
            "status": "warn",
            "detail": (
                f"IT 额定 {report['asset']['it_load_rated_mw']:.0f} MW、设计 PUE "
                f"{report['asset']['pue_design']:.2f}：削制冷受 IT 发热与进风温度约束，"
                "实际幅度按冷机性能曲线与蓄冷量核"
            ),
        }
    )
    return items


def write_review(path, config, report, event, baselines, bid, scenarios, plan, actual, bridge, fingerprint, compliance):
    meta = config["meta"]
    lines = []
    lines.append("# 上海独立数据中心需求响应复核表（D 级合成样板）")
    lines.append("")
    lines.append(f"- 实例：`{meta['instance_id']}`")
    lines.append(f"- 主体：{meta['entity_type']}")
    lines.append(f"- 规则版本：{meta['rule_version']}")
    lines.append(f"- 邀约：{event['date']} {event['start']}–{event['end']}（{report['event_duration_h']:.2f} h，D 级演示窗口）")
    lines.append(f"- 风格档：`{report['profile_id']}`，指纹 `{fingerprint}`")
    lines.append(f"- 数据口径：{meta['scope']}")
    lines.append("")
    lines.append("## 1. 来源与警告")
    lines.append("")
    lines.append("| 块 | 级别 | 来源 |")
    lines.append("|---|---|---|")
    for item in report["provenance"]:
        lines.append(f"| {item['block']} | {item['grade']} | {item['source']} |")
    lines.append("")
    if report["warnings"]:
        lines.append("**警告**")
        lines.append("")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")
    lines.append("## 2. 申报")
    lines.append("")
    lines.append("| 控制类型 | 可调能力 MW | 申报比例 | 申报 MW | 报价 元/kWh | 官方上限 | 客户分成 |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in bid["by_type"]:
        cap_text = "待核实" if row["bid_cap_cny_per_kwh"] is None else f"{row['bid_cap_cny_per_kwh']:.2f}"
        lines.append(
            f"| {row['control_type']} | {row['capability_mw']:.2f} | {row['bid_ratio']:.0%} | "
            f"{row['declared_mw']:.2f} | {row['bid_price_cny_per_kwh']:.2f} | "
            f"{cap_text} | {row['customer_share']:.1%} |"
        )
    lines.append("")
    lines.append("| 资源 | 类型 | 额定 MW | 可调比例 | 可用率 | 持续 h | 可调能力 MW | 电量上限 MWh | 是否计入 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in bid["resources"]:
        lines.append(
            f"| {row['name']} | {row['control_type']} | {row['max_mw']:.1f} | "
            f"{row['adjustable_ratio']:.0%} | {row['availability']:.0%} | {row['duration_h']:.1f} | "
            f"{row['capability_mw']:.2f} | {row['energy_limit_mwh']:.2f} | {'是' if row['enabled'] else '否'} |"
        )
    lines.append("")
    lines.append("## 3. 情景出清")
    lines.append("")
    lines.append("情景表按满额交付计算；计划净收益再乘计划执行率，作为差异桥基线。")
    lines.append("")
    lines.append("| 情景 | 权重 | 类型 | 需求 MW | 边际价 | 报价 | 出清 | 中标 MW | 毛收入 元 | 净收益 元 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in scenarios["rows"]:
        if row["control_type"] == "total":
            continue
        lines.append(
            f"| {row['scenario']} | {row['weight']:.0%} | {row['control_type']} | "
            f"{row['required_mw']:.1f} | {row['marginal_price']:.2f} | {row['bid_price']:.2f} | "
            f"{'是' if row['clears'] else '否'} | {row['awarded_mw']:.2f} | "
            f"{_money(row['gross_cny'])} | {_money(row['net_cny'])} |"
        )
    lines.append("")
    lines.append("| 情景 | 权重 | 中标合计 MW | 毛收入 元 | 客户分成 元 | 变动成本 元 | 固定成本 元 | 净收益 元 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in scenarios["totals"]:
        lines.append(
            f"| {row['scenario']} | {row['weight']:.0%} | {row['awarded_mw']:.2f} | "
            f"{_money(row['gross_cny'])} | {_money(row['customer_share_cny'])} | "
            f"{_money(row['variable_opex_cny'])} | {_money(row['fixed_opex_cny'])} | "
            f"{_money(row['net_cny'])} |"
        )
    lines.append("")
    lines.append(
        f"期望净收益 {_money(scenarios['expected_net'])} 元；"
        f"CVaR{report['cvar_confidence']:.0%} {_money(scenarios['cvar'])} 元。"
    )
    lines.append("")
    lines.append("## 4. T+1 响应认定")
    lines.append("")
    if actual is None or bridge is None:
        lines.append("未提供 T+1 计量或出清结果，本次只出申报与情景表。")
        lines.append("")
    else:
        lines.append("| 类型 | 基线均值 MW | 实际均值 MW | 响应量 MW | 中标 MW | 响应率 | 封顶 MW | 计量 MW | 毛收入 元 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for control_type in CONTROL_TYPES:
            item = actual["by_type"][control_type]
            cap_shed = item["awarded_mw"] * report["overshoot"]
            rate = "—" if item["response_rate"] is None else f"{item['response_rate']:.1%}"
            lines.append(
                f"| {control_type} | {sum(record['baseline_mw'] for record in actual['detail'] if record['control_type'] == control_type):.2f} | "
                f"{sum(record['actual_mw'] for record in actual['detail'] if record['control_type'] == control_type):.2f} | "
                f"{item['shed_mw']:.2f} | {item['awarded_mw']:.2f} | {rate} | "
                f"{cap_shed:.2f} | {item['paid_shed_mw']:.2f} | {_money(item['gross_cny'])} |"
            )
        lines.append("")
        lines.append("| 类型 | 资源 | 基线 MW | 实际 MW | 响应 MW | 响应电量 MWh | 电量上限 MWh | 分摊计量 MW | 计量电量 MWh | 毛收入 元 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for record in actual["detail"]:
            lines.append(
                f"| {record['control_type']} | {record['resource_name']} | {record['baseline_mw']:.2f} | "
                f"{record['actual_mw']:.2f} | {record['shed_mw']:.2f} | {record['shed_energy_mwh']:.2f} | "
                f"{record['energy_limit_mwh']:.2f} | {record['paid_shed_mw']:.2f} | "
                f"{record['paid_energy_mwh']:.2f} | {_money(record['gross_cny'])} |"
            )
        lines.append("")
        lines.append(
            f"实际净收益 {_money(actual['net_cny'])} 元；计划净收益 {_money(plan['net_cny'])} 元；"
            f"差异 {_signed(bridge['delta_cny'])} 元。"
        )
        lines.append("")
        lines.append("## 5. 差异桥")
        lines.append("")
        lines.append("| 科目 | 类型 | 责任方 | 金额 元 |")
        lines.append("|---|---|---|---|")
        for bucket in bridge["buckets"]:
            lines.append(
                f"| {bucket['item']} | {bucket['control_type']} | {bucket['owner']} | "
                f"{_signed(bucket['amount'])} |"
            )
        lines.append("")
        lines.append(
            f"恒等式残差 {bridge['identity_gap']:.2e} 元（目标 < 1e-6）。"
        )
        lines.append("")
    lines.append("## 6. 合规清单")
    lines.append("")
    lines.append("| 检查项 | 结果 | 说明 |")
    lines.append("|---|---|---|")
    for item in compliance:
        lines.append(f"| {item['item']} | {item['status']} | {item['detail']} |")
    lines.append("")
    lines.append("## 7. 读法")
    lines.append("")
    lines.append("- 可调能力 = 额定 × 可调比例 × 可用率；申报值 = 可调能力 × 申报比例并向下取整；实际响应 = 基线 − 实际负荷，三层不可混用。")
    lines.append("- 功率能力 ≠ 电量：UPS 按 0.5 h 备电窗口建模，1 h 事件内平均响应只有一半；每个资源有 duration_h 与电量上限，超约束会在合规清单亮红灯。")
    lines.append("- 激励 = 结算单价 × 计量响应电量；超额部分按 1.2 倍封顶（D 级演示），有效性不通过不计费（D 级演示）。上海官方单价未核实（settlement.unit_price=null）。")
    lines.append("- 基线按通用 CBL 口径（5 同类日、剔除日电量偏离约 ±25%、乘修正系数）演示；上海正式基线算法未核实，结算前须以省级原文/协议为准。")
    lines.append("- 407 号「1+5」目标（数据中心 60/15 万 kW）与 2025-08 调用 116.27 万 kW 是全市口径（A / B-C），不是本数据中心的能力或收益。")
    lines.append("- 差异桥按“价格 → 中标 → 执行 → 封顶 → 分成 → 成本”顺序做逐项替换，残差应接近 0；残差不为 0 说明口径或数据有缺口。")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, history_path, event_path, t1_loads_path, t1_event_path, out_dir):
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{instance_path.name} is not valid JSON: {exc}") from exc
    report = validate_instance(config)
    history = load_history(history_path, report)
    event = load_event(event_path, report)
    if event["date"] in history:
        raise ConfigError("event date must not appear in the baseline history sample")
    baselines, sample_days = compute_baselines(history, event["date"], report)
    for resource in report["resources"]:
        if not resource["enabled"]:
            continue
        baseline = baselines[resource["id"]]
        report["warnings"].append(
            f"基线 {resource['name']}：候选 {baseline['candidates']} 日，保留 {baseline['kept']} 日，"
            f"剔除 {baseline['dropped']} 日"
        )
    if t1_loads_path is None or t1_event_path is None:
        t1_loads = None
        t1_event = None
    else:
        t1_loads = load_t1_loads(t1_loads_path, report, event)
        t1_event = load_t1_event(t1_event_path, report, event, report["declared_by_type"])
    bid = build_bid(report)
    scenarios = assess_scenarios(event, report)
    plan = build_plan(scenarios, report)
    actual = None
    bridge = None
    if t1_loads is not None:
        actual = assess_actual(event, report, baselines, t1_loads, t1_event)
        bridge = build_bridge(plan, actual, report)
    compliance = _compliance(event, report, bid, actual, baselines)
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        out_dir / "bid_sheet.csv",
        bid["by_type"],
        [
            "control_type",
            "capability_mw",
            "bid_ratio",
            "declared_mw",
            "bid_price_cny_per_kwh",
            "bid_cap_cny_per_kwh",
            "headroom_mw",
            "customer_share",
        ],
    )
    _write_csv(
        out_dir / "capability.csv",
        bid["resources"],
        [
            "id",
            "name",
            "control_type",
            "max_mw",
            "adjustable_ratio",
            "availability",
            "duration_h",
            "capability_mw",
            "energy_limit_mwh",
            "customer_share",
            "enabled",
        ],
    )
    _write_csv(
        out_dir / "scenario_table.csv",
        scenarios["rows"],
        [
            "scenario",
            "weight",
            "control_type",
            "required_mw",
            "marginal_price",
            "bid_price",
            "clears",
            "awarded_mw",
            "gross_cny",
            "customer_share_cny",
            "variable_opex_cny",
            "fixed_opex_cny",
            "net_cny",
        ],
    )
    if actual is not None:
        _write_csv(
            out_dir / "delivery_detail.csv",
            actual["detail"],
            [
                "control_type",
                "resource_id",
                "resource_name",
                "baseline_mw",
                "actual_mw",
                "shed_mw",
                "shed_energy_mwh",
                "energy_limit_mwh",
                "energy_ok",
                "paid_shed_mw",
                "paid_energy_mwh",
                "cleared_price",
                "gross_cny",
            ],
        )
        _write_csv(
            out_dir / "bridge.csv",
            bridge["buckets"],
            ["item", "category", "owner", "control_type", "amount"],
        )
        (out_dir / "bridge.json").write_text(
            json.dumps(
                {
                    "plan_net_cny": bridge["plan_net_cny"],
                    "actual_net_cny": bridge["actual_net_cny"],
                    "delta_cny": bridge["delta_cny"],
                    "identity_gap": bridge["identity_gap"],
                    "buckets": bridge["buckets"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "event": {
            "date": event["date"],
            "start": event["start"],
            "end": event["end"],
            "duration_h": report["event_duration_h"],
        },
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "asset": config["asset"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "capability": {
            "by_type": report["capability_by_type"],
            "declared_by_type": report["declared_by_type"],
            "share_by_type": report["share_by_type"],
            "resources": bid["resources"],
        },
        "bid": bid["by_type"],
        "baseline": {
            resource["id"]: {
                "name": resource["name"],
                "candidates": baselines[resource["id"]]["candidates"],
                "kept": baselines[resource["id"]]["kept"],
                "dropped": baselines[resource["id"]]["dropped"],
                "mean_energy_mwh": baselines[resource["id"]]["mean_energy_mwh"],
            }
            for resource in report["resources"]
            if resource["enabled"]
        },
        "baseline_sample_days": sample_days,
        "scenarios": scenarios["rows"],
        "expected": {
            "gross_cny": sum(scenarios["expected_gross"].values()),
            "net_cny": scenarios["expected_net"],
            "cvar_cny": scenarios["cvar"],
        },
        "plan": plan,
        "actual": actual,
        "bridge": bridge,
        "compliance": compliance,
        "warnings": report["warnings"],
        "files": {
            "bid_sheet": "bid_sheet.csv",
            "capability": "capability.csv",
            "scenario_table": "scenario_table.csv",
            "delivery_detail": "delivery_detail.csv" if actual is not None else None,
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
        event,
        baselines,
        bid,
        scenarios,
        plan,
        actual,
        bridge,
        fingerprint,
        compliance,
    )
    return {
        "config": config,
        "report": report,
        "history": history,
        "event": event,
        "baselines": baselines,
        "bid": bid,
        "scenarios": scenarios,
        "plan": plan,
        "actual": actual,
        "bridge": bridge,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shanghai datacenter VPP instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--history", help="baseline history CSV")
    parser.add_argument("--event", help="invitation scenario CSV")
    parser.add_argument("--t1-loads", dest="t1_loads", help="T+1 metered loads CSV")
    parser.add_argument("--t1-event", dest="t1_event", help="T+1 clearing outcome CSV")
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
        if not args.history or not args.event:
            print("必须提供 --history 与 --event，或使用 --demo", file=sys.stderr)
            return 1
        if (args.t1_loads is None) != (args.t1_event is None):
            print("--t1-loads 与 --t1-event 必须同时提供或同时省略", file=sys.stderr)
            return 1
        history_path = Path(args.history)
        event_path = Path(args.event)
        t1_loads_path = Path(args.t1_loads) if args.t1_loads else None
        t1_event_path = Path(args.t1_event) if args.t1_event else None
        out_dir = Path(args.out)

    try:
        result = run_instance(
            args.instance,
            history_path,
            event_path,
            t1_loads_path,
            t1_event_path,
            out_dir,
        )
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(f"实例：{summary['instance_id']} / 邀约 {summary['event']['date']} {summary['event']['start']}-{summary['event']['end']}")
    for row in summary["bid"]:
        cap_text = "待核实" if row["bid_cap_cny_per_kwh"] is None else f"{row['bid_cap_cny_per_kwh']:.2f}"
        print(
            f"申报 {row['control_type']}: 能力 {row['capability_mw']:.2f} MW，"
            f"申报 {row['declared_mw']:.2f} MW，报价 {row['bid_price_cny_per_kwh']:.2f} 元/kWh（上限 {cap_text}）"
        )
    print(
        f"情景：期望净收益 {summary['expected']['net_cny']:,.0f} 元，"
        f"CVaR {summary['expected']['cvar_cny']:,.0f} 元"
    )
    if result["bridge"] is not None:
        print(
            f"差异桥：计划 {result['bridge']['plan_net_cny']:,.0f} → "
            f"实际 {result['bridge']['actual_net_cny']:,.0f}，"
            f"差异 {result['bridge']['delta_cny']:+,.0f} 元，残差 {result['bridge']['identity_gap']:.2e}"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
