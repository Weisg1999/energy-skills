<p align="center">
  <img src="knowledge/assets/logo-book.svg" alt="Energy Skills 书页电光标识" width="96">
</p>

<h1 align="center">Energy Skills</h1>

<p align="center">
  <strong>电力系统 · 电力市场 · 碳市场</strong><br>
  9 份面向 AI 助手的领域技能 · 100 个知识模块 · 13 个分区
</p>

<p align="center">
  <a href="CHANGELOG.md"><img alt="version v1.9" src="knowledge/assets/badge-version.svg"></a>&nbsp;
  <a href="knowledge/index.html"><img alt="100 knowledge modules" src="knowledge/assets/badge-modules.svg"></a>&nbsp;
  <a href="更新清单.md"><img alt="data cutoff 2026-11-11" src="knowledge/assets/badge-cutoff.svg"></a>&nbsp;
  <a href="LICENSE"><img alt="license CC BY-NC 4.0" src="knowledge/assets/badge-license.svg"></a>
</p>

<p align="center">
  <a href="https://weisg1999.github.io/energy-skills/"><strong>在线阅读</strong></a> ·
  <a href="knowledge/index.html">仓库内入口</a> ·
  <a href="CHANGELOG.md">更新记录</a> ·
  <a href="README_EN.md">English</a>
</p>

> 每份技能都是一册可直接注入大模型上下文的 Markdown 手册。加载后，模型按该领域资深从业者的身份回答，并遵守内置纪律：数字带文号与时点、涉及省份先确认、政策内容给出查证入口、未交叉验证的数据标注“待核实”。

当前版本 **v1.9**，数据截止 **2026-11-11**，正文 41,273 行。知识笔记、100 个阅读页、技能页、全文检索索引与图表均由仓库内容构建生成。

