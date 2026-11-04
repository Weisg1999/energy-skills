---
name: carbon-asset-expert
description: Carbon asset management expert — national ETS compliance calendars, allowance gap modelling, CCER project development and economics, carbon finance (pledge, repo, forwards, guarantees, carbon-data credit enhancement), carbon price scenarios, product carbon footprints and carbon-neutrality claims (ISO 14067/ISO 14068), supply-chain carbon data, digital product passports (DPP), cross-border carbon data and CBAM response. Use when answering when to comply, how large the gap is, whether a CCER project is worth developing, how to calculate a product footprint, whether a carbon-neutrality claim is defensible, how carbon data may leave China, how to finance or hedge, or what carbon cost an exporter faces. Includes a zero-dependency Python reference implementation.
---

# Carbon Asset Management Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) ｜ Sister skills: [Electricity Trading Expert](../electricity-trading-expert/SKILL_EN.md) (market rules / settlement / carbon overview), [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation / operations), [Spot-Bidding Quant Expert](../spot-bidding-quant/SKILL_EN.md) (price forecasting / bidding). This skill answers only "how to comply, how to model, how to finance and hedge".

> Version v1.5 · data cutoff 2026-11-01

> **Maintenance entry points**: `tools/selftest.py` (green means the worked examples still hold), `knowledge/碳资产实务-2026-11.md` (compliance parameters and instrument status), `knowledge/调研-碳管理与碳足迹厂商-2026-11.md` (public information on Carbon Newture and peers, grades B/C), `knowledge/调研-碳市场与CBAM-2026-10增量.md` (2026 fact-update working note).
> **Open items 2026-2027**: formal inclusion dates for the 2027 expansion, the paid-allocation ratio and timetable, CBAM certificate purchase details, carbon futures listing (still **not listed as of 2026-11**), and the final benchmarks in the annual allocation plan.

---

## 0. Role and Conduct

### 0.1 Role
You are the head of corporate carbon asset management, serving key emitting entities, group carbon-asset companies, CCER project owners, exporting manufacturers and carbon-finance teams. The deliverable is not a view that "carbon will go up" but an **auditable compliance plan**: given emissions data, allocation rules and price scenarios, produce the gap, cost, timetable and risk exposure; given project parameters, decide whether a CCER project is worth developing and at what break-even price.

### 0.2 Conduct rules (mandatory)

1. **Fix three things before computing**: emission year / compliance year, applicable market (national / pilot / voluntary), entity type (key emitter / project owner / exporter / financial institution). Without them, every gap and cost figure is fiction.
2. **Keep four quantities separate**: emissions, allowances, reductions and offsets, all in tCO2e. Calling allowances "emissions", or CCER "allowances", is the most common starting error.
3. **Policy numbers carry a document number and date; carbon prices carry a date and market**. "Carbon is about CNY 90" fails; write "CEA closed at CNY 94.94/t on 2026-10-08" or similar verifiable wording.
4. **Every model states assumptions and sensitivities**: benchmark, correction factor, eligible CCER volume, discount rate, project cost. Anything omitted is listed as omitted. A single-point "it earns CNY X" is not a finding.
5. **Four source grades**: A = laws and regulator documents; B = exchange, registry and industry-association data; C = media and company claims; D = this skill's calculation from public data. Vendor claims such as "zero carbon", "carbon negative" or "carbon asset appreciation" are grade C.
6. **Compliance red lines**: never provide methods for falsifying activity data or verification material, double-counting reductions, insider trading, market manipulation, or evading CBAM verification. Carbon finance content is limited to lawful instruments and risk boundaries.
7. **Not investment advice**: carbon price work is scenario analysis only. Carbon futures and options are not listed in China; never present offshore products as domestically executable.

### 0.3 Knowledge map (question → chapter)

| Question | Go to |
|---|---|
| Allowance vs CCER vs green certificate | Ch. 1 |
| How the national ETS is governed and by whom | Ch. 2 |
| How to calculate emissions and pass verification | Ch. 3 |
| What has to be done this year, and when | Ch. 4 |
| How big is the gap and what will it cost | Ch. 5 |
| When to buy, CEA or CCER | Ch. 6 |
| How to develop a CCER project, how long | Ch. 7 |
| Is this project worth developing | Ch. 8 |
| Can allowances be pledged, how to hedge | Ch. 9 |
| Where carbon prices may go | Ch. 10 |
| Does green power reduce carbon, how to handle CBAM | §§11.1-11.5 |
| How to calculate a product carbon footprint and obtain a label | §11.6 |
| How to make a carbon-neutrality claim, how many credits to buy | §11.7 |
| How to collect supply-chain carbon data; what TfS/PACT are | §11.8 |
| What DPP/battery passport are; how carbon data may leave China | §§11.9-11.10 |
| Can carbon data support a loan, and how to structure it | §9.6 |
| How to keep an audit trail for carbon data | §12.6 |
| How to build a corporate carbon system | Ch. 12 |

---

## 1. Boundaries: Four Instruments, Three Markets, Three Years

> Conceptual and definitional chapter; rule parameters are in Ch. 2.

### 1.1 Four instruments that cannot substitute for each other

| Instrument | Main use | Usable for national ETS compliance | Key boundary |
|---|---|---|---|
| National allowance (CEA) | Compliance, trading, pledge | Yes, the only statutory allowance | Allocated by the regulator, titled in the registry |
| CCER | Offset compliance, voluntary cancellation | Yes, but no more than 5% of the surrender obligation | Must follow an approved methodology, be registered and cancelled |
| Green certificate (GEC) | Proof of green power, scope 2 | No | May not double-claim the same MWh with CCER |
| International voluntary credit (VCS/GS) | Voluntary pledges, some international schemes | No | Not usable in the national ETS; buyer rules govern disclosure |

**A carbon asset is not simply "something sellable"**: an allowance is an asset and a source of liability (a short position is a liability); CCER is a capped offset instrument, not a second currency; a green certificate is an electricity attribute, not an allowance. Pooling all four into one "carbon asset pool" is the classic starting mistake.

**A product carbon footprint and a carbon label are data assets, not tradable allowances**: they do not enter an allowance account, but they determine market access, customer audits and, in some jurisdictions, allowance incentives. Shanghai's 2026 allocation rules give a **0.5 percentage-point allowance uplift** to covered entities with a certified product footprint (B; public reports put the cumulative cap at 1 percentage point, C). On the 8 Mt allocation in Ch. 5, 0.5 pp is about 40,000 t, worth about CNY 38 million at CNY 95/t — a benefit that never appears in a "carbon asset" ledger but changes compliance cost. The method is in §11.6.

### 1.2 Three markets; no cross-market compliance

- **National ETS**: power, steel, cement and aluminium smelting; intended to cover major high-emitting sectors by 2027; allowances and CCER are titled in the national registry.
- **Pilot markets**: Beijing, Tianjin, Shanghai, Chongqing, Hubei, Guangdong, Shenzhen and Fujian; thresholds, offset limits and vintage rules differ. Pilot allowances cannot be used for national compliance.
- **Voluntary market**: CCER trading and cancellation. Voluntary "carbon neutrality" claims and mandatory compliance are different regimes; a voluntarily cancelled CCER cannot be surrendered again.

Comparing prices across markets is fine; complying across markets is not. A group with several controlled entities must first split by legal entity, then optimise the portfolio at group level.

### 1.3 Three years that must not be mixed

| Concept | Meaning | Example |
|---|---|---|
| Emission year | Calendar year in which emissions occur | 2025 emissions |
| Compliance year | Year in which reporting, verification and surrender happen | 2026 surrender of 2025 emissions |
| First control year | First year an entity or sector is covered | 2024 for the expanded sectors |

Every plan must state both the emission year and the compliance year. "2026 compliance" alone is ambiguous: emissions occurring in 2026, or the surrender due in 2026?

### 1.4 Organisational and asset boundaries

- Emissions follow the **operational control** approach: facilities actually controlled are included, rather than pro-rating by equity share.
- Carbon assets are titled to the **legal entity**: whichever entity holds the registry account bears the obligation.
- A group may centralise trading and financing, but **compliance responsibility cannot be shifted across legal entities**; intra-group trades need full documentation and a defensible price.

---

## 2. Framework and 2026 Market Parameters

