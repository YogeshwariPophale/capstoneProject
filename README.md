# I-5 Traffic Congestion Analysis and Short-Term Prediction

This project uses Caltrans PeMS Station 5-Minute observations. The current working dataset is **District 12, freeway 5 (I-5), both N and S directions, January 1–September 30, 2026**, with all lane/station types retained at this acquisition stage. The district daily source files cover District 12 roads generally; the reproducible processing script filters them to I-5.

## Current phase: build the I-5/D12 analysis input

- Raw daily text files are preserved unchanged in `data/raw/d12/2026-01-01_to_2026-09-30/`.
- Run `scripts/build_i5_d12_dataset.py` to produce monthly compressed CSVs in `data/processed/d12_i5_2026-01_to_2026-09/`.
- `manifest.json` records the input file/date coverage, row counts, output sizes, station counts, filtering choices, and malformed-row examples.
- The provided 235 files cover 235 of 273 calendar days in the requested window; missing dates are listed in the manifest. Those gaps indicate what is missing from this local collection, not necessarily what PeMS offers.
- Keep data in CSV.GZ for analysis; Excel is unnecessary and cannot hold this volume in one worksheet.

Run the filter from the project root with the bundled or local Python 3:

```powershell
python scripts/build_i5_d12_dataset.py `
  --input data/raw/d12/2026-01-01_to_2026-09-30 `
  --output data/processed/d12_i5_2026-01_to_2026-09 `
  --start 2026-01-01 --end 2026-09-30
```

See `data/metadata/acquisition_log.md` for the chronological record of scope decisions, input history, and processing. See `data/metadata/acquisition_checklist.md` for the next validation and EDA work.

## Project layout

- `data/raw/` - unchanged PeMS exports; avoid committing large raw files.
- `data/processed/` - reproducible derived datasets, partitioned by month.
- `data/metadata/` - provenance, coverage, and acquisition notes.
- `scripts/build_i5_d12_dataset.py` - repeatable District 12 I-5 filter and manifest generator.
- `scripts/eda_i5_d12.py` - selectable-slice EDA functions for prepared or raw station files.
- `scripts/inventory_pems.py` - read-only inventory for CSV, CSV.GZ, and zipped CSV exports.
- `reports/` - inventory outputs and figures.
- `report/progress_report.md` - progress report draft scaffold.
- `data/metadata/paper_method_notes.md` - method details from the reference paper.

Start the EDA from the project root:

```powershell
python scripts/eda_i5_d12.py
```

Select one month or day so EDA stays scoped to the dataset slice you want:

```powershell
python scripts/eda_i5_d12.py --month 2026-03
python scripts/eda_i5_d12.py --date 2026-03-08
python scripts/eda_i5_d12.py --source raw --date 2026-03-08
```

With no selector, the script opens a file picker for one file. It includes reusable functions for quality/missingness, direction and time patterns, flow-speed-occupancy relationships, station hotspots, sampling gaps, adjacent-station lag analysis, and (when an explicit threshold is supplied) congestion episodes. Add `--prediction-check` to assess 5/10/15-minute timestamp alignment for the selected slice. A station metadata file can be supplied with `--metadata-file` for maps and postmile-ordered analysis; plots are optional via `--plots` and require Matplotlib (`python -m pip install matplotlib`). Results go to a selection-specific subfolder under `reports/eda/`. The full nine-month dataset is not selected by default.

## Research reference

Lopez-Garcia, P., Onieva, E., Osaba, E., Masegosa, A. D., & Perallos, A. (2016). “A Hybrid Method for Short-Term Traffic Congestion Forecasting Using Genetic Algorithms and Cross Entropy.” *IEEE Transactions on Intelligent Transportation Systems*, 17(2), 557-567. https://doi.org/10.1109/TITS.2015.2491365
