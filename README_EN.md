<p align="center">
  <img src="knowledge/assets/logo-book.svg" alt="Energy Skills book-and-bolt logo" width="96">
</p>

# Energy Skills · Power Systems, Power Markets & Carbon Markets

English | [中文](README.md)

Nine domain skills for AI assistants, backed by **64 knowledge modules** (28,769 body lines across 12 sections). Each skill is a self-contained Markdown handbook that can be injected into an LLM as context: once loaded, the model answers as a senior practitioner and follows built-in discipline — figures cited with policy document numbers and dates, province confirmed before giving local rules, policy items returned with official lookup pointers, and unverified data flagged as "to be verified".

Current version **v1.9**, data cutoff **2026-11-10**. Entry points: [knowledge hub](knowledge/index.html) · [changelog](CHANGELOG_EN.md).

## Quick start

- **Inject into any AI assistant**: paste the full text of a `SKILL.md` as system prompt or context; the Chinese versions are denser, the English versions easier for international models.
- **Register as a skill**: place `skills/<name>/` into the skills directory of an AI coding tool that supports custom skills (e.g. Claude Code).
- **Read directly**: the notes under `knowledge/` are standalone quick-reference handbooks with document numbers, figures and comparison tables; browse them from the [knowledge hub](knowledge/index.html). Each of the nine skills also has an HTML reading page with a one-click TXT download. The [national policy index](knowledge/政策列表-2026-11.md) links 55 national documents and the [provincial policy index](knowledge/省级政策列表-2026-11.md) links 13 provincial documents to verified official full texts.
- **Check before committing**: run `node scripts/check-consistency.mjs`, `node scripts/check-maintenance.mjs --check` and `node scripts/build-knowledge-html.mjs --check`; run `python tools/selftest.py` once for each of the seven skills that ship tools.

## Skills

| Skill | Answers | Deliverable | Entry |
|---|---|---|---|
| Electricity Trading Expert | spot clearing and pricing, medium/long-term and finance, ancillary services and capacity, settlement and metering, provincial practice, renewables market entry, carbon markets, overseas markets (Australia/Germany/UK/Italy/Spain/Netherlands/Poland/Belgium-Nordics/US/Japan), strategy and risk | bilingual handbook | [Chinese](skills/electricity-trading-expert/SKILL.md) · [English](skills/electricity-trading-expert/SKILL_EN.md) |
| Virtual Power Plant Expert | VPP concepts, resource aggregation, the three development stages, market participation, business models, control and optimisation, Chinese policy and international benchmarks | bilingual handbook | [Chinese](skills/virtual-power-plant/SKILL.md) · [English](skills/virtual-power-plant/SKILL_EN.md) |
| Spot Bidding Quant | load and price forecasting, bias correction, quantity-price curves, procurement portfolios, bid simulation, rolling backtests and T+1 attribution | bilingual handbook + zero-dependency Python tools + synthetic data | [Chinese](skills/spot-bidding-quant/SKILL.md) · [English](skills/spot-bidding-quant/SKILL_EN.md) |
| Carbon Asset Management Expert | compliance calendar, allowance gap, CEA/CCER procurement, CCER development economics, carbon finance, CBAM, product carbon footprint, neutrality claims, DPP | bilingual handbook + zero-dependency Python tools | [Chinese](skills/carbon-asset-expert/SKILL.md) · [English](skills/carbon-asset-expert/SKILL_EN.md) |
| Storage Investment & Operations Expert | six project forms, five revenue streams, LCOS/IRR/NPV/DSCR, degradation and augmentation, assessment deductions, business models and stress tests | bilingual handbook + zero-dependency Python tools | [Chinese](skills/storage-investment-operations/SKILL.md) · [English](skills/storage-investment-operations/SKILL_EN.md) |
| Renewable Project Development & Grid Connection Expert | resource assessment, Doc. 136 mechanism pricing, LCOE and after-tax cash flow, grid approvals and grid-code standards, curtailment and absorption, provincial auctions | bilingual handbook + zero-dependency Python tools | [Chinese](skills/renewable-project-development/SKILL.md) · [English](skills/renewable-project-development/SKILL_EN.md) |
| EMS Dispatch Expert | 96-interval economic dispatch, SOC and reserve, PCC and export blocking, demand charges and the charging window, degradation cost, multi-market stacking, MPC and uncertainty, capability assessment | bilingual handbook + zero-dependency Python tools | [Chinese](skills/ems-dispatch/SKILL.md) · [English](skills/ems-dispatch/SKILL_EN.md) |
| User-Side Tariff & Bill Optimization Expert | bill line-item teardown, capacity vs contracted vs actual demand, the 105% overrun and 40% floor, optimal declared value, TOU and load shifting, power-factor assessment, government funds, retail and market-linked package comparison | bilingual handbook + zero-dependency Python tools | [Chinese](skills/tariff-bill-optimization/SKILL.md) · [English](skills/tariff-bill-optimization/SKILL_EN.md) |
| Retail Electricity Sales & Risk Expert | full-cost package pricing, customer portfolio contribution, wholesale procurement coverage, deviation expectation and quantiles, retail-wholesale inversion stress tests, performance guarantees and credit, 5/8/10 settlement, exit and universal service | bilingual handbook + zero-dependency Python tools | [Chinese](skills/retail-electricity-risk/SKILL.md) · [English](skills/retail-electricity-risk/SKILL_EN.md) |

