"""Trading-desk portfolio view: read pack outputs, never trade.

This module turns heterogeneous instance-pack artefacts into one normalized
record per pack and aggregates them into a one-page morning brief.

Design constraints:

* read-only: it only reads ``summary.json`` and an adjacent ``bridge.json``;
  it never imports a pack runner, connects to a market or places an order;
* no imputation: a missing actual, CVaR or benchmark stays ``None`` and is
  rendered as ``N/A`` in the brief, never as zero;
* no cross-caliber totals: net margin, revenue, annual profit and savings are
  aggregated in separate groups. A "portfolio total" that adds unlike calibers
  is worse than no total;
* CVaR is a simple sum of standalone CVaRs. It is not a joint portfolio CVaR,
  because the packs share no scenario copula;
* weights: a manifest ``share`` scales monetary totals and CVaR (ownership
  share). The per-pack table still shows the asset's full-size value.

CLI::

    python tools/portfolio.py --demo --out out/portfolio-demo
    python tools/portfolio.py --manifest portfolio.json --out out/portfolio

The manifest is a configuration layer, not a new instance pack. See
``instances/portfolio-demo-2026-11.json`` for the 12-pack trading set.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_MANIFEST = REPO_ROOT / "skills/electricity-trading-expert/instances/portfolio-demo-2026-11.json"

VALUE_LABELS = {
    "net_margin": "交易净收益",
    "revenue": "收入",
    "profit": "利润",
    "saving": "相对基准节省",
    "none": "无可比金额",
}
KIND_LABELS = {
    "hedge": "中长期对冲",
    "capacity": "容量+辅助服务",
    "interprovincial": "省间外送",
    "spot_thermal": "现货煤电",
    "spot_storage": "现货储能",
    "spot_pv_storage": "现货光储",
    "spot_wind": "现货风电",
    "retail": "零售组合",
    "direct": "绿电直连",
    "spot": "现货",
}
HORIZON_LABELS = {"daily": "日度", "annual": "年度/月度", "period": "期间"}

ENERGY_PAIRS = (
    ("plan.forecast_energy_mwh", "actual.output_energy_mwh", "预测/实际发电量"),
    ("plan.declared_net_export_mwh", "actual.export_mwh", "申报/实际上网电量"),
    ("plan.declared_energy_mwh", "actual.energy_mwh", "申报/实际发电量"),
    ("plan.expected_energy_mwh", "actual.energy_mwh", "预期/实际发电量"),
    ("plan.energy_mwh", "bridge.actual_energy_mwh", "计划/实际电量"),
    ("plan.discharge_mwh", "actual.discharge_energy_mwh", "计划/实际放电量"),
    ("plan.output_mwh", None, "计划发电量"),
    ("base.generation_mwh", None, "年度发电量"),
    ("volumes.generation_mwh", None, "年度发电量"),
    ("totals.generation_mwh", None, "年度发电量"),
    ("plan.throughput_mwh", "bridge.actual_throughput_mwh", "计划/实际吞吐量"),
)


def dig(data, path):
    """Return a dotted-path value from nested dicts, or ``None``."""
    if data is None:
        return None
    node = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def first(*values):
    """Return the first value that is not ``None`` (zero is valid)."""
    for value in values:
        if value is not None:
            return value
    return None


def first_path(data, *paths):
    for path in paths:
        value = dig(data, path)
        if value is not None:
            return value
    return None


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_summary(pack_dir, entry):
    """Locate the summary for a manifest entry without guessing data."""
    pack_dir = Path(pack_dir)
    explicit = entry.get("summary")
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        if not candidate.exists():
            raise FileNotFoundError(f"summary not found: {candidate}")
        return candidate
    if pack_dir.is_file():
        return pack_dir
    candidates = sorted(
        pack_dir.glob("out/**/summary.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no summary.json under {pack_dir}")
    return candidates[0]


def load_bridge(summary, summary_path):
    """Read the bridge named in the summary, or an adjacent ``bridge.json``."""
    if not summary_path:
        return None
    name = dig(summary, "files.bridge")
    candidates = []
    if name:
        candidates.append(Path(summary_path).parent / name)
    candidates.append(Path(summary_path).parent / "bridge.json")
    for candidate in candidates:
        if candidate.exists():
            return read_json(candidate)
    return None


def infer_kind(summary, instance_id):
    if "economics" in summary and "totals" in summary:
        return "direct"
    if "pricing" in summary and "plan" in summary:
        return "retail"
    if "base" in summary and "modes" in summary:
        return "capacity"
    if "strategies" in summary and "volumes" in summary and "prices" in summary:
        return "interprovincial"
    if "book" in summary and "plan" in summary:
        return "hedge"
    if "selected_strategy" in summary or "selected" in summary:
        return "spot_wind" if "wind" in instance_id else "spot"
    if "storage" in instance_id:
        return "spot_storage"
    if "pv" in instance_id or "solar" in instance_id:
        return "spot_pv_storage"
    if "wind" in instance_id:
        return "spot_wind"
    if "thermal" in instance_id:
        return "spot_thermal"
    return "spot"


def infer_province(instance_id):
    for key, name in (
        ("shandong", "山东"),
        ("gansu", "甘肃"),
        ("mengxi", "蒙西"),
        ("shanxi", "山西"),
        ("guangdong", "广东"),
        ("jiangsu", "江苏"),
    ):
        if key in instance_id:
            return name
    return ""


def infer_value_kind(summary):
    if dig(summary, "economics.saving_cny") is not None:
        return "saving"
    if dig(summary, "base.profit_cny") is not None:
        return "profit"
    if (
        dig(summary, "plan.expected_revenue_cny") is not None
        or dig(summary, "plan.reference_revenue_cny") is not None
        or dig(summary, "bridge.plan_revenue_cny") is not None
    ):
        return "revenue"
    if any(item.get("total_revenue_cny") is not None for item in summary.get("strategies", [])):
        return "revenue"
    if (
        dig(summary, "plan.expected_net_margin_cny") is not None
        or dig(summary, "selected.expected_net_margin_cny") is not None
        or dig(summary, "scenarios.expected_net_cny") is not None
    ):
        return "net_margin"
    return "none"


def best_strategy_revenue(summary):
    rows = [item for item in summary.get("strategies", []) if item.get("total_revenue_cny") is not None]
    if not rows:
        return None
    return max(rows, key=lambda item: item["total_revenue_cny"])


def local_only_revenue(summary):
    for item in summary.get("strategies", []):
        if item.get("strategy") == "local_only":
            return item
    return None


def energy_pair(summary, bridge):
    """Pick a plan/actual capacity pair from the same semantic family."""
    plan_only = None
    for plan_path, actual_path, label in ENERGY_PAIRS:
        plan_value = dig(summary, plan_path)
        if plan_value is None:
            continue
        actual_value = None
        if actual_path:
            if actual_path.startswith("bridge."):
                actual_value = dig(bridge, actual_path[len("bridge."):])
            else:
                actual_value = dig(summary, actual_path)
        if actual_value is not None:
            return plan_value, actual_value, label
        if plan_only is None:
            plan_only = (plan_value, None, label)
    # Storage summaries expose charge and discharge separately, while the
    # bridge reconciles throughput. Use throughput only when both sides exist.
    plan_charge = dig(summary, "plan.charge_mwh")
    plan_discharge = dig(summary, "plan.discharge_mwh")
    actual_throughput = dig(bridge, "actual_throughput_mwh")
    if plan_charge is not None and plan_discharge is not None and actual_throughput is not None:
        return plan_charge + plan_discharge, actual_throughput, "计划/实际吞吐量"
    if plan_only:
        return plan_only
    return None, None, ""


def constraint_record(summary):
    """Return a cap-utilisation record for limits the pack itself declares."""
    policy = summary.get("policy") or {}
    plan = summary.get("plan") or {}
    cycles = first(plan.get("equivalent_cycles"), plan.get("cycles"))
    max_cycles = policy.get("max_cycles_per_day")
    if cycles is not None and max_cycles:
        return {
            "label": "日循环/上限",
            "value": cycles,
            "limit": max_cycles,
            "utilization": cycles / max_cycles if max_cycles else None,
        }
    hedge_ratio = plan.get("hedge_ratio")
    max_hedge = policy.get("max_hedge_ratio")
    if hedge_ratio is not None and max_hedge:
        return {
            "label": "对冲比例/上限",
            "value": hedge_ratio,
            "limit": max_hedge,
            "utilization": hedge_ratio / max_hedge if max_hedge else None,
        }
    declared = dig(summary, "asset.declared_capacity_mw")
    nameplate = dig(summary, "asset.nameplate_capacity_mw")
    if declared is not None and nameplate:
        return {
            "label": "申报容量/铭牌",
            "value": declared,
            "limit": nameplate,
            "utilization": declared / nameplate if nameplate else None,
        }
    return None


def normalize_summary(summary, bridge=None, entry=None, summary_path=None):
    """Normalize one pack summary into a comparable record."""
    entry = entry or {}
    meta = summary.get("meta") or {}
    policy = summary.get("policy") or {}
    config = summary.get("config") or {}
    plan = summary.get("plan") or {}
    actual = summary.get("actual") or {}
    selected = summary.get("selected") or {}
    scenarios = summary.get("scenarios") or {}
    bridge = bridge or {}

    if summary_path:
        summary_dir = Path(summary_path).parent
        if summary_dir.name == "demo" or summary_dir.parent.name == "out":
            path_instance = summary_dir.parent.parent.name
        else:
            path_instance = summary_dir.name
    else:
        path_instance = None
    instance_id = first(
        meta.get("instance_id"),
        summary.get("instance_id"),
        config.get("profile_id"),
        entry.get("instance_id"),
        path_instance,
        "unknown",
    )
    trading_day = first(summary.get("trading_day"), meta.get("trading_day"), entry.get("trading_day"))
    data_cutoff = first(summary.get("data_cutoff"), meta.get("data_cutoff"), entry.get("data_cutoff"))
    kind = entry.get("kind") or infer_kind(summary, str(instance_id))
    value_kind = entry.get("value_kind") or infer_value_kind(summary)
    horizon = entry.get("period") or ("daily" if trading_day else "annual")
    warnings = [str(item) for item in (summary.get("warnings") or [])]

    expected_paths = {
        "net_margin": (
            "plan.expected_net_margin_cny",
            "selected.expected_net_margin_cny",
            "scenarios.expected_net_cny",
        ),
        "revenue": (
            "plan.expected_revenue_cny",
            "selected.expected_revenue_cny",
        ),
        "saving": ("economics.saving_cny",),
        "profit": ("base.profit_cny", "plan.expected_profit_cny"),
    }
    if value_kind in expected_paths:
        expected = first_path(summary, *expected_paths[value_kind])
    else:
        expected = first_path(
            summary,
            "plan.expected_net_margin_cny",
            "selected.expected_net_margin_cny",
            "plan.expected_revenue_cny",
            "scenarios.expected_net_cny",
            "economics.saving_cny",
            "base.profit_cny",
        )
    if expected is None and value_kind in ("revenue", "none"):
        best = best_strategy_revenue(summary)
        expected = best.get("total_revenue_cny") if best else None

    reference_paths = {
        "net_margin": (
            "plan.reference_net_margin_cny",
            "plan.net_margin_at_reference_cny",
            "plan.net_cny",
            "selected.plan_net_margin_cny",
            "bridge.plan_net_cny",
        ),
        "revenue": (
            "plan.reference_revenue_cny",
            "bridge.plan_revenue_cny",
        ),
        "profit": (
            "plan.reference_profit_cny",
            "bridge.plan_profit",
        ),
    }
    if value_kind in reference_paths:
        reference = first_path(summary, *reference_paths[value_kind])
    else:
        reference = first_path(
            summary,
            "plan.reference_net_margin_cny",
            "plan.net_margin_at_reference_cny",
            "plan.reference_revenue_cny",
            "plan.net_cny",
            "selected.plan_net_margin_cny",
            "bridge.plan_profit",
            "bridge.plan_revenue_cny",
            "bridge.plan_net_cny",
        )
    if kind == "capacity" and summary.get("configured_default_profit_cny") is not None:
        reference = summary["configured_default_profit_cny"]
    if kind == "interprovincial":
        local = local_only_revenue(summary)
        if local is not None:
            reference = local.get("total_revenue_cny")
    if value_kind == "saving":
        reference = None

    if value_kind == "net_margin":
        actual_value = first(
            actual.get("net_margin_cny"),
            bridge.get("actual_net_cny"),
        )
    elif value_kind == "profit":
        actual_value = first(
            actual.get("profit_cny"),
            bridge.get("actual_profit"),
        )
    elif value_kind == "revenue":
        actual_value = first(
            actual.get("revenue_cny"),
            bridge.get("actual_revenue_cny"),
        )
    elif value_kind == "saving":
        actual_value = actual.get("saving_cny")
    else:
        actual_value = first(
            actual.get("saving_cny"),
            actual.get("net_margin_cny"),
            actual.get("profit_cny"),
            actual.get("revenue_cny"),
            bridge.get("actual_profit"),
            bridge.get("actual_net_cny"),
            bridge.get("actual_revenue_cny"),
        )
    cvar = first_path(
        summary,
        "plan.cvar_10_cny",
        "selected.cvar_cny",
        "plan.cvar_cny",
        "scenarios.cvar_10_cny",
    )
    plan_energy, actual_energy, energy_label = energy_pair(summary, bridge)

    if actual_value is not None and reference is not None:
        delta = actual_value - reference
    else:
        delta = None
    delta_vs_expected = (
        actual_value - expected if actual_value is not None and expected is not None else None
    )
    energy_deviation = (
        (actual_energy - plan_energy) / plan_energy
        if actual_energy is not None and plan_energy not in (None, 0)
        else None
    )
    cvar_hit = actual_value >= cvar if actual_value is not None and cvar is not None else None

    capture = first(actual.get("capture_cny_per_mwh"), summary.get("capture_cny_per_mwh"))
    capture_benchmark = first(
        plan.get("reference_capture_cny_per_mwh"),
        bridge.get("da_average_cny_per_mwh"),
    )
    realized_price = None
    da_price = first(actual.get("da_price_average_cny_per_mwh"), actual.get("da_energy_weighted_price_cny_per_mwh"))
    if actual.get("revenue_cny") is not None and actual.get("output_energy_mwh"):
        realized_price = actual["revenue_cny"] / actual["output_energy_mwh"]

    share = entry.get("share", 1.0)
    try:
        share = float(share)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"share must be numeric for {instance_id}: {share!r}") from exc
    if not 0 <= share <= 1:
        raise ValueError(f"share must be within 0..1 for {instance_id}: {share}")

    gaps = []
    if actual_value is None:
        gaps.append("无实际值")
    if cvar is None:
        gaps.append("无 CVaR")
    if bridge.get("identity_gap") is None:
        gaps.append("无差异桥闭合校验")
    if plan_energy is None:
        gaps.append("无电量口径")

    return {
        "instance_id": instance_id,
        "label": entry.get("label") or instance_id,
        "province": first(meta.get("province"), summary.get("province"), entry.get("province"), infer_province(str(instance_id))),
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "role": entry.get("role") or "",
        "horizon": horizon,
        "trading_day": trading_day or "",
        "as_of": data_cutoff or "",
        "data_cutoff": data_cutoff or "",
        "rule_version": first(meta.get("rule_version"), summary.get("rule_version"), ""),
        "policy_id": first(policy.get("profile_id"), config.get("profile_id"), ""),
        "fingerprint": first(summary.get("policy_fingerprint"), summary.get("fingerprint"), ""),
        "grade": first(meta.get("grade"), policy.get("grade"), entry.get("grade"), ""),
        "value_kind": value_kind,
        "value_label": VALUE_LABELS.get(value_kind, value_kind),
        "expected_cny": expected,
        "reference_cny": reference,
        "actual_cny": actual_value,
        "delta_cny": delta,
        "delta_vs_expected_cny": delta_vs_expected,
        "cvar_cny": cvar,
        "cvar_hit": cvar_hit,
        "plan_energy_mwh": plan_energy,
        "actual_energy_mwh": actual_energy,
        "energy_label": energy_label,
        "energy_deviation": energy_deviation,
        "capture_cny_per_mwh": capture,
        "capture_benchmark_cny_per_mwh": capture_benchmark,
        "capture_ratio": (capture / capture_benchmark) if capture is not None and capture_benchmark not in (None, 0) else None,
        "realized_price_cny_per_mwh": realized_price,
        "da_price_cny_per_mwh": da_price,
        "carry_cny": plan.get("carry_cny"),
        "shape_cny": plan.get("shape_cny"),
        "hedge_value_cny": plan.get("expected_hedge_value_cny"),
        "hedge_value_reference_cny": plan.get("reference_hedge_value_cny"),
        "hedge_value_gap": plan.get("hedge_value_identity_gap"),
        "hedge_ratio_plan": plan.get("hedge_ratio"),
        "hedge_ratio_actual": actual.get("hedge_ratio"),
        "hedge_ratio_target": first(plan.get("target_hedge_ratio"), policy.get("target_hedge_ratio")),
        "assessment_cny": first(
            actual.get("assessment_cny"),
            actual.get("deviation_penalty_cny"),
            bridge.get("actual_deviation_cny"),
        ),
        "allocation_cny": first(plan.get("allocation_cost_cny"), summary.get("allocation_cny")),
        "constraint": constraint_record(summary),
        "warning_count": len(warnings),
        "warnings": warnings,
        "bridge_gap_abs": abs(bridge["identity_gap"]) if bridge.get("identity_gap") is not None else None,
        "share": share,
        "status": "ok" if actual_value is not None else "model_only",
        "data_gaps": gaps,
        "summary_path": str(summary_path) if summary_path else "",
    }


def load_entry(entry):
    """Load and normalize one manifest entry."""
    if not entry.get("path"):
        raise ValueError("manifest entry is missing 'path'")
    pack_path = Path(entry["path"])
    if not pack_path.is_absolute():
        pack_path = REPO_ROOT / pack_path
    if not pack_path.exists():
        raise FileNotFoundError(f"pack not found: {pack_path}")
    summary_path = find_summary(pack_path, entry)
    summary = read_json(summary_path)
    bridge = load_bridge(summary, summary_path)
    record = normalize_summary(summary, bridge=bridge, entry=entry, summary_path=summary_path)
    record["pack_path"] = str(pack_path)
    return record


def _sum(records, field):
    values = [record[field] * record["share"] for record in records if record.get(field) is not None]
    return sum(values) if values else None


def _matched_stats(items):
    actual_items = [item for item in items if item.get("actual_cny") is not None]
    delta_items = [
        item
        for item in actual_items
        if item.get("actual_cny") is not None and item.get("reference_cny") is not None
    ]
    matched_reference = _sum(delta_items, "reference_cny")
    matched_actual = _sum(delta_items, "actual_cny")
    delta = (
        matched_actual - matched_reference
        if matched_actual is not None and matched_reference is not None
        else None
    )
    return {
        "actual_packs": len(actual_items),
        "delta_packs": len(delta_items),
        "matched_expected_cny": _sum(actual_items, "expected_cny"),
        "matched_reference_cny": matched_reference,
        "matched_actual_cny": matched_actual,
        "delta_cny": delta,
        "delta_pct": delta / abs(matched_reference) if delta is not None and matched_reference else None,
    }


def group_key(record):
    # A daily total across different trading days is not a portfolio total.
    day = record["trading_day"] if record["horizon"] == "daily" else ""
    return record["horizon"], record["value_kind"], day


def aggregate(records):
    """Aggregate by (horizon, value kind, trading day); never mix calibers."""
    groups = {}
    for record in records:
        key = group_key(record)
        groups.setdefault(key, []).append(record)
    rows = []
    for (horizon, value_kind, day), items in sorted(groups.items()):
        reference = _sum(items, "reference_cny")
        actual = _sum(items, "actual_cny")
        matched = _matched_stats(items)
        period = day or HORIZON_LABELS.get(horizon, horizon)
        rows.append(
            {
                "horizon": horizon,
                "trading_day": day,
                "period_label": period,
                "value_kind": value_kind,
                "label": f"{period}·{VALUE_LABELS.get(value_kind, value_kind)}",
                "packs": len(items),
                "actual_packs": matched["actual_packs"],
                "delta_packs": matched["delta_packs"],
                "matched_expected_cny": matched["matched_expected_cny"],
                "matched_reference_cny": matched["matched_reference_cny"],
                "matched_actual_cny": matched["matched_actual_cny"],
                "cvar_packs": sum(1 for item in items if item["cvar_cny"] is not None),
                "expected_cny": _sum(items, "expected_cny"),
                "reference_cny": reference,
                "actual_cny": actual,
                "delta_cny": matched["delta_cny"],
                "delta_pct": matched["delta_pct"],
                "cvar_cny": _sum(items, "cvar_cny"),
                "assessment_cny": _sum(items, "assessment_cny"),
                "warning_count": sum(item["warning_count"] for item in items),
                "bridge_gap_max": max(
                    (item["bridge_gap_abs"] for item in items if item["bridge_gap_abs"] is not None),
                    default=None,
                ),
            }
        )
    return rows


def fmt_money(value):
    if value is None:
        return "N/A"
    digits = 1 if abs(value) >= 100_000 else 2
    return f"{value / 10000:,.{digits}f} 万"


def fmt_pct(value):
    if value is None:
        return "N/A"
    return f"{value * 100:+.1f}%"


def fmt_num(value, digits=1):
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}"


def md_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def build_brief(records, groups, title="交易台总盘简报", as_of=None, focus_trading_day=None):
    """Render the one-page brief."""
    daily_net_groups = [
        row for row in groups if row["horizon"] == "daily" and row["value_kind"] == "net_margin"
    ]
    daily_revenue_groups = [
        row for row in groups if row["horizon"] == "daily" and row["value_kind"] == "revenue"
    ]
    daily_days = sorted({record["trading_day"] for record in records if record["horizon"] == "daily" and record["trading_day"]})
    focus = focus_trading_day or (daily_days[-1] if daily_days else None)
    focus_net = next((row for row in daily_net_groups if row["trading_day"] == focus), None)
    focus_revenue = next((row for row in daily_revenue_groups if row["trading_day"] == focus), None)
    # 焦点日没有净收益组时，上方会逐日列出全部净收益组，避免在“其他交易日”重复
    other_net = [row for row in daily_net_groups if row != focus_net] if focus_net else []
    other_revenue = [row for row in daily_revenue_groups if row != focus_revenue]
    cutoffs = sorted({record["data_cutoff"] for record in records if record["data_cutoff"]})

    def group_sentence(row):
        expected = fmt_money(row["expected_cny"])
        reference = fmt_money(row["reference_cny"])
        if row["actual_packs"] == 0:
            return f"全口径预期 {expected}，全口径基准 {reference}；实际 N/A（0 个主体有实际值）。"
        if row["actual_packs"] == row["packs"] and row["delta_packs"] == row["packs"]:
            return (
                f"预期 {expected}，基准 {reference}，实际 {fmt_money(row['actual_cny'])}，"
                f"实际−基准 {fmt_money(row['delta_cny'])}（{fmt_pct(row['delta_pct'])}）。"
            )
        return (
            f"全口径预期 {expected}，全口径基准 {reference}；有实际值 {row['actual_packs']} 个主体，"
            f"其中 {row['delta_packs']} 个有可比基准：可比基准 {fmt_money(row['matched_reference_cny'])}，"
            f"对应实际 {fmt_money(row['matched_actual_cny'])}，实际−基准 {fmt_money(row['delta_cny'])}"
            f"（{fmt_pct(row['delta_pct'])}）。"
        )

    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"> 组合：{title}｜实例：{len(records)} 个｜数据截止：{as_of or (cutoffs[-1] if cutoffs else 'N/A')}"
        f"｜焦点交易日：{focus or 'N/A'}｜日度交易日：{daily_days[0] + ' ~ ' + daily_days[-1] if daily_days else 'N/A'}"
    )
    lines.append("> **D 级合成数据，仅用于方法演示，不构成交易建议。** 工具只读实例包产物，不连接实盘、不报价、不下单，也不替代交易中心结算。")
    lines.append("")
    lines.append("## 一、结论先行")
    lines.append("")
    if len(daily_days) > 1:
        lines.append(
            f"- **本批次含 {len(daily_days)} 个交易日（{daily_days[0]} ~ {daily_days[-1]}）**：以下按交易日分列，"
            "不同交易日的金额不相加；焦点日只代表当日总盘。"
        )
    if focus_net:
        lines.append(
            f"- **焦点日 {focus} 交易净收益（{focus_net['packs']} 个主体，{focus_net['actual_packs']} 个有实际值）**："
            f"{group_sentence(focus_net)}"
        )
        lines.append(
            f"- **风险**：{focus} 日度净收益组 CVaR 简单加总 {fmt_money(focus_net['cvar_cny'])}"
            "（组内全部主体，含无实际值）；"
            "这是各主体 10% 分位的简单相加，不是联合 CVaR（各包情景不共享相关性）。"
        )
    elif daily_net_groups:
        for row in daily_net_groups:
            lines.append(
                f"- **{row['trading_day']} 交易净收益（{row['packs']} 个主体，{row['actual_packs']} 个有实际值）**："
                f"{group_sentence(row)}"
            )
    else:
        lines.append("- 本批次没有可比的日度交易净收益组；请检查清单中的 `period` 与实例产物。")
    if focus_revenue:
        lines.append(
            f"- **焦点日 {focus} 收入口径（{focus_revenue['packs']} 个主体，{focus_revenue['actual_packs']} 个有实际值）**："
            f"{group_sentence(focus_revenue)}收入不等于净收益，不与上一行相加。"
        )
    if other_net or other_revenue:
        parts = []
        for row in other_net + other_revenue:
            parts.append(
                f"{row['trading_day']} {VALUE_LABELS.get(row['value_kind'], row['value_kind'])} "
                f"实际 {fmt_money(row['actual_cny'])}（{row['packs']} 个主体）"
            )
        lines.append("- **其他交易日（不并入焦点日）**：" + "；".join(parts) + "。")
    other_groups = [row for row in groups if row["horizon"] != "daily"]
    if other_groups:
        parts = []
        for row in other_groups:
            parts.append(
                f"{row['label']} {fmt_money(row['actual_cny'] if row['actual_cny'] is not None else row['expected_cny'])}"
                f"（{'实际' if row['actual_cny'] is not None else '预期'}）"
            )
        lines.append("- **年度/月度口径（单独列示，不并入日度净收益）**：" + "；".join(parts) + "。")
    gaps = [record for record in records if record["status"] != "ok"]
    warnings_total = sum(record["warning_count"] for record in records)
    if gaps:
        lines.append(
            f"- **数据缺口**：{len(gaps)} 个主体无实际值（"
            + "、".join(record["label"] for record in gaps[:6])
            + (" 等" if len(gaps) > 6 else "")
            + "）；这些行的实际值保持 N/A，没有用 0 或模型值回填。"
        )
    if warnings_total:
        lines.append(f"- **预警**：本批次共 {warnings_total} 条，详见第五节；先处理数据与口径问题，再谈策略优劣。")
    lines.append("")
    lines.append("## 二、分口径总盘")
    lines.append("")
    lines.append("金额单位：万元；日度按交易日落行，CVaR 为组内各主体独立 CVaR 的简单加总（含无实际值主体）。")
    lines.append("")
    lines.append("| 周期 | 口径 | 主体 | 有实际/可比 | 预期 | 基准 | 可比基准 | 实际 | 实际−基准 | 差异% | CVaR 简单加总 | 预警 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in groups:
        lines.append(
            f"| {md_cell(row['period_label'])} | {md_cell(VALUE_LABELS.get(row['value_kind'], row['value_kind']))} | "
            f"{row['packs']} | {row['actual_packs']}/{row['delta_packs']} | "
            f"{fmt_money(row['expected_cny'])} | {fmt_money(row['reference_cny'])} | "
            f"{fmt_money(row['matched_reference_cny'])} | {fmt_money(row['actual_cny'])} | "
            f"{fmt_money(row['delta_cny'])} | {fmt_pct(row['delta_pct'])} | {fmt_money(row['cvar_cny'])} | {row['warning_count']} |"
        )
    lines.append("")
    lines.append(
        "“可比基准”只汇总同时有实际值和基准的主体；“实际−基准”与差异%只在这组主体内计算，"
        "不能拿全口径基准与部分实际值相减。“实际”列为组内全部有实际值主体，"
        "可能大于“可比”样本，不可直接与“可比基准”相减。"
    )
    lines.append("")
    lines.append("## 三、分主体")
    lines.append("")
    lines.append("金额单位：万元；“实际−基准”只采用包内差异桥/参考计划，缺少基准时写 N/A，不用预期值替代；实际−预期见 `portfolio.csv` 的 `delta_vs_expected_cny`。")
    lines.append("")
    lines.append("| 主体 | 省 | 类型 | 口径 | 交易日 | 预期 | 基准 | 实际 | 实际−基准 | 差异% | CVaR | 电量偏差 | 限额利用 | 预警 |")
    lines.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for record in sorted(records, key=lambda item: (item["horizon"], item["trading_day"], item["value_kind"], item["label"])):
        delta_pct = (
            record["delta_cny"] / abs(record["reference_cny"])
            if record["delta_cny"] is not None and record["reference_cny"] not in (None, 0)
            else None
        )
        constraint = record["constraint"]
        if constraint and constraint.get("utilization") is not None:
            limit_text = f"{constraint['label']} {constraint['utilization'] * 100:.0f}%"
        else:
            limit_text = "N/A"
        lines.append(
            f"| {md_cell(record['label'])} | {md_cell(record['province'])} | {md_cell(record['kind_label'])} | "
            f"{md_cell(record['value_label'])} | {md_cell(record['trading_day'] or '年度/月度')} | {fmt_money(record['expected_cny'])} | {fmt_money(record['reference_cny'])} | "
            f"{fmt_money(record['actual_cny'])} | {fmt_money(record['delta_cny'])} | {fmt_pct(delta_pct)} | "
            f"{fmt_money(record['cvar_cny'])} | {fmt_pct(record['energy_deviation'])} | {limit_text} | "
            f"{record['warning_count']} |"
        )
    lines.append("")
    lines.append(f"## 四、分省与分类型（{focus or '最新交易日'} 日度交易净收益）")
    lines.append("")
    lines.append("不同口径不可相加；本节只统计焦点日的日度 `net_margin`，用于回答“哪个省/哪类资产在拖累当日净收益”。")
    lines.append("")
    daily_margin_records = [
        record
        for record in records
        if record["horizon"] == "daily"
        and record["value_kind"] == "net_margin"
        and record["trading_day"] == focus
    ]
    for dimension, attr in (("分省", "province"), ("分类型", "kind_label")):
        lines.append(f"**{dimension}**")
        lines.append("")
        lines.append("| 维度 | 主体 | 有实际 | 可比 | 可比基准 | 实际−基准 | 差异% | 预警 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        buckets = {}
        for record in daily_margin_records:
            buckets.setdefault(record[attr] or "未标注", []).append(record)
        for name, items in sorted(buckets.items()):
            matched = _matched_stats(items)
            lines.append(
                f"| {md_cell(name)} | {len(items)} | {matched['actual_packs']} | {matched['delta_packs']} | "
                f"{fmt_money(matched['matched_reference_cny'])} | {fmt_money(matched['delta_cny'])} | "
                f"{fmt_pct(matched['delta_pct'])} | {sum(item['warning_count'] for item in items)} |"
            )
        lines.append("")
    lines.append("## 五、数据缺口与预警")
    lines.append("")
    if gaps:
        lines.append("**无实际值（保持 N/A）**")
        lines.append("")
        for record in gaps:
            lines.append(f"- {record['label']}（{record['instance_id']}）：{'、'.join(record['data_gaps'])}。")
        lines.append("")
    stale = [record for record in records if record["data_cutoff"] and cutoffs and record["data_cutoff"] < cutoffs[-1]]
    if stale:
        lines.append("**数据截止早于组合最新截止**")
        lines.append("")
        for record in stale:
            lines.append(f"- {record['label']}：{record['data_cutoff']}，组合最新截止为 {cutoffs[-1]}；请确认是否需要刷新。")
        lines.append("")
    warning_items = []
    for record in records:
        for warning in record["warnings"]:
            warning_items.append((record["label"], warning))
    if warning_items:
        lines.append(f"**预警清单（共 {len(warning_items)} 条，按主体去重展示前 8 条）**")
        lines.append("")
        seen = set()
        shown = 0
        for label, warning in warning_items:
            key = warning[:80]
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {label}：{warning[:180]}{'…' if len(warning) > 180 else ''}")
            shown += 1
            if shown >= 8:
                break
        lines.append("")
    if not gaps and not warning_items and not stale:
        lines.append("- 未发现缺实际值、截止不一致或预警。")
        lines.append("")
    lines.append("## 六、口径与边界")
    lines.append("")
    lines.append("- **只读产物**：读取 `out/**/summary.json` 与同目录 `bridge.json`；不改实例包、不读实盘、不生成报价。")
    lines.append("- **不混口径**：日度净收益、收入、年度利润、相对基准节省分组统计；跨组相加会高估或低估真实表现。")
    lines.append("- **CVaR 简单加总**：仅用于量级提示；它假设各主体同时触及 10% 分位，未考虑相关性，不能当作公司级风险限额。")
    lines.append("- **缺失不补零**：实际值、CVaR、电量口径缺失时写 N/A，避免把模型值伪装成实际值。")
    lines.append("- **部分实际值**：组级“实际−基准”只在同时有实际值和基准的主体间计算；全口径基准不直接与部分实际值相减。")
    lines.append("- **份额**：清单中的 `share` 只缩放组合金额与 CVaR；分主体表仍显示资产全口径值。")
    lines.append("- **限额利用**：来自包内 `policy`/`asset` 的自报上限，是配置层而不是监管结论；真实限额以公司风险制度为准。")
    lines.append("- **可复现**：`portfolio_summary.json` 保存逐包归一化记录与分组汇总，`portfolio.csv` 可直接进表格复核。")
    lines.append("")
    return "\n".join(lines)


def write_csv(records, path):
    fields = [
        "instance_id",
        "label",
        "province",
        "kind",
        "role",
        "horizon",
        "trading_day",
        "data_cutoff",
        "value_kind",
        "expected_cny",
        "reference_cny",
        "actual_cny",
        "delta_cny",
        "delta_vs_expected_cny",
        "cvar_cny",
        "cvar_hit",
        "plan_energy_mwh",
        "actual_energy_mwh",
        "energy_deviation",
        "capture_cny_per_mwh",
        "capture_benchmark_cny_per_mwh",
        "capture_ratio",
        "assessment_cny",
        "allocation_cny",
        "carry_cny",
        "shape_cny",
        "hedge_value_cny",
        "hedge_value_reference_cny",
        "warning_count",
        "bridge_gap_abs",
        "share",
        "status",
        "summary_path",
    ]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def load_manifest(path):
    manifest_path = Path(path)
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path
    manifest = read_json(manifest_path)
    packs = manifest.get("packs")
    if not isinstance(packs, list) or not packs:
        raise ValueError(f"manifest must contain a non-empty 'packs' list: {manifest_path}")
    seen = set()
    for entry in packs:
        key = entry.get("path")
        if key in seen:
            raise ValueError(f"duplicate pack path in manifest: {key}")
        seen.add(key)
    return manifest, manifest_path


def build_portfolio(manifest, manifest_path=None, focus_trading_day=None):
    records = []
    errors = []
    for entry in manifest["packs"]:
        try:
            records.append(load_entry(entry))
        except Exception as exc:  # keep the rest of the desk visible
            errors.append({"path": entry.get("path"), "error": str(exc)})
    if not records:
        raise RuntimeError("no pack could be loaded; see errors")
    groups = aggregate(records)
    as_of = manifest.get("as_of")
    if not as_of:
        cutoffs = sorted({record["data_cutoff"] for record in records if record["data_cutoff"]})
        as_of = cutoffs[-1] if cutoffs else None
    daily_days = sorted({record["trading_day"] for record in records if record["horizon"] == "daily" and record["trading_day"]})
    focus = focus_trading_day or manifest.get("trading_day") or (daily_days[-1] if daily_days else None)
    if focus and daily_days and focus not in daily_days:
        raise ValueError(f"focus trading day {focus!r} is not in the loaded daily records: {', '.join(daily_days)}")
    title = manifest.get("name") or "交易台总盘简报"
    summary = {
        "name": title,
        "as_of": as_of,
        "focus_trading_day": focus,
        "daily_trading_days": daily_days,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest": str(manifest_path) if manifest_path else "",
        "pack_count": len(records),
        "error_count": len(errors),
        "errors": errors,
        "groups": groups,
        "records": records,
    }
    brief = build_brief(records, groups, title=title, as_of=as_of, focus_trading_day=focus)
    return summary, brief, errors


def write_outputs(summary, brief, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "portfolio_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "brief.md").write_text(brief, encoding="utf-8")
    write_csv(summary["records"], out / "portfolio.csv")
    return out


def run(manifest, out_dir, strict=False, focus_trading_day=None, manifest_path=None):
    summary, brief, errors = build_portfolio(
        manifest, manifest_path=manifest_path, focus_trading_day=focus_trading_day
    )
    out = write_outputs(summary, brief, out_dir)
    print(f"wrote {out / 'portfolio_summary.json'}")
    print(f"wrote {out / 'brief.md'}")
    print(f"wrote {out / 'portfolio.csv'}")
    for error in errors:
        print(f"error: {error['path']}: {error['error']}", file=sys.stderr)
    if strict and errors:
        raise SystemExit(1)
    return summary


def demo_manifest():
    manifest, _ = load_manifest(DEMO_MANIFEST)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read instance-pack outputs and build a trading-desk portfolio brief.")
    parser.add_argument("--manifest", help="portfolio manifest JSON; paths are relative to the repository root")
    parser.add_argument("--out", default="out/portfolio", help="output directory (default: out/portfolio)")
    parser.add_argument("--demo", action="store_true", help="use the shipped 12-pack demo manifest")
    parser.add_argument("--trading-day", help="focus day for the brief; defaults to the manifest's trading_day or the latest day")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any pack fails to load")
    args = parser.parse_args(argv)

    if args.demo:
        manifest, manifest_path = load_manifest(DEMO_MANIFEST)
    elif args.manifest:
        manifest, manifest_path = load_manifest(args.manifest)
    else:
        parser.error("pass --manifest PATH or --demo")
        return 2
    run(
        manifest,
        args.out,
        strict=args.strict,
        focus_trading_day=args.trading_day,
        manifest_path=manifest_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