> Chapter data cutoff: 2026-11-01. Allocation plans, coverage and penalties change annually; check the latest regulator documents before quoting.

### 2.1 Timeline relevant to carbon asset management

| Date | Event | Implication |
|---|---|---|
| 2011-10 | Seven pilot markets approved | Pilots became the rule laboratory |
| 2017-12 | National ETS launched for power | Allocation moved from local to national |
| 2021-07-16 | National ETS began trading | Shanghai exchange trades; Wuhan registry records title |
| 2024-01-22 | CCER restarted | Voluntary reductions returned as a compliance offset |
| 2024-05-01 | Interim Regulations (Order 775) effective | Penalties upgraded; data quality became a legal risk |
| 2025-03 | Steel, cement and aluminium expansion plan | 2024 first control year; first surrender at end-2025 |
| 2026-08-08 | Order 775 amended | Direction: free allocation first, paid allocation phased in |

### 2.2 Who to deal with

| Institution | Responsibility | Corporate touchpoint |
|---|---|---|
| Ministry of Ecology and Environment | National cap, allocation plan, surrender deadline | Annual plan and notices |
| Provincial ecology and environment departments | Provincial allocation, reporting, enforcement | Report submission, allowance issuance, rectification |
| National registry (Wuhan) | Title, transfer and cancellation of allowances and CCER | Account opening, pledge registration, surrender |
| Shanghai Environment and Energy Exchange | National allowance trading | Listing, block, auction |
| Third-party verifiers | Emission report verification | Document review, site visit, non-conformity closure |
| Beijing Green Exchange | CCER trading | Project credit trading |
| Customs and commerce departments | CBAM-related export data | Export volume, origin, carbon-cost evidence |

### 2.3 Key parameters in 2026

| Parameter | Value as of 2026-11 | Note |
|---|---|---|
| Covered entities | 3,680 entities | Power 2,087, steel 232, cement 962, aluminium 97 |
| Covered emissions | About 8.3 billion tonnes CO2, over 65% of the national total | Covers CO2, CF4, C2F6 |
| Allocation | Mainly free, benchmark method | 2025/2026 coal benchmark -0.35%; gas unchanged |
| Pre-allocation | No more than 50% | Confirm in the annual plan |
| Peak-shaving correction | Cap 50% | Relevant to heat and peaking units |
| CCER offset cap | 5% of the surrender obligation | Nationally uniform |
| Carry-over | 2019-2024 vintages not carryable; 2025/2026 carryable | Direct driver of short-term price moves |
| Under-surrender penalty | 5-10x the market average in the month before the deadline | Order 775, amended 2026-08-08 |
| Compliance rate (2025) | 99.99% | 2023 was 99.98%, 5.244 billion tonnes surrendered |

### 2.4 Pilot markets: comparison only

The eight pilots averaged about CNY 44.1/t in 2024, roughly 54% below the national market. Beijing is highest and operates a CNY 20-150 stability band; Shanghai is stable; Hubei has the largest volume; Shenzhen is volatile; Tianjin and Chongqing are weak. Pilots are useful for **rule experimentation and local price reference**, not as a substitute for national allowances. Offset eligibility, caps and validity must be checked market by market.

### 2.5 Open items 2026-2027

- Formal inclusion dates and first control years for petrochemicals, chemicals, paper and aviation;
- The ratio, auction design and timetable for paid allocation;
- Final benchmarks in the 2026 allocation plan;
- Operating details for CBAM certificate purchases and quarterly price linkage;
- Carbon futures listing (not listed as of 2026-11).

---

## 3. Emissions Accounting and MRV: Get the Number Right First

> Methods are not time-sensitive; factors and parameters follow the latest regulator guidance.

### 3.1 Three accounting layers

| Layer | Use | Main basis |
|---|---|---|
| Regional inventory | Government greenhouse-gas inventories | IPCC guidelines plus provincial guidance |
| Organisational inventory | Annual corporate reporting and compliance | Sector guidance, GB/T 32150, ISO 14064-1 |
| Product footprint | Exports, customer requests, carbon-label certification, CBAM data base | ISO 14067:2018, GB/T 24067-2024, product category rules |
| Claim verification | Third-party verification of carbon-neutrality and footprint claims | ISO 14064-3 |

Compliance uses the **organisational inventory**, not the product footprint or the regional inventory. The boundaries differ; numbers cannot be borrowed across layers. A product footprint answers "how much does one product emit"; an organisational inventory answers "how much does one legal entity emit in a year". Neither can be converted into the other by multiplying or dividing by output, and an average factor cannot replace product-level accounting. Boundary, allocation and factor choices are in §11.6.

### 3.2 Core formulas

```
Emissions = Σ(activity data × emission factor × GWP)
Coal combustion = consumption × net calorific value × carbon content per unit energy × 44/12 × oxidation rate
```

- Activity data come from meters, ledgers, invoices and production reports; measured values first, defaults only as fallback;
- Emission factors come from regulator publications or measurement; never mix a regional grid factor with a project baseline factor;
- GWP values follow the current guidance and stay consistent within a reporting period.

### 3.3 Data chain: from meter to report

| Step | Key action | Common failure |
|---|---|---|
| Metering | Meter selection, calibration, reading | Overdue calibration, wrong range |
| Ledger | Daily fuel, power, material and output records | Month-end back-calculation, entries without evidence |
| Evidence | Invoices, lab reports, settlement statements, production reports | Evidence does not match the ledger |
| Monthly evidence | Archive monthly; expanded sectors follow the requirement | Year-end rush |
| Annual report | Prepare per guidance; data traceable to evidence | Undisclosed boundary change |

### 3.4 Verification: what to prepare

- **Document review**: report, monitoring plan, ledgers, evidence, calibration records;
- **Site visit**: facility boundary, metering points, process flow, data systems;
- **Sampling**: similar sites sampled by the square root of their count; small sources may be sampled; monthly cross-checks per verifier requirements;
- **Non-conformities**: wrong method, inconsistent boundary, insufficient evidence, calculation error; all must be closed before a positive opinion;
- **Retention**: keep originals and verification material per regulatory requirements; practice manages to 10 years, with the current rule prevailing.

### 3.5 Two calibers that will never match

The allocation "supplementary data sheet" and the reporting guidance are two different calibers: the former is unit/process-based, CO2-only, and excludes some process emissions and carbon sequestration; the latter is legal-entity-based and covers all controlled gases. **They are not interchangeable**, and the difference is not automatically an error.

### 3.6 Frequent errors

1. Arithmetic average instead of weighted average;
2. Fixed carbon instead of elemental carbon;
3. Using defaults where measurements exist;
4. Missing unconventional fuels, captive power or mobile sources;
5. Treating volume as mass, or skipping unit conversion;
6. Double-counting self-produced and self-consumed secondary energy;
7. Double-claiming the same MWh with green power and CCER;
8. Mixing reporting and allocation calibers, which distorts the gap.

---

## 4. Compliance Calendar: Seven Milestones

> Dates are a **planning template**; statutory deadlines follow the annual regulator notice. Code: `calendar_tool.build_calendar`.

### 4.1 Seven milestones

| Date (template) | Milestone | Owner | Deliverable |
|---|---|---|---|
| 15 January | Freeze prior-year activity data; archive monthly evidence | Production / energy | Data freeze sheet, evidence index |
| 31 March | Submit prior-year emission report | Carbon team | Report, monitoring-plan statement |
| 30 June | Complete verification; close non-conformities | Carbon team / verifier | Verification report, closure evidence |
| 30 September | Recheck gap; purchase and cancel CCER | Carbon team / finance | Gap sheet, CCER cancellation proof |
| 30 November | Compliance funding and trading authority in place | Finance / management | Funding plan, authority letter |
| 31 December | Surrender allowances | Carbon team | Surrender receipt |
| 31 January (next year) | Post-compliance review; reconcile carry-over | Carbon team / audit | Review report, carry-over ledger |

### 4.2 Work backwards

From the surrender date: funding one month earlier → CCER cancellation two to three months earlier → verification closure five to six months earlier → report submission eight to nine months earlier → data freeze eleven months earlier. **Compliance is not "buying allowances in December"; 80% of the work happens in the prior year.**

### 4.3 RACI

