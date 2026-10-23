"""Streaming 5/10/15-minute alignment and exploratory low-speed episode EDA."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "d12_i5_2026-01_to_2026-09"
OUT = ROOT / "reports" / "eda" / "overview"
KEYS = ["station_id", "direction", "lane_type"]
THRESHOLDS = (30, 40, 50)


def alignment_for_file(path: Path) -> list[dict]:
    history: dict[pd.Timestamp, set[tuple]] = {}
    previous_tail = pd.DataFrame()
    eligible = 0
    matched = {5: 0, 10: 0, 15: 0}

    def consume(frame: pd.DataFrame) -> None:
        nonlocal eligible
        if frame.empty:
            return
        for stamp, group in frame.groupby("timestamp", sort=False):
            current = set(zip(group["station_id"], group["direction"], group["lane_type"]))
            eligible += len(current)
            for lag in matched:
                matched[lag] += len(current.intersection(history.get(stamp - pd.Timedelta(minutes=lag), set())))
            history[stamp] = current
            cutoff = stamp - pd.Timedelta(minutes=15)
            for old in [t for t in history if t < cutoff]:
                del history[old]

    for chunk in pd.read_csv(path, usecols=["timestamp", *KEYS], compression="gzip", chunksize=300_000):
        chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], format="%m/%d/%Y %H:%M:%S", errors="coerce")
        if not previous_tail.empty:
            chunk = pd.concat([previous_tail, chunk], ignore_index=True)
        chunk = chunk.dropna(subset=["timestamp"])
        if chunk.empty:
            previous_tail = chunk
            continue
        last_stamp = chunk["timestamp"].iloc[-1]
        consume(chunk.loc[chunk["timestamp"] < last_stamp])
        previous_tail = chunk.loc[chunk["timestamp"].eq(last_stamp)].copy()
    consume(previous_tail)
    month = path.name[-14:-7]
    rows = []
    for lag in (5, 10, 15):
        rows.append({"month": month, "check": f"history_{lag}m", "requested_lag_minutes": lag,
                     "eligible_rows": eligible, "matched_rows": matched[lag],
                     "coverage_percent": 100 * matched[lag] / eligible if eligible else 0})
    rows.append({"month": month, "check": "future_15m", "requested_lag_minutes": 15,
                 "eligible_rows": eligible, "matched_rows": matched[15],
                 "coverage_percent": 100 * matched[15] / eligible if eligible else 0})
    return rows


def events_for_file(path: Path) -> list[dict]:
    parts = []
    cols = ["timestamp", *KEYS, "avg_speed"]
    for chunk in pd.read_csv(path, usecols=cols, compression="gzip", chunksize=300_000):
        speed = pd.to_numeric(chunk["avg_speed"], errors="coerce")
        low = chunk.loc[speed.le(max(THRESHOLDS)), cols].copy()
        low["avg_speed"] = speed.loc[low.index]
        low["timestamp"] = pd.to_datetime(low["timestamp"], format="%m/%d/%Y %H:%M:%S", errors="coerce")
        parts.append(low.dropna(subset=["timestamp", "avg_speed"]))
    if not parts:
        return []
    data = pd.concat(parts, ignore_index=True).sort_values(KEYS + ["timestamp"])
    month = path.name[-14:-7]
    results = []
    for threshold in THRESHOLDS:
        low = data.loc[data["avg_speed"].le(threshold)].copy()
        gap = low.groupby(KEYS, dropna=False)["timestamp"].diff()
        low["episode_start"] = gap.ne(pd.Timedelta(minutes=5))
        low["episode_id"] = low.groupby(KEYS, dropna=False)["episode_start"].cumsum()
        events = low.groupby(KEYS + ["episode_id"], dropna=False).agg(
            intervals=("timestamp", "size"), mean_speed=("avg_speed", "mean"),
            minimum_speed=("avg_speed", "min")).reset_index()
        duration = events["intervals"] * 5
        results.append({"month": month, "speed_threshold_mph": threshold,
            "episode_count": len(events), "episodes_15m_or_longer": int(duration.ge(15).sum()),
            "median_duration_minutes": float(duration.median()) if len(duration) else 0,
            "p90_duration_minutes": float(duration.quantile(.9)) if len(duration) else 0,
            "max_duration_minutes": int(duration.max()) if len(duration) else 0,
            "interpretation": "exploratory only; threshold is not a finalized project label"})
    return results


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_alignment, all_events = [], []
    for path in sorted(DATA.glob("i5_d12_station_5min_*.csv.gz")):
        all_alignment.extend(alignment_for_file(path))
        all_events.extend(events_for_file(path))
        print(f"Finished alignment and event diagnostics: {path.name[-14:-7]}", flush=True)
    pd.DataFrame(all_alignment).to_csv(OUT / "prediction_alignment_all_months.csv", index=False)
    pd.DataFrame(all_events).to_csv(OUT / "exploratory_episode_duration_sensitivity.csv", index=False)
    print(f"Diagnostics saved to {OUT}")


if __name__ == "__main__":
    main()
