#!/usr/bin/env python3
"""Run the Shandong storage-station EMS daily-operation instance pack.

The engine is shared, the instance is local:

* ``instance.json`` holds the spot tariff, storage parameters, the AGC and
  primary-frequency assessment口径 plus the assets and the dispatch style.
* ``data/profile_demo.csv`` is a 96-point representative day: spot price, AGC
  regulation setpoint, frequency deviation and tariff segment.

The runner schedules a day-ahead energy arbitrage dispatch with the shared DP
kernel, then replays two grid-code assessments on the same day: AGC regulation
performance (rate / precision) and primary-frequency contribution. The综合净收益
is the arbitrage net revenue minus the two assessment charges.

All bundled numbers are synthetic grade D. The assessment formulas are teaching
simplifications, not a并网验收 opinion, a考核申诉 basis or investment advice.
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

import storage  # noqa: E402

DT_H = 0.25
POINTS = 96
F0_HZ = 50.0
GRADES = {"A", "B", "C", "D", "A/B", "B/C", "C/D", "B/C/D"}


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
    if grade not in GRADES:
        raise ConfigError(f"{path}.grade {grade!r} is not a known grade")
    return grade


def _rule_block(rules, name, report):
    block = _need(rules, name, "rules")
    if not isinstance(block, dict):
        raise ConfigError(f"rules.{name} must be an object")
    grade = _grade(block, f"rules.{name}")
    source = _text(block, "source", f"rules.{name}")
    report.append({"block": f"rules.{name}", "grade": grade, "source": source})
    return block, grade


def load_config(path):
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"instance not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"instance is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError("instance must be a JSON object")

    meta = _need(config, "meta", "instance")
    for key in (
        "instance_id",
        "province",
        "market",
        "entity_type",
        "rule_version",
        "data_cutoff",
        "scope",
        "currency",
        "units",
        "disclaimer",
    ):
        _text(meta, key, "meta")
    _grade(meta, "meta")

    rules = _need(config, "rules", "instance")
    report = []
    tariff, _ = _rule_block(rules, "tariff", report)
    storage_block, _ = _rule_block(rules, "storage", report)
    assessment, _ = _rule_block(rules, "assessment", report)

    peak = _number(
        _need(tariff, "peak_cny_per_mwh", "rules.tariff"), "rules.tariff.peak_cny_per_mwh", 0.0
    )
    flat = _number(
        _need(tariff, "flat_cny_per_mwh", "rules.tariff"), "rules.tariff.flat_cny_per_mwh", 0.0
    )
    valley = _number(
        _need(tariff, "valley_cny_per_mwh", "rules.tariff"), "rules.tariff.valley_cny_per_mwh", 0.0
    )
    midday = _number(
        _need(tariff, "midday_dip_cny_per_mwh", "rules.tariff"),
        "rules.tariff.midday_dip_cny_per_mwh",
        0.0,
    )
    if not peak >= flat >= valley:
        raise ConfigError("rules.tariff must satisfy peak >= flat >= valley")

    capacity = _number(
        _need(storage_block, "capacity_mwh", "rules.storage"), "rules.storage.capacity_mwh", 0.0
    )
    power = _number(
        _need(storage_block, "power_mw", "rules.storage"), "rules.storage.power_mw", 0.0
    )
    if capacity <= 0 or power <= 0:
        raise ConfigError("storage capacity and power must be positive")
    rte = _number(_need(storage_block, "rte", "rules.storage"), "rules.storage.rte", 0.0, 1.0)
    if not 0 < rte <= 1:
        raise ConfigError("storage rte must be in (0, 1]")
    soc_min = _number(
        _need(storage_block, "soc_min", "rules.storage"), "rules.storage.soc_min", 0.0, 1.0
    )
    soc_max = _number(
        _need(storage_block, "soc_max", "rules.storage"), "rules.storage.soc_max", 0.0, 1.0
    )
    if not 0 <= soc_min < soc_max <= 1:
        raise ConfigError("require 0 <= soc_min < soc_max <= 1")
    soc_init = _number(
        _need(storage_block, "soc_init", "rules.storage"), "rules.storage.soc_init", soc_min, soc_max
    )
    degradation = _number(
        _need(storage_block, "degradation_cny_per_kwh", "rules.storage"),
        "rules.storage.degradation_cny_per_kwh",
        0.0,
    )

    agc_rate = _number(
        _need(assessment, "agc_rate_capability_mw_per_min", "rules.assessment"),
        "rules.assessment.agc_rate_capability_mw_per_min",
        0.0,
    )
    agc_prec_err = _number(
        _need(assessment, "agc_precision_error_pct", "rules.assessment"),
        "rules.assessment.agc_precision_error_pct",
        0.0,
        1.0,
    )
    agc_prec_thr = _number(
        _need(assessment, "agc_precision_threshold_pct", "rules.assessment"),
        "rules.assessment.agc_precision_threshold_pct",
        0.0,
        1.0,
    )
    agc_factor = _number(
        _need(assessment, "agc_assessment_factor", "rules.assessment"),
        "rules.assessment.agc_assessment_factor",
        0.0,
    )
    _number(
        _need(assessment, "agc_response_time_standard_s", "rules.assessment"),
        "rules.assessment.agc_response_time_standard_s",
        0.0,
    )
    droop = _number(
        _need(assessment, "primary_freq_droop_r", "rules.assessment"),
        "rules.assessment.primary_freq_droop_r",
        0.0,
        1.0,
    )
    if not 0 < droop <= 1:
        raise ConfigError("primary_freq_droop_r must be in (0, 1]")
    deadband = _number(
        _need(assessment, "primary_freq_deadband_hz", "rules.assessment"),
        "rules.assessment.primary_freq_deadband_hz",
        0.0,
    )
    performance = _number(
        _need(assessment, "primary_freq_performance", "rules.assessment"),
        "rules.assessment.primary_freq_performance",
        0.0,
        1.0,
    )
    peak_avail = _number(
        _need(assessment, "primary_freq_peak_available_mw", "rules.assessment"),
        "rules.assessment.primary_freq_peak_available_mw",
        0.0,
        power,
    )
    contribution_thr = _number(
        _need(assessment, "primary_freq_contribution_threshold", "rules.assessment"),
        "rules.assessment.primary_freq_contribution_threshold",
        0.0,
        1.0,
    )
    freq_factor = _number(
        _need(assessment, "primary_freq_assessment_factor", "rules.assessment"),
        "rules.assessment.primary_freq_assessment_factor",
        0.0,
    )

    assets = _need(config, "assets", "instance")
    pcc = _number(_need(assets, "pcc_mw", "assets"), "assets.pcc_mw", 0.0)
    _grade(assets, "assets")

    policy = _need(config, "policy", "instance")
    profile_id = _text(policy, "profile_id", "policy")
    terminal = _text(policy, "terminal", "policy")
    if terminal not in {"cycle", "free"}:
        raise ConfigError("policy.terminal must be cycle or free")
    states = int(_number(_need(policy, "states", "policy"), "policy.states", 10.0, 2000.0))
    _text(policy, "objective", "policy")
    _grade(policy, "policy")

    data_contract = _need(config, "data_contract", "instance")
    profile = _need(data_contract, "profile", "data_contract")
    _text(profile, "file", "data_contract.profile")

    return {
        "config": config,
        "report": report,
        "tariff": {"peak": peak, "flat": flat, "valley": valley, "midday": midday},
        "storage": {
            "capacity": capacity,
            "power": power,
            "rte": rte,
            "soc_min": soc_min,
            "soc_max": soc_max,
            "soc_init": soc_init,
            "degradation": degradation,
        },
        "assessment": {
            "agc_rate": agc_rate,
            "agc_prec_err": agc_prec_err,
            "agc_prec_thr": agc_prec_thr,
            "agc_factor": agc_factor,
            "droop": droop,
            "deadband": deadband,
            "performance": performance,
            "peak_avail": peak_avail,
            "contribution_thr": contribution_thr,
            "freq_factor": freq_factor,
        },
        "assets": {"pcc": pcc},
        "policy": {"profile_id": profile_id, "terminal": terminal, "states": states},
        "base_dir": path.parent,
    }


def _time_label(index):
    hour = index * DT_H
    return f"{int(hour):02d}:{int(round((hour % 1) * 60)):02d}"


def read_profile(path, parsed):
    try:
        fh = path.open(newline="", encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"profile not found: {path}") from exc
    with fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != POINTS:
        raise ConfigError(f"profile must have {POINTS} rows, got {len(rows)}")
    required = [
        "interval",
        "time",
        "price_cny_per_mwh",
        "agc_signal_mw",
        "freq_deviation_hz",
        "segment",
    ]
    if rows and list(rows[0].keys()) != required:
        raise ConfigError(f"profile fields must be {required}")

    tariff = parsed["tariff"]
    prices = {
        "peak": tariff["peak"],
        "flat": tariff["flat"],
        "valley": tariff["valley"],
        "midday": tariff["midday"],
    }
    power = parsed["storage"]["power"]
    price, agc, freq, segment = [], [], [], []
    for i, row in enumerate(rows):
        try:
            interval = int(row["interval"])
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"profile row {i + 1}: interval must be an integer") from exc
        if interval != i:
            raise ConfigError(f"profile row {i + 1}: interval must be {i}")
        if row["time"] != _time_label(i):
            raise ConfigError(f"profile row {i + 1}: time {row['time']!r} must be {_time_label(i)}")
        try:
            price_value = float(row["price_cny_per_mwh"])
            agc_value = float(row["agc_signal_mw"])
            freq_value = float(row["freq_deviation_hz"])
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"profile row {i + 1}: numeric fields are invalid") from exc
        if not math.isfinite(price_value) or price_value <= 0:
            raise ConfigError(f"profile row {i + 1}: price_cny_per_mwh must be positive")
        if not math.isfinite(agc_value) or abs(agc_value) > power + 1e-9:
            raise ConfigError(f"profile row {i + 1}: agc_signal_mw must be within +/- power_mw")
        if not math.isfinite(freq_value) or abs(freq_value) > 1.0:
            raise ConfigError(f"profile row {i + 1}: freq_deviation_hz must be within +/- 1 Hz")
        seg = row["segment"].strip()
        if seg not in prices:
            raise ConfigError(f"profile row {i + 1}: segment must be peak/flat/valley/midday")
        if abs(price_value - prices[seg]) > 1e-9:
            raise ConfigError(
                f"profile row {i + 1}: price {price_value} does not match tariff {seg}={prices[seg]}"
            )
        price.append(price_value)
        agc.append(agc_value)
        freq.append(freq_value)
        segment.append(seg)

    return {"price": price, "agc_signal": agc, "freq_deviation": freq, "segment": segment}


def _arbitrage(parsed, profile):
    s = parsed["storage"]
    policy = parsed["policy"]
    result = storage.station_day(
        profile["price"],
        s["power"],
        s["capacity"],
        s["rte"],
        soc_min=s["soc_min"],
        soc_max=s["soc_max"],
        soc_init=s["soc_init"],
        dt_h=DT_H,
        pcc_import_mw=parsed["assets"]["pcc"],
        pcc_export_mw=parsed["assets"]["pcc"],
        degradation_per_kwh=s["degradation"],
        terminal=policy["terminal"],
        states=policy["states"],
    )
    if not result.get("feasible", False):
        raise ConfigError(f"arbitrage dispatch is infeasible: {result.get('reason')}")
    return result


def agc_review(profile, assessment):
    signal = profile["agc_signal"]
    rate_cap = assessment["agc_rate"]
    prec_err = assessment["agc_prec_err"]
    prec_thr = assessment["agc_prec_thr"]
    factor = assessment["agc_factor"]
    precision_pass = prec_err <= prec_thr + 1e-12
    rows = []
    assess_energy = 0.0
    max_rate = 0.0
    fail_count = 0
    for i in range(POINTS):
        prev = signal[i - 1] if i > 0 else signal[0]
        required_rate = abs(signal[i] - prev) / (DT_H * 60.0)
        max_rate = max(max_rate, required_rate)
        rate_pass = required_rate <= rate_cap + 1e-9
        ok = rate_pass and precision_pass
        energy = 0.0 if ok else abs(signal[i]) * DT_H * factor
        if not ok:
            fail_count += 1
        assess_energy += energy
        rows.append(
            {
                "interval": i,
                "time": _time_label(i),
                "agc_signal_mw": signal[i],
                "required_rate_mw_per_min": required_rate,
                "rate_pass": rate_pass,
                "precision_pass": precision_pass,
                "assessed_mwh": energy,
            }
        )
    return {
        "rows": rows,
        "assessed_mwh": assess_energy,
        "max_required_rate_mw_per_min": max_rate,
        "rate_capability_mw_per_min": rate_cap,
        "precision_error_pct": prec_err,
        "precision_threshold_pct": prec_thr,
        "precision_pass": precision_pass,
        "fail_intervals": fail_count,
    }


def freq_review(profile, assessment, power_mw):
    droop = assessment["droop"]
    deadband = assessment["deadband"]
    performance = assessment["performance"]
    peak_avail = assessment["peak_avail"]
    threshold = assessment["contribution_thr"]
    factor = assessment["freq_factor"]
    rows = []
    theo_total = 0.0
    actual_total = 0.0
    assess_energy = 0.0
    events = 0
    fail_events = 0
    for i in range(POINTS):
        df = profile["freq_deviation"][i]
        seg = profile["segment"][i]
        if abs(df) <= deadband + 1e-12:
            rows.append(
                {
                    "interval": i,
                    "time": _time_label(i),
                    "segment": seg,
                    "freq_deviation_hz": df,
                    "theoretical_mw": 0.0,
                    "actual_mw": 0.0,
                    "theoretical_mwh": 0.0,
                    "actual_mwh": 0.0,
                    "contribution_ratio": "",
                    "assessed_mwh": 0.0,
                }
            )
            continue
        events += 1
        theo_dp = -(1.0 / droop) * (df / F0_HZ) * power_mw
        if theo_dp >= 0:
            avail = peak_avail if seg == "peak" else power_mw
        else:
            avail = power_mw
        actual_dp = math.copysign(min(abs(theo_dp), avail) * performance, theo_dp)
        theo = abs(theo_dp) * DT_H
        actual = abs(actual_dp) * DT_H
        ratio = actual / theo if theo > 0 else 0.0
        if ratio < threshold - 1e-12:
            assess = (theo - actual) * factor
            fail_events += 1
        else:
            assess = 0.0
        theo_total += theo
        actual_total += actual
        assess_energy += assess
        rows.append(
            {
                "interval": i,
                "time": _time_label(i),
                "segment": seg,
                "freq_deviation_hz": df,
                "theoretical_mw": theo_dp,
                "actual_mw": actual_dp,
                "theoretical_mwh": theo,
                "actual_mwh": actual,
                "contribution_ratio": ratio,
                "assessed_mwh": assess,
            }
        )
    aggregate = actual_total / theo_total if theo_total > 0 else 0.0
    return {
        "rows": rows,
        "assessed_mwh": assess_energy,
        "theoretical_mwh": theo_total,
        "actual_mwh": actual_total,
        "aggregate_contribution_ratio": aggregate,
        "contribution_threshold": threshold,
        "events": events,
        "fail_events": fail_events,
    }


def _write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fingerprint(policy):
    payload = json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _fmt(value, digits=2):
    return f"{value:,.{digits}f}"


def write_review(path, parsed, arbitrage, agc, freq, economics):
    config = parsed["config"]
    s = parsed["storage"]
    lines = [
        "# 山东独立储能电站 EMS 日运行 · 复核表",
        "",
        f"> 实例 `{config['meta']['instance_id']}`；代表日 96 点；风格 `{parsed['policy']['profile_id']}`，"
        f"指纹 `{_fingerprint(config['policy'])}`。全部为 D 级合成数据。",
        "",
        "## 1. 结论",
        "",
        f"- 日前能量套利净收益 **{_fmt(economics['arbitrage_net_cny'])} 元/日**"
        f"（充电 {_fmt(arbitrage['charge_mwh'])} MWh、放电 {_fmt(arbitrage['discharge_mwh'])} MWh、"
        f"吞吐 {_fmt(arbitrage['throughput_mwh'])} MWh、退化 {_fmt(arbitrage['degradation_cost'])} 元）。",
        f"- AGC 调节性能考核电量 {_fmt(agc['assessed_mwh'], 3)} MWh，考核电费 "
        f"{_fmt(economics['agc_charge_cny'])} 元：储能速率/精度均合格"
        f"（最大需求速率 {_fmt(agc['max_required_rate_mw_per_min'])} MW/min ≤ "
        f"能力 {_fmt(agc['rate_capability_mw_per_min'], 0)} MW/min；"
        f"精度 {agc['precision_error_pct']:.0%} ≤ 门槛 {agc['precision_threshold_pct']:.0%}）。",
        f"- 一次调频贡献考核电量 {_fmt(freq['assessed_mwh'], 3)} MWh，考核电费 "
        f"{_fmt(economics['freq_charge_cny'])} 元：{freq['events']} 个频率事件中 "
        f"{freq['fail_events']} 个贡献比低于门槛 {freq['contribution_threshold']:.0%}"
        f"（峰段上调可用功率受限 {_fmt(parsed['assessment']['peak_avail'], 0)} MW）。",
        f"- 综合净收益 = 套利净收益 − AGC 考核 − 一次调频考核 = "
        f"**{_fmt(economics['combined_net_cny'])} 元/日**。",
        "",
        "## 2. 能量套利调度",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 充电量 MWh | {_fmt(arbitrage['charge_mwh'])} |",
        f"| 放电量 MWh | {_fmt(arbitrage['discharge_mwh'])} |",
        f"| 吞吐 MWh | {_fmt(arbitrage['throughput_mwh'])} |",
        f"| 等效循环次数 | {arbitrage['equivalent_cycles']:.3f} |",
        f"| 充电成本 元 | {_fmt(arbitrage['charge_cost'])} |",
        f"| 放电收入 元 | {_fmt(arbitrage['discharge_revenue'])} |",
        f"| 退化成本 元 | {_fmt(arbitrage['degradation_cost'])} |",
        f"| 净收益 元 | {_fmt(arbitrage['net_revenue'])} |",
        f"| 终端 SOC | {arbitrage['terminal_soc']:.3f} |",
        "",
        "## 3. AGC 调节性能考核复盘",
        "",
        f"速率能力 {_fmt(agc['rate_capability_mw_per_min'], 0)} MW/min；"
        f"最大需求速率 {_fmt(agc['max_required_rate_mw_per_min'])} MW/min；"
        f"精度误差 {agc['precision_error_pct']:.0%} / 门槛 {agc['precision_threshold_pct']:.0%}；"
        f"不合格时段 {agc['fail_intervals']} 个；考核电量 {_fmt(agc['assessed_mwh'], 3)} MWh。",
        "",
        "储能响应快，AGC 速率与精度通常合格；考核主要来自精度门槛收紧或通信/可用率异常，"
        "本例不触发。逐时段明细见 `agc.csv`。",
        "",
        "## 4. 一次调频贡献考核复盘",
        "",
        f"调差 R = {parsed['assessment']['droop']:.0%}；死区 ±{parsed['assessment']['deadband']} Hz；"
        f"性能系数 {parsed['assessment']['performance']:.0%}；贡献门槛 {freq['contribution_threshold']:.0%}。",
        f"理论贡献 {_fmt(freq['theoretical_mwh'], 3)} MWh，实际贡献 {_fmt(freq['actual_mwh'], 3)} MWh，"
        f"聚合贡献比 {freq['aggregate_contribution_ratio']:.1%}；考核电量 {_fmt(freq['assessed_mwh'], 3)} MWh。",
        "",
        "| 时段 | 段 | 频差 Hz | 理论 MW | 实际 MW | 贡献比 | 考核 MWh |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in freq["rows"]:
        if row["theoretical_mwh"] <= 0:
            continue
        ratio = row["contribution_ratio"]
        ratio_text = f"{ratio:.0%}" if isinstance(ratio, (int, float)) else "—"
        lines.append(
            f"| {row['time']} | {row['segment']} | {row['freq_deviation_hz']:+.2f} | "
            f"{row['theoretical_mw']:+.2f} | {row['actual_mw']:+.2f} | {ratio_text} | "
            f"{row['assessed_mwh']:.3f} |"
        )
    lines += [
        "",
        "## 5. 综合经济性",
        "",
        "| 项目 | 元/日 |",
        "|---|---:|",
        f"| 能量套利净收益 | {_fmt(economics['arbitrage_net_cny'])} |",
        f"| 减：AGC 考核电费 | {_fmt(economics['agc_charge_cny'])} |",
        f"| 减：一次调频考核电费 | {_fmt(economics['freq_charge_cny'])} |",
        f"| 综合净收益 | {_fmt(economics['combined_net_cny'])} |",
        "",
        "## 6. 口径提醒",
        "",
        "1. **能量调度与考核复盘共用同一代表日，但容量互斥**：套利把峰段功率用于放电，"
        "一次调频上调可用功率因此受限；真实运行须在同一 SOC/功率约束下联合优化，本例分步演示。",
        "2. 考核电费按考核电量 × 平段电价（D 级假设）折算；两个细则的考核电价、考核系数与"
        "免考口径以山东现行文件与并网调度协议为准。",
        "3. AGC 速率/精度、一次调频调差/死区/性能/贡献门槛均为 D 级教学简化，"
        "不构成并网验收、考核申诉或投资建议。",
        "4. 一次调频理论出力 ΔP = −(1/R)·(Δf/f0)·Pn，死区内不动作；"
        "实际出力受可用功率与性能系数限制，贡献比 = 实际/理论。",
        "5. 本例不含实时市场出清、调频里程竞价、容量拍卖与辅助服务分成结算；"
        "储能多重收益叠加见 storage-invest 技能与广东收益叠加实例。",
        "",
        "逐时段调度见 `dispatch.csv`，AGC 明细见 `agc.csv`，一次调频明细见 `freq.csv`。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(instance_path, out_dir, demo):
    parsed = load_config(instance_path)
    config = parsed["config"]
    data_path = Path(config["data_contract"]["profile"]["file"])
    if not data_path.is_absolute():
        data_path = parsed["base_dir"] / data_path
    profile = read_profile(data_path, parsed)

    arbitrage = _arbitrage(parsed, profile)
    schedule = arbitrage["schedule"]
    arbitrage["charge_mwh"] = sum(schedule["p_charge_mw"]) * DT_H
    arbitrage["discharge_mwh"] = sum(schedule["p_discharge_mw"]) * DT_H
    arbitrage["charge_cost"] = sum(
        c * p * DT_H for c, p in zip(schedule["p_charge_mw"], profile["price"])
    )
    arbitrage["discharge_revenue"] = sum(
        d * p * DT_H for d, p in zip(schedule["p_discharge_mw"], profile["price"])
    )

    agc = agc_review(profile, parsed["assessment"])
    freq = freq_review(profile, parsed["assessment"], parsed["storage"]["power"])

    flat_price = parsed["tariff"]["flat"]
    agc_charge = agc["assessed_mwh"] * flat_price
    freq_charge = freq["assessed_mwh"] * flat_price
    arbitrage_net = float(arbitrage["net_revenue"])
    economics = {
        "arbitrage_net_cny": arbitrage_net,
        "agc_charge_cny": agc_charge,
        "freq_charge_cny": freq_charge,
        "combined_net_cny": arbitrage_net - agc_charge - freq_charge,
        "assessment_price_cny_per_mwh": flat_price,
    }

    warnings = []
    if freq["fail_events"] > 0:
        warnings.append(
            "峰段一次调频上调贡献不足：套利放电占用了上调裕度，须联合优化或预留调频容量。"
        )
    if agc["fail_intervals"] > 0:
        warnings.append("AGC 出现不合格时段：检查速率能力、精度门槛与通信可用率。")

    out_dir.mkdir(parents=True, exist_ok=True)

    dispatch_rows = []
    for i in range(POINTS):
        dispatch_rows.append(
            {
                "interval": i,
                "time": _time_label(i),
                "segment": profile["segment"][i],
                "price_cny_per_mwh": profile["price"][i],
                "p_charge_mw": schedule["p_charge_mw"][i],
                "p_discharge_mw": schedule["p_discharge_mw"][i],
                "p_import_mw": schedule["p_import_mw"][i],
                "p_export_mw": schedule["p_export_mw"][i],
                "soc": schedule["soc"][i],
            }
        )
    _write_csv(
        out_dir / "dispatch.csv",
        dispatch_rows,
        [
            "interval",
            "time",
            "segment",
            "price_cny_per_mwh",
            "p_charge_mw",
            "p_discharge_mw",
            "p_import_mw",
            "p_export_mw",
            "soc",
        ],
    )
    _write_csv(
        out_dir / "agc.csv",
        agc["rows"],
        [
            "interval",
            "time",
            "agc_signal_mw",
            "required_rate_mw_per_min",
            "rate_pass",
            "precision_pass",
            "assessed_mwh",
        ],
    )
    _write_csv(
        out_dir / "freq.csv",
        freq["rows"],
        [
            "interval",
            "time",
            "segment",
            "freq_deviation_hz",
            "theoretical_mw",
            "actual_mw",
            "theoretical_mwh",
            "actual_mwh",
            "contribution_ratio",
            "assessed_mwh",
        ],
    )

    summary = {
        "instance_id": config["meta"]["instance_id"],
        "rule_version": config["meta"]["rule_version"],
        "data_cutoff": config["meta"]["data_cutoff"],
        "profile": {
            "file": str(data_path),
            "points": POINTS,
            "price_peak_cny_per_mwh": max(profile["price"]),
            "price_valley_cny_per_mwh": min(profile["price"]),
            "freq_events": freq["events"],
        },
        "policy_fingerprint": _fingerprint(config["policy"]),
        "provenance": parsed["report"],
        "arbitrage": {
            "charge_mwh": arbitrage["charge_mwh"],
            "discharge_mwh": arbitrage["discharge_mwh"],
            "throughput_mwh": arbitrage["throughput_mwh"],
            "equivalent_cycles": arbitrage["equivalent_cycles"],
            "charge_cost_cny": arbitrage["charge_cost"],
            "discharge_revenue_cny": arbitrage["discharge_revenue"],
            "degradation_cost_cny": arbitrage["degradation_cost"],
            "net_revenue_cny": arbitrage_net,
            "terminal_soc": arbitrage["terminal_soc"],
        },
        "agc": {
            "assessed_mwh": agc["assessed_mwh"],
            "max_required_rate_mw_per_min": agc["max_required_rate_mw_per_min"],
            "rate_capability_mw_per_min": agc["rate_capability_mw_per_min"],
            "precision_pass": agc["precision_pass"],
            "fail_intervals": agc["fail_intervals"],
        },
        "primary_frequency": {
            "assessed_mwh": freq["assessed_mwh"],
            "theoretical_mwh": freq["theoretical_mwh"],
            "actual_mwh": freq["actual_mwh"],
            "aggregate_contribution_ratio": freq["aggregate_contribution_ratio"],
            "events": freq["events"],
            "fail_events": freq["fail_events"],
        },
        "economics": economics,
        "warnings": warnings,
        "files": [
            "dispatch.csv",
            "agc.csv",
            "freq.csv",
            "summary.json",
            "review.md",
        ],
        "disclaimer": config["meta"]["disclaimer"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(out_dir / "review.md", parsed, arbitrage, agc, freq, economics)

    print(
        f"实例：{config['meta']['instance_id']} / 储能 "
        f"{parsed['storage']['power']:.0f} MW / {parsed['storage']['capacity']:.0f} MWh"
    )
    print(
        f"套利净收益 {arbitrage_net:,.0f} 元 → AGC 考核 {agc_charge:,.0f} 元 / "
        f"一次调频考核 {freq_charge:,.0f} 元 → 综合净收益 {economics['combined_net_cny']:,.0f} 元/日"
    )
    print(f"输出目录：{out_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", default=str(HERE / "instance.json"))
    parser.add_argument("--out", default=str(HERE / "out"))
    parser.add_argument("--demo", action="store_true", help="run the bundled synthetic day")
    parser.add_argument("--check-config", action="store_true", help="validate the instance only")
    args = parser.parse_args()

    instance_path = Path(args.instance)
    try:
        parsed = load_config(instance_path)
        if args.check_config:
            config = parsed["config"]
            print(f"配置校验通过：{config['meta']['instance_id']}")
            for item in parsed["report"]:
                print(f"  {item['block']:<24} {item['grade']:<5} {item['source'][:60]}")
            t = parsed["tariff"]
            print(
                f"  电价 峰/平/谷/午间 = {t['peak']:.0f} / {t['flat']:.0f} / "
                f"{t['valley']:.0f} / {t['midday']:.0f} 元/MWh"
            )
            s = parsed["storage"]
            print(
                f"  储能 {s['power']:.0f} MW / {s['capacity']:.0f} MWh；RTE {s['rte']:.2f}；"
                f"SOC {s['soc_min']:.0%}-{s['soc_max']:.0%}；退化 {s['degradation']:.3f} 元/kWh"
            )
            a = parsed["assessment"]
            print(
                f"  AGC 速率 {a['agc_rate']:.0f} MW/min；精度 {a['agc_prec_err']:.0%}/"
                f"{a['agc_prec_thr']:.0%}；一次调频 R {a['droop']:.0%}；"
                f"峰段上调 {a['peak_avail']:.0f} MW；贡献门槛 {a['contribution_thr']:.0%}"
            )
            return
        if not args.demo:
            print("请使用 --demo 运行合成数据，或 --check-config 只做配置校验。")
            raise SystemExit(2)
        run(instance_path, Path(args.out) / "demo", True)
    except ConfigError as exc:
        print(f"配置错误：{exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()