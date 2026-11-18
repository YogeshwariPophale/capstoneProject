"""Train comparable 15-minute I-5 congestion-state classifiers.

This script is intentionally self-contained and does not import the speed
regression trainer. It uses the same District 12 mainline cohort, chronological
splits, 90% observed rule, six-row continuity check, and feature definitions.

The reference paper's speed ranges overlap. This implementation makes the
speed-only proxy explicit, applying the most severe matching state first:
Severe < 40 km/h; Moderate 40-64 km/h; Slight >64-80 km/h; Free >80 km/h.
These are converted to mph because PeMS average speed is recorded in mph.
This is an operational proxy, not a reconstruction of the paper's density-
and-speed label (PeMS density and the paper's unit/lane conversions need more
validation before those labels can be reproduced).
"""
from __future__ import annotations

import csv
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/d12_i5_2026-01_to_2026-09"
INVENTORY = ROOT / "reports/eda/overview/station_inventory_validation.csv"
OUT = ROOT / "reports/models/congestion_classifiers"
MONTHS = tuple(f"2026-{m:02d}" for m in range(1, 9))
TRAIN_END = datetime(2026, 6, 1)
VALID_END = datetime(2026, 7, 1)
TEST_END = datetime(2026, 9, 1)
QUALITY_MIN = 90.0
SEED = 42
CAPS = {"train": 300_000, "validation": 75_000, "test": 150_000}
CHUNK_ROWS = 500_000
CLASSES = ("Free", "Slight", "Moderate", "Severe")
CLASS_IDS = {name: i for i, name in enumerate(CLASSES)}
KMH_TO_MPH = 0.621371192237334
SPEED_CUTS_MPH = {
    "severe_below": 40.0 * KMH_TO_MPH,
    "moderate_upper": 64.0 * KMH_TO_MPH,
    "slight_upper": 80.0 * KMH_TO_MPH,
}
FEATURES = [
    "speed_now_mph", "speed_lag_5m_mph", "speed_lag_10m_mph", "speed_lag_15m_mph",
    "flow_now_5m", "flow_lag_5m", "occupancy_now", "occupancy_lag_5m",
    "absolute_postmile", "is_southbound", "hour_sin", "hour_cos",
    "weekday_sin", "weekday_cos", "is_weekend", "month_sin", "month_cos",
]


class Reservoir:
    """Uniform deterministic reservoir for bounded training/evaluation samples."""

    def __init__(self, cap: int, n_features: int, rng: random.Random):
        self.cap = cap
        self.rng = rng
        self.n_seen = 0
        self.n_kept = 0
        self.x = np.empty((cap, n_features), dtype=np.float32)
        self.y = np.empty(cap, dtype=np.int8)
        self.persistence = np.empty(cap, dtype=np.int8)
        self.meta = np.empty((cap, 3), dtype=object)
        self.keys = np.empty(cap, dtype=np.float64)

    def add_batch(self, features, target, persistence, metadata):
        n = len(target)
        if not n:
            return
        self.n_seen += n
        keys = np.asarray([self.rng.random() for _ in range(n)], dtype=np.float64)
        if n > self.cap:
            selected = np.argpartition(keys, -self.cap)[-self.cap:]
            keys, features, target, persistence, metadata = (
                keys[selected], features[selected], target[selected], persistence[selected], metadata[selected]
            )
        all_keys = np.concatenate((self.keys[:self.n_kept], keys))
        all_x = np.concatenate((self.x[:self.n_kept], features), axis=0)
        all_y = np.concatenate((self.y[:self.n_kept], target))
        all_p = np.concatenate((self.persistence[:self.n_kept], persistence))
        all_meta = np.concatenate((self.meta[:self.n_kept], metadata), axis=0)
        keep = min(self.cap, len(all_keys))
        chosen = np.argpartition(all_keys, -keep)[-keep:]
        self.n_kept = keep
        self.keys[:keep] = all_keys[chosen]
        self.x[:keep] = all_x[chosen]
        self.y[:keep] = all_y[chosen]
        self.persistence[:keep] = all_p[chosen]
        self.meta[:keep] = all_meta[chosen]


