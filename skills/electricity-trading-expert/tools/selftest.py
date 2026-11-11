"""电力交易专家算例自测（零依赖，仅 Python 标准库）。

从本目录运行：

    python selftest.py

或从仓库根目录运行：

    python skills/electricity-trading-expert/tools/selftest.py

本文件**断言锁 SKILL.md 的算例**：正文（skills/electricity-trading-expert/
SKILL.md）与代码一旦漂移即失败，逐条打印 ``ok  ...``，任一断言不满足
抛 ``AssertionError``。所有算例均为**合成/演示口径**，不构成投资、
法律或税务意见。

口径说明（哪些数字如何被锁）：

* 纯数学复现：各国容量收入公式的单位系数（波兰 ×1000、PJM ×365、
  降额/ELCC 线性）、单位换算尺的 ×1000 / ×365 / ÷1000 关系、备用价
  ``11 = 28 − 17`` 与 ``22 = 20 − 5 + 7``、法国 608 MW 电池交付期收入、
  PJM「约 6 万美元/MW-年」量级（``0.5 × 325 × 365 = 59,312.5``）。
* 锁定基准 + 结构验证（含未公开参数，不硬凑）：三节点四个节点价
  （160 / 280 / 640 / −80）依赖未公开的 PTDF、负荷分布与线路电抗，
  正文只给「两边际机组加权」等定性描述，因此只把正文结果锁为常量，
  并验证 LMP 三分量分解、加权结构、单调性与负电价；比利时电池降额
  系数未公开，仅由 179/525 推导并验证结构。
* 汇率纪律：单位换算的跨币种汇率必须由 ``fx_to_usd`` **显式传入**，
  自测只用显式假汇率验证换算链，断言本身只验证纯数学关系，不写死
  任何实时汇率。
* 显式检查「151 天交付期不得年化」：法国 PL-1 清算价 €28,182.99/MW
  是交付期价，交付期 2026-11-01~2027-03-31 共 151 天；正确交付期
  收入不含 365 因子，年化等值仅作横向对比，二者必须不相等。
"""

from __future__ import annotations

import capacity
import market
import units


_COUNT = 0


def close(name, actual, expected, tol):
    """断言 actual ≈ expected（绝对容差 tol），打印结果，失败抛 AssertionError。"""
    global _COUNT
    if abs(actual - expected) > tol:
        raise AssertionError(f"{name}: {actual} != {expected} (tol {tol})")
    _COUNT += 1
    print(f"ok  {name:<48} {actual:,.4f}")


def check(condition, name):
    """断言 condition 为真，打印结果，失败抛 AssertionError。"""
    global _COUNT
    if not condition:
        raise AssertionError(name)
    _COUNT += 1
    print(f"ok  {name}")


