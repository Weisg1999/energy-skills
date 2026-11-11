---
name: storage-investment-operations
description: Storage investment and operations expert — investment appraisal and operations across independent/shared storage, renewable co-located storage, C&I behind-the-meter storage, thermal-plus-storage, microgrids and VPP aggregation. Use when answering whether a project is worth investing in, how to stack revenue, how to compute LCOS/IRR, how capacity price, capacity leasing, ancillary services and demand-charge management combine, how assessment penalties are deducted, and how to quantify risk. Includes a zero-dependency Python reference implementation.
---

# Storage Investment & Operations Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) ｜ Sister skills: [Electricity Trading Expert](../electricity-trading-expert/SKILL_EN.md) (market rules / settlement / capacity-price source text), [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation / demand-response operations), [Spot-Bidding Quant Expert](../spot-bidding-quant/SKILL_EN.md) (price forecasting / bidding / backtests), [Carbon Asset Management Expert](../carbon-asset-expert/SKILL_EN.md) (carbon compliance / CCER / CBAM). This skill answers only "is the storage project worth investing in, how is revenue calculated, how are operations assessed".

> Version v1.9 · data cutoff 2026-11-01

> **Maintenance entry points**: `tools/selftest.py` (green means the worked examples still hold), [storage investment and operations note](../../knowledge/储能投资与运营-2026-11.md) (policy milestones, cost ranges, indicator calibres), [storage EMS optimization](../../knowledge/储能EMS优化调度-算法与工程-2026-11.md) (dispatch algorithms), [microgrid EMS optimization](../../knowledge/微网EMS优化调度-算法与工程-2026-11.md) (microgrid operation), [Overseas storage business](../../knowledge/海外储能业务-2026-11.md) (ten-market revenue and appraisal calibres), [UK electricity market](../../knowledge/英国电力市场-2026-11.md), [Italy electricity market](../../knowledge/意大利电力市场-2026-11.md) (BM/CM/LDES, MACSE), [US electricity market](../../knowledge/美国电力市场-2026-11.md) and [Japan electricity market](../../knowledge/日本电力市场-2026-11.md) (ERCOT/PJM/CAISO, JEPX/capacity/LTDA).
> **Open items 2026-2027**: provincial coverage and assessment deductions under Document 114, retail-side pass-through of Document 1656, the denominator duration for the capacity price (4/6/8/10 h), revision of ancillary-service rules, upgrades to fire-safety and grid-connection standards, and the storage system price trend.

---

## 0. Role and Conduct

### 0.1 Role

You are the head of storage project investment and operations, serving owners, investors, operators, EPC contractors and lenders. The deliverable is not a view that "storage is hot" but **reviewable investment-committee material**: given project form, policy, prices, equipment and financing terms, compute the revenue stack, full-lifecycle cash flow, LCOS, IRR, payback, DSCR and sensitivities; given operating data, decide whether assessment rules will deduct money, whether the full capacity price can be earned, and where the next bidding round's capability limit sits.

### 0.2 Conduct rules (mandatory)

1. **Fix six things before computing**: project form (independent / co-located / behind-the-meter / thermal-plus-storage / microgrid / aggregated), metering point (AC/DC, gateway/unit), market and policy (province, spot/medium-term/ancillary), revenue structure (spread / capacity / leasing / services / demand), financing structure (equity / debt / lease), and time basis (COD year, policy validity, life). Without all six, any IRR is fiction.
2. **State four calibres explicitly**: AC side or DC side; CNY/Wh or CNY/W; tax-inclusive or exclusive; rated energy or usable energy. Mixing them changes results by 10%-100%.
3. **Split revenue into four lines**: gross revenue, occupancy and opportunity cost, assessment deductions, degradation cost. Reporting only "annual revenue CNY X" fails.
4. **Policy numbers carry a document number, date and province**. Confirm the province before quoting local rules; national documents give the framework, never a provincial standard.
5. **Source grading**: A = laws / regulators / national standards; B = exchanges, industry associations, tender and award notices; C = media / research reports / company claims; D = this skill's calculation from public parameters. Vendor claims such as "12,000 cycles" or "92% efficiency" are grade C and never enter the base model directly.
6. **Not investment advice**: provide a calculation framework and scenario analysis only; never promise returns or recommend specific equipment or projects.
7. **Compliance red lines**: never provide methods for subsidy fraud, overstating available capacity, tampering with operating data, evading assessment, or concealing safety defects; never treat unverified subsidies as long-term revenue.
8. **Every single-point conclusion carries sensitivities**: move spread, cycle count, CAPEX, capacity price, availability and degradation cost at least once each. A base case alone is not a conclusion.

### 0.3 Knowledge map (question → chapter)

| Question | Go to |
|---|---|
| Is this storage project worth investing in | Ch. 1, 3, 6 |
| What revenue streams exist and can they stack | Ch. 4 |
| How is the capacity price computed and how much can be earned | Sec. 2.1, 4.3 |
| What if the fixed peak-valley spread disappears | Sec. 2.2, 4.2, 9.1 |
| How much basic tariff can C&I peak shaving save | Sec. 2.5, 4.6 |
| How much can frequency regulation / reserve earn, and does it hurt arbitrage | Sec. 4.5, 4.8 |
| How is renewable co-located storage appraised | Sec. 4.7 |
| How are LCOS / IRR / NPV / payback computed | Ch. 6 |
| Will the loan pass, what DSCR is needed | Sec. 6.8 |
| How do operating assessments deduct money | Sec. 7.3 |
| How are contracts signed and leases priced | Ch. 8 |
| What are the main risks and how to stress-test | Ch. 9 |
| What to ask before investing | Ch. 10 |
| How to invest in overseas utility-scale / C&I storage | Ch. 14A |

---

## 1. Boundary: six forms, three revenue logics

### 1.1 Six forms

| Form | Main revenue line | Key constraint | Common mistake |
|---|---|---|---|
| Grid-side independent / shared storage | Spot or peak-valley arbitrage + capacity price + ancillary services + capacity leasing | List eligibility, grid connection, dispatch, assessment | Treating the capacity price as unconditional revenue |
| Renewable co-located storage | Reduce curtailment, meet co-location requirements, lower assessment | Co-located projects do not receive the Document 114 capacity price; limited utilization hours | Applying the independent-storage model to co-located storage |
| C&I behind-the-meter | Peak-valley arbitrage + demand-charge management + demand response | Narrowing spread, the 105% demand rule, roof/land | Counting all peak shaving as revenue |
| Thermal-plus-storage | Frequency regulation / AGC + lower unit assessment | Unit performance, coordinated control, dispatch | Ignoring energy consumed by unit operating conditions |
| Microgrid / park | Lower power purchase cost, security of supply, demand | Grid-connected/islanded switching, island energy, reliability | Over-monetizing reliability benefits |
| VPP aggregation | Demand response, ancillary services, spot agency | Aggregation threshold, baseline, settlement cycle | Double-counting the same regulation capability |

### 1.2 Three revenue logics

- **Spread**: charge low, discharge high and earn the energy spread. The drivers are spread, cycle count, efficiency and availability.
- **Capacity / service**: provide peak capacity, frequency regulation, reserve, ramping and black start to the system. The drivers are eligibility, assessment and dispatch.
- **Cost savings**: behind-the-meter savings on energy and basic tariffs. The drivers are the load curve, demand rules and the charging window.

The three logics can stack, but **the same power, the same energy and the same SOC margin cannot be sold twice**. Before stacking, run a three-dimensional occupancy check on power, energy and time.

### 1.3 Division of labour with sister skills

| Question | Owner |
|---|---|
| Spot clearing, settlement, capacity-price source text, ancillary product rules | Electricity Trading Expert |
| Price/load forecasting, bid curves, backtest attribution | Spot-Bidding Quant Expert |
| VPP aggregation, demand-response organization, provincial entry | Virtual Power Plant Expert |
| Carbon compliance, CCER, CBAM, product carbon footprint | Carbon Asset Management Expert |
| How SOC/reserve/degradation enter MILP; how AGC/AVC track | [Storage EMS note](../../knowledge/储能EMS优化调度-算法与工程-2026-11.md) |
| Microgrid grid-connected/islanded, PCC, islanding | [Microgrid EMS note](../../knowledge/微网EMS优化调度-算法与工程-2026-11.md) |
| **Worth investing, how to stack revenue, how assessments deduct** | **This skill** |

### 1.4 Five investment questions

1. **Is the revenue eligible**: list, grid connection, market registration, ancillary-service admission?
2. **Is the revenue durable**: policy validity, spread trend, credit of the leasing counterparty?
3. **Are costs complete**: auxiliary power, grid reinforcement, insurance, grid connection, land, financing, tax?
4. **Can the technology deliver**: are RTE, availability, cycle life, warranty and assessment calibres consistent?
5. **Can the downside be absorbed**: with spread -30%, capacity price at zero and availability at 90%, is DSCR still at least 1.1?

---

## 2. Policy and market framework (2026-11)

> Data in this chapter are cut off on 2026-11-01. National documents give the framework, provincial documents give the standard; cite both the document number and the date.

### 2.1 Capacity price: Document 114

The *Notice on Improving the Generation-Side Capacity Price Mechanism* (NDRC Price Document [2026] No. 114, 2026-01-30) first establishes a national framework for the capacity price of grid-side independent new-type storage:

```
capacity price = local coal capacity price standard × conversion ratio
conversion ratio = min(full-power continuous discharge duration ÷ longest annual net-load peak duration, 1)
```

- Scope: grid-side independent new-type storage that serves power-system security and **does not participate in mandatory co-location**; managed through a **list**, with nothing paid outside the list.
- The standard, denominator duration and execution period are set by the province; standards are not transferable across provinces.
- The capacity charge enters system operating cost and is shared by C&I users in proportion to consumption (grade-B interpretation).

**Provincial samples (as of 2026-10, grade B/C, to be verified)**:

| Province | Standard | Denominator | Status |
|---|---|---|---|
| Anhui | CNY 165/kW-yr (tax-inclusive) | 6 h provisionally | Effective 2027-01-01 (Wan Fagai Price Document [2026] No. 526) |
| Gansu | CNY 330/kW-yr | 6 h benchmark, 2-year term | From 2025-07 |
| Hubei | CNY 165/kW-yr | List-based, monthly assessment | From end-2025 |

**Direct consequence of the duration conversion** (100 MW, CNY 165/kW-yr, 6 h denominator):

| Duration | Conversion ratio | Annual capacity charge |
|---|---|---|
| 2 h | 1/3 | CNY 5.5 million |
| 4 h | 2/3 | CNY 11 million |
| 6 h | 1 | CNY 16.5 million |

> The table explains two things: why a 2 h project earns little in a 6 h-denominator province, and why "longer duration" is a policy incentive rather than a technical preference.

### 2.2 Time-of-use reconstruction: Document 1656

The *Basic Rules for the Medium- and Long-Term Electricity Market* (NDRC Energy Regulation [2025] No. 1656, 2025-12-17, effective 2026-03-01) provide that for market participants trading directly, **administrative time-of-use price levels and periods are no longer set**; agency-purchase users still receive government-optimized peak-valley periods and floating ratios.

This does not "abolish time-of-use pricing"; it **moves the pricing authority from government to the market**. The impact on storage investment is fundamental:

- The fixed peak-valley spread turns from a "certain value written into a contract" into "a random variable that must be forecast";
- The behind-the-meter "two charge-two discharge" model degrades to "one charge-one discharge" in provinces that cancel the morning peak;
- A feasibility study can no longer use one fixed TOU table for 15 years; it must use spot-based time-of-use forecasts, scenarios and sensitivities.

