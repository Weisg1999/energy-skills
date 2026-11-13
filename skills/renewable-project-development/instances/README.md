# 新能源开发实例包：一省一项目的可配置投决切片

> 目录定位：`skills/renewable-project-development/instances/` 是**新能源开发期投决的样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是"一省 + 一个开发主体 + 一个规则版本"的配置包，开发/投资人员只改 JSON 与 CSV，不改代码。当前一个切片：云南 100 MW 陆上风电 2027（136 号文机制电价 + 省内市场）。

## 1. 为什么要有这一层

引擎层（`tools/lcoe.py`、`mechanism.py`、`resource.py`、`finance.py`）回答"LCOE 怎么算、机制差价怎么结、资源怎么折、现金流怎么排"；实例层回答"**这个场址、这套造价与融资、这批机制电价参数，投标价报多少才不亏，IRR / NPV / DSCR 三条线能不能同时过**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | LCOE、差价结算、资源折减、税后现金流公式 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省机制电价参数 + 场址资源 + 造价融资 + 投决风格 + 数据契约 | 月度结算、20 年现金流、LCOE、盈亏平衡价、投标阶梯、敏感性、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的投决复盘 | 按错误类型索引的案例库 | 未建，需真实竞价与建设数据积累 |

开发期投决的私有数据不是运行数据，而是**测风/资源评估、设备询价、接入方案、融资条件、税务筹划与集团投决门槛**。实例层把这些挡在本地，只把结构与口径放进仓库。

## 2. 目录结构

```
instances/
├── README.md                              # 本文件：schema、流程、验收
└── yunnan-wind-development-2027/          # 云南 100 MW 陆上风电，2027 竞价
    ├── instance.json                      # 唯一配置入口
    ├── run.py                             # 校验 → 月度结算 → LCOE → 现金流 → 投标 → 敏感性
    ├── make_demo.py                       # D 级合成资源数据生成器
    ├── README.md                          # 本实例的命令、产物、基准数字、参数状态
    ├── pitfalls.md                        # 云南风电投决易错点
    ├── data/resource_demo.csv             # 首年 12 个月毛发电量与捕获率
    └── out/demo/                          # 运行产物（可删除重建）
```

## 3. `instance.json` 五个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-项目-年度`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称；本包为机制电价 + 省内市场 |
| `entity_type` | 主体类型 | 风电/光伏开发企业（开发期投决） |
| `rule_version` | 规则版本 | 国家级框架 + 省级竞价批次与公示日期；冻结到一个版本 |
| `data_cutoff` | 数据截止日 | 与资源评估、询价、公示时点一致 |
| `grade` | 整体来源级别 | B/C；合成算例为 D |
| `scope` | 纳入/未纳入科目 | 写清是否含土地林草审批、接入工程、建设期利息、保险 |
| `units` | 单位约定 | 装机 MW；电量 MWh；电价 CNY/kWh；造价 CNY/kW；LCOE CNY/MWh |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成投标或投资建议 |

### 3.2 `rules`：机制电价、市场、成本与融资

每个规则子块都必须带 `grade` 和 `source`，缺一个就拒绝运行：

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `mechanism` | 机制电价与竞价 | `mechanism_price_cny_per_kwh`、`bid_cap/bid_floor`、`coverage_ratio`、`pool_demand_ratio`、`single_project_cap`、`settlement` |
| `market` | 市场价与绿证 | `market_price_cny_per_kwh`、`green_certificate_cny_per_mwh`、`status`（捕获价 vs 均价） |
| `cost` | 造价与运维 | `capex_cny_per_kw`、`opex_cny_per_kw_year`、`curtailment_ratio`、`degradation_per_year`、`opex_escalation_per_year`、`life_years` |
| `finance` | 税后与融资 | `discount_rate`、`tax_rate`、`depreciation_years`、`debt_ratio`、`debt_rate`、`debt_years`、`hurdle_irr`、`min_dscr` |

三条硬规则：

- **机制价必须落在申报下限与上限之间**，覆盖比例不得超过单体上限；只实现 `difference` 差价结算。
- **市场收入用捕获价，机制差价用市场均价**。两个价格基准不能合并成"机制价 × 全部电量"。
- **省级公示口径不是正式文件**。云南 2027 第一次竞价参数标 C，正式全文未核实前不得写成 A；每年批次会变，不能跨年套用。

### 3.3 `project`：场址与资源

| 字段 | 单位 | 说明 |
|---|---|---|
| `name` | — | 项目名，入库用占位名 |
| `capacity_mw` | MW | 装机容量 |
| `p50_hours` | h | P50 年利用小时 |
| `p90_cv` | — | 资源变异系数，用于折算 P90 |
| `cod` | 日期 | 商运日 `YYYY-MM-DD` |
| `grade` / `source` | — | 资源评估为私有数据，入库用 D 级占位值 |

### 3.4 `policy`：投决风格档

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 风格档名 | `yunnan-wind-bid-ceiling-v1` |
| `decision_rule` | 投决三条线 | `IRR>=hurdle and NPV>=0 and DSCR>=min` |
| `bid_strategy` | 申报策略 | `bid_at_after_tax_break_even_or_better` |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入 `summary.json` 与复核表。保守/激进风格应通过 `bid_strategy` 与敏感性档体现，不能直接改基准数字。

### 3.5 `data_contract`：输入契约

| 子块 | 文件 | 内容 |
|---|---|---|
| `resource` | `data/resource_demo.csv` | 首年 12 个月：`month`、`generation_mwh`、`capture_rate` |

