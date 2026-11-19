#!/usr/bin/env python3
"""Run the Yunnan two-reservoir / three-station cascade hydro case.

The engine is shared, the instance is local:

* ``instance.json`` holds the regional-spot, bidding, mid/long-term,
  settlement, coal-capacity, green-certificate, mechanism and
  regulation-capacity rule blocks (each with grade + source), the cascade
  asset and the portfolio style.
* ``data/profile_demo.csv`` is a synthetic hydro year: monthly generation,
  the flat annual-average contract weight (1/12), the wet/dry seasonal
  contract weight, the monthly intra-provincial contract price and the
  green-certificate share of generation.
* ``data/price_shapes_demo.csv`` holds two synthetic Southern-regional
  15-minute price shapes (wet / dry season), 96 slots per day, plus the
  within-day generation distribution used to weight the time-average price
  into a generation-weighted capture price.

The runner contrasts three portfolios: sell everything into the regional
spot at the generation-weighted capture price, sign a 75% intra-provincial
mid/long-term contract decomposed flat across months, or decompose it on a
wet/dry seasonal curve. Surplus and shortfall settle at the 15-minute
capture price, which is deliberately contrasted with the time-weighted
average price — the 96-point mismatch between monthly contract volumes and
15-minute regional clearing. Green certificates are booked as a separate
line and never stacked on mechanism-differential energy; the regulation
capacity market stays a zero placeholder.

All bundled numbers are synthetic grade D. They are not a trading
instruction or investment advice. Regional formal operation (2026-10-24)
does not mean the Yunnan provincial spot market has formally started.
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
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SEASON_BY_MONTH = {m: ("wet" if 6 <= m <= 10 else "dry") for m in range(1, 13)}
SEASON_LABELS = {"wet": "汛期（6–10 月）", "dry": "枯期（11–5 月）"}
STRATEGIES = ("all_spot", "contract_flat", "contract_seasonal")
LABELS = {
    "all_spot": "全部现货（不签中长期）",
    "contract_flat": "中长期平推 + 现货余量",
    "contract_seasonal": "中长期丰枯曲线 + 现货余量",
}
# 合理性检查上限（不是省级限价——省内限价待核实，不得填值）
PRICE_SANITY_CAP_CNY_PER_MWH = 2000.0


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


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    if not isinstance(block, dict):
        raise ConfigError(f"rules.{name} 必须是对象")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report.append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block


def _must_be_null(block, key, path, reason):
    value = block.get(key, None)
    if value is not None:
        raise ConfigError(f"{path}.{key} 必须保持 null（{reason}），不得填值")
    return None


def _must_be_true(block, key, path, reason):
    value = block.get(key, None)
    if value is not True:
        raise ConfigError(f"{path}.{key} 必须为 true（{reason}）")
    return True


def _must_be_false(block, key, path, reason):
    value = block.get(key, None)
    if value is not False:
        raise ConfigError(f"{path}.{key} 必须为 false（{reason}）")
    return False


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

    rules = _need(config, "rules", "instance")
    report = []
    regional_spot = _rule_block(rules, "regional_spot", report)
    bidding = _rule_block(rules, "bidding", report)
    mid_long_term = _rule_block(rules, "mid_long_term", report)
    settlement = _rule_block(rules, "settlement", report)
    coal_capacity = _rule_block(rules, "coal_capacity", report)
    green_cert = _rule_block(rules, "green_cert", report)
    mechanism = _rule_block(rules, "mechanism", report)
    regulation_capacity = _rule_block(rules, "regulation_capacity", report)

    # 区域现货：15 分钟、96 点、一地注册全域交易；区域正式 ≠ 省内转正；
    # 省内限价待核实，不得填值。
    interval = _number(_need(regional_spot, "price_interval_minutes", "rules.regional_spot"), "rules.regional_spot.price_interval_minutes", 1.0, 60.0)
    points = _number(_need(regional_spot, "points_per_day", "rules.regional_spot"), "rules.regional_spot.points_per_day", 1.0, 1440.0)
    if points != 24.0 * 60.0 / interval:
        raise ConfigError("rules.regional_spot.points_per_day 必须等于 24×60/price_interval_minutes（15 分钟 = 96 点）")
    _text(regional_spot, "formal_since", "rules.regional_spot")
    _text(regional_spot, "registration", "rules.regional_spot")
    _must_be_false(
        regional_spot,
        "provincial_spot_formal",
        "rules.regional_spot",
        "区域正式运行不等于云南省内现货转正，省内仍是配合区域连续结算试运行（B）",
    )
    _must_be_null(regional_spot, "provincial_spot_price_cap_cny_per_mwh", "rules.regional_spot", "云南省内现货限价待核实，不得填值，更不得套广东/广西限价")

    # 竞价：水火风光同台；日前按 96 点建模，与区域价格粒度一致。
    _must_be_true(bidding, "multi_energy_same_platform", "rules.bidding", "「水火风光」多能同台竞价（B）")
    _text(bidding, "hydro_pricing", "rules.bidding")
    _text(bidding, "coal_pricing", "rules.bidding")
    model_points = _number(_need(bidding, "model_points_per_day", "rules.bidding"), "rules.bidding.model_points_per_day", 1.0, 1440.0)
    if model_points != points:
        raise ConfigError("rules.bidding.model_points_per_day 必须与区域 15 分钟价格粒度一致（96 点）")

    # 中长期：偏差公式待核实，不得填值。
    _text(mid_long_term, "framework", "rules.mid_long_term")
    _must_be_null(mid_long_term, "deviation_formula", "rules.mid_long_term", "云南省级偏差考核公式待核实（昆明交易函〔2026〕71号仍为草案）")

    # 结算：煤电容量电费分摊不适用于水电主体。
    _text(settlement, "basis", "rules.settlement")
    _must_be_false(settlement, "applies_to_hydro", "rules.settlement", "本主体为水电，不涉及煤电容量电费分摊")

    # 煤电容量电价 330 元/kW·年是煤电专属，不得套水电。
    coal_price = _number(_need(coal_capacity, "price_cny_per_kw_year", "rules.coal_capacity"), "rules.coal_capacity.price_cny_per_kw_year", 0.0)
    recovery = _number(_need(coal_capacity, "recovery_ratio", "rules.coal_capacity"), "rules.coal_capacity.recovery_ratio", 0.0, 1.0)
    _text(coal_capacity, "effective_from", "rules.coal_capacity")
    _must_be_false(coal_capacity, "applies_to_hydro", "rules.coal_capacity", "330 元/kW·年是煤电容量电价（A），水电与储能不得套用")
    if coal_price <= 0 or recovery <= 0:
        raise ConfigError("rules.coal_capacity 价格与回收比例必须为正")

    # 绿证：无偿划转不是发电侧收入；与机制差价结算防重。
    _text(green_cert, "aggregate_certificates_transferred", "rules.green_cert")
    _text(green_cert, "aggregate_energy", "rules.green_cert")
    _must_be_false(green_cert, "transfer_creates_producer_revenue", "rules.green_cert", "存量常规水电绿证无偿划转面向受惠企业，不构成发电侧销售收入")
    _must_be_true(green_cert, "double_count_guard_with_mechanism", "rules.green_cert", "绿证收益与机制电量差价结算不能重复计算（B）")

    # 机制差价：常规水电参数待核实，不得填值。
    _must_be_null(mechanism, "hydro_mechanism_price_cny_per_kwh", "rules.mechanism", "模块未给常规水电机制差价结算参数（136 机制电价仅覆盖光伏/风电）")
    _must_be_null(mechanism, "hydro_mechanism_ratio", "rules.mechanism", "常规水电机制电量比例待核实")

    # 调节容量市场：水电补偿标准待核实，不得填值。
    _must_be_null(regulation_capacity, "hydro_compensation_cny_per_kw_year", "rules.regulation_capacity", "水电调节容量补偿标准待核实，不得套煤电 330 元/kW·年")
    _must_be_null(regulation_capacity, "hydro_access_threshold", "rules.regulation_capacity", "水电参与调节容量市场的准入门槛待核实")

    project = _need(config, "project", "instance")
    _text(project, "name", "project")
    stations = _need(project, "stations", "project")
    if not isinstance(stations, list) or len(stations) < 2:
        raise ConfigError("project.stations 必须是至少两级电站的列表")
    station_total = 0.0
    for index, station in enumerate(stations, start=1):
        _text(station, "id", f"project.stations[{index}]")
        _text(station, "name", f"project.stations[{index}]")
        station_capacity = _number(_need(station, "capacity_mw", f"project.stations[{index}]"), f"project.stations[{index}].capacity_mw", 0.0)
        _text(station, "regulation", f"project.stations[{index}]")
        if station_capacity <= 0:
            raise ConfigError(f"project.stations[{index}].capacity_mw 必须为正")
        station_total += station_capacity
    reservoirs = _number(_need(project, "reservoirs", "project"), "project.reservoirs", 1.0, 20.0)
    capacity = _number(_need(project, "capacity_mw", "project"), "project.capacity_mw", 0.0)
    p50 = _number(_need(project, "p50_hours", "project"), "project.p50_hours", 0.0, 8760.0)
    planned_declared = _number(_need(project, "planned_generation_mwh", "project"), "project.planned_generation_mwh", 0.0)
    cod = _text(project, "cod", "project")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", cod):
        raise ConfigError("project.cod 必须是 YYYY-MM-DD")
    _grade(project, "project")
    _text(project, "source", "project")
    if capacity <= 0 or p50 <= 0 or planned_declared <= 0:
        raise ConfigError("装机容量、P50 小时数与计划年电量必须为正")
    if abs(station_total - capacity) > 0.5:
        raise ConfigError(f"project.capacity_mw ({capacity:,.1f}) 必须等于梯级各站装机之和 ({station_total:,.1f})")
    planned_hours = capacity * p50
    if abs(planned_declared - planned_hours) > 0.005 * planned_hours:
        raise ConfigError(f"project.planned_generation_mwh ({planned_declared:,.0f}) 必须等于 capacity_mw × p50_hours ({planned_hours:,.0f})")

    policy = _need(config, "policy", "instance")
    profile_id = _text(policy, "profile_id", "policy")
    ratio = _number(_need(policy, "contract_ratio", "policy"), "policy.contract_ratio", 0.0, 1.0)
    strategies = _need(policy, "strategies", "policy")
    if not isinstance(strategies, list) or set(strategies) != set(STRATEGIES):
        raise ConfigError("policy.strategies 必须包含 all_spot / contract_flat / contract_seasonal 三项")
    shortfall = _text(policy, "shortfall_settlement", "policy")
    if shortfall != "regional_spot_capture":
        raise ConfigError("policy.shortfall_settlement 只实现 regional_spot_capture（偏差按区域现货捕获价价差结算）")
    cert_price = _number(_need(policy, "green_cert_price_cny_per_certificate", "policy"), "policy.green_cert_price_cny_per_certificate", 0.0)
    mech_ratio = _number(_need(policy, "mechanism_ratio", "policy"), "policy.mechanism_ratio", 0.0, 1.0)
    regulation_placeholder = _number(_need(policy, "regulation_capacity_placeholder_cny", "policy"), "policy.regulation_capacity_placeholder_cny", 0.0)
    _text(policy, "decision_rule", "policy")
    _grade(policy, "policy")

    contract = _need(config, "data_contract", "instance")
    profile = _need(contract, "profile", "data_contract")
    _text(profile, "file", "data_contract.profile")
    profile_fields = _need(profile, "fields", "data_contract.profile")
    required_profile = {"month", "season", "generation_mwh", "contract_weight", "seasonal_weight", "contract_price_cny_per_kwh", "green_ratio"}
    if not isinstance(profile_fields, list) or not required_profile.issubset(set(profile_fields)):
        raise ConfigError("data_contract.profile.fields 必须包含 month / season / generation_mwh / contract_weight / seasonal_weight / contract_price_cny_per_kwh / green_ratio")
    shapes = _need(contract, "price_shapes", "data_contract")
    _text(shapes, "file", "data_contract.price_shapes")
    shape_fields = _need(shapes, "fields", "data_contract.price_shapes")
    required_shape = {"season", "slot", "price_cny_per_mwh", "generation_share"}
    if not isinstance(shape_fields, list) or not required_shape.issubset(set(shape_fields)):
        raise ConfigError("data_contract.price_shapes.fields 必须包含 season / slot / price_cny_per_mwh / generation_share")

    return {
        "config": config,
        "report": report,
        "meta": meta,
        "regional_spot": regional_spot,
        "bidding": bidding,
        "mid_long_term": mid_long_term,
        "settlement": settlement,
        "coal_capacity": coal_capacity,
        "green_cert": green_cert,
        "mechanism": mechanism,
        "regulation_capacity": regulation_capacity,
        "project": project,
        "policy": policy,
        "profile": profile,
        "shapes": shapes,
        "values": {
            "interval_minutes": interval,
            "points_per_day": points,
            "coal_price": coal_price,
            "recovery": recovery,
            "capacity": capacity,
            "p50": p50,
            "planned_declared": planned_declared,
            "reservoirs": reservoirs,
            "stations": stations,
            "ratio": ratio,
            "cert_price": cert_price,
            "mechanism_ratio": mech_ratio,
            "regulation_placeholder": regulation_placeholder,
            "profile_id": profile_id,
        },
    }


def load_profile(path, bundle):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = reader.fieldnames or []
    except FileNotFoundError as exc:
        raise ConfigError(f"profile 文件不存在: {path}") from exc
    except csv.Error as exc:
        raise ConfigError(f"profile CSV 解析失败: {exc}") from exc

    for field in ("month", "season", "generation_mwh", "contract_weight", "seasonal_weight", "contract_price_cny_per_kwh", "green_ratio"):
        if field not in fields:
            raise ConfigError(f"profile CSV 缺少字段 {field}")
    if len(rows) != 12:
        raise ConfigError(f"profile 必须包含 12 个月，实际 {len(rows)} 行")

    months, seasons, generation, flat_weights, seasonal_weights, contract_prices, green_ratios = [], [], [], [], [], [], []
    for index, row in enumerate(rows, start=2):
        month = (row.get("month") or "").strip()
        if not MONTH_RE.match(month):
            raise ConfigError(f"profile 第 {index} 行 month 不是 YYYY-MM")
        if month in months:
            raise ConfigError(f"profile 第 {index} 行 month 重复: {month}")
        season = (row.get("season") or "").strip()
        canonical = SEASON_BY_MONTH[int(month.split("-")[1])]
        if season != canonical:
            raise ConfigError(
                f"profile 第 {index} 行 season={season!r} 与云南丰枯口径不符（{month} 应为 {canonical}：汛期 6–10 月 / 枯期 11–5 月）"
            )
        gen = _number(float(row["generation_mwh"]), f"profile 第 {index} 行 generation_mwh", 0.0)
        flat_w = _number(float(row["contract_weight"]), f"profile 第 {index} 行 contract_weight", 0.0, 1.0)
        seasonal_w = _number(float(row["seasonal_weight"]), f"profile 第 {index} 行 seasonal_weight", 0.0, 1.0)
        price = _number(float(row["contract_price_cny_per_kwh"]), f"profile 第 {index} 行 contract_price_cny_per_kwh", 0.0, 2.0)
        green = _number(float(row["green_ratio"]), f"profile 第 {index} 行 green_ratio", 0.0, 1.0)
        if gen <= 0:
            raise ConfigError(f"profile 第 {index} 行 generation_mwh 必须为正")
        if price <= 0:
            raise ConfigError(f"profile 第 {index} 行 contract_price_cny_per_kwh 必须为正")
        months.append(month)
        seasons.append(season)
        generation.append(gen)
        flat_weights.append(flat_w)
        seasonal_weights.append(seasonal_w)
        contract_prices.append(price)
        green_ratios.append(green)

    if len({month.split("-")[0] for month in months}) != 1:
        raise ConfigError("profile 必须覆盖同一个自然年")
    if months != sorted(months):
        raise ConfigError("profile 必须按月份升序排列")
    if abs(sum(flat_weights) - 1.0) > 1e-3:
        raise ConfigError(f"contract_weight 合计必须为 1，实际 {sum(flat_weights):.6f}")
    if abs(sum(seasonal_weights) - 1.0) > 1e-3:
        raise ConfigError(f"seasonal_weight 合计必须为 1，实际 {sum(seasonal_weights):.6f}")

    total = sum(generation)
    planned = bundle["values"]["planned_declared"]
    warnings = []
    if not 0.8 * planned <= total <= 1.2 * planned:
        warnings.append(
            f"年度发电量 {total:,.0f} MWh 偏离计划电量 {planned:,.0f} MWh 超过 20%，请核对来水数据"
        )
    return {
        "months": months,
        "seasons": seasons,
        "generation": generation,
        "flat_weights": flat_weights,
        "seasonal_weights": seasonal_weights,
        "contract_prices": contract_prices,
        "green_ratios": green_ratios,
        "total_generation": total,
        "planned_generation": planned,
        "warnings": warnings,
    }


def load_shapes(path, bundle):
    points_per_day = int(bundle["values"]["points_per_day"])
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = reader.fieldnames or []
    except FileNotFoundError as exc:
        raise ConfigError(f"price_shapes 文件不存在: {path}") from exc
    except csv.Error as exc:
        raise ConfigError(f"price_shapes CSV 解析失败: {exc}") from exc

    for field in ("season", "slot", "price_cny_per_mwh", "generation_share"):
        if field not in fields:
            raise ConfigError(f"price_shapes CSV 缺少字段 {field}")

    shapes = {}
    for index, row in enumerate(rows, start=2):
        season = (row.get("season") or "").strip()
        if season not in ("wet", "dry"):
            raise ConfigError(f"price_shapes 第 {index} 行 season 必须是 wet 或 dry，实际 {season!r}")
        slot = int(float(row["slot"]))
        if not 0 <= slot < points_per_day:
            raise ConfigError(f"price_shapes 第 {index} 行 slot 越界（0–{points_per_day - 1}）: {slot}")
        price = _number(float(row["price_cny_per_mwh"]), f"price_shapes 第 {index} 行 price_cny_per_mwh", 0.0, PRICE_SANITY_CAP_CNY_PER_MWH)
        share = _number(float(row["generation_share"]), f"price_shapes 第 {index} 行 generation_share", 0.0, 1.0)
        bucket = shapes.setdefault(season, {"slots": {}, "prices": {}, "shares": {}})
        if slot in bucket["slots"]:
            raise ConfigError(f"price_shapes {season} 季 slot {slot} 重复")
        bucket["slots"][slot] = True
        bucket["prices"][slot] = price
        bucket["shares"][slot] = share

    missing = {"wet", "dry"} - set(shapes)
    if missing:
        raise ConfigError(f"price_shapes 缺少季节形态: {'、'.join(sorted(missing))}")
    for season, bucket in shapes.items():
        if sorted(bucket["slots"]) != list(range(points_per_day)):
            raise ConfigError(f"price_shapes {season} 季必须覆盖 0–{points_per_day - 1} 全部 {points_per_day} 个 15 分钟槽，不得有缺口")
        share_sum = sum(bucket["shares"].values())
        if abs(share_sum - 1.0) > 1e-3:
            raise ConfigError(f"price_shapes {season} 季 generation_share 合计必须为 1，实际 {share_sum:.6f}")
        bucket["prices"] = [bucket["prices"][s] for s in range(points_per_day)]
        bucket["shares"] = [bucket["shares"][s] for s in range(points_per_day)]
    return shapes


def compute(bundle, profile, shapes, overrides=None):
    overrides = overrides or {}
    values = bundle["values"]
    ratio = overrides.get("contract_ratio", values["ratio"])
    price_delta = overrides.get("contract_price_delta", 0.0)
    spot_scale = overrides.get("spot_scale", 1.0)
    wet_spot_scale = spot_scale * overrides.get("wet_spot_scale", 1.0)
    dry_spot_scale = spot_scale * overrides.get("dry_spot_scale", 1.0)
    wet_gen_scale = overrides.get("wet_gen_scale", 1.0)
    dry_gen_scale = overrides.get("dry_gen_scale", 1.0)
    cert_price = values["cert_price"] * overrides.get("cert_price_scale", 1.0)
    if "cert_price" in overrides:
        cert_price = overrides["cert_price"]
    mech_ratio = overrides.get("mechanism_ratio", values["mechanism_ratio"])
    use_average = overrides.get("use_average_price", False)
    planned = profile["planned_generation"]
    regulation_monthly = values["regulation_placeholder"] / 12.0

    monthly = []
    for month, season, gen0, flat_w, seasonal_w, cp0, green in zip(
        profile["months"],
        profile["seasons"],
        profile["generation"],
        profile["flat_weights"],
        profile["seasonal_weights"],
        profile["contract_prices"],
        profile["green_ratios"],
    ):
        prices = shapes[season]["prices"]
        shares = shapes[season]["shares"]
        scale = wet_spot_scale if season == "wet" else dry_spot_scale
        scaled_prices = [p * scale for p in prices]
        avg_price = sum(scaled_prices) / len(scaled_prices)
        capture_price_m = sum(p * s for p, s in zip(scaled_prices, shares))
        settle_price = avg_price if use_average else capture_price_m
        gen = gen0 * (wet_gen_scale if season == "wet" else dry_gen_scale)
        cp = cp0 + price_delta

        flat_contract = planned * ratio * flat_w
        seasonal_contract = planned * ratio * seasonal_w

        green_generation = gen * green
        mechanism_energy = gen * mech_ratio
        green_base = max(green_generation - mechanism_energy, 0.0)
        green_revenue = green_base * cert_price  # 1 张 = 1 MWh
        mechanism_excluded = green_generation - green_base

        rows = {}
        contract_by_strategy = {"all_spot": 0.0, "contract_flat": flat_contract, "contract_seasonal": seasonal_contract}
        for strategy in STRATEGIES:
            contract_mwh = contract_by_strategy[strategy]
            own = min(gen, contract_mwh)
            surplus = max(gen - contract_mwh, 0.0)
            shortfall = max(contract_mwh - gen, 0.0)
            contract_revenue = own * cp * 1000.0
            spot_revenue = surplus * settle_price
            shortfall_cost = shortfall * settle_price
            total = contract_revenue + spot_revenue - shortfall_cost + green_revenue + regulation_monthly
            rows[strategy] = {
                "contract_mwh": contract_mwh,
                "own_contract_mwh": own,
                "surplus_mwh": surplus,
                "shortfall_mwh": shortfall,
                "contract_revenue_cny": contract_revenue,
                "spot_surplus_cny": spot_revenue,
                "shortfall_cost_cny": shortfall_cost,
                "green_cert_cny": green_revenue,
                "regulation_capacity_cny": regulation_monthly,
                "total_revenue_cny": total,
            }

        monthly.append(
            {
                "month": month,
                "season": season,
                "season_label": SEASON_LABELS[season],
                "generation_mwh": gen,
                "contract_price_cny_per_kwh": cp,
                "avg_price_cny_per_mwh": avg_price,
                "capture_price_cny_per_mwh": capture_price_m,
                "settle_price_cny_per_mwh": settle_price,
                "capture_minus_avg_cny_per_mwh": capture_price_m - avg_price,
                "green_base_mwh": green_base,
                "mechanism_excluded_mwh": mechanism_excluded,
                "green_cert_cny": green_revenue,
                "regulation_capacity_cny": regulation_monthly,
                "contract_flat_mwh": flat_contract,
                "contract_seasonal_mwh": seasonal_contract,
                "all_spot_cny": rows["all_spot"]["total_revenue_cny"],
                "contract_flat_cny": rows["contract_flat"]["total_revenue_cny"],
                "contract_seasonal_cny": rows["contract_seasonal"]["total_revenue_cny"],
                "delta_flat_vs_all_spot_cny": rows["contract_flat"]["total_revenue_cny"] - rows["all_spot"]["total_revenue_cny"],
                "delta_seasonal_vs_all_spot_cny": rows["contract_seasonal"]["total_revenue_cny"] - rows["all_spot"]["total_revenue_cny"],
                "detail": rows,
            }
        )

    total_generation = sum(row["generation_mwh"] for row in monthly)
    total_green_base = sum(row["green_base_mwh"] for row in monthly)
    total_mechanism_excluded = sum(row["mechanism_excluded_mwh"] for row in monthly)
    total_green_revenue = sum(row["green_cert_cny"] for row in monthly)

    strategies = []
    for strategy in STRATEGIES:
        contract_mwh = sum(row["detail"][strategy]["contract_mwh"] for row in monthly)
        own_mwh = sum(row["detail"][strategy]["own_contract_mwh"] for row in monthly)
        surplus_mwh = sum(row["detail"][strategy]["surplus_mwh"] for row in monthly)
        shortfall_mwh = sum(row["detail"][strategy]["shortfall_mwh"] for row in monthly)
        contract_revenue = sum(row["detail"][strategy]["contract_revenue_cny"] for row in monthly)
        spot_revenue = sum(row["detail"][strategy]["spot_surplus_cny"] for row in monthly)
        shortfall_cost = sum(row["detail"][strategy]["shortfall_cost_cny"] for row in monthly)
        regulation = sum(row["detail"][strategy]["regulation_capacity_cny"] for row in monthly)
        total = contract_revenue + spot_revenue - shortfall_cost + total_green_revenue + regulation
        strategies.append(
            {
                "strategy": strategy,
                "label": LABELS[strategy],
                "contract_mwh": contract_mwh,
                "own_contract_mwh": own_mwh,
                "surplus_mwh": surplus_mwh,
                "shortfall_mwh": shortfall_mwh,
                "contract_revenue_cny": contract_revenue,
                "spot_surplus_cny": spot_revenue,
                "shortfall_cost_cny": shortfall_cost,
                "green_cert_cny": total_green_revenue,
                "regulation_capacity_cny": regulation,
                "total_revenue_cny": total,
                "net_price_cny_per_kwh": total / (total_generation * 1000.0) if total_generation > 0 else 0.0,
            }
        )
    best = max(strategies, key=lambda row: row["total_revenue_cny"])
    for row in strategies:
        row["delta_vs_all_spot_cny"] = row["total_revenue_cny"] - strategies[0]["total_revenue_cny"]
        row["delta_vs_best_cny"] = row["total_revenue_cny"] - best["total_revenue_cny"]

    season_metrics = {}
    for season in ("wet", "dry"):
        rows = [row for row in monthly if row["season"] == season]
        season_gen = sum(row["generation_mwh"] for row in rows)
        season_metrics[season] = {
            "generation_mwh": season_gen,
            "capture_price_cny_per_mwh": capture_price(
                [row["capture_price_cny_per_mwh"] for row in rows],
                [row["generation_mwh"] for row in rows],
            )
            if season_gen > 0
            else 0.0,
            "avg_price_cny_per_mwh": capture_price(
                [row["avg_price_cny_per_mwh"] for row in rows],
                [row["generation_mwh"] for row in rows],
            )
            if season_gen > 0
            else 0.0,
        }
    for metrics in season_metrics.values():
        metrics["capture_minus_avg_cny_per_mwh"] = metrics["capture_price_cny_per_mwh"] - metrics["avg_price_cny_per_mwh"]

    annual_capture = capture_price(
        [row["capture_price_cny_per_mwh"] for row in monthly],
        [row["generation_mwh"] for row in monthly],
    )
    annual_avg = capture_price(
        [row["avg_price_cny_per_mwh"] for row in monthly],
        [row["generation_mwh"] for row in monthly],
    )
    average_price_error_cny = sum(
        row["generation_mwh"] * (row["capture_price_cny_per_mwh"] - row["avg_price_cny_per_mwh"])
        for row in monthly
    )

    metrics = {
        "total_generation_mwh": total_generation,
        "planned_generation_mwh": planned,
        "contract_ratio": ratio,
        "green_base_mwh": total_green_base,
        "mechanism_excluded_mwh": total_mechanism_excluded,
        "green_cert_revenue_cny": total_green_revenue,
        "cert_price_cny_per_certificate": cert_price,
        "mechanism_ratio": mech_ratio,
        "regulation_capacity_cny": values["regulation_placeholder"],
        "use_average_price": use_average,
        "season_metrics": season_metrics,
        "annual_capture_cny_per_mwh": annual_capture,
        "annual_avg_cny_per_mwh": annual_avg,
        "annual_capture_minus_avg_cny_per_mwh": annual_capture - annual_avg,
        "average_price_error_cny": average_price_error_cny,
        "contract_price_delta": price_delta,
        "spot_scale": spot_scale,
        "wet_gen_scale": wet_gen_scale,
        "dry_gen_scale": dry_gen_scale,
    }
    return {
        "monthly": monthly,
        "strategies": strategies,
        "best": best,
        "metrics": metrics,
    }


def build_sensitivity(bundle, profile, shapes, base):
    base_best = base["best"]["total_revenue_cny"]
    cases = [
        ("基准", "75% 中长期（平推与丰枯曲线对比）+ 余量现货", {}),
        ("丰水年（汛期电量 +15%）", "汛期发电量上调 15%，合同电量不变", {"wet_gen_scale": 1.15}),
        ("枯水年（汛期电量 −20%）", "汛期发电量下调 20%，合同电量不变", {"wet_gen_scale": 0.80}),
        ("枯期电量 −10%", "枯期发电量下调 10%（来水偏枯或检修）", {"dry_gen_scale": 0.90}),
        ("区域现货 +30%", "丰枯两套 96 点价格整体上浮 30%", {"spot_scale": 1.30}),
        ("区域现货 −30%", "丰枯两套 96 点价格整体下调 30%", {"spot_scale": 0.70}),
        ("汛期压价 −20%", "仅汛期 96 点价格下调 20%（大发压价）", {"wet_spot_scale": 0.80}),
        ("合同价 +0.02", "各月中长期合同价上调 0.02 元/kWh", {"contract_price_delta": 0.02}),
        ("合同价 −0.02", "各月中长期合同价下调 0.02 元/kWh", {"contract_price_delta": -0.02}),
        ("合同比例 60%", "中长期锁量由 75% 降至 60%", {"contract_ratio": 0.60}),
        ("合同比例 85%", "中长期锁量由 75% 升至 85%", {"contract_ratio": 0.85}),
        ("绿证单价 +50%", "绿证单价由 15 元/张升至 22.5 元/张", {"cert_price_scale": 1.5}),
        ("绿证单价 0", "绿证收入归零（无偿划转口径）", {"cert_price": 0.0}),
        ("机制电量 10%", "假设 10% 电量走机制差价结算，绿证基数防重扣减", {"mechanism_ratio": 0.10}),
        ("均价替代捕获价", "用时间均价代替 96 点发电加权捕获价（错位演示）", {"use_average_price": True}),
    ]
    rows = []
    for name, change, overrides in cases:
        result = compute(bundle, profile, shapes, overrides)
        best = result["best"]
        rows.append(
            {
                "case": name,
                "change": change,
                "all_spot_cny": result["strategies"][0]["total_revenue_cny"],
                "contract_flat_cny": result["strategies"][1]["total_revenue_cny"],
                "contract_seasonal_cny": result["strategies"][2]["total_revenue_cny"],
                "best_strategy": best["label"],
                "best_net_cny": best["total_revenue_cny"],
                "best_price_cny_per_kwh": best["net_price_cny_per_kwh"],
                "delta_vs_base_best_cny": best["total_revenue_cny"] - base_best,
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


def build_price_rows(bundle, base):
    values = bundle["values"]
    metrics = base["metrics"]
    wet = metrics["season_metrics"]["wet"]
    dry = metrics["season_metrics"]["dry"]
    mech = bundle["config"]["rules"]["mechanism"]
    reg = bundle["config"]["rules"]["regulation_capacity"]
    coal = bundle["config"]["rules"]["coal_capacity"]
    green = bundle["config"]["rules"]["green_cert"]
    rows = [
        {
            "item": "汛期 96 点时间均价",
            "value": f"{wet['avg_price_cny_per_mwh']:.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "丰季 96 个 15 分钟槽的等权均价（合成形态）",
        },
        {
            "item": "汛期捕获价（96 点发电加权）",
            "value": f"{wet['capture_price_cny_per_mwh']:.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "Σ(价格 × 日内发电分布)：汛期大发压在低价时段",
        },
        {
            "item": "汛期错位（捕获 − 均价）",
            "value": f"{wet['capture_minus_avg_cny_per_mwh']:+.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "为负：用时间均价会高估汛期余量收入",
        },
        {
            "item": "枯期 96 点时间均价",
            "value": f"{dry['avg_price_cny_per_mwh']:.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "枯季 96 个 15 分钟槽的等权均价（合成形态）",
        },
        {
            "item": "枯期捕获价（96 点发电加权）",
            "value": f"{dry['capture_price_cny_per_mwh']:.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "枯期水电跟早晚双峰，捕获价高于均价",
        },
        {
            "item": "枯期错位（捕获 − 均价）",
            "value": f"{dry['capture_minus_avg_cny_per_mwh']:+.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "为正：用时间均价会低估枯期偏差回购成本",
        },
        {
            "item": "年发电加权捕获价",
            "value": f"{metrics['annual_capture_cny_per_mwh']:.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "12 个月按发电量加权的 96 点捕获价",
        },
        {
            "item": "年发电加权均价",
            "value": f"{metrics['annual_avg_cny_per_mwh']:.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "12 个月按发电量加权的时间均价",
        },
        {
            "item": "年度错位（捕获 − 均价）",
            "value": f"{metrics['annual_capture_minus_avg_cny_per_mwh']:+.2f}",
            "unit": "CNY/MWh",
            "grade": "D",
            "note": "丰枯两季错位按电量加权后的净方向",
        },
        {
            "item": "均价替代的年收入误差（全现货口径）",
            "value": f"{metrics['average_price_error_cny']:+,.0f}",
            "unit": "CNY",
            "grade": "D",
            "note": "Σ(电量 × (捕获 − 均价))：把月均价当结算价的误差量级",
        },
        {
            "item": "绿证单价（1 张 = 1 MWh）",
            "value": f"{metrics['cert_price_cny_per_certificate']:.2f}",
            "unit": "CNY/张",
            "grade": "D",
            "note": "D 级合成占位；真实绿证出售单价待核实",
        },
        {
            "item": "机制电量比例（占位）",
            "value": f"{metrics['mechanism_ratio'] * 100:.1f}%",
            "unit": "比例",
            "grade": "C",
            "note": "常规水电机制差价参数待核实；>0 时绿证基数防重扣减",
        },
        {
            "item": "调节容量市场收入（占位）",
            "value": f"{metrics['regulation_capacity_cny']:.2f}",
            "unit": "CNY/年",
            "grade": "B",
            "note": reg.get("status", "")[:80] or "水电补偿标准待核实，保持 0 占位",
        },
        {
            "item": "煤电容量电价（不适用水电）",
            "value": f"{values['coal_price']:.0f}",
            "unit": "CNY/kW·年",
            "grade": "A",
            "note": "330 元/kW·年、回收比例 100%（2026-01-01 起，A）；煤电专属，水电不得套用",
        },
        {
            "item": "省内现货限价",
            "value": "待核实",
            "unit": "CNY/MWh",
            "grade": "-",
            "note": green.get("status", "")[:0] or "未核到省级正式全文，不得套广东 −50–1,800 或广西 0–1,125 元/MWh",
        },
    ]
    return rows


def build_outputs(bundle, profile, shapes, out_dir):
    values = bundle["values"]
    base = compute(bundle, profile, shapes)
    sensitivity = build_sensitivity(bundle, profile, shapes, base)
    metrics = base["metrics"]

    price_rows = build_price_rows(bundle, base)

    warnings = list(profile["warnings"])
    wet = metrics["season_metrics"]["wet"]
    dry = metrics["season_metrics"]["dry"]
    if wet["capture_minus_avg_cny_per_mwh"] < 0:
        warnings.append(
            f"汛期捕获价 {wet['capture_price_cny_per_mwh']:.2f} 低于时间均价 {wet['avg_price_cny_per_mwh']:.2f} 元/MWh"
            f"（{wet['capture_minus_avg_cny_per_mwh']:+.2f}）：汛期大发压在低价时段，用区域均价会高估余量收入"
        )
    if dry["capture_minus_avg_cny_per_mwh"] > 0:
        warnings.append(
            f"枯期捕获价 {dry['capture_price_cny_per_mwh']:.2f} 高于时间均价 {dry['avg_price_cny_per_mwh']:.2f} 元/MWh"
            f"（{dry['capture_minus_avg_cny_per_mwh']:+.2f}）：枯期偏差回购发生在高价时段，用均价会低估回购成本"
        )
    flat = base["strategies"][1]
    seasonal = base["strategies"][2]
    if flat["shortfall_mwh"] > 3 * max(seasonal["shortfall_mwh"], 1.0):
        warnings.append(
            f"年度平推分解产生 {flat['shortfall_mwh']:,.0f} MWh 偏差电量，约为丰枯曲线（{seasonal['shortfall_mwh']:,.0f} MWh）的 "
            f"{flat['shortfall_mwh'] / max(seasonal['shortfall_mwh'], 1.0):.0f} 倍：丰枯显著省份不能按 1/12 平推签合同"
        )
    if seasonal["shortfall_mwh"] > 0:
        warnings.append(
            f"丰枯曲线仍有 {seasonal['shortfall_mwh']:,.0f} MWh 偏差按捕获价价差回购；云南省级偏差考核公式待核实，本包未计罚则"
        )
    if base["best"]["strategy"] == "all_spot":
        warnings.append(
            "合成价格假设下全部现货占优（枯期捕获价高于合同价、汛期合同价高于捕获价）：真实决策须校核来水预测、"
            "偏差考核、外送机会成本与签约相对现货的风险溢价，不能据此不签中长期"
        )
    if metrics["mechanism_ratio"] > 0:
        warnings.append(
            f"机制电量比例 {metrics['mechanism_ratio'] * 100:.0f}%：已从绿证基数扣减 {metrics['mechanism_excluded_mwh']:,.0f} MWh（绿证收益与机制差价结算防重，B）"
        )
    if metrics["regulation_capacity_cny"] > 0:
        warnings.append("调节容量补偿标准待核实，policy 占位值应保持 0，不得套煤电容量电价")
    if metrics["cert_price_cny_per_certificate"] == 0:
        warnings.append("绿证单价为 0：绿证收入线归零（无偿划转口径），请确认这是有意设置")

    fingerprint = hashlib.sha1(
        json.dumps(bundle["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]

    stations_text = "+".join(f"{station['capacity_mw']:,.0f}" for station in values["stations"])
    summary = {
        "meta": bundle["meta"],
        "fingerprint": fingerprint,
        "config": {
            "profile_id": values["profile_id"],
            "project_name": bundle["project"]["name"],
            "reservoirs": int(values["reservoirs"]),
            "stations": values["stations"],
            "capacity_mw": values["capacity"],
            "p50_hours": values["p50"],
            "planned_generation_mwh": profile["planned_generation"],
            "contract_ratio": metrics["contract_ratio"],
            "price_interval_minutes": values["interval_minutes"],
            "points_per_day": values["points_per_day"],
            "green_cert_price_cny_per_certificate": metrics["cert_price_cny_per_certificate"],
            "mechanism_ratio": metrics["mechanism_ratio"],
            "regulation_capacity_placeholder_cny": metrics["regulation_capacity_cny"],
        },
        "volumes": {
            "generation_mwh": metrics["total_generation_mwh"],
            "green_base_mwh": metrics["green_base_mwh"],
            "green_cert_revenue_cny": metrics["green_cert_revenue_cny"],
            "green_cert_price_cny_per_certificate": metrics["cert_price_cny_per_certificate"],
            "mechanism_excluded_mwh": metrics["mechanism_excluded_mwh"],
            "all_spot": {key: base["strategies"][0][key] for key in ("contract_mwh", "surplus_mwh", "shortfall_mwh", "total_revenue_cny")},
            "contract_flat": {key: base["strategies"][1][key] for key in ("contract_mwh", "own_contract_mwh", "surplus_mwh", "shortfall_mwh", "total_revenue_cny")},
            "contract_seasonal": {key: base["strategies"][2][key] for key in ("contract_mwh", "own_contract_mwh", "surplus_mwh", "shortfall_mwh", "total_revenue_cny")},
        },
        "prices": {
            "wet_avg_cny_per_mwh": wet["avg_price_cny_per_mwh"],
            "wet_capture_cny_per_mwh": wet["capture_price_cny_per_mwh"],
            "wet_capture_minus_avg_cny_per_mwh": wet["capture_minus_avg_cny_per_mwh"],
            "dry_avg_cny_per_mwh": dry["avg_price_cny_per_mwh"],
            "dry_capture_cny_per_mwh": dry["capture_price_cny_per_mwh"],
            "dry_capture_minus_avg_cny_per_mwh": dry["capture_minus_avg_cny_per_mwh"],
            "annual_capture_cny_per_mwh": metrics["annual_capture_cny_per_mwh"],
            "annual_avg_cny_per_mwh": metrics["annual_avg_cny_per_mwh"],
            "average_price_error_cny": metrics["average_price_error_cny"],
        },
        "strategies": [
            {
                "strategy": row["strategy"],
                "label": row["label"],
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
            "contract_price_cny_per_kwh",
            "contract_flat_mwh",
            "contract_seasonal_mwh",
            "avg_price_cny_per_mwh",
            "capture_price_cny_per_mwh",
            "capture_minus_avg_cny_per_mwh",
            "settle_price_cny_per_mwh",
            "green_base_mwh",
            "mechanism_excluded_mwh",
            "green_cert_cny",
            "regulation_capacity_cny",
            "all_spot_cny",
            "contract_flat_cny",
            "contract_seasonal_cny",
            "delta_flat_vs_all_spot_cny",
            "delta_seasonal_vs_all_spot_cny",
        ],
    )
    write_csv(
        out_dir / "strategies.csv",
        base["strategies"],
        [
            "strategy",
            "label",
            "contract_mwh",
            "own_contract_mwh",
            "surplus_mwh",
            "shortfall_mwh",
            "contract_revenue_cny",
            "spot_surplus_cny",
            "shortfall_cost_cny",
            "green_cert_cny",
            "regulation_capacity_cny",
            "total_revenue_cny",
            "net_price_cny_per_kwh",
            "delta_vs_all_spot_cny",
            "delta_vs_best_cny",
        ],
    )
    write_csv(out_dir / "prices.csv", price_rows, ["item", "value", "unit", "grade", "note"])
    write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        [
            "case",
            "change",
            "all_spot_cny",
            "contract_flat_cny",
            "contract_seasonal_cny",
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
        render_review(bundle, profile, base, sensitivity, price_rows),
        encoding="utf-8",
    )
    return summary


def render_review(bundle, profile, base, sensitivity, price_rows):
    meta = bundle["meta"]
    values = bundle["values"]
    metrics = base["metrics"]
    strategies = base["strategies"]
    best = base["best"]
    all_spot = strategies[0]
    flat = strategies[1]
    seasonal = strategies[2]
    wet = metrics["season_metrics"]["wet"]
    dry = metrics["season_metrics"]["dry"]

    lines = [
        f"# {meta['province']}梯级水电 · 区域现货 + 省内中长期复核表",
        "",
        f"- 实例：`{meta['instance_id']}`（{meta['entity_type']}）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}；全部电量、价格、合同与绿证参数为 D 级合成数据",
        "",
        "## 1. 结论",
        "",
        f"基准情景的最优组合是 **{best['label']}**：净收入 **{_fmt_wan(best['total_revenue_cny'])} 万元**，"
        f"净价 **{best['net_price_cny_per_kwh']:.4f} 元/kWh**。",
        f"汛期 96 点捕获价 {wet['capture_price_cny_per_mwh']:.2f} 元/MWh **低于**时间均价 {wet['avg_price_cny_per_mwh']:.2f}"
        f"（{wet['capture_minus_avg_cny_per_mwh']:+.2f}），枯期捕获价 {dry['capture_price_cny_per_mwh']:.2f} **高于**均价 {dry['avg_price_cny_per_mwh']:.2f}"
        f"（{dry['capture_minus_avg_cny_per_mwh']:+.2f}）：中长期按月度电量分解、现货按 15 分钟出清结算，"
        "两个粒度之间的错位直接改写余量与偏差的结算价格。",
        f"年度平推分解产生 {flat['shortfall_mwh']:,.0f} MWh 偏差电量（丰枯曲线只有 {seasonal['shortfall_mwh']:,.0f} MWh），"
        f"其净收入比丰枯曲线低 **{_fmt_wan(seasonal['total_revenue_cny'] - flat['total_revenue_cny'])} 万元**；"
        f"绿证单独计线 {_fmt_wan(metrics['green_cert_revenue_cny'])} 万元（{metrics['green_base_mwh']:,.0f} 张 × "
        f"{metrics['cert_price_cny_per_certificate']:.2f} 元/张，D 级合成），机制电量比例 0% 时防重约束未触发；"
        f"调节容量市场收入占位 **{metrics['regulation_capacity_cny']:.2f} 元**（补偿标准待核实）。",
        "",
        "## 2. 电量与价格",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 梯级结构 | 两库三级：{' + '.join(station['name'] + ' ' + format(station['capacity_mw'], ',.0f') + ' MW' for station in values['stations'])} |",
        f"| 装机容量 | {values['capacity']:,.0f} MW |",
        f"| 计划电量（P50 {values['p50']:,.0f} h） | {profile['planned_generation']:,.0f} MWh |",
        f"| 实际发电量 | {metrics['total_generation_mwh']:,.0f} MWh |",
        f"| 汛期（6–10 月）电量 | {wet['generation_mwh']:,.0f} MWh（占 {wet['generation_mwh'] / metrics['total_generation_mwh'] * 100:.0f}%） |",
        f"| 枯期（11–5 月）电量 | {dry['generation_mwh']:,.0f} MWh |",
        f"| 合同比例 | {metrics['contract_ratio'] * 100:.0f}%（平推与丰枯曲线两种分解对比） |",
        f"| 汛期均价 / 捕获价 | {wet['avg_price_cny_per_mwh']:.2f} / {wet['capture_price_cny_per_mwh']:.2f} 元/MWh |",
        f"| 枯期均价 / 捕获价 | {dry['avg_price_cny_per_mwh']:.2f} / {dry['capture_price_cny_per_mwh']:.2f} 元/MWh |",
        f"| 年发电加权均价 / 捕获价 | {metrics['annual_avg_cny_per_mwh']:.2f} / {metrics['annual_capture_cny_per_mwh']:.2f} 元/MWh |",
        f"| 绿证基数 / 收入 | {metrics['green_base_mwh']:,.0f} MWh / {_fmt_wan(metrics['green_cert_revenue_cny'])} 万元 |",
        "",
        "## 3. 价格口径分解（96 点错位）",
        "",
        "| 项目 | 值 | 级别 |",
        "|---|---:|---|",
    ]
    for row in price_rows:
        lines.append(f"| {row['item']} | {row['value']} {row['unit']} | {row['grade']} |")
    lines.extend(
        [
            "",
            "捕获价 = Σ(15 分钟价格 × 日内发电分布)。中长期合同按月度电量分解，区域现货按 15 分钟价格出清结算：",
            "汛期水电大发压在午间低谷（捕获价低于均价），枯期水电跟早晚双峰（捕获价高于均价）。"
            "用月均价或区域均价代替捕获价，会把全现货组合的年收入误差做到 "
            f"**{_fmt_wan(abs(metrics['average_price_error_cny']))} 万元**（{metrics['average_price_error_cny']:+,.0f} 元）。",
            "南方区域为 15 分钟价格、一地注册全域交易（A）；云南省内现货限价与转正节点待核实，不得套广东/广西限价。",
            "",
            "## 4. 组合比较",
            "",
            "| 组合 | 合同电量 | 自有合同 | 现货余量 | 偏差 | 合同收入 | 现货余量 | 偏差回购 | 绿证 | 净收入（万元） | 净价（元/kWh） | 较全部现货（万元） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in strategies:
        lines.append(
            f"| {row['label']} | {row['contract_mwh']:,.0f} | {row['own_contract_mwh']:,.0f} | "
            f"{row['surplus_mwh']:,.0f} | {row['shortfall_mwh']:,.0f} | "
            f"{_fmt_wan(row['contract_revenue_cny'])} | {_fmt_wan(row['spot_surplus_cny'])} | "
            f"{_fmt_wan(row['shortfall_cost_cny'])} | {_fmt_wan(row['green_cert_cny'])} | "
            f"{_fmt_wan(row['total_revenue_cny'])} | {row['net_price_cny_per_kwh']:.4f} | "
            f"{row['delta_vs_all_spot_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            f"偏差按区域现货捕获价价差结算、未计罚则（云南省级偏差考核公式待核实，昆明交易函〔2026〕71号仍为草案）。"
            f"「中长期平推」的净收入比「全部现货」低 {_fmt_wan(all_spot['total_revenue_cny'] - flat['total_revenue_cny'])} 万元："
            "枯期 1/12 平推的合同量超过来水，偏差按枯期高价捕获价回购；汛期余量又被汛期低价捕获价压住。"
            "「丰枯曲线」把偏差压到枯期小月，仍比全部现货低 "
            f"{_fmt_wan(all_spot['total_revenue_cny'] - seasonal['total_revenue_cny'])} 万元——"
            "本合成情景中枯期合同价低于枯期捕获价，签合同让出了枯期高价收益；这是 D 级价格假设的结果，不是结论。",
            "",
            "## 5. 月度明细",
            "",
            "| 月份 | 季 | 发电量 | 平推合同 | 丰枯合同 | 捕获价 | 均价 | 错位 | 全部现货 | 平推+现货 | 丰枯+现货 | 丰枯−现货 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in base["monthly"]:
        lines.append(
            f"| {row['month']} | {'汛' if row['season'] == 'wet' else '枯'} | {row['generation_mwh']:,.0f} | "
            f"{row['contract_flat_mwh']:,.0f} | {row['contract_seasonal_mwh']:,.0f} | "
            f"{row['capture_price_cny_per_mwh']:.2f} | {row['avg_price_cny_per_mwh']:.2f} | "
            f"{row['capture_minus_avg_cny_per_mwh']:+.2f} | {_fmt_wan(row['all_spot_cny'])} | "
            f"{_fmt_wan(row['contract_flat_cny'])} | {_fmt_wan(row['contract_seasonal_cny'])} | "
            f"{row['delta_seasonal_vs_all_spot_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            "合同价按月给出（枯期高、汛期低，D 级合成）；捕获价丰枯两套 96 点形态按月套用。"
            "2、4、12 月丰枯曲线合同量高于当月发电，产生偏差；6–10 月与 11 月余量集中。",
            "",
            "## 6. 敏感性",
            "",
            "| 情景 | 全部现货 | 平推+现货 | 丰枯+现货 | 最优组合 | 最优净收入（万元） | 较基准最优（万元） |",
            "|---|---:|---:|---:|---|---:|---:|",
        ]
    )
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {_fmt_wan(row['all_spot_cny'])} | {_fmt_wan(row['contract_flat_cny'])} | "
            f"{_fmt_wan(row['contract_seasonal_cny'])} | {row['best_strategy']} | "
            f"{_fmt_wan(row['best_net_cny'])} | {row['delta_vs_base_best_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            "组合排名对枯期现货价与合同价最敏感：枯期现货走弱或合同价改善时，「丰枯曲线」可能反超「全部现货」；"
            "「均价替代捕获价」情景展示忽略 15 分钟粒度的收入误差。绿证单价与机制电量比例只动绿证线："
            "机制电量比例 10% 时绿证基数被防重扣减，绿证收入等比例下降，不能叠加补回。",
            "",
            "## 7. 口径提醒",
            "",
            "- **区域正式 ≠ 省内现货转正**：2026-10-24 正式运行的是南方区域市场（发改办体改〔2026〕715号，A）；"
            "云南省内现货仍是配合区域连续结算试运行（B），省内限价待核实，不得套广东 −50–1,800 或广西 0–1,125 元/MWh。",
            "- **捕获价不是均价**：汛期捕获价低于时间均价、枯期高于均价；用区域均价推省内项目收益是云南最典型的错误（B）。",
            "- **绿证与机制差价防重**：绿证收益与机制电量差价结算不能重复计算（B）；无偿划转的 3.03 亿张存量绿证面向受惠企业，"
            "不构成发电侧销售收入，本包绿证单价与比例为 D 级合成占位。",
            "- **煤电容量电价不适用水电**：330 元/kW·年、回收比例 100% 是煤电专属（A）；水电与储能不得套用 330 或 165 口径；"
            "调节容量市场收入按 0 占位（补偿标准待核实）。",
            "- **平推分解的代价**：丰枯显著省份按 1/12 平推签合同会同时制造枯期偏差与汛期余量；丰枯曲线更贴近资源，"
            "但签约前仍须按来水预测滚动校核。",
            "- **偏差无罚则是简化**：云南省级偏差考核公式待核实（71号为 2026-07-09 征求意见稿，A 草案）；"
            "真实合同必须把偏差考核与规则变更条款写清。",
            "- 本包不构成报价、投资或法律建议；全部价格形态、电量、合同比例与绿证参数为 D 级合成，"
            "实际以南方区域规则、云南省级正式文件、交易公告和结算单为准。",
            "",
            f"风格指纹 `{hashlib.sha1(json.dumps(bundle['policy'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()[:12]}`；"
            "本复核表由 `run.py` 生成。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="云南两库三级梯级水电：区域现货 + 省内中长期实例")
    parser.add_argument("--instance", type=Path, default=HERE / "instance.json")
    parser.add_argument("--profile", type=Path, help="月度电量与合同 CSV；--demo 时省略")
    parser.add_argument("--shapes", type=Path, help="丰/枯 96 点价格形态 CSV；--demo 时省略")
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
        stations_text = "+".join(f"{station['capacity_mw']:,.0f}" for station in values["stations"])
        print("配置校验通过")
        print(f"实例: {bundle['meta']['instance_id']} · {bundle['meta']['province']} · {bundle['meta']['market']}")
        print(f"规则版本: {bundle['meta']['rule_version']}")
        print(f"风格: {values['profile_id']}")
        print(
            f"资产: 两库三级 {values['capacity']:,.0f} MW（{stations_text} MW）· P50 {values['p50']:,.0f} h "
            f"· 计划年电量 {values['planned_declared']:,.0f} MWh"
        )
        print(
            f"合同比例: {values['ratio']:.0%} · 绿证单价: {values['cert_price']:.2f} 元/张 · "
            f"机制电量比例: {values['mechanism_ratio']:.0%} · 调节容量占位: {values['regulation_placeholder']:.2f} 元"
        )
        print(
            f"区域价格: {values['interval_minutes']:.0f} 分钟 × {values['points_per_day']:.0f} 点 · "
            f"省内现货限价: 待核实（保持 null，正确）· 省内现货转正: 否（正确）"
        )
        print(f"煤电容量电价 {values['coal_price']:.0f} 元/kW·年: 不适用水电（正确）")
        print("规则来源:")
        for row in bundle["report"]:
            print(f"  - {row['block']} [{row['grade']}] {row['source'][:90]}")
        print("待核实清单:")
        pending = 0
        for name, block in bundle["config"]["rules"].items():
            status = block.get("status", "")
            if "待核实" in status:
                pending += 1
                print(f"  - rules.{name}: {status[:100]}")
        if pending == 0:
            print("  （无）")
        return 0

    if args.profile is not None and args.shapes is not None:
        profile_path, shapes_path = args.profile, args.shapes
    elif args.demo:
        profile_path = HERE / bundle["profile"]["file"]
        shapes_path = HERE / bundle["shapes"]["file"]
    else:
        print("请用 --profile 与 --shapes 指定月度电量与价格形态 CSV，或加 --demo 使用合成数据", file=sys.stderr)
        return 2

    try:
        profile = load_profile(profile_path, bundle)
        shapes = load_shapes(shapes_path, bundle)
        out_dir = args.out / "demo" if args.demo else args.out
        summary = build_outputs(bundle, profile, shapes, out_dir)
    except ConfigError as exc:
        print(f"数据错误: {exc}", file=sys.stderr)
        return 2

    best = next(row for row in summary["strategies"] if row["delta_vs_best_cny"] == 0.0)
    print(f"输出目录: {out_dir}")
    print(
        f"发电量 / 汛期占比: {summary['volumes']['generation_mwh']:,.0f} MWh / "
        f"{summary['prices']['wet_capture_cny_per_mwh']:.2f} 元/MWh 捕获价（汛）"
    )
    print(
        f"96 点错位: 汛 {summary['prices']['wet_capture_minus_avg_cny_per_mwh']:+.2f} · "
        f"枯 {summary['prices']['dry_capture_minus_avg_cny_per_mwh']:+.2f} 元/MWh（捕获 − 均价）"
    )
    print(
        f"绿证收入: {summary['volumes']['green_base_mwh']:,.0f} 张 × "
        f"{summary['volumes']['green_cert_price_cny_per_certificate']:.2f} 元/张 = "
        f"{summary['volumes']['green_cert_revenue_cny'] / 1e4:,.2f} 万元"
        f"（机制电量防重扣减 {summary['volumes']['mechanism_excluded_mwh']:,.0f} MWh）"
    )
    print(f"最优组合: {best['label']} · {best['total_revenue_cny'] / 1e4:,.2f} 万元 · {best['net_price_cny_per_kwh']:.4f} 元/kWh")
    for warning in summary["warnings"]:
        print(f"警告: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
