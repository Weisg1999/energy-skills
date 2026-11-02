"""Self-test for the carbon-asset reference implementation.

Run: python tools/selftest.py
The assertions encode the worked examples quoted in SKILL.md / SKILL_EN.md.
"""

from __future__ import annotations

from datetime import date

import calendar_tool
import ccer
import compliance
import finance
import pcf


def close(name, actual, expected, tol=1e-6):
    if abs(actual - expected) > tol:
        raise AssertionError(f"{name}: {actual} != {expected}")
    print(f"ok  {name:<34} {actual:,.4f}")


def main():
    activity = 10_000_000  # MWh
    allocation = compliance.free_allocation(activity, 0.80)
    close("free allocation (t)", allocation, 8_000_000, 1e-9)
    close("CCER cap at 5% (t)", compliance.ccer_limit(8_600_000), 430_000, 1e-9)

    position = compliance.compliance_position(
        allocation, verified_emissions=8_600_000, ccer_available=300_000
    )
    close("gap (t)", position["gap"], 600_000, 1e-9)
    close("CCER cap (t)", position["ccer_limit"], 430_000, 1e-9)
    close("CCER used (t)", position["ccer_used"], 300_000, 1e-9)
    close("CEA needed (t)", position["cea_needed"], 300_000, 1e-9)

    cost = compliance.compliance_cost(position, cea_price=95, ccer_price=86.51)
    close("purchase cost (CNY)", cost, 54_453_000, 1.0)
    penalty = compliance.non_compliance_penalty(300_000, 90, multiple=5)
    close("5x penalty (CNY)", penalty, 135_000_000, 1.0)

    if compliance.carryover_allowed(2024) or not compliance.carryover_allowed(2026):
        raise AssertionError("carry-over rule mapping is wrong")
    print("ok  carry-over rule                2024=no, 2026=yes")

    reduction = ccer.emission_reductions(160_000, 60_000)
    close("annual reductions (t)", reduction, 100_000, 1e-9)

    flows = ccer.project_cashflows(100_000, 85, 40_000_000, 3_000_000, 10)
    project_npv = ccer.npv(flows, 0.08)
    close("project NPV @8% (CNY)", project_npv, -3_094_552.31, 1.0)
    project_irr = ccer.irr(flows)
    close("project IRR", project_irr, 0.062528, 1e-6)
    break_even = ccer.break_even_price(100_000, 40_000_000, 3_000_000, 10, 0.08)
    close("break-even price (CNY/t)", break_even, 89.6118, 1e-3)

    sens = ccer.sensitivity(100_000, 85, 40_000_000, 3_000_000, 10, 0.08)
    close("NPV price -10% (CNY)", sens["price -10%"], -8_798_121.49, 1.0)
    close("NPV price +10% (CNY)", sens["price +10%"], 2_609_016.88, 1.0)

    loan = finance.pledge_value(100_000, 95, haircut=0.6)
    close("pledge value (CNY)", loan, 5_700_000, 1e-9)
    trigger = finance.margin_call_price(loan, 100_000, max_ltv=0.8)
    close("margin-call price (CNY/t)", trigger, 71.25, 1e-9)
    close("forward seller @70 (CNY)", finance.forward_payoff(100_000, 88, 70), 1_800_000, 1e-9)
    close("forward seller @95 (CNY)", finance.forward_payoff(100_000, 88, 95), -700_000, 1e-9)
    close("carbon-linked loan saving (CNY)", finance.carbon_linked_loan_savings(5_000_000, 0.002), 10_000, 1e-9)

    stages = {
        "raw_material": 8_200,
        "production": 2_100,
        "transport": 480,
        "use": 1_300,
        "end_of_life": 320,
    }
    grave = pcf.lifecycle_total(stages)
    close("PCF cradle-to-grave (kg)", grave, 12_400, 1e-9)
    close("PCF intensity (kg/kg)", pcf.intensity(grave, 1_000), 12.4, 1e-9)
    gate = pcf.lifecycle_total({k: stages[k] for k in ("raw_material", "production", "transport")})
    close("PCF cradle-to-gate (kg)", gate, 10_780, 1e-9)
    close("PCF raw-material share", pcf.stage_shares(stages)["raw_material"], 0.661290, 1e-6)
    co_products = pcf.allocate(grave, {"main": 60, "by_product": 40})
    close("allocated main product (kg)", co_products["main"], 7_440, 1e-9)
    residual = pcf.residual_after_reduction(grave, 0.20)
    close("residual after 20% cut (kg)", residual, 9_920, 1e-9)
    close("offset cost at 90 (CNY)", pcf.offset_cost(residual, 90), 892.8, 1e-9)

    bonus = compliance.allocation_with_certification_bonus(8_000_000)
    close("PCF certification bonus (t)", bonus, 40_000, 1e-9)
    close("bonus value at 95 (CNY)", bonus * 95, 3_800_000, 1e-9)
    close("bonus capped at 1pp (t)", compliance.allocation_with_certification_bonus(8_000_000, 0.012, 0.01), 80_000, 1e-9)

    events = calendar_tool.build_calendar(2026)
    if len(events) != 7:
        raise AssertionError("calendar should contain seven milestones")
    if events[0].day != date(2026, 1, 15) or events[-1].day != date(2027, 1, 31):
        raise AssertionError("calendar boundary dates are wrong")
    if any(events[i].day >= events[i + 1].day for i in range(len(events) - 1)):
        raise AssertionError("calendar milestones are not strictly ordered")
    ics = calendar_tool.to_ics(events)
    if ics.count("BEGIN:VEVENT") != 7 or not ics.startswith("BEGIN:VCALENDAR"):
        raise AssertionError("ICS export is malformed")
    if "\r\n" not in ics:
        raise AssertionError("ICS must use CRLF line endings")
    print("ok  compliance calendar             7 events, 2026-01-15 -> 2027-01-31")

    print("\ncarbon-asset-expert self-test passed (synthetic examples, not a market forecast)")


if __name__ == "__main__":
    main()
