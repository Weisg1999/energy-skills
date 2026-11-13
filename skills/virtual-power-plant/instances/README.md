# 虚拟电厂实例包：一省一聚合商的可配置响应切片

> 目录定位：`skills/virtual-power-plant/instances/` 是**邀约型 VPP 的样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是"一省 + 一个聚合商 + 一个规则版本"的配置包，聚合商的交易人员只改 JSON 与 CSV，不改代码。当前三个切片：上海 407号"1+5"、浙江 VPP 2.0（公告〔2026〕第7号）、江苏负荷快速响应（苏发改规发〔2026〕1号）。

## 1. 为什么要有这一层

引擎层（`tools/aggregation.py`、`cbl.py`、`dispatch.py`、`finance.py`）回答"可调能力怎么折算、基线怎么算、响应怎么认定、收益怎么估"；实例层回答"**你这个省、这批资源、这套合同、这个报价风格，下一次邀约报多少、中了怎么交付、T+1 差在哪**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 公式、算法、合成算例 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省规则 + 资源组合 + 合同 + 风格档 + 数据契约 | 申报表、情景出清、T+1 响应认定、差异桥、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的邀约复盘 | 按错误类型索引的案例库 | 暂未建，需真实邀约积累 |

邀约型 VPP 的私有数据不是机组铭牌，而是**用户可中断能力、基线历史、响应率、分成合同、计量点位与违约条款**。实例层把这些挡在本地，只把结构与口径放进仓库。

