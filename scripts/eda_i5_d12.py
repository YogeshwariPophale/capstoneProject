"""Reusable EDA for a selected I-5 / District 12 PeMS data slice.

Choose one month, one day, or one input file. This module does not load or run
EDA over the full nine-month collection unless individual months are selected
one at a time. All EDA functions accept a pandas DataFrame so they can also be
used interactively in a notebook.

Examples from the project root:
    python scripts/eda_i5_d12.py --month 2026-03
    python scripts/eda_i5_d12.py --date 2026-03-08
    python scripts/eda_i5_d12.py --file i5_d12_station_5min_2026-03.csv.gz
    python scripts/eda_i5_d12.py --source raw --date 2026-03-08

With no selection option, a file picker opens for one file. The proposal calls
for direction/time comparisons, congestion hotspots and duration, relationships
among speed/flow/occupancy, and a later 15-minute prediction task. A congestion
threshold is intentionally required as an argument because the proposal has
not yet established the project label rule; the reference paper's thresholds
have unit and boundary ambiguities noted in data/metadata/paper_method_notes.md.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterator, Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "d12_i5_2026-01_to_2026-09"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "reports" / "eda"

BASE_COLUMNS = [
    "timestamp", "station_id", "district", "freeway", "direction", "lane_type",
    "station_length", "samples", "percent_observed", "total_flow",
    "avg_occupancy", "avg_speed",
]
LANE_COLUMNS = [f"lane_{lane}_{field}" for lane in range(1, 11)
                for field in ("samples", "flow", "avg_occupancy", "avg_speed")]
PEMS_COLUMNS = BASE_COLUMNS + LANE_COLUMNS
METADATA_COLUMNS = [
    "station_id", "freeway", "direction", "district", "county", "city",
    "postmile", "absolute_pm", "latitude", "longitude", "station_length",
    "station_type", "lanes", "name", "user_id_1", "user_id_2", "user_id_3", "user_id_4",
]
TRAFFIC_METRICS = ["total_flow", "avg_occupancy", "avg_speed"]
RAW_STATION_FILE = re.compile(r"station_5min", re.IGNORECASE)
RAW_DATE = re.compile(r"(\d{4})[_-](\d{2})[_-](\d{2})")
PROCESSED_MONTH = re.compile(r"(\d{4})-(\d{2})")


def find_processed_files(directory: Path = PROCESSED_DIR) -> list[Path]:
    """Return the prepared monthly I-5 files, sorted by month."""
    return sorted(directory.glob("i5_d12_station_5min_*.csv.gz"))


def find_i5_raw_files(raw_root: Path = RAW_DIR) -> list[Path]:
    """Find raw PeMS station 5-minute data files; metadata files are excluded."""
    supported = {".txt", ".csv", ".gz"}
    return sorted(
        path for path in raw_root.rglob("*")
        if path.is_file() and path.suffix.lower() in supported
        and RAW_STATION_FILE.search(path.name)
    )


def _choose_file_with_dialog(source: str, directory: Path) -> Path:
    """Open a single-file picker when no month/day/file was provided."""
    try:
        from tkinter import Tk, filedialog
    except ImportError as exc:
        raise RuntimeError("File picker unavailable; pass --month, --date, or --file.") from exc
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    patterns = "*.csv.gz" if source == "processed" else "*.txt *.txt.gz *.csv *.csv.gz"
    chosen = filedialog.askopenfilename(
        title=f"Choose one {source} PeMS Station 5-Minute file",
        initialdir=str(directory),
        filetypes=[("PeMS station data", patterns), ("All files", "*.*")],
    )
    root.destroy()
    if not chosen:
        raise SystemExit("No file selected; no EDA was run.")
    return Path(chosen)


def select_input_files(
    source: str = "processed",
    month: str | None = None,
    day: str | None = None,
    file_path: str | Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
    raw_root: Path = RAW_DIR,
) -> list[Path]:
    """Select one month, one day, or one file from processed or raw data.

    For processed data, --date reads the matching month's file and filters to
    that date. For raw data, --date selects the matching daily source file.
    A raw month selects the available daily files in that month.
    """
    if source not in {"processed", "raw"}:
        raise ValueError("source must be 'processed' or 'raw'")
    if sum(value is not None for value in (month, day, file_path)) > 1:
        raise ValueError("Choose only one of month, day, or file_path")
    directory = processed_dir if source == "processed" else raw_root

    if file_path is not None:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = directory / candidate
        if not candidate.is_file():
            raise FileNotFoundError(f"Selected input file does not exist: {candidate}")
        return [candidate]

    if day is not None:
        target = pd.Timestamp(day).strftime("%Y-%m-%d")
        if source == "processed":
            month_key = target[:7]
            paths = [p for p in find_processed_files(processed_dir) if month_key in p.name]
        else:
            paths = [p for p in find_i5_raw_files(raw_root)
                     if (match := RAW_DATE.search(p.name))
                     and "-".join(match.groups()) == target]
        if not paths:
            raise FileNotFoundError(f"No {source} PeMS input found for {target}")
        return paths

    if month is not None:
        if not PROCESSED_MONTH.fullmatch(month):
            raise ValueError("month must use YYYY-MM format, such as 2026-03")
        if source == "processed":
            paths = [p for p in find_processed_files(processed_dir) if month in p.name]
        else:
            paths = [p for p in find_i5_raw_files(raw_root)
                     if (match := RAW_DATE.search(p.name))
                     and f"{match.group(1)}-{match.group(2)}" == month]
        if not paths:
            raise FileNotFoundError(f"No {source} PeMS inputs found for {month}")
        return paths

    picked = _choose_file_with_dialog(source, directory)
    return [picked]


def iter_selected_chunks(
    files: Sequence[Path],
    source: str = "processed",
    district: int = 12,
    freeway: int = 5,
    directions: Sequence[str] = ("N", "S"),
    day: str | None = None,
    lane_types: Sequence[str] | None = None,
    chunksize: int = 250_000,
) -> Iterator[pd.DataFrame]:
    """Yield only selected I-5 records from the chosen input file(s)."""
    direction_set = {direction.upper() for direction in directions}
    lane_set = {lane.upper() for lane in lane_types} if lane_types else None
    target_day = pd.Timestamp(day).date() if day else None

    for path in files:
        if source == "processed":
            reader = pd.read_csv(path, compression="gzip", chunksize=chunksize)
        else:
            reader = pd.read_csv(
                path, header=None, names=PEMS_COLUMNS, compression="infer",
                chunksize=chunksize, low_memory=False,
            )
        for chunk in reader:
            chunk["district"] = pd.to_numeric(chunk["district"], errors="coerce")
            chunk["freeway"] = pd.to_numeric(chunk["freeway"], errors="coerce")
            chunk["direction"] = chunk["direction"].astype("string").str.strip().str.upper()
            keep = (
                chunk["district"].eq(district)
                & chunk["freeway"].eq(freeway)
                & chunk["direction"].isin(direction_set)
            )
            if lane_set is not None:
                keep &= chunk["lane_type"].astype("string").str.strip().str.upper().isin(lane_set)
            chunk = chunk.loc[keep].copy()
            if chunk.empty:
                continue
            chunk["timestamp"] = pd.to_datetime(
                chunk["timestamp"], format="%m/%d/%Y %H:%M:%S", errors="coerce"
            )
            if target_day is not None:
                chunk = chunk.loc[chunk["timestamp"].dt.date.eq(target_day)].copy()
            if not chunk.empty:
                chunk["source_file"] = path.name
                yield add_time_features(chunk)


def load_selected_data(
    files: Sequence[Path],
    source: str = "processed",
    district: int = 12,
    freeway: int = 5,
    directions: Sequence[str] = ("N", "S"),
    day: str | None = None,
    lane_types: Sequence[str] | None = None,
    chunksize: int = 250_000,
) -> pd.DataFrame:
    """Load the chosen slice, reading source files in chunks first.

    Select one day for the lightest memory use. A month is supported, but it
    can contain several million rows. This function never selects all months
    unless the caller explicitly passes files spanning all months.
    """
    parts = list(iter_selected_chunks(
        files, source=source, district=district, freeway=freeway,
        directions=directions, day=day, lane_types=lane_types, chunksize=chunksize,
    ))
    if not parts:
        raise ValueError("The selection contains no matching I-5 records.")
    return pd.concat(parts, ignore_index=True, copy=False)


def add_time_features(data: pd.DataFrame) -> pd.DataFrame:
    """Add hour, weekday/weekend, and meteorological season columns."""
    result = data.copy()
    if not pd.api.types.is_datetime64_any_dtype(result["timestamp"]):
        result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
    result["hour"] = result["timestamp"].dt.hour
    result["weekday"] = result["timestamp"].dt.day_name()
    result["is_weekend"] = result["timestamp"].dt.dayofweek >= 5
    result["month"] = result["timestamp"].dt.month
    result["season"] = result["month"].map({
        12: "Winter", 1: "Winter", 2: "Winter",
        3: "Spring", 4: "Spring", 5: "Spring",
        6: "Summer", 7: "Summer", 8: "Summer",
        9: "Fall", 10: "Fall", 11: "Fall",
    })
    return result


def data_quality_summary(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return dataset-level checks and per-column missingness/invalid counts."""
    keys = [key for key in ("timestamp", "station_id", "direction", "lane_type") if key in data]
    duplicate_count = int(data.duplicated(keys).sum()) if keys else 0
    overview = pd.DataFrame([{
        "rows": len(data),
        "columns": len(data.columns),
        "stations": data["station_id"].nunique(dropna=True),
        "start_time": data["timestamp"].min(),
        "end_time": data["timestamp"].max(),
        "duplicate_station_time_type_rows": duplicate_count,
    }])
    checks = []
    for col in data.columns:
        if col == "source_file":
            continue
        missing = int(data[col].isna().sum())
        numeric = pd.to_numeric(data[col], errors="coerce")
        negative = int(numeric.lt(0).sum()) if col in {
            "total_flow", "avg_occupancy", "avg_speed", "percent_observed", "samples"
        } else 0
        checks.append({"column": col, "missing_count": missing,
                       "missing_percent": 100 * missing / max(len(data), 1),
                       "negative_value_count": negative})
    return overview, pd.DataFrame(checks)


