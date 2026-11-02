# 15-minute speed forecast error review

**Review date:** November 1, 2026  
**Evaluation:** Every eligible July–August 2026 test window (not a sample)  
**Rows evaluated:** 1,843,305; July 884,734 and August 958,571

## Overall test results

| Method | MAE | RMSE | R² |
|---|---:|---:|---:|
| Persistence | 1.747 mph | 3.198 mph | 0.840 |
| HistGradientBoostingRegressor | 1.601 mph | 2.858 mph | 0.872 |

The model reduces full-test MAE by 8.4% versus persistence. This improves on the earlier sampled estimate; these full-holdout results supersede that estimate.

## Where errors differ

- **Direction:** Northbound MAE is 1.540 mph (895,730 rows); southbound MAE is 1.659 mph (947,575 rows). Persistence MAEs are 1.673 and 1.817 mph, respectively.
- **Month:** July MAE is 1.600 mph and August is 1.602 mph, so aggregate accuracy is similar in these two test months.
- **Time of day:** Hourly MAE is lowest around 02:00 (1.174 mph) and highest at 17:00 (2.060 mph). Afternoon hours 15:00–17:00 are among the harder periods.
- **Day type:** Weekday MAE is 1.736 mph across 1,214,698 rows; weekend MAE is 1.340 mph across 628,607 rows.
- **Target speed ranges (descriptive bins, not approved congestion labels):** At speeds below 30 mph, MAE is 6.473 mph versus persistence at 5.020 mph, so the model is worse by 29%. For 30–50 mph, the model and persistence are nearly tied (6.122 vs 6.140 mph). For 50–65 and at least 65 mph, the model improves MAE by 10.4% and 11.6%.
- **Large speed changes:** When target speed differs from current speed by more than 15 mph (17,244 windows), model MAE is 16.89 mph versus 21.10 mph for persistence. The model helps, but forecasts remain difficult in these transitions. For changes of 5–15 mph, MAE is 6.39 vs 8.01 mph; for changes of at most 5 mph, it is 1.22 vs 1.25 mph.

## Largest misses and data review

The top 100 absolute errors all exceed 20 mph; their median absolute error is 43.28 mph. A recurring pattern is a rapid transition between very low speed and free-flow speed within 15 minutes. For example, southbound station 1204886 (N of Sand Canyon) had 14.9 mph at 05:45 on July 16 and 82.4 mph at 06:00, with 100% observed at both rows. Its subsequent 5-minute speeds stayed near 80 mph. This may reflect a real rapid recovery or a detector/aggregation issue; `% observed` alone does not settle that question.

Some individual stations have relatively high MAE, and one of the highest-error stations has only 282 eligible test windows. Station-level results should be interpreted alongside their row counts. Review the detailed subgroup and top-error tables before excluding any station or event.

## Leakage and alignment review

The error analysis recreates the training window rules. Predictions use measurements at t and earlier only; target speed is at t+15. The exact five-minute input sequence and target are checked, records must meet the 90% observed cutoff, and test origins/targets remain within July–August. No target-time measurement is used as a predictor. Target-speed bands and transition-size groups are post-hoc error strata only.

## Files

- Full subgroup metrics: `i5_d12_forecast_error_subgroups.csv`
- 100 largest errors: `i5_d12_forecast_largest_errors.csv`
- Machine-readable summary: `i5_d12_forecast_error_review.json`
- Reproducible analysis: `scripts/analyze_i5_d12_forecast_errors.py`
