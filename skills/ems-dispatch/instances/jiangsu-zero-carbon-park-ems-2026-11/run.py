#!/usr/bin/env python3
"""Run the Jiangsu zero-carbon park microgrid instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the tariff, carbon, storage and island rules plus the
  assets and the dispatch style.
* ``data/profile_demo.csv`` is a 96-point representative day: load, PV, price
  and tariff segment.

The runner schedules a no-storage baseline, an arbitrage-only storage case and
a demand-capped case, then compares cost, imports, curtailment, unit-energy
carbon and island feasibility.

All bundled numbers are synthetic grade D. They are not a park evaluation, a
green direct-connection compliance opinion or investment advice.
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

from microgrid import (  # noqa: E402
    baseline_day,
    island_feasible,
    island_window,
    microgrid_day,
)

DT_H = 0.25
POINTS = 96
GRADES = {"A", "B", "C", "D", "A/B", "B/C", "C/D", "B/C/D"}


class ConfigError(ValueError):
    """Raised when the instance or an input file fails validation."""


def _need(block, key, path):
    if not isinstance(block, dict) or key not in block:
        raise ConfigError(f"{path} is missing {key}")
    return block[key]


def _text(block, key, path):
    value = _need(block, key, path)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _number(value, path, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a number")
    if not math.isfinite(value):
        raise ConfigError(f"{path} must be finite")
    if low is not None and value < low - 1e-12:
        raise ConfigError(f"{path} must be >= {low}")
    if high is not None and value > high + 1e-12:
        raise ConfigError(f"{path} must be <= {high}")
    return float(value)


def _grade(block, path):
    grade = _text(block, "grade", path)
    if grade not in GRADES:
        raise ConfigError(f"{path}.grade {grade!r} is not a known grade")
    return grade


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    if not isinstance(block, dict):
        raise ConfigError(f"rules.{name} must be an object")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report.append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block, grade


def load_config(path):
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"instance not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"instance is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError("instance must be a JSON object")

    meta = _need(config, "meta", "instance")
    for key in (
        "instance_id",
        "province",
        "market",
        "entity_type",
        "rule_version",
        "data_cutoff",
        "scope",
        "currency",
        "units",
        "disclaimer",
    ):
        _text(meta, key, "meta")
    _grade(meta, "meta")

    rules = _need(config, "rules", "instance")
    report = []
    tariff, _ = _rule_block(rules, "tariff", report)
    carbon, _ = _rule_block(rules, "carbon", report)
    storage, _ = _rule_block(rules, "storage", report)
    island, _ = _rule_block(rules, "island", report)

    peak = _number(_need(tariff, "peak_cny_per_kwh", "rules.tariff"), "rules.tariff.peak_cny_per_kwh", 0.0)
    flat = _number(_need(tariff, "flat_cny_per_kwh", "rules.tariff"), "rules.tariff.flat_cny_per_kwh", 0.0)
    valley = _number(_need(tariff, "valley_cny_per_kwh", "rules.tariff"), "rules.tariff.valley_cny_per_kwh", 0.0)
    if not peak >= flat >= valley:
        raise ConfigError("rules.tariff must satisfy peak >= flat >= valley")
    demand_charge = _number(
        _need(tariff, "demand_charge_cny_per_kw_month", "rules.tariff"),
        "rules.tariff.demand_charge_cny_per_kw_month",
        0.0,
    )

    grid_factor = _number(
        _need(carbon, "grid_factor_tco2_per_mwh", "rules.carbon"),
        "rules.carbon.grid_factor_tco2_per_mwh",
        0.0,
        2.0,
    )
    tce_per_mwh = _number(
        _need(carbon, "tce_per_mwh", "rules.carbon"), "rules.carbon.tce_per_mwh", 0.0, 1.0
    )

    capacity = _number(
        _need(storage, "capacity_kwh", "rules.storage"), "rules.storage.capacity_kwh", 0.0
    )
    power_charge = _number(
        _need(storage, "power_charge_kw", "rules.storage"), "rules.storage.power_charge_kw", 0.0
    )
    power_discharge = _number(
        _need(storage, "power_discharge_kw", "rules.storage"),
        "rules.storage.power_discharge_kw",
        0.0,
    )
    if capacity <= 0 or power_charge <= 0 or power_discharge <= 0:
        raise ConfigError("storage capacity and power must be positive")
    eta_charge = _number(
        _need(storage, "eta_charge", "rules.storage"), "rules.storage.eta_charge", 0.0, 1.0
    )
    eta_discharge = _number(
        _need(storage, "eta_discharge", "rules.storage"), "rules.storage.eta_discharge", 0.0, 1.0
    )
    if not 0 < eta_charge <= 1 or not 0 < eta_discharge <= 1:
        raise ConfigError("storage efficiencies must be in (0, 1]")
    soc_min = _number(_need(storage, "soc_min", "rules.storage"), "rules.storage.soc_min", 0.0, 1.0)
    soc_max = _number(_need(storage, "soc_max", "rules.storage"), "rules.storage.soc_max", 0.0, 1.0)
    if not 0 <= soc_min < soc_max <= 1:
        raise ConfigError("require 0 <= soc_min < soc_max <= 1")
    soc_init = _number(
        _need(storage, "soc_init", "rules.storage"), "rules.storage.soc_init", soc_min, soc_max
    )
    degradation = _number(
        _need(storage, "degradation_cny_per_kwh", "rules.storage"),
        "rules.storage.degradation_cny_per_kwh",
        0.0,
    )

    critical_ratio = _number(
        _need(island, "critical_load_ratio", "rules.island"),
        "rules.island.critical_load_ratio",
        0.0,
        1.0,
    )
    reserve_ratio = _number(
        _need(island, "reserve_ratio", "rules.island"), "rules.island.reserve_ratio", 0.0, 1.0
    )
    pv_availability = _number(
        _need(island, "pv_availability", "rules.island"),
        "rules.island.pv_availability",
        0.0,
        1.0,
    )
    windows = {}
    for name in ("day_window", "night_window"):
        raw = _need(island, name, "rules.island")
        if not isinstance(raw, list) or len(raw) != 2:
            raise ConfigError(f"rules.island.{name} must be a two-element list")
        start = int(_number(raw[0], f"rules.island.{name}[0]", 0.0, POINTS))
        end = int(_number(raw[1], f"rules.island.{name}[1]", 0.0, POINTS))
        if start >= end:
            raise ConfigError(f"rules.island.{name} must satisfy start < end")
        windows[name] = (start, end)

    assets = _need(config, "assets", "instance")
    pv_kwp = _number(_need(assets, "pv_kwp", "assets"), "assets.pv_kwp", 0.0)
    pcc_import = _number(
        _need(assets, "pcc_import_kw", "assets"), "assets.pcc_import_kw", 0.0
    )
    pcc_export = _number(
        _need(assets, "pcc_export_kw", "assets"), "assets.pcc_export_kw", 0.0
    )
    raw_caps = _need(assets, "demand_cap_candidates_kw", "assets")
    if not isinstance(raw_caps, list) or not raw_caps:
        raise ConfigError("assets.demand_cap_candidates_kw must be a non-empty list")
    caps = [
        _number(value, f"assets.demand_cap_candidates_kw[{i}]", 0.0, pcc_import)
        for i, value in enumerate(raw_caps)
    ]
    if len(set(caps)) != len(caps):
        raise ConfigError("assets.demand_cap_candidates_kw contains duplicates")

    policy = _need(config, "policy", "instance")
    profile_id = _text(policy, "profile_id", "policy")
    terminal = _text(policy, "terminal", "policy")
    if terminal not in {"cycle", "free"}:
        raise ConfigError("policy.terminal must be cycle or free")
    states = int(_number(_need(policy, "states", "policy"), "policy.states", 10.0, 2000.0))
    _text(policy, "objective", "policy")
    _text(policy, "demand_cap_selection", "policy")
    _grade(policy, "policy")

    data_contract = _need(config, "data_contract", "instance")
    profile = _need(data_contract, "profile", "data_contract")
    _text(profile, "file", "data_contract.profile")

    return {
        "config": config,
        "report": report,
        "tariff": {
            "peak": peak,
            "flat": flat,
            "valley": valley,
            "demand_charge": demand_charge,
        },
        "carbon": {"grid_factor": grid_factor, "tce_per_mwh": tce_per_mwh},
        "storage": {
            "capacity": capacity,
            "power_charge": power_charge,
            "power_discharge": power_discharge,
            "eta_charge": eta_charge,
            "eta_discharge": eta_discharge,
            "soc_min": soc_min,
            "soc_max": soc_max,
            "soc_init": soc_init,
            "degradation": degradation,
        },
        "island": {
            "critical_ratio": critical_ratio,
            "reserve_ratio": reserve_ratio,
            "pv_availability": pv_availability,
            "windows": windows,
        },
        "assets": {"pv_kwp": pv_kwp, "pcc_import": pcc_import, "pcc_export": pcc_export, "caps": caps},
        "policy": {"profile_id": profile_id, "terminal": terminal, "states": states},
        "base_dir": path.parent,
    }


def _time_label(index):
    hour = index * DT_H
    return f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}"


def read_profile(path, parsed):
    try:
        fh = path.open(newline="", encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"profile not found: {path}") from exc
    with fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != POINTS:
        raise ConfigError(f"profile must have {POINTS} rows, got {len(rows)}")
    required = ["interval", "time", "load_kw", "pv_kw", "buy_cny_per_kwh", "segment"]
    if rows and list(rows[0].keys()) != required:
        raise ConfigError(f"profile fields must be {required}")

    tariff = parsed["tariff"]
    prices = {"peak": tariff["peak"], "flat": tariff["flat"], "valley": tariff["valley"]}
    pv_limit = parsed["assets"]["pv_kwp"] * 1.05
    load, pv, price, segment = [], [], [], []
    for i, row in enumerate(rows):
        try:
            interval = int(row["interval"])
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"profile row {i + 1}: interval must be an integer") from exc
        if interval != i:
            raise ConfigError(f"profile row {i + 1}: interval must be {i}")
        if row["time"] != _time_label(i):
            raise ConfigError(f"profile row {i + 1}: time {row['time']!r} must be {_time_label(i)}")
        try:
            load_value = float(row["load_kw"])
            pv_value = float(row["pv_kw"])
            price_value = float(row["buy_cny_per_kwh"])
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"profile row {i + 1}: numeric fields are invalid") from exc
        if not math.isfinite(load_value) or load_value < 0:
            raise ConfigError(f"profile row {i + 1}: load_kw must be finite and >= 0")
        if not math.isfinite(pv_value) or pv_value < 0:
            raise ConfigError(f"profile row {i + 1}: pv_kw must be finite and >= 0")
        if pv_value > pv_limit + 1e-9:
            raise ConfigError(f"profile row {i + 1}: pv_kw exceeds assets.pv_kwp")
        if not math.isfinite(price_value) or price_value <= 0:
            raise ConfigError(f"profile row {i + 1}: buy_cny_per_kwh must be positive")
        seg = row["segment"].strip()
        if seg not in prices:
            raise ConfigError(f"profile row {i + 1}: segment must be peak/flat/valley")
        if abs(price_value - prices[seg]) > 1e-9:
            raise ConfigError(
                f"profile row {i + 1}: price {price_value} does not match tariff {seg}={prices[seg]}"
            )
        load.append(load_value)
        pv.append(pv_value)
        price.append(price_value)
        segment.append(seg)

    if sum(load) <= 0 or sum(pv) <= 0:
        raise ConfigError("profile must have positive load and PV energy")
    return {"load": load, "pv": pv, "price": price, "segment": segment}


def _dispatch(parsed, profile, cap_kw, pv_scale=1.0):
    storage = parsed["storage"]
    policy = parsed["policy"]
    pv = [value * pv_scale for value in profile["pv"]]
    result = microgrid_day(
        profile["load"],
        pv,
        profile["price"],
        capacity_kwh=storage["capacity"],
        power_charge_kw=storage["power_charge"],
        power_discharge_kw=storage["power_discharge"],
        eta_charge=storage["eta_charge"],
        eta_discharge=storage["eta_discharge"],
        soc_min=storage["soc_min"],
        soc_max=storage["soc_max"],
        soc_init=storage["soc_init"],
        dt_h=DT_H,
        pcc_import_kw=cap_kw,
        pcc_export_kw=parsed["assets"]["pcc_export"],
        degradation_per_kwh=storage["degradation"],
        terminal=policy["terminal"],
        states=policy["states"],
    )
    result["pv_input"] = pv
    return result


def _baseline(parsed, profile):
    result = baseline_day(
        profile["load"],
        profile["pv"],
        profile["price"],
        pcc_import_kw=parsed["assets"]["pcc_import"],
        pcc_export_kw=parsed["assets"]["pcc_export"],
    )
    if not result.get("feasible", False):
        raise ConfigError(f"baseline is infeasible: {result.get('reason')}")
    return result


def _metrics(label, result, load_total, pv_total, parsed):
    imported = float(result["imported_kwh"])
    exported = float(result["exported_kwh"])
    curtailed = float(result["curtailed_kwh"])
    pv_used = pv_total - curtailed
    emissions = imported / 1000.0 * parsed["carbon"]["grid_factor"]
    tce = load_total / 1000.0 * parsed["carbon"]["tce_per_mwh"]
    demand_charge = float(result["peak_import_kw"]) * parsed["tariff"]["demand_charge"]
    degradation = float(result.get("degradation_cost", 0.0))
    energy_cost = float(result["buy_cost"]) - float(result["sell_revenue"])
    return {
        "scenario": label,
        "imported_mwh": imported / 1000.0,
        "exported_mwh": exported / 1000.0,
        "pv_used_mwh": pv_used / 1000.0,
        "curtailed_mwh": curtailed / 1000.0,
        "peak_import_kw": float(result["peak_import_kw"]),
        "energy_cost_cny": energy_cost,
        "demand_charge_cny": demand_charge,
        "degradation_cny": degradation,
        "total_cost_cny": energy_cost + demand_charge + degradation,
        "emissions_tco2": emissions,
        "energy_tce": tce,
        "unit_carbon_t_per_mwh": emissions / (load_total / 1000.0),
        "unit_carbon_t_per_tce": emissions / tce if tce > 0 else 0.0,
        "pv_self_consumption_ratio": pv_used / pv_total if pv_total > 0 else 0.0,
        "pv_share_of_load": pv_used / load_total if load_total > 0 else 0.0,
        "self_sufficiency_ratio": (load_total - imported + exported) / load_total,
    }


def _island_rows(parsed, profile):
    island = parsed["island"]
    critical = [value * island["critical_ratio"] for value in profile["load"]]
    usable = (
        (parsed["storage"]["soc_max"] - parsed["storage"]["soc_min"])
        * parsed["storage"]["capacity"]
    )
    rows = []
    for name, (start, end) in island["windows"].items():
        need = island_window(critical, start, end, DT_H, island["reserve_ratio"])
        pv_window = sum(profile["pv"][start:end]) * DT_H * island["pv_availability"]
        available = usable + pv_window
        check = island_feasible(available, need["need_kwh"], reserve_ratio=island["reserve_ratio"])
        average_critical = sum(critical[start:end]) / need["intervals"]
        rows.append(
            {
                "window": name,
                "start": _time_label(start),
                "end": _time_label(end),
                "intervals": need["intervals"],
                "critical_load_kw": average_critical,
                "storage_available_kwh": usable,
                "pv_available_kwh": pv_window,
                "need_kwh": check["need_kwh"],
                "required_kwh": check["required_kwh"],
                "margin_kwh": check["margin_kwh"],
                "feasible": check["feasible"],
            }
        )
    return rows


def _write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fingerprint(policy):
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _fmt(value, digits=2):
    return f"{value:,.{digits}f}"


def write_review(path, parsed, rows, carbon_rows, island_rows, sensitivity, best, search_rows):
    config = parsed["config"]
    best_row = next(row for row in rows if row["scenario"] == "demand_cap")
    baseline = next(row for row in rows if row["scenario"] == "baseline")
    arbitrage = next(row for row in rows if row["scenario"] == "arbitrage_only")
    saving = baseline["total_cost_cny"] - best_row["total_cost_cny"]
    energy_saving = baseline["energy_cost_cny"] - best_row["energy_cost_cny"]
    demand_saving = baseline["demand_charge_cny"] - best_row["demand_charge_cny"]
    labels = {
        "baseline": "基线（无储能）",
        "arbitrage_only": "仅能量套利",
        "demand_cap": "需量封顶",
    }
    lines = [
        "# 江苏零碳园区微网 · 复核表",
        "",
        f"> 实例 `{config['meta']['instance_id']}`；代表日 96 点；风格 `{parsed['policy']['profile_id']}`，"
        f"指纹 `{_fingerprint(config['policy'])}`。全部为 D 级合成数据。",
        "",
        "## 1. 结论",
        "",
        f"- 基线总电费 {_fmt(baseline['total_cost_cny'])} 元/月，其中需量电费 "
        f"{_fmt(baseline['demand_charge_cny'])} 元（峰值 {_fmt(baseline['peak_import_kw'], 0)} kW）。",
        f"- 仅做能量套利（PCC 6 MW）总电费 {_fmt(arbitrage['total_cost_cny'])} 元，"
        f"比基线高 {_fmt(arbitrage['total_cost_cny'] - baseline['total_cost_cny'])} 元："
        "套利把峰值抬到 "
        f"{_fmt(arbitrage['peak_import_kw'], 0)} kW，需量电费吃掉了电量套利收益。",
        f"- 需量封顶 {_fmt(best, 0)} kW 的总电费最低：{_fmt(best_row['total_cost_cny'])} 元/月，"
        f"比基线省 **{_fmt(saving)} 元/月**（电量 {_fmt(energy_saving)} + 需量 "
        f"{_fmt(demand_saving)} − 退化 {_fmt(best_row['degradation_cny'])}）。",
        f"- 单位能耗碳排放从基线 {baseline['unit_carbon_t_per_tce']:.3f} tCO2/tce "
        f"降至 {best_row['unit_carbon_t_per_tce']:.3f} tCO2/tce，"
        "降幅来自多消纳的弃光电量，不是储能本身“零碳”。",
        "",
        "## 2. 情景对比",
        "",
        "| 情景 | 下网电量 MWh | 弃光 MWh | 峰值 kW | 电量电费 元 | 需量电费 元 | 合计 元 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {labels.get(row['scenario'], row['scenario'])} | {row['imported_mwh']:.2f} | "
            f"{row['curtailed_mwh']:.2f} | {row['peak_import_kw']:.0f} | "
            f"{row['energy_cost_cny']:,.0f} | {row['demand_charge_cny']:,.0f} | "
            f"{row['total_cost_cny']:,.0f} |"
        )
    lines += [
        "",
        "## 3. 单位能耗碳排放",
        "",
        "| 情景 | 排放 tCO2 | 能耗 tce | tCO2/MWh | tCO2/tce | 光伏占负荷 | 自给率 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in carbon_rows:
        lines.append(
            f"| {row['scenario']} | {row['emissions_tco2']:.3f} | {row['energy_tce']:.3f} | "
            f"{row['unit_carbon_t_per_mwh']:.4f} | {row['unit_carbon_t_per_tce']:.3f} | "
            f"{row['pv_share_of_load']:.1%} | {row['self_sufficiency_ratio']:.1%} |"
        )
    lines += [
        "",
        "## 4. 孤岛保安负荷校核",
        "",
        "| 窗口 | 时段 | 保安负荷需要 MWh | 含备用需要 MWh | 储能可用 MWh | 光伏可用 MWh | 余量 MWh | 可行 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in island_rows:
        lines.append(
            f"| {row['window']} | {row['start']}-{row['end']} | {row['need_kwh'] / 1000:.2f} | "
            f"{row['required_kwh'] / 1000:.2f} | {row['storage_available_kwh'] / 1000:.2f} | "
            f"{row['pv_available_kwh'] / 1000:.2f} | {row['margin_kwh'] / 1000:.2f} | "
            f"{'是' if row['feasible'] else '否'} |"
        )
    lines += [
        "",
        "## 5. 敏感性",
        "",
        "| 情景 | 关键变化 | 总电费 元/月 | 相对同情景基线 元/月 |",
        "|---|---|---:|---:|",
    ]
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {row['change']} | {row['total_cost_cny']:,.0f} | "
            f"{row['delta_vs_baseline_cny']:,.0f} |"
        )
    lines += [
        "",
        "## 6. 口径提醒",
        "",
        "1. **需量电费按元/kW·月**，电量电费按元/kWh；两者不能相加成一个“电价”。",
        "2. 代表日被假设为当月峰值日；若月内另有更高尖峰，需量电费会高于本表。",
        "3. `pcc_import_kw` 是物理上限，需量封顶是运行目标；封顶后必须校验储能 SOC 与备用。",
        f"4. 需量候选 {', '.join(f'{cap:.0f}' for cap in parsed['assets']['caps'])} kW，"
        f"最低可行候选为 {best:.0f} kW（实际峰值 {best_row['peak_import_kw']:.0f} kW）；"
        "更低的封顶不可行。",
        "5. 排放因子 0.55 tCO2/MWh 与电折标 0.1229 tce/MWh 是 D/B 级口径，"
        "正式评价须用现行官方因子并统一园区边界。",
        "6. 孤岛校核只做能量平衡，不含切换时间、保护定值、频率电压稳定与黑启动。",
        "",
        f"候选封顶搜索结果见 `demand_cap_search.csv`（{len(search_rows)} 行）。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(instance_path, out_dir, demo):
    parsed = load_config(instance_path)
    config = parsed["config"]
    data_path = Path(config["data_contract"]["profile"]["file"])
    if not data_path.is_absolute():
        data_path = parsed["base_dir"] / data_path
    profile = read_profile(data_path, parsed)

    load_total = sum(profile["load"]) * DT_H
    pv_total = sum(profile["pv"]) * DT_H

    baseline = _baseline(parsed, profile)
    baseline_metrics = _metrics("baseline", baseline, load_total, pv_total, parsed)

    arbitrage = _dispatch(parsed, profile, parsed["assets"]["pcc_import"])
    if not arbitrage.get("feasible", False):
        raise ConfigError(f"arbitrage-only dispatch is infeasible: {arbitrage.get('reason')}")
    arbitrage_metrics = _metrics("arbitrage_only", arbitrage, load_total, pv_total, parsed)

    search_rows = []
    best_result = None
    best_cap = None
    for cap in parsed["assets"]["caps"]:
        result = _dispatch(parsed, profile, cap)
        if not result.get("feasible", False):
            search_rows.append(
                {
                    "cap_kw": cap,
                    "feasible": False,
                    "peak_import_kw": 0.0,
                    "energy_cost_cny": 0.0,
                    "demand_charge_cny": 0.0,
                    "total_cost_cny": 0.0,
                    "note": result.get("reason", "infeasible"),
                }
            )
            continue
        metrics = _metrics("demand_cap", result, load_total, pv_total, parsed)
        search_rows.append(
            {
                "cap_kw": cap,
                "feasible": True,
                "peak_import_kw": metrics["peak_import_kw"],
                "energy_cost_cny": metrics["energy_cost_cny"],
                "demand_charge_cny": metrics["demand_charge_cny"],
                "total_cost_cny": metrics["total_cost_cny"],
                "note": "",
            }
        )
        if best_result is None or metrics["total_cost_cny"] < best_metrics["total_cost_cny"]:
            best_result = result
            best_metrics = metrics
            best_cap = cap
    if best_result is None:
        raise ConfigError("no demand cap candidate is feasible")
    if best_cap is None:
        raise ConfigError("failed to select a demand cap")

    demand_metrics = _metrics("demand_cap", best_result, load_total, pv_total, parsed)
    rows = [baseline_metrics, arbitrage_metrics, demand_metrics]

    carbon_rows = []
    for factor in (parsed["carbon"]["grid_factor"], 0.45):
        for row in rows:
            emissions = row["imported_mwh"] * factor
            carbon_rows.append(
                {
                    "scenario": f"{row['scenario']}@{factor:.2f}",
                    "imported_mwh": row["imported_mwh"],
                    "emissions_tco2": emissions,
                    "energy_tce": row["energy_tce"],
                    "unit_carbon_t_per_mwh": emissions / (load_total / 1000.0),
                    "unit_carbon_t_per_tce": emissions / row["energy_tce"]
                    if row["energy_tce"] > 0
                    else 0.0,
                    "pv_share_of_load": row["pv_share_of_load"],
                    "self_sufficiency_ratio": row["self_sufficiency_ratio"],
                }
            )

    island_rows = _island_rows(parsed, profile)

    sensitivity = [
        {
            "case": "基准",
            "change": "电价、需量、排放因子按配置",
            "total_cost_cny": demand_metrics["total_cost_cny"],
            "delta_vs_baseline_cny": demand_metrics["total_cost_cny"]
            - baseline_metrics["total_cost_cny"],
        }
    ]
    for value in (30.0, 50.0):
        base_total = (
            baseline_metrics["energy_cost_cny"]
            + baseline_metrics["peak_import_kw"] * value
        )
        cap_total = (
            demand_metrics["energy_cost_cny"]
            + demand_metrics["peak_import_kw"] * value
            + demand_metrics["degradation_cny"]
        )
        sensitivity.append(
            {
                "case": f"需量单价 {value:.0f} 元/kW·月",
                "change": "基线同价重算，电量与调度不变",
                "total_cost_cny": cap_total,
                "delta_vs_baseline_cny": cap_total - base_total,
            }
        )
    pv_scaled = _dispatch(parsed, profile, best_cap, pv_scale=0.9)
    if not pv_scaled.get("feasible", False):
        sensitivity.append(
            {
                "case": "光伏 −10%",
                "change": "不可行",
                "total_cost_cny": 0.0,
                "delta_vs_baseline_cny": 0.0,
            }
        )
    else:
        scaled_load = load_total
        scaled_pv = pv_total * 0.9
        scaled_metrics = _metrics("pv90", pv_scaled, scaled_load, scaled_pv, parsed)
        scaled_baseline = baseline_day(
            profile["load"],
            [value * 0.9 for value in profile["pv"]],
            profile["price"],
            pcc_import_kw=parsed["assets"]["pcc_import"],
            pcc_export_kw=parsed["assets"]["pcc_export"],
        )
        if not scaled_baseline.get("feasible", False):
            raise ConfigError(f"PV -10% baseline is infeasible: {scaled_baseline.get('reason')}")
        scaled_base_metrics = _metrics(
            "pv90_baseline", scaled_baseline, scaled_load, scaled_pv, parsed
        )
        sensitivity.append(
            {
                "case": "光伏 −10%",
                "change": "基线同幅重算，需量封顶不变",
                "total_cost_cny": scaled_metrics["total_cost_cny"],
                "delta_vs_baseline_cny": scaled_metrics["total_cost_cny"]
                - scaled_base_metrics["total_cost_cny"],
            }
        )

    warnings = []
    if arbitrage_metrics["total_cost_cny"] > baseline_metrics["total_cost_cny"]:
        warnings.append(
            "只做能量套利会把峰值抬高，需量电费可能吞掉全部套利收益；必须把需量纳入目标。"
        )
    if not next(row for row in island_rows if row["window"] == "night_window")["feasible"]:
        warnings.append("夜间孤岛不可行：2 MW/4 MWh 储能不足以覆盖 1 MW 保安负荷 4 小时。")
    if best_cap == min(parsed["assets"]["caps"]):
        warnings.append("最优需量封顶落在候选下限；应继续向下试算或检查是否被储能功率卡住。")

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        out_dir / "scenarios.csv",
        rows,
        [
            "scenario",
            "imported_mwh",
            "exported_mwh",
            "pv_used_mwh",
            "curtailed_mwh",
            "peak_import_kw",
            "energy_cost_cny",
            "demand_charge_cny",
            "degradation_cny",
            "total_cost_cny",
            "emissions_tco2",
            "energy_tce",
            "unit_carbon_t_per_mwh",
            "unit_carbon_t_per_tce",
            "pv_self_consumption_ratio",
            "pv_share_of_load",
            "self_sufficiency_ratio",
        ],
    )
    _write_csv(
        out_dir / "demand_cap_search.csv",
        search_rows,
        [
            "cap_kw",
            "feasible",
            "peak_import_kw",
            "energy_cost_cny",
            "demand_charge_cny",
            "total_cost_cny",
            "note",
        ],
    )
    _write_csv(
        out_dir / "carbon.csv",
        carbon_rows,
        [
            "scenario",
            "imported_mwh",
            "emissions_tco2",
            "energy_tce",
            "unit_carbon_t_per_mwh",
            "unit_carbon_t_per_tce",
            "pv_share_of_load",
            "self_sufficiency_ratio",
        ],
    )
    _write_csv(
        out_dir / "island.csv",
        island_rows,
        [
            "window",
            "start",
            "end",
            "intervals",
            "critical_load_kw",
            "storage_available_kwh",
            "pv_available_kwh",
            "need_kwh",
            "required_kwh",
            "margin_kwh",
            "feasible",
        ],
    )
    _write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        ["case", "change", "total_cost_cny", "delta_vs_baseline_cny"],
    )

    schedule = best_result["schedule"]
    dispatch_rows = []
    for i in range(POINTS):
        dispatch_rows.append(
            {
                "interval": i,
                "time": _time_label(i),
                "segment": profile["segment"][i],
                "buy_cny_per_kwh": profile["price"][i],
                "load_kw": profile["load"][i],
                "pv_kw": profile["pv"][i],
                "baseline_import_kw": max(0.0, profile["load"][i] - profile["pv"][i]),
                "ems_import_kw": schedule["p_import_kw"][i],
                "ems_charge_kw": schedule["p_charge_kw"][i],
                "ems_discharge_kw": schedule["p_discharge_kw"][i],
                "pv_curtailed_kw": schedule["pv_curtailed_kw"][i],
                "soc": schedule["soc"][i],
            }
        )
    _write_csv(
        out_dir / "dispatch.csv",
        dispatch_rows,
        [
            "interval",
            "time",
            "segment",
            "buy_cny_per_kwh",
            "load_kw",
            "pv_kw",
            "baseline_import_kw",
            "ems_import_kw",
            "ems_charge_kw",
            "ems_discharge_kw",
            "pv_curtailed_kw",
            "soc",
        ],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "profile": {
            "file": str(data_path),
            "points": POINTS,
            "load_mwh": load_total / 1000.0,
            "pv_mwh": pv_total / 1000.0,
            "load_peak_kw": max(profile["load"]),
            "pv_peak_kw": max(profile["pv"]),
        },
        "policy_fingerprint": _fingerprint(config["policy"]),
        "provenance": parsed["report"],
        "best_demand_cap_kw": best_cap,
        "scenarios": rows,
        "carbon": carbon_rows,
        "island": island_rows,
        "sensitivity": sensitivity,
        "warnings": warnings,
        "files": [
            "scenarios.csv",
            "demand_cap_search.csv",
            "dispatch.csv",
            "carbon.csv",
            "island.csv",
            "sensitivity.csv",
            "summary.json",
            "review.md",
        ],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(
        out_dir / "review.md",
        parsed,
        rows,
        carbon_rows,
        island_rows,
        sensitivity,
        best_cap,
        search_rows,
    )

    print(
        f"实例：{config['meta']['instance_id']} / 代表日负荷 {load_total / 1000:.2f} MWh / "
        f"光伏 {pv_total / 1000:.2f} MWh"
    )
    print(
        f"基线 {baseline_metrics['total_cost_cny']:,.0f} 元 → 需量封顶 {best_cap:.0f} kW "
        f"{demand_metrics['total_cost_cny']:,.0f} 元（省 "
        f"{baseline_metrics['total_cost_cny'] - demand_metrics['total_cost_cny']:,.0f} 元/月）"
    )
    print(f"输出目录：{out_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--out", default=str(HERE / "out"))
    parser.add_argument("--demo", action="store_true", help="run the bundled synthetic day")
    parser.add_argument("--check-config", action="store_true", help="validate the instance only")
    args = parser.parse_args()

    instance_path = Path(args.instance)
    try:
        parsed = load_config(instance_path)
        if args.check_config:
            config = parsed["config"]
            print(f"配置校验通过：{config['meta']['instance_id']}")
            for item in parsed["report"]:
                print(f"  {item['block']:<24} {item['grade']:<5} {item['source'][:60]}")
            print(
                f"  电价 峰/平/谷 = {parsed['tariff']['peak']:.2f} / "
                f"{parsed['tariff']['flat']:.2f} / {parsed['tariff']['valley']:.2f} 元/kWh；"
                f"需量 {parsed['tariff']['demand_charge']:.0f} 元/kW·月"
            )
            print(
                f"  储能 {parsed['storage']['capacity']:.0f} kWh / "
                f"{parsed['storage']['power_discharge']:.0f} kW；"
                f"需量候选 {', '.join(f'{cap:.0f}' for cap in parsed['assets']['caps'])} kW"
            )
            return
        if not args.demo:
            print("请使用 --demo 运行合成数据，或 --check-config 只做配置校验。")
            raise SystemExit(2)
        run(instance_path, Path(args.out) / "demo", True)
    except ConfigError as exc:
        print(f"配置错误：{exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
