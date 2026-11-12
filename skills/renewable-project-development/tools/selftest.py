"""Self-test for the renewable-project reference implementation.

Run: python skills/renewable-project-development/tools/selftest.py
The assertions encode the worked examples quoted in SKILL.md / SKILL_EN.md.
"""

from __future__ import annotations

import finance
import lcoe
import mechanism
import resource


def close(name, actual, expected, tol):
    if abs(actual - expected) > tol:
        raise AssertionError(f"{name}: {actual} != {expected}")
    print(f"ok  {name:<40} {actual:,.4f}")


def check(condition, name):
    if not condition:
        raise AssertionError(name)
    print(f"ok  {name}")


def main():
    # Resource screening.
    close("wind capacity factor (2,400 h)", resource.capacity_factor(2400), 0.273973, 1e-6)
    close("PV capacity factor (1,400 h)", resource.capacity_factor(1400), 0.159817, 1e-6)
    close("P90 from P50 2,400 h, CV 8%", resource.p90_from_p50(2400, 0.08), 2153.9328, 1e-3)
    close(
        "Weibull wind capacity factor",
        resource.wind_capacity_factor(7.0, 2.0, 3.0, 11.0, 25.0, 0.97),
        0.279237,
        1e-5,
    )
    close("PV specific yield (kWh/kWp)", resource.pv_specific_yield(1650, 0.82, 0.04), 1407.12, 1e-2)
    close("annual energy (MWh)", resource.annual_energy_mwh(100, 2400), 240000, 1e-6)

    # Example A: 100 MW onshore wind, 2,400 h, 3% curtailment.
    a = lcoe.lcoe(450_000_000, 11_000_000, 240_000, 20, 0.08, 0.005, 0.03)
    close("A LCOE (CNY/MWh)", a["lcoe"], 252.8013, 1e-3)
    close("A discounted cost (CNY)", a["discounted_cost"], 557_999_621.48, 1.0)
    close("A discounted energy (MWh)", a["discounted_energy_mwh"], 2_207_265.66, 0.01)

    # Example B: 100 MW PV, 1,400 h, 2% curtailment.
    b = lcoe.lcoe(300_000_000, 9_000_000, 140_000, 25, 0.08, 0.006, 0.02)
    close("B LCOE (CNY/MWh)", b["lcoe"], 283.9359, 1e-3)

    # Example C: 200 MW offshore wind, 3,200 h, 3% curtailment.
    c = lcoe.lcoe(2_200_000_000, 60_000_000, 640_000, 25, 0.08, 0.005, 0.03)
    close("C LCOE (CNY/MWh)", c["lcoe"], 446.4286, 1e-3)
    close(
        "C LCOE capex +20%",
        lcoe.lcoe(2_640_000_000, 60_000_000, 640_000, 25, 0.08, 0.005, 0.03)["lcoe"],
        515.5818,
        1e-3,
    )
    close(
        "C LCOE generation -10%",
        lcoe.lcoe(2_200_000_000, 60_000_000, 576_000, 25, 0.08, 0.005, 0.03)["lcoe"],
        496.0318,
        1e-3,
    )
    close(
        "C LCOE availability 90%",
        lcoe.lcoe(2_200_000_000, 60_000_000, 640_000 * 0.90 / 0.95, 25, 0.08, 0.005, 0.03)["lcoe"],
        471.2302,
        1e-3,
    )
    close(
        "C LCOE opex +30%",
        lcoe.lcoe(2_200_000_000, 78_000_000, 640_000, 25, 0.08, 0.005, 0.03)["lcoe"],
        476.6275,
        1e-3,
    )
    close(
        "C LCOE discount 10%",
        lcoe.lcoe(2_200_000_000, 60_000_000, 640_000, 25, 0.10, 0.005, 0.03)["lcoe"],
        505.3657,
        1e-3,
    )
    close(
        "C LCOE life 30y",
        lcoe.lcoe(2_200_000_000, 60_000_000, 640_000, 30, 0.08, 0.005, 0.03)["lcoe"],
        430.5198,
        1e-3,
    )
    close("C CfD top-up 1 TWh", (91.20 - 65.0) * 1.0, 26.2, 1e-9)
    close("C CfD clawback 1 TWh", (91.20 - 110.0) * 1.0, -18.8, 1e-9)
    close("C floating CfD top-up 0.5 TWh", (216.49 - 65.0) * 0.5, 75.745, 1e-9)
    close("C delay one year", 640_000 * c["lcoe"] / 1.10 / 1e8, 2.5974, 1e-3)
    check(
        lcoe.lcoe(2_640_000_000, 60_000_000, 640_000, 25, 0.08, 0.005, 0.03)["lcoe"]
        > c["lcoe"],
        "C capex sensitivity raises LCOE",
    )
    check(
        lcoe.lcoe(2_200_000_000, 60_000_000, 640_000, 30, 0.08, 0.005, 0.03)["lcoe"]
        < c["lcoe"],
        "C longer life lowers LCOE",
    )

    # Doc. 136 settlement for example A at a 70% coverage ratio.
    energy = 240_000 * 0.97
    low = mechanism.cfd_settlement(0.30, 0.25, 0.70 * energy, energy, 6.0)
    close("A coverage", low["coverage"], 0.70, 1e-9)
    close("A market revenue (CNY)", low["market_revenue"], 58_200_000, 1e-3)
    close("A mechanism top-up (CNY)", low["transfer"], 8_148_000, 1e-3)
    close("A certificate revenue (CNY)", low["certificate_revenue"], 1_396_800, 1e-3)
    close("A total revenue (CNY)", low["total_revenue"], 67_744_800, 1e-3)
    close("A effective energy price", low["effective_energy_price"], 0.285, 1e-9)
    close("A all-in price", low["all_in_price"], 0.291, 1e-9)

    high = mechanism.cfd_settlement(0.30, 0.35, 0.70 * energy, energy, 6.0)
    close("A high-price clawback (CNY)", high["transfer"], -8_148_000, 1e-3)
    close("A high-price total (CNY)", high["total_revenue"], 74_728_800, 1e-3)

    close("break-even mechanism price (pre-tax)", mechanism.break_even_mechanism_price(a["lcoe"], 250, 0.70, 6.0), 245.4304, 1e-3)
    close("capture price at 92%", mechanism.capture_price(0.25, 0.92), 0.23, 1e-9)

    # After-tax cash flow at the 0.30 mechanism price.
    flows = finance.project_cashflow(67_744_800, 11_000_000, 450_000_000, 20, 0.25, 20, 0.005)
    close("A year-1 cash flow (CNY)", flows[1], 48_183_600, 1e-3)
    close("A NPV @8% (CNY)", finance.npv(0.08, flows), 5_963_092.44, 1.0)
    close("A IRR", finance.irr(flows), 0.081811, 1e-5)
    close("A payback (years)", finance.payback(flows), 9.5526, 1e-3)

    # Same project at a 0.244 CNY/kWh mechanism price.
    low_price_revenue = 0.25 * energy * 1000 + (0.244 - 0.25) * 0.70 * energy * 1000 + 6.0 * energy
    low_flows = finance.project_cashflow(low_price_revenue, 11_000_000, 450_000_000, 20, 0.25, 20, 0.005)
    close("A low-price revenue (CNY)", low_price_revenue, 58_619_040, 1e-3)
    close("A low-price NPV @8% (CNY)", finance.npv(0.08, low_flows), -58_930_517.84, 1.0)
    close("A low-price IRR", finance.irr(low_flows), 0.061527, 1e-5)
    close("A low-price payback (years)", finance.payback(low_flows), 11.1842, 1e-3)

    # After-tax break-even mechanism price at an 8% hurdle.
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        revenue = 0.25 * energy * 1000 + (mid - 0.25) * 0.70 * energy * 1000 + 6.0 * energy
        trial = finance.project_cashflow(revenue, 11_000_000, 450_000_000, 20, 0.25, 20, 0.005)
        if finance.npv(0.08, trial) > 0.0:
            hi = mid
        else:
            lo = mid
    close("after-tax 8% break-even price", (lo + hi) / 2.0, 0.294854, 1e-5)

    # Debt service and DSCR in year 1.
    principal = 450_000_000 * 0.70
    payment = finance.debt_payment(principal, 0.045, 15)
    close("debt principal (CNY)", principal, 315_000_000, 1e-3)
    close("annual debt service (CNY)", payment, 29_330_849.56, 1e-2)
    interest = principal * 0.045
    taxable = max(67_744_800 - 11_000_000 - 22_500_000 - interest, 0.0)
    cfads = 67_744_800 - 11_000_000 - taxable * 0.25
    close("year-1 CFADS (CNY)", cfads, 51_727_350, 1e-3)
    close("year-1 DSCR", finance.dscr(cfads, payment), 1.7636, 1e-3)

    # LCOE sensitivities for example A.
    close("A LCOE capex +10%", lcoe.lcoe(495_000_000, 11_000_000, 240_000, 20, 0.08, 0.005, 0.03)["lcoe"], 273.1885, 1e-3)
    close("A LCOE generation -10%", lcoe.lcoe(450_000_000, 11_000_000, 216_000, 20, 0.08, 0.005, 0.03)["lcoe"], 280.8903, 1e-3)
    close("A LCOE opex +20%", lcoe.lcoe(450_000_000, 13_200_000, 240_000, 20, 0.08, 0.005, 0.03)["lcoe"], 262.5871, 1e-3)

    print("\nAll renewable-project self-tests passed.")


if __name__ == "__main__":
    main()
