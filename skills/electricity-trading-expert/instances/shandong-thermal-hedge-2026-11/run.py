#!/usr/bin/env python3
"""Run the Shandong thermal mid/long-term hedge instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the market rules, the unit, the contract book, the
  style profile and the data contract. A trader edits it; no code change is
  needed for a new unit or a new hedge style.
* ``data/d1_demo.csv`` is a 96-point D-1 forecast plus five day-ahead price
  scenarios. Scenarios drive the revenue distribution and CVaR only; the
  contract curves are not re-optimised per scenario.
* ``data/rolling_demo.csv`` is the D-7~D-1 rolling forecast and the position
  before each daily rebalance.
* ``data/t1_demo.csv`` is the T+1 metered output, the settled contract energy
  per slot and the day-ahead price.

The maths lives in ``../tools/hedge.py``: period energy is decomposed to a
96-point contract curve, settled as a financial CfD
``Σ q·c + Σ (g − q)·s``, and the plan-vs-actual revenue gap is split into six
buckets with an exact identity.

All bundled numbers are synthetic grade D. They are not a market forecast, a
live trading signal or investment advice.
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


def validate_instance(config):
    """Validate the six blocks and return a provenance report."""
    meta = _need(config, "meta", "instance")
    for key in ("instance_id", "province", "entity_type", "rule_version", "data_cutoff", "scope"):
        _text(meta, key, "meta")
    rules = _need(config, "rules", "instance")
    asset = _need(config, "asset", "instance")
    policy = _need(config, "policy", "instance")
    book = _need(config, "book", "instance")
    data_contract = _need(config, "data_contract", "instance")

    spot = _rule_block(rules, "spot")
    mid_long = _rule_block(rules, "mid_long_term")
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

    capacity = _number(_need(asset, "capacity_mw", "asset"), "asset.capacity_mw", 1e-9)
    min_output = _number(_need(asset, "min_output_mw", "asset"), "asset.min_output_mw", 0.0)
    if min_output > capacity + 1e-9:
        raise ConfigError("asset.min_output_mw must not exceed asset.capacity_mw")

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
            raise ConfigError(f"{path}.type must be cfd in v1; physical contracts are out of scope")
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
    ceiling = capacity * 24.0 * high_ratio
    if book_daily > ceiling + 1e-9:
        raise ConfigError(
            f"book decomposes to {book_daily:.1f} MWh/day, above capacity × 24 × max_hedge_ratio "
            f"({ceiling:.1f}); a period energy was probably used as a daily energy"
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
    weights = d1.get("scenario_weights", [1.0 / len(scenario_fields)] * len(scenario_fields))
    if len(weights) != len(scenario_fields):
        raise ConfigError("data_contract.d1.scenario_weights must match the scenario fields")
    parsed_weights = [_number(value, "data_contract.d1.scenario_weights", 0.0) for value in weights]
    if abs(sum(parsed_weights) - 1.0) > 1e-9:
        raise ConfigError("data_contract.d1.scenario_weights must sum to 1")

    t1 = _need(data_contract, "t1", "data_contract.t1")
    _text(t1, "file", "data_contract.t1")
    t1_required = _need(t1, "required_fields", "data_contract.t1")
    if not isinstance(t1_required, list) or len(t1_required) == 0:
        raise ConfigError("data_contract.t1.required_fields must be a non-empty list")
    for field in ("date", "slot", "actual_mw", "actual_contract_mwh", "actual_da_price"):
        if field not in t1_required:
            raise ConfigError(f"data_contract.t1.required_fields is missing {field}")
    rolling = _need(data_contract, "rolling", "data_contract.rolling")
    _text(rolling, "file", "data_contract.rolling")
    rolling_required = _need(rolling, "required_fields", "data_contract.rolling")
    for field in ("day_offset", "forecast_output_mwh", "position_before_mwh"):
        if field not in rolling_required:
            raise ConfigError(f"data_contract.rolling.required_fields is missing {field}")

    provenance = []
    for name in ("spot", "mid_long_term", "settlement", "deviation"):
        block = rules[name]
        item = {"block": f"rules.{name}", "grade": block["grade"], "source": block["source"]}
        if block.get("status"):
            item["status"] = block["status"]
        if name == "deviation" and block.get("included") is False:
            item["status"] = "未纳入本包"
        provenance.append(item)

    warnings = [
        "本包只用日前价结算：实时偏差两结算、两个细则考核、供热成本与辅助服务未纳入；日前收入不是最终结算收入。",
        "合约价格、曲线形状与机组出力均为 D 级示例；峰谷时段是合同约定，不是省级分时电价。",
        "目标对冲比例是交易风格，不是监管要求；实际签约还受六签、资金与交易窗口约束。",
        "合同价只做数据合理性校验，不代表省级中长期价格区间。",
        "2026-10-19 现货基本规则征求意见稿未生效；2027 年规则变化必须切段重算。",
    ]

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
        "forecast_field": forecast_field,
        "capacity_mw": capacity,
        "min_output_mw": min_output,
        "book_daily_energy_mwh": book_daily,
        "book_weighted_price": book_weighted_price,
        "book_summaries": summaries,
        "target_hedge_ratio": target,
        "min_hedge_ratio": low_ratio,
        "max_hedge_ratio": high_ratio,
        "price_quantile": price_q,
        "rebalance_start_day": rebalance_start,
        "freeze_day_offset": freeze_offset,
        "contract_kinds": list(mid_long.get("contract_types", allowed_kinds)),
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
        price = _number(row["actual_da_price"], f"{path.name}:actual_da_price@slot{slot}")
        if not (
            report["bounds"]["clear_floor"] - 0.01
            <= price
            <= report["bounds"]["clear_cap"] + 0.01
        ):
            raise ConfigError(
                f"{path.name}:actual_da_price@slot{slot}={price} is outside the clearing band"
            )
        actual_mw.append(output)
        actual_contract.append(contract)
        actual_price.append(price)
    return {
        "date": rows[0]["date"],
        "actual_mw": actual_mw,
        "actual_contract_mwh": actual_contract,
        "actual_da_price": actual_price,
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
            row["forecast_output_mwh"], f"{path.name}:forecast_output_mwh@{index + 1}", 0.0
        )
        position = _number(
            row["position_before_mwh"], f"{path.name}:position_before_mwh@{index + 1}", 0.0
        )
        parsed.append(
            {"day_offset": offset, "forecast_output_mwh": forecast, "position_before_mwh": position}
        )
    parsed.sort(key=lambda item: item["day_offset"])
    if len(parsed) < 2:
        raise ConfigError(f"{path.name}: at least two rolling days are required")
    offsets = [item["day_offset"] for item in parsed]
    if len(set(offsets)) != len(offsets):
        raise ConfigError(f"{path.name}: duplicate day_offset values")
    if offsets[0] == offsets[-1]:
        raise ConfigError(f"{path.name}: rolling days must span more than one day")
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


def build_plan(config, report, d1, position):
    n = report["points_per_day"]
    mtu = report["mtu_min"]
    dt_h = mtu / 60.0
    weights = report["scenario_weights"]
    policy = config["policy"]

    forecast_energy = sum(d1["forecast"]) * dt_h
    ratio = hedge.hedge_ratio(position["energy_mwh"], forecast_energy)
    reference_price = [
        quantile([d1["prices"][s][t] for s in range(len(d1["prices"]))], report["price_quantile"])
        for t in range(n)
    ]
    reference_settle = hedge.settle_book(
        config["book"], d1["forecast"], reference_price, n, mtu
    )
    reference_no_hedge = sum(d1["forecast"][t] * dt_h * reference_price[t] for t in range(n))
    reference_value = hedge.hedge_value(
        config["book"], d1["forecast"], reference_price, n, mtu
    )
    stats = hedge.curve_stats(position["position"], d1["forecast"], reference_price, n, mtu)

    scenarios = []
    for index, prices in enumerate(d1["prices"]):
        settle = hedge.settle_book(config["book"], d1["forecast"], prices, n, mtu)
        no_hedge = sum(d1["forecast"][t] * dt_h * prices[t] for t in range(n))
        scenarios.append(
            {
                "scenario": index + 1,
                "weight": weights[index],
                "mean_price": sum(prices) / n,
                "contract_revenue_cny": settle["contract_revenue_cny"],
                "spot_revenue_cny": settle["spot_revenue_cny"],
                "total_revenue_cny": settle["total_revenue_cny"],
                "no_hedge_revenue_cny": no_hedge,
                "hedge_value_cny": settle["total_revenue_cny"] - no_hedge,
                "hedge_ratio": settle["hedge_ratio"],
                "net_exposure_mwh": settle["net_exposure_mwh"],
            }
        )
    expected_revenue = sum(item["weight"] * item["total_revenue_cny"] for item in scenarios)
    expected_no_hedge = sum(item["weight"] * item["no_hedge_revenue_cny"] for item in scenarios)
    cvar = desk.weighted_cvar(
        [(item["total_revenue_cny"], item["weight"]) for item in scenarios], alpha=0.10
    )
    required = hedge.required_trade(
        forecast_energy, position["energy_mwh"], report["target_hedge_ratio"]
    )

    rows = []
    for slot in range(n):
        gross = d1["forecast"][slot] * dt_h
        q = position["position"][slot]
        c = position["price_curve"][slot]
        s = reference_price[slot]
        rows.append(
            {
                "date": d1["date"],
                "slot": slot,
                "start": d1["start"][slot],
                "end": d1["end"][slot],
                "forecast_mw": d1["forecast"][slot],
                "position_mwh": q,
                "position_mw": q / dt_h,
                "contract_price": c,
                "reference_price": s,
                "hedged_revenue_cny": q * c + (gross - q) * s,
                "no_hedge_revenue_cny": gross * s,
                "basis_cny": q * (c - s),
            }
        )

    return {
        "forecast_energy_mwh": forecast_energy,
        "position_energy_mwh": position["energy_mwh"],
        "hedge_ratio": ratio,
        "target_hedge_ratio": report["target_hedge_ratio"],
        "net_exposure_mwh": forecast_energy - position["energy_mwh"],
        "absolute_exposure_mwh": stats["absolute_exposure_mwh"] if "absolute_exposure_mwh" in stats else stats["mismatch_mwh"],
        "buy_back_mwh": stats["buy_back_mwh"],
        "sell_surplus_mwh": stats["sell_surplus_mwh"],
        "mismatch_mwh": stats["mismatch_mwh"],
        "spot_average": stats["spot_average"],
        "spot_max": stats["spot_max"],
        "spot_min": stats["spot_min"],
        "spot_peak_to_average": stats["spot_peak_to_average"],
        "reference_price": reference_price,
        "reference_settle": reference_settle,
        "reference_revenue_cny": reference_settle["total_revenue_cny"],
        "reference_no_hedge_revenue_cny": reference_no_hedge,
        "reference_hedge_value_cny": reference_value["hedge_value_cny"],
        "carry_cny": reference_value["carry_cny"],
        "shape_cny": reference_value["shape_cny"],
        "hedge_value_identity_gap": reference_value["identity_gap"],
        "weighted_contract_price": reference_value["weighted_contract_price"],
        "time_average_spot": reference_value["time_average_spot"],
        "expected_revenue_cny": expected_revenue,
        "expected_no_hedge_revenue_cny": expected_no_hedge,
        "expected_hedge_value_cny": expected_revenue - expected_no_hedge,
        "cvar_10_cny": cvar,
        "required_trade": required,
        "scenarios": scenarios,
        "rows": rows,
    }


def build_rolling(config, report, rolling_rows, position):
    if rolling_rows is None:
        return None
    target = report["target_hedge_ratio"]
    forecasts = [item["forecast_output_mwh"] for item in rolling_rows]
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
                "forecast_output_mwh": item["forecast_output_mwh"],
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
        "final_hedge_ratio": hedge.hedge_ratio(position["energy_mwh"], final["forecast_output_mwh"]),
    }


def build_bridge(config, report, plan, t1, position):
    n = report["points_per_day"]
    mtu = report["mtu_min"]
    plan_block = {
        "output_mw": [row["forecast_mw"] for row in plan["rows"]],
        "position_curve": position["position"],
        "contract_price_curve": position["price_curve"],
        "spot_prices": plan["reference_price"],
    }
    actual_block = {
        "output_mw": t1["actual_mw"],
        "position_curve": t1["actual_contract_mwh"],
        "contract_price_curve": position["price_curve"],
        "spot_prices": t1["actual_da_price"],
    }
    bridge = hedge.pnl_bridge(plan_block, actual_block, n, mtu)
    owners = {
        "contract_volume": "交易/持仓",
        "contract_shape": "交易/曲线",
        "output_volume": "运行/预测",
        "output_shape": "运行/出力",
        "spot_price": "市场",
        "interaction": "共同",
    }
    for bucket in bridge["buckets"]:
        bucket["owner"] = owners[bucket["category"]]
    bridge["actual_contract_energy_mwh"] = sum(t1["actual_contract_mwh"])
    bridge["actual_output_energy_mwh"] = sum(t1["actual_mw"]) * mtu / 60.0
    bridge["actual_price_average"] = sum(t1["actual_da_price"]) / n
    return bridge


def build_bridge_detail(plan, t1, position, report):
    dt_h = report["mtu_min"] / 60.0
    detail = []
    for slot in range(report["points_per_day"]):
        plan_revenue = (
            position["position"][slot] * position["price_curve"][slot]
            + (plan["rows"][slot]["forecast_mw"] * dt_h - position["position"][slot])
            * plan["reference_price"][slot]
        )
        actual_revenue = (
            t1["actual_contract_mwh"][slot] * position["price_curve"][slot]
            + (t1["actual_mw"][slot] * dt_h - t1["actual_contract_mwh"][slot])
            * t1["actual_da_price"][slot]
        )
        detail.append(
            {
                "slot": slot,
                "start": _slot_time(slot, report["mtu_min"]),
                "plan_output_mw": plan["rows"][slot]["forecast_mw"],
                "actual_output_mw": t1["actual_mw"][slot],
                "plan_position_mwh": position["position"][slot],
                "actual_position_mwh": t1["actual_contract_mwh"][slot],
                "plan_price": plan["reference_price"][slot],
                "actual_price": t1["actual_da_price"][slot],
                "delta_revenue_cny": actual_revenue - plan_revenue,
            }
        )
    detail.sort(key=lambda item: abs(item["delta_revenue_cny"]), reverse=True)
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
        if field in ("contract_price", "reference_price", "plan_price", "actual_price"):
            return f"{value:.2f}"
        if field in ("amount", "delta_revenue_cny", "hedged_revenue_cny", "no_hedge_revenue_cny", "basis_cny"):
            return f"{_signed(value):.2f}"
        if field in ("share", "hedge_ratio", "current_hedge_ratio"):
            return f"{value:.4f}"
        return f"{value:.6f}"
    return value


def write_review(path, config, report, d1, position, plan, rolling, bridge, bridge_detail, fingerprint):
    policy = config["policy"]
    dt_h = report["mtu_min"] / 60.0
    lines = [
        f"# 山东煤电中长期持仓与曲线分解复核表：{config['meta']['instance_id']}",
        "",
        f"- 交易日：{d1['date']}（{report['points_per_day']} 点，{report['mtu_min']} 分钟）",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格档：`{policy['profile_id']}` / 指纹 `{fingerprint}`",
        f"- 机组：{config['asset']['name']}；容量 {report['capacity_mw']:.0f} MW，最小出力 {report['min_output_mw']:.0f} MW",
        f"- 合约簿：{len(position['contracts'])} 份，日分解电量 {position['energy_mwh']:.1f} MWh，"
        f"加权合约价 {plan['weighted_contract_price']:.2f} CNY/MWh",
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
        "## 2. 合约簿与曲线分解",
        "",
        "| 合约 | 类型 | 日电量（MWh） | 占比 | 合约价 | 曲线形状 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in position["contracts"]:
        source = next(c for c in config["book"] if c["id"] == item["id"])
        shape = source["shape"]
        if shape["type"] == "base":
            shape_text = "平段"
        elif shape["type"] == "window":
            shape_text = "峰段 " + "、".join(f"{a:g}–{b:g}" for a, b in shape["windows"])
        elif shape["type"] == "complement":
            shape_text = "谷段（" + "、".join(f"{a:g}–{b:g}" for a, b in shape["windows"]) + " 之外）"
        elif shape["type"] == "anchors":
            shape_text = f"锚点曲线 {len(shape['anchors'])} 点"
        else:
            shape_text = "显式 96 点"
        lines.append(
            f"| {item['id']} | {item['kind']} | {item['daily_energy_mwh']:.1f} | "
            f"{item['share']:.1%} | {item['price_cny_per_mwh']:.2f} | {shape_text} |"
        )
    lines += [
        "",
        f"> 合约期间电量按 `period_days` 分解到日；年度合约不得把年电量当日电量。"
        f"峰谷时段来自合同约定，不是省级分时电价文件。",
        "",
        "## 3. 持仓、对冲比例与曲线匹配",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 预测出力电量 | {plan['forecast_energy_mwh']:.1f} MWh |",
        f"| 合约日电量 | {plan['position_energy_mwh']:.1f} MWh |",
        f"| 对冲比例 | {plan['hedge_ratio']:.2%} |",
        f"| 目标对冲比例 | {plan['target_hedge_ratio']:.0%} |",
        f"| 净敞口（出力 − 合约） | {plan['net_exposure_mwh']:+,.1f} MWh |",
        f"| 买入平仓量 | {plan['buy_back_mwh']:.1f} MWh |",
        f"| 卖出富余量 | {plan['sell_surplus_mwh']:.1f} MWh |",
        f"| 曲线错配量 | {plan['mismatch_mwh']:.1f} MWh |",
        f"| 参考现货均价 | {plan['spot_average']:.2f} CNY/MWh |",
        f"| 参考现货最高/均价 | {plan['spot_peak_to_average']:.2f}× |",
        f"| 所需调仓（达到目标） | {plan['required_trade']['required_trade_mwh']:+,.1f} MWh（{plan['required_trade']['action']}） |",
        "",
        "## 4. 情景收入与 CVaR",
        "",
        "| 情景 | 权重 | 均价 | 合约收入 | 现货偏差收入 | 总收入 | 不对冲收入 | 对冲价值 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in plan["scenarios"]:
        lines.append(
            f"| {item['scenario']} | {item['weight']:.2f} | {item['mean_price']:.1f} | "
            f"{item['contract_revenue_cny']:,.0f} | {item['spot_revenue_cny']:,.0f} | "
            f"{item['total_revenue_cny']:,.0f} | {item['no_hedge_revenue_cny']:,.0f} | "
            f"{item['hedge_value_cny']:+,.0f} |"
        )
    lines += [
        "",
        f"| 期望总收入 | {plan['expected_revenue_cny']:,.0f} CNY |",
        f"| 期望不对冲收入 | {plan['expected_no_hedge_revenue_cny']:,.0f} CNY |",
        f"| 期望对冲价值 | {plan['expected_hedge_value_cny']:+,.0f} CNY |",
        f"| CVaR10（最差 10% 概率平均） | {plan['cvar_10_cny']:,.0f} CNY |",
        "",
        "## 5. 对冲价值分解（参考价）",
        "",
        f"对冲价值 {plan['reference_hedge_value_cny']:+,.0f} CNY = "
        f"均价 carry {plan['carry_cny']:+,.0f} + 曲线形状 {plan['shape_cny']:+,.0f}；"
        f"残差 {plan['hedge_value_identity_gap']:.2e}。",
        "",
        f"> 合约加权价 {plan['weighted_contract_price']:.2f} 高于现货时间均价 "
        f"{plan['time_average_spot']:.2f} 时 carry 为正；峰段合约卖在固定价、而现货峰段更高时，"
        f"曲线项为负。两项必须分开看，不能只报 carry。",
    ]
    if rolling is None:
        lines += ["", "## 6. 滚动调仓", "", "未提供滚动预测文件，本次不做 D-7~D-1 调仓复核。"]
    else:
        lines += [
            "",
            "## 6. 滚动调仓（D-7~D-1）",
            "",
            "| 日偏移 | 预测电量 | 调仓前持仓 | 目标持仓 | 所需交易 | 调仓后持仓 | 调仓前比例 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in rolling["rows"]:
            lines.append(
                f"| {item['day_offset']} | {item['forecast_output_mwh']:.1f} | "
                f"{item['position_before_mwh']:.1f} | {item['target_position_mwh']:.1f} | "
                f"{item['required_trade_mwh']:+,.1f} | {item['position_after_mwh']:.1f} | "
                f"{item['current_hedge_ratio']:.2%} |"
            )
        lines += [
            "",
            f"滚动目标持仓 {rolling['final_target_position_mwh']:.1f} MWh，实际合约簿 "
            f"{rolling['book_position_mwh']:.1f} MWh，整档签约差 {rolling['lot_gap_mwh']:+.1f} MWh；"
            f"最终对冲比例 {rolling['final_hedge_ratio']:.2%}。",
        ]
    if bridge is None:
        lines += ["", "## 7. T+1 差异桥", "", "未提供 T+1 实际数据，本次只出合约簿与计划表。"]
    else:
        ordered = sorted(bridge["buckets"], key=lambda item: abs(item["amount"]), reverse=True)
        lines += [
            "",
            "## 7. T+1 差异桥",
            "",
            f"计划收入 {bridge['plan_revenue_cny']:,.0f} CNY，实际收入 {bridge['actual_revenue_cny']:,.0f} CNY，"
            f"差异 {bridge['delta_cny']:+,.0f} CNY，残差 {bridge['identity_gap']:.2e}。",
            "",
            "| 科目 | 类别 | 责任 | 金额（CNY） |",
            "|---|---|---|---:|",
        ]
        for item in ordered:
            lines.append(
                f"| {item['item']} | {item['category']} | {item['owner']} | {_signed(item['amount']):+,.0f} |"
            )
        top = ordered[0] if ordered else None
        lines += [
            "",
            f"**最大差异科目**：{top['item'] if top else '—'}，{top['amount']:+,.0f} CNY。" if top else "**最大差异科目**：—",
            "",
            f"计划合约电量 {bridge['plan_contract_energy_mwh']:.1f} MWh / 出力 "
            f"{bridge['plan_output_energy_mwh']:.1f} MWh（对冲 {bridge['plan_hedge_ratio']:.2%}）；"
            f"实际合约电量 {bridge['actual_contract_energy_mwh']:.1f} MWh / 出力 "
            f"{bridge['actual_output_energy_mwh']:.1f} MWh（对冲 {bridge['actual_hedge_ratio']:.2%}）；"
            f"实际日前均价 {bridge['actual_price_average']:.2f} CNY/MWh。",
            "",
        ]
        if bridge_detail:
            lines += [
                "**收入偏差最大的 5 个时段**：",
                "",
                "| 时段 | 计划出力 | 实际出力 | 计划合约量 | 实际合约量 | 计划价 | 实际价 | 收入差（CNY） |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for item in bridge_detail:
                lines.append(
                    f"| {item['start']} | {item['plan_output_mw']:.1f} | {item['actual_output_mw']:.1f} | "
                    f"{item['plan_position_mwh']:.1f} | {item['actual_position_mwh']:.1f} | "
                    f"{item['plan_price']:.2f} | {item['actual_price']:.2f} | "
                    f"{_signed(item['delta_revenue_cny']):+,.0f} |"
                )
    lines += [
        "",
        "## 8. 三个复核问题",
        "",
        "1. 对冲比例是按总电量还是分时段计算？峰段合约占比与峰段出力是否匹配？",
        "2. 合约曲线是合同约定、典型曲线还是预测曲线？换曲线后 carry 与形状项各变多少？",
        "3. 差异桥的最大科目归因到合约量、合约曲线、出力预测、现货价还是交互？证据包是否齐全？",
        "",
        "## 9. 下一日动作（人工填写）",
        "",
        "- [ ] ",
        "- [ ] ",
        "- [ ] ",
        "",
        "## 10. 告警与边界",
        "",
    ]
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    lines += [
        f"- {config['meta']['disclaimer']}",
        "- 本表是合约簿与曲线口径复核，不是交易中心结算单；实际结算价、合约电量与考核以正式结算结果为准。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, d1_path, t1_path, rolling_path, out_dir):
    """Validate, decompose the book, evaluate scenarios and write the review."""
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

    position = build_position(config, report)
    plan = build_plan(config, report, d1, position)
    rolling = build_rolling(config, report, rolling_rows, position)
    bridge = None
    bridge_detail = None
    if t1 is not None:
        bridge = build_bridge(config, report, plan, t1, position)
        bridge_detail = build_bridge_detail(plan, t1, position, report)

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
            "forecast_mw",
            "position_mwh",
            "position_mw",
            "contract_price",
            "reference_price",
            "hedged_revenue_cny",
            "no_hedge_revenue_cny",
            "basis_cny",
        ],
    )
    if rolling is not None:
        _write_csv(
            out_dir / "rolling.csv",
            rolling["rows"],
            [
                "day_offset",
                "forecast_output_mwh",
                "position_before_mwh",
                "target_position_mwh",
                "required_trade_mwh",
                "position_after_mwh",
                "current_hedge_ratio",
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
        "book": {
            "contracts": [
                {key: item[key] for key in ("id", "kind", "daily_energy_mwh", "share", "price_cny_per_mwh")}
                for item in position["contracts"]
            ],
            "daily_energy_mwh": position["energy_mwh"],
            "weighted_price_cny_per_mwh": plan["weighted_contract_price"],
        },
        "plan": {
            "forecast_energy_mwh": plan["forecast_energy_mwh"],
            "position_energy_mwh": plan["position_energy_mwh"],
            "hedge_ratio": plan["hedge_ratio"],
            "target_hedge_ratio": plan["target_hedge_ratio"],
            "net_exposure_mwh": plan["net_exposure_mwh"],
            "buy_back_mwh": plan["buy_back_mwh"],
            "sell_surplus_mwh": plan["sell_surplus_mwh"],
            "mismatch_mwh": plan["mismatch_mwh"],
            "spot_average_cny_per_mwh": plan["spot_average"],
            "spot_peak_to_average": plan["spot_peak_to_average"],
            "reference_revenue_cny": plan["reference_revenue_cny"],
            "expected_revenue_cny": plan["expected_revenue_cny"],
            "expected_no_hedge_revenue_cny": plan["expected_no_hedge_revenue_cny"],
            "expected_hedge_value_cny": plan["expected_hedge_value_cny"],
            "cvar_10_cny": plan["cvar_10_cny"],
            "reference_hedge_value_cny": plan["reference_hedge_value_cny"],
            "carry_cny": plan["carry_cny"],
            "shape_cny": plan["shape_cny"],
            "hedge_value_identity_gap": plan["hedge_value_identity_gap"],
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
            "contract_energy_mwh": bridge["actual_contract_energy_mwh"],
            "output_energy_mwh": bridge["actual_output_energy_mwh"],
            "hedge_ratio": bridge["actual_hedge_ratio"],
            "da_price_average_cny_per_mwh": bridge["actual_price_average"],
        },
        "warnings": report["warnings"],
        "files": {
            "book_sheet": "book_sheet.csv",
            "rolling": "rolling.csv" if rolling is not None else None,
            "review": "review.md",
            "bridge": "bridge.json" if bridge is not None else None,
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if bridge is not None:
        bridge_out = {
            "plan_revenue_cny": bridge["plan_revenue_cny"],
            "actual_revenue_cny": bridge["actual_revenue_cny"],
            "delta_cny": bridge["delta_cny"],
            "identity_gap": bridge["identity_gap"],
            "plan_contract_energy_mwh": bridge["plan_contract_energy_mwh"],
            "actual_contract_energy_mwh": bridge["actual_contract_energy_mwh"],
            "plan_output_energy_mwh": bridge["plan_output_energy_mwh"],
            "actual_output_energy_mwh": bridge["actual_output_energy_mwh"],
            "plan_hedge_ratio": bridge["plan_hedge_ratio"],
            "actual_hedge_ratio": bridge["actual_hedge_ratio"],
            "actual_price_average": bridge["actual_price_average"],
            "buckets": bridge["buckets"],
            "top_revenue_slots": bridge_detail,
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
        position,
        plan,
        rolling,
        bridge,
        bridge_detail,
        fingerprint,
    )
    return {
        "config": config,
        "report": report,
        "d1": d1,
        "position": position,
        "plan": plan,
        "rolling": rolling,
        "bridge": bridge,
        "bridge_detail": bridge_detail,
        "summary": summary,
        "out_dir": out_dir,
    }


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shandong thermal mid/long-term hedge instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--d1", help="D-1 96-point forecast and price scenario CSV")
    parser.add_argument("--t1", help="T+1 actual CSV; omit to skip the bridge")
    parser.add_argument("--rolling", help="D-7~D-1 rolling forecast CSV; omit to skip")
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
            print(f"  {item['block']:<28} {item['grade']:<5} {item['source']}")
        for warning in report["warnings"]:
            print(f"  warning: {warning}")
        print(
            f"  合约 {len(config['book'])} 份，日电量 {report['book_daily_energy_mwh']:.1f} MWh，"
            f"加权价 {report['book_weighted_price']:.2f} CNY/MWh"
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
    print(f"实例：{summary['instance_id']} / 交易日 {summary['trading_day']}")
    print(
        f"合约簿：日电量 {plan['position_energy_mwh']:.1f} MWh，"
        f"预测出力 {plan['forecast_energy_mwh']:.1f} MWh，"
        f"对冲比例 {plan['hedge_ratio']:.2%}"
    )
    print(
        f"参考价收入 {plan['reference_revenue_cny']:,.0f} CNY；"
        f"期望收入 {plan['expected_revenue_cny']:,.0f} CNY，CVaR10 {plan['cvar_10_cny']:,.0f} CNY"
    )
    print(
        f"对冲价值 {plan['reference_hedge_value_cny']:+,.0f} CNY "
        f"（carry {plan['carry_cny']:+,.0f} + shape {plan['shape_cny']:+,.0f}，"
        f"残差 {plan['hedge_value_identity_gap']:.2e}）"
    )
    if result["rolling"] is not None:
        rolling = result["rolling"]
        print(
            f"滚动调仓：目标持仓 {rolling['final_target_position_mwh']:.1f} MWh，"
            f"合约簿 {rolling['book_position_mwh']:.1f} MWh，整档差 {rolling['lot_gap_mwh']:+.1f} MWh"
        )
    if result["bridge"] is not None:
        bridge = result["bridge"]
        print(
            f"差异桥：计划 {bridge['plan_revenue_cny']:,.0f} → 实际 {bridge['actual_revenue_cny']:,.0f}，"
            f"差异 {bridge['delta_cny']:+,.0f} CNY，残差 {bridge['identity_gap']:.2e}"
        )
    print(f"输出目录：{result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
