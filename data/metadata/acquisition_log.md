# PeMS acquisition log

## One-day district collection

| Field | Value |
|---|---|
| Source | Caltrans PeMS Data Clearinghouse, signed-in browser session |
| Product | Station 5-Minute, one daily text gzip per selected district |
| Data date | October 18, 2026 (latest daily file shown in the PeMS listing for these districts) |
| Retrieved | 2026-10-19 (local date) |
| Initial format check | gzip magic `1F 8B`; decompressed sample is comma-delimited and has no header row |

| District | Source filename | Bytes | SHA-256 |
|---:|---|---:|---|
| 3 | `d03_text_station_5min_2026_10_18.txt.gz` | 11,595,737 | `AFBF20EE7D088CA8AD428AED2B4BE582BF938D98EBB3BC2A4225149C0951B08D` |
| 6 | `d06_text_station_5min_2026_10_18.txt.gz` | 5,782,217 | `F86CCB9B4A7AF3129797EB288E2533B3D433F79A0EF20C66DF450E657A046584` |
| 7 | `d07_text_station_5min_2026_10_18.txt.gz` | 17,928,797 | `6FC9116EF4D1C041825B51323B062673FB7AFD390D7ECF8D7B033B58F16C9332` |
| 10 | `d10_text_station_5min_2026_10_18.txt.gz` | 8,591,042 | `C79FC9F910C6D8541BA234BAE4C64B2941147FC558CB78CB1C393C9F571C6F7B` |
| 11 | `d11_text_station_5min_2026_10_18.txt.gz` | 9,061,804 | `BF29282CA8759E00844CB41D930311B77E25039C72E724B50F83BBCA0D907872` |
| 12 | `d12_text_station_5min_2026_10_18.txt.gz` | 10,767,341 | `01233EECB7D480210E700345E5D414793170ED40B3082AA62AA126286B9DB092` |

All six originals are stored in `data/raw/`. The D3 file's gzip signature and decompressed record format were checked; no analysis or cleaning has been applied to any raw file.

PeMS's field specification lists timestamp, station ID, district, freeway number, direction, lane type, station length, samples, percent observed, total flow, average occupancy, average speed, followed by lane-level fields. Daily files are district-wide and include roads other than I-5. Filter by freeway number 5 and retain N/S direction; the route station inventory should be used to validate station IDs and geographic coverage. Use the mainline/HOV stations for the primary corridor analysis; analyze ramps separately if they are included in the research question.

## Route inventory observation

The PeMS freeway 5 northbound station export view displayed 1,114 rows/stations across seven districts (D2, D3, D6, D7, D10, D11, and D12) and postmiles from approximately 0.21 to 621.42. The view included multiple station types (mainline, HOV, ramps, freeway connectors). The export response was viewable in the browser, but it has not yet been saved as a local station metadata file. The southbound route inventory has not yet been recorded. District 2 was not present in the available Station 5-Minute Clearinghouse selector, so this one-day collection does not yet cover the full I-5 route.

## Acquisition constraints and next step

The PeMS Clearinghouse organizes 5-minute station data as daily district files. Its page says downloads are recorded and asks users not to use automated scripts; if using batch downloading tools, requests must be serial because concurrent requests will be blocked. This one-day set is not a complete time series and omits D2. Next, obtain a longer time window for available route districts and determine an approved PeMS source for D2. Keep all originals unchanged and record each file's name, date, byte size, and checksum.

## Extended District 12 collection and I-5 filtering (2026-10-19)

### Scope decision

- Current working scope is **District 12, freeway 5 (I-5), both N and S directions, January 1 through September 30, 2026**. This is the available 2026 window the project elected to start with; it does not claim statewide coverage.
- The input is the PeMS **Station 5-Minute** district product. District exports include non-I-5 roads. Filter only on `District == 12`, `Freeway == 5`, and `Direction in {N,S}` at this stage; retain every lane/station type and all raw fields for later EDA and study-specific selection.
- Use all available daily files from Jan 1 through Sep 30. The folder has 235 files for 235 of 273 calendar dates. Missing dates are captured in the generated manifest; this is a local-collection gap, not proof of unavailability at PeMS.
- Station metadata is not required to apply this first-pass route filter because district, freeway, direction, station, and lane-type fields are present in each observation. Metadata will be needed to validate geography, postmile order, and station characteristics later.
- Keep the daily raw `.txt` files and original archive unchanged. Do not combine this high-volume set into an Excel workbook. Use monthly gzip-compressed CSV outputs for analysis.

