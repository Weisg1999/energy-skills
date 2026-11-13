"""Self-test: exercises the whole chain and asserts the claims made in SKILL.md.

CI entry point. Any assertion failure means the skill's stated guarantees are
no longer true, so the text must change together with the code.

Run:  python tools/selftest.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backtest as bt
import bid
import desk
import forecast as fc
import simulate
import weather as wx
import network as nw
from dataio import load_rows, to_days


def build_models(days: list[list[float]]) -> dict:
    return {
        "seasonal_naive": lambda d, t: fc.seasonal_naive(d, t),
        "similar_day": lambda d, t: fc.similar_day(d, t),
        "ar2": lambda d, t: fc.ar_forecast(d, t),
    }


def section(title: str) -> None:
    print(f"\n== {title}")


def main() -> int:
    rows = load_rows()
    load_actual = to_days(rows, "load_actual_mw")
    load_forecast = to_days(rows, "load_forecast_mw")
    price = to_days(rows, "da_price")
    rt_price = to_days(rows, "rt_price")

    assert len(load_actual) == 60 and len(load_actual[0]) == 96, "unexpected data shape"

    section("load forecast")
    flat_fc = [v for day in load_forecast for v in day]
    flat_act = [v for day in load_actual for v in day]
    given_mape = fc.mape(flat_fc, flat_act)
    print(f"provided day-ahead load forecast MAPE = {given_mape:.3%}")
    assert given_mape < 0.04, "provided load forecast is worse than the documented ~1.5-3%"

    baseline = bt.rolling_predict(load_actual, lambda d, t: fc.seasonal_naive(d, t))
    base_summary = bt.summarize(*baseline)
    print(f"seasonal_naive  MAE={base_summary['mae']:.0f} MW  MAPE={base_summary['mape']:.2%}")

    similar = bt.rolling_predict(load_actual, lambda d, t: fc.similar_day(d, t))
    similar_summary = bt.summarize(*similar)
    print(f"similar_day     MAE={similar_summary['mae']:.0f} MW  MAPE={similar_summary['mape']:.2%}")

    corrected = bt.rolling_corrected(load_actual, lambda d, t: fc.similar_day(d, t))
    corrected_summary = bt.summarize(*corrected)
    print(f"similar+resid   MAE={corrected_summary['mae']:.0f} MW  MAPE={corrected_summary['mape']:.2%}")

    assert corrected_summary["mae"] < base_summary["mae"], "residual correction must beat seasonal naive"
    gain = bt.improvement(base_summary, corrected_summary)
    print(f"improvement over baseline = {gain:.1%} (MAE)")
    assert gain > 0.10, "documented MAE improvement is at least 10%"

    section("price forecast")
    price_base = bt.rolling_predict(price, lambda d, t: fc.seasonal_naive(d, t))
    price_corrected = bt.rolling_corrected(price, lambda d, t: fc.similar_day(d, t))
    pb, pc = bt.summarize(*price_base), bt.summarize(*price_corrected)
    print(f"seasonal_naive  MAE={pb['mae']:.1f} CNY/MWh  dir={pb['direction_accuracy']:.1%}  spike_recall={pb['spike_recall']:.1%}")
    print(f"similar+resid   MAE={pc['mae']:.1f} CNY/MWh  dir={pc['direction_accuracy']:.1%}  spike_recall={pc['spike_recall']:.1%}")
    assert pc["mae"] < pb["mae"], "corrected price forecast must beat seasonal naive"
    assert pc["direction_accuracy"] > 0.55, "direction accuracy must clear the coin-flip test"

    quantiles = fc.residual_quantiles(*price_corrected, quantiles=(0.1, 0.5, 0.9))
    print(f"residual quantiles q10/q50/q90 = {quantiles[0.1]:.1f} / {quantiles[0.5]:.1f} / {quantiles[0.9]:.1f}")
    assert quantiles[0.1] < quantiles[0.9], "price cone must widen in the right direction"

    section("bid construction")
    samples = [v for day in rt_price[-20:] for v in day]
    taker = bid.price_taker_optimum(280.0, samples, quantity=350.0)
    print(f"price-taker optimum: bid={taker['price']:.1f} at cost 280, expected profit={taker['profit']:.0f} CNY")
    assert abs(taker["price"] - 280.0) < 1e-6, "price taker must bid at marginal cost"
    assert taker["profit"] > 0, "profitable hours must show up in the expected value"

    pivotal = bid.pivotal_markup(cost=280.0, residual_intercept=1300.0, residual_slope=1.6)
    print(f"pivotal markup: bid={pivotal['price']:.1f}  qty={pivotal['quantity']:.0f} MW  pivotal={pivotal['pivotal']}")
    assert pivotal["price"] > 280.0 and pivotal["quantity"] < 1300.0 / 1.6

    skewed = sorted(samples)
    median = skewed[len(skewed) // 2]
    declared = bid.declared_quantity(samples, over_penalty=400.0, under_penalty=100.0)
    print(f"declared quantity under asymmetric penalty: {declared['quantity']:.0f} vs median {median:.0f} CNY/MWh")
    assert declared["quantity"] < median, "harsher over-declaration penalty must push the quantity down"

    curve = bid.bid_curve([180.0, 280.0, 420.0], [120.0, 120.0, 110.0])
    for row in curve:
        print(f"  bid {row['price']:>7.1f} CNY/MWh  qty={row['quantity']:.0f} MW  cum={row['cumulative']:.0f} MW")
    assert [r["price"] for r in curve] == sorted(r["price"] for r in curve), "curve must be monotone"
    assert curve[0]["price"] == 180.0, "default curve is a pure cost stack (markup = 0)"

    spread = bid.storage_arbitrage_threshold(0.88, 60.0)
    print(f"storage break-even spread at 88% efficiency, CNY 60/MWh cycle cost = {spread:.1f} CNY/MWh")
    assert spread > 0

    section("market simulation")
    participants = [
        simulate.Participant("coal-a", cost=270.0, capacity=600.0),
        simulate.Participant("coal-b", cost=300.0, capacity=500.0),
        simulate.Participant("gas-c", cost=420.0, capacity=300.0),
        simulate.Participant("wind-d", cost=0.0, capacity=400.0),
    ]
    for p in participants:
        p.segments = [(p.cost, p.capacity)]
    market = simulate.clear(participants, demand_mw=1300.0)
    print(f"clearing={market['clearing_price']:.1f}  served={market['served_mw']:.0f} MW  HHI={market['hhi']:.0f}")
    assert market["clearing_price"] == 300.0, "marginal unit sets the price"
    assert 0.0 <= market["hhi"] <= 10000.0

    sweep = simulate.bid_sweep(participants, 1300.0, "coal-b", [300.0, 350.0, 400.0, 450.0])
    for row in sweep:
        print(f"  bid={row['bid']:.0f}  clear={row['clearing_price']:.0f}  mw={row['dispatched_mw']:.0f}  profit={row['profit']:.0f}")
    pivotal_rows = [row for row in sweep if row["bid"] < 420.0]
    assert all(row["dispatched_mw"] > 0 and row["sets_price"] for row in pivotal_rows), "pivotal unit prices the margin"
    assert [row["profit"] for row in pivotal_rows] == sorted(row["profit"] for row in pivotal_rows), "profit rises with the bid while pivotal"
    assert sweep[-1]["dispatched_mw"] == 0 and sweep[-1]["clearing_price"] == 420.0, "above the next rival the unit is priced out"

    section("weather-to-power conversion chain")
    assert wx.degree_days([32.0, 35.0, 29.0], kind="cdd") == 42.0, "three-day CDD"
    assert wx.degree_days([5.0, 8.0, 3.0], kind="hdd") == 38.0, "three-day HDD"
    assert wx.temperature_load_mw(1000.0, 42.0, 12.0, 30.0) == 1534.0, "temperature load split"
    print("cdd=42.0  hdd=38.0  load=1534.0 MW")

    p8 = wx.wind_power_mw(8.0, 100.0)
    p8_rho = wx.wind_power_mw(8.0, 100.0, rho=1.15)
    hub_v = wx.hub_height_wind(6.0, 10.0, 100.0)
    assert abs(p8 - 28.5126) < 1e-3 and abs(p8_rho - 26.7670) < 1e-3
    assert wx.wind_power_mw(2.0, 100.0) == 0.0, "below cut-in"
    assert wx.wind_power_mw(13.0, 100.0) == 100.0, "capped at rated"
    assert wx.wind_power_mw(26.0, 100.0) == 0.0, "above cut-out"
    assert abs(hub_v - 8.2823) < 1e-3
    print(f"wind@8m/s={p8:.4f} MW  density_derated={p8_rho:.4f} MW  hub_v={hub_v:.4f} m/s")

    t_cell = wx.cell_temperature_c(32.0, 850.0)
    pv = wx.pv_dc_mw(850.0, 100.0, t_cell)
    assert abs(t_cell - 58.5625) < 1e-9 and abs(pv - 75.0152) < 1e-3
    assert wx.pv_dc_mw(0.0, 100.0, t_cell) == 0.0, "night output"
    print(f"cell_temp={t_cell:.4f} C  pv_dc={pv:.4f} MW")

    scenarios = [80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0]
    q_star = wx.optimal_bid_quantile(0.6, 0.4)
    declared = wx.bid_from_ensemble(scenarios, 0.6, 0.4)
    loss_mean = wx.asymmetric_loss(100.0, scenarios, 0.6, 0.4)
    loss_opt = wx.asymmetric_loss(declared, scenarios, 0.6, 0.4)
    assert q_star == 0.6 and declared == 104.0, "newsvendor quantile beats the mean"
    assert loss_opt < loss_mean
    print(f"q*={q_star:.2f}  declare={declared:.1f} MW  loss_opt={loss_opt:.4f} < loss_mean={loss_mean:.4f}")

    assert wx.weather_future_payout(1850.0, 1800.0, 20.0, 10.0) == 10000.0
    assert wx.weather_future_payout(1850.0, 1800.0, 20.0, 10.0, cap=8000.0) == 8000.0
    assert wx.basis_gap(1850.0, 1790.0) == 60.0
    assert wx.inflow_index_mm([20.0, 0.0, 35.0], 0.6, 1) == [0.0, 12.0, 0.0]
    print("hdd_payout=10000  capped=8000  basis_gap=60  lagged_runoff=[0,12,0]")

    section("grid constraints and locational prices")
    cong = nw.two_node_clearing(200.0, 1000.0, 500.0, 1000.0, 300.0, 600.0, 200.0)
    assert cong["congested"] and cong["p_a"] == 200.0 and cong["p_b"] == 500.0
    assert cong["flow_mw"] == 200.0 and cong["congestion_rent"] == 60000.0
    assert cong["unbounded_price"] == 200.0, "without the limit one uniform price"
    free = nw.two_node_clearing(200.0, 1000.0, 500.0, 1000.0, 300.0, 600.0, 700.0)
    assert not free["congested"] and free["p_a"] == free["p_b"] == 200.0 and free["congestion_rent"] == 0.0
    assert nw.location_basis(500.0, 200.0) == 300.0
    atc = nw.available_transfer_capability(2000.0, 0.10, 0.05, 0.02)
    assert abs(atc - 1675.8) < 1e-6
    assert cong["congestion_rent"] == (500.0 - 200.0) * 200.0, "same calibre as market.py::congestion_surplus"
    print(f"p_a={cong['p_a']:.0f}  p_b={cong['p_b']:.0f}  flow={cong['flow_mw']:.0f} MW  rent={cong['congestion_rent']:.0f}  ATC={atc:.1f} MW")

    section("desk layer: clock, frontier, bridge, public-data gate")
    timeline = desk.trading_day_timeline()
    print(f"timeline stages={len(timeline)}  first={timeline[0]['time']}  last={timeline[-1]['time']}")
    assert len(timeline) == 9 and all(row["cutoff"] and row["failure"] for row in timeline)

    contract_curve = bid.bid_curve([200.0, 260.0, 340.0], [120.0, 120.0, 110.0])
    scenarios = [
        {"price": 180.0, "prob": 0.10},
        {"price": 240.0, "prob": 0.15},
        {"price": 270.0, "prob": 0.10},
        {"price": 300.0, "prob": 0.30},
        {"price": 420.0, "prob": 0.20},
        {"price": 650.0, "prob": 0.15},
    ]
    candidates = [
        {"name": "spot only", "curve": contract_curve, "contract_quantity": 0.0},
        {"name": "100 MW contract", "curve": contract_curve, "contract_quantity": 100.0},
        {"name": "200 MW contract", "curve": contract_curve, "contract_quantity": 200.0},
    ]
    metrics = {}
    for candidate in candidates:
        m = desk.curve_metrics(
            candidate["curve"],
            scenarios,
            contract_quantity=candidate["contract_quantity"],
            contract_price=320.0,
            alpha=0.10,
            fixed_cost=20000.0,
        )
        metrics[candidate["name"]] = m
        print(
            f"  {candidate['name']:<16} E={m['expected']:.0f}  CVaR={m['cvar']:.0f}  "
            f"worst={m['worst']:.0f}  std={m['std']:.0f}  dispatch={m['mean_dispatch']:.1f}"
        )
    assert metrics["spot only"]["expected"] == 17835.0
    assert metrics["100 MW contract"]["expected"] == 14585.0
    assert metrics["200 MW contract"]["expected"] == 11335.0
    assert [metrics[name]["cvar"] for name in ("spot only", "100 MW contract", "200 MW contract")] == [
        -20000.0,
        -7200.0,
        -400.0,
    ]
    assert all(m["mean_dispatch"] == 236.5 for m in metrics.values())

    frontier = desk.risk_frontier(
        candidates, scenarios, contract_price=320.0, alpha=0.10, fixed_cost=20000.0
    )
    print(f"frontier = {[row['name'] for row in frontier]}")
    assert len(frontier) == 3, "no contract size dominates on both mean and tail in this example"

    marked = bid.bid_curve([200.0, 260.0, 340.0], [120.0, 120.0, 110.0], markup=0.05)
    marked_m = desk.curve_metrics(
        marked, scenarios, contract_quantity=100.0, contract_price=320.0, alpha=0.10, fixed_cost=20000.0
    )
    cost_m = metrics["100 MW contract"]
    print(
        f"cost curve E={cost_m['expected']:.0f} dispatch={cost_m['mean_dispatch']:.1f}  "
        f"+5% E={marked_m['expected']:.0f} dispatch={marked_m['mean_dispatch']:.1f}"
    )
    assert cost_m["expected"] > marked_m["expected"] and cost_m["mean_dispatch"] > marked_m["mean_dispatch"]
    assert cost_m["cvar"] == marked_m["cvar"], "markup cuts dispatch without changing the worst scenario"

    plan = {"q_da": 300.0, "q_actual": 310.0, "p_da": 300.0, "p_rt": 420.0}
    actual = {"q_da": 290.0, "q_actual": 320.0, "p_da": 320.0, "p_rt": 480.0}
    bridge = desk.settlement_bridge(
        plan,
        actual,
        cost=220.0,
        contract_quantity=100.0,
        contract_price=320.0,
        penalty=2000.0,
        allocation=500.0,
    )
    print(
        f"bridge plan={bridge['plan_profit']:.0f} actual={bridge['actual_profit']:.0f} "
        f"delta={bridge['delta']:.0f} gap={bridge['identity_gap']:.6f}"
    )
    assert bridge["delta"] == 6300.0 and abs(bridge["identity_gap"]) < 1e-6
    assert [bucket["amount"] for bucket in bridge["buckets"]] == [
        -3200.0,
        4000.0,
        9600.0,
        600.0,
        -2200.0,
        -2000.0,
        -500.0,
    ]

    implicit = desk.implicit_cost(
        plan,
        actual,
        cost=220.0,
        available=350.0,
        contract_quantity=100.0,
        contract_price=320.0,
        penalty=2000.0,
    )
    print(f"implicit opportunity=6000 deviation=2000 total={implicit['total_positive']:.0f}")
    assert implicit["total_positive"] == 8000.0

    packet = desk.dispute_packet(bridge, threshold=1000.0)
    print(f"dispute packet items={len(packet)} top={packet[0]['item']} {packet[0]['amount']:.0f}")
    assert len(packet) == 5 and packet[0]["amount"] == 9600.0

    fields = [
        "date",
        "slot",
        "load_forecast_mw",
        "load_actual_mw",
        "da_price",
        "rt_price",
    ]
    report = desk.validate_public_dataset(rows, fields)
    print(
        f"public-data check ok={report['ok']} rows={report['row_count']} "
        f"days={report['date_count']} slots={len(rows) // max(1, report['date_count'])}"
    )
    assert report["ok"] and report["row_count"] == 5760 and report["date_count"] == 60
    duplicated = list(rows)
    duplicated.insert(10, dict(rows[10]))
    assert not desk.validate_public_dataset(duplicated, fields)["ok"], "duplicate point must fail the gate"
    holed = list(rows)
    del holed[500]
    assert not desk.validate_public_dataset(holed, fields)["ok"], "missing slot must fail the gate"
    no_date = list(rows)
    no_date[100] = {key: value for key, value in rows[100].items() if key != "date"}
    missing_report = desk.validate_public_dataset(no_date, fields)
    assert not missing_report["ok"] and "date" in missing_report["missing_fields"]

    section("storage bridge and instance pack")
    plan = {
        "price": [300.0, 200.0, 200.0],
        "discharge_mw": [100.0, 100.0, 0.0],
        "charge_mw": [0.0, 0.0, 100.0],
    }
    actual = {
        "price": [320.0, 220.0, 220.0],
        "discharge_mw": [92.0, 100.0, 0.0],
        "charge_mw": [0.0, 0.0, 104.0],
    }
    storage = desk.storage_bridge(
        plan,
        actual,
        dt_h=0.25,
        contract_quantity_mw=40.0,
        contract_price=265.0,
        penalty_actual=200.0,
        allocation_actual=10.0,
    )
    amounts = {row["item"]: row["amount"] for row in storage["buckets"]}
    print(
        f"storage bridge plan={storage['plan_profit']:.0f} actual={storage['actual_profit']:.0f} "
        f"delta={storage['delta']:.0f} gap={storage['identity_gap']:.2e}"
    )
    assert storage["plan_profit"] == 8450.0
    assert storage["actual_profit"] == 7280.0
    assert storage["delta"] == -1170.0
    assert abs(storage["identity_gap"]) < 1e-9
    assert amounts == {
        "放电量偏差": -600.0,
        "放电价偏差": 1000.0,
        "放电量价交叉": -40.0,
        "充电量偏差": -200.0,
        "充电价偏差": -500.0,
        "充电量价交叉": -20.0,
        "退化成本": 0.0,
        "合约价差": -600.0,
        "容量补偿": 0.0,
        "考核": -200.0,
        "分摊": -10.0,
    }

    repo_root = Path(__file__).resolve().parents[3]
    pack_dir = (
        repo_root / "skills" / "spot-bidding-quant" / "instances" / "shandong-storage-2026-11"
    )
    spec = importlib.util.spec_from_file_location("shandong_storage_instance", pack_dir / "run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    instance_path = pack_dir / "instance.json"
    config = json.loads(instance_path.read_text(encoding="utf-8"))
    instance_report = runner.validate_instance(config)
    print(
        f"instance config ok={instance_report['ok']} points={instance_report['points_per_day']} "
        f"warnings={len(instance_report['warnings'])}"
    )
    assert instance_report["ok"] and instance_report["points_per_day"] == 96
    assert instance_report["mtu_min"] == 15

    broken = json.loads(json.dumps(config))
    del broken["rules"]["spot"]["grade"]
    try:
        runner.validate_instance(broken)
    except runner.ConfigError:
        pass
    else:
        raise AssertionError("a rule block without grade must be rejected")

    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run_instance(
            instance_path,
            pack_dir / "data" / "d1_demo.csv",
            pack_dir / "data" / "t1_demo.csv",
            Path(tmp),
        )
        summary = result["summary"]
        plan_summary = summary["plan"]
        print(
            f"instance demo cycles={plan_summary['equivalent_cycles']:.2f} "
            f"E={plan_summary['expected_net_margin_cny']:.0f} "
            f"CVaR10={plan_summary['cvar_10_cny']:.0f} "
            f"bridge gap={result['bridge']['identity_gap']:.2e}"
        )
        assert result["report"]["ok"]
        assert plan_summary["equivalent_cycles"] <= summary["policy"]["max_cycles_per_day"] + 1e-9
        assert plan_summary["cvar_10_cny"] <= plan_summary["expected_net_margin_cny"] + 1e-9
        assert abs(result["bridge"]["identity_gap"]) < 1e-6
        assert len(result["bid"]["rows"]) > 0
        assert (Path(tmp) / "bid_sheet.csv").exists()
        assert (Path(tmp) / "review.md").exists()

    section("gansu wind instance")
    gansu_dir = (
        repo_root / "skills" / "spot-bidding-quant" / "instances" / "gansu-wind-2027"
    )
    gansu_spec = importlib.util.spec_from_file_location("gansu_wind_instance", gansu_dir / "run.py")
    gansu = importlib.util.module_from_spec(gansu_spec)
    gansu_spec.loader.exec_module(gansu)
    gansu_config = json.loads((gansu_dir / "instance.json").read_text(encoding="utf-8"))
    gansu_report = gansu.validate_instance(gansu_config)
    print(
        f"gansu config ok={gansu_report['ok']} points={gansu_report['points_per_day']} "
        f"mech={gansu_report['predicates']['mechanism_price']:.1f} "
        f"ratio={gansu_report['predicates']['mechanism_ratio']:.2f}"
    )
    assert gansu_report["ok"] and gansu_report["points_per_day"] == 96
    assert gansu_report["mtu_min"] == 15
    assert gansu_report["bounds"] == {
        "declare_floor": 40.0,
        "declare_cap": 500.0,
        "clear_floor": 40.0,
        "clear_cap": 650.0,
    }
    assert gansu_report["predicates"]["mechanism_price"] == 244.0
    assert gansu_report["predicates"]["mechanism_ratio"] == 0.3
    assert gansu_report["predicates"]["bid_price"] == 40.0
    assert gansu_config["rules"]["capacity_compensation"]["applicable_to_wind"] is False

    wrong_batch = json.loads(json.dumps(gansu_config))
    wrong_batch["rules"]["mechanism"]["batches_cny_per_mwh"]["wind_2027h1"] = 195.4
    try:
        gansu.validate_instance(wrong_batch)
    except gansu.ConfigError:
        pass
    else:
        raise AssertionError("2027H1 wind mechanism price must stay 244.0 CNY/MWh")

    payable = json.loads(json.dumps(gansu_config))
    payable["rules"]["capacity_compensation"]["applicable_to_wind"] = True
    try:
        gansu.validate_instance(payable)
    except gansu.ConfigError:
        pass
    else:
        raise AssertionError("wind must not receive the reliable capacity payment")

    with tempfile.TemporaryDirectory() as tmp:
        result = gansu.run_instance(
            gansu_dir / "instance.json",
            gansu_dir / "data" / "d1_demo.csv",
            gansu_dir / "data" / "t1_demo.csv",
            Path(tmp),
        )
        summary = result["summary"]
        plan = summary["plan"]
        actual = summary["actual"]
        bridge = result["bridge"]
        print(
            f"gansu demo declared={plan['declared_energy_mwh']:.1f} "
            f"plan={plan['reference_net_margin_cny']:.0f} "
            f"E={plan['expected_net_margin_cny']:.0f} "
            f"CVaR20={plan['cvar_cny']:.0f} "
            f"actual={actual['net_margin_cny']:.0f} "
            f"gap={bridge['identity_gap']:.2e}"
        )
        assert result["report"]["ok"]
        assert abs(plan["declared_energy_mwh"] - 2442.0) < 1.0
        assert abs(plan["reference_net_margin_cny"] - 552046.0) < 2.0
        assert abs(plan["expected_net_margin_cny"] - 569378.0) < 2.0
        assert plan["cvar_cny"] <= plan["expected_net_margin_cny"] + 1e-9
        assert abs(actual["net_margin_cny"] - 581869.0) < 2.0
        assert abs(actual["assessment_cny"] - 349.0) < 1.0
        assert actual["fishing"]["daily_completion_ratio"] > 1.0
        assert actual["fishing"]["slots_below_threshold"] > 0
        assert len(bridge["buckets"]) == 7
        assert abs(bridge["identity_gap"]) < 1e-6
        assert abs(
            bridge["delta"] - sum(item["amount"] for item in bridge["buckets"])
        ) < 1e-6
        assert len(summary["policy_fingerprint"]) == 12
        assert (Path(tmp) / "bid_sheet.csv").exists()
        assert (Path(tmp) / "bridge.csv").exists()
        assert (Path(tmp) / "review.md").exists()

    section("shanxi storage instance")
    shanxi_dir = (
        repo_root / "skills" / "spot-bidding-quant" / "instances" / "shanxi-storage-2026-11"
    )
    shanxi_spec = importlib.util.spec_from_file_location(
        "shanxi_storage_instance", shanxi_dir / "run.py"
    )
    shanxi = importlib.util.module_from_spec(shanxi_spec)
    shanxi_spec.loader.exec_module(shanxi)
    shanxi_config = json.loads((shanxi_dir / "instance.json").read_text(encoding="utf-8"))
    shanxi_report = shanxi.validate_instance(shanxi_config)
    print(
        f"shanxi config ok={shanxi_report['ok']} points={shanxi_report['points_per_day']} "
        f"mtu={shanxi_report['mtu_min']:g} fuse={shanxi_report['fuse']['duration_hours']:.1f}h"
    )
    assert shanxi_report["ok"] and shanxi_report["points_per_day"] == 288
    assert shanxi_report["mtu_min"] == 5.0
    assert shanxi_report["bounds"] == {
        "declare_floor": 0.0,
        "declare_cap": 1500.0,
        "clear_floor": 0.0,
        "clear_cap": 1500.0,
    }
    assert shanxi_report["fuse"]["window_start"] == "17:00"
    assert shanxi_report["fuse"]["window_end"] == "19:00"
    assert shanxi_report["fuse"]["duration_hours"] == 2.0
    assert shanxi_report["fuse"]["settlement_price"] == 450.0
    assert shanxi_config["rules"]["capacity_compensation"]["applicable_to_storage"] is False
    assert shanxi_config["rules"]["capacity_compensation"]["price_cny_per_kw_year"] is None

    fifteen_minute = json.loads(json.dumps(shanxi_config))
    fifteen_minute["rules"]["spot"]["market_time_unit_min"] = 15
    fifteen_minute["rules"]["spot"]["points_per_day"] = 96
    try:
        shanxi.validate_instance(fifteen_minute)
    except shanxi.ConfigError:
        pass
    else:
        raise AssertionError("Shanxi must reject the 15-minute / 96-point template")

    paid_capacity = json.loads(json.dumps(shanxi_config))
    paid_capacity["rules"]["capacity_compensation"]["applicable_to_storage"] = True
    try:
        shanxi.validate_instance(paid_capacity)
    except shanxi.ConfigError:
        pass
    else:
        raise AssertionError("independent storage must not book the coal capacity payment")

    priced_capacity = json.loads(json.dumps(shanxi_config))
    priced_capacity["rules"]["capacity_compensation"]["price_cny_per_kw_year"] = 165.0
    try:
        shanxi.validate_instance(priced_capacity)
    except shanxi.ConfigError:
        pass
    else:
        raise AssertionError("storage capacity price must stay null until verified")

    short_fuse = json.loads(json.dumps(shanxi_config))
    short_fuse["rules"]["fuse"]["max_duration_hours"] = 12.0
    try:
        shanxi.validate_instance(short_fuse)
    except shanxi.ConfigError:
        pass
    else:
        raise AssertionError("fuse duration cap must stay at 24 h")

    with tempfile.TemporaryDirectory() as tmp:
        result = shanxi.run_instance(
            shanxi_dir / "instance.json",
            shanxi_dir / "data" / "d1_demo.csv",
            shanxi_dir / "data" / "t1_demo.csv",
            Path(tmp),
        )
        summary = result["summary"]
        plan = summary["plan"]
        actual = summary["actual"]
        bridge = result["bridge"]
        fuse = summary["fuse_stress"]
        print(
            f"shanxi demo cycles={plan['cycles']:.2f} "
            f"plan={plan['reference_net_margin_cny']:.0f} "
            f"E={plan['expected_net_margin_cny']:.0f} "
            f"CVaR10={plan['cvar_10_cny']:.0f} "
            f"actual={actual['net_margin_cny']:.0f} "
            f"fuse={fuse['delta_cny']:.0f} "
            f"gap={bridge['identity_gap']:.2e}"
        )
        assert result["report"]["ok"]
        assert plan["points_per_day"] == 288
        assert abs(plan["reference_spread_cny_per_mwh"] - 563.89) < 0.05
        assert abs(plan["charge_anchor_cny_per_mwh"] - 86.73) < 0.05
        assert abs(plan["discharge_anchor_cny_per_mwh"] - 650.62) < 0.05
        assert abs(plan["discharge_breakeven_cny_per_mwh"] - 139.78) < 0.05
        assert abs(plan["charge_breakeven_cny_per_mwh"] - 526.05) < 0.05
        assert plan["cycles"] <= summary["policy"]["max_cycles_per_day"] + 1e-9
        assert plan["switches"] == 4
        assert abs(plan["reference_net_margin_cny"] - 53314.0) < 2.0
        assert abs(plan["expected_net_margin_cny"] - 52025.0) < 2.0
        assert abs(plan["cvar_10_cny"] - 44933.0) < 2.0
        assert plan["cvar_10_cny"] <= plan["expected_net_margin_cny"] + 1e-9
        assert plan["capacity_compensation_cny"] is None
        assert sum(1 for item in plan["scenarios"] if item["rebalanced"]) == 2
        assert abs(actual["net_margin_cny"] - 59301.0) < 2.0
        assert abs(actual["degradation_cny"] - 11520.0) < 1.0
        assert abs(actual["revenue_per_discharge_mwh"] - 317.0) < 1.0
        assert len(bridge["buckets"]) == 4
        assert abs(bridge["identity_gap"]) < 1e-6
        assert abs(bridge["delta"] - sum(item["amount"] for item in bridge["buckets"])) < 1e-6
        assert abs(bridge["delta"] - 5987.0) < 2.0
        assert len(result["bridge_detail"]) == 5
        assert result["bridge_detail"][0]["start"] == "19:30"
        assert abs(fuse["delta_cny"] + 32999.0) < 2.0
        assert abs(fuse["fuse_net_margin_cny"] - 26302.0) < 2.0
        assert len(summary["policy_fingerprint"]) == 12
        assert (Path(tmp) / "bid_sheet.csv").exists()
        assert (Path(tmp) / "bridge.csv").exists()
        assert (Path(tmp) / "review.md").exists()

    section("summary")
    print("all checks passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\nFAILED: {exc}")
        traceback.print_exc()
        sys.exit(1)
