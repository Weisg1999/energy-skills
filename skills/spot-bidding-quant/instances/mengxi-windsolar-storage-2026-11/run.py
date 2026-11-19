#!/usr/bin/env python3
"""Run the Mengxi wind+PV+storage joint-declaration instance pack.

One station, one settlement point, three assets:

* wind + PV declare jointly (报量报价) on the 288-point 5-minute spine that
  matches the Mengxi real-time 5-minute rolling clearing (A/B);
* the on-site standalone storage is scheduled behind the same meter with the
  2026 draft constraints (C 级征求意见稿，非正式规则): no discharge while
  renewables are in surplus (proxied by price < 0), SOC window inside
  0-10% / 90-100%, at most 1.5 equivalent cycles per day, runs of at least
  30 minutes;
* T+1 replays the full-volume real-time settlement (single-track: actual net
  export is paid at the real-time price, the day-ahead pre-clear is only a
  reference);
* the pack compares the joint declaration against a "separate" world in
  which wind+PV and the storage settle independently, including a charge
  adder that stands in for an unverified user-side settlement caliber.

The dispatch engine is a self-written dynamic program over a uniform SOC
grid, equivalent to ``skills/ems-dispatch/tools/dispatch.py`` (same SOC-grid
DP, same terminal=cycle convention) plus a per-slot discharge-ban mask and a
Lagrangian daily-cycle cap, which the shared kernel cannot express without
distorting the PV export price. All stdlib, deterministic.

All bundled numbers are synthetic grade D. They are not a market forecast,
a live trading signal or investment advice.
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

import desk  # noqa: E402


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


def _s(value, path):
    """Validate a string value that is already extracted from its mapping."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} must be a non-empty string")
    return value.strip()


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    grade = _text(block, "grade", f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report["provenance"].append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block


def validate_instance(config):
    """Validate the configuration and return a provenance/check report."""
    report = {"ok": True, "provenance": [], "checks": [], "warnings": []}
    meta = _need(config, "meta", "instance")
    for key in (
        "instance_id",
        "province",
        "market",
        "entity_type",
        "rule_version",
        "data_cutoff",
        "grade",
        "scope",
    ):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot", report)
    settlement = _rule_block(rules, "settlement", report)
    new_energy = _rule_block(rules, "new_energy", report)
    storage_rule = _rule_block(rules, "storage_participation", report)
    freq = _rule_block(rules, "frequency_regulation", report)
    capacity = _rule_block(rules, "capacity_compensation", report)
    deviation = _rule_block(rules, "deviation_assessment", report)
    context = _rule_block(rules, "market_context", report)

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = int(_number(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1))
    if mtu != 5 or points != 288:
        raise ConfigError(
            "Mengxi real-time clearing is 5 minutes / 288 points (A/B); "
            "do not reuse a 15-minute / 96-point spine in this pack"
        )
    floor = _number(_need(spot, "model_floor_cny_per_mwh", "rules.spot"), "rules.spot.model_floor_cny_per_mwh")
    cap = _number(_need(spot, "model_cap_cny_per_mwh", "rules.spot"), "rules.spot.model_cap_cny_per_mwh")
    if not (floor < 0 < cap):
        raise ConfigError("model bounds must straddle zero to allow negative prices")
    observed = _need(spot, "observed_2025", "rules.spot")
    observed_floor = _number(
        _need(observed, "floor_cny_per_mwh", "rules.spot.observed_2025"),
        "rules.spot.observed_2025.floor_cny_per_mwh",
    )
    observed_cap = _number(
        _need(observed, "cap_cny_per_mwh", "rules.spot.observed_2025"),
        "rules.spot.observed_2025.cap_cny_per_mwh",
    )
    if observed_floor < floor - 1e-9 or observed_cap > cap + 1e-9:
        raise ConfigError("model bounds must cover the observed 2025 range")
    early_status = _s(_need(spot, "early_limit", "rules.spot").get("status", ""), "rules.spot.early_limit.status")
    if "历史" not in early_status and "不得" not in early_status:
        raise ConfigError("early_limit.status must mark the shallow-archive band as historical")
    draft_status = _s(_need(spot, "draft_2026", "rules.spot").get("status", ""), "rules.spot.draft_2026.status")
    if "未生效" not in draft_status and "征求意见" not in draft_status:
        raise ConfigError("draft_2026.status must mark the draft as not effective")
    if "待核" not in _text(spot, "current_limit_status", "rules.spot"):
        raise ConfigError("spot.current_limit_status must flag the current limit as unverified")
    if "待核" not in _text(spot, "day_ahead_granularity_status", "rules.spot"):
        raise ConfigError("spot.day_ahead_granularity_status must flag the DA granularity as unverified")
    _text(settlement, "basis", "rules.settlement")
    _text(settlement, "granularity", "rules.settlement")

    incremental_after = _text(new_energy, "incremental_after", "rules.new_energy")
    if incremental_after != "2025-06-01":
        raise ConfigError("new_energy.incremental_after must be 2025-06-01")
    mechanism_text = _text(new_energy, "incremental_mechanism", "rules.new_energy")
    if "暂不纳入" not in mechanism_text:
        raise ConfigError("incremental projects must be marked as excluded from the mechanism price")
    stock_price = _number(
        _need(new_energy, "stock_mechanism_cny_per_mwh", "rules.new_energy"),
        "rules.new_energy.stock_mechanism_cny_per_mwh",
    )
    if abs(stock_price - 282.9) > 1e-9:
        raise ConfigError("stock mechanism price must be 282.9 CNY/MWh (0.2829 CNY/kWh, stock projects only)")

    if _text(storage_rule, "grade", "rules.storage_participation") != "C":
        raise ConfigError(
            "storage_participation carries only the 2026 draft clauses; its grade must be C "
            "(C 级征求意见稿，非正式规则)"
        )
    if "征求意见" not in _text(storage_rule, "status", "rules.storage_participation"):
        raise ConfigError("storage_participation.status must mark the draft caliber")
    draft_cycles = _number(
        _need(storage_rule, "max_cycles_per_day", "rules.storage_participation"),
        "rules.storage_participation.max_cycles_per_day",
    )
    if abs(draft_cycles - 1.5) > 1e-9:
        raise ConfigError("storage_participation.max_cycles_per_day must be 1.5 (2026 draft)")
    draft_min_run = _number(
        _need(storage_rule, "min_continuous_minutes", "rules.storage_participation"),
        "rules.storage_participation.min_continuous_minutes",
    )
    if abs(draft_min_run - 30.0) > 1e-9:
        raise ConfigError("storage_participation.min_continuous_minutes must be 30 (2026 draft)")

    if _text(freq, "grade", "rules.frequency_regulation") != "C":
        raise ConfigError("frequency_regulation carries the opinion-letter caliber; its grade must be C")
    freq_cap = _number(
        _need(freq, "mileage_clear_cap_cny_per_mw", "rules.frequency_regulation"),
        "rules.frequency_regulation.mileage_clear_cap_cny_per_mw",
    )
    if abs(freq_cap - 15.0) > 1e-9:
        raise ConfigError("frequency_regulation.mileage_clear_cap must be 15 CNY/MW")
    share_cap = _number(
        _need(freq, "new_entity_capacity_share_cap", "rules.frequency_regulation"),
        "rules.frequency_regulation.new_entity_capacity_share_cap",
    )
    if abs(share_cap - 0.3) > 1e-9:
        raise ConfigError("frequency_regulation.new_entity_capacity_share_cap must be 0.3")
    if capacity.get("applicable_to_wind_solar_storage") is not False:
        raise ConfigError("wind/PV/storage must not book a capacity payment; none is verified for Mengxi")

    band = _number(
        _need(deviation, "band", "rules.deviation_assessment"), "rules.deviation_assessment.band", 0.0, 1.0
    )
    penalty_price = _number(
        _need(deviation, "penalty_cny_per_mwh", "rules.deviation_assessment"),
        "rules.deviation_assessment.penalty_cny_per_mwh",
        0.0,
    )
    if _text(deviation, "basis", "rules.deviation_assessment") != "renewable_available_energy":
        raise ConfigError("deviation assessment must use the renewable available energy (before curtailment)")
    _text(context, "storage_installed", "rules.market_context")
    _text(context, "dongx_note", "rules.market_context")

    wind = _need(asset, "wind", "asset")
    pv = _need(asset, "pv", "asset")
    storage = _need(asset, "storage", "asset")
    wind_cap = _number(_need(wind, "capacity_mw", "asset.wind"), "asset.wind.capacity_mw", 1e-9)
    pv_cap = _number(_need(pv, "capacity_mw", "asset.pv"), "asset.pv.capacity_mw", 1e-9)
    power = _number(_need(storage, "power_mw", "asset.storage"), "asset.storage.power_mw", 1e-9)
    energy = _number(_need(storage, "energy_mwh", "asset.storage"), "asset.storage.energy_mwh", 1e-9)
    duration = _number(storage.get("duration_h", energy / power), "asset.storage.duration_h", 1e-9)
    if abs(duration - energy / power) > 1e-6:
        raise ConfigError("asset.storage.duration_h must equal energy_mwh / power_mw")
    rte = _number(_need(storage, "rte", "asset.storage"), "asset.storage.rte", 1e-9, 1.0)
    soc_min = _number(_need(storage, "soc_min", "asset.storage"), "asset.storage.soc_min", 0.0, 1.0)
    soc_max = _number(_need(storage, "soc_max", "asset.storage"), "asset.storage.soc_max", 0.0, 1.0)
    if not soc_min < soc_max:
        raise ConfigError("asset.storage.soc_min must be below soc_max")
    if soc_min > 0.10 + 1e-9:
        raise ConfigError("draft SOC window: the lower limit must stay inside 0-10% (C 级征求意见稿)")
    if soc_max < 0.90 - 1e-9:
        raise ConfigError("draft SOC window: the upper limit must stay inside 90-100% (C 级征求意见稿)")
    soc_init = _number(_need(storage, "soc_init", "asset.storage"), "asset.storage.soc_init", 0.0, 1.0)
    if not soc_min <= soc_init <= soc_max:
        raise ConfigError("asset.storage.soc_init must lie inside the SOC window")
    usable = _number(_need(storage, "usable_energy_mwh", "asset.storage"), "asset.storage.usable_energy_mwh", 1e-9)
    if abs(usable - energy * (soc_max - soc_min)) > 1e-6 * max(1.0, usable):
        raise ConfigError("usable_energy_mwh must equal energy_mwh * (soc_max - soc_min)")
    degradation = _number(
        _need(storage, "degradation_cny_per_mwh_throughput", "asset.storage"),
        "asset.storage.degradation_cny_per_mwh_throughput",
        0.0,
    )
    states = int(_number(storage.get("solver_states", 96), "asset.storage.solver_states", 10))
    opex_wind = _number(_need(asset, "opex_wind_cny_per_mwh", "asset"), "asset.opex_wind_cny_per_mwh", 0.0)
    opex_pv = _number(_need(asset, "opex_pv_cny_per_mwh", "asset"), "asset.opex_pv_cny_per_mwh", 0.0)
    fixed = _number(_need(asset, "fixed_cost_cny_per_day", "asset"), "asset.fixed_cost_cny_per_day", 0.0)
    grid = _need(asset, "grid_connection", "asset")
    export_limit = _number(
        _need(grid, "export_limit_mw", "asset.grid_connection"), "asset.grid_connection.export_limit_mw", 0.0
    )
    import_limit = _number(
        _need(grid, "import_limit_mw", "asset.grid_connection"), "asset.grid_connection.import_limit_mw", 0.0
    )
    if abs(import_limit - power) > 1e-6:
        raise ConfigError(
            "grid import limit must equal the storage power in this pack: behind the meter, "
            "net import only serves charging"
        )

    _text(policy, "profile_id", "policy")
    _text(policy, "description", "policy")
    storage_mode = _text(policy, "storage_mode", "policy")
    if storage_mode not in ("bid_quantity_price", "quantity_only"):
        raise ConfigError("policy.storage_mode must be bid_quantity_price or quantity_only (2026 draft)")
    price_q = _number(
        _need(policy, "price_reference_quantile", "policy"), "policy.price_reference_quantile", 0.0, 1.0
    )
    ban = _need(policy, "discharge_ban", "policy")
    if ban.get("enabled") is not True:
        raise ConfigError("policy.discharge_ban.enabled must be true (2026 draft clause)")
    if _text(ban, "proxy", "policy.discharge_ban") != "price_below_zero":
        raise ConfigError("policy.discharge_ban.proxy must be price_below_zero (D-grade proxy)")
    policy_cycles = _number(
        _need(policy, "max_cycles_per_day", "policy"), "policy.max_cycles_per_day", 1e-9
    )
    if abs(policy_cycles - draft_cycles) > 1e-9:
        raise ConfigError("policy.max_cycles_per_day must match the draft storage rule (1.5)")
    policy_min_run = _number(
        _need(policy, "min_continuous_minutes", "policy"), "policy.min_continuous_minutes", 0.0
    )
    if abs(policy_min_run - draft_min_run) > 1e-9:
        raise ConfigError("policy.min_continuous_minutes must match the draft storage rule (30)")
    discharge_markup = _number(
        _need(policy, "discharge_markup_cny_per_mwh", "policy"), "policy.discharge_markup_cny_per_mwh", 0.0
    )
    charge_markup = _number(
        _need(policy, "charge_markup_cny_per_mwh", "policy"), "policy.charge_markup_cny_per_mwh", 0.0
    )
    spike_threshold = _number(
        _need(policy, "spike_threshold_cny_per_mwh", "policy"), "policy.spike_threshold_cny_per_mwh", 0.0
    )
    spike_markup = _number(
        _need(policy, "spike_markup_cny_per_mwh", "policy"), "policy.spike_markup_cny_per_mwh", 0.0
    )
    adder = _number(
        _need(policy, "separate_charge_adder_cny_per_mwh", "policy"),
        "policy.separate_charge_adder_cny_per_mwh",
        0.0,
    )
    if policy.get("compliant_only_selection") is not True:
        raise ConfigError("policy.compliant_only_selection must be true: draft-noncompliant strategies are reference only")
    renewable_bid = _number(
        _need(policy, "renewable_bid_price_cny_per_mwh", "policy"),
        "policy.renewable_bid_price_cny_per_mwh",
        floor,
        cap,
    )
    strategies = _need(policy, "strategies", "policy")
    if not isinstance(strategies, dict) or len(strategies) < 2:
        raise ConfigError("policy.strategies must contain at least two strategies")
    for name, strategy in strategies.items():
        path = f"policy.strategies.{name}"
        _text(strategy, "label", path)
        _number(_need(strategy, "declared_quantity_quantile", path), f"{path}.declared_quantity_quantile", 0.0, 1.0)
        if not isinstance(_need(strategy, "compliant", path), bool):
            raise ConfigError(f"{path}.compliant must be a boolean")
    if not any(strategy.get("compliant") for strategy in strategies.values()):
        raise ConfigError("policy.strategies must contain at least one compliant strategy")

    contracts = config.get("contracts", [])
    if not isinstance(contracts, list) or contracts:
        raise ConfigError(
            "this joint v1 pack covers spot energy only; medium/long-term CfD contracts are not modelled"
        )

    d1 = _need(data_contract, "d1", "data_contract")
    _text(d1, "file", "data_contract.d1")
    required = _need(d1, "required_fields", "data_contract.d1")
    if not isinstance(required, list) or not required:
        raise ConfigError("data_contract.d1.required_fields must be a non-empty list")
    wind_fields = _need(d1, "wind_scenario_fields", "data_contract.d1")
    pv_fields = _need(d1, "pv_scenario_fields", "data_contract.d1")
    price_fields = _need(d1, "price_scenario_fields", "data_contract.d1")
    if not (len(wind_fields) == len(pv_fields) == len(price_fields) == 5):
        raise ConfigError("this pack expects exactly five paired wind/PV/price scenarios")
    weights = _need(d1, "scenario_weights", "data_contract.d1")
    if len(weights) != 5:
        raise ConfigError("data_contract.d1.scenario_weights must have five entries")
    parsed_weights = [_number(value, "data_contract.d1.scenario_weights", 0.0) for value in weights]
    if abs(sum(parsed_weights) - 1.0) > 1e-9:
        raise ConfigError("data_contract.d1.scenario_weights must sum to 1")
    for field in (
        list(wind_fields)
        + list(pv_fields)
        + list(price_fields)
        + ["forecast_wind_mw", "forecast_pv_mw", "da_price", "date", "slot", "start", "end"]
    ):
        if field not in required:
            raise ConfigError(f"data_contract.d1.required_fields is missing {field}")
    t1 = _need(data_contract, "t1", "data_contract")
    _text(t1, "file", "data_contract.t1")
    t1_required = _need(t1, "required_fields", "data_contract.t1")
    for field in ("date", "slot", "actual_da_price", "actual_rt_price", "actual_wind_mw", "actual_pv_mw"):
        if field not in t1_required:
            raise ConfigError(f"data_contract.t1.required_fields must include {field}")

    dt_h = mtu / 60.0
    eta = math.sqrt(rte)
    if export_limit >= wind_cap + pv_cap:
        report["warnings"].append(
            "场站出口限额不低于风光装机之和：共享限额的弃电回收效应不会生效，请确认并网点限额口径"
        )

    report["predicates"] = {
        "points_per_day": points,
        "mtu_min": mtu,
        "dt_h": dt_h,
        "wind_cap_mw": wind_cap,
        "pv_cap_mw": pv_cap,
        "storage_power_mw": power,
        "storage_energy_mwh": energy,
        "eta_ch": eta,
        "eta_dis": eta,
        "soc_min": soc_min,
        "soc_max": soc_max,
        "soc_init": soc_init,
        "e_lo_mwh": soc_min * energy,
        "e_hi_mwh": soc_max * energy,
        "e_init_mwh": soc_init * energy,
        "export_limit_mw": export_limit,
        "import_limit_mw": import_limit,
        "degradation": degradation,
        "opex_wind": opex_wind,
        "opex_pv": opex_pv,
        "fixed": fixed,
        "band": band,
        "penalty": penalty_price,
        "cycle_cap": draft_cycles,
        "min_run_slots": int(round(draft_min_run / mtu)),
        "solver_states": states,
        "ban_enabled": True,
        "model_floor": floor,
        "model_cap": cap,
        "scenario_weights": parsed_weights,
        "wind_fields": list(wind_fields),
        "pv_fields": list(pv_fields),
        "price_fields": list(price_fields),
        "price_reference_quantile": price_q,
        "storage_mode": storage_mode,
        "discharge_markup": discharge_markup,
        "charge_markup": charge_markup,
        "spike_threshold": spike_threshold,
        "spike_markup": spike_markup,
        "separate_charge_adder": adder,
        "renewable_bid_price": renewable_bid,
    }
    report["warnings"].extend(
        [
            "2026 修订版储能条款（弃电禁放、循环上限 1.5 次、SOC 窗口、报量方式选择）全部是 C 级征求意见稿口径，未生效，不得当正式规则",
            "禁放代理“现货价 < 0”是 D 级指标；官方“可再生能源富裕程度”定义待核，正式规则发布后须替换",
            "蒙西现行申报/出清限价待核：早期 40-550/600 是历史浅档案口径（B），2025 实绩 -48.66~1555.85（B），2026 草案 -50~1500（C，未生效）；本包模型边界只覆盖实绩",
            "独立储能充电结算价口径（是否含输配电价与附加）未核到；分开对照的充电加成是 D 级占位，不构成结算规则",
            "蒙西价格机制为基于用户侧节点电价的分区价格（A/B）；本包全站用同一价格序列，未按分区/节点分列（D 级简化）",
            "储能/新型主体的申报偏差考核口径未核到；本包只对风光可用电量做 D 级偏差考核（±5% 带，30 元/MWh 简化）",
            "蒙西日前为预出清，不用于结算；本包按实时全电量结算（单轨制），日前计划仅作对照",
            "储能严格按日前计划执行是 D 级假设；5 分钟内滚动执行、SOC/断面/爬坡约束未建模",
            "调频仅记录 C 级意见函口径，未建模；参调时段须预留 SOC 20%-80%，与现货窗口不一致",
        ]
    )
    return report


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
    d1_contract = config["data_contract"]["d1"]
    _check_shape(rows, d1_contract["required_fields"], report["predicates"]["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    pred = report["predicates"]
    n = pred["points_per_day"]
    bounds = (pred["model_floor"], pred["model_cap"])

    def power_series(field, limit, label):
        series = []
        for slot in range(n):
            value = _number(by_slot[slot][field], f"{path.name}:{field}@slot{slot}", 0.0)
            if value > limit + 1e-6:
                raise ConfigError(f"{path.name}:{field}@slot{slot}={value} exceeds the {label} capacity")
            series.append(value)
        return series

    forecast_wind = power_series("forecast_wind_mw", pred["wind_cap_mw"], "wind")
    forecast_pv = power_series("forecast_pv_mw", pred["pv_cap_mw"], "PV")

    wind = []
    for field in pred["wind_fields"]:
        wind.append(power_series(field, pred["wind_cap_mw"], "wind"))
    pv = []
    for field in pred["pv_fields"]:
        pv.append(power_series(field, pred["pv_cap_mw"], "PV"))

    prices = []
    for field in pred["price_fields"]:
        series = []
        for slot in range(n):
            price = _number(by_slot[slot][field], f"{path.name}:{field}@slot{slot}")
            if not (bounds[0] - 0.01 <= price <= bounds[1] + 0.01):
                raise ConfigError(
                    f"{path.name}:{field}@slot{slot}={price} is outside the model bounds; "
                    "this is a model guard, not the formal market limit"
                )
            series.append(price)
        prices.append(series)

    da_price = []
    for slot in range(n):
        price = _number(by_slot[slot]["da_price"], f"{path.name}:da_price@slot{slot}")
        if not (bounds[0] - 0.01 <= price <= bounds[1] + 0.01):
            raise ConfigError(f"{path.name}:da_price@slot{slot}={price} is outside the model bounds")
        da_price.append(price)

    return {
        "date": rows[0]["date"],
        "slots": list(range(n)),
        "forecast_wind": forecast_wind,
        "forecast_pv": forecast_pv,
        "wind": wind,
        "pv": pv,
        "prices": prices,
        "da_price": da_price,
        "start": {slot: by_slot[slot]["start"] for slot in by_slot},
        "end": {slot: by_slot[slot]["end"] for slot in by_slot},
    }


def read_t1(path, config, report):
    rows = _read_rows(path)
    t1_contract = config["data_contract"]["t1"]
    _check_shape(rows, t1_contract["required_fields"], report["predicates"]["points_per_day"], path.name)
    dates = {row["date"] for row in rows}
    if len(dates) != 1:
        raise ConfigError(f"{path.name}: one trading day per run, found {sorted(dates)}")
    by_slot = {int(row["slot"]): row for row in rows}
    pred = report["predicates"]
    n = pred["points_per_day"]
    bounds = (pred["model_floor"], pred["model_cap"])
    da_price, rt_price, wind, pv = [], [], [], []
    for slot in range(n):
        row = by_slot[slot]
        da = _number(row["actual_da_price"], f"{path.name}:actual_da_price@slot{slot}")
        rt = _number(row["actual_rt_price"], f"{path.name}:actual_rt_price@slot{slot}")
        for label, price in (("actual_da_price", da), ("actual_rt_price", rt)):
            if not (bounds[0] - 0.01 <= price <= bounds[1] + 0.01):
                raise ConfigError(f"{path.name}:{label}@slot{slot}={price} is outside the model bounds")
        wind_value = _number(row["actual_wind_mw"], f"{path.name}:actual_wind_mw@slot{slot}", 0.0)
        pv_value = _number(row["actual_pv_mw"], f"{path.name}:actual_pv_mw@slot{slot}", 0.0)
        if wind_value > pred["wind_cap_mw"] + 1e-6 or pv_value > pred["pv_cap_mw"] + 1e-6:
            raise ConfigError(f"{path.name}:slot{slot} exceeds the renewable capacity")
        da_price.append(da)
        rt_price.append(rt)
        wind.append(wind_value)
        pv.append(pv_value)
    return {
        "date": rows[0]["date"],
        "da_price": da_price,
        "rt_price": rt_price,
        "wind_mw": wind,
        "pv_mw": pv,
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


def ban_mask_from_prices(prices):
    """D-grade proxy for the draft discharge ban: price < 0 means renewable surplus."""
    return [price < 0.0 for price in prices]


def dispatch_joint(
    prices,
    renewables,
    pred,
    ban_mask,
    cycle_penalty=0.0,
    export_limit=None,
    import_limit=None,
):
    """SOC-grid dynamic program for the behind-the-meter storage schedule.

    Equivalent to the ems-dispatch kernel ``dispatch_day`` (uniform SOC grid,
    ``terminal="cycle"``) plus two Mengxi draft constraints the shared kernel
    cannot express cleanly: a per-slot discharge ban and a Lagrangian cycle
    price. Units: MW / MWh / CNY/MWh. Deterministic.
    """
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    states = pred["solver_states"]
    e_lo = pred["e_lo_mwh"]
    e_hi = pred["e_hi_mwh"]
    e_init = pred["e_init_mwh"]
    energy_cap = pred["storage_energy_mwh"]
    eta_ch = pred["eta_ch"]
    eta_dis = pred["eta_dis"]
    power = pred["storage_power_mw"]
    step = (e_hi - e_lo) / states
    i0 = int(round((e_init - e_lo) / step))
    i0 = max(0, min(states, i0))
    energies = [e_lo + i * step for i in range(states + 1)]
    ch_dc_max = power * eta_ch * dt_h
    dis_dc_max = power * dt_h / eta_dis
    exp_lim = pred["export_limit_mw"] if export_limit is None else float(export_limit)
    imp_lim = pred["import_limit_mw"] if import_limit is None else float(import_limit)
    deg = pred["degradation"] + cycle_penalty
    inf = float("inf")
    lo_off = int(math.ceil(dis_dc_max / step - 1e-9))
    hi_off = int(math.ceil(ch_dc_max / step - 1e-9))

    prev = [inf] * (states + 1)
    prev[i0] = 0.0
    parents = []
    for t in range(n):
        curr = [inf] * (states + 1)
        parent = [-1] * (states + 1)
        price = prices[t]
        ren = renewables[t]
        ban = ban_mask[t]
        for i in range(states + 1):
            base = prev[i]
            if base == inf:
                continue
            e0 = energies[i]
            j_lo = i - lo_off
            if j_lo < 0:
                j_lo = 0
            j_hi = i + hi_off
            if j_hi > states:
                j_hi = states
            for j in range(j_lo, j_hi + 1):
                delta = energies[j] - e0
                if delta < -1e-12:
                    if ban:
                        continue
                    dis = -delta * eta_dis / dt_h
                    if dis > power + 1e-9:
                        continue
                    ch = 0.0
                elif delta > 1e-12:
                    ch = delta / (eta_ch * dt_h)
                    if ch > power + 1e-9:
                        continue
                    dis = 0.0
                else:
                    dis = 0.0
                    ch = 0.0
                net = ren + dis - ch
                if net >= 0.0:
                    export = net if net < exp_lim else exp_lim
                    imp = 0.0
                else:
                    imp = -net
                    if imp > imp_lim + 1e-9:
                        continue
                    export = 0.0
                cost = base + ((imp - export) * price + deg * (ch + dis)) * dt_h
                if cost < curr[j] - 1e-12:
                    curr[j] = cost
                    parent[j] = i
        parents.append(parent)
        prev = curr

    if prev[i0] == inf:
        return {
            "feasible": False,
            "reason": "no schedule satisfies SOC, power, import limits and the discharge ban",
        }

    idx = [0] * (n + 1)
    idx[n] = i0
    for t in range(n - 1, -1, -1):
        idx[t] = parents[t][idx[t + 1]]

    charge = [0.0] * n
    discharge = [0.0] * n
    export = [0.0] * n
    import_mw = [0.0] * n
    curtail = [0.0] * n
    soc = [0.0] * (n + 1)
    for t in range(n):
        e0 = energies[idx[t]]
        delta = energies[idx[t + 1]] - e0
        if delta > 1e-12:
            ch = delta / (eta_ch * dt_h)
            dis = 0.0
        elif delta < -1e-12:
            ch = 0.0
            dis = -delta * eta_dis / dt_h
        else:
            ch = 0.0
            dis = 0.0
        net = renewables[t] + dis - ch
        if net >= 0.0:
            exp = net if net < exp_lim else exp_lim
            curt = net - exp
            imp = 0.0
        else:
            imp = -net
            exp = 0.0
            curt = 0.0
        charge[t] = ch
        discharge[t] = dis
        export[t] = exp
        import_mw[t] = imp
        curtail[t] = curt
        soc[t] = e0 / energy_cap
    soc[n] = energies[idx[n]] / energy_cap

    cash = sum((export[t] - import_mw[t]) * prices[t] for t in range(n)) * dt_h
    throughput = sum(charge[t] + discharge[t] for t in range(n)) * dt_h
    return {
        "feasible": True,
        "charge_mw": charge,
        "discharge_mw": discharge,
        "export_mw": export,
        "import_mw": import_mw,
        "curtail_mw": curtail,
        "soc": soc,
        "cash_cny": cash,
        "throughput_mwh": throughput,
        "cycles": throughput / (2.0 * energy_cap),
        "charge_mwh": sum(charge) * dt_h,
        "discharge_mwh": sum(discharge) * dt_h,
        "export_mwh": sum(export) * dt_h,
        "import_mwh": sum(import_mw) * dt_h,
        "curtail_mwh": sum(curtail) * dt_h,
        "cycle_penalty": cycle_penalty,
        "terminal_soc": soc[n],
    }


def solve_plan(prices, renewables, pred, ban_mask, cycle_cap, export_limit=None, import_limit=None):
    """Solve the DP, engaging a Lagrangian throughput price when the draft
    cycle cap binds. Returns (plan, lambda_used, iterations)."""
    plan = dispatch_joint(
        prices, renewables, pred, ban_mask, export_limit=export_limit, import_limit=import_limit
    )
    if not plan["feasible"]:
        raise ConfigError(f"dispatch infeasible: {plan.get('reason', 'unknown')}")
    if plan["cycles"] <= cycle_cap + 1e-9:
        return plan, 0.0, 0
    lo, hi = 0.0, 16.0
    probes = 0
    for _ in range(10):
        probe = dispatch_joint(
            prices,
            renewables,
            pred,
            ban_mask,
            cycle_penalty=hi,
            export_limit=export_limit,
            import_limit=import_limit,
        )
        probes += 1
        if not probe["feasible"]:
            raise ConfigError(f"dispatch infeasible at cycle penalty {hi}: {probe.get('reason', 'unknown')}")
        if probe["cycles"] <= cycle_cap + 1e-9:
            break
        lo = hi
        hi *= 2.0
    else:
        raise ConfigError("cycle cap could not be enforced with a finite throughput price")
    for _ in range(8):
        mid = 0.5 * (lo + hi)
        probe = dispatch_joint(
            prices,
            renewables,
            pred,
            ban_mask,
            cycle_penalty=mid,
            export_limit=export_limit,
            import_limit=import_limit,
        )
        probes += 1
        if not probe["feasible"]:
            raise ConfigError(f"dispatch infeasible at cycle penalty {mid}: {probe.get('reason', 'unknown')}")
        if probe["cycles"] <= cycle_cap + 1e-9:
            hi = mid
        else:
            lo = mid
    plan = dispatch_joint(
        prices,
        renewables,
        pred,
        ban_mask,
        cycle_penalty=hi,
        export_limit=export_limit,
        import_limit=import_limit,
    )
    if not plan["feasible"]:
        raise ConfigError("dispatch infeasible after cycle-cap enforcement")
    return plan, hi, probes


def count_action_runs(charge, discharge):
    """Return [(kind, start, length)] for consecutive charge/discharge runs."""
    runs = []
    kind = 0
    start = 0
    for t in range(len(charge)):
        state = 1 if charge[t] > 1e-6 else (-1 if discharge[t] > 1e-6 else 0)
        if state != kind:
            if kind != 0:
                runs.append((kind, start, t - start))
            kind = state
            start = t
    if kind != 0:
        runs.append((kind, start, len(charge) - start))
    return runs


def enforce_min_run(charge, discharge, min_slots, pred):
    """Zero out runs shorter than the draft minimum and repair SOC feasibility.

    Returns (charge, discharge, violations_found, repairs).
    """
    if min_slots <= 1:
        return charge, discharge, 0, 0
    runs = count_action_runs(charge, discharge)
    short = [run for run in runs if run[2] < min_slots]
    if not short:
        return charge, discharge, 0, 0
    charge = list(charge)
    discharge = list(discharge)
    for _, start, length in short:
        for t in range(start, start + length):
            charge[t] = 0.0
            discharge[t] = 0.0
    eta = pred["eta_ch"]
    capacity = pred["storage_energy_mwh"]
    low = pred["e_lo_mwh"]
    high = pred["e_hi_mwh"]
    energy = pred["e_init_mwh"]
    dt_h = pred["dt_h"]
    repairs = 0
    for t in range(len(charge)):
        if charge[t] > 1e-9:
            room = max(0.0, high - energy)
            limit = room / (eta * dt_h)
            if charge[t] > limit + 1e-9:
                charge[t] = limit
                repairs += 1
            energy += charge[t] * eta * dt_h
        if discharge[t] > 1e-9:
            available = max(0.0, energy - low)
            limit = available * eta / dt_h
            if discharge[t] > limit + 1e-9:
                discharge[t] = limit
                repairs += 1
            energy -= discharge[t] / eta * dt_h
    return charge, discharge, len(short), repairs


def execute_plan(charge, discharge, renewables, prices, pred, charge_adder=0.0,
                 export_limit=None, import_limit=None):
    """Execute a fixed storage plan against actual/scenario renewables and prices.

    The plan itself is SOC-feasible by construction, so charge/discharge run
    as planned; renewables only move the station export, curtailment, import
    and cash. Banned-slot violations are counted against the execution price,
    not silently re-scheduled (grade-D assumption, flagged in the review).
    """
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    exp_lim = pred["export_limit_mw"] if export_limit is None else float(export_limit)
    imp_lim = pred["import_limit_mw"] if import_limit is None else float(import_limit)
    export = [0.0] * n
    import_mw = [0.0] * n
    curtail = [0.0] * n
    cash = 0.0
    violations = 0
    for t in range(n):
        net = renewables[t] + discharge[t] - charge[t]
        if net >= 0.0:
            export[t] = net if net < exp_lim else exp_lim
            curtail[t] = net - export[t]
        else:
            import_mw[t] = -net
        cash += (export[t] - import_mw[t]) * prices[t] * dt_h
        if prices[t] < 0.0 and discharge[t] > 1e-6:
            violations += 1
    charge_mwh = sum(charge) * dt_h
    adder_cost = charge_adder * charge_mwh
    return {
        "export_mw": export,
        "import_mw": import_mw,
        "curtail_mw": curtail,
        "cash_cny": cash - adder_cost,
        "gross_cash_cny": cash,
        "adder_cost_cny": adder_cost,
        "ban_violation_slots": violations,
        "export_mwh": sum(export) * dt_h,
        "import_mwh": sum(import_mw) * dt_h,
        "curtail_mwh": sum(curtail) * dt_h,
        "charge_mwh": charge_mwh,
        "discharge_mwh": sum(discharge) * dt_h,
        "throughput_mwh": (sum(charge) + sum(discharge)) * dt_h,
        "cycles": (sum(charge) + sum(discharge)) * dt_h / (2.0 * pred["storage_energy_mwh"]),
    }


def deviation_penalty(available_mwh, declared_mwh, band, price):
    if declared_mwh <= 0:
        return 0.0, 0.0
    ratio = abs(available_mwh - declared_mwh) / declared_mwh
    penalty = max(0.0, ratio - band) * declared_mwh * price
    return ratio, penalty


def scenario_renewables(d1, index):
    return [
        d1["wind"][index][t] + d1["pv"][index][t] for t in range(len(d1["da_price"]))
    ]


def build_joint_bid(d1, strategy, config, report, plan_cache):
    """Declare the renewable joint quantity and build the storage plan/offers."""
    pred = report["predicates"]
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    weights = pred["scenario_weights"]
    q = float(strategy["declared_quantity_quantile"])
    ren_scenarios = [scenario_renewables(d1, index) for index in range(len(d1["wind"]))]
    da = d1["da_price"]

    declared = []
    for slot in range(n):
        value = quantile([ren_scenarios[s][slot] for s in range(len(ren_scenarios))], q)
        value = min(pred["export_limit_mw"], max(0.0, value))
        declared.append(math.floor(value * 10.0 + 1e-9) / 10.0)
    declared_energy = sum(declared) * dt_h

    use_ban = bool(pred["ban_enabled"]) and bool(strategy.get("compliant", True))
    cache_key = "joint_ban" if use_ban else "joint_free"
    cache_entry = plan_cache.get(cache_key)
    if cache_entry is None:
        ref_renewables = [
            quantile([ren_scenarios[s][slot] for s in range(len(ren_scenarios))], pred["price_reference_quantile"])
            for slot in range(n)
        ]
        ban = ban_mask_from_prices(da) if use_ban else [False] * n
        plan, lam, probes = solve_plan(da, ref_renewables, pred, ban, pred["cycle_cap"])
        charge, discharge, violations, repairs = enforce_min_run(
            plan["charge_mw"], plan["discharge_mw"], pred["min_run_slots"], pred
        )
        plan["charge_mw"] = charge
        plan["discharge_mw"] = discharge
        throughput = (sum(charge) + sum(discharge)) * dt_h
        plan["throughput_mwh"] = throughput
        plan["charge_mwh"] = sum(charge) * dt_h
        plan["discharge_mwh"] = sum(discharge) * dt_h
        plan["cycles"] = throughput / (2.0 * pred["storage_energy_mwh"])
        plan["min_run_violations"] = violations
        plan["min_run_repairs"] = repairs
        plan["reference_renewables"] = ref_renewables
        plan["lagrange_multiplier"] = lam
        plan["solver_probes"] = probes
        # If the minimum-run repair changed the plan, recompute the plan-side
        # export/import/curtail/cash on the same reference renewables so the
        # day-ahead reference and the bridge identity stay consistent.
        ref_exec = execute_plan(charge, discharge, ref_renewables, da, pred)
        plan["export_mw"] = ref_exec["export_mw"]
        plan["import_mw"] = ref_exec["import_mw"]
        plan["curtail_mw"] = ref_exec["curtail_mw"]
        plan["cash_cny"] = ref_exec["cash_cny"]
        plan["export_mwh"] = ref_exec["export_mwh"]
        plan["import_mwh"] = ref_exec["import_mwh"]
        plan["curtail_mwh"] = ref_exec["curtail_mwh"]
        plan_cache[cache_key] = plan
        cache_entry = plan

    plan = cache_entry
    charge = plan["charge_mw"]
    discharge = plan["discharge_mw"]
    charge_slots = [t for t in range(n) if charge[t] > 1e-6]
    discharge_slots = [t for t in range(n) if discharge[t] > 1e-6]
    charge_anchor = min((da[t] for t in charge_slots), default=min(da))
    discharge_anchor = max((da[t] for t in discharge_slots), default=max(da))
    rte = float(config["asset"]["storage"]["rte"])
    deg = pred["degradation"]
    discharge_breakeven = charge_anchor / rte + deg * (1.0 + 1.0 / rte)
    charge_breakeven = discharge_anchor * rte - deg * (1.0 + rte)

    offer = []
    bid = []
    for slot in range(n):
        markup = (
            pred["spike_markup"]
            if da[slot] >= pred["spike_threshold"]
            else pred["discharge_markup"]
        )
        raw_offer = discharge_breakeven + markup
        raw_bid = charge_breakeven - pred["charge_markup"]
        offer.append(min(pred["model_cap"], max(pred["model_floor"], raw_offer)))
        bid.append(min(pred["model_cap"], max(pred["model_floor"], raw_bid)))

    rows = []
    for slot in range(n):
        rows.append(
                {
                    "date": None,
                    "slot": slot,
                    "start": d1["start"][slot],
                    "end": d1["end"][slot],
                    "side": "renewable_joint",
                    "quantity_mw": declared[slot],
                    "price_cny_per_mwh": pred["renewable_bid_price"],
                    "reference_price": da[slot],
                    "clear_probability": sum(
                        weights[s] for s in range(len(weights)) if d1["prices"][s][slot] >= 0.0
                    ),
                    "expected_mw": declared[slot],
                    "soc_plan": round(plan["soc"][slot], 4),
                    "note": (
                        f"q={q:.2f}; wind+pv joint 报量报价; DA pre-clear is reference only"
                    ),
                }
            )
        if discharge[slot] > 1e-6:
            probability = sum(
                weights[s] for s in range(len(weights)) if d1["prices"][s][slot] >= offer[slot] - 1e-9
            )
            rows.append(
                {
                    "date": None,
                    "slot": slot,
                    "start": d1["start"][slot],
                    "end": d1["end"][slot],
                    "side": "storage_discharge",
                    "quantity_mw": round(discharge[slot], 3),
                    "price_cny_per_mwh": round(offer[slot], 2),
                    "reference_price": da[slot],
                    "clear_probability": round(probability, 4),
                    "expected_mw": round(discharge[slot] * probability, 3),
                    "soc_plan": round(plan["soc"][slot], 4),
                    "note": (
                        f"breakeven={discharge_breakeven:.1f}; ban=price<0"
                        + ("; spike markup" if da[slot] >= pred["spike_threshold"] else "")
                    ),
                }
            )
        if charge[slot] > 1e-6:
            probability = sum(
                weights[s] for s in range(len(weights)) if d1["prices"][s][slot] <= bid[slot] + 1e-9
            )
            rows.append(
                {
                    "date": None,
                    "slot": slot,
                    "start": d1["start"][slot],
                    "end": d1["end"][slot],
                    "side": "storage_charge",
                    "quantity_mw": round(charge[slot], 3),
                    "price_cny_per_mwh": round(bid[slot], 2),
                    "reference_price": da[slot],
                    "clear_probability": round(probability, 4),
                    "expected_mw": round(charge[slot] * probability, 3),
                    "soc_plan": round(plan["soc"][slot], 4),
                    "note": (
                        f"breakeven={charge_breakeven:.1f}; charge allowed during surplus"
                        + ("; spike window" if da[slot] >= pred["spike_threshold"] else "")
                    ),
                }
            )

    return {
        "declared": declared,
        "declared_energy_mwh": declared_energy,
        "plan": plan,
        "charge_anchor_cny_per_mwh": charge_anchor,
        "discharge_anchor_cny_per_mwh": discharge_anchor,
        "discharge_breakeven_cny_per_mwh": discharge_breakeven,
        "charge_breakeven_cny_per_mwh": charge_breakeven,
        "offer": offer,
        "bid": bid,
        "rows": rows,
        "ren_scenarios": ren_scenarios,
    }


def evaluate_strategy(d1, bid, strategy, config, report):
    """Evaluate one strategy over the five paired scenarios (plan fixed)."""
    pred = report["predicates"]
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    weights = pred["scenario_weights"]
    plan = bid["plan"]
    charge = plan["charge_mw"]
    discharge = plan["discharge_mw"]
    has_storage = not strategy.get("no_storage", False)
    if not has_storage:
        charge = [0.0] * n
        discharge = [0.0] * n
    outcomes = []
    for index in range(len(d1["prices"])):
        renewables = bid["ren_scenarios"][index]
        prices = d1["prices"][index]
        execution = execute_plan(charge, discharge, renewables, prices, pred)
        available_mwh = sum(renewables) * dt_h
        wind_mwh = sum(d1["wind"][index]) * dt_h
        pv_mwh = sum(d1["pv"][index]) * dt_h
        opex = pred["opex_wind"] * wind_mwh + pred["opex_pv"] * pv_mwh
        ratio, penalty = deviation_penalty(
            available_mwh, bid["declared_energy_mwh"], pred["band"], pred["penalty"]
        )
        net = execution["cash_cny"] - opex - pred["fixed"] - penalty
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "available_mwh": available_mwh,
                "wind_mwh": wind_mwh,
                "pv_mwh": pv_mwh,
                "export_mwh": execution["export_mwh"],
                "import_mwh": execution["import_mwh"],
                "curtail_mwh": execution["curtail_mwh"],
                "charge_mwh": execution["charge_mwh"],
                "discharge_mwh": execution["discharge_mwh"],
                "spot_cash_cny": execution["cash_cny"],
                "opex_cny": opex,
                "fixed_cny": pred["fixed"],
                "deviation_ratio": ratio,
                "deviation_penalty_cny": penalty,
                "ban_violation_slots": execution["ban_violation_slots"],
                "cycles": execution["cycles"],
                "net_margin_cny": net,
            }
        )
    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    alpha = 0.20
    cvar = desk.weighted_cvar(
        [(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=alpha
    )
    expected_curtail = sum(item["weight"] * item["curtail_mwh"] for item in outcomes)
    expected_penalty = sum(item["weight"] * item["deviation_penalty_cny"] for item in outcomes)
    expected_violations = sum(item["weight"] * item["ban_violation_slots"] for item in outcomes)
    return {
        "strategy": strategy,
        "outcomes": outcomes,
        "expected_net_margin_cny": expected,
        "cvar_cny": cvar,
        "cvar_confidence": 0.8,
        "expected_curtail_mwh": expected_curtail,
        "expected_deviation_penalty_cny": expected_penalty,
        "expected_ban_violation_slots": expected_violations,
        "plan_cycles": plan["cycles"] if has_storage else 0.0,
    }


def separate_storage_dispatch(d1, config, report, adder):
    """Plan the standalone storage (no renewables behind the meter)."""
    pred = report["predicates"]
    n = pred["points_per_day"]
    da = d1["da_price"]
    ban = ban_mask_from_prices(da) if pred["ban_enabled"] else [False] * n
    plan, lam, probes = solve_plan(
        da,
        [0.0] * n,
        pred,
        ban,
        pred["cycle_cap"],
        export_limit=pred["storage_power_mw"],
        import_limit=pred["storage_power_mw"],
    )
    charge, discharge, violations, repairs = enforce_min_run(
        plan["charge_mw"], plan["discharge_mw"], pred["min_run_slots"], pred
    )
    plan["charge_mw"] = charge
    plan["discharge_mw"] = discharge
    throughput = (sum(charge) + sum(discharge)) * pred["dt_h"]
    plan["throughput_mwh"] = throughput
    plan["charge_mwh"] = sum(charge) * pred["dt_h"]
    plan["discharge_mwh"] = sum(discharge) * pred["dt_h"]
    plan["cycles"] = throughput / (2.0 * pred["storage_energy_mwh"])
    plan["min_run_violations"] = violations
    plan["min_run_repairs"] = repairs
    plan["lagrange_multiplier"] = lam
    return plan


def build_joint_vs_separate(d1, joint_bid, joint_results, separate_plan, config, report, adder=0.0):
    """Joint net margin vs wind+PV + standalone storage, per scenario."""
    pred = report["predicates"]
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    weights = pred["scenario_weights"]
    charge = separate_plan["charge_mw"]
    discharge = separate_plan["discharge_mw"]
    exp_lim = pred["storage_power_mw"]
    rows = []
    for index in range(len(d1["prices"])):
        renewables = joint_bid["ren_scenarios"][index]
        prices = d1["prices"][index]
        wind_pv_cash = 0.0
        for t in range(n):
            wind_pv_cash += min(renewables[t], pred["export_limit_mw"]) * prices[t] * dt_h
        storage_cash = 0.0
        for t in range(n):
            net = discharge[t] - charge[t]
            export = net if net > 0.0 else 0.0
            import_mw = -net if net < 0.0 else 0.0
            storage_cash += (export - import_mw) * prices[t] * dt_h
        storage_cash -= adder * sum(charge) * dt_h
        joint_net = joint_results[index]["net_margin_cny"]
        opex = pred["opex_wind"] * joint_results[index]["wind_mwh"] + pred["opex_pv"] * joint_results[index]["pv_mwh"]
        separate_net = (
            wind_pv_cash
            + storage_cash
            - opex
            - pred["fixed"]
            - joint_results[index]["deviation_penalty_cny"]
        )
        rows.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "joint_net_cny": joint_net,
                "separate_net_cny": separate_net,
                "gain_cny": joint_net - separate_net,
                "wind_pv_curtail_mwh": sum(
                    max(0.0, renewables[t] - pred["export_limit_mw"]) for t in range(n)
                )
                * dt_h,
            }
        )
    expected = {
        "joint_net_cny": sum(row["weight"] * row["joint_net_cny"] for row in rows),
        "separate_net_cny": sum(row["weight"] * row["separate_net_cny"] for row in rows),
        "gain_cny": sum(row["weight"] * row["gain_cny"] for row in rows),
        "wind_pv_curtail_mwh": sum(row["weight"] * row["wind_pv_curtail_mwh"] for row in rows),
    }
    return {"rows": rows, "expected": expected, "adder_cny_per_mwh": adder}


def settle_actual(t1, d1, joint_bid, config, report):
    """Replay the T+1 full-volume real-time settlement with the fixed plan."""
    pred = report["predicates"]
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    plan = joint_bid["plan"]
    charge = plan["charge_mw"]
    discharge = plan["discharge_mw"]
    renewables = [t1["wind_mw"][t] + t1["pv_mw"][t] for t in range(n)]
    execution = execute_plan(charge, discharge, renewables, t1["rt_price"], pred)
    available_mwh = sum(renewables) * dt_h
    wind_mwh = sum(t1["wind_mw"]) * dt_h
    pv_mwh = sum(t1["pv_mw"]) * dt_h
    opex = pred["opex_wind"] * wind_mwh + pred["opex_pv"] * pv_mwh
    ratio, penalty = deviation_penalty(
        available_mwh, joint_bid["declared_energy_mwh"], pred["band"], pred["penalty"]
    )
    net = execution["cash_cny"] - opex - pred["fixed"] - penalty

    da = d1["da_price"]
    plan_export_cash = sum(
        (plan["export_mw"][t] - plan["import_mw"][t]) * da[t] for t in range(n)
    ) * dt_h
    plan_ref_renewables = plan["reference_renewables"]
    plan_wind_mwh = sum(plan_ref_renewables) * dt_h
    plan_opex = (
        pred["opex_wind"] * sum(d1["forecast_wind"]) * dt_h
        + pred["opex_pv"] * sum(d1["forecast_pv"]) * dt_h
    )
    plan_ratio, plan_penalty = deviation_penalty(
        plan_wind_mwh, joint_bid["declared_energy_mwh"], pred["band"], pred["penalty"]
    )
    plan_net = plan_export_cash - plan_opex - pred["fixed"] - plan_penalty

    # Separate-world replay on the same actual prices (grade-D comparison).
    wind_pv_cash = 0.0
    for t in range(n):
        wind_pv_cash += min(renewables[t], pred["export_limit_mw"]) * t1["rt_price"][t] * dt_h
    storage_cash = 0.0
    for t in range(n):
        net_storage = discharge[t] - charge[t]
        export_s = net_storage if net_storage > 0.0 else 0.0
        import_s = -net_storage if net_storage < 0.0 else 0.0
        storage_cash += (export_s - import_s) * t1["rt_price"][t] * dt_h
    separate_net = wind_pv_cash + storage_cash - opex - pred["fixed"] - penalty

    return {
        "available_mwh": available_mwh,
        "wind_mwh": wind_mwh,
        "pv_mwh": pv_mwh,
        "export_mwh": execution["export_mwh"],
        "import_mwh": execution["import_mwh"],
        "curtail_mwh": execution["curtail_mwh"],
        "charge_mwh": execution["charge_mwh"],
        "discharge_mwh": execution["discharge_mwh"],
        "spot_cash_cny": execution["cash_cny"],
        "rt_capture_cny_per_mwh": (
            execution["cash_cny"] / execution["export_mwh"] if execution["export_mwh"] > 0 else None
        ),
        "opex_cny": opex,
        "fixed_cny": pred["fixed"],
        "deviation_ratio": ratio,
        "deviation_penalty_cny": penalty,
        "ban_violation_slots": execution["ban_violation_slots"],
        "cycles": execution["cycles"],
        "net_margin_cny": net,
        "plan_net_margin_cny": plan_net,
        "plan_export_cash_cny": plan_export_cash,
        "separate_net_margin_cny": separate_net,
        "joint_minus_separate_cny": net - separate_net,
        "negative_rt_slots": sum(1 for price in t1["rt_price"] if price < 0.0),
        "rt_min_cny_per_mwh": min(t1["rt_price"]),
        "rt_max_cny_per_mwh": max(t1["rt_price"]),
        "declared_energy_mwh": joint_bid["declared_energy_mwh"],
    }


def build_bridge(t1, d1, joint_bid, actual, report):
    """Five buckets from the day-ahead reference plan to the actual settlement.

    Identity (exact, because the plan is executed as-is):
      actual_cash - plan_cash
        = sum[(net_act - net_plan) - (curt_act - curt_plan)]*da*dt   (quantity)
        + sum[net_act]*(rt - da)*dt                                  (price)
    with net_act - net_plan = ren_act - ren_ref when the plan is unchanged.
    """
    pred = report["predicates"]
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    da = d1["da_price"]
    plan = joint_bid["plan"]
    charge = plan["charge_mw"]
    discharge = plan["discharge_mw"]
    ren_ref = plan["reference_renewables"]
    ren_act = [t1["wind_mw"][t] + t1["pv_mw"][t] for t in range(n)]
    rt = t1["rt_price"]

    quantity_effect = 0.0
    price_effect = 0.0
    for t in range(n):
        net_act = ren_act[t] + discharge[t] - charge[t]
        curt_act = max(0.0, net_act - pred["export_limit_mw"]) if net_act > 0 else 0.0
        net_plan = ren_ref[t] + discharge[t] - charge[t]
        curt_plan = max(0.0, net_plan - pred["export_limit_mw"]) if net_plan > 0 else 0.0
        quantity_effect += ((net_act - net_plan) - (curt_act - curt_plan)) * da[t] * dt_h
        export_act = min(max(net_act, 0.0), pred["export_limit_mw"])
        import_act = max(0.0, -net_act)
        price_effect += (export_act - import_act) * (rt[t] - da[t]) * dt_h

    opex_effect = -(actual["opex_cny"] - (
        pred["opex_wind"] * sum(d1["forecast_wind"]) * dt_h
        + pred["opex_pv"] * sum(d1["forecast_pv"]) * dt_h
    ))
    plan_throughput = (sum(charge) + sum(discharge)) * dt_h
    actual_throughput = plan_throughput
    degradation_effect = -pred["degradation"] * (actual_throughput - plan_throughput)
    assessment_effect = -(actual["deviation_penalty_cny"] - 0.0)

    buckets = [
        {
            "item": "风光可用电量偏差（含出口限额弃电，按日前价）",
            "category": "电量",
            "owner": "预测/执行",
            "amount": quantity_effect,
        },
        {
            "item": "实时价格效应（按实际净上网）",
            "category": "价格",
            "owner": "市场",
            "amount": price_effect,
        },
        {
            "item": "运维成本偏差",
            "category": "成本",
            "owner": "财务",
            "amount": opex_effect,
        },
        {
            "item": "退化成本偏差",
            "category": "成本",
            "owner": "运维",
            "amount": degradation_effect,
        },
        {
            "item": "申报偏差考核",
            "category": "考核",
            "owner": "调度/考核",
            "amount": assessment_effect,
        },
    ]
    total = sum(item["amount"] for item in buckets)
    return {
        "plan_profit": actual["plan_net_margin_cny"],
        "actual_profit": actual["net_margin_cny"],
        "delta": actual["net_margin_cny"] - actual["plan_net_margin_cny"],
        "identity_gap": actual["net_margin_cny"] - actual["plan_net_margin_cny"] - total,
        "buckets": buckets,
        "plan_spot_cash_cny": actual["plan_export_cash_cny"],
        "actual_spot_cash_cny": actual["spot_cash_cny"],
    }


def bridge_detail(t1, d1, joint_bid, report):
    pred = report["predicates"]
    dt_h = pred["dt_h"]
    plan = joint_bid["plan"]
    charge = plan["charge_mw"]
    discharge = plan["discharge_mw"]
    ren_ref = plan["reference_renewables"]
    ren_act = [t1["wind_mw"][t] + t1["pv_mw"][t] for t in range(pred["points_per_day"])]
    detail = []
    for t in range(pred["points_per_day"]):
        net_act = ren_act[t] + discharge[t] - charge[t]
        net_plan = ren_ref[t] + discharge[t] - charge[t]
        export_act = min(max(net_act, 0.0), pred["export_limit_mw"])
        export_plan = min(max(net_plan, 0.0), pred["export_limit_mw"])
        detail.append(
            {
                "slot": t,
                "start": _slot_time(t, pred["mtu_min"]),
                "declared_mw": joint_bid["declared"][t],
                "renewable_mw": round(ren_act[t], 2),
                "charge_mw": round(charge[t], 2),
                "discharge_mw": round(discharge[t], 2),
                "export_mw": round(export_act, 2),
                "curtail_mw": round(max(0.0, net_act - export_act), 2),
                "rt_price": t1["rt_price"][t],
                "quantity_effect_cny": (net_act - net_plan) * d1["da_price"][t] * dt_h,
            }
        )
    detail.sort(key=lambda item: abs(item["quantity_effect_cny"]), reverse=True)
    return detail[:5]


def _scaled_joint_plan(d1, pred, report, price_multiplier=1.0, renewable_multiplier=1.0, cycle_cap=None):
    n = pred["points_per_day"]
    da = [price * price_multiplier for price in d1["da_price"]]
    ren_scenarios = [scenario_renewables(d1, index) for index in range(len(d1["wind"]))]
    ref = [
        quantile([ren_scenarios[s][t] for s in range(len(ren_scenarios))], pred["price_reference_quantile"])
        for t in range(n)
    ]
    ref = [value * renewable_multiplier for value in ref]
    ban = ban_mask_from_prices(da) if pred["ban_enabled"] else [False] * n
    cap = pred["cycle_cap"] if cycle_cap is None else float(cycle_cap)
    plan, lam, probes = solve_plan(da, ref, pred, ban, cap)
    charge, discharge, violations, repairs = enforce_min_run(
        plan["charge_mw"], plan["discharge_mw"], pred["min_run_slots"], pred
    )
    plan["charge_mw"] = charge
    plan["discharge_mw"] = discharge
    throughput = (sum(charge) + sum(discharge)) * pred["dt_h"]
    plan["throughput_mwh"] = throughput
    plan["cycles"] = throughput / (2.0 * pred["storage_energy_mwh"])
    plan["min_run_violations"] = violations
    plan["min_run_repairs"] = repairs
    plan["reference_renewables"] = ref
    plan["lagrange_multiplier"] = lam
    plan["da_scaled"] = da
    plan["ren_scale"] = renewable_multiplier
    plan["charge_mwh"] = sum(plan["charge_mw"]) * pred["dt_h"]
    plan["discharge_mwh"] = sum(plan["discharge_mw"]) * pred["dt_h"]
    ref_exec = execute_plan(plan["charge_mw"], plan["discharge_mw"], ref, da, pred)
    plan["export_mw"] = ref_exec["export_mw"]
    plan["import_mw"] = ref_exec["import_mw"]
    plan["curtail_mw"] = ref_exec["curtail_mw"]
    plan["cash_cny"] = ref_exec["cash_cny"]
    return plan


def _evaluate_scaled(d1, bid, strategy, config, report, plan, price_multiplier=1.0, renewable_multiplier=1.0):
    pred = report["predicates"]
    n = pred["points_per_day"]
    dt_h = pred["dt_h"]
    weights = pred["scenario_weights"]
    outcomes = []
    for index in range(len(d1["prices"])):
        renewables = [value * renewable_multiplier for value in bid["ren_scenarios"][index]]
        prices = [value * price_multiplier for value in d1["prices"][index]]
        execution = execute_plan(plan["charge_mw"], plan["discharge_mw"], renewables, prices, pred)
        available_mwh = sum(renewables) * dt_h
        wind_mwh = sum(d1["wind"][index]) * dt_h * renewable_multiplier
        pv_mwh = sum(d1["pv"][index]) * dt_h * renewable_multiplier
        opex = pred["opex_wind"] * wind_mwh + pred["opex_pv"] * pv_mwh
        declared = bid["declared_energy_mwh"] * renewable_multiplier
        ratio, penalty = deviation_penalty(available_mwh, declared, pred["band"], pred["penalty"])
        net = execution["cash_cny"] - opex - pred["fixed"] - penalty
        outcomes.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "curtail_mwh": execution["curtail_mwh"],
                "cycles": execution["cycles"],
                "ban_violation_slots": execution["ban_violation_slots"],
                "deviation_penalty_cny": penalty,
                "net_margin_cny": net,
            }
        )
    expected = sum(item["weight"] * item["net_margin_cny"] for item in outcomes)
    cvar = desk.weighted_cvar(
        [(item["net_margin_cny"], item["weight"]) for item in outcomes], alpha=0.20
    )
    return {
        "outcomes": outcomes,
        "expected_net_margin_cny": expected,
        "cvar_cny": cvar,
        "expected_curtail_mwh": sum(item["weight"] * item["curtail_mwh"] for item in outcomes),
        "expected_deviation_penalty_cny": sum(
            item["weight"] * item["deviation_penalty_cny"] for item in outcomes
        ),
        "expected_ban_violation_slots": sum(
            item["weight"] * item["ban_violation_slots"] for item in outcomes
        ),
        "plan_cycles": plan["cycles"],
    }


