#!/usr/bin/env python3
"""Jiangsu 2027 retail instance runner: pass-through, monthly cap, bridge.

The instance is a configuration package, not a forecast. All demo data are
grade-D synthetic and correspond to no real retailer, customer or contract.

Model (苏电交易〔2026〕11号):
    P_retail   = P_wholesale + P_float + Σ K_i × P_allocation,i
    P_wholesale,t = (1−K1−K2) × P_MT,t + K1 × P_DA,t + K2 × P_RT,t
    P_ref      = Σ_t max(P_annual, P_monthly, P_intra_month, P_DA, P_RT) × Q_t / ΣQ_t
    P_cap      = P_ref + F × P_wholesale + P_allocation
    settle at min(P_retail, P_cap) after comparing monthly averages.

Commands:
    python run.py --check-config
    python run.py --demo
    python run.py --d1 data/d1_demo.csv --t1 data/t1_demo.csv --out out/run
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULE_BLOCKS = ("spot", "retail_market", "price_formula", "allocation", "guarantee", "settlement")
PACKAGE_TYPE = "pass_through_cap"
GRADE_RE = re.compile(r"^[ABCD](/[ABCD])*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


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


def _text(block, key, where, errors):
    value = _require(block, key, where, errors)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}.{key} 必须是非空字符串")
        return None
    return value.strip()


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


def _grade(block, where, errors):
    value = _require(block, "grade", where, errors)
    source = _require(block, "source", where, errors)
    if value is not None and not GRADE_RE.match(str(value)):
        errors.append(f"{where}.grade 必须是 A/B/C/D 或其组合")
    if source is not None and not str(source).strip():
        errors.append(f"{where}.source 不能为空")
    return value


def _list(value, where, errors):
    if not isinstance(value, list) or not value:
        errors.append(f"{where} 必须是非空数组")
        return []
    return value


def _parse_date(value, where, errors):
    if not isinstance(value, str) or not DATE_RE.match(value):
        errors.append(f"{where} 必须是 YYYY-MM-DD")
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{where} 不是有效日期：{value}")
        return None


def _business_days_between(start, end):
    """Count weekdays after start up to and including end (no holiday calendar)."""
    if end <= start:
        return 0
    days = 0
    cursor = start + dt.timedelta(days=1)
    while cursor <= end:
        if cursor.weekday() < 5:
            days += 1
        cursor += dt.timedelta(days=1)
    return days


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
    if isinstance(meta.get("units"), dict):
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
        _grade(block, f"rules.{name}", errors)

    spot = rules.get("spot", {}) if isinstance(rules, dict) else {}
    if isinstance(spot, dict):
        mtu = _number(spot, "market_time_unit_min", "rules.spot", errors, minimum=1)
        points = _number(spot, "points_per_day", "rules.spot", errors, minimum=1)
        clear_floor = _number(spot, "clear_floor_cny_per_mwh", "rules.spot", errors)
        clear_cap = _number(spot, "clear_cap_cny_per_mwh", "rules.spot", errors)
        declare_floor = _number(spot, "declare_floor_cny_per_mwh", "rules.spot", errors)
        if mtu is not None and points is not None and abs(points - 24.0 * 60.0 / mtu) > 1e-9:
            errors.append("rules.spot.points_per_day 必须等于 24×60 / market_time_unit_min")
        if clear_floor is not None and clear_cap is not None and clear_floor >= clear_cap:
            errors.append("rules.spot.clear_floor_cny_per_mwh 必须小于 clear_cap_cny_per_mwh")
        if clear_floor is not None and declare_floor is not None and declare_floor < clear_floor:
            errors.append("rules.spot.declare_floor_cny_per_mwh 不能低于 clear_floor_cny_per_mwh")
    else:
        mtu = points = clear_floor = clear_cap = None

    retail_market = rules.get("retail_market", {}) if isinstance(rules, dict) else {}
    if isinstance(retail_market, dict):
        _text(retail_market, "document", "rules.retail_market", errors)
        _text(retail_market, "issued", "rules.retail_market", errors)
        _text(retail_market, "effective_from", "rules.retail_market", errors)
        _text(retail_market, "package_price", "rules.retail_market", errors)
        window = retail_market.get("annual_window")
        if not isinstance(window, dict):
            errors.append("rules.retail_market.annual_window 缺失")
        else:
            start = _parse_date(window.get("start"), "rules.retail_market.annual_window.start", errors)
            end = _parse_date(window.get("end"), "rules.retail_market.annual_window.end", errors)
            if start is not None and end is not None and start >= end:
                errors.append("rules.retail_market.annual_window.start 必须早于 end")
        cancelled = retail_market.get("cancelled")
        if not isinstance(cancelled, list) or len(cancelled) < 2:
            errors.append("rules.retail_market.cancelled 必须列出取消的套餐机制")
        if retail_market.get("one_household_one_price") is not True:
            errors.append("rules.retail_market.one_household_one_price 必须为 true")

    price_formula = rules.get("price_formula", {}) if isinstance(rules, dict) else {}
    if isinstance(price_formula, dict):
        for key in ("wholesale", "reference", "cap", "settlement", "tou_constraint"):
            _text(price_formula, key, "rules.price_formula", errors)

    allocation_rule = rules.get("allocation", {}) if isinstance(rules, dict) else {}
    if isinstance(allocation_rule, dict):
        categories = allocation_rule.get("categories")
        if not isinstance(categories, dict) or set(categories) != {"cost_compensation", "imbalance", "market_adjustment"}:
            errors.append("rules.allocation.categories 必须包含三类分摊科目")
        table = allocation_rule.get("monthly_reference_2026")
        if not isinstance(table, dict) or len(table) < 6:
            errors.append("rules.allocation.monthly_reference_2026 至少需要 6 个月参考值")
        else:
            for month, values in table.items():
                where = f"rules.allocation.monthly_reference_2026.{month}"
                if not MONTH_RE.match(month):
                    errors.append(f"{where} 月份键必须是 YYYY-MM")
                    continue
                if not isinstance(values, dict):
                    errors.append(f"{where} 必须是对象")
                    continue
                parts = []
                for key in ("cost_compensation", "imbalance", "market_adjustment"):
                    value = values.get(key)
                    if not _is_number(value):
                        errors.append(f"{where}.{key} 必须是数字")
                    else:
                        parts.append(float(value))
                total = values.get("total")
                if len(parts) == 3 and _is_number(total) and abs(sum(parts) - float(total)) > 1e-9:
                    errors.append(f"{where}.total 必须等于三项之和")
        base_month = _text(allocation_rule, "base_month", "rules.allocation", errors)
        if base_month is not None and isinstance(table, dict) and base_month not in table:
            errors.append("rules.allocation.base_month 必须存在于 monthly_reference_2026")
        _text(allocation_rule, "reported_range", "rules.allocation", errors)
        _text(allocation_rule, "status", "rules.allocation", errors)

    guarantee_rule = rules.get("guarantee", {}) if isinstance(rules, dict) else {}
    if isinstance(guarantee_rule, dict):
        current = guarantee_rule.get("current")
        if not isinstance(current, dict):
            errors.append("rules.guarantee.current 缺失")
        else:
            _text(current, "formula", "rules.guarantee.current", errors)
            _text(current, "document", "rules.guarantee.current", errors)
        draft = guarantee_rule.get("draft_2026_09_04")
        if isinstance(draft, dict) and draft.get("effective") is True:
            errors.append("rules.guarantee.draft_2026_09_04 是草案，effective 不能为 true")
        if isinstance(draft, dict) and draft.get("effective") is False:
            warnings.append("2026-09-04 售电办法修订稿是草案，本包未按草案保函公式测算")

    settlement = rules.get("settlement", {}) if isinstance(rules, dict) else {}
    if isinstance(settlement, dict):
        _text(settlement, "timeline", "rules.settlement", errors)
        _text(settlement, "document", "rules.settlement", errors)
        _text(settlement, "retail_basis", "rules.settlement", errors)

    portfolio = config.get("portfolio")
    if not isinstance(portfolio, dict):
        errors.append("缺少 portfolio 块")
        portfolio = {}
    segments = _list(portfolio.get("segments"), "portfolio.segments", errors)
    share_sum = 0.0
    names = []
    green_segments = []
    for index, segment in enumerate(segments):
        where = f"portfolio.segments[{index}]"
        if not isinstance(segment, dict):
            errors.append(f"{where} 必须是对象")
            continue
        name = _text(segment, "name", where, errors)
        if name is not None:
            if name in names:
                errors.append(f"{where}.name 重复：{name}")
            names.append(name)
        package_type = _text(segment, "package_type", where, errors)
        if package_type is not None and package_type != PACKAGE_TYPE:
            errors.append(f"{where}.package_type 必须为 {PACKAGE_TYPE}；2027 指引已取消固定价/现货联动电量比例/比例分成")
        share = _number(segment, "share", where, errors, minimum=0.0, maximum=1.0)
        if share is not None:
            share_sum += share
        _number(segment, "tilt", where, errors, minimum=-1.0, maximum=1.0)
        _number(segment, "forecast_sigma_pct", where, errors, minimum=0.0, maximum=1.0)
        _number(segment, "opex_cny_per_mwh", where, errors, minimum=0.0)
        green = segment.get("green_power")
        if not isinstance(green, bool):
            errors.append(f"{where}.green_power 必须是布尔值")
        elif green:
            green_segments.append(name)
    if segments and abs(share_sum - 1.0) > 1e-9:
        errors.append(f"portfolio.segments 的 share 之和必须为 1，当前为 {share_sum:.6f}")

    _number(portfolio, "annual_energy_mwh", "portfolio", errors, minimum=0.0)
    _number(portfolio, "fixed_cost_cny_per_day", "portfolio", errors, minimum=0.0)

    mix = portfolio.get("wholesale_mix")
    if not isinstance(mix, dict):
        errors.append("portfolio.wholesale_mix 缺失")
    else:
        for key in ("annual_price_cny_per_mwh", "monthly_price_cny_per_mwh", "intra_month_price_cny_per_mwh"):
            _number(mix, key, "portfolio.wholesale_mix", errors, minimum=0.0)
        annual_weight = _number(mix, "annual_weight", "portfolio.wholesale_mix", errors, minimum=0.0, maximum=1.0)
        monthly_weight = _number(mix, "monthly_weight", "portfolio.wholesale_mix", errors, minimum=0.0, maximum=1.0)
        intra_weight = _number(mix, "intra_month_weight", "portfolio.wholesale_mix", errors, minimum=0.0, maximum=1.0)
        da_share = _number(mix, "da_share", "portfolio.wholesale_mix", errors, minimum=0.0, maximum=1.0)
        rt_share = _number(mix, "rt_share", "portfolio.wholesale_mix", errors, minimum=0.0, maximum=1.0)
        if annual_weight is not None and monthly_weight is not None and intra_weight is not None:
            if abs(annual_weight + monthly_weight + intra_weight - 1.0) > 1e-9:
                errors.append("portfolio.wholesale_mix 的年度/月度/月内权重之和必须为 1")
        if da_share is not None and rt_share is not None and da_share + rt_share > 1.0 + 1e-12:
            errors.append("portfolio.wholesale_mix 的 da_share + rt_share 不能大于 1")
        _text(mix, "basis", "portfolio.wholesale_mix", errors)

    green_power = portfolio.get("green_power")
    if not isinstance(green_power, dict):
        errors.append("portfolio.green_power 缺失")
    else:
        segment_name = _text(green_power, "segment", "portfolio.green_power", errors)
        if segment_name is not None and green_segments and segment_name not in green_segments:
            errors.append("portfolio.green_power.segment 必须对应一个 green_power=true 的客户群")
        for key in ("energy_premium_cny_per_mwh", "environmental_value_cny_per_mwh", "environmental_cost_cny_per_mwh"):
            _number(green_power, key, "portfolio.green_power", errors, minimum=0.0)
        _text(green_power, "basis", "portfolio.green_power", errors)

    guarantee = portfolio.get("guarantee")
    if not isinstance(guarantee, dict):
        errors.append("portfolio.guarantee 缺失")
    else:
        amount = _number(guarantee, "amount_cny", "portfolio.guarantee", errors, minimum=0.0)
        rate = _number(guarantee, "annual_funding_rate", "portfolio.guarantee", errors, minimum=0.0)
        annual = _number(guarantee, "annual_wholesale_mwh", "portfolio.guarantee", errors, minimum=0.0)
        peak = _number(guarantee, "peak_two_month_mwh", "portfolio.guarantee", errors, minimum=0.0)
        _text(guarantee, "basis", "portfolio.guarantee", errors)
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
    _text(policy, "profile_id", "policy", errors)
    mode = _text(policy, "pricing_mode", "policy", errors)
    if mode is not None and mode not in {"flat", "tou"}:
        errors.append("policy.pricing_mode 只能为 flat 或 tou")
    _number(policy, "retail_float_cny_per_mwh", "policy", errors, minimum=0.0)
    _number(policy, "cap_float_factor", "policy", errors, minimum=0.0, maximum=1.0)
    coefficients = policy.get("allocation_coefficients")
    if not isinstance(coefficients, dict) or set(coefficients) != {"cost_compensation", "imbalance", "market_adjustment"}:
        errors.append("policy.allocation_coefficients 必须包含三类分摊系数")
    else:
        for key, value in coefficients.items():
            if not _is_number(value) or not 0.0 <= float(value) <= 1.0:
                errors.append(f"policy.allocation_coefficients.{key} 必须在 [0, 1] 内")
    _number(policy, "price_reference_quantile", "policy", errors, minimum=0.0, maximum=1.0)
    for key in ("stress_spot_multipliers", "stress_cap_factors", "stress_floats", "stress_allocation_pass_through"):
        values = _list(policy.get(key), f"policy.{key}", errors)
        for value in values:
            if not _is_number(value) or float(value) < 0:
                errors.append(f"policy.{key} 必须全部为非负数字")
                break
    top_slots = policy.get("review_top_slots")
    if top_slots is not None and (not isinstance(top_slots, int) or top_slots < 0):
        errors.append("policy.review_top_slots 必须是非负整数")

    contracts = config.get("contracts")
    if not isinstance(contracts, dict):
        errors.append("缺少 contracts 块")
        contracts = {}
    retail_contract = contracts.get("retail_2027")
    if not isinstance(retail_contract, dict):
        errors.append("contracts.retail_2027 缺失")
    else:
        _text(retail_contract, "contract_id", "contracts.retail_2027", errors)
        contract_type = _text(retail_contract, "type", "contracts.retail_2027", errors)
        if contract_type is not None and contract_type != "annual_retail_pass_through":
            errors.append("contracts.retail_2027.type 必须为 annual_retail_pass_through")
        signed = _parse_date(retail_contract.get("signed_date"), "contracts.retail_2027.signed_date", errors)
        trade = _parse_date(retail_contract.get("retail_trade_date"), "contracts.retail_2027.retail_trade_date", errors)
        wholesale = _parse_date(retail_contract.get("annual_wholesale_date"), "contracts.retail_2027.annual_wholesale_date", errors)
        if trade is not None and wholesale is not None and trade >= wholesale:
            errors.append("contracts.retail_2027.retail_trade_date 必须早于 annual_wholesale_date")
        if retail_contract.get("one_household_one_price") is not True:
            errors.append("contracts.retail_2027.one_household_one_price 必须为 true")
        _grade(retail_contract, "contracts.retail_2027", errors)
        if signed is not None and isinstance(retail_market.get("annual_window"), dict):
            start = _parse_date(retail_market["annual_window"].get("start"), "annual_window.start", [])
            end = _parse_date(retail_market["annual_window"].get("end"), "annual_window.end", [])
            if start is not None and end is not None and not (start <= signed <= end):
                warnings.append("contracts.retail_2027.signed_date 不在 2026-10-16–2026-12-24 年度交易窗口内")
    green_contract = contracts.get("green_power")
    if not isinstance(green_contract, dict):
        errors.append("contracts.green_power 缺失")
    else:
        _text(green_contract, "contract_id", "contracts.green_power", errors)
        contract_type = _text(green_contract, "type", "contracts.green_power", errors)
        if contract_type is not None and contract_type != "green_power_split":
            errors.append("contracts.green_power.type 必须为 green_power_split")
        _text(green_contract, "energy_contract", "contracts.green_power", errors)
        _text(green_contract, "environmental_contract", "contracts.green_power", errors)
        if green_contract.get("signed") is not True:
            errors.append("contracts.green_power.signed 必须为 true")
        _grade(green_contract, "contracts.green_power", errors)
    if green_segments and not isinstance(green_contract, dict):
        warnings.append("存在绿电客户群但未配置绿电拆分合同")

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
            _text(block, field, f"data_contract.{key}", errors)
        _grade(block, f"data_contract.{key}", errors)
    d1_contract = data_contract.get("d1", {}) if isinstance(data_contract.get("d1"), dict) else {}
    scenario_fields = _list(d1_contract.get("scenario_fields"), "data_contract.d1.scenario_fields", errors)
    weights = _list(d1_contract.get("scenario_weights"), "data_contract.d1.scenario_weights", errors)
    if scenario_fields and weights:
        if len(scenario_fields) != len(weights):
            errors.append("data_contract.d1.scenario_fields 与 scenario_weights 长度不一致")
        elif abs(sum(float(w) for w in weights if _is_number(w)) - 1.0) > 1e-9:
            errors.append("data_contract.d1.scenario_weights 之和必须为 1")
    t1_contract = data_contract.get("t1", {}) if isinstance(data_contract.get("t1"), dict) else {}
    _text(t1_contract, "price_field", "data_contract.t1", errors)
    allocation_fields = t1_contract.get("allocation_fields")
    if not isinstance(allocation_fields, list) or len(allocation_fields) != 3:
        errors.append("data_contract.t1.allocation_fields 必须是三个字段")

    if meta.get("grade") == "D":
        warnings.append("实例客户、合约、分摊与演示数据为 D 级合成，不得直接用于真实报价或签约")
    if isinstance(allocation_rule, dict):
        warnings.append("2026 年 1–8 月分摊值为参考值，2027 年按月公布；实际结算必须使用当月公布值")
    if isinstance(price_formula, dict):
        warnings.append("F 由购售双方约定，不是规则固定常数；本包按 policy.cap_float_factor 建模")
    if isinstance(portfolio.get("wholesale_mix"), dict):
        warnings.append("演示中日前与实时取同一情景价；实际应分别提供日前/实时曲线")
    if isinstance(retail_market, dict):
        warnings.append("年度交易窗口与“批发交易前 5 个工作日完成零售交易”为公开解读口径，以交易平台公告为准")
    if isinstance(settlement, dict) and "未明确" in str(settlement.get("retail_deviation_status", "")):
        warnings.append("2027 指引未明确零售偏差统一考核口径；本包不计偏差考核")
    if mode == "flat":
        warnings.append("本包为平段套餐，未触发分时套餐的峰谷约束；分时套餐峰段≥1.6×平段、谷段≤0.4×平段")
    if green_segments:
        warnings.append("绿电拆分按“封顶只作用于电能量传导部分、环境价值单独结算”建模，属 D 级解释")

    if errors:
        raise ConfigError("配置校验失败：\n- " + "\n- ".join(errors))

    fingerprint = hashlib.sha1(
        json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    provenance = []
    for name in RULE_BLOCKS:
        block = rules[name]
        provenance.append({"block": f"rules.{name}", "grade": block["grade"], "source": block["source"]})
    provenance.append({"block": "portfolio", "grade": "D", "source": "客户群、合约价、分摊系数与保函参数为示例占位"})
    provenance.append({"block": "contracts", "grade": "D", "source": "示例合同；日期与客户数不对应任何真实主体"})
    provenance.append({"block": "data_contract", "grade": "D", "source": "本包输入契约；演示数据由 make_demo.py 生成"})

    return {
        "ok": True,
        "errors": [],
        "warnings": warnings,
        "points_per_day": int(points),
        "mtu_min": int(mtu),
        "style_fingerprint": fingerprint,
        "provenance": provenance,
        "base_month": allocation_rule.get("base_month"),
        "annual_window": retail_market.get("annual_window"),
        "retail_trade_date": retail_contract.get("retail_trade_date") if isinstance(retail_contract, dict) else None,
        "annual_wholesale_date": retail_contract.get("annual_wholesale_date") if isinstance(retail_contract, dict) else None,
        "pricing_mode": mode,
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
    return {
        "path": str(path),
        "date": date,
        "slots": list(range(points)),
        "interval_hours": report["mtu_min"] / 60.0,
        "load": load,
        "scenario_fields": scenario_fields,
        "scenarios": scenarios,
        "weights": [float(value) for value in contract["scenario_weights"]],
    }


def read_t1(path, config, report, expected_date):
    contract = config["data_contract"]["t1"]
    allocation_fields = list(contract["allocation_fields"])
    fields = ["date", "slot", contract["load_field"], contract["price_field"]] + allocation_fields
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
    allocation = {field: [] for field in allocation_fields}
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
        for field in allocation_fields:
            allocation[field].append(_parse_float(row[field], f"{where} {field}"))
    return {
        "path": str(path),
        "date": date,
        "slots": list(range(points)),
        "interval_hours": report["mtu_min"] / 60.0,
        "load": load,
        "price": price,
        "allocation": allocation,
    }


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


def _mt_price(config):
    mix = config["portfolio"]["wholesale_mix"]
    return (
        float(mix["annual_price_cny_per_mwh"]) * float(mix["annual_weight"])
        + float(mix["monthly_price_cny_per_mwh"]) * float(mix["monthly_weight"])
        + float(mix["intra_month_price_cny_per_mwh"]) * float(mix["intra_month_weight"])
    )


def _wholesale_curve(config, price_curve):
    mix = config["portfolio"]["wholesale_mix"]
    mt = _mt_price(config)
    da_share = float(mix["da_share"])
    rt_share = float(mix["rt_share"])
    mt_share = 1.0 - da_share - rt_share
    return [mt_share * mt + da_share * price + rt_share * price for price in price_curve]


def _reference_price_curve(config, price_curve):
    mix = config["portfolio"]["wholesale_mix"]
    annual = float(mix["annual_price_cny_per_mwh"])
    monthly = float(mix["monthly_price_cny_per_mwh"])
    intra = float(mix["intra_month_price_cny_per_mwh"])
    return [max(annual, monthly, intra, price, price) for price in price_curve]


def _plan_allocation(config, month=None):
    table = config["rules"]["allocation"]["monthly_reference_2026"]
    key = month or config["rules"]["allocation"]["base_month"]
    values = table[key]
    return {name: float(values[name]) for name in ("cost_compensation", "imbalance", "market_adjustment")}


def _actual_allocation(t1):
    fields = ("actual_p1", "actual_p2", "actual_p3")
    keys = ("cost_compensation", "imbalance", "market_adjustment")
    total = sum(t1["load"])
    return {
        key: sum(value * load for value, load in zip(t1["allocation"][field], t1["load"])) / total
        for key, field in zip(keys, fields)
    }


def _split_load(total_load, segments):
    average = sum(total_load) / len(total_load)
    result = {}
    for segment in segments:
        tilt = float(segment["tilt"])
        raw = [
            float(segment["share"]) * load * (1.0 + tilt * (load / average - 1.0))
            for load in total_load
        ]
        target = float(segment["share"]) * sum(total_load)
        scale = target / sum(raw)
        result[segment["name"]] = [value * scale for value in raw]
    return result


def _segment_metrics(config, segment, seg_load, wholesale_curve, reference_curve, allocation,
                     float_value, cap_factor, k_scale, interval):
    energy = sum(seg_load) * interval
    total_load = sum(seg_load)
    wholesale_avg = sum(p * q for p, q in zip(wholesale_curve, seg_load)) / total_load
    reference_avg = sum(p * q for p, q in zip(reference_curve, seg_load)) / total_load
    coefficients = config["policy"]["allocation_coefficients"]
    alloc_retail = sum(
        float(coefficients[key]) * allocation[key] for key in allocation
    ) * k_scale
    alloc_cost = sum(allocation.values())
    retail_before_cap = wholesale_avg + float_value + alloc_retail
    cap = reference_avg + cap_factor * wholesale_avg + alloc_retail
    settled = min(retail_before_cap, cap)
    clip = max(0.0, retail_before_cap - cap)
    headroom = cap - retail_before_cap
    break_even_float = cap - wholesale_avg - alloc_retail
    revenue = settled * energy
    procurement = wholesale_avg * energy
    allocation_cost = alloc_cost * energy
    opex = float(segment["opex_cny_per_mwh"]) * energy
    green = config["portfolio"]["green_power"]
    green_margin = 0.0
    energy_premium = 0.0
    environmental_value = 0.0
    if segment.get("green_power"):
        energy_premium = float(green["energy_premium_cny_per_mwh"])
        environmental_value = float(green["environmental_value_cny_per_mwh"])
        green_margin = (environmental_value - float(green["environmental_cost_cny_per_mwh"])) * energy
    gross_net = revenue - procurement - allocation_cost
    net = gross_net + green_margin - opex
    return {
        "segment": segment["name"],
        "share": float(segment["share"]),
        "tilt": float(segment["tilt"]),
        "package_type": segment["package_type"],
        "energy_mwh": energy,
        "wholesale_avg_cny_per_mwh": wholesale_avg,
        "reference_avg_cny_per_mwh": reference_avg,
        "allocation_retail_cny_per_mwh": alloc_retail,
        "allocation_cost_cny_per_mwh": alloc_cost,
        "float_cny_per_mwh": float_value,
        "retail_before_cap_cny_per_mwh": retail_before_cap,
        "cap_cny_per_mwh": cap,
        "settled_price_cny_per_mwh": settled,
        "clip_cny_per_mwh": clip,
        "headroom_cny_per_mwh": headroom,
        "break_even_float_cny_per_mwh": break_even_float,
        "revenue_cny": revenue,
        "procurement_cny": procurement,
        "allocation_cost_cny": allocation_cost,
        "opex_cny": opex,
        "green_margin_cny": green_margin,
        "green_energy_premium_cny_per_mwh": energy_premium,
        "environmental_value_cny_per_mwh": environmental_value,
        "all_in_price_cny_per_mwh": settled + energy_premium + environmental_value,
        "gross_net_cny": gross_net,
        "net_cny": net,
        "net_per_mwh_cny": net / energy if energy > 0 else 0.0,
        "capped": clip > 1e-9,
    }


def portfolio_metrics(config, load, wholesale_price_curve, reference_price_curve, allocation,
                      float_value=None, cap_factor=None, k_scale=1.0):
    policy = config["policy"]
    float_value = float(policy["retail_float_cny_per_mwh"] if float_value is None else float_value)
    cap_factor = float(policy["cap_float_factor"] if cap_factor is None else cap_factor)
    interval = 15.0 / 60.0
    segments = config["portfolio"]["segments"]
    split = _split_load(load, segments)
    wholesale_curve = _wholesale_curve(config, wholesale_price_curve)
    reference_curve = _reference_price_curve(config, reference_price_curve)
    rows = [
        _segment_metrics(
            config, segment, split[segment["name"]], wholesale_curve, reference_curve,
            allocation, float_value, cap_factor, k_scale, interval,
        )
        for segment in segments
    ]
    energy = sum(row["energy_mwh"] for row in rows)
    revenue = sum(row["revenue_cny"] for row in rows)
    procurement = sum(row["procurement_cny"] for row in rows)
    allocation_cost = sum(row["allocation_cost_cny"] for row in rows)
    variable_opex = sum(row["opex_cny"] for row in rows)
    green_margin = sum(row["green_margin_cny"] for row in rows)
    gross_net = sum(row["gross_net_cny"] for row in rows)
    fixed_cost = float(config["portfolio"]["fixed_cost_cny_per_day"])
    guarantee = config["portfolio"]["guarantee"]
    guarantee_daily = float(guarantee["amount_cny"]) * float(guarantee["annual_funding_rate"]) / 365.0
    net = gross_net + green_margin - variable_opex - fixed_cost - guarantee_daily
    clip_cny = sum(row["clip_cny_per_mwh"] * row["energy_mwh"] for row in rows)

    def weighted(field):
        return sum(row[field] * row["energy_mwh"] for row in rows) / energy if energy > 0 else 0.0

    return {
        "rows": rows,
        "energy_mwh": energy,
        "float_cny_per_mwh": float_value,
        "cap_float_factor": cap_factor,
        "allocation_scale": k_scale,
        "revenue_cny": revenue,
        "procurement_cny": procurement,
        "allocation_cost_cny": allocation_cost,
        "variable_opex_cny": variable_opex,
        "green_margin_cny": green_margin,
        "gross_net_cny": gross_net,
        "fixed_cost_cny": fixed_cost,
        "guarantee_daily_cny": guarantee_daily,
        "net_cny": net,
        "net_per_mwh_cny": net / energy if energy > 0 else 0.0,
        "clip_cny": clip_cny,
        "clip_avg_cny_per_mwh": clip_cny / energy if energy > 0 else 0.0,
        "weighted_reference_cny_per_mwh": weighted("reference_avg_cny_per_mwh"),
        "weighted_wholesale_cny_per_mwh": weighted("wholesale_avg_cny_per_mwh"),
        "weighted_cap_cny_per_mwh": weighted("cap_cny_per_mwh"),
        "weighted_retail_cny_per_mwh": weighted("retail_before_cap_cny_per_mwh"),
        "weighted_settled_cny_per_mwh": weighted("settled_price_cny_per_mwh"),
        "weighted_headroom_cny_per_mwh": weighted("headroom_cny_per_mwh"),
        "capped_segments": sum(1 for row in rows if row["capped"]),
        "mt_price_cny_per_mwh": _mt_price(config),
    }


def build_plan(config, d1, ref_curve, allocation):
    metrics = portfolio_metrics(config, d1["load"], ref_curve, ref_curve, allocation)
    metrics["scenario"] = "plan"
    return metrics


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


def build_scenarios(config, d1, ref_curve, allocation):
    rows = []
    for field, weight in zip(d1["scenario_fields"], d1["weights"]):
        metrics = portfolio_metrics(
            config, d1["load"], d1["scenarios"][field], d1["scenarios"][field], allocation
        )
        rows.append(
            {
                "scenario": field,
                "weight": weight,
                "average_spot_cny_per_mwh": sum(d1["scenarios"][field]) / len(d1["scenarios"][field]),
                "wholesale_avg_cny_per_mwh": metrics["weighted_wholesale_cny_per_mwh"],
                "reference_avg_cny_per_mwh": metrics["weighted_reference_cny_per_mwh"],
                "cap_avg_cny_per_mwh": metrics["weighted_cap_cny_per_mwh"],
                "retail_avg_cny_per_mwh": metrics["weighted_retail_cny_per_mwh"],
                "clip_avg_cny_per_mwh": metrics["clip_avg_cny_per_mwh"],
                "revenue_cny": metrics["revenue_cny"],
                "procurement_cny": metrics["procurement_cny"],
                "allocation_cost_cny": metrics["allocation_cost_cny"],
                "green_margin_cny": metrics["green_margin_cny"],
                "opex_cny": metrics["variable_opex_cny"] + metrics["fixed_cost_cny"] + metrics["guarantee_daily_cny"],
                "net_cny": metrics["net_cny"],
                "net_per_mwh_cny": metrics["net_per_mwh_cny"],
                "capped_segments": metrics["capped_segments"],
            }
        )
    expected = sum(row["weight"] * row["net_cny"] for row in rows)
    cvar = _weighted_cvar([row["net_cny"] for row in rows], [row["weight"] for row in rows], 0.10)
    return {
        "rows": rows,
        "expected_net_cny": expected,
        "cvar_10_cny": cvar,
        "plan": build_plan(config, d1, ref_curve, allocation),
    }


def build_stress(config, d1, ref_curve, allocation):
    policy = config["policy"]
    energy = sum(d1["load"]) * d1["interval_hours"]
    spot_rows = []
    for multiplier in policy["stress_spot_multipliers"]:
        curve = [price * float(multiplier) for price in ref_curve]
        metrics = portfolio_metrics(config, d1["load"], curve, curve, allocation)
        spot_rows.append(
            {
                "type": "spot",
                "parameter": "multiplier",
                "value": float(multiplier),
                "net_cny": metrics["net_cny"],
                "net_per_mwh_cny": metrics["net_per_mwh_cny"],
                "clip_avg_cny_per_mwh": metrics["clip_avg_cny_per_mwh"],
                "capped_segments": metrics["capped_segments"],
                "note": "参考情景价格整体倍数",
            }
        )
    cap_rows = []
    for factor in policy["stress_cap_factors"]:
        metrics = portfolio_metrics(config, d1["load"], ref_curve, ref_curve, allocation, cap_factor=float(factor))
        cap_rows.append(
            {
                "type": "cap_factor",
                "parameter": "F",
                "value": float(factor),
                "net_cny": metrics["net_cny"],
                "net_per_mwh_cny": metrics["net_per_mwh_cny"],
                "clip_avg_cny_per_mwh": metrics["clip_avg_cny_per_mwh"],
                "capped_segments": metrics["capped_segments"],
                "note": "F 由购售双方约定；越高封顶越松",
            }
        )
    float_rows = []
    for value in policy["stress_floats"]:
        metrics = portfolio_metrics(config, d1["load"], ref_curve, ref_curve, allocation, float_value=float(value))
        float_rows.append(
            {
                "type": "float",
                "parameter": "P_float",
                "value": float(value),
                "net_cny": metrics["net_cny"],
                "net_per_mwh_cny": metrics["net_per_mwh_cny"],
                "clip_avg_cny_per_mwh": metrics["clip_avg_cny_per_mwh"],
                "capped_segments": metrics["capped_segments"],
                "note": "浮动价越高，越容易触顶",
            }
        )
    pass_rows = []
    for scale in policy["stress_allocation_pass_through"]:
        metrics = portfolio_metrics(config, d1["load"], ref_curve, ref_curve, allocation, k_scale=float(scale))
        pass_rows.append(
            {
                "type": "allocation_pass_through",
                "parameter": "K 缩放",
                "value": float(scale),
                "net_cny": metrics["net_cny"],
                "net_per_mwh_cny": metrics["net_per_mwh_cny"],
                "clip_avg_cny_per_mwh": metrics["clip_avg_cny_per_mwh"],
                "capped_segments": metrics["capped_segments"],
                "note": "0=全部由售电公司吸收，1=全部传导",
            }
        )
    table = config["rules"]["allocation"]["monthly_reference_2026"]
    month_rows = []
    for month in sorted(table):
        values = table[month]
        alloc = {key: float(values[key]) for key in ("cost_compensation", "imbalance", "market_adjustment")}
        metrics = portfolio_metrics(config, d1["load"], ref_curve, ref_curve, alloc)
        month_rows.append(
            {
                "type": "allocation_month",
                "parameter": month,
                "value": float(values["total"]),
                "net_cny": metrics["net_cny"],
                "net_per_mwh_cny": metrics["net_per_mwh_cny"],
                "clip_avg_cny_per_mwh": metrics["clip_avg_cny_per_mwh"],
                "capped_segments": metrics["capped_segments"],
                "note": f"分摊合计 {values['total']:.2f} CNY/MWh",
            }
        )
    return {
        "energy_mwh": energy,
        "spot": spot_rows,
        "cap_factor": cap_rows,
        "float": float_rows,
        "allocation_pass_through": pass_rows,
        "allocation_month": month_rows,
    }


def build_bridge(config, d1, t1, ref_curve, plan_allocation):
    plan = build_plan(config, d1, ref_curve, plan_allocation)
    actual_allocation = _actual_allocation(t1)
    actual = portfolio_metrics(config, t1["load"], t1["price"], t1["price"], actual_allocation)
    step1 = portfolio_metrics(config, d1["load"], t1["price"], ref_curve, plan_allocation)
    step2 = portfolio_metrics(config, d1["load"], t1["price"], t1["price"], plan_allocation)
    step3 = portfolio_metrics(config, t1["load"], t1["price"], t1["price"], plan_allocation)
    step4 = portfolio_metrics(config, t1["load"], t1["price"], t1["price"], actual_allocation)
    buckets = [
        {
            "item": "批发价差",
            "category": "市场",
            "owner": "批发市场价格",
            "amount": step1["gross_net_cny"] - plan["gross_net_cny"],
        },
        {
            "item": "参考价差",
            "category": "规则",
            "owner": "封顶参考价",
            "amount": step2["gross_net_cny"] - step1["gross_net_cny"],
        },
        {
            "item": "负荷量差",
            "category": "客户",
            "owner": "客户负荷",
            "amount": step3["gross_net_cny"] - step2["gross_net_cny"],
        },
        {
            "item": "分摊价差",
            "category": "规则",
            "owner": "月度分摊",
            "amount": step4["gross_net_cny"] - step3["gross_net_cny"],
        },
        {
            "item": "绿电环境价值",
            "category": "合同",
            "owner": "绿电合同",
            "amount": step4["green_margin_cny"] - plan["green_margin_cny"],
        },
        {
            "item": "运营成本",
            "category": "运营",
            "owner": "售电公司",
            "amount": -(step4["variable_opex_cny"] - plan["variable_opex_cny"]),
        },
    ]
    delta = actual["net_cny"] - plan["net_cny"]
    identity_gap = plan["net_cny"] + sum(bucket["amount"] for bucket in buckets) - actual["net_cny"]
    no_cap = portfolio_metrics(
        config, t1["load"], t1["price"], t1["price"], actual_allocation, cap_factor=1e9
    )
    cap_impact = actual["net_cny"] - no_cap["net_cny"]

    mtu_min = int(round(d1["interval_hours"] * 60))
    plan_wholesale = _wholesale_curve(config, ref_curve)
    actual_wholesale = _wholesale_curve(config, t1["price"])
    actual_reference = _reference_price_curve(config, t1["price"])
    detail = []
    for slot in range(len(d1["load"])):
        deviation = t1["load"][slot] - d1["load"][slot]
        detail.append(
            {
                "slot": slot,
                "start": _slot_start(slot, mtu_min),
                "end": _slot_end(slot, mtu_min),
                "forecast_load_mw": d1["load"][slot],
                "actual_load_mw": t1["load"][slot],
                "load_deviation_mw": deviation,
                "deviation_share": deviation / d1["load"][slot] if d1["load"][slot] > 0 else 0.0,
                "plan_wholesale_cny_per_mwh": plan_wholesale[slot],
                "actual_wholesale_cny_per_mwh": actual_wholesale[slot],
                "actual_reference_layer_cny_per_mwh": actual_reference[slot],
            }
        )
    detail.sort(key=lambda row: abs(row["load_deviation_mw"]), reverse=True)
    top_slots = detail[: int(config["policy"].get("review_top_slots", 5))]

    return {
        "plan_net_cny": plan["net_cny"],
        "actual_net_cny": actual["net_cny"],
        "delta_cny": delta,
        "identity_gap": identity_gap,
        "plan_energy_mwh": plan["energy_mwh"],
        "actual_energy_mwh": actual["energy_mwh"],
        "plan_clip_avg_cny_per_mwh": plan["clip_avg_cny_per_mwh"],
        "actual_clip_avg_cny_per_mwh": actual["clip_avg_cny_per_mwh"],
        "cap_impact_cny": cap_impact,
        "plan": plan,
        "actual": actual,
        "buckets": buckets,
        "top_slots": top_slots,
    }


def _business_day_check(report):
    trade = report.get("retail_trade_date")
    wholesale = report.get("annual_wholesale_date")
    if not trade or not wholesale:
        return None
    start = dt.date.fromisoformat(trade)
    end = dt.date.fromisoformat(wholesale)
    return _business_days_between(start, end)


def build_compliance(config, report, plan, d1, t1):
    items = []
    window = report["annual_window"] or {}
    contract = config["contracts"]["retail_2027"]
    signed = contract["signed_date"]
    start = window.get("start")
    end = window.get("end")
    items.append(
        {
            "item": "年度零售交易窗口",
            "status": "pass" if start and end and start <= signed <= end else "fail",
            "detail": f"签约 {signed}；窗口 {start}–{end}",
        }
    )
    days = _business_day_check(report)
    items.append(
        {
            "item": "批发交易前完成零售交易",
            "status": "pass" if days is not None and days >= 5 else "fail",
            "detail": f"零售交易 {report['retail_trade_date']}，年度批发 {report['annual_wholesale_date']}，间隔 {days} 个工作日（≥5）",
        }
    )
    package_types = {row["package_type"] for row in plan["rows"]}
    items.append(
        {
            "item": "套餐机制",
            "status": "pass" if package_types == {PACKAGE_TYPE} else "fail",
            "detail": f"全部为 {PACKAGE_TYPE}；2027 指引已取消固定价/现货联动电量比例/比例分成",
        }
    )
    items.append(
        {
            "item": "一户一价",
            "status": "pass" if contract.get("one_household_one_price") is True else "fail",
            "detail": "合同约定一户一价；客户群仅通过曲线、运营成本与绿电附加区分，电能量传导价一致",
        }
    )
    coefficients = config["policy"]["allocation_coefficients"]
    items.append(
        {
            "item": "分摊系数范围",
            "status": "pass" if all(0.0 <= float(v) <= 1.0 for v in coefficients.values()) else "fail",
            "detail": "，".join(f"{key}={value}" for key, value in coefficients.items()),
        }
    )
    base_month = config["rules"]["allocation"]["base_month"]
    items.append(
        {
            "item": "分摊基准月",
            "status": "pass" if base_month in config["rules"]["allocation"]["monthly_reference_2026"] else "fail",
            "detail": f"基准月 {base_month}；2027 年按月公布值替换",
        }
    )
    green = config["contracts"]["green_power"]
    items.append(
        {
            "item": "绿电拆分合同",
            "status": "pass" if green.get("signed") is True and green.get("energy_contract") and green.get("environmental_contract") else "fail",
            "detail": f"{green.get('energy_contract')} + {green.get('environmental_contract')}",
        }
    )
    capped = [row for row in plan["rows"] if row["capped"]]
    items.append(
        {
            "item": "封顶价结算",
            "status": "pass" if all(row["settled_price_cny_per_mwh"] <= row["cap_cny_per_mwh"] + 1e-9 for row in plan["rows"]) else "fail",
            "detail": f"{len(capped)}/{len(plan['rows'])} 个客户群触顶；加权封顶扣减 {plan['clip_avg_cny_per_mwh']:.2f} CNY/MWh",
        }
    )
    if report.get("pricing_mode") == "flat":
        items.append(
            {
                "item": "分时套餐峰谷约束",
                "status": "n/a",
                "detail": "平段套餐，不触发；分时套餐要求峰段≥1.6×平段加权、谷段≤0.4×平段加权",
            }
        )
    else:
        items.append(
            {
                "item": "分时套餐峰谷约束",
                "status": "note",
                "detail": "v1 运行器只实现平段套餐；分时套餐需另建曲线并按 1.6/0.4 校验",
            }
        )
    items.append(
        {
            "item": "零售偏差考核",
            "status": "note",
            "detail": "2027 指引未明确统一口径；本包不计，按合同约定另行测算",
        }
    )
    spot = config["rules"]["spot"]
    floor = float(spot["clear_floor_cny_per_mwh"])
    cap = float(spot["clear_cap_cny_per_mwh"])
    all_prices = [price for curve in d1["scenarios"].values() for price in curve] + list(t1["price"])
    items.append(
        {
            "item": "现货价格边界",
            "status": "pass" if all(floor - 1e-9 <= price <= cap + 1e-9 for price in all_prices) else "fail",
            "detail": f"D-1 与 T+1 价格均在 {floor:.0f}–{cap:.0f} CNY/MWh",
        }
    )
    guarantee = config["portfolio"]["guarantee"]
    required = max(
        float(guarantee["annual_wholesale_mwh"]) * 8.0,
        float(guarantee["peak_two_month_mwh"]) * 50.0,
    )
    amount = float(guarantee["amount_cny"])
    items.append(
        {
            "item": "履约保函金额",
            "status": "pass" if abs(amount - required) <= max(1.0, 0.01 * required) else "warn",
            "detail": f"填写 {amount:,.0f} CNY；1595 号公式值 {required:,.0f} CNY",
        }
    )
    return items


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, float):
        if field in {"share", "tilt"}:
            return f"{value:.3f}"
        if field in {"forecast_load_mw", "actual_load_mw", "load_deviation_mw", "deviation_share"}:
            return f"{0.0 if abs(value) < 1e-9 else value:.6f}"
        if field.endswith("_cny") or field.endswith("_cny_per_mwh"):
            return f"{0.0 if abs(value) < 0.005 else value:.2f}"
        return f"{0.0 if abs(value) < 1e-9 else value:.4f}"
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


def _signed(value):
    return "—" if value is None else f"{value:+,.0f}"


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def write_review(path, config, report, d1, t1, plan, scenarios, stress, bridge, compliance):
    meta = config["meta"]
    policy = config["policy"]
    lines = [
        "# 江苏 2027 售电零售复核表（D 级合成样板）",
        "",
        f"- 实例：`{meta['instance_id']}`",
        f"- 规则版本：{meta['rule_version']}",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']} 分钟；代表日代理月度结算）",
        f"- 风格档：`{policy['profile_id']}`，指纹 `{report['style_fingerprint']}`",
        f"- 口径：{meta['scope']}",
        "",
        "## 1. 来源与警告",
        "",
    ]
    lines += _table(
        ["块", "级别", "来源"],
        [[row["block"], row["grade"], row["source"]] for row in report["provenance"]],
    )
    if report["warnings"]:
        lines += ["", "**警告**", ""]
        lines += [f"- {warning}" for warning in report["warnings"]]
    lines += [
        "",
        "## 2. 结论",
        "",
        f"- 组合电量：{_num(plan['energy_mwh'], 1)} MWh；批发均价 {_num(plan['weighted_wholesale_cny_per_mwh'])} CNY/MWh；参考价 {_num(plan['weighted_reference_cny_per_mwh'])} CNY/MWh。",
        f"- 零售均价（封顶前）{_num(plan['weighted_retail_cny_per_mwh'])} CNY/MWh；封顶均价 {_num(plan['weighted_cap_cny_per_mwh'])} CNY/MWh；加权扣减 {_num(plan['clip_avg_cny_per_mwh'])} CNY/MWh。",
        f"- 计划净收益：{_money(plan['net_cny'])} CNY（{_num(plan['net_per_mwh_cny'], 2)} CNY/MWh）；{plan['capped_segments']}/{len(plan['rows'])} 个客户群触顶。",
        f"- 情景期望净收益：{_money(scenarios['expected_net_cny'])} CNY；CVaR10：{_money(scenarios['cvar_10_cny'])} CNY。",
    ]
    if bridge is not None:
        lines += [
            f"- 实际净收益：{_money(bridge['actual_net_cny'])} CNY；差异 {_signed(bridge['delta_cny'])} CNY；残差 {bridge['identity_gap']:.2e} CNY。",
            f"- 封顶影响（诊断，不计入桥）：{_signed(bridge['cap_impact_cny'])} CNY。",
        ]
    else:
        lines += ["- 未提供 T+1 数据，本次只出 D-1 定价与情景，不跑差异桥。"]
    lines += [
        "",
        "## 3. 定价公式与月度标量",
        "",
        "```",
        "P_retail   = P_wholesale + P_float + Σ K_i × P_allocation,i",
        "P_wholesale,t = (1−K1−K2) × P_MT,t + K1 × P_DA,t + K2 × P_RT,t",
        "P_ref      = Σ_t max(P_annual, P_monthly, P_intra_month, P_DA, P_RT) × Q_t / ΣQ_t",
        "P_cap      = P_ref + F × P_wholesale + P_allocation",
        "结算价     = min(P_retail 月度均价, P_cap)",
        "```",
        "",
        f"- P_MT = {_num(plan['mt_price_cny_per_mwh'])} CNY/MWh（年度/月度/月内加权）；P_wholesale 均价 = {_num(plan['weighted_wholesale_cny_per_mwh'])} CNY/MWh。",
        f"- P_ref = {_num(plan['weighted_reference_cny_per_mwh'])} CNY/MWh；F = {policy['cap_float_factor']:.2f}；P_float = {_num(policy['retail_float_cny_per_mwh'])} CNY/MWh。",
        f"- 分摊：成本补偿 {config['rules']['allocation']['base_values']['cost_compensation']:.2f}、不平衡 {config['rules']['allocation']['base_values']['imbalance']:.2f}、市场调节 {config['rules']['allocation']['base_values']['market_adjustment']:.2f}，合计 {config['rules']['allocation']['base_values']['total']:.2f} CNY/MWh。",
        f"- 分摊系数：P1={policy['allocation_coefficients']['cost_compensation']}、P2={policy['allocation_coefficients']['imbalance']}、P3={policy['allocation_coefficients']['market_adjustment']}；未传导部分由售电公司吸收。",
        "",
        "### 2026 年 1–8 月分摊参考值（CNY/MWh）",
        "",
    ]
    allocation_rows = []
    for month in sorted(config["rules"]["allocation"]["monthly_reference_2026"]):
        values = config["rules"]["allocation"]["monthly_reference_2026"][month]
        mark = "基准" if month == config["rules"]["allocation"]["base_month"] else ""
        allocation_rows.append([
            month,
            _num(values["cost_compensation"]),
            _num(values["imbalance"]),
            _num(values["market_adjustment"]),
            _num(values["total"]),
            mark,
        ])
    lines += _table(["月份", "P1 成本补偿", "P2 不平衡", "P3 市场调节", "合计", "标记"], allocation_rows)
    lines += [
        "",
        f"报道口径月度范围：{config['rules']['allocation']['reported_range']}。2027 年按月公布，结算必须使用当月值。",
        "",
        "## 4. 一户一价封顶（客户群）",
        "",
    ]
    segment_rows = [
        [
            row["segment"],
            _pct(row["share"]),
            _num(row["tilt"], 2),
            _num(row["reference_avg_cny_per_mwh"]),
            _num(row["wholesale_avg_cny_per_mwh"]),
            _num(row["cap_cny_per_mwh"]),
            _num(row["retail_before_cap_cny_per_mwh"]),
            _num(row["clip_cny_per_mwh"]),
            _num(row["headroom_cny_per_mwh"]),
            _num(row["break_even_float_cny_per_mwh"]),
            _num(row["net_per_mwh_cny"], 2),
        ]
        for row in plan["rows"]
    ]
    lines += _table(
        ["客户群", "份额", "曲线 tilt", "P_ref", "P_wholesale", "P_cap", "零售价", "扣减", "余量", "保本浮动价", "净收益/MWh"],
        segment_rows,
    )
    lines += [
        "",
        "tilt > 0 表示负荷更尖峰，tilt < 0 表示更平坦；曲线越尖峰，P_ref 与封顶价越高。净收益/MWh 不含固定成本与保函，固定成本在组合层扣除。",
        "",
        "绿电客户群另签能量包与环境价值包，封顶只作用于电能量传导部分；上表净收益/MWh 含环境价值价差。",
        "",
        "## 5. 情景与 CVaR",
        "",
    ]
    scenario_rows = [
        [
            row["scenario"],
            _pct(row["weight"]),
            _num(row["average_spot_cny_per_mwh"]),
            _num(row["wholesale_avg_cny_per_mwh"]),
            _num(row["reference_avg_cny_per_mwh"]),
            _num(row["cap_avg_cny_per_mwh"]),
            _num(row["clip_avg_cny_per_mwh"]),
            _money(row["net_cny"]),
            row["capped_segments"],
        ]
        for row in scenarios["rows"]
    ]
    lines += _table(
        ["情景", "权重", "现货均价", "批发均价", "P_ref", "封顶均价", "扣减", "净收益 CNY", "触顶群数"],
        scenario_rows,
    )
    lines += [
        "",
        f"期望净收益 {_money(scenarios['expected_net_cny'])} CNY；CVaR10 {_money(scenarios['cvar_10_cny'])} CNY。",
        "",
        "## 6. 压力测试",
        "",
        "### 现货倍数",
        "",
    ]
    lines += _table(
        ["倍数", "净收益 CNY", "净收益/MWh", "封顶扣减/MWh", "触顶群数"],
        [[f"×{row['value']:.2f}", _money(row["net_cny"]), _num(row["net_per_mwh_cny"], 2), _num(row["clip_avg_cny_per_mwh"]), row["capped_segments"]] for row in stress["spot"]],
    )
    lines += ["", "### 封顶系数 F", ""]
    lines += _table(
        ["F", "净收益 CNY", "净收益/MWh", "封顶扣减/MWh", "触顶群数"],
        [[f"{row['value']:.2f}", _money(row["net_cny"]), _num(row["net_per_mwh_cny"], 2), _num(row["clip_avg_cny_per_mwh"]), row["capped_segments"]] for row in stress["cap_factor"]],
    )
    lines += ["", "### 浮动价", ""]
    lines += _table(
        ["P_float", "净收益 CNY", "净收益/MWh", "封顶扣减/MWh", "触顶群数"],
        [[_num(row["value"]), _money(row["net_cny"]), _num(row["net_per_mwh_cny"], 2), _num(row["clip_avg_cny_per_mwh"]), row["capped_segments"]] for row in stress["float"]],
    )
    lines += ["", "### 分摊传导比例", ""]
    lines += _table(
        ["K 缩放", "净收益 CNY", "净收益/MWh", "封顶扣减/MWh"],
        [[f"{row['value']:.1f}", _money(row["net_cny"]), _num(row["net_per_mwh_cny"], 2), _num(row["clip_avg_cny_per_mwh"])] for row in stress["allocation_pass_through"]],
    )
    lines += ["", "### 分摊月份", ""]
    lines += _table(
        ["月份", "分摊合计", "净收益 CNY", "净收益/MWh"],
        [[row["parameter"], _num(row["value"]), _money(row["net_cny"]), _num(row["net_per_mwh_cny"], 2)] for row in stress["allocation_month"]],
    )
    lines += [
        "",
        "## 7. T+1 差异桥",
        "",
    ]
    if bridge is None:
        lines += ["无 T+1 数据。", ""]
    else:
        bridge_rows = [[row["item"], row["category"], row["owner"], _signed(row["amount"])] for row in bridge["buckets"]]
        bridge_rows.append(["残差", "校验", "—", f"{bridge['identity_gap']:.2e}"])
        lines += _table(["科目", "类别", "责任方", "金额 元"], bridge_rows)
        lines += [
            "",
            f"计划 {_money(bridge['plan_net_cny'])} → 实际 {_money(bridge['actual_net_cny'])}，差异 {_signed(bridge['delta_cny'])} CNY；封顶影响 {_signed(bridge['cap_impact_cny'])} CNY（诊断，不计入桥）。",
            "",
            "### 负荷偏差最大的时段",
            "",
        ]
        slot_rows = [
            [
                f"{row['slot']}（{row['start']}–{row['end']}）",
                _num(row["forecast_load_mw"], 2),
                _num(row["actual_load_mw"], 2),
                _num(row["load_deviation_mw"], 2),
                _pct(row["deviation_share"]),
                _num(row["plan_wholesale_cny_per_mwh"]),
                _num(row["actual_wholesale_cny_per_mwh"]),
                _num(row["actual_reference_layer_cny_per_mwh"]),
            ]
            for row in bridge["top_slots"]
        ]
        lines += _table(
            ["时段", "预测 MW", "实际 MW", "偏差 MW", "偏差率", "计划批发价", "实际批发价", "实际参考层"],
            slot_rows,
        )
        lines += [""]
    lines += [
        "## 8. 合规清单",
        "",
    ]
    lines += _table(
        ["检查项", "结果", "说明"],
        [[item["item"], item["status"], item["detail"]] for item in compliance],
    )
    lines += [
        "",
        "## 9. 读法",
        "",
        "- 2027 年固定价套餐退场：电能量价格由批发市场传导 + 浮动价 + 分摊构成，售电公司的可竞争空间主要只剩浮动价与服务。",
        "- 封顶是“一户一价”：曲线越尖峰，P_ref 越高、封顶价越高；平坦负荷的封顶更紧，不能用一个组合平均封顶代替逐户测算。",
        "- F 与浮动价是购售双方约定项：F 越低、浮动价越高，越容易触顶；触顶后售电公司只能拿到封顶价，浮动价被压缩。",
        "- 分摊按月公布、可正可负：本包基准月合计 6.71 CNY/MWh，月度范围约 0.32–6.71；K 系数决定由谁吸收。",
        "- 绿电能量包与环境价值包分开签约、分开结算；封顶只作用于电能量传导部分，环境价值另算。",
        "- 本表只覆盖电能量口径；输配电价、政府性基金、基本电费、税费、坏账、用户流失与零售偏差考核均未计入。",
        "- 代表日只用于演示月度机制；实际结算必须用当月分摊值、月度均价与逐户曲线。",
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
    plan_allocation = _plan_allocation(config)
    plan = build_plan(config, d1, ref_curve, plan_allocation)
    scenarios = build_scenarios(config, d1, ref_curve, plan_allocation)
    stress = build_stress(config, d1, ref_curve, plan_allocation)
    bridge = None if t1 is None else build_bridge(config, d1, t1, ref_curve, plan_allocation)
    compliance = build_compliance(config, report, plan, d1, t1) if t1 is not None else build_compliance(config, report, plan, d1, {"price": ref_curve, "load": d1["load"]})

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    curve_fields = [
        "date", "slot", "start", "end", "forecast_load_mw",
        "p_mt_cny_per_mwh", "p_da_cny_per_mwh", "p_rt_cny_per_mwh",
        "p_wholesale_cny_per_mwh", "p_reference_layer_cny_per_mwh",
        "p_retail_before_cap_cny_per_mwh",
    ]
    mt = plan["mt_price_cny_per_mwh"]
    wholesale_curve = _wholesale_curve(config, ref_curve)
    reference_layers = _reference_price_curve(config, ref_curve)
    curve_rows = []
    for slot, load in enumerate(d1["load"]):
        curve_rows.append({
            "date": d1["date"],
            "slot": slot,
            "start": _slot_start(slot, report["mtu_min"]),
            "end": _slot_end(slot, report["mtu_min"]),
            "forecast_load_mw": load,
            "p_mt_cny_per_mwh": mt,
            "p_da_cny_per_mwh": ref_curve[slot],
            "p_rt_cny_per_mwh": ref_curve[slot],
            "p_wholesale_cny_per_mwh": wholesale_curve[slot],
            "p_reference_layer_cny_per_mwh": reference_layers[slot],
            "p_retail_before_cap_cny_per_mwh": wholesale_curve[slot] + float(config["policy"]["retail_float_cny_per_mwh"]) + sum(
                float(config["policy"]["allocation_coefficients"][key]) * plan_allocation[key] for key in plan_allocation
            ),
        })
    _write_csv(out_dir / "pass_through_curve.csv", curve_rows, curve_fields)

    pricing_fields = [
        "segment", "share", "tilt", "package_type", "energy_mwh",
        "reference_avg_cny_per_mwh", "wholesale_avg_cny_per_mwh",
        "allocation_retail_cny_per_mwh", "allocation_cost_cny_per_mwh",
        "float_cny_per_mwh", "retail_before_cap_cny_per_mwh", "cap_cny_per_mwh",
        "settled_price_cny_per_mwh", "clip_cny_per_mwh", "headroom_cny_per_mwh",
        "break_even_float_cny_per_mwh", "revenue_cny", "procurement_cny",
        "allocation_cost_cny", "opex_cny", "green_margin_cny",
        "green_energy_premium_cny_per_mwh", "environmental_value_cny_per_mwh",
        "all_in_price_cny_per_mwh", "net_cny", "net_per_mwh_cny",
    ]
    _write_csv(out_dir / "pricing_sheet.csv", plan["rows"], pricing_fields)

    scenario_fields = [
        "scenario", "weight", "average_spot_cny_per_mwh", "wholesale_avg_cny_per_mwh",
        "reference_avg_cny_per_mwh", "cap_avg_cny_per_mwh", "retail_avg_cny_per_mwh",
        "clip_avg_cny_per_mwh", "revenue_cny", "procurement_cny",
        "allocation_cost_cny", "green_margin_cny", "opex_cny", "net_cny",
        "net_per_mwh_cny", "capped_segments",
    ]
    _write_csv(out_dir / "scenario_table.csv", scenarios["rows"], scenario_fields)

    stress_rows = stress["spot"] + stress["cap_factor"] + stress["float"] + stress["allocation_pass_through"] + stress["allocation_month"]
    _write_csv(
        out_dir / "stress_table.csv",
        stress_rows,
        ["type", "parameter", "value", "net_cny", "net_per_mwh_cny", "clip_avg_cny_per_mwh", "capped_segments", "note"],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": report["style_fingerprint"],
        "provenance": report["provenance"],
        "warnings": report["warnings"],
        "plan": {
            "energy_mwh": plan["energy_mwh"],
            "mt_price_cny_per_mwh": plan["mt_price_cny_per_mwh"],
            "reference_avg_cny_per_mwh": plan["weighted_reference_cny_per_mwh"],
            "wholesale_avg_cny_per_mwh": plan["weighted_wholesale_cny_per_mwh"],
            "cap_avg_cny_per_mwh": plan["weighted_cap_cny_per_mwh"],
            "retail_avg_cny_per_mwh": plan["weighted_retail_cny_per_mwh"],
            "settled_avg_cny_per_mwh": plan["weighted_settled_cny_per_mwh"],
            "clip_avg_cny_per_mwh": plan["clip_avg_cny_per_mwh"],
            "headroom_avg_cny_per_mwh": plan["weighted_headroom_cny_per_mwh"],
            "revenue_cny": plan["revenue_cny"],
            "procurement_cny": plan["procurement_cny"],
            "allocation_cost_cny": plan["allocation_cost_cny"],
            "variable_opex_cny": plan["variable_opex_cny"],
            "green_margin_cny": plan["green_margin_cny"],
            "fixed_cost_cny": plan["fixed_cost_cny"],
            "guarantee_daily_cny": plan["guarantee_daily_cny"],
            "net_cny": plan["net_cny"],
            "net_per_mwh_cny": plan["net_per_mwh_cny"],
            "capped_segments": plan["capped_segments"],
            "segments": plan["rows"],
        },
        "scenarios": {
            "rows": scenarios["rows"],
            "expected_net_cny": scenarios["expected_net_cny"],
            "cvar_10_cny": scenarios["cvar_10_cny"],
        },
        "stress": stress,
        "compliance": compliance,
        "bridge": None if bridge is None else {
            "plan_net_cny": bridge["plan_net_cny"],
            "actual_net_cny": bridge["actual_net_cny"],
            "delta_cny": bridge["delta_cny"],
            "identity_gap": bridge["identity_gap"],
            "plan_energy_mwh": bridge["plan_energy_mwh"],
            "actual_energy_mwh": bridge["actual_energy_mwh"],
            "plan_clip_avg_cny_per_mwh": bridge["plan_clip_avg_cny_per_mwh"],
            "actual_clip_avg_cny_per_mwh": bridge["actual_clip_avg_cny_per_mwh"],
            "cap_impact_cny": bridge["cap_impact_cny"],
            "buckets": bridge["buckets"],
            "top_slots": bridge["top_slots"],
        },
        "files": {
            "pass_through_curve": "pass_through_curve.csv",
            "pricing_sheet": "pricing_sheet.csv",
            "scenario_table": "scenario_table.csv",
            "stress_table": "stress_table.csv",
            "bridge": "bridge.json" if bridge is not None else None,
            "review": "review.md",
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if bridge is not None:
        bridge_out = {
            "plan_net_cny": bridge["plan_net_cny"],
            "actual_net_cny": bridge["actual_net_cny"],
            "delta_cny": bridge["delta_cny"],
            "identity_gap": bridge["identity_gap"],
            "plan_energy_mwh": bridge["plan_energy_mwh"],
            "actual_energy_mwh": bridge["actual_energy_mwh"],
            "plan_clip_avg_cny_per_mwh": bridge["plan_clip_avg_cny_per_mwh"],
            "actual_clip_avg_cny_per_mwh": bridge["actual_clip_avg_cny_per_mwh"],
            "cap_impact_cny": bridge["cap_impact_cny"],
            "buckets": bridge["buckets"],
            "top_slots": bridge["top_slots"],
        }
        (out_dir / "bridge.json").write_text(json.dumps(bridge_out, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_csv(out_dir / "bridge.csv", bridge["buckets"], ["item", "category", "owner", "amount"])
        _write_csv(
            out_dir / "top_slots.csv",
            bridge["top_slots"],
            ["slot", "start", "end", "forecast_load_mw", "actual_load_mw", "load_deviation_mw", "deviation_share", "plan_wholesale_cny_per_mwh", "actual_wholesale_cny_per_mwh", "actual_reference_layer_cny_per_mwh"],
        )
    write_review(out_dir / "review.md", config, report, d1, t1, plan, scenarios, stress, bridge, compliance)

    return {
        "config": config,
        "report": report,
        "d1": d1,
        "t1": t1,
        "plan": plan,
        "scenarios": scenarios,
        "stress": stress,
        "bridge": bridge,
        "compliance": compliance,
        "summary": summary,
        "out_dir": out_dir,
        "demo": demo,
    }


def _print_summary(result):
    summary = result["summary"]
    plan = summary["plan"]
    print(f"实例：{summary['instance_id']} / 交易日 {summary['trading_day']}")
    print(
        f"组合：{plan['energy_mwh']:,.1f} MWh，P_MT {plan['mt_price_cny_per_mwh']:.2f}，"
        f"批发均价 {plan['wholesale_avg_cny_per_mwh']:.2f}，P_ref {plan['reference_avg_cny_per_mwh']:.2f}"
    )
    print(
        f"封顶：零售均价 {plan['retail_avg_cny_per_mwh']:.2f}，封顶均价 {plan['cap_avg_cny_per_mwh']:.2f}，"
        f"扣减 {plan['clip_avg_cny_per_mwh']:.2f} CNY/MWh，{plan['capped_segments']}/{len(plan['segments'])} 个客户群触顶"
    )
    print(
        f"收益：计划 {plan['net_cny']:,.0f} CNY（{plan['net_per_mwh_cny']:.2f} CNY/MWh），"
        f"情景期望 {summary['scenarios']['expected_net_cny']:,.0f}，CVaR10 {summary['scenarios']['cvar_10_cny']:,.0f}"
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
    parser = argparse.ArgumentParser(description="江苏 2027 售电零售实例包：批发传导、一户一价封顶与 T+1 差异桥")
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
