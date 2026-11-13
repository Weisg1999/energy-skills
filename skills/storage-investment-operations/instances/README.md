# 储能资产实例包：一省一电站的可配置投决与运营切片

> 目录定位：`skills/storage-investment-operations/instances/` 是**储能资产侧的样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区 / 9 技能计数。每个子目录是"一省 + 一个储能主体 + 一个规则版本"的配置包，投资与运营人员只改 JSON 与 CSV，不改代码。

## 1. 为什么要有这一层

引擎层（`tools/stacking.py`、`finance.py`）回答"容量电费怎么折算、套利怎么估、NPV/IRR/LCOS 怎么算"；实例层回答"**你这个省、这个电站、这个容量电价版本，2/4/6 h 哪个时长更值、可用率考核扣多少、十五年现金流长什么样**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 公式、算法、合成算例 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省规则 + 资产参数 + 风格档 + 数据契约 | 时长阶梯、情景收益、可用率考核、现金流、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的项目复盘 | 按错误类型索引的案例库 | 暂未建，需真实项目积累 |

本目录与现货实例层（[`skills/spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)）、售电实例层（[`skills/retail-electricity-risk/instances/`](../../retail-electricity-risk/instances/README.md)）、VPP 实例层（[`skills/virtual-power-plant/instances/`](../../virtual-power-plant/instances/README.md)）平行：现货层回答"明天怎么报"，本层回答"这个项目该不该投、投几年、什么时长"。

## 2. 目录结构

```
instances/
├── README.md                               # 本文件：schema、填写流程、验收
└── anhui-storage-2027/                     # 第一个样板：安徽电网侧独立新型储能
    ├── instance.json                       # 唯一配置入口
    ├── run.py                              # 运行器（校验 → 时长阶梯 → 情景套利 → 考核 → 财务 → 复核）
    ├── make_demo.py                        # D 级合成情景与月度可用率生成器
    ├── README.md                           # 本实例的命令、产物、基准数字、参数状态
    ├── pitfalls.md                         # 安徽容量电价与现货易错点
    ├── data/                               # 年度情景与月度可用率（演示为合成）
    └── out/demo/                           # 运行产物（可删除重建）
```

## 3. `instance.json` 六个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-资产-年月`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称；安徽要区分"容量电价"与"现货" |
| `entity_type` | 主体类型 | 电网侧独立新型储能 / 新能源配储 / 用户侧储能 |
| `rule_version` | 规则版本与生效日 | 冻结到一个版本；容量电价与现货版本分开写 |
| `data_cutoff` | 本包数据截止日 | 与情景、可用率样本的时点一致 |
| `grade` | 整体来源级别 | `D` 表示合成样板 |
| `scope` | 纳入/未纳入科目 | 必须写清是否含辅助服务、容量租赁、绿证、税费优惠 |
| `units` | 单位约定 | 功率 MW、能量 MWh、电价 **CNY/MWh**、容量电价 **CNY/kW·年**、96 点 / 15 分钟 |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成投资建议 |

容量电价用 `CNY/kW·年`，现货用 `CNY/MWh`，两者不能直接相加；复核表先算容量电费毛额，再扣考核，再与套利净额分列。

### 3.2 `rules`：省级规则与来源

每个规则子块都必须带 `grade` 和 `source`，缺一个就拒绝运行。安徽包识别四块：

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `spot` | 现货背景与限价 | `market_time_unit_min`、`points_per_day`、`declare_floor/cap`、`clear_floor/cap`、`status` |
| `capacity` | 容量电价与考核 | `price_cny_per_kw_year`、`denominator_hours`、`duration_conversion_cny_per_kw_year`、`effective_from`、`assessment.output_threshold_ratio`、`assessment.strike_limit` |
| `participation` | 储能参与方式 | `requirement` |
| `settlement` | 结算与分摊 | `basis`、`cycle`、`note` |

三条硬规则：

- **容量电价是含税标准，不是净收益**。165 元/kW·年先按 `min(时长/6, 1)` 折算，再扣可用率考核与运营成本，才能进现金流。
- **限价未核实就留空**。安徽现货申报/出清限价未核到正式数值，四个字段写 `null`，运行器只校验非负与顺序，不套外省限价，并打印警告。
- **阶梯扣减比例未核实不编**。526 号只给"3 次未达标全额扣减"的原则，月度阶梯公式是 D 级简化，复核表必须标注。

### 3.3 `asset`：资产参数

| 字段 | 含义 | 校验 |
|---|---|---|
| `power_mw` | 额定功率 | >0 |
| `energy_mwh` / `usable_energy_mwh` | 铭牌能量 / 可用能量 | 可用能量 = 能量 × (SOC 上限 − 下限) |
| `rte` | 系统往返效率 | (0, 1] |
| `soc_min` / `soc_max` / `soc_init` | SOC 窗口与初值 | 下限 < 上限 |
| `degradation_cny_per_mwh_throughput` | 度电退化成本 | ≥0 |
| `fixed_opex_cny_per_year` | 年固定运维 | ≥0 |
| `capex_cny_per_kwh` | 单位投资 | >0；2/4/6 h 阶梯按能量同比例放大 |
| `project_years` / `discount_rate` / `tax_rate` | 财务假设 | 年数 ≥1，折现率与税率在 [0,1] |
| `availability` | 年度可用率 | [0,1] |

真实项目按铭牌、EPC 合同与运维台账填写；演示的 100 MW / 400 MWh / 450 元/kWh 是 D 级占位，不是市场报价。

### 3.4 `policy`：投资与报价风格档

| 字段 | 含义 | 要求 |
|---|---|---|
| `profile_id` | 风格名 | 改名并保留旧文件，便于比较 |
| `cycles_per_day` / `operating_days` | 日循环与年运行天数 | 循环上限于运行器 |
| `charge_price_quantile` / `discharge_price_quantile` | 充放电取价分位 | [0,1]；必须成对使用，不跨情景混用 |
| `duration_h` | 基准时长 | 必须是 2/4/6 h 之一 |
| `scenario_cvar_confidence` | CVaR 置信度 | (0,1) |

`policy` 块规范化 JSON 的 SHA-1 前 12 位作为**风格指纹**写入复核表。比较两个项目时先看指纹：指纹不同，差异首先归因于风格；指纹相同，才归因于资源、价格或规则。

### 3.5 `contracts`：容量清单与租赁

| 子块 | 内容 |
|---|---|
| `capacity_listing` | 是否进入省级容量电价清单；`listed=false` 时不得计入容量电费 |
| `lease` | 容量租赁是否纳入；v1 不纳入，避免与容量电价重复计算 |

### 3.6 `data_contract`：输入契约

| 子块 | 文件 | 内容 |
|---|---|---|
| `scenarios` | `data/scenarios_demo.csv` | 年度情景：`scenario, charge_price, discharge_price, weight`；权重合计为 1 |
| `assessment` | `data/assessment_demo.csv` | 月度可用率：`month, availability_ratio`；12 个月 |

路径相对实例目录；真实数据用绝对路径或仓库外目录。

## 4. 输入格式

### 4.1 年度情景

```csv
scenario,charge_price,discharge_price,weight
S1,180.0,520.0,0.2
S2,220.0,560.0,0.2
```

- 充、放电价在**同一情景内成对使用**，不允许把低价情景的充电价与高价情景的放电价拼在一起；
- 权重之和必须为 1；价格单位 CNY/MWh；
- 情景数量由 `data_contract.scenarios.scenario_count` 固定为 5（本样板约定，可随新包调整）。

### 4.2 月度可用率

```csv
month,availability_ratio
2027-01,0.985
2027-02,0.990
```

- `month` 为 `YYYY-MM`，覆盖 12 个月；
- 可用率在 [0,1]；低于 98% 的月份按 D 级公式扣减容量电费；
- 累计 3 次未达标触发全额扣减，复核表打印剩余次数。

## 5. 填写流程（约 30 分钟）

1. **复制实例目录**：`cp -r instances/anhui-storage-2027 instances/<省>-<资产>-<年月>`；
2. **改 `meta`**：实例名、省份、主体类型、规则版本、数据截止日与口径边界；
3. **核对 `rules`**：容量电价、分母时长、折算阶梯、执行日期、可用率门槛与三振上限逐项写 `grade` 与 `source`；限价未核实就留 `null`；
4. **填 `asset`**：按铭牌与合同填功率、能量、可用能量、RTE、SOC 窗口、退化、运维、单位投资与财务假设；
5. **选 `policy`**：先沿用 `anhui-capacity-balanced-v1`，跑通后再调循环、取价分位与基准时长；
6. **替换 CSV**：按第 4 节格式导出 5 个年度情景与 12 个月可用率；
7. **跑 `--check-config`**：容量电价、分母、折算值、可用能量与 SOC 窗口不一致会直接报错；
8. **跑一次 `--demo`**：看时长阶梯、考核扣减、NPV/IRR/LCOS 与现金流。

## 6. 运行与产物

```bash
# 只校验配置，打印来源表与警告
python skills/storage-investment-operations/instances/anhui-storage-2027/run.py --check-config

# 用自带 D 级合成数据跑全流程
python skills/storage-investment-operations/instances/anhui-storage-2027/run.py --demo

# 用自己的数据（路径指向仓库外）
python skills/storage-investment-operations/instances/anhui-storage-2027/run.py \
  --scenarios /path/to/scenarios.csv --assessment /path/to/assessment.csv \
  --out /path/to/out
```

产物（默认 `out/demo/`）：

| 文件 | 内容 |
|---|---|
| `duration_ladder.csv` | 2/4/6 h：资本开支、容量电费、考核、套利、NPV/IRR/回收期/LCOS |
| `scenario_stack.csv` | 每个情景的套利净额、容量净额与税前运营净额 |
| `assessment.csv` | 月度可用率、相对 98% 的缺口、扣减金额、累计未达标次数 |
| `cashflow.csv` | 15 年项目现金流（含折旧与所得税） |
| `summary.json` | 配置快照、风格指纹、情景期望 / CVaR、基准时长指标、警告 |
| `review.md` | 复核表：结论、口径、时长阶梯、情景尾部、考核、改数说明、边界 |

## 7. 配置校验与实际拦截

`run.py` 的 `validate_instance` 会拒绝：

- 缺 `meta` 必填项、缺 `rules`/`asset`/`policy`/`contracts`/`data_contract`；
- 任一规则块缺 `grade` 或 `source`，或 `grade` 不是 A/B/C/D 组合；
- `points_per_day ≠ 24×60 / market_time_unit_min`，或不是 96 点；
- 容量电价不是 165 元/kW·年、分母不是 6 h、2/4/6 h 折算值与线性公式不符、执行日不是 2027-01-01；
- 可用率门槛不在 (0,1]、三振上限 <1；
- 可用能量 ≠ 能量 × (SOC 上限 − 下限)，或超过 24 h 功率能量比；
- `policy.duration_h` 不是 2/4/6 h、分位越界、CVaR 置信不在 (0,1)；
- 情景权重之和不为 1、情景数不是 5、价格字段缺失；
- 月度可用率缺月、越界或重复。

会打印但**不拦截**的警告：D 级合成数据、现货限价未核实、容量考核为 D 级简化公式、容量电费自 2027-01-01 起执行。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉项目与合同的人 ~30 分钟；只需改 JSON 与 CSV |
| 运行时间 | 3 个时长 × 5 个情景，单机 < 1 分钟 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` 或留空 |
| 口径分账 | 容量电费毛额、考核扣减、套利净额、运营净额、现金流分列，不混算 |
| 财务指标 | NPV/IRR/回收期/LCOS 可复算，折现率与税率写入配置 |
| 数据本地 | 真实电站、合同、结算数据不上传，仓库只存结构与 D 级样例 |
| 验收口径 | 不看绝对收益高低；看流程是否跑通、口径是否可复现、假设是否可追溯 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实电站或收益；
- 真实数据用 `--scenarios/--assessment/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实电站名称、并网点、EPC 报价、运维合同与结算单写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增实例

1. 选一个**已正式运行、规则版本稳定**的省份与储能主体；
2. 复制 `anhui-storage-2027/` 的 `run.py`、`make_demo.py`，改省份规则、资产与复核表标题；
3. 新建 `instance.json`，六个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本省易错点（容量电价单位、分母时长、可用率考核、现货限价、租赁与容量电价重复计算）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

## 11. 相关入口

- 储能投资方法正文：[`../SKILL.md`](../SKILL.md) §2 容量电价、§3 收益堆叠、§4 财务指标
- 安徽容量电价与现货：[`../../../knowledge/安徽电力市场-2026-11.md`](../../../knowledge/安徽电力市场-2026-11.md)
- 储能收益堆叠与数据源：[`../../../knowledge/储能收益建模与数据源-2026-11.md`](../../../knowledge/储能收益建模与数据源-2026-11.md)
- 现货实例层（交易侧对照）：[`skills/spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)
