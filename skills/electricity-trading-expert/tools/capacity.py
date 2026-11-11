"""各国容量市场收入、降额/ELCC 口径与交付期折算（零依赖，仅标准库）。

锁定 SKILL.md 第 7A 章（海外市场）与第 12 章速查表中的容量算例：

* 波兰 rynek mocy：``容量收入 = 降额容量(MW) × 出清价(PLN/kW·年) × 1000``；
  2030 交付年 465.02 PLN/kW·年；电池降额 13.39% **仅适用** 2025-12 主
  拍卖 / 2030 交付年，2027 T-1 用 95%、2029 主拍卖 61.3%，禁止跨场次混用。
* 英国 GB CM：``收入 = de-rated capacity(kW) × £/kW·年``；
  T-4 2029/30 £27.10/kW·年、40.1 GW；T-1 2026/27 £5.00/kW·年、7,192 MW。
* 比利时 CRM：``收入 = 降额容量(MW) × 中标价(€/MW·年)``；
  Y-4 €27.3k/MW·年（=27,300，非「27.3 万」）、中标 4,690 MW、
  新电池 179 MW（铭牌 525 MW）。
* 法国 PL-1：``交付期收入 ≈ 认证容量(MW) × 交付期价(€/MW) × 降额系数``；
  清算 €28,182.99/MW，交付期 2026-11-01~2027-03-31 共 **151 天**，
  **不得直接年化**（€18,646.6/MW 是成本分摊商数，不是清算价）。
* PJM：``容量收入 ≈ ELCC(MW) × 出清价(美元/MW-day) × 365``；
  2028/29 BRA $325/MW-day、4 小时电池 ELCC 约 50%，
  1 MW 铭牌对应「约 6 万美元/MW-年」量级。

关于「无法纯数学复现」的说明：上述收入公式中的容量规模（40.1 GW、
4,690 MW、151 天等）与出清价均为正文给定的合成/演示口径；本模块不重算
拍卖出清，只把公式结构、单位系数（×1000、×365、降额/ELCC 线性）与正文
数字锁进可运行的函数。凡含未公开参数者（如各拍卖的 PTDF、可用率考核、
比利时电池的具体降额系数）不作硬凑，仅验证公式结构与量级——比利时
隐含降额由 179/525 推导，法国年收入仅作显式「年化等值」对比而非清算价。

所有算例均为合成/演示口径，不构成投资、法律或税务意见。
"""

from __future__ import annotations

from datetime import date

import units


# ---- 正文锁定常量（SKILL.md 数字；正文与代码漂移即自测失败）-----------------

POLAND_2030_CLEARING_PLN_PER_KW_YR = 465.02
"""波兰 2030 交付年主拍卖出清价，单位 PLN/kW·年（SKILL.md §7A.7）。"""

POLAND_DERATING_BY_SESSION = {
    "2025-12_main_2030": 0.1339,  # 13.39%，仅适用 2025-12 主拍卖 / 2030 交付年新建电池
    "2027_t1": 0.95,             # 95%，2027 T-1 沿用
    "2029_main": 0.613,          # 61.3%，2029 主拍卖
}
"""波兰电池降额系数按场次隔离，禁止跨场次混用（SKILL.md §7A.7 明确禁止）。"""

GB_T4_CLEARING_GBP_PER_KW_YR = 27.10
GB_T4_VOLUME_GW = 40.1
GB_T1_CLEARING_GBP_PER_KW_YR = 5.00
GB_T1_VOLUME_MW = 7192.0

BELGIUM_Y4_CLEARING_EUR_PER_MW_YR = 27300.0   # €27.3k/MW·年（=27,300，非「27.3 万」）
BELGIUM_Y4_VOLUME_MW = 4690.0
BELGIUM_BATTERY_DERATED_MW = 179.0
BELGIUM_BATTERY_NAMEPLATE_MW = 525.0

FRANCE_PL1_CLEARING_EUR_PER_MW = 28182.99
FRANCE_DELIVERY_START = "2026-11-01"
FRANCE_DELIVERY_END = "2027-03-31"
FRANCE_DELIVERY_DAYS = 151
FRANCE_COST_SHARE_QUOTIENT_EUR_PER_MW = 18646.6  # 成本分摊商数，不是清算价
FRANCE_BATTERY_CERTIFIED_MW = 608.0
FRANCE_BATTERY_AWARDED_MW = 577.0

