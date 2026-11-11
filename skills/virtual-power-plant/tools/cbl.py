"""CBL 基线（customer_baseline）与响应有效性认定（SKILL.md §11.2/§12、知识模块 §7.2）。

口径与单位：负荷曲线 MW（合成数据为 4 段、每段 1 h）、日电量 MWh；
修正系数、偏离比例、响应率均为无量纲小数。

规则（正文原文）：
- 相似日取最近 5 个同类日；
- 剔除日电量偏离约 ±25% 的异常日（本实现以候选集日电量均值为参照）；
- 保留日逐点平均后乘修正系数；
- 浙江："最大/平均负荷双低于基线 + 响应率 ≥50%" 才认定有效。

所有算例数据均为合成（D 级），仅用于锁定规则本身，不代表任何真实用户负荷。
"""

from __future__ import annotations


def recent_similar_days(days, count=5):
    """取最近 count 个同类日。

    days 按时间由近到远排列：days[0] 为最近一个同类日。元素为
    {"energy_mwh": 日电量 MWh, "curve_mw": 分时负荷曲线 MW 列表}。
    返回新的列表（不修改入参）。
    """
    return list(days[:count])


def filter_by_deviation(days, deviation=0.25):
    """剔除日电量偏离候选集均值超过 ±deviation 的异常日。

    days 中每个元素须含 energy_mwh（MWh）；deviation 为无量纲比例（正文 ±25% → 0.25）。
    判据：|日电量 − 候选集均值| / 候选集均值 > deviation 即剔除（严格大于，边界保留）。
    返回 (kept, dropped) 两个列表；均值非正时不做剔除。
    """
    if not days:
        return [], []
    mean_energy = sum(day["energy_mwh"] for day in days) / len(days)
    kept, dropped = [], []
    for day in days:
        if mean_energy > 0 and abs(day["energy_mwh"] - mean_energy) / mean_energy > deviation:
            dropped.append(day)
        else:
            kept.append(day)
    return kept, dropped


def customer_baseline(days, count=5, deviation=0.25, adjustment=1.0):
    """CBL 基线负荷曲线：最近 5 个同类日 → 剔除 ±25% 异常日 → 逐点平均 × 修正系数。

    days: 按时间由近到远排列的同类日列表，元素含 energy_mwh（MWh）与 curve_mw（MW 列表，
    各日点数须一致）；count 相似日个数；deviation 剔除阈值；adjustment 修正系数。
    返回 dict：baseline_mw 基线曲线（MW 列表）、candidates 候选日数、kept 保留日数、
    dropped 剔除日数、mean_energy_mwh 候选集日均电量（MWh）、adjustment 修正系数。
    无相似日通过筛选时抛 ValueError（避免静默给出空基线）。
    """
    candidates = recent_similar_days(days, count)
    kept, dropped = filter_by_deviation(candidates, deviation)
    if not kept:
        raise ValueError("no similar day survives the +/-25% screen")
    mean_energy = sum(day["energy_mwh"] for day in candidates) / len(candidates)
    points = len(kept[0]["curve_mw"])
    baseline_mw = [
        sum(day["curve_mw"][i] for day in kept) / len(kept) * adjustment
        for i in range(points)
    ]
    return {
        "baseline_mw": baseline_mw,
        "candidates": len(candidates),
        "kept": len(kept),
        "dropped": len(dropped),
        "mean_energy_mwh": mean_energy,
        "adjustment": adjustment,
    }


def response_rate(baseline_mw, actual_mw):
    """响应率（负荷削减率）= (基线负荷 − 实际负荷) / 基线负荷，无量纲。

    baseline_mw 与 actual_mw 单位须一致（MW 或 MWh 均可，只要同口径）。
    """
    if baseline_mw <= 0:
        raise ValueError("baseline load must be positive")
    return (baseline_mw - actual_mw) / baseline_mw


def response_valid(
    actual_max_mw,
    baseline_max_mw,
    actual_avg_mw,
    baseline_avg_mw,
    rate,
    min_rate=0.50,
):
    """浙江口径的有效性认定：最大/平均负荷"双低于"基线，且响应率 ≥ 50%。

    actual_max_mw / baseline_max_mw、actual_avg_mw / baseline_avg_mw 单位 MW；
    rate 响应率、min_rate 门槛（默认 0.50）为无量纲小数。
    三个条件须同时满足，返回 bool。
    """
    return (
        actual_max_mw < baseline_max_mw
        and actual_avg_mw < baseline_avg_mw
        and rate >= min_rate
    )