### Processing record

1. Confirmed 235 plain-text daily files in `data/raw/d12/2026-01-01_to_2026-09-30/` and a total on-disk size of 23,003,000,331 bytes.
2. Inspected the first daily record: no header row, comma-delimited, 52 fields. The first 12 fields are timestamp, station ID, district, freeway, direction, lane type, station length, samples, percent observed, total flow, average occupancy, and average speed; the remaining 40 are ten lane groups with four fields each.
3. Added `scripts/build_i5_d12_dataset.py`, a standard-library-only, repeatable transformation. It retains the 52 values, adds descriptive field names, filters District 12 + freeway 5 + N/S, retains all lane types, and emits monthly `.csv.gz` files plus `manifest.json` with per-file/day/month/direction/type/station counts and missing dates. It processes independent days in parallel (four workers by default) and assembles daily gzip members in date order.
4. A first sequential run was interrupted after 16 days when it was too slow. Its partial output was discarded by the rerun logic. The script was optimized to parallelize daily files and use streaming gzip output; no raw file was changed.
5. The full-window transformation completed from the original daily files on 2026-10-19. It processed 175,057,116 source rows and retained 48,382,620 I-5 records, with zero malformed-width rows and 715 distinct station IDs. Both directions are present: N 24,495,816 and S 23,886,804. All lane types present in these I-5 records were retained: ML 15,563,640; HV 14,886,960; OR 7,917,156; FR 7,511,148; FF 2,030,040; CD 473,676.
6. Wrote nine monthly gzip CSV files (January–September) totaling 1,510,290,815 bytes. Each includes one 52-field header and the corresponding month’s retained rows. Full gzip decompression/CRC verification succeeded for all nine files; each decompressed row count matched the manifest’s count plus one header, and the first three rows of every month had 52 fields. This validates output readability and counts, not analytical data quality or timestamp completeness.
7. Final monthly I-5 record counts: Jan 6,177,600; Feb 5,765,760; Mar 4,933,500; Apr 5,353,920; May 5,971,680; Jun 5,148,000; Jul 5,559,840; Aug 5,765,760; Sep 3,706,560.
8. Confirmed 235/273 source dates; the manifest lists all 38 missing dates. Most late-September dates are absent from the provided input (Sep 9–18 and Sep 20–21). This is only a gap in the supplied local files; it does not establish that PeMS does not offer those days.
9. Added `scripts/eda_i5_d12.py` as the reusable EDA module. It can select one processed month, one date, or one file; it also has a file-picker fallback. `find_i5_raw_files` discovers raw Station 5-Minute files and `iter_selected_chunks` filters them to I-5 for the requested slice. EDA functions cover quality/missingness, time patterns, flow-speed-occupancy relationships, station hotspots, sampling gaps, explicit-threshold congestion events, and caller-defined speed bands. Outputs are organized by selection under `reports/eda/`. The functions and script were not run across the dataset in this step.
10. Expanded the EDA module to include daily profile plots, speed-flow/occupancy plots, data-quality plots, station map and postmile-ordered time-space plot functions, adjacent-station lag correlations, and congestion-event plots. Added station metadata loading/normalization for PeMS column variants. These remain scoped to the selected file/day/month; metadata-dependent functions need a selected metadata file. Plot functions import Matplotlib only when requested with `--plots`; Matplotlib is not installed in the bundled Python runtime checked on this machine, so plots require installing it in the Python environment used to run the script. No EDA or plots were run in this update.
11. Added a prediction-alignment check for exact 5-, 10-, and 15-minute history/future timestamp matches, supporting the proposal's 15-minute target without training models or assigning labels. Preserved the single-file/day/month selector and added optional CLI flags for metadata, plots, and prediction alignment; no full-dataset processing was launched.

## Supplemental monthly EDA runs (2026-10-20)

