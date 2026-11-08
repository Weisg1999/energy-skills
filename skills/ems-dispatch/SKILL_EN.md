---
name: ems-dispatch
description: Microgrid and storage EMS dispatch expert — turns "how should the battery charge and discharge tomorrow" into a deliverable 96-interval plan covering SOC and reserve, point-of-connection limits, demand charges, degradation cost, multi-market products, MPC rolling and uncertainty. Answers whether a plan is deliverable, why the battery moves the way it does, whether reserve is sufficient and whether charging will raise demand. Includes a zero-dependency Python reference implementation.
---

# Microgrid & Storage EMS Dispatch Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) ｜ Sister skills: [Storage Investment & Operations](../storage-investment-operations/SKILL_EN.md) (appraisal / revenue stacking / LCOS), [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation / demand response), [Spot-Bidding Quant Expert](../spot-bidding-quant/SKILL_EN.md) (price forecasting / bidding), [Electricity Trading Expert](../electricity-trading-expert/SKILL_EN.md) (rules / settlement). This skill answers only "given prices, load, equipment and rules, how should tomorrow's power and SOC plan be arranged, and can it be delivered".

> Version v1.7 · data cutoff 2026-11-01

> **Maintenance entry points**: `tools/selftest.py` (green means the worked examples still hold), [storage EMS note](../../knowledge/储能EMS优化调度-算法与工程-2026-11.md) (model, constraints, capacity price and frequency-regulation details), [microgrid EMS note](../../knowledge/微网EMS优化调度-算法与工程-2026-11.md) (PCC, islanding, MPC and capability assessment).
> **Open items 2026-2027**: provincial rules and assessment deductions under Document 114, the denominator duration for the capacity price (4/6/8/10 h), the shape of time-of-use prices under continuous spot operation, revision of ancillary-service products and compensation, and upgrades to grid-forming and grid-connection standards.

---

## 0. Role and Conduct

### 0.1 Role

You are the dispatch algorithm lead for storage and microgrid EMS, serving plant operators, behind-the-meter owners, park energy companies, integrators and trading agents. The deliverable is not "storage is flexible" but a **plan that can be dispatched, reconciled and explained**: given 96-interval prices, load, PV, equipment capability and market rules, produce per-interval charge/discharge power and an SOC trajectory; given a plan, judge whether it satisfies the point-of-connection, BMS/PCS, reserve and safety constraints, which intervals earn the money, and where settlement may deduct.

### 0.2 Conduct rules (mandatory)

1. **Fix the boundary before optimizing**: point-of-connection power and export blocking, BMS/PCS limits, SOC window, reserve requirement, market bid caps, safety interlocks. Without all six, any "optimal plan" may be undeliverable.
2. **Four hard boundaries outrank revenue**: grid connection and PCC, AGC/AVC and primary frequency-response capability, capacity-price eligibility, BMS and safety limits. Revenue does not justify exceeding them.
3. **State the calibres**: kW/kWh or MW/MWh; usable DC energy or AC charge/discharge energy; whether buy price, sell price and agency fees are tax-inclusive; SOC as a percentage or as energy. **Usable DC energy is not AC discharge energy — they differ by one factor of eta.**
4. **Numbers must be reproducible**: every worked example must be regenerable from `tools/`; when the calibre changes, recompute rather than scaling old numbers.
5. **The plan must be deliverable**: return a feasible solution on timeout, diagnose infeasibility, roll back the previous plan on numerical failure. Never "hand-adjust" when the optimizer fails.
6. **Keep revenue and investment separate**: this skill computes daily operating cost and net revenue; IRR, LCOS, DSCR and capacity-lease pricing belong to the storage investment skill. A daily dispatch model must not sign an investment decision.
7. **Source grading**: A = laws / standards / market-rule source text; B = exchange disclosures, industry statistics, tender and award notices; C = media / research / vendor claims; D = this skill's synthetic examples built from public parameters. Vendor claims such as "92% efficiency" or "12,000 cycles" are grade C and only used as an upper sensitivity bound.
8. **Do not present "optimal" as "correct"**: optimal means optimal for the given objective and constraints. If demand charge, degradation or assessment is missing from the objective, the optimum is wrong. Check that the objective is isomorphic to the settlement statement first.

### 0.3 Knowledge map (question → chapter)

| Question | Go to |
|---|---|
| How should the battery charge and discharge tomorrow, and why this shape | Ch. 3, Sec. 8.5 |
| Is this plan deliverable | Ch. 4, Sec. 9.1 |
| Is reserve sufficient, can it be awarded | Sec. 4.6, 5.1 |
| Will charging raise the demand charge | Sec. 7.2 |
| How much capacity price can be earned, how is duration converted | Sec. 4.3 |
| Does frequency regulation or reserve crowd out arbitrage | Ch. 5 |
| What if forecasts are wrong, should we roll | Ch. 6 |
| How does degradation enter the model, how many tiers | Sec. 7.1 |
| How are available power, energy and duration computed | Sec. 4.5 |
| How long can the microgrid island | Sec. 6.5, microgrid note §4.11 |
| The plan does not reconcile with settlement | Sec. 7.4 |
| How to use the tools, how to reproduce the examples | Ch. 8, 10, 12 |

---

## 1. Boundary and Ownership

### 1.1 Decision record: why a standalone seventh skill

EMS dispatch is **not merged into the virtual power plant skill**, for four reasons:

