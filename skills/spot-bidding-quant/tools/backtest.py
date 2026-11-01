"""Rolling-origin backtesting with an explicit no-leakage protocol.

Rules enforced here:
  * a prediction for day t may only use days < t;
  * the residual-correction model is fitted on past *out-of-sample* errors,
    never on in-sample fit;
  * metrics are reported per day and averaged, so one extreme day cannot
    flatter the aggregate.
"""

from __future__ import annotations

import forecast as fc


def rolling_predict(days: list[list[float]], model, start: int = 21, end: int | None = None):
    end = len(days) if end is None else end
    preds, actuals = [], []
    for t in range(start, end):
        preds.append(model(days, t))
        actuals.append(days[t])
    return preds, actuals


def rolling_corrected(days: list[list[float]], base_model, train_days: int = 14, start: int = 21, end: int | None = None):
    """Rolling prediction with an out-of-sample residual-correction layer."""
    end = len(days) if end is None else end
    preds, actuals = [], []
    for t in range(start, end):
        hist_preds, hist_actuals, weekdays = [], [], []
        for d in range(max(7, t - train_days), t):
            hist_preds.append(base_model(days, d))
            hist_actuals.append(days[d])
            weekdays.append(d % 7)
        model = fc.fit_residual_model(hist_preds, hist_actuals, weekdays)
        corrected = fc.apply_residual_model(base_model(days, t), t % 7, model)
        preds.append(corrected)
        actuals.append(days[t])
    return preds, actuals


def summarize(preds: list[list[float]], actuals: list[list[float]], spike_threshold: float = 800.0) -> dict:
    flat_p = [v for day in preds for v in day]
    flat_a = [v for day in actuals for v in day]
    directions = [fc.direction_accuracy(p, a) for p, a in zip(preds, actuals)]
    return {
        "days": len(preds),
        "mae": fc.mae(flat_p, flat_a),
        "rmse": fc.rmse(flat_p, flat_a),
        "mape": fc.mape(flat_p, flat_a),
        "bias": fc.bias(flat_p, flat_a),
        "direction_accuracy": sum(directions) / len(directions),
        "spike_recall": fc.spike_recall(flat_p, flat_a, spike_threshold),
    }


def compare(days: list[list[float]], models: dict, start: int = 21) -> dict[str, dict]:
    """Every model sees the same evaluation window; first entry should be the baseline."""
    out = {}
    for name, fn in models.items():
        preds, actuals = rolling_predict(days, fn, start=start)
        out[name] = summarize(preds, actuals)
    return out


def improvement(baseline: dict, candidate: dict, metric: str = "mae") -> float:
    """Relative improvement of candidate over baseline, positive = better."""
    return (baseline[metric] - candidate[metric]) / baseline[metric]


def pnl_by_quantile(preds: list[list[float]], actuals: list[list[float]], q: float) -> dict:
    """Coverage check for a probabilistic forecast: actual <= predicted q share."""
    covered = total = 0
    for p, a in zip(preds, actuals):
        for pv, av in zip(p, a):
            total += 1
            covered += 1 if av <= pv else 0
    return {"target": q, "observed": covered / total if total else 0.0}
