# 碳资产实例包：一省一控排企业的可配置履约切片

> 目录定位：`skills/carbon-asset-expert/instances/` 是**碳履约的样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是"一省 + 一个控排企业 + 一个配额年度/规则版本"的配置包，履约负责人只改 JSON 与 CSV，不改代码。当前一个切片：山东水泥熟料企业 2025 配额年度。

## 1. 为什么要有这一层

引擎层（`tools/compliance.py`、`ccer.py`、`finance.py`、`calendar_tool.py`）回答"配额怎么算、CCER 怎么抵、成本怎么估、日历怎么排"；实例层回答"**这个企业、这个配额年度、这批持仓与价格，缺口多大、CCER 用多少、什么时候买、晚清缴罚多少**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 分配公式、抵销上限、罚则、折现 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省配额方案 + 企业产量/排放 + 持仓 + 价格路径 + 采购风格 | 分配表、履约头寸、策略比较、采购时点、履约日历、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的履约复盘 | 按错误类型索引的案例库 | 未建，需真实清缴记录积累 |

碳履约的私有数据不是机组铭牌，而是**分月产量、核实排放量、配额与 CCER 持仓、成交价与合同价、集团合并履约安排**。实例层把这些挡在本地，只把结构与口径放进仓库。

## 2. 目录结构

```
instances/
├── README.md                              # 本文件：schema、流程、验收
└── shandong-cement-carbon-2025/           # 山东水泥熟料企业，2025 配额年度
    ├── instance.json                      # 唯一配置入口
    ├── run.py                             # 校验 → 分配 → 头寸 → 策略 → 时点 → 日历
    ├── make_demo.py                       # D 级合成数据生成器
    ├── README.md                          # 本实例的命令、产物、基准数字、参数状态
    ├── pitfalls.md                        # 水泥行业碳履约易错点
    ├── data/
    │   ├── production_demo.csv            # 逐月熟料产量
    │   ├── verification_demo.csv          # 年度核实排放量
    │   └── prices_demo.csv                # CEA / CCER 月度价格路径
    └── out/demo/                          # 运行产物（可删除重建）
```

## 3. `instance.json` 六个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-主体-年度`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称；本包为全国碳排放权交易市场（水泥行业） |
| `entity_type` | 主体类型 | 水泥熟料重点排放单位 |
| `rule_version` | 规则版本 | 配额分配方案文号与日期、条例版本；冻结到一个版本 |
| `data_cutoff` | 数据截止日 | 与价格快照、持仓时点一致 |
| `grade` | 整体来源级别 | B/C；合成算例为 D |
| `scope` | 纳入/未纳入科目 | 写清是否含 CBAM、集团合并履约、地方试点配额 |
| `units` | 单位约定 | 排放与配额 tCO2e；产量 t；价格 CNY/t |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成交易或合规建议 |

### 3.2 `rules`：配额、抵销、清缴与价格

每个规则子块都必须带 `grade` 和 `source`，缺一个就拒绝运行：

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `allocation` | 免费分配方法 | `method`、`benchmark_tco2_per_t_clinker`、`correction_factor`、`surplus_cap_ratio`、`enforce_surplus_cap` |
| `ccer` | CCER 抵销 | `cap_ratio`（5%）、`cap_base`（核实排放量）、`status` |
| `settlement` | 清缴、结转与罚则 | `surrender_deadline`、`carryover_year`、`penalty_multiple_low/high`、`status` |
| `prices` | 价格快照 | `cea_cny_per_t`、`ccer_cny_per_t`、`market_average_cny_per_t`、`price_month` |

三条硬规则：

- **抵销上限按核实排放量，不按缺口**。5% 的基数是应清缴配额对应的核实排放量；缺口小于 5% 时才受缺口约束。
- **罚则基数是未清缴部分**。缺口扣掉可用 CCER 与 CEA 持仓后仍未清缴的量，才按市场均价 5–10 倍计罚。
- **结转年份要写清**。2019–2024 年度配额不得结转，2025/2026 年度可结转；不要把"可结转"套到所有年份。

