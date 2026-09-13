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
| Ancillary services & capacity | Product taxonomy and the "Two Rules", China-specific peak regulation and its absorption into spot markets, joint clearing & opportunity-cost pricing, four capacity-adequacy pathways, coal capacity price (Doc. 1501) |
| Settlement & metering | Nine settlement categories, daily accounting / monthly settlement, three-part settlement formula, imbalance funds, 15-minute metering and gap-filling rules |
| Policy & provincial practice | Document-number timeline from Doc. No. 9 to Ministerial Order No. 20, seven provinces with officially running spot markets, first-batch pilot designs (Shanxi circuit breaker, Shandong capacity payment, Sichuan wet/dry-season split, etc.) |
| Renewables market entry | Doc. 136 mechanism prices, existing/new project cutoff (2025-06-01), provincial implementation plans and auction results |
| Carbon markets | National ETS expansion (steel/cement/aluminum), CEA price history, CCER restart and methodologies, MRV and verification, pilot prices, CBAM and green-certificate linkage |
| Strategy & risk | Generator/retailer/consumer strategies, market-power metrics (HHI/KSI/RSI/TTS), five risk classes, market-entry capability checklist |

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
| Business models | Five revenue streams, e2m commission model, peak-load economics, estimation framework and the "scale first, profit later" industry reality |
| Policy & practice | Doc. 357 (2027/2030 targets), Doc. 93, the national standard series, ~20 provinces with dedicated policies and 15 provinces with market rules, the official national tally (470 projects / 16.85 GW tested capability), four capacity-metric distinctions, DR subsidy landscape, V2G Doc. 241 |
| International benchmarks | Germany's Next Kraftwerke and aFRR price signals, the South Australia VPP handover to AGL, US Order 2222 compliance timetable and DOE 80–160 GW goal, UK DFS, Finnish aggregators |

## Repository Structure

```
energy-skills/
├── README.md                                  ← 中文说明
├── README_EN.md                               ← this file
├── skills/
│   ├── electricity-trading-expert/
│   │   ├── SKILL.md                           ← skill file (Chinese, with frontmatter, directly registerable)
│   │   └── SKILL_EN.md                        ← English translation
│   └── virtual-power-plant/
│       ├── SKILL.md                           ← VPP skill file (Chinese, frontmatter, directly registerable)
│       └── SKILL_EN.md                        ← English translation
└── knowledge/                                 ← thematic notes and research records behind the skills
    ├── 电力现货市场101问-A/B/C-*.md                (Spot Market 101 Questions — three thematic notes)
    ├── 电力系统经济学原理-主题笔记.md               (Principles of Power System Economics)
    ├── 电力现货市场实务-精读笔记.md                 (Spot Market Practice)
    ├── 中国碳排放权交易实务-主题笔记.md             (China Carbon Emission Trading Practice)
    ├── 碳管理-从零通往碳中和-主题笔记.md            (Carbon Management)
    ├── 走近虚拟电厂-主题笔记.md                    (Approaching Virtual Power Plants)
    └── 调研-*.md                                  (policy & market research records, dated 2026-09)
```

## Usage

- **Inject into any AI assistant**: paste the full text of a SKILL file as system prompt or context (the Chinese versions are denser; both skills ship with English translations for international models).
- **Register as a skill**: place a skill directory into the skills directory of AI coding tools that support custom skills (e.g. Claude Code).
- **Read directly**: the notes under knowledge/ are standalone quick-reference handbooks with document numbers, figures and comparison tables.

## Sources

| Type | Content |
|---|---|
| Spot markets | Electricity Spot Market: 101 Questions (State Grid Dispatching Control Center, China Electric Power Press, 2021); Electricity Spot Market Practice (State Grid Dispatching Control Center, China Electric Power Press, 2023) |
| Market economics | Principles of Power System Economics (Kirschen & Strbac, Chinese edition); Principles of Economics, Micro & Macro (Mankiw) |
| Virtual power plants | Approaching Virtual Power Plants (Wang Peng, Wang Dongrong et al., China Machine Press, 2020) |
| Carbon | China Carbon Emission Trading Practice (Meng Zaoming, Ge Xing'an et al.); Carbon Management: From Zero to Carbon Neutrality (Wang Jun) |
| Policy & market research | Documents from NDRC and NEA websites, provincial trading centers and energy bureaus, corporate announcements and annual reports; research cutoff 2026-09, each item annotated with source and date |

## Notes

1. **Timeliness**: policy figures (officially running markets, mechanism prices, subsidy standards) were compiled as of 2026-09; book vintages are annotated per note (the carbon-trading books date to ~2016 — mechanisms still apply, figures superseded by the research layer). Always defer to the latest official documents.
2. **Originality**: the notes under knowledge/ are original thematic summaries, not reproductions; copyrights of the source books remain with their authors.
3. **Not investment advice**: price judgments and estimation frameworks are for learning and research only.
4. **Discipline**: the skills ship with a "to be verified" flagging convention and common-mistakes checklists (e.g., using OM baseline emission factors for consumption accounting, mis-citing Document 813 as the spot-market basic rules, conflating capacity metrics) — see Chapter 0 and the reasoning handbook in each SKILL.md.

## Roadmap

- [x] Electricity Trading Expert (Chinese, English)
- [x] Virtual Power Plant Expert (Chinese, English)
- [ ] Carbon asset management skill (compliance calendar, CCER development economics, carbon finance)
- [ ] Quantitative spot-bidding skill (load forecasting, price forecasting, bid simulation)

---

*Compiled 2026-09*
