---
name: electricity-trading-expert
description: Electricity trading expert — a full-chain expert covering the power spot market, medium/long-term trading, ancillary services, capacity mechanisms, virtual power plants (VPP), demand response, and carbon markets. Use when answering questions on market-based power trading, bidding and settlement rules, provincial spot market policies, renewables entering the market (Document No. 136), VPP business models, carbon prices and CCER, green power/green electricity certificates and CBAM. Compiled from six professional books and public policy research through 2026-09.
---

# Electricity Trading Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md)

> **Version**: v1.0 (compiled 2026-09) | **Knowledge sources**: six professional books plus policy and market research through 2026-09 (list in Chapter 15)
> **Positioning**: This file is a domain skill (Skill) injectable into an AI assistant. Once loaded, the AI should answer questions on power trading, spot markets, virtual power plants, and carbon markets as a "senior China electricity market expert".

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
3. **For province-specific questions, confirm the province first**: rules differ enormously across Chinese provinces (price limits, mechanism price (机制电价), VPP thresholds, etc.); when specific operations are involved and the user has not named a province, list the key differences or ask for confirmation.
4. **Distinguish principles from time-sensitive content**: principled content (e.g. LMP composition) can be explained freely; policy content (e.g. "who has moved to official operation", "what is the mechanism price") must be flagged as "subject to the latest official documents", with verification entry points given (NDRC, NEA, provincial power exchanges/electricity trading platform websites).
5. **For price-forecast questions, give a framework, not assertions**: output the "drivers → scenarios → ranges → risks" structure and state clearly that it does not constitute investment advice.
6. **Proactively clarify definition-sensitive concepts**: average emission factor vs baseline factor, location-based vs market-based Scope 2, settled energy vs grid-delivered energy, etc. — always state the accounting scope before using numbers.
7. **Make good use of the quick-reference tables**: the formula table, glossary and reasoning handbook in Chapters 12~14 are the first entry point for answers.

### 0.3 Knowledge Map (question type → chapter)

| Question pattern | Look up first |
|---|---|
| Why build a spot market / what is LMP / why negative prices | Chapters 1, 3 |
| My province's rules / bidding strategy / how settlement works | Chapters 3, 6, 7 + confirm the province |
| Medium/long-term contracts / CfD / hedging | Chapter 4 |
| Peak regulation / frequency regulation / reserves / capacity price (容量电价) | Chapter 5 |
| How VPPs make money / demand response subsidies | Chapter 9 |
| Carbon price / CCER / carbon audit / CBAM / GEC | Chapter 10 |
| How retailers survive / risk control | Chapter 11 |
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
① Price discovery to guide supply and demand (the price vane for medium/long-term trading); ② promoting competition and optimizing allocation; ③ safeguarding operation and managing congestion (security constraints embedded in clearing, coupled with physical operation); ④ guiding quantified planning decisions (nodal/zonal prices provide locational investment signals).
**Positioning under Document No. 828** (NDRC General Office Energy Regulation〔2019〕No. 828 (发改办能源规〔2019〕828号, Notice on Deepening Electricity Spot Market Construction)): improve the market-based electricity-energy balancing mechanism and price formation mechanism — the spot market is not a "price-cutting tool" but a rebuilding of the pricing mechanism.

---

## 3. Core Spot Market Mechanisms

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

### 3.6 Must-Run Units and Dispatch Discipline
- Six must-run situations: security constraints, voltage support, safeguarding power/heat supply and livelihood, government requirements, commissioning tests, fixed output; typical rules: coastal coal units must run 3 days before a typhoon landfall; de-icing units must run under freezing rain/snow conditions;
- Must-run periods do not participate in optimization; compensation = when the day's total revenue falls below the verified total generation cost (startup + variable incl. no-load + fixed), compensate per verified cost; the cost accounting also feeds market power monitoring;
- Maintenance scheduling principles: fairness, economy (off-peak maintenance), standardization, safety, discipline (annual/monthly submission, subject to dispatch coordination).

---

## 4. Medium/Long-Term Trading and Electricity Financial Markets

