#!/usr/bin/env python3
"""Run the Liaoning nuclear mechanism-price + mid/long-term + spot CfD instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the market rules, the nuclear asset, the mechanism
  price parameters (142号), the financial contract book, the style profile and
  the data contract. A trader edits it; no code change is needed for a new
  plant slice or a new hedge style.
* ``data/d1_demo.csv`` is a 24-slot plan (constant base-load output), the
  day-ahead *pre-clearing* price (signal only — Liaoning suspends day-ahead
  energy settlement) and five real-time price scenarios including
  negative-price slots.
* ``data/t1_demo.csv`` is the T+1 metered output, the settled contract energy
  per slot, the real-time settlement price and the pre-clearing price for
  contrast.
* ``data/rolling_demo.csv`` is the D-7~D-1 rolling *market energy* forecast
  (mechanism energy already excluded) and the position before each rebalance.

Liaoning settles on two separate lines and they must never be mixed:

1. 机制线（辽发改价格〔2026〕142号）：每日 21 小时窗口（02:00–05:00 不纳入）
   × 80% 电量为机制电量，按机制电价差价结算：
   ``Σ 机制电量 ×（机制电价 − 实时价）``。
2. 电能量差价线：全电量按实时现货价定价，中长期合约转为财务合约：
   ``Σ 合约电量 ×（合约价 − 实时价）``。

总收入恒等式（两线分账对账的核对基准）::

    总收入 = 机制电量×机制电价 + 合约电量×合约价
           + （上网电量 − 机制电量 − 合约电量）× 现货价

The maths reuses ``../tools/hedge.py`` for contract curve decomposition,
carry/shape and the rolling plan; ``spot-bidding-quant/tools/desk.py`` for
schema validation and CVaR. All bundled numbers are synthetic grade D — they
are not Hongyanhe production data, a market forecast or investment advice.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parents[1]
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(SKILL_DIR / "tools"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "spot-bidding-quant" / "tools"))

import desk  # noqa: E402
import hedge  # noqa: E402


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


def _rule_block(rules, name):
    block = _need(rules, name, "rules")
    for key in ("grade", "source"):
        _text(block, key, f"rules.{name}")
    return block


def _parse_day(value, path):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ConfigError(f"{path} must be an ISO date (YYYY-MM-DD)")


def _span_hour(spans, slot, dt_h):
    """True when the slot lies fully inside one of the ``[[start, end]]`` spans."""
    start, end = slot * dt_h, (slot + 1) * dt_h
    return any(start >= a - 1e-12 and end <= b + 1e-12 for a, b in spans)


def _window_flags(excluded_spans, points, dt_h):
    return [0.0 if _span_hour(excluded_spans, slot, dt_h) else 1.0 for slot in range(points)]


def _mech_prices(config):
    """Map group_id -> mechanism price in CNY/MWh from rules.mechanism."""
    mech = config["rules"]["mechanism"]
    return {item["group_id"]: float(item["price_cny_per_mwh"]) for item in mech["group_prices"]}


def validate_instance(config):
    """Validate the six blocks and return a provenance report."""
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
    book = _need(config, "book", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot")
    _rule_block(rules, "mid_long_term")
    mechanism = _rule_block(rules, "mechanism")
    _rule_block(rules, "settlement")
    _rule_block(rules, "deviation")

    mtu = _number(_need(spot, "market_time_unit_min", "rules.spot"), "rules.spot.market_time_unit_min", 1)
    points = int(_number(_need(spot, "points_per_day", "rules.spot"), "rules.spot.points_per_day", 1))
    expected_points = 24 * 60 / mtu
    if abs(expected_points - points) > 1e-9:
        raise ConfigError(f"rules.spot.points_per_day ({points}) does not match 24*60/{mtu:g}")
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
    _text(spot, "day_ahead", "rules.spot")
    _text(spot, "settlement_basis", "rules.spot")

    capacity = _number(_need(asset, "capacity_mw", "asset"), "asset.capacity_mw", 1e-9)
    min_output = _number(_need(asset, "min_output_mw", "asset"), "asset.min_output_mw", 0.0)
    if min_output > capacity + 1e-9:
        raise ConfigError("asset.min_output_mw must not exceed asset.capacity_mw")
    load_factor = _number(_need(asset, "load_factor", "asset"), "asset.load_factor", 0.0, 1.0)
    groups = _need(asset, "unit_groups", "asset")
    if not isinstance(groups, list) or not groups:
        raise ConfigError("asset.unit_groups must be a non-empty list")
    group_capacity = 0.0
    group_ids = []
    for index, group in enumerate(groups):
        path = f"asset.unit_groups[{index}]"
        group_id = _text(group, "id", path)
        if group_id in group_ids:
            raise ConfigError(f"{path}.id duplicates {group_id}")
        group_ids.append(group_id)
        units = _number(_need(group, "units", path), f"{path}.units", 1)
        group_cap = _number(_need(group, "capacity_mw", path), f"{path}.capacity_mw", 1e-9)
        group_capacity += group_cap
        _number(units, f"{path}.units", 1)
    if abs(group_capacity - capacity) > 1e-6:
        raise ConfigError(
            f"asset.unit_groups capacity sum ({group_capacity:g}) must equal asset.capacity_mw ({capacity:g})"
        )

    excluded_spans = _need(asset, "excluded_window_hours", "asset")
    if not isinstance(excluded_spans, list) or not excluded_spans:
        raise ConfigError("asset.excluded_window_hours must be a non-empty list of [start, end] hours")
    parsed_spans = []
    for index, span in enumerate(excluded_spans):
        if not isinstance(span, (list, tuple)) or len(span) != 2:
            raise ConfigError(f"asset.excluded_window_hours[{index}] must be [start_hour, end_hour]")
        start, end = float(span[0]), float(span[1])
        if not 0.0 <= start < end <= 24.0:
            raise ConfigError(f"asset.excluded_window_hours[{index}] must satisfy 0 <= start < end <= 24")
        parsed_spans.append((start, end))
    dt_h = mtu / 60.0
    window_hours = sum(1.0 for slot in range(points) if not _span_hour(parsed_spans, slot, dt_h)) * dt_h
    asset_window = _number(_need(asset, "window_hours", "asset"), "asset.window_hours", 0.0, 24.0)
    if abs(window_hours - asset_window) > 1e-9:
        raise ConfigError(
            f"asset.window_hours ({asset_window:g}) does not match the excluded spans ({window_hours:g})"
        )
    share = _number(
        _need(asset, "mechanism_energy_share", "asset"), "asset.mechanism_energy_share", 0.0, 1.0
    )
    if share <= 0.0:
        raise ConfigError("asset.mechanism_energy_share must be positive")

    mech_window = _number(_need(mechanism, "window_hours", "rules.mechanism"), "rules.mechanism.window_hours", 0.0, 24.0)
    if abs(mech_window - window_hours) > 1e-9:
        raise ConfigError(
            f"rules.mechanism.window_hours ({mech_window:g}) does not match asset window structure ({window_hours:g})"
        )
    mech_share = _number(
        _need(mechanism, "mechanism_energy_share", "rules.mechanism"),
        "rules.mechanism.mechanism_energy_share",
        0.0,
        1.0,
    )
    if abs(mech_share - share) > 1e-12:
        raise ConfigError("rules.mechanism.mechanism_energy_share and asset.mechanism_energy_share disagree")
    mech_spans = _need(mechanism, "excluded_window_hours", "rules.mechanism")
    if [[float(a), float(b)] for a, b in mech_spans] != [[float(a), float(b)] for a, b in parsed_spans]:
        raise ConfigError("rules.mechanism.excluded_window_hours and asset.excluded_window_hours disagree")
    _text(mechanism, "document", "rules.mechanism")
    avg_kwh = _number(
        _need(mechanism, "average_price_cny_per_kwh", "rules.mechanism"),
        "rules.mechanism.average_price_cny_per_kwh",
        0.0,
        2.0,
    )
    group_prices = _need(mechanism, "group_prices", "rules.mechanism")
    if not isinstance(group_prices, list) or not group_prices:
        raise ConfigError("rules.mechanism.group_prices must be a non-empty list")
    price_map = {}
    for index, item in enumerate(group_prices):
        path = f"rules.mechanism.group_prices[{index}]"
        group_id = _text(item, "group_id", path)
        if group_id not in group_ids:
            raise ConfigError(f"{path}.group_id {group_id} is not an asset.unit_groups id")
        kwh = _number(_need(item, "price_cny_per_kwh", path), f"{path}.price_cny_per_kwh", 0.0, 2.0)
        mwh = _number(_need(item, "price_cny_per_mwh", path), f"{path}.price_cny_per_mwh", 0.0, 2000.0)
        if abs(kwh * 1000.0 - mwh) > 0.05:
            raise ConfigError(f"{path}: price_cny_per_mwh must equal price_cny_per_kwh × 1000")
        price_map[group_id] = mwh
    if len(price_map) != len(group_ids):
        raise ConfigError("rules.mechanism.group_prices must cover every asset.unit_groups id")
    if not mechanism.get("pending") or not isinstance(mechanism["pending"], list):
        raise ConfigError("rules.mechanism.pending must list the unverified items (待核实)")

    target = _number(_need(policy, "target_hedge_ratio", "policy"), "policy.target_hedge_ratio", 0.0, 2.0)
    low_ratio = _number(_need(policy, "min_hedge_ratio", "policy"), "policy.min_hedge_ratio", 0.0, 2.0)
    high_ratio = _number(_need(policy, "max_hedge_ratio", "policy"), "policy.max_hedge_ratio", 0.0, 2.0)
    if not low_ratio <= target <= high_ratio:
        raise ConfigError("policy must satisfy min_hedge_ratio <= target_hedge_ratio <= max_hedge_ratio")
    price_q = _number(
        _need(policy, "price_reference_quantile", "policy"),
        "policy.price_reference_quantile",
        0.0,
        1.0,
    )
    rebalance_start = int(
        _number(_need(policy, "rebalance_start_day", "policy"), "policy.rebalance_start_day", 1, 7)
    )
    freeze_offset = int(
        _number(_need(policy, "freeze_day_offset", "policy"), "policy.freeze_day_offset", 0, 2)
    )

    if not isinstance(book, list) or not book:
        raise ConfigError("book must be a non-empty list of contracts")
    allowed_kinds = ("annual_base", "monthly_peak", "monthly_offpeak", "intra_month_curve")
    allowed_shapes = ("base", "window", "complement", "anchors", "curve")
    seen_ids = set()
    book_daily = 0.0
    book_notional = 0.0
    summaries = []
    for index, contract in enumerate(book):
        path = f"book[{index}]"
        if not isinstance(contract, dict):
            raise ConfigError(f"{path} must be an object")
        contract_id = _text(contract, "id", path)
        if contract_id in seen_ids:
            raise ConfigError(f"{path}.id duplicates {contract_id}")
        seen_ids.add(contract_id)
        kind = _text(contract, "kind", path)
        if kind not in allowed_kinds:
            raise ConfigError(f"{path}.kind must be one of {allowed_kinds}")
        contract_type = _text(contract, "type", path)
        if contract_type != "cfd":
            raise ConfigError(
                f"{path}.type must be cfd: under Liaoning 差价结算 the mid/long-term contract is a "
                "financial contract; physical execution is out of scope"
            )
        price = _number(_need(contract, "price_cny_per_mwh", path), f"{path}.price_cny_per_mwh", 1e-9)
        if price > clear_cap + 1e-9:
            raise ConfigError(
                f"{path}.price_cny_per_mwh={price} exceeds the spot clear cap {clear_cap:g}; "
                "check whether the contract price is in CNY/MWh"
            )
        shape = _need(contract, "shape", path)
        if not isinstance(shape, dict) or shape.get("type") not in allowed_shapes:
            raise ConfigError(f"{path}.shape.type must be one of {allowed_shapes}")
        try:
            curve = hedge.contract_curve(contract, points, mtu)
        except ValueError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
        daily = sum(curve)
        if daily <= 0.0:
            raise ConfigError(f"{path} decomposes to zero daily energy")
        if "period_start" in contract and "period_end" in contract:
            start = _parse_day(contract["period_start"], f"{path}.period_start")
            end = _parse_day(contract["period_end"], f"{path}.period_end")
            if not start <= end:
                raise ConfigError(f"{path}: period_start must not be after period_end")
        for key in ("grade", "source"):
            _text(contract, key, path)
        book_daily += daily
        book_notional += daily * price
        summaries.append(
            {
                "id": contract_id,
                "kind": kind,
                "daily_energy_mwh": daily,
                "share": 0.0,
                "price_cny_per_mwh": price,
            }
        )
    # 对冲比例的分母是市场电量：market_share = 1 − share × window/24。
    # 上限按满容量估算，用于拦截"期间电量当日电量"这类数量级错误。
    market_share = 1.0 - share * window_hours / 24.0
    ceiling = capacity * 24.0 * market_share * high_ratio
    if book_daily > ceiling + 1e-9:
        raise ConfigError(
            f"book decomposes to {book_daily:.1f} MWh/day, above capacity × 24 × market_share "
            f"({market_share:.4f}) × max_hedge_ratio ({ceiling:.1f}); a period energy was probably "
            "used as a daily energy, or contracts were signed on top of mechanism energy"
        )
    for item in summaries:
        item["share"] = item["daily_energy_mwh"] / book_daily
    book_weighted_price = book_notional / book_daily

    d1 = _need(data_contract, "d1", "data_contract")
    _text(d1, "file", "data_contract.d1")
    required = _need(d1, "required_fields", "data_contract.d1")
    if not isinstance(required, list) or len(required) == 0:
        raise ConfigError("data_contract.d1.required_fields must be a non-empty list")
    scenario_fields = _need(d1, "price_scenario_fields", "data_contract.d1")
    if not isinstance(scenario_fields, list) or len(scenario_fields) < 2:
        raise ConfigError("data_contract.d1.price_scenario_fields needs at least two scenarios")
    for field in scenario_fields:
        if field not in required:
            raise ConfigError(f"data_contract.d1.required_fields is missing {field}")
    forecast_field = _text(d1, "forecast_field", "data_contract.d1")
    if forecast_field not in required:
        raise ConfigError(f"data_contract.d1.required_fields is missing {forecast_field}")
    preclear_field = d1.get("preclear_field")
    if preclear_field is not None:
        _text(d1, "preclear_field", "data_contract.d1")
        if preclear_field not in required:
            raise ConfigError(f"data_contract.d1.required_fields is missing {preclear_field}")
    weights = d1.get("scenario_weights", [1.0 / len(scenario_fields)] * len(scenario_fields))
    if len(weights) != len(scenario_fields):
        raise ConfigError("data_contract.d1.scenario_weights must match the scenario fields")
    parsed_weights = [_number(value, "data_contract.d1.scenario_weights", 0.0) for value in weights]
    if abs(sum(parsed_weights) - 1.0) > 1e-9:
        raise ConfigError("data_contract.d1.scenario_weights must sum to 1")

    t1 = _need(data_contract, "t1", "data_contract")
    _text(t1, "file", "data_contract.t1")
    t1_required = _need(t1, "required_fields", "data_contract.t1")
    if not isinstance(t1_required, list) or len(t1_required) == 0:
        raise ConfigError("data_contract.t1.required_fields must be a non-empty list")
    for field in ("date", "slot", "actual_mw", "actual_contract_mwh", "actual_rt_price"):
        if field not in t1_required:
            raise ConfigError(f"data_contract.t1.required_fields is missing {field}")
    rolling = _need(data_contract, "rolling", "data_contract.rolling")
    _text(rolling, "file", "data_contract.rolling")
    rolling_required = _need(rolling, "required_fields", "data_contract.rolling")
    for field in ("day_offset", "forecast_market_energy_mwh", "position_before_mwh"):
        if field not in rolling_required:
            raise ConfigError(f"data_contract.rolling.required_fields is missing {field}")

    provenance = []
    for name in ("spot", "mid_long_term", "mechanism", "settlement", "deviation"):
        block = rules[name]
        item = {"block": f"rules.{name}", "grade": block["grade"], "source": block["source"]}
        if block.get("status"):
            item["status"] = block["status"]
        if name == "mechanism":
            item["status"] = f"{block.get('status', '')}｜{block.get('document', '')}".strip("｜")
        if name == "deviation" and block.get("included") is False:
            item["status"] = "未纳入本包"
        provenance.append(item)

    pending = []
    for item in mechanism.get("pending", []):
        pending.append({"item": item, "grade": "C", "source": "辽宁省级知识模块（规则模块未载明）"})

    warnings = [
        "辽宁日前市场仅预出清（可靠性机组组合）并暂停日前电能量结算（A/B）：结算价用实时现货价，"
        "preclear_price 只作信号对照，把日前预出清价当结算价会全盘算错。",
        "机制线与电能量差价线分开记账，不能混算（A）：机制电量按辽发改价格〔2026〕142号单独差价结算，"
        "合约电量不得落在机制电量上重复结算。",
        "0.3798 元/kWh 是 142 号文载明的平均机制电价，机组组结算用 0.3823/0.3749；0.3798 只覆盖 "
        "21 小时窗口 × 80% 电量，不是全电量均价，平均的加权口径待核实。",
        "装机、负荷因子、合约组合与价格情景全部为 D 级合成，不对应红沿河核电站真实生产数据。",
        "对冲比例的分母是市场电量（上网电量扣除机制电量，约 30%），不是全上网电量；"
        "用错分母会把约 70% 的机制电量误算进对冲比例。",
        "辽宁现货仍是连续结算试运行（2025-03 起，未转正，A）：限价、差价结算与考核参数可能调整，"
        "跨规则版本必须切段重算。",
        "容量三层口径（煤电 100/165 元/kW·年；370 元可靠容量补偿为征求意见稿）未纳入且不能相加；"
        "核电容量收益适用口径待核实。",
    ]

    return {
        "ok": True,
        "provenance": provenance,
        "pending": pending,
        "warnings": warnings,
        "points_per_day": points,
        "mtu_min": mtu,
        "dt_h": dt_h,
        "bounds": {
            "declare_floor": declare_floor,
            "declare_cap": declare_cap,
            "clear_floor": clear_floor,
            "clear_cap": clear_cap,
        },
        "scenario_weights": parsed_weights,
        "scenario_fields": list(scenario_fields),
        "forecast_field": forecast_field,
        "preclear_field": preclear_field,
        "capacity_mw": capacity,
        "min_output_mw": min_output,
        "load_factor": load_factor,
        "group_ids": group_ids,
        "mech_prices": price_map,
        "documented_avg_price_cny_per_mwh": avg_kwh * 1000.0,
        "excluded_spans": parsed_spans,
        "window_hours": window_hours,
        "mechanism_share": share,
        "market_share": market_share,
        "book_daily_energy_mwh": book_daily,
        "book_weighted_price": book_weighted_price,
        "book_summaries": summaries,
        "target_hedge_ratio": target,
        "min_hedge_ratio": low_ratio,
        "max_hedge_ratio": high_ratio,
        "price_quantile": price_q,
        "rebalance_start_day": rebalance_start,
        "freeze_day_offset": freeze_offset,
        "contract_kinds": list(rules["mid_long_term"].get("contract_types", allowed_kinds)),
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
    trading_day = _parse_day(rows[0]["date"], f"{path.name}:date")
    for contract in config["book"]:
        if "period_start" not in contract or "period_end" not in contract:
            continue
        start = _parse_day(contract["period_start"], f"book.{contract['id']}.period_start")
        end = _parse_day(contract["period_end"], f"book.{contract['id']}.period_end")
        if not start <= trading_day <= end:
            raise ConfigError(
                f"contract {contract['id']} period {start}~{end} does not cover trading day {trading_day}"
            )
    by_slot = {int(row["slot"]): row for row in rows}
    forecast = []
    for slot in range(report["points_per_day"]):
        value = _number(
            by_slot[slot][report["forecast_field"]],
            f"{path.name}:{report['forecast_field']}@slot{slot}",
            0.0,
            report["capacity_mw"],
        )
        forecast.append(value)
    preclear = []
    if report["preclear_field"]:
        for slot in range(report["points_per_day"]):
            value = _number(by_slot[slot][report["preclear_field"]], f"{path.name}:{report['preclear_field']}@slot{slot}")
            if not (
                report["bounds"]["clear_floor"] - 0.01
                <= value
                <= report["bounds"]["clear_cap"] + 0.01
            ):
                raise ConfigError(
                    f"{path.name}:{report['preclear_field']}@slot{slot}={value} is outside the clearing band"
                )
            preclear.append(value)
    prices = []
    for field in report["scenario_fields"]:
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
        "trading_day": trading_day,
        "forecast": forecast,
        "preclear": preclear if report["preclear_field"] else None,
        "prices": prices,
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
    dt_h = report["mtu_min"] / 60.0
    by_slot = {int(row["slot"]): row for row in rows}
    actual_mw = []
    actual_contract = []
    actual_price = []
    preclear = []
    for slot in range(report["points_per_day"]):
        row = by_slot[slot]
        output = _number(
            row["actual_mw"], f"{path.name}:actual_mw@slot{slot}", 0.0, report["capacity_mw"]
        )
        contract = _number(
            row["actual_contract_mwh"],
            f"{path.name}:actual_contract_mwh@slot{slot}",
            0.0,
            report["capacity_mw"] * dt_h * 2.0,
        )
        price = _number(row["actual_rt_price"], f"{path.name}:actual_rt_price@slot{slot}")
        if not (
            report["bounds"]["clear_floor"] - 0.01
            <= price
            <= report["bounds"]["clear_cap"] + 0.01
        ):
            raise ConfigError(
                f"{path.name}:actual_rt_price@slot{slot}={price} is outside the clearing band"
            )
        actual_mw.append(output)
        actual_contract.append(contract)
        actual_price.append(price)
        if report["preclear_field"] and report["preclear_field"] in row:
            value = _number(row[report["preclear_field"]], f"{path.name}:{report['preclear_field']}@slot{slot}")
            preclear.append(value)
        else:
            preclear.append(None)
    return {
        "date": rows[0]["date"],
        "actual_mw": actual_mw,
        "actual_contract_mwh": actual_contract,
        "actual_rt_price": actual_price,
        "preclear": preclear,
    }


def read_rolling(path, config, report):
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"input file not found: {path}")
    rows = _read_rows(path)
    rolling = config["data_contract"]["rolling"]
    for field in rolling["required_fields"]:
        if field not in rows[0]:
            raise ConfigError(f"{path.name} is missing field {field}")
    parsed = []
    for index, row in enumerate(rows):
        offset = int(_number(row["day_offset"], f"{path.name}:day_offset@{index + 1}"))
        if not -report["rebalance_start_day"] <= offset <= 0:
            raise ConfigError(
                f"{path.name}:day_offset {offset} is outside "
                f"-{report['rebalance_start_day']}~0"
            )
        forecast = _number(
            row["forecast_market_energy_mwh"],
            f"{path.name}:forecast_market_energy_mwh@{index + 1}",
            0.0,
        )
        position = _number(
            row["position_before_mwh"], f"{path.name}:position_before_mwh@{index + 1}", 0.0
        )
        parsed.append(
            {
                "day_offset": offset,
                "forecast_market_energy_mwh": forecast,
                "position_before_mwh": position,
            }
        )
    parsed.sort(key=lambda item: item["day_offset"])
    if len(parsed) < 2:
        raise ConfigError(f"{path.name}: at least two rolling days are required")
    offsets = [item["day_offset"] for item in parsed]
    if len(set(offsets)) != len(offsets):
        raise ConfigError(f"{path.name}: duplicate day_offset values")
    return parsed


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


def build_mechanism(config, report, output_mw):
    """机制电量认定：21 小时窗口 × 80%，按机组组拆分并给出固定收入。

    机制差价按 142 号文单独结算（A），与电能量差价线分开记账。机制电量是
    规则认定值，不是交易选择；机组组按容量比例分摊出力（D 级示例口径）。
    """
    n = report["points_per_day"]
    dt_h = report["dt_h"]
    asset = config["asset"]
    window = _window_flags(report["excluded_spans"], n, dt_h)
    share = report["mechanism_share"]
    capacity = report["capacity_mw"]
    price_map = report["mech_prices"]

    groups = []
    total_curve = [0.0] * n
    for group in asset["unit_groups"]:
        cap_share = group["capacity_mw"] / capacity
        curve = [window[slot] * share * output_mw[slot] * cap_share * dt_h for slot in range(n)]
        energy = sum(curve)
        price = price_map[group["id"]]
        groups.append(
            {
                "id": group["id"],
                "units": group["units"],
                "capacity_mw": group["capacity_mw"],
                "price_cny_per_mwh": price,
                "curve": curve,
                "energy_mwh": energy,
                "fixed_revenue_cny": energy * price,
            }
        )
        for slot in range(n):
            total_curve[slot] += curve[slot]
    total_energy = sum(total_curve)
    fixed_revenue = sum(group["fixed_revenue_cny"] for group in groups)
    weighted_price = fixed_revenue / total_energy if total_energy > 0 else 0.0
    output_energy = sum(output_mw) * dt_h
    market_curve = [output_mw[slot] * dt_h - total_curve[slot] for slot in range(n)]
    window_energy = sum(output_mw[slot] * dt_h for slot in range(n) if window[slot] > 0)
    return {
        "window": window,
        "groups": groups,
        "total_curve": total_curve,
        "total_energy_mwh": total_energy,
        "fixed_revenue_cny": fixed_revenue,
        "weighted_price_cny_per_mwh": weighted_price,
        "documented_avg_price_cny_per_mwh": report["documented_avg_price_cny_per_mwh"],
        "output_energy_mwh": output_energy,
        "window_energy_mwh": window_energy,
        "market_curve": market_curve,
        "market_energy_mwh": sum(market_curve),
        "mechanism_share_of_output": total_energy / output_energy if output_energy > 0 else 0.0,
    }


def build_position(config, report):
    n = report["points_per_day"]
    mtu = report["mtu_min"]
    book = hedge.book_position(config["book"], n, mtu)
    price = hedge.price_curve(book, n)
    summaries = []
    for item, source in zip(report["book_summaries"], book["curves"]):
        summaries.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "daily_energy_mwh": item["daily_energy_mwh"],
                "share": item["share"],
                "price_cny_per_mwh": item["price_cny_per_mwh"],
                "curve": source["curve"],
            }
        )
    return {
        "book": book,
        "position": book["position"],
        "energy_mwh": book["energy_mwh"],
        "price_curve": price,
        "contracts": summaries,
    }


def settle_two_lines(position, mech, output_mw, prices, n, dt_h):
    """两线结算：总收入 = 全电量现货 + 机制差价 + 合约差价。

    恒等式：总收入 = 机制固定收入 + 合约固定收入 + 净敞口 × 现货价。
    机制电量按 142 号单独差价结算（A），与电能量差价线分开记账。
    """
    full_spot = sum(output_mw[slot] * dt_h * prices[slot] for slot in range(n))
    mech_cfd = sum(
        mech["total_curve"][slot]
        * (mech["weighted_price_cny_per_mwh"] - prices[slot])
        for slot in range(n)
    )
    contract_cfd = sum(
        position["position"][slot] * (position["price_curve"][slot] - prices[slot])
        for slot in range(n)
    )
    total = full_spot + mech_cfd + contract_cfd
    mech_fixed = mech["fixed_revenue_cny"]
    contract_fixed = sum(
        position["position"][slot] * position["price_curve"][slot] for slot in range(n)
    )
    net_curve = [
        output_mw[slot] * dt_h - mech["total_curve"][slot] - position["position"][slot]
        for slot in range(n)
    ]
    net_spot = sum(net_curve[slot] * prices[slot] for slot in range(n))
    gap = total - (mech_fixed + contract_fixed + net_spot)
    return {
        "full_spot_revenue_cny": full_spot,
        "mechanism_cfd_cny": mech_cfd,
        "contract_cfd_cny": contract_cfd,
        "total_revenue_cny": total,
        "mechanism_fixed_revenue_cny": mech_fixed,
        "contract_fixed_revenue_cny": contract_fixed,
        "net_exposure_spot_revenue_cny": net_spot,
        "identity_gap": gap,
        "net_exposure_mwh": sum(net_curve),
        "net_curve": net_curve,
    }


def carry_shape(curve, price, prices, n):
    """把一条差价线 Σ q×(c−s) 拆成均价 carry 与曲线形状两项（恒等）。"""
    energy = sum(curve)
    if energy <= 0:
        return {"value_cny": 0.0, "carry_cny": 0.0, "shape_cny": 0.0, "identity_gap": 0.0,
                "weighted_price": 0.0, "time_average_spot": sum(prices) / n}
    weighted_price = sum(curve[slot] * price[slot] for slot in range(n)) / energy
    time_average = sum(prices) / n
    value = sum(curve[slot] * (price[slot] - prices[slot]) for slot in range(n))
    carry = energy * (weighted_price - time_average)
    shape = energy * time_average - sum(curve[slot] * prices[slot] for slot in range(n))
    return {
        "value_cny": value,
        "carry_cny": carry,
        "shape_cny": shape,
        "identity_gap": value - (carry + shape),
        "weighted_price": weighted_price,
        "time_average_spot": time_average,
    }


def negative_slots_detail(mech, output_mw, prices, dt_h, label, illusion_price):
    """负价时段逐时段拆解：机制电量兜底 vs 市场残差敞口 vs 全机制收入幻觉。"""
    rows = []
    for slot, price in enumerate(prices):
        if price >= 0:
            continue
        energy = output_mw[slot] * dt_h
        mech_energy = mech["total_curve"][slot]
        residual = energy - mech_energy
        mech_revenue = mech_energy * mech["weighted_price_cny_per_mwh"]
        residual_revenue = residual * price
        correct = mech_revenue + residual_revenue
        illusion = energy * illusion_price
        rows.append(
            {
                "source": label,
                "slot": slot,
                "start": _slot_time(slot, int(round(dt_h * 60))),
                "price_cny_per_mwh": price,
                "output_mwh": energy,
                "mechanism_mwh": mech_energy,
                "market_residual_mwh": residual,
                "mechanism_line_revenue_cny": mech_revenue,
                "residual_revenue_cny": residual_revenue,
                "correct_total_cny": correct,
                "illusion_full_mech_cny": illusion,
                "illusion_delta_cny": illusion - correct,
            }
        )
    return rows


def build_plan(config, report, d1, mech, position):
    n = report["points_per_day"]
    dt_h = report["dt_h"]
    weights = report["scenario_weights"]
    policy = config["policy"]

    forecast_energy = sum(d1["forecast"]) * dt_h
    market_energy = mech["market_energy_mwh"]
    reference_price = [
        quantile([d1["prices"][s][t] for s in range(len(d1["prices"]))], report["price_quantile"])
        for t in range(n)
    ]
    reference = settle_two_lines(position, mech, d1["forecast"], reference_price, n, dt_h)

    # 电能量差价线 carry/shape（对「全部按现货卖」的增量）
    hv = hedge.hedge_value(config["book"], d1["forecast"], reference_price, n, report["mtu_min"])
    contract_line = {
        "value_cny": hv["hedge_value_cny"],
        "carry_cny": hv["carry_cny"],
        "shape_cny": hv["shape_cny"],
        "identity_gap": hv["identity_gap"],
        "weighted_price": hv["weighted_contract_price"],
        "time_average_spot": hv["time_average_spot"],
    }
    # 机制线 carry/shape（同一代数分解，价格是 142 号分组机制电价）
    mech_price_curve = [0.0] * n
    for group in mech["groups"]:
        for slot in range(n):
            mech_price_curve[slot] += group["curve"][slot] * group["price_cny_per_mwh"]
    mech_price_curve = [
        mech_price_curve[slot] / mech["total_curve"][slot] if mech["total_curve"][slot] > 1e-9 else 0.0
        for slot in range(n)
    ]
    mechanism_line = carry_shape(mech["total_curve"], mech_price_curve, reference_price, n)

    scenarios = []
    negative_rows = []
    for index, prices in enumerate(d1["prices"]):
        settle = settle_two_lines(position, mech, d1["forecast"], prices, n, dt_h)
        neg = negative_slots_detail(
            mech, d1["forecast"], prices, dt_h, f"情景{index + 1}",
            report["documented_avg_price_cny_per_mwh"],
        )
        negative_rows.extend(neg)
        scenarios.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "mean_price": sum(prices) / n,
                "min_price": min(prices),
                "full_spot_revenue_cny": settle["full_spot_revenue_cny"],
                "mechanism_cfd_cny": settle["mechanism_cfd_cny"],
                "contract_cfd_cny": settle["contract_cfd_cny"],
                "total_revenue_cny": settle["total_revenue_cny"],
                "identity_gap": settle["identity_gap"],
                "negative_slot_count": len(neg),
                "negative_slot_energy_mwh": sum(row["output_mwh"] for row in neg),
                "negative_residual_mwh": sum(row["market_residual_mwh"] for row in neg),
                "negative_residual_revenue_cny": sum(row["residual_revenue_cny"] for row in neg),
                "illusion_delta_cny": sum(row["illusion_delta_cny"] for row in neg),
            }
        )
    expected_total = sum(item["weight"] * item["total_revenue_cny"] for item in scenarios)
    expected_full_spot = sum(item["weight"] * item["full_spot_revenue_cny"] for item in scenarios)
    cvar = desk.weighted_cvar(
        [(item["total_revenue_cny"], item["weight"]) for item in scenarios], alpha=0.10
    )
    required = hedge.required_trade(market_energy, position["energy_mwh"], report["target_hedge_ratio"])

    buy_back = 0.0
    sell_surplus = 0.0
    over_contract_slots = []
    for slot in range(n):
        market = mech["market_curve"][slot]
        pos = position["position"][slot]
        if pos > market:
            buy_back += pos - market
        else:
            sell_surplus += market - pos
        if pos > d1["forecast"][slot] * dt_h + 1e-9:
            over_contract_slots.append(slot)

    rows = []
    for slot in range(n):
        energy = d1["forecast"][slot] * dt_h
        qm = mech["total_curve"][slot]
        qc = position["position"][slot]
        s = reference_price[slot]
        mech_cfd_slot = qm * (mech["weighted_price_cny_per_mwh"] - s)
        contract_cfd_slot = qc * (position["price_curve"][slot] - s)
        full_spot_slot = energy * s
        rows.append(
            {
                "date": d1["date"],
                "slot": slot,
                "start": d1["start"][slot],
                "end": d1["end"][slot],
                "output_mw": d1["forecast"][slot],
                "output_mwh": energy,
                "mechanism_mwh": qm,
                "market_mwh": energy - qm,
                "contract_mwh": qc,
                "contract_price": position["price_curve"][slot],
                "reference_price": s,
                "mechanism_cfd_cny": mech_cfd_slot,
                "contract_cfd_cny": contract_cfd_slot,
                "full_spot_cny": full_spot_slot,
                "net_exposure_mwh": energy - qm - qc,
                "net_exposure_revenue_cny": (energy - qm - qc) * s,
                "total_line_cny": full_spot_slot + mech_cfd_slot + contract_cfd_slot,
            }
        )

    return {
        "forecast_energy_mwh": forecast_energy,
        "market_energy_mwh": market_energy,
        "mechanism_energy_mwh": mech["total_energy_mwh"],
        "mechanism_share_of_output": mech["mechanism_share_of_output"],
        "position_energy_mwh": position["energy_mwh"],
        "hedge_ratio_on_market": hedge.hedge_ratio(position["energy_mwh"], market_energy),
        "hedge_ratio_on_output": hedge.hedge_ratio(position["energy_mwh"], forecast_energy),
        "target_hedge_ratio": report["target_hedge_ratio"],
        "net_exposure_mwh": market_energy - position["energy_mwh"],
        "buy_back_mwh": buy_back,
        "sell_surplus_mwh": sell_surplus,
        "over_contract_slots": over_contract_slots,
        "reference_price": reference_price,
        "reference_settle": reference,
        "reference_revenue_cny": reference["total_revenue_cny"],
        "identity_gap": reference["identity_gap"],
        "contract_line": contract_line,
        "mechanism_line": mechanism_line,
        "expected_revenue_cny": expected_total,
        "expected_full_spot_cny": expected_full_spot,
        "cvar_10_cny": cvar,
        "required_trade": required,
        "scenarios": scenarios,
        "negative_rows": negative_rows,
        "rows": rows,
    }


def build_rolling(config, report, rolling_rows, position, mech):
    if rolling_rows is None:
        return None
    target = report["target_hedge_ratio"]
    forecasts = [item["forecast_market_energy_mwh"] for item in rolling_rows]
    plan = hedge.rolling_plan(forecasts, rolling_rows[0]["position_before_mwh"], target)
    rows = []
    for item, planned in zip(rolling_rows, plan):
        provided = item["position_before_mwh"]
        if abs(provided - planned["position_before_mwh"]) > 1e-6:
            raise ConfigError(
                f"rolling day {item['day_offset']}: position_before_mwh={provided:.3f} does not "
                f"chain from the previous close {planned['position_before_mwh']:.3f}"
            )
        rows.append(
            {
                "day_offset": item["day_offset"],
                "forecast_market_energy_mwh": item["forecast_market_energy_mwh"],
                "position_before_mwh": provided,
                "target_position_mwh": planned["target_position_mwh"],
                "required_trade_mwh": planned["required_trade_mwh"],
                "position_after_mwh": planned["position_after_mwh"],
                "current_hedge_ratio": planned["current_hedge_ratio"],
            }
        )
    final = rows[-1]
    return {
        "target_hedge_ratio": target,
        "rows": rows,
        "final_target_position_mwh": final["target_position_mwh"],
        "book_position_mwh": position["energy_mwh"],
        "lot_gap_mwh": position["energy_mwh"] - final["target_position_mwh"],
        "final_hedge_ratio": hedge.hedge_ratio(
            position["energy_mwh"], final["forecast_market_energy_mwh"]
        ),
    }


def two_line_bridge(plan_output, mech_plan, position, plan_prices,
                    actual_output, mech_actual, actual_contract, actual_prices,
                    n, dt_h):
    """把「实际总收入 − 计划总收入」拆成五桶，恒等式残差为 0。

    定义 f(E, qm, qc, s) = Σ qm×机制价 + qc×合约价 + (E−qm−qc)×s，按
    机制电量 → 合约电量 → 上网电量 → 实时价 的顺序逐项替换，望远镜求和。
    """
    c_mech = mech_plan["weighted_price_cny_per_mwh"]
    c_curve = position["price_curve"]

    def revenue(e, qm, qc, s):
        return sum(
            qm[slot] * c_mech
            + qc[slot] * c_curve[slot]
            + (e[slot] * dt_h - qm[slot] - qc[slot]) * s[slot]
            for slot in range(n)
        )

    e_p, e_a = plan_output, actual_output
    qm_p, qm_a = mech_plan["total_curve"], mech_actual["total_curve"]
    qc_p, qc_a = position["position"], actual_contract
    s_p, s_a = plan_prices, actual_prices

    p_rev = revenue(e_p, qm_p, qc_p, s_p)
    m1 = revenue(e_p, qm_a, qc_p, s_p)
    m2 = revenue(e_p, qm_a, qc_a, s_p)
    m3 = revenue(e_a, qm_a, qc_a, s_p)
    a_rev = revenue(e_a, qm_a, qc_a, s_a)

    q_p_energy = sum(qc_p)
    q_a_energy = sum(qc_a)
    if q_p_energy <= 0 or q_a_energy <= 0:
        raise ConfigError("合约电量必须为正：计划与实际的结算合约电量都不能为 0")
    d_q = q_a_energy - q_p_energy
    w_p = [value / q_p_energy for value in qc_p]
    w_a = [value / q_a_energy for value in qc_a]

    mech_bucket = sum((qm_a[slot] - qm_p[slot]) * (c_mech - s_p[slot]) for slot in range(n))
    contract_volume = sum(d_q * w_p[slot] * (c_curve[slot] - s_p[slot]) for slot in range(n))
    contract_shape = sum(
        q_a_energy * (w_a[slot] - w_p[slot]) * (c_curve[slot] - s_p[slot]) for slot in range(n)
    )
    output_bucket = sum((e_a[slot] - e_p[slot]) * dt_h * s_p[slot] for slot in range(n))
    price_bucket = sum(
        (e_a[slot] * dt_h - qm_a[slot] - qc_a[slot]) * (s_a[slot] - s_p[slot]) for slot in range(n)
    )
    buckets = [
        {"item": "机制电量偏差（142号认定）", "category": "mechanism_volume", "amount": mech_bucket},
        {"item": "合约总量偏差", "category": "contract_volume", "amount": contract_volume},
        {"item": "合约曲线偏差", "category": "contract_shape", "amount": contract_shape},
        {"item": "上网电量偏差", "category": "output_volume", "amount": output_bucket},
        {"item": "实时价偏差", "category": "spot_price", "amount": price_bucket},
    ]
    delta = a_rev - p_rev
    plan_market = mech_plan["market_energy_mwh"]
    actual_market = mech_actual["market_energy_mwh"]
    return {
        "plan_revenue_cny": p_rev,
        "actual_revenue_cny": a_rev,
        "delta_cny": delta,
        "buckets": buckets,
        "identity_gap": delta - sum(item["amount"] for item in buckets),
        "plan_output_energy_mwh": sum(e_p) * dt_h,
        "actual_output_energy_mwh": sum(e_a) * dt_h,
        "plan_mechanism_energy_mwh": mech_plan["total_energy_mwh"],
        "actual_mechanism_energy_mwh": mech_actual["total_energy_mwh"],
        "plan_market_energy_mwh": plan_market,
        "actual_market_energy_mwh": actual_market,
        "plan_contract_energy_mwh": q_p_energy,
        "actual_contract_energy_mwh": q_a_energy,
        "plan_hedge_ratio_on_market": hedge.hedge_ratio(q_p_energy, plan_market),
        "actual_hedge_ratio_on_market": hedge.hedge_ratio(q_a_energy, actual_market),
        "actual_price_average": sum(s_a) / n,
        "actual_negative_slot_count": sum(1 for value in s_a if value < 0),
    }


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(field, row.get(field)) for field in fields})


def _signed(value):
    return 0.0 if abs(value) < 0.5 else value


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, float):
        if field.endswith("_mw"):
            return f"{value:.3f}"
        if field in (
            "contract_price",
            "reference_price",
            "price_cny_per_mwh",
        ):
            return f"{value:.2f}"
        if field in (
            "mechanism_cfd_cny",
            "contract_cfd_cny",
            "full_spot_cny",
            "net_exposure_revenue_cny",
            "total_line_cny",
            "mechanism_line_revenue_cny",
            "residual_revenue_cny",
            "correct_total_cny",
            "illusion_full_mech_cny",
            "illusion_delta_cny",
        ):
            return f"{_signed(value):.2f}"
        if field in (
            "share",
            "hedge_ratio",
            "current_hedge_ratio",
            "mechanism_share",
        ):
            return f"{value:.4f}"
        return f"{value:.6f}"
    return value


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def write_review(path, config, report, d1, mech, position, plan, rolling, bridge,
                 negative_detail, fingerprint):
    dt_h = report["dt_h"]
    groups_text = "、".join(
        f"{group['id']} {group['capacity_mw']:.0f} MW × {group['units']:.0f} 台"
        for group in config["asset"]["unit_groups"]
    )
    lines = [
        f"# 辽宁核电机制电价＋中长期＋现货差价结算复核表：{config['meta']['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']:.0f} 分钟）",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格档：`{config['policy']['profile_id']}` / 指纹 `{fingerprint}`",
        f"- 机组：{config['asset']['name']}；装机 {report['capacity_mw']:.0f} MW（{groups_text}）",
        f"- 合约簿：{len(position['contracts'])} 份财务合约，日分解电量 {position['energy_mwh']:.1f} MWh，"
        f"加权合约价 {plan['contract_line']['weighted_price']:.2f} CNY/MWh",
        "",
        "> **两线分账**：机制电量按辽发改价格〔2026〕142号单独差价结算，电能量差价线"
        "（中长期财务合约）单独结算，两条线不能混算（A）。本表全部为 D 级合成数据，"
        "不对应红沿河核电站真实生产数据，不构成报价、投资或法律建议。",
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
        "**待核实项（C）**：",
        "",
    ]
    for item in report["pending"]:
        lines.append(f"- {item['item']}")
    lines += [
        "",
        "## 2. 机组、时段结构与机制电量认定（21h × 80%）",
        "",
        f"排除窗口 02:00–05:00（{report['window_hours']:.0f} 小时机制电价窗口之外，A）；"
        f"机制电量比例 {report['mechanism_share']:.0%}（窗口电量口径，本包实现；分母口径待核实）。",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 计划上网电量 | {plan['forecast_energy_mwh']:,.1f} MWh |",
        f"| 机制窗口电量（21h） | {mech['window_energy_mwh']:,.1f} MWh |",
        f"| 机制电量（窗口 × 80%） | {plan['mechanism_energy_mwh']:,.1f} MWh（占上网 {plan['mechanism_share_of_output']:.2%}） |",
        f"| 市场电量（可签约口径） | {plan['market_energy_mwh']:,.1f} MWh |",
    ]
    for group in mech["groups"]:
        lines.append(
            f"| 机组组 {group['id']}（{group['units']:.0f} 台 / {group['capacity_mw']:.0f} MW）"
            f"机制电量 | {group['energy_mwh']:,.1f} MWh × {group['price_cny_per_mwh']:.1f} "
            f"= {group['fixed_revenue_cny']:,.0f} CNY |"
        )
    lines += [
        f"| 机制线固定收入（电量加权均价 {mech['weighted_price_cny_per_mwh']:.4f} CNY/MWh） "
        f"| {mech['fixed_revenue_cny']:,.0f} CNY |",
        f"| 142 号文载明平均机制电价 | {mech['documented_avg_price_cny_per_mwh']:.1f} CNY/MWh"
        f"（0.3798 元/kWh，A；电量加权 {mech['weighted_price_cny_per_mwh']:.4f} 与载明值的口径差待核实） |",
        "",
        "## 3. 合约簿与曲线分解（全部为财务 CfD）",
        "",
        "| 合约 | 类型 | 日电量（MWh） | 占比 | 合约价 | 曲线形状 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in position["contracts"]:
        source = next(c for c in config["book"] if c["id"] == item["id"])
        shape = source["shape"]
        if shape["type"] == "base":
            shape_text = "平段（24 时段平均）"
        elif shape["type"] == "window":
            shape_text = "窗口 " + "、".join(f"{a:g}–{b:g}" for a, b in shape["windows"])
        elif shape["type"] == "complement":
            shape_text = "窗口外（" + "、".join(f"{a:g}–{b:g}" for a, b in shape["windows"]) + " 之外）"
        elif shape["type"] == "anchors":
            shape_text = f"锚点曲线 {len(shape['anchors'])} 点"
        else:
            shape_text = "显式 24 点"
        lines.append(
            f"| {item['id']} | {item['kind']} | {item['daily_energy_mwh']:.1f} | "
            f"{item['share']:.1%} | {item['price_cny_per_mwh']:.2f} | {shape_text} |"
        )
    lines += [
        "",
        "> 中长期合约按「日均分、24 时段平均分解」（试运行规则口径）；带曲线签约按合同曲线。"
        "全部为财务差价合约，不物理执行。差价结算下中长期合约转为财务合约（A/B）。",
        "",
        "## 4. 持仓与对冲比例（两个分母）",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 合约日电量 | {plan['position_energy_mwh']:.1f} MWh |",
        f"| **对冲比例（分母 = 市场电量）** | {plan['hedge_ratio_on_market']:.2%} |",
        f"| 伪口径（分母 = 全上网电量） | {plan['hedge_ratio_on_output']:.2%}（会把约 70% 机制电量算进去，勿用） |",
        f"| 目标对冲比例（市场电量口径） | {plan['target_hedge_ratio']:.0%} |",
        f"| 净敞口（市场电量 − 合约） | {plan['net_exposure_mwh']:+,.1f} MWh |",
        f"| 买入平仓量（合约 > 市场残差） | {plan['buy_back_mwh']:.1f} MWh |",
        f"| 卖出富余量（市场残差 > 合约） | {plan['sell_surplus_mwh']:.1f} MWh |",
        f"| 所需调仓（达到目标） | {plan['required_trade']['required_trade_mwh']:+,.1f} MWh（{plan['required_trade']['action']}） |",
        f"| 参考现货时间均价 | {plan['mechanism_line']['time_average_spot']:.2f} CNY/MWh |",
    ]
    if plan["over_contract_slots"]:
        slots_text = "、".join(_slot_time(slot, report["mtu_min"]) for slot in plan["over_contract_slots"])
        lines += [
            "",
            f"> 警告：{len(plan['over_contract_slots'])} 个时段合约电量超过全上网电量（{slots_text}），"
            "属于卖空全电量的投机仓位，须人工确认。",
        ]
    lines += [
        "",
        "## 5. 情景结算与 CVaR（两条线分别列示）",
        "",
        "| 情景 | 权重 | 实时均价 | 最低价 | 全电量现货收入 | 机制差价 | 合约差价 | 总收入 | 负价时段 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in plan["scenarios"]:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['mean_price']:.1f} | "
            f"{item['min_price']:.1f} | {item['full_spot_revenue_cny']:,.0f} | "
            f"{item['mechanism_cfd_cny']:+,.0f} | {item['contract_cfd_cny']:+,.0f} | "
            f"{item['total_revenue_cny']:,.0f} | {item['negative_slot_count']} 时段 |"
        )
    lines += [
        "",
        f"| 期望总收入 | {plan['expected_revenue_cny']:,.0f} CNY |",
        f"| CVaR10（最差 10% 概率平均） | {plan['cvar_10_cny']:,.0f} CNY |",
        f"| 期望全电量现货收入（不对冲、无机制） | {plan['expected_full_spot_cny']:,.0f} CNY |",
        "",
        "## 6. 两线分账对账（参考价）",
        "",
        f"总收入 {plan['reference_revenue_cny']:,.0f} CNY = 机制固定收入 "
        f"{plan['reference_settle']['mechanism_fixed_revenue_cny']:,.0f} + 合约固定收入 "
        f"{plan['reference_settle']['contract_fixed_revenue_cny']:,.0f} + 净敞口现货收入 "
        f"{plan['reference_settle']['net_exposure_spot_revenue_cny']:+,.0f}；"
        f"恒等式残差 {plan['identity_gap']:.2e}。",
        "",
        f"- 机制差价线：Σ 机制电量 ×（机制电价 − 现货价）= "
        f"{plan['reference_settle']['mechanism_cfd_cny']:+,.0f} CNY "
        f"（carry {plan['mechanism_line']['carry_cny']:+,.0f} + shape {plan['mechanism_line']['shape_cny']:+,.0f}，"
        f"残差 {plan['mechanism_line']['identity_gap']:.2e}）",
        f"- 电能量差价线：Σ 合约电量 ×（合约价 − 现货价）= "
        f"{plan['reference_settle']['contract_cfd_cny']:+,.0f} CNY "
        f"（carry {plan['contract_line']['carry_cny']:+,.0f} + shape {plan['contract_line']['shape_cny']:+,.0f}，"
        f"残差 {plan['contract_line']['identity_gap']:.2e}）",
        "",
        "> 机制线 shape 为负：机制电量集中在白天与晚峰高价时段，按固定 0.3798 元/kWh 结算"
        "相当于把高价时段卖便宜了——这正是机制电价的「兜底换让利」结构。"
        "两条线的 carry 与 shape 必须分开报，不能合并成一个「辽宁核电对冲价值」。",
        "",
        "## 7. 负电价时段敏感性",
        "",
    ]
    negative_by_scenario = {}
    for row in plan["negative_rows"]:
        negative_by_scenario.setdefault(row["source"], []).append(row)
    if bridge is not None:
        t1_neg = [row for row in negative_detail if row["source"] == "T+1"]
        if t1_neg:
            negative_by_scenario["T+1"] = t1_neg
    lines += [
        "| 来源 | 负价时段数 | 负价时段电量 | 其中市场残差 | 残差收入 | 全机制收入幻觉差 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key in sorted(negative_by_scenario, key=lambda k: (k == "T+1", k)):
        rows = negative_by_scenario[key]
        lines.append(
            f"| {key} | {len(rows)} | {sum(r['output_mwh'] for r in rows):,.0f} | "
            f"{sum(r['market_residual_mwh'] for r in rows):,.0f} | "
            f"{sum(r['residual_revenue_cny'] for r in rows):+,.0f} | "
            f"{sum(r['illusion_delta_cny'] for r in rows):+,.0f} |"
        )
    lines += [
        "",
        "> 「核电满发不亏」只对机制电量成立：02:00–05:00 三小时不纳入机制（A），恰是负电价高发时段，"
        "该时段全部电量按实时价结算；把全电量当机制电价结算（幻觉口径）会高估收入。"
        "机制线差价在负价时段反而变大（机制电价 − 负现货价），两条线方向相反。",
        "",
    ]
    if negative_detail:
        lines += [
            "负价时段明细（各情景与 T+1 实际，取幻觉差最大的 8 行）：",
            "",
            "| 来源 | 时段 | 实时价 | 机制电量 | 市场残差 | 残差收入 | 正确合计 | 幻觉差 |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for row in sorted(negative_detail, key=lambda r: abs(r["illusion_delta_cny"]), reverse=True)[:8]:
            lines.append(
                f"| {row['source']} | {row['start']} | {row['price_cny_per_mwh']:.1f} | "
                f"{row['mechanism_mwh']:.0f} | {row['market_residual_mwh']:.0f} | "
                f"{row['residual_revenue_cny']:+,.0f} | {row['correct_total_cny']:+,.0f} | "
                f"{row['illusion_delta_cny']:+,.0f} |"
            )
    if rolling is None:
        lines += ["", "## 8. 滚动调仓", "", "未提供滚动预测文件，本次不做 D-7~D-1 调仓复核。"]
    else:
        lines += [
            "",
            "## 8. 滚动调仓（D-7~D-1，分母 = 市场电量）",
            "",
            "| 日偏移 | 市场电量预测 | 调仓前持仓 | 目标持仓 | 所需交易 | 调仓后持仓 | 调仓前比例 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in rolling["rows"]:
            lines.append(
                f"| {item['day_offset']} | {item['forecast_market_energy_mwh']:.1f} | "
                f"{item['position_before_mwh']:.1f} | {item['target_position_mwh']:.1f} | "
                f"{item['required_trade_mwh']:+,.1f} | {item['position_after_mwh']:.1f} | "
                f"{item['current_hedge_ratio']:.2%} |"
            )
        lines += [
            "",
            f"滚动目标持仓 {rolling['final_target_position_mwh']:.1f} MWh，实际合约簿 "
            f"{rolling['book_position_mwh']:.1f} MWh，整档差 {rolling['lot_gap_mwh']:+.1f} MWh；"
            f"最终对冲比例（市场电量口径）{rolling['final_hedge_ratio']:.2%}。",
        ]
    if bridge is None:
        lines += ["", "## 9. T+1 差异桥", "", "未提供 T+1 实际数据，本次只出机制认定与计划表。"]
    else:
        ordered = sorted(bridge["buckets"], key=lambda item: abs(item["amount"]), reverse=True)
        owners = {
            "mechanism_volume": "规则/结算认定（142号）",
            "contract_volume": "交易/持仓",
            "contract_shape": "交易/曲线",
            "output_volume": "运行/核电机组",
            "spot_price": "市场",
        }
        lines += [
            "",
            "## 9. T+1 差异桥（五桶，恒等式残差应为 0）",
            "",
            f"计划收入 {bridge['plan_revenue_cny']:,.0f} CNY，实际收入 {bridge['actual_revenue_cny']:,.0f} CNY，"
            f"差异 {bridge['delta_cny']:+,.0f} CNY，残差 {bridge['identity_gap']:.2e}。",
            "",
            "| 科目 | 类别 | 责任 | 金额（CNY） |",
            "|---|---|---|---:|",
        ]
        for item in ordered:
            lines.append(
                f"| {item['item']} | {item['category']} | {owners[item['category']]} | "
                f"{_signed(item['amount']):+,.0f} |"
            )
        top = ordered[0] if ordered else None
        lines += [
            "",
            f"**最大差异科目**：{top['item'] if top else '—'}，{top['amount']:+,.0f} CNY。" if top else "**最大差异科目**：—",
            "",
            f"计划上网 {bridge['plan_output_energy_mwh']:,.1f} MWh / 机制 "
            f"{bridge['plan_mechanism_energy_mwh']:,.1f} MWh / 合约 {bridge['plan_contract_energy_mwh']:,.1f} MWh"
            f"（市场口径对冲 {bridge['plan_hedge_ratio_on_market']:.2%}）；"
            f"实际上网 {bridge['actual_output_energy_mwh']:,.1f} MWh / 机制 "
            f"{bridge['actual_mechanism_energy_mwh']:,.1f} MWh / 合约 {bridge['actual_contract_energy_mwh']:,.1f} MWh"
            f"（市场口径对冲 {bridge['actual_hedge_ratio_on_market']:.2%}）；"
            f"实际实时均价 {bridge['actual_price_average']:.2f} CNY/MWh，"
            f"负价时段 {bridge['actual_negative_slot_count']} 个。",
            "",
            "> 机制电量偏差按（机制电价 − 计划现货价）估值、上网电量偏差按计划现货价估值，"
            "两者相加正好是总输出变化的影响分解，不是重复计算。",
        ]
    lines += [
        "",
        "## 10. 三个复核问题",
        "",
        "1. 机制电量认定用的是哪个口径（窗口电量 × 80% 还是全日电量 × 80%）？结算单认定值与本包规则推算值差多少？",
        "2. 两条线的差价是否分开核对？合约电量有没有落在机制电量上（重复结算），或漏掉 02:00–05:00 的非机制时段？",
        "3. 负电价时段（尤其无机制兜底的 02:00–05:00）的市场敞口有多少？日前预出清价有没有被误用为结算价？",
        "",
        "## 11. 下一日动作（人工填写）",
        "",
        "- [ ] ",
        "- [ ] ",
        "- [ ] ",
        "",
        "## 12. 告警与边界",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    for item in report["pending"]:
        lines.append(f"- 待核实（{item['grade']}）：{item['item']}")
    lines += [
        f"- {config['meta']['disclaimer']}",
        "- 本表是两线分账口径复核，不是交易中心结算单；机制电量认定、结算价与考核以正式结算结果为准。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, d1_path, t1_path, rolling_path, out_dir):
    """Validate, recognise mechanism energy, settle two lines and write the review."""
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
    rolling_rows = read_rolling(rolling_path, config, report)

    # ① 机制电量认定（21h × 80%，分组拆分）
    mech = build_mechanism(config, report, d1["forecast"])
    # ② 合约簿（电能量差价线的财务持仓）
    position = build_position(config, report)
    # ③ 两条线情景结算 + 分账对账 + 负电价敏感性
    plan = build_plan(config, report, d1, mech, position)
    negative_detail = plan["negative_rows"]
    rolling = build_rolling(config, report, rolling_rows, position, mech)
    bridge = None
    if t1 is not None:
        mech_actual = build_mechanism(config, report, t1["actual_mw"])
        bridge = two_line_bridge(
            d1["forecast"], mech, position, plan["reference_price"],
            t1["actual_mw"], mech_actual, t1["actual_contract_mwh"], t1["actual_rt_price"],
            report["points_per_day"], report["dt_h"],
        )
        negative_detail = negative_detail + negative_slots_detail(
            mech_actual, t1["actual_mw"], t1["actual_rt_price"], report["dt_h"],
            "T+1", report["documented_avg_price_cny_per_mwh"],
        )

    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        out_dir / "book_sheet.csv",
        plan["rows"],
        [
            "date",
            "slot",
            "start",
            "end",
            "output_mw",
            "output_mwh",
            "mechanism_mwh",
            "market_mwh",
            "contract_mwh",
            "contract_price",
            "reference_price",
            "mechanism_cfd_cny",
            "contract_cfd_cny",
            "full_spot_cny",
            "net_exposure_mwh",
            "net_exposure_revenue_cny",
            "total_line_cny",
        ],
    )
    if rolling is not None:
        _write_csv(
            out_dir / "rolling.csv",
            rolling["rows"],
            [
                "day_offset",
                "forecast_market_energy_mwh",
                "position_before_mwh",
                "target_position_mwh",
                "required_trade_mwh",
                "position_after_mwh",
                "current_hedge_ratio",
            ],
        )
    _write_csv(
        out_dir / "negative_price.csv",
        negative_detail,
        [
            "source",
            "slot",
            "start",
            "price_cny_per_mwh",
            "output_mwh",
            "mechanism_mwh",
            "market_residual_mwh",
            "mechanism_line_revenue_cny",
            "residual_revenue_cny",
            "correct_total_cny",
            "illusion_full_mech_cny",
            "illusion_delta_cny",
        ],
    )

    settlement = {
        "instance_id": config["meta"]["instance_id"],
        "trading_day": d1["date"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "pending": report["pending"],
        "mechanism": {
            "document": config["rules"]["mechanism"]["document"],
            "window_hours": report["window_hours"],
            "excluded_window_hours": [list(span) for span in report["excluded_spans"]],
            "mechanism_energy_share": report["mechanism_share"],
            "mechanism_energy_basis": config["rules"]["mechanism"]["mechanism_energy_basis"],
            "documented_avg_price_cny_per_mwh": mech["documented_avg_price_cny_per_mwh"],
            "energy_weighted_price_cny_per_mwh": mech["weighted_price_cny_per_mwh"],
            "groups": [
                {key: group[key] for key in ("id", "units", "capacity_mw", "price_cny_per_mwh",
                                             "energy_mwh", "fixed_revenue_cny")}
                for group in mech["groups"]
            ],
            "output_energy_mwh": mech["output_energy_mwh"],
            "window_energy_mwh": mech["window_energy_mwh"],
            "mechanism_energy_mwh": mech["total_energy_mwh"],
            "market_energy_mwh": mech["market_energy_mwh"],
            "mechanism_share_of_output": mech["mechanism_share_of_output"],
            "fixed_revenue_cny": mech["fixed_revenue_cny"],
        },
        "book": {
            "contracts": [
                {key: item[key] for key in ("id", "kind", "daily_energy_mwh", "share", "price_cny_per_mwh")}
                for item in position["contracts"]
            ],
            "daily_energy_mwh": position["energy_mwh"],
            "weighted_price_cny_per_mwh": plan["contract_line"]["weighted_price"],
        },
        "plan": {
            "output_energy_mwh": plan["forecast_energy_mwh"],
            "mechanism_energy_mwh": plan["mechanism_energy_mwh"],
            "market_energy_mwh": plan["market_energy_mwh"],
            "position_energy_mwh": plan["position_energy_mwh"],
            "hedge_ratio_on_market": plan["hedge_ratio_on_market"],
            "hedge_ratio_on_output": plan["hedge_ratio_on_output"],
            "target_hedge_ratio": plan["target_hedge_ratio"],
            "net_exposure_mwh": plan["net_exposure_mwh"],
            "buy_back_mwh": plan["buy_back_mwh"],
            "sell_surplus_mwh": plan["sell_surplus_mwh"],
            "over_contract_slots": plan["over_contract_slots"],
            "reference_revenue_cny": plan["reference_revenue_cny"],
            "reference_settle": {
                "mechanism_fixed_revenue_cny": plan["reference_settle"]["mechanism_fixed_revenue_cny"],
                "contract_fixed_revenue_cny": plan["reference_settle"]["contract_fixed_revenue_cny"],
                "net_exposure_spot_revenue_cny": plan["reference_settle"]["net_exposure_spot_revenue_cny"],
                "mechanism_cfd_cny": plan["reference_settle"]["mechanism_cfd_cny"],
                "contract_cfd_cny": plan["reference_settle"]["contract_cfd_cny"],
            },
            "identity_gap": plan["identity_gap"],
            "mechanism_line": plan["mechanism_line"],
            "contract_line": plan["contract_line"],
            "expected_revenue_cny": plan["expected_revenue_cny"],
            "expected_full_spot_cny": plan["expected_full_spot_cny"],
            "cvar_10_cny": plan["cvar_10_cny"],
            "required_trade_mwh": plan["required_trade"]["required_trade_mwh"],
            "required_trade_action": plan["required_trade"]["action"],
            "scenarios": plan["scenarios"],
        },
        "rolling": None
        if rolling is None
        else {
            "target_hedge_ratio": rolling["target_hedge_ratio"],
            "final_target_position_mwh": rolling["final_target_position_mwh"],
            "book_position_mwh": rolling["book_position_mwh"],
            "lot_gap_mwh": rolling["lot_gap_mwh"],
            "final_hedge_ratio": rolling["final_hedge_ratio"],
            "days": rolling["rows"],
        },
        "actual": None
        if bridge is None
        else {
            "revenue_cny": bridge["actual_revenue_cny"],
            "output_energy_mwh": bridge["actual_output_energy_mwh"],
            "mechanism_energy_mwh": bridge["actual_mechanism_energy_mwh"],
            "market_energy_mwh": bridge["actual_market_energy_mwh"],
            "contract_energy_mwh": bridge["actual_contract_energy_mwh"],
            "hedge_ratio_on_market": bridge["actual_hedge_ratio_on_market"],
            "rt_price_average_cny_per_mwh": bridge["actual_price_average"],
            "negative_slot_count": bridge["actual_negative_slot_count"],
        },
        "warnings": report["warnings"],
        "files": {
            "book_sheet": "book_sheet.csv",
            "rolling": "rolling.csv" if rolling is not None else None,
            "negative_price": "negative_price.csv",
            "review": "review.md",
            "bridge": "bridge.json" if bridge is not None else None,
        },
    }
    (out_dir / "settlement.json").write_text(
        json.dumps(settlement, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if bridge is not None:
        bridge_out = {
            "plan_revenue_cny": bridge["plan_revenue_cny"],
            "actual_revenue_cny": bridge["actual_revenue_cny"],
            "delta_cny": bridge["delta_cny"],
            "identity_gap": bridge["identity_gap"],
            "plan_output_energy_mwh": bridge["plan_output_energy_mwh"],
            "actual_output_energy_mwh": bridge["actual_output_energy_mwh"],
            "plan_mechanism_energy_mwh": bridge["plan_mechanism_energy_mwh"],
            "actual_mechanism_energy_mwh": bridge["actual_mechanism_energy_mwh"],
            "plan_contract_energy_mwh": bridge["plan_contract_energy_mwh"],
            "actual_contract_energy_mwh": bridge["actual_contract_energy_mwh"],
            "plan_hedge_ratio_on_market": bridge["plan_hedge_ratio_on_market"],
            "actual_hedge_ratio_on_market": bridge["actual_hedge_ratio_on_market"],
            "actual_rt_price_average_cny_per_mwh": bridge["actual_price_average"],
            "actual_negative_slot_count": bridge["actual_negative_slot_count"],
            "buckets": bridge["buckets"],
        }
        (out_dir / "bridge.json").write_text(
            json.dumps(bridge_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _write_csv(
            out_dir / "bridge.csv",
            bridge_out["buckets"],
            ["item", "category", "amount"],
        )
    write_review(
        out_dir / "review.md",
        config,
        report,
        d1,
        mech,
        position,
        plan,
        rolling,
        bridge,
        negative_detail,
        fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "mechanism": mech,
        "position": position,
        "plan": plan,
        "rolling": rolling,
        "bridge": bridge,
        "summary": settlement,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Liaoning nuclear mechanism-price instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", help="D-1 24-slot plan, pre-clearing price and real-time scenario CSV")
    parser.add_argument("--t1", help="T+1 actual CSV; omit to skip the bridge")
    parser.add_argument("--rolling", help="D-7~D-1 rolling market-energy forecast CSV; omit to skip")
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
            print(f"  {item['block']:<24} {item['grade']:<5} {item['source']}")
        for item in report["pending"]:
            print(f"  待核实({item['grade']}): {item['item']}")
        for warning in report["warnings"]:
            print(f"  warning: {warning}")
        mech = config["rules"]["mechanism"]
        prices = "、".join(
            f"{item['group_id']} {item['price_cny_per_kwh']:.4f}" for item in mech["group_prices"]
        )
        print(
            f"  机制电价（{mech['document']}，{mech['status']}）：平均 {mech['average_price_cny_per_kwh']:.4f} 元/kWh；"
            f"{prices}；{mech['window_hours']:.0f}h 窗口 × {mech['mechanism_energy_share']:.0%}"
        )
        print(
            f"  合约 {len(config['book'])} 份财务 CfD，日电量 {report['book_daily_energy_mwh']:.1f} MWh，"
            f"加权价 {report['book_weighted_price']:.2f} CNY/MWh；市场电量份额约 {report['market_share']:.2%}"
        )
        print(
            f"  现货限价：申报 {report['bounds']['declare_floor']:.0f}~{report['bounds']['declare_cap']:.0f}、"
            f"出清 {report['bounds']['clear_floor']:.0f}~{report['bounds']['clear_cap']:.0f} CNY/MWh"
            "（连续结算试运行参数）"
        )
        return 0

    if args.demo:
        d1_path = _resolve_data(config, "d1")
        t1_path = _resolve_data(config, "t1")
        rolling_path = _resolve_data(config, "rolling")
        out_dir = Path(args.out) if args.out != str(HERE / "out") else HERE / "out" / "demo"
    else:
        if not args.d1:
            print("必须提供 --d1，或使用 --demo", file=sys.stderr)
            return 1
        d1_path = Path(args.d1)
        t1_path = Path(args.t1) if args.t1 else None
        rolling_path = Path(args.rolling) if args.rolling else None
        out_dir = Path(args.out)

    try:
        result = run_instance(args.instance, d1_path, t1_path, rolling_path, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    plan = summary["plan"]
    mech = summary["mechanism"]
    print(f"实例：{summary['instance_id']} / 交易日 {summary['trading_day']}")
    print(
        f"① 机制电量认定：窗口 {mech['window_hours']:.0f}h（02:00–05:00 不纳入）× {mech['mechanism_energy_share']:.0%}，"
        f"机制电量 {mech['mechanism_energy_mwh']:,.1f} MWh（占上网 {mech['mechanism_share_of_output']:.2%}），"
        f"市场电量 {mech['market_energy_mwh']:,.1f} MWh"
    )
    print(
        f"② 机制差价结算线（142号）：固定收入 {mech['fixed_revenue_cny']:,.0f} CNY，"
        f"参考价差价 {plan['mechanism_line']['value_cny']:+,.0f} CNY"
    )
    print(
        f"③ 电能量差价结算线（财务 CfD）：合约 {plan['position_energy_mwh']:,.1f} MWh，"
        f"固定收入 {plan['reference_settle']['contract_fixed_revenue_cny']:,.0f} CNY，"
        f"参考价差价 {plan['contract_line']['value_cny']:+,.0f} CNY"
    )
    print(
        f"④ 两线分账对账：总收入 {plan['reference_revenue_cny']:,.0f} = 机制固定 {plan['reference_settle']['mechanism_fixed_revenue_cny']:,.0f}"
        f" + 合约固定 {plan['reference_settle']['contract_fixed_revenue_cny']:,.0f}"
        f" + 净敞口现货 {plan['reference_settle']['net_exposure_spot_revenue_cny']:+,.0f}，"
        f"残差 {plan['identity_gap']:.2e}"
    )
    print(
        f"⑤ 情景与负电价：期望收入 {plan['expected_revenue_cny']:,.0f} CNY，"
        f"CVaR10 {plan['cvar_10_cny']:,.0f} CNY；负价时段 "
        + "、".join(f"情景{s['scenario']}:{s['negative_slot_count']}" for s in plan["scenarios"])
    )
    if result["rolling"] is not None:
        rolling = result["rolling"]
        print(
            f"滚动调仓（市场电量口径）：目标持仓 {rolling['final_target_position_mwh']:,.1f} MWh，"
            f"合约簿 {rolling['book_position_mwh']:,.1f} MWh，整档差 {rolling['lot_gap_mwh']:+,.1f} MWh"
        )
    if result["bridge"] is not None:
        bridge = result["bridge"]
        print(
            f"⑥ T+1 差异桥：计划 {bridge['plan_revenue_cny']:,.0f} → 实际 {bridge['actual_revenue_cny']:,.0f}，"
            f"差异 {bridge['delta_cny']:+,.0f} CNY，残差 {bridge['identity_gap']:.2e}"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
