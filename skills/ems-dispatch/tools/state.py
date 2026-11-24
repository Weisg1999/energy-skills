"""Deterministic DC state-estimation and N-1 demo for the synthetic example.

The module is a teaching reference, not a production state estimator or a
security-assessment program. It intentionally uses a tiny dense network.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass


EPS = 1e-12


@dataclass(frozen=True)
class Branch:
    name: str
    frm: int
    to: int
    x: float
    limit: float | None = None


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(matrix)
    if n == 0:
        return []
    aug = [matrix[i][:] + [rhs[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) <= EPS:
            raise ValueError("singular matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        divisor = aug[col][col]
        aug[col] = [value / divisor for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if abs(factor) <= EPS:
                continue
            aug[row] = [
                left - factor * right for left, right in zip(aug[row], aug[col])
            ]
    return [aug[i][n] for i in range(n)]


def _inverse(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    aug = [
        matrix[i][:] + [1.0 if i == j else 0.0 for j in range(n)]
        for i in range(n)
    ]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) <= EPS:
            raise ValueError("singular matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        divisor = aug[col][col]
        aug[col] = [value / divisor for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if abs(factor) <= EPS:
                continue
            aug[row] = [
                left - factor * right for left, right in zip(aug[row], aug[col])
            ]
    return [row[n:] for row in aug]


def dc_power_flow(
    n_bus: int,
    branches: list[Branch],
    injections: list[float],
    slack: int = 0,
) -> dict:
    if len(injections) != n_bus:
        raise ValueError("injections length must equal n_bus")
    b_matrix = [[0.0 for _ in range(n_bus)] for _ in range(n_bus)]
    for branch in branches:
        susceptance = 1.0 / branch.x
        i, j = branch.frm, branch.to
        b_matrix[i][i] += susceptance
        b_matrix[j][j] += susceptance
        b_matrix[i][j] -= susceptance
        b_matrix[j][i] -= susceptance
    keep = [i for i in range(n_bus) if i != slack]
    reduced = [[b_matrix[i][j] for j in keep] for i in keep]
    theta_reduced = _solve(reduced, [injections[i] for i in keep])
    theta = [0.0 for _ in range(n_bus)]
    for index, bus in enumerate(keep):
        theta[bus] = theta_reduced[index]
    flows = {
        branch.name: (theta[branch.frm] - theta[branch.to]) / branch.x
        for branch in branches
    }
    return {
        "theta": theta,
        "flows": flows,
        "slack_injection": -sum(injections[i] for i in keep),
    }


def wls_estimate(
    h_matrix: list[list[float]],
    z: list[float],
    sigma: list[float],
) -> dict:
    m = len(z)
    n = len(h_matrix[0])
    if len(h_matrix) != m or len(sigma) != m:
        raise ValueError("measurement dimensions do not match")
    weights = [1.0 / (value * value) for value in sigma]
    normal = [
        [
            sum(h_matrix[k][i] * weights[k] * h_matrix[k][j] for k in range(m))
            for j in range(n)
        ]
        for i in range(n)
    ]
    rhs = [
        sum(h_matrix[k][i] * weights[k] * z[k] for k in range(m))
        for i in range(n)
    ]
    x_hat = _solve(normal, rhs)
    normal_inv = _inverse(normal)
    fitted = [
        sum(h_matrix[i][j] * x_hat[j] for j in range(n)) for i in range(m)
    ]
    residuals = [z[i] - fitted[i] for i in range(m)]
    omega = [
        sigma[i] ** 2
        - sum(
            h_matrix[i][a] * normal_inv[a][b] * h_matrix[i][b]
            for a in range(n)
            for b in range(n)
        )
        for i in range(m)
    ]
    normalized = [
        residuals[i] / math.sqrt(max(omega[i], 1e-18)) for i in range(m)
    ]
    objective = sum((residuals[i] / sigma[i]) ** 2 for i in range(m))
    return {
        "x_hat": x_hat,
        "fitted": fitted,
        "residuals": residuals,
        "normalized_residuals": normalized,
        "omega_diag": omega,
        "objective": objective,
        "degrees_of_freedom": m - n,
    }


def _select(
    h_matrix: list[list[float]],
    z: list[float],
    sigma: list[float],
    indices: list[int],
) -> tuple[list[list[float]], list[float], list[float]]:
    return (
        [h_matrix[i] for i in indices],
        [z[i] for i in indices],
        [sigma[i] for i in indices],
    )


def _connected(n_bus: int, branches: list[Branch]) -> bool:
    adjacency = [[] for _ in range(n_bus)]
    for branch in branches:
        adjacency[branch.frm].append(branch.to)
        adjacency[branch.to].append(branch.frm)
    seen = {0}
    stack = [0]
    while stack:
        bus = stack.pop()
        for nxt in adjacency[bus]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return len(seen) == n_bus


def n1_scan(
    n_bus: int,
    branches: list[Branch],
    injections: list[float],
    slack: int = 0,
) -> dict:
    base = dc_power_flow(n_bus, branches, injections, slack)
    rows = []
    for outage in branches:
        remaining = [b for b in branches if b.name != outage.name]
        if not _connected(n_bus, remaining):
            rows.append(
                {
                    "outage": outage.name,
                    "islanded": True,
                    "flows": None,
                    "overloads": [],
                    "max_excess_pu": None,
                }
            )
            continue
        try:
            result = dc_power_flow(n_bus, remaining, injections, slack)
        except ValueError:
            rows.append(
                {
                    "outage": outage.name,
                    "islanded": True,
                    "flows": None,
                    "overloads": [],
                    "max_excess_pu": None,
                }
            )
            continue
        overloads = []
        for branch in remaining:
            if branch.limit is None:
                continue
            flow = result["flows"][branch.name]
            excess = abs(flow) - branch.limit
            if excess > EPS:
                overloads.append(
                    {
                        "branch": branch.name,
                        "flow_pu": flow,
                        "limit_pu": branch.limit,
                        "excess_pu": excess,
                    }
                )
        rows.append(
            {
                "outage": outage.name,
                "islanded": False,
                "flows": result["flows"],
                "overloads": overloads,
                "max_excess_pu": max(
                    (item["excess_pu"] for item in overloads), default=0.0
                ),
            }
        )
    return {"base": base, "contingencies": rows}


MEASUREMENT_NAMES = ["P12", "P13", "P23", "theta2", "theta3", "P2", "P3"]


def demo() -> dict:
    branches = [
        Branch("1-2", 0, 1, 0.10, 0.40),
        Branch("1-3", 0, 2, 0.20, 0.30),
        Branch("2-3", 1, 2, 0.20, 0.20),
    ]
    injections = [0.0, -0.15, -0.20]
    h_matrix = [
        [-10.0, 0.0],
        [0.0, -5.0],
        [5.0, -5.0],
        [1.0, 0.0],
        [0.0, 1.0],
        [15.0, -5.0],
        [-5.0, 10.0],
    ]
    z_true = [0.200, 0.150, 0.050, -0.020, -0.030, -0.150, -0.200]
    sigma = [0.005, 0.005, 0.005, 0.002, 0.002, 0.006, 0.006]
    z_bad = z_true[:]
    z_bad[1] = 0.180

    estimate = wls_estimate(h_matrix, z_bad, sigma)
    suspect_index = max(
        range(len(z_bad)),
        key=lambda i: (abs(estimate["normalized_residuals"][i]), -i),
    )
    clean_indices = [i for i in range(len(z_bad)) if i != suspect_index]
    clean_h, clean_z, clean_sigma = _select(
        h_matrix, z_bad, sigma, clean_indices
    )
    clean = wls_estimate(clean_h, clean_z, clean_sigma)

    base = dc_power_flow(3, branches, injections)
    n1 = n1_scan(3, branches, injections)
    remedial = dc_power_flow(
        3,
        [b for b in branches if b.name != "1-2"],
        [0.0, -0.15, -0.15],
    )

    measurements = []
    for i, name in enumerate(MEASUREMENT_NAMES):
        measurements.append(
            {
                "name": name,
                "z": z_bad[i],
                "true": z_true[i],
                "sigma": sigma[i],
                "fitted": estimate["fitted"][i],
                "residual": estimate["residuals"][i],
                "normalized_residual": estimate["normalized_residuals"][i],
            }
        )

    return {
        "system": {
            "base_mva": 100.0,
            "branches": [
                {
                    "name": b.name,
                    "from": b.frm,
                    "to": b.to,
                    "x": b.x,
                    "limit": b.limit,
                }
                for b in branches
            ],
            "injections_pu": injections,
            "true_theta": [0.0, -0.020, -0.030],
        },
        "measurements": measurements,
        "estimate": estimate,
        "suspect": {
            "name": MEASUREMENT_NAMES[suspect_index],
            "index": suspect_index,
            "normalized_residual": estimate["normalized_residuals"][
                suspect_index
            ],
            "detected_at_3_sigma": abs(
                estimate["normalized_residuals"][suspect_index]
            )
            > 3.0,
        },
        "clean_estimate": clean,
        "base": base,
        "n1": n1,
        "remedial": {
            "outage": "1-2",
            "injections_pu": [0.0, -0.15, -0.15],
            "flows": remedial["flows"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()
    data = demo()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    est = data["estimate"]
    clean = data["clean_estimate"]
    print(
        f"WLS theta2={est['x_hat'][0]:.6f} theta3={est['x_hat'][1]:.6f} "
        f"J={est['objective']:.2f}"
    )
    print(
        f"suspect {data['suspect']['name']} "
        f"normalized={data['suspect']['normalized_residual']:.2f} "
        f"detected={data['suspect']['detected_at_3_sigma']}"
    )
    print(
        f"clean theta2={clean['x_hat'][0]:.6f} "
        f"theta3={clean['x_hat'][1]:.6f} J={clean['objective']:.2e}"
    )
    print("base flows " + " ".join(
        f"{name}={value:.3f}" for name, value in data["base"]["flows"].items()
    ))
    for row in data["n1"]["contingencies"]:
        if row["islanded"]:
            print(f"N-1 {row['outage']}: islanded")
            continue
        overload = row["overloads"][0] if row["overloads"] else None
        if overload:
            print(
                f"N-1 {row['outage']}: {overload['branch']} "
                f"flow={overload['flow_pu']:.3f} "
                f"limit={overload['limit_pu']:.3f} "
                f"excess={overload['excess_pu']:.3f}"
            )
        else:
            print(f"N-1 {row['outage']}: secure")
    print("remedial flows " + " ".join(
        f"{name}={value:.3f}"
        for name, value in data["remedial"]["flows"].items()
    ))


if __name__ == "__main__":
    main()