PJM_2028_29_CLEARING_USD_PER_MW_DAY = 325.0
PJM_2027_28_CLEARING_USD_PER_MW_DAY = 329.17  # 纠错：不要把 329.17 标成 2028/29
PJM_BATTERY_ELCC_4H = 0.50                     # 4 小时电池 ELCC 约 50%
PJM_DAYS_PER_YEAR = 365


# ---- 容量口径换算 -----------------------------------------------------------

def derated_capacity_mw(nameplate_mw, derating_factor):
    """铭牌容量(MW) -> 降额容量(MW)：``nameplate_mw × derating_factor``。

    口径：de-rated capacity。波兰 / 英国 / 比利时容量收入都按降额容量
    付钱，**不能按铭牌容量算收入**（SKILL.md §7A.7、§7A.11 常见错误）。
    """
    return nameplate_mw * derating_factor


def elcc_capacity_mw(nameplate_mw, elcc_factor):
    """铭牌容量(MW) -> ELCC 有效容量(MW)：``nameplate_mw × elcc_factor``。

    口径：PJM 的 ELCC（Effective Load Carrying Capability），4 小时电池
    约 50%；容量收入按 ELCC 计，不按铭牌。
    """
    return nameplate_mw * elcc_factor


# ---- 波兰 -------------------------------------------------------------------

def poland_derating_for(session):
    """按拍卖场次取电池降额系数，严格隔离，未知场次抛 KeyError。

    口径：SKILL.md 明确「13.39% 仅适用 2025-12 主拍卖/2030 交付年，
    2027 T-1 用 95%、2029 主拍卖 61.3%，禁止跨场次混用」。用场次 key
    取值（而非全局常量）即是为了防止把 13.39% 套到别的交付年。
    """
    return POLAND_DERATING_BY_SESSION[session]


def poland_capacity_revenue(derated_mw, clearing_price_pln_per_kw_yr):
    """波兰容量收入(PLN/年) = 降额容量(MW) × 出清价(PLN/kW·年) × 1000。

    口径：出清价以 /kW·年 计、容量以 MW 计，故需 ×1000 把 MW 折成 kW；
    ``derated_mw`` 必须是降额容量而非铭牌容量。
    """
    return derated_mw * clearing_price_pln_per_kw_yr * 1000.0


def poland_battery_revenue(
    nameplate_mw,
    session,
    clearing_price_pln_per_kw_yr=POLAND_2030_CLEARING_PLN_PER_KW_YR,
):
    """波兰电池容量收入(PLN/年)：按场次取降额系数后套用容量收入公式。

    口径：仅用于演示「降额口径隔离」；真实收入还受可用率 / 履约考核等
    未公开参数影响，本函数不重算这些参数。
    """
    factor = poland_derating_for(session)
    derated = derated_capacity_mw(nameplate_mw, factor)
    return poland_capacity_revenue(derated, clearing_price_pln_per_kw_yr)


# ---- 英国 -------------------------------------------------------------------

def gb_capacity_revenue(derated_kw, clearing_price_gbp_per_kw_yr):
    """英国容量市场收入(£/年) = de-rated capacity(kW) × 出清价(£/kW·年)。

    口径：容量已用 kW、价格也是 /kW·年，**不需要** ×1000（与波兰公式
    因容量口径不同而异，这正是 SKILL.md 强调的单位纪律）。
    """
    return derated_kw * clearing_price_gbp_per_kw_yr


# ---- 比利时 -----------------------------------------------------------------

def belgium_crm_revenue(derated_mw, clearing_price_eur_per_mw_yr):
    """比利时 CRM 收入(€/年) = 降额容量(MW) × 中标价(€/MW·年)。

    口径：pay-as-bid、价格以 /MW·年 计、容量以 MW 计，量纲已对齐，
    无需 ×1000。中标价必须是 €27,300/MW·年（=27.3k，非「27.3 万」）。
    """
    return derated_mw * clearing_price_eur_per_mw_yr


