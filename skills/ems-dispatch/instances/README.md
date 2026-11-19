# EMS 实例包：一省一主体的可配置调度切片

> 目录定位：`skills/ems-dispatch/instances/` 是 **EMS 调度的样板实例层**，不是知识模块，不改变知识库的 111 模块 / 13 分区计数。每个子目录是"一省 + 一个能源运营主体 + 一个规则版本"的配置包，运营主体只改 JSON 与 CSV，不改代码。当前两个纵向切片：
>
> - **江苏零碳园区微网**（用户侧）：并网不上网、需量控制、孤岛校核，单位 kW/kWh；
> - **山东独立储能电站日运行**（电网侧）：现货能量套利 + AGC/一次调频考核复盘，单位 MW/MWh。

## 1. 为什么要有这一层

引擎层（`tools/dispatch.py`、`microgrid.py`、`storage.py`、`curves.py`、`market.py`）回答"给定曲线与设备约束，怎么排充放电、怎么算电费/收益、怎么校核孤岛与考核"；实例层回答"**这个主体、这套电价与规则、这块储能，套利和需量/考核怎么取舍，碳指标怎么算，孤岛撑不撑得住，考核扣多少**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 动态规划调度、储能模型、微网约束、电费/考核函数 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省电价结构 + 主体资产 + 调度风格 + 数据契约 | 情景对比、需量搜索/考核复盘、逐点调度、碳核算、孤岛校核、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏的运行复盘 | 按错误类型索引的案例库 | 未建，需真实计量与结算数据积累 |

私有数据按主体不同：园区是**96 点负荷与光伏、分时电价与需量单价、储能参数与质保、保安负荷清单、并网容量**；电站是**96 点现货价格、AGC 指令与频率偏差、储能参数与质保、并网容量、考核细则参数**。实例层把这些挡在本地，只把结构与口径放进仓库。

## 2. 目录结构

```
instances/
├── README.md                              # 本文件：schema、流程、验收
├── jiangsu-zero-carbon-park-ems-2026-11/  # 江苏零碳园区微网（用户侧）
│   ├── instance.json                      # 唯一配置入口
│   ├── run.py                             # 校验 → 基线 → 套利 → 需量搜索 → 碳 → 孤岛 → 敏感性
│   ├── make_demo.py                       # D 级合成 96 点数据生成器
│   ├── README.md                          # 本实例的命令、产物、基准数字、参数状态
│   ├── pitfalls.md                        # 园区微网 EMS 易错点
│   ├── data/profile_demo.csv              # 代表日 96 点负荷/光伏/电价/时段
│   └── out/demo/                          # 运行产物（可删除重建）
└── shandong-storage-station-ems-2026-11/  # 山东独立储能电站日运行（电网侧）
    ├── instance.json                      # 唯一配置入口
    ├── run.py                             # 校验 → 能量套利 → AGC 复盘 → 一次调频复盘 → 综合经济性
    ├── make_demo.py                       # D 级合成 96 点数据生成器
    ├── README.md                          # 本实例的命令、产物、基准数字、参数状态
    ├── pitfalls.md                        # 储能电站 EMS 日运行易错点（8 条）
    ├── data/profile_demo.csv              # 代表日 96 点价格/AGC 指令/频率偏差/时段
    └── out/demo/                          # 运行产物（可删除重建）
```

## 3. `instance.json` 五个块

