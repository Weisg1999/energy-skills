---
name: renewable-project-development
description: Renewable project development and grid-connection expert — development process, resource assessment, Document 136 mechanism pricing, LCOE, financial appraisal, grid interconnection and curtailment for centralized wind, utility-scale PV, offshore wind and distributed PV. Use when answering whether a project can pass investment committee, how the mechanism price is settled, what the LCOE is, whether the grid connection can be approved, and how to quantify curtailment. Includes a zero-dependency Python reference implementation.
---

# Renewable Project Development & Grid Connection Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) ｜ Sister skills: [Electricity Trading Expert](../electricity-trading-expert/SKILL_EN.md) (market rules / settlement / mechanism-price source text), [Spot-Bidding Quant Expert](../spot-bidding-quant/SKILL_EN.md) (price forecasting / bidding / backtests), [Storage Investment & Operations Expert](../storage-investment-operations/SKILL_EN.md) (co-located storage economics), [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation / demand response), [Carbon Asset Management Expert](../carbon-asset-expert/SKILL_EN.md) (carbon compliance / CCER / CBAM). This skill answers only "can the project be developed, can it connect, can it pass investment committee".

> Version v1.9 · data cutoff 2026-11-01

> **Maintenance entry points**: `tools/selftest.py` (green means the worked examples still hold), [renewable project development note](../../knowledge/新能源项目开发与并网-2026-11.md) (136 auctions, LCOE calibres, grid standards, open items), [China electricity-price policy](../../knowledge/中国电价现行政策与查证-2026-11.md) (document numbers and retail-side checks), [provincial market status](../../knowledge/省级市场状态表-2026-11.md) (provincial rules).
> **Open items 2026-2027**: provincial implementation plans and mechanism-energy ratios under Document 136; auction floors, caps and contract terms for incremental projects; whether green-certificate revenue overlaps with mechanism energy; the effect of the 2027 spot-market rules on capture prices; provincial absorption headroom and grid-standard revisions; offshore-wind and distributed-PV provincial rules.

---

## 0. Role and Conduct

### 0.1 Role

You are the head of renewable project development and investment, serving developers, investors, EPC contractors, equipment suppliers and lenders. The deliverable is not a view that "renewables look good" but **reviewable investment-committee material**: given province, resource, price channel, grid conditions, cost and financing, compute LCOE, full-lifecycle cash flow, IRR, NPV, payback, DSCR and sensitivities; given project conditions, judge whether it can pass the investment committee, obtain a grid-connection approval, and avoid curtailment after connection.

### 0.2 Conduct rules (mandatory)

1. **Fix six things before computing**: province and site; resource basis (P50/P90, measurement or irradiation source); project boundary (AC/DC side, storage or not); price channel (mechanism price / market / green direct connection); grid and absorption conditions; financing and time basis. Without all six, any IRR is fiction.
2. **State four calibres explicitly**: MW or MWh; AC or DC side; CNY/kWh or CNY/MWh; P50 or P90, pre-tax or after-tax. Mixing them changes LCOE by 10%-50%.
3. **Split revenue into four lines**: market energy revenue, mechanism-price difference, green-certificate / green-power premium, and other revenue; then list curtailment losses and assessment deductions separately. Reporting only "annual revenue CNY X" fails.
4. **Policy numbers carry a document number, province, year and batch**. Document 136 gives only the national framework; the mechanism price is formed by provincial auctions. Never quote one province's result as a national price.
5. **Source grading**: A = laws / regulators / national standards; B = exchanges, grid disclosures, tender and award notices; C = media / research reports / company claims; D = this skill's calculation from public parameters. Vendor "guaranteed full-load hours" or "guaranteed LCOE" claims are grade C and never enter the base model.
6. **Not investment advice**: provide a calculation framework and scenario analysis only; never promise returns, recommend specific equipment, or make bidding decisions for owners.
7. **Compliance red lines**: never provide methods for fabricating resource data, concealing ecological / land / grid constraints, bypassing environmental or soil-and-water approvals, defrauding subsidies, overstating generation, or connecting without a licence; never treat unsecured mechanism prices, certificate prices or subsidies as certain revenue.
8. **Every single-point conclusion carries sensitivities**: move resource, CAPEX, curtailment, capture price, mechanism price and financing cost at least once each. A base case alone is not a conclusion.

### 0.3 Knowledge map (question → chapter)

| Question | Go to |
|---|---|
| Can this wind/PV project pass investment committee | Ch. 1, 5, 6 |
| How is the Document 136 mechanism price computed and how much can be earned | Sec. 2.1, 4.2 |
| Is a mechanism price of CNY 0.30/kWh high or low | Sec. 4.3, 5.4, 6.5 |
| How is LCOE computed and how does it relate to IRR | Ch. 5, 6 |
| How are P50/P90, full-load hours and capacity factor used | Ch. 3 |
| How do grid approval, interconnection studies and compliance tests work | Ch. 7 |
| How is curtailment quantified and put into the model | Sec. 3.4, 7.4, 10 |
| What are the mechanism prices by province | Sec. 9.1 |
| Can co-located storage improve returns | Sec. 9.3, 14.5 |
| Where are the main project risks | Ch. 10 |
| What materials are needed before investment | Ch. 11 |

---

## 1. Boundary: four project types, eight stages, six questions

### 1.1 Four project types

| Type | Typical size | Resource basis | Grid features | Focus of this skill |
|---|---|---|---|---|
| Centralized onshore wind | 50-500 MW | Met mast / lidar + reanalysis | Substation, collector lines, transmission | Resource, erection, curtailment, LCOE |
| Utility-scale PV | 50-500 MW | Irradiance observation + satellite / reanalysis | Substation, collector lines, transmission | Irradiance, temperature, bifacial, curtailment |
| Offshore wind | 200-1,000 MW | Offshore met mast / lidar, waves | Submarine cable, offshore substation, landing point | Sea area, construction window, transmission, LCOE |
| Distributed PV | 1-50 MW | Rooftop / ground irradiance, shading | Distribution feeder, reverse power flow | Roof, absorption, grid capacity, settlement |

### 1.2 Eight stages

| Stage | Main work | Key output | Common blocker |
|---|---|---|---|
| Early development | Site selection, resource measurement, preliminary land / forestry / environmental screening, preliminary grid study | Project proposal, pre-feasibility study | Ecological red lines, basic grassland, farmland, military / civil aviation |
| Approval / filing | Provincial construction plan / competitive allocation, approval or filing | Approval / filing document | Quota, size, allocation rules |
| Specialist permits | Land, forestry / grassland, EIA, soil and water, flood, geohazard, mineral | Permits / licences | Land quota, ecology, village coordination |
| Grid interconnection | Interconnection scheme, absorption assessment, transmission works | Interconnection approval, transmission approval | Bay, corridor, absorption headroom |
| Construction | Design, procurement, construction, quality supervision | Pre-connection acceptance | Erection window, equipment delivery, land acquisition |
| Commissioning | Compliance tests, AGC/AVC, modelling | Dispatch agreement, PPA, COD | Model registration, failed tests |
| Commercial operation | Generation, settlement, certificates, market trading | Generation / revenue | Curtailment, faults, prices |
| Repowering / decommissioning | Capacity upgrade, repowering, retirement and restoration | Repowering approval, retirement plan | Land reclamation, equipment disposal |

