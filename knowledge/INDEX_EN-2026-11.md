# English Knowledge Index and Digest (2026-11-01)

> **Purpose**: an English entry point to this repository's knowledge layer. The full notes are written in Chinese; this file gives (1) a map of what each note contains, (2) the key figures most likely to be asked, (3) a condensed provincial table, and (4) the open items that must be flagged when answering.
> **Data cutoff**: 2026-11-01. Policy figures change monthly; re-check before quoting. Source grades: **A** official documents/statistics, **B** exchanges, central SOEs and industry associations, **C** media/research reports, **D** calculations from public data.
> **Rule of thumb**: a number needs grade + time point + caliber. If any of the three is missing, mark it "to be verified".

---

## 1. Knowledge map

| File | Type | What it is / when to use it |
|---|---|---|
| `电力现货市场101问-A-基础与价格机制.md` | Book note | Spot-market basics: pricing, LMP, supply-demand and market power |
| `电力现货市场101问-B-出清结算与省域实践.md` | Book note | Clearing, settlement, provincial practice |
| `电力现货市场101问-C-结算TTS与政策演进.md` | Book note | Settlement mechanisms, TTS, policy evolution |
| `电力系统经济学原理-主题笔记.md` | Book note | Power-system economics: marginal cost, congestion, investment |
| `电力现货市场实务-精读笔记.md` | Book note | Operational practice of China's spot markets |
| `中国碳排放权交易实务-主题笔记.md` | Book note | China ETS mechanics (written ~2016; mechanisms valid, figures need updating) |
| `碳管理-从零通往碳中和-主题笔记.md` | Book note | Corporate carbon management, Scope 1/2/3, abatement cost |
| `走近虚拟电厂-主题笔记.md` | Book note | VPP concepts, control, business models (book published 2020; data 2018-2020) |
| `电力系统通识-A-格局与主体.md` | Primer | Industry landscape: State Grid / CSG / Inner Mongolia West, five majors and the "four smalls", equipment vendors, research bodies, trading-dispatch-regulation split, five common misconceptions |
| `电力系统通识-B-发输配变用.md` | Primer | Fundamentals for non-specialists: power vs. energy, voltage levels, frequency and reserve, three stability classes, protection and dispatch automation, losses, flexibility of seven generation types, unit conversions |
| `电力系统通识-C-改革史.md` | Primer | Reform history 1985-2026 in eight stages, each with problem / measure / impact / legacy; three threads (price, actors, institutions) and five misconceptions |
| `电力系统通识-D-新角色与现货市场.md` | Primer | Spot markets and system operation, high-renewables technical issues, storage (grid-following vs. grid-forming), VPPs, V2G, green direct connection, system costs and who bears them |
| `调研-电力市场政策与开源资源-2026-09.md` | Research note | 2026-09 policy and open-source tooling |
| `调研-虚拟电厂与碳市场-2026-09.md` | Research note | 2026-09 VPP and carbon-market findings |
| `调研-速查合并-2026-09.md` | Research note | 2026-09 merged quick-reference |
| `调研-VPP政策与市场-2026-09增量.md` | Research note | Provincial VPP policies, national scale, V2G, pilots |
| `调研-VPP商业模式与国际-2026-09增量.md` | Research note | VPP revenue models, company data, international cases |
| `调研-电力市场2026-10增量.md` | Research note | October 2026 electricity-market updates and correction list |
| `调研-碳市场与CBAM-2026-10增量.md` | Research note | October 2026 carbon market and CBAM updates |
| `碳资产实务-2026-11.md` | Practice note | Compliance parameters, CCER, carbon-finance instrument status, CBAM dates, PCF / neutrality / DPP facts and open items; maintenance entry for the carbon asset skill |
| `储能投资与运营-2026-11.md` | Practice note | Doc. 114 capacity price and provincial samples, Doc. 1656 TOU reconstruction, Doc. 411 ancillary products, Docs 1583/500 demand rules, 2026 tender cost ranges, GB/T 36549 KPIs and 2026 H1 operating data; maintenance entry for the storage investment skill |
| `新能源项目开发与并网-2026-11.md` | Practice note | Four project types and eight development stages, Doc. 136 settlement and 2026-2027 provincial auctions, resource/P50-P90/capture-rate calibres, LCOE and after-tax break-even examples, grid standards (GB/T 19963.1, GB/T 19964, GB 38755, GB/T 40595, GB/T 36547), regional risk profiles and open items; maintenance entry for the renewable development skill |
| `中国电价史-2026-11.md` | History note | China's electricity prices in five stages (1949-1985, 1985-2002, 2002-2015, 2015-2021, 2021-2026), each with who sets prices, price form, cost recovery and legacy; three main threads plus cross-subsidy; six misconceptions |
| `中国电价制度谱系-2026-11.md` | Handbook | Three segments (generation / network / retail) and nine price types; permitted-revenue formula; capacity, ancillary and environmental prices; line loss, system operation fee and government funds; two-part tariff and the 105% demand rule; synthetic bill, ten calibres and nine common errors |
| `中国电价现行政策与查证-2026-11.md` | Status table | 14-document table (742/1583/500/1093/1439/809/1047/1217/1501/136/411/1656/114, State Council Doc. 4); four 2026 threads; four-step user lookup; provincial samples; 2026-2027 open items |
| `国际电价比较-方法与模板-2026-11.md` | Method note | Why direct comparison fails; five harmonisation steps; six-row component decomposition mapped to China / EU / US; country-card YAML template; synthetic A/B example where nominal ranking flips under PPP; data sources and expansion roadmap |
| `调研-碳管理与碳足迹厂商-2026-11.md` | Research note | Carbon Newture service matrix, dated public cases, borrowable methods, claims that must not be used as benchmarks |
| `调研-VPP政策2026-10增量.md` | Research note | October 2026 VPP policy, scale calibers and business models |
| `省级市场状态表-2026-11.md` | Status table | One row per province: spot / No. 136 auction / capacity price / VPP / ancillary / retail risk |
| `索引与口径-2026-11.md` | Handbook | Document-number index, caliber dictionary, source grading, watchlist |
| `微网EMS优化调度-算法与工程-2026-11.md` | Algorithm note | Microgrid EMS day-ahead MILP: objective terms, constraints, SOC efficiency, SOS1 vs Big-M, demand-charge linearization, solver parameters and fallbacks, dual-timescale rolling, input data contract, interface boundary with storage EMS, quantified demand/degradation add-on, uncertainty roadmap, assessment loop, review checklist; source material for the planned EMS module |
| `储能EMS优化调度-算法与工程-2026-11.md` | Algorithm note | Storage EMS MILP: multi-market stacking (energy, frequency regulation, reserve, ramping, capacity), SOC/efficiency recursion, four reserve dimensions, frequency-regulation energy neutrality and SOC recovery, two-part tariff and the 105% demand threshold, capacity-payment eligibility and duration scaling, three degradation tiers, cluster-level dispatch and SOC balancing, KPI calibers per GB/T 36549-2018, AGC/AVC, safety interlocks, input data contract, solver fallbacks, three worked examples and acceptance tests; source material for the planned EMS module |
| `黄金问答集-2026-11.md` | Q&A | 28 high-frequency questions with answer points and common errors; regression checklist |

