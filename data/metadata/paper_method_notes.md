# Reference paper method notes

Source: Lopez-Garcia et al. (2016), *A Hybrid Method for Short-Term Traffic Congestion Forecasting Using Genetic Algorithms and Cross Entropy*.

## Study corridor and observations

- The paper describes a 9-km section of I-5 in Sacramento, California (paper p. 562, Figure 7).
- Figure 7 labels 13 mainline detector points S1-S13 and ramp sensors OR/IR. It is a schematic and does not provide PeMS station IDs or postmiles, so it is not sufficient by itself to map these points to current station inventory records.
- The observations cover September 1-30, 2013 at five-minute intervals (paper p. 562).
- The paper reports flow, occupancy, and speed on mainline sensors, and flow only on ramp sensors. It describes sensor speed in miles per hour (paper p. 562).
- The paper forms four dataset types: point and simplified point targets at middle sensor S7, and section and simplified section targets using maximum congestion on the mainline segment (paper pp. 562-563).

## Congestion table as printed

Table II (paper p. 562) gives the following classification intervals:

| State | Traffic density (vehicles/km/lane) | Vehicle speed (km/h) |
|---|---:|---:|
| Slight | 29-37 | 48-80 |
| Moderate | 37-50 | 24-64 |
| Severe | Greater than 50 | Less than 40 |
| Free | Other cases | Not specified separately |

The table's intervals meet or overlap at boundaries, and the table/caption alone does not document precedence for a boundary case. Its speed ranges also overlap. The paper states that density is flow divided by speed and that the PeMS measurements are not directly reported as density. It describes mainline speed in mph while Table II uses km/h and density in vehicles/km/lane; flow is described as vehicle counts collected every five minutes. The precise conversion/normalization used before applying Table II must be verified before implementing these labels. Do not directly apply these thresholds to raw exports without resolving time interval, lane, and unit conventions.

## Forecasting design described by the paper

- Forecast horizons: 5, 15, and 30 minutes (one, three, and six five-minute intervals).
- Congestion is treated as a classification target with four ordered states.
- The paper's method is a hierarchical fuzzy-rule-based system optimized with a Genetic Algorithm/Cross-Entropy hybrid (GACE); this project proposal instead plans persistence, Logistic Regression, and Random Forest comparisons.
- The paper describes random 10-fold cross-validation and a training-set reduction procedure. The current project plans chronological splits, so it is an adaptation rather than an exact replication.