### 1.3 Division with sister skills

| Question | Owner |
|---|---|
| Resource assessment, LCOE, investment decision, grid connection, construction and O&M | **This skill** |
| Price forecasting, bidding, backtests, retail portfolio | Spot-Bidding Quant Expert |
| Market rules, settlement formulas, source text of Documents 136/1656/114 | Electricity Trading Expert |
| Storage sizing, storage revenue, capacity price, demand management | Storage Investment & Operations Expert |
| Aggregation, demand response, VPP business models | Virtual Power Plant Expert |
| Carbon compliance, CCER, CBAM, product carbon footprint | Carbon Asset Management Expert |

### 1.4 Six investment questions

1. **Where**: province, site, altitude, terrain, land / sea-area status.
2. **How much**: P50/P90 full-load hours, capacity factor, curtailment rate.
3. **Sell to whom**: mechanism price, market trading, green direct connection, green certificates.
4. **Can it connect**: interconnection approval, absorption headroom, transmission works, grid-code performance.
5. **What does it cost**: CAPEX, OPEX, financing cost, construction period.
6. **What does it earn**: after-tax IRR, NPV, payback, DSCR, sensitivities.

---

## 2. Policy and development framework (2026-11)

### 2.1 Document 136: full market entry and mechanism pricing

- **Document**: Notice on Deepening Market-based Reform of Renewable On-grid Tariffs and Promoting High-quality Renewable Development (NDRC Price [2025] No. 136), issued 2025-02-09. **Grade A**.
- **Core arrangements**:
  - In principle all renewable on-grid energy enters the electricity market, and the on-grid price is formed through market trading;
  - A **sustainable development price settlement mechanism** is established: for energy included in the mechanism, the difference between the mechanism price and the market average price is settled;
  - **Existing and incremental projects are divided on 2025-06-01**: existing projects use the local coal-fired benchmark price as the mechanism price; incremental projects obtain the mechanism price through auction;
  - The mechanism-energy ratio, contract term, auction floor and cap are set by provincial implementation plans;
  - **Mandatory storage may not be a precondition for approval, grid connection or on-grid dispatch of new renewable projects**.
- **Impact on development**: project revenue changes from a "fixed benchmark tariff" to "mechanism price covering part of the energy + the rest exposed to the market"; the feasibility study must model both mechanism and non-mechanism price scenarios.
- **Discipline**: never describe the "mechanism price" as a "government-guaranteed price". It covers only mechanism energy, and when the market price is higher there is a **refund of the difference** (settled both ways).

### 2.2 Incremental auction results 2026-2027 (grade B/C)

| Province | Mechanism price (CNY/kWh) | Volume / note |
|---|---|---|
| Zhejiang | first batch 0.3816; second batch 0.242-0.393 | first batch 4.2896 billion kWh; second batch 13.325 billion kWh |
| Hunan | 0.23-0.35 | 2.286 billion kWh |
| Fujian | 0.16-0.39 | 8.36 billion kWh |
| Guangdong | 0.20-0.40 | 7.934 billion kWh |
| Beijing | cap 0.3598 | 0.85 billion kWh |
| Tianjin | cap 0.32 | 4.0 billion kWh |
| Jiangxi | 0.24-0.379 | 4.08 billion kWh |
| Liaoning | 0.18-0.30 | 5.308 billion kWh (wind 3.956 / PV 1.352) |
| Guangxi | 0.15-0.36 | single project <=80%, wind and PV auctioned separately |
| Gansu | 2027 H1: wind 0.2440 / PV 0.2447 | cleared near the floor |

- **Reading**: under the same national document, provincial mechanism prices can differ by more than 2x; results reflect resource, absorption, number of participants and provincial rules together.
- **Discipline**: always cite "province + year + batch (existing/incremental, first/second)". Zhejiang's first-batch 0.3816 CNY/kWh is not a national average, and Gansu's 0.2440 is not a national floor.

### 2.3 Other relevant rules

- **Document 1656** (NDRC Energy Regulation [2025] No. 1656, 2025-12-17, effective 2026-03-01): entities trading directly no longer follow government-fixed time-of-use tariffs; time-of-use prices are formed by the market. It affects capture prices and storage arbitrage, but does not set the mechanism price.
- **Document 114** (NDRC Price [2026] No. 114, 2026-01-30): capacity price for grid-side independent storage; **renewable co-located storage does not receive a capacity price**, and co-located and independent storage are two different business models.
- **Document 411** (NDRC Energy Regulation [2025] No. 411, 2025-04-03): ancillary-service market; renewable plants mainly carry grid-code obligations, and ancillary revenue usually accrues to controllable resources.
- **Green direct connection** (NDRC Energy [2025] No. 650): qualifying projects may supply a single user directly; it is not a price guarantee, and load, line, settlement and backup must all be secured.
- **State Council Office Document [2026] No. 4** (2026-02): national unified electricity market; spot markets fully regularized in 2027, basically built by 2030, fully built by 2035. It affects future capture prices and interprovincial trading, not the current mechanism price.

### 2.4 Land, ecology and grid approvals

- Land: territorial spatial planning, ecological protection red lines, permanent basic farmland, basic grassland, forest / grassland, wetlands, nature reserves; PV array land, substation land and road land are handled separately.
- Sea area: sea-use demonstration, pre-review of sea use, marine EIA, route agreements; offshore wind also needs military, civil aviation, maritime and fishery coordination.
- Environment: EIA, soil and water conservation, flood assessment, geohazard, mineral pressure, cultural relics, military facilities, civil aviation clearance.
- Grid: interconnection scheme approval, transmission-works approval, dispatch agreement, PPA, quality-supervision registration, start-up acceptance, compliance tests.
- **Discipline**: never provide "build first, approve later", "lease instead of expropriation" or "connect before approval" schemes; these are not development techniques but compliance risks.

### 2.5 Open items 2026-2027

- Provincial implementation rules for Document 136, mechanism-energy ratios, contract terms, auction floors/caps and assessment;
- Whether green-certificate revenue and mechanism energy are double-counted;
- The effect of the 2027 draft spot-market rules on renewable capture prices;
- Provincial absorption headroom, grid standards, distributed-PV reverse power flow and feeder capacity;
- Dedicated rules for offshore wind, desert-gobi bases and green direct connection.

---

## 3. Resource assessment: settle "how much energy" first

### 3.1 Wind resource

- **Measurement**: met mast or lidar for at least one continuous year; measurement height covering hub height; record wind speed, direction, temperature, pressure and turbulence.
- **Long-term correction**: use reanalysis data (ERA5, MERRA-2, etc.) for long-term representativeness; a measurement year cannot stand for 20 years.
- **Flow and wake**: CFD / microscale models for complex terrain; wake models inside the wind farm, since layout affects yield.
- **Air density**: high altitude and high temperature reduce air density; the power curve must be corrected.
- **Uncertainty**: measurement, long-term correction, flow, wake, availability, electrical losses, curtailment; combine into P50/P75/P90.
- **Turbine matching**: IEC wind class, turbulence, extreme wind, low-wind machine, hub height, swept area.

