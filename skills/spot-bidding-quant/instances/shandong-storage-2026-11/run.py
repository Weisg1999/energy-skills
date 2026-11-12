#!/usr/bin/env python3
"""Run the Shandong standalone-storage instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the rule parameters, asset, policy profile and data
  contract. A trader edits it; no code change is needed for a new asset or a
  new style profile.
* ``data/d1_demo.csv`` is a 96-point, five-scenario D-1 price set.
* ``data/t1_demo.csv`` is the T+1 actual price and metered charge/discharge.

The SOC-aware optimiser is the existing ``ems-dispatch/tools/dispatch.py``
kernel. This runner only adds scenario quantiles, bid-sheet translation, a
price-taker evaluation, the T+1 bridge and the review sheet.

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
    """Validate the four blocks and return a provenance report."""
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot")
    _rule_block(rules, "settlement")
    capacity = _rule_block(rules, "capacity_compensation")
    _rule_block(rules, "storage_participation")

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

    power = _number(_need(asset, "power_mw", "asset"), "asset.power_mw", 1e-9)
    energy = _number(_need(asset, "energy_mwh", "asset"), "asset.energy_mwh", 1e-9)
    rte = _number(_need(asset, "rte", "asset"), "asset.rte", 1e-9, 1.0)
    soc_min = _number(_need(asset, "soc_min", "asset"), "asset.soc_min", 0.0, 1.0)
    soc_max = _number(_need(asset, "soc_max", "asset"), "asset.soc_max", 0.0, 1.0)
    soc_init = _number(_need(asset, "soc_init", "asset"), "asset.soc_init", 0.0, 1.0)
    if not soc_min < soc_max:
        raise ConfigError("asset.soc_min must be below asset.soc_max")
    if not soc_min <= soc_init <= soc_max:
        raise ConfigError("asset.soc_init must lie inside the SOC window")
    window = (soc_max - soc_min) * energy
    if "usable_energy_mwh" in asset:
        usable = _number(asset["usable_energy_mwh"], "asset.usable_energy_mwh", 0.0)
        if abs(usable - window) > 1e-6 * max(1.0, window):
            raise ConfigError(
                "asset.usable_energy_mwh must equal energy_mwh * (soc_max - soc_min)"
            )
    _number(
        _need(asset, "degradation_cny_per_mwh_throughput", "asset"),
        "asset.degradation_cny_per_mwh_throughput",
        0.0,
    )
    _number(asset.get("fixed_cost_cny_per_day", 0.0), "asset.fixed_cost_cny_per_day", 0.0)
    effective = _number(
        asset.get("effective_capacity_mw", power),
        "asset.effective_capacity_mw",
        0.0,
    )
    grid = _need(asset, "grid_connection", "asset")
    _number(_need(grid, "import_limit_mw", "asset.grid_connection"), "asset.grid_connection.import_limit_mw", 0.0)
    _number(_need(grid, "export_limit_mw", "asset.grid_connection"), "asset.grid_connection.export_limit_mw", 0.0)
    states = int(_number(asset.get("solver_states", 160), "asset.solver_states", 10))

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
    _number(
        _need(policy, "spike_threshold_cny_per_mwh", "policy"),
        "policy.spike_threshold_cny_per_mwh",
        0.0,
    )
    _number(
        _need(policy, "spike_markup_cny_per_mwh", "policy"),
        "policy.spike_markup_cny_per_mwh",
        0.0,
    )
    _number(
        _need(policy, "max_cycles_per_day", "policy"),
        "policy.max_cycles_per_day",
        1e-9,
    )
    _number(
        _need(policy, "min_daily_spread_cny_per_mwh", "policy"),
        "policy.min_daily_spread_cny_per_mwh",
        0.0,
    )

    contracts = config.get("contracts", [])
    if not isinstance(contracts, list):
        raise ConfigError("contracts must be a list")
    if len(contracts) > 1:
        raise ConfigError("v1 supports at most one CfD contract")
    for index, contract in enumerate(contracts):
        _text(contract, "id", f"contracts[{index}]")
        if contract.get("type", "cfd") != "cfd":
            raise ConfigError("v1 supports contract type 'cfd' only")
        price = _number(
            _need(contract, "price_cny_per_mwh", f"contracts[{index}]"),
            f"contracts[{index}].price_cny_per_mwh",
            0.0,
        )
        if price <= 0:
            raise ConfigError(f"contracts[{index}].price_cny_per_mwh must be positive")
        quantity = _need(contract, "quantity_mw", f"contracts[{index}]")
        if isinstance(quantity, (list, tuple)):
            if len(quantity) != points:
                raise ConfigError(
                    f"contracts[{index}].quantity_mw must be a scalar or {points} values"
                )
            for slot, value in enumerate(quantity):
                _number(value, f"contracts[{index}].quantity_mw[{slot}]", 0.0)
        else:
            _number(quantity, f"contracts[{index}].quantity_mw", 0.0)
        _text(contract, "grade", f"contracts[{index}]")
        _text(contract, "source", f"contracts[{index}]")

    d1 = _need(data_contract, "d1", "data_contract")
    _text(d1, "file", "data_contract.d1")
    required = _need(d1, "required_fields", "data_contract.d1")
    if not isinstance(required, list) or len(required) == 0:
        raise ConfigError("data_contract.d1.required_fields must be a non-empty list")
    scenario_fields = _need(d1, "scenario_fields", "data_contract.d1")
    if not isinstance(scenario_fields, list) or len(scenario_fields) < 2:
        raise ConfigError("data_contract.d1.scenario_fields needs at least two scenarios")
    for field in scenario_fields:
        if field not in required:
            raise ConfigError(f"data_contract.d1.required_fields is missing {field}")
    weights = d1.get("scenario_weights", [1.0 / len(scenario_fields)] * len(scenario_fields))
    if len(weights) != len(scenario_fields):
        raise ConfigError("data_contract.d1.scenario_weights must match scenario_fields")
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
        block("capacity_compensation", capacity.get("status", "")),
        block("storage_participation"),
    ]
    if "negative_price" in rules:
        _rule_block(rules, "negative_price")
        provenance.append(block("negative_price"))
    if "vpp_threshold" in rules:
        _rule_block(rules, "vpp_threshold")
        provenance.append(block("vpp_threshold"))

    warnings = []
    if capacity.get("price_cny_per_kw_year") is None or capacity.get("supply_demand_coefficient") is None:
        warnings.append(
            "容量补偿未计入：补偿电价标准或容量供需系数为空；山东具体数值待核实。"
        )
    if effective > power + 1e-9:
        warnings.append("有效容量大于额定功率，请确认容量认定口径。")
    if not contracts:
        warnings.append("未配置中长期/CfD 合约；本切片按纯现货 + 容量补偿占位结算。")

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
        "scenario_fields": list(scenario_fields),
        "solver_states": states,
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
    scenario_fields = report["scenario_fields"]
    prices = []
    for field in scenario_fields:
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
    return {
        "date": rows[0]["date"],
        "slots": list(range(report["points_per_day"])),
        "prices": prices,
        "start": {slot: by_slot[slot]["start"] for slot in by_slot},
        "end": {slot: by_slot[slot]["end"] for slot in by_slot},
    }


def read_t1(path, config, report, power_mw):
    rows = _read_rows(path)
    t1 = config["data_contract"]["t1"]
    _check_shape(rows, t1["required_fields"], report["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    actual_price = []
    actual_discharge = []
    actual_charge = []
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
        discharge = _number(row["actual_discharge_mw"], f"{path.name}:actual_discharge_mw@slot{slot}", 0.0)
        charge = _number(row["actual_charge_mw"], f"{path.name}:actual_charge_mw@slot{slot}", 0.0)
        if discharge > power_mw + 1e-6 or charge > power_mw + 1e-6:
            raise ConfigError(f"{path.name}:slot {slot} exceeds asset.power_mw")
        if discharge > 1e-6 and charge > 1e-6:
            raise ConfigError(f"{path.name}:slot {slot} has simultaneous charge and discharge")
        actual_price.append(price)
        actual_discharge.append(discharge)
        actual_charge.append(charge)
    return {
        "date": rows[0]["date"],
        "price": actual_price,
        "discharge_mw": actual_discharge,
        "charge_mw": actual_charge,
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


def solve_scenario(prices, config, report):
    asset = config["asset"]
    eta = math.sqrt(float(asset["rte"]))
    grid = asset["grid_connection"]
    result = KERNEL.dispatch_day(
        [float(price) / 1000.0 for price in prices],
        [0.0] * len(prices),
        [0.0] * len(prices),
        sell_price=[float(price) / 1000.0 for price in prices],
        capacity_kwh=float(asset["energy_mwh"]) * 1000.0,
        power_charge_kw=float(asset["power_mw"]) * 1000.0,
        power_discharge_kw=float(asset["power_mw"]) * 1000.0,
        eta_charge=eta,
        eta_discharge=eta,
        soc_min=float(asset["soc_min"]),
        soc_max=float(asset["soc_max"]),
        soc_init=float(asset["soc_init"]),
        dt_h=report["mtu_min"] / 60.0,
        pcc_import_kw=float(grid["import_limit_mw"]) * 1000.0,
        pcc_export_kw=float(grid["export_limit_mw"]) * 1000.0,
        degradation_per_kwh=float(asset["degradation_cny_per_mwh_throughput"]) / 1000.0,
        terminal="cycle",
        states=report["solver_states"],
    )
    if not result["feasible"]:
        raise ConfigError(f"dispatch infeasible: {result.get('reason', 'unknown')}")
    return result


def repair_soc(discharge, charge, config, dt_h):
    """Trim a quantile-mixed schedule so it remains physically feasible."""
    asset = config["asset"]
    eta = math.sqrt(float(asset["rte"]))
    capacity = float(asset["energy_mwh"])
    low = float(asset["soc_min"]) * capacity
    high = float(asset["soc_max"]) * capacity
    energy = float(asset["soc_init"]) * capacity
    repairs = 0
    for slot in range(len(discharge)):
        if charge[slot] > 1e-9:
            room = max(0.0, high - energy)
            limit = room / (eta * dt_h)
            if charge[slot] > limit + 1e-9:
                charge[slot] = limit
                repairs += 1
            energy += charge[slot] * eta * dt_h
        if discharge[slot] > 1e-9:
            available = max(0.0, energy - low)
            limit = available * eta / dt_h
            if discharge[slot] > limit + 1e-9:
                discharge[slot] = limit
                repairs += 1
            energy -= discharge[slot] / eta * dt_h
    return discharge, charge, repairs, energy


def _contract_curve(config, points):
    if not config.get("contracts"):
        return [0.0] * points, 0.0, None
    contract = config["contracts"][0]
    quantity = contract["quantity_mw"]
    if isinstance(quantity, (list, tuple)):
        curve = [float(value) for value in quantity]
    else:
        curve = [float(quantity)] * points
    return curve, float(contract["price_cny_per_mwh"]), contract


def build_bid(prices_by_scenario, config, report):
    asset = config["asset"]
    policy = config["policy"]
    spot = config["rules"]["spot"]
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    weights = report["scenario_weights"]

    schedules = [solve_scenario(series, config, report) for series in prices_by_scenario]
    reference = [
        quantile([prices_by_scenario[s][t] for s in range(len(prices_by_scenario))], policy["price_reference_quantile"])
        for t in range(n)
    ]
    discharge = [
        quantile(
            [schedules[s]["schedule"]["p_discharge_kw"][t] / 1000.0 for s in range(len(schedules))],
            policy["declared_quantity_quantile"],
        )
        for t in range(n)
    ]
    charge = [
        quantile(
            [schedules[s]["schedule"]["p_charge_kw"][t] / 1000.0 for s in range(len(schedules))],
            policy["declared_quantity_quantile"],
        )
        for t in range(n)
    ]
    warnings = []
    for slot in range(n):
        if discharge[slot] > 1e-9 and charge[slot] > 1e-9:
            if discharge[slot] >= charge[slot]:
                discharge[slot] -= charge[slot]
                charge[slot] = 0.0
            else:
                charge[slot] -= discharge[slot]
                discharge[slot] = 0.0
            warnings.append(f"slot {slot}: scenario quantiles mixed charge and discharge; netted")

    spread = max(reference) - min(reference)
    if spread < float(policy["min_daily_spread_cny_per_mwh"]):
        discharge = [0.0] * n
        charge = [0.0] * n
        warnings.append(
            f"daily spread {spread:.1f} < policy minimum "
            f"{policy['min_daily_spread_cny_per_mwh']:.1f}; schedule zeroed"
        )

    throughput = sum(discharge[t] + charge[t] for t in range(n)) * dt_h
    cycles = throughput / (2.0 * float(asset["energy_mwh"]))
    if cycles > float(policy["max_cycles_per_day"]) + 1e-9:
        scale = float(policy["max_cycles_per_day"]) / cycles
        discharge = [value * scale for value in discharge]
        charge = [value * scale for value in charge]
        warnings.append(f"cycles {cycles:.3f} > policy cap; scaled by {scale:.4f}")

    discharge, charge, repairs, end_energy = repair_soc(discharge, charge, config, dt_h)
    if repairs:
        warnings.append(f"SOC repair trimmed {repairs} interval(s)")
    init_energy = float(asset["soc_init"]) * float(asset["energy_mwh"])
    if abs(end_energy - init_energy) > 0.01 * float(asset["energy_mwh"]):
        warnings.append("repaired schedule does not return to the initial SOC")

    offer = []
    bid = []
    offer_clip = []
    bid_clip = []
    for slot in range(n):
        markup = (
            float(policy["spike_markup_cny_per_mwh"])
            if reference[slot] >= float(policy["spike_threshold_cny_per_mwh"])
            else float(policy["discharge_markup_cny_per_mwh"])
        )
        raw_offer = reference[slot] + markup
        raw_bid = reference[slot] - float(policy["charge_markup_cny_per_mwh"])
        offer.append(
            min(report["bounds"]["declare_cap"], max(report["bounds"]["declare_floor"], raw_offer))
        )
        bid.append(
            min(report["bounds"]["declare_cap"], max(report["bounds"]["declare_floor"], raw_bid))
        )
        offer_clip.append(
            "floor" if raw_offer < report["bounds"]["declare_floor"] else "cap" if raw_offer > report["bounds"]["declare_cap"] else ""
        )
        bid_clip.append(
            "floor" if raw_bid < report["bounds"]["declare_floor"] else "cap" if raw_bid > report["bounds"]["declare_cap"] else ""
        )

    rows = []
    for slot in range(n):
        if discharge[slot] > 1e-6:
            probability = sum(
                weights[s]
                for s in range(len(weights))
                if prices_by_scenario[s][slot] >= offer[slot] - 1e-9
            )
            rows.append(
                {
                    "date": None,
                    "slot": slot,
                    "side": "discharge",
                    "quantity_mw": discharge[slot],
                    "price_cny_per_mwh": offer[slot],
                    "reference_price": reference[slot],
                    "clear_probability": probability,
                    "expected_mw": discharge[slot] * probability,
                    "note": (
                        f"q={policy['declared_quantity_quantile']:.2f}; "
                        f"markup={offer[slot] - reference[slot]:.1f}"
                        + (f"; {offer_clip[slot]}-clipped" if offer_clip[slot] else "")
                    ),
                }
            )
        if charge[slot] > 1e-6:
            probability = sum(
                weights[s]
                for s in range(len(weights))
                if prices_by_scenario[s][slot] <= bid[slot] + 1e-9
            )
            rows.append(
                {
                    "date": None,
                    "slot": slot,
                    "side": "charge",
                    "quantity_mw": charge[slot],
                    "price_cny_per_mwh": bid[slot],
                    "reference_price": reference[slot],
                    "clear_probability": probability,
                    "expected_mw": charge[slot] * probability,
                    "note": (
                        f"q={policy['declared_quantity_quantile']:.2f}; "
                        f"markup={reference[slot] - bid[slot]:.1f}"
                        + (f"; {bid_clip[slot]}-clipped" if bid_clip[slot] else "")
                    ),
                }
            )

    cycles = sum(discharge[t] + charge[t] for t in range(n)) * dt_h / (
        2.0 * float(asset["energy_mwh"])
    )
    return {
        "schedules": schedules,
        "reference": reference,
        "discharge": discharge,
        "charge": charge,
        "offer": offer,
        "bid": bid,
        "rows": rows,
        "warnings": warnings,
        "spread": spread,
        "cycles": cycles,
        "throughput_mwh": sum(discharge[t] + charge[t] for t in range(n)) * dt_h,
    }


def daily_capacity(config):
    block = config["rules"]["capacity_compensation"]
    price = block.get("price_cny_per_kw_year")
    coefficient = block.get("supply_demand_coefficient")
    if price is None or coefficient is None:
        return None
    effective = float(config["asset"].get("effective_capacity_mw", config["asset"]["power_mw"]))
    return effective * 1000.0 * float(price) * float(coefficient) / 365.0


def evaluate_plan(bid, prices_by_scenario, config, report, contract_curve, contract_price):
    asset = config["asset"]
    dt_h = report["mtu_min"] / 60.0
    weights = report["scenario_weights"]
    degradation = float(asset["degradation_cny_per_mwh_throughput"])
    fixed = float(asset.get("fixed_cost_cny_per_day", 0.0))
    capacity = daily_capacity(config)
    capacity_value = 0.0 if capacity is None else capacity
    n = report["points_per_day"]
    outcomes = []
    for index, prices in enumerate(prices_by_scenario):
        cleared_discharge = [
            bid["discharge"][t] if prices[t] >= bid["offer"][t] - 1e-9 else 0.0
            for t in range(n)
        ]
        cleared_charge = [
            bid["charge"][t] if prices[t] <= bid["bid"][t] + 1e-9 else 0.0
            for t in range(n)
        ]
        spot = sum(
            (cleared_discharge[t] - cleared_charge[t]) * prices[t] * dt_h
            for t in range(n)
        )
        throughput = sum(cleared_discharge[t] + cleared_charge[t] for t in range(n)) * dt_h
        degradation_cost = throughput * degradation
        contract = sum(
            contract_curve[t] * (contract_price - prices[t]) * dt_h for t in range(n)
        )
        net = spot + contract - degradation_cost + capacity_value - fixed
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "mean_price": sum(prices) / n,
                "cleared_discharge_mwh": sum(cleared_discharge) * dt_h,
                "cleared_charge_mwh": sum(cleared_charge) * dt_h,
                "spot_margin_cny": spot,
                "contract_cny": contract,
                "degradation_cny": degradation_cost,
                "capacity_cny": capacity_value,
                "fixed_cost_cny": fixed,
                "net_margin_cny": net,
            }
        )
    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    cvar = desk.weighted_cvar([(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=0.10)
    reference_spot = sum(
        (bid["discharge"][t] - bid["charge"][t]) * bid["reference"][t] * dt_h
        for t in range(n)
    )
    reference_degradation = bid["throughput_mwh"] * degradation
    reference_contract = sum(
        contract_curve[t] * (contract_price - bid["reference"][t]) * dt_h
        for t in range(n)
    )
    reference_net = (
        reference_spot - reference_degradation + reference_contract + capacity_value - fixed
    )
    return {
        "outcomes": outcomes,
        "expected_net_margin_cny": expected,
        "cvar_10_cny": cvar,
        "spot_margin_at_reference_cny": reference_spot,
        "degradation_at_reference_cny": reference_degradation,
        "capacity_compensation_cny": capacity,
        "fixed_cost_cny": fixed,
        "net_margin_at_reference_cny": reference_net,
        "expected_discharge_mwh": sum(
            bid["discharge"][t] * sum(
                weights[s]
                for s in range(len(weights))
                if prices_by_scenario[s][t] >= bid["offer"][t] - 1e-9
            )
            for t in range(n)
        ) * dt_h,
        "expected_charge_mwh": sum(
            bid["charge"][t] * sum(
                weights[s]
                for s in range(len(weights))
                if prices_by_scenario[s][t] <= bid["bid"][t] + 1e-9
            )
            for t in range(n)
        ) * dt_h,
    }


def build_bridge(bid, t1, config, report, contract_curve, contract_price):
    capacity = daily_capacity(config)
    capacity_value = 0.0 if capacity is None else capacity
    plan = {
        "price": bid["reference"],
        "discharge_mw": bid["discharge"],
        "charge_mw": bid["charge"],
    }
    actual = {
        "price": t1["price"],
        "discharge_mw": t1["discharge_mw"],
        "charge_mw": t1["charge_mw"],
    }
    return desk.storage_bridge(
        plan,
        actual,
        dt_h=report["mtu_min"] / 60.0,
        degradation_per_mwh=float(config["asset"]["degradation_cny_per_mwh_throughput"]),
        contract_quantity_mw=contract_curve,
        contract_price=contract_price,
        capacity_plan=capacity_value,
        capacity_actual=capacity_value,
    )


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
        if field in ("quantity_mw", "expected_mw"):
            return f"{value:.3f}"
        if field in ("price_cny_per_mwh", "reference_price"):
            return f"{value:.2f}"
        if field == "clear_probability":
            return f"{value:.3f}"
        if field in ("amount", "quantity_effect_cny"):
            return f"{_signed(value):.2f}"
        return f"{value:.6f}"
    return value


def build_bridge_detail(bid, t1, report):
    dt_h = report["mtu_min"] / 60.0
    detail = []
    for slot in range(report["points_per_day"]):
        delta_discharge = t1["discharge_mw"][slot] - bid["discharge"][slot]
        delta_charge = t1["charge_mw"][slot] - bid["charge"][slot]
        detail.append(
            {
                "slot": slot,
                "start": _slot_time(slot, report["mtu_min"]),
                "plan_discharge_mw": bid["discharge"][slot],
                "actual_discharge_mw": t1["discharge_mw"][slot],
                "plan_charge_mw": bid["charge"][slot],
                "actual_charge_mw": t1["charge_mw"][slot],
                "quantity_effect_cny": bid["reference"][slot]
                * (delta_discharge - delta_charge)
                * dt_h,
            }
        )
    detail.sort(key=lambda item: abs(item["quantity_effect_cny"]), reverse=True)
    return detail[:5]


def write_review(path, config, report, d1, bid, evaluation, bridge, bridge_detail, policy_fingerprint):
    policy = config["policy"]
    asset = config["asset"]
    dt_h = report["mtu_min"] / 60.0
    lines = [
        f"# 山东独立储能复核表：{config['meta']['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']} 分钟）",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格档：`{policy['profile_id']}` / 指纹 `{policy_fingerprint}`",
        f"- 资产：{asset['power_mw']:.0f} MW / {asset['energy_mwh']:.0f} MWh，RTE {asset['rte']:.2f}，SOC {asset['soc_min']:.2f}–{asset['soc_max']:.2f}",
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
        "## 2. 申报摘要",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 申报放电量 | {sum(bid['discharge']) * dt_h:.1f} MWh |",
        f"| 申报充电量 | {sum(bid['charge']) * dt_h:.1f} MWh |",
        f"| 等效循环 | {bid['cycles']:.2f} 次 |",
        f"| 日价差（参考价） | {bid['spread']:.1f} CNY/MWh |",
        f"| 期望放电量（按情景清算） | {evaluation['expected_discharge_mwh']:.1f} MWh |",
        f"| 期望充电量（按情景清算） | {evaluation['expected_charge_mwh']:.1f} MWh |",
        f"| 参考价口径净边际 | {_money(evaluation['net_margin_at_reference_cny'])} CNY |",
        f"| 情景期望净边际 | {_money(evaluation['expected_net_margin_cny'])} CNY |",
        f"| 情景 CVaR10 | {_money(evaluation['cvar_10_cny'])} CNY |",
        f"| 容量补偿 | {_money(evaluation['capacity_compensation_cny'])} CNY |",
        "",
        "## 3. 情景清算",
        "",
        "| 情景 | 权重 | 均价 | 清算放电 | 清算充电 | 现货边际 | 合约 | 退化 | 净边际 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in evaluation["outcomes"]:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['mean_price']:.1f} | "
            f"{item['cleared_discharge_mwh']:.1f} | {item['cleared_charge_mwh']:.1f} | "
            f"{item['spot_margin_cny']:,.0f} | {item['contract_cny']:,.0f} | "
            f"{item['degradation_cny']:,.0f} | {item['net_margin_cny']:,.0f} |"
        )
    lines += [
        "",
        "> 读法：CVaR10 为负说明该风格在低价情景下充电但不放电，这是尖峰加价的代价，不是算术错误。",
    ]
    if bridge is None:
        lines += ["", "## 4. T+1 差异桥", "", "未提供 T+1 实际数据，本次只出申报表。"]
    else:
        ordered = sorted(bridge["buckets"], key=lambda item: abs(item["amount"]), reverse=True)
        lines += [
            "",
            "## 4. T+1 差异桥",
            "",
            f"计划利润 {bridge['plan_profit']:,.0f} CNY，实际利润 {bridge['actual_profit']:,.0f} CNY，差异 {bridge['delta']:,.0f} CNY，残差 {bridge['identity_gap']:.2e}。",
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
        ]
        if bridge_detail:
            lines += [
                "**量偏差最大的 5 个时段**（按参考价折算的量影响）：",
                "",
                "| 时段 | 计划放电 | 实际放电 | 计划充电 | 实际充电 | 量影响（CNY） |",
                "|---|---:|---:|---:|---:|---:|",
            ]
            for item in bridge_detail:
                lines.append(
                    f"| {item['start']} | {item['plan_discharge_mw']:.1f} | {item['actual_discharge_mw']:.1f} | "
                    f"{item['plan_charge_mw']:.1f} | {item['actual_charge_mw']:.1f} | "
                    f"{_signed(item['quantity_effect_cny']):,.0f} |"
                )
    lines += [
        "",
        "## 5. 三个复核问题",
        "",
        "1. 最大差异科目归因到价、量、执行、口径还是规则版本？证据包是否齐全？",
        "2. 申报量分位、放电加价、充电压价、尖峰加价是否与本风格档一致？如有 override，记录触发条件。",
        "3. 容量补偿、辅助服务、中长期曲线分解是否仍未纳入？下一版实例包要不要接入？",
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
    d1_path = Path(d1_path)
    d1 = read_d1(d1_path, config, report)
    if t1_path is not None:
        t1 = read_t1(Path(t1_path), config, report, float(config["asset"]["power_mw"]))
        if t1["date"] != d1["date"]:
            raise ConfigError("D-1 and T+1 files must refer to the same trading day")
    else:
        t1 = None

    bid = build_bid(d1["prices"], config, report)
    contract_curve, contract_price, contract = _contract_curve(config, report["points_per_day"])
    evaluation = evaluate_plan(bid, d1["prices"], config, report, contract_curve, contract_price)
    bridge = None
    bridge_detail = None
    if t1 is not None:
        bridge = build_bridge(bid, t1, config, report, contract_curve, contract_price)
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
        "quantity_mw",
        "price_cny_per_mwh",
        "reference_price",
        "clear_probability",
        "expected_mw",
        "note",
    ]
    _write_csv(out_dir / "bid_sheet.csv", bid["rows"], bid_fields)

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": policy_fingerprint,
        "provenance": report["provenance"],
        "plan": {
            "discharge_mwh": sum(bid["discharge"]) * (report["mtu_min"] / 60.0),
            "charge_mwh": sum(bid["charge"]) * (report["mtu_min"] / 60.0),
            "equivalent_cycles": bid["cycles"],
            "daily_spread_cny_per_mwh": bid["spread"],
            "expected_discharge_mwh": evaluation["expected_discharge_mwh"],
            "expected_charge_mwh": evaluation["expected_charge_mwh"],
            "spot_margin_at_reference_cny": evaluation["spot_margin_at_reference_cny"],
            "degradation_at_reference_cny": evaluation["degradation_at_reference_cny"],
            "capacity_compensation_cny": evaluation["capacity_compensation_cny"],
            "fixed_cost_cny": evaluation["fixed_cost_cny"],
            "net_margin_at_reference_cny": evaluation["net_margin_at_reference_cny"],
            "expected_net_margin_cny": evaluation["expected_net_margin_cny"],
            "cvar_10_cny": evaluation["cvar_10_cny"],
            "scenarios": evaluation["outcomes"],
        },
        "contract": None if contract is None else {
            "id": contract["id"],
            "price_cny_per_mwh": contract_price,
            "quantity_mwh": sum(contract_curve) * (report["mtu_min"] / 60.0),
            "grade": contract["grade"],
            "source": contract["source"],
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
            "plan_spot": bridge["plan_spot"],
            "actual_spot": bridge["actual_spot"],
            "plan_contract": bridge["plan_contract"],
            "actual_contract": bridge["actual_contract"],
            "plan_degradation": bridge["plan_degradation"],
            "actual_degradation": bridge["actual_degradation"],
            "plan_throughput_mwh": bridge["plan_throughput_mwh"],
            "actual_throughput_mwh": bridge["actual_throughput_mwh"],
            "buckets": [
                {
                    "item": item["item"],
                    "category": item["category"],
                    "owner": item["owner"],
                    "amount": item["amount"],
                }
                for item in bridge["buckets"]
            ],
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
    parser = argparse.ArgumentParser(description="Shandong standalone-storage instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", help="D-1 96-point scenario CSV")
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
        f"申报：放电 {plan['discharge_mwh']:.1f} MWh，充电 {plan['charge_mwh']:.1f} MWh，"
        f"{plan['equivalent_cycles']:.2f} 次循环"
    )
    print(
        f"情景：期望净边际 {plan['expected_net_margin_cny']:,.0f} CNY，"
        f"CVaR10 {plan['cvar_10_cny']:,.0f} CNY"
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
