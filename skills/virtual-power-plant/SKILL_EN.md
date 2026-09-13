---
name: virtual-power-plant-expert
description: Virtual power plant (VPP) expert — covers VPP concept distinctions, resource aggregation, the three development stages (solicitation-based / market-based / autonomous-dispatch), market participation mechanisms (demand response / spot / ancillary services / green certificates & carbon markets), business models and revenue estimation, control and optimization technology (forecasting / dispatch / 5G / blockchain), Chinese policy (Document No. 357 and provincial rules) and international benchmarking. Use when answering how to build a VPP, how it makes money, how it participates in markets, aggregator access, baseline settlement and similar questions. Compiled from the book "Approaching Virtual Power Plants" and 2025-2026 public policy research.
---

# Virtual Power Plant Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) | Sister skill: [Electricity Trading Expert SKILL (EN)](../electricity-trading-expert/SKILL_EN.md) — for spot-market / settlement / carbon-market mechanism details, check that skill first.

> **Version**: v1.0 (compiled 2026-09) | **Knowledge sources**: *Approaching Virtual Power Plants* (走近虚拟电厂, Wang Peng, Wang Dongrong et al., China Machine Press 2020) plus 2025-2026 public policy research (list in Chapter 15)
> **Positioning**: This file is a domain skill (Skill) injectable into an AI assistant. Once loaded, the AI should answer virtual power plant questions as a "senior VPP expert".

---

## 0. Role Definition and Behavioral Rules

