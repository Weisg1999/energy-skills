#!/usr/bin/env python3
"""Guangdong retail instance runner: validate, price, stress, and bridge.

The instance is a configuration package, not a forecast. All demo data are
grade-D synthetic and correspond to no real retailer, customer or contract.

Commands:
    python run.py --check-config
    python run.py --demo
    python run.py --d1 data/d1_demo.csv --t1 data/t1_demo.csv --out out/run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULE_BLOCKS = ("spot", "retail_market", "deviation", "guarantee", "settlement")
PACKAGE_TYPES = {"fixed", "tou", "market_linked", "floor_plus_float", "service_fee"}
GRADE_RE = re.compile(r"^[ABCD](/[ABCD])*$")


class ConfigError(ValueError):
    """The instance configuration is invalid."""


class InputError(ValueError):
    """A D-1 or T+1 input file is invalid."""


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _require(block, key, where, errors):
    if not isinstance(block, dict) or key not in block or block[key] in (None, ""):
        errors.append(f"{where}.{key} 缺失")
        return None
    return block[key]


def _number(block, key, where, errors, minimum=None, maximum=None):
    value = _require(block, key, where, errors)
    if value is None:
        return None
    if not _is_number(value):
        errors.append(f"{where}.{key} 必须是数字")
        return None
    value = float(value)
    if minimum is not None and value < minimum:
        errors.append(f"{where}.{key} 不能小于 {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{where}.{key} 不能大于 {maximum}")
    return value


def _non_empty_list(value, where, errors):
    if not isinstance(value, list) or not value:
        errors.append(f"{where} 必须是非空数组")
        return []
    return value


def validate_instance(config):
    """Validate the six blocks and return a report; raise ConfigError on errors."""
    errors = []
    warnings = []

    if not isinstance(config, dict):
        raise ConfigError("实例配置必须是 JSON 对象")

    meta = config.get("meta")
    if not isinstance(meta, dict):
        raise ConfigError("缺少 meta 块")
    for key in ("instance_id", "province", "market", "entity_type", "rule_version", "data_cutoff", "grade", "scope", "units", "disclaimer"):
        _require(meta, key, "meta", errors)
    if isinstance(meta, dict) and isinstance(meta.get("units"), dict):
        units = meta["units"]
        _require(units, "price", "meta.units", errors)
        _require(units, "energy", "meta.units", errors)
        if str(units.get("price", "")).replace(" ", "").upper() != "CNY/MWH":
            errors.append("meta.units.price 必须是 CNY/MWh")
        if str(units.get("energy", "")).replace(" ", "").upper() != "MWH":
            errors.append("meta.units.energy 必须是 MWh")

    rules = config.get("rules")
    if not isinstance(rules, dict):
        errors.append("缺少 rules 块")
        rules = {}
    for name in RULE_BLOCKS:
        block = rules.get(name)
        if not isinstance(block, dict):
            errors.append(f"rules.{name} 缺失")
            continue
        grade = _require(block, "grade", f"rules.{name}", errors)
        source = _require(block, "source", f"rules.{name}", errors)
        if grade is not None and not GRADE_RE.match(str(grade)):
            errors.append(f"rules.{name}.grade 必须是 A/B/C/D 或其组合")
        if source is not None and not str(source).strip():
            errors.append(f"rules.{name}.source 不能为空")

    spot = rules.get("spot", {}) if isinstance(rules, dict) else {}
    if isinstance(spot, dict):
        mtu = _number(spot, "market_time_unit_min", "rules.spot", errors, minimum=1)
        points = _number(spot, "points_per_day", "rules.spot", errors, minimum=1)
        clear_floor = _number(spot, "clear_floor_cny_per_mwh", "rules.spot", errors)
        clear_cap = _number(spot, "clear_cap_cny_per_mwh", "rules.spot", errors)
        declare_floor = _number(spot, "declare_floor_cny_per_mwh", "rules.spot", errors)
        if mtu is not None and points is not None:
            expected_points = 24.0 * 60.0 / mtu
            if abs(points - expected_points) > 1e-9:
                errors.append("rules.spot.points_per_day 必须等于 24×60 / market_time_unit_min")
        if clear_floor is not None and clear_cap is not None and clear_floor >= clear_cap:
            errors.append("rules.spot.clear_floor_cny_per_mwh 必须小于 clear_cap_cny_per_mwh")
        if clear_floor is not None and declare_floor is not None and declare_floor < clear_floor:
            errors.append("rules.spot.declare_floor_cny_per_mwh 不能低于 clear_floor_cny_per_mwh")
    else:
        mtu = points = clear_floor = clear_cap = None

    retail_market = rules.get("retail_market", {}) if isinstance(rules, dict) else {}
    if isinstance(retail_market, dict):
        packages = retail_market.get("package_types")
        if packages is not None:
            if not isinstance(packages, list) or not packages:
                errors.append("rules.retail_market.package_types 必须是非空数组")
            else:
                unknown = [item for item in packages if item not in PACKAGE_TYPES]
                if unknown:
                    errors.append(f"rules.retail_market.package_types 含未知套餐类型：{unknown}")
        _number(retail_market, "retail_avg_2026h1_cny_per_mwh", "rules.retail_market", errors, minimum=0)
        _number(retail_market, "margin_2026h1_cny_per_mwh", "rules.retail_market", errors)

    deviation_rule = rules.get("deviation", {}) if isinstance(rules, dict) else {}
    if isinstance(deviation_rule, dict):
        _require(deviation_rule, "guangdong_status", "rules.deviation", errors)
        _require(deviation_rule, "contract_basis", "rules.deviation", errors)
        status = str(deviation_rule.get("guangdong_status", ""))
        if "未核到" in status or "C 级" in status:
            warnings.append("广东偏差考核未核到现行正式规则；本包按合同约定测算，不把 ±3%/±5% 当作省统一规则")

    guarantee_rule = rules.get("guarantee", {}) if isinstance(rules, dict) else {}
    if isinstance(guarantee_rule, dict):
        current = guarantee_rule.get("current")
        draft = guarantee_rule.get("draft_2026_09_04")
        if not isinstance(current, dict):
            errors.append("rules.guarantee.current 缺失")
        else:
            _require(current, "formula", "rules.guarantee.current", errors)
            _require(current, "document", "rules.guarantee.current", errors)
        if isinstance(draft, dict) and draft.get("effective") is True:
            errors.append("rules.guarantee.draft_2026_09_04 是草案，effective 不能为 true")
        if isinstance(draft, dict) and draft.get("effective") is False:
            warnings.append("2026-09-04 售电办法修订稿是草案，本包未按草案保函公式测算")

    settlement = rules.get("settlement", {}) if isinstance(rules, dict) else {}
    if isinstance(settlement, dict):
        _require(settlement, "timeline", "rules.settlement", errors)
        _require(settlement, "document", "rules.settlement", errors)

    portfolio = config.get("portfolio")
    if not isinstance(portfolio, dict):
        errors.append("缺少 portfolio 块")
        portfolio = {}
    segments = _non_empty_list(portfolio.get("segments"), "portfolio.segments", errors)
    share_sum = 0.0
    names = []
    for index, segment in enumerate(segments):
        where = f"portfolio.segments[{index}]"
        if not isinstance(segment, dict):
            errors.append(f"{where} 必须是对象")
            continue
        name = _require(segment, "name", where, errors)
        if name is not None:
            if name in names:
                errors.append(f"{where}.name 重复：{name}")
            names.append(name)
        package_type = _require(segment, "package_type", where, errors)
        if package_type is not None and package_type not in PACKAGE_TYPES:
            errors.append(f"{where}.package_type 未知：{package_type}")
        share = _number(segment, "share", where, errors, minimum=0.0, maximum=1.0)
        if share is not None:
            share_sum += share
        _number(segment, "forecast_sigma_pct", where, errors, minimum=0.0, maximum=1.0)
        _number(segment, "opex_cny_per_mwh", where, errors, minimum=0.0)
        if package_type == "fixed":
            _number(segment, "retail_price_cny_per_mwh", where, errors, minimum=0.0)
        elif package_type == "market_linked":
            _number(segment, "pass_through", where, errors, minimum=0.0)
            _number(segment, "adder_cny_per_mwh", where, errors)
            floor = _number(segment, "floor_cny_per_mwh", where, errors)
            cap = _number(segment, "cap_cny_per_mwh", where, errors)
            if floor is not None and cap is not None and floor > cap:
                errors.append(f"{where}.floor_cny_per_mwh 不能大于 cap_cny_per_mwh")
        elif package_type in {"tou", "floor_plus_float", "service_fee"}:
            errors.append(f"{where}.package_type={package_type} 在 v1 运行器中尚未实现，请先改用 fixed 或 linked")
    if segments and abs(share_sum - 1.0) > 1e-9:
        errors.append(f"portfolio.segments 的 share 之和必须为 1，当前为 {share_sum:.6f}")

    _number(portfolio, "annual_energy_mwh", "portfolio", errors, minimum=0.0)
    _number(portfolio, "fixed_cost_cny_per_day", "portfolio", errors, minimum=0.0)

    deviation_terms = portfolio.get("deviation_terms")
    if not isinstance(deviation_terms, dict):
        errors.append("portfolio.deviation_terms 缺失")
    else:
        _number(deviation_terms, "tolerance_share", "portfolio.deviation_terms", errors, minimum=0.0, maximum=1.0)
        _number(deviation_terms, "penalty_cny_per_mwh", "portfolio.deviation_terms", errors, minimum=0.0)
        _require(deviation_terms, "basis", "portfolio.deviation_terms", errors)

    guarantee = portfolio.get("guarantee")
    if not isinstance(guarantee, dict):
        errors.append("portfolio.guarantee 缺失")
    else:
        amount = _number(guarantee, "amount_cny", "portfolio.guarantee", errors, minimum=0.0)
        rate = _number(guarantee, "annual_funding_rate", "portfolio.guarantee", errors, minimum=0.0)
        annual = _number(guarantee, "annual_wholesale_mwh", "portfolio.guarantee", errors, minimum=0.0)
        peak = _number(guarantee, "peak_two_month_mwh", "portfolio.guarantee", errors, minimum=0.0)
        _require(guarantee, "basis", "portfolio.guarantee", errors)
        if amount is not None and annual is not None and peak is not None:
            required = max(annual * 8.0, peak * 50.0)
            tolerance = max(1.0, 0.01 * required)
            if abs(amount - required) > tolerance:
                warnings.append(
                    f"portfolio.guarantee.amount_cny={amount:,.0f} 与 1595 号公式值 {required:,.0f} 不一致；"
                    "请说明是否改用保险/现金或历史口径"
                )
        if rate is not None and rate > 0.05:
            warnings.append("portfolio.guarantee.annual_funding_rate 高于 5%，请确认不是年化百分数误填")

    policy = config.get("policy")
    if not isinstance(policy, dict):
        errors.append("缺少 policy 块")
        policy = {}
    _require(policy, "profile_id", "policy", errors)
    _number(policy, "price_reference_quantile", "policy", errors, minimum=0.0, maximum=1.0)
    _number(policy, "risk_buffer_cny_per_mwh", "policy", errors, minimum=0.0)
    _number(policy, "target_margin_cny_per_mwh", "policy", errors)
    multipliers = _non_empty_list(policy.get("stress_spot_multipliers"), "policy.stress_spot_multipliers", errors)
    for value in multipliers:
        if not _is_number(value) or float(value) <= 0:
            errors.append("policy.stress_spot_multipliers 必须全部为正数")
            break
    sigmas = _non_empty_list(policy.get("stress_sigma_pcts"), "policy.stress_sigma_pcts", errors)
    for value in sigmas:
        if not _is_number(value) or not 0.0 < float(value) < 1.0:
            errors.append("policy.stress_sigma_pcts 必须在 (0, 1) 内")
            break
    top_slots = policy.get("review_top_slots")
    if top_slots is not None and (not isinstance(top_slots, int) or top_slots < 0):
        errors.append("policy.review_top_slots 必须是非负整数")

    contracts = config.get("contracts")
    if contracts is None:
        contracts = []
    if not isinstance(contracts, list):
        errors.append("contracts 必须是数组")
        contracts = []
    if len(contracts) > 1:
        errors.append("v1 运行器只支持一份中长期合约；多合约分段请拆实例")
    for index, contract in enumerate(contracts):
        where = f"contracts[{index}]"
        if not isinstance(contract, dict):
            errors.append(f"{where} 必须是对象")
            continue
        _require(contract, "contract_id", where, errors)
        contract_type = _require(contract, "type", where, errors)
        if contract_type is not None and contract_type != "medium_term_fixed_price":
            errors.append(f"{where}.type 目前只支持 medium_term_fixed_price")
        _number(contract, "coverage_ratio", where, errors, minimum=0.0, maximum=1.0)
        _number(contract, "price_cny_per_mwh", where, errors, minimum=0.0)
        basis = _require(contract, "quantity_basis", where, errors)
        if basis is not None and basis != "forecast_load_share":
            errors.append(f"{where}.quantity_basis 目前只支持 forecast_load_share")

    data_contract = config.get("data_contract")
    if not isinstance(data_contract, dict):
        errors.append("缺少 data_contract 块")
        data_contract = {}
    for key in ("d1", "t1"):
        block = data_contract.get(key)
        if not isinstance(block, dict):
            errors.append(f"data_contract.{key} 缺失")
            continue
        for field in ("path", "date_field", "slot_field", "load_field"):
            _require(block, field, f"data_contract.{key}", errors)
    d1_contract = data_contract.get("d1", {}) if isinstance(data_contract.get("d1"), dict) else {}
    scenario_fields = _non_empty_list(d1_contract.get("scenario_fields"), "data_contract.d1.scenario_fields", errors)
    weights = _non_empty_list(d1_contract.get("scenario_weights"), "data_contract.d1.scenario_weights", errors)
    if scenario_fields and weights:
        if len(scenario_fields) != len(weights):
            errors.append("data_contract.d1.scenario_fields 与 scenario_weights 长度不一致")
        elif abs(sum(float(w) for w in weights if _is_number(w)) - 1.0) > 1e-9:
            errors.append("data_contract.d1.scenario_weights 之和必须为 1")
    t1_contract = data_contract.get("t1", {}) if isinstance(data_contract.get("t1"), dict) else {}
    _require(t1_contract, "price_field", "data_contract.t1", errors)

    if meta.get("grade") == "D":
        warnings.append("实例资产、客户、合约与演示数据为 D 级合成，不得直接用于真实报价或签约")
    notice = str(retail_market.get("price_linkage_notice", "")) if isinstance(retail_market, dict) else ""
    if "未核到正式文号" in notice:
        warnings.append("2026-06-08 零售市场管理通知未核到正式文号，按 B/C 级线索使用")

    if errors:
        raise ConfigError("配置校验失败：\n- " + "\n- ".join(errors))

    fingerprint = hashlib.sha1(
        json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    provenance = []
    for name in RULE_BLOCKS:
        block = rules[name]
        provenance.append({"block": name, "grade": block["grade"], "source": block["source"]})

    return {
        "ok": True,
        "errors": [],
        "warnings": warnings,
        "points_per_day": int(points),
        "mtu_min": int(mtu),
        "style_fingerprint": fingerprint,
        "provenance": provenance,
    }


def _read_rows(path, required_fields):
    path = Path(path)
    if not path.exists():
        raise InputError(f"输入文件不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputError(f"输入文件没有表头：{path}")
        missing = [field for field in required_fields if field not in reader.fieldnames]
        if missing:
            raise InputError(f"{path.name} 缺字段：{missing}")
        rows = list(reader)
    if not rows:
        raise InputError(f"输入文件没有数据行：{path}")
    return rows


def _parse_float(value, where):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{where} 不是数字：{value!r}") from exc
    if not math.isfinite(number):
        raise InputError(f"{where} 不是有限数：{value!r}")
    return number


def _parse_slots(rows, report, path):
    points = report["points_per_day"]
    dates = {row.get("date", "").strip() for row in rows}
    if len(dates) != 1 or "" in dates:
        raise InputError(f"{Path(path).name} 必须且只能包含一个交易日，当前为 {sorted(dates)}")
    slots = []
    for index, row in enumerate(rows):
        try:
            slot = int(row["slot"])
        except (TypeError, ValueError) as exc:
            raise InputError(f"{Path(path).name} 第 {index + 2} 行 slot 不是整数") from exc
        if slot < 0 or slot >= points:
            raise InputError(f"{Path(path).name} 第 {index + 2} 行 slot={slot} 越界（0–{points - 1}）")
        slots.append(slot)
    if sorted(slots) != list(range(points)):
        missing = sorted(set(range(points)) - set(slots))
        duplicated = sorted({slot for slot in slots if slots.count(slot) > 1})
        raise InputError(f"{Path(path).name} 时段不完整：缺 {missing[:5]}，重复 {duplicated[:5]}")
    return dates.pop(), slots


def _slot_start(slot, mtu_min):
    minutes = slot * mtu_min
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _slot_end(slot, mtu_min):
    minutes = (slot + 1) * mtu_min
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def read_d1(path, config, report):
    contract = config["data_contract"]["d1"]
    scenario_fields = list(contract["scenario_fields"])
    fields = ["date", "slot", contract["load_field"]] + scenario_fields
    rows = _read_rows(path, fields)
    date, slots = _parse_slots(rows, report, path)
    points = report["points_per_day"]
    by_slot = {slot: row for slot, row in zip(slots, rows)}
    spot = config["rules"]["spot"]
    floor = float(spot["clear_floor_cny_per_mwh"])
    cap = float(spot["clear_cap_cny_per_mwh"])
    load = []
    scenarios = {field: [] for field in scenario_fields}
    for slot in range(points):
        row = by_slot[slot]
        where = f"{Path(path).name} slot {slot}"
        value = _parse_float(row[contract["load_field"]], f"{where} {contract['load_field']}")
        if value < 0:
            raise InputError(f"{where} 预测负荷不能为负")
        load.append(value)
        for field in scenario_fields:
            price = _parse_float(row[field], f"{where} {field}")
            if price < floor - 1e-9 or price > cap + 1e-9:
                raise InputError(f"{where} {field}={price} 越界（{floor}–{cap} CNY/MWh）")
            scenarios[field].append(price)
    if sum(load) <= 0:
        raise InputError(f"{Path(path).name} 预测负荷合计必须为正")
    weights = [float(value) for value in contract["scenario_weights"]]
    return {
        "path": str(path),
        "date": date,
        "slots": list(range(points)),
        "interval_hours": report["mtu_min"] / 60.0,
        "load": load,
        "scenario_fields": scenario_fields,
        "scenarios": scenarios,
        "weights": weights,
    }


def read_t1(path, config, report, expected_date):
    contract = config["data_contract"]["t1"]
    fields = ["date", "slot", contract["load_field"], contract["price_field"]]
    rows = _read_rows(path, fields)
    date, slots = _parse_slots(rows, report, path)
    if date != expected_date:
        raise InputError(f"T+1 交易日 {date} 与 D-1 交易日 {expected_date} 不一致")
    points = report["points_per_day"]
    by_slot = {slot: row for slot, row in zip(slots, rows)}
    spot = config["rules"]["spot"]
    floor = float(spot["clear_floor_cny_per_mwh"])
    cap = float(spot["clear_cap_cny_per_mwh"])
    load = []
    price = []
    for slot in range(points):
        row = by_slot[slot]
        where = f"{Path(path).name} slot {slot}"
        value = _parse_float(row[contract["load_field"]], f"{where} {contract['load_field']}")
        if value < 0:
            raise InputError(f"{where} 实际负荷不能为负")
        load.append(value)
        actual_price = _parse_float(row[contract["price_field"]], f"{where} {contract['price_field']}")
        if actual_price < floor - 1e-9 or actual_price > cap + 1e-9:
            raise InputError(f"{where} {contract['price_field']}={actual_price} 越界（{floor}–{cap} CNY/MWh）")
        price.append(actual_price)
    return {
        "path": str(path),
        "date": date,
        "slots": list(range(points)),
        "interval_hours": report["mtu_min"] / 60.0,
        "load": load,
        "price": price,
    }


def _load_weighted_average(values, load):
    total = sum(load)
    if total <= 0:
        return sum(values) / len(values)
    return sum(value * weight for value, weight in zip(values, load)) / total


def _weighted_quantile(values, weights, quantile):
    if not 0.0 <= quantile <= 1.0:
        raise ConfigError("price_reference_quantile 必须在 [0, 1] 内")
    pairs = sorted(zip(values, weights), key=lambda pair: pair[0])
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= quantile - 1e-12:
            return value
    return pairs[-1][0]


def reference_curve(d1, quantile):
    return [
        _weighted_quantile(
            [d1["scenarios"][field][slot] for field in d1["scenario_fields"]],
            d1["weights"],
            quantile,
        )
        for slot in range(len(d1["load"]))
    ]


def _contract(config):
    contracts = config.get("contracts") or []
    return contracts[0] if contracts else None


def _contract_terms(config):
    contract = _contract(config)
    if contract is None:
        return 0.0, 0.0
    return float(contract["coverage_ratio"]), float(contract["price_cny_per_mwh"])


def _linked_price(spot, segment):
    return min(
        max(float(segment["pass_through"]) * spot + float(segment["adder_cny_per_mwh"]), float(segment["floor_cny_per_mwh"])),
        float(segment["cap_cny_per_mwh"]),
    )


def _segment_price(segment, spot):
    if segment["package_type"] == "fixed":
        return float(segment["retail_price_cny_per_mwh"])
    return _linked_price(spot, segment)


def _expected_deviation_per_mwh(sigma_pct, tolerance, penalty):
    if sigma_pct <= 0:
        return 0.0
    ratio = tolerance / sigma_pct
    density = math.exp(-0.5 * ratio * ratio) / math.sqrt(2.0 * math.pi)
    return 2.0 * sigma_pct * density * penalty


def _guarantee_daily(config):
    guarantee = config["portfolio"]["guarantee"]
    return float(guarantee["amount_cny"]) * float(guarantee["annual_funding_rate"]) / 365.0


def _weighted_opex(config):
    return sum(float(segment["share"]) * float(segment["opex_cny_per_mwh"]) for segment in config["portfolio"]["segments"])


def _weighted_sigma(config):
    return sum(float(segment["share"]) * float(segment["forecast_sigma_pct"]) for segment in config["portfolio"]["segments"])


def _linked_share(config):
    return sum(
        float(segment["share"]) * float(segment["pass_through"])
        for segment in config["portfolio"]["segments"]
        if segment["package_type"] == "market_linked"
    )


def build_pricing(config, d1, ref_curve, report):
    portfolio = config["portfolio"]
    segments = portfolio["segments"]
    interval = d1["interval_hours"]
    energy = sum(d1["load"]) * interval
    reference_avg = _load_weighted_average(ref_curve, d1["load"])
    coverage, contract_price = _contract_terms(config)
    wholesale = coverage * contract_price + (1.0 - coverage) * reference_avg
    guarantee_per_mwh = _guarantee_daily(config) / energy
    fixed_per_mwh = float(portfolio["fixed_cost_cny_per_day"]) / energy
    terms = portfolio["deviation_terms"]
    tolerance = float(terms["tolerance_share"])
    penalty = float(terms["penalty_cny_per_mwh"])
    policy = config["policy"]
    risk_buffer = float(policy["risk_buffer_cny_per_mwh"])
    target = float(policy["target_margin_cny_per_mwh"])

    rows = []
    for segment in segments:
        share = float(segment["share"])
        sigma = float(segment["forecast_sigma_pct"])
        opex = float(segment["opex_cny_per_mwh"])
        deviation_cost = _expected_deviation_per_mwh(sigma, tolerance, penalty)
        full_cost = wholesale + deviation_cost + opex + guarantee_per_mwh + fixed_per_mwh + risk_buffer + target
        if segment["package_type"] == "fixed":
            current_price = float(segment["retail_price_cny_per_mwh"])
            recommended_price = full_cost
            current_adder = None
            recommended_adder = None
            if coverage < 1.0 - 1e-12:
                break_even = (
                    current_price - deviation_cost - opex - guarantee_per_mwh - fixed_per_mwh - coverage * contract_price
                ) / (1.0 - coverage)
                break_even_buffer = (
                    current_price
                    - deviation_cost
                    - opex
                    - guarantee_per_mwh
                    - fixed_per_mwh
                    - risk_buffer
                    - target
                    - coverage * contract_price
                ) / (1.0 - coverage)
            else:
                break_even = None
                break_even_buffer = None
        else:
            current_price = _linked_price(reference_avg, segment)
            current_adder = float(segment["adder_cny_per_mwh"])
            recommended_adder = full_cost - float(segment["pass_through"]) * reference_avg
            recommended_price = min(
                max(
                    float(segment["pass_through"]) * reference_avg + recommended_adder,
                    float(segment["floor_cny_per_mwh"]),
                ),
                float(segment["cap_cny_per_mwh"]),
            )
            denominator = float(segment["pass_through"]) - (1.0 - coverage)
            if abs(denominator) > 1e-12:
                break_even = (
                    coverage * contract_price
                    + deviation_cost
                    + opex
                    + guarantee_per_mwh
                    + fixed_per_mwh
                    - current_adder
                ) / denominator
                break_even_buffer = (
                    coverage * contract_price
                    + deviation_cost
                    + opex
                    + guarantee_per_mwh
                    + fixed_per_mwh
                    + risk_buffer
                    + target
                    - current_adder
                ) / denominator
            else:
                break_even = None
                break_even_buffer = None
        rows.append(
            {
                "segment": segment["name"],
                "package_type": segment["package_type"],
                "share": share,
                "current_price_cny_per_mwh": current_price,
                "current_adder_cny_per_mwh": current_adder,
                "wholesale_cost_cny_per_mwh": wholesale,
                "expected_deviation_cny_per_mwh": deviation_cost,
                "opex_cny_per_mwh": opex,
                "guarantee_funding_cny_per_mwh": guarantee_per_mwh,
                "fixed_cost_cny_per_mwh": fixed_per_mwh,
                "risk_buffer_cny_per_mwh": risk_buffer,
                "target_margin_cny_per_mwh": target,
                "full_cost_cny_per_mwh": full_cost,
                "recommended_price_cny_per_mwh": recommended_price,
                "recommended_adder_cny_per_mwh": recommended_adder,
                "gap_cny_per_mwh": recommended_price - current_price,
                "break_even_spot_cny_per_mwh": break_even,
                "break_even_spot_with_buffer_cny_per_mwh": break_even_buffer,
            }
        )

    weighted_current = sum(row["share"] * row["current_price_cny_per_mwh"] for row in rows)
    weighted_recommended = sum(row["share"] * row["recommended_price_cny_per_mwh"] for row in rows)
    return {
        "energy_mwh": energy,
        "reference_spot_cny_per_mwh": reference_avg,
        "wholesale_cost_cny_per_mwh": wholesale,
        "coverage_ratio": coverage,
        "contract_price_cny_per_mwh": contract_price,
        "guarantee_daily_cny": _guarantee_daily(config),
        "fixed_cost_daily_cny": float(portfolio["fixed_cost_cny_per_day"]),
        "weighted_current_price_cny_per_mwh": weighted_current,
        "weighted_recommended_price_cny_per_mwh": weighted_recommended,
        "weighted_gap_cny_per_mwh": weighted_recommended - weighted_current,
        "rows": rows,
    }


def _plan_net(config, d1, spot_curve):
    interval = d1["interval_hours"]
    coverage, contract_price = _contract_terms(config)
    segments = config["portfolio"]["segments"]
    revenue = 0.0
    for slot, load in enumerate(d1["load"]):
        price = sum(float(segment["share"]) * _segment_price(segment, spot_curve[slot]) for segment in segments)
        revenue += price * load * interval
    procurement = 0.0
    for slot, load in enumerate(d1["load"]):
        contract_quantity = coverage * load
        procurement += (contract_quantity * contract_price + (load - contract_quantity) * spot_curve[slot]) * interval
    energy = sum(d1["load"]) * interval
    opex = energy * _weighted_opex(config) + float(config["portfolio"]["fixed_cost_cny_per_day"]) + _guarantee_daily(config)
    net = revenue - procurement - opex
    return {
        "revenue_cny": revenue,
        "procurement_cny": procurement,
        "opex_cny": opex,
        "net_cny": net,
        "energy_mwh": energy,
    }


def _weighted_cvar(values, weights, alpha):
    pairs = sorted(zip(values, weights), key=lambda pair: pair[0])
    remaining = alpha
    total = 0.0
    tail = 0.0
    for value, weight in pairs:
        take = min(weight, remaining)
        if take <= 0:
            break
        tail += value * take
        total += take
        remaining -= take
        if remaining <= 1e-12:
            break
    return tail / total if total > 0 else pairs[0][0]


def build_scenarios(config, d1, ref_curve):
    rows = []
    for field, weight in zip(d1["scenario_fields"], d1["weights"]):
        result = _plan_net(config, d1, d1["scenarios"][field])
        rows.append(
            {
                "scenario": field,
                "weight": weight,
                "average_price_cny_per_mwh": sum(d1["scenarios"][field]) / len(d1["scenarios"][field]),
                "revenue_cny": result["revenue_cny"],
                "procurement_cny": result["procurement_cny"],
                "opex_cny": result["opex_cny"],
                "net_cny": result["net_cny"],
            }
        )
    expected = sum(row["weight"] * row["net_cny"] for row in rows)
    cvar = _weighted_cvar([row["net_cny"] for row in rows], [row["weight"] for row in rows], 0.10)
    plan = _plan_net(config, d1, ref_curve)
    coverage, _ = _contract_terms(config)
    energy = plan["energy_mwh"]
    net_exposure = (1.0 - coverage) * energy - _linked_share(config) * energy
    reference_avg = _load_weighted_average(ref_curve, d1["load"])
    break_even_multiplier = None
    if net_exposure > 1e-9 and reference_avg > 0:
        break_even_multiplier = 1.0 + plan["net_cny"] / (net_exposure * reference_avg)
    return {
        "rows": rows,
        "expected_net_cny": expected,
        "cvar_10_cny": cvar,
        "plan": plan,
        "net_exposure_mwh": net_exposure,
        "break_even_spot_multiplier": break_even_multiplier,
    }


def build_stress(config, d1, ref_curve, pricing):
    policy = config["policy"]
    energy = pricing["energy_mwh"]
    spot_rows = []
    for multiplier in policy["stress_spot_multipliers"]:
        result = _plan_net(config, d1, [price * float(multiplier) for price in ref_curve])
        spot_rows.append(
            {
                "multiplier": float(multiplier),
                "net_cny": result["net_cny"],
                "per_mwh_cny": result["net_cny"] / energy if energy > 0 else 0.0,
            }
        )
    terms = config["portfolio"]["deviation_terms"]
    tolerance = float(terms["tolerance_share"])
    penalty = float(terms["penalty_cny_per_mwh"])
    deviation_rows = []
    for sigma in policy["stress_sigma_pcts"]:
        per_mwh = _expected_deviation_per_mwh(float(sigma), tolerance, penalty)
        deviation_rows.append(
            {
                "sigma_pct": float(sigma),
                "expected_cost_cny_per_mwh": per_mwh,
                "expected_cost_cny": per_mwh * energy,
            }
        )
    base_sigma = _weighted_sigma(config)
    return {
        "base_sigma_pct": base_sigma,
        "base_expected_deviation_cny_per_mwh": _expected_deviation_per_mwh(base_sigma, tolerance, penalty),
        "spot": spot_rows,
        "deviation": deviation_rows,
    }


def build_bridge(config, d1, t1, ref_curve):
    interval = d1["interval_hours"]
    forecast = d1["load"]
    actual = t1["load"]
    plan_price = ref_curve
    actual_price = t1["price"]
    coverage, contract_price = _contract_terms(config)
    contract_quantity = [coverage * load for load in forecast]
    segments = config["portfolio"]["segments"]
    terms = config["portfolio"]["deviation_terms"]
    tolerance = float(terms["tolerance_share"])
    penalty = float(terms["penalty_cny_per_mwh"])

    plan_revenue = sum(
        sum(float(segment["share"]) * _segment_price(segment, plan_price[slot]) for segment in segments)
        * forecast[slot]
        * interval
        for slot in range(len(forecast))
    )
    actual_revenue = sum(
        sum(float(segment["share"]) * _segment_price(segment, actual_price[slot]) for segment in segments)
        * actual[slot]
        * interval
        for slot in range(len(actual))
    )
    plan_procurement = sum(
        (contract_quantity[slot] * contract_price + (forecast[slot] - contract_quantity[slot]) * plan_price[slot])
        * interval
        for slot in range(len(forecast))
    )
    actual_procurement = sum(
        (contract_quantity[slot] * contract_price + (actual[slot] - contract_quantity[slot]) * actual_price[slot])
        * interval
        for slot in range(len(actual))
    )
    opex_rate = _weighted_opex(config)
    fixed_cost = float(config["portfolio"]["fixed_cost_cny_per_day"]) + _guarantee_daily(config)
    plan_opex = sum(forecast) * interval * opex_rate + fixed_cost
    actual_opex = sum(actual) * interval * opex_rate + fixed_cost
    plan_deviation = 0.0
    actual_deviation = sum(
        max(abs(actual[slot] - forecast[slot]) - tolerance * forecast[slot], 0.0) for slot in range(len(actual))
    ) * penalty * interval
    plan_net = plan_revenue - plan_procurement - plan_opex
    actual_net = actual_revenue - actual_procurement - actual_opex - actual_deviation

    revenue_volume = sum(
        sum(float(segment["share"]) * _segment_price(segment, plan_price[slot]) for segment in segments)
        * (actual[slot] - forecast[slot])
        * interval
        for slot in range(len(forecast))
    )
    revenue_price = sum(
        sum(
            float(segment["share"]) * (_segment_price(segment, actual_price[slot]) - _segment_price(segment, plan_price[slot]))
            for segment in segments
            if segment["package_type"] == "market_linked"
        )
        * actual[slot]
        * interval
        for slot in range(len(forecast))
    )
    spot_quantity = -sum((actual[slot] - forecast[slot]) * plan_price[slot] * interval for slot in range(len(forecast)))
    spot_price = -sum(
        (forecast[slot] - contract_quantity[slot]) * (actual_price[slot] - plan_price[slot]) * interval
        for slot in range(len(forecast))
    )
    spot_cross = -sum(
        (actual[slot] - forecast[slot]) * (actual_price[slot] - plan_price[slot]) * interval
        for slot in range(len(forecast))
    )
    contract_cost = 0.0
    deviation_cost = -(actual_deviation - plan_deviation)
    opex_cost = -(actual_opex - plan_opex)
    guarantee_cost = 0.0

    buckets = [
        {"item": "零售收入量差", "category": "收入", "owner": "客户负荷", "amount": revenue_volume},
        {"item": "零售价格差", "category": "收入", "owner": "联动套餐", "amount": revenue_price},
        {"item": "现货购电量差", "category": "成本", "owner": "负荷预测", "amount": spot_quantity},
        {"item": "现货购电价差", "category": "成本", "owner": "市场价格", "amount": spot_price},
        {"item": "现货量价交叉", "category": "成本", "owner": "量价共振", "amount": spot_cross},
        {"item": "合约成本差异", "category": "成本", "owner": "中长期合约", "amount": contract_cost},
        {"item": "偏差考核", "category": "成本", "owner": "预测与合同", "amount": deviation_cost},
        {"item": "运营成本", "category": "成本", "owner": "运营", "amount": opex_cost},
        {"item": "担保资金成本", "category": "成本", "owner": "履约保障", "amount": guarantee_cost},
    ]
    delta = actual_net - plan_net
    identity_gap = plan_net + sum(bucket["amount"] for bucket in buckets) - actual_net

    mtu_min = int(round(interval * 60))
    detail = []
    for slot in range(len(forecast)):
        load_deviation = actual[slot] - forecast[slot]
        excess = max(abs(load_deviation) - tolerance * forecast[slot], 0.0)
        detail.append(
            {
                "slot": slot,
                "start": _slot_start(slot, mtu_min),
                "end": _slot_end(slot, mtu_min),
                "forecast_load_mw": forecast[slot],
                "actual_load_mw": actual[slot],
                "load_deviation_mw": load_deviation,
                "deviation_share": load_deviation / forecast[slot] if forecast[slot] > 0 else 0.0,
                "excess_mwh": excess * interval,
                "assessment_cny": excess * penalty * interval,
                "plan_price_cny_per_mwh": plan_price[slot],
                "actual_price_cny_per_mwh": actual_price[slot],
            }
        )
    detail.sort(key=lambda row: (row["assessment_cny"], abs(row["load_deviation_mw"])), reverse=True)
    top_slots = detail[: int(config["policy"].get("review_top_slots", 5))]

    return {
        "plan_net_cny": plan_net,
        "actual_net_cny": actual_net,
        "delta_cny": delta,
        "identity_gap": identity_gap,
        "plan_revenue_cny": plan_revenue,
        "actual_revenue_cny": actual_revenue,
        "plan_procurement_cny": plan_procurement,
        "actual_procurement_cny": actual_procurement,
        "plan_deviation_cny": plan_deviation,
        "actual_deviation_cny": actual_deviation,
        "plan_energy_mwh": sum(forecast) * interval,
        "actual_energy_mwh": sum(actual) * interval,
        "buckets": buckets,
        "top_slots": top_slots,
    }


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, float):
        if field in {"share"}:
            return f"{value:.3f}"
        if field in {
            "forecast_load_mw",
            "contract_mw",
            "spot_mw",
            "actual_load_mw",
            "load_deviation_mw",
            "excess_mwh",
            "deviation_share",
        }:
            return f"{0.0 if abs(value) < 1e-9 else value:.6f}"
        if field in {
            "amount",
            "assessment_cny",
            "revenue_cny",
            "procurement_cny",
            "opex_cny",
            "net_cny",
        }:
            return f"{0.0 if abs(value) < 0.005 else value:.2f}"
        return f"{0.0 if abs(value) < 1e-9 else value:.2f}"
    return value


def _write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(field, row.get(field)) for field in fields})


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _num(value, digits=2):
    if value is None:
        return "—"
    threshold = 0.5 * 10 ** (-digits)
    if abs(value) < threshold:
        value = 0.0
    return f"{value:,.{digits}f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def write_review(path, config, report, d1, t1, pricing, scenarios, stress, bridge):
    meta = config["meta"]
    policy = config["policy"]
    lines = [
        f"# 广东售电零售复核表：{meta['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']} 分钟）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}",
        f"- 风格档：`{policy['profile_id']}` / 指纹 `{report['style_fingerprint']}`",
        f"- 口径：{meta['scope']}",
        "",
        "## 1. 规则来源与未核实项",
        "",
    ]
    lines += _table(
        ["规则块", "级别", "来源"],
        [[row["block"], row["grade"], row["source"]] for row in report["provenance"]],
    )
    if report["warnings"]:
        lines += ["", "警告：", ""]
        lines += [f"- {warning}" for warning in report["warnings"]]
    lines += [
        "",
        "## 2. 结论",
        "",
        f"- 组合预测电量：{_num(pricing['energy_mwh'], 1)} MWh；参考价：{_num(pricing['reference_spot_cny_per_mwh'])} CNY/MWh。",
        f"- 当前加权零售价：{_num(pricing['weighted_current_price_cny_per_mwh'])} CNY/MWh；建议全成本价：{_num(pricing['weighted_recommended_price_cny_per_mwh'])} CNY/MWh；缺口 {_num(pricing['weighted_gap_cny_per_mwh'])} CNY/MWh。",
        f"- 计划净边际：{_money(scenarios['plan']['net_cny'])} CNY（{_num(scenarios['plan']['net_cny'] / pricing['energy_mwh'] if pricing['energy_mwh'] else 0, 4)} CNY/MWh）。",
        f"- 情景期望净边际：{_money(scenarios['expected_net_cny'])} CNY；CVaR10：{_money(scenarios['cvar_10_cny'])} CNY。",
        f"- 现货净敞口：{_num(scenarios['net_exposure_mwh'], 1)} MWh；组合保本现货涨幅：{_pct(None if scenarios['break_even_spot_multiplier'] is None else scenarios['break_even_spot_multiplier'] - 1.0)}。",
    ]
    if bridge is not None:
        lines += [
            f"- 实际净边际：{_money(bridge['actual_net_cny'])} CNY；差异 {_money(bridge['delta_cny'])} CNY；残差 {bridge['identity_gap']:.2e} CNY。",
        ]
    else:
        lines += ["- 未提供 T+1 数据，本次只出 D-1 定价与情景，不跑差异桥。"]
    lines += [
        "",
        "## 3. 套餐定价（参考价口径）",
        "",
        f"采购结构：中长期覆盖 {_pct(pricing['coverage_ratio'])}、合约价 {_num(pricing['contract_price_cny_per_mwh'])} CNY/MWh；加权采购成本 {_num(pricing['wholesale_cost_cny_per_mwh'])} CNY/MWh。",
        "",
    ]
    pricing_rows = []
    for row in pricing["rows"]:
        package = "固定价" if row["package_type"] == "fixed" else "市场联动"
        current = row["current_price_cny_per_mwh"]
        recommended = row["recommended_price_cny_per_mwh"]
        adder = "—"
        if row["package_type"] == "market_linked":
            adder = f"{_num(row['current_adder_cny_per_mwh'])}→{_num(row['recommended_adder_cny_per_mwh'])}"
        pricing_rows.append(
            [
                row["segment"],
                package,
                _pct(row["share"]),
                _num(current),
                _num(row["full_cost_cny_per_mwh"]),
                _num(recommended),
                _num(row["gap_cny_per_mwh"]),
                _num(row["break_even_spot_cny_per_mwh"]),
                _num(row["break_even_spot_with_buffer_cny_per_mwh"]),
                adder,
            ]
        )
    lines += _table(
        ["客户群", "套餐", "份额", "当前价", "全成本", "建议价", "缺口", "保本现货", "含缓冲保本", "联动加价"],
        pricing_rows,
    )
    lines += [
        "",
        "全成本 = 批发 + 期望偏差 + 运营 + 担保资金 + 固定成本 + 风险缓冲 + 目标利润。保本现货不含风险缓冲与目标利润；含缓冲列才用于内部限额。",
        "",
        "## 4. 情景与压力测试",
        "",
    ]
    scenario_rows = [
        [
            row["scenario"],
            _pct(row["weight"]),
            _num(row["average_price_cny_per_mwh"]),
            _money(row["revenue_cny"]),
            _money(row["procurement_cny"]),
            _money(row["net_cny"]),
        ]
        for row in scenarios["rows"]
    ]
    lines += _table(["情景", "权重", "均价", "零售收入", "购电成本", "净边际"], scenario_rows)
    lines += [
        "",
        f"组合加权预测误差 σ={_pct(stress['base_sigma_pct'])}；基准期望偏差成本 {_num(stress['base_expected_deviation_cny_per_mwh'])} CNY/MWh。",
        "",
    ]
    spot_rows = [
        [f"×{row['multiplier']:.2f}", _money(row["net_cny"]), _num(row["per_mwh_cny"], 4)] for row in stress["spot"]
    ]
    lines += _table(["现货倍数", "净边际（CNY）", "度电净边际（CNY/kWh）"], spot_rows)
    lines += [""]
    deviation_rows = [
        [f"σ={_pct(row['sigma_pct'])}", _num(row["expected_cost_cny_per_mwh"]), _money(row["expected_cost_cny"])]
        for row in stress["deviation"]
    ]
    lines += _table(["预测误差情景", "期望考核（CNY/MWh）", "期望考核（CNY/日）"], deviation_rows)
    lines += [
        "",
        "情景净边际不含偏差考核（计划口径）；偏差考核在压力表单列，T+1 差异桥按实际偏差计算。",
        "",
        "## 5. T+1 差异桥",
        "",
    ]
    if bridge is None:
        lines += ["无 T+1 数据。", ""]
    else:
        bridge_rows = [[row["item"], row["category"], row["owner"], _money(row["amount"])] for row in bridge["buckets"]]
        bridge_rows.append(["残差", "校验", "—", f"{bridge['identity_gap']:.2e}"])
        lines += _table(["科目", "类别", "责任", "金额（CNY）"], bridge_rows)
        lines += [
            "",
            f"计划 {_money(bridge['plan_net_cny'])} → 实际 {_money(bridge['actual_net_cny'])}，差异 {_money(bridge['delta_cny'])} CNY。"
            "负号表示对净边际不利；正号表示有利。",
            "",
            "### 偏差最大的时段",
            "",
        ]
        slot_rows = [
            [
                f"{row['slot']}（{row['start']}–{row['end']}）",
                _num(row["forecast_load_mw"], 2),
                _num(row["actual_load_mw"], 2),
                _num(row["load_deviation_mw"], 2),
                _pct(row["deviation_share"]),
                _num(row["assessment_cny"]),
            ]
            for row in bridge["top_slots"]
        ]
        lines += _table(["时段", "预测 MW", "实际 MW", "偏差 MW", "偏差率", "考核 CNY"], slot_rows)
        lines += [""]
    lines += [
        "## 6. 读法与边界",
        "",
        "- 组合平均价差可能被高毛利客户掩盖：先看每个客户群的全成本缺口，再看加权结果。",
        "- 固定价套餐在现货上行时利润收缩；联动套餐的传导系数与加价决定净敞口，不只看套餐名字。",
        "- 保本现货不含风险缓冲与目标利润；对外报价用全成本，内部限额看含缓冲口径。",
        "- 偏差考核按合同约定测算；广东现行统一考核规则未核实，不得把 ±3%/±5% 当作省规则。",
        "- 本表只覆盖电能量口径；输配电价、政府性基金、基本电费、绿电溢价、坏账、用户流失与税费均未计入。",
        "- 所有客户、价格、合约与计量数据均为 D 级合成，不对应任何真实主体。",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, d1_path, t1_path, out_dir, demo=False):
    instance_path = Path(instance_path)
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    report = validate_instance(config)
    d1 = read_d1(d1_path, config, report)
    t1 = None if t1_path is None else read_t1(t1_path, config, report, d1["date"])
    ref_curve = reference_curve(d1, float(config["policy"]["price_reference_quantile"]))
    pricing = build_pricing(config, d1, ref_curve, report)
    scenarios = build_scenarios(config, d1, ref_curve)
    stress = build_stress(config, d1, ref_curve, pricing)
    bridge = None if t1 is None else build_bridge(config, d1, t1, ref_curve)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pricing_fields = [
        "segment",
        "package_type",
        "share",
        "current_price_cny_per_mwh",
        "current_adder_cny_per_mwh",
        "wholesale_cost_cny_per_mwh",
        "expected_deviation_cny_per_mwh",
        "opex_cny_per_mwh",
        "guarantee_funding_cny_per_mwh",
        "fixed_cost_cny_per_mwh",
        "risk_buffer_cny_per_mwh",
        "target_margin_cny_per_mwh",
        "full_cost_cny_per_mwh",
        "recommended_price_cny_per_mwh",
        "recommended_adder_cny_per_mwh",
        "gap_cny_per_mwh",
        "break_even_spot_cny_per_mwh",
        "break_even_spot_with_buffer_cny_per_mwh",
    ]
    _write_csv(out_dir / "pricing_sheet.csv", pricing["rows"], pricing_fields)

    plan_fields = [
        "date",
        "slot",
        "start",
        "end",
        "forecast_load_mw",
        "contract_mw",
        "spot_mw",
    ] + list(d1["scenario_fields"])
    plan_rows = []
    coverage = pricing["coverage_ratio"]
    for slot, load in enumerate(d1["load"]):
        row = {
            "date": d1["date"],
            "slot": slot,
            "start": _slot_start(slot, report["mtu_min"]),
            "end": _slot_end(slot, report["mtu_min"]),
            "forecast_load_mw": load,
            "contract_mw": coverage * load,
            "spot_mw": (1.0 - coverage) * load,
        }
        for field in d1["scenario_fields"]:
            row[field] = d1["scenarios"][field][slot]
        plan_rows.append(row)
    _write_csv(out_dir / "procurement_plan.csv", plan_rows, plan_fields)

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": report["style_fingerprint"],
        "provenance": report["provenance"],
        "warnings": report["warnings"],
        "pricing": {
            "reference_spot_cny_per_mwh": pricing["reference_spot_cny_per_mwh"],
            "coverage_ratio": pricing["coverage_ratio"],
            "contract_price_cny_per_mwh": pricing["contract_price_cny_per_mwh"],
            "wholesale_cost_cny_per_mwh": pricing["wholesale_cost_cny_per_mwh"],
            "weighted_current_price_cny_per_mwh": pricing["weighted_current_price_cny_per_mwh"],
            "weighted_recommended_price_cny_per_mwh": pricing["weighted_recommended_price_cny_per_mwh"],
            "weighted_gap_cny_per_mwh": pricing["weighted_gap_cny_per_mwh"],
            "segments": pricing["rows"],
        },
        "plan": {
            "energy_mwh": pricing["energy_mwh"],
            "net_margin_at_reference_cny": scenarios["plan"]["net_cny"],
            "expected_net_margin_cny": scenarios["expected_net_cny"],
            "cvar_10_cny": scenarios["cvar_10_cny"],
            "net_exposure_mwh": scenarios["net_exposure_mwh"],
            "break_even_spot_multiplier": scenarios["break_even_spot_multiplier"],
            "scenarios": scenarios["rows"],
        },
        "stress": stress,
        "bridge": None
        if bridge is None
        else {
            "plan_net_cny": bridge["plan_net_cny"],
            "actual_net_cny": bridge["actual_net_cny"],
            "delta_cny": bridge["delta_cny"],
            "identity_gap": bridge["identity_gap"],
            "buckets": bridge["buckets"],
            "top_slots": bridge["top_slots"],
        },
        "files": {
            "pricing_sheet": "pricing_sheet.csv",
            "procurement_plan": "procurement_plan.csv",
            "review": "review.md",
            "bridge": "bridge.json" if bridge is not None else None,
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if bridge is not None:
        bridge_out = {
            "plan_net_cny": bridge["plan_net_cny"],
            "actual_net_cny": bridge["actual_net_cny"],
            "delta_cny": bridge["delta_cny"],
            "identity_gap": bridge["identity_gap"],
            "plan_revenue_cny": bridge["plan_revenue_cny"],
            "actual_revenue_cny": bridge["actual_revenue_cny"],
            "plan_procurement_cny": bridge["plan_procurement_cny"],
            "actual_procurement_cny": bridge["actual_procurement_cny"],
            "plan_deviation_cny": bridge["plan_deviation_cny"],
            "actual_deviation_cny": bridge["actual_deviation_cny"],
            "plan_energy_mwh": bridge["plan_energy_mwh"],
            "actual_energy_mwh": bridge["actual_energy_mwh"],
            "buckets": bridge["buckets"],
            "top_slots": bridge["top_slots"],
        }
        (out_dir / "bridge.json").write_text(json.dumps(bridge_out, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_csv(out_dir / "bridge.csv", bridge["buckets"], ["item", "category", "owner", "amount"])
        _write_csv(
            out_dir / "deviation_slots.csv",
            bridge["top_slots"],
            [
                "slot",
                "start",
                "end",
                "forecast_load_mw",
                "actual_load_mw",
                "load_deviation_mw",
                "deviation_share",
                "excess_mwh",
                "assessment_cny",
                "plan_price_cny_per_mwh",
                "actual_price_cny_per_mwh",
            ],
        )
    write_review(out_dir / "review.md", config, report, d1, t1, pricing, scenarios, stress, bridge)

    return {
        "config": config,
        "report": report,
        "d1": d1,
        "t1": t1,
        "pricing": pricing,
        "scenarios": scenarios,
        "stress": stress,
        "bridge": bridge,
        "summary": summary,
        "out_dir": out_dir,
        "demo": demo,
    }


def _print_summary(result):
    config = result["config"]
    summary = result["summary"]
    pricing = result["pricing"]
    plan = summary["plan"]
    print(f"实例：{config['meta']['instance_id']} / 交易日 {summary['trading_day']}")
    print(
        f"组合：预测 {pricing['energy_mwh']:,.1f} MWh，{len(pricing['rows'])} 个客户群，"
        f"固定 {sum(row['share'] for row in pricing['rows'] if row['package_type'] == 'fixed') * 100:.0f}% / "
        f"联动 {sum(row['share'] for row in pricing['rows'] if row['package_type'] == 'market_linked') * 100:.0f}%"
    )
    print(
        f"套餐：参考价 {pricing['reference_spot_cny_per_mwh']:,.2f} CNY/MWh，"
        f"当前加权 {pricing['weighted_current_price_cny_per_mwh']:,.2f}，"
        f"建议 {pricing['weighted_recommended_price_cny_per_mwh']:,.2f}，"
        f"缺口 {pricing['weighted_gap_cny_per_mwh']:+,.2f}"
    )
    if plan["break_even_spot_multiplier"] is None:
        break_even_text = "保本现货涨幅 —（净敞口不为正）"
    else:
        break_even_text = f"保本现货涨幅 {plan['break_even_spot_multiplier'] - 1.0:+.1%}"
    print(
        f"情景：期望净边际 {plan['expected_net_margin_cny']:,.0f} CNY，"
        f"CVaR10 {plan['cvar_10_cny']:,.0f} CNY；{break_even_text}"
    )
    bridge = result["bridge"]
    if bridge is not None:
        print(
            f"差异桥：计划 {bridge['plan_net_cny']:,.0f} → 实际 {bridge['actual_net_cny']:,.0f}，"
            f"差异 {bridge['delta_cny']:+,.0f} CNY，残差 {bridge['identity_gap']:.2e}"
        )
    else:
        print("差异桥：未提供 T+1，跳过")
    print(f"产物：{result['out_dir']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="广东售电零售实例包：D-1 套餐定价与 T+1 毛利差异桥")
    parser.add_argument("--instance", default=str(HERE / "instance.json"), help="实例配置路径")
    parser.add_argument("--check-config", action="store_true", help="只校验配置并打印来源表")
    parser.add_argument("--demo", action="store_true", help="用实例自带 D 级演示数据跑全流程")
    parser.add_argument("--d1", help="D-1 输入 CSV")
    parser.add_argument("--t1", help="T+1 输入 CSV（可选）")
    parser.add_argument("--out", help="输出目录")
    args = parser.parse_args(argv)

    instance_path = Path(args.instance)
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
        report = validate_instance(config)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取配置失败：{exc}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.check_config:
        print(f"实例：{config['meta']['instance_id']}")
        print(f"口径：{config['meta']['scope']}")
        print(f"风格指纹：{report['style_fingerprint']}；点位 {report['points_per_day']}，MTU {report['mtu_min']} 分钟")
        print("规则来源：")
        for row in report["provenance"]:
            print(f"- {row['block']}: {row['grade']} / {row['source']}")
        if report["warnings"]:
            print("警告：")
            for warning in report["warnings"]:
                print(f"- {warning}")
        print("配置校验通过。")
        return 0

    if args.demo:
        d1_path = instance_path.parent / config["data_contract"]["d1"]["path"]
        t1_path = instance_path.parent / config["data_contract"]["t1"]["path"]
        out_dir = Path(args.out) if args.out else HERE / "out" / "demo"
        demo = True
    else:
        if not args.d1:
            print("需要 --d1，或使用 --demo / --check-config", file=sys.stderr)
            return 2
        d1_path = Path(args.d1)
        t1_path = Path(args.t1) if args.t1 else None
        out_dir = Path(args.out) if args.out else HERE / "out" / "run"
        demo = False

    try:
        result = run_instance(instance_path, d1_path, t1_path, out_dir, demo=demo)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (InputError, OSError) as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 2
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
