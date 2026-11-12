"""Desk layer: the trading-day clock, scenario curves, settlement bridge.

This module is deliberately small. It does not forecast or clear. It turns the
skill's forecasts and bid curves into the artefacts a desk actually uses:

* a decision clock with an explicit data cutoff for every step;
* an expected-profit versus CVaR frontier for candidate curves;
* exact settlement variance bridges for a generator and for a storage asset,
  plus implicit (opportunity) losses;
* a schema and gap check for a one-province, one-period public-data backtest.

All examples are synthetic. A public-data backtest still needs the user's own
extract, a frozen rule version and a feature-availability table.
"""

from __future__ import annotations

from collections import Counter, defaultdict


TIMELINE = (
    {
        "time": "D-1 08:30",
        "stage": "数据到位",
        "cutoff": "D-1 08:00",
        "decision": "数据是否完整，是否启用降级数据源",
        "output": "数据快照 + 质量标记",
        "failure": "用昨日数据硬跑，把数据缺失误判成模型误差",
    },
    {
        "time": "D-1 09:30",
        "stage": "预测冻结",
        "cutoff": "D-1 09:00",
        "decision": "是否人工修正，修正依据是什么",
        "output": "96 点 P10/P50/P90 + 情景集",
        "failure": "反复重跑，版本无法追溯，复盘对不上",
    },
    {
        "time": "D-1 10:30",
        "stage": "曲线生成",
        "cutoff": "D-1 10:00",
        "decision": "风险偏好与合约覆盖，选前沿上的哪一点",
        "output": "候选曲线 + 期望利润/CVaR",
        "failure": "只交一条“最优”曲线，没有备选与风险说明",
    },
    {
        "time": "D-1 11:00",
        "stage": "规则校验",
        "cutoff": "D-1 10:30",
        "decision": "通过还是拦截，是否人工 override",
        "output": "校验结果 + override 记录",
        "failure": "绕过校验改单，申报成功但结算被考核",
    },
    {
        "time": "D-1 截止前 90 分钟",
        "stage": "申报",
        "cutoff": "D-1 截止前 90 分钟",
        "decision": "提交还是改单，改单的触发条件",
        "output": "申报回执 + 版本快照",
        "failure": "卡点提交，网络或格式失败没有回退时间",
    },
    {
        "time": "D-1 出清后",
        "stage": "结果核对",
        "cutoff": "出清公告",
        "decision": "是否做日内调整，调整哪些时段",
        "output": "中标曲线 + 偏差预警",
        "failure": "只看出清价，不看中标量与必开/补偿结果",
    },
    {
        "time": "D 日内",
        "stage": "执行",
        "cutoff": "实时",
        "decision": "是否再报价，是否调整出力或 SOC",
        "output": "执行日志 + 指令回执",
        "failure": "用日前曲线应对实时变化，偏差全部进结算",
    },
    {
        "time": "D+1 09:00",
        "stage": "结算初核",
        "cutoff": "D+1 结算数据",
        "decision": "科目是否对上，差异是否超过阈值",
        "output": "结算差异桥 + 争议包",
        "failure": "只对总额，不对科目，差异被“其他”掩盖",
    },
    {
        "time": "D+1 复盘",
        "stage": "复盘",
        "cutoff": "初核完成后",
        "decision": "归因到预测/报价/执行/规则，下一日改什么",
        "output": "归因表 + 改单台账",
        "failure": "把可解释的差异归因成“行情不好”",
    },
)


def trading_day_timeline() -> list[dict]:
    """Return the decision clock. Every step has a cutoff before its decision."""
    return [dict(row) for row in TIMELINE]


def _curve_points(curve) -> list[tuple[float, float, float, float]]:
    """Normalise a curve to (price, cumulative MW, segment cost, segment MW)."""
    points = []
    for seg in curve:
        if isinstance(seg, dict):
            points.append(
                (
                    float(seg["price"]),
                    float(seg["cumulative"]),
                    float(seg.get("cost", 0.0)),
                    float(seg.get("quantity", 0.0)),
                )
            )
        else:
            price, cumulative = seg[0], seg[1]
            points.append((float(price), float(cumulative), 0.0, 0.0))
    points.sort(key=lambda item: item[0])
    for previous, current in zip(points, points[1:]):
        if current[1] < previous[1] - 1e-9:
            raise ValueError("cumulative quantities must be non-decreasing")
    return points