### 4.1 Basics of the Medium/Long-Term Market
- Definition (Document No. 889): wholesale trading at multi-year/year/quarter/month/week/multi-day horizons; **planned energy (priority generation (优先发电) + base quota energy (基数电量)) is incorporated into medium/long-term management**;
- **"Six Signings" (六签)** (NDRC Operations〔2020〕No. 1784 (发改运行〔2020〕1784号)): sign everything (contracted energy ≥95% of last year's actual consumption or the prior three-year average, relaxable to 90%), sign long (annual-based, encouraging 2~3 years or more), sign with witnesses (见签), sign by time segment, sign in a standardized way, sign electronically;
- Signing with curves is key: bilateral contracts decompose their own time-of-use curves; where only energy was signed without curves, typical consumption curves plus renewable forecasts are used;
- The 2025 revised Basic Rules for Medium and Long-Term Power Trading (NDRC Energy Regulation〔2025〕No. 1656 (发改能源规〔2025〕1656号)) added continuous-operation products such as green power D-3 and D-3 rolling matching (superseding the main body of Document No. 889); national medium/long-term turnover in 2025 was 4.81 trillion kWh (incl. green power 0.27 trillion and grid agency power purchase (代理购电) 0.72 trillion).

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

### 4.4 The Core Logic of Linkage
**The transparency and stability of the spot mechanism determine medium/long-term liquidity**: the US once hit major turbulence because its spot market was imperfect; the UK saw market liquidity decline as generation-retail integration deepened; the Nordic financial sector held no special advantage, yet its medium/long-term market stayed robust over the long run thanks to sound spot design. Implication for China: build the spot market first — only then does medium/long-term financialization have a foundation.

---

## 5. Ancillary Services and Capacity Mechanisms

### 5.1 Spectrum of Ancillary Service Products
- Classification: basic (primary frequency regulation, basic peak regulation, basic reactive power — unpaid) vs compensated (AGC, compensated peak regulation, spinning reserve (callable within 10 min), compensated reactive power, black start, etc.);
- Three functional categories: active-power balancing (frequency regulation/reserve/peak regulation), reactive power and voltage, and service restoration (black start);
- **The "Two Rules" (两个细则)** (originally SERC 2006; current versions NEA Regulatory Regulation〔2021〕No. 60/61 (国能发监管规〔2021〕60/61号)): essentially a mutual-aid compensation mechanism rather than a market, with the scope of administration extended to all grid-connected entities at 35 kV and above; products added include AVC, low-frequency regulation (East China 49.93 Hz), hot standby, fast load rejection, planned shutdown/cold standby (Northwest/Southern 72 h), and stability-control unit tripping; once the spot market is built, these must be unbundled from integrated energy pricing;
- **Peak regulation (调峰) is a uniquely Chinese product** (abroad it emerges naturally from the real-time market/balancing mechanism): originated in the 2006 Two Rules → 2014 the Northeast's first peak-regulation market → 2019 full coverage in the Northeast of "valley-filling, peak-topping" → substitutable by spot time-of-use prices → **the 2025 Basic Rules for the Electricity Ancillary Services Market explicitly shut down peak-regulation markets in regions with continuous spot operation**, with costs shared to the user side; at publication, 16 provinces had peak regulation, 15 frequency regulation, 2 ramping, and 6 regional markets nationwide.

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

- **Coal power capacity price (容量电价)** (NDRC Pricing〔2023〕No. 1501 (发改价格〔2023〕1501号, Notice on Establishing a Capacity Price Mechanism for Coal Power), effective 2024-01-01): fixed cost set uniformly at CNY 330/kW·yr, ~30% recovered in 2024-2025 (≈CNY 165/kW·yr), **≥50% from 2026** (most provinces execute at CNY 165/kW·yr; Guangdong 165, Tianjin 231 — details to be verified); apportioned to commercial and industrial users through system operation fees;
- Stranded cost treatment tools: asset portfolio restructuring, CfDs, transition electricity surcharges (adding ~8%~12% to the bill), securitization (CCC→SPV→SCB), and capacity-market recovery netted via Net CONE;
- Peaker logic: a 50 MW old oil unit running 5 h/yr must bid above USD 1000/MWh to cover its full cost — explaining the inevitability of scarcity pricing.

---

## 6. Settlement, Metering and Imbalance Funds

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

## 7. China Policy Framework and Provincial Practice (as of 2026-09)

### 7.1 Policy Document Timeline (the essential backbone)

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

### 7.2 Provincial Spot Markets in Official Operation (as of early 2026)

| Market | Official operation since | Notes |
|---|---|---|
| Shanxi | 2023-12-22 | First in China |
| Guangdong | 2023-12-28 | First simulation in 2018-08 |
| Shandong | 2024-06-17 | High renewable share, longest negative-price hours |
| Gansu | 2024-09-05 | Went official after ~40 months of continuous settlement trial operation |
| Inner Mongolia West | 2025-02-24 | First "single-track" (单轨制) market (all-energy spot) in China |
| Hubei | 2025-06 | Marking the Document No. 394 node |
| Zhejiang | 2025-08-07 | First in the Yangtze River Delta; 463 days of continuous settlement trial |

The inter-provincial spot market is in official operation; Fujian/Sichuan/Liaoning/Chongqing/Hunan and others are in continuous settlement trial operation; Anhui/Shaanxi aim to go official by end of 2026-06; by end-2025 provincial spot markets reached basically full coverage (16 regions in continuous settlement trial). **In 2025, national market-traded electricity was 6.64 trillion kWh (about 60% of total societal consumption)**.

### 7.3 Features of the First Pilot Batch (understanding "tailoring to local conditions")
- **Zhejiang**: government-authorized CfDs covering ~90% of energy for a smooth transition; "dual-differential" (双差价) settlement; users opened in three stages starting from 110 kV;
- **Shanxi**: pioneered the fusion of spot and peak regulation (deep-peaking market suspended upon continuous settlement from 2020-11); 31 units retrofitted for flexibility, adding 2.27 million kW of downward regulation; price limits progressively relaxed from 0~332 to 0~1500 CNY/MWh; first practical circuit-breaker activation nationwide;
- **Shandong**: pioneered the capacity compensation price (charged to users to compensate market-based units' fixed costs); negative prices and "five-tier" (五段式) time-of-use pricing (deep-valley discount of 90%);
- **Sichuan**: wet/dry season split — hydropower competes in the wet season and thermal in the dry season, with a "no water spilled" principle for run-of-river plants;
- **Fujian**: full consumption of clean energy (51.57% of installed capacity) + full delivery of medium/long-term contracts; clean energy scheduled first in the day-ahead as the boundary;
- **Gansu**: the "fishing method" (钓鱼法) — minute-level monitoring of renewable completion rates, clawing back undelivered schedules and reallocating to those that delivered; with a high renewable share, energy first, then frequency regulation.

### 7.4 2025 Price Characteristics (market sensing)
- Spot averages fell broadly: Guangdong user-side average settlement price CNY 0.3803/kWh (−14.2%); day-ahead average declared price 319.0 li/kWh (厘);
- **Shandong negative prices exceeded 1500 hours for the year** (touching the −80 CNY/MWh price floor for ~1145 h); 2025-04 solar spot settlement average ~CNY 0.02/kWh; holiday real-time range 1047.51 to −80 CNY/MWh;
- Shanxi peak-valley spread +43% YoY, the largest in China (average spread ~0.3~0.5 CNY/kWh); Inner Mongolia West the only one narrowing (−14%);
- Overall trend: midday negative prices spreading, peak-valley spreads widening → rising value of storage "charge low, discharge high" and flexible load; international benchmarks: PJM 2026/27 capacity auction cleared at USD 329.17/MW-day (at the cap), ERCOT 2025 real-time average ~USD 38/MWh.

---

## 8. Full Market Entry of Renewables (Document No. 136 is the watershed)

### 8.1 Policy Essentials (NDRC Pricing〔2025〕No. 136, 2025-02-09)
- Renewables' on-grid energy **in principle enters the power market in full**, with on-grid prices formed through market trading;
- **Grid-connection cutoff at 2025-06-01 for full capacity** separates existing/incremental projects;
- Outside the market, a **"sustainable development price settlement mechanism"** is established (differential settlement at the mechanism price, refunding excess or making up shortfalls) — essentially an out-of-market CfD, settled on energy, with hourly curve matching not yet required;
- Existing-project mechanism prices are generally ≤ the local coal benchmark price; incremental prices are formed by **bidding** (with upper and lower limits); the execution period is 12 years in most provinces (national scope to be verified); mechanism energy scale is linked to non-hydro consumption responsibility weights — a dual track of "floor protection for old projects, bidding for new projects";
- By end-2025, 14 regions had issued implementation plans.

### 8.2 Provincial Mechanism Price Quick Reference (2025)

| Province | Existing-project mechanism price | Incremental mechanism | Notes |
|---|---|---|---|
| Shandong | CNY 0.3949/kWh (= benchmark price) | Annual bidding (minimum declared adequacy 125%) | First auction: wind 0.319, solar 0.225 CNY/kWh |
| Guangdong | CNY 0.453/kWh | Bidding range 0.2~0.453 CNY/kWh | Nearly 80 million kW entered the market |
| Inner Mongolia West | CNY 0.2829/kWh | Not yet in the mechanism | Most conservative |
| Gansu | CNY 0.3078/kWh | Limits 0.2447/0.1954 CNY/kWh | First batch cleared at the floor; first generation-side capacity compensation |
| Beijing | CNY 0.3598/kWh | Floor of 12 years | 100% of energy included |

### 8.3 Capability Requirements for Market Entry (trading capability is revenue)
- The revenue model shifts from "guaranteed volume and price" (保量保价) to "market price + mechanism differential": midday troughs/negative prices become routine → **power forecast accuracy, bidding strategy, and curve decomposition become hard requirements of trading capability**;
- Guaranteed utilization hours (full guaranteed offtake) and reasonable utilization hours (subsidy determination, MOF〔2020〕No. 4/5 (财建〔2020〕4/5号)) are two different concepts: the former governs the market-entry boundary, the latter governs subsidy phase-down;
- Consumption responsibility weights (NDRC Energy〔2019〕No. 807 (发改能源〔2019〕807号)) + GECs (from NDRC Energy〔2017〕No. 132 (发改能源〔2017〕132号); full-coverage issuance from 2024) are the pillars of the quota side; green power trading reached 0.27 trillion kWh in 2025.

---

## 9. Virtual Power Plants and Demand Response

### 9.1 National Policy Framework (NDRC Energy〔2025〕No. 357, 2025-03-25)
- Positioning: a **resource-aggregation type of new market entity**, may participate as a whole in medium/long-term/spot/ancillary services (engaging in electricity purchase and sale requires an electricity retailer (售电公司) license);
- Targets: **regulation capacity above 20 million kW by 2027 and above 50 million kW by 2030**; at publication ~470 projects nationwide with a maximum regulation capacity of 16.85 million kW;
- Rule essentials: a single resource may not be aggregated by two or more VPPs simultaneously, nor participate repeatedly in markets during aggregation; demand response goes through the new-type electric power load management system, while spot/ancillary services go through the dispatch automation system.

### 9.2 Three Development Stages (National Dispatching Center framework)
① **Invitation-based (邀约型)** (current mainstream: government/grid issues invitations with subsidy incentives) → ② **Market-based (市场型)** (routine quantity-price bidding (报量报价) into the market; State Grid Jibei demonstrated first; Shanxi entered day-ahead spot with "quantity-price bidding" in 2023-09) → ③ **Cross-space autonomous dispatch type (跨空间自主调度)** (cross-provincial aggregation and optimization).

### 9.3 Comparison of Local Rules

| City | Entry threshold | Products and highlights |
|---|---|---|
| Shenzhen | Access testing + capability verification + qualification review | Real-time precise response at a fixed **CNY 5/kWh** (stackable with provincial/municipal/Two Rules subsidies); as of 2024-03: 45 operators, 5.10 million kW connected, 1.40 million kW real-time adjustable; platform investment subsidized at 10% of response revenue (≤CNY 2 million/yr) |
| Shanxi | Testing of regulation response capability/time/accuracy/aggregation capacity | Two categories: load type + source-grid-load-storage integration; quantity-price bidding into spot; participates in frequency regulation/reserve |
| Shanghai | Aggregation ≥1 MW and ≥2 h (Lingang 1000 kW/30 min) | "1+5" system; V2G reward CNY 50/kW·yr; **2025-08: China's first million-kW-class invocation at 1.1627 million kW** (29 operators) |
| Gansu | Aggregator threshold 10 MW→5 MW | — |

- DR subsidy benchmarks: peak-shaving invitations CNY 0~5/kWh, valley-filling 0~1 CNY/kWh; real-time/quasi-real-time ~2.5 CNY/kWh in many regions; interruptible load bidding cap CNY 15/kW; Jiangsu short-time max 4.8 CNY/kWh; Guangzhou peak-shaving ≤3.5 CNY/kWh;
- Vehicle-grid interaction V2G: pilots in 9 cities (Shanghai/Changzhou/Hefei/Huaibei/Guangzhou/Shenzhen/Haikou/Chongqing/Kunming); Guangzhou discharge subsidy ≤5 CNY/kWh (owners receive ~3.5).

### 9.4 Business Models and Profit Logic
- **Five revenue streams**: demand response subsidies + spot peak-valley arbitrage + ancillary services (frequency regulation/reserve) + capacity compensation + green power/GEC services;
- Quantified sense: peak-regulation compensation ~CNY 0.3/kWh; leading VPPs draw nearly 60% of revenue from spot + ancillary services, with AI load forecast accuracy above 90%; the peak-valley arbitrage market is ~CNY 3 billion → projected to exceed CNY 40 billion by 2030, with VPP adjustable capacity ~82 GW; operators and resource owners commonly split **1:9**; capacity compensation accounts for 40%~60% of storage-aggregation revenue;
- Three-layer technical architecture: resource layer (distributed generation/controllable load/storage/charging piles) → aggregation layer (forecasting, optimization, baseline calculation) → trading layer (submission, clearing, settlement);
- **Customer baseline load (CBL) calculation** (the core of settlement disputes): the mainstream similar-day averaging method — the latest 5 same-type days, excluding abnormal days with daily energy deviation of about ±25%, times a correction factor; Zhejiang deems a response valid when "both maximum and average load are below the baseline + response rate ≥50%".

### 9.5 International Benchmarks
- **FERC Order 2222** (2020-09): allows DER aggregation into wholesale markets, with minimum aggregation size not exceeding 100 kW; CAISO complied fastest (2023-05), full implementation expected by end of 2026 — compare China's provincial thresholds of 1 MW (Shanghai) to 5 MW (Gansu);
- **Next Kraftwerke** (Germany): aggregates 15,000+ units, over 10 GW of capacity, traded 15.1 TWh in 2024; ~10% of Germany's secondary frequency regulation market (low-controllability wind/solar go to the energy market; hydro and biomass to the frequency regulation market);
- **Tesla Autobidder**: manages over 3 GW of storage, cumulative revenue ~USD 330 million (via the ERCOT ADER pilot, 15-minute price forecasting);
- **OhmConnect shutdown**: a cautionary tale of residential demand response models reliant on subsidies;
- US VPP scale exceeds 30 million kW, over 4% of peak load; Japan targets 25 million kW by 2030.

---

## 10. Carbon Market and Corporate Carbon Management

### 10.1 National Carbon Market (CEA) Framework and Evolution
- **Launch**: went live 2021-07-16 (trading at the Shanghai Environment and Energy Exchange, registration at China Carbon Emissions Registration (中碳登)); first batch ~2000 key emitting units in the power sector;
- **Institutional design**: allowance allocation mainly via the **benchmark method + free allocation**, intensity-based control with no absolute cap; CCER offset limit **5%**;
- **Expansion** (2025-03 "Work Plan for Covering the Iron and Steel, Cement, and Aluminum Smelting Sectors in the National Carbon Market"): 2024 is the first control year, first compliance by end-2025; covering ~3700 entities and ~8 billion tonnes, from 40% to 60%+ of national CO₂ emissions (controlling CO₂/CF₄/C₂F₆); ~6000 entities expected by the end of the "15th Five-Year Plan";
- **Regulation**: the Interim Regulations on the Administration of Carbon Emission Trading (《碳排放权交易管理暂行条例》, State Council Decree No. 775, effective 2024-05-01) — failure to surrender in full: a fine of **5-10x** the market average price of the month preceding the surrender deadline; fraudulent reporting: confiscation + 5-10x fine; "dual penalties" for technical service institutions (previous pilot penalties were generally only CNY 30,000~150,000);
- Compliance rhythm: power allowance pre-allocation = 70% of the previous year's verified emissions; 2023 compliance rate 99.98% (5.244 billion tonnes); expanded sectors conduct monthly documentation from 2025-07.

### 10.2 Carbon Price Trends (price sensing)

| Time point | CEA price (CNY/tonne) |
|---|---|
| 2021-07-16 opening | 48.00 |
| 2024-04-24 | 100.59 (first break above 100) |
| 2024-11 peak | 106.02 (2024 average 91.8) |
| 2025-10 low | ~50 (post-compliance demand decline + new carry-over rules) |
| Early 2026-09 | ~93~97, approaching 100 (supply contraction) |

The 8 pilots averaged CNY 44.1/tonne in 2024 (~54% below the national market): Beijing highest (2024 ~62.7; briefly above 100 online in 2025; the only pilot with a CNY 20~150 stabilization band), Shanghai stable at 66.7, Hubei first in volume with mid-range prices, Shenzhen volatile, Tianjin/Chongqing weak. **Pattern: carbon prices show strong cyclicality — spiking in compliance periods, falling between them**; tighter caps + sector expansion are the main long-term upward logic.

### 10.3 CCER (China Certified Emission Reduction, 国家核证自愿减排量)
- **Restarted 2024-01-22** (trading at the Beijing Green Exchange, registration in the registration system); 2025-03: the first 9 projects (offshore wind + afforestation carbon sinks) completed registration;
- Methodologies: first batch (2023-10) 4 items = afforestation carbon sink, grid-connected solar thermal (CSP), grid-connected offshore wind, mangrove creation; second batch (2025-01) 2 items = low-concentration coal mine gas, highway tunnel lighting; 19 items cumulatively published/for comment in 2025;
- Price: 2025 average transaction price CNY 70.76/tonne, **above the CEA average for the same period (62.36)** — scarcity of supply; the rule of thumb "allowance price ≈ CCER price ÷ 0.7" (an old pattern, inverted after the restart; monitor dynamically);
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
- **CBAM**: transitional period from 2023-10, **definitive implementation from 2026-01-01** (buying certificates, priced off the EU ETS auction average); covers steel/cement/aluminum/fertilizer/hydrogen/electricity; exports of one tonne of blast-furnace steel pay ~EUR 44.79 (≈CNY 375) vs ~CNY 200 domestic profit per tonne of steel — forcing the combination of "green power trading + VPP response + carbon footprint accounting + storage arbitrage";
- International mechanisms: GHG Protocol Scope 2 revision expected 2027 Q2 (contested point = hourly matching); SBTi Net-Zero Standard; Paris Agreement Article 6 ITMOs will link global carbon prices (CDM CERs registered after 2013 are the first candidate assets).

### 10.6 Corporate Carbon Management Methodology (carbon management consulting framework)
- The closed loop: **baseline (inventory) → targets (SBTi/intensity metrics) → plan (seven directions: management-driven reduction / energy efficiency / more green power / electrification / zero-carbon readiness / raw material and fuel substitution / non-energy reduction) → offsets (environmental credits must be generated within the last 3 years and must be cancelled; proximity principle: direct purchase > same grid > same country) → communication (annual reports, CDP ratings A-F in 9 grades) → system (ISO 50001 PDCA)**;
- Carbon-neutrality timing discipline: own operations 2030, full value chain 2050, no dimension later than 2060; expansion-stage industries (wind/solar/storage, NEVs) should use carbon intensity metrics;
- Internal carbon pricing in three tiers: retrofit incentives → carbon cost accounting → internal carbon trading (200+ companies globally, average ~USD 20/tonne);
- Seven-piece carbon asset management kit: low-carbon steering group, annual carbon inventory, abatement potential analysis, energy-saving management (GB/T 23331), carbon asset investment, trading management, internal controls (VaR + stress testing + tiered authorization);
- Trading strategy: judge surplus/deficit from emission forecasts, buy low and sell high in batches; **pre-compliance panic buying pushes carbon prices up 20%~30%** (historically lifted from 50-60 to 75-80 CNY) — compliance-period liquidity risk is the No. 1 risk of carbon asset management.

---

## 11. Trading Strategy and Risk Management

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
①Grid operational security ("dual high": high shares of renewables + power electronics; monitor supply-demand ratio/corridor loading/reserves with early warning); ②market power (cap shares, monitor withholding, dilute via FTRs); ③long-term supply (capacity mechanisms, see 5.3); ④price volatility (scientific price limits, futures/options hedging, virtual bidding); ⑤entity credit (performance guarantees, credit line = unsecured credit + secured credit; trading suspended if usage exceeds 100% without replenishment).

### 11.5 Entity Capability Checklist (spot market entry "health check")
- Rules layer: registration/credit management, procedures for each product, settlement formulas, disclosure deadlines;
- Technical layer: dedicated workstations on the technical support system, submission/disclosure time nodes, 15-minute generation and consumption forecasting;
- Strategy layer: price forecasting models, bid decisions, portfolio optimization across medium/long-term + spot + ancillary services;
- Risk layer: price exposure management, deviation assessment simulation, cash flow stress testing, settlement reconciliation (daily allocation checks).

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
| Capacity price | CNY 330/kW·yr × recovery ratio (~30% in 2024-25 → ≥50% from 2026) | Coal fixed cost |

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
| 碳关税 | CBAM | EU Carbon Border Adjustment Mechanism (definitive period from 2026) |
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
10. Comparing provinces on a single spot price (one must also compare price-limit structures, renewable share, and mechanism prices).

### 14.3 Data Timeliness Discipline
- Time points of this skill's book knowledge: spot market material 2019-2023; carbon practice data 2016 (mechanisms still valid, numbers need updating); carbon management 2021; web research 2026-09-12;
- Policy figures (official-operation lists, mechanism prices, subsidy standards, capacity price ratios) **change every year** — always answer with "as-of time point + verification entry points";
- High-frequency verification entry points: NDRC website (pricing/operations), NEA (market regulation/qualifications), provincial DRCs/energy bureaus, Beijing Power Exchange and provincial exchange platforms, the national carbon trading site (cets.com.cn), China Carbon Emissions Registration (中碳登), ICAP annual reports.

---

## 15. Knowledge Sources and Maintenance

### 15.1 Book Sources
1. 101 Questions on the Electricity Spot Market (《电力现货市场101问》), compiled by the National Power Dispatching and Control Center, China Electric Power Press, 2021 — the backbone of spot concepts, mechanisms, and domestic/foreign models
2. Electricity Spot Market in Practice (《电力现货市场实务》), compiled by the National Power Dispatching and Control Center, China Electric Power Press, 2023 — architecture, clearing, settlement, technical support systems, provincial practice
3. Principles of Power System Economics (《电力系统经济学原理》, Kirschen & Strbac), trans. Zhu Zhizhong — market economics theory, LMP/congestion/investment theory, classic worked examples
4. China Carbon Emission Trading in Practice (《中国碳排放权交易实务》, Meng Zaoming, Ge Xing'an et al.) — carbon market mechanisms, pilot comparisons, MRV, CCER development
5. Carbon Management: From Zero to Carbon Neutrality (《碳管理：从零通往碳中和》, Wang Jun) — carbon accounting systems, carbon asset development, corporate carbon management
6. Principles of Economics, micro/macro volumes (《经济学原理》微观/宏观分册, Mankiw) — the basic economics framework (supply-demand, elasticity, market structure, externalities)

### 15.2 Policy and Market Research (2025-2026)
- Policies: NDRC Order No. 20, No. 1217, No. 1501, No. 136, No. 357, No. 394, No. 1656, the Basic Rules for the Electricity Ancillary Services Market (2025-04), the Interim Regulations on the Administration of Carbon Emission Trading (Decree No. 775), the CBAM regulation, etc.;
- Data: NEA "2025 China Electricity Market Development Report", annual reports of provincial power exchanges, Fudan Carbon Price Index, ICAP;
- All items are annotated with source URLs and dates; the full research records are in the research notes under knowledge/.

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
- Items marked "(to be verified)" (about 8) should prompt the user to verify when cited;
- Provincial rules update fast; this skill does not replace real-time policy search.