def load_mainline_metadata():
    metadata = {}
    with INVENTORY.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["station_type"] == "Mainline" and row["validation"] == "match":
                metadata[row["station_id"]] = row
    if not metadata:
        raise RuntimeError(f"No matched mainline metadata found in {INVENTORY}")
    return metadata


def state_ids(speed_mph: np.ndarray) -> np.ndarray:
    """Apply explicit severe-first precedence to the paper's speed ranges."""
    speed = np.asarray(speed_mph, dtype=np.float64)
    result = np.full(speed.shape, CLASS_IDS["Free"], dtype=np.int8)
    result[speed <= SPEED_CUTS_MPH["slight_upper"]] = CLASS_IDS["Slight"]
    result[speed <= SPEED_CUTS_MPH["moderate_upper"]] = CLASS_IDS["Moderate"]
    result[speed < SPEED_CUTS_MPH["severe_below"]] = CLASS_IDS["Severe"]
    return result


def iter_examples(station_meta, postmiles):
    """Yield one split's eligible examples at a time from source chunks."""
    mainline_ids = set(station_meta)
    usecols = ["timestamp", "station_id", "direction", "lane_type", "percent_observed",
               "total_flow", "avg_occupancy", "avg_speed"]
    dtypes = {"timestamp": str, "station_id": str, "direction": str, "lane_type": str,
              "percent_observed": "float32", "total_flow": "float32",
              "avg_occupancy": "float32", "avg_speed": "float32"}
    delta = pd.Timedelta(minutes=5)
    for month in MONTHS:
        path = DATA / f"i5_d12_station_5min_{month}.csv.gz"
        if not path.exists():
            continue
        print(f"Scanning {month}...", flush=True)
        carry = None
        chunk_number = 0
        for chunk in pd.read_csv(path, usecols=usecols, dtype=dtypes,
                                 chunksize=CHUNK_ROWS, compression="gzip", low_memory=False):
            chunk_number += 1
            print(f"  {month} chunk {chunk_number}", flush=True)
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
                continuous &= (combined["timestamp"] - lagged[f"timestamp_{lag}"]).eq(delta * lag)
            origin = lagged["timestamp_3"]
            target_time = combined["timestamp"]
            eligible = continuous.copy()
            for lag in (3, 4, 5, 6):
                eligible &= lagged[f"percent_observed_{lag}"].ge(QUALITY_MIN)
                eligible &= lagged[f"avg_speed_{lag}"].notna()
            eligible &= combined["percent_observed"].ge(QUALITY_MIN)
            eligible &= combined["avg_speed"].notna()
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
                y = state_ids(combined.loc[positions, "avg_speed"].to_numpy(dtype=np.float32))
                current_speed = lagged["avg_speed_3"].loc[positions].to_numpy(dtype=np.float32)
                persistence = state_ids(current_speed)
                metadata = np.column_stack((
                    origin.loc[positions].dt.strftime("%Y-%m-%d %H:%M:%S").to_numpy(),
                    combined.loc[positions, "station_id"].to_numpy(),
                    combined.loc[positions, "direction"].to_numpy(),
                ))
                yield split, x, y, persistence, metadata
            carry = combined.groupby("station_id", sort=False, group_keys=False, observed=True).tail(6).copy()


def make_models():
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(C=1.0, class_weight="balanced", max_iter=300,
                               solver="lbfgs", random_state=SEED),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, min_samples_leaf=5, max_features="sqrt",
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            learning_rate=0.08, max_iter=100, max_leaf_nodes=31,
            max_bins=127, l2_regularization=1.0,
            early_stopping=False, random_state=SEED,
        ),
    }


