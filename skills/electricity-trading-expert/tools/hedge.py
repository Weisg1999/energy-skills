"""中长期持仓、曲线分解与差价合约估值（零依赖，仅标准库）。

本模块补 `electricity-trading-expert` 的中长期切片：把年度/月度/旬度合约的
**期间电量**分解到交易日的 96 点曲线，计算持仓、对冲比例、现货敞口，并按
「合约电量 × 合约价 +（实际出力 − 合约电量）× 现货价」结算。

口径与边界：

* **差价合约口径**：合约电量不物理执行，全电量参与现货；合约按
  ``(合约价 − 现货价) × 合约电量`` 差价结算。对发电机，这与「合约电量
  按合约价、偏差按现货价」的总额相同。物理执行合约不在本模块内。
* **期间电量 ≠ 日电量**：年度合约按 ``daily_weight = 1/365``、月度按
  ``1/30``、旬度按 ``1/10`` 分解到日；也可以直接给 ``daily_energy_mwh``。
  把月度电量当日电量，是最常见的中长期测算错误。
* **曲线形状**：``base`` 平段、``window`` 峰段（合同约定时段，不是省级
  分时电价文件）、``complement`` 谷段、``anchors`` 分段线性、``curve``
  显式 96 点权重。所有权重归一化到和为 1，再乘日电量。
* **对冲价值**：相对「全部按现货卖」的增量，等于 ``Σ 合约量 × (合约价 −
  现货价)``；可拆成「均价 carry」与「曲线形状」两项，二者之和恒等。
* **P&L 差异桥**：把计划与实际收入的差拆成合约总量、合约曲线、出力总量、
  出力曲线、现货价、交互六项，恒等式残差为 0。

所有算例均为合成/演示口径，不构成投资、法律或税务意见。合约类型、峰谷
时段、结算参考价与偏差考核以交易中心正式规则和合同条款为准。
"""

from __future__ import annotations

import math


def _vector(values, name):
    out = [float(v) for v in values]
    if not out:
        raise ValueError(f"{name} 不能为空")
    if any(not math.isfinite(v) for v in out):
        raise ValueError(f"{name} 必须全部有限")
    return out


def normalize_shape(weights):
    """把非负权重归一化到和为 1；全零权重抛 ValueError。"""
    values = _vector(weights, "weights")
    if any(v < 0.0 for v in values):
        raise ValueError("weights 不能为负")
    total = sum(values)
    if total <= 0.0:
        raise ValueError("weights 之和必须为正")
    return [v / total for v in values]


def flat_shape(n):
    """平段曲线：每个时段权重相同。"""
    if n <= 0:
        raise ValueError("n 必须为正")
    return [1.0 / n] * n


def _slot_hours(n, dt_h):
    return [(index * dt_h, (index + 1) * dt_h) for index in range(n)]


def window_shape(n, mtu_min, windows, complement=False):
    """峰段/谷段曲线。

    ``windows`` 是 ``[[start_hour, end_hour], ...]``，按合同约定填写，
    不是省级分时电价文件；落在窗口内的时段等权。``complement=True``
    时取窗口外的时段（谷段）。
    """
    if n <= 0:
        raise ValueError("n 必须为正")
    dt_h = mtu_min / 60.0
    if dt_h <= 0:
        raise ValueError("mtu_min 必须为正")
    if not windows:
        raise ValueError("windows 不能为空")
    spans = []
    for item in windows:
        if len(item) != 2:
            raise ValueError("windows 的每个元素必须是 [start_hour, end_hour]")
        start, end = float(item[0]), float(item[1])
        if not 0.0 <= start < end <= 24.0:
            raise ValueError("window 必须满足 0 <= start < end <= 24")
        spans.append((start, end))

    weights = []
    for start, end in _slot_hours(n, dt_h):
        inside = any(start >= a - 1e-12 and end <= b + 1e-12 for a, b in spans)
        weights.append(1.0 if inside != complement else 0.0)
    return normalize_shape(weights)


