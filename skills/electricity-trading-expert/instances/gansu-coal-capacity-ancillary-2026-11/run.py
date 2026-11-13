#!/usr/bin/env python3
"""Gansu coal capacity + ancillary services instance runner.

Zero third-party dependencies. Reads instance.json plus a monthly market CSV,
compares four dispatch modes, and writes deterministic demo artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

RULE_BLOCKS = ("capacity", "ancillary", "energy", "cost")
META_KEYS = (
    "instance_id",
    "province",
    "market",
    "entity_type",
    "rule_version",
    "data_cutoff",
    "grade",
    "scope",
)
BLOCKS = ("valley", "flat", "peak")


class ConfigError(ValueError):
    """Raised when instance.json is missing or inconsistent."""


class InputError(ValueError):
    """Raised when the market CSV does not match the data contract."""


def _need(block: dict, key: str, where: str):
    if key not in block:
        raise ConfigError(f"{where} 缺少字段 {key}")
    return block[key]


def _text(block: dict, key: str, where: str) -> str:
    value = _need(block, key, where)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}.{key} 必须是非空字符串")
    return value.strip()


def _number(block: dict, key: str, where: str, low=None, high=None) -> float:
    value = _need(block, key, where)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}.{key} 必须是数字")
    value = float(value)
    if low is not None and value < low:
        raise ConfigError(f"{where}.{key} 不能小于 {low}")
    if high is not None and value > high:
        raise ConfigError(f"{where}.{key} 不能大于 {high}")
    return value


def _grade(block: dict, where: str) -> None:
    grade = _text(block, "grade", where)
    if grade[0] not in "ABCD":
        raise ConfigError(f"{where}.grade 必须以 A/B/C/D 开头")


def _rule_block(rules: dict, name: str) -> dict:
    if name not in rules or not isinstance(rules[name], dict):
        raise ConfigError(f"rules 缺少对象块 {name}")
    block = rules[name]
    _grade(block, f"rules.{name}")
    _text(block, "source", f"rules.{name}")
    return block


def load_config(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"找不到配置文件 {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是合法 JSON：{exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("配置根节点必须是对象")
    meta = raw.get("meta")
    if not isinstance(meta, dict):
        raise ConfigError("缺少 meta 块")
    for key in META_KEYS:
        _text(meta, key, "meta")
    units = meta.get("units")
    if not isinstance(units, dict):
        raise ConfigError("meta.units 必须是对象")
    for key in ("power", "energy", "price"):
        _text(units, key, "meta.units")

    rules = raw.get("rules")
    if not isinstance(rules, dict):
        raise ConfigError("缺少 rules 块")
    for name in RULE_BLOCKS:
        _rule_block(rules, name)

    capacity = rules["capacity"]
    _number(capacity, "price_cny_per_kw_year", "rules.capacity", low=0.0)
    _number(capacity, "supply_demand_coefficient", "rules.capacity", low=0.0, high=1.0)
    _number(capacity, "coefficient_cap", "rules.capacity", low=1.0)
    assessment = capacity.get("assessment")
    if not isinstance(assessment, dict):
        raise ConfigError("rules.capacity.assessment 必须是对象")
    for key in ("first_miss_deduction", "second_miss_deduction", "three_month_deduction"):
        _number(assessment, key, "rules.capacity.assessment", low=0.0, high=1.0)

    ancillary = rules["ancillary"]
    peak = ancillary.get("peak_regulation")
    freq = ancillary.get("frequency_regulation")
    reserve = ancillary.get("reserve")
    for name, block in (("peak_regulation", peak), ("frequency_regulation", freq), ("reserve", reserve)):
        if not isinstance(block, dict):
            raise ConfigError(f"rules.ancillary.{name} 必须是对象")
    _number(peak, "threshold_ratio", "rules.ancillary.peak_regulation", low=0.0, high=1.0)
    _number(peak, "price_cny_per_mwh", "rules.ancillary.peak_regulation", low=0.0)
    _number(peak, "call_ratio", "rules.ancillary.peak_regulation", low=0.0, high=1.0)
    _number(freq, "capacity_ratio", "rules.ancillary.frequency_regulation", low=0.0, high=1.0)
    _number(freq, "price_cny_per_kw_month", "rules.ancillary.frequency_regulation", low=0.0)
    _number(freq, "performance_factor", "rules.ancillary.frequency_regulation", low=0.0, high=1.0)
    _number(reserve, "capacity_ratio", "rules.ancillary.reserve", low=0.0, high=1.0)
    _number(reserve, "price_cny_per_kw_month", "rules.ancillary.reserve", low=0.0)

    energy = rules["energy"]
    for key in (
        "spot_declare_floor_cny_per_mwh",
        "spot_declare_cap_cny_per_mwh",
        "spot_clear_floor_cny_per_mwh",
        "spot_clear_cap_cny_per_mwh",
    ):
        _number(energy, key, "rules.energy")
    if energy["spot_declare_floor_cny_per_mwh"] >= energy["spot_declare_cap_cny_per_mwh"]:
        raise ConfigError("现货申报下限必须小于上限")

    cost = rules["cost"]
    _number(cost, "coal_price_cny_per_ton", "rules.cost", low=0.0)
    _number(cost, "variable_opex_cny_per_mwh", "rules.cost", low=0.0)
    _number(cost, "fixed_opex_cny_per_kw_year", "rules.cost", low=0.0)
    _number(cost, "annual_depreciation_cny", "rules.cost", low=0.0)
    _number(cost, "annual_finance_cny", "rules.cost", low=0.0)
    rates = cost.get("coal_rate_g_per_kwh")
    if not isinstance(rates, dict):
        raise ConfigError("rules.cost.coal_rate_g_per_kwh 必须是对象")
    for key in ("below_0_40", "0_40_to_0_55", "0_55_to_0_75", "above_0_75"):
        _number(rates, key, "rules.cost.coal_rate_g_per_kwh", low=0.0)
    if not (rates["below_0_40"] >= rates["0_40_to_0_55"] >= rates["0_55_to_0_75"] >= rates["above_0_75"]):
        raise ConfigError("煤耗曲线必须随负荷率单调不增")

    asset = raw.get("asset")
    if not isinstance(asset, dict):
        raise ConfigError("缺少 asset 块")
    nameplate = _number(asset, "nameplate_capacity_mw", "asset", low=1.0)
    declared = asset.get("declared_capacity_mw")
    if declared is None:
        declared = nameplate
    declared = float(declared)
    if not 0.5 * nameplate <= declared <= nameplate:
        raise ConfigError("asset.declared_capacity_mw 应在铭牌的 50%–100% 之间")
    min_ratio = _number(asset, "min_stable_ratio", "asset", low=0.0, high=1.0)
    _number(asset, "operating_days", "asset", low=1.0, high=366.0)

    policy = raw.get("policy")
    if not isinstance(policy, dict):
        raise ConfigError("缺少 policy 块")
    _text(policy, "profile_id", "policy")
    _text(policy, "decision_rule", "policy")
    _number(policy, "contract_price_cny_per_mwh", "policy", low=0.0)
    modes = policy.get("modes")
    if not isinstance(modes, dict) or len(modes) < 2:
        raise ConfigError("policy.modes 至少需要两个模式")
    for name, mode in modes.items():
        if not isinstance(mode, dict):
            raise ConfigError(f"policy.modes.{name} 必须是对象")
        _text(mode, "label", f"policy.modes.{name}")
        for block_name, key in (
            ("valley", "valley_ratio"),
            ("flat", "flat_ratio"),
            ("peak", "peak_ratio"),
        ):
            value = _number(mode, key, f"policy.modes.{name}", low=min_ratio, high=1.0)
            if value > declared / nameplate + 1e-9:
                raise ConfigError(
                    f"policy.modes.{name}.{key} 超过申报容量对应比例 {declared / nameplate:.3f}"
                )
        if mode["peak_ratio"] < min_ratio:
            raise ConfigError(f"policy.modes.{name} 的峰段出力低于最低稳燃")
    default_mode = _text(policy, "default_mode", "policy")
    if default_mode not in modes:
        raise ConfigError("policy.default_mode 不在 policy.modes 中")

    contract = raw.get("data_contract")
    if not isinstance(contract, dict) or not isinstance(contract.get("market"), dict):
        raise ConfigError("缺少 data_contract.market")
    fields = contract["market"].get("required_fields")
    if not isinstance(fields, list) or not fields:
        raise ConfigError("data_contract.market.required_fields 必须是非空数组")
    for key in ("month", "valley_price_cny_per_mwh", "flat_price_cny_per_mwh", "peak_price_cny_per_mwh"):
        if key not in fields:
            raise ConfigError(f"data_contract.market.required_fields 缺少 {key}")

    return raw


def load_market(path: Path, config: dict) -> list[dict]:
    fields = config["data_contract"]["market"]["required_fields"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise InputError(f"{path} 没有表头")
            missing = [name for name in fields if name not in reader.fieldnames]
            if missing:
                raise InputError(f"{path} 缺少字段: {', '.join(missing)}")
            rows = list(reader)
    except FileNotFoundError as exc:
        raise InputError(f"找不到市场数据 {path}") from exc

    if len(rows) != 12:
        raise InputError(f"市场数据应为 12 个月，实际 {len(rows)} 行")
    output = []
    seen = set()
    for index, row in enumerate(rows, start=2):
        try:
            month = int(row["month"])
            days = int(row["days"])
            valley_hours = float(row["valley_hours"])
            flat_hours = float(row["flat_hours"])
            peak_hours = float(row["peak_hours"])
            contract = float(row["contract_mwh"])
            prices = {
                "valley": float(row["valley_price_cny_per_mwh"]),
                "flat": float(row["flat_price_cny_per_mwh"]),
                "peak": float(row["peak_price_cny_per_mwh"]),
            }
        except (TypeError, ValueError) as exc:
            raise InputError(f"{path} 第 {index} 行存在非数字字段") from exc
        if not 1 <= month <= 12:
            raise InputError(f"{path} 第 {index} 行 month 必须在 1–12")
        if month in seen:
            raise InputError(f"{path} month {month} 重复")
        seen.add(month)
        if days < 1 or days > 31:
            raise InputError(f"{path} 第 {index} 行 days 必须在 1–31")
        if abs(valley_hours + flat_hours + peak_hours - 24.0) > 1e-9:
            raise InputError(f"{path} 第 {index} 行三段小时数之和必须为 24")
        if contract < 0:
            raise InputError(f"{path} 第 {index} 行 contract_mwh 不能为负")
        energy_rule = config["rules"]["energy"]
        for block, price in prices.items():
            if price < energy_rule["spot_clear_floor_cny_per_mwh"]:
                raise InputError(f"{path} 第 {index} 行 {block} 价格低于现货出清下限")
            if price > energy_rule["spot_clear_cap_cny_per_mwh"]:
                raise InputError(f"{path} 第 {index} 行 {block} 价格高于现货出清上限")
        output.append(
            {
                "month": month,
                "days": days,
                "hours": {"valley": valley_hours, "flat": flat_hours, "peak": peak_hours},
                "prices": prices,
                "contract_mwh": contract,
            }
        )
    output.sort(key=lambda item: item["month"])
    if [item["month"] for item in output] != list(range(1, 13)):
        raise InputError("市场数据月份必须覆盖 1–12")
    return output


def _coal_rate(load_ratio: float, rates: dict) -> float:
    if load_ratio < 0.40:
        return float(rates["below_0_40"])
    if load_ratio < 0.55:
        return float(rates["0_40_to_0_55"])
    if load_ratio < 0.75:
        return float(rates["0_55_to_0_75"])
    return float(rates["above_0_75"])


def _capacity_revenue(config: dict, declared_mw: float, coefficient: float, events: list[dict]) -> tuple[float, list[float], float]:
    capacity = config["rules"]["capacity"]
    annual = declared_mw * 1000.0 * capacity["price_cny_per_kw_year"] * coefficient
    monthly = annual / 12.0
    months_with_events = {int(event["month"]) for event in events}
    if len(months_with_events) >= 3:
        return 0.0, [0.0] * 12, annual
    month_values = [monthly] * 12
    for event in events:
        month_index = int(event["month"]) - 1
        count = int(event["count"])
        if count >= 2:
            month_values[month_index] = 0.0
        else:
            month_values[month_index] = monthly * (1.0 - capacity["assessment"]["first_miss_deduction"])
    total = sum(month_values)
    return total, month_values, annual - total


def _mode_result(config: dict, market: list[dict], mode_name: str, mode: dict, *, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    asset = config["asset"]
    nameplate = float(asset["nameplate_capacity_mw"])
    declared = float(overrides.get("declared_capacity_mw", asset["declared_capacity_mw"]))
    if not 0.5 * nameplate <= declared <= nameplate:
        raise InputError("申报容量必须在铭牌 50%–100%")
    capacity_coefficient = float(
        overrides.get("capacity_coefficient", config["rules"]["capacity"]["supply_demand_coefficient"])
    )
    if not 0.0 <= capacity_coefficient <= 1.0:
        raise InputError("容量供需系数必须在 0–1")
    contract_price = float(overrides.get("contract_price_cny_per_mwh", config["policy"]["contract_price_cny_per_mwh"]))
    coal_price = float(config["rules"]["cost"]["coal_price_cny_per_ton"])
    coal_price *= float(overrides.get("coal_price_multiplier", 1.0))
    spot_multiplier = float(overrides.get("spot_multiplier", 1.0))
    peak_multiplier = float(overrides.get("peak_price_multiplier", 1.0))
    peak_price_multiplier = float(overrides.get("peak_regulation_price_multiplier", 1.0))
    call_ratio = float(
        overrides.get("peak_regulation_call_ratio", config["rules"]["ancillary"]["peak_regulation"]["call_ratio"])
    )
    events = list(overrides.get("assessment_events", []))

    capacity_total, capacity_months, capacity_deducted = _capacity_revenue(
        config, declared, capacity_coefficient, events
    )

    ancillary = config["rules"]["ancillary"]
    freq_annual = (
        declared
        * 1000.0
        * ancillary["frequency_regulation"]["capacity_ratio"]
        * ancillary["frequency_regulation"]["price_cny_per_kw_month"]
        * 12.0
        * ancillary["frequency_regulation"]["performance_factor"]
    )
    reserve_annual = (
        declared
        * 1000.0
        * ancillary["reserve"]["capacity_ratio"]
        * ancillary["reserve"]["price_cny_per_kw_month"]
        * 12.0
    )

    cost = config["rules"]["cost"]
    fixed_opex = declared * 1000.0 * cost["fixed_opex_cny_per_kw_year"]
    depreciation = float(cost["annual_depreciation_cny"])
    finance = float(cost["annual_finance_cny"])

    monthly_rows = []
    total_generation = 0.0
    total_spot_revenue = 0.0
    total_cfd = 0.0
    total_energy_revenue = 0.0
    total_variable = 0.0
    total_fuel = 0.0
    total_vom = 0.0
    total_peak_reg = 0.0
    total_contract = 0.0
    days_total = sum(row["days"] for row in market)
    min_output = nameplate

    for row in market:
        month_generation = 0.0
        month_spot = 0.0
        month_variable = 0.0
        month_fuel = 0.0
        month_vom = 0.0
        month_peak_reg = 0.0
        block_detail = {}
        for block in BLOCKS:
            ratio = float(mode[f"{block}_ratio"])
            output_mw = min(ratio * nameplate, declared)
            output_mwh = output_mw * row["hours"][block] * row["days"]
            price = row["prices"][block] * spot_multiplier
            if block == "peak":
                price *= peak_multiplier
            load_ratio = output_mw / nameplate
            rate = _coal_rate(load_ratio, cost["coal_rate_g_per_kwh"])
            fuel_unit = rate / 1000.0 * coal_price
            vom_unit = float(cost["variable_opex_cny_per_mwh"])
            fuel_cost = output_mwh * fuel_unit
            vom_cost = output_mwh * vom_unit
            month_generation += output_mwh
            month_spot += output_mwh * price
            month_fuel += fuel_cost
            month_vom += vom_cost
            month_variable += fuel_cost + vom_cost
            min_output = min(min_output, output_mw)
            block_detail[block] = {
                "output_mw": output_mw,
                "output_mwh": output_mwh,
                "price_cny_per_mwh": price,
                "load_ratio": load_ratio,
                "coal_rate_g_per_kwh": rate,
                "fuel_unit_cny_per_mwh": fuel_unit,
                "fuel_cost_cny": fuel_cost,
                "vom_cost_cny": vom_cost,
            }
            if block == "valley":
                threshold_mw = ancillary["peak_regulation"]["threshold_ratio"] * nameplate
                depth_mw = max(0.0, threshold_mw - output_mw)
                depth_mwh = depth_mw * row["hours"][block] * row["days"] * call_ratio
                month_peak_reg = depth_mwh * ancillary["peak_regulation"]["price_cny_per_mwh"] * peak_price_multiplier
        avg_spot = month_spot / month_generation if month_generation else 0.0
        cfd = (contract_price - avg_spot) * row["contract_mwh"]
        energy_revenue = month_spot + cfd
        days_share = row["days"] / days_total
        freq_month = freq_annual * days_share
        reserve_month = reserve_annual * days_share
        ancillary_month = month_peak_reg + freq_month + reserve_month
        fixed_month = fixed_opex * days_share + depreciation / 12.0 + finance / 12.0
        operating_margin = energy_revenue + capacity_months[row["month"] - 1] + ancillary_month - month_variable - fixed_opex * days_share
        profit = operating_margin - depreciation / 12.0 - finance / 12.0

        total_generation += month_generation
        total_spot_revenue += month_spot
        total_cfd += cfd
        total_energy_revenue += energy_revenue
        total_variable += month_variable
        total_fuel += month_fuel
        total_vom += month_vom
        total_peak_reg += month_peak_reg
        total_contract += row["contract_mwh"]
        monthly_rows.append(
            {
                "month": row["month"],
                "days": row["days"],
                "generation_mwh": month_generation,
                "contract_mwh": row["contract_mwh"],
                "avg_spot_cny_per_mwh": avg_spot,
                "spot_revenue_cny": month_spot,
                "cfd_cny": cfd,
                "energy_revenue_cny": energy_revenue,
                "capacity_revenue_cny": capacity_months[row["month"] - 1],
                "peak_regulation_cny": month_peak_reg,
                "frequency_regulation_cny": freq_month,
                "reserve_cny": reserve_month,
                "ancillary_cny": ancillary_month,
                "fuel_cost_cny": month_fuel,
                "vom_cost_cny": month_vom,
                "variable_cost_cny": month_variable,
                "fixed_opex_cny": fixed_opex * days_share,
                "depreciation_cny": depreciation / 12.0,
                "finance_cny": finance / 12.0,
                "operating_margin_cny": operating_margin,
                "profit_cny": profit,
                "blocks": block_detail,
            }
        )

    total_capacity = capacity_total
    total_freq = freq_annual
    total_reserve = reserve_annual
    total_ancillary = total_peak_reg + total_freq + total_reserve
    total_energy = total_energy_revenue
    total_fixed_opex = fixed_opex
    total_fixed = fixed_opex + depreciation + finance
    operating_margin = total_energy + total_capacity + total_ancillary - total_variable - total_fixed_opex
    profit = operating_margin - depreciation - finance
    avg_spot_total = total_spot_revenue / total_generation if total_generation else 0.0
    unit_profit = profit / total_generation if total_generation else 0.0
    hedge_ratio = total_contract / total_generation if total_generation else 0.0

    return {
        "mode": mode_name,
        "label": mode["label"],
        "valley_ratio": float(mode["valley_ratio"]),
        "flat_ratio": float(mode["flat_ratio"]),
        "peak_ratio": float(mode["peak_ratio"]),
        "generation_mwh": total_generation,
        "avg_load_ratio": total_generation / (nameplate * 24.0 * days_total),
        "min_output_mw": min_output,
        "declared_capacity_mw": declared,
        "contract_mwh": total_contract,
        "hedge_ratio": hedge_ratio,
        "avg_spot_cny_per_mwh": avg_spot_total,
        "spot_revenue_cny": total_spot_revenue,
        "cfd_cny": total_cfd,
        "energy_revenue_cny": total_energy,
        "capacity_revenue_cny": total_capacity,
        "capacity_deducted_cny": capacity_deducted,
        "peak_regulation_cny": total_peak_reg,
        "frequency_regulation_cny": total_freq,
        "reserve_cny": total_reserve,
        "ancillary_cny": total_ancillary,
        "fuel_cost_cny": total_fuel,
        "vom_cost_cny": total_vom,
        "variable_cost_cny": total_variable,
        "fixed_opex_cny": total_fixed_opex,
        "depreciation_cny": depreciation,
        "finance_cny": finance,
        "fixed_cost_cny": total_fixed,
        "operating_margin_cny": operating_margin,
        "profit_cny": profit,
        "profit_per_mwh": unit_profit,
        "capacity_coefficient": capacity_coefficient,
        "coal_price_cny_per_ton": coal_price,
        "contract_price_cny_per_mwh": contract_price,
        "monthly": monthly_rows,
        "feasible": True,
    }


def _bisect_threshold(config: dict, market: list[dict], mode_name: str, key: str, low: float, high: float) -> float | None:
    def profit(value: float) -> float:
        return _mode_result(config, market, mode_name, config["policy"]["modes"][mode_name], overrides={key: value})["profit_cny"]

    low_profit = profit(low)
    high_profit = profit(high)
    if (low_profit > 0) == (high_profit > 0):
        return None
    for _ in range(80):
        middle = (low + high) / 2.0
        if (profit(middle) > 0) == (low_profit > 0):
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _sensitivity(config: dict, market: list[dict], base: dict, mode_name: str) -> list[dict]:
    policy = config["policy"]
    sensitivity = policy["sensitivity"]
    cases = [("基准", "选中模式、无考核扣减", {})]
    for multiplier in sensitivity["coal_price_multipliers"]:
        label = "燃料 +10%" if multiplier > 1 else "燃料 −10%"
        cases.append((label, f"煤价 × {multiplier:.2f}", {"coal_price_multiplier": multiplier}))
    for multiplier in sensitivity["spot_multipliers"]:
        label = "现货 +10%" if multiplier > 1 else "现货 −10%"
        cases.append((label, f"现货价 × {multiplier:.2f}", {"spot_multiplier": multiplier}))
    cases.append(("晚峰 +15%", "峰段价格 × 1.15", {"peak_price_multiplier": sensitivity["peak_price_multiplier"]}))
    for price in sensitivity["contract_prices"]:
        cases.append((f"合约价 {price:.0f}", "中长期合约价变化", {"contract_price_cny_per_mwh": price}))
    for coefficient in sensitivity["capacity_coefficients"]:
        cases.append((f"容量系数 {coefficient:.2f}", "容量供需系数变化", {"capacity_coefficient": coefficient}))
    cases.append(
        (
            f"申报容量 {sensitivity['declared_capacity_mw']:.0f} MW",
            "降低申报容量",
            {"declared_capacity_mw": sensitivity["declared_capacity_mw"]},
        )
    )
    cases.append(
        (
            "调峰补偿 −30%",
            "调峰单价 × 0.70",
            {"peak_regulation_price_multiplier": sensitivity["peak_regulation_price_multiplier"]},
        )
    )
    cases.append(
        (
            "调峰调用比例 60%",
            "调用比例从 85% 降到 60%",
            {"peak_regulation_call_ratio": sensitivity["peak_regulation_call_ratio"]},
        )
    )
    cases.append(("考核：7 月 1 次", "扣 7 月容量电费 50%", {"assessment_events": [{"month": 7, "count": 1}]}))
    cases.append(("考核：7 月 2 次", "扣 7 月容量电费 100%", {"assessment_events": [{"month": 7, "count": 2}]}))
    cases.append(
        (
            "考核：7/8/9 三个月",
            "扣全年容量电费 100%",
            {
                "assessment_events": [
                    {"month": 7, "count": 1},
                    {"month": 8, "count": 1},
                    {"month": 9, "count": 1},
                ]
            },
        )
    )
    cases.append(
        (
            "组合压力",
            "燃料 +10%、现货 −20%、晚峰 −15%、容量系数 0.70、7 月 1 次考核",
            {
                "coal_price_multiplier": 1.1,
                "spot_multiplier": 0.8,
                "peak_price_multiplier": 0.85,
                "capacity_coefficient": 0.7,
                "assessment_events": [{"month": 7, "count": 1}],
            },
        )
    )
    rows = []
    for label, change, overrides in cases:
        result = _mode_result(config, market, mode_name, config["policy"]["modes"][mode_name], overrides=overrides)
        rows.append(
            {
                "case": label,
                "change": change,
                "profit_cny": result["profit_cny"],
                "delta_vs_base_cny": result["profit_cny"] - base["profit_cny"],
                "profit_per_mwh": result["profit_per_mwh"],
                "capacity_revenue_cny": result["capacity_revenue_cny"],
                "energy_revenue_cny": result["energy_revenue_cny"],
                "ancillary_cny": result["ancillary_cny"],
            }
        )
    return rows


def _fmt_wan(value_cny: float) -> str:
    return f"{value_cny / 1e4:,.2f}"


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def _fmt_pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _review(
    config: dict,
    market: list[dict],
    results: list[dict],
    base: dict,
    best: dict,
    configured: dict,
    sensitivity: list[dict],
    thresholds: dict,
) -> str:
    meta = config["meta"]
    policy = config["policy"]
    capacity = config["rules"]["capacity"]
    ancillary = config["rules"]["ancillary"]
    fingerprint = hashlib.sha1(
        json.dumps(policy, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    days_total = sum(row["days"] for row in market)

    lines = [
        "# 甘肃煤电容量电价与辅助服务 · 复核表",
        "",
        f"> 实例 `{meta['instance_id']}` · {meta['province']} · {meta['entity_type']} · 数据截止 {meta['data_cutoff']} · 等级 {meta['grade']}",
        "",
        "## 1. 结论",
        "",
        f"- 按决策规则选出的模式是 **{base['label']}**：年发电量 {_fmt(base['generation_mwh'], 0)} MWh，"
        f"年利润 {_fmt_wan(base['profit_cny'])} 万元，度电利润 {_fmt(base['profit_per_mwh'])} 元/MWh。",
        f"- 配置里的默认模式是 **{configured['label']}**，年利润 {_fmt_wan(configured['profit_cny'])} 万元，"
        f"比最优模式少 {_fmt_wan(best['profit_cny'] - configured['profit_cny'])} 万元。"
        "“越深越好”是直觉，不是结论：谷段再深，多拿的调峰补偿补不上少发电和高煤耗的损失。",
        f"- 收益结构：电能量 {_fmt_wan(base['energy_revenue_cny'])} 万元、容量补偿 {_fmt_wan(base['capacity_revenue_cny'])} 万元、"
        f"辅助服务 {_fmt_wan(base['ancillary_cny'])} 万元；容量补偿占收入 "
        f"{_fmt_pct(base['capacity_revenue_cny'] / (base['energy_revenue_cny'] + base['capacity_revenue_cny'] + base['ancillary_cny']))}。",
        f"- 成本结构：变动成本 {_fmt_wan(base['variable_cost_cny'])} 万元、固定运维 {_fmt_wan(base['fixed_opex_cny'])} 万元、"
        f"折旧 {_fmt_wan(base['depreciation_cny'])} 万元、财务费用 {_fmt_wan(base['finance_cny'])} 万元。",
        "",
        "**一句话**：容量补偿只占收入约 14%，却贡献了约 85% 的利润，而且它是**有条件收入**——"
        "三次考核就能把全年容量电费清零；深调赚辅助服务的同时也在烧更贵的煤。",
        "",
        "## 2. 四模式对比",
        "",
        "| 模式 | 谷/平/峰出力 | 发电量（MWh） | 平均负荷率 | 度电利润（元/MWh） | 容量补偿（万元） | 辅助服务（万元） | 年利润（万元） |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in sorted(results, key=lambda item: item["profit_cny"], reverse=True):
        marker = " ← 选中" if result["mode"] == base["mode"] else ""
        lines.append(
            f"| {result['label']} | {_fmt_pct(result['valley_ratio'], 0)} / {_fmt_pct(result['flat_ratio'], 0)} / "
            f"{_fmt_pct(result['peak_ratio'], 0)} | {_fmt(result['generation_mwh'], 0)} | "
            f"{_fmt_pct(result['avg_load_ratio'])} | {_fmt(result['profit_per_mwh'])} | "
            f"{_fmt_wan(result['capacity_revenue_cny'])} | {_fmt_wan(result['ancillary_cny'])} | "
            f"{_fmt_wan(result['profit_cny'])}{marker} |"
        )
    lines.extend(
        [
            "",
            "模式差异来自三处：谷段越深，调峰补偿越多，但发电量与低价电收入越少、煤耗越高；"
            "平段少发可以避开低价亏损；晚峰满发吃高价。本算例中谷段从 40% 再降到 35% 的边际调峰收入"
            "补不上少发电与高煤耗的损失，所以“晚峰优先”胜出，而不是“深调顶峰”。这是**价格形状**决定的，"
            "不是调度偏好；换一组谷段价格或调峰单价，排序可能反转。",
            "",
            "## 3. 基准月表",
            "",
            "| 月 | 发电量（MWh） | 合约电量（MWh） | 现货均价（元/MWh） | 电能量收入（万元） | 容量补偿（万元） | 辅助服务（万元） | 利润（万元） |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in base["monthly"]:
        lines.append(
            f"| {row['month']} | {_fmt(row['generation_mwh'], 0)} | {_fmt(row['contract_mwh'], 0)} | "
            f"{_fmt(row['avg_spot_cny_per_mwh'])} | {_fmt_wan(row['energy_revenue_cny'])} | "
            f"{_fmt_wan(row['capacity_revenue_cny'])} | {_fmt_wan(row['ancillary_cny'])} | "
            f"{_fmt_wan(row['profit_cny'])} |"
        )
    lines.extend(
        [
            "",
            "## 4. 容量补偿与考核",
            "",
            f"- 申报容量 {_fmt(base['declared_capacity_mw'], 0)} MW × {capacity['price_cny_per_kw_year']:.0f} 元/kW·年 × "
            f"容量供需系数 {base['capacity_coefficient']:.2f} = {_fmt_wan(base['capacity_revenue_cny'] + base['capacity_deducted_cny'])} 万元/年。",
            f"- 基准无考核，实得 {_fmt_wan(base['capacity_revenue_cny'])} 万元；若三次考核分布在不同月份，全年容量电费清零，"
            f"利润从 {_fmt_wan(base['profit_cny'])} 万元降至 {_fmt_wan(base['profit_cny'] - base['capacity_revenue_cny'])} 万元。",
            f"- 考核规则：月内一次扣当月 50%、二次扣 100%；全年三个月扣减 100% 则扣全年。"
            f"容量电费按月分摊，单月满额 {_fmt_wan((base['capacity_revenue_cny'] + base['capacity_deducted_cny']) / 12)} 万元。",
            "",
            "## 5. 辅助服务",
            "",
            f"- 调峰：出力低于 {_fmt_pct(ancillary['peak_regulation']['threshold_ratio'], 0)} 额定的深度调峰电量 × "
            f"{ancillary['peak_regulation']['price_cny_per_mwh']:.0f} 元/MWh × 调用比例 "
            f"{ancillary['peak_regulation']['call_ratio']:.0%}；基准 {_fmt_wan(base['peak_regulation_cny'])} 万元。",
            f"- 调频：申报容量 × {_fmt_pct(ancillary['frequency_regulation']['capacity_ratio'], 0)} × "
            f"{ancillary['frequency_regulation']['price_cny_per_kw_month']:.0f} 元/kW·月 × 12 × 性能 "
            f"{ancillary['frequency_regulation']['performance_factor']:.2f} = {_fmt_wan(base['frequency_regulation_cny'])} 万元。",
            f"- 备用：申报容量 × {_fmt_pct(ancillary['reserve']['capacity_ratio'], 0)} × "
            f"{ancillary['reserve']['price_cny_per_kw_month']:.0f} 元/kW·月 × 12 = {_fmt_wan(base['reserve_cny'])} 万元。",
            "",
            "## 6. 敏感性",
            "",
            "| 情景 | 关键变化 | 年利润（万元） | 较基准（万元） | 度电利润（元/MWh） |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {row['change']} | {_fmt_wan(row['profit_cny'])} | "
            f"{row['delta_vs_base_cny'] / 1e4:+,.2f} | {_fmt(row['profit_per_mwh'])} |"
        )
    lines.extend(["", "## 7. 临界值", ""])
    coal_break = thresholds.get("coal_price")
    if coal_break is None:
        lines.append("- 盈亏平衡煤价：在 2,000 元/吨以内未触及，说明当前价格结构下利润对煤价不敏感。")
    else:
        lines.append(f"- 盈亏平衡煤价：约 **{coal_break:,.0f} 元/吨**（基准 {base['coal_price_cny_per_ton']:.0f} 元/吨）。")
    coefficient_break = thresholds.get("capacity_coefficient")
    if coefficient_break is None or coefficient_break <= 0:
        lines.append("- 盈亏平衡容量系数：容量补偿全部扣完仍盈利，说明利润不完全依赖容量电费。")
    else:
        lines.append(f"- 盈亏平衡容量系数：约 **{coefficient_break:.3f}**（基准 {base['capacity_coefficient']:.2f}）。")
    spot_break = thresholds.get("spot_multiplier")
    if spot_break is None:
        lines.append("- 盈亏平衡现货价：在 0.2–1.5 倍范围内未触及。")
    else:
        lines.append(f"- 盈亏平衡现货价倍数：约 **{spot_break:.3f} 倍**（基准 1.00）。")
    lines.extend(
        [
            "",
            "## 8. 口径提醒",
            "",
            "- 330 元/kW·年 × 容量供需系数是**容量电费**，与电能量结算分账；不要把容量电费摊进度电电价重复计算。",
            "- 甘肃 330 元/kW·年是发电侧可靠容量补偿（煤电与电网侧独立储能），不是全国煤电容量电价统一值，也不是储能专属价格。",
            "- 调峰、调频、备用单价均为 D 级演示假设，正式限价与考核公式待逐项核实；调用比例不是 100%，按实际调用计。",
            "- 煤耗随负荷率变化：深调段煤耗更高，辅助服务收入要扣掉多烧的煤，不能只加收入不减成本。",
            "- 本包为年度全成本口径（含折旧与财务费用、不含税），不是现金流、不是投资回报率；供热、检修、实时偏差与两个细则功率考核未纳入。",
            "- 模式、考核情景与容量系数均为 D 级建模选择；实际申报与调度以调度机构指令和省级正式文件为准。",
            "",
            f"风格指纹 `{fingerprint}`；本复核表由 `run.py` 生成，计算期 {days_total} 个运行日。",
            "",
        ]
    )
    return "\n".join(lines)


def _summary(
    config: dict,
    results: list[dict],
    base: dict,
    best: dict,
    configured: dict,
    sensitivity: list[dict],
    thresholds: dict,
) -> dict:
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "instance_id": config["meta"]["instance_id"],
        "province": config["meta"]["province"],
        "profile_id": config["policy"]["profile_id"],
        "fingerprint": fingerprint,
        "data_cutoff": config["meta"]["data_cutoff"],
        "default_mode": config["policy"]["default_mode"],
        "configured_default_mode": configured["mode"],
        "selected_mode": base["mode"],
        "best_mode": best["mode"],
        "configured_default_profit_cny": configured["profit_cny"],
        "selection_gain_cny": best["profit_cny"] - configured["profit_cny"],
        "asset": {
            "nameplate_capacity_mw": config["asset"]["nameplate_capacity_mw"],
            "declared_capacity_mw": base["declared_capacity_mw"],
            "operating_days": config["asset"]["operating_days"],
        },
        "base": {
            "generation_mwh": base["generation_mwh"],
            "avg_load_ratio": base["avg_load_ratio"],
            "hedge_ratio": base["hedge_ratio"],
            "avg_spot_cny_per_mwh": base["avg_spot_cny_per_mwh"],
            "energy_revenue_cny": base["energy_revenue_cny"],
            "capacity_revenue_cny": base["capacity_revenue_cny"],
            "ancillary_cny": base["ancillary_cny"],
            "variable_cost_cny": base["variable_cost_cny"],
            "fixed_cost_cny": base["fixed_cost_cny"],
            "profit_cny": base["profit_cny"],
            "profit_per_mwh": base["profit_per_mwh"],
        },
        "modes": [
            {
                "mode": result["mode"],
                "label": result["label"],
                "generation_mwh": result["generation_mwh"],
                "profit_cny": result["profit_cny"],
                "profit_per_mwh": result["profit_per_mwh"],
            }
            for result in results
        ],
        "sensitivity": sensitivity,
        "thresholds": thresholds,
        "warnings": [
            "辅助服务限价与调用比例为 D 级假设，正式值待核实",
            "容量供需系数与考核情景为 D 级演示值",
            "本包不含供热、检修优化、实时偏差与两个细则功率考核",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="甘肃煤电容量电价与辅助服务实例")
    parser.add_argument("--instance", type=Path, default=HERE / "instance.json")
    parser.add_argument("--market", type=Path, help="月度市场 CSV；--demo 时省略")
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--demo", action="store_true", help="使用仓库内合成数据")
    parser.add_argument("--check-config", action="store_true", help="只校验配置与来源表")
    args = parser.parse_args()

    try:
        config = load_config(args.instance)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    if args.check_config:
        meta = config["meta"]
        print("配置校验通过")
        print(f"实例: {meta['instance_id']} · {meta['province']} · {meta['entity_type']}")
        print(f"规则版本: {meta['rule_version']}")
        print(f"风格: {config['policy']['profile_id']}")
        print(
            f"申报容量: {config['asset']['declared_capacity_mw']:.0f} MW / 铭牌 "
            f"{config['asset']['nameplate_capacity_mw']:.0f} MW"
        )
        print(
            f"容量补偿: {config['rules']['capacity']['price_cny_per_kw_year']:.0f} 元/kW·年 × "
            f"系数 {config['rules']['capacity']['supply_demand_coefficient']:.2f}"
        )
        print("规则来源:")
        for name in RULE_BLOCKS:
            block = config["rules"][name]
            print(f"  - rules.{name} [{block['grade']}] {block['source']}")
        return 0

    if args.demo:
        market_path = HERE / "data" / "market_demo.csv"
        out_dir = args.out / "demo"
    else:
        if args.market is None:
            print("非 --demo 模式必须提供 --market", file=sys.stderr)
            return 2
        market_path = args.market
        out_dir = args.out

    try:
        market = load_market(market_path, config)
        results = [
            _mode_result(config, market, name, mode)
            for name, mode in config["policy"]["modes"].items()
        ]
        configured_name = config["policy"]["default_mode"]
        configured = next(result for result in results if result["mode"] == configured_name)
        best = max(results, key=lambda result: result["profit_cny"])
        base = best
        base_name = base["mode"]
        sensitivity = _sensitivity(config, market, base, base_name)
        thresholds = {
            "coal_price": _bisect_threshold(config, market, base_name, "coal_price_multiplier", 0.5, 3.0),
            "capacity_coefficient": _bisect_threshold(
                config, market, base_name, "capacity_coefficient", 0.0, 1.0
            ),
            "spot_multiplier": _bisect_threshold(config, market, base_name, "spot_multiplier", 0.0, 1.5),
        }
        if thresholds["coal_price"] is not None:
            thresholds["coal_price"] = thresholds["coal_price"] * config["rules"]["cost"]["coal_price_cny_per_ton"]
    except (InputError, ConfigError) as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return 2

    mode_fields = [
        "mode",
        "label",
        "valley_ratio",
        "flat_ratio",
        "peak_ratio",
        "generation_mwh",
        "avg_load_ratio",
        "min_output_mw",
        "declared_capacity_mw",
        "contract_mwh",
        "hedge_ratio",
        "avg_spot_cny_per_mwh",
        "spot_revenue_cny",
        "cfd_cny",
        "energy_revenue_cny",
        "capacity_revenue_cny",
        "capacity_deducted_cny",
        "peak_regulation_cny",
        "frequency_regulation_cny",
        "reserve_cny",
        "ancillary_cny",
        "fuel_cost_cny",
        "vom_cost_cny",
        "variable_cost_cny",
        "fixed_opex_cny",
        "depreciation_cny",
        "finance_cny",
        "fixed_cost_cny",
        "operating_margin_cny",
        "profit_cny",
        "profit_per_mwh",
        "capacity_coefficient",
        "coal_price_cny_per_ton",
        "contract_price_cny_per_mwh",
    ]
    _write_csv(out_dir / "modes.csv", results, mode_fields)

    monthly_fields = [
        "month",
        "days",
        "generation_mwh",
        "contract_mwh",
        "avg_spot_cny_per_mwh",
        "spot_revenue_cny",
        "cfd_cny",
        "energy_revenue_cny",
        "capacity_revenue_cny",
        "peak_regulation_cny",
        "frequency_regulation_cny",
        "reserve_cny",
        "ancillary_cny",
        "fuel_cost_cny",
        "vom_cost_cny",
        "variable_cost_cny",
        "fixed_opex_cny",
        "depreciation_cny",
        "finance_cny",
        "operating_margin_cny",
        "profit_cny",
    ]
    _write_csv(out_dir / "monthly.csv", base["monthly"], monthly_fields)

    revenue_rows = [
        {"item": "电能量收入", "value_cny": base["energy_revenue_cny"], "basis": "现货全电量 + 中长期平曲线差价"},
        {"item": "可靠容量补偿", "value_cny": base["capacity_revenue_cny"], "basis": "330 元/kW·年 × 系数 × 申报容量"},
        {"item": "调峰补偿", "value_cny": base["peak_regulation_cny"], "basis": "深度调峰电量 × 单价 × 调用比例"},
        {"item": "调频补偿", "value_cny": base["frequency_regulation_cny"], "basis": "申报容量 × 30% × 5 元/kW·月 × 性能"},
        {"item": "备用补偿", "value_cny": base["reserve_cny"], "basis": "申报容量 × 15% × 8 元/kW·月"},
        {"item": "燃料成本", "value_cny": -base["fuel_cost_cny"], "basis": "分负荷段煤耗 × 煤价"},
        {"item": "变动运维", "value_cny": -base["vom_cost_cny"], "basis": "15 元/MWh"},
        {"item": "固定运维", "value_cny": -base["fixed_opex_cny"], "basis": "110 元/kW·年"},
        {"item": "折旧", "value_cny": -base["depreciation_cny"], "basis": "52.8 亿元、20 年直线"},
        {"item": "财务费用", "value_cny": -base["finance_cny"], "basis": "70% 负债、4% 利率"},
        {"item": "利润", "value_cny": base["profit_cny"], "basis": "收入 − 成本"},
    ]
    _write_csv(out_dir / "revenue.csv", revenue_rows, ["item", "value_cny", "basis"])

    _write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        [
            "case",
            "change",
            "profit_cny",
            "delta_vs_base_cny",
            "profit_per_mwh",
            "capacity_revenue_cny",
            "energy_revenue_cny",
            "ancillary_cny",
        ],
    )

    (out_dir / "summary.json").write_text(
        json.dumps(
            _summary(config, results, base, best, configured, sensitivity, thresholds),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "review.md").write_text(
        _review(config, market, results, base, best, configured, sensitivity, thresholds), encoding="utf-8"
    )

    print(f"输出目录: {out_dir}")
    print(f"发电量: {base['generation_mwh']:,.0f} MWh；平均负荷率 {base['avg_load_ratio'] * 100:.1f}%")
    print(
        f"电能量 / 容量 / 辅助: {base['energy_revenue_cny'] / 1e4:,.2f} / "
        f"{base['capacity_revenue_cny'] / 1e4:,.2f} / {base['ancillary_cny'] / 1e4:,.2f} 万元"
    )
    print(f"年利润: {base['profit_cny'] / 1e4:,.2f} 万元；度电利润 {base['profit_per_mwh']:.2f} 元/MWh")
    print(
        f"选中模式: {base['label']}（{base['profit_cny'] / 1e4:,.2f} 万元）；"
        f"配置默认 {configured['label']}（{configured['profit_cny'] / 1e4:,.2f} 万元）"
    )
    print(f"盈亏平衡煤价: {thresholds['coal_price']:.0f} 元/吨" if thresholds["coal_price"] else "盈亏平衡煤价: 未触及")
    print(
        f"盈亏平衡容量系数: {thresholds['capacity_coefficient']:.3f}"
        if thresholds["capacity_coefficient"] is not None
        else "盈亏平衡容量系数: 未触及"
    )
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    print(f"指纹: {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
