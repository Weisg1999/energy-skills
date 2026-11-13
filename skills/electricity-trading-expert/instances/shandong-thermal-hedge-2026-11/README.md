# 山东煤电中长期持仓与曲线分解实例包

> 一个 600 MW 燃煤热电联产、一个 2026-11 合约簿、一个交易日（2026-11-18）的**可运行切片**。回答的不是"明天报什么价"，而是"年度/月度/旬度合约怎么落到 96 点、总对冲比例够不够、峰段曲线错在哪、T+1 收入差归因给谁"。

这是 `electricity-trading-expert` 的第一个实例层。现货与 D-1 报价的实例在 [`skills/spot-bidding-quant/instances/`](../../../spot-bidding-quant/instances/README.md)；本包的合约全部是金融差价合约（CfD），不物理执行。

## 1. 这个包回答什么

| 问题 | 输出 |
|---|---|
| 年度/月度/旬度合约的期间电量，怎么分解到交易日的 96 点？ | `book_sheet.csv` 的逐时段合约电量与加权合约价 |
| 总对冲比例是多少？峰段、谷段各差多少？ | `summary.json` 的 `hedge_ratio`、`buy_back_mwh`、`sell_surplus_mwh` |
| 合约到底赚的是"均价 carry"还是"曲线形状"？ | `review.md` §5 的 carry / shape 分解 |
| 现货价格情景下收入分布如何？最差情景亏多少？ | `summary.json` 的 5 情景收入与 CVaR10 |
| D-7~D-2 预测变了，该加仓还是减仓？ | `rolling.csv` 的每日所需交易 |
| T+1 实际收入与计划差在哪？ | `bridge.csv` 六桶差异桥：合约总量 / 合约曲线 / 出力总量 / 出力曲线 / 现货价 / 交互 |

## 2. 一条命令跑通

```bash
# 只校验配置与来源
python skills/electricity-trading-expert/instances/shandong-thermal-hedge-2026-11/run.py --check-config

# 用自带 D 级合成数据跑全流程
python skills/electricity-trading-expert/instances/shandong-thermal-hedge-2026-11/run.py --demo

# 用自己的数据（D-1、T+1、滚动预测都可选）
python skills/electricity-trading-expert/instances/shandong-thermal-hedge-2026-11/run.py \
  --d1 /path/to/d1.csv --t1 /path/to/t1.csv --rolling /path/to/rolling.csv --out /path/to/out
```

产物（默认 `out/demo/`）：

| 文件 | 内容 |
|---|---|
| `book_sheet.csv` | 96 点：预测出力、合约持仓、合约价、参考价、对冲收入、不对冲收入、基差 |
| `rolling.csv` | D-7~D-1 每日预测、调仓前持仓、目标持仓、所需交易、调仓后持仓 |
| `summary.json` | 配置、来源、合约簿、情景、CVaR、滚动、实际、告警 |
| `bridge.json` / `bridge.csv` | T+1 六桶差异桥与最大偏差时段 |
| `review.md` | 中文复核表（10 节，含三个复核问题） |

## 3. 运行逻辑（8 步）

1. **读配置**：`instance.json` 六个块 `meta` / `rules` / `asset` / `book` / `policy` / `data_contract`；每个规则块必须有 `grade` + `source`。
2. **分解合约曲线**：`period_days` → 日电量 → 形状权重（`base` / `window` / `complement` / `anchors` / `curve`）→ 96 点 `MWh/时段`。
3. **合并持仓**：四份合约逐时段相加，得到总持仓与按电量加权的合约价曲线。
4. **算对冲**：`对冲比例 = 合约日电量 ÷ 预测出力电量`；逐时段比较持仓与出力，得到买入平仓量、卖出富余量与曲线错配量。
5. **情景结算**：5 个日前价格情景分别按 `Σ 合约量×合约价 + Σ（出力 − 合约量）× 日前价` 结算；算期望收入与 CVaR10。
6. **分解对冲价值**：`hedge_value = carry + shape`；carry 是合约加权价与现货时间均价之差，shape 是峰谷曲线错配，二者之和有恒等式。
7. **滚动调仓**：按 `target_hedge_ratio` 逐日给出目标持仓与所需交易；校验 `position_before` 必须与上一日收盘衔接。
8. **T+1 差异桥**：计划（D-1 预测 + D-1 合约簿 + 参考价）与实际（T+1 出力 + 结算合约量 + 日前价）拆成六桶，残差 < 1e-6。