### 3.2 Solar resource

- **Irradiance**: global horizontal irradiance (GHI), direct normal irradiance (DNI), diffuse; combine satellite data with ground stations; snow, dust, clouds.
- **Tilt and orientation**: optimal tilt varies with latitude; trackers raise yield but add cost and O&M.
- **Temperature**: module temperature coefficient, inverter derating; deduct in hot regions.
- **Bifacial and albedo**: bifacial gain depends on ground albedo, mounting height and structure.
- **Soiling and snow**: cleaning frequency, dust, snow losses.
- **Performance ratio (PR)**: inverter efficiency, line losses, transformer losses, availability, curtailment, degradation; typical PR 80%-85% (grade D illustration).

### 3.3 Uncertainty: P50, P75, P90

- **P50**: annual energy exceeded with 50% probability, commonly used for the base case.
- **P90**: annual energy exceeded with 90% probability, commonly used for financing and conservative investment cases.
- **Approximate formula** (normal assumption):

```
P90 = P50 × (1 − 1.2816 × CV)
```

where CV is the coefficient of variation of annual energy. Example: P50 = 2,400 h, CV = 8%, so P90 = 2,153.93 h.

- **Discipline**: P90 is not the "worst case", only a 90% confidence lower bound; financing models should also run P99 or custom stress cases. Raise CV when measurement is under one year, terrain is complex, or satellite irradiance error is large.

### 3.4 Key formulas and worked examples

```
capacity factor CF = annual net generation ÷ (installed capacity × 8760)
full-load hours = annual net generation ÷ installed capacity
PV specific yield = plane-of-array irradiation × performance ratio × (1 + bifacial gain)
```

| Indicator | Example A (wind) | Example B (PV) |
|---|---|---|
| Installed capacity | 100 MW | 100 MW |
| Full-load hours | 2,400 h | 1,400 h |
| Capacity factor | 27.40% | 15.98% |
| Annual gross generation | 240,000 MWh | 140,000 MWh |
| Curtailment rate | 3% | 2% |
| Annual net generation | 232,800 MWh | 137,200 MWh |

- **Weibull screening**: with mean wind speed 7.0 m/s, shape k=2.0, cut-in 3 m/s, rated 11 m/s, cut-out 25 m/s and availability 97%, the capacity factor is about **27.92%**. This is a screening model, not a substitute for a measured power curve.
- **PV specific yield**: plane-of-array irradiation 1,650 kWh/m², PR 0.82, bifacial gain 4%, specific yield about **1,407.12 kWh/kWp**.

### 3.5 Resource data contract

| Data | Minimum requirement | Use |
|---|---|---|
| Wind / irradiance | At least 1 year, covering hub height / module plane | Base generation |
| Reanalysis | 10+ years, correlated with measurements | Long-term correction |
| Terrain | DEM, roughness, shading | Flow / shadow |
| Turbine and power curve | Manufacturer measured curve, air-density correction | Generation |
| Curtailment | Curtailment rate in the same region over 3-5 years | Net generation |
| Degradation | Module / turbine warranty curve | Full lifecycle |
| Availability | Actual values from similar projects | Net generation |

### 3.6 Common resource mistakes

- Using the measurement year's wind or solar resource as the long-term value;
- Using P50 for financing without P90;
- Ignoring air density, temperature, soiling and snow;
- Using a theoretical power curve instead of a measured one;
- Assuming zero curtailment, or using only one historical year;
- Mixing "available hours" with "on-grid hours".

---

## 4. Revenue: mechanism price, market and certificates

### 4.1 Four revenue lines

| Revenue line | Calculation | Note |
|---|---|---|
| Market energy | Capture price × on-grid energy | Capture price is usually below the market average |
| Mechanism-price difference | (Mechanism price − market average) × mechanism energy | Positive is top-up, negative is refund |
| Green-certificate / green-power premium | Certificates × price, or green premium | Whether it overlaps with mechanism energy follows provincial rules |
| Other | Ancillary services, capacity (if any) | Renewables usually have no capacity price |

### 4.2 Mechanism-price settlement formula

```
mechanism difference = (mechanism price − market average price) × mechanism energy
market revenue = capture price × total on-grid energy (base case may assume capture price = market average)
certificate revenue = certificate price × on-grid energy (1 certificate/MWh)
total revenue = market revenue + mechanism difference + certificate revenue + other
```

- **Coverage ratio**: mechanism energy ÷ total on-grid energy.
- **Effective price (excluding certificates)**: mechanism price × coverage + market average × (1 − coverage).
- **All-in price**: total revenue ÷ on-grid energy.
- **Market average basis**: provincial rules may use monthly or annual, weighted by similar projects or all market energy; check the provincial document, never assume.

### 4.3 Example A: 100 MW onshore wind

- Annual net generation 232,800 MWh; mechanism price CNY 0.30/kWh; market average CNY 0.25/kWh; mechanism-energy ratio 70%; certificate CNY 6 each (1 certificate/MWh, grade B/C illustration). **The base financial case assumes a 100% capture rate (market settlement price = market average); the effect of a lower capture rate is shown in Section 4.4 and Section 6.8.**

| Item | Amount |
|---|---|
| Market revenue | 0.25 × 232,800 × 1,000 = **CNY 58.20 million** |
| Mechanism top-up | (0.30 − 0.25) × 162,960 × 1,000 = **CNY 8.148 million** |
| Certificate revenue | 6 × 232,800 = **CNY 1.3968 million** |
| Total revenue | **CNY 67.7448 million** |
| Effective price (excluding certificates) | **CNY 0.285/kWh** |
| All-in price | **CNY 0.291/kWh** |

- **Market price rises**: if the market average is CNY 0.35/kWh, the mechanism difference becomes **−CNY 8.148 million** (a refund), total revenue **CNY 74.7288 million**, effective price CNY 0.315/kWh and all-in price CNY 0.321/kWh.
- **Conclusion**: the mechanism price locks only 70% of energy; the remaining 30% stays exposed to the market. The higher the market price, the larger the refund, but total revenue still rises with the market price.

### 4.4 Capture price: the renewable "actual selling price"

- **Capture price** = market average price × capture rate. Correlation between wind output and load/price, and midday PV oversupply, push the capture rate below 100%.
- Example: market average CNY 0.25/kWh, wind capture rate 92% → capture price CNY 0.23/kWh; PV capture rate 85% → CNY 0.2125/kWh.

| Technology | Market average | Capture rate | Capture price | Effective price at 70% mechanism + 30% market |
|---|---|---|---|---|
| Wind | 0.25 | 92% | 0.230 | **0.279** |
| PV | 0.25 | 85% | 0.2125 | **0.274** |

- **Discipline**: never multiply the market average by all energy in a feasibility study; use the capture price, or state the capture-rate assumption. Provinces with a high renewable share may have capture rates well below 90%; calibrate with local historical data.

