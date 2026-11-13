"""断言锁 SKILL.md 与《虚拟电厂聚合调度与商业模式》的算例，正文与代码漂移即失败，算例均为合成（D 级）。

从仓库根目录运行（同级 import 即可，无需安装包）：

    python skills/virtual-power-plant/tools/selftest.py

或在本目录运行：python selftest.py

四组算例：
- A 资源聚合能力折算（知识模块 §2.3）：12.25 MW / 22.25 MWh → 9.31 MW / 约 2.4 h；
- B 单日调度收益（§6.3）：18,000 − 5,400 − 1,080 = 11,520 元；
- C CBL 基线与有效性认定（§7.2、SKILL §11.2/§12）：近 5 同类日、±25% 剔除、
  修正系数、浙江「最大/平均负荷双低于基线 + 响应率 ≥50%」；
- D 园区 VPP 财务与敏感性（§8.3–8.4）：438.6 / 368.6 / 689.9 / 约 18.0% / 4.49 年。

D 组现金流为「按正文参数重建的合成序列（D 级）」：t=0 为 −CAPEX，t=1..10 为等额
税后经营现金流（直线折旧、所得税 25%、无残值）。正文未给逐年现金流明细，故 NPV/IRR
由 §8.3 参数重建并锁定结论，而不是硬凑数字。

因参数不足改为结构性验证 / 容差覆盖的正文数字（不硬凑）：
- CAPEX+20% 情景 IRR 原写「约 16.3%」，按 §8.3 参数复算为 13.71%，与同表
  NPV 456.8 / 回收期 5.28 不自洽；2026-11-11 已更正正文为「约 13.7%」，
  本文件同时锁定 13.71 与「增加投资 → IRR 下降」的结构结论。
- 基准静态回收期 4.49（重建 4.4951）、需量归零 NPV −34.7（重建 −34.83）、
  所得税显示 57.2（精确 57.15）属正文四舍五入/截断差异，用显式容差覆盖，
  并另加「需量归零 → NPV 转负」「价差下降 → NPV 下降约 300 万元」结构断言。
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import aggregation
import cbl
import dispatch
import finance


_COUNT = 0


def close(name, actual, expected, tol):
    """数值断言：|actual − expected| > tol 即失败；通过则打印并累计断言数。"""
    global _COUNT
    if abs(actual - expected) > tol:
        raise AssertionError(f"{name}: {actual} != {expected} (tol {tol})")
    _COUNT += 1
    print(f"ok  {name:<54} {actual:,.4f}")


def check(condition, name):
    """布尔断言：条件为假即失败；通过则打印并累计断言数。"""
    global _COUNT
    if not condition:
        raise AssertionError(name)
    _COUNT += 1
    print(f"ok  {name}")


def main():
    # ------------------------------------------------------------------ A
    # 资源聚合能力折算：§2.3 分项表 + 同时率 0.8 / 可用率 0.95。
    resources = aggregation.park_resources()
    check(
        [name for name, _ in resources] == ["工业负荷", "楼宇空调", "储能"],
        "A 分项顺序与 §2.3 表格一致",
    )
    industrial, hvac, storage = (item for _, item in resources)
    close("A 工业负荷可调功率 20MW×30% (MW)", industrial["power_mw"], 6.0, 1e-9)
    close("A 工业负荷可调电量 6MW×2h (MWh)", industrial["energy_mwh"], 12.0, 1e-9)
    close("A 楼宇空调可调功率 5MW×25% (MW)", hvac["power_mw"], 1.25, 1e-9)
    close("A 楼宇空调可调电量 1.25MW×1h (MWh)", hvac["energy_mwh"], 1.25, 1e-9)
    close("A 储能可调功率 (MW)", storage["power_mw"], 5.0, 1e-9)
    close("A 储能可用电量 10MWh×90% (MWh)", storage["energy_mwh"], 9.0, 1e-9)
    close(
        "A 分项功率加总 = 理论合计 (MW)",
        sum(item["power_mw"] for _, item in resources),
        12.25,
        1e-9,
    )
    close(
        "A 分项电量加总 = 理论合计 (MWh)",
        sum(item["energy_mwh"] for _, item in resources),
        22.25,
        1e-9,
    )

    agg = aggregation.aggregate(resources, coincidence=0.8, availability=0.95)
    close("A 理论合计功率 (MW)", agg["theoretical_power_mw"], 12.25, 1e-9)
    close("A 理论合计电量 (MWh)", agg["theoretical_energy_mwh"], 22.25, 1e-9)
    close("A 综合折算系数 0.8×0.95", agg["derating"], 0.76, 1e-9)
    close("A 理论可申报功率 (MW)", agg["declared_power_mw"], 9.31, 1e-9)
    close("A 电量不折减 (MWh)", agg["declared_energy_mwh"], 22.25, 1e-9)
    close("A 等效持续时长 ≈2.4 h（电量加权）", agg["duration_h"], 2.4, 0.02)
    check(
        agg["declared_power_mw"] < agg["theoretical_power_mw"],
        "A 9.31 MW 小于理论合计（是理论可申报，非额定）",
    )
    band = aggregation.measured_band(agg["declared_power_mw"])
    close("A 实测能力区间下限 50% (MW)", band[0], 4.655, 1e-9)
    close("A 实测能力区间上限 80% (MW)", band[1], 7.448, 1e-9)
    check(band[1] < agg["declared_power_mw"], "A 实测上限仍低于申报（申报≠实测）")

    # ------------------------------------------------------------------ B
    # 单日能量套利：§6.3，18 MWh、300 / 1000 / 30 元/MWh、AC 侧 1:1。
    day = dispatch.daily_arbitrage()
    close("B 充电量 (MWh)", day["charge_energy_mwh"], 18.0, 1e-9)
    close("B 放电量 (MWh)", day["discharge_energy_mwh"], 18.0, 1e-9)
    close("B 充电成本 18MWh×300 (元)", day["charge_cost"], 5400.0, 1e-9)
    close("B 放电收入 18MWh×1000 (元)", day["discharge_revenue"], 18000.0, 1e-9)
    close("B 退化成本 (18+18)MWh×30 (元)", day["degradation_cost"], 1080.0, 1e-9)
    close("B 日净收益 (元)", day["net"], 11520.0, 1e-9)
    close("B 日净收益 = 18000−5400−1080 (元)", 18000.0 - 5400.0 - 1080.0, day["net"], 1e-9)
    close("B 年净收益 330 日 (万元)", dispatch.annual_net(day["net"]), 380.2, 0.1)
    close("B 峰谷价差 1.00−0.30 (元/MWh)", 1000.0 - 300.0, 700.0, 1e-9)
    seg = dispatch.schedule_energy([(4.5, 4.0), (5.0, 2.0), (4.0, 2.0)])
    close("B 00–04 谷段充电量 (MWh)", seg["segments_mwh"][0], 18.0, 1e-9)
    close("B 10–12 峰段放电量 (MWh)", seg["segments_mwh"][1], 10.0, 1e-9)
    close("B 18–20 晚峰放电量 (MWh)", seg["segments_mwh"][2], 8.0, 1e-9)
    close(
        "B 两段放电合计 (MWh)",
        seg["segments_mwh"][1] + seg["segments_mwh"][2],
        18.0,
        1e-9,
    )
    check(
        seg["segments_mwh"][0] == seg["segments_mwh"][1] + seg["segments_mwh"][2],
        "B AC 侧 1:1 能量搬移：充电量 = 放电量",
    )
    check(day["net"] > 0, "B 纯套利日净收益为正")
    check(
        dispatch.daily_arbitrage(charge_price=400.0)["net"] < day["net"],
        "B 充电价上升 → 日净收益下降（单调性）",
    )

    # ------------------------------------------------------------------ C
    # CBL：合成同类日（4 段 ×1 h，单位 MW；日电量 = 曲线之和 MWh）。
    days = [
        {"energy_mwh": 100.0, "curve_mw": [25.0, 26.0, 24.0, 25.0]},  # 最近
        {"energy_mwh": 100.0, "curve_mw": [26.0, 25.0, 25.0, 24.0]},
        {"energy_mwh": 100.0, "curve_mw": [24.0, 25.0, 26.0, 25.0]},
        {"energy_mwh": 100.0, "curve_mw": [25.0, 25.0, 25.0, 25.0]},
        {"energy_mwh": 160.0, "curve_mw": [40.0, 40.0, 40.0, 40.0]},  # 异常日
        {"energy_mwh": 100.0, "curve_mw": [25.0, 25.0, 25.0, 25.0]},  # 更早，不入选
        {"energy_mwh": 100.0, "curve_mw": [25.0, 25.0, 25.0, 25.0]},
    ]
    base = cbl.customer_baseline(days)
    close("C 最近同类日数 = 5", base["candidates"], 5, 0)
    close("C 候选集日均电量 (MWh)", base["mean_energy_mwh"], 112.0, 1e-9)
    close("C 剔除异常日数 = 1", base["dropped"], 1, 0)
    close("C 保留相似日数 = 4", base["kept"], 4, 0)
    close("C 基线点1 (MW)", base["baseline_mw"][0], 25.0, 1e-9)
    close("C 基线点2 (MW)", base["baseline_mw"][1], 25.25, 1e-9)
    close("C 基线点3 (MW)", base["baseline_mw"][2], 25.0, 1e-9)
    close("C 基线点4 (MW)", base["baseline_mw"][3], 24.75, 1e-9)
    close("C 基线最大负荷 (MW)", max(base["baseline_mw"]), 25.25, 1e-9)
    close("C 基线平均负荷 (MW)", sum(base["baseline_mw"]) / 4, 25.0, 1e-9)
    check(max(base["baseline_mw"]) < 40.0, "C 40 MW 异常日未污染基线")
    adjusted = cbl.customer_baseline(days, adjustment=1.10)
    close("C 修正系数 1.10 后基线点1 (MW)", adjusted["baseline_mw"][0], 27.5, 1e-9)
    close("C 修正系数 1.10 后基线点2 (MW)", adjusted["baseline_mw"][1], 27.775, 1e-9)

    mild = [
        {"energy_mwh": 100.0, "curve_mw": [25.0] * 4},
        {"energy_mwh": 100.0, "curve_mw": [25.0] * 4},
        {"energy_mwh": 100.0, "curve_mw": [25.0] * 4},
        {"energy_mwh": 100.0, "curve_mw": [25.0] * 4},
        {"energy_mwh": 130.0, "curve_mw": [32.5] * 4},
    ]
    within = cbl.customer_baseline(mild)
    close("C 五日候选集日均电量 (MWh)", within["mean_energy_mwh"], 106.0, 1e-9)
    close("C ±25% 内不剔除（保留 5 日）", within["kept"], 5, 0)
    close("C ±25% 内剔除数 = 0", within["dropped"], 0, 0)
    close("C 含 130 MWh 日的基线 (MW)", within["baseline_mw"][0], 26.5, 1e-9)
    low = [dict(day) for day in mild]
    low[-1] = {"energy_mwh": 40.0, "curve_mw": [10.0] * 4}
    low_result = cbl.customer_baseline(low)
    close("C 低异常日同样被剔除（保留 4 日）", low_result["kept"], 4, 0)
    edge_kept, edge_dropped = cbl.filter_by_deviation(
        [{"energy_mwh": 75.0}, {"energy_mwh": 125.0}], 0.25
    )
    close("C 恰在 ±25% 边界的日子保留", len(edge_kept), 2, 0)
    over_kept, over_dropped = cbl.filter_by_deviation(
        [{"energy_mwh": 74.0}, {"energy_mwh": 126.0}], 0.25
    )
    check(
        len(over_dropped) == 2 and len(over_kept) == 0,
        "C 超过 ±25% 的日子全部剔除",
    )
    raised = False
    try:
        cbl.customer_baseline(
            [
                {"energy_mwh": 74.0, "curve_mw": [1.0]},
                {"energy_mwh": 126.0, "curve_mw": [1.0]},
            ]
        )
    except ValueError:
        raised = True
    check(raised, "C 无相似日通过筛选时抛 ValueError（不静默给空基线）")

    # 江苏 5+3 口径：保留 25%–200% 的非对称区间，边界保留。
    ratio_days = [
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 250.0, "curve_mw": [62.5]},
    ]
    ratio_kept, ratio_dropped = cbl.filter_by_ratio_bounds(ratio_days, 0.25, 2.0)
    check(
        len(ratio_kept) == 5 and not ratio_dropped,
        "C 250% 高于均值但低于 200% 上界的两倍口径：保留（非对称）",
    )
    low_ratio_days = [
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
        {"energy_mwh": 40.0, "curve_mw": [10.0]},
    ]
    low_ratio_kept, low_ratio_dropped = cbl.filter_by_ratio_bounds(low_ratio_days, 0.25, 2.0)
    check(
        len(low_ratio_kept) == 5 and not low_ratio_dropped,
        "C 40% 低于均值但高于 25% 下界口径：保留（非对称）",
    )
    edge_days = [
        {"energy_mwh": 25.0, "curve_mw": [6.25]},
        {"energy_mwh": 200.0, "curve_mw": [50.0]},
        {"energy_mwh": 75.0, "curve_mw": [18.75]},
        {"energy_mwh": 100.0, "curve_mw": [25.0]},
    ]
    edge_kept, edge_dropped = cbl.filter_by_ratio_bounds(edge_days, 0.25, 2.0)
    check(
        len(edge_kept) == 4 and not edge_dropped,
        "C 恰在 25%/200% 边界的日子保留",
    )
    out_kept, out_dropped = cbl.filter_by_ratio_bounds(
        [
            {"energy_mwh": 20.0, "curve_mw": [5.0]},
            {"energy_mwh": 280.0, "curve_mw": [70.0]},
            {"energy_mwh": 100.0, "curve_mw": [25.0]},
            {"energy_mwh": 100.0, "curve_mw": [25.0]},
        ],
        0.25,
        2.0,
    )
    check(
        len(out_dropped) == 2 and len(out_kept) == 2,
        "C 低于 25% 或高于 200% 的日子剔除",
    )
    asymmetric = cbl.customer_baseline(ratio_days, lower_ratio=0.25, upper_ratio=2.0)
    check(
        asymmetric["kept"] == 5 and asymmetric["dropped"] == 0,
        "C customer_baseline 支持非对称区间参数",
    )

    baseline_max = max(base["baseline_mw"])
    baseline_avg = sum(base["baseline_mw"]) / 4
    rate = cbl.response_rate(baseline_avg, 12.0)
    close("C 响应率 (基线 25 → 实际 12 MW)", rate, 0.52, 1e-9)
    close("C 响应率 (基线 25 → 实际 15 MW)", cbl.response_rate(baseline_avg, 15.0), 0.40, 1e-9)
    check(
        cbl.response_valid(20.0, baseline_max, 12.0, baseline_avg, rate),
        "C 双低于 + 响应率 52% → 认定有效",
    )
    check(
        cbl.response_valid(20.0, baseline_max, 12.0, baseline_avg, 0.50),
        "C 响应率恰 50% → 认定有效（≥ 门槛）",
    )
    check(
        not cbl.response_valid(20.0, baseline_max, 12.0, baseline_avg, 0.49),
        "C 响应率 49% → 无效",
    )
    check(
        not cbl.response_valid(26.0, baseline_max, 12.0, baseline_avg, rate),
        "C 最大负荷未低于基线 → 无效",
    )
    check(
        not cbl.response_valid(20.0, baseline_max, 26.0, baseline_avg, rate),
        "C 平均负荷未低于基线 → 无效",
    )
    check(
        not cbl.response_valid(26.0, baseline_max, 26.0, baseline_avg, 0.49),
        "C 三个条件全不满足 → 无效",
    )

    # ------------------------------------------------------------------ D
    # 园区 VPP 财务算例与敏感性（§8.3–8.4）。
    proj = finance.evaluate(finance.scenario())
    rev, inc = proj["revenue"], proj["income"]
    close("D 套利年收入 5940MWh×0.40 (万元)", rev["arbitrage"], 237.6, 1e-6)
    close("D 需量管理年收入 3MW×40×12 (万元)", rev["demand"], 144.0, 1e-6)
    close("D 辅助服务年收入 (万元)", rev["ancillary"], 30.0, 1e-6)
    close("D DR 年收入 (万元)", rev["dr"], 27.0, 1e-6)
    close("D 基准年收入合计 (万元)", rev["total"], 438.6, 1e-6)
    close("D 套利占比 54.2%", rev["shares"]["arbitrage"] * 100, 54.2, 0.05)
    close("D 需量占比 32.8%", rev["shares"]["demand"] * 100, 32.8, 0.05)
    close("D 辅助服务占比 6.8%", rev["shares"]["ancillary"] * 100, 6.8, 0.05)
    close("D DR 占比 6.2%", rev["shares"]["dr"] * 100, 6.2, 0.05)
    close("D 四项占比合计 = 100%", sum(rev["shares"].values()) * 100, 100.0, 1e-9)
    close("D 年收入 − OPEX = EBITDA (万元)", inc["ebitda"], 368.6, 1e-6)
    close("D 折旧 1400/10 (万元)", proj["depreciation"], 140.0, 1e-9)
    close("D 税前利润 (万元)", inc["pretax"], 228.6, 1e-6)
    close("D 所得税 57.2 万元（精确 57.15，正文四舍五入）", inc["income_tax"], 57.2, 0.1)
    close(
        "D 税后经营现金流 311.4 万元（精确 311.45）",
        inc["operating_cash_flow"],
        311.4,
        0.1,
    )
    close("D 合成现金流序列长度 = 11 (t=0..10)", len(proj["cashflows"]), 11, 0)
    close("D t=0 现金流 = −CAPEX (万元)", proj["cashflows"][0], -1400.0, 1e-9)
    close("D NPV @8% / 10 年 (万元)", proj["npv"], 689.9, 0.3)
    close("D 项目 IRR ≈18.0%", proj["irr"] * 100, 18.0, 0.05)
    close("D 静态回收期 4.49 年（重建 4.4951）", proj["static_payback"], 4.49, 0.02)
    check(
        proj["discounted_payback"] > proj["static_payback"],
        "D 动态回收期晚于静态回收期",
    )
    check(proj["discounted_payback"] < 10, "D NPV>0 → 10 年运营期内可动态回收")
    check(proj["npv"] > 0 and proj["irr"] > 0.08, "D NPV>0 与 IRR>折现率一致")

    demand_zero = finance.evaluate(finance.scenario(demand_mw=0.0))
    close("D 需量归零 年收入 (万元)", demand_zero["revenue"]["total"], 294.6, 1e-6)
    close("D 需量归零 EBITDA (万元)", demand_zero["income"]["ebitda"], 224.6, 1e-6)
    close("D 需量归零 NPV (万元)", demand_zero["npv"], -34.7, 0.3)
    close("D 需量归零 IRR ≈7.4%", demand_zero["irr"] * 100, 7.4, 0.1)
    close("D 需量归零 回收期 6.88 年", demand_zero["static_payback"], 6.88, 0.01)
    check(demand_zero["npv"] < 0, "D 结构结论：需量收益归零 → NPV 立即转负")
    check(demand_zero["irr"] < 0.08, "D 结构结论：需量归零 → IRR 跌破 8% 折现率")
    check(
        demand_zero["discounted_payback"] is None,
        "D 结构结论：NPV<0 → 运营期内无法动态回收",
    )

    spread = finance.evaluate(finance.scenario(arbitrage_spread=0.30))
    close("D 价差 −0.10 年收入 (万元)", spread["revenue"]["total"], 379.2, 1e-6)
    close("D 价差 −0.10 EBITDA (万元)", spread["income"]["ebitda"], 309.2, 1e-6)
    close("D 价差 −0.10 NPV (万元)", spread["npv"], 390.9, 0.3)
    close("D 价差 −0.10 IRR ≈13.9%", spread["irr"] * 100, 13.9, 0.1)
    close("D 价差 −0.10 回收期 5.25 年", spread["static_payback"], 5.25, 0.01)
    close(
        "D 结构结论：价差 −0.10 → NPV 下降约 300 万元",
        proj["npv"] - spread["npv"],
        300.0,
        2.0,
    )
    check(proj["npv"] - spread["npv"] > 0, "D 结构结论：价差收窄 → NPV 下降")

    capex_up = finance.evaluate(finance.scenario(capex_wan=1680.0))
    close("D CAPEX+20% 年收入不变 (万元)", capex_up["revenue"]["total"], 438.6, 1e-6)
    close("D CAPEX+20% 折旧 1680/10 (万元)", capex_up["depreciation"], 168.0, 1e-9)
    close("D CAPEX+20% NPV (万元)", capex_up["npv"], 456.8, 0.3)
    close("D CAPEX+20% 回收期 5.28 年", capex_up["static_payback"], 5.28, 0.01)
    close("D CAPEX+20% IRR ≈13.7%（2026-11-11 正文勘误）", capex_up["irr"] * 100, 13.71, 0.02)
    check(
        capex_up["irr"] < proj["irr"],
        "D 结构结论：CAPEX+20% → IRR 下降",
    )

    dr_half = finance.evaluate(finance.scenario(dr_wan=13.5))
    close("D DR 减半 年收入 (万元)", dr_half["revenue"]["total"], 425.1, 1e-6)
    close("D DR 减半 EBITDA (万元)", dr_half["income"]["ebitda"], 355.1, 1e-6)
    close("D DR 减半 NPV (万元)", dr_half["npv"], 621.9, 0.3)
    close("D DR 减半 IRR ≈17.0%", dr_half["irr"] * 100, 17.0, 0.15)
    close("D DR 减半 回收期 4.65 年", dr_half["static_payback"], 4.65, 0.01)

    check(finance.irr([100.0, 50.0, 50.0]) is None, "D IRR 无解处理：全正现金流返回 None")
    check(finance.irr([-100.0, -50.0]) is None, "D IRR 无解处理：全负现金流返回 None")
    check(
        finance.static_payback([-100.0, 10.0]) is None,
        "D 静态回收期：运营期内未回收返回 None",
    )
    check(
        abs(finance.npv(0.0, proj["cashflows"]) - (-1400.0 + 311.45 * 10)) < 1e-9,
        "D 零折现率 NPV = 名义现金流之和（自洽）",
    )

    # ------------------------------------------------------------------ E
    # 江苏快响实例包：配置、申报、情景、T+1 认定与差异桥。
    def raises(callable_, name):
        try:
            callable_()
        except ValueError:
            check(True, name)
            return
        raise AssertionError(f"{name}: expected ValueError")

    pack_dir = (
        Path(__file__).resolve().parents[1]
        / "instances"
        / "jiangsu-fast-response-2026-11"
    )
    spec = importlib.util.spec_from_file_location("jiangsu_fast_response_instance", pack_dir / "run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    instance_path = pack_dir / "instance.json"
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    report = runner.validate_instance(config)
    close("E points per day", report["points_per_day"], 96, 0)
    close("E MTU minutes", report["mtu_min"], 15, 0)
    close("E direct capability (MW)", report["capability_by_type"]["direct"], 30.66, 1e-9)
    close("E self capability (MW)", report["capability_by_type"]["self"], 10.80, 1e-9)
    close("E direct declared (MW)", report["declared_by_type"]["direct"], 26.0, 1e-9)
    close("E self declared (MW)", report["declared_by_type"]["self"], 8.6, 1e-9)
    close("E direct bid ratio", report["share_by_type"]["direct"], 0.6774624918460534, 1e-12)

    broken = json.loads(json.dumps(config))
    del broken["rules"]["fast_response"]["grade"]
    raises(lambda: runner.validate_instance(broken), "E reject missing rule grade")

    broken = json.loads(json.dumps(config))
    broken["policy"]["bid_price_cny_per_kwh"]["direct"] = 16.0
    raises(lambda: runner.validate_instance(broken), "E reject bid above the 15 CNY/kWh cap")

    broken = json.loads(json.dumps(config))
    broken["policy"]["bid_ratio"]["direct"] = 1.2
    raises(lambda: runner.validate_instance(broken), "E reject bid ratio above one")

    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_instance(
            instance_path,
            pack_dir / "data" / "history_demo.csv",
            pack_dir / "data" / "event_demo.csv",
            pack_dir / "data" / "t1_loads_demo.csv",
            pack_dir / "data" / "t1_event_demo.csv",
            Path(tmp),
        )
        summary = result["summary"]
        bridge = result["bridge"]
        close("E expected net (CNY)", summary["expected"]["net_cny"], 48400.668623613834, 1e-6)
        close("E expected CVaR (CNY)", summary["expected"]["cvar_cny"], -2000.0, 1e-6)
        close("E plan net (CNY)", bridge["plan_net_cny"], 45880.63519243314, 1e-6)
        close("E actual net (CNY)", bridge["actual_net_cny"], 53303.313111545984, 1e-6)
        close("E bridge delta (CNY)", bridge["delta_cny"], 7422.677919112844, 1e-6)
        check(abs(bridge["identity_gap"]) < 1e-6, "E bridge identity closes")
        check(len(bridge["buckets"]) == 11, "E bridge has eleven buckets")
        check(
            all(item["kept"] == 4 and item["dropped"] == 1 for item in summary["baseline"].values()),
            "E every baseline keeps four of five candidate days",
        )
        close("E direct actual shed (MW)", summary["actual"]["by_type"]["direct"]["shed_mw"], 24.20, 1e-9)
        close("E self paid shed capped (MW)", summary["actual"]["by_type"]["self"]["paid_shed_mw"], 10.32, 1e-9)
        for name in (
            "bid_sheet.csv",
            "capability.csv",
            "scenario_table.csv",
            "delivery_detail.csv",
            "summary.json",
            "bridge.json",
            "bridge.csv",
            "review.md",
        ):
            check((Path(tmp) / name).exists(), f"E writes {name}")

    print(f"\nAll VPP self-tests passed: {_COUNT} assertions.")


if __name__ == "__main__":
    main()
