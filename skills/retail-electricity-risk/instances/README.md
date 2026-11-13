# 售电零售实例包：一省一售电公司的可配置切片

> 目录定位：`skills/retail-electricity-risk/instances/` 是**售电侧的样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是"一省 + 一个售电公司 + 一个规则版本"的配置包，售电公司的交易/结算人员只改 JSON 与 CSV，不改代码。
>
> 当前有两个纵切片：广东 2026-11（固定价 + 市场联动）与江苏 2027（批发价传导 + 一户一价封顶）。两者共用同一套目录约定，但套餐模型不同，见 §3.2。

## 1. 为什么要有这一层

引擎层（`tools/package.py`、`portfolio.py`、`deviation.py`、`guarantee.py`）回答"套餐怎么定价、偏差怎么计量、保函怎么算"；实例层回答"**你这个省、这批客户、这套合同、这个交易风格，明天报什么价、买多少电、T+1 差在哪**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 公式、算法、合成算例 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省规则 + 客户组合 + 合同 + 风格档 + 数据契约 | 套餐定价表、购电计划、T+1 差异桥、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的 T+1 复盘 | 按错误类型索引的案例库 | 暂未建，需真实复盘积累 |

售电的私有数据不是机组参数，而是**客户曲线、合同价、偏差考核条款、保函与信用**。实例层把这些挡在本地，只把结构与口径放进仓库。