## 4. 关键公式

```
合约日电量 = 期间电量 ÷ period_days（或直接给 daily_energy_mwh）
合约逐时段电量 q_t = 合约日电量 × 形状权重_t（权重之和 = 1）
发电收入 = Σ q_t × c_t + Σ (g_t × Δt − q_t) × s_t
对冲价值 = Σ q_t × (c_t − s_t) = 合约电量 × (加权合约价 − 现货时间均价) + 曲线形状
```

T+1 六桶恒等式：

```
实际收入 − 计划收入
= 合约总量偏差 + 合约曲线偏差 + 出力总量偏差
+ 出力曲线偏差 + 现货价偏差 + 交互
```

## 5. 演示基线（D 级合成，已锁进自测）

| 项目 | 值 |
|---|---:|
| 合约簿 | 4 份，日电量 7,500.0 MWh，加权价 375.35 CNY/MWh |
| 预测出力 | 8,800.0 MWh |
| 对冲比例 | 85.23%（目标 85%） |
| 净敞口 / 卖出富余 | +1,300.0 MWh |
| 参考价收入 | 3,285,582 CNY |
| 情景期望收入 | 3,295,135 CNY |
| CVaR10（最差情景） | 3,238,910 CNY |
| 对冲价值 | +102,568 = carry +145,611 + shape −43,043 |
| 滚动目标 vs 合约簿 | 7,480 vs 7,500 MWh（整档差 +20） |
| T+1 计划 → 实际 | 3,285,582 → 3,240,926 CNY（−44,657，残差 2.33e-10） |

T+1 六桶（CNY）：出力总量 −54,111；现货价 +11,682；合约曲线 −4,031；出力曲线 +2,433；交互 −1,001；合约总量 +371。

> 这组数字的教学点：**carry 为正不代表对冲划算**。峰段合约卖在 415 CNY/MWh，而现货晚峰约 520，形状项把 carry 吃掉 43,043；对冲的主要作用是把收入分布收窄，不是提高期望收入（期望对冲价值只有 +65,598）。

策略指纹：`f1e965abe40e`（`policy` 规范化 JSON 的 SHA-1 前 12 位）。

## 6. 参数状态

| 参数 | 值 | 级别 | 说明 |
|---|---|---|---|
| 现货限价 | −100 ~ 1500 CNY/MWh | B/C | 山东现行；2026-08-28 下限草案未生效 |
| 现货申报限价 | −80 ~ 1300 CNY/MWh | B/C | 同上 |
| 合约类型 | 年度基荷 / 月度峰段 / 月度谷段 / 旬度曲线 | D | 示例合约，不是真实签约 |
| 合约价格 | 372 / 415 / 285 / 350 CNY/MWh | D | 示例；只做数据合理性校验 |
| 峰段窗口 | 08:00–22:00 | D | **合同约定**，不是省级分时电价 |
| 机组 | 600 MW，最小出力 180 MW | D | 示例；实际按铭牌与供热最小出力 |
| 目标对冲比例 | 85% | D | 交易风格，不是监管要求 |
| 情景权重 | 5 × 0.2 | D | 合成；可用分位数、集合预报或人工情景替换 |

## 7. 边界

- **只用日前价**：实时偏差两结算、两个细则考核、供热成本、辅助服务、容量补偿均未纳入；本表收入不是最终结算收入，也不是利润。
- **只做金融 CfD**：物理执行合约、绿电合约、跨省合约不在 v1。
- **不重新优化合约曲线**：情景只影响收入分布与 CVaR，不改变已签曲线；真实交易中 D-1 调仓会改变曲线，需在 T+1 用结算单的实际合约电量复核。
- **不构成建议**：全部为 D 级合成数据，不构成报价、投资、法律或税务建议。

## 8. 相关

- 现货与 D-1 报价实例：[`spot-bidding-quant/instances/README.md`](../../../spot-bidding-quant/instances/README.md)
- 售电侧中长期与零售组合：[`retail-electricity-risk/instances/README.md`](../../../retail-electricity-risk/instances/README.md)
- 方法正文：[`SKILL.md`](../../SKILL.md) §4 中长期交易与电力金融市场、§12 关键公式
- 引擎与自测：[`tools/hedge.py`](../../tools/hedge.py)、[`tools/selftest.py`](../../tools/selftest.py)
