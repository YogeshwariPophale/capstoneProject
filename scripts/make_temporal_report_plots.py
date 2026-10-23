#!/usr/bin/env python3
"""Build multi-month hour-of-week and daywise report figures from PeMS CSV.GZ files.

All lane/station types are included to match the project's current EDA scope.
The plots use records with percent_observed >= 90 as a provisional quality
sensitivity filter; this is not a finalized modeling policy.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "d12_i5_2026-01_to_2026-09"
OUT = ROOT / "reports" / "eda" / "report_figures"
OUT.mkdir(parents=True, exist_ok=True)
MONTHS = [f"2026-{m:02d}" for m in range(1, 10)]
COLS = ["timestamp", "direction", "lane_type", "percent_observed", "total_flow", "avg_occupancy", "avg_speed"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.titlesize": 12, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.dpi": 300})


def main() -> None:
    rollup_path = OUT / "temporal_rollup_quality_ge90.csv"
    if rollup_path.exists():
        agg = pd.read_csv(rollup_path, parse_dates=["date"])
    else:
        # Aggregate each source chunk immediately to keep memory use bounded.
        parts: list[pd.DataFrame] = []
        for month in MONTHS:
            path = DATA / f"i5_d12_station_5min_{month}.csv.gz"
            if not path.exists():
                continue
            print(f"Scanning {path.name}", flush=True)
            for chunk in pd.read_csv(path, usecols=COLS, chunksize=400_000):
                chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], errors="coerce")
                chunk = chunk.dropna(subset=["timestamp"])
                chunk["month"] = chunk["timestamp"].dt.strftime("%Y-%m")
                chunk["date"] = chunk["timestamp"].dt.floor("D")
                chunk["hour"] = chunk["timestamp"].dt.hour
                chunk["weekday"] = chunk["timestamp"].dt.dayofweek
                q = chunk.loc[chunk["percent_observed"] >= 90]
                if not q.empty:
                    grouped = q.groupby(["month", "date", "hour", "weekday", "direction"], observed=True).agg(
                        speed_sum=("avg_speed", "sum"), speed_n=("avg_speed", "count"),
                        flow_sum=("total_flow", "sum"), flow_n=("total_flow", "count"),
                        occ_sum=("avg_occupancy", "sum"), occ_n=("avg_occupancy", "count"),
                    ).reset_index()
                    parts.append(grouped)
        if not parts:
            raise SystemExit("No records passed the provisional quality filter.")
        agg = pd.concat(parts, ignore_index=True).groupby(
            ["month", "date", "hour", "weekday", "direction"], as_index=False, observed=True
        ).sum(numeric_only=True)
        for metric in ("speed", "flow", "occ"):
            agg[metric] = agg[f"{metric}_sum"] / agg[f"{metric}_n"].replace(0, np.nan)
        agg.to_csv(rollup_path, index=False)
    # Keep groups with valid speed data for all speed-profile calculations.
    agg = agg[agg["speed_n"] > 0].copy()

    # Figure A: all-month, hourly speed profiles (one panel per month).
    fig, axes = plt.subplots(3, 3, figsize=(12, 9), sharex=True, sharey=True)
    colors = {"N": "#1769aa", "S": "#e67e22"}
    for ax, month in zip(axes.flat, MONTHS):
        sub = agg[agg["month"] == month]
        for direction in ("N", "S"):
            d = sub[sub["direction"] == direction].groupby("hour").apply(
                lambda x: np.average(x["speed"], weights=x["speed_n"]), include_groups=False
            )
            ax.plot(d.index, d.values, marker="o", ms=2.5, lw=1.5, color=colors[direction],
                    label="Northbound" if direction == "N" else "Southbound")
        ax.set_title(month)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.grid(axis="y", alpha=.22)
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.supxlabel("Hour of day")
    fig.supylabel("Mean speed (mph), records with % observed ≥ 90")
    fig.suptitle("Hourly speed profiles across all available months", y=1.01, fontsize=15)
    fig.text(.5, .005, "All lane/station types included. Missing days remain missing; September has low completeness.",
             ha="center", fontsize=8, color="#555")
    fig.tight_layout(rect=(.02, .025, 1, .98))
    fig.savefig(OUT / "05_all_months_hourly_speed_profiles.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Figure B: typical Monday by hour for each month, split by direction.
    monday = agg[agg["weekday"] == 0]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    palette = sns.color_palette("viridis", len(MONTHS))
    for ax, direction, title in zip(axes, ("N", "S"), ("Northbound", "Southbound")):
        subdir = monday[monday["direction"] == direction]
        for color, month in zip(palette, MONTHS):
            sub = subdir[subdir["month"] == month]
            d = sub.groupby("hour").apply(
                lambda x: np.average(x["speed"], weights=x["speed_n"]), include_groups=False
            )
            if not d.empty:
                ax.plot(d.index, d.values, marker="o", ms=3, lw=1.7, color=color, label=month[-2:])
        ax.set_title(title)
        ax.set_xlabel("Hour of day")
        ax.set_xticks(range(0, 24, 3))
        ax.grid(axis="y", alpha=.25)
        ax.legend(title="Month", ncol=3, frameon=False, fontsize=8)
    axes[0].set_ylabel("Mean speed (mph), records with % observed ≥ 90")
    fig.suptitle("Typical Monday by hour: monthly comparison", fontsize=15)
    fig.text(.5, .005, "Each curve averages available Mondays within that month, across all lane/station types.",
             ha="center", fontsize=8, color="#555")
    fig.tight_layout(rect=(0, .03, 1, .93))
    fig.savefig(OUT / "06_monday_hourly_speed_by_month.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Figure C: daywise hour-by-hour speed heatmap for the complete study window.
    daily = agg.groupby(["date", "hour"]).apply(
        lambda x: np.average(x["speed"], weights=x["speed_n"]), include_groups=False
    ).rename("speed").reset_index()
    wide = daily.pivot(index="hour", columns="date", values="speed")
    full_dates = pd.date_range("2026-01-01", "2026-09-30", freq="D")
    wide = wide.reindex(index=range(24), columns=full_dates)
    fig, ax = plt.subplots(figsize=(15, 6))
    sns.heatmap(wide, ax=ax, cmap="RdYlGn", vmin=45, vmax=70, mask=wide.isna(),
                cbar_kws={"label": "Mean speed (mph), % observed ≥ 90"},
                xticklabels=False, yticklabels=2, linewidths=0)
    ax.set_ylabel("Hour of day")
    ax.set_xlabel("")
    ax.set_title("Daywise hourly speed across the study window")
    for date in pd.date_range("2026-01-01", "2026-09-01", freq="MS"):
        idx = (date - full_dates[0]).days
        ax.axvline(idx, color="black", linewidth=.55, alpha=.8)
        ax.text(idx + 1, -0.6, date.strftime("%b"), ha="left", va="center", fontsize=8, clip_on=False)
    ax.invert_yaxis()
    fig.text(.5, .005, "Dates run from January through September; blank areas reflect missing or non-qualifying dates.",
             ha="center", fontsize=8, color="#555")
    fig.tight_layout(rect=(0, .025, 1, 1))
    fig.savefig(OUT / "07_daywise_hourly_speed_heatmap.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Figure D: weekday-by-hour matrix across all available records.
    wd = agg.groupby(["weekday", "hour"]).apply(
        lambda x: np.average(x["speed"], weights=x["speed_n"]), include_groups=False
    ).unstack("hour").reindex(index=range(7), columns=range(24))
    fig, ax = plt.subplots(figsize=(11, 4.3))
    sns.heatmap(wd, ax=ax, cmap="RdYlGn", vmin=45, vmax=70,
                cbar_kws={"label": "Mean speed (mph), % observed ≥ 90"},
                xticklabels=2, yticklabels=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("")
    ax.set_title("Typical speed by weekday and hour — all available months")
    fig.text(.5, .005, "Records are pooled across months and lane/station types; incomplete-date coverage can affect averages.",
             ha="center", fontsize=8, color="#555")
    fig.tight_layout(rect=(0, .025, 1, 1))
    fig.savefig(OUT / "08_weekday_hourly_speed_heatmap.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(f"Saved multi-month and daywise plots to {OUT}", flush=True)


if __name__ == "__main__":
    main()