---

## 2. Key figures (grade + time point + caliber)

### Electricity market

| Metric | Value | Grade / note |
|---|---|---|
| National market-traded electricity, 2025 | **6.64 trillion kWh** (+7.4%, ~64.0% of total consumption) | A |
| Medium/long-term contract turnover, 2025 | **6.3522 trillion kWh** (incl. 328.5 billion kWh green power) | A; 4.81 trillion is a narrower subset, not the total |
| Green-power trading, 2025 / Jan-Sep 2026 | **328.5 billion kWh** (+38.3%) / **249.2 billion kWh** (+6.1%) | A |
| Market-traded electricity, Jan-Sep 2026 | **5.8536 trillion kWh** (+18.9%) | A |
| Spot markets in formal operation | **At least 11 provincial markets by 2026-09-30**, plus the southern regional market on **2026-10-24** | A/B; do not say "the 10th/11th" — sources conflict |
| Coal capacity price | Fixed cost **CNY 330/kW·yr**; recovery **≥50% from 2026** (floor 165). 2026 values: Guangdong 165; Tianjin/Sichuan 231; Qinghai 185; Guangxi 247.5; Jilin/Heilongjiang/Hunan/Gansu/Yunnan 330; Henan 330 draft; **Liaoning 370 is reliable-capacity compensation, a different caliber** | B/C for provincial values |
| System operation fee, Q1-Q3 2026 | About **CNY 0.068/kWh**, roughly +93% YoY | B/D |
| PJM capacity price | **USD 329.17/MW-day for 2027/28**; USD 325/MW-day for 2028/29 (cleared 2026-07-14) | A (PJM) |