The processed monthly CSV.GZ files were scanned read-only. All new tables are in `reports/eda/overview/`; per-month EDA tables remain in their existing `reports/eda/processed_YYYY-MM/` folders. The nine-month master/processed files were not changed.

- Completed monthly scans for `% observed` quality filtering, mean flow/occupancy/speed by direction and lane type, sampled speed quantiles, and exploratory low-speed prevalence at 30/40/50 mph. These cutoffs are sensitivity values only, not adopted congestion labels.
- Completed exact timestamp alignment counts for 5-, 10-, and 15-minute lags and a 15-minute future target. Fifteen-minute match coverage ranged from 99.826% to 99.963% by month. These are row/key timestamp matches, not model performance.
- Completed low-speed episode duration sensitivity summaries at 30/40/50 mph. Durations are based on consecutive five-minute observations for the same station/direction/lane type; episode tables remain exploratory until a label rule and data-quality policy are approved.
- Existing monthly overview tables report zero duplicate `(timestamp, station_id, direction, lane_type)` rows in each month. Monthly records had parseable timestamps; exact temporal match coverage is slightly below 100%, and sampling-gap tables show missing dates and intervals.
- `% observed` is nonmissing for all retained rows. Monthly means ranged from 65.1% to 79.3% in January–August, then fell to 15.7% in September; 85.6% of September records were below 90% observed. Review quality and September coverage before modeling.
- Station metadata validation against the available station inventory and the final selection of mainline/HOV/ramp study stations remain open. No congestion label or forecasting model was selected or trained.

### Repeat the transformation

From the project root:

```powershell
python scripts/build_i5_d12_dataset.py `
  --input data/raw/d12/2026-01-01_to_2026-09-30 `
  --output data/processed/d12_i5_2026-01_to_2026-09 `
  --start 2026-01-01 --end 2026-09-30