| Reason | Explanation |
|---|---|
| Different object | The VPP skill covers which resources to aggregate, how to participate in markets and how to share revenue; EMS covers how to schedule power interval by interval for given resources and prices |
| Different method | VPP is mostly rules, eligibility and business models; EMS is mostly optimization models, constraints and numerical stability |
| Existing division | The storage investment skill explicitly delegates dispatch algorithms to the notes; the VPP skill §6.4 only sketches the technology stack, with no model or tool |
| Verifiability | A standalone skill can carry a zero-dependency kernel and self-test that lock the numbers in both notes; folding it into VPP would entangle market rules with dispatch algorithms |

The "future SKILL chapter draft" reserved in §11.5 of the notes was designed as a standalone skill; this skill is its implementation.

### 1.2 Division of labour with sister skills

| Question | Owner |
|---|---|
| Is this project worth investing in, LCOS/IRR/DSCR, capacity-lease pricing | Storage Investment & Operations |
| Which resources to aggregate, how to organize demand response, VPP revenue sharing | Virtual Power Plant Expert |
| How to forecast prices/load, how to build bid curves, how to backtest strategies | Spot-Bidding Quant Expert |
| Source text for spot/medium-term/ancillary rules, settlement items | Electricity Trading Expert |
| Carbon compliance, CCER, CBAM | Carbon Asset Management Expert |
| **Given prices and equipment, how to schedule 96 intervals of power and SOC, and whether it is deliverable** | **This skill** |

**Interface contract**: this skill receives price forecasts (point forecasts plus quantiles) from the bidding skill and equipment parameters plus revenue calibres from the investment skill, and exports bid-cap curves and planned energy to the trading skill. Field list in §3.1.

### 1.3 Applicable and not applicable

| Applicable | Not applicable |
|---|---|
| Day-ahead/intraday economic dispatch of grid-side independent storage | Full-network security-constrained dispatch (AC/DC power flow) |
| Peak-valley arbitrage and demand-charge management for behind-the-meter storage | Millisecond protection settings and electromagnetic transients |
| Curtailment absorption and plan tracking for renewable co-located storage | Cell chemistry selection and thermal-runaway propagation |
| Microgrid grid-connected/islanded switching, island energy checks | Fire-system design and suppression effectiveness |
| Multi-product capacity allocation for frequency regulation, reserve and ramping | Medium/long-term contract decomposition and financial settlement |
| Multi-station aggregation capacity allocation and PCC checks | Spot bidding strategy and bid-curve optimization |

### 1.4 Four hard boundaries (before revenue)

| Boundary | Consequence of violation | Model location |
|---|---|---|
| PCC power and export blocking | Trip, assessment, reverse-flow charges | Import/export variables + mutual exclusion |
| AGC/AVC and primary frequency response | Awarded capacity cannot be delivered, assessment deduction | Power/energy margin, ramping and response time |
| Capacity-price eligibility | Outside the list no payment; low availability reduces payment | List capacity, availability, duration conversion |
| BMS/PCS and safety interlocks | Equipment damage, safety incident | Derating limits, no charge/discharge on alarm |

**The order cannot be reversed**: stay inside the boundaries first, then maximize revenue. Writing safety constraints as penalties lets the optimizer buy output with fines.

---

## 2. Unified Model

> The full model, 18 constraints and scale analysis are in [storage EMS note §3](../../knowledge/储能EMS优化调度-算法与工程-2026-11.md). This section gives only the skeleton needed to answer dispatch questions.

### 2.1 Indices and units

| Symbol | Meaning | Unit |
|---|---|---|
| t ∈ T | Interval, Δt = 0.25 h (96 points) or 1 h (24 points) | h |
| s ∈ S | Storage station/unit | — |
| r ∈ R | Market product: energy, regulation, reserve, ramping | — |
| P_ch_max, P_dis_max | Maximum charge/discharge power | kW or MW |
| E_cap | Rated energy | kWh or MWh |
| SOC_min, SOC_max | SOC operating window | p.u. |
| η_ch, η_dis | Charge/discharge efficiency | p.u. |
| c_buy, c_sell | Buy/sell price | CNY/kWh or CNY/MWh |
| c_deg | Degradation cost per kWh throughput | CNY/kWh |
| D | Billed demand | kW |

**Unit discipline**: the kernel uses kW, kWh and CNY/kWh; the station wrapper uses MW, MWh and CNY/MWh. Conversion happens only in the wrapper; units are never mixed inside the model.

### 2.2 Objective (minimize net cost)

```
min  Σ_t [ c_buy(t)·p_imp(t)·Δt − c_sell(t)·p_exp(t)·Δt ]
   + c_dem·D
   + c_deg·Σ_t (p_ch(t) + p_dis(t))·Δt
   + c_curt·Σ_t pv_curt(t)·Δt
   − Σ_r [ c_cap[r]·r[r,t]·Δt + c_mil[r]·m[r,t]·K_r ]
   − daily capacity payment
   + assessment penalties and terminal SOC value
```

**The objective must be isomorphic to the settlement statement**: every item in settlement appears in the model; items in the model but not in settlement are internal shadow prices only and never promised externally. The three most common omissions are demand charge, degradation cost and auxiliary power consumption.

### 2.3 Core constraints (must be explainable)

| No. | Constraint | One line |
|---|---|---|
| S1 | PCC balance | `p_imp − p_exp = load + p_ch − p_dis − pv_used` |
| S2 | SOC recursion | `E[t] = (1−σ)·E[t−1] + η_ch·p_ch·Δt − p_dis·Δt/η_dis` |
| S3 | SOC bounds and terminal | Inside the window + daily cycle or terminal value |
| S4 | Charge/discharge exclusion | `p_ch ≤ P_ch·u_ch`, `p_dis ≤ P_dis·u_dis`, `u_ch+u_dis ≤ 1` |
| S5 | Import/export exclusion | Net-load sign decides import or export, never both |
| S6 | Ramping | Power change between adjacent intervals is limited |
| S7 | Reserve power margin | `p_dis + Σr_up ≤ P_dis·a[t]`, same on the charge side |
| S8 | Reserve energy margin | Up-reserve limited by `E − SOC_min·E_cap`, down-reserve by headroom |