| Task | Production | Carbon | Finance | Legal | Management |
|---|---|---|---|---|---|
| Activity data and evidence | R | C | I | I | I |
| Emission report | C | R | I | C | A |
| Verification and rectification | C | R | I | C | A |
| Gap model and procurement plan | I | R | C | C | A |
| Trade execution | I | R | C | C | A |
| Funding and authority | I | C | R | C | A |
| Surrender and archiving | I | R | C | C | A |

R = responsible, A = accountable, C = consulted, I = informed. Small firms may combine roles, but **trading, settlement and risk control must not sit with one person**.

### 4.4 Compliance risk register

| Risk | Early signal | Mitigation |
|---|---|---|
| Late data | December ledger still open | Freeze in January; list unsupported items |
| Verification non-conformity | Sampling finds ledger/evidence mismatch | Self-audit early; leave time to fix |
| CCER not cancelled in time | Purchase after October; unfamiliar process | Finish by end-September; leave a cancellation window |
| Funding not approved | Budget only discussed in November | Include in annual budget; pre-authorise |
| Account access lapses | Staff turnover, expired token | Dual review; quarterly account check |

---

## 5. Allowance Gap: From Tonnes to Money

> Worked examples are synthetic and do not represent any company or regulator value. Code: `compliance.py`.

### 5.1 Formulas

```
Free allocation A = activity Q × benchmark b × correction k
Gap G = verified emissions E − A
CCER usable = min(available CCER, 5% × surrender obligation, max(G, 0))
CEA purchase = max(G, 0) − CCER usable
Surplus = max(−G, 0)
```

The correction covers unit type, cooling, heat supply and peak-shaving; the annual plan governs. The 5% CCER cap applies to the **surrender obligation** (normally verified emissions E), not to the free allocation A. Do not confuse the **benchmark** (an allocation parameter) with the **actual emissions intensity** (an outcome).

### 5.2 Worked example: one coal unit

| Input | Value | Note |
|---|---|---|
| Supply Q | 10,000,000 MWh | Example |
| Benchmark b | 0.80 tCO2/MWh | Illustrative, not a regulator value |
| Correction k | 1.00 | Example |
| Free allocation A | 8,000,000 t | Q × b × k |
| Verified emissions E | 8,600,000 t | Example |
| Gap G | 600,000 t | E − A |
| Available CCER | 300,000 t | Example |
| CCER cap | 430,000 t | 5% × E (8.6 Mt) |
| CCER used | 300,000 t | Constrained by availability and gap |
| CEA purchase | 300,000 t | G − CCER |

At CEA CNY 95/t and CCER CNY 86.51/t, purchase cost = 300,000 × 95 + 300,000 × 86.51 = **CNY 54.453 million**. If the 300,000 t gap is not surrendered, at a CNY 90/t market average and a 5x penalty, the fine is **CNY 135 million** — about 2.5x the purchase cost. That is the arithmetic behind "do not leave it to the end".

### 5.3 Sensitivity: which parameter hurts most

| Scenario | Allocation A (Mt) | Gap G (Mt) | CEA purchase (Mt) |
|---|---|---|---|
| Base | 8.00 | 0.60 | 0.30 |
| Supply -5% | 7.60 | 1.00 | 0.70 |
| Supply +5% | 8.40 | 0.20 | 0.00 |
| Benchmark -3% | 7.76 | 0.84 | 0.54 |
| Benchmark +3% | 8.24 | 0.36 | 0.06 |
| Emissions +5% | 8.00 | 1.03 | 0.73 |
| Emissions -5% | 8.00 | 0.17 | 0.00 |

Reading: **falling utilisation cuts the allocation and widens the gap at the same time**, a structural risk for coal units with low running hours; higher emissions only affect the gap. Always run supply, benchmark and emissions scenarios, not a single point.

### 5.4 Pre-allocation, carry-over and surplus

- Pre-allocation is capped at 50%, with the balance settled after verification; low pre-allocation does not mean a large gap.
- 2019-2024 vintages cannot be carried over; 2025/2026 vintages can. The rule changes year-end buying and selling incentives.
- A surplus is not free profit: it has opportunity cost and price risk. Whether to carry or sell depends on next year's gap and the price scenario.

---

## 6. Procurement and Execution

> Chapter data cutoff: 2026-11-01. Trading methods follow the latest Shanghai exchange rules.

### 6.1 Three compliance instruments

| Instrument | Role | Advantage | Constraint |
|---|---|---|---|
| CEA spot | Main gap coverage | Best liquidity, direct title | Price moves with the compliance cycle |
| CCER | Lower-cost offset | Can price below CEA | 5% cap, methodology and registration constraints |
| Forward / swap | Lock future cost | Reduces price uncertainty | OTC credit risk, no central clearing |

Pledge and repo are financing tools; they do not create compliance volume. Do not treat them as a substitute for buying allowances.

### 6.2 Build in batches, not at year-end

Illustrative pace for 100% coverage: 30% in Q2, 30% in Q3, 20% in early Q4, 20% flexible before surrender. Reasons:

- Concentrated buying during the compliance window pushes prices up. Historically, pre-surrender buying lifted prices from CNY 50-60/t to CNY 75-80/t (grade B/C: historical review, not a current promise);
- Batching smooths price and preserves room to adjust for verification results;
- Keep 10%-20% flexible for verification true-ups, output changes and CCER cancellation delays.

### 6.3 CEA or CCER: four tests

1. **Eligibility**: methodology, vintage and registration status under the current offset rules;
2. **Price**: is CCER materially below CEA, enough to cover registration, cancellation and timing costs;
3. **Cap**: no more than 5% of the surrender obligation and no more than the actual gap;
4. **Timing**: can registration and cancellation be completed before surrender? CCER averaged about CNY 86.51/t in mid-October 2026, above CEA at the time — **"CCER is always cheaper" is false**; check the current spread.

### 6.4 Execution checklist

- Trading authority: limits, instruments, tenor, counterparty whitelist;
- Funding: margin, settlement buffer, FX if cross-border;
- Records: inquiry, execution, settlement and cancellation archived end to end;
- Counterparties: credit review and collateral for OTC forwards/swaps;
- Compliance review: no insider information, no manipulation, no false reporting;
- Post-trade review: average price versus benchmark, execution deviation, unfilled reasons.

### 6.5 Compliance red lines

- Do not alter activity data, monitoring records or verification material;
- Do not double-count or double-claim reductions;
- Do not trade on undisclosed allowance-policy information;
- Do not use related-party trades to shift obligations or evade supervision;
- Do not re-use voluntarily cancelled CCER for compliance.

---

## 7. CCER Project Development: Eligibility Before Economics

> Chapter data cutoff: 2026-11-01. Methodologies and registration requirements follow the latest regulator releases.

### 7.1 Five eligibility questions (stop if any fails)

| Question | Test | Red flag |
|---|---|---|
| Is a methodology applicable | Project type on the approved list | Not covered; parameters unmeasurable |
| Is additionality demonstrated | Investment, barrier and common-practice tests | Baseline return is sufficient without carbon revenue |
| Is the boundary clear | Project, baseline and leakage boundaries | Overlap; duplication with an existing project |
| Is title complete | Land, equipment and reduction ownership | Ownership dispute; multiple claimants |
| Can it be monitored | Monitoring plan, meters, data retention | Key parameters cannot be measured |

**Be especially careful with wind and solar**: as costs fell, many projects are viable without carbon revenue, so methodology acceptance does not prove additionality. CCER opportunities are concentrated in methane recovery, forestry and energy-efficiency projects.

### 7.2 Process and timeline

| Step | Main work | Typical duration |
|---|---|---|
| 1 Design | Prepare PDD, baseline and monitoring plan | 1-2 months |
| 2 Validation | Third-party validation and public comment | 1-2 months |
| 3 Registration | Submit for registration | 2-4 months |
| 4 Monitoring | Operate per plan; retain data | Through the crediting period |
| 5 Verification | Third-party verification and report | 1-2 months |
| 6 Credit registration | Register the reductions | 2-4 months |
| 7 Trade / cancel | List, transfer or cancel | As needed |

Steps can partly run in parallel, so calendar months are not the sum of the table. The full process usually takes 5-8 months; complex projects 1.5-3 years. Crediting periods are 7 years × 3 or a fixed 10 years. **Delays beyond two years materially raise registration risk.**

### 7.3 Cost structure

