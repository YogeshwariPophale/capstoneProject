# Initial I-5 District 12 15-minute speed forecast

**Run date:** November 1, 2026  
**Status:** Initial benchmark  
**Forecast target:** Average station speed, in mph, 15 minutes after the forecast origin

## Scope and data

- District 12, I-5 mainline (`ML`) stations in both directions, matched to the direction-specific PeMS station inventories.
- January–August 2026 observations. September was excluded because 85.6% of its records are below 90% observed.
- Input and target rows require at least 90% observed. A valid example also requires exact five-minute timestamps from t−30 through t, so missing intervals do not get treated as adjacent samples.
- The data collection itself has 38 missing dates in the Jan–Sep window. The model only uses examples with complete local input/target windows; this does not repair or fill those collection gaps.

## Target and features

The target is continuous speed at t+15 minutes. This provides a direct forecasting task without assuming an unapproved congestion definition.

Features available at forecast time t:

- Speed at t, t−5, t−10, and t−15 minutes
- Total flow and average occupancy at t and t−5 minutes
- Absolute postmile and direction
- Cyclic hour-of-day, weekday, and month features, plus a weekend indicator

No measurements after t are used as inputs. Persistence predicts that speed at t+15 remains equal to speed at t.

## Model and chronological evaluation

The regression model is `HistGradientBoostingRegressor` with 100 iterations and 31 maximum leaf nodes. Training examples are deterministically sampled with seed 42 to cap memory and training time. The chronological split is:

| Use | Period | Eligible examples | Used |
|---|---|---:|---:|
| Train | January–May 2026 | 5,608,018 | 300,000 |
| Validation | June 2026 | 901,020 | 75,000 |
| Test | July–August 2026 | 1,843,305 | 1,843,305 |

The model was fit on the 300,000-row training sample. Validation metrics use the 75,000-row sample. After fitting, the held-out model was evaluated on all 1,843,305 eligible July–August examples.

## Results

| Split | Method | MAE (mph) | RMSE (mph) | R² |
|---|---|---:|---:|---:|
| Validation | Persistence | 1.822 | 3.313 | 0.833 |
| Validation | Gradient boosting | 1.682 | 2.993 | 0.864 |
| Test, full eligible holdout | Persistence | 1.747 | 3.198 | 0.840 |
| Test, full eligible holdout | Gradient boosting | 1.601 | 2.858 | 0.872 |

Full-test MAE is 8.4% lower for gradient boosting than persistence. Test MAE by direction was 1.540 mph northbound and 1.659 mph southbound for gradient boosting; corresponding persistence MAEs were 1.673 and 1.817 mph. The earlier sampled estimate is retained in `i5_d12_speed_forecast_metrics.csv`; full metrics and subgroup findings are in `i5_d12_forecast_error_review.md` and its companion CSVs.

## Limits and next steps

- This forecasts speed, not congestion state. These metrics do not establish congestion classification or event detection performance.
- Very low target speeds remain a weakness: below 30 mph, model MAE is 6.47 mph versus 5.02 mph for persistence. Rapid 15-minute speed transitions account for many of the largest misses.
- Results apply to District 12 mainline detectors and the selected quality rule. They do not establish statewide performance or performance for HOV and ramp stations.
- The acquisition has missing dates and September has poor data quality. Select the final analysis window and report missingness explicitly.
- Compare additional simple and tree-based models, inspect errors by time and station, and separately define/validate a congestion label if classification remains a project goal.

## Artifacts

- Training script: `scripts/train_i5_d12_speed_forecast.py`
- Fitted model: `reports/models/i5_d12_mainline_speed_15m.joblib`
- Test sample predictions: `reports/models/i5_d12_speed_forecast_test_predictions.csv`
- Metric table: `reports/models/i5_d12_speed_forecast_metrics.csv`
- Full machine-readable run record: `reports/models/i5_d12_speed_forecast_results.json`
- Full holdout error review: `reports/models/i5_d12_forecast_error_review.md`
