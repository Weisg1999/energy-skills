# ⚡ Energy Skills · Electricity Trading & VPP Skill Library

English | [中文](README.md)

A collection of domain skills (Skill) for AI assistants, focused on electricity markets in China. Each skill is a self-contained Markdown handbook that can be injected into an LLM as context: once loaded, the model answers as a senior practitioner of the field and follows built-in answering discipline — figures cited with policy document numbers and dates, province confirmed before giving local rules, policy items returned with official lookup pointers, and unverified data flagged as "to be verified".

## Skills

### [Electricity Trading Expert (electricity-trading-expert)](skills/electricity-trading-expert/SKILL_EN.md)

Covers spot markets, medium & long-term trading, ancillary services and capacity mechanisms, settlement and metering, provincial market practice, renewables market entry (Document No. 136), carbon markets, and trading strategy and risk management. Chinese original: [SKILL.md](skills/electricity-trading-expert/SKILL.md).

| Domain | Coverage |
|---|---|
| Spot market | SCUC/SCED clearing, LMP/SMP/ZMP pricing, 3-bus worked examples, negative prices, congestion management & FTR, price caps (China vs. international), market circuit breakers |
| Medium & long-term + finance | Contracts for differences (government-authorized / market-based), the "six signing" requirements, power futures & options, day-ahead + real-time two-settlement |
| Ancillary services & capacity | Product taxonomy and the "Two Rules", China-specific peak regulation and its absorption into spot markets, joint clearing & opportunity-cost pricing, four capacity-adequacy pathways, coal capacity price (Doc. 1501 / Doc. 114), grid-side independent-storage capacity price |
| Settlement & metering | Nine settlement categories, daily accounting / monthly settlement, three-part settlement formula, imbalance funds, 15-minute metering and gap-filling rules, the 2026 shift from quantity deviation to price deviation |
| Policy & provincial practice | Document-number timeline from Doc. No. 9 to Ministerial Order No. 20, the 2026 national unified market and southern regional market, at least 11 provincial spot markets formally running (as of 2026-10), first-batch pilot designs (Shanxi circuit breaker, Shandong capacity payment, Sichuan wet/dry-season split, etc.) |
| Unified market & retail | State Council Doc. 4 of 2026, southern regional market (formally running 2026-10-24), the 2026 spot-market rules draft (proposed 2027-01-01), retailer exits and wholesale-retail price inversion, risk control and credit evaluation |
| Renewables market entry | Doc. 136 mechanism prices, existing/new project cutoff (2025-06-01), provincial implementation plans and the 2026–2027 auction results |
| Carbon markets | National ETS expansion (3,680 entities / ~8.3 bn tonnes), CEA 2026 prices, CCER, MRV, the 2025/2026 allowance plan, the 2026 regulation revision, CBAM certificate-purchase timing, green-certificate vintage spreads |
| Strategy & risk | Generator/retailer/consumer strategies, retailer exits and wholesale-retail inversion, market-power metrics (HHI/KSI/RSI/TTS), five risk classes, 2026 risk-control and credit-supervision rules |
| VPPs (market view) | Market identity and the ban on duplicate revenue, eligible products and the order provinces open them, provincial thresholds and DR subsidy benchmarks, revenue structure and retail pass-through, Order 2222 per-ISO rollout; aggregation and operations point to the sister skill |

### [Virtual Power Plant Expert (virtual-power-plant-expert)](skills/virtual-power-plant/SKILL_EN.md)

Covers VPP concept distinctions, resource aggregation and assessment, the three development stages (solicitation-based / market-based / autonomous-dispatch), market participation mechanisms, business models and profitability, control & optimization technology, Chinese policy (Doc. 357 and provincial rules), and international benchmarks. Chinese original: [SKILL.md](skills/virtual-power-plant/SKILL.md). Companion to the Electricity Trading Expert: clearing, settlement and price-cap mechanics live there; VPP implementation and operations live here.