### 2.4 Why MILP, not LP

| Symptom | Error after linear relaxation | Required element |
|---|---|---|
| Simultaneous charge and discharge | Inflated arbitrage, understated degradation | 0-1 exclusion |
| Simultaneous import and export | Fake arbitrage under negative spreads | Import/export variables + exclusion |
| Winning every product | The same capacity sold twice | Product choice coupled to capacity |
| Outage or maintenance | Unavailable intervals still scheduled | Availability parameter |
| Degradation tiers | The cheapest tier used without limit | Piecewise linear or SOS2 |

### 2.5 Scale and the real bottleneck

| Case | Intervals | Binary variables | Solve characteristics |
|---|---|---|---|
| Single station, 96 points | 96 | Hundreds | Seconds |
| Single station, 96 points, multi-product | 96 | Thousands | Seconds to minutes |
| 10-station aggregation | 960 | Tens of thousands | Minutes |
| 100 stations + scenarios | 9,600×Ω | Hundreds of thousands | Decomposition or scenario reduction |

Scale is not the main bottleneck. **Data quality, calibre consistency and fallback strategy** are: one wrong initial SOC or one misaligned metering point is enough to turn an "optimal" plan into a settlement dispute.

---

## 3. Day-Ahead Dispatch Recipe (seven steps)

### 3.1 Input data contract

| Field | Requirement | Common problem |
|---|---|---|
| Prices | 96 points, time-stamped, separate buy/sell, with network-tariff calibre | Using a catalogue tariff instead of settlement price; valuing sell at the buy price |
| Load | 96-point measured or forecast, aligned to the metering point | Mixing gateway meter and internal measurements |
| PV/wind | 96-point forecast plus available capacity | Treating installed capacity as output |
| Equipment | PCS, BMS, SOC window, eta, auxiliary power, SOH/temperature derating | Using rated values instead of available values |
| Market | Bid caps, reserve requirement, regulation capacity, assessment rules | Ignoring non-anticipativity |
| Constraints | PCC import/export limits, export blocking, maintenance plan | Confusing a physical limit with a demand threshold |

### 3.2 Seven steps

1. **Set boundaries**: PCC, SOC window, power limits, reserve, maintenance, safety interlocks;
2. **Compute the baseline**: purchase cost, peak and curtailment without storage or without optimization, as the incremental benchmark;
3. **Check the feasible region**: use the capability assessment in §4.5 to test whether the target is reachable; if not, change the boundary before optimizing;
4. **Solve**: MILP or an equivalent dynamic program; objective isomorphic to settlement;
5. **Validate by back-substitution**: interval power balance, SOC conservation, PCC not exceeded, no simultaneous charge/discharge;
6. **Check deliverability**: reserve power and energy both satisfied, frequency-regulation recovery margin reserved;
7. **Publish and archive**: plan, version, input snapshot, solver status and objective value stored together.

### 3.3 Minimum output set

| Field | Purpose |
|---|---|
| `p_charge` / `p_discharge` | Dispatch and settlement |
| `p_import` / `p_export` | PCC validation |
| `soc` (including terminal) | Cross-day continuity and assessment |
| `reserve_up` / `reserve_dn` | Ancillary-service bidding |
| `throughput` / `equivalent_cycles` | Degradation and warranty |
| `peak_import` | Demand bill |
| `curtailed` | Curtailment statistics |
| `feasible` / `reason` | Fallback and alarms |

### 3.4 How to read a plan

Given a 96-interval plan, ask five questions first: **where does the energy come from, where is it sold, when does SOC touch a bound, when does the peak occur, and when is reserve insufficient**. Take the microgrid example in §8.5: charging in the valley 00:00–02:00, discharging at the midday peak 10:00–13:00, a second charge in the flat period 15:00–17:00, and discharging at the evening spike 21:00–23:00. The two cycles come from the price curve, not from a solver glitch; the small discharge at 18:00–20:00 only holds purchase below the demand threshold.

---

## 4. Hard Boundaries and Capability

### 4.1 PCC and export blocking

- Import and export must be two non-negative variables with mutual exclusion, not one signed net-power variable: otherwise a negative spread produces fake simultaneous import and export.
- When a behind-the-meter site or co-located plant cannot export, set `p_exp_max = 0`; surplus PV can only be curtailed. Whether curtailment is penalized follows the contract and rules, never assume it is free.
- Separate the physical service from the billing threshold: 900 kW may be the service capacity while 840 kW is the 105% demand line. Merging them into one "PCC limit" makes the bill impossible to explain.

### 4.2 BMS/PCS and derating

```
P_available = min(P_PCS, P_BMS, P_PCC) × derate × SOH
E_available = (SOC_max − SOC_min) × E_rated × SOH
duration    = E_available / P_available
```

Temperature and SOH are slow variables, updated daily or hourly; never re-optimize an electrochemical model inside a 15-minute interval. EMS commands must pass BMS/PCS limit checks before dispatch.

### 4.3 Capacity-price eligibility

```
compensated capacity = min(listed capacity, available capacity) × duration factor × availability
duration factor = min(full-power discharge duration ÷ provincial denominator, 1)
```

Document 114 (NDRC price〔2026〕No. 114) gives the framework; provincial rules give the denominator and assessment threshold. **No payment outside the list**; availability is measured over the assessment period; common denominators are 4/6/8/10 h. The ratio is capped at 1, so a 2-hour system cannot earn the full 1.0.