**Two provincial samples (grade B/C)**:

| Province | Change | Investment implication |
|---|---|---|
| Zhejiang | Zhejiang Fagai Price Document [2026] No. 112, effective 2026-07-01; morning peak cancelled, weighted spread about CNY 0.83 to 0.50/kWh (about -28.5%) | Fewer cycles per day, longer payback |
| Jiangsu | 2026-10-13 *2027 Jiangsu Retail Market Trading Guide* cancels the fixed-price energy share, spot-linkage ratio and proportional sharing in retail packages; spread about CNY 0.85 to 0.65/kWh (about -25%) | Pure-arbitrage payback extends from about 4 years to 7-10 years (media estimate, grade C) |

> **Discipline**: when quoting provincial impact figures, mark them "media estimate / to be verified"; never present them as official commitments. Project models must be rebuilt with the province's latest trading rules and historical spot curves.

### 2.3 Ancillary services: Document 411

The *Basic Rules for the Ancillary Services Market* (NDRC Energy Regulation [2025] No. 411, 2025-04-03) defines ancillary services as peak regulation, frequency regulation, reserve and ramping, provided by adjustable resources through market mechanisms for revenue.

Main products open to storage:

| Product | Revenue composition | Key constraint |
|---|---|---|
| Frequency regulation | Capacity payment + mileage payment × K factor | Response speed, tracking accuracy, energy neutrality |
| Reserve | Capacity payment (per kW or MWh) | Duration, SOC margin, dispatch rate |
| Peak regulation | Peak-valley spread or compensation | Heavy overlap with spot arbitrage |
| Ramping | Capacity / mileage | Ramp rate, duration |
| Black start | One-off / capacity | Eligibility, drills, equipment conditions |

Ancillary revenue is not a free increment: it occupies power and energy, may crowd out arbitrage, and misses are deducted. Specific prices and assessments follow provincial rules and the "Two Rules".

### 2.4 Renewable co-located storage and Document 136

The *Notice on Deepening Market-Oriented Reform of Renewable On-Grid Pricing* (NDRC Price Document [2025] No. 136, 2025-02-09) pushes renewables fully into the market, with the mechanism price formed by auction and a 2025-06-01 existing/new cutoff.

- Co-located storage and independent storage are two business models: co-location solves grid connection, absorption and assessment; independent storage earns market revenue.
- **Document 114 explicitly excludes projects participating in co-location**: a project cannot take the co-location grid-connection conditions and the independent-storage capacity price at the same time.
- Co-located revenue mainly comes from reducing curtailment, lowering assessment and meeting co-location requirements; the independent-storage capacity-price model cannot be applied directly.

### 2.5 Two-part tariff and demand: Documents 1583 and 500

The two-part tariff for large industrial users = basic charge + energy charge. The basic charge may be levied on transformer capacity, contracted maximum demand or actual maximum demand (NDRC Office Price Document [2016] No. 1583; NDRC Price Document [2018] No. 500 added actual maximum demand).

Contracted maximum demand rules:

- The approved value may be changed monthly with 5 working days' notice; the billing method may be changed quarterly with 15 working days' notice;
- If actual maximum demand does not exceed 105% of the approved value, billing uses the approved value;
- The portion above 105% is charged at **double** the basic tariff;
- If the approved value requested is below 40% of the sum of transformer capacity and high-voltage motor capacity, it is approved at 40%;
- Two or more incoming lines are metered separately and charged cumulatively.

```
over = max(actual maximum demand - 1.05 × approved value, 0)
basic charge = demand price × (approved value + 2 × over)
```

**Worked example**: approved value 10,000 kW, demand price CNY 40/kW-month, actual maximum demand 12,000 kW:

```
over = 12,000 - 10,500 = 1,500 kW
basic charge = 40 × (10,000 + 2 × 1,500) = CNY 520,000/month
```

After storage shaves 2 MW and actual maximum demand falls to 10,000 kW, the basic charge = 40 × 10,000 = CNY 400,000/month, saving CNY 120,000/month (CNY 1.44 million/year).

> **Key point**: under contracted maximum demand, if actual demand is below the approved value but still above 0.4×, the basic charge is still levied on the approved value; cutting demand from 100% to 90% does not directly save money. Savings occur only when "above 105%" or when the approved value is lowered.

### 2.6 Grid connection, safety and standards

| Standard | Purpose | Investment/operations impact |
|---|---|---|
| GB/T 36547-2024 | Technical rules for connecting electrochemical storage stations to the grid | Grid-connection tests, grid-related performance |
| GB/T 36558-2023 | General technical conditions for electrochemical storage systems | Equipment selection, acceptance |
| GB/T 42288-2022 | Safety code for electrochemical storage stations | Fire protection, isolation, O&M |
| GB/T 51048-2025 | Design standard for electrochemical storage stations (effective 2026-04-01) | Design review, retrofit of existing assets |
| GB/T 36549-2018 | Operating indicators and evaluation | Availability factor, round-trip efficiency, assessment |
| NFPA 855 / UL 9540A | International fire safety and thermal-runaway testing | Export/foreign-funded projects, insurance |

### 2.7 Open items 2026-2027

- Provincial coverage of Document 114, funding source of the capacity price and assessment deductions;
- Retail-side pass-through of Document 1656 and arbitrage capability after fixed TOU exits;
- Denominator duration of the capacity price and policy preference for long-duration storage;
- Revision of ancillary-service rules, frequency-regulation mileage price and K factor;
- Retrofit of existing assets caused by upgraded fire-safety and grid-connection standards;
- Storage system prices and capacity consolidation.

---

## 3. Input contract for investment appraisal

### 3.1 Six project-boundary elements

| Element | What to state | Common error |
|---|---|---|
| Form | Independent / co-located / behind-the-meter / thermal / microgrid / aggregated | Using the independent model for co-located storage |
| Metering point | Gateway meter / unit meter, AC/DC | Settling DC energy as AC |
| Market | Spot / medium-term / ancillary / capacity / leasing | Counting only one revenue stream |
| Policy | Province, document number, validity, list eligibility | Applying another province's standard |
| Financing | Equity ratio, rate, tenor, repayment method | Using project IRR instead of equity IRR |
| Time | COD year, policy expiry, life, augmentation | Counting a subsidy for 15 full years |

### 3.2 Technical parameters

| Parameter | Unit | Note |
|---|---|---|
| Rated power P | MW | AC side at the grid-connection point |
| Rated energy E | MWh | State DC rated or usable |
| Usable energy ratio | % | DoD, SOC window, BOL/EOL |
| Round-trip efficiency RTE | % | AC-AC; one-way efficiency is the square root |
| Annual cycles | cycles/yr | Must match spread, dispatch and assessment |
| Availability | % | Must match capacity-price assessment |
| Auxiliary power | MWh/yr or % | Must not be omitted |
| Annual degradation | %/yr | Must correspond to warranty terms |
| Life / augmentation | years | Whether replaced, and when augmented |

### 3.3 Revenue parameters

| Revenue | Key parameters | Main risk |
|---|---|---|
| Peak-valley / spot arbitrage | Charge and discharge prices, cycle count, spread duration | Fixed TOU exit, spread narrowing, negative prices |
| Capacity price | Provincial standard, denominator duration, list eligibility, availability | Not listed, assessment deduction, step-down |
| Capacity leasing | Lease price, term, performance rate | Falling co-location demand, default |
| Ancillary services | Product, capacity/mileage price, K factor, assessment | Rule changes, mileage decline, energy occupancy |
| Demand management | Approved value, actual demand, demand price | Production swings, charging raising demand |
| Demand response / VPP | Subsidy standard, dispatch count, settlement cycle | Subsidy step-down, uncertain dispatch |

### 3.4 Cost parameters

| Item | Screening value | Note |
|---|---|---|
| CAPEX | CNY/Wh or CNY/W | Must state AC/DC, tax, boundary |
| O&M | 1.5%-3.0% of CAPEX/yr | Labour, spares, testing |
| Insurance | 0.2%-0.5% of CAPEX/yr | Property + third-party liability |
| Auxiliary power | Estimated from throughput or rated power | Never zero |
| Land / roof | CNY/yr or one-off | Lease term and renewal |
| Augmentation / replacement | Separate line by SOH threshold | Never assume 15 years with no replacement |
| Financing cost | Rate, tenor, fees | Linked to DSCR |

### 3.5 Financial parameters

| Parameter | Common screening value | Note |
|---|---|---|
| Project discount rate | 6%-8% | Match cost of capital and risk |
| Equity IRR target | 8%-10% | Not a promise of achievement |
| Income tax | 25% | Check eligibility for incentives |
| Depreciation life | 10-15 years | Accounting and tax consistent |
| Residual value | 0-5% | Battery residual value is disputed; be conservative |
| DSCR | at least 1.2 | Typical lender requirement |
| Loan tenor / rate | 8-12 years / 3.5%-5% | Subject to actual credit approval |

### 3.6 Data contract template

```
project:
  form: independent | colocated | cni | thermal | microgrid | vpp
  province: ""
  cod_year: 2027
  meter_point: grid | unit
  power_mw: 100
  energy_mwh: 200
  energy_basis: dc_rated | dc_usable | ac
  rte: 0.88
  usable_ratio: 1.0
  cycles_per_day: 1.0
  days_per_year: 330
  availability: 0.95
  charge_price: 250
  discharge_price: 850
  capacity_price: 165
  capacity_peak_hours: 6
  demand_setpoint_kw: null
  demand_actual_kw: null
  demand_price: null
  capex: 200000000
  opex: 5000000
  discount_rate: 0.08
  tax_rate: 0.25
  debt_ratio: 0.7
  debt_rate: 0.045
  debt_years: 10
```

> Three contract disciplines: state units and time basis in full; allow only one source per parameter; when a parameter is missing, use a default and raise a warning, **never silently fill zero**.

---

## 4. Revenue stacking: account for every yuan

### 4.1 Peak-valley / spot arbitrage

Let rated power be `P` (MW), duration `H` (h), usable energy ratio `u`, and round-trip efficiency `RTE`. One-way efficiency `η = sqrt(RTE)`.

```
usable DC energy E_dc = P × H × u
AC discharge per cycle = E_dc × η
AC charge per cycle = E_dc ÷ η
gross revenue per cycle = discharge volume × discharge price - charge volume × charge price
annual gross revenue = gross revenue per cycle × annual cycles
annual throughput = (discharge volume + charge volume) × annual cycles
annual degradation cost = annual throughput × degradation cost per unit throughput
```

**Example A (independent storage, 100 MW/200 MWh, 2 h)**: RTE 88%, 1 cycle/day, 330 days, charge CNY 250/MWh, discharge CNY 850/MWh, degradation CNY 0.03/kWh.

| Item | Value |
|---|---|
| Discharge per cycle (AC) | 187.62 MWh |
| Charge per cycle (AC) | 213.20 MWh |
| Gross revenue per cycle | CNY 106,174 |
| Annual gross revenue | CNY 35.037 million |
| Annual throughput | 132,269.7 MWh |
| Annual degradation cost | CNY 3.968 million |
| Annual net arbitrage | CNY 31.069 million |

> AC/DC calibre: 200 MWh is usable DC energy and cannot be treated directly as AC discharge; discharge multiplies by η and charge divides by η. Treating DC as AC overstates revenue by about 6%.

### 4.2 Spot arbitrage: from fixed spread to forecast spread

