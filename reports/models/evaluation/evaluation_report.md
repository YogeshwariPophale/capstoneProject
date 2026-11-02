# I-5 District 12 forecast evaluation visuals

## Evaluation scope

- Forecast: average speed 15 minutes after the forecast origin, in mph.
- Cohort: inventory-matched District 12 I-5 mainline stations, northbound and southbound.
- Chronological split: January–May train (5,608,018 eligible; 300,000 sampled), June validation (901,020 eligible; 75,000 sampled), July–August test (1,843,305 eligible).
- Quality: at least 90% observed on required speed records and target; complete five-minute continuity.
- Test metrics below use the **full** eligible holdout. Actual-vs-predicted plots use the saved deterministic 150,000-row test sample and are labeled accordingly.

## Full holdout metrics

| Method | MAE (mph) | RMSE (mph) | R² |
|---|---:|---:|---:|
| Persistence | 1.747 | 3.198 | 0.840 |
| HistGradientBoostingRegressor | 1.601 | 2.858 | 0.872 |

The model reduces full-holdout MAE by 8.4% relative to persistence. This is speed regression evidence, not congestion-classification performance.

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
