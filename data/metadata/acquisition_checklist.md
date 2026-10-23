# PeMS data acquisition and preparation checklist

Project: I-5 Traffic Congestion Analysis and Short-Term Prediction  
Last reviewed: 2026-10-21

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
- [ ] Validate D12 I-5 station IDs, postmiles, locations, and types against a relevant PeMS metadata snapshot.
- [x] Run monthly EDA and supplemental cross-month comparisons for direction/lane type, quality filtering, speed-threshold sensitivity, prediction alignment, and low-speed episode duration.
- [ ] Choose mainline, HOV, or ramp study segment and justify it after station metadata validation and review of the quality findings.

## Completed EDA run notes (2026-10-20)

- Monthly EDA outputs are saved separately under `reports/eda/processed_2026-01/` through `processed_2026-09/`; supplemental cross-month tables are under `reports/eda/overview/`. The source and processed data files were read only.
- All nine monthly overviews report zero duplicate `(timestamp, station_id, direction, lane_type)` rows. Parsed timestamps were present for all rows; exact 15-minute timestamp matches ranged from 99.83% to 99.96%, depending on month. Missing dates and within-series gaps are represented in the `sampling_gaps.csv` outputs.
- `% observed` is populated in all rows, but its mean varies substantially: 65.1%–79.3% in January–August and 15.7% in September. Across the data, the quality-filter comparison should be reviewed before selecting records for modeling; September is particularly unreliable and incomplete.
- Exploratory speed cutoffs of 30, 40, and 50 mph were scanned for sensitivity only. These are not approved congestion labels. Threshold-based episode-duration results are in `exploratory_episode_duration_sensitivity.csv`.
- The station inventory comparison and final mainline/HOV/ramp selection remain pending. No congestion label or prediction model was finalized in these EDA runs.

## Important scope limits

This is a District 12 segment, not all of I-5 across California. The source district files include other roads, which the script filters out. Missing dates in the supplied folder are not evidence that PeMS does not offer those dates. The reference paper studied a separate 9-km Sacramento corridor over September 2013; use it as methodological context, not as the definition of this dataset.

## Provenance

See `acquisition_log.md` for the chronological scope history, earlier pilot downloads, current input details, processing command, and final run results. The generated `manifest.json` is the authoritative record of exact file and row counts for the derived dataset.