路径相对实例目录；真实数据用绝对路径或仓库外目录。

## 4. 输入格式

```csv
month,generation_mwh,capture_rate
2028-01,28500.0,0.98
```

- 必须 12 行、同一自然年、月份升序；
- 发电量与捕获率非负，捕获率在 0–1；
- 加权捕获率 = Σ(月电量 × 月捕获率) ÷ Σ月电量；
- 数据隐含利用小时偏离 P50 超过 20% 时给出警告。

## 5. 填写流程（约 25 分钟）

1. **复制实例目录**：`cp -r instances/yunnan-wind-development-2027 instances/<省>-<项目>-<年度>`；
2. **改 `meta`**：实例名、省份、市场、规则版本、数据截止日与口径边界；
3. **核对 `rules`**：机制电价、覆盖比例、造价、融资逐块写 `grade` 与 `source`；公示口径标 C；
4. **填 `project`**：装机、P50、P90 变异系数、商运日；
5. **选 `policy`**：先沿用三条线投决规则，跑通后再调申报策略；
6. **替换 CSV**：按第 4 节导出入组首年 12 个月电量与捕获率；
7. **跑 `--check-config`**：机制价越界、覆盖比例超单体上限、资源不足 12 个月会直接报错；
8. **跑一次 `--demo`**：看 LCOE、税前/税后盈亏平衡价、投标阶梯、DSCR 与组合压力。

## 6. 运行与产物

```bash
# 配置校验 + 来源表
python skills/renewable-project-development/instances/yunnan-wind-development-2027/run.py --check-config

# 合成数据全流程
python skills/renewable-project-development/instances/yunnan-wind-development-2027/run.py --demo

# 真实数据（路径指向仓库外）
python skills/renewable-project-development/instances/yunnan-wind-development-2027/run.py \
  --resource /path/to/resource.csv --out /path/to/out
```

产物（默认 `out/demo/`）：

| 文件 | 内容 |
|---|---|
| `monthly.csv` | 逐月：净电量、机制电量、市场收入、差价、绿证、综合度电收入 |
| `finance.csv` | 20 年税后现金流：收入、运维、折旧、应税所得、所得税、累计现金流 |
| `bid.csv` | 申报价阶梯：NPV、IRR、回收期、最低 DSCR、相对盈亏平衡价、判定 |
| `sensitivity.csv` | 单项压力与组合压力：电量、捕获率、覆盖比例、造价、运维、限电、P90 |
| `summary.json` | 配置快照、风格指纹、资源、收入、LCOE、盈亏平衡、财务、投标、敏感性、警告 |
| `review.md` | 复核表：结论、资源、收入、成本、财务、投标区间、敏感性、口径提醒 |

## 7. 配置校验与实际拦截

`run.py` 会拒绝：

- 缺 `meta` 必填项、缺 `rules` / `project` / `policy` / `data_contract`；
- 任一规则块缺 `grade` 或 `source`，或 `grade` 不是 A/B/C/D 组合；
- 机制电价不在申报下限与上限之间；
- 覆盖比例不大于 0 或超过单体上限；
- 结算方式不是 `difference`；
- 单位造价或单位运维非正、负债率或折现率非正；
- 商运日不是 `YYYY-MM-DD`、装机或 P50 非正；
- 资源 CSV 不足 12 行、跨年、月份乱序或重复、电量非正、捕获率越界；
- 数据契约缺 `month` / `generation_mwh` / `capture_rate`。

会打印但**不拦截**的警告：D 级合成数据、省级竞价参数为公示口径、造价不含建设期利息与送出工程、限电按全电量比例简化、亏损结转与税收优惠未建模、P90 为变异系数近似。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉资源评估与投决的人 ~25 分钟；只需改 JSON 与 CSV |
| 运行时间 | 20 年现金流 + 多档申报价，单机 < 1 秒 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，公示口径写 `status` |
| 口径可复算 | 捕获价、机制差价、LCOE、NPV、IRR、DSCR 均可手算复核 |
| 投决可解释 | IRR / NPV / DSCR 三条线同时满足才判通过；任一项不满足要点名 |
| 数据本地 | 真实测风、询价、融资与税务条件不上传；仓库只存结构与 D 级样例 |
| 验收口径 | 不看单一报价的 IRR；看门槛是否同时满足、压力下是否仍过线、口径是否一致 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实项目；
- 真实数据用 `--resource/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实场址、测风数据、设备询价、融资条件、土地与接入协议写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增实例

1. 选一个**机制电价批次与申报区间已公示**的省份与项目类型；
2. 复制本实例，保留 `run.py` 的结算、LCOE 与现金流骨架，改机制参数、造价与融资；
3. 新建 `instance.json`，五个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本省易错点（捕获价 vs 均价、覆盖比例、单体上限、P90、限电、建设期利息）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

## 11. 相关入口

- 开发与并网方法正文：[`../SKILL.md`](../SKILL.md) 资源评估、LCOE、机制电价与投决章节
- 新能源项目开发与并网：[`knowledge/新能源项目开发与并网-2026-11.md`](../../../knowledge/新能源项目开发与并网-2026-11.md)
- 云南市场档案：[`knowledge/云南电力市场-2026-11.md`](../../../knowledge/云南电力市场-2026-11.md)
- 储能收益建模（对照）：[`knowledge/储能收益建模与数据源-2026-11.md`](../../../knowledge/储能收益建模与数据源-2026-11.md)
- 云南风电样板：[`yunnan-wind-development-2027/README.md`](yunnan-wind-development-2027/README.md)