**目录**　[快速开始](#快速开始) · [技能矩阵](#技能矩阵) · [知识库](#知识库) · [仓库结构](#仓库结构) · [维护](#维护知识中心) · [Roadmap](#roadmap) · [许可证](#许可证)

---

## 快速开始

1. **直接阅读**：打开[在线知识库](https://weisg1999.github.io/energy-skills/)，按分类浏览或全文检索；正文命中可直达小节锚点。
2. **注入 AI**：把 `skills/<name>/SKILL.md` 全文作为系统提示或上下文附加给模型。中文版信息密度更高，英文版（`SKILL_EN.md`）便于国际模型理解。
3. **注册为技能**：把 `skills/<name>/` 放入支持自定义技能的 AI 编程工具技能目录（如 Claude Code），即可自动触发。
4. **提交前自检**：重建生成物并运行结构、内容与维护台账校验；九个技能各跑一次自身的 `tools/selftest.py`。

```bash
node scripts/build-knowledge-html.mjs --check
node scripts/check-consistency.mjs
node scripts/check-maintenance.mjs --check
```

## 技能矩阵

九份技能均为中英双语，并各带零依赖 Python 工具与自测。技能之间只留指针，不重复写一套正文。

### 交易与市场

| 技能 | 回答的核心问题 |
|---|---|
| **[电力交易专家](skills/electricity-trading-expert/SKILL.md)** · [EN](skills/electricity-trading-expert/SKILL_EN.md) | 现货出清与定价、中长期与金融、辅助服务与容量、结算计量、省别实践、新能源入市、碳市场、11 个海外市场、交易策略与风控 |
| **[现货报价量化专家](skills/spot-bidding-quant/SKILL.md)** · [EN](skills/spot-bidding-quant/SKILL_EN.md) | 负荷与电价预测、残差校正、量价曲线、购电组合、竞价仿真、滚动回测与 T+1 归因 |
| **[虚拟电厂专家](skills/virtual-power-plant/SKILL.md)** · [EN](skills/virtual-power-plant/SKILL_EN.md) | 资源聚合、三阶段演进、市场参与、商业模式、控制优化、政策与国际对标 |
| **[售电零售与风险专家](skills/retail-electricity-risk/SKILL.md)** · [EN](skills/retail-electricity-risk/SKILL_EN.md) | 套餐全成本定价、客户组合、购电覆盖、偏差考核、批零倒挂、履约保函与退出 |

### 项目与资产

| 技能 | 回答的核心问题 |
|---|---|
| **[储能投资与运营专家](skills/storage-investment-operations/SKILL.md)** · [EN](skills/storage-investment-operations/SKILL_EN.md) | 六种项目形态、五类收益堆叠、LCOS/IRR/NPV/DSCR、退化与增容、考核扣减、商业模式与压测 |
| **[新能源项目开发与并网专家](skills/renewable-project-development/SKILL.md)** · [EN](skills/renewable-project-development/SKILL_EN.md) | 资源评估、136 号文机制电价、LCOE 与税后现金流、并网审批、限电消纳、省别竞价 |
| **[碳资产管理专家](skills/carbon-asset-expert/SKILL.md)** · [EN](skills/carbon-asset-expert/SKILL_EN.md) | 履约日历、配额盈缺、CEA/CCER 采购与开发、碳金融、CBAM、产品碳足迹、碳中和声明、DPP |

### 调度与账单

| 技能 | 回答的核心问题 |
|---|---|
| **[EMS 优化调度专家](skills/ems-dispatch/SKILL.md)** · [EN](skills/ems-dispatch/SKILL_EN.md) | 96 点经济调度、SOC 与备用、并网点与防逆流、需量电费、退化成本、多市场叠加、MPC 与可调能力 |
| **[电价与电费优化专家](skills/tariff-bill-optimization/SKILL.md)** · [EN](skills/tariff-bill-optimization/SKILL_EN.md) | 账单科目拆解、三种基本电费、105% 超需与 40% 下限、最优申报、分时平移、力率考核、零售套餐比价 |

> **怎么选**：市场规则与结算 → 电力交易；报价与回测 → 现货量化；聚合与运营 → 虚拟电厂；项目投决 → 储能/新能源；逐时段调度 → EMS；账单与套餐 → 电价/售电。

<details>
<summary><strong>技能目录索引</strong></summary>

`electricity-trading-expert` · `spot-bidding-quant` · `virtual-power-plant` · `retail-electricity-risk` · `storage-investment-operations` · `renewable-project-development` · `carbon-asset-expert` · `ems-dispatch` · `tariff-bill-optimization`

每个目录包含 `SKILL.md`、`SKILL_EN.md` 与 `tools/`。
</details>

## 知识库

100 个知识模块分为 13 个分区，全部带 frontmatter（`id`、`section`、`title`、`summary`、`tags`、`cutoff`、`related` 等）。[知识中心](knowledge/index.html)的卡片、计数、全文检索、阅读页与下载文件全部由构建脚本生成，覆盖标题、标签与正文；首页以分类筛选切换 13 个分区，每个技能另有 HTML 阅读页与完整 TXT 下载。

**分区速览**

- **基础与市场**：通识与经济学、电力现货、省间与跨区交易、海外 11 个市场
- **专题与资产**：海外并网与合规、容量机制、辅助服务、储能收益、跨国 PPA/绿证、同口径快照
- **产业与运行**：电价、新能源与并网、储能与 EMS（含 SCADA）、综合能源、碳市场、虚拟电厂
- **索引与底稿**：政策原文索引、省别状态、术语口径、黄金问答、调研记录
- **中国省级市场**：11 个 P0 正式市场 + 8 个 P1 试运行/区域市场 + 14 个 P2 薄档案（北京、天津、河北北网、蒙东、吉林、黑龙江、上海、江苏、江西、河南、青海、宁夏、新疆、西藏），共 33 份档案

### 按问题找入口

- **从零建立图景**：[通识 A 格局与主体](knowledge/电力系统通识-A-格局与主体.md) · [B 发输配变用](knowledge/电力系统通识-B-发输配变用.md) · [C 改革史](knowledge/电力系统通识-C-改革史.md) · [D 新角色与现货市场](knowledge/电力系统通识-D-新角色与现货市场.md)
- **政策文号、口径与省别状态**：[国家级政策（55 条）](knowledge/政策列表-2026-11.md) · [省级政策（13 条）](knowledge/省级政策列表-2026-11.md) · [索引与口径](knowledge/索引与口径-2026-11.md) · [省级市场状态表](knowledge/省级市场状态表-2026-11.md) · [英文索引](knowledge/INDEX_EN-2026-11.md)
- **看某个省的市场规则**：[省级市场状态总表](knowledge/省级市场状态表-2026-11.md) · [广东](knowledge/广东电力市场-2026-11.md) · [山东](knowledge/山东电力市场-2026-11.md) · [山西](knowledge/山西电力市场-2026-11.md) · [浙江](knowledge/浙江电力市场-2026-11.md) · [甘肃](knowledge/甘肃电力市场-2026-11.md) · [蒙西](knowledge/蒙西电力市场-2026-11.md) · [安徽](knowledge/安徽电力市场-2026-11.md) · [福建](knowledge/福建电力市场-2026-11.md) · [陕西](knowledge/陕西电力市场-2026-11.md) · [河北南网](knowledge/河北南网电力市场-2026-11.md) · [湖北](knowledge/湖北电力市场-2026-11.md)（首批 11 个 P0；其余省份先在状态总表查状态）
- **第二批（连续结算/区域正式）**：[辽宁](knowledge/辽宁电力市场-2026-11.md) · [湖南](knowledge/湖南电力市场-2026-11.md) · [重庆](knowledge/重庆电力市场-2026-11.md) · [四川](knowledge/四川电力市场-2026-11.md) · [广西](knowledge/广西电力市场-2026-11.md) · [云南](knowledge/云南电力市场-2026-11.md) · [贵州](knowledge/贵州电力市场-2026-11.md) · [海南](knowledge/海南电力市场-2026-11.md)
- **第三批（P2 薄档案）**：[北京](knowledge/北京电力市场-2026-11.md) · [天津](knowledge/天津电力市场-2026-11.md) · [河北北网](knowledge/河北北网电力市场-2026-11.md) · [蒙东](knowledge/蒙东电力市场-2026-11.md) · [吉林](knowledge/吉林电力市场-2026-11.md) · [黑龙江](knowledge/黑龙江电力市场-2026-11.md) · [上海](knowledge/上海电力市场-2026-11.md) · [江苏](knowledge/江苏电力市场-2026-11.md) · [江西](knowledge/江西电力市场-2026-11.md) · [河南](knowledge/河南电力市场-2026-11.md) · [青海](knowledge/青海电力市场-2026-11.md) · [宁夏](knowledge/宁夏电力市场-2026-11.md) · [新疆](knowledge/新疆电力市场-2026-11.md) · [西藏](knowledge/西藏电力市场-2026-11.md)
- **现货怎么出清、怎么结算**：[101 问 A 基础与价格](knowledge/电力现货市场101问-A-基础与价格机制.md) · [B 出清结算与省域实践](knowledge/电力现货市场101问-B-出清结算与省域实践.md) · [C 结算 TTS 与政策](knowledge/电力现货市场101问-C-结算TTS与政策演进.md) · [实务精读](knowledge/电力现货市场实务-精读笔记.md) · [经济学原理](knowledge/电力系统经济学原理-主题笔记.md) · [省间与跨区交易](knowledge/省间与跨区交易-2026-11.md)
- **海外市场怎么交易、储能怎么投**：[澳大利亚 NEM](knowledge/澳大利亚NEM电力市场-2026-11.md) · [德国](knowledge/德国电力市场-2026-11.md) · [英国](knowledge/英国电力市场-2026-11.md) · [意大利](knowledge/意大利电力市场-2026-11.md) · [西班牙](knowledge/西班牙电力市场-2026-11.md) · [法国](knowledge/法国电力市场-2026-11.md) · [荷兰](knowledge/荷兰电力市场-2026-11.md) · [波兰](knowledge/波兰电力市场-2026-11.md) · [比利时与北欧](knowledge/比利时与北欧电力市场-2026-11.md) · [美国](knowledge/美国电力市场-2026-11.md) · [日本](knowledge/日本电力市场-2026-11.md) · [海外储能业务](knowledge/海外储能业务-2026-11.md)
- **电价怎么构成、文件怎么查**：[制度谱系](knowledge/中国电价制度谱系-2026-11.md) · [现行政策与查证](knowledge/中国电价现行政策与查证-2026-11.md) · [电价史](knowledge/中国电价史-2026-11.md) · [国际比较方法](knowledge/国际电价比较-方法与模板-2026-11.md)
- **储能值不值得投、怎么考核**：[储能投资与运营](knowledge/储能投资与运营-2026-11.md) · [技术路线安全与构网型并网](knowledge/储能技术路线安全与构网型并网-2026-11.md) · [储能 EMS 算法](knowledge/储能EMS优化调度-算法与工程-2026-11.md)
- **新能源能不能开发、能不能并网**：[新能源开发与并网](knowledge/新能源项目开发与并网-2026-11.md) · [并网运行考核](knowledge/并网运行考核与两个细则-2026-11.md) · [综合能源与零碳园区](knowledge/综合能源与零碳园区-2026-11.md)
- **VPP 与需求响应怎么落地**：[VPP 聚合、调度与商业模式](knowledge/虚拟电厂聚合调度与商业模式-2026-11.md) · [走近虚拟电厂](knowledge/走近虚拟电厂-主题笔记.md) · [需求响应与车网互动](knowledge/需求响应、车网互动与灵活性资源-2026-11.md) · [微网 EMS 算法](knowledge/微网EMS优化调度-算法与工程-2026-11.md)
- **碳履约、碳足迹与出口应对**：[碳资产实务](knowledge/碳资产实务-2026-11.md) · [中国碳交易实务](knowledge/中国碳排放权交易实务-主题笔记.md) · [碳管理：从零通往碳中和](knowledge/碳管理-从零通往碳中和-主题笔记.md)
- **报价、风控与售电经营**：[量化报价与交易风控](knowledge/量化报价与交易风控-工程化-2026-11.md) · [电力市场风险、信用与结算](knowledge/电力市场风险、信用与结算-2026-11.md) · [省级市场状态表](knowledge/省级市场状态表-2026-11.md)
- **检验回答是否跑偏**：[黄金问答集](knowledge/黄金问答集-2026-11.md)（28 个高频问答，兼改版回归清单）

调研底稿（电力市场、VPP、碳市场、量化厂商、碳管理厂商）按时间存档在 `knowledge/`，用于追溯结论来源；对外结论以技能正文与主题笔记为准。

## 仓库结构

源码与生成物分离：`knowledge/` 是内容源，`knowledge/html/`、`search-index.js`、`credibility.json` 与首页由脚本生成。

<details>
<summary><strong>展开目录树</strong></summary>

```text
energy-skills/
├── README.md / README_EN.md          ← 中英文入口
├── CHANGELOG.md / CHANGELOG_EN.md    ← 版本记录
├── 更新清单.md                       ← 时效台账与复核节奏
├── index.html                        ← Pages 短入口
├── LICENSE                           ← CC BY-NC 4.0
├── .github/workflows/
│   ├── consistency.yml               ← 内容一致性检查
│   └── deploy-pages.yml              ← Pages 发布
├── scripts/
│   ├── build-knowledge-html.mjs      ← 生成知识中心、阅读页、索引与可信度文件
│   ├── architecture-diagrams.mjs     ← 5 张核心架构图的语义化规格
│   ├── check-consistency.mjs         ← 链接、版本、数字与内容纪律
│   ├── check-maintenance.mjs         ← 更新清单到期看板
│   ├── credibility.mjs               ← 可信度登记册
│   └── knowledge.config.mjs          ← 分区、导航与固定文案
├── skills/                           ← 9 份技能，各含 SKILL.md、SKILL_EN.md 与 tools/
└── knowledge/
    ├── index.template.html           ← 首页骨架（手写）
    ├── index.html                    ← 生成：知识中心
    ├── html/                         ← 生成：100 个知识页 + 18 个技能页
    ├── credibility.json              ← 生成：可信度登记册
    ├── english-digest.json           ← 生成：英文路由摘要
    ├── search-index.js               ← 生成：全文检索索引
    ├── assets/                       ← 阅读页样式、脚本与标识
    └── *.md                          ← 知识模块（frontmatter 驱动）
```

</details>

## 维护知识中心

> [!IMPORTANT]
> `knowledge/index.html`、`knowledge/credibility.json`、`knowledge/english-digest.json`、`knowledge/search-index.js` 与 `knowledge/html/` 都是生成物，**不要手改**。内容源始终是 Markdown。

1. **补 frontmatter**：为 `knowledge/*.md` 填写 `id`、`section`、`order`、`level`、`title`、`summary`、`summary_en`、`tags`、`cutoff`、`related`、`search`、`foot`；算例模块补 `examples`，史料型笔记补 `historical: true` 与 `confidence`。
2. **改导航**：分区与导航改 `scripts/knowledge.config.mjs`，首页骨架改 `knowledge/index.template.html`。
3. **记时效**：以 [更新清单.md](更新清单.md) 为准。P0 月度、P1 季度、P2 半年、P3 年度；海外 18 个模块另有拍卖、招标、清缴等事件驱动切片；中国 33 个省级市场的硬节点见 §3.2，其中带完整日期的已挂进 INDEX_EN §4.1 自动触发，到期后一并并入 P0 队列。
4. **重建并校验**：

```bash
node scripts/build-knowledge-html.mjs           # 重建首页、阅读页、索引与 credibility.json
node scripts/build-knowledge-html.mjs --check   # 只校验生成物是否最新
node scripts/check-consistency.mjs              # 结构、链接与内容纪律
node scripts/check-maintenance.mjs --check      # 更新清单结构校验
```

<details>
<summary><strong>生成物、图表、索引与可信度层</strong></summary>

- **正文图表**：无语言标记的 `├/└` 层级树会自动转为结构卡片，多列阶段和箭头链路转为流程卡片；依赖坐标对齐的复杂图保留为带网格和滚动容器的蓝图面板。
- **自动里程碑**：“中国主体进入路径”和“并网流程”的步骤表会转为纵向里程碑，保留负责方、备注、风险与双地区列。储能安全因果/应急链、碳核查与 CCER 流程、微网状态表也会按章节自动组件化。
- **核心架构图**：SCADA 安全分区、VPP/EMS 数据链、V2G、量化交易参考架构、灵活性资源地图由 `architecture-diagrams.mjs` 人工语义化；源图关键节点变动时构建会报错。
- **英文路由**：`english-digest.json` 包含 100 个模块的英文摘要、关键数字、未定事项与 C 级工单状态；`historical: true` 的模块会在阅读页顶部显示“数据不可作现行引用”横幅。
- **全文检索**：`search-index.js` 按 H2/H3 切块，首次聚焦搜索框时才加载；索引只服务页面检索，不进入模型上下文。
- **可信度层**：`credibility.json` 提供 22 项 C 级工单、44 项未定事项、32 条事件日历与逐模块 `confidence` / `examples` / `historical` 声明。注入上下文前可按 `confidence` 过滤，并按 `gradeC.usable` / `banned` 排除不可引用数字。
- **CI**：依次执行一致性校验、维护台账、生成物比对与九个 Python 自测；每月 1 号另把到期看板写入 Actions 摘要。

</details>

> [!TIP]
> Pages 首次启用时，在仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。之后推送 `main` 即自动发布，访问地址保持不变。

## 资料来源

| 类型 | 内容 |
|---|---|
| 电力现货 | 《电力现货市场101问》（国调中心组编，中国电力出版社 2021）、《电力现货市场实务》（国调中心组编，中国电力出版社 2023） |
| 市场经济学 | 《电力系统经济学原理》（Kirschen & Strbac，朱治中译）、《经济学原理》微观/宏观分册（曼昆） |
| 虚拟电厂 | 《走近虚拟电厂》（王鹏、王冬容等，机械工业出版社 2020） |
| 碳市场与碳管理 | 《中国碳排放权交易实务》（孟早明、葛兴安等）、《碳管理：从零通往碳中和》（汪军） |
| 政策与市场调研 | 发改委、能源局官网文件，各省交易中心与能源局公开数据，公司公告与年报；调研时点 2026-11，逐条注明来源与日期 |

## 几点说明

1. **时效性**：政策类数字整理至 **2026-11-11**；2026 年 9–10 月的现货新规、售电公司管理办法、风险防控办法、信用评价指引仍为征求意见稿，正文已标注状态。引用前以官方最新文件为准。
2. **原创性**：`knowledge/` 下的笔记是对原书内容的主题化摘要与提炼，非原文复制；书籍版权归原作者所有。
3. **非投资建议**：文中的价格判断与测算框架仅供学习研究。
4. **口径纪律**：技能内置“待核实”标注约定与常见误区清单；使用前建议先读 `SKILL.md` 第 0 章与推理手册章节。

## Roadmap

- [x] **九份技能**：交易、VPP、量化、碳资产、储能、新能源、EMS、电价与售电，均中英双语并附零依赖 Python 工具与自测。
- [x] **知识库**：100 个模块、13 个分区，含 33 个省级市场、11 个海外市场、横向专题、碳市场、VPP 与调研底稿；知识中心为生成物。
- [x] **阅读体验**：全文检索、分类筛选、深浅主题、移动端适配；正文图表自动组件化，核心架构图人工语义化。
- [ ] **2026-12 增量复核**：现货新规定稿、国家 VPP 管理办法、2027 年 136 号文竞价、省份容量电价与招中标价。

## 许可证

本仓库内容（Markdown 技能、知识笔记、调研记录与辅助脚本）采用 [CC BY-NC 4.0](LICENSE) 授权：可署名后自由复制、分发与改编，**不得用于商业用途**。引用或再发布请按 `LICENSE` 中的建议格式署名，并保留来源链接。

<p align="center"><sub>最后更新于 2026-11-11 · <a href="#energy-skills">回到顶部</a></sub></p>