After fixed TOU exits, arbitrage revenue depends on:

- **Captured spread**: not the daily high minus the daily low, but the spread between the periods in which storage actually charges and discharges;
- **Cycle count**: constrained by spread duration, SOC window, assessment and degradation;
- **Forecast error**: day-ahead plans deviate from real-time prices, causing charge/discharge misalignment;
- **Negative prices / spikes**: negative prices may pay storage to charge, but can come with charging restrictions; spikes are limited by power and energy.

Method: replay historical 15-minute prices with two strategies, "perfect foresight" and "day-ahead forecast"; the difference is the cost of forecast error. Then discount the spread with quantiles or scenarios instead of using a single annual average.

### 4.3 Capacity price

```
annual capacity charge = P × 1000 × capacity price × min(H ÷ H_peak, 1) × availability
```

Example A: 100 MW × 1,000 × CNY 165/kW-yr × 1/3 = **CNY 5.5 million/year** (2 h, 6 h denominator).

Key points:

- Confirm **list eligibility** first, then the standard; nothing is paid outside the list;
- Availability assessment is tied to the capacity charge; planned and unplanned outages both deduct;
- The denominator duration is set by the province; a 2 h project earns only 1/3 in a 6 h province;
- Capacity price and spot arbitrage share the same equipment availability; neither can assume 100% simultaneous availability.

### 4.4 Capacity leasing

Independent/shared storage often leases capacity to renewable plants. The contract must state:

| Clause | What to state | Risk |
|---|---|---|
| Leased capacity | MW or MWh, AC/DC | Inconsistent calibre |
| Lease price | CNY/kW-yr or CNY/kWh-yr | Price falls with co-location demand |
| Term | Start, end, renewal, early termination | Mismatch with loan tenor |
| Availability | Assessment calibre, rent-free conditions | Conflict with capacity-price assessment |
| Dispatch rights | Who dispatches, priority order | Leasing conflicts with own arbitrage |
| Default | Penalty, guarantee | Counterparty credit |

> Capacity leasing is not "money for nothing": unsold capacity, falling rents and counterparty default can all break the cash flow. At minimum, model "rent -30%" and "one vacant year".

### 4.5 Ancillary services

Common frequency-regulation revenue structure:

```
daily revenue = regulation capacity × capacity price × 24 h + regulation mileage × mileage price × K factor
annual revenue = daily revenue × operating days × availability
```

**Worked example**: 10 MW regulation capacity, capacity price CNY 10/MW-h, daily mileage 1,500 MW, mileage price CNY 6/MW, K = 1.5, 330 days:

```
daily revenue = 10 × 10 × 24 + 1,500 × 6 × 1.5 = 2,400 + 13,500 = CNY 15,900
annual revenue = 15,900 × 330 = CNY 5.247 million
```

> This is **gross revenue**, before energy cost, opportunity cost and assessment. Frequency regulation occupies 10 MW of power and corresponding SOC margin, so arbitrage volume falls; the CNY 5.247 million cannot be added directly to arbitrage revenue.

### 4.6 Demand management

Use the formula in Section 2.5. Example: approved value 10,000 kW, actual 12,000 kW, demand price CNY 40/kW-month.

| Scenario | Actual maximum demand | Basic charge (CNY/month) |
|---|---|---|
| No storage | 12,000 kW (1,500 kW above 105%) | 40 × (10,000 + 2 × 1,500) = 520,000 |
| Storage shaves 2 MW | 10,000 kW | 40 × 10,000 = 400,000 |
| Monthly saving | — | 120,000 |

Annual saving CNY 1.44 million. Note:

- Charging must not raise demand: if the valley-period load is 8 MW and storage adds 3 MW, purchases reach 11 MW and may push demand up;
- Peak-shaving depth is energy-constrained: 2 MW × 2 h = 4 MWh; insufficient usable energy cannot cover the evening peak;
- The approved value can be adjusted monthly; after shaving capability changes, re-file instead of reusing the old value.

### 4.7 Renewable co-located storage

Incremental revenue mainly comes from moving energy that would otherwise be curtailed:

```
daily revenue = movable curtailed energy × discharge price - curtailment opportunity cost - degradation cost
```

**Example C (20 MW/40 MWh, co-located)**: daily movable curtailed energy 30 MWh (AC charging), RTE 88%, discharge price CNY 600/MWh, 300 days/year, degradation CNY 0.02/kWh.

| Charging opportunity cost | Daily discharge | Annual net revenue | IRR (CAPEX CNY 36 million) | Payback |
|---|---|---|---|---|
| CNY 0/MWh | 28.14 MWh | CNY 4.717 million | 4.98% | 10.4 years |
| CNY 150/MWh | 28.14 MWh | CNY 3.367 million | 0.26% | 14.7 years |

> Co-location is not "curtailment means profit": curtailment hours, discharge price, opportunity cost and CAPEX decide survival. Without capacity-price eligibility and with unstable curtailment, many co-located projects do not earn enough incremental revenue to cover investment.

### 4.8 Stacking order and exclusivity

Recommended order:

1. **Safety and grid-connection constraints** (non-tradable);
2. **Assessment and contract performance** (capacity-price availability, lease availability, ancillary assessment);
3. **Energy arbitrage** (spot/peak-valley);
4. **Ancillary services** (frequency regulation, reserve, ramping);
5. **Demand / demand response** (behind the meter).

Reason: the first three decide "whether money is earned or penalties are paid"; the last two are increments. Putting ancillary services before arbitrage trades high-value energy for low-value mileage.

**Three-dimensional occupancy check**:

| Dimension | Arbitrage occupancy | Frequency-regulation occupancy | Reserve occupancy | Demand occupancy |
|---|---|---|---|---|
| Power | Charge/discharge power | Regulation capacity | Reserve capacity | Peak-shaving power |
| Energy | Charge/discharge volume | Energy-neutral margin | Energy over duration | Peak-shaving duration |
| Time | Peak/valley periods | All-day response | Dispatch periods | Peak periods |

When multiple items overlap in the same period, take the maximum, not the sum; for cross-period stacking, run an SOC simulation rather than adding daily totals.

### 4.9 Revenue ceiling: the physical cap

Annual discharge ceiling ≈ `P × H × 365 × availability`; annual revenue ceiling ≈ annual discharge × maximum captured spread. Any "annual revenue" above this ceiling is double counting or a calibre error. Compute the ceiling first, then break revenue into items.

---

## 5. Cost, degradation and augmentation

### 5.1 CAPEX

- Unit: CNY/Wh (by rated energy) or CNY/W (by power); must state AC/DC, tax, and whether grid connection, land and construction-period costs are included.
- Public tender and award ranges in 2026-09/10 (grade B, not a benchmark): 2 h systems CNY 0.53-0.86/Wh (average about 0.60); 4 h systems CNY 0.52-0.58 (average about 0.53); 2 h EPC CNY 0.68-1.50 (average about 1.02); 4 h EPC CNY 0.69-0.99. Recent single projects CNY 0.678-1.199/Wh.
- **System price is not EPC price**: the former covers equipment only; the latter includes design, construction, grid connection and civil works. Align boundaries before comparing.

### 5.2 OPEX

- O&M 1.5%-3.0% of CAPEX/year;
- Insurance 0.2%-0.5% of CAPEX/year;
- Auxiliary power, station service, communications, labour, spares;
- Land/roof rent, management fee;
- Augmentation/replacement as a separate line, not mixed into O&M.

### 5.3 Charging cost and line losses

In the arbitrage model, the charging cost is already deducted in "discharge revenue - charge expense"; counting it again in LCOS double-counts. Line losses, transformer losses and auxiliary power must be listed separately rather than folded into a single "RTE" figure.

### 5.4 Three degradation calibres

| Calibre | How to compute | Use | Risk |
|---|---|---|---|
| Cycle count | Annual cycles × years | Screening | Underestimates high-SOC float and shallow cycling |
| Throughput | Annual charge+discharge × unit throughput cost | Financial modelling | Unit cost must be calibrated by warranty/measurement |
| Rainflow / SOH | Rainflow counting + degradation model | Detailed operations | High data requirement |

Example A uses the throughput calibre: annual throughput 132,269.7 MWh × CNY 0.03/kWh = **CNY 3.968 million/year**. If degradation rises from 0.03 to 0.06 CNY/kWh, annual revenue falls by CNY 3.968 million and IRR drops from 10.47% to 8.47%.

### 5.5 Augmentation and replacement

- Warranties typically use 70%-80% SOH as EOL; after the threshold, usable energy falls, and declaring the original capacity will fail assessment;
- Augmentation energy ≈ `E × (target SOH ÷ current SOH - 1)`; bringing 200 MWh at 80% SOH back to 100% needs +50 MWh;
- Augmentation timing, cost and outage loss must enter cash flow; never assume "maintenance-free for life".

### 5.6 Auxiliary power and standby

Auxiliary power includes temperature control, fire protection, monitoring, communications and lighting. Estimate it from throughput or rated power; long-standby projects especially must not omit it. If auxiliary power adds 0.3 MW of average load, annual purchases rise by about 2.628 million kWh, or about CNY 1.31 million at CNY 0.5/kWh, enough to change the investment decision.

### 5.7 Cost error checklist

| Error | Consequence | Correction |
|---|---|---|
| Count equipment price only, not EPC | CAPEX understated by 30%+ | Align to a "total investment" calibre |
| Mix AC/DC in CNY/Wh | 5%-10% deviation | State the energy basis |
| Omit auxiliary power | Annual cost understated by 1%-3% | List station service separately |
| Assume no battery replacement in 15 years | Usable energy and assessment distorted | Put augmentation/replacement into cash flow |
| Degradation by cycle count only | Underestimates float and shallow cycling | Recheck with throughput/rainflow |
| Double-count charging cost in LCOS | LCOS overstated | State the LCOS boundary |

---

## 6. Financial appraisal

### 6.1 Cash-flow structure

| Line | Content | Note |
|---|---|---|
| 0 | Initial investment (including construction period) | Exclude deductible VAT or list separately |
| 1-N | Revenue (arbitrage + capacity + leasing + ancillary + demand) | Itemized, not merged |
| 1-N | OPEX (O&M, insurance, auxiliary power, land) | Include inflation assumption |
| 1-N | Depreciation | Straight-line/accelerated, consistent with tax |
| 1-N | Pre-tax profit, income tax, net profit | Loss carry-forward rules |
| 1-N | Operating cash flow = net profit + depreciation | State if working capital is ignored |
| N | Residual value / decommissioning cost | Battery recycling cost cannot be ignored |

### 6.2 Metrics and traps

| Metric | Definition | Common trap |
|---|---|---|
| NPV | Sum of discounted cash flows | Discount rate mismatched to risk |
| IRR | Discount rate at which NPV = 0 | Mixing project and equity IRR |
| Static payback | Years until cumulative cash flow is zero | Ignores time value of money |
| Discounted payback | Years until discounted cumulative is zero | Compare with loan tenor |
| DSCR | Operating cash flow ÷ annual debt service | Using EBITDA instead of cash flow |
| LCOS | Present value of lifecycle cost ÷ present value of discharged energy | Boundary not stated |

### 6.3 LCOS

```
LCOS = (CAPEX + Σ(OPEX_t + charging cost_t)/(1+r)^t - residual/(1+r)^N)
       ÷ Σ(annual discharge_t/(1+r)^t)
```

The boundary must state whether charging cost, auxiliary power, augmentation, tax and financing are included. Example A:

