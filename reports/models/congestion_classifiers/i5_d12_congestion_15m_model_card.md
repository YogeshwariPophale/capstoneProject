# District 12 I-5 15-minute congestion-state classifiers

**Run date:** 2026-11-18
**Target:** Speed-derived congestion state at t+15 minutes
**Scope:** Inventory-matched District 12 I-5 mainline stations, both directions

## Label definition

The reference paper reports overlapping speed intervals and also uses density. This run uses a transparent speed-only operational proxy, applying the most severe matching interval first:

- Severe: speed < 24.854848 mph (<40 km/h)
- Moderate: 24.854848 <= speed <= 39.767756 mph (40-64 km/h)
- Slight: 39.767756 < speed <= 49.709695 mph (>64-80 km/h)
- Free: speed > 49.709695 mph (>80 km/h)

This does not reproduce the paper's density-plus-speed classifier. Interpret scores as performance against this operational proxy until PeMS units, lane conventions, density calculation, and label validity are further reviewed.

## Comparable setup

- Same cohort, 17 features, 90% observed threshold, exact five-minute continuity, and chronological splits as the speed benchmark.
- Train Jan-May, validate June, test July-Aug 2026. Training was capped at 300,000 examples. Validation and test metrics below use every eligible example.
- Inputs use observations at forecast time t and earlier only; target is the label at t+15.
- Classifiers use inverse-frequency weighting to address imbalance; persistence predicts the t state unchanged.
- Class frequencies are strongly imbalanced: test data contain 1,753,539 Free, 33,526 Slight, 45,353 Moderate, and 10,887 Severe examples.

## Models

| Model | Configuration |
|---|---|
| Persistence | Current-time state carried forward |
| Logistic Regression | StandardScaler; C=1; balanced class weights; lbfgs; 300 iterations |
| Random Forest | 200 trees; min leaf 5; sqrt features; balanced_subsample |
| HistGradientBoosting | 100 iterations; 31 leaves; inverse-frequency sample weights |

## Results

Macro-F1 and balanced accuracy are emphasized because class frequencies differ. The validation/test metrics use all eligible observations in each split.

| Split | Model | Rows | Accuracy | Balanced accuracy | Macro-F1 | Weighted-F1 |
|---|---|---:|---:|---:|---:|---:|
| validation | persistence | 901,020 | 0.9707 | 0.7109 | 0.7110 | 0.9707 |
| validation | logistic_regression | 901,020 | 0.9183 | 0.7691 | 0.6470 | 0.9402 |
| validation | random_forest | 901,020 | 0.9683 | 0.7644 | 0.7242 | 0.9701 |
| validation | hist_gradient_boosting | 901,020 | 0.9318 | 0.7996 | 0.6725 | 0.9482 |
| test | persistence | 1,843,305 | 0.9722 | 0.7145 | 0.7147 | 0.9722 |
| test | logistic_regression | 1,843,305 | 0.9460 | 0.7678 | 0.6734 | 0.9569 |
| test | random_forest | 1,843,305 | 0.9708 | 0.7611 | 0.7273 | 0.9721 |
| test | hist_gradient_boosting | 1,843,305 | 0.9464 | 0.7974 | 0.6858 | 0.9574 |

## Artifacts

- `i5_d12_logistic_regression_congestion_15m.joblib`
- `i5_d12_random_forest_congestion_15m.joblib`
- `i5_d12_hist_gradient_boosting_congestion_15m.joblib`
- `i5_d12_congestion_15m_metrics.csv`
- `i5_d12_congestion_15m_confusion_matrices.csv`
- `i5_d12_congestion_15m_test_predictions_sample.csv` (deterministic 150,000-row sample)
- `i5_d12_congestion_15m_results.json` (full metrics, class counts, label and split metadata)
