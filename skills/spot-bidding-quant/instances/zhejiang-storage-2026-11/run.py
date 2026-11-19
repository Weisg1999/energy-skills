#!/usr/bin/env python3
"""Run the Zhejiang standalone-storage instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the Zhejiang spot rule parameters (price band
  -200..1,200 CNY/MWh from the annual-report / draft wording, 5-minute rolling
  clearing, the ~90% authorized CFD coverage), asset, policy profile and data
  contract. A trader edits it; no code change is needed for a new asset or a
  new style profile.
* ``data/d1_demo.csv`` is a 288-point, five-scenario day-ahead price set
  (5-minute market time unit, midday trough + evening peak shape).
* ``data/t1_demo.csv`` is the T+1 day-ahead price, real-time price and metered
  charge/discharge.

The SOC-aware optimiser is the existing ``ems-dispatch/tools/dispatch.py``
kernel. This runner adds scenario quantiles, bid-sheet translation, a
price-taker evaluation, a two-settlement T+1 bridge, a midday negative-price
stress test and the review sheet.

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
    spec = importlib.util.spec_from_file_location("ems_dispatch_kernel_zj", path)
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


def _minutes_of_day(text, path):
    if not isinstance(text, str) or ":" not in text:
        raise ConfigError(f"{path} must be HH:MM")
    hour_text, minute_text = text.split(":", 1)
    try:
        hour, minute = int(hour_text), int(minute_text)
    except ValueError:
        raise ConfigError(f"{path} must be HH:MM")
    if not (0 <= hour <= 24 and 0 <= minute < 60):
        raise ConfigError(f"{path} is outside 00:00-24:00")
    return hour * 60 + minute


def validate_instance(config):
    """Validate the config blocks and return a provenance report."""
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot")
    _rule_block(rules, "settlement")
    cfd = _rule_block(rules, "authorized_cfd")
    participation = _rule_block(rules, "storage_participation")
    price_features = _rule_block(rules, "price_features")
    capacity = _rule_block(rules, "capacity_compensation")

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = int(_number(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1))
    expected_points = 24 * 60 / mtu
    if abs(expected_points - points) > 1e-9:
        raise ConfigError(
            f"rules.spot.points_per_day ({points}) does not match 24*60/{mtu:g}"
        )
    if mtu != 5 or points != 288:
        raise ConfigError(
            "Zhejiang spot clearing is 5-minute rolling (module §4.2, grade C; "
            "§9.1: model storage on 5-minute prices); "
            "do not reuse the 15-minute / 96-point template"
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
    if (declare_floor, declare_cap, clear_floor, clear_cap) != (-200.0, 1200.0, -200.0, 1200.0):
        raise ConfigError(
            "the Zhejiang band -200..1,200 CNY/MWh is the annual-report / draft "
            "wording (grade B/C, formal parameter unverified); negative prices "
            "are allowed and the VPP demand-response 0-1,200 CNY/MW band is a "
            "different market and unit"
        )
    if not (clear_floor <= declare_floor < declare_cap <= clear_cap):
        raise ConfigError(
            "price bounds must satisfy clear_floor <= declare_floor < declare_cap <= clear_cap"
        )
    if spot.get("negative_price_allowed") is not True:
        raise ConfigError(
            "the Zhejiang band allows negative prices down to -200 CNY/MWh; "
            "negative_price_allowed must stay true"
        )

    stress = _need(spot, "stress_assumption", "rules.spot")
    window_start = _minutes_of_day(
        _need(stress, "window_start", "rules.spot.stress_assumption"),
        "rules.spot.stress_assumption.window_start",
    )
    window_end = _minutes_of_day(
        _need(stress, "window_end", "rules.spot.stress_assumption.window_end"),
        "rules.spot.stress_assumption.window_end",
    )
    if window_end <= window_start:
        raise ConfigError("negative-price stress window_end must be after window_start")
    if window_start % mtu or window_end % mtu:
        raise ConfigError("negative-price stress window must align to the 5-minute market time unit")
    stress_price = _number(
        _need(stress, "settlement_price_cny_per_mwh", "rules.spot.stress_assumption"),
        "rules.spot.stress_assumption.settlement_price_cny_per_mwh",
        clear_floor,
        0.0,
    )
    if stress_price >= 0.0:
        raise ConfigError(
            "the midday stress must reprice the window at a negative price inside "
            "[clear_floor, 0); the module only grades the midday low/negative risk B"
        )

    coverage = _number(
        _need(cfd, "coverage_share_of_energy", "rules.authorized_cfd"),
        "rules.authorized_cfd.coverage_share_of_energy",
        0.0,
        1.0,
    )
    if abs(coverage - 0.9) > 0.05:
        raise ConfigError(
            "the authorized CFD covers about 90% of energy (module grade B, "
            "double-difference settlement); do not change the share silently"
        )
    _text(cfd, "settlement_type", "rules.authorized_cfd")
    if cfd.get("applicable_to_storage") is not None:
        raise ConfigError(
            "storage coverage under the authorized CFD is unverified in the module; "
            "keep applicable_to_storage null and run the storage position as full "
            "spot exposure"
        )

    _text(participation, "requirement", "rules.storage_participation")
    _text(participation, "vpp_route", "rules.storage_participation")
    if participation.get("admission_conditions") is not None:
        raise ConfigError(
            "storage admission conditions are not graded in the module; keep "
            "admission_conditions null and use admission_status"
        )

    mlt = _number(
        _need(price_features, "mid_long_term_2025_cny_per_mwh", "rules.price_features"),
        "rules.price_features.mid_long_term_2025_cny_per_mwh",
    )
    annual = _number(
        _need(price_features, "annual_2025_cny_per_mwh", "rules.price_features"),
        "rules.price_features.annual_2025_cny_per_mwh",
    )
    monthly = _number(
        _need(price_features, "monthly_2025_cny_per_mwh", "rules.price_features"),
        "rules.price_features.monthly_2025_cny_per_mwh",
    )
    if abs(mlt - 390.73) > 0.01 or abs(annual - 412.39) > 0.01 or abs(monthly - 370.43) > 0.01:
        raise ConfigError(
            "2025 mid/long-term averages must be 412.39 (annual, A), 390.73 (total, B) "
            "and 370.43 (monthly, C) CNY/MWh"
        )
    if not annual > mlt > monthly:
        raise ConfigError(
            "the 2025 term structure must be annual > total > monthly "
            "(the shorter the term, the lower the average price)"
        )
    tou_before = _number(
        _need(price_features, "tou_spread_before_112_cny_per_kwh", "rules.price_features"),
        "rules.price_features.tou_spread_before_112_cny_per_kwh",
    )
    tou_after = _number(
        _need(price_features, "tou_spread_after_112_cny_per_kwh", "rules.price_features"),
        "rules.price_features.tou_spread_after_112_cny_per_kwh",
    )
    if not tou_after < tou_before:
        raise ConfigError(
            "the TOU spread must narrow after document 112 (about 0.83 -> 0.50 CNY/kWh, "
            "grade C); two-charge-two-discharge gives way to one-charge-one-discharge"
        )
    mechanism = _number(
        _need(price_features, "mechanism_price_2026_first_cny_per_mwh", "rules.price_features"),
        "rules.price_features.mechanism_price_2026_first_cny_per_mwh",
    )
    if not 242.0 <= mechanism <= 393.0:
        raise ConfigError(
            "the 2026 first mechanism auction cleared 381.6 CNY/MWh inside the "
            "242-393 CNY/MWh band; it is a new-energy settlement price, not a "
            "storage revenue"
        )
    if price_features.get("spot_average_price") is not None:
        raise ConfigError(
            "the module has no Zhejiang spot time-of-day average price; keep "
            "spot_average_price null and do not substitute mid/long-term averages"
        )

    if capacity.get("applicable_to_storage") is not False:
        raise ConfigError("independent storage must not book any capacity payment")
    if capacity.get("price_cny_per_kw_year") is not None:
        raise ConfigError(
            "coal/independent-storage capacity price is unverified in Zhejiang; keep it "
            "null, the 136 mechanism price and the TOU spread are not capacity revenue"
        )
    if capacity.get("supply_demand_coefficient") is not None:
        raise ConfigError("capacity supply-demand coefficient is unverified; keep it null")

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
    fixed = _number(asset.get("fixed_cost_cny_per_day", 0.0), "asset.fixed_cost_cny_per_day", 0.0)
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
    if contracts:
        raise ConfigError(
            "Zhejiang v1 covers spot energy only; mid/long-term curves and "
            "authorized-CFD positions are not modelled"
        )

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
    t1 = _need(data_contract, "t1", "data_contract")
    _text(t1, "file", "data_contract.t1")
    t1_required = _need(t1, "required_fields", "data_contract.t1")
    if not isinstance(t1_required, list) or len(t1_required) == 0:
        raise ConfigError("data_contract.t1.required_fields must be a non-empty list")
    for field in ("date", "slot", "da_price", "rt_price", "actual_discharge_mw", "actual_charge_mw"):
        if field not in t1_required:
            raise ConfigError(
                f"data_contract.t1.required_fields must include {field} for two-settlement"
            )

    def block(name, extra=""):
        item = {"block": f"rules.{name}", "grade": rules[name]["grade"], "source": rules[name]["source"]}
        if extra:
            item["status"] = extra
        return item

    provenance = [
        block("spot"),
        block("settlement"),
        block("authorized_cfd", cfd.get("status", "")),
        block("storage_participation", participation.get("admission_status", "")),
        block("price_features", price_features.get("spot_average_status", "")),
        block("capacity_compensation", capacity.get("status", "")),
    ]

    warnings = [
        "限价 −200–1,200 元/MWh 为年报/征求意见稿口径（B/C）；省级正式规则现行参数待核实，且不能与 VPP 响应 0–1,200 元/MW 混淆",
        "独立储能是否纳入授权差价合约覆盖、双差价完整公式未核实；本包按储能无授权合约头寸、全额现货暴露计算",
        "煤电/独立储能容量电价省级文件未核到；本包容量收入按 0 计，不把 136 机制电价或分时价差当容量收入",
        "午间负价窗口与重算价是 D 级压力假设；模块只说午间低价/负价风险上升（B），未给时段与频次",
        "模块未给浙江现货分时均价；不要用中长期均价 390.73 元/MWh 倒推现货均价",
        "中长期曲线分解、零售、需求响应/AGC 收入未纳入；本切片只做省内现货电能量",
    ]
    if effective > power + 1e-9:
        warnings.append("有效容量大于额定功率，请确认容量认定口径。")
    if fixed > 0:
        warnings.append("固定成本按日分摊，仅影响净收益，不影响充放电策略。")

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
        "stress": {
            "window_start_min": window_start,
            "window_end_min": window_end,
            "window_start": stress["window_start"],
            "window_end": stress["window_end"],
            "settlement_price": stress_price,
            "duration_hours": (window_end - window_start) / 60.0,
        },
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
    da_price = []
    rt_price = []
    actual_discharge = []
    actual_charge = []
    for slot in range(report["points_per_day"]):
        row = by_slot[slot]
        da = _number(row["da_price"], f"{path.name}:da_price@slot{slot}")
        rt = _number(row["rt_price"], f"{path.name}:rt_price@slot{slot}")
        for label, price in (("da_price", da), ("rt_price", rt)):
            if not (
                report["bounds"]["clear_floor"] - 0.01
                <= price
                <= report["bounds"]["clear_cap"] + 0.01
            ):
                raise ConfigError(
                    f"{path.name}:{label}@slot{slot}={price} is outside the clearing band"
                )
        discharge = _number(row["actual_discharge_mw"], f"{path.name}:actual_discharge_mw@slot{slot}", 0.0)
        charge = _number(row["actual_charge_mw"], f"{path.name}:actual_charge_mw@slot{slot}", 0.0)
        if discharge > power_mw + 1e-6 or charge > power_mw + 1e-6:
            raise ConfigError(f"{path.name}:slot {slot} exceeds asset.power_mw")
        if discharge > 1e-6 and charge > 1e-6:
            raise ConfigError(f"{path.name}:slot {slot} has simultaneous charge and discharge")
        da_price.append(da)
        rt_price.append(rt)
        actual_discharge.append(discharge)
        actual_charge.append(charge)
    return {
        "date": rows[0]["date"],
        "da_price": da_price,
        "rt_price": rt_price,
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


def build_bid(prices_by_scenario, config, report):
    asset = config["asset"]
    policy = config["policy"]
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

    # Scenario quantiles can break the charge/discharge energy balance even
    # when every input schedule is cycle-terminal. Trim the larger leg so the
    # declared schedule cannot create energy out of round-trip efficiency.
    rte = float(asset["rte"])
    charge_energy = sum(charge) * dt_h
    discharge_energy = sum(discharge) * dt_h
    if discharge_energy > charge_energy * rte + 1e-9:
        factor = (charge_energy * rte) / discharge_energy if discharge_energy > 0 else 0.0
        discharge = [value * factor for value in discharge]
        warnings.append(
            f"declared discharge trimmed by {1.0 - factor:.4f} to respect charge x RTE"
        )
    elif charge_energy > discharge_energy / rte + 1e-9:
        factor = (discharge_energy / rte) / charge_energy if charge_energy > 0 else 0.0
        charge = [value * factor for value in charge]
        warnings.append(
            f"declared charge trimmed by {1.0 - factor:.4f} to respect discharge / RTE"
        )

    offer = []
    bid = []
    offer_clip = []
    bid_clip = []
    degradation = float(asset["degradation_cny_per_mwh_throughput"])
    discharge_slots = [t for t in range(n) if discharge[t] > 1e-6]
    charge_slots = [t for t in range(n) if charge[t] > 1e-6]
    charge_anchor = min((reference[t] for t in charge_slots), default=min(reference))
    discharge_anchor = max((reference[t] for t in discharge_slots), default=max(reference))
    discharge_breakeven = charge_anchor / rte + degradation * (1.0 + 1.0 / rte)
    charge_breakeven = discharge_anchor * rte - degradation * (1.0 + rte)
    for slot in range(n):
        markup = (
            float(policy["spike_markup_cny_per_mwh"])
            if reference[slot] >= float(policy["spike_threshold_cny_per_mwh"])
            else float(policy["discharge_markup_cny_per_mwh"])
        )
        raw_offer = discharge_breakeven + markup
        raw_bid = charge_breakeven - float(policy["charge_markup_cny_per_mwh"])
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
                        f"offer={offer[slot]:.1f}; breakeven={discharge_breakeven:.1f}"
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
                        f"bid={bid[slot]:.1f}; breakeven={charge_breakeven:.1f}"
                        + (f"; {bid_clip[slot]}-clipped" if bid_clip[slot] else "")
                    ),
                }
            )

    cycles = sum(discharge[t] + charge[t] for t in range(n)) * dt_h / (
        2.0 * float(asset["energy_mwh"])
    )
    switches = 0
    previous = 0
    for slot in range(n):
        net = discharge[slot] - charge[slot]
        if abs(net) <= 1e-9:
            continue
        sign = 1 if net > 0 else -1
        if previous and sign != previous:
            switches += 1
        previous = sign
    mean_interval_change = (
        sum(abs((discharge[t] - charge[t]) - (discharge[t - 1] - charge[t - 1])) for t in range(1, n))
        / max(1, n - 1)
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
        "switches": switches,
        "mean_interval_change_mw": mean_interval_change,
        "charge_anchor_cny_per_mwh": charge_anchor,
        "discharge_anchor_cny_per_mwh": discharge_anchor,
        "discharge_breakeven_cny_per_mwh": discharge_breakeven,
        "charge_breakeven_cny_per_mwh": charge_breakeven,
    }


def daily_capacity(config):
    block = config["rules"]["capacity_compensation"]
    if block.get("applicable_to_storage") is False:
        return None
    price = block.get("price_cny_per_kw_year")
    coefficient = block.get("supply_demand_coefficient")
    if price is None or coefficient is None:
        return None
    effective = float(config["asset"].get("effective_capacity_mw", config["asset"]["power_mw"]))
    return effective * 1000.0 * float(price) * float(coefficient) / 365.0


def evaluate_plan(bid, prices_by_scenario, config, report):
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
        rte = float(asset["rte"])
        discharge_energy = sum(cleared_discharge) * dt_h
        charge_energy = sum(cleared_charge) * dt_h
        rebalanced = False
        if discharge_energy > charge_energy * rte + 1e-9:
            scale = (charge_energy * rte) / discharge_energy if discharge_energy > 0 else 0.0
            cleared_discharge = [value * scale for value in cleared_discharge]
            rebalanced = True
        if charge_energy > discharge_energy / rte + 1e-9:
            scale = (discharge_energy / rte) / charge_energy if charge_energy > 0 else 0.0
            cleared_charge = [value * scale for value in cleared_charge]
            rebalanced = True
        spot = sum(
            (cleared_discharge[t] - cleared_charge[t]) * prices[t] * dt_h
            for t in range(n)
        )
        throughput = sum(cleared_discharge[t] + cleared_charge[t] for t in range(n)) * dt_h
        degradation_cost = throughput * degradation
        net = spot - degradation_cost + capacity_value - fixed
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "mean_price": sum(prices) / n,
                "cleared_discharge_mwh": sum(cleared_discharge) * dt_h,
                "cleared_charge_mwh": sum(cleared_charge) * dt_h,
                "spot_margin_cny": spot,
                "degradation_cny": degradation_cost,
                "capacity_cny": capacity_value,
                "fixed_cost_cny": fixed,
                "net_margin_cny": net,
                "rebalanced": rebalanced,
            }
        )
    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    cvar = desk.weighted_cvar([(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=0.10)
    reference_spot = sum(
        (bid["discharge"][t] - bid["charge"][t]) * bid["reference"][t] * dt_h
        for t in range(n)
    )
    reference_degradation = bid["throughput_mwh"] * degradation
    reference_net = reference_spot - reference_degradation + capacity_value - fixed
    return {
        "outcomes": outcomes,
        "expected_net_margin_cny": expected,
        "cvar_10_cny": cvar,
        "spot_margin_at_reference_cny": reference_spot,
        "degradation_at_reference_cny": reference_degradation,
        "capacity_compensation_cny": capacity,
        "fixed_cost_cny": fixed,
        "net_margin_at_reference_cny": reference_net,
    }


def settle_actual(bid, t1, config, report):
    asset = config["asset"]
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    degradation = float(asset["degradation_cny_per_mwh_throughput"])
    fixed = float(asset.get("fixed_cost_cny_per_day", 0.0))
    capacity = daily_capacity(config)
    capacity_value = 0.0 if capacity is None else capacity
    plan_net = [bid["discharge"][t] - bid["charge"][t] for t in range(n)]
    actual_net = [t1["discharge_mw"][t] - t1["charge_mw"][t] for t in range(n)]
    spot = sum(
        plan_net[t] * t1["da_price"][t] + (actual_net[t] - plan_net[t]) * t1["rt_price"][t]
        for t in range(n)
    ) * dt_h
    throughput = sum(t1["discharge_mw"][t] + t1["charge_mw"][t] for t in range(n)) * dt_h
    degradation_cost = throughput * degradation
    net = spot - degradation_cost + capacity_value - fixed
    return {
        "spot_cny": spot,
        "degradation_cny": degradation_cost,
        "capacity_cny": capacity_value,
        "fixed_cost_cny": fixed,
        "net_margin_cny": net,
        "throughput_mwh": throughput,
        "discharge_energy_mwh": sum(t1["discharge_mw"]) * dt_h,
        "charge_energy_mwh": sum(t1["charge_mw"]) * dt_h,
        "revenue_per_discharge_mwh": (
            spot / (sum(t1["discharge_mw"]) * dt_h)
            if sum(t1["discharge_mw"]) > 0
            else None
        ),
        "da_energy_weighted_price_cny_per_mwh": (
            sum(abs(plan_net[t]) * t1["da_price"][t] for t in range(n))
            / sum(abs(plan_net[t]) for t in range(n))
            if sum(abs(value) for value in plan_net) > 0
            else None
        ),
        "rt_energy_weighted_price_cny_per_mwh": (
            sum(abs(actual_net[t]) * t1["rt_price"][t] for t in range(n))
            / sum(abs(actual_net[t]) for t in range(n))
            if sum(abs(value) for value in actual_net) > 0
            else None
        ),
    }


def build_bridge(bid, t1, plan, actual, config, report):
    """Four buckets: DA price, DA quantity, RT spread, degradation."""
    n = report["points_per_day"]
    dt_h = report["mtu_min"] / 60.0
    degradation = float(config["asset"]["degradation_cny_per_mwh_throughput"])
    plan_net = [bid["discharge"][t] - bid["charge"][t] for t in range(n)]
    actual_net = [t1["discharge_mw"][t] - t1["charge_mw"][t] for t in range(n)]
    deviation = [actual_net[t] - plan_net[t] for t in range(n)]
    buckets = [
        {
            "item": "日前价格偏差",
            "category": "价格",
            "owner": "交易",
            "amount": sum(
                plan_net[t] * (t1["da_price"][t] - bid["reference"][t]) for t in range(n)
            )
            * dt_h,
        },
        {
            "item": "日前计划量差",
            "category": "电量",
            "owner": "预测/执行",
            "amount": sum(deviation[t] * t1["da_price"][t] for t in range(n)) * dt_h,
        },
        {
            "item": "实时偏差价差",
            "category": "价格",
            "owner": "市场",
            "amount": sum(
                deviation[t] * (t1["rt_price"][t] - t1["da_price"][t]) for t in range(n)
            )
            * dt_h,
        },
        {
            "item": "退化成本偏差",
            "category": "成本",
            "owner": "运维",
            "amount": -degradation * (actual["throughput_mwh"] - bid["throughput_mwh"]),
        },
    ]
    plan_profit = plan["net_margin_at_reference_cny"]
    actual_profit = actual["net_margin_cny"]
    total = sum(item["amount"] for item in buckets)
    return {
        "plan_profit": plan_profit,
        "actual_profit": actual_profit,
        "delta": actual_profit - plan_profit,
        "identity_gap": actual_profit - plan_profit - total,
        "plan_spot": plan["spot_margin_at_reference_cny"],
        "actual_spot": actual["spot_cny"],
        "plan_throughput_mwh": bid["throughput_mwh"],
        "actual_throughput_mwh": actual["throughput_mwh"],
        "buckets": buckets,
    }


def midday_stress(bid, t1, actual, config, report):
    """D-level stress: reprices the midday PV-surplus window at a negative price.

    The module says full new-energy market entry raises the midday low/negative
    price risk (grade B) but gives no window, frequency or duration. The
    assumption here is deliberately simple and labelled: actual net injection
    in the window is settled at one configured negative price, with no separate
    day-ahead leg. It is a stress test, not a settlement rule. Negative prices
    pay the charge leg and punish any discharge left in the window.
    """
    stress = report["stress"]
    mtu = report["mtu_min"]
    dt_h = mtu / 60.0
    start_slot = int(stress["window_start_min"] // mtu)
    end_slot = int(stress["window_end_min"] // mtu)
    price = stress["settlement_price"]
    n = report["points_per_day"]
    plan_net = [bid["discharge"][t] - bid["charge"][t] for t in range(n)]
    base_window = 0.0
    stress_window = 0.0
    charge_window = 0.0
    discharge_window = 0.0
    negative_rt_slots = 0
    for slot in range(start_slot, end_slot):
        actual_net = t1["discharge_mw"][slot] - t1["charge_mw"][slot]
        base_window += (
            plan_net[slot] * t1["da_price"][slot]
            + (actual_net - plan_net[slot]) * t1["rt_price"][slot]
        ) * dt_h
        stress_window += actual_net * price * dt_h
        charge_window += t1["charge_mw"][slot] * dt_h
        discharge_window += t1["discharge_mw"][slot] * dt_h
        if t1["rt_price"][slot] < 0.0:
            negative_rt_slots += 1
    delta = stress_window - base_window
    return {
        "window_start": stress["window_start"],
        "window_end": stress["window_end"],
        "duration_hours": stress["duration_hours"],
        "settlement_price_cny_per_mwh": price,
        "base_window_cny": base_window,
        "stress_window_cny": stress_window,
        "delta_cny": delta,
        "base_net_margin_cny": actual["net_margin_cny"],
        "stress_net_margin_cny": actual["net_margin_cny"] + delta,
        "charge_window_mwh": charge_window,
        "discharge_window_mwh": discharge_window,
        "negative_rt_slots": negative_rt_slots,
    }


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


def write_review(path, config, report, d1, bid, evaluation, actual, bridge, stress, bridge_detail, policy_fingerprint):
    policy = config["policy"]
    asset = config["asset"]
    dt_h = report["mtu_min"] / 60.0
    lines = [
        f"# 浙江独立新型储能复核表：{config['meta']['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']} 分钟）",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格档：`{policy['profile_id']}` / 指纹 `{policy_fingerprint}`",
        f"- 资产：{asset['power_mw']:.0f} MW / {asset['energy_mwh']:.0f} MWh，RTE {asset['rte']:.2f}，SOC {asset['soc_min']:.2f}–{asset['soc_max']:.2f}",
        f"- 授权差价合约：覆盖约 90% 电量为发电侧/用户侧口径（B）；储能是否纳入未核实，本包按无授权合约头寸、全额现货暴露计算",
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
        f"- 日参考价差：{bid['spread']:.1f} 元/MWh（政策门槛 {policy['min_daily_spread_cny_per_mwh']:.0f}）",
        f"- 价差报价：放电保本 {bid['discharge_breakeven_cny_per_mwh']:.1f}（充电锚点 {bid['charge_anchor_cny_per_mwh']:.1f}），充电保本 {bid['charge_breakeven_cny_per_mwh']:.1f}（放电锚点 {bid['discharge_anchor_cny_per_mwh']:.1f}）",
        f"- 计划循环：{bid['cycles']:.2f} 次/日（上限 {policy['max_cycles_per_day']:.2f}，对应 112 号后「一充一放」为主）",
        f"- 计划吞吐量：{bid['throughput_mwh']:.1f} MWh；充放切换 {bid['switches']} 次；相邻时段净出力平均变化 {bid['mean_interval_change_mw']:.2f} MW",
        f"- 参考价净收益：{_money(evaluation['net_margin_at_reference_cny'])} CNY",
        f"- 情景期望净收益：{_money(evaluation['expected_net_margin_cny'])} CNY；CVaR(10%)：{_money(evaluation['cvar_10_cny'])} CNY",
        "",
        "## 3. 情景表",
        "",
        "| 情景 | 权重 | 均价 | 放电 MWh | 充电 MWh | 现货收益 | 退化 | 净收益 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in evaluation["outcomes"]:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['mean_price']:.1f} | "
            f"{item['cleared_discharge_mwh']:.1f} | {item['cleared_charge_mwh']:.1f} | "
            f"{_money(item['spot_margin_cny'])} | {_money(item['degradation_cny'])} | "
            f"{_money(item['net_margin_cny'])} |"
        )
    lines += [
        "",
        "## 4. T+1 两结算",
        "",
        "| 项目 | 数值 |",
        "|---|---|",
        f"| 日前价加权参考 | {_money(actual['da_energy_weighted_price_cny_per_mwh'])} 元/MWh |",
        f"| 实时价加权参考 | {_money(actual['rt_energy_weighted_price_cny_per_mwh'])} 元/MWh |",
        f"| 实际放电 / 充电 | {actual['discharge_energy_mwh']:.1f} / {actual['charge_energy_mwh']:.1f} MWh |",
        f"| 现货净收入 | {_money(actual['spot_cny'])} CNY |",
        f"| 单位放电收入 | {_money(actual['revenue_per_discharge_mwh'])} 元/MWh |",
        f"| 退化成本 | {_money(actual['degradation_cny'])} CNY |",
        f"| 固定成本 | {_money(actual['fixed_cost_cny'])} CNY |",
        f"| 实际净收益 | {_money(actual['net_margin_cny'])} CNY |",
        "",
        "> 两结算口径：日前计划净出力按日前价，实际与计划的偏差按实时价（模块 §3：实时与日前衔接、偏差按实时价结算）。浙江授权合约双差价公式未核实，本表不含授权合约结算科目，不要用单一实时价重算整日收益。",
        "",
        "## 5. 差异桥",
        "",
        "| 分桶 | 类别 | 责任 | 金额 CNY |",
        "|---|---|---|---|",
    ]
    for item in bridge["buckets"]:
        lines.append(
            f"| {item['item']} | {item['category']} | {item['owner']} | {_signed(item['amount']):,.0f} |"
        )
    lines += [
        "",
        f"- 计划净收益 {_money(bridge['plan_profit'])} → 实际净收益 {_money(bridge['actual_profit'])}，差异 {_signed(bridge['delta']):,.0f} CNY",
        f"- 恒等式残差：{bridge['identity_gap']:.2e} CNY",
        "",
        "### 偏差最大时段",
        "",
        "| 时段 | 计划放电 | 实际放电 | 计划充电 | 实际充电 | 量差影响 |",
        "|---|---|---|---|---|---|",
    ]
    for item in bridge_detail:
        lines.append(
            f"| {item['start']} | {item['plan_discharge_mw']:.1f} | {item['actual_discharge_mw']:.1f} | "
            f"{item['plan_charge_mw']:.1f} | {item['actual_charge_mw']:.1f} | "
            f"{_signed(item['quantity_effect_cny']):,.0f} |"
        )
    lines += [
        "",
        "## 6. 午间负价压力测试（D 级，不是结算规则）",
        "",
        f"- 假设窗口：{stress['window_start']}–{stress['window_end']}（{stress['duration_hours']:.1f} h），重算价 {stress['settlement_price_cny_per_mwh']:.0f} 元/MWh（限价下限）",
        f"- 窗口内充电量：{stress['charge_window_mwh']:.1f} MWh；放电量：{stress['discharge_window_mwh']:.1f} MWh",
        f"- 窗口内实时价 < 0 的时段：{stress['negative_rt_slots']} 个",
        f"- 基准窗口收入：{_money(stress['base_window_cny'])} CNY；负价窗口收入：{_money(stress['stress_window_cny'])} CNY",
        f"- 负价冲击：{_signed(stress['delta_cny']):,.0f} CNY；压力情景净收益：{_money(stress['stress_net_margin_cny'])} CNY",
        "",
        "> 模块只说新能源全量入市后「午间低价/负价风险上升」（B），未给负价时段与频次。本表用限价下限 −200 元/MWh 做敏感性：负价对充电腿是收入、对放电腿是损失；申报策略应让午间保持充电头寸。不得当作结算依据。",
        "",
        "## 7. 5 分钟粒度检查",
        "",
        f"- 288 点/日：相邻时段 5 分钟，计划充放切换 {bid['switches']} 次，平均净出力变化 {bid['mean_interval_change_mw']:.2f} MW",
        f"- 若把同一策略降采样到 96 点，会漏掉 {report['points_per_day'] - 96} 个可调整时段；本包不做降采样回测",
        "- 模块 §9.1 要求独立储能按 5 分钟价格建模（C）；负价时段以 5 分钟粒度出现，降采样会把午间负价削平",
        "- 现货晚峰与 112 号晚高峰 16:00–23:00 大体重合；晚峰放电决策按 5 分钟价格逐段核对，不能只看日均价",
        "",
        "## 8. 复盘问题与次日动作",
        "",
        "1. 差异桥中「日前计划量差」和「实时偏差价差」哪一项更大？若量差主导，先修预测与执行；若价差主导，先修申报曲线。",
        "2. 午间负价是否被充电腿吃满？若实际负价时段计划没有充电头寸，检查申报曲线是否把充电从夜间前移到午间低谷。",
        "3. 晚峰放电是否覆盖 112 号晚高峰 16:00–23:00 全程？若走 VPP 聚合路线，先确认独立计量表计，否则只能按负荷类单元结算。",
        "",
        "次日动作：核对 T+1 的 da_price 与 rt_price 是否来自同一结算版本；跟踪授权差价合约双差价公式与独立储能准入条件的省级原文；把实际 SOC 曲线与计划 SOC 曲线叠加，定位执行偏差。",
        "",
        "## 9. 警告与边界",
        "",
    ]
    for item in report["warnings"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "---",
        "",
        "本表由 `run.py` 生成，全部数字为 D 级合成演示；不构成报价、投资或法律建议。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _fingerprint(policy):
    canonical = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def run_instance(instance_path, d1_path, t1_path, out_dir):
    """Validate, build the bid sheet, settle T+1, and write the review."""
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    report = validate_instance(config)
    fingerprint = _fingerprint(config["policy"])

    d1 = read_d1(Path(d1_path), config, report)
    t1 = read_t1(Path(t1_path), config, report, float(config["asset"]["power_mw"]))
    if d1["date"] != t1["date"]:
        raise ConfigError("D-1 and T+1 files must describe the same trading day")

    bid = build_bid(d1["prices"], config, report)
    evaluation = evaluate_plan(bid, d1["prices"], config, report)
    actual = settle_actual(bid, t1, config, report)
    bridge = build_bridge(bid, t1, evaluation, actual, config, report)
    stress = midday_stress(bid, t1, actual, config, report)
    bridge_detail = build_bridge_detail(bid, t1, report)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bid_rows = []
    for row in bid["rows"]:
        row = dict(row)
        row["date"] = d1["date"]
        bid_rows.append(row)
    _write_csv(
        out_dir / "bid_sheet.csv",
        bid_rows,
        [
            "date",
            "slot",
            "side",
            "quantity_mw",
            "price_cny_per_mwh",
            "reference_price",
            "clear_probability",
            "expected_mw",
            "note",
        ],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "plan": {
            "points_per_day": report["points_per_day"],
            "mtu_min": report["mtu_min"],
            "reference_spread_cny_per_mwh": bid["spread"],
            "charge_anchor_cny_per_mwh": bid["charge_anchor_cny_per_mwh"],
            "discharge_anchor_cny_per_mwh": bid["discharge_anchor_cny_per_mwh"],
            "discharge_breakeven_cny_per_mwh": bid["discharge_breakeven_cny_per_mwh"],
            "charge_breakeven_cny_per_mwh": bid["charge_breakeven_cny_per_mwh"],
            "cycles": bid["cycles"],
            "throughput_mwh": bid["throughput_mwh"],
            "switches": bid["switches"],
            "mean_interval_change_mw": bid["mean_interval_change_mw"],
            "bid_rows": len(bid_rows),
            "reference_net_margin_cny": evaluation["net_margin_at_reference_cny"],
            "expected_net_margin_cny": evaluation["expected_net_margin_cny"],
            "cvar_10_cny": evaluation["cvar_10_cny"],
            "scenarios": evaluation["outcomes"],
            "capacity_compensation_cny": evaluation["capacity_compensation_cny"],
        },
        "actual": {
            "da_energy_weighted_price_cny_per_mwh": actual["da_energy_weighted_price_cny_per_mwh"],
            "rt_energy_weighted_price_cny_per_mwh": actual["rt_energy_weighted_price_cny_per_mwh"],
            "discharge_energy_mwh": actual["discharge_energy_mwh"],
            "charge_energy_mwh": actual["charge_energy_mwh"],
            "spot_cny": actual["spot_cny"],
            "revenue_per_discharge_mwh": actual["revenue_per_discharge_mwh"],
            "degradation_cny": actual["degradation_cny"],
            "fixed_cost_cny": actual["fixed_cost_cny"],
            "net_margin_cny": actual["net_margin_cny"],
        },
        "midday_stress": stress,
        "warnings": report["warnings"],
        "files": {
            "bid_sheet": "bid_sheet.csv",
            "review": "review.md",
            "bridge": "bridge.json",
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    bridge_out = {
        "plan_profit": bridge["plan_profit"],
        "actual_profit": bridge["actual_profit"],
        "delta": bridge["delta"],
        "identity_gap": bridge["identity_gap"],
        "plan_spot": bridge["plan_spot"],
        "actual_spot": bridge["actual_spot"],
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
        actual,
        bridge,
        stress,
        bridge_detail,
        fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "bid": bid,
        "evaluation": evaluation,
        "actual": actual,
        "bridge": bridge,
        "stress": stress,
        "bridge_detail": bridge_detail,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Zhejiang standalone-storage instance pack")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", default=None, help="D-1 price CSV (defaults to data_contract.d1.file)")
    parser.add_argument("--t1", default=None, help="T+1 settlement CSV (defaults to data_contract.t1.file)")
    parser.add_argument("--out", default=str(HERE / "out" / "demo"))
    parser.add_argument("--check-config", action="store_true", help="validate instance.json only")
    parser.add_argument("--demo", action="store_true", help="regenerate deterministic demo data first")
    args = parser.parse_args(argv)

    instance_path = Path(args.instance)
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    if args.check_config:
        report = validate_instance(config)
        print(
            f"config ok points={report['points_per_day']} mtu={report['mtu_min']:g} "
            f"bounds={report['bounds']} midday-stress={report['stress']['window_start']}-"
            f"{report['stress']['window_end']}@{report['stress']['settlement_price']:.0f}"
        )
        for item in report["warnings"]:
            print(f"warning: {item}")
        return 0

    if args.demo:
        import make_demo

        make_demo.main()

    d1_path = Path(args.d1) if args.d1 else _resolve_data(config, "d1")
    t1_path = Path(args.t1) if args.t1 else _resolve_data(config, "t1")
    result = run_instance(instance_path, d1_path, t1_path, Path(args.out))
    summary = result["summary"]
    plan = summary["plan"]
    actual = summary["actual"]
    stress = summary["midday_stress"]
    print(
        f"points={plan['points_per_day']} mtu={plan['mtu_min']}min "
        f"cycles={plan['cycles']:.2f} switches={plan['switches']} "
        f"spread={plan['reference_spread_cny_per_mwh']:.0f}"
    )
    print(
        f"plan={plan['reference_net_margin_cny']:.0f} "
        f"E={plan['expected_net_margin_cny']:.0f} "
        f"CVaR10={plan['cvar_10_cny']:.0f} "
        f"actual={actual['net_margin_cny']:.0f} "
        f"bridge_gap={result['bridge']['identity_gap']:.2e}"
    )
    print(
        f"midday {stress['window_start']}-{stress['window_end']}@{stress['settlement_price_cny_per_mwh']:.0f}: "
        f"delta={stress['delta_cny']:.0f} stressed={stress['stress_net_margin_cny']:.0f}"
    )
    print(f"fingerprint={summary['policy_fingerprint']}")
    print(f"out={result['out_dir']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        sys.exit(2)