### 4.4 Safety interlocks

When the alarm level reaches its threshold, `p_ch = p_dis = 0`; temperature, pressure-difference or insulation violations isolate the unit and block grid connection. This is a hard constraint, not a penalty; never let the optimizer "pay a fine" to keep producing.

### 4.5 Capability: power, energy, duration

Example: 500 kW / 1000 kWh, BMS 480 kW, PCC 450 kW, derate 0.95, SOH 0.98, SOC 20%–95%:

| Metric | Calculation | Result |
|---|---|---|
| Available power | min(500, 480, 450) × 0.95 × 0.98 | 418.95 kW |
| Available energy | 0.75 × 1000 × 0.98 | 735.00 kWh |
| Duration | 735.00 / 418.95 | 1.7544 h |

**A bid may not exceed available capability**, and must leave margin for reserve and assessment. The binding limit is often not the PCS but the PCC or BMS.

### 4.6 Four dimensions of reserve and deliverability

| Dimension | Meaning | Model location |
|---|---|---|
| Capacity | How much power can be added or reduced | `r_up` / `r_dn` caps |
| Rate | How fast it can be reached | Ramping and response time |
| Duration | How long it can be sustained | Energy constraint `r·τ ≤ available energy` |
| Energy | Whether SOC margin suffices | SOC headroom in each direction |

**Enough power does not mean deliverable reserve**. In the §8.5 microgrid example, the 50 kW × 1 h power margin is not tight (maximum discharge 441.8 kW < 450 kW), but the energy margin is **−52.63 kWh**: with SOC at the 20% floor there is no 52.63 kWh to give. Making reserve reliable needs an SOC floor near 25.3%, which raises the daily cost from 6,525.12 to 6,663.52 CNY and cuts throughput from 3,086.56 to 2,625.45 kWh.

---

## 5. Multi-Product Stacking

### 5.1 Four revenue classes and resource occupancy

| Product | Revenue basis | Occupies | Main constraint |
|---|---|---|---|
| Energy arbitrage | Spread × energy | Power + energy + cycling | SOC window, cycle budget |
| Frequency regulation | Capacity price + mileage × K | Power + bidirectional SOC margin | Energy neutrality, recovery band |
| Reserve / ramping | Capacity price | Power + sustained energy | Up/down energy margin |
| Capacity payment | CNY/kW·yr × factor | Available capacity | List, availability, denominator |

### 5.2 Stacking order and opportunity cost

Satisfy eligibility-type revenue first (capacity-price availability, lease obligations), then energy arbitrage, then use the remainder for regulation/reserve. **Reversing the order trades eligibility for small change**: chasing mileage revenue until availability falls below the threshold wipes out the entire capacity payment.

Every product carries an opportunity cost: 10 MW of regulation occupies power and SOC margin, so arbitrage energy falls. Reporting "regulation gross revenue 15,900 CNY/day" without the arbitrage it displaced is double counting.

### 5.3 K factor and energy neutrality

- Frequency regulation is a bidirectional, zero-mean service, but real deployment has random deviation; reserve recovery energy so the unit returns to its baseline band by the end of the assessment period;
- The K factor converts mileage into effective regulation; a falling K directly cuts revenue, so never use the rated K for long-term projections;
- Capacity and mileage are priced in different units (CNY/MW·h versus CNY/MW); an order-of-magnitude conversion error is common.

### 5.4 No double selling

The same power, energy and SOC margin cannot be sold twice. Run a three-dimensional occupancy check on power, energy and time before stacking; the external revenue table must list products separately, never merge them into one "combined revenue" that hides the occupancy.

---

## 6. MPC and Uncertainty

### 6.1 Two time scales

| Loop | Time scale | Inputs | Outputs |
|---|---|---|---|
| Day-ahead | 96 × 15 min | Day-ahead prices, load/renewable forecasts | Bid curves, SOC plan |
| Intraday rolling | 15 min–1 h rolling | Latest observations and forecasts | Corrected power setpoints |
| Real time | Seconds–minutes | Measured deviation, AGC command | Tracking and clipping |

### 6.2 MPC form

Execute only the first step of each rolling window and re-solve with new observations next period. Three horizons must match: forecast horizon, control horizon and settlement horizon. If the control horizon is shorter than the settlement horizon, the result is locally optimal and worse for the day.

### 6.3 Four ways to handle uncertainty

| Method | Approach | When to use | Cost |
|---|---|---|---|
| Deterministic + reserve | Point forecast plus power/energy margin | Accurate forecasts, simple rules | Conservative, slightly lower revenue |
| Two-stage stochastic | Scenario tree + second-stage recourse | Price/renewable distributions estimable | Scenario explosion |
| CVaR | Penalize tail loss in the objective | Risk aversion | Confidence level must be calibrated |
| Robust | Optimize the worst case inside an uncertainty set | Extreme weather, rule shocks | Overly conservative |

**Start with deterministic + reserve, then consider stochastic or robust**: for most projects the forecast error is not yet large enough to justify scenario optimization, and getting reserve energy right is worth more.

### 6.4 Non-anticipativity

The day-ahead plan may use only day-ahead information; intraday rolling may use only observations available at decision time. **Non-anticipativity is a data-pipeline problem, not a solver problem**: leaking future measurements into features produces beautiful but unreproducible backtests.

### 6.5 Fallback ladder and islanding

Timeout → return the best feasible solution so far; infeasible → output a conflicting-constraint diagnosis (SOC, PCC, reserve, power); numerical failure → roll back the previous plan and alarm. For islanding, check energy first:

```
island energy need = Σ load × Δt
available energy  = (SOC − SOC_min) × E_rated × SOH
feasible if: available energy ≥ need × (1 + reserve ratio)
```

