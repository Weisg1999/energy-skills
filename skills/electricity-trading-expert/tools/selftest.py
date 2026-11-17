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
* 中长期对冲：期间电量→日电量→96 点曲线、差价合约结算、carry/curve
  分解与六桶差异桥均为纯数学关系；山东煤电实例的日电量、对冲比例、
  情景收入、滚动调仓与差异桥数字全部锁定。
"""

from __future__ import annotations

import importlib.util
import csv
import json
import os
import tempfile
from datetime import date
from pathlib import Path

import capacity
import contracts
import fuel
import hedge
import market
import portfolio
import review
import rulecheck
import units


_COUNT = 0
REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_DIR = REPO_ROOT / "skills" / "electricity-trading-expert" / "rules"


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

    print("\n== fuel cost to bid (synthetic, grade D)")
    close("fuel long-term price 800 -> 737.5", fuel.long_term_coal_price(800.0), 737.5, 1e-9)
    close("fuel long-term cap 770", fuel.long_term_coal_price(900.0), 770.0, 1e-9)
    close("fuel blended price", fuel.blended_coal_price(737.5, 989.0, 0.8), 787.8, 1e-9)
    close("fuel cost per MWh", fuel.coal_cost_per_mwh(787.8), 236.34, 1e-6)
    close("fuel dark spread", fuel.dark_spread(400.0, 236.34, 20.0), 143.66, 1e-9)
    close("fuel clean dark", fuel.clean_spread(143.66, 80.0, 0.95), 67.66, 1e-9)
    close("fuel spark spread", fuel.spark_spread(400.0, 320.0, 15.0), 65.0, 1e-9)
    close("fuel clean spark", fuel.clean_spread(65.0, 80.0, 0.40), 33.0, 1e-9)
    close("fuel switch carbon price", fuel.switch_carbon_price(236.34, 320.0), 152.10909090909092, 1e-6)
    close("fuel dual-track gap", fuel.dual_track_gap(989.0, 800.0), 251.5, 1e-9)
    close("fuel inventory days", fuel.inventory_days(1500000.0, 100000.0), 15.0, 1e-9)

    print("\n== gas and LNG conversion (synthetic, grade D)")
    close("gas MMBtu->MWh factor", fuel.MMBTU_TO_MWH, 0.293071, 1e-12)
    close("gas HH $3.37/MMBtu -> $/MWh", fuel.price_mmbtu_to_mwh(3.37), 11.4989, 1e-3)
    close("gas TTF EUR85.83/MWh -> EUR/MMBtu", fuel.price_mwh_to_mmbtu(85.83), 25.1543, 1e-3)
    close("gas MMBtu round-trip", fuel.mwh_to_mmbtu(fuel.mmbtu_to_mwh(3.37)), 3.37, 1e-9)
    close("gas 1 t LNG -> MMBtu", fuel.lng_tonnes_to_mmbtu(1.0), 48.7, 1e-9)
    close("gas 1 t LNG -> MWh", fuel.lng_tonnes_to_mwh(1.0), 14.2726, 1e-3)
    close("gas 2.6 CNY/m3 -> CNY/GJ", fuel.gas_price_from_m3(2.6), 72.222222, 1e-6)
    close("gas fuel 6.3 GJ/MWh", fuel.gas_fuel_cost(fuel.gas_price_from_m3(2.6), 6.3), 455.0, 1e-6)
    close("gas CCGT 58% fuel", fuel.ccgt_fuel_cost(85.83, 0.58), 147.9828, 1e-3)
    close("gas CCGT 60% fuel", fuel.ccgt_fuel_cost(85.83, 0.60), 143.05, 1e-3)
    close("gas carbon 85 x 0.36", fuel.gas_carbon_cost(85.0, 0.36), 30.6, 1e-9)
    close(
        "gas clean spark 58%",
        120.0 - fuel.ccgt_fuel_cost(85.83, 0.58) - fuel.gas_carbon_cost(85.0, 0.36) - 5.0,
        -63.5828,
        1e-3,
    )
    close(
        "gas clean spark 60%",
        120.0 - fuel.ccgt_fuel_cost(85.83, 0.60) - fuel.gas_carbon_cost(85.0, 0.36) - 5.0,
        -58.65,
        1e-3,
    )
    close("gas oil-indexed 80 x 11.5%", fuel.oil_indexed_lng_price(80.0, 0.115), 9.2, 1e-9)
    close(
        "gas oil-indexed in $/MWh",
        fuel.price_mmbtu_to_mwh(fuel.oil_indexed_lng_price(80.0, 0.115)),
        31.3917,
        1e-3,
    )
    close("gas DES cost", fuel.lng_des_cost_usd_per_mmbtu(3.37), 7.37, 1e-9)
    close(
        "gas DES in $/MWh",
        fuel.price_mmbtu_to_mwh(fuel.lng_des_cost_usd_per_mmbtu(3.37)),
        25.1475,
        1e-3,
    )
    close("gas JKM netback $/MMBtu", fuel.lng_netback(31.70, 7.37), 24.33, 1e-6)
    close(
        "gas JKM netback $/MWh",
        fuel.price_mmbtu_to_mwh(fuel.lng_netback(31.70, 7.37)),
        83.0174,
        1e-3,
    )
    close(
        "gas capacity 264 CNY/kW-yr -> CNY/MWh",
        fuel.capacity_price_per_mwh(264.0, 2000.0),
        132.0,
        1e-9,
    )
    close(
        "gas China total cost",
        fuel.gas_fuel_cost(fuel.gas_price_from_m3(2.6), 6.3)
        + fuel.capacity_price_per_mwh(264.0, 2000.0),
        587.0,
        1e-6,
    )
    check(
        0.0 < fuel.capacity_price_per_mwh(264.0, 2000.0) / 587.0 < 0.25,
        "gas capacity share below 25%",
    )
    close("G congestion surplus cross-check", market.congestion_surplus(500.0, 200.0, 200.0), 60000.0, 1e-6)

    print("\n== contract and asset valuation (synthetic, grade D)")
    close("H annuity factor 10y 7%", contracts.annuity_factor(10, 0.07), 7.02358154, 1e-8)
    close("H PV of 10 x 1 at 7%", contracts.pv([1.0] * 10, 0.07), 7.02358154, 1e-8)
    close(
        "H forward strip PV",
        contracts.forward_strip_pv([100.0, 100.0], [1000.0, 1000.0], 0.10),
        173553.719008,
        1e-6,
    )
    project = [-100.0, 30.0, 30.0, 30.0, 30.0]
    check(abs(contracts.npv(project, contracts.irr(project))) < 1e-6, "H IRR zeroes NPV")
    close("H capture price", contracts.capture_price([20.0, 80.0], [100.0, 50.0]), 40.0, 1e-9)
    close("H capture rate", contracts.capture_rate(40.0, 60.0), 0.6666666667, 1e-9)
    close("H floor pays at 30", contracts.floor_payoff(30.0, 45.0, 40_000.0), 600_000.0, 1e-6)
    close("H floor pays zero at 60", contracts.floor_payoff(60.0, 45.0, 40_000.0), 0.0, 1e-9)
    close("H cap gives up at 100", contracts.cap_payoff(100.0, 90.0, 40_000.0), 400_000.0, 1e-6)
    close("H cap gives up zero at 75", contracts.cap_payoff(75.0, 90.0, 40_000.0), 0.0, 1e-9)
    close("H collar floor leg", contracts.collar_payoff(30.0, 45.0, 90.0, 40_000.0), 600_000.0, 1e-6)
    close("H collar cap leg", contracts.collar_payoff(100.0, 45.0, 90.0, 40_000.0), -400_000.0, 1e-6)
    close("H collar inside band", contracts.collar_payoff(60.0, 45.0, 90.0, 40_000.0), 0.0, 1e-9)
    close("H CfD top-up", contracts.cfd_settlement(80.0, 60.0, 150_000.0), 3_000_000.0, 1e-6)
    close("H CfD clawback", contracts.cfd_settlement(80.0, 90.0, 150_000.0), -1_500_000.0, 1e-6)
    close("H proxy revenue swap", contracts.proxy_revenue_swap(5_000_000.0, 4_200_000.0), 800_000.0, 1e-6)
    close("H tolling gross", contracts.tolling_gross_revenue(100.0, 60_000.0, 0.97), 5_820_000.0, 1e-6)
    close(
        "H tolling net",
        contracts.tolling_net_revenue(100.0, 60_000.0, 0.97, 1_000_000.0, 500_000.0, 200_000.0),
        4_120_000.0,
        1e-6,
    )
    close(
        "H tolling breakeven fee",
        contracts.tolling_breakeven_fee(4_000_000.0, 1_000_000.0, 500_000.0, 200_000.0, 100.0, 0.97),
        58_762.886598,
        1e-6,
    )
    close(
        "H merchant tail PV",
        contracts.merchant_tail_pv(50.0, 70_000.0, 10, 0.07),
        24_582_535.39,
        0.01,
    )
    net_scenarios = [5.492, 5.492, 6.092, 6.692, 7.292]
    stats = contracts.scenario_stats(net_scenarios)
    close("H scenario mean", stats["mean"], 6.212, 1e-12)
    close("H scenario P10", stats["p10"], 5.492, 1e-12)
    close("H scenario P50", stats["p50"], 6.092, 1e-12)
    close("H scenario P90", stats["p90"], 7.052, 1e-12)
    close(
        "H 10y PV of scenario mean",
        stats["mean"] * contracts.annuity_factor(10, 0.07),
        43.6305,
        1e-4,
    )
    close("H DSCR at P10", contracts.dscr(5_492_000.0, 4_393_600.0), 1.25, 1e-9)
    close(
        "H max debt at P10",
        contracts.max_debt_by_dscr(5_492_000.0, 1.25, 0.05, 10),
        33_926_214.58,
        0.1,
    )
    close(
        "H max debt at P50",
        contracts.max_debt_by_dscr(6_092_000.0, 1.25, 0.05, 10),
        37_632_647.35,
        0.1,
    )
    neg = contracts.scenario_stats(
        contracts.simulate_correlated_revenue(
            60.0, 15.0, 1.0, 0.1, 40_000.0, rho=-0.8, draws=20_000, seed=7
        )
    )
    ind = contracts.scenario_stats(
        contracts.simulate_correlated_revenue(
            60.0, 15.0, 1.0, 0.1, 40_000.0, rho=0.0, draws=20_000, seed=7
        )
    )
    pos = contracts.scenario_stats(
        contracts.simulate_correlated_revenue(
            60.0, 15.0, 1.0, 0.1, 40_000.0, rho=0.8, draws=20_000, seed=7
        )
    )
    check(
        neg["mean"] < ind["mean"] < pos["mean"],
        "H negative price-capture correlation lowers mean revenue",
    )
    check(ind["p10"] < ind["p50"] < ind["p90"], "H revenue quantiles are ordered")

    # ---- I. 中长期合约曲线与差价合约（hedge.py，纯数学关系） ---------------
    check(hedge.flat_shape(4) == [0.25, 0.25, 0.25, 0.25], "I flat shape is uniform")
    check(abs(sum(hedge.flat_shape(96)) - 1.0) < 1e-12, "I flat 96 sums to 1")
    peak_shape = hedge.window_shape(96, 15, [[8, 22]])
    off_shape = hedge.window_shape(96, 15, [[8, 22]], complement=True)
    close("I peak shape slot 32", peak_shape[32], 1.0 / 56.0, 1e-12)
    close("I off-peak shape slot 0", off_shape[0], 1.0 / 40.0, 1e-12)
    check(peak_shape[31] == 0.0 and peak_shape[88] == 0.0, "I peak window is 08:00-22:00")
    check(off_shape[32] == 0.0 and off_shape[87] == 0.0, "I off-peak excludes the window")
    check(abs(sum(peak_shape) - 1.0) < 1e-12, "I peak shape sums to 1")
    check(abs(sum(off_shape) - 1.0) < 1e-12, "I off-peak shape sums to 1")

    anchor = hedge.anchor_shape(96, 15, [[0, 1], [12, 2], [24, 1]])
    close("I anchor symmetric left", anchor[0], anchor[95], 1e-15)
    close("I anchor symmetric peak", anchor[47], anchor[48], 1e-15)
    check(anchor[47] > anchor[0], "I anchor rises to midday")
    check(abs(sum(anchor) - 1.0) < 1e-12, "I anchor shape sums to 1")

    close(
        "I annual 1,752,000 MWh / 365",
        hedge.contract_daily_energy({"id": "a", "energy_mwh": 1_752_000.0, "daily_weight": 1.0 / 365.0}),
        4800.0,
        1e-9,
    )
    close(
        "I monthly 54,000 MWh / 30",
        hedge.contract_daily_energy({"id": "m", "energy_mwh": 54_000.0, "period_days": 30}),
        1800.0,
        1e-9,
    )
    close(
        "I explicit daily energy wins",
        hedge.contract_daily_energy(
            {"id": "d", "energy_mwh": 54_000.0, "period_days": 30, "daily_energy_mwh": 123.0}
        ),
        123.0,
        1e-12,
    )
    try:
        hedge.contract_daily_energy({"id": "x", "energy_mwh": 100.0})
        daily_raised = False
    except ValueError:
        daily_raised = True
    check(daily_raised, "I period energy without days raises")
    try:
        hedge.shape_from_spec({"type": "curve", "weights": [1.0, 2.0]}, 96, 15)
        curve_raised = False
    except ValueError:
        curve_raised = True
    check(curve_raised, "I wrong-length curve raises")
    try:
        hedge.normalize_shape([0.0, 0.0])
        zero_raised = False
    except ValueError:
        zero_raised = True
    check(zero_raised, "I all-zero shape raises")

    toy = [
        {
            "id": "toy",
            "type": "cfd",
            "daily_energy_mwh": 100.0,
            "price_cny_per_mwh": 300.0,
            "shape": {"type": "curve", "weights": [0.2, 0.8]},
        }
    ]
    toy_book = hedge.book_position(toy, 2, 30)
    close("I toy position slot 0", toy_book["position"][0], 20.0, 1e-12)
    close("I toy position slot 1", toy_book["position"][1], 80.0, 1e-12)
    close("I toy book energy", toy_book["energy_mwh"], 100.0, 1e-12)
    check(hedge.price_curve(toy_book, 2) == [300.0, 300.0], "I toy price curve is flat")
    toy_settle = hedge.settle_book(toy, [120.0, 80.0], [200.0, 500.0], 2, 30)
    close("I toy contract revenue", toy_settle["contract_revenue_cny"], 30_000.0, 1e-9)
    close("I toy spot revenue", toy_settle["spot_revenue_cny"], -12_000.0, 1e-9)
    close("I toy total revenue", toy_settle["total_revenue_cny"], 18_000.0, 1e-9)
    close("I toy hedge ratio", toy_settle["hedge_ratio"], 1.0, 1e-12)
    close("I toy absolute exposure", toy_settle["absolute_exposure_mwh"], 80.0, 1e-9)
    toy_value = hedge.hedge_value(toy, [120.0, 80.0], [200.0, 500.0], 2, 30)
    close("I toy hedge value", toy_value["hedge_value_cny"], -14_000.0, 1e-9)
    close("I toy carry", toy_value["carry_cny"], -5_000.0, 1e-9)
    close("I toy curve shape", toy_value["shape_cny"], -9_000.0, 1e-9)
    close("I toy carry + shape identity", toy_value["identity_gap"], 0.0, 1e-9)
    toy_stats = hedge.curve_stats(toy_book["position"], [120.0, 80.0], [200.0, 500.0], 2, 30)
    close("I toy buy back", toy_stats["buy_back_mwh"], 40.0, 1e-9)
    close("I toy sell surplus", toy_stats["sell_surplus_mwh"], 40.0, 1e-9)
    close("I toy mismatch", toy_stats["mismatch_mwh"], 80.0, 1e-9)
    close("I toy peak/average", toy_stats["spot_peak_to_average"], 500.0 / 350.0, 1e-12)
    toy_plan = {
        "output_mw": [120.0, 80.0],
        "position_curve": [20.0, 80.0],
        "contract_price_curve": [300.0, 300.0],
        "spot_prices": [200.0, 500.0],
    }
    toy_actual = {
        "output_mw": [110.0, 85.0],
        "position_curve": [22.0, 76.0],
        "contract_price_curve": [300.0, 300.0],
        "spot_prices": [220.0, 480.0],
    }
    toy_bridge = hedge.pnl_bridge(toy_plan, toy_actual, 2, 30)
    close("I toy bridge plan", toy_bridge["plan_revenue_cny"], 18_000.0, 1e-9)
    close("I toy bridge actual", toy_bridge["actual_revenue_cny"], 20_580.0, 1e-9)
    close("I toy bridge delta", toy_bridge["delta_cny"], 2_580.0, 1e-9)
    check(len(toy_bridge["buckets"]) == 6, "I toy bridge has six buckets")
    check(abs(toy_bridge["identity_gap"]) < 1e-9, "I toy bridge identity holds")
    toy_amounts = {item["category"]: item["amount"] for item in toy_bridge["buckets"]}
    close("I toy contract volume", toy_amounts["contract_volume"], 280.0, 1e-9)
    close("I toy contract shape", toy_amounts["contract_shape"], 720.0, 1e-9)
    close("I toy output volume", toy_amounts["output_volume"], -800.0, 1e-9)
    close("I toy output shape", toy_amounts["output_shape"], 1050.0, 1e-9)
    close("I toy spot price", toy_amounts["spot_price"], 1600.0, 1e-9)
    close("I toy interaction", toy_amounts["interaction"], -270.0, 1e-9)
    close(
        "I toy buckets sum to delta",
        sum(toy_amounts.values()),
        toy_bridge["delta_cny"],
        1e-9,
    )

    trade = hedge.required_trade(10_000.0, 7_500.0, 0.85)
    close("I required trade target", trade["target_position_mwh"], 8_500.0, 1e-9)
    close("I required trade size", trade["required_trade_mwh"], 1_000.0, 1e-9)
    check(trade["action"] == "加仓", "I required trade is a buy")
    close("I current hedge ratio", trade["current_hedge_ratio"], 0.75, 1e-12)
    rolling = hedge.rolling_plan([8000.0, 8500.0, 9000.0], 6000.0, 0.85)
    close("I rolling day1 trade", rolling[0]["required_trade_mwh"], 800.0, 1e-9)
    close("I rolling day2 trade", rolling[1]["required_trade_mwh"], 425.0, 1e-9)
    close("I rolling day3 trade", rolling[2]["required_trade_mwh"], 425.0, 1e-9)
    close("I rolling day2 ratio", rolling[1]["current_hedge_ratio"], 0.8, 1e-12)
    close("I rolling ends at target", rolling[2]["position_after_mwh"], 7650.0, 1e-9)

    # ---- J. 山东煤电中长期实例包（配置 + 演示数字全部锁定） ----------------
    print("\n== shandong thermal hedge instance")
    instance_dir = (
        Path(__file__).resolve().parents[1]
        / "instances"
        / "shandong-thermal-hedge-2026-11"
    )
    spec = importlib.util.spec_from_file_location(
        "shandong_thermal_hedge_instance", instance_dir / "run.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    instance_path = instance_dir / "instance.json"
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    report = runner.validate_instance(config)
    print(
        f"hedge config ok={report['ok']} points={report['points_per_day']} "
        f"book={report['book_daily_energy_mwh']:.1f} MWh price={report['book_weighted_price']:.2f}"
    )
    check(report["ok"] and report["points_per_day"] == 96, "J hedge config validates at 96 points")
    close("J book daily energy", report["book_daily_energy_mwh"], 7500.0, 1e-9)
    close("J book weighted price", report["book_weighted_price"], 375.34666666666664, 1e-9)
    check(report["target_hedge_ratio"] == 0.85, "J target hedge ratio is 0.85")
    check(report["mtu_min"] == 15, "J hedge pack uses 15-minute MTU")

    def bad_config(mutate):
        broken = json.loads(json.dumps(config))
        mutate(broken)
        try:
            runner.validate_instance(broken)
        except runner.ConfigError:
            return True
        return False

    check(
        bad_config(lambda c: c["book"][0].__setitem__("daily_energy_mwh", 1_752_000.0)),
        "J annual energy used as daily is rejected",
    )
    check(
        bad_config(lambda c: c["book"][0].__setitem__("type", "physical")),
        "J physical contract is rejected in v1",
    )
    check(
        bad_config(lambda c: c["book"][0]["shape"].__setitem__("type", "linear")),
        "J unknown shape type is rejected",
    )
    check(
        bad_config(lambda c: c["policy"].__setitem__("target_hedge_ratio", 1.5)),
        "J target above max hedge ratio is rejected",
    )
    check(
        bad_config(lambda c: c["book"][0].__setitem__("price_cny_per_mwh", 2000.0)),
        "J contract price above spot cap is rejected",
    )

    position = runner.build_position(config, report)
    bad_rolling = [
        {"day_offset": -1, "forecast_output_mwh": 8000.0, "position_before_mwh": 7000.0},
        {"day_offset": 0, "forecast_output_mwh": 9000.0, "position_before_mwh": 6000.0},
    ]
    try:
        runner.build_rolling(config, report, bad_rolling, position)
        chain_raised = False
    except runner.ConfigError:
        chain_raised = True
    check(chain_raised, "J broken rolling position chain is rejected")

    late_period = json.loads(json.dumps(config))
    late_period["book"][0]["period_start"] = "2026-12-01"
    late_period["book"][0]["period_end"] = "2026-12-31"
    late_report = runner.validate_instance(late_period)
    try:
        runner.read_d1(instance_dir / "data" / "d1_demo.csv", late_period, late_report)
        coverage_raised = False
    except runner.ConfigError:
        coverage_raised = True
    check(coverage_raised, "J contract period must cover the trading day")

    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_instance(
            instance_path,
            instance_dir / "data" / "d1_demo.csv",
            instance_dir / "data" / "t1_demo.csv",
            instance_dir / "data" / "rolling_demo.csv",
            Path(tmp),
        )
        plan = result["summary"]["plan"]
        rolling_out = result["rolling"]
        bridge = result["bridge"]
        print(
            f"hedge demo ratio={plan['hedge_ratio']:.4f} E={plan['expected_revenue_cny']:.0f} "
            f"CVaR10={plan['cvar_10_cny']:.0f} delta={bridge['delta_cny']:.0f} "
            f"gap={bridge['identity_gap']:.2e}"
        )
        check(result["report"]["ok"], "J hedge demo report is ok")
        close("J forecast energy", plan["forecast_energy_mwh"], 8800.0, 1e-6)
        close("J position energy", plan["position_energy_mwh"], 7500.0, 1e-6)
        close("J hedge ratio", plan["hedge_ratio"], 0.8522727272727273, 1e-12)
        close("J net exposure", plan["net_exposure_mwh"], 1300.0, 1e-6)
        close("J sell surplus", plan["sell_surplus_mwh"], 1300.0, 1e-6)
        close("J buy back is zero", plan["buy_back_mwh"], 0.0, 1e-9)
        close("J reference revenue", plan["reference_revenue_cny"], 3_285_582.4470592756, 0.01)
        close("J expected revenue", plan["expected_revenue_cny"], 3_295_135.308125722, 0.01)
        close("J CVaR10", plan["cvar_10_cny"], 3_238_909.562358778, 0.01)
        close("J reference hedge value", plan["reference_hedge_value_cny"], 102_568.37723157229, 0.01)
        close("J carry", plan["carry_cny"], 145_611.17296875577, 0.01)
        close("J curve shape", plan["shape_cny"], -43_042.795737182256, 0.01)
        check(abs(plan["hedge_value_identity_gap"]) < 1e-6, "J carry + shape identity holds")
        close("J required trade", plan["required_trade_mwh"], -20.0, 1e-9)
        check(plan["required_trade_action"] == "减仓", "J required trade is a trim")
        check(len(plan["scenarios"]) == 5, "J five price scenarios")
        close(
            "J worst scenario is CVaR10",
            min(item["total_revenue_cny"] for item in plan["scenarios"]),
            plan["cvar_10_cny"],
            1e-6,
        )
        close("J rolling final target", rolling_out["final_target_position_mwh"], 7480.0, 1e-9)
        close("J rolling lot gap", rolling_out["lot_gap_mwh"], 20.0, 1e-9)
        close("J rolling final ratio", rolling_out["final_hedge_ratio"], 0.8522727272727273, 1e-12)
        check(len(rolling_out["rows"]) == 5, "J five rolling days")
        close("J rolling day -4 trade", rolling_out["rows"][0]["required_trade_mwh"], 182.5, 1e-9)
        close("J rolling day -2 trade", rolling_out["rows"][2]["required_trade_mwh"], -187.0, 1e-9)
        close("J bridge plan revenue", bridge["plan_revenue_cny"], 3_285_582.447059269, 0.01)
        close("J bridge actual revenue", bridge["actual_revenue_cny"], 3_240_925.8805671693, 0.01)
        close("J bridge delta", bridge["delta_cny"], -44_656.56649209978, 0.01)
        check(abs(bridge["identity_gap"]) < 1e-6, "J bridge identity holds")
        check(len(bridge["buckets"]) == 6, "J bridge has six buckets")
        close(
            "J bridge buckets sum to delta",
            sum(item["amount"] for item in bridge["buckets"]),
            bridge["delta_cny"],
            1e-6,
        )
        amounts = {item["category"]: item["amount"] for item in bridge["buckets"]}
        close("J bridge output volume", amounts["output_volume"], -54_111.239187070445, 0.01)
        close("J bridge spot price", amounts["spot_price"], 11_681.85681309089, 0.01)
        close("J bridge contract shape", amounts["contract_shape"], -4_030.7955588320747, 0.01)
        close("J bridge output shape", amounts["output_shape"], 2_433.4447987185467, 0.01)
        close("J bridge interaction", amounts["interaction"], -1_000.5611641149402, 0.01)
        close("J bridge contract volume", amounts["contract_volume"], 370.7278061080034, 0.01)
        check(
            result["summary"]["policy_fingerprint"] == "f1e965abe40e",
            "J hedge policy fingerprint is locked",
        )
        check(len(result["bridge_detail"]) == 5, "J bridge detail lists top five slots")
        check((Path(tmp) / "book_sheet.csv").exists(), "J book sheet is written")
        check((Path(tmp) / "rolling.csv").exists(), "J rolling sheet is written")
        check((Path(tmp) / "bridge.csv").exists(), "J bridge csv is written")
        check((Path(tmp) / "review.md").exists(), "J review is written")

    # ---- K. 交易台总盘：归一化、分组与份额（portfolio.py）------------------
    hedge_summary = {
        "instance_id": "hedge-demo",
        "trading_day": "2026-11-18",
        "data_cutoff": "2026-11-13",
        "policy": {
            "profile_id": "hedge-profile",
            "max_hedge_ratio": 1.0,
            "target_hedge_ratio": 0.85,
            "grade": "D",
        },
        "policy_fingerprint": "fp-hedge",
        "plan": {
            "forecast_energy_mwh": 1000.0,
            "position_energy_mwh": 850.0,
            "hedge_ratio": 0.85,
            "expected_revenue_cny": 400000.0,
            "reference_revenue_cny": 390000.0,
            "cvar_10_cny": 360000.0,
            "carry_cny": 20000.0,
            "shape_cny": -5000.0,
            "reference_hedge_value_cny": 15000.0,
            "expected_hedge_value_cny": 10000.0,
            "hedge_value_identity_gap": 0.0,
        },
        "actual": {
            "revenue_cny": 395000.0,
            "output_energy_mwh": 980.0,
            "hedge_ratio": 0.87,
        },
        "warnings": ["w1", "w2"],
        "files": {"bridge": "bridge.json"},
    }
    hedge_bridge = {
        "plan_revenue_cny": 390000.0,
        "actual_revenue_cny": 395000.0,
        "delta_cny": 5000.0,
        "identity_gap": 1e-10,
        "plan_output_energy_mwh": 1000.0,
        "actual_output_energy_mwh": 980.0,
    }
    hedge_record = portfolio.normalize_summary(
        hedge_summary,
        bridge=hedge_bridge,
        entry={"label": "Hedge", "province": "山东", "kind": "hedge", "period": "daily"},
    )
    check(hedge_record["value_kind"] == "revenue", "K hedge is revenue caliber")
    close("K hedge expected", hedge_record["expected_cny"], 400000.0, 1e-9)
    close("K hedge reference", hedge_record["reference_cny"], 390000.0, 1e-9)
    close("K hedge actual", hedge_record["actual_cny"], 395000.0, 1e-9)
    close("K hedge delta", hedge_record["delta_cny"], 5000.0, 1e-9)
    close("K hedge energy deviation", hedge_record["energy_deviation"], -0.02, 1e-12)
    close("K hedge carry", hedge_record["carry_cny"], 20000.0, 1e-9)
    close("K hedge shape", hedge_record["shape_cny"], -5000.0, 1e-9)
    close("K hedge reference value", hedge_record["hedge_value_reference_cny"], 15000.0, 1e-9)
    close("K hedge ratio deviation", hedge_record["hedge_ratio_actual"] - hedge_record["hedge_ratio_target"], 0.02, 1e-12)
    close("K hedge limit utilisation", hedge_record["constraint"]["utilization"], 0.85, 1e-12)
    check(hedge_record["status"] == "ok", "K hedge has actual value")
    hedge_derived = review.derive(hedge_record)
    close("K hedge review delta pct", hedge_derived["delta_pct"], 5000.0 / 390000.0, 1e-12)
    close("K hedge forecast error", hedge_derived["forecast_error_pct"], -0.02, 1e-12)
    check(hedge_derived["declaration_deviation_pct"] is None, "K hedge has no declaration deviation")
    close("K hedge ratio review deviation", hedge_derived["hedge_ratio_deviation"], 0.02, 1e-12)

    retail_summary = {
        "instance_id": "retail-demo",
        "trading_day": "2026-11-18",
        "data_cutoff": "2026-11-13",
        "policy": {"profile_id": "retail-profile", "grade": "D"},
        "pricing": {"coverage_ratio": 0.75},
        "plan": {
            "energy_mwh": 1000.0,
            "expected_net_margin_cny": 10000.0,
            "net_margin_at_reference_cny": 12000.0,
            "cvar_10_cny": -5000.0,
        },
        "warnings": ["w3"],
        "files": {"bridge": "bridge.json"},
    }
    retail_bridge = {
        "plan_net_cny": 12000.0,
        "actual_net_cny": 11000.0,
        "identity_gap": -2e-10,
        "plan_energy_mwh": 1000.0,
        "actual_energy_mwh": 1020.0,
        "actual_deviation_cny": 100.0,
    }
    retail_record = portfolio.normalize_summary(
        retail_summary,
        bridge=retail_bridge,
        entry={"label": "Retail", "province": "广东", "kind": "retail", "period": "daily"},
    )
    check(retail_record["value_kind"] == "net_margin", "K retail is net margin caliber")
    close("K retail expected", retail_record["expected_cny"], 10000.0, 1e-9)
    close("K retail reference", retail_record["reference_cny"], 12000.0, 1e-9)
    close("K retail actual uses net not revenue", retail_record["actual_cny"], 11000.0, 1e-9)
    close("K retail delta", retail_record["delta_cny"], -1000.0, 1e-9)
    close("K retail assessment", retail_record["assessment_cny"], 100.0, 1e-9)
    close("K retail energy deviation", retail_record["energy_deviation"], 0.02, 1e-12)
    retail_derived = review.derive(retail_record)
    close("K retail plan energy deviation", retail_derived["plan_energy_deviation_pct"], 0.02, 1e-12)
    check(retail_derived["forecast_error_pct"] is None, "K retail has no forecast error label")
    close("K retail regret", retail_derived["regret_cny"], 1000.0, 1e-9)

    coal_summary = {
        "meta": {"instance_id": "coal-demo", "province": "甘肃", "grade": "B/C"},
        "fingerprint": "fp-coal",
        "base": {"profit_cny": 1000000.0, "generation_mwh": 500000.0},
        "modes": [],
        "configured_default_profit_cny": 900000.0,
        "warnings": [],
    }
    coal_record = portfolio.normalize_summary(
        coal_summary,
        entry={"label": "Coal", "province": "甘肃", "kind": "capacity", "period": "annual"},
    )
    check(coal_record["horizon"] == "annual", "K coal is annual")
    check(coal_record["value_kind"] == "profit", "K coal is profit caliber")
    close("K coal expected", coal_record["expected_cny"], 1000000.0, 1e-9)
    close("K coal reference", coal_record["reference_cny"], 900000.0, 1e-9)
    check(coal_record["actual_cny"] is None, "K coal keeps actual as N/A")
    check(coal_record["status"] == "model_only", "K coal is model only")
    check(review.is_annual_summary(coal_summary), "K coal is detected as annual")
    check(not review.is_annual_summary(hedge_summary), "K hedge is detected as daily")

    groups = portfolio.aggregate([hedge_record, retail_record, coal_record])
    check(len(groups) == 3, "K three calibers stay separate")
    daily_revenue = next(row for row in groups if row["horizon"] == "daily" and row["value_kind"] == "revenue")
    daily_net = next(row for row in groups if row["horizon"] == "daily" and row["value_kind"] == "net_margin")
    annual_profit = next(row for row in groups if row["horizon"] == "annual" and row["value_kind"] == "profit")
    close("K daily revenue total", daily_revenue["expected_cny"], 400000.0, 1e-9)
    close("K daily net total is not mixed", daily_net["expected_cny"], 10000.0, 1e-9)
    close("K annual profit total", annual_profit["expected_cny"], 1000000.0, 1e-9)
    weighted = portfolio.aggregate([{**hedge_record, "share": 0.5}])
    close("K share scales expected", weighted[0]["expected_cny"], 200000.0, 1e-9)
    close("K share scales actual", weighted[0]["actual_cny"], 197500.0, 1e-9)
    check(portfolio.fmt_money(349.19) == "0.03 万", "K small money keeps two decimals")

    missing_record = portfolio.normalize_summary(
        {
            "instance_id": "hedge-missing",
            "trading_day": "2026-11-18",
            "plan": {
                "expected_revenue_cny": 400000.0,
                "reference_revenue_cny": 390000.0,
                "cvar_10_cny": 360000.0,
            },
        },
        entry={"kind": "hedge", "value_kind": "revenue", "period": "daily"},
    )
    partial_group = portfolio.aggregate([hedge_record, missing_record])[0]
    close("K partial group full reference", partial_group["reference_cny"], 780000.0, 1e-9)
    close("K partial group matched reference", partial_group["matched_reference_cny"], 390000.0, 1e-9)
    close("K partial group matched actual", partial_group["matched_actual_cny"], 395000.0, 1e-9)
    close("K partial group delta uses matched", partial_group["delta_cny"], 5000.0, 1e-9)
    close("K partial group actual stays partial", partial_group["actual_cny"], 395000.0, 1e-9)
    check(partial_group["actual_packs"] == 1 and partial_group["delta_packs"] == 1, "K partial group counts matched packs")

    earlier_net = portfolio.normalize_summary(
        {
            "instance_id": "retail-earlier",
            "trading_day": "2026-11-17",
            "plan": {"expected_net_margin_cny": 9000.0, "reference_net_margin_cny": 10000.0},
        },
        entry={"label": "Earlier", "province": "广东", "kind": "retail", "period": "daily"},
    )
    focus_records = [hedge_record, earlier_net]
    focus_groups = portfolio.aggregate(focus_records)
    focus_brief = portfolio.build_brief(focus_records, focus_groups, focus_trading_day="2026-11-18")
    check(focus_brief.count("2026-11-17 交易净收益") == 1, "K focus-missing net day appears once")
    check("其他交易日" not in focus_brief, "K focus-missing net day is not repeated as other")

    mixed_summary = {
        "instance_id": "mixed-demo",
        "trading_day": "2026-11-18",
        "plan": {
            "expected_net_margin_cny": 10000.0,
            "reference_net_margin_cny": 12000.0,
            "expected_revenue_cny": 400000.0,
            "reference_revenue_cny": 390000.0,
            "reference_profit_cny": 800000.0,
        },
        "base": {"profit_cny": 1000000.0},
        "actual": {
            "net_margin_cny": 11000.0,
            "revenue_cny": 395000.0,
            "profit_cny": 900000.0,
        },
    }
    mixed_net = portfolio.normalize_summary(
        mixed_summary,
        entry={"kind": "retail", "value_kind": "net_margin", "period": "daily"},
    )
    close("K mixed net expected stays net", mixed_net["expected_cny"], 10000.0, 1e-9)
    close("K mixed net reference stays net", mixed_net["reference_cny"], 12000.0, 1e-9)
    close("K mixed net actual stays net", mixed_net["actual_cny"], 11000.0, 1e-9)
    mixed_revenue = portfolio.normalize_summary(
        mixed_summary,
        entry={"kind": "hedge", "value_kind": "revenue", "period": "daily"},
    )
    close("K mixed revenue expected stays revenue", mixed_revenue["expected_cny"], 400000.0, 1e-9)
    close("K mixed revenue reference stays revenue", mixed_revenue["reference_cny"], 390000.0, 1e-9)
    close("K mixed revenue actual stays revenue", mixed_revenue["actual_cny"], 395000.0, 1e-9)
    mixed_profit = portfolio.normalize_summary(
        mixed_summary,
        entry={"kind": "capacity", "value_kind": "profit", "period": "annual"},
    )
    close("K mixed profit expected stays profit", mixed_profit["expected_cny"], 1000000.0, 1e-9)
    close("K mixed profit reference stays profit", mixed_profit["reference_cny"], 800000.0, 1e-9)
    close("K mixed profit actual stays profit", mixed_profit["actual_cny"], 900000.0, 1e-9)

    no_reference = portfolio.normalize_summary(
        {
            "instance_id": "no-reference",
            "trading_day": "2026-11-18",
            "plan": {"expected_revenue_cny": 400000.0},
            "actual": {"revenue_cny": 395000.0},
        },
        entry={"kind": "hedge", "value_kind": "revenue", "period": "daily"},
    )
    check(no_reference["delta_cny"] is None, "K delta is N/A without a reference")
    close("K delta vs expected still populated", no_reference["delta_vs_expected_cny"], -5000.0, 1e-9)

    with tempfile.TemporaryDirectory() as raw:
        summary_pack = Path(raw) / "summary-pack"
        demo_summary = summary_pack / "out" / "demo" / "summary.json"
        new_summary = summary_pack / "out" / "new-run" / "summary.json"
        demo_summary.parent.mkdir(parents=True)
        new_summary.parent.mkdir(parents=True)
        demo_summary.write_text("{}", encoding="utf-8")
        new_summary.write_text("{}", encoding="utf-8")
        os.utime(demo_summary, (1_700_000_000, 1_700_000_000))
        os.utime(new_summary, (1_700_000_100, 1_700_000_100))
        check(portfolio.find_summary(summary_pack, {}) == new_summary, "K portfolio picks newest summary")
        check(rulecheck.find_summary(summary_pack) == new_summary, "K rulecheck picks newest summary")
        check(
            portfolio.find_summary(summary_pack, {"summary": str(demo_summary)}) == demo_summary,
            "K explicit summary still wins",
        )

        archive = Path(raw) / "archive"
        inside = archive / "2026-11-18" / "pack" / "summary.json"
        inside.parent.mkdir(parents=True)
        inside.write_text("{}", encoding="utf-8")
        outside = Path(raw) / "2026-11-19" / "pack" / "summary.json"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}", encoding="utf-8")
        check(review.archive_date(inside, archive) == "2026-11-18", "K archive date reads inside root")
        check(review.archive_date(outside, archive) == "", "K archive date ignores outside root")

        orphan_archive = Path(raw) / "orphan-archive"
        orphan_summary = orphan_archive / "pack" / "summary.json"
        orphan_summary.parent.mkdir(parents=True)
        orphan_summary.write_text(
            json.dumps({"plan": {"expected_net_margin_cny": 1.0}}),
            encoding="utf-8",
        )
        orphan_runs, _, _, orphan_errors = review.collect_runs(orphan_archive)
        check(not orphan_runs, "K daily summary without trading_day is skipped")
        check(len(orphan_errors) == 1, "K daily summary without trading_day is reported")

    # ---- L. 月度评分：MAPE、CVaR 命中、桥残差与日度合计（review.py）--------
    hedge_run_2 = review.derive(
        portfolio.normalize_summary(
            {
                **hedge_summary,
                "actual": {"revenue_cny": 380000.0, "output_energy_mwh": 990.0, "hedge_ratio": 0.86},
            },
            bridge={**hedge_bridge, "actual_revenue_cny": 380000.0, "actual_output_energy_mwh": 990.0, "delta_cny": -10000.0},
            entry={"label": "Hedge", "province": "山东", "kind": "hedge", "period": "daily"},
        )
    )
    instance_rows = review.instance_rows([hedge_derived, hedge_run_2], review.DEFAULT_THRESHOLDS)
    check(len(instance_rows) == 1, "L one instance row")
    close("L plan MAPE", instance_rows[0]["plan_mape"], (5000.0 / 390000.0 + 10000.0 / 390000.0) / 2, 1e-12)
    close("L CVaR hit rate", instance_rows[0]["cvar_hit_rate"], 1.0, 1e-12)
    close("L warnings mean", instance_rows[0]["warnings_mean"], 2.0, 1e-12)
    check(instance_rows[0]["status"] == "正常", "L instance status is normal")

    retail_run_2 = review.derive(
        portfolio.normalize_summary(
            retail_summary,
            bridge={**retail_bridge, "actual_net_cny": 11000.0, "actual_energy_mwh": 980.0},
            entry={"label": "Retail", "province": "广东", "kind": "retail", "period": "daily"},
        )
    )
    days = review.daily_net_totals([retail_derived, retail_run_2])
    check(len(days) == 1, "L daily totals group by day")
    close("L daily reference total", days[0]["reference_cny"], 24000.0, 1e-9)
    close("L daily actual total", days[0]["actual_cny"], 22000.0, 1e-9)
    close("L daily delta total", days[0]["delta_cny"], -2000.0, 1e-9)

    values = review.kpi_values([hedge_derived, retail_derived], instance_rows, [], 3)
    close("L actual coverage", values["actual_coverage"], 1.0, 1e-12)
    close("L plan mape mixed sample", values["plan_mape"], (5000.0 / 390000.0 + 1000.0 / 12000.0) / 2, 1e-12)
    close("L CVaR sample count", float(values["cvar_n"]), 2.0, 1e-12)
    close("L assessment sample count", float(values["assessment_n"]), 1.0, 1e-12)
    close("L bridge gap max", values["bridge_gap_max"], 2e-10, 1e-15)
    close("L warnings per run", values["warnings_per_run"], 1.5, 1e-12)

    scorecard, summary = review.build_scorecard(
        [hedge_derived, retail_derived],
        label="合成批次",
        month="2026-11",
        duplicates=[],
        annual_skipped=1,
        errors=[],
        thresholds=review.DEFAULT_THRESHOLDS,
        archive_text="/tmp/archive",
    )
    check("月度交易质量评分卡" in scorecard, "L scorecard title")
    check("carry+shape−参考" in scorecard, "L scorecard uses the reference hedge value")
    check(summary["run_count"] == 2, "L scorecard run count")
    check(len(summary["hedge_runs"]) == 1, "L scorecard lists hedge run")
    close("L scorecard hedge reference", summary["hedge_runs"][0]["hedge_value_reference_cny"], 15000.0, 1e-9)
    check("跳过年度/月度包 1 个" in scorecard, "L scorecard reports annual skips")

    # ---- M. 省级规则包与申报前校验（rulecheck.py）--------------------------
    check(len(rulecheck.PROVINCE_RULE_FILES) == 6, "M six provincial markets mapped")
    for province, filename in sorted(rulecheck.PROVINCE_RULE_FILES.items()):
        path = RULES_DIR / filename
        check(path.is_file(), f"M rule file exists: {province}")
        rule = rulecheck.load_json(path)
        check(rule.get("schema_version") == 1, f"M schema v1: {province}")
        check(rule.get("province") == province, f"M province matches: {province}")
        check(isinstance(rule.get("spot"), dict), f"M spot block: {province}")
        check(bool(rule["spot"].get("grade")), f"M spot grade: {province}")

    expired = rulecheck.new_report(REPO_ROOT, "period-expired", "山东", "thermal")
    ok = rulecheck.check_period(
        expired,
        {"effective_from": "2026-01-01", "effective_to": "2026-06-30"},
        "测试规则",
        date(2026, 7, 1),
        hard=True,
        prefix="test.expired",
    )
    check(not ok and expired["counts"]["block"] == 1, "M expired period blocks")
    check("过期" in expired["checks"][-1]["message"], "M expired message says expired")

    future = rulecheck.new_report(REPO_ROOT, "period-future", "山东", "thermal")
    ok = rulecheck.check_period(
        future,
        {"effective_from": "2026-12-01"},
        "测试规则",
        date(2026, 11, 17),
        hard=False,
        prefix="test.future",
    )
    check(not ok and future["counts"]["warn"] == 1, "M unverified future period warns")
    check("尚未生效" in future["checks"][-1]["message"], "M future message says not yet effective")

    hard = {"limits_enforcement": "hard"}
    partial = {"limits_enforcement": "partial"}
    model = {"limits_enforcement": "model"}
    check(rulecheck.limit_level(hard, "declare_cap_cny_per_mwh") == "block", "M hard cap blocks")
    check(rulecheck.limit_level(partial, "declare_floor_cny_per_mwh") == "block", "M partial floor blocks")
    check(rulecheck.limit_level(partial, "declare_cap_cny_per_mwh") == "warn", "M partial cap warns")
    check(rulecheck.limit_level(model, "declare_cap_cny_per_mwh") == "warn", "M model cap warns")
    check(
        rulecheck.limit_level(hard, "declare_cap_cny_per_mwh", band=True) == "warn",
        "M asset band always warns",
    )

    band_spot = {
        "declare_floor_cny_per_mwh": -80,
        "declare_cap_cny_per_mwh": 1300,
        "limits_enforcement": "hard",
        "asset_bands": {
            "thermal": {
                "declare_floor_cny_per_mwh": 0,
                "declare_cap_cny_per_mwh": 800,
                "enforcement": "soft",
            }
        },
    }
    band = rulecheck.price_band(band_spot, "thermal")
    close("M thermal band floor", band["floor"], 0.0, 1e-9)
    close("M thermal band cap", band["cap"], 800.0, 1e-9)
    check("thermal" in band["source"], "M thermal band label")
    check(rulecheck.bid_price(band, -1.0)[0] == "warn", "M below soft floor warns")
    check(rulecheck.bid_price(band, 801.0)[0] == "warn", "M above soft cap warns")
    check(rulecheck.bid_price(band, 500.0)[0] is None, "M inside band passes")

    shandong_pack = REPO_ROOT / "skills" / "spot-bidding-quant" / "instances" / "shandong-thermal-2026-11"
    shandong_report = rulecheck.evaluate(
        shandong_pack,
        RULES_DIR,
        date(2026, 11, 18),
        date(2026, 11, 17),
        entry={"province": "山东"},
    )
    check(shandong_report["status"] == "warn", "M Shandong thermal is warn")
    check(shandong_report["counts"]["block"] == 0, "M Shandong thermal has no block")

    shandong_rule = rulecheck.load_json(RULES_DIR / "shandong.json")
    shandong_storage_capacity = rulecheck.new_report(REPO_ROOT, "shandong-storage-cap", "山东", "storage")
    rulecheck.check_capacity(shandong_storage_capacity, {}, shandong_rule, {}, date(2026, 11, 18))
    check(
        any(
            check["id"] == "capacity.eligibility"
            and check["level"] == "warn"
            and "未核实" in check["message"]
            for check in shandong_storage_capacity["checks"]
        ),
        "M Shandong grid storage capacity is unverified",
    )

    mengxi_rule = rulecheck.load_json(RULES_DIR / "mengxi.json")
    mengxi_income = rulecheck.new_report(REPO_ROOT, "mengxi-cap-income", "蒙西", "thermal")
    rulecheck.check_capacity(
        mengxi_income,
        {},
        mengxi_rule,
        {"capacity_compensation_cny": 123.0},
        date(2026, 11, 18),
    )
    check(
        any(
            check["id"] == "capacity.eligibility" and check["level"] == "block"
            for check in mengxi_income["checks"]
        ),
        "M not_applicable capacity blocks income",
    )
    mengxi_clean = rulecheck.new_report(REPO_ROOT, "mengxi-cap-clean", "蒙西", "thermal")
    rulecheck.check_capacity(mengxi_clean, {}, mengxi_rule, {}, date(2026, 11, 18))
    check(
        any(
            check["id"] == "capacity.eligibility" and check["level"] == "pass"
            for check in mengxi_clean["checks"]
        ),
        "M not_applicable capacity passes without income",
    )

    check(rulecheck.mentions_ratio("峰≥平×160%、谷≤平×40%", 1.6), "M TOU matches 160 percent")
    check(rulecheck.mentions_ratio("峰≥平×160%、谷≤平×40%", 0.4), "M TOU matches 40 percent")
    check(not rulecheck.mentions_ratio("峰≥平×1600%", 1.6), "M TOU avoids substring false match")

    inter_pack = (
        REPO_ROOT
        / "skills"
        / "electricity-trading-expert"
        / "instances"
        / "gansu-wind-to-shandong-2026-11"
    )
    inter_report = rulecheck.evaluate(
        inter_pack,
        RULES_DIR,
        date(2026, 11, 18),
        date(2026, 11, 17),
        entry={"province": "甘肃"},
    )
    check(inter_report["status"] == "pass", "M Gansu interprovincial is pass")
    check(
        any(
            check["id"] == "interprovincial.effective" and check["level"] == "pass"
            for check in inter_report["checks"]
        ),
        "M interprovincial effective date passes",
    )

    shanxi_pack = REPO_ROOT / "skills" / "spot-bidding-quant" / "instances" / "shanxi-storage-2026-11"
    shanxi_report = rulecheck.evaluate(
        shanxi_pack,
        RULES_DIR,
        date(2026, 11, 19),
        date(2026, 11, 17),
        entry={"province": "山西"},
    )
    check(shanxi_report["status"] == "warn", "M Shanxi storage is warn")
    shanxi_capacity = next(
        check for check in shanxi_report["checks"] if check["id"] == "capacity.eligibility"
    )
    check(shanxi_capacity["level"] == "pass", "M grid_storage alias matches Shanxi ineligible list")
    check(
        any(
            check["id"] == "spot.asset_band" and check["level"] == "warn"
            for check in shanxi_report["checks"]
        ),
        "M Shanxi storage band remains a warn",
    )

    direct_pack = (
        REPO_ROOT
        / "skills"
        / "retail-electricity-risk"
        / "instances"
        / "guangdong-multi-user-direct-2026-11"
    )
    direct_report = rulecheck.evaluate(
        direct_pack,
        RULES_DIR,
        date(2026, 11, 18),
        date(2026, 11, 17),
        entry={"province": "广东"},
    )
    check(direct_report["status"] == "warn", "M Guangdong direct is warn")
    check(
        any(
            check["id"] == "direct.effective" and check["level"] == "pass"
            for check in direct_report["checks"]
        ),
        "M direct connection rule is effective",
    )
    check(
        not any(check["id"] == "capacity.eligibility" for check in direct_report["checks"]),
        "M direct pack skips capacity eligibility",
    )
    check(
        any(
            check["id"] == "rule.deadline" and check["level"] == "skip"
            for check in direct_report["checks"]
        ),
        "M direct pack skips spot deadline",
    )
    check(
        any(
            check["id"] == "rule.limits_status" and check["level"] == "skip"
            for check in direct_report["checks"]
        ),
        "M direct pack skips spot limit enforcement",
    )

    province_wind_pack = REPO_ROOT / "skills" / "spot-bidding-quant" / "instances" / "gansu-wind-2027"
    province_wind_report = rulecheck.evaluate(
        province_wind_pack,
        RULES_DIR,
        date(2027, 1, 15),
        date(2026, 11, 17),
        entry={"province": "甘肃"},
    )
    check(province_wind_report["status"] == "warn", "M Gansu wind 2027 is warn")
    check(
        not any(check["id"].startswith("bid.interprovincial") for check in province_wind_report["checks"]),
        "M provincial bid does not use interprovincial bid rules",
    )

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        def write_bid(path, rows):
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

        shandong_rule = rulecheck.load_json(RULES_DIR / "shandong.json")
        gansu_rule = rulecheck.load_json(RULES_DIR / "gansu.json")
        thermal_instance = {
            "meta": {"province": "山东", "entity_type": "燃煤电厂"},
            "asset": {"type": "thermal", "capacity_mw": 350, "min_output_mw": 120},
            "policy": {"regulation_reserve_mw": 20},
        }
        pass_rows = [
            {
                "date": "2026-11-18",
                "slot": slot,
                "must_run_mw": 120,
                "quantity_mw": 200,
                "price_cny_per_mwh": 500,
            }
            for slot in range(96)
        ]
        pass_path = tmp / "pass.csv"
        write_bid(pass_path, pass_rows)
        pass_report = rulecheck.new_report(tmp, "bid-pass", "山东", "thermal")
        rulecheck.check_bid(
            pass_report,
            tmp,
            pass_path,
            thermal_instance,
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            pass_report["counts"]["block"] == 0 and pass_report["counts"]["warn"] == 0,
            "M valid thermal bid passes",
        )
        check(
            any(
                check["id"] == "bid.price_band" and check["level"] == "pass"
                for check in pass_report["checks"]
            ),
            "M valid bid price passes",
        )
        check(
            any(
                check["id"] == "bid.thermal_total" and check["level"] == "pass"
                for check in pass_report["checks"]
            ),
            "M thermal bid total passes",
        )

        partial_date_rows = [dict(row) for row in pass_rows]
        partial_date_rows[0]["date"] = ""
        partial_date_path = tmp / "partial-date.csv"
        write_bid(partial_date_path, partial_date_rows)
        partial_date_report = rulecheck.new_report(tmp, "bid-partial-date", "山东", "thermal")
        rulecheck.check_bid(
            partial_date_report,
            tmp,
            partial_date_path,
            thermal_instance,
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.date" and check["level"] == "warn"
                for check in partial_date_report["checks"]
            ),
            "M partial blank dates warn",
        )

        partial_price_rows = [dict(row) for row in pass_rows]
        partial_price_rows[0]["price_cny_per_mwh"] = ""
        partial_price_path = tmp / "partial-price.csv"
        write_bid(partial_price_path, partial_price_rows)
        partial_price_report = rulecheck.new_report(tmp, "bid-partial-price", "山东", "thermal")
        rulecheck.check_bid(
            partial_price_report,
            tmp,
            partial_price_path,
            thermal_instance,
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.price_band"
                and check["level"] == "warn"
                and "缺价格" in check["message"]
                for check in partial_price_report["checks"]
            ),
            "M partial blank prices warn",
        )

        partial_spot = {
            "points_per_day": 96,
            "market_time_unit_min": 15,
            "declare_floor_cny_per_mwh": 40,
            "declare_cap_cny_per_mwh": 500,
            "clear_floor_cny_per_mwh": 40,
            "clear_cap_cny_per_mwh": 650,
            "limits_enforcement": "partial",
        }
        mixed_price_rows = [
            {**row, "price_cny_per_mwh": 500}
            for row in pass_rows
        ]
        mixed_price_rows[0]["price_cny_per_mwh"] = 30
        mixed_price_rows[1]["price_cny_per_mwh"] = 600
        mixed_price_path = tmp / "mixed-price.csv"
        write_bid(mixed_price_path, mixed_price_rows)
        mixed_price_report = rulecheck.new_report(tmp, "bid-mixed-price", "山东", "thermal")
        rulecheck.check_bid(
            mixed_price_report,
            tmp,
            mixed_price_path,
            thermal_instance,
            shandong_rule,
            partial_spot,
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.price_band" and check["level"] == "block"
                for check in mixed_price_report["checks"]
            ),
            "M price block is not overwritten by a later warn",
        )

        gansu_instance = {
            "meta": {"province": "甘肃", "entity_type": "燃煤电厂"},
            "asset": {"type": "thermal", "capacity_mw": 660, "min_output_mw": 300},
            "policy": {"regulation_reserve_mw": 20},
        }
        bad_rows = [
            {
                "date": "2026-11-18",
                "slot": slot,
                "must_run_mw": 300,
                "quantity_mw": 400,
                "price_cny_per_mwh": 600,
            }
            for slot in range(96)
        ]
        bad_path = tmp / "bad.csv"
        write_bid(bad_path, bad_rows)
        bad_report = rulecheck.new_report(tmp, "bid-bad", "甘肃", "thermal")
        rulecheck.check_bid(
            bad_report,
            tmp,
            bad_path,
            gansu_instance,
            gansu_rule,
            gansu_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(bad_report["counts"]["block"] >= 2, "M invalid bid blocks")
        check(
            any(
                check["id"] == "bid.price_band" and check["level"] == "block"
                for check in bad_report["checks"]
            ),
            "M hard price cap blocks",
        )
        check(
            any(
                check["id"] == "bid.thermal_total" and check["level"] == "block"
                for check in bad_report["checks"]
            ),
            "M thermal total cap blocks",
        )

        short_rows = bad_rows[:95]
        short_path = tmp / "short.csv"
        write_bid(short_path, short_rows)
        short_report = rulecheck.new_report(tmp, "bid-short", "甘肃", "thermal")
        rulecheck.check_bid(
            short_report,
            tmp,
            short_path,
            gansu_instance,
            gansu_rule,
            gansu_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.coverage" and check["level"] == "block"
                for check in short_report["checks"]
            ),
            "M missing slot blocks",
        )

        duplicate_rows = pass_rows + [dict(pass_rows[0])]
        duplicate_path = tmp / "duplicate.csv"
        write_bid(duplicate_path, duplicate_rows)
        duplicate_report = rulecheck.new_report(tmp, "bid-duplicate", "山东", "thermal")
        rulecheck.check_bid(
            duplicate_report,
            tmp,
            duplicate_path,
            thermal_instance,
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.duplicates" and check["level"] == "block"
                for check in duplicate_report["checks"]
            ),
            "M duplicate slot blocks",
        )
        check(rulecheck.finish(duplicate_report)["status"] == "block", "M finish prioritizes block")

        wind_instance = {
            "meta": {"province": "山东", "entity_type": "风电"},
            "asset": {"type": "wind", "capacity_mw": 100, "grid_connection": {"export_limit_mw": 0}},
        }
        wind_zero_rows = [
            {
                "date": "2026-11-18",
                "slot": slot,
                "forecast_mw": 1,
                "declared_mw": 1,
                "bid_price_cny_per_mwh": 500,
            }
            for slot in range(96)
        ]
        wind_zero_path = tmp / "wind-zero.csv"
        write_bid(wind_zero_path, wind_zero_rows)
        wind_zero_report = rulecheck.new_report(tmp, "wind-zero", "山东", "wind")
        rulecheck.check_bid(
            wind_zero_report,
            tmp,
            wind_zero_path,
            wind_instance,
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.wind_capacity" and check["level"] == "block"
                for check in wind_zero_report["checks"]
            ),
            "M explicit zero export limit is preserved",
        )

        wind_missing_rows = [
            {
                "date": "2026-11-18",
                "slot": slot,
                "declared_mw": 1,
                "bid_price_cny_per_mwh": 500,
            }
            for slot in range(96)
        ]
        wind_missing_path = tmp / "wind-missing-forecast.csv"
        write_bid(wind_missing_path, wind_missing_rows)
        wind_missing_report = rulecheck.new_report(tmp, "wind-missing", "山东", "wind")
        rulecheck.check_bid(
            wind_missing_report,
            tmp,
            wind_missing_path,
            {
                "meta": {"province": "山东", "entity_type": "风电"},
                "asset": {"type": "wind", "capacity_mw": 100},
            },
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.wind_forecast" and check["level"] == "skip"
                for check in wind_missing_report["checks"]
            ),
            "M wind without forecast skips forecast check",
        )

        thermal_no_capacity = {
            "meta": {"province": "山东", "entity_type": "燃煤电厂"},
            "asset": {"type": "thermal", "min_output_mw": 120},
            "policy": {"regulation_reserve_mw": 20},
        }
        no_capacity_report = rulecheck.new_report(tmp, "thermal-no-capacity", "山东", "thermal")
        rulecheck.check_bid(
            no_capacity_report,
            tmp,
            pass_path,
            thermal_no_capacity,
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.thermal_total" and check["level"] == "warn"
                for check in no_capacity_report["checks"]
            ),
            "M missing thermal capacity warns",
        )

        shanxi_rule = rulecheck.load_json(RULES_DIR / "shanxi.json")
        storage_instance = {
            "meta": {"province": "山西", "entity_type": "独立新型储能"},
            "asset": {
                "type": "storage",
                "power_mw": 50,
                "energy_mwh": 100,
                "soc_init": 0.5,
                "soc_min": 0.1,
                "soc_max": 0.9,
            },
        }
        storage_rows = [
            {
                "date": "2026-11-19",
                "slot": 0,
                "side": "charge",
                "quantity_mw": 10,
                "price_cny_per_mwh": 100,
            },
            {
                "date": "2026-11-19",
                "slot": 1,
                "side": "discharge",
                "quantity_mw": "",
                "price_cny_per_mwh": 100,
            },
        ]
        storage_path = tmp / "storage-missing.csv"
        write_bid(storage_path, storage_rows)
        storage_report = rulecheck.new_report(tmp, "storage-missing", "山西", "storage")
        rulecheck.check_bid(
            storage_report,
            tmp,
            storage_path,
            storage_instance,
            shanxi_rule,
            shanxi_rule["spot"],
            date(2026, 11, 19),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.storage_power"
                and check["level"] == "warn"
                and "quantity_mw" in check["message"]
                for check in storage_report["checks"]
            ),
            "M incomplete storage quantities warn",
        )
        check(
            any(
                check["id"] == "bid.storage_soc_rte" and check["level"] == "warn"
                for check in storage_report["checks"]
            ),
            "M missing RTE warns",
        )

        bad_summary_pack = tmp / "bad-summary-pack"
        (bad_summary_pack / "out" / "demo").mkdir(parents=True)
        (bad_summary_pack / "out" / "demo" / "summary.json").write_text("{", encoding="utf-8")
        (bad_summary_pack / "instance.json").write_text(
            json.dumps(
                {
                    "meta": {
                        "instance_id": "bad-summary",
                        "province": "山东",
                        "entity_type": "风电",
                        "data_cutoff": "2026-11-18",
                    },
                    "asset": {"type": "wind", "capacity_mw": 10},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bad_summary_report = rulecheck.evaluate(
            bad_summary_pack,
            RULES_DIR,
            None,
            date(2026, 11, 17),
            entry={"province": "山东"},
        )
        check(
            any(
                check["id"] == "summary.file" and check["level"] == "warn"
                for check in bad_summary_report["checks"]
            ),
            "M malformed summary warns",
        )

        retail_bid_report = rulecheck.new_report(tmp, "retail-bid", "广东", "retail")
        rulecheck.check_bid(
            retail_bid_report,
            tmp,
            pass_path,
            {"meta": {"province": "广东", "entity_type": "售电公司"}},
            shandong_rule,
            shandong_rule["spot"],
            date(2026, 11, 18),
            explicit=True,
        )
        check(
            any(
                check["id"] == "bid.file" and check["level"] == "skip"
                for check in retail_bid_report["checks"]
            ),
            "M non-spot pack ignores bid CSV",
        )

        result = rulecheck.build_result([duplicate_report], date(2026, 11, 17), "selftest")
        check(result["summary"]["block"] == 1, "M result counts block")
        markdown = rulecheck.build_markdown(result)
        check("省级规则包 · 申报前校验" in markdown, "M markdown title")
        check("不提交报价" in markdown, "M markdown keeps read-only boundary")
        check("bid.duplicates" in markdown, "M markdown includes check ids")

    print(f"\nAll electricity-trading-expert self-tests passed ({_COUNT} assertions).")


if __name__ == "__main__":
    main()
