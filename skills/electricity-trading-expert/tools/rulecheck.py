"""省级规则包 · 申报前校验（零依赖，仅 Python 标准库）。

从仓库根目录运行：

    python skills/electricity-trading-expert/tools/rulecheck.py --demo
    python skills/electricity-trading-expert/tools/rulecheck.py \
        --instance skills/spot-bidding-quant/instances/shandong-thermal-2026-11

本工具只读：读取 `rules/<省>.json`、实例 `instance.json`、最近一次
`out/**/summary.json` 和可选申报 CSV，输出 `rulecheck.md` 与
`rulecheck.json`。它不写入实例包、不连接交易系统、不提交报价。

判定语义：

* ``block``：违反已核实的硬规则，或结构上无法申报（点数、限价、容量、
  充放电功率、申报日期等），必须修正后再报。
* ``warn``：规则为草案/未核实/模型边界，或命中软分档、近似 SOC、
  截止时点未核验等，需要交易员人工确认。
* ``pass``：已检查且未发现问题。
* ``skip``：该实例不适用此检查，例如年度包没有现货申报文件。

所有实例均为 D 级合成样板；规则包中的 B/C、C/D 和“待核实”标记
不会因为本工具通过而升级。报告不构成报价、投资或法律建议。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_DIR = REPO_ROOT / "skills" / "electricity-trading-expert" / "rules"
DEFAULT_MANIFEST = (
    REPO_ROOT / "skills" / "electricity-trading-expert" / "instances" / "portfolio-demo-2026-11.json"
)
DEFAULT_OUT = REPO_ROOT / "skills" / "electricity-trading-expert" / "out" / "rulecheck"
PROVINCE_RULE_FILES = {
    "山东": "shandong.json",
    "甘肃": "gansu.json",
    "蒙西": "mengxi.json",
    "山西": "shanxi.json",
    "广东": "guangdong.json",
    "江苏": "jiangsu.json",
}
LEVELS = ("pass", "warn", "block", "skip")
STATUS_LABELS = {"pass": "PASS", "warn": "WARN", "block": "BLOCK", "skip": "SKIP"}
SPOT_ASSETS = {"wind", "thermal", "storage", "pv_storage"}
ASSET_LABELS = {
    "wind": "风电",
    "thermal": "煤电/热电",
    "storage": "独立储能",
    "pv_storage": "光储联合",
    "retail": "售电零售",
    "direct": "绿电直连",
    "unknown": "未识别",
}
NOT_VERIFIED = ("待核实", "待核", "未核实", "未核到", "两种说法", "征求意见稿")


def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def as_float(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def relpath(path):
    try:
        return os.path.relpath(str(path), str(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else (REPO_ROOT / path)


def find_summary(pack):
    candidates = [path for path in pack.glob("out/**/summary.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def find_bid(pack, summary_path):
    if summary_path and summary_path.is_file():
        try:
            summary = load_json(summary_path)
        except (OSError, json.JSONDecodeError):
            summary = {}
        name = (summary.get("files") or {}).get("bid_sheet")
        if name:
            candidate = summary_path.parent / name
            if candidate.is_file():
                return candidate
        adjacent = summary_path.parent / "bid_sheet.csv"
        return adjacent if adjacent.is_file() else None
    for candidate in (pack / "out" / "demo" / "bid_sheet.csv", pack / "out" / "bid_sheet.csv"):
        if candidate.is_file():
            return candidate
    return None


def read_csv(path):
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with Path(path).open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                return list(reader), list(reader.fieldnames or [])
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法解码 {path}")


def classify_asset(instance):
    meta = instance.get("meta") or {}
    asset = instance.get("asset") or {}
    text = " ".join(
        str(item)
        for item in (
            meta.get("entity_type"),
            meta.get("market"),
            meta.get("scope"),
            instance.get("project", {}).get("name") if isinstance(instance.get("project"), dict) else "",
        )
        if item
    )
    if "绿电直连" in text:
        return "direct"
    if "售电" in text:
        return "retail"
    if isinstance(asset, dict) and "pv" in asset and "storage" in asset:
        return "pv_storage"
    if isinstance(asset, dict) and asset.get("type") == "wind":
        return "wind"
    if "独立新型储能" in text or ("储能" in text and "光储" not in text and "配建" not in text):
        return "storage"
    if any(word in text for word in ("燃煤", "煤电", "热电")):
        return "thermal"
    if "风电" in text or "新能源" in text:
        return "wind"
    return "unknown"


def normalize_spot(instance):
    rules = instance.get("rules") or {}
    if isinstance(rules.get("spot"), dict):
        return rules["spot"], "rules.spot"
    energy = rules.get("energy") or {}
    spot = {}
    for key, value in energy.items():
        if key.startswith("spot_"):
            spot[key[5:]] = value
    if spot:
        return spot, "rules.energy(spot_*)"
    return None, None


def asset_power(instance, asset_class):
    asset = instance.get("asset") or {}
    project = instance.get("project") or {}
    if asset_class == "pv_storage":
        return as_float((asset.get("pv") or {}).get("capacity_mw"))
    if asset_class == "storage":
        return as_float(asset.get("power_mw"))
    for key in ("power_mw", "capacity_mw", "nameplate_capacity_mw", "declared_capacity_mw"):
        value = as_float(asset.get(key))
        if value is not None:
            return value
    return as_float(project.get("capacity_mw"))


def new_report(pack, instance_id, province, asset_class):
    return {
        "instance_id": instance_id,
        "province": province,
        "path": relpath(pack),
        "asset_class": asset_class,
        "asset_label": ASSET_LABELS.get(asset_class, asset_class),
        "target_date": None,
        "target_source": None,
        "rule_file": None,
        "rule": {},
        "status": "pass",
        "counts": {level: 0 for level in LEVELS},
        "checks": [],
        "open_items": [],
    }


def add(report, check_id, level, message, detail=None):
    if level not in LEVELS:
        raise ValueError(f"unknown level {level}")
    record = {"id": check_id, "level": level, "message": message}
    if detail:
        record["detail"] = detail
    report["checks"].append(record)
    report["counts"][level] += 1


def finish(report):
    if report["counts"]["block"]:
        report["status"] = "block"
    elif report["counts"]["warn"]:
        report["status"] = "warn"
    else:
        report["status"] = "pass"
    return report


def check_period(report, block, label, target, hard, prefix):
    if not isinstance(block, dict):
        add(report, prefix, "skip", f"{label}：规则包未提供")
        return True
    effective_from = parse_date(block.get("effective_from"))
    effective_to = parse_date(block.get("effective_to"))
    if effective_from is None:
        add(report, prefix, "block" if hard else "warn", f"{label}：缺少生效日期")
        return False
    if target < effective_from:
        add(
            report,
            prefix,
            "block" if hard else "warn",
            f"{label}：{target.isoformat()} 尚未生效（生效日 {effective_from.isoformat()}）",
        )
        return False
    if effective_to is not None and target > effective_to:
        add(
            report,
            prefix,
            "block" if hard else "warn",
            f"{label}：{target.isoformat()} 已超过截止日 {effective_to.isoformat()}，规则已过期",
        )
        return False
    add(
        report,
        prefix,
        "pass",
        f"{label}：{target.isoformat()} 在有效期内（{effective_from.isoformat()} 起"
        + (f"，至 {effective_to.isoformat()}" if effective_to else "，未设截止")
        + "）",
    )
    return True


def check_rule_package(report, rule, rule_path, province, target, now, has_spot_config=True, is_spot_bidder=None):
    if is_spot_bidder is None:
        is_spot_bidder = has_spot_config
    if rule is None:
        add(report, "rule.file", "block", f"缺少 {province} 省级规则包")
        return False
    report["rule_file"] = relpath(rule_path)
    spot = rule.get("spot")
    report["rule"] = {
        "file": relpath(rule_path),
        "province": rule.get("province"),
        "market": rule.get("market"),
        "as_of": rule.get("as_of"),
        "spot_status": (spot or {}).get("status"),
        "spot_effective_from": (spot or {}).get("effective_from"),
        "spot_effective_to": (spot or {}).get("effective_to"),
        "spot_grade": (spot or {}).get("grade"),
        "capacity_status": (rule.get("capacity_compensation") or {}).get("status"),
        "retail_status": (rule.get("retail") or {}).get("status"),
        "direct_status": (rule.get("direct_connection") or {}).get("status"),
        "open_items": list(rule.get("open_items") or []),
    }
    if rule.get("schema_version") != 1:
        add(report, "rule.schema", "block", f"规则包 schema_version 不是 1：{rule.get('schema_version')}")
    else:
        add(report, "rule.schema", "pass", "规则包 schema_version=1")
    if rule.get("province") != province:
        add(
            report,
            "rule.province",
            "block",
            f"规则包省份 {rule.get('province')} 与实例 {province} 不一致",
        )
    else:
        add(report, "rule.province", "pass", f"规则包省份与实例一致：{province}")

    if not isinstance(spot, dict):
        add(report, "rule.spot", "block", "规则包缺少 spot 块")
        return False

    check_period(report, spot, "现货规则", target, hard=True, prefix="rule.spot_effective")
    if str(spot.get("status", "")).lower() in ("draft", "draft_only"):
        add(report, "rule.spot_status", "block", f"现货规则状态为草案：{spot.get('status')}")
    else:
        add(report, "rule.spot_status", "pass", f"现货规则状态：{spot.get('status')}")

    market_time_unit = as_float(spot.get("market_time_unit_min"))
    points = as_float(spot.get("points_per_day"))
    if not market_time_unit or market_time_unit <= 0:
        add(report, "rule.spot_mtu", "block", "规则包缺少有效的 market_time_unit_min")
    elif not points:
        add(report, "rule.spot_points", "block", "规则包缺少 points_per_day")
    elif abs(points - 24 * 60 / market_time_unit) > 0.5:
        add(
            report,
            "rule.spot_points",
            "block",
            f"规则包点数与 MTU 不一致：{points:g} 点 vs {market_time_unit:g} 分钟/点",
        )
    else:
        add(
            report,
            "rule.spot_points",
            "pass",
            f"现货结构：{points:g} 点/日，{market_time_unit:g} 分钟/点",
        )

    declare_floor = as_float(spot.get("declare_floor_cny_per_mwh"))
    declare_cap = as_float(spot.get("declare_cap_cny_per_mwh"))
    clear_floor = as_float(spot.get("clear_floor_cny_per_mwh"))
    clear_cap = as_float(spot.get("clear_cap_cny_per_mwh"))
    bounds = [("申报", declare_floor, declare_cap), ("出清", clear_floor, clear_cap)]
    bad = []
    for label, low, high in bounds:
        if low is not None and high is not None and low > high:
            bad.append(f"{label}下限 {low:g} > 上限 {high:g}")
    if bad:
        add(report, "rule.limits_order", "block", "；".join(bad))
    else:
        add(report, "rule.limits_order", "pass", "限价上下限顺序正常")

    enforcement = str(spot.get("limits_enforcement", "hard"))
    limits_status = spot.get("limits_status")
    if not is_spot_bidder:
        add(report, "rule.limits_status", "skip", "本实例不直接提交省内现货申报，限价执行方式不适用")
    elif enforcement == "hard":
        add(report, "rule.limits_status", "pass", "申报限价按硬规则校验")
    else:
        add(
            report,
            "rule.limits_status",
            "warn",
            f"申报限价按 {enforcement} 校验"
            + (f"（{limits_status}）" if limits_status else "")
            + "；越界只提示，不直接阻断",
        )

    verified = parse_date(spot.get("verified_on")) or parse_date(rule.get("as_of"))
    if verified is None:
        add(report, "rule.staleness", "warn", "规则包缺少 as_of/verified_on，无法判断时效")
    else:
        age = (now - verified).days
        if age < 0:
            add(report, "rule.staleness", "warn", f"规则核验日期 {verified.isoformat()} 晚于校验日 {now.isoformat()}")
        elif age > 180:
            add(report, "rule.staleness", "warn", f"规则已 {age} 天未复核（核验日 {verified.isoformat()}）")
        else:
            add(report, "rule.staleness", "pass", f"规则核验距校验日 {age} 天，未超过 180 天")

    deadline = spot.get("deadline") or {}
    if deadline.get("verified") is True:
        add(report, "rule.deadline", "pass", f"申报截止：{deadline.get('label') or deadline.get('time')}")
    elif is_spot_bidder:
        add(
            report,
            "rule.deadline",
            "warn",
            f"申报截止时点未核验：{deadline.get('label') or '未给出'}；以交易中心公告为准",
        )
    else:
        add(report, "rule.deadline", "skip", "本实例不直接申报省内现货，截止时点不适用")
    return True


def limit_level(spot, key, band=False):
    enforcement = str(spot.get("limits_enforcement", "hard"))
    if band:
        return "warn"
    if enforcement == "hard":
        return "block"
    if enforcement == "partial" and "floor" in key:
        return "block"
    return "warn"


def check_instance_limit(report, i_spot, r_spot, key, label, band=False):
    instance_value = as_float(i_spot.get(key))
    rule_value = as_float(r_spot.get(key))
    if instance_value is None:
        return
    if rule_value is None:
        add(
            report,
            f"spot.{key}",
            "warn",
            f"规则未核实{label}，实例填写 {instance_value:g}，需人工确认口径",
        )
        return
    if abs(instance_value - rule_value) <= 1e-9:
        add(report, f"spot.{key}", "pass", f"{label}一致：{instance_value:g} 元/MWh")
        return
    add(
        report,
        f"spot.{key}",
        limit_level(r_spot, key, band=band),
        f"{label}不一致：实例 {instance_value:g} vs 规则 {rule_value:g} 元/MWh",
    )


def check_spot_config(report, instance, r_spot):
    i_spot, origin = normalize_spot(instance)
    if i_spot is None:
        add(report, "spot.config", "skip", "本实例没有省内现货申报字段，跳过配置比对")
        return
    add(report, "spot.config", "pass", f"读取到现货配置：{origin}")
    points = as_float(i_spot.get("points_per_day"))
    rule_points = as_float(r_spot.get("points_per_day"))
    if points is None:
        add(report, "spot.points", "skip", "实例未声明 points_per_day")
    elif rule_points is None:
        add(report, "spot.points", "warn", f"实例申报 {points:g} 点，规则未给出点数")
    elif abs(points - rule_points) <= 0.5:
        add(report, "spot.points", "pass", f"实例点数与规则一致：{points:g} 点/日")
    else:
        add(report, "spot.points", "block", f"实例点数 {points:g} 与规则 {rule_points:g} 不一致")
    mtu = as_float(i_spot.get("market_time_unit_min"))
    rule_mtu = as_float(r_spot.get("market_time_unit_min"))
    if mtu is None:
        add(report, "spot.mtu", "skip", "实例未声明 market_time_unit_min")
    elif rule_mtu is None:
        add(report, "spot.mtu", "warn", f"实例 MTU {mtu:g} 分钟，规则未给出 MTU")
    elif abs(mtu - rule_mtu) <= 1e-9:
        add(report, "spot.mtu", "pass", f"实例 MTU 与规则一致：{mtu:g} 分钟")
    else:
        add(report, "spot.mtu", "block", f"实例 MTU {mtu:g} 与规则 {rule_mtu:g} 不一致")

    aliases = {}
    if "model_floor_cny_per_mwh" in i_spot and "declare_floor_cny_per_mwh" not in i_spot:
        aliases["declare_floor_cny_per_mwh"] = "model_floor_cny_per_mwh"
    if "model_cap_cny_per_mwh" in i_spot and "declare_cap_cny_per_mwh" not in i_spot:
        aliases["declare_cap_cny_per_mwh"] = "model_cap_cny_per_mwh"
    lookup = dict(i_spot)
    for target, source in aliases.items():
        lookup[target] = i_spot[source]

    for key, label in (
        ("declare_floor_cny_per_mwh", "申报下限"),
        ("declare_cap_cny_per_mwh", "申报上限"),
        ("clear_floor_cny_per_mwh", "出清下限"),
        ("clear_cap_cny_per_mwh", "出清上限"),
    ):
        check_instance_limit(report, lookup, r_spot, key, label)

    bands = r_spot.get("asset_bands") or {}
    if bands:
        band_key = {
            "thermal": "thermal",
            "wind": "renewable",
            "pv_storage": "renewable",
            "storage": "storage",
        }.get(report["asset_class"])
        band = bands.get(band_key) if band_key else None
        if band:
            floor = as_float(band.get("declare_floor_cny_per_mwh"))
            cap = as_float(band.get("declare_cap_cny_per_mwh"))
            if floor is None and cap is None:
                add(report, "spot.asset_band", "warn", f"资产分档 {band_key} 未核实，按总区间校验")
            else:
                add(
                    report,
                    "spot.asset_band",
                    "warn" if band.get("enforcement") != "hard" else "pass",
                    f"资产分档 {band_key}：{floor if floor is not None else '未定'}–{cap if cap is not None else '未定'} 元/MWh"
                    f"（{band.get('enforcement', 'soft')}）",
                )

    drafts = r_spot.get("drafts") or []
    if drafts:
        misused = []
        for draft in drafts:
            for key in (
                "declare_floor_cny_per_mwh",
                "declare_cap_cny_per_mwh",
                "clear_floor_cny_per_mwh",
                "clear_cap_cny_per_mwh",
            ):
                instance_value = as_float(lookup.get(key))
                draft_value = as_float(draft.get(key))
                if instance_value is not None and draft_value is not None and abs(instance_value - draft_value) <= 1e-9:
                    misused.append(f"{key}={draft_value:g}")
        if misused:
            add(report, "spot.draft_misuse", "warn", "实例现行参数与未生效草案一致：" + "；".join(misused))
        else:
            add(report, "spot.draft_misuse", "pass", f"{len(drafts)} 份草案未写入实例现行申报字段")


def check_thermal_config(report, instance, rule):
    if report["asset_class"] != "thermal":
        return
    block = rule.get("thermal_participation")
    if not isinstance(block, dict):
        add(report, "thermal.participation", "skip", "规则包未提供煤电最小技术出力条款")
        return
    asset = instance.get("asset") or {}
    capacity = asset_power(instance, "thermal")
    minimum = as_float(asset.get("min_output_mw"))
    expected = as_float(block.get("min_technical_output_ratio"))
    if capacity and minimum is not None and expected is not None:
        ratio = minimum / capacity
        if ratio + 1e-9 < expected:
            add(
                report,
                "thermal.min_output",
                "warn",
                f"实例最小出力 {minimum:g} MW / {capacity:g} MW = {ratio:.1%}，低于规则 {expected:.0%}；"
                "若为供热期特殊工况需注明依据",
            )
        else:
            add(report, "thermal.min_output", "pass", f"最小出力比例 {ratio:.1%} 不低于规则 {expected:.0%}")
    else:
        add(report, "thermal.min_output", "skip", "实例缺少 min_output_mw 或容量，跳过最小出力比对")
    if block.get("run_cost_compensation") is True:
        add(report, "thermal.run_cost", "warn", "规则包含运行成本补偿；实例是否计入需按省级细则确认")
    else:
        add(report, "thermal.run_cost", "skip", "规则未声明运行成本补偿")


def check_storage_config(report, instance, rule):
    if report["asset_class"] not in ("storage", "pv_storage"):
        return
    asset = instance.get("asset") or {}
    storage = asset.get("storage") if report["asset_class"] == "pv_storage" else asset
    if not isinstance(storage, dict):
        add(report, "storage.config", "block", "实例缺少储能参数")
        return
    power = as_float(storage.get("power_mw"))
    energy = as_float(storage.get("energy_mwh"))
    block = rule.get("storage_participation") or {}
    min_power = as_float(block.get("min_power_mw"))
    min_duration = as_float(block.get("min_duration_h"))
    if report["asset_class"] == "storage":
        if power is not None and min_power is not None:
            if power + 1e-9 < min_power:
                add(report, "storage.min_power", "block", f"储能功率 {power:g} MW 低于独立储能门槛 {min_power:g} MW")
            else:
                add(report, "storage.min_power", "pass", f"储能功率 {power:g} MW 满足门槛 {min_power:g} MW")
        if power and energy is not None and min_duration is not None:
            duration = energy / power
            if duration + 1e-9 < min_duration:
                add(
                    report,
                    "storage.min_duration",
                    "block",
                    f"储能时长 {duration:g} h 低于门槛 {min_duration:g} h",
                )
            else:
                add(report, "storage.min_duration", "pass", f"储能时长 {duration:g} h 满足门槛 {min_duration:g} h")
    colocated = rule.get("colocated_storage") or {}
    if report["asset_class"] == "pv_storage":
        pv = asset.get("pv") or {}
        pv_capacity = as_float(pv.get("capacity_mw"))
        max_ratio = as_float(colocated.get("max_power_ratio_pv"))
        if power is not None and pv_capacity and max_ratio is not None:
            ratio = power / pv_capacity
            if ratio > max_ratio + 1e-9:
                add(
                    report,
                    "storage.colocated_ratio",
                    "block",
                    f"配储功率 {power:g} MW / 光伏 {pv_capacity:g} MW = {ratio:.1%}，超过规则上限 {max_ratio:.0%}",
                )
            else:
                add(report, "storage.colocated_ratio", "pass", f"配储功率比例 {ratio:.1%} 未超过 {max_ratio:.0%}")
        grid = asset.get("grid_connection") or {}
        import_limit = as_float(grid.get("import_limit_mw"))
        grid_charge_allowed = colocated.get("grid_charge_allowed")
        if import_limit is not None and grid_charge_allowed is False:
            if import_limit <= 1e-9:
                add(report, "storage.grid_charge", "pass", "并网购电上限为 0，与‘不得从公共电网充电’一致")
            else:
                add(
                    report,
                    "storage.grid_charge",
                    "warn",
                    f"并网购电上限 {import_limit:g} MW > 0，需确认配储充电是否只来自配套光伏",
                )


def capacity_type(asset_class):
    return {
        "thermal": "coal",
        "storage": "grid_storage",
        "pv_storage": "colocated_storage",
        "wind": "wind",
    }.get(asset_class)


def find_capacity_income(summary):
    if not isinstance(summary, dict):
        return None, None
    keys = ("capacity_compensation_cny", "capacity_cny", "capacity_income_cny", "capacity_revenue_cny")
    for container in (summary, summary.get("plan") or {}, summary.get("base") or {}):
        if not isinstance(container, dict):
            continue
        for key in keys:
            value = as_float(container.get(key))
            if value is not None and value > 1e-9:
                return key, value
    return None, None


def check_capacity(report, instance, rule, summary, target):
    block = rule.get("capacity_compensation")
    if not isinstance(block, dict):
        return
    asset_class = report["asset_class"]
    if asset_class in ("retail", "direct", "unknown"):
        return
    kind = capacity_type(asset_class)
    candidates = {kind}
    if asset_class == "storage":
        candidates.update({"grid_storage", "storage"})
    ineligible = set(block.get("ineligible_types") or [])
    eligible = set(block.get("eligible_types") or [])
    unverified = set(block.get("unverified_types") or [])
    status = str(block.get("status") or "")
    income_key, income_value = find_capacity_income(summary)
    if status == "not_applicable":
        if income_key:
            add(
                report,
                "capacity.eligibility",
                "block",
                f"规则明确本资产类别不适用容量补偿，但输出中出现 {income_key}={income_value:,.0f} 元",
            )
        else:
            add(report, "capacity.eligibility", "pass", "规则明确本资产类别不适用容量补偿，实例未计容量收入")
        return
    if candidates & ineligible:
        if income_key:
            add(
                report,
                "capacity.eligibility",
                "block",
                f"本资产类别不适用容量补偿，但输出中出现 {income_key}={income_value:,.0f} 元",
            )
        else:
            add(report, "capacity.eligibility", "pass", "本资产类别不在容量补偿范围内，实例未计容量收入")
        return
    if candidates & unverified:
        if income_key:
            add(
                report,
                "capacity.eligibility",
                "warn",
                f"容量补偿资格未核实，但输出中出现 {income_key}={income_value:,.0f} 元；人工确认前不得计入结算",
            )
        else:
            add(report, "capacity.eligibility", "warn", "容量补偿资格未核实，实例未计容量收入；确认省级细则后再计入")
        return
    if not (candidates & eligible):
        add(report, "capacity.eligibility", "warn", f"资产类型 {kind} 未在规则资格清单中")
        return
    check_period(report, block, "容量补偿规则", target, hard=False, prefix="capacity.effective")
    if status in ("pending_parameters", "unverified", "pending"):
        add(report, "capacity.parameters", "warn", f"容量补偿资格成立，但参数未核实（{status}）")
        return
    rule_price = as_float(block.get("price_cny_per_kw_year"))
    instance_rules = instance.get("rules") or {}
    config = instance_rules.get("capacity_compensation") or instance_rules.get("capacity") or {}
    instance_price = as_float(config.get("price_cny_per_kw_year"))
    if rule_price is not None and instance_price is not None:
        if abs(rule_price - instance_price) > 1e-9:
            add(
                report,
                "capacity.price",
                "block",
                f"容量补偿价不一致：实例 {instance_price:g} vs 规则 {rule_price:g} 元/kW·年",
            )
        else:
            add(report, "capacity.price", "pass", f"容量补偿价一致：{rule_price:g} 元/kW·年")
    else:
        add(report, "capacity.price", "skip", "实例或规则缺少容量补偿价")
    text = " ".join(str(block.get(key, "")) for key in ("source", "note", "grade"))
    if "D 级" in text or "演示" in text:
        add(report, "capacity.assumption", "warn", "容量补偿系数/参数含 D 级演示值，不能当作正式结算依据")
    else:
        add(report, "capacity.assumption", "pass", "容量补偿参数未见 D 级演示标记")


def check_ancillary(report, instance, rule):
    block = rule.get("ancillary")
    if not isinstance(block, dict):
        return
    asset_class = report["asset_class"]
    if asset_class not in ("thermal",):
        return
    status = str(block.get("status") or "")
    if status in ("unverified_prices", "unverified", "pending"):
        add(report, "ancillary.status", "warn", f"辅助服务规则状态为 {status}，限价/比例需人工核对")
    else:
        add(report, "ancillary.status", "pass", f"辅助服务规则状态：{status or '未标注'}")
    policy = instance.get("policy") or {}
    mileage_cap = as_float(block.get("mileage_price_cap_cny_per_kw_mile"))
    mileage = as_float(policy.get("mileage_price_cny_per_kw_mile"))
    if mileage_cap is not None and mileage is not None:
        if mileage > mileage_cap + 1e-12:
            add(report, "ancillary.mileage_cap", "block", f"里程价 {mileage:g} 超过规则上限 {mileage_cap:g} 元/kW·mile")
        else:
            add(report, "ancillary.mileage_cap", "pass", f"里程价 {mileage:g} 未超过上限 {mileage_cap:g}")
    coefficient_cap = as_float(block.get("coefficient_cap"))
    k_factor = as_float(policy.get("k_factor"))
    if coefficient_cap is not None and k_factor is not None:
        if k_factor > coefficient_cap + 1e-12:
            add(report, "ancillary.coefficient_cap", "block", f"K 值 {k_factor:g} 超过系数上限 {coefficient_cap:g}")
        else:
            add(report, "ancillary.coefficient_cap", "pass", f"K 值 {k_factor:g} 未超过上限 {coefficient_cap:g}")
    ratios = []
    for key in ("frequency_regulation", "reserve"):
        item = block.get(key) or {}
        ratio = as_float(item.get("capacity_ratio"))
        if ratio is not None:
            ratios.append((key, ratio))
    if ratios:
        total = sum(value for _, value in ratios)
        if total > 1.0 + 1e-9:
            add(report, "ancillary.overlap", "block", f"规则包登记的调频+备用容量比例合计 {total:.0%}，超过 100%")
        elif total > 0.6 + 1e-9:
            add(
                report,
                "ancillary.overlap",
                "warn",
                f"规则包登记的调频+备用容量比例合计 {total:.0%}，需确认同一 MW 未重复出售；仅规则口径，未核实例申报容量",
            )
        else:
            add(
                report,
                "ancillary.overlap",
                "pass",
                f"规则包登记的调频+备用容量比例合计 {total:.0%}，未超过 60%；仅规则口径，未核实例申报容量",
            )


def check_deviation(report, rule):
    block = rule.get("deviation_assessment")
    if not isinstance(block, dict) or report["asset_class"] not in ("wind", "pv_storage"):
        return
    text = " ".join(str(block.get(key, "")) for key in ("source", "note", "grade"))
    if "D 级" in text or "D级" in text:
        add(report, "deviation.assumption", "warn", "偏差考核公式含 D 级简化，只能作风险提示，不能当结算依据")
    else:
        add(report, "deviation.assumption", "pass", "偏差考核条款未见 D 级简化标记")


def mentions_ratio(text, value):
    if value is None:
        return False
    for token in (f"{value * 100:g}", f"{value:g}"):
        if re.search(rf"(?<![\d.]){re.escape(token)}(?![\d.])", text):
            return True
    return False


def check_retail(report, instance, rule, target):
    if report["asset_class"] != "retail":
        return
    block = rule.get("retail")
    if not isinstance(block, dict):
        add(report, "retail.rule", "block", "售电零售实例缺少 retail 规则块")
        return
    check_period(report, block, "零售规则", target, hard=True, prefix="retail.effective")
    deviation = block.get("deviation") or {}
    if str(deviation.get("status")) == "unverified":
        add(report, "retail.deviation", "warn", "零售偏差考核未核到正式文件，不得按外省规则套用")
    else:
        add(report, "retail.deviation", "pass", "零售偏差条款已标注状态")
    retail_market = (instance.get("rules") or {}).get("retail_market") or {}
    pricing = block.get("pricing") or {}
    if pricing.get("mode") and retail_market.get("one_household_one_price") is not None:
        if pricing.get("mode") == "一户一价" and retail_market.get("one_household_one_price") is True:
            add(report, "retail.one_household", "pass", "实例一户一价标记与规则一致")
        else:
            add(report, "retail.one_household", "warn", "实例一户一价标记与规则不一致，需核对套餐")
    tou = block.get("tou_constraint") or {}
    formula = (instance.get("rules") or {}).get("price_formula") or {}
    instance_tou = str(formula.get("tou_constraint") or "")
    if tou:
        peak = as_float(tou.get("peak_min_ratio_of_flat"))
        valley = as_float(tou.get("valley_max_ratio_of_flat"))
        if not instance_tou:
            add(report, "retail.tou", "warn", "规则包含峰谷约束，但实例未声明 tou_constraint")
        elif peak is not None and valley is not None:
            if mentions_ratio(instance_tou, peak) and mentions_ratio(instance_tou, valley):
                add(report, "retail.tou", "pass", f"实例分时约束与规则一致：峰≥平×{peak:.0%}、谷≤平×{valley:.0%}")
            else:
                add(report, "retail.tou", "warn", f"实例分时约束未同时包含峰≥平×{peak:.0%}、谷≤平×{valley:.0%}")
        else:
            add(report, "retail.tou", "warn", "规则包峰谷约束数值不完整，无法比对")
    guarantee = block.get("guarantee") or {}
    draft = guarantee.get("draft") or {}
    if draft:
        basis = str((instance.get("portfolio") or {}).get("guarantee", {}).get("basis", ""))
        if "2026-09-04" in basis or "草案" in basis:
            add(report, "retail.guarantee", "warn", "实例可能引用未生效保函草案，需切回现行 1595 号公式")
        else:
            add(report, "retail.guarantee", "pass", "未发现实例引用未生效保函草案")
    if block.get("settlement") or block.get("settlement_timeline"):
        add(report, "retail.settlement", "pass", "规则包已登记结算时间线")


def check_direct(report, instance, rule, summary, target):
    if report["asset_class"] != "direct":
        return
    block = rule.get("direct_connection")
    if not isinstance(block, dict):
        add(report, "direct.rule", "block", "绿电直连实例缺少 direct_connection 规则块")
        return
    check_period(report, block, "绿电直连规则", target, hard=True, prefix="direct.effective")
    compliance = (summary or {}).get("compliance") or {}
    checks = compliance.get("checks") or {}
    users_check = checks.get("users") or {}
    users = as_float(users_check.get("value"))
    if users is None:
        project = instance.get("project") or {}
        users = float(len(project.get("users") or [])) if project.get("users") else None
    min_users = as_float(block.get("min_users"))
    if users is not None and min_users is not None:
        if users + 1e-9 < min_users:
            add(report, "direct.users", "block", f"用户数 {users:g} 少于规则下限 {min_users:g}")
        else:
            add(report, "direct.users", "pass", f"用户数 {users:g} 满足下限 {min_users:g}")
    else:
        add(report, "direct.users", "warn", "无法读取用户数，跳过直连用户数校验")
    ratio_checks = (
        ("self_use_generation", "self_use_min_ratio_generation", "自用/发电量", ">="),
        ("self_use_consumption", "self_use_min_ratio_consumption", "自用/用电量", ">="),
        ("feed_in_generation", "feed_in_max_ratio_generation", "上网/发电量", "<="),
    )
    for check_key, rule_key, label, operator in ratio_checks:
        item = checks.get(check_key) or {}
        value = as_float(item.get("value"))
        threshold = as_float(block.get(rule_key))
        if value is None or threshold is None:
            add(report, f"direct.{check_key}", "warn", f"{label} 缺少数值，无法校验")
            continue
        ok = value >= threshold - 1e-9 if operator == ">=" else value <= threshold + 1e-9
        if ok:
            add(report, f"direct.{check_key}", "pass", f"{label} {value:.2%} 满足 {operator} {threshold:.0%}")
        else:
            add(report, f"direct.{check_key}", "block", f"{label} {value:.2%} 不满足 {operator} {threshold:.0%}")
    text = " ".join(str(block.get(key, "")) for key in ("source", "note"))
    if any(word in text for word in ("待核实", "两种说法", "未核到")):
        add(report, "direct.source", "warn", "多用户直连规则日期/文号仍有待核项，签约前核对正式原文")


def check_interprovincial(report, instance, rule, target):
    block = rule.get("interprovincial")
    market = str((instance.get("meta") or {}).get("market") or "")
    if not isinstance(block, dict) or "省间" not in market:
        return
    check_period(report, block, "省间现货规则", target, hard=True, prefix="interprovincial.effective")
    capacity = asset_power(instance, report["asset_class"])
    min_bid = as_float(block.get("min_bid_mw"))
    if capacity is not None and min_bid is not None:
        if capacity + 1e-9 < min_bid:
            add(report, "interprovincial.min_bid", "block", f"装机 {capacity:g} MW 低于省间最小申报 {min_bid:g} MW")
        else:
            add(report, "interprovincial.min_bid", "pass", f"装机 {capacity:g} MW 不低于省间最小申报 {min_bid:g} MW")


def price_band(r_spot, asset_class):
    bands = r_spot.get("asset_bands") or {}
    band_key = {
        "thermal": "thermal",
        "wind": "renewable",
        "pv_storage": "renewable",
        "storage": "storage",
    }.get(asset_class)
    band = bands.get(band_key) if band_key else None
    floor = as_float(r_spot.get("declare_floor_cny_per_mwh"))
    cap = as_float(r_spot.get("declare_cap_cny_per_mwh"))
    floor_enforcement = str(r_spot.get("limits_enforcement", "hard"))
    cap_enforcement = floor_enforcement
    source = "总区间"
    if band:
        band_floor = as_float(band.get("declare_floor_cny_per_mwh"))
        band_cap = as_float(band.get("declare_cap_cny_per_mwh"))
        if band_floor is not None or band_cap is not None:
            floor = band_floor if band_floor is not None else floor
            cap = band_cap if band_cap is not None else cap
            floor_enforcement = str(band.get("enforcement", "soft"))
            cap_enforcement = floor_enforcement
            source = f"资产分档 {band_key}"
    if cap is None:
        cap = as_float(r_spot.get("validation_upper_cny_per_mwh"))
        cap_enforcement = str(r_spot.get("validation_upper_enforcement", "soft"))
        if cap is not None:
            source += " + 软性校验上限"
    return {
        "floor": floor,
        "cap": cap,
        "floor_level": "block" if floor_enforcement == "hard" or (floor_enforcement == "partial" and not band) else "warn",
        "cap_level": "block" if cap_enforcement == "hard" else "warn",
        "source": source,
    }


def bid_price(band, value):
    if value is None:
        return None, None
    floor = band["floor"]
    cap = band["cap"]
    if floor is not None and value < floor - 1e-6:
        return band["floor_level"], f"低于下限 {floor:g}（{value:g}）"
    if cap is not None and value > cap + 1e-6:
        return band["cap_level"], f"高于上限 {cap:g}（{value:g}）"
    return None, None


def storage_soc(asset, rows, mode, mtu):
    energy = as_float(asset.get("energy_mwh"))
    if not energy:
        usable = as_float(asset.get("usable_energy_mwh"))
        soc_min = as_float(asset.get("soc_min"))
        soc_max = as_float(asset.get("soc_max"))
        if usable and soc_min is not None and soc_max is not None and soc_max > soc_min:
            energy = usable / (soc_max - soc_min)
    if not energy:
        return None
    rte = as_float(asset.get("rte"))
    rte_missing = rte is None
    if rte is None:
        rte = 1.0
    if not 0 < rte <= 1:
        return None
    soc = as_float(asset.get("soc_init"))
    if soc is None:
        return None
    dt = (mtu or 15.0) / 60.0
    net = {}
    simultaneous = []
    if mode == "side":
        for row in rows:
            side = str(row.get("side") or "").strip().lower()
            quantity = as_float(row.get("quantity_mw"))
            slot = as_float(row.get("slot"))
            if quantity is None or slot is None:
                continue
            slot = int(slot)
            net.setdefault(slot, {"charge": 0.0, "discharge": 0.0})
            if side == "charge":
                net[slot]["charge"] += quantity
            elif side == "discharge":
                net[slot]["discharge"] += quantity
        for slot, item in net.items():
            if item["charge"] > 1e-9 and item["discharge"] > 1e-9:
                simultaneous.append(slot)
    else:
        for row in rows:
            charge = as_float(row.get("charge_plan_mw")) or 0.0
            discharge = as_float(row.get("discharge_plan_mw")) or 0.0
            slot = as_float(row.get("slot"))
            if slot is None:
                continue
            slot = int(slot)
            net.setdefault(slot, {"charge": 0.0, "discharge": 0.0})
            net[slot]["charge"] += charge
            net[slot]["discharge"] += discharge
            if charge > 1e-9 and discharge > 1e-9:
                simultaneous.append(slot)
    minimum = maximum = soc
    for slot in sorted(net):
        item = net[slot]
        soc += item["charge"] * dt * math.sqrt(rte) / energy
        soc -= item["discharge"] * dt / math.sqrt(rte) / energy
        minimum = min(minimum, soc)
        maximum = max(maximum, soc)
    return {
        "min": minimum,
        "max": maximum,
        "final": soc,
        "simultaneous": simultaneous,
        "soc_min": as_float(asset.get("soc_min")),
        "soc_max": as_float(asset.get("soc_max")),
        "rte": rte,
        "rte_missing": rte_missing,
    }


def value_or(value, fallback):
    return fallback if value is None else value


def check_bid(report, pack, bid_path, instance, rule, r_spot, target, explicit):
    if bid_path is not None and report["asset_class"] not in SPOT_ASSETS:
        add(report, "bid.file", "skip", "本实例不提交省内现货申报，忽略申报 CSV")
        return
    if bid_path is None:
        if explicit:
            add(report, "bid.file", "block", "命令行指定的申报文件不存在")
        else:
            add(report, "bid.file", "skip", "无申报 CSV；只做配置与规则校验")
        return
    try:
        rows, fields = read_csv(bid_path)
    except (OSError, ValueError) as error:
        add(report, "bid.file", "block", f"申报文件无法读取：{error}")
        return
    if not rows:
        add(report, "bid.file", "block", "申报文件为空")
        return
    add(report, "bid.file", "pass", f"读取申报文件：{relpath(bid_path)}（{len(rows)} 行）")

    price_key = next(
        (
            key
            for key in ("bid_price_cny_per_mwh", "offer_price", "price_cny_per_mwh", "bid_price")
            if key in fields
        ),
        None,
    )
    quantity_keys = [
        key
        for key in (
            "quantity_mw",
            "declared_mw",
            "must_run_mw",
            "declared_net_export_mw",
            "charge_plan_mw",
            "discharge_plan_mw",
        )
        if key in fields
    ]
    if price_key is None and not quantity_keys:
        add(report, "bid.columns", "block", f"无法识别价格或数量列：{', '.join(fields)}")
        return
    add(report, "bid.columns", "pass", f"识别价格列 {price_key or '无'}；数量列 {', '.join(quantity_keys) or '无'}")

    expected_points = int(as_float(r_spot.get("points_per_day")) or 0)
    slot_values = []
    bad_slots = 0
    for row in rows:
        slot = as_float(row.get("slot"))
        if slot is None or slot < 0:
            bad_slots += 1
        else:
            slot_values.append(int(slot))
    if bad_slots:
        add(report, "bid.slots", "block", f"{bad_slots} 行缺少有效 slot")
    elif not slot_values:
        add(report, "bid.slots", "block", "申报文件没有可解析的 slot")
    elif expected_points and max(slot_values) >= expected_points:
        add(
            report,
            "bid.slots",
            "block",
            f"slot 最大值 {max(slot_values)} 超出规则点数 0–{expected_points - 1}",
        )
    else:
        add(report, "bid.slots", "pass", f"slot 范围 0–{max(slot_values)}，未超出规则点数")

    sides = {str(row.get("side") or "").strip().lower() for row in rows if str(row.get("side") or "").strip()}
    sparse = bool(sides) and sides <= {"charge", "discharge"}
    full_required = bool(
        not sparse
        and (
            any(key in fields for key in ("declared_mw", "must_run_mw", "declared_net_export_mw"))
            or ("side" not in fields and quantity_keys)
        )
    )
    duplicates = []
    seen = set()
    for row in rows:
        slot = as_float(row.get("slot"))
        side = str(row.get("side") or "").strip().lower()
        key = (int(slot), side) if slot is not None else None
        if key in seen:
            duplicates.append(key)
        if key:
            seen.add(key)
    if duplicates:
        add(report, "bid.duplicates", "block", f"存在重复 (slot, side)：{duplicates[:5]}")
    if expected_points and full_required:
        missing = sorted(set(range(expected_points)) - set(slot_values))
        if missing:
            add(
                report,
                "bid.coverage",
                "block",
                f"全量申报缺少 {len(missing)} 个 slot，例如 {missing[:8]}",
            )
        else:
            add(report, "bid.coverage", "pass", f"全量申报覆盖完整：{expected_points} 点")
    elif sparse:
        add(report, "bid.coverage", "pass", f"稀疏申报 {len(slot_values)} 行；未出现的 slot 按 0 处理")
    else:
        add(report, "bid.coverage", "skip", "无法判断是否要求全量覆盖")

    if target is not None:
        date_values = [str(row.get("date") or "").strip() for row in rows]
        known_dates = {value for value in date_values if value}
        blank_dates = sum(1 for value in date_values if not value)
        if not known_dates:
            add(report, "bid.date", "warn", "申报文件没有 date 列或日期为空")
        elif known_dates != {target.isoformat()}:
            add(
                report,
                "bid.date",
                "block",
                f"申报日期 {', '.join(sorted(known_dates))} 与目标交易日 {target.isoformat()} 不一致",
            )
        elif blank_dates:
            add(
                report,
                "bid.date",
                "warn",
                f"已核 {len(rows) - blank_dates} 行日期与目标交易日一致，但 {blank_dates} 行 date 为空，未完成校核",
            )
        else:
            add(report, "bid.date", "pass", f"申报日期与目标交易日一致：{target.isoformat()}")

    band = price_band(r_spot, report["asset_class"])
    raw_prices = [as_float(row.get(price_key)) for row in rows] if price_key else []
    missing_prices = sum(1 for value in raw_prices if value is None)
    prices = [value for value in raw_prices if value is not None]
    if band["floor"] is None and band["cap"] is None:
        add(report, "bid.price_band", "warn", "规则未提供可用的申报/出清限价，无法校核报价边界")
    elif not prices:
        if price_key:
            add(report, "bid.price_band", "warn", f"价格列 {price_key} 存在但没有可解析数值，未完成校核")
        else:
            add(report, "bid.price", "skip", "申报文件没有可解析价格")
    else:
        violations = []
        level = None
        for row in rows:
            value = as_float(row.get(price_key))
            hit_level, message = bid_price(band, value)
            if hit_level:
                if level != "block":
                    level = hit_level
                violations.append(f"slot {row.get('slot')}: {message}")
        missing_note = f"；另有 {missing_prices} 行价格为空" if missing_prices else ""
        if violations:
            add(
                report,
                "bid.price_band",
                level,
                f"{len(violations)} 行价格越界（{band['source']}，下限 {band['floor']} / 上限 {band['cap']}）："
                + "；".join(violations[:5])
                + missing_note,
            )
        elif missing_prices:
            add(
                report,
                "bid.price_band",
                "warn",
                f"已核 {len(prices)} 行价格在边界内（{band['source']}，下限 {band['floor']} / 上限 {band['cap']}），"
                f"但 {missing_prices} 行缺价格，未完成校核",
            )
        else:
            add(
                report,
                "bid.price_band",
                "pass",
                f"价格 {min(prices):g}–{max(prices):g} 在边界内（{band['source']}，下限 {band['floor']} / 上限 {band['cap']}）",
            )

    negatives = []
    for row in rows:
        for key in quantity_keys:
            value = as_float(row.get(key))
            if value is not None and value < -1e-9:
                negatives.append(f"slot {row.get('slot')} {key}={value:g}")
    if negatives:
        add(report, "bid.quantity", "block", f"{len(negatives)} 个数量为负：{'; '.join(negatives[:5])}")
    elif quantity_keys:
        add(report, "bid.quantity", "pass", "未发现负数量")

    if report["asset_class"] == "wind":
        capacity = asset_power(instance, "wind")
        grid = (instance.get("asset") or {}).get("grid_connection") or {}
        export_limit = value_or(as_float(grid.get("export_limit_mw")), capacity)
        over_capacity = []
        over_forecast = []
        declared_rows = 0
        forecast_rows = 0
        for row in rows:
            declared = as_float(row.get("declared_mw"))
            forecast = as_float(row.get("forecast_mw"))
            if declared is not None:
                declared_rows += 1
            if forecast is not None:
                forecast_rows += 1
            if declared is None:
                continue
            if export_limit is not None and declared > export_limit + 1e-6:
                over_capacity.append(f"slot {row.get('slot')}: {declared:g}>{export_limit:g}")
            if forecast is not None and declared > forecast + 1e-6:
                over_forecast.append(f"slot {row.get('slot')}: {declared:g}>{forecast:g}")
        missing_declared = len(rows) - declared_rows
        missing_forecast = len(rows) - forecast_rows
        if not declared_rows:
            add(report, "bid.wind_capacity", "skip", "申报文件没有可解析 declared_mw，无法校核装机/并网上限")
        elif export_limit is None:
            add(report, "bid.wind_capacity", "warn", "缺少并网上限和装机容量，无法校核申报量")
        elif over_capacity:
            add(report, "bid.wind_capacity", "block", f"{len(over_capacity)} 行申报量超过并网上限：{'; '.join(over_capacity[:5])}")
        elif missing_declared:
            add(
                report,
                "bid.wind_capacity",
                "warn",
                f"已核 {declared_rows} 行未超并网上限 {export_limit:g} MW，但 {missing_declared} 行缺 declared_mw，未完成校核",
            )
        else:
            add(report, "bid.wind_capacity", "pass", f"已核 {declared_rows} 行，申报量未超过并网上限 {export_limit:g} MW")
        if not forecast_rows:
            add(report, "bid.wind_forecast", "skip", "申报文件没有可解析 forecast_mw，无法校核参考预测")
        elif over_forecast:
            add(
                report,
                "bid.wind_forecast",
                "warn",
                f"{len(over_forecast)} 行申报量超过参考预测，存在超报风险：{'; '.join(over_forecast[:5])}",
            )
        elif missing_forecast:
            add(
                report,
                "bid.wind_forecast",
                "warn",
                f"已核 {forecast_rows} 行未超参考预测，但 {missing_forecast} 行缺 forecast_mw，未完成校核",
            )
        else:
            add(report, "bid.wind_forecast", "pass", f"已核 {forecast_rows} 行，申报量未超过参考预测")

    if report["asset_class"] == "thermal":
        asset = instance.get("asset") or {}
        capacity = asset_power(instance, "thermal")
        reserve = value_or(as_float((instance.get("policy") or {}).get("regulation_reserve_mw")), 0.0)
        minimum = as_float(asset.get("min_output_mw"))
        over_total = []
        under_min = []
        missing_rows = 0
        checked_total = 0
        checked_min = 0
        has_dispatch_columns = "must_run_mw" in fields and "quantity_mw" in fields
        if capacity is None:
            add(report, "bid.thermal_total", "warn", "缺少装机容量，无法校核 must_run+增量上限")
        elif reserve > capacity + 1e-9:
            add(
                report,
                "bid.thermal_total",
                "block",
                f"调频备用 {reserve:g} MW 大于装机 {capacity:g} MW，容量扣减后无可申报空间",
            )
        elif not has_dispatch_columns:
            add(report, "bid.thermal_total", "skip", "申报文件缺少 must_run_mw 或 quantity_mw 列，无法校核总量")
        else:
            cap = capacity - reserve
            for row in rows:
                must_run = as_float(row.get("must_run_mw"))
                quantity = as_float(row.get("quantity_mw"))
                if must_run is None or quantity is None:
                    missing_rows += 1
                    continue
                checked_total += 1
                total = must_run + quantity
                if total > cap + 1e-6:
                    over_total.append(f"slot {row.get('slot')}: {total:g}>{cap:g}")
            if not checked_total:
                add(report, "bid.thermal_total", "skip", "没有可解析的 must_run_mw/quantity_mw 行")
            elif over_total:
                add(
                    report,
                    "bid.thermal_total",
                    "block",
                    f"{len(over_total)} 行 must_run+增量超过（容量−调频备用）{cap:g} MW：{'; '.join(over_total[:5])}",
                )
            elif missing_rows:
                add(
                    report,
                    "bid.thermal_total",
                    "warn",
                    f"已核 {checked_total} 行未超 {cap:g} MW，但 {missing_rows} 行缺 must_run_mw/quantity_mw，未完成校核",
                )
            else:
                add(report, "bid.thermal_total", "pass", f"已核 {checked_total} 行，must_run+增量未超过 {cap:g} MW（已扣 {reserve:g} MW 调频备用）")
        if minimum is None:
            add(report, "bid.thermal_min", "skip", "实例缺少 min_output_mw，无法校核最小出力")
        else:
            for row in rows:
                must_run = as_float(row.get("must_run_mw"))
                if must_run is None:
                    continue
                checked_min += 1
                if must_run + 1e-6 < minimum:
                    under_min.append(f"slot {row.get('slot')}: {must_run:g}<{minimum:g}")
            if not checked_min:
                add(report, "bid.thermal_min", "skip", "没有可解析的 must_run_mw 行")
            elif under_min:
                add(report, "bid.thermal_min", "warn", f"{len(under_min)} 行 must_run 低于机组最小出力：{'; '.join(under_min[:5])}")
            elif checked_min < len(rows):
                add(report, "bid.thermal_min", "warn", f"已核 {checked_min} 行未低于最小出力，但 {len(rows) - checked_min} 行缺 must_run_mw，未完成校核")
            else:
                add(report, "bid.thermal_min", "pass", f"已核 {checked_min} 行，must_run 均不低于机组最小出力 {minimum:g} MW")

    if report["asset_class"] == "storage":
        asset = instance.get("asset") or {}
        power = as_float(asset.get("power_mw"))
        grid = asset.get("grid_connection") or {}
        import_limit = value_or(as_float(grid.get("import_limit_mw")), power)
        export_limit = value_or(as_float(grid.get("export_limit_mw")), power)
        over_power = []
        checked_power = 0
        missing_limit = 0
        missing_quantity = 0
        if power is None and import_limit is None and export_limit is None:
            add(report, "bid.storage_power", "skip", "缺少储能功率和并网进出口限值，无法校核充放电功率")
        else:
            for row in rows:
                side = str(row.get("side") or "").strip().lower()
                quantity = as_float(row.get("quantity_mw"))
                if quantity is None:
                    missing_quantity += 1
                    continue
                candidates = [power]
                if side == "charge":
                    candidates.append(import_limit)
                elif side == "discharge":
                    candidates.append(export_limit)
                candidates = [value for value in candidates if value is not None]
                if not candidates:
                    missing_limit += 1
                    continue
                limit = min(candidates)
                checked_power += 1
                if quantity > limit + 1e-6:
                    over_power.append(f"slot {row.get('slot')} {side}: {quantity:g}>{limit:g}")
            if over_power:
                add(report, "bid.storage_power", "block", f"{len(over_power)} 行充放电功率超限：{'; '.join(over_power[:5])}")
            elif not checked_power:
                add(report, "bid.storage_power", "skip", "没有可解析的充放电数量行")
            elif missing_quantity:
                add(
                    report,
                    "bid.storage_power",
                    "warn",
                    f"已核 {checked_power} 行未超限，但 {missing_quantity} 行缺 quantity_mw，未完成校核",
                )
            elif missing_limit:
                add(report, "bid.storage_power", "warn", f"已核 {checked_power} 行未超限，但 {missing_limit} 行缺少可用功率/并网限值")
            else:
                add(report, "bid.storage_power", "pass", f"已核 {checked_power} 行，充放电功率未超过功率/并网限值")
        soc = storage_soc(asset, rows, "side", as_float(r_spot.get("market_time_unit_min")))
        if soc is None:
            add(report, "bid.storage_soc", "warn", "缺少 energy_mwh/soc_init 或储能参数无效，无法近似校核 SOC")
        else:
            if soc.get("rte_missing"):
                add(
                    report,
                    "bid.storage_soc_rte",
                    "warn",
                    "实例未提供 rte，SOC 近似按 100% 效率计算；实际效率低于 100% 时放电后 SOC 会被高估，需按 PCS/BMS 参数复核",
                )
            if soc["simultaneous"]:
                add(report, "bid.storage_simultaneous", "block", f"同一 slot 同时充放：{soc['simultaneous'][:8]}")
            else:
                add(report, "bid.storage_simultaneous", "pass", "未发现同一 slot 同时充放")
            low = soc["soc_min"]
            high = soc["soc_max"]
            if soc["min"] < 0 or soc["max"] > 1:
                add(report, "bid.storage_soc", "block", f"近似 SOC {soc['min']:.2%}–{soc['max']:.2%} 超出 0–100% 物理边界")
            elif low is not None and soc["min"] < low - 0.005:
                add(
                    report,
                    "bid.storage_soc",
                    "warn",
                    f"近似 SOC 最低 {soc['min']:.2%} 低于下限 {low:.0%}（近似口径，需滚动复核）",
                )
            elif high is not None and soc["max"] > high + 0.005:
                add(
                    report,
                    "bid.storage_soc",
                    "warn",
                    f"近似 SOC 最高 {soc['max']:.2%} 高于上限 {high:.0%}（近似口径，需滚动复核）",
                )
            else:
                add(
                    report,
                    "bid.storage_soc",
                    "pass",
                    f"近似 SOC {soc['min']:.2%}–{soc['max']:.2%} 在 "
                    f"{low if low is not None else 0:.0%}–{high if high is not None else 1:.0%} 内；期末 {soc['final']:.2%}",
                )

    if report["asset_class"] == "pv_storage":
        asset = instance.get("asset") or {}
        storage = asset.get("storage") or {}
        power = as_float(storage.get("power_mw"))
        grid = asset.get("grid_connection") or {}
        export_limit = value_or(as_float(grid.get("export_limit_mw")), power)
        over_charge = []
        over_discharge = []
        over_pv = []
        over_export = []
        gross_over = []
        checked_power = 0
        checked_pv = 0
        declared_rows = 0
        gross_rows = 0
        for row in rows:
            charge = value_or(as_float(row.get("charge_plan_mw")), 0.0)
            discharge = value_or(as_float(row.get("discharge_plan_mw")), 0.0)
            pv = as_float(row.get("pv_reference_mw"))
            declared = as_float(row.get("declared_net_export_mw"))
            if power is not None:
                checked_power += 1
                if charge > power + 1e-6:
                    over_charge.append(f"slot {row.get('slot')}: {charge:g}>{power:g}")
                if discharge > power + 1e-6:
                    over_discharge.append(f"slot {row.get('slot')}: {discharge:g}>{power:g}")
            if pv is not None:
                checked_pv += 1
                if charge > pv + 1e-6:
                    over_pv.append(f"slot {row.get('slot')}: {charge:g}>{pv:g}")
            if declared is not None:
                declared_rows += 1
                if export_limit is not None and declared > export_limit + 1e-6:
                    over_export.append(f"slot {row.get('slot')}: {declared:g}>{export_limit:g}")
                if pv is not None and "discharge_plan_mw" in fields:
                    gross_rows += 1
                    if declared > pv + discharge + 1e-6:
                        gross_over.append(f"slot {row.get('slot')}: {declared:g}>{pv + discharge:g}")
        missing_declared = len(rows) - declared_rows
        missing_pv = len(rows) - checked_pv
        missing_gross = declared_rows - gross_rows
        if power is None:
            add(report, "bid.pv_storage_power", "skip", "缺少配储 power_mw，无法校核充放电功率")
        elif not any(key in fields for key in ("charge_plan_mw", "discharge_plan_mw")):
            add(report, "bid.pv_storage_power", "skip", "申报文件缺少 charge_plan_mw/discharge_plan_mw，无法校核充放电功率")
        elif over_charge or over_discharge:
            add(
                report,
                "bid.pv_storage_power",
                "block",
                f"配储充放电功率超限：充电 {len(over_charge)} 行、放电 {len(over_discharge)} 行；"
                + "；".join((over_charge + over_discharge)[:5]),
            )
        else:
            add(report, "bid.pv_storage_power", "pass", f"已核 {checked_power} 行，配储充放电功率未超过 {power:g} MW")
        if not checked_pv or "charge_plan_mw" not in fields:
            add(report, "bid.pv_charge_source", "skip", "申报文件缺少 pv_reference_mw 或 charge_plan_mw，无法校核充电来源")
        elif over_pv:
            add(
                report,
                "bid.pv_charge_source",
                "warn",
                f"{len(over_pv)} 行充电计划超过光伏参考出力，可能从电网购电：{'; '.join(over_pv[:5])}",
            )
        elif missing_pv:
            add(
                report,
                "bid.pv_charge_source",
                "warn",
                f"已核 {checked_pv} 行充电计划未超过光伏参考出力，但 {missing_pv} 行缺 pv_reference_mw，未完成校核",
            )
        else:
            add(report, "bid.pv_charge_source", "pass", f"已核 {checked_pv} 行，充电计划未超过光伏参考出力，符合‘配储只用配套光伏充电’")
        if export_limit is None:
            add(report, "bid.pv_export_limit", "warn", "缺少并网上限和配储功率，无法校核净上网")
        elif not declared_rows:
            add(report, "bid.pv_export_limit", "skip", "申报文件没有可解析 declared_net_export_mw")
        elif over_export:
            add(report, "bid.pv_export_limit", "block", f"{len(over_export)} 行净上网超过并网上限：{'; '.join(over_export[:5])}")
        elif missing_declared:
            add(
                report,
                "bid.pv_export_limit",
                "warn",
                f"已核 {declared_rows} 行净上网未超过并网上限 {export_limit:g} MW，但 {missing_declared} 行缺 declared_net_export_mw，未完成校核",
            )
        else:
            add(report, "bid.pv_export_limit", "pass", f"已核 {declared_rows} 行，净上网未超过并网上限 {export_limit:g} MW")
        if not gross_rows:
            add(report, "bid.pv_gross", "skip", "缺少 declared_net_export_mw 或 pv_reference_mw，无法校核净上网来源")
        elif gross_over:
            add(report, "bid.pv_gross", "warn", f"{len(gross_over)} 行净上网超过光伏+放电可用出力：{'; '.join(gross_over[:5])}")
        elif missing_gross:
            add(
                report,
                "bid.pv_gross",
                "warn",
                f"已核 {gross_rows} 行净上网未超过光伏+放电可用出力，但 {missing_gross} 行缺 pv_reference_mw 或 declared_net_export_mw，未完成校核",
            )
        else:
            add(report, "bid.pv_gross", "pass", f"已核 {gross_rows} 行，净上网未超过光伏+放电可用出力")
        soc = storage_soc(storage, rows, "pv", as_float(r_spot.get("market_time_unit_min")))
        if soc is None:
            add(report, "bid.pv_soc", "warn", "缺少 energy_mwh/soc_init 或储能参数无效，无法近似校核 SOC")
        else:
            if soc.get("rte_missing"):
                add(
                    report,
                    "bid.pv_soc_rte",
                    "warn",
                    "实例未提供 rte，SOC 近似按 100% 效率计算；实际效率低于 100% 时放电后 SOC 会被高估，需按 PCS/BMS 参数复核",
                )
            if soc["simultaneous"]:
                add(report, "bid.pv_simultaneous", "warn", f"同一 slot 同时有充电与放电计划：{soc['simultaneous'][:8]}")
            low = soc["soc_min"]
            high = soc["soc_max"]
            if soc["min"] < 0 or soc["max"] > 1:
                add(report, "bid.pv_soc", "block", f"近似 SOC {soc['min']:.2%}–{soc['max']:.2%} 超出 0–100%")
            elif (low is not None and soc["min"] < low - 0.005) or (high is not None and soc["max"] > high + 0.005):
                add(
                    report,
                    "bid.pv_soc",
                    "warn",
                    f"近似 SOC {soc['min']:.2%}–{soc['max']:.2%} 接近/超过 {low:.0%}–{high:.0%} 边界，需滚动复核",
                )
            else:
                add(report, "bid.pv_soc", "pass", f"近似 SOC {soc['min']:.2%}–{soc['max']:.2%} 在边界内")

    instance_interprovincial = isinstance((instance.get("rules") or {}).get("interprovincial"), dict)
    interprovincial = rule.get("interprovincial") if isinstance(rule, dict) else None
    if instance_interprovincial and isinstance(interprovincial, dict) and price_key and quantity_keys:
        min_bid = as_float(interprovincial.get("min_bid_mw"))
        step = as_float(interprovincial.get("bid_step_cny_per_mwh"))
        small = []
        off_step = []
        for row in rows:
            quantity = as_float(row.get("quantity_mw"))
            price = as_float(row.get(price_key))
            if quantity is not None and min_bid is not None and 1e-9 < quantity < min_bid - 1e-9:
                small.append(f"slot {row.get('slot')}: {quantity:g}<{min_bid:g}")
            if price is not None and step and step > 0:
                remainder = abs(price / step - round(price / step))
                if remainder > 1e-6:
                    off_step.append(f"slot {row.get('slot')}: {price:g}")
        if small:
            add(report, "bid.interprovincial_min", "block", f"{len(small)} 行低于省间最小申报量：{'; '.join(small[:5])}")
        if off_step:
            add(report, "bid.interprovincial_step", "warn", f"{len(off_step)} 行不在 {step:g} 元/MWh 报价步长上：{'; '.join(off_step[:5])}")


def evaluate(pack, rules_dir, as_of, now, manifest_day=None, entry=None, bid_override=None, bid_required=False):
    pack = resolve(pack)
    if pack.is_file() and pack.name == "instance.json":
        pack = pack.parent
    instance_path = pack / "instance.json"
    summary_path = find_summary(pack)
    summary = {}
    summary_error = None
    if summary_path:
        try:
            summary = load_json(summary_path)
        except (OSError, json.JSONDecodeError) as error:
            summary = {}
            summary_error = error
    try:
        instance = load_json(instance_path)
    except (OSError, json.JSONDecodeError) as error:
        report = new_report(pack, pack.name, "未知", "unknown")
        add(report, "instance.file", "block", f"实例文件无法读取：{error}")
        return finish(report)

    meta = instance.get("meta") or {}
    province = str(meta.get("province") or "未知")
    asset_class = classify_asset(instance)
    report = new_report(pack, str(meta.get("instance_id") or pack.name), province, asset_class)
    report["summary_file"] = relpath(summary_path) if summary_path else None
    add(report, "instance.file", "pass", f"读取实例：{relpath(instance_path)}")
    add(report, "instance.asset", "pass", f"资产类型：{ASSET_LABELS.get(asset_class, asset_class)}")
    if summary_error is not None:
        add(
            report,
            "summary.file",
            "warn",
            f"summary 无法读取，已忽略并改用实例日期兜底：{summary_error}",
        )
    if entry and entry.get("province") and entry.get("province") != province:
        add(
            report,
            "instance.manifest",
            "warn",
            f"清单省份 {entry.get('province')} 与实例 meta.province {province} 不一致",
        )

    if as_of is not None:
        target = as_of
        source = "命令行 --as-of"
    else:
        target = parse_date((summary or {}).get("trading_day"))
        source = "summary.trading_day"
        if target is None:
            target = parse_date(manifest_day)
            source = "组合清单 trading_day"
        if target is None:
            target = parse_date(meta.get("data_cutoff"))
            source = "meta.data_cutoff"
        if target is None:
            target = now
            source = "当前日期"
    report["target_date"] = target.isoformat()
    report["target_source"] = source
    add(report, "target.date", "pass", f"目标交易日：{target.isoformat()}（{source}）")

    rule_name = PROVINCE_RULE_FILES.get(province)
    rule_path = None
    rule = None
    if rule_name:
        rule_path = Path(rules_dir) / rule_name
        if rule_path.is_file():
            try:
                rule = load_json(rule_path)
            except (OSError, json.JSONDecodeError) as error:
                add(report, "rule.file", "block", f"规则包无法读取：{error}")
        else:
            add(report, "rule.file", "block", f"缺少规则文件：{relpath(rule_path)}")
    else:
        add(report, "rule.file", "block", f"未登记 {province} 的规则包映射")
    if rule is None:
        return finish(report)

    i_spot_probe, _ = normalize_spot(instance)
    is_spot_bidder = i_spot_probe is not None and asset_class in SPOT_ASSETS
    if not check_rule_package(
        report,
        rule,
        rule_path,
        province,
        target,
        now,
        has_spot_config=i_spot_probe is not None,
        is_spot_bidder=is_spot_bidder,
    ):
        return finish(report)
    report["open_items"] = list(rule.get("open_items") or [])

    r_spot = rule.get("spot") or {}
    check_spot_config(report, instance, r_spot)
    check_thermal_config(report, instance, rule)
    check_storage_config(report, instance, rule)
    check_capacity(report, instance, rule, summary, target)
    check_ancillary(report, instance, rule)
    check_deviation(report, rule)
    check_retail(report, instance, rule, target)
    check_direct(report, instance, rule, summary, target)
    check_interprovincial(report, instance, rule, target)

    if bid_override:
        bid_path = resolve(bid_override)
    else:
        bid_path = find_bid(pack, summary_path)
    check_bid(report, pack, bid_path, instance, rule, r_spot, target, explicit=bid_required)
    return finish(report)


def md(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def build_markdown(result):
    reports = result["instances"]
    totals = result["summary"]
    lines = [
        "# 省级规则包 · 申报前校验",
        "",
        f"生成时间：{result['generated_at']}  ",
        f"校验日期：{result['now']}  ",
        f"范围：{totals['instances']} 个实例包，覆盖 {totals['provinces']} 个省级市场  ",
        f"结论：BLOCK {totals['block']} 个 · WARN {totals['warn']} 个 · PASS {totals['pass']} 个",
        "",
        "判定语义：`block` 必须修正后再报；`warn` 需人工确认；`pass` 已检查无问题；"
        "`skip` 该实例不适用。规则包中的 B/C、C/D 与“待核实”标记不会因本工具通过而升级。",
        "",
        "## 总览",
        "",
        "| 实例 | 省 | 资产 | 目标交易日 | 规则包 | 结论 | block | warn | pass | skip |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for report in reports:
        rule_file = report.get("rule_file") or "缺失"
        lines.append(
            f"| {md(report['instance_id'])} | {md(report['province'])} | {md(report['asset_label'])} | "
            f"{md(report['target_date'] or '-')} | {md(rule_file)} | **{STATUS_LABELS[report['status']]}** | "
            f"{report['counts']['block']} | {report['counts']['warn']} | {report['counts']['pass']} | {report['counts']['skip']} |"
        )
    lines.append("")
    lines.append(
        f"合计检查 {totals['checks']} 项：pass {totals['check_counts']['pass']} · "
        f"warn {totals['check_counts']['warn']} · block {totals['check_counts']['block']} · "
        f"skip {totals['check_counts']['skip']}。"
    )
    lines.append("")

    for report in reports:
        lines.extend(
            [
                f"## {md(report['province'])} · {md(report['instance_id'])}",
                "",
                f"**结论：{STATUS_LABELS[report['status']]}**（block {report['counts']['block']} / "
                f"warn {report['counts']['warn']} / pass {report['counts']['pass']} / skip {report['counts']['skip']}）",
                "",
                f"- 资产：{md(report['asset_label'])}",
                f"- 实例路径：`{md(report['path'])}`",
                f"- 目标交易日：{md(report['target_date'] or '-')}（{md(report['target_source'] or '-')}）",
                f"- 规则包：`{md(report.get('rule_file') or '缺失')}`",
                f"- 待核项：{len(report.get('open_items') or [])} 条",
                "",
                "| 级别 | 校验 | 说明 |",
                "| --- | --- | --- |",
            ]
        )
        for check in report["checks"]:
            lines.append(
                f"| {STATUS_LABELS[check['level']]} | {md(check['id'])} | {md(check['message'])} |"
            )
        lines.append("")

    lines.extend(["## 规则包未闭合项", ""])
    by_rule = {}
    for report in reports:
        key = report.get("rule_file") or report["province"]
        bucket = by_rule.setdefault(key, {"province": report["province"], "items": []})
        for item in report.get("open_items") or []:
            if item not in bucket["items"]:
                bucket["items"].append(item)
    if not by_rule:
        lines.append("无。")
    else:
        for rule_file, bucket in by_rule.items():
            lines.append(f"### {md(bucket['province'])} · `{md(rule_file)}`")
            lines.append("")
            for item in bucket["items"]:
                lines.append(f"- {md(item)}")
            lines.append("")

    lines.extend(
        [
            "## 边界",
            "",
            "- 本报告只读本地规则包、实例配置、summary 和申报 CSV，不连接交易系统，不提交报价。",
            "- 申报限价为“已核到”的省级口径；草案、未核实和模型边界只降级为 warn，不会被静默当作硬规则。",
            "- SOC 为近似校核：按 energy_mwh、RTE 平方根和申报充放电量逐点估算，实际以 BMS/PCS 与交易中心结果为准。",
            "- 所有实例与数据均为 D 级合成样板；规则包不能替代交易中心最新公告、合同和结算单。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_result(reports, now, scope):
    check_counts = {level: 0 for level in LEVELS}
    for report in reports:
        for level in LEVELS:
            check_counts[level] += report["counts"][level]
    status_counts = {level: 0 for level in ("pass", "warn", "block")}
    for report in reports:
        status_counts[report["status"]] += 1
    provinces = {report["province"] for report in reports}
    return {
        "tool": "rulecheck",
        "version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "now": now.isoformat(),
        "scope": scope,
        "summary": {
            "instances": len(reports),
            "provinces": len(provinces),
            "checks": sum(check_counts.values()),
            "check_counts": check_counts,
            "pass": status_counts["pass"],
            "warn": status_counts["warn"],
            "block": status_counts["block"],
        },
        "instances": reports,
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="省级规则包 · 申报前校验（只读，不提交报价）",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--instance", help="单个实例包目录或 instance.json")
    group.add_argument("--demo", action="store_true", help="扫描组合清单中的 12 个实例包")
    parser.add_argument("--bid", help="单实例校验时指定申报 CSV")
    parser.add_argument("--rules-dir", default=str(DEFAULT_RULES_DIR), help="规则包目录")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    parser.add_argument("--as-of", help="统一覆盖目标交易日（YYYY-MM-DD）")
    parser.add_argument("--now", help="校验基准日（YYYY-MM-DD），默认今天")
    parser.add_argument("--manifest", help="组合清单路径；--demo 时使用")
    parser.add_argument("--strict", action="store_true", help="把 warn 也视为失败退出码")
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    if args.demo and args.bid:
        print("错误：--bid 只能与 --instance 一起使用")
        return 2
    if args.instance and args.manifest:
        print("错误：--manifest 只能与 --demo 一起使用")
        return 2
    now = parse_date(args.now) if args.now else date.today()
    if now is None:
        print("错误：--now 不是有效日期")
        return 2
    as_of = parse_date(args.as_of) if args.as_of else None
    if args.as_of and as_of is None:
        print("错误：--as-of 不是有效日期")
        return 2
    rules_dir = resolve(args.rules_dir)
    if not rules_dir.is_dir():
        print(f"错误：规则包目录不存在：{rules_dir}")
        return 2

    reports = []
    if args.demo:
        manifest_path = resolve(args.manifest) if args.manifest else DEFAULT_MANIFEST
        try:
            manifest = load_json(manifest_path)
        except (OSError, json.JSONDecodeError) as error:
            print(f"错误：组合清单无法读取：{error}")
            return 2
        packs = manifest.get("packs") or []
        manifest_day = manifest.get("trading_day")
        for entry in packs:
            report = evaluate(
                entry.get("path"),
                rules_dir,
                as_of,
                now,
                manifest_day=manifest_day,
                entry=entry,
            )
            reports.append(report)
        scope = f"demo:{relpath(manifest_path)}"
    else:
        report = evaluate(
            args.instance,
            rules_dir,
            as_of,
            now,
            bid_override=args.bid,
            bid_required=bool(args.bid),
        )
        reports.append(report)
        scope = f"instance:{report['instance_id']}"

    result = build_result(reports, now, scope)
    out_dir = resolve(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "rulecheck.json"
    md_path = out_dir / "rulecheck.md"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    md_path.write_text(build_markdown(result), encoding="utf-8")

    for report in reports:
        print(
            f"[{STATUS_LABELS[report['status']]}] {report['province']} · {report['instance_id']} "
            f"(block {report['counts']['block']}, warn {report['counts']['warn']}, pass {report['counts']['pass']})"
        )
    summary = result["summary"]
    print(
        f"\n规则包校验：{summary['instances']} 个实例，{summary['provinces']} 个省级市场；"
        f"BLOCK {summary['block']} · WARN {summary['warn']} · PASS {summary['pass']}"
    )
    print(f"报告：{md_path}")
    print(f"明细：{json_path}")

    if summary["block"]:
        return 1
    if args.strict and summary["warn"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