def anchor_shape(n, mtu_min, anchors):
    """分段线性锚点曲线；``anchors`` 为 ``[[hour, weight], ...]``。"""
    if n <= 0:
        raise ValueError("n 必须为正")
    dt_h = mtu_min / 60.0
    if len(anchors) < 2:
        raise ValueError("anchors 至少需要两个点")
    points = sorted((float(h), float(w)) for h, w in anchors)
    if points[0][0] > 0.0 or points[-1][0] < 24.0:
        raise ValueError("anchors 必须覆盖 0 到 24 时")
    if any(w < 0.0 for _, w in points):
        raise ValueError("anchors 权重不能为负")

    weights = []
    for start, end in _slot_hours(n, dt_h):
        hour = (start + end) / 2.0
        for index in range(len(points) - 1):
            h0, w0 = points[index]
            h1, w1 = points[index + 1]
            if h0 <= hour <= h1:
                fraction = 0.0 if h1 == h0 else (hour - h0) / (h1 - h0)
                weights.append(w0 + (w1 - w0) * fraction)
                break
        else:
            weights.append(points[-1][1])
    return normalize_shape(weights)


def shape_from_spec(spec, n, mtu_min):
    """按 ``{"type": ...}`` 生成归一化形状。"""
    if not isinstance(spec, dict):
        raise ValueError("shape 必须是对象")
    kind = spec.get("type")
    if kind == "base":
        return flat_shape(n)
    if kind == "window":
        return window_shape(n, mtu_min, spec.get("windows", []), complement=False)
    if kind == "complement":
        return window_shape(n, mtu_min, spec.get("windows", []), complement=True)
    if kind == "anchors":
        return anchor_shape(n, mtu_min, spec.get("anchors", []))
    if kind == "curve":
        weights = spec.get("weights")
        if not isinstance(weights, list) or len(weights) != n:
            raise ValueError(f"curve.weights 必须有 {n} 个点")
        return normalize_shape(weights)
    raise ValueError(f"未知 shape.type: {kind}")


def contract_daily_energy(contract):
    """合约在交易日的电量（MWh）。

    优先用 ``daily_energy_mwh``；否则用 ``energy_mwh × daily_weight``；
    再否则用 ``energy_mwh / period_days``。三者都没有就报错。
    """
    if "daily_energy_mwh" in contract and contract["daily_energy_mwh"] is not None:
        value = float(contract["daily_energy_mwh"])
    elif "daily_weight" in contract and contract["daily_weight"] is not None:
        value = float(contract["energy_mwh"]) * float(contract["daily_weight"])
    elif "period_days" in contract and contract["period_days"]:
        value = float(contract["energy_mwh"]) / float(contract["period_days"])
    else:
        raise ValueError(
            f"合约 {contract.get('id', '?')} 缺少 daily_energy_mwh / daily_weight / period_days"
        )
    if value < 0.0:
        raise ValueError("日电量不能为负")
    return value


def contract_curve(contract, n, mtu_min):
    """把合约日电量分解成 96 点电量曲线（MWh/时段）。"""
    daily = contract_daily_energy(contract)
    shape = shape_from_spec(contract.get("shape", {"type": "base"}), n, mtu_min)
    return [daily * weight for weight in shape]


def book_position(contracts, n, mtu_min):
    """合并合约簿，返回逐合约曲线与合计持仓曲线（MWh/时段）。"""
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("contracts 不能为空")
    curves = []
    total = [0.0] * n
    for contract in contracts:
        curve = contract_curve(contract, n, mtu_min)
        curves.append(
            {
                "id": contract.get("id", "?"),
                "curve": curve,
                "daily_energy_mwh": sum(curve),
                "price_cny_per_mwh": float(contract["price_cny_per_mwh"]),
                "kind": contract.get("kind", "base"),
            }
        )
        for slot in range(n):
            total[slot] += curve[slot]
    return {"curves": curves, "position": total, "energy_mwh": sum(total)}