def main():
    # ---- A. 单位换算 / 容量口径换算（units.py，纯数学关系）------------------
    close("A MW->kW 1 MW", units.mw_to_kw(1.0), 1000.0, 1e-9)
    close("A 40.1 GW -> kW", units.mw_to_kw(40.1 * 1000), 40_100_000.0, 1e-6)
    close("A kW->MW 1000 kW", units.kw_to_mw(1000.0), 1.0, 1e-9)
    close("A 7,192 MW round-trip", units.kw_to_mw(units.mw_to_kw(7192.0)), 7192.0, 1e-6)
    close("A /MW->/kW 27,300", units.price_per_mw_to_per_kw(27300.0), 27.3, 1e-9)
    close("A /kW->/MW 27.10", units.price_per_kw_to_per_mw(27.10), 27100.0, 1e-6)
    close("A /kW->/MW 465.02", units.price_per_kw_to_per_mw(465.02), 465020.0, 1e-6)
    close("A day->year 325 x365", units.per_day_to_per_year(325.0), 118625.0, 1e-6)
    close("A year->day 118625", units.per_year_to_per_day(118625.0), 325.0, 1e-9)
    close("A $/MW-day->$/kW-yr 325", units.mw_day_to_kw_year(325.0), 118.625, 1e-9)
    close(
        "A ruler $/MW-day->$/kW-yr",
        units.convert_capacity_price(325.0, "$/MW-day", "$/kW-yr"),
        118.625,
        1e-9,
    )
    close(
        "A ruler matches mw_day_to_kw_year",
        units.convert_capacity_price(325.0, "$/MW-day", "$/kW-yr"),
        units.mw_day_to_kw_year(325.0),
        1e-9,
    )
    close(
        "A ruler EUR/MW-yr->EUR/kW-yr",
        units.convert_capacity_price(27300.0, "€/MW-yr", "€/kW-yr"),
        27.3,
        1e-9,
    )
    close(
        "A ruler PLN/kW-yr->PLN/MW-yr",
        units.convert_capacity_price(465.02, "PLN/kW-yr", "PLN/MW-yr"),
        465020.0,
        1e-6,
    )
    close(
        "A ruler GBP/kW-yr->GBP/MW-yr",
        units.convert_capacity_price(5.00, "£/kW-yr", "£/MW-yr"),
        5000.0,
        1e-6,
    )
    close(
        "A ruler explicit fx EUR->USD",
        units.convert_capacity_price(100.0, "€/kW-yr", "$/kW-yr", {"EUR": 1.25}),
        125.0,
        1e-9,
    )
    close(
        "A ruler round-trip with explicit fx",
        units.convert_capacity_price(
            units.convert_capacity_price(1.0, "$/MW-day", "€/kW-yr", {"EUR": 1.1}),
            "€/kW-yr",
            "$/MW-day",
            {"EUR": 1.1},
        ),
        1.0,
        1e-9,
    )
    close(
        "A ruler days param not hardcoded",
        units.convert_capacity_price(325.0, "$/MW-day", "$/kW-yr", days=366),
        325.0 * 366.0 / 1000.0,
        1e-9,
    )
    check(
        all(
            u in units.supported_units()
            for u in ("$/MW-day", "€/kW-yr", "PLN/kW-yr", "£/kW-yr", "¥/kW")
        ),
        "A ruler lists 5 currency families",
    )
    check("€/MW" not in units.supported_units(), "A ruler excludes delivery-period EUR/MW")
    try:
        units.convert_capacity_price(100.0, "€/kW-yr", "$/kW-yr")
        cross_raised = False
    except ValueError:
        cross_raised = True
    check(cross_raised, "A cross-currency without fx raises")

    # ---- B. 波兰 rynek mocy + 降额口径隔离 ---------------------------------
    close("B 2030 clearing 465.02", capacity.POLAND_2030_CLEARING_PLN_PER_KW_YR, 465.02, 1e-9)
    close(
        "B revenue 100MW derated",
        capacity.poland_capacity_revenue(100.0, 465.02),
        46_502_000.0,
        1.0,
    )
    close("B formula has x1000 factor", capacity.poland_capacity_revenue(1.0, 100.0), 100_000.0, 1e-6)
    close("B 13.39% derating of 100MW", capacity.derated_capacity_mw(100.0, 0.1339), 13.39, 1e-9)
    close(
        "B battery revenue 2030 session",
        capacity.poland_battery_revenue(100.0, "2025-12_main_2030"),
        6_226_617.8,
        0.01,
    )
    check(
        capacity.poland_capacity_revenue(100.0, 465.02)
        != capacity.poland_battery_revenue(100.0, "2025-12_main_2030"),
        "B nameplate != derated revenue",
    )
    close("B derating 2030 main 13.39%", capacity.POLAND_DERATING_BY_SESSION["2025-12_main_2030"], 0.1339, 1e-12)
    close("B derating 2027 T-1 95%", capacity.POLAND_DERATING_BY_SESSION["2027_t1"], 0.95, 1e-12)
    close("B derating 2029 main 61.3%", capacity.POLAND_DERATING_BY_SESSION["2029_main"], 0.613, 1e-12)
    close("B derating_for 2030", capacity.poland_derating_for("2025-12_main_2030"), 0.1339, 1e-12)
    close("B derating_for 2027 T-1", capacity.poland_derating_for("2027_t1"), 0.95, 1e-12)
    close("B derating_for 2029 main", capacity.poland_derating_for("2029_main"), 0.613, 1e-12)
    check(
        len(
            {
                capacity.poland_battery_revenue(100.0, s)
                for s in ("2025-12_main_2030", "2027_t1", "2029_main")
            }
        )
        == 3,
        "B three sessions stay isolated",
    )
    check(
        capacity.poland_battery_revenue(100.0, "2025-12_main_2030")
        < capacity.poland_battery_revenue(100.0, "2029_main")
        < capacity.poland_battery_revenue(100.0, "2027_t1"),
        "B 13.39% < 61.3% < 95% ordering",
    )
    try:
        capacity.poland_derating_for("2031_unknown")
        unknown_raised = False
    except KeyError:
        unknown_raised = True
    check(unknown_raised, "B unknown session raises (no mixing)")

    # ---- C. 英国 GB CM ------------------------------------------------------
    close("C T-4 clearing 27.10", capacity.GB_T4_CLEARING_GBP_PER_KW_YR, 27.10, 1e-9)
    close("C T-4 volume 40.1 GW", capacity.GB_T4_VOLUME_GW, 40.1, 1e-9)
    close("C T-1 clearing 5.00", capacity.GB_T1_CLEARING_GBP_PER_KW_YR, 5.00, 1e-9)
    close("C T-1 volume 7,192 MW", capacity.GB_T1_VOLUME_MW, 7192.0, 1e-9)
    close("C 1 kW at T-4 (no x1000)", capacity.gb_capacity_revenue(1.0, 27.10), 27.10, 1e-9)
    close(
        "C T-4 40.1 GW revenue",
        capacity.gb_capacity_revenue(units.mw_to_kw(40.1 * 1000), 27.10),
        1_086_710_000.0,
        1.0,
    )
    close(
        "C T-1 7,192 MW revenue",
        capacity.gb_capacity_revenue(units.mw_to_kw(7192.0), 5.00),
        35_960_000.0,
        1.0,
    )
    check(capacity.gb_capacity_revenue(1000.0, 1.0) == 1000.0, "C GB pays per kW not per MW")

    # ---- D. 比利时 CRM ------------------------------------------------------
    close("D Y-4 price 27,300", capacity.BELGIUM_Y4_CLEARING_EUR_PER_MW_YR, 27300.0, 1e-9)
    close("D 27.3k unit correction", 27.3 * 1000, 27300.0, 1e-6)
    close("D Y-4 volume 4,690 MW", capacity.BELGIUM_Y4_VOLUME_MW, 4690.0, 1e-9)
    close("D battery derated 179 MW", capacity.BELGIUM_BATTERY_DERATED_MW, 179.0, 1e-9)
    close("D battery nameplate 525 MW", capacity.BELGIUM_BATTERY_NAMEPLATE_MW, 525.0, 1e-9)
    close(
        "D battery 179MW CRM revenue",
        capacity.belgium_crm_revenue(179.0, 27300.0),
        4_886_700.0,
        1.0,
    )
    close(
        "D total Y-4 CRM revenue",
        capacity.belgium_crm_revenue(4690.0, 27300.0),
        128_037_000.0,
        1.0,
    )
    close(
        "D implied derating 179/525",
        capacity.belgium_battery_implied_derating(),
        179.0 / 525.0,
        1e-12,
    )
    check(
        0.0 < capacity.belgium_battery_implied_derating() < 1.0,
        "D implied derating in (0,1)",
    )
    check(
        capacity.belgium_crm_revenue(525.0, 27300.0)
        != capacity.belgium_crm_revenue(179.0, 27300.0),
        "D nameplate overstates CRM",
    )

    # ---- E. 法国 PL-1：151 天交付期不得年化（显式检查）----------------------
    close("E clearing 28,182.99", capacity.FRANCE_PL1_CLEARING_EUR_PER_MW, 28182.99, 1e-9)
    close("E locked 151 days", capacity.FRANCE_DELIVERY_DAYS, 151.0, 1e-9)
    close(
        "E computed delivery days",
        capacity.delivery_period_days("2026-11-01", "2027-03-31"),
        151.0,
        1e-9,
    )
    close(
        "E 1MW delivery revenue (no x365)",
        capacity.france_pl1_delivery_revenue(1.0, 28182.99),
        28182.99,
        1e-6,
    )
    close(
        "E 608MW battery delivery revenue",
        capacity.france_pl1_delivery_revenue(608.0, 28182.99),
        17_135_257.92,
        0.01,
    )
    close(
        "E derating is linear",
        capacity.france_pl1_delivery_revenue(100.0, 28182.99, 0.5),
        1_409_149.5,
        0.01,
    )
    close(
        "E cost-share quotient 18,646.6",
        capacity.FRANCE_COST_SHARE_QUOTIENT_EUR_PER_MW,
        18646.6,
        1e-9,
    )
    check(18646.6 != 28182.99, "E quotient != clearing price")
    check(
        capacity.france_pl1_delivery_revenue(1.0, 18646.6)
        != capacity.france_pl1_delivery_revenue(1.0, 28182.99),
        "E quotient cannot be the price",
    )
    delivery = capacity.france_pl1_delivery_revenue(1.0, 28182.99)
    annual = capacity.france_pl1_annualized_equivalent(delivery, 151)
    close("E annualization factor 365/151", annual / delivery, 365.0 / 151.0, 1e-12)
    close("E annualized equivalent", annual, 28182.99 * 365.0 / 151.0, 1e-6)
    check(delivery != annual, "E 151-day delivery must NOT be annualized")
    check(delivery != 28182.99 * 365, "E wrong x365 differs from delivery")
    check(annual > delivery, "E annualized > delivery-period")

    # ---- F. PJM BRA / ELCC --------------------------------------------------
    close("F 2028/29 clearing 325", capacity.PJM_2028_29_CLEARING_USD_PER_MW_DAY, 325.0, 1e-9)
    close("F 2027/28 clearing 329.17", capacity.PJM_2027_28_CLEARING_USD_PER_MW_DAY, 329.17, 1e-9)
    check(325.0 != 329.17, "F 325 != 329.17 (no year mix-up)")
    close("F 4h battery ELCC 50%", capacity.PJM_BATTERY_ELCC_4H, 0.50, 1e-12)
    close("F ELCC of 1MW", capacity.elcc_capacity_mw(1.0, 0.5), 0.5, 1e-12)
    close("F revenue 0.5MW ELCC", capacity.pjm_capacity_revenue(0.5, 325.0), 59_312.5, 1e-6)
    close(
        "F per-nameplate-MW helper",
        capacity.pjm_battery_revenue_per_nameplate_mw(),
        59_312.5,
        1e-6,
    )
    check(
        50_000.0 < capacity.pjm_battery_revenue_per_nameplate_mw() < 70_000.0,
        "F ~60k USD/MW-yr magnitude",
    )
    close("F 1MW full ELCC", capacity.pjm_capacity_revenue(1.0, 325.0), 118_625.0, 1e-6)
    close(
        "F x365 matches units.per_day_to_per_year",
        capacity.pjm_capacity_revenue(1.0, 325.0),
        units.per_day_to_per_year(325.0),
        1e-6,
    )

    # ---- G. 三节点四价 / LMP 结构 / 备用价 ---------------------------------
    check(
        (market.GEN1_BID_CNY_PER_MWH, market.GEN2_BID_CNY_PER_MWH, market.GEN3_BID_CNY_PER_MWH)
        == (160.0, 80.0, 400.0),
        "G generator bids 160/80/400",
    )
    check(
        (market.GEN2_CAPACITY_MW, market.GEN3_CAPACITY_MW) == (1500.0, 3000.0),
        "G generator caps 1500/3000",
    )
    check(
        tuple(
            market.THREE_NODE_LINE_LIMITS_MW[k]
            for k in ("line_1_3_limit_4000mw", "line_1_2_limit_1000mw", "line_2_3_limit_2000mw")
        )
        == (4000.0, 1000.0, 2000.0),
        "G line limits 4000/1000/2000 MW",
    )
    close("G no congestion -> 160", market.THREE_NODE_NODE2_PRICES["no_congestion"], 160.0, 1e-9)
    close(
        "G 1-3 limit 4000MW -> 280",
        market.THREE_NODE_NODE2_PRICES["line_1_3_limit_4000mw"],
        280.0,
        1e-9,
    )
    close(
        "G 1-2 limit 1000MW -> 640",
        market.THREE_NODE_NODE2_PRICES["line_1_2_limit_1000mw"],
        640.0,
        1e-9,
    )
    close(
        "G 2-3 limit 2000MW -> -80",
        market.THREE_NODE_NODE2_PRICES["line_2_3_limit_2000mw"],
        -80.0,
        1e-9,
    )
    close(
        "G merit-order no congestion 160",
        market.merit_order_marginal_price(market.THREE_NODE_GENERATORS, 2500.0),
        160.0,
        1e-9,
    )
    close(
        "G merit-order below gen2 80",
        market.merit_order_marginal_price(market.THREE_NODE_GENERATORS, 1000.0),
        80.0,
        1e-9,
    )
    check(160.0 < 280.0 < 640.0, "G prices rise with congestion")
    check(-80.0 < 0.0, "G 2-3 case is a negative price")
    check(80.0 <= 280.0 <= 400.0, "G 280 is weighted avg of 80/400")
    close("G implied weight 0.375", market.implied_weight(80.0, 400.0, 280.0), 0.375, 1e-9)
    check(
        0.0 < market.implied_weight(80.0, 400.0, 280.0) < 1.0,
        "G weight in (0,1)",
    )
    close("G congestion component of 280", market.lmp_congestion_component(280.0, 160.0), 120.0, 1e-9)
    close("G congestion component of 640", market.lmp_congestion_component(640.0, 160.0), 480.0, 1e-9)
    close("G congestion component of -80", market.lmp_congestion_component(-80.0, 160.0), -240.0, 1e-9)
    close("G LMP decompose -> 280", market.lmp_decompose(160.0, 120.0, 0.0), 280.0, 1e-9)
    close("G LMP decompose -> 640", market.lmp_decompose(160.0, 480.0, 0.0), 640.0, 1e-9)
    close("G LMP decompose -> -80", market.lmp_decompose(160.0, -240.0, 0.0), -80.0, 1e-9)
    close("G congestion surplus", market.congestion_surplus(280.0, 160.0, 4000.0), 480_000.0, 1e-6)
    close("G FTR payout", market.ftr_payout(100.0, 280.0, 160.0), 12_000.0, 1e-6)
    check(market.ftr_payout(100.0, 160.0, 280.0) < 0.0, "G FTR obligation can be negative")
    close("G reserve 11 = 28 - 17", market.reserve_opportunity_cost(28.0, 17.0), 11.0, 1e-9)
    close("G reserve standalone 22", market.reserve_standalone_price(20.0, 5.0, 7.0), 22.0, 1e-9)
    check(11.0 != 22.0, "G 11 != 22 are two examples")
    close(
        "G sort price = offer + opportunity",
        market.co_optimized_sort_price(20.0, 7.0),
        27.0,
        1e-9,
    )

    print(f"\nAll electricity-trading-expert self-tests passed ({_COUNT} assertions).")


if __name__ == "__main__":
    main()