| Domain | Coverage |
|---|---|
| Concepts & distinctions | VPP definition and "positive/negative plant" dual role, distinctions vs. DR/microgrid/energy-efficiency plant (reverse power flow, physical vs. logical aggregation), the market-stability criterion |
| Resource side | Flexible loads / distributed generation / storage, A–D quadrant classification, five flexibility factors, industry adjustable ratios and resource-base estimates |
| Three-stage framework | Solicitation-based (subsidy-driven) → market-based (price signals) → autonomous dispatch (cross-space scheduling): criteria, transition conditions, coexistence |
| Solicitation practice | Jiangsu model (peak-price fund pool + valley-filling auction, 4.02 GW record), Shanghai model (four-party operation, precision response, auction trading) |
| Market-based mechanisms | Participation flows in energy/ancillary/green-certificate/carbon markets, CVPP vs. TVPP, US entity taxonomy (SC/LSE/CSP/MSP), Finnish aggregator regulatory insights |
| Control & optimization | Four forecast types (load/output/price/flexibility), three-layer control mechanisms, Jibei FUN-power platform architecture |
| Emerging tech | Communication selection (NB-IoT/LoRa/5G), blockchain selection (consortium chain + distributed-consensus algorithms + off-chain scaling) and application areas |
| Business models | Five revenue streams, e2m commission model, peak-load economics, estimation framework, the "scale first, profit later" industry reality and the 2026 retail-side transmission constraint |
| Policy & practice | Doc. 357 (2027/2030 targets), Doc. 93, the national standard series (GB/T 47241-2026 now in force), at least 20 provinces with dedicated policies and 15 provinces with market rules (Liaoning, Fujian and Anhui are new in 2026; Yunnan's framework dates from 2025), the official national tally (470 projects / 16.85 GW tested capability) versus the 2026 media figure of 120 GW of connected capacity, four capacity-metric distinctions, green direct connection (100 projects / 34.10 GW), DR subsidy landscape, V2G Doc. 241 |
| International benchmarks | Germany's Next Kraftwerke and aFRR price signals, the South Australia VPP handover to AGL, US Order 2222 per-ISO compliance timetable (CAISO / ISO-NE 2026-11-01) and DOE 80–160 GW goal, UK DFS, Finnish aggregators |

### [Spot Bidding Quant (spot-bidding-quant)](skills/spot-bidding-quant/SKILL_EN.md)

Covers a reproducible chain from raw data to a submitted bid: load, price and output forecasting, forecast-bias correction, quantity-price curves and declared-quantity decisions, retail procurement portfolios, bid simulation and market-structure identification, rolling backtests and T+1 PnL attribution. Chinese original: [SKILL.md](skills/spot-bidding-quant/SKILL.md). Ships with a **zero-dependency Python reference implementation** (`tools/`) and **synthetic sample data** (`data/sample/`); `python tools/selftest.py` runs and asserts the figures quoted in the text. Complementary to the other two skills: rules and settlement live in Electricity Trading Expert, aggregation and operations in Virtual Power Plant Expert, and this skill answers only "how to compute, how to bid, how to verify".

| Domain | Coverage |
|---|---|
| Bidding space | The ten rule parameters to confirm before bidding (segment count, price caps, secondary cap, offer adequacy, minimum load, contract decomposition, etc.), three bidding identities, and rule text versus system implementation |
| Data & leakage | Minimum data set, availability and disclosure channels, cleaning rules, feature-availability timing table (to prevent look-ahead leakage) |
| Load forecasting | Seasonal naive baseline → similar-day (±25% abnormal-day filter) → AR/ARIMAX; temperature correction; translating forecast error into economic value |
| Price forecasting | Residual load and marginal-cost mechanics, end-to-end learning routes, separate modelling of spikes and negative prices, direction accuracy / spike recall / pinball loss |
| Bidding theory | Optimal bid for a price taker = marginal cost (falsifiable), pivotal-unit residual-demand pricing, compliance red lines, contract coverage and risk appetite |
| Thermal bidding | Cost structure to multi-segment curves, start-up decisions, separate accounting for must-run units |
| Renewables & storage | Declared quantity under asymmetric penalties, storage arbitrage threshold, co-located solar-plus-storage bidding, input contract for revenue estimates |
| Retail & consumers | Forecast → procurement portfolio → tariff design, the 2026 wholesale-retail inversion constraint, scenario and CVaR exposure simulation |
| Bid simulation | Marginal clearing, bid sweep (pivotal range and the dispatch cliff), HHI concentration, and the limits of simulation |
| Backtest & attribution | Rolling origin, out-of-sample residual correction, metric set, four-way T+1 attribution (forecast / bid / execution / rules) |
| Engineering & submission | D-1 timeline, submission checklist, amendment audit trail, monitoring and fallback, build-versus-buy |
| Production engines | What a production clearing engine contains (SCUC, SCED, RUC, joint clearing, inter-regional ATC, capacity) and why a teaching sandbox differs structurally, not just in accuracy |

## Repository Structure

```
energy-skills/
├── README.md                                  ← 中文说明
├── README_EN.md                               ← this file
├── LICENSE                                    ← CC BY-NC 4.0
├── scripts/check-consistency.mjs              ← checker (Node 24, no third-party deps)
├── .github/workflows/consistency.yml          ← CI: tables / links / versions / CN-EN numbers + Python self-test
├── skills/
│   ├── electricity-trading-expert/
│   │   ├── SKILL.md                           ← skill file (Chinese, with frontmatter, directly registerable)
│   │   └── SKILL_EN.md                        ← English translation
│   ├── virtual-power-plant/
│   │   ├── SKILL.md                           ← VPP skill file (Chinese, frontmatter, directly registerable)
│   │   └── SKILL_EN.md                        ← English translation
│   └── spot-bidding-quant/
│       ├── SKILL.md                           ← spot-bidding skill (Chinese, frontmatter, directly registerable)
│       ├── SKILL_EN.md                        ← English translation
│       ├── tools/                             ← zero-dependency reference implementation (forecast / bid / simulate / backtest / selftest)
│       └── data/sample/                       ← synthetic sample data (60 days × 96 slots)
└── knowledge/                                 ← thematic notes and research records behind the skills
    ├── 电力现货市场101问-A/B/C-*.md                (Spot Market 101 Questions — three thematic notes)
    ├── 电力系统经济学原理-主题笔记.md               (Principles of Power System Economics)
    ├── 电力现货市场实务-精读笔记.md                 (Spot Market Practice)
    ├── 中国碳排放权交易实务-主题笔记.md             (China Carbon Emission Trading Practice)
    ├── 碳管理-从零通往碳中和-主题笔记.md            (Carbon Management)
    ├── 走近虚拟电厂-主题笔记.md                    (Approaching Virtual Power Plants)
    ├── 调研-*-2026-09(.增量).md                    (policy & market research records dated 2026-09)
    ├── 调研-电力市场2026-10增量.md                 (electricity-market update, 2026-11)
    ├── 调研-碳市场与CBAM-2026-10增量.md            (carbon market & CBAM update, 2026-11)
    ├── 调研-VPP政策2026-10增量.md                  (VPP policy update, 2026-11)
    ├── 省级市场状态表-2026-11.md                   (provincial market status table: 33 markets + southern region)
    ├── 索引与口径-2026-11.md                       (policy index / caliber dictionary / source grading / watchlist)
    ├── INDEX_EN-2026-11.md                        (English index, key figures and condensed provincial table)
    ├── 调研-量化报价与厂商实践-2026-11.md           (vendor practice: Lumin AI participant side, Tsintergy operations side)
    └── 黄金问答集-2026-11.md                       (28 golden Q&As, also the regression checklist)
```

## Usage

- **Inject into any AI assistant**: paste the full text of a SKILL file as system prompt or context (the Chinese versions are denser; every skill ships with an English translation for international models).
- **Register as a skill**: place a skill directory into the skills directory of AI coding tools that support custom skills (e.g. Claude Code).
- **Read directly**: the notes under knowledge/ are standalone quick-reference handbooks with document numbers, figures and comparison tables.
- **Verify and maintain**: check document numbers and status in [knowledge/索引与口径-2026-11.md](knowledge/索引与口径-2026-11.md); look up province-specific answers in [knowledge/省级市场状态表-2026-11.md](knowledge/省级市场状态表-2026-11.md); test whether an answer has drifted using [knowledge/黄金问答集-2026-11.md](knowledge/黄金问答集-2026-11.md). English-only readers should start from [knowledge/INDEX_EN-2026-11.md](knowledge/INDEX_EN-2026-11.md).
- **Check before committing**: run `node scripts/check-consistency.mjs` (GitHub Actions runs it too) to verify blank lines around tables, relative links, version markers and CN/EN number parity.

## Sources

| Type | Content |
|---|---|
| Spot markets | Electricity Spot Market: 101 Questions (State Grid Dispatching Control Center, China Electric Power Press, 2021); Electricity Spot Market Practice (State Grid Dispatching Control Center, China Electric Power Press, 2023) |
| Market economics | Principles of Power System Economics (Kirschen & Strbac, Chinese edition); Principles of Economics, Micro & Macro (Mankiw) |
| Virtual power plants | Approaching Virtual Power Plants (Wang Peng, Wang Dongrong et al., China Machine Press, 2020) |
| Carbon | China Carbon Emission Trading Practice (Meng Zaoming, Ge Xing'an et al.); Carbon Management: From Zero to Carbon Neutrality (Wang Jun) |
| Policy & market research | Documents from NDRC and NEA websites, provincial trading centers and energy bureaus, corporate announcements and annual reports; research cutoff 2026-11, each item annotated with source and date |

## Notes

1. **Timeliness**: policy figures (officially running markets, mechanism prices, subsidy standards, capacity prices, carbon prices) were compiled as of **2026-11-01**; the September–October 2026 spot-market rules, retailer management measure, risk-control measure and credit-evaluation guideline are still **drafts for comment**, marked as such in the text. Book vintages are annotated per note (the carbon-trading books date to ~2016 — mechanisms still apply, figures superseded by the research layer). Always defer to the latest official documents.
2. **Originality**: the notes under knowledge/ are original thematic summaries, not reproductions; copyrights of the source books remain with their authors.
3. **Not investment advice**: price judgments and estimation frameworks are for learning and research only.
4. **Discipline**: the skills ship with a "to be verified" flagging convention and common-mistakes checklists (e.g., using OM baseline emission factors for consumption accounting, mis-citing Document 813 as the spot-market basic rules, conflating capacity metrics) — see Chapter 0 and the reasoning handbook in each SKILL.md.

## Update Log

### 2026-11-01 (v1.3)
- **Third skill: Spot Bidding Quant (Chinese and English)**. Covers the data layer and leakage prevention, load/price/output forecasting, bias correction, quantity-price curves and declared-quantity decisions, retail procurement portfolios, bid simulation, rolling backtests and four-way T+1 attribution. Scope is "how to compute, how to bid, how to verify"; market rules and settlement stay in the Electricity Trading Expert, aggregation and operations in the Virtual Power Plant Expert.
- **Zero-dependency reference implementation plus synthetic data**: `skills/spot-bidding-quant/tools/` (`forecast` / `bid` / `simulate` / `backtest` / `selftest`, standard library only) and `data/sample/synthetic_spot_60d.csv` (60 days × 96 slots, generated with a fixed seed, not real market data). `python tools/selftest.py` asserts the figures quoted in the text, so prose and code cannot drift apart silently.
- **Falsifiable conclusions**: the optimal bid of a price taker equals marginal cost (no markup is computed for price takers); pivotal units price on residual demand; the storage arbitrage threshold is cycle cost divided by efficiency (68.2 CNY/MWh in the sample); on the synthetic sample the corrected load forecast improves MAE by 10.8% over seasonal naive, and price direction accuracy is 61.4%.
- **Vendor material split by side and graded**: participant side (Shanghai Lumin AI — all performance figures grade C, never benchmarks) and operations/rules side (Beijing Tsintergy — awarded the CNY 4.62 million "clearing-algorithm upgrades" package of the Southern Regional spot technical-support system in 2026-05, grade B tender notice). On this basis Chapter 10.4, "production clearing engine vs teaching simulation", explains how dropping any of SCUC/SCED/RUC/joint clearing/inter-regional ATC/capacity changes what a conclusion can claim.
- **Compliance boundaries**: no regulatory-evasion bidding practices, no economic or capacity withholding playbooks, no collusion strategies; market-power content is for identification and self-checks only; simulation results must be labelled "mechanism demonstration, not a revenue forecast".

### 2026-11-01 (v1.2)
- **Six new maintenance files**: three 2026-10 incremental research notes (electricity market / carbon market & CBAM / VPP policy), a provincial market status table, an index-and-caliber handbook, and a golden Q&A set.
- **Skill structure**: Section 15.2 of both skills (Chinese and English) now links the new files; each opening adds a "maintenance entry points + 2026-2027 open items" block; §0.2 adds A/B/C/D source grading and a province-lookup pointer; Chapters 2–11 (5, 6, 8, 9, 10 for the VPP skill) carry a "chapter data cutoff" line; §7.1 adds a document-status convention; both openings point to the sister skill, making the split explicit ("market rules here, aggregation there") with pointers rather than duplicated figures.
- **Purpose**: the provincial table answers "confirm the province first", the index handbook answers "which document number / which caliber / what source grade", and the Q&A set serves as the regression checklist for each revision.
- **Provincial fact check (2026-11-01)**: added document numbers and dates for Liaoning (Liao Dev Energy Regulation〔2026〕No. 3), Fujian, Anhui, Yunnan and Zhejiang 2.0; corrected Yunnan's "new in 2026" label (framework effective 2025-10-01, 2026 market rules still a draft); added 2026 coal capacity-price levels (Guangdong 165; Tianjin/Sichuan 231; Qinghai 185; Guangxi 247.5; Jilin/Heilongjiang/Hunan/Gansu/Yunnan 330; Liaoning's 370 is reliable-capacity compensation) and the 2027 No. 136 auction ranges for Liaoning/Guangxi; added nuclear market-entry cases (Liaoning Hongyanhe 0.3823/0.3749 CNY/kWh, Guangxi CfD, Guangdong direct market participation).
- **Maintenance tooling and English layer**: added `scripts/check-consistency.mjs` plus GitHub Actions (table spacing/column counts, relative links, version markers, CN/EN number parity) and `knowledge/INDEX_EN-2026-11.md` (English file map, key figures, condensed provincial table, open items), linked from the English README and §15.2 of both English skills.
- **Body-level dedup**: Chapter 9 of the Electricity Trading Expert (Chinese and English) was rewritten as "VPPs and Demand Response (Market View)", keeping only market identity, eligible products, provincial thresholds, revenue and retail pass-through, and Order 2222; aggregation, the three development stages, the technical stack, profitability modelling and company cases now point to Chapters 4/8/9/10 of *Virtual Power Plant Expert*, removing duplication at the body level.
- **License**: added `LICENSE` — all repository content is under CC BY-NC 4.0 (attribution, non-commercial), with a license section in both READMEs.

### 2026-11-01 (v1.1)
- **Electricity Trading Expert**: the list of formally running spot markets was updated from seven provinces to at least 11 provincial markets plus the southern regional market; added the national unified market (State Council Doc. 4 of 2026), the 2026 spot-market rules draft, Doc. 114 and the independent-storage capacity price, the 2026–2027 No. 136 auction results, 2026 carbon price / allowance plan / regulation revision, the CBAM certificate-timing correction, green-certificate vintage spreads, retailer exits and wholesale-retail inversion, nuclear power entering the market, and China's power and carbon futures progress.
- **Virtual Power Plant Expert**: separated the official tally (470 projects / 16.85 GW tested capability) from the 2026 media figure (120 GW of connected capacity); added the note that the national VPP management measure is **not yet issued**, GB/T 47241-2026 taking effect, 2026 provincial rules, green direct connection (100 projects / 34.10 GW), the impact of the 2026 spot rules on VPPs, the retail-side transmission constraint, and per-ISO Order 2222 compliance detail.
- **Corrections**: 2025 medium/long-term turnover 4.81 → 6.3522 trillion kWh (old caliber noted), green power 0.27 → 0.3285 trillion kWh, PJM 329.17 USD/MW-day labeled as 2027/28 (not 2028/29), and CBAM "in force in 2026" is not the same as "buying certificates in 2026".

## Roadmap

- [x] Electricity Trading Expert (Chinese, English)
- [x] Virtual Power Plant Expert (Chinese, English)
- [x] Quantitative spot-bidding skill (load forecasting, price forecasting, bid simulation)
- [ ] Carbon asset management skill (compliance calendar, CCER development economics, carbon finance)
- [ ] 2026-12 incremental review (spot rules finalized, national VPP management measure, 2027 No. 136 auctions)

---

## License

All content in this repository (Markdown skill files, knowledge notes, research records and supporting scripts) is licensed under [CC BY-NC 4.0](LICENSE): free to copy, redistribute and adapt with attribution, **not for commercial use**. When quoting or republishing, use the attribution format suggested in `LICENSE` and keep the source link.

*Last updated 2026-11-01*
