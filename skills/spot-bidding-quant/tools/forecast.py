"""Reference forecasters and accuracy metrics.

Pure standard library. The point of this module is not to compete with a
gradient-boosting stack, but to make the *evaluation protocol* explicit:
seasonal-naive baseline, similar-day baseline, a residual-correction layer,
and metrics that separate point accuracy from decision accuracy.
"""

from __future__ import annotations

import math


def mae(pred: list[float], actual: list[float]) -> float:
    return sum(abs(p - a) for p, a in zip(pred, actual)) / len(pred)


def rmse(pred: list[float], actual: list[float]) -> float:
    return math.sqrt(sum((p - a) ** 2 for p, a in zip(pred, actual)) / len(pred))


def mape(pred: list[float], actual: list[float], floor: float = 1.0) -> float:
    """MAPE with a floor; near-zero actuals make plain MAPE meaningless."""
    return sum(abs(p - a) / max(abs(a), floor) for p, a in zip(pred, actual)) / len(pred)


def bias(pred: list[float], actual: list[float]) -> float:
    return sum(p - a for p, a in zip(pred, actual)) / len(pred)


def pinball(pred: list[float], actual: list[float], q: float) -> float:
    """Quantile (pinball) loss; use this for price forecasts instead of MAPE."""
    total = 0.0
    for p, a in zip(pred, actual):
        total += (a - p) * q if a >= p else (p - a) * (1.0 - q)
    return total / len(pred)


def direction_accuracy(pred: list[float], actual: list[float], deadband: float = 5.0) -> float:
    """Share of adjacent steps whose price-change direction is predicted correctly.

    Steps where the actual change is inside +/- deadband are skipped, because
    calling the direction of noise is not a skill.
    """
    hits = total = 0
    for i in range(1, min(len(pred), len(actual))):
        da = actual[i] - actual[i - 1]
        if abs(da) < deadband:
            continue
        dp = pred[i] - pred[i - 1]
        total += 1
        hits += 1 if (dp > 0) == (da > 0) else 0
    return hits / total if total else 0.0


def spike_recall(pred: list[float], actual: list[float], threshold: float) -> float:
    """Of the slots where price exceeded `threshold`, how many were flagged."""
    flagged = total = 0
    for p, a in zip(pred, actual):
        if a >= threshold:
            total += 1
            flagged += 1 if p >= threshold else 0
    return flagged / total if total else 0.0


def seasonal_naive(days: list[list[float]], target: int, lag: int = 1) -> list[float]:
    """Same slot, `lag` days ago. The baseline every model must beat."""
    return list(days[target - lag])


