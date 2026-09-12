# ⚡ Energy Skills · AI Skills for Power & Energy

> English | [中文](README.md)

> Distills professional books and up-to-date policy research in electricity trading into ready-to-load AI skills.
> A collection of distilled domain skills for AI assistants, focused on electricity markets, virtual power plants and carbon markets in China.

## 📦 Current Skills

### [Electricity Trading Expert (electricity-trading-expert)](skills/electricity-trading-expert/SKILL_EN.md)

A full-chain expert skill covering **spot markets / medium & long-term trading / ancillary services / capacity mechanisms / virtual power plants / demand response / carbon markets**. Once loaded, the AI answers as a senior China power-market expert under strict answering discipline (every number cited with policy document number and time point; province-specific questions confirmed first; policy items returned with official lookup pointers).

**Capability Overview**

| Domain | Coverage |
|---|---|
| Spot market | SCUC/SCED clearing, LMP/SMP/ZMP pricing, 3-bus worked examples, negative prices, congestion management & FTR, domestic vs. international price caps, market circuit breakers |
| Medium & long-term + finance | Contracts for differences (government-authorized / market-based), the "six signing" requirements, power futures & options, day-ahead + real-time two-settlement |
| Ancillary services & capacity | Product taxonomy and the "Two Rules" (两个细则)， China-specific peak-regulation product and its absorption into spot, joint clearing & opportunity-cost pricing, four capacity-adequacy pathways, coal capacity price (Doc. 1501) |
| Settlement & metering | Nine settlement categories, daily accounting & monthly settlement, three-part settlement formula, imbalance funds, 15-minute metering and gap-filling rules |
| Policy & provincial practice | Document-number timeline from Document No. 9 to Ministerial Order No. 20, the seven provinces with officially running spot markets, first-batch pilot distinctive designs (Shanxi circuit breaker / Shandong capacity payment / Sichuan wet-dry season split, etc.) |
| New-energy market entry | Document No. 136 mechanism prices, existing/new project cutoff (2025-06-01), provincial implementation plans and auction results |
| Virtual power plants | Doc. 357 (2027/2030 targets), three development stages, Shenzhen/Shanghai/Shanxi rule comparison, five revenue models, CBL baseline calculation, FERC Order 2222 benchmark |
| Carbon markets | National ETS expansion (steel/cement/aluminum), CEA price history, CCER restart & methodologies, MRV and verification practice, pilot carbon prices, CBAM and green-certificate linkage |
| Trading strategy & risk | Generator/retailer/consumer strategies, market-power metrics (HHI/KSI/RSI/TTS), five risk classes, market-entry capability checklist |

### [Virtual Power Plant Expert (virtual-power-plant-expert)](skills/virtual-power-plant/SKILL.md) — Chinese, English version in progress

A full-chain VPP expert skill covering **concept distinctions / resource aggregation / three development stages / market participation mechanisms / business models / control & optimization technology / China policy and international benchmarks**. Complementary to the Electricity Trading Expert: market-mechanism details (clearing, settlement, price caps) live in the former; VPP implementation and operations live in this one.

**Capability Overview**

| Domain | Coverage |
|---|---|
| Concepts & distinctions | Formal definition and "positive/negative plant" dual role, distinctions vs. DR/microgrid/energy-efficiency plant (reverse power flow, physical vs. logical aggregation), the market-stability criterion |
| Resource side | Three resource classes (flexible loads / distributed generation / storage), A–D quadrant classification and development strategy, five flexibility factors, industry-level adjustable ratios, resource-base estimates |
| Three-stage framework | Solicitation-based (subsidy-driven) → market-based (price signals) → self-dispatch (cross-space scheduling): criteria, transition conditions, coexistence |
| Solicitation practice | Jiangsu model (peak-price fund pool + valley-filling auction, 4.02 GW record) and Shanghai model (four-party operation, precision response, auction trading) |
| Market-based mechanisms | Participation flows in energy/ancillary/green-certificate-carbon markets, CVPP/TVPP duality, US entity taxonomy (SC/LSE/CSP/MSP), Finnish aggregator regulatory insights |
| Control & optimization | Four forecast types (load/output/price/flexibility), three-layer control mechanisms (clustering, differentiated contracts, storage alliance), Jibei FUN-power platform architecture |
| Emerging tech | Communication selection (NB-IoT/LoRa/5G uRLLC), blockchain selection (consortium chain + PBFT/Raft + off-chain scaling + BSN) and five application areas |
| Business models | Five revenue streams, e2m 25% commission model, peak-load economics (coal ~¥40bn vs VPP ¥40-57bn), five-step estimation framework |
| Policy & practice | Doc. 357 (2027/2030 targets), Shenzhen/Shanghai/Shanxi rules comparison, DR subsidy landscape, V2G nine-city pilots, Jibei operating data |
| International benchmarks | Germany Next Kraftwerke (9,516 units/8,179 MW) & e2m, Australia Tesla SA VPP (hierarchical aggregation + FCAS 83% lesson), three US institutional paths, Finnish aggregators |
| Risk & operations | Six-difficulty checklist, CBL baseline settlement, aggregation ≠ reliability (daily configuration audits), single-market dependency warning, capability checklist |

## 📁 Repository Structure