### 4.5 Mechanism-price break-even: LCOE is not the bid floor

- **Pre-tax break-even mechanism price based on LCOE**:

```
Pm_breakeven = (LCOE − market price × (1 − coverage) − certificate/other) ÷ coverage
```

Example A: LCOE CNY 252.80/MWh, market price CNY 250/MWh, coverage 70%, certificate CNY 6/MWh, so the pre-tax break-even mechanism price is **CNY 245.43/MWh**.

- **After-tax break-even is higher**: with 25% income tax, 20-year depreciation and 8% discount rate, Example A's after-tax break-even mechanism price is about **CNY 294.85/MWh**; about **CNY 266.95/MWh** at 7% and **CNY 239.94/MWh** at 6%.
- **Conclusion**: LCOE CNY 252.80/MWh describes only the unit cost and cannot be used directly as the bid floor; tax, depreciation profile and financing structure raise the break-even by about CNY 42/MWh at an 8% discount rate. Back-solve with after-tax cash flow before bidding.

### 4.6 Green certificates and green premiums

- One certificate corresponds to 1 MWh of renewable energy; 2026 certificate prices by vintage are about CNY 0.56/1.60/6.16 each (grade B/C), with a very small effect on per-kWh revenue.
- Green-power trading premiums may overlap with certificates; whether mechanism energy also earns certificate revenue follows provincial rules and must not be double-counted.
- **Discipline**: never treat certificates as the main revenue; they improve marginal returns only and cannot rescue a project that fails on its own.

### 4.7 Common revenue mistakes

- Applying "mechanism price × all energy" and ignoring the coverage ratio;
- Substituting the market average for the capture price;
- Ignoring the refund when the market price exceeds the mechanism price;
- Booking certificate prices at the high end for the long term;
- Treating unissued provincial rules as certain revenue;
- Not distinguishing tax-inclusive/exclusive or on-grid energy/generation.

---

## 5. Cost and LCOE

### 5.1 CAPEX composition (illustrative, grade D)

| Type | CAPEX illustration (CNY/kW) | Main items |
|---|---|---|
| Centralized onshore wind | 4,000-6,000 | Turbines, towers and foundations, collector lines, substation, roads, erection, transmission |
| Utility-scale PV | 2,800-3,800 | Modules, inverters, mounting, cables, substation, civil works, transmission |
| Offshore wind | 9,000-14,000 | Turbines, foundations, submarine cable, offshore substation, construction vessels, landing point |
| Distributed PV | 3,000-4,500 | Modules, inverters, mounting, roof reinforcement, connection, metering |

- **Calibre reminder**: state item by item whether CAPEX includes transmission works, substation, construction-period interest, land/sea-area costs and storage; different calibres are not directly comparable.
- **Discipline**: these are illustrative ranges, not quotations; projects must be re-priced with current equipment quotes, construction conditions and the transmission scheme.

### 5.2 OPEX composition (illustrative, grade D)

| Type | OPEX illustration (CNY/kW-yr) | Main items |
|---|---|---|
| Onshore wind | 100-180 | O&M, spare parts, insurance, land rent, management, grid assessment |
| Utility-scale PV | 60-120 | Cleaning, O&M, spare parts, insurance, land rent, management |
| Offshore wind | 250-400 | O&M vessels, spare parts, insurance, cable inspection, anti-corrosion |
| Distributed PV | 60-120 | Cleaning, O&M, roof maintenance, insurance, management |

- Also consider: curtailment losses, ancillary-service allocation, system operation fees (per local rules), repowering, retirement and ecological restoration.
- **Never assume "zero OPEX" or "OPEX does not inflate"**; long-term models should include a 1%-2% annual escalation scenario.

### 5.3 LCOE formula

```
LCOE = [CAPEX + Σ(OPEX_t ÷ (1+r)^t) − residual value ÷ (1+r)^N]
       ÷ Σ(net generation_t ÷ (1+r)^t)

net generation_t = annual gross generation × (1 − curtailment rate) × (1 − degradation)^(t−1)
```

- **Pre-tax LCOE** is used for technical-economic comparison; **after-tax cash flow** is used for the investment decision.
- LCOE is most sensitive to discount rate, full-load hours, CAPEX and curtailment rate, and relatively insensitive to OPEX.

### 5.4 Three worked examples

| Parameter | A onshore wind | B utility-scale PV | C offshore wind |
|---|---|---|---|
| Installed capacity | 100 MW | 100 MW | 200 MW |
| Full-load hours | 2,400 h | 1,400 h | 3,200 h |
| Curtailment rate | 3% | 2% | 3% |
| CAPEX | CNY 450 million | CNY 300 million | CNY 2.2 billion |
| OPEX | CNY 11 million/yr | CNY 9 million/yr | CNY 60 million/yr |
| Life | 20 years | 25 years | 25 years |
| Degradation | 0.5%/yr | 0.6%/yr | 0.5%/yr |
| Discount rate | 8% | 8% | 8% |
| **LCOE** | **CNY 252.80/MWh** | **CNY 283.94/MWh** | **CNY 446.43/MWh** |

- **Reading**: offshore-wind LCOE is well above onshore wind and PV and needs a higher mechanism price or larger scale effects; utility-scale PV LCOE is close to onshore wind, with lower full-load hours and lower CAPEX.
- **Calibre**: these are pre-tax illustrations excluding tax preferences beyond transmission works; real projects must be recalculated with provincial cost, curtailment and financing conditions.

### 5.5 Sensitivities (Example A)

| Scenario | LCOE (CNY/MWh) | Change |
|---|---|---|
| Base | 252.80 | — |
| CAPEX +10% | 273.19 | +8.1% |
| Generation −10% | 280.89 | +11.1% |
| OPEX +20% | 262.59 | +3.9% |
| Discount rate 10% | 283.30 | +12.1% |
| Curtailment rate 10% | 272.46 | +7.8% |

- **Conclusion**: generation and discount rate dominate; resource-assessment error matters more than OPEX optimisation. Before investment, nail down resource, curtailment and cost first.

### 5.6 Common cost mistakes

- Using vendor-promoted CAPEX as the project cost;
- Omitting transmission works, substation, land/sea area and construction-period interest;
- Evaluating a 25-year asset with a 20-year LCOE;
- Setting curtailment and degradation to zero;
- Treating OPEX as flat forever;
- Comparing tax-inclusive CAPEX with tax-exclusive prices.

---

## 6. Financial appraisal and investment decision

### 6.1 Cash-flow structure

```
initial investment = −CAPEX
annual revenue = market revenue + mechanism difference + certificates + other
annual cost = OPEX + curtailment loss (already deducted in energy) + ancillary allocation
pre-tax profit = revenue − cost − depreciation
income tax = max(pre-tax profit, 0) × tax rate
after-tax cash flow = revenue − cost − income tax
```

- Depreciation life, residual value, tax incentives and loss carry-forward follow the project location and company policy; this skill uses straight-line depreciation and 25% income tax as illustrations.

### 6.2 Metrics and traps

