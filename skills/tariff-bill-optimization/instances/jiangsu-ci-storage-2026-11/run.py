#!/usr/bin/env python3
"""Run the Jiangsu commercial-industrial storage bill instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the tariff table, basic-charge rules, asset, policy
  profile and data contract. A user-side advisor edits it; no code change is
  needed for a new customer or a new storage size.
* ``data/load_demo.csv`` is a twelve-month, 96-point representative-day load.

The bill kernels are the existing ``tariff-bill-optimization/tools`` modules
(``bill``, ``demand``, ``tariff``, ``curves``). This runner adds the monthly
declaration logic, a stylised peak-shaving block and a review sheet.

All bundled numbers are synthetic grade D. They are not a real bill, a real
customer or a pricing recommendation.
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

import bill  # noqa: E402
import curves  # noqa: E402
import demand  # noqa: E402
import tariff  # noqa: E402

MODE_NAMES = {"capacity": "按容量", "contract": "按合同需量", "actual": "按实际需量"}


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


def _periods(raw):
    periods = []
    for index, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ConfigError(f"rules.tariff.periods[{index}] must be [name, start, end]")
        name, start, end = item
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"rules.tariff.periods[{index}][0] must be a non-empty string")
        periods.append((name.strip(), int(start), int(end)))
    return periods


def validate_instance(config):
    """Validate the six blocks and return a provenance and check report."""
    report = {"ok": True, "provenance": [], "warnings": [], "checks": []}
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    _need(config, "contracts", "instance")
    data_contract = _need(config, "data_contract", "instance")

    tariff_rule = _rule_block(rules, "tariff")
    basic_rule = _rule_block(rules, "basic_charge")
    pf_rule = _rule_block(rules, "power_factor")
    _rule_block(rules, "storage_participation")
    _rule_block(rules, "market_channel")

    periods = _periods(_need(tariff_rule, "periods", "rules.tariff"))
    try:
        hours = tariff.validate_periods(periods)
    except ValueError as exc:
        raise ConfigError(f"rules.tariff.periods invalid: {exc}") from exc
    prices = _need(tariff_rule, "prices_cny_per_kwh", "rules.tariff")
    if not isinstance(prices, dict) or not prices:
        raise ConfigError("rules.tariff.prices_cny_per_kwh must be a non-empty object")
    for name in set(hours):
        if name not in prices:
            raise ConfigError(f"rules.tariff.prices_cny_per_kwh is missing period {name}")
    for name, value in prices.items():
        _number(value, f"rules.tariff.prices_cny_per_kwh.{name}", 0.0)
    transmission = _number(
        _need(tariff_rule, "transmission_cny_per_kwh", "rules.tariff"),
        "rules.tariff.transmission_cny_per_kwh",
        0.0,
    )
    system = _number(
        _need(tariff_rule, "system_cny_per_kwh", "rules.tariff"),
        "rules.tariff.system_cny_per_kwh",
        0.0,
    )
    fund = _number(
        _need(tariff_rule, "fund_cny_per_kwh", "rules.tariff"),
        "rules.tariff.fund_cny_per_kwh",
        0.0,
    )
    other = _number(
        tariff_rule.get("other_cny_per_kwh", 0.0),
        "rules.tariff.other_cny_per_kwh",
        0.0,
    )

    capacity_price = _number(
        _need(basic_rule, "capacity_price_cny_per_kva_month", "rules.basic_charge"),
        "rules.basic_charge.capacity_price_cny_per_kva_month",
        0.0,
    )
    demand_price = _number(
        _need(basic_rule, "demand_price_cny_per_kw_month", "rules.basic_charge"),
        "rules.basic_charge.demand_price_cny_per_kw_month",
        0.0,
    )
    threshold = _number(
        _need(basic_rule, "threshold", "rules.basic_charge"), "rules.basic_charge.threshold", 1.0
    )
    overrun = _number(
        _need(basic_rule, "overrun_multiplier", "rules.basic_charge"),
        "rules.basic_charge.overrun_multiplier",
        1.0,
    )
    floor_ratio = _number(
        _need(basic_rule, "floor_ratio", "rules.basic_charge"),
        "rules.basic_charge.floor_ratio",
        0.0,
        1.0,
    )

    pf_standard = _number(
        _need(pf_rule, "standard", "rules.power_factor"), "rules.power_factor.standard", 0.0, 1.0
    )
    _number(
        _need(pf_rule, "penalty_per_step", "rules.power_factor"),
        "rules.power_factor.penalty_per_step",
        0.0,
    )
    _number(
        _need(pf_rule, "reward_per_step", "rules.power_factor"),
        "rules.power_factor.reward_per_step",
        0.0,
    )
    _number(pf_rule.get("max_penalty", 0.15), "rules.power_factor.max_penalty", 0.0, 1.0)
    _number(pf_rule.get("max_reward", 0.075), "rules.power_factor.max_reward", 0.0, 1.0)

    transformer = _number(
        _need(asset, "transformer_kva", "asset"), "asset.transformer_kva", 1e-9
    )
    motor = _number(
        asset.get("high_voltage_motor_kva", 0.0), "asset.high_voltage_motor_kva", 0.0
    )
    contract_demand = _number(
        _need(asset, "contract_demand_kw", "asset"), "asset.contract_demand_kw", 0.0
    )
    floor_kw = float(floor_ratio) * (transformer + motor)
    if contract_demand < floor_kw - 1e-9:
        raise ConfigError("asset.contract_demand_kw is below the 40% floor")
    if contract_demand > transformer + 1e-9:
        raise ConfigError("asset.contract_demand_kw exceeds asset.transformer_kva")
    pf = _number(_need(asset, "power_factor", "asset"), "asset.power_factor", 0.0, 1.0)
    if pf <= 0:
        raise ConfigError("asset.power_factor must be positive")
    if pf_standard <= 0:
        raise ConfigError("rules.power_factor.standard must be positive")
    storage_power = _number(
        _need(asset, "storage_power_kw", "asset"), "asset.storage_power_kw", 1e-9
    )
    storage_energy = _number(
        _need(asset, "storage_energy_kwh", "asset"), "asset.storage_energy_kwh", 1e-9
    )
    usable_ratio = _number(
        _need(asset, "storage_usable_ratio", "asset"), "asset.storage_usable_ratio", 1e-9, 1.0
    )
    rte = _number(_need(asset, "storage_rte", "asset"), "asset.storage_rte", 1e-9, 1.0)
    _number(
        _need(asset, "storage_degradation_cny_per_kwh", "asset"),
        "asset.storage_degradation_cny_per_kwh",
        0.0,
    )
    _number(
        asset.get("storage_capex_cny_per_kwh", 0.0),
        "asset.storage_capex_cny_per_kwh",
        0.0,
    )
    _number(
        asset.get("storage_fixed_opex_cny_per_kw_year", 0.0),
        "asset.storage_fixed_opex_cny_per_kw_year",
        0.0,
    )

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    shave_ratio = _number(
        _need(policy, "shave_ratio", "policy"), "policy.shave_ratio", 0.0, 0.99
    )
    if shave_ratio <= 0:
        raise ConfigError("policy.shave_ratio must be positive")
    charge_period = _text(policy, "charge_period", "policy")
    if charge_period not in prices:
        raise ConfigError("policy.charge_period must be a tariff period")
    discharge_periods = _need(policy, "discharge_periods", "policy")
    if not isinstance(discharge_periods, list) or not discharge_periods:
        raise ConfigError("policy.discharge_periods must be a non-empty list")
    for name in discharge_periods:
        if name not in prices:
            raise ConfigError(f"policy.discharge_periods contains unknown period {name}")
    cycles = _number(
        _need(policy, "max_cycles_per_day", "policy"), "policy.max_cycles_per_day", 1e-9
    )
    min_spread = _number(
        _need(policy, "min_spread_cny_per_kwh", "policy"),
        "policy.min_spread_cny_per_kwh",
        0.0,
    )
    mode = _text(policy, "basic_charge_mode", "policy")
    if mode not in MODE_NAMES:
        raise ConfigError("policy.basic_charge_mode must be capacity, contract or actual")
    strategy = _text(policy, "declaration_strategy", "policy")
    if strategy != "monthly_optimal":
        raise ConfigError("policy.declaration_strategy must be monthly_optimal")

    load_contract = _need(data_contract, "load", "data_contract")
    _text(load_contract, "file", "data_contract.load")
    fields = _need(load_contract, "required_fields", "data_contract.load")
    if not isinstance(fields, list) or not fields:
        raise ConfigError("data_contract.load.required_fields must be a non-empty list")
    if int(_number(_need(load_contract, "months", "data_contract.load"), "months", 1)) != 12:
        raise ConfigError("data_contract.load.months must be 12")
    if int(_number(_need(load_contract, "points_per_month", "data_contract.load"), "points", 1)) != 96:
        raise ConfigError("data_contract.load.points_per_month must be 96")

    max_spread = max(float(prices[name]) for name in discharge_periods) - float(
        prices[charge_period]
    )
    if max_spread < min_spread:
        report["warnings"].append(
            f"峰谷价差 {max_spread:.2f} 元/kWh 低于策略下限 {min_spread:.2f}；demo 会按零收益处理"
        )

    def block(name, extra=""):
        item = {
            "block": f"rules.{name}",
            "grade": rules[name]["grade"],
            "source": rules[name]["source"],
        }
        if extra:
            item["status"] = extra
        return item

    report["provenance"] = [
        block("tariff", tariff_rule.get("status", "")),
        block("basic_charge", basic_rule.get("status", "")),
        block("power_factor"),
        block("storage_participation"),
        block("market_channel", rules["market_channel"].get("note", "")),
    ]
    report["warnings"].append("时段表与电价为 D 级合成示例，不是江苏现行电价；落地必须整表替换。")
    report["warnings"].append("削峰按恒功率块简化，不是 EMS 逐时段调度；SOC 与备用约束未逐点校核。")
    report["warnings"].append("零售套餐比价、代理购电分摊、双路进线与高可靠性供电费未纳入。")
    report["checks"] = [
        {
            "hours": hours,
            "prices": {name: float(value) for name, value in prices.items()},
            "transmission": transmission,
            "system": system,
            "fund": fund,
            "other": other,
            "capacity_price": capacity_price,
            "demand_price": demand_price,
            "threshold": threshold,
            "overrun": overrun,
            "floor_ratio": floor_ratio,
            "floor_kw": floor_kw,
            "pf": pf,
            "storage_power_kw": storage_power,
            "storage_energy_kwh": storage_energy,
            "usable_ratio": usable_ratio,
            "rte": rte,
            "shave_ratio": shave_ratio,
            "charge_period": charge_period,
            "discharge_periods": list(discharge_periods),
            "max_cycles": cycles,
            "min_spread": min_spread,
            "mode": mode,
        }
    ]
    report["periods"] = periods
    return report


def read_load(path, config):
    """Read the twelve-month representative-day load and validate the grid."""
    contract = config["data_contract"]["load"]
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if not rows:
        raise ConfigError(f"{path} is empty")
    for field in contract["required_fields"]:
        if field not in rows[0]:
            raise ConfigError(f"{path} is missing field {field}")
    loads = {month: [None] * 96 for month in range(1, 13)}
    for index, row in enumerate(rows, start=2):
        try:
            month = int(row["month"])
            slot = int(row["slot"])
        except (TypeError, ValueError):
            raise ConfigError(f"{path}: row {index} has a non-integer month or slot")
        if month not in loads:
            raise ConfigError(f"{path}: row {index} month {month} is outside 1-12")
        if not 0 <= slot < 96:
            raise ConfigError(f"{path}: row {index} slot {slot} is outside 0-95")
        if loads[month][slot] is not None:
            raise ConfigError(f"{path}: duplicate month {month} slot {slot}")
        load = _number(row["load_kw"], f"{path}:row {index} load_kw", 0.0)
        loads[month][slot] = load
    for month, series in loads.items():
        missing = [slot for slot, value in enumerate(series) if value is None]
        if missing:
            raise ConfigError(f"{path}: month {month} is missing slots {missing[:5]}")
    return loads


def _days_in_month(month):
    return curves.MONTH_DAYS[month - 1]


def _monthly_energy(load, config, report):
    check = report["checks"][0]
    daily = tariff.tou_energy_cost(
        load,
        check["prices"],
        report["periods"],
        dt_h=0.25,
    )
    return daily


def _bill(load, max_load, mode, declared_kw, config, report, days):
    check = report["checks"][0]
    daily = _monthly_energy(load, config, report)
    kwh_by_period = {name: row["kwh"] * days for name, row in daily["by_period"].items()}
    if mode == "capacity":
        basic = bill.basic_charge_capacity(
            config["asset"]["transformer_kva"],
            check["capacity_price"],
        )["charge"]
    elif mode == "contract":
        basic = bill.basic_charge_demand(
            declared_kw,
            max_load,
            check["demand_price"],
            threshold=check["threshold"],
            overrun_multiplier=check["overrun"],
            floor_kw=check["floor_kw"],
        )["charge"]
    else:
        basic = bill.basic_charge_actual(max_load, check["demand_price"])["charge"]
    breakdown = bill.bill_breakdown(
        kwh_by_period,
        check["prices"],
        check["transmission"],
        check["system"],
        check["fund"],
        basic,
        pf=config["asset"]["power_factor"],
        pf_base=None,
        other_fees=check["other"] * sum(kwh_by_period.values()),
        pf_kwargs={
            "standard": config["rules"]["power_factor"]["standard"],
            "penalty_per_step": config["rules"]["power_factor"]["penalty_per_step"],
            "reward_per_step": config["rules"]["power_factor"]["reward_per_step"],
            "max_penalty": config["rules"]["power_factor"].get("max_penalty", 0.15),
            "max_reward": config["rules"]["power_factor"].get("max_reward", 0.075),
        },
    )
    return {
        "energy_kwh": breakdown["total_kwh"],
        "energy_cost": breakdown["lines"]["energy"],
        "transmission": breakdown["lines"]["transmission"],
        "system": breakdown["lines"]["system"],
        "fund": breakdown["lines"]["fund"],
        "other": breakdown["lines"]["other"],
        "basic_charge": breakdown["lines"]["basic"],
        "power_factor": breakdown["lines"]["power_factor"],
        "total": breakdown["total"],
        "average_price": breakdown["average_price"],
        "max_demand_kw": max_load,
        "mode": mode,
        "declared_kw": declared_kw,
    }


def _optimal_declared(max_load, config, report):
    check = report["checks"][0]
    row = demand.optimal_declared(
        max_load,
        check["demand_price"],
        floor_kw=check["floor_kw"],
        cap_kw=config["asset"]["transformer_kva"],
        threshold=check["threshold"],
        overrun_multiplier=check["overrun"],
    )
    return row


def _shave(load, config, report):
    """Stylised peak shaving: cap load at target, charge in valley headroom."""
    check = report["checks"][0]
    asset = config["asset"]
    policy = config["policy"]
    dt_h = 0.25
    max_load = max(load)
    target = max_load * (1.0 - check["shave_ratio"])
    power = check["storage_power_kw"]
    usable = check["storage_energy_kwh"] * check["usable_ratio"] * check["max_cycles"]
    max_discharge_ac = usable
    max_charge_ac = usable / check["rte"]
    hours = check["hours"]

    discharge = [0.0] * len(load)
    for slot in sorted(range(len(load)), key=lambda index: load[index], reverse=True):
        if hours[int(slot * dt_h + 1e-9)] not in check["discharge_periods"]:
            continue
        if load[slot] <= target + 1e-9:
            break
        discharge[slot] = min(power, load[slot] - target)
    raw_total = sum(discharge) * dt_h
    if raw_total <= 1e-9:
        return {
            "discharge": discharge,
            "charge": [0.0] * len(load),
            "new_load": list(load),
            "max_load": max_load,
            "target": target,
            "discharge_kwh": 0.0,
            "charge_kwh": 0.0,
        }
    scale = min(1.0, max_discharge_ac / raw_total)
    discharge = [value * scale for value in discharge]
    total_discharge = raw_total * scale
    needed_charge = total_discharge / check["rte"]

    candidates = []
    for slot in range(len(load)):
        if hours[int(slot * dt_h + 1e-9)] != check["charge_period"]:
            continue
        room = max(0.0, target - load[slot])
        if room > 1e-9:
            candidates.append((load[slot], slot, min(power, room)))
    candidates.sort()
    available = min(max_charge_ac, sum(room * dt_h for _, _, room in candidates))
    if available < needed_charge:
        scale = available / needed_charge
        discharge = [value * scale for value in discharge]
        total_discharge *= scale
        needed_charge = available

    charge = [0.0] * len(load)
    remaining = needed_charge
    for _, slot, room in candidates:
        if remaining <= 1e-9:
            break
        take = min(remaining, room * dt_h)
        charge[slot] = take / dt_h
        remaining -= take
    charge_total = sum(charge) * dt_h
    new_load = [
        max(0.0, load[slot] - discharge[slot] + charge[slot]) for slot in range(len(load))
    ]
    return {
        "discharge": discharge,
        "charge": charge,
        "new_load": new_load,
        "max_load": max(new_load),
        "target": target,
        "discharge_kwh": total_discharge,
        "charge_kwh": charge_total,
    }


def build_month(month, load, config, report):
    check = report["checks"][0]
    days = _days_in_month(month)
    max_load = max(load)
    optimal = _optimal_declared(max_load, config, report)

    baseline = _bill(load, max_load, "contract", config["asset"]["contract_demand_kw"], config, report, days)
    optimized = _bill(load, max_load, "contract", optimal["declared_kw"], config, report, days)
    capacity = _bill(load, max_load, "capacity", 0.0, config, report, days)
    actual = _bill(load, max_load, "actual", 0.0, config, report, days)

    shaved = _shave(load, config, report)
    new_max = shaved["max_load"]
    optimal_after = _optimal_declared(new_max, config, report)
    headline = _bill(shaved["new_load"], new_max, check["mode"], optimal_after["declared_kw"] if check["mode"] == "contract" else 0.0, config, report, days)
    capacity_after = _bill(shaved["new_load"], new_max, "capacity", 0.0, config, report, days)
    actual_after = _bill(shaved["new_load"], new_max, "actual", 0.0, config, report, days)

    throughput = (shaved["discharge_kwh"] + shaved["charge_kwh"]) * days
    degradation = throughput * float(config["asset"]["storage_degradation_cny_per_kwh"])
    fixed_opex = (
        float(config["asset"]["storage_power_kw"])
        * float(config["asset"].get("storage_fixed_opex_cny_per_kw_year", 0.0))
        / 12.0
    )
    storage_cost = degradation + fixed_opex
    net_saving = baseline["total"] - (headline["total"] + storage_cost)
    storage_saving = optimized["total"] - (headline["total"] + storage_cost)

    modes_before = {"capacity": capacity["basic_charge"], "contract": optimized["basic_charge"], "actual": actual["basic_charge"]}
    modes_after = {"capacity": capacity_after["basic_charge"], "contract": headline["basic_charge"], "actual": actual_after["basic_charge"]}
    best_before = min(modes_before, key=modes_before.get)
    best_after = min(modes_after, key=modes_after.get)

    return {
        "month": month,
        "days": days,
        "max_load_kw": max_load,
        "optimal_declared_kw": optimal["declared_kw"],
        "baseline": baseline,
        "optimized": optimized,
        "capacity": capacity,
        "actual": actual,
        "shaved": shaved,
        "new_max_kw": new_max,
        "optimal_after_kw": optimal_after["declared_kw"],
        "headline": headline,
        "capacity_after": capacity_after,
        "actual_after": actual_after,
        "degradation_cny": degradation,
        "fixed_opex_cny": fixed_opex,
        "storage_cost_cny": storage_cost,
        "net_saving_cny": net_saving,
        "storage_saving_cny": storage_saving,
        "modes_before": modes_before,
        "modes_after": modes_after,
        "best_before": best_before,
        "best_after": best_after,
    }


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(field, row.get(field)) for field in fields})


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if field in ("average_price",):
            return f"{value:.6f}"
        if field in ("declared_kw", "optimal_declared_kw", "optimal_after_kw"):
            return f"{value:.2f}"
        return f"{value:.2f}"
    return value


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _wan(value):
    return "—" if value is None else f"{value / 10000.0:,.2f}"


def _kwh(value):
    return f"{value:,.0f}"


def write_review(path, config, report, months, summary, fingerprint):
    policy = config["policy"]
    asset = config["asset"]
    lines = [
        "# 江苏工商业储能电费优化复核表",
        "",
        f"- 实例：`{config['meta']['instance_id']}`",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 策略档：`{policy['profile_id']}` / 指纹 `{fingerprint}`",
        f"- 用户：{asset['transformer_kva']:.0f} kVA，当前合同需量 {asset['contract_demand_kw']:.0f} kW，"
        f"功率因数 {asset['power_factor']:.2f}",
        f"- 储能：{asset['storage_power_kw']:.0f} kW / {asset['storage_energy_kwh']:.0f} kWh，"
        f"RTE {asset['storage_rte']:.2f}，可用比例 {asset['storage_usable_ratio']:.2f}",
        "- 全部数据为 D 级合成，不对应任何真实用户或账单。",
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
        "## 2. 年度结论",
        "",
        "| 项目 | 金额（万元） |",
        "|---|---:|",
        f"| 当前账单（合同需量 {asset['contract_demand_kw']:.0f} kW） | {_wan(summary['baseline_total_cny'])} |",
        f"| 仅重算申报、不加储能 | {_wan(summary['optimized_total_cny'])} |",
        f"| 储能削峰 + 重算申报 | {_wan(summary['headline_total_cny'])} |",
        f"| 申报优化节省（vs 当前） | {_wan(summary['declaration_saving_cny'])} |",
        f"| 储能净节省（vs 仅重算申报） | {_wan(summary['storage_saving_cny'])} |",
        f"| 总节省（vs 当前） | {_wan(summary['net_saving_cny'])} |",
        f"| 储能资本开支（参考） | {_wan(summary['storage_capex_cny'])} |",
        f"| 静态回收期（仅储能节省，参考） | {summary['payback_years']:.2f} 年 |" if summary["payback_years"] is not None else "| 静态回收期 | — |",
        "",
        "读法：申报优化节省来自按月把合同需量压到实际峰值 ÷ 1.05；储能节省还要扣退化、运维与充电成本。"
        "两者必须分开看，不能把申报优化说成储能收益。",
        "",
        "## 3. 逐月账单",
        "",
        "| 月 | 当前账单（万元） | 仅重算申报（万元） | 储能后（万元） | 削峰前最大需量 | 削峰后最大需量 | 净节省（万元） |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in months:
        lines.append(
            f"| {item['month']} | {_wan(item['baseline']['total'])} | {_wan(item['optimized']['total'])} | "
            f"{_wan(item['headline']['total'])} | {item['max_load_kw']:.0f} | {item['new_max_kw']:.0f} | "
            f"{_wan(item['net_saving_cny'])} |"
        )
    lines += [
        "",
        "## 4. 基本电费三方式",
        "",
        "| 月 | 削峰前最大需量 | 按容量 | 按合同需量（最优申报） | 按实际需量 | 削峰前最优 | 削峰后最优 |",
        "|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in months:
        lines.append(
            f"| {item['month']} | {item['max_load_kw']:.0f} | {_money(item['modes_before']['capacity'])} | "
            f"{_money(item['modes_before']['contract'])} | {_money(item['modes_before']['actual'])} | "
            f"{MODE_NAMES[item['best_before']]} | {MODE_NAMES[item['best_after']]} |"
        )
    lines += [
        "",
        f"策略档选择的基本电费方式：**{MODE_NAMES[policy['basic_charge_mode']]}**。三方式按月比较，"
        "不能用全年一个方式一刀切。",
        "",
        "## 5. 储能削峰口径",
        "",
        "| 项目 | 年度值 |",
        "|---|---:|",
        f"| 放电量 | {_kwh(summary['discharge_mwh'] * 1000)} kWh |",
        f"| 充电量 | {_kwh(summary['charge_mwh'] * 1000)} kWh |",
        f"| 平均削峰 | {summary['average_reduction_kw']:.1f} kW |",
        f"| 退化成本 | {_wan(summary['degradation_cny'])} 万元 |",
        f"| 运维分摊 | {_wan(summary['fixed_opex_cny'])} 万元 |",
        "",
        "削峰按恒功率块简化：先按目标线削减峰/尖段，再在谷段有裕度时充电；"
        "没有做 SOC 逐点、备用与电池寿命的详细优化，详细调度交给 EMS 技能。",
        "",
        "## 6. 三个复核问题",
        "",
        "1. 当前合同需量为什么低于实际峰值？是历史申报遗留、扩产还是季节性负荷？",
        "2. 储能削峰后，新最大需量是否会在下月被充电抬高？申报值是否留了 5% 余量？",
        "3. 分时时段、40% 下限、105% 超需与力率基数是否已替换为江苏现行文件？",
        "",
        "## 7. 告警与边界",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        f"- {config['meta']['disclaimer']}",
        "- 本表是账单与削峰测算，不是投资决策、设备选型或售电套餐报价。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, load_path, out_dir):
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{instance_path.name} is not valid JSON: {exc}") from exc
    report = validate_instance(config)
    loads = read_load(load_path, config)
    months = [build_month(month, loads[month], config, report) for month in range(1, 13)]

    baseline_total = sum(item["baseline"]["total"] for item in months)
    optimized_total = sum(item["optimized"]["total"] for item in months)
    headline_total = sum(item["headline"]["total"] for item in months)
    storage_cost = sum(item["storage_cost_cny"] for item in months)
    declaration_saving = baseline_total - optimized_total
    storage_saving = optimized_total - (headline_total + storage_cost)
    net_saving = baseline_total - (headline_total + storage_cost)
    discharge_mwh = sum(item["shaved"]["discharge_kwh"] * item["days"] for item in months) / 1000.0
    charge_mwh = sum(item["shaved"]["charge_kwh"] * item["days"] for item in months) / 1000.0
    average_reduction = sum(item["max_load_kw"] - item["new_max_kw"] for item in months) / 12.0
    capex = (
        float(config["asset"]["storage_power_kw"])
        * (float(config["asset"]["storage_energy_kwh"]) / float(config["asset"]["storage_power_kw"]))
        * float(config["asset"].get("storage_capex_cny_per_kwh", 0.0))
    )
    payback = capex / storage_saving if storage_saving > 0 else None

    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_rows = []
    storage_rows = []
    compare_rows = []
    demand_rows = []
    for item in months:
        baseline = item["baseline"]
        baseline_rows.append(
            {
                "month": item["month"],
                "mode": MODE_NAMES[baseline["mode"]],
                "energy_kwh": baseline["energy_kwh"],
                "energy_cost": baseline["energy_cost"],
                "transmission": baseline["transmission"],
                "system": baseline["system"],
                "fund": baseline["fund"],
                "basic_charge": baseline["basic_charge"],
                "power_factor": baseline["power_factor"],
                "total": baseline["total"],
                "average_price": baseline["average_price"],
                "max_demand_kw": baseline["max_demand_kw"],
            }
        )
        storage_rows.append(
            {
                "month": item["month"],
                "baseline_total": baseline["total"],
                "storage_discharge_kwh": item["shaved"]["discharge_kwh"] * item["days"],
                "storage_charge_kwh": item["shaved"]["charge_kwh"] * item["days"],
                "new_max_demand_kw": item["new_max_kw"],
                "new_basic_charge": item["headline"]["basic_charge"],
                "new_total": item["headline"]["total"],
                "degradation_cny": item["degradation_cny"],
                "fixed_opex_cny": item["fixed_opex_cny"],
                "net_saving_cny": item["net_saving_cny"],
            }
        )
        compare_rows.append(
            {
                "month": item["month"],
                "max_demand_kw": item["max_load_kw"],
                "capacity_charge": item["modes_before"]["capacity"],
                "contract_declared_kw": item["optimal_declared_kw"],
                "contract_charge": item["modes_before"]["contract"],
                "actual_charge": item["modes_before"]["actual"],
                "best_mode": MODE_NAMES[item["best_before"]],
                "optimal_declared_kw": item["optimal_declared_kw"],
            }
        )
        demand_rows.append(
            {
                "month": item["month"],
                "baseline_max_kw": item["max_load_kw"],
                "target_kw": item["shaved"]["target"],
                "after_max_kw": item["new_max_kw"],
                "declared_before_kw": item["optimal_declared_kw"],
                "declared_after_kw": item["optimal_after_kw"],
                "reduction_kw": item["max_load_kw"] - item["new_max_kw"],
            }
        )

    _write_csv(
        out_dir / "bill_baseline.csv",
        baseline_rows,
        [
            "month",
            "mode",
            "energy_kwh",
            "energy_cost",
            "transmission",
            "system",
            "fund",
            "basic_charge",
            "power_factor",
            "total",
            "average_price",
            "max_demand_kw",
        ],
    )
    _write_csv(
        out_dir / "bill_with_storage.csv",
        storage_rows,
        [
            "month",
            "baseline_total",
            "storage_discharge_kwh",
            "storage_charge_kwh",
            "new_max_demand_kw",
            "new_basic_charge",
            "new_total",
            "degradation_cny",
            "fixed_opex_cny",
            "net_saving_cny",
        ],
    )
    _write_csv(
        out_dir / "basic_charge_compare.csv",
        compare_rows,
        [
            "month",
            "max_demand_kw",
            "capacity_charge",
            "contract_declared_kw",
            "contract_charge",
            "actual_charge",
            "best_mode",
            "optimal_declared_kw",
        ],
    )
    _write_csv(
        out_dir / "demand.csv",
        demand_rows,
        [
            "month",
            "baseline_max_kw",
            "target_kw",
            "after_max_kw",
            "declared_before_kw",
            "declared_after_kw",
            "reduction_kw",
        ],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "baseline_total_cny": baseline_total,
        "optimized_total_cny": optimized_total,
        "headline_total_cny": headline_total,
        "declaration_saving_cny": declaration_saving,
        "storage_saving_cny": storage_saving,
        "net_saving_cny": net_saving,
        "storage_capex_cny": capex,
        "payback_years": payback,
        "discharge_mwh": discharge_mwh,
        "charge_mwh": charge_mwh,
        "average_reduction_kw": average_reduction,
        "degradation_cny": sum(item["degradation_cny"] for item in months),
        "fixed_opex_cny": sum(item["fixed_opex_cny"] for item in months),
        "warnings": report["warnings"],
        "months": months,
        "files": [
            "bill_baseline.csv",
            "bill_with_storage.csv",
            "basic_charge_compare.csv",
            "demand.csv",
            "review.md",
        ],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(out_dir / "review.md", config, report, months, summary, fingerprint)
    return {"summary": summary, "out_dir": out_dir}


def _resolve_load(config):
    path = Path(config["data_contract"]["load"]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Jiangsu C&I storage bill instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--load", help="12-month, 96-point load CSV")
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
        load_path = _resolve_load(config)
        out_dir = Path(args.out) if args.out != str(HERE / "out") else HERE / "out" / "demo"
    else:
        if not args.load:
            print("必须提供 --load，或使用 --demo", file=sys.stderr)
            return 1
        load_path = Path(args.load)
        out_dir = Path(args.out)

    try:
        result = run_instance(args.instance, load_path, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(f"实例：{summary['instance_id']}")
    print(
        f"年账单：当前 {_wan(summary['baseline_total_cny'])} 万元 → 仅重算申报 "
        f"{_wan(summary['optimized_total_cny'])} 万元 → 储能后 {_wan(summary['headline_total_cny'])} 万元"
    )
    print(
        f"节省：申报优化 {_wan(summary['declaration_saving_cny'])} 万元，"
        f"储能净节省 {_wan(summary['storage_saving_cny'])} 万元，"
        f"合计 {_wan(summary['net_saving_cny'])} 万元"
    )
    payback = "—" if summary["payback_years"] is None else f"{summary['payback_years']:.2f} 年"
    print(
        f"储能：放电 {summary['discharge_mwh']:.1f} MWh，充电 {summary['charge_mwh']:.1f} MWh，"
        f"平均削峰 {summary['average_reduction_kw']:.1f} kW，静态回收期 {payback}"
    )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
