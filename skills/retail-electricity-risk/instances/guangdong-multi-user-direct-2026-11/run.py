#!/usr/bin/env python3
"""Guangdong multi-user green direct-connection instance runner.

The instance is a configuration package, not a forecast. All demo data are
grade-D synthetic and correspond to no real park, user or project.

Commands:
    python run.py --check-config
    python run.py --demo
    python run.py --profile data/profile_demo.csv --out out/run
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULE_BLOCKS = ("direct_connection", "tariff", "market", "cost")
ALLOCATION_KEYS = ("energy", "capacity", "contract", "two_part")
KEY_LABELS = {
    "energy": "按用电量",
    "capacity": "按最大需量",
    "contract": "按合同份额",
    "two_part": "两部制（容量+电量）",
}
GRADE_RE = re.compile(r"^[ABCD](/[ABCD])*$")


class ConfigError(ValueError):
    """The instance configuration is invalid."""


class InputError(ValueError):
    """A monthly profile file is invalid."""


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _need(block, key, where):
    if not isinstance(block, dict) or key not in block or block[key] in (None, ""):
        raise ConfigError(f"{where}.{key} 缺失")
    return block[key]


def _text(block, key, where):
    value = _need(block, key, where)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}.{key} 必须是非空字符串")
    return value.strip()


def _number(block, key, where, low=None, high=None):
    value = _need(block, key, where)
    if not _is_number(value):
        raise ConfigError(f"{where}.{key} 必须是数字")
    value = float(value)
    if low is not None and value < low:
        raise ConfigError(f"{where}.{key} 不能小于 {low}")
    if high is not None and value > high:
        raise ConfigError(f"{where}.{key} 不能大于 {high}")
    return value


def _grade(block, where):
    value = _text(block, "grade", where)
    if not GRADE_RE.match(value):
        raise ConfigError(f"{where}.grade 必须是 A/B/C/D 或其组合")
    return value


def _rule_block(rules, name, warnings=None):
    block = rules.get(name)
    if not isinstance(block, dict):
        raise ConfigError(f"rules.{name} 缺失")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    return block, grade, source


def load_config(path):
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            config = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"找不到实例文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"实例文件不是合法 JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError("实例配置必须是 JSON 对象")
    return config


def validate_config(config):
    """Validate all blocks; return (sources, warnings)."""
    warnings = []
    sources = []

    meta = config.get("meta")
    if not isinstance(meta, dict):
        raise ConfigError("缺少 meta 块")
    for key in ("instance_id", "province", "market", "entity_type",
                "rule_version", "data_cutoff", "grade", "scope",
                "units", "disclaimer"):
        _need(meta, key, "meta")
    _grade(meta, "meta")
    units = _need(meta, "units", "meta")
    if not isinstance(units, dict):
        raise ConfigError("meta.units 必须是对象")
    for key in ("power", "energy", "price", "conversion"):
        _need(units, key, "meta.units")
    if str(units.get("price", "")).replace(" ", "").upper() != "CNY/MWH":
        raise ConfigError("meta.units.price 必须是 CNY/MWh")
    if str(units.get("energy", "")).replace(" ", "").upper() != "MWH":
        raise ConfigError("meta.units.energy 必须是 MWh")

    rules = config.get("rules")
    if not isinstance(rules, dict):
        raise ConfigError("缺少 rules 块")
    blocks = {}
    for name in RULE_BLOCKS:
        block, grade, source = _rule_block(rules, name)
        blocks[name] = block
        sources.append({"block": f"rules.{name}", "grade": grade, "source": source})

    dc = blocks["direct_connection"]
    for key in ("self_use_min_ratio_generation", "self_use_min_ratio_consumption",
                "feed_in_max_ratio_generation"):
        _number(dc, key, "rules.direct_connection", low=0.0, high=1.0)
    min_users = _number(dc, "min_users", "rules.direct_connection", low=2)
    if int(min_users) != min_users:
        raise ConfigError("rules.direct_connection.min_users 必须是整数")
    _text(dc, "user_scope", "rules.direct_connection")
    allocation_basis = _text(dc, "allocation_basis", "rules.direct_connection")
    if allocation_basis not in ("contract_share", "consumption_share"):
        raise ConfigError("rules.direct_connection.allocation_basis 只支持 contract_share 或 consumption_share")

    tariff = blocks["tariff"]
    for key in ("capacity_price_cny_per_kva_month", "conversion_energy_price_cny_per_mwh",
                "conversion_hours_per_month", "access_capacity_mva",
                "system_operation_cny_per_mwh", "loss_cny_per_mwh",
                "government_fund_cny_per_mwh", "baseline_all_in_cny_per_mwh"):
        _number(tariff, key, "rules.tariff", low=0.0)
    _number(tariff, "provincial_average_load_rate", "rules.tariff", low=0.0, high=1.0)
    if _number(tariff, "access_capacity_mva", "rules.tariff", low=0.0) <= 0.0:
        raise ConfigError("rules.tariff.access_capacity_mva 必须大于 0")
    if _number(tariff, "baseline_all_in_cny_per_mwh", "rules.tariff", low=0.0) <= 0.0:
        raise ConfigError("rules.tariff.baseline_all_in_cny_per_mwh 必须大于 0")

    market = blocks["market"]
    _number(market, "feed_in_price_cny_per_mwh", "rules.market", low=0.0)
    _number(market, "green_certificate_cny_per_mwh", "rules.market", low=0.0)

    cost = blocks["cost"]
    for key in ("wind_mw", "wind_hours", "pv_mw", "pv_hours",
                "generation_lcoe_cny_per_mwh", "storage_power_mw",
                "storage_energy_mwh", "storage_annual_cost_cny",
                "line_opex_cny_per_mwh"):
        _number(cost, key, "rules.cost", low=0.0)
    if _number(cost, "generation_lcoe_cny_per_mwh", "rules.cost", low=0.0) <= 0.0:
        raise ConfigError("rules.cost.generation_lcoe_cny_per_mwh 必须大于 0")

    project = config.get("project")
    if not isinstance(project, dict):
        raise ConfigError("缺少 project 块")
    _text(project, "name", "project")
    max_demand = _number(project, "max_demand_mw", "project", low=0.0)
    if max_demand <= 0.0:
        raise ConfigError("project.max_demand_mw 必须大于 0")
    users = project.get("users")
    if not isinstance(users, list) or len(users) < 2:
        raise ConfigError("project.users 必须是至少 2 个用户的数组")
    seen_ids = set()
    seen_columns = set()
    share_sum = 0.0
    demand_sum = 0.0
    for index, user in enumerate(users):
        where = f"project.users[{index}]"
        if not isinstance(user, dict):
            raise ConfigError(f"{where} 必须是对象")
        user_id = _text(user, "id", where)
        if user_id in seen_ids:
            raise ConfigError(f"{where}.id 重复: {user_id}")
        seen_ids.add(user_id)
        _text(user, "name", where)
        _text(user, "type", where)
        column = _text(user, "column", where)
        if column in seen_columns:
            raise ConfigError(f"{where}.column 重复: {column}")
        seen_columns.add(column)
        _number(user, "annual_consumption_mwh", where, low=0.0)
        if _number(user, "annual_consumption_mwh", where, low=0.0) <= 0.0:
            raise ConfigError(f"{where}.annual_consumption_mwh 必须大于 0")
        demand = _number(user, "max_demand_mw", where, low=0.0)
        if demand <= 0.0:
            raise ConfigError(f"{where}.max_demand_mw 必须大于 0")
        share = _number(user, "contract_share", where, low=0.0, high=1.0)
        share_sum += share
        demand_sum += demand
    if abs(share_sum - 1.0) > 1e-6:
        raise ConfigError(f"project.users 合同份额之和必须为 1，当前 {share_sum:.6f}")
    if len(users) < int(min_users):
        raise ConfigError(f"project.users 少于 rules.direct_connection.min_users={int(min_users)}")
    if max_demand < max(float(user["max_demand_mw"]) for user in users):
        raise ConfigError("project.max_demand_mw 不能小于任一用户的最大需量")
    if demand_sum > max_demand * 1.5 + 1e-9:
        warnings.append("各用户最大需量之和明显高于园区最大负荷，容量分摊可能高估同时率")

    policy = config.get("policy")
    if not isinstance(policy, dict):
        raise ConfigError("缺少 policy 块")
    _text(policy, "profile_id", "policy")
    keys = policy.get("allocation_keys")
    if not isinstance(keys, list) or not keys:
        raise ConfigError("policy.allocation_keys 必须是非空数组")
    for key in keys:
        if key not in ALLOCATION_KEYS:
            raise ConfigError(f"policy.allocation_keys 含未知口径: {key}")
    primary = _text(policy, "primary_allocation_key", "policy")
    if primary not in keys:
        raise ConfigError("policy.primary_allocation_key 必须在 allocation_keys 中")
    _text(policy, "decision_rule", "policy")
    bounds = policy.get("critical_lcoe_bounds_cny_per_mwh")
    if not isinstance(bounds, list) or len(bounds) != 2 or not all(_is_number(v) for v in bounds):
        raise ConfigError("policy.critical_lcoe_bounds_cny_per_mwh 必须是两个数字")
    if float(bounds[0]) >= float(bounds[1]):
        raise ConfigError("policy.critical_lcoe_bounds_cny_per_mwh 下限必须小于上限")
    lcoe_values = policy.get("sensitivity_lcoe_values_cny_per_mwh")
    if not isinstance(lcoe_values, list) or not lcoe_values:
        raise ConfigError("policy.sensitivity_lcoe_values_cny_per_mwh 必须是非空数组")
    for value in lcoe_values:
        if not _is_number(value):
            raise ConfigError("policy.sensitivity_lcoe_values_cny_per_mwh 必须是数字数组")

    data_contract = config.get("data_contract")
    if not isinstance(data_contract, dict):
        raise ConfigError("缺少 data_contract 块")
    profile = data_contract.get("profile")
    if not isinstance(profile, dict):
        raise ConfigError("data_contract.profile 缺失")
    _text(profile, "path", "data_contract.profile")
    fields = profile.get("fields")
    required = ["month", "generation_mwh", "feed_in_price_cny_per_mwh"]
    if not isinstance(fields, list) or any(field not in fields for field in required):
        raise ConfigError("data_contract.profile.fields 必须包含 month/generation_mwh/feed_in_price_cny_per_mwh")
    for user in users:
        if user["column"] not in fields:
            raise ConfigError(f"data_contract.profile.fields 缺少用户列 {user['column']}")

    return sources, warnings


def load_profile(path, config):
    profile_path = Path(path)
    try:
        with profile_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise InputError("月度曲线缺少表头")
            rows = list(reader)
    except FileNotFoundError as exc:
        raise InputError(f"找不到月度曲线: {path}") from exc

    users = config["project"]["users"]
    required = ["month", "generation_mwh", "feed_in_price_cny_per_mwh"] + [u["column"] for u in users]
    missing = [field for field in required if field not in reader.fieldnames]
    if missing:
        raise InputError(f"月度曲线缺少字段: {', '.join(missing)}")
    if len(rows) != 12:
        raise InputError(f"月度曲线必须是 12 个月，当前 {len(rows)} 行")

    parsed = []
    months = set()
    years = set()
    for index, row in enumerate(rows, start=2):
        month = str(row["month"]).strip()
        if not re.match(r"^\d{4}-\d{2}$", month):
            raise InputError(f"第 {index} 行 month 必须是 YYYY-MM")
        if month in months:
            raise InputError(f"第 {index} 行 month 重复: {month}")
        months.add(month)
        years.add(month[:4])
        if month[5:7] not in {f"{m:02d}" for m in range(1, 13)}:
            raise InputError(f"第 {index} 行 month 月份非法: {month}")
        try:
            generation = float(row["generation_mwh"])
            feed_in_price = float(row["feed_in_price_cny_per_mwh"])
        except (TypeError, ValueError) as exc:
            raise InputError(f"第 {index} 行电量或电价不是数字") from exc
        if generation < 0.0 or feed_in_price < 0.0:
            raise InputError(f"第 {index} 行电量与电价不能为负")
        user_values = {}
        for user in users:
            try:
                value = float(row[user["column"]])
            except (TypeError, ValueError) as exc:
                raise InputError(f"第 {index} 行 {user['column']} 不是数字") from exc
            if value < 0.0:
                raise InputError(f"第 {index} 行 {user['column']} 不能为负")
            user_values[user["id"]] = value
        parsed.append({
            "month": month,
            "generation_mwh": generation,
            "feed_in_price_cny_per_mwh": feed_in_price,
            "users": user_values,
        })

    if len(years) != 1:
        raise InputError("月度曲线必须属于同一年")
    parsed.sort(key=lambda row: row["month"])
    expected_months = [f"{sorted(years)[0]}-{m:02d}" for m in range(1, 13)]
    if [row["month"] for row in parsed] != expected_months:
        raise InputError("月度曲线必须覆盖 1-12 月且按月份升序")

    for user in users:
        actual = sum(row["users"][user["id"]] for row in parsed)
        declared = float(user["annual_consumption_mwh"])
        tolerance = max(1.0, declared * 0.001)
        if abs(actual - declared) > tolerance:
            raise InputError(
                f"{user['name']} 年用电量 {actual:,.0f} MWh 与配置 {declared:,.0f} MWh 不一致"
            )

    generation_total = sum(row["generation_mwh"] for row in parsed)
    expected_generation = (
        float(config["rules"]["cost"]["wind_mw"]) * float(config["rules"]["cost"]["wind_hours"])
        + float(config["rules"]["cost"]["pv_mw"]) * float(config["rules"]["cost"]["pv_hours"])
    )
    if expected_generation > 0.0 and abs(generation_total - expected_generation) / expected_generation > 0.10:
        # A warning is enough here: real monthly data may differ from the annual P50 estimate.
        pass
    return parsed, generation_total, expected_generation


def _project_month(generation, consumption, feed_in_cap):
    if generation >= consumption:
        self_use = consumption
        surplus = generation - consumption
        export = min(surplus, feed_in_cap * generation)
        curtail = surplus - export
        grid_import = 0.0
    else:
        self_use = generation
        surplus = 0.0
        export = 0.0
        curtail = 0.0
        grid_import = consumption - generation
    return {
        "generation_mwh": generation,
        "consumption_mwh": consumption,
        "self_use_mwh": self_use,
        "surplus_mwh": surplus,
        "export_mwh": export,
        "curtail_mwh": curtail,
        "import_mwh": grid_import,
    }


def _user_month(generation, user_consumption, users, export, curtail):
    allocated = {user["id"]: generation * float(user["contract_share"]) for user in users}
    self_use = {}
    surplus = {}
    deficit = {}
    for user in users:
        user_id = user["id"]
        consumption = user_consumption[user_id]
        self_use[user_id] = min(allocated[user_id], consumption)
        surplus[user_id] = max(allocated[user_id] - consumption, 0.0)
        deficit[user_id] = max(consumption - allocated[user_id], 0.0)
    total_surplus = sum(surplus.values())
    total_deficit = sum(deficit.values())
    internal_transfer = min(total_surplus, total_deficit)
    result = {}
    for user in users:
        user_id = user["id"]
        if total_surplus > 0.0:
            internal_sell = surplus[user_id] * internal_transfer / total_surplus
            export_share = surplus[user_id] * export / total_surplus
            curtail_share = surplus[user_id] * curtail / total_surplus
        else:
            internal_sell = 0.0
            export_share = 0.0
            curtail_share = 0.0
        if total_deficit > 0.0:
            internal_buy = deficit[user_id] * internal_transfer / total_deficit
        else:
            internal_buy = 0.0
        result[user_id] = {
            "allocated_mwh": allocated[user_id],
            "self_use_mwh": self_use[user_id],
            "surplus_mwh": surplus[user_id],
            "deficit_mwh": deficit[user_id],
            "internal_sell_mwh": internal_sell,
            "internal_buy_mwh": internal_buy,
            "export_mwh": export_share,
            "curtail_mwh": curtail_share,
            "import_mwh": deficit[user_id] - internal_buy,
        }
    return result, internal_transfer


def _shares(config, totals):
    users = config["project"]["users"]
    consumption = {u["id"]: totals["users"][u["id"]]["consumption_mwh"] for u in users}
    demand = {u["id"]: float(u["max_demand_mw"]) for u in users}
    contract = {u["id"]: float(u["contract_share"]) for u in users}
    consumption_total = sum(consumption.values())
    demand_total = sum(demand.values())
    return {
        "energy": {user_id: value / consumption_total for user_id, value in consumption.items()},
        "capacity": {user_id: value / demand_total for user_id, value in demand.items()},
        "contract": contract,
    }


def _economics(config, totals, policy):
    rules = config["rules"]
    cost = rules["cost"]
    tariff = rules["tariff"]
    market = rules["market"]
    lcoe = float(cost["generation_lcoe_cny_per_mwh"])
    generation = totals["generation_mwh"]
    consumption = totals["consumption_mwh"]
    self_use = totals["self_use_mwh"]
    export = totals["export_mwh"]
    grid_import = totals["import_mwh"]
    storage_cost = float(cost["storage_annual_cost_cny"])
    line_opex = float(cost["line_opex_cny_per_mwh"]) * (self_use + export)
    capacity_charge = (
        float(tariff["capacity_price_cny_per_kva_month"])
        * float(tariff["access_capacity_mva"]) * 1000.0 * 12.0
    )
    conversion_mwh = (
        float(tariff["access_capacity_mva"]) * 1000.0
        * float(tariff["conversion_hours_per_month"])
        * float(tariff["provincial_average_load_rate"]) * 12.0 / 1000.0
    )
    conversion_charge = float(tariff["conversion_energy_price_cny_per_mwh"]) * conversion_mwh
    system_operation = float(tariff["system_operation_cny_per_mwh"]) * grid_import
    loss_cost = float(tariff["loss_cny_per_mwh"]) * grid_import
    government_fund = float(tariff["government_fund_cny_per_mwh"]) * consumption
    generation_cost = lcoe * generation
    feed_in_revenue = totals["feed_in_revenue_cny"]
    green_revenue = float(market["green_certificate_cny_per_mwh"]) * (self_use + export)
    net_cost = (
        generation_cost + storage_cost + line_opex + capacity_charge + conversion_charge
        + system_operation + loss_cost + government_fund - feed_in_revenue - green_revenue
    )
    baseline_cost = float(tariff["baseline_all_in_cny_per_mwh"]) * consumption
    unit_cost = net_cost / consumption if consumption else 0.0
    baseline_price = float(tariff["baseline_all_in_cny_per_mwh"])
    return {
        "lcoe_cny_per_mwh": lcoe,
        "generation_cost_cny": generation_cost,
        "storage_cost_cny": storage_cost,
        "line_opex_cny": line_opex,
        "capacity_charge_cny": capacity_charge,
        "conversion_charge_cny": conversion_charge,
        "transmission_total_cny": capacity_charge + conversion_charge,
        "conversion_mwh": conversion_mwh,
        "system_operation_cny": system_operation,
        "loss_cost_cny": loss_cost,
        "government_fund_cny": government_fund,
        "feed_in_revenue_cny": feed_in_revenue,
        "green_revenue_cny": green_revenue,
        "net_cost_cny": net_cost,
        "baseline_cost_cny": baseline_cost,
        "unit_cost_cny_per_mwh": unit_cost,
        "baseline_price_cny_per_mwh": baseline_price,
        "saving_cny": baseline_cost - net_cost,
        "saving_cny_per_mwh": baseline_price - unit_cost,
    }


def compute(config, profile, overrides=None):
    overrides = overrides or {}
    users = config["project"]["users"]
    rules = config["rules"]
    dc = rules["direct_connection"]
    tariff = rules["tariff"]
    market = rules["market"]
    cost = rules["cost"]

    generation_multiplier = float(overrides.get("generation_multiplier", 1.0))
    consumption_multiplier = float(overrides.get("consumption_multiplier", 1.0))
    user_multipliers = overrides.get("user_multipliers", {})
    contract_shares = overrides.get("contract_shares")
    feed_in_price = overrides.get("feed_in_price_cny_per_mwh")
    access_capacity = float(overrides.get("access_capacity_mva", tariff["access_capacity_mva"]))
    storage_cost = float(overrides.get("storage_annual_cost_cny", cost["storage_annual_cost_cny"]))
    lcoe = float(overrides.get("generation_lcoe_cny_per_mwh", cost["generation_lcoe_cny_per_mwh"]))

    effective_users = copy.deepcopy(users)
    if contract_shares is not None:
        if len(contract_shares) != len(effective_users):
            raise ConfigError("contract_shares 长度必须与用户数一致")
        share_sum = sum(float(value) for value in contract_shares)
        if abs(share_sum - 1.0) > 1e-6:
            raise ConfigError("contract_shares 之和必须为 1")
        for user, share in zip(effective_users, contract_shares):
            user["contract_share"] = float(share)
    effective_config = copy.deepcopy(config)
    effective_config["project"]["users"] = effective_users
    effective_config["rules"]["tariff"]["access_capacity_mva"] = access_capacity
    effective_config["rules"]["cost"]["storage_annual_cost_cny"] = storage_cost
    effective_config["rules"]["cost"]["generation_lcoe_cny_per_mwh"] = lcoe

    monthly = []
    user_totals = {
        user["id"]: {
            "name": user["name"],
            "type": user["type"],
            "consumption_mwh": 0.0,
            "allocated_mwh": 0.0,
            "self_use_mwh": 0.0,
            "surplus_mwh": 0.0,
            "deficit_mwh": 0.0,
            "internal_sell_mwh": 0.0,
            "internal_buy_mwh": 0.0,
            "export_mwh": 0.0,
            "curtail_mwh": 0.0,
            "import_mwh": 0.0,
        }
        for user in effective_users
    }
    project_totals = {
        "generation_mwh": 0.0,
        "consumption_mwh": 0.0,
        "self_use_mwh": 0.0,
        "export_mwh": 0.0,
        "curtail_mwh": 0.0,
        "import_mwh": 0.0,
        "internal_transfer_mwh": 0.0,
        "feed_in_revenue_cny": 0.0,
    }

    for row in profile:
        generation = row["generation_mwh"] * generation_multiplier
        user_consumption = {}
        for user in effective_users:
            multiplier = float(user_multipliers.get(user["id"], 1.0)) * consumption_multiplier
            user_consumption[user["id"]] = row["users"][user["id"]] * multiplier
        consumption = sum(user_consumption.values())
        month_project = _project_month(
            generation, consumption, float(dc["feed_in_max_ratio_generation"])
        )
        month_users, internal_transfer = _user_month(
            generation, user_consumption, effective_users,
            month_project["export_mwh"], month_project["curtail_mwh"]
        )
        price = float(feed_in_price) if feed_in_price is not None else row["feed_in_price_cny_per_mwh"]
        feed_in_revenue = month_project["export_mwh"] * price
        month_project["feed_in_price_cny_per_mwh"] = price
        month_project["feed_in_revenue_cny"] = feed_in_revenue
        month_project["internal_transfer_mwh"] = internal_transfer
        month_project["month"] = row["month"]
        month_project["users"] = month_users
        monthly.append(month_project)
        for key in ("generation_mwh", "consumption_mwh", "self_use_mwh",
                    "export_mwh", "curtail_mwh", "import_mwh"):
            project_totals[key] += month_project[key]
        project_totals["internal_transfer_mwh"] += internal_transfer
        project_totals["feed_in_revenue_cny"] += feed_in_revenue
        for user in effective_users:
            user_id = user["id"]
            user_totals[user_id]["consumption_mwh"] += user_consumption[user_id]
            for key in ("allocated_mwh", "self_use_mwh", "surplus_mwh", "deficit_mwh",
                        "internal_sell_mwh", "internal_buy_mwh", "export_mwh",
                        "curtail_mwh", "import_mwh"):
                user_totals[user_id][key] += month_users[user_id][key]

    for user_id, values in user_totals.items():
        values["green_supply_mwh"] = values["consumption_mwh"] - values["import_mwh"]
        values["green_coverage_ratio"] = (
            values["green_supply_mwh"] / values["consumption_mwh"]
            if values["consumption_mwh"] else 0.0
        )
        values["self_use_ratio"] = (
            values["self_use_mwh"] / values["allocated_mwh"]
            if values["allocated_mwh"] else 0.0
        )
        values["import_ratio"] = (
            values["import_mwh"] / values["consumption_mwh"]
            if values["consumption_mwh"] else 0.0
        )

    economics = _economics(effective_config, project_totals, config["policy"])
    shares = _shares(effective_config, {"users": user_totals})
    allocation = {}
    capacity_cost = economics["transmission_total_cny"]
    other_cost = economics["net_cost_cny"] - capacity_cost
    for key in config["policy"]["allocation_keys"]:
        rows = {}
        for user in effective_users:
            user_id = user["id"]
            if key == "energy":
                share = shares["energy"][user_id]
                cost_value = economics["net_cost_cny"] * share
            elif key == "capacity":
                share = shares["capacity"][user_id]
                cost_value = economics["net_cost_cny"] * share
            elif key == "contract":
                share = shares["contract"][user_id]
                cost_value = economics["net_cost_cny"] * share
            else:
                share = shares["capacity"][user_id]
                cost_value = (
                    capacity_cost * shares["capacity"][user_id]
                    + other_cost * shares["energy"][user_id]
                )
            consumption = user_totals[user_id]["consumption_mwh"]
            unit = cost_value / consumption if consumption else 0.0
            rows[user_id] = {
                "cost_cny": cost_value,
                "unit_cost_cny_per_mwh": unit,
                "saving_cny": economics["baseline_price_cny_per_mwh"] * consumption - cost_value,
                "saving_cny_per_mwh": economics["baseline_price_cny_per_mwh"] - unit,
            }
        unit_values = [row["unit_cost_cny_per_mwh"] for row in rows.values()]
        spread = max(unit_values) - min(unit_values)
        if spread < 1e-9:
            spread = 0.0
        allocation[key] = {
            "users": rows,
            "spread_cny_per_mwh": spread,
            "lowest_user": min(rows, key=lambda user_id: rows[user_id]["unit_cost_cny_per_mwh"]),
            "highest_user": max(rows, key=lambda user_id: rows[user_id]["unit_cost_cny_per_mwh"]),
        }

    self_use_ratio_generation = (
        project_totals["self_use_mwh"] / project_totals["generation_mwh"]
        if project_totals["generation_mwh"] else 0.0
    )
    self_use_ratio_consumption = (
        project_totals["self_use_mwh"] / project_totals["consumption_mwh"]
        if project_totals["consumption_mwh"] else 0.0
    )
    feed_in_ratio_generation = (
        project_totals["export_mwh"] / project_totals["generation_mwh"]
        if project_totals["generation_mwh"] else 0.0
    )
    import_ratio_consumption = (
        project_totals["import_mwh"] / project_totals["consumption_mwh"]
        if project_totals["consumption_mwh"] else 0.0
    )
    checks = {
        "self_use_generation": {
            "label": "自用/可用发电量",
            "value": self_use_ratio_generation,
            "threshold": float(dc["self_use_min_ratio_generation"]),
            "operator": ">=",
            "pass": self_use_ratio_generation + 1e-12 >= float(dc["self_use_min_ratio_generation"]),
        },
        "self_use_consumption": {
            "label": "自用/总用电量",
            "value": self_use_ratio_consumption,
            "threshold": float(dc["self_use_min_ratio_consumption"]),
            "operator": ">=",
            "pass": self_use_ratio_consumption + 1e-12 >= float(dc["self_use_min_ratio_consumption"]),
        },
        "feed_in_generation": {
            "label": "上网/可用发电量",
            "value": feed_in_ratio_generation,
            "threshold": float(dc["feed_in_max_ratio_generation"]),
            "operator": "<=",
            "pass": feed_in_ratio_generation <= float(dc["feed_in_max_ratio_generation"]) + 1e-12,
        },
        "users": {
            "label": "用户数",
            "value": float(len(effective_users)),
            "threshold": float(dc["min_users"]),
            "operator": ">=",
            "pass": len(effective_users) >= int(dc["min_users"]),
        },
    }
    compliance = {
        "checks": checks,
        "pass": all(check["pass"] for check in checks.values()),
        "self_use_ratio_generation": self_use_ratio_generation,
        "self_use_ratio_consumption": self_use_ratio_consumption,
        "feed_in_ratio_generation": feed_in_ratio_generation,
        "import_ratio_consumption": import_ratio_consumption,
    }

    return {
        "config": {
            "profile_id": config["policy"]["profile_id"],
            "users": effective_users,
            "access_capacity_mva": access_capacity,
            "feed_in_price_cny_per_mwh": (
                float(feed_in_price) if feed_in_price is not None
                else float(market["feed_in_price_cny_per_mwh"])
            ),
            "lcoe_cny_per_mwh": lcoe,
            "storage_annual_cost_cny": storage_cost,
            "generation_multiplier": generation_multiplier,
            "consumption_multiplier": consumption_multiplier,
            "user_multipliers": dict(user_multipliers),
        },
        "monthly": monthly,
        "users": user_totals,
        "totals": project_totals,
        "economics": economics,
        "allocation": allocation,
        "compliance": compliance,
    }


def critical_lcoe(config, profile, result):
    bounds = config["policy"]["critical_lcoe_bounds_cny_per_mwh"]
    low, high = float(bounds[0]), float(bounds[1])

    def gap(value):
        trial = compute(config, profile, {"generation_lcoe_cny_per_mwh": value})
        return trial["economics"]["net_cost_cny"] - trial["economics"]["baseline_cost_cny"]

    if gap(low) > 0.0:
        return low, "下限仍高于原模式成本"
    if gap(high) < 0.0:
        return high, "上限仍低于原模式成本"
    for _ in range(80):
        mid = (low + high) / 2.0
        if gap(mid) > 0.0:
            high = mid
        else:
            low = mid
    return (low + high) / 2.0, "ok"


def sensitivity(config, profile, base):
    cases = [
        ("基准", "合同份额 50/30/20，LCOE 220", {}),
        ("LCOE 264", "发电 LCOE +20%", {"generation_lcoe_cny_per_mwh": 264.0}),
        ("LCOE 300", "发电 LCOE 升至 300", {"generation_lcoe_cny_per_mwh": 300.0}),
        ("发电量 −10%", "可用发电量整体下降 10%", {"generation_multiplier": 0.9}),
        ("发电量 +30%", "可用发电量整体上升 30%，校核自用率", {"generation_multiplier": 1.3}),
        ("用电量 +10%", "三个用户用电量同比例上升 10%", {"consumption_multiplier": 1.1}),
        ("用电量 −10%", "三个用户用电量同比例下降 10%", {"consumption_multiplier": 0.9}),
        ("上网电价 200", "上网电价由 250 降至 200", {"feed_in_price_cny_per_mwh": 200.0}),
        ("上网电价 300", "上网电价由 250 升至 300", {"feed_in_price_cny_per_mwh": 300.0}),
        ("接入容量 50 MVA", "接入公共电网容量由 63 降至 50 MVA", {"access_capacity_mva": 50.0}),
        ("储能成本 +20%", "储能年化成本上升 20%", {"storage_annual_cost_cny": float(config["rules"]["cost"]["storage_annual_cost_cny"]) * 1.2}),
        ("合同份额 40/40/20", "合同份额由 50/30/20 改为 40/40/20", {"contract_shares": [0.40, 0.40, 0.20]}),
        ("用户 C +20%", "冷链仓储用电量上升 20%", {"user_multipliers": {"cold": 1.2}}),
    ]
    primary = config["policy"]["primary_allocation_key"]
    rows = []
    for name, change, overrides in cases:
        trial = compute(config, profile, overrides)
        allocation = trial["allocation"][primary]
        min_green = min(user["green_coverage_ratio"] for user in trial["users"].values())
        rows.append({
            "case": name,
            "change": change,
            "unit_cost_cny_per_mwh": trial["economics"]["unit_cost_cny_per_mwh"],
            "saving_wan_cny": trial["economics"]["saving_cny"] / 1e4,
            "self_use_ratio_generation": trial["compliance"]["self_use_ratio_generation"],
            "self_use_ratio_consumption": trial["compliance"]["self_use_ratio_consumption"],
            "feed_in_ratio_generation": trial["compliance"]["feed_in_ratio_generation"],
            "compliance": "通过" if trial["compliance"]["pass"] else "不通过",
            "internal_transfer_mwh": trial["totals"]["internal_transfer_mwh"],
            "min_green_coverage": min_green,
            "spread_cny_per_mwh": allocation["spread_cny_per_mwh"],
            "highest_unit_cost_cny_per_mwh": allocation["users"][allocation["highest_user"]]["unit_cost_cny_per_mwh"],
            "lowest_unit_cost_cny_per_mwh": allocation["users"][allocation["lowest_user"]]["unit_cost_cny_per_mwh"],
            "delta_vs_base_unit": trial["economics"]["unit_cost_cny_per_mwh"] - base["economics"]["unit_cost_cny_per_mwh"],
        })
    return rows


def _fmt(value, digits=2):
    return f"{value:,.{digits}f}"


def _fmt_wan(value):
    return f"{value / 1e4:,.2f}"


def _fmt_pct(value):
    return f"{value * 100:.2f}%"


def _write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_outputs(out_dir, config, profile, result, sensitivity_rows, critical):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    users = config["project"]["users"]

    monthly_rows = []
    for row in result["monthly"]:
        monthly_rows.append({
            "month": row["month"],
            "generation_mwh": row["generation_mwh"],
            "consumption_mwh": row["consumption_mwh"],
            "self_use_mwh": row["self_use_mwh"],
            "export_mwh": row["export_mwh"],
            "curtail_mwh": row["curtail_mwh"],
            "import_mwh": row["import_mwh"],
            "internal_transfer_mwh": row["internal_transfer_mwh"],
            "feed_in_price_cny_per_mwh": row["feed_in_price_cny_per_mwh"],
            "feed_in_revenue_cny": row["feed_in_revenue_cny"],
        })
    _write_csv(out_dir / "monthly.csv", monthly_rows, list(monthly_rows[0].keys()))

    user_rows = []
    for user in users:
        values = result["users"][user["id"]]
        user_rows.append({
            "user_id": user["id"],
            "name": user["name"],
            "type": user["type"],
            "contract_share": user["contract_share"],
            "consumption_mwh": values["consumption_mwh"],
            "allocated_mwh": values["allocated_mwh"],
            "self_use_mwh": values["self_use_mwh"],
            "surplus_mwh": values["surplus_mwh"],
            "deficit_mwh": values["deficit_mwh"],
            "internal_sell_mwh": values["internal_sell_mwh"],
            "internal_buy_mwh": values["internal_buy_mwh"],
            "export_mwh": values["export_mwh"],
            "curtail_mwh": values["curtail_mwh"],
            "import_mwh": values["import_mwh"],
            "green_supply_mwh": values["green_supply_mwh"],
            "green_coverage_ratio": values["green_coverage_ratio"],
            "self_use_ratio": values["self_use_ratio"],
            "import_ratio": values["import_ratio"],
        })
    _write_csv(out_dir / "users.csv", user_rows, list(user_rows[0].keys()))

    economics = result["economics"]
    cost_rows = [
        {"item": "发电成本", "value_cny": economics["generation_cost_cny"], "basis": "LCOE × 可用发电量"},
        {"item": "储能年化", "value_cny": economics["storage_cost_cny"], "basis": "50 MW/100 MWh"},
        {"item": "专线运维", "value_cny": economics["line_opex_cny"], "basis": "10 元/MWh ×（自用 + 上网）"},
        {"item": "容需量电费", "value_cny": economics["capacity_charge_cny"], "basis": "30 元/kVA·月 × 63 MVA × 12"},
        {"item": "1192 折算电费", "value_cny": economics["conversion_charge_cny"], "basis": "100 元/MWh × 730 h/月 × 60% × 63 MVA × 12"},
        {"item": "系统运行费", "value_cny": economics["system_operation_cny"], "basis": "68 元/MWh × 下网电量"},
        {"item": "线损", "value_cny": economics["loss_cost_cny"], "basis": "12 元/MWh × 下网电量"},
        {"item": "政府性基金及附加", "value_cny": economics["government_fund_cny"], "basis": "20 元/MWh × 总用电量"},
        {"item": "上网收入（抵减）", "value_cny": -economics["feed_in_revenue_cny"], "basis": "上网电量 × 上网电价"},
        {"item": "绿证收入（抵减）", "value_cny": -economics["green_revenue_cny"], "basis": "6 元/MWh ×（自用 + 上网）"},
        {"item": "净成本", "value_cny": economics["net_cost_cny"], "basis": "成本 − 抵减"},
        {"item": "原模式成本", "value_cny": economics["baseline_cost_cny"], "basis": "675.6 元/MWh × 总用电量"},
    ]
    _write_csv(out_dir / "costs.csv", cost_rows, ["item", "value_cny", "basis"])

    allocation_rows = []
    for key in config["policy"]["allocation_keys"]:
        block = result["allocation"][key]
        for user in users:
            row = block["users"][user["id"]]
            allocation_rows.append({
                "key": key,
                "label": KEY_LABELS.get(key, key),
                "user_id": user["id"],
                "name": user["name"],
                "cost_cny": row["cost_cny"],
                "unit_cost_cny_per_mwh": row["unit_cost_cny_per_mwh"],
                "saving_cny": row["saving_cny"],
                "saving_cny_per_mwh": row["saving_cny_per_mwh"],
                "spread_cny_per_mwh": block["spread_cny_per_mwh"],
            })
    _write_csv(out_dir / "allocation.csv", allocation_rows,
               ["key", "label", "user_id", "name", "cost_cny", "unit_cost_cny_per_mwh",
                "saving_cny", "saving_cny_per_mwh", "spread_cny_per_mwh"])

    _write_csv(out_dir / "sensitivity.csv", sensitivity_rows, list(sensitivity_rows[0].keys()))

    summary = {
        "meta": config["meta"],
        "fingerprint": hashlib.sha1(
            json.dumps(config["policy"], sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12],
        "config": {
            "profile_id": config["policy"]["profile_id"],
            "primary_allocation_key": config["policy"]["primary_allocation_key"],
            "users": result["config"]["users"],
            "access_capacity_mva": result["config"]["access_capacity_mva"],
            "generation_lcoe_cny_per_mwh": result["config"]["lcoe_cny_per_mwh"],
        },
        "totals": result["totals"],
        "compliance": result["compliance"],
        "economics": economics,
        "critical_lcoe_cny_per_mwh": critical[0],
        "critical_lcoe_status": critical[1],
        "allocation": {
            key: {
                "spread_cny_per_mwh": block["spread_cny_per_mwh"],
                "lowest_user": block["lowest_user"],
                "highest_user": block["highest_user"],
                "users": block["users"],
            }
            for key, block in result["allocation"].items()
        },
        "sensitivity": sensitivity_rows,
        "warnings": [],
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    (out_dir / "review.md").write_text(
        build_review(config, result, sensitivity_rows, critical),
        encoding="utf-8",
    )
    return summary


def build_review(config, result, sensitivity_rows, critical):
    meta = config["meta"]
    users = config["project"]["users"]
    totals = result["totals"]
    econ = result["economics"]
    compliance = result["compliance"]
    primary = config["policy"]["primary_allocation_key"]
    allocation = result["allocation"][primary]
    lines = [
        f"# {meta['province']}多用户绿电直连 · 复核表",
        "",
        f"- 实例：`{meta['instance_id']}`（{meta['entity_type']}）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}；全部发用电量、价格与成本为 D 级合成数据",
        "",
        "## 1. 结论",
        "",
        f"基准情景全口径度电成本 **{_fmt(econ['unit_cost_cny_per_mwh'])} 元/MWh**"
        f"（{econ['unit_cost_cny_per_mwh'] / 1000:.4f} 元/kWh），比原模式 "
        f"{_fmt(econ['baseline_price_cny_per_mwh'])} 元/MWh 低 "
        f"**{_fmt(econ['saving_cny_per_mwh'])} 元/MWh**，年省 "
        f"**{_fmt_wan(econ['saving_cny'])} 万元**。",
        "",
        f"60%/35%/20% 三项门槛与用户数要求{'全部通过' if compliance['pass'] else '未全部通过'}："
        f"自用/可用发电量 {_fmt_pct(compliance['self_use_ratio_generation'])}，"
        f"自用/总用电量 {_fmt_pct(compliance['self_use_ratio_consumption'])}，"
        f"上网/可用发电量 {_fmt_pct(compliance['feed_in_ratio_generation'])}。"
        f"临界 LCOE 约 **{_fmt(critical[0])} 元/MWh**，高于此值直连不再优于原模式。",
        "",
        f"主分摊口径为「{KEY_LABELS.get(primary, primary)}」：用户单位成本在 "
        f"{_fmt(allocation['users'][allocation['lowest_user']]['unit_cost_cny_per_mwh'])}–"
        f"{_fmt(allocation['users'][allocation['highest_user']]['unit_cost_cny_per_mwh'])} 元/MWh 之间，"
        f"极差 **{_fmt(allocation['spread_cny_per_mwh'])} 元/MWh**。"
        "容量费按容量分摊、其余成本按电量分摊的两部制口径，通常比单一电量或单一容量口径更接近成本因果。",
        "",
        "## 2. 电量平衡",
        "",
        "| 项目 | 电量（MWh） | 占可用发电量 | 占总用电量 |",
        "|---|---:|---:|---:|",
        f"| 可用发电量 | {_fmt(totals['generation_mwh'], 0)} | 100.00% | — |",
        f"| 总用电量 | {_fmt(totals['consumption_mwh'], 0)} | — | 100.00% |",
        f"| 自用电量 | {_fmt(totals['self_use_mwh'], 0)} | {_fmt_pct(compliance['self_use_ratio_generation'])} | {_fmt_pct(compliance['self_use_ratio_consumption'])} |",
        f"| 上网电量 | {_fmt(totals['export_mwh'], 0)} | {_fmt_pct(compliance['feed_in_ratio_generation'])} | — |",
        f"| 弃电 | {_fmt(totals['curtail_mwh'], 0)} | {_fmt_pct(totals['curtail_mwh'] / totals['generation_mwh'])} | — |",
        f"| 下网电量 | {_fmt(totals['import_mwh'], 0)} | — | {_fmt_pct(compliance['import_ratio_consumption'])} |",
        "",
        f"项目内用户互济电量 {_fmt(totals['internal_transfer_mwh'], 0)} MWh；"
        "上网与弃电按用户盈余比例分摊，下网按用户缺口比例分摊。",
        "",
        "## 3. 合规门槛",
        "",
        "| 门槛 | 本期值 | 要求 | 判定 |",
        "|---|---:|---:|---|",
    ]
    for check in compliance["checks"].values():
        value = check["value"]
        if check["label"] == "用户数":
            value_text = f"{int(value)}"
            threshold_text = f"{int(check['threshold'])}"
        else:
            value_text = _fmt_pct(value)
            threshold_text = _fmt_pct(check["threshold"])
        lines.append(
            f"| {check['label']} | {value_text} | {check['operator']} {threshold_text} | "
            f"{'通过' if check['pass'] else '不通过'} |"
        )
    lines.extend([
        "",
        "## 4. 成本堆叠",
        "",
        "| 科目 | 金额（万元） | 口径 |",
        "|---|---:|---|",
        f"| 发电成本 | {_fmt_wan(econ['generation_cost_cny'])} | LCOE × 可用发电量（弃电也摊成本） |",
        f"| 储能年化 | {_fmt_wan(econ['storage_cost_cny'])} | 50 MW/100 MWh |",
        f"| 专线运维 | {_fmt_wan(econ['line_opex_cny'])} | 自用 + 上网电量 |",
        f"| 容需量电费 | {_fmt_wan(econ['capacity_charge_cny'])} | 30 元/kVA·月 × 63 MVA × 12 |",
        f"| 1192 折算电费 | {_fmt_wan(econ['conversion_charge_cny'])} | 730 h/月 × 60% × 63 MVA × 100 元/MWh |",
        f"| 系统运行费 | {_fmt_wan(econ['system_operation_cny'])} | 仅下网电量 |",
        f"| 线损 | {_fmt_wan(econ['loss_cost_cny'])} | 仅下网电量 |",
        f"| 政府性基金及附加 | {_fmt_wan(econ['government_fund_cny'])} | 总用电量 |",
        f"| 上网收入（抵减） | −{_fmt_wan(econ['feed_in_revenue_cny'])} | 上网电量 × 上网电价 |",
        f"| 绿证收入（抵减） | −{_fmt_wan(econ['green_revenue_cny'])} | 自用 + 上网电量 |",
        f"| **净成本** | **{_fmt_wan(econ['net_cost_cny'])}** | — |",
        f"| 原模式成本 | {_fmt_wan(econ['baseline_cost_cny'])} | 675.6 元/MWh × 总用电量 |",
        "",
        f"直连模式度电成本 **{_fmt(econ['unit_cost_cny_per_mwh'])} 元/MWh**，"
        f"原模式 {_fmt(econ['baseline_price_cny_per_mwh'])} 元/MWh；"
        f"输配电费合计 {_fmt_wan(econ['transmission_total_cny'])} 万元，"
        f"折 {_fmt(econ['transmission_total_cny'] / totals['consumption_mwh'])} 元/MWh。",
        "",
        "## 5. 分用户结果",
        "",
        "| 用户 | 合同份额 | 用电量 | 分配电量 | 自用 | 盈余 | 缺口 | 内部买入 | 内部卖出 | 下网 | 绿电覆盖 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for user in users:
        values = result["users"][user["id"]]
        lines.append(
            f"| {user['name']} | {_fmt_pct(user['contract_share'])} | "
            f"{_fmt(values['consumption_mwh'], 0)} | {_fmt(values['allocated_mwh'], 0)} | "
            f"{_fmt(values['self_use_mwh'], 0)} | {_fmt(values['surplus_mwh'], 0)} | "
            f"{_fmt(values['deficit_mwh'], 0)} | {_fmt(values['internal_buy_mwh'], 0)} | "
            f"{_fmt(values['internal_sell_mwh'], 0)} | {_fmt(values['import_mwh'], 0)} | "
            f"{_fmt_pct(values['green_coverage_ratio'])} |"
        )
    lines.extend([
        "",
        (
            f"合同份额与用电份额刻意错配：{users[0]['name']} 合同份额 "
            f"{_fmt_pct(users[0]['contract_share'])}、年度缺口 "
            f"{_fmt(result['users'][users[0]['id']]['deficit_mwh'], 0)} MWh，主要靠项目内买入；"
            f"{users[1]['name']} 合同份额 {_fmt_pct(users[1]['contract_share'])}、年度盈余 "
            f"{_fmt(result['users'][users[1]['id']]['surplus_mwh'], 0)} MWh，其中内部卖出 "
            f"{_fmt(result['users'][users[1]['id']]['internal_sell_mwh'], 0)} MWh、上网 "
            f"{_fmt(result['users'][users[1]['id']]['export_mwh'], 0)} MWh、弃电 "
            f"{_fmt(result['users'][users[1]['id']]['curtail_mwh'], 0)} MWh；"
            f"{users[2]['name']} 合同份额与用电份额均为 "
            f"{_fmt_pct(users[2]['contract_share'])}，但夏季缺口、冬季盈余并存，年度盈余 "
            f"{_fmt(result['users'][users[2]['id']]['surplus_mwh'], 0)} MWh、缺口 "
            f"{_fmt(result['users'][users[2]['id']]['deficit_mwh'], 0)} MWh。"
            "内部买卖必须约定结算价，否则分摊口径再好也会在成员之间产生争议。"
        ),
        "",
        "## 6. 分摊口径比较",
        "",
        "| 口径 | 数据中心 A | 电子制造 B | 冷链仓储 C | 极差（元/MWh） |",
        "|---|---:|---:|---:|---:|",
    ])
    for key in config["policy"]["allocation_keys"]:
        block = result["allocation"][key]
        values = [block["users"][user["id"]]["unit_cost_cny_per_mwh"] for user in users]
        lines.append(
            f"| {KEY_LABELS.get(key, key)} | " + " | ".join(_fmt(value) for value in values)
            + f" | {_fmt(block['spread_cny_per_mwh'])} |"
        )
    lines.extend([
        "",
        "按用电量分摊时单位成本完全相同，但把容量费转嫁给高电量用户；"
        "按最大需量分摊时冷链仓储 C 因负荷率低而单位成本最高；"
        "按合同份额分摊时电子制造 B 因合同份额高于用电份额而单位成本最高；"
        "两部制把容需量与 1192 折算费按容量分摊、其余成本按电量分摊，是成本因果最接近的口径。",
        "",
        "## 7. 敏感性",
        "",
        "| 情景 | 变化 | 度电成本（元/MWh） | 年省（万元） | 自用/发电 | 上网/发电 | 合规 | 互济电量（MWh） | 最低绿电覆盖 | 主口径极差 |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|",
    ])
    for row in sensitivity_rows:
        lines.append(
            f"| {row['case']} | {row['change']} | {_fmt(row['unit_cost_cny_per_mwh'])} | "
            f"{_fmt(row['saving_wan_cny'])} | {_fmt_pct(row['self_use_ratio_generation'])} | "
            f"{_fmt_pct(row['feed_in_ratio_generation'])} | {row['compliance']} | "
            f"{_fmt(row['internal_transfer_mwh'], 0)} | {_fmt_pct(row['min_green_coverage'])} | "
            f"{_fmt(row['spread_cny_per_mwh'])} |"
        )
    lines.extend([
        "",
        "发电量 +30% 时自用率跌破 60%，是唯一触发合规不通过的情景；"
        "用电量 +10% 会把固定容量费摊薄，度电成本反而下降；"
        "接入容量从 63 MVA 降到 50 MVA，容需量与 1192 折算费同步下降，是最直接的降本项。",
        "",
        "## 8. 口径提醒",
        "",
        "- 60% 的分母是**可用发电量**，不是理论发电量，也不是上网电量；弃电仍要摊发电成本。",
        "- 自用/总用电量的门槛按更严的 35% 校核（2030 年前口径）；不要用 30% 替代后宣称合规。",
        "- 650/688 号与 1192 号的 730 小时是**月度折算小时数**，不是项目年利用小时；省级平均负荷率也不是园区自身负荷率。",
        "- 容需量电费按接入容量与变压器容量计，不随下网电量下降而同比例下降；直连后下网少了，容量费仍在。",
        "- 绿证归属必须在多用户合同中写明；自用电量与上网电量的绿证不能重复声明。",
        "- 本包参数为 D 级合成算例，不对应广东任何真实园区；实际项目须查 650/688 号原文、1192 号、粤发改能源〔2026〕267号与粤发改价格函〔2026〕1848号。",
        "",
        f"风格指纹 `{hashlib.sha1(json.dumps(config['policy'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()[:12]}`；"
        "本复核表由 `run.py` 生成。",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="广东多用户绿电直连实例")
    parser.add_argument("--instance", type=Path, default=HERE / "instance.json")
    parser.add_argument("--profile", type=Path, help="月度发用电 CSV；--demo 时省略")
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--demo", action="store_true", help="使用仓库内合成数据")
    parser.add_argument("--check-config", action="store_true", help="只校验配置与来源表")
    args = parser.parse_args()

    try:
        config = load_config(args.instance)
        sources, warnings = validate_config(config)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    if args.check_config:
        print("配置校验通过")
        print(f"实例: {config['meta']['instance_id']} · {config['meta']['province']} · {config['meta']['market']}")
        print(f"规则版本: {config['meta']['rule_version']}")
        print(f"风格: {config['policy']['profile_id']}")
        print(f"用户数: {len(config['project']['users'])}；合同份额: "
              + " / ".join(f"{user['contract_share']:.0%}" for user in config['project']['users']))
        print(f"接入容量: {config['rules']['tariff']['access_capacity_mva']} MVA；"
              f"原模式全口径电价: {config['rules']['tariff']['baseline_all_in_cny_per_mwh']} 元/MWh")
        print("规则来源:")
        for source in sources:
            print(f"  - {source['block']} [{source['grade']}] {source['source'][:120]}")
        for warning in warnings:
            print(f"警告: {warning}")
        return 0

    profile_path = args.profile
    out_dir = args.out
    if args.demo:
        if profile_path is None:
            profile_path = HERE / "data" / "profile_demo.csv"
        out_dir = args.out if args.out != HERE / "out" else HERE / "out" / "demo"

    if profile_path is None:
        print("必须提供 --profile 或使用 --demo", file=sys.stderr)
        return 2

    try:
        profile, generation_total, expected_generation = load_profile(profile_path, config)
    except InputError as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return 2
    if expected_generation > 0.0 and abs(generation_total - expected_generation) / expected_generation > 0.10:
        warnings.append(
            f"月度发电量合计 {generation_total:,.0f} MWh 偏离配置的 P50 估算 "
            f"{expected_generation:,.0f} MWh 超过 10%"
        )

    try:
        result = compute(config, profile)
        critical = critical_lcoe(config, profile, result)
        sensitivity_rows = sensitivity(config, profile, result)
        summary = write_outputs(out_dir, config, profile, result, sensitivity_rows, critical)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    print(f"输出目录: {Path(out_dir).resolve()}")
    print(f"可用发电量 / 总用电量: {generation_total:,.0f} / {result['totals']['consumption_mwh']:,.0f} MWh")
    print(f"自用 / 上网 / 弃电 / 下网: "
          f"{result['totals']['self_use_mwh']:,.0f} / {result['totals']['export_mwh']:,.0f} / "
          f"{result['totals']['curtail_mwh']:,.0f} / {result['totals']['import_mwh']:,.0f} MWh")
    print(f"度电成本: {result['economics']['unit_cost_cny_per_mwh']:,.2f} 元/MWh；"
          f"原模式: {result['economics']['baseline_price_cny_per_mwh']:,.2f} 元/MWh；"
          f"年省: {result['economics']['saving_cny'] / 1e4:,.2f} 万元")
    print(f"合规: {'通过' if result['compliance']['pass'] else '不通过'}；"
          f"临界 LCOE: {critical[0]:,.2f} 元/MWh")
    print(f"主分摊口径 {config['policy']['primary_allocation_key']} 极差: "
          f"{result['allocation'][config['policy']['primary_allocation_key']]['spread_cny_per_mwh']:,.2f} 元/MWh")
    for warning in warnings:
        print(f"警告: {warning}")
    print(f"指纹: {summary['fingerprint']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