def similar_day(
    days: list[list[float]],
    target: int,
    k: int = 5,
    lookback: int = 28,
    exclude: float = 0.25,
) -> list[float]:
    """Average of the k most similar recent days, by daily-energy distance.

    Days whose daily energy deviates more than `exclude` from the median of the
    lookback window are dropped before ranking, mirroring the CBL cleaning rule
    used in demand-response settlement.
    """
    start = max(0, target - lookback)
    candidates = list(range(start, target))
    energies = [sum(days[i]) for i in candidates]
    median_energy = sorted(energies)[len(energies) // 2]
    keep = [i for i, e in zip(candidates, energies) if abs(e - median_energy) <= exclude * median_energy]
    if len(keep) < k:
        keep = candidates[-k:]
    target_profile = [s / max(1e-9, sum(days[target - 1])) for s in days[target - 1]]
    target_energy = median_energy

    def distance(i: int) -> float:
        profile = [s / max(1e-9, sum(days[i])) for s in days[i]]
        shape = sum(abs(a - b) for a, b in zip(profile, target_profile))
        level = abs(sum(days[i]) - target_energy) / max(1.0, target_energy)
        return shape + level

    chosen = sorted(keep, key=distance)[:k]
    return [sum(days[i][s] for i in chosen) / len(chosen) for s in range(len(days[0]))]


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (small systems only)."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            return [0.0] * n
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(col + 1, n):
            factor = a[row][col] / a[col][col]
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    out = [0.0] * n
    for i in range(n - 1, -1, -1):
        out[i] = (a[i][n] - sum(a[i][j] * out[j] for j in range(i + 1, n))) / a[i][i]
    return out


def ar_forecast(days: list[list[float]], target: int, order: int = 2, train_days: int = 21) -> list[float]:
    """AR(p) fitted on the last `train_days` and rolled forward one day.

    Deliberately simple: a linear AR is a useful sanity check that a fancier
    model is actually earning its complexity.
    """
    start = max(0, target - train_days)
    series = [v for day in days[start:target] for v in day]
    if len(series) <= order + 2:
        return list(days[target - 1])

    rows, rhs = [], []
    for t in range(order, len(series)):
        rows.append([1.0] + [series[t - j - 1] for j in range(order)])
        rhs.append(series[t])

    k = order + 1
    xtx = [[sum(row[i] * row[j] for row in rows) for j in range(k)] for i in range(k)]
    xty = [sum(row[i] * y for row, y in zip(rows, rhs)) for i in range(k)]
    coef = _solve(xtx, xty)

    window = series[-order:][::-1]
    forecast = []
    for _ in range(len(days[0])):
        value = coef[0] + sum(coef[i + 1] * window[i] for i in range(order))
        forecast.append(value)
        window = [value] + window[:-1]
    return forecast


def fit_residual_model(
    preds: list[list[float]],
    actuals: list[list[float]],
    weekdays: list[int],
    shrinkage: float = 3.0,
) -> dict:
    """Two-factor systematic-bias model: residual ~ weekday effect + slot effect.

    Same structure as the published "time component + exogenous component"
    correction: the mean residual of a (weekday, slot) cell is shrunk toward the
    slot mean so that thin cells do not overfit.
    """
    slots = len(preds[0])
    cells: dict[tuple[int, int], list[float]] = {}
    slot_res: dict[int, list[float]] = {}
    for pred, actual, wd in zip(preds, actuals, weekdays):
        for s in range(slots):
            r = actual[s] - pred[s]
            cells.setdefault((wd, s), []).append(r)
            slot_res.setdefault(s, []).append(r)

    slot_mean = {s: sum(v) / len(v) for s, v in slot_res.items()}
    model: dict[tuple[int, int], float] = {}
    for (wd, s), values in cells.items():
        n = len(values)
        cell_mean = sum(values) / n
        base = slot_mean[s]
        model[(wd, s)] = (n * cell_mean + shrinkage * base) / (n + shrinkage)
    return {"cells": model, "slot_mean": slot_mean}


def apply_residual_model(forecast: list[float], weekday: int, model: dict) -> list[float]:
    out = []
    for s, value in enumerate(forecast):
        correction = model["cells"].get((weekday, s), model["slot_mean"].get(s, 0.0))
        out.append(value + correction)
    return out


def residual_quantiles(
    preds: list[list[float]],
    actuals: list[list[float]],
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
) -> dict[float, float]:
    """Pooled residual quantiles, used to build a price cone for bidding."""
    residuals = sorted(a - p for pred, actual in zip(preds, actuals) for p, a in zip(pred, actual))
    n = len(residuals)
    out = {}
    for q in quantiles:
        idx = min(n - 1, max(0, int(round(q * (n - 1)))))
        out[q] = residuals[idx]
    return out


def economic_value(errors_mw: list[float], prices: list[float], imbalance_penalty: float = 1.0) -> float:
    """Cost of forecast error in CNY: deviation MWh x price x penalty.

    errors_mw are 15-minute average MW deviations; divide by 4 to get MWh.
    """
    return sum(abs(e) / 4.0 * p * imbalance_penalty for e, p in zip(errors_mw, prices))
