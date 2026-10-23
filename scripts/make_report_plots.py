#!/usr/bin/env python3
"""Create report-ready figures from the saved monthly EDA summary tables."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EDA = ROOT / "reports" / "eda"
OUT = EDA / "report_figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.titlesize": 14, "axes.labelsize": 11,
    "figure.dpi": 140, "savefig.dpi": 300,
    "axes.spines.top": False, "axes.spines.right": False,
})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def hourly_profiles() -> None:
    rows = []
    for p in sorted(EDA.glob("processed_2026-*/temporal_patterns.csv")):
        month = p.parent.name[-2:]
        if month == "09":
            rows = read_csv(p)
            break
    if not rows:
        return
    # Direction + hour aggregates preserve the directional commute patterns.
    rows = [r for r in rows if r["grouping"] == "direction + hour"]
    hours = np.arange(24)
    fig, axes = plt.subplots(3, 1, figsize=(9, 9), sharex=True)
    metrics = [("avg_flow", "Mean flow (vehicles / 5 min)"),
               ("avg_occupancy", "Mean occupancy"),
               ("avg_speed", "Mean speed (mph)")]
    colors = {"N": "#1769aa", "S": "#e67e22"}
    for ax, (field, label) in zip(axes, metrics):
        for direction in ("N", "S"):
            series = sorted((r for r in rows if r["group_direction"] == direction),
                             key=lambda r: int(float(r["group_hour"])))
            ax.plot(hours, [float(r[field]) for r in series], marker="o", ms=3,
                    lw=2, color=colors[direction], label=f"{direction}orthbound" if direction == "N" else "Southbound")
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=.25)
    axes[0].set_title("I-5 District 12 traffic by hour and direction — September 2026")
    axes[-1].set_xlabel("Hour of day")
    axes[-1].set_xticks(range(0, 24, 2))
    axes[0].legend(frameon=False, ncol=2, loc="upper left")
    fig.text(.01, .005, "Descriptive averages across available records; September has substantial missing data.",
             fontsize=8, color="#555")
    fig.tight_layout(rect=(0, .025, 1, 1))
    save(fig, "01_hourly_profiles_sep2026.png")


def monthly_quality() -> None:
    rows = read_csv(EDA / "overview" / "quality_filter_comparison.csv")
    months = [r["month"][-2:] for r in rows]
    low = [float(r["percent_observed_below_90_percent"]) for r in rows]
    mean = [float(r["percent_observed_mean"]) for r in rows]
    x = np.arange(len(months))
    fig, ax = plt.subplots(figsize=(9, 4.8))
    bars = ax.bar(x, low, color=["#c94c4c" if m == "09" else "#4c88a8" for m in months], alpha=.88)
    ax.set_xticks(x, [f"2026-{m}" for m in months], rotation=35, ha="right")
    ax.set_ylabel("Records below 90% observed (%)")
    ax.set_title("Data completeness varies by month")
    ax.grid(axis="y", alpha=.25)
    for b, v in zip(bars, low):
        ax.text(b.get_x()+b.get_width()/2, v+.8, f"{v:.1f}%", ha="center", va="bottom", fontsize=8)
    ax.annotate(f"September mean % observed: {mean[-1]:.1f}%", xy=(8, low[-1]), xytext=(5.7, 65),
                arrowprops={"arrowstyle": "->", "color": "#8e3030"}, color="#8e3030", fontsize=9)
    ax.set_ylim(0, max(low) * 1.25)
    fig.text(.01, .005, "Red highlights September. Review the source coverage and quality policy before modeling.",
             fontsize=8, color="#555")
    fig.tight_layout(rect=(0, .03, 1, 1))
    save(fig, "02_monthly_data_quality.png")


def threshold_sensitivity() -> None:
    rows = read_csv(EDA / "overview" / "speed_threshold_sensitivity.csv")
    months = sorted({r["month"] for r in rows})
    thresholds = sorted({int(r["speed_threshold_mph"]) for r in rows})
    fig, ax = plt.subplots(figsize=(9, 4.8))
    colors = {30: "#287a55", 40: "#e39b27", 50: "#b94b4b"}
    for t in thresholds:
        series = {r["month"]: float(r["low_speed_percent"]) for r in rows if int(r["speed_threshold_mph"]) == t}
        ax.plot(range(len(months)), [series[m] for m in months], marker="o", lw=2,
                label=f"Below {t} mph", color=colors.get(t))
    ax.set_xticks(range(len(months)), [m[-2:] for m in months])
    ax.set_xlabel("Month (2026)")
    ax.set_ylabel("Speed observations below threshold (%)")
    ax.set_title("Low-speed prevalence depends on the chosen cutoff")
    ax.grid(axis="y", alpha=.25)
    ax.legend(frameon=False, ncol=3)
    fig.text(.01, .005, "Exploratory sensitivity analysis; these cutoffs are not finalized congestion labels.",
             fontsize=8, color="#555")
    fig.tight_layout(rect=(0, .03, 1, 1))
    save(fig, "03_low_speed_threshold_sensitivity.png")


def prediction_alignment() -> None:
    rows = read_csv(EDA / "overview" / "prediction_alignment_all_months.csv")
    checks = ["history_5m", "history_10m", "history_15m", "future_15m"]
    labels = ["History 5 min", "History 10 min", "History 15 min", "Future 15 min"]
    months = sorted({r["month"] for r in rows})
    values = {c: {r["month"]: float(r["coverage_percent"]) for r in rows if r["check"] == c} for c in checks}
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for check, label in zip(checks, labels):
        ax.plot(range(len(months)), [values[check][m] for m in months], marker="o", ms=4, lw=1.8, label=label)
    ax.set_xticks(range(len(months)), [m[-2:] for m in months])
    ax.set_xlabel("Month (2026)")
    ax.set_ylabel("Exact timestamp match (%)")
    ax.set_ylim(99.75, 100.005)
    ax.set_title("Five-minute timestamp alignment is consistently high")
    ax.grid(axis="y", alpha=.25)
    ax.legend(frameon=False, ncol=2, loc="lower left")
    fig.text(.01, .005, "Timestamp-key coverage only; this is not model accuracy. Gaps are retained in the data.",
             fontsize=8, color="#555")
    fig.tight_layout(rect=(0, .03, 1, 1))
    save(fig, "04_prediction_timestamp_alignment.png")


if __name__ == "__main__":
    hourly_profiles()
    monthly_quality()
    threshold_sensitivity()
    prediction_alignment()
    print(f"Saved report figures to {OUT}")
