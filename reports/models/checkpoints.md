# Modeling checkpoints

Updated: November 1, 2026

This log records completed modeling milestones and the criteria for advancing to the next one.

## Checkpoint 1 — Data and cohort ready

**Status: complete**

- District 12 I-5 mainline stations selected for both directions.
- Northbound and southbound observed station IDs matched their direction-specific PeMS inventory snapshots.
- Primary modeling data use January–August 2026. September is held out of the first model because 85.6% of its records have less than 90% observed.
- The available local source collection has 38 missing dates in January–September; only exact, complete five-minute windows enter this model.

**Evidence:** `reports/eda/overview/station_inventory_validation.csv`, `data/processed/d12_i5_2026-01_to_2026-09/manifest.json`.

## Checkpoint 2 — First 15-minute speed forecast

**Status: complete; baseline benchmark**

- Target: mainline average speed in mph at t+15 minutes.
- Inputs: speed at t and t−5/t−10/t−15, flow and occupancy at t and t−5, direction, postmile, and time features.
- Quality rule: at least 90% observed for input speed records and target; exact five-minute continuity required.
- Chronological split: train January–May, validate June, test July–August.
- Held-out test sample: 150,000 of 1,843,305 eligible examples.

| Method | Test MAE | Test RMSE | Test R² |
|---|---:|---:|---:|
| Persistence | 1.760 mph | 3.207 mph | 0.839 |
| HistGradientBoostingRegressor | 1.610 mph | 2.863 mph | 0.871 |

**Evidence:** `reports/models/i5_d12_speed_forecast_model_card.md`, `reports/models/i5_d12_speed_forecast_metrics.csv`, `reports/models/i5_d12_speed_forecast_test_predictions.csv`.

## Checkpoint 3 — Error review and full test evaluation

**Status: complete**

- Evaluated all 1,843,305 eligible July–August examples: 884,734 in July and 958,571 in August.
- Full-test MAE/RMSE/R² are 1.601 mph / 2.858 mph / 0.872 for gradient boosting and 1.747 mph / 3.198 mph / 0.840 for persistence. Full-test MAE improvement is 8.4%; these results supersede the earlier 150,000-row sample estimate.
- Saved subgroups by direction, month, hour, weekday/weekend, station, target-speed range, and size of speed change. Added the 100 largest errors and a written review.
- Inspected the feature/target alignment: predictors are from t and earlier; target is t+15; exact five-minute intervals and quality checks are required. No target-time value is used as a predictor.
- Key weakness: for target speeds below 30 mph, model MAE is 6.47 mph vs persistence at 5.02 mph. The largest misses cluster around rapid transitions.

**Evidence:** `reports/models/i5_d12_forecast_error_review.md`, `reports/models/i5_d12_forecast_error_subgroups.csv`, `reports/models/i5_d12_forecast_largest_errors.csv`.

## Checkpoint 4 — Congestion target definition

**Status: implemented for an exploratory classifier; validation remains open**

- Added a four-class speed-only operational proxy using the reference paper's speed ranges converted to mph. Because the printed bands overlap, the implementation applies severe-first precedence: Severe <40 km/h; Moderate 40–64 km/h; Slight >64–80 km/h; Free >80 km/h.
- This does not reproduce the paper's density-plus-speed labels. The paper's unit, lane, and density conventions still need review before treating these states as validated congestion ground truth.
- Used the existing 90% observed rule, exact five-minute continuity, and t+15 target alignment.
- Reviewed class coverage: eligible test labels are Free 1,753,539; Slight 33,526; Moderate 45,353; Severe 10,887 (1,843,305 total).

## Checkpoint 5 — Congestion classifier comparison

**Status: first comparable run complete; label validation and final interpretation remain open**

- Trained persistence, Logistic Regression, Random Forest, and HistGradientBoosting classifiers on the same 17 features, matched District 12 mainline cohort, quality rule, and chronological splits as the speed benchmark.
- Train: Jan-May (5,608,018 eligible; 300,000 sampled). Validation: June (901,020 scored). Test: July-August (1,843,305 scored).
- Full test results:

| Model | Accuracy | Balanced accuracy | Macro-F1 | Weighted-F1 |
|---|---:|---:|---:|---:|
| Persistence | 0.9722 | 0.7145 | 0.7147 | 0.9722 |
| Logistic Regression | 0.9460 | 0.7678 | 0.6734 | 0.9569 |
| Random Forest | 0.9708 | 0.7611 | 0.7273 | 0.9721 |
| HistGradientBoosting | 0.9464 | 0.7974 | 0.6858 | 0.9574 |

- The test set is strongly imbalanced toward Free (95.1%). Random Forest has the highest macro-F1; HistGradientBoosting has the highest balanced accuracy and recall for Slight and Severe. Persistence remains strong on aggregate accuracy because Free dominates. Use per-class metrics and confusion matrices when interpreting models.
- Fitted estimators, shared metrics, confusion matrices, class prevalence, and a deterministic 150,000-row test prediction sample are saved under `reports/models/congestion_classifiers/`.
- The speed-regression comparison remains separate because its continuous target and metrics cannot be compared directly with classification scores. Held-out test data were evaluated once and were not used for tuning.

**Next:** validate or revise the speed-only proxy before presenting it as congestion ground truth; inspect false negatives and false alarms by direction, station, and time; update the final report with this classifier experiment and its limitations.
