# ⚡ Energy Skills · 电力系统、电力市场与碳市场技能库

[English](README_EN.md) | 中文

九份面向 AI 助手的领域技能，配套 **45 个知识模块**（15,383 行正文、10 个分区）。每份技能是一册可直接注入大模型上下文的 Markdown 手册：加载后，模型以该领域资深从业者的身份回答，并遵守内置纪律——数字带文号与时点、涉及省份先确认、政策类内容给出查证入口、未交叉验证的数据标注"待核实"。

当前版本 **v1.9**，数据截止 **2026-11-09**。入口：[知识中心](knowledge/index.html) · [更新记录](CHANGELOG.md)。

## 快速开始

- **注入 AI 助手**：将 `SKILL.md` 全文作为系统提示或上下文附加给模型；中文版信息密度更高，英文版便于国际模型理解。
- **注册为技能**：把 `skills/<name>/` 放入支持自定义技能的 AI 编程工具（如 Claude Code）的技能目录，即可自动触发。
- **直接阅读**：`knowledge/` 下的笔记本身就是带文号、数字与对比表的速查手册，从[知识中心](knowledge/index.html)按分区进入即可。
- **提交前自检**：运行 `node scripts/check-consistency.mjs` 与 `node scripts/build-knowledge-html.mjs --check`；七个带工具的技能各跑一次 `python tools/selftest.py`。

## 九个技能

| 技能 | 回答什么问题 | 交付物 | 入口 |
|---|---|---|---|
| 电力交易专家 electricity-trading-expert | 现货出清与定价、中长期与金融、辅助服务与容量、结算计量、省别实践、新能源入市、碳市场、交易策略与风控 | 双语手册 | [中文](skills/electricity-trading-expert/SKILL.md) · [English](skills/electricity-trading-expert/SKILL_EN.md) |
| 虚拟电厂专家 virtual-power-plant-expert | VPP 概念辨析、资源聚合、三阶段演进、市场参与、商业模式、控制优化、政策与国际对标 | 双语手册 | [中文](skills/virtual-power-plant/SKILL.md) · [English](skills/virtual-power-plant/SKILL_EN.md) |
| 现货报价量化专家 spot-bidding-quant | 负荷与电价预测、残差校正、量价曲线、购电组合、竞价仿真、滚动回测与 T+1 归因 | 双语手册 + 零依赖 Python 工具 + 合成数据 | [中文](skills/spot-bidding-quant/SKILL.md) · [English](skills/spot-bidding-quant/SKILL_EN.md) |
| 碳资产管理专家 carbon-asset-expert | 履约日历、配额盈缺、CEA/CCER 采购、CCER 开发测算、碳金融、CBAM、产品碳足迹、碳中和声明、DPP | 双语手册 + 零依赖 Python 工具 | [中文](skills/carbon-asset-expert/SKILL.md) · [English](skills/carbon-asset-expert/SKILL_EN.md) |
| 储能投资与运营专家 storage-investment-operations | 六种项目形态、五类收益堆叠、LCOS/IRR/NPV/DSCR、退化与增容、考核扣减、商业模式与压测 | 双语手册 + 零依赖 Python 工具 | [中文](skills/storage-investment-operations/SKILL.md) · [English](skills/storage-investment-operations/SKILL_EN.md) |
| 新能源项目开发与并网专家 renewable-project-development | 资源评估、136 号文机制电价、LCOE 与税后现金流、并网审批与涉网标准、限电消纳、省别竞价 | 双语手册 + 零依赖 Python 工具 | [中文](skills/renewable-project-development/SKILL.md) · [English](skills/renewable-project-development/SKILL_EN.md) |
| EMS 优化调度专家 ems-dispatch | 96 点经济调度、SOC 与备用、并网点与防逆流、需量电费与充电窗口、退化成本、多市场叠加、MPC 与不确定性、可调能力 | 双语手册 + 零依赖 Python 工具 | [中文](skills/ems-dispatch/SKILL.md) · [English](skills/ems-dispatch/SKILL_EN.md) |
| 用户侧电价与电费优化专家 tariff-bill-optimization | 电费单科目拆解、容量/合同需量/实际需量比选、105% 超需与 40% 下限、最优申报值、分时与负荷平移、力率考核、基金附加、零售套餐与市场联动比价 | 双语手册 + 零依赖 Python 工具 | [中文](skills/tariff-bill-optimization/SKILL.md) · [English](skills/tariff-bill-optimization/SKILL_EN.md) |
| 售电零售与风险专家 retail-electricity-risk | 套餐全成本定价、客户组合贡献、批发购电覆盖、偏差考核期望与分位、批零倒挂压测、履约保函与信用、结算 5/8/10、退出与保底售电 | 双语手册 + 零依赖 Python 工具 | [中文](skills/retail-electricity-risk/SKILL.md) · [English](skills/retail-electricity-risk/SKILL_EN.md) |