### 3.3 `facility`：生产设施

| 字段 | 单位 | 说明 |
|---|---|---|
| `name` | — | 企业/基地名称，入库用占位名 |
| `lines[].id` / `name` | — | 生产线唯一标识与名称 |
| `lines[].design_t_per_day` | t/日 | 设计产能，用于检查月产量是否离谱 |
| `grade` / `source` | — | 资产参数通常是私有数据，入库用 D 级占位值 |

### 3.4 `holdings`：配额与 CCER 持仓

| 字段 | 单位 | 说明 |
|---|---|---|
| `cea_2025_t` | tCO2e | 2025 配额年度可用 CEA 持仓 |
| `ccer_t` | t | 可用 CCER 持仓（须在抵销上限内） |
| `grade` / `source` | — | 持仓为私有数据，入库用 D 级占位值 |

### 3.5 `policy`：采购风格档

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 风格档名 | `carbon-compliance-ccer-first-v1` |
| `purchase_mode` | 采购路径 | `ccer_first` / `cea_only` / `break_even` |
| `cea_transaction_cost_cny_per_t` | CEA 交易成本 | 1.0 元/t（D） |
| `ccer_transaction_cost_cny_per_t` | CCER 交易成本 | 2.0 元/t（D） |
| `purchase_timing` | 采购时点规则 | `min_cea_month` / `current_month` |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入 `summary.json` 与复核表。换采购路径就换 `profile_id`，旧产物保留便于横向比较。

### 3.6 `data_contract`：输入契约

| 子块 | 文件 | 内容 |
|---|---|---|
| `production` | `data/production_demo.csv` | 12 个月熟料产量，月份连续 |
| `verification` | `data/verification_demo.csv` | 年度核实排放量，恰好一行 |
| `prices` | `data/prices_demo.csv` | CEA / CCER 月度价格，至少 6 个月，含 `price_month` |

路径相对实例目录；真实数据用绝对路径或仓库外目录。

## 4. 输入格式

### 4.1 产量

```csv
month,clinker_t,note
2025-01,120000,春节检修
```

- 必须 12 行、月份唯一；熟料产量为正；
- 月产量不得超过设计产能 × 当月天数 × 1.2（合理性提示）。

### 4.2 核实排放

```csv
compliance_year,verified_emissions_tco2,verification_body
2025,1430000,合成核查机构
```

- 本包冻结在 2025 配额年度，其他年份直接拒绝；
- 排放强度 = 核实排放 ÷ 熟料产量，必须落在 0.5–1.5 tCO2/t。

### 4.3 价格

```csv
month,cea_cny_per_t,ccer_cny_per_t
2026-01,88.0,80.5
```

- 至少 6 个月、月份唯一、价格为正；
- `rules.prices.price_month` 必须出现在价格表中。

## 5. 填写流程（约 20 分钟）

1. **复制实例目录**：`cp -r instances/shandong-cement-carbon-2025 instances/<省>-<企业>-<年度>`；
2. **改 `meta`**：实例名、省份、市场、规则版本、数据截止日与口径边界；
3. **核对 `rules`**：只填当前生效值，逐块写 `grade` 与 `source`；基准线与盈余上限未核实的，把状态写进 `source`；
4. **填 `facility`**：生产线与设计产能；
5. **填 `holdings`**：CEA 与 CCER 持仓；
6. **选 `policy`**：先沿用 `ccer_first`，跑通后再比较 `cea_only` 与 `break_even`；
7. **替换 CSV**：按第 4 节格式导入产量、核实排放与价格；
8. **跑 `--check-config`**：来源缺失、单位错误、排放强度越界、价格月份缺失会直接报错；
9. **跑一次 `--demo`**：看分配、头寸、五情景、盈亏平衡与采购时点。

## 6. 运行与产物