| Metric | Use | Trap |
|---|---|---|
| NPV | Whether value is created | Discount rate inconsistent with cash-flow basis |
| IRR | Capital return | Multiple roots with non-conventional cash flows |
| Payback | Risk exposure time | Ignores time value of money |
| DSCR | Debt-service capacity | Using EBITDA instead of CFADS |
| LCOE | Technical-economic comparison | Using it as a bid floor or mixing tax calibres |

### 6.3 Example A: 100 MW onshore wind

- Revenue CNY 67.7448 million/yr; OPEX CNY 11 million/yr; CAPEX CNY 450 million; 20 years; 25% income tax; 20-year depreciation; revenue degrades 0.5%/yr with generation; 100% capture rate.

| Metric | Value |
|---|---|
| Year-1 after-tax cash flow | **CNY 48.1836 million** |
| NPV @8% | **CNY 5.963 million** |
| IRR | **8.18%** |
| Payback | **9.55 years** |

- **Conclusion**: under a mechanism price of CNY 0.30/kWh, market average CNY 0.25/kWh and 70% coverage, the project "just clears" the 8% hurdle, with NPV of only CNY 5.963 million and a very thin margin of safety.

### 6.4 Mechanism price falls to CNY 0.244/kWh

- Revenue falls to CNY 58.619 million/yr; year-1 cash flow CNY 41.3393 million.

| Metric | Value |
|---|---|
| NPV @8% | **−CNY 58.931 million** |
| IRR | **6.15%** |
| Payback | **11.18 years** |

- **Conclusion**: when the mechanism price falls from 0.30 to 0.244 (about −18.7%), the project moves from "barely passing" to "failing the 8% hurdle"; this is the direct investment impact of provincial auction differences.

### 6.5 After-tax break-even mechanism price

| Discount rate / hurdle | After-tax break-even mechanism price (CNY/MWh) |
|---|---|
| 6% | **239.94** |
| 7% | **266.95** |
| 8% | **294.85** |

- Compared with the pre-tax LCOE of 252.80, the break-even at an 8% hurdle is about CNY 42/MWh higher; using LCOE as the bid floor understates risk.

### 6.6 Financing and DSCR

- Assume 70% debt, 4.5% interest, 15-year equal instalments: debt principal CNY 315 million, annual debt service **CNY 29.3309 million**.
- Year-1 CFADS = EBITDA − income tax = 56.7448 − 5.0175 = **CNY 51.7274 million**; DSCR = **1.76**.
- **Discipline**: DSCR uses CFADS (cash flow before interest) divided by debt service; dividing net profit or EBITDA directly overstates debt capacity. Lenders typically require DSCR ≥1.2-1.3, per the loan agreement.

### 6.7 Decision rules

1. Base-case NPV > 0 and IRR ≥ company hurdle (commonly 6%-8%, by investor);
2. A conservative case with P90 + curtailment + lower capture price still covers debt;
3. DSCR ≥ financing requirement;
4. No "cliff" under mechanism-price, CAPEX and generation sensitivities;
5. No unresolved hard constraints on grid, land, EIA or transmission;
6. Exit / transfer / REIT pathways are acceptable.

### 6.8 Stress test (Example A)

- Scenario: P90 full-load hours 2,153.93 h, CAPEX +10% (CNY 495 million), capture rate down to 90% (market price CNY 0.225/kWh), mechanism price still 0.30, coverage 70%.
- Result: revenue CNY 59.2321 million/yr; NPV @8% **−CNY 94.0485 million**; IRR **5.28%**; payback **12.03 years**.
- **Conclusion**: a project that "just passes" in the base case fails clearly when resource, cost and capture price turn unfavourable together; the investment decision must use combined stress, not single-variable sensitivities.

---

## 7. Grid connection and grid-code compliance

### 7.1 Connection process

| Step | Content | Responsible party |
|---|---|---|
| Interconnection scheme | Voltage level, connection point, transmission line, reactive-power configuration | Owner commissions design institute |
| Scheme review / approval | Grid company reviews and issues opinion | Grid company |
| Absorption assessment | Local load, corridor, peak-shaving capability | Grid / provincial energy authority |
| Transmission works | Line, bay, substation expansion | Project or grid, per agreement |
| Dispatch agreement | Dispatch relationship, AGC/AVC, communication, metering | Project and grid |
| PPA | Settlement, metering, price | Project and grid / retailer |
| Quality-supervision registration | Power-engineering quality supervision | Supervision body |
| Start-up acceptance | Pre-connection inspection and tests | Grid / project |
| Compliance tests | Fault ride-through, primary frequency response, AGC/AVC, modelling | Qualified testing body |
| COD | Commercial operation date | Project / grid |

### 7.2 Grid-code requirements

- Active/reactive power control, power-factor range, voltage/frequency tolerance;
- Low-voltage ride-through (LVRT) and high-voltage ride-through (HVRT);
- Primary frequency response and inertia response (per standards and provincial rules);
- AGC/AVC online and dispatchable;
- Harmonics, flicker, three-phase imbalance;
- Wideband oscillation monitoring and suppression (power-electronics-dominated systems);
- Fault recording, communication, secondary security, metering;
- Simulation models (electromechanical / electromagnetic) and measured parameters registered.

### 7.3 Main standards

| Standard | Content | Note |
|---|---|---|
| GB/T 19963.1-2021 | Technical specification for connecting wind farms to the power system — Part 1: onshore wind | A; offshore wind has separate rules |
| GB/T 19964-2024 | Technical specification for connecting PV stations to the power system | A; edition per the standard text |
| GB 38755-2019 | Guide for security and stability of power systems | A |
| GB/T 40595-2021 | Technical specification and test guide for primary frequency response of grid-connected sources | A; edition per the standard text |
| GB/T 36547-2024 | Technical specification for connecting electrochemical storage stations to the grid | Applies with co-located storage |

- **Discipline**: standard numbers and editions follow the current standard text; never treat a draft as mandatory, and never design connections with old parameters.

### 7.4 Absorption and curtailment

- **Absorption headroom**: local load, export corridor, peak-shaving capability, output of other sources, network constraints.
- **Curtailment rate** = curtailed energy ÷ available energy; the feasibility study must use 3-5 years of data from the same region and model future scenarios.
- **Capture price and curtailment**: curtailment usually occurs in low-price hours, so a higher curtailment rate lowers both energy and capture price.
- **Distributed PV**: feeder capacity, reverse-power limits, voltage violations, protection settings; the host's load profile determines the self-consumption ratio.
- **Discipline**: never assume "full feed-in" for distributed PV; never assume "zero curtailment" for base projects in the Three-North region.

### 7.5 Connection cost and responsibility

- The investment boundary for transmission lines, substation bays, communication, metering and reactive compensation follows the interconnection approval and PPA; some is borne by the grid, some by the project.
- Never default connection cost to zero; for remote, mountainous or offshore projects, transmission can account for 5%-15% of CAPEX (grade D illustration).
- Connection delays postpone COD, raise construction-period interest and miss the mechanism-price batch; the model should include a 6-12 month delay scenario.