def curve_dispatch(curve, price: float) -> float:
    """Dispatched MW under pay-as-clear when the clearing price is `price`."""
    dispatched = 0.0
    for segment_price, cumulative, _, _ in _curve_points(curve):
        if price >= segment_price:
            dispatched = cumulative
        else:
            break
    return dispatched


def _dispatch_cost(curve, price: float, fallback_cost: float) -> tuple[float, float]:
    """Return (dispatched MW, variable cost) using per-segment costs if present."""
    dispatched = 0.0
    variable_cost = 0.0
    has_segment_costs = False
    for segment_price, cumulative, segment_cost, segment_mw in _curve_points(curve):
        if price >= segment_price:
            dispatched = cumulative
            if segment_mw > 0.0:
                has_segment_costs = True
                variable_cost += segment_cost * segment_mw
        else:
            break
    if not has_segment_costs:
        variable_cost = fallback_cost * dispatched
    return dispatched, variable_cost


def _normalise_scenarios(scenarios) -> list[tuple[float, float]]:
    """Accept [price, ...] or [{"price": p, "prob": w}, ...]; weights sum to 1."""
    if not scenarios:
        raise ValueError("at least one scenario is required")
    pairs = []
    for item in scenarios:
        if isinstance(item, dict):
            pairs.append((float(item["price"]), float(item.get("prob", 1.0))))
        else:
            pairs.append((float(item), 1.0))
    total = sum(weight for _, weight in pairs)
    if total <= 0.0:
        raise ValueError("scenario weights must sum to a positive number")
    return [(price, weight / total) for price, weight in pairs]


def weighted_cvar(profit_and_weight: list[tuple[float, float]], alpha: float = 0.10) -> float:
    """Average of the worst `alpha` probability mass, allowing partial weights."""
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must lie in (0, 1]")
    tail = alpha
    total = 0.0
    for profit, weight in sorted(profit_and_weight):
        take = min(weight, tail)
        total += profit * take
        tail -= take
        if tail <= 1e-12:
            break
    return total / alpha


def curve_metrics(
    curve,
    scenarios,
    cost: float = 0.0,
    contract_quantity: float = 0.0,
    contract_price: float = 0.0,
    alpha: float = 0.10,
    fixed_cost: float = 0.0,
) -> dict:
    """Expected profit, CVaR and dispatch statistics for one bid curve.

    Revenue follows the physical-contract convention:
        R = Qc*Pc + (Q - Qc)*P
    where Q is dispatched MW and P is the scenario price. Variable cost uses
    the per-segment costs in `curve`; `cost` is only a fallback for curves given
    as (price, cumulative MW) pairs. `fixed_cost` is deducted in every scenario.
    """
    profits_and_weights = []
    profits = []
    dispatched_mw = []
    for price, weight in _normalise_scenarios(scenarios):
        dispatched, variable_cost = _dispatch_cost(curve, price, cost)
        revenue = contract_quantity * contract_price + (dispatched - contract_quantity) * price
        profit = revenue - variable_cost - fixed_cost
        profits_and_weights.append((profit, weight))
        profits.append(profit)
        dispatched_mw.append(dispatched * weight)
    expected = sum(profit * weight for profit, weight in profits_and_weights)
    cvar = weighted_cvar(profits_and_weights, alpha)
    variance = sum(weight * (profit - expected) ** 2 for profit, weight in profits_and_weights)
    return {
        "expected": round(expected, 2),
        "cvar": round(cvar, 2),
        "worst": round(min(profits), 2),
        "best": round(max(profits), 2),
        "std": round(variance ** 0.5, 2),
        "mean_dispatch": round(sum(dispatched_mw), 2),
        "scenario_count": len(profits),
        "alpha": alpha,
    }