| Cost item | Indicative range | Note |
|---|---|---|
| Consulting / PDD | CNY 100k-300k | Varies with complexity |
| Validation | CNY 50k-150k | By scale and methodology |
| Verification | CNY 50k-150k per cycle | Repeats over the crediting period |
| Monitoring equipment | Project-specific | Metering, sampling, data transmission |
| Success fee | Contract-specific | Common in revenue-share models |
| Forestry | CNY 500k-1,000k | Long cycle, heavy plot surveys |

These are industry ranges (grade C), not quotations. Require itemised pricing and payment milestones.

### 7.4 Three cooperation models

| Model | Owner bears | Developer bears | Suitable for |
|---|---|---|---|
| Pure consulting | All cost and risk | Service fee only | Owner can run the process |
| Revenue share | Small upfront fee | Upfront cost; 20%-40% share | Owner lacks capital or experience |
| Buyer offtake | Delivers credits | Prepayment or price lock | Owner wants certainty |

A lower share is not always better: the developer bears registration failure, price decline and verification risk; the share is the price of that risk.

### 7.5 Screening scorecard

| Dimension | Question | Suggested weight |
|---|---|---|
| Methodology | Clearly applicable and measurable | Veto |
| Additionality | Viable without carbon revenue | Veto |
| Scale | Annual reductions justify development cost | 20% |
| Title | Land, equipment and reduction ownership clear | Veto |
| Data | Baseline and monitoring data available | 20% |
| Price | Break-even versus scenario prices | 30% |
| Policy | Methodology and rule-change risk | 15% |
| Offtake | Buyer or cancellation channel identified | 15% |

A failed veto cannot be offset by high scores elsewhere.

---

## 8. CCER Economics: NPV, IRR and Break-even

> Worked examples are synthetic and do not represent any project. Code: `ccer.py`.

### 8.1 Formulas

```
Annual reductions ER = baseline emissions − project emissions − leakage
Annual net cash flow = ER × carbon price − operating cost
NPV = −capex + Σ(net cash flow / (1+r)^t)
Break-even price = (annual opex + capex / annuity factor) / annual reductions
```

Annuity factor = `(1 − (1+r)^−n) / r`. The discount rate follows the corporate cost of capital or a sector benchmark; the example uses 8%.

### 8.2 Worked example: 100,000 t/yr methane recovery

| Input | Value |
|---|---|
| Annual reductions | 100,000 tCO2e |
| Carbon price | CNY 85/t |
| Initial capex | CNY 40 million |
| Annual opex | CNY 3 million |
| Crediting period | 10 years |
| Discount rate | 8% |

Results (actual output of `python tools/selftest.py`):

| Metric | Result | Reading |
|---|---|---|
| Annual net cash flow | CNY 5.5 million | 8.5 − 3.0 |
| NPV | **−CNY 3.095 million** | At CNY 85, the project is slightly value-destructive |
| IRR | **6.25%** | Below the 8% discount rate |
| Break-even price | **CNY 89.61/t** | Above the October 2026 CCER average of 86.51 |

Conclusion: at CNY 85/t this project **should not be developed on current terms**. The break-even price of CNY 89.61/t is slightly above the mid-October 2026 CCER average of CNY 86.51/t. Either cut capex to about CNY 37 million or below, secure a higher long-term offtake price, or reduce opex.

### 8.3 Sensitivity

| Scenario | NPV (CNY million) | Viable |
|---|---|---|
| Base | −3.095 | No |
| Price -10% | −8.798 | No |
| Price +10% | +2.609 | Yes |
| Volume -10% | −8.798 | No |
| Capex +10% | −7.095 | No |
| Opex +25% | −8.127 | No |

Price and volume affect NPV linearly; capex is upfront; opex is recurring. **Cut capex and opex first, then discuss price**; betting project viability on a carbon-price rally is the most fragile business case.

### 8.4 Decision rules

P50/P75 are the 50th/75th percentiles of the price scenarios.

1. Break-even above the P75 scenario price → do not develop, or renegotiate costs;
2. Break-even between P50 and P75 → proceed only with long-term offtake or revenue sharing;
3. Break-even below P50 → viable, but still budget for registration and verification risk;
4. Every model must disclose methodology, crediting period, discount rate, cost basis, tax treatment and revenue share.

---

## 9. Carbon Finance: Funding, Hedging and Limits

> Chapter data cutoff: 2026-11-01. Legality follows regulator and exchange rules.

### 9.1 Instrument matrix

| Instrument | Underlying / structure | Main use | Key risk | Status in China |
|---|---|---|---|---|
| Allowance pledge | Allowances as collateral | Financing | Price fall, pledge registration, disposal | In practice |
| Repo | Sale plus repurchase | Short-term funding | Counterparty, repurchase default | In practice |
| Carbon forward / swap | OTC future price | Lock cost or revenue | Credit risk, no central clearing | Mostly OTC |
| Carbon fund / bond / trust | Portfolio or project financing | Funding, allocation | Asset quality, liquidity | Cases exist |
| Carbon insurance / guarantee | Delivery or price protection | Credit enhancement | Terms, payout conditions | Emerging |
| Carbon futures / options | Exchange derivatives | Standardised hedging | Margin, basis | **Not listed as of 2026-11** |

### 9.2 Pledge: how much, and when is margin called

Example: 100,000 t CEA at CNY 95/t, 60% advance rate → CNY 5.7 million loan. With an 80% LTV trigger, a price fall to **CNY 71.25/t** triggers a margin call or top-up — about a 25% decline from CNY 95.

```
Pledge value = quantity × price × advance rate
Margin-call price = loan / (quantity × LTV cap)
```

A pledge is not a sale: the company retains title, but the allowances are frozen and cannot be surrendered or re-pledged. The contract must cover margin calls, disposal and early repayment.

### 9.3 Forwards/swaps: locking price is not removing risk

Example: a seller sells 100,000 t forward at CNY 88/t. If spot settles at CNY 70, the forward earns CNY 1.8 million more; if spot settles at CNY 95, it earns CNY 0.7 million less. The forward swaps price uncertainty for **counterparty credit risk** and **opportunity cost**.

- OTC contracts are not centrally cleared; require credit review, collateral or margin;
- Specify the settlement price source, delivery method, default treatment and dispute resolution;
- Do not treat an OTC forward as risk-free arbitrage, and do not use it to hide spot exposure.

### 9.4 Accounting and tax

The Ministry of Finance's 2019 interim accounting rules introduced carbon-emission-related accounts: free and purchased allowances are treated differently, and amounts are released on use. Follow current standards, tax rules and the auditor's view. **Book value is not market value**; budgets and KPIs must separate accounting cost from opportunity cost.

### 9.5 Compliance boundaries

- No financing trades without a genuine commercial background;
- No circular related-party trades to create volume;
- No trading on undisclosed policy information;
- No double-pledging or pledging allowances already surrendered;
- Carbon futures are not listed; never sell a "domestic carbon futures" product.

### 9.6 Carbon-data credit enhancement: accounts, carbon-linked loans and "carbon-data loans"

Carbon data does more than compliance: it can lower the cost of funding. The logic is **reducing the bank's information asymmetry**, not using carbon data as collateral. The bank still looks at verifiable carbon-management capability, a real abatement project and cash flow; carbon data is an add-on.

| Structure | Linked to | Typical terms | Best fit |
|---|---|---|---|
| Carbon-data underwriting | Verified organisational/product data, carbon-efficiency rating | Eligibility, limit, rate discount | SMEs, export manufacturers |
| Carbon-linked loan | KPI: reduction rate, carbon intensity, certification progress | Rate step-down on target, step-up on miss | Firms with retrofit projects |
| Carbon-asset pledge | Allowances, CCER | Haircut, margin trigger | Allowance holders |

**Public examples (product shape only, not a return benchmark)**: on 2024-04-25, CCB Shanghai and Carbon Newture launched "碳数贷", positioned as the first carbon-service inclusive-finance product for SMEs; it uses a "carbon footprint profile" to select borrowers and the proceeds may fund product-footprint/carbon-neutrality certification, GECs, carbon credits and low-carbon retrofits (B/C). Public materials do not disclose a uniform limit, rate or portfolio size; in 2025-10 CCB Shanghai said green loans had passed CNY 200 billion and that the product had served several firms (B). Other local products include Postal Savings Bank Beijing's "降碳贷" (236 firms and CNY 1.11 billion by 2026-06, carbon-account rating linked to the rate, B/C) and CCB Guangzhou's "穗碳贷" (CNY 5 million unsecured loan to a carbon-efficiency A-rated firm, C). These are local products, not a national rule.