本目录与现货实例层（[`skills/spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)）、售电实例层（[`skills/retail-electricity-risk/instances/`](../../retail-electricity-risk/instances/README.md)）平行：那边的主体是储能/新能源或售电公司，配置块分别用 `asset`、`portfolio`；这边的主体是**负荷聚合商**，配置块用 `resources`，并多出"响应认定、超额封顶、客户分成、未达标补偿"四块。

## 2. 目录结构

```
instances/
├── README.md                               # 本文件：schema、填写流程、验收
├── shanghai-vpp-2026-11/                   # 上海用户侧 VPP（沪经信运〔2025〕407号"1+5"）
├── zhejiang-vpp2-2026-11/                  # 浙江 VPP 2.0（公告〔2026〕第7号，2026-09-23）
└── jiangsu-fast-response-2026-11/          # 江苏负荷快速响应聚合商（苏发改规发〔2026〕1号）
```

三个包目录结构相同，每个包含：

```
    ├── instance.json                       # 唯一配置入口
    ├── run.py                              # 运行器（校验 → 申报/结算 → T+1 复盘 → 复核）
    ├── make_demo.py                        # D 级合成数据生成器
    ├── README.md                           # 本实例的命令、产物、基准数字、参数状态
    ├── pitfalls.md                         # 本省易错点
    ├── data/                               # 历史基线/邀约/计量（演示为合成）
    └── out/demo/                           # 运行产物（可删除重建）
```

### 2.1 三个切片的分工

| 包 | 主体与资源 | 规则主线 | 运行链 | 结算重点 |
|---|---|---|---|---|
| `shanghai-vpp-2026-11/` | 用户侧聚合商，五类资源 | 407号"1+5"目标 110/160/220 万 kW；2025-08 调用 116.27 万 kW | 5 日基线 → 组合能力 → 情景申报 → T+1 认定 → 5 科目差异桥 | 响应量认定、超额封顶、客户分成、未达标让利 |
| `zhejiang-vpp2-2026-11/` | 三类聚合单元：发电 / 储能 / 负荷 | 公告〔2026〕第7号：单元 ≥5 MW/≥1 h；正调节 800/1000/1200、负调节 300/350/380 元/MW | 门槛校验 → 逐次调用结算 → 考核封顶 → 快速型准备费 → 月度评级 | 有效响应 70%、考核不超过补偿 1.2 倍、评级 3:7、快速型无效 ≥3 次准备费归零 |
| `jiangsu-fast-response-2026-11/` | 直控 / 自控两类资源的负荷聚合商 | 苏发改规发〔2026〕1号：直控上限 15 元/kWh、超额 150%；自控 10 元/kWh、超额 120% | 可调能力与申报 → 情景出清 → T+1 响应认定 → 11 科目差异桥 | 0.5 h 调整、120%/150% 封顶、客户分成、未达标补偿 |

三包都用 96 点 / 15 分钟；字段名与规则块不同，runner 只校验本包声明的块（上海 `vpp_plan`/`baseline`/`event`/`settlement`，浙江 `vpp2`/`baseline`/`spot`/`settlement`，江苏 `fast_response`/`baseline`/`spot`/`settlement`）。

## 3. `instance.json` 六个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-主体-年月`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称；江苏要区分"需求响应"与"现货" |
| `entity_type` | 主体类型 | 负荷聚合商 / 虚拟电厂运营商 / 综合能源服务商 |
| `rule_version` | 规则版本与生效日 | 冻结到一个版本；跨版本要切段 |
| `data_cutoff` | 本包数据截止日 | 与邀约数据、基线样本的时点一致 |
| `grade` | 整体来源级别 | `D` 表示合成样板 |
| `scope` | 纳入/未纳入科目 | 必须写清是否含考核罚款、现货、辅助服务、容量补偿 |
| `units` | 单位约定 | 功率 MW、电量 MWh、激励价 **CNY/kWh**、负荷 MW、时段 0–95；换算 `1 CNY/kWh = 1000 CNY/MWh` |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成报价建议 |

激励价用 `CNY/kWh` 是因为江苏快响规则原文以"元/kWh"申报（直控 15、自控 10）。不要把它改成 `CNY/MWh` 后再和规则上限比较，15 元/kWh = 15,000 元/MWh，量级差 1000 倍。

### 3.2 `rules`：省级规则与来源

每个规则子块都必须带 `grade` 和 `source`，缺一个就拒绝运行。各包块名不同，下表以江苏快响为例（上海、浙江的字段见各自 `instance.json` 与实例 README）：

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `fast_response` | 产品、申报上限、超额封顶、出清、测试 | `products.direct/self.bid_cap_cny_per_kwh`、`overshoot_cap_ratio`、`ramp_time_h`、`event_duration_h`、`min_response_rate`、`no_double_participation`、`test` |
| `baseline` | 基线算法 | `method`、`weekday_days`、`weekend_days`、`lower_ratio`、`upper_ratio`、`aggregation`、`status` |
| `spot` | 现货背景（本包不参与） | `status`、`clear_floor/cap`、`included` |
| `settlement` | 结算与资金 | `incentive_formula`、`funding`、`cycle`、`status` |

三条硬规则：

- **上限是申报天花板，不是结算价**。15/10 元/kWh 只约束报价；实际到手 = 出清价 × 实际响应负荷 × 时长，再按 150%/120% 封顶。
- **0.5 h 是调整时间**。1号文明确"0.5 h 内完成功率调整"；单次事件持续多久、结算按几个小时，方案未明确写死，实例必须把 `event_duration_h` 单列并标状态，不能把两者混为一谈。
- **未核实的算法不编**。江苏快响 1号文没有给出完整基线算法，`baseline.status` 必须写"按 2025 需求响应细则口径、待与快响方案/协议原文核对"，并标 `B/C`。

### 3.3 `resources`：资源组合（替代现货实例的 `asset`）

| 字段 | 单位 | 说明 |
|---|---|---|
| `items[].id` | — | 资源唯一标识，与 CSV 列名一一对应 |
| `items[].name` | — | 资源名称，同一实例内不重复 |
| `items[].control_type` | — | `direct`（直控型）或 `self`（自控型） |
| `items[].max_mw` | MW | 资源额定/最大可调功率 |
| `items[].adjustable_ratio` | — | 可中断/可调比例（如工业 0.50、空调 0.30） |
| `items[].availability` | — | 可用率（0–1），与同时率分开 |
| `items[].customer_share` | — | 客户分成比例（0–1），聚合商留存 `1 − customer_share` |
| `items[].allow_negative_load` | — | 是否允许净受电负荷为负（用户侧储能放电时为 `true`） |
| `items[].other_market_commitment` | — | 同一时段是否已承诺现货/辅助服务；为 `true` 时不得计入可调能力 |
| `items[].load_field` | — | 历史与 T+1 CSV 中的负荷列名 |
| `items[].grade` / `source` | — | 资源参数的来源级别与依据 |

可调能力 = `max_mw × adjustable_ratio × availability`，**不是**额定功率，也**不是**申报值。申报值 = 可调能力 × 风格档 `bid_ratio`，再向下取整到 `declaration_rounding_mw`。三层口径必须分开：

| 口径 | 计算 | 用途 |
|---|---|---|
| 可调能力 | 额定 × 可调比例 × 可用率 | 资源盘点、方案上限 |
| 申报值 | 可调能力 × 申报比例（取整） | 报给交易/邀约平台 |
| 实际响应 | 基线 − 实际负荷（计量） | 结算与考核 |

### 3.4 `policy`：报价风格档

风格是聚合商的选择，不是事实。同一批资源换风格档，申报量与报价就不同；复盘时必须能区分"风格造成的差异"与"执行造成的差异"。

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 风格档名 | `jiangsu-fast-response-balanced-v1` |
| `bid_ratio` | 各控制类型的申报比例 | 直控 0.85 / 自控 0.80 |
| `bid_price_cny_per_kwh` | 各控制类型的报价 | 必须 ≤ 对应上限 |
| `declaration_rounding_mw` | 申报量向下取整粒度 | 0.1 MW |
| `planned_delivery_ratio` | 计划执行率 | 0.95（用于计划收益与差异桥） |
| `scenario_cvar_confidence` | 情景 CVaR 置信度 | 0.80 |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入 `summary.json` 与复核表。比较两次邀约时先看指纹：指纹不同，差异首先归因于风格；指纹相同，才归因于预测、执行或规则。

### 3.5 `contracts`：客户分成、未达标补偿与运营成本

| 字段 | 说明 |
|---|---|
| `shortfall.delivery_threshold` | 执行率低于此值触发客户补偿 |
| `shortfall.extra_customer_share` | 触发后额外让给客户的分成比例 |
| `opex.variable_cny_per_mwh` | 按实际响应电量计的可变运营成本 |
| `opex.fixed_cny_per_event` | 每次邀约的固定成本（值守、通信、核验） |
| `grade` / `source` | 合同条款与成本参数的来源级别 |

分成比例放在 `resources[].customer_share`（按资源差异化），未达标补偿放在 `contracts.shortfall`。不要把两者混成一个"平均分成"数字，否则差异桥无法归因到具体资源。

### 3.6 `data_contract`：输入契约

下表是江苏/上海包的基线+邀约+T+1 形态；浙江包改用 `events`（逐次调用）与 `response`（各单元实际响应）两份输入，字段见其 `data_contract` 与实例 README。

| 子块 | 文件 | 内容 |
|---|---|---|
| `history` | `data/history_demo.csv` | 近 5 个工作日（或 3 个非工作日）× 96 点 × 各资源负荷，用于基线 |
| `event` | `data/event_demo.csv` | 邀约情景：控制类型、事件时段、需求 MW、边际出清价 |
| `t1_loads` | `data/t1_loads_demo.csv` | T+1 实际负荷（96 点），用于响应量认定 |
| `t1_event` | `data/t1_event_demo.csv` | T+1 实际出清价与中标 MW（按控制类型） |

路径相对实例目录；真实数据用绝对路径或仓库外目录。

## 4. 输入格式

以下三小节是江苏/上海包的基线+情景+T+1 格式；浙江包的两份输入（`events` / `response`）见该包 README 第 1–2 节。

### 4.1 历史基线（6 日 × 96 点）

```csv
date,slot,start,end,industrial_direct_mw,storage_direct_mw,hvac_direct_mw,industrial_self_mw
2026-07-08,0,00:00,00:15,18.000000,0.000000,1.200000,16.000000
```

- 建议给出 5+3 日；runner 取最近 `count` 日，剔除日电量低于均值 25% 或高于 200% 的异常日；
- 同一资源各日点数一致；负荷列名与 `resources[].load_field` 一致；
- 用户侧储能允许负值（放电），其余资源默认非负；
- 事件当日不得混入历史样本。

### 4.2 邀约情景

```csv
scenario,control_type,event_date,event_start,event_end,required_mw,marginal_price_cny_per_kwh
s1,direct,2026-07-15,19:00,19:30,20.0,13.0
s1,self,2026-07-15,19:00,19:30,6.0,8.8
```

- 情景权重在 `data_contract.event.scenario_weights`，总和必须为 1；
- `marginal_price` 是情景下的边际出清价，不是本聚合商报价；
- 同一情景内各控制类型的事件时段必须一致；
- 事件时长必须等于 `rules.fast_response.event_duration_h × 60` 分钟，且落在 15 分钟整数倍上。

### 4.3 T+1 实际负荷与出清结果

```csv
date,slot,start,end,industrial_direct_mw,storage_direct_mw,hvac_direct_mw,industrial_self_mw
2026-07-15,76,19:00,19:15,17.460000,-9.500000,1.840000,15.200000
```

```csv
control_type,event_date,event_start,event_end,cleared_price_cny_per_kwh,awarded_mw
direct,2026-07-15,19:00,19:30,13.8,26.0
self,2026-07-15,19:00,19:30,9.6,8.6
```

- T+1 负荷必须覆盖整个事件窗口；
- 中标 MW 不得超过申报值（超发按封顶比例计，不是按中标量计）；
- 没有 T+1 数据时只出申报表与情景表，不跑响应认定与差异桥（省略 `--t1-loads` / `--t1-event`）。

## 5. 填写流程（约 30 分钟）

1. **复制实例目录**：`cp -r instances/jiangsu-fast-response-2026-11 instances/<省>-<聚合商>-<年月>`；
2. **改 `meta`**：实例名、省份、主体类型、规则版本、数据截止日与口径边界；
3. **核对 `rules`**：只填当前生效值，逐块写 `grade` 与 `source`；基线算法未核实的，把状态写进 `baseline.status`；
4. **填 `resources`**：按用户台账填额定、可调比例、可用率、分成与计量列名；同一时段已承诺其他市场的资源标 `other_market_commitment: true`，不计入能力；
5. **填 `contracts`**：未达标补偿门槛、额外分成、可变/固定运营成本；
6. **选 `policy`**：先沿用所复制包的 `profile_id`，跑通后再调申报比例与报价；
7. **替换 CSV**：按第 4 节格式导出历史基线、邀约情景、T+1 实际；
8. **跑 `--check-config`**：来源缺失、单位错误、报价超上限、申报超能力、资源重名会直接报错；
9. **跑一次 `--demo`**：看申报表、情景出清、T+1 响应认定与差异桥残差。

## 6. 运行与产物

```bash
# 三个包各自校验与演示（<pack> = shanghai-vpp-2026-11 / zhejiang-vpp2-2026-11 / jiangsu-fast-response-2026-11）
python skills/virtual-power-plant/instances/<pack>/run.py --check-config
python skills/virtual-power-plant/instances/<pack>/run.py --demo

# 用自己的数据（以江苏包为例，路径指向仓库外）
python skills/virtual-power-plant/instances/jiangsu-fast-response-2026-11/run.py \
  --history /path/to/history.csv --event /path/to/event.csv \
  --t1-loads /path/to/t1_loads.csv --t1-event /path/to/t1_event.csv \
  --out /path/to/out
```

`--history/--event/--t1-loads/--t1-event` 是上海与江苏包的输入；浙江包用 `--events` 与 `--response`，详见该包 README。

产物（默认 `out/demo/`，下表为江苏包；上海包为 `baseline.csv`/`bid.csv`/`scenarios.csv`/`t1_bridge.csv`，浙江包为 `unit_capability.csv`/`events.csv`/`rating.csv`）：

| 文件 | 内容 |
|---|---|
| `bid_sheet.csv` | 按控制类型的可调能力、申报 MW、报价、上限、剩余空间 |
| `scenario_table.csv` | 各情景的出清与否、中标 MW、激励毛收入、净收益 |
| `delivery_detail.csv` | T+1 各资源在事件窗口的基线、实际、响应量、封顶后计量电量 |
| `summary.json` | 配置快照、风格指纹、申报、情景、T+1 认定、差异桥摘要 |
| `bridge.json` / `bridge.csv` | 差异桥：每类控制类型 5 项 × 2 类 + 总运营成本 1 项，共 11 个科目，残差 < 1e-6 CNY |
| `review.md` | 复核表：来源与警告、申报、情景、响应认定、差异桥、合规清单 |

## 7. 配置校验与实际拦截

`run.py` 的 `validate_instance` 会拒绝：

- 缺 `meta` 必填项、缺 `rules`/`resources`/`policy`/`contracts`/`data_contract`；
- 任一规则块缺 `grade` 或 `source`，或 `grade` 不是 A/B/C/D 组合；
- `meta.units.price` 不是 `CNY/kWh`、`meta.units.power` 不是 `MW`；
- `points_per_day ≠ 24×60 / market_time_unit_min`；
- `products.direct/self` 缺上限或封顶比例，封顶比例不在 `[1.0, 3.0]`；
- 资源 `control_type` 未知、`max_mw`/`adjustable_ratio`/`availability`/`customer_share` 越界；
- 资源重名、`load_field` 重复或缺失；
- 同一资源 `other_market_commitment=true` 却仍被计入能力（runner 直接排除并告警，不静默计入）；
- 报价超过对应控制类型的申报上限；
- 申报量超过可调能力；
- 事件时长与 `event_duration_h` 不一致、时段不在 15 分钟整数倍；
- 情景权重之和不为 1、权重数与情景数不一致；
- T+1 事件中标量超过申报值、T+1 负荷缺事件时段。

输入数据还会拒绝：历史样本不足 3 日、同一天重复、缺时段、负荷列非数值、非储能资源出现负负荷、事件当日混入历史。

会打印但**不拦截**的警告：D 级合成数据、快响基线算法待核、事件时长是 D 级假设、直控/自控是否同场出清待核、响应率门槛按 2025 细则口径、报价接近上限。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉用户与合同的人 ~30 分钟；只需改 JSON 与 CSV |
| 运行时间 | 3 情景 × 2 控制类型，单机 < 1 分钟 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 差异桥 | 残差 < 1e-6 CNY；上海 5 科目、江苏 11 科目可归因；浙江包不做差异桥，改为逐次结算与月度评级 |
| 响应认定 | 基线、申报、实际三层口径分列；超额封顶可复算 |
| 数据本地 | 真实用户、合同、计量数据不上传，仓库只存结构与 D 级样例 |
| 验收口径 | 不看样本内收益；看流程是否跑通、口径是否可复现、差异是否可归因 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实用户或聚合商；
- 真实数据用 `--history/--event/--t1-loads/--t1-event/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实用户名称、可中断设备清单、基线曲线、分成合同、违约条款写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增实例

1. 选一个**已正式运行、规则版本稳定**的省份与聚合主体；
2. 复制**结构最接近**的实例目录（基线+邀约+T+1 型复制上海或江苏包，逐次调用+评级型复制浙江包），改 `run.py`、`make_demo.py` 与复核表标题；
3. 新建 `instance.json`，六个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本省易错点（上限单位、响应时间与事件时长、基线算法、封顶比例、重复参与、评级与准备费）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

## 11. 相关入口

- VPP 方法正文：[`../SKILL.md`](../SKILL.md) §11.2 运营实务、§12 公式速查
- 需求响应规则与基线：[`knowledge/需求响应、车网互动与灵活性资源-2026-11.md`](../../../knowledge/需求响应、车网互动与灵活性资源-2026-11.md) §4–§6
- VPP 商业模式与聚合：[`knowledge/虚拟电厂聚合调度与商业模式-2026-11.md`](../../../knowledge/虚拟电厂聚合调度与商业模式-2026-11.md)
- 现货实例层：[`skills/spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)
- 售电实例层：[`skills/retail-electricity-risk/instances/`](../../retail-electricity-risk/instances/README.md)
- 江苏快响样板：[`jiangsu-fast-response-2026-11/README.md`](jiangsu-fast-response-2026-11/README.md)
