"""Self-test for the storage-investment reference implementation.

Run: python tools/selftest.py
The assertions encode the worked examples quoted in SKILL.md / SKILL_EN.md.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import degradation
import finance
import stacking


def close(name, actual, expected, tol):
    if abs(actual - expected) > tol:
        raise AssertionError(f"{name}: {actual} != {expected}")
    print(f"ok  {name:<36} {actual:,.4f}")


def main():
    # Example A: 100 MW / 200 MWh independent storage, 2 h.
    a = stacking.arbitrage(
        power_mw=100,
        duration_h=2,
        rte=0.88,
        cycles_per_day=1,
        days=330,
        charge_price=250,
        discharge_price=850,
        usable_ratio=1.0,
        availability=1.0,
        degradation_cost_per_kwh=0.03,
    )
    close("A discharge per cycle (MWh)", a["discharge_mwh_per_cycle"], 187.6166, 1e-3)
    close("A charge per cycle (MWh)", a["charge_mwh_per_cycle"], 213.2007, 1e-3)
    close("A gross per cycle (CNY)", a["gross_per_cycle"], 106_173.9567, 1e-2)
    close("A annual net arbitrage (CNY)", a["annual_net"], 31_069_313.99, 1.0)
    close("A annual throughput (MWh)", a["annual_throughput_mwh"], 132_269.7244, 1e-2)

    cap = stacking.capacity_payment(100, 165, 2, 6)
    close("A capacity ratio", cap["ratio"], 1 / 3, 1e-9)
    close("A capacity payment (CNY)", cap["annual"], 5_500_000, 1e-6)
    close("A 4h capacity payment (CNY)", stacking.capacity_payment(100, 165, 4, 6)["annual"], 11_000_000, 1e-6)
    close("A 6h capacity payment (CNY)", stacking.capacity_payment(100, 165, 6, 6)["annual"], 16_500_000, 1e-6)

    revenue_a = a["annual_net"] + cap["annual"]
    close("A total revenue (CNY)", revenue_a, 36_569_313.99, 1.0)
    flows_a = finance.annual_cashflow(revenue_a, 5_000_000, 200_000_000, 15, 0.25, 15)
    close("A annual cash flow (CNY)", flows_a[1], 27_010_318.83, 1.0)
    close("A NPV @8% (CNY)", finance.npv(0.08, flows_a), 31_194_248.36, 5.0)
    close("A IRR", finance.irr(flows_a), 0.1047, 1e-4)
    close("A payback (years)", finance.payback(flows_a), 7.40, 0.01)

    annual_discharge = a["discharge_mwh_per_cycle"] * 330
    annual_charge_cost = a["charge_mwh_per_cycle"] * 330 * 250
    close("A LCOS incl. charging (CNY/MWh)", finance.lcos(200_000_000, 5_000_000, annual_charge_cost, annual_discharge, 15, 0.08), 742.2449, 1e-2)
    close("A LCOS excl. charging (CNY/MWh)", finance.lcos(200_000_000, 5_000_000, 0, annual_discharge, 15, 0.08), 458.1539, 1e-2)

    debt = 200_000_000 * 0.7
    payment = debt * 0.045 / (1 - 1.045 ** -10)
    close("A DSCR", finance.dscr(flows_a[1], payment), 1.527, 1e-3)

    # Example B: 5 MW / 10 MWh user-side, 90% usable, demand shaving.
    b = stacking.arbitrage(5, 2, 0.88, 1, 330, 350, 950, 0.9, 1.0, 0.03)
    close("B annual net arbitrage (CNY)", b["annual_net"], 1_360_126.76, 1.0)
    demand = stacking.demand_savings(10_000, 12_000, 10_000, 40)
    close("B bill before (CNY/month)", demand["before"]["monthly"], 520_000, 1e-6)
    close("B bill after (CNY/month)", demand["after"]["monthly"], 400_000, 1e-6)
    close("B demand saving (CNY/year)", demand["annual"], 1_440_000, 1e-6)
    close("B no shaving below setpoint (CNY/month)", stacking.demand_bill(10_000, 9_000, 40)["monthly"], 400_000, 1e-6)

    revenue_b = b["annual_net"] + demand["annual"]
    flows_b = finance.annual_cashflow(revenue_b, 300_000, 12_000_000, 10, 0.25, 10)
    close("B total revenue (CNY)", revenue_b, 2_800_126.76, 1.0)
    close("B NPV @8% (CNY)", finance.npv(0.08, flows_b), 2_595_064.98, 5.0)
    close("B IRR", finance.irr(flows_b), 0.1259, 1e-4)
    close("B payback (years)", finance.payback(flows_b), 5.52, 0.01)

    # Example C: 20 MW / 40 MWh co-located, 30 MWh curtailed charge per day.
    charge = 30.0
    discharge = charge * (0.88 ** 0.5)
    for price, expected_net, expected_irr, expected_payback in (
        (0, 4_716_794.05, 0.0498, 10.40),
        (150, 3_366_794.05, 0.0026, 14.69),
    ):
        gross_day = discharge * 600 - charge * price
        net = gross_day * 300 - (charge + discharge) * 300 * 1000 * 0.02
        close(f"C net at charge {price} (CNY)", net, expected_net, 1.0)
        flows_c = finance.annual_cashflow(net, 900_000, 36_000_000, 15, 0.25, 15)
        close(f"C IRR at charge {price}", finance.irr(flows_c), expected_irr, 1e-4)
        close(f"C payback at charge {price} (years)", finance.payback(flows_c), expected_payback, 0.01)

    # Frequency regulation is gross revenue and must not be added naively.
    fcas = stacking.frequency_regulation(10, 10, 1500, 6, 1.5, 330)
    close("FCAS daily gross (CNY)", fcas["daily"], 15_900, 1e-6)
    close("FCAS annual gross (CNY)", fcas["annual"], 5_247_000, 1e-6)

    close("A equivalent cycles", degradation.equivalent_cycles(61_913.49, 200, 0.95), 325.9, 0.1)
    close("years to 80% SOH", degradation.years_to_threshold(1.0, 0.015, 0.8), 13.33, 0.01)
    close("augmentation at 80% SOH (MWh)", degradation.augmentation_energy(200, 0.8), 50.0, 1e-9)

    # Instance K: Anhui standalone-storage capacity-price pack.
    pack_dir = (
        Path(__file__).resolve().parents[1]
        / "instances"
        / "anhui-storage-2027"
    )
    spec = importlib.util.spec_from_file_location("anhui_storage_instance", pack_dir / "run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    instance_path = pack_dir / "instance.json"
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    report = runner.validate_instance(config)
    assert report["ok"] and report["points_per_day"] == 96 and report["mtu_min"] == 15
    print(f"instance config ok={report['ok']} points={report['points_per_day']}")

    broken = json.loads(json.dumps(config))
    del broken["rules"]["capacity"]["grade"]
    try:
        runner.validate_instance(broken)
    except runner.ConfigError:
        pass
    else:
        raise AssertionError("a capacity rule block without grade must be rejected")

    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_instance(
            instance_path,
            pack_dir / "data" / "scenarios_demo.csv",
            pack_dir / "data" / "assessment_demo.csv",
            Path(tmp),
        )
        summary = result["summary"]
        base = summary["base_case"]
        close("K capacity gross (CNY)", base["capacity_gross_cny"], 11_000_000.0, 1e-6)
        close("K assessment deduction (CNY)", base["assessment_deduction_cny"], 46_768.71, 0.05)
        close("K capacity net (CNY)", base["capacity_net_cny"], 10_953_231.29, 0.05)
        assert base["strikes"] == 2 and base["strike_limit"] == 3 and not base["capacity_zeroed"]
        close("K 4h NPV @8% (CNY)", base["npv_cny"], 94_590_857.98, 5.0)
        close("K 4h IRR", base["irr"], 0.15865, 1e-5)
        close("K 4h payback (years)", base["payback_years"], 5.6109, 1e-3)
        close("K 4h LCOS (CNY/MWh)", base["lcos_cny_per_mwh"], 529.0618, 1e-2)
        ladder = {row["duration_h"]: row for row in summary["duration_ladder"]}
        close("K 2h capacity (CNY)", ladder[2.0]["capacity_gross_cny"], 5_500_000.0, 1e-6)
        close("K 6h capacity (CNY)", ladder[6.0]["capacity_gross_cny"], 16_500_000.0, 1e-6)
        close("K 2h ratio", ladder[2.0]["capacity_ratio"], 1 / 3, 1e-9)
        assert len(ladder) == 3
        assert summary["inputs"]["assessment_months"] == 12
        assert summary["scenario_metrics"]["cvar_cny"] <= summary["scenario_metrics"]["expected_annual_net_cny"]
        assert (Path(tmp) / "review.md").exists()
        assert (Path(tmp) / "duration_ladder.csv").exists()
        assert summary["policy_fingerprint"] == "1ea292c25eed"

    print("\nAll storage-investment self-tests passed.")


if __name__ == "__main__":
    main()
