"""Train a first 15-minute mainline speed forecaster for District 12 I-5."""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/d12_i5_2026-01_to_2026-09"
INVENTORY = ROOT / "reports/eda/overview/station_inventory_validation.csv"
OUT = ROOT / "reports/models"
MONTHS = tuple(f"2026-{m:02d}" for m in range(1, 9))
TRAIN_END = datetime(2026, 6, 1)
VALID_END = datetime(2026, 7, 1)
TEST_END = datetime(2026, 9, 1)
QUALITY_MIN = 90.0
SEED = 42
CAPS = {"train": 300_000, "validation": 75_000, "test": 150_000}
FEATURES = [
    "speed_now_mph", "speed_lag_5m_mph", "speed_lag_10m_mph", "speed_lag_15m_mph",
    "flow_now_5m", "flow_lag_5m", "occupancy_now", "occupancy_lag_5m",
    "absolute_postmile", "is_southbound", "hour_sin", "hour_cos",
    "weekday_sin", "weekday_cos", "is_weekend", "month_sin", "month_cos",
]


class Reservoir:
    def __init__(self, cap: int, n_features: int, rng: random.Random):
        self.cap = cap
        self.rng = rng
        self.n_seen = 0
        self.n_kept = 0
        self.x = np.empty((cap, n_features), dtype=np.float32)
        self.y = np.empty(cap, dtype=np.float32)
        self.persistence = np.empty(cap, dtype=np.float32)
        self.keys = np.empty(cap, dtype=np.float64)
        self.meta = np.empty((cap, 3), dtype=object)

    def add_batch(self, features: np.ndarray, target: np.ndarray, persistence: np.ndarray,
                  metadata: np.ndarray) -> None:
        n = len(target)
        if n == 0:
            return
        self.n_seen += n
        keys = np.asarray([self.rng.random() for _ in range(n)], dtype=np.float64)
        if n > self.cap:
            selected = np.argpartition(keys, -self.cap)[-self.cap:]
            keys, features, target, persistence, metadata = (
                keys[selected], features[selected], target[selected], persistence[selected], metadata[selected]
            )
        combined_keys = np.concatenate((self.keys[:self.n_kept], keys))
        combined_x = np.concatenate((self.x[:self.n_kept], features), axis=0)
        combined_y = np.concatenate((self.y[:self.n_kept], target))
        combined_p = np.concatenate((self.persistence[:self.n_kept], persistence))
        combined_meta = np.concatenate((self.meta[:self.n_kept], metadata), axis=0)
        keep = min(self.cap, len(combined_keys))
        chosen = np.argpartition(combined_keys, -keep)[-keep:]
        self.n_kept = keep
        self.keys[:keep] = combined_keys[chosen]
        self.x[:keep] = combined_x[chosen]
        self.y[:keep] = combined_y[chosen]
        self.persistence[:keep] = combined_p[chosen]
        self.meta[:keep] = combined_meta[chosen]

    def arrays(self):
        return (self.x[:self.n_kept], self.y[:self.n_kept],
                self.persistence[:self.n_kept], self.meta[:self.n_kept])


def load_mainline_metadata() -> dict[str, dict[str, str]]:
    metadata = {}
    with INVENTORY.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["station_type"] == "Mainline" and row["validation"] == "match":
                metadata[row["station_id"]] = row
    if not metadata:
        raise RuntimeError("No matched Mainline station metadata found.")
    return metadata


def metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae_mph": float(mean_absolute_error(y, prediction)),
        "rmse_mph": float(math.sqrt(mean_squared_error(y, prediction))),
        "r2": float(r2_score(y, prediction)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    station_meta = load_mainline_metadata()
    mainline_ids = set(station_meta)
    postmiles = {sid: float(row["postmile_absolute"]) for sid, row in station_meta.items()}
    rng = random.Random(SEED)
    reservoirs = {name: Reservoir(cap, len(FEATURES), rng) for name, cap in CAPS.items()}
    monthly_rows = {}
    usecols = ["timestamp", "station_id", "direction", "lane_type", "percent_observed",
               "total_flow", "avg_occupancy", "avg_speed"]
    dtypes = {"timestamp": str, "station_id": str, "direction": str, "lane_type": str,
              "percent_observed": "float32", "total_flow": "float32",
              "avg_occupancy": "float32", "avg_speed": "float32"}
    shift_delta = pd.Timedelta(minutes=5)
    for month in MONTHS:
        path = DATA / f"i5_d12_station_5min_{month}.csv.gz"
        if not path.exists():
            continue
        carry = None  # Avoid forming windows across month boundaries.
        count = 0
        for chunk in pd.read_csv(path, usecols=usecols, dtype=dtypes,
                                 chunksize=500_000, compression="gzip", low_memory=False):
            selected = chunk.loc[chunk["station_id"].isin(mainline_ids)
                                 & chunk["lane_type"].eq("ML")].copy()
            if selected.empty:
                continue
            count += len(selected)
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
                continuous &= (combined["timestamp"] - lagged[f"timestamp_{lag}"]).eq(shift_delta * lag)
            origin = lagged["timestamp_3"]
            target_time = combined["timestamp"]
            eligible = continuous
            for col in ("percent_observed",):
                for lag in (3, 4, 5, 6):
                    eligible &= lagged[f"{col}_{lag}"].ge(QUALITY_MIN)
                eligible &= combined[col].ge(QUALITY_MIN)
            eligible &= combined["avg_speed"].notna()
            for lag in (3, 4, 5, 6):
                eligible &= lagged[f"avg_speed_{lag}"].notna()
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
            }, index=combined.index)[FEATURES]

            split_masks = {
                "train": eligible & origin.lt(TRAIN_END) & target_time.lt(TRAIN_END),
                "validation": eligible & origin.ge(TRAIN_END) & target_time.lt(VALID_END),
                "test": eligible & origin.ge(VALID_END) & target_time.lt(TEST_END),
            }
            for split, mask in split_masks.items():
                if not mask.any():
                    continue
                subset = features.loc[mask]
                finite = np.isfinite(subset.to_numpy(dtype=np.float32)).all(axis=1)
                if not finite.any():
                    continue
                positions = subset.index.to_numpy()[finite]
                x = subset.iloc[np.flatnonzero(finite)].to_numpy(dtype=np.float32)
                y = combined.loc[positions, "avg_speed"].to_numpy(dtype=np.float32)
                persistence = lagged["avg_speed_3"].loc[positions].to_numpy(dtype=np.float32)
                metadata = np.column_stack((
                    origin.loc[positions].dt.strftime("%Y-%m-%d %H:%M:%S").to_numpy(),
                    combined.loc[positions, "station_id"].to_numpy(),
                    combined.loc[positions, "direction"].to_numpy(),
                ))
                reservoirs[split].add_batch(x, y, persistence, metadata)
            carry = combined.groupby("station_id", sort=False, group_keys=False, observed=True).tail(6).copy()
        monthly_rows[month] = count
        print(f"Processed {month}: {count:,} mainline records")

    for name, reservoir in reservoirs.items():
        print(f"{name}: {reservoir.n_seen:,} eligible, sampled {reservoir.n_kept:,}")
    x_train, y_train, _, _ = reservoirs["train"].arrays()
    if len(y_train) < 1000 or reservoirs["test"].n_kept < 1000:
        raise RuntimeError("Insufficient eligible rows to train and evaluate the model.")

    model = HistGradientBoostingRegressor(
        learning_rate=0.08, max_iter=100, max_leaf_nodes=31,
        max_bins=127, l2_regularization=1.0, early_stopping=False,
        random_state=SEED,
    )
    model.fit(x_train, y_train)
    joblib.dump({"model": model, "features": FEATURES, "target": "avg_speed_mph at t+15m",
                 "quality_min_percent_observed": QUALITY_MIN}, OUT / "i5_d12_mainline_speed_15m.joblib")

    results = {
        "target": "average speed (mph) 15 minutes after forecast origin",
        "scope": "District 12 I-5, matched mainline stations, both directions",
        "quality_rule": "% observed >= 90 for every input speed row and the target row",
        "feature_columns": FEATURES,
        "split": {"train": "Jan-May 2026", "validation": "June 2026", "test": "July-Aug 2026"},
        "sample_caps": CAPS,
        "eligible_rows": {k: v.n_seen for k, v in reservoirs.items()},
        "sampled_rows": {k: v.n_kept for k, v in reservoirs.items()},
        "monthly_mainline_records_scanned": monthly_rows,
        "model": "HistGradientBoostingRegressor; 100 iterations; max_leaf_nodes=31",
        "seed": SEED,
    }
    metric_rows = []
    for split in ("validation", "test"):
        x, y, persistence, meta = reservoirs[split].arrays()
        pred = model.predict(x)
        split_result = {
            "persistence": metrics(y, persistence),
            "hist_gradient_boosting": metrics(y, pred),
        }
        split_result["model_mae_improvement_percent_vs_persistence"] = 100.0 * (
            split_result["persistence"]["mae_mph"] - split_result["hist_gradient_boosting"]["mae_mph"]
        ) / split_result["persistence"]["mae_mph"]
        results[split] = split_result
        for name, values in (("persistence", persistence), ("hist_gradient_boosting", pred)):
            metric_rows.append({"split": split, "model": name, **metrics(y, values), "sampled_rows": len(y)})
        if split == "test":
            with (OUT / "i5_d12_speed_forecast_test_predictions.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["forecast_origin", "station_id", "direction", "actual_speed_t_plus_15_mph",
                                 "persistence_prediction_mph", "model_prediction_mph"])
                order = sorted(range(len(meta)), key=lambda i: tuple(meta[i]))
                for i in order:
                    writer.writerow([*meta[i], f"{y[i]:.3f}", f"{persistence[i]:.3f}", f"{pred[i]:.3f}"])
            for direction in ("N", "S"):
                indices = np.array([i for i, row in enumerate(meta) if row[2] == direction], dtype=int)
                results["test"][f"{direction}_only"] = {
                    "rows": int(len(indices)),
                    "persistence": metrics(y[indices], persistence[indices]),
                    "hist_gradient_boosting": metrics(y[indices], pred[indices]),
                }

    with (OUT / "i5_d12_speed_forecast_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "model", "mae_mph", "rmse_mph", "r2", "sampled_rows"])
        writer.writeheader()
        writer.writerows(metric_rows)
    with (OUT / "i5_d12_speed_forecast_results.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nHoldout results:")
    print(json.dumps({"test": results["test"], "validation": results["validation"]}, indent=2))


if __name__ == "__main__":
    main()