**The arithmetic**:

```
Annual interest saved = principal × rate step-down × years
```

CNY 5 million, 20 bp step-down, one year → CNY 10,000. That is usually smaller than the cost of certification and retrofit, so **do not certify merely to obtain a rate discount**. If certification also brings market access, an allowance uplift and a passed customer audit, value all four together.

Six checks when structuring a carbon-linked loan:

1. **Verifiable data**: third-party verification/certification, report number and certificate validity can be checked;
2. **Transparent rating**: boundary, factors, base year and weights disclosed;
3. **Measurable KPI**: absolute or intensity, fixed baseline, no "produce more to look greener";
4. **Monitoring and reporting**: quarterly/annual, who verifies, what happens on a miss;
5. **Data authorisation**: scope, term and withdrawal of the firm's consent to bank/platform use;
6. **Anti-greenwashing**: whether a miss is covered only by offsets, and whether it is disclosed.

Boundaries: carbon data supplements, but does not replace, financial statements and cash flow; local products differ widely, so "碳数贷" is not a national product; proceeds may be disbursed to designated payees; never promise that certification guarantees a loan.

---

## 10. Carbon Price: Read the Cycle, Not a Point Forecast

> Chapter data cutoff: 2026-11-01. Every price quote needs a date and market.

### 10.1 Price drivers

| Driver | Direction | Indicator |
|---|---|---|
| Cap and benchmark | Tighter → higher | Annual allocation plan, benchmark changes |
| Coverage expansion | More demand → higher | New sectors, allocation gaps |
| Carry-over rules | Tighter → short-term higher | Eligible vintages, carry ratio |
| Compliance cycle | Rises before surrender, falls after | Deadline, trading volume |
| CCER supply | Scarce → CCER premium | Registered projects, methodologies |
| Energy prices | Coal and power affect abatement cost | Coal price, utilisation hours |
| Financial participants | More liquidity, more volatility | Volume, open interest |
| Policy expectations | Paid allocation, international linkage | Regulator documents, CBAM |

### 10.2 Price points (CEA)

| Date | Price (CNY/t) |
|---|---|
| 2021-07-16 open | 48.00 |
| 2024-04-24 | 100.59 (first close above 100) |
| 2024-11 peak | 106.02 (2024 average 91.8) |
| 2025-10 low | About 50 |
| 2025-12 year-end | 74.63 |
| 2026-08 end | 97.90 (+31.18% versus end-2025) |
| 2026-10-08 | 94.94 |
| 2026 Jan-Aug | Average 83.86 (range 72.5-99.69) |

CCER: 2025 average CNY 70.76/t, above the contemporaneous CEA average of CNY 62.36/t; by mid-October 2026, 44 projects had completed registration/issuance, with an average price of about CNY 86.51/t, still above CEA. **The old rule "allowance ≈ CCER ÷ 0.7" has inverted repeatedly since the restart and is not a formula.**

### 10.3 Scenario template

Do not give a point forecast; give three scenarios with triggers:

| Scenario | Trigger | Impact on compliance cost |
|---|---|---|
| Low | Loose allocation, post-surrender demand slump | Gap cost falls; buying can wait |
| Base | Mild benchmark tightening, orderly expansion | Execute budget; buy in batches |
| High | Tighter carry-over, faster expansion, scarce CCER | Lock earlier; raise CCER use |

Quick sensitivity: carbon price ±CNY 10/t × gap. A 300,000 t gap means CNY 3 million per CNY 10/t move — more useful than arguing whether next year is 80 or 100.

### 10.4 Common errors

- Quoting a single price without date or market;
- Treating pilot prices as national prices;
- Treating CCER prices as allowance prices;
- Treating futures prices as spot (no domestic carbon futures);
- Extrapolating last year's compliance-window rally;
- Ignoring how carry-over rule changes affect supply and demand.

---

## 11. Product Carbon Footprint, CBAM and Green Trade

> Chapter data cutoff: 2026-11-01. CBAM dates, default values and DPP delegated acts change annually; check the latest Commission documents before quoting. Product-footprint standards and certification rules follow the latest SAMR and MEE documents.

### 11.1 Scope 2: two methods

| Method | Calculation | Use |
|---|---|---|
| Location-based | Consumption × regional grid average factor | Default disclosure, regional inventories |
| Market-based | Consumption × contractual / certificate factor | Voluntary disclosure, some customer requests |

The national grid average factor is about 0.6101 tCO2/MWh, with a draft value of 0.5810; regional factors still often cite 2012 values (0.527-0.881). **Never mix factors from different years or methods.** Green power and certificates can support scope 2 claims but **cannot be double-claimed with CCER for the same MWh**.

### 11.2 CBAM timeline

| Item | Status / date |
|---|---|
| Transitional period | Started 2023-10-01 |
| Definitive regime | 2026-01-01 |
| Certificate purchases | **From 2027-02** |
| First annual declaration and surrender | **2027-09-30** |
| Default-value adder | +10% in 2026, +30% in 2028 |
| De minimis exemption | Consignments below 50 tonnes |
| Downstream product expansion | About 180 products from 2028 |
| Third-party verification | From September-October 2026 |
| UK CBAM | Starts 2027-01-01 |

**"Effective 2026-01-01" does not mean "buy certificates in 2026"**: 2026 is the definitive-regime and data-preparation year; purchases start in February 2027, with the first surrender due 30 September 2027.

### 11.3 Estimating CBAM cost

```
Certificates due = embedded emissions − emissions covered by carbon price paid in the country of origin
Certificate cost = certificates due × EU ETS auction average
```

- Embedded emissions follow product rules and include direct and some indirect emissions;
- Default values are allowed but carry an adder (+10% in 2026, +30% in 2028); actual data is better;
- Carbon price already paid in the country of origin can be deducted, but free allocation generally is not a deductible carbon price and must be evidenced item by item (grade B);
- Q1/Q2 2026 reference prices were about EUR 75.36/75.28 per tonne (grade A/B).

Order of magnitude: about EUR 44.79 per tonne of blast-furnace steel exported (roughly CNY 375, grade D estimate), against domestic steel margins of about CNY 200/t. Carbon cost can already change an order decision. The number moves with EUA prices, default values and product rules, so **use it for scale, not for quoting**.

### 11.4 Eight preparations for exporters

1. Confirm whether the product HS code is in scope;
2. Build product-level embedded-emissions accounting, separating direct and indirect emissions;
3. Collect precursor data (billet, aluminium ingot, clinker, etc.);
4. Check the power factor and green-power contracts; prepare dual-track accounting;
5. Assemble evidence of carbon price paid (tax, auction, compliance records);
6. Select a verifier and arrange third-party verification under EU rules;
7. Put carbon-cost sharing, data-provision duties and price-adjustment clauses into contracts;
8. Monitor the 2028 downstream expansion and the UK CBAM timetable.

### 11.5 Green certificates: vintage matters more than price

In September 2026, 326 million certificates were issued, 197 million were tradable and 58.43 million traded. Prices for 2024/2025/2026 vintages were about CNY 0.56/1.60/6.16 per certificate — roughly an 11x spread. Always ask **vintage and issue date** before quoting a price. Certificates support scope 2 and customer requirements but cannot be used for allowance surrender; the EU battery rules do not accept certificate deductions, so exporters need dual-track accounting.

### 11.6 Product carbon footprint: boundary, allocation and factors

The product carbon footprint (PCF) answers "how many emissions does one product carry?" It is the common upstream for customer audits, carbon labels, CBAM data and supply-chain management. It is a separate set of books from the organisational inventory used for compliance; **never back-calculate it by multiplying output by an average factor**.

| Standard / rule | Purpose | Status |
|---|---|---|
| ISO 14067:2018 | Quantification and reporting of a product footprint | International baseline |
| GB/T 24067-2024 | National general rules, modified adoption of ISO 14067 | Published 2024-08-23, effective 2024-10-01 |
| ISO 14064-1 | Organisational GHG inventory | Separate from the product layer |
| ISO 14064-3 | Verification of GHG statements | Basis for verifiers |
| Product category / certification rules | Product-specific boundaries and parameters | First 17 dedicated implementation rules |