def risk_frontier(
    candidates,
    scenarios,
    cost: float = 0.0,
    contract_price: float = 0.0,
    alpha: float = 0.10,
    fixed_cost: float = 0.0,
) -> list[dict]:
    """Non-dominated (expected profit, CVaR) candidates, highest expected first.

    `candidates` is a list of {"name", "curve", "contract_quantity"}. A candidate
    is dominated when another has both a higher expected profit and a higher CVaR.
    There is no single optimum: the choice depends on risk appetite, contract
    availability and regulatory constraints.
    """
    results = []
    for candidate in candidates:
        metrics = curve_metrics(
            candidate["curve"],
            scenarios,
            cost=cost,
            contract_quantity=float(candidate.get("contract_quantity", 0.0)),
            contract_price=contract_price,
            alpha=alpha,
            fixed_cost=fixed_cost,
        )
        results.append({"name": candidate["name"], **metrics})
    frontier = []
    for result in results:
        dominated = False
        for other in results:
            if other is result:
                continue
            better_expected = other["expected"] >= result["expected"] - 1e-9
            better_cvar = other["cvar"] >= result["cvar"] - 1e-9
            strictly_better = (
                other["expected"] > result["expected"] + 1e-9
                or other["cvar"] > result["cvar"] + 1e-9
            )
            if better_expected and better_cvar and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(result)
    frontier.sort(key=lambda item: item["expected"], reverse=True)
    return frontier


def _revenue(trade: dict, contract_quantity: float, contract_price: float) -> float:
    return (
        contract_quantity * contract_price
        + (float(trade["q_da"]) - contract_quantity) * float(trade["p_da"])
        + (float(trade["q_actual"]) - float(trade["q_da"])) * float(trade["p_rt"])
    )


def settlement_bridge(
    plan: dict,
    actual: dict,
    cost: float,
    contract_quantity: float = 0.0,
    contract_price: float = 0.0,
    penalty: float = 0.0,
    allocation: float = 0.0,
) -> dict:
    """Exact bridge from planned profit to settled profit.

    `plan` and `actual` each hold q_da, q_actual, p_da and p_rt. The identity is
        dR = dQda*Pda + (Qda0-Qc)*dPda + (dQa-dQda)*Prt + (Qa0-Qda0)*dPrt
    with quantity changes valued first at actual prices and price changes valued
    on planned positions. Cost, penalty and allocation are separate buckets, so
    the residual `identity_gap` should be zero (up to floating-point noise).
    """
    plan_profit = _revenue(plan, contract_quantity, contract_price) - cost * float(plan["q_actual"])
    actual_profit = (
        _revenue(actual, contract_quantity, contract_price)
        - cost * float(actual["q_actual"])
        - penalty
        - allocation
    )
    delta = actual_profit - plan_profit
    d_qda = float(actual["q_da"]) - float(plan["q_da"])
    d_qa = float(actual["q_actual"]) - float(plan["q_actual"])
    d_pda = float(actual["p_da"]) - float(plan["p_da"])
    d_prt = float(actual["p_rt"]) - float(plan["p_rt"])
    buckets = [
        {
            "item": "日前申报量偏差",
            "category": "量",
            "owner": "交易",
            "amount": round(d_qda * float(actual["p_da"]), 2),
        },
        {
            "item": "日前价格偏差",
            "category": "价",
            "owner": "市场",
            "amount": round((float(plan["q_da"]) - contract_quantity) * d_pda, 2),
        },
        {
            "item": "实时执行偏差",
            "category": "量",
            "owner": "调度/运行",
            "amount": round((d_qa - d_qda) * float(actual["p_rt"]), 2),
        },
        {
            "item": "实时价格偏差",
            "category": "价",
            "owner": "市场",
            "amount": round((float(plan["q_actual"]) - float(plan["q_da"])) * d_prt, 2),
        },
        {
            "item": "变动成本",
            "category": "成本",
            "owner": "财务/生产",
            "amount": round(-cost * d_qa, 2),
        },
        {
            "item": "考核",
            "category": "考核",
            "owner": "交易",
            "amount": round(-penalty, 2),
        },
        {
            "item": "分摊",
            "category": "分摊",
            "owner": "财务/交易",
            "amount": round(-allocation, 2),
        },
    ]
    total = sum(bucket["amount"] for bucket in buckets)
    return {
        "plan_profit": round(plan_profit, 2),
        "actual_profit": round(actual_profit, 2),
        "delta": round(delta, 2),
        "buckets": buckets,
        "total": round(total, 2),
        "identity_gap": round(total - delta, 6),
    }