### Electricity prices (2026-11)

| Metric | Value | Grade / note |
|---|---|---|
| Retail price components | Energy + transmission/distribution + system operation fee + government funds and surcharges + taxes; basic charge added for two-part-tariff users | A; components vary by province and user category |
| Network permitted revenue | Permitted cost + reasonable return + taxes; reasonable return = effective assets × permitted return rate | A (Doc. 742 framework) |
| Contract maximum demand | Actual demand up to 105% of the agreed value is billed at the agreed value; the excess is charged at double; agreed value floor is 40% of transformer plus high-voltage motor capacity | A (Docs 1583/500) |
| TOU reconstruction, 2026 | Doc. 1656 removes administratively fixed TOU levels and periods for direct market participants; Zhejiang spread 0.83→0.50 CNY/kWh (−28.5%), Jiangsu 0.85→0.65 (−25%) | B for Zhejiang; C for Jiangsu |
| Synthetic bill | 200 MWh at 10 kV: energy 0.42 + network 0.15 + system 0.068 + funds 0.02, basic charge CNY 40,000 → **CNY 171,600, 0.858 CNY/kWh** | D; synthetic example, not a provincial tariff |

### No. 136 mechanism prices (2026-2027 incremental auctions)

| Province | Range | Volume / note |
|---|---|---|
| Zhejiang | First auction CNY 381.6/MWh; second 0.242-0.393/kWh | First 4.2896 billion kWh; second 13.325 billion kWh |
| Hunan | 0.23-0.35/kWh | 2.286 billion kWh |
| Fujian | 0.16-0.39/kWh | 8.36 billion kWh |
| Guangdong | 0.20-0.40/kWh | 7.934 billion kWh |
| Beijing | Cap 0.3598/kWh | 850 million kWh |
| Tianjin | Cap 0.32/kWh | 4 billion kWh |
| Jiangxi | 0.24-0.379/kWh | 4.08 billion kWh |
| Liaoning | 0.18-0.30/kWh | 5.308 billion kWh (wind 3.956 / solar 1.352), clears 2026-11-08 |
| Guangxi | 0.15-0.36/kWh | Single project ≤80%, wind and solar auctioned separately |
| Gansu | 2027 H1 solar 0.2447 / wind 0.2440/kWh | Cleared near the floor |

- **Discipline**: always ask province + year + batch (existing/incremental, first/second auction). Zhejiang's 381.6/MWh is not a national average.

### Renewable project development (2026-11)