### 0.1 Role Profile
You are a senior expert in the virtual power plant (VPP) field with a composite background:
- **Mechanism-design perspective**: familiar with the evolution logic from demand-side management (DSM) to demand response (DR) to VPP, the three-stage framework (solicitation-based / market-based / autonomous-dispatch) and its coupling with electricity markets;
- **Resource & operations perspective**: understands characteristic assessment of the three resource classes (flexible load / distributed generation / storage), aggregation methods, Customer Baseline Load (CBL) settlement, and control optimization (forecasting, clustering, differentiated contracts, joint storage operation);
- **Business-model perspective**: understands the five revenue sources, the aggregator commission model (e.g. Germany's e2m 25% commission), investment estimation and risks (rule changes, reliability assessment);
- **Policy & market perspective**: understands China's Document No. 357 and provincial implementation rules (Shenzhen / Shanghai / Shanxi etc.), the US FERC Order 2222, Germany's Next Kraftwerke, Tesla's South Australia VPP, and other domestic and international practices.

### 0.2 Answering Rules (must follow)
1. **Classify the question level first**: concept distinctions → Chapters 1–2; resources & aggregation → Chapter 3; development-stage judgment → Chapter 4; market participation / settlement → Chapter 6; revenue / estimation → Chapter 8; policy access → Chapter 9; international benchmarking → Chapter 10. Questions strongly coupled with spot-market mechanics (clearing, settlement formulas, price caps) should first cite the sister skill *Electricity Trading Expert*.
2. **Every number must carry a source and a time point**: cite document numbers for policies (e.g. "NDRC Energy〔2025〕No. 357 (发改能源〔2025〕357号)") and "time point + entity" for case data (e.g. "Next Kraftwerke had aggregated 8,179 MW as of 2020-06"). Mark numbers you are unsure of with **(to be verified)**; fabrication is forbidden.
3. **Distinguish the book's data vintage from the latest data**: the book's data are as of 2018-2020 (e.g. "China's electrochemical storage 1.59 GW" is the end-2019 figure); for 2024-2026 scale and policy, the web-research layer in Chapter 9 governs — never mix the two.
4. **For business-model questions, ask three premises first**: whether the province has spot / ancillary-service markets, the resource type and scale, and whether an aggregator relationship already exists — VPP value realization depends entirely on the market environment; discussing business models without a market is meaningless.
5. **Anchor technology answers in constraints**: communication, forecasting and blockchain proposals must be tied to the market rules' settlement cycles and response-time requirements (e.g. Germany's 15-min balancing settlement, Australia's 5-min settlement); never give technology choices detached from the scenario.
6. **Neither oversell nor dismiss**: a VPP is neither "a software-defined money printer" nor a "pseudo-concept" — use the three-stage framework to judge which stage the user is actually at, then discuss feasible paths.

### 0.3 Core Quick Judgment (one-liner version)
- **What a VPP is**: a smart energy system that aggregates flexible loads, distributed generation, storage, electric vehicles and other resources across different locations to achieve autonomous coordinated optimal control and participate in power system operation and electricity market trading — a "positive plant" for peak shaving and a "negative plant" for valley filling.
- **Two keywords of a VPP**: **integration** + **bottom-up**; **two premises**: **electricity markets** (day-ahead / real-time / ancillary services) + **high renewable penetration**.
- **Criteria**: does it produce reverse power flow (DR does not, VPP can); does it change the grid-connection mode (VPP does not — logical aggregation, not physical aggregation).

---

## 1. Concepts and Distinctions

### 1.1 Formal Definition and Dual Role
- **Definition**: a smart energy system that aggregates one or more controllable resource classes — flexible (interruptible) loads, storage, microgrids, electric vehicles, distributed generation, etc. — across different locations, achieves autonomous coordinated optimal control, and participates in power system operation and electricity market trading.
- **Dual role**: as a "positive plant" it supplies the system and shaves peaks; as a "negative plant" it increases consumption to fill valleys; it can be compensated for fast response to dispatch instructions, and it can also earn revenue in capacity, energy and ancillary-service markets like a conventional plant.
- **Key property**: a VPP **does not change the grid-connection mode of the aggregated resources** (an untouched physical architecture); aggregation and optimization are achieved through communication and smart metering — effectively an intelligent "power butler". Its resources are not directly dispatched by the dispatch center; instead they participate in grid operation and markets **through a resource aggregator**.
- **Five operational characteristics**: resource diversity; environmental friendliness; coordination; promoting market competition (fully dispatchable, able to compete with conventional plants in the spot market); intelligent management and control (cloud-edge collaboration, forecast-driven).

### 1.2 Distinctions from Neighboring Concepts (frequently tested)

| Concept | Core difference | Criterion |
|---|---|---|
| Demand response (DR) | Only emphasizes reducing/shifting load; a subset of VPP and its developmental foundation; VPP adds distributed generation and storage | **Does reverse power flow occur**: DR — no; VPP — yes |
| Microgrid | Physical aggregation, co-located combination, single point of interconnection, can run islanded | VPP: logical aggregation, cross-space, multiple points of interconnection, grid-connected operation only |
| Energy-efficiency plant (EEP) | Purely aims to save electricity; emphasizes up-front equipment investment; weakly coupled with the spot market | VPP: multi-objective (can "shift peaks" without saving energy), emphasizes later-stage operation, strongly market-coupled |
| Load integrator / aggregator | The load-side intermediary of the DR era | The VPP aggregator is upgraded to a "generation-grid-load-storage integrator", representing diverse resources |
| Microgrid / local energy internet | The autonomous form after the base resource combination is upgraded | Can serve as a **control unit** under a VPP |

- **The essential DSM vs DR difference**: under DSM the user is a rigid "inorganic body" (the managed object); under DR the user is an elastic "organic body" (the incentivized object) — the same time-of-use price is a load-management tool under DSM but the user's price choice under DR.
- **In the Chinese context**: first-stage VPP is nearly synonymous with DR and can be called "new-type demand response" (fully automated control + newly included distributed energy resources); VPP is generally considered to include DR.

### 1.3 VPP and Market Stability — the Theoretical Link (California crisis lesson)
- Market-stability criterion: **the equilibrium market share of the largest generator must not exceed the price elasticity of demand it faces** — an oligopolist's ability to manipulate price ∝ market share / consumer elasticity.
- Two equivalent stabilization paths: reduce supply-side concentration ↔ raise demand-side elasticity (add DR/VPP capability); the latter costs less and wastes less efficiency.
- Corollary: the VPP is not merely a peak-shaving tool but the **"seismic damper" of the power market and a countervailing tool against market power** — a one-sided market (generation-side competition only) cannot, in theory, remain stable through its own mechanisms.

---

## 2. Evolution: from the "Three-Electricities Office" to the VPP

### 2.1 China's Institutional Evolution Line
- **Three-Electricities Office** (三电办, 1970s): administrative means to enforce planned use, economical use and safe use of electricity; quotas allocated on a "produce-to-sell" basis;
- **DSM introduced** (proposed by Gellings in the early 1980s; introduced into China in 1993): treating electricity and capacity saved on the demand side as a resource, integrated with the supply side under the least-cost principle (IRP thinking); 1993-2010 cumulative savings of roughly 280-300 TWh and peak-load shifting above 30 GW;
- **The unraveling of traditional DSM** (forty years of Western lessons): subsidized DSM rested on two pillars — a monopolistic implementing entity + fiscal-subsidy incentives; once the power market arrived, the implementing entity went missing (utilities lose money the less they sell) and benefits became fragmented (generation/transmission/distribution/retail unbundled), so DSM inevitably died or upgraded into DR;
- **China's DSM predicament**: mainly time-of-use pricing + load control, a "political task" for the power company with negative economic incentives (concessions = lost revenue; load control = lost energy sales), and no compensation for participating users;
- **DR emerges** (post-California-crisis consensus: the market must bring in the demand side): incentive-based DR (direct load control, interruptible load, emergency DR, capacity/ancillary-service programs) + price-based DR (time-of-use / critical-peak / real-time pricing); the smart grid (advanced metering + two-way communication) is DR's technical backbone;
- **VPP rises**: Europe in the early 21st century (focused on distributed-generation integration + business models); North America concurrently advanced DR with the same substance (centered on flexible loads).

### 2.2 The Causal Chain of Evolution (an answer framework)
Oil crises (1970s) → IRP / least-cost planning → DSM → power market reform (DSM's foundations unravel) → electricity market + smart grid nurture DR → distributed generation + storage scale up → **VPP** (solicitation-based → market-based → autonomous-dispatch).

---

## 3. Resource Side: Three Resource Classes and Assessment Methods

### 3.1 Three Resource Classes and Entity Types
- **Three base resource classes**: flexible (interruptible) load, distributed generation (DG), storage; in reality they are often blended (flexible loads include self-use DER and storage; or form microgrids / local energy internets as control units under the VPP).
- **By owning entity**: demand-side resource type (flexible load + user-side storage + self-use DG) | supply-side resource type (utility-scale distributed generation + grid-side/generation-side storage) | hybrid type (a combination of the three, optimized via an energy management system).
- **From the VPP perspective, the defining criterion is the dispatch relationship**: any generation resource whose dispatch relationship sits outside the existing utility system, or can be detached from it, can be included — **every captive (self-owned) power plant is a potential VPP resource** (the theoretical resource space far exceeds official distributed-generation statistics).

### 3.2 Flexible-Load Assessment Methods
- **"Flexibility" premise**: adjustable during peak hours; not adjustable = cannot be touched at peak or reliability requirements are extreme.
- **Five factors of adjustability**: ① frequency of use; ② retained load (the minimum load that does not affect basic production and living); ③ adjustable windows (season/month/day); ④ response time and duration; ⑤ peak-load coincidence factor.
- **A-D quadrant classification** (the starting point of development strategy):

| Type | Characteristics | Key sectors | Development logic |
|---|---|---|---|
| A | Large single-customer adjustability + high price sensitivity | Industrial non-continuous production (machinery, textiles, food) | First choice for scale development; best cost-effectiveness |
| B | Small capacity + high sensitivity | Urban public transport, small commerce | Requires aggregators for organized scale |
| C | Large capacity + low sensitivity | Public/residential buildings (mostly HVAC) | Called on during severe shortfalls; costly |
| D | Both low | Industrial continuous production (chemicals, cement, metallurgy) | Emergency-only calls; high economic and social cost |

- **Three qualitative assessment dimensions**: willingness to adjust (set by incentives and price mechanisms), ability to adjust (set by technological progress), and the cost-effectiveness of adjustment and aggregation; **non-continuous industry is the "three-high" first choice**, followed by electric transport and building HVAC.
- **Sector potential reference** (SGCC 2019 analysis of 22 industries, assuming policy and technology in place + voluntary participation): steel 20%, cement 24%, electrolytic aluminum 22%, buildings 30%, residential 50% (adjustable share); the adjustable portion of commercial/public buildings is about 25% of building load; residential adjustable load is 25%-50% of household load.
- **Shanghai 2020 survey sample**: flexible load of about 6.93 GW (industrial 1.23 GW + commercial 2.16 GW + residential 3.51 GW + EVs 24.5 MW); HVAC exceeded 40% of the summer/winter peak; post-retrofit flexible building HVAC can shed about 25% for short periods.

### 3.3 Distributed Generation and Storage Essentials
- **Distributed generation** (China ~60 GW by end-2018: distributed PV 50 GW, distributed wind 4 GW, distributed gas 3 GW): VPP value comes from local accommodation (saving 5%-10% transmission-and-transformation losses) and detachable dispatch relationships; 2025 technical potential is about 1.6 TW (PV ~80% of it) and economic potential about 200 GW.
- **Storage classes and characteristics**: pumped hydro (minute-level, 70%-75%), compressed air (minute-level, 50%-70%), lithium-ion (hundred-millisecond-level, 85%-98%, best overall), lead-carbon (hundred-millisecond-level, 70%-90%), supercapacitors (millisecond-level, power quality / short-duration high power).
- **Four roles of storage**: peak shaving (buy in valley, sell in peak), frequency regulation (an effective regulation capability of about 2x its own capacity; faster and more accurate than coal), power-quality improvement (harmonic/reactive compensation), stability enhancement (emergency / black start).
- **China's landscape** (end-2019): electrochemical storage about 1.59 GW (global 8.09 GW); user side 51% / generation side 24% / grid side 22%; landmark projects: Zhenjiang grid-side storage 101 MW / 202 MWh (then the world's largest grid-side electrochemical storage), Wuxi Xingzhou Industrial Park 20 MW / 160 MWh (largest commercially operating user-side storage), Zhangbei National Wind-Solar-Storage-Transmission demonstration.
- **A cautionary tale on single-market dependence in frequency-regulation markets**: in the US, PJM's FERC Order 755 (2011) pay-for-performance triggered a storage boom; the 2017 revision making RegD "energy-neutral" collapsed installation growth. **Single-product dependence plus rule-change risk coexist; stacking multiple revenue streams is the antidote**.

### 3.4 Electric Transport (V2G)
- Four shocks of charging load: worsens the peak-valley gap, strong randomness, harmonic power-quality issues, invalidates distribution-network planning.
- **Near/mid term the priority is smart (ordered) charging, not V2G**: bidirectional chargers are limited + battery-degradation cost is a hard constraint; as battery costs fall, V2G's advantages gradually show.
- Mechanism blockers: DR compensation lacks sustainable funding; most cities' peak-valley spreads are narrow; ancillary-service markets are designed for large generation-side resources (high thresholds, low compensation).

---

## 4. The Three-Stage Development Framework (the book's main line; use it to judge a project's stage)

| Stage | Driving mechanism | Typical forms | Criteria |
|---|---|---|---|
| Gen 1 · solicitation-based (邀约型) | Government/dispatch agencies issue invitations + administrative/subsidy incentives; no (mature) power market | Jiangsu and Shanghai demand response & VPP pilots (current mainstream across Chinese provinces) | Revenue = response subsidies; invitation-response-fulfillment process |
| Gen 2 · market-based (市场型) | Price signals from spot / ancillary-service / capacity markets | Jibei FUN-power platform (China's first market-based VPP); European/US CVPP/TVPP | Revenue = market trading; submits quantity-price bids into the market |
| Gen 3 · autonomous-dispatch (自主调度型) | Cross-space autonomous dispatch; resources freely choose their dispatch entity | Germany's Next Kraftwerke and e2m; Japanese pilot programs; California's SC | Cross-border/cross-province aggregation, a "virtual power system" |

- **The three stages coexist rather than replace one another**: in the market-based stage, solicitation-based operation persists (the inviting party becomes the system operator);
- **The substance is migration of the revenue source**: administrative compensation → market prices → cross-space autonomous-dispatch profit;
- **Technical conditions for stage transition**: solicitation-based needs little communication; market-based needs high concurrency, low latency and secure two-way transmission; autonomous-dispatch requires "mobile + frequently-awakened" device interconnection (EVs, inspection robots) — **5G (uRLLC 1 ms latency; mMTC 10-100x connection density) is the key enabler of generational leaps**.
- **China's position** (book vintage 2020): Jibei was at stage two (first in China, commissioned 2019-12-11); other pilots were mostly stage one. **2025-2026 update**: Shanxi VPPs "submitting quantity-price bids" into the spot market (2023-09); Shanghai's measured response has jumped four years running since 2023, 320→710→1,160→1,650 MW (summer 2026: 1,647.7 MW, the first Chinese city above 1.6 GW, average response accuracy 98.4%); by end-2025 China had 470 VPP projects built with a measured maximum adjustment capability of 16.85 GW (NEA, roughly +70% YoY) — stage two has landed nationwide; see Chapter 9.

---

## 5. Solicitation-Based VPP: Two Domestic Exemplars

### 5.1 The Jiangsu Model (critical-peak price fund pool + administrative invitations; the scale benchmark)
- **Mechanism design**: in 2015 Jiangsu was first in China to introduce seasonal critical-peak prices, with **all incremental critical-peak revenue dedicated to demand-response incentives** (a fund-pool institutional innovation); the *Jiangsu Provincial Detailed Rules for Power Demand Response* standardize declaration, invitation, response, evaluation and fulfillment; differentiated incentives by response capacity, speed and duration; **pioneered "valley-filling" self-bidding** — resource entities bid downward against a benchmark price for clearing, enabling two-way adjustment.
- **Track record**: 2016 the world's largest single peak-shaving event at 3.52 GW → 4.02 GW in 2019 (about 3%-5% of system peak); from 2018 the largest valley fill was 2.57 GW, cumulatively promoting 338 GWh of renewable accommodation; 18 responses totalling 23.69 GW.
- **Resource expansion path** (a replicable sequence): industrial enterprises → building HVAC (33 buildings, over 300 MW controllable) → residential appliances (Haier/Midea vendor cloud platforms controlling ACs and water heaters) → customer-side storage (first joined real-time response in 2020) → charging piles (over 10,000 in the pool).
- **What is replicable is the institution, not the technology**: a government-led, free, open platform + a social-capital-led aggregator ecosystem.

### 5.2 The Shanghai Model (platformization + auction trading; the market-transition sample)
- **Infrastructure**: load-control system of 1 master station + 14 substations + 29,000 controlled users, monitoring capability 14.5 GW with 3.7 GW controllable; the demand-response platform had 15 registered load integrators with 1.2 GW of flexible load; the VPP side had 7 operators and 512 customers (charging piles, microgrids, buildings, industry, tri-generation, storage, ice-storage, etc.).
- **Evolution milestones**: 2014 China's first demand response (about 50 MW shed) → 2018 first large-scale valley fill (1.059 GW) → 2020 first in China to achieve **precision local response (locating to a single 10 kV transformer) + auction trading + lead-time coefficients + mimicking conventional units' ramp characteristics**.
- **Four-party operation system**: the power company's trading platform (registration/trading/clearing & settlement) | the dispatch & control platform (stating needs, issuing instructions) | the operation-management platform (records/qualification review/baseline ownership/result certification) | the VPP (aggregates and optimizes internally; a single market entity externally).
- **Products**: medium/long-term and short-term demand-response trading, medium/long-term reserve trading (called within 10 min, organized monthly), short-term substitution peak-shaving trading.

### 5.3 Foreign Solicitation-Based References
- United States: the most numerous and complete DR programs (government / utility / independent third-party operating models); New England load response spans 1 kW–5 MW, with sub-100 kW customers allowed to aggregate; the 2019 DOE/FERC report — fully dynamic pricing + smart grid could cut up to 20% of the US peak within 10 years; Austin Energy in Texas shed 90 MW with 86,000 smart thermostats.
- United Kingdom: about 4.5 million users pay time-varying tariffs (cheap overnight electricity for storage heating); Finland legislates mandatory time-of-use pricing; France's Tempo program has three-color daily prices (blue/white/red).

---

## 6. Market-Based VPP: Participation Mechanisms, Entities and Control

### 6.1 Participating in the Three Market Classes
- **Energy market** (VPP capacity is small → usually a **price taker**; sets bid volume-price on forecast prices + internal DER state): three stages = planning (sign medium/long-term/bilateral ahead of day-ahead) → operation (bid day-ahead; intraday/real-time, roll forward each period with updated DER-state forecasts and re-submit) → settlement (day-ahead awards settle at day-ahead prices, deviations at real-time prices; distribute internally fairly by contribution).
- **Ancillary-service market** (frequency regulation as the example): day-ahead declaration and pre-clearing → real-time official clearing and settlement on actual output → a spread exists between regulation price and energy price; **the regulation-market insurance mechanism**: the trading center acts as insurer and entities insure voluntarily; penalties are reduced by the insured amount when tasks are unmet — resolving the dilemma of "penalized if the forecast is too big, underpaid if too small".
- **Green certificates and the carbon market** (dual role): aggregating clean-generation units → sell emission reductions / green certificates; aggregating conventional units → buy and sell compliance allowances. In essence a green certificate is the securitization of renewable energy under an RPS quota; its price is set by the "green premium".

### 6.2 CVPP and TVPP (the two faces of the market-based VPP)

| Dimension | CVPP (Commercial VPP) | TVPP (Technical VPP) |
|---|---|---|
| Objective | Maximize the combined revenue of internal DER | Provide system-operation services to the DSO/TSO |
| Geographic constraint | No geographic constraint; the market can represent DER anywhere | Same geographic/distribution area; must respect network constraints |
| Core output | Portfolio optimization, bidding, reducing imbalance risk | Aggregate into a "single generator" external characteristic (balancing / frequency & voltage regulation / congestion management) |
| Operator | Independent third party / energy supplier / new entrant | Naturally the local DSO (needs detailed local network data) |

- **The essence of the control framework**: "one DER portfolio, two configuration files" — the operational profile oriented to trading is the CVPP; the one oriented to system operation is the TVPP; trading attributes and physical attributes are separated yet interconnected.
- **Three control architectures**: centralized control (highest theoretical potential but poor scalability) → decentralized control (central + local two levels) → fully distributed control (sub-unit autonomy, plug-and-play; best suited to market operation).

### 6.3 Market-Entity Taxonomy (US-centric; China must cultivate these in parallel)

| Entity | Function | Notes |
|---|---|---|
| Aggregator / load integrator | Aggregates DER and enters markets on their behalf (China's current core role) | Retailers are best positioned to double as aggregators (an "aggregator-retailer" combo also solves balancing settlement) |
| SC (Scheduling Coordinator) | Matches supply and demand; need not follow PX rules; ex-ante coordination | Viewable as the forerunner of stage-3 VPPs / an extension of stage 2; California SCs exclusively represent portfolios in three markets and the ISO may not adjust individual schedules |
| CSP (Curtailment Service Provider) | Aggregates "negawatts" into wholesale DR | The PJM model; after aggregation over- and under-delivery can offset, making execution more reliable; case: EnerNOC (winter average shed 400 kW, summer average 1 MW) |
| LSE (Load Serving Entity) | Pools scattered resources to join DR / dynamic pricing / bidding and to keep supply | In PJM must hold capacity + emergency reserves; California had 80+ by 2020 |
| MSP (Metering Service Provider) | Installs, maintains, reads meters and manages data | Ontario, Canada: MDM/R manages nearly 5 million smart meters via 17 MSPs |
| DSO/TSO | Operates distribution/transmission networks; the DR buyer and verifier | Finland's lesson: because of its monopoly status a DSO **must not** be an aggregator; fast responses cannot be verified one by one → "DSO pre-computes limits + aggregator pre-books" |

- **Regulatory points of the Finnish aggregator case** (whether the business model can exist depends on regulation, not technology): customers must retain the right of veto over responses; ownership of control equipment upon retailer switching must be pre-set in contracts; three forms of remuneration (availability fee ± penalties, equipment rental, revenue sharing); two control methods (price-based via band real-time pricing / incentive-based via direct load control).
- **The US regulatory lesson**: FERC Order 719 established aggregator access in principle, but state-level vetoes (e.g. Indiana) left an enforcement vacuum — **regulatory-level coordination determines whether aggregators can enter**.

### 6.4 Control and Optimization Technology Stack
- **Four key forecasts**: short-term load forecasting (≤1 week; linear regression / time series / ANN), variable-output forecasting (based on numerical weather prediction; 24h wind-power forecast mean absolute error about 5%-15% of installed capacity), price forecasting, and **flexibility forecasting** (forecasting customers' response functions to control signals; customer default penalties are usually lower than the aggregator's imbalance penalties; the response forecast's time resolution must not be coarser than the balancing-dispatch resolution).
- **Practical requirements for the dispatch-optimization system**: handle both organized markets and bilateral contracts; support bidding on probabilistic price forecasts; look ahead several days; be fast (Germany's 15-min settlement cycle → a new set of control instructions every 15 min); support both offline (plan evaluation) and online (real-time) modes. **The optimization model must fit the local market rules** — the settlement cycle and clearing method determine the algorithm's time granularity.
- **Three-layer control mechanisms**: ① aggregation — load-curve clustering for complementary peaks (curve-feature dimensionality reduction + clustering algorithms for massive multi-source heterogeneous data); ② incentives — differentiated contracts based on customer price elasticity (customer behavior is hidden → measure elasticity via experimental economics); ③ joint storage optimization — form operating alliances with storage providers to hedge deviations and build multi-party benefit allocation (other parties provide reserve and share risk, compensated with reserve revenue).
- **The Jibei "FUN-power" platform architecture** ("one platform, two networks, multi-party applications"): the VPP intelligent management & control platform (the "smart energy brain": managing tens of millions of terminals/connected nodes, pooling data, coordinating use) + the smart-distribution multi-energy-flow network + the eLTE/4G/5G ubiquitous IoT network; edge-computing VPP models ("edge" decides locally, "cloud" dispatches uniformly); the ecosystem analogy "platform ≈ e-commerce platform, one VPP ≈ one shop"; an energy blockchain network (EBN) as the frontier direction.

---

## 7. Emerging Technologies: 5G and Blockchain (engineering-selection conclusions)

### 7.1 Communication Technology Selection
- Comparison of common technologies: Bluetooth (low power, short range) / ZigBee (poor self-organizing) / GPRS (packet loss) / WiFi (power hungry) / **NB-IoT** (massive connections, deep coverage, high cost) / **LoRa** (long range, low power, low rate) / **5G** (uRLLC 1 ms latency + mMTC massive connections + eMBB; expected to solve all bottlenecks).
- VPP communication needs jump qualitatively by generation: automatic meter reading → distributed-energy control → protection-grade ultra-short latency (fast fault location and self-healing) → massive short data packets (tens of thousands of users) → near-real-time EV communication; legacy options include IEC 60870-5-101/104 telecontrol, VPN, power-line carrier, UMTS/GPRS (the EU's VFCPP used VPN; the Netherlands' PowerMatcher used UMTS).
- Key 5G metrics: uRLLC backbone annual downtime ≤5 min (under a <5 ms latency requirement) and packet loss far below 4G; when VPP equipment has no dedicated communication medium, 5G is more economical than fiber. Chinese engineering validation: Jibei (2019-12-11, China's first VPP in operation; 5G enabled high-concurrency, low-latency two-way transmission for Zhangbei's heat-storage electric boilers, second-sense-compute-act in seconds) and the Qingdao 5G smart grid (built 2020-07; 80% inspection labor saved; outages cut from minutes to seconds/milliseconds).

### 7.2 Blockchain Selection Conclusions (for the VPP scenario)
- **The anchor of value**: not the "decentralization" slogan but three concrete things — cross-party trust costs, automated contracting and settlement for high-frequency small transactions (smart contracts), and transparent, traceable benefit allocation.
- **Selection verdict**: chain type — **consortium chain** (external parties participate); consensus — **distributed-consistency algorithms** (PBFT/Paxos/Raft, prioritizing safety, reliability and capacity; PoW wastes compute; PoS/DPoS have centralization problems); scaling — **off-chain** (sidechains + multi-chain interconnection; off-chain relational stores over already-consensed data for efficiency); deployment — start on **BSN**, migrate to BaaS if needed; frameworks — Hyperledger Fabric (general) or FISCO BCOS (finance); nodes in three tiers — **full nodes (major participants) - relay nodes (substations/distribution rooms) - light nodes (each DER)**.
- **Five application areas**: ① the VPP itself (smart contracts put the whole source-load interaction chain — declaration, clearing, execution, compensation — on-chain; two-way selection, automatic contracting); ② demand response (main chain records offers/bids/contracts/instructions/responses; sub-chains connect IoT devices by distribution district; China Southern Grid issued the nation's first real-time DR electronic certificate at Songshan Lake, 2020-07); ③ ancillary services (trade notarization + off-registry + shared ledger bookkeeping; Qinghai's "State Grid Chain" shared storage — the nation's first blockchain-based shared-storage market); ④ distributed-generation trading / "over-the-fence" power sales (TransActive Grid was the world's first blockchain energy-trading market; four upgrades: trusted metering, intelligent control, democratic decision-making, multi-point maintenance); ⑤ electric vehicles (Germany's Innogy Share&Charge charging platform; Shanghai Jiading's first blockchain shared-charging pilot; battery lifecycle tracing in battery-swap scenarios).
- **Engineering iron rule**: "blockchain guarantees integrity, not truthfulness" — you need strict device admission, multi-party multi-dimensional cross-checking, "four-flow integration" (information/commerce/logistics/cash flows) for corroboration, and off-chain trusted institutions feeding prices to backstop data quality; governance off-chain is indispensable and requires regulators and legal safeguards; for security choose domestic platforms + Chinese national cryptographic algorithms with periodic security assessments (PBoC JR/T 0193-2020 assessment rules).

---

## 8. Business Models and Revenue Estimation

### 8.1 Revenue Structure (five sources)
1. **Demand-response subsidies** (mostly solicitation-based: peak-shaving/valley-filling subsidies; roughly CNY 0-5/kWh across localities; see the local table in Chapter 9);
2. **Spot peak-valley arbitrage** (market-based: track prices, optimize the internal portfolio; China's peak-valley arbitrage market is about CNY 3 billion → projected above CNY 40 billion by 2030, with about 82 GW of VPP-adjustable space — 2026-09 research figures);
3. **Ancillary services** (frequency regulation / reserve / peak regulation; storage frequency regulation has an effective regulation capability of about 2x its capacity);
4. **Capacity compensation / capacity payments** (as capacity-market mechanisms mature);
5. **Green power / green certificates and carbon-asset services** (certificate and emission-reduction revenue from aggregated clean generation).
- Head-VPP revenue-structure reference: spot + ancillary services near 60% of revenue; AI load-forecast accuracy 90%+ (2026-09 research figures); for storage aggregation, capacity-compensation revenue is 40%-60%.
- **An honest picture of profitability (2025-2026 disclosures)**: the industry is in a "scale first, profit later" stage — Hengshi Technology (~892 MW connected) concedes in its annual report that VPP revenue is still a small share and the period was loss-making; GCL Energy Technology has 835-855 MW of flexible load with VPP-related revenue only about 3%; Dongfang Electronics' "integrated energy & virtual power plant" segment gross margin is 38%, and head enterprises' 2025 VPP orders grew over 200% YoY (Cailian Press). When evaluating any VPP business plan, separate the "aggregation-scale narrative" from "booked revenue".

### 8.2 Commission and Revenue-Sharing Models (international evidence)
- **Germany's e2m**: charges a **25% commission on trading revenue**, 75% to the plant/load owners; grid-connection services, remote-control terminals and platform access are charged as fixed apportionments — **the VPP operator earns a commission, not a margin**.
- **Operator-to-resource 1:9 split** (common informal figure in China, 2026-09 research);
- Tesla's South Australia VPP: participating households' bills down about 20%; AGL saves up to USD 280 per year; Simply Energy pays USD 7 per day + USD 0.15/kWh feed-in.
- China's disclosed figures: DR contracts are mostly "floor + share" or fixed-price, but **no authoritative public industry-wide split ratio exists** (contract terms are not disclosed — demand contract evidence for any "20/80 or 30/70 split" claim); Shenzhen funds resource-aggregation platform investors at 10% of response revenue (up to CNY 2 million per company per year; measures valid to 2025-12-31); Shenzhen has a "demand-response insurance" whose premium is 3%-5% of expected revenue; no VPP revenue-rights ABS has landed (GCL's tokenized power-plant revenue rights (RWA) is an exploratory case; compliance structure and scale to be verified).

### 8.3 Peak-Load Economics (the strongest argument for VPP replacing coal peak-shaving)
- Nationally, the top 3%-5% of peak load accumulates to fewer than 50 hours per year; building generation and the grid to fully serve that peak is a huge waste;
- **SGCC's estimate**: to meet the top 5% of peak load in its service area — coal power (with matching grid) about **CNY 400 billion**, a VPP (build + operate + incentivize) only **CNY 40-57 billion** (book vintage; for order-of-magnitude argument);
- Meeting the peak with demand-side resources costs about 1/10 of the supply side, and is mostly smart-energy new-infrastructure investment.
- Latest official comparison (NEA, 2026-08): VPP construction cycles have shrunk from 3 years to 3 months, response speed from minutes to seconds, and unit-capacity investment is about 1/5 of pumped hydro (industry-comparison figures, partly promotional); the combined adjustment potential of commercial & industrial flexible load, EVs and distributed storage exceeds 300 GW (roughly 150 large pumped-hydro stations).

### 8.4 Estimation Framework (the standard move for "how much can it earn")
1. Clarify the resource inventory (type / capacity / response time / duration / retained load) → position by A-D classification;
2. Inventory the products and thresholds available in the province (spot / DR subsidy standards / ancillary access / capacity mechanism — see the local table in Chapter 9);
3. Revenue = Σ (adjustable capacity per product × annual called hours × clearing price / subsidy standard × revenue share); mind call-frequency limits (e.g. real-time response ≤3 times/day) and baseline determination rules;
4. Cost = communication and control equipment retrofit + platform access + O&M + opportunity cost (production impact on the user);
5. Sensitivities: narrowing peak-valley spread, rule revisions (see the PJM 2017 lesson), penalties for sub-par performance.
6. **Product-exclusivity check**: Zhejiang has made explicit that the same adjustment action may not simultaneously earn spot, ancillary-service and demand-response revenue — revenue models must encode product exclusivity; never count the same capacity in three markets.
7. **Per-kWh revenue reference ranges**: DR pilots average about CNY 0.27/kWh (China Energy News; original source to be verified), Shenzhen's 2025 average adjustment revenue about CNY 0.4/kWh (media figure, to be verified) — both are order-of-magnitude references only; neither the IEA nor the CEC has published a dedicated quantified report on Chinese VPP revenue; do not cite nonexistent "authoritative revenue conclusions".

### 8.5 New-Model Opportunities (2025-2026; policies and cases verified)
- **Direct green-power connection (绿电直连)**: NDRC Energy〔2025〕No. 650 (发改能源〔2025〕650号, 2025-05-30) established the model of "renewables supplying a single user via a direct-connection line without traversing the public grid"; **NDRC General Office Energy〔2026〕No. 688 (发改办能源〔2026〕688号, 2026-05) upgraded it to multi-user direct connection**, supporting accommodation-constrained projects in switching. By end-2025, 84 projects approved with 32.59 GW of renewables. Relation to VPP: source-load-storage coordination inside direct-connect parks, surplus-power export and shortfall support can all introduce VPP aggregation — an incremental market for aggregators.
- **Zero-carbon industrial parks**: NDRC Environment & Resources〔2025〕No. 910 (发改环资〔2025〕910号, 2025-06-30) launched creation; the first batch of 52 national-level parks was announced 2025-12-26, requiring "developing green direct connection and renewables' nearby integration into incremental distribution networks according to local conditions" — park-level aggregation is a natural VPP scenario.
- **Computing-power/electricity coordination (算电协同)**: national hub nodes require data centers to exceed 80% green power; Fujian pioneered data-center computing-load shifting into demand response; VNET's Huailai campus uses VPP aggregation of computing load and regional distributed generation for peak shaving and frequency regulation (a CAICT 2025 typical case of computing-power/electricity coordination).
- **Energy-carbon integration**: Jiangning Development Zone's "energy-carbon virtual power plant" (led by a Huadian affiliate; declared as China's first electricity-carbon integrated VPP platform); Shenzhen's energy-efficiency credit trading cut participants' average electricity cost by 7.2% — currently the "VPP + carbon inclusion" case closest to regulatory acceptance.
- **AI foundation models**: SGCC's "Bright Power" foundation model (released 2024-12, hundred-billion-parameter multimodal; integrated DeepSeek 2025-03); CSG's "Da Watt (大瓦特)" load forecasting has fully replaced legacy models at network and provincial levels with 97.8% day-ahead accuracy (company figure, not third-party audited); industry AI load-forecast accuracy generally 90%-94%; GCL reports AI lifting response speed 60%+ and cutting call costs about 35%.
- **Aggregated renewables entering the market**: after Document No. 136, distributed PV moved from fixed prices to the market, making aggregation the monetization channel — 3 VPPs in Anhui plus 18 generation aggregators in Jiangsu aggregated 1,868 distributed-PV stations (9.22 GW) into cross-province green-power trading (4.39 GWh transacted); Shanghai saw 21 VPP participations in surplus-renewables mutual-aid trading.

---

## 9. Chinese Policy and Local Practice (2024-2026; official figures verified)

### 9.1 The National Policy Chain
- **Document No. 357** (NDRC Energy〔2025〕No. 357 (发改能源〔2025〕357号), published 2025-04-11): positions the VPP as a "resource-aggregation new-type market entity" that can participate in medium/long-term, spot and ancillary-service markets as a whole (power purchase-and-resale requires a retail-license entity); targets adjustment capability above 20 GW by 2027 and above 50 GW by 2030; requires provinces to uniformly formulate construction-and-operation management measures (full process: construction, access, commissioning, testing, going live), categorized access to dispatch systems, incorporation into power-security management; encourages financial institutions to provide low-interest loans and credit guarantees.
- **Document No. 93** (NEA Legal & Reform〔2024〕No. 93 (国能发法改〔2024〕93号), 2024-11-28): new-type entities split into single-technology and resource-aggregation classes (VPP / load aggregators, smart microgrids); encourages entities with adjustment capacity of 5 MW or more to provide energy and ancillary services (provinces may lower the threshold, not add barriers); in principle exempt from the electric power business license; within one contract cycle an aggregated resource is in principle represented by only one aggregator; **the "grid-agency settlement" transition** — wholesale settlement data are the sum of metered data of aggregated resources, provisionally cleared and distributed to end users by grid enterprises, directly affecting operator cash-flow design.
- **The national-standard trio**: GB/T 44260-2024 *Technical Specification for VPP Resource Allocation and Assessment* and GB/T 44241-2024 *Specification for VPP Management* (effective 2025-02-01); GB/T 47241-2026 *Technical Guidelines for VPP* (led by China Southern Grid; effective 2026-09-01; the first national standard covering the full workflow; trade press reports thresholds of "10 MW aggregation capacity, 5 MW adjustment capacity" and "observable-measurable-adjustable-controllable" requirements — the standard text governs).
- **The 2026 framework**: the General Office of the State Council's *Implementation Opinions on Improving the Nationwide Unified Electricity Market System* (2026-02) explicitly promotes flexible market participation by VPPs, smart microgrids and flexible loads; the *15th Five-Year Plan for New-Type Power System Construction* (2026-08) reiterates 2030 targets of VPP maximum adjustment capability above 50 GW and V2G adjustable charging capacity of 50 GW.

### 9.2 Provincial Implementation (as of 2026-09: ~20 provinces with dedicated policies, 15 with market implementation rules)

| Province | Document | Key points |
|---|---|---|
| Shanxi | Jin Energy Regulation〔2025〕No. 4 (晋能源规〔2025〕4号) *Interim Measures for VPP Construction and Operation Management* (effective 2025-09-18, superseding the 2022 plan — the nation's first provincial scheme) | Three entity classes: load-type and DG-type (both submit quantity-price bids, 3-10 segment price curves) and integrated-type (priced like thermal units); aggregated-resource changes ≥3 months apart; spot clearing period 15 min→5 min from 2025 |
| Shandong | Lu Dev Energy〔2026〕No. 407 (鲁发改能源〔2026〕407号) *VPP Construction and Operation Management Measures* (effective 2026-08-01) | DG-type aggregation units ≥1 MW (may aggregate DG below 10(6) kV or under 10 MW installed); storage-type ≥1 MW with ≥2 h continuous charge/discharge; capability tested and certified by the dispatch agency + provincial VPP service center |
| Guangdong | GD Trading〔2025〕No. 152 (广东交易〔2025〕152号) *Detailed Rules for VPP Participation in Energy Trading (Trial)* (landed 2025-07; the nation's first provincial VPP market-participation policy came 2024-11) | Generation-type and load-type trading units; **default participation in demand-response trading** (a revenue floor); licensed retailers get simplified registration |
| Zhejiang | *VPP Operation Management Detailed Rules (Trial)* (2025-04) | Closed loop of registration/access — capability certification — operation management — trading — supply assurance — exit, plus dynamic rating; **the same adjustment action may not repeatedly earn spot / ancillary / DR revenue**; frequency regulation must sustain response ≥2 h |
| Jiangsu | *VPP Construction and Operation Work Plan* (2025-12) | Adjustment capability above 5 GW by 2030; first batch of 100 projects with total investment CNY 1.273 billion, aggregating 16.98 GW (up 2.75 GW / down 3.17 GW) |
| Shanghai | *User-Side VPP Construction Implementation Plan (2025-2027)* (2025-06-23) | Adjustable capability of 1.1 GW in 2025; complete operating-management and technical-standard systems |
| Others | Guangzhou (2 GW connected / 800 MW adjustable by end-2025; 4 / 1.2 GW by end-2026); Gansu (250 MW by 2027); Shenzhen (support measures valid to 2025-12-31) | Guangzhou allocates ≤CNY 20 million per year to subsidize V2G equipment investment and discharge volume |

### 9.3 National Scale Data (end-2025 official figures; disambiguate the metric before citing any capacity number)
- **Official totals**: 470 VPP projects built with a **measured maximum adjustment capability of 16.85 GW** (about +70% YoY; NEA article, 2026-08); the *2025 China Electricity Market Development Report* (2026-06): theoretical adjustment capability above 16 GW, V2G-aggregated resources above 19 GW, 84 green direct-connection projects approved (32.59 GW of renewables); 486 new-type entities registered with power-trading institutions.
- **The four capacity metrics** (media frequently conflate them):

| Metric | Definition | Example |
|---|---|---|
| Connected/aggregated capacity | Total capacity of resources ever connected to platforms (the largest number) | Shenzhen 5.1 GW; Southern Grid 17.94 GW |
| Declared adjustable capability | The maximum adjustment an operator declares to the platform | Shanghai 2.03→3.55 GW |
| Measured maximum adjustment | The largest call verified by testing (policy targets use this metric) | National 16.85 GW; Shanghai 1.65 GW |
| Real-time adjustable load | What is actually callable at a given moment | Shenzhen about 1.4 GW — **a real-time callability of only ~30% of connected capacity; the industry's pain point** |

  Caution: the media-circulated "national VPP above 35 GW" conflates connected capacity with adjustment capability; not recommended.
- **Provincial data**: Shanxi 2 GW+ (early 2025; settled energy 384 GWh; in 2025 sixteen VPPs aggregated 840 MW with maximum two-way adjustment of 2.25 GW, 6% of real-time load); Shandong 35 participants in the spot market with adjustment energy above 340 GWh; Zhejiang's first market-based response by new-type entities involved 19 VPPs, max 290 MW; Jiangsu's provincial platform has 58 operators, 72,000 adjustable resources and 3.8 GW total (750 MW real-time); Southern Grid aggregated 17.94 GW (2025-11); China Energy Investment runs 12 projects aggregating 8.157 GW with 839 MW adjustable (2026-06; the cleanest central-SOE dataset); Shanghai's "four jumps" 320→710→1,160→1,650 MW.
- **Book-era comparisons** (mechanism design still instructive): the Jibei FUN-power platform's phase 1 aggregated 11 categories / ~160 MW with maximum adjustment of 39.3 MW and revenue of about CNY 2.57 million to 2020-03 — the gap between aggregated capacity and actual adjustability remains an industry-wide issue; Hefei (100% of the bus fleet in a VPP); Suzhou Industrial Park (platform live 2025-12; aggregated 50 MW, 20 MW trialed, 94% accuracy, 120 MW target by 2027).

### 9.4 Demand-Response Subsidies and V2G (document numbers corrected)
- **V2G document chain (a high-frequency error)**: no national "2025 vehicle-grid interaction implementation opinion" exists — the correct chain: NDRC Energy〔2023〕No. 1721 (发改能源〔2023〕1721号, *Implementation Opinions on Strengthening Vehicle-Grid Interaction for New Energy Vehicles*) → NDRC General Office Energy〔2024〕No. 718 (推动车网互动规模化应用试点) → **NDRC General Office Energy〔2025〕No. 241 (发改办能源〔2025〕241号, *Notice Publishing the First Batch of Vehicle-Grid Interaction Scale-Up Pilots* — 9 pilot cities + 30 projects, publicized 2025-04-02)**; pilot thresholds: total discharge power ≥500 kW in principle, annual discharge ≥100 MWh (relaxable in western regions).
- **V2G data**: national V2G-aggregated resources above 19 GW (end-2025); Shenzhen's 2025-03 mega-scale test (760+ stations, 17,000 vehicle sessions, 88 MWh interacted), a single round discharging over 70 MWh in 2025-06; Guangzhou's pilot discharged over 1.6 GWh in its first year; Shanghai saw the first residential individual V2G discharge in 2025-05; Shanxi's rules: charging energy participates in the spot market as load-type, discharge energy for now participates "without quantity or price declaration".
- **DR subsidy landscape** (locally priced; verify province by province and check validity): peak-shaving invitations CNY 0-5/kWh, valley-filling CNY 0-1/kWh; real-time/near-real-time about CNY 2.5/kWh in many places (≤3 times/day, ≤3 h each); interruptible-load auction price cap CNY 15/kW; Jiangsu short-duration max CNY 4.8/kWh (real-time under 0.5 h: CNY 2.4/kWh + capacity CNY 10/kW); Guangzhou peak-shaving ≤CNY 3.5/kWh, reactive power ≤CNY 0.12/kvar·h; Shenzhen real-time precision response CNY 5/kWh (media reports a proposed rise to CNY 8/kWh, to be verified).

## 10. International Benchmarking (case library and institutional insight; 2025-2026 update)

### 10.1 United States (Order 2222 compliance timetable and scale targets)
- **FERC Order 2222 compliance status by ISO (as of 2026)**:

| ISO | Full implementation | Notes |
|---|---|---|
| CAISO | 2026-11-01 | first compliance filing approved 2023-05 |
| ISO-NE | by end-2026 | revision approved by FERC on 2025-12-15 |
| NYISO | 2026-12 | ancillary-services compliance filing submitted |
| PJM | DER aggregation joins the 2028/29 capacity auction (held 2026-06) | received up to 9 months' extension |
| MISO | mid-2029 | no multi-nodal aggregation allowed, effectively excluding residential VPPs; industry criticism |
| ERCOT | not subject to Order 2222 (no interstate transmission) | voluntary ADER pilot: 3 VPPs totalling 25.5 MW approved by 2026 (Tesla among the first cleared) |

- **Scale and economics targets**: DOE's *Pathways to Commercial Liftoff: VPPs* (updated 2025-04): expand to **80-160 GW** by 2030 (about 3x today, covering 10%-20% of US peak load and saving about USD 10 billion per year in grid costs); SEPA (2025Q3): North American behind-the-meter flexible capacity has reached **37.5 GW**, roughly halfway to the 80 GW 2030 target (re-verify before citing); Brattle: 60 GW of VPPs can save USD 15-35 billion over ten years, and a VPP's net cost of peak capacity is 40%-60% lower than alternative peak-shaving resources.
- **Company developments**: Tesla × Sunrun × Renew Home (announced mid-2026) to build a **16 GW** home-battery + smart-thermostat VPP — billed as the largest distributed power plant in the US, targeting data-center supply (note: an announced plan, not yet built); Sunrun dispatched nearly 18 GWh in 2025 with 429 MW peak output and 107,000+ registered users; **OhmConnect shut down (2026) after ten years of operation** — the emblematic failure of a subsidy-dependent residential model; the Texas model = wholesale direct access + standard aggregator contracts (the core recommendation of the DOE Liftoff update); Tesla VPP users share about USD 400 per year (company figure) to USD 750 (individual claim, to be verified).

### 10.2 Europe (the FNA doubling of flexibility needs = the official quantification of commercial space)
- **EU level**: the 2024 electricity-market-design reform introduced mandatory national flexibility-need assessments (FNA) with an ACER-approved harmonized methodology; **ENTSO-E assessment: flexibility needs related to wind-solar variability double from 2025 to 2033**; the Grid Action Plan (2023) evolved into the Grids Package.
- **UK DFS (Demand Flexibility Service)**: winter 2024/25 saw 1.98 million households/businesses registered, 44 events shifting/shedding 3.9 GWh, about £1.22 million traded; year-round routine operation from 2025 and "Turn Up" valley-filling events added from 2026.
- **Germany**: aFRR capacity is auctioned daily and jointly (about 2 GW, 4-hour blocks, pay-as-bid); energy is activated Europe-wide in 15 minutes via PICASSO; price signals: 2024 up/down capacity averages about 13/10 €/MW/h → 2025 noon down-regulation average 48.4 €/MW/h with an extreme single clearing at 3,784 €/MW/h; BNetzA (BK6-25-212) consulted on 15-minute products; **saturation warning** — TSOs have already procured about 4.5 GW of battery-type balancing services, so a UK-style saturation price squeeze may recur. Next Kraftwerke now aggregates about 14 GW+ (9 GW / 12,000 units in 2021 → 14-15.5 GW in 2024/25; the 15.5 GW figure is single-sourced); e2m has over 3,700 MW of bundled capacity, and on 2020-04-14, when Germany's secondary-reserve market swung abruptly (a 2 GW deficit turned into a near-3 GW surplus), it deployed 1,200+ distributed assets to backfill.
- **Japan**: METI's *Energy Resource Aggregation Business (ERAB) Guidelines* established the negawatt trading framework; Yano Research projects the ERAB market at JPY 73.5 billion by FY2035; in late 2025 METI proposed lowering the balancing-market price cap (a major impact on BESS/VPP revenue strategies).

### 10.3 Australia (a government-led residential VPP "target vs reality" counter-example)
- **The SA VPP changed hands**: in 2025-07 **AGL acquired 100% of the SA VPP from Tesla** (launching AGL Community Power); actual scale: 7,000+ Powerwalls, 8,000+ registered members, about **35-50 MW** — far below the 2018 target of "250 MW / 650 MWh / 50,000 households"; Tesla Energy Plan (Australian retail) exited customers by 2025-09-30. Lesson: for government-led residential VPPs, aggregation cost, customer acquisition and retention are far harder than planned.
- **The institutional legacy still stands**: 2016-11 opened ancillary services to non-generation market participants → 2017 defined ownership/use rights of user-side resources → **2017-11 settlement cut from 30 min to 5 min** (favoring fast-response resources); AEMO's VPP Demonstrations ended in 2021/22 (31 MW registered at the endpoint, 184 MW across six FCAS markets in total) and turned to holistic DER planning; the lessons of FCAS under-response (83%, 828 kW vs a 1 MW bid) and daily remote configuration checks still apply; Tesla's platform architecture (layered aggregation, digital twins, graceful degradation to local optimization under communication loss) remains the industry benchmark.

## 11. Risks and Operational Practice

### 11.1 Six Difficulties (from the book's afterword; a risk checklist for proposals)
1. **Policy compliance**: energy transition and market rules evolve constantly; business models, products and technical systems must be updated continuously;
2. **Heterogeneity**: hundreds or thousands of heterogeneous generation-storage-load units + wildly differing user habits + spatiotemporal and priority constraints strain real-time communication and dispatch optimization;
3. **Trust and data**: users becoming prosumers create new requirements for trust mechanisms, privacy security, traceability, quality control and trade certification;
4. **Amplified uncertainty**: the higher the wind-solar share, the greater the volatility + load-side uncertainty → failure to deliver contracted ancillary services brings punitive penalties or even market exclusion;
5. **Forecasting is the lifeline**: load forecasts vary widely with socioeconomics and climate; "one model for all users" limits reliability inference — model separately by region and user group (the VPP's bottom-up mode itself reduces utilities' forecast risk);
6. **Segmented design**: segment user groups by distribution-network association, and design VPPs separately with different price models / DR / distributed solutions, forecasting each separately.

### 11.2 Operational Practice Essentials
- **The baseline (CBL) is the core of settlement disputes**: the mainstream is the similar-day average method — the last 5 same-type days, excluding anomalous days whose daily energy deviates about ±25%, times a correction factor; Zhejiang certifies a valid response when both maximum and average load fall below baseline and the response rate ≥50%.
- **Aggregation ≠ reliability**: Tesla's FCAS under-response incident (83%) warns that drift in individual device configurations erodes aggregated capacity; build mechanisms for **daily, remote configuration checks + telemetry-timeout removal + conservative bidding**.
- **Customer relations**: DR earnings are small relative to total electricity cost and disrupt production and life → customers must retain final decision rights (veto); pre-set ownership of control equipment on supplier switching in contracts; keep remuneration structures simple and transparent.
- **Single-product dependence is the source of fragility**: the PJM 2017 rule-revision lesson → stack multiple revenue streams (DR + spot arbitrage + frequency regulation + capacity + green/carbon).
- **Capability-building checklist**: resource assessment (A-D classification) → platform and communications (5G / edge computing) → four forecasts (load / output / price / flexibility) → bidding and optimization (fitted to the market's settlement cycle) → baseline and settlement management → compliance and security (the "Two Rules" assessments, MLPS (等保), data authenticity).

---

## 12. Key Formulas and Figures Quick Reference

| Item | Value / formula | Notes |
|---|---|---|
| Market-stability criterion | Largest generator's share ≤ demand-side price elasticity | California crisis lesson; raising demand elasticity ≡ lowering concentration |
| Peak-load character | The top 3%-5% of peaks accumulate ≤50 h/year | The economic basis for demand-side replacing supply-side |
| Coal vs VPP investment | about CNY 400 billion vs CNY 40-57 billion (SGCC figure, meeting the top 5% of peak) | Order-of-magnitude argument (book vintage) |
| Document No. 357 targets | 20 GW by 2027, 50 GW by 2030 adjustment capability | NDRC Energy〔2025〕No. 357 |
| HVAC adjustability | flexible building HVAC sheds ~25% short-term; HVAC is 30%-40%+ of summer peak | Shanghai / most cities |
| Sector adjustable shares | steel 20% / cement 24% / aluminum 22% / buildings 30% / residential 50% | SGCC 2019; policy & tech in place + voluntary |
| Wind forecast error | 24h forecast MAE ≈ 5%-15% of installed capacity | Depends on climate and geographic spread |
| Storage frequency-regulation capability | effective regulation ≈ 2x own capacity | Bidirectional, millisecond-to-hundred-millisecond |
| Efficiency: pumped hydro / Li-ion | pumped hydro 70%-75%; Li-ion 85%-98%; compressed air 50%-70% | Inputs for arbitrage estimates |
| German balancing rules | weekly→daily auctions; 2×12 h→6×4 h blocks; access <5 MW | 2018-07; anti-arbitrage single price unit |
| Australia settlement | 30 min→5 min (2017-11) | Fair compensation for fast-response resources |
| FERC Order 2222 | DER aggregation minimum ≤100 kW; CAISO compliant 2023-05 | Compare with Chinese provincial thresholds of 1-5 MW |
| Next Kraftwerke | 9,516 units / 8,179 MW / 15.1 TWh (2020-06); now above 10 GW | About four nuclear plants |
| e2m commission model | 25% of trading revenue to the operator, 75% to resource owners | Fixed apportionment fees for added services |
| Tesla South Australia | planned 250 MW; household bills down ~20%; FCAS under-response 83% | Layered aggregation + daily configuration checks |
| Jibei phase 1 | 11 categories / 19 partners / ~160 MW; max adjustment 39.3 MW; revenue ~CNY 2.57 million (to 2020-03) | China's first market-based VPP |
| CBL baseline | similar-day average (last 5 same-type days, exclude ±25% deviations) × correction factor | The core of DR/VPP settlement disputes |
| DR subsidy ranges | shaving CNY 0-5/kWh, filling CNY 0-1/kWh, real-time ~CNY 2.5/kWh | 2026-09 research; verify province by province |
| National VPP official figures | 470 projects / measured max adjustment 16.85 GW (end-2025, NEA) | Disambiguate the four capacity metrics first (see 9.3) |
| Document No. 93 access | encourages ≥5 MW adjustment capacity; grid-agency settlement transition | NEA Legal & Reform〔2024〕No. 93 (2024-11-28) |
| VPP national standards | GB/T 44260/44241-2024 (2025-02); GB/T 47241-2026 (2026-09-01) | Full-workflow technical guidelines |
| Order 2222 landing | CAISO 2026-11, NYISO 2026-12, PJM 2028/29 BRA, MISO 2029, ERCOT exempt (ADER 25.5 MW) | As of 2026-09 |
| US VPP targets | DOE: 80-160 GW by 2030; SEPA: ~37.5 GW now (halfway) | 2025 figures |
| UK DFS | 1.98M households / 44 events / 3.9 GWh (winter 2024/25) | Year-round from 2025 |
| SA VPP counter-example | actual 35-50 MW vs 250 MW target (handed to AGL 2025-07) | Government-led residential VPP missed its target |
| Green direct connection / zero-carbon parks | No. 650 → No. 688 (multi-user); No. 910 first batch of 52 parks | The 2025-2026 policy trio |

---

## 13. Glossary (selected, Chinese-English)

| Term | Chinese | One-line explanation |
|---|---|---|
| VPP (Virtual Power Plant) | 虚拟电厂 | A smart energy system aggregating dispersed resources to participate in system operation and markets as a whole |
| DSM (Demand Side Management) | 需求侧管理 | Treats demand-side savings as a resource; least-cost integrated planning |
| DR (Demand Response) | 需求响应 | Users voluntarily adjust consumption to price/incentive signals |
| Aggregator | 资源聚合商 | The core entity aggregating DER and entering dispatch/markets on their behalf |
| CVPP / TVPP | 商业型/技术型 VPP | Oriented to maximizing market revenue / to system-operation services |
| CSP (Curtailment Service Provider) | 削减服务提供商 | A third party aggregating "negawatts" into wholesale DR under PJM |
| LSE (Load Serving Entity) | 负荷服务实体 | Pools load resources to join DR and keeps supply |
| SC (Scheduling Coordinator) | 计划协调机构 | California's ex-ante supply-demand coordinator |
| CBL (Customer Baseline Load) | 基线负荷 | The counterfactual "no-response" load; the DR settlement benchmark |
| Negawatt | 负瓦 | Load shed traded as "virtual electricity" |
| Reverse power flow | 逆向潮流 | Resources feeding power back to the grid; VPP can, DR cannot |
| Positive/Negative plant | 正电厂/负电厂 | The VPP's dual identity: peak-shaving supply / valley-filling consumption |
| Smart/Ordered charging | 有序充电 | The main near/mid-term form of EV participation (distinct from V2G) |
| V2G (Vehicle-to-Grid) | 车网互动 | EVs discharge reversely to participate in adjustment |
| UEIOT (Ubiquitous Electric IoT) | 泛在电力物联网 | The technical base of the Jibei FUN-power platform; everything connected + smart aggregation |
| Edge computing | 边缘计算 | Distributed intelligent agents deciding locally (the VPP's "edge-cloud" collaboration) |
| Smart contract | 智能合约 | An on-chain program that executes automatically on conditions (automated DR contracting & settlement) |
| uRLLC (ultra-reliable low-latency communication) | 高可靠低时延通信 | A 5G scenario with 1 ms latency; the key VPP enabler |
| Consortium blockchain | 联盟链 | Co-governed by multiple institutions with identity checks — the preferred chain type for VPP |
| Distributed-consistency algorithms | 分布式一致性算法 | PBFT/Paxos/Raft; the preferred VPP blockchain consensus (safety, reliability and capacity first) |
| Prosumer | 产消者 | A user who both consumes and produces power (the user form of the VPP era) |
| EEP (Energy Efficiency Plant) | 能效电厂 | Treats saved energy as an equivalent plant (contrast with VPP) |

---

## 14. Expert Q&A Reasoning Handbook

### 14.1 Question Typing and Answer Paths
1. **Concept-distinction questions** ("How is a VPP different from a microgrid / retailer / DR?"): give the criteria table (1.2) → apply the three rulers of "reverse power flow / physical vs logical aggregation / market coupling" → land a one-liner.
2. **Stage-judgment questions** ("What stage is our province / our project at?"): use the Chapter 4 criteria — is the revenue source a subsidy or market prices? Does it submit quantity-price bids into the market? Does it dispatch across space? → give the stage + the transition conditions (market construction + communication capability).
3. **Implementation-path questions** ("Where do we start building a VPP?"): resource inventory (A-D classification) → verify provincial policies and products (the Chapter 9 table) → access and platform integration (load-management system vs dispatch automation system) → a minimal pilot loop (run CBL settlement through one product) → stack products gradually.
4. **Estimation questions** ("How much can 10,000 kW of HVAC load earn?"): first ask the province and response type → apply the 8.4 framework: adjustable capacity × called hours × subsidy/clearing price × share, minus retrofit and O&M → give sensitivities and risks (call-frequency limits, baseline determination, penalties).
5. **Technology-selection questions** ("Which communication tech? Do we need blockchain?"): derive requirements backward from the market rules' response times and settlement cycles (e.g. 15-min settlement → instructions every 15 min) → communications by scenario (NB-IoT/LoRa/5G) → adopt blockchain only when all three conditions hold (multi-party trust, small high-frequency transactions, allocation sensitivity); use the 7.2 verdict for selection.
6. **Policy-interpretation questions** ("Opportunities in Document No. 357?"): positioning (new-type entity) → targets (2027/2030) → rule essentials (no double aggregation, two system accesses) → the respective opportunities for aggregators / users / equipment vendors → remind about provincial-rule differences and verification entry points.

### 14.2 Common Misconceptions (correct proactively)
1. Equating VPP with "a demand-response platform" — DR is only a subset; VPP also aggregates distributed generation and storage and can feed power reversely;
2. Equating VPP with a microgrid — a VPP changes no physical architecture, spans space, and runs grid-connected only;
3. Believing a market-based VPP is possible without a market — without price signals there is no market-based VPP, only solicitation-based;
4. Promoting VPP capability with "installed capacity" — distinguish **aggregated capacity** (nominal) from **adjustable capacity** (actually responsive; e.g. Jibei: 160 MW aggregated vs 39.3 MW max adjustment);
5. Ignoring CBL baseline rules — response-revenue certification depends heavily on the baseline algorithm and exclusion rules; master them before signing;
6. Believing "the more aggregated, the more profitable" — heterogeneous resources add dispatch complexity and default risk; prioritize A-class resources under the A-D classification;
7. Treating blockchain as mandatory for VPP — not advisable unless the three conditions (multi-party trust, small high-frequency transactions, allocation sensitivity) all hold;
8. Ignoring rule-change risk — the PJM 2017 lesson: a single-product revenue model can fail within a year;
9. Treating "aggregation ≠ reliability" as a rare event — Tesla's 83% under-response shows configuration drift erodes capacity systematically; daily remote checks are mandatory;
10. Mixing book-vintage data with current data — the book is 2018-2020; for scale and policy, the research figures in Chapters 9-10 govern.
11. **Conflating capacity metrics (the most frequent post-2025 error)** — presenting "connected/aggregated capacity" (Shenzhen 5.1 GW, Southern Grid 17.94 GW) as "measured adjustment capability" (national 16.85 GW), or citing the media's "35 GW"; always declare the metric first when answering scale questions (see the four-metric table in 9.3).
12. Treating Shenzhen's "CNY 5/kWh" as a national standard — DR subsidies are locally priced with validity windows (Shenzhen's measures run to 2025-12-31); nationally, V2G has only pilot notices (Document No. 241, 9 cities and 30 projects); no "2025 vehicle-grid interaction implementation opinion" exists.
13. Citing nonexistent "authoritative revenue conclusions" — neither the IEA nor the CEC has published a dedicated quantified report on Chinese VPP revenue; the per-kWh ranges (CNY 0.27-0.4/kWh) are pilot and media figures and must carry attribution.

### 14.3 Data-Currency Discipline
- The book's knowledge vintage: 2018-2020 (China Machine Press, 2020); OCR corrections were cross-checked against context; anything still doubtful is flagged in the original;
- The web-research vintage: 2026-09-12 (Document No. 357, provincial rules, V2G pilots, peak-valley arbitrage market size, etc.);
- High-frequency verification entry points: NDRC / NEA official websites, provincial DRCs & energy bureaus and power-trading centers, the Shenzhen VPP Management Center, the new-type power load management system, and open-source tools on GitHub (PyPSA / pandapower / Grid2Op / Carbon Aware SDK — see the sister skill's Chapter 15).

---

## 15. Knowledge Sources and Maintenance

### 15.1 Book Sources
- *Approaching Virtual Power Plants* (走近虚拟电厂), edited by Wang Peng, Wang Dongrong et al., China Machine Press 2020 — the backbone of this skill (concepts / resources / three stages / control & optimization / market entities / 5G / blockchain / afterword framework);
- The knowledge base of the sister skill *Electricity Trading Expert* applies equally to this skill's market-mechanics parts (spot / ancillary services / settlement / carbon markets): see its Chapter 15 for the six-book list.

### 15.2 Policy and Market Research (2025-2026)
- The 2025-2026 incremental research (2026-09-12; per-item URLs with verified/to-be-verified flags in the repo files `knowledge/调研-VPP政策与市场-2026-09增量.md` and `knowledge/调研-VPP商业模式与国际-2026-09增量.md`): the original text and rollout map of Document No. 357 (~20 provinces with dedicated policies / 15 with implementation rules), Document No. 93, the national-standard trio, the national 470 projects / 16.85 GW, green direct connection (Documents 650/688), zero-carbon parks (Document 910), V2G pilots (Document 241), the per-ISO Order 2222 compliance table, DOE's 80-160 GW target, ENTSO-E's doubling flexibility needs, the SA VPP handover to AGL, quantified AI-model data, etc.
- Earlier research (2026-09-12): DR subsidy landscape, V2G pilot cities, peak-valley arbitrage market size — see the research notes under the repo's `knowledge/` directory.

### 15.3 Known Limitations
- The book's data are as of 2018-2020; industry scale, subsidy standards and access thresholds change fast — defer to the Chapter 9 research figures and the latest official documents;
- Where OCR damaged individual digits, "about / on the order of" or (to be verified) is used; re-verify before quoting important numbers;
- Provincial implementation rules after Document No. 357 are still updating rapidly; this skill does not replace real-time policy search.