def hedge_ratio(position_mwh, output_mwh):
    """对冲比例 = 合约电量 ÷ 预测/实际出力电量；出力为 0 时返回 None。"""
    if output_mwh < 0.0:
        raise ValueError("output_mwh 不能为负")
    if output_mwh == 0.0:
        return None
    return position_mwh / output_mwh


def price_curve(book, n):
    """按合约电量加权的逐时段合约价曲线。"""
    curve = [0.0] * n
    for item in book["curves"]:
        for slot in range(n):
            curve[slot] += item["curve"][slot] * item["price_cny_per_mwh"]
    return [curve[slot] / book["position"][slot] if book["position"][slot] > 1e-12 else 0.0 for slot in range(n)]


def settle_book(contracts, output_mw, spot_prices, n, mtu_min):
    """按差价合约口径结算：合约收入 + 现货偏差收入。

    ``output_mw`` 与 ``spot_prices`` 都是 ``n`` 点；返回合约收入、现货收入、
    总收入、合约电量、出力电量、对冲比例与敞口。
    """
    output = _vector(output_mw, "output_mw")
    spot = _vector(spot_prices, "spot_prices")
    if len(output) != n or len(spot) != n:
        raise ValueError("output_mw 与 spot_prices 必须为 n 点")
    dt_h = mtu_min / 60.0
    book = book_position(contracts, n, mtu_min)
    contract_revenue = sum(
        item["curve"][slot] * item["price_cny_per_mwh"] for item in book["curves"] for slot in range(n)
    )
    spot_revenue = sum(
        (output[slot] * dt_h - book["position"][slot]) * spot[slot] for slot in range(n)
    )
    output_energy = sum(output) * dt_h
    net_exposure = output_energy - book["energy_mwh"]
    absolute_exposure = sum(
        abs(output[slot] * dt_h - book["position"][slot]) for slot in range(n)
    )
    return {
        "contract_revenue_cny": contract_revenue,
        "spot_revenue_cny": spot_revenue,
        "total_revenue_cny": contract_revenue + spot_revenue,
        "contract_energy_mwh": book["energy_mwh"],
        "output_energy_mwh": output_energy,
        "hedge_ratio": hedge_ratio(book["energy_mwh"], output_energy),
        "net_exposure_mwh": net_exposure,
        "absolute_exposure_mwh": absolute_exposure,
        "contract_price_curve": price_curve(book, n),
        "position_curve": book["position"],
    }


def hedge_value(contracts, output_mw, spot_prices, n, mtu_min):
    """相对「全部按现货卖」的增量，并拆成均价 carry 与曲线形状两项。

    ``hedge_value = Σ 合约量 × (合约价 − 现货价)``
    ``= 合约电量 × (加权合约价 − 现货时间均价)
       + Σ 合约量 × (现货时间均价 − 现货价)``
    """
    output = _vector(output_mw, "output_mw")
    spot = _vector(spot_prices, "spot_prices")
    if len(output) != n or len(spot) != n:
        raise ValueError("output_mw 与 spot_prices 必须为 n 点")
    book = book_position(contracts, n, mtu_min)
    contract_revenue = sum(
        item["curve"][slot] * item["price_cny_per_mwh"] for item in book["curves"] for slot in range(n)
    )
    position_weighted_spot = sum(
        book["position"][slot] * spot[slot] for slot in range(n)
    )
    no_hedge_revenue = sum(
        output[slot] * (mtu_min / 60.0) * spot[slot] for slot in range(n)
    )
    total_revenue = contract_revenue + sum(
        (output[slot] * (mtu_min / 60.0) - book["position"][slot]) * spot[slot]
        for slot in range(n)
    )
    value = total_revenue - no_hedge_revenue
    weighted_price = contract_revenue / book["energy_mwh"] if book["energy_mwh"] > 0 else 0.0
    time_average_spot = sum(spot) / n
    carry = book["energy_mwh"] * (weighted_price - time_average_spot)
    shape = book["energy_mwh"] * time_average_spot - position_weighted_spot
    return {
        "hedge_value_cny": value,
        "carry_cny": carry,
        "shape_cny": shape,
        "identity_gap": value - (carry + shape),
        "contract_energy_mwh": book["energy_mwh"],
        "weighted_contract_price": weighted_price,
        "time_average_spot": time_average_spot,
    }


