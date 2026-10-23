# Progress Report: I-5 Traffic Congestion Analysis and Short-Term Prediction

**Student:** Yogeshwari Pophale  
**Program:** M.S. Computational Data Science, UC Riverside  
**Reporting date:** October 19, 2026  
**Submission deadline:** Confirm exact date and time with instructor

## Introduction

This project will analyze five-minute Caltrans PeMS observations from I-5 across California, including all districts and both directions. It will characterize statewide congestion patterns and compare northbound and southbound traffic by station and geographic segment, then evaluate whether current and recent measurements predict congestion 15 minutes ahead. The initial analysis window will be the latest complete 30 days available at retrieval, with a planned expansion toward six months if statewide coverage and export size allow.

## Prior Work

Lopez-Garcia et al. (2016) studied a 9-km Sacramento I-5 section using September 2013 PeMS data from 13 mainline sensors and eight ramp sensors. Their measurements were collected every five minutes. They classified traffic into free, slight, moderate, and severe states and predicted at 5-, 15-, and 30-minute horizons with a hierarchical fuzzy-rule system optimized by a Genetic Algorithm/Cross-Entropy hybrid. The current project uses this work to guide the temporal resolution and prediction horizon while planning simpler, reproducible baselines and directional analysis.

The paper's Figure 7 and Table II have been reviewed. The table gives density bands of 29-37, 37-50, and greater than 50 vehicles/km/lane for slight, moderate, and severe congestion; free flow is listed as the other cases. It also gives speed bands in km/h. The raw speed/flow units and five-minute aggregation must be reconciled before these labels can be applied.

## Dataset

The planned primary source is the Caltrans PeMS station data product. The user supplied a freeway 5 northbound station view; the study scope now covers all California I-5 stations in both directions without a district filter. District and postmile metadata will be retained to order and summarize the statewide route. The paper's 9-km Sacramento corridor remains a methodological reference and is not the geographic scope of this project.

**Acquisition status:** A pilot daily station file, `data/raw/d03_text_station_5min_2026_10_18.txt.gz`, was downloaded from the PeMS Clearinghouse on October 19, 2026. The source page listed it at 11,595,737 bytes. The compressed file opens as gzip and begins with comma-delimited five-minute observations (no header row); its field specification on PeMS identifies timestamps, station, district, freeway, direction, lane type, flow, occupancy, speed, and lane-level values. It covers all of District 3, so it must be filtered to freeway 5 and is not a statewide corridor dataset. The I-5 northbound station inventory export view displayed 1,114 stations across seven districts, but a local inventory file has not yet been saved; southbound coverage also remains to be inventoried. No statewide row counts, missingness, or prediction results are claimed. See `data/metadata/acquisition_log.md` for details and limits.

## Intended Tasks and Milestones

1. Save/verify route station inventories in both directions, then identify the districts traversed by each direction and retain location metadata.
2. Validate the D3 pilot's field positions, quality fields, I-5 station subset, and date completeness; use this to estimate the latest complete 30-day acquisition before expanding toward six months.
3. Inventory coverage, missingness, duplicates, and timestamp continuity before cleaning.
4. Compare speed, flow, and occupancy by direction, time of day, and weekday/weekend.
5. Define congestion labels from verified thresholds and report severity and duration.
6. Evaluate a persistence baseline and, when data support it, Logistic Regression and Random Forest for 15-minute-ahead prediction with chronological splits.

## Experiments and Results

No traffic-data experiments have been run. One district-day pilot has been acquired, but statewide I-5 station-day coverage has not. Results will be added only after the source files are inventoried and validated. The first analysis will report actual dates, stations, records, missingness, and units before presenting plots or model scores.

## Conclusion and Discussion

The research question and published reference are established. The geographic scope is statewide I-5, with both directions and no district filter. PeMS access and a small D3 pilot download are confirmed; the next dependency is validating the route station lists in both directions and choosing a corridor-wide acquisition that is manageable. Since the study covers a longer and broader period than the reference paper, it is an adaptation of the paper's methodology.

## Reference

Lopez-Garcia, P., Onieva, E., Osaba, E., Masegosa, A. D., & Perallos, A. (2016). A hybrid method for short-term traffic congestion forecasting using genetic algorithms and cross entropy. *IEEE Transactions on Intelligent Transportation Systems*, 17(2), 557-567. https://doi.org/10.1109/TITS.2015.2491365
