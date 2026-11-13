# 安徽独立储能 · 容量电价 2027 样板实例

> 本目录是 `skills/storage-investment-operations/instances/` 的第一个纵向切片：**一省（安徽）+ 一主体（电网侧独立新型储能）+ 一个规则版本（皖发改价格〔2026〕526号 + 现货 2026-09-09 转正）**。配置改 `instance.json`，数据换 `data/*.csv`，运行 `run.py`，不改代码。
>
> 所有演示数据为 **D 级合成数据**，不代表任何真实电站、真实报价或真实收益。

## 1. 一条命令

```bash
# 配置校验 + 来源分级
python skills/storage-investment-operations/instances/anhui-storage-2027/run.py --check-config

# 合成数据全流程：时长阶梯 → 情景套利 → 98% 可用率考核 → 财务指标 → 复核表
python skills/storage-investment-operations/instances/anhui-storage-2027/run.py --demo

# 真实数据（路径指向仓库外）
python skills/storage-investment-operations/instances/anhui-storage-2027/run.py \
  --scenarios /path/to/scenarios.csv --assessment /path/to/assessment.csv --out /path/to/out
```

合成数据可重新生成：

```bash
python skills/storage-investment-operations/instances/anhui-storage-2027/make_demo.py
```

## 2. 交付物

| 文件 | 内容 |
|---|---|
| `instance.json` | 唯一配置入口：`meta` / `rules` / `asset` / `policy` / `contracts` / `data_contract` |
| `data/scenarios_demo.csv` | 年度情景模板：5 个情景 ×（充电价、放电价、权重），权重合计为 1 |
| `data/assessment_demo.csv` | 月度可用率模板：2027 年 12 个月 |
| `out/demo/summary.json` | 配置快照、情景期望 / CVaR、基准 4 h 指标、时长阶梯、警告 |
| `out/demo/duration_ladder.csv` | 2 h / 4 h / 6 h：资本开支、容量电费、套利、NPV / IRR / 回收期 / LCOS |
| `out/demo/scenario_stack.csv` | 每个情景的套利净额、容量净额与税前运营净额 |
| `out/demo/assessment.csv` | 月度可用率、相对 98% 的缺口、扣减金额、累计未达标次数 |
| `out/demo/cashflow.csv` | 15 年项目现金流（含折旧与所得税） |
| `out/demo/review.md` | 复核表：结论、口径、时长阶梯、情景尾部、考核、改数说明、边界 |
| `pitfalls.md` | 安徽容量电价与现货的 8 条易错点 |

## 3. 运行逻辑

1. **配置校验**：六个块齐全；每个规则块有 `grade` + `source`；96 点 / 15 分钟一致；容量电价 165 元/kW·年、6 h 分母、2/4/6 h 折算值必须与线性公式一致；可用率门槛 98%、三振上限 3 次；可用能量与 SOC 窗口一致。
2. **读情景**：5 个年度情景，权重合计为 1；每个情景的充、放电价**成对使用**，不跨情景混用分位。
3. **时长阶梯**：对 2 h / 4 h / 6 h 分别计算容量电费毛额（`stacking.capacity_payment`，比例 = min(时长/6, 1)）、套利毛额与退化成本（`stacking.arbitrage`，RTE 0.88 按单程平方根拆分）、资本开支（450 元/kWh）。
4. **可用率考核**：月度扣减 = 月度容量电费 × max(0, 1 − 可用率/0.98)；累计 3 次未达标即全额扣减（D 级简化，省级阶梯表待核实）。
5. **财务指标**：`finance.annual_cashflow` 生成 15 年现金流（直线折旧、25% 所得税），`npv` / `irr` / `payback` / `lcos` 输出基准时长与阶梯结果。
6. **情景尾部**：按权重计算期望运营净额与 CVaR（默认置信 80%，即最差 20% 概率质量的平均）。
7. **复核表**：把「毛额 → 考核扣减 → 净额」与「套利 → 运营支出 → 现金流」两条链分开写，避免把容量电费当成现货收益。

## 4. 合成演示的基准输出

基准资产：100 MW / 400 MWh、可用 360 MWh、RTE 88%、日循环 1 次、年运行 330 天；情景充放价 180–340 / 520–680 元/MWh。

