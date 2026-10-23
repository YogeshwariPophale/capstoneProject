"""Stream supplemental cross-month EDA from the prepared monthly CSV.GZ files.

Writes only to reports/eda/overview; prepared data is read-only.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "d12_i5_2026-01_to_2026-09"
OUT = ROOT / "reports" / "eda" / "overview"
USECOLS = ["timestamp", "station_id", "direction", "lane_type", "percent_observed",
           "total_flow", "avg_occupancy", "avg_speed"]
METRICS = ["total_flow", "avg_occupancy", "avg_speed"]
THRESHOLDS = (30, 40, 50)  # exploratory mph cutoffs; not the project label rule


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    type_totals: dict[tuple[str, str], dict[str, float]] = {}
    month_rows = []
    quality_rows = []
    threshold_rows = []
    sampled_speeds = []

    for path in sorted(DATA.glob("i5_d12_station_5min_*.csv.gz")):
        month = path.name[:-7][-7:]
        n = 0
        obs_sum = obs_low90 = 0.0
        obs_count = obs_missing = 0
        speed_count = 0
        metric_totals = {k: {"sum": 0.0, "n": 0, "sum_q90": 0.0, "n_q90": 0}
                         for k in METRICS}
        local_threshold = {t: 0 for t in THRESHOLDS}

        for chunk in pd.read_csv(path, usecols=USECOLS, compression="gzip", chunksize=300_000):
            n += len(chunk)
            obs = pd.to_numeric(chunk["percent_observed"], errors="coerce")
            ok_obs = obs.notna()
            obs_sum += obs[ok_obs].sum()
            obs_count += int(ok_obs.sum())
            obs_low90 += int((obs[ok_obs] < 90).sum())
            obs_missing += int((~ok_obs).sum())
            speed = pd.to_numeric(chunk["avg_speed"], errors="coerce")
            valid_speed = speed.notna()
            speed_count += int(valid_speed.sum())
            for t in THRESHOLDS:
                local_threshold[t] += int((speed[valid_speed] <= t).sum())
            # Deterministic thinning supplies a memory-light descriptive quantile sample.
            sampled_speeds.append(speed[valid_speed].iloc[::20].to_numpy(dtype=np.float32))

            q90 = obs.ge(90)
            for metric in METRICS:
                values = pd.to_numeric(chunk[metric], errors="coerce")
                good = values.notna()
                metric_totals[metric]["sum"] += values[good].sum()
                metric_totals[metric]["n"] += int(good.sum())
                qualified = good & q90
                metric_totals[metric]["sum_q90"] += values[qualified].sum()
                metric_totals[metric]["n_q90"] += int(qualified.sum())

            chunk["avg_speed"] = speed
            chunk["avg_occupancy"] = pd.to_numeric(chunk["avg_occupancy"], errors="coerce")
            chunk["total_flow"] = pd.to_numeric(chunk["total_flow"], errors="coerce")
            grouped = chunk.groupby(["direction", "lane_type"], dropna=False).agg(
                observations=("timestamp", "size"),
                mean_speed=("avg_speed", "mean"),
                mean_occupancy=("avg_occupancy", "mean"),
                mean_flow=("total_flow", "mean"),
            )
            for key, row in grouped.iterrows():
                acc = type_totals.setdefault(key, {"observations": 0, "speed_sum": 0.0,
                    "speed_n": 0, "occupancy_sum": 0.0, "occupancy_n": 0,
                    "flow_sum": 0.0, "flow_n": 0})
                acc["observations"] += int(row.observations)
                for field, mean_field, n_field in (
                    ("speed_sum", "mean_speed", "speed_n"),
                    ("occupancy_sum", "mean_occupancy", "occupancy_n"),
                    ("flow_sum", "mean_flow", "flow_n"),
                ):
                    if pd.notna(row[mean_field]):
                        acc[field] += float(row[mean_field]) * int(row.observations)
                        acc[n_field] += int(row.observations)

        month_rows.append({"month": month, "rows": n, "speed_observations": speed_count})
        quality_rows.append({"month": month, "rows": n, "percent_observed_missing": obs_missing,
            "percent_observed_mean": obs_sum / obs_count if obs_count else np.nan,
            "percent_observed_below_90_count": obs_low90,
            "percent_observed_below_90_percent": 100 * obs_low90 / obs_count if obs_count else np.nan,
            **{f"{m}_mean_all": metric_totals[m]["sum"] / metric_totals[m]["n"] if metric_totals[m]["n"] else np.nan
               for m in METRICS},
            **{f"{m}_mean_observed_ge_90": metric_totals[m]["sum_q90"] / metric_totals[m]["n_q90"] if metric_totals[m]["n_q90"] else np.nan
               for m in METRICS}})
        for t in THRESHOLDS:
            threshold_rows.append({"month": month, "speed_threshold_mph": t,
                "low_speed_count": local_threshold[t],
                "speed_observation_count": speed_count,
                "low_speed_percent": 100 * local_threshold[t] / speed_count if speed_count else np.nan,
                "interpretation": "exploratory sensitivity only; not a finalized congestion label"})
        print(f"Finished supplemental scan: {month} ({n:,} rows)", flush=True)

    q = pd.DataFrame(quality_rows)
    q.to_csv(OUT / "quality_filter_comparison.csv", index=False)
    pd.DataFrame(threshold_rows).to_csv(OUT / "speed_threshold_sensitivity.csv", index=False)
    type_rows = []
    for (direction, lane_type), acc in sorted(type_totals.items()):
        type_rows.append({"direction": direction, "lane_type": lane_type,
            "observations": acc["observations"],
            "mean_speed": acc["speed_sum"] / acc["speed_n"] if acc["speed_n"] else np.nan,
            "mean_occupancy": acc["occupancy_sum"] / acc["occupancy_n"] if acc["occupancy_n"] else np.nan,
            "mean_flow": acc["flow_sum"] / acc["flow_n"] if acc["flow_n"] else np.nan})
    pd.DataFrame(type_rows).to_csv(OUT / "direction_lane_type_comparison.csv", index=False)
    speeds = np.concatenate(sampled_speeds) if sampled_speeds else np.array([])
    quantiles = ([{"quantile": qv, "sampled_speed_mph": float(np.quantile(speeds, qv))}
                  for qv in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)]
                 if len(speeds) else [])
    pd.DataFrame(quantiles).to_csv(OUT / "sampled_speed_quantiles.csv", index=False)
    pd.DataFrame(month_rows).to_csv(OUT / "monthly_scan_coverage.csv", index=False)
    print(f"Supplemental tables saved to {OUT}")


if __name__ == "__main__":
    main()
