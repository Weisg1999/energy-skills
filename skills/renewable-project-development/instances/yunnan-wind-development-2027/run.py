#!/usr/bin/env python3
"""Run the Yunnan 100 MW wind development-stage investment case.

The engine is shared, the instance is local:

* ``instance.json`` holds the mechanism-price, market, cost and finance rules,
  the project assumptions and the investment style.
* ``data/resource_demo.csv`` is a synthetic first-operating-year profile:
  monthly gross generation and a generation-weighted capture rate.

The runner prices the project's market revenue at the capture price, settles
the mechanism transfer against the market average price, then computes LCOE,
pre-tax and after-tax break-even prices, after-tax cash flow, NPV, IRR,
payback, DSCR, a bid ladder and a combined stress case.

All bundled numbers are synthetic grade D. They are not a bid instruction, a
bankability opinion or investment advice.
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

from finance import debt_payment, dscr, irr, npv, payback, project_cashflow  # noqa: E402
from lcoe import lcoe  # noqa: E402
from mechanism import break_even_mechanism_price, capture_price, cfd_settlement  # noqa: E402
from resource import annual_energy_mwh, p90_from_p50  # noqa: E402

GRADES = {"A", "B", "C", "D", "A/B", "B/C", "C/D", "B/C/D"}
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
BID_LADDER = (0.320, 0.330, 0.332, 0.334, 0.3351, 0.3358)


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
    return block, grade


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
    mechanism, _ = _rule_block(rules, "mechanism", report)
    market, _ = _rule_block(rules, "market", report)
    cost, _ = _rule_block(rules, "cost", report)
    finance_rules, _ = _rule_block(rules, "finance", report)

    mech_price = _number(_need(mechanism, "mechanism_price_cny_per_kwh", "rules.mechanism"), "rules.mechanism.mechanism_price_cny_per_kwh", 0.0, 5.0)
    bid_cap = _number(_need(mechanism, "bid_cap_cny_per_kwh", "rules.mechanism"), "rules.mechanism.bid_cap_cny_per_kwh", 0.0, 5.0)
    bid_floor = _number(_need(mechanism, "bid_floor_cny_per_kwh", "rules.mechanism"), "rules.mechanism.bid_floor_cny_per_kwh", 0.0, 5.0)
    coverage = _number(_need(mechanism, "coverage_ratio", "rules.mechanism"), "rules.mechanism.coverage_ratio", 0.0, 1.0)
    pool_ratio = _number(_need(mechanism, "pool_demand_ratio", "rules.mechanism"), "rules.mechanism.pool_demand_ratio", 0.0, 1.0)
    single_cap = _number(_need(mechanism, "single_project_cap", "rules.mechanism"), "rules.mechanism.single_project_cap", 0.0, 1.0)
    if not bid_floor <= mech_price <= bid_cap:
        raise ConfigError("机制电价必须落在申报下限与上限之间")
    if not 0.0 < coverage <= single_cap:
        raise ConfigError("coverage_ratio 必须大于 0 且不超过 single_project_cap")
    if _text(mechanism, "settlement", "rules.mechanism") != "difference":
        raise ConfigError("本包只实现 difference 差价结算")

    market_price = _number(_need(market, "market_price_cny_per_kwh", "rules.market"), "rules.market.market_price_cny_per_kwh", 0.0, 5.0)
    green_cert = _number(_need(market, "green_certificate_cny_per_mwh", "rules.market"), "rules.market.green_certificate_cny_per_mwh", 0.0, 200.0)

    capex_per_kw = _number(_need(cost, "capex_cny_per_kw", "rules.cost"), "rules.cost.capex_cny_per_kw", 0.0)
    opex_per_kw = _number(_need(cost, "opex_cny_per_kw_year", "rules.cost"), "rules.cost.opex_cny_per_kw_year", 0.0)
    curtailment = _number(_need(cost, "curtailment_ratio", "rules.cost"), "rules.cost.curtailment_ratio", 0.0, 0.99)
    degradation = _number(_need(cost, "degradation_per_year", "rules.cost"), "rules.cost.degradation_per_year", 0.0, 0.5)
    escalation = _number(_need(cost, "opex_escalation_per_year", "rules.cost"), "rules.cost.opex_escalation_per_year", -0.2, 0.5)
    life = int(_number(_need(cost, "life_years", "rules.cost"), "rules.cost.life_years", 1.0, 60.0))
    if capex_per_kw <= 0 or opex_per_kw <= 0:
        raise ConfigError("单位造价与单位运维必须为正")

    discount = _number(_need(finance_rules, "discount_rate", "rules.finance"), "rules.finance.discount_rate", 0.0, 1.0)
    tax = _number(_need(finance_rules, "tax_rate", "rules.finance"), "rules.finance.tax_rate", 0.0, 0.8)
    dep_years = int(_number(_need(finance_rules, "depreciation_years", "rules.finance"), "rules.finance.depreciation_years", 1.0, 60.0))
    debt_ratio = _number(_need(finance_rules, "debt_ratio", "rules.finance"), "rules.finance.debt_ratio", 0.0, 0.95)
    debt_rate = _number(_need(finance_rules, "debt_rate", "rules.finance"), "rules.finance.debt_rate", 0.0, 0.5)
    debt_years = int(_number(_need(finance_rules, "debt_years", "rules.finance"), "rules.finance.debt_years", 1.0, 40.0))
    hurdle = _number(_need(finance_rules, "hurdle_irr", "rules.finance"), "rules.finance.hurdle_irr", 0.0, 1.0)
    min_dscr = _number(_need(finance_rules, "min_dscr", "rules.finance"), "rules.finance.min_dscr", 0.0, 10.0)
    if debt_ratio <= 0:
        raise ConfigError("debt_ratio 必须大于 0，本包以 CFADS/还本付息计算 DSCR")
    if discount <= 0:
        raise ConfigError("discount_rate 必须大于 0")

    project = _need(config, "project", "instance")
    capacity = _number(_need(project, "capacity_mw", "project"), "project.capacity_mw", 0.0)
    p50_hours = _number(_need(project, "p50_hours", "project"), "project.p50_hours", 0.0, 8760.0)
    p90_cv = _number(_need(project, "p90_cv", "project"), "project.p90_cv", 0.0, 0.5)
    cod = _text(project, "cod", "project")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", cod):
        raise ConfigError("project.cod 必须是 YYYY-MM-DD")
    _grade(project, "project")
    _text(project, "source", "project")
    if capacity <= 0 or p50_hours <= 0:
        raise ConfigError("装机容量与 P50 利用小时必须为正")

    policy = _need(config, "policy", "instance")
    _text(policy, "profile_id", "policy")
    _text(policy, "decision_rule", "policy")
    _text(policy, "bid_strategy", "policy")
    _grade(policy, "policy")

    contract = _need(config, "data_contract", "instance")
    resource = _need(contract, "resource", "data_contract")
    _text(resource, "file", "data_contract.resource")
    fields = _need(resource, "fields", "data_contract.resource")
    if not isinstance(fields, list) or not fields:
        raise ConfigError("data_contract.resource.fields 必须是非空数组")
    required = {"month", "generation_mwh", "capture_rate"}
    if not required.issubset(set(fields)):
        raise ConfigError("data_contract.resource.fields 必须包含 month / generation_mwh / capture_rate")

    return {
        "config": config,
        "report": report,
        "meta": meta,
        "mechanism": mechanism,
        "market": market,
        "cost": cost,
        "finance": finance_rules,
        "project": project,
        "policy": policy,
        "resource": resource,
        "values": {
            "mech_price": mech_price,
            "bid_cap": bid_cap,
            "bid_floor": bid_floor,
            "coverage": coverage,
            "pool_ratio": pool_ratio,
            "single_cap": single_cap,
            "market_price": market_price,
            "green_cert": green_cert,
            "capex_per_kw": capex_per_kw,
            "opex_per_kw": opex_per_kw,
            "curtailment": curtailment,
            "degradation": degradation,
            "escalation": escalation,
            "life": life,
            "discount": discount,
            "tax": tax,
            "dep_years": dep_years,
            "debt_ratio": debt_ratio,
            "debt_rate": debt_rate,
            "debt_years": debt_years,
            "hurdle": hurdle,
            "min_dscr": min_dscr,
            "capacity": capacity,
            "p50_hours": p50_hours,
            "p90_cv": p90_cv,
        },
    }


def load_resource(path, bundle):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = reader.fieldnames or []
    except FileNotFoundError as exc:
        raise ConfigError(f"resource 文件不存在: {path}") from exc
    except csv.Error as exc:
        raise ConfigError(f"resource CSV 解析失败: {exc}") from exc

    for field in ("month", "generation_mwh", "capture_rate"):
        if field not in fields:
            raise ConfigError(f"resource CSV 缺少字段 {field}")
    if len(rows) != 12:
        raise ConfigError(f"resource 必须包含 12 个月，实际 {len(rows)} 行")

    months = []
    generation = []
    capture = []
    for index, row in enumerate(rows, start=2):
        month = (row.get("month") or "").strip()
        if not MONTH_RE.match(month):
            raise ConfigError(f"resource 第 {index} 行 month 不是 YYYY-MM")
        if month in months:
            raise ConfigError(f"resource 第 {index} 行 month 重复: {month}")
        gen = _number(float(row["generation_mwh"]), f"resource 第 {index} 行 generation_mwh", 0.0)
        cap_rate = _number(float(row["capture_rate"]), f"resource 第 {index} 行 capture_rate", 0.0, 1.5)
        if gen <= 0:
            raise ConfigError(f"resource 第 {index} 行 generation_mwh 必须为正")
        months.append(month)
        generation.append(gen)
        capture.append(cap_rate)

    if [month.split("-")[0] for month in months].count(months[0].split("-")[0]) != 12:
        raise ConfigError("resource 必须覆盖同一个自然年的 12 个月")
    if months != sorted(months):
        raise ConfigError("resource 必须按月份升序排列")

    gross = sum(generation)
    weighted_capture = sum(g * c for g, c in zip(generation, capture)) / gross
    implied_hours = gross / bundle["values"]["capacity"]
    warnings = []
    p50 = bundle["values"]["p50_hours"]
    if not 0.8 * p50 <= implied_hours <= 1.2 * p50:
        warnings.append(
            f"数据隐含利用小时 {implied_hours:,.1f} h 偏离 P50 {p50:,.1f} h 超过 20%，请核对资源数据"
        )
    return {
        "months": months,
        "generation": generation,
        "capture": capture,
        "gross": gross,
        "weighted_capture": weighted_capture,
        "implied_hours": implied_hours,
        "warnings": warnings,
    }


def revenue_case(bundle, gross, capture, coverage, mech_price, curtailment):
    values = bundle["values"]
    net = gross * (1.0 - curtailment)
    covered = net * coverage
    if covered <= 0:
        raise ConfigError("机制电量必须为正")
    settled = cfd_settlement(
        mech_price,
        values["market_price"],
        covered,
        net,
        values["green_cert"],
    )
    market_rev = capture_price(values["market_price"], capture) * net * 1000.0
    total = market_rev + settled["transfer"] + settled["certificate_revenue"]
    return {
        "net_mwh": net,
        "covered_mwh": covered,
        "market_revenue_cny": market_rev,
        "transfer_cny": settled["transfer"],
        "certificate_revenue_cny": settled["certificate_revenue"],
        "total_revenue_cny": total,
        "effective_price_cny_per_kwh": total / (net * 1000.0),
        "capture_price_cny_per_kwh": capture_price(values["market_price"], capture),
    }


def finance_case(bundle, gross, capture, coverage, mech_price, capex, opex, curtailment):
    values = bundle["values"]
    revenue = revenue_case(bundle, gross, capture, coverage, mech_price, curtailment)
    flows = project_cashflow(
        revenue["total_revenue_cny"],
        opex,
        capex,
        values["life"],
        values["tax"],
        values["dep_years"],
        values["degradation"],
        values["escalation"],
    )
    try:
        irr_value = irr(flows)
    except ValueError:
        irr_value = None
    debt = capex * values["debt_ratio"]
    service = debt_payment(debt, values["debt_rate"], min(values["debt_years"], values["life"]))
    dscr_values = [
        dscr(flows[year], service)
        for year in range(1, min(values["debt_years"], values["life"]) + 1)
    ]
    return {
        "revenue": revenue,
        "flows": flows,
        "npv_cny": npv(values["discount"], flows),
        "irr": irr_value,
        "payback_years": payback(flows),
        "debt_cny": debt,
        "debt_service_cny": service,
        "dscr_year1": dscr_values[0],
        "dscr_min": min(dscr_values),
    }


def decision(bundle, case):
    values = bundle["values"]
    irr_ok = case["irr"] is not None and case["irr"] >= values["hurdle"] - 1e-9
    npv_ok = case["npv_cny"] >= -1e-6
    dscr_ok = case["dscr_min"] >= values["min_dscr"] - 1e-9
    return {
        "pass": bool(irr_ok and npv_ok and dscr_ok),
        "irr_ok": irr_ok,
        "npv_ok": npv_ok,
        "dscr_ok": dscr_ok,
    }


def after_tax_break_even(bundle, gross, capture, coverage, curtailment, rate):
    values = bundle["values"]
    capex = values["capacity"] * 1000.0 * values["capex_per_kw"]
    opex = values["capacity"] * 1000.0 * values["opex_per_kw"]

    def trial(price):
        revenue = revenue_case(bundle, gross, capture, coverage, price, curtailment)
        flows = project_cashflow(
            revenue["total_revenue_cny"],
            opex,
            capex,
            values["life"],
            values["tax"],
            values["dep_years"],
            values["degradation"],
            values["escalation"],
        )
        return npv(rate, flows)

    low, high = 0.0, 1.0
    if trial(low) >= 0.0:
        return low
    if trial(high) <= 0.0:
        raise ConfigError("机制电价上限 1 元/kWh 仍为负 NPV，检查成本假设")
    for _ in range(90):
        mid = (low + high) / 2.0
        if trial(mid) > 0.0:
            high = mid
        else:
            low = mid
    return (low + high) / 2.0


def pre_tax_break_even(bundle, lcoe_value, capture):
    values = bundle["values"]
    capture_price_mwh = capture_price(values["market_price"], capture) * 1000.0
    covered_price = break_even_mechanism_price(
        lcoe_value,
        capture_price_mwh,
        values["coverage"],
        values["green_cert"],
    )
    wedge = values["market_price"] - capture_price_mwh / 1000.0
    return covered_price / 1000.0 + wedge


def build_sensitivity(bundle, base, p90_gross):
    values = bundle["values"]
    capex = values["capacity"] * 1000.0 * values["capex_per_kw"]
    opex = values["capacity"] * 1000.0 * values["opex_per_kw"]
    cases = [
        {
            "case": "基准",
            "change": "P50 资源、配置造价与机制电价",
            "gross": base["gross"],
            "capture": base["capture"],
            "coverage": values["coverage"],
            "mech": values["mech_price"],
            "capex": capex,
            "opex": opex,
            "curtailment": values["curtailment"],
        },
        {
            "case": "单位造价 +10%",
            "change": "CAPEX 由 4,800 升至 5,280 元/kW",
            "gross": base["gross"],
            "capture": base["capture"],
            "coverage": values["coverage"],
            "mech": values["mech_price"],
            "capex": capex * 1.10,
            "opex": opex,
            "curtailment": values["curtailment"],
        },
        {
            "case": "发电量 −10%",
            "change": "P50 利用小时降至 2,565 h",
            "gross": base["gross"] * 0.90,
            "capture": base["capture"],
            "coverage": values["coverage"],
            "mech": values["mech_price"],
            "capex": capex,
            "opex": opex,
            "curtailment": values["curtailment"],
        },
        {
            "case": "运维 +20%",
            "change": "年度运维由 175 升至 210 元/kW",
            "gross": base["gross"],
            "capture": base["capture"],
            "coverage": values["coverage"],
            "mech": values["mech_price"],
            "capex": capex,
            "opex": opex * 1.20,
            "curtailment": values["curtailment"],
        },
        {
            "case": "限电率 10%",
            "change": "净电量再减少 5 个百分点",
            "gross": base["gross"],
            "capture": base["capture"],
            "coverage": values["coverage"],
            "mech": values["mech_price"],
            "capex": capex,
            "opex": opex,
            "curtailment": 0.10,
        },
        {
            "case": "捕获率 88%",
            "change": "加权捕获率由 92.5% 降至 88%",
            "gross": base["gross"],
            "capture": 0.88,
            "coverage": values["coverage"],
            "mech": values["mech_price"],
            "capex": capex,
            "opex": opex,
            "curtailment": values["curtailment"],
        },
        {
            "case": "机制覆盖 50%",
            "change": "机制电量占比由 65% 降至 50%",
            "gross": base["gross"],
            "capture": base["capture"],
            "coverage": 0.50,
            "mech": values["mech_price"],
            "capex": capex,
            "opex": opex,
            "curtailment": values["curtailment"],
        },
        {
            "case": "P90 资源",
            "change": "利用小时由 P50 2,850 降至 P90",
            "gross": p90_gross,
            "capture": base["capture"],
            "coverage": values["coverage"],
            "mech": values["mech_price"],
            "capex": capex,
            "opex": opex,
            "curtailment": values["curtailment"],
        },
        {
            "case": "按上限申报",
            "change": "机制电价由 0.3351 升至 0.3358 元/kWh",
            "gross": base["gross"],
            "capture": base["capture"],
            "coverage": values["coverage"],
            "mech": values["bid_cap"],
            "capex": capex,
            "opex": opex,
            "curtailment": values["curtailment"],
        },
        {
            "case": "组合压力",
            "change": "P90 + 造价 +10% + 捕获率 88.5% + 限电 10% + 覆盖 50% + 电价 0.320",
            "gross": p90_gross,
            "capture": 0.885,
            "coverage": 0.50,
            "mech": 0.320,
            "capex": capex * 1.10,
            "opex": opex,
            "curtailment": 0.10,
        },
    ]

    rows = []
    for case in cases:
        result = finance_case(
            bundle,
            case["gross"],
            case["capture"],
            case["coverage"],
            case["mech"],
            case["capex"],
            case["opex"],
            case["curtailment"],
        )
        verdict = decision(bundle, result)
        rows.append(
            {
                "case": case["case"],
                "change": case["change"],
                "gross_mwh": case["gross"],
                "capture": case["capture"],
                "coverage": case["coverage"],
                "mech_price": case["mech"],
                "capex_cny": case["capex"],
                "npv_cny": result["npv_cny"],
                "irr": result["irr"],
                "payback_years": result["payback_years"],
                "dscr_min": result["dscr_min"],
                "pass": verdict["pass"],
            }
        )
    return rows


def build_bid_ladder(bundle, base, break_even):
    values = bundle["values"]
    capex = values["capacity"] * 1000.0 * values["capex_per_kw"]
    opex = values["capacity"] * 1000.0 * values["opex_per_kw"]
    prices = sorted(set(BID_LADDER) | {round(break_even, 4)})
    rows = []
    for price in prices:
        result = finance_case(
            bundle,
            base["gross"],
            base["capture"],
            values["coverage"],
            price,
            capex,
            opex,
            values["curtailment"],
        )
        verdict = decision(bundle, result)
        if price > values["bid_cap"] + 1e-12:
            label = "超申报上限"
        elif price < values["bid_floor"] - 1e-12:
            label = "低于申报下限"
        elif price + 1e-12 < break_even:
            label = "低于税后盈亏平衡"
        elif verdict["pass"]:
            label = "可投（达门槛）"
        else:
            label = "不达门槛"
        rows.append(
            {
                "bid_cny_per_kwh": price,
                "vs_break_even_cny_per_mwh": (price - break_even) * 1000.0,
                "cover_headroom_cny_per_mwh": (values["bid_cap"] - price) * 1000.0,
                "npv_cny": result["npv_cny"],
                "irr": result["irr"],
                "payback_years": result["payback_years"],
                "dscr_min": result["dscr_min"],
                "pass": verdict["pass"],
                "label": label,
            }
        )
    return rows


def _fmt_cny(value):
    return f"{value:,.0f}"


def _fmt_wan(value):
    return f"{value / 1e4:,.2f}"


def _fmt_pct(value):
    return "不适用" if value is None else f"{value * 100:.2f}%"


def _fmt_years(value):
    return "未回收" if value is None else f"{value:.2f}"


def _fmt_price(value):
    return f"{value:.4f}"


def _fmt_hours(value):
    return f"{value:,.1f}"


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_outputs(bundle, resource, out_dir):
    values = bundle["values"]
    gross = resource["gross"]
    capture = resource["weighted_capture"]
    capex = values["capacity"] * 1000.0 * values["capex_per_kw"]
    opex = values["capacity"] * 1000.0 * values["opex_per_kw"]

    monthly = []
    for month, gen, cap_rate in zip(resource["months"], resource["generation"], resource["capture"]):
        net = gen * (1.0 - values["curtailment"])
        covered = net * values["coverage"]
        settled = cfd_settlement(
            values["mech_price"], values["market_price"], covered, net, values["green_cert"]
        )
        market_rev = capture_price(values["market_price"], cap_rate) * net * 1000.0
        total = market_rev + settled["transfer"] + settled["certificate_revenue"]
        monthly.append(
            {
                "month": month,
                "generation_mwh": round(gen, 3),
                "net_generation_mwh": round(net, 3),
                "capture_rate": round(cap_rate, 6),
                "capture_price_cny_per_kwh": round(capture_price(values["market_price"], cap_rate), 6),
                "covered_mwh": round(covered, 3),
                "market_revenue_cny": round(market_rev, 2),
                "transfer_cny": round(settled["transfer"], 2),
                "certificate_revenue_cny": round(settled["certificate_revenue"], 2),
                "total_revenue_cny": round(total, 2),
                "effective_price_cny_per_kwh": round(total / (net * 1000.0), 6),
            }
        )

    base_revenue = revenue_case(
        bundle, gross, capture, values["coverage"], values["mech_price"], values["curtailment"]
    )
    base_finance = finance_case(
        bundle,
        gross,
        capture,
        values["coverage"],
        values["mech_price"],
        capex,
        opex,
        values["curtailment"],
    )

    lcoe_result = lcoe(
        capex,
        opex,
        gross,
        values["life"],
        values["discount"],
        values["degradation"],
        values["curtailment"],
        values["escalation"],
    )
    pre_tax_be = pre_tax_break_even(bundle, lcoe_result["lcoe"], capture)
    after_tax_be = after_tax_break_even(
        bundle, gross, capture, values["coverage"], values["curtailment"], values["hurdle"]
    )
    bid_floor = math.ceil(after_tax_be * 10000.0) / 10000.0
    headroom = values["bid_cap"] - bid_floor

    p90_hours = p90_from_p50(values["p50_hours"], values["p90_cv"])
    p90_gross = annual_energy_mwh(values["capacity"], p90_hours)

    finance_rows = []
    cumulative = 0.0
    dep = capex / values["dep_years"]
    for year, flow in enumerate(base_finance["flows"]):
        if year == 0:
            revenue = 0.0
            cost = 0.0
            depreciation = 0.0
            taxable = 0.0
            tax_value = 0.0
            cumulative = flow
        else:
            revenue = base_revenue["total_revenue_cny"] * (1.0 - values["degradation"]) ** (year - 1)
            cost = opex * (1.0 + values["escalation"]) ** (year - 1)
            depreciation = dep if year <= values["dep_years"] else 0.0
            taxable = max(revenue - cost - depreciation, 0.0)
            tax_value = taxable * values["tax"]
            cumulative += flow
        finance_rows.append(
            {
                "year": year,
                "revenue_cny": round(revenue, 2),
                "opex_cny": round(cost, 2),
                "depreciation_cny": round(depreciation, 2),
                "taxable_income_cny": round(taxable, 2),
                "tax_cny": round(tax_value, 2),
                "after_tax_flow_cny": round(flow, 2),
                "cumulative_flow_cny": round(cumulative, 2),
            }
        )

    sensitivity = build_sensitivity(bundle, {"gross": gross, "capture": capture}, p90_gross)
    bid = build_bid_ladder(bundle, {"gross": gross, "capture": capture}, after_tax_be)

    warnings = list(resource["warnings"])
    if values["mech_price"] < after_tax_be:
        warnings.append(
            f"当前机制电价 {values['mech_price']:.4f} 低于 8% 门槛的税后盈亏平衡价 {after_tax_be:.4f} 元/kWh"
        )
    if after_tax_be > values["bid_cap"]:
        warnings.append("税后盈亏平衡价高于申报上限，按上限申报也不达门槛")
    if after_tax_be < values["bid_floor"]:
        warnings.append("税后盈亏平衡价低于申报下限，需复核成本假设")
    if not decision(bundle, base_finance)["pass"]:
        warnings.append("基准情景未同时满足 IRR / NPV / DSCR 三项门槛")
    if headroom < 0.002:
        warnings.append(
            f"盈亏平衡价距申报上限仅 {headroom * 1000:.2f} 元/MWh，申报区间极窄"
        )

    fingerprint = hashlib.sha1(
        json.dumps(bundle["policy"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]

    summary = {
        "meta": bundle["meta"],
        "fingerprint": fingerprint,
        "config": {
            "profile_id": bundle["policy"]["profile_id"],
            "capacity_mw": values["capacity"],
            "p50_hours": values["p50_hours"],
            "p90_hours": round(p90_hours, 2),
            "mechanism_price_cny_per_kwh": values["mech_price"],
            "bid_cap_cny_per_kwh": values["bid_cap"],
            "coverage_ratio": values["coverage"],
            "market_price_cny_per_kwh": values["market_price"],
            "green_certificate_cny_per_mwh": values["green_cert"],
            "capex_cny": capex,
            "opex_cny_per_year": opex,
            "discount_rate": values["discount"],
            "hurdle_irr": values["hurdle"],
            "min_dscr": values["min_dscr"],
        },
        "resource": {
            "gross_generation_mwh": round(gross, 3),
            "net_generation_mwh": round(base_revenue["net_mwh"], 3),
            "implied_hours": round(resource["implied_hours"], 2),
            "weighted_capture_rate": round(capture, 6),
            "capture_price_cny_per_kwh": round(base_revenue["capture_price_cny_per_kwh"], 6),
        },
        "annual": {
            "covered_mwh": round(base_revenue["covered_mwh"], 3),
            "market_revenue_cny": round(base_revenue["market_revenue_cny"], 2),
            "transfer_cny": round(base_revenue["transfer_cny"], 2),
            "certificate_revenue_cny": round(base_revenue["certificate_revenue_cny"], 2),
            "total_revenue_cny": round(base_revenue["total_revenue_cny"], 2),
            "effective_price_cny_per_kwh": round(base_revenue["effective_price_cny_per_kwh"], 6),
        },
        "lcoe": {
            "lcoe_cny_per_mwh": round(lcoe_result["lcoe"], 2),
            "capex_share": round(lcoe_result["capex_share"], 4),
            "opex_share": round(lcoe_result["opex_share"], 4),
            "pre_tax_break_even_cny_per_kwh": round(pre_tax_be, 6),
        },
        "break_even": {
            "after_tax_break_even_cny_per_kwh": round(after_tax_be, 6),
            "bid_floor_cny_per_kwh": round(bid_floor, 4),
            "bid_cap_cny_per_kwh": values["bid_cap"],
            "headroom_cny_per_kwh": round(headroom, 6),
        },
        "finance": {
            "npv_cny": round(base_finance["npv_cny"], 2),
            "irr": round(base_finance["irr"], 6) if base_finance["irr"] is not None else None,
            "payback_years": round(base_finance["payback_years"], 3) if base_finance["payback_years"] else None,
            "debt_cny": round(base_finance["debt_cny"], 2),
            "debt_service_cny": round(base_finance["debt_service_cny"], 2),
            "dscr_year1": round(base_finance["dscr_year1"], 4),
            "dscr_min": round(base_finance["dscr_min"], 4),
            "decision": decision(bundle, base_finance),
        },
        "bid": [
            {
                "price": round(row["bid_cny_per_kwh"], 6),
                "irr": round(row["irr"], 6) if row["irr"] is not None else None,
                "npv_cny": round(row["npv_cny"], 2),
                "dscr_min": round(row["dscr_min"], 4),
                "label": row["label"],
            }
            for row in bid
        ],
        "sensitivity": [
            {
                "case": row["case"],
                "irr": round(row["irr"], 6) if row["irr"] is not None else None,
                "npv_cny": round(row["npv_cny"], 2),
                "dscr_min": round(row["dscr_min"], 4),
                "pass": row["pass"],
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
        monthly,
        [
            "month",
            "generation_mwh",
            "net_generation_mwh",
            "capture_rate",
            "capture_price_cny_per_kwh",
            "covered_mwh",
            "market_revenue_cny",
            "transfer_cny",
            "certificate_revenue_cny",
            "total_revenue_cny",
            "effective_price_cny_per_kwh",
        ],
    )
    write_csv(
        out_dir / "finance.csv",
        finance_rows,
        [
            "year",
            "revenue_cny",
            "opex_cny",
            "depreciation_cny",
            "taxable_income_cny",
            "tax_cny",
            "after_tax_flow_cny",
            "cumulative_flow_cny",
        ],
    )
    write_csv(
        out_dir / "bid.csv",
        bid,
        [
            "bid_cny_per_kwh",
            "vs_break_even_cny_per_mwh",
            "cover_headroom_cny_per_mwh",
            "npv_cny",
            "irr",
            "payback_years",
            "dscr_min",
            "pass",
            "label",
        ],
    )
    write_csv(
        out_dir / "sensitivity.csv",
        sensitivity,
        [
            "case",
            "change",
            "gross_mwh",
            "capture",
            "coverage",
            "mech_price",
            "capex_cny",
            "npv_cny",
            "irr",
            "payback_years",
            "dscr_min",
            "pass",
        ],
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "review.md").write_text(
        render_review(bundle, summary, monthly, bid, sensitivity),
        encoding="utf-8",
    )
    return summary


def render_review(bundle, summary, monthly, bid, sensitivity):
    meta = bundle["meta"]
    values = bundle["values"]
    res = summary["resource"]
    annual = summary["annual"]
    fin = summary["finance"]
    be = summary["break_even"]
    lc = summary["lcoe"]

    first_month = monthly[0]
    last_month = monthly[-1]
    lines = [
        f"# {meta['province']}风电开发期投决 · 复核表",
        "",
        f"- 实例：`{meta['instance_id']}`（{meta['entity_type']}）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}；全部资源、价格与成本为 D 级合成数据",
        "",
        "## 1. 结论",
        "",
    ]
    base_pass = fin["decision"]["pass"]
    if base_pass:
        lines.append(
            f"基准情景在机制电价 {values['mech_price']:.4f} 元/kWh 下 IRR "
            f"{_fmt_pct(fin['irr'])}、NPV {_fmt_wan(fin['npv_cny'])} 万元、最低 DSCR "
            f"{fin['dscr_min']:.2f}，三项门槛同时通过，但安全垫很薄。"
        )
    else:
        lines.append(
            f"基准情景在机制电价 {values['mech_price']:.4f} 元/kWh 下未同时通过 IRR / NPV / DSCR 门槛，"
            "不应按当前参数投决。"
        )
    lines.extend(
        [
            f"8% 门槛的税后盈亏平衡价为 **{be['after_tax_break_even_cny_per_kwh']:.4f} 元/kWh**，"
            f"申报上限 {be['bid_cap_cny_per_kwh']:.4f}，可投区间宽度仅 "
            f"{be['headroom_cny_per_kwh'] * 1000:.2f} 元/MWh。",
            "任一单项压力（造价 +10%、电量 −10%、运维 +20%、限电 10%、捕获率 88%、覆盖 50%、P90）"
            "都会把 IRR 压到 8% 以下；组合压力下三项门槛全部失守。",
            "",
            "## 2. 资源与电量",
            "",
            "| 项目 | 值 |",
            "|---|---:|",
            f"| 装机容量 | {values['capacity']:,.0f} MW |",
            f"| P50 利用小时 | {values['p50_hours']:,.0f} h |",
            f"| P90 利用小时 | {summary['config']['p90_hours']:,.1f} h |",
            f"| 首年毛发电量 | {res['gross_generation_mwh']:,.1f} MWh |",
            f"| 扣限电后净电量 | {res['net_generation_mwh']:,.1f} MWh |",
            f"| 加权捕获率 | {res['weighted_capture_rate'] * 100:.2f}% |",
            f"| 捕获价（市场均价 × 捕获率） | {res['capture_price_cny_per_kwh']:.4f} 元/kWh |",
            f"| 数据隐含利用小时 | {res['implied_hours']:,.1f} h |",
            "",
            "## 3. 年度收入拆分",
            "",
            "| 项目 | 金额（万元） | 说明 |",
            "|---|---:|---|",
            f"| 市场电量收入 | {_fmt_wan(annual['market_revenue_cny'])} | 净电量 × 捕获价，不是市场均价 |",
            f"| 机制差价 | {_fmt_wan(annual['transfer_cny'])} | (机制价 − 市场均价) × 机制电量 |",
            f"| 绿证收入 | {_fmt_wan(annual['certificate_revenue_cny'])} | 6 元/MWh × 净电量 |",
            f"| 合计 | {_fmt_wan(annual['total_revenue_cny'])} | 综合度电收入 {annual['effective_price_cny_per_kwh']:.4f} 元/kWh |",
            "",
            f"机制电量 {annual['covered_mwh']:,.1f} MWh，覆盖比例 {values['coverage'] * 100:.0f}%；"
            f"剩余 {100 - values['coverage'] * 100:.0f}% 电量只拿捕获价。",
            "",
            "## 4. 成本与盈亏平衡",
            "",
            "| 项目 | 值 |",
            "|---|---:|",
            f"| 单位造价 | {values['capex_per_kw']:,.0f} 元/kW |",
            f"| 单位运维 | {values['opex_per_kw']:,.0f} 元/kW·年 |",
            f"| 税前 LCOE | {lc['lcoe_cny_per_mwh']:,.2f} 元/MWh |",
            f"| 税前机制价盈亏平衡 | {lc['pre_tax_break_even_cny_per_kwh']:.4f} 元/kWh |",
            f"| 税后 8% 门槛盈亏平衡 | {be['after_tax_break_even_cny_per_kwh']:.4f} 元/kWh |",
            f"| 申报上限 | {be['bid_cap_cny_per_kwh']:.4f} 元/kWh |",
            f"| 盈亏平衡价距上限 | {be['headroom_cny_per_kwh'] * 1000:.2f} 元/MWh |",
            "",
            "税前 LCOE 口径不含所得税与权益回报，不能直接当作申报底线；"
            "税后盈亏平衡价同时包含 25% 所得税、8% 折现与 20 年折旧。",
            "",
            "## 5. 财务指标",
            "",
            "| 指标 | 值 | 门槛 | 判定 |",
            "|---|---:|---:|---|",
            f"| 项目 NPV | {_fmt_wan(fin['npv_cny'])} 万元 | ≥ 0 | {'通过' if fin['npv_cny'] >= 0 else '不通过'} |",
            f"| 项目 IRR | {_fmt_pct(fin['irr'])} | ≥ {values['hurdle'] * 100:.1f}% | {'通过' if fin['decision']['irr_ok'] else '不通过'} |",
            f"| 最低 DSCR | {fin['dscr_min']:.2f} | ≥ {values['min_dscr']:.2f} | {'通过' if fin['decision']['dscr_ok'] else '不通过'} |",
            f"| 静态回收期 | {_fmt_years(fin['payback_years'])} 年 | — | — |",
            f"| 债务本金 | {_fmt_wan(fin['debt_cny'])} 万元 | — | — |",
            f"| 年度还本付息 | {_fmt_wan(fin['debt_service_cny'])} 万元 | — | — |",
            "",
            f"DSCR 以各年 CFADS / 等额还本付息计算，并取还本期内的最低值（首年 "
            f"{fin['dscr_year1']:.2f}）；本包未在 CFADS 中扣除利息，也未计利息税盾，属于 D 级简化。",
            "",
            "## 6. 投标区间",
            "",
            "| 申报价（元/kWh） | NPV（万元） | IRR | 最低 DSCR | 相对盈亏平衡（元/MWh） | 判定 |",
            "|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in bid:
        lines.append(
            f"| {row['bid_cny_per_kwh']:.4f} | {_fmt_wan(row['npv_cny'])} | {_fmt_pct(row['irr'])} | "
            f"{row['dscr_min']:.2f} | {row['vs_break_even_cny_per_mwh']:+.2f} | {row['label']} |"
        )
    lines.extend(
        [
            "",
            f"建议可投下限为税后盈亏平衡价向上取整到 0.1 分，即 "
            f"{be['bid_floor_cny_per_kwh']:.4f} 元/kWh；低于该价的申报在 8% 门槛下不成立。",
            "",
            "## 7. 敏感性",
            "",
            "| 情景 | IRR | NPV（万元） | 最低 DSCR | 判定 |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for row in sensitivity:
        lines.append(
            f"| {row['case']} | {_fmt_pct(row['irr'])} | {_fmt_wan(row['npv_cny'])} | "
            f"{row['dscr_min']:.2f} | {'通过' if row['pass'] else '不通过'} |"
        )
    lines.extend(
        [
            "",
            "## 8. 口径提醒",
            "",
            "- 机制电价只覆盖 65% 电量，剩余电量按捕获价结算；把机制价当全额上网电价会高估收入。",
            "- 市场收入按捕获价（市场均价 × 月度捕获率）计，机制差价按市场均价计，两者不能互换。",
            "- 税前 LCOE 与税前盈亏平衡价不含所得税和权益回报，不能直接作为申报底线。",
            "- 申报上限 0.3358 与税后盈亏平衡价之间的安全垫很薄，竞价结果或造价波动即可翻转结论。",
            "- 云南省 2027 年第一次竞价参数为公示口径（2026-06-16），正式文件与后续批次可能调整；"
            "本包不构成投标、融资或投资建议。",
            "",
            f"数据文件覆盖 {first_month['month']} 至 {last_month['month']}；"
            f"本复核表由 `run.py` 生成，风格指纹 `{summary['fingerprint']}`。",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="云南 100 MW 风电开发期投决实例")
    parser.add_argument("--instance", type=Path, default=HERE / "instance.json")
    parser.add_argument("--resource", type=Path, help="月度资源 CSV；--demo 时省略")
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
        print(f"风格: {bundle['policy']['profile_id']}")
        print("规则来源:")
        for row in bundle["report"]:
            print(f"  - {row['block']} [{row['grade']}] {row['source'][:90]}")
        return 0

    if args.resource is not None:
        resource_path = args.resource
    elif args.demo:
        resource_path = HERE / bundle["resource"]["file"]
    else:
        print("请用 --resource 指定月度资源 CSV，或加 --demo 使用合成数据", file=sys.stderr)
        return 2

    try:
        resource = load_resource(resource_path, bundle)
        out_dir = args.out / "demo" if args.demo else args.out
        summary = build_outputs(bundle, resource, out_dir)
    except ConfigError as exc:
        print(f"数据错误: {exc}", file=sys.stderr)
        return 2

    fin = summary["finance"]
    be = summary["break_even"]
    print(f"输出目录: {out_dir}")
    print(f"首年毛发电量: {summary['resource']['gross_generation_mwh']:,.1f} MWh")
    print(f"综合度电收入: {summary['annual']['effective_price_cny_per_kwh']:.4f} 元/kWh")
    print(f"LCOE: {summary['lcoe']['lcoe_cny_per_mwh']:,.2f} 元/MWh")
    print(f"税后 8% 盈亏平衡价: {be['after_tax_break_even_cny_per_kwh']:.4f} 元/kWh")
    print(f"NPV: {fin['npv_cny'] / 1e4:,.2f} 万元 · IRR: {_fmt_pct(fin['irr'])} · 最低 DSCR: {fin['dscr_min']:.2f}")
    print(f"投决结论: {'通过' if fin['decision']['pass'] else '不通过'}")
    for warning in summary["warnings"]:
        print(f"警告: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