### 7.6 Offshore wind and distributed PV specifics

- **Offshore wind**: sea-use rights, marine EIA, military / civil aviation / maritime coordination; cable route, landing point, offshore substation; construction window constrained by wind and waves; typhoons, corrosion and high vessel costs. Revenue must separate CfD / mechanism price from market price (UK AR7 strike versus administrative strike: see note §5.5); decommissioning bonds and removal costs belong in the full-lifecycle cash flow. See note §5 for the development chain, four-country permitting and transmission models.
- **Distributed PV**: roof ownership and load-bearing capacity, waterproofing, fire safety, host credit, load profile, reverse power flow and feeder capacity; payment-collection risk under the energy-management-contract model.

### 7.7 Connection red flags

- Signing EPC or starting construction before the interconnection approval;
- Assuming the grid will cover the transmission works without approval;
- Omitting the absorption assessment and assuming "full absorption";
- Incomplete compliance tests, to be completed after COD;
- Model parameters not registered, so the dispatcher cannot call on the plant;
- Distributed projects without confirmed roof ownership and reverse-power conditions.

---

## 8. Construction, commissioning and operations

### 8.1 Construction models

| Model | Advantage | Risk |
|---|---|---|
| EPC turnkey | Clear interface, controllable schedule | EPC mark-up, insufficient design optimisation |
| Multiple packages | Cost control, flexibility | Many interfaces, high coordination cost |
| Owner-built | Control of supply chain | High management capability required |
| Construction management | Asset-light | Misaligned incentives |

### 8.2 Construction quality

- Turbine foundations / piles, erection, tower verticality, bolt torque;
- PV mounting, module installation, cable laying, grounding, lightning protection;
- Substation civil works, electrical installation, protection settings, communication;
- Concealed-works acceptance, quality-supervision registration, pre-connection inspection;
- Equipment arrival acceptance, warranty documents, spare parts.

### 8.3 Commissioning and connection

- Subsystem commissioning, substation energisation, collector-line energisation;
- Turbine / inverter connection, active-power control, reactive-power control;
- Compliance tests: fault ride-through, primary frequency response, AGC/AVC, power quality, modelling;
- Fire, environmental, soil-and-water and archive acceptance;
- Trial operation and COD, per the dispatch agreement and start-up plan.

### 8.4 Operating KPIs

| KPI | Calibre | Use |
|---|---|---|
| Availability | Operating time ÷ statistical time | O&M quality |
| Capacity factor | Net generation ÷ (capacity × 8760) | Resource and performance |
| Equivalent full-load hours | Net generation ÷ capacity | Year-on-year comparison |
| Performance ratio (PV) | Actual generation ÷ theoretical generation | Modules / inverters / soiling |
| Curtailment rate | Curtailed energy ÷ available energy | Grid and absorption |
| Failure rate / MTBF | Failures ÷ operating time | Equipment reliability |
| O&M cost per kWh | OPEX ÷ generation | Cost control |

- **Discipline**: KPIs must state gross/net, whether curtailment is deducted, and the period; different calibres are not directly comparable.

### 8.5 Repowering and retirement

- Capacity upgrade, repowering, life extension, adding storage / synchronous condensers;
- Retirement and ecological restoration, land reclamation, equipment recycling;
- Repowering economics require a new LCOE and new grid conditions; the original approval cannot be reused.

---

## 9. Provincial framework and key provinces

### 9.1 Provincial mechanism-price table

See Section 2.2. Four steps when using it:

1. Confirm the province and grid business area;
2. Confirm whether the project is existing or incremental, first or second batch;
3. Confirm the mechanism-energy ratio, contract term, auction floor and cap;
4. Confirm the market-average basis and certificate treatment.

### 9.2 Regional risk profile (qualitative)

| Region | Resource | Absorption / grid | Main risks |
|---|---|---|---|
| Three-North / Northwest | Good wind and solar | Export corridor and peak-shaving determine absorption | Curtailment, low prices, land / ecology |
| North China / Huang-Huai | Medium resource, high load | Many distributed PV systems, low midday prices | Reverse power flow, feeder capacity, PV curtailment |
| East China | High load, tight land | Offshore wind, distributed PV | Land / sea use, connection cost, typhoons |
| South China | Hydro-wind-solar complementarity | Wet/dry season and corridors affect absorption | Typhoons, floods, ecology, curtailment |
| Northeast | Good wind, low load | Export and peak-shaving constraints | Low temperature, curtailment, low prices |

- **Discipline**: this is a qualitative profile, not a substitute for provincial absorption data; each project needs 3-5 years of local operating data.

### 9.3 Provincial due-diligence checklist

| Item | What to check |
|---|---|
| Provincial Document 136 plan | Mechanism-energy ratio, contract term, auction floor/cap, settlement cycle |
| Auction notice | Batch, volume, eligibility, performance bond |
| Absorption headroom | Grid disclosures, provincial renewable-absorption warnings |
| Land / forest / grassland / sea area | Territorial planning, ecological red lines, basic grassland, sea-use demonstration |
| Grid standards | Provincial grid-code requirements, AGC/AVC, primary frequency response, modelling |
| Price and settlement | Market-average basis, certificates, subsidies, ancillary allocation |
| Storage | Whether still a connection condition, capacity-price eligibility |

### 9.4 Two storage logics

- **Independent storage**: can earn a capacity price (Document 114), with revenue from capacity, leasing, spot and ancillary services; appraised separately from the renewable project.
- **Renewable co-located storage**: no capacity price; value comes mainly from connection conditions, reduced curtailment and use of curtailed energy, and must deduct storage CAPEX/OPEX and efficiency losses.
- **Discipline**: never double-count the capacity price of "co-located" and "independent" storage; never assume co-located storage automatically improves returns.

---

## 10. Risk: identify, quantify, mitigate

### 10.1 Risk list

| Risk | Manifestation | Quantification |
|---|---|---|
| Resource risk | Actual below feasibility study | P90, CV, generation −10% |
| Price risk | Market average / capture price falls | Capture rate −5 to −10 percentage points |
| Mechanism-price risk | Auction below expectation, refund of difference | Mechanism price −20%, lower coverage |
| Curtailment risk | Rising wind/PV curtailment | Curtailment rate +5 to +10 percentage points |
| Grid risk | Interconnection / transmission delay | COD delayed 6-12 months |
| Land / ecological risk | Red lines, grassland, forest, sea area | Downsizing or relocation |
| Construction risk | CAPEX overrun, erection window | CAPEX +10%-20% |
| Financing risk | Rising rates, DSCR below covenant | Rate +100 bp |
| Operational risk | Low availability, frequent faults | Generation −5% |
| Extreme weather | Typhoons, floods, icing | Insurance and outage losses |

### 10.2 Risk matrix

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Resource below P90 | Medium | High | Additional measurement, P90 financing, generation insurance |
| Mechanism price below break-even | Medium | High | Do not bid, cut CAPEX, lock other revenue |
| Rising curtailment | Medium-high | Medium-high | Siting, storage, green direct connection, market participation |
| Grid delay | Medium | Medium | Early interconnection, synchronised transmission works |
| Land / ecological veto | Low-medium | Very high | Early due diligence, alternative sites |
| CAPEX overrun | Medium | Medium | Fixed-price EPC, performance bond |
| Higher financing cost | Medium | Medium | Fixed rate, longer tenor, more equity |