本目录与现货实例层（[`skills/spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)）平行：那边的主体是储能/新能源，配置块用 `asset`；这边的主体是售电公司，配置块改用 `portfolio`，并多出零售套餐、偏差合同、履约保障三块。

## 2. 目录结构

```
instances/
├── README.md                          # 本文件：schema、填写流程、验收
├── guangdong-retail-2026-11/          # 广东 2026：固定价 + 市场联动
│   ├── instance.json                  # 唯一配置入口
│   ├── run.py                         # 运行器（校验 → 定价 → 情景/压力 → 差异桥 → 复核）
│   ├── make_demo.py                   # D 级合成 D-1/T+1 数据生成器
│   ├── README.md                      # 本实例的命令、产物、基准数字、参数状态
│   ├── pitfalls.md                    # 广东售电易错点
│   ├── data/                          # D-1 / T+1 输入（演示为合成）
│   └── out/demo/                      # 运行产物（可删除重建）
└── jiangsu-retail-2027/               # 江苏 2027：批发价传导 + 一户一价封顶
    ├── instance.json
    ├── run.py                         # 运行器（校验 → 传导/参考价 → 封顶 → 情景/压力 → 差异桥 → 复核）
    ├── make_demo.py
    ├── README.md
    ├── pitfalls.md
    ├── data/
    └── out/demo/
```

## 3. `instance.json` 六个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-主体-年月`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称；广东要区分省内市场与南方区域价区 |
| `entity_type` | 主体类型 | 售电公司 / 批发用户 / 综合能源服务商 |
| `rule_version` | 规则版本与生效日 | 冻结到一个版本；跨版本要切段 |
| `data_cutoff` | 本包数据截止日 | 与 D-1 输入的发布时点一致 |
| `grade` | 整体来源级别 | `D` 表示合成样板 |
| `scope` | 纳入/未纳入科目 | 必须写清"电能量口径"还是"全口径" |
| `units` | 单位约定 | 价格 **CNY/MWh**、电量 MWh、功率 MW、时段 0–95；换算 `1 CNY/MWh = 0.001 CNY/kWh` |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成报价建议 |

价格单位是售电实例最容易出错的地方：`405 CNY/MWh = 0.405 CNY/kWh`。配置校验只接受 `CNY/MWh` 与 `MWh`，防止把 0.405 和 405 混写。

### 3.2 `rules`：省级规则与来源

每个规则子块都必须带 `grade` 和 `source`，缺一个就拒绝运行。规则子块按套餐模型不同：

| 模型 | 实例 | 规则子块 |
|---|---|---|
| `fixed_market_linked` | 广东 2026-11 | `spot`、`retail_market`、`deviation`、`guarantee`、`settlement` |
| `pass_through_cap` | 江苏 2027 | `spot`、`retail_market`、`price_formula`、`allocation`、`guarantee`、`settlement` |

**广东模型的五个子块**

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `spot` | 现货价区、限价、时段粒度、结算口径 | `declare_floor_cny_per_mwh`、`clear_floor_cny_per_mwh`、`clear_cap_cny_per_mwh`、`market_time_unit_min`、`points_per_day`、`settlement_basis` |
| `retail_market` | 零售平台、均价、套餐类型 | `package_types`、`retail_avg_2026h1_cny_per_mwh`、`margin_2026h1_cny_per_mwh`、`price_linkage_notice` |
| `deviation` | 偏差考核的规则状态 | `guangdong_status`、`contract_basis`、`national_framework` |
| `guarantee` | 现行/草案履约保障 | `current`、`draft_2026_09_04`、各自 `effective` |
| `settlement` | 结算时限与文号 | `timeline`、`document` |

**江苏 2027 模型的六个子块**

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `spot` | 现货限价、粒度、结算口径 | `clear_floor_cny_per_mwh`、`clear_cap_cny_per_mwh`、`market_time_unit_min`、`points_per_day`、`settlement_basis` |
| `retail_market` | 2027 零售指引、取消项、一户一价、年度窗口 | `document`、`effective_from`、`cancelled`、`one_household_one_price`、`annual_window`、`retailer_requirement` |
| `price_formula` | 批发价/参考价/封顶/结算公式 | `wholesale`、`reference`、`cap`、`settlement`、`tou_constraint`、`cap_float_factor_status` |
| `allocation` | 三类分摊与 2026 参考值 | `categories`、`monthly_reference_2026`、`base_month`、`reported_range` |
| `guarantee` | 现行/草案履约保障 | `current`、`draft_2026_09_04`、各自 `effective` |
| `settlement` | 结算时限、零售口径、偏差状态 | `timeline`、`retail_basis`、`retail_deviation_status` |

三条硬规则：

- **区域参数与省内参数分开**。广东现货写南方区域正式方案（−50–1,800 元/MWh），旧试点 0–1,000 / 70–1,500 只能放 `historical_pilot` 并标"历史口径"；江苏写省内 0–1,500 元/MWh。
- **草案不生效**。2026-09-04 售电办法修订稿放 `draft_2026_09_04`，`effective` 必须为 `false`；写成 `true` 配置直接报错。
- **未核实的省规则不编**。广东偏差考核只核到市场宣传口径，`grade` 写 `C`，按合同约定测算；江苏 2027 零售偏差未明确统一口径，`retail_deviation_status` 写 `C`，本包不计并在复核表打印 warning。

### 3.3 `portfolio`：客户组合（替代现货实例的 `asset`）

| 字段 | 单位 | 说明 |
|---|---|---|
| `segments[].name` | — | 客户群名称，同一实例内不重复 |
| `segments[].package_type` | — | 广东模型支持 `fixed` 与 `market_linked`；江苏模型只支持 `pass_through_cap` |
| `segments[].share` | — | 电量份额，所有 segment 之和必须为 1 |
| `segments[].retail_price_cny_per_mwh` | CNY/MWh | 固定价套餐的当前售价（广东模型） |
| `segments[].pass_through` / `adder_cny_per_mwh` | — / CNY/MWh | 联动套餐的传导系数与加价（广东模型） |
| `segments[].floor_cny_per_mwh` / `cap_cny_per_mwh` | CNY/MWh | 联动套餐的价格上下限（广东模型） |
| `segments[].tilt` | — | 江苏模型：客户曲线相对组合平均的尖峰/平坦程度，正=尖峰、负=平坦；决定 P_ref 与封顶价 |
| `segments[].sigma` | — | 江苏模型：该客户群负荷预测误差标准差（如 0.025 = 2.5%） |
| `segments[].green_power` | bool | 江苏模型：是否绿电客户；为真时另签能量包与环境价值包 |
| `segments[].forecast_sigma_pct` | — | 广东模型：客户群负荷预测误差标准差（如 0.03 = 3%） |
| `segments[].opex_cny_per_mwh` | CNY/MWh | 该客户群的服务/获客/结算运营成本 |
| `annual_energy_mwh` | MWh | 年售电量，仅作规模上下文与保函核对 |
| `fixed_cost_cny_per_day` | CNY/日 | 公司固定成本分摊 |
| `deviation_terms` | — | 广东模型：合同约定的免考带、考核价与依据 |
| `guarantee` | — | 保函金额、资金成本率、计算基数与依据 |
| `wholesale_mix` | — | 江苏模型：年度/月度/月内价格与权重，日前/实时占比 |
| `green_power` | — | 江苏模型：能量溢价、环境价值、环境成本 |

`share` 是电量份额，不是客户数份额，也不是收入份额。用客户数填 `share` 会让组合定价整体失真。

江苏模型的 `tilt` 不是装饰参数：它把组合总负荷拆成不同形状的客户曲线，进而改变 P_ref、P_cap 与扣减。`tilt=0` 表示与组合同形状，正负值只改变形状、不改变该客户群的总电量份额。

### 3.4 `policy`：交易风格档

风格是售电公司的选择，不是事实。同一个组合换风格档，建议价、压力测试与情景结论都会变；复盘时要能区分"风格造成的差异"与"预测/执行造成的差异"。

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 风格档名 | `guangdong-balanced-v1`、`jiangsu-retail-2027-balanced-v1` |
| `price_reference_quantile` | 参考价取情景分位 | 0.5 中性 / 0.7 保守（买贵一点） |
| `risk_buffer_cny_per_mwh` | 报价中的风险缓冲 | 覆盖尾部与执行误差（广东模型） |
| `target_margin_cny_per_mwh` | 目标利润 | 可为负（战略客户），但要有理由（广东模型） |
| `stress_spot_multipliers` | 现货压力倍数 | 1.0 / 1.2 / 1.3 / 1.5；江苏另用 0.8 低档 |
| `stress_sigma_pcts` | 偏差压力档 | 0.02 / 0.04 / 0.06（广东模型） |
| `retail_float_cny_per_mwh` | 浮动价 P_float | 江苏模型，如 55 |
| `cap_float_factor` | 封顶公式中的 F | 江苏模型，如 0.05；**由购售双方约定** |
| `allocation_coefficients` | 三类分摊传导系数 | 江苏模型：P1=0.8、P2=1.0、P3=0.5 |
| `stress_cap_factors` | 封顶系数压力档 | 江苏模型：0 / 0.05 / 0.10 / 0.20 |
| `stress_floats` | 浮动价压力档 | 江苏模型：40 / 55 / 70 |
| `stress_allocation_pass_through` | 分摊传导比例压力档 | 江苏模型：0 / 0.5 / 1.0 |
| `review_top_slots` | 复核表列出的最大偏差时段数 | 5 |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入 `summary.json` 与复核表。比较两个交易日时先看指纹：指纹不同，差异首先归因于风格；指纹相同，才归因于预测、执行或规则。

### 3.5 `contracts`：中长期与零售合同

**广东模型**只支持一份固定价、按预测负荷比例锁定的中长期合约：

| 字段 | 说明 |
|---|---|
| `contract_id` | 合约编号 |
| `type` | 目前只支持 `medium_term_fixed_price` |
| `coverage_ratio` | 覆盖预测负荷的比例（0–1） |
| `price_cny_per_mwh` | 合约价 |
| `quantity_basis` | 目前只支持 `forecast_load_share`（D-1 按预测负荷锁量） |
| `settlement` | 结算文字说明，写入复核表 |

未配置合约时按纯现货处理。多段合约、分时段合约、差价合约的参考点选择留到后续版本；`contracts` 超过 1 份会被拒绝。

**江苏 2027 模型**把零售合同与绿电合同分开：

| 合同 | 关键字段 | 说明 |
|---|---|---|
| `contracts.retail_2027` | `type: annual_retail_pass_through`、`signed_date`、`retail_trade_date`、`annual_wholesale_date`、`one_household_one_price`、`customers` | 年度零售合同；校验窗口、日期先后与一户一价 |
| `contracts.green_power` | `type: green_power_split`、`energy_contract`、`environmental_contract`、`signed` | 绿电能量包与环境价值包分开签约 |

### 3.6 `data_contract`：输入契约

`d1` 声明 D-1 预测负荷文件与情景价格列、权重、发布截止时点；`t1` 声明 T+1 实际负荷与实际结算价。路径相对实例目录，绝对路径用于本地私有数据。

江苏 2027 模型的 `t1` 还声明 `allocation_fields`（三类实际分摊列）；D-1 的 `scenario_fields` / `scenario_weights` 与广东模型相同。`data_contract` 的两个子块也必须带 `grade` + `source`。

## 4. 输入格式

### 4.1 D-1（96 点 × 5 情景）

```csv
date,slot,start,end,forecast_load_mw,price_s1,price_s2,price_s3,price_s4,price_s5
2026-11-18,0,00:00,00:15,81.184225,230.32,257.41,270.96,311.60,392.89
```

- 只能有一个交易日；`slot` 必须 0–95 连续、无缺口、无重复；
- `forecast_load_mw` 非负；情景价格必须在 `[clear_floor, clear_cap]` 内；
- 情景列名与 `scenario_fields` 一致，`scenario_weights` 之和为 1；
- 情景必须是 D-1 截止前可得的：分位数、集合预报成员或人工情景都可，但不能用事后价格。

### 4.2 T+1（实际负荷与实际结算价）

广东模型：

```csv
date,slot,start,end,actual_load_mw,actual_price
2026-11-18,0,00:00,00:15,82.158660,248.75
```

江苏 2027 模型另加三类实际分摊：

```csv
date,slot,start,end,actual_load_mw,actual_price,actual_p1,actual_p2,actual_p3
2027-01-15,0,00:00,00:15,71.32,282.61,1.60,5.50,-0.12
```

- 同一交易日、96 点齐全；
- 实际负荷非负；实际价格必须在同一限价区间内；
- 江苏模型的三类分摊按电量加权得到实际分摊均价，再与计划值做差异桥；
- 没有 T+1 数据时只出定价表与情景/压力，不跑差异桥（省略 `--t1`）。

## 5. 填写流程（约 30 分钟）

1. **先选套餐模型**：固定价/市场联动 → 复制 `guangdong-retail-2026-11`；批发价传导 + 一户一价封顶 → 复制 `jiangsu-retail-2027`。模型不同，`rules`、`portfolio`、`contracts`、`policy` 的字段都不同，不能混拷；
2. **改 `meta`**：实例名、省份、主体类型、规则版本、数据截止日与口径边界；
3. **核对 `rules`**：只填当前生效值，逐块写 `grade` 与 `source`；草案与历史口径放独立字段；
4. **填 `portfolio`**：按客户群填电量份额、套餐类型、售价/联动参数或曲线 `tilt`/绿电标记、预测误差与运营成本；`share` 合计必须为 1；
5. **填 `contracts`**：广东模型填覆盖比例与合约价；江苏模型填零售合同日期、一户一价与绿电拆分合同；
6. **选 `policy`**：先沿用模板风格（`guangdong-balanced-v1` 或 `jiangsu-retail-2027-balanced-v1`），跑通后再调分位、浮动价、F 与压力档；
7. **替换 CSV**：按第 4 节格式导出自己的 D-1 情景与 T+1 实际；江苏模型要带三类实际分摊；
8. **跑 `--check-config`**：来源缺失、单位错误、份额不为 1、套餐类型不符、日期关系错误会直接报错；
9. **跑一次 `--demo`**：看定价/封顶缺口、情景 CVaR、压力测试与差异桥残差。

## 6. 运行与产物

```bash
# 广东 2026：固定价 + 市场联动
python skills/retail-electricity-risk/instances/guangdong-retail-2026-11/run.py --check-config
python skills/retail-electricity-risk/instances/guangdong-retail-2026-11/run.py --demo

# 江苏 2027：批发价传导 + 一户一价封顶
python skills/retail-electricity-risk/instances/jiangsu-retail-2027/run.py --check-config
python skills/retail-electricity-risk/instances/jiangsu-retail-2027/run.py --demo

# 用自己的数据（路径指向仓库外）
python skills/retail-electricity-risk/instances/<实例目录>/run.py \
  --d1 /path/to/d1.csv --t1 /path/to/t1.csv --out /path/to/out
```

产物（默认 `out/demo/`，按模型不同）：

| 文件 | 内容 |
|---|---|
| `pricing_sheet.csv` | 广东：客户群当前价、全成本、建议价、缺口、保本现货价；江苏：P_ref、P_cap、零售价、扣减、余量、保本浮动价 |
| `procurement_plan.csv` | 广东：96 点预测负荷、合约锁量、现货购电量与五情景价格 |
| `pass_through_curve.csv` | 江苏：96 点 P_MT、P_wholesale、P_ref、封顶价、封顶前零售价 |
| `scenario_table.csv` | 五情景的零售/批发/封顶/扣减/净收益；江苏另列触顶群数 |
| `stress_table.csv` | 压力测试：现货倍数、封顶系数、浮动价、分摊传导比例、分摊月份 |
| `summary.json` | 配置快照、风格指纹、定价、情景、压力、差异桥摘要 |
| `bridge.json` / `bridge.csv` | T+1 差异桥：广东 9 个科目；江苏 6 个科目；残差 < 1e-6 CNY |
| `deviation_slots.csv` / `top_slots.csv` | 偏差最大的时段：预测/实际负荷、价格与考核或参考层 |
| `review.md` | 复核表：来源与警告、定价/封顶、情景/压力、差异桥、时段明细、读法 |

## 7. 配置校验与实际拦截

`run.py` 的 `validate_instance` 会拒绝：

- 缺 `meta` 必填项、缺 `rules`/`portfolio`/`policy`/`data_contract`；
- 任一规则块缺 `grade` 或 `source`，或 `grade` 不是 A/B/C/D 组合；
- `meta.units.price` 不是 `CNY/MWh`、`meta.units.energy` 不是 `MWh`；
- `points_per_day ≠ 24×60 / market_time_unit_min`；
- `clear_floor ≥ clear_cap`，或 `declare_floor < clear_floor`；
- 未知套餐类型；广东模型的 `tou`/`floor_plus_float`/`service_fee` 在 v1 未实现；
- `share` 之和不为 1、客户群重名、联动套餐下限大于上限；
- 广东模型：`deviation_terms` 缺依据、`guarantee` 缺依据、合约为空以外的类型、覆盖比例越界、超过一份合约；
- 江苏模型：`retail_market` 缺取消项/一户一价/年度窗口，`price_formula` 缺公式，`allocation` 月度表不足 6 个月或逐月合计不自洽，`base_month` 不在表内，`contracts.retail_2027` 日期先后错误，绿电客户缺拆分合同，`wholesale_mix` 权重或日前/实时占比越界；
- 草案保函 `effective=true`；
- 情景列数与权重数不一致、权重和不为 1。

输入数据还会拒绝：多交易日、缺时段、重复点、负荷为负、价格越界、江苏模型缺三类分摊列。

会打印但**不拦截**的警告：D 级合成数据、广东偏差规则未核实、江苏 2027 零售偏差未明确、草案未生效、2026-06-08 通知无正式文号、保函金额与 1595 号公式不一致、资金成本率高于 5%（疑似百分数误填）、江苏年度窗口/5 个工作日为公开解读口径、F 由双方约定、2027 分摊按月公布、绿电封顶口径为 D 级解释。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉客户与合同的人 ~30 分钟；只需改 JSON 与 CSV |
| 运行时间 | 5 情景 × 96 点，单机 < 1 分钟 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 差异桥 | 残差 < 1e-6 CNY；广东 9 个科目、江苏 6 个科目可归因 |
| 数据本地 | 真实客户、合同、计量数据不上传，仓库只存结构与 D 级样例 |
| 验收口径 | 不看样本内 PnL；看流程是否跑通、口径是否可复现、差异是否可归因 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实售电公司或用户；
- 真实数据用 `--d1/--t1/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实客户名、合同价、偏差条款、保函与信用信息写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增第三个实例

1. 选一个**已正式运行、规则版本稳定**的省份与售电主体，并先确定套餐模型：固定价/联动，还是批发价传导 + 封顶；
2. 复制对应样板目录（广东或江苏）的 `run.py` 与 `make_demo.py`，改复核表标题与命令行描述；
3. 新建 `instance.json`，六个块齐全，规则值全部带来源级别；套餐模型不同就不要混用字段；
4. 在 `pitfalls.md` 写本省易错点（区域/省内混用、机制电价批次、零售均价口径、草案当现行、封顶与分摊口径）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

## 11. 相关入口

- 售电方法正文：[`../SKILL.md`](../SKILL.md) §10 算例、§12 代码映射
- 广东市场档案：[`knowledge/广东电力市场-2026-11.md`](../../../knowledge/广东电力市场-2026-11.md)
- 现货实例层（储能/新能源）：[`skills/spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)
- 负荷聚合实例层（邀约型 VPP）：[`skills/virtual-power-plant/instances/`](../../virtual-power-plant/instances/README.md)
- 广东售电样板：[`guangdong-retail-2026-11/README.md`](guangdong-retail-2026-11/README.md)
- 江苏 2027 售电样板：[`jiangsu-retail-2027/README.md`](jiangsu-retail-2027/README.md)
- 江苏市场档案：[`knowledge/江苏电力市场-2026-11.md`](../../../knowledge/江苏电力市场-2026-11.md)