| 项目 | 2 h | 4 h（基准） | 6 h |
|---|---:|---:|---:|
| 资本开支（万元） | 9,000.0 | 18,000.0 | 27,000.0 |
| 容量电费毛额（万元/年） | 550.0 | 1,100.0 | 1,650.0 |
| 考核扣减（万元/年） | 2.3 | 4.7 | 7.0 |
| 容量净额（万元/年） | 547.7 | 1,095.3 | 1,643.0 |
| 套利净额（万元/年） | 1,526.0 | 3,052.1 | 4,578.1 |
| NPV @8%（万元） | 3,862.9 | 9,459.1 | 15,055.3 |
| IRR | 14.51% | 15.86% | 16.31% |
| 静态回收期（年） | 5.99 | 5.61 | 5.50 |
| LCOS（元/MWh） | 553.3 | 529.1 | 521.0 |

- 情景期望年运营净额（税前）：4,147.4 万元；CVaR（置信 80%）：4,041.0 万元。
- 月度可用率：2027-04 为 97.0%、2027-05 为 94.0%，两次低于 98%，累计扣减 4.7 万元；距离第 3 次全额扣减仅剩 1 次。

**阶梯读数**：526 号按 6 h 分母线性折算，2 h 项目只能拿到 1/3 容量电价，短时长更依赖现货价差；6 h 项目容量电费绝对值最高，但资本开支同比例上升，阶梯比较的是单位价值，不是绝对收益。

## 5. 参数状态：已核实 / 待核实

| 参数 | 值 | 级别 | 状态 |
|---|---|---|---|
| 容量电价 | 165 元/kW·年（含税） | A | 已核实，皖发改价格〔2026〕526号 |
| 分母时长 | 6 h | A | 已核实 |
| 时长折算 | 2 h ≈ 55、4 h ≈ 110、6 h = 165 元/kW·年 | A | 已核实，按线性折算复算 |
| 执行时间 | 2027-01-01 | A | 已核实 |
| 可用率考核 | 月度出力/可用容量达计划曲线 98% | A | 已核实原则 |
| 三振规则 | 自然年 3 次未达标 → 全额扣减 / 取消资格 | A | 已核实原则 |
| 阶梯扣减比例 | D 级简化公式 | D | **待核实**；省级阶梯表未在本库核到 |
| 现货转正 | 2026-09-09（2026-09-07 通知） | A/B | 已核实 |
| 现货申报 / 出清限价 | `null` | — | **待核实**；不套用外省限价 |
| 独立储能参与方式 | 报量报价，按报价出清充放电曲线 | A | 已核实 |
| 资产参数（100 MW / 400 MWh 等） | — | D | 合成占位，实际项目按铭牌与台账 |
| 风格参数 | `anhui-capacity-balanced-v1` | D | 投资方假设，不是事实 |

未核实的限价与阶梯比例不会被估算或编造：限价为空时运行器只校验输入非负或允许的负值，复核表打印 warning。

## 6. 风格档与指纹

当前风格 `anhui-capacity-balanced-v1`：日循环 1.0 次、年运行 330 天、基准时长 4 h、CVaR 置信 80%。

`policy` 块规范化 JSON 的 SHA-1 前 12 位作为**风格指纹**写入复核表（当前 `1ea292c25eed`）。比较两个项目的差异时先看指纹：指纹不同，差异首先归因于风格；指纹相同，才归因于资源、价格或规则。

换风格的做法：复制 `instance.json` 为 `instance.aggressive.json`，改 `profile_id` 与参数，用 `--instance` 指向新文件，保留旧文件与旧输出。

## 7. 依赖与边界

- **依赖**：仅 Python 标准库；计算内核来自 `skills/storage-investment-operations/tools/`（`stacking.py`、`finance.py`），不修改内核。
- **纳入**：容量电价（含时长折算）、现货电能量套利、退化成本、固定运维、可用率考核、所得税与直线折旧。
- **未纳入**：辅助服务（调频 / 备用）、容量租赁、绿证、税费优惠、融资结构与保险。
- **不是**：不是交易中心结算的替代品，不是投资建议；容量电费与现货收益必须分账复核。
- 真实数据放在仓库外，用 `--scenarios/--assessment/--out` 指向本地路径；仓库内只保留 D 级合成样例。

## 8. 相关入口

- 储能实例层说明：[`../README.md`](../README.md)
- 安徽易错点：[`pitfalls.md`](pitfalls.md)
- 储能投资方法：[`../../SKILL.md`](../../SKILL.md)
- 安徽市场规则背景：[`../../../../knowledge/安徽电力市场-2026-11.md`](../../../../knowledge/安徽电力市场-2026-11.md)
- 现货实例层（对照）：[`../../../spot-bidding-quant/instances/shandong-storage-2026-11/`](../../../spot-bidding-quant/instances/shandong-storage-2026-11/)