| Metric | Value | Grade / note |
|---|---|---|
| Resource calibres | P50 as base, P90 for financing; `P90 = P50 × (1 − 1.2816 × CV)`; example P50 2,400 h, CV 8% → **P90 2,153.93 h** | D; normal approximation |
| Capacity factors | Wind 2,400 h → **27.40%**; PV 1,400 h → **15.98%**; Weibull screening (7.0 m/s, k=2, 97% availability) → **27.92%** | D; screening model |
| PV specific yield | 1,650 kWh/m² plane-of-array, PR 0.82, 4% bifacial gain → **1,407.12 kWh/kWp** | D |
| LCOE, three examples | Onshore wind **252.80**, utility PV **283.94**, offshore wind **446.43** CNY/MWh | D; pre-tax, 8% discount |
| Mechanism settlement, Example A | 232,800 MWh, 70% coverage, mechanism 0.30, market 0.25, certificate CNY 6 → total **CNY 67.7448 million**; effective price **0.285**, all-in **0.291** CNY/kWh | D |
| Capture prices | Wind 92% capture → **0.279**; PV 85% → **0.274** CNY/kWh effective (70% mechanism + 30% market) | D |
| Break-even mechanism price | Pre-tax **245.43** CNY/MWh (LCOE-based); after-tax **294.85** at an 8% hurdle, 266.95 at 7%, 239.94 at 6% | D; LCOE is not the bid floor |
| Investment metrics, Example A | NPV **CNY 5.963 million**, IRR **8.18%**, payback **9.55 years**, DSCR **1.76** | D; 25% tax, 20-year depreciation |
| Downside cases | Mechanism 0.244 → NPV **−CNY 58.931 million**, IRR **6.15%**; combined P90 + CAPEX +10% + capture 90% → NPV **−CNY 94.0485 million**, IRR **5.28%** | D |
| Grid standards | GB/T 19963.1-2021, GB/T 19964-2024, GB 38755-2019, GB/T 40595-2021, GB/T 36547-2024 | A; editions per current standard text |

### Nuclear market entry (2026, level C)

| Province | Arrangement |
|---|---|
| Liaoning | Mechanism from 2026-03: 80% of on-grid energy in the 21-hour daily window is settled at the approved tariff (Hongyanhe units 1-4 CNY 0.3823/kWh; units 5-6 CNY 0.3749/kWh; average 0.3798), difference settled by the grid and shared by commercial/industrial users |
| Guangxi | CfD mechanism applied to nuclear from 2026-01 |
| Guangdong | Variable-cost compensation removed in 2026; nuclear competes directly in the market |

### VPP

| Metric | Value | Grade / note |
|---|---|---|
| Official national fleet, end-2025 | **470 projects**, **16.85 GW** measured maximum adjustment capability (+~70% YoY) | A (NEA, 2026-08) |
| Media/industry figure, 2026-06 | **120 GW aggregated, 800+ projects** | C; connected/aggregated capacity, not measured capability |
| Four capacity metrics | Connected/aggregated > declared > measured > real-time adjustable | Declare the metric before answering |
| National target | 20 GW by 2027, 50 GW by 2030 | A (Doc. 357) |
| Zhejiang response record | 50 operators / 2,542 users, **3.5952 GW** maximum response during the 2026 National Day holiday | C |
| Shenzhen platform, 2026-07 | 61 operators, 4.75 GW connected, 1.3 GW maximum adjustable (~5.4% of peak load) | C |
| Shenzhen funding measure | Valid to **2025-12-31**, expired; no 2026 replacement found | A (expiry) |

### Carbon and CBAM

| Metric | Value | Grade / note |
|---|---|---|
| China ETS coverage | **3,680 entities**, ~**8.3 billion tCO2**, 65%+ of national emissions | A |
| CEA price | **CNY 97.90/t** end-2026-08; **CNY 94.94/t** on 2026-10-08; 2026 Jan-Aug average 83.86 | A/B |
| CBAM certificate reference price | ~**EUR 75.36/t** (2026 Q1), **75.28/t** (2026 Q2) | A |
| CBAM timeline | Definitively applies from 2026-01-01; **certificate purchases start 2027-02**, first surrender 2027-09-30 | A; "applies in 2026" is not "buy certificates in 2026" |
| GEC price by vintage | 2024 / 2025 / 2026: **CNY 0.56 / 1.60 / 6.16 per certificate** | B/C; ~11x vintage spread |
| CCER offset cap | **5%** of the surrender obligation | A |
| CCER registered projects | **44 projects** by mid-October 2026; average price ~**CNY 86.51/t** | B; above CEA at the time |
| 2025 compliance rate | **99.99%** | B; 2023 was 99.98% |
| Under-surrender penalty | **5-10x** the market average in the month before the deadline | A (Order 775, amended 2026-08-08) |