def _broadcast(value, n, name):
    if isinstance(value, (list, tuple)):
        if len(value) != n:
            raise ValueError(f"{name} must have {n} values")
        return [float(v) for v in value]
    return [float(value)] * n


def _storage_frame(frame, name, n):
    for key in ("price", "discharge_mw", "charge_mw"):
        if key not in frame:
            raise ValueError(f"{name} is missing '{key}'")
        if len(frame[key]) != n:
            raise ValueError(f"{name}.{key} must have {n} values")
    price = [float(v) for v in frame["price"]]
    discharge = [float(v) for v in frame["discharge_mw"]]
    charge = [float(v) for v in frame["charge_mw"]]
    if any(v < -1e-9 for v in discharge + charge):
        raise ValueError(f"{name} quantities must be non-negative")
    return price, [max(0.0, v) for v in discharge], [max(0.0, v) for v in charge]


def storage_bridge(
    plan: dict,
    actual: dict,
    *,
    dt_h: float = 0.25,
    degradation_per_mwh: float = 0.0,
    contract_quantity_mw=0.0,
    contract_price: float = 0.0,
    capacity_plan: float = 0.0,
    capacity_actual: float = 0.0,
    penalty_plan: float = 0.0,
    penalty_actual: float = 0.0,
    allocation_plan: float = 0.0,
    allocation_actual: float = 0.0,
) -> dict:
    """Exact plan-versus-actual bridge for a storage asset.

    Both frames carry per-interval ``price``, ``discharge_mw`` and
    ``charge_mw``. Charge and discharge are kept separate so a quantity error on
    the charge side cannot hide inside discharge revenue. The contract is a
    fixed-price CfD overlay on a net-discharge profile, which is algebraically
    the same as the physical convention ``Qc*Pc + (Q-Qc)*P``.

    Capacity compensation, penalties and allocations are daily scalars. Amounts
    are exact floats; round at the display layer. The identity is checked by
    ``identity_gap`` (sum of buckets minus profit delta).
    """
    if "price" not in plan or "price" not in actual:
        raise ValueError("plan and actual must carry a 'price' series")
    n = len(plan["price"])
    if len(actual["price"]) != n:
        raise ValueError("plan and actual must have the same length")
    p_plan, dis_plan, ch_plan = _storage_frame(plan, "plan", n)
    p_act, dis_act, ch_act = _storage_frame(actual, "actual", n)
    qc = _broadcast(contract_quantity_mw, n, "contract_quantity_mw")
    if float(contract_price) < 0:
        raise ValueError("contract_price must be non-negative")
    if any(q < -1e-9 for q in qc):
        raise ValueError("contract quantities must be non-negative")
    dt = float(dt_h)
    if dt <= 0:
        raise ValueError("dt_h must be positive")
    deg = float(degradation_per_mwh)

    def frame_values(prices, discharge, charge):
        spot = sum((discharge[t] - charge[t]) * prices[t] * dt for t in range(n))
        throughput = sum((discharge[t] + charge[t]) * dt for t in range(n))
        contract = sum(
            qc[t] * (float(contract_price) - prices[t]) * dt for t in range(n)
        )
        return spot, throughput, contract

    plan_spot, plan_throughput, plan_contract = frame_values(
        p_plan, dis_plan, ch_plan
    )
    actual_spot, actual_throughput, actual_contract = frame_values(
        p_act, dis_act, ch_act
    )
    plan_deg = plan_throughput * deg
    actual_deg = actual_throughput * deg
    plan_profit = (
        plan_spot
        + plan_contract
        - plan_deg
        + float(capacity_plan)
        - float(penalty_plan)
        - float(allocation_plan)
    )
    actual_profit = (
        actual_spot
        + actual_contract
        - actual_deg
        + float(capacity_actual)
        - float(penalty_actual)
        - float(allocation_actual)
    )
    delta = actual_profit - plan_profit

    buckets = []
    for label, planned, executed, sign in (
        ("放电", dis_plan, dis_act, 1.0),
        ("充电", ch_plan, ch_act, -1.0),
    ):
        quantity = sign * sum(
            p_plan[t] * (executed[t] - planned[t]) * dt for t in range(n)
        )
        price = sign * sum(
            planned[t] * (p_act[t] - p_plan[t]) * dt for t in range(n)
        )
        cross = sign * sum(
            (executed[t] - planned[t]) * (p_act[t] - p_plan[t]) * dt
            for t in range(n)
        )
        buckets.append(
            {"item": f"{label}量偏差", "category": "量", "owner": "交易/调度", "amount": quantity}
        )
        buckets.append(
            {"item": f"{label}价偏差", "category": "价", "owner": "市场", "amount": price}
        )
        buckets.append(
            {"item": f"{label}量价交叉", "category": "量价交叉", "owner": "交易", "amount": cross}
        )
    buckets.extend(
        [
            {"item": "退化成本", "category": "成本", "owner": "运行/财务", "amount": -(actual_deg - plan_deg)},
            {"item": "合约价差", "category": "合约", "owner": "交易/财务", "amount": actual_contract - plan_contract},
            {"item": "容量补偿", "category": "容量", "owner": "财务/交易", "amount": float(capacity_actual) - float(capacity_plan)},
            {"item": "考核", "category": "考核", "owner": "交易", "amount": -(float(penalty_actual) - float(penalty_plan))},
            {"item": "分摊", "category": "分摊", "owner": "财务/交易", "amount": -(float(allocation_actual) - float(allocation_plan))},
        ]
    )
    total = sum(bucket["amount"] for bucket in buckets)
    return {
        "plan_profit": plan_profit,
        "actual_profit": actual_profit,
        "delta": delta,
        "buckets": buckets,
        "total": total,
        "identity_gap": total - delta,
        "plan_spot": plan_spot,
        "actual_spot": actual_spot,
        "plan_contract": plan_contract,
        "actual_contract": actual_contract,
        "plan_degradation": plan_deg,
        "actual_degradation": actual_deg,
        "plan_throughput_mwh": plan_throughput,
        "actual_throughput_mwh": actual_throughput,
    }


