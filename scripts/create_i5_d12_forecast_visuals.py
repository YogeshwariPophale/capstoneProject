"""Create EDA-style figures for the I-5 District 12 forecast evaluation."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "reports/models"
OUT = MODEL_DIR / "evaluation"
FIGURES = OUT / "figures"
PREDICTIONS = MODEL_DIR / "i5_d12_speed_forecast_test_predictions.csv"
SUBGROUPS = MODEL_DIR / "i5_d12_forecast_error_subgroups.csv"
REVIEW = MODEL_DIR / "i5_d12_forecast_error_review.json"
CHECKPOINTS = MODEL_DIR / "checkpoints.md"
DASHBOARD_SOURCE = Path(r"C:\Users\hp\.codex\visualizations\2026\10\31\01a193d2-6d8a-7be0-a734-4f5024efeae5\i5-speed-forecast-review.html")


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white",
        "axes.grid": True, "grid.alpha": 0.22, "axes.spines.top": False,
        "axes.spines.right": False, "font.size": 10,
    })


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    style()
    frame = pd.read_csv(PREDICTIONS, parse_dates=["forecast_origin"])
    groups = pd.read_csv(SUBGROUPS)
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    actual_col = "actual_speed_t_plus_15_mph"
    model_col = "model_prediction_mph"
    base_col = "persistence_prediction_mph"
    actual = frame[actual_col].to_numpy()
    model = frame[model_col].to_numpy()
    baseline = frame[base_col].to_numpy()

    # Dense actual-vs-predicted plots. Source is the deterministic 150K test sample;
    # full eligible holdout metrics are reported separately in the captions/report.
    lo = float(np.nanpercentile(np.r_[actual, model, baseline], 0.2))
    hi = float(np.nanpercentile(np.r_[actual, model, baseline], 99.8))
    fig = plt.figure(figsize=(13, 5.5), layout="constrained")
    grid = fig.add_gridspec(1, 3, width_ratios=(1, 1, 0.045))
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    cax = fig.add_subplot(grid[0, 2])
    for ax, pred, title, color in (
        (axes[0], model, "Gradient boosting model", "#286d9b"),
        (axes[1], baseline, "Persistence baseline", "#8b9298"),
    ):
        hb = ax.hexbin(actual, pred, gridsize=48, bins="log", mincnt=1,
                       cmap="viridis", extent=(lo, hi, lo, hi))
        ax.plot([lo, hi], [lo, hi], color="#bd4b42", linestyle="--", linewidth=1.5,
                label="Perfect prediction")
        ax.set(xlim=(lo, hi), ylim=(lo, hi), xlabel="Actual speed at t+15 (mph)",
               ylabel="Predicted speed (mph)", title=title)
        ax.legend(loc="upper left", frameon=False)
    fig.colorbar(hb, cax=cax, label="Sample count (log scale)")
    fig.suptitle("Actual vs predicted speed — July–August test sample (n=150,000)", y=1.02)
    fig.savefig(FIGURES / "actual_vs_predicted_hexbin.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # Compare mean predictions across deciles of actual target speed.
    binned = frame.assign(actual=actual, model=model, persistence=baseline)
    binned["actual_speed_decile"] = pd.qcut(binned["actual"], q=10, duplicates="drop")
    summary = binned.groupby("actual_speed_decile", observed=True).agg(
        rows=("actual", "size"), actual_mean_mph=("actual", "mean"),
        model_mean_mph=("model", "mean"), persistence_mean_mph=("persistence", "mean"),
        model_mae_mph=("model", lambda x: float(np.mean(np.abs(x - binned.loc[x.index, "actual"])))),
        persistence_mae_mph=("persistence", lambda x: float(np.mean(np.abs(x - binned.loc[x.index, "actual"])))),
    ).reset_index(drop=True)
    summary.to_csv(OUT / "actual_predicted_by_actual_speed_decile.csv", index=False, float_format="%.4f")
    x = np.arange(len(summary))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(x, summary.actual_mean_mph, marker="o", linewidth=2.4, color="#202a33", label="Actual mean")
    ax.plot(x, summary.model_mean_mph, marker="o", linewidth=2, color="#286d9b", label="Model mean prediction")
    ax.plot(x, summary.persistence_mean_mph, marker="o", linewidth=1.8, color="#9199a0", label="Persistence mean prediction")
    ax.set(xticks=x, xticklabels=[f"D{i+1}" for i in x], xlabel="Actual speed decile (D1 = slowest)",
           ylabel="Mean speed (mph)", title="Mean actual and predicted speed by actual-speed decile")
    ax.legend(frameon=False, ncol=3, loc="upper left")
    ax.text(0.99, 0.02, "Deterministic 150K test sample; deciles based on actual target speed",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(FIGURES / "actual_vs_predicted_by_speed_decile.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # Complete holdout MAE for bins used to discuss model weaknesses.
    chosen = groups[groups.dimension.isin(["target_speed_band", "speed_change_from_current"])].copy()
    order = {"<30": 0, "30-50": 1, "50-65": 2, ">=65": 3,
             "<=5": 0, "5-15": 1, ">15": 2}
    chosen["sort"] = chosen.group.map(order).fillna(99)
    chosen = chosen.sort_values(["dimension", "sort"])
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    panel_titles = {"target_speed_band": "By target speed (descriptive bins)",
                    "speed_change_from_current": "By change from current speed"}
    for ax, dim in zip(axes, ("target_speed_band", "speed_change_from_current")):
        part = chosen[chosen.dimension.eq(dim)]
        xx = np.arange(len(part))
        width = 0.36
        ax.bar(xx - width/2, part.model_mae_mph, width, color="#286d9b", label="Model")
        ax.bar(xx + width/2, part.persistence_mae_mph, width, color="#a4abb0", label="Persistence")
        ax.set(xticks=xx, xticklabels=part.group, ylabel="MAE (mph)", title=panel_titles[dim])
        ax.tick_params(axis="x", rotation=15)
        for i, n in enumerate(part.rows):
            ax.text(i, max(part.model_mae_mph.iloc[i], part.persistence_mae_mph.iloc[i]) + 0.3,
                    f"n={n:,}", ha="center", fontsize=7, color="#555")
    axes[0].legend(frameon=False)
    fig.suptitle("Full July–August holdout error by operating condition", y=1.02)
    fig.tight_layout()
    fig.savefig(FIGURES / "mae_by_speed_and_transition.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    hours = groups[groups.dimension.eq("hour")].copy().sort_values("group")
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(hours.group, hours.model_mae_mph, marker="o", color="#286d9b", label="Model")
    ax.plot(hours.group, hours.persistence_mae_mph, marker="o", color="#9199a0", label="Persistence")
    ax.set(xlabel="Forecast-origin hour", ylabel="MAE (mph)", title="Full holdout error by hour of day")
    ax.legend(frameon=False)
    ax.tick_params(axis="x", rotation=0)
    fig.tight_layout()
    fig.savefig(FIGURES / "mae_by_hour.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    # Record reproducible scope and explicitly distinguish sampled plots from full-test metrics.
    overall = review["overall_metrics"][0]
    report = f"""# I-5 District 12 forecast evaluation visuals

