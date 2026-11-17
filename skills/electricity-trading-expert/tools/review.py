"""Monthly trading-quality scorecard from archived pack outputs.

The scorecard answers a narrow question: *did the desk execute the plan it had
on the table, and can the result be reconciled?* It is not a performance
attribution model and it does not grade a strategy on a single day.

Input convention::

    <archive>/2026-11-18/<instance-or-label>/summary.json
    <archive>/2026-11-18/<instance-or-label>/bridge.json   # optional

Any ``summary.json`` under the archive root is discovered recursively. The
directory name is used as the trading day only when the summary itself does not
provide one. Duplicate (instance, trading day) runs keep the newest file and
are reported, never silently summed.

KPIs are computed only where the underlying artefact exists. A missing forecast
or capture benchmark is rendered as ``N/A`` with an explicit sample count; it is
never imputed as zero. The desk thresholds in ``DEFAULT_THRESHOLDS`` are
management defaults, not regulatory requirements, and can be overridden with a
JSON file.

CLI::

    python tools/review.py --demo --out out/review-demo
    python tools/review.py --archive out/archive --month 2026-11 --out out/review-2026-11
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio  # noqa: E402

DEFAULT_THRESHOLDS = {
    "actual_coverage_min": 0.90,
    "plan_mape_max": 0.10,
    "energy_mape_max": 0.08,
    "cvar_hit_min": 0.85,
    "capture_ratio_min": 0.97,
    "assessment_ratio_max": 0.02,
    "bridge_gap_max": 1e-3,
    "warnings_per_run_max": 5.0,
    "hedge_ratio_deviation_max": 0.05,
}

DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fmt_ratio(value):
    if value is None:
        return "N/A"
    return f"{value * 100:+.1f}%"


def fmt_pct_unsigned(value):
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def fmt_gap(value):
    if value is None:
        return "N/A"
    if abs(value) < 0.01:
        return f"{value:.2e}"
    return f"{value:,.4f}"


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def mean_abs(values):
    return mean([abs(value) for value in values if value is not None])


def archive_date(path, root=None):
    path = Path(path).resolve()
    stop = Path(root).resolve() if root is not None else None
    if stop is not None:
        try:
            path.relative_to(stop)
        except ValueError:
            return ""
    for parent in path.parents:
        if DATE_DIR.match(parent.name):
            return parent.name
        if stop is not None and parent == stop:
            break
    return ""


def derive(record):
    """Add review-only KPIs without changing the normalized portfolio record."""
    item = dict(record)
    reference = item.get("reference_cny")
    actual = item.get("actual_cny")
    expected = item.get("expected_cny")
    item["delta_pct"] = (
        item["delta_cny"] / abs(reference)
        if item.get("delta_cny") is not None and reference not in (None, 0)
        else None
    )
    item["regret_cny"] = reference - actual if reference is not None and actual is not None else None
    item["expected_gap_pct"] = (
        (actual - expected) / abs(expected)
        if actual is not None and expected not in (None, 0)
        else None
    )
    energy = item.get("energy_deviation")
    energy_label = item.get("energy_label") or ""
    item["forecast_error_pct"] = energy if energy is not None and ("预测" in energy_label or "预期" in energy_label) else None
    item["declaration_deviation_pct"] = energy if energy is not None and "申报" in energy_label else None
    item["plan_energy_deviation_pct"] = (
        energy
        if energy is not None and item["forecast_error_pct"] is None and item["declaration_deviation_pct"] is None
        else None
    )
    realized = item.get("realized_price_cny_per_mwh")
    da_price = item.get("da_price_cny_per_mwh")
    item["realized_to_da"] = realized / da_price if realized is not None and da_price not in (None, 0) else None
    hedge_actual = item.get("hedge_ratio_actual")
    hedge_target = item.get("hedge_ratio_target")
    item["hedge_ratio_deviation"] = (
        hedge_actual - hedge_target
        if hedge_actual is not None and hedge_target is not None
        else None
    )
    item["has_actual"] = actual is not None
    return item


def filter_runs(runs, month=None):
    if not month:
        return runs
    return [run for run in runs if (run.get("trading_day") or "").startswith(month)]


def is_annual_summary(summary):
    """Annual/model-only packs must not inherit a trading day from a folder."""
    meta = summary.get("meta") or {}
    config = summary.get("config") or {}
    instance_id = (
        meta.get("instance_id")
        or summary.get("instance_id")
        or config.get("profile_id")
        or ""
    )
    kind = portfolio.infer_kind(summary, str(instance_id))
    return kind in ("capacity", "interprovincial", "direct") or "base" in summary or "economics" in summary


def collect_runs(archive, month=None):
    """Discover archived summaries, dedupe by (instance, day), return daily runs."""
    root = Path(archive)
    if not root.exists():
        raise FileNotFoundError(f"archive not found: {root}")
    runs = []
    errors = []
    duplicates = []
    annual_skipped = 0
    seen = {}
    for summary_path in sorted(root.rglob("summary.json")):
        try:
            summary = portfolio.read_json(summary_path)
            meta = summary.get("meta") or {}
            entry = {}
            if not (summary.get("trading_day") or meta.get("trading_day")) and not is_annual_summary(summary):
                day = archive_date(summary_path, root)
                if day:
                    entry["trading_day"] = day
                else:
                    errors.append(
                        {
                            "path": str(summary_path),
                            "error": "日度 summary 缺少 trading_day，归档路径也没有日期目录，已跳过",
                        }
                    )
                    continue
            bridge = portfolio.load_bridge(summary, summary_path)
            record = portfolio.normalize_summary(
                summary,
                bridge=bridge,
                entry=entry,
                summary_path=summary_path,
            )
            record["summary_mtime"] = summary_path.stat().st_mtime
        except Exception as exc:
            errors.append({"path": str(summary_path), "error": str(exc)})
            continue
        if record["horizon"] != "daily":
            annual_skipped += 1
            continue
        if month and not (record.get("trading_day") or "").startswith(month):
            continue
        key = (record["instance_id"], record["trading_day"])
        if key in seen:
            previous = seen[key]
            if record["summary_mtime"] > previous["summary_mtime"]:
                kept, dropped = record, previous
                runs[runs.index(previous)] = record
                seen[key] = record
            else:
                kept, dropped = previous, record
            duplicates.append(
                {
                    "instance_id": record["instance_id"],
                    "trading_day": record["trading_day"],
                    "kept": kept["summary_path"],
                    "dropped": dropped["summary_path"],
                }
            )
            continue
        seen[key] = record
        runs.append(record)
    return [derive(run) for run in runs], duplicates, annual_skipped, errors


def demo_runs(month=None):
    manifest, manifest_path = portfolio.load_manifest(portfolio.DEMO_MANIFEST)
    runs = []
    annual_skipped = 0
    errors = []
    for entry in manifest["packs"]:
        try:
            record = portfolio.load_entry(entry)
        except Exception as exc:
            errors.append({"path": entry.get("path"), "error": str(exc)})
            continue
        if record["horizon"] != "daily":
            annual_skipped += 1
            continue
        if not (record.get("trading_day") or "").strip():
            errors.append(
                {
                    "path": entry.get("path"),
                    "error": "日度清单条目缺少 trading_day，已跳过",
                }
            )
            continue
        if month and not (record.get("trading_day") or "").startswith(month):
            continue
        record["summary_mtime"] = 0.0
        runs.append(derive(record))
    return runs, annual_skipped, errors, manifest, manifest_path


def group_by_instance(runs):
    groups = {}
    for run in runs:
        groups.setdefault(run["instance_id"], []).append(run)
    return groups


def instance_rows(runs, thresholds):
    rows = []
    for instance_id, items in sorted(group_by_instance(runs).items()):
        labels = [item.get("label") for item in items if item.get("label")]
        kinds = [item.get("kind_label") for item in items if item.get("kind_label")]
        cvar_values = [item for item in items if item.get("cvar_hit") is not None]
        assessment = [item["assessment_cny"] for item in items if item.get("assessment_cny") is not None]
        allocation = [item["allocation_cny"] for item in items if item.get("allocation_cny") is not None]
        bridge_gaps = [item["bridge_gap_abs"] for item in items if item.get("bridge_gap_abs") is not None]
        plan_mape = mean_abs([item.get("delta_pct") for item in items])
        energy_mape = mean_abs([item.get("energy_deviation") for item in items])
        cvar_hit_rate = (
            sum(1 for item in cvar_values if item["cvar_hit"]) / len(cvar_values)
            if cvar_values
            else None
        )
        fingerprints = {item.get("fingerprint") for item in items if item.get("fingerprint")}
        rule_versions = {item.get("rule_version") for item in items if item.get("rule_version")}
        warnings_mean = mean([item.get("warning_count", 0) for item in items])
        bridge_gap_max = max(bridge_gaps) if bridge_gaps else None
        status = "正常"
        if any(item.get("actual_cny") is None for item in items):
            status = "异常"
        elif bridge_gap_max is not None and bridge_gap_max > thresholds["bridge_gap_max"]:
            status = "异常"
        elif (
            (plan_mape is not None and plan_mape > thresholds["plan_mape_max"])
            or (warnings_mean is not None and warnings_mean > thresholds["warnings_per_run_max"])
            or len(fingerprints) > 1
            or len(rule_versions) > 1
        ):
            status = "关注"
        rows.append(
            {
                "instance_id": instance_id,
                "label": labels[0] if labels else instance_id,
                "kind": kinds[0] if kinds else "",
                "runs": len(items),
                "actual_runs": sum(1 for item in items if item.get("actual_cny") is not None),
                "trading_days": len({item.get("trading_day") for item in items if item.get("trading_day")}),
                "plan_mape": plan_mape,
                "energy_mape": energy_mape,
                "cvar_hits": sum(1 for item in cvar_values if item["cvar_hit"]),
                "cvar_n": len(cvar_values),
                "cvar_hit_rate": cvar_hit_rate,
                "assessment_cny": sum(assessment) if assessment else None,
                "allocation_cny": sum(allocation) if allocation else None,
                "warnings_mean": warnings_mean,
                "bridge_gap_max": bridge_gap_max,
                "fingerprints": sorted(fingerprints),
                "rule_versions": sorted(rule_versions),
                "status": status,
            }
        )
    return rows


def daily_net_totals(runs):
    """Sum only daily net-margin runs; never mix revenue or annual profit."""
    grouped = {}
    for run in runs:
        if run.get("value_kind") != "net_margin":
            continue
        if run.get("actual_cny") is None or run.get("reference_cny") is None:
            continue
        grouped.setdefault(run["trading_day"], []).append(run)
    rows = []
    for day, items in grouped.items():
        reference = sum(item["reference_cny"] for item in items)
        actual = sum(item["actual_cny"] for item in items)
        delta = actual - reference
        rows.append(
            {
                "trading_day": day,
                "packs": len(items),
                "reference_cny": reference,
                "actual_cny": actual,
                "delta_cny": delta,
                "delta_pct": delta / abs(reference) if reference else None,
                "cvar_cny": sum(item["cvar_cny"] for item in items if item.get("cvar_cny") is not None),
                "warning_count": sum(item.get("warning_count", 0) for item in items),
            }
        )
    return sorted(rows, key=lambda item: item["trading_day"])


def kpi_values(runs, instance_items, duplicates, annual_skipped):
    actual = [run for run in runs if run.get("actual_cny") is not None]
    plan_values = [run.get("delta_pct") for run in actual if run.get("delta_pct") is not None]
    energy_values = [run.get("energy_deviation") for run in actual if run.get("energy_deviation") is not None]
    cvar_values = [run for run in actual if run.get("cvar_hit") is not None]
    capture_values = [run.get("capture_ratio") for run in actual if run.get("capture_ratio") is not None]
    assessment = [run["assessment_cny"] for run in actual if run.get("assessment_cny") is not None]
    actual_abs = [abs(run["actual_cny"]) for run in actual if run.get("assessment_cny") is not None]
    bridge_gaps = [run["bridge_gap_abs"] for run in runs if run.get("bridge_gap_abs") is not None]
    hedge_devs = [run.get("hedge_ratio_deviation") for run in runs if run.get("hedge_ratio_deviation") is not None]
    fingerprints = {run.get("fingerprint") for run in runs if run.get("fingerprint")}
    return {
        "run_count": len(runs),
        "actual_runs": len(actual),
        "actual_coverage": len(actual) / len(runs) if runs else None,
        "plan_mape": mean_abs(plan_values),
        "plan_mape_n": len(plan_values),
        "energy_mape": mean_abs(energy_values),
        "energy_mape_n": len(energy_values),
        "cvar_hit_rate": (
            sum(1 for run in cvar_values if run["cvar_hit"]) / len(cvar_values)
            if cvar_values
            else None
        ),
        "cvar_n": len(cvar_values),
        "capture_ratio": mean(capture_values),
        "capture_n": len(capture_values),
        "assessment_cny": sum(assessment) if assessment else None,
        "assessment_n": len(assessment),
        "assessment_ratio": (
            sum(assessment) / sum(actual_abs)
            if assessment and actual_abs and sum(actual_abs)
            else None
        ),
        "allocation_cny": sum(
            (run["allocation_cny"] for run in runs if run.get("allocation_cny") is not None),
            start=0.0,
        )
        if any(run.get("allocation_cny") is not None for run in runs)
        else None,
        "bridge_gap_max": max(bridge_gaps) if bridge_gaps else None,
        "warnings_per_run": mean([run.get("warning_count", 0) for run in runs]),
        "hedge_ratio_deviation": mean_abs(hedge_devs),
        "hedge_n": len(hedge_devs),
        "duplicate_count": len(duplicates),
        "fingerprint_count": len(fingerprints),
        "annual_skipped": annual_skipped,
        "instance_count": len(instance_items),
    }


def status_high(value, target):
    if value is None:
        return "无数据"
    return "达标" if value >= target else "关注"


def status_low(value, limit):
    if value is None:
        return "无数据"
    return "达标" if value <= limit else "关注"


def build_kpi_rows(values, thresholds):
    return [
        {
            "name": "实际值覆盖率",
            "value": fmt_pct_unsigned(values["actual_coverage"]),
            "target": f"≥{fmt_pct_unsigned(thresholds['actual_coverage_min'])}",
            "status": status_high(values["actual_coverage"], thresholds["actual_coverage_min"]),
            "sample": f"{values['actual_runs']}/{values['run_count']} 次运行",
        },
        {
            "name": "计划偏差 MAPE（实际−基准）",
            "value": fmt_pct_unsigned(values["plan_mape"]),
            "target": f"≤{fmt_pct_unsigned(thresholds['plan_mape_max'])}",
            "status": status_low(values["plan_mape"], thresholds["plan_mape_max"]),
            "sample": f"{values['plan_mape_n']} 次运行",
        },
        {
            "name": "电量偏差 MAPE（计划/申报 vs 实际）",
            "value": fmt_pct_unsigned(values["energy_mape"]),
            "target": f"≤{fmt_pct_unsigned(thresholds['energy_mape_max'])}",
            "status": status_low(values["energy_mape"], thresholds["energy_mape_max"]),
            "sample": f"{values['energy_mape_n']} 次运行",
        },
        {
            "name": "CVaR 命中率",
            "value": fmt_pct_unsigned(values["cvar_hit_rate"]),
            "target": f"≥{fmt_pct_unsigned(thresholds['cvar_hit_min'])}",
            "status": status_high(values["cvar_hit_rate"], thresholds["cvar_hit_min"]),
            "sample": f"{values['cvar_n']} 次运行",
        },
        {
            "name": "捕获率均值（相对基准）",
            "value": fmt_pct_unsigned(values["capture_ratio"]),
            "target": f"≥{fmt_pct_unsigned(thresholds['capture_ratio_min'])}",
            "status": status_high(values["capture_ratio"], thresholds["capture_ratio_min"]),
            "sample": f"{values['capture_n']} 次运行",
        },
        {
            "name": "考核支出占实际收益",
            "value": fmt_pct_unsigned(values["assessment_ratio"]),
            "target": f"≤{fmt_pct_unsigned(thresholds['assessment_ratio_max'])}",
            "status": status_low(values["assessment_ratio"], thresholds["assessment_ratio_max"]),
            "sample": f"{values['assessment_n']} 次运行",
        },
        {
            "name": "差异桥闭合最大残差",
            "value": fmt_gap(values["bridge_gap_max"]),
            "target": f"≤{thresholds['bridge_gap_max']:.0e} 元",
            "status": status_low(values["bridge_gap_max"], thresholds["bridge_gap_max"]),
            "sample": "含 bridge.json 的运行",
        },
        {
            "name": "预警密度",
            "value": f"{values['warnings_per_run']:.1f} 条/次" if values["warnings_per_run"] is not None else "N/A",
            "target": f"≤{thresholds['warnings_per_run_max']:.1f} 条/次",
            "status": status_low(values["warnings_per_run"], thresholds["warnings_per_run_max"]),
            "sample": f"{values['run_count']} 次运行",
        },
        {
            "name": "对冲比例偏离目标（持仓包）",
            "value": fmt_pct_unsigned(values["hedge_ratio_deviation"]),
            "target": f"≤{fmt_pct_unsigned(thresholds['hedge_ratio_deviation_max'])}",
            "status": status_low(values["hedge_ratio_deviation"], thresholds["hedge_ratio_deviation_max"]),
            "sample": f"{values['hedge_n']} 次运行",
        },
    ]


def fmt_assessment(row):
    parts = []
    if row.get("assessment_cny") is not None:
        parts.append(f"考核 {portfolio.fmt_money(row['assessment_cny'])}")
    if row.get("allocation_cny") is not None:
        parts.append(f"分摊 {portfolio.fmt_money(row['allocation_cny'])}")
    return " / ".join(parts) if parts else "N/A"


def build_scorecard(runs, label, month, duplicates, annual_skipped, errors, thresholds, archive_text):
    instance_items = instance_rows(runs, thresholds)
    values = kpi_values(runs, instance_items, duplicates, annual_skipped)
    kpi_rows = build_kpi_rows(values, thresholds)
    daily = daily_net_totals(runs)
    hedge_runs = [
        run
        for run in runs
        if run.get("carry_cny") is not None or run.get("hedge_value_reference_cny") is not None
    ]
    days = sorted({run["trading_day"] for run in runs if run.get("trading_day")})
    cutoffs = sorted({run["data_cutoff"] for run in runs if run.get("data_cutoff")})
    lines = []
    lines.append("# 月度交易质量评分卡")
    lines.append("")
    lines.append(
        f"> 范围：{label}｜筛选：{month or '全部'}｜日度运行：{len(runs)} 次｜实例：{len(instance_items)} 个"
        f"｜交易日：{days[0] + ' ~ ' + days[-1] if days else 'N/A'}"
        f"｜数据截止：{cutoffs[0] + ' ~ ' + cutoffs[-1] if cutoffs else 'N/A'}"
    )
    lines.append(
        "> **D 级合成数据，仅用于方法演示，不构成交易建议。** 本卡不合成单一分数：先看覆盖与数据质量，"
        "再看计划偏差、电量偏差、CVaR 命中和考核/分摊；不同口径不合并排名。"
    )
    if archive_text:
        lines.append(f"> 数据源：`{archive_text}`")
    lines.append("")
    lines.append("## 一、KPI 总览")
    lines.append("")
    lines.append("阈值是交易台管理默认值，不是监管标准；如公司风险制度不同，用 `--thresholds` 覆盖。")
    lines.append("")
    lines.append("| KPI | 本期 | 目标 | 状态 | 样本 |")
    lines.append("|---|---:|---:|---|---|")
    for row in kpi_rows:
        lines.append(
            f"| {row['name']} | {row['value']} | {row['target']} | {row['status']} | {row['sample']} |"
        )
    lines.append("")
    lines.append("**本期结论**")
    lines.append("")
    focus_findings = []
    if values["run_count"] == 0:
        focus_findings.append("未找到可用的日度运行；检查归档目录、`trading_day` 与 `--month`。")
    else:
        if values["actual_coverage"] is not None and values["actual_coverage"] < thresholds["actual_coverage_min"]:
            focus_findings.append(
                f"实际值覆盖不足（{fmt_pct_unsigned(values['actual_coverage'])}），先补齐 T+1 桥，再谈策略。"
            )
        if values["plan_mape"] is not None and values["plan_mape"] > thresholds["plan_mape_max"]:
            focus_findings.append(
                f"计划偏差 MAPE {fmt_pct_unsigned(values['plan_mape'])} 超过管理阈值，优先查电量、价格与执行三类桶。"
            )
        if values["cvar_hit_rate"] is not None and values["cvar_hit_rate"] < thresholds["cvar_hit_min"]:
            focus_findings.append("CVaR 命中率偏低，说明尾部情景或实际执行偏离了风险假设。")
        if values["bridge_gap_max"] is not None and values["bridge_gap_max"] > thresholds["bridge_gap_max"]:
            focus_findings.append("差异桥残差超限，先查量价口径与舍入，不要先归因于市场。")
        if duplicates:
            focus_findings.append(f"发现 {len(duplicates)} 组重复 (实例, 交易日)，已保留最新文件；归档流程需要去重。")
        if annual_skipped:
            focus_findings.append(f"跳过 {annual_skipped} 个年度/月度包；评分卡只统计带交易日的日度运行。")
        if not focus_findings:
            focus_findings.append("本期未触发硬阈值；继续看第三节的尾部运行与第四节的口径稳定性。")
    for finding in focus_findings:
        lines.append(f"- {finding}")
    lines.append("")
    lines.append("## 二、分实例")
    lines.append("")
    lines.append("金额单位：万元；“考核/分摊”分列，不混为一项；桥残差是 `|identity_gap|`。")
    lines.append("")
    lines.append("| 实例 | 类型 | 运行 | 有实际 | 计划偏差 | 电量偏差 | CVaR 命中 | 考核/分摊 | 桥残差 max | 预警/次 | 规则/指纹 | 状态 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|")
    for row in instance_items:
        cvar_text = (
            f"{row['cvar_hits']}/{row['cvar_n']} ({fmt_pct_unsigned(row['cvar_hit_rate'])})"
            if row["cvar_n"]
            else "N/A"
        )
        rule_text = f"{len(row['rule_versions'])} 版 / {len(row['fingerprints'])} 指纹"
        lines.append(
            f"| {portfolio.md_cell(row['label'])} | {portfolio.md_cell(row['kind'])} | {row['runs']} | {row['actual_runs']} | "
            f"{fmt_pct_unsigned(row['plan_mape'])} | {fmt_pct_unsigned(row['energy_mape'])} | {cvar_text} | "
            f"{fmt_assessment(row)} | {fmt_gap(row['bridge_gap_max'])} | "
            f"{row['warnings_mean']:.1f} | {rule_text} | {row['status']} |"
        )
    lines.append("")
    lines.append("## 三、最好/最差交易日（日度净收益合计）")
    lines.append("")
    if not daily:
        lines.append("没有同时具备基准与实际值的日度净收益运行，无法排名。")
        lines.append("")
    else:
        lines.append(
            "只按“实际−基准”的偏差率排序，不评价策略优劣；若每日主体集合不同，横向比较会失真，样本少时不要外推。"
            "CVaR 为当日同时有实际值和基准的主体的 10% 分位带符号简单相加，不是联合 CVaR；"
            "与组合简报主体集合不同时，两侧数值不可直接对比。"
        )
        lines.append("")
        lines.append("| 排名 | 交易日 | 主体 | 基准 | 实际 | 实际−基准 | 差异% | CVaR | 预警 |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        ranked = sorted(daily, key=lambda item: item["delta_pct"] if item["delta_pct"] is not None else -999, reverse=True)
        if len(ranked) <= 5:
            for index, row in enumerate(ranked, start=1):
                lines.append(
                    f"| {index} | {row['trading_day']} | {row['packs']} | {portfolio.fmt_money(row['reference_cny'])} | "
                    f"{portfolio.fmt_money(row['actual_cny'])} | {portfolio.fmt_money(row['delta_cny'])} | "
                    f"{fmt_ratio(row['delta_pct'])} | {portfolio.fmt_money(row['cvar_cny'])} | {row['warning_count']} |"
                )
        else:
            for title, rows in (("最好", ranked[:5]), ("最差", ranked[-5:][::-1])):
                for index, row in enumerate(rows, start=1):
                    lines.append(
                        f"| {title} {index} | {row['trading_day']} | {row['packs']} | {portfolio.fmt_money(row['reference_cny'])} | "
                        f"{portfolio.fmt_money(row['actual_cny'])} | {portfolio.fmt_money(row['delta_cny'])} | "
                        f"{fmt_ratio(row['delta_pct'])} | {portfolio.fmt_money(row['cvar_cny'])} | {row['warning_count']} |"
                    )
        lines.append("")
    lines.append("## 四、对冲有效性与口径稳定性")
    lines.append("")
    if hedge_runs:
        lines.append("| 实例 | 交易日 | 计划对冲 | 实际对冲 | 目标 | 偏离 | carry | shape | 参考对冲价值 | carry+shape−参考 | 预期对冲价值 |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for run in hedge_runs:
            identity = None
            if (
                run.get("carry_cny") is not None
                and run.get("shape_cny") is not None
                and run.get("hedge_value_reference_cny") is not None
            ):
                identity = run["carry_cny"] + run["shape_cny"] - run["hedge_value_reference_cny"]
            lines.append(
                f"| {portfolio.md_cell(run['label'])} | {run['trading_day']} | {fmt_pct_unsigned(run.get('hedge_ratio_plan'))} | "
                f"{fmt_pct_unsigned(run.get('hedge_ratio_actual'))} | {fmt_pct_unsigned(run.get('hedge_ratio_target'))} | "
                f"{fmt_ratio(run.get('hedge_ratio_deviation'))} | {portfolio.fmt_money(run.get('carry_cny'))} | "
                f"{portfolio.fmt_money(run.get('shape_cny'))} | {portfolio.fmt_money(run.get('hedge_value_reference_cny'))} | "
                f"{fmt_gap(identity)} | {portfolio.fmt_money(run.get('hedge_value_cny'))} |"
            )
        lines.append("")
        lines.append(
            "carry/curve 分解是持仓包内部的数学恒等式，恒等于**参考对冲价值**；预期对冲价值用于情景决策，"
            "两者不能混用。残差应接近 0，偏离目标对冲比例要结合仓位、流动性和合约可得性解释。"
        )
        lines.append("")
    else:
        lines.append("本期没有带 carry/shape 分解的持仓包运行。")
        lines.append("")
    multiple_rules = [row for row in instance_items if len(row["fingerprints"]) > 1 or len(row["rule_versions"]) > 1]
    if multiple_rules:
        lines.append("**规则/指纹不一致**")
        lines.append("")
        for row in multiple_rules:
            lines.append(
                f"- {row['label']}：{len(row['rule_versions'])} 套规则、{len(row['fingerprints'])} 个指纹；"
                "月内规则切换时应切段比较，不能把规则变化当成交易质量下降。"
            )
        lines.append("")
    else:
        lines.append("- 每个实例本期只有一套规则版本与一个策略指纹，未发现口径混用。")
        lines.append("")
    lines.append("## 五、数据质量与边界")
    lines.append("")
    lines.append(f"- 日度运行 {len(runs)} 次；其中有实际值 {values['actual_runs']} 次；跳过年度/月度包 {annual_skipped} 个。")
    lines.append(f"- 重复 (实例, 交易日) {len(duplicates)} 组；加载失败 {len(errors)} 个文件。")
    if duplicates:
        for item in duplicates[:5]:
            lines.append(f"  - {item['instance_id']} {item['trading_day']}：保留 `{item['kept']}`，丢弃 `{item['dropped']}`。")
    if errors:
        for item in errors[:5]:
            lines.append(f"  - `{item['path']}`：{item['error']}")
    lines.append("- 评分卡只读归档产物；不连接实盘、不生成报价，也不替代交易中心结算。")
    lines.append("- 缺失值写 N/A，不以 0 或模型值回填；CVaR 命中是事后核对，不是事前保证。")
    lines.append("- 计划偏差与电量偏差只说明执行与预测质量，不单独证明策略好坏；必须结合市场行情、约束与考核规则解释。")
    lines.append("- 管理阈值：`plan_mape_max`、`energy_mape_max`、`cvar_hit_min`、`bridge_gap_max` 等可按公司制度覆盖。")
    lines.append("")
    return "\n".join(lines), {
        "label": label,
        "month": month,
        "run_count": len(runs),
        "instance_count": len(instance_items),
        "trading_days": days,
        "data_cutoffs": cutoffs,
        "annual_skipped": annual_skipped,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "errors": errors,
        "thresholds": thresholds,
        "kpis": values,
        "instances": instance_items,
        "daily_totals": daily,
        "hedge_runs": [
            {
                "instance_id": run["instance_id"],
                "trading_day": run["trading_day"],
                "hedge_ratio_plan": run.get("hedge_ratio_plan"),
                "hedge_ratio_actual": run.get("hedge_ratio_actual"),
                "hedge_ratio_target": run.get("hedge_ratio_target"),
                "hedge_ratio_deviation": run.get("hedge_ratio_deviation"),
                "carry_cny": run.get("carry_cny"),
                "shape_cny": run.get("shape_cny"),
                "hedge_value_cny": run.get("hedge_value_cny"),
                "hedge_value_reference_cny": run.get("hedge_value_reference_cny"),
            }
            for run in hedge_runs
        ],
    }


def write_run_csv(runs, path):
    fields = [
        "instance_id",
        "label",
        "province",
        "kind",
        "trading_day",
        "data_cutoff",
        "value_kind",
        "expected_cny",
        "reference_cny",
        "actual_cny",
        "delta_cny",
        "delta_pct",
        "regret_cny",
        "expected_gap_pct",
        "plan_energy_mwh",
        "actual_energy_mwh",
        "energy_deviation",
        "forecast_error_pct",
        "declaration_deviation_pct",
        "plan_energy_deviation_pct",
        "cvar_cny",
        "cvar_hit",
        "capture_cny_per_mwh",
        "capture_benchmark_cny_per_mwh",
        "capture_ratio",
        "realized_price_cny_per_mwh",
        "da_price_cny_per_mwh",
        "realized_to_da",
        "assessment_cny",
        "allocation_cny",
        "hedge_ratio_plan",
        "hedge_ratio_actual",
        "hedge_ratio_target",
        "hedge_ratio_deviation",
        "carry_cny",
        "shape_cny",
        "hedge_value_cny",
        "hedge_value_reference_cny",
        "bridge_gap_abs",
        "warning_count",
        "rule_version",
        "fingerprint",
        "status",
        "summary_path",
    ]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            writer.writerow({field: run.get(field, "") for field in fields})


def write_kpi_csv(rows, path):
    fields = [
        "instance_id",
        "label",
        "kind",
        "runs",
        "actual_runs",
        "trading_days",
        "plan_mape",
        "energy_mape",
        "cvar_hits",
        "cvar_n",
        "cvar_hit_rate",
        "assessment_cny",
        "allocation_cny",
        "warnings_mean",
        "bridge_gap_max",
        "fingerprints",
        "rule_versions",
        "status",
    ]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            item = dict(row)
            item["fingerprints"] = "|".join(item["fingerprints"])
            item["rule_versions"] = "|".join(item["rule_versions"])
            writer.writerow({field: item.get(field, "") for field in fields})


def load_thresholds(path):
    thresholds = dict(DEFAULT_THRESHOLDS)
    if not path:
        return thresholds
    override = portfolio.read_json(path)
    if not isinstance(override, dict):
        raise ValueError("thresholds file must contain a JSON object")
    for key, value in override.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"threshold {key!r} must be numeric")
        thresholds[key] = value
    return thresholds


def write_outputs(out_dir, scorecard, summary, kpi_rows, runs):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scorecard.md").write_text(scorecard, encoding="utf-8")
    (out / "review_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_kpi_csv(kpi_rows, out / "kpis.csv")
    write_run_csv(runs, out / "runs.csv")
    return out


def build_review(runs, label, month, duplicates, annual_skipped, errors, thresholds, archive_text):
    scorecard, summary = build_scorecard(
        runs,
        label=label,
        month=month,
        duplicates=duplicates,
        annual_skipped=annual_skipped,
        errors=errors,
        thresholds=thresholds,
        archive_text=archive_text,
    )
    summary["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary["archive"] = archive_text
    return scorecard, summary


def run(archive, out_dir, label, month, thresholds, demo=False):
    if demo:
        runs, annual_skipped, errors, manifest, manifest_path = demo_runs(month=month)
        duplicates = []
        archive_text = f"清单 {manifest_path}" if manifest_path else ""
        if not label:
            label = manifest.get("name") or "样例批次"
        if not month:
            label = f"{label} · 样例批次（非月度）"
    else:
        runs, duplicates, annual_skipped, errors = collect_runs(archive, month=month)
        archive_text = str(Path(archive))
        if not label:
            label = f"归档 {Path(archive).name}"
    scorecard, summary = build_review(
        runs,
        label=label,
        month=month,
        duplicates=duplicates,
        annual_skipped=annual_skipped,
        errors=errors,
        thresholds=thresholds,
        archive_text=archive_text,
    )
    out = write_outputs(out_dir, scorecard, summary, summary["instances"], runs)
    print(f"wrote {out / 'scorecard.md'}")
    print(f"wrote {out / 'kpis.csv'}")
    print(f"wrote {out / 'runs.csv'}")
    print(f"wrote {out / 'review_summary.json'}")
    if not runs:
        print("warning: no daily runs found; scorecard contains N/A rows", file=sys.stderr)
    if errors:
        for item in errors:
            print(f"error: {item['path']}: {item['error']}", file=sys.stderr)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a monthly trading-quality scorecard from archived pack outputs.")
    parser.add_argument("--archive", help="archive root containing **/summary.json")
    parser.add_argument("--out", default="out/review", help="output directory (default: out/review)")
    parser.add_argument("--month", help="filter YYYY-MM on trading_day")
    parser.add_argument("--label", help="report label")
    parser.add_argument("--thresholds", help="JSON file overriding management KPI thresholds")
    parser.add_argument("--demo", action="store_true", help="use the shipped 12-pack demo manifest")
    args = parser.parse_args(argv)

    if args.month and not re.fullmatch(r"\d{4}-\d{2}", args.month):
        parser.error("--month must be YYYY-MM")
    if not args.demo and not args.archive:
        parser.error("pass --archive PATH or --demo")
    thresholds = load_thresholds(args.thresholds)
    run(
        args.archive,
        args.out,
        label=args.label,
        month=args.month,
        thresholds=thresholds,
        demo=args.demo,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
