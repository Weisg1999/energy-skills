"""Deterministic day-ahead dispatch kernel shared by storage and microgrid EMS.

Pure standard library, no solver. The model is the single-battery linear
program solved by dynamic programming on a uniform state-of-charge grid:

    min  sum_t  buy_t * p_imp_t * dt - sell_t * p_exp_t * dt
             + c_deg * (p_ch_t + p_dis_t) * dt
             + c_curt * pv_curt_t * dt
    s.t. p_imp_t - p_exp_t = load_t + p_ch_t - p_dis_t - pv_used_t
         E_{t+1} = E_t * (1 - sigma*dt) + eta_ch*p_ch_t*dt - p_dis_t*dt/eta_dis
         SOC_min <= E_t / cap <= SOC_max
         p_ch_t <= P_ch - reserve_dn,  p_dis_t <= P_dis - reserve_up
         p_imp_t <= PCC_import,         p_exp_t <= PCC_export
         p_ch_t * p_dis_t = 0 (by construction)
         pv_used_t + pv_curt_t = pv_t

Simultaneous charge/discharge is impossible by construction; simultaneous
import/export is impossible because the grid term is split on the sign of the
net load. PV surplus beyond the export limit is curtailed.

This is a screening tool. It does not model market clearance, frequency
response performance, degradation chemistry, thermal limits or network flow.
All inputs are synthetic unless the caller supplies measured curves.
"""

from __future__ import annotations

import math

INF = float("inf")
EPS = 1e-9


def _vector(values, name):
    out = [float(v) for v in values]
    if not out:
        raise ValueError(f"{name} must not be empty")
    return out


def _clip(value, low, high):
    return low if value < low else high if value > high else value


