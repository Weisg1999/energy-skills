#!/usr/bin/env python3
"""Run the Guangdong standalone-storage revenue-stacking instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the Guangdong spot rules, the frequency-regulation
  parameter set, the asset, the policy profile, contract boundaries and the
  data contract.
* ``data/scenarios_demo.csv`` is a five-scenario annual spot price set.
* ``data/frequency_demo.csv`` is a twelve-month mileage and K-factor record.
* ``data/availability_demo.csv`` is a twelve-month availability record.

Revenue is built from two lines only: spot arbitrage and frequency regulation.
The provincial capacity price for independent storage is not verified in the
knowledge base, so it is explicitly excluded; the review sheet reports the
mathematical revenue gap instead of inventing a capacity payment.

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
DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


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
    frequency_rule = _rule_block(rules, "frequency_regulation", report)
    capacity = _rule_block(rules, "capacity", report)
    _rule_block(rules, "participation", report)
    _rule_block(rules, "settlement", report)

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = _integer(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1)
    if abs(24 * 60 / mtu - points) > 1e-9:
        raise ConfigError(f"rules.spot.points_per_day ({points}) does not match 24*60/{mtu:g}")
    if points != 96:
        raise ConfigError("Guangdong spot uses 96 fifteen-minute points per day")
    floor = _number(
        _need(spot, "price_floor_cny_per_mwh", "rules.spot"),
        "rules.spot.price_floor_cny_per_mwh",
    )
    cap = _number(
        _need(spot, "price_cap_cny_per_mwh", "rules.spot"),
        "rules.spot.price_cap_cny_per_mwh",
    )
    if not floor < cap:
        raise ConfigError("rules.spot price floor must be below the cap")
    if floor > 0 or cap <= 0:
        raise ConfigError("rules.spot price band must straddle zero for this market")

    frequency_capacity_price = _number(
        _need(frequency_rule, "capacity_price_cny_per_mw_h", "rules.frequency_regulation"),
        "rules.frequency_regulation.capacity_price_cny_per_mw_h",
        0.0,
    )
    frequency_mileage_price = _number(
        _need(frequency_rule, "mileage_price_cny_per_mw", "rules.frequency_regulation"),
        "rules.frequency_regulation.mileage_price_cny_per_mw",
        0.0,
    )
    k_min = _number(
        _need(frequency_rule, "k_factor_min", "rules.frequency_regulation"),
        "rules.frequency_regulation.k_factor_min",
        0.0,
    )
    k_max = _number(
        _need(frequency_rule, "k_factor_max", "rules.frequency_regulation"),
        "rules.frequency_regulation.k_factor_max",
        k_min,
    )
    if not k_min < k_max:
        raise ConfigError("rules.frequency_regulation.k_factor_max must exceed k_factor_min")

    if _need(capacity, "included", "rules.capacity") is not False:
        raise ConfigError(
            "rules.capacity.included must be false: the Guangdong storage capacity price is not verified"
        )
    if capacity.get("price_cny_per_kw_year") is not None:
        raise ConfigError(
            "rules.capacity.price_cny_per_kw_year must stay null while the provincial policy is unverified"
        )

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
    degradation = _number(
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
    duration = _number(_need(policy, "duration_h", "policy"), "policy.duration_h", 1e-9)
    if duration not in DURATIONS_H:
        raise ConfigError("policy.duration_h must be one of 2/4/6 h")
    cycles = _number(_need(policy, "cycles_per_day", "policy"), "policy.cycles_per_day", 0.0, 10.0)
    days = _number(_need(policy, "operating_days", "policy"), "policy.operating_days", 0.0, 365.0)
    reserve = _number(
        _need(policy, "frequency_reserve_mw", "policy"),
        "policy.frequency_reserve_mw",
        0.0,
    )
    if reserve >= power:
        raise ConfigError("policy.frequency_reserve_mw must be below asset.power_mw")
    haircut = _number(
        _need(policy, "stack_haircut", "policy"),
        "policy.stack_haircut",
        0.0,
        1.0,
    )
    if haircut >= 1.0:
        raise ConfigError("policy.stack_haircut must be < 1")
    confidence = _number(
        _need(policy, "scenario_cvar_confidence", "policy"),
        "policy.scenario_cvar_confidence",
        0.0,
        1.0,
    )
    if not 0 < confidence < 1:
        raise ConfigError("policy.scenario_cvar_confidence must be in (0, 1)")

    registration = _need(contracts, "frequency_registration", "contracts")
    if _need(registration, "registered", "contracts.frequency_registration") is not True:
        raise ConfigError("contracts.frequency_registration.registered must be true for this pack")
    if _need(contracts, "capacity_listing", "contracts.capacity_listing").get("included") is not False:
        raise ConfigError("contracts.capacity_listing.included must be false")
    if _need(contracts, "lease", "contracts.lease").get("included") is not False:
        raise ConfigError("contracts.lease.included must be false in v1")

    scenario_contract = _need(data_contract, "scenarios", "data_contract")
    frequency_contract = _need(data_contract, "frequency", "data_contract")
    availability_contract = _need(data_contract, "availability", "data_contract")
    for item, name in (
        (scenario_contract, "scenarios"),
        (frequency_contract, "frequency"),
        (availability_contract, "availability"),
    ):
        _text(item, "file", f"data_contract.{name}")
        fields = _need(item, "required_fields", f"data_contract.{name}")
        if not isinstance(fields, list) or not fields:
            raise ConfigError(f"data_contract.{name}.required_fields must be a non-empty list")
    if _integer(
        _need(scenario_contract, "scenario_count", "data_contract.scenarios"),
        "data_contract.scenarios.scenario_count",
        1,
    ) != 5:
        raise ConfigError("data_contract.scenarios.scenario_count must be 5 for this demo contract")
    for name in ("frequency", "availability"):
        if _integer(
            _need(data_contract[name], "months", f"data_contract.{name}"),
            f"data_contract.{name}.months",
            1,
        ) != MONTHS_EXPECTED:
            raise ConfigError(f"data_contract.{name}.months must be {MONTHS_EXPECTED}")

    report["checks"].append(
        {
            "points_per_day": points,
            "mtu_min": mtu,
            "price_floor": floor,
            "price_cap": cap,
            "frequency_capacity_price": frequency_capacity_price,
            "frequency_mileage_price": frequency_mileage_price,
            "k_min": k_min,
            "k_max": k_max,
            "power_mw": power,
            "energy_mwh": energy,
            "usable_energy_mwh": usable,
            "rte": rte,
            "degradation_cny_per_mwh_throughput": degradation,
            "fixed_opex_cny_per_year": fixed_opex,
            "capex_cny_per_kwh": capex_per_kwh,
            "project_years": years,
            "discount_rate": discount,
            "tax_rate": tax_rate,
            "duration_h": duration,
            "cycles_per_day": cycles,
            "operating_days": days,
            "frequency_reserve_mw": reserve,
            "stack_haircut": haircut,
            "cvar_confidence": confidence,
        }
    )
    report["warnings"].append("调频价格与 K 值为 D 级示例，不是广东调频市场正式参数")
    report["warnings"].append("独立储能容量电价/容量补偿未闭环，本包明确不计容量收入")
    report["warnings"].append("现货情景是年度代表价对，不是节点价时序；15 分钟 SOC 策略未逐点优化")
    report["warnings"].append("调频毛收入未扣额外退化与考核，用统一 5% 叠加折减近似")
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


def _month_index(value, path):
    text = (value or "").strip()
    parts = text.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise ConfigError(f"{path} must be YYYY-MM, got {value!r}")
    month = _integer(parts[1], f"{path} month", 1)
    if month > 12:
        raise ConfigError(f"{path} month must be 1-12")
    return month


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
        floor = config["rules"]["spot"]["price_floor_cny_per_mwh"]
        cap = config["rules"]["spot"]["price_cap_cny_per_mwh"]
        for label, value in (("charge_price", charge), ("discharge_price", discharge)):
            if value < floor - 1e-9 or value > cap + 1e-9:
                raise ConfigError(
                    f"scenario {name}.{label} {value:g} is outside the spot price band "
                    f"[{floor:g}, {cap:g}]"
                )
        scenarios.append(
            {
                "scenario": name,
                "charge_price": charge,
                "discharge_price": discharge,
                "weight": weight,
            }
        )
    if len(scenarios) != int(contract["scenario_count"]):
        raise ConfigError(f"expected {contract['scenario_count']} scenarios, got {len(scenarios)}")
    total_weight = sum(item["weight"] for item in scenarios)
    if abs(total_weight - 1.0) > 1e-6:
        raise ConfigError(f"scenario weights must sum to 1, got {total_weight:g}")
    return scenarios


def read_frequency(path, config):
    """Read the monthly frequency mileage and K-factor record."""
    contract = config["data_contract"]["frequency"]
    rows = _read_rows(path)
    _require_fields(rows, contract["required_fields"], "frequency")
    k_min = config["rules"]["frequency_regulation"]["k_factor_min"]
    k_max = config["rules"]["frequency_regulation"]["k_factor_max"]
    records = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        month = (row.get("month") or "").strip()
        if not month:
            raise ConfigError(f"frequency row {index} has an empty month")
        if month in seen:
            raise ConfigError(f"duplicate frequency month: {month}")
        seen.add(month)
        _month_index(month, f"frequency row {index}.month")
        mileage = _number(
            row.get("mileage_mw_per_day"),
            f"frequency {month}.mileage_mw_per_day",
            0.0,
        )
        k_factor = _number(
            row.get("k_factor"), f"frequency {month}.k_factor", k_min, k_max
        )
        records.append({"month": month, "mileage_mw_per_day": mileage, "k_factor": k_factor})
    if len(records) != MONTHS_EXPECTED:
        raise ConfigError(f"expected {MONTHS_EXPECTED} frequency months, got {len(records)}")
    return records


def read_availability(path, config):
    """Read the monthly availability record."""
    contract = config["data_contract"]["availability"]
    rows = _read_rows(path)
    _require_fields(rows, contract["required_fields"], "availability")
    records = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        month = (row.get("month") or "").strip()
        if not month:
            raise ConfigError(f"availability row {index} has an empty month")
        if month in seen:
            raise ConfigError(f"duplicate availability month: {month}")
        seen.add(month)
        _month_index(month, f"availability row {index}.month")
        ratio = _number(
            row.get("availability_ratio"),
            f"availability {month}.availability_ratio",
            0.0,
            1.0,
        )
        records.append({"month": month, "availability_ratio": ratio})
    if len(records) != MONTHS_EXPECTED:
        raise ConfigError(f"expected {MONTHS_EXPECTED} availability months, got {len(records)}")
    return records


def arbitrage_case(config, charge_price, discharge_price, annual_availability):
    """Annual spot arbitrage after reserving power for frequency regulation."""
    asset = config["asset"]
    policy = config["policy"]
    power = asset["power_mw"] - policy["frequency_reserve_mw"]
    usable_ratio = asset["usable_energy_mwh"] / asset["energy_mwh"]
    return stacking.arbitrage(
        power_mw=power,
        duration_h=policy["duration_h"],
        rte=asset["rte"],
        cycles_per_day=policy["cycles_per_day"],
        days=policy["operating_days"],
        charge_price=charge_price,
        discharge_price=discharge_price,
        usable_ratio=usable_ratio,
        availability=annual_availability,
        degradation_cost_per_kwh=asset["degradation_cny_per_mwh_throughput"] / 1000.0,
    )


def frequency_case(config, frequency_rows, availability_rows):
    """Monthly frequency capacity and mileage revenue, gross of extra degradation."""
    rule = config["rules"]["frequency_regulation"]
    policy = config["policy"]
    availability = {row["month"]: row["availability_ratio"] for row in availability_rows}
    monthly = []
    capacity_total = 0.0
    mileage_total = 0.0
    for row in frequency_rows:
        if row["month"] not in availability:
            raise ConfigError(f"frequency month {row['month']} has no availability record")
        month_number = _month_index(row["month"], "frequency.month")
        days = DAYS_IN_MONTH[month_number - 1]
        ratio = availability[row["month"]]
        capacity_daily = policy["frequency_reserve_mw"] * rule["capacity_price_cny_per_mw_h"] * 24
        mileage_daily = (
            row["mileage_mw_per_day"] * rule["mileage_price_cny_per_mw"] * row["k_factor"]
        )
        result = stacking.frequency_regulation(
            capacity_mw=policy["frequency_reserve_mw"],
            capacity_price_per_mw_h=rule["capacity_price_cny_per_mw_h"],
            mileage_mw_per_day=row["mileage_mw_per_day"],
            mileage_price_per_mw=rule["mileage_price_cny_per_mw"],
            k_factor=row["k_factor"],
            days=days,
            availability=ratio,
        )
        expected = (capacity_daily + mileage_daily) * days * ratio
        if abs(result["annual"] - expected) > 1e-6 * max(1.0, expected):
            raise ConfigError(f"frequency kernel mismatch for {row['month']}")
        capacity_month = capacity_daily * days * ratio
        mileage_month = mileage_daily * days * ratio
        capacity_total += capacity_month
        mileage_total += mileage_month
        monthly.append(
            {
                "month": row["month"],
                "days": days,
                "mileage_mw_per_day": row["mileage_mw_per_day"],
                "k_factor": row["k_factor"],
                "availability_ratio": ratio,
                "capacity_revenue_cny": capacity_month,
                "mileage_revenue_cny": mileage_month,
                "total_cny": result["annual"],
            }
        )
    return {
        "capacity_cny": capacity_total,
        "mileage_cny": mileage_total,
        "annual_cny": capacity_total + mileage_total,
        "months": monthly,
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


def build_stack(config, scenarios, frequency, availability):
    """Annual revenue stack, scenario tail and financial metrics."""
    asset = config["asset"]
    policy = config["policy"]
    annual_availability = sum(row["availability_ratio"] for row in availability) / len(availability)
    arbitrage = [
        arbitrage_case(config, item["charge_price"], item["discharge_price"], annual_availability)
        for item in scenarios
    ]
    arbitrage_gross = _weighted_mean(
        [
            {"weight": item["weight"], "value": result["annual_gross"]}
            for item, result in zip(scenarios, arbitrage)
        ],
        "value",
    )
    degradation_cost = arbitrage[0]["annual_degradation_cost"]
    arbitrage_net = arbitrage_gross - degradation_cost
    frequency_gross = frequency["annual_cny"]

    stacked = stacking.stack(
        {"arbitrage": arbitrage_gross, "frequency": frequency_gross},
        haircut=float(policy["stack_haircut"]),
    )
    fixed_opex = asset["fixed_opex_cny_per_year"]
    opex = fixed_opex + degradation_cost
    operating_net = stacked["net"] - opex

    cycles = policy["cycles_per_day"] * policy["operating_days"] * annual_availability
    discharge_mwh = arbitrage[0]["discharge_mwh_per_cycle"] * cycles
    charge_mwh = arbitrage[0]["charge_mwh_per_cycle"] * cycles
    weighted_charge_price = _weighted_mean(scenarios, "charge_price")
    charge_cost = charge_mwh * weighted_charge_price

    capex = asset["power_mw"] * policy["duration_h"] * 1000.0 * asset["capex_cny_per_kwh"]
    cashflows = finance.annual_cashflow(
        revenue=stacked["net"],
        opex=opex,
        capex=capex,
        years=asset["project_years"],
        tax_rate=asset["tax_rate"],
        depreciation_years=asset["project_years"],
    )
    npv = finance.npv(asset["discount_rate"], cashflows)

    def npv_with_gap(gap):
        trial = finance.annual_cashflow(
            revenue=stacked["net"] + gap,
            opex=opex,
            capex=capex,
            years=asset["project_years"],
            tax_rate=asset["tax_rate"],
            depreciation_years=asset["project_years"],
        )
        return finance.npv(asset["discount_rate"], trial)

    capacity_gap = 0.0
    if npv < 0:
        low, high = 0.0, max(1.0, -npv)
        while npv_with_gap(high) < 0:
            high *= 2.0
        for _ in range(100):
            mid = (low + high) / 2.0
            if npv_with_gap(mid) < 0:
                low = mid
            else:
                high = mid
        capacity_gap = (low + high) / 2.0

    scenario_rows = []
    for item, result in zip(scenarios, arbitrage):
        gross = result["annual_gross"] + frequency_gross
        net = gross * (1.0 - float(policy["stack_haircut"]))
        scenario_rows.append(
            {
                "scenario": item["scenario"],
                "weight": item["weight"],
                "charge_price": item["charge_price"],
                "discharge_price": item["discharge_price"],
                "arbitrage_gross_cny": result["annual_gross"],
                "arbitrage_degradation_cny": result["annual_degradation_cost"],
                "arbitrage_net_cny": result["annual_net"],
                "frequency_gross_cny": frequency_gross,
                "stack_net_cny": net,
                "opex_cny": opex,
                "operating_net_cny": net - opex,
                "capacity_cny": 0.0,
            }
        )
    cvar = weighted_cvar(
        [(row["weight"], row["operating_net_cny"]) for row in scenario_rows],
        float(policy["scenario_cvar_confidence"]),
    )

    return {
        "annual_availability": annual_availability,
        "arbitrage_gross_cny": arbitrage_gross,
        "arbitrage_degradation_cny": degradation_cost,
        "arbitrage_net_cny": arbitrage_net,
        "frequency_gross_cny": frequency_gross,
        "frequency_capacity_cny": frequency["capacity_cny"],
        "frequency_mileage_cny": frequency["mileage_cny"],
        "stack_gross_cny": stacked["gross"],
        "stack_net_cny": stacked["net"],
        "stack_haircut": stacked["haircut"],
        "fixed_opex_cny": fixed_opex,
        "opex_cny": opex,
        "operating_net_cny": operating_net,
        "discharge_mwh": discharge_mwh,
        "charge_mwh": charge_mwh,
        "charge_cost_cny": charge_cost,
        "capex_cny": capex,
        "cashflows": cashflows,
        "npv_cny": npv,
        "irr": finance.irr(cashflows),
        "payback_years": finance.payback(cashflows),
        "lcos_cny_per_mwh": finance.lcos(
            capex=capex,
            annual_opex=opex,
            annual_charge_cost=charge_cost,
            annual_discharge_mwh=discharge_mwh,
            years=asset["project_years"],
            discount_rate=asset["discount_rate"],
        ),
        "capacity_gap_cny_per_year": capacity_gap,
        "capacity_gap_cny_per_kw_year": capacity_gap / (asset["power_mw"] * 1000.0),
        "scenario_rows": scenario_rows,
        "expected_operating_net_cny": _weighted_mean(scenario_rows, "operating_net_cny"),
        "cvar_cny": cvar,
        "frequency_months": frequency["months"],
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
        if field == "irr":
            return f"{value:.6f}"
        return f"{value:.2f}"
    return value


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _wan(value):
    return "—" if value is None else f"{value / 10000.0:,.2f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def _years(value):
    return "—" if value is None else f"{value:.2f} 年"


def write_review(path, config, report, stack, fingerprint):
    policy = config["policy"]
    asset = config["asset"]
    lines = [
        "# 广东独立储能 · 现货 + 调频收益叠加复核表",
        "",
        f"- 实例：`{config['meta']['instance_id']}`",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 策略档：`{policy['profile_id']}` / 指纹 `{fingerprint}`",
        f"- 资产：{asset['power_mw']:.0f} MW / {asset['energy_mwh']:.0f} MWh，"
        f"可用 {asset['usable_energy_mwh']:.0f} MWh，RTE {asset['rte']:.2f}",
        f"- 调频预留：{policy['frequency_reserve_mw']:.0f} MW；现货日循环 {policy['cycles_per_day']:.2f} 次、"
        f"年运行 {policy['operating_days']:.0f} 天；叠加折减 {policy['stack_haircut'] * 100:.1f}%",
        "- **容量收入：未纳入。** 广东独立储能容量电价/容量补偿的省级文件未在本库闭环，"
        "煤电 165 元/kW·年不得套用。",
        "- 全部数据为 D 级合成，不对应任何真实电站、合同或结算单。",
        "",
        "## 1. 规则来源与未核实项",
        "",
        "| 规则块 | 级别 | 来源 | 状态 |",
        "|---|---|---|---|",
    ]
    for item in report["provenance"]:
        block = item["block"].split(".", 1)[1]
        status = config["rules"][block].get("status", "—")
        lines.append(f"| {item['block']} | {item['grade']} | {item['source']} | {status} |")

    lines += [
        "",
        "## 2. 年度收益叠加",
        "",
        "| 项目 | 金额（万元/年） |",
        "|---|---:|",
        f"| 现货套利毛额 | {_wan(stack['arbitrage_gross_cny'])} |",
        f"| 现货退化成本 | {_wan(stack['arbitrage_degradation_cny'])} |",
        f"| 现货套利净额 | {_wan(stack['arbitrage_net_cny'])} |",
        f"| 调频容量收入（毛） | {_wan(stack['frequency_capacity_cny'])} |",
        f"| 调频里程收入（毛） | {_wan(stack['frequency_mileage_cny'])} |",
        f"| 调频毛收入合计 | {_wan(stack['frequency_gross_cny'])} |",
        f"| 叠加毛额（套利 + 调频） | {_wan(stack['stack_gross_cny'])} |",
        f"| 叠加折减 {policy['stack_haircut'] * 100:.1f}% | {_wan(stack['stack_gross_cny'] - stack['stack_net_cny'])} |",
        f"| 叠加净额 | {_wan(stack['stack_net_cny'])} |",
        f"| 固定运维 | {_wan(stack['fixed_opex_cny'])} |",
        f"| 运营支出合计（固定运维 + 退化） | {_wan(stack['opex_cny'])} |",
        f"| 税前运营净额 | {_wan(stack['operating_net_cny'])} |",
        f"| 资本开支（{asset['capex_cny_per_kwh']:.0f} 元/kWh） | {_wan(stack['capex_cny'])} |",
        f"| NPV @{asset['discount_rate'] * 100:.0f}% | {_wan(stack['npv_cny'])} |",
        f"| IRR | {_pct(stack['irr'])} |",
        f"| 静态回收期 | {_years(stack['payback_years'])} |",
        f"| LCOS（含充电成本，不含税与融资） | {stack['lcos_cny_per_mwh']:.1f} 元/MWh |",
        "",
        "读法：套利、调频、容量是三条线，必须分账。调频毛收入未扣额外退化、考核与机会成本，"
        "本包用统一叠加折减近似；不能把调频毛收入直接加到套利净额上。",
        "",
        "## 3. 情景与尾部",
        "",
        "| 情景 | 充电价 | 放电价 | 权重 | 套利净额（万元） | 叠加净额（万元） | 税前运营净额（万元） |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stack["scenario_rows"]:
        lines.append(
            f"| {row['scenario']} | {row['charge_price']:.1f} | {row['discharge_price']:.1f} | "
            f"{row['weight']:.2f} | {_wan(row['arbitrage_net_cny'])} | {_wan(row['stack_net_cny'])} | "
            f"{_wan(row['operating_net_cny'])} |"
        )
    lines += [
        "",
        f"- 情景期望税前运营净额：{_wan(stack['expected_operating_net_cny'])} 万元/年；"
        f"CVaR（置信 {policy['scenario_cvar_confidence'] * 100:.0f}%）：{_wan(stack['cvar_cny'])} 万元/年。",
        "- 情景是年度充放价对，不是 15 分钟节点价时序；SOC 与 15 分钟策略未逐点优化。",
        "",
        "## 4. 调频月度",
        "",
        "| 月份 | 天数 | 日里程（MW） | K 值 | 可用率 | 容量收入（万元） | 里程收入（万元） | 合计（万元） |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stack["frequency_months"]:
        lines.append(
            f"| {row['month']} | {row['days']} | {row['mileage_mw_per_day']:.0f} | "
            f"{row['k_factor']:.2f} | {row['availability_ratio'] * 100:.1f}% | "
            f"{_wan(row['capacity_revenue_cny'])} | {_wan(row['mileage_revenue_cny'])} | "
            f"{_wan(row['total_cny'])} |"
        )
    lines += [
        "",
        "## 5. 容量收入缺口（指示值）",
        "",
    ]
    if stack["capacity_gap_cny_per_year"] > 0:
        lines += [
            f"若要把 NPV 拉到 0，当前假设下每年还需约 **{_wan(stack['capacity_gap_cny_per_year'])} 万元**"
            f"（折合 **{stack['capacity_gap_cny_per_kw_year']:.1f} 元/kW·年**）的容量性收入。",
            "",
            "这只是数学缺口，不是政策建议，也不代表广东存在独立储能容量电价或容量补偿；"
            "在省级文件与资格清单落地前，不得把它写进报价、融资模型或投资决策。",
        ]
    else:
        lines += [
            "当前假设下 NPV 已非负，不需要容量收入填补；这同样不代表容量政策存在。",
        ]
    lines += [
        "",
        "## 6. 三个复核问题",
        "",
        "1. 现货情景价差是否来自广东实际节点价？是否已按 15 分钟粒度、分季节复核，而不是只用年度均价？",
        "2. 预留调频后，套利功率与 SOC 是否还够？K 值下降、调频考核与额外退化会不会把毛收入打掉？",
        "3. 容量收入是否已核到省级文件、执行日期与资格清单？未确认前必须保持 `included: false`。",
        "",
        "## 7. 告警与边界",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        f"- {config['meta']['disclaimer']}",
        "- 本表是收益叠加测算，不是交易中心结算替代品，不是投资建议。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, scenarios_path, frequency_path, availability_path, out_dir):
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{instance_path.name} is not valid JSON: {exc}") from exc
    report = validate_instance(config)
    scenarios = read_scenarios(scenarios_path, config)
    frequency_rows = read_frequency(frequency_path, config)
    availability = read_availability(availability_path, config)
    frequency = frequency_case(config, frequency_rows, availability)
    stack = build_stack(config, scenarios, frequency, availability)

    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario_fields = [
        "scenario",
        "charge_price",
        "discharge_price",
        "weight",
        "arbitrage_gross_cny",
        "arbitrage_degradation_cny",
        "arbitrage_net_cny",
        "frequency_gross_cny",
        "stack_net_cny",
        "opex_cny",
        "operating_net_cny",
        "capacity_cny",
    ]
    _write_csv(out_dir / "scenario_stack.csv", stack["scenario_rows"], scenario_fields)
    _write_csv(
        out_dir / "frequency.csv",
        stack["frequency_months"],
        [
            "month",
            "days",
            "mileage_mw_per_day",
            "k_factor",
            "availability_ratio",
            "capacity_revenue_cny",
            "mileage_revenue_cny",
            "total_cny",
        ],
    )
    cashflow_rows = [
        {"year": year, "cashflow_cny": value}
        for year, value in enumerate(stack["cashflows"])
    ]
    _write_csv(out_dir / "cashflow.csv", cashflow_rows, ["year", "cashflow_cny"])

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "capacity_included": False,
        "annual_availability": stack["annual_availability"],
        "arbitrage_gross_cny": stack["arbitrage_gross_cny"],
        "arbitrage_degradation_cny": stack["arbitrage_degradation_cny"],
        "arbitrage_net_cny": stack["arbitrage_net_cny"],
        "frequency_gross_cny": stack["frequency_gross_cny"],
        "frequency_capacity_cny": stack["frequency_capacity_cny"],
        "frequency_mileage_cny": stack["frequency_mileage_cny"],
        "stack_net_cny": stack["stack_net_cny"],
        "opex_cny": stack["opex_cny"],
        "operating_net_cny": stack["operating_net_cny"],
        "discharge_mwh": stack["discharge_mwh"],
        "charge_mwh": stack["charge_mwh"],
        "charge_cost_cny": stack["charge_cost_cny"],
        "capex_cny": stack["capex_cny"],
        "npv_cny": stack["npv_cny"],
        "irr": stack["irr"],
        "payback_years": stack["payback_years"],
        "lcos_cny_per_mwh": stack["lcos_cny_per_mwh"],
        "capacity_gap_cny_per_year": stack["capacity_gap_cny_per_year"],
        "capacity_gap_cny_per_kw_year": stack["capacity_gap_cny_per_kw_year"],
        "expected_operating_net_cny": stack["expected_operating_net_cny"],
        "cvar_cny": stack["cvar_cny"],
        "scenarios": stack["scenario_rows"],
        "frequency_months": stack["frequency_months"],
        "warnings": report["warnings"],
        "files": [
            "scenario_stack.csv",
            "frequency.csv",
            "cashflow.csv",
            "review.md",
        ],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(out_dir / "review.md", config, report, stack, fingerprint)
    return {"summary": summary, "out_dir": out_dir}


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Guangdong storage revenue-stacking instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--scenarios", help="annual spot scenarios CSV")
    parser.add_argument("--frequency", help="monthly frequency record CSV")
    parser.add_argument("--availability", help="monthly availability CSV")
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
        frequency_path = _resolve_data(config, "frequency")
        availability_path = _resolve_data(config, "availability")
        out_dir = Path(args.out) if args.out != str(HERE / "out") else HERE / "out" / "demo"
    else:
        if not (args.scenarios and args.frequency and args.availability):
            print(
                "必须同时提供 --scenarios --frequency --availability，或使用 --demo",
                file=sys.stderr,
            )
            return 1
        scenarios_path = Path(args.scenarios)
        frequency_path = Path(args.frequency)
        availability_path = Path(args.availability)
        out_dir = Path(args.out)

    try:
        result = run_instance(
            args.instance, scenarios_path, frequency_path, availability_path, out_dir
        )
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(f"实例：{summary['instance_id']}")
    print(
        f"现货套利净额 {_wan(summary['arbitrage_net_cny'])} 万元；"
        f"调频毛收入 {_wan(summary['frequency_gross_cny'])} 万元；"
        f"叠加净额 {_wan(summary['stack_net_cny'])} 万元"
    )
    print(
        f"税前运营净额 {_wan(summary['operating_net_cny'])} 万元；"
        f"NPV {_wan(summary['npv_cny'])} 万元，IRR {_pct(summary['irr'])}，"
        f"回收期 {_years(summary['payback_years'])}，LCOS {summary['lcos_cny_per_mwh']:.1f} 元/MWh"
    )
    print("容量收入：未纳入（省级文件未闭环）")
    if summary["capacity_gap_cny_per_year"] > 0:
        print(
            f"容量缺口指示：若要把 NPV 拉到 0，每年还需 {_wan(summary['capacity_gap_cny_per_year'])} 万元"
            f" ≈ {summary['capacity_gap_cny_per_kw_year']:.1f} 元/kW·年"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