def implicit_cost(
    plan: dict,
    actual: dict,
    cost: float,
    available: float,
    contract_quantity: float = 0.0,
    contract_price: float = 0.0,
    penalty: float = 0.0,
) -> dict:
    """Decision losses that do not appear as a negative line on the invoice.

    * opportunity loss: available MW that could have earned a positive margin at
      the day-ahead price but was not dispatched;
    * deviation cost: the explicit imbalance penalty;
    * contract exposure: the signed cost of covering a contract position that is
      larger than actual output (positive = loss).
    """
    foregone = max(0.0, float(actual["p_da"]) - cost) * max(
        0.0, available - float(actual["q_da"])
    )
    contract_gap = (contract_quantity - float(actual["q_actual"])) * (
        float(actual["p_da"]) - contract_price
    )
    items = [
        {
            "item": "机会损失",
            "amount": round(foregone, 2),
            "note": "可用容量 × 正边际（日前价高于成本的部分）",
        },
        {
            "item": "偏差成本",
            "amount": round(penalty, 2),
            "note": "考核与偏差罚则，按结算单口径",
        },
        {
            "item": "合约敞口",
            "amount": round(contract_gap, 2),
            "note": "正=为覆盖合约在日前市场回补的损失；负=敞口收益",
        },
    ]
    return {
        "items": items,
        "total_positive": round(
            foregone + max(0.0, penalty) + max(0.0, contract_gap), 2
        ),
    }


