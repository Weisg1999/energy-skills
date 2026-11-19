#!/usr/bin/env python3
"""Guangdong retail-inversion instance runner: replay, attribute, scan.

This is a strategy-failure/boundary instance package: it replays the monthly
P&L of a fixed-price retail book under a spot-price upside path, attributes the
wholesale-retail inversion (批零倒挂) by customer segment and month, and scans
the stop-loss boundary over (wholesale cost uplift × linkage share × stop line).

Three replay tracks on the realized monthly path:
    Track A  失败盘   —— 100% 固定价、无联动、无止损（案例 7 的核心错误）
    Track B  对照盘   —— 签约即按 linkage.target_share 联动（有联动、无止损）
    Track C  止损盘   —— 止损线/联动触发价触发后，滞后 action_lag_months 转联动

The instance is a configuration package, not a forecast. All demo data are
grade-D synthetic and correspond to no real retailer, customer or contract.
It is the runnable quantification of case 7 (批零倒挂·套餐无联动无止损) in
knowledge/合成案例复盘库-2026-11.md.

Commands:
    python run.py --check-config
    python run.py --demo
    python run.py --monthly data/monthly_demo.csv --out out/run
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    import deviation  # noqa: E402  引擎层：偏差超带电量与考核成本
    import guarantee  # noqa: E402  引擎层：1595 号保函公式与资金成本
    import package    # noqa: E402  引擎层：联动套餐价格与固定价保本现货
    import portfolio  # noqa: E402  引擎层：单客户群度电毛利
except ImportError as exc:
    print(f"无法导入引擎层 tools/（deviation/guarantee/package/portfolio）：{exc}", file=sys.stderr)
    raise SystemExit(2)

RULE_BLOCKS = ("spot", "retail_market", "deviation", "guarantee", "settlement")
PACKAGE_TYPES = {"fixed", "tou", "market_linked", "floor_plus_float", "service_fee"}
GRADE_RE = re.compile(r"^[ABCD](/[ABCD])*$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ConfigError(ValueError):
    """The instance configuration is invalid."""


class InputError(ValueError):
    """The monthly replay input file is invalid."""


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _require(block, key, where, errors):
    if not isinstance(block, dict) or key not in block or block[key] in (None, ""):
        errors.append(f"{where}.{key} 缺失")
        return None
    return block[key]


def _number(block, key, where, errors, minimum=None, maximum=None):
    value = _require(block, key, where, errors)
    if value is None:
        return None
    if not _is_number(value):
        errors.append(f"{where}.{key} 必须是数字")
        return None
    value = float(value)
    if minimum is not None and value < minimum:
        errors.append(f"{where}.{key} 不能小于 {minimum}")
    if maximum is not None and value > maximum:
        errors.append(f"{where}.{key} 不能大于 {maximum}")
    return value


def _non_empty_list(value, where, errors):
    if not isinstance(value, list) or not value:
        errors.append(f"{where} 必须是非空数组")
        return []
    return value


# ---------------------------------------------------------------- 配置校验


def validate_instance(config):
    """Validate all blocks and return a report; raise ConfigError on errors."""
    errors = []
    warnings = []

    if not isinstance(config, dict):
        raise ConfigError("实例配置必须是 JSON 对象")

    meta = config.get("meta")
    if not isinstance(meta, dict):
        raise ConfigError("缺少 meta 块")
    for key in ("instance_id", "province", "market", "entity_type", "rule_version", "data_cutoff", "grade", "scope", "units", "disclaimer"):
        _require(meta, key, "meta", errors)
    if isinstance(meta, dict) and isinstance(meta.get("units"), dict):
        units = meta["units"]
        _require(units, "price", "meta.units", errors)
        _require(units, "energy", "meta.units", errors)
        if str(units.get("price", "")).replace(" ", "").upper() != "CNY/MWH":
            errors.append("meta.units.price 必须是 CNY/MWh")
        if str(units.get("energy", "")).replace(" ", "").upper() != "MWH":
            errors.append("meta.units.energy 必须是 MWh")
    if isinstance(meta, dict) and not str(meta.get("disclaimer", "")).strip():
        errors.append("meta.disclaimer 不能为空")

    rules = config.get("rules")
    if not isinstance(rules, dict):
        errors.append("缺少 rules 块")
        rules = {}
    for name in RULE_BLOCKS:
        block = rules.get(name)
        if not isinstance(block, dict):
            errors.append(f"rules.{name} 缺失")
            continue
        grade = _require(block, "grade", f"rules.{name}", errors)
        source = _require(block, "source", f"rules.{name}", errors)
        if grade is not None and not GRADE_RE.match(str(grade)):
            errors.append(f"rules.{name}.grade 必须是 A/B/C/D 或其组合")
        if source is not None and not str(source).strip():
            errors.append(f"rules.{name}.source 不能为空")

    spot = rules.get("spot", {}) if isinstance(rules, dict) else {}
    mtu = points = clear_floor = clear_cap = None
    if isinstance(spot, dict):
        mtu = _number(spot, "market_time_unit_min", "rules.spot", errors, minimum=1)
        points = _number(spot, "points_per_day", "rules.spot", errors, minimum=1)
        clear_floor = _number(spot, "clear_floor_cny_per_mwh", "rules.spot", errors)
        clear_cap = _number(spot, "clear_cap_cny_per_mwh", "rules.spot", errors)
        declare_floor = _number(spot, "declare_floor_cny_per_mwh", "rules.spot", errors)
        if mtu is not None and points is not None:
            expected_points = 24.0 * 60.0 / mtu
            if abs(points - expected_points) > 1e-9:
                errors.append("rules.spot.points_per_day 必须等于 24×60 / market_time_unit_min")
        if clear_floor is not None and clear_cap is not None and clear_floor >= clear_cap:
            errors.append("rules.spot.clear_floor_cny_per_mwh 必须小于 clear_cap_cny_per_mwh")
        if clear_floor is not None and declare_floor is not None and declare_floor < clear_floor:
            errors.append("rules.spot.declare_floor_cny_per_mwh 不能低于 clear_floor_cny_per_mwh")

    retail_market = rules.get("retail_market", {}) if isinstance(rules, dict) else {}
    if isinstance(retail_market, dict):
        packages = retail_market.get("package_types")
        if packages is not None:
            if not isinstance(packages, list) or not packages:
                errors.append("rules.retail_market.package_types 必须是非空数组")
            else:
                unknown = [item for item in packages if item not in PACKAGE_TYPES]
                if unknown:
                    errors.append(f"rules.retail_market.package_types 含未知套餐类型：{unknown}")
        _number(retail_market, "retail_avg_2026h1_cny_per_mwh", "rules.retail_market", errors, minimum=0)
        _number(retail_market, "margin_2026h1_cny_per_mwh", "rules.retail_market", errors)

    deviation_rule = rules.get("deviation", {}) if isinstance(rules, dict) else {}
    if isinstance(deviation_rule, dict):
        _require(deviation_rule, "guangdong_status", "rules.deviation", errors)
        _require(deviation_rule, "contract_basis", "rules.deviation", errors)
        status = str(deviation_rule.get("guangdong_status", ""))
        if "未核到" in status or "C 级" in status:
            warnings.append("广东偏差考核未核到现行正式规则；本包按合同约定测算，不把 ±3%/±5% 当作省统一规则")

    guarantee_rule = rules.get("guarantee", {}) if isinstance(rules, dict) else {}
    if isinstance(guarantee_rule, dict):
        current = guarantee_rule.get("current")
        draft = guarantee_rule.get("draft_2026_09_04")
        if not isinstance(current, dict):
            errors.append("rules.guarantee.current 缺失")
        else:
            _require(current, "formula", "rules.guarantee.current", errors)
            _require(current, "document", "rules.guarantee.current", errors)
        if isinstance(draft, dict) and draft.get("effective") is True:
            errors.append("rules.guarantee.draft_2026_09_04 是草案，effective 不能为 true")
        if isinstance(draft, dict) and draft.get("effective") is False:
            warnings.append("2026-09-04 售电办法修订稿是草案，本包未按草案保函公式测算")

    settlement = rules.get("settlement", {}) if isinstance(rules, dict) else {}
    if isinstance(settlement, dict):
        _require(settlement, "timeline", "rules.settlement", errors)
        _require(settlement, "document", "rules.settlement", errors)

    portfolio_cfg = config.get("portfolio")
    if not isinstance(portfolio_cfg, dict):
        errors.append("缺少 portfolio 块")
        portfolio_cfg = {}
    segments = _non_empty_list(portfolio_cfg.get("segments"), "portfolio.segments", errors)
    share_sum = 0.0
    names = []
    for index, segment in enumerate(segments):
        where = f"portfolio.segments[{index}]"
        if not isinstance(segment, dict):
            errors.append(f"{where} 必须是对象")
            continue
        name = _require(segment, "name", where, errors)
        if name is not None:
            if name in names:
                errors.append(f"{where}.name 重复：{name}")
            names.append(name)
        package_type = _require(segment, "package_type", where, errors)
        if package_type is not None and package_type not in PACKAGE_TYPES:
            errors.append(f"{where}.package_type 未知：{package_type}")
        elif package_type is not None and package_type != "fixed":
            errors.append(f"{where}.package_type={package_type}：失败重放模型的售价段只支持 fixed，联动比例由 strategy 控制")
        share = _number(segment, "share", where, errors, minimum=0.0, maximum=1.0)
        if share is not None:
            share_sum += share
        _number(segment, "forecast_sigma_pct", where, errors, minimum=0.0, maximum=1.0)
        _number(segment, "opex_cny_per_mwh", where, errors, minimum=0.0)
        if package_type == "fixed":
            _number(segment, "retail_price_cny_per_mwh", where, errors, minimum=0.0)
    if segments and abs(share_sum - 1.0) > 1e-9:
        errors.append(f"portfolio.segments 的 share 之和必须为 1，当前为 {share_sum:.6f}")

    _number(portfolio_cfg, "annual_energy_mwh", "portfolio", errors, minimum=0.0)
    _number(portfolio_cfg, "fixed_cost_cny_per_day", "portfolio", errors, minimum=0.0)

    deviation_terms = portfolio_cfg.get("deviation_terms")
    if not isinstance(deviation_terms, dict):
        errors.append("portfolio.deviation_terms 缺失")
    else:
        _number(deviation_terms, "tolerance_share", "portfolio.deviation_terms", errors, minimum=0.0, maximum=1.0)
        _number(deviation_terms, "penalty_cny_per_mwh", "portfolio.deviation_terms", errors, minimum=0.0)
        _require(deviation_terms, "basis", "portfolio.deviation_terms", errors)

    guarantee_cfg = portfolio_cfg.get("guarantee")
    if not isinstance(guarantee_cfg, dict):
        errors.append("portfolio.guarantee 缺失")
    else:
        amount = _number(guarantee_cfg, "amount_cny", "portfolio.guarantee", errors, minimum=0.0)
        rate = _number(guarantee_cfg, "annual_funding_rate", "portfolio.guarantee", errors, minimum=0.0)
        annual = _number(guarantee_cfg, "annual_wholesale_mwh", "portfolio.guarantee", errors, minimum=0.0)
        peak = _number(guarantee_cfg, "peak_two_month_mwh", "portfolio.guarantee", errors, minimum=0.0)
        _require(guarantee_cfg, "basis", "portfolio.guarantee", errors)
        if amount is not None and annual is not None and peak is not None:
            # 引擎层公式：max(年批发电量×0.008 元/kWh, 2 个月峰值×0.05 元/kWh)，输入为 kWh。
            required = guarantee.current_guarantee(annual * 1000.0, peak * 1000.0, 0.008, 0.05)
            tolerance = max(1.0, 0.01 * required)
            if abs(amount - required) > tolerance:
                warnings.append(
                    f"portfolio.guarantee.amount_cny={amount:,.0f} 与 1595 号公式值 {required:,.0f} 不一致；"
                    "请说明是否改用保险/现金或历史口径"
                )
        if rate is not None and rate > 0.05:
            warnings.append("portfolio.guarantee.annual_funding_rate 高于 5%，请确认不是年化百分数误填")

    strategy = config.get("strategy")
    if not isinstance(strategy, dict):
        errors.append("缺少 strategy 块")
        strategy = {}
    _number(strategy, "baseline_linkage_share", "strategy", errors, minimum=0.0, maximum=1.0)
    _require(strategy, "notes", "strategy", errors)
    linkage = strategy.get("linkage")
    if not isinstance(linkage, dict):
        errors.append("strategy.linkage 缺失")
    else:
        _number(linkage, "pass_through", "strategy.linkage", errors, minimum=0.0, maximum=1.0)
        _number(linkage, "adder_cny_per_mwh", "strategy.linkage", errors)
        floor_l = _number(linkage, "floor_cny_per_mwh", "strategy.linkage", errors)
        cap_l = _number(linkage, "cap_cny_per_mwh", "strategy.linkage", errors)
        if floor_l is not None and cap_l is not None and floor_l > cap_l:
            errors.append("strategy.linkage.floor_cny_per_mwh 不能大于 cap_cny_per_mwh")
        _number(linkage, "target_share", "strategy.linkage", errors, minimum=0.0, maximum=1.0)
    stop_loss = strategy.get("stop_loss")
    if not isinstance(stop_loss, dict):
        errors.append("strategy.stop_loss 缺失")
    else:
        _number(stop_loss, "margin_line_cny_per_mwh", "strategy.stop_loss", errors)
        trigger_price = _number(stop_loss, "linkage_trigger_price_cny_per_mwh", "strategy.stop_loss", errors, minimum=0.0)
        lag = stop_loss.get("action_lag_months")
        if not isinstance(lag, int) or isinstance(lag, bool) or not 0 <= lag <= 3:
            errors.append("strategy.stop_loss.action_lag_months 必须是 0–3 的整数")
        actions = _non_empty_list(stop_loss.get("actions"), "strategy.stop_loss.actions", errors)
        if actions and any(not isinstance(item, str) or not item.strip() for item in actions):
            errors.append("strategy.stop_loss.actions 必须全是非空字符串")
        if trigger_price is not None and trigger_price == 0.0:
            warnings.append("strategy.stop_loss.linkage_trigger_price_cny_per_mwh=0：任何月份都会触发，请确认不是笔误")

    policy = config.get("policy")
    if not isinstance(policy, dict):
        errors.append("缺少 policy 块")
        policy = {}
    _require(policy, "profile_id", "policy", errors)
    top_attr = policy.get("review_top_attribution")
    if not isinstance(top_attr, int) or isinstance(top_attr, bool) or top_attr < 0:
        errors.append("policy.review_top_attribution 必须是非负整数")
    scan = policy.get("scan")
    if not isinstance(scan, dict):
        errors.append("缺少 policy.scan 块")
        scan = {}
    if isinstance(scan, dict):
        uplift = _non_empty_list(scan.get("spot_uplift_steps"), "policy.scan.spot_uplift_steps", errors)
        for value in uplift:
            if not _is_number(value) or not 0.0 <= float(value) <= 2.0:
                errors.append("policy.scan.spot_uplift_steps 必须在 [0, 2] 内")
                break
        shares = _non_empty_list(scan.get("linkage_share_steps"), "policy.scan.linkage_share_steps", errors)
        for value in shares:
            if not _is_number(value) or not 0.0 <= float(value) <= 1.0:
                errors.append("policy.scan.linkage_share_steps 必须在 [0, 1] 内")
                break
        lines = _non_empty_list(scan.get("stop_loss_line_steps"), "policy.scan.stop_loss_line_steps", errors)
        for value in lines:
            if not _is_number(value):
                errors.append("policy.scan.stop_loss_line_steps 必须全是数字（可为负）")
                break

    contracts = config.get("contracts")
    if contracts is None:
        contracts = []
    if not isinstance(contracts, list):
        errors.append("contracts 必须是数组")
        contracts = []
    if len(contracts) > 1:
        errors.append("本运行器只支持一份中长期合约；多合约分段请拆实例")
    for index, contract in enumerate(contracts):
        where = f"contracts[{index}]"
        if not isinstance(contract, dict):
            errors.append(f"{where} 必须是对象")
            continue
        _require(contract, "contract_id", where, errors)
        contract_type = _require(contract, "type", where, errors)
        if contract_type is not None and contract_type != "medium_term_fixed_price":
            errors.append(f"{where}.type 目前只支持 medium_term_fixed_price")
        _number(contract, "coverage_ratio", where, errors, minimum=0.0, maximum=1.0)
        _number(contract, "price_cny_per_mwh", where, errors, minimum=0.0)
        basis = _require(contract, "quantity_basis", where, errors)
        if basis is not None and basis != "forecast_load_share":
            errors.append(f"{where}.quantity_basis 目前只支持 forecast_load_share")

    data_contract = config.get("data_contract")
    if not isinstance(data_contract, dict):
        errors.append("缺少 data_contract 块")
        data_contract = {}
    monthly = data_contract.get("monthly")
    if not isinstance(monthly, dict):
        errors.append("data_contract.monthly 缺失")
    else:
        for field in ("path", "month_field", "realized_price_field", "grade", "source"):
            _require(monthly, field, "data_contract.monthly", errors)
        scenario_fields = _non_empty_list(monthly.get("scenario_fields"), "data_contract.monthly.scenario_fields", errors)
        weights = _non_empty_list(monthly.get("scenario_weights"), "data_contract.monthly.scenario_weights", errors)
        if scenario_fields and weights:
            if len(scenario_fields) != len(weights):
                errors.append("data_contract.monthly.scenario_fields 与 scenario_weights 长度不一致")
            elif abs(sum(float(w) for w in weights if _is_number(w)) - 1.0) > 1e-9:
                errors.append("data_contract.monthly.scenario_weights 之和必须为 1")
        seg_entries = _non_empty_list(monthly.get("segments"), "data_contract.monthly.segments", errors)
        portfolio_names = [str(segment.get("name")) for segment in segments if isinstance(segment, dict)]
        entry_names = []
        for index, entry in enumerate(seg_entries):
            where = f"data_contract.monthly.segments[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{where} 必须是对象")
                continue
            name = _require(entry, "name", where, errors)
            if name is not None:
                entry_names.append(str(name))
                if str(name) not in portfolio_names:
                    errors.append(f"{where}.name={name} 与 portfolio.segments 不一致")
            f_field = _require(entry, "forecast_field", where, errors)
            a_field = _require(entry, "actual_field", where, errors)
            if f_field is not None and a_field is not None and f_field == a_field:
                errors.append(f"{where}.forecast_field 与 actual_field 不能相同")
        if entry_names and sorted(entry_names) != sorted(portfolio_names):
            errors.append("data_contract.monthly.segments 必须与 portfolio.segments 一一对应")

    if meta.get("grade") == "D":
        warnings.append("实例资产、客户、合约、价格路径与演示数据为 D 级合成，不得直接用于真实报价、签约或复盘归档")
    notice = str(retail_market.get("price_linkage_notice", "")) if isinstance(retail_market, dict) else ""
    if "未核到正式文号" in notice:
        warnings.append("2026-06-08 零售市场管理通知未核到正式文号，按 B/C 级线索使用")
    if isinstance(strategy, dict) and float(strategy.get("baseline_linkage_share") or 0.0) == 0.0:
        warnings.append("baseline_linkage_share=0：Track A 是失败重放（无联动无止损），Track B/C 是对照情景而非历史事实")

    if errors:
        raise ConfigError("配置校验失败：\n- " + "\n- ".join(errors))

    fingerprint = hashlib.sha1(
        json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    provenance = []
    for name in RULE_BLOCKS:
        block = rules[name]
        provenance.append({"block": name, "grade": block["grade"], "source": block["source"]})

    return {
        "ok": True,
        "errors": [],
        "warnings": warnings,
        "style_fingerprint": fingerprint,
        "provenance": provenance,
    }


# ---------------------------------------------------------------- 输入读取


def _parse_float(value, where):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{where} 不是数字：{value!r}") from exc
    if not math.isfinite(number):
        raise InputError(f"{where} 不是有限数：{value!r}")
    return number


def read_monthly(path, config, report):
    """Read and validate the monthly replay CSV."""
    contract = config["data_contract"]["monthly"]
    fields = [contract["month_field"], contract["realized_price_field"]] + list(contract["scenario_fields"])
    for entry in contract["segments"]:
        fields += [entry["forecast_field"], entry["actual_field"]]
    path = Path(path)
    if not path.exists():
        raise InputError(f"输入文件不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InputError(f"输入文件没有表头：{path}")
        missing = [field for field in fields if field not in reader.fieldnames]
        if missing:
            raise InputError(f"{path.name} 缺字段：{missing}")
        rows = list(reader)
    if not rows:
        raise InputError(f"输入文件没有数据行：{path}")

    spot_cfg = config["rules"]["spot"]
    floor = float(spot_cfg["clear_floor_cny_per_mwh"])
    cap = float(spot_cfg["clear_cap_cny_per_mwh"])

    months = []
    realized = []
    scenarios = {field: [] for field in contract["scenario_fields"]}
    forecast = {entry["name"]: [] for entry in contract["segments"]}
    actual = {entry["name"]: [] for entry in contract["segments"]}
    for index, row in enumerate(rows):
        where = f"{path.name} 第 {index + 2} 行"
        month = str(row[contract["month_field"]] or "").strip()
        if not MONTH_RE.match(month):
            raise InputError(f"{where} month={month!r} 不是 YYYY-MM 格式")
        if month in months:
            raise InputError(f"{where} 月份重复：{month}")
        months.append(month)
        price = _parse_float(row[contract["realized_price_field"]], f"{where} {contract['realized_price_field']}")
        if price < floor - 1e-9 or price > cap + 1e-9:
            raise InputError(f"{where} {contract['realized_price_field']}={price} 越界（{floor}–{cap} CNY/MWh）")
        realized.append(price)
        for field in contract["scenario_fields"]:
            value = _parse_float(row[field], f"{where} {field}")
            if value < floor - 1e-9 or value > cap + 1e-9:
                raise InputError(f"{where} {field}={value} 越界（{floor}–{cap} CNY/MWh）")
            scenarios[field].append(value)
        for entry in contract["segments"]:
            name = entry["name"]
            f_value = _parse_float(row[entry["forecast_field"]], f"{where} {entry['forecast_field']}")
            a_value = _parse_float(row[entry["actual_field"]], f"{where} {entry['actual_field']}")
            if f_value < 0 or a_value < 0:
                raise InputError(f"{where} 电量不能为负")
            forecast[name].append(f_value)
            actual[name].append(a_value)

    if sum(sum(values) for values in forecast.values()) <= 0:
        raise InputError(f"{path.name} 预测电量合计必须为正")
    if len(months) != 12:
        report["warnings"].append(f"复盘窗口为 {len(months)} 个月（{months[0]} .. {months[-1]}），不是完整 12 个月年度复盘")

    weights = [float(value) for value in contract["scenario_weights"]]
    return {
        "path": str(path),
        "months": months,
        "realized": realized,
        "scenarios": scenarios,
        "scenario_fields": list(contract["scenario_fields"]),
        "scenario_labels": list(contract.get("scenario_labels") or contract["scenario_fields"]),
        "weights": weights,
        "forecast": forecast,
        "actual": actual,
        "segment_names": [entry["name"] for entry in contract["segments"]],
    }


# ---------------------------------------------------------------- 重放模型


def _contract_terms(config):
    contracts = config.get("contracts") or []
    if not contracts:
        return 0.0, 0.0
    return float(contracts[0]["coverage_ratio"]), float(contracts[0]["price_cny_per_mwh"])


def _wholesale_cost(coverage, contract_price, spot):
    return coverage * contract_price + (1.0 - coverage) * spot


def _linked_price(wholesale, linkage):
    """联动价 = clamp(传导系数×月度加权采购成本 + 加价, 下限, 上限)（引擎层 package.market_linked_price）。"""
    return package.market_linked_price(
        wholesale,
        pass_through=float(linkage["pass_through"]),
        adder=float(linkage["adder_cny_per_mwh"]),
        floor=float(linkage["floor_cny_per_mwh"]),
        cap=float(linkage["cap_cny_per_mwh"]),
    )


def _days_in_month(month):
    year, m = int(month[:4]), int(month[5:7])
    return calendar.monthrange(year, m)[1]


def _monthly_guarantee(config):
    guarantee_cfg = config["portfolio"]["guarantee"]
    annual = guarantee.funding_cost(float(guarantee_cfg["amount_cny"]), float(guarantee_cfg["annual_funding_rate"]))
    return annual / 12.0


def replay_month(config, data, idx, spot, linkage_share):
    """Replay one month at a given spot price and linkage share.

    结算口径：Qc_i = 覆盖比例 × 月度预测电量（按客户群预测份额分摊）；
    电量成本_i = Qc_i×Pc + (实际电量_i − Qc_i)×当月现货价（偏差电量按实时价口径，广东 §3，B）。
    联动部分电量按 clamp(α×W_m + 加价, 下限, 上限) 结算，W_m 为月度加权采购成本。
    """
    portfolio_cfg = config["portfolio"]
    segments = portfolio_cfg["segments"]
    terms = portfolio_cfg["deviation_terms"]
    tolerance = float(terms["tolerance_share"])
    penalty = float(terms["penalty_cny_per_mwh"])
    coverage, contract_price = _contract_terms(config)
    linkage = config["strategy"]["linkage"]
    month = data["months"][idx]

    wholesale = _wholesale_cost(coverage, contract_price, spot)
    price_link = _linked_price(wholesale, linkage)

    energy_forecast = 0.0
    energy_actual = 0.0
    revenue = 0.0
    energy_cost = 0.0
    deviation_cost = 0.0
    opex_cost = 0.0
    segment_rows = []
    for segment in segments:
        name = segment["name"]
        f_value = data["forecast"][name][idx]
        a_value = data["actual"][name][idx]
        price_fixed = float(segment["retail_price_cny_per_mwh"])
        price = (1.0 - linkage_share) * price_fixed + linkage_share * price_link
        contract_qty = coverage * f_value
        cost = contract_qty * contract_price + (a_value - contract_qty) * spot
        dev = deviation.deviation_cost(a_value, f_value, tolerance, penalty)
        opex = a_value * float(segment["opex_cny_per_mwh"])
        revenue += a_value * price
        energy_cost += cost
        deviation_cost += dev
        opex_cost += opex
        energy_forecast += f_value
        energy_actual += a_value
        effective_cost = cost / a_value if a_value > 0 else 0.0
        dev_per_mwh = dev / a_value if a_value > 0 else 0.0
        segment_rows.append(
            {
                "segment": name,
                "share": float(segment["share"]),
                "energy_forecast_mwh": f_value,
                "energy_actual_mwh": a_value,
                "retail_price_cny_per_mwh": price_fixed,
                "blended_price_cny_per_mwh": price,
                "contract_qty_mwh": contract_qty,
                "energy_cost_cny": cost,
                "effective_cost_cny_per_mwh": effective_cost,
                "deviation_cost_cny": dev,
                "deviation_cost_cny_per_mwh": dev_per_mwh,
                "opex_cny": opex,
            }
        )

    guarantee_cost = _monthly_guarantee(config)
    fixed_cost = float(portfolio_cfg["fixed_cost_cny_per_day"]) * _days_in_month(month)
    net = revenue - energy_cost - deviation_cost - opex_cost - guarantee_cost - fixed_cost

    # 归因分摊：担保资金成本与固定成本按实际电量占比摊到客户群，保证 Σ 客户群净额 = 组合净额。
    alloc_total = guarantee_cost + fixed_cost
    for row in segment_rows:
        weight = row["energy_actual_mwh"] / energy_actual if energy_actual > 0 else 0.0
        allocated = alloc_total * weight
        row["allocated_guarantee_fixed_cny"] = allocated
        row["net_cny"] = row["energy_actual_mwh"] * row["blended_price_cny_per_mwh"] - row["energy_cost_cny"] - row["deviation_cost_cny"] - row["opex_cny"] - allocated
        row["per_mwh_net_cny"] = row["net_cny"] / row["energy_actual_mwh"] if row["energy_actual_mwh"] > 0 else 0.0

    identity_residual = sum(row["net_cny"] for row in segment_rows) - net
    blended_price = revenue / energy_actual if energy_actual > 0 else 0.0
    return {
        "month": month,
        "spot_cny_per_mwh": spot,
        "wholesale_cost_cny_per_mwh": wholesale,
        "linkage_share": linkage_share,
        "linked_price_cny_per_mwh": price_link,
        "energy_forecast_mwh": energy_forecast,
        "energy_actual_mwh": energy_actual,
        "revenue_cny": revenue,
        "energy_cost_cny": energy_cost,
        "deviation_cost_cny": deviation_cost,
        "opex_cny": opex_cost,
        "guarantee_cost_cny": guarantee_cost,
        "fixed_cost_cny": fixed_cost,
        "net_cny": net,
        "per_mwh_cny": net / energy_actual if energy_actual > 0 else 0.0,
        "blended_retail_price_cny_per_mwh": blended_price,
        "segments": segment_rows,
        "identity_residual_cny": identity_residual,
    }


def replay(config, data, spot_path, linkage_shares):
    months_out = []
    for idx, spot in enumerate(spot_path):
        months_out.append(replay_month(config, data, idx, spot, linkage_shares[idx]))
    annual_net = sum(m["net_cny"] for m in months_out)
    annual_energy = sum(m["energy_actual_mwh"] for m in months_out)
    inversion = [m["month"] for m in months_out if m["per_mwh_cny"] < 0]
    deepest = min(months_out, key=lambda m: m["per_mwh_cny"])
    residual = sum(abs(m["identity_residual_cny"]) for m in months_out)
    return {
        "monthly": months_out,
        "annual_net_cny": annual_net,
        "annual_energy_mwh": annual_energy,
        "per_mwh_cny": annual_net / annual_energy if annual_energy > 0 else 0.0,
        "inversion_months": inversion,
        "deepest_month": deepest["month"],
        "deepest_per_mwh_cny": deepest["per_mwh_cny"],
        "identity_residual_cny": residual,
        "revenue_cny": sum(m["revenue_cny"] for m in months_out),
        "energy_cost_cny": sum(m["energy_cost_cny"] for m in months_out),
        "deviation_cost_cny": sum(m["deviation_cost_cny"] for m in months_out),
        "opex_cny": sum(m["opex_cny"] for m in months_out),
        "guarantee_cost_cny": sum(m["guarantee_cost_cny"] for m in months_out),
        "fixed_cost_cny": sum(m["fixed_cost_cny"] for m in months_out),
    }


def stop_loss_replay(config, data, spot_path, line=None, target=None):
    """止损盘：止损线或联动触发价首次触发后，滞后 action_lag_months 个月将联动比例切到目标值。"""
    strategy = config["strategy"]
    stop_loss = strategy["stop_loss"]
    line = float(stop_loss["margin_line_cny_per_mwh"]) if line is None else float(line)
    target = float(strategy["linkage"]["target_share"]) if target is None else float(target)
    baseline = float(strategy["baseline_linkage_share"])
    trigger_price = float(stop_loss["linkage_trigger_price_cny_per_mwh"])
    lag = int(stop_loss["action_lag_months"])
    count = len(spot_path)

    shares = [baseline] * count
    probe = replay(config, data, spot_path, shares)
    trigger_idx = None
    trigger_type = None
    for idx, row in enumerate(probe["monthly"]):
        margin_hit = row["per_mwh_cny"] < line - 1e-12
        price_hit = row["wholesale_cost_cny_per_mwh"] > trigger_price + 1e-12
        if margin_hit or price_hit:
            trigger_idx = idx
            trigger_type = "both" if margin_hit and price_hit else ("margin_line" if margin_hit else "linkage_trigger_price")
            break

    action_idx = None
    if trigger_idx is not None:
        action_idx = trigger_idx + lag
        if action_idx < count:
            for idx in range(action_idx, count):
                shares[idx] = target

    result = replay(config, data, spot_path, shares)
    result.update(
        {
            "trigger_month": data["months"][trigger_idx] if trigger_idx is not None else None,
            "trigger_type": trigger_type,
            "action_month": data["months"][action_idx] if action_idx is not None and action_idx < count else None,
            "action_effective": action_idx is not None and action_idx < count,
            "linkage_shares": shares,
            "stop_line_cny_per_mwh": line,
            "target_linkage_share": target,
        }
    )
    return result


def build_tracks(config, data):
    strategy = config["strategy"]
    baseline = float(strategy["baseline_linkage_share"])
    target = float(strategy["linkage"]["target_share"])
    count = len(data["months"])
    realized = data["realized"]
    track_a = replay(config, data, realized, [baseline] * count)
    track_b = replay(config, data, realized, [target] * count)
    track_c = stop_loss_replay(config, data, realized)
    return {"A": track_a, "B": track_b, "C": track_c}


def build_scenarios(config, data):
    strategy = config["strategy"]
    baseline = float(strategy["baseline_linkage_share"])
    target = float(strategy["linkage"]["target_share"])
    count = len(data["months"])
    rows = []
    for field, label, weight in zip(data["scenario_fields"], data["scenario_labels"], data["weights"]):
        path = data["scenarios"][field]
        track_a = replay(config, data, path, [baseline] * count)
        track_b = replay(config, data, path, [target] * count)
        track_c = stop_loss_replay(config, data, path)
        rows.append(
            {
                "scenario": field,
                "label": label,
                "weight": float(weight),
                "avg_spot_cny_per_mwh": sum(path) / len(path),
                "net_track_a_cny": track_a["annual_net_cny"],
                "per_mwh_track_a_cny": track_a["per_mwh_cny"],
                "net_track_b_cny": track_b["annual_net_cny"],
                "per_mwh_track_b_cny": track_b["per_mwh_cny"],
                "net_track_c_cny": track_c["annual_net_cny"],
                "per_mwh_track_c_cny": track_c["per_mwh_cny"],
                "trigger_month_c": track_c["trigger_month"],
                "inversion_months_a": len(track_a["inversion_months"]),
            }
        )
    expected_a = sum(row["weight"] * row["net_track_a_cny"] for row in rows)
    expected_b = sum(row["weight"] * row["net_track_b_cny"] for row in rows)
    expected_c = sum(row["weight"] * row["net_track_c_cny"] for row in rows)
    return {
        "rows": rows,
        "expected_net_track_a_cny": expected_a,
        "expected_net_track_b_cny": expected_b,
        "expected_net_track_c_cny": expected_c,
    }


def build_attribution(config, track_a):
    """倒挂归因：Track A 的（客户群 × 月份）净贡献，负值即倒挂亏损点。"""
    points = []
    for month_row in track_a["monthly"]:
        for seg in month_row["segments"]:
            points.append(
                {
                    "month": month_row["month"],
                    "segment": seg["segment"],
                    "energy_actual_mwh": seg["energy_actual_mwh"],
                    "retail_price_cny_per_mwh": seg["retail_price_cny_per_mwh"],
                    "effective_cost_cny_per_mwh": seg["effective_cost_cny_per_mwh"],
                    "deviation_cost_cny": seg["deviation_cost_cny"],
                    "opex_cny": seg["opex_cny"],
                    "allocated_guarantee_fixed_cny": seg["allocated_guarantee_fixed_cny"],
                    "net_cny": seg["net_cny"],
                    "per_mwh_net_cny": seg["per_mwh_net_cny"],
                    "inversion": seg["per_mwh_net_cny"] < 0,
                }
            )
    points.sort(key=lambda row: row["net_cny"])
    return {"points": points}


def build_segment_summary(config, track_a):
    """按客户群汇总 Track A 年度贡献（用于'哪个客户群在补贴谁'的归因）。"""
    summary = {}
    for month_row in track_a["monthly"]:
        for seg in month_row["segments"]:
            row = summary.setdefault(
                seg["segment"],
                {"segment": seg["segment"], "share": seg["share"], "energy_mwh": 0.0, "net_cny": 0.0, "deviation_cost_cny": 0.0},
            )
            row["energy_mwh"] += seg["energy_actual_mwh"]
            row["net_cny"] += seg["net_cny"]
            row["deviation_cost_cny"] += seg["deviation_cost_cny"]
    rows = sorted(summary.values(), key=lambda item: item["net_cny"])
    for row in rows:
        row["per_mwh_cny"] = row["net_cny"] / row["energy_mwh"] if row["energy_mwh"] > 0 else 0.0
    return rows


def build_scan(config, data):
    """止损边界扫描：批发成本涨幅 × 套餐联动比例 × 止损线 的三维网格。"""
    scan_cfg = config["policy"]["scan"]
    spot_cfg = config["rules"]["spot"]
    floor = float(spot_cfg["clear_floor_cny_per_mwh"])
    cap = float(spot_cfg["clear_cap_cny_per_mwh"])
    coverage, contract_price = _contract_terms(config)
    realized = data["realized"]

    rows = []
    for uplift in scan_cfg["spot_uplift_steps"]:
        g = float(uplift)
        path = [min(max(s * (1.0 + g), floor), cap) for s in realized]
        avg_spot = sum(path) / len(path)
        avg_wholesale = _wholesale_cost(coverage, contract_price, avg_spot)
        for line in scan_cfg["stop_loss_line_steps"]:
            stop_line = float(line)
            for share in scan_cfg["linkage_share_steps"]:
                lam = float(share)
                result = stop_loss_replay(config, data, path, line=stop_line, target=lam)
                rows.append(
                    {
                        "spot_uplift": g,
                        "avg_spot_cny_per_mwh": avg_spot,
                        "avg_wholesale_cny_per_mwh": avg_wholesale,
                        "linkage_share": lam,
                        "stop_line_cny_per_mwh": stop_line,
                        "trigger_month": result["trigger_month"],
                        "trigger_type": result["trigger_type"],
                        "action_month": result["action_month"],
                        "action_effective": result["action_effective"],
                        "inversion_months": len(result["inversion_months"]),
                        "annual_net_cny": result["annual_net_cny"],
                        "per_mwh_cny": result["per_mwh_cny"],
                        "safe": result["annual_net_cny"] >= 0.0,
                    }
                )

    frontier = []
    groups = {}
    for row in rows:
        groups.setdefault((row["spot_uplift"], row["stop_line_cny_per_mwh"]), []).append(row)
    for (uplift, line), items in sorted(groups.items()):
        safe_items = [item for item in items if item["safe"]]
        if safe_items:
            best = min(safe_items, key=lambda item: (item["linkage_share"], str(item["action_month"])))
            frontier.append(
                {
                    "spot_uplift": uplift,
                    "stop_line_cny_per_mwh": line,
                    "min_safe_linkage_share": best["linkage_share"],
                    "action_month": best["action_month"],
                    "annual_net_cny": best["annual_net_cny"],
                    "per_mwh_cny": best["per_mwh_cny"],
                }
            )
        else:
            frontier.append(
                {
                    "spot_uplift": uplift,
                    "stop_line_cny_per_mwh": line,
                    "min_safe_linkage_share": None,
                    "action_month": None,
                    "annual_net_cny": None,
                    "per_mwh_cny": None,
                }
            )

    safe_by_uplift = {}
    for row in rows:
        if row["safe"]:
            current = safe_by_uplift.get(row["spot_uplift"])
            if current is None or row["linkage_share"] < current["linkage_share"]:
                safe_by_uplift[row["spot_uplift"]] = row
    max_safe_uplift = max(safe_by_uplift) if safe_by_uplift else None
    best_overall = (
        min(safe_by_uplift.values(), key=lambda item: (item["linkage_share"], item["spot_uplift"], -item["annual_net_cny"]))
        if safe_by_uplift
        else None
    )

    alpha = float(config["strategy"]["linkage"]["pass_through"])
    # 不亏边界＝第一个“所有止损线下都没有不亏组合”的涨幅。
    fully_empty = [item["spot_uplift"] for item in frontier if item["min_safe_linkage_share"] is None]
    all_empty_by_uplift = {}
    for item in frontier:
        all_empty_by_uplift.setdefault(item["spot_uplift"], []).append(item["min_safe_linkage_share"] is None)
    boundary_uplift = min((g for g, flags in all_empty_by_uplift.items() if all(flags)), default=None)
    if max_safe_uplift is None:
        conclusion = (
            f"在传导系数 α={alpha:.2f}、中长期覆盖 {_pct(coverage)} 的结构下，扫描范围内（涨幅 ≤{max(float(u) for u in scan_cfg['spot_uplift_steps']):.0%}）"
            "没有任何（联动比例, 止损线）组合能让年度不亏：止损只能减损，不能创造安全垫，必须提高传导系数或覆盖比例。"
        )
    else:
        if boundary_uplift is None:
            boundary_text = f"扫描上限 {max(float(u) for u in scan_cfg['spot_uplift_steps']):.0%} 内均有不亏组合"
        elif boundary_uplift == 0:
            boundary_text = "仅在不叠加涨幅（g=0）时存在不亏组合"
        else:
            boundary_text = f"批发成本较已实现路径再涨约 {boundary_uplift:.0%} 后，无任何不亏组合"
        conclusion = (
            f"{boundary_text}；存在不亏组合的最大涨幅为 {max_safe_uplift:.0%}，其中最省联动的不亏组合为止损线 "
            f"{_num(best_overall['stop_line_cny_per_mwh'])} CNY/MWh + 联动比例 {best_overall['linkage_share']:.0%}"
            f"（{best_overall['action_month'] or '次年'}起生效，年度净 {best_overall['annual_net_cny']:,.0f} CNY）；"
            "涨幅更高时，止损联动只能减损、不能创造安全垫，需提高传导系数（α→1）、提高中长期覆盖或停止新增固定价电量。"
        )
    return {
        "rows": rows,
        "frontier": frontier,
        "conclusion": conclusion,
        "max_safe_uplift": max_safe_uplift,
        "best_overall": best_overall,
        "safe_combo_count": sum(1 for row in rows if row["safe"]),
    }


def build_five_questions(config, data, tracks, scenarios, attribution, segment_summary, scan):
    """复盘五问（对齐《交易台日课与异常处置 SOP》§5.1 的五问结构，归因落到环节）。"""
    track_a = tracks["A"]
    track_b = tracks["B"]
    track_c = tracks["C"]
    strategy = config["strategy"]
    stop_loss = strategy["stop_loss"]
    baseline = float(strategy["baseline_linkage_share"])
    target = float(strategy["linkage"]["target_share"])
    top_point = attribution["points"][0] if attribution["points"] else None
    worst_segment = segment_summary[0] if segment_summary else None
    plan_row = next((row for row in scenarios["rows"] if "中性" in row["label"] or row["scenario"].endswith("s2")), scenarios["rows"][0] if scenarios["rows"] else None)
    fixed_share = 1.0 - baseline

    q1 = (
        f"申报与合同：客户组合 {fixed_share:.0%} 固定价、baseline_linkage_share={baseline:.0%}，"
        "套餐无联动条款、无止损执行——报价与合同两个环节先失守（对应案例 7 的核心错误：一口价把全部价格风险留在售电侧）。"
    )
    if top_point is not None:
        q2 = (
            f"结算与损失：Track A 年度净 {_money(track_a['annual_net_cny'])} CNY（{_num(track_a['per_mwh_cny'], 2)} CNY/MWh），"
            f"倒挂 {len(track_a['inversion_months'])} 个月、最深 {_num(track_a['deepest_per_mwh_cny'], 2)} CNY/MWh（{track_a['deepest_month']}）；"
            f"最大亏损点为 {top_point['segment']} × {top_point['month']}（{_money(top_point['net_cny'])} CNY）"
            + (f"，年度最差客户群为 {worst_segment['segment']}（{_money(worst_segment['net_cny'])} CNY）" if worst_segment else "")
            + "。"
        )
    else:
        q2 = f"结算与损失：Track A 年度净 {_money(track_a['annual_net_cny'])} CNY，无单点归因输出。"
    q3 = (
        f"触发线：止损线 {stop_loss['margin_line_cny_per_mwh']:g} CNY/MWh + 联动触发价 {stop_loss['linkage_trigger_price_cny_per_mwh']:g} CNY/MWh，"
        f"Track C 在 {track_c['trigger_month'] or '—'} 触发（{track_c['trigger_type'] or '—'}），滞后 {stop_loss['action_lag_months']} 个月、"
        f"{track_c['action_month'] or '未在本窗口内生效'}起转联动 {target:.0%}，年度净 {_money(track_c['annual_net_cny'])} CNY，"
        f"较失败盘挽回 {_money(track_c['annual_net_cny'] - track_a['annual_net_cny'])} CNY；Track B（签约即联动）年度净 {_money(track_b['annual_net_cny'])} CNY。"
    )
    deviation_share = abs(track_a["deviation_cost_cny"]) / abs(track_a["annual_net_cny"]) if track_a["annual_net_cny"] else 0.0
    q4 = (
        f"归因：价差倒挂是主因（客户群×月份归因表显示亏损集中在批发成本上行后的固定价电量），"
        f"偏差考核合计仅 {_money(track_a['deviation_cost_cny'])} CNY（约占净亏损的 {deviation_share:.1%}），"
        "但 7–9 月实际负荷超预测、超带电量按实时价补货，在尖峰月放大了有效购电成本——预测偏差是放大器，不是主因。"
    )
    q5 = (
        f"明日改动：不亏参数域——{scan['conclusion']} "
        "下年签约三件事：套餐分层联动（联动比例、参考价、下限按成本反推）、压力测试双向（价涨情景必须做）、"
        "止损三件套（警戒线+动作清单+触发权限）事先写死并演练。"
    )
    if plan_row is not None:
        q4 += (
            f" 签约假设（{plan_row['label']}）下 Track A 年度净为 {_money(plan_row['net_track_a_cny'])} CNY，"
            f"与实际相差 {_money(track_a['annual_net_cny'] - plan_row['net_track_a_cny'])} CNY——这个落差就是批零倒挂的代价。"
        )
    return [
        {"question": "1. 申报与合同：价格风险留在了谁手里？", "answer": q1},
        {"question": "2. 结算与损失：亏了多少、亏在哪？", "answer": q2},
        {"question": "3. 触发线：止损线设了吗、触发了吗、动作对吗？", "answer": q3},
        {"question": "4. 归因：差异归到哪一环？证据是什么？", "answer": q4},
        {"question": "5. 明日改动：不亏的参数域在哪、下年改什么？", "answer": q5},
    ]


# ---------------------------------------------------------------- 输出格式


def _format_cell(field, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        if abs(value) < 5e-7:
            value = 0.0
        if field in {"share", "linkage_share", "spot_uplift", "min_safe_linkage_share"}:
            return f"{value:.3f}"
        if field in {"per_mwh_cny", "per_mwh_net_cny", "per_mwh_track_a_cny", "per_mwh_track_b_cny", "per_mwh_track_c_cny", "stop_line_cny_per_mwh"}:
            return f"{value:.4f}"
        if field in {
            "effective_cost_cny_per_mwh",
            "deviation_cost_cny_per_mwh",
            "energy_forecast_mwh",
            "energy_actual_mwh",
            "contract_qty_mwh",
        }:
            return f"{value:.3f}"
        return f"{value:.2f}"
    return value


def _write_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(field, row.get(field)) for field in fields})


def _money(value):
    return "—" if value is None else f"{value:,.0f}"


def _num(value, digits=2):
    if value is None:
        return "—"
    threshold = 0.5 * 10 ** (-digits)
    if abs(value) < threshold:
        value = 0.0
    return f"{value:,.{digits}f}"


def _pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def write_review(path, config, report, data, tracks, attribution, segment_summary, scenarios, scan, five_questions):
    meta = config["meta"]
    strategy = config["strategy"]
    policy = config["policy"]
    track_a = tracks["A"]
    track_b = tracks["B"]
    track_c = tracks["C"]
    tolerance = float(config["portfolio"]["deviation_terms"]["tolerance_share"])
    penalty = float(config["portfolio"]["deviation_terms"]["penalty_cny_per_mwh"])
    linkage = strategy["linkage"]
    stop_loss = strategy["stop_loss"]
    top_points = attribution["points"][: int(policy.get("review_top_attribution", 5))]

    lines = [
        f"# 广东售电批零倒挂复盘表：{meta['instance_id']}",
        "",
        f"- 复盘窗口：{data['months'][0]} .. {data['months'][-1]}（{len(data['months'])} 个月，月度电能量口径）",
        f"- 规则版本：{meta['rule_version']}",
        f"- 数据截止：{meta['data_cutoff']}",
        f"- 风格档：`{policy['profile_id']}` / 指纹 `{report['style_fingerprint']}`",
        f"- 口径：{meta['scope']}",
        f"- 案例呼应：{meta['case_ref']}——本包是该案例的可运行量化版（失败重放 + 归因 + 止损边界扫描）。",
        "",
        "## 1. 规则来源与未核实项",
        "",
    ]
    lines += _table(
        ["规则块", "级别", "来源"],
        [[row["block"], row["grade"], row["source"]] for row in report["provenance"]],
    )
    if report["warnings"]:
        lines += ["", "警告：", ""]
        lines += [f"- {warning}" for warning in report["warnings"]]

    lines += [
        "",
        "## 2. 失败重放结论（Track A：100% 固定价、无联动、无止损）",
        "",
        f"- 实际电量：{_num(track_a['annual_energy_mwh'], 1)} MWh；实际零售收入：{_money(track_a['revenue_cny'])} CNY。",
        f"- Track A 年度净：**{_money(track_a['annual_net_cny'])} CNY**（{_num(track_a['per_mwh_cny'], 2)} CNY/MWh），"
        f"倒挂 {len(track_a['inversion_months'])} 个月，最深 {track_a['deepest_month']}（{_num(track_a['deepest_per_mwh_cny'], 2)} CNY/MWh）。",
        f"- Track B（签约即联动 {_pct(float(linkage['target_share']))}）年度净：{_money(track_b['annual_net_cny'])} CNY（{_num(track_b['per_mwh_cny'], 2)} CNY/MWh）。",
        f"- Track C（止损线 {stop_loss['margin_line_cny_per_mwh']:g} + 联动触发价 {stop_loss['linkage_trigger_price_cny_per_mwh']:g}，"
        f"{track_c['trigger_month'] or '—'} 触发、{track_c['action_month'] or '未生效'}起转联动 {_pct(float(linkage['target_share']))}）年度净：{_money(track_c['annual_net_cny'])} CNY，"
        f"较 Track A 挽回 {_money(track_c['annual_net_cny'] - track_a['annual_net_cny'])} CNY。",
        f"- 行业背景：广东 2026H1 售电公司平均度电收益约 0.0039 元/kWh、500 家样本中 298 家亏损（B/C）——本包失败盘的度电结果应对照这个量级读。",
        "",
        "三条轨道都是**对照情景**：Track A 量化倒挂损失，Track B/C 回答'当年如果有联动/止损会怎样'，不是历史事实。",
        "",
        "## 3. 月度损益重放",
        "",
    ]
    monthly_rows = []
    for idx, row in enumerate(track_a["monthly"]):
        monthly_rows.append(
            [
                row["month"],
                _num(row["energy_actual_mwh"], 1),
                _num(row["spot_cny_per_mwh"], 1),
                _num(row["wholesale_cost_cny_per_mwh"], 2),
                _num(row["blended_retail_price_cny_per_mwh"], 2),
                _num(row["per_mwh_cny"], 2),
                _money(row["net_cny"]),
                _num(track_b["monthly"][idx]["per_mwh_cny"], 2),
                _money(track_b["monthly"][idx]["net_cny"]),
                _pct(track_c["monthly"][idx]["linkage_share"]),
                _num(track_c["monthly"][idx]["per_mwh_cny"], 2),
                _money(track_c["monthly"][idx]["net_cny"]),
            ]
        )
    lines += _table(
        ["月份", "实际电量 MWh", "现货均价", "加权采购成本 W", "加权零售价(A)", "A 度电净", "A 净额", "B 度电净", "B 净额", "C 联动比例", "C 度电净", "C 净额"],
        monthly_rows,
    )
    lines += [
        "",
        f"成本口径：W = 覆盖 {_pct(_contract_terms(config)[0])} × 合约价 + 现货敞口 × 当月现货价；"
        f"偏差考核按合同（免考带 {_pct(tolerance)}、考核价 {_num(penalty, 0)} CNY/MWh，D 级假设），"
        "超带电量按实时价口径补货已含在 W 的实际电量结算里。",
        "",
        "## 4. 倒挂归因表（Track A：客户群 × 月份）",
        "",
        "归因口径：担保资金成本与固定成本按实际电量占比摊入；净额为负即倒挂亏损点。全部 36 行见 `inversion_attribution.csv`。",
        "",
    ]
    attribution_rows = []
    for point in top_points:
        attribution_rows.append(
            [
                point["month"],
                point["segment"],
                _num(point["energy_actual_mwh"], 1),
                _num(point["retail_price_cny_per_mwh"], 2),
                _num(point["effective_cost_cny_per_mwh"], 2),
                _num(point["per_mwh_net_cny"], 2),
                _money(point["net_cny"]),
            ]
        )
    lines += _table(
        ["月份", "客户群", "实际电量 MWh", "固定零售价", "有效购电成本", "度电净额", "净额 CNY"],
        attribution_rows,
    )
    lines += [
        "",
        "按客户群汇总（年度）：",
        "",
    ]
    seg_rows = [
        [
            row["segment"],
            _pct(row["share"]),
            _num(row["energy_mwh"], 1),
            _num(row["per_mwh_cny"], 2),
            _money(row["net_cny"]),
        ]
        for row in segment_summary
    ]
    lines += _table(["客户群", "电量份额", "实际电量 MWh", "度电净额", "年度净额 CNY"], seg_rows)
    lines += [
        "",
        "## 5. 止损边界扫描（批发成本涨幅 × 套餐联动比例 × 止损线）",
        "",
        f"扫描口径：在已实现现货路径上叠加涨幅 g（现货分量 ×(1+g)，截断在 −50–1,800 元/MWh 内），"
        f"对每（g, 止损线 L, 联动比例 λ）重放 12 个月止损盘（触发次月起转联动 λ，传导系数 α={float(linkage['pass_through']):.2f}、"
        f"加价 {_num(float(linkage['adder_cny_per_mwh']), 0)}、下限 {_num(float(linkage['floor_cny_per_mwh']), 0)}、上限 {_num(float(linkage['cap_cny_per_mwh']), 0)}）；"
        f"不亏判据：年度净 ≥ 0。全部 {_len_or(scan['rows'])} 行见 `stop_loss_scan.csv`，frontier 见 `scan_frontier.csv`。",
        "",
    ]
    frontier_rows = []
    for item in scan["frontier"]:
        frontier_rows.append(
            [
                f"{item['spot_uplift']:.0%}",
                _num(item["stop_line_cny_per_mwh"], 0),
                "—" if item["min_safe_linkage_share"] is None else f"{item['min_safe_linkage_share']:.0%}",
                item["action_month"] or "—",
                _money(item["annual_net_cny"]),
            ]
        )
    lines += _table(
        ["批发成本涨幅 g", "止损线 L（CNY/MWh）", "最小不亏联动比例 λ", "动作生效月", "该组合年度净 CNY"],
        frontier_rows,
    )
    lines += [
        "",
        f"**扫描结论**：{scan['conclusion']}",
        "",
        f"扫描网格 {_len_or(scan['rows'])} 组中不亏组合 {scan['safe_combo_count']} 组。"
        + ("" if scan["max_safe_uplift"] is None else f" 可承受的最大涨幅为 {scan['max_safe_uplift']:.0%}。"),
        "",
        "## 6. 情景对照（含当年没测的上行方向）",
        "",
    ]
    scenario_rows = [
        [
            row["label"],
            _pct(row["weight"]),
            _num(row["avg_spot_cny_per_mwh"], 1),
            _money(row["net_track_a_cny"]),
            _money(row["net_track_b_cny"]),
            _money(row["net_track_c_cny"]),
            row["trigger_month_c"] or "—",
        ]
        for row in scenarios["rows"]
    ]
    lines += _table(
        ["情景", "权重", "现货均价", "A 净额（失败盘）", "B 净额（签约即联动）", "C 净额（止损盘）", "C 触发月"],
        scenario_rows,
    )
    lines += [
        "",
        f"加权期望净额：A {_money(scenarios['expected_net_track_a_cny'])}、B {_money(scenarios['expected_net_track_b_cny'])}、"
        f"C {_money(scenarios['expected_net_track_c_cny'])} CNY。s1（下行）是当年压力测试只测的方向；s3/s4（上行/尖峰上行）是没测的方向——"
        "只测价跌的压测等于没有压测（案例 7 错误做法）。",
        "",
        "## 7. 复盘五问摘要",
        "",
    ]
    for item in five_questions:
        lines += [f"**{item['question']}**", "", item["answer"], ""]
    lines += [
        "## 8. 读法与边界",
        "",
        "- 本包是**失败复盘器**，不是定价器：止损边界扫描给出的是'这套成本结构下参数域是否不亏'，不是报价建议。",
        "- 广东零售是薄利生意：2026H1 度电收益约 0.0039 元/kWh、500 家样本中 298 家亏损（B/C）——几个百分点的批发涨幅就能吞掉全年利润，安全垫必须事前留。",
        "- 联动不是开关，是剂量：传导系数 α<1 时仍有 (1−α)×W 的敞口留在售电侧；联动下限要按成本反推，不能按市场价定。",
        "- 止损只能减损：涨幅超出联动+覆盖能兜住的范围时，靠的是停止新增固定价电量、提高传导系数或提高覆盖，而不是更晚的止损线。",
        "- 偏差考核按合同字段测算（D 级假设）；广东现行统一考核规则未核实（C 级线索），不得把 ±3%/±5% 当作省规则。",
        "- 偏差电量按实时价口径结算（广东 §3，B）；尖峰月实际负荷超预测会同时触发考核与高价补货，放大倒挂。",
        "- 本包只覆盖电能量口径；输配电价、政府性基金、基本电费、绿电溢价、坏账、用户流失、解约争议成本与税费均未计入。",
        "- 所有客户、价格、电量与价格路径均为 D 级合成，不对应任何真实售电公司、用户或交易结果。",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _len_or(rows):
    return f"{len(rows):,}" if rows else "0"


# ---------------------------------------------------------------- 主流程


def run_instance(instance_path, monthly_path, out_dir, demo=False):
    instance_path = Path(instance_path)
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    report = validate_instance(config)
    data = read_monthly(monthly_path, config, report)

    tracks = build_tracks(config, data)
    scenarios = build_scenarios(config, data)
    attribution = build_attribution(config, tracks["A"])
    segment_summary = build_segment_summary(config, tracks["A"])
    scan = build_scan(config, data)
    five_questions = build_five_questions(config, data, tracks, scenarios, attribution, segment_summary, scan)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    monthly_fields = [
        "month",
        "energy_forecast_mwh",
        "energy_actual_mwh",
        "spot_cny_per_mwh",
        "wholesale_cost_cny_per_mwh",
        "blended_retail_price_cny_per_mwh",
        "net_track_a_cny",
        "per_mwh_track_a_cny",
        "net_track_b_cny",
        "per_mwh_track_b_cny",
        "net_track_c_cny",
        "per_mwh_track_c_cny",
        "linkage_share_track_c",
        "trigger_flag",
    ]
    monthly_rows = []
    for idx, row in enumerate(tracks["A"]["monthly"]):
        track_c_row = tracks["C"]["monthly"][idx]
        monthly_rows.append(
            {
                "month": row["month"],
                "energy_forecast_mwh": row["energy_forecast_mwh"],
                "energy_actual_mwh": row["energy_actual_mwh"],
                "spot_cny_per_mwh": row["spot_cny_per_mwh"],
                "wholesale_cost_cny_per_mwh": row["wholesale_cost_cny_per_mwh"],
                "blended_retail_price_cny_per_mwh": row["blended_retail_price_cny_per_mwh"],
                "net_track_a_cny": row["net_cny"],
                "per_mwh_track_a_cny": row["per_mwh_cny"],
                "net_track_b_cny": tracks["B"]["monthly"][idx]["net_cny"],
                "per_mwh_track_b_cny": tracks["B"]["monthly"][idx]["per_mwh_cny"],
                "net_track_c_cny": track_c_row["net_cny"],
                "per_mwh_track_c_cny": track_c_row["per_mwh_cny"],
                "linkage_share_track_c": track_c_row["linkage_share"],
                "trigger_flag": 1 if row["month"] == tracks["C"]["trigger_month"] else 0,
            }
        )
    _write_csv(out_dir / "monthly_pnl.csv", monthly_rows, monthly_fields)

    attribution_fields = [
        "month",
        "segment",
        "energy_actual_mwh",
        "retail_price_cny_per_mwh",
        "effective_cost_cny_per_mwh",
        "deviation_cost_cny",
        "opex_cny",
        "allocated_guarantee_fixed_cny",
        "net_cny",
        "per_mwh_net_cny",
        "inversion",
    ]
    _write_csv(out_dir / "inversion_attribution.csv", attribution["points"], attribution_fields)
    _write_csv(
        out_dir / "top_inversion.csv",
        attribution["points"][: int(config["policy"].get("review_top_attribution", 5))],
        attribution_fields,
    )

    scan_fields = [
        "spot_uplift",
        "avg_spot_cny_per_mwh",
        "avg_wholesale_cny_per_mwh",
        "linkage_share",
        "stop_line_cny_per_mwh",
        "trigger_month",
        "trigger_type",
        "action_month",
        "action_effective",
        "inversion_months",
        "annual_net_cny",
        "per_mwh_cny",
        "safe",
    ]
    _write_csv(out_dir / "stop_loss_scan.csv", scan["rows"], scan_fields)

    frontier_fields = [
        "spot_uplift",
        "stop_line_cny_per_mwh",
        "min_safe_linkage_share",
        "action_month",
        "annual_net_cny",
        "per_mwh_cny",
    ]
    _write_csv(out_dir / "scan_frontier.csv", scan["frontier"], frontier_fields)

    scenario_fields = [
        "scenario",
        "label",
        "weight",
        "avg_spot_cny_per_mwh",
        "net_track_a_cny",
        "per_mwh_track_a_cny",
        "net_track_b_cny",
        "per_mwh_track_b_cny",
        "net_track_c_cny",
        "per_mwh_track_c_cny",
        "trigger_month_c",
        "inversion_months_a",
    ]
    _write_csv(out_dir / "scenario_table.csv", scenarios["rows"], scenario_fields)

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "package_kind": config["meta"].get("package_kind"),
        "case_ref": config["meta"].get("case_ref"),
        "replay_window": {"start": data["months"][0], "end": data["months"][-1], "months": len(data["months"])},
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "policy": config["policy"],
        "policy_fingerprint": report["style_fingerprint"],
        "provenance": report["provenance"],
        "warnings": report["warnings"],
        "identity_residual_cny": tracks["A"]["identity_residual_cny"],
        "tracks": {
            "A_failure": {
                "annual_net_cny": tracks["A"]["annual_net_cny"],
                "per_mwh_cny": tracks["A"]["per_mwh_cny"],
                "inversion_months": tracks["A"]["inversion_months"],
                "deepest_month": tracks["A"]["deepest_month"],
                "deepest_per_mwh_cny": tracks["A"]["deepest_per_mwh_cny"],
                "costs_cny": {
                    "revenue": tracks["A"]["revenue_cny"],
                    "energy": tracks["A"]["energy_cost_cny"],
                    "deviation": tracks["A"]["deviation_cost_cny"],
                    "opex": tracks["A"]["opex_cny"],
                    "guarantee": tracks["A"]["guarantee_cost_cny"],
                    "fixed": tracks["A"]["fixed_cost_cny"],
                },
            },
            "B_linkage": {
                "annual_net_cny": tracks["B"]["annual_net_cny"],
                "per_mwh_cny": tracks["B"]["per_mwh_cny"],
                "inversion_months": tracks["B"]["inversion_months"],
            },
            "C_stop_loss": {
                "annual_net_cny": tracks["C"]["annual_net_cny"],
                "per_mwh_cny": tracks["C"]["per_mwh_cny"],
                "trigger_month": tracks["C"]["trigger_month"],
                "trigger_type": tracks["C"]["trigger_type"],
                "action_month": tracks["C"]["action_month"],
                "action_effective": tracks["C"]["action_effective"],
                "inversion_months": tracks["C"]["inversion_months"],
                "saved_vs_a_cny": tracks["C"]["annual_net_cny"] - tracks["A"]["annual_net_cny"],
            },
        },
        "segment_summary": segment_summary,
        "top_inversion_points": attribution["points"][: int(config["policy"].get("review_top_attribution", 5))],
        "scenarios": scenarios,
        "scan": {
            "combo_count": len(scan["rows"]),
            "safe_combo_count": scan["safe_combo_count"],
            "max_safe_uplift": scan["max_safe_uplift"],
            "conclusion": scan["conclusion"],
            "frontier": scan["frontier"],
        },
        "five_questions": five_questions,
        "files": {
            "monthly_pnl": "monthly_pnl.csv",
            "inversion_attribution": "inversion_attribution.csv",
            "top_inversion": "top_inversion.csv",
            "stop_loss_scan": "stop_loss_scan.csv",
            "scan_frontier": "scan_frontier.csv",
            "scenario_table": "scenario_table.csv",
            "review": "review.md",
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_review(
        out_dir / "review.md",
        config,
        report,
        data,
        tracks,
        attribution,
        segment_summary,
        scenarios,
        scan,
        five_questions,
    )

    return {
        "config": config,
        "report": report,
        "data": data,
        "tracks": tracks,
        "scenarios": scenarios,
        "attribution": attribution,
        "segment_summary": segment_summary,
        "scan": scan,
        "five_questions": five_questions,
        "summary": summary,
        "out_dir": out_dir,
        "demo": demo,
    }


def _print_summary(result):
    config = result["config"]
    summary = result["summary"]
    tracks = summary["tracks"]
    scan = summary["scan"]
    data = result["data"]
    print(f"实例：{config['meta']['instance_id']} / 复盘窗口 {data['months'][0]} .. {data['months'][-1]}")
    a = tracks["A_failure"]
    b = tracks["B_linkage"]
    c = tracks["C_stop_loss"]
    print(
        f"轨道A 失败盘：年度净 {a['annual_net_cny']:,.0f} CNY（{a['per_mwh_cny']:,.2f} CNY/MWh），"
        f"倒挂 {len(a['inversion_months'])} 个月，最深 {a['deepest_month']} {a['deepest_per_mwh_cny']:,.2f} CNY/MWh"
    )
    print(
        f"轨道B 对照盘（签约即联动）：年度净 {b['annual_net_cny']:,.0f} CNY（{b['per_mwh_cny']:,.2f} CNY/MWh）"
    )
    print(
        f"轨道C 止损盘：{c['trigger_month'] or '—'} 触发（{c['trigger_type'] or '—'}）→ {c['action_month'] or '未生效'}起转联动，"
        f"年度净 {c['annual_net_cny']:,.0f} CNY，挽回 {c['saved_vs_a_cny']:,.0f} CNY"
    )
    top = summary["top_inversion_points"][0] if summary["top_inversion_points"] else None
    if top is not None:
        print(f"倒挂归因：最大亏损点 {top['segment']} × {top['month']}（{top['net_cny']:,.0f} CNY）")
    print(
        f"止损边界扫描：{scan['combo_count']} 组网格，不亏 {scan['safe_combo_count']} 组；"
        + ("无可行组合" if scan["max_safe_uplift"] is None else f"最大可承受涨幅 {scan['max_safe_uplift']:.0%}")
    )
    print(f"结论：{scan['conclusion']}")
    print(f"差异桥残差（归因恒等式）：{summary['identity_residual_cny']:.2e} CNY")
    print(f"产物：{result['out_dir']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="广东售电批零倒挂实例包：失败重放 → 倒挂归因 → 止损边界扫描")
    parser.add_argument("--instance", default=str(HERE / "instance.json"), help="实例配置路径")
    parser.add_argument("--check-config", action="store_true", help="只校验配置并打印来源表")
    parser.add_argument("--demo", action="store_true", help="用实例自带 D 级演示数据跑全流程")
    parser.add_argument("--monthly", help="月度复盘输入 CSV")
    parser.add_argument("--out", help="输出目录")
    args = parser.parse_args(argv)

    instance_path = Path(args.instance)
    try:
        config = json.loads(instance_path.read_text(encoding="utf-8"))
        report = validate_instance(config)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取配置失败：{exc}", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.check_config:
        print(f"实例：{config['meta']['instance_id']}")
        print(f"定位：{config['meta'].get('package_kind', '—')}（{config['meta'].get('case_ref', '—')}）")
        print(f"口径：{config['meta']['scope']}")
        print(f"风格指纹：{report['style_fingerprint']}")
        print("规则来源：")
        for row in report["provenance"]:
            print(f"- {row['block']}: {row['grade']} / {row['source']}")
        if report["warnings"]:
            print("警告：")
            for warning in report["warnings"]:
                print(f"- {warning}")
        print("配置校验通过。")
        return 0

    if args.demo:
        monthly_path = instance_path.parent / config["data_contract"]["monthly"]["path"]
        out_dir = Path(args.out) if args.out else HERE / "out" / "demo"
        demo = True
    else:
        if not args.monthly:
            print("需要 --monthly，或使用 --demo / --check-config", file=sys.stderr)
            return 2
        monthly_path = Path(args.monthly)
        out_dir = Path(args.out) if args.out else HERE / "out" / "run"
        demo = False

    try:
        result = run_instance(instance_path, monthly_path, out_dir, demo=demo)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (InputError, OSError) as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 2
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
