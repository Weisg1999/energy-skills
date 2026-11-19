#!/usr/bin/env python3
"""Shandong noon negative-price day: "full-output declaration" strategy failure replay.

This is the repo's first *strategy-failure / boundary* instance pack. It does not
teach the right answer first; it quantifies:

1. how much the wrong decision (declaring full available output on a deep
   negative-price noon) loses, slot by slot, against two better postures;
2. where the boundary sits: a grid scan over "noon price floor x curtailment
   ratio" finds the break-even between full output (A) and curtailment (B).

Three strategies are replayed on the same D-1 declaration basis:

* A ``full_output`` — declare full available output, no negative-price plan
  (the wrong baseline, mirroring 合成案例复盘库 案例 1);
* B ``curtail_negative`` — declare (1-ratio) of available output in the
  forecast negative-price window;
* C ``curtail_plus_storage`` — same as B, but the curtailed energy charges a
  small co-located battery (charged from the plant's own PV, never from the
  grid) and is discharged into the evening peak.

Revenue components per slot: energy at the clearing price (negative price
means selling power *costs* money), mechanism-price CFD (grade-D assumption:
proportional coverage, reference price = same-slot clearing price), an
ancillary-service levy placeholder, and a capacity-compensation item that is
settled separately (分账) and therefore identical across strategies — it never
enters any strategy delta.

Rule facts come from knowledge/山东电力市场-2026-11.md with grade tags; plant,
prices, volumes and decision parameters are grade-D synthetic data. Outputs
are deterministic and written to ``out/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parents[1]
sys.path.insert(0, str(SKILL_DIR / "tools"))

from contracts import capture_price  # noqa: E402

GRADES = {"A", "B", "C", "D", "A/B", "B/C", "C/D", "B/C/D"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
STRATEGY_KEYS = ("full_output", "curtail_negative", "curtail_plus_storage")
STRATEGY_LABELS = {
    "full_output": "A 满发申报（错误基线）",
    "curtail_negative": "B 负价时段压出力",
    "curtail_plus_storage": "C 压出力 + 储能配合",
}
REQUIRED_PRICE_FIELDS = ("slot", "start", "end", "pv_available_mw")
REQUIRED_DECL_FIELDS = ("slot", "start", "end", "declare_a_full_mw", "declare_b_curtail_mw")
TOL = 1e-6


class ConfigError(ValueError):
    """Raised when the instance or an input file fails validation."""


def _need(block, key, path):
    if not isinstance(block, dict) or key not in block:
        raise ConfigError(f"{path} 缺少 {key}")
    return block[key]


def _text(block, key, path):
    value = _need(block, key, path)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}.{key} 必须是非空字符串")
    return value.strip()


def _number(value, path, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} 必须是数字")
    if not math.isfinite(value):
        raise ConfigError(f"{path} 必须是有限数字")
    if low is not None and value < low - 1e-12:
        raise ConfigError(f"{path} 必须 >= {low}")
    if high is not None and value > high + 1e-12:
        raise ConfigError(f"{path} 必须 <= {high}")
    return float(value)


def _grade(block, path):
    grade = _text(block, "grade", path)
    if grade not in GRADES:
        raise ConfigError(f"{path}.grade {grade!r} 不是已知级别")
    return grade


def _graded_block(container, name, parent, report):
    block = _need(container, name, parent)
    if not isinstance(block, dict):
        raise ConfigError(f"{parent}.{name} 必须是对象")
    grade = _grade(block, f"{parent}.{name}")
    source = _text(block, "source", f"{parent}.{name}")
    report.append({"block": f"{parent}.{name}", "grade": grade, "source": source})
    return block


def load_config(path):
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"instance 文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"instance 不是合法 JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError("instance 必须是 JSON 对象")

    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "market", "entity_type", "rule_version", "data_cutoff", "grade", "scope", "currency", "units", "disclaimer"):
        _text(meta, key, "meta")
    _grade(meta, "meta")
    if not DATE_RE.match(meta["data_cutoff"]):
        raise ConfigError("meta.data_cutoff 必须是 YYYY-MM-DD")

    rules = _need(config, "rules", "instance")
    report = []
    spot = _graded_block(rules, "spot", "rules", report)
    negative = _graded_block(rules, "negative_price", "rules", report)
    capacity = _graded_block(rules, "capacity_compensation", "rules", report)
    new_energy = _graded_block(rules, "new_energy", "rules", report)

    declare_floor = _number(_need(spot, "declare_floor_cny_per_mwh", "rules.spot"), "rules.spot.declare_floor_cny_per_mwh")
    declare_cap = _number(_need(spot, "declare_cap_cny_per_mwh", "rules.spot"), "rules.spot.declare_cap_cny_per_mwh", 0.0)
    clear_floor = _number(_need(spot, "clear_floor_cny_per_mwh", "rules.spot"), "rules.spot.clear_floor_cny_per_mwh")
    clear_cap = _number(_need(spot, "clear_cap_cny_per_mwh", "rules.spot"), "rules.spot.clear_cap_cny_per_mwh", 0.0)
    if declare_floor >= 0:
        raise ConfigError("山东现货申报下限必须是负值（−80 元/MWh），下限写成 0 或正数是山东页最高频错误")
    if clear_floor > declare_floor + 1e-12:
        raise ConfigError("出清下限必须不高于申报下限")
    if declare_cap <= 0 or clear_cap < declare_cap - 1e-12:
        raise ConfigError("申报/出清上限必须为正且出清上限不低于申报上限")
    if not DATE_RE.match(_text(spot, "formal_operation_date", "rules.spot")):
        raise ConfigError("rules.spot.formal_operation_date 必须是 YYYY-MM-DD")
    if _number(_need(spot, "realtime_clearing_interval_min", "rules.spot"), "rules.spot.realtime_clearing_interval_min", 0.0) <= 0:
        raise ConfigError("rules.spot.realtime_clearing_interval_min 必须为正")
    draft = spot.get("draft_2026_08_28")
    if draft is not None and not isinstance(draft, dict):
        raise ConfigError("rules.spot.draft_2026_08_28 必须是对象")

    if _number(_need(negative, "negative_hours_2025_gt", "rules.negative_price"), "rules.negative_price.negative_hours_2025_gt", 0.0) <= 0:
        raise ConfigError("rules.negative_price.negative_hours_2025_gt 必须为正")
    share = _number(_need(negative, "floor_share_2025_pct", "rules.negative_price"), "rules.negative_price.floor_share_2025_pct", 0.0, 100.0)
    if share <= 0:
        raise ConfigError("rules.negative_price.floor_share_2025_pct 必须为正")
    _text(negative, "deep_valley_window", "rules.negative_price")

    _text(capacity, "formula", "rules.capacity_compensation")
    _text(capacity, "settlement_separation", "rules.capacity_compensation")
    if "待核实" not in _text(capacity, "standard_value", "rules.capacity_compensation"):
        raise ConfigError("rules.capacity_compensation.standard_value 必须标注待核实（具体标准数值未核到省级原文）")

    participation = _need(new_energy, "full_market_participation", "rules.new_energy")
    if participation is not True:
        raise ConfigError("rules.new_energy.full_market_participation 必须为 true（新能源全量入市）")
    mech_price_kwh = _number(_need(new_energy, "mechanism_price_pv_2026_cny_per_kwh", "rules.new_energy"), "rules.new_energy.mechanism_price_pv_2026_cny_per_kwh", 0.0, declare_cap / 1000.0)
    if mech_price_kwh <= 0:
        raise ConfigError("机制电价必须为正")
    _text(new_energy, "mechanism_settlement", "rules.new_energy")

    asset = _graded_block(config, "asset", "instance", report)
    cap_mw = _number(_need(asset, "capacity_mw", "asset"), "asset.capacity_mw", 0.0)
    if cap_mw <= 0:
        raise ConfigError("asset.capacity_mw 必须为正")
    if not DATE_RE.match(_text(asset, "replay_date", "asset")):
        raise ConfigError("asset.replay_date 必须是 YYYY-MM-DD")
    gamma = _number(_need(asset, "mechanism_quota_share", "asset"), "asset.mechanism_quota_share", 0.0, 1.0)

    strategy = _graded_block(config, "strategy", "instance", report)
    profile_id = _text(strategy, "profile_id", "strategy")
    strategy_a = _need(strategy, "strategy_a", "strategy")
    if _text(strategy_a, "type", "strategy.strategy_a") != "full_output":
        raise ConfigError("strategy.strategy_a.type 必须是 full_output（满发申报是错误基线）")
    strategy_b = _need(strategy, "strategy_b", "strategy")
    if _text(strategy_b, "type", "strategy.strategy_b") != "curtail_negative":
        raise ConfigError("strategy.strategy_b.type 必须是 curtail_negative")
    curtail_ratio = _number(_need(strategy_b, "curtail_ratio", "strategy.strategy_b"), "strategy.strategy_b.curtail_ratio", 0.0, 1.0)
    trigger = _number(_need(strategy_b, "trigger_price_cny_per_mwh", "strategy.strategy_b"), "strategy.strategy_b.trigger_price_cny_per_mwh")
    strategy_c = _need(strategy, "strategy_c", "strategy")
    if _text(strategy_c, "type", "strategy.strategy_c") != "curtail_plus_storage":
        raise ConfigError("strategy.strategy_c.type 必须是 curtail_plus_storage")
    storage = _need(strategy_c, "storage", "strategy.strategy_c")
    storage_power = _number(_need(storage, "power_mw", "strategy.strategy_c.storage"), "storage.power_mw", 0.0, cap_mw)
    storage_energy = _number(_need(storage, "energy_mwh", "strategy.strategy_c.storage"), "storage.energy_mwh", 0.0)
    storage_eff = _number(_need(storage, "round_trip_efficiency", "strategy.strategy_c.storage"), "storage.round_trip_efficiency", 0.0, 1.0)
    discharge_trigger = _number(_need(storage, "discharge_trigger_price_cny_per_mwh", "strategy.strategy_c.storage"), "storage.discharge_trigger_price_cny_per_mwh", 0.0)
    if storage_power <= 0 or storage_energy <= 0 or storage_eff <= 0:
        raise ConfigError("储能功率、容量与效率必须为正")
    _text(storage, "charge_source", "strategy.strategy_c.storage")
    _text(strategy, "decision_rule", "strategy")

    assumptions = _graded_block(config, "assumptions", "instance", report)
    cap_assum = _need(assumptions, "capacity_compensation", "assumptions")
    effective_capacity = _number(_need(cap_assum, "effective_capacity_mw", "assumptions.capacity_compensation"), "assumptions.capacity_compensation.effective_capacity_mw", 0.0)
    standard = _number(_need(cap_assum, "standard_cny_per_kw_year", "assumptions.capacity_compensation"), "assumptions.capacity_compensation.standard_cny_per_kw_year", 0.0)
    factor = _number(_need(cap_assum, "supply_demand_factor", "assumptions.capacity_compensation"), "assumptions.capacity_compensation.supply_demand_factor", 0.0)
    if effective_capacity <= 0 or standard <= 0 or factor <= 0:
        raise ConfigError("容量补偿占位参数必须为正")
    if "待核实" not in _text(cap_assum, "note", "assumptions.capacity_compensation"):
        raise ConfigError("assumptions.capacity_compensation.note 必须标注待核实")
    levy = _number(_need(assumptions, "ancillary_levy_cny_per_mwh", "assumptions"), "assumptions.ancillary_levy_cny_per_mwh", 0.0)
    _text(assumptions, "mechanism_reference", "assumptions")
    _text(assumptions, "mechanism_coverage", "assumptions")

    scan = _graded_block(config, "scan", "instance", report)
    window = _need(scan, "window_slots", "scan")
    if not isinstance(window, list) or not window:
        raise ConfigError("scan.window_slots 必须是非空列表")
    window = [int(x) for x in window]
    if any(t < 0 or t > 23 for t in window) or window != sorted(set(window)):
        raise ConfigError("scan.window_slots 必须是 0-23 内升序且不重复的时段")
    floors_raw = _need(scan, "floor_prices_cny_per_mwh", "scan")
    if not isinstance(floors_raw, list) or not floors_raw:
        raise ConfigError("scan.floor_prices_cny_per_mwh 必须是非空列表")
    floors = [_number(x, f"scan.floor_prices_cny_per_mwh[{i}]", clear_floor, clear_cap) for i, x in enumerate(floors_raw)]
    ratios_raw = _need(scan, "curtail_ratios", "scan")
    if not isinstance(ratios_raw, list) or not ratios_raw:
        raise ConfigError("scan.curtail_ratios 必须是非空列表")
    ratios = [_number(x, f"scan.curtail_ratios[{i}]", 0.0, 1.0) for i, x in enumerate(ratios_raw)]

    contract = _need(config, "data_contract", "instance")
    price_contract = _need(contract, "price_profile", "data_contract")
    _text(price_contract, "file", "data_contract.price_profile")
    price_fields = _need(price_contract, "fields", "data_contract.price_profile")
    if not isinstance(price_fields, list) or not set(REQUIRED_PRICE_FIELDS).issubset(set(price_fields)):
        raise ConfigError("data_contract.price_profile.fields 必须包含 slot/start/end/pv_available_mw")
    scenario_fields = _need(price_contract, "scenario_fields", "data_contract.price_profile")
    if not isinstance(scenario_fields, list) or not scenario_fields:
        raise ConfigError("data_contract.price_profile.scenario_fields 必须是非空列表")
    base_scenario = _text(price_contract, "base_scenario", "data_contract.price_profile")
    if base_scenario not in scenario_fields:
        raise ConfigError("data_contract.price_profile.base_scenario 必须是 scenario_fields 之一")
    decl_contract = _need(contract, "declaration_curves", "data_contract")
    _text(decl_contract, "file", "data_contract.declaration_curves")
    decl_fields = _need(decl_contract, "fields", "data_contract.declaration_curves")
    if not isinstance(decl_fields, list) or not set(REQUIRED_DECL_FIELDS).issubset(set(decl_fields)):
        raise ConfigError("data_contract.declaration_curves.fields 必须包含 slot/start/end/declare_a_full_mw/declare_b_curtail_mw")

    cap_comp_daily = effective_capacity * 1000.0 * standard * factor / 365.0
    return {
        "config": config,
        "report": report,
        "meta": meta,
        "spot": spot,
        "negative": negative,
        "capacity": capacity,
        "new_energy": new_energy,
        "asset": asset,
        "strategy": strategy,
        "assumptions": assumptions,
        "scan": scan,
        "profile": price_contract,
        "decl": decl_contract,
        "values": {
            "capacity_mw": cap_mw,
            "replay_date": asset["replay_date"],
            "gamma": gamma,
            "mech_price_cny_per_mwh": mech_price_kwh * 1000.0,
            "levy_cny_per_mwh": levy,
            "curtail_ratio": curtail_ratio,
            "trigger_price_cny_per_mwh": trigger,
            "storage": {
                "power_mw": storage_power,
                "energy_mwh": storage_energy,
                "round_trip_efficiency": storage_eff,
                "discharge_trigger_price_cny_per_mwh": discharge_trigger,
            },
            "cap_comp_daily_cny": cap_comp_daily,
            "profile_id": profile_id,
            "declare_floor": declare_floor,
            "declare_cap": declare_cap,
            "clear_floor": clear_floor,
            "clear_cap": clear_cap,
            "window_slots": window,
            "floor_prices": floors,
            "curtail_ratios": ratios,
            "base_scenario": base_scenario,
        },
    }


def _read_csv_rows(path, required):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = reader.fieldnames or []
    except FileNotFoundError as exc:
        raise ConfigError(f"数据文件不存在: {path}") from exc
    except csv.Error as exc:
        raise ConfigError(f"CSV 解析失败: {path}: {exc}") from exc
    for field in required:
        if field not in fields:
            raise ConfigError(f"{path.name} 缺少字段 {field}")
    return rows, fields


def load_price_profile(path, bundle):
    values = bundle["values"]
    price_contract = bundle["profile"]
    scenario_fields = price_contract["scenario_fields"]
    required = list(REQUIRED_PRICE_FIELDS) + list(scenario_fields)
    rows, _ = _read_csv_rows(path, required)
    if len(rows) != 24:
        raise ConfigError(f"price_profile 必须包含 24 个小时时段，实际 {len(rows)} 行")

    slots, starts, ends, avail = [], [], [], []
    scenarios = {field: [] for field in scenario_fields}
    for index, row in enumerate(rows, start=2):
        slot_raw = (row.get("slot") or "").strip()
        if not slot_raw or not slot_raw.lstrip("-").isdigit():
            raise ConfigError(f"price_profile 第 {index} 行 slot 不是整数")
        slot = int(slot_raw)
        if slot != index - 2:
            raise ConfigError(f"price_profile 第 {index} 行 slot 必须按 0..23 升序排列")
        start = (row.get("start") or "").strip()
        end = (row.get("end") or "").strip()
        if not HHMM_RE.match(start) or not HHMM_RE.match(end):
            raise ConfigError(f"price_profile 第 {index} 行 start/end 必须是 HH:MM")
        if int(start[:2]) != slot or start[3:] != "00":
            raise ConfigError(f"price_profile 第 {index} 行 start 必须与 slot 对齐（整点）")
        expect_end = f"{(slot + 1) % 24:02d}:00"
        if end != expect_end:
            raise ConfigError(f"price_profile 第 {index} 行 end 必须是 {expect_end}")
        mw = _number(float(row["pv_available_mw"]), f"price_profile 第 {index} 行 pv_available_mw", 0.0, values["capacity_mw"])
        slots.append(slot)
        starts.append(start)
        ends.append(end)
        avail.append(mw)
        for field in scenario_fields:
            price = _number(float(row[field]), f"price_profile 第 {index} 行 {field}", values["clear_floor"], values["clear_cap"])
            scenarios[field].append(price)

    warnings = []
    if avail[11:15] == [0.0, 0.0, 0.0, 0.0]:
        warnings.append("午间时段可用出力为 0，负价复盘不成立，请核对资源曲线")
    return {
        "slots": slots,
        "starts": starts,
        "ends": ends,
        "avail": avail,
        "scenarios": scenarios,
        "daily_energy_mwh": sum(avail),
        "warnings": warnings,
    }


def load_declarations(path, profile, bundle):
    values = bundle["values"]
    rows, _ = _read_csv_rows(path, list(REQUIRED_DECL_FIELDS))
    if len(rows) != 24:
        raise ConfigError(f"declaration_curves 必须包含 24 个小时时段，实际 {len(rows)} 行")

    decl_a, decl_b = [], []
    for index, row in enumerate(rows, start=2):
        slot_raw = (row.get("slot") or "").strip()
        if not slot_raw or not slot_raw.lstrip("-").isdigit() or int(slot_raw) != index - 2:
            raise ConfigError(f"declaration_curves 第 {index} 行 slot 必须按 0..23 升序排列")
        available = profile["avail"][index - 2]
        a_mw = _number(float(row["declare_a_full_mw"]), f"declaration_curves 第 {index} 行 declare_a_full_mw", 0.0, available + 1e-6)
        b_mw = _number(float(row["declare_b_curtail_mw"]), f"declaration_curves 第 {index} 行 declare_b_curtail_mw", 0.0, available + 1e-6)
        decl_a.append(a_mw)
        decl_b.append(b_mw)

    warnings = []
    if any(a < v - 1e-6 for a, v in zip(decl_a, profile["avail"])):
        warnings.append("策略 A 的申报曲线低于可用出力：满发申报（错误基线）的定义被削弱，请核对申报曲线")
    implied_window = [t for t in range(24) if decl_b[t] < profile["avail"][t] - 1e-6]
    forecast_window = [t for t in range(24) if profile["scenarios"][bundle["values"]["base_scenario"]][t] < values["trigger_price_cny_per_mwh"]]
    if implied_window != forecast_window:
        warnings.append(
            f"策略 B 的压出力时段 {implied_window} 与基准情景中价格低于触发线的时段 {forecast_window} 不一致，请核对申报曲线与触发线"
        )
    return {"decl_a": decl_a, "decl_b": decl_b, "warnings": warnings}


def storage_dispatch(prices, avail, decl_b, storage, charge_trigger):
    power = storage["power_mw"]
    energy_cap = storage["energy_mwh"]
    efficiency = storage["round_trip_efficiency"]
    discharge_trigger = storage["discharge_trigger_price_cny_per_mwh"]

    charge = [0.0] * 24
    stored = 0.0
    charge_order = sorted((t for t in range(24) if prices[t] < charge_trigger), key=lambda t: (prices[t], t))
    for t in charge_order:
        pool = max(avail[t] - decl_b[t], 0.0)
        volume = min(power, energy_cap - stored, pool)
        if volume > 1e-9:
            charge[t] = volume
            stored += volume

    dischargeable = stored * efficiency
    discharge = [0.0] * 24
    discharged = 0.0
    discharge_order = sorted((t for t in range(24) if prices[t] >= discharge_trigger), key=lambda t: (-prices[t], t))
    for t in discharge_order:
        volume = min(power, dischargeable - discharged)
        if volume > 1e-9:
            discharge[t] = volume
            discharged += volume
    return charge, discharge, stored, discharged


def replay_day(prices, avail, decl_a, decl_b, values):
    gamma = values["gamma"]
    mech = values["mech_price_cny_per_mwh"]
    levy = values["levy_cny_per_mwh"]
    trigger = values["trigger_price_cny_per_mwh"]
    storage = values["storage"]
    charge, discharge, stored, discharged = storage_dispatch(prices, avail, decl_b, storage, trigger)

    margins = [(1.0 - gamma) * p + gamma * mech - levy for p in prices]
    rows = []
    for t in range(24):
        price = prices[t]
        q_a = decl_a[t]
        q_b = decl_b[t]
        a_energy = q_a * price
        b_energy = q_b * price
        c_energy = q_b * price + discharge[t] * price
        a_mech = gamma * q_a * (mech - price)
        b_mech = gamma * q_b * (mech - price)
        c_mech = b_mech
        a_levy = levy * q_a
        b_levy = levy * q_b
        c_levy = levy * (q_b + discharge[t])
        rows.append(
            {
                "slot": t,
                "price_cny_per_mwh": price,
                "available_mw": avail[t],
                "margin_cny_per_mwh": margins[t],
                "declare_a_mw": q_a,
                "declare_b_mw": q_b,
                "c_charge_mwh": charge[t],
                "c_discharge_mwh": discharge[t],
                "a_energy_cny": a_energy,
                "b_energy_cny": b_energy,
                "c_energy_cny": c_energy,
                "a_mech_cny": a_mech,
                "b_mech_cny": b_mech,
                "c_mech_cny": c_mech,
                "a_levy_cny": a_levy,
                "b_levy_cny": b_levy,
                "c_levy_cny": c_levy,
                "a_subtotal_cny": a_energy + a_mech - a_levy,
                "b_subtotal_cny": b_energy + b_mech - b_levy,
                "c_subtotal_cny": c_energy + c_mech - c_levy,
                "b_minus_a_cny": (b_energy + b_mech - b_levy) - (a_energy + a_mech - a_levy),
                "c_minus_a_cny": (c_energy + c_mech - c_levy) - (a_energy + a_mech - a_levy),
            }
        )

    totals = {
        key: sum(row[key] for row in rows)
        for key in (
            "a_energy_cny",
            "b_energy_cny",
            "c_energy_cny",
            "a_mech_cny",
            "b_mech_cny",
            "c_mech_cny",
            "a_levy_cny",
            "b_levy_cny",
            "c_levy_cny",
            "a_subtotal_cny",
            "b_subtotal_cny",
            "c_subtotal_cny",
        )
    }
    totals["charged_mwh"] = stored
    totals["discharged_mwh"] = discharged
    totals["discharge_revenue_cny"] = sum(discharge[t] * prices[t] for t in range(24))
    totals["storage_net_cny"] = totals["c_subtotal_cny"] - totals["b_subtotal_cny"]
    return {"rows": rows, "margins": margins, "totals": totals}


def strategy_summary(replay, values):
    cap_comp = values["cap_comp_daily_cny"]
    subtotals = {
        "full_output": replay["totals"]["a_subtotal_cny"],
        "curtail_negative": replay["totals"]["b_subtotal_cny"],
        "curtail_plus_storage": replay["totals"]["c_subtotal_cny"],
    }
    strategies = []
    for key in STRATEGY_KEYS:
        total = subtotals[key] + cap_comp
        strategies.append(
            {
                "strategy": key,
                "label": STRATEGY_LABELS[key],
                "subtotal_excl_cap_cny": subtotals[key],
                "capacity_compensation_cny": cap_comp,
                "total_cny": total,
            }
        )
    best = max(strategies, key=lambda row: row["total_cny"])
    for row in strategies:
        row["delta_vs_a_cny"] = row["total_cny"] - strategies[0]["total_cny"]
        row["delta_vs_best_cny"] = row["total_cny"] - best["total_cny"]
    return {"strategies": strategies, "best": best}


def analytical_threshold(values):
    gamma = values["gamma"]
    if gamma >= 1.0 - 1e-12:
        return None
    return (values["levy_cny_per_mwh"] - gamma * values["mech_price_cny_per_mwh"]) / (1.0 - gamma)


def run_scan(profile, values):
    window = values["window_slots"]
    gamma = values["gamma"]
    mech = values["mech_price_cny_per_mwh"]
    levy = values["levy_cny_per_mwh"]
    trigger = values["trigger_price_cny_per_mwh"]
    base = profile["scenarios"][values["base_scenario"]]
    avail = profile["avail"]

    rows = []
    for floor in values["floor_prices"]:
        prices = list(base)
        for t in window:
            prices[t] = floor
        margins = [(1.0 - gamma) * p + gamma * mech - levy for p in prices]
        a_total = sum(avail[t] * margins[t] for t in range(24))
        window_a_mwh = sum(avail[t] for t in window)
        for ratio in values["curtail_ratios"]:
            decl_b = list(avail)
            if floor < trigger:
                for t in window:
                    decl_b[t] = avail[t] * (1.0 - ratio)
            b_total = sum(decl_b[t] * margins[t] for t in range(24))
            delta = b_total - a_total
            if abs(delta) < 1e-6:
                winner = "平"
            elif delta > 0:
                winner = "B"
            else:
                winner = "A"
            rows.append(
                {
                    "floor_price_cny_per_mwh": floor,
                    "curtail_ratio": ratio,
                    "window_energy_a_mwh": window_a_mwh,
                    "window_energy_b_mwh": sum(decl_b[t] for t in window),
                    "a_revenue_excl_cap_cny": a_total,
                    "b_revenue_excl_cap_cny": b_total,
                    "b_minus_a_cny": delta,
                    "winner": winner,
                }
            )
    return rows


def scan_first_win_ratios(scan_rows, values):
    """对每个下限价，找出 B 首次占优的压出力比例。"""
    by_floor = {}
    for row in scan_rows:
        by_floor.setdefault(row["floor_price_cny_per_mwh"], []).append(row)
    result = {}
    for floor, rows in by_floor.items():
        wins = [row["curtail_ratio"] for row in rows if row["b_minus_a_cny"] > 1e-6]
        result[floor] = min(wins) if wins else None
    return result


def _fmt_wan(value):
    return f"{value / 1e4:,.2f}"


def _fmt_cny(value):
    return f"{value:,.2f}"


def _fmt_price(value):
    return f"{value:,.2f}"


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: ("" if row.get(field) is None else row.get(field, "")) for field in fields})


def build_outputs(bundle, profile, declarations, out_dir):
    values = bundle["values"]
    base_field = values["base_scenario"]
    base_prices = profile["scenarios"][base_field]
    decl_a = declarations["decl_a"]
    decl_b = declarations["decl_b"]

    base_replay = replay_day(base_prices, profile["avail"], decl_a, decl_b, values)
    summary_of_strategies = strategy_summary(base_replay, values)
    threshold = analytical_threshold(values)
    scan_rows = run_scan(profile, values)
    first_wins = scan_first_win_ratios(scan_rows, values)

    warnings = []
    warnings.extend(profile["warnings"])
    warnings.extend(declarations["warnings"])
    if any(p <= values["declare_floor"] + 1e-9 for p in base_prices):
        warnings.append("基准日午间时段触及申报下限 −80 元/MWh：满发时段存在卖电即亏的深谷")
    if threshold is not None and threshold < values["clear_floor"]:
        warnings.append("解析门槛价低于出清下限：在现行限价内满发恒为优，压出力无意义")
    if threshold is not None and threshold > 0:
        warnings.append("解析门槛价为正：辅助服务分摊超过机制差价保护，任何低价时段都应压出力，请先核实分摊口径")

    negative_window_energy_a = sum(
        base_replay["rows"][t]["a_energy_cny"]
        for t in range(24)
        if base_prices[t] < 0
    )
    window_slots = values["window_slots"]
    window_subtotal_a = sum(base_replay["rows"][t]["a_subtotal_cny"] for t in window_slots)
    attribution_rows = [dict(row) for row in base_replay["rows"]]
    max_b_minus_a = max(row["b_minus_a_cny"] for row in attribution_rows)
    for row in attribution_rows:
        if row["b_minus_a_cny"] > 1e-6 and abs(row["b_minus_a_cny"] - max_b_minus_a) < 1e-6:
            row["contribution_note"] = "满发决策最大损失时段（触地板价）"
        elif row["c_charge_mwh"] > 1e-9:
            row["contribution_note"] = "储能充电（压出力电量入储，不改变申报）"
        elif row["c_discharge_mwh"] > 1e-9:
            row["contribution_note"] = "储能放电（晚峰回收）"
        else:
            row["contribution_note"] = ""
    attribution_rows.append(
        {
            "slot": "合计",
            "start": "",
            "end": "",
            "price_cny_per_mwh": "",
            "available_mwh": sum(profile["avail"]),
            "b_minus_a_cny": sum(r["b_minus_a_cny"] for r in base_replay["rows"]),
            "c_minus_a_cny": sum(r["c_minus_a_cny"] for r in base_replay["rows"]),
            "contribution_note": "容量补偿分账不动：三条策略金额相同，不进入差额",
        }
    )

    scenarios = []
    scenario_labels = bundle["profile"].get("scenario_labels", [])
    for index, field in enumerate(bundle["profile"]["scenario_fields"]):
        prices = profile["scenarios"][field]
        replay = replay_day(prices, profile["avail"], decl_a, decl_b, values)
        strategies = strategy_summary(replay, values)
        best = strategies["best"]
        label = scenario_labels[index] if index < len(scenario_labels) else field
        scenarios.append(
            {
                "scenario": field,
                "label": label,
                "a_day_cny": strategies["strategies"][0]["total_cny"],
                "b_day_cny": strategies["strategies"][1]["total_cny"],
                "c_day_cny": strategies["strategies"][2]["total_cny"],
                "b_minus_a_cny": strategies["strategies"][1]["total_cny"] - strategies["strategies"][0]["total_cny"],
                "c_minus_a_cny": strategies["strategies"][2]["total_cny"] - strategies["strategies"][0]["total_cny"],
                "best_strategy": best["strategy"],
                "best_label": best["label"],
            }
        )

    capture_a = capture_price(base_prices, profile["avail"])
    time_weighted = sum(base_prices) / len(base_prices)
    a_total = summary_of_strategies["strategies"][0]["total_cny"]
    loss_vs_best = summary_of_strategies["best"]["total_cny"] - a_total

    flip_rows = [
        row for row in scan_rows
        if row["curtail_ratio"] == max(values["curtail_ratios"]) and abs(row["b_minus_a_cny"]) > 1e-6
    ]
    if flip_rows:
        losing_floors = [row["floor_price_cny_per_mwh"] for row in flip_rows if row["b_minus_a_cny"] < 0]
        winning_floors = [row["floor_price_cny_per_mwh"] for row in flip_rows if row["b_minus_a_cny"] > 0]
        if losing_floors and winning_floors:
            # 翻转带 = B 仍占优的最浅下限 与 A 仍占优的最深下限 之间（包住盈亏平衡点）
            flip_band = [max(winning_floors), min(losing_floors)]
        else:
            flip_band = None
    else:
        flip_band = None

    fingerprint = hashlib.sha1(
        json.dumps(bundle["strategy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]

    scan_conclusion = (
        f"D 级假设下（机制覆盖比例 {values['gamma']:.0%}、机制电价 {values['mech_price_cny_per_mwh']:.0f} 元/MWh、"
        f"辅助服务分摊 {values['levy_cny_per_mwh']:.0f} 元/MWh、按上网电量计），压出力在午间预期价 < "
        f"{threshold:.2f} 元/MWh 时占优"
        if threshold is not None
        else "机制电量全额覆盖时压出力与价格无关，先核实机制分摊口径"
    )

    summary = {
        "meta": bundle["meta"],
        "fingerprint": fingerprint,
        "config": {
            "profile_id": values["profile_id"],
            "capacity_mw": values["capacity_mw"],
            "replay_date": values["replay_date"],
            "mechanism_quota_share": values["gamma"],
            "mechanism_price_cny_per_mwh": values["mech_price_cny_per_mwh"],
            "curtail_ratio": values["curtail_ratio"],
            "trigger_price_cny_per_mwh": values["trigger_price_cny_per_mwh"],
            "storage": values["storage"],
            "ancillary_levy_cny_per_mwh": values["levy_cny_per_mwh"],
            "capacity_compensation_daily_cny": round(values["cap_comp_daily_cny"], 2),
            "base_scenario": base_field,
            "scan_window_slots": values["window_slots"],
        },
        "base_day": {
            "capture_price_a_cny_per_mwh": round(capture_a, 4),
            "time_weighted_avg_price_cny_per_mwh": round(time_weighted, 4),
            "capture_rate": round(capture_a / time_weighted, 4) if time_weighted else None,
            "daily_energy_mwh": round(profile["daily_energy_mwh"], 2),
            "negative_window_energy_a_cny": round(negative_window_energy_a, 2),
            "window_subtotal_a_cny": round(window_subtotal_a, 2),
            "strategies": [
                {
                    "strategy": row["strategy"],
                    "label": row["label"],
                    "subtotal_excl_cap_cny": round(row["subtotal_excl_cap_cny"], 2),
                    "capacity_compensation_cny": round(row["capacity_compensation_cny"], 2),
                    "total_cny": round(row["total_cny"], 2),
                    "delta_vs_a_cny": round(row["delta_vs_a_cny"], 2),
                    "delta_vs_best_cny": round(row["delta_vs_best_cny"], 2),
                }
                for row in summary_of_strategies["strategies"]
            ],
            "best_strategy": summary_of_strategies["best"]["strategy"],
            "loss_vs_best_cny": round(loss_vs_best, 2),
            "storage_charged_mwh": round(base_replay["totals"]["charged_mwh"], 2),
            "storage_discharged_mwh": round(base_replay["totals"]["discharged_mwh"], 2),
            "storage_net_cny": round(base_replay["totals"]["storage_net_cny"], 2),
        },
        "loss_attribution": {
            "b_minus_a_total_cny": round(sum(r["b_minus_a_cny"] for r in base_replay["rows"]), 2),
            "c_minus_a_total_cny": round(sum(r["c_minus_a_cny"] for r in base_replay["rows"]), 2),
            "largest_loss_slots": [
                row["slot"] for row in base_replay["rows"]
                if row["b_minus_a_cny"] > 1e-6 and abs(row["b_minus_a_cny"] - max_b_minus_a) < 1e-6
            ],
            "largest_loss_slot_cny": round(max_b_minus_a, 2),
        },
        "scenarios": scenarios,
        "boundary_scan": {
            "threshold_analytical_cny_per_mwh": round(threshold, 4) if threshold is not None else None,
            "threshold_formula": "p* = (辅助服务分摊 − 机制覆盖比例 × 机制价) ÷ (1 − 机制覆盖比例)",
            "flip_between_cny_per_mwh": flip_band,
            "flip_independent_of_curtail_ratio": True,
            "first_win_curtail_ratio_by_floor": {
                f"{floor:g}": (ratio if ratio is None else round(ratio, 2))
                for floor, ratio in first_wins.items()
            },
            "conclusion": scan_conclusion,
            "grid_rows": len(scan_rows),
        },
        "five_questions": build_five_questions(bundle, base_replay, profile, summary_of_strategies, attribution_rows[:-1], threshold, negative_window_energy_a, window_subtotal_a, capture_a, time_weighted),
        "warnings": warnings,
        "sources": bundle["report"],
        "disclaimer": bundle["meta"]["disclaimer"],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        out_dir / "settlement.csv",
        base_replay["rows"],
        [
            "slot", "start", "end", "price_cny_per_mwh", "available_mw", "margin_cny_per_mwh",
            "declare_a_mw", "declare_b_mw", "c_charge_mwh", "c_discharge_mwh",
            "a_energy_cny", "b_energy_cny", "c_energy_cny",
            "a_mech_cny", "b_mech_cny", "c_mech_cny",
            "a_levy_cny", "b_levy_cny", "c_levy_cny",
            "a_subtotal_cny", "b_subtotal_cny", "c_subtotal_cny",
            "b_minus_a_cny", "c_minus_a_cny",
        ],
    )
    write_csv(
        out_dir / "loss_attribution.csv",
        [
            {
                "slot": row["slot"],
                "start": profile["starts"][row["slot"]] if isinstance(row["slot"], int) else "",
                "end": profile["ends"][row["slot"]] if isinstance(row["slot"], int) else "",
                "price_cny_per_mwh": row.get("price_cny_per_mwh", ""),
                "available_mwh": row.get("available_mw", row.get("available_mwh", "")),
                "b_minus_a_cny": row["b_minus_a_cny"],
                "c_minus_a_cny": row["c_minus_a_cny"],
                "contribution_note": row.get("contribution_note", ""),
            }
            for row in attribution_rows
        ],
        ["slot", "start", "end", "price_cny_per_mwh", "available_mwh", "b_minus_a_cny", "c_minus_a_cny", "contribution_note"],
    )
    write_csv(
        out_dir / "boundary_scan.csv",
        scan_rows,
        [
            "floor_price_cny_per_mwh", "curtail_ratio", "window_energy_a_mwh", "window_energy_b_mwh",
            "a_revenue_excl_cap_cny", "b_revenue_excl_cap_cny", "b_minus_a_cny", "winner",
        ],
    )
    write_csv(
        out_dir / "scenarios.csv",
        scenarios,
        ["scenario", "label", "a_day_cny", "b_day_cny", "c_day_cny", "b_minus_a_cny", "c_minus_a_cny", "best_strategy", "best_label"],
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "review.md").write_text(
        render_review(bundle, profile, base_replay, base_prices, summary_of_strategies, attribution_rows[:-1], scenarios, scan_rows, first_wins, threshold, values, fingerprint, capture_a, time_weighted, negative_window_energy_a, window_subtotal_a),
        encoding="utf-8",
    )
    return summary


def build_five_questions(bundle, replay, profile, strategies, attribution_rows, threshold, negative_window_energy_a, window_subtotal_a, capture_a, time_weighted):
    values = bundle["values"]
    rows = replay["rows"]
    best = strategies["best"]
    a_total = strategies["strategies"][0]["total_cny"]
    loss = best["total_cny"] - a_total
    largest = [row["slot"] for row in rows if row["b_minus_a_cny"] > 1e-6 and abs(row["b_minus_a_cny"] - max(r["b_minus_a_cny"] for r in rows)) < 1e-6]
    largest_txt = "、".join(f"{s:02d}:00–{s + 1:02d}:00" for s in largest) if largest else "无"
    b_minus_a = sum(r["b_minus_a_cny"] for r in rows)
    floor_slots_share = (
        sum(r["b_minus_a_cny"] for r in rows if r["slot"] in largest) / b_minus_a * 100.0
        if abs(b_minus_a) > 1e-9
        else 0.0
    )
    q1 = (
        "申报与中标：合成重放中申报曲线即出清结果，无执行偏差；错误发生在 D-1 决策"
        "（晴天 + 低负荷假日组合下按 P50 满发申报、无负价预案），不在申报执行环节。"
    )
    q2 = (
        f"结算初核：全天电能量收入 {_fmt_cny(replay['totals']['a_energy_cny'])} 元，捕获价 "
        f"{capture_a:,.2f} 元/MWh，只有时段均价 {time_weighted:,.2f} 元/MWh 的 "
        f"{capture_a / time_weighted * 100:.1f}%；其中负价时段卖电收入为 {_fmt_cny(negative_window_energy_a)} 元，"
        f"午间扫描窗口含机制差价与分摊后的净额为 {_fmt_cny(window_subtotal_a)} 元——窗口本身净亏，"
        "这不是执行问题，是决策问题。"
    )
    q3 = (
        f"触发线：当日没有任何价格触发线。按本包 D 级参数，解析门槛为 {threshold:,.2f} 元/MWh"
        "（低于该价每多发 1 MWh 净亏）；应设「预期价 < 门槛 → 压出力至〔Y〕%」并写入异常处置预案、每季演练"
        "（SOP §4.1：触发线五要素缺一等于没设）。"
    )
    q4 = (
        f"归因：满发比最优策略（{best['label']}）少收 {_fmt_cny(loss)} 元，占满发当日净收入 "
        f"{loss / a_total * 100:.1f}%（D 级口径）；申报决策部分（相对 B）{_fmt_cny(b_minus_a)} 元中，"
        f"{largest_txt} 两个触地板时段贡献约 {floor_slots_share:.0f}%。归因落到「无负价预案」环节"
        "（盘前未查负价分布、未算停机账、无触发线），不允许以「行情极端」结案（SOP §5.1 第 4 问）。"
    )
    q5 = (
        "明日改动：① 盘前简报第 1 栏加入负价风险（节假日 + 大发 + 低负荷三信号即列入，模板 A）；"
        "② 用同一张账测算并冻结本台「负价动作门槛」（机制差价、辅助服务分摊与负价支出同表比较）；"
        "③ 负价时段申报曲线按价格分段，而不是全天满发或全天固定比例压出力；"
        "④ 核实机制电量在负价时段的履约口径与辅助服务分摊基数——两者直接移动门槛价（见待核实清单）。"
    )
    return [q1, q2, q3, q4, q5]


def render_review(bundle, profile, replay, base_prices, strategies, attribution_rows, scenarios, scan_rows, first_wins, threshold, values, fingerprint, capture_a, time_weighted, negative_window_energy_a, window_subtotal_a):
    meta = bundle["meta"]
    rows = replay["rows"]
    totals = replay["totals"]
    a_strategy = strategies["strategies"][0]
    b_strategy = strategies["strategies"][1]
    c_strategy = strategies["strategies"][2]
    best = strategies["best"]
    loss = best["total_cny"] - a_strategy["total_cny"]
    window = values["window_slots"]

    losing_floors = [r["floor_price_cny_per_mwh"] for r in scan_rows if r["b_minus_a_cny"] < -1e-6]
    winning_floors = [r["floor_price_cny_per_mwh"] for r in scan_rows if r["b_minus_a_cny"] > 1e-6]
    flip_txt = ""
    if threshold is not None and losing_floors and winning_floors:
        flip_txt = (
            f"D 级假设下压出力在午间预期价 < {threshold:,.2f} 元/MWh 时占优；网格翻转位于 "
            f"{max(winning_floors):g}（B 占优）与 {min(losing_floors):g}（A 占优）元/MWh 之间，"
            "与压出力比例无关（比例只放大金额）"
        )

    lines = [
        f"# {meta['province']}午间负价日 · 满发申报策略失败复盘",
        "",
        f"- 实例：`{meta['instance_id']}`（{meta['entity_type']}）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}；电站、价格、电量与决策参数全部为 D 级合成数据",
        "- 本包是 [`knowledge/合成案例复盘库-2026-11.md`](../../../../../../knowledge/合成案例复盘库-2026-11.md) 案例 1"
        "（负电价日·光伏聚合商满发申报）的可运行版：先看错误怎么发生，再量化损失与边界。",
        "",
        "## 1. 结论",
        "",
        f"复盘日（D 级合成，午间触地板 −80 元/MWh）三条策略的当日净收入（含容量补偿分账项）："
        f"A 满发 **{_fmt_wan(a_strategy['total_cny'])} 万元**、B 负价时段压出力 **{_fmt_wan(b_strategy['total_cny'])} 万元**、"
        f"C 压出力 + 储能 **{_fmt_wan(c_strategy['total_cny'])} 万元**。",
        f"满发申报比最优策略少收 **{_fmt_cny(loss)} 元（约 {_fmt_wan(loss)} 万元）**；"
        f"其中申报决策部分（相对 B）{_fmt_cny(b_strategy['total_cny'] - a_strategy['total_cny'])} 元，"
        f"储能配合部分（C−B）{_fmt_cny(c_strategy['total_cny'] - b_strategy['total_cny'])} 元。",
        f"负价时段卖电收入为 **{_fmt_cny(negative_window_energy_a)} 元**（为负），"
        f"午间窗口含机制差价与分摊后净额 {_fmt_cny(window_subtotal_a)} 元——满发时段窗口本身净亏。",
        f"边界扫描结论：{flip_txt if flip_txt else '见边界扫描表'}。",
        "容量补偿分账不动：三条策略的容量补偿金额相同，不进入任何差额；若光伏实际不适用容量补偿，该行清零，以上全部结论不变。",
        "",
        "## 2. 逐时段结算重放（基准情景 S1 深谷负价日）",
        "",
        "| 时段 | 出清价 | 可用/申报A | 申报B | 边际净额 | A 收入 | B 收入 | C 收入 | B−A |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["available_mw"] <= 0 and row["declare_a_mw"] <= 0:
            continue
        lines.append(
            f"| {row['slot']:02d}:00–{row['slot'] + 1:02d}:00 | {row['price_cny_per_mwh']:,.0f} | "
            f"{row['available_mw']:,.0f} / {row['declare_a_mw']:,.1f} | {row['declare_b_mw']:,.1f} | "
            f"{row['margin_cny_per_mwh']:+,.1f} | {_fmt_cny(row['a_subtotal_cny'])} | "
            f"{_fmt_cny(row['b_subtotal_cny'])} | {_fmt_cny(row['c_subtotal_cny'])} | "
            f"{row['b_minus_a_cny']:+,.2f} |"
        )
    lines.extend(
        [
            f"| **全天** | — | {sum(profile['avail']):,.0f} | {sum(r['declare_b_mw'] for r in rows):,.1f} | — | "
            f"{_fmt_cny(totals['a_subtotal_cny'])} | {_fmt_cny(totals['b_subtotal_cny'])} | {_fmt_cny(totals['c_subtotal_cny'])} | "
            f"{totals['b_subtotal_cny'] - totals['a_subtotal_cny']:+,.2f} |",
            "",
            f"注：收入 = 电能量（负价时段为负）+ 机制差价（D 级假设：按申报量 {values['gamma']:.0%} 同比例覆盖、参考价取该时段出清价）− 辅助服务分摊占位（{values['levy_cny_per_mwh']:.0f} 元/MWh × 上网电量）；不含容量补偿。",
            f"储能（{values['storage']['power_mw']:.0f} MW / {values['storage']['energy_mwh']:.0f} MWh，效率 {values['storage']['round_trip_efficiency']:.0%}）："
            f"深谷充电 {totals['charged_mwh']:,.1f} MWh（压出力电量入储，不改变申报），晚峰放电 {totals['discharged_mwh']:,.1f} MWh，"
            f"净贡献 {_fmt_cny(totals['storage_net_cny'])} 元；放电电量按现货结算、不再享受机制差价（D 级口径）。",
            f"捕获价：满发申报把当日捕获价压到 **{capture_a:,.2f} 元/MWh**，只有时段均价 {time_weighted:,.2f} 元/MWh 的 {capture_a / time_weighted * 100:.1f}%——"
            "「发得多」的时段恰好是「价极低」的时段，这正是山东午间收益模型的核心约束。",
            "",
            "## 3. 损失归因表",
            "",
            "错误决策（满发申报）相对正确策略少收多少、哪个时段贡献最大（正数 = 满发少收）：",
            "",
            "| 时段 | 出清价 | B−A（元） | C−A（元） | 归因 |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for row in attribution_rows:
        if abs(row["b_minus_a_cny"]) < 1e-6 and abs(row["c_minus_a_cny"]) < 1e-6 and not row.get("contribution_note"):
            continue
        slot_label = f"{row['slot']:02d}:00–{row['slot'] + 1:02d}:00" if isinstance(row["slot"], int) else str(row["slot"])
        lines.append(
            f"| {slot_label} | {row.get('price_cny_per_mwh', '')} | {row['b_minus_a_cny']:+,.2f} | "
            f"{row['c_minus_a_cny']:+,.2f} | {row.get('contribution_note', '') or '—'} |"
        )
    lines.extend(
        [
            "",
            "- 申报决策损失集中在触地板价的 12:00 与 13:00 两个时段（各 "
            f"{max(r['b_minus_a_cny'] for r in attribution_rows):,.2f} 元）。基准日午间四个时段价格全部低于门槛价，"
            "固定比例压出力在基准日全窗口占优；但三情景比较显示：温和负价日同样的一刀切压出力已在高于门槛的时段开始亏钱，"
            "无负价日更是白扔约 4.94 万元——压出力必须按门槛分段，不是一刀切。",
            f"- 储能回收 {totals['storage_net_cny']:,.2f} 元发生在充电时段（12:00–14:00，压出力电量入储）与放电时段（18:00–20:00 晚峰）之间，"
            "是「错误决策的机会成本」的另一半。",
            "- 容量补偿（分账项）三条策略完全相同，从未进入差额：负价决策不触碰可靠性侧的固定成本回收。",
            "",
            "## 4. 三情景比较（同一组 D-1 申报曲线，午间价格不同）",
            "",
            "| 情景 | A 满发 | B 压出力 | C 压出力+储能 | B−A | C−A | 最优 |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for scenario in scenarios:
        lines.append(
            f"| {scenario['label']} | {_fmt_wan(scenario['a_day_cny'])} | {_fmt_wan(scenario['b_day_cny'])} | "
            f"{_fmt_wan(scenario['c_day_cny'])} | {scenario['b_minus_a_cny'] / 1e4:+,.2f} 万 | "
            f"{scenario['c_minus_a_cny'] / 1e4:+,.2f} 万 | {scenario['best_label']} |"
        )
    lines.extend(
        [
            "",
            "同一组 D-1 申报曲线在三种午间价格下结论完全不同：深谷日 C 最优；温和负价日纯压出力 B 已开始"
            "亏于「压过头」的时段（h11、h14 高于门槛价），靠储能才反超；无负价日满发 A 最优，按负价预案压出力"
            "白扔约 4.94 万元。**姿态（永远满发 / 永远压出力）不可辩护，门槛 + 触发线才可辩护。**",
            "",
            "## 5. 边界扫描：午间价格下限 × 压出力比例",
            "",
            f"把扫描窗口（时段 {window}）价格统一设为下限价、其余时段不变，扫 {len(values['floor_prices'])} × "
            f"{len(values['curtail_ratios'])} 网格（完整 90 行见 `boundary_scan.csv`）。单元格为 B−A（万元，正数 = 压出力占优）：",
            "",
            "| 下限价 \\ 压出力比例 | " + " | ".join(f"{r:.1f}" for r in values["curtail_ratios"]) + " | B 首次占优 |",
            "|---|" + "---:|" * (len(values["curtail_ratios"]) + 1),
        ]
    )
    floors_sorted = sorted(first_wins.keys(), reverse=True)
    for floor in floors_sorted:
        row_cells = []
        for row in scan_rows:
            if row["floor_price_cny_per_mwh"] != floor:
                continue
            value = row["b_minus_a_cny"] / 1e4
            row_cells.append(f"{value:+.2f}" if abs(value) > 5e-5 else "0.00")
        first = first_wins[floor]
        first_txt = "—" if first is None else f"{first:.1f}"
        lines.append(f"| {floor:g} | " + " | ".join(row_cells) + f" | {first_txt} |")
    lines.extend(
        [
            "",
            f"解析门槛：p* = (辅助服务分摊 − 机制覆盖比例 × 机制价) ÷ (1 − 机制覆盖比例) = "
            f"({values['levy_cny_per_mwh']:.0f} − {values['gamma']:.2f} × {values['mech_price_cny_per_mwh']:.0f}) ÷ "
            f"{1 - values['gamma']:.2f} = **{threshold:,.2f} 元/MWh**。",
            "读法：每多发 1 MWh 的边际净额 = (1−γ)·p + γ·机制价 − 分摊，价格低于门槛时边际净额为负，"
            "多发就是多亏；网格翻转位置与压出力比例无关——**比例决定省多少，门槛决定压不压**。",
            "该门槛对机制覆盖比例 γ 高度敏感（γ→0 时门槛≈ −分摊单价，γ→1 时压出力几乎永不可取），"
            "所以「负价动作门槛」必须先核实自家机制电量在负价时段的履约安排（案例 1 决策点 2）。",
            "",
            "## 6. 复盘五问（SOP §5.1）",
            "",
        ]
    )
    for index, question in enumerate(build_five_questions(bundle, replay, profile, strategies, attribution_rows, threshold, negative_window_energy_a, window_subtotal_a, capture_a, time_weighted), start=1):
        lines.append(f"{index}. {question}")
    lines.extend(
        [
            "",
            "## 7. 口径与边界",
            "",
            "- **规则事实**（带级别）全部取自 [`knowledge/山东电力市场-2026-11.md`](../../../../../../knowledge/山东电力市场-2026-11.md)："
            "现货 2024-06-17 转正式（B）、申报/出清限价 −80~1,300 / −100~1,500 元/MWh（B/C）、5 分钟实时出清（A/B）、"
            "2025 年负电价 >1,500 h 且触地板占 13%≈1,145 h（B/C）、负价与容量补偿分账（A，576 号）、新能源全量入市（A/B）、"
            "2026 机制电价光 0.261 元/kWh（A，149 号）、深谷时段 11:00–14:00（A，五段式分时）。",
            "- **D 级简化（影响门槛价，须先核实）**：机制电量按申报量同比例覆盖、机制差价参考价取该时段出清价、"
            "辅助服务分摊按上网电量计 6 元/MWh 占位、容量补偿按 200 MW × 50 元/kW·年 × 1.0 占位且光伏适用性待核实。",
            "- **未纳入**：预测偏差与偏差考核、两个细则、辅助服务正式结算、实时 5 分钟出清曲线细节（本包为小时级合成近似）、"
            "零售侧传导、限价草案（2026-08-28 未生效）。",
            "- 压出力的可行性与考核口径（申报曲线能否表达负价时段意愿、是否触发免考流程）按新版规则与调度要求执行，本包只算账。",
            "- 本复核表由 `run.py` 生成，全部产物确定性可复算；不构成报价、投资或法律建议。",
            "",
            f"策略指纹 `{fingerprint}`（`strategy` 规范化 JSON 的 SHA-1 前 12 位）。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="山东午间负价日满发申报策略失败复盘实例")
    parser.add_argument("--instance", type=Path, default=HERE / "instance.json")
    parser.add_argument("--price", type=Path, help="24 点价格与可用出力 CSV；--demo 时省略")
    parser.add_argument("--declare", type=Path, help="D-1 申报曲线 CSV（A 满发 / B 压出力）")
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--demo", action="store_true", help="使用仓库内合成数据")
    parser.add_argument("--check-config", action="store_true", help="只校验配置与来源表")
    args = parser.parse_args()

    try:
        bundle = load_config(args.instance)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    if args.check_config:
        values = bundle["values"]
        threshold = analytical_threshold(values)
        print("配置校验通过")
        print(f"实例: {bundle['meta']['instance_id']} · {bundle['meta']['province']} · {bundle['meta']['market']}")
        print(f"规则版本: {bundle['meta']['rule_version']}")
        print(f"风格: {values['profile_id']} · 复盘日 {values['replay_date']}（D 级合成）")
        print(
            f"三条策略: A 满发申报 / B 压出力 {values['curtail_ratio']:.0%}（触发线 {values['trigger_price_cny_per_mwh']:g} 元/MWh）"
            f" / C 压出力+储能 {values['storage']['power_mw']:.0f} MW·{values['storage']['energy_mwh']:.0f} MWh"
        )
        print(
            f"限价校验: 申报 {values['declare_floor']:g}~{values['declare_cap']:g}、出清 {values['clear_floor']:g}~{values['clear_cap']:g} 元/MWh"
        )
        if threshold is not None:
            print(f"解析门槛价（D 级假设）: {threshold:,.2f} 元/MWh")
        print("规则来源:")
        for row in bundle["report"]:
            print(f"  - {row['block']} [{row['grade']}] {row['source'][:90]}")
        return 0

    if args.price is not None and args.declare is not None:
        price_path, declare_path = args.price, args.declare
    elif args.price is not None or args.declare is not None:
        print("真实数据需同时提供 --price 与 --declare", file=sys.stderr)
        return 2
    elif args.demo:
        price_path = HERE / bundle["profile"]["file"]
        declare_path = HERE / bundle["decl"]["file"]
    else:
        print("请用 --price/--declare 指定数据 CSV，或加 --demo 使用合成数据", file=sys.stderr)
        return 2

    try:
        profile = load_price_profile(price_path, bundle)
        declarations = load_declarations(declare_path, profile, bundle)
        out_dir = args.out / "demo" if args.demo else args.out
        summary = build_outputs(bundle, profile, declarations, out_dir)
    except ConfigError as exc:
        print(f"数据错误: {exc}", file=sys.stderr)
        return 2

    base = summary["base_day"]
    best = next(row for row in base["strategies"] if row["strategy"] == base["best_strategy"])
    scan = summary["boundary_scan"]
    print(f"输出目录: {out_dir}")
    print(f"复盘日: {summary['config']['replay_date']} · 基准情景 {summary['config']['base_scenario']}（D 级合成）")
    print(f"捕获价 {base['capture_price_a_cny_per_mwh']:,.2f} 元/MWh / 时段均价 {base['time_weighted_avg_price_cny_per_mwh']:,.2f} 元/MWh（捕获率 {base['capture_rate'] * 100:.1f}%）")
    print(f"负价时段卖电收入: {base['negative_window_energy_a_cny']:,.2f} 元；午间窗口净额: {base['window_subtotal_a_cny']:,.2f} 元")
    for row in base["strategies"]:
        print(
            f"{row['label']}: 当日 {_fmt_wan(row['total_cny'])} 万元"
            + ("" if row["strategy"] == "full_output" else f"（较满发 {row['delta_vs_a_cny'] / 1e4:+,.2f} 万元）")
        )
    print(f"最优策略: {best['label']}；满发少收 {_fmt_cny(base['loss_vs_best_cny'])} 元")
    largest = summary["loss_attribution"]["largest_loss_slots"]
    print(f"最大损失时段: {largest}（各 {summary['loss_attribution']['largest_loss_slot_cny']:,.2f} 元）")
    if scan["threshold_analytical_cny_per_mwh"] is not None:
        print(f"边界: {scan['conclusion']}")
        if scan["flip_between_cny_per_mwh"]:
            print(
                f"网格翻转: {scan['flip_between_cny_per_mwh'][0]:g} 元/MWh 时 B 占优，"
                f"{scan['flip_between_cny_per_mwh'][1]:g} 元/MWh 时 A 占优（与压出力比例无关）"
            )
    for warning in summary["warnings"]:
        print(f"警告: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