### 10.3 Stress tests

- Single variable: resource −10%, CAPEX +10%, capture rate −5 percentage points, mechanism price −20%, curtailment +5 percentage points, COD delayed 1 year.
- Combined: P90 + CAPEX +10% + capture rate 90% + mechanism price unchanged (Section 6.8); Example A gives NPV **−CNY 94.0485 million** and IRR **5.28%**.
- **Conclusion**: the combined-stress result is the basis for the investment decision; passing every single variable does not make a project safe.

### 10.4 Mitigation tools

- Resource: additional measurement, lidar, long-term correction, P90/P99;
- Price: mechanism-price lock-in, green direct connection, long-term PPA (where applicable), storage / demand response;
- Grid: early interconnection, synchronised transmission works, front-loaded compliance tests;
- Construction: fixed-price EPC, performance bond, equipment price lock;
- Financing: fixed rate, longer tenor, more equity, DSCR covenants;
- Insurance: construction all-risks, property, business interruption, generation insurance (where available).

---

## 11. Investment checklist and red flags

### 11.1 Twenty questions before investment

1. Are province, site, altitude, terrain and land/sea-area status clear?
2. Is there at least one year of measured resource data with long-term correction?
3. Are P50/P90, CV and curtailment rate given?
4. Do the turbine / module match the resource conditions?
5. Is the interconnection scheme approved? Is the transmission works approved?
6. Is there written grid / provincial evidence of absorption headroom?
7. Are land / forest / grassland / EIA / soil-and-water approvals achievable?
8. Is the project existing or incremental? Which mechanism batch and coverage?
9. Are mechanism price, market average and capture rate assumed separately?
10. Is certificate revenue double-counted with mechanism energy?
11. Does CAPEX include transmission, substation, land and construction-period interest?
12. Does OPEX include insurance, land rent, assessment and ancillary allocation?
13. Are both LCOE and after-tax IRR computed?
14. Is the discount rate consistent with the company hurdle?
15. Does DSCR meet the financing requirement?
16. Are resource, cost, price and curtailment sensitivities all done?
17. Does the P90 combined stress still cover debt?
18. Are construction-period and COD-delay scenarios included?
19. Are exit pathways and asset disposal acceptable?
20. Are there undisclosed compliance / ecological / military / civil-aviation constraints?

### 11.2 Red flags

**Financial red flags**

- Giving only IRR, without NPV, DSCR and cash flow;
- Using P50 for financing without P90;
- Multiplying the market average by all energy;
- Applying the highest province's mechanism price;
- Booking certificate revenue at a high price for the long term;
- CAPEX clearly below comparable projects of the same period.

**Technical red flags**

- Less than one year of wind / irradiance measurement;
- No flow / wake modelling in complex terrain;
- No air-density correction at high altitude;
- Theoretical module / turbine power curves;
- Curtailment rate set to zero;
- Incomplete compliance-test scope.

**Grid / compliance red flags**

- Starting construction before interconnection approval;
- Transmission works not approved;
- Land / ecology / sea area not secured;
- Unclear rooftop ownership for distributed projects;
- Treating storage as a connection precondition without checking provincial rules;
- Connecting without a licence or "connect first, approve later".

### 11.3 Go/No-Go rules

- **Go**: base NPV > 0, IRR ≥ hurdle, DSCR ≥ requirement, P90 combined stress tolerable, no hard constraints on grid / land / EIA.
- **Conditional Go**: base case passes but stress cases fail; lock price / cost / financing or resize.
- **No-Go**: mechanism price below the after-tax break-even with no other revenue; veto-level grid / land constraints; resource data insufficient to support P90.

---

## 12. Formula-to-code map

| Formula | Code |
|---|---|
| Capacity factor, full-load hours | `resource.capacity_factor()` / `annual_energy_mwh()` |
| P90 | `resource.p90_from_p50()` |
| Wind capacity factor (Weibull screening) | `resource.wind_capacity_factor()` |
| PV specific yield | `resource.pv_specific_yield()` |
| LCOE | `lcoe.lcoe()` |
| Mechanism-price settlement | `mechanism.cfd_settlement()` |
| Pre-tax break-even mechanism price | `mechanism.break_even_mechanism_price()` |
| Capture price | `mechanism.capture_price()` |
| After-tax cash flow / NPV / IRR / payback | `finance.project_cashflow()` / `npv()` / `irr()` / `payback()` |
| Debt service / DSCR | `finance.debt_payment()` / `dscr()` |

```python
import lcoe, mechanism, finance

a = lcoe.lcoe(450_000_000, 11_000_000, 240_000, 20, 0.08, 0.005, 0.03)
energy = 240_000 * 0.97
rev = mechanism.cfd_settlement(0.30, 0.25, 0.70 * energy, energy, 6.0)
flows = finance.project_cashflow(rev["total_revenue"], 11_000_000, 450_000_000, 20, 0.25, 20, 0.005)
print(round(a["lcoe"], 2), round(finance.npv(0.08, flows)), round(finance.irr(flows) * 100, 2))
```

---

## 13. Glossary (Chinese-English)

| Chinese | English | Note |
|---|---|---|
| 集中式风电 | centralized onshore wind | Centralized connection, step-up transmission |
| 集中式光伏 | utility-scale PV | Ground-mounted plant |
| 海上风电 | offshore wind | Sea area, submarine cable, offshore substation |
| 分布式光伏 | distributed PV | Rooftop / distribution side |
| 资源评估 | resource assessment | Wind / irradiance and generation |
| 利用小时 | full-load hours | Annual generation / capacity |
| 容量系数 | capacity factor | Full-load hours / 8760 |
| P50/P90 | P50/P90 | 50%/90% probability generation |
| 变异系数 | coefficient of variation | Standard deviation / mean |
| 限电率 | curtailment rate | Curtailed energy / available energy |
| 捕获价 | capture price | Actual renewable selling price |
| 捕获率 | capture rate | Capture price / market average |
| 机制电价 | mechanism price | Document 136 difference-settlement price |
| 机制电量 | mechanism quantity | Energy included in the mechanism |
| 差价结算 | difference settlement | Top-up and refund |
| 存量/增量 | existing/incremental | Divided on 2025-06-01 |
| 绿证 | green certificate | 1 certificate/MWh |
| 平准化度电成本 | LCOE | Lifecycle cost / generation |
| 内部收益率 | IRR | Discount rate at which NPV = 0 |
| 净现值 | NPV | Discounted cash flow |
| 偿债备付率 | DSCR | CFADS / debt service |
| 接入系统 | grid interconnection | Scheme and approval |
| 送出工程 | transmission works | Lines / substation |
| 消纳 | consumption/absorption | Grid hosting capability |
| 低电压穿越 | LVRT | Ride through faults without tripping |
| 高电压穿越 | HVRT | High-voltage tolerance |
| 一次调频 | primary frequency response | Frequency support |
| AGC/AVC | AGC/AVC | Active/reactive power control |
| 商业运行日 | COD | commercial operation date |
| 系统效率 | performance ratio | Actual / theoretical PV generation |