_DISPUTE_GUIDE = {
    "价": {
        "owner": "交易/市场",
        "question": "价差是否由规则版本、限价或出清口径变化导致？",
        "evidence": ["规则版本号与生效日", "出清公告", "限价/二次限价文件"],
    },
    "量": {
        "owner": "调度/计量",
        "question": "差异是申报量、执行量还是计量口径造成的？",
        "evidence": ["申报回执与改单记录", "出清结果", "计量数据与 CT/PT 变比"],
    },
    "量价交叉": {
        "owner": "交易",
        "question": "交叉项是否由申报量与价格同时偏离导致？先拆价、再拆量，最后看交叉。",
        "evidence": ["申报回执", "出清结果", "结算单"],
    },
    "合约": {
        "owner": "交易/财务",
        "question": "合约曲线、参考点与结算价是否与计划版本一致？",
        "evidence": ["合约分解曲线", "参考点选择", "合约结算单"],
    },
    "容量": {
        "owner": "财务/交易",
        "question": "有效容量、补偿标准与供需系数是否按同一版本计算？",
        "evidence": ["容量补偿计算底稿", "有效容量认定", "补偿标准文件"],
    },
    "成本": {
        "owner": "财务/生产",
        "question": "成本口径是否与结算电量口径一致？",
        "evidence": ["燃料/变动成本台账", "厂用电率", "机组效率曲线"],
    },
    "考核": {
        "owner": "交易",
        "question": "考核项是否适用、是否已免考或已申诉？",
        "evidence": ["考核明细", "规则条款", "免考/豁免依据"],
    },
    "分摊": {
        "owner": "财务/交易",
        "question": "分摊科目是否重复归集或被错误分摊？",
        "evidence": ["分摊明细", "结算单", "分摊规则"],
    },
}


def dispute_packet(bridge: dict, threshold: float = 1000.0) -> list[dict]:
    """Turn bridge buckets above a materiality threshold into a dispute list."""
    packet = []
    for bucket in bridge["buckets"]:
        if abs(bucket["amount"]) < threshold:
            continue
        guide = _DISPUTE_GUIDE.get(bucket["category"])
        if guide is None:
            continue
        packet.append(
            {
                "item": bucket["item"],
                "amount": bucket["amount"],
                "category": bucket["category"],
                "owner": guide["owner"],
                "question": guide["question"],
                "evidence": list(guide["evidence"]),
            }
        )
    packet.sort(key=lambda item: abs(item["amount"]), reverse=True)
    return packet


def validate_public_dataset(
    rows: list[dict],
    required_fields: list[str],
    points_per_day: int = 96,
    date_field: str = "date",
    slot_field: str = "slot",
) -> dict:
    """Check schema, duplicates and the 96-slot grid before a public-data backtest.

    This checks shape, not leakage. Publication lag and data revisions are a
    separate problem: a field published after the D-1 cutoff cannot be used as a
    feature for that day even if it appears in a historical file.
    """
    if not rows:
        return {
            "ok": False,
            "row_count": 0,
            "date_count": 0,
            "missing_fields": sorted(required_fields),
            "duplicates": [],
            "gaps": [],
            "bad_slots": [],
            "ordered": True,
            "warnings": ["no rows"],
        }
    missing_fields = sorted(
        {field for field in required_fields if any(field not in row for row in rows)}
    )
    duplicates = []
    counter = Counter()
    bad_slots = []
    slots_by_date = defaultdict(list)
    for row in rows:
        if date_field not in row:
            continue
        try:
            slot = int(row[slot_field])
        except (KeyError, TypeError, ValueError):
            if len(bad_slots) < 10:
                bad_slots.append(row.get(slot_field))
            continue
        key = (row[date_field], slot)
        counter[key] += 1
        slots_by_date[row[date_field]].append(slot)
    for (date, slot), count in counter.items():
        if count > 1:
            duplicates.append({"date": date, "slot": slot, "count": count})
    all_slots = [slot for slots in slots_by_date.values() for slot in slots]
    start = 0 if not all_slots or min(all_slots) == 0 else 1
    expected = set(range(start, start + points_per_day))
    gaps = []
    for date, slots in slots_by_date.items():
        missing = sorted(expected - set(slots))
        if missing:
            gaps.append({"date": date, "missing": missing})
    sequence = [
        (row[date_field], int(row[slot_field]))
        for row in rows
        if date_field in row and str(row.get(slot_field, "")).lstrip("-").isdigit()
    ]
    ordered = sequence == sorted(sequence)
    warnings = []
    if not ordered:
        warnings.append("rows are not sorted by (date, slot)")
    if gaps:
        warnings.append("missing slots; do not interpolate across rule changes")
    return {
        "ok": not (missing_fields or duplicates or gaps or bad_slots),
        "row_count": len(rows),
        "date_count": len(slots_by_date),
        "missing_fields": missing_fields,
        "duplicates": duplicates,
        "gaps": gaps,
        "bad_slots": bad_slots,
        "ordered": ordered,
        "warnings": warnings,
    }