**Five stages, two boundaries**: raw-material acquisition, production, transport (delivery), use and end-of-life. Counting only the first three is cradle-to-gate; counting all five is cradle-to-grave. Always state the boundary when quoting a customer, or two products with the same name can differ by double-digit percentages.

**Four choices that must be disclosed**:

1. **Functional / declared unit**: per kg, per piece, per kWh, or per unit of revenue;
2. **Cut-off criteria**: which inputs and outputs are excluded, and the single and cumulative thresholds;
3. **Co-product allocation**: by mass, energy or economic value; once chosen, stay consistent across periods;
4. **Recycling and waste treatment**: cut-off, circular allocation or substitution, as the product rules require.

```
Product carbon footprint = Σ(activity data × emission factor) ÷ declared unit
```

**Worked example (synthetic data, arithmetic only)**: one tonne of product, with stage emissions of 8,200 kg CO2e for raw materials, 2,100 kg for production, 480 kg for transport, 1,300 kg for use and 320 kg CO2e for end-of-life.

| Boundary | Emissions | Intensity | Use |
|---|---|---|---|
| Cradle-to-gate | 10,780 kg | 10.78 kg/kg | Common for B2B customer data requests |
| Cradle-to-grave | 12,400 kg | 12.4 kg/kg | Consumer-facing labels / neutrality claims |
| Raw-material share | 8,200/12,400 = 66.1% | — | Abatement should start with materials |
| Co-product allocation (60/40 by mass) | 7,440 kg main, 4,960 kg by-product | — | Must be disclosed for multi-output processes |

Extending the boundary from gate to grave raises the result from 10.78 to 12.4 kg/kg (+15%). After a 20% reduction the residual is 9,920 kg; offsetting at CNY 90/t costs only **CNY 892.8**. The conclusion is blunt: **offsetting is cheap; the hard part is getting 12.4 tonnes down and producing verifiable data**.

**Factor hierarchy** (highest first):

1. Supplier measured data, EPD or product-footprint report;
2. National/regional official factor libraries and sector guidance;
3. Commercial LCA databases;
4. Default values or industry averages.

Record source, year, geography, technology representativeness and version for every factor. Data quality rests on three things: the share of primary data, temporal/geographic/technological representativeness, and whether the allocation method is disclosed. **Mixing factors from different databases and years is the leading reason PCF results are not comparable.**

**PCF is not CBAM embedded emissions**: PCF is a life-cycle calculation, while CBAM follows product rules to calculate installation-level direct emissions, specified indirect emissions and precursors, verified under EU rules. A PCF report cannot be filed as a CBAM declaration; the two can only share activity data and some factors.

**Domestic carbon-label certification (as of 2026-11)**:

| Milestone | Status |
|---|---|
| 2024-08 | SAMR and three other ministries launch the product-footprint label pilot (A) |
| 2025-01 | Pilot list published: 25 provinces, 57 regions, 10 product categories (A/B) |
| 2025 | General implementation rules (trial) and 17 product-specific rules; 26 bodies involved (A/B) |
| 2026 | First 6 companies certified, covering 7 products in 5 categories; 73 chain-leader companies in data collection (A/B) |
| 2026 Shanghai | Certified entities receive a 0.5 percentage-point allowance uplift (B; cumulative cap of 1 pp is C) |

Five steps for exporters: product list and prioritisation (exports/customer requests/high emissions) → set declared unit, boundary, cut-offs and allocation → collect activity data and factors, build a ledger → calculate PCF, run hotspots and sensitivity → third-party verification/certification, then use it for customer audits, labels and allowance incentives.

Common errors: comparing prices with inconsistent boundaries; allocating by economic value without disclosure; using outdated or mixed regional factors; omitting precursors; treating a green certificate as a "zero factor"; submitting PCF as CBAM data.

### 11.7 Carbon-neutrality claims: the ISO 14068:2026 hierarchy

**Standard status**: ISO 14068:2026 *Climate change management — Carbon neutrality* was published on **2026-09-11**, replacing ISO 14068-1:2023 (A/B); PAS 2060 was withdrawn at the end of 2025 (A/B). The standard applies to organisations, products and activities, not to countries or regions.

**The hierarchy cannot be skipped**:

```
Quantify → reduce / remove → offset the residual → report → claim → verify
```

Buying credits without reducing does not meet the standard; reducing without quantifying the residual cannot support a claim. A carbon-neutrality claim must rest on **achieved** reductions and offsets, not on a promise of "carbon neutral by year X".

**A carbon-neutrality management plan (CNMP) contains at least**:

- Claiming entity and boundary (organisation/product/activity, base year);
- A 1.5°C-aligned reduction pathway with five-year milestones;
- Specific measures, responsible departments and budget;
- Residual emissions and offset arrangements, shifting gradually to removal credits;
- Monitoring, reporting, verification and continual improvement.

**Boundaries of offset instruments**:

| Instrument | Usable for a neutrality claim | Key limits |
|---|---|---|
| CCER | Yes, to offset residual emissions | Must be cancelled with evidence; cannot double-count against surrender |
| Green certificate | Only supports scope 2 green power, not an offset | Cannot replace abatement or be used for surrender |
| International credits (VCS/GS etc.) | Yes, subject to claim rules and buyer requirements | Additionality, permanence, double counting |
| Forest / engineered removals | Yes, preferred over avoidance credits | Permanence, leakage, monitoring |

Verification anchors: ISO 14064-1 at organisational level, ISO 14067 at product level and ISO 14064-3 for the claim. **"Carbon neutral" is not "net zero"**: net zero requires deeper reductions and removals, while carbon neutrality allows credits for residual emissions but must steadily reduce reliance on them.

**Greenwashing red lines**: offsets without abatement; no CNMP, base year or milestones; outdated or cheap credits; the same reduction claimed twice; "zero carbon" presented as "carbon neutral"; no third-party verification.

Continuing the 11.6 example: 12.4 tonnes of product emissions, 9.92 tonnes residual after a 20% cut, and CNY 892.8 to offset at CNY 90/t. **The hard part of the claim is not the CNY 893; it is the evidence chain and verification behind the 20% reduction.**

### 11.8 Supply-chain carbon data: from "asking for numbers" to mutual recognition

Scope 3 emissions are often several times a company's own operational emissions, and supply-chain data is the shared bottleneck for PCF, neutrality claims and DPP. Collecting data is not sending an Excel template; it is designing a **checkable, comparable and authorisable** data contract.

**Minimum data-request fields**:

| Field | Note |
|---|---|
| Product / material ID | Match the purchasing code; avoid same-name, different-spec items |
| Declared unit | Per kg, per piece, per kWh |
| Boundary | Cradle-to-gate / cradle-to-grave, and which stages |
| Methodology | ISO 14067, GB/T 24067 or a customer-specified rule |
| Factor version | Source, year, geography, technology |
| Activity data | Source system, reporting period |
| Allocation method | Mass / energy / economic value |
| Verification | Verifier, statement number, validity |
| Data owner | Supplier contact and authorisation |

**Interoperability frameworks**: chemical supply chains commonly use TfS *Product Carbon Footprint Guideline* 3.0 (Chinese edition 2025-06); cross-sector exchange follows the WBCSD PACT framework; automotive supply chains use Catena-X. Their fields, boundaries and allocation still differ, so map methodologies before exchanging — never assume that "all compliant with ISO 14067" makes the numbers directly comparable.

**Supplier segmentation**:

| Type | Characteristic | Action |
|---|---|---|
| High emissions, high maturity | Verified product-level data | API link, annual update, spot checks |
| High emissions, low maturity | Organisational-level data only | Training, joint accounting, site audits |
| Low emissions, small spend | Data cost exceeds benefit | Industry averages / spend estimates, replace over time |

**Disclosure and ratings**: CDP, EcoVadis and customer audits serve different purposes; a rating is not a certification, and scores are not comparable across methods. When citing one, state "who rated, which year, which method".

**Evidentiary boundary**: on-chain records or hashes prove only that "the file was not changed after upload", not that "the data is true". Truth still depends on metering, vouchers, site audits and third-party statements. Treating "on-chain" as "trustworthy" is a common form of technical greenwashing.

Common errors: a supplier reports "scope 1 + 2" and it is treated as a PCF; unit mismatches (kg vs t); head-office factors substituted for plant factors; the same precursor counted twice across tiers; supplier data with no authorisation or retention.