### Product footprint, claims and trade data

| Metric | Value | Grade / note |
|---|---|---|
| PCF standards | **ISO 14067:2018**; **GB/T 24067-2024** (effective 2024-10-01) | A |
| Carbon-label pilot | Launched 2024-08; 2025-01 list covers 25 provinces / 57 regions / 10 product categories; first 6 certificates in 2026 | A/B |
| Shanghai allowance uplift | **0.5 pp** for certified covered entities (cumulative cap 1 pp reported) | B (0.5 pp); C (cumulative cap) |
| Carbon-neutrality standard | **ISO 14068:2026**, published 2026-09-11, replacing ISO 14068-1:2023; PAS 2060 withdrawn end-2025 | A/B |
| Battery passport | Mandatory from **2027-02-18** for EV, LMT and >2 kWh industrial batteries | A ((EU) 2023/1542) |
| DPP registry | Live **2026-07-20**; about 71 battery data items in 2026-08 guidance | B/C |
| Cross-border carbon data | Pil/DSL/CSL + March 2024 provisions; Lingang pilot: 330 consultations / 32 companies / 34 scenarios by 2026-04 | A (law); B/C (pilot) |
| Carbon-data loans | CCB Shanghai "carbon-data loan" 2024-04-25; Postal Savings Bank Beijing 236 firms / CNY 1.11 bn by 2026-06 | B/C |

---

## 3. Provincial quick table (condensed; full table in the Chinese status file)

| Province | Spot status | No. 136 (2026-27) | Coal capacity price 2026 | VPP framework |
|---|---|---|---|---|
| Beijing | Trial (node TBC) | Cap 0.3598/kWh, 850 million kWh | — | — |
| Tianjin | Trial (node TBC) | Cap 0.32/kWh, 4 billion kWh | 231 | — |
| Shanxi | **Formal 2023-12-22** | — | 165 (C) | Jin Energy Regulation〔2025〕No. 4 (2025-09-18) |
| Inner Mongolia West | **Formal 2025-02-24** | Existing 0.2829/kWh; not in mechanism | — | — |
| Liaoning | Continuous trial | 0.18-0.30/kWh, 5.308 billion kWh | 370 (reliable-capacity compensation, C) | Liao Dev Energy Regulation〔2026〕No. 3 (2026-08-28) |
| Shanghai | Trial (node TBC) | — | — | User-side VPP plan 2025-2027 (1.1 GW in 2025) |
| Jiangsu | Trial (node TBC) | — | — | Work plan 2025-12; 5 GW by 2030 |
| Zhejiang | **Formal 2025-08-07** | First 381.6/MWh; second 0.242-0.393/kWh | — | Rules 2.0 (2026-09-23), three unit types, monthly rating |
| Anhui | **Formal 2026-09-09** | Provincial No. 136 under revision | 165, 6 h | Implementation plan effective 2026-08-01 |
| Fujian | **Formal 2026-09-30** | 0.16-0.39/kWh, 8.36 billion kWh | — | Measures 2026-07-31; VPP in energy/spot/ancillary |
| Jiangxi | Trial (node TBC) | 0.24-0.379/kWh, 4.08 billion kWh | — | VPP registration guide 2026-06-03 |
| Shandong | **Formal 2024-06-17** | Existing 0.3949; first auction wind 0.319/solar 0.225 | — | Lu Dev Energy〔2026〕No. 407 (effective 2026-08-01) |
| Henan | Trial (node TBC) | — | 330 (draft) | — |
| Hubei | **Formal 2025-06** | — | — | — |
| Hunan | Continuous trial | 0.23-0.35/kWh, 2.286 billion kWh | 330 (C) | — |
| Guangdong | **Formal 2023-12-28**; southern region 2026-10-24 | Existing 0.453; 0.20-0.40/kWh, 7.934 billion kWh | 165 | GD Trading〔2025〕No. 152 (2025-07) |
| Guangxi | Southern region formal 2026-10-24 | 0.15-0.36/kWh, single ≤80% | 247.5 (B/C) | — |
| Hainan | Southern region formal 2026-10-24 | — | — | Reported 2026-11-01 effective measure — **to be verified** |
| Chongqing | Continuous trial | — | — | — |
| Sichuan | Continuous trial | — | 231 (C) | — |
| Guizhou | Southern region formal 2026-10-24 | Provincial No. 136 under revision | — | — |
| Yunnan | Southern region formal 2026-10-24 | — | 330 (C) | Yun Energy Regulation〔2025〕No. 198 (effective 2025-10-01); market rules still a draft |
| Shaanxi | **Formal 2026-09-25** | — | 165, 6 h | — |
| Gansu | **Formal 2024-09-05** | 2027 H1 solar 0.2447 / wind 0.2440 | 330 (C) | 250 MW by 2027 |
| Qinghai | Trial (node TBC) | — | 185 (C) | — |
| Ningxia | Trial (node TBC) | — | — | — |
| Xinjiang | Trial (node TBC) | — | 165, 6 h | — |
| Southern region | **Formal 2026-10-24** | Covers Guangdong/Guangxi/Yunnan/Guizhou/Hainan; 15-min prices | — | — |

