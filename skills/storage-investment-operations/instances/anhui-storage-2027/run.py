#!/usr/bin/env python3
"""Run the Anhui standalone-storage capacity-price instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the rule parameters, asset, policy profile,
  contracts and data contract. An investor edits it; no code change is
  needed for a new asset or a new style profile.
* ``data/scenarios_demo.csv`` is a five-scenario annual price set.
* ``data/assessment_demo.csv`` is a twelve-month availability record.

The calculations reuse the existing ``storage-investment-operations/tools``
kernels (``stacking``, ``finance``). This runner only adds the Anhui duration
ladder, the 98% availability assessment and a review sheet.

All bundled numbers are synthetic grade D. They are not a market forecast, a
real project or investment advice.
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

import finance  # noqa: E402
import stacking  # noqa: E402

DURATIONS_H = (2.0, 4.0, 6.0)
MONTHS_EXPECTED = 12


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
    capacity = _rule_block(rules, "capacity", report)
    _rule_block(rules, "participation", report)
    _rule_block(rules, "settlement", report)

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = _integer(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1)
    if abs(24 * 60 / mtu - points) > 1e-9:
        raise ConfigError(f"rules.spot.points_per_day ({points}) does not match 24*60/{mtu:g}")
    if points != 96:
        raise ConfigError("Anhui spot uses 96 fifteen-minute points per day")
    bounds = [
        spot.get("clear_floor_cny_per_mwh"),
        spot.get("declare_floor_cny_per_mwh"),
        spot.get("declare_cap_cny_per_mwh"),
        spot.get("clear_cap_cny_per_mwh"),
    ]
    if all(value is not None for value in bounds):
        clear_floor, declare_floor, declare_cap, clear_cap = (
            _number(value, "rules.spot.price_bound") for value in bounds
        )
        if not (clear_floor <= declare_floor < declare_cap <= clear_cap):
            raise ConfigError(
                "price bounds must satisfy clear_floor <= declare_floor < declare_cap <= clear_cap"
            )
    else:
        report["warnings"].append("现货限价未核到正式数值，运行器不套用外省限价")

    capacity_price = _number(
        _need(capacity, "price_cny_per_kw_year", "rules.capacity"),
        "rules.capacity.price_cny_per_kw_year",
        1e-9,
    )
    if abs(capacity_price - 165.0) > 1e-9:
        raise ConfigError("皖发改价格〔2026〕526号: capacity price must be 165 CNY/kW-year")
    denominator = _number(
        _need(capacity, "denominator_hours", "rules.capacity"),
        "rules.capacity.denominator_hours",
        1e-9,
    )
    if abs(denominator - 6.0) > 1e-9:
        raise ConfigError("皖发改价格〔2026〕526号: duration denominator must be 6 hours")
    ladder = _need(capacity, "duration_conversion_cny_per_kw_year", "rules.capacity")
    for duration in DURATIONS_H:
        key = f"{duration:g}"
        value = _number(ladder.get(key), f"rules.capacity.duration_conversion.{key}", 0.0)
        expected = capacity_price * min(duration / denominator, 1.0)
        if abs(value - expected) > 1e-6:
            raise ConfigError(
                f"duration conversion {key}h must equal {expected:g} CNY/kW-year"
            )
    effective_from = _text(capacity, "effective_from", "rules.capacity")
    if effective_from != "2027-01-01":
        raise ConfigError("capacity price effective date must be 2027-01-01")

    assessment = _need(capacity, "assessment", "rules.capacity")
    threshold = _number(
        _need(assessment, "output_threshold_ratio", "rules.capacity.assessment"),
        "rules.capacity.assessment.output_threshold_ratio",
        1e-9,
        1.0,
    )
    strike_limit = _integer(
        _need(assessment, "strike_limit", "rules.capacity.assessment"),
        "rules.capacity.assessment.strike_limit",
        1,
    )
    _text(assessment, "deduction_formula", "rules.capacity.assessment")

    power = _number(_need(asset, "power_mw", "asset"), "asset.power_mw", 1e-9)
    energy = _number(_need(asset, "energy_mwh", "asset"), "asset.energy_mwh", 1e-9)
    usable = _number(_need(asset, "usable_energy_mwh", "asset"), "asset.usable_energy_mwh", 1e-9)
    rte = _number(_need(asset, "rte", "asset"), "asset.rte", 1e-9, 1.0)
    soc_min = _number(_need(asset, "soc_min", "asset"), "asset.soc_min", 0.0, 1.0)
    soc_max = _number(_need(asset, "soc_max", "asset"), "asset.soc_max", 0.0, 1.0)
    if not soc_min < soc_max:
        raise ConfigError("asset.soc_min must be below asset.soc_max")
    window = (soc_max - soc_min) * energy
    if abs(usable - window) > 1e-6 * max(1.0, window):
        raise ConfigError("asset.usable_energy_mwh must equal energy_mwh * (soc_max - soc_min)")
    if usable > power * 24:
        raise ConfigError("asset.usable_energy_mwh exceeds a plausible 24-hour duration")
    _number(
        _need(asset, "degradation_cny_per_mwh_throughput", "asset"),
        "asset.degradation_cny_per_mwh_throughput",
        0.0,
    )
    fixed_opex = _number(
        _need(asset, "fixed_opex_cny_per_year", "asset"),
        "asset.fixed_opex_cny_per_year",
        0.0,
    )
    capex_per_kwh = _number(
        _need(asset, "capex_cny_per_kwh", "asset"),
        "asset.capex_cny_per_kwh",
        1e-9,
    )
    years = _integer(_need(asset, "project_years", "asset"), "asset.project_years", 1)
    discount = _number(_need(asset, "discount_rate", "asset"), "asset.discount_rate", 0.0, 1.0)
    tax_rate = _number(_need(asset, "tax_rate", "asset"), "asset.tax_rate", 0.0, 1.0)
    _number(_need(asset, "availability", "asset"), "asset.availability", 0.0, 1.0)

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    cycles = _number(_need(policy, "cycles_per_day", "policy"), "policy.cycles_per_day", 0.0, 10.0)
    days = _number(_need(policy, "operating_days", "policy"), "policy.operating_days", 0.0, 365.0)
    charge_q = _number(
        _need(policy, "charge_price_quantile", "policy"), "policy.charge_price_quantile", 0.0, 1.0
    )
    discharge_q = _number(
        _need(policy, "discharge_price_quantile", "policy"),
        "policy.discharge_price_quantile",
        0.0,
        1.0,
    )
    base_duration = _number(_need(policy, "duration_h", "policy"), "policy.duration_h", 1e-9)
    if base_duration not in DURATIONS_H:
        raise ConfigError("policy.duration_h must be one of the ladder durations 2/4/6 h")
    confidence = _number(
        _need(policy, "scenario_cvar_confidence", "policy"),
        "policy.scenario_cvar_confidence",
        0.0,
        1.0,
    )
    if not 0 < confidence < 1:
        raise ConfigError("policy.scenario_cvar_confidence must be in (0, 1)")

    _need(contracts, "capacity_listing", "contracts")
    _need(contracts, "lease", "contracts")
    scenario_contract = _need(data_contract, "scenarios", "data_contract")
    assessment_contract = _need(data_contract, "assessment", "data_contract")
    for item, name in ((scenario_contract, "scenarios"), (assessment_contract, "assessment")):
        _text(item, "file", f"data_contract.{name}")
        fields = _need(item, "required_fields", f"data_contract.{name}")
        if not isinstance(fields, list) or not fields:
            raise ConfigError(f"data_contract.{name}.required_fields must be a non-empty list")
    scenario_count = _integer(
        _need(scenario_contract, "scenario_count", "data_contract.scenarios"),
        "data_contract.scenarios.scenario_count",
        1,
    )
    if scenario_count != 5:
        raise ConfigError("data_contract.scenarios.scenario_count must be 5 for this demo contract")

    report["checks"].append(
        {
            "capacity_price_cny_per_kw_year": capacity_price,
            "denominator_hours": denominator,
            "duration_ladder": {f"{d:g}": ladder[f"{d:g}"] for d in DURATIONS_H},
            "assessment_threshold": threshold,
            "strike_limit": strike_limit,
            "effective_from": effective_from,
            "power_mw": power,
            "energy_mwh": energy,
            "usable_energy_mwh": usable,
            "rte": rte,
            "fixed_opex_cny_per_year": fixed_opex,
            "capex_cny_per_kwh": capex_per_kwh,
            "project_years": years,
            "discount_rate": discount,
            "tax_rate": tax_rate,
            "cycles_per_day": cycles,
            "operating_days": days,
            "charge_quantile": charge_q,
            "discharge_quantile": discharge_q,
            "base_duration_h": base_duration,
            "cvar_confidence": confidence,
        }
    )
    report["points_per_day"] = points
    report["mtu_min"] = mtu
    report["warnings"].append("容量考核扣减为 D 级简化公式，不是省级阶梯表")
    report["warnings"].append("容量电费自 2027-01-01 起执行，模型第 1 年为 2027")
    return report


def _read_rows(path):
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}")


def _require_fields(rows, required, name):
    if not rows:
        raise ConfigError(f"{name} is empty")
    missing = [field for field in required if field not in rows[0]]
    if missing:
        raise ConfigError(f"{name} is missing fields: {', '.join(missing)}")


def read_scenarios(path, config):
    """Read and validate the annual scenario set; weights must sum to one."""
    contract = config["data_contract"]["scenarios"]
    rows = _read_rows(path)
    _require_fields(rows, contract["required_fields"], "scenarios")
    scenarios = []
    for index, row in enumerate(rows, start=1):
        name = (row.get("scenario") or "").strip()
        if not name:
            raise ConfigError(f"scenario row {index} has an empty scenario name")
        charge = _number(row.get("charge_price"), f"scenario {name}.charge_price", -1000.0, 5000.0)
        discharge = _number(
            row.get("discharge_price"), f"scenario {name}.discharge_price", -1000.0, 5000.0
        )
        weight = _number(row.get("weight"), f"scenario {name}.weight", 0.0, 1.0)
        scenarios.append(
            {
                "scenario": name,
                "charge_price": charge,
                "discharge_price": discharge,
                "weight": weight,
            }
        )
    if len(scenarios) != int(contract["scenario_count"]):
        raise ConfigError(
            f"expected {contract['scenario_count']} scenarios, got {len(scenarios)}"
        )
    total_weight = sum(item["weight"] for item in scenarios)
    if abs(total_weight - 1.0) > 1e-6:
        raise ConfigError(f"scenario weights must sum to 1, got {total_weight:g}")
    return scenarios


def read_assessment(path, config):
    """Read and validate the monthly availability record."""
    contract = config["data_contract"]["assessment"]
    rows = _read_rows(path)
    _require_fields(rows, contract["required_fields"], "assessment")
    months = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        month = (row.get("month") or "").strip()
        if not month:
            raise ConfigError(f"assessment row {index} has an empty month")
        if month in seen:
            raise ConfigError(f"duplicate assessment month: {month}")
        seen.add(month)
        availability = _number(
            row.get("availability_ratio"), f"assessment {month}.availability_ratio", 0.0, 1.0
        )
        months.append({"month": month, "availability_ratio": availability})
    if len(months) != MONTHS_EXPECTED:
        raise ConfigError(f"expected {MONTHS_EXPECTED} assessment months, got {len(months)}")
    return months


def arbitrage_case(config, duration_h, charge_price, discharge_price):
    """Annual arbitrage for one duration under one price pair."""
    asset = config["asset"]
    policy = config["policy"]
    usable_ratio = asset["usable_energy_mwh"] / asset["energy_mwh"]
    return stacking.arbitrage(
        power_mw=asset["power_mw"],
        duration_h=duration_h,
        rte=asset["rte"],
        cycles_per_day=policy["cycles_per_day"],
        days=policy["operating_days"],
        charge_price=charge_price,
        discharge_price=discharge_price,
        usable_ratio=usable_ratio,
        availability=1.0,
        degradation_cost_per_kwh=asset["degradation_cny_per_mwh_throughput"] / 1000.0,
    )


def capacity_case(config, duration_h, assessment_rows):
    """Gross capacity payment and the 98% availability deduction for one duration."""
    asset = config["asset"]
    rules = config["rules"]["capacity"]
    payment = stacking.capacity_payment(
        power_mw=asset["power_mw"],
        price_per_kw_year=rules["price_cny_per_kw_year"],
        duration_h=duration_h,
        peak_duration_h=rules["denominator_hours"],
        availability=1.0,
    )
    gross = payment["annual"]
    threshold = rules["assessment"]["output_threshold_ratio"]
    strike_limit = rules["assessment"]["strike_limit"]
    monthly = gross / MONTHS_EXPECTED
    months = []
    strikes = 0
    deduction = 0.0
    for record in assessment_rows:
        availability = record["availability_ratio"]
        shortfall = max(0.0, 1.0 - availability / threshold)
        month_deduction = monthly * shortfall
        if shortfall > 0:
            strikes += 1
        deduction += month_deduction
        months.append(
            {
                "month": record["month"],
                "availability_ratio": availability,
                "shortfall_ratio": shortfall,
                "deduction_cny": month_deduction,
                "strikes_cumulative": strikes,
            }
        )
    zeroed = strikes >= strike_limit
    net = 0.0 if zeroed else gross - deduction
    return {
        "duration_h": duration_h,
        "ratio": payment["ratio"],
        "gross_cny": gross,
        "monthly_cny": monthly,
        "deduction_cny": deduction,
        "net_cny": net,
        "strikes": strikes,
        "strike_limit": strike_limit,
        "zeroed": zeroed,
        "months": months,
    }


def _weighted_mean(scenarios, key):
    return sum(item["weight"] * item[key] for item in scenarios)


def weighted_cvar(pairs, confidence):
    """Weighted CVaR of the worst (1 - confidence) probability mass."""
    tail = 1.0 - confidence
    remaining = tail
    accumulated = 0.0
    for weight, value in sorted(pairs, key=lambda pair: pair[1]):
        take = min(weight, remaining)
        accumulated += take * value
        remaining -= take
        if remaining <= 1e-12:
            break
    used = tail - remaining
    if used <= 1e-12:
        return None
    return accumulated / used


def build_ladder(config, scenarios, assessment_rows):
    """Duration ladder with capacity payment, arbitrage, NPV and LCOS."""
    asset = config["asset"]
    policy = config["policy"]
    fixed_opex = asset["fixed_opex_cny_per_year"]
    rows = []
    for duration in DURATIONS_H:
        arbitrage = [
            arbitrage_case(config, duration, item["charge_price"], item["discharge_price"])
            for item in scenarios
        ]
        annual_gross = _weighted_mean(
            [{"weight": item["weight"], "value": result["annual_gross"]} for item, result in zip(scenarios, arbitrage)],
            "value",
        )
        annual_charge_cost = _weighted_mean(
            [
                {
                    "weight": item["weight"],
                    "value": result["charge_mwh_per_cycle"]
                    * policy["cycles_per_day"]
                    * policy["operating_days"]
                    * item["charge_price"],
                }
                for item, result in zip(scenarios, arbitrage)
            ],
            "value",
        )
        annual_degradation = arbitrage[0]["annual_degradation_cost"]
        arbitrage_net = annual_gross - annual_degradation
        discharge_mwh = (
            arbitrage[0]["discharge_mwh_per_cycle"] * policy["cycles_per_day"] * policy["operating_days"]
        )
        capacity = capacity_case(config, duration, assessment_rows)
        capex = asset["power_mw"] * duration * 1000.0 * asset["capex_cny_per_kwh"]
        revenue = annual_gross + capacity["net_cny"]
        opex = fixed_opex + annual_degradation
        cashflows = finance.annual_cashflow(
            revenue=revenue,
            opex=opex,
            capex=capex,
            years=asset["project_years"],
            tax_rate=asset["tax_rate"],
            depreciation_years=asset["project_years"],
        )
        rows.append(
            {
                "duration_h": duration,
                "power_mw": asset["power_mw"],
                "energy_mwh": asset["power_mw"] * duration,
                "usable_energy_mwh": asset["power_mw"] * duration
                * asset["usable_energy_mwh"]
                / asset["energy_mwh"],
                "capex_cny": capex,
                "capacity_ratio": capacity["ratio"],
                "capacity_gross_cny": capacity["gross_cny"],
                "assessment_deduction_cny": capacity["deduction_cny"],
                "capacity_net_cny": capacity["net_cny"],
                "strikes": capacity["strikes"],
                "strike_limit": capacity["strike_limit"],
                "capacity_zeroed": capacity["zeroed"],
                "arbitrage_gross_cny": annual_gross,
                "degradation_cny": annual_degradation,
                "arbitrage_net_cny": arbitrage_net,
                "charge_cost_cny": annual_charge_cost,
                "fixed_opex_cny": fixed_opex,
                "revenue_cny": revenue,
                "opex_cny": opex,
                "npv_cny": finance.npv(asset["discount_rate"], cashflows),
                "irr": finance.irr(cashflows),
                "payback_years": finance.payback(cashflows),
                "lcos_cny_per_mwh": finance.lcos(
                    capex=capex,
                    annual_opex=opex,
                    annual_charge_cost=annual_charge_cost,
                    annual_discharge_mwh=discharge_mwh,
                    years=asset["project_years"],
                    discount_rate=asset["discount_rate"],
                ),
                "cashflows": cashflows,
            }
        )
    return rows


def build_scenario_table(config, scenarios, duration_h, capacity_net):
    """Per-scenario annual net for the base duration."""
    rows = []
    for item in scenarios:
        arbitrage = arbitrage_case(config, duration_h, item["charge_price"], item["discharge_price"])
        total = arbitrage["annual_net"] + capacity_net
        rows.append(
            {
                "scenario": item["scenario"],
                "weight": item["weight"],
                "charge_price": item["charge_price"],
                "discharge_price": item["discharge_price"],
                "arbitrage_net_cny": arbitrage["annual_net"],
                "capacity_net_cny": capacity_net,
                "total_net_cny": total,
            }
        )
    return rows


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
        if field == "irr":
            return f"{value:.6f}"
        if field in ("lcos_cny_per_mwh", "payback_years", "capacity_ratio"):
            return f"{value:.4f}"
        if field in ("availability_ratio", "shortfall_ratio"):
            return f"{value:.4f}"
        if field == "weight":
            return f"{value:.2f}"
        return f"{value:.2f}"
    return value


def _money(value):
    if value is None:
        return "—"
    return f"{value:,.0f}"


def _wan(value):
    if value is None:
        return "—"
    return f"{value / 10000.0:,.1f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def _years(value):
    return "—" if value is None else f"{value:.2f} 年"


def write_review(path, config, report, scenarios, ladder, scenario_table, assessment, fingerprint):
    asset = config["asset"]
    policy = config["policy"]
    base = next(row for row in ladder if row["duration_h"] == policy["duration_h"])
    expected_total = sum(item["weight"] * item["total_net_cny"] for item in scenario_table)
    cvar = weighted_cvar(
        [(item["weight"], item["total_net_cny"]) for item in scenario_table],
        policy["scenario_cvar_confidence"],
    )
    lines = [
        "# 安徽独立储能容量电价实例 · 复核单",
        "",
        f"- 实例：`{config['meta']['instance_id']}`",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格指纹：`{fingerprint}`",
        "- 全部数据为 D 级合成，不对应任何真实项目或结算单。",
        "",
        "## 1. 结论摘要",
        "",
        f"- 基准时长 {base['duration_h']:g} h：容量电价毛收入 {_wan(base['capacity_gross_cny'])} 万元/年，"
        f"考核扣减 {_wan(base['assessment_deduction_cny'])} 万元，净额 {_wan(base['capacity_net_cny'])} 万元。",
        f"- 电能量套利净收益（期望）{_wan(base['arbitrage_net_cny'])} 万元/年；"
        f"项目年收入 {_wan(base['revenue_cny'])} 万元，年运营支出 {_wan(base['opex_cny'])} 万元。",
        f"- 资本金投入 {_wan(base['capex_cny'])} 万元；NPV（{_pct(asset['discount_rate'])}）"
        f"{_wan(base['npv_cny'])} 万元，IRR {_pct(base['irr'])}，静态回收期 "
        f"{_years(base['payback_years'])}，LCOS {base['lcos_cny_per_mwh']:.1f} 元/MWh。",
        f"- 情景期望年运营净额（税前）{_wan(expected_total)} 万元；CVaR（置信 "
        f"{_pct(policy['scenario_cvar_confidence'])}，最差 {_pct(1 - policy['scenario_cvar_confidence'])} 均值）"
        f"{_wan(cvar)} 万元。",
        f"- 可用率考核：{base['strikes']} 次低于 {_pct(config['rules']['capacity']['assessment']['output_threshold_ratio'])}，"
        f"上限 {base['strike_limit']} 次；{'已触发全额扣减' if base['capacity_zeroed'] else '未触发全额扣减'}。",
        "",
        "## 2. 输入口径",
        "",
        "| 项目 | 数值 | 口径 |",
        "| --- | --- | --- |",
        f"| 装机功率 | {asset['power_mw']:g} MW | 交流侧 |",
        f"| 额定能量 | {asset['energy_mwh']:g} MWh | 直流侧，{base['duration_h']:g} h |",
        f"| 可用能量 | {asset['usable_energy_mwh']:g} MWh | SOC {asset['soc_min']:g}–{asset['soc_max']:g} |",
        f"| RTE | {_pct(asset['rte'])} | AC-AC，单程效率按平方根拆分 |",
        f"| 年运行天数 | {policy['operating_days']:g} 天 | 已含可用率，不再二次折算 |",
        f"| 日循环 | {policy['cycles_per_day']:g} 次 | 全年同口径 |",
        f"| 容量电价 | {config['rules']['capacity']['price_cny_per_kw_year']:g} 元/kW·年 | 6 h 分母，{base['duration_h']:g} h 折算 {base['capacity_ratio']:.4f} |",
        "",
        "## 3. 时长阶梯",
        "",
        "| 时长 | 能量 | 资本开支（万元） | 容量电费毛额（万元） | 容量净额（万元） | 套利净额（万元） | NPV（万元） | IRR | 回收期 | LCOS（元/MWh） |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in ladder:
        payback = "—" if row["payback_years"] is None else f"{row['payback_years']:.2f}"
        lines.append(
            f"| {row['duration_h']:g} h | {row['energy_mwh']:g} MWh | {_wan(row['capex_cny'])} | "
            f"{_wan(row['capacity_gross_cny'])} | {_wan(row['capacity_net_cny'])} | "
            f"{_wan(row['arbitrage_net_cny'])} | {_wan(row['npv_cny'])} | {_pct(row['irr'])} | "
            f"{payback} | {row['lcos_cny_per_mwh']:.1f} |"
        )
    lines += [
        "",
        "解读：526 号按 6 h 分母线性折算，2 h 项目只能拿到 1/3 容量电价，短时长更依赖现货价差；"
        "6 h 项目的容量电费绝对值最高，但资本开支也同比例上升，阶梯比较的是单位价值而非绝对收益。",
        "",
        "## 4. 情景与尾部",
        "",
        "| 情景 | 权重 | 充电价 | 放电价 | 套利净额（万元） | 容量净额（万元） | 年运营净额（税前，万元） |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in scenario_table:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['charge_price']:.0f} | "
            f"{item['discharge_price']:.0f} | {_wan(item['arbitrage_net_cny'])} | "
            f"{_wan(item['capacity_net_cny'])} | {_wan(item['total_net_cny'])} |"
        )
    lines += [
        "",
        f"情景充放价按同一情景配对使用，不跨情景混用分位。CVaR 取最差 {_pct(1 - policy['scenario_cvar_confidence'])} 概率质量的平均。",
        "",
        "## 5. 可用率考核",
        "",
        "| 月份 | 可用率 | 相对 98% 缺口 | 扣减（万元） | 累计未达标次数 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for month in assessment:
        lines.append(
            f"| {month['month']} | {_pct(month['availability_ratio'])} | {_pct(month['shortfall_ratio'])} | "
            f"{_wan(month['deduction_cny'])} | {month['strikes_cumulative']} |"
        )
    lines += [
        "",
        f"扣减公式为 D 级简化：月度扣减 = 月度容量电费 × max(0, 1 − 可用率/0.98)。"
        f"本算例累计 {base['strikes']} 次未达标，距离第 {base['strike_limit']} 次全额扣减"
        f"仅剩 {max(base['strike_limit'] - base['strikes'], 0)} 次，可用率管理是容量电费的生命线。",
        "",
        "## 6. 使用与改数",
        "",
        "```bash",
        "python make_demo.py",
        "python run.py --demo",
        "python run.py --check-config",
        "python run.py --scenarios 我的情景.csv --assessment 我的可用率.csv --out out/my-case",
        "```",
        "",
        "替换真实数据时，保持 `instance.json` 的六块结构与字段名不变；规则参数改 `rules`，"
        "项目参数改 `asset`，风格假设改 `policy` 并保留旧 `profile_id`。",
        "",
        "## 7. 边界与声明",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        "- v1 不含辅助服务、容量租赁、绿证与税费优惠；容量电费与现货收益分账。",
        "- 本复核单是 D 级合成样板，不构成投资、报价或法律建议。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, scenarios_path, assessment_path, out_dir):
    config = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    report = validate_instance(config)
    scenarios = read_scenarios(scenarios_path, config)
    assessment_rows = read_assessment(assessment_path, config)
    out_dir.mkdir(parents=True, exist_ok=True)

    policy = config["policy"]
    duration = policy["duration_h"]
    ladder = build_ladder(config, scenarios, assessment_rows)
    base = next(row for row in ladder if row["duration_h"] == duration)
    capacity = capacity_case(config, duration, assessment_rows)

    scenario_table = build_scenario_table(config, scenarios, duration, capacity["net_cny"])
    expected_total = sum(item["weight"] * item["total_net_cny"] for item in scenario_table)
    cvar = weighted_cvar(
        [(item["weight"], item["total_net_cny"]) for item in scenario_table],
        policy["scenario_cvar_confidence"],
    )
    fingerprint = hashlib.sha1(
        json.dumps(policy, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]

    ladder_rows = []
    for row in ladder:
        ladder_rows.append({key: value for key, value in row.items() if key != "cashflows"})
    _write_csv(
        out_dir / "duration_ladder.csv",
        ladder_rows,
        [
            "duration_h",
            "power_mw",
            "energy_mwh",
            "usable_energy_mwh",
            "capex_cny",
            "capacity_ratio",
            "capacity_gross_cny",
            "assessment_deduction_cny",
            "capacity_net_cny",
            "strikes",
            "strike_limit",
            "capacity_zeroed",
            "arbitrage_gross_cny",
            "degradation_cny",
            "arbitrage_net_cny",
            "charge_cost_cny",
            "fixed_opex_cny",
            "revenue_cny",
            "opex_cny",
            "npv_cny",
            "irr",
            "payback_years",
            "lcos_cny_per_mwh",
        ],
    )
    _write_csv(
        out_dir / "scenario_stack.csv",
        scenario_table,
        [
            "scenario",
            "weight",
            "charge_price",
            "discharge_price",
            "arbitrage_net_cny",
            "capacity_net_cny",
            "total_net_cny",
        ],
    )
    _write_csv(
        out_dir / "assessment.csv",
        capacity["months"],
        ["month", "availability_ratio", "shortfall_ratio", "deduction_cny", "strikes_cumulative"],
    )

    cashflow_rows = [{"year": 0, "revenue_cny": 0.0, "opex_cny": 0.0, "ebit_cny": 0.0, "tax_cny": 0.0, "net_cashflow_cny": -base["capex_cny"]}]
    depreciation = base["capex_cny"] / config["asset"]["project_years"]
    for year, net in enumerate(base["cashflows"][1:], start=1):
        ebit = base["revenue_cny"] - base["opex_cny"] - depreciation
        tax = max(ebit, 0.0) * config["asset"]["tax_rate"]
        cashflow_rows.append(
            {
                "year": year,
                "revenue_cny": base["revenue_cny"],
                "opex_cny": base["opex_cny"],
                "ebit_cny": ebit,
                "tax_cny": tax,
                "net_cashflow_cny": net,
            }
        )
    _write_csv(
        out_dir / "cashflow.csv",
        cashflow_rows,
        ["year", "revenue_cny", "opex_cny", "ebit_cny", "tax_cny", "net_cashflow_cny"],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": policy,
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "inputs": {
            "scenarios": len(scenarios),
            "scenario_weight_sum": sum(item["weight"] for item in scenarios),
            "assessment_months": len(assessment_rows),
        },
        "scenario_metrics": {
            "expected_annual_net_cny": expected_total,
            "cvar_cny": cvar,
            "cvar_confidence": policy["scenario_cvar_confidence"],
            "best_scenario": max(scenario_table, key=lambda item: item["total_net_cny"])["scenario"],
            "worst_scenario": min(scenario_table, key=lambda item: item["total_net_cny"])["scenario"],
            "scenarios": scenario_table,
        },
        "base_case": {
            "duration_h": duration,
            "capex_cny": base["capex_cny"],
            "capacity_gross_cny": base["capacity_gross_cny"],
            "assessment_deduction_cny": base["assessment_deduction_cny"],
            "capacity_net_cny": base["capacity_net_cny"],
            "strikes": base["strikes"],
            "strike_limit": base["strike_limit"],
            "capacity_zeroed": base["capacity_zeroed"],
            "arbitrage_gross_cny": base["arbitrage_gross_cny"],
            "degradation_cny": base["degradation_cny"],
            "arbitrage_net_cny": base["arbitrage_net_cny"],
            "revenue_cny": base["revenue_cny"],
            "opex_cny": base["opex_cny"],
            "npv_cny": base["npv_cny"],
            "irr": base["irr"],
            "payback_years": base["payback_years"],
            "lcos_cny_per_mwh": base["lcos_cny_per_mwh"],
        },
        "duration_ladder": ladder_rows,
        "warnings": report["warnings"],
        "files": [
            "duration_ladder.csv",
            "scenario_stack.csv",
            "assessment.csv",
            "cashflow.csv",
            "review.md",
        ],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(
        out_dir / "review.md",
        config,
        report,
        scenarios,
        ladder,
        scenario_table,
        capacity["months"],
        fingerprint,
    )
    return {"summary": summary, "out_dir": out_dir}


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Anhui standalone-storage capacity-price instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--scenarios", help="annual scenario CSV (scenario, charge_price, discharge_price, weight)")
    parser.add_argument("--assessment", help="monthly availability CSV (month, availability_ratio)")
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
        scenarios_path = _resolve_data(config, "scenarios")
        assessment_path = _resolve_data(config, "assessment")
        out_dir = Path(args.out) if args.out != str(HERE / "out") else HERE / "out" / "demo"
    else:
        if not args.scenarios or not args.assessment:
            print("必须同时提供 --scenarios 与 --assessment，或使用 --demo", file=sys.stderr)
            return 1
        scenarios_path = Path(args.scenarios)
        assessment_path = Path(args.assessment)
        out_dir = Path(args.out)

    try:
        result = run_instance(args.instance, scenarios_path, assessment_path, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    base = summary["base_case"]
    print(f"实例：{summary['instance_id']} / 基准 {base['duration_h']:g} h")
    print(
        f"容量电费：毛额 {_wan(base['capacity_gross_cny'])} 万元，"
        f"考核扣减 {_wan(base['assessment_deduction_cny'])} 万元，"
        f"净额 {_wan(base['capacity_net_cny'])} 万元（{base['strikes']}/{base['strike_limit']} 次）"
    )
    print(
        f"套利净额 {_wan(base['arbitrage_net_cny'])} 万元；NPV {_wan(base['npv_cny'])} 万元，"
        f"IRR {_pct(base['irr'])}，回收期 {_years(base['payback_years'])}，"
        f"LCOS {base['lcos_cny_per_mwh']:.1f} 元/MWh"
    )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
