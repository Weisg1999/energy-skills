# 实例包：一省一主体的可配置交易切片

> 目录定位：`skills/spot-bidding-quant/instances/` 是**样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是一个"一省 + 一主体 + 一个规则版本"的配置包，交易员只改 JSON 和 CSV，不改代码。

## 1. 为什么要有这一层

引擎层（`tools/desk.py`、`tools/bid.py`、`tools/forecast.py`）回答"方法是什么"；实例层回答"**你这个省、这个资产、这套规则、这个交易风格，明天报什么**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 公式、算法、合成算例 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省规则 + 资产参数 + 风格档 + 数据契约 | 申报表、差异桥、复盘表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的 T+1 复盘 | 按错误类型索引的案例库 | 暂未建，需 2–3 周真实复盘积累 |

引擎层给的是通用结论；真实交易价值在私有数据（成本、合约、检修、弃电、人脉）里。实例层的作用是把私有数据挡在本地，只把**结构与口径**放进仓库。

## 2. 目录结构

```
instances/
├── README.md                       # 本文件：schema、填写流程、验收
└── shandong-storage-2026-11/       # 第一个样板：山东独立储能
    ├── instance.json               # 唯一配置入口
    ├── run.py                      # 运行器（配置校验 → 申报 → 差异桥 → 复盘）
    ├── make_demo.py                # D 级合成演示数据生成器
    ├── README.md                   # 本实例的填写表、命令、参数状态
    ├── pitfalls.md                 # 本省易错点
    ├── data/                       # D-1 / T+1 输入（演示为合成）
    └── out/demo/                   # 运行产物（可删除重建）
```

## 3. `instance.json` 六个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-主体-年月`，与目录同名 |
| `province` / `market` | 省份与市场 | 市场写全称，避免"山东现货"这种含糊口径 |
| `entity_type` | 主体类型 | 独立新型储能 / 新能源 / 售电公司 / VPP |
| `rule_version` | 规则版本与生效日 | 必须冻结到一个版本；跨版本要切段 |
| `data_cutoff` | 本包数据截止日 | 与 D-1 输入的发布时点一致 |
| `grade` | 整体来源级别 | A/B/C/D；`D` 表示合成样板 |
| `scope` | 纳入/未纳入的品种 | 写清边界，防止把占位当完整结算 |
| `units` | 单位约定 | 功率 MW、电量 MWh、价格 CNY/MWh、时段 0–95 |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成建议 |

### 3.2 `rules`：省级规则与来源

每个规则子块都必须带 `grade` 和 `source`，缺一个配置校验就拒绝运行。当前 runner 识别：

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `spot` | 现货限价、时段粒度 | `market_time_unit_min`、`points_per_day`、申报/出清上下限 |
| `settlement` | 结算口径 | `basis`（分账方式、容量补偿是否单列） |
| `capacity_compensation` | 容量补偿公式 | `formula`、`price_cny_per_kw_year`、`supply_demand_coefficient`、`status` |
| `storage_participation` | 储能参与方式 | `requirement`、`effective_from` |
| `negative_price` | 负价背景 | `hours_2025`、`floor_share_2025` |
| `vpp_threshold` | VPP 门槛（如适用） | `storage_class`，并注明不适用于独立储能本体 |

**规则值必须是"当前生效"版本**。征求意见稿、公示值、草案放独立字段（如 `draft_2026_08_28`）并标 `status`，不得写进生效字段。

### 3.3 `asset`：资产参数

| 字段 | 单位 | 说明 |
|---|---|---|
| `power_mw` | MW | PCS/并网点可用功率 |
| `energy_mwh` | MWh | 铭牌能量 |
| `usable_energy_mwh` | MWh | 必须等于 `energy_mwh × (soc_max − soc_min)`，校验会核对 |
| `rte` | — | 往返效率，内核按 `sqrt(rte)` 拆充放两侧 |
| `soc_min` / `soc_max` / `soc_init` | — | SOC 窗口与初始值 |
| `degradation_cny_per_mwh_throughput` | CNY/MWh | 按吞吐量线性折旧 |
| `fixed_cost_cny_per_day` | CNY/日 | 固定成本分摊（可为 0） |
| `effective_capacity_mw` | MW | 容量补偿的"有效容量"，不等于铭牌 |
| `solver_states` | — | DP 状态数，越大越精确越慢 |
| `grid_connection.import_limit_mw` / `export_limit_mw` | MW | 关口进出口限制 |

资产块通常是**私有数据**。入库版本用占位值并标 `grade: D`；真实参数只放本地覆盖文件，不要提交。

### 3.4 `policy`：交易风格档（与资产参数分离）

风格是交易员的选择，不是事实。同一个资产换风格档，申报曲线就不同；复盘时必须能区分"风格造成的差异"和"预测/执行造成的差异"。

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 风格档名 | `balanced-v1`、`aggressive-spike-v1` |
| `declared_quantity_quantile` | 申报量取情景分位 | 0.3 保守 / 0.5 中性 / 0.7 激进 |
| `price_reference_quantile` | 参考价取情景分位 | 同上 |
| `discharge_markup_cny_per_mwh` | 放电报价加价 | 覆盖预测误差与风险溢价 |
| `charge_markup_cny_per_mwh` | 充电报价压价 | 越低越难中标 |
| `spike_threshold_cny_per_mwh` | 尖峰阈值 | 超过则改用 `spike_markup` |
| `spike_markup_cny_per_mwh` | 尖峰时段加价 | 用低价情景不中标换取高价情景收益 |
| `max_cycles_per_day` | 日循环上限 | 保护电池与考核 |
| `min_daily_spread_cny_per_mwh` | 最小日价差 | 低于此值不出手 |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入复盘表。换风格就换 `profile_id`，旧文件保留，便于横向比较。