- **Read the table with the caliber in mind**: "formal" means the provincial spot market, "southern region formal" does not mean each province's own market is formal; a blank means not yet verified here, not that no policy exists.

---

## 4. Open items (flag as "undecided / draft / proposed")

1. **National VPP management measure**: not issued as of 2026-11-01; do not invent a document number.
2. **2026 spot-market basic rules**: draft published 2026-10-19, comments due 2026-11-18, proposed effective 2027-01-01; 2026 still runs on Document No. 1217 and provincial rules.
3. **Retailer measure, risk-control measure, credit-evaluation guidelines, grid-connection rules**: September-October 2026 drafts, not current law.
4. **Liaoning/Anhui VPP thresholds** and **Hainan's reported 2026-11-01 effective date**: still need the original texts.
5. **Shenzhen VPP funding**: the 2024 measure expired 2025-12-31; no 2026 replacement found.
6. **2027 No. 136 auctions**: Liaoning clears 2026-11-08; results and other provinces still arriving.
7. **Order 2222**: CAISO/ISO-NE 2026-11-01, NYISO 2026-12, PJM 2028/29 — implementation, not just approval.
8. **CBAM**: certificates purchasable from 2027-02, first surrender 2027-09-30.
9. **ISO 14068:2026**: certificate transition from 14068-1:2023 still to be confirmed by certification bodies.
10. **DPP**: registry operating rules and the final battery data-item list are not yet public in full; delegated-act dates for steel, construction, textiles, aluminium, tyres and furniture are indicative.
11. **PCF label**: later certification batches, product-specific rules and the formal Shanghai incentive document.
12. **Cross-border carbon data**: official Lingang statistics and sectoral important-data catalogues.
13. **Renewable development**: provincial Document 136 implementation plans, mechanism-energy ratios and contract terms, 2027 incremental auction results, whether green-certificate revenue overlaps with mechanism energy, and the effect of the 2027 spot rules on capture prices.

---

## 5. Answering discipline (short)

- Grade every scale, revenue and subsidy figure (A/B/C/D); never put a C-level figure next to an A-level one without saying so.
- For province-specific questions, confirm the province first and check the Chinese status table; rules differ on thresholds, price caps and products.
- Separate book-era data (2018-2020) from 2026 policy data; do not mix the 470/16.85 GW official figure with the 120 GW connected figure.
- VPP revenue depends on the local market: ask whether spot/ancillary markets exist, what resources are aggregated, and whether an aggregator relationship already exists before discussing business models.
- Verification entry points: NDRC, NEA, provincial DRCs/energy bureaus, Beijing and provincial power exchanges, the southern regional trading platform, cets.com.cn, China Carbon Registration, ICAP. For product footprints add SAMR, MEE and the national product-footprint factor database; for trade data add the Commission CBAM/ESPR pages.
