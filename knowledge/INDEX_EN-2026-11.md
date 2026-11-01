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
| `调研-电力市场政策与开源资源-2026-09.md` | Research note | 2026-09 policy and open-source tooling |
| `调研-虚拟电厂与碳市场-2026-09.md` | Research note | 2026-09 VPP and carbon-market findings |
| `调研-速查合并-2026-09.md` | Research note | 2026-09 merged quick-reference |
| `调研-VPP政策与市场-2026-09增量.md` | Research note | Provincial VPP policies, national scale, V2G, pilots |
| `调研-VPP商业模式与国际-2026-09增量.md` | Research note | VPP revenue models, company data, international cases |
| `调研-电力市场2026-10增量.md` | Research note | October 2026 electricity-market updates and correction list |
| `调研-碳市场与CBAM-2026-10增量.md` | Research note | October 2026 carbon market and CBAM updates |
| `调研-VPP政策2026-10增量.md` | Research note | October 2026 VPP policy, scale calibers and business models |
| `省级市场状态表-2026-11.md` | Status table | One row per province: spot / No. 136 auction / capacity price / VPP / ancillary / retail risk |
| `索引与口径-2026-11.md` | Handbook | Document-number index, caliber dictionary, source grading, watchlist |
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

---

## 5. Answering discipline (short)

- Grade every scale, revenue and subsidy figure (A/B/C/D); never put a C-level figure next to an A-level one without saying so.
- For province-specific questions, confirm the province first and check the Chinese status table; rules differ on thresholds, price caps and products.
- Separate book-era data (2018-2020) from 2026 policy data; do not mix the 470/16.85 GW official figure with the 120 GW connected figure.
- VPP revenue depends on the local market: ask whether spot/ancillary markets exist, what resources are aggregated, and whether an aggregator relationship already exists before discussing business models.
- Verification entry points: NDRC, NEA, provincial DRCs/energy bureaus, Beijing and provincial power exchanges, the southern regional trading platform, cets.com.cn, China Carbon Registration, ICAP.
