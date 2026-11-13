# EMS 实例包：一省一园区的可配置微网调度切片

> 目录定位：`skills/ems-dispatch/instances/` 是**园区微网 EMS 的样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是"一省 + 一个能源运营主体 + 一个规则版本"的配置包，园区能源经理只改 JSON 与 CSV，不改代码。当前一个切片：江苏零碳园区 2026-11（并网不上网、需量控制、孤岛校核）。

## 1. 为什么要有这一层

引擎层（`tools/dispatch.py`、`microgrid.py`、`storage.py`、`curves.py`、`market.py`）回答"给定曲线与设备约束，怎么排充放电、怎么算电费、怎么校核孤岛"；实例层回答"**这个园区、这套电价与需量、这块储能，套利和需量控制怎么取舍，碳指标怎么算，孤岛到底撑不撑得住**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 动态规划调度、储能模型、微网约束、电费函数 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省电价结构 + 园区资产 + 调度风格 + 数据契约 | 情景对比、需量搜索、逐点调度、碳核算、孤岛校核、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的园区运行复盘 | 按错误类型索引的案例库 | 未建，需真实计量与结算数据积累 |

园区 EMS 的私有数据不是机组铭牌，而是**96 点负荷与光伏、分时电价与需量单价、储能设备参数与质保、保安负荷清单、并网容量**。实例层把这些挡在本地，只把结构与口径放进仓库。

## 2. 目录结构

```
instances/
├── README.md                              # 本文件：schema、流程、验收
└── jiangsu-zero-carbon-park-ems-2026-11/  # 江苏零碳园区微网
    ├── instance.json                      # 唯一配置入口
    ├── run.py                             # 校验 → 基线 → 套利 → 需量搜索 → 碳 → 孤岛 → 敏感性
    ├── make_demo.py                       # D 级合成 96 点数据生成器
    ├── README.md                          # 本实例的命令、产物、基准数字、参数状态
    ├── pitfalls.md                        # 园区微网 EMS 易错点
    ├── data/profile_demo.csv              # 代表日 96 点负荷/光伏/电价/时段
    └── out/demo/                          # 运行产物（可删除重建）
```

## 3. `instance.json` 五个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-园区-年月`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称；本包为园区微网（并网不上网） |
| `entity_type` | 主体类型 | 零碳园区能源运营主体 |
| `rule_version` | 规则版本 | 零碳园区政策与绿电直连边界文件；冻结到一个版本 |
| `data_cutoff` | 数据截止日 | 与代表日、电价快照一致 |
| `grade` | 整体来源级别 | B/C；合成算例为 D |
| `scope` | 纳入/未纳入科目 | 写清是否含绿电直连合规、绿证与碳抵消、园区评价申报 |
| `units` | 单位约定 | 功率 kW；电量 kWh；电价 CNY/kWh；需量 CNY/kW·月 |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成园区评价或投资建议 |

### 3.2 `rules`：电价、碳、储能与孤岛

每个规则子块都必须带 `grade` 和 `source`，缺一个就拒绝运行：

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `tariff` | 分时电价与需量 | `peak/flat/valley_cny_per_kwh`、`demand_charge_cny_per_kw_month`、`status`（时段划分） |
| `carbon` | 碳核算口径 | `grid_factor_tco2_per_mwh`、`tce_per_mwh`、`status`（单位说明） |
| `storage` | 储能参数 | `capacity_kwh`、充放电功率、效率、SOC 窗口、`degradation_cny_per_kwh` |
| `island` | 孤岛校核 | `critical_load_ratio`、`reserve_ratio`、`pv_availability`、`day_window`、`night_window` |

三条硬规则：

- **峰 ≥ 平 ≥ 谷**。配置校验直接拒绝倒挂；分时时段必须与 CSV 的 `segment` 标签一致。
- **可用电量按 SOC 窗口算**，不是额定容量。4 MWh × (0.95 − 0.20) = 3.0 MWh；孤岛能力不能用额定值。
- **碳指标口径分两种**。单位能耗碳排放 = 排放 ÷ 能耗（tce），度电碳排放 = 排放 ÷ 电量（tCO2/MWh）；两者不能混用。

### 3.3 `assets`：园区资产

| 字段 | 单位 | 说明 |
|---|---|---|
| `pv_kwp` | kWp | 光伏装机；CSV 中光伏不得超过装机的 105% |
| `pcc_import_kw` | kW | 并网受电容量 |
| `pcc_export_kw` | kW | 上网容量；本包为 0（并网不上网） |
| `demand_cap_candidates_kw` | kW | 需量上限候选集，非空且不重复 |
| `grade` / `source` | — | 资产为私有数据，入库用 D 级占位值 |

### 3.4 `policy`：调度风格档

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 风格档名 | `zero-carbon-park-ems-demand-cap-v1` |
| `objective` | 优化目标 | `energy_and_demand_cost` |
| `terminal` | 调度期末 SOC 处理 | `cycle`（回到初始）或 `free` |
| `states` | 动态规划 SOC 离散数 | 400 |
| `demand_cap_selection` | 需量上限选择规则 | `min_total_cost` |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入 `summary.json` 与复核表。换目标（只省电量费 vs 电费+需量）会改变调度结果，复盘时必须先看指纹。

### 3.5 `data_contract`：输入契约

| 子块 | 文件 | 内容 |
|---|---|---|
| `profile` | `data/profile_demo.csv` | 96 点：`interval`、`time`、`load_kw`、`pv_kw`、`buy_cny_per_kwh`、`segment` |

代表日口径：96 点 × 15 分钟，序号与时间连续，`segment` 与 `rules.tariff.status` 一致。真实数据用绝对路径或仓库外目录。

## 4. 输入格式

