"""合同与资产估值：远期曲线、捕获率、期权型条款、merchant tail 与分布输出（零依赖，仅标准库）。

锁定 SKILL.md 与 knowledge/跨国PPA与绿证-2026-11.md 的合同估值口径：

* 远期曲线折现：``PV = Σ F_t × Q_t / (1+r)^t``；远期是市场定价，
  不是期望电价，只能做 base case 的锚。
* 捕获价：``capture = Σ(price_i × output_i) / Σ output_i``；
  捕获率 = 捕获价 ÷ 同期基荷均价。价格与捕获率通常负相关，独立
  抽样会高估收入上行。
* 期权型条款：floor 是卖方买入 put，cap 是卖方卖出 call，
  collar 是两者净额；权利金必须计入有效价，不能把 floor 当免费保险。
* CfD：``(strike − reference) × volume``，reference 口径决定基差。
* Tolling：容量费 × 可用容量 × 可用率 − OPEX − 退化 − 罚则；
  保本容量费 = (merchant 净收入 + 成本) ÷ (容量 × 可用率)。
* Merchant tail：分段折现，tail 用更高折现率或现金流 haircut；
  不要用 PPA 期价格外推。
* 分布输出：P10/P50/P90 按分位数定义（P10 为下行），与风电资源
  评估的 P90 保证率方向相反，引用时必须写明。

所有算例均为合成/演示口径（D 级），不构成投资、法律或税务意见。
本模块不实现债务摊销表、税盾和通胀指数化，相关计算归
``storage-investment-operations/tools/finance.py``。
"""

from __future__ import annotations

import math
import random


def pv(cashflows, rate):
    """把从第 1 期开始的现金流折现到第 0 期。"""
    return sum(cf / (1.0 + rate) ** (t + 1) for t, cf in enumerate(cashflows))


def npv(cashflows, rate):
    """净现值；``cashflows[0]`` 视为第 0 期（通常是初始投资）。"""
    return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows, low=-0.9999, high=10.0, tol=1e-10):
    """二分法求 IRR；要求现金流至少有一次正负号变化。"""
    if not cashflows:
        raise ValueError("cashflows 不能为空")
    if all(cf >= 0.0 for cf in cashflows) or all(cf <= 0.0 for cf in cashflows):
        raise ValueError("IRR 需要正负现金流")

    def f(r):
        return npv(cashflows, r)

    f_low, f_high = f(low), f(high)
    if f_low * f_high > 0.0:
        raise ValueError("给定区间内未找到 IRR")
    for _ in range(300):
        mid = (low + high) / 2.0
        f_mid = f(mid)
        if abs(f_mid) < tol or (high - low) < tol:
            return mid
        if f_low * f_mid < 0.0:
            high, f_high = mid, f_mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2.0


def annuity_factor(years, rate):
    """等额年金的现值因子；零利率时退化为年限。"""
    if years < 0:
        raise ValueError("years 不能为负")
    if abs(rate) < 1e-12:
        return float(years)
    return (1.0 - (1.0 + rate) ** (-years)) / rate


def forward_strip_pv(forward_prices, volumes, discount_rate):
    """按远期曲线逐期折现：``Σ F_t × Q_t / (1+r)^t``。"""
    if len(forward_prices) != len(volumes):
        raise ValueError("forward_prices 与 volumes 长度必须一致")
    return sum(
        price * volume / (1.0 + discount_rate) ** (t + 1)
        for t, (price, volume) in enumerate(zip(forward_prices, volumes))
    )


def capture_price(prices, outputs):
    """加权捕获价：``Σ(price × output) / Σ output``。"""
    if len(prices) != len(outputs):
        raise ValueError("prices 与 outputs 长度必须一致")
    total_output = sum(outputs)
    if total_output <= 0.0:
        raise ValueError("outputs 之和必须为正")
    return sum(p * q for p, q in zip(prices, outputs)) / total_output


def capture_rate(capture, baseload_price):
    """捕获率 = 捕获价 ÷ 同期基荷均价。"""
    if baseload_price <= 0.0:
        raise ValueError("baseload_price 必须为正")
    return capture / baseload_price


def floor_payoff(price, floor, volume):
    """卖方 floor 的补偿：``max(floor − price, 0) × volume``。"""
    return max(floor - price, 0.0) * volume


def cap_payoff(price, cap, volume):
    """卖方 cap 让渡的上行：``max(price − cap, 0) × volume``。"""
    return max(price - cap, 0.0) * volume


def collar_payoff(price, floor, cap, volume):
    """Collar 净补偿：floor 补偿减 cap 让渡；可为负。"""
    if floor > cap:
        raise ValueError("floor 不能高于 cap")
    return floor_payoff(price, floor, volume) - cap_payoff(price, cap, volume)