Enough energy is only necessary; also check maximum power, ramping and the black-start sequence (microgrid note §4.11).

---

## 7. Degradation, Demand Charges and Calibres

### 7.1 Three tiers of degradation modelling

| Tier | Model | Cost | Use |
|---|---|---|---|
| 1 | Linear throughput: `c_deg·Σ(p_ch+p_dis)·Δt` | Low | Day-ahead economic dispatch |
| 2 | Equivalent cycles: DoD-weighted tiers or rainflow counting | Medium | Weekly/monthly planning, life assessment |
| 3 | Electrochemical-thermal coupling | High | R&D, warranty disputes |

Engineering advice: tier 1 for day-ahead, tier 2 for monthly review. **Never replace throughput and depth with a single cycle count**, or high-SOC float and shallow cycling will be underestimated.

### 7.2 Demand charge and the charging window

Billed demand takes the maximum purchase power; export does not offset it; the portion above 105% of the contracted value is usually billed at double. Example at 40 CNY/kW·month, 800 kW contracted, 840 kW threshold:

| Case | Maximum purchase | Billed demand | Monthly basic charge (CNY) |
|---|---|---|---|
| No storage | 878.54 kW (38.54 kW above threshold) | 800 + 2 × 38.54 = 877.07 | 35,082.99 |
| Storage, 840 kW cap | 838.50 kW | 800 | 32,000.00 |
| Monthly saving | — | — | 3,082.99 (about 102.77 CNY/day) |

**Charging raises demand**: with 400 kW valley load, charging at full 500 kW makes purchase 900 kW, `over = 60 kW`, and the basic charge becomes 36,800 CNY/month — 1,717.01 CNY/month more than without storage. Hence the valley charging cap:

```
p_ch ≤ 1.05·D_set − P_load_valley   (here 840 − 400 = 440 kW)
```

Demand and arbitrage must be solved in one model; fixing charging power after an energy-only optimum pushes the charging window into more expensive intervals.

### 7.3 DC and AC calibres

| Calibre | Definition | Common error |
|---|---|---|
| Rated energy | Nameplate kWh/MWh | Treating it as usable energy |
| Usable DC energy | (SOC_max − SOC_min) × rated × SOH | Treating it as discharge energy |
| AC discharge energy | Usable DC energy × η_dis | Missing one factor of eta |
| AC charge energy | Usable DC energy ÷ η_ch | Missing one factor of eta |

For 100 MW / 200 MWh, SOC 10%–90%, RTE 88%: usable DC 160 MWh, AC discharge 150.09 MWh, AC charge 170.56 MWh. Treating 160 MWh directly as discharge overstates revenue by about 6%.

### 7.4 Settlement and metering reconciliation

- Map the gateway meter, internal measurements and storage PCS explicitly;
- Prices, energy and intervals must share the same source and timestamp; handle time zones and daylight saving explicitly;
- Ancillary settlement follows the assessment period, not the energy period; monthly settlement must separate them;
- Keep planned, actual and settled values side by side and attribute each difference (forecast error, curtailment, equipment derating, manual intervention).

---

## 8. Tools and Worked Examples

### 8.1 Tool structure (standard library only, zero dependencies)

| File | Content |
|---|---|
| `tools/dispatch.py` | Single-battery kernel: SOC-grid dynamic programming, PCC, curtailment, reserve, degradation, terminal SOC |
| `tools/storage.py` | Station wrapper: MW/MWh conversion, single-cycle arbitrage, curtailment charging, capability |
| `tools/microgrid.py` | Microgrid wrapper: PV, PCC, baseline, island energy checks |
| `tools/market.py` | Capacity payment, regulation capacity + mileage, demand bill |
| `tools/curves.py` | Synthetic curves: station 24-point, microgrid 96-point, behind-the-meter 96-point |
| `tools/selftest.py` | Assertions that lock every worked example in the text |

The kernel runs forward dynamic programming on an SOC grid, excludes simultaneous charge/discharge by construction, splits import/export on the sign of net load, and curtails PV beyond the export limit. It is a **screening tool**, not a settlement system.

### 8.2 Storage station: 100 MW / 200 MWh

| Parameter | Value |
|---|---|
| Rated power/energy | 100 MW / 200 MWh |
| SOC window | 10%–90%, 160 MWh usable DC |
| System RTE | 88% (eta = 0.938083) |
| Prices | Valley 200, flat 450, peak 900 CNY/MWh (24 points) |
| Degradation | 0.03 CNY/kWh |
| Capacity payment | 165 CNY/kW·yr, duration factor 2/6 |

| Item | Calculation | Result |
|---|---|---|
| Discharge (AC) | 160 × 0.938083 | 150.09 MWh |
| Charge (AC) | 160 / 0.938083 | 170.56 MWh |
| Gross arbitrage | 150.09 × 900 − 170.56 × 200 | 100,971.86 CNY/day |
| Degradation cost | 0.03 × 320.65 MWh | 9,619.62 |
| Net energy revenue | — | 91,352.24 |
| Capacity payment | 165 × 100,000 × 2/6 ÷ 365 | 15,068.49 |
| Total | — | 106,420.74 |
| Auxiliary power 0.3 MW | 0.3 × 24 × 400 | −2,880.00, total 103,540.74 |

The dispatch kernel reproduces the analytic charge/discharge within ±0.01 MWh. At RTE 85% net revenue is 88,420.85 CNY/day; with a 4/6 duration factor the capacity payment is 30,136.99 CNY/day; at 95% availability it is 14,315.07 CNY/day; 10 MW of regulation plus 1,500 MW mileage at K = 1.5 gives 15,900 CNY/day gross.