def temporal_pattern_summary(data: pd.DataFrame) -> pd.DataFrame:
    """Summarize flow, occupancy, and speed by direction and time dimensions."""
    frame = add_time_features(data)
    groupings = [
        ["direction"], ["hour"], ["weekday"], ["is_weekend"], ["season"],
        ["direction", "hour"], ["direction", "is_weekend"],
    ]
    outputs = []
    for grouping in groupings:
        present = [key for key in grouping if key in frame]
        if not present:
            continue
        grouped = frame.groupby(present, dropna=False).agg(
            observations=("timestamp", "size"),
            avg_flow=("total_flow", "mean"),
            avg_occupancy=("avg_occupancy", "mean"),
            avg_speed=("avg_speed", "mean"),
        ).reset_index()
        grouped.insert(0, "grouping", " + ".join(present))
        outputs.append(grouped.rename(columns={key: "group_" + key for key in present}))
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()


def traffic_relationships(data: pd.DataFrame) -> pd.DataFrame:
    """Return pairwise correlations among flow, average occupancy, and speed."""
    metrics = [name for name in TRAFFIC_METRICS if name in data]
    numeric = data[metrics].apply(pd.to_numeric, errors="coerce")
    return numeric.corr(method="pearson").rename_axis("metric").reset_index()


