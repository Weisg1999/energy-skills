#!/usr/bin/env python3
"""Run the Sichuan 300 MW runoff-hydro mid/long-term hedging case.

The engine is shared, the instance is local:

* ``instance.json`` holds the Sichuan season (丰/平/枯) rules, the spot
  settlement design, the surplus-water (弃水电量消纳) facts, the synthetic
  hydro asset and the hedging style.
* ``data/profile_demo.csv`` is a synthetic first-full-trading-year profile:
  season tag, generation, contract weight and the monthly spot price.

Sichuan specifics modeled here (grades from the provincial knowledge module):

* the medium/long-term contract is a PURE FINANCIAL HEDGE (C): all physical
  energy settles at the spot price, the contract settles the difference
  ``contract_mwh x (contract_price - spot_price)``;
* contract volume is decomposed by the 丰/平/枯 season ratio of 2025 regular
  direct purchases, 45.23% / 16.73% / 38.04% (B);
* the day-ahead run is a pre-clearing that does NOT settle (C/draft);
  real-time clearing settles (C/draft);
* surplus 丰水期 energy can be sold through the surplus-water channel
  (弃水电量消纳, 2025 avg 0.1477 CNY/kWh, B) instead of the spot market;
* the spot declare/clear limits are NULL by design: the draft only sets the
  2026 floor tentatively at 0 and never divides limits by season (C/draft).
  Profile prices are instead plausibility-checked against the observed 2025
  trial range [-0.05, 0.8] CNY/kWh (B), which is NOT a price limit.

All bundled numbers are grade D synthetic except the cited rule facts. This
pack is not a trading instruction or investment advice.
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

GRADES = {"A", "B", "C", "D", "A/B", "B/C", "B/C/D", "C/D"}
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SEASONS = ("丰", "平", "枯")
STRATEGIES = ("all_spot", "contract_cfd", "contract_cfd_surplus")
LABELS = {
    "all_spot": "全电量现货（不对冲）",
    "contract_cfd": "中长期对冲（余量留现货）",
    "contract_cfd_surplus": "中长期对冲 + 弃水消纳",
}
# 模块口径（C，§7.2）：丰水期 6–10 月、枯水期 1–4 月及 12 月、平水期其余
MODULE_SEASON_MONTHS = {"丰": [6, 7, 8, 9, 10], "平": [5, 11], "枯": [1, 2, 3, 4, 12]}
REQUIRED_PROFILE_FIELDS = ("month", "season", "generation_mwh", "contract_weight", "spot_price_cny_per_kwh")

# 待核实清单：模块未给正式值、本包一律不补数
PENDING_ITEMS = [
    "现货申报/出清限价正式值：征求意见稿为不分水期、2026 全年下限暂设 0（C/草案，§4.1），未核到正式印发；2025 实测 −0.05 与行业口径 −50–800 元/MWh 不能当作限价",
    "中长期丰平枯分期限价省级正式文件：丰 211.43 / 平 333.84 / 枯 415.63 / 月内滚动 481.44 元/MWh 为行业口径（C，§4.1）",
    "四川现货转正式运行时间表与文号：2025-11 起为连续结算试运行（B），截至 2026-11-12 未核到转正文件",
    "规则体系 V4.0 现行全文与 420号/421号征求意见稿的正式印发版（C，文档状态：草案）",
    "结算细则调整（291号文，2026-07-06）发电侧缺额/超额收益回收 85%/115% 的省级原文（C 行业口径，§5）",
    "弃水电量消纳 2026 年组织方式、限价与购售主体结构（2025 口径为 B，当年以交易公告为准）",
]


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


def _nullable_number(block, key, path):
    value = _need(block, key, path)
    if value is None:
        return None
    return _number(value, path)


def _grade(block, path):
    grade = _text(block, "grade", path)
    if grade not in GRADES:
        raise ConfigError(f"{path}.grade {grade!r} 不是已知级别")
    return grade


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    if not isinstance(block, dict):
        raise ConfigError(f"rules.{name} 必须是对象")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    status = _text(block, "status", f"rules.{name}")
    report.append({"block": f"rules.{name}", "grade": grade, "source": source, "status": status})
    return block


def _season_number_map(block, key, path):
    raw = _need(block, key, path)
    if not isinstance(raw, dict) or set(raw) != set(SEASONS):
        raise ConfigError(f"{path} 必须包含 丰/平/枯 三个键")
    result = {}
    for season in SEASONS:
        months = raw[season]
        if not isinstance(months, list) or not months:
            raise ConfigError(f"{path}.{season} 必须是非空月份列表")
        values = []
        for month in months:
            if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
                raise ConfigError(f"{path}.{season} 月份必须是 1–12 的整数")
            values.append(month)
        result[season] = values
    flat = [month for months in result.values() for month in months]
    if sorted(flat) != list(range(1, 13)):
        raise ConfigError(f"{path} 必须恰好覆盖 1–12 月各一次")
    return result


def _season_ratio_map(block, key, path):
    raw = _need(block, key, path)
    if not isinstance(raw, dict) or set(raw) != set(SEASONS):
        raise ConfigError(f"{path} 必须包含 丰/平/枯 三个键")
    result = {}
    for season in SEASONS:
        result[season] = _number(raw[season], f"{path}.{season}", 0.0, 1.0)
    if abs(sum(result.values()) - 1.0) > 1e-6:
        raise ConfigError(f"{path} 三季之和必须为 1，实际 {sum(result.values()):.6f}")
    return result


def _season_price_map(block, key, path):
    """丰/平/枯 三键的正数价格表（元/MWh），不限制上限。"""
    raw = _need(block, key, path)
    if not isinstance(raw, dict) or set(raw) != set(SEASONS):
        raise ConfigError(f"{path} 必须包含 丰/平/枯 三个键")
    return {season: _number(raw[season], f"{path}.{season}", 0.0) for season in SEASONS}


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
    for key in ("instance_id", "province", "market", "entity_type", "rule_version", "data_cutoff", "scope", "currency", "units", "disclaimer"):
        _text(meta, key, "meta")
    _grade(meta, "meta")

    rules = _need(config, "rules", "instance")
    report = []
    season_rules = _rule_block(rules, "season_pricing", report)
    spot_rules = _rule_block(rules, "spot_settlement", report)
    surplus_rules = _rule_block(rules, "surplus_water", report)

    season_split = _season_ratio_map(season_rules, "regular_direct_ratio", "rules.season_pricing")
    season_months = _season_number_map(season_rules, "season_months", "rules.season_pricing")
    if season_months != MODULE_SEASON_MONTHS:
        raise ConfigError(
            "rules.season_pricing.season_months 必须与模块口径一致：丰 6–10 月、平 5/11 月、枯 1–4 及 12 月（C，§7.2）"
        )
    limits_raw = _season_price_map(season_rules, "mid_long_term_limit_cny_per_mwh", "rules.season_pricing")
    for season in SEASONS:
        if limits_raw[season] <= 0:
            raise ConfigError(f"rules.season_pricing.mid_long_term_limit_cny_per_mwh.{season} 必须为正")
    limits = {season: value / 1000.0 for season, value in limits_raw.items()}  # 元/MWh → 元/kWh
    rolling_cap = _nullable_number(season_rules, "rolling_monthly_cap_cny_per_mwh", "rules.season_pricing")
    rolling_cap_kwh = rolling_cap / 1000.0 if rolling_cap is not None else None
    if rolling_cap_kwh is not None and rolling_cap_kwh < max(limits.values()):
        raise ConfigError("月内滚动上限不得低于枯季分期限价")

    role = _text(spot_rules, "mid_long_term_role", "rules.spot_settlement")
    if role != "financial_hedge":
        raise ConfigError("本包只实现中长期纯金融对冲（financial_hedge）口径")
    observed_min = _number(_need(spot_rules, "observed_2025_min_cny_per_kwh", "rules.spot_settlement"), "rules.spot_settlement.observed_2025_min_cny_per_kwh")
    observed_max = _number(_need(spot_rules, "observed_2025_max_cny_per_kwh", "rules.spot_settlement"), "rules.spot_settlement.observed_2025_max_cny_per_kwh")
    observed_avg = _number(_need(spot_rules, "observed_2025_avg_cny_per_kwh", "rules.spot_settlement"), "rules.spot_settlement.observed_2025_avg_cny_per_kwh", 0.0)
    if observed_min >= observed_max:
        raise ConfigError("observed_2025_min_cny_per_kwh 必须小于 observed_2025_max_cny_per_kwh")
    declare_floor = _nullable_number(spot_rules, "declare_floor_cny_per_kwh", "rules.spot_settlement")
    declare_cap = _nullable_number(spot_rules, "declare_cap_cny_per_kwh", "rules.spot_settlement")
    if declare_floor is None or declare_cap is None:
        _text(spot_rules, "status", "rules.spot_settlement")  # 限价未核实时必须写明待核实状态
    feng_anchor = _number(_need(spot_rules, "feng_realtime_avg_cny_per_mwh", "rules.spot_settlement"), "rules.spot_settlement.feng_realtime_avg_cny_per_mwh", 0.0)
    ku_anchor = _number(_need(spot_rules, "ku_realtime_avg_cny_per_mwh", "rules.spot_settlement"), "rules.spot_settlement.ku_realtime_avg_cny_per_mwh", 0.0)
    if feng_anchor >= ku_anchor:
        raise ConfigError("丰水期实时均价锚必须低于枯水期锚（丰低枯高，C 口径 §4.3）")

    surplus_price = _number(_need(surplus_rules, "avg_price_cny_per_kwh", "rules.surplus_water"), "rules.surplus_water.avg_price_cny_per_kwh", 0.0)
    feng_share = _number(_need(surplus_rules, "feng_share", "rules.surplus_water"), "rules.surplus_water.feng_share", 0.0, 1.0)
    ping_share = _number(_need(surplus_rules, "ping_share", "rules.surplus_water"), "rules.surplus_water.ping_share", 0.0, 1.0)
    if abs(feng_share + ping_share - 1.0) > 1e-6:
        raise ConfigError("rules.surplus_water 丰平比之和必须为 1")
    volume = _number(_need(surplus_rules, "volume_2025_yi_kwh", "rules.surplus_water"), "rules.surplus_water.volume_2025_yi_kwh", 0.0)
    if volume <= 0 or surplus_price <= 0:
        raise ConfigError("弃水消纳成交量与均价必须为正")

    project = _need(config, "project", "instance")
    capacity = _number(_need(project, "capacity_mw", "project"), "project.capacity_mw", 0.0)
    p50 = _number(_need(project, "p50_hours", "project"), "project.p50_hours", 0.0, 8760.0)
    cod = _text(project, "cod", "project")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", cod):
        raise ConfigError("project.cod 必须是 YYYY-MM-DD")
    _text(project, "runoff_type", "project")
    _grade(project, "project")
    _text(project, "source", "project")
    if capacity <= 0 or p50 <= 0:
        raise ConfigError("装机容量与 P50 利用小时必须为正")

    policy = _need(config, "policy", "instance")
    profile_id = _text(policy, "profile_id", "policy")
    ratio = _number(_need(policy, "contract_ratio", "policy"), "policy.contract_ratio", 0.0, 1.0)
    strategies = _need(policy, "strategies", "policy")
    if not isinstance(strategies, list) or set(strategies) != set(STRATEGIES):
        raise ConfigError("policy.strategies 必须包含 all_spot / contract_cfd / contract_cfd_surplus 三项")
    prices_raw = _need(policy, "contract_price_cny_per_kwh", "policy")
    if not isinstance(prices_raw, dict) or set(prices_raw) != set(SEASONS):
        raise ConfigError("policy.contract_price_cny_per_kwh 必须包含 丰/平/枯 三个键")
    contract_prices = {}
    for season in SEASONS:
        price = _number(prices_raw[season], f"policy.contract_price_cny_per_kwh.{season}", 0.0)
        if price > limits[season]:
            raise ConfigError(
                f"policy.contract_price_cny_per_kwh.{season}={price:.4f} 高于分期限价 {limits[season]:.5f} 元/kWh"
                f"（{limits_raw[season]:.2f} 元/MWh，C 行业口径）——不得按超限价签约"
            )
        if rolling_cap_kwh is not None and price > rolling_cap_kwh:
            raise ConfigError(f"policy.contract_price_cny_per_kwh.{season} 高于月内滚动上限")
        contract_prices[season] = price
    if _text(policy, "surplus_channel", "policy") != "feng_only":
        raise ConfigError("本包只实现丰水期弃水消纳（feng_only）口径")
    _text(policy, "decision_rule", "policy")
    _grade(policy, "policy")

    contract = _need(config, "data_contract", "instance")
    profile = _need(contract, "profile", "data_contract")
    _text(profile, "file", "data_contract.profile")
    fields = _need(profile, "fields", "data_contract.profile")
    if not isinstance(fields, list) or not set(REQUIRED_PROFILE_FIELDS).issubset(set(fields)):
        raise ConfigError("data_contract.profile.fields 必须包含 month / season / generation_mwh / contract_weight / spot_price_cny_per_kwh")

    return {
        "config": config,
        "report": report,
        "meta": meta,
        "season_rules": season_rules,
        "spot_rules": spot_rules,
        "surplus_rules": surplus_rules,
        "project": project,
        "policy": policy,
        "profile": profile,
        "values": {
            "season_split": season_split,
            "season_months": season_months,
            "limits_kwh": limits,
            "limits_mwh": limits_raw,
            "rolling_cap_kwh": rolling_cap_kwh,
            "observed_min": observed_min,
            "observed_max": observed_max,
            "observed_avg": observed_avg,
            "feng_anchor": feng_anchor,
            "ku_anchor": ku_anchor,
            "surplus_price": surplus_price,
            "feng_share": feng_share,
            "ping_share": ping_share,
            "capacity": capacity,
            "p50": p50,
            "planned": capacity * p50,
            "ratio": ratio,
            "contract_prices": contract_prices,
            "profile_id": profile_id,
        },
    }


def load_profile(path, bundle):
    values = bundle["values"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = reader.fieldnames or []
    except FileNotFoundError as exc:
        raise ConfigError(f"profile 文件不存在: {path}") from exc
    except csv.Error as exc:
        raise ConfigError(f"profile CSV 解析失败: {exc}") from exc

    for field in REQUIRED_PROFILE_FIELDS:
        if field not in fields:
            raise ConfigError(f"profile CSV 缺少字段 {field}")
    if len(rows) != 12:
        raise ConfigError(f"profile 必须包含 12 个月，实际 {len(rows)} 行")

    month_to_season = {}
    for season, months in values["season_months"].items():
        for month in months:
            month_to_season[month] = season

    months, seasons, generation, weights, spot = [], [], [], [], []
    for index, row in enumerate(rows, start=2):
        month = (row.get("month") or "").strip()
        if not MONTH_RE.match(month):
            raise ConfigError(f"profile 第 {index} 行 month 不是 YYYY-MM")
        if month in months:
            raise ConfigError(f"profile 第 {index} 行 month 重复: {month}")
        season = (row.get("season") or "").strip()
        if season not in SEASONS:
            raise ConfigError(f"profile 第 {index} 行 season 必须是 丰/平/枯")
        expected = month_to_season[int(month.split("-")[1])]
        if season != expected:
            raise ConfigError(
                f"profile 第 {index} 行 season={season} 与模块口径不符：{month} 应为 {expected}"
                "（丰 6–10 月、平 5/11 月、枯 1–4 及 12 月，C，§7.2）"
            )
        gen = _number(float(row["generation_mwh"]), f"profile 第 {index} 行 generation_mwh", 0.0)
        weight = _number(float(row["contract_weight"]), f"profile 第 {index} 行 contract_weight", 0.0, 1.0)
        price = _number(float(row["spot_price_cny_per_kwh"]), f"profile 第 {index} 行 spot_price_cny_per_kwh", values["observed_min"], values["observed_max"])
        if gen <= 0:
            raise ConfigError(f"profile 第 {index} 行 generation_mwh 必须为正")
        months.append(month)
        seasons.append(season)
        generation.append(gen)
        weights.append(weight)
        spot.append(price)

    if len({month.split("-")[0] for month in months}) != 1:
        raise ConfigError("profile 必须覆盖同一个自然年")
    if months != sorted(months):
        raise ConfigError("profile 必须按月份升序排列")
    if abs(sum(weights) - 1.0) > 1e-3:
        raise ConfigError(f"contract_weight 合计必须为 1，实际 {sum(weights):.6f}")
    for season in SEASONS:
        season_weight = sum(weight for weight, tag in zip(weights, seasons) if tag == season)
        target = values["season_split"][season]
        if abs(season_weight - target) > 2e-3:
            raise ConfigError(
                f"{season} 季合同权重合计 {season_weight:.6f} 偏离分期比例 {target:.4f} 超过 0.002"
                "（常规直购丰/平/枯电量比，B，§5）"
            )

    total = sum(generation)
    planned = values["planned"]
    warnings = []
    if not 0.8 * planned <= total <= 1.2 * planned:
        warnings.append(
            f"年度发电量 {total:,.0f} MWh 偏离计划电量 {planned:,.0f} MWh 超过 20%，请核对来水数据"
        )
    season_gen = {season: sum(generation[i] for i in range(12) if seasons[i] == season) for season in SEASONS}
    if season_gen["丰"] / total < 0.40:
        warnings.append(
            f"丰水期发电占比 {season_gen['丰'] / total:.1%} 低于 40%：四川丰水期 6–10 月来水集中（C，§7.2），"
            "径流式机组出力形态明显偏离该口径时请复核径流曲线"
        )
    return {
        "months": months,
        "seasons": seasons,
        "generation": generation,
        "weights": weights,
        "spot": spot,
        "total_generation": total,
        "planned_generation": planned,
        "season_generation": season_gen,
        "warnings": warnings,
    }


def compute(bundle, profile, overrides=None):
    overrides = overrides or {}
    values = bundle["values"]
    ratio = overrides.get("contract_ratio", values["ratio"])
    contract_prices = dict(values["contract_prices"])
    price_delta = overrides.get("contract_price_delta", 0.0)
    season_price_delta = overrides.get("season_contract_delta", {})
    for season in SEASONS:
        contract_prices[season] = max(contract_prices[season] + price_delta + season_price_delta.get(season, 0.0), 0.0)
    spot_scale = overrides.get("spot_scale", 1.0)
    season_spot_scale = overrides.get("season_spot_scale", {})
    surplus_price = max(values["surplus_price"] + overrides.get("surplus_price_delta", 0.0), 0.0)
    surplus_off = bool(overrides.get("surplus_off", False))
    generation_scale = overrides.get("generation_scale", 1.0)
    planned = profile["planned_generation"]

    monthly = []
    for index in range(12):
        month = profile["months"][index]
        season = profile["seasons"][index]
        generation = profile["generation"][index] * generation_scale
        weight = profile["weights"][index]
        spot_price = profile["spot"][index] * spot_scale * season_spot_scale.get(season, 1.0)
        contract_mwh = planned * ratio * weight
        contract_price = contract_prices[season]
        coverage = contract_mwh / generation if generation > 0 else 0.0
        spot_revenue = generation * spot_price * 1000.0
        hedge_settlement = contract_mwh * (contract_price - spot_price) * 1000.0
        surplus_mwh = max(generation - contract_mwh, 0.0) if season == "丰" and not surplus_off else 0.0
        surplus_gain = surplus_mwh * (surplus_price - spot_price) * 1000.0 if surplus_mwh > 0 else 0.0
        monthly.append(
            {
                "month": month,
                "season": season,
                "generation_mwh": generation,
                "contract_mwh": contract_mwh,
                "hedge_coverage": coverage,
                "spot_price_cny_per_kwh": spot_price,
                "contract_price_cny_per_kwh": contract_price,
                "spot_revenue_cny": spot_revenue,
                "hedge_settlement_cny": hedge_settlement,
                "surplus_mwh": surplus_mwh,
                "surplus_gain_cny": surplus_gain,
                "all_spot_cny": spot_revenue,
                "contract_cfd_cny": spot_revenue + hedge_settlement,
                "contract_surplus_cny": spot_revenue + hedge_settlement + surplus_gain,
                "delta_cfd_vs_spot_cny": hedge_settlement,
                "delta_surplus_vs_spot_cny": hedge_settlement + surplus_gain,
            }
        )

    total_generation = sum(row["generation_mwh"] for row in monthly)
    total_contract = sum(row["contract_mwh"] for row in monthly)
    total_spot_revenue = sum(row["spot_revenue_cny"] for row in monthly)
    total_hedge = sum(row["hedge_settlement_cny"] for row in monthly)
    total_surplus = sum(row["surplus_mwh"] for row in monthly)
    total_surplus_gain = sum(row["surplus_gain_cny"] for row in monthly)
    weighted_spot = (
        capture_price(
            [row["spot_price_cny_per_kwh"] for row in monthly],
            [row["generation_mwh"] for row in monthly],
        )
        if total_generation > 0
        else 0.0
    )
    weighted_contract = (
        capture_price(
            [row["contract_price_cny_per_kwh"] for row in monthly],
            [row["contract_mwh"] for row in monthly],
        )
        if total_contract > 0
        else 0.0
    )
    negative_hedge = [row for row in monthly if row["hedge_settlement_cny"] < 0]

    seasons = []
    for season in SEASONS:
        rows = [row for row in monthly if row["season"] == season]
        season_gen = sum(row["generation_mwh"] for row in rows)
        season_contract = sum(row["contract_mwh"] for row in rows)
        season_spot_revenue = sum(row["spot_revenue_cny"] for row in rows)
        season_hedge = sum(row["hedge_settlement_cny"] for row in rows)
        season_surplus = sum(row["surplus_mwh"] for row in rows)
        season_surplus_gain = sum(row["surplus_gain_cny"] for row in rows)
        seasons.append(
            {
                "season": season,
                "months": " ".join(row["month"] for row in rows),
                "generation_mwh": season_gen,
                "generation_share": season_gen / total_generation if total_generation > 0 else 0.0,
                "contract_mwh": season_contract,
                "contract_coverage": season_contract / season_gen if season_gen > 0 else 0.0,
                "contract_price_cny_per_kwh": contract_prices[season],
                "limit_price_cny_per_mwh": values["limits_mwh"][season],
                "limit_headroom_cny_per_mwh": values["limits_mwh"][season] - contract_prices[season] * 1000.0,
                "weighted_spot_price_cny_per_kwh": (
                    capture_price(
                        [row["spot_price_cny_per_kwh"] for row in rows],
                        [row["generation_mwh"] for row in rows],
                    )
                    if season_gen > 0
                    else 0.0
                ),
                "hedge_settlement_cny": season_hedge,
                "surplus_mwh": season_surplus,
                "surplus_gain_cny": season_surplus_gain,
                "net_price_all_spot_cny_per_kwh": (
                    season_spot_revenue / (season_gen * 1000.0) if season_gen > 0 else 0.0
                ),
                "net_price_contract_cfd_cny_per_kwh": (
                    (season_spot_revenue + season_hedge) / (season_gen * 1000.0) if season_gen > 0 else 0.0
                ),
            }
        )

    strategies = [
        {
            "strategy": "all_spot",
            "label": LABELS["all_spot"],
            "contract_mwh": 0.0,
            "spot_revenue_cny": total_spot_revenue,
            "hedge_settlement_cny": 0.0,
            "surplus_mwh": 0.0,
            "surplus_gain_cny": 0.0,
            "total_revenue_cny": total_spot_revenue,
            "net_price_cny_per_kwh": total_spot_revenue / (total_generation * 1000.0) if total_generation > 0 else 0.0,
        },
        {
            "strategy": "contract_cfd",
            "label": LABELS["contract_cfd"],
            "contract_mwh": total_contract,
            "spot_revenue_cny": total_spot_revenue,
            "hedge_settlement_cny": total_hedge,
            "surplus_mwh": 0.0,
            "surplus_gain_cny": 0.0,
            "total_revenue_cny": total_spot_revenue + total_hedge,
            "net_price_cny_per_kwh": (total_spot_revenue + total_hedge) / (total_generation * 1000.0) if total_generation > 0 else 0.0,
        },
        {
            "strategy": "contract_cfd_surplus",
            "label": LABELS["contract_cfd_surplus"],
            "contract_mwh": total_contract,
            "spot_revenue_cny": total_spot_revenue,
            "hedge_settlement_cny": total_hedge,
            "surplus_mwh": total_surplus,
            "surplus_gain_cny": total_surplus_gain,
            "total_revenue_cny": total_spot_revenue + total_hedge + total_surplus_gain,
            "net_price_cny_per_kwh": (total_spot_revenue + total_hedge + total_surplus_gain) / (total_generation * 1000.0) if total_generation > 0 else 0.0,
        },
    ]
    best = max(strategies, key=lambda row: row["total_revenue_cny"])
    for row in strategies:
        row["delta_vs_all_spot_cny"] = row["total_revenue_cny"] - total_spot_revenue
        row["delta_vs_best_cny"] = row["total_revenue_cny"] - best["total_revenue_cny"]

    season_gen_map = {row["season"]: row["generation_mwh"] for row in seasons}
    season_contract_map = {row["season"]: row["contract_mwh"] for row in seasons}
    return {
        "monthly": monthly,
        "seasons": seasons,
        "strategies": strategies,
        "best": best,
        "metrics": {
            "planned_generation_mwh": planned,
            "total_generation_mwh": total_generation,
            "total_contract_mwh": total_contract,
            "contract_ratio": ratio,
            "total_spot_revenue_cny": total_spot_revenue,
            "total_hedge_settlement_cny": total_hedge,
            "negative_hedge_months": [row["month"] for row in negative_hedge],
            "negative_hedge_total_cny": sum(row["hedge_settlement_cny"] for row in negative_hedge),
            "total_surplus_mwh": total_surplus,
            "total_surplus_gain_cny": total_surplus_gain,
            "weighted_spot_price_cny_per_kwh": weighted_spot,
            "weighted_contract_price_cny_per_kwh": weighted_contract,
            "surplus_price_cny_per_kwh": surplus_price,
            "season_generation": season_gen_map,
            "season_contract": season_contract_map,
            "season_coverage": {
                season: (season_contract_map[season] / season_gen_map[season] if season_gen_map[season] > 0 else 0.0)
                for season in SEASONS
            },
        },
    }


def build_sensitivity(bundle, profile, base):
    base_best = base["best"]["total_revenue_cny"]
    cases = [
        ("基准", "80% 合同按丰平枯分解 + 丰水期余量走弃水消纳", {}),
        ("现货整体 +30%", "枯水期持续冲高情景：现货价全线上浮 30%", {"spot_scale": 1.30}),
        ("现货整体 −20%", "丰水期过剩外溢：现货价整体下调 20%", {"spot_scale": 0.80}),
        ("丰水期现货 −40%", "丰水过剩加剧：丰水期月份现货再降 40%", {"season_spot_scale": {"丰": 0.60}}),
        ("枯水期现货 +30%", "枯水冲高：枯水期月份现货再涨 30%", {"season_spot_scale": {"枯": 1.30}}),
        ("合同价全线 −0.02", "合同价各季下调 0.02 元/kWh", {"contract_price_delta": -0.02}),
        ("枯水期合同价 −0.03", "枯水期签约折价：仅枯季合同价下调 0.03 元/kWh", {"season_contract_delta": {"枯": -0.03}}),
        ("合同比例 65%", "合同电量由 80% 降至 65%", {"contract_ratio": 0.65}),
        ("合同比例 90%", "合同电量由 80% 升至 90%", {"contract_ratio": 0.90}),
        ("弃水消纳价 −0.03", "弃水电量消纳价由 0.1477 降至 0.1177 元/kWh", {"surplus_price_delta": -0.03}),
        ("弃水品种缺失", "丰水期余量无弃水消纳可走，全留现货", {"surplus_off": True}),
        ("来水枯年 −12%", "发电量整体下调 12%，合同电量不变", {"generation_scale": 0.88}),
    ]
    rows = []
    for name, change, overrides in cases:
        result = compute(bundle, profile, overrides)
        best = result["best"]
        rows.append(
            {
                "case": name,
                "change": change,
                "all_spot_cny": round(result["strategies"][0]["total_revenue_cny"], 2),
                "contract_cfd_cny": round(result["strategies"][1]["total_revenue_cny"], 2),
                "contract_surplus_cny": round(result["strategies"][2]["total_revenue_cny"], 2),
                "best_strategy": best["label"],
                "best_net_cny": round(best["total_revenue_cny"], 2),
                "best_price_cny_per_kwh": round(best["net_price_cny_per_kwh"], 6),
                "delta_vs_base_best_cny": round(best["total_revenue_cny"] - base_best, 2) or 0.0,
            }
        )
    return rows


def _fmt_wan(value):
    return f"{value / 1e4:,.2f}"


def _fmt_pct(value):
    return f"{value * 100:.2f}%"


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_outputs(bundle, profile, out_dir):
    values = bundle["values"]
    base = compute(bundle, profile)
    sensitivity = build_sensitivity(bundle, profile, base)
    metrics = base["metrics"]

    warnings = list(profile["warnings"])
    if metrics["season_coverage"]["枯"] > 1.10:
        warnings.append(
            f"枯水期合同覆盖率 {_fmt_pct(metrics['season_coverage']['枯'])}：按全省常规直购分期比例"
            f"（45.23/16.73/38.04，B，§5）分解合同，对丰水期占比 {_fmt_pct(base['seasons'][0]['generation_share'])}"
            " 的径流式机组意味着枯水期超对冲、丰水期欠对冲——别人的分期比例不是你的分期比例"
        )
    if metrics["season_coverage"]["丰"] < 0.90:
        warnings.append(
            f"丰水期合同覆盖率仅 {_fmt_pct(metrics['season_coverage']['丰'])}，"
            "丰水期余量直接暴露于现货低价；余量是否走弃水消纳见策略比较"
        )
    if metrics["negative_hedge_months"]:
        warnings.append(
            f"{len(metrics['negative_hedge_months'])} 个月现货价高于合同价（"
            + "、".join(metrics["negative_hedge_months"])
            + f"），中长期锁价让渡上行合计 {_fmt_wan(-metrics['negative_hedge_total_cny'])} 万元"
        )
    if metrics["weighted_spot_price_cny_per_kwh"] < values["observed_avg"]:
        warnings.append(
            f"本站加权捕获价 {metrics['weighted_spot_price_cny_per_kwh']:.4f} 元/kWh 低于 2025 现货出清均价 "
            f"{values['observed_avg']:.4f} 元/kWh（B，§4.3）：径流式出力集中于丰水期低价时段，"
            "捕获率低于 1 是水电常态，不能用市场均价测算本站收入"
        )
    if metrics["total_surplus_mwh"] <= 0:
        warnings.append("丰水期无余量，弃水电量消纳情景为空")
    feng_over = [row for row in base["monthly"] if row["season"] == "丰" and row["surplus_mwh"] > 0 and row["spot_price_cny_per_kwh"] > metrics["surplus_price_cny_per_kwh"]]
    if feng_over:
        warnings.append(
            f"{len(feng_over)} 个丰水月份（" + "、".join(row["month"] for row in feng_over)
            + f"）现货价高于弃水消纳价 {metrics['surplus_price_cny_per_kwh']:.4f} 元/kWh（B，§0.1-5），"
            "该月余量走弃水品种反而低于现货，不要把余量都塞进弃水通道"
        )
    if base["best"]["strategy"] != "contract_cfd_surplus":
        warnings.append(f"基准最优策略为 {base['best']['label']}，请复核合同价与弃水价假设")

    fingerprint = hashlib.sha1(
        json.dumps(bundle["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]

    summary = {
        "meta": bundle["meta"],
        "fingerprint": fingerprint,
        "config": {
            "profile_id": values["profile_id"],
            "capacity_mw": values["capacity"],
            "p50_hours": values["p50"],
            "planned_generation_mwh": values["planned"],
            "contract_ratio": metrics["contract_ratio"],
            "contract_season_ratio": values["season_split"],
            "contract_price_cny_per_kwh": values["contract_prices"],
            "season_limit_cny_per_mwh": values["limits_mwh"],
            "surplus_price_cny_per_kwh": values["surplus_price"],
            "observed_2025_spot_cny_per_kwh": {
                "min": values["observed_min"],
                "max": values["observed_max"],
                "avg": values["observed_avg"],
            },
            "spot_declare_limits": {"floor": None, "cap": None, "status": "待核实：草案下限 0、不分水期（C/草案，§4.1）"},
        },
        "volumes": {
            "generation_mwh": metrics["total_generation_mwh"],
            "contract_mwh": metrics["total_contract_mwh"],
            "season_generation": metrics["season_generation"],
            "season_contract": metrics["season_contract"],
            "season_coverage": metrics["season_coverage"],
            "surplus_feng_mwh": metrics["total_surplus_mwh"],
        },
        "prices": {
            "weighted_spot_cny_per_kwh": metrics["weighted_spot_price_cny_per_kwh"],
            "weighted_contract_cny_per_kwh": metrics["weighted_contract_price_cny_per_kwh"],
            "observed_2025_avg_cny_per_kwh": values["observed_avg"],
            "feng_realtime_anchor_cny_per_mwh": values["feng_anchor"],
            "ku_realtime_anchor_cny_per_mwh": values["ku_anchor"],
            "surplus_avg_cny_per_kwh": values["surplus_price"],
        },
        "strategies": [
            {
                "strategy": row["strategy"],
                "label": row["label"],
                "contract_mwh": round(row["contract_mwh"], 2),
                "surplus_mwh": round(row["surplus_mwh"], 2),
                "spot_revenue_cny": round(row["spot_revenue_cny"], 2),
                "hedge_settlement_cny": round(row["hedge_settlement_cny"], 2),
                "surplus_gain_cny": round(row["surplus_gain_cny"], 2),
                "total_revenue_cny": round(row["total_revenue_cny"], 2),
                "net_price_cny_per_kwh": round(row["net_price_cny_per_kwh"], 6),
                "delta_vs_all_spot_cny": round(row["delta_vs_all_spot_cny"], 2),
                "delta_vs_best_cny": round(row["delta_vs_best_cny"], 2),
            }
            for row in base["strategies"]
        ],
        "sensitivity": [
            {
                "case": row["case"],
                "best_strategy": row["best_strategy"],
                "best_net_cny": round(row["best_net_cny"], 2),
                "best_price_cny_per_kwh": round(row["best_price_cny_per_kwh"], 6),
                "delta_vs_base_best_cny": round(row["delta_vs_base_best_cny"], 2),
            }
            for row in sensitivity
        ],
        "warnings": warnings,
        "pending": PENDING_ITEMS,
        "sources": bundle["report"],
        "disclaimer": bundle["meta"]["disclaimer"],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        out_dir / "monthly.csv",
        base["monthly"],
        [
            "month",
            "season",
            "generation_mwh",
            "contract_mwh",
            "hedge_coverage",
            "spot_price_cny_per_kwh",
            "contract_price_cny_per_kwh",
            "spot_revenue_cny",
            "hedge_settlement_cny",
            "surplus_mwh",
            "surplus_gain_cny",
            "all_spot_cny",
            "contract_cfd_cny",
            "contract_surplus_cny",
            "delta_cfd_vs_spot_cny",
            "delta_surplus_vs_spot_cny",
        ],
    )
    write_csv(
        out_dir / "seasons.csv",
        base["seasons"],
        [
            "season",
            "months",
            "generation_mwh",
            "generation_share",
            "contract_mwh",
            "contract_coverage",
            "contract_price_cny_per_kwh",
            "limit_price_cny_per_mwh",
            "limit_headroom_cny_per_mwh",
            "weighted_spot_price_cny_per_kwh",
            "hedge_settlement_cny",
            "surplus_mwh",
            "surplus_gain_cny",
            "net_price_all_spot_cny_per_kwh",
            "net_price_contract_cfd_cny_per_kwh",
        ],
    )
    write_csv(
        out_dir / "strategies.csv",
        base["strategies"],
        [
            "strategy",
            "label",
            "contract_mwh",
            "spot_revenue_cny",
            "hedge_settlement_cny",
            "surplus_mwh",
            "surplus_gain_cny",
            "total_revenue_cny",
            "net_price_cny_per_kwh",
            "delta_vs_all_spot_cny",
            "delta_vs_best_cny",
        ],
    )
    write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        [
            "case",
            "change",
            "all_spot_cny",
            "contract_cfd_cny",
            "contract_surplus_cny",
            "best_strategy",
            "best_net_cny",
            "best_price_cny_per_kwh",
            "delta_vs_base_best_cny",
        ],
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "review.md").write_text(
        render_review(bundle, profile, base, sensitivity),
        encoding="utf-8",
    )
    return summary


def render_review(bundle, profile, base, sensitivity):
    meta = bundle["meta"]
    values = bundle["values"]
    metrics = base["metrics"]
    strategies = base["strategies"]
    best = base["best"]
    all_spot = strategies[0]
    contract_cfd = strategies[1]
    contract_surplus = strategies[2]
    feng, ping, kuy = base["seasons"]

    lines = [
        f"# {meta['province']}水电 · 丰平枯对冲复核表",
        "",
        f"- 实例：`{meta['instance_id']}`（{meta['entity_type']}）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}；除已标注级别的规则事实外，电量、价格、合同比例均为 D 级合成数据",
        "- 市场状态：**连续结算试运行（2025-11 起），未转正式**；中长期纯金融对冲、物理电量按现货价结算（C，§4.2）",
        "",
        "## 1. 结论",
        "",
        f"基准情景的最优策略是 **{best['label']}**：净收入 **{_fmt_wan(best['total_revenue_cny'])} 万元**，"
        f"净价 **{best['net_price_cny_per_kwh']:.4f} 元/kWh**，比全电量现货高 "
        f"**{_fmt_wan(best['delta_vs_all_spot_cny'])} 万元**。",
        f"中长期合同贡献差价结算 **{_fmt_wan(metrics['total_hedge_settlement_cny'])} 万元**：丰水期合同价 "
        f"{values['contract_prices']['丰']:.3f} 元/kWh 托住了 {values['feng_anchor']:.0f} 元/MWh（C 口径）附近的现货低价，"
        f"但 {len(metrics['negative_hedge_months'])} 个月（{'、'.join(metrics['negative_hedge_months'])}）现货冲高越过枯季合同价 "
        f"{values['contract_prices']['枯']:.2f} 元/kWh，让渡上行 {abs(metrics['negative_hedge_total_cny']) / 1e4:,.2f} 万元。",
        f"丰水期余量 {metrics['total_surplus_mwh']:,.0f} MWh 走弃水电量消纳（2025 均价 0.1477 元/kWh，B，§5）"
        f"增益仅 **{_fmt_wan(metrics['total_surplus_gain_cny'])} 万元**：弃水价与丰水期现货价之差很薄，"
        "且现货越过弃水价的月份反而倒挂。结论是：**对冲保护的是丰水期下行，弃水通道只是余量的薄溢价出口**。",
        "",
        "## 2. 电量与价格",
        "",
        "| 项目 | 值 | 级别 |",
        "|---|---:|---|",
        f"| 装机容量 | {values['capacity']:,.0f} MW（径流式，无调节库容） | D |",
        f"| 计划电量（P50） | {metrics['planned_generation_mwh']:,.0f} MWh | D |",
        f"| 实际发电量 | {metrics['total_generation_mwh']:,.0f} MWh | D |",
        f"| 合同电量（{metrics['contract_ratio'] * 100:.0f}%，按丰平枯分期分解） | {metrics['total_contract_mwh']:,.0f} MWh | D（分期比例为 B） |",
        f"| 加权现货捕获价 | {metrics['weighted_spot_price_cny_per_kwh']:.4f} 元/kWh | D |",
        f"| 2025 现货出清均价（109 天试运行） | {values['observed_avg']:.4f} 元/kWh | B（§4.3） |",
        f"| 合同加权价 | {metrics['weighted_contract_price_cny_per_kwh']:.4f} 元/kWh | D |",
        f"| 弃水电量消纳均价（2025） | {values['surplus_price']:.4f} 元/kWh | B（§5） |",
        "",
        f"本站捕获率约 {metrics['weighted_spot_price_cny_per_kwh'] / values['observed_avg']:.2f}："
        "径流式出力集中在丰水期低价时段，捕获价天然低于全市场均价；用 0.2193 元/kWh（B）直接乘电量会高估收入。",
        "",
        "## 3. 丰平枯分解",
        "",
        "| 水期 | 月份 | 发电量 | 占比 | 合同电量 | 覆盖率 | 合同价 | 分期限价（C 口径） | 加权现货价 | 差价结算 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in base["seasons"]:
        lines.append(
            f"| {row['season']} | {row['months']} | {row['generation_mwh']:,.0f} | "
            f"{_fmt_pct(row['generation_share'])} | {row['contract_mwh']:,.0f} | {_fmt_pct(row['contract_coverage'])} | "
            f"{row['contract_price_cny_per_kwh']:.3f} | {row['limit_price_cny_per_mwh']:.2f} 元/MWh | "
            f"{row['weighted_spot_price_cny_per_kwh']:.4f} | {row['hedge_settlement_cny'] / 1e4:+,.2f} 万 |"
        )
    lines.extend(
        [
            "",
            f"按全省常规直购分期比例（45.23/16.73/38.04，B）签出的合同，对丰水期占比 "
            f"{_fmt_pct(feng['generation_share'])} 的径流式机组意味着：枯水期覆盖率 {_fmt_pct(kuy['contract_coverage'])}"
            f"（超对冲）、丰水期仅 {_fmt_pct(feng['contract_coverage'])}（欠对冲）。"
            "**别人的分期比例不是你的分期比例**：签约前必须用本站丰平枯出力形态重排合同曲线。",
            "",
            "## 4. 策略比较",
            "",
            "| 策略 | 合同电量 | 弃水余量 | 差价结算 | 弃水增益 | 净收入（万元） | 净价（元/kWh） | 较全现货（万元） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in strategies:
        lines.append(
            f"| {row['label']} | {row['contract_mwh']:,.0f} | {row['surplus_mwh']:,.0f} | "
            f"{row['hedge_settlement_cny'] / 1e4:+,.2f} | {row['surplus_gain_cny'] / 1e4:+,.2f} | "
            f"{_fmt_wan(row['total_revenue_cny'])} | {row['net_price_cny_per_kwh']:.4f} | "
            f"{row['delta_vs_all_spot_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            f"物理电量全部按现货价结算（中长期纯金融对冲，C，§4.2）：三种策略的现货收入都是 "
            f"{_fmt_wan(metrics['total_spot_revenue_cny'])} 万元，差异只来自差价结算与弃水增益，"
            "不存在\"合同电量按合同价物理交付\"的收入项。",
            "",
            "## 5. 月度明细",
            "",
            "| 月份 | 水期 | 发电量 | 合同 | 覆盖率 | 现货价 | 合同价 | 差价结算 | 弃水余量 | 弃水增益 | 全现货 | 对冲 | 对冲+弃水 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in base["monthly"]:
        lines.append(
            f"| {row['month']} | {row['season']} | {row['generation_mwh']:,.0f} | {row['contract_mwh']:,.0f} | "
            f"{_fmt_pct(row['hedge_coverage'])} | {row['spot_price_cny_per_kwh']:.2f} | "
            f"{row['contract_price_cny_per_kwh']:.3f} | {row['hedge_settlement_cny'] / 1e4:+,.2f} | "
            f"{row['surplus_mwh']:,.0f} | {row['surplus_gain_cny'] / 1e4:+,.2f} | "
            f"{_fmt_wan(row['all_spot_cny'])} | {_fmt_wan(row['contract_cfd_cny'])} | "
            f"{_fmt_wan(row['contract_surplus_cny'])} |"
        )
    lines.extend(
        [
            "",
            "丰水月份覆盖率低、差价结算为正（托底）；12 月与次年 1 月现货冲高越过枯季合同价，差价结算转负（让渡上行）。"
            "现货申报/出清限价不分水期（C/草案，§4.1），丰枯分期限价只约束中长期，不要用限价去预判现货边界。",
            "",
            "## 6. 敏感性",
            "",
            "| 情景 | 全现货 | 中长期对冲 | 对冲+弃水 | 最优策略 | 最优净收入（万元） | 较基准最优（万元） |",
            "|---|---:|---:|---:|---|---:|---:|",
        ]
    )
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {_fmt_wan(row['all_spot_cny'])} | {_fmt_wan(row['contract_cfd_cny'])} | "
            f"{_fmt_wan(row['contract_surplus_cny'])} | {row['best_strategy']} | "
            f"{_fmt_wan(row['best_net_cny'])} | {row['delta_vs_base_best_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            "在本包合成数据下，现货整体上涨 30% 时全现货策略反超：锁价合同让渡的上行超过丰水托底的价值；"
            "而现货整体下跌 20%、丰水期现货崩塌或来水枯年时，对冲加弃水的组合最能托底。"
            "对冲比例是风险偏好问题——丰水期占比越高的径流式机组，越应该把合同电量堆在丰水期，而不是照抄全省分期比例。",
            "",
            "## 7. 口径提醒",
            "",
            "- **连续结算试运行 ≠ 正式运行**：2025-11 起连续结算试运行（B，§0.1-1），截至 2026-11-12 未核到转正文件。",
            "- **日前预出清不结算**：征求意见稿架构为日前预出清不结算、日内全时段滚动优化、实时出清并结算（C/草案，§3.1）；"
            "日前价不能当结算依据。",
            "- **丰枯分期是中长期口径**：中长期限价丰 211.43 / 平 333.84 / 枯 415.63 / 月内滚动 481.44 元/MWh 为行业口径（C，§4.1，待省级确认）；"
            "现货申报/出清限价不分水期，2026 下限暂设 0（C/草案），本包限价字段一律置空。",
            "- **中长期是金融对冲**：物理电量按现货价结算，合同结算差价（C，§4.2）；本包把差价结算简化为"
            " `合同电量 × (合同价 − 当月现货价)`，未建模 24 时段带曲线（V4.0 行业口径，C，§5）与分时结构。",
            "- **弃水电量消纳是独有品种**：2025 成交 105.72 亿 kWh、均价 0.1477 元/kWh、丰平比 86.42%/13.58%（B，§5）；"
            "本包只对丰水期余量建模（D 级简化），成交价与组织方式以当年公告为准。",
            "- **径流式\"不弃水\"是调度原则不是价格保证**（B，§4.2）：不代表全部水电按固定价结算。",
            "- 偏差考核与 291 号文收益回收（发电侧 85%/115%，C 行业口径，§5）未纳入本包；真实签约前须核对结算细则正式文本。",
            "- 本包不构成报价、投资或法律建议；丰枯打捆省间外送（2026-03 超 67 亿 kWh，A，§2）属省间市场，不在本包范围内。",
            "",
            f"风格指纹 `{hashlib.sha1(json.dumps(bundle['policy'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()[:12]}`；"
            "本复核表由 `run.py` 生成。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="四川 300 MW 径流式水电丰平枯对冲实例")
    parser.add_argument("--instance", type=Path, default=HERE / "instance.json")
    parser.add_argument("--profile", type=Path, help="月度电量与价格 CSV（含水期列）；--demo 时省略")
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
        print("配置校验通过")
        print(f"实例: {bundle['meta']['instance_id']} · {bundle['meta']['province']} · {bundle['meta']['market']}")
        print(f"规则版本: {bundle['meta']['rule_version']}")
        print(f"风格: {values['profile_id']}")
        print(f"合同比例: {values['ratio']:.0%}；分期比例（B，§5）: " + "/".join(f"{values['season_split'][s]:.2%}" for s in SEASONS))
        for season in SEASONS:
            print(
                f"  {season}季合同价 {values['contract_prices'][season]:.3f} 元/kWh"
                f" ≤ 分期限价 {values['limits_mwh'][season]:.2f} 元/MWh（C 行业口径，待省级确认）"
            )
        print(
            f"弃水电量消纳价: {values['surplus_price']:.4f} 元/kWh（B，§5）；"
            f"丰平比 {values['feng_share']:.2%}/{values['ping_share']:.2%}"
        )
        print(
            f"现货申报/出清限价: 待核实（草案不分水期、2026 下限暂设 0，C/草案，§4.1）；"
            f"2025 实测区间 {values['observed_min']:.2f} ~ {values['observed_max']:.2f} 元/kWh（B，§4.1）仅作数据合理性边界"
        )
        print("规则来源:")
        for row in bundle["report"]:
            print(f"  - {row['block']} [{row['grade']}] {row['source'][:88]}")
        print(f"待核实项: {len(PENDING_ITEMS)} 条")
        for item in PENDING_ITEMS:
            print(f"  - {item[:96]}")
        return 0

    if args.profile is not None:
        profile_path = args.profile
    elif args.demo:
        profile_path = HERE / bundle["profile"]["file"]
    else:
        print("请用 --profile 指定月度电量与价格 CSV，或加 --demo 使用合成数据", file=sys.stderr)
        return 2

    try:
        profile = load_profile(profile_path, bundle)
        out_dir = args.out / "demo" if args.demo else args.out
        summary = build_outputs(bundle, profile, out_dir)
    except ConfigError as exc:
        print(f"数据错误: {exc}", file=sys.stderr)
        return 2

    best = next(row for row in summary["strategies"] if row["delta_vs_best_cny"] == 0.0)
    print(f"输出目录: {out_dir}")
    print(f"发电量 / 合同电量: {summary['volumes']['generation_mwh']:,.0f} / {summary['volumes']['contract_mwh']:,.0f} MWh")
    print(
        f"加权现货捕获价: {summary['prices']['weighted_spot_cny_per_kwh']:.4f} 元/kWh"
        f"（2025 现货均价锚 {summary['prices']['observed_2025_avg_cny_per_kwh']:.4f}，B）"
    )
    print(f"差价结算合计: {summary['strategies'][1]['hedge_settlement_cny'] / 1e4:+,.2f} 万元；弃水增益: {summary['strategies'][2]['surplus_gain_cny'] / 1e4:+,.2f} 万元")
    print(f"最优策略: {best['label']} · {best['total_revenue_cny'] / 1e4:,.2f} 万元 · {best['net_price_cny_per_kwh']:.4f} 元/kWh")
    for warning in summary["warnings"]:
        print(f"警告: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