```

The script defaults to four parallel workers; change with `--workers N` if needed. It replaces existing monthly outputs for the selected months so reruns do not duplicate records.

The output manifest is `data/processed/d12_i5_2026-01_to_2026-09/manifest.json`; it records per-source-file and per-day counts, all missing dates, direction/type/station counts, and output byte sizes.

## Phase 2: station metadata validation and primary cohort (2026-10-31)

1. Inspected `pems_output_stations_I5N.xlsx`, a northbound I-5 Field Elements > Stations export generated by PeMS on 2026-10-19. It contains 1,114 route stations, with station ID, district, county, city, California/absolute postmile, name, type, and HOV status.
2. Added `scripts/validate_d12_station_inventory.py` to compare station IDs across all nine processed monthly files with District 12 rows in the inventory. The data contain 362 unique N IDs and 353 unique S IDs. All 362 N IDs match the inventory (zero observation-only and zero inventory-only IDs).
3. Wrote the initial station-level result to `reports/eda/overview/station_inventory_validation.csv`. At that point, it included N metadata and identified S observations as requiring their own inventory; it did not infer S geography or types from N records.
4. Selected District 12 mainline (`ML`) observations in both directions as the provisional primary cohort. The N inventory classifies its 362 stations as 115 Mainline, 113 HOV, 64 On Ramp, 52 Off Ramp, 15 Fwy-Fwy, and 3 Coll-Dist. HOV, ramps, connectors, and collector-distributors remain available for separate analyses. ML mean speed is present for both directions in the cross-month EDA, while ramp-like lane types do not have mean speed.
5. Remaining phase-2 work: select modeling dates using a documented missing-date and quality policy. September has 85.6% of records below 90% observed and should not enter primary modeling without a justified policy.

### Shared route metadata applied to southbound records (2026-11-01)

Applied District 12 and freeway 5 metadata to each S station row in `station_inventory_validation.csv`, with the same field layout as the northbound rows. At that time, no station-level S inventory was present, so S names, cities, counties, postmiles, station types, HOV flags, and inventory-match results remained unfilled/unverified. This intermediate route-level-only output was superseded after the southbound inventory was added.

## Southbound station inventory validation (2026-11-01)

1. Added `southbound_stations.xlsx`, a direction-specific I-5 southbound station inventory.
2. Updated `scripts/validate_d12_station_inventory.py` to use the N inventory for N observations and the new S inventory for S observations.
3. Re-scanned all nine processed monthly datasets. All 362 observed N IDs matched 362 D12 inventory IDs; all 353 observed S IDs matched 353 D12 inventory IDs. Both directions had zero observation-only and zero inventory-only IDs.
4. Refreshed `reports/eda/overview/station_inventory_validation.csv` with station-level metadata for both directions. The S inventory reports 115 Mainline, 107 HOV, 59 Off Ramp, 53 On Ramp, 15 Fwy-Fwy, and 4 Coll-Dist stations. This confirms the mainline cohort choice on both sides.

## Initial 15-minute speed forecast (2026-11-01)

1. Started modeling with a continuous target—station average speed in mph at t+15 minutes—because no congestion label has been approved. The cohort is inventory-matched District 12 I-5 Mainline (`ML`) stations in N and S.
2. Features at forecast time t are speed at t and t−5/t−10/t−15, flow and occupancy at t and t−5, absolute postmile, direction, and cyclic hour/weekday/month features. Exact five-minute windows are required. Input speed rows and target require at least 90% observed.
3. Used chronological splits with Jan–May for training, June for validation, and July–August for held-out testing. Excluded September because 85.6% of its observations fall below the 90% observed cutoff. Random seed 42 selected reproducible samples capped at 300,000 train, 75,000 validation, and 150,000 test examples (eligible counts: 5,608,018; 901,020; and 1,843,305).
4. Fit a `HistGradientBoostingRegressor` (100 iterations, max leaf nodes 31) and compared it with persistence (predict speed remains at its current t value). On the 150,000-row held-out sample, gradient boosting scored MAE 1.610 mph, RMSE 2.863 mph, R² 0.871. Persistence scored MAE 1.760 mph, RMSE 3.207 mph, R² 0.839. MAE improved 8.6% on this sample. June validation MAE was 1.682 mph vs 1.822 mph for persistence.
5. Outputs and reproducible code are in `reports/models/` and `scripts/train_i5_d12_speed_forecast.py`. These are baseline speed predictions, not congestion classification. The test metric is based on a deterministic random sample of eligible July–August windows, not every eligible test row. Missing dates and the quality cutoff limit generalization; define the congestion label and test it separately before claiming congestion prediction performance.

## Full holdout error review (2026-11-01)

1. Added `scripts/analyze_i5_d12_forecast_errors.py` and streamed every eligible July–August test example through the saved model in chunks. Evaluated 1,843,305 rows (884,734 July; 958,571 August), matching the eligible count from model preparation.
2. Full-test gradient boosting metrics are MAE 1.601 mph, RMSE 2.858 mph, R² 0.872. Persistence metrics are MAE 1.747 mph, RMSE 3.198 mph, R² 0.840. The MAE reduction is 8.4%.
3. Saved full-test metrics by direction, month, hour, day type, station, target-speed band, and speed-change size in `i5_d12_forecast_error_subgroups.csv`; saved 100 largest misses in `i5_d12_forecast_largest_errors.csv`.
4. The model is weaker on low speeds: for targets below 30 mph, model MAE is 6.47 mph versus 5.02 mph for persistence; for 30–50 mph they are effectively tied (6.12 vs 6.14 mph). Hourly MAE peaks at 2.06 mph around 17:00, while weekend MAE is lower than weekday MAE (1.34 vs 1.74 mph).
5. Largest misses commonly occur during rapid changes. For target speeds differing from current speed by more than 15 mph (17,244 windows), model MAE is 16.89 mph vs 21.10 mph for persistence. The largest single error in the top-100 table is 63.1 mph at southbound station 1204886 on July 16, during a 14.9-to-82.4 mph rise over 15 minutes despite 100% observed. This may be an abrupt traffic recovery or a detector/aggregation issue and merits review; percent observed alone does not distinguish these causes.
6. Reviewed the forecast alignment: features use measurements at t and earlier, target is t+15, complete five-minute intervals are required, and target-time measurements are not used as predictors. Target-speed and speed-change bands are descriptive error strata, not congestion labels.
7. Summary is `i5_d12_forecast_error_review.md`; full eligible holdout evaluation and error review are complete. Congestion-label definition and classification remain pending.