两个切片共用 `meta` / `rules` / `assets` / `policy` / `data_contract` 五块骨架，规则子块与单位按主体不同。

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-主体-年月`，与目录同名 |
| `province` / `market` | 省份与市场 | 写全称；园区为微网（并网不上网），电站为独立储能（现货能量 + 辅助服务考核复盘） |
| `entity_type` | 主体类型 | 园区能源运营主体 / 独立储能电站运营主体 |
| `rule_version` | 规则版本 | 冻结到一个版本；电站考核口径仅参照两个细则，不替代现行结算细则 |
| `data_cutoff` | 数据截止日 | 与代表日、电价快照一致 |
| `grade` | 整体来源级别 | B/C；合成算例为 D |
| `scope` | 纳入/未纳入科目 | 写清边界（园区是否含绿电直连合规/碳抵消；电站是否含实时出清/里程竞价/容量拍卖） |
| `units` | 单位约定 | 园区：kW / kWh / CNY/kWh / 需量 CNY/kW·月；电站：MW / MWh / CNY/MWh / 考核电量 MWh / 频率 Hz |
| `disclaimer` | 免责声明 | D 级样板必须写明不构成评价、并网验收、考核申诉或投资建议 |

### 3.2 `rules`：电价、储能与主体特有规则

每个规则子块都必须带 `grade` 和 `source`，缺一个就拒绝运行。子块按切片不同：

| 子块 | 园区微网 | 储能电站 | 关键字段 |
|---|---|---|---|
| `tariff` | ✓ | ✓ | 分时电价；园区 `peak/flat/valley_cny_per_kwh` + `demand_charge_cny_per_kw_month`；电站 `peak/flat/valley/midday_dip_cny_per_mwh`；均带 `status`（时段划分） |
| `storage` | ✓ | ✓ | 容量、充放电功率、效率（园区分充放效率，电站 `rte`）、SOC 窗口、`degradation_cny_per_kwh` |
| `carbon` | ✓ | — | `grid_factor_tco2_per_mwh`、`tce_per_mwh`、`status`（单位说明） |
| `island` | ✓ | — | `critical_load_ratio`、`reserve_ratio`、`pv_availability`、`day_window`、`night_window` |
| `assessment` | — | ✓ | AGC 响应时间/速率能力/精度误差与门槛/考核系数；一次调频调差 `r`/死区/性能/峰段上调可用功率/贡献门槛/考核系数 |

三条硬规则：

- **峰 ≥ 平 ≥ 谷**（电站另有午间深谷，须 ≤ 谷）。配置校验直接拒绝倒挂；分时时段必须与 CSV 的 `segment` 标签一致。
- **可用电量按 SOC 窗口算**，不是额定容量。园区 4 MWh × (0.95 − 0.20) = 3.0 MWh；电站 200 MWh × (0.9 − 0.1) = 160 MWh。孤岛能力与考核裕度都不能用额定值。
- **口径不能混用**。园区碳指标分两种：单位能耗碳排放 = 排放 ÷ 能耗（tce），度电碳排放 = 排放 ÷ 电量（tCO2/MWh）；电站**考核电量 ≠ 电费**，考核电量 × 平段电价（D 级假设）才折成考核电费。

### 3.3 `assets`：主体资产

| 切片 | 字段 | 单位 | 说明 |
|---|---|---|---|
| 园区 | `pv_kwp` | kWp | 光伏装机；CSV 中光伏不得超过装机的 105% |
| 园区 | `pcc_import_kw` / `pcc_export_kw` | kW | 并网受电 / 上网容量；园区上网为 0（并网不上网） |
| 园区 | `demand_cap_candidates_kw` | kW | 需量上限候选集，非空且不重复 |
| 电站 | `pcc_mw` | MW | 并网容量 |
| 共用 | `grade` / `source` | — | 资产为私有数据，入库用 D 级占位值 |

### 3.4 `policy`：调度风格档

| 字段 | 含义 | 园区取值 | 电站取值 |
|---|---|---|---|
| `profile_id` | 风格档名 | `zero-carbon-park-ems-demand-cap-v1` | `shandong-storage-station-ems-assessment-v1` |
| `objective` | 优化目标 | `energy_and_demand_cost` | `energy_revenue` |
| `terminal` | 期末 SOC 处理 | `cycle`（回到初始）或 `free` | `cycle` 或 `free` |
| `states` | 动态规划 SOC 离散数 | 400 | 400 |
| `demand_cap_selection` | 需量上限选择规则 | `min_total_cost` | —（电站无需量） |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入 `summary.json` 与复核表。换目标（园区只省电量费 vs 电费+需量；电站能量套利 vs 留调频裕度）会改变调度结果，复盘时必须先看指纹。电站当前指纹 `109cd87cce2e`。

### 3.5 `data_contract`：输入契约

| 切片 | 文件 | 96 点字段 |
|---|---|---|
| 园区 | `data/profile_demo.csv` | `interval`、`time`、`load_kw`、`pv_kw`、`buy_cny_per_kwh`、`segment` |
| 电站 | `data/profile_demo.csv` | `interval`、`time`、`price_cny_per_mwh`、`agc_signal_mw`、`freq_deviation_hz`、`segment` |

代表日口径：96 点 × 15 分钟，序号与时间连续，`segment` 与 `rules.tariff.status` 一致。真实数据用绝对路径或仓库外目录。

## 4. 输入格式

园区微网：

```csv
interval,time,load_kw,pv_kw,buy_cny_per_kwh,segment
0,00:00,4200.0,0.0,0.28,valley
```

储能电站：

```csv
interval,time,price_cny_per_mwh,agc_signal_mw,freq_deviation_hz,segment
0,00:00,200.0,0.0,0.0,valley
```

- 必须 96 行，`interval` 从 0 到 95，`time` 与序号对应；
- 园区：负荷、光伏非负，光伏不超过 `assets.pv_kwp × 1.05`，负荷与光伏全年电量为正；
- 电站：电价为正，AGC 指令在 ±额定功率内，频率偏差在 ±1 Hz 内；
- 每点电价必须等于该点 `segment` 对应的电价。

## 5. 填写流程（约 20 分钟）

1. **复制实例目录**：`cp -r instances/<最接近的切片> instances/<省>-<主体>-<年月>`；
2. **改 `meta`**：实例名、省份、主体、规则版本、数据截止日、单位与口径边界；
3. **核对 `rules`**：电价、储能与主体特有块（园区碳/孤岛，电站考核）逐块写 `grade` 与 `source`；D 级假设单列；
4. **填 `assets`**：园区光伏/并网容量/需量候选集，电站并网容量；
5. **选 `policy`**：先沿用 `cycle` 与 400 个 SOC 状态，跑通后再调；
6. **替换 CSV**：按第 4 节导出代表日 96 点；
7. **跑 `--check-config`**：时段与电价不一致、参数越界、SOC 窗口非法会直接报错；
8. **跑一次 `--demo`**：园区看三情景成本/需量搜索/碳/孤岛；电站看能量套利/AGC/一次调频/综合净收益。

## 6. 运行与产物

园区微网：

```bash
python skills/ems-dispatch/instances/jiangsu-zero-carbon-park-ems-2026-11/run.py --check-config
python skills/ems-dispatch/instances/jiangsu-zero-carbon-park-ems-2026-11/run.py --demo
python skills/ems-dispatch/instances/jiangsu-zero-carbon-park-ems-2026-11/run.py \
  --instance /path/to/instance.json --out /path/to/out
