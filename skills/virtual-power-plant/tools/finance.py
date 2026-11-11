"""园区 VPP 财务算例（知识模块《虚拟电厂聚合调度与商业模式》§8.3–8.4，D 级合成）。

口径与单位：金额 万元（除电价外）、电量 MWh、套利净价差 元/kWh、
需量电价 元/kW·月、功率 MW、期限 年、折现率与税率均为无量纲小数。

现金流为「按正文参数重建的合成序列（D 级）」：t=0 为 −CAPEX，t=1..10 为等额
税后经营现金流（直线折旧 10 年、所得税 25%、无残值、无营运资金、无建设期）。
正文未给出逐年现金流明细，本模块由 §8.3 的收入/成本/折旧/税率参数重建该序列；
若正文与代码漂移，selftest.py 会失败。

注意两处舍入口径（不硬凑数字，只保留正文精度）：
- 正文"所得税 57.2 万元"是 228.6×25%=57.15 的四舍五入显示值；
- 正文"税后经营现金流 311.4 万元"是 368.6−57.15=311.45 的显示值。
NPV/IRR/回收期均按未舍入的 311.45 计算，否则 NPV 为 689.5 而非正文 689.9。
"""

from __future__ import annotations


# §8.3 假设（D 级合成）。所有金额单位万元，除非字段名另有说明。
BASE = {
    "capex_wan": 1400.0,          # 储能 1200（1.2 元/Wh）+ 控制与平台 200
    "life_years": 10,             # 运营期/折旧期 10 年
    "depreciation_years": 10,
    "discount_rate": 0.08,        # 折现率 8%
    "tax_rate": 0.25,             # 所得税 25%
    "opex_wan": 70.0,             # 年 OPEX
    "arbitrage_mwh": 5940.0,      # 年放电量 MWh
    "arbitrage_spread": 0.40,     # 套利净价差 元/kWh
    "demand_mw": 3.0,             # 需量管理削峰 MW
    "demand_price": 40.0,         # 需量电价 元/kW·月
    "ancillary_wan": 30.0,        # 辅助服务净收益 万元/年
    "dr_wan": 27.0,               # DR 净收益 万元/年（10 次、8 MW×2 h）
}


def revenue_breakdown(params):
    """四品种年收入与占比（万元 / 无量纲占比）。

    套利 = 年放电量 MWh × 1000 kWh/MWh × 净价差 元/kWh / 10000；
    需量 = 削峰 MW × 1000 kW/MW × 元/kW·月 × 12 月 / 10000；
    辅助服务与 DR 直接取给定净收益。
    返回 dict：四个分项、total 合计、shares 各分项占合计比例。
    """
    arbitrage = params["arbitrage_mwh"] * 1000.0 * params["arbitrage_spread"] / 10000.0
    demand = params["demand_mw"] * 1000.0 * params["demand_price"] * 12.0 / 10000.0
    ancillary = params["ancillary_wan"]
    dr = params["dr_wan"]
    total = arbitrage + demand + ancillary + dr
    return {
        "arbitrage": arbitrage,
        "demand": demand,
        "ancillary": ancillary,
        "dr": dr,
        "total": total,
        "shares": {
            "arbitrage": arbitrage / total,
            "demand": demand / total,
            "ancillary": ancillary / total,
            "dr": dr / total,
        },
    }


def income_statement(revenue_wan, opex_wan, depreciation_wan, tax_rate=0.25):
    """利润表 → 税后经营现金流（单位：万元）。

    EBITDA = 年收入 − OPEX；税前利润 = EBITDA − 折旧；
    所得税 = max(税前利润, 0) × 税率；
    税后经营现金流 = EBITDA − 所得税（等价于 净利润 + 折旧）。
    返回 dict：revenue、opex、ebitda、depreciation、pretax、income_tax、net_profit、
    operating_cash_flow。
    """
    ebitda = revenue_wan - opex_wan
    pretax = ebitda - depreciation_wan
    income_tax = max(pretax, 0.0) * tax_rate
    net_profit = pretax - income_tax
    return {
        "revenue": revenue_wan,
        "opex": opex_wan,
        "ebitda": ebitda,
        "depreciation": depreciation_wan,
        "pretax": pretax,
        "income_tax": income_tax,
        "net_profit": net_profit,
        "operating_cash_flow": ebitda - income_tax,
    }