```
energy-skills/
├── README.md                                  ← 中文说明
├── README_EN.md                               ← this file
├── skills/
│   ├── electricity-trading-expert/
│   │   ├── SKILL.md                           ← skill file (Chinese, with frontmatter, directly registerable)
│   │   └── SKILL_EN.md                        ← skill file (English translation)
│   └── virtual-power-plant/
│       └── SKILL.md                           ← VPP skill file (Chinese, frontmatter, directly registerable)
└── knowledge/                                 ← distilled knowledge base behind the skills
    ├── 电力现货市场101问-A-基础与价格机制.md        (Spot Market 101 Qs, Part A: fundamentals & price mechanisms)
    ├── 电力现货市场101问-B-出清结算与省域实践.md    (Part B: clearing, settlement & provincial practice)
    ├── 电力现货市场101问-C-结算TTS与政策演进.md     (Part C: settlement, TTS & policy evolution)
    ├── 电力系统经济学原理-主题笔记.md               (Principles of Power System Economics — thematic notes)
    ├── 电力现货市场实务-精读笔记.md                 (Spot Market Practice — close-reading notes)
    ├── 中国碳排放权交易实务-主题笔记.md             (China Carbon Emission Trading Practice — thematic notes)
    ├── 碳管理-从零通往碳中和-主题笔记.md            (Carbon Management — thematic notes)
    ├── 走近虚拟电厂-主题笔记.md                    (Approaching Virtual Power Plants — thematic notes)
    ├── 调研-电力市场政策与开源资源-2026-09.md       (Research: market policy & open-source tools, Sep 2026)
    ├── 调研-虚拟电厂与碳市场-2026-09.md            (Research: VPP & carbon markets, Sep 2026)
    └── 调研-速查合并-2026-09.md                    (Research: merged quick-reference, Sep 2026)
```

> Note: the `knowledge/` notes are kept in Chinese — they are dense original-language distillations aimed at Chinese-market practice. The English SKILL.md is self-contained and does not require reading them.

## 🚀 Usage

**Option 1 — as a ZCode / Claude Code skill**
Drop the `skills/electricity-trading-expert/` directory into your user skills directory (e.g. `~/.zcode/skills/`) and restart; the skill triggers automatically, or invoke it via `/skill`.

**Option 2 — inject into any AI assistant**
Paste the full text of `SKILL_EN.md` (or `SKILL.md` for Chinese) as system prompt / context into any LLM (ChatGPT, Gemini, DeepSeek, etc.).

**Option 3 — human reading**
The 10 thematic notes under `knowledge/` are standalone quick-reference handbooks packed with document numbers, figures, worked examples and comparison tables.

## 🔬 How the Knowledge Was Built

A **three-level distillation pipeline** produced this repository:

```
7 professional books (PDF; 4 of them image-only scans)
   │  PyMuPDF rendering + Windows OCR (1,127 pages)
   ▼
L1 part distillation —— 22 parallel agents, section-by-section structured notes (~2.85M chars → 27 notes)
   ▼
L2 book-level merge —— 8 agents, thematic dedup & compression (→ 10 book notes + 1 research digest)
   ▼
L3 final synthesis —— read all book notes + web research, write SKILL.md
   ▲
   └── Web research layer: 2 research agents (2026-09-12), latest policies/prices/open-source tools,
       every fact tagged with source URL and date; unverifiable items flagged 待核实 (to be verified)
```

**Knowledge Sources**

| Type | Content |
|---|---|
| Spot markets | Electricity Spot Market: 101 Questions (State Grid Dispatching Control Center, 2021), Electricity Spot Market Practice (State Grid Dispatching Control Center, 2023) |
| Market economics | Principles of Power System Economics (Kirschen & Strbac, Chinese ed.), Principles of Economics, Micro & Macro (Mankiw) |
| Virtual power plants | Approaching Virtual Power Plants (Wang Peng, Wang Dongrong et al., China Machine Press 2020) |
| Carbon | China Carbon Emission Trading Practice (Meng Zaoming et al.), Carbon Management: From Zero to Carbon Neutrality (Wang Jun) |
| Web research | NDRC/NEA policies 2023-2026, provincial trading-center data, Fudan Carbon Price Index, ICAP, GitHub open-source ecosystem (PyPSA, pandapower, Grid2Op, gridstatus, etc.) |

## ⚠️ Important Notes

1. **Timeliness**: policy figures (officially-running market list, mechanism prices, subsidy standards, etc.) reflect the research cutoff of **2026-09-12**; always defer to the latest official documents. Book-knowledge time points are annotated per book (carbon-trading books date to ~2016 — mechanisms still valid, figures superseded by the web-research layer).
2. **Originality**: the `knowledge/` notes are original thematic summaries and distillations (not reproductions); copyrights of the source books remain with their authors. This repository contains no full-text book content.
3. **Not investment advice**: all price judgments and estimation frameworks are for learning and research only.
4. **Discipline**: the skill ships with a "to-be-verified" flagging convention and a common-mistakes checklist (e.g., using OM baseline emission factors for consumption accounting, mis-citing Document 813 as the spot-market basic rules) — see SKILL.md Chapters 0 and 14.

## 🗺️ Roadmap

- [x] Electricity Trading Expert skill (released, Chinese + English)
- [x] Virtual Power Plant Expert skill (released, Chinese)
- [ ] Carbon asset management skill (compliance calendar, CCER development economics, carbon finance instruments)
- [ ] Quantitative spot-bidding skill (load forecasting, price forecasting, bid simulation with open-source toolchain)
- [ ] English versions of remaining skills (VPP expert in progress)

---

*Built 2026-09-12 ｜ Generated by a ZCode multi-agent distillation pipeline*