def station_hotspots(
    data: pd.DataFrame, speed_threshold_mph: float | None = None
) -> pd.DataFrame:
    """Rank station/direction/type combinations by speed and optional low-speed rate.

    The project congestion threshold has not been finalized. Pass one explicitly
    to calculate the proportion of observations at or below that speed.
    """
    keys = [key for key in ("station_id", "direction", "lane_type") if key in data]
    frame = data.copy()
    frame["avg_speed"] = pd.to_numeric(frame["avg_speed"], errors="coerce")
    result = frame.groupby(keys, dropna=False).agg(
        observations=("avg_speed", "count"), mean_speed=("avg_speed", "mean"),
        median_speed=("avg_speed", "median"), min_speed=("avg_speed", "min"),
    ).reset_index()
    if speed_threshold_mph is not None:
        frame["below_threshold"] = frame["avg_speed"].le(speed_threshold_mph)
        below = frame.groupby(keys, dropna=False)["below_threshold"].agg(["sum", "mean"]).reset_index()
        below = below.rename(columns={"sum": "low_speed_observations", "mean": "low_speed_rate"})
        result = result.merge(below, on=keys, how="left")
    return result.sort_values("mean_speed", ascending=True).reset_index(drop=True)


def sampling_gap_summary(
    data: pd.DataFrame, expected_interval_minutes: int = 5
) -> pd.DataFrame:
    """Count timestamp gaps within each station/direction/type series."""
    keys = [key for key in ("station_id", "direction", "lane_type") if key in data]
    rows = []
    for values, group in data.sort_values(keys + ["timestamp"]).groupby(keys, dropna=False):
        if not isinstance(values, tuple):
            values = (values,)
        times = group["timestamp"].dropna().drop_duplicates().sort_values()
        deltas = times.diff().dt.total_seconds().div(60).dropna()
        gap_deltas = deltas[deltas > expected_interval_minutes]
        missing = ((gap_deltas / expected_interval_minutes).round().astype(int) - 1).clip(lower=0)
        rows.append({
            **dict(zip(keys, values)),
            "observed_timestamps": len(times),
            "gap_count": int(len(gap_deltas)),
            "estimated_missing_intervals": int(missing.sum()),
            "largest_gap_minutes": float(gap_deltas.max()) if not gap_deltas.empty else 0.0,
        })
    return pd.DataFrame(rows)