技能之间有明确分工：市场规则与结算归电力交易专家，资源聚合与运营归虚拟电厂专家，碳履约与碳金融归碳资产管理专家，报价与风控归现货报价量化专家，项目投决归储能与新能源两个专家，逐时段调度与可交付性归 EMS 优化调度专家，电费账单结构与申报比选归电价与电费优化专家，售电公司的套餐、客户组合、购电匹配、偏差与担保归售电零售与风险专家。重叠处只留指针，不重复写一套。

## 知识库

45 个模块分为 10 个分区：通识与经济学、电力现货与省间交易、电价、新能源与并网、储能与 EMS（含 SCADA 数据链路）、综合能源与零碳园区、碳市场与碳管理、虚拟电厂、索引与工具、调研底稿。每份 Markdown 带 frontmatter（`id`、`section`、`level`、`title`、`summary`、`tags`、`cutoff`、`related` 等），[知识中心](knowledge/index.html)的卡片、计数、搜索与 45 个阅读页全部由构建脚本生成。

| 想解决的问题 | 从这里开始 |
|---|---|
| 没有电力背景，先建立整体图景 | [通识 A 格局与主体](knowledge/电力系统通识-A-格局与主体.md)、[B 发输配变用](knowledge/电力系统通识-B-发输配变用.md)、[C 改革史](knowledge/电力系统通识-C-改革史.md)、[D 新角色与现货市场](knowledge/电力系统通识-D-新角色与现货市场.md) |
| 政策文号、口径与省别状态 | [国家级政策列表（55 条官方原文）](knowledge/政策列表-2026-11.md)、[省级政策列表（13 条官方原文）](knowledge/省级政策列表-2026-11.md)、[索引与口径](knowledge/索引与口径-2026-11.md)、[省级市场状态表](knowledge/省级市场状态表-2026-11.md)、[英文索引](knowledge/INDEX_EN-2026-11.md) |
| 现货怎么出清、怎么结算 | [101 问 A 基础与价格机制](knowledge/电力现货市场101问-A-基础与价格机制.md)、[B 出清结算与省域实践](knowledge/电力现货市场101问-B-出清结算与省域实践.md)、[C 结算 TTS 与政策演进](knowledge/电力现货市场101问-C-结算TTS与政策演进.md)、[实务精读](knowledge/电力现货市场实务-精读笔记.md)、[经济学原理](knowledge/电力系统经济学原理-主题笔记.md)、[省间与跨区交易](knowledge/省间与跨区交易-2026-11.md) |
| 电价怎么构成、现行文件怎么查 | [制度谱系](knowledge/中国电价制度谱系-2026-11.md)、[现行政策与查证](knowledge/中国电价现行政策与查证-2026-11.md)、[电价史](knowledge/中国电价史-2026-11.md)、[国际比较方法与模板](knowledge/国际电价比较-方法与模板-2026-11.md)、[电价与电费优化技能](skills/tariff-bill-optimization/SKILL.md) |
| 储能值不值得投、怎么考核 | [储能投资与运营](knowledge/储能投资与运营-2026-11.md)、[技术路线安全与构网型并网](knowledge/储能技术路线安全与构网型并网-2026-11.md)、[储能 EMS 算法底稿](knowledge/储能EMS优化调度-算法与工程-2026-11.md)、[EMS 技能](skills/ems-dispatch/SKILL.md) |
| 新能源能不能开发、能不能并网 | [新能源项目开发与并网](knowledge/新能源项目开发与并网-2026-11.md)、[并网运行考核与两个细则](knowledge/并网运行考核与两个细则-2026-11.md)、[综合能源与零碳园区](knowledge/综合能源与零碳园区-2026-11.md) |
| 虚拟电厂与需求响应怎么落地 | [走近虚拟电厂](knowledge/走近虚拟电厂-主题笔记.md)、[需求响应、车网互动与灵活性资源](knowledge/需求响应、车网互动与灵活性资源-2026-11.md)、[微网 EMS 算法底稿](knowledge/微网EMS优化调度-算法与工程-2026-11.md)、[EMS 技能](skills/ems-dispatch/SKILL.md) |
| 碳履约、碳足迹与出口应对 | [碳资产实务](knowledge/碳资产实务-2026-11.md)、[中国碳排放权交易实务](knowledge/中国碳排放权交易实务-主题笔记.md)、[碳管理：从零通往碳中和](knowledge/碳管理-从零通往碳中和-主题笔记.md) |
| 报价与风控怎么工程化 | [量化报价与交易风控](knowledge/量化报价与交易风控-工程化-2026-11.md)、[电力市场风险、信用与结算](knowledge/电力市场风险、信用与结算-2026-11.md) |
| 售电公司怎么定价、怎么控偏差与担保 | [售电零售与风险技能](skills/retail-electricity-risk/SKILL.md)、[电力市场风险、信用与结算](knowledge/电力市场风险、信用与结算-2026-11.md)、[省级市场状态表](knowledge/省级市场状态表-2026-11.md) |
| 快速检验回答是否跑偏 | [黄金问答集](knowledge/黄金问答集-2026-11.md)（28 个高频问答，兼改版回归清单） |

