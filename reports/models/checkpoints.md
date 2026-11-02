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

**Status: pending**

- Decide whether the project will add congestion classification alongside continuous speed forecasting.
- Review the reference paper’s speed/density categories against PeMS field definitions and the available variables; do not assume exploratory 30/40/50 mph cutoffs are validated labels.
- Document the chosen threshold(s), quality rule, episode handling, and target timing before producing labels.
- Check class prevalence and station/time coverage before model training.

**Complete when:** the label definition is documented, implementable from the available fields, and its prevalence/coverage has been reviewed on the intended date window.

## Checkpoint 5 — Model comparison and final evaluation

**Status: pending**

- Keep persistence as the minimum baseline.
- Compare the speed regressor with at least one additional suitable model using the same inputs, chronological split, and test set.
- If a congestion label is approved, train classification baselines separately and report metrics appropriate to class imbalance, including precision, recall, F1, and confusion matrix.
- Freeze the evaluation period before final model selection; do not tune on the held-out test period.

**Complete when:** model comparisons use consistent data and splits, test results are reported with sample counts, and limitations are written into the report.
