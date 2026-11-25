"""Deterministic positive-sequence impedance-scan and tuning demo.

The model is a two-block teaching reduction: a grid Thevenin impedance with an
equivalent series-capacitive effect, and a converter impedance with a
frequency-dependent negative-resistance band. It is not a vendor model, an
electromagnetic-transient study, or a compliance test.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, replace


EPS = 1e-12
DEFAULT_TARGET_R = 0.03


@dataclass(frozen=True)
class GridImpedance:
    r_pu: float = 0.02
    x50_pu: float = 0.40
    xc50_pu: float = 5.184
    f0: float = 50.0


@dataclass(frozen=True)
class ConverterImpedance:
    x50_pu: float = 0.10
    negative_r_pu: float = 0.05
    center_hz: float = 160.0
    bandwidth_hz: float = 50.0
    virtual_r_pu: float = 0.0
    f0: float = 50.0


def grid_impedance(f_hz: float, grid: GridImpedance) -> complex:
    ratio = f_hz / grid.f0
    return complex(grid.r_pu, grid.x50_pu * ratio - grid.xc50_pu / ratio)


def converter_impedance(f_hz: float, conv: ConverterImpedance) -> complex:
    ratio = f_hz / conv.f0
    offset = (f_hz - conv.center_hz) / conv.bandwidth_hz
    negative = -conv.negative_r_pu / (1.0 + offset * offset)
    return complex(negative + conv.virtual_r_pu, conv.x50_pu * ratio)


def impedance_at(
    f_hz: float, grid: GridImpedance, conv: ConverterImpedance
) -> dict[str, float]:
    zg = grid_impedance(f_hz, grid)
    zc = converter_impedance(f_hz, conv)
    z = zg + zc
    return {
        "frequency_hz": f_hz,
        "grid_r_pu": zg.real,
        "grid_x_pu": zg.imag,
        "converter_r_pu": zc.real,
        "converter_x_pu": zc.imag,
        "r_pu": z.real,
        "x_pu": z.imag,
        "magnitude_pu": abs(z),
        "zeta": damping_ratio(f_hz, grid, conv),
    }


def damping_ratio(f_hz: float, grid: GridImpedance, conv: ConverterImpedance) -> float:
    h = max(f_hz * 1e-5, 1e-4)
    z_plus = grid_impedance(f_hz + h, grid) + converter_impedance(f_hz + h, conv)
    z_minus = grid_impedance(f_hz - h, grid) + converter_impedance(f_hz - h, conv)
    dx_df = (z_plus.imag - z_minus.imag) / (2.0 * h)
    slope = f_hz * dx_df
    if abs(slope) <= EPS:
        return math.nan
    z = grid_impedance(f_hz, grid) + converter_impedance(f_hz, conv)
    return z.real / slope


def scan(
    grid: GridImpedance,
    conv: ConverterImpedance,
    fmin_hz: float = 5.0,
    fmax_hz: float = 1000.0,
    points: int = 4000,
) -> list[dict[str, float]]:
    if points < 2:
        raise ValueError("points must be at least 2")
    step = (fmax_hz - fmin_hz) / (points - 1)
    return [impedance_at(fmin_hz + i * step, grid, conv) for i in range(points)]


def find_resonances(
    grid: GridImpedance,
    conv: ConverterImpedance,
    fmin_hz: float = 5.0,
    fmax_hz: float = 1000.0,
    points: int = 40000,
) -> list[dict[str, float]]:
    samples = scan(grid, conv, fmin_hz, fmax_hz, points)
    result: list[dict[str, float]] = []
    for left, right in zip(samples, samples[1:]):
        x1, x2 = left["x_pu"], right["x_pu"]
        if x1 == 0.0:
            result.append(left)
            continue
        if x1 * x2 < 0.0:
            weight = abs(x1) / (abs(x1) + abs(x2))
            f = left["frequency_hz"] + weight * (
                right["frequency_hz"] - left["frequency_hz"]
            )
            result.append(impedance_at(f, grid, conv))
    return result


def negative_bands(
    grid: GridImpedance,
    conv: ConverterImpedance,
    fmin_hz: float = 5.0,
    fmax_hz: float = 1000.0,
    points: int = 20000,
) -> list[dict[str, float]]:
    samples = scan(grid, conv, fmin_hz, fmax_hz, points)
    bands: list[dict[str, float]] = []
    start = math.nan
    for left, right in zip(samples, samples[1:]):
        if left["r_pu"] < 0.0 <= right["r_pu"]:
            weight = abs(left["r_pu"]) / (abs(left["r_pu"]) + abs(right["r_pu"]))
            end = left["frequency_hz"] + weight * (
                right["frequency_hz"] - left["frequency_hz"]
            )
            if not math.isnan(start):
                bands.append(
                    {"start_hz": start, "end_hz": end, "width_hz": end - start}
                )
            start = math.nan
        elif left["r_pu"] >= 0.0 > right["r_pu"]:
            weight = left["r_pu"] / (left["r_pu"] + abs(right["r_pu"]))
            start = left["frequency_hz"] + weight * (
                right["frequency_hz"] - left["frequency_hz"]
            )
    if not math.isnan(start):
        bands.append(
            {"start_hz": start, "end_hz": fmax_hz, "width_hz": fmax_hz - start}
        )
    return bands


def required_virtual_r(
    grid: GridImpedance,
    conv: ConverterImpedance,
    target_hz: float,
    target_r_pu: float = DEFAULT_TARGET_R,
) -> float:
    base = replace(conv, virtual_r_pu=0.0)
    return target_r_pu - impedance_at(target_hz, grid, base)["r_pu"]


def pll_sweep(
    grid: GridImpedance,
    conv: ConverterImpedance,
    target_hz: float,
    target_r_pu: float = DEFAULT_TARGET_R,
    bandwidths: tuple[float, ...] = (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0),
) -> list[dict[str, float | bool]]:
    rows: list[dict[str, float | bool]] = []
    for bandwidth in bandwidths:
        negative = conv.negative_r_pu * bandwidth / conv.bandwidth_hz
        candidate = replace(
            conv, bandwidth_hz=bandwidth, negative_r_pu=negative, virtual_r_pu=0.0
        )
        required = required_virtual_r(grid, candidate, target_hz, target_r_pu)
        rows.append(
            {
                "bandwidth_hz": bandwidth,
                "negative_r_pu": negative,
                "required_virtual_r_pu": required,
                "allowed": required >= 0.0,
            }
        )
    return rows


def tune_virtual_resistance(
    grid: GridImpedance,
    conv: ConverterImpedance,
    target_hz: float,
    target_r_pu: float = DEFAULT_TARGET_R,
    min_bandwidth_hz: float = 30.0,
    max_virtual_r_pu: float = 0.06,
) -> dict:
    rows = pll_sweep(grid, conv, target_hz, target_r_pu)
    eligible = [
        row
        for row in rows
        if row["bandwidth_hz"] >= min_bandwidth_hz
        and row["required_virtual_r_pu"] <= max_virtual_r_pu + EPS
        and row["required_virtual_r_pu"] >= 0.0
    ]
    if not eligible:
        raise ValueError("no bandwidth satisfies the tuning constraints")
    chosen = min(eligible, key=lambda row: float(row["bandwidth_hz"]))
    virtual = math.ceil(float(chosen["required_virtual_r_pu"]) * 100.0 - 1e-9) / 100.0
    tuned = replace(
        conv,
        bandwidth_hz=float(chosen["bandwidth_hz"]),
        negative_r_pu=float(chosen["negative_r_pu"]),
        virtual_r_pu=virtual,
    )
    return {
        "target_hz": target_hz,
        "target_r_pu": target_r_pu,
        "min_bandwidth_hz": min_bandwidth_hz,
        "max_virtual_r_pu": max_virtual_r_pu,
        "chosen_bandwidth_hz": float(chosen["bandwidth_hz"]),
        "chosen_negative_r_pu": float(chosen["negative_r_pu"]),
        "required_virtual_r_pu": float(chosen["required_virtual_r_pu"]),
        "virtual_r_pu": virtual,
        "converter": tuned,
    }


def demo() -> dict:
    grid = GridImpedance()
    conv = ConverterImpedance()
    resonances = find_resonances(grid, conv)
    if not resonances:
        raise ValueError("demo case has no resonance")
    resonance = resonances[0]
    target_hz = resonance["frequency_hz"]
    base = impedance_at(target_hz, grid, conv)
    base_bands = negative_bands(grid, conv)
    required = required_virtual_r(grid, conv, target_hz)
    sweep = pll_sweep(grid, conv, target_hz)
    tuned_info = tune_virtual_resistance(grid, conv, target_hz)
    tuned_conv = tuned_info["converter"]
    tuned = impedance_at(target_hz, grid, tuned_conv)
    tuned_bands = negative_bands(grid, tuned_conv)
    return {
        "grid": {
            "r_pu": grid.r_pu,
            "x50_pu": grid.x50_pu,
            "xc50_pu": grid.xc50_pu,
            "series_resonance_hz": grid.f0 * math.sqrt(grid.xc50_pu / grid.x50_pu),
        },
        "converter": {
            "x50_pu": conv.x50_pu,
            "negative_r_pu": conv.negative_r_pu,
            "center_hz": conv.center_hz,
            "bandwidth_hz": conv.bandwidth_hz,
            "virtual_r_pu": conv.virtual_r_pu,
        },
        "resonances_hz": [row["frequency_hz"] for row in resonances],
        "base": base,
        "base_negative_bands": base_bands,
        "base_required_virtual_r_pu": required,
        "pll_sweep": sweep,
        "tuned": tuned,
        "tuned_negative_bands": tuned_bands,
        "tuning": {
            key: value for key, value in tuned_info.items() if key != "converter"
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    result = demo()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    grid = result["grid"]
    base = result["base"]
    tuned = result["tuned"]
    tuning = result["tuning"]
    print("Impedance-scan demo (synthetic, D-level)")
    print(f"  grid series resonance  {grid['series_resonance_hz']:.2f} Hz")
    print(f"  converter resonance    {base['frequency_hz']:.2f} Hz")
    print(f"  base R / X             {base['r_pu']:+.5f} / {base['x_pu']:+.5f} pu")
    print(f"  base damping ratio     {base['zeta']:+.5f}")
    for band in result["base_negative_bands"]:
        print(f"  negative band          {band['start_hz']:.1f}-{band['end_hz']:.1f} Hz")
    print(f"  required virtual R     {result['base_required_virtual_r_pu']:.5f} pu")
    print(f"  chosen PLL bandwidth   {tuning['chosen_bandwidth_hz']:.0f} Hz")
    print(f"  chosen virtual R       {tuning['virtual_r_pu']:.2f} pu")
    print(f"  tuned R / damping      {tuned['r_pu']:+.5f} pu / {tuned['zeta']:+.5f}")
    print(f"  tuned negative bands   {len(result['tuned_negative_bands'])}")
    for row in result["pll_sweep"]:
        print(
            f"    bw {row['bandwidth_hz']:>4.0f} Hz  r_neg {row['negative_r_pu']:.2f}"
            f"  required Rv {row['required_virtual_r_pu']:.2f}"
        )


if __name__ == "__main__":
    main()