```

储能电站：

```bash
python skills/ems-dispatch/instances/shandong-storage-station-ems-2026-11/run.py --check-config
python skills/ems-dispatch/instances/shandong-storage-station-ems-2026-11/run.py --demo
python skills/ems-dispatch/instances/shandong-storage-station-ems-2026-11/run.py \
  --instance /path/to/instance.json --out /path/to/out
```

园区产物（默认 `out/demo/`）：

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

电站产物（默认 `out/demo/`）：

| 文件 | 内容 |
|---|---|
| `dispatch.csv` | 逐 15 分钟：电价、充放电功率、下网/上网、SOC |
| `agc.csv` | 逐时段 AGC：指令、需求速率、速率/精度合格判定、考核电量 |
| `freq.csv` | 逐时段一次调频：频差、理论/实际出力、贡献比、考核电量 |
| `summary.json` | 配置快照、风格指纹、来源表、套利、AGC、一次调频、综合经济性、警告 |
| `review.md` | 复核表：结论、套利调度、AGC 复盘、一次调频复盘、综合经济性、口径提醒 |

## 7. 配置校验与实际拦截

两个 `run.py` 共同拒绝：

- 缺 `meta` 必填项、缺 `rules` / `assets` / `policy` / `data_contract`；
- 任一规则块缺 `grade` 或 `source`，或 `grade` 不是 A/B/C/D 组合；
- 电价不满足峰 ≥ 平 ≥ 谷（电站午间深谷须 ≤ 谷）；
- 储能容量/功率非正、效率不在 (0,1]、SOC 窗口非法；
- 调度期末规则不是 `cycle` / `free`；
- CSV 不是 96 行、序号或时间不连续、电价与时段不符。

园区额外拒绝：孤岛窗口不是两元素或起止倒置；需量候选集为空或重复；负荷/光伏为负、光伏超装机、负荷或光伏电量为零。

电站额外拒绝：AGC 指令超 ±额定功率；频率偏差超 ±1 Hz；一次调频峰段上调可用功率超过额定功率。

会打印但**不拦截**的警告：D 级合成数据、电网因子/考核公式为取整或教学假设、分时电价结构不是现行目录/出清价、需量单价与考核系数为示例值、储能与孤岛/考核参数为建模假设。

## 8. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉主体台账的人 ~20 分钟；只需改 JSON 与 CSV |
| 运行时间 | 园区 96 点 × 3 情景 + 6 个需量候选、电站 96 点套利 + 考核复盘，单机 < 5 秒 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 口径可复算 | 电量电费/收益、需量电费、退化成本、碳指标、考核电量与考核电费均可手算复核 |
| 约束可解释 | 园区不可行需量候选必须给原因、孤岛结论列可用能量与缺口；电站考核按逐事件计算，不能用聚合贡献比一刀切 |
| 数据本地 | 真实负荷/光伏/价格/AGC 指令/频率事件/结算单不上传；仓库只存结构与 D 级样例 |
| 验收口径 | 不看单日省多少/赚多少；看约束是否满足、口径是否一致、结论是否可复现 |

## 9. 数据安全边界

- 仓库内的 `data/*.csv` 是 `make_demo.py` 生成的合成数据（D 级），不代表任何真实园区或电站；
- 真实数据用 `--instance/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录（`instances/*/out/`）；
- 不要把真实园区/电站名、负荷曲线、光伏出力、现货价格、AGC 指令、频率事件、结算单、保安负荷清单写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 10. 新增实例

1. 选一个**电价结构、并网方式与主体边界明确**的园区或电站；
2. 复制最接近的切片，保留 `run.py` 的调度与校验骨架，改电价、储能与主体特有规则（园区碳/孤岛/需量，电站考核）；
3. 新建 `instance.json`，五个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本主体易错点（园区：套利抬需量、SOC 窗口、孤岛额定 vs 可用、碳口径、光伏超装；电站：容量互斥、考核电量 ≠ 电费、逐事件 vs 聚合贡献比、峰段上调裕度）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

## 11. 相关入口

- EMS 方法正文：[`../SKILL.md`](../SKILL.md) 调度模型、储能约束、需量管理与涉网考核章节
- 微网 EMS：[`knowledge/微网EMS优化调度-算法与工程-2026-11.md`](../../../knowledge/微网EMS优化调度-算法与工程-2026-11.md)
- 储能 EMS：[`knowledge/储能EMS优化调度-算法与工程-2026-11.md`](../../../knowledge/储能EMS优化调度-算法与工程-2026-11.md)
- 场站群与集控 EMS 架构：[`knowledge/场站群与集控EMS架构-2026-11.md`](../../../knowledge/场站群与集控EMS架构-2026-11.md)
- EMS 数据接口参考架构：[`knowledge/EMS数据接口参考架构-2026-11.md`](../../../knowledge/EMS数据接口参考架构-2026-11.md)
- 并网测试与涉网验收实务清单：[`knowledge/并网测试与涉网验收实务清单-2026-11.md`](../../../knowledge/并网测试与涉网验收实务清单-2026-11.md)
- 频率、惯量与灵活性供需：[`knowledge/频率惯量与灵活性供需-2026-11.md`](../../../knowledge/频率惯量与灵活性供需-2026-11.md)
- 预测误差→申报→EMS 闭环：[`knowledge/预测误差申报与EMS闭环-2026-11.md`](../../../knowledge/预测误差申报与EMS闭环-2026-11.md)
- 零碳园区：[`knowledge/综合能源与零碳园区-2026-11.md`](../../../knowledge/综合能源与零碳园区-2026-11.md)
- 江苏市场档案：[`knowledge/江苏电力市场-2026-11.md`](../../../knowledge/江苏电力市场-2026-11.md)
- 江苏园区样板：[`jiangsu-zero-carbon-park-ems-2026-11/README.md`](jiangsu-zero-carbon-park-ems-2026-11/README.md)
- 山东储能电站样板：[`shandong-storage-station-ems-2026-11/README.md`](shandong-storage-station-ems-2026-11/README.md)