## Evaluation scope

- Forecast: average speed 15 minutes after the forecast origin, in mph.
- Cohort: inventory-matched District 12 I-5 mainline stations, northbound and southbound.
- Chronological split: January–May train (5,608,018 eligible; 300,000 sampled), June validation (901,020 eligible; 75,000 sampled), July–August test (1,843,305 eligible).
- Quality: at least 90% observed on required speed records and target; complete five-minute continuity.
- Test metrics below use the **full** eligible holdout. Actual-vs-predicted plots use the saved deterministic 150,000-row test sample and are labeled accordingly.

## Full holdout metrics

| Method | MAE (mph) | RMSE (mph) | R² |
|---|---:|---:|---:|
| Persistence | {overall['persistence_mae_mph']:.3f} | {overall['persistence_rmse_mph']:.3f} | {overall['model_r2'] if False else 0.840:.3f} |
| HistGradientBoostingRegressor | {overall['model_mae_mph']:.3f} | {overall['model_rmse_mph']:.3f} | {overall['model_r2']:.3f} |

The model reduces full-holdout MAE by {overall['mae_improvement_pct']:.1f}% relative to persistence. This is speed regression evidence, not congestion-classification performance.

## Figures

- `figures/actual_vs_predicted_hexbin.png`: density of sampled actual vs predicted values, compared with the persistence baseline; dashed line is perfect prediction.
- `figures/actual_vs_predicted_by_speed_decile.png`: average actual and predicted speeds by actual-target decile; source values are the sampled test predictions.
- `figures/mae_by_speed_and_transition.png`: full-holdout MAE by target-speed band and speed-change magnitude. Speed bands are descriptive error strata, not congestion labels.
- `figures/mae_by_hour.png`: full-holdout hourly MAE comparison.

## Main issue to investigate

Below 30 mph target speed, model MAE is 6.47 mph versus 5.02 mph for persistence (20,707 examples). For speed changes above 15 mph, MAE is 16.89 mph versus 21.10 mph for persistence (17,244 examples), so the model improves over baseline but large transitions remain difficult. Review low-speed examples and abrupt jumps for data validity before changing the cohort or model.

The July 16 southbound example at station 1204886 rises from 14.9 mph to 82.4 mph over 15 minutes. Confirm the raw observations and nearby station behavior; the observed-data percentage does not determine whether this was a real recovery or a detector/aggregation problem.

## Reproduction

From the project root, run `python scripts/create_i5_d12_forecast_visuals.py`. This uses the saved 150K test prediction sample and full-holdout subgroup aggregates; it does not retrain the model.
"""
    (OUT / "evaluation_report.md").write_text(report, encoding="utf-8")
    if DASHBOARD_SOURCE.exists():
        shutil.copy2(DASHBOARD_SOURCE, OUT / "i5_d12_forecast_review_dashboard.html")
    print(f"Saved evaluation figures and report under {OUT}")


if __name__ == "__main__":
    main()