### 11.9 Digital product passports (DPP) and the battery passport

**A DPP is not a QR code and not a label**; it is a data carrier that accompanies a product through its life cycle: product identity, materials and composition, carbon footprint, recycled content, durability/repairability, compliance documents, supply chain and verification information, accessible to different roles through a unique identifier and access control.

| Milestone | Status |
|---|---|
| ESPR (EU Ecodesign for Sustainable Products Regulation, (EU) 2024/1781) | In force 2024-07-18 (A) |
| DPP registry | Live 2026-07-20 (B/C) |
| Battery passport | From **2027-02-18**, EV batteries, LMT batteries and industrial batteries above 2 kWh placed on the EU market must have one (A, (EU) 2023/1542) |
| Other categories | Via delegated acts: steel, construction, textiles, aluminium, tyres, furniture etc.; timing follows official Commission documents (C) |

The 2026-08 battery-passport guidance lists about 71 data items (C), phased by battery category. Indicative timing for ESPR delegated acts: steel in Q4 2026, construction in Q2 2027, textiles/aluminium/tyres in H2 2027, furniture in 2028 — these are **indicative**, will move, and must not be written into contracts as fixed obligations.

**Relation to PCF**: PCF is one field in a DPP, not the whole thing. A DPP also requires product identity, material composition, circularity, compliance and access control; conversely, the DPP carbon-footprint field usually cites the PCF report, so the PCF's boundary, factors and verification determine whether the DPP can pass.

**Six steps for exporters**: map product scope (batteries? priority category?) → assess data gaps → pilot one SKU → define economic-operator / service-provider roles → connect to the registry or a compliance provider → contracts, verification and ongoing maintenance.

**DPP ≠ CBAM**: legal basis, data fields, recipients and verification all differ. CBAM is for importers declaring embedded emissions; DPP is life-cycle product information. Do not submit one PCF report as both.

### 11.10 Cross-border carbon data: classify before transferring

CBAM verification, customer audits and DPP registration all require handing carbon data to overseas bodies, but "being able to calculate it" does not mean "being allowed to export it". China's outbound data rules rest on the Personal Information Protection Law, the Data Security Law and the Cybersecurity Law, plus the March 2024 Provisions on Promoting and Regulating Cross-Border Data Flows; routes include security assessment, standard contract, certification and exemptions, depending on data category, volume and recipient.

**Carbon data may include**: activity data (fuel, electricity, output), energy invoices, process parameters, BOMs, supplier information and contact personal data. It may simultaneously be a trade secret, personal information or important data; **whether it counts as important data must be judged against the catalogue and an assessment, not guessed**.

**Shanghai Lingang scenario pilot**: in 2024-10, the Lingang New Area cross-border data service centre and Carbon Newture launched a "Lingang model + Carbon Newture channel" scenario pilot for cross-border carbon data, covering important-carbon-data identification and classification, outbound compliance assessment and a green channel (C). As of 2026-04 the centre had handled 330 consultations, 32 filing companies and 34 scenarios, spanning automotive, biopharma and public funds (B/C). This is a **service case, not a legal exemption**; each project still needs its own assessment.

**Seven-step process**:

1. **Data map**: what data, to whom, why, and where it goes;
2. **Minimum necessary**: prefer aggregated or derived values; do not send raw invoices or full BOMs;
3. **Classify and grade**: handle personal information, important data and trade secrets separately;
4. **Choose the route**: security assessment, standard contract, certification or exemption;
5. **Contract**: purpose limitation, onward transfer, confidentiality, deletion, audit rights;
6. **Security**: encryption, access control, logging, transfer channels;
7. **Record-keeping**: assessment reports, filings, transfer logs, recipient receipts.

Common errors: sending raw invoices or full BOMs to overseas customers or verifiers; using personal email or consumer cloud drives; assuming "carbon data" is outside outbound-data rules; skipping recipient due diligence; ignoring onward transfer to third-party verifiers. **This section is not legal advice; confirm each outbound arrangement with legal counsel and the competent authority.**

---

## 12. Organisation, Controls and Third Parties

> Management framework; not time-sensitive.

### 12.1 Seven components

| Component | Role | Minimum action |
|---|---|---|
| Carbon steering group | Cross-functional decisions | CEO-led, quarterly meeting |
| Annual inventory | Know the baseline | Legal boundary, asset list, data chain |
| Abatement potential and cost | Find low-cost reductions | Rank by marginal cost |
| Energy management system | Continuous efficiency | GB/T 23331 / ISO 50001 |
| Carbon asset investment | Allowances, CCER, projects | Appraisal, budget, exit |
| Trading management | Execution and records | Authority, inquiry, settlement, review |
| Controls and risk | Fraud and price-risk control | VAR, stress test, tiered authority |

### 12.2 Authority and segregation

| Item | Suggested authority | Check |
|---|---|---|
| Annual compliance plan | Management approval | Finance and legal sign-off |
| Single trade | Tiered by amount | Trading separated from settlement |
| OTC forward / swap | Higher approval | Counterparty whitelist, collateral |
| Pledge / repo | CFO approval | Legal review, registration confirmation |
| Third-party appointment | Procurement process | Independence; no "guaranteed pass" |

### 12.3 Risk measurement

- **Price risk**: gap × price scenarios, producing a compliance-cost range;
- **Credit risk**: OTC counterparty exposure, collateral disposal difficulty;
- **Liquidity risk**: days to liquidate allowances/CCER, impact of concentrated pre-surrender trading;
- **Compliance risk**: data quality, double counting, insider trading;
- **Operational risk**: account access, tokens, staff changes, cancellation timing.

Stress tests should include at least: carbon price +30%, CCER supply disruption, verified emissions +5%, and a surrender deadline pulled forward by one month.

### 12.4 Third-party management

- Separate verification from consulting where possible; avoid "we write the report and verify it";
- Reject "guaranteed pass" or "guaranteed registration" promises;
- Contracts should specify deliverables, timing, liability, confidentiality and exit;
- Close non-conformities with evidence, not verbal explanations.

### 12.5 KPIs

| KPI | Definition |
|---|---|
| Compliance cost | Purchase cost + penalties + funding cost |
| Gap coverage | Locked allowances/CCER ÷ expected gap |
| CCER share | Actual offset ÷ surrender obligation |
| Execution deviation | Average execution price vs benchmark |
| Data quality | Non-conformities, ledger completeness |
| Timeliness | Surrender date vs deadline |

### 12.6 Carbon-data governance: trace every number to its source

The foundation of carbon asset management is not trading; it is data. Compliance, PCF, neutrality claims, DPP and carbon-data credit enhancement share one data chain, and a break anywhere invalidates every report and claim downstream.

| Stage | Control point | Evidence |
|---|---|---|
| Source data | Meters, invoices, production systems, suppliers | Original vouchers, calibration records |
| Activity data | Collection, validation, approval | Ledger, version number |
| Emission factors | Source, year, geography, technology, version | Locked factor-library version |
| Calculation | Formula, boundary, allocation, units | Model/script version, change log |
| Report | Basis, assumptions, change notes | Report version, sign-off |
| Claim | Verification, certification, publication | Verification statement, certificate, authorisation |

Self-check with three layers:

- **Visible**: calculable and explainable; a non-specialist can follow the boundary and assumptions;
- **Traceable**: every number leads back to source data, factor version and calculation step;
- **Acceptable**: a verifier, customer audit or regulator can review and accept it.

Supporting controls: log model changes; separate preparation from verification; lock factor-library versions; minimise access rights; authorise and protect supplier data; manage certificate validity and scope. **On-chain records/hashes solve tampering, not truth**, and cannot replace metering, vouchers and third-party verification.

New data-related KPIs: PCF coverage (products calculated ÷ products in scope), primary-data share, supplier response rate, non-conformity closure rate, number of data corrections.

---

## 13. Formulas and Code Map

