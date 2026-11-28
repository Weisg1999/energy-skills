<p align="center">
  <img src="knowledge/assets/logo-book.svg" alt="Energy Skills book-and-bolt logo" width="96">
</p>

<h1 align="center">Energy Skills</h1>

<p align="center">
  <strong>Power Systems · Power Markets · Carbon Markets</strong><br>
  Nine domain skills for AI assistants · 130 knowledge modules · 32 runnable instance packs · 13 sections
</p>

<p align="center">
  <a href="CHANGELOG_EN.md"><img alt="version v2.6" src="knowledge/assets/badge-version.svg"></a>&nbsp;
  <a href="knowledge/index.html"><img alt="130 knowledge modules" src="knowledge/assets/badge-modules.svg"></a>&nbsp;
  <a href="更新清单.md"><img alt="data cutoff 2026-11-27" src="knowledge/assets/badge-cutoff.svg"></a>&nbsp;
  <a href="LICENSE"><img alt="license CC BY-NC 4.0" src="knowledge/assets/badge-license.svg"></a>
</p>

<p align="center">
  <a href="https://weisg1999.github.io/energy-skills/"><strong>Read online</strong></a> ·
  <a href="knowledge/index.html">In-repo entry</a> ·
  <a href="CHANGELOG_EN.md">Changelog</a> ·
  <a href="README.md">中文</a>
</p>

> Every skill is a self-contained Markdown handbook that can be injected into an LLM context. Once loaded, the model answers as a senior practitioner and follows built-in discipline: figures cited with document numbers and dates, province confirmed before local rules, policy items returned with official lookup pointers, and unverified data flagged as “to be verified”.

Current version **v2.6**, data cutoff **2026-11-27**, 58,448 body lines. Notes, 130 reading pages, skill pages, the full-text index and all diagrams are generated from repository content.