def dispatch_day(
    buy_price,
    load_kw,
    pv_kw=None,
    *,
    sell_price=None,
    capacity_kwh,
    power_charge_kw,
    power_discharge_kw,
    eta_charge=1.0,
    eta_discharge=1.0,
    soc_min=0.0,
    soc_max=1.0,
    soc_init=None,
    dt_h=0.25,
    pcc_import_kw=None,
    pcc_export_kw=0.0,
    reserve_up_kw=0.0,
    reserve_dn_kw=0.0,
    reserve_hours=1.0,
    degradation_per_kwh=0.0,
    curtail_penalty_per_kwh=0.0,
    terminal="cycle",
    terminal_value_per_kwh=0.0,
    self_discharge_per_h=0.0,
    states=200,
    enforce_reserve_energy=False,
):
    """Dispatch one horizon on a uniform SOC grid.

    Units: kW, kWh, CNY/kWh, hours. ``terminal`` is ``"cycle"`` (finish at the
    initial SOC) or ``"free"`` (any final SOC, optionally valued).
    """
    buy = _vector(buy_price, "buy_price")
    load = _vector(load_kw, "load_kw")
    n = len(buy)
    if len(load) != n:
        raise ValueError("buy_price and load_kw must have the same length")
    pv = [0.0] * n if pv_kw is None else _vector(pv_kw, "pv_kw")
    sell = [0.0] * n if sell_price is None else _vector(sell_price, "sell_price")
    if len(pv) != n or len(sell) != n:
        raise ValueError("pv_kw and sell_price must match buy_price length")

    capacity_kwh = float(capacity_kwh)
    power_charge_kw = float(power_charge_kw)
    power_discharge_kw = float(power_discharge_kw)
    eta_charge = float(eta_charge)
    eta_discharge = float(eta_discharge)
    soc_min = float(soc_min)
    soc_max = float(soc_max)
    dt_h = float(dt_h)
    if capacity_kwh <= 0 or power_charge_kw < 0 or power_discharge_kw < 0:
        raise ValueError("capacity and power must be non-negative, capacity positive")
    if not 0 < eta_charge <= 1 or not 0 < eta_discharge <= 1:
        raise ValueError("efficiencies must be in (0, 1]")
    if not 0 <= soc_min < soc_max <= 1:
        raise ValueError("require 0 <= soc_min < soc_max <= 1")
    if dt_h <= 0:
        raise ValueError("dt_h must be positive")
    if states < 10:
        raise ValueError("states must be at least 10")
    if terminal not in ("cycle", "free"):
        raise ValueError("terminal must be 'cycle' or 'free'")
    if soc_init is None:
        soc_init = soc_min
    soc_init = float(soc_init)
    if not soc_min - EPS <= soc_init <= soc_max + EPS:
        raise ValueError("soc_init must lie inside the SOC window")

    usable = (soc_max - soc_min) * capacity_kwh
    step = usable / states
    i0 = int(round((soc_init - soc_min) * capacity_kwh / step))
    i0 = _clip(i0, 0, states)
    energies = [i * step for i in range(states + 1)]

    p_ch_lim = max(0.0, power_charge_kw - reserve_dn_kw)
    p_dis_lim = max(0.0, power_discharge_kw - reserve_up_kw)
    ch_dc_max = p_ch_lim * eta_charge * dt_h
    dis_dc_max = p_dis_lim * dt_h / eta_discharge

    e_res_up = reserve_up_kw * reserve_hours / eta_discharge
    e_res_dn = reserve_dn_kw * reserve_hours * eta_charge
    if enforce_reserve_energy and e_res_up + e_res_dn > usable + EPS:
        return {
            "feasible": False,
            "reason": "reserve energy exceeds the usable SOC window",
        }
    e_lo = e_res_up if enforce_reserve_energy else 0.0
    e_hi = usable - e_res_dn if enforce_reserve_energy else usable

    decay = max(0.0, 1.0 - self_discharge_per_h * dt_h)
    import_limit = INF if pcc_import_kw is None else float(pcc_import_kw)
    export_limit = float(pcc_export_kw)

    prev = [INF] * (states + 1)
    prev_move = [INF] * (states + 1)
    prev[i0] = 0.0
    prev_move[i0] = 0.0
    parents = []

    for t in range(n):
        curr = [INF] * (states + 1)
        curr_move = [INF] * (states + 1)
        parent = [-1] * (states + 1)
        load_t = load[t]
        pv_t = pv[t]
        buy_t = buy[t]
        sell_t = sell[t]

        for i in range(states + 1):
            base = prev[i]
            if base == INF:
                continue
            e0 = energies[i] * decay
            lo = max(e_lo, e0 - dis_dc_max)
            hi = min(e_hi, e0 + ch_dc_max)
            if hi < lo - EPS:
                continue
            j_lo = int(math.ceil(lo / step - 1e-9))
            j_hi = int(math.floor(hi / step + 1e-9))
            j_lo = _clip(j_lo, 0, states)
            j_hi = _clip(j_hi, 0, states)

            for j in range(j_lo, j_hi + 1):
                e_j = energies[j]
                delta = e_j - e0
                if delta >= 0.0:
                    p_ch = delta / (eta_charge * dt_h) if delta > EPS else 0.0
                    p_dis = 0.0
                else:
                    p_ch = 0.0
                    p_dis = (-delta) * eta_discharge / dt_h

                net = load_t + p_ch - p_dis - pv_t
                if net >= 0.0:
                    p_imp = net
                    p_exp = 0.0
                    curt = 0.0
                else:
                    surplus = -net
                    p_exp = surplus if surplus < export_limit else export_limit
                    curt = surplus - p_exp
                    p_imp = 0.0
                if p_imp > import_limit + EPS:
                    continue

                cost = (
                    base
                    + (buy_t * p_imp - sell_t * p_exp) * dt_h
                    + degradation_per_kwh * (p_ch + p_dis) * dt_h
                    + curtail_penalty_per_kwh * curt * dt_h
                )
                move = (p_ch + p_dis) * dt_h
                if cost < curr[j] - EPS or (
                    abs(cost - curr[j]) <= EPS and move < curr_move[j] - 1e-12
                ):
                    curr[j] = cost
                    curr_move[j] = move
                    parent[j] = i
        parents.append(parent)
        prev = curr
        prev_move = curr_move

    if terminal == "cycle":
        end = i0
        total = prev[end]
    else:
        end = -1
        total = INF
        for j in range(states + 1):
            if prev[j] == INF:
                continue
            value = prev[j] - terminal_value_per_kwh * energies[j]
            if value < total - EPS:
                total = value
                end = j
    if end < 0 or total == INF:
        return {
            "feasible": False,
            "reason": "no schedule satisfies SOC, power and PCC limits",
        }

    idx = [0] * (n + 1)
    idx[n] = end
    for t in range(n - 1, -1, -1):
        idx[t] = parents[t][idx[t + 1]]
        if idx[t] < 0:
            return {"feasible": False, "reason": "broken dynamic-programming path"}

    soc = [0.0] * (n + 1)
    p_charge = [0.0] * n
    p_discharge = [0.0] * n
    p_import = [0.0] * n
    p_export = [0.0] * n
    p_curtail = [0.0] * n
    energy = [0.0] * (n + 1)

    for t in range(n):
        energy[t] = energies[idx[t]]
        e0 = energy[t] * decay
        e_j = energies[idx[t + 1]]
        delta = e_j - e0
        if delta >= 0.0:
            p_ch = delta / (eta_charge * dt_h) if delta > EPS else 0.0
            p_dis = 0.0
        else:
            p_ch = 0.0
            p_dis = (-delta) * eta_discharge / dt_h
        net = load[t] + p_ch - p_dis - pv[t]
        if net >= 0.0:
            imp, exp, curt = net, 0.0, 0.0
        else:
            surplus = -net
            exp = surplus if surplus < export_limit else export_limit
            curt = surplus - exp
            imp = 0.0
        p_charge[t] = p_ch
        p_discharge[t] = p_dis
        p_import[t] = imp
        p_export[t] = exp
        p_curtail[t] = curt
        soc[t] = soc_min + energy[t] / capacity_kwh
    energy[n] = energies[idx[n]]
    soc[n] = soc_min + energy[n] / capacity_kwh

    buy_cost = sum(buy[t] * p_import[t] * dt_h for t in range(n))
    sell_revenue = sum(sell[t] * p_export[t] * dt_h for t in range(n))
    throughput = sum((p_charge[t] + p_discharge[t]) * dt_h for t in range(n))
    degradation = throughput * degradation_per_kwh
    curtail_penalty = sum(p_curtail[t] * dt_h for t in range(n)) * curtail_penalty_per_kwh
    net_cost = buy_cost - sell_revenue + degradation + curtail_penalty

    return {
        "feasible": True,
        "cost": net_cost,
        "buy_cost": buy_cost,
        "sell_revenue": sell_revenue,
        "degradation_cost": degradation,
        "curtailment_penalty": curtail_penalty,
        "schedule": {
            "p_charge_kw": p_charge,
            "p_discharge_kw": p_discharge,
            "p_import_kw": p_import,
            "p_export_kw": p_export,
            "pv_curtailed_kw": p_curtail,
            "soc": soc,
        },
        "throughput_kwh": throughput,
        "equivalent_cycles": throughput / (2.0 * capacity_kwh),
        "imported_kwh": sum(p_import) * dt_h,
        "exported_kwh": sum(p_export) * dt_h,
        "curtailed_kwh": sum(p_curtail) * dt_h,
        "peak_import_kw": max(p_import),
        "peak_export_kw": max(p_export),
        "reserve_up_margin_kwh": min(energy) - e_res_up,
        "reserve_dn_margin_kwh": usable - max(energy) - e_res_dn,
        "terminal_soc": soc[-1],
        "states": states,
    }