```bash
# 配置校验 + 来源表
python skills/carbon-asset-expert/instances/shandong-cement-carbon-2025/run.py --check-config

# 合成数据全流程
python skills/carbon-asset-expert/instances/shandong-cement-carbon-2025/run.py --demo

# 换一份配置（数据路径可指向仓库外）
python skills/carbon-asset-expert/instances/shandong-cement-carbon-2025/run.py \
  --instance /path/to/instance.json --out /path/to/out
```

产物（默认 `out/demo/`）：

| 文件 | 内容 |
|---|---|
| `allocation.csv` | 产量、基准线、原始分配、盈余上限、有效分配、强度 |
| `position.json` | 缺口、CCER 上限与用量、CEA 需求与采购量 |
| `cost_scenarios.csv` | 全买 CEA、CCER 优先、盈亏平衡、未清缴 5 倍 / 10 倍 |
| `prices.csv` | CEA / CCER 含交易成本的到岸价 |
| `compliance-2025.ics` | 履约日历（报告、核查、清缴共 7 个节点） |
| `summary.json` | 配置快照、风格指纹、来源表、分配、头寸、情景、时点、日历、警告 |
| `review.md` | 复核表：结论、头寸、策略、盈亏平衡、时点、口径提醒 |

## 7. 配置校验与实际拦截

`run.py` 会拒绝：

- 缺 `meta` 必填项、缺 `rules` / `facility` / `holdings` / `policy` / `data_contract`；
- 任一规则块缺 `grade` 或 `source`，或 `grade` 不是 A/B/C/D 组合；
- 基准线不在合理区间、修正系数越界、盈余上限开关不是布尔；
- CCER 上限基数不是核实排放量；
- 罚则倍数区间倒置；
- 生产线为空、生产线 `id` 重复；
- 采购路径不在 `ccer_first` / `cea_only` / `break_even`；
- 产量不足 12 个月、月份重复或非正、核实排放不是恰好一行、价格不足 6 个月或价格月份缺失。

会打印但**不拦截**的警告：D 级合成数据、基准线与盈余上限为建模假设、清缴截止日为惯例口径、价格会被时点反转、采购时点是事后视角。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉履约台账的人 ~20 分钟；只需改 JSON 与 CSV |
| 运行时间 | 12 个月产量 + 价格路径，单机 < 1 秒 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 口径可复算 | CCER 5% 上限、罚则基数、结转年份均可手算复核 |
| 策略可解释 | CCER 盈亏平衡价 = CEA 到岸价 − CCER 交易成本，差额可归因 |
| 数据本地 | 真实产量、排放、持仓、成交价不上传；仓库只存结构与 D 级样例 |
| 验收口径 | 不看样本内收益；看头寸是否闭合、策略是否可复算、时间点是否合规 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实企业；
- 真实数据用 `--instance/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实企业名、产量、核实排放、持仓、成交价、集团履约安排写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增实例

1. 选一个**配额方案与清缴要求已明确**的行业与省份；
2. 复制本实例，保留 `run.py` 的校验骨架，改分配方法、基准线、抵销与罚则；
3. 新建 `instance.json`，六个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本行业易错点（基准线、强度修正、盈余上限、抵销基数、罚则基数、结转）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

## 11. 相关入口

- 碳资产方法正文：[`../SKILL.md`](../SKILL.md) 配额分配、抵销、清缴与罚则章节
- 碳资产实务：[`knowledge/碳资产实务-2026-11.md`](../../../knowledge/碳资产实务-2026-11.md)
- 全国碳市场与 CCER 衔接：[`knowledge/绿证-CCER-CBAM衔接-2026-11.md`](../../../knowledge/绿证-CCER-CBAM衔接-2026-11.md)
- 山东市场档案：[`knowledge/山东电力市场-2026-11.md`](../../../knowledge/山东电力市场-2026-11.md)
- 山东水泥样板：[`shandong-cement-carbon-2025/README.md`](shandong-cement-carbon-2025/README.md)
