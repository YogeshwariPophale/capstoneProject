"""Evaluate every eligible July-August holdout window and summarize forecast errors."""
from __future__ import annotations

import csv
import heapq
import json
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/d12_i5_2026-01_to_2026-09"
INVENTORY = ROOT / "reports/eda/overview/station_inventory_validation.csv"
MODEL_PATH = ROOT / "reports/models/i5_d12_mainline_speed_15m.joblib"
OUT = ROOT / "reports/models"
MONTHS = ("2026-07", "2026-08")
QUALITY_MIN = 90.0
CHUNK_SIZE = 500_000
TOP_N = 100
USECOLS = ["timestamp", "station_id", "direction", "lane_type", "percent_observed",
           "total_flow", "avg_occupancy", "avg_speed"]
DTYPES = {"timestamp": str, "station_id": str, "direction": str, "lane_type": str,
          "percent_observed": "float32", "total_flow": "float32",
          "avg_occupancy": "float32", "avg_speed": "float32"}


def station_metadata():
    out = {}
    with INVENTORY.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["station_type"] == "Mainline" and row["validation"] == "match":
                out[row["station_id"]] = row
    return out


def add_aggregate(store, dimension, groups, y, pred, persistence):
    frame = pd.DataFrame({
        "group": groups.astype(str),
        "actual": y.astype(np.float64),
        "model_abs": np.abs(pred.astype(np.float64) - y),
        "model_sq": (pred.astype(np.float64) - y) ** 2,
        "baseline_abs": np.abs(persistence.astype(np.float64) - y),
        "baseline_sq": (persistence.astype(np.float64) - y) ** 2,
        "actual_sq": y.astype(np.float64) ** 2,
    })
    grouped = frame.groupby("group", observed=True).agg(
        rows=("actual", "size"),
        model_abs=("model_abs", "sum"),
        model_sq=("model_sq", "sum"),
        baseline_abs=("baseline_abs", "sum"),
        baseline_sq=("baseline_sq", "sum"),
        actual=("actual", "sum"),
        actual_sq=("actual_sq", "sum"),
    )
    for label, row in grouped.iterrows():
        acc = store[(dimension, label)]
        for i, key in enumerate(("rows", "model_abs", "model_sq", "baseline_abs", "baseline_sq", "actual", "actual_sq")):
            acc[i] += float(row[key])


def metric_rows(aggregates):
    result = []
    for (dimension, group), a in sorted(aggregates.items()):
        n, mae_sum, sq_sum, base_mae_sum, base_sq_sum, sy, sy2 = a
        if n <= 0:
            continue
        sst = sy2 - (sy * sy / n)
        model_mae = mae_sum / n
        base_mae = base_mae_sum / n
        result.append({
            "dimension": dimension,
            "group": group,
            "rows": int(n),
            "model_mae_mph": model_mae,
            "model_rmse_mph": (sq_sum / n) ** 0.5,
            "model_r2": 1.0 - sq_sum / sst if sst > 0 else float("nan"),
            "persistence_mae_mph": base_mae,
            "persistence_rmse_mph": (base_sq_sum / n) ** 0.5,
            "mae_improvement_pct": (base_mae - model_mae) / base_mae * 100.0 if base_mae else float("nan"),
        })
    return result