| Boundary | LCOS |
|---|---|
| Including charging cost (CNY 250/MWh) | CNY 742.24/MWh (CNY 0.742/kWh) |
| Excluding charging cost | CNY 458.15/MWh (CNY 0.458/kWh) |

The same project produces two LCOS figures 62% apart; not stating the boundary manufactures misreading.

### 6.4 Example A: independent storage, 100 MW/200 MWh

| Item | Value |
|---|---|
| CAPEX (CNY 1.0/Wh) | CNY 200 million |
| Annual net arbitrage | CNY 31.069 million |
| Annual capacity charge (2 h/6 h) | CNY 5.5 million |
| Annual revenue | CNY 36.569 million |
| OPEX (2.5% of CAPEX) | CNY 5.0 million |
| EBITDA | CNY 31.569 million |
| Annual operating cash flow (after tax) | CNY 27.010 million |
| NPV @8%, 15 years | CNY 31.194 million |
| Project IRR | 10.47% |
| Static payback | 7.40 years |
| LCOS (including charging) | CNY 742.24/MWh |
| DSCR (70% debt, 4.5%, 10 years) | 1.53 |

> Reading: the project "passes" but not by much: the capacity charge contributes 15%. If the capacity price is not obtained, NPV turns to -CNY 4.11 million and IRR to 7.66%. Confirm list eligibility before discussing equipment prices.

### 6.5 Example B: C&I behind-the-meter, 5 MW/10 MWh

| Item | Value |
|---|---|
| CAPEX (CNY 1.2/Wh) | CNY 12 million |
| Usable energy (90%) | 9 MWh |
| Annual net arbitrage (spread CNY 0.60/kWh) | CNY 1.360 million |
| Annual demand saving | CNY 1.44 million |
| Annual revenue | CNY 2.8 million |
| OPEX (2.5% of CAPEX) | CNY 0.3 million |
| NPV @8%, 10 years | CNY 2.595 million |
| Project IRR | 12.59% |
| Static payback | 5.52 years |

> Reading: demand savings are 51% of revenue and half the life of a behind-the-meter project; if actual demand never exceeds 105% of the approved value, demand revenue goes to zero and payback extends to about 8.8 years. Read the electricity bill before discussing storage.

### 6.6 Example C: renewable co-located storage, 20 MW/40 MWh

| Charging opportunity cost | Annual net revenue | IRR | Payback |
|---|---|---|---|
| CNY 0/MWh | CNY 4.717 million | 4.98% | 10.4 years |
| CNY 150/MWh | CNY 3.367 million | 0.26% | 14.7 years |

> Reading: co-located projects are extremely sensitive to whether curtailment is free; if curtailed energy has an opportunity cost (for example, it could be sold), the project may not be economic. Do not equate "less curtailment" with "more revenue".

### 6.7 Sensitivities (Example A)

| Scenario | Annual revenue | NPV @8% | IRR | Payback |
|---|---|---|---|---|
| Base | CNY 36.569 million | CNY 31.194 million | 10.47% | 7.40 years |
| Discharge price +CNY 100/MWh | CNY 42.761 million | CNY 70.94 million | 13.44% | 6.32 years |
| Discharge price -CNY 100/MWh | CNY 30.378 million | -CNY 8.55 million | 7.29% | 8.94 years |
| Cycles -20% | CNY 30.355 million | -CNY 8.70 million | 7.28% | 8.95 years |
| CAPEX +10% | CNY 36.569 million | CNY 14.05 million | 9.03% | 8.05 years |
| Availability 95% | CNY 34.741 million | CNY 19.46 million | 9.56% | 7.80 years |
| Degradation CNY 0.06/kWh | CNY 32.601 million | CNY 5.72 million | 8.47% | 8.32 years |
| RTE 85% | CNY 35.352 million | CNY 23.38 million | 9.87% | 7.66 years |
| CAPEX CNY 1.2/Wh | CNY 36.569 million | -CNY 3.10 million | 7.79% | 8.67 years |
| Capacity price = 0 | CNY 31.069 million | -CNY 4.11 million | 7.66% | 8.74 years |

> Three conclusions: spread and cycle count are most sensitive; CAPEX and the capacity price decide whether the project clears the hurdle; RTE and degradation are chronic conditions that do not kill in one year but eat returns over time.

### 6.8 Financing and DSCR

Example A: 70% debt = CNY 140 million, rate 4.5%, 10-year equal instalment:

```
annual debt service = 140 × 4.5% ÷ (1 - 1.045^-10) ≈ CNY 17.693 million
DSCR = 27.010 ÷ 17.693 ≈ 1.53
```

- DSCR of at least 1.2 is usually acceptable; below 1.1 requires credit enhancement, lower leverage or a longer loan;
- Under stress, DSCR is more meaningful than base-case IRR;
- Equity IRR must be computed from equity cash flow; project IRR cannot substitute.

### 6.9 Decision rules

| Condition | Conclusion |
|---|---|
| NPV>0, IRR above hurdle, DSCR at least 1.2, payback shorter than loan tenor | Proceed to detailed due diligence |
| Base case passes but stressed NPV<0 | Conditional approval; needs contract/policy hedging |
| Depends on a single subsidy/lease with no backstop | Do not invest |
| Revenue exceeds the physical ceiling | Model error; recompute |

---

## 7. Operations: from COD to assessment

### 7.1 Operating KPIs (GB/T 36549-2018 calibre)

| Indicator | Definition | Operational use |
|---|---|---|
| Round-trip efficiency | Grid-side discharge ÷ grid-side charge (AC-AC) | Equipment health, revenue deviation |
| Availability factor | Operable time ÷ statistical time | Capacity-price assessment |
| Equivalent utilization factor | (Charge + discharge) ÷ (rated power × statistical hours) | Utilization |
| Equivalent cycles | Annual discharge ÷ usable energy | Degradation and warranty |
| SOH | Current usable capacity ÷ initial capacity | Augmentation/replacement |
| Response time / tracking error | Command to output, error band | Ancillary assessment |
| Station-service power rate | Station service ÷ grid-side charge | Auxiliary power cost |
| Unplanned outage | Count, duration, cause | Reliability |

### 7.2 Bidding and dispatch

- Day-ahead: declare the charge/discharge curve, reserve capacity and maintenance plan;
- Intraday: track AGC/AVC commands, keep SOC margin, avoid "empty/full" loss of regulation capability;
- Real-time: deviation assessment, power limits, charging limits at negative prices;
- Monthly: reconcile settled energy, assessment deductions and ancillary mileage;
- Annual: SOH, augmentation, capacity-price list review.

### 7.3 Assessment and deductions

| Assessment item | Common rule | Impact |
|---|---|---|
| Capacity-price availability | Monthly assessment; deduction in proportion to unavailable capacity | Direct deduction from capacity charge |
| Lease availability | Contractual; rent-free or compensation | Lower lease revenue |
| Frequency-regulation K factor | Response speed, tracking accuracy, energy neutrality | Discounted mileage payment |
| Reserve dispatch | Non-response / insufficient duration | Assessment, loss of eligibility |
| Spot deviation | Plan vs actual | Deviation settlement/penalty |
| Safety incident | Shutdown, rectification, penalty | Revenue to zero, asset loss |

### 7.4 Maintenance and safety

- BMS/PCS/EMS/SCADA layered with clear boundaries; EMS never directly operates BMS protection;
- Thermal-runaway prevention: cell monitoring, cluster-level isolation, explosion venting, fire linkage, combustible-gas detection;
- Maintenance: isolation, voltage verification, grounding, work permits; two-person review for battery-cluster work;
- Drills: fire, station blackout, communications loss, AGC disconnection;
- Standards: GB/T 42288-2022, GB/T 51048-2025, NFPA 855/UL 9540A (export projects).

### 7.5 Data and reporting

- Three metering levels: gateway meter, unit/PCS meter, auxiliary-system meter;
- Three ledgers: raw data, statistical reports, evaluation reports;
- Reconcile settlement data with operating data; every difference must be traceable to meters and periods;
- Assessment appeals need curves, commands, receipts and timestamps.

### 7.6 Operational anti-patterns

| Anti-pattern | Consequence | Correction |
|---|---|---|
| Watching revenue but not assessment | Clawed back at year-end | Monthly assessment ledger |
| Counting availability as "not broken" | Planned outages not deducted | Use the standard calibre |
| Filling all power with frequency regulation | No margin for arbitrage or reserve | Three-dimensional occupancy check |
| Charging raises demand | Basic charge rises instead | Charging power cap |
| Not re-verifying SOH | Overstated capacity declaration | Annual capacity calibration |
| No data trail | Cannot appeal an assessment | Raw curves + receipts |

---

## 8. Business models and contracts

### 8.1 Model comparison

| Model | Who funds | Revenue ownership | Main risk |
|---|---|---|---|
| Owner self-investment | Owner | All | Technology, policy, operations |
| EPC turnkey | Owner | All | Warranty boundary, performance guarantee |
| EMC energy management | Service provider | Shared savings | Baseline dispute, customer credit |
| Capacity leasing | Owner/lessee | Rent | Vacancy, default, price decline |
| Shared storage | Multiple parties | Lease + market | Dispatch rights, settlement allocation |
| Entrusted operations | Owner | All (pays a service fee) | Assessment, incentive incompatibility |

### 8.2 Capacity lease contract points

- Leased capacity (MW/MWh, AC/DC), price (CNY/kW-yr), term, start date;
- Availability assessment, rent-free conditions, deduction formula;
- Dispatch rights and priority: who prevails when leased capacity conflicts with own arbitrage;
- Price adjustment mechanism linked to capacity price, spot spread and market rules;
- Default, guarantee, early termination, dispute resolution;
- Renegotiation clauses if policy changes (list cancellation, capacity-price step-down).

### 8.3 Revenue sharing and floors

- Revenue floor: who backstops, how much, trigger conditions;
- Sharing ratio: on revenue or savings, pre-tax or post-tax;
- Metering and audit: mutually accepted metering points, data sharing, dispute handling;
- Incentive compatibility: operator assessment tied to owner revenue, avoiding "collect the floor and stop maintaining".

### 8.4 Insurance and force majeure

- Property all-risks, machinery breakdown, third-party liability;
- Fire/thermal-runaway special clauses, deductibles;
- Whether grid-connection delay, policy change and curtailment are force majeure;
- Whether business-interruption insurance covers assessment losses.

### 8.5 Exit and asset disposal

- Residual/second-hand equipment value, battery recycling cost;
- Remaining life after augmentation/retrofit;
- Demolition and restoration after land/roof lease expiry;
- Tax and debt assumptions in an equity transfer of the project company.

---

## 9. Risk: identify, quantify, mitigate

### 9.1 Price risk

- Fixed TOU exit and spread narrowing (Zhejiang -28.5%, Jiangsu -25%, grade B/C);
- Negative spot prices, weak spikes, captured spread below calendar spread;
- Rising charging cost, demand-price adjustment;
- Mitigation: multi-market stacking, contractually lock part of the spread, scenario modelling, shorten payback.

### 9.2 Policy risk

- Not on the capacity-price list, standard cut, tighter assessment;
- Ancillary rule changes, subsidy step-down;
- Retrofit caused by upgraded grid-connection/fire standards;
- Mitigation: write policy clauses into contracts, retain exit rights, diversify provinces.

### 9.3 Technical risk

- Faster-than-expected degradation, augmentation cost, outage loss;
- Thermal runaway, recall, fire;
- RTE and auxiliary power above the promised values;
- Mitigation: performance guarantees, warranties, insurance, online monitoring, acceptance tests.