### 8.3 Behind-the-meter: 5 MW / 10 MWh plus demand

| Parameter | Value |
|---|---|
| Storage | 5 MW / 10 MWh, SOC 10%–90%, 8 MWh usable DC |
| System RTE | 88% (eta = 0.938083) |
| Time-of-use prices | Valley 350, flat 700, peak 1,050 CNY/MWh |
| Demand | 40 CNY/kW·month, contracted 10,000 kW |
| Charge/discharge power | 4 MW (one charge, one discharge) |

| Item | Calculation | Result (CNY/day) |
|---|---|---|
| Charge cost | 8.5280 MWh × 350 | 2,984.81 |
| Discharge revenue | 7.5047 MWh × 1,050 | 7,879.90 |
| Gross spread | — | 4,895.09 |
| Degradation cost | 0.03 × 16.0327 MWh | 480.98 |
| Net spread | — | 4,414.11 |
| Demand saving | 520,000 → 400,000 CNY/month | 120,000/month, 4,000/day |
| Total | — | 8,414.11 |

Charging takes about 2.13 h and discharging about 1.88 h at 4 MW. **Demand contributes nearly half**, so judging by the spread alone understates behind-the-meter revenue; conversely, if charging raises demand, the basic charge eats the spread.

### 8.4 Renewable co-located: charging from curtailment

| Parameter | Value |
|---|---|
| Wind / co-located storage | 100 MW; 20 MW / 40 MWh, 32 MWh usable DC |
| System RTE | 88% (eta = 0.938083) |
| Night-time curtailed energy | 30 MWh/day |
| Morning-peak price | 600 CNY/MWh |
| Degradation | 0.03 CNY/kWh |

| Item | Calculation | Result |
|---|---|---|
| Stored DC energy | 30 × 0.938083 | 28.14 MWh ≤ 32 MWh |
| AC discharge | 28.14 × 0.938083 | 26.40 MWh |
| Discharge revenue | 26.40 × 600 | 15,840 CNY/day |
| Degradation | 0.03 × 56.40 MWh | 1,692 |
| Net (zero-cost charge) | — | 14,148 |
| Net (charging at 150 CNY/MWh) | less 30 × 150 | 9,648 |

Whether the marginal cost of curtailed energy is zero or 150 CNY/MWh depends on the settlement calibre (whether it enters exported energy, whether curtailment is compensated); the two calibres differ by 4,500 CNY/day and must match the contract and settlement statement. When curtailment exceeds usable DC energy, the surplus cannot be absorbed — a direct consequence of duration selection.

### 8.5 Microgrid: 96 points, PV, demand, reserve

| Parameter | Value |
|---|---|
| Intervals | 96 × 15 min |
| PV | 500 kW peak, output 06–18 h |
| Storage | 1000 kWh / 500 kW, eta = 0.95, SOC 20%–95% |
| Service | 900 kW; purchase cap 840 kW (105% demand line) |
| Reserve | 50 kW up, 1 h (base case constrains power only) |
| Load | Double peak, baseline peak 878.54 kW |

| Metric | No storage | With storage | Change |
|---|---|---|---|
| Daily purchase cost | 7,408.72 CNY | 6,525.12 CNY | −883.59 CNY (−11.93%) |
| Maximum purchase | 878.54 kW | 838.50 kW | −40.04 kW |
| Daily purchased energy | 9,816.03 kWh | 9,974.21 kWh | +158.18 kWh (round-trip loss) |
| Daily throughput | — | 3,086.56 kWh | equivalent 1.5433 cycles |
| Curtailment | 0 | 0 | PV always below load |

Plan shape: valley charge 00:00–02:00 (about 426 kW), midday discharge 10:00–13:00 (maximum 427.5 kW), second charge in the flat period 15:00–17:00 (about 490 kW), small discharge 18:00–20:00 to hold demand, spike discharge 21:00–23:00 (about 441.8 kW). **Purchased energy rises while cost falls**: the extra 158.18 kWh all covers the round-trip loss (0.9025).

### 8.6 Sensitivities (re-solved on the same kernel)

| Change | Daily cost (CNY) | Daily saving (CNY) | Note |
|---|---|---|---|
| Base | 6,525.12 | 883.59 | Throughput 3,086.56 kWh |
| Degradation 0.03 CNY/kWh | 6,617.72 | 791.00 | Degradation cost 92.60, plan unchanged |
| Storage +20% | 6,350.61 | 1,058.10 | 1.5358 cycles, diminishing returns |
| Purchase cap 900 kW | 6,519.97 | 888.75 | Peak rises to 889.47 kW |
| PV +20% with export allowed | 5,996.19 | 857.19 | Baseline 6,853.38 |
| Reserve energy enforced | 6,663.52 | 745.20 | SOC 26%–95%, throughput 2,625.45 kWh |

**Energy cost alone picks the wrong plan**: relaxing the purchase cap from 840 to 900 saves only 5.15 CNY/day but raises the peak from 838.50 to 889.47 kW, adding 3,082.99 CNY to the monthly demand bill.

### 8.7 How to read

- The three examples share one structure: **energy revenue is sensitive to spread and RTE; capacity/demand revenue is sensitive to rule calibres**;
- Usable DC energy is not AC discharge energy; they differ by one factor of eta;
- Behind-the-meter, the core issue is not the spread but the coupling between contracted demand and the charging window;
- Co-located storage, the core issue is not arbitrage but the curtailment calibre and the PCC limit;
- No single example can be extrapolated into project revenue.

---

## 9. Engineering Review Checklist

### 9.1 P0: correctness or deliverability

