# 电费优化实例层：一省一用户的账单切片

> 目录定位：`skills/tariff-bill-optimization/instances/` 是**样板实例层**，不是知识模块，不改变知识库的 101 模块 / 13 分区计数。每个子目录是"一省 + 一类用户 + 一套电价参数"的配置包，用户侧顾问只改 JSON 与 CSV，不改代码。

## 1. 为什么有这一层

引擎层（`tools/bill.py`、`tools/demand.py`、`tools/tariff.py`）回答"科目怎么拆、基本电费怎么算、负荷怎么移"；实例层回答"**你这个省、这个用户、这张电费单，贵在哪、报多少、储能削峰能省多少**"。三层分工：

| 层 | 输入 | 输出 | 是否入库 |
|---|---|---|---|
| 引擎层 | 公式、科目、申报闭式解 | 函数与自测 | 是，`tools/` |
| 实例层 | 本省电价参数 + 用户负荷 + 储能参数 | 账单、三方式比选、削峰收益、复核表 | 是，本目录（参数脱敏） |
| 案例层 | 真实脱敏账单与负荷 | 按异常类型索引的案例库 | 暂未建 |

## 2. 目录结构

```
instances/
├── README.md                          # 本文件：schema、填写流程、验收
└── jiangsu-ci-storage-2026-11/        # 江苏 10 kV 工商业用户 + 用户侧储能
    ├── instance.json
    ├── run.py
    ├── make_demo.py
    ├── README.md
    ├── pitfalls.md
    ├── data/load_demo.csv
    └── out/demo/
```

每个实例目录结构一致：`instance.json`（唯一配置入口）、`run.py`（校验 → 账单 → 削峰 → 复核）、`make_demo.py`（D 级合成负荷）、`README.md`、`pitfalls.md`、`data/`、`out/demo/`。

## 3. `instance.json` 六个块

### 3.1 `meta`：身份与边界

| 字段 | 含义 | 要求 |
|---|---|---|
| `instance_id` | 实例唯一名 | `省-用户类型-年月`，与目录同名 |
| `province` / `market` | 省份与价格通道 | 写清目录、代理购电还是市场化 |
| `entity_type` | 用户类型 | 工商业用户 / 数据中心 / 园区等 |
| `rule_version` | 电价参数版本 | 冻结到一份文件或一个日期 |
| `data_cutoff` | 数据截止日 | 与账单期间一致 |
| `grade` | 整体来源级别 | A/B/C/D；`D` 表示合成样板 |
| `scope` | 纳入/未纳入科目 | 写清边界，防止把削峰收益当净利 |
| `units` | 单位约定 | kW、kWh、kVA、CNY、CNY/kWh、CNY/kW·月 |

### 3.2 `rules`：电价与计费规则

每个子块必须带 `grade` 与 `source`，缺一个校验就拒绝运行。

| 子块 | 用途 | 关键字段 |
|---|---|---|
| `tariff` | 分时时段、电能量价、输配/系统/基金 | `periods`、`prices`、`transmission`、`system`、`fund` |
| `basic_charge` | 两部制基本电费 | `capacity_price`、`demand_price`、`threshold`、`overrun_multiplier`、`floor_ratio` |
| `power_factor` | 力率考核 | `standard`、`penalty_per_step`、`reward_per_step`、上限 |
| `storage_participation` | 用户侧储能参与方式 | `mode`、`constraint`、`settlement` |
| `market_channel` | 价格通道与代理购电 | `channel`、`spot_status`、`note` |

**时段表必须覆盖 0–24 时、无重叠、无缺口**，由 `tariff.validate_periods` 校验。草案、征求意见值放 `status` 字段，不写进生效参数。

### 3.3 `asset`：用户与储能参数

| 字段 | 单位 | 说明 |
|---|---|---|
| `transformer_kva` | kVA | 变压器容量，40% 下限与容量计费的基数 |
| `high_voltage_motor_kva` | kVA | 高压电动机容量，省级 40% 下限可能合并计算 |
| `contract_demand_kw` | kW | 当前合同需量（以下简称"申报值"） |
| `power_factor` | — | 月功率因数 |
| `storage_power_kw` | kW | 用户侧储能功率 |
| `storage_energy_kwh` | kWh | 储能额定能量 |
| `storage_usable_ratio` | — | 可用能量比例 |
| `storage_rte` | — | 往返效率 |
| `storage_degradation_cny_per_kwh` | CNY/kWh | 按吞吐量线性折旧 |
| `storage_capex_cny_per_kwh` | CNY/kWh | 仅用于静态回收期参考，不构成投决 |
| `storage_fixed_opex_cny_per_kw_year` | CNY/kW·年 | 运维分摊 |

### 3.4 `policy`：削峰与申报策略