def curve_stats(position_mwh, output_mw, spot_prices, n, mtu_min):
    """持仓曲线与出力曲线的形状匹配统计。"""
    position = _vector(position_mwh, "position_mwh")
    output = _vector(output_mw, "output_mw")
    spot = _vector(spot_prices, "spot_prices")
    if not (len(position) == len(output) == len(spot) == n):
        raise ValueError("position_mwh / output_mw / spot_prices 必须为 n 点")
    dt_h = mtu_min / 60.0
    position_energy = sum(position)
    output_energy = sum(output) * dt_h
    buy_back = sum(max(0.0, position[slot] - output[slot] * dt_h) for slot in range(n))
    sell_surplus = sum(max(0.0, output[slot] * dt_h - position[slot]) for slot in range(n))
    peak_price = max(spot)
    average_price = sum(spot) / n
    return {
        "position_energy_mwh": position_energy,
        "output_energy_mwh": output_energy,
        "hedge_ratio": hedge_ratio(position_energy, output_energy),
        "buy_back_mwh": buy_back,
        "sell_surplus_mwh": sell_surplus,
        "mismatch_mwh": buy_back + sell_surplus,
        "spot_average": average_price,
        "spot_max": peak_price,
        "spot_min": min(spot),
        "spot_peak_to_average": peak_price / average_price if average_price else None,
    }


def pnl_bridge(plan, actual, n, mtu_min):
    """把「实际收入 − 计划收入」拆成六项，恒等式残差为 0。

    ``plan`` / ``actual`` 各含 ``output_mw``、``position_curve``（MWh/时段）、
    ``contract_price_curve``（CNY/MWh）、``spot_prices``（CNY/MWh）。六项：

    1. 合约总量偏差
    2. 合约曲线偏差
    3. 出力总量偏差
    4. 出力曲线偏差
    5. 现货价偏差
    6. 交互
    """
    dt_h = mtu_min / 60.0
    for name, block in (("plan", plan), ("actual", actual)):
        for key in ("output_mw", "position_curve", "contract_price_curve", "spot_prices"):
            if len(block[key]) != n:
                raise ValueError(f"{name}.{key} 必须为 {n} 点")

    g_p = _vector(plan["output_mw"], "plan.output_mw")
    g_a = _vector(actual["output_mw"], "actual.output_mw")
    q_p = _vector(plan["position_curve"], "plan.position_curve")
    q_a = _vector(actual["position_curve"], "actual.position_curve")
    c_p = _vector(plan["contract_price_curve"], "plan.contract_price_curve")
    c_a = _vector(actual["contract_price_curve"], "actual.contract_price_curve")
    s_p = _vector(plan["spot_prices"], "plan.spot_prices")
    s_a = _vector(actual["spot_prices"], "actual.spot_prices")

    def revenue(g, q, c, s):
        return sum(q[slot] * c[slot] + (g[slot] * dt_h - q[slot]) * s[slot] for slot in range(n))

    plan_revenue = revenue(g_p, q_p, c_p, s_p)
    actual_revenue = revenue(g_a, q_a, c_a, s_a)

    q_p_energy = sum(q_p)
    q_a_energy = sum(q_a)
    g_p_energy = sum(g_p) * dt_h
    g_a_energy = sum(g_a) * dt_h
    if q_p_energy <= 0 or q_a_energy <= 0 or g_p_energy <= 0 or g_a_energy <= 0:
        raise ValueError("合约电量与出力电量都必须为正")

    d_q = q_a_energy - q_p_energy
    d_g = g_a_energy - g_p_energy
    w_p = [value / q_p_energy for value in q_p]
    w_a = [value / q_a_energy for value in q_a]
    v_p = [value * dt_h / g_p_energy for value in g_p]
    v_a = [value * dt_h / g_a_energy for value in g_a]

    contract_volume = sum(d_q * w_p[slot] * (c_p[slot] - s_p[slot]) for slot in range(n))
    contract_shape = sum(
        q_a_energy * (w_a[slot] - w_p[slot]) * (c_p[slot] - s_p[slot]) for slot in range(n)
    )
    output_volume = sum(d_g * v_p[slot] * s_p[slot] for slot in range(n))
    output_shape = sum(
        g_a_energy * (v_a[slot] - v_p[slot]) * s_p[slot] for slot in range(n)
    )
    spot_price = sum(
        (g_p[slot] * dt_h - q_p[slot]) * (s_a[slot] - s_p[slot]) for slot in range(n)
    )
    interaction = sum(
        ((g_a[slot] - g_p[slot]) * dt_h - (q_a[slot] - q_p[slot])) * (s_a[slot] - s_p[slot])
        for slot in range(n)
    )
    buckets = [
        {"item": "合约总量偏差", "category": "contract_volume", "amount": contract_volume},
        {"item": "合约曲线偏差", "category": "contract_shape", "amount": contract_shape},
        {"item": "出力总量偏差", "category": "output_volume", "amount": output_volume},
        {"item": "出力曲线偏差", "category": "output_shape", "amount": output_shape},
        {"item": "现货价偏差", "category": "spot_price", "amount": spot_price},
        {"item": "交互", "category": "interaction", "amount": interaction},
    ]
    delta = actual_revenue - plan_revenue
    return {
        "plan_revenue_cny": plan_revenue,
        "actual_revenue_cny": actual_revenue,
        "delta_cny": delta,
        "buckets": buckets,
        "identity_gap": delta - sum(item["amount"] for item in buckets),
        "plan_contract_energy_mwh": q_p_energy,
        "actual_contract_energy_mwh": q_a_energy,
        "plan_output_energy_mwh": g_p_energy,
        "actual_output_energy_mwh": g_a_energy,
        "plan_hedge_ratio": hedge_ratio(q_p_energy, g_p_energy),
        "actual_hedge_ratio": hedge_ratio(q_a_energy, g_a_energy),
    }