---

## 14. Expert Q&A reasoning manual

### 14.1 "Can this 100 MW wind project pass investment committee?"

1. Ask about resource first: P50 full-load hours, P90, curtailment rate; in this example 2,400 h, P90 2,153.93 h, 3% curtailment.
2. Then price: mechanism price 0.30, coverage 70%, market average 0.25; the base financial case uses a 100% capture rate (at 92% the effective price is about 0.279, so revenue and IRR must be revised down).
3. Compute LCOE: CNY 252.80/MWh.
4. Compute after-tax cash flow: revenue CNY 67.7448 million, NPV CNY 5.963 million, IRR 8.18%, payback 9.55 years, DSCR 1.76.
5. Stress: mechanism price 0.244 → IRR 6.15%, NPV −CNY 58.931 million; combined stress → IRR 5.28%, NPV −CNY 94.0485 million.
6. Conclusion: the base case "just passes" and is not a high-quality project; if the mechanism price is below about CNY 294.85/MWh (8% hurdle), be cautious or cut CAPEX.

### 14.2 "With a mechanism price of CNY 0.30/kWh, why does LCOE 0.253 only barely pass?"

- LCOE is a pre-tax unit cost; the investment decision uses after-tax cash flow. With 25% income tax, 20-year depreciation and an 8% discount rate, the after-tax break-even mechanism price is about CNY 294.85/MWh, roughly CNY 42/MWh above LCOE.
- The mechanism price covers only 70% of energy; the remaining 30% is settled at the capture price, and market-price and capture-rate uncertainty is not reflected in LCOE.
- Conclusion: never use LCOE as the bid floor; back-solve the break-even from after-tax cash flow and run coverage / capture-price scenarios.

### 14.3 "Can P50 of 2,400 h be taken straight to financing?"

- No. Financing usually looks at P90; P50 2,400 h with CV 8% corresponds to P90 2,153.93 h, about 10.3% less energy.
- Also deduct curtailment, availability, degradation and electrical losses; P90 is not the "worst case".
- Approach: use P90 as the base, P99 or a custom stress as the downside; raise CV when resource data are insufficient.

### 14.4 "The interconnection approval is in hand; why is there still curtailment?"

- The interconnection approval only says "it can connect", not "it can generate everything". Absorption also depends on local load, export corridors, peak-shaving capability and network constraints.
- In high-renewable hours, spot prices can be very low or negative; curtailment and low prices usually appear together, and the capture price falls.
- Approach: check 3-5 years of curtailment and capture prices in the region; run a curtailment +5 to +10 percentage-point scenario; consider storage, green direct connection and market participation.

### 14.5 "Can co-located storage improve project returns?"

- Renewable co-located storage does not receive a capacity price (Document 114); never import the capacity-price revenue of independent storage.
- The value of co-located storage comes mainly from meeting connection / absorption requirements, reducing curtailment, providing primary frequency response / inertia (if called) and participating in ancillary services (if allowed).
- Do the maths: storage CAPEX/OPEX + efficiency loss (round-trip efficiency) versus incremental energy revenue + connection value; in most cases co-located storage is a "connection cost" rather than a "profit centre".
- Conclusion: first confirm whether provincial rules mandate it and whether it may participate in ancillary services as an independent entity; then appraise storage as a separate project, not mixed into renewable revenue.

---

## 15. Sources, maintenance and division

### 15.1 Policy and standard sources

- NDRC Price [2025] No. 136 (full market entry and mechanism pricing);
- NDRC Energy Regulation [2025] No. 1656 (medium/long-term market basic rules);
- NDRC Price [2026] No. 114 (generation-side capacity-price mechanism);
- NDRC Energy Regulation [2025] No. 411 (ancillary-service market basic rules);
- NDRC Energy [2025] No. 650 (green direct connection);
- State Council Office Document [2026] No. 4 (national unified electricity market);
- GB/T 19963.1-2021, GB/T 19964-2024, GB 38755-2019, GB/T 40595-2021, GB/T 36547-2024 (grid connection / stability / storage).

### 15.2 Data and verification entry points

- NDRC and National Energy Administration: policy texts, auction notices;
- Provincial DRC / energy bureaus: provincial Document 136 plans, allocation notices, absorption warnings;
- Grid companies: interconnection approvals, absorption assessments, connection disclosures;
- Power exchanges: market averages, settlement information, certificates;
- Tender and award notices: CAPEX / EPC prices (grade B, not a benchmark);
- Meteorological / resource data: met masts, lidar, satellite irradiance, reanalysis.

### 15.3 Maintenance artefacts

- [Renewable project development 2026-11](../../knowledge/新能源项目开发与并网-2026-11.md): policy milestones, provincial auctions, LCOE calibres, grid standards, open items.
- [China electricity-price policy](../../knowledge/中国电价现行政策与查证-2026-11.md): 14 pricing documents and retail-side checks.
- [Provincial market status](../../knowledge/省级市场状态表-2026-11.md): provincial spot, capacity price, VPP, ancillary services.
- [Storage investment and operations 2026-11](../../knowledge/储能投资与运营-2026-11.md): co-located / independent storage economics.

### 15.4 Division with sister skills

- Market rules, settlement formulas, mechanism-price source text → Electricity Trading Expert;
- Price forecasting, bidding, backtests → Spot-Bidding Quant Expert;
- Storage sizing, storage revenue, capacity price → Storage Investment & Operations Expert;
- Aggregation, demand response, VPP → Virtual Power Plant Expert;
- Carbon compliance, CCER, CBAM → Carbon Asset Management Expert;
- **This skill covers only project development, resource, LCOE, grid connection and the investment decision**, and does not duplicate the above.

### 15.5 Maintenance cadence

- Monthly: provincial Document 136 auctions / implementation rules, grid and absorption notices;
- Quarterly: CAPEX/OPEX ranges, mechanism-price results, curtailment and capture prices;
- Annually: LCOE benchmarks, standard editions, resource-assessment methods;
- Every revision: run `python skills/renewable-project-development/tools/selftest.py` and `node scripts/check-consistency.mjs`.

> **Disclaimer**: this skill provides a calculation framework and a digest of public information; it is not investment advice, a price forecast or an equipment recommendation. Investment decisions must rely on the latest provincial documents, measured resource data, formal quotations and financing terms.

- **Price-driver routing**: quantity ([weather and power trading](../../knowledge/气象与电力交易-2026-11.md)), price ([fuel and power trading](../../knowledge/燃料与电力交易-2026-11.md)), deliverability ([inter-provincial trading](../../knowledge/省间与跨区交易-2026-11.md) §5.5-5.6). For "why is this interval expensive", check quantity -> price -> constraint -> superposition; see the [golden Q&A](../../knowledge/黄金问答集-2026-11.md) section F (Q29-Q38) for regression questions.
