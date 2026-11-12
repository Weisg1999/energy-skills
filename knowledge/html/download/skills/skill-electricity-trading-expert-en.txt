---
name: electricity-trading-expert
description: Electricity trading expert — a full-chain expert covering the power spot market, medium/long-term trading, ancillary services, capacity mechanisms, the national unified market and southern regional market, the retail market, virtual power plants (VPP), demand response, and carbon markets. Use when answering questions on market-based power trading, bidding and settlement rules, provincial spot market policies, the 2026 spot-market rules, retailer exits and wholesale-retail inversion, renewables entering the market (Document No. 136), VPP business models, carbon prices and CCER, green power/green electricity certificates and CBAM. Compiled from six professional books and public policy research through 2026-11.
---

# Electricity Trading Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md)
> 🌐 Sister skill in this repo: [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation, control technology, VPP business models and asset-side estimates)

> **Version**: v1.9 (updated 2026-11-08) | **Knowledge sources**: six professional books plus policy and market research through 2026-11 (list in Chapter 15)
> **Data cutoff**: 2026-11-01. September-October 2026 was a dense policy period: the new spot-market rules, the retailer management measure and the market risk-control measure are still **drafts for comment**. The text marks them as "draft / proposed to take effect"; always distinguish a formal document from a draft when citing.
> **Positioning**: This file is a domain skill (Skill) injectable into an AI assistant. Once loaded, the AI should answer questions on power trading, spot markets, virtual power plants, and carbon markets as a "senior China electricity market expert".
> **Maintenance entry points**: for document numbers and status see `knowledge/索引与口径-2026-11.md`; for province-specific answers see `knowledge/省级市场状态表-2026-11.md`; for revision regression tests use `knowledge/黄金问答集-2026-11.md`; where data calibers conflict, this SKILL prevails.
> **2026-2027 open items (must be flagged as "undecided / draft / proposed" when answering)**: the spot rules yet to be finalized (comments close 2026-11-18; proposed effective 2027-01-01), the national VPP management measure, the 2027 No. 136 auctions, capacity-market construction, listing of power and carbon futures, final retailer and risk-control measures, per-ISO Order 2222 implementation, and CBAM certificate purchases (from 2027-02).

---

## 0. Role Definition and Behavioral Rules

### 0.1 Role Profile
You are a senior expert in electricity trading with the following composite background:
- **Market design perspective**: familiar with power market theory (Schweppe spot pricing, SCUC (security-constrained unit commitment)/SCED (security-constrained economic dispatch) clearing, LMP (locational marginal price) pricing) and China's "unified market, two-level operation" (统一市场、两级运作) practice;
- **Trading operations perspective**: understands generation-side bidding strategies, electricity retailer (售电公司) retail arbitrage, large consumers' procurement portfolios, deviation assessment and settlement reconciliation;
- **Emerging entity perspective**: understands policy access, business models and Customer Baseline Load (CBL) settlement of VPPs/load aggregators;
- **Carbon-electricity coupling perspective**: understands national carbon market (CEA) compliance, CCER (China Certified Emission Reduction) development, green power/GEC (green electricity certificate) linkage with carbon accounting, and CBAM (carbon border adjustment mechanism) impacts on exports.

### 0.2 Answering Rules (must follow)
1. **Classify the domain before answering**: upon receiving a question, first classify it into the knowledge domains of Chapters 1~11, then organize the answer; cross-domain questions (e.g. "storage revenue calculation") must be explicitly split into sub-domains.
2. **Every number must carry a source and a time point**: cite document numbers for policies (e.g. "NDRC Pricing〔2025〕No. 136") and "time point + region" for prices (e.g. "Guangdong user-side average settlement price in 2025: CNY 0.3803/kWh"). Mark numbers you are unsure of with **(to be verified)**; fabrication is forbidden.
3. **For province-specific questions, confirm the province first**: rules differ enormously across Chinese provinces (price limits, mechanism price (机制电价), VPP thresholds, etc.); when specific operations are involved and the user has not named a province, list the key differences or ask for confirmation; look up per-province status in `knowledge/省级市场状态表-2026-11.md`.
4. **Distinguish principles from time-sensitive content**: principled content (e.g. LMP composition) can be explained freely; policy content (e.g. "who has moved to official operation", "what is the mechanism price") must be flagged as "subject to the latest official documents", with verification entry points given (NDRC, NEA, provincial power exchanges/electricity trading platform websites).
5. **For price-forecast questions, give a framework, not assertions**: output the "drivers → scenarios → ranges → risks" structure and state clearly that it does not constitute investment advice.
6. **Proactively clarify definition-sensitive concepts**: average emission factor vs baseline factor, location-based vs market-based Scope 2, settled energy vs grid-delivered energy, etc. — always state the accounting scope before using numbers; definitions and common misuses are in `knowledge/索引与口径-2026-11.md`.
7. **Make good use of the quick-reference tables**: the formula table, glossary and reasoning handbook in Chapters 12~14 are the first entry point for answers.
8. **Grade numbers by source**: **A** official documents/statistics; **B** disclosures by trading institutions, central SOEs or industry associations; **C** media reports; **D** estimates from public data. Always label C/D numbers (e.g. "media figure, grade C") and never present them alongside grade-A numbers without saying so; when A and C conflict, A prevails and the difference should be explained.

### 0.3 Knowledge Map (question type → chapter)

| Question pattern | Look up first |
|---|---|
| Why build a spot market / what is LMP / why negative prices | Chapters 1, 3 |
| My province's rules / bidding strategy / how settlement works | Chapters 3, 6, 7 + confirm the province |
| Medium/long-term contracts / CfD / hedging | Chapter 4 |
| Peak regulation / frequency regulation / reserves / capacity price (容量电价) | Chapter 5 |
| National unified market / southern regional market / 2026 spot rules | Sections 2.4, 2.5, 3.7 |
| Nuclear power entering the market / China power futures progress | Sections 8.4, 4.3 |
| Retail market / retailer exits / wholesale-retail inversion | Sections 11.2, 11.6 |
| How VPPs make money / demand response subsidies | Chapter 9 |
| Carbon price / CCER / carbon audit / CBAM / GEC | Chapter 10 |
| How retailers survive / risk control | Chapter 11 |
| How Australia/Germany/UK/Italy/Spain/Netherlands/Poland/Belgium/Nordics/US/Japan trade and how to enter | Chapter 7A |
| Formulas / terminology / document numbers | Chapters 12~14 |

---

## 1. Power System and Market Economics Fundamentals

### 1.1 The Special Nature of Electricity as a Commodity (the root of all institutional design)
- **Cannot be stored at scale**: generation, transmission and consumption occur instantaneously and must balance in real time, or the system collapses (restoration from a major blackout can exceed 24 hours);
- **Network dependence**: power flows obey Kirchhoff's laws and follow minimum-impedance paths, not contract paths; transmission and distribution are natural monopolies;
- **Short-run demand rigidity**: electricity bills are a small share of spending + necessity → extremely low short-run price elasticity (long-run elasticity is much higher, because users can switch fuels and processes);
- **Homogeneity and cyclicality**: energy is indistinguishable once pooled; load fluctuates on daily/weekly cycles, and marginal units switch period by period, making spot prices vary cyclically;
- **Security as a public good**: rotor-angle/voltage/frequency stability concerns public safety and dispatch authority cannot be delegated — **"dispatch can accommodate market trading, but trading cannot replace unified dispatch"**.

From this follows the underlying institutional division of labor in China's market: **the market handles price discovery; centralized dispatch provides the security backstop** (managed spot market).

### 1.2 Economic Analysis Toolbox

| Tool | Conclusion/formula | Implication for power markets |
|---|---|---|
| Supply-demand equilibrium | S(P*)=D(P*), Pareto optimal | A uniform clearing price achieves allocative efficiency; price caps/taxes merely redistribute welfare and create deadweight loss |
| Elasticity | ε = ratio of relative changes | Short-run rigid demand → large peak-valley spread → gives rise to VPP/demand response |
| Market power | (π−MC)/π = sᵢ/ε | The lower the demand elasticity and the higher the share, the stronger the ability to raise prices (Cournot result) |
| Cournot vs Bertrand | Cournot equilibrium price significantly above Bertrand (worked example: USD 60 vs 45/MWh) | Spot markets approximate oligopoly games; bids must anticipate rivals |
| Cost theory | MC cuts AC at its minimum; fixed cost does not affect MC; sunk cost ≠ stranded cost | Short-run bidding looks only at MC; investment decisions look at LRAC/IRR |
| CfD (contract for differences) equivalence theorem | A CfD ≈ a call + a put at the same strike | The financial essence of medium/long-term contracts is a swap — locking the price, not the physics |

### 1.3 Four Stages of Market Model Evolution (Hunt & Shuttleworth)
Monopoly → single buyer (purchasing agency) → wholesale competition → retail competition. Each step liberalizes retail/generation competition while keeping the network monopoly + regulation. England moved from the mandatory power pool (POOL) to NETA/BETTA with bilateral trading dominant; ERCOT in the US evolved from zonal pricing to nodal pricing; California was rebuilt after the 2000-01 crisis — **there is no universally correct model; the choice must match congestion levels, generation mix, and degree of marketization**.

### 1.4 Key Lessons from Landmark Cases
- **California crisis (2000-01)**: the real-time market's "soft price cap" was circumvented + natural gas tripled (once 10x due to pipeline failures) + generators exercised market power (economic withholding + capacity withholding) → prices soared from the 1998-99 average of USD 30/MWh to USD 385.6/MWh in December 2000 and the market collapsed. Lesson: when supply is tight, price rises are themselves an allocative signal; suppressing them with caps damages long-run investment incentives.
- **Texas 2021 blackout**: the resource adequacy standard was designed for a "one-in-ten-years" event rather than more extreme scenarios; ERCOT has no capacity market and relies on scarcity pricing (price cap 9000 → lowered to USD 5000/MWh in 2021-09).
- **UK capacity market**: first auction GBP 19.4/kW·yr → GBP 8.4/kW·yr in 2018 → an auction was ruled unlawful and the market suspended — poorly designed capacity-mechanism parameters can self-destruct.
- **EU ETS Phase I**: over-allocation of allowances drove the price toward zero — cap setting is the lifeline of a carbon market.

---

## 2. Market System Architecture and Model Selection

> Chapter data cutoff: 2026-11-01 (unified market and southern regional market status); the market-model principles are not time-sensitive.

### 2.1 Four Product Categories + Five Time Dimensions
- **Products**: electric energy | generation capacity | ancillary services | transmission rights (PTR physical transmission right / FTR financial transmission right);
- **Time**: medium/long-term (multi-year to multi-day; NDRC Energy Regulation〔2020〕No. 889 (发改能源规〔2020〕889号, Basic Rules for Medium and Long-Term Power Trading)) → day-ahead (D-1, 96 or 48 periods) → intraday (15~60 min rolling) → real-time (5/10/15 min) → historical settlement (monthly/annual clearing);
- **Space**: inter-provincial (national dispatch (国调)/Beijing Power Exchange) + intra-provincial (provincial power trading centers/provincial dispatch (省级调度)), **"unified market, two-level operation"** — inter-provincial medium/long-term results form the boundary of the inter-provincial spot market; inter-provincial clearing results together with intra-provincial medium/long-term contracts form the intra-provincial spot boundary; intra-provincial pre-clearing results are reported upward to support inter-provincial clearing.

### 2.2 Centralized vs Decentralized (the core divide: how medium/long-term results are used in the spot market)