def build_sensitivity(d1, joint_bid, selected, config, report):
    cases = []
    policy = config["policy"]
    sens = policy["sensitivity"]
    base = selected["expected_net_margin_cny"]

    def add(name, change, result):
        cases.append(
            {
                "case": name,
                "change": change,
                "expected_net_margin_cny": result["expected_net_margin_cny"],
                "delta_vs_selected_cny": result["expected_net_margin_cny"] - base,
                "cvar_cny": result["cvar_cny"],
                "plan_cycles": result["plan_cycles"],
                "expected_curtail_mwh": result["expected_curtail_mwh"],
                "expected_deviation_penalty_cny": result["expected_deviation_penalty_cny"],
                "expected_ban_violation_slots": result["expected_ban_violation_slots"],
            }
        )

    for multiplier in sens["price_multipliers"]:
        plan = _scaled_joint_plan(d1, report["predicates"], report, price_multiplier=multiplier)
        result = _evaluate_scaled(
            d1, joint_bid, selected["strategy"], config, report, plan, price_multiplier=multiplier
        )
        add(f"实时价 ×{multiplier:.2f}", f"全部日前/情景价 ×{multiplier:.2f}，储能按新价格重新计划", result)
    for multiplier in sens["renewable_multipliers"]:
        plan = _scaled_joint_plan(d1, report["predicates"], report, renewable_multiplier=multiplier)
        result = _evaluate_scaled(
            d1, joint_bid, selected["strategy"], config, report, plan, renewable_multiplier=multiplier
        )
        add(
            f"风光出力 ×{multiplier:.2f}",
            f"全部风光情景 ×{multiplier:.2f}，重新申报与重新计划",
            result,
        )
    alt_cap = float(sens["cycle_cap_alternative"])
    if abs(alt_cap - report["predicates"]["cycle_cap"]) > 1e-9:
        plan = _scaled_joint_plan(d1, report["predicates"], report, cycle_cap=alt_cap)
        result = _evaluate_scaled(d1, joint_bid, selected["strategy"], config, report, plan)
        add(
            f"循环上限 {alt_cap:.1f} 次",
            f"把征求意见稿 1.5 次/日上限放开到 {alt_cap:.1f} 次（仅对照，非合规口径）",
            result,
        )
    combined = sens["combined"]
    plan = _scaled_joint_plan(
        d1,
        report["predicates"],
        report,
        price_multiplier=combined["price_multiplier"],
        renewable_multiplier=combined["renewable_multiplier"],
    )
    result = _evaluate_scaled(
        d1,
        joint_bid,
        selected["strategy"],
        config,
        report,
        plan,
        price_multiplier=combined["price_multiplier"],
        renewable_multiplier=combined["renewable_multiplier"],
    )
    add(
        "组合压力",
        f"实时价 ×{combined['price_multiplier']:.2f} 且风光出力 ×{combined['renewable_multiplier']:.2f}",
        result,
    )
    return cases