def summarize_confusion(matrix):
    # Derive class metrics directly so evaluation can be accumulated by batch.
    tp = np.diag(matrix).astype(float)
    actual = matrix.sum(axis=1).astype(float)
    predicted = matrix.sum(axis=0).astype(float)
    class_precision = np.divide(tp, predicted, out=np.zeros_like(tp), where=predicted > 0)
    class_recall = np.divide(tp, actual, out=np.zeros_like(tp), where=actual > 0)
    class_f1 = np.divide(2 * class_precision * class_recall,
                         class_precision + class_recall,
                         out=np.zeros_like(tp), where=(class_precision + class_recall) > 0)
    total = int(matrix.sum())
    return {
        "rows": total,
        "accuracy": float(tp.sum() / total) if total else 0.0,
        "balanced_accuracy": float(class_recall.mean()),
        "macro_f1": float(class_f1.mean()),
        "weighted_f1": float(np.average(class_f1, weights=actual)) if total else 0.0,
        "per_class": {
            CLASSES[i]: {"precision": float(class_precision[i]), "recall": float(class_recall[i]),
                         "f1": float(class_f1[i]), "support": int(actual[i])}
            for i in range(len(CLASSES))
        },
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    station_meta = load_mainline_metadata()
    postmiles = {sid: float(row["postmile_absolute"]) for sid, row in station_meta.items()}
    rng = random.Random(SEED)
    reservoirs = {name: Reservoir(cap, len(FEATURES), rng) for name, cap in CAPS.items()}

    for split, x, y, persistence, metadata in iter_examples(station_meta, postmiles):
        reservoirs[split].add_batch(x, y, persistence, metadata)
    for split, reservoir in reservoirs.items():
        print(f"{split}: eligible={reservoir.n_seen:,}; sampled={reservoir.n_kept:,}")
    if reservoirs["train"].n_kept < 1000 or reservoirs["test"].n_kept < 1000:
        raise RuntimeError("Insufficient eligible observations to train and evaluate classifiers.")

    x_train = reservoirs["train"].x[:reservoirs["train"].n_kept]
    y_train = reservoirs["train"].y[:reservoirs["train"].n_kept]
    train_counts = Counter(int(v) for v in y_train)
    if len(train_counts) != len(CLASSES):
        raise RuntimeError(f"Training sample lacks one or more classes: {train_counts}")
    class_weights = np.asarray([1.0 / train_counts[i] for i in range(len(CLASSES))], dtype=np.float64)
    class_weights /= class_weights.mean()
    models = make_models()
    for name, model in models.items():
        print(f"Training {name} ...")
        if name == "hist_gradient_boosting":
            model.fit(x_train, y_train, sample_weight=class_weights[y_train])
        else:
            model.fit(x_train, y_train)
        joblib.dump({
            "model": model, "features": FEATURES, "classes": CLASSES,
            "target": "speed-derived congestion state at t+15m",
            "speed_cutoffs_mph": SPEED_CUTS_MPH,
            "label_rule": "Severe-first ordered speed-only proxy; see model card.",
            "quality_min_percent_observed": QUALITY_MIN,
            "seed": SEED,
        }, OUT / f"i5_d12_{name}_congestion_15m.joblib", compress=3)

    metrics = {split: {name: np.zeros((len(CLASSES), len(CLASSES)), dtype=np.int64)
                       for name in ["persistence", *models]}
               for split in ("validation", "test")}
    sampled_predictions = []
    sample_rng = random.Random(SEED + 1)
    sample_seen = 0
    sample_cap = CAPS["test"]
    for split, x, y, persistence, metadata in iter_examples(station_meta, postmiles):
        if split not in metrics:
            continue
        prediction_map = {"persistence": persistence}
        for name, model in models.items():
            prediction_map[name] = model.predict(x).astype(np.int8)
        for name, prediction in prediction_map.items():
            metrics[split][name] += confusion_matrix(y, prediction, labels=np.arange(len(CLASSES)))
        if split == "test":
            for i in range(len(y)):
                sample_seen += 1
                if len(sampled_predictions) < sample_cap:
                    sampled_predictions.append((metadata[i], int(y[i]),
                                                {k: int(v[i]) for k, v in prediction_map.items()}))
                else:
                    j = sample_rng.randrange(sample_seen)
                    if j < sample_cap:
                        sampled_predictions[j] = (metadata[i], int(y[i]),
                                                   {k: int(v[i]) for k, v in prediction_map.items()})
        print(f"Evaluated {split} batch: {len(y):,} rows")

    results = {
        "target": "speed-derived congestion state at t+15 minutes",
        "label_definition": {
            "method": "speed-only operational proxy using reference-paper speed bands with explicit severity precedence",
            "units": "mph; paper km/h cutoffs converted using 1 km/h = 0.6213711922 mph",
            "precedence": "Severe, then Moderate, then Slight, then Free",
            "states": {
                "Severe": f"speed < {SPEED_CUTS_MPH['severe_below']:.6f} mph (<40 km/h)",
                "Moderate": f"{SPEED_CUTS_MPH['severe_below']:.6f} <= speed <= {SPEED_CUTS_MPH['moderate_upper']:.6f} mph (40-64 km/h)",
                "Slight": f"{SPEED_CUTS_MPH['moderate_upper']:.6f} < speed <= {SPEED_CUTS_MPH['slight_upper']:.6f} mph (>64-80 km/h)",
                "Free": f"speed > {SPEED_CUTS_MPH['slight_upper']:.6f} mph (>80 km/h)",
            },
            "limitation": "Does not reproduce the paper's density-plus-speed classifier; thresholds are an operational proxy pending validation of PeMS units, lane conventions, and density calculation.",
        },
        "scope": "District 12 I-5 inventory-matched mainline stations, both directions",
        "quality_rule": "% observed >= 90 for all required speed rows and the target; exact five-minute continuity required",
        "features": FEATURES,
        "split": {"train": "Jan-May 2026", "validation": "June 2026", "test": "July-Aug 2026"},
        "sample_caps": CAPS,
        "eligible_rows": {k: v.n_seen for k, v in reservoirs.items()},
        "sampled_rows": {k: v.n_kept for k, v in reservoirs.items()},
        "training_class_counts": {CLASSES[k]: int(v) for k, v in sorted(train_counts.items())},
        "validation_class_counts": {CLASSES[i]: int(metrics["validation"]["persistence"][i].sum())
                                    for i in range(len(CLASSES))},
        "test_class_counts": {CLASSES[i]: int(metrics["test"]["persistence"][i].sum())
                              for i in range(len(CLASSES))},
        "models": {
            "persistence": "predict current-time state unchanged",
            "logistic_regression": "StandardScaler + LogisticRegression(C=1, class_weight=balanced, max_iter=300)",
            "random_forest": "RandomForestClassifier(200 trees, min_samples_leaf=5, sqrt features, balanced_subsample)",
            "hist_gradient_boosting": "HistGradientBoostingClassifier(100 iterations, max_leaf_nodes=31); inverse-frequency training weights",
        },
        "seed": SEED,
        "scores": {},
    }
    confusion_rows = []
    metric_rows = []
    for split in ("validation", "test"):
        results["scores"][split] = {}
        for name, matrix in metrics[split].items():
            score = summarize_confusion(matrix)
            results["scores"][split][name] = score
            metric_rows.append({"split": split, "model": name, **{k: v for k, v in score.items() if k != "per_class"}})
            for i, actual in enumerate(CLASSES):
                for j, predicted in enumerate(CLASSES):
                    confusion_rows.append({"split": split, "model": name,
                                           "actual_state": actual, "predicted_state": predicted,
                                           "count": int(matrix[i, j])})
    with (OUT / "i5_d12_congestion_15m_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "model", "rows", "accuracy", "balanced_accuracy", "macro_f1", "weighted_f1"])
        writer.writeheader(); writer.writerows(metric_rows)
    with (OUT / "i5_d12_congestion_15m_confusion_matrices.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "model", "actual_state", "predicted_state", "count"])
        writer.writeheader(); writer.writerows(confusion_rows)
    with (OUT / "i5_d12_congestion_15m_test_predictions_sample.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["forecast_origin", "station_id", "direction", "actual_state"] + [f"{m}_prediction" for m in ["persistence", *models]]
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for meta, actual, predictions in sorted(sampled_predictions, key=lambda row: tuple(row[0])):
            writer.writerow({"forecast_origin": meta[0], "station_id": meta[1], "direction": meta[2],
                             "actual_state": CLASSES[actual],
                             **{f"{k}_prediction": CLASSES[v] for k, v in predictions.items()}})
    with (OUT / "i5_d12_congestion_15m_results.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    lines = [
        "# District 12 I-5 15-minute congestion-state classifiers",
        "",
        f"**Run date:** {datetime.now().date().isoformat()}",
        "",
        "**Target:** Speed-derived congestion state at t+15 minutes",
        "",
        "**Scope:** Inventory-matched District 12 I-5 mainline stations, both directions",
        "",
        "## Label definition",
        "",
        "The reference paper reports overlapping speed intervals and also uses density. This run uses a transparent speed-only operational proxy, applying the most severe matching interval first:",
        "",
        f"- Severe: speed < {SPEED_CUTS_MPH['severe_below']:.3f} mph (<40 km/h)",
        f"- Moderate: {SPEED_CUTS_MPH['severe_below']:.3f} to {SPEED_CUTS_MPH['moderate_upper']:.3f} mph (40-64 km/h)",
        f"- Slight: >{SPEED_CUTS_MPH['moderate_upper']:.3f} to {SPEED_CUTS_MPH['slight_upper']:.3f} mph (>64-80 km/h)",
        f"- Free: >{SPEED_CUTS_MPH['slight_upper']:.3f} mph (>80 km/h)",
        "",
        "This does not reproduce the paper's density-plus-speed classifier. Interpret scores as performance against this operational proxy until PeMS units, lane conventions, density calculation, and label validity are further reviewed.",
        "",
        "## Comparable setup",
        "",
        "- Same cohort, features, 90% observed threshold, exact five-minute continuity, and chronological splits as the speed benchmark.",
        "- Train Jan-May, validate June, test July-Aug 2026. Training sample capped at 300,000; validation and test scores below use every eligible example in each split.",
        "- Inputs use observations at forecast time t and earlier only; target is the label at t+15.",
        "- Classifiers use inverse-frequency weighting to address class imbalance; persistence predicts the t state unchanged.",
        "",
        "## Models",
        "",
        "| Model | Configuration |",
        "|---|---|",
        "| Persistence | Current-time state carried forward |",
        "| Logistic Regression | StandardScaler; C=1; balanced class weights; lbfgs; 300 iterations |",
        "| Random Forest | 200 trees; min leaf 5; sqrt features; balanced_subsample |",
        "| HistGradientBoosting | 100 iterations; 31 leaves; inverse-frequency sample weights |",
        "",
        "## Results",
        "",
        "Metrics emphasize macro-F1 and balanced accuracy because class frequencies differ. See the CSV companion for all metrics and confusion matrices.",
        "",
        "| Split | Model | Rows | Accuracy | Balanced accuracy | Macro-F1 | Weighted-F1 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in metric_rows:
        lines.append(f"| {row['split']} | {row['model']} | {row['rows']:,} | {row['accuracy']:.4f} | {row['balanced_accuracy']:.4f} | {row['macro_f1']:.4f} | {row['weighted_f1']:.4f} |")
    lines += [
        "",
        "## Artifacts",
        "",
        "- `i5_d12_logistic_regression_congestion_15m.joblib`",
        "- `i5_d12_random_forest_congestion_15m.joblib`",
        "- `i5_d12_hist_gradient_boosting_congestion_15m.joblib`",
        "- `i5_d12_congestion_15m_metrics.csv`",
        "- `i5_d12_congestion_15m_confusion_matrices.csv`",
        "- `i5_d12_congestion_15m_test_predictions_sample.csv` (deterministic 150,000-row sample)",
        "- `i5_d12_congestion_15m_results.json` (full metrics, class counts, label and split metadata)",
    ]
    (OUT / "i5_d12_congestion_15m_model_card.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nFull-split classification metrics:")
    print(json.dumps(results["scores"], indent=2))


if __name__ == "__main__":
    main()
