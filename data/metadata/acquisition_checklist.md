# PeMS data acquisition and preparation checklist

Project: I-5 Traffic Congestion Analysis and Short-Term Prediction  
Last reviewed: 2026-11-01

## Current working scope

- [x] Start with District 12, I-5 (Freeway 5), both N and S directions.
- [x] Work with available 2026 daily Station 5-Minute data from January 1 through September 30.
- [x] Retain every lane/station type initially; defer inclusion/exclusion choices to EDA and report methods.
- [x] Preserve the supplied daily text files and create a reproducible monthly compressed CSV dataset.
- [x] Record input coverage gaps and processing provenance in the manifest and acquisition log.
- [x] Confirm the transformation completed and reconcile the manifest totals: 175,057,116 source rows; 48,382,620 retained I-5 rows; 0 malformed-width rows.
- [x] Validate all nine gzip outputs by full decompression/CRC; monthly row counts match manifest, header has 52 fields.
- [x] Add reusable EDA functions with one-file/day/month selection, raw-data filtering, metadata joins, plots, and optional prediction-alignment checks.
- [x] Check timestamp parsing, five-minute continuity, duplicate station/timestamp records, missingness, and `% observed` quality in the monthly EDA outputs and nine-month diagnostics.
- [x] Validate D12 I-5 northbound station IDs, postmiles, locations, and types against the supplied PeMS metadata snapshot.
- [x] Obtain and validate the southbound PeMS station inventory snapshot against observed southbound station IDs.
- [x] Run monthly EDA and supplemental cross-month comparisons for direction/lane type, quality filtering, speed-threshold sensitivity, prediction alignment, and low-speed episode duration.
- [x] Select District 12 mainline (`ML`) stations in both directions as the provisional primary modeling cohort; analyze HOV and ramps separately.
- [x] Confirm southbound mainline station IDs/types and postmile coverage against a southbound inventory.
- [x] Train an initial 15-minute mainline speed forecasting model and compare it with a persistence baseline using chronological holdout periods.
- [ ] Select and validate the final congestion label before classification experiments.
- [ ] Expand evaluation to additional seasons or a new date window after the missing-date and quality policy is finalized.
- [x] Complete model-error review and full eligible July–August holdout evaluation; track next criteria in `reports/models/checkpoints.md`.

## Completed EDA run notes (2026-10-20)

- Monthly EDA outputs are saved separately under `reports/eda/processed_2026-01/` through `processed_2026-09/`; supplemental cross-month tables are under `reports/eda/overview/`. The source and processed data files were read only.
- All nine monthly overviews report zero duplicate `(timestamp, station_id, direction, lane_type)` rows. Parsed timestamps were present for all rows; exact 15-minute timestamp matches ranged from 99.83% to 99.96%, depending on month. Missing dates and within-series gaps are represented in the `sampling_gaps.csv` outputs.
- `% observed` is populated in all rows, but its mean varies substantially: 65.1%–79.3% in January–August and 15.7% in September. Across the data, the quality-filter comparison should be reviewed before selecting records for modeling; September is particularly unreliable and incomplete.
- Exploratory speed cutoffs of 30, 40, and 50 mph were scanned for sensitivity only. These are not approved congestion labels. Threshold-based episode-duration results are in `exploratory_episode_duration_sensitivity.csv`.
- As of the 2026-10-20 EDA runs, station inventory validation and mainline/HOV/ramp selection were pending. Phase 2 later completed both direction-specific inventory checks and selected the mainline cohort; model labeling/training remain open.

## Phase 2: station validation and cohort definition (2026-10-31)

- The supplied `pems_output_stations_I5N.xlsx` is a PeMS Field Elements > Stations export for I-5 northbound generated 2026-10-19. It contains 1,114 station records across the route and includes District, County, City, postmile, station ID/name, station type, and HOV status.
- Compared its 362 District 12 station IDs with the unique northbound IDs across all nine processed months. All 362 matched; there were no observation-only or inventory-only IDs. See `reports/eda/overview/station_inventory_validation.csv`; rerun with `scripts/validate_d12_station_inventory.py`.
- At the time of the Oct. 31 review, the project had 353 unique southbound IDs but no southbound inventory; the inventory was added and matched on Nov. 1 (see below).
- The N inventory classifies its 362 D12 stations as 115 Mainline, 113 HOV, 64 On Ramp, 52 Off Ramp, 15 Fwy-Fwy, and 3 Coll-Dist. Use `ML` records in both directions as the provisional primary cohort; retain other types for separate analyses. This choice aligns with the reference study's use of mainline sensors and the cross-month EDA, where ML mean speed is available in both directions but ramp-like lane types do not have mean speed.
- The ID match establishes consistency with the supplied October 19 inventory, not continuous operation or measurement completeness throughout January–September. September remains a quality concern: 85.6% of its observations are below 90% observed. Decide and document a quality policy before modeling.

## Southbound inventory added (2026-11-01)

- Added `southbound_stations.xlsx` and updated `scripts/validate_d12_station_inventory.py` to compare each direction to its own inventory.
- All 353 observed S station IDs matched the 353 District 12 I-5 S inventory IDs. There were zero observation-only and zero inventory-only IDs. The inventory supplies station-level county, city, postmile, name, type, and HOV status for S as well as N.
- Southbound station types: 115 Mainline, 107 HOV, 59 Off Ramp, 53 On Ramp, 15 Fwy-Fwy, and 4 Coll-Dist. Mainline stations are now inventory-validated for both directions, confirming the provisional primary cohort choice.
- The refreshed N/S station-level comparison is `reports/eda/overview/station_inventory_validation.csv`.

## Initial forecasting model (2026-11-01)

- Trained a first regression model for average mainline speed 15 minutes ahead. This is a continuous-speed forecasting target; it does not require a congestion-label definition.
- Used current and prior 5/10/15-minute speeds, current and prior-5-minute flow/occupancy, postmile, direction, and time-of-week/calendar features. Rows required exact five-minute continuity and at least 90% observed for input speed records and the target.
- Chronological periods: Jan–May train, June validation, July–August test. September was excluded because 85.6% of its rows are below 90% observed. Of 5.61M eligible train windows, 901,020 validation windows, and 1.84M test windows, deterministic random samples of 300K/75K/150K were used respectively.
- On the 150K test sample, HistGradientBoostingRegressor achieved 1.610 mph MAE, 2.863 mph RMSE, and R² 0.871; persistence achieved 1.760 mph MAE, 3.207 mph RMSE, and R² 0.839. This is an initial benchmark, not a finalized congestion detector or a complete production evaluation.
- Detailed method, metrics, and limitations are in `reports/models/i5_d12_speed_forecast_model_card.md`; test predictions, fitted model, metrics, and machine-readable results are saved beside it.

## Important scope limits

This is a District 12 segment, not all of I-5 across California. The source district files include other roads, which the script filters out. Missing dates in the supplied folder are not evidence that PeMS does not offer those dates. The reference paper studied a separate 9-km Sacramento corridor over September 2013; use it as methodological context, not as the definition of this dataset.

## Provenance

See `acquisition_log.md` for the chronological scope history, earlier pilot downloads, current input details, processing command, and final run results. The generated `manifest.json` is the authoritative record of exact file and row counts for the derived dataset.