### 9.4 Operational risk

- Availability below target, assessment deductions;
- SOC management errors, non-neutral frequency-regulation energy;
- Charging raising demand, misjudged peak/valley periods;
- Mitigation: monthly KPI review, AGC closed loop, demand interlock, staff training.

### 9.5 Financing risk

- Rising rates, insufficient DSCR, refinancing failure;
- Cash-flow/loan-tenor mismatch;
- Mitigation: fixed rate, longer tenor, reserve accounts, stress testing.

### 9.6 Contract risk

- Lease counterparty default, grid-connection delay, EPC performance shortfall;
- Dispatch-right disputes, unclear settlement allocation;
- Mitigation: guarantees, penalties, milestone payments, dispute-resolution clauses.

### 9.7 Risk matrix

| Risk | Probability | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Spread narrowing | High | High | Multi-market, contract lock-in, stress test | Investment |
| Not on capacity-price list | Medium | High | Pre-investment confirmation, policy tracking | Development |
| Degradation above plan | Medium | Medium | Warranty, augmentation budget, SOH monitoring | Technical |
| Availability assessment | Medium | Medium | Maintenance plan, spares, KPI | Operations |
| Lease default | Medium | High | Guarantee, tenant diversification | Commercial |
| Fire/safety | Low | Very high | Standard design, fire protection, insurance | Safety |
| Grid-connection delay | Medium | Medium | Milestones, penalties | Engineering |

### 9.8 Stress tests

Run at least four scenarios:

1. Spread -30%, cycles -20%;
2. Capacity price at zero / not on the list;
3. CAPEX +15%, COD delayed 6 months;
4. Availability 90%, degradation cost doubled.

If DSCR falls below 1.0 in any scenario, credit enhancement or structural adjustment is required; do not use the base-case IRR to persuade the investment committee.

---

## 10. Decision checklist and red flags

### 10.1 Twenty pre-investment questions

1. What are the project form and metering point?
2. Province, policy document number and validity?
3. Is it on the capacity-price list? Who files?
4. Which revenue items exist and what share does each take?
5. Is the spread fixed, agency-purchase or spot?
6. Who controls cycle count and dispatch rights?
7. Who is the capacity-lease counterparty and what is its credit?
8. Ancillary-service admission and assessment rules?
9. Approved demand value and actual maximum demand?
10. Does the charging window conflict with demand?
11. What does CAPEX include and exclude?
12. How are auxiliary power and line losses estimated?
13. Degradation and augmentation assumptions?
14. Warranty and performance-guarantee clauses?
15. Financing structure, rate and tenor?
16. What is DSCR under stress?
17. Which risks does insurance cover?
18. Are grid connection, fire safety and land secured?
19. Exit and residual-value assumptions?
20. Who bears the loss in the worst case?

### 10.2 Financial red flags

- Revenue exceeds the physical ceiling;
- High IRR but DSCR below 1.1;
- Capacity-price/lease revenue above 50% with no contractual backstop;
- Payback longer than the loan tenor;
- Residual value/augmentation assumptions clearly optimistic;
- Only one sensitivity case.

### 10.3 Technical red flags

- Cycle life quoted without RTE/availability/degradation curve;
- Warranty EOL inconsistent with the capacity-declaration calibre;
- Auxiliary power omitted;
- Fire-protection design non-compliant with standards;
- Grid performance (high/low voltage ride-through, primary frequency response) unverified.

### 10.4 Contract red flags

- Lease contract without availability assessment;
- Unclear dispatch-right ownership;
- No renegotiation clause for policy change;
- Penalty below the loss;
- Settlement metering point inconsistent with the assessment metering point.

### 10.5 Operational red flags

- Availability near 100% for a long time with no maintenance records;
- Frequency-regulation K factor steadily declining;
- SOC frequently hitting top or bottom;
- Demand rising month after month;
- Assessment deductions absent from monthly reports.

---

## 11. Key formulas and code mapping

| Formula | Code |
|---|---|
| Discharge/charge per cycle, arbitrage revenue | `stacking.arbitrage()` |
| Capacity price and duration conversion | `stacking.capacity_payment()` |
| Basic charge and peak-shaving savings | `stacking.demand_bill()` / `demand_savings()` |
| Frequency-regulation capacity + mileage | `stacking.frequency_regulation()` |
| Revenue stacking and haircut | `stacking.stack()` |
| NPV/IRR/payback | `finance.npv()` / `irr()` / `payback()` |
| LCOS | `finance.lcos()` |
| Cash flow and DSCR | `finance.annual_cashflow()` / `dscr()` |
| Equivalent cycles, SOH, augmentation | `degradation.equivalent_cycles()` / `linear_soh()` / `augmentation_energy()` |

```python
import stacking, finance

a = stacking.arbitrage(100, 2, 0.88, 1, 330, 250, 850, degradation_cost_per_kwh=0.03)
cap = stacking.capacity_payment(100, 165, 2, 6)
revenue = a["annual_net"] + cap["annual"]
flows = finance.annual_cashflow(revenue, 5_000_000, 200_000_000, 15, 0.25, 15)
print(round(finance.npv(0.08, flows)), round(finance.irr(flows) * 100, 2))
```

---

## 12. Glossary (Chinese-English)

| Chinese | English | Note |
|---|---|---|
| 独立储能 | independent storage | Grid side, independently connected, market-facing |
| 共享储能 | shared storage | Capacity leased to multiple parties |
| 新能源配储 | co-located storage | On the same site as wind/solar, meeting co-location/absorption |
| 用户侧储能 | behind-the-meter storage | Behind the meter, peak-valley + demand |
| 容量电价 | capacity price | Paid on available capacity |
| 容量租赁 | capacity leasing | Leasing the right to use capacity |
| 两部制 | two-part tariff | Basic charge + energy charge |
| 最大需量 | maximum demand | Billing demand |
| 核定值 | contracted demand | Contracted maximum demand |
| 往返效率 | round-trip efficiency | AC-AC |
| 可用系数 | availability factor | Operable time/statistical time |
| 等效利用系数 | utilization factor | Charge+discharge/rated power·time |
| 平准化储能成本 | LCOS | Lifecycle cost/discharged energy |
| 内部收益率 | IRR | Discount rate at NPV=0 |
| 偿债备付率 | DSCR | Cash flow/debt service |
| 增容 | augmentation | Adding battery capacity |
| 热失控 | thermal runaway | Safety risk |
| 辅助服务 | ancillary services | Frequency regulation/reserve/ramping |
| 调频里程 | regulation mileage | Actual regulation movement |
| K 值 | performance score | Frequency-regulation performance assessment |
| 捕获价差 | captured spread | Actual charge-discharge spread |
| 机会成本 | opportunity cost | Forgone alternative revenue |

---

## 13. Reference implementation and self-test

- Directory: `tools/`, standard library only, zero dependencies.
- Run:

```
python skills/storage-investment-operations/tools/selftest.py
```

- Assertion coverage:
  - Example A: 187.62/213.20 MWh per cycle, annual net arbitrage CNY 31.069 million, capacity charge CNY 5.5 million, NPV CNY 31.194 million, IRR 10.47%, payback 7.40 years, LCOS 742.24/458.15 CNY/MWh, DSCR 1.53;
  - Example B: annual revenue CNY 2.8 million, demand charge CNY 520,000 to 400,000/month, NPV CNY 2.595 million, IRR 12.59%, payback 5.52 years;
  - Example C: IRR 4.98%/0.26% and payback 10.4/14.7 years at CNY 0/150 per MWh charging opportunity cost;
  - Frequency regulation gross revenue CNY 15,900/day, CNY 5.247 million/year;
  - Equivalent cycles 325.9/year, 13.33 years to 80% SOH, augmentation 50 MWh.

> The tool is an **investment screening device**, not a settlement system: it does not handle provincial assessment rules, tax incentives, complex financing or hourly spot optimization. Formal investment decisions must be recomputed with provincial rules, measured curves and equipment quotes.

---

## 14. Expert reasoning handbook

> The five questions below cover the most common investment and operating disputes. Each is answered as "fix the calibre → list the formula → give the number → state the boundary", with no skipped steps.

### 14.1 "Can this 100 MW/200 MWh independent storage be invested in?"

Reasoning chain: (1) confirm capacity-price list eligibility and the provincial denominator duration; (2) compute arbitrage with captured spread, not calendar spread; (3) add the capacity charge and deduct availability; (4) compute NPV/IRR from total-investment cash flow, then equity IRR and DSCR from equity cash flow; (5) run four stress scenarios.

Conclusion template: base IRR 10.47% and DSCR 1.53, but with the capacity price at zero, NPV is -CNY 4.11 million and IRR 7.66%. The answer is therefore not "yes", but "**due diligence may proceed if list eligibility and the capacity price can be confirmed; otherwise reprice it as a pure-arbitrage project**".

### 14.2 "Our province cancelled the fixed peak-valley spread. Can the old model still be used?"

No. After Document 1656, direct market participants no longer have government-set time-of-use prices, so the fixed spread becomes a random variable. A 15-year fixed-spread model systematically overstates revenue.

Method: replay the province's historical 15-minute spot prices to obtain the distribution of captured spread; use P50 as the base case and P10 as the stress case; re-constrain cycle count by spread duration and SOC window; replace "two charge-two discharge" with the actual number of peak periods. The Zhejiang and Jiangsu narrowing figures are directional references only (grade B/C) and cannot be transplanted to other provinces.

### 14.3 "The co-located project has curtailment, so is it surely profitable?"

Not necessarily. Curtailment is only the upper bound of "movable energy"; revenue = movable energy × discharge price - opportunity cost - degradation cost. Example C shows IRR 4.98% at zero charging cost and 0.26% at CNY 150/MWh opportunity cost.

Ask three follow-ups: are curtailment hours stable, is there market demand at the discharge price, and does CAPEX already include grid connection and augmentation? If any one fails, co-located storage should not be treated as an independent revenue project.

### 14.4 "Frequency-regulation revenue is high. Can all the power be used for regulation?"

No. Frequency regulation occupies power, SOC margin and all-day response time, crowding out arbitrage and reserve. The CNY 5.247 million is gross revenue before energy cost, opportunity cost and assessment; if all 10 MW goes to regulation, evening-peak arbitrage capability is essentially gone.

Correct approach: first satisfy capacity-price availability and lease performance, then run the three-dimensional occupancy check, and finally apply a haircut with `stacking.stack()` rather than adding revenue items directly.

### 14.5 "Operating data looks normal. Why is money deducted at year-end?"

Four common causes: (1) availability counted as "not broken", with planned outages not deducted; (2) capacity declared at the initial value, so actual usable capacity is short after SOH declines; (3) the frequency-regulation K factor declined without review; (4) charging raised demand, so the basic charge rose instead.

Troubleshooting order: reconcile settled energy with the gateway meter, then check unplanned-outage records, then verify SOH and capacity declaration, and finally check the demand curve and charging window. An assessment appeal must carry raw curves, dispatch commands, receipts and timestamps.

---

## 14A. Overseas quick reference (Australia NEM / Germany DE-LU / UK GB / Italy / Spain / Netherlands / Poland / Belgium & Nordics / United States / Japan)