def belgium_battery_implied_derating():
    """比利时新电池隐含降额系数 = 降额 179 MW / 铭牌 525 MW。

    口径：正文未直接给出降额系数，此为由两个公开数字推导的演示口径；
    自测只验证其落在 (0,1) 且不等于 1（即「不能用铭牌容量算 CRM」）。
    """
    return BELGIUM_BATTERY_DERATED_MW / BELGIUM_BATTERY_NAMEPLATE_MW


# ---- 法国 -------------------------------------------------------------------

def delivery_period_days(start_iso, end_iso):
    """交付期天数（含首尾），入参为 ISO 日期串 ``YYYY-MM-DD``。

    单位：返回天。口径：法国 PL-1 交付期 2026-11-01 至 2027-03-31
    （含首尾）共 151 天；用标准库 ``datetime.date`` 计算，避免手写
    天数导致与正文漂移。
    """
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    return (end - start).days + 1


def france_pl1_delivery_revenue(certified_mw, delivery_price_eur_per_mw,
                                derating_factor=1.0):
    """法国 PL-1 **交付期**收入(€/交付期) =
    认证容量(MW) × 交付期价(€/MW) × 降额系数。

    口径：这是「每交付期」的一次性收入，**不是年价**，公式中**不含**
    365 或 365/151 等年化因子。清算价 €28,182.99/MW 是交付期价；
    €18,646.6/MW 是成本分摊商数，不是清算价，不得代入本函数。
    SKILL.md 明确「不得把交付期价直接年化」。
    """
    return certified_mw * delivery_price_eur_per_mw * derating_factor


def france_pl1_annualized_equivalent(delivery_revenue_eur, delivery_days,
                                     year_days=365.0):
    """交付期收入 -> **年化等值**(€/年) = 收入 × year_days / delivery_days。

    口径：仅用于与英 / 波 / 比等「/年」口径做**横向对比**时的显式折算，
    绝非清算价口径，也不代表法国按年付款。把交付期价当年价（直接
    ×365 或按 365/151 放大）是 SKILL.md 列出的常见错误；本函数显式
    暴露该放大倍数，供自测断言「151 天交付期不得年化」。
    """
    return delivery_revenue_eur * year_days / delivery_days


# ---- PJM --------------------------------------------------------------------

def pjm_capacity_revenue(elcc_mw, clearing_price_usd_per_mw_day,
                         days=PJM_DAYS_PER_YEAR):
    """PJM 容量收入($/年) ≈ ELCC(MW) × 出清价($/MW-day) × 365。

    口径：出清价按「美元/MW-日」计，故 ×365 得到年值；``elcc_mw`` 是
    ELCC 有效容量（4 小时电池约取铭牌的 50%），不是铭牌容量。
    """
    return elcc_mw * clearing_price_usd_per_mw_day * days


def pjm_battery_revenue_per_nameplate_mw(
    elcc_factor=PJM_BATTERY_ELCC_4H,
    clearing_price_usd_per_mw_day=PJM_2028_29_CLEARING_USD_PER_MW_DAY,
    days=PJM_DAYS_PER_YEAR,
):
    """每 1 MW 铭牌的电池容量收入($/MW-年)：ELCC × 出清价 × 365。

    口径：用于复现正文「容量收入约 6 万美元/MW-年（量级口径）」；
    0.5 × 325 × 365 = 59,312.5，落在「约 6 万」量级；未公开的
    ELCC 衰减细节不硬凑，只验证量级。
    """
    elcc = elcc_capacity_mw(1.0, elcc_factor)
    return pjm_capacity_revenue(elcc, clearing_price_usd_per_mw_day, days)


# 显式再导出，便于自测用 units 做单位换算交叉验证。
__all__ = [
    "units",
    "derated_capacity_mw", "elcc_capacity_mw",
    "poland_derating_for", "poland_capacity_revenue", "poland_battery_revenue",
    "gb_capacity_revenue",
    "belgium_crm_revenue", "belgium_battery_implied_derating",
    "delivery_period_days", "france_pl1_delivery_revenue",
    "france_pl1_annualized_equivalent",
    "pjm_capacity_revenue", "pjm_battery_revenue_per_nameplate_mw",
]