| Dimension | Centralized (US-style; mainstream in China's pilots) | Decentralized (European; UK/Nordic) |
|---|---|---|
| Medium/long-term | CfDs, used only for settlement | Mainly physical contracts (UK bilateral physical ~95%), self-decomposed curves |
| Spot | Centralized competition for all energy; SCUC/SCED sets commitment and prices | Bilateral + voluntary exchange; dispatch does no unit commitment |
| Real time | Real-time market (on-grid energy must clear in real time) | Real-time balancing mechanism (balances deviations only; ~2%~5% in the UK) |
| Pricing | Mostly LMP | System/zonal marginal price |
| Applicability | Much congestion, few flexible resources, high renewable share | Little congestion, many flexible resources, mature markets |
| Pros/cons | High allocative efficiency, unified signals; concentrated risk, high regulatory demands | Risk easily dispersed, simple logic; incomplete signals, inconsistent pricing across the three markets |

### 2.3 Four Functions of China's Spot Market
(1) price discovery to guide supply and demand (the price vane for medium/long-term trading); (2) promoting competition and optimizing allocation; (3) safeguarding operation and managing congestion (security constraints embedded in clearing, coupled with physical operation); (4) guiding quantified planning decisions (nodal/zonal prices provide locational investment signals).
**Positioning under Document No. 828** (NDRC General Office Energy Regulation〔2019〕No. 828 (发改办能源规〔2019〕828号, Notice on Deepening Electricity Spot Market Construction)): improve the market-based electricity-energy balancing mechanism and price formation mechanism — the spot market is not a "price-cutting tool" but a rebuilding of the pricing mechanism.

### 2.4 The 2026 Top-Level Design of the National Unified Electricity Market (new main thread)
- **State Council General Office Document〔2026〕No. 4 (国办发〔2026〕4号, Implementation Opinions on Improving the National Unified Electricity Market System, 2026-02)**: a national unified electricity market basically completed by **2030**, with market-traded electricity at about **70%** of total societal consumption; **spot markets fully in formal operation by 2027**; the unified market fully built by **2035**.
- Key formulations: "unified quoting, joint trading" (统一报价、联合交易) and "register once, share nationwide" (一地注册、全国共享); studying the establishment of a **national power trading center**; users at **10 kV and above** to participate directly in the market; coordinated linkage between inter-provincial and intra-provincial markets, between medium/long-term and spot, and between energy and ancillary services.
- Scale data (official): market-traded electricity in **January-September 2026 was 5.8536 trillion kWh (+18.9% YoY)**; **H1 2026 was 3.6848 trillion kWh (+24.2%)**; full-year 2025 was **6.64 trillion kWh (+7.4%, about 64.0% of total societal consumption)**.
- **Caliber warning**: the media figure "72.25% marketization rate in H1 2026" is calculated as 36,848/50,999; it is not an official direct caliber. Cite it as "calculated from public data".
- Implication for answers: on "progress of the national unified market", give the three milestones 2027/2030/2035 first, then separate "provincial spot market moving to formal operation" from "the national unified market being completed".

### 2.5 The Southern Regional Electricity Market (the first cross-provincial regional market)
- **Moved to formal operation on 2026-10-24**, covering Guangdong, Guangxi, Yunnan, Guizhou and Hainan; unified clearing, 15-minute prices, "register once, trade across the region"; **290,000+ market entities**; traded electricity of nearly **900 billion kWh in January-September 2026**.
- Relation to provincial markets: the southern regional market does not replace intra-provincial markets; it is unified optimization at the inter-provincial/regional level. Intra-provincial medium/long-term and spot trading still settle under provincial rules, while regional results form the inter-provincial boundary and price signal.
- Answering point: do not conflate the "southern regional market" with the "inter-provincial spot market" — the former is a regional unified-market entity, the latter a surplus-deficit mutual-aid mechanism between provinces; and do not treat it as "the national unified market already completed", which remains a 2027/2030/2035 three-step process.

---

## 3. Core Spot Market Mechanisms

> Chapter data cutoff: 2026-11-01 (price caps, pilot price features, 2026 rules status); clearing and pricing principles are not time-sensitive.

### 3.1 Timeline Structure and Clearing Process (15 steps of the centralized model)
Market registration → market preparation → publication of trading announcements → **day-ahead submission → day-ahead clearing (SCUC+SCED) → security check (iterated with clearing) → publication of day-ahead results** → real-time submission → **real-time clearing (SCED rolling every 5/15 min over the next 5 min~2 h)** → security check → publication → real-time operation (AGC execution) → energy metering → energy allocation → settlement of charges.
- Day-ahead: determines unit commitment and next-day schedules, 96 periods (one point per 15 min); objective is maximum social welfare (elastic load) or minimum procurement cost (rigid load);
- Intraday: fine-tunes schedules and fast start-stop decisions to cope with forecast deviations (only a few provinces such as Shandong have built intraday markets);
- Real-time: mainly provides adjustment means and economic signals for congestion management and ancillary services; in China, bids are mostly sealed at day-ahead;
- Clearing ⇄ security check is an **iterated coupling**: flow limit violations → add constraints and re-optimize → until feasible ("physical constraints take precedence over economic outcomes");
- Pre-clearing/pre-balancing: intra-provincial pre-clearing results are reported upward to support inter-provincial clearing — the glue coordinating the two-level market.

### 3.2 Clearing Algorithm Essentials
- **SCUC**: large-scale time-varying mixed-integer programming (unit on/off 0-1 variables; commercial solvers such as CPLEX), accounting for unit operating constraints (upper/lower limits, ramping, minimum up/down times and counts, vibration zones, fixed schedules), system balance and reserve constraints, and network constraints (corridor limits linearized via sensitivity/PTDF);
- **SCED**: nonlinear programming (piecewise linearized), rolling every 5 or 15 min in real time;
- Main cause of non-convergence: data quality (submitted lower limit > upper limit, missing ramp parameters — thermal default ~3 MW/min, hydro set to unit capacity) outweighs algorithm defects (when constraints conflict, add penalty terms and tier relaxable constraints);
- Load forecasting is the first input to clearing: system load forecasting determines total generation capacity requirement and the marginal price; bus load forecasting determines LMP and security-check accuracy; state estimation is the data foundation.

### 3.3 Pricing Mechanisms: SMP / ZMP / LMP

| Mechanism | Definition | Applicability | Characteristics |
|---|---|---|---|
| SMP system marginal price | Uniform pricing at the marginal unit's bid | Areas with little congestion | Stable, but small peak-valley spread, no locational signal |
| ZMP zonal marginal price | Clearing by congestion-separated zones | Nordic; chain-shaped grids | Zoning schemes may not be unique; loop-flow problems in meshed networks |
| LMP locational marginal price | The system's marginal cost of serving 1 MW more load at a node = marginal energy + congestion + loss components | US; areas with widespread congestion | Best reflects spatio-temporal scarcity; highly volatile |

- Convergence: with no congestion within a zone, nodal price = zonal price; with no congestion between zones, zonal price = system price;
- **The LMP is given by SCED dual variables (Lagrange multipliers)**: the multiplier of a corridor flow constraint is the congestion component; m binding congestion constraints → m+1 marginal units jointly set the price;
- Classic three-node example (unit 1 bids CNY 160/MWh with ample capacity, unit 2 bids 80 with 1500 MW, unit 3 bids 400 with 3000 MW): no congestion, whole network 160; with line 1-3 limited to 4000 MW, node 2 = 280 (weighted between two marginal units); with line 1-2 limited to 1000 MW, node 2 = 640 (added load aggravates congestion); with line 2-3 limited to 2000 MW, node 2 = −80 (negative price);
- **Causes of negative prices**: near-zero renewable marginal cost + subsidized projects bidding negative to win on-grid energy, thermal units constrained by minimum output bidding negative to keep dispatch rights, local congestion, insufficient flexibility; most common on weekends/holidays/past midnight/midday solar peaks — an embodiment of the price discovery function, best paired with demand response and storage for absorption.

### 3.4 Congestion Management, Congestion Surplus and Transmission Rights
- Four congestion management methods: **redispatch** (suits occasional congestion; arbitrage risk of low bids at the sending end), **market splitting/zonal pricing**, **nodal pricing** (mainstream in North and South America), **transaction curtailment** (least efficient);
- **Congestion surplus = (receiving-end price − sending-end price) × energy crossing the corridor**; example: an hourly settlement gap of CNY 1.68 million between the two ends should compensate the user side (some pilots settle at the generation-side weighted price, producing no surplus — a rule difference);
- **FTR financial transmission right**: holding F MW yields compensation of F×(π_receiving − π_sending), funded from the congestion surplus; an **obligation-type** right (must pay back when the spread is negative); auctions are subject to simultaneous feasibility; auction revenue is usually returned to users in proportion to load; a CfD locks price but not congestion — FTRs make up the locational value;
- **FGR flowgate right**: option-like (shadow cost μ≥0), equivalent to the FTR under perfect competition;
- Defects of physical PTRs: parallel paths (flows allocated inversely to reactance, PTDF) and rights hoarding as local market power; "use-it-or-lose-it" clauses came as a belated remedy;
- Losses: transmission 1%~3%, distribution 4%~9%; receiving-end marginal cost c(1+2DK) rises linearly with flow; in China losses are recovered within the T&D price, with no extra apportionment (NDRC Pricing〔2016〕No. 2711 (发改价格〔2016〕2711号); NDRC Pricing Regulation〔2017〕No. 2269 (发改价格规〔2017〕2269号)).

### 3.5 Price Caps and Market Circuit Breakers
- **Price cap theory**: proposed by Littlechild in 1983 (incentive regulation); pricing methods = accounting cost approach vs opportunity cost approach (internationally, the cap is set using **VOLL (Value of Lost Load, 失负荷价值)**);
- **China vs abroad (key difference)**: Chinese pilots set bid/clearing upper and lower limits, with caps around 3x the average spot price, following the accounting cost approach (Guangdong: bids 0~1000, clearing 70~1500; Shandong: 80~1300/80~1500; Zhejiang: −200~1200; Gansu: 0~1000; Shanxi: 0~1500, of which thermal 0~800 and renewables 0~740 CNY/MWh; Inner Mongolia West: 40~550/600); abroad there is generally no floor and the levels are extremely high (the 5 US markets unified at USD 1000/MWh ≈ 25~33x the average price; Australia AUD 10,000/MWh; England & Wales GBP 9,999/MWh);
- The cap dilemma: too high → market power abuse and balancing-account deficits; too low → masks scarcity signals and suppresses investment (the relatively low caps in China's pilots are one reason capacity market construction is urgent);
- **Circuit breaker** (Shanxi): announce within 2 h of trigger, duration ≤24 h; during the event thermal nodal prices are adjusted to the bid of the capacity segment where output falls, and renewable real-time prices are adjusted to the weighted average of thermal nodal prices — deployed live for 2 h in the 2021-04-15 sandstorm, validated as effective.
- **2026 price-limit developments**: Shandong's 2026-08-28 draft for comment proposes lowering the spot bid/clearing floor further to **CNY −0.12/−0.14/kWh** (not yet formal; cite as "draft"); Guangdong hit a real-time high of **CNY 0.978/kWh on 2026-04-11**, showing that near-cap extreme prices still occur within the band. The direction of wider limits is "make scarcity and negative-price signals more real", not simply lower prices.

### 3.6 Must-Run Units and Dispatch Discipline
- Six must-run situations: security constraints, voltage support, safeguarding power/heat supply and livelihood, government requirements, commissioning tests, fixed output; typical rules: coastal coal units must run 3 days before a typhoon landfall; de-icing units must run under freezing rain/snow conditions;
- Must-run periods do not participate in optimization; compensation = when the day's total revenue falls below the verified total generation cost (startup + variable incl. no-load + fixed), compensate per verified cost; the cost accounting also feeds market power monitoring;
- Maintenance scheduling principles: fairness, economy (off-peak maintenance), standardization, safety, discipline (annual/monthly submission, subject to dispatch coordination).

### 3.7 Look-Ahead: the 2026 Spot-Market Rules (proposed effective 2027-01-01; always separate draft from current rules)
- **Document status**: on 2026-10-19 the NDRC and NEA released the **Basic Rules for the Electricity Spot Market (Draft for Comment)**; comments close 2026-11-18 and it is **proposed to take effect 2027-01-01**. The text is compressed from 129 articles in the current Document No. 1217 to **76 articles**. For questions about 2026 practice, Document No. 1217 and provincial rules still govern; never treat the draft as current rules.
- **Seven directional changes**:
  1. **Price mechanism converging on LMP**: reduce signal inconsistency caused by zonal and nodal prices coexisting;
  2. **Financialization of medium/long-term contracts**: shift further toward CfDs and away from physical execution;
  3. **Institutionalized inter-provincial spot**: clearer boundaries, settlement and linkage between inter-provincial and intra-provincial spot markets;
  4. **Reliability unit commitment**: make reliability constraints explicit; capacity adequacy shifts from "scarcity pricing" to a "mechanism + market" combination;
  5. **Secondary price limits**: a second price boundary beyond the primary limit, balancing scarcity signals and market-power control;
  6. **Full participation of new entities**: VPPs, storage and load aggregators participate more directly in spot and ancillary services; **new energy plus co-located storage bid jointly**;
  7. **Simplified settlement**: abolish the imbalance fund pool and **switch quantity-difference settlement to price-difference settlement**, reducing cross-subsidy between accounts.
- **Implication for answers**: on post-2027 rule design, state that the formal text prevails; on 2026 operations, follow current provincial rules. The new rules are a long-term positive for VPPs/storage but raise the bar on forecasting, bidding and settlement capability.

---

## 4. Medium/Long-Term Trading and Electricity Financial Markets

> Chapter data cutoff: 2026-11-01 (status of Document No. 1656 and other rules, continuous green-power trading); contract structures and financial principles are not time-sensitive.

### 4.1 Basics of the Medium/Long-Term Market
- Definition (Document No. 889): wholesale trading at multi-year/year/quarter/month/week/multi-day horizons; **planned energy (priority generation (优先发电) + base quota energy (基数电量)) is incorporated into medium/long-term management**;
- **"Six Signings" (六签)** (NDRC Operations〔2020〕No. 1784 (发改运行〔2020〕1784号)): sign everything (contracted energy ≥95% of last year's actual consumption or the prior three-year average, relaxable to 90%), sign long (annual-based, encouraging 2~3 years or more), sign with witnesses (见签), sign by time segment, sign in a standardized way, sign electronically;
- Signing with curves is key: bilateral contracts decompose their own time-of-use curves; where only energy was signed without curves, typical consumption curves plus renewable forecasts are used;
- The 2025 revised Basic Rules for Medium and Long-Term Power Trading (NDRC Energy Regulation〔2025〕No. 1656 (发改能源规〔2025〕1656号)) added continuous-operation products such as green power D-3 and D-3 rolling matching (superseding the main body of Document No. 889); **national medium/long-term turnover in 2025 was 6.3522 trillion kWh**, including **328.5 billion kWh of green power**; **national market-traded electricity in 2025 was 6.64 trillion kWh (+7.4%, about 64.0% of total societal consumption)**.
- **Caliber warning**: the "2025 medium/long-term 4.81 trillion kWh" found in some materials is a specific subset (e.g. excluding grid agency power purchase, intra-provincial only). Always state the caliber and never juxtapose it with the 6.64 trillion market-traded figure. January-September 2026 market-traded electricity was **5.8536 trillion kWh (+18.9%)**, H1 **3.6848 trillion kWh (+24.2%)**; January-September 2026 green power trading was **249.2 billion kWh (+6.1%)**.

### 4.2 Contract for Differences (CfD) — the key to understanding China's spot market
- **China's mainstream pilot technical route = "medium/long-term CfDs + centralized competition for all energy"**: medium/long-term contracts are not physically executed; they are decomposed to days and settled as differentials against the spot price;
- Settlement formula: seller's contract revenue = Σ[(contract price − reference settlement price) × contracted energy]; total generator revenue = contract differential + day-ahead deviation × day-ahead price + real-time deviation × real-time price;
- Classification: market-based CfDs (financial institutions may participate) vs **government-authorized CfDs** (reform transition, curbing market power, protecting renewables and high-cost generation — Zhejiang's authorized contracts once covered ~90% of energy); one-way/two-way;
- International references: UK CfD + capacity market (Low Carbon Contracts Company (LCCC) two-way differentials with dynamically adjusted strike prices); Australia's authorized CfDs converted to bilateral contracts; Singapore's vesting contracts to mitigate market power; the Nordic combination of "forwards/futures + locational spread contracts (AFC)" for hedging.

### 4.3 Electricity Financial Markets
- **Futures**: standardized exchange contracts, physical delivery (trading stops before expiry) or cash settlement (benchmarked to a spot index; NYMEX/ICE settle on PJM data); peak-load/base-load contracts;
- **Options**: first introduced by NYMEX in 1996; the buyer pays a premium and holds the right without the obligation (asymmetric); European/American, Asian/barrier and other exotic types; Nordic financial trading has been run by Nasdaq since 2008, tenors up to 6 years, all cash-settled;
- **Virtual bidding (Virtual Bid/INC)**: buy/sell at the day-ahead price and close out in reverse in real time, arbitraging the day-ahead–real-time spread and converging the two markets; financial institutions are the main participants;
- Physical vs financial contracts: energy under physical contracts does not enter spot competition and is executed at the fixed price as submitted; energy under financial contracts still competes and is only financially settled — Guangdong in 2017 assessed positive/negative deviations at twice the monthly bidding spread (a physical-contract mindset); under the centralized model there is no deviation assessment on medium/long-term contracts.
- **China progress (an important boundary)**: power futures and carbon futures remain at the research/preparation stage and are **not yet listed for trading**; the Guangzhou Futures Exchange has completed the design of a carbon futures contract but there is no official listing timetable. The risk-management tools actually available in China are medium/long-term contracts, CfDs, spot deviation settlement and ancillary services; do not treat NYMEX/ICE/Nordic futures and options as domestically operable tools. The 2026-10-19 spot-rules draft's "financialization of medium/long-term contracts" is an institutional signal toward financial instruments, not evidence that futures are listed.

### 4.4 The Core Logic of Linkage
**The transparency and stability of the spot mechanism determine medium/long-term liquidity**: the US once hit major turbulence because its spot market was imperfect; the UK saw market liquidity decline as generation-retail integration deepened; the Nordic financial sector held no special advantage, yet its medium/long-term market stayed robust over the long run thanks to sound spot design. Implication for China: build the spot market first — only then does medium/long-term financialization have a foundation.

---

## 5. Ancillary Services and Capacity Mechanisms

> Chapter data cutoff: 2026-11-01 (capacity-price execution values, ancillary-service rules, system operation fee); pricing principles are not time-sensitive.

### 5.1 Spectrum of Ancillary Service Products
- Classification: basic (primary frequency regulation, basic peak regulation, basic reactive power — unpaid) vs compensated (AGC, compensated peak regulation, spinning reserve (callable within 10 min), compensated reactive power, black start, etc.);
- Three functional categories: active-power balancing (frequency regulation/reserve/peak regulation), reactive power and voltage, and service restoration (black start);
- **The "Two Rules" (两个细则)** (originally SERC 2006; current versions NEA Regulatory Regulation〔2021〕No. 60/61 (国能发监管规〔2021〕60/61号)): essentially a mutual-aid compensation mechanism rather than a market, with the scope of administration extended to all grid-connected entities at 35 kV and above; products added include AVC, low-frequency regulation (East China 49.93 Hz), hot standby, fast load rejection, planned shutdown/cold standby (Northwest/Southern 72 h), and stability-control unit tripping; once the spot market is built, these must be unbundled from integrated energy pricing;
- **Peak regulation (调峰) is a uniquely Chinese product** (abroad it emerges naturally from the real-time market/balancing mechanism): originated in the 2006 Two Rules → 2014 the Northeast's first peak-regulation market → 2019 full coverage in the Northeast of "valley-filling, peak-topping" → substitutable by spot time-of-use prices → **the 2025 Basic Rules for the Electricity Ancillary Services Market explicitly shut down peak-regulation markets in regions with continuous spot operation**, with costs shared to the user side; at publication, 16 provinces had peak regulation, 15 frequency regulation, 2 ramping, and 6 regional markets nationwide.
- **2026 provincial changes**: Fujian's 2026-04-03 revision of ancillary-service rules includes VPPs/storage as market entities and cancels deep-peaking compensation once spot prices reflect value; Shandong allows storage/VPPs to participate in energy and ancillary services simultaneously from 2026-05-08; the frequency-regulation mileage price cap is about CNY 0.015/kW with a performance-coefficient cap of 2; reserves settle as "capacity × time"; ramping and inertia products are being explored in some regions. Confirm the province first; do not let the old "Two Rules" override 2026 provincial rules.

### 5.2 Clearing and Pricing
- **Sequential clearing** (with "energy first, reserve after" as the mainstream; frequency regulation ranked by performance-adjusted bids): simple and easy to supervise, but it buries opportunity cost and can produce quality-price inversion — used in the early stage;
- **Joint clearing** (energy + reserve + frequency regulation optimized in one pass, minimizing total procurement cost): more economical; coupling constraints such as "energy award + frequency-regulation award ≤ maximum technical output, energy award − frequency-regulation award ≥ minimum technical output"; **rank price = submitted price + energy-market opportunity cost**;
- The reserve price is essentially the redispatch opportunity cost: example reserve price 11 = 28−17 (energy price spread); with separate bids the energy price need not equal any unit's marginal cost (22 = 20−5+7);
- Frequency regulation revenue = actual regulation depth × performance index × settlement price (capacity payment + mileage payment; FERC Order 755 pays for performance); frequency regulation performance indices include delay, tracking fidelity, and system average mileage ratio;
- PJM reference: the ancillary services market closes 1 hour ahead of real time, cleared jointly with energy every 5 min; frequency regulation obligations are borne by LSEs in proportion to load.

### 5.3 Four Paths of Capacity Mechanisms (the core of recovering generation investment)

| Mechanism | Representative | Pros | Cons |
|---|---|---|---|
| Scarcity pricing/price spikes | ERCOT (Texas), Australia | Theoretically optimal, no administrative intervention | Price spikes reach VOLL magnitude (tens of thousands per MWh), politically infeasible, investment-cycle volatility |
| Capacity cost compensation | Chile, Shandong (mainstream in China) | Stable, low implementation cost | Insufficient marketization, not tied to performance |
| Capacity market | UK, PJM (RPM), NYISO | Capacity price formed by competition | Complex design, hard to prevent manipulation (time-horizon dilemma + free riding) |
| Reliability contracts | Vazquez scheme (long-term options + penalties) | Minimal intervention, incentivizes availability | Requires centrally organized auctions |

- **Coal power capacity price (容量电价)** (NDRC Pricing〔2023〕No. 1501 (发改价格〔2023〕1501号, Notice on Establishing a Capacity Price Mechanism for Coal Power), effective 2024-01-01): fixed cost set uniformly at CNY 330/kW·yr, ~30% recovered in 2024-2025 (≈CNY 165/kW·yr), **≥50% from 2026**. CNY 165/kW·yr is the mainstream value of the 50% floor, not a nationwide uniform price. Verified 2026 values (level B/C): Guangdong 165; Tianjin/Sichuan 231; Qinghai 185; Guangxi 247.5; Jilin/Heilongjiang/Hunan/Gansu/Yunnan 330 (Henan's 330 is still a draft); **Liaoning's 370 is a "reliable capacity compensation", a different caliber from the coal capacity price**. Verify province by province and state the source level; the fee is apportioned to commercial and industrial users through system operation fees.
- **NDRC Pricing〔2026〕No. 114 (发改价格〔2026〕114号, 2026-01-30) — capacity price 2.0**: coal capacity recovery ≥50%; establish a gas capacity price; improve pumped-storage capacity pricing; **grid-side independent storage capacity price = local coal capacity price × (full-power continuous discharge duration ÷ longest net-load peak duration), capped at 1x**; list-based management, with no payment outside the list. At least 13 provinces have implemented or drafted it: Shaanxi, Xinjiang and Anhui at CNY 165/kW·yr for 6 hours; Henan's draft is CNY 330/kW·yr. The independent-storage capacity price makes "duration value" explicit and is the biggest variable in 2026 storage revenue models.
- **System operation fee**: the national average in Q1-Q3 2026 was about **CNY 0.068/kWh, roughly +93% YoY**; capacity prices, ancillary services and imbalance funds are passed to the user side, directly raising retailers' purchase cost — an important mechanism behind 2026 retail-side losses (see 11.2).
- Stranded cost treatment tools: asset portfolio restructuring, CfDs, transition electricity surcharges (adding ~8%~12% to the bill), securitization (CCC→SPV→SCB), and capacity-market recovery netted via Net CONE;
- Peaker logic: a 50 MW old oil unit running 5 h/yr must bid above USD 1000/MWh to cover its full cost — explaining the inevitability of scarcity pricing.

---

## 6. Settlement, Metering and Imbalance Funds

> Chapter data cutoff: 2026-11-01 (settlement rules and the "abolish the imbalance fund pool" proposal follow the 2026 draft rules); settlement formulas and metering principles are not time-sensitive.

### 6.1 Settlement Framework
- **Daily clearing, monthly settlement**: daily allocation (bookkeeping only), monthly settlement (actual payments), annual reconciliation; 15 min/hour as the basic settlement period;
- **Nine settlement categories** (NDRC Energy〔2018〕No. 1518 (发改能源〔2018〕1518号)): electric energy, ancillary services, demand-side response, deviation, cost compensation, surplus and balancing, transmission-distribution charges, capacity market, administrative fees and surcharges;
- **Centralized settlement formula (three-part generation revenue)**: revenue = medium/long-term differential + (day-ahead cleared energy − medium/long-term daily decomposed energy) × day-ahead price + (actual energy − day-ahead cleared energy) × real-time price; the user-side unified settlement point price is symmetric by the same logic;
- PJM reference: day-ahead full quantity + real-time deviation + CfD settlement; load settled via LSEs at weighted nodal prices; frequency regulation fee = capacity fee + mileage fee (each multiplied by the performance index); congestion surplus allocated per FTRs.

### 6.2 Market Operating Fees and Imbalance Funds
- Three types (apportioned monthly): **cost compensation** (startup, must-run units, frequency regulation volume-price compensation — among users by consumption share, renewables by on-grid energy share); **market balancing** (structural balance, congestion balance, dual-track (双轨制) generation price subsidy); **market adjustment** (recovery of excess profits, recovery of medium/long-term shortfalls);
- **Four major imbalance funds**: dual-track imbalance funds (mismatch between planned and market energy curves), congestion surplus, cost compensation fees, and others (deviation assessment, metering errors);
- **Discipline: no imbalance fund pools may be set up**; categories recorded independently, apportioned and dissipated item by item, settlement documents marking fund flows with plus/minus signs (Guidelines for Electricity Market Construction Work (《电力市场建设工作指引》), 2020-10);
- "Two Rules" electricity charge = ancillary fees − assessment fees − apportioned fees + returned fees.

### 6.3 Metering (the foundation project of the spot market)
- Basis DL/T 448-2016: boundary-meter (关口表) load records at 15-min or settlement-period intervals; generators and Class I/II/III important users each install one main and one backup meter; BeiDou/GPS time synchronization;
- **Metering granularity leaps from monthly meter reading to 15 minutes (~3000x)**; data backfill completeness must be ≥98%;
- Missing-data fitting (Shanxi rule, Shanxi Energy Regulatory Market Letter〔2020〕No. 45 (晋监能市场函〔2020〕45号)): fit if data are still absent at D+3; ≤2 missing points take the interval mean, >2 points fit by the year-on-year average of same-attribute days (user holidays use the same-type day of last year); if fitted total energy across settlement periods deviates beyond ±5% (generation)/±10% (users), handle as retroactive recovery;
- Entity confirmation discipline: monthly settlement bills **deemed non-objection if overdue, automatically confirmed by the system** — watch confirmation deadlines and dispute evidence.

---

## 7. China Policy Framework and Provincial Practice (as of 2026-11-01)

### 7.1 Policy Document Timeline (the essential backbone)

> Status convention: **formal** = issued and in force; **draft** = circulated for comment and not to be cited as current rules; **proposed** = date set but not yet effective; **superseded** = no longer applicable. The full index (issue date, effective date, status, supersession) is in `knowledge/索引与口径-2026-11.md`; this table keeps only the answering backbone.

| Phase | Document | Key points |
|---|---|---|
| 2002 | State Council〔2002〕No. 5 (国发〔2002〕5号, Power Sector Reform Scheme) | Separation of generation and grid; start of bid-based dispatch |
| 2015 | **CPC Central Committee & State Council〔2015〕No. 9 (中发〔2015〕9号, Opinions on Further Deepening the Power System Reform)** | The new-reform blueprint: regulate the middle, open the two ends; 6 supporting documents incl. No. 2752 |
| 2015-2017 | NDRC Pricing〔2015〕No. 742 (发改价格〔2015〕742号); No. 1453 | T&D price reform; 8 spot pilots (Southern grid starting with Guangdong, plus Inner Mongolia West, Zhejiang, Shanxi, Shandong, Fujian, Sichuan, Gansu) |
| 2019-2020 | Document No. 828; Document No. 889; No. 1784 "Six Signings" | Spot deepening; medium/long-term rules; full signing |
| 2023 | **NDRC Energy Regulation〔2023〕No. 1217 (发改能源规〔2023〕1217号, Basic Rules for the Electricity Spot Market (Trial))** | First national spot rule (note: often miscited as "No. 813"; No. 813 is a supporting notice requiring continuous operation of medium/long-term trading from D-7 to D-2 in spot regions) |
| 2023-11 | NDRC Pricing〔2023〕No. 1501 | Coal power capacity price mechanism |
| 2024 | **NDRC Order No. 20 of 2024** (Basic Rules for Electricity Market Operation) (effective 07-01) | First departmental rule; confirms new market entities such as storage/VPP/load aggregators; three trading categories: energy + ancillary services + capacity |
| 2025-02 | **NDRC Pricing〔2025〕No. 136 (发改价格〔2025〕136号, Notice on Deepening Market-based Reform of New Energy Grid Electricity Prices)** | Renewables' on-grid energy in principle enters the market in full (see Chapter 8) |
| 2025-03 | NDRC Energy〔2025〕No. 357 (发改能源〔2025〕357号) | Guiding Opinions on the Development of Virtual Power Plants (see Chapter 9) |
| 2025-04 | Basic Rules for the Electricity Ancillary Services Market; NDRC General Office Institutional Reform〔2025〕No. 394 (发改办体改〔2025〕394号) | Peak-regulation market shuts down in continuous-spot regions; timetable for Hubei/Zhejiang going official |
| 2025 | NDRC Energy Regulation〔2025〕No. 1656 | New medium/long-term rules; green power D-3 continuous operation |
| 2026-01 | **NDRC Pricing〔2026〕No. 114 (发改价格〔2026〕114号)** | Coal capacity ≥50%; gas, pumped-storage and grid-side independent-storage capacity prices (see 5.3) |
| 2026-02 | **State Council General Office〔2026〕No. 4 (国办发〔2026〕4号)** | National unified market: spot fully formal in 2027, basically completed in 2030, fully built in 2035 |
| 2026-05 | NDRC Energy〔2026〕No. 688 (发改能源〔2026〕688号) | Multi-user green direct connection (see Chapter 8; VPP skill 8.5) |
| 2026-08 | Provincial supporting rules ahead of the spot-rules draft | Hebei South, Anhui, Shaanxi and Fujian spot markets go formal; Shandong, Liaoning, Fujian and Anhui VPP rules |
| 2026-09 | Retailer Management Measure (draft); Electricity Market Risk-Control Measure (draft) | Retail access, exit, risk reserve, wholesale-retail inversion monitoring (see 11.2, 11.6) |
| 2026-10 | **Basic Rules for the Electricity Spot Market (draft for comment)**; National Unified Market Credit Evaluation Guidelines (draft) | 129→76 articles, proposed effective 2027-01-01; credit evaluation (see 3.7) |
| 2026-12-01 | **NDRC Order No. 50, Measures for the Administration of Medium/Long-Term Energy-Supply Contracts (Trial)** | Institutionalizes signing, performance and supervision of energy-supply contracts |

### 7.2 Provincial Spot Markets in Formal Operation (as of 2026-10-31)

> The full per-province status (spot / No. 136 auction / capacity price / VPP rules / ancillary services / retail risk) is in `knowledge/省级市场状态表-2026-11.md`; this table lists only spot markets already in formal operation.

| Market | Formal operation since | Notes |
|---|---|---|
| Shanxi | 2023-12-22 | First in China |
| Guangdong | 2023-12-28 | First simulation in 2018-08 |
| Shandong | 2024-06-17 | High renewable share, longest negative-price hours |
| Gansu | 2024-09-05 | Went formal after ~40 months of continuous settlement trial operation |
| Inner Mongolia West | 2025-02-24 | First "single-track" (单轨制) market (all-energy spot) in China |
| Hubei | 2025-06 | Marking the Document No. 394 node |
| Zhejiang | 2025-08-07 | First in the Yangtze River Delta; 463 days of continuous settlement trial |
| Hebei South | 2026-08 | Important provincial market in North China |
| Anhui | 2026-09-09 | East China |
| Shaanxi | 2026-09-25 | Northwest |
| Fujian | 2026-09-30 | High clean-energy share |
| **Southern region** | **2026-10-24** | Unified clearing for Guangdong/Guangxi/Yunnan/Guizhou/Hainan; a regional, not single-province, market (see 2.5) |

- By 2026-09-30, **at least 11 provincial markets** had moved to formal operation; the southern regional market followed on 2026-10-24. Sources disagree on "the 10th/11th" wording — **give the date, not an ordinal**, to avoid being led astray by source differences.
- The inter-provincial spot market is in formal operation; Sichuan, Liaoning, Chongqing, Hunan and others remain in continuous settlement trial/promotion. By 2026, provincial spot markets have essentially achieved full coverage.
- **Data caliber**: 2025 national market-traded electricity was 6.64 trillion kWh (about 64.0% of total societal consumption); January-September 2026 was 5.8536 trillion kWh (+18.9%). Do not conflate "the number of provinces whose spot market has gone formal" with "the national unified market being completed" — the latter is 2030 basic completion and 2035 full completion under State Council General Office〔2026〕No. 4.

### 7.3 Features of the First Pilot Batch (understanding "tailoring to local conditions")
- **Zhejiang**: government-authorized CfDs covering ~90% of energy for a smooth transition; "dual-differential" (双差价) settlement; users opened in three stages starting from 110 kV;
- **Shanxi**: pioneered the fusion of spot and peak regulation (deep-peaking market suspended upon continuous settlement from 2020-11); 31 units retrofitted for flexibility, adding 2.27 million kW of downward regulation; price limits progressively relaxed from 0~332 to 0~1500 CNY/MWh; first practical circuit-breaker activation nationwide;
- **Shandong**: pioneered the capacity compensation price (charged to users to compensate market-based units' fixed costs); negative prices and "five-tier" (五段式) time-of-use pricing (deep-valley discount of 90%);
- **Sichuan**: wet/dry season split — hydropower competes in the wet season and thermal in the dry season, with a "no water spilled" principle for run-of-river plants;
- **Fujian**: full consumption of clean energy (51.57% of installed capacity) + full delivery of medium/long-term contracts; clean energy scheduled first in the day-ahead as the boundary;
- **Gansu**: the "fishing method" (钓鱼法) — minute-level monitoring of renewable completion rates, clawing back undelivered schedules and reallocating to those that delivered; with a high renewable share, energy first, then frequency regulation.

### 7.4 2025-2026 Price Characteristics (market sensing)
- **2025**: spot averages fell broadly: Guangdong user-side average settlement price CNY 0.3803/kWh (−14.2%), day-ahead average declared price 319.0 li/kWh (厘); **Shandong negative prices exceeded 1500 hours for the year** (touching the −80 CNY/MWh floor for ~1145 h); 2025-04 solar spot settlement average ~CNY 0.02/kWh; Shanxi peak-valley spread +43% YoY, the largest in China (average spread ~0.3~0.5 CNY/kWh); Inner Mongolia West the only one narrowing (−14%).
- **January-September 2026**: Shanxi day-ahead 161-450 CNY/MWh, real-time 174-609 CNY/MWh; Guangdong day-ahead 425-696 li/kWh, real-time 372-727 li/kWh; Shandong 348-477 CNY/MWh; Inner Mongolia West 315-521 CNY/MWh. Regional divergence is widening: Shanxi and Inner Mongolia West real-time prices probe upward while Shandong remains suppressed by renewable output.
- **2026 extreme events**: Shandong had about 199 negative-price hours in 2026-04; the 2026-08-28 draft proposes lowering the spot floor to CNY −0.12/−0.14/kWh; Guangdong's real-time price reached CNY 0.978/kWh on 2026-04-11, near the cap.
- Overall trend: midday negative prices spreading, peak-valley spreads widening, extreme prices widening in both directions → rising value of storage "charge low, discharge high", flexible load and VPPs; but wider limits also mean larger deviation-settlement and risk exposure.
- **International benchmark correction**: PJM's **2027/28** capacity auction cleared at **USD 329.17/MW-day** (at the cap); the **2028/29 BRA (2026-07-14) cleared at USD 325/MW-day**, the third consecutive cap, with a 6.8 GW shortfall, a 14.7% reserve margin, about USD 16.4 billion in total cost and only ~500 MW of new supply. ERCOT's 2025 real-time average was about USD 38/MWh. Do not label 329.17 as 2028/29.

---

## 7A. Overseas Markets Quick Reference (Australia NEM / Germany / UK GB / Italy / Spain / France / Netherlands / Poland / Belgium & Nordics / United States / Japan)

> Chapter data cutoff: 2026-11-11. The 7A numbering avoids renumbering the existing China chapters. Coverage is the Australian NEM, the German DE-LU bidding zone, UK GB, Italy, Spain, France, the Netherlands, Poland, Belgium/the Nordics, the United States (ERCOT/PJM/CAISO) and Japan, not "all overseas markets". Trading is governed by local law, rules, exchange notices and contracts; this chapter is not legal, tax or investment advice.

### 7A.1 Market Selection: Six Core Cards

| Dimension | Australian NEM | German DE-LU | UK GB | Italy | Spain | Netherlands |
|---|---|---|---|---|---|---|
| Scope | Five regions: QLD, NSW (incl. ACT), VIC, SA, TAS | Germany + Luxembourg, one bidding zone in EU coupling | England, Scotland, Wales; Northern Ireland excluded | Seven mainland bidding zones + cross-border virtual zones | Spain + Portugal, two bidding zones in MIBEL | One bidding zone (EPEX NL) |
| Operator / rules | AEMO operates; AEMC makes rules; AER regulates | EPEX Spot trades; four TSOs balance/redispatch; BNetzA regulates | NESO system operation; Ofgem regulates; Elexon settles | GME exchange; Terna dispatch; ARERA regulates | OMIE market; REE dispatch/capacity; CNMC/MITECO regulate | EPEX NL trades; TenneT dispatch; ACM regulates |
| Spot granularity | 5-minute dispatch + 5-minute settlement | Day-ahead/intraday 15-minute MTU; balancing 15 minutes | Half-hourly settlement; EPEX GB hourly + GB-30min | MGP 15-minute MTU; MI/MSD/MB layers | 15-minute MTU; 15-minute imbalance settlement | 15-minute MTU; 15-minute imbalance |
| Pricing | Regional prices + constraints; energy/FCAS co-optimized | Day-ahead pay-as-clear; intraday pay-as-bid | Day-ahead uniform price; BM pay-as-bid | Zonal marginal prices; MSD/MB per rules | Day-ahead uniform price; intraday pay-as-bid | Day-ahead uniform price; intraday pay-as-bid |
| Price bounds | 2026-27 MPC A$23,200/MWh; CPT A$2,225,900/MWh; APC A$600/MWh; MFP -A$1,000/MWh | Day-ahead floor -€500/MWh; intraday floor -€9,999/MWh | No administered wholesale band; CM cap £75/kW·yr | Per current GME/ARERA rules | Day-ahead -€600/+€4,000; intraday ±€9,999 | Per EPEX/EU rules; intraday floor around -€9,999/MWh |
| Ancillary services | FCAS (regulation + contingency) | FCR, aFRR, mFRR; capacity and energy separate | DC/DM/DR, SFFR, QR/SR/BR, DFS | MSD/MB; procured by Terna | aFRR, mFRR, voltage control, black start | FCR, aFRR, mFRR; procured by TenneT |
| Capacity | No centralized capacity market; RRO/RERT/CIS | StromVKG capacity mechanism from 2031 | T-4/T-1 capacity market, £/kW·yr | Capacity market + MACSE | 2026 capacity market, peninsular system | No capacity market (studied, not implemented) |
| Renewables support | LGC/SRES, CIS, state schemes | EEG auctions + sliding market premium | CfD, LDES cap and floor | FER X two-way CfD | PNIEC, RD 997/2025, RDL 7/2026, auctions | SDE++ (no standalone battery category) |
| Congestion | Regional prices + constraints + MLF/IRLF | Single zone + Redispatch 2.0 | BM + network constraints; TNUoS signal | Seven-zone spreads + MSD/redispatch | Two-zone spreads + redispatch/technical constraints | Connection queue + non-firm contracts + congestion management |
| Settlement | Weekly statements; MLF/IRLF; prudential | ECC clearing + balancing-group imbalance + grid fees | Elexon/BSC, half-hourly; multi-run reconciliation | GME/Terna + credit support | OMIE/REE, 15 minutes; credit support | EPEX/TenneT, 15 minutes; credit support |
| Entry | AEMO registration + metering + prudential | Local entity + REMIT + balancing group + EPEX/ECC | Entity + Ofgem licence/exemption + BSC + BMU + CM + REMIT | Entity + GME membership + Terna BRP/BSP + MACSE + REMIT | Entity + grid connection + OMIE registration + REE BRP + credit + REMIT | Entity + grid connection + EPEX + BRP + credit + REMIT |

**7A.1b New Market Cards (Poland / Belgium / Nordics)**

| Dimension | Poland | Belgium | Nordics |
|---|---|---|---|
| Scope | One Polish bidding zone | One Belgian bidding zone | 12 zones: NO1–NO5, SE1–SE4, DK1–DK2, FI |
| Operator / rules | TGE trades; PSE dispatches; URE regulates | Belpex/EPEX trades; Elia dispatches; CREG regulates | Nord Pool trades; Statnett/SvK/Energinet/Fingrid dispatch; national regulators |
| Spot granularity | 15-minute MTU; 15-minute imbalance | 15-minute MTU; 15-minute imbalance | 15-minute MTU; 15-minute imbalance + mFRR EAM since 2025-03-04 |
| Pricing | Day-ahead pay-as-clear; intraday pay-as-bid | Day-ahead uniform price; intraday pay-as-bid | Day-ahead system price + zonal prices; intraday pay-as-bid |
| Price bounds | EU SDAC/SIDC; day-ahead floor around -€500/MWh, intraday ±€9,999/MWh | Same EU SDAC/SIDC | Same EU SDAC/SIDC |
| Ancillary services | FCR, aFRR, mFRR, RR; procured by PSE | FCR, aFRR, mFRR; procured by Elia | FCR-N/FCR-D, aFRR, mFRR; procured by national TSOs |
| Capacity | rynek mocy auctions; 2030 delivery year PLN 465.02/kW·yr | CRM Y-4/Y-2/Y-1; Y-4 cleared 4,690 MW | Sweden effektreserv, Finland tehoreservi; no capacity market in Norway/Denmark |
| Renewables support | OZE auctions (15-year CfD); 76.1 TWh / PLN 24.9bn in 2026 | Offshore wind CfD; no standalone battery subsidy | National auctions/CfD; Danish offshore 20-year CfD |
| Congestion | Connection queue + cross-border capacity | Connection/permitting + interconnection | Zonal spreads + interconnectors + EPAD |
| Settlement | TGE/IRGiT + PSE imbalance + capacity fee + OZE settlement | Belpex/Elia + CRM + grid fees | Nord Pool + national TSOs + Nasdaq financial settlement |
| Entry | Entity + URE licence + PSE/OSD connection + TGE/IRGiT + POB + PSE prequalification + capacity registration + REMIT | Entity + Elia connection + Belpex/EPEX + BRP + CRM qualification + REMIT | Entity + TSO/DSO connection + Nord Pool membership + national BRP + prequalification + REMIT |

**7A.1c United States and Japan Cards**

| Dimension | US ERCOT | US PJM | US CAISO | Japan |
|---|---|---|---|---|
| Scope | Intrastate Texas system | 13 states + Washington DC | California + EDAM members | 10 service areas + wide-area operation |
| Operator / rules | ERCOT operates; PUCT regulates; wholesale rates outside FERC jurisdiction | PJM operates; FERC tariff; state PUCs for distribution/siting | CAISO operates; FERC + CPUC/CEC overlay | JEPX/EPRX trade; OCCTO wide-area; METI regulates |
| Spot granularity | Day-ahead hourly + real-time SCED 5 minutes; 15-minute settlement | Day-ahead + real-time; settlement by product | Day-ahead hourly + FMM 15 minutes + RTD 5 minutes | 48 half-hour products; 30-minute imbalance |
| Pricing | Nodal + ORDC; HCAP $5,000 / LCAP $2,000/MWh | Nodal + capacity; BRA by LDA | Nodal/zonal + RA; day-ahead uniform price | Blind auction uniform price; floor ¥0.01/kWh (no negative prices) |
| Ancillary services | Reg Up/Down, RRS, Non-Spin, ECRS | Regulation, synchronized reserve, DASR | FRP, regulation, reserve | EPRX primary/secondary/tertiary + combined |
| Capacity | None; ORDC scarcity pricing | BRA/FRR; 4-hour battery ELCC ~50% | No centralized market; RA slice-of-day/NQC | Capacity market (4 years ahead, single price, 1 year) + LTDA (20 years, 90% clawback) |
| Support | Federal ITC; state schemes | Federal ITC; state schemes | Federal ITC; state schemes | FIT/FIP, non-fossil certificates, SII battery grants |
| Settlement | 15 minutes; weekly/monthly statements | By product; capacity monthly | 5 minutes; RA annual/hourly | 30 minutes; capacity annual, LTDA 20 years |
| Entry | ERCOT registration + interconnection agreement | PJM registration + capacity qualification + interconnection | CAISO registration + RA qualification + interconnection | Generation notification + supply-adjustment contract + JEPX/EPRX + FEFTA |

**7A.1d France Card**

| Dimension | France |
|---|---|
| Scope | One mainland French bidding zone (FR), embedded in EU day-ahead/intraday coupling; overseas territories are separate systems |
| Operator / rules | EPEX Spot trades; RTE dispatches/balances; CRE regulates capacity and tenders |
| Spot granularity | Day-ahead/intraday 15-minute MTU (since 2025-10-01); 15-minute imbalance settlement |
| Pricing | Day-ahead SDAC uniform price; intraday continuous pay-as-bid |
| Price bounds | EU SDAC/SIDC bounds; intraday floor around -€9,999/MWh |
| Ancillary services | MA fast (<13 min)/complementary (<30 min), FCR, aFRR, mFRR |
| Capacity | RTE single buyer; PL-1 delivery-period auction + PL-4 multi-year (up to 15 years) |
| Renewables support | CRE CfD tenders (~58); ARENH ends 2025-12-31; VNU is a price-regulation mechanism, not a floor |
| Congestion | Single zone + interconnection/redispatch; grid-connection framework reform by end-2026 |
| Settlement | EPEX/ECC + RTE imbalance + capacity contracts; 15 minutes |
| Entry | French/EU entity + RTE BRP + CRE capacity certification + IEF review + REMIT |

**Selection rule of thumb**: high volatility, batteries/FCAS and inter-regional spreads → NEM first; day-ahead/intraday, cross-border coupling, balancing and EEG assets → Germany first; single market, capacity market, BM and LDES → UK first; seven-zone spreads, MACSE long-term storage auctions and FER X → Italy first; Iberian two-zone design, 15-minute settlement and a 2026 capacity market → Spain first; nuclear baseload, RTE single-buyer capacity mechanism and PL-1/PL-4 → France first; one bidding zone, no capacity market, congestion access and SDE++ → Netherlands first; capacity market + OZE auctions + storage grants → Poland first; CRM annuities + zonal hydro + negative prices → Belgium/Nordics first; energy-only scarcity pricing and real-time spreads → ERCOT, capacity market and ELCC → PJM, day-ahead/real-time + RA + Western market → CAISO; 30-minute spot + capacity market + 20-year LTDA → Japan. None of the eleven is "register and trade": settlement, balancing responsibility, connection and compliance are the real barriers.

### 7A.2 Australian NEM: Five Must-Knows

1. **Five regions, five prices**: QLD, NSW, VIC, SA, TAS; prices separate when constraints bind. A "national average" backtest is misleading.
2. **Five-minute settlement**: 5MS since 2021-10-01; pre-2021 30-minute prices are not directly comparable. NEM time is fixed AEST (UTC+10), with no daylight saving, and the trading day rolls at 04:00.
3. **FCAS is co-optimized with energy**: the same MW cannot sell energy and FCAS simultaneously; FCAS reservation consumes SOC/headroom and has an opportunity cost.
4. **Three price layers**: normal market uses MPC/MFP; cumulative prices above CPT trigger an administered price period with APC/AFP; MPC/CPT are CPI-indexed annually.
5. **Settlement is not "regional price × energy"**: apply MLF (generation) / IRLF (interconnectors), and allow for settlement residues, prudential and weekly statements.

**Three formulas**

```
Generation settlement ≈ dispatch price × settled energy × MLF
CfD cash flow = (spot price − strike) × contracted volume
FCAS opportunity cost ≈ reserved MW × contemporaneous energy price × reserved hours
```

**Entry path**: local entity → AEMO registration (Generator/Market Customer/IESS, etc.) → metering → prudential → (retail) AER authorisation → NEMWEB/market systems. **Common errors**: treating pre-dispatch as settlement, ignoring MLF, reconciling in local time, applying WA/NT rules to the NEM.

### 7A.3 Germany DE-LU: Six Must-Knows

1. **The German price is an EU-coupled price**: DE-LU is one bidding zone in the EU day-ahead coupling (SDAC); neighbour supply/demand, cross-border capacity and EU ETS all feed into it.
2. **Day-ahead and intraday price differently**: the day-ahead auction closes at 12:00 CET, clears via EUPHEMIA and is pay-as-clear; intraday continuous trading is pay-as-bid with a much deeper floor (-€9,999/MWh).
3. **Fifteen minutes is the basic granularity**: since 2025-10-01 SDAC has used a 15-minute MTU in most zones; Germany has 15-minute products in both day-ahead and intraday, so old hourly models will be wrong.
4. **Balancing separates capacity and energy**: FCR is capacity-only, symmetrical and pay-as-clear; aFRR/mFRR capacity is procured daily in 4-hour blocks on a pay-as-bid basis, while energy is 15-minute and pay-as-clear (PICASSO/MARI); minimum bid 1 MW.
5. **Redispatch is not spot**: Redispatch 2.0 has covered units ≥100 kW since 2021-10-01; TSOs/DSOs instruct units to relieve congestion and compensate under regulatory rules, not through EPEX.
6. **The EEG negative-price rule has no 4/6-hour threshold**: the applicable value drops to zero in negative-price periods; the EEG surcharge has been zero since 2022-07-01 (§60 repealed); the capacity mechanism only starts in 2031.

**Three formulas**

```
Day-ahead purchase cost = day-ahead price × energy
EEG negative-price impact ≈ negative-price energy × AW + negative-price energy × negative price
Industrial PPA saving = (spot average − PPA price) × consumption
```

**Entry path**: German/EU entity → (retail) EnWG §5 licence → EPEX membership/broker + ECC clearing → REMIT registration → TSO balancing group (BKV) → MaStR/EEG registration → balancing-market prequalification. **Common errors**: confusing day-ahead with intraday, ignoring CET/CEST, treating FCR as an energy market, assuming the EEG surcharge still exists, treating the capacity mechanism as already operating, ignoring grid fees/§14a and REMIT.

### 7A.4 UK GB: Five Must-Knows

1. **GB is not an EU-coupled market**: it does not take part in SDAC/SIDC; day-ahead prices form in domestic auctions, cross-border volumes trade through explicit capacity auctions, and prices can diverge from neighbours.
2. **Day-ahead means two auctions**: the EPEX GB hourly auction closes at 10:20 CET and the GB-30min auction at 16:30 CET; neither runs through EUPHEMIA coupling, and gate closure is one hour before the start of the half-hourly delivery period.
3. **The BM is pay-as-bid**: NESO accepts bids/offers for system needs and BOALF is the settlement basis; expensive offers get skipped, with a reported skip rate around 38% in 2026.
4. **The capacity market pays on de-rated capacity**: T-4 2029/30 cleared at £27.10/kW·yr for 40.1 GW; T-1 2026/27 at £5.00/kW·yr for 7,192 MW. Batteries can bid, but de-rating factors and delivery obligations matter.
5. **Support tools are layered**: standalone storage generally does not take standard CfD; co-located storage needs separate metering/BMU registration; LDES uses cap and floor (minded-to on 2026-06-26 covered 16 projects, 7,645 MW); TMO4+ grid reform emphasises "ready + needed".

**Three formulas**

```
Capacity market revenue = de-rated capacity (kW) × £/kW·yr
BM revenue = accepted MW × offer price × instructed hours
BSC imbalance settlement = deviation energy × imbalance price (plus credit/reconciliation)
```

**Entry path**: UK entity → Ofgem licence/exemption → BSC accession → BMU registration → CM prequalification/auction → (retail) supply licence → REMIT (remit.gb.net) → metering/MHHS. **Common errors**: treating GB as EU-coupled, using CET as UK time, assuming the BM clears at one price, using nameplate capacity for CM, expecting standard CfD for standalone storage.

### 7A.5 Italy: Five Must-Knows

1. **Seven bidding zones, not one price**: Nord, Centro-Nord, Centro-Sud, Sud, Calabria, Sicilia, Sardegna; PUN is a reference price, not a project's settlement price.
2. **MGP is the main day-ahead market**: run by GME, closing 12:00 D-1, SDAC-coupled; delivery periods switch to 15-minute MTU from 2025-10-01.
3. **MSD/MB belong to Terna**: GME runs the MGP/MI/MSD platforms, while Terna as dispatch operator procures frequency, reserve and congestion services; settlement differs from MGP.
4. **MACSE is the storage-specific long-term mechanism**: paid in €/MWh·yr on a 15-year contract, pay-as-bid, zonal auctions, new-build only; the first auction cleared 10 GWh at an average €12,959/MWh·yr; the second offers 16 GWh on 2026-11-24; the battery cap is €37,000/MWh·yr.
5. **Capacity market and FER X are two other tracks**: the capacity market pays for available capacity; FER X is a 20-year two-way CfD (DM 194/2026, 37.15 GW, 10 GW PV, €80/MWh reference), with NZIA-specific auctions imposing supply-chain conditions on PV above 1 MW.

**Three formulas**

```
MACSE annual revenue = winning price (€/MWh·yr) × storage energy capacity (MWh)
Capacity market revenue = available capacity (MW) × de-rating factor × capacity price (€/MW·yr)
FER X CfD = (strike price − market price) × contracted energy
```

**Entry path**: Italian/EU entity → GME membership + credit support → Terna BRP/BSP registration + dispatch contract → grid connection agreement → MACSE qualification/guarantees → REMIT (MERIT/ARERA/GME rules) → (generation) FER X/NZIA. **Common errors**: treating PUN as the settlement price, reading MACSE units as €/MW·yr, assuming the first-auction price repeats, expecting MACSE for existing or co-located assets, ignoring permitting and grid connection.

### 7A.6 Spain: Five Must-Knows

1. **Two bidding zones, not one**: Spain and Portugal form MIBEL but are separate bidding zones; prices separate when the interconnection binds, so an "Iberian average" is not a project settlement price.
2. **Fifteen minutes runs through trading and settlement**: day-ahead/intraday moved to 15-minute MTU on 2025-10-01; imbalance settlement has been 15-minute since 2024-12-01. Hourly models misprice both arbitrage and deviation.
3. **Day-ahead and intraday bounds differ**: day-ahead -€600/+€4,000 per MWh; intraday continuous ±€9,999 per MWh; negative prices are common in solar-heavy hours (about 555 hours in 2025, grade C).
4. **The capacity market only arrived in 2026**: Orden TED/966/2026, in force 2026-09-18; peninsular system, firm power, sealed-bid pay-as-bid; new-build main auctions up to 15 years; existing generation subject to a 550 g CO2/kWh gate; as of 2026-11-11 REE / the Secretary of State for Energy has published **no convocatoria**; the "late 2026 to 2027" press estimate has been withdrawn and must not be quoted as a date. The Order provides main, annual adjustment and transitional auctions; the EU approved the scheme in May 2026 with a €9bn/10-year ceiling (grade A).
5. **Storage policy has three tracks**: PNIEC targets 22.5 GW by 2030 (all technologies); RD 997/2025 requires grid-forming capability and 120%–130% voltage ride-through; RDL 7/2026 introduces flexible access and a 10% self-consumption reserve. The pipeline is large, but permitting and connection conversion is the bottleneck.

**Three formulas**

```
Energy arbitrage = discharge price × discharge energy × efficiency − charge price × charge energy
Capacity revenue = effective capacity (MW) × capacity price (€/MW·yr)
Ancillary opportunity cost ≈ reserved MW × contemporaneous energy spread × reserved hours
```

**Entry path**: Spanish/EU entity → grid connection → OMIE market registration → REE balancing responsibility (BRP) → ancillary prequalification → credit support → REMIT reporting. **Common errors**: treating MIBEL as one zone, treating OMIE as the regulator, using hourly models, treating the first capacity auction as priced, ignoring grid-forming/permitting.

### 7A.6b France: Five Must-Knows

1. **Nuclear sets the baseload, neighbours set the margin**: installed capacity was 164.5 GW at end-2025, with nuclear at 62.99 GW and 373.0 TWh (68.1%) out of 547.5 TWh; net exports reached 92.3 TWh. The 2025 day-ahead average was €61.1/MWh with 513 negative-price hours (mean -€6.5/MWh). Nuclear maintenance, river levels and temperature move the baseload and the peak/off-peak spread.
2. **ARENH has ended and VNU is neither a CfD nor a floor**: ARENH ended on 2025-12-31; VNU uses 78/110 €/MWh thresholds (50%/90% clawback), and CRE estimates 66.08 €/MWh for 2026 and 65.50 for 2027. It recovers excess revenue; it does not guarantee a minimum price.
3. **The capacity mechanism centralized under an RTE single buyer in 2026**: PL-1 is a delivery-period auction and PL-4 a multi-year contract (up to 15 years). The first 2026-27 auction cleared on 2026-07-06 for delivery from 2026-11-01 to 2027-03-31 (151 days) at €28,182.99/MW; 86,197.8 MW was certified and 82,446.8 MW cleared; batteries certified 608 MW and cleared 577 MW. **The €18,646.6/MW figure is a cost-allocation quotient, not a clearing price**.
4. **Fifteen minutes plus a wider MA**: day-ahead/intraday moved to 15-minute MTU on 2025-10-01; MA is split into fast (<13 min) and complementary (<30 min); OA/CR units above 10 MW must participate in MA from 2026-01-01; FCR is about 540 MW and jointly tendered weekly with DE/AT/BE/NL/CH; PICASSO was joined on 2025-04-04 and MARI on 2026-04-16.
5. **Storage and grid connection**: 1.6 GW in operation, a 14 GW/180-project battery queue and a CRE 2030 target of 5.5 GW; about 30 GW of connection rights had been granted by end-2025 (data centres 14, hydrogen 9.5, industry 6.5), which is a different caliber from the battery queue. Four-hour batteries go through PL-1; PL-4 has a long contract and heavy availability obligations. The IEF foreign-investment thresholds are 25% for non-EU and 10% for EU investors.

**Three formulas**

```
PL-1 delivery-period revenue ≈ certified capacity (MW) × delivery-period price (€/MW) × de-rating factor
PL-4 annual revenue ≈ certified capacity (MW) × €/MW·yr
MA opportunity cost ≈ reserved MW × contemporaneous day-ahead/intraday spread × reserved hours
```

**Entry path**: French/EU entity → RTE connection → EPEX/ECC clearing → RTE BRP registration → CRE capacity certification/PPI → ancillary prequalification → REMIT reporting → IEF review if triggered. **Common errors**: treating €18,646.6/MW as the clearing price, annualizing a delivery-period price, treating VNU as a CfD/floor, assuming ARENH still exists, bidding a four-hour battery into PL-4, using hourly models for 15-minute deviation, treating the 30 GW connection rights as the battery queue.

### 7A.7 Netherlands: Five Must-Knows

1. **The Netherlands is a separate bidding zone**: EPEX NL is not part of DE-LU; its price reflects domestic supply/demand plus interconnection with Germany, Belgium and the UK. Do not substitute German prices.
2. **There is no capacity market**: the Netherlands is energy-only plus balancing/ancillary services; the government has studied a capacity mechanism but has not implemented one. Storage relies on spreads, FCR/aFRR/mFRR and congestion contracts, with higher merchant risk than the UK, Italy or Spain.
3. **Fifteen minutes plus dynamic ancillary procurement**: 15-minute MTU since 2025-10-01 and 15-minute imbalance settlement; aFRR has used dynamic dimensioning since September 2025 (D-5 preliminary, D-1 06:00 firm, 09:00 gate closure), and 10% of volumes moved to 4-hour contracts from November 2025 (grade B).
4. **The connection queue is harder than the price**: about 15,000 businesses are waiting for grid access (grade C); ATR85 non-firm contracts trade curtailment for earlier connection (about 9 GW offered in 2025); the priority framework took effect on 2026-07-01; TenneT introduced time-of-use grid fees from 2025.
5. **SDE++ is not a battery subsidy**: the 2026 budget is €8bn with a window of 2026-10-27 to 2026-11-26, but the RVO page does not list batteries as a standalone category; net metering ends on 2027-01-01; large-scale batteries stood at 350 MW/620 MWh at end-2024, and TenneT expects about 4 GW by 2030 (grade B).

**Three formulas**

```
Energy arbitrage = (discharge price − charge price ÷ efficiency) × discharge energy
Ancillary capacity revenue = reserved MW × €/MW·h × available hours
Non-firm curtailment loss ≈ curtailed energy × (arbitrage spread − charging cost)
```

**Entry path**: Dutch/EU entity → TenneT/DSO connection → EPEX participant/clearing → BRP balancing responsibility → ancillary prequalification → credit support → REMIT reporting. **Common errors**: treating NL as DE-LU, assuming a capacity market, treating SDE++ as a battery subsidy, ignoring the connection queue/non-firm contracts, using hourly models.

### 7A.8 Poland: Five Must-Knows

1. **One bidding zone plus 15 minutes**: TGE runs the RDN day-ahead and RDB intraday markets, PSE dispatches and URE regulates; 15-minute MTU applies to day-ahead/intraday since 2025-10-01, and imbalance settlement is also 15 minutes. A negative price of −PLN 791.32/MWh occurred on 2026-04-06 (grade C), so negative prices are no longer an outlier.
2. **The capacity market is the main revenue pillar**: rynek mocy pays on de-rated capacity in PLN/kW·yr; for the 2030 delivery year the Polish price was PLN 465.02, synchronous profile PLN 78.00, Lithuania PLN 418.00 and Sweden PLN 444.67/kW·yr, with a 6,887.639 MW obligation and 992 MW of foreign awards; the auction ended in round 2 (grade A). Battery de-rating is **13.39%** (grade C, only for the Dec-2025 main auction / 2030 delivery year; the 2027 T-1 top-up still uses 95% and the 2029 main auction 61.3% — never mix auctions), so nameplate capacity cannot be used for revenue.
3. **OZE auctions are 15-year CfDs**: 2025 clearing prices were PLN 216.90–329.68/MWh for PV >1 MW and PLN 100–320/MWh for wind; the 2026 schedule is 76.1 TWh and PLN 24.9bn; non-price criteria apply from 2026, so equipment origin/carbon footprint may affect eligibility.
4. **Storage grants are CAPEX support**: the NFOŚiGW scheme provides PLN 4.15bn (PLN 3.735bn grants + PLN 0.415bn loans) for 172 projects, 3.9 GW/14.5 GWh, with grant rates of 45%/55%/65% and a minimum of 2 MW/4 MWh; Żarnowiec+Ełk add 425 MW/2,032 MWh. It is CAPEX support, not long-term revenue.
5. **Balancing has been Europeanised**: the 2024-06-14 WDB reform separated capacity and energy and moved to 15-minute settlement; POBs carry imbalance, DUBs provide balancing services; PSE joined PICASSO around July 2025 (grade B), MARI is pending, and it exited TERRE on 2025-01-01 (grade A).

**Three formulas**

```
Capacity revenue = de-rated capacity (MW) × clearing price (PLN/kW·yr) × 1000
Arbitrage gross margin = discharge energy × discharge price − charge energy × charge price (charge = discharge ÷ RTE)
OZE CfD cash flow = (reference price − market price) × awarded energy
```

**Entry path**: Polish/EU entity → URE koncesja → PSE/OSD connection → TGE membership/IRGiT clearing → PSE POB registration (or delegate) → ancillary prequalification → capacity-market qualification → REMIT. **Common errors**: treating the capacity price as €/kW·yr, using nameplate capacity for de-rated revenue, treating storage grants as operating revenue, using hourly models, assuming MARI is live.

### 7A.9 Belgium and the Nordics: Five Must-Knows

1. **Belgium's CRM is pay-as-bid**: Y-4/Y-2/Y-1 auctions, single-round sealed bids, pay-as-bid with an intermediate price cap; new build can get up to 15 years, existing units 1 year. The 2025 Y-4 auction cleared 4,690 MW, including 179 MW of new batteries (525 MW nameplate), at **€27.3k/MW·yr** (€27,300, grade A, Elia 2025-10-30; the "€273k" seen in some reports is a unit error); Y-2 cleared at €25,100/MW·yr and Y-1 at a weighted ~€14,100/MW·yr.
2. **Belgian nuclear extension changes the capacity gap**: Doel 4 and Tihange 3 are extended to 2035, and a May 2025 federal law repealed the 2003 phase-out law; do not keep using the old "2025 nuclear exit" assumption for CRM demand.
3. **The Nordics are 12 bidding zones, not one price**: NO1–NO5, SE1–SE4, DK1–DK2 and FI; Nord Pool forms a system price first and then zonal prices under interconnector constraints, and projects settle at the zonal price; EPADs hedge zonal spreads but are not physical PPAs.
4. **Nordic capacity tools are reserves, not a capacity market**: Sweden's effektreserv targets 800 MW and its 2025-10-07 auction failed because bids exceeded the SEK 120,000/MW cap; Finland has tehoreservi; Norway and Denmark have no national capacity market. Storage cannot treat reserves as a long-term capacity annuity.
5. **Fifteen minutes and negative prices are structural**: 15-minute MTU since 2025-10-01; 15-minute imbalance and mFRR EAM since 2025-03-04, with the share of hours where imbalance equals day-ahead falling from about 33% to about 3% and balancing costs rising from about €1 to €5–6/MWh (grades B/C); Finland had negative prices in about 8% of hours in 2024 and Sweden about 7%. Danish offshore wind uses 20-year CfDs, Sweden's 2025 law allows new nuclear, and entry rules differ across the four countries.

**Three formulas**

```
CRM revenue = de-rated capacity (MW) × clearing price (€/MW·yr)
Zonal arbitrage = (zonal discharge price − zonal charge price ÷ efficiency) × discharge energy
EPAD cash flow = (zonal price − system price) × contracted energy
```

**Entry path**: Belgian entity → Elia connection → Belpex/EPEX + BRP → CRM qualification/credit → REMIT; Nordic entity → national TSO/DSO connection → Nord Pool membership → national TSO BRP registration → ancillary prequalification → REMIT. **Common errors**: treating CRM as a uniform clearing price, using nameplate capacity for CRM, treating Nord Pool as one zone, treating effektreserv/tehoreservi as a capacity market, converting SEK/NOK/DKK at a single EUR rate.

### 7A.9b United States: Five Must-Knows

1. **There is no single national market**: ERCOT is an intrastate system whose wholesale pricing is governed mainly by PUCT and ERCOT rules; PJM spans 13 states plus DC and clears capacity by LDA; CAISO layers CPUC resource adequacy and CEC planning data on top. The three rulebooks are not interchangeable.
2. **ERCOT is energy-only with scarcity pricing**: real-time SCED runs every 5 minutes and settlement is 15 minutes; HCAP/LCAP are $5,000/$2,000 per MWh; ORDC adds scarcity payments when reserves are short. RTC+B went live on 2025-12-05, co-optimising real-time energy and ancillary services and modelling SOC.
3. **PJM runs on capacity, but a cap is not bankability**: the 2028/29 BRA cleared at $325/MW-day (the new cap), 152.1 GW cleared against a 6.8 GW gap and a 14.7% reserve margin, yet only about 525 MW of new effective capacity was added; a 4-hour battery has an ELCC of about 50% and capacity revenue of roughly $60k/MW-yr (order of magnitude).
4. **CAISO runs on day-ahead/real-time plus RA**: day-ahead + 15-minute FMM + 5-minute RTD; RA moves to full slice-of-day compliance from the 2026 compliance year; EDAM went live on 2026-05-01 with PacifiCorp as the first member and PGE joining 2026-10-01; storage exceeds 21 GW, and negative prices cluster in midday solar hours.
5. **Interconnection and supply chain are hard gates**: PJM's first 2026-08 cycle includes 715 projects/201.5 GW with a study cycle of about 40 months; the CAISO queue is about 197 GW; FEOC rules apply to projects starting construction after 2025-12-31, ITC is 30% plus 10% domestic content plus 10% energy community, Section 301 tariffs rise to 25% from 2026-01-01, and an August 2026 executive order targets grid equipment.

**Three formulas**

```
PJM capacity revenue ≈ ELCC (MW) × clearing price ($/MW-day) × 365
ERCOT arbitrage gross revenue ≈ discharged energy (MWh) × spread ($/MWh) × RTE × cycles
CAISO RA revenue ≈ NQC (MW) × capacity price ($/kW-yr) × 1000
```

**Entry path**: US entity/project company → ISO/RTO interconnection queue → market registration (ERCOT/PJM/CAISO) → capacity/RA qualification (PJM ELCC, CAISO NQC) → ancillary prequalification → state/local permits and fire code → tax (ITC/tax equity) and CFIUS/FEOC compliance. **Common errors**: treating ERCOT as 5-minute settlement, modelling 2022–2023 ancillary revenue, treating the PJM cap as bankable, ignoring ELCC decay and capacity performance penalties, counting only the 30% ITC.

### 7A.9c Japan: Five Must-Knows

1. **Thirty-minute granularity, no negative prices**: JEPX day-ahead has 48 half-hour products, a 10:00 gate and a blind single-price auction; the floor is ¥0.01/kWh, so surplus solar presses the price to the floor but never negative; the cap is quoted as either ¥100 or ¥200/kWh, and the rulebook wording still needs verification.
2. **Imbalance costs are high**: 30-minute settlement; from 2026-10-01 the C value rises from ¥200 to ¥300/kWh and the D value from ¥45 to ¥50/kWh (grade C); deviation costs can exceed arbitrage margin, so storage needs intraday rolling forecasts.
3. **The capacity market is four years ahead, single-price, one-year contracts**: units of 1,000 kW or more can participate and batteries are certified by de-rating factor; round 5 (FY2028) cleared ¥11,134/kW and round 6 (FY2029) ¥13,303/kW; historical average prices have ranged from ¥3,109 to ¥14,137/kW, so a single result cannot be extrapolated.
4. **LTDA is 20-year revenue with clawback and a duration threshold**: pay-as-bid with about 90% of other market revenue clawed back ex post; from round 3 batteries under 6 hours are no longer eligible; round 3 awarded 1,251 MW/19 battery projects at a 36% award rate (grade C). The EPRX cap fell from ¥19.51 to ¥10.00/ΔkW·30min in September 2026, so a ΔkW-only model no longer works.
5. **Grid queueing and foreign-investment review are hard gates**: storage connection-study applications reached 24,880 in FY2025; from 2026-08-01 each applicant is capped — Tokyo 11, Kansai 12, Kyushu 8; general transmission/distribution, transmission and generation of 50 MW or more are core sectors under FEFTA, requiring prior notification with a 30-day to 5-month review.

**Three formulas**

```
Capacity market revenue ≈ de-rated capacity (kW) × clearing price (¥/kW-yr)
LTDA net revenue ≈ LTDA capacity revenue + other market revenue × (1 − 90%)
EPRX revenue ≈ Σ ΔkW × unit price (¥/ΔkW·30min) + dispatched energy × kWh price
```

**Entry path**: Japanese entity/project company → connection study and grid connection → generation business filing → generation output adjustment contract (balancing responsibility) → JEPX/EPRX membership → capacity market/LTDA registration → FEFTA prior notification → equipment certification/fire code/telecoms. **Common errors**: applying European negative-price models, hard-coding the spot cap, underestimating C-value deviation costs, bidding 4-hour projects into LTDA, extrapolating one capacity-market price, ignoring FEFTA and the per-applicant connection-study cap.

### 7A.10 The Same Question, Eleven Markets

| Question | Australian NEM | German DE-LU | UK GB | Italy | Spain | Netherlands |
|---|---|---|---|---|---|---|
| "What is the spot price now?" | Ask which region first; read the 5-minute dispatch price | Ask day-ahead or intraday first; read the DE-LU MTU | Ask day-ahead or BM first; read EPEX GB or BOALF | Ask which zone first; read the MGP zonal price, PUN is reference only | Ask Spain or Portugal; read the OMIE 15-minute price | Read EPEX NL 15-minute price; do not substitute German prices |
| "What is the price cap?" | 2026-27 MPC/CPT/APC, with financial year | Day-ahead/intraday floors differ; cap harmonised/validated by ACER | No administered wholesale band; CM cap £75/kW·yr | Per current GME/ARERA rules | Day-ahead -€600/+€4,000; intraday ±€9,999 | Per EPEX/EU rules; intraday floor around -€9,999 |
| "How do I lock in a price?" | ASX futures, OTC, PPAs, CfD/LTESA | EPEX day-ahead/intraday, OTC, PPAs, retail packages | EPEX GB, OTC, PPAs, CfD | GME products, OTC, PPAs, FER X CfD | OMIE day-ahead/intraday, PPAs, capacity contracts | EPEX day-ahead/intraday, PPAs, tolling, congestion contracts |
| "How do batteries make money?" | Energy arbitrage + FCAS + CIS/state schemes | Energy arbitrage + FCR/aFRR/mFRR + capacity mechanism (from 2031) | Energy arbitrage + BM + CM + ancillary; LDES via cap and floor | Energy arbitrage + MSD/MB + capacity market + MACSE | Energy arbitrage + ancillary + capacity market (first auction pending) + grants | Energy arbitrage + FCR/aFRR/mFRR + congestion contracts (no capacity market) |
| "Renewables support?" | LGC/SRES, CIS | EEG auctions + sliding premium; zero value at negative prices | CfD (generally not for standalone storage) | FER X two-way CfD, NZIA auctions | PNIEC, RD 997/2025, RDL 7/2026, auctions | SDE++ (not standalone batteries), net metering ends 2027 |
| "How is congestion handled?" | Regional prices + constraints + MLF/IRLF | Single zone + Redispatch 2.0 | BM + network constraints; TNUoS signal | Seven-zone spreads + MSD/redispatch | Two-zone spreads + redispatch/technical constraints | Connection queue + non-firm contracts + congestion management |
| "How do I enter?" | AEMO registration + metering + prudential | Local entity + REMIT + balancing group + EPEX/ECC | Entity + Ofgem licence/exemption + BSC/BMU + CM | Entity + GME membership + Terna BRP/BSP + MACSE | Entity + grid connection + OMIE + REE BRP + credit + REMIT | Entity + grid connection + EPEX + BRP + credit + REMIT |
| "Biggest risk?" | MLF, FCAS opportunity cost, prudential | Balancing responsibility, EEG negative prices, grid fees, REMIT | BM skipping, CM delivery/de-rating, grid queue | Zonal spreads, MACSE delivery, permitting/connection | First capacity auction, grid-forming/permitting, 15-minute deviation | Connection queue, no capacity market, non-firm access, SDE++ misreading |

**New markets: the same questions**

| Question | Poland | Belgium | Nordics |
|---|---|---|---|
| "What is the spot price now?" | Read the TGE RDN 15-minute price; do not substitute German prices | Read the Belpex 15-minute price; it is not DE-LU | Ask which zone first; read the zonal price, the system price is reference only |
| "What is the price cap?" | EU SDAC/SIDC; day-ahead floor around -€500/MWh, intraday ±€9,999/MWh | Same EU SDAC/SIDC | Same EU SDAC/SIDC |
| "How do I lock in a price?" | TGE day-ahead/intraday, OTC, PPAs, OZE CfD, capacity contract | Belpex/EPEX, OTC, PPAs, CRM | Nord Pool, Nasdaq futures/EPAD, PPAs, CfD |
| "How do batteries make money?" | Capacity market + arbitrage + ancillary + NFOŚiGW CAPEX grant | CRM + arbitrage + FCR/aFRR/mFRR | Arbitrage + ancillary + reserves (not a capacity market) |
| "Renewables support?" | OZE auctions, 15-year CfD; 76.1 TWh in 2026 | Offshore wind CfD; no standalone battery subsidy | National auctions/CfD; Danish offshore 20-year CfD |
| "How is congestion handled?" | Connection queue + cross-border capacity | Connection/permitting + interconnection | Zonal spreads + interconnectors + EPAD |
| "How do I enter?" | URE licence + PSE/OSD connection + TGE/IRGiT + POB + capacity registration | Elia connection + Belpex/EPEX + BRP + CRM qualification | National TSO/DSO connection + Nord Pool + national BRP |
| "Biggest risk?" | De-rating/availability penalties, policy change, grants mistaken for revenue | CRM penalties/price cap, unit conventions | Zonal spreads, hydro/negative prices, four-country rule differences |

**United States and Japan: the same questions**

| Question | ERCOT | PJM | CAISO | Japan |
|---|---|---|---|---|
| "What is the spot price now?" | Read the nodal price and ORDC; real-time dominates | Read the nodal price; capacity is a separate BRA | Read the zonal price with FMM/RTD; negative prices midday | Read the JEPX 30-minute product price; no negative prices |
| "What is the price cap?" | HCAP $5,000 / LCAP $2,000 per MWh | Capacity $325/$175 per MW-day; energy per tariff | Day-ahead/real-time bounds per CAISO tariff | Spot cap ¥100/¥200 per kWh (to verify) |
| "How do I lock in a price?" | Bilateral, ASX/OTC, PPAs, tolling | Bilateral, futures, PPAs, capacity contracts | Bilateral, PPAs, RA, EDAM | JEPX forward/time-ahead, PPAs, capacity/LTDA |
| "How do batteries make money?" | Arbitrage + ancillary (Reg/RRS/ECRS) | Capacity + arbitrage + ancillary | Arbitrage + RA + FRP | Spot + EPRX + capacity + LTDA |
| "How is capacity priced?" | No capacity market; ORDC scarcity pricing | ELCC × $/MW-day × 365 | NQC/RA slice-of-day | De-rated capacity × ¥/kW-yr |
| "Renewables support?" | Federal ITC + state schemes | Federal ITC + state schemes | Federal ITC + state schemes | FIT/FIP, non-fossil certificates, SII grants |
| "How do I enter?" | ERCOT registration + interconnection + state permits | PJM registration + capacity qualification + state permits | CAISO registration + RA certification + CPUC/CEC | Filing + balancing responsibility + connection study + FEFTA |
| "Biggest risk?" | Skewed spreads, interconnection queue, FEOC | Cap is not bankable, ELCC decay, 40-month interconnection | Negative prices, RA penalties, cluster interconnection | ≥6h threshold, 90% clawback, C-value deviation, queue |

**France: the same questions**

| Question | France |
|---|---|
| "What is the spot price now?" | Read the EPEX FR 15-minute price; it is not a "European nuclear price" — neighbour coupling transmits through |
| "What is the price cap?" | EU SDAC/SIDC bounds; day-ahead floor around -€600/MWh, intraday floor around -€9,999/MWh |
| "How do I lock in a price?" | EPEX day-ahead/intraday, OTC, PPAs, CRE CfD tenders, capacity PL-1/PL-4 |
| "How do batteries make money?" | Capacity PL-1 + MA/ancillary + arbitrage; only long-duration/new-build looks at PL-4 |
| "How is capacity priced?" | Certified capacity × de-rating factor × €/MW over the delivery period, or €/MW·yr for PL-4; €18,646.6/MW is a cost-sharing quotient, not a clearing price |
| "Renewables support?" | CRE CfD tenders (~58 rounds); GO via EEX, AIB EECS |
| "How do I enter?" | RTE connection + EPEX/ECC + BRP + CRE capacity certification + IEF/REMIT |
| "Biggest risk?" | Delivery-period price mistaken for annual, PPI deadline, PL-4 long-contract obligations, grid queue |

### 7A.11 Answering Discipline for Overseas Markets

1. **Confirm market, region and time first**: for Australia ask state/region; for Germany ask day-ahead/intraday and CET/CEST; for the UK ask day-ahead/BM and GB time; for Italy ask bidding zone and MGP/MSD; for Spain ask Spain/Portugal zone and OMIE period; for France ask EPEX FR and the delivery period; for the Netherlands confirm EPEX NL (not DE-LU); for Poland confirm TGE RDN (not German prices); for Belgium confirm Belpex (not DE-LU/French prices); for the Nordics confirm which of the 12 bidding zones; for the US confirm ERCOT, PJM or CAISO; for Japan confirm the supply area and JEPX product. Never answer with a single "European price", "US price" or "Australian price".
2. **Currency and units**: AUD/MWh, EUR/MWh, GBP/MWh, PLN/MWh, SEK/NOK/DKK/MWh, USD/MWh and USD/kW-month, USD/MW-day, USD/kW-yr, JPY/kWh and JPY/kW-yr; French capacity also uses €/MW over a delivery period and €/MW·yr; do not mix with CNY or CNY/kWh. If converting, state the FX date.
3. **Time zones**: NEM is fixed AEST; Germany, France, Italy, Spain, the Netherlands, Poland, Belgium, Sweden, Norway and Denmark switch CET/CEST; Finland uses EET/EEST; the UK switches GMT/BST, and EPEX GB gate times are quoted in CET; ERCOT uses CT, PJM ET and CAISO PT, each with daylight saving; Japan uses JST with no daylight saving. Gates, settlement and reports must use one consistent clock.
4. **Rule hierarchy**: Australia NER + AEMO procedures; Germany EnWG/StromNEV/EEG + BNetzA/EPEX rules; UK BSC/CUSC + NESO/Ofgem rules; Italy TIDE + ARERA/GME/Terna rules; Spain BOE decrees + OMIE/REE/CNMC rules; France CRE decisions + RTE rules + EU coupling rules; Netherlands Energiewet + ACM/TenneT rules; Poland energy law + URE/PSE/TGE rules; Belgium electricity law + CREG/Elia rules; Nordics Nord Pool rules + national TSO rules; US FERC tariffs + ISO/RTO rules + state PUC rules (ERCOT wholesale sales are not FERC rate-jurisdictional); Japan the Electricity Business Act + METI ordinances + OCCTO/JEPX/EPRX rules; EU coupling rules only to the extent relevant to the trade.
5. **Source grading**: official rules/notices A; exchange/regulator data A/B; media/reports B/C; own calculations D. Volatile figures such as capacity-mechanism volumes, French PL-1/PL-4 and PPI, CIS/MACSE/Polish capacity/Belgian CRM/PJM BRA/Japanese capacity-market and LTDA results, the Spanish first capacity auction, the Dutch connection queue and Nordic reserve auctions need a grade and a date.
6. **Do not replace local advice**: registration, tax, REMIT/MiFID, grid connection and contracts, US ITC/FEOC and CFIUS, Japanese FEFTA and the French IEF should be reviewed by local counsel/tax/compliance; this skill provides a trading framework only.
7. **Draft vs in force**: Australia's reliability-standard recommendation, Germany's AgNes (final determination 2027-01-01, rules from 2029), the EEG 2027 amendment, the UK's REMA/TMO4+/LDES final parameters, Italy's second MACSE auction and capacity-market rules, Spain's first capacity auction and RD 997/2025 implementation, France's PL-4 auction schedule and PPI acceptance/grid-reform detail, the Netherlands' Energiewet implementation/aFRR 4-hour rollout/priority framework, Poland's capacity de-rating and 2026 OZE non-price criteria, the Belgian CRM price unit, the Nordic mFRR EAM/PICASSO timetable, US FEOC/tariff/grid-equipment executive-order details, and Japan's capacity-market de-rating and LTDA round-4 rules may be proposals or not fully effective; state the status.

### 7A.12 Where to Read in the Repository

- Australia in depth: `knowledge/澳大利亚NEM电力市场-2026-11.md` (five regions, 5MS, FCAS, MLF/IRLF, CIS, IESS, entry path, ten pitfalls).
- Germany in depth: `knowledge/德国电力市场-2026-11.md` (DE-LU, EPEX, 15-minute MTU, balancing, redispatch, EEG, capacity mechanism, entry path, ten pitfalls).
- UK in depth: `knowledge/英国电力市场-2026-11.md` (GB single market, EPEX GB, BM/BOALF, T-4/T-1 capacity market, CfD/LDES, TMO4+, entry path, ten pitfalls).
- Italy in depth: `knowledge/意大利电力市场-2026-11.md` (seven zones, MGP/MI/MSD/MB, MACSE, capacity market, FER X, entry path, ten pitfalls).
- Spain in depth: `knowledge/西班牙电力市场-2026-11.md` (MIBEL two zones, OMIE 15 minutes, TED/966/2026 capacity market, RD 997/2025, RDL 7/2026, storage connection, entry path, ten pitfalls).
- France in depth: `knowledge/法国电力市场-2026-11.md` (nuclear, ARENH exit, VNU, RTE single-buyer capacity mechanism, PL-1/PL-4, MA/FCR/aFRR/mFRR, RTE/Enedis connection, IEF, entry path, ten pitfalls).
- Netherlands in depth: `knowledge/荷兰电力市场-2026-11.md` (EPEX NL, no capacity market, 15-minute settlement, SDE++, connection queue/non-firm, storage revenue, entry path, ten pitfalls).
- Poland in depth: `knowledge/波兰电力市场-2026-11.md` (single bidding zone, rynek mocy, OZE auctions, NFOŚiGW storage grants, POB/DUB, PICASSO/MARI, entry path, ten pitfalls).
- Belgium and the Nordics in depth: `knowledge/比利时与北欧电力市场-2026-11.md` (Belgian CRM Y-4/Y-2/Y-1, nuclear extension, 12 Nordic zones, 15-minute imbalance, mFRR EAM, effektreserv, negative prices, entry path, ten pitfalls).
- United States in depth: `knowledge/美国电力市场-2026-11.md` (ERCOT energy-only and ORDC, PJM BRA/ELCC, CAISO RA/EDAM, interconnection and ITC/FEOC, Chinese entry paths, ten pitfalls).
- Japan in depth: `knowledge/日本电力市场-2026-11.md` (JEPX 30-minute spot, imbalance C/D values, capacity market, EPRX, LTDA, connection study, FEFTA, entry path, ten pitfalls).
- International retail-price comparison method: `knowledge/国际电价比较-方法与模板-2026-11.md` (retail tariff calibers, not to be mixed with wholesale market rules here).
- China interprovincial/provincial: `knowledge/省间与跨区交易-2026-11.md`, `knowledge/省级市场状态表-2026-11.md`.

### 7A.13 Cross-Cutting Topics

- Grid connection and compliance: `knowledge/海外并网与合规-2026-11.md` (EU RfG/EN 50549; German VDE-AR-N; UK G99/G100; Italian CEI 0-21/0-16; Spanish NTS; French RTE/Enedis; Dutch Netcode; Polish grid code; Belgium/Nordics; IEC 62933, UL 9540/9540A, NFPA 855, NIS2, Battery Regulation/passport, NZIA, FDI screening including Belgium/Netherlands/Nordics).
- Capacity mechanisms: `knowledge/容量机制横向对照-2026-11.md` (capacity annuity / auction / two-way CfD / strategic reserve / energy-only archetypes; UK/Italy/Spain/France/Poland/Belgium/Germany/Nordics/Netherlands/Australia/US/Japan comparison; unit conversion, five capacity calibres, de-rating, storage capacity revenue).
- Ancillary services: `knowledge/辅助服务与平衡市场对照-2026-11.md` (FCR/aFRR/mFRR, FCAS, BM, MSD/MB, EPRX; PICASSO/MARI/TERRE accession and storage eligibility).
- Storage revenue and data: `knowledge/储能收益建模与数据源-2026-11.md` (ENTSO-E, NESO, Elexon BMRS, GME, OMIE, REE, PSE, Nord Pool, Nordic TSOs and other entry points; an eleven-market country index and gaps; granularity/time zones, RTE, degradation, capture rate, de-rating, revenue stacking, backtest).
- PPA / certificates / tolling: `knowledge/跨国PPA与绿证-2026-11.md` (GO/REGO/REC/LGC/NFC/GEC, AIB EECS cross-border recognition, eleven-market support schemes and storage eligibility, CfD/CIS stacking, merchant tail, tolling terms, 24/7 hourly matching).
- Same-caliber snapshot and decision calendar: `knowledge/海外市场同口径快照与投决日历-2026-11.md` (eleven markets side by side on installed capacity, storage, average price, negative-price hours, capture rate, interconnection queue and de-rating, with 2025 P0 data backfilled and remaining gaps marked "to be verified"; five-topic × eleven-market coverage matrix; 2026Q4–2027 event calendar, China-entry six gates and 22 grade-C figures with verification entries).
- **How to use**: confirm local rules in the single-market module first, then compare across markets with the cross-cutting note; the cross-cutting note does not replace local rules, contract texts or local legal advice. Before an investment decision, check whether a number is comparable in the snapshot, then model the project in the single-market module.

---

## 8. Full Market Entry of Renewables (Document No. 136 is the watershed)

> Chapter data cutoff: 2026-11-01 (mechanism prices and 2026-2027 auction results update province by province; verify province and year before citing).

### 8.1 Policy Essentials (NDRC Pricing〔2025〕No. 136, 2025-02-09)
- Renewables' on-grid energy **in principle enters the power market in full**, with on-grid prices formed through market trading;
- **Grid-connection cutoff at 2025-06-01 for full capacity** separates existing/incremental projects;
- Outside the market, a **"sustainable development price settlement mechanism"** is established (differential settlement at the mechanism price, refunding excess or making up shortfalls) — essentially an out-of-market CfD, settled on energy, with hourly curve matching not yet required;
- Existing-project mechanism prices are generally ≤ the local coal benchmark price; incremental prices are formed by **bidding** (with upper and lower limits); the execution period is **10 or 12 years depending on the province — provincial plans govern, there is no national uniform figure**; mechanism energy scale is linked to non-hydro consumption responsibility weights — a dual track of "floor protection for old projects, bidding for new projects";
- As of 2026-09 most provinces had issued implementation plans and **12 provinces had launched 2027 auctions**; Anhui and Guizhou are revising their provincial supporting documents; auction results vary widely and cannot be summarized by one national average price.

### 8.2 Provincial Mechanism Price Quick Reference (2025)

| Province | Existing-project mechanism price | Incremental mechanism | Notes |
|---|---|---|---|
| Shandong | CNY 0.3949/kWh (= benchmark price) | Annual bidding (submission adequacy floor 125%) | First auction: wind 0.319, solar 0.225 CNY/kWh |
| Guangdong | CNY 0.453/kWh | Bidding range 0.2~0.453 CNY/kWh | Nearly 80 million kW entered the market |
| Inner Mongolia West | CNY 0.2829/kWh | Not yet in the mechanism | Most conservative |
| Gansu | CNY 0.3078/kWh | Limits 0.2447/0.1954 CNY/kWh | First batch cleared at the floor; first generation-side capacity compensation |
| Beijing | CNY 0.3598/kWh | Guaranteed 12-year execution | 100% of energy included |

**2026-2027 Incremental Auction Results (as of 2026-10; verify province by province)**

| Province | Auction result | Volume/notes |
|---|---|---|
| Zhejiang | First auction CNY 381.6/MWh; second auction CNY 0.242-0.393/kWh | First: 4.2896 billion kWh, 31,024 projects; second: 13.325 billion kWh, 110% declared adequacy |
| Hunan | CNY 0.23-0.35/kWh | 2.286 billion kWh |
| Fujian | CNY 0.16-0.39/kWh | 8.36 billion kWh |
| Guangdong | CNY 0.20-0.40/kWh | 7.934 billion kWh |
| Beijing | Cap CNY 0.3598/kWh | 0.85 billion kWh |
| Tianjin | Cap CNY 0.32/kWh | 4.0 billion kWh |
| Jiangxi | Range CNY 0.24-0.379/kWh (C) | 4.08 billion kWh |
| Liaoning | Range CNY 0.18-0.30/kWh | 5.308 billion kWh (wind 3.956 / solar 1.352), 2027 auction clears 11-08; single centralised project ≤60%, distributed ≤80% |
| Guangxi | Range CNY 0.15-0.36/kWh | Single project ≤80%, wind and solar auctioned separately; 2025-26 results wind 0.355 / solar 0.31 |
| Gansu | 2027 H1 solar CNY 0.2447, wind CNY 0.2440/kWh | First batch cleared near the floor |

- **Interpretive discipline**: Zhejiang's first auction at CNY 381.6/MWh (0.3816/kWh) was near the cap, a result of rush installation plus scarce mechanism volume — it is not a national average. Bidding bands, declared adequacy and execution years differ enormously; always ask for province and year before quoting a mechanism price.
- **Trend**: 2026 incremental auctions are generally below existing-project mechanism prices; in some provinces (Fujian, Guangdong) the floor is already close to CNY 0.16-0.20/kWh. Lower "floor protection" forces investment in power forecasting, curve decomposition and joint bidding with storage.

### 8.3 Capability Requirements for Market Entry (trading capability is revenue)
- The revenue model shifts from "guaranteed volume and price" (保量保价) to "market price + mechanism differential": midday troughs/negative prices become routine → **power forecast accuracy, bidding strategy, and curve decomposition become hard requirements of trading capability**;
- Guaranteed utilization hours (full guaranteed offtake) and reasonable utilization hours (subsidy determination, MOF〔2020〕No. 4/5 (财建〔2020〕4/5号)) are two different concepts: the former governs the market-entry boundary, the latter governs subsidy phase-down;
- Consumption responsibility weights (NDRC Energy〔2019〕No. 807 (发改能源〔2019〕807号)) + GECs (from NDRC Energy〔2017〕No. 132 (发改能源〔2017〕132号); full-coverage issuance from 2024) are the pillars of the quota side; **green power trading was 328.5 billion kWh in 2025 (+38.3% YoY) and 249.2 billion kWh in January-September 2026 (+6.1%)**. Slower green-power growth shows that after existing projects entered the market the "green premium" is no longer an unlimited increment — trading capability matters more than obtaining quota.

### 8.4 Nuclear Power Entering the Market (a new 2026 variable)
- **Policy signal**: nuclear is entering the market faster in 2026, with three provincial models coexisting (level C; follow the provincial official documents): **Liaoning** established a nuclear sustainable-development price-settlement mechanism in 2026-03 — monthly mechanism energy covers 80% of on-grid energy in the 21-hour daily window, priced at the state-approved tariff (Hongyanhe units 1-4 CNY 0.3823, units 5-6 CNY 0.3749, average 0.3798/kWh), with the difference settled by the grid and shared among commercial/industrial users; **Guangxi** has applied a CfD mechanism to nuclear since 2026-01; **Guangdong** scrapped nuclear variable-cost compensation in 2026 and moved nuclear directly into market competition.
- **Market impact**: as baseload, nuclear typically bids below coal and above the marginal cost of renewables; once in the market it depresses spot averages and squeezes coal baseload space. Its stable output also moderates extreme midday/nighttime volatility, hedging the "scarcity-hour" revenue of storage and VPPs.
- **Answering discipline**: distinguish "planned/protected energy" from "marketized energy"; do not classify nuclear as "new energy", and do not treat the Liaoning/Guangxi mechanism prices as national rules.

---

## 9. Virtual Power Plants and Demand Response (Market View)

> Chapter data cutoff: 2026-11-01 (products, thresholds, subsidies). Resource aggregation, control technology, business models and international cases belong to the sister skill *Virtual Power Plant Expert*; this chapter keeps only "market identity, eligible products, settlement and retail pass-through".

### 9.1 Market Identity and Rule Essentials (NDRC Energy〔2025〕No. 357)
- Positioning: a **resource-aggregation type of new market entity**, participating as a whole in medium/long-term, spot and ancillary service markets; engaging in power purchase and sale requires an electricity retailer license.
- Targets: regulation capacity above 20 million kW by 2027 and above 50 million kW by 2030; at publication about 470 projects nationwide and 16.85 million kW.
- Rule essentials: a single resource may not be aggregated by two or more VPPs at the same time; the same regulation action may not earn spot/ancillary/DR revenue repeatedly (Zhejiang and Fujian state this explicitly); demand response goes through the new-type load management system, spot/ancillary services through the dispatch automation system.
- **2026 updates**: the 2026-10-19 spot-rules draft provides for full participation of new entities and joint bidding of new energy plus co-located storage, moving VPPs from "invitation subsidies" toward "market bidding"; a national VPP management measure is **not yet issued**.
- For the national standard, the full policy chain and scale calibers, see *Virtual Power Plant Expert* §9; **470 projects / 16.85 million kW is measured maximum regulation capability, while the 2026-06 media figure of "120 million kW / 800+ projects" is connected capacity — the two must not be mixed**.

### 9.2 Eligible Products
- Demand response (invited / market-based), medium/long-term, spot, ancillary services, capacity compensation; provinces open these in different orders, so first confirm whether a local spot and ancillary market exists.
- The development-stage judgement (invitation → market → autonomous dispatch) belongs to the aggregation side; see *Virtual Power Plant Expert* Chapter 4. This chapter only asks "can it enter the market, and how is it settled".

### 9.3 Provincial Entry Thresholds and Products (Trading View)

| City | Entry threshold | Products and highlights |
|---|---|---|
| Shenzhen | Access testing + capability verification + qualification review | Real-time precise response at a fixed **CNY 5/kWh** (stackable with provincial/municipal/Two Rules subsidies); platform investment subsidized at 10% of response revenue (≤CNY 2 million/yr, **measure expired 2025-12-31**) |
| Shanxi | Testing of regulation capability/time/accuracy/aggregation capacity | Load type + source-grid-load-storage integration; quantity-price bidding into spot; frequency regulation/reserve |
| Shanghai | Aggregation ≥1 MW and ≥2 h (Lingang 1000 kW/30 min) | "1+5" system; V2G reward CNY 50/kW·yr; **2025-08: China's first million-kW-class invocation at 1.1627 million kW** (29 operators) |
| Gansu | Aggregator threshold 10 MW→5 MW | — |

- Complete provincial VPP rules, thresholds and the 2026 additions are in *Virtual Power Plant Expert* §9.2 and `knowledge/省级市场状态表-2026-11.md`; this table keeps only the provinces most used on the trading side.
- DR subsidy benchmarks: peak-shaving invitations CNY 0~5/kWh, valley-filling 0~1 CNY/kWh; real-time/quasi-real-time ~CNY 2.5/kWh in many regions; interruptible load bidding cap CNY 15/kW; Jiangsu short-time max 4.8 CNY/kWh; Guangzhou peak-shaving ≤3.5 CNY/kWh.
- Vehicle-grid interaction V2G: pilots in 9 cities (Shanghai/Changzhou/Hefei/Huaibei/Guangzhou/Shenzhen/Haikou/Chongqing/Kunming); Guangzhou discharge subsidy ≤CNY 5/kWh (owners receive ~3.5).

### 9.4 Revenue Structure and Retail Pass-Through
- Five revenue streams: DR subsidies, spot peak-valley arbitrage, ancillary services, capacity compensation, green power/GEC services; peak-regulation compensation reference ~CNY 0.3/kWh.
- **Retail-side constraint (new in 2026)**: VPP DR/spot-arbitrage revenue ultimately passes through a retailer or the customer bill. With widespread retail losses and wholesale-retail inversion in 2026, the share left to VPPs is compressed: 400+ retailers exited in the first seven months; 298 of 500 Guangdong retailers lost money in H1; Guangxi's maximum inversion was CNY 0.373/kWh; the system operation fee rose about 93% YoY. Do not look only at the wholesale spread — check whether the retail side can pass it through.
- Revenue splits, the e2m commission model, profitability models and project cases are in *Virtual Power Plant Expert* Chapter 8; this section only answers "can the revenue reach the customer bill".

### 9.5 International Rules Comparison (Market Design Only)
- **FERC Order 2222** (2020-09): allows DER aggregation into wholesale markets, with minimum aggregation size not exceeding 100 kW; implementation is per ISO: CAISO and ISO-NE implement energy/ancillary services from **2026-11-01**, NYISO 2026-12, PJM in the 2028/29 capacity auction, MISO mid-2029, ERCOT not subject to the order (ADER pilot). "Compliance plan approved" does not equal "actually able to participate".
- Company cases (Next Kraftwerke, Tesla Autobidder, OhmConnect) and national capacity targets are in *Virtual Power Plant Expert* Chapter 10 and are not repeated here.

---

## 10. Carbon Market and Corporate Carbon Management

> Chapter data cutoff: 2026-11-01 (carbon prices, allowance plan, CCER, CBAM timing); MRV and accounting methods are not time-sensitive.
> This chapter keeps market rules and a carbon-price overview only; compliance calendars, allowance gaps, CCER development economics and carbon finance belong to *Carbon Asset Management Expert* (`skills/carbon-asset-expert/SKILL_EN.md`), which owns the numbers and operating detail.

### 10.1 National Carbon Market (CEA) Framework and Evolution
- **Launch**: went live 2021-07-16 (trading at the Shanghai Environment and Energy Exchange, registration at China Carbon Emissions Registration (中碳登)); first batch ~2000 key emitting units in the power sector;
- **Institutional design**: allowance allocation mainly via the **benchmark method + free allocation**, intensity-based control with no absolute cap; CCER offset limit **5%**;
- **Expansion** (2025-03 "Work Plan for Covering the Iron and Steel, Cement, and Aluminum Smelting Sectors in the National Carbon Market"): 2024 is the first control year, first compliance by end-2025; **as of 2026 it covers 3,680 entities** (power 2,087, steel 232, cement 962, aluminum 97), about **8.3 billion tonnes** of CO₂, **over 65%** of national emissions (controlling CO₂/CF₄/C₂F₆); the next batch is expected to cover petrochemicals, chemicals, paper and civil aviation, with **basic coverage of major high-emission sectors by 2027**.
- **Regulation**: the Interim Regulations on the Administration of Carbon Emission Trading (《碳排放权交易管理暂行条例》, State Council Decree No. 775, effective 2024-05-01; **revised 2026-08-08**) — failure to surrender in full: a fine of **5-10x** the market average price of the month preceding the surrender deadline; fraudulent reporting: confiscation + 5-10x fine; "dual penalties" for technical service institutions. The revision moves toward "free allocation as the main method, with paid allocation introduced gradually".
- **2025/2026 allowance plan**: mainly free allocation; the coal benchmark is **−0.35%** versus the previous period and gas is unchanged; the peak-shaving correction coefficient is capped at **50%**; the pre-allocation ratio is at most **50%**; **allowances for 2019-2024 cannot be carried over, while 2025/2026 allowances can** — carry-over rules are the direct cause of short-term carbon-price moves.
- Compliance rhythm: power allowance pre-allocation = 70% of the previous year's verified emissions; **the 2025 compliance rate was 99.99%** (previously 99.98% for 2023, 5.244 billion tonnes); expanded sectors conduct monthly documentation from 2025-07.

### 10.2 Carbon Price Trends (price sensing)

| Time point | CEA price (CNY/tonne) |
|---|---|
| 2021-07-16 opening | 48.00 |
| 2024-04-24 | 100.59 (first break above 100) |
| 2024-11 peak | 106.02 (2024 average 91.8) |
| 2025-10 low | ~50 (post-compliance demand decline + new carry-over rules) |
| 2025-12 year-end | 74.63 |
| End-2026-08 | **97.90** (+31.18% vs end-2025) |
| 2026-10-08 | 94.94 |
| Jan-Aug 2026 | average 83.86 (range 72.5-99.69) |

The 8 pilots averaged CNY 44.1/tonne in 2024 (~54% below the national market): Beijing highest (2024 ~62.7; briefly above 100 online in 2025; the only pilot with a CNY 20~150 stabilization band), Shanghai stable at 66.7, Hubei first in volume with mid-range prices, Shenzhen volatile, Tianjin/Chongqing weak. **Pattern: carbon prices show strong cyclicality — spiking in compliance periods, falling between them**; tighter caps + sector expansion are the main long-term upward logic.

### 10.3 CCER (China Certified Emission Reduction, 国家核证自愿减排量)
- **Restarted 2024-01-22** (trading at the Beijing Green Exchange, registration in the registration system); 2025-03: the first 9 projects (offshore wind + afforestation carbon sinks) completed registration;
- Methodologies: first batch (2023-10) 4 items = afforestation carbon sink, grid-connected solar thermal (CSP), grid-connected offshore wind, mangrove creation; second batch (2025-01) 2 items = low-concentration coal mine gas, highway tunnel lighting; 19 items cumulatively published/for comment in 2025;
- Price: 2025 average transaction price CNY 70.76/tonne, **above the CEA average for the same period (62.36)** — scarcity of supply; **by mid-October 2026, 44 projects had completed registration/issuance, with an average price of about CNY 86.51/tonne**, still above CEA. The old rule of thumb "allowance price ≈ CCER price ÷ 0.7" has inverted several times since the restart; observe dynamically and never use it as a formula;
- Development practice (book material: 2016-era data + current mechanisms): seven-step process (PDD → validation → registration → monitoring → verification → emission-reduction filing → trading); crediting period 7 years ×3 or fixed 10 years; full cycle ~5-8 months to 1.5-3 years; development cost CNY 200,000~300,000 for typical projects (forestry carbon sinks 500,000~1,000,000); cooperation models = pure consulting / revenue sharing (typically 20~40%) / buyer buyout;
- The core of additivity argumentation = IRR analysis (power-sector benchmark 8%, sensitivity ±10%); **wind and solar projects will most likely lose additivity due to falling costs** (VCS already rejects renewable generation) — CCER opportunities are concentrating in methane recovery, forestry carbon sinks, and energy-saving projects.

### 10.4 Carbon Accounting and MRV (where experts most often stumble)
- Three-tier system: **regional inventories** (IPCC 2006 + provincial guidelines) | **organizational inventories** (GHG Protocol / ISO 14064-1 / China's 24-industry guidelines + GB/T 32150) | **product carbon footprint** (PAS 2050 / ISO 14067 / EU PEF);
- Formulas: emissions = activity data × emission factor × GWP; coal combustion = consumption × lower heating value × carbon content per unit heat × 44/12 × oxidation rate; mass balance = (carbon input − carbon output) × 44/12;
- Scopes 1-2-3: Scope 1 direct emissions; **Scope 2 purchased electricity/heat split into location-based/market-based methods** (green power can count as zero; assessments use the market-based method); Scope 3 optional;
- **Electricity factors (a frequent error point)**: for consumption emissions use the **average factor** (national 0.6101 → draft 0.5810 tCO2/MWh; regional values stuck at 2012's 0.527~0.881); for emission reductions only the **baseline factor** (OM/BM weighted; wind/solar OM 0.75 + BM 0.25) — misusing OM for enterprise consumption emissions is the most common mistake;
- Verification essentials: records kept ≥10 years; sampling = square root of the count of similar sites, sites <5% of the total may be sampled, monthly data cross-checked ≥30%; frequent errors = arithmetic mean instead of weighted average, fixed carbon instead of elemental carbon, default values despite measurements, double counting of self-produced self-used secondary energy;
- The allowance-scope "supplementary data sheet" and the reporting-scope accounting guidelines are **two datasets that will never match** (the former excludes process emissions/carbon sequestration deductions/mobile sources) and cannot substitute for each other.

### 10.5 Green Power, GECs and the Electricity-Carbon Linkage
- NDRC Environment & Resources〔2024〕No. 113 (发改环资〔2024〕113号): GECs incorporated into the national standards for product carbon footprint accounting; the 2025-03 "Opinions on Promoting High-Quality Development of the GEC Market" pushes their application in carbon accounting and international mutual recognition;
- **Boundary discipline**: GECs/green power claim Scope 2 reductions; CCER is used for compliance offset (≤5%) or voluntary cancellation — **the same energy/emission reduction may never be claimed twice**;
- Export risk: the EU Battery Regulation's carbon footprint rules do not recognize GEC deductions (all-average / consumption-location combined marginal method) → exporters need **dual-track accounting** (Scope 2 deductions only where the target market recognizes GECs);
- **CBAM (a key 2026 correction)**: transitional period from 2023-10, **definitive implementation from 2026-01-01**, but **certificate purchases are deferred to 2027-02**, with the first annual declaration and surrender due by **2027-09-30**; certificate prices are linked to the EU ETS auction average, with Q1/Q2 2026 reference prices of about **EUR 75.36/75.28 per tonne**; default values carry a **+10%** markup in 2026 and **+30%** in 2028; imports below 50 tonnes are exempt; from 2028 the scope extends to about 180 downstream products; third-party verification is introduced from September-October 2026; the UK CBAM starts 2027-01-01. It covers steel/cement/aluminum/fertilizer/hydrogen/electricity; one tonne of blast-furnace steel exported pays ~EUR 44.79 (≈CNY 375, an estimate) vs ~CNY 200 domestic profit per tonne of steel — forcing the combination of "green power trading + VPP response + carbon footprint accounting + storage arbitrage". **Do not say "implementation on 2026-01-01" means "certificates must be bought in 2026".**
- **2026 GEC market (new)**: by 2026-09, **326 million certificates had been issued, 197 million were tradable (60.45%), and 58.43 million were traded**; vintage spreads are huge — about **CNY 0.56** for 2024 vintage, **CNY 1.60** for 2025 and **CNY 6.16** for 2026 (an ~11x spread); the September GEC index was 190.5, −6.0% MoM and −12.3% YoY; cumulative issuance in January-September was 2.65 billion. Always ask for vintage and issuance date before quoting a GEC price.
- International mechanisms: GHG Protocol Scope 2 revision expected 2027 Q2 (contested point = hourly matching); SBTi Net-Zero Standard; Paris Agreement Article 6 ITMOs will link global carbon prices (CDM CERs registered after 2013 are the first candidate assets).

### 10.6 Corporate Carbon Management Methodology (carbon management consulting framework)
- The closed loop: **baseline (inventory) → targets (SBTi/intensity metrics) → plan (seven directions: management-driven reduction / energy efficiency / more green power / electrification / zero-carbon readiness / raw material and fuel substitution / non-energy reduction) → offsets (environmental credits must be generated within the last 3 years and must be cancelled; proximity principle: direct purchase > same grid > same country) → communication (annual reports, CDP ratings A-F in 9 grades) → system (ISO 50001 PDCA)**;
- Carbon-neutrality timing discipline: own operations 2030, full value chain 2050, no dimension later than 2060; expansion-stage industries (wind/solar/storage, NEVs) should use carbon intensity metrics;
- Internal carbon pricing in three tiers: retrofit incentives → carbon cost accounting → internal carbon trading (200+ companies globally, average ~USD 20/tonne);
- Seven-piece carbon asset management kit: low-carbon steering group, annual carbon inventory, abatement potential analysis, energy-saving management (GB/T 23331), carbon asset investment, trading management, internal controls (VaR + stress testing + tiered authorization);
- Trading strategy: judge surplus/deficit from emission forecasts, buy low and sell high in batches; **pre-compliance panic buying pushes carbon prices up 20%~30%** (historically lifted from 50-60 to 75-80 CNY) — compliance-period liquidity risk is the No. 1 risk of carbon asset management.

---

## 11. Trading Strategy and Risk Management

> Chapter data cutoff: 2026-11-01 (retail losses, system operation fee, risk-control and credit rules are 2026 data and drafts); the strategy framework is not time-sensitive.

### 11.1 Generation-Side Strategies
- Three-part revenue = medium/long-term contracts + spot energy + ancillary services; short term, build bidding strategies on **next-day clearing price forecasts**; long term, set contract/bidding energy ratios on marginal price forecasts;
- Bid formats: quantity-price bids (multi-segment quantity-price pairs, can become the price-setting marginal unit) vs quantity-only bids (price taker); bid curves of 3~10 segments;
- Single-unit optimum: profit maximized when MC=π; with no-load cost counted, the price must exceed a threshold for genuine profit (example: price ≥13.26 run at full output, ≤11.18 shut down); unit commitment is a cross-period trade-off — running at a loss in low-price hours may beat shutting down and restarting (saving startup costs);
- Under perfect competition, bidding at marginal cost is optimal; under real oligopoly the common practices: bid above/below marginal cost, submit slightly below the expected market marginal price, anticipate rivals, run market simulations;
- Hydro: run-of-river acts as price taker or bids quantity only; cascade joint dispatch targets maximum cascade benefit; pumped storage round-trip efficiency ~75% (a hard arbitrage threshold); as the peak-valley spread narrows, arbitrage turns negative.

### 11.2 Electricity Retailer and Large Consumer Strategies
- Retailers earn the wholesale-retail spread and **concentrate the risk of spot price volatility — risk-control capability is competitiveness**; retail packages must be differentiated and transmit wholesale price signals;
- Load forecasting is the first barrier: for every trading window, at 15-minute granularity, precise to the node or customer group; aggregated forecast error can be squeezed to 1.5%~2% — **forecast accuracy has direct economic value** (example: retail price 38.50, average purchase price 39.23 → loss 1154; with accurate forecasting, profit 2896);
- Large-consumer procurement portfolio: high share of locked medium/long-term prices (80%~95%) + floating spot exposure + storage/VPP adjustment; reverting to grid agency power purchase is executed at **1.5x** (NDRC General Office Pricing〔2021〕No. 809 (发改办价格〔2021〕809号)) — staying out of the market carries a clear penalty;
- Retail pricing must cover: wholesale cost + deviation assessment + T&D price + fund surcharges + operating cost + profit.
- **The 2026 retail-side reality (media/industry data, item by item)**: **400+ retailers exited in the first seven months of 2026**; **298 of 500 Guangdong retailers lost money in H1**; Guangxi's maximum wholesale-retail inversion was **CNY 0.373/kWh**; Guizhou lost over **CNY 40 million** in January-February; Anhui lost over **CNY 119 million** in January; Shanxi's per-kWh loss was about **CNY 0.02**; the system operation fee in Q1-Q3 2026 was about **CNY 0.068/kWh (+93% YoY)**; about **11 provinces** have cancelled or marketized fixed time-of-use prices, so retail packages lose their "fixed peak-valley spread" protection.
- **New regulation**: the Retailer Management Measure (draft for comment, 2026-09-04), the Electricity Market Risk-Control Measure (draft for comment, 2026-09-30, 7 chapters and 32 articles) and the forthcoming Basic Rules for the Retail Market; the direction is higher entry requirements, stronger performance guarantees/risk reserves, wholesale-retail inversion monitoring and an exit mechanism.
- **Strategic conclusion**: retailers must move from "capturing the wholesale-retail spread" to "forecasting + risk control + package design + customer service"; VPP/storage/green-power revenue must pass through the retail side — never assume wholesale-side revenue automatically reaches the customer bill.

### 11.3 Market Power Identification and Regulatory Indicators (understand regulation to understand the boundary of strategy)

| Category | Indicator | Threshold/criterion |
|---|---|---|
| Structure | CR4/CR8 | 40 as the dividing line; CR8≥70 very high oligopoly |
| Structure | HHI | ≥1800 high oligopoly; 1000~1800 low oligopoly; <1000 competitive |
| Structure | KSI key supply index | A supplier is pivotal if its capacity exceeds the difference between remaining capacity and demand |
| Structure | RSI residual supply index | <100% means the market depends on it |
| Local | TTS three-pivotal-supplier test | Used by PJM for congested areas |
| Conduct | Lerner index (π−MC)/π | 0 under perfect competition |
| Conduct | Marginal unit formation rate | Far above its generation share → suspected market power |
| Conduct | Declared adequacy | California 125% as the threshold of ample competition, >150% no price cap needed |
| Three manipulation behaviors | Economic withholding (high bids) / capacity withholding (creating scarcity) / collusion | Main causes of the California crisis; ex-ante price caps → in-period bid replacement → ex-post penalties |

### 11.4 Five Market Risk Types and Mitigation
(1) grid operational security ("dual high": high shares of renewables + power electronics; monitor supply-demand ratio/corridor loading/reserves with early warning); (2) market power (cap shares, monitor withholding, dilute via FTRs); (3) long-term supply (capacity mechanisms, see 5.3); (4) price volatility (scientific price limits, futures/options hedging, virtual bidding); (5) entity credit (performance guarantees, credit line = unsecured credit + secured credit; trading suspended if usage exceeds 100% without replenishment).

### 11.5 Entity Capability Checklist (spot market entry "health check")
- Rules layer: registration/credit management, procedures for each product, settlement formulas, disclosure deadlines;
- Technical layer: dedicated workstations on the technical support system, submission/disclosure time nodes, 15-minute generation and consumption forecasting;
- Strategy layer: price forecasting models, bid decisions, portfolio optimization across medium/long-term + spot + ancillary services;
- Risk layer: price exposure management, deviation assessment simulation, cash flow stress testing, settlement reconciliation (daily allocation checks).

### 11.6 2026 Risk Control and Credit Supervision (new)
- **Electricity Market Risk-Control Measure (draft for comment, 2026-09-30, 7 chapters and 32 articles)**: covers abnormal prices, supply-demand imbalance, market power, credit default, settlement risk and technical-system risk; requires trading institutions to build a monitoring-early warning-disposal loop and market entities to hold risk reserves/performance guarantees.
- **National Unified Electricity Market Credit Evaluation Guidelines (draft for comment, 2026-10-19)**: unifies credit evaluation indicators, grades and disclosure; credit results are linked to access, trading permissions and margins.
- **Measures for the Administration of Medium/Long-Term Energy-Supply Contracts (Trial) (NDRC Order No. 50, effective 2026-12-01)**: institutionalizes the signing, performance and supervision of energy-supply contracts; they are no longer "temporary coordination".
- **Provisions on the Administration of Grid-Connected Operation (draft for comment, NEA, 2026-09-30)**: updates grid-connection operation, grid-related performance, assessment and exit rules, clarifying the connection responsibilities of VPPs/storage/distributed generation.
- Answering note: apart from Order No. 50, these are mostly drafts for comment; mark them "draft/proposed" and do not present them as laws already in force.

---

## 12. Key Formula Quick Reference

| Formula | Expression | Use |
|---|---|---|
| LMP | πₙ = marginal energy + marginal congestion (μ×PTDF) + marginal loss | Nodal pricing |
| Congestion surplus | (π_receiving − π_sending) × corridor-crossing energy | Source of FTR funding |
| FTR payoff | F × (π_W − π_S), can be negative | Congestion hedging (obligation type) |
| CfD settlement | Σ[(contract price − reference price) × contracted energy] | Medium/long-term differential settlement |
| Three-part generation revenue | Contract differential + (day-ahead cleared − medium/long-term decomposition) × day-ahead price + (actual − day-ahead) × real-time price | Centralized spot settlement |
| Market power | (π−MC)/π = sᵢ/ε | Assessing price-raising room |
| Equal-marginal dispatch | dCᵢ/dPᵢ = λ (λ = shadow price) | Economic dispatch |
| Single-unit decision | Profit maximized at MC=π; full output/shutdown hinges on the no-load-inclusive threshold | Bidding and commitment |
| Reserve opportunity cost | Reserve price = energy price spread (e.g. 28−17=11) | Joint clearing pricing |
| ATC | ATC = TTC − TRM − ETC (incl. CBM) | Inter-provincial available transfer capability |
| Carbon emissions | Activity data × emission factor × GWP; coal = volume × heating value × carbon content × 44/12 × oxidation rate | Carbon accounting |
| Emission reduction (project) | Baseline emissions − project emissions (additivity must be proven; IRR benchmark 8%) | CCER development |
| Grid factor selection | Consumption emissions = average factor; project reductions = OM/BM baseline factors | Electricity-carbon coupling |
| CBL baseline | Similar-day average (latest 5 same-type days, excluding ±25% deviations) × correction factor | VPP/DR settlement |
| Pumped storage arbitrage | Peak-valley spread > spread threshold (75% efficiency + charge/discharge losses) | Storage calculations |
| Capacity price (coal) | CNY 330/kW·yr × recovery ratio (~30% in 2024-25 → ≥50% from 2026); 165 is the mainstream value of the 50% floor | Coal fixed cost |
| Capacity price (independent storage) | Local coal capacity price × (full-power continuous discharge duration ÷ longest net-load peak duration), capped at 1x | NDRC Pricing〔2026〕No. 114; list-based |

---

## 13. Glossary (Selected Chinese-English Terms)

| Term (Chinese) | English | One-line explanation |
|---|---|---|
| 现货市场 | Spot Market | Day-ahead/intraday/real-time centralized energy competition market |
| 节点边际电价 | LMP (Locational Marginal Price) | Marginal cost of serving 1 MW more load at a node = energy + congestion + loss |
| 安全约束机组组合 | SCUC (Security Constrained Unit Commitment) | Unit commitment optimization accounting for grid and unit constraints (mixed-integer programming) |
| 安全约束经济调度 | SCED (Security Constrained Economic Dispatch) | Constrained output optimization (rolling) |
| 差价合约 | CfD (Contract for Differences) | Financial contract settled on the difference between contract price and reference price |
| 金融输电权 | FTR (Financial Transmission Right) | Financial right hedging nodal price differences (congestion) |
| 物理输电权 | PTR (Physical Transmission Right) | Physical right to transmit a specified power across a specified interface |
| 失负荷价值 | VOLL (Value of Lost Load) | Value of outage losses; theoretical benchmark for the price cap |
| 可用输电能力 | ATC (Available Transfer Capability) | Remaining transfer capacity beyond existing transactions |
| 母线负荷预测 | Bus Load Forecasting | Node-level load forecast; the basis for LMP calculation |
| 市场力 | Market Power | Ability to price above competitive levels and sustain it |
| 持留 | Withholding | Economic withholding (raising prices) / physical withholding (under-declaring capacity) |
| 日前/实时偏差结算 | Two-Settlement | Dual settlement: financial day-ahead + physical real-time |
| 平衡机制 | Balancing Mechanism | Real-time balancing of decentralized markets (UK BM) |
| 需求响应 | DR (Demand Response) | Users changing consumption patterns to reduce/shift load |
| 虚拟电厂 | VPP (Virtual Power Plant) | Aggregates distributed resources to participate in markets as a special power plant |
| 基线负荷 | CBL (Customer Baseline Load) | The "counterfactual no-response" load for demand response settlement |
| 车网互动 | V2G (Vehicle-to-Grid) | EVs discharge in reverse to provide regulation |
| 绿证 | GEC (Green Electricity Certificate) | 1 certificate = 1 MWh of renewable electricity environmental attributes |
| 全国碳市场 | China ETS | CEA allowance trading (trading in Shanghai, registration in Wuhan) |
| 国家核证自愿减排量 | CCER | Project-based emission reductions, offset up to 5% of allowance surrender |
| 范围一/二/三 | Scope 1/2/3 | Direct emissions / purchased electricity & heat / other indirect |
| 碳关税 | CBAM | EU Carbon Border Adjustment Mechanism (applies from 2026-01-01; certificate purchases from 2027-02, first surrender 2027-09-30) |
| 科学碳目标 | SBTi | International science-based target initiative (1.5°C/2°C alignment) |
| 监视-估计-状态估计 | State Estimation | The data foundation inferring system state from measurements |

---

## 14. Expert Q&A Reasoning Handbook

### 14.1 Question Typing and Answer Paths
1. **Concept/principle type** ("What is LMP / why build a spot market"): definition → composition/causes → differences in the Chinese context → one-sentence practical implication. Cite Chapters 1, 3.
2. **Rule/operation type** ("How is Shandong solar settled / how to submit in Shanxi"): first confirm the province and entity identity → check that province's rule essentials (quick tables in Chapters 7, 8) → give the process and time nodes → remind that the provincial power exchange's latest rules prevail.
3. **Calculation type** ("How much can this storage project earn / VPP revenue"): first clarify the boundaries (province, scale, resource type, existing contracts) → give the revenue-item framework (Sections 9.4/11) → give key parameters as ranges with source and time point → state assumption sensitivities explicitly (e.g. the effect of a 20% narrower peak-valley spread).
4. **Policy-interpretation type** ("Impact of Document No. 136"): document number + publication date → core mechanism → existing/incremental cutoff → differentiated impacts on different entities → implementation details subject to provincial documents (attach the known provincial comparison table).
5. **Forecast/judgment type** ("What about next year's carbon price"): drivers (supply/demand/policy/season) → historical ranges and patterns (compliance cyclicality) → scenario ranges → risks and disclaimer.
6. **Cross-domain synthesis type** ("How should an export steel mill respond to CBAM"): decompose into carbon accounting (Section 10.4) + green power procurement (Section 10.5) + power cost optimization (Chapters 9, 11) + timetable, and give an action list.

### 14.2 Common Misconceptions (proactively correct the user)
1. Treating "Document No. 813" as the spot market basic rule (it is No. 1217; 813 is a supporting notice);
2. Believing medium/long-term contracts are physically executed (under the centralized model they are CfDs — settled, not executed);
3. Treating peak regulation as an internationally standard ancillary product (a Chinese specialty, being absorbed into the spot market);
4. Using the OM baseline factor for enterprise consumption emissions (the average factor should be used);
5. Believing GECs can directly offset the EU Battery Regulation carbon footprint (not recognized);
6. Treating spot negative prices as "market failure" (it is the price discovery function at work; pair with flexibility);
7. Equating the capacity price with a capacity market (compensation is administratively priced; a market is competitively formed);
8. Ignoring settlement confirmation deadlines (overdue is deemed non-objection and auto-confirmed);
9. Treating CCER supply as unlimited (under additivity constraints wind/solar hardly qualify; scarce supply pushes up prices);
10. Comparing provinces on a single spot price (one must also compare price-limit structures, renewable share, and mechanism prices);
11. Treating the 2026-10-19 spot-rules draft as current rules (proposed effective 2027-01-01; in 2026 Document No. 1217 and provincial rules still govern);
12. Saying CBAM "applies from 2026-01-01" means "certificates must be bought in 2026" (certificate purchases are deferred to 2027-02, first surrender 2027-09-30);
13. Labeling PJM's 2027/28 figure of USD 329.17/MW-day as 2028/29 (the latter is USD 325/MW-day, cleared 2026-07-14).

### 14.3 Data Timeliness Discipline
- Time points of this skill's book knowledge: spot market material 2019-2023; carbon practice data 2016 (mechanisms still valid, numbers need updating); carbon management 2021; web research **2026-11-01**; time-sensitive chapters (2–11) carry a data-cutoff note under or at the top of the chapter heading; unmarked principle chapters are not time-sensitive;
- **Caliber dictionary**: definitions and common misuses for traded energy (market-traded / medium-long-term / green power), the number of spot markets, capacity prices, the system operation fee, No. 136 existing/incremental projects, the four VPP capacity metrics, carbon allowances, CBAM certificates, GECs and PJM prices are in `knowledge/索引与口径-2026-11.md`; confirm the caliber before citing;
- Policy figures (formal-operation lists, mechanism prices, subsidy standards, capacity price ratios, carbon prices) **change every month** — always answer with "as-of time point + verification entry points"; the spot rules, retailer measure, risk-control measure and credit-evaluation guidelines of September-October 2026 are all drafts and must be labeled as such;
- High-frequency verification entry points: NDRC website (pricing/operations), NEA (market regulation/qualifications), provincial DRCs/energy bureaus, Beijing Power Exchange and provincial exchange platforms, the southern regional power trading platform, the national carbon trading site (cets.com.cn), China Carbon Emissions Registration (中碳登), ICAP annual reports.

---

## 15. Knowledge Sources and Maintenance

### 15.1 Book Sources
1. 101 Questions on the Electricity Spot Market (《电力现货市场101问》), compiled by the National Power Dispatching and Control Center, China Electric Power Press, 2021 — the backbone of spot concepts, mechanisms, and domestic/foreign models
2. Electricity Spot Market in Practice (《电力现货市场实务》), compiled by the National Power Dispatching and Control Center, China Electric Power Press, 2023 — architecture, clearing, settlement, technical support systems, provincial practice
3. Principles of Power System Economics (《电力系统经济学原理》, Kirschen & Strbac), trans. Zhu Zhizhong — market economics theory, LMP/congestion/investment theory, classic worked examples
4. China Carbon Emission Trading in Practice (《中国碳排放权交易实务》, Meng Zaoming, Ge Xing'an et al.) — carbon market mechanisms, pilot comparisons, MRV, CCER development
5. Carbon Management: From Zero to Carbon Neutrality (《碳管理：从零通往碳中和》, Wang Jun) — carbon accounting systems, carbon asset development, corporate carbon management
6. Principles of Economics, micro/macro volumes (《经济学原理》微观/宏观分册, Mankiw) — the basic economics framework (supply-demand, elasticity, market structure, externalities)

### 15.2 Policy and Market Research (2025-2026-11)
- Policies: NDRC Order No. 20, No. 1217, No. 1501, No. 136, No. 357, No. 394, No. 1656; **2026 additions**: State Council General Office〔2026〕No. 4, NDRC Pricing〔2026〕No. 114, NDRC Energy〔2026〕No. 688, NDRC Order No. 50, the Basic Rules for the Electricity Spot Market (draft for comment, 2026-10-19), the Retailer Management Measure (draft), the Electricity Market Risk-Control Measure (draft), the National Unified Electricity Market Credit Evaluation Guidelines (draft), the Provisions on the Administration of Grid-Connected Operation (draft); the Basic Rules for the Electricity Ancillary Services Market (2025-04), the Interim Regulations on the Administration of Carbon Emission Trading (Decree No. 775, revised 2026-08-08), the CBAM regulation, etc.;
- Data: NEA "2025 China Electricity Market Development Report", January-September 2026 market-trading data, southern regional market formal-operation data, annual reports of provincial power exchanges, the national carbon market 2025/2026 allowance plan, Fudan Carbon Price Index, ICAP;
- All items are annotated with source URLs and dates; the full research records are in the research notes under knowledge/. **Caliber conflicts found during the 2026-11 update (2025 medium/long-term 4.81 vs 6.3522 trillion; green power 0.27 vs 0.3285 trillion; the year of PJM 329.17) have been corrected in the text; where old notes disagree, this SKILL prevails.**
- **New maintenance files (2026-11; check these three first)**:
  - `knowledge/索引与口径-2026-11.md` — policy-document index (issue date / effective date / status), caliber dictionary, A/B/C/D source grading, 2026-2027 watchlist;
  - `knowledge/省级市场状态表-2026-11.md` — one-row-per-province status table for 33 provincial markets plus the southern regional market (spot status / No. 136 auction / capacity price / VPP / ancillary services / retail risk);
  - `knowledge/黄金问答集-2026-11.md` — 28 high-frequency questions with answer points and common errors, doubling as a regression checklist for each revision;
  - `knowledge/调研-电力市场2026-10增量.md` and `knowledge/调研-碳市场与CBAM-2026-10增量.md` — the underlying research records and "to be verified" lists for this round;
  - `knowledge/INDEX_EN-2026-11.md` — English index and digest: file map, key figures with grades, a condensed provincial table and the open-items list; use it when answering from an English-only context.
- **Division of labour with the sister skills**: this skill owns market rules, settlement, pricing mechanisms, retail and a carbon-market overview; resource aggregation, control technology, VPP business models and asset-side estimates belong to *Virtual Power Plant Expert*; compliance calendars, allowance gaps, CCER development economics, carbon finance and CBAM operations belong to *Carbon Asset Management Expert*. Overlapping passages carry only a pointer, and numbers defer to the skill that owns the topic, so the files cannot drift apart.

### 15.3 Open-Source Toolbox (modeling and data)

| Purpose | Tool | Address |
|---|---|---|
| System clearing/planning simulation | PyPSA (~2.1k★) | github.com/pypsa/pypsa |
| Distribution power flow/VPP grid-connection checks | pandapower (~1.3k★) | github.com/e2nIEE/pandapower |
| Bidding agents/reinforcement learning | Grid2Op (~470★) | github.com/Grid2op/grid2op |
| North American ISO data scraping | gridstatus (~440★) | github.com/gridstatus/gridstatus |
| Market multi-agent simulation | PowerTAC / elecsim | github.com/PowerTAC/powertac-server |
| Carbon-aware dispatch | Carbon Aware SDK | github.com/Green-Software-Foundation/carbon-aware-sdk |
| Electricity carbon intensity data | Electricity Maps / WattTime | electricitymaps.com / watttime.org |
| China carbon data | National carbon trading platform / China Carbon Emissions Registration (中碳登) / CEADs | cets.com.cn / cnemission.com / ceads.net |

### 15.4 Known Limitations
- Some scanned files carry OCR noise; occasional typos may remain (corrected by context where possible, formulas described in words);
- The carbon practice book's data are from around 2016; for post-2021 national carbon market rules, Sections 10.1~10.5 (web research) prevail;
- Items marked "(to be verified)" should prompt the user to verify when cited; the spot rules, retailer measure, risk-control measure, credit-evaluation guidelines and grid-connection provisions of September-October 2026 are **drafts for comment** and the final clauses may change;
- Provincial rules update fast; this skill does not replace real-time policy search. Re-verify 2026 provincial spot formal operation, No. 136 auctions, capacity prices and VPP rules before answering;
- Overseas markets (Chapter 7A) cover the Australian NEM, German DE-LU, UK GB, Italy, Spain, France, the Netherlands, Poland, Belgium and the Nordics, the United States (ERCOT/PJM/CAISO) and Japan, excluding the WA WEM, the Northern Territory, French overseas territories and other US ISOs/RTOs such as MISO, SPP, NYISO and ISO-NE; rules, taxes, grid connection and contracts require local official documents and professional advice;
- 2025 trading volumes exist in several calibers ("market-traded 6.64 trillion / medium-long-term 6.3522 trillion / 4.81 trillion in some materials"); the preferred caliber is stated in the text — check old materials against it.

### 15.5 Zero-dependency worked-example tools

- `tools/fuel.py` (thermal-coal contract pricing, dual-track blended cost, fuel cost per MWh, dark/spark/clean spreads, coal-to-gas switching carbon price, inventory days) is locked to assertions in `tools/selftest.py` and corresponds to the knowledge base note [fuel and power trading](../../knowledge/燃料与电力交易-2026-11.md). All examples are synthetic (grade D), not investment advice.
- `tools/market.py` owns congestion surplus, FTR payouts and LMP decomposition, mapped to [inter-provincial and cross-region trading](../../knowledge/省间与跨区交易-2026-11.md) §5.5. Two-node price separation and dynamic ATC belong to `spot-bidding-quant/tools/network.py` and are not re-implemented here; both use the same "(price difference) x constrained flow" calibre and are cross-checked.

- **Price-driver routing**: quantity ([weather and power trading](../../knowledge/气象与电力交易-2026-11.md)), price ([fuel and power trading](../../knowledge/燃料与电力交易-2026-11.md)), deliverability ([inter-provincial trading](../../knowledge/省间与跨区交易-2026-11.md) §5.5-5.6). For "why is this interval expensive", check quantity -> price -> constraint -> superposition; see the [golden Q&A](../../knowledge/黄金问答集-2026-11.md) section F (Q29-Q38) for regression questions.
