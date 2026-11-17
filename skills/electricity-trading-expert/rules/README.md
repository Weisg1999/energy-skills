# 省级规则包（rules/）

把散落在 `instance.json`、知识页和交易公告里的省级可校验参数收口为一份
JSON，供 `tools/rulecheck.py` 在申报前做只读校验。规则包不是新的实例包，
不改变 **23 个实例包 / 9 个技能**的计数。

## 1. 覆盖范围

当前覆盖 demo 组合涉及的 6 个省级市场，规则快照日为 **2026-11-17**：

| 省 | 文件 | 现货状态 | 点数 | 申报区间（元/MWh） | 出清区间（元/MWh） | 限价执行 | 主要附加块 |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| 山东 | `shandong.json` | active | 96×15min | −80 – 1,300 | −100 – 1,500 | hard | 容量、辅助服务、煤电、储能、配储 |
| 甘肃 | `gansu.json` | active | 96×15min | 40 – 500 | 40 – 650 | hard | 容量、辅助服务、省间 |
| 蒙西 | `mengxi.json` | active | 96×15min | −60 – 1,600（模型边界） | 待核 | model | 偏差、新能源机制、容量不适用 |
| 山西 | `shanxi.json` | active | 288×5min | 0 – 1,500 | 0 – 1,500 | hard（分档 soft） | 储能、熔断、容量待核 |
| 广东 | `guangdong.json` | active | 96×15min | −50 – 待核（软边界 1,800） | −50 – 1,800 | partial | 零售、绿电直连 |
| 江苏 | `jiangsu.json` | active | 96×15min | 0 – 待核（软边界 1,500） | 0 – 1,500 | partial | 零售 2027 |

“待核”不是 0，也不是可以自由申报的上限；`rulecheck.py` 只把它当软边界并
提示人工确认。文件头部只有 `as_of` 与省份元数据；`grade` 和 `source` 按规则
块分别标注，正文的待核项汇总在 `open_items`。

## 2. Schema v1

```json
{
  "schema_version": 1,
  "province": "山东",
  "market": "山东省级电力市场（中长期 + 现货 + 辅助服务）",
  "as_of": "2026-11-17",
  "spot": {
    "status": "active",
    "rule_version": "新版《山东电力市场规则（试行）》（2026-01-01 实施）",
    "effective_from": "2026-01-01",
    "effective_to": null,
    "verified_on": "2026-11-17",
    "grade": "B/C",
    "source": "……",
    "market_time_unit_min": 15,
    "points_per_day": 96,
    "declare_floor_cny_per_mwh": -80,
    "declare_cap_cny_per_mwh": 1300,
    "clear_floor_cny_per_mwh": -100,
    "clear_cap_cny_per_mwh": 1500,
    "limits_enforcement": "hard",
    "deadline": {"label": "D-1 09:00", "time": "09:00", "verified": false},
    "drafts": [],
    "notes": []
  },
  "capacity_compensation": {},
  "ancillary": {},
  "retail": {},
  "direct_connection": {},
  "interprovincial": {},
  "open_items": []
}
```

约定：

- 只有 `spot` 是必需块；其余块按省份实际市场拼接。
- 每个规则块都带 `status`、`effective_from`、`effective_to`、`grade`、`source`；
  能核到核验日的再加 `verified_on`。
- `status` 常用值：`active`、`pending_parameters`、`unverified`、
  `unverified_prices`、`not_applicable`、`draft`。
- `limits_enforcement` 决定越界级别：
  - `hard`：申报越界直接 `block`；
  - `partial`：下限按硬规则，上限按软边界（`warn`）；
  - `soft` / `model`：只提示，不阻断；
  - `asset_bands`（如山西火电 0–800、新能源 0–740）单独标 `soft`，命中只
    `warn`，不覆盖总区间。
- `drafts` 只存未生效口径，不能写入现行字段；`historical_limits` 只作历史
  对照，不能用于当前交易日。
- 草案、未核实、模型边界、D 级演示参数都保留原文标记；工具不会因为校验
  通过而把 B/C 升级成 A。

## 3. 申报前校验

```bash
# 组合 demo：12 个实例、6 个省级市场
python skills/electricity-trading-expert/tools/rulecheck.py --demo

# 单个实例；有申报 CSV 时自动读取 out/demo/bid_sheet.csv
python skills/electricity-trading-expert/tools/rulecheck.py \
  --instance skills/spot-bidding-quant/instances/shandong-thermal-2026-11

# 指定申报文件，并统一覆盖目标交易日
python skills/electricity-trading-expert/tools/rulecheck.py \
  --instance skills/spot-bidding-quant/instances/shandong-storage-2026-11 \
  --bid /path/to/bid_sheet.csv --as-of 2026-11-18
```

输出：

- `out/rulecheck/rulecheck.md`：总览、逐实例检查表、规则包未闭合项、边界；
- `out/rulecheck/rulecheck.json`：结构化明细，适合二次处理或接入盘面。