### 3.5 `contracts`：合约与 CfD

当前支持固定量固定价的 CfD 覆盖：按 `quantity_mw`（可为标量或 96 点曲线）与 `price` 结算，等价于 `Qc·(Pc − P)`。未配置时按纯现货处理。中长期曲线分解、分时段合约、差价合约的参考点选择留到后续版本。

### 3.6 `data_contract`：输入契约

`d1` 块声明 D-1 情景价格文件的字段、情景列、权重和发布截止时点；`t1` 块声明 T+1 实际价格与计量充放电量。路径相对实例目录，绝对路径用于本地私有数据。

## 4. 输入格式

### 4.1 D-1（96 点 × 5 情景）

```csv
date,slot,start,end,price_s1,price_s2,price_s3,price_s4,price_s5
2026-11-18,0,00:00,00:15,283.0,300.0,330.0,360.0,390.0
```

- 只能有一个交易日；`slot` 必须 0–95 连续无缺口；
- 价格列名与 `scenario_fields` 一致，权重之和为 1；
- 情景可以来自分位数（P10/P25/P50/P75/P90）、集合预报成员或人工情景，但**必须是 D-1 截止前可得的**。

### 4.2 T+1（实际结算价与计量电量）

```csv
date,slot,actual_price,actual_discharge_mw,actual_charge_mw
2026-11-18,0,310.0,0.0,42.5
```

- 同一交易日、96 点齐全；
- 充放电量非负，且不得超过 `power_mw`；
- 同一时段不允许同时充放电；
- 没有实际数据时只出申报表，不跑差异桥（`--t1` 省略）。

## 5. 填写流程（约 30 分钟）

1. **复制实例目录**：`cp -r instances/shandong-storage-2026-11 instances/<省>-<主体>-<年月>`；
2. **改 `meta`**：实例名、省份、主体类型、规则版本、数据截止日；
3. **核对 `rules`**：只填当前生效值，逐块写 `grade` 与 `source`；草案值放独立字段；
4. **填 `asset`**：用铭牌与台账；`usable_energy_mwh` 按 SOC 窗口重算；
5. **选 `policy`**：先沿用 `balanced-v1`，跑通后再调分位与加价；
6. **替换 CSV**：按第 4 节格式导出自己的 D-1 情景与 T+1 实际；
7. **跑 `--check-config`**：来源缺失、单位不一致、SOC 窗口非法会直接报错；
8. **跑一次全流程**：看申报摘要、情景 CVaR、差异桥残差是否为 0。

## 6. 运行与产物

```bash
# 只校验配置，打印来源表与警告
python skills/spot-bidding-quant/instances/shandong-storage-2026-11/run.py --check-config

# 用自带 D 级合成数据跑全流程
python skills/spot-bidding-quant/instances/shandong-storage-2026-11/run.py --demo

# 用自己的数据
python skills/spot-bidding-quant/instances/shandong-storage-2026-11/run.py \
  --d1 /path/to/d1.csv --t1 /path/to/t1.csv --out /path/to/out
```

产物（默认 `out/<run>/`）：`bid_sheet.csv`（96 点申报表）、`summary.json`（配置、情景、评估摘要）、`bridge.json` / `bridge.csv`（T+1 差异桥）、`review.md`（复核表）。

## 7. 配置校验与实际拦截

`run.py` 的 `validate_instance` 会拒绝：

- 缺 `meta` 必填项、缺 `rules`/`asset`/`policy`/`data_contract`；
- 任一规则块缺 `grade` 或 `source`；
- `points_per_day ≠ 24×60 / market_time_unit_min`；
- 限价不满足 `clear_floor ≤ declare_floor < declare_cap ≤ clear_cap`；
- `usable_energy_mwh ≠ energy_mwh × (soc_max − soc_min)`；
- `soc_min ≥ soc_max` 或 `soc_init` 越界；
- 情景权重之和不为 1、情景列数与权重数不一致；
- 合约覆盖超过 1、或合约类型不是 CfD。

输入数据会拒绝：多交易日、缺时段、重复点、价格越界、充放电同时为正、电量超过功率上限。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉规则的人 ~30 分钟；只需改 JSON 与 CSV |
| 运行时间 | 5 情景 × 96 点 DP，单机 < 1 分钟 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 差异桥 | 残差 < 1e-6 CNY，科目可分 |
| 数据本地 | 真实资产/合约/计量数据不上传，仓库只存结构与 D 级样例 |
| 验收口径 | **不看样本内 PnL**；看流程是否跑通、口径是否可复现、差异是否可归因 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实电站；
- 真实数据用 `--d1/--t1/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实成本、合约价、计量曲线、检修计划写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增第二个实例

1. 选一个**已正式运行、规则版本稳定**的省份与主体；
2. 复制本目录的 `run.py` 与 `make_demo.py`（复核表标题与命令行描述目前按山东独立储能写死，校验与算法本身与省份无关；第二个实例复制后改标题即可）；
3. 新建 `instance.json`，六个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本省易错点（限价正负号、口径混用、批次混用、草案当现行）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

第二批已落地：售电侧的广东售电零售实例包见 [`skills/retail-electricity-risk/instances/`](../../retail-electricity-risk/instances/README.md)，配置块用 `portfolio` 替代 `asset`，并增加零售套餐、偏差合同与履约保障。再往后才是配置向导与匿名复盘库。