The skills divide labour explicitly: market rules and settlement in Electricity Trading Expert, aggregation and operations in Virtual Power Plant Expert, carbon compliance and finance in Carbon Asset Management Expert, bidding and risk control in Spot Bidding Quant, project decisions in the storage and renewable skills, interval-by-interval dispatch and deliverability in the EMS Dispatch Expert, bill structure and filing choices in the Tariff & Bill Optimization Expert, and retailer packaging, customer portfolios, procurement matching, deviation and guarantees in the Retail Electricity Sales & Risk Expert. Overlaps are pointers, not duplicated text.

## Knowledge base

The 64 modules sit in 12 sections: foundations and economics, spot and inter-provincial trading, overseas markets (Australia's NEM, Germany, UK GB, Italy, Spain, France, the Netherlands, Poland, Belgium/the Nordics, the US ERCOT/PJM/CAISO and Japan), cross-cutting topics (grid connection and compliance, capacity mechanisms, ancillary and balancing markets, storage revenue modelling and data sources, cross-border PPAs/green certificates/tolling, same-caliber snapshot and decision calendar), electricity prices, renewables and grid connection, storage and EMS (including the SCADA data link), integrated energy and zero-carbon parks, carbon markets and management, VPPs, index and tools, and research records. Every Markdown file carries frontmatter (`id`, `section`, `level`, `title`, `summary`, `tags`, `cutoff`, `related`, and more); the [knowledge hub](knowledge/index.html) and its 64 knowledge pages plus 18 skill pages — cards, counts, search and TXT downloads — are generated by the build script.

| Question | Start here |
|---|---|
| No power-sector background; build the big picture first | [101 A landscape](knowledge/电力系统通识-A-格局与主体.md), [B fundamentals](knowledge/电力系统通识-B-发输配变用.md), [C reform history](knowledge/电力系统通识-C-改革史.md), [D new actors](knowledge/电力系统通识-D-新角色与现货市场.md) |
| Document numbers, calibres and provincial status | [index and calibres](knowledge/索引与口径-2026-11.md), [provincial market table](knowledge/省级市场状态表-2026-11.md), [English index](knowledge/INDEX_EN-2026-11.md) |
| How spot markets clear and settle | [101 A basics and pricing](knowledge/电力现货市场101问-A-基础与价格机制.md), [B clearing, settlement and provinces](knowledge/电力现货市场101问-B-出清结算与省域实践.md), [C settlement, TTS and policy](knowledge/电力现货市场101问-C-结算TTS与政策演进.md), [practice notes](knowledge/电力现货市场实务-精读笔记.md), [power-system economics](knowledge/电力系统经济学原理-主题笔记.md), [inter-provincial and cross-regional trading](knowledge/省间与跨区交易-2026-11.md) |
| How Australia, Germany, the UK, Italy, Spain, France, the Netherlands, Poland, Belgium/the Nordics, the US and Japan trade electricity, and how storage is invested in | [Australia's NEM](knowledge/澳大利亚NEM电力市场-2026-11.md), [Germany](knowledge/德国电力市场-2026-11.md), [UK](knowledge/英国电力市场-2026-11.md), [Italy](knowledge/意大利电力市场-2026-11.md), [Spain](knowledge/西班牙电力市场-2026-11.md), [France](knowledge/法国电力市场-2026-11.md), [Netherlands](knowledge/荷兰电力市场-2026-11.md), [Poland](knowledge/波兰电力市场-2026-11.md), [Belgium and the Nordics](knowledge/比利时与北欧电力市场-2026-11.md), [United States](knowledge/美国电力市场-2026-11.md), [Japan](knowledge/日本电力市场-2026-11.md), [Overseas storage business](knowledge/海外储能业务-2026-11.md), [skill chapter 7A](skills/electricity-trading-expert/SKILL_EN.md), [storage skill chapter 14A](skills/storage-investment-operations/SKILL_EN.md) |
| What an electricity price is made of, and which documents govern it | [taxonomy](knowledge/中国电价制度谱系-2026-11.md), [current policy and lookup](knowledge/中国电价现行政策与查证-2026-11.md), [price history](knowledge/中国电价史-2026-11.md), [international comparison method](knowledge/国际电价比较-方法与模板-2026-11.md), [tariff and bill skill](skills/tariff-bill-optimization/SKILL_EN.md) |
| Whether storage is worth investing in, and how it is assessed | [storage investment and operations](knowledge/储能投资与运营-2026-11.md), [technology routes, safety and grid-forming](knowledge/储能技术路线安全与构网型并网-2026-11.md), [storage EMS algorithms](knowledge/储能EMS优化调度-算法与工程-2026-11.md), [EMS skill](skills/ems-dispatch/SKILL.md) |
| Whether a renewable project can be developed and connected | [renewable development and grid connection](knowledge/新能源项目开发与并网-2026-11.md), [grid-connection assessment and the two rules](knowledge/并网运行考核与两个细则-2026-11.md), [integrated energy and zero-carbon parks](knowledge/综合能源与零碳园区-2026-11.md) |
| How VPPs and demand response are implemented | [VPP aggregation, dispatch and business models](knowledge/虚拟电厂聚合调度与商业模式-2026-11.md), [approaching virtual power plants](knowledge/走近虚拟电厂-主题笔记.md), [demand response, V2G and flexible resources](knowledge/需求响应、车网互动与灵活性资源-2026-11.md), [microgrid EMS algorithms](knowledge/微网EMS优化调度-算法与工程-2026-11.md), [EMS skill](skills/ems-dispatch/SKILL.md) |
| Carbon compliance, footprints and export response | [carbon practice](knowledge/碳资产实务-2026-11.md), [China carbon trading practice](knowledge/中国碳排放权交易实务-主题笔记.md), [carbon management](knowledge/碳管理-从零通往碳中和-主题笔记.md) |
| How bidding and risk control are engineered | [quantitative bidding and trading risk](knowledge/量化报价与交易风控-工程化-2026-11.md), [market risk, credit and settlement](knowledge/电力市场风险、信用与结算-2026-11.md) |
| How a retailer prices, controls deviation and secures guarantees | [retail electricity sales and risk skill](skills/retail-electricity-risk/SKILL_EN.md), [market risk, credit and settlement](knowledge/电力市场风险、信用与结算-2026-11.md), [provincial market table](knowledge/省级市场状态表-2026-11.md) |
| Test whether an answer has drifted | [golden Q&A](knowledge/黄金问答集-2026-11.md) — 28 high-frequency questions, also the regression checklist |

Research records (electricity market, VPP, carbon market, quant vendors, carbon-management vendors) are archived in `knowledge/` by date to trace where conclusions came from; the skills and thematic notes remain the authoritative layer.

## Repository structure

```
energy-skills/
├── README.md / README_EN.md        ← entry pages (this file)
├── CHANGELOG.md / CHANGELOG_EN.md  ← release history
├── LICENSE                         ← CC BY-NC 4.0
├── .github/workflows/consistency.yml
├── scripts/
│   ├── check-consistency.mjs       ← structure / links / versions / CN-EN parity / content discipline
│   ├── credibility.mjs             ← credibility register parser and content gates
│   ├── check-maintenance.mjs       ← due-review board and maintenance-ledger checks
│   ├── build-knowledge-html.mjs    ← hub builder (frontmatter → HTML + credibility.json)
│   └── knowledge.config.mjs        ← sections, navigation and static copy
├── skills/                         ← nine skills, each with SKILL.md and SKILL_EN.md
│   ├── electricity-trading-expert/
│   ├── virtual-power-plant/
│   ├── spot-bidding-quant/             ← plus tools/ and data/sample/
│   ├── carbon-asset-expert/            ← plus tools/
│   ├── storage-investment-operations/  ← plus tools/
│   ├── renewable-project-development/  ← plus tools/
│   ├── ems-dispatch/                  ← plus tools/ (microgrid and storage dispatch kernel)
│   ├── tariff-bill-optimization/      ← plus tools/ (bill, demand, TOU and package calculators)
│   └── retail-electricity-risk/       ← plus tools/ (package, portfolio, deviation and guarantee models)
└── knowledge/
    ├── index.template.html         ← hub skeleton (hand-maintained)
    ├── index.html                  ← generated
    ├── credibility.json            ← generated: machine-readable credibility register
    ├── assets/                     ← reading-page styles and scripts + marks (3 SVGs)
    ├── html/                       ← generated: 64 knowledge pages + 18 skill pages
    │   └── download/skills/        ← generated: 18 skill TXT files
    └── *.md                        ← knowledge modules (source, frontmatter-driven)
```

## Maintaining the knowledge hub

`knowledge/index.html`, `knowledge/credibility.json` and `knowledge/html/` are generated artifacts — do not edit them by hand. When adding or changing a module:

1. fill in the frontmatter of `knowledge/*.md`: `id`, `section`, `order`, `level`, `title`, `summary`, `tags`, `cutoff`, `related`, `search`, `foot`; modules with worked examples also declare `examples` (`synthetic` / `documented`), and book-note modules declare `historical: true` plus `confidence`;
2. change sections and navigation in `scripts/knowledge.config.mjs`, and the hub skeleton in `knowledge/index.template.html`;
3. rebuild and verify:

```bash
node scripts/build-knowledge-html.mjs           # rebuild hub, reading pages and credibility.json
node scripts/build-knowledge-html.mjs --check   # verify artifacts are current
node scripts/check-consistency.mjs              # structure + content discipline (grade-C / drafts / examples / historical)
node scripts/check-maintenance.mjs              # due-review board (non-blocking)
node scripts/check-maintenance.mjs --check      # maintenance-ledger structure check
```

`knowledge/credibility.json` is the machine-readable register for models and search: 22 grade-C verification tickets, 37 open items, 32 calendar events, draft policy entries, and per-module `confidence` / `examples` / `historical` flags. Filter by `confidence` and exclude unverified `gradeC` figures before injecting content. The source of truth remains the structured tables and lists already present in the Markdown; no second inventory is maintained.

CI runs the consistency check, the maintenance-ledger check, the artifact comparison and seven Python self-tests in sequence; any failure blocks the merge. On the first day of each month `maintenance.yml` publishes the due-review board to the Actions run summary.

## Sources

| Type | Content |
|---|---|
| Spot markets | Electricity Spot Market: 101 Questions (State Grid Dispatching Control Center, China Electric Power Press, 2021); Electricity Spot Market Practice (State Grid Dispatching Control Center, China Electric Power Press, 2023) |
| Market economics | Principles of Power System Economics (Kirschen & Strbac, Chinese edition); Principles of Economics, Micro & Macro (Mankiw) |
| Virtual power plants | Approaching Virtual Power Plants (Wang Peng, Wang Dongrong et al., China Machine Press, 2020) |
| Carbon | China Carbon Emission Trading Practice (Meng Zaoming, Ge Xing'an et al.); Carbon Management: From Zero to Carbon Neutrality (Wang Jun) |
| Policy & market research | Documents from NDRC and NEA websites, provincial trading centers and energy bureaus, corporate announcements and annual reports; research cutoff 2026-11, each item annotated with source and date |

## Notes

1. **Timeliness**: policy figures are compiled as of **2026-11-10**; the September–October 2026 spot-market rules, retailer management measure, risk-control measure and credit-evaluation guideline are still drafts for comment, marked as such in the text. Always defer to the latest official documents.
2. **Originality**: the notes under `knowledge/` are original thematic summaries, not reproductions; copyrights of the source books remain with their authors.
3. **Not investment advice**: price judgments and estimation frameworks are for learning and research only.
4. **Discipline**: the skills ship with a "to be verified" flagging convention and common-mistakes checklists; see Chapter 0 and the reasoning handbook in each `SKILL.md`.

## Roadmap

- [x] Nine skills: electricity trading, virtual power plants, spot bidding quant, carbon asset management, storage investment and operations, renewable project development and grid connection, EMS dispatch, tariff and bill optimization, retail electricity sales and risk (all bilingual; the last seven ship zero-dependency tools)
- [x] Knowledge base: 64 modules across foundations, spot, overseas (Australia/Germany/UK/Italy/Spain/France/Netherlands/Poland/Belgium-Nordics/US/Japan, including storage business), cross-cutting topics (grid compliance, capacity mechanisms, ancillary services, storage revenue and data, PPA/certificates, same-caliber snapshot and decision calendar), prices, renewables, storage, integrated energy, carbon, VPPs, index and research records; the hub is now a generated artifact
- [x] **EMS optimisation and dispatch**: standalone seventh skill with a 96-interval dispatch kernel, demand/capacity/regulation calculators and assertions for every worked example; the examples in both the microgrid and storage notes now match the tools
- [x] **Tariff and bill optimization**: standalone eighth skill with bill teardown, the three basic-charge methods, closed-form optimal declaration, TOU shifting and package comparison, locking worked examples A–H
- [x] **Retail electricity sales and risk**: standalone ninth skill with full-cost package pricing, customer portfolios, deviation expectation and quantiles, and guarantee-gap models, locking worked examples A–H
- [ ] **2026-12 incremental review**: final spot-market rules, the national VPP management measure, the 2027 Doc. 136 auctions, and provincial capacity prices and tender results

## License

All content in this repository (Markdown skill files, knowledge notes, research records and supporting scripts) is licensed under [CC BY-NC 4.0](LICENSE): free to copy, redistribute and adapt with attribution, **not for commercial use**. When quoting or republishing, use the attribution format suggested in `LICENSE` and keep the source link.

*Last updated 2026-11-10*