调研底稿（电力市场、VPP、碳市场、量化厂商、碳管理厂商）按时间存档在 `knowledge/`，用于追溯结论来源；对外结论以技能正文与主题笔记为准。

## 仓库结构

```
energy-skills/
├── README.md / README_EN.md        ← 入口说明（本页）
├── CHANGELOG.md / CHANGELOG_EN.md  ← 版本变更记录
├── LICENSE                         ← CC BY-NC 4.0
├── .github/workflows/consistency.yml
├── scripts/
│   ├── check-consistency.mjs       ← 表格/链接/版本/中英数字校验
│   ├── build-knowledge-html.mjs    ← 知识中心构建器（frontmatter → HTML）
│   └── knowledge.config.mjs        ← 分区、导航与固定文案
├── skills/                         ← 九份技能，各含 SKILL.md、SKILL_EN.md
│   ├── electricity-trading-expert/
│   ├── virtual-power-plant/
│   ├── spot-bidding-quant/             ← 附 tools/ 与 data/sample/
│   ├── carbon-asset-expert/            ← 附 tools/
│   ├── storage-investment-operations/  ← 附 tools/
│   ├── renewable-project-development/  ← 附 tools/
│   ├── ems-dispatch/                  ← 附 tools/（微网与储能调度内核）
│   ├── tariff-bill-optimization/      ← 附 tools/（账单、需量、分时与套餐测算）
│   └── retail-electricity-risk/       ← 附 tools/（套餐定价、组合、偏差与保函）
└── knowledge/
    ├── index.template.html         ← 首页骨架（手动维护）
    ├── index.html                  ← 生成物
    ├── html/                       ← 生成物：45 个阅读页
    └── *.md                        ← 知识模块（源头，frontmatter 驱动）
```

