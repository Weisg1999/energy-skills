#!/usr/bin/env python3
"""Liaoning load-side VPP portfolio instance runner.

Zero third-party dependencies. Compares four product-allocation strategies
under a shared MW budget and writes deterministic demo artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

RULE_BLOCKS = ("vpp", "spot", "demand_response", "ancillary", "cost")
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

    vpp = rules["vpp"]
    access = vpp.get("access")
    if not isinstance(access, dict):
        raise ConfigError("rules.vpp.access 必须是对象")
    _number(access, "min_aggregate_capacity_mw", "rules.vpp.access", low=0.0)
    _number(access, "min_regulation_capacity_mw", "rules.vpp.access", low=0.0)
    _number(access, "build_deadline_months", "rules.vpp.access", low=1.0)

    spot = rules["spot"]
    for key in (
        "declare_floor_cny_per_mwh",
        "declare_cap_cny_per_mwh",
        "clear_floor_cny_per_mwh",
        "clear_cap_cny_per_mwh",
    ):
        _number(spot, key, "rules.spot")
    if not spot["declare_floor_cny_per_mwh"] < spot["declare_cap_cny_per_mwh"]:
        raise ConfigError("现货申报下限必须小于上限")
    if not spot["clear_floor_cny_per_mwh"] < spot["clear_cap_cny_per_mwh"]:
        raise ConfigError("现货出清下限必须小于上限")

    demand = rules["demand_response"]
    _number(demand, "tolerance_ratio", "rules.demand_response", low=0.0, high=1.0)
    _number(demand, "penalty_multiplier", "rules.demand_response", low=0.0)
    _number(demand, "price_cny_per_mwh", "rules.demand_response", low=0.0)
    _number(demand, "valley_fill_price_cny_per_mwh", "rules.demand_response", low=0.0)

    ancillary = rules["ancillary"]
    _number(ancillary, "frequency_price_cny_per_kw_month", "rules.ancillary", low=0.0)

    cost = rules["cost"]
    _number(cost, "platform_cost_cny", "rules.cost", low=0.0)
    _number(cost, "measurement_cost_cny", "rules.cost", low=0.0)
    _number(cost, "storage_round_trip_efficiency", "rules.cost", low=0.01, high=1.0)
    _number(cost, "storage_degradation_cny_per_mwh", "rules.cost", low=0.0)
    _number(cost, "storage_duration_hours", "rules.cost", low=0.1)
    _number(cost, "members", "rules.cost", low=1.0)

    asset = raw.get("asset")
    if not isinstance(asset, dict):
        raise ConfigError("缺少 asset 块")
    for key in ("peak_load_mw", "flat_load_mw", "valley_load_mw", "tested_turndown_mw", "tested_ramp_up_mw"):
        _number(asset, key, "asset", low=0.0)
    _number(asset, "storage_mw", "asset", low=0.0)
    _number(asset, "storage_mwh", "asset", low=0.0)
    if not asset["valley_load_mw"] <= asset["flat_load_mw"] <= asset["peak_load_mw"]:
        raise ConfigError("基线负荷应满足谷段 ≤ 平段 ≤ 峰段")
    if asset["tested_turndown_mw"] > asset["peak_load_mw"]:
        raise ConfigError("可下调能力不能大于峰段基线负荷")
    if asset["storage_mwh"] < asset["storage_mw"] * cost["storage_duration_hours"] - 1e-9:
        raise ConfigError("储能电量不足以支撑申报时长")

    policy = raw.get("policy")
    if not isinstance(policy, dict):
        raise ConfigError("缺少 policy 块")
    _text(policy, "profile_id", "policy")
    _text(policy, "decision_rule", "policy")
    budget = _number(policy, "resource_budget_mw", "policy", low=0.0)
    if abs(budget - asset["tested_turndown_mw"]) > 1e-6:
        raise ConfigError("policy.resource_budget_mw 应等于 asset.tested_turndown_mw")
    shares = policy.get("shares")
    if not isinstance(shares, dict):
        raise ConfigError("policy.shares 必须是对象")
    for key in ("dr_share", "energy_share", "valley_fill_share"):
        _number(shares, key, "policy.shares", low=0.0, high=1.0)
    strategies = policy.get("strategies")
    if not isinstance(strategies, dict) or len(strategies) < 2:
        raise ConfigError("policy.strategies 至少需要两个策略")
    for name, strategy in strategies.items():
        if not isinstance(strategy, dict):
            raise ConfigError(f"policy.strategies.{name} 必须是对象")
        _text(strategy, "label", f"policy.strategies.{name}")
        dr = _number(strategy, "dr_mw", f"policy.strategies.{name}", low=0.0)
        fill = _number(strategy, "valley_fill_mw", f"policy.strategies.{name}", low=0.0)
        freq = _number(strategy, "freq_mw", f"policy.strategies.{name}", low=0.0)
        storage = _number(strategy, "storage_mw", f"policy.strategies.{name}", low=0.0)
        _number(strategy, "storage_cycles", f"policy.strategies.{name}", low=0.0)
        _number(strategy, "delivery_ratio", f"policy.strategies.{name}", low=0.0, high=1.0)
        if dr + freq + storage > budget + 1e-9:
            raise ConfigError(
                f"policy.strategies.{name} 的 DR + 调频 + 储能 = {dr + freq + storage:.1f} MW，"
                f"超过资源预算 {budget:.1f} MW；同一 MW 不能重复卖给多个品种"
            )
        if dr > asset["tested_turndown_mw"] + 1e-9:
            raise ConfigError(f"policy.strategies.{name}.dr_mw 超过可下调能力")
        if fill > asset["tested_ramp_up_mw"] + 1e-9:
            raise ConfigError(f"policy.strategies.{name}.valley_fill_mw 超过可上调能力")
        if storage > asset["storage_mw"] + 1e-9:
            raise ConfigError(f"policy.strategies.{name}.storage_mw 超过储能功率")
    default_strategy = _text(policy, "default_strategy", "policy")
    if default_strategy not in strategies:
        raise ConfigError("policy.default_strategy 不在 policy.strategies 中")

    contract = raw.get("data_contract")
    if not isinstance(contract, dict) or not isinstance(contract.get("market"), dict):
        raise ConfigError("缺少 data_contract.market")
    fields = contract["market"].get("required_fields")
    if not isinstance(fields, list) or not fields:
        raise ConfigError("data_contract.market.required_fields 必须是非空数组")
    for key in (
        "month",
        "days",
        "peak_price_cny_per_mwh",
        "valley_price_cny_per_mwh",
        "dr_call_hours",
        "dr_price_cny_per_mwh",
        "valley_fill_hours",
        "valley_fill_price_cny_per_mwh",
        "freq_price_cny_per_kw_month",
    ):
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
    spot = config["rules"]["spot"]
    for index, row in enumerate(rows, start=2):
        try:
            month = int(row["month"])
            days = int(row["days"])
            peak_hours = float(row["peak_hours"])
            flat_hours = float(row["flat_hours"])
            valley_hours = float(row["valley_hours"])
            peak_price = float(row["peak_price_cny_per_mwh"])
            flat_price = float(row["flat_price_cny_per_mwh"])
            valley_price = float(row["valley_price_cny_per_mwh"])
            dr_hours = float(row["dr_call_hours"])
            dr_price = float(row["dr_price_cny_per_mwh"])
            fill_hours = float(row["valley_fill_hours"])
            fill_price = float(row["valley_fill_price_cny_per_mwh"])
            freq_price = float(row["freq_price_cny_per_kw_month"])
        except (TypeError, ValueError) as exc:
            raise InputError(f"{path} 第 {index} 行存在非数字字段") from exc
        if not 1 <= month <= 12:
            raise InputError(f"{path} 第 {index} 行 month 必须在 1–12")
        if month in seen:
            raise InputError(f"{path} month {month} 重复")
        seen.add(month)
        if days < 1 or days > 31:
            raise InputError(f"{path} 第 {index} 行 days 必须在 1–31")
        if abs(peak_hours + flat_hours + valley_hours - 24.0) > 1e-9:
            raise InputError(f"{path} 第 {index} 行三段小时数之和必须为 24")
        for label, price in (("peak", peak_price), ("flat", flat_price), ("valley", valley_price)):
            if price < spot["clear_floor_cny_per_mwh"] or price > spot["clear_cap_cny_per_mwh"]:
                raise InputError(f"{path} 第 {index} 行 {label} 价格超出出清限价")
        for label, value in (
            ("dr_call_hours", dr_hours),
            ("dr_price", dr_price),
            ("valley_fill_hours", fill_hours),
            ("valley_fill_price", fill_price),
            ("freq_price", freq_price),
        ):
            if value < 0:
                raise InputError(f"{path} 第 {index} 行 {label} 不能为负")
        output.append(
            {
                "month": month,
                "days": days,
                "peak_hours": peak_hours,
                "flat_hours": flat_hours,
                "valley_hours": valley_hours,
                "peak_price": peak_price,
                "flat_price": flat_price,
                "valley_price": valley_price,
                "dr_call_hours": dr_hours,
                "dr_price": dr_price,
                "valley_fill_hours": fill_hours,
                "valley_fill_price": fill_price,
                "freq_price": freq_price,
            }
        )
    output.sort(key=lambda item: item["month"])
    if [item["month"] for item in output] != list(range(1, 13)):
        raise InputError("市场数据月份必须覆盖 1–12")
    days_total = sum(item["days"] for item in output)
    if days_total not in (365, 366):
        raise InputError(f"市场数据天数合计应为 365 或 366，实际 {days_total}")
    return output


def _strategy_result(config: dict, market: list[dict], name: str, strategy: dict, *, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    asset = config["asset"]
    rules = config["rules"]
    shares = config["policy"]["shares"]
    dr_share = float(overrides.get("dr_share", shares["dr_share"]))
    energy_share = float(shares["energy_share"])
    fill_share = float(shares["valley_fill_share"])
    if not 0.0 <= dr_share <= 1.0:
        raise InputError("dr_share 必须在 0–1")
    dr_mw = float(strategy["dr_mw"])
    fill_mw = float(strategy["valley_fill_mw"])
    freq_mw = float(strategy["freq_mw"])
    storage_mw = float(strategy["storage_mw"])
    storage_cycles = float(strategy["storage_cycles"])
    delivery_ratio = float(overrides.get("delivery_ratio_abs", strategy["delivery_ratio"]))
    delivery_ratio = max(0.0, min(1.0, delivery_ratio + float(overrides.get("delivery_delta", 0.0))))
    response_multiplier = float(overrides.get("baseline_haircut", 1.0))
    if not 0.0 <= response_multiplier <= 1.0:
        raise InputError("baseline_haircut 必须在 0–1")
    dr_price_multiplier = float(overrides.get("dr_price_multiplier", 1.0))
    peak_price_multiplier = float(overrides.get("peak_price_multiplier", 1.0))
    freq_price_multiplier = float(overrides.get("freq_price_multiplier", 1.0))
    storage_spread_multiplier = float(overrides.get("storage_spread_multiplier", 1.0))
    storage_degradation_multiplier = float(overrides.get("storage_degradation_multiplier", 1.0))
    platform_multiplier = float(overrides.get("platform_cost_multiplier", 1.0))

    days_total = sum(row["days"] for row in market)
    avg_peak_price = sum(row["peak_price"] * row["days"] for row in market) / days_total * peak_price_multiplier
    avg_valley_price = sum(row["valley_price"] * row["days"] for row in market) / days_total
    avg_freq_price = sum(row["freq_price"] * row["days"] for row in market) / days_total * freq_price_multiplier

    efficiency = rules["cost"]["storage_round_trip_efficiency"]
    degradation = rules["cost"]["storage_degradation_cny_per_mwh"] * storage_degradation_multiplier
    discharge_mwh = storage_mw * rules["cost"]["storage_duration_hours"] * storage_cycles
    charge_mwh = discharge_mwh / efficiency if efficiency else 0.0
    storage_gross = discharge_mwh * avg_peak_price - charge_mwh * avg_valley_price
    storage_net_annual = storage_gross * storage_spread_multiplier - discharge_mwh * degradation
    freq_annual = freq_mw * 1000.0 * avg_freq_price * 12.0
    platform_annual = (
        rules["cost"]["platform_cost_cny"] + rules["cost"]["measurement_cost_cny"]
    ) * platform_multiplier
    tolerance = rules["demand_response"]["tolerance_ratio"]
    penalty_multiplier = rules["demand_response"]["penalty_multiplier"]

    monthly = []
    totals = {
        "dr_mwh": 0.0,
        "dr_revenue_cny": 0.0,
        "energy_saving_cny": 0.0,
        "fill_mwh": 0.0,
        "fill_net_cny": 0.0,
        "freq_revenue_cny": 0.0,
        "storage_net_cny": 0.0,
        "penalty_cny": 0.0,
        "platform_cost_cny": 0.0,
        "vpp_revenue_cny": 0.0,
        "member_benefit_cny": 0.0,
        "total_benefit_cny": 0.0,
    }
    for row in market:
        actual_mw = dr_mw * delivery_ratio * response_multiplier
        dr_mwh = actual_mw * row["dr_call_hours"]
        dr_revenue = dr_mwh * row["dr_price"] * dr_price_multiplier
        energy_saving = dr_mwh * row["peak_price"] * peak_price_multiplier
        fill_mwh = fill_mw * row["valley_fill_hours"]
        fill_net = fill_mwh * (row["valley_fill_price"] - row["valley_price"])
        freq_revenue = freq_annual * row["days"] / days_total
        storage_net = storage_net_annual * row["days"] / days_total
        shortfall_mw = max(0.0, dr_mw - actual_mw)
        penalized_mw = max(0.0, shortfall_mw - dr_mw * tolerance)
        penalty = penalized_mw * row["dr_call_hours"] * row["dr_price"] * dr_price_multiplier * penalty_multiplier
        platform = platform_annual * row["days"] / days_total
        vpp_revenue = (
            dr_share * dr_revenue
            + energy_share * energy_saving
            + fill_share * fill_net
            + freq_revenue
            + storage_net
            - platform
            - penalty
        )
        member_benefit = (
            (1.0 - dr_share) * dr_revenue
            + (1.0 - energy_share) * energy_saving
            + (1.0 - fill_share) * fill_net
        )
        total_benefit = vpp_revenue + member_benefit
        monthly.append(
            {
                "month": row["month"],
                "days": row["days"],
                "declared_dr_mw": dr_mw,
                "actual_dr_mw": actual_mw,
                "dr_mwh": dr_mwh,
                "dr_revenue_cny": dr_revenue,
                "energy_saving_cny": energy_saving,
                "fill_mwh": fill_mwh,
                "fill_net_cny": fill_net,
                "freq_revenue_cny": freq_revenue,
                "storage_net_cny": storage_net,
                "penalty_cny": penalty,
                "platform_cost_cny": platform,
                "vpp_revenue_cny": vpp_revenue,
                "member_benefit_cny": member_benefit,
                "total_benefit_cny": total_benefit,
            }
        )
        totals["dr_mwh"] += dr_mwh
        totals["dr_revenue_cny"] += dr_revenue
        totals["energy_saving_cny"] += energy_saving
        totals["fill_mwh"] += fill_mwh
        totals["fill_net_cny"] += fill_net
        totals["freq_revenue_cny"] += freq_revenue
        totals["storage_net_cny"] += storage_net
        totals["penalty_cny"] += penalty
        totals["platform_cost_cny"] += platform
        totals["vpp_revenue_cny"] += vpp_revenue
        totals["member_benefit_cny"] += member_benefit
        totals["total_benefit_cny"] += total_benefit

    resource_used = dr_mw + freq_mw + storage_mw
    return {
        "strategy": name,
        "label": strategy["label"],
        "dr_mw": dr_mw,
        "fill_mw": fill_mw,
        "freq_mw": freq_mw,
        "storage_mw": storage_mw,
        "storage_cycles": storage_cycles,
        "resource_used_mw": resource_used,
        "resource_budget_mw": config["policy"]["resource_budget_mw"],
        "delivery_ratio": delivery_ratio,
        "actual_dr_mw": dr_mw * delivery_ratio * response_multiplier,
        "dr_mwh": totals["dr_mwh"],
        "dr_revenue_cny": totals["dr_revenue_cny"],
        "energy_saving_cny": totals["energy_saving_cny"],
        "fill_mwh": totals["fill_mwh"],
        "fill_net_cny": totals["fill_net_cny"],
        "freq_revenue_cny": totals["freq_revenue_cny"],
        "storage_net_cny": totals["storage_net_cny"],
        "penalty_cny": totals["penalty_cny"],
        "platform_cost_cny": totals["platform_cost_cny"],
        "vpp_revenue_cny": totals["vpp_revenue_cny"],
        "member_benefit_cny": totals["member_benefit_cny"],
        "total_benefit_cny": totals["total_benefit_cny"],
        "vpp_share_of_total": totals["vpp_revenue_cny"] / totals["total_benefit_cny"] if totals["total_benefit_cny"] else 0.0,
        "dr_share": dr_share,
        "monthly": monthly,
    }


def _bisect_threshold(config: dict, market: list[dict], strategy_name: str, key: str, low: float, high: float) -> float | None:
    def value(param: float) -> float:
        return _strategy_result(
            config,
            market,
            strategy_name,
            config["policy"]["strategies"][strategy_name],
            overrides={key: param},
        )["vpp_revenue_cny"]

    low_value = value(low)
    high_value = value(high)
    if (low_value > 0) == (high_value > 0):
        return None
    for _ in range(80):
        middle = (low + high) / 2.0
        if (value(middle) > 0) == (low_value > 0):
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _sensitivity(config: dict, market: list[dict], selected: dict, strategy_name: str) -> list[dict]:
    sensitivity = config["policy"]["sensitivity"]
    cases = [("基准", "选中策略、无压力", {})]
    for multiplier in sensitivity["dr_price_multipliers"]:
        label = "DR 价格 +30%" if multiplier > 1 else "DR 价格 −30%"
        cases.append((label, f"需求响应单价 × {multiplier:.2f}", {"dr_price_multiplier": multiplier}))
    for multiplier in sensitivity["peak_price_multipliers"]:
        label = "峰价 +15%" if multiplier > 1 else "峰价 −15%"
        cases.append((label, f"峰段价格 × {multiplier:.2f}", {"peak_price_multiplier": multiplier}))
    cases.append(("基线核减 20%", "实际响应按基线的 80% 计", {"baseline_haircut": sensitivity["baseline_haircut"]}))
    cases.append(
        (
            "交付比例 −10pp",
            f"从 {selected['delivery_ratio']:.0%} 降到 {selected['delivery_ratio'] - 0.1:.0%}",
            {"delivery_delta": sensitivity["delivery_delta"]},
        )
    )
    cases.append(("调频价格 −30%", "调频容量单价 × 0.70", {"freq_price_multiplier": sensitivity["freq_price_multiplier"]}))
    cases.append(
        (
            "储能退化 +50%",
            "退化成本 × 1.50",
            {"storage_degradation_multiplier": sensitivity["storage_degradation_multiplier"]},
        )
    )
    cases.append(
        (
            "储能价差 −30%",
            "充放电价差收益 × 0.70",
            {"storage_spread_multiplier": sensitivity["storage_spread_multiplier"]},
        )
    )
    cases.append(
        (
            "平台成本 +30%",
            "平台与核证成本 × 1.30",
            {"platform_cost_multiplier": sensitivity["platform_cost_multiplier"]},
        )
    )
    cases.append(
        (
            "VPP 分成 50%",
            "需求响应分成从 40% 提到 50%",
            {"dr_share": sensitivity["dr_share"]},
        )
    )
    cases.append(
        (
            "组合压力",
            "DR −30%、峰价 −15%、基线核减 20%、交付 −10pp、储能价差 −30%、平台 +30%",
            {
                "dr_price_multiplier": 0.7,
                "peak_price_multiplier": 0.85,
                "baseline_haircut": 0.8,
                "delivery_delta": -0.1,
                "storage_spread_multiplier": 0.7,
                "platform_cost_multiplier": 1.3,
            },
        )
    )
    rows = []
    for label, change, overrides in cases:
        result = _strategy_result(
            config, market, strategy_name, config["policy"]["strategies"][strategy_name], overrides=overrides
        )
        rows.append(
            {
                "case": label,
                "change": change,
                "vpp_revenue_cny": result["vpp_revenue_cny"],
                "delta_vs_base_cny": result["vpp_revenue_cny"] - selected["vpp_revenue_cny"],
                "member_benefit_cny": result["member_benefit_cny"],
                "total_benefit_cny": result["total_benefit_cny"],
                "penalty_cny": result["penalty_cny"],
                "dr_revenue_cny": result["dr_revenue_cny"],
            }
        )
    return rows


def _fmt_wan(value_cny: float) -> str:
    return f"{value_cny / 1e4:,.2f}"


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def _fmt_pct(value: float, digits: int = 1) -> str:
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
    selected: dict,
    best_total: dict,
    sensitivity: list[dict],
    thresholds: dict,
) -> str:
    meta = config["meta"]
    policy = config["policy"]
    asset = config["asset"]
    rules = config["rules"]
    fingerprint = hashlib.sha1(
        json.dumps(policy, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    conflict = best_total["strategy"] != selected["strategy"]
    lines = [
        "# 辽宁负荷侧 VPP 组合 · 复核表",
        "",
        f"> 实例 `{meta['instance_id']}` · {meta['province']} · {meta['entity_type']} · 数据截止 {meta['data_cutoff']} · 等级 {meta['grade']}",
        "",
        "## 1. 结论",
        "",
        f"- VPP 净收益最大的策略是 **{selected['label']}**：VPP 净收益 {_fmt_wan(selected['vpp_revenue_cny'])} 万元，"
        f"成员收益 {_fmt_wan(selected['member_benefit_cny'])} 万元，总盘 {_fmt_wan(selected['total_benefit_cny'])} 万元。",
        f"- 总盘最大的策略是 **{best_total['label']}**：总盘 {_fmt_wan(best_total['total_benefit_cny'])} 万元，"
        f"VPP 净收益 {_fmt_wan(best_total['vpp_revenue_cny'])} 万元。",
    ]
    if conflict:
        lines.append(
            f"- **VPP 最优与总盘最优不一致**：VPP 选 {selected['label']} 比 {best_total['label']} 多赚 "
            f"{_fmt_wan(selected['vpp_revenue_cny'] - best_total['vpp_revenue_cny'])} 万元，但总盘少 "
            f"{_fmt_wan(best_total['total_benefit_cny'] - selected['total_benefit_cny'])} 万元，成员少 "
            f"{_fmt_wan(best_total['member_benefit_cny'] - selected['member_benefit_cny'])} 万元。"
            "分成合同决定谁承担效率损失，不能只看 VPP 自己的账。"
        )
    lines.extend(
        [
            f"- 资源预算：可下调能力 {asset['tested_turndown_mw']:.0f} MW，需求响应 + 调频 + 储能放电合计不得超过；"
            f"选中策略使用 {selected['resource_used_mw']:.0f} MW。",
            f"- 交付考核：申报 DR {selected['dr_mw']:.0f} MW，实际 {selected['actual_dr_mw']:.2f} MW，"
            f"交付率 {_fmt_pct(selected['delivery_ratio'])}，考核扣款 {_fmt_wan(selected['penalty_cny'])} 万元。",
            "",
            "**一句话**：VPP 的钱不是“品种越多越赚”，而是**同一份 MW 的机会成本**——"
            "把高价值的 DR 容量挪给低价值品种，收入可能不升反降，还会触发交付考核。",
            "",
            "## 2. 四策略对比",
            "",
            "| 策略 | DR / 调频 / 储能（MW） | 资源占用 | 交付率 | DR 电量（MWh） | VPP 净收益（万元） | 成员收益（万元） | 总盘（万元） |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in sorted(results, key=lambda item: item["vpp_revenue_cny"], reverse=True):
        marker = " ← VPP 最优" if result["strategy"] == selected["strategy"] else ""
        lines.append(
            f"| {result['label']} | {result['dr_mw']:.0f} / {result['freq_mw']:.0f} / {result['storage_mw']:.0f} | "
            f"{result['resource_used_mw']:.0f} / {result['resource_budget_mw']:.0f} MW | "
            f"{_fmt_pct(result['delivery_ratio'])} | {_fmt(result['dr_mwh'], 0)} | "
            f"{_fmt_wan(result['vpp_revenue_cny'])} | {_fmt_wan(result['member_benefit_cny'])} | "
            f"{_fmt_wan(result['total_benefit_cny'])}{marker} |"
        )
    lines.extend(
        [
            "",
            "四策略的 DR + 调频 + 储能放电都不超过 18 MW，不是“叠加”，而是**分配**。"
            "全栈申报把 8 MW 留给 DR、5 MW 给调频、5 MW 给储能，DR 收入和交付率同时下降，"
            "考核扣款吃掉调频与储能的增量，VPP 净收益反而最低。",
            "",
            "## 3. 选中策略月表",
            "",
            "| 月 | DR 电量（MWh） | DR 收入（万元） | 节电收益（万元） | 填谷净收益（万元） | 调频（万元） | 储能（万元） | 考核（万元） | VPP 净收益（万元） |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in selected["monthly"]:
        lines.append(
            f"| {row['month']} | {_fmt(row['dr_mwh'], 0)} | {_fmt_wan(row['dr_revenue_cny'])} | "
            f"{_fmt_wan(row['energy_saving_cny'])} | {_fmt_wan(row['fill_net_cny'])} | "
            f"{_fmt_wan(row['freq_revenue_cny'])} | {_fmt_wan(row['storage_net_cny'])} | "
            f"{_fmt_wan(row['penalty_cny'])} | {_fmt_wan(row['vpp_revenue_cny'])} |"
        )
    lines.extend(
        [
            "",
            "## 4. 资源预算与品种分配",
            "",
            f"- 18 MW 是可下调能力，不是“每种品种各 18 MW”。DR、调频容量、储能放电共用同一份 MW；"
            f"策略配置在校验时强制 `DR + 调频 + 储能 ≤ {policy['resource_budget_mw']:.0f} MW`。",
            f"- 需求响应补偿 {rules['demand_response']['price_cny_per_mwh']:.0f} 元/MWh，是最高价值品种；"
            "调频 15 元/kW·月、储能价差收益都要按同一 MW 的机会成本比较。",
            f"- 填谷电量按可上调能力 {asset['tested_ramp_up_mw']:.0f} MW 约束，不与下调能力混用。",
            "",
            "## 5. 需求响应、基线与考核",
            "",
            f"- 交付率 {_fmt_pct(selected['delivery_ratio'])}；容差 {_fmt_pct(rules['demand_response']['tolerance_ratio'], 0)}；"
            f"超出容差的短供按 {rules['demand_response']['penalty_multiplier']:.1f} 倍 DR 单价扣款。",
            f"- 选中策略考核扣款 {_fmt_wan(selected['penalty_cny'])} 万元；基线核减 20% 会同时减少 DR 收入与节电收益，"
            "并放大短供考核。",
            "- 基线是“同类型日历史平均”，不是用户自己报多少算多少；基线核减、异常日剔除与计量核证必须在合同里写清。",
            "",
            "## 6. 敏感性",
            "",
            "| 情景 | 关键变化 | VPP 净收益（万元） | 较基准（万元） | 成员收益（万元） | 总盘（万元） | 考核（万元） |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {row['change']} | {_fmt_wan(row['vpp_revenue_cny'])} | "
            f"{row['delta_vs_base_cny'] / 1e4:+,.2f} | {_fmt_wan(row['member_benefit_cny'])} | "
            f"{_fmt_wan(row['total_benefit_cny'])} | {_fmt_wan(row['penalty_cny'])} |"
        )
    lines.extend(["", "## 7. 临界值", ""])
    dr_break = thresholds.get("dr_price_multiplier")
    if dr_break is None:
        lines.append("- DR 价格盈亏平衡：在 0–3 倍范围内未触及。")
    else:
        lines.append(f"- DR 价格盈亏平衡：约 **{dr_break:.2f} 倍**（基准 1.00）。")
    delivery_break = thresholds.get("delivery_ratio")
    if delivery_break is None:
        lines.append("- 交付率盈亏平衡：在 30%–100% 范围内未触及。")
    else:
        lines.append(f"- 交付率盈亏平衡：约 **{_fmt_pct(delivery_break)}**（选中策略 {_fmt_pct(selected['delivery_ratio'])}）。")
    spread_break = thresholds.get("storage_spread_multiplier")
    if spread_break is None:
        lines.append("- 储能价差盈亏平衡：在 0–2 倍范围内未触及。")
    else:
        lines.append(f"- 储能价差盈亏平衡：约 **{spread_break:.2f} 倍**（基准 1.00）。")
    lines.extend(
        [
            "",
            "## 8. 口径提醒",
            "",
            "- 辽宁现货是**连续结算试运行**，不是省级正式运行；日前只预出清、不结算，本包用月度三段价格近似，不能替代 96 点节点价。",
            "- VPP 在现货“报量不报价、优先出清”，不等于没有价格风险；结算按实际现货价，响应成本要低于当时价格才有净收益。",
            "- 10 MW/5 MW 是辽宁接入门槛（总聚合 ≥10 MW、总调节 ≥5 MW），不是可交易容量，也不是山西/山东/海南的门槛；不能跨省套用。",
            "- 需求响应补偿、调频价格、交付比例、基线方法与分成比例均为 D 级演示假设；正式品种、限价、结算与考核细则待核实。",
            "- 同一 MW 不能同时卖给 DR、调频和储能；本包用资源预算硬约束，实际项目还要做时序校验与能力测试。",
            "- 本包只算调节收益与分成，不含成员全部电费、零售套餐、绿电、容量补偿与两个细则考核，不是聚合商完整损益表。",
            "",
            f"风格指纹 `{fingerprint}`；本复核表由 `run.py` 生成，计算期 {sum(row['days'] for row in market)} 天。",
            "",
        ]
    )
    return "\n".join(lines)


def _summary(
    config: dict,
    results: list[dict],
    selected: dict,
    best_total: dict,
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
        "selected_strategy": selected["strategy"],
        "best_total_strategy": best_total["strategy"],
        "conflict": selected["strategy"] != best_total["strategy"],
        "asset": {
            "peak_load_mw": config["asset"]["peak_load_mw"],
            "tested_turndown_mw": config["asset"]["tested_turndown_mw"],
            "tested_ramp_up_mw": config["asset"]["tested_ramp_up_mw"],
            "storage_mw": config["asset"]["storage_mw"],
            "members": config["rules"]["cost"]["members"],
        },
        "selected": {
            "dr_mw": selected["dr_mw"],
            "freq_mw": selected["freq_mw"],
            "storage_mw": selected["storage_mw"],
            "resource_used_mw": selected["resource_used_mw"],
            "delivery_ratio": selected["delivery_ratio"],
            "dr_mwh": selected["dr_mwh"],
            "dr_revenue_cny": selected["dr_revenue_cny"],
            "vpp_revenue_cny": selected["vpp_revenue_cny"],
            "member_benefit_cny": selected["member_benefit_cny"],
            "total_benefit_cny": selected["total_benefit_cny"],
            "penalty_cny": selected["penalty_cny"],
        },
        "strategies": [
            {
                "strategy": result["strategy"],
                "label": result["label"],
                "dr_mw": result["dr_mw"],
                "freq_mw": result["freq_mw"],
                "storage_mw": result["storage_mw"],
                "vpp_revenue_cny": result["vpp_revenue_cny"],
                "member_benefit_cny": result["member_benefit_cny"],
                "total_benefit_cny": result["total_benefit_cny"],
                "penalty_cny": result["penalty_cny"],
            }
            for result in results
        ],
        "sensitivity": sensitivity,
        "thresholds": thresholds,
        "warnings": [
            "辽宁现货为连续结算试运行，非正式运行",
            "需求响应、调频价格、交付比例与基线方法为 D 级假设",
            "10 MW/5 MW 为辽宁接入门槛，不能跨省套用",
            "本包不含成员全部电费与零售套餐",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="辽宁负荷侧 VPP 组合实例")
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
            f"接入门槛: 总聚合 ≥{config['rules']['vpp']['access']['min_aggregate_capacity_mw']:.0f} MW、"
            f"总调节 ≥{config['rules']['vpp']['access']['min_regulation_capacity_mw']:.0f} MW"
        )
        print(
            f"资源: 峰段 {config['asset']['peak_load_mw']:.0f} MW、可下调 "
            f"{config['asset']['tested_turndown_mw']:.0f} MW、可上调 "
            f"{config['asset']['tested_ramp_up_mw']:.0f} MW、储能 "
            f"{config['asset']['storage_mw']:.0f} MW / {config['asset']['storage_mwh']:.0f} MWh"
        )
        print("策略:")
        for name, strategy in config["policy"]["strategies"].items():
            print(
                f"  - {name}（{strategy['label']}）：DR {strategy['dr_mw']:.0f} MW、"
                f"调频 {strategy['freq_mw']:.0f} MW、储能 {strategy['storage_mw']:.0f} MW、"
                f"交付率 {strategy['delivery_ratio']:.0%}"
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
            _strategy_result(config, market, name, strategy)
            for name, strategy in config["policy"]["strategies"].items()
        ]
        selected = max(results, key=lambda result: result["vpp_revenue_cny"])
        best_total = max(results, key=lambda result: result["total_benefit_cny"])
        sensitivity = _sensitivity(config, market, selected, selected["strategy"])
        thresholds = {
            "dr_price_multiplier": _bisect_threshold(
                config, market, selected["strategy"], "dr_price_multiplier", 0.0, 3.0
            ),
            "delivery_ratio": _bisect_threshold(
                config, market, selected["strategy"], "delivery_ratio_abs", 0.3, 1.0
            ),
            "storage_spread_multiplier": _bisect_threshold(
                config, market, selected["strategy"], "storage_spread_multiplier", 0.0, 2.0
            ),
        }
    except (InputError, ConfigError) as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return 2

    strategy_fields = [
        "strategy",
        "label",
        "dr_mw",
        "fill_mw",
        "freq_mw",
        "storage_mw",
        "storage_cycles",
        "resource_used_mw",
        "resource_budget_mw",
        "delivery_ratio",
        "actual_dr_mw",
        "dr_mwh",
        "dr_revenue_cny",
        "energy_saving_cny",
        "fill_mwh",
        "fill_net_cny",
        "freq_revenue_cny",
        "storage_net_cny",
        "penalty_cny",
        "platform_cost_cny",
        "vpp_revenue_cny",
        "member_benefit_cny",
        "total_benefit_cny",
        "vpp_share_of_total",
        "dr_share",
    ]
    _write_csv(out_dir / "strategies.csv", results, strategy_fields)

    monthly_fields = [
        "month",
        "days",
        "declared_dr_mw",
        "actual_dr_mw",
        "dr_mwh",
        "dr_revenue_cny",
        "energy_saving_cny",
        "fill_mwh",
        "fill_net_cny",
        "freq_revenue_cny",
        "storage_net_cny",
        "penalty_cny",
        "platform_cost_cny",
        "vpp_revenue_cny",
        "member_benefit_cny",
        "total_benefit_cny",
    ]
    _write_csv(out_dir / "monthly.csv", selected["monthly"], monthly_fields)

    revenue_rows = [
        {"item": "需求响应收入", "value_cny": selected["dr_revenue_cny"], "basis": "实际响应电量 × DR 单价"},
        {"item": "成员节电收益", "value_cny": selected["energy_saving_cny"], "basis": "实际响应电量 × 峰段价格"},
        {"item": "填谷净收益", "value_cny": selected["fill_net_cny"], "basis": "填谷电量 ×（补偿价 − 谷价）"},
        {"item": "调频收入", "value_cny": selected["freq_revenue_cny"], "basis": "调频 MW × 月单价 × 12"},
        {"item": "储能净收益", "value_cny": selected["storage_net_cny"], "basis": "峰谷价差 − 充电成本 − 退化"},
        {"item": "考核扣款", "value_cny": -selected["penalty_cny"], "basis": "超容差短供 × DR 单价 × 1.2"},
        {"item": "平台与核证成本", "value_cny": -selected["platform_cost_cny"], "basis": "平台 100 万 + 核证 20 万"},
        {"item": "VPP 净收益", "value_cny": selected["vpp_revenue_cny"], "basis": "分成 + 调频 + 储能 − 考核 − 平台"},
    ]
    _write_csv(out_dir / "revenue.csv", revenue_rows, ["item", "value_cny", "basis"])

    _write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        [
            "case",
            "change",
            "vpp_revenue_cny",
            "delta_vs_base_cny",
            "member_benefit_cny",
            "total_benefit_cny",
            "penalty_cny",
            "dr_revenue_cny",
        ],
    )

    (out_dir / "summary.json").write_text(
        json.dumps(
            _summary(config, results, selected, best_total, sensitivity, thresholds),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "review.md").write_text(
        _review(config, market, results, selected, best_total, sensitivity, thresholds), encoding="utf-8"
    )

    print(f"输出目录: {out_dir}")
    print(
        f"选中策略: {selected['label']}；VPP 净收益 {selected['vpp_revenue_cny'] / 1e4:,.2f} 万元；"
        f"成员 {selected['member_benefit_cny'] / 1e4:,.2f} 万元；总盘 {selected['total_benefit_cny'] / 1e4:,.2f} 万元"
    )
    print(
        f"总盘最优: {best_total['label']}（{best_total['total_benefit_cny'] / 1e4:,.2f} 万元）；"
        f"VPP 最优与总盘最优{'不一致' if selected['strategy'] != best_total['strategy'] else '一致'}"
    )
    print(
        f"DR 电量 {selected['dr_mwh']:,.0f} MWh；交付率 {selected['delivery_ratio'] * 100:.1f}%；"
        f"考核 {selected['penalty_cny'] / 1e4:,.2f} 万元"
    )
    print(
        "DR 价格盈亏平衡: "
        + (f"{thresholds['dr_price_multiplier']:.2f} 倍" if thresholds["dr_price_multiplier"] else "未触及")
    )
    print(
        "交付率盈亏平衡: "
        + (f"{thresholds['delivery_ratio'] * 100:.1f}%" if thresholds["delivery_ratio"] else "未触及")
    )
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    print(f"指纹: {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