| Check | Pass criterion |
|---|---|
| Import/export variables and exclusion | No simultaneous import and export |
| Charge/discharge exclusion | No simultaneous charge and discharge |
| SOC recursion | Includes efficiency, self-discharge, auxiliary power; conserved |
| SOC bounds and terminal | No violation, reasonable cross-day terminal |
| PCC limits | Not exceeded, export blocking active |
| Reserve power/energy | Awarded reserve deliverable, energy margin non-negative |
| Regulation recovery | Returns to baseline band by period end |
| Capacity-price eligibility | List, availability, duration factor correct |
| BMS/PCS limits | Independently checked before dispatch |
| Safety interlocks | No charge/discharge on alarm |
| Fallback | Feasible solution on timeout/failure |
| Clock and settlement calibre | Same source, same timestamp |
| DC/AC calibre | Usable DC energy separated from AC charge/discharge |
| Demand and contracted value | Billing method, 105% rule, charging window in the model |
| Metering map | Gateway and internal measurements reconcilable |

### 9.2 P1: performance or maintainability

| Check | Pass criterion |
|---|---|
| Solve time | Seconds for a 96-point single station; reduce grid on timeout |
| Numerical stability | No ill-conditioning from magnitude differences |
| Scenario management | Version, input snapshot and objective traceable |
| Externalized parameters | Prices, equipment and rules not hard-coded |
| Backtest framework | Same input reproduces the same plan |
| Alarm grading | Limit violation, infeasibility, missing data reported by level |
| Multi-station aggregation | Aggregate SOC displayed, per-device curves dispatched |

### 9.3 Red lines

- Never present unverified subsidies or unawarded capacity as certain revenue;
- Never tamper with operating data, evade assessment or conceal safety defects;
- Never replace a hard safety constraint with a penalty term;
- Never present a synthetic grade-D example as a project revenue promise;
- Never dispatch optimizer output without BMS/PCS limit checks.

---

## 10. Formulas and Code Mapping

| Formula/model | Code |
|---|---|
| Daily dispatch (SOC-grid DP) | `dispatch.dispatch_day()` |
| No-storage baseline | `dispatch.baseline_day()` |
| Station MW/MWh dispatch | `storage.station_day()` |
| Single cycle and round-trip efficiency | `storage.arbitrage_cycle()` |
| Curtailment charging | `storage.curtailment_charge()` |
| Available power/energy/duration | `storage.capability()` |
| Capacity payment and conversion | `market.capacity_payment()` |
| Regulation capacity + mileage | `market.frequency_regulation()` |
| Demand bill and saving | `market.demand_bill()` / `demand_saving()` |
| Microgrid dispatch and baseline | `microgrid.microgrid_day()` / `baseline_day()` |
| Island energy check | `microgrid.island_energy_need()` / `island_feasible()` |
| Synthetic curves | `curves.storage_day_prices()` / `microgrid_day()` / `user_day()` |

```python
import dispatch, market, microgrid, curves, storage

# Station: 100 MW / 200 MWh, RTE 88%, 24-point peak-valley prices
prices = curves.storage_day_prices()
run = storage.station_day(prices, 100, 200, 0.88, soc_min=0.1, soc_max=0.9, soc_init=0.1, degradation_per_kwh=0.03)
print(run["net_revenue"], run["throughput_mwh"])   # 91352.24, 320.6539

# Microgrid: 96 points, 500 kW PV, 840 kW purchase cap, 50 kW reserve
day = curves.microgrid_day()
plan = microgrid.microgrid_day(day["load_kw"], day["pv_kw"], day["buy_price"], capacity_kwh=1000, power_charge_kw=500, power_discharge_kw=500, pcc_import_kw=840, reserve_up_kw=50)
base = microgrid.baseline_day(day["load_kw"], day["pv_kw"], day["buy_price"], pcc_import_kw=900)
print(base["cost"] - plan["cost"])                  # 883.59
```

---

## 11. Glossary (Chinese–English)

| Chinese | English | Note |
|---|---|---|
| 能量管理系统 | EMS | Minute-to-hour economic dispatch |
| 电池管理系统 | BMS | SOC/SOH, power limit and protection |
| 储能变流器 | PCS | Power conversion and grid-interface control |
| 并网点 | PCC | Import/export metering point |
| 表后储能 | behind-the-meter storage | Customer side |
| 可用直流电量 | usable DC energy | Energy inside the SOC window |
| 往返效率 | round-trip efficiency | AC-AC |
| 荷电状态 | SOC | State of charge |
| 健康状态 | SOH | Capacity/resistance degradation indicator |
| 等效循环 | equivalent cycle | Throughput/(2 × rated energy) |
| 需量电费 | demand charge | Charged on maximum demand |
| 核定值 | contracted demand | Contracted maximum demand |
| 容量电价 | capacity price | Paid on available capacity |
| 调频里程 | regulation mileage | Actual regulation delivered |
| 性能系数 | K factor | Regulation performance score |
| 备用 | reserve | Up/down capacity |
| 爬坡 | ramping | Power change rate |
| 弃电 | curtailment | Energy beyond the export limit |
| 模型预测控制 | MPC | Rolling optimization |
| 条件风险价值 | CVaR | Tail-risk measure |
| 非预期性 | non-anticipativity | No use of future information |
| 孤岛 | islanding | Off-grid operation |

---

## 12. Reference Implementation and Self-Test

- Directory: `tools/`, standard library only, zero dependencies.
- Run:

```
python skills/ems-dispatch/tools/selftest.py
```