> Scope: revenue structure, access, grid fees and appraisal calibres for utility-scale and C&I storage in Australia, Germany, the UK, Italy, Spain, the Netherlands, Poland, Belgium/the Nordics, the United States (ERCOT/PJM/CAISO) and Japan only; do not transplant China's capacity price or peak-valley spread. Overseas figures cut off 2026-11-10; see the knowledge modules "Overseas storage business: ten markets", "UK electricity market", "Italy electricity market", "Spain electricity market", "Netherlands electricity market", "Poland electricity market", "Belgium and the Nordics electricity market", "US electricity market" and "Japan electricity market" for rule detail.

### 14A.1 Market cards: six core markets

| Dimension | Australia NEM | Germany DE-LU | UK GB | Italy | Spain | Netherlands |
|---|---|---|---|---|---|---|
| Utility-scale revenue | Energy arbitrage + FCAS + CIS | Arbitrage + FCR/aFRR/mFRR + grid-fee exemption | Arbitrage + BM + capacity market + frequency/ancillary | Arbitrage + MSD/MB + capacity market + MACSE | Arbitrage + aFRR/mFRR + capacity market (first auction pending) + grants | Arbitrage + FCR/aFRR/mFRR + congestion contracts |
| C&I revenue | Demand charges + spread + self-consumption | Demand charges + §14a + dynamic tariffs | Demand charges + time-of-use spread + DFS + aggregated BM/CM | Demand management + time-of-use spread + self-consumption | Demand charges + time-of-use spread + self-consumption + flexible access | Demand charges + time-of-use spread + self-consumption + congestion/non-firm |
| Capacity mechanism | None; CIS revenue support | None; StromVKG from 2031 | T-4/T-1, £/kW·yr; batteries de-rated | Capacity market + MACSE (15 years) | 2026 capacity market, peninsular system, firm power, pay-as-bid | None (studied, not implemented) |
| Settlement granularity | 5 minutes | 15-minute MTU in DA/ID | Half-hourly; EPEX GB hourly + GB-30min | MGP 15-minute MTU; MSD/MB layers | 15 minutes (DA/ID/imbalance) | 15-minute MTU; 15-minute imbalance |
| Connection | NSP connection + AEMO registration + MASS | VDE-AR-N + MaStR + unit certificate | NESO/DNO connection + BSC/BMU + CM prequalification + TMO4+ | Terna/GME registration + connection agreement + permitting | REE/DSO connection + permitting/EIA + grid-forming + agreement | TenneT/DSO connection + non-firm/ATR85 + permitting |
| Key policy date | CIS Tender 8 COD by 2029-12-31 | §118(6) commissioning 2029-08-04 | LDES minded-to 2026-06-26, final parameters autumn 2026 | MACSE second auction 2026-11-24; FER X in force | RD 997/2025 and RDL 7/2026 in force; first capacity auction pending | Energiewet 2026-01-01; priority framework 2026-07-01; net metering ends 2027-01-01 |

**14A.1b New market cards (Poland / Belgium / Nordics)**

| Dimension | Poland | Belgium | Nordics |
|---|---|---|---|
| Utility-scale revenue | Capacity market + arbitrage + FCR/aFRR/mFRR + NFOŚiGW CAPEX | CRM + arbitrage + FCR/aFRR/mFRR | Arbitrage + ancillary + reserves (no capacity market) |
| C&I revenue | Demand charges + spread + self-consumption + capacity-fee optimisation | Demand charges + time-of-use spread + self-consumption | Demand charges + time-of-use spread + self-consumption + zonal spreads |
| Capacity mechanism | rynek mocy; 2030 delivery year PLN 465.02/kW·yr; de-rating around 13% (C) | CRM Y-4/Y-2/Y-1; Y-4 cleared 4,690 MW; new build up to 15 years | Sweden effektreserv, Finland tehoreservi; no capacity market in Norway/Denmark |
| Settlement granularity | 15-minute MTU; 15-minute imbalance | 15-minute MTU; 15-minute imbalance | 15-minute MTU; 15-minute imbalance + mFRR EAM since 2025-03-04 |
| Connection | PSE/OSD connection + URE licence + capacity registration | Elia connection + permitting + CRM qualification | National TSO/DSO connection + permitting + prequalification |
| Key policy date | 2030 capacity auction ended (round 2); 2026 OZE auctions 76.1 TWh | 2025 Y-4/Y-2/Y-1 results; nuclear extension to 2035 | 2025-03-04 imbalance reform; 2025-10-01 15-minute MTU; effektreserv auction failed 2025-10-07 |

**14A.1c United States and Japan cards**

| Dimension | ERCOT | PJM | CAISO | Japan |
|---|---|---|---|---|
| Utility-scale revenue | Arbitrage + Reg/RRS/ECRS | Capacity + arbitrage + ancillary | Arbitrage + RA + FRP | Spot + EPRX + capacity + LTDA |
| C&I revenue | Demand charges + spread + self-consumption | Demand charges + spread + aggregated capacity/ancillary | Demand charges + spread + RA/FRP | Demand charges + spread + self-consumption + EPRX |
| Capacity mechanism | None; ORDC scarcity pricing | BRA/FRR; ELCC de-rating; 2028/29 capped at $325/MW-day | No central capacity auction; RA slice-of-day | Capacity market (4 years ahead, single price, 1 year) + LTDA (20 years) |
| Spot and settlement | 5-minute dispatch, 15-minute settlement; HCAP/LCAP $5,000/$2,000 per MWh | By product (hourly/5-minute); energy per tariff | Day-ahead + 15-minute FMM + 5-minute RTD; 5-minute settlement | JEPX 48 half-hour products; 30-minute settlement; no negative prices |
| Balancing/ancillary | Reg/RRS/ECRS; RTC+B live 2025-12-05 | Frequency/reserve by product; capacity performance penalties | FRP (up/down); monthly RA showing | EPRX 5 products + combined; cap ¥10.00/ΔkW·30min |
| Connection | ERCOT interconnection queue + state/local permits | Queue about 40 months + state permits | Cluster queue about 197 GW + CPUC/CEC | OCCTO connection studies 24,880 in FY2025 + per-applicant caps |
| Key policy date | RTC+B 2025-12-05; Section 301 at 25% from 2026-01-01 | 2028/29 BRA cleared 2026-07-14; FEOC for construction after 2025-12-31 | EDAM 2026-05-01; RA 2026 compliance year | C value 2026-10-01; EPRX cap 2026-09-01; LTDA round 3 2026-05-13 |

### 14A.2 Five points for Australia

1. **Revenue = arbitrage + FCAS + CIS**: no capacity market; CIS is a competitive revenue support, not a per-MW subsidy.
2. **Arbitrage**: `margin = discharge × discharge price − charge × charge price`, with `charge = discharge ÷ RTE`; then deduct degradation and network charges.
3. **5-minute settlement + regional prices + MLF**: settled energy is adjusted by the marginal loss factor; MLF changes annually, so backtests must be split by year.
4. **10 FCAS markets** (8 contingency + 2 regulation); very fast 1-second FCAS started 2023-10-09; FCAS competes with arbitrage for MW and SOC.
5. **Registration and connection**: storage can register as an IRP, Generator or Market Customer; NSP connection, AEMO registration, MASS testing and SCADA are all required.

### 14A.3 Six points for Germany

1. **Revenue = DA/ID arbitrage + FCR/aFRR/mFRR + grid-fee exemption**; a capacity market only from 2031.
2. **15-minute MTU** since 2025-10-01; DA gate 12:00 CET, pay-as-clear; ID pay-as-bid; SDAC floor −€500/MWh vs. SIDC floor −€9,999/MWh.
3. **Balancing**: FCR is symmetric and capacity-only; aFRR/mFRR tender capacity and energy separately; minimum bid at the 1 MW level; prequalification required.
4. **§118(6)**: 20-year grid-fee exemption for storage commissioned by 2029-08-04; AgNes plans a final determination on 2027-01-01 and capacity-based grid fees from 2029 (about €4–7/kW/year for utility-scale storage), final design pending.
5. **§14a applies only to LV controllable loads** (>4.2 kW); module 2 gives a 60% grid-fee reduction; it is neither a utility-scale rule nor an unconditional subsidy.
6. **StromVKG capacity market**: delivery from 2031, EU approval 2026-09-02; the two 2026 auctions are reportedly not open to battery storage, while the 2027 new-capacity tender is open to storage (≥10 hours), so do not book the revenue yet.

### 14A.4 Five points for the UK

1. **Revenue = arbitrage + BM + capacity market + frequency/ancillary services**: GB does not take part in EU coupling; cross-border volumes trade through explicit capacity auctions and day-ahead prices form domestically.
2. **The BM is pay-as-bid**: NESO accepts bids/offers for system needs and BOALF is the settlement basis; expensive offers get skipped (a reported skip rate around 38% in 2026), so do not assume every offer is accepted.
3. **The capacity market pays on de-rated capacity**: T-4 2029/30 cleared at £27.10/kW·yr for 40.1 GW; T-1 2026/27 at £5.00/kW·yr for 7,192 MW; cap £75/kW·yr. T-1 can be very low, so do not extrapolate high years.
4. **Support tools are layered**: standalone storage generally does not take standard CfD; co-located storage needs separate metering/BMU registration; LDES uses cap and floor (minded-to on 2026-06-26 covered 16 projects, 7,645 MW; final parameters autumn 2026); TMO4+ grid reform emphasises "ready + needed".
5. **Access and connection**: Ofgem licence/exemption + BSC + BMU + CM prequalification; distribution connections follow G99/G100, and behind-the-meter projects still need DNO connection and fire compliance; MHHS migration affects half-hourly settlement.

### 14A.5 Five points for Italy

1. **Revenue = arbitrage + MSD/MB + capacity market + MACSE**: MACSE is a storage-specific long-term capacity premium, not energy revenue and not a substitute for arbitrage.
2. **Seven bidding zones, not one price**: Nord, Centro-Nord, Centro-Sud, Sud, Calabria, Sicilia, Sardegna; PUN is a reference price, not a project's settlement price. MGP closes 12:00 D-1, is SDAC-coupled and uses 15-minute MTU from 2025-10-01.
3. **MSD/MB are Terna's dispatch procurement**: frequency, reserve and congestion services; BSPs need prequalification, and settlement differs from MGP, so MGP prices cannot be applied directly to MSD.
4. **MACSE pays in €/MWh·yr for 15 years**: pay-as-bid, zonal auctions, new-build only; the first auction cleared 10 GWh at an average €12,959/MWh·yr; the second offers 16 GWh on 2026-11-24; the battery cap is €37,000/MWh·yr. The first-auction price is not a guaranteed repeat.
5. **Capacity market and FER X are two other tracks**: the capacity market pays for available capacity; FER X is a 20-year two-way CfD (DM 194/2026, 37.15 GW, €80/MWh reference), with NZIA-specific auctions imposing supply-chain conditions on PV above 1 MW. Storage can stack the capacity market, but obligations must be assessed separately.

### 14A.6 Five points for Spain

1. **Revenue = arbitrage + aFRR/mFRR + capacity market (first auction pending) + grants**: the capacity market only arrived in 2026, and auction prices/obligations are unknown; PERTE/ERDF grants are project capex support, not long-term revenue.
2. **Fifteen minutes runs through trading and settlement**: 15-minute MTU in day-ahead/intraday since 2025-10-01; 15-minute imbalance settlement since 2024-12-01; hourly models misprice both arbitrage and deviation.
3. **Know the price bounds**: day-ahead -€600/+€4,000 per MWh; intraday continuous ±€9,999; negative prices are common in solar-heavy hours (about 555 hours in 2025, grade C).
4. **Capacity market design**: Orden TED/966/2026, in force 2026-09-18; peninsular system, firm power, sealed-bid pay-as-bid; new-build main auctions up to 15 years; existing generation subject to a 550 g CO2/kWh gate; first auction date to be confirmed by REE (public reports point to late 2026 to 2027, grade C).
5. **Connection/grid-forming is a hard gate**: PNIEC targets 22.5 GW by 2030 (all technologies); RD 997/2025 requires grid-forming and 120%–130% voltage ride-through; RDL 7/2026 introduces flexible access and a 10% self-consumption reserve; pipeline around 24.3 GW permitted + 15.1 GW pending (grade C, January 2026), but permitting/connection conversion is the bottleneck.