退出码：有 `block` 返回 1；`--strict` 时同时把 `warn` 视为失败。工具只读
本地文件，不连接交易系统、不提交报价、不下单。

### 3.1 判定语义

| 级别 | 含义 | 典型场景 |
| --- | --- | --- |
| `pass` | 已检查且未发现问题 | 点数、日期、限价、功率、SOC 均在范围内 |
| `warn` | 需人工确认，不能直接当作可报 | 规则未核实、软分档、近似 SOC、截止时点未核、草案/模型边界 |
| `block` | 违反已核实硬规则或结构上无法申报 | 点数不符、硬限价越界、负数量、覆盖缺失、重复 slot、功率/容量越界 |
| `skip` | 本实例不适用 | 年度包无现货申报、资产类别不参与容量补偿 |

实例总体状态：任一 `block` 即 `BLOCK`；否则任一 `warn` 即 `WARN`；否则
`PASS`。年度/零售/直连包没有申报 CSV 时只做配置与规则校验，不伪造申报
检查。

### 3.2 检查项

- 规则包：`schema_version`、省份匹配、现货有效期、点数与 MTU 一致性、限价
  上下限顺序、限价执行级别、核验时效（超过 180 天提示）、申报截止时点。
- 实例配置：`rules.spot` / `rules.energy(spot_*)` 与规则包的申报/出清限价、
  点数、MTU 比对；草案字段误用；煤电最小出力与运行成本补偿；储能最小
  功率/时长；配储比例与电网充电限制。
- 申报 CSV：列识别、slot 范围、全量/稀疏覆盖、重复 `(slot, side)`、申报
  日期、价格上下限、负数量；部分行日期或价格为空时降级为 `warn`，不把
  已核行通过当成整份文件通过；风电装机/预测上限；煤电 `must_run + 增量`
  与调频备用扣减；储能充放电功率与近似 SOC；光储净上网、充电来源与 SOC。
- 规则块：容量补偿资格与参数（含 `grid_storage`/`storage` 别名；山东电网侧
  独立储能目前列为 `unverified_types`，工具只提示“未核实”，不得默认计入）、
  辅助服务限价与容量比例重叠（重叠检查只按规则包登记比例，不替代实例申报
  容量核对）、偏差考核 D 级标记、零售保函/分时/结算、绿电直连用户数与
  60%/35%/20% 合规线、省间最小申报量与报价步长。

SOC 是近似校核：按 `energy_mwh`、RTE 平方根和申报充放电量逐点估算，未
考虑辅助用电、温控、衰减与 BMS 策略；实例缺少 `rte` 时按 100% 效率估算
并单独 `warn`，结果只用于申报前发现明显越界，实际以 BMS/PCS 和交易中心
结果为准。

### 3.3 支持的申报格式

| 资产 | 关键列 | 说明 |
| --- | --- | --- |
| 风电 | `slot, forecast_mw, declared_mw, bid_price_cny_per_mwh` | 96 点全量；申报量不得超过装机与参考预测 |
| 煤电 | `slot, must_run_mw, quantity_mw, price_cny_per_mwh` | 96 点全量；`must_run+quantity` 不得超过容量减调频备用 |
| 独立储能 | `slot, side, quantity_mw, price_cny_per_mwh` | 稀疏行；`side=charge/discharge`，同一 slot 不得同时充放 |
| 光储联合 | `slot, pv_reference_mw, charge_plan_mw, discharge_plan_mw, declared_net_export_mw, offer_price` | 96 点；配储充电原则上不超过光伏参考出力，净上网受并网上限约束 |

## 4. 新增或更新一个省

1. 复制结构最接近的规则文件，保留 `schema_version: 1`；
2. 先填 `spot` 的生效日、点数、MTU、申报/出清限价和执行级别；核不到的上限
   写 `null`，另用 `validation_upper_cny_per_mwh` + `soft`，不要猜一个硬值；
3. 按市场实际追加容量、辅助服务、零售、直连或省间块；每条都写
   `source`、`grade`、`effective_from`，能核到日期的写 `verified_on`；
4. 草案放 `drafts`，历史口径放 `historical_limits`，不要把两者写进现行字段；
5. 把未闭合项写入 `open_items`，并在 `rulecheck.py` 的
   `PROVINCE_RULE_FILES` 里登记；
6. 跑 `--demo` 和 `tools/selftest.py` 的 M 段，确认没有把 `warn` 静默升级为
   `pass`。

## 5. 边界

- 所有实例与申报数据均为 **D 级合成样板**，不对应任何真实机组、合同或计量；
- 规则包是申报前辅助校验，不替代交易中心最新公告、并网调度协议、合同和
  结算单；
- 规则包不构成报价、交易、投资或法律建议；正式申报前必须由交易员复核
  限价、截止时点、ATC、考核与偏差条款；
- 工具只读，不写入实例包、不连接交易系统、不自动下单。