def cfd_settlement(strike, reference, volume):
    """CfD 结算：``(strike − reference) × volume``；正数由买方补足。"""
    return (strike - reference) * volume


def proxy_revenue_swap(fixed_revenue, actual_revenue):
    """Proxy revenue swap：固定收入减实际收入；正数为对手方补足。"""
    return fixed_revenue - actual_revenue


def tolling_gross_revenue(capacity_mw, fee_per_mw_year, availability=1.0):
    """Tolling 容量费毛收入。"""
    if capacity_mw < 0.0:
        raise ValueError("capacity_mw 不能为负")
    if not 0.0 <= availability <= 1.0:
        raise ValueError("availability 必须在 [0, 1]")
    return capacity_mw * fee_per_mw_year * availability


def tolling_net_revenue(
    capacity_mw,
    fee_per_mw_year,
    availability=1.0,
    opex=0.0,
    degradation=0.0,
    penalty=0.0,
):
    """Tolling 净收入：容量费毛收入减 OPEX、退化与性能罚则。"""
    return (
        tolling_gross_revenue(capacity_mw, fee_per_mw_year, availability)
        - opex
        - degradation
        - penalty
    )


def tolling_breakeven_fee(
    merchant_net,
    opex,
    degradation,
    penalty,
    capacity_mw,
    availability=1.0,
):
    """与 merchant 净收入相等的容量费；低于它 tolling 不划算。"""
    if capacity_mw <= 0.0:
        raise ValueError("capacity_mw 必须为正")
    if not 0.0 < availability <= 1.0:
        raise ValueError("availability 必须在 (0, 1]")
    return (merchant_net + opex + degradation + penalty) / (
        capacity_mw * availability
    )


def merchant_tail_pv(
    price,
    volume,
    years,
    discount_rate,
    escalation=0.0,
    degradation=0.0,
    capture_rate=1.0,
):
    """Merchant tail 现值；价格可 escalate，出力按 degradation 逐年衰减。"""
    if years < 0:
        raise ValueError("years 不能为负")
    if not 0.0 <= degradation <= 1.0:
        raise ValueError("degradation 必须在 [0, 1]")
    total = 0.0
    for t in range(years):
        period_price = price * (1.0 + escalation) ** t
        period_volume = volume * (1.0 - degradation) ** t
        total += (
            period_price
            * period_volume
            * capture_rate
            / (1.0 + discount_rate) ** (t + 1)
        )
    return total


def dscr(cfads, debt_service):
    """偿债覆盖率 = CFADS ÷ 年债务服务。"""
    if debt_service <= 0.0:
        raise ValueError("debt_service 必须为正")
    return cfads / debt_service


def max_debt_by_dscr(cfads, target_dscr, discount_rate, years):
    """按目标 DSCR 与等额年金反推最大债务规模。"""
    if target_dscr <= 0.0:
        raise ValueError("target_dscr 必须为正")
    annual_debt_service = cfads / target_dscr
    return annual_debt_service * annuity_factor(years, discount_rate)


def percentile(values, q):
    """经验分位数（线性插值）；``q=0.1`` 为下行 P10。"""
    if not values:
        raise ValueError("values 不能为空")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q 必须在 [0, 1]")
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def scenario_stats(values):
    """等概率情景的均值与 P10/P50/P90；概率不等时不要直接套用。"""
    if not values:
        raise ValueError("values 不能为空")
    return {
        "mean": sum(values) / len(values),
        "p10": percentile(values, 0.10),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "min": min(values),
        "max": max(values),
    }


def simulate_correlated_revenue(
    price_mean,
    price_sd,
    capture_mean,
    capture_sd,
    volume,
    rho=0.0,
    draws=10000,
    seed=42,
):
    """价格与捕获率相关的收入抽样；光伏通常取 ``rho < 0``。

    ``rho=0`` 的独立抽样会高估期望收入：价格与捕获率同向波动时，
    高价格情景往往对应低捕获率。返回抽样收入列表，供分位数与偿债测试。
    """
    if not -1.0 <= rho <= 1.0:
        raise ValueError("rho 必须在 [-1, 1]")
    if draws <= 0:
        raise ValueError("draws 必须为正")
    rng = random.Random(seed)
    residual = math.sqrt(max(0.0, 1.0 - rho * rho))
    revenues = []
    for _ in range(draws):
        z_price = rng.gauss(0.0, 1.0)
        z_capture = rho * z_price + residual * rng.gauss(0.0, 1.0)
        price = max(0.0, price_mean + price_sd * z_price)
        capture = max(0.0, capture_mean + capture_sd * z_capture)
        revenues.append(price * capture * volume)
    return revenues