def build_cashflows(params):
    """构造「按正文参数重建的合成序列（D 级）」。

    cashflows[0] = −CAPEX（万元），cashflows[1..life] = 等额税后经营现金流（万元）。
    折旧 = CAPEX / 折旧年限（直线法，故 CAPEX+20% 情景的税盾同步变化）。
    返回 (cashflows, details)，details 含 revenue / depreciation / income 三块。
    """
    revenue = revenue_breakdown(params)
    depreciation = params["capex_wan"] / params["depreciation_years"]
    income = income_statement(
        revenue["total"], params["opex_wan"], depreciation, params["tax_rate"]
    )
    cashflows = [-params["capex_wan"]] + [
        income["operating_cash_flow"]
    ] * params["life_years"]
    return cashflows, {"revenue": revenue, "depreciation": depreciation, "income": income}


def npv(rate, cashflows):
    """净现值（金额单位与 cashflows 一致，本模块为万元）。

    cashflows[0] 为 t=0（通常为 −CAPEX），第 t 期折现因子 1/(1+rate)^t。
    rate 须 > −1，否则抛 ValueError。
    """
    if rate <= -1:
        raise ValueError("rate must be greater than -1")
    return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows, low=-0.99, high=10.0, tol=1e-10, max_iter=10000):
    """内部收益率（无量纲小数），二分法求解。

    前置条件：现金流至少一正一负；在 [low, high] 内 NPV 必须变号。
    收敛判据：|NPV(mid)| < tol（金额单位）或区间半宽 < tol；迭代上限 max_iter。
    无解（无正负号变化、区间内不变号、迭代不收敛）一律返回 None，不抛异常、不外推。
    low 默认 −0.99（利率 > −1），high 默认 10.0 覆盖高收益情景。
    """
    if not any(cf < 0 for cf in cashflows) or not any(cf > 0 for cf in cashflows):
        return None
    f_low = npv(low, cashflows)
    f_high = npv(high, cashflows)
    if f_low * f_high > 0:
        return None
    for _ in range(max_iter):
        mid = (low + high) / 2.0
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol or (high - low) / 2.0 < tol:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return None


def static_payback(cashflows):
    """静态回收期（年）：累计未折现现金流首次转正的线性插值年份。

    cashflows[0] 为 t=0 投资；运营期内未回收返回 None。
    """
    cumulative = cashflows[0]
    if cumulative >= 0:
        return 0.0
    for year, cf in enumerate(cashflows[1:], start=1):
        previous = cumulative
        cumulative += cf
        if cumulative >= 0 and cf != 0:
            return year - 1 + (-previous) / cf
    return None


def discounted_payback(rate, cashflows):
    """动态回收期（年）：累计折现现金流首次转正的线性插值年份。

    rate 为无量纲折现率（如 0.08）；运营期内未回收返回 None。
    """
    cumulative = cashflows[0]
    if cumulative >= 0:
        return 0.0
    for year, cf in enumerate(cashflows[1:], start=1):
        discounted = cf / (1.0 + rate) ** year
        previous = cumulative
        cumulative += discounted
        if cumulative >= 0 and discounted != 0:
            return year - 1 + (-previous) / discounted
    return None


def evaluate(params):
    """一次性给出 §8.3 全部指标（万元 / 无量纲 / 年）。

    返回 dict：revenue（收入结构）、income（利润表）、depreciation、cashflows、
    npv（按 params["discount_rate"]）、irr、static_payback、discounted_payback。
    """
    cashflows, details = build_cashflows(params)
    rate = params["discount_rate"]
    return {
        "revenue": details["revenue"],
        "income": details["income"],
        "depreciation": details["depreciation"],
        "cashflows": cashflows,
        "npv": npv(rate, cashflows),
        "irr": irr(cashflows),
        "static_payback": static_payback(cashflows),
        "discounted_payback": discounted_payback(rate, cashflows),
    }


def scenario(**overrides):
    """基于 BASE 生成敏感性情景参数（浅拷贝后覆盖），用于 §8.4 四组情景。"""
    params = dict(BASE)
    params.update(overrides)
    return params