| 字段 | 含义 | 典型取值 |
|---|---|---|
| `profile_id` | 策略档名 | `jiangsu-ci-storage-balanced-v1` |
| `shave_ratio` | 目标削峰比例 | 0.10–0.15 |
| `charge_period` | 充电时段 | `valley` |
| `discharge_periods` | 放电时段 | `["peak", "critical"]` |
| `max_cycles_per_day` | 日循环上限 | 1.0 |
| `min_spread_cny_per_kwh` | 最小峰谷价差 | 低于此值不出手 |
| `basic_charge_mode` | 基准计费方式 | `contract` / `capacity` / `actual` |
| `declaration_strategy` | 申报策略 | `monthly_optimal`（A/1.05） |

风格指纹 = `policy` 块规范化 JSON 的 SHA-1 前 12 位，写入复核表。

### 3.5 `contracts`：零售套餐/代理购电

当前版本只记录边界：`retail_package` 为 `null` 表示本包只做账单与削峰，不做套餐比价；套餐比价用 `tools/retail.py` 单独跑。不要把零售电能量价与到户价混在一起。

### 3.6 `data_contract`：输入契约

```csv
month,slot,load_kw
1,0,393.6
1,1,393.6
...
```

- `month` 1–12，每月 96 点，15 分钟；
- 只能有一个代表日；同一月内 slot 0–95 连续无缺口；
- 负荷为 kW，非负；充电后负荷不得为负；
- 真实数据用 `--load` 指向仓库外路径。

## 4. 运行与产物

```bash
cd skills/tariff-bill-optimization/instances/jiangsu-ci-storage-2026-11

python run.py --check-config
python run.py --demo
python run.py --load /path/to/load.csv --out out/my-case
```

产物（默认 `out/<run>/`）：

- `bill_baseline.csv`：逐月账单科目（电能量、输配、系统、基金、基本电费、力率）；
- `bill_with_storage.csv`：加储能后的逐月账单、削峰量、退化成本、净节省；
- `basic_charge_compare.csv`：容量/合同需量/实际需量三方式逐月对比；
- `demand.csv`：削峰前后最大需量、申报值、削减量；
- `summary.json`：年账单、年节省、回收期、来源与告警；
- `review.md`：复核表与三个复核问题。

## 5. 配置校验与实际拦截

`run.py` 会拒绝：

- 缺 `meta` 必填项、缺 `rules`/`asset`/`policy`/`data_contract`；
- 任一规则块缺 `grade` 或 `source`；
- 时段表缺口、重叠、越界；
- `shave_ratio` 不在 (0, 1)、储能功率/能量非正；
- 合同需量低于 40% 下限或高于变压器容量；
- 功率因数不在 (0, 1]；
- 输入多月份缺 slot、重复、负荷为负、月份不在 1–12。

## 6. 验收标准

| 项 | 标准 |
|---|---|
| 填写时间 | 熟悉账单的人 ~30 分钟；只改 JSON 与 CSV |
| 运行时间 | 12 月 × 96 点，单机 < 5 秒 |
| 非法配置 | 明确报错并指出字段路径，不静默降级 |
| 规则溯源 | 每个规则块有 `grade` + `source`，未核实项写 `status` |
| 账单恒等 | 各科目之和 = 合计；平均价 = 合计 ÷ 电量 |
| 削峰口径 | 削峰前后最大需量、申报值、基本电费三者可复算 |
| 数据本地 | 真实账单、负荷、储能参数不上传，仓库只存结构与 D 级样例 |
| 验收口径 | **不看演示节省额**；看科目是否拆对、申报是否可执行、口径是否可复现 |

## 7. 数据安全边界

- 仓库内 `data/*.csv` 是 `make_demo.py` 生成的合成负荷（D 级），不对应任何真实用户；
- 真实数据用 `--load/--out` 指向仓库外路径，或放本地被 `.gitignore` 覆盖的目录；
- 不要把真实户号、账单、负荷、变压器容量写进 `instance.json` 后提交；
- 实例包只记录"方法与结构"，不记录"商业项目溯源"。

## 8. 新增实例

1. 选一个**电价文件稳定、账单科目齐全**的省份与用户类型；
2. 复制 `jiangsu-ci-storage-2026-11`，保留 `run.py` 的校验骨架；
3. 新建 `instance.json`，六个块齐全，规则值全部带来源级别；
4. 在 `pitfalls.md` 写本省易错点（40% 下限、105% 超需、双路进线、力率基数、分时退出）；
5. 跑 `--check-config` 与 `--demo`，把关键输出写进实例 `README.md`；
6. 不改知识库计数，不改 `knowledge/`；实例是技能目录内的配置层。

已落地的其他主体层：现货侧见 [`spot-bidding-quant/instances/`](../../spot-bidding-quant/instances/README.md)，储能投资侧见 [`storage-investment-operations/instances/`](../../storage-investment-operations/instances/README.md)，售电侧见 [`retail-electricity-risk/instances/`](../../retail-electricity-risk/instances/README.md)，VPP 侧见 [`virtual-power-plant/instances/`](../../virtual-power-plant/instances/README.md)。
