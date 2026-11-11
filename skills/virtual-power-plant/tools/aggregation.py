"""资源聚合能力折算（知识模块《虚拟电厂聚合调度与商业模式》§2.3，D 级合成算例）。

口径与单位：功率 MW、电量 MWh、持续时间 h；同时率/可用率/可调比例为无量纲小数。
算例主体：某园区 VPP 聚合 20 MW 工业负荷、5 MW 空调、5 MW/10 MWh 储能。

正文口径要点（写代码时不要"顺手改进"）：
- 分项"可调电量"= 可调功率 × 持续时间 × 可用比例，储能的 9 MWh 已含 90% 可用率；
- 同时率 0.8、可用率 0.95 只折减功率，电量 22.25 MWh 不折减；
- 等效持续时长按电量加权，即 总电量 / 折算后申报功率，不是各资源时长的简单平均；
- 9.31 MW 是"理论可申报"，不是"实测能力"（§2.4：实测常为申报的 50%~80%）。
"""

from __future__ import annotations


def resource_capability(rated_mw, adjustable_ratio, hours, usable_ratio=1.0):
    """单资源可调能力（§2.3 公式的算例化）。

    参数：rated_mw 额定功率 MW；adjustable_ratio 可调比例；hours 持续时间 h；
    usable_ratio 可用电量比例（储能 0.90，其余 1.0）。
    返回 dict：power_mw 可调功率 MW、hours 持续时间 h、energy_mwh 可调电量 MWh。
    """
    power_mw = rated_mw * adjustable_ratio
    energy_mwh = power_mw * hours * usable_ratio
    return {"power_mw": power_mw, "hours": hours, "energy_mwh": energy_mwh}


def park_resources():
    """正文 §2.3 分项表（D 级合成），顺序与表格一致。

    返回 [(名称, 能力 dict)]；能力 dict 见 resource_capability。
    工业负荷 20 MW × 30% × 2 h = 12 MWh；楼宇空调 5 MW × 25% × 1 h = 1.25 MWh；
    储能 5 MW × 2 h × 90% = 9 MWh（额定 10 MWh）。
    """
    return [
        ("工业负荷", resource_capability(20.0, 0.30, 2.0)),
        ("楼宇空调", resource_capability(5.0, 0.25, 1.0)),
        ("储能", resource_capability(5.0, 1.00, 2.0, usable_ratio=0.90)),
    ]


def aggregate(resources, coincidence=0.8, availability=0.95):
    """聚合可调能力折算（单位：MW / MWh / h）。

    resources: [(名称, 能力 dict)]，能力 dict 含 power_mw 与 energy_mwh。
    coincidence 同时率、availability 可用率，均为无量纲小数。
    返回 dict：theoretical_power_mw 理论合计功率、theoretical_energy_mwh 理论合计电量、
    derating 综合折算系数、declared_power_mw 理论可申报功率、declared_energy_mwh 电量（不折减）、
    duration_h 等效持续时长（总电量 / 申报功率）。
    """
    total_power = sum(item["power_mw"] for _, item in resources)
    total_energy = sum(item["energy_mwh"] for _, item in resources)
    derating = coincidence * availability
    declared_power = total_power * derating
    return {
        "theoretical_power_mw": total_power,
        "theoretical_energy_mwh": total_energy,
        "derating": derating,
        "declared_power_mw": declared_power,
        "declared_energy_mwh": total_energy,
        "duration_h": total_energy / declared_power,
    }


def measured_band(declared_power_mw, low=0.5, high=0.8):
    """§2.4 口径：实测能力可能只有申报能力的 50%~80%（MW 区间）。

    参数单位 MW，low/high 无量纲；返回 (下限 MW, 上限 MW)。用于提示"申报≠实测"。
    """
    return (declared_power_mw * low, declared_power_mw * high)