### 14A.7 Five points for the Netherlands

1. **Revenue = arbitrage + FCR/aFRR/mFRR + congestion contracts**: there is no capacity market, so merchant risk is higher than in the UK, Italy or Spain; congestion contracts are locational rent, not a standard annuity.
2. **Separate bidding zone + 15 minutes**: EPEX NL is not part of DE-LU; 15-minute MTU in day-ahead/intraday since 2025-10-01, with 15-minute imbalance settlement.
3. **The connection queue is harder than the price**: about 15,000 businesses waiting for grid access (grade C); ATR85 non-firm contracts trade curtailment for earlier connection (about 9 GW offered in 2025); the priority framework took effect on 2026-07-01; TenneT introduced time-of-use grid fees from 2025.
4. **SDE++ is not a battery subsidy**: the 2026 budget is €8bn with a window of 2026-10-27 to 2026-11-26, but the RVO page does not list batteries as a standalone category; net metering ends on 2027-01-01.
5. **Small base, changing ancillary rules**: 350 MW/620 MWh of large-scale batteries at end-2024 (CBS), about 3 GWh total at end-2025, and TenneT expects about 4 GW by 2030 (grade B); aFRR uses dynamic dimensioning from September 2025, with 10% of volumes on 4-hour contracts from November 2025 (grade B).

### 14A.8 Five points for Poland

1. **Revenue = capacity market + arbitrage + ancillary + grants**: the capacity market is the first driver; storage awards rose from 165 MW in 2022 to 2.5 GW in 2024, then fell to about 685 MW for the 2030 delivery year after the de-rating change (grade C). Arbitrage alone rarely carries the investment case.
2. **Capacity revenue uses de-rated capacity**: the 2030 Polish price is PLN 465.02/kW·yr; battery de-rating is about 13% (grade C), so 100 MW nameplate counts as roughly 13 MW; the GP BESS example has a 17-year contract, but not every unit gets 17 years. Availability tests and grant deductions reduce actual revenue.
3. **NFOŚiGW grants are CAPEX support**: the total budget is PLN 4.15bn (PLN 3.735bn grants + PLN 0.415bn loans) for 172 projects, about 3.9 GW/14.5 GWh, targeted for completion by end-2028; stacking with capacity revenue triggers a deduction under Article 62 of the Capacity Market Act (grades B/C). It is not annual operating revenue.
4. **Fifteen minutes and negative prices**: 15-minute MTU in day-ahead/intraday since 2025-10-01; a −PLN 791.32/MWh price lasted about 10 hours on 2026-04-06 (grade C); hourly models misstate both arbitrage and capacity obligations.
5. **Connection, licensing and capacity registration are hard gates**: PSE/OSD connection queue, URE koncesja, TGE/IRGiT membership, POB balancing responsibility, PSE ancillary prequalification and capacity-market qualification are separate processes; a connection is not a capacity contract.

**Three formulas**

```
Capacity revenue = de-rated capacity (MW) × clearing price (PLN/kW·yr) × 1000
Arbitrage gross margin = (discharge price − charge price ÷ RTE) × discharge energy
Post-grant CAPEX = CAPEX − eligible cost × grant rate
```

### 14A.9 Five points for Belgium and the Nordics

1. **Belgium relies on CRM annuities**: Y-4/Y-2/Y-1 auctions, pay-as-bid with an intermediate price cap; new build up to 15 years. The 2025 Y-4 auction cleared 4,690 MW, including 179 MW of new batteries (525 MW nameplate), at a price in the ~€27k/MW·yr range (grade C, unit needs verification); CRM pays on de-rated capacity, not nameplate.
2. **Belgium's capacity gap is changing**: Doel 4/Tihange 3 are extended to 2035 and the phase-out law was repealed in May 2025; offshore wind targets 5.8 GW by 2030. New storage was 491 MWh in 2024, CRM has contracted about 1.6 GW of new batteries, and the 2030 storage target is about 3.6 GW (grade C). Use the latest gap, not the old "2025 nuclear exit" assumption.
3. **The Nordics are 12 bidding zones**: NO1–NO5, SE1–SE4, DK1–DK2 and FI; projects settle at the zonal price, the system price is reference only; hydro flexibility shapes the spreads, and EPADs hedge zonal differences but are not physical contracts.
4. **Nordic reserves are not a capacity market**: Sweden's effektreserv targets 800 MW and its 2025-10-07 auction failed because bids exceeded the SEK 120,000/MW cap; Finland has tehoreservi; Norway and Denmark have no national capacity market. Storage cannot treat reserves as a long-term annuity.
5. **Fifteen-minute imbalance changes revenue**: 15-minute imbalance and mFRR EAM since 2025-03-04; the share of hours where imbalance equals day-ahead fell from about 33% to about 3%, and balancing costs rose from about €1 to €5–6/MWh (grades B/C); PICASSO is live in Denmark (2024-10) and Finland (2025-03), with Sweden/Norway later. Licensing, BRP registration and ancillary prequalification differ across the four countries.

**Three formulas**

```
CRM revenue = de-rated capacity (MW) × clearing price (€/MW·yr)
Zonal arbitrage = (zonal discharge price − zonal charge price ÷ RTE) × discharge energy
Reserve revenue = awarded capacity (MW) × reserve price (local currency/MW·season)
```

### 14A.9b Five points for the United States (three markets)

1. **Three markets, three logics**: ERCOT is energy-only with ORDC scarcity pricing; PJM runs on a capacity market (BRA/ELCC); CAISO runs on day-ahead/real-time plus RA. One revenue model cannot be transplanted across the three.
2. **ERCOT settles every 15 minutes**: real-time SCED every 5 minutes, settlement every 15 minutes; HCAP/LCAP $5,000/$2,000 per MWh; RTC+B went live on 2025-12-05, co-optimising real-time energy and ancillary services and modelling SOC; 15,008 MW of batteries in operation (2025-09, grade B).
3. **PJM capacity revenue is ELCC-de-rated**: the 2028/29 BRA cleared at $325/MW-day (the new cap), 152.1 GW cleared against a 6.8 GW gap and a 14.7% reserve margin, with only about 525 MW of new effective capacity; a 4-hour battery has an ELCC of about 50% and capacity revenue of roughly $60k/MW-yr (order of magnitude). A capped price is not a bankable price, and performance penalties still apply.
4. **CAISO layers RA and FRP**: day-ahead + 15-minute FMM + 5-minute RTD; RA moves to full slice-of-day compliance from the 2026 compliance year; EDAM went live on 2026-05-01; storage exceeds 21 GW and negative prices cluster in midday solar hours, pushing the arbitrage window later.
5. **Interconnection and supply chain are hard gates**: PJM's first 2026-08 cycle includes 715 projects/201.5 GW with a study cycle of about 40 months; the CAISO queue is about 197 GW; ITC is 30% plus 10% domestic content plus 10% energy community; FEOC rules apply to projects starting construction after 2025-12-31; Section 301 tariffs rise to 25% from 2026-01-01; fire compliance follows UL 9540/NFPA 855 and interconnection IEEE 1547.

**Three formulas**

```
PJM capacity revenue ≈ ELCC (MW) × clearing price ($/MW-day) × 365
ERCOT arbitrage gross revenue ≈ discharged energy (MWh) × spread ($/MWh) × RTE × cycles
CAISO RA revenue ≈ NQC (MW) × capacity price ($/kW-yr) × 1000
```

### 14A.9c Five points for Japan

1. **Revenue = spot + EPRX + capacity market + LTDA**: JEPX day-ahead has 48 half-hour products, a 10:00 gate and a blind single-price auction; the floor is ¥0.01/kWh and there are **no negative prices**, so applying European negative-price models overstates charging revenue.
2. **The capacity market pays on de-rated capacity**: four years ahead, single price, one-year contracts; round 5 (FY2028) cleared ¥11,134/kW and round 6 (FY2029) ¥13,303/kW; historical average prices have ranged from ¥3,109 to ¥14,137/kW, so a single result cannot be extrapolated.
3. **LTDA is 20-year revenue with clawback and a duration threshold**: pay-as-bid with about 90% of other market revenue clawed back ex post; from round 3 batteries under 6 hours are no longer eligible; round 3 awarded 1,251 MW/19 battery projects at a 36% award rate (grade C). LTDA revenue cannot simply be added to spot/EPRX revenue.
4. **Imbalance costs are high**: 30-minute settlement; from 2026-10-01 the C value rises from ¥200 to ¥300/kWh and the D value from ¥45 to ¥50/kWh (grade C); deviation costs can exceed arbitrage margin, so intraday rolling forecasts are mandatory. The EPRX cap fell to ¥10.00/ΔkW·30min on 2026-09-01, so a ΔkW-only model no longer works.
5. **Grid queueing and foreign-investment review are hard gates**: storage connection-study applications reached 24,880 in FY2025; from 2026-08-01 each applicant is capped — Tokyo 11, Kansai 12, Kyushu 8; general transmission/distribution, transmission and generation of 50 MW or more are core sectors under FEFTA, requiring prior notification with a 30-day to 5-month review.

**Three formulas**

```
Capacity market revenue ≈ de-rated capacity (kW) × clearing price (¥/kW-yr)
LTDA net revenue ≈ LTDA capacity revenue + other market revenue × (1 − 90%)
EPRX revenue ≈ Σ ΔkW × unit price (¥/ΔkW·30min) + dispatched energy × kWh price
```

### 14A.10 Same question, ten answers

| Question | Australia NEM | Germany DE-LU | UK GB | Italy | Spain | Netherlands |
|---|---|---|---|---|---|---|
| How does a 100 MW/200 MWh project recover its investment? | Arbitrage + FCAS + CIS | Arbitrage + balancing + grid-fee exemption | Arbitrage + BM + capacity market + ancillary | Arbitrage + MSD/MB + capacity market + MACSE | Arbitrage + ancillary + capacity market (first auction pending) + grants | Arbitrage + FCR/aFRR/mFRR + congestion contracts |
| Is there a capacity price? | No; CIS revenue support | No; capacity market from 2031 | Yes; T-4/T-1, de-rated | Yes; capacity market + MACSE | Yes; 2026 mechanism, peninsular system | No; studied but not implemented |
| Largest C&I revenue item | Demand charges + spread | Demand charges + §14a + dynamic tariffs | Demand charges + time-of-use spread + DFS | Demand management + time-of-use spread | Demand charges + time-of-use spread + flexible access | Demand charges + time-of-use spread + congestion/non-firm |
| Connection bottleneck | NSP queue, MASS testing | VDE-AR-N certification, unit certificate | Grid queue, TMO4+, G99/G100 | South/island queues, permitting and reinforcement | Permitting/EIA, grid-forming, connection capacity | Connection queue, non-firm access, congestion |
| Key policy deadline | CIS COD 2029-12-31 | §118(6) commissioning 2029-08-04 | LDES final parameters autumn 2026 | MACSE second auction 2026-11-24 | First capacity auction pending; RD/RDL in force | Energiewet 2026-01-01; net metering 2027-01-01 |

