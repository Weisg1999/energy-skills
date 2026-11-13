#!/usr/bin/env python3
"""Run the Shandong cement compliance instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the allocation, CCER, settlement and price rules plus
  the facility, holdings and purchase style.
* ``data/production_demo.csv`` is the monthly clinker output for 2025.
* ``data/verification_demo.csv`` is the annual verified emissions.
* ``data/prices_demo.csv`` is the monthly CEA / CCER price path.

The runner builds the benchmark allocation, applies the surplus cap, settles
the CCER 5% offset, chooses the cheaper compliance mix, compares a retrospective
purchase-timing counterfactual and exports the 2026 compliance calendar.

All bundled numbers are synthetic grade D. They are not a compliance opinion,
a price forecast or trading advice.
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

from calendar_tool import build_calendar, to_ics  # noqa: E402
from compliance import (  # noqa: E402
    carryover_allowed,
    ccer_limit,
    compliance_cost,
    compliance_position,
    free_allocation,
    non_compliance_penalty,
)


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
    if grade not in {"A", "B", "C", "D", "A/B", "B/C", "C/D", "B/C/D"}:
        raise ConfigError(f"{path}.grade {grade!r} is not a known grade")
    return grade


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report["provenance"].append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block


def validate_instance(config):
    """Validate the instance blocks and return a provenance report."""
    report = {"ok": True, "provenance": [], "warnings": [], "checks": []}
    meta = _need(config, "meta", "instance")
    for key in (
        "instance_id",
        "province",
        "market",
        "entity_type",
        "rule_version",
        "data_cutoff",
        "scope",
        "disclaimer",
    ):
        _text(meta, key, "meta")

    rules = _need(config, "rules", "instance")
    allocation = _rule_block(rules, "allocation", report)
    ccer = _rule_block(rules, "ccer", report)
    settlement = _rule_block(rules, "settlement", report)
    prices = _rule_block(rules, "prices", report)

    benchmark = _number(
        _need(allocation, "benchmark_tco2_per_t_clinker", "rules.allocation"),
        "rules.allocation.benchmark_tco2_per_t_clinker",
        1e-6,
    )
    correction = _number(
        _need(allocation, "correction_factor", "rules.allocation"),
        "rules.allocation.correction_factor",
        0.5,
        2.0,
    )
    surplus_cap = _number(
        _need(allocation, "surplus_cap_ratio", "rules.allocation"),
        "rules.allocation.surplus_cap_ratio",
        0.0,
        0.2,
    )
    if not isinstance(_need(allocation, "enforce_surplus_cap", "rules.allocation"), bool):
        raise ConfigError("rules.allocation.enforce_surplus_cap must be boolean")
    if benchmark > 1.5:
        raise ConfigError("benchmark looks implausible for cement clinker (tCO2/t)")
    if not 0 < correction <= 1.5:
        raise ConfigError("correction_factor must be in (0, 1.5]")
    report["checks"].append(
        f"基准线 {benchmark:g} tCO2/t；修正系数 {correction:g}；盈余上限 {surplus_cap:.1%}"
    )

    ccer_cap = _number(_need(ccer, "cap_ratio", "rules.ccer"), "rules.ccer.cap_ratio", 0.0, 0.2)
    if abs(ccer_cap - 0.05) > 1e-9:
        report["warnings"].append("CCER 上限不是 5%，请确认是否为地方或年度特殊规则")
    cap_base = _text(ccer, "cap_base", "rules.ccer")
    if cap_base != "verified_emissions":
        raise ConfigError("the national CCER cap base is verified emissions")

    low = _number(
        _need(settlement, "penalty_multiple_low", "rules.settlement"),
        "rules.settlement.penalty_multiple_low",
        5.0,
        10.0,
    )
    high = _number(
        _need(settlement, "penalty_multiple_high", "rules.settlement"),
        "rules.settlement.penalty_multiple_high",
        5.0,
        10.0,
    )
    if not low <= high:
        raise ConfigError("penalty multiple range is inverted")
    _text(settlement, "surrender_deadline", "rules.settlement")
    carry_year = int(
        _number(_need(settlement, "carryover_year", "rules.settlement"), "rules.settlement.carryover_year", 2000)
    )

    _number(_need(prices, "cea_cny_per_t", "rules.prices"), "rules.prices.cea_cny_per_t", 0.0)
    _number(_need(prices, "ccer_cny_per_t", "rules.prices"), "rules.prices.ccer_cny_per_t", 0.0)
    _number(
        _need(prices, "market_average_cny_per_t", "rules.prices"),
        "rules.prices.market_average_cny_per_t",
        0.0,
    )
    _text(prices, "price_month", "rules.prices")

    facility = _need(config, "facility", "instance")
    lines = _need(facility, "lines", "facility")
    if not isinstance(lines, list) or not lines:
        raise ConfigError("facility.lines must be a non-empty list")
    seen = set()
    for index, line in enumerate(lines):
        path = f"facility.lines[{index}]"
        line_id = _text(line, "id", path)
        if line_id in seen:
            raise ConfigError(f"{path}.id {line_id!r} is duplicated")
        seen.add(line_id)
        _text(line, "name", path)
        _number(_need(line, "design_t_per_day", path), f"{path}.design_t_per_day", 1.0)

    holdings = _need(config, "holdings", "instance")
    _number(_need(holdings, "cea_2025_t", "holdings"), "holdings.cea_2025_t", 0.0)
    _number(_need(holdings, "ccer_t", "holdings"), "holdings.ccer_t", 0.0)

    policy = _need(config, "policy", "instance")
    _text(policy, "profile_id", "policy")
    mode = _text(policy, "purchase_mode", "policy")
    if mode not in {"ccer_first", "cea_only", "break_even"}:
        raise ConfigError("policy.purchase_mode must be ccer_first / cea_only / break_even")
    timing = _text(policy, "purchase_timing", "policy")
    if timing not in {"min_cea_month", "current_month"}:
        raise ConfigError("policy.purchase_timing must be min_cea_month / current_month")
    _number(
        _need(policy, "cea_transaction_cost_cny_per_t", "policy"),
        "policy.cea_transaction_cost_cny_per_t",
        0.0,
    )
    _number(
        _need(policy, "ccer_transaction_cost_cny_per_t", "policy"),
        "policy.ccer_transaction_cost_cny_per_t",
        0.0,
    )

    data_contract = _need(config, "data_contract", "instance")
    for key in ("production", "verification", "prices"):
        block = _need(data_contract, key, "data_contract")
        _text(block, "file", f"data_contract.{key}")

    report["carryover_2025"] = carryover_allowed(carry_year)
    if not report["carryover_2025"]:
        report["warnings"].append(f"{carry_year} 年度配额不可结转")
    return report


def _resolve_data(config, key):
    path = Path(config["data_contract"][key]["file"])
    return path if path.is_absolute() else HERE / path


def _read_rows(path, fields):
    if not path.exists():
        raise ConfigError(f"missing input file {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in fields if field not in (reader.fieldnames or [])]
        if missing:
            raise ConfigError(f"{path} is missing columns: {', '.join(missing)}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def _to_float(value, path):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{path} must be numeric")
    if not math.isfinite(number):
        raise ConfigError(f"{path} must be finite")
    return number


def load_production(config):
    rows = _read_rows(
        _resolve_data(config, "production"), ["month", "clinker_t", "note"]
    )
    if len(rows) != 12:
        raise ConfigError("production must contain 12 monthly rows")
    months = [row["month"] for row in rows]
    if len(set(months)) != 12:
        raise ConfigError("production months must be unique")
    total = 0.0
    for index, row in enumerate(rows):
        value = _to_float(row["clinker_t"], f"production[{index}].clinker_t")
        if value <= 0:
            raise ConfigError(f"production[{index}].clinker_t must be positive")
        total += value
        row["clinker_t"] = value
    return rows, total


def load_verification(config):
    rows = _read_rows(
        _resolve_data(config, "verification"),
        ["compliance_year", "verified_emissions_tco2", "verification_body"],
    )
    if len(rows) != 1:
        raise ConfigError("verification must contain exactly one annual row")
    row = rows[0]
    year = int(_to_float(row["compliance_year"], "verification.compliance_year"))
    emissions = _to_float(row["verified_emissions_tco2"], "verification.verified_emissions_tco2")
    if emissions <= 0:
        raise ConfigError("verified emissions must be positive")
    if not row["verification_body"]:
        raise ConfigError("verification_body must be non-empty")
    if year != 2025:
        raise ConfigError("this pack is frozen to the 2025 compliance year")
    return {"year": year, "emissions": emissions, "body": row["verification_body"]}


def load_prices(config):
    rows = _read_rows(
        _resolve_data(config, "prices"), ["month", "cea_cny_per_t", "ccer_cny_per_t"]
    )
    if len(rows) < 6:
        raise ConfigError("prices must contain at least 6 monthly rows")
    months = [row["month"] for row in rows]
    if len(set(months)) != len(months):
        raise ConfigError("price months must be unique")
    for index, row in enumerate(rows):
        row["cea"] = _to_float(row["cea_cny_per_t"], f"prices[{index}].cea_cny_per_t")
        row["ccer"] = _to_float(row["ccer_cny_per_t"], f"prices[{index}].ccer_cny_per_t")
        if row["cea"] <= 0 or row["ccer"] <= 0:
            raise ConfigError(f"prices[{index}] must be positive")
    wanted = config["rules"]["prices"]["price_month"]
    if wanted not in months:
        raise ConfigError(f"rules.prices.price_month {wanted!r} is not in the price file")
    return rows


def allocate(config, report, activity, verified):
    allocation_rule = config["rules"]["allocation"]
    raw = free_allocation(
        activity,
        allocation_rule["benchmark_tco2_per_t_clinker"],
        allocation_rule["correction_factor"],
    )
    cap = verified * (1.0 + allocation_rule["surplus_cap_ratio"])
    effective = raw
    cap_binding = False
    if allocation_rule["enforce_surplus_cap"] and raw > cap:
        effective = cap
        cap_binding = True
        report["warnings"].append(
            f"基准线分配 {raw:,.0f} t 超过核实排放的 {1 + allocation_rule['surplus_cap_ratio']:.0%}，"
            f"按盈余上限压到 {effective:,.0f} t"
        )
    return {
        "activity_t": activity,
        "raw_allocation_t": raw,
        "effective_allocation_t": effective,
        "verified_tco2": verified,
        "cap_binding": cap_binding,
        "intensity_tco2_per_t": verified / activity,
    }


def _ccer_cap(config, verified):
    return ccer_limit(verified, config["rules"]["ccer"]["cap_ratio"])


def build_scenarios(config, position, verified):
    """Cost under CEA-only, CCER-first, break-even and non-compliance."""
    policy = config["policy"]
    prices = config["rules"]["prices"]
    holdings = config["holdings"]
    cea_tx = policy["cea_transaction_cost_cny_per_t"]
    ccer_tx = policy["ccer_transaction_cost_cny_per_t"]
    gap = max(0.0, position["gap"])
    limit = min(_ccer_cap(config, verified), holdings["ccer_t"], gap)
    break_even = prices["cea_cny_per_t"] + cea_tx - ccer_tx

    rows = []
    for mode in ("cea_only", "ccer_first", "break_even"):
        ccer_used = limit if mode != "cea_only" else 0.0
        if mode == "break_even" and prices["ccer_cny_per_t"] + ccer_tx > break_even:
            ccer_used = 0.0
        cea_needed = max(0.0, gap - ccer_used)
        cea_purchase = max(0.0, cea_needed - holdings["cea_2025_t"])
        cost = (
            cea_purchase * (prices["cea_cny_per_t"] + cea_tx)
            + ccer_used * (prices["ccer_cny_per_t"] + ccer_tx)
        )
        rows.append(
            {
                "strategy": mode,
                "ccer_used_t": ccer_used,
                "cea_needed_t": cea_needed,
                "cea_purchased_t": cea_purchase,
                "cea_holdings_used_t": min(cea_needed, holdings["cea_2025_t"]),
                "cost_cny": cost,
                "unit_gap_cost_cny_per_t": cost / gap if gap > 0 else 0.0,
                "note": "CCER 盈亏平衡价 "
                f"{break_even:.2f} 元/t；当前 CCER {prices['ccer_cny_per_t']:.2f} 元/t",
            }
        )

    shortfall = max(0.0, gap - limit - holdings["cea_2025_t"])
    for multiple in (
        config["rules"]["settlement"]["penalty_multiple_low"],
        config["rules"]["settlement"]["penalty_multiple_high"],
    ):
        penalty = non_compliance_penalty(
            shortfall, config["rules"]["prices"]["market_average_cny_per_t"], multiple
        )
        rows.append(
            {
                "strategy": f"non_compliant_{multiple:g}x",
                "ccer_used_t": 0.0,
                "cea_needed_t": gap,
                "cea_purchased_t": 0.0,
                "cea_holdings_used_t": 0.0,
                "cost_cny": penalty,
                "unit_gap_cost_cny_per_t": penalty / gap if gap > 0 else 0.0,
                "note": f"未清缴缺口 {shortfall:,.0f} t × 市场均价 × {multiple:g}",
            }
        )
    best = min(row["cost_cny"] for row in rows if not row["strategy"].startswith("non_"))
    for row in rows:
        row["delta_vs_best_cny"] = row["cost_cny"] - best
    return rows, break_even, shortfall


def purchase_timing(config, price_rows, cea_purchase):
    current = next(
        row for row in price_rows if row["month"] == config["rules"]["prices"]["price_month"]
    )
    cheapest = min(price_rows, key=lambda row: row["cea"])
    saving = cea_purchase * (current["cea"] - cheapest["cea"])
    return {
        "current_month": current["month"],
        "current_cea_cny_per_t": current["cea"],
        "cheapest_month": cheapest["month"],
        "cheapest_cea_cny_per_t": cheapest["cea"],
        "cea_purchase_t": cea_purchase,
        "saving_vs_current_cny": saving,
        "note": "事后最低价，不是预测；只用于说明采购时点的量级",
    }


def _write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_review(path, config, report, allocation, position, scenarios, timing, break_even):
    prices = config["rules"]["prices"]
    reference = next(row for row in scenarios if row["strategy"] == "ccer_first")
    lines = [
        f"# 复核表：{config['meta']['instance_id']}",
        "",
        f"- 省份 / 主体：{config['meta']['province']} / {config['meta']['entity_type']}",
        f"- 规则版本：{config['meta']['rule_version']}",
        f"- 数据截止：{config['meta']['data_cutoff']}",
        f"- 风格指纹：{report['fingerprint']}",
        "",
        "## 1. 结论",
        "",
        f"- 熟料产量 {allocation['activity_t']:,.0f} t，核实排放 {allocation['verified_tco2']:,.0f} tCO2e，"
        f"排放强度 {allocation['intensity_tco2_per_t']:.3f} tCO2/t。",
        f"- 基准线分配 {allocation['raw_allocation_t']:,.0f} t，"
        f"{'触发' if allocation['cap_binding'] else '未触发'} 3% 盈余上限，"
        f"有效分配 {allocation['effective_allocation_t']:,.0f} t。",
        f"- 配额缺口 {max(0.0, position['gap']):,.0f} t；CCER 上限 "
        f"{position.get('ccer_limit', _ccer_cap(config, allocation['verified_tco2'])):,.0f} t，"
        f"已用 {position['ccer_used']:,.0f} t，CEA 缺口 {position['cea_needed']:,.0f} t。",
        f"- 推荐策略成本 {reference['cost_cny']:,.0f} 元；全买 CEA 成本 "
        f"{next(row['cost_cny'] for row in scenarios if row['strategy'] == 'cea_only'):,.0f} 元。",
        "",
        "## 2. 配额与抵销",
        "",
        "| 项 | 值 |",
        "|---|---:|",
        f"| 熟料产量 (t) | {allocation['activity_t']:,.0f} |",
        f"| 基准线 (tCO2/t) | {config['rules']['allocation']['benchmark_tco2_per_t_clinker']:g} |",
        f"| 原始分配 (t) | {allocation['raw_allocation_t']:,.0f} |",
        f"| 有效分配 (t) | {allocation['effective_allocation_t']:,.0f} |",
        f"| 核实排放 (tCO2e) | {allocation['verified_tco2']:,.0f} |",
        f"| 缺口 (t) | {max(0.0, position['gap']):,.0f} |",
        f"| CCER 可用 (t) | {config['holdings']['ccer_t']:,.0f} |",
        f"| CCER 已用 (t) | {position['ccer_used']:,.0f} |",
        f"| CEA 持仓 (t) | {config['holdings']['cea_2025_t']:,.0f} |",
        f"| CEA 需采购 (t) | {max(0.0, position['cea_needed'] - config['holdings']['cea_2025_t']):,.0f} |",
        "",
        "## 3. 策略对比",
        "",
        "| 策略 | CCER 用量 (t) | CEA 采购 (t) | 成本 (元) | 相对最优 (元) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in scenarios:
        lines.append(
            f"| {row['strategy']} | {row['ccer_used_t']:,.0f} | {row['cea_purchased_t']:,.0f} | "
            f"{row['cost_cny']:,.0f} | {row['delta_vs_best_cny']:,.0f} |"
        )
    lines.extend(
        [
            "",
            f"CCER 与 CEA 的盈亏平衡价：**{break_even:.2f} 元/t**（含交易成本）。"
            f"当前 CCER {prices['ccer_cny_per_t']:.2f} 元/t、CEA {prices['cea_cny_per_t']:.2f} 元/t；"
            "价差随时点反转，不能把某一时点的排序当全年结论。",
            "",
            "## 4. 采购时点（事后口径）",
            "",
            f"- 当前月 {timing['current_month']}：CEA {timing['current_cea_cny_per_t']:.2f} 元/t；"
            f"最低月 {timing['cheapest_month']}：{timing['cheapest_cea_cny_per_t']:.2f} 元/t。",
            f"- 按 {timing['cea_purchase_t']:,.0f} t 计，事后最低价相对当前价节省 "
            f"{timing['saving_vs_current_cny']:,.0f} 元。",
            "- 这是回溯对照，不是价格预测；真实采购还要考虑资金、授权与流动性。",
            "",
            "## 5. 日历与罚则",
            "",
            f"- 清缴截止：{config['rules']['settlement']['surrender_deadline']}（以年度清缴通知为准）。",
            f"- 2025 年度配额可结转：{'是' if report['carryover_2025'] else '否'}；2019-2024 年度不得结转。",
            f"- 未足额清缴缺口 {max(0.0, position['gap'] - position['ccer_used'] - config['holdings']['cea_2025_t']):,.0f} t，"
            "按市场均价 5-10 倍处罚；处罚成本通常显著高于提前采购。",
            "",
            "## 6. 口径提醒",
            "",
            "1. **基准线分配不是免费额度到账**：还要经过省级清缴通知、核查与结转规则。",
            "2. **CCER 5% 是抵销上限，不是建议用量**：CCER 价高于 CEA 时用满反而多花钱。",
            "3. **持仓不是成本为零**：存量 CEA 有机会成本，本表只算现金支出。",
            "4. **盈余上限只在盈余时触发**：本包按核实排放的 3% 建模，正式口径以年度方案为准。",
            "5. **价格是时点快照**：2025 年 CCER 曾高于 CEA，2026-10 又低于 CEA，不能线性外推。",
            "",
            "## 7. 来源",
            "",
        ]
    )
    for item in report["provenance"]:
        lines.append(f"- `{item['block']}`（{item['grade']}）：{item['source']}")
    lines.extend(
        [
            "",
            f"> {config['meta']['disclaimer']}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_instance(instance_path, out_dir):
    config = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    report = validate_instance(config)
    production, activity = load_production(config)
    verification = load_verification(config)
    price_rows = load_prices(config)

    allocation = allocate(config, report, activity, verification["emissions"])
    position = compliance_position(
        allocation["effective_allocation_t"],
        allocation["verified_tco2"],
        config["holdings"]["ccer_t"],
        config["rules"]["ccer"]["cap_ratio"],
    )
    scenarios, break_even, shortfall = build_scenarios(
        config, position, allocation["verified_tco2"]
    )
    preferred = next(row for row in scenarios if row["strategy"] == config["policy"]["purchase_mode"])
    timing = purchase_timing(config, price_rows, preferred["cea_purchased_t"])
    fingerprint = hashlib.sha1(
        json.dumps(config["policy"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    report["fingerprint"] = fingerprint

    out_dir.mkdir(parents=True, exist_ok=True)
    allocation_rows = []
    per_line = allocation["raw_allocation_t"] / len(config["facility"]["lines"])
    for line in config["facility"]["lines"]:
        allocation_rows.append(
            {
                "line_id": line["id"],
                "line_name": line["name"],
                "design_t_per_day": line["design_t_per_day"],
                "clinker_share_t": per_line,
                "benchmark_tco2_per_t": config["rules"]["allocation"]["benchmark_tco2_per_t_clinker"],
                "correction_factor": config["rules"]["allocation"]["correction_factor"],
                "allocation_t": per_line,
                "note": "按产能均分，仅演示；真实分配按企业活动数据核算",
            }
        )
    _write_csv(
        out_dir / "allocation.csv",
        allocation_rows,
        [
            "line_id",
            "line_name",
            "design_t_per_day",
            "clinker_share_t",
            "benchmark_tco2_per_t",
            "correction_factor",
            "allocation_t",
            "note",
        ],
    )
    _write_csv(
        out_dir / "cost_scenarios.csv",
        scenarios,
        [
            "strategy",
            "ccer_used_t",
            "cea_needed_t",
            "cea_purchased_t",
            "cea_holdings_used_t",
            "cost_cny",
            "unit_gap_cost_cny_per_t",
            "delta_vs_best_cny",
            "note",
        ],
    )
    price_out = [
        {
            "month": row["month"],
            "cea_cny_per_t": row["cea"],
            "ccer_cny_per_t": row["ccer"],
            "spread_cea_minus_ccer": row["cea"] - row["ccer"],
            "cea_with_tx": row["cea"] + config["policy"]["cea_transaction_cost_cny_per_t"],
            "ccer_with_tx": row["ccer"] + config["policy"]["ccer_transaction_cost_cny_per_t"],
        }
        for row in price_rows
    ]
    _write_csv(
        out_dir / "prices.csv",
        price_out,
        [
            "month",
            "cea_cny_per_t",
            "ccer_cny_per_t",
            "spread_cea_minus_ccer",
            "cea_with_tx",
            "ccer_with_tx",
        ],
    )

    position_doc = {
        **allocation,
        "position": position,
        "holdings": config["holdings"],
        "cea_purchase_t": preferred["cea_purchased_t"],
        "shortfall_after_offsets_t": shortfall,
        "ccer_break_even_cny_per_t": break_even,
        "carryover_2025": report["carryover_2025"],
    }
    (out_dir / "position.json").write_text(
        json.dumps(position_doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    calendar_events = build_calendar(2026, surrender=(12, 31))
    (out_dir / "compliance-2025.ics").write_text(
        to_ics(calendar_events, "2025 年度碳履约日历"), encoding="utf-8", newline=""
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": fingerprint,
        "provenance": report["provenance"],
        "production": production,
        "verification": verification,
        "allocation": allocation,
        "position": position,
        "scenarios": scenarios,
        "preferred_strategy": preferred,
        "break_even_ccer_cny_per_t": break_even,
        "purchase_timing": timing,
        "calendar": [
            {
                "day": event.day.isoformat(),
                "code": event.code,
                "title": event.title,
                "owner": event.owner,
            }
            for event in calendar_events
        ],
        "warnings": report["warnings"],
        "files": [
            "allocation.csv",
            "cost_scenarios.csv",
            "prices.csv",
            "position.json",
            "compliance-2025.ics",
            "summary.json",
            "review.md",
        ],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(
        out_dir / "review.md", config, report, allocation, position, scenarios, timing, break_even
    )
    return {"summary": summary, "out_dir": out_dir}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Shandong cement compliance instance runner")
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--out", default=str(HERE / "out"))
    parser.add_argument("--demo", action="store_true", help="use the bundled synthetic data")
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
            print(f"  {item['block']:<24} {item['grade']:<5} {item['source'][:64]}")
        print(
            f"  基准线 {config['rules']['allocation']['benchmark_tco2_per_t_clinker']:g} tCO2/t；"
            f"CCER 上限 {config['rules']['ccer']['cap_ratio']:.0%}；"
            f"结转 {'允许' if report['carryover_2025'] else '不允许'}"
        )
        for warning in report["warnings"]:
            print(f"  warning: {warning}")
        return 0

    out_dir = HERE / "out" / "demo" if args.demo else Path(args.out)
    try:
        result = run_instance(args.instance, out_dir)
    except ConfigError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    preferred = summary["preferred_strategy"]
    print(
        f"实例：{summary['instance_id']} / 缺口 {max(0.0, summary['position']['gap']):,.0f} t / "
        f"CCER 用 {summary['position']['ccer_used']:,.0f} t"
    )
    print(
        f"推荐策略 {preferred['strategy']}：CEA 采购 {preferred['cea_purchased_t']:,.0f} t / "
        f"成本 {preferred['cost_cny']:,.0f} 元"
    )
    print(f"输出目录：{out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
