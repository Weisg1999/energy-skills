#!/usr/bin/env python3
"""Shenzhen V2G aggregation instance runner.

Zero third-party dependencies. Compares four product-allocation strategies
under one bidirectional-capacity budget and writes deterministic demo artifacts.

The binding constraint is not nameplate charger power but:
- tested capability = min(charger power x coincidence x availability, reverse limit)
- daily usable energy = vehicles x usable kWh x coincidence x availability
so a 7.31 MW fleet with 1.8 h duration cannot sell 7.31 MW for a 4 h peak.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

RULE_BLOCKS = ("v2g", "vpp", "spot", "demand_response", "ancillary", "cost")
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


def _site_capability(site: dict) -> dict:
    power_mw = (
        float(site["vehicles"])
        * float(site["charger_kw"])
        * float(site["coincidence"])
        * float(site["availability"])
        / 1000.0
    )
    energy_mwh = (
        float(site["vehicles"])
        * float(site["usable_kwh"])
        * float(site["coincidence"])
        * float(site["availability"])
        / 1000.0
    )
    tested_mw = min(power_mw, float(site["reverse_limit_mw"]))
    return {
        "id": site["id"],
        "label": site["label"],
        "vehicles": int(site["vehicles"]),
        "power_mw": power_mw,
        "energy_mwh": energy_mwh,
        "reverse_limit_mw": float(site["reverse_limit_mw"]),
        "transformer_mva": float(site["transformer_mva"]),
        "tested_mw": tested_mw,
        "duration_h": energy_mwh / tested_mw if tested_mw else 0.0,
        "limited_by": "配变反向限额" if power_mw > float(site["reverse_limit_mw"]) + 1e-9 else "车-桩可用功率",
        "charger_capex_cny": int(site["vehicles"]) * float(site["charger_cost_cny"]),
    }


def _fleet_summary(asset: dict) -> dict:
    sites = [_site_capability(site) for site in asset["sites"]]
    tested_mw = sum(site["tested_mw"] for site in sites)
    energy_mwh = sum(site["energy_mwh"] for site in sites)
    return {
        "sites": sites,
        "power_mw": sum(site["power_mw"] for site in sites),
        "energy_mwh": energy_mwh,
        "tested_mw": tested_mw,
        "duration_h": energy_mwh / tested_mw if tested_mw else 0.0,
        "charger_capex_cny": sum(site["charger_capex_cny"] for site in sites),
    }


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

    v2g = rules["v2g"]
    _number(v2g, "pilot_cities", "rules.v2g", low=1)
    _number(v2g, "pilot_projects", "rules.v2g", low=1)
    _number(v2g, "national_target_2030_mw", "rules.v2g", low=0)

    vpp = rules["vpp"]
    access = vpp.get("access")
    if not isinstance(access, dict):
        raise ConfigError("rules.vpp.access 必须是对象")
    min_capacity = _number(access, "min_aggregate_capacity_mw", "rules.vpp.access", low=0)
    min_duration = _number(access, "min_duration_hours", "rules.vpp.access", low=0)
    min_resource = _number(access, "min_resource_mw", "rules.vpp.access", low=0)

    spot = rules["spot"]
    declare_floor = _number(spot, "declare_floor_cny_per_mwh", "rules.spot")
    declare_cap = _number(spot, "declare_cap_cny_per_mwh", "rules.spot")
    clear_floor = _number(spot, "clear_floor_cny_per_mwh", "rules.spot")
    clear_cap = _number(spot, "clear_cap_cny_per_mwh", "rules.spot")
    if not declare_floor < declare_cap:
        raise ConfigError("现货申报下限必须小于上限")
    if not clear_floor < clear_cap:
        raise ConfigError("现货出清下限必须小于上限")
    if declare_floor < clear_floor - 1e-9 or declare_cap > clear_cap + 1e-9:
        raise ConfigError("申报区间必须落在出清区间内")
    _text(spot, "v2g_price_basis", "rules.spot")

    demand = rules["demand_response"]
    tolerance = _number(demand, "tolerance_ratio", "rules.demand_response", low=0.0, high=1.0)
    penalty_multiplier = _number(demand, "penalty_multiplier", "rules.demand_response", low=0.0)
    max_event_hours = _number(demand, "max_event_hours", "rules.demand_response", low=0.1)
    dr_cap = _number(demand, "price_cap_cny_per_mwh", "rules.demand_response", low=0.0)

    ancillary = rules["ancillary"]
    _number(ancillary, "reserve_price_cny_per_kw_month", "rules.ancillary", low=0.0)
    _number(ancillary, "min_duration_hours", "rules.ancillary", low=0.0)

    cost = rules["cost"]
    life = _number(cost, "charger_life_years", "rules.cost", low=1.0)
    install_ratio = _number(cost, "charger_installation_ratio", "rules.cost", low=0.0, high=1.0)
    opex_ratio = _number(cost, "charger_opex_ratio", "rules.cost", low=0.0, high=1.0)
    _number(cost, "platform_cost_cny", "rules.cost", low=0.0)
    _number(cost, "measurement_cost_cny", "rules.cost", low=0.0)
    _number(cost, "battery_degradation_cny_per_mwh", "rules.cost", low=0.0)
    _number(cost, "round_trip_efficiency", "rules.cost", low=0.01, high=1.0)
    for key in ("owner_share_arbitrage", "owner_share_dr", "owner_share_reserve"):
        _number(cost, key, "rules.cost", low=0.0, high=1.0)
    members = _number(cost, "members", "rules.cost", low=1.0)
    del life, install_ratio, opex_ratio, members  # validated above; used later from config

    asset = raw.get("asset")
    if not isinstance(asset, dict):
        raise ConfigError("缺少 asset 块")
    vehicle_total = _number(asset, "vehicle_total", "asset", low=1.0)
    _number(asset, "operating_days_per_year", "asset", low=1.0, high=366.0)
    sites = asset.get("sites")
    if not isinstance(sites, list) or len(sites) < 2:
        raise ConfigError("asset.sites 至少需要两个站点")
    seen = set()
    vehicle_sum = 0.0
    for index, site in enumerate(sites):
        where = f"asset.sites[{index}]"
        if not isinstance(site, dict):
            raise ConfigError(f"{where} 必须是对象")
        site_id = _text(site, "id", where)
        if site_id in seen:
            raise ConfigError(f"{where}.id 重复：{site_id}")
        seen.add(site_id)
        _text(site, "label", where)
        vehicles = _number(site, "vehicles", where, low=1.0)
        vehicle_sum += vehicles
        battery = _number(site, "battery_kwh", where, low=1.0)
        usable = _number(site, "usable_kwh", where, low=0.0)
        _number(site, "charger_kw", where, low=0.0)
        _number(site, "coincidence", where, low=0.0, high=1.0)
        _number(site, "availability", where, low=0.0, high=1.0)
        soc_min = _number(site, "soc_min", where, low=0.0, high=1.0)
        soc_max = _number(site, "soc_max", where, low=0.0, high=1.0)
        if soc_min >= soc_max:
            raise ConfigError(f"{where}.soc_min 必须小于 soc_max")
        if usable > battery * (soc_max - soc_min) + 1e-9:
            raise ConfigError(
                f"{where}.usable_kwh 超过电池 ×（soc_max − soc_min）的可放电量"
            )
        transformer = _number(site, "transformer_mva", where, low=0.0)
        reverse = _number(site, "reverse_limit_mw", where, low=0.0)
        if reverse > transformer + 1e-9:
            raise ConfigError(f"{where}.reverse_limit_mw 不能大于配变容量")
        _number(site, "charger_cost_cny", where, low=0.0)
    if abs(vehicle_sum - vehicle_total) > 1e-6:
        raise ConfigError("asset.vehicle_total 应等于各站点 vehicles 之和")
    if abs(vehicle_total - float(cost["members"])) > 1e-6:
        raise ConfigError("rules.cost.members 应等于 asset.vehicle_total")

    fleet = _fleet_summary(asset)
    if fleet["tested_mw"] + 1e-9 < min_capacity:
        raise ConfigError(
            f"实测聚合能力 {fleet['tested_mw']:.2f} MW 低于准入门槛 {min_capacity:.2f} MW"
        )
    if fleet["duration_h"] + 1e-9 < min_duration:
        raise ConfigError(
            f"聚合持续时间 {fleet['duration_h']:.2f} h 低于准入门槛 {min_duration:.2f} h"
        )
    for site in fleet["sites"]:
        if site["tested_mw"] + 1e-9 < min_resource:
            raise ConfigError(
                f"站点 {site['id']} 的实测能力 {site['tested_mw']:.3f} MW 低于最小资源门槛"
            )

    policy = raw.get("policy")
    if not isinstance(policy, dict):
        raise ConfigError("缺少 policy 块")
    _text(policy, "profile_id", "policy")
    _text(policy, "decision_rule", "policy")
    budget = _number(policy, "resource_budget_mw", "policy", low=0.0)
    if abs(budget - fleet["tested_mw"]) > 1e-6:
        raise ConfigError(
            f"policy.resource_budget_mw 应等于实测能力 {fleet['tested_mw']:.3f} MW"
        )
    _number(policy, "arbitrage_delivery_ratio", "policy", low=0.0, high=1.0)
    strategies = policy.get("strategies")
    if not isinstance(strategies, dict) or len(strategies) < 2:
        raise ConfigError("policy.strategies 至少需要两个策略")
    for name, strategy in strategies.items():
        if not isinstance(strategy, dict):
            raise ConfigError(f"policy.strategies.{name} 必须是对象")
        _text(strategy, "label", f"policy.strategies.{name}")
        arb = _number(strategy, "arb_mw", f"policy.strategies.{name}", low=0.0)
        dr = _number(strategy, "dr_mw", f"policy.strategies.{name}", low=0.0)
        reserve = _number(strategy, "reserve_mw", f"policy.strategies.{name}", low=0.0)
        _number(strategy, "delivery_ratio", f"policy.strategies.{name}", low=0.0, high=1.0)
        if arb + dr + reserve > budget + 1e-9:
            raise ConfigError(
                f"policy.strategies.{name} 的套利 + DR + 备用 = {arb + dr + reserve:.2f} MW，"
                f"超过容量预算 {budget:.2f} MW；同一 MW 不能重复卖给多个品种"
            )
        if dr * max_event_hours > fleet["energy_mwh"] + 1e-9:
            raise ConfigError(
                f"policy.strategies.{name}.dr_mw × {max_event_hours:.1f} h = "
                f"{dr * max_event_hours:.1f} MWh，超过车队日可用电量 {fleet['energy_mwh']:.1f} MWh"
            )
        if reserve * float(ancillary["min_duration_hours"]) > fleet["energy_mwh"] + 1e-9:
            raise ConfigError(f"policy.strategies.{name}.reserve_mw 超过日可用电量约束")
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
        "peak_hours",
        "flat_hours",
        "valley_hours",
        "peak_price_cny_per_mwh",
        "flat_price_cny_per_mwh",
        "valley_price_cny_per_mwh",
        "v2g_discharge_price_cny_per_mwh",
        "dr_call_hours",
        "dr_price_cny_per_mwh",
        "reserve_price_cny_per_kw_month",
    ):
        if key not in fields:
            raise ConfigError(f"data_contract.market.required_fields 缺少 {key}")

    # store derived context for later checks without mutating the raw config file
    raw["_derived"] = {
        "fleet": fleet,
        "declare_floor": declare_floor,
        "declare_cap": declare_cap,
        "clear_floor": clear_floor,
        "clear_cap": clear_cap,
        "dr_cap": dr_cap,
        "tolerance": tolerance,
        "penalty_multiplier": penalty_multiplier,
        "max_event_hours": max_event_hours,
    }
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
    derived = config["_derived"]
    clear_floor = derived["clear_floor"]
    clear_cap = derived["clear_cap"]
    dr_cap = derived["dr_cap"]
    output = []
    seen = set()
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
            v2g_price = float(row["v2g_discharge_price_cny_per_mwh"])
            dr_hours = float(row["dr_call_hours"])
            dr_price = float(row["dr_price_cny_per_mwh"])
            reserve_price = float(row["reserve_price_cny_per_kw_month"])
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
        if peak_hours <= 0:
            raise InputError(f"{path} 第 {index} 行 peak_hours 必须大于 0")
        for label, price in (("peak", peak_price), ("flat", flat_price), ("valley", valley_price)):
            if price < clear_floor or price > clear_cap:
                raise InputError(f"{path} 第 {index} 行 {label} 价格超出出清限价")
        if v2g_price < 0 or v2g_price > clear_cap:
            raise InputError(f"{path} 第 {index} 行 v2g 放电价超出合理区间")
        if dr_price < 0 or dr_price > dr_cap + 1e-9:
            raise InputError(f"{path} 第 {index} 行 DR 价格超过申报上限 {dr_cap:.0f}")
        for label, value in (
            ("dr_call_hours", dr_hours),
            ("dr_price", dr_price),
            ("reserve_price", reserve_price),
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
                "v2g_price": v2g_price,
                "dr_hours": dr_hours,
                "dr_price": dr_price,
                "reserve_price": reserve_price,
            }
        )
    output.sort(key=lambda item: item["month"])
    if [item["month"] for item in output] != list(range(1, 13)):
        raise InputError("市场数据月份必须覆盖 1–12")
    days_total = sum(item["days"] for item in output)
    if days_total not in (365, 366):
        raise InputError(f"市场数据天数合计应为 365 或 366，实际 {days_total}")
    return output


def _strategy_result(
    config: dict,
    market: list[dict],
    name: str,
    strategy: dict,
    *,
    overrides: dict | None = None,
) -> dict:
    overrides = overrides or {}
    asset = config["asset"]
    cost = config["rules"]["cost"]
    derived = config["_derived"]
    fleet = derived["fleet"]

    arb_mw = float(strategy["arb_mw"])
    dr_mw = float(strategy["dr_mw"])
    reserve_mw = float(strategy["reserve_mw"])
    delivery = float(overrides.get("delivery_abs", strategy["delivery_ratio"]))
    delivery = max(0.0, min(1.0, delivery + float(overrides.get("delivery_delta", 0.0))))

    v2g_mult = float(overrides.get("v2g_price_multiplier", 1.0))
    valley_mult = float(overrides.get("valley_price_multiplier", 1.0))
    dr_price_mult = float(overrides.get("dr_price_multiplier", 1.0))
    dr_hours_mult = float(overrides.get("dr_hours_multiplier", 1.0))
    deg_mult = float(overrides.get("degradation_multiplier", 1.0))
    charger_mult = float(overrides.get("charger_capex_multiplier", 1.0))
    platform_mult = float(overrides.get("platform_cost_multiplier", 1.0))
    operating_days = float(overrides.get("operating_days", asset["operating_days_per_year"]))
    owner_delta = float(overrides.get("owner_share_delta", 0.0))
    if not 0.0 <= operating_days <= 366.0:
        raise InputError("operating_days 必须在 0–366")
    owner_arb = max(0.0, min(1.0, float(cost["owner_share_arbitrage"]) + owner_delta))
    owner_dr = max(0.0, min(1.0, float(cost["owner_share_dr"]) + owner_delta))
    owner_res = max(0.0, min(1.0, float(cost["owner_share_reserve"]) + owner_delta))

    efficiency = float(cost["round_trip_efficiency"])
    degradation = float(cost["battery_degradation_cny_per_mwh"]) * deg_mult
    arb_delivery = float(config["policy"]["arbitrage_delivery_ratio"])
    daily_energy = fleet["energy_mwh"] * arb_delivery
    max_event_hours = derived["max_event_hours"]
    if dr_mw * max_event_hours > fleet["energy_mwh"] + 1e-9:
        raise InputError(
            f"{name}: DR {dr_mw:.2f} MW × {max_event_hours:.1f} h 超过日可用电量"
        )

    charger_annual = (
        fleet["charger_capex_cny"]
        * (1.0 + float(cost["charger_installation_ratio"]))
        / float(cost["charger_life_years"])
        + fleet["charger_capex_cny"] * float(cost["charger_opex_ratio"])
    ) * charger_mult
    other_annual = (
        float(cost["platform_cost_cny"]) + float(cost["measurement_cost_cny"])
    ) * platform_mult

    monthly = []
    totals = {
        "arb_mwh": 0.0,
        "arb_revenue_cny": 0.0,
        "arb_charge_cost_cny": 0.0,
        "arb_degradation_cny": 0.0,
        "arb_net_cny": 0.0,
        "dr_mwh": 0.0,
        "dr_revenue_cny": 0.0,
        "dr_penalty_cny": 0.0,
        "dr_net_cny": 0.0,
        "reserve_revenue_cny": 0.0,
        "fixed_cost_cny": 0.0,
        "owner_benefit_cny": 0.0,
        "vpp_net_cny": 0.0,
        "total_benefit_cny": 0.0,
        "effective_peak_hours": 0.0,
        "operating_days": 0.0,
        "limited_months": 0,
    }
    for row in market:
        op_days = row["days"] / 365.0 * operating_days
        arb_energy_day = min(arb_mw * row["peak_hours"], daily_energy)
        arb_mwh = arb_energy_day * op_days
        arb_effective_mw = arb_energy_day / row["peak_hours"]
        limited = arb_mw * row["peak_hours"] > daily_energy + 1e-9
        if limited:
            totals["limited_months"] += 1
        arb_revenue = arb_mwh * row["v2g_price"] * v2g_mult
        arb_charge = arb_mwh / efficiency * row["valley_price"] * valley_mult
        arb_degradation = arb_mwh * degradation
        arb_net = arb_revenue - arb_charge - arb_degradation

        dr_mwh = dr_mw * row["dr_hours"] * dr_hours_mult * delivery
        dr_revenue = dr_mwh * row["dr_price"] * dr_price_mult
        shortfall_mw = dr_mw * (1.0 - delivery)
        penalized_mw = max(0.0, shortfall_mw - dr_mw * derived["tolerance"])
        penalty = (
            penalized_mw
            * row["dr_hours"]
            * dr_hours_mult
            * row["dr_price"]
            * dr_price_mult
            * derived["penalty_multiplier"]
        )
        dr_net = dr_revenue - penalty

        reserve_revenue = reserve_mw * 1000.0 * row["reserve_price"]
        fixed_cost = (charger_annual + other_annual) * row["days"] / 365.0

        owner_benefit = (
            owner_arb * arb_net
            + owner_dr * dr_net
            + owner_res * reserve_revenue
        )
        vpp_net = (
            (1.0 - owner_arb) * arb_net
            + (1.0 - owner_dr) * dr_net
            + (1.0 - owner_res) * reserve_revenue
            - fixed_cost
        )
        total_benefit = owner_benefit + vpp_net

        monthly.append(
            {
                "month": row["month"],
                "days": row["days"],
                "operating_days": op_days,
                "peak_hours": row["peak_hours"],
                "valley_hours": row["valley_hours"],
                "arb_declared_mw": arb_mw,
                "arb_effective_mw": arb_effective_mw,
                "arb_mwh": arb_mwh,
                "arb_revenue_cny": arb_revenue,
                "arb_charge_cost_cny": arb_charge,
                "arb_degradation_cny": arb_degradation,
                "arb_net_cny": arb_net,
                "dr_mwh": dr_mwh,
                "dr_revenue_cny": dr_revenue,
                "dr_penalty_cny": penalty,
                "dr_net_cny": dr_net,
                "reserve_revenue_cny": reserve_revenue,
                "fixed_cost_cny": fixed_cost,
                "owner_benefit_cny": owner_benefit,
                "vpp_net_cny": vpp_net,
                "total_benefit_cny": total_benefit,
            }
        )
        totals["arb_mwh"] += arb_mwh
        totals["arb_revenue_cny"] += arb_revenue
        totals["arb_charge_cost_cny"] += arb_charge
        totals["arb_degradation_cny"] += arb_degradation
        totals["arb_net_cny"] += arb_net
        totals["dr_mwh"] += dr_mwh
        totals["dr_revenue_cny"] += dr_revenue
        totals["dr_penalty_cny"] += penalty
        totals["dr_net_cny"] += dr_net
        totals["reserve_revenue_cny"] += reserve_revenue
        totals["fixed_cost_cny"] += fixed_cost
        totals["owner_benefit_cny"] += owner_benefit
        totals["vpp_net_cny"] += vpp_net
        totals["total_benefit_cny"] += total_benefit
        totals["effective_peak_hours"] += op_days * row["peak_hours"]
        totals["operating_days"] += op_days

    arb_effective_mw = (
        totals["arb_mwh"] / totals["effective_peak_hours"]
        if totals["effective_peak_hours"]
        else 0.0
    )
    avg_peak_hours = (
        totals["effective_peak_hours"] / totals["operating_days"]
        if totals["operating_days"]
        else 0.0
    )
    energy_limited = arb_mw * avg_peak_hours > daily_energy + 1e-9

    return {
        "strategy": name,
        "label": strategy["label"],
        "arb_mw": arb_mw,
        "dr_mw": dr_mw,
        "reserve_mw": reserve_mw,
        "resource_used_mw": arb_mw + dr_mw + reserve_mw,
        "resource_budget_mw": float(config["policy"]["resource_budget_mw"]),
        "delivery_ratio": delivery,
        "arb_delivery_ratio": arb_delivery,
        "arb_effective_mw": arb_effective_mw,
        "arb_energy_limited": energy_limited,
        "arb_limited_months": totals["limited_months"],
        "avg_peak_hours": avg_peak_hours,
        "daily_energy_mwh": daily_energy,
        "arb_mwh": totals["arb_mwh"],
        "arb_revenue_cny": totals["arb_revenue_cny"],
        "arb_charge_cost_cny": totals["arb_charge_cost_cny"],
        "arb_degradation_cny": totals["arb_degradation_cny"],
        "arb_net_cny": totals["arb_net_cny"],
        "dr_mwh": totals["dr_mwh"],
        "dr_revenue_cny": totals["dr_revenue_cny"],
        "dr_penalty_cny": totals["dr_penalty_cny"],
        "dr_net_cny": totals["dr_net_cny"],
        "reserve_revenue_cny": totals["reserve_revenue_cny"],
        "fixed_cost_cny": totals["fixed_cost_cny"],
        "owner_benefit_cny": totals["owner_benefit_cny"],
        "vpp_net_cny": totals["vpp_net_cny"],
        "total_benefit_cny": totals["total_benefit_cny"],
        "owner_share_arbitrage": owner_arb,
        "owner_share_dr": owner_dr,
        "owner_share_reserve": owner_res,
        "operating_days": totals["operating_days"],
        "monthly": monthly,
    }


def _bisect_zero(
    config: dict,
    market: list[dict],
    strategy_name: str,
    key: str,
    low: float,
    high: float,
) -> float | None:
    strategy = config["policy"]["strategies"][strategy_name]

    def value(param: float) -> float:
        return _strategy_result(
            config, market, strategy_name, strategy, overrides={key: param}
        )["vpp_net_cny"]

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


def _bisect_cross(
    config: dict,
    market: list[dict],
    name_a: str,
    name_b: str,
    key: str,
    low: float,
    high: float,
) -> float | None:
    strategy_a = config["policy"]["strategies"][name_a]
    strategy_b = config["policy"]["strategies"][name_b]

    def value(param: float) -> float:
        a = _strategy_result(
            config, market, name_a, strategy_a, overrides={key: param}
        )["vpp_net_cny"]
        b = _strategy_result(
            config, market, name_b, strategy_b, overrides={key: param}
        )["vpp_net_cny"]
        return a - b

    low_value = value(low)
    high_value = value(high)
    if low_value * high_value > 0:
        return None
    for _ in range(80):
        middle = (low + high) / 2.0
        if value(middle) * low_value <= 0:
            high = middle
        else:
            low = middle
            low_value = value(low)
    return (low + high) / 2.0


def _sensitivity(
    config: dict,
    market: list[dict],
    selected: dict,
    strategy_name: str,
) -> list[dict]:
    sensitivity = config["policy"]["sensitivity"]
    cases = [("基准", "选中策略、无压力", {})]
    for multiplier in sensitivity["v2g_price_multipliers"]:
        label = "V2G 放电价 +20%" if multiplier > 1 else "V2G 放电价 −20%"
        cases.append((label, f"放电价 × {multiplier:.2f}", {"v2g_price_multiplier": multiplier}))
    for multiplier in sensitivity["valley_price_multipliers"]:
        label = "谷电价 +20%" if multiplier > 1 else "谷电价 −20%"
        cases.append((label, f"充电谷价 × {multiplier:.2f}", {"valley_price_multiplier": multiplier}))
    for multiplier in sensitivity["dr_price_multipliers"]:
        label = "DR 价格 +30%" if multiplier > 1 else "DR 价格 −30%"
        cases.append((label, f"DR 单价 × {multiplier:.2f}", {"dr_price_multiplier": multiplier}))
    for multiplier in sensitivity["dr_hours_multipliers"]:
        label = "DR 调用 +50%" if multiplier > 1 else "DR 调用 −50%"
        cases.append((label, f"DR 小时 × {multiplier:.2f}", {"dr_hours_multiplier": multiplier}))
    cases.append(
        (
            "交付率 −10pp",
            f"从 {selected['delivery_ratio']:.0%} 降到 {max(0.0, selected['delivery_ratio'] - 0.1):.0%}",
            {"delivery_delta": sensitivity["delivery_delta"]},
        )
    )
    cases.append(
        (
            "电池退化 +50%",
            "退化成本 × 1.50",
            {"degradation_multiplier": sensitivity["degradation_multiplier"]},
        )
    )
    cases.append(
        (
            "双向桩成本 +30%",
            "桩与安装年化 × 1.30",
            {"charger_capex_multiplier": sensitivity["charger_capex_multiplier"]},
        )
    )
    cases.append(
        (
            "年运营 200 天",
            "从 300 天降到 200 天",
            {"operating_days": sensitivity["operating_days"]},
        )
    )
    cases.append(
        (
            "车主分成 +10pp",
            "套利/DR/备用车主分成各 +10 个百分点",
            {"owner_share_delta": sensitivity["owner_share_delta"]},
        )
    )
    combined = sensitivity["combined"]
    cases.append(
        (
            "组合压力",
            "放电价 −20%、谷价 +20%、DR 价格 −30%、DR 小时 −50%、交付 −10pp、退化 +50%、桩成本 +30%、200 天",
            {
                "v2g_price_multiplier": combined["v2g_price_multiplier"],
                "valley_price_multiplier": combined["valley_price_multiplier"],
                "dr_price_multiplier": combined["dr_price_multiplier"],
                "dr_hours_multiplier": combined["dr_hours_multiplier"],
                "delivery_delta": combined["delivery_delta"],
                "degradation_multiplier": combined["degradation_multiplier"],
                "charger_capex_multiplier": combined["charger_capex_multiplier"],
                "operating_days": combined["operating_days"],
            },
        )
    )
    rows = []
    for label, change, overrides in cases:
        result = _strategy_result(
            config,
            market,
            strategy_name,
            config["policy"]["strategies"][strategy_name],
            overrides=overrides,
        )
        rows.append(
            {
                "case": label,
                "change": change,
                "vpp_net_cny": result["vpp_net_cny"],
                "delta_vs_base_cny": result["vpp_net_cny"] - selected["vpp_net_cny"],
                "owner_benefit_cny": result["owner_benefit_cny"],
                "total_benefit_cny": result["total_benefit_cny"],
                "arb_net_cny": result["arb_net_cny"],
                "dr_net_cny": result["dr_net_cny"],
                "dr_penalty_cny": result["dr_penalty_cny"],
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
    cost = rules["cost"]
    fleet = config["_derived"]["fleet"]
    fingerprint = hashlib.sha1(
        json.dumps(policy, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    conflict = best_total["strategy"] != selected["strategy"]
    lines = [
        "# 深圳 V2G 聚合 · 复核表",
        "",
        f"> 实例 `{meta['instance_id']}` · {meta['province']} · {meta['entity_type']} · 数据截止 {meta['data_cutoff']} · 等级 {meta['grade']}",
        "",
        "## 1. 结论",
        "",
        f"- VPP 净收益最大的策略是 **{selected['label']}**：VPP 净收益 {_fmt_wan(selected['vpp_net_cny'])} 万元，"
        f"车主收益 {_fmt_wan(selected['owner_benefit_cny'])} 万元，总盘 {_fmt_wan(selected['total_benefit_cny'])} 万元。",
        f"- 总盘最大的策略是 **{best_total['label']}**：总盘 {_fmt_wan(best_total['total_benefit_cny'])} 万元，"
        f"VPP 净收益 {_fmt_wan(best_total['vpp_net_cny'])} 万元。",
    ]
    if conflict:
        lines.append(
            f"- **VPP 最优与总盘最优不一致**：VPP 选 {selected['label']} 比 {best_total['label']} 多赚 "
            f"{_fmt_wan(selected['vpp_net_cny'] - best_total['vpp_net_cny'])} 万元，但总盘少 "
            f"{_fmt_wan(best_total['total_benefit_cny'] - selected['total_benefit_cny'])} 万元；"
            "分成与考核条款决定谁承担效率损失。"
        )
    lines.extend(
        [
            f"- 选中策略申报套利 {selected['arb_mw']:.2f} MW，能量受限后有效 **{selected['arb_effective_mw']:.2f} MW**；"
            f"日可用电量 {selected['daily_energy_mwh']:.2f} MWh，平均峰段 {selected['avg_peak_hours']:.1f} h，"
            f"所以“报多少 MW”不等于“能放多少 MW”。",
            f"- DR 申报 {selected['dr_mw']:.2f} MW、年调用 {sum(row['dr_hours'] for row in market):.0f} h；"
            f"备用 {selected['reserve_mw']:.2f} MW；资源占用 {selected['resource_used_mw']:.2f} / "
            f"{selected['resource_budget_mw']:.2f} MW。",
            f"- 固定成本（桩年化 + 安装 + 运维 + 平台 + 计量）{_fmt_wan(selected['fixed_cost_cny'])} 万元/年；"
            f"套利净收益 {_fmt_wan(selected['arb_net_cny'])} 万元、DR 净收益 {_fmt_wan(selected['dr_net_cny'])} 万元、"
            f"备用 {_fmt_wan(selected['reserve_revenue_cny'])} 万元。",
            "",
            "**一句话**：V2G 的收益不是由单价最高的品种决定，而是由 **MW × 一年能调用多少小时** 决定；"
            "套利单价低但一年可用上千小时，DR 单价高但只调用一两百小时，只做 DR 会把高价值容量锁在低利用率品种上。",
            "",
            "## 2. 四策略对比",
            "",
            "| 策略 | 套利 / DR / 备用（MW） | 资源占用 | 套利有效 MW | 套利电量（MWh） | DR 电量（MWh） | VPP 净收益（万元） | 车主收益（万元） | 总盘（万元） |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for result in sorted(results, key=lambda item: item["vpp_net_cny"], reverse=True):
        marker = " ← VPP 最优" if result["strategy"] == selected["strategy"] else ""
        lines.append(
            f"| {result['label']} | {result['arb_mw']:.2f} / {result['dr_mw']:.2f} / {result['reserve_mw']:.2f} | "
            f"{result['resource_used_mw']:.2f} / {result['resource_budget_mw']:.2f} MW | "
            f"{result['arb_effective_mw']:.2f} | {_fmt(result['arb_mwh'], 0)} | {_fmt(result['dr_mwh'], 0)} | "
            f"{_fmt_wan(result['vpp_net_cny'])} | {_fmt_wan(result['owner_benefit_cny'])} | "
            f"{_fmt_wan(result['total_benefit_cny'])}{marker} |"
        )
    lines.extend(
        [
            "",
            "套利、DR、备用共用同一份 MW；四策略的资源占用都不超过容量预算，不是“叠加”，而是**分配**。"
            "套利申报超过能量允许的功率时，多报的 MW 不会带来更多电量，只会挤占 DR 与备用。",
            "",
            "## 3. 选中策略月表",
            "",
            "| 月 | 套利电量（MWh） | 套利净收益（万元） | DR 电量（MWh） | DR 净收益（万元） | 备用（万元） | 固定成本（万元） | VPP 净收益（万元） | 车主（万元） | 总盘（万元） |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in selected["monthly"]:
        lines.append(
            f"| {row['month']} | {_fmt(row['arb_mwh'], 0)} | {_fmt_wan(row['arb_net_cny'])} | "
            f"{_fmt(row['dr_mwh'], 0)} | {_fmt_wan(row['dr_net_cny'])} | {_fmt_wan(row['reserve_revenue_cny'])} | "
            f"{_fmt_wan(row['fixed_cost_cny'])} | {_fmt_wan(row['vpp_net_cny'])} | "
            f"{_fmt_wan(row['owner_benefit_cny'])} | {_fmt_wan(row['total_benefit_cny'])} |"
        )
    lines.extend(
        [
            "",
            "## 4. 站点能力与配变约束",
            "",
            "| 站点 | 车辆 | 车-桩可用功率（MW） | 日可用电量（MWh） | 配变（MVA） | 反向限额（MW） | 实测能力（MW） | 持续时间（h） | 桩投资（万元） | 受限环节 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for site in fleet["sites"]:
        lines.append(
            f"| {site['label']} | {site['vehicles']} | {site['power_mw']:.2f} | {site['energy_mwh']:.2f} | "
            f"{site['transformer_mva']:.1f} | {site['reverse_limit_mw']:.2f} | {site['tested_mw']:.2f} | "
            f"{site['duration_h']:.2f} | {_fmt_wan(site['charger_capex_cny'])} | {site['limited_by']} |"
        )
    lines.extend(
        [
            "",
            f"- 铭牌/车-桩可用功率合计 {fleet['power_mw']:.2f} MW，配变反向限额后实测 "
            f"{fleet['tested_mw']:.2f} MW；少掉的 {fleet['power_mw'] - fleet['tested_mw']:.2f} MW 不是“效率损失”，"
            "而是配变、保护与台区承载力不允许。",
            f"- 车队日可用电量 {fleet['energy_mwh']:.2f} MWh，按实测能力折合持续时间 "
            f"{fleet['duration_h']:.2f} h；广东 VPP 要求 ≥{rules['vpp']['access']['min_duration_hours']:.0f} h，"
            "本包通过，但不足以支撑 4 h 满功率放电。",
            "",
            "## 5. 成本、退化与分成",
            "",
            f"- 双向桩投资合计 {_fmt_wan(fleet['charger_capex_cny'])} 万元；按 {cost['charger_life_years']} 年折旧、"
            f"安装 {_fmt_pct(cost['charger_installation_ratio'], 0)}、运维 {_fmt_pct(cost['charger_opex_ratio'], 0)} 年化，"
            f"加平台 {_fmt_wan(cost['platform_cost_cny'])} 万元/年、计量核证 {_fmt_wan(cost['measurement_cost_cny'])} 万元/年。",
            f"- 电池退化 {cost['battery_degradation_cny_per_mwh']:.0f} 元/MWh、往返效率 "
            f"{_fmt_pct(cost['round_trip_efficiency'], 0)}；套利充电成本按“放电量 ÷ 效率 × 谷价”计。",
            f"- 车主分成：套利 {_fmt_pct(selected['owner_share_arbitrage'], 0)}、DR "
            f"{_fmt_pct(selected['owner_share_dr'], 0)}、备用 {_fmt_pct(selected['owner_share_reserve'], 0)}；"
            "分成基数均为扣除充电成本与退化后的净收益（备用为收入）。",
            f"- 选中策略固定成本 {_fmt_wan(selected['fixed_cost_cny'])} 万元/年，是聚合商自己承担的刚性成本；"
            "只做套利时 VPP 净收益可能为负，原因不是套利不赚钱，而是车主分走一半后剩余毛利覆盖不了桩与平台。",
            "",
            "## 6. 敏感性",
            "",
            "| 情景 | 关键变化 | VPP 净收益（万元） | 较基准（万元） | 车主收益（万元） | 总盘（万元） | 套利净收益（万元） | DR 净收益（万元） | 考核（万元） |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {row['change']} | {_fmt_wan(row['vpp_net_cny'])} | "
            f"{row['delta_vs_base_cny'] / 1e4:+,.2f} | {_fmt_wan(row['owner_benefit_cny'])} | "
            f"{_fmt_wan(row['total_benefit_cny'])} | {_fmt_wan(row['arb_net_cny'])} | "
            f"{_fmt_wan(row['dr_net_cny'])} | {_fmt_wan(row['dr_penalty_cny'])} |"
        )
    lines.extend(["", "## 7. 临界值", ""])
    avg_dr_price = sum(row["dr_price"] * row["dr_hours"] for row in market) / max(
        1e-9, sum(row["dr_hours"] for row in market)
    )
    avg_v2g_price = sum(row["v2g_price"] * row["days"] for row in market) / sum(
        row["days"] for row in market
    )
    v2g_break = thresholds.get("vpp_breakeven_v2g_multiplier")
    if v2g_break is None:
        lines.append("- VPP 净收益为零的放电价倍数：在 0.2–1.5 倍范围内未触及。")
    else:
        lines.append(
            f"- VPP 净收益为零的放电价倍数：约 **{v2g_break:.2f} 倍**（基准 1.00，"
            f"约 {v2g_break * avg_v2g_price:,.0f} 元/MWh）。"
        )
    days_break = thresholds.get("vpp_breakeven_operating_days")
    if days_break is None:
        lines.append("- VPP 净收益为零的年运营天数：在 50–300 天范围内未触及。")
    else:
        lines.append(f"- VPP 净收益为零的年运营天数：约 **{days_break:.0f} 天**（基准 300 天）。")
    charger_break = thresholds.get("vpp_breakeven_charger_multiplier")
    if charger_break is None:
        lines.append("- VPP 净收益为零的桩成本倍数：在 0.5–3.0 倍范围内未触及。")
    else:
        lines.append(f"- VPP 净收益为零的桩成本倍数：约 **{charger_break:.2f} 倍**（基准 1.00）。")
    dr_switch = thresholds.get("switch_dr_price_multiplier")
    if dr_switch is None:
        lines.append("- DR 优先反超均衡组合的 DR 价格倍数：在 0.5–3.0 倍范围内未触及。")
    else:
        lines.append(
            f"- DR 优先反超均衡组合的 DR 价格倍数：约 **{dr_switch:.2f} 倍**（基准 1.00，"
            f"约 {dr_switch * avg_dr_price:,.0f} 元/MWh；广东申报上限 2,700 元/MWh）。"
        )
        if dr_switch * avg_dr_price > rules["demand_response"]["price_cap_cny_per_mwh"]:
            lines.append(
                "- 该临界值**高于广东 2,700 元/MWh 的申报上限**：在现行价格上限内，DR 优先难以反超均衡组合；"
                "把 DR 当成主力品种，需要更高的补偿或更长的调用小时，而不是只看单价。"
            )
    v2g_switch = thresholds.get("switch_v2g_price_multiplier")
    if v2g_switch is None:
        lines.append("- DR 优先反超均衡组合的放电价倍数：在 0.3–1.2 倍范围内未触及。")
    else:
        lines.append(
            f"- DR 优先反超均衡组合的放电价倍数：约 **{v2g_switch:.2f} 倍**（基准 1.00，"
            f"约 {v2g_switch * avg_v2g_price:,.0f} 元/MWh）；放电价跌破该水平时，DR 优先开始占优。"
        )
    lines.extend(
        [
            "",
            "## 8. 口径提醒",
            "",
            "- 深圳 VPP 平台“510 万 kW 接入”“140 万 kW 最大可调”和“实际响应”是三层口径；本包的 7.31 MW 是 D 级合成聚合能力，不是深圳全市 V2G 容量。",
            "- “140 万 kW”是全类型可调资源，不是 V2G 反向放电容量；不要把 VPP 规模直接当成 V2G 规模。",
            "- 光明虹桥公园 61 辆车 / 4.21 MW 是单站公开报道，不是本包资产，也不能按单站复制推算全市；城市级规模要靠站点数量与配网承载力。",
            "- 首批试点是 9 个城市、30 个项目（部分报道称 32 个）；2030 年 5,000 万 kW 是“聚合可调充电规模”，含有序充电，不是反向放电功率。",
            "- 广东现货 2026 南方区域正式方案给广东价区申报下限 −50 元/MWh、出清 −50–1,800 元/MWh；1,500 元/MWh 申报上限是本包建模上限，不能当官方参数引用。",
            "- DR 2,700 元/MWh 是广东 2026 削峰年度交易申报价格上限，不是结算价；容差、考核倍数、调用小时与单次时长均为 D 级假设。",
            "- 备用 8 元/kW·月参考广州 VPP 备用 ≤0.01 元/kW·h 的公开口径折算，是邻近城市参考，不是深圳本地价格。",
            "- V2G 放电价、电池退化、桩成本、分成比例均为 D 级假设；输配电费抵扣、需量电费、容量补偿、绿证/碳、补贴与税费均未计入。",
            "- 同一 MW 不能同时卖给套利、DR 和备用；本包用容量预算与时序能量约束，实际项目还要做站点级、台区级与保护校核。",
            "- 本包不是聚合商完整损益表，也不是 V2G 投资建议；真实项目以车辆清单、桩铭牌、并网测试、台区承载力评估与合同为准。",
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
    policy = config["policy"]
    fleet = config["_derived"]["fleet"]
    fingerprint = hashlib.sha1(
        json.dumps(policy, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return {
        "instance_id": config["meta"]["instance_id"],
        "province": config["meta"]["province"],
        "profile_id": policy["profile_id"],
        "fingerprint": fingerprint,
        "data_cutoff": config["meta"]["data_cutoff"],
        "selected_strategy": selected["strategy"],
        "best_total_strategy": best_total["strategy"],
        "conflict": selected["strategy"] != best_total["strategy"],
        "fleet": {
            "power_mw": fleet["power_mw"],
            "tested_mw": fleet["tested_mw"],
            "energy_mwh": fleet["energy_mwh"],
            "duration_h": fleet["duration_h"],
            "charger_capex_cny": fleet["charger_capex_cny"],
            "sites": fleet["sites"],
        },
        "selected": {
            "arb_mw": selected["arb_mw"],
            "dr_mw": selected["dr_mw"],
            "reserve_mw": selected["reserve_mw"],
            "resource_used_mw": selected["resource_used_mw"],
            "resource_budget_mw": selected["resource_budget_mw"],
            "delivery_ratio": selected["delivery_ratio"],
            "arb_effective_mw": selected["arb_effective_mw"],
            "arb_energy_limited": selected["arb_energy_limited"],
            "arb_mwh": selected["arb_mwh"],
            "arb_net_cny": selected["arb_net_cny"],
            "dr_mwh": selected["dr_mwh"],
            "dr_net_cny": selected["dr_net_cny"],
            "dr_penalty_cny": selected["dr_penalty_cny"],
            "reserve_revenue_cny": selected["reserve_revenue_cny"],
            "fixed_cost_cny": selected["fixed_cost_cny"],
            "owner_benefit_cny": selected["owner_benefit_cny"],
            "vpp_net_cny": selected["vpp_net_cny"],
            "total_benefit_cny": selected["total_benefit_cny"],
        },
        "strategies": [
            {
                "strategy": result["strategy"],
                "label": result["label"],
                "arb_mw": result["arb_mw"],
                "dr_mw": result["dr_mw"],
                "reserve_mw": result["reserve_mw"],
                "resource_used_mw": result["resource_used_mw"],
                "arb_effective_mw": result["arb_effective_mw"],
                "arb_mwh": result["arb_mwh"],
                "dr_mwh": result["dr_mwh"],
                "owner_benefit_cny": result["owner_benefit_cny"],
                "vpp_net_cny": result["vpp_net_cny"],
                "total_benefit_cny": result["total_benefit_cny"],
                "dr_penalty_cny": result["dr_penalty_cny"],
            }
            for result in results
        ],
        "sensitivity": sensitivity,
        "thresholds": thresholds,
        "warnings": [
            "深圳 510 万 kW 是接入规模、140 万 kW 是最大可调能力，二者都不是实际响应或 V2G 反向容量",
            "9 城 30 个项目（部分报道称 32 个），引用时注明口径",
            "V2G 放电价、DR 补偿、备用价格、退化、桩成本与分成为 D 级假设",
            "本包不含输配电费抵扣、需量电费、容量补偿、绿证/碳、补贴与税费",
            "配变反向限额与日可用电量是硬约束；申报 MW 不等于有效 MW",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="深圳 V2G 聚合实例")
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
        fleet = config["_derived"]["fleet"]
        print("配置校验通过")
        print(f"实例: {meta['instance_id']} · {meta['province']} · {meta['entity_type']}")
        print(f"规则版本: {meta['rule_version']}")
        print(f"风格: {config['policy']['profile_id']}")
        print(
            f"准入: 聚合 ≥{config['rules']['vpp']['access']['min_aggregate_capacity_mw']:.0f} MW、"
            f"持续 ≥{config['rules']['vpp']['access']['min_duration_hours']:.0f} h、"
            f"单资源 ≥{config['rules']['vpp']['access']['min_resource_mw']:.2f} MW"
        )
        print(
            f"车队: 车-桩可用 {fleet['power_mw']:.2f} MW、日可用电量 {fleet['energy_mwh']:.2f} MWh、"
            f"配变限额后实测 {fleet['tested_mw']:.2f} MW、持续 {fleet['duration_h']:.2f} h"
        )
        print("站点:")
        for site in fleet["sites"]:
            print(
                f"  - {site['label']}：{site['vehicles']} 辆、可用 {site['power_mw']:.2f} MW、"
                f"日电量 {site['energy_mwh']:.2f} MWh、反向限额 {site['reverse_limit_mw']:.2f} MW、"
                f"实测 {site['tested_mw']:.2f} MW（{site['limited_by']}）"
            )
        print("策略:")
        for name, strategy in config["policy"]["strategies"].items():
            print(
                f"  - {name}（{strategy['label']}）：套利 {strategy['arb_mw']:.2f} MW、"
                f"DR {strategy['dr_mw']:.2f} MW、备用 {strategy['reserve_mw']:.2f} MW、"
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
        selected = max(results, key=lambda result: result["vpp_net_cny"])
        best_total = max(results, key=lambda result: result["total_benefit_cny"])
        sensitivity = _sensitivity(config, market, selected, selected["strategy"])
        thresholds = {
            "vpp_breakeven_v2g_multiplier": _bisect_zero(
                config, market, selected["strategy"], "v2g_price_multiplier", 0.2, 1.5
            ),
            "vpp_breakeven_operating_days": _bisect_zero(
                config, market, selected["strategy"], "operating_days", 50.0, 300.0
            ),
            "vpp_breakeven_charger_multiplier": _bisect_zero(
                config, market, selected["strategy"], "charger_capex_multiplier", 0.5, 3.0
            ),
            "switch_dr_price_multiplier": _bisect_cross(
                config, market, "dr_first", "balanced", "dr_price_multiplier", 0.5, 3.0
            ),
            "switch_v2g_price_multiplier": _bisect_cross(
                config, market, "dr_first", "balanced", "v2g_price_multiplier", 0.3, 1.2
            ),
        }
    except (InputError, ConfigError) as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return 2

    strategy_fields = [
        "strategy",
        "label",
        "arb_mw",
        "dr_mw",
        "reserve_mw",
        "resource_used_mw",
        "resource_budget_mw",
        "delivery_ratio",
        "arb_effective_mw",
        "arb_energy_limited",
        "arb_limited_months",
        "arb_mwh",
        "arb_revenue_cny",
        "arb_charge_cost_cny",
        "arb_degradation_cny",
        "arb_net_cny",
        "dr_mwh",
        "dr_revenue_cny",
        "dr_penalty_cny",
        "dr_net_cny",
        "reserve_revenue_cny",
        "fixed_cost_cny",
        "owner_benefit_cny",
        "vpp_net_cny",
        "total_benefit_cny",
    ]
    _write_csv(out_dir / "strategies.csv", results, strategy_fields)

    site_rows = []
    for site in config["_derived"]["fleet"]["sites"]:
        site_rows.append(
            {
                "site": site["id"],
                "label": site["label"],
                "vehicles": site["vehicles"],
                "power_mw": site["power_mw"],
                "energy_mwh": site["energy_mwh"],
                "transformer_mva": site["transformer_mva"],
                "reverse_limit_mw": site["reverse_limit_mw"],
                "tested_mw": site["tested_mw"],
                "duration_h": site["duration_h"],
                "limited_by": site["limited_by"],
                "charger_capex_cny": site["charger_capex_cny"],
            }
        )
    _write_csv(
        out_dir / "sites.csv",
        site_rows,
        [
            "site",
            "label",
            "vehicles",
            "power_mw",
            "energy_mwh",
            "transformer_mva",
            "reverse_limit_mw",
            "tested_mw",
            "duration_h",
            "limited_by",
            "charger_capex_cny",
        ],
    )

    monthly_fields = [
        "month",
        "days",
        "operating_days",
        "peak_hours",
        "valley_hours",
        "arb_declared_mw",
        "arb_effective_mw",
        "arb_mwh",
        "arb_revenue_cny",
        "arb_charge_cost_cny",
        "arb_degradation_cny",
        "arb_net_cny",
        "dr_mwh",
        "dr_revenue_cny",
        "dr_penalty_cny",
        "dr_net_cny",
        "reserve_revenue_cny",
        "fixed_cost_cny",
        "owner_benefit_cny",
        "vpp_net_cny",
        "total_benefit_cny",
    ]
    _write_csv(out_dir / "monthly.csv", selected["monthly"], monthly_fields)

    revenue_rows = [
        {"item": "套利收入", "value_cny": selected["arb_revenue_cny"], "basis": "放电量 × 放电价"},
        {"item": "套利充电成本", "value_cny": -selected["arb_charge_cost_cny"], "basis": "放电量 ÷ 效率 × 谷价"},
        {"item": "电池退化", "value_cny": -selected["arb_degradation_cny"], "basis": "放电量 × 退化单价"},
        {"item": "DR 收入", "value_cny": selected["dr_revenue_cny"], "basis": "实际响应电量 × DR 单价"},
        {"item": "DR 考核", "value_cny": -selected["dr_penalty_cny"], "basis": "超容差短供 × DR 单价 × 1.2"},
        {"item": "备用收入", "value_cny": selected["reserve_revenue_cny"], "basis": "备用 MW × 元/kW·月"},
        {"item": "固定成本", "value_cny": -selected["fixed_cost_cny"], "basis": "桩年化 + 安装 + 运维 + 平台 + 计量"},
        {"item": "车主收益", "value_cny": selected["owner_benefit_cny"], "basis": "套利 50% / DR 60% / 备用 30% 分成"},
        {"item": "VPP 净收益", "value_cny": selected["vpp_net_cny"], "basis": "分成后毛利 − 固定成本"},
        {"item": "总盘", "value_cny": selected["total_benefit_cny"], "basis": "车主 + VPP"},
    ]
    _write_csv(out_dir / "revenue.csv", revenue_rows, ["item", "value_cny", "basis"])

    _write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        [
            "case",
            "change",
            "vpp_net_cny",
            "delta_vs_base_cny",
            "owner_benefit_cny",
            "total_benefit_cny",
            "arb_net_cny",
            "dr_net_cny",
            "dr_penalty_cny",
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
        _review(config, market, results, selected, best_total, sensitivity, thresholds),
        encoding="utf-8",
    )

    print(f"输出目录: {out_dir}")
    print(
        f"选中策略: {selected['label']}；VPP 净收益 {selected['vpp_net_cny'] / 1e4:,.2f} 万元；"
        f"车主 {selected['owner_benefit_cny'] / 1e4:,.2f} 万元；"
        f"总盘 {selected['total_benefit_cny'] / 1e4:,.2f} 万元"
    )
    print(
        f"总盘最优: {best_total['label']}（{best_total['total_benefit_cny'] / 1e4:,.2f} 万元）；"
        f"VPP 最优与总盘最优{'不一致' if selected['strategy'] != best_total['strategy'] else '一致'}"
    )
    print(
        f"套利 {selected['arb_mw']:.2f} MW（有效 {selected['arb_effective_mw']:.2f} MW）、"
        f"{selected['arb_mwh']:,.0f} MWh；DR {selected['dr_mw']:.2f} MW、"
        f"{selected['dr_mwh']:,.0f} MWh；备用 {selected['reserve_mw']:.2f} MW"
    )
    print(
        "VPP 盈亏平衡: 放电价 "
        + (
            f"{thresholds['vpp_breakeven_v2g_multiplier']:.2f} 倍"
            if thresholds["vpp_breakeven_v2g_multiplier"]
            else "未触及"
        )
        + "；运营天数 "
        + (
            f"{thresholds['vpp_breakeven_operating_days']:.0f} 天"
            if thresholds["vpp_breakeven_operating_days"]
            else "未触及"
        )
    )
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    print(f"指纹: {fingerprint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