**New markets: the same questions**

| Question | Poland | Belgium | Nordics |
|---|---|---|---|
| How does a 100 MW/200 MWh project recover its investment? | Capacity market + arbitrage + ancillary + NFOŚiGW CAPEX | CRM + arbitrage + FCR/aFRR/mFRR | Arbitrage + ancillary + reserves (no capacity market) |
| Is there a capacity price? | Yes; rynek mocy, on de-rated capacity | Yes; CRM Y-4/Y-2/Y-1, on de-rated capacity | No national capacity market; Sweden/Finland have peak reserves |
| Largest C&I revenue item | Demand charges + spread + capacity-fee optimisation | Demand charges + time-of-use spread | Demand charges + time-of-use spread + zonal spreads |
| Connection bottleneck | PSE/OSD queue, URE licence, capacity registration | Elia connection/permitting, CRM qualification | National TSO/DSO connection, four-country rule differences |
| Key policy deadline | 2030 capacity auction ended; 2026 OZE auctions 76.1 TWh | 2025 CRM results; nuclear extension to 2035 | 2025-03-04 imbalance reform; 2025-10-01 15-minute MTU |

**United States and Japan: the same questions**

| Question | ERCOT | PJM | CAISO | Japan |
|---|---|---|---|---|
| How does a 100 MW/200 MWh project recover its investment? | Arbitrage + Reg/RRS/ECRS | Capacity + arbitrage + ancillary | Arbitrage + RA + FRP | Spot + EPRX + capacity + LTDA |
| Is there a capacity price? | No; ORDC scarcity pricing | Yes; BRA/FRR, ELCC de-rated | No central auction; RA slice-of-day | Yes; capacity market + LTDA |
| Largest C&I revenue item | Demand charges + spread + self-consumption | Demand charges + spread + aggregated capacity/ancillary | Demand charges + spread + RA/FRP | Demand charges + spread + self-consumption + EPRX |
| Connection bottleneck | ERCOT queue, state/local permits | About 40-month queue, state permits, co-location rules | Cluster queue, CPUC/CEC | Connection-study queue, per-applicant caps, FEFTA |
| Key policy deadline | RTC+B 2025-12-05; Section 301 2026-01-01 | 2028/29 BRA cleared; FEOC 2025-12-31 | EDAM 2026-05-01; RA 2026 compliance year | C value 2026-10-01; LTDA round 3 2026-05-13 |

### 14A.11 Answer discipline

- First ask which quadrant (Australia/Germany/UK/Italy/Spain/Netherlands/Poland/Belgium-Nordics/US/Japan × utility-scale/C&I), then give the revenue stack; do not apply utility-scale FCAS, balancing, BM, MACSE or capacity revenue to C&I. For the US ask ERCOT/PJM/CAISO first; for Japan ask the supply area and JEPX product first.
- Every revenue figure needs currency, year, price scenario and whether grid fees are included; label synthetic examples as grade D and not investment advice.
- Use A$ for Australia, € for Germany/Italy/Spain/Netherlands/Belgium, £ for the UK, PLN for Poland, SEK/NOK/DKK for the Nordics, USD for the US (note the $/MW-day and $/kW-yr conventions) and JPY for Japan (¥/kWh and ¥/kW-yr); do not mix currencies or present a "unified IRR".
- State policy timing precisely: CIS round and COD, §118(6) commissioning deadline, AgNes effect date, UK LDES final parameters, Italian MACSE round and delivery year, Spain's first capacity auction and RD 997/2025 implementation, the Dutch Energiewet/priority framework/net-metering dates, Poland's capacity/OZE auctions and NFOŚiGW progress, Belgian CRM rounds/nuclear extension, the Nordic imbalance reform/effektreserv, US BRA/ELCC/ITC/FEOC/tariffs, and Japan's capacity market/LTDA rounds/EPRX cap/C value.
- Do not call IESS a registration category; the correct category is IRP (final rule 2021-12-02, effective 2024-06-03). Do not call §14a a utility-scale rule or the 2031 capacity market a secured revenue stream; do not read MACSE €/MWh·yr as €/MW·yr; do not treat PUN as a settlement price.
- Spain: do not treat MIBEL as one bidding zone; do not treat the first capacity auction as priced; do not treat grid-forming/permitting as a formality.
- Netherlands: do not treat EPEX NL as DE-LU; do not assume a capacity market; do not treat SDE++ as a standalone battery subsidy; do not treat non-firm access as firm.
- Poland: do not treat the capacity price as €/kW·yr; do not use nameplate capacity for de-rated revenue; do not treat NFOŚiGW grants as annual revenue; do not assume MARI is live.
- Belgium/Nordics: do not treat CRM as a uniform clearing price; do not use nameplate capacity for CRM; do not treat Nord Pool as one zone; do not treat effektreserv/tehoreservi as a capacity market; do not treat the four countries as one rule set.
- United States: do not treat ERCOT as having a capacity market; do not treat the PJM cap as bankable; do not use nameplate capacity for capacity revenue (use ELCC/NQC); do not treat 2022–2023 ancillary revenue as normal; do not ignore FEOC/Section 301.
- Japan: do not apply European negative-price models; do not hard-code the spot cap; do not underestimate C-value deviation costs; do not bid 4-hour projects into LTDA; do not extrapolate one capacity-market price; do not ignore the per-applicant connection-study cap or FEFTA.

---

## 15. Sources, maintenance and division of labour

### 15.1 Methods and standards sources

- Policy: NDRC Price Document [2026] No. 114, NDRC Energy Regulation [2025] No. 1656, NDRC Energy Regulation [2025] No. 411, NDRC Price Document [2025] No. 136, NDRC Office Price Document [2016] No. 1583, NDRC Price Document [2018] No. 500;
- Standards: GB/T 36549-2018, GB/T 36547-2024, GB/T 36558-2023, GB/T 42288-2022, GB/T 51048-2025;
- Methods: general financial methods for LCOS/NPV/IRR/DSCR; Lazard LCOS, NREL ATB and IEC 62933 as international references (grade B);
- Industry data: CEC operating statistics, public tender and award notices (grade B);
- Overseas rules: AEMC/AEMO/AER (Australia NEM), EPEX/BNetzA/EnWG/regelleistung.net (Germany), NESO/Ofgem/Elexon (UK GB), GME/Terna/ARERA (Italy), OMIE/REE/CNMC (Spain), EPEX NL/TenneT/ACM (Netherlands), detailed in the respective storage and market modules (grades A/B).

### 15.2 Data and verification entry points

- Price Department of the NDRC, Policy and Law Department of the National Energy Administration;
- Provincial development and reform commissions / energy bureaus price documents;
- Electricity trading centre information disclosure;
- National Standards Information Public Service Platform;
- China Tendering and Bidding Public Service Platform.

### 15.3 Maintenance artefacts

- [Storage investment and operations note](../../knowledge/储能投资与运营-2026-11.md): policy milestones, cost ranges, indicator calibres, open items;
- [Overseas storage business](../../knowledge/海外储能业务-2026-11.md): revenue, access, connection and appraisal calibres across Australia, Germany, the UK, Italy, Spain, the Netherlands, Poland, Belgium/the Nordics, the United States and Japan;
- [UK electricity market](../../knowledge/英国电力市场-2026-11.md): GB single market, BM/BOALF, T-4/T-1 capacity market, LDES and grid reform;
- [Italy electricity market](../../knowledge/意大利电力市场-2026-11.md): seven bidding zones, MGP/MSD, MACSE storage auctions, capacity market and FER X;
- [Spain electricity market](../../knowledge/西班牙电力市场-2026-11.md): MIBEL two zones, OMIE 15 minutes, TED/966/2026 capacity market, storage connection and grid-forming;
- [Netherlands electricity market](../../knowledge/荷兰电力市场-2026-11.md): EPEX NL, no capacity market, 15-minute settlement, SDE++ and connection congestion;
- [US electricity market](../../knowledge/美国电力市场-2026-11.md): ERCOT/PJM/CAISO designs, ELCC/RA, interconnection and ITC/FEOC;
- [Japan electricity market](../../knowledge/日本电力市场-2026-11.md): JEPX 30-minute spot, capacity market, EPRX, LTDA and connection studies;
- [Storage EMS optimization](../../knowledge/储能EMS优化调度-算法与工程-2026-11.md): dispatch algorithms and operating constraints;
- [Microgrid EMS optimization](../../knowledge/微网EMS优化调度-算法与工程-2026-11.md): microgrid grid-connected/islanded operation;
- [Cross-border grid connection and compliance](../../knowledge/海外并网与合规-2026-11.md): grid codes, IEC/UL certification, fire, NIS2, Battery Regulation/passport, NZIA, FDI screening;
- [Capacity mechanisms side by side](../../knowledge/容量机制横向对照-2026-11.md): capacity revenue calibres for CM/MACSE/TED-966/rynek mocy/CRM/StromVKG/CIS/PJM/CAISO/Japan CM/LTDA;
- [Ancillary and balancing markets side by side](../../knowledge/辅助服务与平衡市场对照-2026-11.md): FCR/aFRR/mFRR, FCAS, BM, MSD/MB, EPRX eligibility, settlement and storage opportunity cost;
- [Storage revenue modelling and data sources](../../knowledge/储能收益建模与数据源-2026-11.md): public data, granularity/time zones, RTE/degradation, capture rate, de-rating, revenue stacking and backtest;
- [Cross-border PPAs and green certificates](../../knowledge/跨国PPA与绿证-2026-11.md): PPA/CfD/tolling structures, GO/REGO/REC/LGC/GEC, merchant tail and 24/7 matching;
- [Ten-market same-caliber snapshot and decision calendar](../../knowledge/海外市场同口径快照与投决日历-2026-11.md): seven columns across ten markets (installed capacity, storage, average price, negative-price hours, capture rate, interconnection queue, de-rating), 2026Q4–2027 event calendar, China-entry checklist and grade-C verification list; check comparability before project-level modelling.

### 15.4 Division of labour with sister skills

| Skill | Responsible for | How this skill references it |
|---|---|---|
| Electricity Trading Expert | Market rules, settlement, capacity-price policy | Cite document numbers and rules without re-explaining |
| Spot-Bidding Quant Expert | Price forecasting, bidding, backtests | Use forecast outputs without rewriting models |
| Virtual Power Plant Expert | Aggregation, demand-response operations | Use aggregation capability without repeating organization plans |
| Carbon Asset Management Expert | Carbon compliance, CCER, CBAM | Not covered here |
| Storage EMS note | SOC/reserve/degradation/AGC | Use dispatch models without repeating MILP |

### 15.5 Maintenance cadence

- Quarterly: provincial capacity prices, time-of-use prices, ancillary-service rules; Australian CIS rounds/FCAS prices, German balancing/AgNes/capacity-market progress, UK CM auctions/LDES/TMO4+, Italian MACSE rounds/capacity market/FER X, Spain's first capacity auction/RD 997 implementation/storage connection, Dutch aFRR contracts/priority framework/SDE++, US BRA/ELCC/ITC/FEOC/tariffs, and Japan's capacity market/LTDA rounds/EPRX cap/connection studies;
- Semi-annual: cost ranges, equipment prices, warranty terms;
- Annual: standards updates, operating indicators, worked-example regression;
- Trigger-based: within one month of a major policy release (for example, provincial rules under Document 114, retail pass-through of Document 1656).
