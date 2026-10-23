#!/usr/bin/env python3
"""Inventory PeMS-style CSV exports without changing source files.

Supports .csv, .csv.gz, and CSV members inside .zip archives. Column names are
matched using conservative aliases; unrecognized schemas are still inventoried.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import itertools
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, TextIO

ALIASES = {
    "timestamp": ("timestamp", "datetime", "date_time", "measurement_time", "time_stamp"),
    "station_id": ("station_id", "station", "detector_id", "detector", "stationid", "detectorid"),
    "direction": ("direction", "dir", "travel_direction"),
    "district": ("district", "district_id"),
    "freeway": ("freeway", "freeway_number", "freeway_#", "fwy"),
    "postmile": ("postmile", "post_mile", "milepost", "mile_marker"),
    "station_type": ("station_type", "lane_type", "detector_type", "type"),
    "flow": ("flow", "volume", "total_flow", "total_volume", "vehicles"),
    "speed": ("speed", "avg_speed", "average_speed", "mean_speed"),
    "occupancy": ("occupancy", "occ", "avg_occupancy", "average_occupancy"),
}

PEMS_5MIN_BASE_COLUMNS = [
    "timestamp", "station_id", "district", "freeway", "direction", "lane_type",
    "station_length", "samples", "percent_observed", "total_flow", "avg_occupancy", "avg_speed",
]


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def map_columns(headers: list[str]) -> dict[str, str]:
    normalized = {normalize(h): h for h in headers}
    result = {}
    for concept, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[concept] = normalized[alias]
                break
    # Some exports split the date and time into separate fields.
    if "timestamp" not in result:
        date_col = normalized.get("date")
        time_col = normalized.get("time_of_day") or normalized.get("time")
        if date_col and time_col:
            result["date"] = date_col
            result["time_of_day"] = time_col
    return result


def parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y%m%d %H:%M", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
    return None


def open_member(path: Path, member: str | None = None) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", errors="replace", newline="")
    if path.suffix.lower() == ".zip" and member:
        archive = zipfile.ZipFile(path)
        # The ZipExtFile stays valid while the TextIOWrapper is in use.
        return __import__("io").TextIOWrapper(archive.open(member), encoding="utf-8-sig", errors="replace", newline="")
    return path.open("r", encoding="utf-8-sig", errors="replace", newline="")


def sources(root: Path) -> Iterator[tuple[Path, str | None]]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in {".csv", ".gz"}:
            yield path, None
        elif suffix == ".zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if name.lower().endswith(".csv") and not name.endswith("/"):
                            yield path, name
            except zipfile.BadZipFile:
                continue


def inventory_file(path: Path, member: str | None, global_keys: set[tuple[str, str]], station_times: dict[str, set[datetime]], station_rows: Counter) -> dict:
    label = f"{path.as_posix()}::{member}" if member else path.as_posix()
    result = {"source": label, "bytes": path.stat().st_size, "rows": 0, "headers": [], "column_map": {},
              "missing_by_column": {}, "timestamp_parse_failures": 0, "duplicate_station_timestamp_rows": 0,
              "station_ids": [], "directions": [], "districts": [], "station_types": [], "date_min": None, "date_max": None, "status": "ok"}
    try:
        with open_member(path, member) as stream:
            raw_reader = csv.reader(stream)
            first_row = next(raw_reader, None)
            is_headerless_pems = bool(first_row and len(first_row) >= 12 and parse_timestamp(first_row[0]) is not None)
            if is_headerless_pems:
                lane_count = max(0, (len(first_row) - len(PEMS_5MIN_BASE_COLUMNS) + 3) // 4)
                headers = PEMS_5MIN_BASE_COLUMNS.copy()
                for lane in range(1, lane_count + 1):
                    headers.extend((f"lane_{lane}_samples", f"lane_{lane}_flow", f"lane_{lane}_avg_occupancy", f"lane_{lane}_avg_speed"))
                reader = csv.DictReader(itertools.chain([first_row], raw_reader), fieldnames=headers)
            else:
                reader = csv.DictReader(itertools.chain([first_row] if first_row else [], raw_reader))
                headers = reader.fieldnames or []
            result["headers"] = headers
            columns = map_columns(headers)
            result["column_map"] = columns
            missing = Counter()
            stations, directions, districts, station_types, freeways = set(), set(), set(), set(), set()
            dates = []
            timestamp_col = columns.get("timestamp")
            for row in reader:
                if not row or all(v is None for v in row.values()):
                    continue
                result["rows"] += 1
                for key, value in row.items():
                    if value is None or not value.strip():
                        missing[key or "<extra>"] += 1
                station = (row.get(columns.get("station_id", ""), "") or "").strip()
                direction = (row.get(columns.get("direction", ""), "") or "").strip()
                district = (row.get(columns.get("district", ""), "") or "").strip()
                freeway = (row.get(columns.get("freeway", ""), "") or "").strip()
                station_type = (row.get(columns.get("station_type", ""), "") or "").strip()
                if "date" in columns and "time_of_day" in columns:
                    timestamp_value = (row.get(columns["date"], "") or "").strip() + " " + (row.get(columns["time_of_day"], "") or "").strip()
                else:
                    timestamp_value = (row.get(timestamp_col, "") or "").strip() if timestamp_col else ""
                dt = parse_timestamp(timestamp_value) if timestamp_col or ("date" in columns and "time_of_day" in columns) else None
                if timestamp_value and dt is None:
                    result["timestamp_parse_failures"] += 1
                if station:
                    stations.add(station)
                    station_rows[station] += 1
                    if dt:
                        key = (station, dt.isoformat())
                        if key in global_keys:
                            result["duplicate_station_timestamp_rows"] += 1
                        global_keys.add(key)
                        station_times[station].add(dt)
                if direction:
                    directions.add(direction)
                if district:
                    districts.add(district)
                if freeway:
                    freeways.add(freeway)
                if station_type:
                    station_types.add(station_type)
                if dt:
                    dates.append(dt)
            result["missing_by_column"] = dict(missing)
            result["station_ids"] = sorted(stations)
            result["directions"] = sorted(directions)
            result["districts"] = sorted(districts)
            result["station_types"] = sorted(station_types)
            result["freeways"] = sorted(freeways)
            if dates:
                result["date_min"] = min(dates).isoformat()
                result["date_max"] = max(dates).isoformat()
            if not headers:
                result["status"] = "empty_or_no_header"
    except (OSError, UnicodeError, csv.Error, zipfile.BadZipFile) as exc:
        result["status"] = f"read_error: {type(exc).__name__}: {exc}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", nargs="?", type=Path, default=Path("data/raw"), help="Folder containing unchanged source exports")
    parser.add_argument("--json", type=Path, default=Path("reports/dataset_inventory.json"), help="JSON report path")
    parser.add_argument("--markdown", type=Path, default=Path("reports/dataset_inventory.md"), help="Markdown report path")
    args = parser.parse_args()
    if not args.data_root.exists():
        parser.error(f"data folder does not exist: {args.data_root}")
    global_keys: set[tuple[str, str]] = set()
    station_times: dict[str, set[datetime]] = defaultdict(set)
    station_rows: Counter = Counter()
    files = [inventory_file(p, member, global_keys, station_times, station_rows) for p, member in sources(args.data_root)]
    stations = sorted(station_rows)
    station_time_checks = {}
    for station in stations:
        times = sorted(station_times[station])
        gaps = [(right - left).total_seconds() for left, right in zip(times, times[1:])]
        station_time_checks[station] = {
            "first_timestamp": times[0].isoformat() if times else None,
            "last_timestamp": times[-1].isoformat() if times else None,
            "unique_timestamps": len(times),
            "intervals_not_5_minutes": sum(delta != 300 for delta in gaps),
            "largest_interval_seconds": max(gaps) if gaps else None,
        }
    result = {
        "data_root": str(args.data_root),
        "file_count": len(files),
        "total_rows": sum(f["rows"] for f in files),
        "station_count": len(stations),
        "stations": stations,
        "rows_by_station": dict(sorted(station_rows.items())),
        "unique_timestamps_by_station": {s: len(station_times[s]) for s in stations},
        "timestamp_coverage_by_station": station_time_checks,
        "duplicate_station_timestamp_rows": sum(f["duplicate_station_timestamp_rows"] for f in files),
        "files": files,
        "notes": ["Inventory reads source files and does not modify them.", "Column matching is heuristic; review headers and units before analysis.", "Duplicate keys are counted across all scanned sources when station ID and timestamp can be parsed."],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Dataset inventory", "", f"- Data folder: `{args.data_root}`", f"- Files scanned: {result['file_count']}", f"- Parsed rows: {result['total_rows']}", f"- Station IDs found: {result['station_count']}", f"- Duplicate station/timestamp rows: {result['duplicate_station_timestamp_rows']}", "", "## Files", "", "| Source | Rows | Date range | Stations | Directions | Status |", "|---|---:|---|---:|---|---|"]
    for f in files:
        date_range = f"{f['date_min'] or 'unparsed'} to {f['date_max'] or 'unparsed'}"
        directions = ', '.join(f['directions']) or 'not detected'
        if f['districts']:
            directions += '; districts: ' + ', '.join(f['districts'])
        lines.append(f"| `{f['source']}` | {f['rows']} | {date_range} | {len(f['station_ids'])} | {directions} | {f['status']} |")
    if not files:
        lines.append("| No CSV, CSV.GZ, or ZIP CSV files found | 0 | - | 0 | - | waiting for PeMS export |")
    lines.extend(["", "## Station coverage", "", "| Station ID | Rows | Unique timestamps | First timestamp | Last timestamp | Intervals not 5 min |", "|---|---:|---:|---|---|---:|"])
    for station in stations:
        check = station_time_checks[station]
        lines.append(f"| `{station}` | {station_rows[station]} | {check['unique_timestamps']} | {check['first_timestamp'] or '-'} | {check['last_timestamp'] or '-'} | {check['intervals_not_5_minutes']} |")
    lines.extend(["", "## Review notes", "", "- See the JSON report for headers, inferred columns, missing values, and timestamp parse failures by source file.", "- Confirm units, station type, direction, and quality fields against PeMS metadata before analysis.", "- This report describes the scanned exports; it does not validate their scientific suitability.", ""])
    args.markdown.write_text("\n".join(lines), encoding="utf-8")
    print(f"Scanned {result['file_count']} file(s), {result['total_rows']} row(s), {result['station_count']} station(s).")
    print(f"Wrote {args.markdown} and {args.json}")


if __name__ == "__main__":
    main()