def main():
    metadata = station_metadata()
    mainline_ids = set(metadata)
    postmiles = {sid: float(row["postmile_absolute"]) for sid, row in metadata.items()}
    model_bundle = joblib.load(MODEL_PATH)
    model = model_bundle["model"]
    feature_names = model_bundle["features"]
    aggregates = defaultdict(lambda: [0.0] * 7)
    worst = []
    worst_seq = 0
    eligible_total = 0
    monthly_counts = defaultdict(int)

    for month in MONTHS:
        path = DATA / f"i5_d12_station_5min_{month}.csv.gz"
        carry = None
        month_eligible = 0
        for chunk in pd.read_csv(path, usecols=USECOLS, dtype=DTYPES,
                                 chunksize=CHUNK_SIZE, compression="gzip", low_memory=False):
            selected = chunk.loc[chunk["station_id"].isin(mainline_ids)
                                 & chunk["lane_type"].eq("ML")].copy()
            if selected.empty:
                continue
            selected["timestamp"] = pd.to_datetime(
                selected["timestamp"], format="%m/%d/%Y %H:%M:%S", errors="coerce"
            )
            selected = selected.loc[selected["timestamp"].notna()]
            if selected.empty:
                continue
            combined = pd.concat(([carry] if carry is not None else []) + [selected], ignore_index=True)
            groups = combined.groupby("station_id", sort=False, observed=True)
            lagged = {f"{col}_{lag}": groups[col].shift(lag)
                      for col in ("timestamp", "percent_observed", "total_flow", "avg_occupancy", "avg_speed")
                      for lag in range(1, 7)}
            continuous = pd.Series(True, index=combined.index)
            for lag in range(1, 7):
                continuous &= (combined["timestamp"] - lagged[f"timestamp_{lag}"]).eq(pd.Timedelta(minutes=5 * lag))
            origin = lagged["timestamp_3"]
            target_time = combined["timestamp"]
            eligible = continuous & origin.ge(pd.Timestamp("2026-07-01")) & target_time.lt(pd.Timestamp("2026-09-01"))
            eligible &= target_time.ge(pd.Timestamp("2026-07-01"))
            for lag in (3, 4, 5, 6):
                eligible &= lagged[f"percent_observed_{lag}"].ge(QUALITY_MIN)
                eligible &= lagged[f"avg_speed_{lag}"].notna()
            eligible &= combined["percent_observed"].ge(QUALITY_MIN) & combined["avg_speed"].notna()
            eligible &= lagged["total_flow_3"].notna() & lagged["total_flow_4"].notna()
            eligible &= lagged["avg_occupancy_3"].notna() & lagged["avg_occupancy_4"].notna()

            hour = origin.dt.hour + origin.dt.minute / 60.0
            dow = origin.dt.weekday
            month_angle = 2.0 * np.pi * (origin.dt.month - 1) / 12.0
            features = pd.DataFrame({
                "speed_now_mph": lagged["avg_speed_3"],
                "speed_lag_5m_mph": lagged["avg_speed_4"],
                "speed_lag_10m_mph": lagged["avg_speed_5"],
                "speed_lag_15m_mph": lagged["avg_speed_6"],
                "flow_now_5m": lagged["total_flow_3"],
                "flow_lag_5m": lagged["total_flow_4"],
                "occupancy_now": lagged["avg_occupancy_3"],
                "occupancy_lag_5m": lagged["avg_occupancy_4"],
                "absolute_postmile": combined["station_id"].map(postmiles),
                "is_southbound": combined["direction"].eq("S").astype("float32"),
                "hour_sin": np.sin(2.0 * np.pi * hour / 24.0),
                "hour_cos": np.cos(2.0 * np.pi * hour / 24.0),
                "weekday_sin": np.sin(2.0 * np.pi * dow / 7.0),
                "weekday_cos": np.cos(2.0 * np.pi * dow / 7.0),
                "is_weekend": dow.ge(5).astype("float32"),
                "month_sin": np.sin(month_angle),
                "month_cos": np.cos(month_angle),
            }, index=combined.index)[feature_names]
            eligible &= np.isfinite(features.to_numpy(dtype=np.float32)).all(axis=1)
            if eligible.any():
                rows = np.flatnonzero(eligible.to_numpy())
                x = features.iloc[rows].to_numpy(dtype=np.float32)
                y = combined.loc[rows, "avg_speed"].to_numpy(dtype=np.float32)
                persistence = lagged["avg_speed_3"].iloc[rows].to_numpy(dtype=np.float32)
                pred = model.predict(x).astype(np.float32)
                origin_values = origin.iloc[rows]
                station_ids = combined.loc[rows, "station_id"].to_numpy()
                directions = combined.loc[rows, "direction"].to_numpy()
                actual_bins = pd.cut(y, [-np.inf, 30, 50, 65, np.inf],
                                     labels=["<30", "30-50", "50-65", ">=65"], right=False).astype(str)
                transition = pd.cut(np.abs(y - persistence), [-np.inf, 5, 15, np.inf],
                                    labels=["<=5", "5-15", ">15"], right=True).astype(str)
                keysets = {
                    "direction": directions,
                    "month": origin_values.dt.strftime("%Y-%m").to_numpy(),
                    "hour": origin_values.dt.strftime("%H").to_numpy(),
                    "day_type": np.where(origin_values.dt.weekday.to_numpy() >= 5, "weekend", "weekday"),
                    "target_speed_band": actual_bins,
                    "speed_change_from_current": transition,
                    "station": np.char.add(np.char.add(station_ids.astype(str), "_"), directions.astype(str)),
                    "overall": np.full(len(rows), "all", dtype=object),
                }
                for dimension, keys in keysets.items():
                    add_aggregate(aggregates, dimension, np.asarray(keys), y, pred, persistence)
                month_eligible += len(rows)
                errors = np.abs(pred.astype(np.float64) - y.astype(np.float64))
                for local in np.argpartition(errors, -min(TOP_N, len(errors)))[-min(TOP_N, len(errors)):]:
                    worst_seq += 1
                    origin_dt = origin_values.iloc[local]
                    sid = station_ids[local]
                    info = metadata[sid]
                    record = {
                        "forecast_origin": origin_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "target_time": (origin_dt + pd.Timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),
                        "station_id": sid,
                        "direction": directions[local],
                        "station_name": info.get("station_name", ""),
                        "city": info.get("city", ""),
                        "postmile_ca": info.get("postmile_ca", ""),
                        "actual_speed_t_plus_15_mph": float(y[local]),
                        "persistence_prediction_mph": float(persistence[local]),
                        "model_prediction_mph": float(pred[local]),
                        "absolute_error_mph": float(errors[local]),
                        "signed_error_mph": float(pred[local] - y[local]),
                        "hour": int(origin_dt.hour),
                        "target_speed_band": str(actual_bins[local]),
                    }
                    item = (record["absolute_error_mph"], worst_seq, record)
                    if len(worst) < TOP_N:
                        heapq.heappush(worst, item)
                    elif item[0] > worst[0][0]:
                        heapq.heapreplace(worst, item)
            carry = combined.groupby("station_id", sort=False, group_keys=False, observed=True).tail(6).copy()
        monthly_counts[month] = month_eligible
        eligible_total += month_eligible
        print(f"Evaluated {month}: {month_eligible:,} eligible holdout rows")

    output_rows = metric_rows(aggregates)
    with (OUT / "i5_d12_forecast_error_subgroups.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    worst_rows = [item[2] for item in sorted(worst, reverse=True)]
    with (OUT / "i5_d12_forecast_largest_errors.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(worst_rows[0]))
        writer.writeheader()
        writer.writerows(worst_rows)
    summary = {
        "test_period": "July-August 2026",
        "eligible_rows_evaluated": eligible_total,
        "rows_by_month": dict(monthly_counts),
        "quality_rule": ">=90% observed for input speed rows and target; exact five-minute intervals",
        "subgroup_metrics": "i5_d12_forecast_error_subgroups.csv",
        "largest_errors": "i5_d12_forecast_largest_errors.csv",
        "overall_metrics": [r for r in output_rows if r["dimension"] == "overall"],
        "interpretation": "Continuous speed forecast errors; target-speed bands are descriptive error strata, not congestion labels.",
    }
    with (OUT / "i5_d12_forecast_error_review.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary["overall_metrics"], indent=2))


if __name__ == "__main__":
    main()
