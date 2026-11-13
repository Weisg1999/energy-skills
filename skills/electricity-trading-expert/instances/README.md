# 实例包：中长期持仓、煤电收益与省间组合的可配置切片

> 目录定位：`skills/electricity-trading-expert/instances/` 是**实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是"一省 + 一主体 + 一套合约/资产 + 一个规则版本"的配置包，交易员只改 JSON 与 CSV，不改代码。当前三个切片：山东煤电中长期持仓、甘肃煤电容量电价与辅助服务、甘肃风电送山东省间组合。

## 1. 为什么要有这一层

`electricity-trading-expert` 正文回答"中长期、容量、辅助服务与省间市场的机制是什么"；实例层回答"**你这个省、这台机组、这本合约、这个交易日，持仓够不够、曲线错在哪、收益叠加后还剩多少、跨省扣减后净价是多少**"。

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | `tools/hedge.py` 的曲线分解、CfD 结算、carry/shape、六桶桥 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省规则 + 机组/项目 + 合约簿或资产 + 风格档 + 数据契约 | 持仓表、模式对比、通道扣减、差异桥、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的月度/年度复盘 | 按错误类型索引的案例库 | 未建，需真实结算单积累 |

D-1 现货与报价的实例层在 [`skills/spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)；售电侧在 [`skills/retail-electricity-risk/instances/`](../../retail-electricity-risk/instances/README.md)。三者共用"一省一主体一规则版本"的结构，但问题不同：现货包问"明天报什么"，本层问"合约怎么落到 96 点、总持仓够不够""容量与辅助服务能把煤电利润托到什么程度""跨省送电扣完通道费还剩多少"。

## 2. 目录结构

```
instances/
├── README.md                              # 本文件：schema、流程、验收
├── shandong-thermal-hedge-2026-11/        # 山东 600 MW 煤电，2026-11 合约簿
│   ├── instance.json                      # 唯一配置入口
│   ├── run.py                             # 校验 → 分解 → 情景 → 滚动 → 差异桥
│   ├── make_demo.py                       # D 级合成数据
│   ├── README.md
│   ├── pitfalls.md
│   ├── data/
│   │   ├── d1_demo.csv                    # 96 点预测 + 5 情景价格
│   │   ├── t1_demo.csv                    # 实际出力/合约电量/日前价
│   │   └── rolling_demo.csv               # D-7~D-1 滚动预测
│   └── out/demo/                          # 产物（默认 git 忽略）
├── gansu-coal-capacity-ancillary-2026-11/ # 甘肃 2×660 MW 煤电，容量+辅助服务
│   ├── data/market_demo.csv               # 12 月三段价格与合约电量
│   └── out/demo/
└── gansu-wind-to-shandong-2026-11/        # 甘肃 200 MW 风电送山东
    ├── data/profile_demo.csv              # 12 月发电量、合同权重、落地价、绿电比例
    └── out/demo/
```

### 2.1 三个切片的分工

| 包 | 主体 | 规则主线 | 运行链 | 结算重点 |
|---|---|---|---|---|
| `shandong-thermal-hedge-2026-11/` | 600 MW 煤电 | 山东现货 + 中长期分解 + CfD | D-1 分解 → 5 情景 carry/shape → D-7~D-1 滚动 → T+1 六桶桥 | 期间电量→日电量、峰谷窗口、对冲比例、桥闭合 |
| `gansu-coal-capacity-ancillary-2026-11/` | 2×660 MW 公用煤电 | 甘发改价格规〔2025〕4号容量补偿 330 元/kW·年；现货 V3.2；1656 号中长期 | 四模式出力 → 电能量/容量/辅助服务 → 考核扣减 → 敏感性 → 临界值 | 容量供需系数、一次/二次/三个月考核、深度调峰与调频备用 |
| `gansu-wind-to-shandong-2026-11/` | 200 MW 风电项目公司 | 发改办体改〔2026〕275号、发改能源规〔2025〕1656号、2027 跨省跨区输电价 | 月度电量 → 合同分解 → 通道扣减 → 三种组合 → 敏感性 | 输电价按落地电量、网损按发电量、绿电溢价只落合同内电量 |

三包输入形态不同：山东用 96 点 D-1 / T+1 / 滚动；甘肃煤电与甘肃送山东用 12 个月月度表。规则块随包变化（山东 `spot`/`mid_long_term`/`settlement`/`deviation`，甘肃煤电 `capacity`/`ancillary`/`energy`/`cost`，省间 `interprovincial`/`delivery`/`market`），runner 只校验本包声明的块。

## 3. `instance.json` 配置块

3.1–3.6 描述山东煤电持仓包的完整结构（`book` 合约簿）；甘肃煤电包用 `asset` + `rules.capacity/ancillary/energy/cost` + `policy.modes`，甘肃送山东包用 `project` + `rules.interprovincial/delivery/market` + `policy.strategies`，字段见各自 `instance.json` 与实例 README。三包共同要求：`meta` 八项必填、每个规则块带 `grade` + `source`、配置错误直接报错。

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-主体-年月`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称，避免"山东现货"这种含糊口径 |
| `entity_type` | 主体类型 | 煤电/热电/新能源/售电 |
| `rule_version` | 规则版本与生效日 | 冻结到一个版本；跨年切段 |
| `data_cutoff` | 本包数据截止日 | 与 D-1 输入发布时点一致 |
| `grade` | 整体来源级别 | A/B/C/D；`D` 表示合成样板 |
| `scope` | 纳入/未纳入的品种 | 写清边界，防止把电能量收入当利润 |
| `units` | 单位约定 | 功率 MW、电量 MWh、价格 CNY/MWh、96 点 |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成建议 |

### 3.2 `rules`：省级规则与来源

每个子块都必须带 `grade` 和 `source`，缺一个配置校验就拒绝运行：

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `spot` | 现货限价与时段粒度 | `market_time_unit_min`、`points_per_day`、申报/出清上下限 |
| `mid_long_term` | 合约类型、分解与结算原则 | `contract_types`、`period_energy_decomposition`、`shape_basis`、`rolling_window` |
| `settlement` | 结算口径 | `basis`（CfD 公式）、`deviation_basis` |
| `deviation` | 偏差与考核边界 | `included`（本包为 false）、`basis` |

草案值放独立字段（如 `draft_2026_08_28`）并标 `status`，不得写进生效字段。

### 3.3 `asset`：机组参数

| 字段 | 单位 | 说明 |
|---|---|---|
| `capacity_mw` | MW | 铭牌容量 |
| `min_output_mw` | MW | 供热/稳燃最小出力，用于检查预测是否离谱 |
| `grade` / `source` | — | 资产参数通常是私有数据，入库用占位值 |

### 3.4 `book`：合约簿

每份合约：

| 字段 | 含义 | 要求 |
|---|---|---|
| `id` | 合约唯一名 | 不得重复 |
| `kind` | 合约类型 | `annual_base` / `monthly_peak` / `monthly_offpeak` / `intra_month_curve` |
| `type` | 合约性质 | v1 只支持 `cfd`（金融差价合约） |
| `period_start` / `period_end` | 合约期间 | 必须覆盖交易日 |
| `period_days` | 期间天数 | 与期间一致；用于期间电量→日电量 |
| `energy_mwh` | 期间电量 | 与 `daily_energy_mwh` 二选一 |
| `price_cny_per_mwh` | 合约价 | 正数且不高于现货价格上限（数据合理性校验） |
| `shape` | 曲线形状 | `base` / `window` / `complement` / `anchors` / `curve` |
| `grade` / `source` | 来源 | 必须填 |

`shape` 的权重会归一化到和为 1，再乘日电量。峰谷窗口是**合同约定**，不是省级分时电价。

### 3.5 `policy`：交易风格档

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 风格档名 | `shandong-thermal-hedge-balanced-v1` |
| `target_hedge_ratio` | 目标对冲比例 | 0.85 |
| `min_hedge_ratio` / `max_hedge_ratio` | 允许区间 | 0.7 / 1.0 |
| `price_reference_quantile` | 参考价取情景分位 | 0.5 |
| `rebalance_start_day` | 滚动起始日 | 7（D-7） |
| `freeze_day_offset` | 冻结日 | 1（D-1） |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入复核表。换风格就换 `profile_id`，旧文件保留，便于横向比较。

### 3.6 `data_contract`：输入契约

- `d1`：96 点预测字段、情景价格字段、权重、发布截止时点；
- `t1`：实际出力、结算合约电量、日前价；
- `rolling`：D-7~D-1 预测电量与调仓前持仓。

路径相对实例目录；绝对路径用于本地私有数据。

## 4. 输入格式

### 4.1 D-1

```csv
date,slot,start,end,forecast_mw,price_s1,price_s2,price_s3,price_s4,price_s5
2026-11-18,0,00:00,00:15,346.5,275.0,305.0,320.0,355.0,295.0
```

- 只能有一个交易日；`slot` 从 0 到 95 连续无缺口；
- 价格列名与 `price_scenario_fields` 一致，权重之和为 1；
- 情景必须是在 D-1 截止前可得的，不能用事后价格回填。

### 4.2 T+1

```csv
date,slot,actual_mw,actual_contract_mwh,actual_da_price
2026-11-18,0,340.7,62.5,321.0
```

- `actual_contract_mwh` 是结算单上的实际合约电量（MWh/时段），允许含 D-1 调仓；
- 实际合约电量按合约簿加权价结算；v1 不单独建模 D-1 新增交易的成交价；
- 没有实际数据时只出合约簿与计划表（`--t1` 省略）。

### 4.3 滚动预测

```csv
day_offset,forecast_output_mwh,position_before_mwh
-4,8450.0,7000.0
-3,8600.0,7182.5
```

- `day_offset` 在 `-rebalance_start_day ~ 0`；
- `position_before_mwh` 必须与上一日 `position_after` 衔接，否则报错；
- 不需要滚动复核时 `--rolling` 省略。

## 5. 填写流程（约 30 分钟）

山东煤电持仓包：

1. **复制实例目录**：`cp -r instances/shandong-thermal-hedge-2026-11 instances/<省>-<主体>-<年月>`；
2. **改 `meta`**：实例名、省份、主体类型、规则版本、数据截止日；
3. **核对 `rules`**：只填当前生效值，逐块写 `grade` 与 `source`；草案值放独立字段；
4. **填 `asset`**：铭牌容量与最小出力；
5. **填 `book`**：从合同台账录期间电量、合约价、曲线形状；先跑一次 `--check-config` 看日电量量级；
6. **选 `policy`**：先沿用 0.85 目标比例，跑通后再调；
7. **替换 CSV**：按第 4 节格式导出 D-1、T+1 与滚动预测；
8. **跑全流程**：看对冲比例、carry/shape、滚动衔接与差异桥残差是否为 0。

甘肃煤电容量包：

1. 复制 `gansu-coal-capacity-ancillary-2026-11`；
2. 核对 `rules.capacity` 的补偿标准、容量供需系数与考核条款，标 A/B 与文号；
3. 填 `asset`：铭牌、申报容量比例、最低稳燃、煤耗曲线、固定成本与财务费用；
4. 填 `policy.modes`：各模式谷/平/峰出力比例，确认不超过申报容量；
5. 换 `data/market_demo.csv`：12 个月三段价格、小时数、合约电量；
6. 跑 `--check-config` 与 `--demo`，看四模式利润、容量补偿、辅助服务与临界煤价。

甘肃送山东省间包：

1. 复制 `gansu-wind-to-shandong-2026-11`；
2. 核对 `rules.interprovincial`（275号/1656号）与 `rules.delivery`（输电价、线损、结算参考）；
3. 填 `project`：装机、计划电量、合同比例、绿电比例；
4. 填 `policy.strategies`：`local_only` / `contract_spot` / `contract_local`；
5. 换 `data/profile_demo.csv`：12 个月发电量、合同权重、落地价、绿电比例；
6. 跑 `--check-config` 与 `--demo`，看通道扣减分解、三种组合净价与相对全部本地的差额。

## 6. 运行与产物

```bash
# 三个包各自校验与演示
python skills/electricity-trading-expert/instances/<pack>/run.py --check-config
python skills/electricity-trading-expert/instances/<pack>/run.py --demo
# <pack> = shandong-thermal-hedge-2026-11 / gansu-coal-capacity-ancillary-2026-11 / gansu-wind-to-shandong-2026-11

# 山东持仓：用自己的 D-1 / T+1 / 滚动数据
python skills/electricity-trading-expert/instances/shandong-thermal-hedge-2026-11/run.py \
  --d1 /path/to/d1.csv --t1 /path/to/t1.csv --rolling /path/to/rolling.csv --out /path/to/out

# 甘肃煤电：用自己的月度市场数据
python skills/electricity-trading-expert/instances/gansu-coal-capacity-ancillary-2026-11/run.py \
  --market /path/to/market.csv --out /path/to/out

# 甘肃送山东：用自己的月度电量与价格
python skills/electricity-trading-expert/instances/gansu-wind-to-shandong-2026-11/run.py \
  --profile /path/to/profile.csv --out /path/to/out
```

产物：山东包 `book_sheet.csv`、`rolling.csv`、`summary.json`、`bridge.json` / `bridge.csv`、`review.md`；甘肃煤电包 `modes.csv`、`monthly.csv`、`revenue.csv`、`sensitivity.csv`、`summary.json`、`review.md`；省间包 `monthly.csv`、`strategies.csv`、`delivery.csv`、`sensitivity.csv`、`summary.json`、`review.md`。

## 7. 配置校验与实际拦截

山东持仓包 `run.py` 会拒绝：

- 缺 `meta` 必填项、缺 `rules` / `asset` / `book` / `policy` / `data_contract`；
- 任一规则块缺 `grade` 或 `source`；
- `points_per_day ≠ 24×60 / market_time_unit_min`；
- 限价不满足 `clear_floor ≤ declare_floor < declare_cap ≤ clear_cap`；
- 合约 `type ≠ cfd`、`kind` 不在允许列表、`shape.type` 未知；
- 合约价 ≤ 0 或高于现货价格上限；
- 合约期间不覆盖交易日、`period_start > period_end`；
- 合约簿日电量 > `容量 × 24 × max_hedge_ratio`（拦截"期间电量当日电量"）；
- `min_hedge_ratio > target > max_hedge_ratio`；
- 情景权重之和不为 1、情景列数与权重数不一致；
- 滚动 `position_before` 与上一日收盘不衔接、`day_offset` 越界。

甘肃煤电包还会拒绝：申报容量不在铭牌 50%–100%、模式出力低于最低稳燃或超过申报容量对应比例、煤耗曲线随负荷率非单调不增、月度三段小时数之和不为 24、价格越界。省间包还会拒绝：合同比例不在 0–1、输电价或线损为负、结算参考未实现、数据契约缺字段、月份跨年或乱序。

输入数据会拒绝：多交易日、缺时段、重复点、出力超容量、价格越界、实际合约电量为负。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉合同台账/机组台账的人 ~30 分钟；只需改 JSON 与 CSV |
| 运行时间 | 山东 5 情景 × 96 点、甘肃两包 12 个月，单机 < 1 秒 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 对冲价值 | carry + shape 恒等于 hedge value，残差 < 1e-6（山东包） |
| 差异桥 | 六桶之和等于实际 − 计划，残差 < 1e-6（山东包） |
| 收益叠加 | 电能量、容量、辅助服务分列，考核与容量系数可复算（甘肃煤电包） |
| 通道扣减 | 输电价、网损、合同综合扣减分列，不重复乘线损（省间包） |
| 数据本地 | 真实机组、合约价、结算电量、通道合同不上传；仓库只存结构与 D 级样例 |
| 验收口径 | **不看样本内收入**；看分解是否可复现、口径是否可归因、桥是否闭合 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实机组或合同；
- 真实数据用 `--d1/--t1/--rolling/--market/--profile/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实合约价、结算电量、机组出力、煤价、通道合同写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增实例

1. 选一个**已正式运行、规则版本稳定**的省份与主体；
2. 复制**结构最接近**的实例，保留 `run.py` 的校验骨架：持仓分解复制山东，收益叠加复制甘肃煤电，跨省组合复制甘肃送山东；
3. 新建 `instance.json`，配置块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本省易错点（期间电量、峰谷窗口、CfA 符号、草案当现行、容量系数、考核扣减、输电价按落地电量、网损按发电量）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。
