"""三节点节点价（LMP）与备用机会成本算例（零依赖，仅标准库）。

锁定 SKILL.md 第 3 章（出清与定价）、第 5.2 节（联合出清）与第 12 章
速查表中的定价算例：

* 三节点经典算例：机1 报 160 元/MWh（容量充裕）、机2 报 80 元/MWh /
  容量 1500 MW、机3 报 400 元/MWh / 容量 3000 MW；无阻塞全网 160；
  线路 1-3 限 4000 MW 时节点 2 = 280（两边际机组加权）；
  线路 1-2 限 1000 MW 时节点 2 = 640（增负荷加重阻塞）；
  线路 2-3 限 2000 MW 时节点 2 = −80（负电价）。
* LMP 分解：``πₙ = 边际电能 + 边际阻塞(μ×PTDF) + 边际网损``（§3.3）。
* 备用价格本质 = 重调度机会成本：算例 11 = 28 − 17（电能价差）；
  单独报价时电能价可不等于任何机组边际成本：22 = 20 − 5 + 7。

关于「无法纯数学复现」的说明：四个节点价（160 / 280 / 640 / −80）是
正文给出的演示算例**结果**。阻塞场景下的 LMP 依赖未公开的网络参数
（各线路电抗 / PTDF、负荷大小与节点分布、再调度细节），正文只给了
「两边际机组加权」等定性描述，未给权重。按 SKILL.md 纪律不硬凑这些
参数去「重算」出清，因此本模块：
  1) 把四个正文数字作为锁定基准常量（正文与代码漂移即自测失败）；
  2) 验证 LMP 三分量分解结构、两边际机组加权结构（权重落在 (0,1)）、
     阻塞加重的单调性、负电价、阻塞盈余与 FTR 的代数结构；
  3) 备用价 11 / 22 是纯算术，直接复现并锁定。
所有算例均为合成/演示口径。
"""

from __future__ import annotations


# ---- 正文锁定常量 -----------------------------------------------------------

GEN1_BID_CNY_PER_MWH = 160.0   # 机1：容量充裕
GEN2_BID_CNY_PER_MWH = 80.0
GEN2_CAPACITY_MW = 1500.0
GEN3_BID_CNY_PER_MWH = 400.0
GEN3_CAPACITY_MW = 3000.0

# 「容量充裕」用 float("inf") 表示，仅为复现无阻塞统一价的演示口径。
THREE_NODE_GENERATORS = (
    (GEN1_BID_CNY_PER_MWH, float("inf")),
    (GEN2_BID_CNY_PER_MWH, GEN2_CAPACITY_MW),
    (GEN3_BID_CNY_PER_MWH, GEN3_CAPACITY_MW),
)

# 三节点场景 -> 节点 2 的节点价（元/MWh），正文锁定值
THREE_NODE_NODE2_PRICES = {
    "no_congestion": 160.0,          # 无阻塞：全网统一 160
    "line_1_3_limit_4000mw": 280.0,  # 两边际机组加权
    "line_1_2_limit_1000mw": 640.0,  # 增负荷加重阻塞
    "line_2_3_limit_2000mw": -80.0,  # 负电价
}
THREE_NODE_LINE_LIMITS_MW = {
    "line_1_3_limit_4000mw": 4000.0,
    "line_1_2_limit_1000mw": 1000.0,
    "line_2_3_limit_2000mw": 2000.0,
}

# 无阻塞统一价，作为 LMP 分解中的「边际电能分量 λ」（元/MWh）。
ENERGY_COMPONENT_CNY_PER_MWH = 160.0


# ---- 三节点 LMP 结构 --------------------------------------------------------

def merit_order_marginal_price(generators, load_mw):
    """无阻塞系统边际价：按报价从低到高带满机组，取边际机组报价。

    参数 ``generators`` 为 ``(bid_cny_per_mwh, capacity_mw)`` 序列。
    单位：报价 元/MWh、容量 MW、负荷 MW、返回 元/MWh。
    口径：SMP 系统边际定价（§3.3），机组按 merit order 排序，边际机组
    所在段的报价即统一出清价；负荷超出总容量时抛 ValueError。
    """
    remaining = load_mw
    marginal = None
    for bid, capacity in sorted(generators, key=lambda g: g[0]):
        if remaining <= 0:
            break
        marginal = bid
        remaining -= capacity
    if remaining > 0:
        raise ValueError("负荷超过机组总容量，无法确定边际价")
    return marginal


def lmp_decompose(energy_component, congestion_component, loss_component=0.0):
    """LMP 三分量分解：``π = 边际电能 + 边际阻塞 + 边际网损``。

    单位：各分量与返回均为 元/MWh；阻塞分量可为负（负电价场景）。
    口径：§3.3 与第 12 章速查表；阻塞分量 = μ×PTDF。
    """
    return energy_component + congestion_component + loss_component


def lmp_congestion_component(node_price, energy_component):
    """从节点价反推阻塞分量：``节点价 − 边际电能分量``。

    单位：元/MWh。口径：算例忽略网损（0），故节点价与统一电能价之差
    全部归到阻塞分量；用于验证三节点四个价格的分解结构。
    """
    return node_price - energy_component


def implied_weight(price_low, price_high, weighted_price):
    """求使 ``w×price_low + (1−w)×price_high = weighted_price`` 的权重 ``w``。

    单位：三个价格单位一致即可，返回无量纲权重。口径：验证正文
    「节点 2 = 两边际机组加权」——机2 报 80、机3 报 400，节点价 280
    对应的 w 落在 (0,1) 即说明它确为两台边际机组报价的加权平均
    （结构验证，非重算出清）。
    """
    if price_low == price_high:
        raise ValueError("两台边际机组报价相同，无法求权重")
    return (price_high - weighted_price) / (price_high - price_low)


def congestion_surplus(price_receiving, price_sending, flow_mw):
    """阻塞盈余(元/h) = (受端节点价 − 送端节点价) × 过断面电量(MW)。

    单位：价 元/MWh、电量 MW、返回 元/h。口径：§3.4，FTR 资金来源。
    """
    return (price_receiving - price_sending) * flow_mw


def ftr_payout(mw, price_receiving, price_sending):
    """FTR 收益(元/h) = F(MW) × (受端价 − 送端价)。

    单位：价 元/MWh、F MW、返回 元/h；结果可为负（义务属性，价差为负
    须倒付）。口径：§3.4 与第 12 章速查表。
    """
    return mw * (price_receiving - price_sending)


# ---- 备用机会成本 -----------------------------------------------------------

def reserve_opportunity_cost(electric_price_high, electric_price_low):
    """备用价 = 电能价差（重调度机会成本）：``high − low``。

    单位：元/MWh。口径：§5.2「备用价格本质 = 重调度机会成本」，
    正文算例 11 = 28 − 17。
    """
    return electric_price_high - electric_price_low


def reserve_standalone_price(energy_price, avoided_cost, opportunity_cost):
    """单独报价时的备用价：``电能价 − 避开机组成本 + 机会成本``。

    单位：元/MWh。口径：§5.2「单独报价时电能价可不等于任何机组边际
    成本」，正文算例 22 = 20 − 5 + 7；三项均由正文给出，纯算术复现。
    """
    return energy_price - avoided_cost + opportunity_cost


def co_optimized_sort_price(offer_price, opportunity_cost):
    """联合出清排序价 = 申报价 + 电能市场机会成本。

    单位：元/MWh。口径：§5.2「排序价 = 申报价 + 电能市场机会成本」；
    用于验证公式结构（备用机会成本会抬高排序价）。
    """
    return offer_price + opportunity_cost