def required_trade(forecast_output_mwh, current_position_mwh, target_hedge_ratio):
    """达到目标对冲比例所需的合约增量；正数加仓，负数减仓。"""
    if forecast_output_mwh < 0.0:
        raise ValueError("forecast_output_mwh 不能为负")
    if not 0.0 <= target_hedge_ratio <= 2.0:
        raise ValueError("target_hedge_ratio 应在 [0, 2]")
    target = forecast_output_mwh * target_hedge_ratio
    gap = target - current_position_mwh
    return {
        "forecast_output_mwh": forecast_output_mwh,
        "current_position_mwh": current_position_mwh,
        "target_hedge_ratio": target_hedge_ratio,
        "target_position_mwh": target,
        "required_trade_mwh": gap,
        "action": "加仓" if gap > 0 else ("减仓" if gap < 0 else "不动"),
        "current_hedge_ratio": hedge_ratio(current_position_mwh, forecast_output_mwh),
    }


def rolling_plan(daily_forecast_mwh, current_position_mwh, target_hedge_ratio):
    """按日预测逐日给出目标持仓与所需交易；用于 D-7~D-2 滚动运营。"""
    forecasts = _vector(daily_forecast_mwh, "daily_forecast_mwh")
    if any(value < 0.0 for value in forecasts):
        raise ValueError("daily_forecast_mwh 不能为负")
    position = float(current_position_mwh)
    rows = []
    for day, forecast in enumerate(forecasts, start=1):
        trade = required_trade(forecast, position, target_hedge_ratio)
        rows.append(
            {
                "day": day,
                "forecast_output_mwh": forecast,
                "position_before_mwh": position,
                "target_position_mwh": trade["target_position_mwh"],
                "required_trade_mwh": trade["required_trade_mwh"],
                "position_after_mwh": trade["target_position_mwh"],
                "current_hedge_ratio": trade["current_hedge_ratio"],
            }
        )
        position = trade["target_position_mwh"]
    return rows