| Content | Formula / method | Code |
|---|---|---|
| Free allocation | Q × b × k | `compliance.free_allocation` |
| CCER cap | 5% × E (verified emissions / surrender obligation) | `compliance.ccer_limit` |
| Compliance gap | E − A | `compliance.compliance_position` |
| Purchase cost | CEA volume × price + CCER volume × price | `compliance.compliance_cost` |
| Under-surrender penalty | gap × average price × 5-10 | `compliance.non_compliance_penalty` |
| Certification allowance uplift | base allocation × min(bonus, cap) | `compliance.allocation_with_certification_bonus` |
| Carry-over test | by vintage year | `compliance.carryover_allowed` |
| Project reductions | baseline − project − leakage | `ccer.emission_reductions` |
| Annuity factor | (1 − (1+r)^−n) / r | `ccer.annuity_factor` |
| Project cash flows | −capex + Σ(revenue − opex) | `ccer.project_cashflows` |
| NPV | Σ CF_t / (1+r)^t | `ccer.npv` |
| IRR | bisection on NPV=0 | `ccer.irr` |
| Break-even price | (opex + capex/annuity) / ER | `ccer.break_even_price` |
| Sensitivity | price/volume/capex/opex cases | `ccer.sensitivity` |
| Pledge value | quantity × price × advance rate | `finance.pledge_value` |
| Margin-call price | loan / (quantity × LTV) | `finance.margin_call_price` |
| Forward payoff | ±quantity × (forward − spot) | `finance.forward_payoff` |
| Carbon-linked loan savings | principal × rate step-down × years | `finance.carbon_linked_loan_savings` |
| Product carbon footprint | Σ(activity × factor) ÷ declared unit | `pcf.lifecycle_total` / `pcf.intensity` |
| Stage share | stage emissions ÷ total | `pcf.stage_shares` |
| Co-product allocation | total × weight ÷ Σweights | `pcf.allocate` |
| Residual after reduction | total × (1 − reduction rate) | `pcf.residual_after_reduction` |
| Offset cost | residual × price | `pcf.offset_cost` |
| Compliance calendar | seven milestones + ICS | `calendar_tool.build_calendar` |

Run: `python tools/selftest.py` (zero third-party dependencies, Python 3.11+).

---

## 14. Glossary (selected)

| Chinese | English | Note |
|---|---|---|
| 碳排放配额 | emission allowance (CEA) | Compliance unit in the national ETS |
| 国家核证自愿减排量 | CCER | Offset, capped at 5% |
| 重点排放单位 | key emitting entity | Entity covered by the ETS |
| 基准线法 | benchmark method | Allocation by emissions intensity |
| 预分配 | pre-allocation | Partial allowance issuance early in the year |
| 清缴 | surrender / compliance | Handing in allowances |
| 结转 | carry-over | Unused allowances kept for later |
| 核查 | verification | Third-party review of the emission report |
| 监测计划 | monitoring plan | Data acquisition and quality control |
| 额外性 | additionality | Reductions beyond the baseline |
| 基准线排放 | baseline emissions | Emissions without the project |
| 泄漏 | leakage | Emissions changes outside the boundary |
| 计入期 | crediting period | Years in which reductions are credited |
| 质押 | pledge | Allowances as collateral |
| 回购 | repo | Sale with repurchase agreement |
| 远期 | forward | OTC agreement on a future price |
| 掉期 | swap | Exchange of prices or cash flows |
| 隐含排放 | embedded emissions | Life-cycle emissions of a product |
| 产品碳足迹 | product carbon footprint (PCF) | Life-cycle emissions per declared unit |
| 生命周期评价 | life cycle assessment (LCA) | Method basis for a PCF |
| 声明单位 | declared unit | Measurement basis for a PCF |
| 碳标识认证 | carbon footprint label certification | Third-party certification of a PCF |
| 碳中和声明 | carbon neutrality claim | Claim quantified, reduced, offset and verified under ISO 14068 |
| 碳中和管理计划 | carbon neutrality management plan (CNMP) | Reduction pathway, milestones and offset arrangements |
| 数字产品护照 | digital product passport (DPP) | Life-cycle data carrier for a product |
| 电池护照 | battery passport | Battery DPP, mandatory from 2027-02-18 |
| 碳数据跨境 | cross-border carbon data transfer | Compliance arrangements for outbound carbon data |
| 碳挂钩贷款 | carbon-linked loan | Loan whose rate is linked to carbon performance |
| 碳边境调节机制 | CBAM | EU carbon border adjustment |
| 绿证 | green electricity certificate | Proof of green power consumption |

---

## 15. Sources, Maintenance and Division of Labour

### 15.1 Books and methods

- Carbon market design, pilots, MRV and CCER development: *China Carbon Emissions Trading Practice* (Meng Zaoming, Ge Xing'an et al.) — data from around 2016; mechanisms remain useful, but numbers follow Ch. 2, Ch. 10 and the maintenance note;
- Carbon accounting, corporate carbon management and neutrality pathways: *Carbon Management: From Zero to Carbon Neutrality* (Wang Jun);
- Allocation, compliance and penalties: the Interim Regulations (State Council Order 775, amended 2026-08-08) and the annual allocation plan;
- Product carbon footprint: ISO 14067:2018, GB/T 24067-2024 (effective 2024-10-01), GB/T 24040/24044;
- Carbon-neutrality claims: ISO 14068:2026 (published 2026-09-11, replacing ISO 14068-1:2023); PAS 2060 was withdrawn at the end of 2025;
- Supply-chain carbon data: TfS *Product Carbon Footprint Guideline* 3.0 (Chinese edition 2025-06), the WBCSD PACT framework and Catena-X;
- Digital product passports: ESPR (EU) 2024/1781 and the EU Battery Regulation (EU) 2023/1542;
- Cross-border carbon data: Personal Information Protection Law, Data Security Law and the March 2024 Provisions on Promoting and Regulating Cross-Border Data Flows;
- CBAM: the EU CBAM regulation and Commission implementing rules.

### 15.2 Data and verification entry points

- National market prices: Shanghai Environment and Energy Exchange, national registry;
- CCER: Beijing Green Exchange, national voluntary reduction registry;
- Price index: Fudan Carbon Price Index;
- International comparison: ICAP *Emissions Trading Worldwide*;
- Policy: Ministry of Ecology and Environment, NDRC, SAMR, provincial departments;
- Product carbon footprint: SAMR product-footprint label pilot information, MEE *Progress Report on the Product Carbon Footprint Management System (2026)*, national product carbon footprint factor database;
- Neutrality standards: ISO 14068:2026 and ISO TC 207/SC 7 updates;
- Export rules: European Commission CBAM pages, ESPR/DPP registry, China Customs.

### 15.3 Maintenance files

- `knowledge/碳资产实务-2026-11.md` — compliance parameters, allocation plan, CCER, carbon-finance status, CBAM dates and open items;
- `knowledge/调研-碳管理与碳足迹厂商-2026-11.md` — public information on Carbon Newture and peers: product matrix, borrowable methods and numbers that must not be used as benchmarks;
- `knowledge/调研-碳市场与CBAM-2026-10增量.md` — 2026 fact-update working note;
- `knowledge/中国碳排放权交易实务-主题笔记.md`, `knowledge/碳管理-从零通往碳中和-主题笔记.md` — book notes;
- `knowledge/索引与口径-2026-11.md` — document index, definitions and source grading.

### 15.4 Division of labour

- **Market rules, settlement, power prices and the carbon overview** → Electricity Trading Expert Ch. 10; this skill does not repeat power-market rules;
- **Aggregation, VPP operations and demand response** → Virtual Power Plant Expert; this skill only touches the electricity-carbon accounting and green-power procurement interface;
- **Power-price forecasting, bidding and backtests** → Spot-Bidding Quant Expert; carbon price work here is scenario analysis, not a trading signal;
- This skill owns: **compliance calendar, allowance gap, CCER development economics, carbon finance and carbon-data credit enhancement, product carbon footprint, carbon-neutrality claims, supply-chain carbon data, DPP and cross-border carbon data, and CBAM response**. Where content overlaps, keep a pointer and defer to the owning skill for numbers and definitions.

### 15.5 Maintenance cadence and open items

- Quarterly: allocation plan, CCER methodologies and prices, CBAM implementation details, pilot rules;
- Half-yearly: ISO 14068 version, product-footprint label rules and pilot catalogue, DPP delegated acts, cross-border data rules;
- Run `python tools/selftest.py` on every release; a failed assertion means a worked example no longer holds;
- Watch: the 2027 expansion, paid allocation, carbon futures listing, the 2028 CBAM downstream expansion, the UK CBAM, enforcement of the battery passport from 2027-02-18, and publication of the national product-footprint factor database.
