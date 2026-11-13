#!/usr/bin/env python3
"""Run the Gansu 200 MW wind-to-Shandong interprovincial portfolio case.

The engine is shared, the instance is local:

* ``instance.json`` holds the interprovincial, delivery and market rules, the
  project assumptions and the portfolio style.
* ``data/profile_demo.csv`` is a synthetic first-operating-year profile:
  generation, contract weight, Shandong landing spot price and green share.

The runner compares three portfolios: sell everything in Gansu, sign a 70%
interprovincial contract and export the surplus to the interprovincial spot
market, or sign the same contract and sell the surplus locally. Delivery fees
and line loss are deducted from the seller's landing-price revenue.

All bundled numbers are synthetic grade D. They are not a trading instruction
or investment advice.
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
STRATEGIES = ("local_only", "contract_spot", "contract_local")
LABELS = {
    "local_only": "全部本地",
    "contract_spot": "合同 + 省间现货余量",
    "contract_local": "合同 + 本地余量",
}


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
    interprovincial = _rule_block(rules, "interprovincial", report)
    delivery = _rule_block(rules, "delivery", report)
    market = _rule_block(rules, "market", report)

    min_bid = _number(_need(interprovincial, "min_bid_mw", "rules.interprovincial"), "rules.interprovincial.min_bid_mw", 0.0)
    bid_step = _number(_need(interprovincial, "bid_step_cny_per_mwh", "rules.interprovincial"), "rules.interprovincial.bid_step_cny_per_mwh", 0.0)
    max_multiple = _number(_need(interprovincial, "max_bid_multiple_of_provincial_cap", "rules.interprovincial"), "rules.interprovincial.max_bid_multiple_of_provincial_cap", 0.0)
    reference = _text(interprovincial, "settlement_reference", "rules.interprovincial")
    if reference != "receiving_landing":
        raise ConfigError("本包只实现受端落地价结算")
    if min_bid <= 0 or bid_step <= 0 or max_multiple <= 0:
        raise ConfigError("申报单位、报价步长与限价倍数必须为正")

    send_price = _number(_need(delivery, "send_province_cny_per_kwh", "rules.delivery"), "rules.delivery.send_province_cny_per_kwh", 0.0)
    regional = _number(_need(delivery, "regional_grid_cny_per_kwh", "rules.delivery"), "rules.delivery.regional_grid_cny_per_kwh", 0.0)
    dedicated = _number(_need(delivery, "dedicated_project_cny_per_kwh", "rules.delivery"), "rules.delivery.dedicated_project_cny_per_kwh", 0.0)
    loss = _number(_need(delivery, "loss_rate", "rules.delivery"), "rules.delivery.loss_rate", 0.0, 0.30)
    fee = send_price + regional + dedicated
    if fee <= 0:
        raise ConfigError("输电价合计必须为正")

    contract_price = _number(_need(market, "contract_price_cny_per_kwh", "rules.market"), "rules.market.contract_price_cny_per_kwh", 0.0)
    local_price = _number(_need(market, "local_price_cny_per_kwh", "rules.market"), "rules.market.local_price_cny_per_kwh", 0.0)
    green_premium = _number(_need(market, "green_premium_cny_per_kwh", "rules.market"), "rules.market.green_premium_cny_per_kwh", 0.0)
    if contract_price <= 0 or local_price <= 0:
        raise ConfigError("合同价与本地价必须为正")

    project = _need(config, "project", "instance")
    capacity = _number(_need(project, "capacity_mw", "project"), "project.capacity_mw", 0.0)
    p50 = _number(_need(project, "p50_hours", "project"), "project.p50_hours", 0.0, 8760.0)
    _text(project, "cod", "project")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", _text(project, "cod", "project")):
        raise ConfigError("project.cod 必须是 YYYY-MM-DD")
    _grade(project, "project")
    _text(project, "source", "project")
    if capacity <= 0 or p50 <= 0:
        raise ConfigError("装机容量与 P50 利用小时必须为正")

    policy = _need(config, "policy", "instance")
    profile_id = _text(policy, "profile_id", "policy")
    ratio = _number(_need(policy, "contract_ratio", "policy"), "policy.contract_ratio", 0.0, 1.0)
    strategies = _need(policy, "strategies", "policy")
    if not isinstance(strategies, list) or set(strategies) != set(STRATEGIES):
        raise ConfigError("policy.strategies 必须包含 local_only / contract_spot / contract_local 三项")
    shortfall = _need(policy, "shortfall_reference", "policy")
    if _text(shortfall, "contract_spot", "policy.shortfall_reference") != "spot_landing":
        raise ConfigError("contract_spot 的偏差参考必须是 spot_landing")
    if _text(shortfall, "contract_local", "policy.shortfall_reference") != "local_send":
        raise ConfigError("contract_local 的偏差参考必须是 local_send")
    _text(policy, "decision_rule", "policy")
    _grade(policy, "policy")

    contract = _need(config, "data_contract", "instance")
    profile = _need(contract, "profile", "data_contract")
    _text(profile, "file", "data_contract.profile")
    fields = _need(profile, "fields", "data_contract.profile")
    required = {"month", "generation_mwh", "contract_weight", "spot_price_cny_per_kwh", "green_ratio"}
    if not isinstance(fields, list) or not required.issubset(set(fields)):
        raise ConfigError("data_contract.profile.fields 必须包含 month / generation_mwh / contract_weight / spot_price_cny_per_kwh / green_ratio")

    return {
        "config": config,
        "report": report,
        "meta": meta,
        "interprovincial": interprovincial,
        "delivery": delivery,
        "market": market,
        "project": project,
        "policy": policy,
        "profile": profile,
        "values": {
            "min_bid": min_bid,
            "bid_step": bid_step,
            "max_multiple": max_multiple,
            "send_price": send_price,
            "regional": regional,
            "dedicated": dedicated,
            "loss": loss,
            "fee": fee,
            "contract_price": contract_price,
            "local_price": local_price,
            "green_premium": green_premium,
            "capacity": capacity,
            "p50": p50,
            "ratio": ratio,
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

    for field in ("month", "generation_mwh", "contract_weight", "spot_price_cny_per_kwh", "green_ratio"):
        if field not in fields:
            raise ConfigError(f"profile CSV 缺少字段 {field}")
    if len(rows) != 12:
        raise ConfigError(f"profile 必须包含 12 个月，实际 {len(rows)} 行")

    months, generation, weights, spot, green = [], [], [], [], []
    for index, row in enumerate(rows, start=2):
        month = (row.get("month") or "").strip()
        if not MONTH_RE.match(month):
            raise ConfigError(f"profile 第 {index} 行 month 不是 YYYY-MM")
        if month in months:
            raise ConfigError(f"profile 第 {index} 行 month 重复: {month}")
        gen = _number(float(row["generation_mwh"]), f"profile 第 {index} 行 generation_mwh", 0.0)
        weight = _number(float(row["contract_weight"]), f"profile 第 {index} 行 contract_weight", 0.0, 1.0)
        price = _number(float(row["spot_price_cny_per_kwh"]), f"profile 第 {index} 行 spot_price_cny_per_kwh", 0.0, 2.0)
        ratio = _number(float(row["green_ratio"]), f"profile 第 {index} 行 green_ratio", 0.0, 1.0)
        if gen <= 0:
            raise ConfigError(f"profile 第 {index} 行 generation_mwh 必须为正")
        months.append(month)
        generation.append(gen)
        weights.append(weight)
        spot.append(price)
        green.append(ratio)

    if len({month.split("-")[0] for month in months}) != 1:
        raise ConfigError("profile 必须覆盖同一个自然年")
    if months != sorted(months):
        raise ConfigError("profile 必须按月份升序排列")
    if abs(sum(weights) - 1.0) > 1e-3:
        raise ConfigError(f"contract_weight 合计必须为 1，实际 {sum(weights):.6f}")

    total = sum(generation)
    planned = bundle["values"]["capacity"] * bundle["values"]["p50"]
    warnings = []
    if not 0.8 * planned <= total <= 1.2 * planned:
        warnings.append(
            f"年度发电量 {total:,.0f} MWh 偏离计划电量 {planned:,.0f} MWh 超过 20%，请核对资源数据"
        )
    return {
        "months": months,
        "generation": generation,
        "weights": weights,
        "spot": spot,
        "green": green,
        "total_generation": total,
        "planned_generation": planned,
        "warnings": warnings,
    }


def compute(bundle, profile, overrides=None):
    overrides = overrides or {}
    values = bundle["values"]
    loss = overrides.get("loss", values["loss"])
    fee = values["fee"] * overrides.get("delivery_scale", 1.0)
    contract_price = overrides.get("contract_price", values["contract_price"])
    local_price = overrides.get("local_price", values["local_price"])
    green_premium = overrides.get("green_premium", values["green_premium"])
    contract_ratio = overrides.get("contract_ratio", values["ratio"])
    spot_scale = overrides.get("spot_scale", 1.0)
    generation_scale = overrides.get("generation_scale", 1.0)
    planned = profile["planned_generation"]

    monthly = []
    for month, gen, weight, spot, green in zip(
        profile["months"],
        profile["generation"],
        profile["weights"],
        profile["spot"],
        profile["green"],
    ):
        generation = gen * generation_scale
        spot_price = spot * spot_scale
        contract_mwh = planned * contract_ratio * weight
        own_contract = min(generation, contract_mwh)
        surplus = max(generation - contract_mwh, 0.0)
        shortfall = max(contract_mwh - generation, 0.0)
        contract_energy = own_contract * (1.0 - loss) * (contract_price - fee) * 1000.0
        green_revenue = own_contract * green * (1.0 - loss) * green_premium * 1000.0
        spot_net = surplus * (1.0 - loss) * (spot_price - fee) * 1000.0
        local_surplus = surplus * local_price * 1000.0
        shortfall_spot = shortfall * (contract_price - spot_price) * 1000.0
        shortfall_local = shortfall * (contract_price - local_price / (1.0 - loss) - fee) * 1000.0
        local_only = generation * local_price * 1000.0
        contract_spot = contract_energy + green_revenue + spot_net + shortfall_spot
        contract_local = contract_energy + green_revenue + local_surplus + shortfall_local
        monthly.append(
            {
                "month": month,
                "generation_mwh": generation,
                "contract_mwh": contract_mwh,
                "own_contract_mwh": own_contract,
                "surplus_mwh": surplus,
                "shortfall_mwh": shortfall,
                "spot_price_cny_per_kwh": spot_price,
                "green_ratio": green,
                "contract_energy_cny": contract_energy,
                "green_premium_cny": green_revenue,
                "spot_net_cny": spot_net,
                "local_surplus_cny": local_surplus,
                "shortfall_spot_cny": shortfall_spot,
                "shortfall_local_cny": shortfall_local,
                "local_only_cny": local_only,
                "contract_spot_cny": contract_spot,
                "contract_local_cny": contract_local,
                "delta_spot_vs_local_cny": contract_spot - local_only,
                "delta_local_vs_local_cny": contract_local - local_only,
            }
        )

    total_generation = sum(row["generation_mwh"] for row in monthly)
    total_contract = sum(row["contract_mwh"] for row in monthly)
    total_own_contract = sum(row["own_contract_mwh"] for row in monthly)
    total_surplus = sum(row["surplus_mwh"] for row in monthly)
    total_shortfall = sum(row["shortfall_mwh"] for row in monthly)
    total_green = sum(row["own_contract_mwh"] * row["green_ratio"] for row in monthly)
    weighted_spot = (
        capture_price(
            [row["spot_price_cny_per_kwh"] for row in monthly],
            [row["surplus_mwh"] for row in monthly],
        )
        if total_surplus > 0
        else 0.0
    )
    weighted_green = total_green / total_own_contract if total_own_contract > 0 else 0.0

    contract_energy = sum(row["contract_energy_cny"] for row in monthly)
    green_revenue = sum(row["green_premium_cny"] for row in monthly)
    spot_net = sum(row["spot_net_cny"] for row in monthly)
    local_surplus = sum(row["local_surplus_cny"] for row in monthly)
    shortfall_spot = sum(row["shortfall_spot_cny"] for row in monthly)
    shortfall_local = sum(row["shortfall_local_cny"] for row in monthly)
    local_only = sum(row["local_only_cny"] for row in monthly)

    strategies = [
        {
            "strategy": "local_only",
            "label": LABELS["local_only"],
            "contract_mwh": 0.0,
            "own_contract_mwh": 0.0,
            "spot_mwh": 0.0,
            "local_mwh": total_generation,
            "shortfall_mwh": 0.0,
            "contract_energy_cny": 0.0,
            "green_premium_cny": 0.0,
            "spot_net_cny": 0.0,
            "local_net_cny": local_only,
            "shortfall_net_cny": 0.0,
            "total_revenue_cny": local_only,
            "net_price_cny_per_kwh": local_only / (total_generation * 1000.0),
        },
        {
            "strategy": "contract_spot",
            "label": LABELS["contract_spot"],
            "contract_mwh": total_contract,
            "own_contract_mwh": total_own_contract,
            "spot_mwh": total_surplus,
            "local_mwh": 0.0,
            "shortfall_mwh": total_shortfall,
            "contract_energy_cny": contract_energy,
            "green_premium_cny": green_revenue,
            "spot_net_cny": spot_net,
            "local_net_cny": 0.0,
            "shortfall_net_cny": shortfall_spot,
            "total_revenue_cny": contract_energy + green_revenue + spot_net + shortfall_spot,
            "net_price_cny_per_kwh": (contract_energy + green_revenue + spot_net + shortfall_spot)
            / (total_generation * 1000.0),
        },
        {
            "strategy": "contract_local",
            "label": LABELS["contract_local"],
            "contract_mwh": total_contract,
            "own_contract_mwh": total_own_contract,
            "spot_mwh": 0.0,
            "local_mwh": total_surplus,
            "shortfall_mwh": total_shortfall,
            "contract_energy_cny": contract_energy,
            "green_premium_cny": green_revenue,
            "spot_net_cny": 0.0,
            "local_net_cny": local_surplus,
            "shortfall_net_cny": shortfall_local,
            "total_revenue_cny": contract_energy + green_revenue + local_surplus + shortfall_local,
            "net_price_cny_per_kwh": (contract_energy + green_revenue + local_surplus + shortfall_local)
            / (total_generation * 1000.0),
        },
    ]
    best = max(strategies, key=lambda row: row["total_revenue_cny"])
    for row in strategies:
        row["delta_vs_local_cny"] = row["total_revenue_cny"] - local_only
        row["delta_vs_best_cny"] = row["total_revenue_cny"] - best["total_revenue_cny"]

    contract_net_energy = (1.0 - loss) * (contract_price - fee)
    contract_net_green = contract_net_energy + weighted_green * (1.0 - loss) * green_premium
    spot_net_price = (1.0 - loss) * (weighted_spot - fee) if total_surplus > 0 else 0.0
    return {
        "monthly": monthly,
        "strategies": strategies,
        "best": best,
        "metrics": {
            "total_generation_mwh": total_generation,
            "total_contract_mwh": total_contract,
            "own_contract_mwh": total_own_contract,
            "surplus_mwh": total_surplus,
            "shortfall_mwh": total_shortfall,
            "green_mwh": total_green,
            "weighted_green_ratio": weighted_green,
            "weighted_spot_price_cny_per_kwh": weighted_spot,
            "contract_net_energy_cny_per_kwh": contract_net_energy,
            "contract_net_green_cny_per_kwh": contract_net_green,
            "spot_net_price_cny_per_kwh": spot_net_price,
            "local_price_cny_per_kwh": local_price,
            "fee_cny_per_kwh": fee,
            "loss_rate": loss,
            "contract_price_cny_per_kwh": contract_price,
            "green_premium_cny_per_kwh": green_premium,
            "contract_ratio": contract_ratio,
        },
    }


def build_sensitivity(bundle, profile, base):
    base_best = base["best"]["total_revenue_cny"]
    cases = [
        ("基准", "70% 合同 + 余量二选一", {}),
        ("输电价 +20%", "送出省、区域与专项工程输电价同比例上升", {"delivery_scale": 1.20}),
        ("线损 7%", "通道线损由 5% 升至 7%", {"loss": 0.07}),
        ("省间现货 +30%", "山东落地现货价整体上浮 30%", {"spot_scale": 1.30}),
        ("省间现货 −20%", "山东落地现货价整体下调 20%", {"spot_scale": 0.80}),
        ("合同价 −0.02", "合同落地价由 0.33 降至 0.31 元/kWh", {"contract_price": 0.31}),
        ("本地价 0.20", "甘肃本地价由 0.22 降至 0.20 元/kWh", {"local_price": 0.20}),
        ("本地价 0.24", "甘肃本地价由 0.22 升至 0.24 元/kWh", {"local_price": 0.24}),
        ("合同比例 50%", "合同电量由 70% 降至 50%", {"contract_ratio": 0.50}),
        ("合同比例 80%", "合同电量由 70% 升至 80%", {"contract_ratio": 0.80}),
        ("发电量 −10%", "实际发电量整体下降 10%，合同电量不变", {"generation_scale": 0.90}),
        ("绿电溢价 0", "绿电环境溢价由 0.02 降至 0", {"green_premium": 0.0}),
    ]
    rows = []
    for name, change, overrides in cases:
        result = compute(bundle, profile, overrides)
        best = result["best"]
        rows.append(
            {
                "case": name,
                "change": change,
                "local_only_cny": result["strategies"][0]["total_revenue_cny"],
                "contract_spot_cny": result["strategies"][1]["total_revenue_cny"],
                "contract_local_cny": result["strategies"][2]["total_revenue_cny"],
                "best_strategy": best["label"],
                "best_net_cny": best["total_revenue_cny"],
                "best_price_cny_per_kwh": best["net_price_cny_per_kwh"],
                "delta_vs_base_best_cny": best["total_revenue_cny"] - base_best,
            }
        )
    return rows


def _fmt_wan(value):
    return f"{value / 1e4:,.2f}"


def _fmt_price(value):
    return f"{value:.4f}"


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

    delivery_rows = [
        {
            "item": "送出省输电价",
            "value": values["send_price"],
            "unit": "CNY/kWh（落地电量）",
            "grade": "B",
            "note": "2027 年送出省输电价原则上不超过 3 分/kWh；本实例取 1.5 分",
        },
        {
            "item": "区域电网电量电价",
            "value": values["regional"],
            "unit": "CNY/kWh（落地电量）",
            "grade": "B",
            "note": "西北区域电网电量电价样本 1.21 分/kWh",
        },
        {
            "item": "专项工程输电价",
            "value": values["dedicated"],
            "unit": "CNY/kWh（落地电量）",
            "grade": "D",
            "note": "合成通道取 5.5 分；2027 年专项工程区间 0.81–8.36 分/kWh",
        },
        {
            "item": "输电价合计",
            "value": metrics["fee_cny_per_kwh"],
            "unit": "CNY/kWh（落地电量）",
            "grade": "C/D",
            "note": "三项相加，未含落地省输配电价、系统运行费与政府性基金",
        },
        {
            "item": "线损率",
            "value": metrics["loss_rate"],
            "unit": "比例",
            "grade": "D",
            "note": "合成通道取 5%；2027 年专项工程线损区间 1%–7%",
        },
        {
            "item": "合同价网损成本",
            "value": metrics["contract_price_cny_per_kwh"] * metrics["loss_rate"],
            "unit": "CNY/kWh（发电量）",
            "grade": "D",
            "note": "按合同落地价计的损失电量价值",
        },
        {
            "item": "现货价网损成本",
            "value": metrics["weighted_spot_price_cny_per_kwh"] * metrics["loss_rate"],
            "unit": "CNY/kWh（发电量）",
            "grade": "D",
            "note": "按加权现货落地价计的损失电量价值",
        },
        {
            "item": "合同综合扣减",
            "value": metrics["loss_rate"] * metrics["contract_price_cny_per_kwh"]
            + (1.0 - metrics["loss_rate"]) * metrics["fee_cny_per_kwh"],
            "unit": "CNY/kWh（发电量）",
            "grade": "D",
            "note": "网损成本 + 按落地电量计的输电价",
        },
        {
            "item": "现货综合扣减",
            "value": metrics["loss_rate"] * metrics["weighted_spot_price_cny_per_kwh"]
            + (1.0 - metrics["loss_rate"]) * metrics["fee_cny_per_kwh"],
            "unit": "CNY/kWh（发电量）",
            "grade": "D",
            "note": "网损成本 + 按落地电量计的输电价",
        },
        {
            "item": "落地省输配电价",
            "value": 0.0,
            "unit": "CNY/kWh",
            "grade": "A",
            "note": "由购电方承担，未计入卖方扣减；真实报价须按山东目录另算",
        },
    ]

    warnings = list(profile["warnings"])
    if metrics["shortfall_mwh"] > 0:
        warnings.append(
            f"合同曲线与资源不匹配：{metrics['shortfall_mwh']:,.1f} MWh 需按偏差价回购"
        )
    if metrics["spot_net_price_cny_per_kwh"] < metrics["local_price_cny_per_kwh"]:
        warnings.append(
            f"省间现货余量净价 {metrics['spot_net_price_cny_per_kwh']:.4f} 低于甘肃本地 "
            f"{metrics['local_price_cny_per_kwh']:.4f} 元/kWh，余量应优先本地消纳"
        )
    spot_total = base["strategies"][1]["total_revenue_cny"]
    local_total = base["strategies"][0]["total_revenue_cny"]
    if spot_total < local_total:
        warnings.append("合同 + 省间现货组合的净收入低于全部本地，现货外送未覆盖通道成本")
    if base["best"]["strategy"] != "contract_local":
        warnings.append(f"基准最优策略为 {base['best']['label']}，请复核组合假设")
    deduction = metrics["loss_rate"] * metrics["contract_price_cny_per_kwh"] + (
        1.0 - metrics["loss_rate"]
    ) * metrics["fee_cny_per_kwh"]
    if deduction > 0.09:
        warnings.append(f"合同价综合扣减 {deduction:.4f} 元/kWh，已超过 9 分/kWh")
    if metrics["contract_price_cny_per_kwh"] - metrics["local_price_cny_per_kwh"] < 0.05:
        warnings.append("合同落地价与本地价差不足 5 分/kWh，扣通道费后空间有限")

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
            "planned_generation_mwh": profile["planned_generation"],
            "contract_ratio": metrics["contract_ratio"],
            "contract_price_cny_per_kwh": metrics["contract_price_cny_per_kwh"],
            "local_price_cny_per_kwh": metrics["local_price_cny_per_kwh"],
            "green_premium_cny_per_kwh": metrics["green_premium_cny_per_kwh"],
            "delivery_fee_cny_per_kwh": metrics["fee_cny_per_kwh"],
            "loss_rate": metrics["loss_rate"],
        },
        "volumes": {
            "generation_mwh": metrics["total_generation_mwh"],
            "contract_mwh": metrics["total_contract_mwh"],
            "own_contract_mwh": metrics["own_contract_mwh"],
            "surplus_mwh": metrics["surplus_mwh"],
            "shortfall_mwh": metrics["shortfall_mwh"],
            "green_mwh": metrics["green_mwh"],
            "weighted_green_ratio": metrics["weighted_green_ratio"],
        },
        "prices": {
            "weighted_spot_cny_per_kwh": metrics["weighted_spot_price_cny_per_kwh"],
            "contract_net_energy_cny_per_kwh": metrics["contract_net_energy_cny_per_kwh"],
            "contract_net_green_cny_per_kwh": metrics["contract_net_green_cny_per_kwh"],
            "spot_net_cny_per_kwh": metrics["spot_net_price_cny_per_kwh"],
            "local_cny_per_kwh": metrics["local_price_cny_per_kwh"],
        },
        "delivery": {
            "send_province_cny_per_kwh": values["send_price"],
            "regional_grid_cny_per_kwh": values["regional"],
            "dedicated_project_cny_per_kwh": values["dedicated"],
            "fee_cny_per_kwh": metrics["fee_cny_per_kwh"],
            "loss_rate": metrics["loss_rate"],
            "contract_comprehensive_deduction_cny_per_kwh": metrics["loss_rate"]
            * metrics["contract_price_cny_per_kwh"]
            + (1.0 - metrics["loss_rate"]) * metrics["fee_cny_per_kwh"],
        },
        "strategies": [
            {
                "strategy": row["strategy"],
                "label": row["label"],
                "total_revenue_cny": round(row["total_revenue_cny"], 2),
                "net_price_cny_per_kwh": round(row["net_price_cny_per_kwh"], 6),
                "delta_vs_local_cny": round(row["delta_vs_local_cny"], 2),
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
            "generation_mwh",
            "contract_mwh",
            "own_contract_mwh",
            "surplus_mwh",
            "shortfall_mwh",
            "spot_price_cny_per_kwh",
            "green_ratio",
            "contract_energy_cny",
            "green_premium_cny",
            "spot_net_cny",
            "local_surplus_cny",
            "shortfall_spot_cny",
            "shortfall_local_cny",
            "local_only_cny",
            "contract_spot_cny",
            "contract_local_cny",
            "delta_spot_vs_local_cny",
            "delta_local_vs_local_cny",
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
            "spot_mwh",
            "local_mwh",
            "shortfall_mwh",
            "contract_energy_cny",
            "green_premium_cny",
            "spot_net_cny",
            "local_net_cny",
            "shortfall_net_cny",
            "total_revenue_cny",
            "net_price_cny_per_kwh",
            "delta_vs_local_cny",
            "delta_vs_best_cny",
        ],
    )
    write_csv(
        out_dir / "delivery.csv",
        delivery_rows,
        ["item", "value", "unit", "grade", "note"],
    )
    write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        [
            "case",
            "change",
            "local_only_cny",
            "contract_spot_cny",
            "contract_local_cny",
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
        render_review(bundle, profile, base, sensitivity, delivery_rows),
        encoding="utf-8",
    )
    return summary


def render_review(bundle, profile, base, sensitivity, delivery_rows):
    meta = bundle["meta"]
    values = bundle["values"]
    metrics = base["metrics"]
    strategies = base["strategies"]
    best = base["best"]
    local = strategies[0]
    contract_spot = strategies[1]
    contract_local = strategies[2]

    lines = [
        f"# {meta['province']}风电送山东 · 省间组合复核表",
        "",
        f"- 实例：`{meta['instance_id']}`（{meta['entity_type']}）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}；全部电量、价格、合同与通道参数为 D 级合成数据",
        "",
        "## 1. 结论",
        "",
        f"基准情景的最优组合是 **{best['label']}**：净收入 **{_fmt_wan(best['total_revenue_cny'])} 万元**，"
        f"净价 **{best['net_price_cny_per_kwh']:.4f} 元/kWh**，比全部本地高 "
        f"**{_fmt_wan(best['delta_vs_local_cny'])} 万元**。",
        f"合同落地价 0.3300 元/kWh，扣 5% 网损与 8.21 分/kWh 输电价后，"
        f"含绿电溢价的净价只有 **{metrics['contract_net_green_cny_per_kwh']:.4f} 元/kWh**，"
        f"仅比本地 0.2200 元/kWh 高 "
        f"{(metrics['contract_net_green_cny_per_kwh'] - metrics['local_price_cny_per_kwh']) * 100:.2f} 分/kWh。",
        f"余量送省间现货的净价 **{metrics['spot_net_price_cny_per_kwh']:.4f} 元/kWh**，"
        f"比本地低 "
        f"{(metrics['local_price_cny_per_kwh'] - metrics['spot_net_price_cny_per_kwh']) * 100:.2f} 分/kWh；"
        f"因此「合同 + 省间现货」组合的净收入比全部本地低 "
        f"**{_fmt_wan(local['total_revenue_cny'] - contract_spot['total_revenue_cny'])} 万元**。"
        "结论不是“外送越多越好”，而是“合同电量外送、余量本地消纳”。",
        "",
        "## 2. 电量与价格",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| 装机容量 | {values['capacity']:,.0f} MW |",
        f"| 计划电量（P50） | {profile['planned_generation']:,.0f} MWh |",
        f"| 实际发电量 | {metrics['total_generation_mwh']:,.0f} MWh |",
        f"| 合同电量（{metrics['contract_ratio'] * 100:.0f}%） | {metrics['total_contract_mwh']:,.0f} MWh |",
        f"| 合同内自有电量 | {metrics['own_contract_mwh']:,.0f} MWh |",
        f"| 余量 / 偏差 | {metrics['surplus_mwh']:,.0f} / {metrics['shortfall_mwh']:,.0f} MWh |",
        f"| 绿电电量（合同内） | {metrics['green_mwh']:,.0f} MWh（{metrics['weighted_green_ratio'] * 100:.0f}%） |",
        f"| 合同落地价 | {metrics['contract_price_cny_per_kwh']:.4f} 元/kWh |",
        f"| 甘肃本地价 | {metrics['local_price_cny_per_kwh']:.4f} 元/kWh |",
        f"| 加权现货落地价 | {metrics['weighted_spot_price_cny_per_kwh']:.4f} 元/kWh |",
        f"| 绿电溢价 | {metrics['green_premium_cny_per_kwh']:.4f} 元/kWh |",
        "",
        "## 3. 通道扣减",
        "",
        "| 项目 | 值 | 级别 |",
        "|---|---:|---|",
    ]
    for row in delivery_rows:
        if row["item"] in ("送出省输电价", "区域电网电量电价", "专项工程输电价", "输电价合计", "线损率", "合同综合扣减", "现货综合扣减", "落地省输配电价"):
            value = f"{row['value'] * 100:.2f}%" if row["unit"] == "比例" else f"{row['value']:.4f}"
            lines.append(f"| {row['item']} | {value} | {row['grade']} |")
    lines.extend(
        [
            "",
            f"合同价下的综合扣减 = 5% × 0.33 + 95% × 0.0821 = **{metrics['loss_rate'] * metrics['contract_price_cny_per_kwh'] + (1 - metrics['loss_rate']) * metrics['fee_cny_per_kwh']:.4f} 元/kWh**。"
            "输电价按落地电量计，网损按发电量计，两者不能简单相加后再乘一次线损。",
            "落地省输配电价、系统运行费与政府性基金由购电方承担，未计入卖方扣减；若合同改为送端关口价，通道成本则转由买方承担。",
            "",
            "## 4. 组合比较",
            "",
            "| 组合 | 合同电量 | 现货余量 | 本地余量 | 偏差 | 净收入（万元） | 净价（元/kWh） | 较全部本地（万元） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in strategies:
        lines.append(
            f"| {row['label']} | {row['contract_mwh']:,.0f} | {row['spot_mwh']:,.0f} | "
            f"{row['local_mwh']:,.0f} | {row['shortfall_mwh']:,.0f} | "
            f"{_fmt_wan(row['total_revenue_cny'])} | {row['net_price_cny_per_kwh']:.4f} | "
            f"{row['delta_vs_local_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            f"「合同 + 省间现货余量」比全部本地低 {_fmt_wan(local['total_revenue_cny'] - contract_spot['total_revenue_cny'])} 万元："
            f"合同部分贡献了 {_fmt_wan(contract_spot['contract_energy_cny'] + contract_spot['green_premium_cny'])} 万元，"
            f"但余量现货净收入只有 {_fmt_wan(contract_spot['spot_net_cny'])} 万元，"
            "不足以弥补相对本地价的损失。",
            "",
            "## 5. 月度明细",
            "",
            "| 月份 | 发电量 | 合同 | 余量 | 偏差 | 现货价 | 全部本地 | 合同+现货 | 合同+本地 | 合同+本地−本地 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in base["monthly"]:
        lines.append(
            f"| {row['month']} | {row['generation_mwh']:,.0f} | {row['contract_mwh']:,.0f} | "
            f"{row['surplus_mwh']:,.0f} | {row['shortfall_mwh']:,.0f} | "
            f"{row['spot_price_cny_per_kwh']:.2f} | {_fmt_wan(row['local_only_cny'])} | "
            f"{_fmt_wan(row['contract_spot_cny'])} | {_fmt_wan(row['contract_local_cny'])} | "
            f"{row['delta_local_vs_local_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            "合同曲线在 7、8 月高于资源出力，产生小额偏差；偏差按当月现货价或本地价回购，"
            "两种组合的偏差成本不同。实际签约应按月度资源曲线校核，不能只看年度电量。",
            "",
            "## 6. 敏感性",
            "",
            "| 情景 | 全部本地 | 合同+现货 | 合同+本地 | 最优组合 | 最优净收入（万元） | 较基准最优（万元） |",
            "|---|---:|---:|---:|---|---:|---:|",
        ]
    )
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {_fmt_wan(row['local_only_cny'])} | {_fmt_wan(row['contract_spot_cny'])} | "
            f"{_fmt_wan(row['contract_local_cny'])} | {row['best_strategy']} | "
            f"{_fmt_wan(row['best_net_cny'])} | {row['delta_vs_base_best_cny'] / 1e4:+,.2f} |"
        )
    lines.extend(
        [
            "",
            "现货价 +30% 时，「合同 + 省间现货」可能反超本地余量；这说明余量去向取决于**净现货价**，"
            "不是合同落地价。输电价上升、线损上升、合同价下降都会直接压缩最优组合的净收入。",
            "",
            "## 7. 口径提醒",
            "",
            "- 省间合同按受端落地价签，不等于送端关口价；输电价与网损由谁承担，必须在合同里写清。",
            f"- 输电价 {metrics['fee_cny_per_kwh'] * 100:.2f} 分/kWh 是落地电量口径，"
            f"网损 {metrics['loss_rate'] * 100:.1f}% 是发电量口径，"
            f"合同综合扣减约 {(metrics['loss_rate'] * metrics['contract_price_cny_per_kwh'] + (1 - metrics['loss_rate']) * metrics['fee_cny_per_kwh']) * 100:.2f} 分/kWh。",
            "- 省间现货余量的净价可能低于本地价；外送边际电量要看净价，不要用合同价或现货落地价代替。",
            "- 落地省输配电价、系统运行费与政府性基金由购电方承担，卖方模型不应重复扣减。",
            "- 甘肃—山东通道参数为 D 级合成组合，不对应陇东—山东等具体工程；实际交易须查 2027 年输电价格表、ATC 与北京交易中心公告。",
            "- 本包不构成交易、投标或投资建议；省间规则与通道参数以现行文件、交易公告和合同为准。",
            "",
            f"风格指纹 `{hashlib.sha1(json.dumps(bundle['policy'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()[:12]}`；"
            "本复核表由 `run.py` 生成。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="甘肃 200 MW 风电送山东省间组合实例")
    parser.add_argument("--instance", type=Path, default=HERE / "instance.json")
    parser.add_argument("--profile", type=Path, help="月度资源 CSV；--demo 时省略")
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
        print("配置校验通过")
        print(f"实例: {bundle['meta']['instance_id']} · {bundle['meta']['province']} · {bundle['meta']['market']}")
        print(f"规则版本: {bundle['meta']['rule_version']}")
        print(f"风格: {bundle['values']['profile_id']}")
        print(f"合同比例: {bundle['values']['ratio']:.0%}")
        print(f"输电价合计: {bundle['values']['fee']:.4f} 元/kWh；线损率: {bundle['values']['loss']:.2%}")
        print("规则来源:")
        for row in bundle["report"]:
            print(f"  - {row['block']} [{row['grade']}] {row['source'][:90]}")
        return 0

    if args.profile is not None:
        profile_path = args.profile
    elif args.demo:
        profile_path = HERE / bundle["profile"]["file"]
    else:
        print("请用 --profile 指定月度资源 CSV，或加 --demo 使用合成数据", file=sys.stderr)
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
    print(f"合同净价（含绿电）: {summary['prices']['contract_net_green_cny_per_kwh']:.4f} 元/kWh")
    print(f"现货余量净价: {summary['prices']['spot_net_cny_per_kwh']:.4f} 元/kWh；本地价: {summary['prices']['local_cny_per_kwh']:.4f} 元/kWh")
    print(f"最优组合: {best['label']} · {best['total_revenue_cny'] / 1e4:,.2f} 万元 · {best['net_price_cny_per_kwh']:.4f} 元/kWh")
    for warning in summary["warnings"]:
        print(f"警告: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