**Contents**　[Quick start](#quick-start) · [Skills](#skills) · [Knowledge base](#knowledge-base) · [Repository layout](#repository-layout) · [Maintenance](#maintaining-the-knowledge-hub) · [Roadmap](#roadmap) · [License](#license)

---

## Quick start

1. **Read directly**: open the [online knowledge hub](https://weisg1999.github.io/energy-skills/) and browse by category or search the full text; hits link straight to the matching section anchor.
2. **Inject into AI**: paste `skills/<name>/SKILL.md` as the system prompt or context. The Chinese editions are denser; the English editions (`SKILL_EN.md`) are easier for international models.
3. **Register as a skill**: place `skills/<name>/` into the skills directory of an AI coding tool that supports custom skills (e.g. Claude Code).
4. **Run an instance pack**: pick any `skills/<name>/instances/<pack>/`, run `python run.py --check-config` then `python run.py --demo` to see configuration checks, bid sheets and variance-bridge output.
5. **Check before committing**: rebuild the generated artifacts and run structure, content and maintenance checks; run each skill's `tools/selftest.py` for the nine skills.

```bash
node scripts/build-province-matrix.mjs --check
node scripts/build-knowledge-html.mjs --check
node scripts/check-consistency.mjs
node scripts/check-maintenance.mjs --check
```

## Skills

All nine skills are bilingual and ship zero-dependency Python tools, self-tests and instance packs. Overlaps between skills are pointers, never duplicated text; all 32 instance packs are summarised in the [instance-pack matrix](knowledge/instances.html).

### Trading and markets

| Skill | Core questions |
|---|---|
| **[Electricity Trading Expert](skills/electricity-trading-expert/SKILL_EN.md)** · [CN](skills/electricity-trading-expert/SKILL.md) | spot clearing and pricing, medium/long-term and finance, ancillary services and capacity, settlement, provincial practice, renewables market entry, fuel and gas-fired costs, carbon markets, 11 overseas markets, strategy and risk; includes seven instance packs: the Shandong coal medium/long-term position, Gansu coal capacity plus ancillary services, Gansu wind delivered to Shandong, Sichuan hydro seasonal hedging, the Yunnan cascaded-hydro regional portfolio, Liaoning nuclear mechanism-price allocation, and the Shandong midday negative-price failure replay (runnable replay of replay-library case 1) |
| **[Spot Bidding Quant](skills/spot-bidding-quant/SKILL_EN.md)** · [CN](skills/spot-bidding-quant/SKILL.md) | load and price forecasting, bias correction, quantity-price curves, procurement portfolios, bid simulation, rolling backtests, T+1 attribution; desk layer with the decision clock, scenario/CVaR frontier, settlement bridge and public-data backtest protocol; a zero-dependency SCED/SCUC clearing sandbox plus price-factor attribution and pre-market scenario tools; includes eight instance packs: Shandong thermal, Shandong standalone storage, Shandong PV-plus-storage, Shanxi standalone storage, Gansu wind, Inner Mongolia West renewable spot, Zhejiang spot storage and the Inner Mongolia West wind-solar-storage joint bid (configuration, bids, two-settlement and variance bridge) |
| **[Virtual Power Plant Expert](skills/virtual-power-plant/SKILL_EN.md)** · [CN](skills/virtual-power-plant/SKILL.md) | resource aggregation, three development stages, market participation, business models, control and optimisation, policy and international benchmarks; includes six instance packs for Shanghai, Zhejiang, Jiangsu fast response, Liaoning resource allocation, Shenzhen V2G and the Shanghai data-centre DR slice (aggregation configuration, declaration, scenario clearing and variance bridge) |
| **[Retail Electricity Sales & Risk Expert](skills/retail-electricity-risk/SKILL_EN.md)** · [CN](skills/retail-electricity-risk/SKILL.md) | full-cost package pricing, customer portfolio, procurement coverage, deviation assessment, retail-wholesale inversion, guarantees and exit; includes four instance packs for Guangdong 2026, Jiangsu 2027, Guangdong multi-user direct connection and the Guangdong retail-wholesale inversion failure replay (one province, one entity, D-1 pricing and procurement, T+1 variance bridge) |

### Projects and assets

| Skill | Core questions |
|---|---|
| **[Storage Investment & Operations Expert](skills/storage-investment-operations/SKILL_EN.md)** · [CN](skills/storage-investment-operations/SKILL.md) | six project forms, five revenue streams, LCOS/IRR/NPV/DSCR, degradation and augmentation, assessment deductions, business models and stress tests; includes two instance packs for Anhui capacity pricing and Guangdong spot plus frequency regulation |
| **[Renewable Project Development & Grid Connection Expert](skills/renewable-project-development/SKILL_EN.md)** · [CN](skills/renewable-project-development/SKILL.md) | resource assessment, Doc. 136 mechanism pricing, LCOE and after-tax cash flow, offshore wind CfD, grid approvals, curtailment and absorption, provincial auctions; includes the Yunnan 2027 wind investment-decision instance pack (P50/P90, LCOE, difference settlement, hurdle break-even price and bid band) |
| **[Carbon Asset Management Expert](skills/carbon-asset-expert/SKILL_EN.md)** · [CN](skills/carbon-asset-expert/SKILL.md) | compliance calendar, allowance gap, CEA/CCER procurement and development, carbon finance, CBAM, product carbon footprint, neutrality claims, DPP; includes the Shandong cement 2025 compliance instance pack (benchmark allocation, 5% CCER offset, CEA make-up and carryover) |

### Dispatch and bills

| Skill | Core questions |
|---|---|
| **[EMS Dispatch Expert](skills/ems-dispatch/SKILL_EN.md)** · [CN](skills/ems-dispatch/SKILL.md) | 96-interval economic dispatch, SOC and reserve, PCC and export blocking, demand charges, degradation cost, multi-market stacking, MPC and capability assessment, the forecast-error → declaration → EMS loop, AGC/AVC plant loops and state-estimation / N-1 / ATC interface boundaries; includes the Jiangsu zero-carbon park microgrid instance pack (PV self-consumption, storage peak-valley and demand control, energy-intensity carbon, islanding check) and the Shandong standalone storage-station daily-operation instance pack (96-interval energy arbitrage, AGC and primary-frequency assessment replay) |
| **[User-Side Tariff & Bill Optimization Expert](skills/tariff-bill-optimization/SKILL_EN.md)** · [CN](skills/tariff-bill-optimization/SKILL.md) | bill line-item teardown, three basic-charge methods, the 105% overrun and 40% floor, optimal declared value, TOU shifting, power-factor assessment, retail package comparison; includes the Jiangsu C&I storage instance pack |

> **How to choose**: market rules and settlement → Electricity Trading; bidding and backtests → Spot Quant; aggregation and operations → VPP; project decisions → Storage/Renewables; interval dispatch → EMS; bills and packages → Tariff/Retail.

<details>
<summary><strong>Skill directory index</strong></summary>

`electricity-trading-expert` · `spot-bidding-quant` · `virtual-power-plant` · `retail-electricity-risk` · `storage-investment-operations` · `renewable-project-development` · `carbon-asset-expert` · `ems-dispatch` · `tariff-bill-optimization`

Each directory contains `SKILL.md`, `SKILL_EN.md` and `tools/`.
</details>

## Knowledge base

The 130 knowledge modules sit in 13 sections. Every module carries frontmatter (`id`, `section`, `title`, `summary`, `tags`, `cutoff`, `related`, and more). Cards, counts, full-text search, reading pages and downloads in the [knowledge hub](knowledge/index.html) are generated by the build script and cover titles, tags and body text; the hub switches among 13 sections through category filters, and every skill also has an HTML reading page with a full TXT download. The 32 runnable instance packs cover 12 provincial regions and are summarised on the [instance-pack matrix](knowledge/instances.html); each pack is one province + one entity + one contract/bill set + one rule version.

**Section map**

- **Foundations and markets**: power-system basics and economics, spot markets, quantitative bidding and risk, the desk-day SOP, inter-provincial trading, 11 overseas markets
- **Topics and assets**: grid connection and compliance, capacity mechanisms, ancillary services, storage revenue, cross-border PPAs/certificates, same-caliber snapshot, synthetic case replays and the contract clause library
- **Industry and operations**: tariffs, renewables and grid connection, storage and EMS (including SCADA), integrated energy, carbon markets, VPPs
- **Indexes and research**: policy sources, provincial status, glossary and calibres, golden Q&A, research records
- **Chinese provincial markets**: 11 P0 formal markets + 8 P1 trial/regional markets + 14 P2 thin dossiers (Beijing, Tianjin, Hebei North, Mengdong, Jilin, Heilongjiang, Shanghai, Jiangsu, Jiangxi, Henan, Qinghai, Ningxia, Xinjiang, Tibet), 33 dossiers in total

### Find an entry point by question

- **Build the big picture from zero**: [101 A landscape](knowledge/电力系统通识-A-格局与主体.md) · [B fundamentals](knowledge/电力系统通识-B-发输配变用.md) · [C reform history](knowledge/电力系统通识-C-改革史.md) · [D new actors](knowledge/电力系统通识-D-新角色与现货市场.md) · [E faults, protection and defence](knowledge/故障保护与安全防御-2026-11.md) · [F operations and dispatch](knowledge/电力系统通识-F-运行与调度-2026-11.md) · [G planning and resource adequacy](knowledge/电力系统通识-G-规划与资源充裕性-2026-11.md)
- **Document numbers, calibres and provincial status**: [national policy (55)](knowledge/政策列表-2026-11.md) · [provincial policy (21)](knowledge/省级政策列表-2026-11.md) · [index and calibres](knowledge/索引与口径-2026-11.md) · [provincial market table](knowledge/省级市场状态表-2026-11.md) · [English index](knowledge/INDEX_EN-2026-11.md)
- **Find the rules for one province**: [provincial status table](knowledge/省级市场状态表-2026-11.md) · [Guangdong](knowledge/广东电力市场-2026-11.md) · [Shandong](knowledge/山东电力市场-2026-11.md) · [Shanxi](knowledge/山西电力市场-2026-11.md) · [Zhejiang](knowledge/浙江电力市场-2026-11.md) · [Gansu](knowledge/甘肃电力市场-2026-11.md) · [Mengxi](knowledge/蒙西电力市场-2026-11.md) · [Anhui](knowledge/安徽电力市场-2026-11.md) · [Fujian](knowledge/福建电力市场-2026-11.md) · [Shaanxi](knowledge/陕西电力市场-2026-11.md) · [Hebei South](knowledge/河北南网电力市场-2026-11.md) · [Hubei](knowledge/湖北电力市场-2026-11.md) (first 11 P0; check the status table for the rest)
- **Second batch (continuous trial / regional formal)**: [Liaoning](knowledge/辽宁电力市场-2026-11.md) · [Hunan](knowledge/湖南电力市场-2026-11.md) · [Chongqing](knowledge/重庆电力市场-2026-11.md) · [Sichuan](knowledge/四川电力市场-2026-11.md) · [Guangxi](knowledge/广西电力市场-2026-11.md) · [Yunnan](knowledge/云南电力市场-2026-11.md) · [Guizhou](knowledge/贵州电力市场-2026-11.md) · [Hainan](knowledge/海南电力市场-2026-11.md)
- **Third batch (P2 thin dossiers)**: [Beijing](knowledge/北京电力市场-2026-11.md) · [Tianjin](knowledge/天津电力市场-2026-11.md) · [Hebei North](knowledge/河北北网电力市场-2026-11.md) · [Mengdong](knowledge/蒙东电力市场-2026-11.md) · [Jilin](knowledge/吉林电力市场-2026-11.md) · [Heilongjiang](knowledge/黑龙江电力市场-2026-11.md) · [Shanghai](knowledge/上海电力市场-2026-11.md) · [Jiangsu](knowledge/江苏电力市场-2026-11.md) · [Jiangxi](knowledge/江西电力市场-2026-11.md) · [Henan](knowledge/河南电力市场-2026-11.md) · [Qinghai](knowledge/青海电力市场-2026-11.md) · [Ningxia](knowledge/宁夏电力市场-2026-11.md) · [Xinjiang](knowledge/新疆电力市场-2026-11.md) · [Tibet](knowledge/西藏电力市场-2026-11.md)
- **How spot markets clear and settle**: [101 A basics and pricing](knowledge/电力现货市场101问-A-基础与价格机制.md) · [B clearing, settlement and provinces](knowledge/电力现货市场101问-B-出清结算与省域实践.md) · [C settlement, TTS and policy](knowledge/电力现货市场101问-C-结算TTS与政策演进.md) · [practice notes](knowledge/电力现货市场实务-精读笔记.md) · [power-system economics](knowledge/电力系统经济学原理-主题笔记.md) · [from bids to nodal prices](knowledge/现货出清与价格形成-2026-11.md) · [from power flow to nodal prices](knowledge/潮流阻塞与节点电价-2026-11.md) · [state estimation and security analysis](knowledge/状态估计与安全分析-2026-11.md) · [dynamic security assessment and emergency control](knowledge/动态安全评估与紧急控制-2026-11.md) · [price attribution and pre-market scenarios](knowledge/电价归因与盘前推演-2026-11.md) · [forecast-error → declaration → EMS loop](knowledge/预测误差申报与EMS闭环-2026-11.md) · [inter-provincial trading](knowledge/省间与跨区交易-2026-11.md)
- **How overseas markets trade and how storage is invested in**: [Australia's NEM](knowledge/澳大利亚NEM电力市场-2026-11.md) · [Germany](knowledge/德国电力市场-2026-11.md) · [UK](knowledge/英国电力市场-2026-11.md) · [Italy](knowledge/意大利电力市场-2026-11.md) · [Spain](knowledge/西班牙电力市场-2026-11.md) · [France](knowledge/法国电力市场-2026-11.md) · [Netherlands](knowledge/荷兰电力市场-2026-11.md) · [Poland](knowledge/波兰电力市场-2026-11.md) · [Belgium and the Nordics](knowledge/比利时与北欧电力市场-2026-11.md) · [United States](knowledge/美国电力市场-2026-11.md) · [Japan](knowledge/日本电力市场-2026-11.md) · [Overseas storage business](knowledge/海外储能业务-2026-11.md)
- **How tariffs are built and where to verify them**: [taxonomy](knowledge/中国电价制度谱系-2026-11.md) · [current policy and lookup](knowledge/中国电价现行政策与查证-2026-11.md) · [price history](knowledge/中国电价史-2026-11.md) · [international comparison method](knowledge/国际电价比较-方法与模板-2026-11.md)
- **Whether storage is worth investing in**: [storage investment and operations](knowledge/储能投资与运营-2026-11.md) · [technology routes, safety and grid-forming](knowledge/储能技术路线安全与构网型并网-2026-11.md) · [storage EMS algorithms](knowledge/储能EMS优化调度-算法与工程-2026-11.md) · [plant-cluster and centralised EMS architecture](knowledge/场站群与集控EMS架构-2026-11.md) · [EMS data-interface reference architecture](knowledge/EMS数据接口参考架构-2026-11.md) · [AGC/AVC and frequency-voltage loop](knowledge/AGC-AVC与频率电压闭环-2026-11.md) · [state estimation and security analysis](knowledge/状态估计与安全分析-2026-11.md) · [dynamic security assessment and emergency control](knowledge/动态安全评估与紧急控制-2026-11.md) · [microgrid and storage-station protection setting](knowledge/微电网与储能电站保护整定-2026-11.md) · [BMS and storage EMS state boundaries](knowledge/BMS与储能EMS的状态边界-2026-11.md) · [grid-side storage siting, sizing and reliability value](knowledge/电网侧储能选址定容与可靠性韧性价值-2026-11.md)
- **Whether a renewable project can be developed and connected**: [renewable development and grid connection](knowledge/新能源项目开发与并网-2026-11.md) · [reactive power, voltage and power quality](knowledge/无功电压与电能质量-2026-11.md) · [distribution hosting capacity and distributed connection](knowledge/配电网承载力与分布式接入-2026-11.md) · [grid-connection assessment](knowledge/并网运行考核与两个细则-2026-11.md) · [grid-connection testing and acceptance checklist](knowledge/并网测试与涉网验收实务清单-2026-11.md) · [AGC/AVC and frequency-voltage loop](knowledge/AGC-AVC与频率电压闭环-2026-11.md) · [wideband oscillation and plant impedance](knowledge/宽频振荡与场站阻抗分析-2026-11.md) · [integrated energy and zero-carbon parks](knowledge/综合能源与零碳园区-2026-11.md)
- **How VPPs and demand response are implemented**: [VPP aggregation, dispatch and models](knowledge/虚拟电厂聚合调度与商业模式-2026-11.md) · [approaching virtual power plants](knowledge/走近虚拟电厂-主题笔记.md) · [demand response and V2G](knowledge/需求响应、车网互动与灵活性资源-2026-11.md) · [physical ground truth of adjustable load](knowledge/可调负荷的物理真值-2026-11.md) · [microgrid EMS algorithms](knowledge/微网EMS优化调度-算法与工程-2026-11.md) · [microgrid operating modes and islanding transitions](knowledge/微网运行方式与并离网切换-2026-11.md)
- **Carbon compliance, footprints and export response**: [carbon practice](knowledge/碳资产实务-2026-11.md) · [China carbon trading practice](knowledge/中国碳排放权交易实务-主题笔记.md) · [carbon management](knowledge/碳管理-从零通往碳中和-主题笔记.md)
- **Bidding, risk and retail operations**: [quantitative bidding and risk](knowledge/量化报价与交易风控-工程化-2026-11.md) · [market risk, credit and settlement](knowledge/电力市场风险、信用与结算-2026-11.md) · [provincial market table](knowledge/省级市场状态表-2026-11.md) · [desk-day SOP and exception handling](knowledge/交易台日课与异常处置-SOP-2026-11.md) · [synthetic case replays](knowledge/合成案例复盘库-2026-11.md) · [contract clause library](knowledge/合同与条款库-2026-11.md)
- **How to sign contracts, review a month, move to wholesale, and run asset custody**: [medium/long-term contract structure and signing assessment](knowledge/中长期合同结构与签约考核-2026-11.md) · [monthly market monitoring and review](knowledge/电力市场月度监测与复盘-2026-11.md) · [retail and wholesale-user procurement portfolios](knowledge/售电与批发用户购电组合-2026-11.md) · [asset trading custody and agency](knowledge/场站交易托管与代理-2026-11.md)
- **Start from a runnable pack**: the [instance-pack matrix](knowledge/instances.html) summarises all 32 packs — spot bids (including storage and wind-solar-storage joint bids), retail pricing, VPP aggregation, storage investment, EMS dispatch (park microgrid + storage-station daily operation) and carbon compliance, plus two failure-replay slices (Shandong midday negative price, Guangdong retail-wholesale inversion).
- **Test whether an answer has drifted**: [golden Q&A](knowledge/黄金问答集-2026-11.md) — 86 high-frequency questions, including 10 on price drivers, 11 on system physics / EMS engineering, 12 on tariffs / investment / contracts, 4 on data / replay, 6 on fault protection / distribution, 2 on microgrid operating-mode transitions, 2 on spot clearing, 2 on price attribution / pre-market scenarios, 2 on AGC/AVC and state estimation, 2 on transient stability and wideband oscillation, and 5 on protection setting, BMS boundaries, storage siting, operations and planning, also the regression checklist.

Research records (electricity market, VPP, carbon market, quant vendors, carbon-management vendors) are archived in `knowledge/` by date to trace where conclusions came from; the skills and thematic notes remain the authoritative layer.

## Repository layout

Source and generated artifacts are kept separate: `knowledge/` is the source of content; `knowledge/html/`, `search-index.js`, `credibility.json` and the hub are generated.

<details>
<summary><strong>Expand the directory tree</strong></summary>

```text
energy-skills/
├── README.md / README_EN.md          ← entry pages
├── CHANGELOG.md / CHANGELOG_EN.md    ← release history
├── 更新清单.md                       ← time-sensitivity ledger and review cadence
├── index.html                        ← Pages short entry
├── LICENSE                           ← CC BY-NC 4.0
├── .github/workflows/
│   ├── consistency.yml               ← content consistency checks
│   └── deploy-pages.yml              ← Pages deployment
├── scripts/
│   ├── build-knowledge-html.mjs      ← hub, reading pages, index and credibility artifacts
│   ├── architecture-diagrams.mjs     ← semantic specs for five core architecture diagrams
│   ├── build-province-matrix.mjs     ← generate the provincial parameter matrix
│   ├── check-consistency.mjs         ← links, versions, figures and content discipline
│   ├── check-maintenance.mjs         ← due-review board
│   ├── credibility.mjs               ← credibility register
│   └── knowledge.config.mjs          ← sections, navigation and static copy
├── skills/                           ← nine skills, each with SKILL.md, SKILL_EN.md, tools/ and instances/ packs
└── knowledge/
    ├── index.template.html           ← hand-maintained hub skeleton
    ├── index.html                    ← generated: knowledge hub
    ├── instances.html                ← generated: instance-pack matrix (32 packs / 12 provincial regions)
    ├── html/                         ← generated: 130 knowledge pages + 18 skill pages
    ├── credibility.json              ← generated: credibility register
    ├── english-digest.json           ← generated: English routing digest
    ├── search-index.js               ← generated: full-text index
    ├── assets/                       ← reading-page styles, scripts and marks
    ├── data/province-params.json     ← structured source for the provincial matrix
    └── *.md                          ← knowledge modules (frontmatter-driven)
```

</details>

## Maintaining the knowledge hub

> [!IMPORTANT]
> `knowledge/index.html`, `knowledge/instances.html`, `knowledge/credibility.json`, `knowledge/english-digest.json`, `knowledge/search-index.js` and `knowledge/html/` are generated artifacts. **Do not edit them by hand.** Markdown remains the source of truth. The provincial parameter matrix inside the status table is also generated from `knowledge/data/province-params.json` by `scripts/build-province-matrix.mjs`.

1. **Fill frontmatter**: add `id`, `section`, `order`, `level`, `title`, `summary`, `summary_en`, `tags`, `cutoff`, `related`, `search` and `foot` to each `knowledge/*.md`; add `examples` for worked examples and `historical: true` plus `confidence` for historical notes.
2. **Update navigation**: edit `scripts/knowledge.config.mjs` for sections and navigation, and `knowledge/index.template.html` for the hub skeleton.
3. **Track time sensitivity**: use [更新清单.md](更新清单.md): P0 monthly, P1 quarterly, P2 half-yearly, P3 yearly. The 18 overseas modules also carry event-driven slices for auctions, tenders and compliance deadlines, escalated into the P0 queue. Hard dates for the 33 Chinese provincial markets are listed in §3.2 of the same ledger; entries with full dates are hooked into INDEX_EN §4.1 for automatic escalation into the P0 queue.
4. **Rebuild and verify**:

```bash
node scripts/build-province-matrix.mjs           # rebuild the provincial parameter matrix
node scripts/build-province-matrix.mjs --check   # verify the matrix is current
node scripts/build-knowledge-html.mjs           # rebuild hub, reading pages, index and credibility.json
node scripts/build-knowledge-html.mjs --check   # verify artifacts are current
node scripts/check-consistency.mjs              # structure, links and content discipline
node scripts/check-maintenance.mjs --check      # maintenance-ledger structure check
```

<details>
<summary><strong>Generated artifacts, diagrams, search and credibility</strong></summary>

- **Body diagrams**: unlabelled `├/└` hierarchies become structure cards; multi-column stages and arrow chains become process cards; coordinate-dependent layouts remain in a blueprint panel with a grid and horizontal scrolling.
- **Automatic milestones**: step tables under market-entry and grid-connection headings become vertical milestones retaining owner, note, risk and two-region fields. Storage-safety chains, carbon verification/CCER flows and microgrid state tables are also componentised by section.
- **Core architecture figures**: SCADA security zones, the VPP/EMS data chain, V2G, the quantitative reference architecture and the flexibility resource map are hand-semanticised in `architecture-diagrams.mjs`; the build fails if their source anchors move.
- **English routing**: `english-digest.json` contains English summaries for 130 modules, key figures, open items and grade-C states; `historical: true` modules show a “data is not current” banner at the top of the reading page.
- **Full-text search**: `search-index.js` splits each note at H2/H3 and loads only when the search field is focused. It never enters a model context.
- **Credibility layer**: `credibility.json` provides 22 grade-C tickets, 55 open items, 32 calendar events and per-module `confidence` / `examples` / `historical` flags. Filter by `confidence` and by `gradeC.usable` / `banned` before injecting content.
- **CI**: consistency, maintenance ledger, artifact comparison and nine Python self-tests run in sequence; a monthly workflow publishes the due-review board to the Actions summary.

</details>

> [!TIP]
> For first-time Pages setup, choose **Settings → Pages → Build and deployment → Source → GitHub Actions**. After that, pushing `main` deploys automatically and the public URL stays stable.

## Sources

| Type | Content |
|---|---|
| Spot markets | Electricity Spot Market: 101 Questions (State Grid Dispatching Control Center, China Electric Power Press, 2021); Electricity Spot Market Practice (State Grid Dispatching Control Center, China Electric Power Press, 2023) |
| Market economics | Principles of Power System Economics (Kirschen & Strbac, Chinese edition); Principles of Economics, Micro and Macro (Mankiw) |
| Virtual power plants | Approaching Virtual Power Plants (Wang Peng, Wang Dongrong et al., China Machine Press, 2020) |
| Carbon | China Carbon Emission Trading Practice (Meng Zaoming, Ge Xing'an et al.); Carbon Management: From Zero to Carbon Neutrality (Wang Jun) |
| Policy and market research | NDRC and NEA documents, provincial trading centres and energy bureaus, corporate announcements and annual reports; research cutoff 2026-11, each item annotated with source and date |

## Notes

1. **Timeliness**: policy figures are compiled as of **2026-11-27**; the September–October 2026 spot-market rules, retailer management measure, risk-control measure and credit-evaluation guideline are still drafts for comment, marked as such. Always defer to the latest official documents.
2. **Originality**: the notes under `knowledge/` are original thematic summaries, not reproductions; copyrights of the source books remain with their authors.
3. **Not investment advice**: price judgments and estimation frameworks are for learning and research only.
4. **Discipline**: the skills ship with a “to be verified” convention and common-mistakes checklists; read Chapter 0 and the reasoning handbook in each `SKILL.md` before use.

## Roadmap

- [x] **Nine skills**: trading, VPP, quant, carbon, storage, renewables, EMS, tariff and retail — all bilingual, each with zero-dependency Python tools, self-tests and instance packs.
- [x] **Knowledge base**: 130 modules across 13 sections, including 33 Chinese provincial markets, 11 overseas markets, cross-cutting topics, the three decision-layer modules (desk-day SOP / replay library / clause library), the seven system-physics and EMS-engineering chain modules, the fault-protection / power-quality / distribution / microgrid-operations quartet, the spot-clearing and price-attribution pair, the AGC/AVC and state-estimation pair, the dynamic-security and wideband-oscillation pair, the protection-setting / BMS / storage-siting trio, the medium/long-term contract structure / monthly review / procurement-portfolio / asset-custody quartet and foundations F/G, carbon, VPPs and research records; plus 32 instance packs (12 provincial regions). The hub and the instance-pack matrix are generated.
- [x] **Reading experience**: full-text search, category filters, light/dark themes and mobile layouts; body diagrams are componentised automatically and core architecture figures semanticised.
- [ ] **December 2026 incremental review**: final spot-market rules, the national VPP management measure, the 2027 Doc. 136 auctions, and provincial capacity prices and tender results.

## License

All content in this repository (Markdown skills, knowledge notes, research records and supporting scripts) is licensed under [CC BY-NC 4.0](LICENSE): free to copy, redistribute and adapt with attribution, **not for commercial use**. When quoting or republishing, use the attribution format suggested in `LICENSE` and keep the source link.

<p align="center"><sub>Last updated 2026-11-27 · <a href="#energy-skills">Back to top</a></sub></p>
