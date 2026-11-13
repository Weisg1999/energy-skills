"""Self-test for the tariff and bill reference implementation.

Run from this directory:

    python selftest.py

or from the repository root:

    python skills/tariff-bill-optimization/tools/selftest.py

The assertions encode the worked examples in
skills/tariff-bill-optimization/SKILL.md. All curves are synthetic, generated
by ``curves.py``, and are not a forecast for any real customer or province.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import bill
import curves
import demand
import retail
import tariff


def close(name, actual, expected, tol):
    if abs(actual - expected) > tol:
        raise AssertionError(f"{name}: {actual} != {expected} (tol {tol})")
    print(f"ok  {name:<46} {actual:,.4f}")


def check(condition, name):
    if not condition:
        raise AssertionError(name)
    print(f"ok  {name}")


def raises(callable_, name):
    try:
        callable_()
    except ValueError:
        print(f"ok  {name}")
        return
    raise AssertionError(f"{name}: expected ValueError")


def main():
    # A. Monthly bill from the price-system note: 200 MWh at 10 kV.
    a = bill.bill_breakdown(
        {"flat": 200_000},
        {"flat": 0.42},
        transmission_price=0.15,
        system_price=0.068,
        fund_price=0.02,
        basic_fee=40_000,
    )
    close("A energy charge (CNY)", a["lines"]["energy"], 84_000.00, 0.01)
    close("A transmission (CNY)", a["lines"]["transmission"], 30_000.00, 0.01)
    close("A system operation (CNY)", a["lines"]["system"], 13_600.00, 0.01)
    close("A government fund (CNY)", a["lines"]["fund"], 4_000.00, 0.01)
    close("A basic charge (CNY)", a["lines"]["basic"], 40_000.00, 0.01)
    close("A total (CNY)", a["total"], 171_600.00, 0.01)
    close("A average price (CNY/kWh)", a["average_price"], 0.858, 1e-9)
    close("A energy share (%)", a["lines"]["energy"] / a["total"] * 100, 48.95, 0.01)

    # B. One month, three basic-charge modes: 1,600 kVA transformer, peak 1,150 kW.
    b = demand.compare_modes(
        [1_150.0],
        demand_price=40,
        capacity_price=32,
        transformer_kva=1_600,
    )
    close("B capacity mode (CNY/month)", b["rows"]["capacity"]["total"], 51_200.00, 0.01)
    close("B contracted demand (CNY/month)", b["rows"]["contract"]["total"], 43_809.52, 0.01)
    close("B actual demand (CNY/month)", b["rows"]["actual"]["total"], 46_000.00, 0.01)
    check(b["best"] == "contract", "B contracted demand wins")
    close("B saving vs capacity (CNY/month)", b["saving_vs_worst"], 7_390.48, 0.01)
    opt = demand.optimal_declared(1_150, 40)
    close("B optimal declared (kW)", opt["declared_kw"], 1_095.2381, 1e-4)
    close("B overrun (kW)", opt["over_kw"], 0.0, 1e-9)

    # C. Twelve months: peak 1,150 kW scaled by the monthly factors.
    monthly = {month: 1_150.0 * factor for month, factor in enumerate(curves.MONTH_FACTORS, 1)}
    c = demand.compare_modes(
        monthly,
        demand_price=40,
        capacity_price=32,
        transformer_kva=1_600,
    )
    close("C capacity mode (CNY/year)", c["rows"]["capacity"]["total"], 614_400.00, 0.01)
    close("C contracted demand (CNY/year)", c["rows"]["contract"]["total"], 500_304.76, 0.01)
    close("C actual demand (CNY/year)", c["rows"]["actual"]["total"], 525_320.00, 0.01)
    naive = 40 * max(monthly.values()) * 12
    close("C naive declaration (CNY/year)", naive, 629_280.00, 0.01)
    close("C optimisation saving (CNY/year)", naive - c["rows"]["contract"]["total"], 128_975.24, 0.01)
    close("C peak month maximum (kW)", max(monthly.values()), 1_311.00, 0.01)

    # D. Power-factor adjustment on the 131,600 CNY energy-side subtotal.
    d_low = bill.power_factor_adjustment(131_600, 0.85)
    d_high = bill.power_factor_adjustment(131_600, 0.92)
    close("D surcharge at 0.85 (CNY)", d_low["adjustment"], 3_290.00, 0.01)
    close("D reward at 0.92 (CNY)", d_high["adjustment"], -394.80, 0.01)
    close("D gap (CNY/month)", d_low["adjustment"] - d_high["adjustment"], 3_684.80, 0.01)

    # E. Retail packages on the same annual load (6.7 GWh).
    loads = curves.monthly_loads()
    dt = 0.25
    energy = sum(sum(loads[month]) * dt * curves.MONTH_DAYS[month - 1] for month in loads)
    close("E annual energy (kWh)", energy, 6_702_688.50, 1.0)
    fixed = retail.fixed_price_cost(loads, 0.60, dt_h=dt)
    tou = retail.tou_cost(loads, curves.tou_prices(), dt_h=dt)
    linked = retail.market_linked_cost(
        loads, curves.market_day(), dt_h=dt, pass_through=1.0, adder=0.05
    )
    close("E fixed 0.60 (CNY/year)", fixed, 4_021_613.10, 0.01)
    close("E TOU package (CNY/year)", tou, 4_509_570.56, 0.01)
    close("E market-linked base (CNY/year)", linked, 3_681_791.55, 0.01)
    close("E market beats fixed (CNY/year)", fixed - linked, 339_821.55, 0.01)

    low = retail.market_linked_cost(
        loads, curves.market_day(scale=0.8), dt_h=dt, pass_through=1.0, adder=0.05
    )
    high = retail.market_linked_cost(
        loads, curves.market_day(scale=1.2), dt_h=dt, pass_through=1.0, adder=0.05
    )
    close("E market scenario -20% (CNY/year)", low, 3_012_460.13, 0.01)
    close("E market scenario +20% (CNY/year)", high, 4_351_122.98, 0.01)
    close("E +20% vs fixed (CNY/year)", high - fixed, 329_509.88, 0.01)

    ranked = retail.compare_packages(
        loads,
        [
            {"name": "fixed", "type": "fixed", "price": 0.60},
            {"name": "tou", "type": "tou", "prices": curves.tou_prices()},
            {
                "name": "market",
                "type": "market",
                "market_prices": curves.market_day(),
                "pass_through": 1.0,
                "adder": 0.05,
            },
        ],
        dt_h=dt,
    )
    check(ranked[0]["name"] == "market" and ranked[-1]["name"] == "tou", "E ranking: market, fixed, TOU")

    # F. Shift 1,600 kWh from peak to valley on the synthetic industrial day.
    load = curves.industrial_day()
    shifted = tariff.shift_energy(
        load,
        curves.tou_prices(),
        source_period="peak",
        target_period="valley",
        energy_kwh=1_600,
        dt_h=dt,
        max_power_kw=1_300,
    )
    close("F energy moved (kWh)", shifted["moved_kwh"], 1_600.00, 0.01)
    close("F cost before (CNY/day)", shifted["cost_before"], 12_968.225, 0.01)
    close("F cost after (CNY/day)", shifted["cost_after"], 11_768.225, 0.01)
    close("F saving (CNY/day)", shifted["saving"], 1_200.00, 0.01)

    # G. Period table and daily TOU arithmetic.
    close("G valley hours", tariff.period_hours()["valley"], 9, 0)
    close("G flat hours", tariff.period_hours()["flat"], 10, 0)
    close("G peak hours", tariff.period_hours()["peak"], 4, 0)
    close("G critical hours", tariff.period_hours()["critical"], 1, 0)
    day = tariff.tou_energy_cost(load, curves.tou_prices(), dt_h=dt)
    close("G daily energy (kWh)", day["energy_kwh"], 19_275.00, 0.01)
    close("G daily cost (CNY)", day["cost"], 12_968.225, 0.01)
    close("G valley share (%)", day["by_period"]["valley"]["kwh"] / day["energy_kwh"] * 100, 24.50, 0.01)
    close("G peak share (%)", day["by_period"]["peak"]["kwh"] / day["energy_kwh"] * 100, 21.78, 0.01)
    check(tariff.validate_periods()[0] == "valley", "G period table covers hour 0")
    raises(lambda: tariff.validate_periods([("all", 0, 23)]), "G 23-hour table is rejected")
    raises(
        lambda: tariff.validate_periods([("a", 0, 13), ("b", 12, 24)]),
        "G overlapping table is rejected",
    )
    raises(
        lambda: tariff.shift_energy(load, curves.tou_prices(), "peak", "valley", 100, dt_h=dt, max_power_kw=1_000),
        "G shift below current peak is rejected",
    )

    # H. Determinism and no-op checks.
    again = bill.bill_breakdown(
        {"flat": 200_000}, {"flat": 0.42}, 0.15, 0.068, 0.02, 40_000
    )
    close("H repeat total (CNY)", again["total"], a["total"], 1e-9)
    zero = tariff.shift_energy(
        load, curves.tou_prices(), "peak", "valley", 0, dt_h=dt, max_power_kw=1_300
    )
    close("H zero shift saving (CNY)", zero["saving"], 0.0, 1e-9)

    # I. Jiangsu C&I storage instance: declaration and storage savings stay separate.
    pack_dir = (
        Path(__file__).resolve().parents[1]
        / "instances"
        / "jiangsu-ci-storage-2026-11"
    )
    spec = importlib.util.spec_from_file_location("jiangsu_ci_storage_instance", pack_dir / "run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    instance_path = pack_dir / "instance.json"
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    report = runner.validate_instance(config)
    print(f"ok  I instance config ok={report['ok']} warnings={len(report['warnings'])}")
    check(report["ok"], "I config validates")
    check(
        config["data_contract"]["load"]["months"] == 12
        and config["data_contract"]["load"]["points_per_month"] == 96,
        "I 12x96 load grid",
    )

    broken = json.loads(json.dumps(config))
    del broken["rules"]["basic_charge"]["grade"]
    raises(lambda: runner.validate_instance(broken), "I rule block without grade is rejected")

    bad_declared = json.loads(json.dumps(config))
    bad_declared["asset"]["contract_demand_kw"] = bad_declared["asset"]["transformer_kva"] + 100.0
    raises(lambda: runner.validate_instance(bad_declared), "I declaration above transformer is rejected")

    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_instance(
            instance_path,
            pack_dir / "data" / "load_demo.csv",
            Path(tmp),
        )
        summary = result["summary"]
        close("I baseline bill (CNY)", summary["baseline_total_cny"], 6_639_050.46, 0.05)
        close("I declaration-only bill (CNY)", summary["optimized_total_cny"], 6_586_795.22, 0.05)
        close("I with-storage bill (CNY)", summary["headline_total_cny"], 6_474_697.26, 0.05)
        close("I declaration saving (CNY)", summary["declaration_saving_cny"], 52_255.24, 0.05)
        close("I storage net saving (CNY)", summary["storage_saving_cny"], 70_072.39, 0.05)
        close("I total saving (CNY)", summary["net_saving_cny"], 122_327.63, 0.05)
        close("I storage capex (CNY)", summary["storage_capex_cny"], 900_000.0, 0.01)
        close("I payback (years)", summary["payback_years"], 12.8439, 1e-3)
        close("I discharge (MWh)", summary["discharge_mwh"], 113.9265, 1e-3)
        close("I charge (MWh)", summary["charge_mwh"], 126.5849, 1e-3)
        close("I average shave (kW)", summary["average_reduction_kw"], 54.725, 1e-3)
        close("I degradation (CNY)", summary["degradation_cny"], 12_025.57, 0.05)
        close("I fixed opex (CNY)", summary["fixed_opex_cny"], 30_000.0, 0.01)
        check(summary["declaration_saving_cny"] + summary["storage_saving_cny"] == summary["net_saving_cny"], "I savings add up")
        check(summary["policy_fingerprint"] == "4a210e513c99", "I policy fingerprint")
        check(len(summary["months"]) == 12, "I twelve monthly bills")
        check((Path(tmp) / "bill_baseline.csv").exists(), "I baseline bill file")
        check((Path(tmp) / "bill_with_storage.csv").exists(), "I storage bill file")
        check((Path(tmp) / "basic_charge_compare.csv").exists(), "I basic-charge comparison file")
        check((Path(tmp) / "demand.csv").exists(), "I demand file")
        check((Path(tmp) / "review.md").exists(), "I review file")

    print("\nAll tariff and bill self-tests passed.")


if __name__ == "__main__":
    main()