def build_thresholds(d1, joint_bid, selected, separate, config, report):
    pred = report["predicates"]
    charge_mwh = sum(joint_bid["plan"]["charge_mw"]) * pred["dt_h"]
    gain0 = separate["expected"]["gain_cny"]
    if charge_mwh > 1e-9:
        adder_breakeven = -gain0 / charge_mwh
    else:
        adder_breakeven = None
    return {
        "discharge_breakeven_cny_per_mwh": joint_bid["discharge_breakeven_cny_per_mwh"],
        "charge_breakeven_cny_per_mwh": joint_bid["charge_breakeven_cny_per_mwh"],
        "joint_vs_separate_adder_breakeven_cny_per_mwh": adder_breakeven,
        "adder_breakeven_note": (
            "线性外推近似：沿用加成 0 的分开储能计划，只移动充电现金；未重解分开调度"
            if adder_breakeven is not None
            else "分开计划无充电量，无法定义加成临界"
        ),
    }


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _signed(value):
    return "—" if value is None else f"{value:+,.0f}"


def _neg_money(value):
    """Amount that is displayed as a deduction; zero stays plain 0."""
    if value is None:
        return "—"
    if abs(value) < 0.5:
        return "0"
    return f"−{value:,.0f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def write_review(path, config, report, d1, results, selected_name, selected, actual, bridge,
                 bridge_top, separate_zero, separate_adder, sensitivity, thresholds, fingerprint):
    pred = report["predicates"]
    policy = config["policy"]
    bid = selected["bid"]
    lines = [
        "# 蒙西风光储联合申报 · 复核表",
        "",
        f"> 实例 `{config['meta']['instance_id']}` · {config['meta']['province']} · "
        f"{config['meta']['entity_type']} · 交易日 {d1['date']}（{pred['points_per_day']} 点 / {pred['mtu_min']} 分钟） · "
        f"数据截止 {config['meta']['data_cutoff']} · 等级 {config['meta']['grade']}",
        "",
        "## 1. 结论",
        "",
        f"- 选中策略 **{selected['strategy']['label']}**：情景期望净收益 **{_money(selected['expected_net_margin_cny'])} 元**，"
        f"CVaR(80%) {_money(selected['cvar_cny'])} 元；储能计划循环 {selected['plan_cycles']:.2f} 次/日"
        f"（征求意见稿上限 {pred['cycle_cap']:.1f} 次，C）。",
            f"- 风光联合申报电量 **{_money(selected['bid']['declared_energy_mwh'])} MWh**（P{selected['strategy']['declared_quantity_quantile'] * 100:.0f} 分位），"
        f"期望弃电 {_money(selected['expected_curtail_mwh'])} MWh，期望偏差考核 {_neg_money(selected['expected_deviation_penalty_cny'])} 元。",
        f"- 联合 vs 分开（同价口径）：期望差额 **{_signed(separate_zero['expected']['gain_cny'])} 元**；"
        f"分开充电加成 180 元/MWh（D 级占位）时期望差额 {_signed(separate_adder['expected']['gain_cny'])} 元。",
        f"- T+1 实际净收益 **{_money(actual['net_margin_cny'])} 元**（日前参考计划 {_money(actual['plan_net_margin_cny'])} 元），"
        f"实际弃电 {_money(actual['curtail_mwh'])} MWh，负价时段 {actual['negative_rt_slots']} 个，"
        f"禁放违规时段 {actual['ban_violation_slots']} 个。",
        "",
        "**一句话**：风光储同一场站联合参与，储能的调度自由度被征求意见稿的三条约束（弃电禁放、1.5 次循环、最小连续 30 分钟）压缩；"
        "联合与分开的现金流差异在单一节点价下主要来自出口限额共享与弃电回收，充电结算口径才是真正的分水岭。",
        "",
        "## 2. 规则来源与级别",
        "",
        "| 规则块 | 级别 | 来源 |",
        "|---|---|---|",
    ]
    for item in report["provenance"]:
        lines.append(f"| {item['block']} | {item['grade']} | {item['source']} |")
    lines.extend(
        [
            "",
            "储能参与条款整块为 C 级征求意见稿（非正式规则）；现行限价、储能充电结算口径、富裕度指标定义均待核。",
            "",
            "## 3. 策略对比（五情景期望）",
            "",
            "| 策略 | 申报分位 | 合规 | 期望净收益（元） | CVaR（元） | 期望弃电（MWh） | 期望考核（元） | 期望禁放违规时段 | 循环 |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in results:
        lines.append(
            f"| {item['strategy']['label']} | P{item['strategy']['declared_quantity_quantile'] * 100:.0f} | "
            f"{'是' if item['strategy'].get('compliant') else '否（对照）'} | "
            f"{_money(item['expected_net_margin_cny'])} | {_money(item['cvar_cny'])} | "
            f"{_money(item['expected_curtail_mwh'])} | {_neg_money(item['expected_deviation_penalty_cny'])} | "
            f"{item['expected_ban_violation_slots']:.1f} | {item['plan_cycles']:.2f} |"
        )
    lines.extend(
        [
            "",
            f"选择规则：仅在有储能且合规的策略中取期望净收益最大（`compliant_only_selection=true`）；"
            f"「禁放不执行」与「无储能」两行是对照，不是可选策略。",
            "",
            "注意：若「禁放不执行」与「禁放执行」两行数字相同，说明禁放条款在本演示日不 binding——"
            "无约束的最优套利本来就不在负价时段放电；禁放真正咬合的是「负价时段被迫放电腾容量再充」"
            "这类与循环上限/SOC 窗口组合的操作，换价格形态后须重查。",
            "",
            "## 4. 选中策略情景明细",
            "",
            "| 情景 | 权重 | 可用电量（MWh） | 弃电（MWh） | 上网（MWh） | 充电（MWh） | 放电（MWh） | 现货现金（元） | 偏差率 | 考核（元） | 禁放违规 | 净收益（元） |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for outcome in selected["outcomes"]:
        lines.append(
            f"| s{outcome['scenario']} | {outcome['weight']:.0%} | {_money(outcome['available_mwh'])} | "
            f"{_money(outcome['curtail_mwh'])} | {_money(outcome['export_mwh'])} | "
            f"{_money(outcome['charge_mwh'])} | {_money(outcome['discharge_mwh'])} | "
            f"{_money(outcome['spot_cash_cny'])} | {_pct(outcome['deviation_ratio'])} | "
            f"{_neg_money(outcome['deviation_penalty_cny'])} | {outcome['ban_violation_slots']} | "
            f"{_money(outcome['net_margin_cny'])} |"
        )
    lines.extend(
        [
            "",
            "s1 是「大发 + 午间深负价」情景，s5 是「小发 + 高价」情景；风、光、价按同一情景编号配对，不能独立抽样后拼配。",
            "",
            "## 5. T+1 实际结算与差异桥",
            "",
            "| 项目 | 值 |",
            "|---|---:|",
            f"| 实际风光可用电量 | {_money(actual['available_mwh'])} MWh |",
            f"| 实际上网电量 / 弃电 | {_money(actual['export_mwh'])} / {_money(actual['curtail_mwh'])} MWh |",
            f"| 实时捕获价 | {_money(actual['rt_capture_cny_per_mwh'])} 元/MWh |",
            f"| 现货现金（实时全电量） | {_money(actual['spot_cash_cny'])} 元 |",
            f"| 储能充电 / 放电 | {_money(actual['charge_mwh'])} / {_money(actual['discharge_mwh'])} MWh |",
            f"| 运维成本 | {_money(actual['opex_cny'])} 元 |",
            f"| 申报偏差率（免考核带 ±{pred['band']:.0%}） | {_pct(actual['deviation_ratio'])} |",
            f"| 申报偏差考核 | {_neg_money(actual['deviation_penalty_cny'])} 元 |",
            f"| **实际净收益** | **{_money(actual['net_margin_cny'])} 元** |",
            f"| 日前参考计划净收益（不用于结算） | {_money(actual['plan_net_margin_cny'])} 元 |",
            f"| T+1 联合 − 分开（同价口径） | {_signed(actual['joint_minus_separate_cny'])} 元 |",
            "",
            "| 差异桥科目 | 类别 | 责任 | 金额（元） |",
            "|---|---|---|---:|",
        ]
    )
    for item in bridge["buckets"]:
        lines.append(f"| {item['item']} | {item['category']} | {item['owner']} | {_signed(item['amount'])} |")
    lines.append(f"| **合计** | | | **{_signed(bridge['delta'])}** |")
    lines.extend(
        [
            f"",
            f"差异桥残差 {bridge['identity_gap']:.2e} 元（计划即执行的恒等式）。日前预出清只作对照，不是结算依据。",
            "",
            "量差影响最大的时段：",
            "",
            "| 时段 | 申报（MW） | 风光（MW） | 充电（MW） | 放电（MW） | 上网（MW） | 弃电（MW） | 实时价 | 量差影响（元） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in bridge_top:
        lines.append(
            f"| {item['start']} | {item['declared_mw']:.1f} | {item['renewable_mw']:.1f} | "
            f"{item['charge_mw']:.1f} | {item['discharge_mw']:.1f} | {item['export_mw']:.1f} | "
            f"{item['curtail_mw']:.1f} | {item['rt_price']:.2f} | {_signed(item['quantity_effect_cny'])} |"
        )
    lines.extend(
        [
            "",
            "## 6. 联合 vs 分开收益对照",
            "",
            "分开口径：风光按同一出口限额上网（超限弃电且不可回收），储能独立并网、按同一节点价充放电、"
            "同样受禁放/循环/最小连续约束；差额 = 联合净收益 − 分开净收益（运维、固定成本与偏差考核两边相同）。",
            "",
            "| 口径 | s1 | s2 | s3 | s4 | s5 | 期望 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lines.append(
        "| 联合净收益（元） | "
        + " | ".join(_money(row["joint_net_cny"]) for row in separate_zero["rows"])
        + f" | {_money(separate_zero['expected']['joint_net_cny'])} |"
    )
    lines.append(
        "| 分开净收益·加成 0（元） | "
        + " | ".join(_money(row["separate_net_cny"]) for row in separate_zero["rows"])
        + f" | {_money(separate_zero['expected']['separate_net_cny'])} |"
    )
    lines.append(
        "| 差额·加成 0（元） | "
        + " | ".join(_signed(row["gain_cny"]) for row in separate_zero["rows"])
        + f" | **{_signed(separate_zero['expected']['gain_cny'])}** |"
    )
    lines.append(
        "| 分开净收益·加成 180（元） | "
        + " | ".join(_money(row["separate_net_cny"]) for row in separate_adder["rows"])
        + f" | {_money(separate_adder['expected']['separate_net_cny'])} |"
    )
    lines.append(
        "| 差额·加成 180（元） | "
        + " | ".join(_signed(row["gain_cny"]) for row in separate_adder["rows"])
        + f" | **{_signed(separate_adder['expected']['gain_cny'])}** |"
    )
    lines.extend(
        [
            "",
            f"- 分开口径下风光超限弃电期望 {_money(separate_zero['expected']['wind_pv_curtail_mwh'])} MWh；"
            f"联合口径把这部分改由储能消纳（充电机会成本为零）。",
            f"- 加成临界值（线性外推）：**{_money(thresholds['joint_vs_separate_adder_breakeven_cny_per_mwh'])} 元/MWh**"
            f"——分开储能充电加成高于该值时，分开模式劣于联合；该值为负表示加成 0 下联合已占优"
            f"（{thresholds['adder_breakeven_note']}）。",
            "- 该对照是同价口径（分开储能按同一节点价充放电）。若分开储能充电按含输配电价与附加的用户侧口径结算，"
            "联合优势会显著扩大——蒙西独立储能充电结算口径未核到（待核）。",
            "",
            "## 7. 敏感性与临界值",
            "",
            "| 情景 | 关键变化 | 期望净收益（元） | 较选中（元） | CVaR（元） | 循环 | 期望弃电（MWh） | 期望考核（元） | 期望禁放违规 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case in sensitivity:
        lines.append(
            f"| {case['case']} | {case['change']} | {_money(case['expected_net_margin_cny'])} | "
            f"{_signed(case['delta_vs_selected_cny'])} | {_money(case['cvar_cny'])} | "
            f"{case['plan_cycles']:.2f} | {_money(case['expected_curtail_mwh'])} | "
            f"{_neg_money(case['expected_deviation_penalty_cny'])} | {case['expected_ban_violation_slots']:.1f} |"
        )
    lines.extend(
        [
            "",
            f"- 储能放电保本价 **{thresholds['discharge_breakeven_cny_per_mwh']:.1f} 元/MWh**"
            f"（充电锚点 {bid['charge_anchor_cny_per_mwh']:.1f}）；"
            f"充电保本价 **{thresholds['charge_breakeven_cny_per_mwh']:.1f} 元/MWh**"
            f"（放电锚点 {bid['discharge_anchor_cny_per_mwh']:.1f}）。联合模式下充电的机会成本是放弃的上网收益，保本式为 D 级近似。",
            "",
            "## 8. 口径提醒",
            "",
            "- **储能条款是 C 级征求意见稿**：弃电禁放（富裕程度<0 不得放电）、SOC 窗口 0-10%/90-100%、循环上限 1.5 次、"
            "最小连续 30 分钟、报量报价/不报价自主选择，全部出自 2026-02-14 征求意见稿，未生效；本包另以“价<0”作 D 级禁放代理。",
            "- **限价三套口径**：早期 4-10 月 40-550、其他月 40-600（B，历史，申报/出清同区间）；2025 实绩 -48.66~1555.85（B）；"
            "2026 草案 -50~1500（C，未生效）。现行参数待核；本包模型边界只覆盖实绩。",
            "- **单轨制全电量结算**：日前预出清只是参考，实际按实时（用户侧节点电价分区口径）结算；中长期是差价合约。"
            "本包未建模中长期与结算参考点。",
            "- **机制电价**：0.2829 元/kWh 只适用存量项目；本包资产按 2025-06-01 后增量口径，无保底价、暂不纳入机制；"
            "0.28 元/kWh 储能度电补贴是行业口径（C/D），与 0.2829 性质不同，本包均未计入。",
            "- **负价时段的储能行为**：禁放只禁放、不禁充——负价时充电（含表后消纳与净进口）依然有利；"
            "「先放后充腾容量」的做法被禁放条款切断，与循环上限 1.5 次共同压缩操作空间。",
            "- **联合 vs 分开的结论依赖充电结算口径**：同价口径下两者接近，差异主要来自出口限额共享与弃电回收；"
            "若分开储能充电含输配及附加，结论反转。结算口径待核。",
            "- **申报偏差考核是 D 级简化**：只对风光可用电量（弃电前）与申报电量比较，超出 ±5% 按 30 元/MWh 计；"
            "储能偏差口径未核到，本包储能偏差按实时价结算、不设考核。",
            "- **5 分钟出清被建模为 288 点 DP**：不模拟 5 分钟内滚动决策、爬坡、断面与场站控制；"
            "储能按计划执行是 D 级假设，禁放违规只统计不强改。",
            f"风格指纹 `{fingerprint}`；本复核表由 `run.py` 生成，计算期 {d1['date']} 单日 {pred['points_per_day']} 点。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fingerprint(policy):
    canonical = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def run_instance(instance_path, d1_path, t1_path, out_dir=None):
    instance_path = Path(instance_path)
    if not instance_path.exists():
        raise ConfigError(f"instance file not found: {instance_path}")
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{instance_path.name} is not valid JSON: {exc}") from exc
    report = validate_instance(config)
    d1 = read_d1(Path(d1_path), config, report)
    t1 = None
    if t1_path is not None:
        t1 = read_t1(Path(t1_path), config, report)
        if t1["date"] != d1["date"]:
            raise ConfigError("D-1 and T+1 files must refer to the same trading day")

    pred = report["predicates"]
    plan_cache = {}
    results = []
    bids = {}
    for name, strategy in config["policy"]["strategies"].items():
        bid = build_joint_bid(d1, strategy, config, report, plan_cache)
        bids[name] = bid
        result = evaluate_strategy(d1, bid, strategy, config, report)
        result["name"] = name
        result["bid"] = bid
        results.append(result)
    report["strategy_results"] = results

    eligible = [
        item
        for item in results
        if item["strategy"].get("compliant") and not item["strategy"].get("no_storage")
    ]
    if not eligible:
        raise ConfigError("no compliant storage strategy available for selection")
    selected = max(eligible, key=lambda item: (item["expected_net_margin_cny"], item["cvar_cny"]))
    selected_name = selected["name"]
    joint_bid = selected["bid"]

    separate_plan_zero = separate_storage_dispatch(d1, config, report, 0.0)
    separate_zero = build_joint_vs_separate(
        d1, joint_bid, selected["outcomes"], separate_plan_zero, config, report, adder=0.0
    )
    adder_value = float(config["policy"]["sensitivity"]["separate_charge_adder_cny_per_mwh"])
    separate_plan_adder = separate_storage_dispatch(d1, config, report, adder_value)
    separate_adder = build_joint_vs_separate(
        d1, joint_bid, selected["outcomes"], separate_plan_adder, config, report, adder=adder_value
    )

    actual = None
    bridge = None
    bridge_top = []
    if t1 is not None:
        actual = settle_actual(t1, d1, joint_bid, config, report)
        bridge = build_bridge(t1, d1, joint_bid, actual, report)
        bridge_top = bridge_detail(t1, d1, joint_bid, report)

    sensitivity = build_sensitivity(d1, joint_bid, selected, config, report)
    thresholds = build_thresholds(d1, joint_bid, selected, separate_zero, config, report)

    fingerprint = _fingerprint(config["policy"])
    out_dir = Path(out_dir) if out_dir is not None else HERE / "out" / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)

    bid_rows = []
    for row in joint_bid["rows"]:
        row = dict(row)
        row["date"] = d1["date"]
        bid_rows.append(row)
    _write_csv(
        out_dir / "bid_sheet.csv",
        bid_rows,
        [
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
            "soc_plan",
            "note",
        ],
    )

    strategy_rows = []
    for item in results:
        strategy_rows.append(
            {
                "strategy": item["name"],
                "label": item["strategy"]["label"],
                "compliant": "yes" if item["strategy"].get("compliant") else "reference_only",
                "quantile": item["strategy"]["declared_quantity_quantile"],
                "expected_net_margin_cny": item["expected_net_margin_cny"],
                "cvar_cny": item["cvar_cny"],
                "expected_curtail_mwh": item["expected_curtail_mwh"],
                "expected_deviation_penalty_cny": item["expected_deviation_penalty_cny"],
                "expected_ban_violation_slots": item["expected_ban_violation_slots"],
                "plan_cycles": item["plan_cycles"],
                "declared_energy_mwh": item["bid"]["declared_energy_mwh"],
            }
        )
    _write_csv(
        out_dir / "strategies.csv",
        strategy_rows,
        [
            "strategy",
            "label",
            "compliant",
            "quantile",
            "expected_net_margin_cny",
            "cvar_cny",
            "expected_curtail_mwh",
            "expected_deviation_penalty_cny",
            "expected_ban_violation_slots",
            "plan_cycles",
            "declared_energy_mwh",
        ],
    )

    scenario_rows = []
    for outcome in selected["outcomes"]:
        scenario_rows.append(
            {
                "scenario": f"s{outcome['scenario']}",
                "weight": outcome["weight"],
                "available_mwh": outcome["available_mwh"],
                "export_mwh": outcome["export_mwh"],
                "import_mwh": outcome["import_mwh"],
                "curtail_mwh": outcome["curtail_mwh"],
                "charge_mwh": outcome["charge_mwh"],
                "discharge_mwh": outcome["discharge_mwh"],
                "spot_cash_cny": outcome["spot_cash_cny"],
                "opex_cny": outcome["opex_cny"],
                "deviation_ratio": outcome["deviation_ratio"],
                "deviation_penalty_cny": outcome["deviation_penalty_cny"],
                "ban_violation_slots": outcome["ban_violation_slots"],
                "net_margin_cny": outcome["net_margin_cny"],
            }
        )
    _write_csv(
        out_dir / "scenarios.csv",
        scenario_rows,
        [
            "scenario",
            "weight",
            "available_mwh",
            "export_mwh",
            "import_mwh",
            "curtail_mwh",
            "charge_mwh",
            "discharge_mwh",
            "spot_cash_cny",
            "opex_cny",
            "deviation_ratio",
            "deviation_penalty_cny",
            "ban_violation_slots",
            "net_margin_cny",
        ],
    )

    joint_rows = []
    for row in separate_zero["rows"]:
        joint_rows.append(
            {
                "scenario": f"s{row['scenario']}",
                "weight": row["weight"],
                "joint_net_cny": row["joint_net_cny"],
                "separate_net_adder0_cny": row["separate_net_cny"],
                "gain_adder0_cny": row["gain_cny"],
                "separate_net_adder180_cny": "",
                "gain_adder180_cny": "",
                "wind_pv_curtail_mwh": row["wind_pv_curtail_mwh"],
            }
        )
    for row in separate_adder["rows"]:
        joint_rows[row["scenario"] - 1]["separate_net_adder180_cny"] = row["separate_net_cny"]
        joint_rows[row["scenario"] - 1]["gain_adder180_cny"] = row["gain_cny"]
    joint_rows.append(
        {
            "scenario": "expected",
            "weight": "",
            "joint_net_cny": separate_zero["expected"]["joint_net_cny"],
            "separate_net_adder0_cny": separate_zero["expected"]["separate_net_cny"],
            "gain_adder0_cny": separate_zero["expected"]["gain_cny"],
            "separate_net_adder180_cny": separate_adder["expected"]["separate_net_cny"],
            "gain_adder180_cny": separate_adder["expected"]["gain_cny"],
            "wind_pv_curtail_mwh": separate_zero["expected"]["wind_pv_curtail_mwh"],
        }
    )
    _write_csv(
        out_dir / "joint_vs_separate.csv",
        joint_rows,
        [
            "scenario",
            "weight",
            "joint_net_cny",
            "separate_net_adder0_cny",
            "gain_adder0_cny",
            "separate_net_adder180_cny",
            "gain_adder180_cny",
            "wind_pv_curtail_mwh",
        ],
    )

    if t1 is not None:
        pred_dt = pred["dt_h"]
        settlement_rows = []
        plan = joint_bid["plan"]
        renewables_actual = [t1["wind_mw"][t] + t1["pv_mw"][t] for t in range(pred["points_per_day"])]
        for slot in range(pred["points_per_day"]):
            net = renewables_actual[slot] + plan["discharge_mw"][slot] - plan["charge_mw"][slot]
            export = min(max(net, 0.0), pred["export_limit_mw"])
            import_mw = max(0.0, -net)
            curtail = max(0.0, net - export)
            settlement_rows.append(
                {
                    "date": t1["date"],
                    "slot": slot,
                    "start": d1["start"][slot],
                    "end": d1["end"][slot],
                    "da_price_cny_per_mwh": t1["da_price"][slot],
                    "rt_price_cny_per_mwh": t1["rt_price"][slot],
                    "actual_wind_mw": t1["wind_mw"][slot],
                    "actual_pv_mw": t1["pv_mw"][slot],
                    "charge_mw": round(plan["charge_mw"][slot], 3),
                    "discharge_mw": round(plan["discharge_mw"][slot], 3),
                    "export_mw": round(export, 3),
                    "import_mw": round(import_mw, 3),
                    "curtail_mw": round(curtail, 3),
                    "spot_cash_cny": round(
                        (export - import_mw) * t1["rt_price"][slot] * pred_dt, 2
                    ),
                    "banned_slot": "yes" if t1["rt_price"][slot] < 0 else "",
                }
            )
        _write_csv(
            out_dir / "settlement.csv",
            settlement_rows,
            [
                "date",
                "slot",
                "start",
                "end",
                "da_price_cny_per_mwh",
                "rt_price_cny_per_mwh",
                "actual_wind_mw",
                "actual_pv_mw",
                "charge_mw",
                "discharge_mw",
                "export_mw",
                "import_mw",
                "curtail_mw",
                "spot_cash_cny",
                "banned_slot",
            ],
        )
        bridge_out = {
            "plan_profit": bridge["plan_profit"],
            "actual_profit": bridge["actual_profit"],
            "delta": bridge["delta"],
            "identity_gap": bridge["identity_gap"],
            "buckets": bridge["buckets"],
            "top_quantity_slots": bridge_top,
        }
        (out_dir / "bridge.json").write_text(
            json.dumps(bridge_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _write_csv(
            out_dir / "bridge.csv",
            bridge["buckets"],
            ["item", "category", "owner", "amount"],
        )

    plan = joint_bid["plan"]
    summary = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "predicates": {key: value for key, value in pred.items() if key != "scenario_weights"},
        "selected_strategy": selected_name,
        "selected": {
            "label": selected["strategy"]["label"],
            "declared_quantity_quantile": selected["strategy"]["declared_quantity_quantile"],
            "declared_energy_mwh": joint_bid["declared_energy_mwh"],
            "expected_net_margin_cny": selected["expected_net_margin_cny"],
            "cvar_cny": selected["cvar_cny"],
            "expected_curtail_mwh": selected["expected_curtail_mwh"],
            "expected_deviation_penalty_cny": selected["expected_deviation_penalty_cny"],
            "expected_ban_violation_slots": selected["expected_ban_violation_slots"],
            "plan_cycles": plan["cycles"],
            "plan_throughput_mwh": plan["throughput_mwh"],
            "plan_charge_mwh": plan["charge_mwh"],
            "plan_discharge_mwh": plan["discharge_mwh"],
            "plan_lagrange_multiplier": plan.get("lagrange_multiplier", 0.0),
            "plan_min_run_violations": plan.get("min_run_violations", 0),
            "plan_min_run_repairs": plan.get("min_run_repairs", 0),
            "discharge_breakeven_cny_per_mwh": joint_bid["discharge_breakeven_cny_per_mwh"],
            "charge_breakeven_cny_per_mwh": joint_bid["charge_breakeven_cny_per_mwh"],
            "scenarios": selected["outcomes"],
        },
        "strategies": [
            {
                "name": item["name"],
                "label": item["strategy"]["label"],
                "compliant": bool(item["strategy"].get("compliant")),
                "expected_net_margin_cny": item["expected_net_margin_cny"],
                "cvar_cny": item["cvar_cny"],
                "plan_cycles": item["plan_cycles"],
            }
            for item in results
        ],
        "joint_vs_separate": {
            "adder0": separate_zero["expected"],
            "adder180": separate_adder["expected"],
            "rows": separate_zero["rows"],
        },
        "actual": actual,
        "bridge": None
        if bridge is None
        else {
            "plan_profit": bridge["plan_profit"],
            "actual_profit": bridge["actual_profit"],
            "delta": bridge["delta"],
            "identity_gap": bridge["identity_gap"],
        },
        "sensitivity": sensitivity,
        "thresholds": thresholds,
        "warnings": report["warnings"],
        "files": {
            "bid_sheet": "bid_sheet.csv",
            "strategies": "strategies.csv",
            "scenarios": "scenarios.csv",
            "joint_vs_separate": "joint_vs_separate.csv",
            "settlement": "settlement.csv" if t1 is not None else None,
            "bridge": "bridge.json" if bridge is not None else None,
            "review": "review.md",
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(
        out_dir / "review.md",
        config,
        report,
        d1,
        results,
        selected_name,
        selected,
        actual,
        bridge,
        bridge_top,
        separate_zero,
        separate_adder,
        sensitivity,
        thresholds,
        fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "results": results,
        "selected": selected,
        "actual": actual,
        "bridge": bridge,
        "separate_zero": separate_zero,
        "separate_adder": separate_adder,
        "sensitivity": sensitivity,
        "thresholds": thresholds,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mengxi wind+PV+storage joint-declaration instance pack")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", help="D-1 288-point wind/PV/price scenario CSV")
    parser.add_argument("--t1", help="T+1 actual CSV; omit to skip settlement and bridge")
    parser.add_argument("--out", default=str(HERE / "out"))
    parser.add_argument("--demo", action="store_true", help="use the bundled synthetic demo data (default when no --d1/--t1 is given)")
    parser.add_argument("--check-config", action="store_true", help="validate and print provenance")
    args = parser.parse_args(argv)
    if not args.demo and args.d1 is None and args.t1 is None:
        args.demo = True

    try:
        config = json.loads(Path(args.instance).read_text(encoding="utf-8"))
        report = validate_instance(config)
    except (OSError, json.JSONDecodeError, ConfigError) as exc:
        print(f"配置校验失败：{exc}", file=sys.stderr)
        return 1

    if args.check_config:
        print(f"配置校验通过：{config['meta']['instance_id']}")
        for item in report["provenance"]:
            print(f"  {item['block']:<34} {item['grade']:<5} {item['source']}")
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
        if not args.t1:
            print("必须提供 --t1：T+1 全电量实时结算重放是本包的必算环节；演示口径请用 --demo", file=sys.stderr)
            return 1
        d1_path = Path(args.d1)
        t1_path = Path(args.t1)
        out_dir = Path(args.out)

    try:
        result = run_instance(args.instance, d1_path, t1_path, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    selected = summary["selected"]
    print(f"实例：{summary['instance_id']} / 交易日 {summary['trading_day']}（288 点 / 5 分钟）")
    print(
        f"选中：{selected['label']}；风光联合申报 {selected['declared_energy_mwh']:,.1f} MWh，"
        f"期望净收益 {selected['expected_net_margin_cny']:,.2f} 元，CVaR(80%) {selected['cvar_cny']:,.2f} 元"
    )
    print(
        f"储能计划：充电 {selected['plan_charge_mwh']:,.1f} MWh / 放电 {selected['plan_discharge_mwh']:,.1f} MWh，"
        f"循环 {selected['plan_cycles']:.2f} 次（上限 1.5，拉格朗日乘子 {selected['plan_lagrange_multiplier']:.2f}），"
        f"最小连续违规 {selected['plan_min_run_violations']} 段"
    )
    sep0 = summary["joint_vs_separate"]["adder0"]
    sep180 = summary["joint_vs_separate"]["adder180"]
    print(
        f"联合 vs 分开：加成 0 期望差额 {sep0['gain_cny']:+,.2f} 元；"
        f"加成 180 期望差额 {sep180['gain_cny']:+,.2f} 元"
    )
    if result["actual"] is not None:
        actual = result["actual"]
        bridge = result["bridge"]
        print(
            f"实际：风光可用 {actual['available_mwh']:,.1f} MWh，上网 {actual['export_mwh']:,.1f} MWh，"
            f"弃电 {actual['curtail_mwh']:,.1f} MWh，禁放违规 {actual['ban_violation_slots']} 时段，"
            f"净收益 {actual['net_margin_cny']:,.2f} 元"
        )
        print(
            f"差异桥：计划 {bridge['plan_profit']:,.2f} → 实际 {bridge['actual_profit']:,.2f}，"
            f"差异 {bridge['delta']:+,.2f} 元，残差 {bridge['identity_gap']:.2e}"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