```csv
interval,time,load_kw,pv_kw,buy_cny_per_kwh,segment
0,00:00,4200.0,0.0,0.28,valley
```

- 必须 96 行，`interval` 从 0 到 95，`time` 与序号对应；
- 负荷、光伏非负；光伏不超过 `assets.pv_kwp × 1.05`；
- 每点电价必须等于该点 `segment` 对应的电价；
- 负荷与光伏全年电量必须为正。

## 5. 填写流程（约 20 分钟）

1. **复制实例目录**：`cp -r instances/jiangsu-zero-carbon-park-ems-2026-11 instances/<省>-<园区>-<年月>`；
2. **改 `meta`**：实例名、省份、主体、规则版本、数据截止日与口径边界；
3. **核对 `rules`**：电价、需量、储能、孤岛参数逐块写 `grade` 与 `source`；D 级假设单列；
4. **填 `assets`**：光伏、并网容量、需量候选集；
5. **选 `policy`**：先沿用 `cycle` 与 400 个 SOC 状态，跑通后再调；
6. **替换 CSV**：按第 4 节导出代表日 96 点；
7. **跑 `--check-config`**：时段与电价不一致、光伏超装机、SOC 窗口非法会直接报错；
8. **跑一次 `--demo`**：看三情景成本、需量搜索、逐点调度、碳指标与孤岛结论。

## 6. 运行与产物

```bash
# 配置校验 + 规则来源表
python skills/ems-dispatch/instances/jiangsu-zero-carbon-park-ems-2026-11/run.py --check-config

# 合成数据全流程
python skills/ems-dispatch/instances/jiangsu-zero-carbon-park-ems-2026-11/run.py --demo

# 换一份配置（数据路径可指向仓库外）
python skills/ems-dispatch/instances/jiangsu-zero-carbon-park-ems-2026-11/run.py \
  --instance /path/to/instance.json --out /path/to/out
```

产物（默认 `out/demo/`）：

| 文件 | 内容 |
|---|---|
| `scenarios.csv` | 基线、仅能量套利、需量封顶的成本与碳指标 |
| `demand_cap_search.csv` | 六个需量上限候选的可行性与总电费 |
| `dispatch.csv` | 最优情景逐 15 分钟：下网、充放电、弃光、SOC |
| `carbon.csv` | 两种排放因子下的排放量与单位能耗碳排放 |
| `island.csv` | 白天 / 夜间孤岛保安负荷校核 |
| `sensitivity.csv` | 需量单价 30/50 元与光伏 −10% 的同情景对比 |
| `summary.json` | 配置快照、风格指纹、来源表、情景、碳、孤岛、敏感性、警告 |
| `review.md` | 复核表：结论、成本、碳、孤岛、敏感性、口径提醒 |

## 7. 配置校验与实际拦截

`run.py` 会拒绝：

- 缺 `meta` 必填项、缺 `rules` / `assets` / `policy` / `data_contract`；
- 任一规则块缺 `grade` 或 `source`，或 `grade` 不是 A/B/C/D 组合；
- 电价不满足峰 ≥ 平 ≥ 谷；
- 储能容量/功率非正、效率不在 (0,1]、SOC 窗口非法；
- 孤岛窗口不是两元素、起止倒置；
- 需量候选集为空或重复；
- 调度期末规则不是 `cycle` / `free`；
- CSV 不是 96 行、序号或时间不连续、负荷/光伏为负、光伏超装机、电价与时段不符、负荷或光伏电量为零。

会打印但**不拦截**的警告：D 级合成数据、电网因子为取整假设、分时电价结构不是江苏现行目录电价、需量单价为示例值、储能与孤岛参数为建模假设。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉园区台账的人 ~20 分钟；只需改 JSON 与 CSV |
| 运行时间 | 96 点 × 3 情景 + 6 个需量候选，单机 < 5 秒 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 口径可复算 | 电量电费、需量电费、退化成本、碳指标均可手算复核 |
| 约束可解释 | 不可行需量候选必须给原因；孤岛结论必须列可用能量与缺口 |
| 数据本地 | 真实负荷、光伏、电价、需量与保安负荷清单不上传；仓库只存结构与 D 级样例 |
| 验收口径 | 不看单日省多少钱；看约束是否满足、口径是否一致、结论是否可复现 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实园区；
- 真实数据用 `--instance/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实园区名、负荷曲线、光伏出力、结算单、保安负荷清单写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增实例

1. 选一个**电价结构、并网方式与园区边界明确**的园区；
2. 复制本实例，保留 `run.py` 的调度与校验骨架，改电价、储能、孤岛与需量候选；
3. 新建 `instance.json`，五个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本园区易错点（套利抬需量、SOC 窗口、孤岛额定 vs 可用、碳口径、光伏超装）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

## 11. 相关入口

- EMS 方法正文：[`../SKILL.md`](../SKILL.md) 调度模型、储能约束与需量管理章节
- 微网 EMS：[`knowledge/微网EMS优化调度-算法与工程-2026-11.md`](../../../knowledge/微网EMS优化调度-算法与工程-2026-11.md)
- 储能 EMS：[`knowledge/储能EMS优化调度-算法与工程-2026-11.md`](../../../knowledge/储能EMS优化调度-算法与工程-2026-11.md)
- 零碳园区：[`knowledge/综合能源与零碳园区-2026-11.md`](../../../knowledge/综合能源与零碳园区-2026-11.md)
- 江苏市场档案：[`knowledge/江苏电力市场-2026-11.md`](../../../knowledge/江苏电力市场-2026-11.md)
- 江苏园区样板：[`jiangsu-zero-carbon-park-ems-2026-11/README.md`](jiangsu-zero-carbon-park-ems-2026-11/README.md)