def congestion_events(
    data: pd.DataFrame,
    speed_threshold_mph: float,
    max_gap_minutes: int = 5,
) -> pd.DataFrame:
    """Find contiguous low-speed episodes, using an explicit mph threshold.

    Duration is the number of consecutive observed five-minute intervals. A
    time gap greater than max_gap_minutes starts a new event. This is a
    parameterized project rule, not the paper's unresolved four-class label.
    """
    keys = [key for key in ("station_id", "direction", "lane_type") if key in data]
    frame = data.copy()
    frame["avg_speed"] = pd.to_numeric(frame["avg_speed"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "avg_speed"]).sort_values(keys + ["timestamp"])
    frame["is_low_speed"] = frame["avg_speed"].le(speed_threshold_mph)
    grouped = frame.groupby(keys, dropna=False, sort=False)
    previous_state = grouped["is_low_speed"].shift(fill_value=False)
    elapsed = grouped["timestamp"].diff().dt.total_seconds().div(60)
    frame["event_start"] = frame["is_low_speed"] & (
        ~previous_state | elapsed.gt(max_gap_minutes)
    )
    frame["event_number"] = frame.groupby(keys, dropna=False, sort=False)["event_start"].cumsum()
    low = frame.loc[frame["is_low_speed"]].copy()
    event_keys = keys + ["event_number"]
    events = low.groupby(event_keys, dropna=False).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        intervals=("timestamp", "size"),
        mean_speed=("avg_speed", "mean"),
        min_speed=("avg_speed", "min"),
    ).reset_index()
    events["duration_minutes"] = events["intervals"] * 5
    return events.sort_values("start_time").reset_index(drop=True)


def prediction_alignment_summary(
    data: pd.DataFrame,
    horizon_minutes: int = 15,
    history_lags_minutes: Sequence[int] = (5, 10, 15),
) -> pd.DataFrame:
    """Check exact-time coverage for proposal-style future targets and lag features.

    This does not train a model or define congestion labels. It only checks
    whether each selected observation has matching earlier measurements and a
    future observation at the requested horizon, reducing timestamp leakage.
    """
    keys = [key for key in ("station_id", "direction", "lane_type") if key in data]
    base_columns = keys + ["timestamp"]
    unique = data[base_columns].dropna(subset=["timestamp"]).drop_duplicates().copy()
    future = unique[keys + ["timestamp"]].copy()
    future["timestamp"] -= pd.Timedelta(minutes=horizon_minutes)
    future["future_match"] = True
    aligned = unique.merge(future, on=keys + ["timestamp"], how="left", validate="one_to_one")
    rows = [{
        "check": f"future_{horizon_minutes}m",
        "requested_lag_minutes": horizon_minutes,
        "eligible_rows": len(unique),
        "matched_rows": int(aligned["future_match"].fillna(False).sum()),
        "coverage_percent": 100 * float(aligned["future_match"].fillna(False).mean()) if len(aligned) else 0.0,
    }]
    for lag in history_lags_minutes:
        lagged = unique[keys + ["timestamp"]].copy()
        lagged["timestamp"] += pd.Timedelta(minutes=lag)
        lagged["lag_match"] = True
        matched = unique.merge(lagged, on=keys + ["timestamp"], how="left", validate="one_to_one")
        rows.append({
            "check": f"history_{lag}m",
            "requested_lag_minutes": lag,
            "eligible_rows": len(unique),
            "matched_rows": int(matched["lag_match"].fillna(False).sum()),
            "coverage_percent": 100 * float(matched["lag_match"].fillna(False).mean()) if len(matched) else 0.0,
        })
    return pd.DataFrame(rows)