## 维护知识中心

`knowledge/index.html` 与 `knowledge/html/` 是生成物，不要手改。新增或修改模块时：

1. 在 `knowledge/*.md` 的 frontmatter 补全 `id`、`section`、`order`、`level`、`title`、`summary`、`tags`、`cutoff`、`related`、`search`、`foot`；
2. 分区与导航改 `scripts/knowledge.config.mjs`，首页骨架改 `knowledge/index.template.html`；
3. 重建并校验：

```bash
node scripts/build-knowledge-html.mjs           # 重建首页与阅读页
node scripts/build-knowledge-html.mjs --check   # 只校验生成物是否最新
node scripts/check-consistency.mjs              # 表格、链接、版本与中英数字
```

CI 会依次执行一致性校验、生成物比对与七个 Python 自测；任一步失败即拒绝合并。

## 资料来源

| 类型 | 内容 |
|---|---|
| 电力现货 | 《电力现货市场101问》（国调中心组编，中国电力出版社 2021）、《电力现货市场实务》（国调中心组编，中国电力出版社 2023） |
| 市场经济学 | 《电力系统经济学原理》（Kirschen & Strbac，朱治中译）、《经济学原理》微观/宏观分册（曼昆） |
| 虚拟电厂 | 《走近虚拟电厂》（王鹏、王冬容等，机械工业出版社 2020） |
| 碳市场与碳管理 | 《中国碳排放权交易实务》（孟早明、葛兴安等）、《碳管理：从零通往碳中和》（汪军） |
| 政策与市场调研 | 发改委、能源局官网文件，各省交易中心与能源局公开数据，公司公告与年报；调研时点 2026-11，逐条注明来源与日期 |

## 几点说明

1. **时效性**：政策类数字整理至 **2026-11-08**；2026 年 9-10 月的现货新规、售电公司管理办法、风险防控办法、信用评价指引仍为征求意见稿，正文已标注状态。引用前以官方最新文件为准。
2. **原创性**：`knowledge/` 下的笔记是对原书内容的主题化摘要与提炼，非原文复制；书籍版权归原作者所有。
3. **非投资建议**：文中的价格判断与测算框架仅供学习研究。
4. **口径纪律**：技能内置"待核实"标注约定与常见误区清单，使用前建议先读 SKILL.md 第 0 章与推理手册章节。

## Roadmap

- [x] 九份技能：电力交易、虚拟电厂、现货报价量化、碳资产管理、储能投资与运营、新能源项目开发与并网、EMS 优化调度、电价与电费优化、售电零售与风险（均为中英双语，后七份附零依赖工具）
- [x] 知识库：通识、现货、电价、新能源、储能、综合能源、碳市场、VPP、索引与调研底稿共 45 个模块，知识中心已改为生成物
- [x] **EMS 优化调度**：独立第七技能，附 96 点调度内核、需量/容量/调频测算与全部算例断言；微网与储能两份底稿的算例已对齐工具
- [x] **电价与电费优化**：独立第八技能，附账单拆分、三种基本电费、闭式最优申报、分时平移与套餐比价工具，锁定 A–H 算例
- [x] **售电零售与风险**：独立第九技能，附套餐全成本定价、客户组合、偏差期望与分位、保函缺口工具，锁定 A–H 算例
- [ ] **2026-12 增量复核**：现货新规定稿、国家 VPP 管理办法、2027 年 136 号文竞价、省份容量电价与招中标价

## 许可证

本仓库内容（Markdown 技能文件、知识笔记、调研记录与辅助脚本）采用 [CC BY-NC 4.0](LICENSE) 授权：可署名后自由复制、分发与改编，**不得用于商业用途**。引用或再发布请按 `LICENSE` 中的建议格式署名，并保留来源链接。

*最后更新于 2026-11-08*
