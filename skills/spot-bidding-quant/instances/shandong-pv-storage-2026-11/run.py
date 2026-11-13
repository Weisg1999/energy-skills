#!/usr/bin/env python3
"""Run the Shandong PV-plus-storage joint-bidding instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the rule parameters, the PV/storage asset, the policy
  profile and the data contract. A trader edits it; no code change is needed
  for a new station or a new style profile.
* ``data/d1_demo.csv`` is a 96-point, five-scenario D-1 set. Price and PV carry
  the same scenario number, so a cloudy scenario is also a high-price scenario.
* ``data/t1_demo.csv`` is the T+1 actual price, PV, metered charge/discharge,
  export and curtailment.

The storage schedule is the existing ``ems-dispatch/tools/dispatch.py`` DP
kernel with ``load_kw=0`` and the PV curve as the only supply. The grid import
limit is zero because the 2026-08-27 Shandong notice requires co-located
storage to charge from the matched PV station, not from the public grid.

The joint entity declares one net-export curve, not two separate asset curves:
``net = PV - charge + discharge``. The pack answers three questions the
standalone storage pack cannot: how much midday PV to curtail, how much to
store, and how much net position to declare.

All bundled numbers are synthetic grade D. They are not a market forecast, a
live trading signal or investment advice.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parents[1]
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(SKILL_DIR / "tools"))

import desk  # noqa: E402


class ConfigError(ValueError):
    """Raised when the instance or an input file fails validation."""


def _load_kernel():
    path = REPO_ROOT / "skills" / "ems-dispatch" / "tools" / "dispatch.py"
    if not path.exists():
        raise ConfigError(f"missing EMS dispatch kernel: {path}")
    spec = importlib.util.spec_from_file_location("ems_dispatch_kernel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KERNEL = _load_kernel()


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


def validate_instance(config):
    """Validate the six blocks and return a provenance report."""
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot")
    _rule_block(rules, "settlement")
    joint = _rule_block(rules, "new_energy_participation")
    storage_rule = _rule_block(rules, "storage_participation")
    capacity = _rule_block(rules, "capacity_compensation")

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = int(_number(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1))
    expected_points = 24 * 60 / mtu
    if abs(expected_points - points) > 1e-9:
        raise ConfigError(
            f"rules.spot.points_per_day ({points}) does not match 24*60/{mtu:g}"
        )
    declare_floor = _number(
        _need(spot, "declare_floor_cny_per_mwh", "rules.spot"),
        "rules.spot.declare_floor_cny_per_mwh",
    )
    declare_cap = _number(
        _need(spot, "declare_cap_cny_per_mwh", "rules.spot"),
        "rules.spot.declare_cap_cny_per_mwh",
    )
    clear_floor = _number(
        _need(spot, "clear_floor_cny_per_mwh", "rules.spot"),
        "rules.spot.clear_floor_cny_per_mwh",
    )
    clear_cap = _number(
        _need(spot, "clear_cap_cny_per_mwh", "rules.spot"),
        "rules.spot.clear_cap_cny_per_mwh",
    )
    if not (clear_floor <= declare_floor < declare_cap <= clear_cap):
        raise ConfigError(
            "price bounds must satisfy clear_floor <= declare_floor < declare_cap <= clear_cap"
        )

    pv = _need(asset, "pv", "asset")
    pv_capacity = _number(_need(pv, "capacity_mw", "asset.pv"), "asset.pv.capacity_mw", 1e-9)
    _number(pv.get("availability", 1.0), "asset.pv.availability", 0.0, 1.0)
    storage = _need(asset, "storage", "asset")
    power = _number(_need(storage, "power_mw", "asset.storage"), "asset.storage.power_mw", 1e-9)
    energy = _number(_need(storage, "energy_mwh", "asset.storage"), "asset.storage.energy_mwh", 1e-9)
    rte = _number(_need(storage, "rte", "asset.storage"), "asset.storage.rte", 1e-9, 1.0)
    soc_min = _number(_need(storage, "soc_min", "asset.storage"), "asset.storage.soc_min", 0.0, 1.0)
    soc_max = _number(_need(storage, "soc_max", "asset.storage"), "asset.storage.soc_max", 0.0, 1.0)
    soc_init = _number(_need(storage, "soc_init", "asset.storage"), "asset.storage.soc_init", 0.0, 1.0)
    if not soc_min < soc_max:
        raise ConfigError("asset.storage.soc_min must be below soc_max")
    if not soc_min <= soc_init <= soc_max:
        raise ConfigError("asset.storage.soc_init must lie inside the SOC window")
    _number(
        _need(storage, "degradation_cny_per_mwh_throughput", "asset.storage"),
        "asset.storage.degradation_cny_per_mwh_throughput",
        0.0,
    )
    _number(storage.get("fixed_cost_cny_per_day", 0.0), "asset.storage.fixed_cost_cny_per_day", 0.0)
    states = int(_number(storage.get("solver_states", 120), "asset.storage.solver_states", 10))
    grid = _need(asset, "grid_connection", "asset")
    import_limit = _number(
        _need(grid, "import_limit_mw", "asset.grid_connection"),
        "asset.grid_connection.import_limit_mw",
        0.0,
    )
    export_limit = _number(
        _need(grid, "export_limit_mw", "asset.grid_connection"),
        "asset.grid_connection.export_limit_mw",
        0.0,
    )

    max_ratio = _number(
        _need(joint, "max_colocated_storage_ratio_pv", "rules.new_energy_participation"),
        "rules.new_energy_participation.max_colocated_storage_ratio_pv",
        0.0,
        1.0,
    )
    if power > pv_capacity * max_ratio + 1e-9:
        raise ConfigError(
            "asset.storage.power_mw exceeds the provincial co-located-storage cap "
            f"({max_ratio:.0%} of PV capacity)"
        )
    clearing_max_ratio = _number(
        _need(joint, "clearing_plan_max_ratio_of_pv_capacity", "rules.new_energy_participation"),
        "rules.new_energy_participation.clearing_plan_max_ratio_of_pv_capacity",
        0.0,
    )
    clearing_max = pv_capacity * clearing_max_ratio
    if export_limit > clearing_max + 1e-9:
        raise ConfigError(
            "asset.grid_connection.export_limit_mw exceeds the joint clearing-plan cap "
            f"({clearing_max:.1f} MW)"
        )
    grid_charge_allowed = _need(
        joint, "grid_charge_allowed", "rules.new_energy_participation"
    )
    if not isinstance(grid_charge_allowed, bool):
        raise ConfigError("rules.new_energy_participation.grid_charge_allowed must be true or false")
    if not grid_charge_allowed and import_limit > 1e-9:
        raise ConfigError(
            "配建储能不得从公共电网购电充电：grid_charge_allowed=false 时 import_limit_mw 必须为 0；"
            "若要做电网充电，请改用独立储能实例"
        )
    if grid_charge_allowed and import_limit <= 1e-9:
        raise ConfigError("grid_charge_allowed=true requires a positive import_limit_mw")

    bid_mode = _text(joint, "bid_mode_code", "rules.new_energy_participation")
    if bid_mode not in ("quantity_only", "price_quote"):
        raise ConfigError("rules.new_energy_participation.bid_mode_code must be quantity_only or price_quote")
    min_power = _number(
        _need(storage_rule, "min_power_mw", "rules.storage_participation"),
        "rules.storage_participation.min_power_mw",
        0.0,
    )
    min_duration = _number(
        _need(storage_rule, "min_duration_h", "rules.storage_participation"),
        "rules.storage_participation.min_duration_h",
        0.0,
    )
    if power < min_power - 1e-9:
        raise ConfigError("asset.storage.power_mw is below the provincial minimum")
    if energy / power < min_duration - 1e-9:
        raise ConfigError("asset.storage duration is below the provincial minimum")

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    qty_q = _number(
        _need(policy, "declared_quantity_quantile", "policy"),
        "policy.declared_quantity_quantile",
        0.0,
        1.0,
    )
    price_q = _number(
        _need(policy, "price_reference_quantile", "policy"),
        "policy.price_reference_quantile",
        0.0,
        1.0,
    )
    pv_q = _number(
        _need(policy, "pv_reference_quantile", "policy"),
        "policy.pv_reference_quantile",
        0.0,
        1.0,
    )
    _number(
        _need(policy, "discharge_markup_cny_per_mwh", "policy"),
        "policy.discharge_markup_cny_per_mwh",
        0.0,
    )
    _number(
        _need(policy, "charge_markup_cny_per_mwh", "policy"),
        "policy.charge_markup_cny_per_mwh",
        0.0,
    )
    spike_threshold = _number(
        _need(policy, "spike_threshold_cny_per_mwh", "policy"),
        "policy.spike_threshold_cny_per_mwh",
        0.0,
    )
    _number(
        _need(policy, "spike_markup_cny_per_mwh", "policy"),
        "policy.spike_markup_cny_per_mwh",
        0.0,
    )
    max_cycles = _number(
        _need(policy, "max_cycles_per_day", "policy"),
        "policy.max_cycles_per_day",
        1e-9,
    )
    min_spread = _number(
        _need(policy, "min_daily_spread_cny_per_mwh", "policy"),
        "policy.min_daily_spread_cny_per_mwh",
        0.0,
    )
    curtail_penalty = _number(
        _need(policy, "curtail_penalty_cny_per_mwh", "policy"),
        "policy.curtail_penalty_cny_per_mwh",
        0.0,
    )

    contracts = config.get("contracts", [])
    if not isinstance(contracts, list):
        raise ConfigError("contracts must be a list")
    if contracts:
        raise ConfigError("v1 光储联合包不支持中长期/CfD 合约；请改用中长期持仓实例包")

    d1 = _need(data_contract, "d1", "data_contract")
    _text(d1, "file", "data_contract.d1")
    required = _need(d1, "required_fields", "data_contract.d1")
    if not isinstance(required, list) or len(required) == 0:
        raise ConfigError("data_contract.d1.required_fields must be a non-empty list")
    price_fields = _need(d1, "price_scenario_fields", "data_contract.d1")
    pv_fields = _need(d1, "pv_scenario_fields", "data_contract.d1")
    if not isinstance(price_fields, list) or len(price_fields) < 2:
        raise ConfigError("data_contract.d1.price_scenario_fields needs at least two scenarios")
    if not isinstance(pv_fields, list) or len(pv_fields) != len(price_fields):
        raise ConfigError("data_contract.d1.pv_scenario_fields must match price_scenario_fields")
    for field in list(price_fields) + list(pv_fields):
        if field not in required:
            raise ConfigError(f"data_contract.d1.required_fields is missing {field}")
    weights = d1.get("scenario_weights", [1.0 / len(price_fields)] * len(price_fields))
    if len(weights) != len(price_fields):
        raise ConfigError("data_contract.d1.scenario_weights must match the scenario fields")
    parsed_weights = [_number(value, "data_contract.d1.scenario_weights", 0.0) for value in weights]
    if abs(sum(parsed_weights) - 1.0) > 1e-9:
        raise ConfigError("data_contract.d1.scenario_weights must sum to 1")
    t1 = _need(data_contract, "t1", "data_contract.t1")
    _text(t1, "file", "data_contract.t1")
    t1_required = _need(t1, "required_fields", "data_contract.t1")
    if not isinstance(t1_required, list) or len(t1_required) == 0:
        raise ConfigError("data_contract.t1.required_fields must be a non-empty list")

    def block(name, extra=""):
        item = {"block": f"rules.{name}", "grade": rules[name]["grade"], "source": rules[name]["source"]}
        if extra:
            item["status"] = extra
        return item

    provenance = [
        block("spot"),
        block("settlement"),
        block("new_energy_participation", joint.get("status", "")),
        block("storage_participation"),
        block("capacity_compensation", capacity.get("status", "")),
    ]
    if "negative_price" in rules:
        _rule_block(rules, "negative_price")
        provenance.append(block("negative_price"))

    warnings = []
    if capacity.get("price_cny_per_kw_year") is None or capacity.get("supply_demand_coefficient") is None:
        warnings.append(
            "容量补偿未计入：配建储能不适用电网侧独立储能容量电价；山东配建储能容量补偿口径待核实。"
        )
    if bid_mode == "quantity_only":
        warnings.append("本包按报量不报价（价格接受者）测算；若交易中心要求报量报价，把 bid_mode_code 改为 price_quote。")
    warnings.append("弃光惩罚是绿证/消纳价值的 D 级占位，不是山东规则值；不要把它当补贴。")
    warnings.append("机制电价差价、两个细则考核、绿证收益与容量补偿均未纳入；本表净边际不是电站利润。")
    warnings.append("联合出清计划上限为光伏本体额定容量、下限为 0；储能放电视同光伏电量，充电不重复计入上网电量。")

    return {
        "ok": True,
        "provenance": provenance,
        "warnings": warnings,
        "points_per_day": points,
        "mtu_min": mtu,
        "bounds": {
            "declare_floor": declare_floor,
            "declare_cap": declare_cap,
            "clear_floor": clear_floor,
            "clear_cap": clear_cap,
        },
        "scenario_weights": parsed_weights,
        "price_scenario_fields": list(price_fields),
        "pv_scenario_fields": list(pv_fields),
        "solver_states": states,
        "bid_mode": bid_mode,
        "grid_charge_allowed": grid_charge_allowed,
        "pv_capacity_mw": pv_capacity,
        "storage_power_mw": power,
        "storage_energy_mwh": energy,
        "storage_rte": rte,
        "soc_min": soc_min,
        "soc_max": soc_max,
        "soc_init": soc_init,
        "export_limit_mw": export_limit,
        "import_limit_mw": import_limit,
        "max_cycles": max_cycles,
        "min_spread": min_spread,
        "curtail_penalty": curtail_penalty,
        "price_quantile": price_q,
        "pv_quantile": pv_q,
        "quantity_quantile": qty_q,
        "spike_threshold": spike_threshold,
        "clearing_plan_max_mw": clearing_max,
    }


def _read_rows(path):
    if not path.exists():
        raise ConfigError(f"input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            if None in raw:
                raise ConfigError(f"{path.name}: row has more columns than the header")
            rows.append(
                {
                    (key.strip() if isinstance(key, str) else key): (
                        value.strip() if isinstance(value, str) else value
                    )
                    for key, value in raw.items()
                }
            )
    if not rows:
        raise ConfigError(f"{path.name} is empty")
    return rows


def _check_shape(rows, required, points, name):
    report = desk.validate_public_dataset(
        rows, required, points_per_day=points, date_field="date", slot_field="slot"
    )
    if not report["ok"]:
        raise ConfigError(
            f"{name} failed schema check: missing={report['missing_fields']} "
            f"duplicates={report['duplicates'][:3]} gaps={report['gaps'][:1]} "
            f"bad_slots={report['bad_slots'][:3]}"
        )
    return report


def _slot_time(slot, mtu_min):
    minutes = int(slot * mtu_min)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def read_d1(path, config, report):
    rows = _read_rows(path)
    d1 = config["data_contract"]["d1"]
    _check_shape(rows, d1["required_fields"], report["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    prices = []
    for field in report["price_scenario_fields"]:
        series = []
        for slot in range(report["points_per_day"]):
            price = _number(by_slot[slot][field], f"{path.name}:{field}@slot{slot}")
            if not (
                report["bounds"]["clear_floor"] - 0.01
                <= price
                <= report["bounds"]["clear_cap"] + 0.01
            ):
                raise ConfigError(
                    f"{path.name}:{field}@slot{slot}={price} is outside the clearing band"
                )
            series.append(price)
        prices.append(series)
    pv = []
    for field in report["pv_scenario_fields"]:
        series = []
        for slot in range(report["points_per_day"]):
            value = _number(
                by_slot[slot][field],
                f"{path.name}:{field}@slot{slot}",
                0.0,
                report["pv_capacity_mw"],
            )
            series.append(value)
        pv.append(series)
    return {
        "date": rows[0]["date"],
        "slots": list(range(report["points_per_day"])),
        "prices": prices,
        "pv": pv,
        "start": {slot: by_slot[slot]["start"] for slot in by_slot},
        "end": {slot: by_slot[slot]["end"] for slot in by_slot},
    }


def read_t1(path, config, report):
    rows = _read_rows(path)
    t1 = config["data_contract"]["t1"]
    _check_shape(rows, t1["required_fields"], report["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    actual_price = []
    actual_pv = []
    actual_charge = []
    actual_discharge = []
    actual_export = []
    actual_curtail = []
    for slot in range(report["points_per_day"]):
        row = by_slot[slot]
        price = _number(row["actual_price"], f"{path.name}:actual_price@slot{slot}")
        if not (
            report["bounds"]["clear_floor"] - 0.01
            <= price
            <= report["bounds"]["clear_cap"] + 0.01
        ):
            raise ConfigError(
                f"{path.name}:actual_price@slot{slot}={price} is outside the clearing band"
            )
        pv = _number(
            row["actual_pv_mw"], f"{path.name}:actual_pv_mw@slot{slot}", 0.0, report["pv_capacity_mw"]
        )
        charge = _number(row["actual_charge_mw"], f"{path.name}:actual_charge_mw@slot{slot}", 0.0)
        discharge = _number(
            row["actual_discharge_mw"], f"{path.name}:actual_discharge_mw@slot{slot}", 0.0
        )
        export = _number(
            row["actual_export_mw"],
            f"{path.name}:actual_export_mw@slot{slot}",
            0.0,
            report["export_limit_mw"],
        )
        curtail = _number(
            row["actual_curtail_mw"], f"{path.name}:actual_curtail_mw@slot{slot}", 0.0
        )
        if charge > report["storage_power_mw"] + 1e-6 or discharge > report["storage_power_mw"] + 1e-6:
            raise ConfigError(f"{path.name}:slot {slot} exceeds storage power")
        if charge > 1e-6 and discharge > 1e-6:
            raise ConfigError(f"{path.name}:slot {slot} has simultaneous charge and discharge")
        if not report["grid_charge_allowed"] and charge > pv + 1e-6:
            raise ConfigError(
                f"{path.name}:slot {slot} charges {charge:.3f} MW from a {pv:.3f} MW PV curve "
                "without grid charging"
            )
        identity = pv - charge + discharge - export - curtail
        if abs(identity) > 0.02:
            raise ConfigError(
                f"{path.name}:slot {slot} violates PV − charge + discharge − export = curtail "
                f"(residual {identity:.4f} MW)"
            )
        actual_price.append(price)
        actual_pv.append(pv)
        actual_charge.append(charge)
        actual_discharge.append(discharge)
        actual_export.append(export)
        actual_curtail.append(curtail)
    return {
        "date": rows[0]["date"],
        "price": actual_price,
        "pv": actual_pv,
        "charge_mw": actual_charge,
        "discharge_mw": actual_discharge,
        "export_mw": actual_export,
        "curtail_mw": actual_curtail,
    }


def quantile(values, q):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile needs at least one value")
    if q <= 0:
        return ordered[0]
    if q >= 1:
        return ordered[-1]
    position = (len(ordered) - 1) * q
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def solve_scenario(prices, pv, config, report):
    eta = math.sqrt(report["storage_rte"])
    result = KERNEL.dispatch_day(
        [float(price) / 1000.0 for price in prices],
        [0.0] * len(prices),
        [float(value) * 1000.0 for value in pv],
        sell_price=[float(price) / 1000.0 for price in prices],
        capacity_kwh=report["storage_energy_mwh"] * 1000.0,
        power_charge_kw=report["storage_power_mw"] * 1000.0,
        power_discharge_kw=report["storage_power_mw"] * 1000.0,
        eta_charge=eta,
        eta_discharge=eta,
        soc_min=report["soc_min"],
        soc_max=report["soc_max"],
        soc_init=report["soc_init"],
        dt_h=report["mtu_min"] / 60.0,
        pcc_import_kw=report["import_limit_mw"] * 1000.0,
        pcc_export_kw=report["export_limit_mw"] * 1000.0,
        degradation_per_kwh=float(config["asset"]["storage"]["degradation_cny_per_mwh_throughput"]) / 1000.0,
        curtail_penalty_per_kwh=report["curtail_penalty"] / 1000.0,
        terminal="cycle",
        states=report["solver_states"],
    )
    if not result["feasible"]:
        raise ConfigError(f"dispatch infeasible: {result.get('reason', 'unknown')}")
    return result


def scale_cycles(schedule, max_cycles, capacity_mwh, dt_h):
    """Scale a DP schedule down if it exceeds the policy cycle cap."""
    charge = [value / 1000.0 for value in schedule["schedule"]["p_charge_kw"]]
    discharge = [value / 1000.0 for value in schedule["schedule"]["p_discharge_kw"]]
    throughput = (sum(charge) + sum(discharge)) * dt_h
    cycles = throughput / (2.0 * capacity_mwh)
    scale = 1.0
    if cycles > max_cycles + 1e-9:
        scale = max_cycles / cycles
        charge = [value * scale for value in charge]
        discharge = [value * scale for value in discharge]
    return charge, discharge, cycles, scale


def build_bid(prices_by_scenario, pv_by_scenario, config, report):
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    weights = report["scenario_weights"]
    policy = config["policy"]

    reference_price = [
        quantile([prices_by_scenario[s][t] for s in range(len(prices_by_scenario))], report["price_quantile"])
        for t in range(n)
    ]
    reference_pv = [
        quantile([pv_by_scenario[s][t] for s in range(len(pv_by_scenario))], report["pv_quantile"])
        for t in range(n)
    ]
    schedules = [solve_scenario(series, pv_by_scenario[s], config, report) for s, series in enumerate(prices_by_scenario)]
    plan_schedule = solve_scenario(reference_price, reference_pv, config, report)
    plan_charge, plan_discharge, raw_cycles, scale = scale_cycles(
        plan_schedule, report["max_cycles"], report["storage_energy_mwh"], dt_h
    )
    warnings = []
    if scale < 1.0:
        warnings.append(
            f"reference schedule cycles {raw_cycles:.3f} > policy cap {report['max_cycles']:.3f}; "
            f"scaled by {scale:.4f}"
        )
    declared = [
        min(
            report["export_limit_mw"],
            max(0.0, quantile([schedules[s]["schedule"]["p_export_kw"][t] / 1000.0 for s in range(len(schedules))], policy["declared_quantity_quantile"])),
        )
        for t in range(n)
    ]
    expected_export = [
        sum(weights[s] * schedules[s]["schedule"]["p_export_kw"][t] / 1000.0 for s in range(len(schedules)))
        for t in range(n)
    ]
    expected_curtail = [
        sum(weights[s] * schedules[s]["schedule"]["pv_curtailed_kw"][t] / 1000.0 for s in range(len(schedules)))
        for t in range(n)
    ]
    negative_probability = [
        sum(weights[s] for s in range(len(weights)) if prices_by_scenario[s][t] < 0.0) for t in range(n)
    ]

    offer = []
    clear_probability = []
    for slot in range(n):
        if report["bid_mode"] == "quantity_only":
            offer.append(report["bounds"]["declare_floor"])
            clear_probability.append(1.0)
            continue
        markup = (
            float(policy["spike_markup_cny_per_mwh"])
            if reference_price[slot] >= report["spike_threshold"]
            else float(policy["discharge_markup_cny_per_mwh"])
        )
        raw = reference_price[slot] + markup
        offer.append(
            min(report["bounds"]["declare_cap"], max(report["bounds"]["declare_floor"], raw))
        )
        clear_probability.append(
            sum(
                weights[s]
                for s in range(len(weights))
                if prices_by_scenario[s][slot] >= offer[slot] - 1e-9
            )
        )

    rows = []
    for slot in range(n):
        note = (
            f"q={policy['declared_quantity_quantile']:.2f}; "
            f"{report['bid_mode']}; "
            f"PVref={reference_pv[slot]:.1f}"
        )
        if scale < 1.0:
            note += f"; cycle-scaled={scale:.3f}"
        rows.append(
            {
                "date": None,
                "slot": slot,
                "side": "joint_net_export",
                "pv_reference_mw": reference_pv[slot],
                "charge_plan_mw": plan_charge[slot],
                "discharge_plan_mw": plan_discharge[slot],
                "declared_net_export_mw": declared[slot],
                "expected_net_export_mw": expected_export[slot],
                "expected_curtail_mw": expected_curtail[slot],
                "reference_price": reference_price[slot],
                "offer_price": offer[slot],
                "negative_price_probability": negative_probability[slot],
                "clear_probability": clear_probability[slot],
                "note": note,
            }
        )

    plan_export = [value / 1000.0 for value in plan_schedule["schedule"]["p_export_kw"]]
    plan_curtail = [value / 1000.0 for value in plan_schedule["schedule"]["pv_curtailed_kw"]]
    if scale < 1.0 - 1e-12:
        # keep the scaled plan but recompute export/curtail from the scaled actions
        plan_export = [
            min(report["export_limit_mw"], max(0.0, reference_pv[t] - plan_charge[t] + plan_discharge[t]))
            for t in range(n)
        ]
        plan_curtail = [
            max(0.0, reference_pv[t] - plan_charge[t] + plan_discharge[t] - plan_export[t])
            for t in range(n)
        ]
    cycles = (sum(plan_charge) + sum(plan_discharge)) * dt_h / (2.0 * report["storage_energy_mwh"])
    return {
        "schedules": schedules,
        "plan_schedule": plan_schedule,
        "reference_price": reference_price,
        "reference_pv": reference_pv,
        "plan_charge": plan_charge,
        "plan_discharge": plan_discharge,
        "plan_export": plan_export,
        "plan_curtail": plan_curtail,
        "declared": declared,
        "expected_export": expected_export,
        "expected_curtail": expected_curtail,
        "offer": offer,
        "rows": rows,
        "warnings": warnings,
        "cycles": cycles,
        "pv_energy_mwh": sum(reference_pv) * dt_h,
        "charge_mwh": sum(plan_charge) * dt_h,
        "discharge_mwh": sum(plan_discharge) * dt_h,
        "declared_energy_mwh": sum(declared) * dt_h,
        "expected_export_mwh": sum(expected_export) * dt_h,
        "expected_curtail_mwh": sum(expected_curtail) * dt_h,
        "negative_price_hours": sum(1 for price in reference_price if price < 0.0) * dt_h,
    }


def execute_plan(plan_charge, plan_discharge, pv, prices, config, report):
    """Execute a fixed storage plan under a PV/price scenario, without grid charging."""
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    eta = math.sqrt(report["storage_rte"])
    capacity = report["storage_energy_mwh"]
    low = report["soc_min"] * capacity
    high = report["soc_max"] * capacity
    energy = report["soc_init"] * capacity
    charge = [0.0] * n
    discharge = [0.0] * n
    export = [0.0] * n
    curtail = [0.0] * n
    for t in range(n):
        c = max(0.0, min(plan_charge[t], pv[t]))
        d = max(0.0, plan_discharge[t])
        if c > 1e-9 and d > 1e-9:
            net = c - d
            c = max(0.0, net)
            d = max(0.0, -net)
        if c > 1e-9:
            room = max(0.0, high - energy)
            c = min(c, room / (eta * dt_h))
            energy += c * eta * dt_h
        if d > 1e-9:
            available = max(0.0, energy - low)
            d = min(d, available * eta / dt_h)
            energy -= d / eta * dt_h
        gross = pv[t] - c + d
        e = min(report["export_limit_mw"], max(0.0, gross))
        cur = max(0.0, gross - e)
        charge[t] = c
        discharge[t] = d
        export[t] = e
        curtail[t] = cur
    revenue = sum(export[t] * prices[t] * dt_h for t in range(n))
    degradation = sum(charge[t] + discharge[t] for t in range(n)) * dt_h * float(
        config["asset"]["storage"]["degradation_cny_per_mwh_throughput"]
    )
    curtail_penalty = sum(curtail) * dt_h * report["curtail_penalty"]
    fixed = float(config["asset"]["storage"].get("fixed_cost_cny_per_day", 0.0))
    return {
        "charge_mw": charge,
        "discharge_mw": discharge,
        "export_mw": export,
        "curtail_mw": curtail,
        "revenue_cny": revenue,
        "degradation_cny": degradation,
        "curtail_penalty_cny": curtail_penalty,
        "fixed_cost_cny": fixed,
        "net_margin_cny": revenue - degradation - curtail_penalty - fixed,
        "export_mwh": sum(export) * dt_h,
        "charge_mwh": sum(charge) * dt_h,
        "discharge_mwh": sum(discharge) * dt_h,
        "curtail_mwh": sum(curtail) * dt_h,
        "cycles": (sum(charge) + sum(discharge)) * dt_h / (2.0 * capacity),
        "terminal_energy_mwh": energy,
    }


def evaluate_plan(bid, prices_by_scenario, pv_by_scenario, config, report):
    dt_h = report["mtu_min"] / 60.0
    weights = report["scenario_weights"]
    fixed = float(config["asset"]["storage"].get("fixed_cost_cny_per_day", 0.0))
    outcomes = []
    foresight = []
    for index, prices in enumerate(prices_by_scenario):
        execution = execute_plan(
            bid["plan_charge"], bid["plan_discharge"], pv_by_scenario[index], prices, config, report
        )
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "mean_price": sum(prices) / len(prices),
                "pv_mwh": sum(pv_by_scenario[index]) * dt_h,
                "export_mwh": execution["export_mwh"],
                "charge_mwh": execution["charge_mwh"],
                "discharge_mwh": execution["discharge_mwh"],
                "curtail_mwh": execution["curtail_mwh"],
                "revenue_cny": execution["revenue_cny"],
                "degradation_cny": execution["degradation_cny"],
                "curtail_penalty_cny": execution["curtail_penalty_cny"],
                "net_margin_cny": execution["net_margin_cny"],
                "terminal_energy_mwh": execution["terminal_energy_mwh"],
            }
        )
        schedule = bid["schedules"][index]
        foresight_net = (
            schedule["sell_revenue"] - schedule["degradation_cost"] - schedule["curtailment_penalty"] - fixed
        )
        foresight.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "net_margin_cny": foresight_net,
                "curtail_mwh": schedule["curtailed_kwh"] / 1000.0,
                "cycles": schedule["equivalent_cycles"],
            }
        )
    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    cvar = desk.weighted_cvar([(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=0.10)
    foresight_expected = sum(item["weight"] * item["net_margin_cny"] for item in foresight)
    reference_execution = execute_plan(
        bid["plan_charge"], bid["plan_discharge"], bid["reference_pv"], bid["reference_price"], config, report
    )
    return {
        "outcomes": outcomes,
        "foresight": foresight,
        "expected_net_margin_cny": expected,
        "cvar_10_cny": cvar,
        "perfect_foresight_expected_net_cny": foresight_expected,
        "foresight_uplift_cny": foresight_expected - expected,
        "reference_net_margin_cny": reference_execution["net_margin_cny"],
        "reference_execution": reference_execution,
        "fixed_cost_cny": fixed,
    }


def build_bridge(bid, t1, config, report):
    dt_h = report["mtu_min"] / 60.0
    degradation = float(config["asset"]["storage"]["degradation_cny_per_mwh_throughput"])
    fixed = float(config["asset"]["storage"].get("fixed_cost_cny_per_day", 0.0))
    n = report["points_per_day"]
    plan_revenue = sum(bid["plan_export"][t] * bid["reference_price"][t] * dt_h for t in range(n))
    plan_degradation = sum(bid["plan_charge"][t] + bid["plan_discharge"][t] for t in range(n)) * dt_h * degradation
    plan_curtail_penalty = sum(bid["plan_curtail"]) * dt_h * report["curtail_penalty"]
    plan_profit = plan_revenue - plan_degradation - plan_curtail_penalty - fixed
    actual_revenue = sum(t1["export_mw"][t] * t1["price"][t] * dt_h for t in range(n))
    actual_degradation = sum(t1["charge_mw"][t] + t1["discharge_mw"][t] for t in range(n)) * dt_h * degradation
    actual_curtail_penalty = sum(t1["curtail_mw"]) * dt_h * report["curtail_penalty"]
    actual_profit = actual_revenue - actual_degradation - actual_curtail_penalty - fixed
    price_effect = sum(
        bid["plan_export"][t] * (t1["price"][t] - bid["reference_price"][t]) * dt_h for t in range(n)
    )
    quantity_effect = sum(
        (t1["export_mw"][t] - bid["plan_export"][t]) * bid["reference_price"][t] * dt_h
        for t in range(n)
    )
    interaction = sum(
        (t1["export_mw"][t] - bid["plan_export"][t])
        * (t1["price"][t] - bid["reference_price"][t])
        * dt_h
        for t in range(n)
    )
    degradation_effect = plan_degradation - actual_degradation
    curtail_effect = plan_curtail_penalty - actual_curtail_penalty
    buckets = [
        {"item": "电价影响", "category": "price", "owner": "市场", "amount": price_effect},
        {"item": "净头寸量差", "category": "quantity", "owner": "执行/光伏", "amount": quantity_effect},
        {"item": "价量交叉", "category": "interaction", "owner": "共同", "amount": interaction},
        {"item": "退化成本差", "category": "degradation", "owner": "储能", "amount": degradation_effect},
        {"item": "弃光惩罚差", "category": "curtailment", "owner": "运行", "amount": curtail_effect},
        {"item": "固定成本", "category": "fixed", "owner": "财务", "amount": 0.0},
    ]
    delta = actual_profit - plan_profit
    identity_gap = delta - sum(item["amount"] for item in buckets)
    return {
        "plan_profit": plan_profit,
        "actual_profit": actual_profit,
        "delta": delta,
        "identity_gap": identity_gap,
        "plan_revenue": plan_revenue,
        "actual_revenue": actual_revenue,
        "plan_degradation": plan_degradation,
        "actual_degradation": actual_degradation,
        "plan_curtail_penalty": plan_curtail_penalty,
        "actual_curtail_penalty": actual_curtail_penalty,
        "plan_export_mwh": sum(bid["plan_export"]) * dt_h,
        "actual_export_mwh": sum(t1["export_mw"]) * dt_h,
        "plan_charge_mwh": sum(bid["plan_charge"]) * dt_h,
        "actual_charge_mwh": sum(t1["charge_mw"]) * dt_h,
        "plan_discharge_mwh": sum(bid["plan_discharge"]) * dt_h,
        "actual_discharge_mwh": sum(t1["discharge_mw"]) * dt_h,
        "plan_curtail_mwh": sum(bid["plan_curtail"]) * dt_h,
        "actual_curtail_mwh": sum(t1["curtail_mw"]) * dt_h,
        "plan_cycles": (sum(bid["plan_charge"]) + sum(bid["plan_discharge"]))
        * dt_h
        / (2.0 * report["storage_energy_mwh"]),
        "actual_cycles": (sum(t1["charge_mw"]) + sum(t1["discharge_mw"]))
        * dt_h
        / (2.0 * report["storage_energy_mwh"]),
        "buckets": buckets,
    }


def build_bridge_detail(bid, t1, report):
    dt_h = report["mtu_min"] / 60.0
    detail = []
    for slot in range(report["points_per_day"]):
        delta = t1["export_mw"][slot] - bid["plan_export"][slot]
        detail.append(
            {
                "slot": slot,
                "start": _slot_time(slot, report["mtu_min"]),
                "plan_export_mw": bid["plan_export"][slot],
                "actual_export_mw": t1["export_mw"][slot],
                "plan_charge_mw": bid["plan_charge"][slot],
                "actual_charge_mw": t1["charge_mw"][slot],
                "plan_discharge_mw": bid["plan_discharge"][slot],
                "actual_discharge_mw": t1["discharge_mw"][slot],
                "plan_curtail_mw": bid["plan_curtail"][slot],
                "actual_curtail_mw": t1["curtail_mw"][slot],
                "quantity_effect_cny": delta * bid["reference_price"][slot] * dt_h,
            }
        )
    detail.sort(key=lambda item: abs(item["quantity_effect_cny"]), reverse=True)
    return detail[:5]


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(field, row.get(field)) for field in fields})


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _signed(value):
    return 0.0 if abs(value) < 0.5 else value


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, float):
        if field.endswith("_mw"):
            return f"{value:.3f}"
        if field.endswith("_price") or field == "reference_price":
            return f"{value:.2f}"
        if "probability" in field:
            return f"{value:.3f}"
        if field in ("amount", "quantity_effect_cny"):
            return f"{_signed(value):.2f}"
        return f"{value:.6f}"
    return value


def write_review(path, config, report, d1, bid, evaluation, bridge, bridge_detail, policy_fingerprint):
    policy = config["policy"]
    asset = config["asset"]
    pv = asset["pv"]
    storage = asset["storage"]
    dt_h = report["mtu_min"] / 60.0
    lines = [
        f"# 山东光储联合报价复核表：{config['meta']['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']} 分钟）",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格档：`{policy['profile_id']}` / 指纹 `{policy_fingerprint}`",
        f"- 联合主体：光伏 {pv['capacity_mw']:.0f} MW + 配建储能 {storage['power_mw']:.0f} MW / {storage['energy_mwh']:.0f} MWh，"
        f"RTE {storage['rte']:.2f}，SOC {storage['soc_min']:.2f}–{storage['soc_max']:.2f}",
        f"- 申报方式：{report['bid_mode']}；并网上限 {report['export_limit_mw']:.0f} MW；购电上限 {report['import_limit_mw']:.0f} MW",
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
        "## 2. 联合净头寸摘要",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 参考光伏电量 | {bid['pv_energy_mwh']:.1f} MWh |",
        f"| 计划充电量 | {bid['charge_mwh']:.1f} MWh |",
        f"| 计划放电量 | {bid['discharge_mwh']:.1f} MWh |",
        f"| 计划净上网（参考调度） | {sum(bid['plan_export']) * dt_h:.1f} MWh |",
        f"| 申报净头寸（{policy['declared_quantity_quantile']:.0%} 分位） | {bid['declared_energy_mwh']:.1f} MWh |",
        f"| 期望净上网（按情景） | {bid['expected_export_mwh']:.1f} MWh |",
        f"| 期望弃光 | {bid['expected_curtail_mwh']:.1f} MWh |",
        f"| 等效循环 | {bid['cycles']:.2f} 次 |",
        f"| 负价时长（参考价） | {bid['negative_price_hours']:.1f} h |",
        f"| 参考价口径净边际 | {_money(evaluation['reference_net_margin_cny'])} CNY |",
        f"| 情景期望净边际 | {_money(evaluation['expected_net_margin_cny'])} CNY |",
        f"| 情景 CVaR10 | {_money(evaluation['cvar_10_cny'])} CNY |",
        f"| 完美预见期望（上界） | {_money(evaluation['perfect_foresight_expected_net_cny'])} CNY |",
        f"| 预见价值（上界 − 计划） | {_money(evaluation['foresight_uplift_cny'])} CNY |",
        "",
        "## 3. 情景清算（固定参考调度，不重新优化）",
        "",
        "| 情景 | 权重 | 均价 | 光伏 | 净上网 | 弃光 | 充电 | 放电 | 净边际 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in evaluation["outcomes"]:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['mean_price']:.1f} | "
            f"{item['pv_mwh']:.1f} | {item['export_mwh']:.1f} | {item['curtail_mwh']:.1f} | "
            f"{item['charge_mwh']:.1f} | {item['discharge_mwh']:.1f} | {item['net_margin_cny']:,.0f} |"
        )
    lines += [
        "",
        f"> 完美预见上界 {evaluation['perfect_foresight_expected_net_cny']:,.0f} CNY；"
        f"计划与上界的差 {evaluation['foresight_uplift_cny']:,.0f} CNY 是预测不确定性的代价，不可实现，只作改进空间。",
        "",
        "> 情景清算固定参考调度：低价/低光伏情景下充电被可用光伏限制，放电受 SOC 限制；这不是场景最优，是正确的执行口径。",
    ]
    if bridge is None:
        lines += ["", "## 4. T+1 差异桥", "", "未提供 T+1 实际数据，本次只出申报表。"]
    else:
        ordered = sorted(bridge["buckets"], key=lambda item: abs(item["amount"]), reverse=True)
        lines += [
            "",
            "## 4. T+1 差异桥",
            "",
            f"计划利润 {bridge['plan_profit']:,.0f} CNY，实际利润 {bridge['actual_profit']:,.0f} CNY，"
            f"差异 {bridge['delta']:,.0f} CNY，残差 {bridge['identity_gap']:.2e}。",
            "",
            "| 科目 | 类别 | 责任 | 金额（CNY） |",
            "|---|---|---|---:|",
        ]
        for item in ordered:
            lines.append(
                f"| {item['item']} | {item['category']} | {item['owner']} | {_signed(item['amount']):,.0f} |"
            )
        top = ordered[0] if ordered else None
        lines += [
            "",
            f"**最大差异科目**：{top['item'] if top else '—'}，{top['amount']:,.0f} CNY。" if top else "**最大差异科目**：—",
            "",
            f"计划净上网 {bridge['plan_export_mwh']:.1f} MWh / 充电 {bridge['plan_charge_mwh']:.1f} MWh / "
            f"放电 {bridge['plan_discharge_mwh']:.1f} MWh / 弃光 {bridge['plan_curtail_mwh']:.1f} MWh / "
            f"{bridge['plan_cycles']:.2f} 次循环；实际净上网 {bridge['actual_export_mwh']:.1f} MWh / "
            f"充电 {bridge['actual_charge_mwh']:.1f} MWh / 放电 {bridge['actual_discharge_mwh']:.1f} MWh / "
            f"弃光 {bridge['actual_curtail_mwh']:.1f} MWh / {bridge['actual_cycles']:.2f} 次循环。",
            "",
        ]
        if bridge_detail:
            lines += [
                "**净头寸偏差最大的 5 个时段**（按参考价折算的量影响）：",
                "",
                "| 时段 | 计划净上网 | 实际净上网 | 计划充电 | 实际充电 | 计划放电 | 实际放电 | 量影响（CNY） |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for item in bridge_detail:
                lines.append(
                    f"| {item['start']} | {item['plan_export_mw']:.1f} | {item['actual_export_mw']:.1f} | "
                    f"{item['plan_charge_mw']:.1f} | {item['actual_charge_mw']:.1f} | "
                    f"{item['plan_discharge_mw']:.1f} | {item['actual_discharge_mw']:.1f} | "
                    f"{_signed(item['quantity_effect_cny']):,.0f} |"
                )
    lines += [
        "",
        "## 5. 三个复核问题",
        "",
        "1. 最大差异科目归因到价、净头寸、光伏预测、储能执行、弃光口径还是规则版本？证据包是否齐全？",
        "2. 申报净头寸用的是哪个分位？低价/负价时段是否把可充电量算进净头寸，而不是把全部光伏都报上网？",
        "3. 配建储能充电是否全部来自配套光伏？有没有出现从公共电网购电充电、或把充电量重复计入上网电量？",
        "",
        "## 6. 下一日动作（人工填写）",
        "",
        "- [ ] ",
        "- [ ] ",
        "- [ ] ",
        "",
        "## 7. 告警与边界",
        "",
    ]
    for warning in report["warnings"] + bid["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        f"- {config['meta']['disclaimer']}",
        "- 本表是价格接受者口径的盘面复核，不是市场出清仿真；实际出清、结算与考核以交易中心、调度机构正式结果为准。",
        "- 联合主体注册、计量与两个细则考核口径以山东省 2026-08-27 通知的正式原文和交易中心实施细则为准；文号与条款仍需复核。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, d1_path, t1_path, out_dir):
    """Validate, optimise, write the bid sheet, bridge and review."""
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{instance_path.name} is not valid JSON: {exc}") from exc
    report = validate_instance(config)
    d1 = read_d1(Path(d1_path), config, report)
    if t1_path is not None:
        t1 = read_t1(Path(t1_path), config, report)
        if t1["date"] != d1["date"]:
            raise ConfigError("D-1 and T+1 files must refer to the same trading day")
    else:
        t1 = None

    bid = build_bid(d1["prices"], d1["pv"], config, report)
    evaluation = evaluate_plan(bid, d1["prices"], d1["pv"], config, report)
    bridge = None
    bridge_detail = None
    if t1 is not None:
        bridge = build_bridge(bid, t1, config, report)
        bridge_detail = build_bridge_detail(bid, t1, report)

    for row in bid["rows"]:
        row["date"] = d1["date"]
        row["start"] = d1["start"][row["slot"]]
        row["end"] = d1["end"][row["slot"]]

    policy_fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bid_fields = [
        "date",
        "slot",
        "start",
        "end",
        "side",
        "pv_reference_mw",
        "charge_plan_mw",
        "discharge_plan_mw",
        "declared_net_export_mw",
        "expected_net_export_mw",
        "expected_curtail_mw",
        "reference_price",
        "offer_price",
        "negative_price_probability",
        "clear_probability",
        "note",
    ]
    _write_csv(out_dir / "bid_sheet.csv", bid["rows"], bid_fields)

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "bid_mode": report["bid_mode"],
        "policy": config["policy"],
        "policy_fingerprint": policy_fingerprint,
        "provenance": report["provenance"],
        "plan": {
            "pv_energy_mwh": bid["pv_energy_mwh"],
            "charge_mwh": bid["charge_mwh"],
            "discharge_mwh": bid["discharge_mwh"],
            "declared_net_export_mwh": bid["declared_energy_mwh"],
            "expected_net_export_mwh": bid["expected_export_mwh"],
            "expected_curtail_mwh": bid["expected_curtail_mwh"],
            "equivalent_cycles": bid["cycles"],
            "negative_price_hours": bid["negative_price_hours"],
            "reference_net_margin_cny": evaluation["reference_net_margin_cny"],
            "expected_net_margin_cny": evaluation["expected_net_margin_cny"],
            "cvar_10_cny": evaluation["cvar_10_cny"],
            "perfect_foresight_expected_net_cny": evaluation["perfect_foresight_expected_net_cny"],
            "foresight_uplift_cny": evaluation["foresight_uplift_cny"],
            "fixed_cost_cny": evaluation["fixed_cost_cny"],
            "scenarios": evaluation["outcomes"],
            "foresight": evaluation["foresight"],
        },
        "actual": None if bridge is None else {
            "net_margin_cny": bridge["actual_profit"],
            "export_mwh": bridge["actual_export_mwh"],
            "charge_mwh": bridge["actual_charge_mwh"],
            "discharge_mwh": bridge["actual_discharge_mwh"],
            "curtail_mwh": bridge["actual_curtail_mwh"],
            "equivalent_cycles": bridge["actual_cycles"],
        },
        "warnings": report["warnings"] + bid["warnings"],
        "files": {
            "bid_sheet": "bid_sheet.csv",
            "review": "review.md",
            "bridge": "bridge.json" if bridge is not None else None,
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if bridge is not None:
        bridge_out = {
            "plan_profit": bridge["plan_profit"],
            "actual_profit": bridge["actual_profit"],
            "delta": bridge["delta"],
            "identity_gap": bridge["identity_gap"],
            "plan_revenue": bridge["plan_revenue"],
            "actual_revenue": bridge["actual_revenue"],
            "plan_degradation": bridge["plan_degradation"],
            "actual_degradation": bridge["actual_degradation"],
            "plan_curtail_penalty": bridge["plan_curtail_penalty"],
            "actual_curtail_penalty": bridge["actual_curtail_penalty"],
            "plan_export_mwh": bridge["plan_export_mwh"],
            "actual_export_mwh": bridge["actual_export_mwh"],
            "plan_charge_mwh": bridge["plan_charge_mwh"],
            "actual_charge_mwh": bridge["actual_charge_mwh"],
            "plan_discharge_mwh": bridge["plan_discharge_mwh"],
            "actual_discharge_mwh": bridge["actual_discharge_mwh"],
            "plan_curtail_mwh": bridge["plan_curtail_mwh"],
            "actual_curtail_mwh": bridge["actual_curtail_mwh"],
            "plan_cycles": bridge["plan_cycles"],
            "actual_cycles": bridge["actual_cycles"],
            "buckets": bridge["buckets"],
            "top_quantity_slots": bridge_detail,
        }
        (out_dir / "bridge.json").write_text(
            json.dumps(bridge_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _write_csv(
            out_dir / "bridge.csv",
            bridge_out["buckets"],
            ["item", "category", "owner", "amount"],
        )
    write_review(
        out_dir / "review.md",
        config,
        report,
        d1,
        bid,
        evaluation,
        bridge,
        bridge_detail,
        policy_fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "bid": bid,
        "evaluation": evaluation,
        "bridge": bridge,
        "bridge_detail": bridge_detail,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shandong PV-plus-storage joint instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", help="D-1 96-point price/PV scenario CSV")
    parser.add_argument("--t1", help="T+1 actual CSV; omit to skip the bridge")
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
        d1_path = _resolve_data(config, "d1")
        t1_path = _resolve_data(config, "t1")
        out_dir = Path(args.out) if args.out != str(HERE / "out") else HERE / "out" / "demo"
    else:
        if not args.d1:
            print("必须提供 --d1，或使用 --demo", file=sys.stderr)
            return 1
        d1_path = Path(args.d1)
        t1_path = Path(args.t1) if args.t1 else None
        out_dir = Path(args.out)

    try:
        result = run_instance(args.instance, d1_path, t1_path, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    plan = summary["plan"]
    print(f"实例：{summary['instance_id']} / 交易日 {summary['trading_day']}")
    print(
        f"联合净头寸：申报 {plan['declared_net_export_mwh']:.1f} MWh，"
        f"计划充电 {plan['charge_mwh']:.1f} MWh / 放电 {plan['discharge_mwh']:.1f} MWh，"
        f"{plan['equivalent_cycles']:.2f} 次循环"
    )
    print(
        f"情景：期望净边际 {plan['expected_net_margin_cny']:,.0f} CNY，"
        f"CVaR10 {plan['cvar_10_cny']:,.0f} CNY，"
        f"完美预见上界 {plan['perfect_foresight_expected_net_cny']:,.0f} CNY"
    )
    if result["bridge"] is not None:
        print(
            f"差异桥：计划 {result['bridge']['plan_profit']:,.0f} → "
            f"实际 {result['bridge']['actual_profit']:,.0f}，"
            f"差异 {result['bridge']['delta']:,.0f} CNY，残差 {result['bridge']['identity_gap']:.2e}"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