def speed_severity_summary(
    data: pd.DataFrame, speed_bands_mph: dict[str, tuple[float, float]]
) -> pd.DataFrame:
    """Count speed observations in caller-defined bands; no thresholds assumed."""
    frame = data.copy()
    frame["avg_speed"] = pd.to_numeric(frame["avg_speed"], errors="coerce")
    frame["speed_band"] = pd.NA
    for label, (lower, upper) in speed_bands_mph.items():
        in_band = frame["avg_speed"].ge(lower) & frame["avg_speed"].lt(upper)
        frame.loc[in_band, "speed_band"] = label
    keys = [key for key in ("direction", "lane_type", "speed_band") if key in frame]
    counts = frame.dropna(subset=["speed_band"]).groupby(keys).size().rename("observations").reset_index()
    if counts.empty:
        return counts
    counts["percent"] = 100 * counts["observations"] / counts["observations"].sum()
    return counts


def load_station_metadata(metadata: pd.DataFrame | str | Path) -> pd.DataFrame:
    """Load PeMS station metadata and normalize its common field-name variants.

    Supports a headered PeMS metadata file or a headerless 18-field export.
    """
    if isinstance(metadata, pd.DataFrame):
        frame = metadata.copy()
    else:
        path = Path(metadata)
        frame = pd.read_csv(path, compression="infer", low_memory=False)
        normalized = {re.sub(r"[^a-z0-9]", "", str(c).lower()): c for c in frame.columns}
        if not any(name in normalized for name in ("id", "stationid", "station")):
            frame = pd.read_csv(path, header=None, names=METADATA_COLUMNS,
                                compression="infer", low_memory=False)
    aliases = {
        "id": "station_id", "stationid": "station_id", "station": "station_id",
        "fwy": "freeway", "dir": "direction", "statepm": "postmile",
        "statemilepost": "postmile", "abspm": "absolute_pm", "lat": "latitude",
        "lon": "longitude", "long": "longitude", "type": "station_type",
        "length": "station_length",
    }
    rename = {}
    for column in frame.columns:
        key = re.sub(r"[^a-z0-9]", "", str(column).lower())
        rename[column] = aliases.get(key, key)
    frame = frame.rename(columns=rename)
    if "station_id" not in frame:
        raise ValueError("Metadata file needs an ID/Station ID field.")
    frame["station_id"] = frame["station_id"].astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    for column in ("postmile", "absolute_pm", "latitude", "longitude"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.drop_duplicates("station_id", keep="last").reset_index(drop=True)


def merge_station_metadata(data: pd.DataFrame, metadata: pd.DataFrame | str | Path) -> pd.DataFrame:
    """Attach available location/type metadata to records by station ID."""
    stations = load_station_metadata(metadata)
    left = data.copy()
    left["station_id"] = left["station_id"].astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    keep = [column for column in stations.columns if column == "station_id" or column not in left.columns]
    return left.merge(stations[keep], on="station_id", how="left", validate="many_to_one")


def adjacent_station_lag_correlations(
    data: pd.DataFrame,
    metadata: pd.DataFrame | str | Path,
    metric: str = "avg_speed",
    max_lag_intervals: int = 6,
    min_pairs: int = 30,
) -> pd.DataFrame:
    """Compare time-shifted measurements at adjacent postmile-ordered stations.

    Positive lag means the second station's value is compared at a later time
    than the first station's. This is a descriptive association, not causation.
    """
    stations = load_station_metadata(metadata)
    if "postmile" not in stations:
        raise ValueError("Station metadata needs State PM/postmile for route ordering.")
    if metric not in data:
        raise ValueError(f"Metric not found in selected data: {metric}")
    station_order = stations.dropna(subset=["postmile"])[["station_id", "postmile"]]
    frame = data.copy()
    frame["station_id"] = frame["station_id"].astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    frame = frame.merge(station_order, on="station_id", how="inner")
    rows = []
    for direction, direction_frame in frame.groupby("direction", dropna=False):
        order = station_order.sort_values("postmile")["station_id"].tolist()
        observed = set(direction_frame["station_id"].dropna().astype(str))
        order = [station for station in order if station in observed]
        pivot = direction_frame.pivot_table(index="timestamp", columns="station_id",
                                            values=metric, aggfunc="mean").sort_index()
        for first_id, second_id in zip(order, order[1:]):
            first, second = pivot.get(first_id), pivot.get(second_id)
            if first is None or second is None:
                continue
            pm = station_order.set_index("station_id")["postmile"]
            for lag in range(-max_lag_intervals, max_lag_intervals + 1):
                paired = pd.concat([first.rename("first"), second.shift(-lag).rename("second")], axis=1).dropna()
                if len(paired) < min_pairs:
                    continue
                rows.append({
                    "direction": direction,
                    "first_station_id": first_id,
                    "first_postmile": pm.get(first_id),
                    "second_station_id": second_id,
                    "second_postmile": pm.get(second_id),
                    "lag_intervals": lag,
                    "lag_minutes": lag * 5,
                    "paired_observations": len(paired),
                    "correlation": paired["first"].corr(paired["second"]),
                })
    return pd.DataFrame(rows)


def _pyplot():
    """Import plotting library only when a plot is requested."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Plot functions require matplotlib. Install it with: python -m pip install matplotlib") from exc
    return plt


def plot_daily_profiles(data: pd.DataFrame, output_path: str | Path) -> None:
    """Plot hourly flow, occupancy, and speed profiles by direction."""
    plt = _pyplot()
    frame = add_time_features(data)
    metrics = [("total_flow", "Mean five-minute flow"),
               ("avg_occupancy", "Mean occupancy"), ("avg_speed", "Mean speed (mph)")]
    fig, axes = plt.subplots(3, 1, figsize=(11, 12), sharex=True)
    for ax, (metric, label) in zip(axes, metrics):
        profile = frame.groupby(["direction", "hour"], dropna=False)[metric].mean().reset_index()
        for direction, series in profile.groupby("direction"):
            ax.plot(series["hour"], series[metric], marker="o", label=str(direction))
        ax.set_ylabel(label)
        ax.grid(alpha=0.25)
        ax.legend(title="Direction")
    axes[-1].set_xlabel("Hour of day")
    axes[-1].set_xticks(range(0, 24, 2))
    fig.suptitle("Selected I-5 Slice: Hourly Traffic Profiles")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_traffic_relationships(
    data: pd.DataFrame, output_path: str | Path, max_points: int = 30_000
) -> None:
    """Plot speed-flow and speed-occupancy relationships on a bounded sample."""
    plt = _pyplot()
    fields = ["avg_speed", "total_flow", "avg_occupancy"]
    frame = data[fields].apply(pd.to_numeric, errors="coerce").dropna()
    if len(frame) > max_points:
        frame = frame.sample(max_points, random_state=42)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    points = axes[0].scatter(frame["total_flow"], frame["avg_speed"],
                             c=frame["avg_occupancy"], s=8, alpha=0.35, cmap="viridis")
    axes[0].set(xlabel="Total flow", ylabel="Average speed (mph)", title="Speed vs flow")
    fig.colorbar(points, ax=axes[0], label="Average occupancy")
    points = axes[1].scatter(frame["avg_occupancy"], frame["avg_speed"],
                             c=frame["total_flow"], s=8, alpha=0.35, cmap="plasma")
    axes[1].set(xlabel="Average occupancy", ylabel="Average speed (mph)", title="Speed vs occupancy")
    fig.colorbar(points, ax=axes[1], label="Total flow")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_data_quality(data: pd.DataFrame, output_path: str | Path) -> None:
    """Plot missing traffic values by field and record volume by date."""
    plt = _pyplot()
    metrics = [column for column in TRAFFIC_METRICS if column in data]
    missing_pct = data[metrics].isna().mean().mul(100).sort_values()
    daily_rows = data.groupby(data["timestamp"].dt.date).size()
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    axes[0].bar(missing_pct.index, missing_pct.values)
    axes[0].set_ylabel("Missing values (%)")
    axes[0].set_title("Traffic-field missingness")
    axes[0].tick_params(axis="x", rotation=25)
    axes[1].plot(pd.to_datetime(daily_rows.index), daily_rows.values, marker=".")
    axes[1].set_ylabel("Records")
    axes[1].set_title("Records by date")
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_station_map(
    data: pd.DataFrame, metadata: pd.DataFrame | str | Path, output_path: str | Path
) -> None:
    """Plot selected stations by latitude/longitude, colored by mean speed."""
    plt = _pyplot()
    stations = load_station_metadata(metadata)
    if not {"latitude", "longitude"}.issubset(stations.columns):
        raise ValueError("Station metadata needs Latitude and Longitude for the map.")
    means = data.groupby(["station_id", "direction"], dropna=False)["avg_speed"].mean().reset_index()
    means["station_id"] = means["station_id"].astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    coordinate_columns = [column for column in ("station_id", "latitude", "longitude")
                          if column in stations]
    mapped = means.merge(stations[coordinate_columns], on="station_id", how="inner")
    mapped = mapped.dropna(subset=["latitude", "longitude"])
    if mapped.empty:
        raise ValueError("No selected station IDs matched metadata coordinates.")
    fig, ax = plt.subplots(figsize=(8, 10))
    for direction, group in mapped.groupby("direction"):
        points = ax.scatter(group["longitude"], group["latitude"], c=group["avg_speed"],
                            s=24, alpha=0.8, label=str(direction), cmap="viridis")
    fig.colorbar(points, ax=ax, label="Mean speed (mph)")
    ax.set(xlabel="Longitude", ylabel="Latitude", title="Selected I-5 Stations by Mean Speed")
    ax.legend(title="Direction")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_speed_space_time(
    data: pd.DataFrame, metadata: pd.DataFrame | str | Path, output_path: str | Path
) -> None:
    """Plot a time-by-postmile speed heatmap for each direction."""
    plt = _pyplot()
    stations = load_station_metadata(metadata)
    if "postmile" not in stations:
        raise ValueError("Station metadata needs State PM/postmile for spatial ordering.")
    frame = data.copy()
    frame["station_id"] = frame["station_id"].astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    frame["avg_speed"] = pd.to_numeric(frame["avg_speed"], errors="coerce")
    frame = frame.merge(stations[["station_id", "postmile"]].dropna(), on="station_id", how="inner")
    directions = list(frame["direction"].dropna().unique())
    if not directions:
        raise ValueError("No station postmiles matched the selected data.")
    fig, axes = plt.subplots(len(directions), 1, figsize=(14, max(4, 3.5 * len(directions))), squeeze=False)
    for ax, direction in zip(axes[:, 0], directions):
        part = frame.loc[frame["direction"] == direction]
        station_order = (part[["station_id", "postmile"]].drop_duplicates()
                         .sort_values("postmile")["station_id"].tolist())
        matrix = part.pivot_table(index="timestamp", columns="station_id", values="avg_speed", aggfunc="mean")
        matrix = matrix.sort_index().reindex(columns=station_order)
        image = ax.imshow(matrix.to_numpy().T, aspect="auto", interpolation="nearest",
                          origin="lower", cmap="turbo", vmin=0, vmax=80)
        ax.set_ylabel(f"{direction} station order\n(low to high postmile)")
        ax.set_title(f"Direction {direction}")
        ax.set_yticks([])
        if len(matrix.index):
            ax.set_xticks([0, len(matrix.index) - 1])
            ax.set_xticklabels([str(matrix.index[0]), str(matrix.index[-1])], rotation=15)
    fig.colorbar(image, ax=axes.ravel().tolist(), label="Average speed (mph)", shrink=0.8)
    fig.suptitle("Speed by Time and Postmile-Ordered Station")
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_congestion_events(events: pd.DataFrame, output_path: str | Path) -> None:
    """Plot event duration distribution and event counts by start hour."""
    plt = _pyplot()
    if events.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No events found for the selected threshold and data slice.",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        fig.savefig(output_path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return
    frame = events.copy()
    frame["start_hour"] = pd.to_datetime(frame["start_time"]).dt.hour
    counts = frame.groupby(["direction", "start_hour"]).size().rename("events").reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].hist(frame["duration_minutes"], bins=30, color="steelblue")
    axes[0].set(xlabel="Duration (minutes)", ylabel="Event count", title="Low-speed event duration")
    for direction, group in counts.groupby("direction"):
        axes[1].plot(group["start_hour"], group["events"], marker="o", label=str(direction))
    axes[1].set(xlabel="Start hour", ylabel="Event count", title="Events by start hour")
    axes[1].legend(title="Direction")
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def run_selected_eda(
    data: pd.DataFrame,
    output_dir: Path,
    speed_threshold_mph: float | None = None,
    metadata: pd.DataFrame | str | Path | None = None,
    make_plots: bool = False,
    speed_bands_mph: dict[str, tuple[float, float]] | None = None,
    include_prediction_check: bool = False,
) -> dict[str, pd.DataFrame]:
    """Run and save proposal-aligned EDA tables for this selected slice only."""
    output_dir.mkdir(parents=True, exist_ok=True)
    overview, missingness = data_quality_summary(data)
    results = {
        "overview": overview,
        "missingness_and_quality": missingness,
        "temporal_patterns": temporal_pattern_summary(data),
        "traffic_relationships": traffic_relationships(data),
        "station_hotspots": station_hotspots(data, speed_threshold_mph),
        "sampling_gaps": sampling_gap_summary(data),
    }
    if speed_threshold_mph is not None:
        results["congestion_events"] = congestion_events(data, speed_threshold_mph)
    if speed_bands_mph:
        results["speed_severity"] = speed_severity_summary(data, speed_bands_mph)
    if include_prediction_check:
        results["prediction_alignment"] = prediction_alignment_summary(data)
    if metadata is not None:
        results["adjacent_station_lags"] = adjacent_station_lag_correlations(data, metadata)
    for name, table in results.items():
        table.to_csv(output_dir / f"{name}.csv", index=False)
    if make_plots:
        plot_daily_profiles(data, output_dir / "daily_profiles.png")
        plot_traffic_relationships(data, output_dir / "traffic_relationships.png")
        plot_data_quality(data, output_dir / "data_quality.png")
        if metadata is not None:
            plot_station_map(data, metadata, output_dir / "station_map.png")
            plot_speed_space_time(data, metadata, output_dir / "speed_space_time.png")
        if speed_threshold_mph is not None:
            plot_congestion_events(results["congestion_events"], output_dir / "congestion_events.png")
    return results


def _selection_name(source: str, files: Sequence[Path], day: str | None, month: str | None) -> str:
    if day:
        return f"{source}_{day}"
    if month:
        return f"{source}_{month}"
    if len(files) == 1:
        return f"{source}_{files[0].stem.replace('.', '_')}"
    return f"{source}_selected_files"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("processed", "raw"), default="processed")
    picker = parser.add_mutually_exclusive_group()
    picker.add_argument("--month", help="Select one month, YYYY-MM")
    picker.add_argument("--date", help="Select one day, YYYY-MM-DD")
    picker.add_argument("--file", dest="file_path", help="Select one file name or path")
    parser.add_argument("--chunksize", type=int, default=250_000)
    parser.add_argument("--district", type=int, default=12)
    parser.add_argument("--freeway", type=int, default=5)
    parser.add_argument("--speed-threshold-mph", type=float,
                        help="Optional project rule for low-speed rate and event duration")
    parser.add_argument("--metadata-file", type=Path,
                        help="Optional PeMS station metadata file for map/postmile analyses")
    parser.add_argument("--plots", action="store_true",
                        help="Create plots for the selected slice (requires matplotlib)")
    parser.add_argument("--prediction-check", action="store_true",
                        help="Check 5/10/15-minute timestamp alignment for the selected slice")
    args = parser.parse_args()

    files = select_input_files(source=args.source, month=args.month, day=args.date,
                               file_path=args.file_path)
    data = load_selected_data(
        files, source=args.source, district=args.district, freeway=args.freeway,
        day=args.date, chunksize=args.chunksize,
    )
    selection = _selection_name(args.source, files, args.date, args.month)
    output_dir = REPORT_DIR / selection
    result = run_selected_eda(data, output_dir, args.speed_threshold_mph,
                              metadata=args.metadata_file, make_plots=args.plots,
                              include_prediction_check=args.prediction_check)
    print(f"Selected input files: {len(files)}")
    for path in files:
        print(f"  {path}")
    print(f"Selected I-5 rows analyzed: {len(data):,}")
    print(f"EDA tables saved to: {output_dir}")
    print(f"Summary: {result['overview'].iloc[0].to_dict()}")


if __name__ == "__main__":
    main()