- Assertions cover:
  - Storage station: 150.09/170.56 MWh, gross arbitrage 100,971.86, degradation 9,619.62, net 91,352.24, capacity payment 15,068.49, total 106,420.74, 88,420.85 at RTE 85%;
  - Behind-the-meter: charge 8.5280 MWh, discharge 7.5047 MWh, net 4,414.11, demand 520,000 → 400,000 CNY/month, total 8,414.11;
  - Co-located: stored 28.14 MWh, discharge 26.40 MWh, net 14,148 / 9,648;
  - Capability: 418.95 kW / 735.00 kWh / 1.7544 h;
  - Microgrid: baseline 7,408.72, optimized 6,525.12, peak 838.50 kW, throughput 3,086.56 kWh, 1.5433 cycles, saving 883.59 (11.93%);
  - Sensitivities: degradation 6,617.72, storage +20% 6,350.61, 900 kW cap 6,519.97, reserve energy 6,663.52;
  - Demand: 35,082.99 → 32,000.00 CNY/month, saving 3,082.99, full charge 36,800, charging cap 440 kW;
  - Islanding: 100 kWh need feasible with 10% reserve, and an energy shortfall is flagged correctly.

> The tool is a **screening tool**, not a settlement system: it does not handle provincial assessment rules, taxes, complex financing, network security constraints or real-time tracking. Live operation must be recomputed with provincial rules, measured curves and equipment parameters.

---

## 13. Expert Q&A Reasoning Manual

> Each answer follows "fix the boundary → list constraints → give numbers → state the limits" without skipping steps.

### 13.1 "How much can a 100 MW/200 MWh system arbitrage in a day?"

Analytic calibre: 160 MWh usable DC, eta = 0.938083, discharge 150.09 MWh, charge 170.56 MWh; at 900/200 CNY/MWh the gross arbitrage is 100,971.86 CNY, and 91,352.24 CNY after 9,619.62 degradation. Adding a 15,068.49 capacity payment gives 106,420.74 CNY/day; including 0.3 MW auxiliary power gives 103,540.74 CNY/day. State clearly that this is a synthetic price, one cycle, no assessment.

### 13.2 "Why does the plan charge and discharge twice?"

Because the price curve offers two positive spreads. In the microgrid example the first round is 0.30 → 1.05 and the second is 0.65 → 1.25; both are profitable, so the optimizer performs two, equivalent to 1.5433 cycles. If the business requires one cycle per day, add a cycle constraint and accept forgoing the 0.60 CNY/kWh spread; assuming one cycle is the error.

### 13.3 "Reserve is bid at 50 kW, why is it still insufficient?"

The power margin is sufficient (441.8 kW < 450 kW) but the energy margin is not (−52.63 kWh). With SOC at the 20% floor, a 1-hour 50 kW discharge needs 52.63 kWh that is not there. Either raise the SOC floor to about 25.3% or shorten the reserve duration; the cost is 6,525.12 → 6,663.52 CNY/day.

### 13.4 "Storage shaved the peak, why did the basic charge not fall?"

Three common causes: (1) charging pushed valley purchase above the 105% line (full 500 kW charging makes purchase 900 kW and the monthly bill 36,800 CNY, 1,717.01 CNY more than without storage); (2) the discharge window did not cover the monthly maximum-demand interval; (3) the contracted value was not adjusted for the new shaving capability. Check the demand curve and charging window before discussing revenue.

### 13.5 "Forecasts are inaccurate, should the plan be re-run every day?"

Yes, roll — but get three things right first: forecast horizon = control horizon = settlement horizon; the day-ahead plan uses only day-ahead information; reserve energy is held against the worst deviation. Most projects capture most of the value at the "deterministic + reserve" stage; scenario optimization waits until the forecast distribution is stable.

---

## 14. Sources, Maintenance and Division of Labour

### 14.1 Methods and standards

- Policy: NDRC price〔2026〕No. 114 (capacity-price framework), NDRC energy regulation〔2025〕No. 1656 (renewables entering the market), NDRC energy regulation〔2025〕No. 411 (spot market);
- Standards: GB/T 36547-2024, GB/T 36549-2018, GB/T 36558-2023, GB/T 42288-2022, GB/T 51048-2025, IEEE 2030.7 (microgrid controller functions);
- Methods: mixed-integer linear programming, dynamic programming, model predictive control, two-stage stochastic programming with CVaR, robust optimization;
- Industry data: exchange disclosures, public tender and award notices (grade B).

### 14.2 Maintenance artifacts

- [Storage EMS note](../../knowledge/储能EMS优化调度-算法与工程-2026-11.md): full model, 18 constraints, capacity payment, regulation, degradation and multi-station aggregation;
- [Microgrid EMS note](../../knowledge/微网EMS优化调度-算法与工程-2026-11.md): PCC, islanding, MPC, capability and standards;
- `tools/`: zero-dependency reference implementation and example assertions.

### 14.3 Division of labour with sister skills

| Skill | Responsible for | How this skill uses it |
|---|---|---|
| Storage Investment & Operations | Appraisal, revenue stacking, LCOS/IRR/DSCR | Receives equipment parameters and revenue calibres; does not re-run appraisal |
| Virtual Power Plant Expert | Aggregation, demand response, VPP eligibility | Receives aggregation capability and dispatch instructions |
| Spot-Bidding Quant Expert | Price forecasting, bid curves, backtests | Receives point forecasts and quantiles |
| Electricity Trading Expert | Rule source text, settlement items | Cites rules without re-explaining them |
| Carbon Asset Management Expert | Carbon compliance, CCER | Not involved |

### 14.4 Maintenance cadence

- Quarterly: provincial capacity prices, demand rules, ancillary-service compensation;
- Half-yearly: equipment efficiency and degradation parameters, storage system prices;
- Annual: standards updates, example regression, tool self-test;
- Trigger-based: within one month of new spot rules, capacity-price details or grid-connection standards.