def baseline_day(
    buy_price,
    load_kw,
    pv_kw=None,
    *,
    sell_price=None,
    dt_h=0.25,
    pcc_import_kw=None,
    pcc_export_kw=0.0,
    curtail_penalty_per_kwh=0.0,
):
    """No-storage cost, used as the counterfactual in worked examples."""
    buy = _vector(buy_price, "buy_price")
    load = _vector(load_kw, "load_kw")
    n = len(buy)
    if len(load) != n:
        raise ValueError("buy_price and load_kw must have the same length")
    pv = [0.0] * n if pv_kw is None else _vector(pv_kw, "pv_kw")
    sell = [0.0] * n if sell_price is None else _vector(sell_price, "sell_price")
    import_limit = INF if pcc_import_kw is None else float(pcc_import_kw)
    export_limit = float(pcc_export_kw)

    buy_cost = 0.0
    sell_revenue = 0.0
    curtailed = 0.0
    imported = 0.0
    exported = 0.0
    peak = 0.0
    for t in range(n):
        net = load[t] - pv[t]
        if net >= 0:
            imp, exp, curt = net, 0.0, 0.0
        else:
            surplus = -net
            exp = surplus if surplus < export_limit else export_limit
            curt = surplus - exp
            imp = 0.0
        if imp > import_limit + EPS:
            return {
                "feasible": False,
                "reason": f"load exceeds PCC import limit at interval {t}",
            }
        buy_cost += buy[t] * imp * dt_h
        sell_revenue += sell[t] * exp * dt_h
        curtailed += curt * dt_h
        imported += imp * dt_h
        exported += exp * dt_h
        peak = max(peak, imp)
    return {
        "feasible": True,
        "cost": buy_cost - sell_revenue + curtail_penalty_per_kwh * curtailed,
        "buy_cost": buy_cost,
        "sell_revenue": sell_revenue,
        "curtailed_kwh": curtailed,
        "imported_kwh": imported,
        "exported_kwh": exported,
        "peak_import_kw": peak,
    }
