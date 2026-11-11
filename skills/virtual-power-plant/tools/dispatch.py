"""单日能量套利收益（知识模块《虚拟电厂聚合调度与商业模式》§6.3，D 级合成算例）。

口径与单位：能量 MWh；价格 元/MWh（正文 0.30 / 1.00 / 0.03 元/kWh 分别换算为
300 / 1000 / 30 元/MWh）；金额 元，年化后为 万元。
算例口径：可用能量 18 MWh、日循环 1 次、AC 侧 1:1 能量搬移、不计 RTE、
退化成本按充电量与放电量双侧计量；纯能量套利，未给调频/备用留 SOC 裕度。
"""

from __future__ import annotations


def daily_arbitrage(
    energy_mwh=18.0,
    charge_price=300.0,
    discharge_price=1000.0,
    degradation_price=30.0,
    cycles=1.0,
):
    """单日纯套利结算（单位见模块 docstring，返回金额均为 元）。

    energy_mwh 单次循环充/放电能量 MWh（AC 侧 1:1）；charge_price、discharge_price、
    degradation_price 为 元/MWh；cycles 日循环次数。
    充电成本 = 充电量 × 充电价；放电收入 = 放电量 × 放电价；
    退化成本 = (充电量 + 放电量) × 退化单价（正文 (18+18) MWh × 30 元/MWh）；
    日净收益 = 放电收入 − 充电成本 − 退化成本。
    返回 dict：上述四项及 charge_energy_mwh、discharge_energy_mwh。
    """
    charge_energy = energy_mwh * cycles
    discharge_energy = energy_mwh * cycles
    charge_cost = charge_energy * charge_price
    discharge_revenue = discharge_energy * discharge_price
    degradation_cost = (charge_energy + discharge_energy) * degradation_price
    net = discharge_revenue - charge_cost - degradation_cost
    return {
        "charge_energy_mwh": charge_energy,
        "discharge_energy_mwh": discharge_energy,
        "charge_cost": charge_cost,
        "discharge_revenue": discharge_revenue,
        "degradation_cost": degradation_cost,
        "net": net,
    }


def annual_net(net_per_day_yuan, days=330):
    """年净收益（万元）= 日净收益（元）× 年运行天数 / 10000。"""
    return net_per_day_yuan * days / 10000.0


def schedule_energy(segments):
    """校核 §6.3 调度时段表：每段 (功率 MW, 时长 h) → 电量 MWh。

    返回 {"segments_mwh": [...], "total_mwh": 合计}；用于核对
    00–04 充电 4.5 MW×4 h=18 MWh、10–12 放电 5 MW×2 h=10 MWh、
    18–20 放电 4 MW×2 h=8 MWh，放电合计 18 MWh 与充电量相等。
    """
    segments_mwh = [power_mw * hours for power_mw, hours in segments]
    return {"segments_mwh": segments_mwh, "total_mwh": sum(segments_mwh)}
